"""Download one day's archive (about 250 MB) to disk, streaming."""

lazy from pathlib import Path

import httpx

from kyb_vetter_core.errors import NotFoundError, RegistryUnavailableError

SOURCE = "mf-flat-file"
_CHUNK = 1 << 20


def archive_url(base_url: str, date: str) -> str:
    return f"{base_url.rstrip('/')}/{date}.7z"


async def download_archive(http: httpx.AsyncClient, base_url: str, date: str, dest: Path) -> Path:
    """Stream ``<date>.7z`` to ``dest`` (written as ``.part`` first, renamed when complete)."""
    url = archive_url(base_url, date)
    tmp = dest.with_name(dest.name + ".part")
    try:
        async with http.stream("GET", url, timeout=httpx.Timeout(60.0, read=600.0)) as response:
            if response.status_code == httpx.codes.NOT_FOUND:
                raise NotFoundError(f"no flat file for {date}", source=SOURCE, http_status=404)
            if response.status_code != httpx.codes.OK:
                raise RegistryUnavailableError(
                    f"flat file server answered HTTP {response.status_code}",
                    source=SOURCE,
                    http_status=response.status_code,
                )
            expected = int(response.headers.get("content-length", "0") or 0)
            written = 0
            with tmp.open("wb") as f:
                async for chunk in response.aiter_bytes(_CHUNK):
                    f.write(chunk)
                    written += len(chunk)
    except httpx.HTTPError as exc:
        _discard(tmp)
        raise RegistryUnavailableError(f"flat file download failed: {exc}", source=SOURCE) from exc
    except RegistryUnavailableError:
        _discard(tmp)
        raise
    if expected and written != expected:
        _discard(tmp)
        raise RegistryUnavailableError(
            f"flat file download truncated: {written} of {expected} bytes", source=SOURCE
        )
    tmp.replace(dest)
    return dest


def _discard(tmp: Path) -> None:
    tmp.unlink(missing_ok=True)
