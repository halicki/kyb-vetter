import pytest

from kyb_vetter_core.errors import (
    InvalidBankAccountError,
    InvalidKrsError,
    InvalidNipError,
    InvalidRegonError,
)
from kyb_vetter_core.identifiers import (
    normalize_bank_account,
    normalize_krs,
    normalize_nip,
    normalize_regon,
    validate_bank_account,
    validate_krs,
    validate_nip,
    validate_regon,
)

# --- NIP ------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["1234563218", "7740001454", "123-456-32-18", "PL 7740001454"])
def test_validate_nip_accepts_valid_numbers_in_common_notations(raw: str) -> None:
    assert validate_nip(raw) == raw.upper().removeprefix("PL").replace("-", "").replace(" ", "")


@pytest.mark.parametrize(
    "raw",
    [
        "1234567890",  # checksum remainder 10, never valid
        "1234563219",  # wrong check digit
        "123456321",  # too short
        "12345632181",  # too long
        "12345632a8",  # non-digit
        "",
    ],
)
def test_validate_nip_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidNipError):
        validate_nip(raw)


def test_normalize_nip_strips_formatting_without_validating() -> None:
    assert normalize_nip(" pl 123-456-78-90 ") == "1234567890"


# --- REGON ----------------------------------------------------------------


@pytest.mark.parametrize("raw", ["123456785", "12345678512347", "123 456 785"])
def test_validate_regon_accepts_9_and_14_digit_numbers(raw: str) -> None:
    assert validate_regon(raw) == raw.replace(" ", "")


@pytest.mark.parametrize(
    "raw",
    [
        "123456786",  # wrong check digit (9)
        "12345678512348",  # wrong check digit (14)
        "12345678612347",  # 14-digit whose 9-digit prefix is invalid
        "1234567",  # wrong length
        "12345678x",
        "",
    ],
)
def test_validate_regon_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidRegonError):
        validate_regon(raw)


def test_normalize_regon_strips_whitespace_and_dashes() -> None:
    assert normalize_regon(" 123-456-785 ") == "123456785"


# --- NRB (Polish bank account number) --------------------------------------

WIKI_NRB = "61109010140000071219812874"  # pl.wikipedia IBAN example, PL61 1090 1014 ...


@pytest.mark.parametrize(
    "raw",
    [
        WIKI_NRB,
        "PL" + WIKI_NRB,
        "PL61 1090 1014 0000 0712 1981 2874",
        "61 1090 1014 0000 0712 1981 2874",
    ],
)
def test_validate_bank_account_accepts_nrb_and_iban_notations(raw: str) -> None:
    assert validate_bank_account(raw) == WIKI_NRB


@pytest.mark.parametrize(
    "raw",
    [
        "62109010140000071219812874",  # wrong check digits
        "6110901014000007121981287",  # 25 digits
        "611090101400000712198128744",  # 27 digits
        "DE61109010140000071219812874",  # not a Polish IBAN
        "6110901014000007121981287x",
        "",
    ],
)
def test_validate_bank_account_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidBankAccountError):
        validate_bank_account(raw)


def test_normalize_bank_account_strips_pl_prefix_and_spaces() -> None:
    assert normalize_bank_account("pl 61 1090 1014 0000 0712 1981 2874") == WIKI_NRB


# --- KRS ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0000028860", "0000028860"), ("28860", "0000028860"), (" 0000028860 ", "0000028860")],
)
def test_validate_krs_zero_pads_to_ten_digits(raw: str, expected: str) -> None:
    assert validate_krs(raw) == expected


@pytest.mark.parametrize("raw", ["00000288601", "28860a", "", "0000000000"])
def test_validate_krs_rejects_invalid_numbers(raw: str) -> None:
    with pytest.raises(InvalidKrsError):
        validate_krs(raw)


def test_normalize_krs_pads_without_validating() -> None:
    assert normalize_krs("123") == "0000000123"
