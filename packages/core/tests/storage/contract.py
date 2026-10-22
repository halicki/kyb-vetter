"""Behavioural contract every storage implementation must satisfy (memory and Postgres)."""

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from kyb_vetter_core.storage.ports import AuditEvent, AuditStore, CacheEntry, CacheStore, QuotaStore

DAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def make_event(
    nip: str = "1234563218", ts: datetime = NOW, tool: str = "verify_company"
) -> AuditEvent:
    return AuditEvent(
        id=uuid4(),
        ts=ts,
        principal="local",
        tool=tool,
        nip=nip,
        input={"nip": nip},
        outcome="ok",
        error_code=None,
        request_ids=("d2n10-84df1a1",),
        sources=("mf-whitelist",),
        response_sha256="ab" * 32,
        result={"found": True},
        from_cache=False,
    )


async def quota_contract(store: QuotaStore) -> None:
    assert await store.usage("wl_search", DAY) == 0
    assert await store.try_reserve("wl_search", DAY, limit=2) == 1
    assert await store.try_reserve("wl_search", DAY, limit=2) == 2
    assert (
        await store.try_reserve("wl_search", DAY, limit=2) is None
    )  # at limit: refused, not counted
    assert await store.usage("wl_search", DAY) == 2
    # buckets and days are independent
    assert await store.try_reserve("wl_check", DAY, limit=2) == 1
    assert await store.try_reserve("wl_search", DAY + timedelta(days=1), limit=2) == 1
    # exhaust pins the counter at the limit
    await store.exhaust("wl_status", DAY, limit=5)
    assert await store.usage("wl_status", DAY) == 5
    assert await store.try_reserve("wl_status", DAY, limit=5) is None


async def audit_contract(store: AuditStore) -> None:
    older = make_event(ts=NOW - timedelta(hours=1))
    newer = make_event(ts=NOW, tool="check_bank_account")
    other = make_event(nip="7740001454")
    for event in (older, newer, other):
        await store.record(event)

    history = await store.history("1234563218", limit=10)
    assert [e.id for e in history] == [newer.id, older.id]  # newest first
    assert history[0].tool == "check_bank_account"
    assert history[0].result == {"found": True}
    assert history[0].ts == NOW
    assert await store.history("1234563218", limit=1) == [newer]
    assert await store.history("0000000000", limit=10) == []


async def cache_contract(store: CacheStore) -> None:
    entry = CacheEntry(
        source="mf-whitelist",
        cache_key="1234563218",
        queried_date=DAY,
        payload={"subject": None},
        fetched_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    assert await store.get("mf-whitelist", "1234563218", DAY, now=NOW) is None
    await store.put(entry)
    assert await store.get("mf-whitelist", "1234563218", DAY, now=NOW) == entry
    assert await store.get("mf-whitelist", "1234563218", DAY + timedelta(days=1), now=NOW) is None
    assert await store.get("krs", "1234563218", DAY, now=NOW) is None
    assert (
        await store.get("mf-whitelist", "1234563218", DAY, now=NOW + timedelta(hours=2)) is None
    )  # expired
    # put replaces an existing entry
    fresh = entry.model_copy(
        update={"payload": {"subject": {"name": "X"}}, "expires_at": NOW + timedelta(hours=3)}
    )
    await store.put(fresh)
    got = await store.get("mf-whitelist", "1234563218", DAY, now=NOW + timedelta(hours=2))
    assert got is not None
    assert got.payload == {"subject": {"name": "X"}}
