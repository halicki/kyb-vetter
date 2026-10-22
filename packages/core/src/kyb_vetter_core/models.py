"""Domain models returned by the register clients.

Models are deliberately narrower than the registry payloads: no PESEL numbers,
no free-text fields about natural persons, no raw JSON. Every result carries a
:class:`RegistryReceipt` (official request id when the registry issues one,
timestamps and a SHA-256 of the raw response) so that the audit log can prove
what was verified and when.
"""

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256
from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from kyb_vetter_core.errors import RegistryError, registry_error_from_code

WARSAW = ZoneInfo("Europe/Warsaw")
SOURCE_WHITELIST = "mf-whitelist"
SOURCE_WHITELIST_STATUS = "mf-whitelist-status"
SOURCE_KRS = "krs"

type Json = Mapping[str, Any]


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _parse_wl_datetime(value: str) -> datetime:
    """White-list timestamps look like ``19-11-2019 14:58:49`` (Warsaw local time)."""
    return datetime.strptime(value, "%d-%m-%Y %H:%M:%S").replace(tzinfo=WARSAW)


def _parse_wl_date(value: str) -> date:
    """White-list ``requestedDate`` looks like ``10-10-2021``."""
    return datetime.strptime(value, "%d-%m-%Y").date()


def _parse_iso_date(value: str | None) -> date | None:
    return None if value is None else date.fromisoformat(value)


def _parse_krs_date(value: str) -> date:
    """KRS dates look like ``09.10.2026``."""
    return datetime.strptime(value, "%d.%m.%Y").date()


# --- Receipt --------------------------------------------------------------


class RegistryReceipt(_Model):
    """Proof of a registry call, kept with every result for the audit trail."""

    source: str
    host: str
    """Hostname that answered; tells the production register from its test environment."""
    request_id: str | None
    request_datetime: datetime
    queried_date: date
    response_sha256: str
    from_cache: bool = False

    @classmethod
    def from_whitelist(cls, result: Json, *, raw: bytes, queried_date: date, host: str) -> Self:
        return cls(
            source=SOURCE_WHITELIST,
            host=host,
            request_id=result["requestId"],
            request_datetime=_parse_wl_datetime(result["requestDateTime"]),
            queried_date=queried_date,
            response_sha256=sha256(raw).hexdigest(),
        )


class ReceiptedModel(_Model):
    """A registry result that carries the receipt of the call that produced it."""

    receipt: RegistryReceipt


# --- VAT white list -------------------------------------------------------


class VatStatus(StrEnum):
    ACTIVE = "active"
    EXEMPT = "exempt"
    NOT_REGISTERED = "not_registered"

    @classmethod
    def from_api(cls, value: str) -> Self:
        return cls(_VAT_STATUS_FROM_API[value])


_VAT_STATUS_FROM_API = {
    "Czynny": "active",
    "Zwolniony": "exempt",
    "Niezarejestrowany": "not_registered",
}


class Person(_Model):
    """A representative, authorized clerk or partner. PESEL is never carried over."""

    company_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    nip: str | None = None

    @classmethod
    def from_api(cls, data: Json) -> Self:
        return cls(
            company_name=data.get("companyName"),
            first_name=data.get("firstName"),
            last_name=data.get("lastName"),
            nip=data.get("nip"),
        )


class VatSubject(_Model):
    """A taxpayer entry from the VAT white list."""

    name: str
    nip: str | None
    status: VatStatus
    regon: str | None
    krs: str | None
    residence_address: str | None
    working_address: str | None
    registration_legal_date: date | None
    registration_denial_date: date | None
    registration_denial_basis: str | None
    restoration_date: date | None
    restoration_basis: str | None
    removal_date: date | None
    removal_basis: str | None
    exemption_sme_date: date | None
    account_numbers: tuple[str, ...]
    has_virtual_accounts: bool | None
    representatives: tuple[Person, ...]
    authorized_clerks: tuple[Person, ...]
    partners: tuple[Person, ...]

    @classmethod
    def from_api(cls, data: Json) -> Self:
        def persons(key: str) -> tuple[Person, ...]:
            return tuple(Person.from_api(p) for p in data.get(key) or ())

        return cls(
            name=data["name"],
            nip=data.get("nip"),
            status=VatStatus.from_api(data["statusVat"]),
            regon=data.get("regon"),
            krs=data.get("krs"),
            residence_address=data.get("residenceAddress"),
            working_address=data.get("workingAddress"),
            registration_legal_date=_parse_iso_date(data.get("registrationLegalDate")),
            registration_denial_date=_parse_iso_date(data.get("registrationDenialDate")),
            registration_denial_basis=data.get("registrationDenialBasis"),
            restoration_date=_parse_iso_date(data.get("restorationDate")),
            restoration_basis=data.get("restorationBasis"),
            removal_date=_parse_iso_date(data.get("removalDate")),
            removal_basis=data.get("removalBasis"),
            exemption_sme_date=_parse_iso_date(data.get("exemptionSmeDate")),
            account_numbers=tuple(data.get("accountNumbers") or ()),
            has_virtual_accounts=data.get("hasVirtualAccounts"),
            representatives=persons("representatives"),
            authorized_clerks=persons("authorizedClerks"),
            partners=persons("partners"),
        )


class VatSearchResult(ReceiptedModel):
    """Result of ``/api/search/nip/{nip}``; ``subject`` is ``None`` when the NIP is unknown."""

    subject: VatSubject | None

    @classmethod
    def from_api(cls, payload: Json, *, raw: bytes, queried_date: date, host: str) -> Self:
        result = payload["result"]
        subject = result.get("subject")
        return cls(
            subject=None if subject is None else VatSubject.from_api(subject),
            receipt=RegistryReceipt.from_whitelist(
                result, raw=raw, queried_date=queried_date, host=host
            ),
        )


class VatBatchResult(ReceiptedModel):
    """Result of ``/api/search/nips/{...}``: subjects per identifier, plus per-identifier errors."""

    subjects: Mapping[str, tuple[VatSubject, ...]]
    errors: Mapping[str, RegistryError]

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    @classmethod
    def from_api(cls, payload: Json, *, raw: bytes, queried_date: date, host: str) -> Self:
        result = payload["result"]
        subjects: dict[str, tuple[VatSubject, ...]] = {}
        errors: dict[str, RegistryError] = {}
        for entry in result["entries"]:
            identifier = entry["identifier"]
            if "error" in entry:
                error = entry["error"]
                errors[identifier] = registry_error_from_code(
                    error["code"], error["message"], source=SOURCE_WHITELIST
                )
            else:
                subjects[identifier] = tuple(
                    VatSubject.from_api(s) for s in entry.get("subjects") or ()
                )
        return cls(
            subjects=subjects,
            errors=errors,
            receipt=RegistryReceipt.from_whitelist(
                result, raw=raw, queried_date=queried_date, host=host
            ),
        )


class VatStatusResult(ReceiptedModel):
    """Result of the WL2 ``/api2/status/nip/{nip}`` endpoint (status only, high quota)."""

    nip: str
    status: VatStatus

    @classmethod
    def from_api(cls, payload: Json, *, raw: bytes, host: str) -> Self:
        subject = payload["result"]["subject"]
        return cls(
            nip=subject["nip"],
            status=VatStatus.from_api(subject["statusVat"]),
            receipt=RegistryReceipt(
                source=SOURCE_WHITELIST_STATUS,
                host=host,
                request_id=subject["requestId"],
                request_datetime=_parse_wl_datetime(subject["responseDateTime"]),
                queried_date=_parse_wl_date(subject["requestedDate"]),
                response_sha256=sha256(raw).hexdigest(),
            ),
        )


class BankAccountCheck(ReceiptedModel):
    """Result of ``/api/check/nip/{nip}/bank-account/{nrb}``."""

    nip: str
    account: str
    assigned: bool

    @classmethod
    def from_api(
        cls, payload: Json, *, nip: str, account: str, raw: bytes, queried_date: date, host: str
    ) -> Self:
        result = payload["result"]
        return cls(
            nip=nip,
            account=account,
            assigned=result["accountAssigned"] == "TAK",
            receipt=RegistryReceipt.from_whitelist(
                result, raw=raw, queried_date=queried_date, host=host
            ),
        )


# --- KRS ------------------------------------------------------------------


class Seat(_Model):
    country: str | None = None
    voivodeship: str | None = None
    county: str | None = None
    municipality: str | None = None
    city: str | None = None

    @classmethod
    def from_api(cls, data: Json) -> Self:
        return cls(
            country=data.get("kraj"),
            voivodeship=data.get("wojewodztwo"),
            county=data.get("powiat"),
            municipality=data.get("gmina"),
            city=data.get("miejscowosc"),
        )


class Address(_Model):
    street: str | None = None
    building_number: str | None = None
    unit_number: str | None = None
    city: str | None = None
    postal_code: str | None = None
    post_office: str | None = None
    country: str | None = None

    @classmethod
    def from_api(cls, data: Json) -> Self:
        return cls(
            street=data.get("ulica"),
            building_number=data.get("nrDomu"),
            unit_number=data.get("nrLokalu"),
            city=data.get("miejscowosc"),
            postal_code=data.get("kodPocztowy"),
            post_office=data.get("poczta"),
            country=data.get("kraj"),
        )


class ShareCapital(_Model):
    amount: Decimal
    currency: str

    @classmethod
    def from_api(cls, data: Json) -> Self:
        return cls(
            amount=Decimal(data["wartosc"].replace(" ", "").replace(",", ".")),
            currency=data["waluta"],
        )


class Officer(_Model):
    """A member of the representing body. Names arrive masked from the registry."""

    name_masked: str
    role: str | None = None
    suspended: bool | None = None

    @classmethod
    def from_api(cls, data: Json) -> Self:
        given = " ".join(v for v in (data.get("imiona") or {}).values() if v)
        family = (data.get("nazwisko") or {}).get("nazwiskoICzlon", "")
        return cls(
            name_masked=f"{given} {family}".strip(),
            role=data.get("funkcjaWOrganie"),
            suspended=data.get("czyZawieszona"),
        )


class Representation(_Model):
    organ: str | None
    rule: str | None
    members: tuple[Officer, ...]

    @classmethod
    def from_api(cls, data: Json) -> Self:
        return cls(
            organ=data.get("nazwaOrganu"),
            rule=data.get("sposobReprezentacji"),
            members=tuple(Officer.from_api(m) for m in data.get("sklad") or ()),
        )


class Activity(_Model):
    """A PKD activity code such as ``19.20.Z``."""

    code: str
    description: str

    @classmethod
    def from_api(cls, data: Json) -> Self:
        parts = [data.get("kodDzial"), data.get("kodKlasa"), data.get("kodPodklasa")]
        return cls(code=".".join(p for p in parts if p), description=data["opis"])


class KrsExtract(ReceiptedModel):
    """Condensed current extract (``OdpisAktualny``) from the National Court Register."""

    krs: str
    register_kind: str
    name: str
    legal_form: str | None
    nip: str | None
    regon: str | None
    seat: Seat
    address: Address
    email: str | None
    website: str | None
    share_capital: ShareCapital | None
    representation: Representation | None
    main_activity: Activity | None
    other_activities: tuple[Activity, ...]
    registration_date: date | None
    as_of: date
    last_entry_number: int | None

    @classmethod
    def from_api(cls, payload: Json, *, raw: bytes, fetched_at: datetime, host: str) -> Self:
        odpis = payload["odpis"]
        header = odpis["naglowekA"]
        dane = odpis["dane"]
        d1 = dane.get("dzial1") or {}
        d2 = dane.get("dzial2") or {}
        d3 = dane.get("dzial3") or {}
        entity = d1.get("danePodmiotu") or {}
        ids = entity.get("identyfikatory") or {}
        seat_addr = d1.get("siedzibaIAdres") or {}
        capital = (d1.get("kapital") or {}).get("wysokoscKapitaluZakladowego")
        representation = d2.get("reprezentacja")
        activity = d3.get("przedmiotDzialalnosci") or {}
        main = activity.get("przedmiotPrzewazajacejDzialalnosci") or []
        return cls(
            krs=header["numerKRS"],
            register_kind=header["rejestr"].removeprefix("Rej"),
            name=entity["nazwa"],
            legal_form=entity.get("formaPrawna"),
            nip=ids.get("nip"),
            regon=ids.get("regon"),
            seat=Seat.from_api(seat_addr.get("siedziba") or {}),
            address=Address.from_api(seat_addr.get("adres") or {}),
            email=seat_addr.get("adresPocztyElektronicznej"),
            website=seat_addr.get("adresStronyInternetowej"),
            share_capital=None if capital is None else ShareCapital.from_api(capital),
            representation=None
            if representation is None
            else Representation.from_api(representation),
            main_activity=Activity.from_api(main[0]) if main else None,
            other_activities=tuple(
                Activity.from_api(a) for a in activity.get("przedmiotPozostalejDzialalnosci") or ()
            ),
            registration_date=(
                _parse_krs_date(header["dataRejestracjiWKRS"])
                if header.get("dataRejestracjiWKRS")
                else None
            ),
            as_of=_parse_krs_date(header["stanZDnia"]),
            last_entry_number=header.get("numerOstatniegoWpisu"),
            receipt=RegistryReceipt(
                source=SOURCE_KRS,
                host=host,
                request_id=None,
                request_datetime=fetched_at,
                queried_date=fetched_at.astimezone(WARSAW).date(),
                response_sha256=sha256(raw).hexdigest(),
            ),
        )


__all__: Sequence[str] = (
    "Activity",
    "Address",
    "BankAccountCheck",
    "KrsExtract",
    "Officer",
    "Person",
    "RegistryReceipt",
    "Representation",
    "Seat",
    "ShareCapital",
    "VatBatchResult",
    "VatSearchResult",
    "VatStatus",
    "VatStatusResult",
    "VatSubject",
)
