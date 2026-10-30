# ADR-0024: One Auth0 tenant for dev and prod

Status: Accepted (2026-10-30). Amends ADR-0023.

## Context

ADR-0023 gave prod its own Auth0 tenant (EU, CIMD only, DCR off). The Auth0
Free plan includes one tenant; a second one requires Essentials (35 USD per
month at the time of writing). Prod has no paying customer yet, and the only
thing the servers need from Auth0 is an issuer URL and a resource server
(API) whose identifier equals the public MCP URL.

## Decision

- **One tenant (`kybvetter-dev.eu.auth0.com`) serves both environments** with
  two APIs: `https://mcp.dev.<zone>/mcp` (dev) and `https://mcp.<zone>/mcp`
  (prod). Prod Terraform sets `auth_issuer` to the dev tenant's issuer; the
  audience is still derived from the prod hostname, so a token minted for dev
  is rejected on prod and vice versa (`aud` check in `core/auth`).
- **Default Audience = the prod identifier.** MCP clients send `resource`
  (RFC 8707) and get the matching audience; the default only matters for
  clients that send none, and those should land on prod, not dev.
- **DCR stays on for both** (the tenant setting is global); CIMD is the
  preferred path, DCR the fallback. The user consent screen remains the gate.
- **Trigger to split:** the first paying customer, or a Free-plan limit that
  bites (one-day log retention, five Organizations). Splitting is the
  ADR-0023 procedure: new tenant, `auth_issuer` change, redeploy; existing
  users log in again.

## Consequences

- Zero Auth0 cost until the trigger; zero code change.
- Dev and prod share the user directory, tenant settings, Actions and logs.
  A dev-side experiment in tenant settings can break prod login: treat the
  tenant as production (environment tag `Production`) and test risky
  changes in a throw-away tenant, never in this one.
- `docs/auth0.md` section 7 describes the single-tenant layout; the
  two-tenant layout stays documented as the target after the trigger.
