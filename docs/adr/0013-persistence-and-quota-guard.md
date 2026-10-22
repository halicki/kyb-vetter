# ADR-0013: Persistence, quota guard, audit log and cache

Status: Accepted (2026-10-22)

## Context

The white list allows 100 `search`, 5 000 `check` and 50 000 WL2 `status`
calls per day per source IP and may block the IP until midnight when a limit
is exceeded. A hosted server shares one IP across all users and may run as
several instances, so the counters must live outside the process. Users also
need proof of what was verified (audit) and agents repeat the same questions
within a day (cache).

## Decision

- **Ports, two implementations.** `storage/ports.py` defines `QuotaStore`,
  `AuditStore` and `CacheStore` protocols. `storage/memory.py` is
  process-local; `storage/postgres.py` is SQLAlchemy 2.1 async + asyncpg.
  `open_stores(settings)` picks Postgres when `APP_DATABASE_URL` is set and
  logs a warning otherwise. `Stores.persistent` tells the service (and the
  `verification_history` tool) whether state survives restarts.
- **Quota guard before the network.** `QuotaGuard` counts calls per bucket
  (`wl_search` 100/90, `wl_check` 5000/4800, `wl_status` 50000/45000: official
  limit / our threshold) and per Europe/Warsaw day, through an atomic
  `try_reserve` (`INSERT … ON CONFLICT DO UPDATE … WHERE count < limit
  RETURNING`). At the threshold it raises `QuotaExhaustedError` without any
  request. A `WL-191` (HTTP 429) answer pins the bucket at the threshold for
  the day. A batch `search_many` counts as one query, as the ministry states.
- **Decorator order `Cached(Guarded(Client))`.** Cache hits never spend
  quota. Cache keys are `(source, identifier, queried_date)`; `search`,
  `check` and KRS entries expire at the next Warsaw midnight (the registry
  refreshes once a day), WL2 `status` after one hour. Cached results keep the
  original receipt and are marked `from_cache=True`.
- **Audit every invocation.** `AuditRecorder` writes one `AuditEvent` per
  tool call, success or error: principal (constant `local` until M6), tool,
  normalised NIP, input, outcome, error code (`INVALID_INPUT`, `QUOTA_GUARD`,
  registry code or exception name), registry request ids, sources, SHA-256 of
  the canonical result JSON, the condensed result itself, and whether it came
  from cache. `verification_history` reads this log.
- **Schema owned by Alembic** in `packages/core/alembic` (async env, URL from
  `APP_DATABASE_URL` or `-x url=`). Tests run `downgrade base` + `upgrade head`
  on a real Postgres (`postgres:17-alpine` via `compose.yaml` locally and a
  service container in CI) through `alembic.command` with an injected
  connection.

## Alternatives considered

- Counting quota in memory only: wrong as soon as there are two instances.
- Redis for counters: a second datastore for one table; Postgres row locks
  are enough at our volumes.
- Caching inside the clients: would hide quota accounting; wrappers keep the
  clients honest and testable.

## Consequences

- Full test gate needs a database: `docker compose up -d db` and
  `APP_TEST_DATABASE_URL`; without it the `db` tests skip and the 100%
  coverage gate fails on purpose.
- `check_bank_account` costs one `wl_check` and one `wl_status`; the guard
  tracks them separately.
- Whether the ministry counts a batch as 1 or N queries is still unconfirmed
  (`docs/problems.md`); the guard assumes 1.
- Audit rows contain company names and masked board names; retention and
  GDPR policy are an M8 item.
