"""Daily quota guard for the MF white list (ADR-0013).

The registry limits calls per source IP per day and blocks the IP until
midnight when exceeded. A hosted server shares one IP across all users, so
the guard refuses calls *before* the registry would, at a safety threshold
below each official limit. Days follow Europe/Warsaw, like the registry.
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from kyb_vetter_core.clients.whitelist import today_in_warsaw
from kyb_vetter_core.errors import DailyLimitExceededError, QuotaExhaustedError
from kyb_vetter_core.identifiers import validate_bank_account, validate_nip

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping, Sequence

    from kyb_vetter_core.clients.protocols import WhiteListProtocol
    from kyb_vetter_core.models import (
        BankAccountCheck,
        VatBatchResult,
        VatSearchResult,
        VatStatusResult,
    )
    from kyb_vetter_core.storage.ports import QuotaStore

BUCKET_SEARCH = "wl_search"
BUCKET_CHECK = "wl_check"
BUCKET_STATUS = "wl_status"


class Bucket(BaseModel):
    """Official daily ``limit`` and the ``threshold`` at which we stop calling."""

    model_config = ConfigDict(frozen=True)

    limit: int
    threshold: int


DEFAULT_BUCKETS: Mapping[str, Bucket] = {
    BUCKET_SEARCH: Bucket(limit=100, threshold=90),
    BUCKET_CHECK: Bucket(limit=5000, threshold=4800),
    BUCKET_STATUS: Bucket(limit=50_000, threshold=45_000),
}


class QuotaGuard:
    def __init__(
        self,
        store: QuotaStore,
        *,
        buckets: Mapping[str, Bucket] = DEFAULT_BUCKETS,
        today: Callable[[], date] = today_in_warsaw,
    ) -> None:
        self._store = store
        self._buckets = dict(buckets)
        self._today = today

    def with_buckets(self, overrides: Mapping[str, Bucket]) -> QuotaGuard:
        return QuotaGuard(self._store, buckets={**self._buckets, **overrides}, today=self._today)

    async def reserve(self, bucket: str) -> int:
        """Count one call against ``bucket`` or raise :class:`QuotaExhaustedError`."""
        day = self._today()
        cfg = self._buckets[bucket]
        count = await self._store.try_reserve(bucket, day, limit=cfg.threshold)
        if count is None:
            raise QuotaExhaustedError(
                bucket=bucket,
                used=cfg.threshold,
                threshold=cfg.threshold,
                resets_on=day + timedelta(days=1),
            )
        return count

    async def mark_exhausted(self, bucket: str) -> None:
        """The registry reported the IP as blocked: stop calling until tomorrow."""
        await self._store.exhaust(bucket, self._today(), limit=self._buckets[bucket].threshold)

    async def usage(self) -> dict[str, tuple[int, int]]:
        """``{bucket: (used, threshold)}`` for today."""
        day = self._today()
        return {
            name: (await self._store.usage(name, day), cfg.threshold)
            for name, cfg in self._buckets.items()
        }


class GuardedWhiteListClient:
    """Wraps a :class:`WhiteListClient`; every network call is reserved first.

    Input validation still happens inside the wrapped client, after the
    reservation, so a reservation is made only for syntactically valid input:
    validation is run here first to keep the ordering cheap and explicit.
    """

    def __init__(self, inner: WhiteListProtocol, guard: QuotaGuard) -> None:
        self._inner = inner
        self._guard = guard

    async def status(self, nip: str, *, date: date | None = None) -> VatStatusResult:
        validate_nip(nip)
        await self._guard.reserve(BUCKET_STATUS)
        return await self._call(BUCKET_STATUS, self._inner.status(nip, date=date))

    async def search(self, nip: str, *, date: date | None = None) -> VatSearchResult:
        validate_nip(nip)
        await self._guard.reserve(BUCKET_SEARCH)
        return await self._call(BUCKET_SEARCH, self._inner.search(nip, date=date))

    async def search_many(self, nips: Sequence[str], *, date: date | None = None) -> VatBatchResult:
        for nip in nips:
            validate_nip(nip)
        await self._guard.reserve(BUCKET_SEARCH)
        return await self._call(BUCKET_SEARCH, self._inner.search_many(nips, date=date))

    async def check(self, nip: str, account: str, *, date: date | None = None) -> BankAccountCheck:
        validate_nip(nip)
        validate_bank_account(account)
        await self._guard.reserve(BUCKET_CHECK)
        return await self._call(BUCKET_CHECK, self._inner.check(nip, account, date=date))

    async def _call[T](self, bucket: str, awaitable: Awaitable[T]) -> T:
        try:
            return await awaitable
        except DailyLimitExceededError:
            await self._guard.mark_exhausted(bucket)
            raise
