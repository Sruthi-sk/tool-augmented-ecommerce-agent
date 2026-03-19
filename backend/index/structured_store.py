"""
StructuredStore: query-time read API over the pre-indexed SQLite database.

This layer must be the source of truth for exact facts:
- part metadata
- part compatibility facts
- installation steps
- structured troubleshooting evidence (where available)
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Optional

import aiosqlite

from config import INDEX_DB_PATH

logger = logging.getLogger(__name__)


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


# ── Symptom key normalization ────────────────────────────────────────────────
# Bump this when the normalization logic changes.  Re-ingestion is required
# after a version change so that stored symptom_keys match query-time keys.
SYMPTOM_NORM_VERSION = 2

# Common synonyms that users and ingestion sources express differently.
# Maps variant → canonical form.  Applied after lowercasing.
_SYMPTOM_SYNONYMS: dict[str, str] = {
    "doesnt": "does not",
    "doesn't": "does not",
    "dont": "do not",
    "don't": "do not",
    "wont": "will not",
    "won't": "will not",
    "isnt": "is not",
    "isn't": "is not",
    "cant": "cannot",
    "can't": "cannot",
    "noisy": "making noise",
    "loud": "making noise",
    "leaks": "leaking",
    "leak": "leaking",
    "drips": "leaking",
    "drip": "leaking",
    "frosting": "frost buildup",
    "icing": "frost buildup",
    "icy": "frost buildup",
}

# Stop words removed from symptom keys — articles, prepositions, and filler
# that don't carry diagnostic meaning.
_STOP_WORDS: frozenset[str] = frozenset(
    "a an the my our your its is are was were be been being "
    "of in on for to at by with from and or but".split()
)

# Regex for punctuation stripping (keep alphanumeric + spaces).
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def normalize_symptom_key(symptom: str) -> str:
    """Deterministic symptom normalization shared by ingestion and query-time.

    Pipeline: lowercase → punctuation strip → synonym replacement →
    stop-word removal → whitespace collapse → sorted tokens.

    Both ingestion (crawl_partselect.py, build_partselect_index.py) and
    query-time (StructuredStore, KnowledgeService) import this function,
    ensuring keys always match.
    """
    s = (symptom or "").strip().lower()
    s = _PUNCT_RE.sub(" ", s)

    # Apply synonym mapping (longest-first to avoid partial replacement).
    for variant, canonical in _SYMPTOM_SYNONYMS.items():
        s = s.replace(variant, canonical)

    # Remove stop words and collapse whitespace.
    tokens = [t for t in s.split() if t not in _STOP_WORDS]
    return " ".join(tokens)


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

    async def search_parts(
        self, query: str, appliance_type: str, model_number: Optional[str] = None
    ) -> list[dict]:
        """
        Deterministic search over structured data.

        When *model_number* is provided the results are filtered to parts that
        are known-compatible with that model (via the part_compatibility table).

        Notes:
        - This is primarily for PartSelect-like keyword discovery (demo/demo test flows).
        - For long-form semantic retrieval, use KnowledgeService+HelpVectorIndex.
        """
        assert self._db is not None, "Call initialize() first"
        q = (query or "").strip()
        if not q:
            return []

        mn = (model_number or "").strip().upper() if model_number else ""

        rows: list[aiosqlite.Row] = []

        # ── Model-filtered search (highest priority) ────────────────────────
        if mn:
            try:
                rows = await self._fetchall(
                    """
                    SELECT DISTINCT p.part_number, p.name, p.price, p.source_url
                    FROM parts p
                    JOIN part_compatibility pc ON pc.part_number = p.part_number
                    WHERE pc.model_number = ?
                      AND (
                        p.name LIKE '%' || ? || '%'
                        OR p.description LIKE '%' || ? || '%'
                      )
                    LIMIT 25
                    """,
                    (mn, q, q),
                )
            except Exception:
                rows = []

        # ── Appliance-type search (fallback when no model or no model hits) ─
        if not rows:
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

        # ── Bare keyword fallback (Phase 0 bootstrap / empty models table) ──
        if not rows:
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

    async def get_model_overview(self, model_number: str) -> Optional[dict]:
        """Build a model overview from local DB data.

        Returns None if the model is not in the database.
        """
        assert self._db is not None, "Call initialize() first"
        mn = model_number.strip().upper()

        # Basic model info
        model = await self._fetchone(
            "SELECT model_number, brand, appliance_type FROM models WHERE model_number = ?",
            (mn,),
        )
        if not model:
            return None

        brand = model["brand"] or ""
        appliance_type = model["appliance_type"] or ""

        # Compatible parts (for part categories)
        parts_rows = await self._fetchall(
            """
            SELECT p.part_number, p.name, p.price, p.source_url
            FROM parts p
            JOIN part_compatibility pc ON pc.part_number = p.part_number
            WHERE pc.model_number = ?
            ORDER BY p.name
            """,
            (mn,),
        )

        # Build part categories from part names
        cat_counts: dict[str, int] = {}
        for row in parts_rows:
            name = row["name"] or ""
            # Extract the main category word(s) — e.g. "Water Filter", "Ice Maker"
            # Use the full name as the category since parts have descriptive names
            cat_counts[name] = cat_counts.get(name, 0) + 1

        part_categories = [
            {"name": name, "count": count}
            for name, count in sorted(cat_counts.items())
        ]

        # Symptoms from repair stories for parts compatible with this model
        symptom_rows = await self._fetchall(
            """
            SELECT DISTINCT ps.symptom_key
            FROM part_symptoms ps
            JOIN part_compatibility pc ON pc.part_number = ps.part_number
            WHERE pc.model_number = ?
            ORDER BY ps.symptom_key
            LIMIT 30
            """,
            (mn,),
        )
        common_symptoms = [row["symptom_key"] for row in symptom_rows]

        # Also get structured troubleshooting symptoms for this appliance type
        if appliance_type:
            ts_rows = await self._fetchall(
                """
                SELECT DISTINCT symptom_key
                FROM troubleshooting_causes
                WHERE appliance_type = ?
                ORDER BY symptom_key
                """,
                (appliance_type,),
            )
            structured_symptoms = [row["symptom_key"] for row in ts_rows]
        else:
            structured_symptoms = []

        # Build title
        title_parts = [mn]
        if brand:
            title_parts.append(brand)
        if appliance_type:
            title_parts.append(appliance_type.capitalize())
        model_title = " ".join(title_parts)

        source_url = f"https://www.partselect.com/Models/{mn}/"

        return {
            "model_number": mn,
            "model_title": model_title,
            "brand": brand,
            "appliance_type": appliance_type,
            "common_symptoms": common_symptoms[:15],
            "structured_symptoms": structured_symptoms[:15],
            "sections": [],  # Only available from live scrape
            "part_categories": part_categories[:20],
            "parts_count": len(parts_rows),
            "source_url": source_url,
        }

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

        # Positive match: model is in our index → definitively compatible
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
                "compatible": True,
                "part_number": part_number,
                "part_name": part["name"] or "",
                "model_number": model_number,
                "compatible_models_count": compatible_models_count,
                "source_url": evidence_url or (part["source_url"] or ""),
            }

        # Negative: model not found in local index. The index is always
        # partial (PartSelect paginates models, we only capture ~30), so
        # we can never authoritatively say "incompatible" from local data.
        # Return None to signal KnowledgeService to try the live check.
        return {
            "compatible": None,
            "part_number": part_number,
            "part_name": part["name"] or "",
            "model_number": model_number,
            "compatible_models_count": compatible_models_count,
            "source_url": part["source_url"] or "",
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
            logger.warning(
                "No troubleshooting causes for appliance=%s symptom_key=%r "
                "(raw=%r, norm_version=%d). Check ingestion normalization.",
                appliance_type, symptom_key, symptom, SYMPTOM_NORM_VERSION,
            )
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

