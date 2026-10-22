# ADR-0007: CI on GitHub Actions with uv

Status: Accepted (2026-10-22)

## Context

Every push should prove lint, format, types and tests before anything is
deployed. Deployment (M4) will reuse the same pipeline with Workload Identity
Federation. The repo is small; one job is enough.

## Decision

Workflow `.github/workflows/ci.yml` on push to `main` and on pull requests:

1. `actions/checkout@v7`
2. `astral-sh/setup-uv@v10` with `enable-cache: true` (reads `.python-version`)
3. `uv sync --locked --all-packages` - fails if `uv.lock` is stale
4. `uv run ruff check .` and `uv run ruff format --check .`
5. `uv run pyright`
6. `uv run pytest` (live tests excluded by config)

Locally the same checks run via `pre-commit` (ruff hooks, pyright as a local
hook through `uv run --frozen`).

## Consequences

- `permissions: contents: read` by default; the deploy job (M4) adds
  `id-token: write` for WIF.
- Concurrency group per ref cancels superseded runs.
- Branch protection on `main` requiring the `check` job is configured on
  GitHub once the remote exists.
