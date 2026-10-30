# ADR-0023: Production environment

Status: Accepted (2026-10-24); the separate Auth0 tenant is deferred by ADR-0024

## Context

Dev has been the only environment since M4: one GCP project, one Neon
project, one Auth0 tenant, the ministry's test host, and the bare hostnames
`mcp.<zone>` / `api.<zone>`. M8 needs a production environment that a first
customer can be pointed at, at near-zero idle cost, with a promotion step
that is deliberate rather than every push to `main`.

## Decision

- **`envs/prod` is a copy of `envs/dev`** (same modules, own bootstrap root,
  state bucket, tfvars and backend file) with production defaults:
  `environment = "prod"`, the real white-list host, `protect = true`
  (deletion protection on services and jobs), `max_instances = 3`, budget
  50 PLN. No load balancer: Cloud Run domain mapping as in dev (ADR-0018),
  to be revisited if the preview feature misbehaves.
- **Separate identities and data:** its own GCP project, Neon project, Auth0
  tenant (EU; CIMD and pre-registered clients only, DCR off) and Cloudflare
  records. Nothing is shared with dev except the image registry's build
  pipeline and the zone.
- **Hostnames:** prod takes `mcp.<zone>` and `api.<zone>`; dev moves to
  `mcp.dev.<zone>` and `api.dev.<zone>`. Auth0 API identifiers follow the
  hostnames (`https://mcp.<host>/mcp`).
- **Promotion by tag:** pushing `vX.Y.Z` runs the checks and the reusable
  deploy workflow with the GitHub environment `prod`, whose variables point
  at the prod project; the environment may require a reviewer. `main` keeps
  deploying dev on every push. One image per commit serves both.

## Consequences

- Owner's one-time work: bootstrap apply (project + state bucket), Auth0
  prod tenant per `docs/auth0.md`, tfvars, GitHub environment `prod` with
  its variables, and the dev hostname move (dev tenant identifier, Claude
  connector URL).
- Prod quotas are real: 100 `search` / 5 000 `check` / 50 000 `status` per
  day for every user together; the quota guard and the flat file carry the
  load. Monitor usage before onboarding more than a handful of users.
- Two environments double the manual Auth0 surface; the `auth0/auth0`
  provider remains the candidate if the checklist drifts (problems.md).
