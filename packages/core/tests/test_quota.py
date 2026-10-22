from collections.abc import AsyncIterator, Callable, Iterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from kyb_vetter_core.clients import whitelist as whitelist_module
from kyb_vetter_core.clients.whitelist import WhiteListClient
from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import DailyLimitExceededError, QuotaExhaustedError
from kyb_vetter_core.quota import (
    BUCKET_CHECK,
    BUCKET_SEARCH,
    BUCKET_STATUS,
    DEFAULT_BUCKETS,
    GuardedWhiteListClient,
    QuotaGuard,
)
from kyb_vetter_core.storage.memory import MemoryQuotaStore

MF = "https://mf.example"
NIP = "1234563218"
NRB = "61109010140000071219812874"
TODAY = date(2026, 10, 22)


def test_default_buckets_follow_the_spec_margins() -> None:
    assert DEFAULT_BUCKETS[BUCKET_SEARCH].limit == 100
    assert DEFAULT_BUCKETS[BUCKET_SEARCH].threshold == 90
    assert DEFAULT_BUCKETS[BUCKET_CHECK].limit == 5000
    assert DEFAULT_BUCKETS[BUCKET_CHECK].threshold == 4800
    assert DEFAULT_BUCKETS[BUCKET_STATUS].limit == 50_000
    assert DEFAULT_BUCKETS[BUCKET_STATUS].threshold == 45_000


async def test_guard_refuses_at_threshold_with_reset_time() -> None:
    guard = QuotaGuard(MemoryQuotaStore(), today=lambda: TODAY)
    guard = guard.with_buckets(
        {BUCKET_SEARCH: DEFAULT_BUCKETS[BUCKET_SEARCH].model_copy(update={"threshold": 2})}
    )

    assert await guard.reserve(BUCKET_SEARCH) == 1
    assert await guard.reserve(BUCKET_SEARCH) == 2
    with pytest.raises(QuotaExhaustedError) as excinfo:
        await guard.reserve(BUCKET_SEARCH)

    assert excinfo.value.bucket == BUCKET_SEARCH
    assert excinfo.value.used == 2
    assert excinfo.value.threshold == 2
    assert excinfo.value.resets_on == date(2026, 10, 23)
    assert "midnight" in str(excinfo.value).lower()


async def test_guard_usage_reports_per_bucket() -> None:
    guard = QuotaGuard(MemoryQuotaStore(), today=lambda: TODAY)
    await guard.reserve(BUCKET_CHECK)
    usage = await guard.usage()
    assert usage[BUCKET_CHECK] == (1, 4800)
    assert usage[BUCKET_SEARCH] == (0, 90)


# --- guarded client -------------------------------------------------------


@pytest.fixture
def store() -> MemoryQuotaStore:
    return MemoryQuotaStore()


@pytest.fixture
async def client(
    store: MemoryQuotaStore, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[GuardedWhiteListClient]:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(mf_base_url=MF, project_name="unit-test")
    guard = QuotaGuard(store, today=lambda: TODAY)
    async with httpx.AsyncClient() as http:
        yield GuardedWhiteListClient(WhiteListClient(http, settings), guard)


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=MF, assert_all_called=False) as router:
        yield router


async def test_each_method_charges_its_bucket(
    client: GuardedWhiteListClient,
    store: MemoryQuotaStore,
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    mock_api.get(f"/api2/status/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/status_czynny")
    )
    mock_api.get(f"/api/search/nip/{NIP}").respond(200, json=fixture_json("whitelist/search_found"))
    mock_api.get(f"/api/search/nips/{NIP},7740001454").respond(
        200, json=fixture_json("whitelist/search_many")
    )
    mock_api.get(f"/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        200, json=fixture_json("whitelist/check_tak")
    )

    await client.status(NIP)
    await client.search(NIP)
    await client.search_many([NIP, "7740001454"])  # one query regardless of batch size
    await client.check(NIP, NRB)

    assert await store.usage(BUCKET_STATUS, TODAY) == 1
    assert await store.usage(BUCKET_SEARCH, TODAY) == 2
    assert await store.usage(BUCKET_CHECK, TODAY) == 1


async def test_refusal_happens_before_the_network_call(
    client: GuardedWhiteListClient, store: MemoryQuotaStore, mock_api: respx.MockRouter
) -> None:
    await store.exhaust(BUCKET_SEARCH, TODAY, limit=90)
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    with pytest.raises(QuotaExhaustedError):
        await client.search(NIP)

    assert not route.called


async def test_invalid_input_does_not_consume_quota(
    client: GuardedWhiteListClient, store: MemoryQuotaStore, mock_api: respx.MockRouter
) -> None:
    from kyb_vetter_core.errors import InvalidNipError

    with pytest.raises(InvalidNipError):
        await client.search("1234567890")

    assert await store.usage(BUCKET_SEARCH, TODAY) == 0


async def test_registry_limit_error_marks_bucket_exhausted(
    client: GuardedWhiteListClient,
    store: MemoryQuotaStore,
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").respond(429, json=fixture_json("whitelist/error_wl191"))

    with pytest.raises(DailyLimitExceededError):
        await client.search(NIP)
    with pytest.raises(QuotaExhaustedError):
        await client.search(NIP)

    assert await store.usage(BUCKET_SEARCH, TODAY) == 90
