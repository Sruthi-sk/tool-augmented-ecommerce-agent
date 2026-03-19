"""
Offline ingestion entrypoint.

Phase 0 skeleton:
- Creates the SQLite structured DB schema.
- Optionally bootstraps a *demo/dev* structured dataset from `backend/seed/seed_data.json`
  (disabled by default at runtime).
- Provides hooks for later "regenerate from PartSelect" using scraping (offline ingestion).
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiosqlite

from index.structured_store import normalize_symptom_key  # noqa: F401
from config import INDEX_DB_PATH
from retrieval.scraper import PartSelectRetriever


logger = logging.getLogger(__name__)


BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "index" / "schema.sql"
SEED_FILE = BASE_DIR / "seed" / "seed_data.json"


async def _apply_schema(db_path: str) -> None:
    schema = SCHEMA_PATH.read_text()
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(schema)
        NEW_COLS = [
            ("brand", "TEXT"),
            ("availability", "TEXT"),
            ("appliance_type", "TEXT"),
            ("install_difficulty", "TEXT"),
            ("install_time", "TEXT"),
            ("replace_parts", "TEXT"),
            ("symptoms_text", "TEXT"),
            ("repair_rating", "TEXT"),
        ]
        for col, coldef in NEW_COLS:
            try:
                await db.execute(f"ALTER TABLE parts ADD COLUMN {col} {coldef}")
            except Exception:
                pass
        await db.commit()

async def ensure_structured_index(
    db_path: str = INDEX_DB_PATH,
    bootstrap_from_seed: bool = False,
) -> None:
    """
    Ensure the pre-indexed structured DB exists with the expected schema.

    This is intended for runtime bootstrap in local dev/demo environments.
    It never performs network scraping.
    """
    # Detect schema presence cheaply.
    try:
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table' AND name = 'parts'
                LIMIT 1
                """
            )
            row = await cur.fetchone()
            await cur.close()
            has_schema = row is not None
    except Exception:
        has_schema = False

    if not has_schema:
        await _apply_schema(db_path)
        logger.info("Applied structured index schema to %s", db_path)

    if bootstrap_from_seed:
        # Populate only if empty-ish.
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT COUNT(1) FROM parts")
            count = (await cur.fetchone())[0]
            await cur.close()
        if count == 0:
            inserted = await _bootstrap_from_seed(db_path)
            logger.info("Bootstrapped %d parts from seed_data.json", inserted)



async def _bootstrap_from_seed(db_path: str) -> int:
    if not SEED_FILE.exists():
        logger.warning("Seed file not found: %s", SEED_FILE)
        return 0

    data = json.loads(SEED_FILE.read_text())
    parts = data.get("parts", [])

    inserted = 0
    ts = time.time()
    async with aiosqlite.connect(db_path) as db:
        for part in parts:
            pn = str(part["part_number"]).upper()
            await db.execute(
                """
                INSERT OR REPLACE INTO parts (
                  part_number, name, price, in_stock, description,
                  manufacturer_part_number, source_url, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pn,
                    part.get("name", ""),
                    part.get("price", ""),
                    1 if part.get("in_stock") else 0,
                    part.get("description", ""),
                    part.get("manufacturer_part_number"),
                    part.get("source_url", ""),
                    ts,
                ),
            )
            inserted += 1

            # Compatibility
            for mn in part.get("compatible_models", []) or []:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO part_compatibility (
                      part_number, model_number, evidence_url, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (pn, str(mn).upper(), part.get("source_url", ""), ts),
                )

            # Installation steps
            for i, step in enumerate(part.get("installation_steps", []) or []):
                await db.execute(
                    """
                    INSERT OR REPLACE INTO part_installation_steps (
                      part_number, step_index, step_text, evidence_url, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (pn, int(i), str(step), part.get("source_url", ""), ts),
                )

            # Symptom tags
            for symptom in part.get("symptoms", []) or []:
                sk = normalize_symptom_key(symptom)
                await db.execute(
                    """
                    INSERT OR REPLACE INTO part_symptoms (
                      part_number, symptom_key, evidence_url, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (pn, sk, part.get("source_url", ""), ts),
                )

        await db.commit()

    return inserted


async def _regenerate_part_from_partselect(db_path: str, part_number: str) -> None:
    """
    Optional later behavior:
    - Fetch PartSelect page
    - deterministically parse into tables
    """
    retriever = PartSelectRetriever()
    try:
        part = await retriever.fetch_part(part_number)
        if part is None:
            logger.warning("Part not found on PartSelect: %s", part_number)
            return

        ts = time.time()
        async with aiosqlite.connect(db_path) as db:
            pn = part.part_number.upper()
            await db.execute(
                """
                INSERT OR REPLACE INTO parts (
                  part_number, name, price, in_stock, description,
                  manufacturer_part_number, source_url, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pn,
                    part.name,
                    part.price,
                    1 if part.in_stock else 0,
                    part.description,
                    part.manufacturer_part_number,
                    part.source_url,
                    ts,
                ),
            )

            for mn in part.compatible_models or []:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO part_compatibility (
                      part_number, model_number, evidence_url, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (pn, mn.upper(), part.source_url, ts),
                )

            for i, step in enumerate(part.installation_steps or []):
                await db.execute(
                    """
                    INSERT OR REPLACE INTO part_installation_steps (
                      part_number, step_index, step_text, evidence_url, updated_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (pn, int(i), step, part.source_url, ts),
                )

            # symptoms parsing is not available in the scraper Phase 0, so we skip
            await db.commit()
    finally:
        await retriever.close()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=INDEX_DB_PATH)
    parser.add_argument("--bootstrap-from-seed", action="store_true")
    parser.add_argument("--regenerate", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    db_path = args.db_path

    await _apply_schema(db_path)
    logger.info("Applied schema to %s", db_path)

    if args.bootstrap_from_seed:
        inserted = await _bootstrap_from_seed(db_path)
        logger.info("Bootstrapped %d parts from seed_data.json", inserted)

    if args.regenerate:
        # Later: read parts from the seeded DB or seed file and regenerate.
        # For now: this is a placeholder loop.
        if not SEED_FILE.exists():
            logger.warning("Seed file missing; cannot regenerate")
            return

        seed = json.loads(SEED_FILE.read_text())
        part_numbers = [p["part_number"] for p in seed.get("parts", [])]
        for pn in part_numbers[:20]:
            logger.info("Regenerating part %s", pn)
            await _regenerate_part_from_partselect(db_path, pn)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())

