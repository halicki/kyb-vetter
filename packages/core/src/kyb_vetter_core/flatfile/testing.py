"""Tiny but structurally faithful flat-file archives for tests (core, worker, evals)."""

import hashlib
import io
import json
lazy from pathlib import Path

import py7zr

from kyb_vetter_core.flatfile.hashing import nip_digest, pair_digest

DATE = "20261023"
TRANSFORMATIONS = 7  # small on purpose; the real file uses 5000
ACTIVE_PAIRS = [
    ("5451726954", "82114020040000340276776163"),
    ("1234563218", "61109010140000071219812874"),
]
EXEMPT_PAIRS = [("7740001454", "61109010140000071219812874")]
NIP_ONLY_ACTIVE = ["1854510877"]
MASKS = ["XX72123370XXXXXXXYYYXXXXXX", "XX10900000YYYYYYYYYYYYXXXX"]
VIRTUAL_ACTIVE = [("1134679109", "20721233708680000022663112")]  # matched through MASKS[0]


def flat_file_json(date: str = DATE) -> dict[str, object]:
    from kyb_vetter_core.flatfile.hashing import masked_account

    active = [pair_digest(date, n, a, transformations=TRANSFORMATIONS) for n, a in ACTIVE_PAIRS]
    active += [nip_digest(date, n, transformations=TRANSFORMATIONS) for n in NIP_ONLY_ACTIVE]
    active += [
        pair_digest(date, n, masked_account(MASKS[0], a), transformations=TRANSFORMATIONS)
        for n, a in VIRTUAL_ACTIVE
    ]
    exempt = [pair_digest(date, n, a, transformations=TRANSFORMATIONS) for n, a in EXEMPT_PAIRS]
    return {
        "naglowek": {
            "dataGenerowaniaDanych": date,
            "liczbaTransformacji": str(TRANSFORMATIONS),
            "schemat": "RRRRMMDDNNNNNNNNNNBBBBBBBBBBBBBBBBBBBBBBBBBB lub RRRRMMDDNNNNNNNNNN",
        },
        "skrotyPodatnikowCzynnych": sorted(active),
        "skrotyPodatnikowZwolnionych": sorted(exempt),
        "maski": MASKS,
    }


def write_archive(directory: Path, *, corrupt_sidecar: bool = False, date: str = DATE) -> Path:
    payload = json.dumps(flat_file_json(date), indent=2).encode()
    digest = hashlib.sha512(payload).hexdigest()
    if corrupt_sidecar:
        digest = "0" * 128
    sidecar = f"{digest}  {date}.json\n".encode()
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / f"{date}.7z"
    with py7zr.SevenZipFile(archive, "w") as z:
        z.writef(io.BytesIO(payload), f"{date}.json")
        z.writef(io.BytesIO(sidecar), f"{date}.json.sha512sum")
    return archive
