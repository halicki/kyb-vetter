"""Client for the Ministry of Finance VAT white list ("Wykaz podatników VAT").

Endpoints (API v1.6.1, ADR-0009):

- ``GET /api2/status/nip/{nip}``                        status only, 50 000 calls/day
- ``GET /api/search/nip/{nip}?date=``                   full entry, 100 calls/day
- ``GET /api/search/nips/{nip,...}?date=``              up to 30 NIPs per call
- ``GET /api/check/nip/{nip}/bank-account/{nrb}?date=`` 5 000 checks/day

Quotas are per source IP and exhausting one blocks the IP until midnight, so
this client never retries on its own except for ``WL-195`` (the registry
refreshed its data mid-request and explicitly asks for one retry). Inputs are
validated locally first so a malformed identifier never costs quota.
"""

import json
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

import httpx

from kyb_vetter_core.errors import (
    DataUpdatedRetryError,
    RegistryError,
    RegistryUnavailableError,
    TooManyIdentifiersError,
    registry_error_from_code,
)
from kyb_vetter_core.identifiers import validate_bank_account, validate_nip
from kyb_vetter_core.models import (
    SOURCE_WHITELIST,
    WARSAW,
    BankAccountCheck,
    VatBatchResult,
    VatSearchResult,
    VatStatusResult,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from kyb_vetter_core.config import Settings

MAX_BATCH_SIZE = 30
_DATE_FORMAT = "%Y-%m-%d"


def today_in_warsaw() -> date:
    """The registry answers "as of a day" in Polish local time."""
    return datetime.now(tz=WARSAW).date()


class WhiteListClient:
    """Thin async client over the white-list API. See module docstring for quotas."""

    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._base_url = settings.mf_base_url
        self._timeout = settings.http_timeout_s
        self._headers = {"User-Agent": settings.user_agent, "Accept": "application/json"}

    async def status(self, nip: str, *, date: date | None = None) -> VatStatusResult:
        """VAT status only (WL2 endpoint, high quota)."""
        clean_nip = validate_nip(nip)
        payload, raw = await self._get(f"/api2/status/nip/{clean_nip}", date or today_in_warsaw())
        return self._parse(VatStatusResult.from_api, payload, raw=raw)

    async def search(self, nip: str, *, date: date | None = None) -> VatSearchResult:
        """Full white-list entry for one NIP; ``subject`` is ``None`` when unknown."""
        clean_nip = validate_nip(nip)
        queried = date or today_in_warsaw()
        payload, raw = await self._get(f"/api/search/nip/{clean_nip}", queried)
        return self._parse(VatSearchResult.from_api, payload, raw=raw, queried_date=queried)

    async def search_many(self, nips: Sequence[str], *, date: date | None = None) -> VatBatchResult:
        """Full entries for up to 30 NIPs in one call (counts as one ``search`` query)."""
        if len(nips) > MAX_BATCH_SIZE:
            raise TooManyIdentifiersError(
                f"at most {MAX_BATCH_SIZE} identifiers per call, got {len(nips)}",
                source=SOURCE_WHITELIST,
            )
        clean = ",".join(validate_nip(n) for n in nips)
        queried = date or today_in_warsaw()
        payload, raw = await self._get(f"/api/search/nips/{clean}", queried)
        return self._parse(VatBatchResult.from_api, payload, raw=raw, queried_date=queried)

    async def check(self, nip: str, account: str, *, date: date | None = None) -> BankAccountCheck:
        """Whether ``account`` is assigned to the active taxpayer ``nip`` as of ``date``."""
        clean_nip = validate_nip(nip)
        clean_account = validate_bank_account(account)
        queried = date or today_in_warsaw()
        payload, raw = await self._get(
            f"/api/check/nip/{clean_nip}/bank-account/{clean_account}", queried
        )
        return self._parse(
            BankAccountCheck.from_api,
            payload,
            nip=clean_nip,
            account=clean_account,
            raw=raw,
            queried_date=queried,
        )

    # --- internals ---------------------------------------------------------

    async def _get(self, path: str, queried: date) -> tuple[Any, bytes]:
        """Perform the request, retrying exactly once on WL-195, and return ``(json, raw)``."""
        try:
            return await self._get_once(path, queried)
        except DataUpdatedRetryError:
            return await self._get_once(path, queried)

    async def _get_once(self, path: str, queried: date) -> tuple[Any, bytes]:
        try:
            response = await self._http.get(
                f"{self._base_url}{path}",
                params={"date": queried.strftime(_DATE_FORMAT)},
                headers=self._headers,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise RegistryUnavailableError(
                f"transport failure: {exc}", source=SOURCE_WHITELIST
            ) from exc
        raw = response.content
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = None
        if response.status_code != httpx.codes.OK:
            raise self._error_from_response(response.status_code, payload)
        return payload, raw

    @staticmethod
    def _error_from_response(status: int, payload: Any) -> RegistryError:
        if isinstance(payload, dict) and "code" in payload:
            return registry_error_from_code(
                str(payload["code"]),
                str(payload.get("message", "")),
                source=SOURCE_WHITELIST,
                http_status=status,
            )
        return RegistryUnavailableError(
            f"unexpected HTTP {status} without a WL error code",
            source=SOURCE_WHITELIST,
            http_status=status,
        )

    @staticmethod
    def _parse[T](factory: Callable[..., T], payload: Any, **kwargs: Any) -> T:
        try:
            return factory(payload, **kwargs)
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryUnavailableError(
                f"unexpected response shape: {exc!r}", source=SOURCE_WHITELIST, http_status=200
            ) from exc
