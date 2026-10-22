"""Storage ports and their implementations (in-memory, Postgres). See ADR-0013."""

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING
lazy from collections.abc import AsyncGenerator

from kyb_vetter_core.storage.memory import MemoryAuditStore, MemoryCacheStore, MemoryQuotaStore
from kyb_vetter_core.storage.ports import Stores

if TYPE_CHECKING:
    from kyb_vetter_core.config import Settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def open_stores(settings: Settings) -> AsyncGenerator[Stores]:
    """Postgres-backed stores when ``database_url`` is set, in-memory otherwise."""
    if settings.database_url is None:
        logger.warning(
            "no APP_DATABASE_URL: quota, audit and cache are in-memory and lost on restart"
        )
        yield Stores(
            quota=MemoryQuotaStore(),
            audit=MemoryAuditStore(),
            cache=MemoryCacheStore(),
            persistent=False,
        )
        return
    from kyb_vetter_core.storage.postgres import open_postgres_stores

    async with open_postgres_stores(settings.database_url) as stores:
        yield stores


__all__ = ["Stores", "open_stores"]
