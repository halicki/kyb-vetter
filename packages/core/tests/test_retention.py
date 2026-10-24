"""Audit retention and housekeeping (ADR-0022): 5 years from the end of the event's year."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from kyb_vetter_core.retention import (
    AUDIT_RETENTION_YEARS,
    QUOTA_COUNTER_RETENTION_DAYS,
    audit_cutoff,
    purge,
)
from kyb_vetter_core.storage.blobs import MemoryBlobStore
from kyb_vetter_core.storage.memory import (
    MemoryApiKeyStore,
    MemoryAuditStore,
    MemoryCacheStore,
    MemoryQuotaStore,
)
from kyb_vetter_core.storage.ports import AuditEvent, CacheEntry, Stores

NOW = datetime(2026, 10, 24, 3, 30, tzinfo=UTC)


def test_constants_match_the_decision() -> None:
    assert AUDIT_RETENTION_YEARS == 5
    assert QUOTA_COUNTER_RETENTION_DAYS == 7


def test_audit_cutoff_is_january_first_five_years_back() -> None:
    assert audit_cutoff(NOW) == datetime(2021, 1, 1, tzinfo=UTC)
    assert audit_cutoff(datetime(2031, 12, 31, 23, 59, tzinfo=UTC)) == datetime(
        2026, 1, 1, tzinfo=UTC
    )


def _event(ts: datetime) -> AuditEvent:
    return AuditEvent(
        id=uuid4(),
        ts=ts,
        principal="p",
        tool="verify_company",
        nip="1234563218",
        input={},
        outcome="ok",
        error_code=None,
        request_ids=(),
        sources=(),
        response_sha256=None,
        result=None,
        from_cache=False,
    )


def _stores() -> Stores:
    return Stores(
        quota=MemoryQuotaStore(),
        audit=MemoryAuditStore(),
        cache=MemoryCacheStore(),
        blobs=MemoryBlobStore(),
        apikeys=MemoryApiKeyStore(),
        persistent=False,
    )


async def test_purge_removes_expired_audit_rows_old_counters_and_stale_cache() -> None:
    stores = _stores()
    await stores.audit.record(_event(datetime(2020, 12, 31, 23, 59, tzinfo=UTC)))  # 2020: gone
    await stores.audit.record(_event(datetime(2021, 1, 1, tzinfo=UTC)))  # 2021: kept until 2027
    await stores.quota.try_reserve("wl_search", date(2026, 10, 1), limit=10)
    await stores.quota.try_reserve("user:p:verify_company", date(2026, 10, 20), limit=10)
    await stores.cache.put(
        CacheEntry(
            source="s",
            cache_key="old",
            queried_date=date(2026, 10, 1),
            payload={},
            fetched_at=NOW - timedelta(days=20),
            expires_at=NOW - timedelta(days=19),
        )
    )
    await stores.cache.put(
        CacheEntry(
            source="s",
            cache_key="fresh",
            queried_date=date(2026, 10, 24),
            payload={},
            fetched_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        )
    )

    report = await purge(stores, now=NOW)

    assert (report.audit_events, report.quota_counters, report.cache_entries) == (1, 1, 1)
    assert len(await stores.audit.history("1234563218", principal="p", limit=10)) == 1
    assert await stores.quota.usage("wl_search", date(2026, 10, 1)) == 0
    assert await stores.quota.usage("user:p:verify_company", date(2026, 10, 20)) == 1
    assert (
        await stores.cache.get("s", "old", date(2026, 10, 1), now=NOW - timedelta(days=30)) is None
    )
    assert await stores.cache.get("s", "fresh", date(2026, 10, 24), now=NOW) is not None
    assert "audit_events=1" in str(report)
