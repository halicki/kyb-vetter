"""Verification service: the use cases behind the MCP tools and the REST API.

Composes the register clients into condensed, sanitised results that are safe
to hand to a language model (ADR-0012): every free-text field from a register
goes through :func:`clean_text`, person data is reduced to what the registers
already publish masked, and each result carries the receipts of the calls
that produced it.
"""

import logging
import re
from datetime import date, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any, Literal, Protocol, TypeIs

from pydantic import BaseModel, ConfigDict

from kyb_vetter_core.config import RegistryEnvironment, registry_environment
from kyb_vetter_core.errors import NotFoundError, RegistryError
from kyb_vetter_core.flatfile.checker import FlatFileChecker
from kyb_vetter_core.identifiers import normalize_nip, validate_bank_account, validate_nip
from kyb_vetter_core.models import (
    SOURCE_KRS,
    WARSAW,
    KrsExtract,
    RegistryReceipt,
    VatStatus,
    VatSubject,
)
from kyb_vetter_core.sanitize import clean_text

if TYPE_CHECKING:
    from kyb_vetter_core.audit import AuditRecorder
    from kyb_vetter_core.clients.protocols import KrsProtocol, WhiteListProtocol
    from kyb_vetter_core.flatfile.index import FlatFileIndex
    from kyb_vetter_core.storage.ports import AuditEvent

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
WARN_FLAT_FILE_MISS = "FLAT_FILE_MISS"

SOURCE_FLAT_FILE = "mf-flat-file"
FLAT_FILE_HOST = "wykazpodatnikowvat.mf.gov.pl"

SOURCE_CEIDG = "ceidg"
DEFAULT_PRINCIPAL = "local"
"""Caller identity until authentication lands (M6)."""
TOOL_VERIFY_COMPANY = "verify_company"
TOOL_CHECK_BANK_ACCOUNT = "check_bank_account"

MAX_ACCOUNT_NUMBERS = 20
"""Accounts listed per company; `account_count` still reports the total (large firms have hundreds)."""
SKIPPED_CEIDG = "not configured"
SKIPPED_KRS_NOT_IN_WHITELIST = "no KRS number to look up: NIP is not on the white list"
SKIPPED_KRS_NO_NUMBER = "no KRS number on the white-list entry (not a registered company)"


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FlatFileSource(Protocol):
    """Whatever serves the newest flat-file index (see :mod:`flatfile.provider`)."""

    async def current(self) -> FlatFileIndex | None: ...


class VerificationWarning(_Model):
    """A finding the caller should weigh; ``code`` is stable, ``message`` is for humans."""

    code: str
    message: str


class SourceReceipt(_Model):
    """Proof of one registry call (see :class:`RegistryReceipt`)."""

    source: str
    host: str
    environment: RegistryEnvironment
    """``test`` means a sandbox or mock answered: synthetic data, no legal value."""
    request_id: str | None
    request_datetime: str
    queried_date: date
    response_sha256: str
    from_cache: bool = False

    @classmethod
    def from_receipt(cls, receipt: RegistryReceipt) -> SourceReceipt:
        return cls(
            source=receipt.source,
            host=receipt.host,
            environment=registry_environment(receipt.host),
            request_id=receipt.request_id,
            request_datetime=receipt.request_datetime.isoformat(),
            queried_date=receipt.queried_date,
            response_sha256=receipt.response_sha256,
            from_cache=receipt.from_cache,
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
    account_numbers: tuple[str, ...]
    accounts_truncated: bool
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
            account_numbers=subject.account_numbers[:MAX_ACCOUNT_NUMBERS],
            accounts_truncated=len(subject.account_numbers) > MAX_ACCOUNT_NUMBERS,
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
    via: Literal["flat_file", "api"]
    """``flat_file``: confirmed offline from the ministry's daily file; ``api``: live white-list call."""
    mask: str | None
    """Bank mask that matched a virtual account, when the flat file answered through one."""
    warnings: tuple[VerificationWarning, ...]
    sources: tuple[SourceReceipt, ...]


class HistoryEntry(_Model):
    """One past invocation, condensed from the audit log."""

    ts: datetime
    tool: str
    outcome: Literal["ok", "error"]
    error_code: str | None
    vat_status: VatStatus | None
    assigned: bool | None
    request_ids: tuple[str, ...]
    sources: tuple[str, ...]
    response_sha256: str | None
    from_cache: bool

    @classmethod
    def from_event(cls, event: AuditEvent) -> HistoryEntry:
        result = event.result or {}
        vat = result.get("vat") or {}
        status = vat.get("status") or result.get("vat_status")
        return cls(
            ts=event.ts,
            tool=event.tool,
            outcome=event.outcome,
            error_code=event.error_code,
            vat_status=None if status is None else VatStatus(status),
            assigned=result.get("assigned"),
            request_ids=event.request_ids,
            sources=event.sources,
            response_sha256=event.response_sha256,
            from_cache=event.from_cache,
        )


class VerificationHistory(_Model):
    """What this server has checked for a NIP, newest first."""

    nip: str
    persistent: bool
    entries: tuple[HistoryEntry, ...]


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
    def __init__(
        self,
        whitelist: WhiteListProtocol,
        krs: KrsProtocol,
        *,
        audit: AuditRecorder,
        persistent: bool,
        flatfile: FlatFileSource | None = None,
    ) -> None:
        self._whitelist = whitelist
        self._krs = krs
        self._audit = audit
        self._persistent = persistent
        self._flatfile = flatfile

    async def verify_company(
        self, nip: str, *, date: date | None = None, principal: str = DEFAULT_PRINCIPAL
    ) -> CompanyVerification:
        """White-list entry plus, when it names a KRS number, the current KRS extract. Audited."""
        audit_input: dict[str, Any] = {
            "nip": nip,
            "date": None if date is None else date.isoformat(),
        }
        try:
            result = await self._verify_company(nip, date=date)
        except Exception as exc:
            await self._audit.record_error(
                principal=principal,
                tool=TOOL_VERIFY_COMPANY,
                nip=normalize_nip(nip),
                input=audit_input,
                exc=exc,
            )
            raise
        await self._audit.record_success(
            principal=principal,
            tool=TOOL_VERIFY_COMPANY,
            nip=result.nip,
            input=audit_input,
            result=result,
        )
        return result

    async def check_bank_account(
        self,
        nip: str,
        account: str,
        *,
        date: date | None = None,
        principal: str = DEFAULT_PRINCIPAL,
    ) -> BankAccountVerification:
        """Whether ``account`` belongs to ``nip`` on the white list, plus the current VAT status. Audited."""
        audit_input: dict[str, Any] = {
            "nip": nip,
            "account": account,
            "date": None if date is None else date.isoformat(),
        }
        try:
            result = await self._check_bank_account(nip, account, date=date)
        except Exception as exc:
            await self._audit.record_error(
                principal=principal,
                tool=TOOL_CHECK_BANK_ACCOUNT,
                nip=normalize_nip(nip),
                input=audit_input,
                exc=exc,
            )
            raise
        await self._audit.record_success(
            principal=principal,
            tool=TOOL_CHECK_BANK_ACCOUNT,
            nip=result.nip,
            input=audit_input,
            result=result,
        )
        return result

    async def verification_history(
        self, nip: str, *, principal: str, limit: int = 20
    ) -> VerificationHistory:
        """Past invocations of ``principal`` for ``nip`` on this server, newest first.

        ``principal`` is required on purpose: history is per user (ADR-0017) and a
        forgotten argument must not fall back to everyone's rows.
        """
        clean = validate_nip(nip)
        events = await self._audit.history(clean, principal=principal, limit=limit)
        return VerificationHistory(
            nip=clean,
            persistent=self._persistent,
            entries=tuple(HistoryEntry.from_event(e) for e in events),
        )

    async def _verify_company(self, nip: str, *, date: date | None) -> CompanyVerification:
        search = await self._whitelist.search(nip, date=date)
        sources = [SourceReceipt.from_receipt(search.receipt)]
        skipped = [SkippedSource(source=SOURCE_CEIDG, reason=SKIPPED_CEIDG)]
        subject = search.subject
        if subject is None:
            skipped.append(SkippedSource(source=SOURCE_KRS, reason=SKIPPED_KRS_NOT_IN_WHITELIST))
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
                skipped=tuple(skipped),
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
        else:
            skipped.append(SkippedSource(source=SOURCE_KRS, reason=SKIPPED_KRS_NO_NUMBER))
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
            skipped=tuple(skipped),
        )

    async def _check_bank_account(
        self, nip: str, account: str, *, date: date | None
    ) -> BankAccountVerification:
        warnings: list[VerificationWarning] = []
        if date is None:
            offline = await self._check_flat_file(nip, account)
            if offline is not None:
                return offline
            if self._flatfile is not None and await self._flatfile.current() is not None:
                warnings.append(
                    VerificationWarning(
                        code=WARN_FLAT_FILE_MISS,
                        message="Pair not found in today's flat file; confirmed with the live API instead.",
                    )
                )
        check = await self._whitelist.check(nip, account, date=date)
        sources = [SourceReceipt.from_receipt(check.receipt)]
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
            via="api",
            mask=None,
            warnings=tuple(warnings),
            sources=tuple(sources),
        )

    async def _check_flat_file(self, nip: str, account: str) -> BankAccountVerification | None:
        """Positive answers come from the daily file (no quota); misses are not conclusive."""
        if self._flatfile is None:
            return None
        index = await self._flatfile.current()
        if index is None:
            return None
        clean_nip = validate_nip(nip)
        clean_account = validate_bank_account(account)
        match = FlatFileChecker(index).check(clean_nip, clean_account)
        if match is None:
            return None
        vat_status = VatStatus.ACTIVE if match.status == "active" else VatStatus.EXEMPT
        receipt = RegistryReceipt(
            source=SOURCE_FLAT_FILE,
            host=self._flatfile_host,
            request_id=None,
            request_datetime=datetime.now(tz=WARSAW),
            queried_date=datetime.strptime(index.date, "%Y%m%d").date(),
            response_sha256=sha256(f"{index.source_sha512}{match.digest}".encode()).hexdigest(),
        )
        warnings = [] if vat_status is VatStatus.ACTIVE else [_not_active_warning(vat_status)]
        return BankAccountVerification(
            nip=clean_nip,
            account=clean_account,
            assigned=True,
            vat_status=vat_status,
            via="flat_file",
            mask=match.mask,
            warnings=tuple(warnings),
            sources=(SourceReceipt.from_receipt(receipt),),
        )

    @property
    def _flatfile_host(self) -> str:
        return FLAT_FILE_HOST

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
