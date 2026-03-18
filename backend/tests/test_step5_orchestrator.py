"""Step 5b: Orchestrator tests — end-to-end agent flow with mocked LLM."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from agent.orchestrator import AgentOrchestrator
from agent.session import InMemorySessionStore
from providers.base import LLMResponse, ToolCall
from tools.registry import ToolRegistry


@pytest.fixture
def mock_provider():
    provider = AsyncMock()
    return provider


@pytest.fixture
def test_registry():
    reg = ToolRegistry()

    @reg.register(
        name="search_parts",
        description="Search parts",
        parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
    )
    async def search_parts(query: str):
        return {"parts": [{"part_number": "PS123", "name": "Test Part"}], "source_url": "https://example.com"}

    return reg


@pytest.fixture
def orchestrator(mock_provider, test_registry):
    return AgentOrchestrator(
        provider=mock_provider,
        registry=test_registry,
        session_store=InMemorySessionStore(),
        provider_name="openai",
    )


@pytest.mark.asyncio
async def test_out_of_scope_returns_refusal(orchestrator):
    """Out-of-scope queries return a polite refusal without calling LLM."""
    result = await orchestrator.handle_message("What's the weather?", "session-1")
    assert result["type"] == "refusal"
    assert "refrigerator" in result["message"].lower() or "dishwasher" in result["message"].lower()


@pytest.mark.asyncio
async def test_in_scope_calls_llm(orchestrator, mock_provider):
    """In-scope queries call the LLM provider."""
    mock_provider.generate.return_value = LLMResponse(
        content="Here are some water filters for your refrigerator.",
        tool_calls=[],
    )
    result = await orchestrator.handle_message("Find me a refrigerator water filter", "session-1")
    assert mock_provider.generate.called


@pytest.mark.asyncio
async def test_tool_call_flow(orchestrator, mock_provider):
    """LLM tool call → execute tool → compose response."""
    # First call: LLM wants to use a tool
    mock_provider.generate.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc1", name="search_parts", arguments={"query": "water filter"})],
        ),
        # Second call: LLM composes response from tool result
        LLMResponse(
            content="I found a Test Part (PS123) for you.",
            tool_calls=[],
        ),
    ]
    result = await orchestrator.handle_message("Find me a refrigerator water filter", "session-1")
    assert mock_provider.generate.call_count == 2
    assert result["message"] is not None


@pytest.mark.asyncio
async def test_session_state_persists(orchestrator, mock_provider):
    """Session state carries across messages."""
    mock_provider.generate.return_value = LLMResponse(content="Got it.", tool_calls=[])

    await orchestrator.handle_message("I have a Whirlpool refrigerator model WDT780SAEM1", "session-1")

    # Session should have extracted entities
    session = await orchestrator._session_store.get("session-1")
    assert session.model_number == "WDT780SAEM1" or session.brand == "Whirlpool"


@pytest.mark.asyncio
async def test_orchestrator_returns_detail_data(orchestrator, mock_provider):
    """Response includes detail_data when tool was called."""
    mock_provider.generate.side_effect = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id="tc1", name="search_parts", arguments={"query": "filter"})],
        ),
        LLMResponse(content="Found parts.", tool_calls=[]),
    ]
    result = await orchestrator.handle_message("Search for refrigerator filter", "session-1")
    assert "detail_data" in result
