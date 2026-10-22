# kyb-vetter

Counterparty (KYB) verification of Polish companies for AI agents: a hosted
MCP server and REST API over public registers (VAT white list, KRS, CEIDG)
with an audit trail that proves each verification happened.

> Working name. Brand, domain and connector name come from configuration, see
> [ADR-0004](docs/adr/0004-project-name-single-source.md).

## Layout

```txt
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
uv run tach check && uv run tach check-external   # module boundaries, see ADR-0008
```

Tests that reach real endpoints are marked `live` and excluded by default:
`uv run pytest -m live --no-cov` runs them on purpose against the MF test host
and KRS (mind the daily quotas). Unit tests enforce 100% coverage.

## Configuration

Environment variables, prefix `APP_` (see `kyb_vetter_core.config`):

| Variable           | Default      | Meaning                                         |
| ------------------ | ------------ | ----------------------------------------------- |
| `APP_PROJECT_NAME` | `kyb-vetter` | product name used in strings and resource names |
| `APP_DOMAIN`       | `localhost`  | public hostname of the hosted service           |
| `APP_MF_BASE_URL`  | `https://wykazpodatnikowvat.mf.gov.pl` | VAT white-list API (test: `wykazpodatnikowvat-test.mf.gov.pl`) |
| `APP_KRS_BASE_URL` | `https://api-krs.ms.gov.pl` | KRS open API |
| `APP_HTTP_TIMEOUT_S` | `10` | per-request timeout for registry calls |

## Status

Milestone 0 (repository skeleton, tooling, CI, initial ADRs) - done.
Milestone 1 (identifier validation, white-list and KRS clients, domain models) - done.
See `SPEC.md` for the milestone list.
