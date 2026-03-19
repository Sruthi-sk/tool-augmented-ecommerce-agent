"""
KnowledgeService: high-level abstraction used by tools.

Tools should not coordinate multiple retrieval backends. Instead:
- Tools call KnowledgeService.
- KnowledgeService merges structured facts (StructuredStore) with semantic help
  (HelpVectorIndex) deterministically.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from index.help_vector_store import HelpVectorIndex
from index.structured_store import StructuredStore
from index.structured_store import normalize_symptom_key


class KnowledgeService:
    def __init__(
        self,
        structured_store: StructuredStore,
        help_vector_index: HelpVectorIndex,
        # Optional: a cache can be injected later (Phase 0 avoids changing runtime).
        query_cache: Optional[Any] = None,
    ):
        self._structured_store = structured_store
        self._help_vector_index = help_vector_index
        self._query_cache = query_cache

    async def search_parts(self, query: str, appliance_type: str) -> dict:
        parts = await self._structured_store.search_parts(query=query, appliance_type=appliance_type)
        return {
            "parts": parts,
            "query": query,
            "appliance_type": appliance_type,
        }

    async def get_part_details(self, part_number: str) -> dict:
        part = await self._structured_store.get_part_details(part_number)
        if part is None:
            return {"error": f"Part {part_number} not found.", "part_number": part_number}
        return part

    async def check_compatibility(self, part_number: str, model_number: str) -> dict:
        return await self._structured_store.check_compatibility(
            part_number=part_number, model_number=model_number
        )

    async def get_installation_guide(self, part_number: str) -> dict:
        """
        Structured-first installation behavior:
        - If indexed steps exist, return them.
        - If missing, semantic retrieval may backfill long-form help and deterministically extract steps.
        """
        structured = await self._structured_store.get_installation_steps(part_number)
        if structured.get("error"):
            return structured

        steps = structured.get("steps") or []
        if steps:
            return structured

        # Semantic backfill (Phase 0: likely empty unless help_chunks are populated).
        hits = await self._help_vector_index.search_help(
            query=f"installation {part_number}",
            appliance_type=None,
            help_type="installation_help",
            k=3,
        )
        backfilled_steps = []
        for h in hits:
            txt = h.get("chunk_text") or ""
            # Deterministically extract bullet-like lines as steps.
            for line in txt.splitlines():
                line = line.strip()
                if not line:
                    continue
                # Common step markers: "1.", "-", "*", "Step"
                if re.match(r"^(\d+\.|\-|\*|step\s+\d+)", line, flags=re.IGNORECASE):
                    backfilled_steps.append(line)
                # Fallback: keep short imperative-ish sentences.
                elif len(line) <= 160 and any(w in line.lower() for w in ["turn", "remove", "install", "disconnect", "connect", "replace"]):
                    backfilled_steps.append(line)
                if len(backfilled_steps) >= 8:
                    break
            if len(backfilled_steps) >= 8:
                break

        structured["steps"] = backfilled_steps
        # Prefer PartSelect part source_url if present; otherwise use semantic sources.
        if not structured.get("source_url"):
            structured["source_url"] = hits[0].get("source_url") if hits else ""
        return structured

    async def diagnose_troubleshooting(
        self,
        appliance_type: str,
        symptom: str,
        model_number: str = "",
    ) -> dict:
        """
        Troubleshooting behavior:
        - Structured-first using `troubleshooting_causes`.
        - Semantic backfill may add likely causes or recommended parts when structured data is missing.
        - Service-level canonical output: likely_causes, recommended_parts, source_urls.
        """
        structured = await self._structured_store.get_troubleshooting_causes(
            appliance_type=appliance_type, symptom=symptom
        )
        likely_causes = structured.get("likely_causes") or []
        recommended_parts = structured.get("recommended_parts") or []
        source_urls = structured.get("source_urls") or []
        matched_symptom = structured.get("matched_symptom") or normalize_symptom_key(symptom)

        if likely_causes:
            return structured

        # Semantic backfill.
        symptom_key = normalize_symptom_key(symptom)
        hits = await self._help_vector_index.search_help(
            query=symptom_key,
            appliance_type=appliance_type,
            symptom_key=symptom_key,
            help_type="troubleshooting",
            k=5,
        )
        semantic_text = "\n".join([h.get("chunk_text") or "" for h in hits]).strip()

        # Deterministic normalization:
        # - likely causes: heuristic extraction of lines.
        # - recommended parts: extract PS numbers and de-duplicate.
        likely_causes_backfill: list[dict] = []
        for line in semantic_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if len(likely_causes_backfill) >= 6:
                break
            if re.match(r"^(\-|\*|•)", line) or len(line) < 140:
                likely_causes_backfill.append(
                    {
                        "cause": line.lstrip("-*• ").strip(),
                        "part_type": None,
                        "likelihood": "low",
                    }
                )

        part_numbers = sorted(
            {m.group(0).upper() for m in re.finditer(r"\bPS\d{6,10}\b", semantic_text)}
        )

        source_urls_backfill = [h.get("source_url") for h in hits if h.get("source_url")]

        return {
            "causes": likely_causes_backfill,
            "likely_causes": likely_causes_backfill,
            "recommended_parts": part_numbers,
            "source_urls": source_urls_backfill,
            "matched_symptom": matched_symptom,
        }

