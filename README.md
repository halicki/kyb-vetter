# kyb-vetter

Counterparty (KYB) verification of Polish companies for AI agents: a hosted
MCP server and REST API over public registers (VAT white list, KRS, CEIDG)
with an audit trail that proves each verification happened.

> Working name. Brand, domain and connector name come from configuration, see
> [ADR-0004](docs/adr/0004-project-name-single-source.md).

## Layout

```
packages/core/    domain: register clients, NIP/REGON/NRB validation, models, limits, audit
apps/mcp/         MCP server (stdio locally, Streamable HTTP in the cloud)
apps/api/         REST API (FastAPI)
apps/worker/      batch jobs (daily MF flat file, later sanctions lists)
infra/terraform/  GCP infrastructure (from milestone 4)
evals/            evaluation sets for MCP tools (from milestone 2)
docs/adr/         architecture decision records
SPEC.md           product and engineering spec, milestones, backlog
```

All business logic lives in `packages/core`; apps are thin adapters.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) 0.13+ (it installs Python 3.15 itself).

```sh
uv sync --all-packages        # create .venv and install every workspace member
uv run pre-commit install     # lint/format/type-check on commit
uv run pytest                 # unit tests (never call real government APIs)
uv run ruff check . && uv run ruff format --check .
uv run ty check
```

Tests that reach real endpoints are marked `live` and excluded by default:
`uv run pytest -m live` runs them on purpose (mind the MF daily quota).

## Configuration

Environment variables, prefix `APP_` (see `kyb_vetter_core.config`):

| Variable | Default | Meaning |
|----------|---------|---------|
| `APP_PROJECT_NAME` | `kyb-vetter` | product name used in strings and resource names |
| `APP_DOMAIN` | `localhost` | public hostname of the hosted service |

## Status

Milestone 0 (repository skeleton, tooling, CI, initial ADRs) - done.
See `SPEC.md` for the milestone list.
