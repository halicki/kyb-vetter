---
layout: default
title: KYB Vetter
---

# KYB Vetter

Verify Polish counterparties from inside Claude or from your own systems: VAT white list
status, bank account assignment, KRS extract and a receipt that proves the check happened.
Hosted MCP server and REST API over the official public registers.

## Add it to Claude

1. Settings → Connectors → **Add custom connector**.
2. URL: `https://mcp.kybvetter.dev/mcp`. Claude detects the sign-in flow itself.
3. Sign in, accept the consent screen, and ask in a chat: *"Verify the company with NIP 7740001454"*.

Tools exposed to the model (all read-only):

| Tool | What it does |
|------|--------------|
| `verify_company` | VAT status, registry name and addresses, KRS summary, warnings, receipts |
| `check_bank_account` | Whether a bank account is assigned to the NIP on the white list |
| `verification_history` | Your own past checks of a NIP |

## REST API

The same checks over HTTPS with an API key or an OAuth bearer token:

```sh
curl -H "X-API-Key: $KEY" https://api.kybvetter.dev/v1/companies/7740001454
```

Interactive schema: [api.kybvetter.dev/docs](https://api.kybvetter.dev/docs).

## Sources

- VAT white list (Ministry of Finance): status, accounts, registration history.
- KRS (National Court Register): company extract, representatives.
- CEIDG (sole traders): passed through, never stored.

Every answer carries a receipt (`request id`, timestamp, register) so you can show that the
verification took place.

[Documentation](docs.html) · [Privacy policy](privacy.html) · Contact: [support@kybvetter.dev](mailto:support@kybvetter.dev)
