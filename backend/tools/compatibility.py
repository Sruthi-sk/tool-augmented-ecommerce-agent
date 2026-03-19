"""check_compatibility tool — check compatibility from structured index."""

from tools.registry import ToolRegistry


def register_compatibility_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="check_compatibility",
        description="Check if a specific part is compatible with a given appliance model number.",
        parameters={
            "type": "object",
            "properties": {
                "part_number": {
                    "type": "string",
                    "description": "PartSelect part number (e.g., PS11752778)",
                },
                "model_number": {
                    "type": "string",
                    "description": "Appliance model number (e.g., WDT780SAEM1)",
                },
            },
            "required": ["part_number", "model_number"],
        },
    )
    async def check_compatibility(part_number: str, model_number: str) -> dict:
        return await knowledge_service.check_compatibility(
            part_number=part_number, model_number=model_number
        )
