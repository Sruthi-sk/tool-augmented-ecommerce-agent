"""Agent orchestrator: preprocess → LLM tool_use → execute → compose response."""
import json
import logging
from typing import Optional

from agent.preprocessor import preprocess
from agent.session import Session, SessionStore
from providers.base import LLMProvider, LLMResponse, ToolCall
from tools.registry import ToolRegistry
from agent.validation import validate_and_maybe_ground

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the PartSelect Parts Assistant, helping customers find and learn about \
refrigerator and dishwasher replacement parts.

RULES:
- ONLY answer questions about refrigerator and dishwasher parts from PartSelect.
- NEVER invent or guess product information. Only use data returned by your tools.
- ALWAYS cite the source URL when providing factual product information.
- If a tool returns no results, say so honestly — do not fabricate an answer.
- If you need a model number or part number to help, ask for it.
- Do not answer questions about other appliances, general knowledge, or unrelated topics.
  Politely redirect: "I can only help with refrigerator and dishwasher parts from PartSelect."

RESPONSE FORMAT:
- Be concise and helpful.
- Lead with the direct answer.
- Include the source link when citing product data.
- Suggest logical next steps (e.g., "Would you like installation instructions?").

CONVERSATION CONTEXT:
{context}"""


def _build_tool_result_message(tool_call: ToolCall, result: dict, provider_name: str) -> dict:
    """Format a tool result as a message for the LLM."""
    if provider_name == "openai":
        return {
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result),
        }
    else:  # anthropic
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": json.dumps(result),
                }
            ],
        }


def _build_assistant_tool_call_message(tool_call: ToolCall, provider_name: str) -> dict:
    """Format the assistant's tool call as a message for the conversation."""
    if provider_name == "openai":
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.arguments),
                    },
                }
            ],
        }
    else:  # anthropic
        return {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": tool_call.id,
                    "name": tool_call.name,
                    "input": tool_call.arguments,
                }
            ],
        }


class AgentOrchestrator:
    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        session_store: SessionStore,
        provider_name: str = "openai",
    ):
        self._provider = provider
        self._registry = registry
        self._session_store = session_store
        self._provider_name = provider_name

    async def handle_message(self, message: str, session_id: str) -> dict:
        """Process a user message through the full agent pipeline."""
        # 1. Get or create session
        session = await self._session_store.get(session_id)

        # 2. Pre-process (deterministic)
        pre = preprocess(message)

        # Update session with extracted entities
        if pre.entities:
            session.update(**pre.entities)
            await self._session_store.save(session)

        # 3. Scope gate — skip refusal if session has active context
        #    (follow-ups like "yes" / "sure" won't match keywords but are valid)
        has_session_context = bool(
            session.conversation_history
            and (session.part_number or session.model_number)
        )
        if not pre.is_in_scope and not has_session_context:
            session.add_message(role="user", content=message)
            session.add_message(role="assistant", content=pre.refusal_message)
            await self._session_store.save(session)
            return {
                "type": "refusal",
                "message": pre.refusal_message,
                "detail_data": None,
                "response_type": None,
                "source_url": None,
                "suggested_actions": [],
            }

        # 4. Build messages for LLM
        session.add_message(role="user", content=message)
        context = session.get_context_for_llm()
        system = SYSTEM_PROMPT.format(context=json.dumps(context, indent=2))

        llm_messages = [
            {"role": m.role, "content": m.content}
            for m in session.conversation_history
        ]

        tool_schemas = self._registry.get_schemas(self._provider_name)

        # 5. First LLM call — may return tool calls
        try:
            response = await self._provider.generate(llm_messages, system, tool_schemas)
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            error_msg = "I'm having trouble processing that right now. Could you try rephrasing?"
            session.add_message(role="assistant", content=error_msg)
            await self._session_store.save(session)
            return {
                "type": "error",
                "message": error_msg,
                "detail_data": None,
                "response_type": None,
                "source_url": None,
                "suggested_actions": [],
            }

        # 6. If tool calls, execute (bounded) and compose
        detail_data = None
        response_type = None
        source_url = None

        max_tool_calls = 2
        tool_call_count = 0

        # The LLM may request a first tool call, and optionally a second tool call
        # if it needs more exact facts (e.g., search -> details -> compatibility).
        while response.tool_calls and tool_call_count < max_tool_calls:
            tool_call = response.tool_calls[0]  # Handle first tool call from this LLM response

            try:
                tool_result = await self._registry.execute(tool_call.name, tool_call.arguments)
            except Exception as e:
                logger.error(f"Tool execution failed: {e}")
                tool_result = {"error": str(e)}

            detail_data = tool_result
            source_url = tool_result.get("source_url")
            response_type = self._infer_response_type(tool_call.name)

            # Update session with tool result (for follow-ups)
            session.update(
                last_tool_result=tool_result,
                last_source_url=source_url,
            )

            # Append tool call + tool result to messages
            llm_messages.append(_build_assistant_tool_call_message(tool_call, self._provider_name))
            llm_messages.append(_build_tool_result_message(tool_call, tool_result, self._provider_name))
            tool_call_count += 1

            # Next LLM call:
            # - If we can still call more tools, allow tool calling.
            # - Otherwise, disable tools to force natural language composition.
            next_tools = tool_schemas if tool_call_count < max_tool_calls else []
            try:
                response = await self._provider.generate(llm_messages, system, next_tools)
            except Exception as e:
                logger.error(f"LLM composition failed: {e}")
                response = LLMResponse(content="I found some results but had trouble formatting the response.")
                break

        # 7. Finalize (deterministic grounding/validation)
        assistant_message = response.content or "I wasn't able to generate a response."
        validated_message = validate_and_maybe_ground(
            assistant_message=assistant_message,
            response_type=response_type,
            detail_data=detail_data,
        )
        session.add_message(role="assistant", content=validated_message)
        await self._session_store.save(session)

        suggested = self._suggest_actions(response_type, detail_data)

        return {
            "type": "response",
            "message": validated_message,
            "detail_data": detail_data,
            "response_type": response_type,
            "source_url": source_url,
            "suggested_actions": suggested,
        }

    def _infer_response_type(self, tool_name: str) -> str:
        """Map tool name to frontend response_type."""
        mapping = {
            "search_parts": "search_results",
            "get_part_details": "product",
            "check_compatibility": "compatibility",
            "get_installation_guide": "installation",
            "diagnose_symptom": "troubleshooting",
        }
        return mapping.get(tool_name, "generic")

    def _suggest_actions(self, response_type: Optional[str], detail_data: Optional[dict]) -> list[str]:
        """Generate contextual suggested actions."""
        if response_type == "search_results":
            return ["Show me details for a part", "Check compatibility with my model"]
        elif response_type == "product":
            return ["Check compatibility", "How to install this part", "View on PartSelect"]
        elif response_type == "compatibility":
            if detail_data and detail_data.get("compatible"):
                return ["How to install this part", "View part details", "View on PartSelect"]
            return ["Find compatible parts", "Search for alternatives"]
        elif response_type == "installation":
            return ["Check compatibility with my model", "View part details"]
        elif response_type == "troubleshooting":
            return ["Find replacement parts", "Check compatibility"]
        return []
