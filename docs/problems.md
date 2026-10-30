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
- (2026-10-30) Prod promoted by tag `v1.0.0` (run `deploy-prod` green); services and jobs run
  the tagged image. The dev Claude connector was re-added on `mcp.dev.<zone>`.
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

## Open since M8 (2026-10-24)

- No database spans: `opentelemetry-instrumentation-sqlalchemy` 0.66b1 supports SQLAlchemy
  `< 2.1.0` and we run 2.1.6. Re-add the instrumentation (and `instrument_engine` in
  `storage/postgres.py`) when a release lifts the bound; `skip_dep_check` was not used on purpose.

- Trace sampling is the SDK default (parent-based, always on); set a ratio sampler before
  traffic grows (ADR-0021). No metrics export yet.
- Purged audit rows have no archive; Neon PITR on the free plan is hours. An export-before-purge
  step is a candidate if a customer needs it (ADR-0022).
- Prod shares the dev Auth0 tenant (ADR-0024): shared user directory, settings and one-day
  logs. Split into its own tenant at the first paying customer or when a Free-plan limit bites.

## Open since M7 (2026-10-23)

- The REST API accepts Auth0 tokens issued for the MCP audience (`https://mcp.<zone>/mcp`); a
  dedicated API identifier in Auth0 would separate them, not needed while one IdP API serves both.
- FastAPI 0.162 declares no Python 3.15 classifier (pure Python, runs fine); re-check at upgrades.
- Background job queue is deferred (ADR index, pending decisions): procrastinate on Postgres when
  batch verification, webhooks or long reports appear.

## Open since M6 (2026-10-23)

- Auth0 DCR is enabled in dev for Gemini CLI: an open registration endpoint (anyone can create a
  third-party application; tenant ACLs are Enterprise-only). Such clients only get
  `authorization_code`/`refresh_token`, still need a real login and only the API's default
  permissions, but prod (M8) should keep DCR off and rely on CIMD / pre-registered clients.
- Cloud Run domain mapping is a preview feature (latency caveats, no production support); the
  load balancer path (~18 USD/month) is the prod alternative (ADR-0018).
- Domain ownership verification (Search Console) lives outside Terraform: it is bound to the
  Google account that ran `terraform apply`, and the TXT record in Cloudflare must stay.
- ChatGPT Developer Mode and Gemini Enterprise connectors are documented from vendor docs only,
  untested (no accounts). ChatGPT needs RFC 9207 `iss` (Auth0 advertises it); Gemini Enterprise
  needs a pre-registered confidential client.
- Auth0 tenant configuration is manual (`docs/auth0.md`); the `auth0/auth0` Terraform provider is
  the candidate if the checklist drifts.
- API keys (ADR-0019) have storage and verification but no way to be issued until the REST API
  (M7) adds a CLI/endpoint; `quota_counters` rows for `user:` buckets are never purged (retention
  with the audit log, M8).

## Open since M5 (2026-10-23)

- The flat file also lists `date + NIP` digests for taxpayers without accounts; `verify_company`/status could use them without quota (not implemented).
- The index keeps 16-byte digest prefixes; a false positive needs a 128-bit collision (odds ~1e-26 per day), accepted.
- The file for day D is published ~22:10 UTC on D-1 while the service uses it from the moment the job runs (01:15 Warsaw); between midnight and the job the index is one day old. Acceptable: `queried_date` on the receipt names the file's day.
- `storage/gcs.py` has no unit tests (needs real credentials); it is exercised by the deployed job and a `live` test.
