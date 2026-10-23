"""Daily job: fetch the ministry's flat file, verify it, publish a compact index (ADR-0016)."""

import asyncio
import json
import logging
import shutil
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal
lazy from pathlib import Path

from kyb_vetter_core.clients.whitelist import today_in_warsaw
from kyb_vetter_core.errors import NotFoundError
from kyb_vetter_core.flatfile.build import build_index, extract_archive, verify_sidecar
from kyb_vetter_core.flatfile.download import download_archive
from kyb_vetter_core.flatfile.provider import LATEST_KEY, index_key, latest_manifest

if TYPE_CHECKING:
    import httpx

    from kyb_vetter_core.config import Settings
    from kyb_vetter_core.storage.ports import BlobStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlatFileOutcome:
    date: str
    action: Literal["published", "skipped", "not_published_yet"]
    active: int = 0
    exempt: int = 0
    masks: int = 0


async def run_flatfile(
    http: httpx.AsyncClient,
    settings: Settings,
    blobs: BlobStore,
    *,
    date: str | None,
    force: bool,
    workdir: Path,
) -> FlatFileOutcome:
    day = date or today_in_warsaw().strftime("%Y%m%d")
    manifest_raw = await blobs.get(LATEST_KEY)
    if manifest_raw is not None and not force:
        current = json.loads(manifest_raw).get("date")
        if current == day:
            logger.info("flat file %s already published, nothing to do", day)
            return FlatFileOutcome(date=day, action="skipped")
    await asyncio.to_thread(workdir.mkdir, parents=True, exist_ok=True)
    archive = workdir / f"{day}.7z"
    started = time.monotonic()
    try:
        try:
            await download_archive(http, settings.mf_flatfile_base_url, day, archive)
        except NotFoundError:
            logger.warning("flat file %s is not published yet", day)
            return FlatFileOutcome(date=day, action="not_published_yet")
        logger.info(
            "downloaded %s (%d MB) in %.0fs",
            archive.name,
            archive.stat().st_size >> 20,
            time.monotonic() - started,
        )
        json_path, sidecar_path = extract_archive(archive, workdir / "extract")
        sha = verify_sidecar(json_path, sidecar_path)
        index = build_index(json_path, source_sha512=sha)
        await blobs.put(index_key(index.date), index.to_bytes())
        await blobs.put(LATEST_KEY, json.dumps(latest_manifest(index)).encode())
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    active, exempt = index.counts
    logger.info(
        "published flat file index %s: %d active, %d exempt, %d masks in %.0fs",
        index.date,
        active,
        exempt,
        len(index.masks),
        time.monotonic() - started,
    )
    return FlatFileOutcome(
        date=index.date, action="published", active=active, exempt=exempt, masks=len(index.masks)
    )
