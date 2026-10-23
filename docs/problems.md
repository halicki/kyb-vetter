# Open and closed problems

## Open
- RESOLVED 2026-10-23 (ADR-0016): MF flat-file specification (hash algorithm, virtual-account
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
- RESOLVED 2026-10-23 (ADR-0017): MCP SDK 2.3.0 server-side CIMD support was
  unverified. Not needed: CIMD and DCR are handled by the identity provider;
  the server only verifies tokens (`TokenVerifier`, PRM route). Tasks
  extension, DPoP and `jwt-bearer` remain unimplemented in the SDK.

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
- RESOLVED 2026-10-23 (ADR-0018): host allow-listing was off on Cloud Run; M6 attaches a custom domain, turns the check on and allow-lists the deterministic `run.app` host via `APP_EXTRA_ALLOWED_HOSTS`.

## Open since M5 (2026-10-23)

- The flat file also lists `date + NIP` digests for taxpayers without accounts; `verify_company`/status could use them without quota (not implemented).
- The index keeps 16-byte digest prefixes; a false positive needs a 128-bit collision (odds ~1e-26 per day), accepted.
- The file for day D is published ~22:10 UTC on D-1 while the service uses it from the moment the job runs (01:15 Warsaw); between midnight and the job the index is one day old. Acceptable: `queried_date` on the receipt names the file's day.
- `storage/gcs.py` has no unit tests (needs real credentials); it is exercised by the deployed job and a `live` test.
