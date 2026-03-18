"""check_compatibility tool — check if a part is compatible with a model."""
from dataclasses import asdict

from retrieval.cache import CacheLayer
from retrieval.scraper import PartSelectRetriever
from tools.registry import ToolRegistry


def register_compatibility_tool(
    registry: ToolRegistry,
    cache: CacheLayer,
    retriever: PartSelectRetriever,
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
        async def fetcher():
            part = await retriever.fetch_part(part_number)
            if part is None:
                return None
            return asdict(part)

        cache_key = f"part:{part_number.upper()}"
        part_data = await cache.get_or_fetch(cache_key, fetcher)

        if part_data is None:
            return {
                "error": f"Part {part_number} not found.",
                "part_number": part_number,
                "model_number": model_number,
                "compatible": False,
            }

        compatible_models = part_data.get("compatible_models", [])
        model_upper = model_number.upper()
        is_compatible = any(
            model_upper in m.upper() for m in compatible_models
        )

        return {
            "compatible": is_compatible,
            "part_number": part_number,
            "part_name": part_data.get("name", ""),
            "model_number": model_number,
            "compatible_models_count": len(compatible_models),
            "source_url": part_data.get("source_url", ""),
        }
