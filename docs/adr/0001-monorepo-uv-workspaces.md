# ADR-0001: Monorepo on uv workspaces, business logic only in `core`

Status: Accepted (2026-10-22)

## Context

The product has several deployables (MCP server, REST API, batch worker) that
share one domain model, register clients and validation rules. They must stay
in lock-step: a change to the white-list client must reach every adapter in
the same commit. The project is also a learning vehicle, so the layout should
be conventional and easy to reason about.

## Decision

- One repository, one `uv` workspace, one `uv.lock`.
- Root `pyproject.toml` is a *virtual* project (no `[build-system]`): it holds
  shared tooling config and the `dev` dependency group, nothing installable.
- Members: `packages/core` (`kyb_vetter_core`), `apps/mcp`, `apps/api`,
  `apps/worker`. Apps depend on core via `[tool.uv.sources] ... = { workspace = true }`
  (editable installs).
- Build backend: `uv_build` (src layout, module name derived from the
  distribution name).
- **All business logic lives in `packages/core`.** Apps are thin adapters:
  they translate transport concerns (MCP tool calls, HTTP requests, cron
  triggers) into core calls and back. A reviewer should be able to reject any
  PR that puts a register call or a validation rule outside core.

## Alternatives considered

- Separate repositories per deployable - rejected: cross-repo version
  coordination for a one-person project is pure overhead.
- Single package with sub-modules - rejected: Docker images for the worker
  would ship FastAPI and the MCP SDK, and dependency boundaries would erode.

## Consequences

- `requires-python` is the intersection across members; keep it identical
  everywhere (`>=3.15`).
- `uv sync --all-packages` installs everything; CI uses `--locked`.
- Each app gets its own Dockerfile later (M4/M5); `uv` can export a per-package
  lock subset.
