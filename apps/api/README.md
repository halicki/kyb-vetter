# REST API (v1)

Thin FastAPI adapter over `kyb_vetter_core` (ADR-0020). Same verification use cases and the
same JSON models as the MCP tools; runs as its own Cloud Run service (`api.<zone>`).

## Endpoints

| Method and path | Returns |
|-----------------|---------|
| `GET /v1/companies/{nip}?date=YYYY-MM-DD` | `CompanyVerification`: VAT status, registry name and addresses, KRS summary, warnings, receipts |
| `GET /v1/companies/{nip}/bank-accounts/{account}?date=` | `BankAccountVerification`: `assigned`, VAT status, `via` (`flat_file` or `api`), receipts |
| `GET /v1/companies/{nip}/history?limit=20` | `VerificationHistory`: your own past calls for the NIP, newest first |
| `GET /health` | liveness, storage mode, loaded flat-file date (public) |
| `GET /openapi.json`, `GET /docs` | OpenAPI 3.1 schema, interactive docs |

Text fields come from public registers and are untrusted data (ADR-0012): never feed them to a
model as instructions.

## Authentication

Either header works; both resolve to the same principal (the Auth0 `sub`), so REST and MCP calls
of one person share history and daily limits.

```sh
# dev: api.dev.kybvetter.dev (ministry sandbox, synthetic companies); prod: api.kybvetter.dev
curl -H "X-API-Key: $KEY" https://api.dev.kybvetter.dev/v1/companies/3245174504
curl -H "Authorization: Bearer $AUTH0_ACCESS_TOKEN" https://api.dev.kybvetter.dev/v1/companies/3245174504
```

Keys are issued by an administrator (shown once, stored hashed):

```sh
APP_DATABASE_URL=... uv run python -m kyb_vetter_worker keys issue --principal 'client:acme' --name erp
APP_DATABASE_URL=... uv run python -m kyb_vetter_worker keys list --principal 'client:acme'
APP_DATABASE_URL=... uv run python -m kyb_vetter_worker keys revoke --prefix AbCd1234
```

Use the Auth0 `sub` as the principal when the key belongs to a person who also uses MCP;
`client:<name>` for integrations without an Auth0 account.

## Errors (RFC 9457, `application/problem+json`)

| Status | `type` | When |
|--------|--------|------|
| 401 | `/problems/unauthorized` | no or invalid key / token |
| 422 | `/problems/invalid-identifier`, `/problems/invalid-request` | bad NIP or account checksum, bad date or limit |
| 429 | `/problems/user-limit` | your daily budget is used up; `Retry-After` until Warsaw midnight |
| 503 | `/problems/quota-guard`, `/problems/registry-blocked`, `/problems/registry-unavailable` | shared ministry quota or a register is down; `Retry-After` |
| 502 | `/problems/registry-rejected` | the register refused the request |

## Run locally

```sh
uv run python -m kyb_vetter_api        # 0.0.0.0:$PORT (default 8080); same APP_* settings as the MCP server
```
