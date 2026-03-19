"""search_parts tool — search structured index for parts by query."""

from tools.registry import ToolRegistry


def register_search_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="search_parts",
        description=(
            "Search for refrigerator or dishwasher parts on PartSelect by keyword query. "
            "When the user has provided a model number, ALWAYS pass it as model_number "
            "so results are filtered to parts compatible with that model."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'water filter', 'spray arm', 'ice maker')",
                },
                "appliance_type": {
                    "type": "string",
                    "enum": ["refrigerator", "dishwasher"],
                    "description": "Type of appliance to search parts for",
                },
                "model_number": {
                    "type": "string",
                    "description": "Appliance model number to filter results to compatible parts only (e.g., 'WDT780SAEM1')",
                },
            },
            "required": ["query", "appliance_type"],
        },
    )
    async def search_parts(query: str, appliance_type: str, model_number: str = "") -> dict:
        parts_result = await knowledge_service.search_parts(
            query=query, appliance_type=appliance_type, model_number=model_number or None
        )
        result = {
            "parts": parts_result["parts"],
            "query": query,
            "appliance_type": appliance_type,
            "source_url": f"https://www.partselect.com/Search.aspx?q={query}",
        }
        if model_number:
            result["model_number"] = model_number
            result["filtered_by_model"] = True
        return result
