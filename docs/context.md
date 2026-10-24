# Product and domain context

Durable facts about the product, users and the domain that are not derivable
from the code. Keep entries short; date them.

## Product (2026-10-22)

- Hosted MCP server + REST API for verifying Polish counterparties in public
  registers, with an audit trail (who verified what, when, with which
  official `requestId`). Users install nothing: they add the URL as a
  connector in Claude, ChatGPT or Gemini, or call the REST API.
- Positioning: "KYB / counterparty verification for AI agents" in regulated
  environments.
- Also the owner's learning project for MCP, Terraform and GCP: engineering
  quality and understood decisions matter more than speed.

## Domain constraints (2026-10-22)

- MF VAT white list (host `wykazpodatnikowvat.mf.gov.pl` since 2026-10-15):
  `search` 100 queries/day/IP (up to 30 entities each), `check` 5000
  entities/day/IP, WL2 `status` 50 000/day/IP; exceeding may block the IP
  until midnight. A hosted server shares one IP for all users, so limits are
  an architectural concern. The daily flat file (hashed NIP+account pairs) is
  the basis for offline account checks.
- The registry answers "as of a day" (`date` parameter, Polish local time)
  and refreshes data once per working day, so `(nip, date)` responses are
  stable and cacheable until the next refresh (cache arrives in M3).
- KRS API: no key, about 2 req/s, lookup only by KRS number (taken from the
  white list), persons anonymised, open-data licence allows reuse.
- CEIDG: JWT bearer, data about natural persons (GDPR): pass-through only.

## Warning codes (product vocabulary, from M2)

Stable codes returned in `warnings[].code`; messages are free text for humans.

| Code | Meaning |
|------|---------|
| `NOT_IN_WHITELIST` | NIP unknown to the VAT white list |
| `VAT_NOT_ACTIVE` | VAT status is `exempt` or `not_registered` |
| `VAT_REMOVED` | Entry has a removal date |
| `VAT_STATUS_UNAVAILABLE` | WL2 status endpoint failed during `check_bank_account` |
| `KRS_NOT_FOUND` | White list names a KRS number the register does not know (P and S) |
| `KRS_UNAVAILABLE` | KRS API failed; VAT data returned alone |
| `NAME_MISMATCH` | White-list name differs from KRS name after normalisation |
| `NO_BANK_ACCOUNTS` | No accounts registered on the white list |

## Quota buckets (from M3)

| Bucket | Official limit / day / IP | Our threshold | Charged by |
|--------|---------------------------|---------------|------------|
| `wl_search` | 100 queries (batch of up to 30 NIPs = 1 query) | 90 | `verify_company` (cache miss) |
| `wl_check` | 5 000 | 4 800 | `check_bank_account` (cache miss) |
| `wl_status` | 50 000 | 45 000 | `check_bank_account` status lookup (1 h cache) |

Days follow Europe/Warsaw. `verification_history` and cache hits cost nothing.

## Auth and identity (from M6, 2026-10-23)

- Identity provider: Auth0, tenant per environment in the EU region (ADR-0017). The MCP server
  is an OAuth resource server; the principal is the token's `sub` (e.g. `google-oauth2|123`).
- Hostnames: prod `mcp.kybvetter.dev` / `api.kybvetter.dev`, dev `mcp.dev.kybvetter.dev` / `api.dev.kybvetter.dev` (since 2026-10-24, ADR-0023).
  The zone is a working domain, not the brand (SPEC backlog).
- `verification_history` is per principal: users never see each other's calls.
- Per-user daily budgets (ADR-0019): 200 `verify_company`, 500 `check_bank_account`, cache hits
  included, history free. Error code `USER_LIMIT` in the audit log.
- Connectors verified: Claude custom connector (CIMD). Gemini CLI, ChatGPT and Gemini Enterprise
  are documented but untested (`docs/connectors.md`).

## Environments (from M8, 2026-10-24)

- dev: GCP project `kyb-vetter-dev-*`, MF test host, Auth0 dev tenant (DCR on), hostnames
  `mcp.dev.<zone>` / `api.dev.<zone>`, deploys on every push to `main`.
- prod: own project, Neon, Auth0 tenant (CIMD only), real MF host, `mcp.<zone>` / `api.<zone>`,
  deploys on `v*` tags; deletion protection on. ADR-0023.
- Observability: JSON logs with identifier redaction, traces in Cloud Trace (ADR-0021);
  retention 5 years from year end for audit rows, weekly purge job (ADR-0022).

## REST API (from M7, 2026-10-23)

- Separate Cloud Run service `api.<zone>` from the same image (ADR-0020); resource-shaped
  `GET /v1/companies/{nip}[/bank-accounts/{account}|/history]`, RFC 9457 errors.
- Credentials: `X-API-Key` (issued by the admin CLI, principal = Auth0 `sub` or `client:<name>`)
  or an Auth0 bearer token; same principal model as MCP.

## Flat file facts (verified 2026-10-23)

- URL `https://wykazpodatnikowvat.mf.gov.pl/plikplaski/YYYYMMDD.7z`, ~250 MB, 30 days kept, published ~22:10 UTC the evening before the file date (spec: target 00:01).
- Contents: `naglowek` (date, 5000 transformations, schema), 3.33 M active + 0.35 M exempt SHA-512 digests (sorted), 1 506 bank masks, sidecar `<date>.json.sha512sum`.
- Digest = SHA-512 iterated 5 000 times over the hex text of `YYYYMMDD + NIP + NRB` (or `YYYYMMDD + NIP` without an account). Masks: positions 2-9 routing number, `Y` substituted from the account, `X` kept.
- Spec PDF: `wykazpodatnikowvat.mf.gov.pl/plikplaski/Specyfikacja_techniczna_pliku_płaskiego_2026_09_30.pdf`; the site also offers a SHA-512 calculator for cross-checks.
