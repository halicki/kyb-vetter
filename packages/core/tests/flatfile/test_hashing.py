"""Official test vectors from the MF flat-file specification (2026-09-07 edition)."""

import pytest

from kyb_vetter_core.flatfile.hashing import (
    MASK_LENGTH,
    iterate_sha512,
    mask_matches,
    masked_account,
    nip_digest,
    pair_digest,
)

SPEC_DATE = "20191018"
V1 = (
    "1435721230",
    "34102012221314181237774212",
    "f8b915776eab735fdd10266b2e66068447904852b82c30eeb6de30703a087eb17ea4c4a37630494607194ddb9354c1211bd984fb5f4d9cff95f5a24ed52065e7",
)
V2_MASK = "XX72123370XXXXXXXYYYXXXXXX"
V2 = (
    "1134679109",
    "20721233708680000022663112",
    "d3dfed802034d198b484c9f19e43c1b7540c3a7808503d01a5ccedbb169012bee6a77979ed46b27f5de2bee0d22eb7c7ca9522dfa92e465999e68e9906e01425",
)


def test_spec_vector_1_plain_account() -> None:
    nip, nrb, expected = V1
    assert pair_digest(SPEC_DATE, nip, nrb, transformations=5000) == expected


def test_spec_vector_2_virtual_account_through_mask() -> None:
    nip, nrb, expected = V2
    built = masked_account(V2_MASK, nrb)
    assert built == "XX72123370XXXXXXX022XXXXXX"
    assert pair_digest(SPEC_DATE, nip, built, transformations=5000) == expected


def test_iteration_rehashes_the_hex_text() -> None:
    once = iterate_sha512("abc", 1)
    twice = iterate_sha512("abc", 2)
    assert twice == iterate_sha512(once, 1)
    assert len(once) == 128
    assert once == once.lower()


def test_zero_iterations_is_rejected() -> None:
    with pytest.raises(ValueError, match="transformations"):
        iterate_sha512("abc", 0)


def test_nip_only_digest_concatenates_date_and_nip() -> None:
    assert nip_digest("20191017", "4356579386", transformations=1) == iterate_sha512(
        "201910174356579386", 1
    )


def test_mask_matches_on_bank_routing_digits() -> None:
    assert mask_matches(V2_MASK, "20721233708680000022663112")
    assert not mask_matches(V2_MASK, "61109010140000071219812874")


@pytest.mark.parametrize("bad", ["XX7212337", "X" * 27, "XX72123370XXXXXXXYYYXXXXX1Z"])
def test_mask_must_be_26_characters(bad: str) -> None:
    with pytest.raises(ValueError, match=str(MASK_LENGTH)):
        masked_account(bad, "20721233708680000022663112")


def test_masked_account_keeps_mask_digits_and_x_positions() -> None:
    mask = "XX14034305XXXXXXYYYYXXXXXX"
    nrb = "12140343059999998765000000"
    assert masked_account(mask, nrb) == "XX14034305XXXXXX8765XXXXXX"
