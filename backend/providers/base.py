from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: Optional[str] = None


@dataclass
class LLMChunk:
    content: str = ""
    is_tool_call: bool = False
    tool_call: Optional[ToolCall] = None
    is_done: bool = False


class LLMProvider(ABC):
    """Abstract base for LLM providers. All agent code uses this interface."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> LLMResponse:
        """Generate a complete response (non-streaming)."""
        ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
    ) -> AsyncIterator[LLMChunk]:
        """Stream response chunks."""
        ...
