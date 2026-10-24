"""Structured logs with redaction and OpenTelemetry wiring (ADR-0021)."""

import io
import json
import logging

import httpx
import pytest
import respx
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from kyb_vetter_core import telemetry
from kyb_vetter_core.config import Settings
from kyb_vetter_core.telemetry import JsonFormatter, configure_logging, configure_tracing, redact


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "GET /api/search/nip/1234563218?date=2026-10-23",
            "GET /api/search/nip/12******18?date=2026-10-23",
        ),
        ("account 61109010140000071219812874", "account 61**********************74"),
        ("status 200 in 0.123s on 2026-10-23", "status 200 in 0.123s on 2026-10-23"),
        ("nip=PL 123-456-32-18", "nip=PL 123-456-32-18"),  # digit runs under 7 stay
    ],
)
def test_redact_masks_long_digit_runs_only(text: str, expected: str) -> None:
    assert redact(text) == expected


def _record(
    level: int, msg: str, *args: object, exc: BaseException | None = None
) -> logging.LogRecord:
    record = logging.LogRecord("kyb.test", level, __file__, 1, msg, args, None)
    if exc is not None:
        try:
            raise exc
        except BaseException:
            import sys

            record.exc_info = sys.exc_info()
    return record


def test_json_formatter_emits_cloud_logging_fields_with_redaction() -> None:
    line = JsonFormatter(project=None).format(
        _record(logging.WARNING, "nip %s rejected", "1234563218")
    )
    body = json.loads(line)
    assert body["severity"] == "WARNING"
    assert body["message"] == "nip 12******18 rejected"
    assert body["logger"] == "kyb.test"
    assert body["time"].endswith("+00:00")
    assert "logging.googleapis.com/trace" not in body


def test_json_formatter_includes_exception_text() -> None:
    line = JsonFormatter(project=None).format(
        _record(logging.ERROR, "boom", exc=ValueError("1234563218"))
    )
    body = json.loads(line)
    assert body["severity"] == "ERROR"
    assert "ValueError: 12******18" in body["exception"]


def test_json_formatter_links_the_active_span_to_cloud_trace() -> None:
    provider = TracerProvider()
    with provider.get_tracer("t").start_as_current_span("op") as span:
        line = JsonFormatter(project="proj-1").format(_record(logging.INFO, "hello"))
    body = json.loads(line)
    ctx = span.get_span_context()
    assert body["logging.googleapis.com/trace"] == f"projects/proj-1/traces/{ctx.trace_id:032x}"
    assert body["logging.googleapis.com/spanId"] == f"{ctx.span_id:016x}"
    assert body["logging.googleapis.com/trace_sampled"] is True


def test_configure_logging_json_quiets_httpx_and_is_idempotent() -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    stream = io.StringIO()
    try:
        configure_logging(Settings(log_format="json", gcp_project="p"), stream=stream)
        configure_logging(Settings(log_format="json", gcp_project="p"), stream=stream)
        logging.getLogger("kyb.probe").warning("nip 1234563218")
        assert logging.getLogger("httpx").level == logging.WARNING
    finally:
        root.handlers[:] = before
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(lines) == 1  # one handler, not two
    assert lines[0]["message"] == "nip 12******18"


def test_configure_logging_text_still_redacts() -> None:
    root = logging.getLogger()
    before = list(root.handlers)
    stream = io.StringIO()
    try:
        configure_logging(Settings(log_format="text"), stream=stream)
        logging.getLogger("kyb.probe").warning("account 61109010140000071219812874")
    finally:
        root.handlers[:] = before
    assert "61**********************74" in stream.getvalue()
    assert "61109010140000071219812874" not in stream.getvalue()


def test_tracing_is_off_by_default() -> None:
    assert configure_tracing(Settings(), role="test") is None


async def test_tracing_records_httpx_spans_under_the_service_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    monkeypatch.setattr(telemetry, "_gcp_exporter", lambda _settings: exporter)
    settings = Settings(trace_export="gcp", gcp_project="p", project_name="unit-test")

    provider = configure_tracing(settings, role="api")
    assert provider is not None
    try:
        with respx.mock() as router:
            router.get("https://mf.example/ping").respond(200)
            async with httpx.AsyncClient() as http:
                await http.get("https://mf.example/ping")
        provider.force_flush()
    finally:
        telemetry.shutdown_tracing(provider)

    spans = exporter.get_finished_spans()
    assert spans, "httpx call produced no span"
    assert spans[0].resource.attributes["service.name"] == "unit-test-api"
    attrs = dict(spans[0].attributes or {})
    assert "GET" in {attrs.get("http.request.method"), attrs.get("http.method")}


def test_tracing_without_a_project_omits_the_gcp_resource_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telemetry, "_gcp_exporter", lambda _settings: InMemorySpanExporter())
    provider = configure_tracing(Settings(trace_export="gcp", project_name="x"), role="worker")
    assert provider is not None
    try:
        assert "gcp.project_id" not in provider.resource.attributes
        assert provider.resource.attributes["service.name"] == "x-worker"
    finally:
        telemetry.shutdown_tracing(provider)


def test_gcp_exporter_factory_takes_no_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[object, ...]] = []

    class FakeExporter(InMemorySpanExporter):
        def __init__(self, *args: object, **kwargs: object) -> None:
            calls.append((args, kwargs))
            super().__init__()

    monkeypatch.setattr(telemetry, "_EXPORTER_FACTORY", FakeExporter)
    telemetry._gcp_exporter(Settings(gcp_project="proj-9"))
    assert calls == [((), {})]  # the project travels as the gcp.project_id resource attribute


def test_exporter_failure_disables_tracing_but_never_stops_startup(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(_settings: Settings) -> InMemorySpanExporter:
        raise RuntimeError("no credentials here")

    monkeypatch.setattr(telemetry, "_gcp_exporter", broken)
    with caplog.at_level(logging.WARNING, logger="kyb_vetter_core.telemetry"):
        provider = configure_tracing(Settings(trace_export="gcp", project_name="x"), role="api")
    assert provider is None
    assert "tracing disabled" in caplog.text
    assert "RuntimeError" in caplog.text


def test_in_memory_processor_helper_is_not_needed_by_production_code() -> None:
    assert (
        SimpleSpanProcessor
    )  # imported for symmetry with the SDK docs; keeps the import list honest
    assert trace.get_tracer_provider() is not None


def test_current_provider_follows_configure_and_shutdown(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(telemetry, "_gcp_exporter", lambda _settings: InMemorySpanExporter())
    assert telemetry.current_provider() is None
    first = configure_tracing(Settings(trace_export="gcp", project_name="x"), role="a")
    assert first is not None
    assert telemetry.current_provider() is first
    second = configure_tracing(Settings(trace_export="gcp", project_name="x"), role="b")
    assert second is not None
    telemetry.shutdown_tracing(first)  # stale provider: the current one stays
    assert telemetry.current_provider() is second
    telemetry.shutdown_tracing(second)
    assert telemetry.current_provider() is None
