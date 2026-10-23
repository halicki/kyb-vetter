"""Access-token verification for the hosted server (ADR-0017).

The MCP server is an OAuth 2.1 *resource server*: it never issues tokens, it
only checks that a bearer token was signed by the configured identity
provider, for this server (``aud``), and is still valid. Keys come from the
provider's JWKS endpoint and are cached in process; an unknown ``kid`` forces
one refresh (key rotation), a missing key after that marks the cache stale.
Nothing here logs token contents.
"""

import logging
import time
from typing import Any
lazy from collections.abc import Callable

import httpx
import jwt
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

ALGORITHMS = ["RS256"]
REQUIRED_CLAIMS = ["exp", "sub"]
DEFAULT_JWKS_TTL_S = 600.0


class Principal(BaseModel):
    """Who a verified token represents. ``subject`` keys all per-user state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    client_id: str | None
    """The OAuth client that obtained the token (``client_id`` or ``azp`` claim)."""
    issuer: str
    scopes: tuple[str, ...]
    expires_at: int | None


class JwksCache:
    """Signing keys of one issuer, fetched lazily and kept for ``ttl_s`` seconds."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        url: str,
        *,
        ttl_s: float = DEFAULT_JWKS_TTL_S,
        now: Callable[[], float] | None = None,
    ) -> None:
        self._http = http
        self._url = url
        self._ttl_s = ttl_s
        self._now = now if now is not None else self.default_now
        self._keys: dict[str, jwt.PyJWK] | None = None
        self._fetched_at = 0.0

    @staticmethod
    def default_now() -> float:
        return time.monotonic()

    async def key(self, kid: str) -> jwt.PyJWK | None:
        """The key for ``kid``; refreshes at most once per call when it is unknown."""
        refreshed = False
        if self._keys is None or self._now() - self._fetched_at >= self._ttl_s:
            await self._refresh()
            refreshed = True
        key = None if self._keys is None else self._keys.get(kid)
        if key is None and not refreshed:
            await self._refresh()
            key = None if self._keys is None else self._keys.get(kid)
        if key is None:
            self._keys = None  # stale: the next call fetches again
        return key

    async def _refresh(self) -> None:
        try:
            response = await self._http.get(self._url)
            response.raise_for_status()
            keyset = jwt.PyJWKSet.from_dict(response.json())
        except (httpx.HTTPError, ValueError, jwt.PyJWTError) as exc:
            logger.warning("JWKS fetch from %s failed: %s", self._url, type(exc).__name__)
            self._keys = None
            return
        self._keys = {k.key_id: k for k in keyset.keys if k.key_id is not None}
        self._fetched_at = self._now()


class JwtVerifier:
    """Verifies RS256 access tokens issued by ``issuer`` for ``audience``."""

    def __init__(self, jwks: JwksCache, *, issuer: str, audience: str) -> None:
        self._jwks = jwks
        self._issuer = issuer
        self._audience = audience

    async def verify(self, token: str) -> Principal | None:
        """The token's principal, or ``None`` for anything that must be refused."""
        try:
            kid = jwt.get_unverified_header(token).get("kid")
        except jwt.PyJWTError as exc:
            logger.info("bearer token rejected: %s", type(exc).__name__)
            return None
        if not kid:
            logger.info("bearer token rejected: no kid header")
            return None
        key = await self._jwks.key(kid)
        if key is None:
            logger.info("bearer token rejected: unknown signing key")
            return None
        try:
            claims: dict[str, Any] = jwt.decode(
                token,
                key,
                algorithms=ALGORITHMS,
                audience=self._audience,
                issuer=self._issuer,
                options={"require": REQUIRED_CLAIMS},
            )
        except jwt.PyJWTError as exc:
            logger.info("bearer token rejected: %s", type(exc).__name__)
            return None
        client_id = claims.get("client_id", claims.get("azp"))
        return Principal(
            subject=str(claims["sub"]),
            client_id=None if client_id is None else str(client_id),
            issuer=str(claims["iss"]),
            scopes=tuple(str(claims.get("scope", "")).split()),
            expires_at=int(claims["exp"]),
        )
