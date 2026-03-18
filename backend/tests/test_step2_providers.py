"""Step 2a: LLM Provider abstraction tests."""
import pytest
from providers.base import LLMProvider, LLMResponse, ToolCall, LLMChunk


def test_llm_provider_is_abstract():
    """Cannot instantiate LLMProvider directly."""
    with pytest.raises(TypeError):
        LLMProvider()


def test_llm_response_dataclass():
    """LLMResponse holds content and optional tool calls."""
    resp = LLMResponse(content="hello")
    assert resp.content == "hello"
    assert resp.tool_calls == []
    assert resp.stop_reason is None


def test_llm_response_with_tool_calls():
    """LLMResponse can carry tool calls."""
    tc = ToolCall(id="tc_1", name="search_parts", arguments={"query": "filter"})
    resp = LLMResponse(content="", tool_calls=[tc])
    assert len(resp.tool_calls) == 1
    assert resp.tool_calls[0].name == "search_parts"


def test_llm_chunk_dataclass():
    """LLMChunk holds streaming fragment data."""
    chunk = LLMChunk(content="partial ")
    assert chunk.content == "partial "
    assert chunk.is_done is False
    assert chunk.is_tool_call is False
