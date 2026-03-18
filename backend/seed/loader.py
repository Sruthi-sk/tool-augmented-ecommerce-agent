"""Load seed data into the cache on startup."""
import json
import logging
from pathlib import Path

from retrieval.cache import CacheLayer

logger = logging.getLogger(__name__)

SEED_FILE = Path(__file__).parent / "seed_data.json"


async def load_seed_data(cache: CacheLayer, ttl_hours: int = 720) -> int:
    """Load seed_data.json into the cache. Returns number of entries loaded.

    Uses a long TTL (default 30 days) so seed data stays cached.
    Skips entries that already exist in the cache.
    """
    if not SEED_FILE.exists():
        logger.warning("Seed file not found at %s", SEED_FILE)
        return 0

    with open(SEED_FILE) as f:
        data = json.load(f)

    loaded = 0

    # Load individual parts
    for part in data.get("parts", []):
        cache_key = f"part:{part['part_number'].upper()}"
        existing = await cache.get(cache_key)
        if existing is None:
            await cache.set(cache_key, part, ttl_hours=ttl_hours)
            loaded += 1

    # Load search indexes
    for entry in data.get("search_indexes", []):
        cache_key = f"search:{entry['appliance_type']}:{entry['query'].lower().strip()}"
        existing = await cache.get(cache_key)
        if existing is None:
            await cache.set(cache_key, entry["results"], ttl_hours=ttl_hours)
            loaded += 1

    logger.info("Loaded %d seed entries into cache", loaded)
    return loaded
