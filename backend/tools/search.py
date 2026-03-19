"""search_parts tool — search structured index for parts by query."""

from tools.registry import ToolRegistry


def register_search_tool(
    registry: ToolRegistry,
    knowledge_service,
) -> None:
    @registry.register(
        name="search_parts",
        description="Search for refrigerator or dishwasher parts on PartSelect by keyword query.",
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
            },
            "required": ["query", "appliance_type"],
        },
    )
    async def search_parts(query: str, appliance_type: str) -> dict:
        parts_result = await knowledge_service.search_parts(query=query, appliance_type=appliance_type)
        return {
            "parts": parts_result["parts"],
            "query": query,
            "appliance_type": appliance_type,
            "source_url": f"https://www.partselect.com/Search.aspx?q={query}",
        }
