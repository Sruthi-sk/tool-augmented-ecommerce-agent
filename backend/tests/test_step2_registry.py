"""Step 2c: Tool registry tests."""
import pytest
from tools.registry import ToolRegistry


def test_registry_register_and_list():
    """Can register a tool and list it."""
    registry = ToolRegistry()

    @registry.register(
        name="test_tool",
        description="A test tool",
        parameters={
            "type": "object",
            "properties": {"query": {"type": "string", "description": "search query"}},
            "required": ["query"],
        },
    )
    async def test_tool(query: str):
        return {"result": query}

    tools = registry.list_tools()
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"


def test_registry_get_schemas_openai_format():
    """get_schemas('openai') returns OpenAI function calling format."""
    registry = ToolRegistry()

    @registry.register(
        name="search",
        description="Search for parts",
        parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )
    async def search(q: str):
        return {}

    schemas = registry.get_schemas("openai")
    assert len(schemas) == 1
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "search"
    assert schemas[0]["function"]["description"] == "Search for parts"


def test_registry_get_schemas_anthropic_format():
    """get_schemas('anthropic') returns Anthropic tool_use format."""
    registry = ToolRegistry()

    @registry.register(
        name="search",
        description="Search for parts",
        parameters={
            "type": "object",
            "properties": {"q": {"type": "string"}},
            "required": ["q"],
        },
    )
    async def search(q: str):
        return {}

    schemas = registry.get_schemas("anthropic")
    assert len(schemas) == 1
    assert schemas[0]["name"] == "search"
    assert schemas[0]["description"] == "Search for parts"
    assert "input_schema" in schemas[0]


@pytest.mark.asyncio
async def test_registry_execute_tool():
    """Can execute a registered tool by name."""
    registry = ToolRegistry()

    @registry.register(
        name="echo",
        description="Echo back",
        parameters={
            "type": "object",
            "properties": {"msg": {"type": "string"}},
            "required": ["msg"],
        },
    )
    async def echo(msg: str):
        return {"echoed": msg}

    result = await registry.execute("echo", {"msg": "hello"})
    assert result == {"echoed": "hello"}


@pytest.mark.asyncio
async def test_registry_execute_unknown_tool_raises():
    """Executing an unregistered tool raises KeyError."""
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        await registry.execute("nonexistent", {})
