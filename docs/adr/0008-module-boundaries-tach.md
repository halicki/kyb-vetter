# ADR-0008: Module boundaries enforced with tach

Status: Accepted (2026-10-22)

## Context

ADR-0001 states that all business logic lives in `packages/core` and that
apps are thin adapters. Until now this was a review rule only. The intended
import graph is one-way: `apps/* -> core`. Core must never import an app, and
apps must never import each other. Inside core, sub-packages (register
clients, validation, audit) will appear in M1 and should not grow into a
tangle either.

## Decision

Use [tach](https://github.com/gauge-sh/tach) (dev dependency, config under
`[tool.tach]` in the root `pyproject.toml`), run in pre-commit and CI.

Two checks with two scopes:

- `tach check-external` enforces the cross-package direction. Each workspace
  member has its own `pyproject.toml`, so tach treats members as separate
  distributions and validates that every import from another member is
  declared in that member's `[project].dependencies`. Apps declare only
  `kyb-vetter-core`; core declares no app. There is no second list of
  allowed edges to keep in sync.
- `tach check` enforces boundaries *inside* a package via `[[tool.tach.modules]]`.
  Because of the distribution split above it never sees cross-package imports,
  so top-level modules declare `depends_on = []`. Sub-module boundaries in
  core get added as the code arrives. `exact = true` and
  `forbid_circular_dependencies = true` keep the declared graph honest.

Verified on 2026-10-22 by injecting `import kyb_vetter_mcp` into core and
`import kyb_vetter_api` into the MCP app: both fail `tach check-external`;
`import kyb_vetter_core` from an app passes.

## Alternatives considered

- Keep the rule in review only - rejected: it is exactly the kind of rule that
  erodes silently.
- import-linter - viable, but tach also checks declared third-party
  dependencies against real imports (`check-external`), which doubles as a
  guard against undeclared or stale dependencies per member.
- A single `tach.toml` with `depends_on` edges between packages - does not
  work with nested `pyproject.toml` files (see above); the edges would be
  silently ignored.

## Consequences

- `unused_external_dependencies = "warn"`: the scaffold declares
  `kyb-vetter-core` in apps that do not import it yet, and `pydantic` in core
  which only imports `pydantic-settings`. Switch the rule to `"error"` once
  M1 lands and the warnings are gone.
- Adding a dependency to a member now requires importing it; importing a
  package now requires declaring it. `tach sync` is not used - edit
  `pyproject.toml` deliberately.
- New sub-packages in core must be registered as `[[tool.tach.modules]]`
  entries with explicit `depends_on`.
