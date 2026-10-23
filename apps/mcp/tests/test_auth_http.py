"""OAuth resource-server behaviour of the hosted transport (ADR-0017)."""

from typing import Any

import httpx
import httpx2
import pytest
import respx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from kyb_vetter_core.config import Settings
from kyb_vetter_mcp.auth import CoreTokenVerifier, auth_settings
from kyb_vetter_mcp.http import build_http_app
from kyb_vetter_mcp.server import TOOL_VERIFICATION_HISTORY, TOOL_VERIFY_COMPANY

from .conftest import MF, NIP
from .jwt_helpers import AUDIENCE, DOMAIN, ISSUER, JWKS_URL, Signer
from .test_http import BASE, hosted

PRM_PATH = "/.well-known/oauth-protected-resource"


@pytest.fixture
def signer(mock_api: respx.MockRouter) -> Signer:
    signer = Signer()
    mock_api.get(JWKS_URL).respond(200, json=signer.jwks())
    return signer


@pytest.fixture
def secured(settings: Settings) -> Settings:
    return settings.model_copy(update={"domain": DOMAIN, "auth_issuer": ISSUER})


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_mcp_without_a_token_is_challenged_with_resource_metadata(
    secured: Settings,
) -> None:
    async with hosted(secured) as http:
        response = await http.post("/mcp", json={})

    assert response.status_code == 401
    challenge = response.headers["WWW-Authenticate"]
    assert challenge.startswith("Bearer")
    assert f'resource_metadata="https://{DOMAIN}{PRM_PATH}/mcp"' in challenge


async def test_mcp_with_a_bad_token_is_refused(secured: Settings, signer: Signer) -> None:
    async with hosted(secured) as http:
        garbage = await http.post("/mcp", json={}, headers=bearer("nope"))
        wrong_audience = await http.post(
            "/mcp", json={}, headers=bearer(signer.token(aud="https://other.example/mcp"))
        )

    assert garbage.status_code == 401
    assert wrong_audience.status_code == 401


async def test_protected_resource_metadata_is_served_at_both_paths(secured: Settings) -> None:
    async with hosted(secured) as http:
        scoped = await http.get(f"{PRM_PATH}/mcp")
        root = await http.get(PRM_PATH)

    assert scoped.status_code == 200
    body = scoped.json()
    assert body["resource"] == AUDIENCE
    assert body["authorization_servers"] == [ISSUER]
    assert body["bearer_methods_supported"] == ["header"]
    assert root.status_code == 200
    assert root.json() == body


async def test_health_stays_public_when_auth_is_on(secured: Settings) -> None:
    async with hosted(secured) as http:
        response = await http.get("/health")
    assert response.status_code == 200


async def test_valid_token_reaches_the_tools_and_scopes_history_to_the_subject(
    secured: Settings, signer: Signer, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    wl_found["result"]["subject"]["krs"] = None
    mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl_found)

    app = build_http_app(secured)

    def as_user(subject: str) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url=BASE,
            headers=bearer(signer.token(subject)),
        )

    async with app.router.lifespan_context(app):  # one app: Alice and Bob share the stores
        async with (
            as_user("auth0|alice") as http,
            Client(streamable_http_client(f"{BASE}/mcp", http_client=http)) as alice,
        ):
            verified = await alice.call_tool(TOOL_VERIFY_COMPANY, {"nip": NIP})
            own = await alice.call_tool(TOOL_VERIFICATION_HISTORY, {"nip": NIP})
        async with (
            as_user("auth0|bob") as http,
            Client(streamable_http_client(f"{BASE}/mcp", http_client=http)) as bob,
        ):
            others = await bob.call_tool(TOOL_VERIFICATION_HISTORY, {"nip": NIP})

    assert verified.is_error is False
    assert own.structured_content is not None
    assert [e["tool"] for e in own.structured_content["entries"]] == [TOOL_VERIFY_COMPANY]
    assert others.structured_content is not None
    assert others.structured_content["entries"] == []


async def test_auth_settings_are_absent_when_no_issuer_is_configured(settings: Settings) -> None:
    assert auth_settings(settings) is None


def test_auth_settings_point_at_issuer_and_resource(secured: Settings) -> None:
    auth = auth_settings(secured)
    assert auth is not None
    assert str(auth.issuer_url) == ISSUER
    assert str(auth.resource_server_url) == AUDIENCE
    assert auth.validate_token_resource is True


async def test_verifier_refuses_everything_before_it_is_bound(secured: Settings) -> None:
    assert await CoreTokenVerifier(secured).verify_token("anything") is None


async def test_verifier_maps_the_principal_onto_an_access_token(
    secured: Settings, signer: Signer
) -> None:
    verifier = CoreTokenVerifier(secured)
    async with httpx.AsyncClient() as http:
        verifier.bind(http)
        access = await verifier.verify_token(signer.token("auth0|alice"))
        refused = await verifier.verify_token(signer.token(exp=1))

    assert access is not None
    assert access.subject == "auth0|alice"
    assert access.client_id == "client-abc"
    assert access.scopes == ["openid"]
    assert access.resource == AUDIENCE
    assert access.claims == {"iss": ISSUER}
    assert refused is None
