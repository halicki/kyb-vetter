from collections.abc import AsyncIterator, Callable, Iterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from kyb_vetter_core.clients import whitelist as whitelist_module
from kyb_vetter_core.clients.whitelist import WhiteListClient
from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import (
    DailyLimitExceededError,
    DataUpdatedRetryError,
    InvalidBankAccountError,
    InvalidNipError,
    RegistryUnavailableError,
    RemoteValidationError,
    TooManyIdentifiersError,
)
from kyb_vetter_core.models import VatStatus

BASE = "https://wl.example"
NIP = "1234563218"
NRB = "61109010140000071219812874"
TODAY = date(2026, 10, 22)


@pytest.fixture
def settings() -> Settings:
    return Settings(mf_base_url=BASE, project_name="unit-test")


@pytest.fixture
async def client(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[WhiteListClient]:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    async with httpx.AsyncClient() as http:
        yield WhiteListClient(http, settings)


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


async def test_status_returns_vat_status_with_receipt(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(f"/api2/status/nip/{NIP}", params={"date": "2026-10-22"}).respond(
        200, json=fixture_json("whitelist/status_czynny")
    )

    result = await client.status(NIP)

    assert result.status is VatStatus.ACTIVE
    assert result.receipt.request_id == "d2n10-84df1a1"
    assert result.receipt.source == "mf-whitelist-status"
    assert result.receipt.host == "wl.example"
    assert route.calls.last.request.headers["User-Agent"].startswith("unit-test/")


async def test_search_uses_explicit_date_and_maps_subject(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}", params={"date": "2026-01-15"}).respond(
        200, json=fixture_json("whitelist/search_found")
    )

    result = await client.search(NIP, date=date(2026, 1, 15))

    assert result.subject is not None
    assert result.subject.name == "ABC Jan Nowak"
    assert result.receipt.queried_date == date(2026, 1, 15)


async def test_search_unknown_nip_returns_none_subject(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/search_missing")
    )

    result = await client.search(NIP)

    assert result.subject is None
    assert result.receipt.request_id == "d2n10-84df1a1"


async def test_search_normalizes_formatted_nip_before_calling(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(f"/api/search/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/search_found")
    )

    await client.search("PL 123-456-32-18")

    assert route.called


async def test_invalid_nip_is_rejected_locally_without_a_request(
    client: WhiteListClient, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    with pytest.raises(InvalidNipError):
        await client.search("1234567890")
    with pytest.raises(InvalidNipError):
        await client.status("1234567890")

    assert not route.called


async def test_search_many_maps_subjects_and_per_identifier_errors(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(f"/api/search/nips/{NIP},7740001454").respond(
        200, json=fixture_json("whitelist/search_many")
    )

    batch = await client.search_many([NIP, "774-000-14-54"])

    assert route.called
    assert batch.subjects[NIP][0].nip == NIP
    assert batch.subjects["7740001454"] == ()
    assert batch.errors["1234567890"].code == "WL-115"


async def test_search_many_rejects_more_than_30_identifiers_locally(
    client: WhiteListClient, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    with pytest.raises(TooManyIdentifiersError):
        await client.search_many([NIP] * 31)

    assert not route.called


async def test_check_maps_tak_and_nie(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(f"/api/check/nip/{NIP}/bank-account/{NRB}", params={"date": "2026-10-22"})
    route.side_effect = [
        httpx.Response(200, json=fixture_json("whitelist/check_tak")),
        httpx.Response(200, json=fixture_json("whitelist/check_nie")),
    ]

    yes = await client.check(NIP, "PL61 1090 1014 0000 0712 1981 2874")
    no = await client.check(NIP, NRB)

    assert yes.assigned is True
    assert no.assigned is False
    assert yes.account == NRB
    assert yes.nip == NIP


async def test_check_rejects_invalid_account_locally(
    client: WhiteListClient, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    with pytest.raises(InvalidBankAccountError):
        await client.check(NIP, "62109010140000071219812874")

    assert not route.called


async def test_http_400_with_wl_code_maps_to_domain_error(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").respond(400, json=fixture_json("whitelist/error_wl115"))

    with pytest.raises(RemoteValidationError) as excinfo:
        await client.search(NIP)

    assert excinfo.value.code == "WL-115"
    assert excinfo.value.http_status == 400


async def test_http_429_daily_limit(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").respond(429, json=fixture_json("whitelist/error_wl191"))

    with pytest.raises(DailyLimitExceededError):
        await client.search(NIP)


async def test_wl195_is_retried_exactly_once(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(f"/api/search/nip/{NIP}")
    route.side_effect = [
        httpx.Response(400, json=fixture_json("whitelist/error_wl195")),
        httpx.Response(200, json=fixture_json("whitelist/search_found")),
    ]

    result = await client.search(NIP)

    assert result.subject is not None
    assert route.call_count == 2


async def test_wl195_twice_raises_and_does_not_loop(
    client: WhiteListClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(f"/api/search/nip/{NIP}").respond(
        400, json=fixture_json("whitelist/error_wl195")
    )

    with pytest.raises(DataUpdatedRetryError):
        await client.search(NIP)

    assert route.call_count == 2


async def test_server_error_without_json_body(
    client: WhiteListClient, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").respond(502, text="Bad Gateway")

    with pytest.raises(RegistryUnavailableError) as excinfo:
        await client.search(NIP)

    assert excinfo.value.http_status == 502


async def test_timeout_maps_to_unavailable(
    client: WhiteListClient, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(RegistryUnavailableError):
        await client.search(NIP)


async def test_unexpected_payload_maps_to_unavailable(
    client: WhiteListClient, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"/api/search/nip/{NIP}").respond(200, json={"unexpected": True})

    with pytest.raises(RegistryUnavailableError):
        await client.search(NIP)


def test_today_in_warsaw_returns_a_date() -> None:
    assert isinstance(whitelist_module.today_in_warsaw(), date)
