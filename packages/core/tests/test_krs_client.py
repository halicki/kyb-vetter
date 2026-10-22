from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from kyb_vetter_core.clients import krs as krs_module
from kyb_vetter_core.clients.krs import KrsClient
from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import (
    InvalidKrsError,
    NotFoundError,
    RegistryError,
    RegistryUnavailableError,
)

BASE = "https://krs.example"
KRS = "0000028860"
PATH = f"/api/krs/OdpisAktualny/{KRS}"
NOW = datetime(2026, 10, 22, 19, 13, tzinfo=UTC)
PROBLEM_404 = {
    "type": "https://tools.ietf.org/html/rfc7231#section-6.5.4",
    "title": "Not Found",
    "status": 404,
}
PROBLEM_400 = {
    "type": "https://tools.ietf.org/html/rfc7231#section-6.5.1",
    "title": "Bad Request",
    "status": 400,
}


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[KrsClient]:
    monkeypatch.setattr(krs_module, "now_utc", lambda: NOW)
    async with httpx.AsyncClient() as http:
        yield KrsClient(http, Settings(krs_base_url=BASE, project_name="unit-test"))


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(base_url=BASE, assert_all_called=False) as router:
        yield router


async def test_get_extract_from_entrepreneurs_register(
    client: KrsClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(PATH, params={"rejestr": "P", "format": "json"}).respond(
        200, json=fixture_json("krs/0000028860")
    )

    extract = await client.get_extract(KRS)

    assert extract.name == "ORLEN SPÓŁKA AKCYJNA"
    assert extract.register_kind == "P"
    assert extract.receipt.request_datetime == NOW
    assert route.call_count == 1
    assert route.calls.last.request.headers["User-Agent"].startswith("unit-test/")


async def test_falls_back_to_associations_register_on_404(
    client: KrsClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    payload = fixture_json("krs/0000028860")
    payload["odpis"]["naglowekA"]["rejestr"] = "RejS"
    route_p = mock_api.get(PATH, params={"rejestr": "P"}).respond(404, json=PROBLEM_404)
    route_s = mock_api.get(PATH, params={"rejestr": "S"}).respond(200, json=payload)

    extract = await client.get_extract(KRS)

    assert extract.register_kind == "S"
    assert route_p.called
    assert route_s.called


async def test_not_found_in_both_registers(client: KrsClient, mock_api: respx.MockRouter) -> None:
    mock_api.get(PATH).respond(404, json=PROBLEM_404)

    with pytest.raises(NotFoundError) as excinfo:
        await client.get_extract(KRS)

    assert excinfo.value.source == "krs"
    assert excinfo.value.http_status == 404


async def test_short_number_is_zero_padded_in_the_url(
    client: KrsClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(PATH).respond(200, json=fixture_json("krs/0000028860"))

    await client.get_extract("28860")

    assert route.called


async def test_invalid_number_is_rejected_locally(
    client: KrsClient, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    with pytest.raises(InvalidKrsError):
        await client.get_extract("0000000000")

    assert not route.called


async def test_bad_request_maps_to_registry_error(
    client: KrsClient, mock_api: respx.MockRouter
) -> None:
    mock_api.get(PATH).respond(400, json=PROBLEM_400)

    with pytest.raises(RegistryError) as excinfo:
        await client.get_extract(KRS)

    assert excinfo.value.http_status == 400
    assert "Bad Request" in excinfo.value.message


async def test_server_error_is_retried_once(
    client: KrsClient, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    route = mock_api.get(PATH, params={"rejestr": "P"})
    route.side_effect = [
        httpx.Response(503, text="down"),
        httpx.Response(200, json=fixture_json("krs/0000028860")),
    ]

    extract = await client.get_extract(KRS)

    assert extract.krs == KRS
    assert route.call_count == 2


async def test_persistent_server_error_raises_unavailable(
    client: KrsClient, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(PATH).respond(503, text="down")

    with pytest.raises(RegistryUnavailableError) as excinfo:
        await client.get_extract(KRS)

    assert excinfo.value.http_status == 503
    assert route.call_count == 2


async def test_timeout_is_retried_once_then_raises(
    client: KrsClient, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(PATH).mock(side_effect=httpx.ReadTimeout("slow"))

    with pytest.raises(RegistryUnavailableError):
        await client.get_extract(KRS)

    assert route.call_count == 2


async def test_unexpected_payload_maps_to_unavailable(
    client: KrsClient, mock_api: respx.MockRouter
) -> None:
    mock_api.get(PATH).respond(200, json={"odpis": {}})

    with pytest.raises(RegistryUnavailableError):
        await client.get_extract(KRS)


async def test_non_json_200_maps_to_unavailable(
    client: KrsClient, mock_api: respx.MockRouter
) -> None:
    mock_api.get(PATH).respond(200, text="<html>")

    with pytest.raises(RegistryUnavailableError):
        await client.get_extract(KRS)


def test_now_utc_is_timezone_aware() -> None:
    assert krs_module.now_utc().tzinfo is not None
