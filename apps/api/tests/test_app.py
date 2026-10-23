"""REST v1 over the core service (ADR-0020), exercised in-process over ASGI."""

from collections.abc import Callable
from typing import Any

import respx

from kyb_vetter_core.config import Settings

from .conftest import MF, NIP, NRB, serve

PROBLEM = "application/problem+json"


def key(k: str) -> dict[str, str]:
    return {"X-API-Key": k}


async def test_health_is_public(settings: Settings) -> None:
    async with serve(settings) as (http, _):
        response = await http.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["name"] == "unit-test-api"


async def test_openapi_lists_the_v1_routes_and_api_key_security(settings: Settings) -> None:
    async with serve(settings) as (http, _):
        spec = (await http.get("/openapi.json")).json()
    assert spec["info"]["title"] == "unit-test-api"
    assert set(spec["paths"]) >= {
        "/v1/companies/{nip}",
        "/v1/companies/{nip}/bank-accounts/{account}",
        "/v1/companies/{nip}/history",
    }
    assert "ApiKey" in spec["components"]["securitySchemes"]


async def test_missing_or_bad_credentials_are_401_problems(settings: Settings) -> None:
    async with serve(settings) as (http, _):
        none = await http.get(f"/v1/companies/{NIP}")
        bad = await http.get(f"/v1/companies/{NIP}", headers=key("nope.nope"))
    for response in (none, bad):
        assert response.status_code == 401
        assert response.headers["content-type"] == PROBLEM
        assert response.headers["www-authenticate"].startswith("ApiKey")
        assert response.json()["status"] == 401


async def test_company_lookup_returns_the_core_model(
    settings: Settings, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl_found)
    async with serve(settings) as (http, k):
        response = await http.get(f"/v1/companies/{NIP}", headers=key(k))
    assert response.status_code == 200
    body = response.json()
    assert body["nip"] == NIP
    assert body["found"] is True
    assert body["vat"]["name"] == "ORLEN S.A."


async def test_bank_account_check_and_history_belong_to_the_caller(
    settings: Settings,
    mock_api: respx.MockRouter,
    fixture_json: Callable[[str], Any],
) -> None:
    mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        200, json=fixture_json("whitelist/check_tak")
    )
    mock_api.get(f"{MF}/api2/status/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/status_czynny")
    )
    async with serve(settings) as (http, k):
        check = await http.get(f"/v1/companies/{NIP}/bank-accounts/{NRB}", headers=key(k))
        history = await http.get(f"/v1/companies/{NIP}/history?limit=5", headers=key(k))
    assert check.status_code == 200
    assert check.json()["assigned"] is True
    assert history.status_code == 200
    assert [e["tool"] for e in history.json()["entries"]] == ["check_bank_account"]


async def test_invalid_identifier_and_bad_query_are_422_problems(settings: Settings) -> None:
    async with serve(settings) as (http, k):
        bad_nip = await http.get("/v1/companies/1234567890", headers=key(k))
        bad_date = await http.get(f"/v1/companies/{NIP}?date=yesterday", headers=key(k))
        bad_limit = await http.get(f"/v1/companies/{NIP}/history?limit=0", headers=key(k))
        bad_account = await http.get(f"/v1/companies/{NIP}/bank-accounts/123", headers=key(k))
        bad_history_nip = await http.get("/v1/companies/1234567890/history", headers=key(k))
    for response in (bad_nip, bad_date, bad_limit, bad_account, bad_history_nip):
        assert response.status_code == 422
        assert response.headers["content-type"] == PROBLEM
    assert "NIP" in bad_nip.json()["detail"]


async def test_user_limit_is_429_with_retry_after(
    settings: Settings, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl_found)
    limited = settings.model_copy(update={"user_daily_limit_verify": 1})
    async with serve(limited) as (http, k):
        await http.get(f"/v1/companies/{NIP}", headers=key(k))
        response = await http.get(f"/v1/companies/{NIP}", headers=key(k))
    assert response.status_code == 429
    assert response.headers["content-type"] == PROBLEM
    assert 0 < int(response.headers["retry-after"]) <= 25 * 3600
    assert response.json()["type"].endswith("/user-limit")


async def test_ministry_block_then_quota_guard_are_503_with_retry_after(
    settings: Settings, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(
        429, json=fixture_json("whitelist/error_wl191")
    )
    async with serve(settings) as (http, k):
        blocked = await http.get(f"/v1/companies/{NIP}", headers=key(k))
        guarded = await http.get(f"/v1/companies/{NIP}?date=2026-01-02", headers=key(k))

    assert blocked.status_code == 503
    assert blocked.json()["type"].endswith("/registry-blocked")
    assert int(blocked.headers["retry-after"]) > 0
    assert guarded.status_code == 503  # pinned guard refuses without calling the registry
    assert guarded.json()["type"].endswith("/quota-guard")
    assert int(guarded.headers["retry-after"]) > 0


async def test_register_down_is_503_and_rejection_is_502(
    settings: Settings, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(f"{MF}/api/search/nip/{NIP}")
    async with serve(settings) as (http, k):
        route.respond(500, text="boom")
        down = await http.get(f"/v1/companies/{NIP}", headers=key(k))
        route.respond(400, json={"code": "WL-199", "message": "nope"})
        rejected = await http.get(f"/v1/companies/{NIP}?date=2026-01-04", headers=key(k))

    assert down.status_code == 503
    assert down.json()["type"].endswith("/registry-unavailable")
    assert rejected.status_code == 502
    assert rejected.json()["type"].endswith("/registry-rejected")
