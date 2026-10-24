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


class ApiKeyRecord(BaseModel):
    """An API key as stored: identity, owner, lookup prefix and the hash of the full key."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    principal: str
    name: str
    prefix: str
    key_hash: str
    created_at: datetime
    revoked_at: datetime | None
    last_used_at: datetime | None


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

    async def purge_before(self, day: date) -> int:
        """Drop counters for days before ``day``; returns how many rows went."""
        ...


class AuditStore(Protocol):
    async def record(self, event: AuditEvent) -> None: ...

    async def history(self, nip: str, *, principal: str, limit: int) -> list[AuditEvent]:
        """Events for ``nip`` recorded for ``principal``, newest first. Never cross-user."""
        ...

    async def purge_before(self, cutoff: datetime) -> int:
        """Drop events with ``ts`` before ``cutoff`` (retention, ADR-0022); returns the count."""
        ...


class BlobStore(Protocol):
    """Named binary objects (flat-file indexes). Keys use ``/`` separators."""

    async def get(self, name: str) -> bytes | None: ...

    async def put(self, name: str, data: bytes) -> None: ...

    async def exists(self, name: str) -> bool: ...


class CacheStore(Protocol):
    async def get(
        self, source: str, cache_key: str, queried_date: date, *, now: datetime
    ) -> CacheEntry | None:
        """The entry if present and not expired at ``now``."""
        ...

    async def put(self, entry: CacheEntry) -> None:
        """Insert or replace."""
        ...

    async def purge_expired(self, now: datetime) -> int:
        """Physically remove entries expired at ``now``; returns the count."""
        ...


class ApiKeyStore(Protocol):
    async def insert(self, record: ApiKeyRecord) -> None: ...

    async def find_by_prefix(self, prefix: str) -> ApiKeyRecord | None: ...

    async def touch(self, key_id: UUID, *, used_at: datetime) -> None:
        """Record a successful use."""
        ...

    async def revoke(self, key_id: UUID, *, revoked_at: datetime) -> None: ...

    async def list_for(self, principal: str) -> list[ApiKeyRecord]:
        """All keys of ``principal`` (revoked ones included), oldest first."""
        ...


@dataclass(frozen=True)
class Stores:
    quota: QuotaStore
    audit: AuditStore
    cache: CacheStore
    blobs: BlobStore
    apikeys: ApiKeyStore
    persistent: bool
    """False when state lives in this process only (quota is then NOT shared across instances)."""
