# ADR-0020: REST API as a separate Cloud Run service

Status: Accepted (2026-10-23)

## Context

M7 exposes the same verification use cases over REST for integrations that do
not speak MCP. ADR-0008 forbids imports between apps, so a single process
hosting both the MCP server and the REST API would need an exception. Users
of the REST API authenticate with API keys (ADR-0019); the owner also wants
Auth0 bearer tokens accepted, so one person has one identity across MCP and
REST. FastAPI is in the SPEC stack; version 0.162 (2026-10) is pure Python,
declares `>=3.10` without a 3.15 classifier, and its dependencies (Starlette,
pydantic) already run on 3.15 in this repository.

## Decision

- **Separate service** `<project_name>-api` from the same image, command
  `python -m kyb_vetter_api`, same runtime service account, secrets and env
  as the MCP service; public invoker (auth is enforced by the app); hostname
  `api.<zone>` through a second domain mapping. ADR-0008 stays unchanged.
- **Resource-shaped v1 endpoints**, all `GET`, all read-only:
  `/v1/companies/{nip}?date=`, `/v1/companies/{nip}/bank-accounts/{account}?date=`,
  `/v1/companies/{nip}/history?limit=`. Bodies are the core result models
  (`CompanyVerification`, `BankAccountVerification`, `VerificationHistory`),
  so MCP and REST return the same JSON and the same OpenAPI schemas.
- **Authentication**: `X-API-Key: <prefix>.<secret>` or
  `Authorization: Bearer <Auth0 JWT>`; both resolve to one principal in core
  (`kyb_vetter_core.principals`). A key wins when both headers are present;
  an invalid credential is never retried with the other one. Missing or
  invalid credentials: `401` with `WWW-Authenticate`.
- **Errors as RFC 9457 problem details** (`application/problem+json`, stable
  `type` URIs relative to the API): invalid identifier or date `422`,
  per-user limit `429` with `Retry-After` until Warsaw midnight, quota guard
  and ministry block `503` with `Retry-After`, register unavailable `503`,
  other register rejections `502`.
- **OpenAPI** at `/openapi.json`, interactive docs at `/docs`; `/health` is
  public and mirrors the MCP service's.
- Keys are issued by an admin CLI in the worker
  (`python -m kyb_vetter_worker keys issue|list|revoke`), not over HTTP.

## Consequences

- Two Cloud Run services to deploy and observe; with `min_instances = 0` in
  dev neither costs anything idle. CI rolls both from one image.
- Register text in REST responses is still untrusted (ADR-0012): REST clients
  that feed it to a model get the same sanitised fields as MCP.
- No self-service key issuing until there is a UI or a concrete need.
