from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from kyb_vetter_core.cache import CachedKrsClient, CachedWhiteListClient, next_warsaw_midnight
from kyb_vetter_core.clients import whitelist as whitelist_module
from kyb_vetter_core.clients.krs import KrsClient
from kyb_vetter_core.clients.whitelist import WhiteListClient
from kyb_vetter_core.config import Settings
from kyb_vetter_core.storage.memory import MemoryCacheStore

MF = "https://mf.example"
KRS = "https://krs.example"
NIP = "1234563218"
NRB = "61109010140000071219812874"
ORLEN_KRS = "0000028860"
TODAY = date(2026, 10, 22)
NOW = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)  # 12:00 in Warsaw (CEST)
WARSAW = ZoneInfo("Europe/Warsaw")


def test_next_warsaw_midnight() -> None:
    assert next_warsaw_midnight(NOW) == datetime(2026, 10, 23, 0, 0, tzinfo=WARSAW)
    late = datetime(2026, 10, 22, 22, 30, tzinfo=UTC)  # 00:30 on the 23rd in Warsaw
    assert next_warsaw_midnight(late) == datetime(2026, 10, 24, 0, 0, tzinfo=WARSAW)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store() -> MemoryCacheStore:
    return MemoryCacheStore()


@pytest.fixture
async def clients(
    store: MemoryCacheStore, clock: Clock, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[CachedWhiteListClient, CachedKrsClient]]:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(mf_base_url=MF, krs_base_url=KRS, project_name="unit-test")
    async with httpx.AsyncClient() as http:
        yield (
            CachedWhiteListClient(
                WhiteListClient(http, settings), store, now=clock, today=lambda: TODAY
            ),
            CachedKrsClient(KrsClient(http, settings), store, now=clock, today=lambda: TODAY),
        )


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


async def test_search_is_served_from_cache_until_midnight(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    clock: Clock,
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    wl, _ = clients
    route = mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/search_found")
    )

    first = await wl.search(NIP)
    second = await wl.search("123-456-32-18")  # normalised key
    assert route.call_count == 1
    assert first.receipt.from_cache is False
    assert second.receipt.from_cache is True
    assert second.receipt.request_id == first.receipt.request_id
    assert second.subject == first.subject

    clock.now = datetime(2026, 10, 22, 22, 5, tzinfo=UTC)  # past Warsaw midnight
    third = await wl.search(NIP)
    assert route.call_count == 2
    assert third.receipt.from_cache is False


async def test_search_cache_is_keyed_by_queried_date(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    wl, _ = clients
    route = mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/search_found")
    )

    await wl.search(NIP, date=date(2026, 1, 15))
    await wl.search(NIP, date=date(2026, 1, 16))
    await wl.search(NIP, date=date(2026, 1, 15))

    assert route.call_count == 2


async def test_status_cache_expires_after_one_hour(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    clock: Clock,
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    wl, _ = clients
    route = mock_api.get(f"{MF}/api2/status/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/status_czynny")
    )

    await wl.status(NIP)
    clock.now = NOW + timedelta(minutes=59)
    cached = await wl.status(NIP)
    clock.now = NOW + timedelta(minutes=61)
    await wl.status(NIP)

    assert route.call_count == 2
    assert cached.receipt.from_cache is True


async def test_check_is_cached_per_nip_account_pair(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    wl, _ = clients
    route = mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        200, json=fixture_json("whitelist/check_tak")
    )

    await wl.check(NIP, NRB)
    again = await wl.check(NIP, "PL61 1090 1014 0000 0712 1981 2874")

    assert route.call_count == 1
    assert again.assigned is True
    assert again.receipt.from_cache is True


async def test_search_many_is_not_cached(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    wl, _ = clients
    route = mock_api.get(f"{MF}/api/search/nips/{NIP},7740001454").respond(
        200, json=fixture_json("whitelist/search_many")
    )

    await wl.search_many([NIP, "7740001454"])
    await wl.search_many([NIP, "7740001454"])

    assert route.call_count == 2


async def test_errors_are_not_cached(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    from kyb_vetter_core.errors import RegistryUnavailableError

    wl, _ = clients
    route = mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(503, text="down")

    for _ in range(2):
        with pytest.raises(RegistryUnavailableError):
            await wl.search(NIP)

    assert route.call_count == 2


async def test_krs_extract_is_cached_per_day(
    clients: tuple[CachedWhiteListClient, CachedKrsClient],
    clock: Clock,
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    _, krs = clients
    route = mock_api.get(f"{KRS}/api/krs/OdpisAktualny/{ORLEN_KRS}").respond(
        200, json=fixture_json(f"krs/{ORLEN_KRS}")
    )

    first = await krs.get_extract(ORLEN_KRS)
    second = await krs.get_extract("28860")
    assert route.call_count == 1
    assert second.receipt.from_cache is True
    assert second.name == first.name
    assert second.share_capital == first.share_capital

    clock.now = datetime(2026, 10, 22, 22, 5, tzinfo=UTC)
    await krs.get_extract(ORLEN_KRS)
    assert route.call_count == 2
