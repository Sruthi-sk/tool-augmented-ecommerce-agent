"""get_part_details tool — fetch full details for a specific part from structured index."""

from tools.registry import ToolRegistry


def register_part_details_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="get_part_details",
        description="Get detailed information about a specific part by its PartSelect number (e.g., PS11752778).",
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
    async def get_part_details(part_number: str) -> dict:
        return await knowledge_service.get_part_details(part_number=part_number)
