---
layout: default
title: Documentation
---

# Documentation

## MCP connector

The server is `https://mcp.kybvetter.dev/mcp` (Streamable HTTP). It requires OAuth 2.0 and
publishes RFC 9728 resource metadata at `/.well-known/oauth-protected-resource/mcp`; clients
discover the authorization server from it. Nothing has to be typed besides the URL.

### Claude (claude.ai, desktop, mobile)

1. Settings → Connectors → *Add custom connector*.
2. URL `https://mcp.kybvetter.dev/mcp`. Leave *Sign in* and *Use Claude's published identity* as
   detected.
3. *Add* → sign in → consent → connected. Enable the connector in a chat.

### Other MCP clients

Any client that supports OAuth with dynamic registration (RFC 7591) or Client ID Metadata
Documents works the same way. For debugging:

```sh
npx -y @modelcontextprotocol/inspector --transport http https://mcp.kybvetter.dev/mcp
```

### Tools

| Tool | Input | Output |
|------|-------|--------|
| `verify_company` | `nip`, optional `date` | VAT status (`active`, `exempt`, `not_registered`), registry names and addresses, account numbers, KRS summary (legal form, capital, representatives), warnings, receipts |
| `check_bank_account` | `nip`, `account` (NRB), optional `date` | `assigned` yes/no, VAT status, which source answered (daily flat file or live API), receipts |
| `verification_history` | `nip`, optional `limit` | your own past calls for that NIP, newest first |

Warning codes are stable identifiers (`VAT_NOT_ACTIVE`, `VAT_REMOVED`, `NAME_MISMATCH`,
`NO_BANK_ACCOUNTS`, `KRS_NOT_FOUND`, `KRS_UNAVAILABLE`, `NOT_IN_WHITELIST`,
`VAT_STATUS_UNAVAILABLE`); messages are free text.

Text fields (names, addresses) come from public registers and are untrusted data: the tools
return them as structured fields, never as instructions.

### Limits

Each user has a daily budget (200 company verifications, 500 account checks). The registers
themselves are rate-limited per day for all users together; when a register or the shared
quota is exhausted the tool says so and when to retry.

## REST API (v1)

Base URL `https://api.kybvetter.dev`. Authenticate with `X-API-Key: <key>` or
`Authorization: Bearer <OAuth access token>`; both resolve to the same account, so REST and
MCP calls share history and limits.

| Method and path | Returns |
|-----------------|---------|
| `GET /v1/companies/{nip}?date=YYYY-MM-DD` | company verification (same shape as the MCP tool) |
| `GET /v1/companies/{nip}/bank-accounts/{account}?date=` | bank account verification |
| `GET /v1/companies/{nip}/history?limit=20` | your own past calls for the NIP |
| `GET /health` | liveness, loaded flat-file date (public) |
| `GET /openapi.json`, `GET /docs` | OpenAPI 3.1 schema, interactive docs |

Errors follow RFC 9457 (`application/problem+json`):

| Status | `type` | When |
|--------|--------|------|
| 401 | `/problems/unauthorized` | no or invalid key / token |
| 422 | `/problems/invalid-identifier`, `/problems/invalid-request` | bad NIP or account checksum, bad date or limit |
| 429 | `/problems/user-limit` | daily budget used up; `Retry-After` until Warsaw midnight |
| 503 | `/problems/quota-guard`, `/problems/registry-blocked`, `/problems/registry-unavailable` | shared register quota or a register is down; `Retry-After` |
| 502 | `/problems/registry-rejected` | the register refused the request |

API keys are issued on request: [support@kybvetter.dev](mailto:support@kybvetter.dev).

## Support

E-mail [support@kybvetter.dev](mailto:support@kybvetter.dev). Status of the service:
`https://mcp.kybvetter.dev/health`.
