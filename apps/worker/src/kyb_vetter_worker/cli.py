"""Command line of the worker.

``python -m kyb_vetter_worker flatfile [--date YYYYMMDD] [--force]``
``python -m kyb_vetter_worker keys issue --principal P --name N | list --principal P | revoke --prefix X``
``python -m kyb_vetter_worker purge``  apply the retention rules (ADR-0022)
"""

import argparse
import asyncio
import logging
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import httpx

from kyb_vetter_core.config import get_settings
from kyb_vetter_core.errors import CoreError
from kyb_vetter_core.retention import purge
from kyb_vetter_core.storage import open_stores
from kyb_vetter_core.telemetry import configure_logging
from kyb_vetter_worker.flatfile import run_flatfile
from kyb_vetter_worker.keys import issue_key, list_keys, revoke_key

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_NOT_PUBLISHED = 3

logger = logging.getLogger(__name__)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kyb_vetter_worker")
    sub = parser.add_subparsers(dest="command", required=True)
    flat = sub.add_parser(
        "flatfile", help="download, verify and publish the daily MF flat file index"
    )
    flat.add_argument("--date", help="file date YYYYMMDD (default: today in Europe/Warsaw)")
    flat.add_argument(
        "--force", action="store_true", help="rebuild even if that day is already published"
    )
    flat.add_argument(
        "--workdir", type=Path, default=None, help="scratch directory (default: temp)"
    )
    keys = sub.add_parser("keys", help="manage REST API keys (needs APP_DATABASE_URL)")
    keys_sub = keys.add_subparsers(dest="action", required=True)
    issue = keys_sub.add_parser("issue", help="create a key; prints it once")
    issue.add_argument(
        "--principal", required=True, help="owner, e.g. the Auth0 sub or client:<name>"
    )
    issue.add_argument("--name", required=True, help="label, e.g. the integration using it")
    listing = keys_sub.add_parser("list", help="list a principal's keys (no secrets)")
    listing.add_argument("--principal", required=True)
    revoke = keys_sub.add_parser("revoke", help="disable a key by its prefix")
    revoke.add_argument("--prefix", required=True)
    sub.add_parser("purge", help="apply retention: old audit rows, counters, expired cache")
    return parser


async def _purge() -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if settings.database_url is None:
        logger.error("purge needs APP_DATABASE_URL")
        return EXIT_USAGE
    async with open_stores(settings) as stores:
        report = await purge(stores, now=datetime.now(tz=UTC))
    logger.info("%s", report)
    return EXIT_OK


async def _keys(args: argparse.Namespace) -> int:
    get_settings.cache_clear()
    settings = get_settings()
    if settings.database_url is None:
        logger.error("keys need APP_DATABASE_URL: an in-memory key store would be lost on exit")
        return EXIT_USAGE
    now = datetime.now(tz=UTC)
    async with open_stores(settings) as stores:
        match args.action:
            case "issue":
                await issue_key(
                    stores.apikeys,
                    principal=args.principal,
                    name=args.name,
                    now=now,
                    out=sys.stdout,
                )
            case "list":
                await list_keys(stores.apikeys, principal=args.principal, out=sys.stdout)
            case _:
                if not await revoke_key(stores.apikeys, prefix=args.prefix, now=now):
                    logger.error("no key with prefix %s", args.prefix)
                    return EXIT_ERROR
    return EXIT_OK


async def _flatfile(date: str | None, force: bool, workdir: Path | None) -> int:
    get_settings.cache_clear()
    settings = get_settings()
    work = workdir or Path(tempfile.mkdtemp(prefix="flatfile-"))
    async with open_stores(settings) as stores, httpx.AsyncClient() as http:
        outcome = await run_flatfile(
            http, settings, stores.blobs, date=date, force=force, workdir=work
        )
    return EXIT_NOT_PUBLISHED if outcome.action == "not_published_yet" else EXIT_OK


def main(argv: list[str]) -> int:
    get_settings.cache_clear()
    configure_logging(get_settings())
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    if args.command == "keys":
        return asyncio.run(_keys(args))
    if args.command == "purge":
        return asyncio.run(_purge())
    try:
        return asyncio.run(_flatfile(args.date, args.force, args.workdir))
    except CoreError as exc:
        logger.error("flat file job failed: %s", exc)
        return EXIT_ERROR
