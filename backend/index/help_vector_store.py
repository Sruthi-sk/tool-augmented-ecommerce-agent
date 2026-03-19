"""
HelpVectorIndex: semantic retrieval over long-form help chunks.

Phase 0 goal:
- Provide a stable interface and safe fallback behavior when FAISS/embeddings
  are not yet configured.

Later phases will implement:
- embedding generation
- FAISS index persistence/loading
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import aiosqlite

from config import INDEX_DB_PATH, HELP_VECTOR_INDEX_PATH


@dataclass(frozen=True)
class HelpHit:
    chunk_id: str
    source_url: str
    appliance_type: str | None
    help_type: str | None
    symptom_key: str | None
    chunk_text: str | None


class HelpVectorIndex:
    def __init__(
        self,
        structured_db_path: str = INDEX_DB_PATH,
        # FAISS persistence dir; may be unused in Phase 0.
        faiss_path: str = HELP_VECTOR_INDEX_PATH,
    ):
        self._structured_db_path = structured_db_path
        self._faiss_path = faiss_path
        self._db: Optional[aiosqlite.Connection] = None

        self._faiss_available = False
        try:
            import faiss  # noqa: F401

            self._faiss_available = True
        except Exception:
            self._faiss_available = False

    async def initialize(self) -> None:
        # Phase 0: we at least connect so we can do lexical fallback retrieval from help_chunks_fts.
        self._db = await aiosqlite.connect(self._structured_db_path)
        self._db.row_factory = aiosqlite.Row

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def search_help(
        self,
        query: str,
        appliance_type: str | None = None,
        symptom_key: str | None = None,
        help_type: str | None = None,
        k: int = 5,
    ) -> list[dict]:
        """
        Return help chunks as structured hits.

        Phase 0 behavior:
        - Use SQLite FTS over `help_chunks_fts` as a keyword-based fallback.
        - Return [] if help text isn't present or indexing isn't built.
        """
        assert self._db is not None, "Call initialize() first"
        q = (query or "").strip()
        if not q:
            return []

        # FTS query. We also apply optional filters.
        filters = []
        params: list[Any] = []
        if appliance_type:
            filters.append("hc.appliance_type = ?")
            params.append(appliance_type)
        if help_type:
            filters.append("hc.help_type = ?")
            params.append(help_type)
        if symptom_key:
            filters.append("hc.symptom_key = ?")
            params.append(symptom_key)

        where_filters = ""
        if filters:
            where_filters = " AND " + " AND ".join(filters)

        # Note: `help_chunks_fts` includes chunk_id and chunk_text.
        query = f"""
        SELECT hc.chunk_id, hc.source_url, hc.appliance_type, hc.help_type, hc.symptom_key, hc.chunk_text
        FROM help_chunks hc
        JOIN help_chunks_fts fts ON fts.chunk_id = hc.chunk_id
        WHERE fts MATCH ?
        {where_filters}
        LIMIT ?
        """
        cur = await self._db.execute(query, (q, *params, k))
        rows = await cur.fetchall()
        await cur.close()

        hits: list[dict] = []
        for r in rows:
            hits.append(
                {
                    "chunk_id": r["chunk_id"],
                    "source_url": r["source_url"] or "",
                    "appliance_type": r["appliance_type"],
                    "help_type": r["help_type"],
                    "symptom_key": r["symptom_key"],
                    "chunk_text": r["chunk_text"],
                }
            )
        return hits

