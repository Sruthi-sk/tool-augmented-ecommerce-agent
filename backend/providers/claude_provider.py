"""Anthropic Claude LLM provider using tool_use."""
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from config import ANTHROPIC_API_KEY
from providers.base import LLMProvider, LLMResponse, LLMChunk, ToolCall


class ClaudeProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
        self._model = model

    async def generate(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> LLMResponse:
        kwargs = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        content = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        arguments=block.input,
                    )
                )

        return LLMResponse(
            content=content,
            tool_calls=tool_calls,
            stop_reason=response.stop_reason,
        )

    async def stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> AsyncIterator[LLMChunk]:
        kwargs = {
            "model": self._model,
            "max_tokens": 4096,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield LLMChunk(content=text)
            yield LLMChunk(is_done=True)
