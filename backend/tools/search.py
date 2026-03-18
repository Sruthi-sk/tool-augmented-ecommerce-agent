"""search_parts tool — search PartSelect for parts by query."""
from dataclasses import asdict

from retrieval.cache import CacheLayer
from retrieval.scraper import PartSelectRetriever
from tools.registry import ToolRegistry


def register_search_tool(
    registry: ToolRegistry,
    cache: CacheLayer,
    retriever: PartSelectRetriever,
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
        async def fetcher():
            results = await retriever.search(query, appliance_type)
            return [asdict(r) for r in results]

        cache_key = f"search:{appliance_type}:{query.lower().strip()}"
        parts = await cache.get_or_fetch(cache_key, fetcher, ttl_hours=6)
        return {
            "parts": parts,
            "query": query,
            "appliance_type": appliance_type,
            "source_url": f"https://www.partselect.com/Search.aspx?q={query}",
        }
