"""Client for the National Court Register (KRS) open API.

``GET /api/krs/OdpisAktualny/{krs}?rejestr=P|S&format=json`` returns the
current extract. ``P`` is the register of entrepreneurs, ``S`` the register of
associations, foundations and similar bodies. The API answers 404 (RFC 7807
body) for an unknown number in the chosen register, so the client tries ``P``
first and falls back to ``S``. Unofficial guidance is about two requests per
second; one retry on transport failures or 5xx is the only automatic repeat.
"""

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from kyb_vetter_core.errors import NotFoundError, RegistryError, RegistryUnavailableError
from kyb_vetter_core.identifiers import validate_krs
from kyb_vetter_core.models import SOURCE_KRS, KrsExtract

if TYPE_CHECKING:
    from kyb_vetter_core.config import Settings

REGISTERS = ("P", "S")


def now_utc() -> datetime:
    return datetime.now(tz=UTC)


class KrsClient:
    """Thin async client over the KRS API. See module docstring."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._base_url = settings.krs_base_url
        self._timeout = settings.http_timeout_s
        self._headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}

    async def get_extract(self, krs: str) -> KrsExtract:
        """Current extract for ``krs``; raises :class:`NotFoundError` when absent from both registers."""
        clean = validate_krs(krs)
        last_not_found: NotFoundError | None = None
        for register in REGISTERS:
            try:
                payload, raw = await self._get(clean, register)
            except NotFoundError as exc:
                last_not_found = exc
                continue
            return self._parse(payload, raw)
        assert last_not_found is not None  # noqa: S101 - loop always sets it before falling through
        raise last_not_found

    # --- internals ---------------------------------------------------------

    async def _get(self, krs: str, register: str) -> tuple[Any, bytes]:
        """Perform the request, retrying once on transport failure or 5xx."""
        try:
            return await self._get_once(krs, register)
        except RegistryUnavailableError as first:
            if first.http_status is not None and first.http_status < 500:
                raise
            try:
                return await self._get_once(krs, register)
            except RegistryUnavailableError as second:
                raise second from first

    async def _get_once(self, krs: str, register: str) -> tuple[Any, bytes]:
        try:
            response = await self._http.get(
                f"{self._base_url}/api/krs/OdpisAktualny/{krs}",
                params={"rejestr": register, "format": "json"},
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise RegistryUnavailableError(f"transport failure: {exc}", source=SOURCE_KRS) from exc
        raw = response.content
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        status = response.status_code
        if status == httpx.codes.NOT_FOUND:
            raise NotFoundError(
                f"KRS {krs} not found in register {register}", source=SOURCE_KRS, http_status=status
            )
        if status >= 500:
            raise RegistryUnavailableError(f"HTTP {status}", source=SOURCE_KRS, http_status=status)
        if status != httpx.codes.OK:
            title = payload.get("title", "") if isinstance(payload, dict) else ""
            raise RegistryError(
                f"HTTP {status} {title}".strip(), source=SOURCE_KRS, http_status=status
            )
        if payload is None:
            raise RegistryUnavailableError("non-JSON body", source=SOURCE_KRS, http_status=status)
        return payload, raw

    @staticmethod
    def _parse(payload: Any, raw: bytes) -> KrsExtract:
        try:
            return KrsExtract.from_api(payload, raw=raw, fetched_at=now_utc())
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryUnavailableError(
                f"unexpected response shape: {exc!r}", source=SOURCE_KRS, http_status=200
            ) from exc
