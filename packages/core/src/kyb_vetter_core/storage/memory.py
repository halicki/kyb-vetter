"""Process-local storage. State is lost on restart and not shared between processes.

Used for local stdio runs without a database; the hosted service must use
:mod:`kyb_vetter_core.storage.postgres` because the MF quota is per IP, not
per process.
"""

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime

    from kyb_vetter_core.storage.ports import AuditEvent, CacheEntry


class MemoryQuotaStore:
    def __init__(self) -> None:
        self._counts: dict[tuple[str, date], int] = {}
        self._lock = asyncio.Lock()

    async def try_reserve(self, bucket: str, day: date, *, limit: int) -> int | None:
        async with self._lock:
            current = self._counts.get((bucket, day), 0)
            if current >= limit:
                return None
            self._counts[(bucket, day)] = current + 1
            return current + 1

    async def exhaust(self, bucket: str, day: date, *, limit: int) -> None:
        async with self._lock:
            self._counts[(bucket, day)] = max(limit, self._counts.get((bucket, day), 0))

    async def usage(self, bucket: str, day: date) -> int:
        return self._counts.get((bucket, day), 0)


class MemoryAuditStore:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self._events.append(event)

    async def history(self, nip: str, *, principal: str, limit: int) -> list[AuditEvent]:
        matching = [e for e in self._events if e.nip == nip and e.principal == principal]
        matching.sort(key=lambda e: e.ts, reverse=True)
        return matching[:limit]


class MemoryCacheStore:
    def __init__(self) -> None:
        self._entries: dict[tuple[str, str, date], CacheEntry] = {}

    async def get(
        self, source: str, cache_key: str, queried_date: date, *, now: datetime
    ) -> CacheEntry | None:
        entry = self._entries.get((source, cache_key, queried_date))
        if entry is None or entry.expires_at <= now:
            return None
        return entry

    async def put(self, entry: CacheEntry) -> None:
        self._entries[(entry.source, entry.cache_key, entry.queried_date)] = entry
