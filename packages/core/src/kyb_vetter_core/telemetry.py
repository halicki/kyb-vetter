"""Structured logs and OpenTelemetry tracing (ADR-0021).

Logs: one JSON object per line on stderr, with the field names Cloud Logging
understands (``severity``, ``message``, trace and span ids), or a plain text
line for terminals. Every message is redacted: digit runs of seven or more
(NIP, REGON, bank accounts, KRS) keep only their first and last two digits, so
identifiers never land in logs by accident (register responses are logged by
hash only, see the audit log). ``httpx`` request lines are silenced for the
same reason.

Tracing: an SDK tracer provider is installed only when ``trace_export`` asks
for it; spans go to Cloud Trace through OTLP/gRPC on ``telemetry.googleapis.com``
with the runtime service account's credentials (the project is the
``gcp.project_id`` resource attribute). Instrumentation of ``httpx`` and
SQLAlchemy is global; ASGI apps are instrumented by their adapters. With no
provider, every instrumented call is a no-op.
"""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TextIO, override
lazy from collections.abc import Callable

from opentelemetry import trace
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine

    from kyb_vetter_core.config import Settings

OTLP_ENDPOINT = "telemetry.googleapis.com:443"
_DIGITS = re.compile(r"\d{7,}")
_SEVERITY = {
    logging.DEBUG: "DEBUG",
    logging.INFO: "INFO",
    logging.WARNING: "WARNING",
    logging.ERROR: "ERROR",
    logging.CRITICAL: "CRITICAL",
}
_TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_CONFIGURED_MARK = "kyb_vetter_telemetry"


def redact(text: str) -> str:
    """Mask long digit runs: ``1234563218`` -> ``12******18``. Dates and codes stay readable."""
    return _DIGITS.sub(lambda m: f"{m[0][:2]}{'*' * (len(m[0]) - 4)}{m[0][-2:]}", text)


class _RedactingFormatter(logging.Formatter):
    def __init__(self, fmt: str | None = None) -> None:
        super().__init__(fmt)

    @override
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class JsonFormatter(logging.Formatter):
    """Cloud Logging structured records; links the active span when a project is known."""

    def __init__(self, *, project: str | None) -> None:
        super().__init__()
        self._project = project

    @override
    def format(self, record: logging.LogRecord) -> str:
        body: dict[str, Any] = {
            "severity": _SEVERITY.get(record.levelno, "DEFAULT"),
            "message": redact(record.getMessage()),
            "logger": record.name,
            "time": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
        }
        exc_info = record.exc_info
        if isinstance(exc_info, tuple) and exc_info[0] is not None:
            body["exception"] = redact(self.formatException(exc_info))
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid and self._project is not None:
            body["logging.googleapis.com/trace"] = (
                f"projects/{self._project}/traces/{ctx.trace_id:032x}"
            )
            body["logging.googleapis.com/spanId"] = f"{ctx.span_id:016x}"
            body["logging.googleapis.com/trace_sampled"] = bool(ctx.trace_flags.sampled)
        return json.dumps(body, ensure_ascii=False)


def configure_logging(settings: Settings, *, stream: TextIO | None = None) -> None:
    """Install the root handler once (JSON or text, both redacted) and silence httpx request lines."""
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if getattr(h, _CONFIGURED_MARK, False) is False]
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    setattr(handler, _CONFIGURED_MARK, True)
    handler.setFormatter(
        JsonFormatter(project=settings.gcp_project)
        if settings.log_format == "json"
        else _RedactingFormatter(_TEXT_FORMAT)
    )
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _exporter_factory(**kwargs: Any) -> SpanExporter:  # pragma: no cover - needs Google credentials
    import google.auth
    import google.auth.transport.requests
    import grpc
    from google.auth.transport.grpc import AuthMetadataPlugin
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    credentials, _ = google.auth.default()
    plugin = AuthMetadataPlugin(
        credentials=credentials, request=google.auth.transport.requests.Request()
    )
    channel = grpc.composite_channel_credentials(
        grpc.ssl_channel_credentials(), grpc.metadata_call_credentials(plugin)
    )
    return OTLPSpanExporter(endpoint=OTLP_ENDPOINT, credentials=channel, **kwargs)


_EXPORTER_FACTORY: Callable[..., SpanExporter] = _exporter_factory


def _gcp_exporter(settings: Settings) -> SpanExporter:
    return _EXPORTER_FACTORY(project_id=settings.gcp_project)


def configure_tracing(settings: Settings, *, role: str) -> TracerProvider | None:
    """Install a tracer provider named ``<project_name>-<role>``; ``None`` when export is off."""
    if settings.trace_export == "none":
        return None
    attributes: dict[str, Any] = {"service.name": f"{settings.project_name}-{role}"}
    if settings.gcp_project is not None:
        attributes["gcp.project_id"] = settings.gcp_project
    provider = TracerProvider(resource=Resource.create(attributes))
    provider.add_span_processor(BatchSpanProcessor(_gcp_exporter(settings)))
    trace.set_tracer_provider(provider)
    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    return provider


def shutdown_tracing(provider: TracerProvider) -> None:
    HTTPXClientInstrumentor().uninstrument()
    provider.shutdown()


def instrument_engine(engine: AsyncEngine) -> None:
    """Database spans for one engine; a no-op without a provider."""
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
