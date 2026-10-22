# ADR-0014: Cloud database: Neon (serverless Postgres) over Cloud SQL

Status: Accepted (2026-10-22), infrastructure in M4

## Context

The service needs Postgres (ADR-0013) in the cloud. Load is tiny and bursty
(a few hundred tool calls a day at first), EU data residency is required, and
the budget for a pre-revenue product should stay near zero while idle.

Prices checked on 2026-10-22 (public pages; US list prices where EU was not
shown):

| Option | Idle cost | Notes |
|--------|-----------|-------|
| Cloud SQL Enterprise `db-f1-micro` | ~$8–10 / month, billed 24/7 | shared core, no SLA; smallest dedicated 1 vCPU ~$49 / month; needs Cloud SQL connector or VPC from Cloud Run |
| Neon Free | $0 (100 CU-hours, 0.5 GB) | scale-to-zero; Frankfurt (EU) region |
| Neon Launch | $0.106 / CU-hour + $0.35 / GB-month, no minimum | typical bursty bill ~$15 / month |

## Decision

Neon, region Frankfurt, one project with a `dev` and a `prod` branch.
Cloud Run connects over TLS with the pooled connection string stored in
Secret Manager. Terraform uses the Neon provider next to the Google provider.

## Consequences

- Two vendors: data lives outside the GCP project (still in the EU). If a
  customer requires single-vendor GCP, Cloud SQL is a drop-in: the code only
  needs a different `APP_DATABASE_URL`.
- Scale-to-zero adds a cold-start of up to a few hundred ms on the first
  query after idle; acceptable for an agent tool.
- Neon's pooler (PgBouncer, transaction mode) is incompatible with
  session-level features; the code uses plain transactions only. Alembic
  migrations run against the direct (non-pooled) endpoint.
- Revisit when sustained load makes an always-on instance cheaper or when
  an enterprise customer asks for Cloud SQL.
