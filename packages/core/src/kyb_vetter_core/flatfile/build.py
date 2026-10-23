"""Turn a downloaded archive into a :class:`FlatFileIndex`: extract, verify, stream-parse."""

import hashlib
import logging
from typing import Any
lazy from pathlib import Path

import ijson
import py7zr

from kyb_vetter_core.errors import CoreError
from kyb_vetter_core.flatfile.index import FlatFileIndex

logger = logging.getLogger(__name__)

SIDECAR_SUFFIX = ".sha512sum"
_CHUNK = 1 << 20


class IntegrityError(CoreError):
    """The archive or its contents do not match what the ministry publishes."""


def extract_archive(archive: Path, dest: Path) -> tuple[Path, Path]:
    """Extract ``<date>.json`` and its sidecar; return their paths."""
    dest.mkdir(parents=True, exist_ok=True)
    with py7zr.SevenZipFile(archive, "r") as z:
        names = [str(n) for n in z.getnames()]
        json_names = [n for n in names if n.endswith(".json")]
        sidecar_names = [n for n in names if n.endswith(SIDECAR_SUFFIX)]
        if len(json_names) != 1 or len(sidecar_names) != 1:
            raise IntegrityError(f"unexpected archive entries: {names}")
        z.extract(path=dest, targets=[json_names[0], sidecar_names[0]])
    return dest / json_names[0], dest / sidecar_names[0]


def verify_sidecar(json_path: Path, sidecar_path: Path) -> str:
    """Check the JSON against the published SHA-512 and return the digest."""
    expected, _, named = sidecar_path.read_text().strip().partition(" ")
    if named.strip() != json_path.name:
        raise IntegrityError(f"sidecar names {named.strip()!r}, expected {json_path.name!r}")
    digest = hashlib.sha512()
    with json_path.open("rb") as f:
        while chunk := f.read(_CHUNK):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected.lower():
        raise IntegrityError("SHA-512 of the JSON does not match the published sidecar")
    return actual


def build_index(json_path: Path, *, source_sha512: str) -> FlatFileIndex:
    """Stream the 500 MB JSON once; keep 16-byte prefixes and the masks."""
    header: dict[str, Any] = {}
    active: list[str] = []
    exempt: list[str] = []
    masks: list[str] = []
    targets = {
        "skrotyPodatnikowCzynnych.item": active,
        "skrotyPodatnikowZwolnionych.item": exempt,
        "maski.item": masks,
    }
    with json_path.open("rb") as f:
        for prefix, event, value in ijson.parse(f):
            if prefix.startswith("naglowek.") and event in {"string", "number"}:
                header[prefix.removeprefix("naglowek.")] = value
            elif event == "string" and prefix in targets:
                targets[prefix].append(value)
    try:
        date = str(header["dataGenerowaniaDanych"])
        transformations = int(header["liczbaTransformacji"])
    except (KeyError, ValueError) as exc:
        raise IntegrityError(
            f"header lacks dataGenerowaniaDanych/liczbaTransformacji: {exc!r}"
        ) from exc
    logger.info(
        "flat file %s: %d active, %d exempt, %d masks", date, len(active), len(exempt), len(masks)
    )
    return FlatFileIndex.build(
        date=date,
        transformations=transformations,
        source_sha512=source_sha512,
        active=active,
        exempt=exempt,
        masks=masks,
    )
