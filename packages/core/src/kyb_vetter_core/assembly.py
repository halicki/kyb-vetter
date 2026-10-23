"""Composition root: wires clients, guard, caches and audit into a service.

Order matters: ``Cached(Guarded(Client))`` so that a cache hit never spends
registry quota (ADR-0013).
"""

from typing import TYPE_CHECKING
lazy from collections.abc import Callable
lazy from datetime import date

from kyb_vetter_core.audit import AuditRecorder
from kyb_vetter_core.cache import CachedKrsClient, CachedWhiteListClient
from kyb_vetter_core.clients.krs import KrsClient
from kyb_vetter_core.clients.whitelist import WhiteListClient, today_in_warsaw
from kyb_vetter_core.quota import GuardedWhiteListClient, QuotaGuard
from kyb_vetter_core.ratelimit import UserLimiter, UserLimits
from kyb_vetter_core.verification import VerificationService
lazy from kyb_vetter_core.flatfile.provider import FlatFileProvider

if TYPE_CHECKING:
    import httpx

    from kyb_vetter_core.config import Settings
    from kyb_vetter_core.storage import Stores


def build_verification_service(
    http: httpx.AsyncClient,
    settings: Settings,
    stores: Stores,
    *,
    today: Callable[[], date] = today_in_warsaw,
    flatfile: FlatFileProvider | None = None,
) -> VerificationService:
    guard = QuotaGuard(stores.quota, today=today)
    whitelist = CachedWhiteListClient(
        GuardedWhiteListClient(WhiteListClient(http, settings), guard), stores.cache, today=today
    )
    krs = CachedKrsClient(KrsClient(http, settings), stores.cache, today=today)
    return VerificationService(
        whitelist,
        krs,
        audit=AuditRecorder(stores.audit),
        persistent=stores.persistent,
        flatfile=flatfile if flatfile is not None else FlatFileProvider(stores.blobs),
        limiter=UserLimiter(stores.quota, limits=UserLimits.from_settings(settings), today=today),
    )
