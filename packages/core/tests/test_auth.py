"""JWT access-token verification against a JWKS (ADR-0017)."""

import time
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
import jwt
import pytest
import respx
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from kyb_vetter_core.auth import JwksCache, JwtVerifier, Principal

ISSUER = "https://tenant.eu.auth0.com/"
JWKS_URL = "https://tenant.eu.auth0.com/.well-known/jwks.json"
AUDIENCE = "https://mcp.example.test/mcp"
NOW = int(time.time())  # PyJWT checks ``exp`` against wall time


class Signer:
    """An RSA key pair with a ``kid``: signs tokens and publishes its JWK."""

    def __init__(self, kid: str) -> None:
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self._pem = self._key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def jwk(self) -> dict[str, Any]:
        public = RSAAlgorithm.to_jwk(self._key.public_key(), as_dict=True)
        return {**public, "kid": self.kid, "use": "sig", "alg": "RS256"}

    def token(self, kid: str | None = None, **overrides: Any) -> str:
        claims: dict[str, Any] = {
            "iss": ISSUER,
            "sub": "google-oauth2|123",
            "aud": [AUDIENCE, f"{ISSUER}userinfo"],
            "iat": NOW,
            "exp": NOW + 3600,
            "azp": "client-abc",
            "scope": "openid profile",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        headers = {"kid": self.kid if kid is None else kid}
        return jwt.encode(claims, self._pem, algorithm="RS256", headers=headers)


@pytest.fixture
def signer() -> Signer:
    return Signer("key-1")


@pytest.fixture
def jwks_route(signer: Signer) -> Iterator[respx.Route]:
    with respx.mock(assert_all_called=False) as router:
        yield router.get(JWKS_URL).respond(200, json={"keys": [signer.jwk()]})


@pytest.fixture
def clock() -> Callable[[], float]:
    return lambda: float(NOW)


@pytest.fixture
async def verifier(
    jwks_route: respx.Route, clock: Callable[[], float]
) -> AsyncIterator[JwtVerifier]:
    async with httpx.AsyncClient() as http:
        yield JwtVerifier(JwksCache(http, JWKS_URL, now=clock), issuer=ISSUER, audience=AUDIENCE)


async def test_valid_token_yields_a_principal(verifier: JwtVerifier, signer: Signer) -> None:
    principal = await verifier.verify(signer.token())

    assert principal == Principal(
        subject="google-oauth2|123",
        client_id="client-abc",
        issuer=ISSUER,
        scopes=("openid", "profile"),
        expires_at=NOW + 3600,
    )


async def test_client_id_claim_wins_over_azp_and_may_be_absent(
    verifier: JwtVerifier, signer: Signer
) -> None:
    explicit = await verifier.verify(signer.token(client_id="https://claude.ai/client.json"))
    none = await verifier.verify(signer.token(azp=None))

    assert explicit is not None
    assert explicit.client_id == "https://claude.ai/client.json"
    assert none is not None
    assert none.client_id is None


async def test_missing_scope_claim_means_no_scopes(verifier: JwtVerifier, signer: Signer) -> None:
    principal = await verifier.verify(signer.token(scope=None))
    assert principal is not None
    assert principal.scopes == ()


@pytest.mark.parametrize(
    "overrides",
    [
        {"aud": "https://other.example/mcp"},
        {"iss": "https://evil.example/"},
        {"exp": NOW - 1},
        {"sub": None},
        {"exp": None},
    ],
    ids=["wrong-audience", "wrong-issuer", "expired", "no-subject", "no-expiry"],
)
async def test_bad_claims_are_rejected(
    verifier: JwtVerifier, signer: Signer, overrides: dict[str, Any]
) -> None:
    assert await verifier.verify(signer.token(**overrides)) is None


async def test_token_signed_by_another_key_is_rejected(verifier: JwtVerifier) -> None:
    impostor = Signer("key-1")  # same kid, different key
    assert await verifier.verify(impostor.token()) is None


async def test_garbage_and_kid_less_tokens_are_rejected(
    verifier: JwtVerifier, signer: Signer
) -> None:
    assert await verifier.verify("not-a-jwt") is None
    assert await verifier.verify(signer.token(kid="")) is None


async def test_jwks_is_cached_within_ttl(
    verifier: JwtVerifier, signer: Signer, jwks_route: respx.Route
) -> None:
    await verifier.verify(signer.token())
    await verifier.verify(signer.token())
    assert jwks_route.call_count == 1


async def test_unknown_kid_refreshes_jwks_once(
    verifier: JwtVerifier, signer: Signer, jwks_route: respx.Route
) -> None:
    rotated = Signer("key-2")
    await verifier.verify(signer.token())  # primes the cache with key-1 only
    jwks_route.respond(200, json={"keys": [signer.jwk(), rotated.jwk()]})

    assert await verifier.verify(rotated.token()) is not None
    assert jwks_route.call_count == 2


async def test_kid_still_unknown_after_refresh_is_rejected_without_a_third_fetch(
    verifier: JwtVerifier, signer: Signer, jwks_route: respx.Route
) -> None:
    await verifier.verify(signer.token())
    stranger = Signer("key-9")

    assert await verifier.verify(stranger.token()) is None
    assert jwks_route.call_count == 2
    assert (
        await verifier.verify(stranger.token()) is None
    )  # refreshed again: cache was marked stale
    assert jwks_route.call_count == 3


async def test_jwks_fetch_failure_rejects_the_token(
    verifier: JwtVerifier, signer: Signer, jwks_route: respx.Route
) -> None:
    jwks_route.respond(503)
    assert await verifier.verify(signer.token()) is None
    jwks_route.respond(200, text="not json")
    assert await verifier.verify(signer.token()) is None


async def test_jwks_expires_after_ttl(signer: Signer, jwks_route: respx.Route) -> None:
    clock = {"t": 0.0}
    async with httpx.AsyncClient() as http:
        verifier = JwtVerifier(
            JwksCache(http, JWKS_URL, ttl_s=600, now=lambda: clock["t"]),
            issuer=ISSUER,
            audience=AUDIENCE,
        )
        await verifier.verify(signer.token())
        clock["t"] = 601.0
        await verifier.verify(signer.token())
    assert jwks_route.call_count == 2


def test_default_clock_is_wall_time() -> None:
    assert abs(JwksCache.default_now() - time.monotonic()) < 1.0
