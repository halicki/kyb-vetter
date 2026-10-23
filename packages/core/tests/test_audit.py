from datetime import UTC, date, datetime

from kyb_vetter_core.audit import AuditRecorder
from kyb_vetter_core.config import registry_environment
from kyb_vetter_core.errors import DailyLimitExceededError, InvalidNipError, QuotaExhaustedError
from kyb_vetter_core.storage.memory import MemoryAuditStore
from kyb_vetter_core.verification import BankAccountVerification, SourceReceipt

NOW = datetime(2026, 10, 22, 10, 0, tzinfo=UTC)
NIP = "1234563218"


def _receipt(source: str, request_id: str | None, from_cache: bool = False) -> SourceReceipt:
    return SourceReceipt(
        source=source,
        host="https://mf.example",
        environment=registry_environment("https://mf.example"),
        request_id=request_id,
        request_datetime=NOW.isoformat(),
        queried_date=date(2026, 10, 22),
        response_sha256="cd" * 32,
        from_cache=from_cache,
    )


async def test_record_success_stores_result_hash_and_receipts() -> None:
    store = MemoryAuditStore()
    recorder = AuditRecorder(store, now=lambda: NOW)
    result = BankAccountVerification(
        nip=NIP,
        account="61109010140000071219812874",
        assigned=True,
        vat_status=None,
        via="api",
        mask=None,
        warnings=(),
        sources=(
            _receipt("mf-whitelist", "r-1"),
            _receipt("mf-whitelist-status", "r-2", from_cache=True),
        ),
    )

    event = await recorder.record_success(
        principal="local",
        tool="check_bank_account",
        nip=NIP,
        input={"nip": NIP, "account": "x"},
        result=result,
    )

    assert event.ts == NOW
    assert event.outcome == "ok"
    assert event.request_ids == ("r-1", "r-2")
    assert event.sources == ("mf-whitelist", "mf-whitelist-status")
    assert event.from_cache is True
    assert event.result is not None
    assert event.result["assigned"] is True
    assert event.response_sha256 == recorder.digest(result)
    assert await store.history(NIP, principal="local", limit=5) == [event]


async def test_record_error_classifies_exceptions() -> None:
    store = MemoryAuditStore()
    recorder = AuditRecorder(store, now=lambda: NOW)
    cases = [
        (InvalidNipError("x", "bad"), "INVALID_INPUT"),
        (
            QuotaExhaustedError(
                bucket="wl_search", used=90, threshold=90, resets_on=date(2026, 10, 23)
            ),
            "QUOTA_GUARD",
        ),
        (
            DailyLimitExceededError("limit", source="mf-whitelist", code="WL-191", http_status=429),
            "WL-191",
        ),
        (RuntimeError("boom"), "RuntimeError"),
    ]
    for exc, code in cases:
        event = await recorder.record_error(
            principal="local", tool="verify_company", nip=NIP, input={}, exc=exc
        )
        assert event.outcome == "error"
        assert event.error_code == code
        assert event.result is None
        assert event.response_sha256 is None

    assert len(await store.history(NIP, principal="local", limit=10)) == 4


def test_digest_is_stable_for_equal_results() -> None:
    recorder = AuditRecorder(MemoryAuditStore(), now=lambda: NOW)
    a = BankAccountVerification(
        nip=NIP,
        account="a",
        assigned=False,
        vat_status=None,
        via="api",
        mask=None,
        warnings=(),
        sources=(),
    )
    b = BankAccountVerification(
        nip=NIP,
        account="a",
        assigned=False,
        vat_status=None,
        via="api",
        mask=None,
        warnings=(),
        sources=(),
    )
    assert recorder.digest(a) == recorder.digest(b)
    assert len(recorder.digest(a)) == 64
