"""get_part_details tool — fetch full details for a specific part."""
from dataclasses import asdict

from retrieval.cache import CacheLayer
from retrieval.scraper import PartSelectRetriever
from tools.registry import ToolRegistry


def register_part_details_tool(
    registry: ToolRegistry,
    cache: CacheLayer,
    retriever: PartSelectRetriever,
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
        async def fetcher():
            part = await retriever.fetch_part(part_number)
            if part is None:
                return None
            return asdict(part)

        cache_key = f"part:{part_number.upper()}"
        result = await cache.get_or_fetch(cache_key, fetcher)

        if result is None:
            return {"error": f"Part {part_number} not found.", "part_number": part_number}

        return result
