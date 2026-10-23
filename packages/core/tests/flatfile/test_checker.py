from typing import cast

from kyb_vetter_core.flatfile.checker import FlatFileChecker
from kyb_vetter_core.flatfile.hashing import masked_account
from kyb_vetter_core.flatfile.index import FlatFileIndex
from kyb_vetter_core.flatfile.testing import (
    ACTIVE_PAIRS,
    DATE,
    EXEMPT_PAIRS,
    MASKS,
    TRANSFORMATIONS,
    VIRTUAL_ACTIVE,
    flat_file_json,
)


def make_checker() -> FlatFileChecker:
    data = flat_file_json()
    index = FlatFileIndex.build(
        date=DATE,
        transformations=TRANSFORMATIONS,
        source_sha512="ab" * 64,
        active=cast("list[str]", data["skrotyPodatnikowCzynnych"]),
        exempt=cast("list[str]", data["skrotyPodatnikowZwolnionych"]),
        masks=MASKS,
    )
    return FlatFileChecker(index)


def test_plain_pair_active_and_exempt() -> None:
    checker = make_checker()
    nip, nrb = ACTIVE_PAIRS[0]
    hit = checker.check(nip, nrb)
    assert hit is not None
    assert hit.status == "active"
    assert hit.mask is None
    assert len(hit.digest) == 128

    nip, nrb = EXEMPT_PAIRS[0]
    exempt = checker.check(nip, nrb)
    assert exempt is not None
    assert exempt.status == "exempt"


def test_virtual_account_is_found_through_a_mask() -> None:
    checker = make_checker()
    nip, nrb = VIRTUAL_ACTIVE[0]
    hit = checker.check(nip, nrb)
    assert hit is not None
    assert hit.status == "active"
    assert hit.mask == MASKS[0]
    assert hit.account == masked_account(MASKS[0], nrb)


def test_unknown_pair_is_a_miss_even_with_matching_mask() -> None:
    checker = make_checker()
    assert checker.check("1234563218", "20721233709999999999999999") is None


def test_nip_only_lookup() -> None:
    checker = make_checker()
    assert checker.check_nip("1854510877") == "active"
    assert checker.check_nip("9999999999") is None
