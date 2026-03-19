"""
HelpVectorIndex: semantic retrieval over long-form help chunks.

Uses FAISS with OpenAI text-embedding-3-small for vector search.
Falls back to SQLite FTS5 when FAISS index is not built or faiss-cpu
is not installed.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
from pathlib import Path
from typing import Any, Optional

import aiosqlite
import numpy as np

from config import INDEX_DB_PATH, HELP_VECTOR_INDEX_PATH, OPENAI_API_KEY

logger = logging.getLogger(__name__)

EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536
EMBED_BATCH_SIZE = 100


def _embed_sync(texts: list[str]) -> np.ndarray:
    """Embed a list of texts using OpenAI API. Returns (n, EMBED_DIM) float32 array."""
    from openai import OpenAI

    client = OpenAI(api_key=OPENAI_API_KEY)
    all_embeddings: list[list[float]] = []

    for i in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[i : i + EMBED_BATCH_SIZE]
        resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
        for item in resp.data:
            all_embeddings.append(item.embedding)

    arr = np.array(all_embeddings, dtype=np.float32)
    # L2-normalize so inner product = cosine similarity
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    arr = arr / norms
    return arr


class HelpVectorIndex:
    def __init__(
        self,
        structured_db_path: str = INDEX_DB_PATH,
        faiss_path: str = HELP_VECTOR_INDEX_PATH,
    ):
        self._structured_db_path = structured_db_path
        self._faiss_path = faiss_path
        self._db: Optional[aiosqlite.Connection] = None

        self._faiss_index = None
        self._metadata: list[dict] = []  # parallel to FAISS index rows

        self._faiss_available = False
        try:
            import faiss  # noqa: F401
            self._faiss_available = True
        except Exception:
            self._faiss_available = False

    async def initialize(self) -> None:
        """Open DB connection and load FAISS index from disk if available."""
        self._db = await aiosqlite.connect(self._structured_db_path)
        self._db.row_factory = aiosqlite.Row
        self._load_index()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    # ── Index persistence ────────────────────────────────────────────────────

    def _index_dir(self) -> Path:
        return Path(self._faiss_path)

    def _load_index(self) -> None:
        """Load FAISS index + metadata from disk. Silent no-op if missing."""
        if not self._faiss_available:
            return
        import faiss

        idx_path = self._index_dir() / "index.faiss"
        meta_path = self._index_dir() / "metadata.pkl"
        if not idx_path.exists() or not meta_path.exists():
            logger.debug("No FAISS index found at %s — using FTS fallback", self._faiss_path)
            return

        self._faiss_index = faiss.read_index(str(idx_path))
        with open(meta_path, "rb") as f:
            self._metadata = pickle.load(f)
        logger.info(
            "Loaded FAISS index: %d vectors from %s",
            self._faiss_index.ntotal,
            idx_path,
        )

    def _save_index(self) -> None:
        """Persist FAISS index + metadata to disk."""
        import faiss

        d = self._index_dir()
        d.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._faiss_index, str(d / "index.faiss"))
        with open(d / "metadata.pkl", "wb") as f:
            pickle.dump(self._metadata, f)
        logger.info("Saved FAISS index: %d vectors to %s", self._faiss_index.ntotal, d)

    # ── Index building ───────────────────────────────────────────────────────

    async def build_index(self) -> int:
        """Read all help_chunks from SQLite, embed, and build FAISS index.

        Returns the number of vectors indexed.
        """
        if not self._faiss_available:
            logger.warning("faiss-cpu not installed — skipping index build")
            return 0
        import faiss

        db = await aiosqlite.connect(self._structured_db_path)
        db.row_factory = aiosqlite.Row
        try:
            cur = await db.execute(
                "SELECT chunk_id, source_url, appliance_type, help_type, symptom_key, chunk_text FROM help_chunks"
            )
            rows = await cur.fetchall()
            await cur.close()
        finally:
            await db.close()

        if not rows:
            logger.warning("No help_chunks found — skipping FAISS index build")
            return 0

        texts = [r["chunk_text"] or "" for r in rows]
        metadata = [
            {
                "chunk_id": r["chunk_id"],
                "source_url": r["source_url"] or "",
                "appliance_type": r["appliance_type"],
                "help_type": r["help_type"],
                "symptom_key": r["symptom_key"],
                "chunk_text": r["chunk_text"],
            }
            for r in rows
        ]

        logger.info("Embedding %d help chunks...", len(texts))
        embeddings = _embed_sync(texts)

        index = faiss.IndexFlatIP(EMBED_DIM)
        index.add(embeddings)

        self._faiss_index = index
        self._metadata = metadata
        self._save_index()
        return len(texts)

    # ── Search ───────────────────────────────────────────────────────────────

    async def search_help(
        self,
        query: str,
        appliance_type: str | None = None,
        symptom_key: str | None = None,
        help_type: str | None = None,
        k: int = 5,
    ) -> list[dict]:
        """Semantic search over help chunks. Falls back to FTS5 if no FAISS index."""
        q = (query or "").strip()
        if not q:
            return []

        # Try FAISS first
        if self._faiss_index is not None and self._faiss_index.ntotal > 0:
            return self._search_faiss(q, appliance_type, symptom_key, help_type, k)

        # FTS fallback
        return await self._search_fts(q, appliance_type, symptom_key, help_type, k)

    def _search_faiss(
        self,
        query: str,
        appliance_type: str | None,
        symptom_key: str | None,
        help_type: str | None,
        k: int,
    ) -> list[dict]:
        query_vec = _embed_sync([query])
        total = self._faiss_index.ntotal
        has_filters = bool(appliance_type or symptom_key or help_type)

        # Adaptive over-fetch: start conservatively, widen if filters are selective.
        # Without filters we only need exactly k; with filters start at max(k*2, 20)
        # and double up to the full index if too few results pass the filter.
        if not has_filters:
            fetch_k = min(k, total)
        else:
            fetch_k = min(max(k * 2, 20), total)

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            scores, indices = self._faiss_index.search(query_vec, fetch_k)

            hits: list[dict] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0:
                    continue
                meta = self._metadata[idx]
                if appliance_type and meta.get("appliance_type") != appliance_type:
                    continue
                if symptom_key and meta.get("symptom_key") != symptom_key:
                    continue
                if help_type and meta.get("help_type") != help_type:
                    continue
                hits.append({**meta, "score": float(score)})
                if len(hits) >= k:
                    return hits

            # Got enough or already fetched everything — stop retrying
            if len(hits) >= k or fetch_k >= total:
                return hits

            # Widen the search for next attempt
            fetch_k = min(fetch_k * 2, total)

        return hits

    async def _search_fts(
        self,
        query: str,
        appliance_type: str | None,
        symptom_key: str | None,
        help_type: str | None,
        k: int,
    ) -> list[dict]:
        """FTS5 keyword fallback."""
        assert self._db is not None, "Call initialize() first"

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

        sql = f"""
        SELECT hc.chunk_id, hc.source_url, hc.appliance_type, hc.help_type, hc.symptom_key, hc.chunk_text
        FROM help_chunks hc
        JOIN help_chunks_fts fts ON fts.chunk_id = hc.chunk_id
        WHERE fts MATCH ?
        {where_filters}
        LIMIT ?
        """
        try:
            cur = await self._db.execute(sql, (query, *params, k))
            rows = await cur.fetchall()
            await cur.close()
        except Exception:
            return []

        return [
            {
                "chunk_id": r["chunk_id"],
                "source_url": r["source_url"] or "",
                "appliance_type": r["appliance_type"],
                "help_type": r["help_type"],
                "symptom_key": r["symptom_key"],
                "chunk_text": r["chunk_text"],
            }
            for r in rows
        ]
