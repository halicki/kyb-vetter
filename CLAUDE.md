# kyb-vetter - project rules for Claude Code

Read `SPEC.md` and `docs/adr/README.md` before any non-trivial task.

## Language
- Talk to the owner in Polish.
- Code, docstrings, commit messages, README and ADRs in English.

## Working mode
- Work milestone by milestone (list in `SPEC.md`). After each milestone: stop,
  show what was built, explain 3-5 key decisions (why, alternatives, costs),
  wait for an explicit OK.
- Do not implement backlog items. Ask before adding a dependency outside the
  stack listed in `SPEC.md`.
- Check current documentation before using any library or API (MCP SDK 2.x,
  MCP spec 2026-07-28, MF / KRS / CEIDG APIs, Terraform providers). Do not
  rely on memory.
- Record architectural decisions as ADRs in `docs/adr/` (Status / Context /
  Decision / Consequences) and add them to the index.

## Hard rules
- TDD for every function in `packages/core` (and by default everywhere):
  write the failing test first, watch it fail, write the minimal code, watch
  it pass, refactor. Coverage is a 100% gate (`fail_under = 100`); bootstrap
  code in apps may carry `# pragma: no cover` with a reason.
- Business logic only in `packages/core`. `apps/*` are thin adapters.
  Import direction `apps -> core` only, enforced by tach (ADR-0008).
- Tests never call real government APIs. Mock HTTP with `respx`. Live tests
  carry `@pytest.mark.live` and are excluded by default.
- The product name is configured, not hard-coded (ADR-0004). Never write
  `kyb-vetter` in strings, URLs or resource names; use `Settings` / Terraform
  `var.project_name`.
- No `print()` and nothing on stdout in the MCP stdio path (ruff `T20`).
- Data returned by registers (names, addresses) is untrusted input to the
  model: keep tool outputs structured and concise; prompt-injection tests are
  mandatory for tool outputs.
- CEIDG data concerns natural persons (GDPR): pass-through only, never stored.

## Commits
- Conventional Commits: `type(scope): summary` with types `feat`, `fix`,
  `docs`, `chore`, `ci`, `refactor`, `test`, `build`. Lower-case imperative
  summary. Never rewrite pushed history.

## Commands
```sh
uv sync --all-packages
uv run ruff check . && uv run ruff format --check .
uv run ty check
uv run tach check && uv run tach check-external
docker compose up -d db && export APP_TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app
uv run pytest                # unit tests + 100% coverage gate (db tests need the URL above)
uv run pytest -m live --no-cov  # by hand only: MF test host + KRS
uv run pre-commit run --all-files
```
