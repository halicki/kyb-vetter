"""One principal from either an API key or an Auth0 bearer token (ADR-0020)."""

from datetime import UTC, datetime

from kyb_vetter_core.apikeys import generate_api_key
from kyb_vetter_core.auth import Principal
from kyb_vetter_core.principals import Authenticator
from kyb_vetter_core.storage.memory import MemoryApiKeyStore

NOW = datetime(2026, 10, 23, 20, 0, tzinfo=UTC)
GOOD_JWT = "good-jwt"


class FakeJwt:
    """Stands in for :class:`JwtVerifier`: accepts exactly one token."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def verify(self, token: str) -> Principal | None:
        self.seen.append(token)
        if token != GOOD_JWT:
            return None
        return Principal(
            subject="auth0|bob", client_id="c", issuer="https://idp/", scopes=(), expires_at=None
        )


async def _keyed() -> tuple[Authenticator, str, FakeJwt]:
    store = MemoryApiKeyStore()
    plaintext, record = generate_api_key("auth0|alice", "ci", now=NOW)
    await store.insert(record)
    jwt = FakeJwt()
    return Authenticator(apikeys=store, jwt=jwt, now=lambda: NOW), plaintext, jwt


async def test_api_key_resolves_to_its_owner() -> None:
    auth, key, _ = await _keyed()
    assert await auth.principal(api_key=key, bearer=None) == "auth0|alice"


async def test_bearer_token_resolves_to_its_subject() -> None:
    auth, _, _ = await _keyed()
    assert await auth.principal(api_key=None, bearer="good-jwt") == "auth0|bob"


async def test_key_wins_and_an_invalid_key_never_falls_back_to_the_token() -> None:
    auth, key, jwt = await _keyed()
    assert await auth.principal(api_key=key, bearer="good-jwt") == "auth0|alice"
    assert await auth.principal(api_key="bad.key", bearer="good-jwt") is None
    assert jwt.seen == []


async def test_missing_or_invalid_credentials_give_no_principal() -> None:
    auth, _, _ = await _keyed()
    assert await auth.principal(api_key=None, bearer=None) is None
    assert await auth.principal(api_key=None, bearer="bad-jwt") is None
    assert await auth.principal(api_key="", bearer="") is None


async def test_bearer_is_refused_when_no_issuer_is_configured() -> None:
    store = MemoryApiKeyStore()
    auth = Authenticator(apikeys=store, jwt=None, now=lambda: NOW)
    assert await auth.principal(api_key=None, bearer="good-jwt") is None


def test_default_clock_is_utc() -> None:
    auth = Authenticator(apikeys=MemoryApiKeyStore(), jwt=None)
    assert auth.now().tzinfo is UTC
