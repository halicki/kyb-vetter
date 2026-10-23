"""Process-local storage. State is lost on restart and not shared between processes.

Used for local stdio runs without a database; the hosted service must use
:mod:`kyb_vetter_core.storage.postgres` because the MF quota is per IP, not
per process.
"""

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date, datetime
    from uuid import UUID

    from kyb_vetter_core.storage.ports import ApiKeyRecord, AuditEvent, CacheEntry


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


class MemoryApiKeyStore:
    def __init__(self) -> None:
        self._keys: dict[UUID, ApiKeyRecord] = {}

    async def insert(self, record: ApiKeyRecord) -> None:
        self._keys[record.id] = record

    async def find_by_prefix(self, prefix: str) -> ApiKeyRecord | None:
        return next((k for k in self._keys.values() if k.prefix == prefix), None)

    async def touch(self, key_id: UUID, *, used_at: datetime) -> None:
        self._keys[key_id] = self._keys[key_id].model_copy(update={"last_used_at": used_at})

    async def revoke(self, key_id: UUID, *, revoked_at: datetime) -> None:
        self._keys[key_id] = self._keys[key_id].model_copy(update={"revoked_at": revoked_at})

    async def list_for(self, principal: str) -> list[ApiKeyRecord]:
        mine = [k for k in self._keys.values() if k.principal == principal]
        mine.sort(key=lambda k: k.created_at)
        return mine
