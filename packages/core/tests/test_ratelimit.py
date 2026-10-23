"""Per-user daily limits (ADR-0019): product limits independent of the MF quota guard."""

from datetime import date

import pytest

from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import UserLimitExceededError
from kyb_vetter_core.ratelimit import UserLimiter, UserLimits, user_bucket
from kyb_vetter_core.storage.memory import MemoryQuotaStore
from kyb_vetter_core.verification import TOOL_CHECK_BANK_ACCOUNT, TOOL_VERIFY_COMPANY

TODAY = date(2026, 10, 23)


def test_default_limits_and_settings_mapping() -> None:
    limits = UserLimits()
    assert limits.limit_for(TOOL_VERIFY_COMPANY) == 200
    assert limits.limit_for(TOOL_CHECK_BANK_ACCOUNT) == 500
    custom = UserLimits.from_settings(Settings(user_daily_limit_verify=3, user_daily_limit_check=0))
    assert (custom.verify_company, custom.check_bank_account) == (3, 0)
    with pytest.raises(ValueError, match="verification_history"):
        limits.limit_for("verification_history")


def test_user_bucket_is_namespaced_per_principal_and_tool() -> None:
    assert user_bucket("auth0|alice", TOOL_VERIFY_COMPANY) == "user:auth0|alice:verify_company"


async def test_limiter_refuses_above_the_daily_limit() -> None:
    limiter = UserLimiter(
        MemoryQuotaStore(), limits=UserLimits(verify_company=2), today=lambda: TODAY
    )

    assert await limiter.reserve("alice", TOOL_VERIFY_COMPANY) == 1
    assert await limiter.reserve("alice", TOOL_VERIFY_COMPANY) == 2
    with pytest.raises(UserLimitExceededError) as excinfo:
        await limiter.reserve("alice", TOOL_VERIFY_COMPANY)

    assert excinfo.value.tool == TOOL_VERIFY_COMPANY
    assert excinfo.value.limit == 2
    assert excinfo.value.resets_on == date(2026, 10, 24)
    assert "midnight" in str(excinfo.value).lower()


async def test_limits_are_separate_per_user_tool_and_day() -> None:
    store = MemoryQuotaStore()
    today = {"d": TODAY}
    limiter = UserLimiter(
        store, limits=UserLimits(verify_company=1, check_bank_account=1), today=lambda: today["d"]
    )
    await limiter.reserve("alice", TOOL_VERIFY_COMPANY)

    assert await limiter.reserve("bob", TOOL_VERIFY_COMPANY) == 1
    assert await limiter.reserve("alice", TOOL_CHECK_BANK_ACCOUNT) == 1
    with pytest.raises(UserLimitExceededError):
        await limiter.reserve("alice", TOOL_VERIFY_COMPANY)
    today["d"] = date(2026, 10, 24)
    assert await limiter.reserve("alice", TOOL_VERIFY_COMPANY) == 1


async def test_zero_means_unlimited_and_touches_no_counter() -> None:
    store = MemoryQuotaStore()
    limiter = UserLimiter(store, limits=UserLimits(verify_company=0), today=lambda: TODAY)
    for _ in range(3):
        assert await limiter.reserve("alice", TOOL_VERIFY_COMPANY) == 0
    assert await store.usage(user_bucket("alice", TOOL_VERIFY_COMPANY), TODAY) == 0
