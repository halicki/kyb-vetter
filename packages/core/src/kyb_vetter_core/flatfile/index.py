"""Compact in-memory index of one day's flat file.

Each digest is reduced to its first 16 bytes (the 128-bit prefixes are unique
in practice: 3.7 M entries, collision probability ~1e-26). Entries are kept
sorted in a flat ``bytes`` buffer and looked up by binary search, so the whole
day fits in ~60 MB and a lookup costs ~22 comparisons.

Binary layout (``to_bytes``): ``KVFF1`` magic, 4-byte big-endian header
length, JSON header, then the active and exempt blocks back to back.
"""

import itertools
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

PREFIX_BYTES = 16
DIGEST_HEX_LENGTH = 128
MAGIC = b"KVFF1"

type Status = Literal["active", "exempt"]


class IndexFormatError(ValueError):
    """The bytes are not a flat-file index this code understands."""


def _pack(digests: Iterable[str]) -> bytes:
    prefixes = [bytes.fromhex(d[: PREFIX_BYTES * 2]) for d in digests]
    if any(b < a for a, b in itertools.pairwise(prefixes)):
        prefixes.sort()
    return b"".join(prefixes)


def _contains(block: bytes, prefix: bytes) -> bool:
    lo, hi = 0, len(block) // PREFIX_BYTES
    while lo < hi:
        mid = (lo + hi) // 2
        start = mid * PREFIX_BYTES
        candidate = block[start : start + PREFIX_BYTES]
        if candidate < prefix:
            lo = mid + 1
        elif candidate > prefix:
            hi = mid
        else:
            return True
    return False


@dataclass(frozen=True, slots=True)
class FlatFileIndex:
    date: str
    transformations: int
    source_sha512: str
    active: bytes
    exempt: bytes
    masks: tuple[str, ...]

    @classmethod
    def build(
        cls,
        *,
        date: str,
        transformations: int,
        source_sha512: str,
        active: Iterable[str],
        exempt: Iterable[str],
        masks: Sequence[str],
    ) -> FlatFileIndex:
        return cls(
            date=date,
            transformations=transformations,
            source_sha512=source_sha512,
            active=_pack(active),
            exempt=_pack(exempt),
            masks=tuple(masks),
        )

    @property
    def counts(self) -> tuple[int, int]:
        return len(self.active) // PREFIX_BYTES, len(self.exempt) // PREFIX_BYTES

    def lookup(self, digest_hex: str) -> Status | None:
        if len(digest_hex) != DIGEST_HEX_LENGTH:
            raise ValueError(f"digest must be {DIGEST_HEX_LENGTH} hex characters")
        prefix = bytes.fromhex(digest_hex[: PREFIX_BYTES * 2])
        if _contains(self.active, prefix):
            return "active"
        if _contains(self.exempt, prefix):
            return "exempt"
        return None

    def to_bytes(self) -> bytes:
        header = json.dumps(
            {
                "date": self.date,
                "transformations": self.transformations,
                "source_sha512": self.source_sha512,
                "active_bytes": len(self.active),
                "exempt_bytes": len(self.exempt),
                "masks": list(self.masks),
            },
            separators=(",", ":"),
        ).encode()
        return MAGIC + len(header).to_bytes(4, "big") + header + self.active + self.exempt

    @classmethod
    def from_bytes(cls, data: bytes) -> FlatFileIndex:
        if not data.startswith(MAGIC):
            raise IndexFormatError("unknown index format (bad magic)")
        header_len = int.from_bytes(data[5:9], "big")
        try:
            header = json.loads(data[9 : 9 + header_len])
        except ValueError as exc:
            raise IndexFormatError("corrupt index header") from exc
        start = 9 + header_len
        active_end = start + header["active_bytes"]
        exempt_end = active_end + header["exempt_bytes"]
        if exempt_end != len(data):
            raise IndexFormatError("index length does not match header")
        return cls(
            date=header["date"],
            transformations=header["transformations"],
            source_sha512=header["source_sha512"],
            active=data[start:active_end],
            exempt=data[active_end:exempt_end],
            masks=tuple(header["masks"]),
        )
