import copy
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import date
from typing import Any

import httpx
import pytest
import respx

from kyb_vetter_core.clients import whitelist as whitelist_module
from kyb_vetter_core.clients.krs import KrsClient
from kyb_vetter_core.clients.whitelist import WhiteListClient
from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import DailyLimitExceededError, InvalidNipError
from kyb_vetter_core.models import VatStatus
from kyb_vetter_core.verification import (
    WARN_KRS_NOT_FOUND,
    WARN_KRS_UNAVAILABLE,
    WARN_NAME_MISMATCH,
    WARN_NO_BANK_ACCOUNTS,
    WARN_NOT_IN_WHITELIST,
    WARN_VAT_NOT_ACTIVE,
    WARN_VAT_REMOVED,
    WARN_VAT_STATUS_UNAVAILABLE,
    VerificationService,
    names_match,
)

MF = "https://mf.example"
KRS = "https://krs.example"
NIP = "1234563218"
NRB = "61109010140000071219812874"
ORLEN_KRS = "0000028860"
TODAY = date(2026, 10, 22)


@pytest.fixture
async def service(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[VerificationService]:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(mf_base_url=MF, krs_base_url=KRS, project_name="unit-test")
    async with httpx.AsyncClient() as http:
        yield VerificationService(WhiteListClient(http, settings), KrsClient(http, settings))


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


@pytest.fixture
def wl_found(fixture_json: Callable[[str], Any]) -> dict[str, Any]:
    payload = copy.deepcopy(fixture_json("whitelist/search_found"))
    payload["result"]["subject"]["krs"] = ORLEN_KRS
    payload["result"]["subject"]["name"] = "ORLEN S.A."
    return payload


@pytest.fixture
def krs_orlen(fixture_json: Callable[[str], Any]) -> dict[str, Any]:
    return fixture_json(f"krs/{ORLEN_KRS}")


def _mock_wl_search(mock_api: respx.MockRouter, payload: Any, status: int = 200) -> respx.Route:
    return mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(status, json=payload)


def _mock_krs(
    mock_api: respx.MockRouter, register: str, payload: Any, status: int = 200
) -> respx.Route:
    return mock_api.get(
        f"{KRS}/api/krs/OdpisAktualny/{ORLEN_KRS}", params={"rejestr": register}
    ).respond(status, json=payload)


# --- verify_company -------------------------------------------------------


async def test_verify_company_full_path_combines_whitelist_and_krs(
    service: VerificationService,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    krs_orlen: Any,
) -> None:
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", krs_orlen)

    result = await service.verify_company(NIP)

    assert result.nip == NIP
    assert result.found is True
    assert result.vat is not None
    assert result.vat.status is VatStatus.ACTIVE
    assert result.vat.name == "ORLEN S.A."
    assert result.vat.krs == ORLEN_KRS
    assert result.vat.account_count == 1
    assert result.krs is not None
    assert result.krs.name == "ORLEN SPÓŁKA AKCYJNA"
    assert result.krs.legal_form == "SPÓŁKA AKCYJNA"
    assert result.krs.seat_city == "PŁOCK"
    assert result.krs.address == "CHEMIKÓW 7, 09-411 PŁOCK"
    assert result.krs.share_capital_amount == "1451177561.25"
    assert result.krs.share_capital_currency == "PLN"
    assert result.krs.main_activity is not None
    assert result.krs.main_activity.startswith("19.20.Z WYTWARZANIE")
    assert result.krs.board[0].role == "PREZES ZARZĄDU"
    assert result.krs.as_of == date(2026, 10, 9)
    assert result.warnings == ()
    assert [s.source for s in result.sources] == ["mf-whitelist", "krs"]
    assert result.sources[0].request_id == "d2n10-84df1a1"
    assert result.sources[1].request_id is None
    assert [s.source for s in result.skipped] == ["ceidg"]
    assert result.sources[0].host == "mf.example"
    assert result.sources[0].environment == "test"
    assert result.sources[1].host == "krs.example"


async def test_verify_company_formats_address_with_unit_number(
    service: VerificationService,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    krs_orlen: Any,
) -> None:
    krs_orlen["odpis"]["dane"]["dzial1"]["siedzibaIAdres"]["adres"]["nrLokalu"] = "3"
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", krs_orlen)

    result = await service.verify_company(NIP)

    assert result.krs is not None
    assert result.krs.address == "CHEMIKÓW 7/3, 09-411 PŁOCK"


async def test_verify_company_uses_explicit_date(
    service: VerificationService,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    krs_orlen: Any,
) -> None:
    route = mock_api.get(f"{MF}/api/search/nip/{NIP}", params={"date": "2026-01-15"}).respond(
        200, json=wl_found
    )
    _mock_krs(mock_api, "P", krs_orlen)

    result = await service.verify_company(NIP, date=date(2026, 1, 15))

    assert route.called
    assert result.sources[0].queried_date == date(2026, 1, 15)


async def test_verify_company_not_in_whitelist(
    service: VerificationService, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    _mock_wl_search(mock_api, fixture_json("whitelist/search_missing"))
    krs_route = mock_api.get(url__regex=rf"{KRS}/.*").respond(200, json={})

    result = await service.verify_company(NIP)

    assert result.found is False
    assert result.vat is None
    assert result.krs is None
    assert [w.code for w in result.warnings] == [WARN_NOT_IN_WHITELIST]
    assert not krs_route.called
    assert len(result.sources) == 1
    assert [s.source for s in result.skipped] == ["ceidg", "krs"]
    assert "white list" in result.skipped[1].reason


@pytest.mark.parametrize(
    ("status_vat", "removal_date", "expected"),
    [
        ("Zwolniony", None, [WARN_VAT_NOT_ACTIVE]),
        ("Niezarejestrowany", None, [WARN_VAT_NOT_ACTIVE]),
        ("Niezarejestrowany", "2024-03-01", [WARN_VAT_NOT_ACTIVE, WARN_VAT_REMOVED]),
    ],
)
async def test_verify_company_flags_inactive_and_removed_vat(
    service: VerificationService,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    krs_orlen: Any,
    status_vat: str,
    removal_date: str | None,
    expected: list[str],
) -> None:
    wl_found["result"]["subject"]["statusVat"] = status_vat
    wl_found["result"]["subject"]["removalDate"] = removal_date
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", krs_orlen)

    result = await service.verify_company(NIP)

    assert [w.code for w in result.warnings] == expected


async def test_verify_company_without_krs_number_skips_krs(
    service: VerificationService, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    wl_found["result"]["subject"]["krs"] = None
    _mock_wl_search(mock_api, wl_found)
    krs_route = mock_api.get(url__regex=rf"{KRS}/.*").respond(200, json={})

    result = await service.verify_company(NIP)

    assert result.krs is None
    assert result.warnings == ()
    assert not krs_route.called
    assert [s.source for s in result.skipped] == ["ceidg", "krs"]
    assert "KRS number" in result.skipped[1].reason


async def test_verify_company_krs_not_found_is_a_warning(
    service: VerificationService, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", {"status": 404}, status=404)
    _mock_krs(mock_api, "S", {"status": 404}, status=404)

    result = await service.verify_company(NIP)

    assert result.found is True
    assert result.krs is None
    assert [w.code for w in result.warnings] == [WARN_KRS_NOT_FOUND]


async def test_verify_company_krs_failure_is_a_warning_not_an_error(
    service: VerificationService, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", {"status": 503}, status=503)

    result = await service.verify_company(NIP)

    assert result.vat is not None
    assert result.krs is None
    assert [w.code for w in result.warnings] == [WARN_KRS_UNAVAILABLE]


async def test_verify_company_falls_back_to_association_register(
    service: VerificationService,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    krs_orlen: Any,
) -> None:
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", {"status": 404}, status=404)
    _mock_krs(mock_api, "S", krs_orlen)

    result = await service.verify_company(NIP)

    assert result.krs is not None
    assert result.warnings == ()


async def test_verify_company_name_mismatch_and_no_accounts(
    service: VerificationService,
    mock_api: respx.MockRouter,
    wl_found: dict[str, Any],
    krs_orlen: Any,
) -> None:
    wl_found["result"]["subject"]["name"] = "ZUPEŁNIE INNA FIRMA SP. Z O.O."
    wl_found["result"]["subject"]["accountNumbers"] = []
    _mock_wl_search(mock_api, wl_found)
    _mock_krs(mock_api, "P", krs_orlen)

    result = await service.verify_company(NIP)

    assert {w.code for w in result.warnings} == {WARN_NAME_MISMATCH, WARN_NO_BANK_ACCOUNTS}
    assert all(w.message for w in result.warnings)


async def test_verify_company_sanitises_register_text(
    service: VerificationService, mock_api: respx.MockRouter, wl_found: dict[str, Any]
) -> None:
    wl_found["result"]["subject"]["krs"] = None
    wl_found["result"]["subject"]["name"] = "ACME​ \x00SP. Z O.O." + "!" * 1000
    wl_found["result"]["subject"]["residenceAddress"] = "ul.\tDługa  1\x07"
    _mock_wl_search(mock_api, wl_found)

    result = await service.verify_company(NIP)

    assert result.vat is not None
    assert result.vat.name is not None
    assert result.vat.name.startswith("ACME SP. Z O.O.!!!")
    assert len(result.vat.name) == 300
    assert "\x00" not in result.vat.name
    assert result.vat.residence_address == "ul. Długa 1"


async def test_verify_company_propagates_whitelist_errors(
    service: VerificationService, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    _mock_wl_search(mock_api, fixture_json("whitelist/error_wl191"), status=429)

    with pytest.raises(DailyLimitExceededError):
        await service.verify_company(NIP)


async def test_verify_company_rejects_invalid_nip_locally(
    service: VerificationService, mock_api: respx.MockRouter
) -> None:
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    with pytest.raises(InvalidNipError):
        await service.verify_company("1234567890")

    assert not route.called


# --- check_bank_account ---------------------------------------------------


async def test_check_bank_account_assigned_with_vat_status(
    service: VerificationService, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        200, json=fixture_json("whitelist/check_tak")
    )
    mock_api.get(f"{MF}/api2/status/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/status_czynny")
    )

    result = await service.check_bank_account(NIP, "PL61 1090 1014 0000 0712 1981 2874")

    assert result.nip == NIP
    assert result.account == NRB
    assert result.assigned is True
    assert result.vat_status is VatStatus.ACTIVE
    assert result.warnings == ()
    assert [s.source for s in result.sources] == ["mf-whitelist", "mf-whitelist-status"]


async def test_check_bank_account_not_assigned_and_inactive_vat(
    service: VerificationService, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    status = copy.deepcopy(fixture_json("whitelist/status_czynny"))
    status["result"]["subject"]["statusVat"] = "Niezarejestrowany"
    mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        200, json=fixture_json("whitelist/check_nie")
    )
    mock_api.get(f"{MF}/api2/status/nip/{NIP}").respond(200, json=status)

    result = await service.check_bank_account(NIP, NRB)

    assert result.assigned is False
    assert result.vat_status is VatStatus.NOT_REGISTERED
    assert [w.code for w in result.warnings] == [WARN_VAT_NOT_ACTIVE]


async def test_check_bank_account_survives_status_endpoint_failure(
    service: VerificationService, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        200, json=fixture_json("whitelist/check_tak")
    )
    mock_api.get(f"{MF}/api2/status/nip/{NIP}").respond(503, text="down")

    result = await service.check_bank_account(NIP, NRB)

    assert result.assigned is True
    assert result.vat_status is None
    assert [w.code for w in result.warnings] == [WARN_VAT_STATUS_UNAVAILABLE]
    assert [s.source for s in result.sources] == ["mf-whitelist"]


async def test_check_bank_account_propagates_check_errors(
    service: VerificationService, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    mock_api.get(f"{MF}/api/check/nip/{NIP}/bank-account/{NRB}").respond(
        429, json=fixture_json("whitelist/error_wl191")
    )

    with pytest.raises(DailyLimitExceededError):
        await service.check_bank_account(NIP, NRB)


async def test_verify_company_marks_official_host_as_production(
    monkeypatch: pytest.MonkeyPatch, mock_api: respx.MockRouter, fixture_json: Callable[[str], Any]
) -> None:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(project_name="unit-test")
    mock_api.get(f"{settings.mf_base_url}/api/search/nip/{NIP}").respond(
        200, json=fixture_json("whitelist/search_missing")
    )
    async with httpx.AsyncClient() as http:
        service = VerificationService(WhiteListClient(http, settings), KrsClient(http, settings))
        result = await service.verify_company(NIP)

    assert result.sources[0].host == "wykazpodatnikowvat.mf.gov.pl"
    assert result.sources[0].environment == "production"


# --- names_match ----------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("ORLEN S.A.", "ORLEN SPÓŁKA AKCYJNA"),
        ("Acme sp. z o.o.", "ACME SPÓŁKA Z OGRANICZONĄ ODPOWIEDZIALNOŚCIĄ"),
        ("Firma  Handlowa\tX", "FIRMA HANDLOWA X"),
        ("ABC Sp.K.", "ABC SPÓŁKA KOMANDYTOWA"),
    ],
)
def test_names_match_tolerates_case_whitespace_and_legal_form_abbreviations(a: str, b: str) -> None:
    assert names_match(a, b)


@pytest.mark.parametrize(("a", "b"), [("ORLEN S.A.", "LOTOS S.A."), (None, "X"), ("X", None)])
def test_names_match_false_for_different_or_missing(a: str | None, b: str | None) -> None:
    assert not names_match(a, b)
