# ADR-0022: Audit retention and housekeeping

Status: Accepted (2026-10-24)

## Context

Audit rows (ADR-0013) hold the proof of a verification: principal, tool,
NIP, official request ids, hashes and the condensed result, which includes
company names and masked board names from public registers. CEIDG data about
natural persons is never stored. The SPEC asks for a retention policy before
production. Polish tax liabilities expire five years after the end of the year
in which the tax was due, which is the period during which a company may have
to show that it verified a counterparty's account before paying.

## Decision

- **Audit rows are kept for five full years counted from the end of the
  event's year** and then deleted: a row from year Y is purged on or after
  1 January of Y+6. The period is a constant in `kyb_vetter_core.retention`,
  not a setting; rows are deleted whole (no partial anonymisation).
- **Housekeeping in the same pass:** quota counters older than seven days and
  expired cache rows are deleted. API keys are never purged automatically
  (revocation is explicit).
- **Mechanism:** `AuditStore.purge_before`, `QuotaStore.purge_before`,
  `CacheStore.purge_expired` on both store implementations; `purge(stores,
  now)` in core; `python -m kyb_vetter_worker purge` as a Cloud Run job
  triggered by Cloud Scheduler every Sunday 03:30 Europe/Warsaw, against the
  direct database endpoint. CI rolls the job image like the flat-file job.

## Consequences

- The first purge with effect happens in 2027 at the earliest (no rows older
  than 2021 exist); the job runs weekly from now so that it is proven.
- Backups: Neon's point-in-time history (hours on the free plan) is the only
  copy; a purged row is gone. Export before purge is a possible M9 item.
- Users cannot request deletion of their own history yet; principals are IdP
  subjects, and such a request is handled by the operator with SQL.
