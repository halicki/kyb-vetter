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
