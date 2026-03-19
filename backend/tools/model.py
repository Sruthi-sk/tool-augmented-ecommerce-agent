"""lookup_model tool — fetch model overview from PartSelect."""

from tools.registry import ToolRegistry


def register_model_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="lookup_model",
        description=(
            "Look up an appliance model on PartSelect to get an overview: brand, "
            "appliance type, common symptoms, part categories, and sections. "
            "Use this when the user asks about a specific model number (not a "
            "specific part). Do NOT use this for part searches or compatibility checks."
        ),
        parameters={
            "type": "object",
            "properties": {
                "model_number": {
                    "type": "string",
                    "description": "The appliance model number (e.g., '10650022211', 'WDT780SAEM1')",
                },
            },
            "required": ["model_number"],
        },
    )
    async def lookup_model(model_number: str) -> dict:
        return await knowledge_service.lookup_model(model_number=model_number)
