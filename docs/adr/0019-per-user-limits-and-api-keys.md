# ADR-0019: Per-user daily limits and API keys

Status: Accepted (2026-10-23)

## Context

With OAuth in place (ADR-0017) every call has a principal. The SPEC asks for
rate limiting per user, independent of the ministry's per-IP quota (which
the guard of ADR-0013 protects), and for per-user API keys for the REST API
(M7), stored hashed. The hosted server runs as up to two Cloud Run instances,
so counters must live in the database; the MF quota guard already keeps
atomic daily counters there.

## Decision

- **Daily budgets per principal and tool**, counted in the existing
  `quota_counters` table under `user:<principal>:<tool>` buckets through the
  same atomic `try_reserve`; no schema change. Defaults 200 `verify_company`
  and 500 `check_bank_account` per Europe/Warsaw day (`APP_USER_DAILY_LIMIT_*`,
  `0` = unlimited, which is the stdio/local default behaviour only when set
  so). `verification_history` is free.
- **Charged at the service entry**, after local identifier validation and
  before the cache: this is a product limit on calls, not on registry
  traffic, so cache hits count and malformed input does not. A refusal is
  audited as `USER_LIMIT` and told to the model in words distinct from the
  shared quota-guard message.
- **No per-minute limits yet.** Cloud Run's `max_instances = 2` with
  concurrency 40 bounds bursts; finer limits are an M8 item if needed.
- **API keys** are `<prefix>.<secret>` strings shown once: an 8-character
  random prefix for lookup and a 32-byte random secret. Only the SHA-256 of
  the full string is stored (random secrets do not need password stretching);
  comparison is constant-time. A key belongs to a principal (the IdP `sub`),
  so REST and MCP calls of one person share history and budget. Records keep
  `created_at`, `revoked_at` and `last_used_at`; table `api_keys`, migration
  `0003`. M6 ships the model, the stores and the generate/authenticate
  functions; issuing keys (CLI or endpoint) and the `X-API-Key` header arrive
  with the REST API in M7.

## Consequences

- Per-user counters share a table with the MF guard; the `user:` prefix keeps
  them apart and the day column makes them self-expiring in meaning (rows are
  not purged; retention is an M8 item together with the audit log).
- A principal is a string from the IdP; changing identity providers changes
  every principal, budgets and key ownership included (see ADR-0017).
- Without a CLI, keys cannot be issued in dev until M7; the storage and the
  authentication path are nevertheless covered by tests on both store
  implementations.
