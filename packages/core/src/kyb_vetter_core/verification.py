"""Verification service: the use cases behind the MCP tools and the REST API.

Composes the register clients into condensed, sanitised results that are safe
to hand to a language model (ADR-0012): every free-text field from a register
goes through :func:`clean_text`, person data is reduced to what the registers
already publish masked, and each result carries the receipts of the calls
that produced it.
"""

import logging
import re
from datetime import date
from typing import TYPE_CHECKING, Literal, TypeIs

from pydantic import BaseModel, ConfigDict

from kyb_vetter_core.errors import NotFoundError, RegistryError
from kyb_vetter_core.identifiers import normalize_nip
from kyb_vetter_core.models import KrsExtract, RegistryReceipt, VatStatus, VatSubject
from kyb_vetter_core.sanitize import clean_text

if TYPE_CHECKING:
    from kyb_vetter_core.clients.krs import KrsClient
    from kyb_vetter_core.clients.whitelist import WhiteListClient

logger = logging.getLogger(__name__)


def _present(value: str | None) -> TypeIs[str]:
    return value is not None and value != ""


WARN_NOT_IN_WHITELIST = "NOT_IN_WHITELIST"
WARN_VAT_NOT_ACTIVE = "VAT_NOT_ACTIVE"
WARN_VAT_REMOVED = "VAT_REMOVED"
WARN_VAT_STATUS_UNAVAILABLE = "VAT_STATUS_UNAVAILABLE"
WARN_KRS_NOT_FOUND = "KRS_NOT_FOUND"
WARN_KRS_UNAVAILABLE = "KRS_UNAVAILABLE"
WARN_NAME_MISMATCH = "NAME_MISMATCH"
WARN_NO_BANK_ACCOUNTS = "NO_BANK_ACCOUNTS"

SOURCE_CEIDG = "ceidg"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VerificationWarning(_Model):
    """A finding the caller should weigh; ``code`` is stable, ``message`` is for humans."""

    code: str
    message: str


class SourceReceipt(_Model):
    """Proof of one registry call (see :class:`RegistryReceipt`)."""

    source: str
    request_id: str | None
    request_datetime: str
    queried_date: date
    response_sha256: str

    @classmethod
    def from_receipt(cls, receipt: RegistryReceipt) -> SourceReceipt:
        return cls(
            source=receipt.source,
            request_id=receipt.request_id,
            request_datetime=receipt.request_datetime.isoformat(),
            queried_date=receipt.queried_date,
            response_sha256=receipt.response_sha256,
        )


class SkippedSource(_Model):
    source: str
    reason: str


class VatSummary(_Model):
    """Condensed VAT white-list entry."""

    status: VatStatus
    name: str | None
    residence_address: str | None
    working_address: str | None
    regon: str | None
    krs: str | None
    registration_legal_date: date | None
    removal_date: date | None
    restoration_date: date | None
    account_count: int
    has_virtual_accounts: bool | None

    @classmethod
    def from_subject(cls, subject: VatSubject) -> VatSummary:
        return cls(
            status=subject.status,
            name=clean_text(subject.name),
            residence_address=clean_text(subject.residence_address),
            working_address=clean_text(subject.working_address),
            regon=subject.regon,
            krs=subject.krs,
            registration_legal_date=subject.registration_legal_date,
            removal_date=subject.removal_date,
            restoration_date=subject.restoration_date,
            account_count=len(subject.account_numbers),
            has_virtual_accounts=subject.has_virtual_accounts,
        )


class BoardMember(_Model):
    name_masked: str
    role: str | None


class KrsSummary(_Model):
    """Condensed current KRS extract."""

    krs: str
    register_kind: Literal["P", "S"]
    name: str | None
    legal_form: str | None
    seat_city: str | None
    address: str | None
    share_capital_amount: str | None
    share_capital_currency: str | None
    main_activity: str | None
    board: tuple[BoardMember, ...]
    as_of: date

    @classmethod
    def from_extract(cls, extract: KrsExtract) -> KrsSummary:
        address = extract.address
        street_line = " ".join(p for p in (address.street, address.building_number) if _present(p))
        if _present(address.unit_number):
            street_line = f"{street_line}/{address.unit_number}"
        city_line = " ".join(p for p in (address.postal_code, address.city) if _present(p))
        address_line = ", ".join(p for p in (street_line, city_line) if p != "") or None
        capital = extract.share_capital
        activity = extract.main_activity
        representation = extract.representation
        return cls(
            krs=extract.krs,
            register_kind="S" if extract.register_kind == "S" else "P",
            name=clean_text(extract.name),
            legal_form=clean_text(extract.legal_form),
            seat_city=clean_text(extract.seat.city),
            address=clean_text(address_line),
            share_capital_amount=None if capital is None else str(capital.amount),
            share_capital_currency=None if capital is None else capital.currency,
            main_activity=None
            if activity is None
            else clean_text(f"{activity.code} {activity.description}"),
            board=()
            if representation is None
            else tuple(
                BoardMember(
                    name_masked=clean_text(m.name_masked, max_len=120) or "",
                    role=clean_text(m.role),
                )
                for m in representation.members
            ),
            as_of=extract.as_of,
        )


class CompanyVerification(_Model):
    """Everything the registers say about a company, condensed for an agent."""

    nip: str
    found: bool
    vat: VatSummary | None
    krs: KrsSummary | None
    warnings: tuple[VerificationWarning, ...]
    sources: tuple[SourceReceipt, ...]
    skipped: tuple[SkippedSource, ...]


class BankAccountVerification(_Model):
    nip: str
    account: str
    assigned: bool
    vat_status: VatStatus | None
    warnings: tuple[VerificationWarning, ...]
    sources: tuple[SourceReceipt, ...]


# --- name comparison ------------------------------------------------------

_LEGAL_FORMS: tuple[tuple[str, str], ...] = (
    ("spółka z ograniczoną odpowiedzialnością", "spzoo"),
    ("sp. z o.o.", "spzoo"),
    ("spółka akcyjna", "sa"),
    ("s.a.", "sa"),
    ("spółka komandytowa", "spk"),
    ("sp.k.", "spk"),
    ("spółka jawna", "spj"),
    ("sp.j.", "spj"),
)
_NON_ALNUM = re.compile(r"[^0-9a-ząćęłńóśźż]+")


def _normalise_name(name: str) -> str:
    text = re.sub(r"\s+", " ", name.casefold()).strip()
    for long_form, short in _LEGAL_FORMS:
        text = text.replace(long_form, f" {short} ")
    return _NON_ALNUM.sub("", text)


def names_match(a: str | None, b: str | None) -> bool:
    """Loose equality of company names: case, whitespace and legal-form spelling are ignored."""
    if not (_present(a) and _present(b)):
        return False
    return _normalise_name(a) == _normalise_name(b)


# --- service --------------------------------------------------------------


class VerificationService:
    def __init__(self, whitelist: WhiteListClient, krs: KrsClient) -> None:
        self._whitelist = whitelist
        self._krs = krs

    async def verify_company(self, nip: str, *, date: date | None = None) -> CompanyVerification:
        """White-list entry plus, when it names a KRS number, the current KRS extract."""
        search = await self._whitelist.search(nip, date=date)
        sources = [SourceReceipt.from_receipt(search.receipt)]
        skipped = (SkippedSource(source=SOURCE_CEIDG, reason="not configured"),)
        subject = search.subject
        if subject is None:
            return CompanyVerification(
                nip=normalize_nip(nip),
                found=False,
                vat=None,
                krs=None,
                warnings=(
                    VerificationWarning(
                        code=WARN_NOT_IN_WHITELIST, message="NIP is not on the VAT white list."
                    ),
                ),
                sources=tuple(sources),
                skipped=skipped,
            )

        vat = VatSummary.from_subject(subject)
        warnings = _vat_warnings(subject)
        krs_summary: KrsSummary | None = None
        if _present(subject.krs):
            krs_summary, krs_warning, krs_receipt = await self._fetch_krs(subject.krs)
            if krs_receipt is not None:
                sources.append(SourceReceipt.from_receipt(krs_receipt))
            if krs_warning is not None:
                warnings.append(krs_warning)
            if krs_summary is not None and not names_match(vat.name, krs_summary.name):
                warnings.append(
                    VerificationWarning(
                        code=WARN_NAME_MISMATCH,
                        message="Company name on the VAT white list differs from the KRS entry.",
                    )
                )
        if vat.account_count == 0:
            warnings.append(
                VerificationWarning(
                    code=WARN_NO_BANK_ACCOUNTS,
                    message="No bank accounts are registered on the white list.",
                )
            )
        return CompanyVerification(
            nip=subject.nip or normalize_nip(nip),
            found=True,
            vat=vat,
            krs=krs_summary,
            warnings=tuple(warnings),
            sources=tuple(sources),
            skipped=skipped,
        )

    async def check_bank_account(
        self, nip: str, account: str, *, date: date | None = None
    ) -> BankAccountVerification:
        """Whether ``account`` belongs to ``nip`` on the white list, plus the current VAT status."""
        check = await self._whitelist.check(nip, account, date=date)
        sources = [SourceReceipt.from_receipt(check.receipt)]
        warnings: list[VerificationWarning] = []
        vat_status: VatStatus | None
        try:
            status = await self._whitelist.status(check.nip, date=date)
        except RegistryError as exc:
            logger.warning("VAT status lookup failed for %s: %s", check.nip, exc)
            vat_status = None
            warnings.append(
                VerificationWarning(
                    code=WARN_VAT_STATUS_UNAVAILABLE, message="VAT status could not be retrieved."
                )
            )
        else:
            vat_status = status.status
            sources.append(SourceReceipt.from_receipt(status.receipt))
            if vat_status is not VatStatus.ACTIVE:
                warnings.append(_not_active_warning(vat_status))
        return BankAccountVerification(
            nip=check.nip,
            account=check.account,
            assigned=check.assigned,
            vat_status=vat_status,
            warnings=tuple(warnings),
            sources=tuple(sources),
        )

    async def _fetch_krs(
        self, krs: str
    ) -> tuple[KrsSummary | None, VerificationWarning | None, RegistryReceipt | None]:
        try:
            extract = await self._krs.get_extract(krs)
        except NotFoundError:
            return (
                None,
                VerificationWarning(
                    code=WARN_KRS_NOT_FOUND, message=f"KRS {krs} was not found in the register."
                ),
                None,
            )
        except RegistryError as exc:
            logger.warning("KRS lookup failed for %s: %s", krs, exc)
            return (
                None,
                VerificationWarning(
                    code=WARN_KRS_UNAVAILABLE, message="KRS could not be reached; VAT data only."
                ),
                None,
            )
        return KrsSummary.from_extract(extract), None, extract.receipt


def _not_active_warning(status: VatStatus) -> VerificationWarning:
    return VerificationWarning(
        code=WARN_VAT_NOT_ACTIVE, message=f"VAT status is '{status.value}', not 'active'."
    )


def _vat_warnings(subject: VatSubject) -> list[VerificationWarning]:
    warnings: list[VerificationWarning] = []
    if subject.status is not VatStatus.ACTIVE:
        warnings.append(_not_active_warning(subject.status))
    if subject.removal_date is not None:
        warnings.append(
            VerificationWarning(
                code=WARN_VAT_REMOVED,
                message=f"Removed from the VAT register on {subject.removal_date}.",
            )
        )
    return warnings
