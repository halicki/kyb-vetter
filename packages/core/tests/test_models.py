import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from kyb_vetter_core.models import (
    BankAccountCheck,
    KrsExtract,
    RegistryReceipt,
    VatBatchResult,
    VatSearchResult,
    VatStatus,
    VatStatusResult,
    VatSubject,
)

FIXTURES = Path(__file__).parent / "fixtures"
WARSAW = ZoneInfo("Europe/Warsaw")

SUBJECT = {
    "name": "ABC Jan Nowak",
    "nip": "1234563218",
    "statusVat": "Czynny",
    "regon": "123456785",
    "pesel": "90010112345",
    "krs": "0000636771",
    "residenceAddress": "ul. Chmielna 85/87 00-805 Warszawa",
    "workingAddress": None,
    "representatives": [
        {
            "companyName": None,
            "firstName": "Jan",
            "lastName": "Nowak",
            "pesel": "90010112345",
            "nip": None,
        }
    ],
    "authorizedClerks": [],
    "partners": [
        {
            "companyName": "Partner sp. z o.o.",
            "firstName": None,
            "lastName": None,
            "pesel": None,
            "nip": "7740001454",
        }
    ],
    "registrationLegalDate": "2019-09-01",
    "registrationDenialDate": None,
    "registrationDenialBasis": None,
    "restorationDate": None,
    "restorationBasis": None,
    "removalDate": None,
    "removalBasis": None,
    "exemptionSmeDate": None,
    "accountNumbers": ["61109010140000071219812874"],
    "hasVirtualAccounts": False,
}
RESULT_META = {"requestDateTime": "19-11-2019 14:58:49", "requestId": "d2n10-84df1a1"}


def test_vat_status_parses_polish_api_values() -> None:
    assert VatStatus.from_api("Czynny") is VatStatus.ACTIVE
    assert VatStatus.from_api("Zwolniony") is VatStatus.EXEMPT
    assert VatStatus.from_api("Niezarejestrowany") is VatStatus.NOT_REGISTERED


def test_vat_subject_from_api_keeps_business_fields_and_drops_pesel() -> None:
    subject = VatSubject.from_api(SUBJECT)

    assert subject.name == "ABC Jan Nowak"
    assert subject.nip == "1234563218"
    assert subject.status is VatStatus.ACTIVE
    assert subject.regon == "123456785"
    assert subject.krs == "0000636771"
    assert subject.residence_address == "ul. Chmielna 85/87 00-805 Warszawa"
    assert subject.working_address is None
    assert subject.registration_legal_date == date(2019, 9, 1)
    assert subject.removal_date is None
    assert subject.account_numbers == ("61109010140000071219812874",)
    assert subject.has_virtual_accounts is False
    assert subject.representatives[0].last_name == "Nowak"
    assert subject.partners[0].company_name == "Partner sp. z o.o."
    assert subject.partners[0].nip == "7740001454"
    assert "pesel" not in subject.model_dump_json()
    assert "90010112345" not in subject.model_dump_json()


def test_registry_receipt_from_whitelist_parses_request_metadata_and_hashes_raw_body() -> None:
    raw = b'{"result": {}}'
    receipt = RegistryReceipt.from_whitelist(
        RESULT_META, raw=raw, queried_date=date(2019, 11, 19), host="mf.example"
    )

    assert receipt.source == "mf-whitelist"
    assert receipt.host == "mf.example"
    assert receipt.request_id == "d2n10-84df1a1"
    assert receipt.request_datetime == datetime(2019, 11, 19, 14, 58, 49, tzinfo=WARSAW)
    assert receipt.queried_date == date(2019, 11, 19)
    assert receipt.response_sha256 == hashlib.sha256(raw).hexdigest()


def test_vat_search_result_with_subject_and_without() -> None:
    found = VatSearchResult.from_api(
        {"result": {"subject": SUBJECT, **RESULT_META}},
        raw=b"x",
        queried_date=date(2019, 11, 19),
        host="mf.example",
    )
    missing = VatSearchResult.from_api(
        {"result": {"subject": None, **RESULT_META}},
        raw=b"x",
        queried_date=date(2019, 11, 19),
        host="mf.example",
    )

    assert found.subject is not None
    assert found.subject.nip == "1234563218"
    assert found.receipt.request_id == "d2n10-84df1a1"
    assert found.receipt.host == "mf.example"
    assert missing.subject is None


def test_vat_batch_result_separates_subjects_from_per_identifier_errors() -> None:
    payload = {
        "result": {
            "entries": [
                {"identifier": "1234563218", "subjects": [SUBJECT]},
                {"identifier": "7740001454", "subjects": []},
                {
                    "identifier": "1234567890",
                    "error": {"code": "WL-115", "message": "Nieprawidłowy NIP."},
                },
            ],
            **RESULT_META,
        }
    }
    batch = VatBatchResult.from_api(
        payload, raw=b"x", queried_date=date(2019, 11, 19), host="mf.example"
    )

    assert [s.nip for s in batch.subjects["1234563218"]] == ["1234563218"]
    assert batch.subjects["7740001454"] == ()
    assert batch.errors["1234567890"].code == "WL-115"
    assert batch.receipt.request_id == "d2n10-84df1a1"


def test_vat_status_result_from_api2() -> None:
    payload = {
        "result": {
            "subject": {
                "nip": "1234563218",
                "statusVat": "Zwolniony",
                "requestedDate": "10-10-2021",
                "responseDateTime": "21-11-2019 14:58:49",
                "requestId": "d2n10-84df1a1",
            }
        }
    }
    result = VatStatusResult.from_api(payload, raw=b"x", host="mf.example")

    assert result.nip == "1234563218"
    assert result.status is VatStatus.EXEMPT
    assert result.receipt.source == "mf-whitelist-status"
    assert result.receipt.queried_date == date(2021, 10, 10)
    assert result.receipt.request_datetime == datetime(2019, 11, 21, 14, 58, 49, tzinfo=WARSAW)
    assert result.receipt.request_id == "d2n10-84df1a1"
    assert result.receipt.host == "mf.example"


def test_bank_account_check_parses_tak_nie() -> None:
    yes = BankAccountCheck.from_api(
        {"result": {"accountAssigned": "TAK", **RESULT_META}},
        nip="1234563218",
        account="61109010140000071219812874",
        raw=b"x",
        queried_date=date(2019, 11, 19),
        host="mf.example",
    )
    no = BankAccountCheck.from_api(
        {"result": {"accountAssigned": "NIE", **RESULT_META}},
        nip="1234563218",
        account="61109010140000071219812874",
        raw=b"x",
        queried_date=date(2019, 11, 19),
        host="mf.example",
    )
    assert yes.assigned is True
    assert no.assigned is False
    assert yes.nip == "1234563218"
    assert yes.account == "61109010140000071219812874"
    assert yes.receipt.host == "mf.example"


def test_krs_extract_from_api_maps_the_current_extract() -> None:
    payload = json.loads((FIXTURES / "krs" / "0000028860.json").read_text())
    extract = KrsExtract.from_api(
        payload,
        raw=b"x",
        fetched_at=datetime(2026, 10, 22, 19, 13, tzinfo=UTC),
        host="krs.example",
    )

    assert extract.krs == "0000028860"
    assert extract.register_kind == "P"
    assert extract.name == "ORLEN SPÓŁKA AKCYJNA"
    assert extract.legal_form == "SPÓŁKA AKCYJNA"
    assert extract.nip == "7740001454"
    assert extract.regon == "61018820100000"
    assert extract.seat.city == "PŁOCK"
    assert extract.seat.voivodeship == "MAZOWIECKIE"
    assert extract.address.street == "CHEMIKÓW"
    assert extract.address.building_number == "7"
    assert extract.address.postal_code == "09-411"
    assert extract.email == "ZARZAD@ORLEN.PL"
    assert extract.website == "WWW.ORLEN.PL"
    assert extract.share_capital is not None
    assert extract.share_capital.amount == Decimal("1451177561.25")
    assert extract.share_capital.currency == "PLN"
    assert extract.representation is not None
    assert extract.representation.organ == "ZARZĄD"
    assert extract.representation.rule is not None
    assert extract.representation.rule.startswith("- DWAJ CZŁONKOWIE")
    assert extract.representation.members[0].role == "PREZES ZARZĄDU"
    assert extract.representation.members[0].name_masked.endswith("*")
    assert extract.representation.members[0].suspended is False
    assert extract.main_activity is not None
    assert extract.main_activity.code == "19.20.Z"
    assert extract.main_activity.description.startswith("WYTWARZANIE")
    assert extract.other_activities[0].code == "20.1"
    assert extract.registration_date == date(2001, 7, 19)
    assert extract.as_of == date(2026, 10, 9)
    assert extract.last_entry_number == 222
    assert extract.receipt.source == "krs"
    assert extract.receipt.request_id is None
    assert extract.receipt.queried_date == date(2026, 10, 22)
    assert extract.receipt.host == "krs.example"
    dumped = extract.model_dump_json()
    assert "pesel" not in dumped
    assert "PROKURA" not in dumped
