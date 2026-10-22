"""Domain error hierarchy.

Identifier errors are raised locally, before any network call, so that a
malformed NIP or account number never consumes registry quota.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date


class CoreError(Exception):
    """Base class for every error raised by the domain core."""


class InvalidIdentifierError(CoreError, ValueError):
    """An identifier failed local syntactic / checksum validation."""

    identifier_kind: str = "identifier"

    def __init__(self, value: str, reason: str) -> None:
        self.value = value
        self.reason = reason
        super().__init__(f"invalid {self.identifier_kind} {value!r}: {reason}")


class InvalidNipError(InvalidIdentifierError):
    identifier_kind = "NIP"


class InvalidRegonError(InvalidIdentifierError):
    identifier_kind = "REGON"


class InvalidBankAccountError(InvalidIdentifierError):
    identifier_kind = "bank account (NRB)"


class InvalidKrsError(InvalidIdentifierError):
    identifier_kind = "KRS"


# --- Registry (remote) errors ---------------------------------------------


class RegistryError(CoreError):
    """A registry call failed. ``code`` is the registry's own code (e.g. ``WL-191``)."""

    def __init__(
        self,
        message: str,
        *,
        source: str,
        code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.message = message
        self.source = source
        self.code = code
        self.http_status = http_status
        label = source if code is None else f"{source} {code}"
        super().__init__(f"{label}: {message}")


class RemoteValidationError(RegistryError):
    """The registry rejected an input field (should not happen after local validation)."""

    def __init__(
        self,
        message: str,
        *,
        source: str,
        field: str,
        code: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.field = field
        super().__init__(message, source=source, code=code, http_status=http_status)


class InvalidDateError(RegistryError):
    """The ``date`` query parameter was rejected (empty, malformed, future, before the register)."""


class TooManyIdentifiersError(RegistryError):
    """A batch query exceeded the registry's maximum number of identifiers."""


class DailyLimitExceededError(RegistryError):
    """The registry's daily quota for this IP is exhausted; blocked until midnight."""


class DataUpdatedRetryError(RegistryError):
    """The registry refreshed its data mid-request and asks for one retry (WL-195)."""


class RegistryUpdatingError(RegistryError):
    """The registry is being updated; try again later (WL-196)."""


class RegistryUnavailableError(RegistryError):
    """Server-side failure, timeout or unexpected response from the registry."""


class NotFoundError(RegistryError):
    """The registry has no entry for the given identifier (e.g. KRS 404)."""


# Field rejected by the white-list API per code range (official error table v1.6.1).
_WHITELIST_FIELD_CODES: dict[str, tuple[str, ...]] = {
    "regon": ("WL-104", "WL-105", "WL-106", "WL-107"),
    "bank_account": ("WL-108", "WL-109", "WL-110", "WL-111"),
    "nip": ("WL-112", "WL-113", "WL-114", "WL-115"),
    "name": ("WL-116", "WL-117"),
}
_WHITELIST_CODE_TO_FIELD = {
    code: field for field, codes in _WHITELIST_FIELD_CODES.items() for code in codes
}

_WHITELIST_CODE_TO_CLASS: dict[str, type[RegistryError]] = {
    "WL-100": RegistryUnavailableError,
    "WL-101": InvalidDateError,
    "WL-102": InvalidDateError,
    "WL-103": InvalidDateError,
    "WL-118": InvalidDateError,
    "WL-130": TooManyIdentifiersError,
    "WL-191": DailyLimitExceededError,
    "WL-195": DataUpdatedRetryError,
    "WL-196": RegistryUpdatingError,
    "WL-197": RegistryUnavailableError,
}


def registry_error_from_code(
    code: str, message: str, *, source: str, http_status: int | None = None
) -> RegistryError:
    """Build the domain error matching a white-list ``WL-xxx`` code (unknown codes → ``RegistryError``)."""
    field = _WHITELIST_CODE_TO_FIELD.get(code)
    if field is not None:
        return RemoteValidationError(
            message, source=source, field=field, code=code, http_status=http_status
        )
    cls = _WHITELIST_CODE_TO_CLASS.get(code, RegistryError)
    return cls(message, source=source, code=code, http_status=http_status)


# --- Local quota guard ----------------------------------------------------


class QuotaExhaustedError(CoreError):
    """Our own guard refused a registry call: the daily safety threshold is reached.

    Raised before any network traffic, so the registry never sees the request
    and the IP is not blocked.
    """

    def __init__(self, *, bucket: str, used: int, threshold: int, resets_on: date) -> None:
        self.bucket = bucket
        self.used = used
        self.threshold = threshold
        self.resets_on = resets_on
        super().__init__(
            f"quota guard: {bucket} used {used}/{threshold} today; "
            f"resets at midnight Europe/Warsaw ({resets_on.isoformat()})"
        )
