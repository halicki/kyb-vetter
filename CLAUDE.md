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
- Business logic only in `packages/core`. `apps/*` are thin adapters.
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

## Commands
```sh
uv sync --all-packages
uv run ruff check . && uv run ruff format --check .
uv run pyright
uv run pytest
uv run pre-commit run --all-files
```
