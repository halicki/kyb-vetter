"""Storage ports (protocols) and the records they persist.

The verification service depends only on these protocols. Two
implementations exist: :mod:`memory` (process-local, used when no database
is configured) and :mod:`postgres` (ADR-0013).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditEvent(BaseModel):
    """One tool invocation, successful or not."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    ts: datetime
    principal: str
    tool: str
    nip: str | None
    input: dict[str, Any]
    outcome: Literal["ok", "error"]
    error_code: str | None
    request_ids: tuple[str, ...]
    sources: tuple[str, ...]
    response_sha256: str | None
    result: dict[str, Any] | None
    from_cache: bool


class CacheEntry(BaseModel):
    """A cached registry response keyed by source, identifier and the day it describes."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str
    cache_key: str
    queried_date: date
    payload: dict[str, Any]
    fetched_at: datetime
    expires_at: datetime


class QuotaStore(Protocol):
    """Daily counters shared by every process behind one public IP."""

    async def try_reserve(self, bucket: str, day: date, *, limit: int) -> int | None:
        """Atomically increment the counter unless it already reached ``limit``.

        Returns the new count, or ``None`` when refused (the counter is left untouched).
        """
        ...

    async def exhaust(self, bucket: str, day: date, *, limit: int) -> None:
        """Pin the counter at ``limit`` (the registry told us the IP is blocked)."""
        ...

    async def usage(self, bucket: str, day: date) -> int: ...


class AuditStore(Protocol):
    async def record(self, event: AuditEvent) -> None: ...

    async def history(self, nip: str, *, limit: int) -> list[AuditEvent]:
        """Events for ``nip``, newest first."""
        ...


class CacheStore(Protocol):
    async def get(
        self, source: str, cache_key: str, queried_date: date, *, now: datetime
    ) -> CacheEntry | None:
        """The entry if present and not expired at ``now``."""
        ...

    async def put(self, entry: CacheEntry) -> None:
        """Insert or replace."""
        ...


@dataclass(frozen=True)
class Stores:
    quota: QuotaStore
    audit: AuditStore
    cache: CacheStore
    persistent: bool
    """False when state lives in this process only (quota is then NOT shared across instances)."""
