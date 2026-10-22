"""Read-through caches in front of the register clients (ADR-0013).

Registry answers describe "the state as of a day" and the white list is
refreshed once a day, so a response for ``(identifier, queried_date)`` is
stable until the next Warsaw midnight. Cached results keep the original
receipt (request id, hash) and are marked ``from_cache=True``.
"""

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

lazy from pydantic import BaseModel

from kyb_vetter_core.clients.whitelist import today_in_warsaw
from kyb_vetter_core.identifiers import normalize_bank_account, normalize_krs, normalize_nip
from kyb_vetter_core.models import (
    WARSAW,
    BankAccountCheck,
    KrsExtract,
    ReceiptedModel,
    VatBatchResult,
    VatSearchResult,
    VatStatusResult,
)
from kyb_vetter_core.storage.ports import CacheEntry

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from kyb_vetter_core.clients.protocols import KrsProtocol, WhiteListProtocol
    from kyb_vetter_core.storage.ports import CacheStore

SOURCE_SEARCH = "mf-whitelist-search"
SOURCE_CHECK = "mf-whitelist-check"
SOURCE_STATUS = "mf-whitelist-status"
SOURCE_KRS = "krs"
STATUS_TTL = timedelta(hours=1)


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def next_warsaw_midnight(now: datetime) -> datetime:
    local = now.astimezone(WARSAW)
    tomorrow = local.date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=WARSAW)


class _ReadThrough:
    def __init__(
        self, store: CacheStore, now: Callable[[], datetime], today: Callable[[], date]
    ) -> None:
        self._store = store
        self._now = now
        self._today = today

    async def _get[T: ReceiptedModel](
        self, model: type[T], source: str, key: str, queried: date
    ) -> T | None:
        entry = await self._store.get(source, key, queried, now=self._now())
        if entry is None:
            return None
        result = model.model_validate(entry.payload)
        receipt = result.receipt.model_copy(update={"from_cache": True})
        return result.model_copy(update={"receipt": receipt})

    async def _put(
        self, source: str, key: str, queried: date, result: BaseModel, *, ttl: timedelta | None
    ) -> None:
        now = self._now()
        expires = now + ttl if ttl is not None else next_warsaw_midnight(now)
        await self._store.put(
            CacheEntry(
                source=source,
                cache_key=key,
                queried_date=queried,
                payload=result.model_dump(mode="json"),
                fetched_at=now,
                expires_at=expires,
            )
        )


class CachedWhiteListClient(_ReadThrough):
    def __init__(
        self,
        inner: WhiteListProtocol,
        store: CacheStore,
        *,
        now: Callable[[], datetime] = utcnow,
        today: Callable[[], date] = today_in_warsaw,
    ) -> None:
        super().__init__(store, now, today)
        self._inner = inner

    async def status(self, nip: str, *, date: date | None = None) -> VatStatusResult:
        key, queried = normalize_nip(nip), date or self._today()
        cached = await self._get(VatStatusResult, SOURCE_STATUS, key, queried)
        if cached is not None:
            return cached
        result = await self._inner.status(nip, date=date)
        await self._put(SOURCE_STATUS, key, queried, result, ttl=STATUS_TTL)
        return result

    async def search(self, nip: str, *, date: date | None = None) -> VatSearchResult:
        key, queried = normalize_nip(nip), date or self._today()
        cached = await self._get(VatSearchResult, SOURCE_SEARCH, key, queried)
        if cached is not None:
            return cached
        result = await self._inner.search(nip, date=date)
        await self._put(SOURCE_SEARCH, key, queried, result, ttl=None)
        return result

    async def search_many(self, nips: Sequence[str], *, date: date | None = None) -> VatBatchResult:
        """Not cached: batch results carry per-identifier error objects and are rarely repeated."""
        return await self._inner.search_many(nips, date=date)

    async def check(self, nip: str, account: str, *, date: date | None = None) -> BankAccountCheck:
        key = f"{normalize_nip(nip)}:{normalize_bank_account(account)}"
        queried = date or self._today()
        cached = await self._get(BankAccountCheck, SOURCE_CHECK, key, queried)
        if cached is not None:
            return cached
        result = await self._inner.check(nip, account, date=date)
        await self._put(SOURCE_CHECK, key, queried, result, ttl=None)
        return result


class CachedKrsClient(_ReadThrough):
    def __init__(
        self,
        inner: KrsProtocol,
        store: CacheStore,
        *,
        now: Callable[[], datetime] = utcnow,
        today: Callable[[], date] = today_in_warsaw,
    ) -> None:
        super().__init__(store, now, today)
        self._inner = inner

    async def get_extract(self, krs: str) -> KrsExtract:
        key, queried = normalize_krs(krs), self._today()
        cached = await self._get(KrsExtract, SOURCE_KRS, key, queried)
        if cached is not None:
            return cached
        result = await self._inner.get_extract(krs)
        await self._put(SOURCE_KRS, key, queried, result, ttl=None)
        return result


__all__: Sequence[str] = (
    "CachedKrsClient",
    "CachedWhiteListClient",
    "next_warsaw_midnight",
    "utcnow",
)
