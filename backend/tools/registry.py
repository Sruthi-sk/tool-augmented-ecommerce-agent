"""Tool registry with decorator-based registration and multi-provider schema generation."""
from typing import Any, Callable


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, dict] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: dict,
    ) -> Callable:
        """Decorator to register an async tool function."""
        def decorator(func: Callable) -> Callable:
            self._tools[name] = {
                "name": name,
                "description": description,
                "parameters": parameters,
                "func": func,
            }
            return func
        return decorator

    def list_tools(self) -> list[dict]:
        """Return tool metadata (without func) for inspection."""
        return [
            {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}
            for t in self._tools.values()
        ]

    def get_schemas(self, provider: str) -> list[dict]:
        """Return tool schemas in the format expected by the given provider."""
        if provider == "openai":
            return [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t["description"],
                        "parameters": t["parameters"],
                    },
                }
                for t in self._tools.values()
            ]
        elif provider == "anthropic":
            return [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"],
                }
                for t in self._tools.values()
            ]
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def execute(self, name: str, arguments: dict[str, Any]) -> Any:
        """Execute a registered tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")
        return await self._tools[name]["func"](**arguments)
