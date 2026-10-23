"""Who is calling: one principal from an API key or an OAuth bearer token (ADR-0020).

Both credentials resolve to the same identity (the identity provider's
``sub``), so one person shares history and daily budgets across MCP and REST.
A key wins when both are present, and a rejected credential is never retried
with the other one: the caller sent something wrong and should be told so.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
lazy from collections.abc import Callable

from kyb_vetter_core.apikeys import authenticate_api_key

if TYPE_CHECKING:
    from kyb_vetter_core.auth import Principal
    from kyb_vetter_core.storage.ports import ApiKeyStore


class TokenVerifier(Protocol):
    async def verify(self, token: str) -> Principal | None: ...


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Authenticator:
    def __init__(
        self,
        *,
        apikeys: ApiKeyStore,
        jwt: TokenVerifier | None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._apikeys = apikeys
        self._jwt = jwt
        self.now = now

    async def principal(self, *, api_key: str | None, bearer: str | None) -> str | None:
        """The caller's principal, or ``None`` when no valid credential was presented."""
        if api_key is not None and api_key != "":
            record = await authenticate_api_key(self._apikeys, api_key, now=self.now())
            return None if record is None else record.principal
        if bearer is not None and bearer != "" and self._jwt is not None:
            verified = await self._jwt.verify(bearer)
            return None if verified is None else verified.subject
        return None
