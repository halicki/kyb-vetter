# Open and closed problems

## Open
- (2026-10-22) MF flat-file specification (hash algorithm, virtual-account
  masks, integrity check) could not be read from the official site (JS-only
  page, PDF not text-extractable). Needed for milestone 5; try the PDF with a
  proper extractor or the HTML spec on the registry site.
- (2026-10-22) NRB routing-number check digit (8-digit `numer rozliczeniowy`)
  algorithm not found in an official source; validation uses IBAN mod-97 only.
- (2026-10-22) KRS API has no citable official documentation page
  (`prs.ms.gov.pl/krs/openApi` renders client-side); behaviour recorded from
  probing: 404/400 as RFC 7807, short numbers zero-padded server-side.
- (2026-10-22) Whether a 30-NIP batch counts as 1 or 30 `search` queries is
  undocumented; measure on the test host before M3.
- (2026-10-22) `gcloud` auth token expired on the dev machine; `terraform`
  not installed. Both needed before milestone 4.
- (2026-10-22) MCP SDK 2.3.0: server-side CIMD support unverified; tasks
  extension, DPoP and `jwt-bearer` grant not implemented. Re-check before
  milestone 6.

## Closed
- (2026-10-22) Python 3.15 wheel availability: all compiled dependencies ship
  `cp315` wheels. See ADR-0002.

## Open since M2 (2026-10-22)

- `check_bank_account` makes two white-list calls (`check` + WL2 `status`); the quota guard in M3 must count them separately (5000/day and 50 000/day).
- httpx logs request URLs (including NIPs) at INFO on stderr. Fine for local stdio; structured logging with redaction is an M8 item.
- MCP Inspector CLI JSON-parses `--tool-arg` values, so an all-digit NIP becomes an integer. Documented in `apps/mcp/README.md`; consider accepting `int` input in the tool schema if real clients do the same.

## Open since M3 (2026-10-22)

- Batch `search_many` is counted as one `wl_search` query, per the ministry's wording ("100 zapytań o maksymalnie 30 podmiotów"); unconfirmed by observation.
- Audit rows keep condensed results (company names, masked board). Retention/GDPR policy and a purge job are M8.
- Neon pooler is transaction-mode PgBouncer; run Alembic against the direct endpoint (M4).

## Open since M4 (2026-10-23)

- ADC quota project must point at a project with open billing, otherwise the GCS backend fails with `UserProjectAccountProblem`; documented in `infra/terraform/README.md`.
- `neondatabase/neon` provider: check the registry each milestone and switch the `source` when published.
- Host allow-listing is off on Cloud Run (`APP_HOST_CHECK=false`); revisit when a custom domain is attached in M6 (then allow-list the domain and turn the check back on).
