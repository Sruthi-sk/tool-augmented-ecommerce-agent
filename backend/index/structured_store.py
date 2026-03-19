"""
StructuredStore: query-time read API over the pre-indexed SQLite database.

This layer must be the source of truth for exact facts:
- part metadata
- part compatibility facts
- installation steps
- structured troubleshooting evidence (where available)
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import aiosqlite

from config import INDEX_DB_PATH


@dataclass(frozen=True)
class PartDetails:
    part_number: str
    name: str
    price: str
    in_stock: bool
    description: str
    manufacturer_part_number: Optional[str]
    source_url: str
    compatible_models: list[str]
    installation_steps: list[str]
    symptoms: list[str]


@dataclass(frozen=True)
class CompatibilityResult:
    compatible: bool
    part_number: str
    part_name: str
    model_number: str
    compatible_models_count: int
    source_url: str


def normalize_symptom_key(symptom: str) -> str:
    """Deterministic symptom normalization used across structured ingestion."""
    s = (symptom or "").strip().lower()
    # Minimal normalization; ingestion can choose richer mapping later.
    s = " ".join(s.split())
    return s


class StructuredStore:
    def __init__(self, db_path: str = INDEX_DB_PATH):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Open connection. Schema creation is expected to be run by ingestion."""
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def _fetchone(self, query: str, params: tuple[Any, ...]) -> Optional[aiosqlite.Row]:
        assert self._db is not None, "Call initialize() first"
        cur = await self._db.execute(query, params)
        row = await cur.fetchone()
        await cur.close()
        return row

    async def _fetchall(self, query: str, params: tuple[Any, ...]) -> list[aiosqlite.Row]:
        assert self._db is not None, "Call initialize() first"
        cur = await self._db.execute(query, params)
        rows = await cur.fetchall()
        await cur.close()
        return rows

    async def get_part_details(self, part_number: str) -> Optional[dict]:
        assert self._db is not None, "Call initialize() first"
        pn = part_number.upper()

        part = await self._fetchone(
            """
            SELECT part_number, name, price, in_stock, description,
                   manufacturer_part_number, source_url,
                   brand, availability, appliance_type,
                   install_difficulty, install_time, replace_parts,
                   symptoms_text, repair_rating
            FROM parts
            WHERE part_number = ?
            """,
            (pn,),
        )
        if not part:
            return None

        compat_rows = await self._fetchall(
            """
            SELECT model_number
            FROM part_compatibility
            WHERE part_number = ?
            """,
            (pn,),
        )
        compatible_models = [r["model_number"] for r in compat_rows]

        steps_rows = await self._fetchall(
            """
            SELECT step_text
            FROM part_installation_steps
            WHERE part_number = ?
            ORDER BY step_index ASC
            """,
            (pn,),
        )
        installation_steps = [r["step_text"] for r in steps_rows]

        symptom_rows = await self._fetchall(
            """
            SELECT symptom_key
            FROM part_symptoms
            WHERE part_number = ?
            """,
            (pn,),
        )
        symptoms = [r["symptom_key"] for r in symptom_rows]

        return {
            "part_number": part["part_number"],
            "name": part["name"],
            "price": part["price"] or "",
            "in_stock": bool(part["in_stock"]) if part["in_stock"] is not None else False,
            "description": part["description"] or "",
            "manufacturer_part_number": part["manufacturer_part_number"],
            "source_url": part["source_url"] or "",
            "compatible_models": compatible_models,
            "installation_steps": installation_steps,
            "symptoms": symptoms,
            "brand": part["brand"] or None,
            "availability": part["availability"] or None,
            "appliance_type": part["appliance_type"] or None,
            "install_difficulty": part["install_difficulty"] or None,
            "install_time": part["install_time"] or None,
            "replace_parts": part["replace_parts"] or None,
            "symptoms_text": part["symptoms_text"] or None,
            "repair_rating": part["repair_rating"] or None,
        }

    async def search_parts(self, query: str, appliance_type: str) -> list[dict]:
        """
        Deterministic search over structured data.

        Notes:
        - This is primarily for PartSelect-like keyword discovery (demo/demo test flows).
        - For long-form semantic retrieval, use KnowledgeService+HelpVectorIndex.
        """
        assert self._db is not None, "Call initialize() first"
        q = (query or "").strip()
        if not q:
            return []

        # Appliance type currently lives in models; use a join for compatibility-model-driven search.
        # If the dataset doesn't have models/appliance_type populated, we fall back to LIKE on parts fields.
        rows: list[aiosqlite.Row] = []
        try:
            rows = await self._fetchall(
                """
                SELECT DISTINCT p.part_number, p.name, p.price, p.source_url
                FROM parts p
                JOIN part_compatibility pc ON pc.part_number = p.part_number
                JOIN models m ON m.model_number = pc.model_number
                WHERE m.appliance_type = ?
                  AND (
                    p.name LIKE '%' || ? || '%'
                    OR p.description LIKE '%' || ? || '%'
                  )
                LIMIT 25
                """,
                (appliance_type, q, q),
            )
        except Exception:
            rows = []

        if not rows:
            # If models/appliance_type aren't populated yet (Phase 0 bootstrap),
            # fall back to keyword matching on `parts`.
            rows = await self._fetchall(
                """
                SELECT part_number, name, price, source_url
                FROM parts
                WHERE name LIKE '%' || ? || '%'
                   OR description LIKE '%' || ? || '%'
                LIMIT 25
                """,
                (q, q),
            )

        return [
            {
                "part_number": r["part_number"],
                "name": r["name"],
                "price": r["price"] or "",
                "url": r["source_url"] or "",
            }
            for r in rows
        ]

    async def check_compatibility(self, part_number: str, model_number: str) -> dict:
        assert self._db is not None, "Call initialize() first"
        pn = part_number.upper()
        mn = model_number.upper()

        part = await self._fetchone(
            """
            SELECT name, source_url
            FROM parts
            WHERE part_number = ?
            """,
            (pn,),
        )
        if not part:
            return {
                "compatible": False,
                "part_number": part_number,
                "part_name": "",
                "model_number": model_number,
                "compatible_models_count": 0,
                "source_url": "",
                "error": f"Part {part_number} not found.",
            }

        compat_rows = await self._fetchall(
            """
            SELECT model_number, evidence_url
            FROM part_compatibility
            WHERE part_number = ?
            """,
            (pn,),
        )
        compatible_models = [r["model_number"] for r in compat_rows]
        compatible_models_count = len(compatible_models)
        compatible = any(mn == m for m in compatible_models)

        # If the model isn't in our index but we have some models on record,
        # we can't confidently say "incompatible" — the index may be partial.
        # Only return compatible=False with high confidence when the part exists
        # AND we have a meaningful number of models indexed.
        index_complete = compatible_models_count >= 20
        if not compatible and not index_complete:
            return {
                "compatible": None,  # unknown — not enough index coverage
                "part_number": part_number,
                "part_name": part["name"] or "",
                "model_number": model_number,
                "compatible_models_count": compatible_models_count,
                "source_url": part["source_url"] or "",
                "note": (
                    "Compatibility could not be confirmed from the local index. "
                    "Please verify on the PartSelect product page."
                ),
            }

        evidence_url = ""
        if compatible:
            evidence_url_row = await self._fetchone(
                """
                SELECT evidence_url
                FROM part_compatibility
                WHERE part_number = ? AND model_number = ?
                """,
                (pn, mn),
            )
            evidence_url = evidence_url_row["evidence_url"] if evidence_url_row else ""

        return {
            "compatible": compatible,
            "part_number": part_number,
            "part_name": part["name"] or "",
            "model_number": model_number,
            "compatible_models_count": compatible_models_count,
            "source_url": evidence_url or (part["source_url"] or ""),
        }

    async def get_installation_steps(self, part_number: str) -> dict:
        assert self._db is not None, "Call initialize() first"
        pn = part_number.upper()

        part = await self._fetchone(
            """
            SELECT name, source_url
            FROM parts
            WHERE part_number = ?
            """,
            (pn,),
        )
        if not part:
            return {"error": f"Part {part_number} not found.", "part_number": part_number}

        steps_rows = await self._fetchall(
            """
            SELECT step_text
            FROM part_installation_steps
            WHERE part_number = ?
            ORDER BY step_index ASC
            """,
            (pn,),
        )
        steps = [r["step_text"] for r in steps_rows]
        return {
            "part_number": part_number,
            "part_name": part["name"] or "",
            "steps": steps,
            "source_url": part["source_url"] or "",
        }

    async def get_troubleshooting_causes(self, appliance_type: str, symptom: str) -> dict:
        assert self._db is not None, "Call initialize() first"
        symptom_key = normalize_symptom_key(symptom)

        rows = await self._fetchall(
            """
            SELECT likely_cause_text, recommended_part_number, part_type, likelihood, evidence_url
            FROM troubleshooting_causes
            WHERE appliance_type = ? AND symptom_key = ?
            LIMIT 20
            """,
            (appliance_type, symptom_key),
        )

        if not rows:
            return {
                "causes": [],
                "likely_causes": [],
                "recommended_parts": [],
                "source_urls": [],
                "matched_symptom": symptom_key,
            }

        likely_causes = [
            {
                "cause": r["likely_cause_text"],
                "part_type": r["part_type"],
                "likelihood": r["likelihood"],
            }
            for r in rows
        ]

        recommended_parts = sorted(
            {
                r["recommended_part_number"]
                for r in rows
                if r["recommended_part_number"]
            }
        )

        source_urls = sorted({r["evidence_url"] for r in rows if r["evidence_url"]})

        # Frontend expects `causes` + `source_url` today; service can map later.
        return {
            "causes": likely_causes,
            "likely_causes": likely_causes,
            "recommended_parts": recommended_parts,
            "source_urls": source_urls,
            "matched_symptom": symptom_key,
        }

