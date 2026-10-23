"""Answer "is this account registered to this NIP today?" from the flat file."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kyb_vetter_core.flatfile.hashing import mask_matches, masked_account, nip_digest, pair_digest

if TYPE_CHECKING:
    from kyb_vetter_core.flatfile.index import FlatFileIndex, Status


@dataclass(frozen=True, slots=True)
class FlatFileMatch:
    status: Status
    digest: str
    account: str
    """The string that was hashed: the NRB itself or the mask-built virtual account."""
    mask: str | None


class FlatFileChecker:
    def __init__(self, index: FlatFileIndex) -> None:
        self._index = index

    def check(self, nip: str, account: str) -> FlatFileMatch | None:
        """Plain pair first, then every mask of the account's bank (spec order)."""
        idx = self._index
        digest = pair_digest(idx.date, nip, account, transformations=idx.transformations)
        status = idx.lookup(digest)
        if status is not None:
            return FlatFileMatch(status=status, digest=digest, account=account, mask=None)
        for mask in idx.masks:
            if not mask_matches(mask, account):
                continue
            built = masked_account(mask, account)
            digest = pair_digest(idx.date, nip, built, transformations=idx.transformations)
            status = idx.lookup(digest)
            if status is not None:
                return FlatFileMatch(status=status, digest=digest, account=built, mask=mask)
        return None

    def check_nip(self, nip: str) -> Status | None:
        """Taxpayers without accounts are listed as ``date + NIP``."""
        idx = self._index
        return idx.lookup(nip_digest(idx.date, nip, transformations=idx.transformations))
