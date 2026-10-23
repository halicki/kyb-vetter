"""Auth0 bearer tokens are accepted next to API keys when an issuer is configured."""

import time
from typing import Any

import jwt
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from kyb_vetter_core.config import Settings

from .conftest import MF, NIP, serve

ISSUER = "https://tenant.eu.auth0.com/"
AUDIENCE = "https://mcp.example.test/mcp"


async def test_bearer_token_identifies_the_same_principal_as_a_key(
    settings: Settings, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = RSAAlgorithm.to_jwk(private.public_key(), as_dict=True)
    mock_api.get(f"{ISSUER}.well-known/jwks.json").respond(
        200, json={"keys": [{**public, "kid": "k1", "alg": "RS256", "use": "sig"}]}
    )
    mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl_found)
    pem = private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    now = int(time.time())
    token = jwt.encode(
        {"iss": ISSUER, "sub": "auth0|alice", "aud": AUDIENCE, "iat": now, "exp": now + 600},
        pem,
        algorithm="RS256",
        headers={"kid": "k1"},
    )
    secured = settings.model_copy(update={"auth_issuer": ISSUER, "auth_audience": AUDIENCE})

    async with serve(secured, principal="auth0|alice") as (http, k):
        via_token = await http.get(
            f"/v1/companies/{NIP}", headers={"Authorization": f"Bearer {token}"}
        )
        history = await http.get(f"/v1/companies/{NIP}/history", headers={"X-API-Key": k})
        wrong_scheme = await http.get(
            f"/v1/companies/{NIP}", headers={"Authorization": f"Basic {token}"}
        )

    assert via_token.status_code == 200
    assert [e["tool"] for e in history.json()["entries"]] == ["verify_company"]
    assert wrong_scheme.status_code == 401
