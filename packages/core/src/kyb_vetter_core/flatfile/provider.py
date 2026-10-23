"""Serve the newest published index to the running service, refreshing after midnight."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
lazy from collections.abc import Callable

from kyb_vetter_core.flatfile.index import FlatFileIndex, IndexFormatError

if TYPE_CHECKING:
    from kyb_vetter_core.storage.ports import BlobStore

logger = logging.getLogger(__name__)

LATEST_KEY = "flatfile/latest.json"


def index_key(date: str) -> str:
    return f"flatfile/{date}.idx"


def latest_manifest(index: FlatFileIndex) -> dict[str, Any]:
    active, exempt = index.counts
    return {
        "date": index.date,
        "object": index_key(index.date),
        "source_sha512": index.source_sha512,
        "transformations": index.transformations,
        "active": active,
        "exempt": exempt,
        "masks": len(index.masks),
    }


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class FlatFileProvider:
    def __init__(
        self,
        blobs: BlobStore,
        *,
        now: Callable[[], datetime] = utcnow,
        refresh_every: timedelta = timedelta(minutes=15),
    ) -> None:
        self._blobs = blobs
        self._now = now
        self._refresh_every = refresh_every
        self._index: FlatFileIndex | None = None
        self._checked_at: datetime | None = None

    async def current(self) -> FlatFileIndex | None:
        """The loaded index; re-reads the manifest at most every ``refresh_every``."""
        now = self._now()
        if self._checked_at is not None and now - self._checked_at < self._refresh_every:
            return self._index
        self._checked_at = now
        try:
            raw = await self._blobs.get(LATEST_KEY)
            if raw is None:
                return self._index
            manifest = json.loads(raw)
            date = str(manifest["date"])
            if self._index is not None and self._index.date == date:
                return self._index
            data = await self._blobs.get(str(manifest["object"]))
            if data is None:
                logger.warning(
                    "flat file manifest points at a missing object %s", manifest["object"]
                )
                return self._index
            self._index = FlatFileIndex.from_bytes(data)
            logger.info("flat file index loaded for %s (%s)", date, self._index.counts)
        except (ValueError, KeyError, IndexFormatError) as exc:
            logger.warning("flat file manifest/index unreadable, keeping previous: %r", exc)
        return self._index
