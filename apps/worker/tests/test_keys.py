"""Admin CLI for API keys (ADR-0020): issue once in clear, list without secrets, revoke."""

import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection

from kyb_vetter_core.apikeys import authenticate_api_key
from kyb_vetter_core.storage.memory import MemoryApiKeyStore
from kyb_vetter_core.storage.postgres import make_engine
from kyb_vetter_worker.cli import EXIT_ERROR, EXIT_OK, EXIT_USAGE, main
from kyb_vetter_worker.keys import issue_key, list_keys, revoke_key

NOW = datetime(2026, 10, 23, 21, 0, tzinfo=UTC)
ALEMBIC_INI = Path(__file__).resolve().parents[3] / "packages" / "core" / "alembic.ini"
DATABASE_URL = os.environ.get("APP_TEST_DATABASE_URL")


async def test_issue_list_and_revoke() -> None:
    store = MemoryApiKeyStore()
    out = io.StringIO()

    plaintext = await issue_key(store, principal="client:acme", name="erp", now=NOW, out=out)
    prefix = plaintext.split(".")[0]
    assert plaintext in out.getvalue()
    assert await authenticate_api_key(store, plaintext, now=NOW) is not None

    listing = io.StringIO()
    await list_keys(store, principal="client:acme", out=listing)
    assert prefix in listing.getvalue()
    assert "erp" in listing.getvalue()
    assert plaintext not in listing.getvalue()  # secrets are never listed

    assert await revoke_key(store, prefix=prefix, now=NOW) is True
    assert await authenticate_api_key(store, plaintext, now=NOW) is None
    assert await revoke_key(store, prefix="missing0", now=NOW) is False

    again = io.StringIO()
    await list_keys(store, principal="client:acme", out=again)
    assert "revoked" in again.getvalue()
    empty = io.StringIO()
    await list_keys(store, principal="nobody", out=empty)
    assert empty.getvalue() == "no keys\n"


def test_keys_refuse_to_run_without_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    assert main(["keys", "issue", "--principal", "p", "--name", "n"]) == EXIT_USAGE
    assert main(["keys"]) == EXIT_USAGE


def _upgrade(connection: Connection) -> None:
    cfg = Config(str(ALEMBIC_INI))
    cfg.attributes["connection"] = connection
    command.upgrade(cfg, "head")


@pytest.mark.db
async def test_cli_round_trip_against_postgres(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    if DATABASE_URL is None:
        pytest.skip("APP_TEST_DATABASE_URL not set")
    engine = make_engine(DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(_upgrade)
    await engine.dispose()
    monkeypatch.setenv("APP_DATABASE_URL", DATABASE_URL)
    principal = f"client:cli-{NOW.timestamp()}-{os.getpid()}"

    assert await _run(["keys", "issue", "--principal", principal, "--name", "ci"]) == EXIT_OK
    plaintext = capsys.readouterr().out.strip().splitlines()[-1]
    prefix = plaintext.split(".")[0]
    assert await _run(["keys", "list", "--principal", principal]) == EXIT_OK
    assert prefix in capsys.readouterr().out
    assert await _run(["keys", "revoke", "--prefix", prefix]) == EXIT_OK
    assert await _run(["keys", "revoke", "--prefix", prefix + "x"]) == EXIT_ERROR


async def _run(argv: list[str]) -> int:
    """``main`` owns an event loop; run it in a worker thread from this async test."""
    import asyncio

    return await asyncio.to_thread(main, argv)
