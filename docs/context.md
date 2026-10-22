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
- MF VAT white list: `search` 100 requests/day/IP, `check` 5000/day/IP;
  exceeding blocks the IP until midnight. A hosted server shares one IP for
  all users, so limits are an architectural concern. The daily flat file
  (hashed NIP+account pairs) is the basis for offline account checks.
- KRS API: no key, about 2 req/s, lookup only by KRS number (taken from the
  white list), persons anonymised, open-data licence allows reuse.
- CEIDG: JWT bearer, data about natural persons (GDPR): pass-through only.
