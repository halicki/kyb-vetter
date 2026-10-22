import json
from collections.abc import Callable
from typing import Any

import respx
from mcp.types import TextContent

from kyb_vetter_mcp.server import TOOL_CHECK_BANK_ACCOUNT, TOOL_VERIFY_COMPANY

from .conftest import KRS, MF, NIP, NRB, ORLEN_KRS, ClientFactory


async def test_server_identity_comes_from_settings(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        assert client.server_info is not None
        assert client.server_info.name == "unit-test-connector"


async def test_tools_are_listed_read_only_with_output_schema(mcp_client: ClientFactory) -> None:
    async with mcp_client() as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}

        assert set(tools) == {TOOL_VERIFY_COMPANY, TOOL_CHECK_BANK_ACCOUNT}
        for tool in tools.values():
            assert tool.annotations is not None
            assert tool.annotations.read_only_hint is True
            assert tool.annotations.open_world_hint is True
            assert tool.output_schema is not None
            assert tool.description is not None
            assert "untrusted" in tool.description.lower()
        assert set(tools[TOOL_VERIFY_COMPANY].input_schema["properties"]) == {"nip", "date"}
        assert tools[TOOL_VERIFY_COMPANY].input_schema["required"] == ["nip"]
        assert set(tools[TOOL_CHECK_BANK_ACCOUNT].input_schema["properties"]) == {
            "nip",
            "account",
            "date",
        }


async def test_verify_company_returns_structured_profile(
    mcp_client: ClientFactory,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    fixture_json: Callable[[str], Any],
) -> None:
    async with mcp_client() as client:
        mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl_found)
        mock_api.get(f"{KRS}/api/krs/OdpisAktualny/{ORLEN_KRS}").respond(
            200, json=fixture_json(f"krs/{ORLEN_KRS}")
        )

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": "123-456-32-18"})

        assert result.is_error is False
        data = result.structured_content
        assert data is not None
        assert data["nip"] == NIP
        assert data["found"] is True
        assert data["vat"]["status"] == "active"
        assert data["krs"]["name"] == "ORLEN SPÓŁKA AKCYJNA"
        assert data["warnings"] == []
        assert [s["source"] for s in data["sources"]] == ["mf-whitelist", "krs"]
        assert isinstance(result.content[0], TextContent)
        assert json.loads(result.content[0].text)["nip"] == NIP


async def test_verify_company_accepts_iso_date(
    mcp_client: ClientFactory, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    async with mcp_client() as client:
        wl_found["result"]["subject"]["krs"] = None
        route = mock_api.get(f"{MF}/api/search/nip/{NIP}", params={"date": "2026-01-15"}).respond(
            200, json=wl_found
        )

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP, "date": "2026-01-15"})

        assert result.is_error is False
        assert route.called


async def test_invalid_date_is_a_tool_error(
    mcp_client: ClientFactory, mock_api: respx.MockRouter
) -> None:
    async with mcp_client() as client:
        route = mock_api.get(url__regex=r".*").respond(200, json={})

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP, "date": "15/01/2026"})

        assert result.is_error is True
        assert isinstance(result.content[0], TextContent)
        assert "YYYY-MM-DD" in result.content[0].text
        assert not route.called


async def test_invalid_nip_is_a_tool_error_without_network(
    mcp_client: ClientFactory, mock_api: respx.MockRouter
) -> None:
    async with mcp_client() as client:
        route = mock_api.get(url__regex=r".*").respond(200, json={})

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": "1234567890"})

        assert result.is_error is True
        assert isinstance(result.content[0], TextContent)
        assert "NIP" in result.content[0].text
        assert "checksum" in result.content[0].text
        assert not route.called


async def test_daily_limit_is_reported_to_the_model(
    mcp_client: ClientFactory, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    async with mcp_client() as client:
        mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(
            429, json=fixture_json("whitelist/error_wl191")
        )

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP})

        assert result.is_error is True
        assert isinstance(result.content[0], TextContent)
        assert "midnight" in result.content[0].text.lower()


async def test_registry_outage_is_a_retry_later_error(
    mcp_client: ClientFactory, mock_api: respx.MockRouter
) -> None:
    async with mcp_client() as client:
        mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(503, text="down")

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP})

        assert result.is_error is True
        assert isinstance(result.content[0], TextContent)
        assert "later" in result.content[0].text.lower()


async def test_other_registry_rejections_are_passed_through(
    mcp_client: ClientFactory, mock_api: respx.MockRouter
) -> None:
    async with mcp_client() as client:
        mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(
            400, json={"code": "WL-190", "message": "Nieprawidłowe żądanie"}
        )

        result = await client.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP})

        assert result.is_error is True
        assert isinstance(result.content[0], TextContent)
        assert "Nieprawidłowe żądanie" in result.content[0].text


async def test_check_bank_account_returns_structured_result(
    mcp_client: ClientFactory, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    async with mcp_client() as client:
        mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
            200, json=fixture_json("whitelist/check_tak")
        )
        mock_api.get(f"{MF}/api2/status/nip/{NIP}").respond(
            200, json=fixture_json("whitelist/status_czynny")
        )

        result = await client.call_tool(
            TOOL_CHECK_BANK_ACCOUNT, {"nip": NIP, "account": "PL61 1090 1014 0000 0712 1981 2874"}
        )

        assert result.is_error is False
        data = result.structured_content
        assert data is not None
        assert data["assigned"] is True
        assert data["account"] == NRB
        assert data["vat_status"] == "active"


async def test_check_bank_account_invalid_account_is_a_tool_error(
    mcp_client: ClientFactory, mock_api: respx.MockRouter
) -> None:
    async with mcp_client() as client:
        route = mock_api.get(url__regex=r".*").respond(200, json={})

        result = await client.call_tool(
            TOOL_CHECK_BANK_ACCOUNT, {"nip": NIP, "account": "62" + NRB[2:]}
        )

        assert result.is_error is True
        assert isinstance(result.content[0], TextContent)
        assert "bank account" in result.content[0].text.lower()
        assert not route.called
