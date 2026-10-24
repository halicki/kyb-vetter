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
| [0011](0011-mcp-server-shape.md) | Shape of the MCP server: tools only, structured output, `ToolError` | Accepted |
| [0012](0012-untrusted-registry-data.md) | Register data is untrusted input to the model | Accepted |
| [0010](0010-register-client-design.md) | Register client design: local validation, injected httpx, no retries, receipts, data minimisation | Accepted |
| [0008](0008-module-boundaries-tach.md) | Module boundaries enforced with tach | Accepted |
| [0013](0013-persistence-and-quota-guard.md) | Persistence, quota guard, audit log and cache | Accepted |
| [0014](0014-cloud-database-neon.md) | Cloud database: Neon over Cloud SQL | Accepted |
| [0015](0015-infrastructure-dev.md) | Development infrastructure: two Terraform roots, keyless CI, image rolls | Accepted |
| [0016](0016-flat-file.md) | Daily MF flat file as the primary source for account checks | Accepted |
| [0017](0017-identity-provider-auth0.md) | Auth0 (EU tenant) as the identity provider for MCP OAuth | Accepted |
| [0018](0018-domain-and-dns.md) | Working domain on Cloudflare, Cloud Run domain mapping in dev | Accepted |
| [0019](0019-per-user-limits-and-api-keys.md) | Per-user daily limits and API keys | Accepted |
| [0020](0020-rest-api.md) | REST API as a separate Cloud Run service | Accepted |
| [0021](0021-observability.md) | Structured logs and OpenTelemetry traces | Accepted |
| [0022](0022-retention.md) | Audit retention and housekeeping | Accepted |
| [0023](0023-production-environment.md) | Production environment | Accepted |

## Pending decisions

| Topic | Decide by | Notes |
|-------|-----------|-------|
| Background job queue | When a trigger appears | Not needed while every call is synchronous and sub-second. Triggers: batch verification (hundreds of NIPs), webhooks with retries, long reports (PDF). Candidate: procrastinate (Postgres-backed, reuses Neon). Core services are plain async functions, so tasks call them directly; no event-driven rewrite needed. Noted 2026-10-23. |
