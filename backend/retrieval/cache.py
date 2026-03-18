"""SQLite-backed cache with TTL expiry."""
import json
import time
from typing import Any, Callable, Optional

import aiosqlite


class CacheLayer:
    def __init__(self, db_path: str = "cache.db"):
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Create the cache table if it doesn't exist."""
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    async def get(self, key: str) -> Optional[dict]:
        """Get a cached value. Returns None if missing or expired."""
        assert self._db is not None, "Call initialize() first"
        cursor = await self._db.execute(
            "SELECT data, expires_at FROM cache WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        data, expires_at = row
        if time.time() > expires_at:
            await self._db.execute("DELETE FROM cache WHERE key = ?", (key,))
            await self._db.commit()
            return None
        return json.loads(data)

    async def set(self, key: str, data: dict, ttl_hours: int = 24) -> None:
        """Store a value with TTL."""
        assert self._db is not None, "Call initialize() first"
        expires_at = time.time() + (ttl_hours * 3600)
        await self._db.execute(
            """
            INSERT INTO cache (key, data, expires_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET data = excluded.data, expires_at = excluded.expires_at
            """,
            (key, json.dumps(data), expires_at),
        )
        await self._db.commit()

    async def get_or_fetch(
        self, key: str, fetcher: Callable, ttl_hours: int = 24
    ) -> dict:
        """Return cached value or call fetcher, cache the result, and return it."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        result = await fetcher()
        await self.set(key, result, ttl_hours)
        return result
