"""Storage ports and their implementations (in-memory, Postgres). See ADR-0013."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING
lazy from collections.abc import AsyncGenerator

from kyb_vetter_core.storage.blobs import FilesystemBlobStore, MemoryBlobStore
from kyb_vetter_core.storage.memory import MemoryAuditStore, MemoryCacheStore, MemoryQuotaStore
from kyb_vetter_core.storage.ports import Stores

if TYPE_CHECKING:
    from kyb_vetter_core.config import Settings
    from kyb_vetter_core.storage.ports import BlobStore

logger = logging.getLogger(__name__)


@asynccontextmanager
async def open_stores(settings: Settings) -> AsyncGenerator[Stores]:
    """Postgres-backed stores when ``database_url`` is set, in-memory otherwise.

    Blobs (flat-file indexes) go to GCS when ``flatfile_bucket`` is set, to a
    directory when ``flatfile_dir`` is set, and to process memory otherwise.
    """
    blobs: BlobStore
    if settings.flatfile_bucket is not None:
        from kyb_vetter_core.storage.gcs import GcsBlobStore

        blobs = GcsBlobStore(settings.flatfile_bucket)
    elif settings.flatfile_dir is not None:
        blobs = FilesystemBlobStore(Path(settings.flatfile_dir))
    else:
        blobs = MemoryBlobStore()
    if settings.database_url is None:
        logger.warning(
            "no APP_DATABASE_URL: quota, audit and cache are in-memory and lost on restart"
        )
        yield Stores(
            quota=MemoryQuotaStore(),
            audit=MemoryAuditStore(),
            cache=MemoryCacheStore(),
            blobs=blobs,
            persistent=False,
        )
        return
    from kyb_vetter_core.storage.postgres import open_postgres_stores

    async with open_postgres_stores(settings.database_url, blobs=blobs) as stores:
        yield stores


__all__ = ["Stores", "open_stores"]
