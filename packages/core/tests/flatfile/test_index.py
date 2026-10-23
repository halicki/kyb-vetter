import hashlib

import pytest

from kyb_vetter_core.flatfile.index import PREFIX_BYTES, FlatFileIndex, IndexFormatError

DATE = "20261023"
SHA = "ab" * 64


def digests(seed: str, n: int) -> list[str]:
    return sorted(hashlib.sha512(f"{seed}{i}".encode()).hexdigest() for i in range(n))


def make_index(active: list[str], exempt: list[str], masks: tuple[str, ...] = ()) -> FlatFileIndex:
    return FlatFileIndex.build(
        date=DATE,
        transformations=5000,
        source_sha512=SHA,
        active=active,
        exempt=exempt,
        masks=masks,
    )


def test_lookup_distinguishes_active_exempt_and_unknown() -> None:
    active, exempt = digests("a", 50), digests("e", 20)
    index = make_index(active, exempt, masks=("XX72123370XXXXXXXYYYXXXXXX",))

    assert index.lookup(active[0]) == "active"
    assert index.lookup(active[-1]) == "active"
    assert index.lookup(exempt[7]) == "exempt"
    assert index.lookup(hashlib.sha512(b"nope").hexdigest()) is None
    assert index.counts == (50, 20)
    assert index.masks == ("XX72123370XXXXXXXYYYXXXXXX",)


def test_build_sorts_unsorted_input() -> None:
    active = digests("a", 30)
    index = make_index(list(reversed(active)), [])
    assert all(index.lookup(d) == "active" for d in active)


def test_bytes_round_trip() -> None:
    index = make_index(digests("a", 10), digests("e", 3), masks=("XX10100055YYYXXXXXXXXXXXXX",))

    restored = FlatFileIndex.from_bytes(index.to_bytes())

    assert restored == index
    assert restored.date == DATE
    assert restored.transformations == 5000
    assert restored.source_sha512 == SHA
    assert len(index.to_bytes()) < 13 * PREFIX_BYTES + 400


def test_from_bytes_rejects_other_formats() -> None:
    with pytest.raises(IndexFormatError):
        FlatFileIndex.from_bytes(b"not an index")
    with pytest.raises(IndexFormatError):
        FlatFileIndex.from_bytes(b"KVFF9" + b"\x00" * 20)


def test_lookup_rejects_non_hex_input() -> None:
    index = make_index(digests("a", 2), [])
    with pytest.raises(ValueError, match="128"):
        index.lookup("zz")


def test_from_bytes_rejects_corrupt_header_and_wrong_length() -> None:
    index = make_index(digests("a", 3), [])
    raw = index.to_bytes()
    header_len = int.from_bytes(raw[5:9], "big")
    corrupt = raw[:9] + b"{" * header_len + raw[9 + header_len :]
    with pytest.raises(IndexFormatError, match="header"):
        FlatFileIndex.from_bytes(corrupt)
    with pytest.raises(IndexFormatError, match="length"):
        FlatFileIndex.from_bytes(raw + b"\x00")
