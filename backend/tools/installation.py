"""get_installation_guide tool — fetch installation instructions for a part."""
from dataclasses import asdict

from retrieval.cache import CacheLayer
from retrieval.scraper import PartSelectRetriever
from tools.registry import ToolRegistry


def register_installation_tool(
    registry: ToolRegistry,
    cache: CacheLayer,
    retriever: PartSelectRetriever,
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
        async def fetcher():
            part = await retriever.fetch_part(part_number)
            if part is None:
                return None
            return asdict(part)

        cache_key = f"part:{part_number.upper()}"
        part_data = await cache.get_or_fetch(cache_key, fetcher)

        if part_data is None:
            return {"error": f"Part {part_number} not found.", "part_number": part_number}

        steps = part_data.get("installation_steps", [])
        if not steps:
            steps = [
                f"Refer to the PartSelect page for installation instructions for {part_data.get('name', part_number)}."
            ]

        return {
            "part_number": part_number,
            "part_name": part_data.get("name", ""),
            "steps": steps,
            "source_url": part_data.get("source_url", ""),
        }
