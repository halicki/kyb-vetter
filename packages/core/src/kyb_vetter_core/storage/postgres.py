"""Postgres implementations of the storage ports (SQLAlchemy 2.1 async + asyncpg).

Schema is owned by Alembic (``packages/core/alembic``); the ORM classes here
mirror it for queries and for ``--autogenerate``.
"""

from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Any
lazy import uuid
lazy from collections.abc import AsyncGenerator

from sqlalchemy import DateTime, Index, delete, func, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kyb_vetter_core.storage.ports import ApiKeyRecord, AuditEvent, BlobStore, CacheEntry, Stores


class Base(DeclarativeBase):
    pass


class QuotaCounterRow(Base):
    __tablename__ = "quota_counters"

    bucket: Mapped[str] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(nullable=False, default=0)


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_nip_ts", "nip", "ts"),
        Index("ix_audit_events_principal_nip_ts", "principal", "nip", "ts"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    principal: Mapped[str] = mapped_column(nullable=False)
    tool: Mapped[str] = mapped_column(nullable=False)
    nip: Mapped[str | None]
    input: Mapped[dict[str, Any]] = mapped_column(JSONB(), nullable=False)
    outcome: Mapped[str] = mapped_column(nullable=False)
    error_code: Mapped[str | None]
    request_ids: Mapped[list[str]] = mapped_column(JSONB(), nullable=False)
    sources: Mapped[list[str]] = mapped_column(JSONB(), nullable=False)
    response_sha256: Mapped[str | None]
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB(), nullable=True)
    from_cache: Mapped[bool] = mapped_column(nullable=False, default=False)


class CacheRow(Base):
    __tablename__ = "registry_cache"

    source: Mapped[str] = mapped_column(primary_key=True)
    cache_key: Mapped[str] = mapped_column(primary_key=True)
    queried_date: Mapped[date] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB(), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ApiKeyRow(Base):
    __tablename__ = "api_keys"
    __table_args__ = (Index("ix_api_keys_principal", "principal"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    principal: Mapped[str] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    prefix: Mapped[str] = mapped_column(nullable=False, unique=True)
    key_hash: Mapped[str] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


type SessionFactory = async_sessionmaker[Any]


class PostgresQuotaStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def try_reserve(self, bucket: str, day: date, *, limit: int) -> int | None:
        stmt = insert(QuotaCounterRow).values(bucket=bucket, day=day, count=1)
        stmt = stmt.on_conflict_do_update(
            index_elements=[QuotaCounterRow.bucket, QuotaCounterRow.day],
            set_={"count": QuotaCounterRow.count + 1},
            where=QuotaCounterRow.count < limit,
        ).returning(QuotaCounterRow.count)
        async with self._sessions.begin() as session:
            count = (await session.execute(stmt)).scalar_one_or_none()
        return None if count is None else int(count)

    async def exhaust(self, bucket: str, day: date, *, limit: int) -> None:
        stmt = insert(QuotaCounterRow).values(bucket=bucket, day=day, count=limit)
        stmt = stmt.on_conflict_do_update(
            index_elements=[QuotaCounterRow.bucket, QuotaCounterRow.day],
            set_={"count": func.greatest(QuotaCounterRow.count, limit)},
        )
        async with self._sessions.begin() as session:
            await session.execute(stmt)

    async def usage(self, bucket: str, day: date) -> int:
        async with self._sessions() as session:
            count = await session.scalar(
                select(QuotaCounterRow.count).where(
                    QuotaCounterRow.bucket == bucket, QuotaCounterRow.day == day
                )
            )
        return 0 if count is None else int(count)

    async def purge_before(self, day: date) -> int:
        async with self._sessions.begin() as session:
            result = await session.execute(delete(QuotaCounterRow).where(QuotaCounterRow.day < day))
        return int(result.rowcount)


class PostgresAuditStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def record(self, event: AuditEvent) -> None:
        row = AuditEventRow(
            id=event.id,
            ts=event.ts,
            principal=event.principal,
            tool=event.tool,
            nip=event.nip,
            input=event.input,
            outcome=event.outcome,
            error_code=event.error_code,
            request_ids=list(event.request_ids),
            sources=list(event.sources),
            response_sha256=event.response_sha256,
            result=event.result,
            from_cache=event.from_cache,
        )
        async with self._sessions.begin() as session:
            session.add(row)

    async def history(self, nip: str, *, principal: str, limit: int) -> list[AuditEvent]:
        stmt = (
            select(AuditEventRow)
            .where(AuditEventRow.nip == nip, AuditEventRow.principal == principal)
            .order_by(AuditEventRow.ts.desc())
            .limit(limit)
        )
        async with self._sessions() as session:
            rows = (await session.scalars(stmt)).all()
        return [
            AuditEvent(
                id=r.id,
                ts=r.ts,
                principal=r.principal,
                tool=r.tool,
                nip=r.nip,
                input=r.input,
                outcome="ok" if r.outcome == "ok" else "error",
                error_code=r.error_code,
                request_ids=tuple(r.request_ids),
                sources=tuple(r.sources),
                response_sha256=r.response_sha256,
                result=r.result,
                from_cache=r.from_cache,
            )
            for r in rows
        ]

    async def purge_before(self, cutoff: datetime) -> int:
        async with self._sessions.begin() as session:
            result = await session.execute(delete(AuditEventRow).where(AuditEventRow.ts < cutoff))
        return int(result.rowcount)


class PostgresCacheStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    async def get(
        self, source: str, cache_key: str, queried_date: date, *, now: datetime
    ) -> CacheEntry | None:
        stmt = select(CacheRow).where(
            CacheRow.source == source,
            CacheRow.cache_key == cache_key,
            CacheRow.queried_date == queried_date,
            CacheRow.expires_at > now,
        )
        async with self._sessions() as session:
            row = await session.scalar(stmt)
        if row is None:
            return None
        return CacheEntry(
            source=row.source,
            cache_key=row.cache_key,
            queried_date=row.queried_date,
            payload=row.payload,
            fetched_at=row.fetched_at,
            expires_at=row.expires_at,
        )

    async def put(self, entry: CacheEntry) -> None:
        stmt = insert(CacheRow).values(
            source=entry.source,
            cache_key=entry.cache_key,
            queried_date=entry.queried_date,
            payload=entry.payload,
            fetched_at=entry.fetched_at,
            expires_at=entry.expires_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[CacheRow.source, CacheRow.cache_key, CacheRow.queried_date],
            set_={
                "payload": stmt.excluded.payload,
                "fetched_at": stmt.excluded.fetched_at,
                "expires_at": stmt.excluded.expires_at,
            },
        )
        async with self._sessions.begin() as session:
            await session.execute(stmt)

    async def purge_expired(self, now: datetime) -> int:
        async with self._sessions.begin() as session:
            result = await session.execute(delete(CacheRow).where(CacheRow.expires_at <= now))
        return int(result.rowcount)


class PostgresApiKeyStore:
    def __init__(self, sessions: SessionFactory) -> None:
        self._sessions = sessions

    @staticmethod
    def _record(row: ApiKeyRow) -> ApiKeyRecord:
        return ApiKeyRecord(
            id=row.id,
            principal=row.principal,
            name=row.name,
            prefix=row.prefix,
            key_hash=row.key_hash,
            created_at=row.created_at,
            revoked_at=row.revoked_at,
            last_used_at=row.last_used_at,
        )

    async def insert(self, record: ApiKeyRecord) -> None:
        async with self._sessions.begin() as session:
            session.add(ApiKeyRow(**record.model_dump()))

    async def find_by_prefix(self, prefix: str) -> ApiKeyRecord | None:
        async with self._sessions() as session:
            row = await session.scalar(select(ApiKeyRow).where(ApiKeyRow.prefix == prefix))
        return None if row is None else self._record(row)

    async def touch(self, key_id: uuid.UUID, *, used_at: datetime) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ApiKeyRow).where(ApiKeyRow.id == key_id).values(last_used_at=used_at)
            )

    async def revoke(self, key_id: uuid.UUID, *, revoked_at: datetime) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(ApiKeyRow).where(ApiKeyRow.id == key_id).values(revoked_at=revoked_at)
            )

    async def list_for(self, principal: str) -> list[ApiKeyRecord]:
        stmt = (
            select(ApiKeyRow)
            .where(ApiKeyRow.principal == principal)
            .order_by(ApiKeyRow.created_at.asc())
        )
        async with self._sessions() as session:
            rows = (await session.scalars(stmt)).all()
        return [self._record(r) for r in rows]


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


@asynccontextmanager
async def open_postgres_stores(url: str, *, blobs: BlobStore) -> AsyncGenerator[Stores]:

    engine = make_engine(url)
    sessions: SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield Stores(
            quota=PostgresQuotaStore(sessions),
            audit=PostgresAuditStore(sessions),
            cache=PostgresCacheStore(sessions),
            blobs=blobs,
            apikeys=PostgresApiKeyStore(sessions),
            persistent=True,
        )
    finally:
        await engine.dispose()
