# Architecture Decision Records

Short records (Status / Context / Decision / Consequences) of decisions that are
expensive to reverse. One file per decision, numbered, never edited after
acceptance - supersede with a new ADR instead.

| # | Title | Status |
|---|-------|--------|
| [0001](0001-monorepo-uv-workspaces.md) | Monorepo on uv workspaces, logic only in `core` | Accepted |
| [0002](0002-python-3.15.md) | Python 3.15 | Accepted |
| [0003](0003-mcp-sdk-2x-spec-2026-07-28.md) | MCP Python SDK 2.x, spec revision 2026-07-28 | Accepted |
| [0004](0004-project-name-single-source.md) | Project name and domain from one place per layer | Accepted |
| [0005](0005-gcp-region-and-project.md) | GCP, region `europe-west1`, project created by Terraform | Accepted |
| [0006](0006-testing-strategy.md) | Tests never hit government APIs; `live` marker | Accepted |
| [0007](0007-ci-github-actions.md) | CI on GitHub Actions with uv | Accepted |
| [0009](0009-mf-whitelist-endpoints-and-hosts.md) | VAT white-list hosts (moved 2026-10-15) and endpoint strategy incl. WL2 status | Accepted |
| [0010](0010-register-client-design.md) | Register client design: local validation, injected httpx, no retries, receipts, data minimisation | Accepted |
| [0008](0008-module-boundaries-tach.md) | Module boundaries enforced with tach | Accepted |

## Pending decisions

| Topic | Decide by | Notes |
|-------|-----------|-------|
| Database hosting: Cloud SQL vs Neon | M3/M4 | Compare cost, EU residency, complexity (connector, IAM auth, Terraform provider). |
| Identity provider for MCP OAuth | M6 | Candidates: WorkOS AuthKit, Auth0, Stytch, Descope, Google Identity Platform. Criteria: MCP auth compliance (RFC 9728 PRM, CIMD, PKCE, refresh tokens), starting cost, EU data residency. |
| Audit-log retention and GDPR policy | M8 | CEIDG data (natural persons) is never persisted; define retention for audit rows. |
| MF rate-limit guard storage (Postgres vs in-memory) | M3 | Hosted server shares one IP; counters must survive restarts and multiple instances. Three counters: `status` (50k), `search` (100 queries, batch counted pessimistically as 30), `check` (5k). |
