from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
import respx

from kyb_vetter_core.errors import NotFoundError, RegistryUnavailableError
from kyb_vetter_core.flatfile.download import archive_url, download_archive

BASE = "https://flat.example/plikplaski"


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


def test_archive_url_pattern() -> None:
    assert archive_url(BASE, "20261023") == f"{BASE}/20261023.7z"
    assert archive_url(BASE + "/", "20261023") == f"{BASE}/20261023.7z"


async def test_download_streams_to_disk(tmp_path: Path, mock_api: respx.MockRouter) -> None:
    body = b"7z\xbc\xaf\x27\x1c" + b"x" * 5000
    mock_api.get(f"{BASE}/20261023.7z").respond(
        200, content=body, headers={"content-length": str(len(body))}
    )

    async with httpx.AsyncClient() as http:
        path = await download_archive(http, BASE, "20261023", tmp_path / "20261023.7z")

    assert path.read_bytes() == body


async def test_missing_day_is_not_found(tmp_path: Path, mock_api: respx.MockRouter) -> None:
    mock_api.get(f"{BASE}/20261023.7z").respond(404)

    async with httpx.AsyncClient() as http:
        with pytest.raises(NotFoundError):
            await download_archive(http, BASE, "20261023", tmp_path / "x.7z")


async def test_truncated_body_is_rejected(tmp_path: Path, mock_api: respx.MockRouter) -> None:
    mock_api.get(f"{BASE}/20261023.7z").respond(
        200, content=b"short", headers={"content-length": "99"}
    )

    async with httpx.AsyncClient() as http:
        with pytest.raises(RegistryUnavailableError, match="truncated"):
            await download_archive(http, BASE, "20261023", tmp_path / "x.7z")
    assert not (tmp_path / "x.7z").exists()


async def test_server_error(tmp_path: Path, mock_api: respx.MockRouter) -> None:
    mock_api.get(f"{BASE}/20261023.7z").respond(503)

    async with httpx.AsyncClient() as http:
        with pytest.raises(RegistryUnavailableError):
            await download_archive(http, BASE, "20261023", tmp_path / "x.7z")


async def test_transport_error_discards_partial_file(
    tmp_path: Path, mock_api: respx.MockRouter
) -> None:
    mock_api.get(f"{BASE}/20261023.7z").mock(side_effect=httpx.ReadError("reset"))

    async with httpx.AsyncClient() as http:
        with pytest.raises(RegistryUnavailableError, match="failed"):
            await download_archive(http, BASE, "20261023", tmp_path / "x.7z")
    assert not (tmp_path / "x.7z.part").exists()
