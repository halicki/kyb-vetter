# ADR-0009: VAT white-list hosts and endpoint strategy

Status: Accepted (2026-10-22)

## Context

The Ministry of Finance moved the white-list API on 2026-10-15. Verified on
2026-10-22 from https://www.gov.pl/web/kas/api-wykazu-podatnikow-vat and the
official Swagger v1.6.1:

- Production: `https://wykazpodatnikowvat.mf.gov.pl/api` (and `/api2`);
  test: `https://wykazpodatnikowvat-test.mf.gov.pl`. The old host
  `wl-api.mf.gov.pl` (named in SPEC.md) is served only until 2026-12-01.
- Quotas per source IP per day: `search` 100 queries of up to 30 entities,
  `check` 5 000 entities, and the new WL2 `GET /api2/status/nip/{nip}`
  50 000 queries. Exceeding a quota may block the IP until midnight.
- WL2 returns only `statusVat` plus `requestId` / timestamps, i.e. exactly the
  "is this an active VAT payer, and prove it" question with 500x the quota of
  `search`.
- Error codes are documented in an official table (`WL-100`..`WL-197`); the
  daily-limit code is `WL-191` with HTTP 429.

## Decision

- Base URL comes from `Settings.mf_base_url` (`APP_MF_BASE_URL`), default
  `https://wykazpodatnikowvat.mf.gov.pl`; the test host is a configuration
  change, not code.
- The client exposes four calls: `status` (WL2), `search`, `search_many`
  (<= 30 NIPs) and `check`. Nothing else from the API is wrapped until a tool
  needs it (no REGON / bank-account searches).
- From M2 on, `verify_company` answers the VAT-status question from WL2 and
  calls `search` only when the full profile (KRS number, addresses, accounts)
  is needed. The quota guard in M3 therefore tracks three counters, not one.
- Every result keeps the official `requestId` and request timestamp in a
  `RegistryReceipt` (ADR-0010).

## Consequences

- SPEC.md's data-source section is outdated on the host; the "Ustalenia"
  section records the correction.
- Whether a 30-NIP batch counts as 1 or 30 of the 100 daily `search` queries
  is not documented; the M3 guard assumes the pessimistic 30 until measured
  on the test host.
- The test host's own quota behaviour is undocumented; live tests run it at
  most a few times per day, by hand.
