"""OpenAI LLM provider — default provider using function calling."""
import asyncio
import json
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from config import OPENAI_API_KEY
from providers.base import LLMProvider, LLMResponse, LLMChunk, ToolCall

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    def __init__(self, model: str = "gpt-4o", max_retries: int = 3):
        self._client = AsyncOpenAI(api_key=OPENAI_API_KEY, max_retries=max_retries)
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

        for attempt in range(3):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"OpenAI call failed (attempt {attempt + 1}), retrying: {e}")
                    await asyncio.sleep(2 ** attempt)
                else:
                    raise
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
