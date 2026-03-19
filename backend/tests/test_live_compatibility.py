"""
Tests for live PartSelect compatibility widget fallback.

Tests the flow: local DB miss → crawl4ai navigates to part page →
fills model number in "Does this part fit my model?" widget →
clicks SEARCH → reads checkmark/X result.

Run with:
    pytest tests/test_live_compatibility.py -m live -v

Requires: crawl4ai, playwright chromium, internet access.
"""

import asyncio
import time
import pytest
import aiosqlite

from index.knowledge_service import _live_compatibility_check, KnowledgeService
from index.structured_store import StructuredStore
from index.help_vector_store import HelpVectorIndex
from ingestion.build_partselect_index import _apply_schema


# ─── Live tests (network + Playwright) ──────────────────────────────────────

pytestmark = pytest.mark.live


# Known compatible pair: PS11752778 (water filter) fits model 10650592000
PART_URL = "https://www.partselect.com/PS11752778-Whirlpool-W10295370A-Refrigerator-Water-Filter.htm"
PART_NUMBER = "PS11752778"
COMPATIBLE_MODEL = "10650592000"
INCOMPATIBLE_MODEL = "FAKEMODEL9999"


@pytest.mark.asyncio
async def test_live_compat_check_compatible():
    """Verify the live widget returns True for a known compatible model."""
    result = await _live_compatibility_check(PART_URL, COMPATIBLE_MODEL)
    assert result is True, f"Expected True for {COMPATIBLE_MODEL}, got {result}"


@pytest.mark.asyncio
async def test_live_compat_check_incompatible():
    """Verify the live widget returns False for a fake model number."""
    result = await _live_compatibility_check(PART_URL, INCOMPATIBLE_MODEL)
    assert result is False, f"Expected False for {INCOMPATIBLE_MODEL}, got {result}"


@pytest.mark.asyncio
async def test_full_fallback_flow_caches_result(tmp_path):
    """End-to-end: local DB miss → live check → result cached in part_compatibility."""
    db_path = str(tmp_path / "test_compat.db")

    # Set up schema and seed the part (but no compatibility rows for our model)
    await _apply_schema(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """INSERT INTO parts (part_number, name, price, in_stock, source_url, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (PART_NUMBER, "Refrigerator Water Filter", "$49.95", 1, PART_URL, time.time()),
        )
        await db.commit()

    # Build KnowledgeService with real structured store
    store = StructuredStore(db_path=db_path)
    await store.initialize()
    hvi = HelpVectorIndex(structured_db_path=db_path)
    await hvi.initialize()
    ks = KnowledgeService(structured_store=store, help_vector_index=hvi)

    try:
        # First call: local miss → should trigger live check
        result = await ks.check_compatibility(PART_NUMBER, COMPATIBLE_MODEL)
        assert result["compatible"] is True, f"Expected compatible=True, got {result}"
        assert result.get("live_checked") is True, "Expected live_checked flag"

        # Verify the result was cached in part_compatibility
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                "SELECT 1 FROM part_compatibility WHERE part_number = ? AND model_number = ?",
                (PART_NUMBER, COMPATIBLE_MODEL.upper()),
            )
            row = await cur.fetchone()
            await cur.close()
            assert row is not None, "Compatibility result should be cached in DB"

        # Second call: should hit the local cache (no live check)
        result2 = await ks.check_compatibility(PART_NUMBER, COMPATIBLE_MODEL)
        assert result2["compatible"] is True
        assert result2.get("live_checked") is None, "Second call should use cache, not live"
    finally:
        await store.close()
        await hvi.close()
