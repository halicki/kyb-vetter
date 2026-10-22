"""Polish business identifiers: NIP, REGON, NRB (bank account), KRS.

``normalize_*`` strips common formatting (spaces, dashes, ``PL`` prefix) and
never raises. ``validate_*`` normalizes, checks length, digits and checksum,
and raises the matching :class:`~kyb_vetter_core.errors.InvalidIdentifierError`.
Checksum rules follow the published algorithms (see ADR-0010 for sources).
"""

from typing import TYPE_CHECKING

from kyb_vetter_core.errors import (
    InvalidBankAccountError,
    InvalidKrsError,
    InvalidNipError,
    InvalidRegonError,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

NIP_WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)
REGON9_WEIGHTS = (8, 9, 2, 3, 4, 5, 6, 7)
REGON14_WEIGHTS = (2, 4, 8, 5, 0, 9, 7, 3, 6, 1, 2, 4, 8)
KRS_LENGTH = 10
NRB_LENGTH = 26
_PL_AS_DIGITS = "2521"  # "P" = 25, "L" = 21 in the IBAN letter mapping


def _weighted_mod11(digits: str, weights: Sequence[int]) -> int:
    return sum(int(d) * w for d, w in zip(digits, weights, strict=True)) % 11


def _strip(value: str) -> str:
    return value.replace(" ", "").replace("-", "").strip()


# --- NIP ------------------------------------------------------------------


def normalize_nip(value: str) -> str:
    """Remove spaces, dashes and an optional ``PL`` prefix."""
    return _strip(value).upper().removeprefix("PL")


def validate_nip(value: str) -> str:
    """Return the normalized NIP or raise :class:`InvalidNipError`."""
    nip = normalize_nip(value)
    if len(nip) != 10 or not nip.isdigit():
        raise InvalidNipError(value, "expected 10 digits")
    check = _weighted_mod11(nip[:9], NIP_WEIGHTS)
    if check == 10 or check != int(nip[9]):
        raise InvalidNipError(value, "checksum mismatch")
    return nip


# --- REGON ----------------------------------------------------------------


def normalize_regon(value: str) -> str:
    """Remove spaces and dashes."""
    return _strip(value)


def _regon_check_digit(digits: str, weights: Sequence[int]) -> int:
    check = _weighted_mod11(digits, weights)
    return 0 if check == 10 else check


def validate_regon(value: str) -> str:
    """Return the normalized 9- or 14-digit REGON or raise :class:`InvalidRegonError`."""
    regon = normalize_regon(value)
    if len(regon) not in (9, 14) or not regon.isdigit():
        raise InvalidRegonError(value, "expected 9 or 14 digits")
    if _regon_check_digit(regon[:8], REGON9_WEIGHTS) != int(regon[8]):
        raise InvalidRegonError(value, "checksum mismatch")
    if len(regon) == 14 and _regon_check_digit(regon[:13], REGON14_WEIGHTS) != int(regon[13]):
        raise InvalidRegonError(value, "checksum mismatch (14-digit part)")
    return regon


# --- NRB ------------------------------------------------------------------


def normalize_bank_account(value: str) -> str:
    """Remove spaces, dashes and an optional ``PL`` IBAN prefix; returns the 26-digit NRB form."""
    return _strip(value).upper().removeprefix("PL")


def validate_bank_account(value: str) -> str:
    """Return the normalized NRB or raise :class:`InvalidBankAccountError`.

    Uses the ISO 13616 (IBAN) mod-97 check with the ``PL`` country code.
    """
    nrb = normalize_bank_account(value)
    if len(nrb) != NRB_LENGTH or not nrb.isdigit():
        raise InvalidBankAccountError(value, f"expected {NRB_LENGTH} digits")
    rearranged = nrb[2:] + _PL_AS_DIGITS + nrb[:2]
    if int(rearranged) % 97 != 1:
        raise InvalidBankAccountError(value, "checksum mismatch")
    return nrb


# --- KRS ------------------------------------------------------------------


def normalize_krs(value: str) -> str:
    """Strip whitespace and left-pad with zeros to 10 digits."""
    return _strip(value).zfill(KRS_LENGTH)


def validate_krs(value: str) -> str:
    """Return the zero-padded 10-digit KRS number or raise :class:`InvalidKrsError`.

    KRS numbers carry no check digit; ``0000000000`` is not a valid entry.
    """
    krs = normalize_krs(value)
    if len(krs) != KRS_LENGTH or not krs.isdigit():
        raise InvalidKrsError(value, f"expected up to {KRS_LENGTH} digits")
    if int(krs) == 0:
        raise InvalidKrsError(value, "must not be zero")
    return krs
