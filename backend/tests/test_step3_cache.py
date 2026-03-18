"""Step 3a: SQLite cache layer tests."""
import pytest
import os
import asyncio
from retrieval.cache import CacheLayer


@pytest.fixture
async def cache(tmp_path):
    """Create a CacheLayer with a temp DB."""
    db_path = str(tmp_path / "test_cache.db")
    c = CacheLayer(db_path)
    await c.initialize()
    yield c
    await c.close()


@pytest.mark.asyncio
async def test_cache_set_and_get(cache):
    """Can store and retrieve a value."""
    await cache.set("part:PS123", {"name": "Water Filter", "price": 24.99})
    result = await cache.get("part:PS123")
    assert result is not None
    assert result["name"] == "Water Filter"
    assert result["price"] == 24.99


@pytest.mark.asyncio
async def test_cache_get_missing_returns_none(cache):
    """Getting a non-existent key returns None."""
    result = await cache.get("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_cache_get_or_fetch_uses_cache(cache):
    """get_or_fetch returns cached value without calling fetcher."""
    await cache.set("part:PS123", {"name": "Cached"})

    call_count = 0

    async def fetcher():
        nonlocal call_count
        call_count += 1
        return {"name": "Fresh"}

    result = await cache.get_or_fetch("part:PS123", fetcher)
    assert result["name"] == "Cached"
    assert call_count == 0


@pytest.mark.asyncio
async def test_cache_get_or_fetch_calls_fetcher_on_miss(cache):
    """get_or_fetch calls fetcher and caches result on cache miss."""
    async def fetcher():
        return {"name": "Fetched"}

    result = await cache.get_or_fetch("part:PS999", fetcher)
    assert result["name"] == "Fetched"

    # Should now be cached
    cached = await cache.get("part:PS999")
    assert cached["name"] == "Fetched"


@pytest.mark.asyncio
async def test_cache_ttl_expiry(cache):
    """Expired entries return None."""
    await cache.set("part:old", {"name": "Old"}, ttl_hours=0)
    # TTL of 0 hours means it's already expired
    result = await cache.get("part:old")
    assert result is None


@pytest.mark.asyncio
async def test_cache_overwrite(cache):
    """Setting the same key again overwrites the value."""
    await cache.set("key", {"v": 1})
    await cache.set("key", {"v": 2})
    result = await cache.get("key")
    assert result["v"] == 2
