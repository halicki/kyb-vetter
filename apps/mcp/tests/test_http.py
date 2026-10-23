"""Hosted transport: Streamable HTTP mounted under /mcp plus /healthz, exercised in-process over ASGI."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import pytest
import respx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from kyb_vetter_core.config import Settings
from kyb_vetter_mcp.http import allowed_hosts, build_http_app
from kyb_vetter_mcp.server import (
    TOOL_CHECK_BANK_ACCOUNT,
    TOOL_VERIFICATION_HISTORY,
    TOOL_VERIFY_COMPANY,
)

from .conftest import MF, NIP

BASE = "http://localhost"  # must match the DNS-rebinding allow-list


@asynccontextmanager
async def hosted(settings: Settings, base_url: str = BASE) -> AsyncGenerator[httpx2.AsyncClient]:
    """In-process ASGI client (httpx2, which the SDK transport expects).

    Same task for enter and exit: the SDK lifespan uses anyio cancel scopes.
    ASGITransport does not run lifespan events itself, so the app lifespan is entered explicitly.
    """
    app = build_http_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url=base_url) as client,
    ):
        yield client


async def test_healthz_reports_name_and_storage_mode(settings: Settings) -> None:
    async with hosted(settings) as http:
        response = await http.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["name"] == "unit-test-connector"
    assert body["persistent"] is False


async def test_mcp_endpoint_lists_tools_over_streamable_http(settings: Settings) -> None:
    async with (
        hosted(settings) as http,
        Client(streamable_http_client(f"{BASE}/mcp", http_client=http)) as client,
    ):
        tools = {t.name for t in (await client.list_tools()).tools}

    assert tools == {TOOL_VERIFY_COMPANY, TOOL_CHECK_BANK_ACCOUNT, TOOL_VERIFICATION_HISTORY}


async def test_mcp_endpoint_calls_a_tool_over_streamable_http(
    settings: Settings, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    wl_found["result"]["subject"]["krs"] = None
    mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl_found)

    async with (
        hosted(settings) as http,
        Client(streamable_http_client(f"{BASE}/mcp", http_client=http)) as client,
    ):
        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP})

    assert result.is_error is False
    assert result.structured_content is not None
    assert result.structured_content["found"] is True


async def test_unknown_host_header_is_rejected(settings: Settings) -> None:
    strict = settings.model_copy(update={"domain": "mcp.example.test"})
    async with hosted(strict, base_url="http://evil.example") as http:
        response = await http.post("/mcp", json={}, headers={"Host": "evil.example"})
    assert response.status_code == 421


def test_allowed_hosts_include_domain_loopback_and_extras(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_EXTRA_ALLOWED_HOSTS", '["svc-123.europe-west1.run.app"]')
    hosts = allowed_hosts(Settings(domain="mcp.example.test"))
    assert "mcp.example.test" in hosts
    assert "svc-123.europe-west1.run.app" in hosts
    assert {"localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"} <= set(hosts)
    assert "mcp.example.test" not in allowed_hosts(Settings(domain="localhost"))


async def test_host_check_can_be_disabled_behind_a_platform(settings: Settings) -> None:
    relaxed = settings.model_copy(update={"domain": "mcp.example.test", "host_check": False})
    async with hosted(relaxed, base_url="http://anything.a.run.app") as http:
        response = await http.get("/health", headers={"Host": "anything.a.run.app"})
    assert response.status_code == 200


async def test_health_reports_flat_file_state(settings: Settings) -> None:
    async with hosted(settings) as http:
        body = (await http.get("/health")).json()
    assert body["flat_file"] == {"loaded": False, "date": None}
