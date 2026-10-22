"""Structural types of the register clients, so that guards and caches can wrap them."""

from typing import TYPE_CHECKING, Protocol
lazy from collections.abc import Sequence
lazy from datetime import date

if TYPE_CHECKING:
    from kyb_vetter_core.models import (
        BankAccountCheck,
        KrsExtract,
        VatBatchResult,
        VatSearchResult,
        VatStatusResult,
    )


class WhiteListProtocol(Protocol):
    async def status(self, nip: str, *, date: date | None = None) -> VatStatusResult: ...

    async def search(self, nip: str, *, date: date | None = None) -> VatSearchResult: ...

    async def search_many(
        self, nips: Sequence[str], *, date: date | None = None
    ) -> VatBatchResult: ...

    async def check(
        self, nip: str, account: str, *, date: date | None = None
    ) -> BankAccountCheck: ...


class KrsProtocol(Protocol):
    async def get_extract(self, krs: str) -> KrsExtract: ...
