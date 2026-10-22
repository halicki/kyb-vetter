import pytest

from kyb_vetter_core.errors import (
    DailyLimitExceededError,
    DataUpdatedRetryError,
    InvalidDateError,
    RegistryError,
    RegistryUnavailableError,
    RegistryUpdatingError,
    RemoteValidationError,
    TooManyIdentifiersError,
    registry_error_from_code,
)


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("WL-100", RegistryUnavailableError),
        ("WL-101", InvalidDateError),
        ("WL-102", InvalidDateError),
        ("WL-103", InvalidDateError),
        ("WL-118", InvalidDateError),
        ("WL-104", RemoteValidationError),
        ("WL-107", RemoteValidationError),
        ("WL-108", RemoteValidationError),
        ("WL-111", RemoteValidationError),
        ("WL-112", RemoteValidationError),
        ("WL-115", RemoteValidationError),
        ("WL-116", RemoteValidationError),
        ("WL-117", RemoteValidationError),
        ("WL-130", TooManyIdentifiersError),
        ("WL-190", RegistryError),
        ("WL-191", DailyLimitExceededError),
        ("WL-195", DataUpdatedRetryError),
        ("WL-196", RegistryUpdatingError),
        ("WL-197", RegistryUnavailableError),
        ("WL-999", RegistryError),  # unknown code falls back to the base class
    ],
)
def test_whitelist_codes_map_to_domain_errors(code: str, expected: type[RegistryError]) -> None:
    err = registry_error_from_code(code, "message", source="mf-whitelist", http_status=400)
    assert type(err) is expected
    assert err.code == code
    assert err.message == "message"
    assert err.source == "mf-whitelist"
    assert err.http_status == 400


@pytest.mark.parametrize(
    ("code", "field"),
    [("WL-105", "regon"), ("WL-109", "bank_account"), ("WL-113", "nip"), ("WL-117", "name")],
)
def test_remote_validation_error_names_the_rejected_field(code: str, field: str) -> None:
    err = registry_error_from_code(code, "msg", source="mf-whitelist", http_status=400)
    assert isinstance(err, RemoteValidationError)
    assert err.field == field


def test_registry_error_message_includes_source_and_code() -> None:
    err = RegistryError("Limit", source="mf-whitelist", code="WL-191", http_status=429)
    assert str(err) == "mf-whitelist WL-191: Limit"
