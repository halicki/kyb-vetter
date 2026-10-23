"""OAuth resource-server adapter: core's JWT verifier behind the SDK's ``TokenVerifier`` (ADR-0017).

The SDK supplies the bearer middleware (401 + ``WWW-Authenticate``), the RFC 9728
metadata route and the request-scoped principal; this module only turns a
verified :class:`Principal` into the SDK's :class:`AccessToken`.
"""

from typing import TYPE_CHECKING

from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.shared.auth import ProtectedResourceMetadata
from pydantic import AnyHttpUrl

from kyb_vetter_core.auth import JwksCache, JwtVerifier

if TYPE_CHECKING:
    import httpx

    from kyb_vetter_core.config import Settings

UNKNOWN_CLIENT = "unknown"
"""``AccessToken.client_id`` is mandatory in the SDK; tokens without ``client_id``/``azp`` get this."""


def auth_settings(settings: Settings) -> AuthSettings | None:
    """SDK auth configuration, or ``None`` when no issuer is configured (stdio, tests)."""
    if settings.auth_issuer is None:
        return None
    return AuthSettings(
        issuer_url=AnyHttpUrl(settings.auth_issuer),
        resource_server_url=AnyHttpUrl(settings.auth_resource_url),
        required_scopes=[],
        # Explicit: the SDK warns when unset and flips the default in 3.0. Core already
        # checks ``aud``; this makes the bearer middleware re-check ``AccessToken.resource``.
        validate_token_resource=True,
    )


def resource_metadata(settings: Settings) -> ProtectedResourceMetadata:
    """The RFC 9728 document, identical to what the SDK serves under ``/.well-known/...​/mcp``."""
    return ProtectedResourceMetadata(
        resource=AnyHttpUrl(settings.auth_resource_url),
        authorization_servers=[AnyHttpUrl(settings.auth_issuer or "")],
        scopes_supported=[],
    )


class CoreTokenVerifier:
    """``TokenVerifier`` that becomes live once :meth:`bind` receives the server's HTTP client."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._verifier: JwtVerifier | None = None

    def bind(self, http: httpx.AsyncClient) -> None:
        """Attach the lifespan HTTP client (JWKS fetches share it with the register clients)."""
        self._verifier = JwtVerifier(
            JwksCache(http, self._settings.auth_jwks_url),
            issuer=self._settings.auth_issuer or "",
            audience=self._settings.auth_resource_url,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if self._verifier is None:
            return None
        principal = await self._verifier.verify(token)
        if principal is None:
            return None
        return AccessToken(
            token=token,
            client_id=principal.client_id or UNKNOWN_CLIENT,
            scopes=list(principal.scopes),
            expires_at=principal.expires_at,
            resource=self._settings.auth_resource_url,
            subject=principal.subject,
            claims={"iss": principal.issuer},
        )
