"""Per-user daily limits (ADR-0019).

A product limit, independent of the ministry's per-IP quota (:mod:`quota`):
each principal may call each tool a fixed number of times per Europe/Warsaw
day, cache hits included. Counters reuse the atomic :class:`QuotaStore`
under namespaced buckets, so no schema change is needed. A limit of ``0``
means unlimited (local stdio runs, tests).
"""

from datetime import date, timedelta
from typing import TYPE_CHECKING
lazy from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

from kyb_vetter_core.clients.whitelist import today_in_warsaw
from kyb_vetter_core.config import DEFAULT_USER_LIMIT_CHECK, DEFAULT_USER_LIMIT_VERIFY
from kyb_vetter_core.errors import UserLimitExceededError

if TYPE_CHECKING:
    from kyb_vetter_core.config import Settings
    from kyb_vetter_core.storage.ports import QuotaStore

TOOL_VERIFY_COMPANY = "verify_company"
TOOL_CHECK_BANK_ACCOUNT = "check_bank_account"


def user_bucket(principal: str, tool: str) -> str:
    """Counter key: ``user:<principal>:<tool>`` (principals never contain ``:``-sensitive parsing)."""
    return f"user:{principal}:{tool}"


class UserLimits(BaseModel):
    """Daily call budget per principal and tool; ``0`` disables the limit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verify_company: int = DEFAULT_USER_LIMIT_VERIFY
    check_bank_account: int = DEFAULT_USER_LIMIT_CHECK

    @classmethod
    def from_settings(cls, settings: Settings) -> UserLimits:
        return cls(
            verify_company=settings.user_daily_limit_verify,
            check_bank_account=settings.user_daily_limit_check,
        )

    def limit_for(self, tool: str) -> int:
        match tool:
            case "verify_company":
                return self.verify_company
            case "check_bank_account":
                return self.check_bank_account
        raise ValueError(f"no per-user limit is defined for tool {tool!r}")


class UserLimiter:
    def __init__(
        self,
        store: QuotaStore,
        *,
        limits: UserLimits | None = None,
        today: Callable[[], date] = today_in_warsaw,
    ) -> None:
        self._store = store
        self._limits = limits if limits is not None else UserLimits()
        self._today = today

    async def reserve(self, principal: str, tool: str) -> int:
        """Count one call of ``tool`` by ``principal``; ``0`` when unlimited.

        Raises :class:`UserLimitExceededError` once the day's budget is used up.
        """
        limit = self._limits.limit_for(tool)
        if limit == 0:
            return 0
        day = self._today()
        count = await self._store.try_reserve(user_bucket(principal, tool), day, limit=limit)
        if count is None:
            raise UserLimitExceededError(tool=tool, limit=limit, resets_on=day + timedelta(days=1))
        return count
