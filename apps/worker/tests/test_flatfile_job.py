import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from kyb_vetter_core.config import Settings
from kyb_vetter_core.flatfile.provider import LATEST_KEY, index_key
from kyb_vetter_core.flatfile.testing import DATE, write_archive
from kyb_vetter_core.storage.blobs import FilesystemBlobStore
from kyb_vetter_worker.cli import main
from kyb_vetter_worker.flatfile import FlatFileOutcome, run_flatfile

BASE = "https://flat.example/plikplaski"


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def archive_bytes(tmp_path: Path) -> bytes:
    return write_archive(tmp_path / "src").read_bytes()


async def test_run_downloads_verifies_builds_and_publishes(
    tmp_path: Path, mock_api: respx.MockRouter, archive_bytes: bytes
) -> None:
    mock_api.get(f"{BASE}/{DATE}.7z").respond(200, content=archive_bytes)
    blobs = FilesystemBlobStore(tmp_path / "blobs")
    settings = Settings(mf_flatfile_base_url=BASE)

    async with httpx.AsyncClient() as http:
        outcome = await run_flatfile(
            http, settings, blobs, date=DATE, force=False, workdir=tmp_path / "work"
        )

    assert outcome == FlatFileOutcome(date=DATE, action="published", active=4, exempt=1, masks=2)
    manifest = json.loads((await blobs.get(LATEST_KEY)) or b"{}")
    assert manifest["date"] == DATE
    assert manifest["object"] == index_key(DATE)
    assert await blobs.exists(index_key(DATE))
    assert not list((tmp_path / "work").glob("*.7z"))  # downloads are cleaned up


async def test_run_skips_when_latest_is_already_that_day(
    tmp_path: Path, mock_api: respx.MockRouter, archive_bytes: bytes
) -> None:
    route = mock_api.get(f"{BASE}/{DATE}.7z").respond(200, content=archive_bytes)
    blobs = FilesystemBlobStore(tmp_path / "blobs")
    settings = Settings(mf_flatfile_base_url=BASE)
    async with httpx.AsyncClient() as http:
        await run_flatfile(http, settings, blobs, date=DATE, force=False, workdir=tmp_path / "work")
        skipped = await run_flatfile(
            http, settings, blobs, date=DATE, force=False, workdir=tmp_path / "work"
        )
        forced = await run_flatfile(
            http, settings, blobs, date=DATE, force=True, workdir=tmp_path / "work"
        )

    assert skipped.action == "skipped"
    assert forced.action == "published"
    assert route.call_count == 2


async def test_run_reports_missing_day(tmp_path: Path, mock_api: respx.MockRouter) -> None:
    mock_api.get(f"{BASE}/{DATE}.7z").respond(404)
    blobs = FilesystemBlobStore(tmp_path / "blobs")
    settings = Settings(mf_flatfile_base_url=BASE)

    async with httpx.AsyncClient() as http:
        outcome = await run_flatfile(
            http, settings, blobs, date=DATE, force=False, workdir=tmp_path / "work"
        )

    assert outcome.action == "not_published_yet"
    assert await blobs.get(LATEST_KEY) is None


async def test_run_rejects_corrupt_archive(tmp_path: Path, mock_api: respx.MockRouter) -> None:
    from kyb_vetter_core.flatfile.build import IntegrityError

    bad = write_archive(tmp_path / "src", corrupt_sidecar=True).read_bytes()
    mock_api.get(f"{BASE}/{DATE}.7z").respond(200, content=bad)
    blobs = FilesystemBlobStore(tmp_path / "blobs")

    async with httpx.AsyncClient() as http:
        with pytest.raises(IntegrityError):
            await run_flatfile(
                http,
                Settings(mf_flatfile_base_url=BASE),
                blobs,
                date=DATE,
                force=False,
                workdir=tmp_path / "work",
            )
    assert await blobs.get(LATEST_KEY) is None


def test_cli_publishes_into_the_configured_directory(
    tmp_path: Path,
    mock_api: respx.MockRouter,
    archive_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_api.get(f"{BASE}/{DATE}.7z").respond(200, content=archive_bytes)
    monkeypatch.setenv("APP_FLATFILE_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("APP_MF_FLATFILE_BASE_URL", BASE)
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)

    assert main(["flatfile", "--date", DATE, "--workdir", str(tmp_path / "work")]) == 0
    assert (tmp_path / "blobs" / "flatfile" / "latest.json").exists()


def test_cli_exit_codes(
    tmp_path: Path, mock_api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    mock_api.get(f"{BASE}/{DATE}.7z").respond(404)
    monkeypatch.setenv("APP_FLATFILE_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("APP_MF_FLATFILE_BASE_URL", BASE)

    assert (
        main(["flatfile", "--date", DATE, "--workdir", str(tmp_path / "work")]) == 3
    )  # not published yet
    mock_api.get(f"{BASE}/{DATE}.7z").respond(503)
    assert main(["flatfile", "--date", DATE, "--workdir", str(tmp_path / "work")]) == 1
    assert main(["nonsense"]) == 2


async def test_run_replaces_an_older_day(
    tmp_path: Path, mock_api: respx.MockRouter, archive_bytes: bytes
) -> None:
    older = write_archive(tmp_path / "older", date="20261001").read_bytes()
    mock_api.get(f"{BASE}/20261001.7z").respond(200, content=older)
    mock_api.get(f"{BASE}/{DATE}.7z").respond(200, content=archive_bytes)
    blobs = FilesystemBlobStore(tmp_path / "blobs")
    settings = Settings(mf_flatfile_base_url=BASE)

    async with httpx.AsyncClient() as http:
        first = await run_flatfile(
            http, settings, blobs, date="20261001", force=False, workdir=tmp_path / "w1"
        )
        second = await run_flatfile(
            http, settings, blobs, date=DATE, force=False, workdir=tmp_path / "w2"
        )

    assert (first.action, second.action) == ("published", "published")
    assert json.loads((await blobs.get(LATEST_KEY)) or b"{}")["date"] == DATE
