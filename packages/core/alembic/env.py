"""Alembic environment (async). URL precedence: config.attributes["connection"] (tests),
``-x url=...``, ``APP_DATABASE_URL``, then ``sqlalchemy.url`` from alembic.ini."""

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
lazy from sqlalchemy import Connection

from kyb_vetter_core.storage.postgres import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = context.get_x_argument(as_dictionary=True).get("url") or os.environ.get(
        "APP_DATABASE_URL"
    )
    if url:
        config.set_main_option("sqlalchemy.url", url)
    return config.get_main_option("sqlalchemy.url") or ""


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    _url()
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy."
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:  # tests pass an already-open (sync-adapted) connection
        do_run_migrations(connection)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
