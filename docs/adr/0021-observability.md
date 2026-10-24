# ADR-0021: Structured logs and OpenTelemetry traces

Status: Accepted (2026-10-24)

## Context

Three processes (MCP server, REST API, worker) logged through a bare
`logging.basicConfig`, and `httpx` logged every request URL, which carries
NIPs and account numbers, at INFO. The SPEC asks for structured logs and
tracing with OpenTelemetry in M8. Facts verified on 2026-10-24: Google's
`CloudTraceSpanExporter` and `opentelemetry-propagator-gcp` are deprecated
(the propagator is archived after 2026-10-30); the recommended path is OTLP
over gRPC to `telemetry.googleapis.com` with `google-auth` credentials, the
project chosen by the `gcp.project_id` resource attribute, the sending
service account holding `roles/telemetry.tracesWriter`, and the Telemetry and
Cloud Trace APIs enabled. Cloud Run already ships stdout/stderr to Cloud
Logging; a JSON line with `severity` and `logging.googleapis.com/trace` is
parsed into a structured, trace-correlated entry.

## Decision

- **One `kyb_vetter_core.telemetry` module**, used by every entry point:
  `configure_logging` (root handler, JSON or text by `APP_LOG_FORMAT`),
  `configure_tracing` (tracer provider named `<project_name>-<role>` when
  `APP_TRACE_EXPORT=gcp`), `instrument_engine` for SQLAlchemy. `httpx` is
  instrumented globally; the Starlette (MCP) and FastAPI apps instrument
  themselves in their factories. Without a provider every instrumentation is
  a no-op, so tests and stdio runs carry no exporter.
- **Redaction in the formatter, not at call sites.** Every log line, JSON or
  text, masks digit runs of seven or more (`1234563218` → `12******18`);
  `httpx` request lines are silenced. Register payloads are never logged;
  the audit log keeps their hash.
- **Exporter: OTLP/gRPC to `telemetry.googleapis.com:443`** with
  `google.auth.default()` credentials on the channel; W3C `traceparent`
  propagation (the default), no GCP propagator. Cloud Run's own
  `X-Cloud-Trace-Context` is not consumed; request spans start at the app.
- Dependencies (core): `opentelemetry-api/sdk`, `-exporter-otlp-proto-grpc`,
  `-instrumentation-httpx/-sqlalchemy`, `google-auth`, `grpcio`; apps add
  `-instrumentation-starlette` / `-fastapi`. Terraform sets the three
  `APP_*` variables, enables the APIs and grants the role.

## Consequences

- Log volume stays small (no per-request lines from httpx); request-level
  detail lives in traces, sampled by the SDK default (always-on parent-based)
  — revisit sampling when traffic grows.
- The redaction regex also masks long numeric ids in unrelated messages
  (timestamps are untouched). Acceptable; identifiers belong in traces as
  attributes only when non-sensitive.
- Metrics are not exported yet; Cloud Run's built-in request metrics suffice
  for M8.
- Addendum (2026-10-24, first deploy): `opentelemetry-instrumentation-sqlalchemy`
  0.66b1 refuses SQLAlchemy 2.1 (`< 2.1.0`), so database spans are not
  collected; the dependency was removed and the item is tracked in
  problems.md. httpx and ASGI spans are unaffected.
