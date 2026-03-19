"""get_installation_guide tool — fetch installation instructions for a part."""
from tools.registry import ToolRegistry


def register_installation_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="get_installation_guide",
        description="Get installation instructions for a specific part, including step-by-step guide and difficulty level.",
        parameters={
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "PartSelect part number (e.g., PS11752778)",
                },
            },
            "required": ["part_number"],
        },
    )
    async def get_installation_guide(part_number: str) -> dict:
        return await knowledge_service.get_installation_guide(part_number=part_number)
