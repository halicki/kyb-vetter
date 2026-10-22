# ADR-0002: Python 3.15

Status: Accepted (2026-10-22)

## Context

The spec asks for the newest stable Python, falling back to 3.14 only if
dependencies lack 3.15 wheels. CPython 3.15.0 was released on 2026-10-09
(PEP 790). The risk is compiled dependencies shipping source-only, which would
make Cloud Run image builds slow or fail.

## Decision

Python 3.15 (`.python-version` = `3.15`, `requires-python = ">=3.15"`).

Verified on 2026-10-22 against PyPI that every compiled dependency on the
planned stack publishes `cp315` wheels:

| Package | Version | cp315 wheel |
|---------|---------|-------------|
| pydantic-core | 2.50.1 | yes |
| SQLAlchemy | 2.1.6 | yes |
| asyncpg | 0.32.0 | yes |
| greenlet | 3.5.6 | yes |

Pure-Python packages (mcp 2.3.0, fastapi 0.160.0, httpx 0.28.1, respx 0.23.1,
alembic 1.20.1, pydantic-settings 2.16.1, pytest 9.1.1, pytest-asyncio 1.4.0,
ruff 0.17.1, ty 0.0.91) declare no upper bound.

## Consequences

- Base image for Cloud Run: an official `python:3.15-slim` (or uv's
  `ghcr.io/astral-sh/uv:python3.15-*`) - confirm availability in M4.
- If a later dependency (e.g. a sanctions-list parser) ships no 3.15 wheel,
  record it here and decide between waiting and pinning 3.14.
- ruff infers `target-version = py315` from `requires-python`; ty is pinned to
  `python-version = "3.15"` explicitly.
