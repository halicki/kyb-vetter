"""Data retention and housekeeping (ADR-0022).

Audit rows are proof of a verification and keep their value for tax purposes
for five years counted from the end of the year of the event, so a row from
year Y is purged on or after 1 January of Y+6. Quota counters are only
meaningful for their day; cache rows only until they expire. CEIDG data
(natural persons) is never stored, so nothing here touches personal data
beyond the register text in audit results.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, override

if TYPE_CHECKING:
    from kyb_vetter_core.storage.ports import Stores

AUDIT_RETENTION_YEARS = 5
QUOTA_COUNTER_RETENTION_DAYS = 7


def audit_cutoff(now: datetime) -> datetime:
    """Rows with ``ts`` before this instant are older than the retention period."""
    return datetime(now.year - AUDIT_RETENTION_YEARS, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class PurgeReport:
    audit_events: int
    quota_counters: int
    cache_entries: int

    @override
    def __str__(self) -> str:
        return (
            f"purged audit_events={self.audit_events} quota_counters={self.quota_counters} "
            f"cache_entries={self.cache_entries}"
        )


async def purge(stores: Stores, *, now: datetime) -> PurgeReport:
    """Apply the retention rules once; returns how many rows each store dropped."""
    return PurgeReport(
        audit_events=await stores.audit.purge_before(audit_cutoff(now)),
        quota_counters=await stores.quota.purge_before(
            (now - timedelta(days=QUOTA_COUNTER_RETENTION_DAYS)).date()
        ),
        cache_entries=await stores.cache.purge_expired(now),
    )
