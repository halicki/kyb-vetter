"""Postgres store tests. Need APP_TEST_DATABASE_URL (see compose.yaml); skipped otherwise.

Without a database the 100% coverage gate cannot pass: run ``docker compose up -d db``
and export ``APP_TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app``.
"""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from kyb_vetter_core.config import Settings
from kyb_vetter_core.storage import Stores, open_stores
from kyb_vetter_core.storage.postgres import (
    PostgresApiKeyStore,
    PostgresAuditStore,
    PostgresCacheStore,
    PostgresQuotaStore,
    make_engine,
)

from .contract import apikey_contract, audit_contract, cache_contract, quota_contract

pytestmark = pytest.mark.db

DATABASE_URL = os.environ.get("APP_TEST_DATABASE_URL")
ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
TABLES = ("quota_counters", "audit_events", "registry_cache", "api_keys")


def _migrate(connection: Connection, target: str) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    if target == "base":
        command.downgrade(cfg, "base")
    else:
        command.upgrade(cfg, "head")


@pytest.fixture
async def sessions() -> AsyncIterator[async_sessionmaker]:
    if DATABASE_URL is None:
        pytest.skip("APP_TEST_DATABASE_URL not set")
    engine = make_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(_migrate, "base")
        await conn.run_sync(_migrate, "head")
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def test_quota_store_contract(sessions: async_sessionmaker) -> None:
    await quota_contract(PostgresQuotaStore(sessions))


async def test_audit_store_contract(sessions: async_sessionmaker) -> None:
    await audit_contract(PostgresAuditStore(sessions))


async def test_cache_store_contract(sessions: async_sessionmaker) -> None:
    await cache_contract(PostgresCacheStore(sessions))


async def test_apikey_store_contract(sessions: async_sessionmaker) -> None:
    await apikey_contract(PostgresApiKeyStore(sessions))


async def test_migrations_round_trip_leaves_a_clean_schema(sessions: async_sessionmaker) -> None:
    async with sessions() as session:
        for table in TABLES:
            assert (await session.scalar(text(f"select count(*) from {table}"))) == 0  # noqa: S608 - fixed names


async def test_open_stores_with_database_url_is_persistent(sessions: async_sessionmaker) -> None:
    assert DATABASE_URL is not None
    async with open_stores(Settings(database_url=DATABASE_URL)) as stores:
        assert isinstance(stores, Stores)
        assert stores.persistent is True
        assert await stores.quota.usage("wl_search", __import__("datetime").date(2026, 1, 1)) == 0
