"""Command line of the worker: ``python -m kyb_vetter_worker flatfile [--date YYYYMMDD] [--force]``."""

import argparse
import asyncio
import logging
import sys
import tempfile
from pathlib import Path

import httpx

from kyb_vetter_core.config import get_settings
from kyb_vetter_core.errors import CoreError
from kyb_vetter_core.storage import open_stores
from kyb_vetter_worker.flatfile import run_flatfile

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
    return parser


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
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK
    try:
        return asyncio.run(_flatfile(args.date, args.force, args.workdir))
    except CoreError as exc:
        logger.error("flat file job failed: %s", exc)
        return EXIT_ERROR
