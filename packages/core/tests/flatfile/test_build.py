from pathlib import Path

import pytest

from kyb_vetter_core.flatfile.build import (
    IntegrityError,
    build_index,
    extract_archive,
    verify_sidecar,
)
from kyb_vetter_core.flatfile.hashing import pair_digest
from kyb_vetter_core.flatfile.testing import (
    ACTIVE_PAIRS,
    DATE,
    EXEMPT_PAIRS,
    MASKS,
    TRANSFORMATIONS,
    write_archive,
)


def test_extract_verify_and_build(tmp_path: Path) -> None:
    archive = write_archive(tmp_path)

    json_path, sidecar_path = extract_archive(archive, tmp_path / "out")
    sha = verify_sidecar(json_path, sidecar_path)
    index = build_index(json_path, source_sha512=sha)

    assert json_path.name == f"{DATE}.json"
    assert len(sha) == 128
    assert index.date == DATE
    assert index.transformations == TRANSFORMATIONS
    assert index.source_sha512 == sha
    assert index.counts == (4, 1)
    assert index.masks == tuple(MASKS)
    nip, nrb = ACTIVE_PAIRS[0]
    assert index.lookup(pair_digest(DATE, nip, nrb, transformations=TRANSFORMATIONS)) == "active"
    nip, nrb = EXEMPT_PAIRS[0]
    assert index.lookup(pair_digest(DATE, nip, nrb, transformations=TRANSFORMATIONS)) == "exempt"


def test_corrupt_sidecar_is_rejected(tmp_path: Path) -> None:
    archive = write_archive(tmp_path, corrupt_sidecar=True)
    json_path, sidecar_path = extract_archive(archive, tmp_path / "out")

    with pytest.raises(IntegrityError, match="SHA-512"):
        verify_sidecar(json_path, sidecar_path)


def test_sidecar_must_name_the_json_file(tmp_path: Path) -> None:
    archive = write_archive(tmp_path)
    json_path, sidecar_path = extract_archive(archive, tmp_path / "out")
    sidecar_path.write_text(sidecar_path.read_text().replace(f"{DATE}.json", "other.json"))

    with pytest.raises(IntegrityError, match="names"):
        verify_sidecar(json_path, sidecar_path)


def test_archive_without_expected_entries_is_rejected(tmp_path: Path) -> None:
    import io

    import py7zr

    archive = tmp_path / "bad.7z"
    with py7zr.SevenZipFile(archive, "w") as z:
        z.writef(io.BytesIO(b"{}"), "readme.txt")

    with pytest.raises(IntegrityError, match="entries"):
        extract_archive(archive, tmp_path / "out")


def test_build_rejects_unexpected_header(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        '{"naglowek": {"dataGenerowaniaDanych": "20261023"}, "skrotyPodatnikowCzynnych": [], "skrotyPodatnikowZwolnionych": [], "maski": []}'
    )

    with pytest.raises(IntegrityError, match="liczbaTransformacji"):
        build_index(bad, source_sha512="00" * 64)
