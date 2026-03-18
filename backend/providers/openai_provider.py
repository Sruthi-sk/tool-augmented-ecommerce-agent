"""OpenAI LLM provider — default provider using function calling."""
import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from config import OPENAI_API_KEY
from providers.base import LLMProvider, LLMResponse, LLMChunk, ToolCall


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o"):
        self._client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        self._model = model

    async def generate(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> LLMResponse:
        kwargs = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + messages,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=json.loads(tc.function.arguments),
                    )
                )

        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason,
        )

    async def stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> AsyncIterator[LLMChunk]:
        kwargs = {
            "model": self._model,
            "messages": [{"role": "system", "content": system}] + messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = await self._client.chat.completions.create(**kwargs)
        async for chunk in response:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield LLMChunk(content=delta.content)
            if chunk.choices and chunk.choices[0].finish_reason:
                yield LLMChunk(is_done=True)
