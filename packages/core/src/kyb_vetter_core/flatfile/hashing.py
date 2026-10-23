"""SHA-512 scheme of the MF flat file (specification of 2026-09-07).

Input is the concatenation ``date (YYYYMMDD) + NIP (10) + NRB (26)``, or
``date + NIP`` for taxpayers without an account. The digest is applied
``transformations`` times, each round hashing the lowercase hex text of the
previous one. Virtual accounts are matched through bank masks: positions 2-9
hold the bank routing number, ``Y`` marks digits taken from the customer's
account, ``X`` stays literal.
"""

from hashlib import sha512

MASK_LENGTH = 26
ROUTING = slice(2, 10)


def iterate_sha512(text: str, transformations: int) -> str:
    if transformations < 1:
        raise ValueError("transformations must be at least 1")
    digest = text
    for _ in range(transformations):
        digest = sha512(digest.encode("ascii")).hexdigest()
    return digest


def pair_digest(date: str, nip: str, account: str, *, transformations: int) -> str:
    return iterate_sha512(f"{date}{nip}{account}", transformations)


def nip_digest(date: str, nip: str, *, transformations: int) -> str:
    return iterate_sha512(f"{date}{nip}", transformations)


def _check_mask(mask: str) -> None:
    if len(mask) != MASK_LENGTH or any(c not in "XY0123456789" for c in mask):
        raise ValueError(f"mask must be {MASK_LENGTH} characters of digits, X and Y: {mask!r}")


def mask_matches(mask: str, account: str) -> bool:
    """A mask applies when its bank routing digits equal the account's."""
    _check_mask(mask)
    return mask[ROUTING] == account[ROUTING]


def masked_account(mask: str, account: str) -> str:
    """Substitute the customer's digits at ``Y`` positions; digits and ``X`` stay as in the mask."""
    _check_mask(mask)
    return "".join(a if m == "Y" else m for m, a in zip(mask, account, strict=True))
