# ADR-0006: Tests never call government APIs; `live` marker opt-in

Status: Accepted (2026-10-22)

## Context

The Ministry of Finance white-list API allows 100 search requests per day per
IP and blocks the IP until midnight when exceeded. The KRS API tolerates about
2 requests per second. A test suite that touches these would burn the daily
budget of the hosted service and could get a developer IP (or CI runner) blocked.

## Decision

- Unit and integration tests mock HTTP at the transport level with `respx`
  (httpx's mock router). Fixtures carry recorded, anonymised responses.
- Any test that must reach a real endpoint is marked `@pytest.mark.live`.
  `pytest` is configured with `-m "not live"` by default and `--strict-markers`;
  live tests run only on explicit `uv run pytest -m live` from a developer
  machine, never in CI.
- `pytest-asyncio` in `asyncio_mode = "auto"`; `--import-mode=importlib` so
  each package can have its own `tests/` directory without name clashes.
- Type checking: Astral's `ty` (beta, `0.0.x`, API may change between
  versions - pinned by `uv.lock`). Warnings fail the run. `packages/core/src`
  gets a strict profile via `[[tool.ty.overrides]]` (all rules at `error`,
  return-type inference, strict equality and generic narrowing); apps and
  tests use the defaults. Chosen over pyright on 2026-10-22 for speed and a
  single-vendor toolchain with ruff and uv.
- Prompt-injection tests for tool outputs are part of the suite from M2 (data
  from registers is untrusted input to the model).

## Consequences

- Recorded fixtures drift from reality; schedule a manual `-m live` run when a
  register announces API changes, and keep fixtures small and readable.
- The MF test environment (`wl-test.mf.gov.pl`) is still a live call for
  rate-limit purposes; it counts as `live`.
