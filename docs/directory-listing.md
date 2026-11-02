# Claude connector directory listing (runbook, updated 2026-11-02)

Submission: claude.ai/directory/manage → Submit new → MCP connector. Needs a paid Claude plan
(Pro, Max, Ultra, Team or Enterprise); on Pro the owner submits from their own account and the
listing belongs to that account. Requirements checked 2026-11-02 against
claude.com/docs/connectors/building/submission and `review-criteria`.

Server-side prerequisites are met: every tool has a `title` and `read_only_hint=True`
(`apps/mcp/src/kyb_vetter_mcp/tools.py`), read and write operations are separate tools (all
read-only), errors are actionable `ToolError`s, the server advertises `website_url`, and each
tool was run in the MCP Inspector and as a Claude custom connector against prod (M6/M8).

## Portal steps

### 1. Connection

| Field | Value |
|-------|-------|
| Server URL | `https://mcp.kybvetter.dev/mcp` |
| Users connect to different URLs | No |

### 2. Tools

Synced from the server; nothing to fill.

### 3. Listing

| Field | Value |
|-------|-------|
| Name | KYB Vetter |
| One-liner (≤200) | Verify Polish companies against the VAT white list and KRS, with a receipt for every check. |
| Categories (1–5) | Data & analytics, Finance, Developer tools |
| Documentation URL | `https://kybvetter.dev/docs.html` |
| Privacy policy URL | `https://kybvetter.dev/privacy.html` |
| Support contact | support@kybvetter.dev |
| Icon | `site/icon.png` (512×512 PNG, served at `https://kybvetter.dev/icon.png`; source `site/icon.svg`) |
| Slug (permanent) | `kyb-vetter` |

Description (≤2000):

KYB Vetter lets Claude check a Polish counterparty before you invoice, pay or sign. Give it a
NIP (tax id) and it answers from the official registers: whether the company is an active VAT
payer on the Ministry of Finance white list, which bank accounts are registered to it, what the
National Court Register (KRS) says about its legal form, capital and representatives, and
whether the names across registers agree. Give it a bank account number and it tells you
whether that account is assigned to the NIP, the check Polish law expects before paying a
B2B invoice above 15 000 PLN.

Every answer carries a receipt (request id, timestamp, register, date of the data) so the
verification can be shown later, and your own history of checks is available to the model.
Stable warning codes (VAT_NOT_ACTIVE, VAT_REMOVED, NAME_MISMATCH, NO_BANK_ACCOUNTS, …) make
the result easy to act on. Register text is returned as structured fields, never as
instructions to the model.

All tools are read-only. Sign in with your account; each user has a daily budget. Sole-trader
(CEIDG) data is passed through and never stored. Hosted in the EU.

### 4. Use cases

Primary use cases:

- "Is NIP 7740001454 an active VAT payer and who represents the company?"
- "Before I pay this invoice: is account 61 1090 1014 0000 0712 1981 2874 registered to NIP 5451726954?"
- "Show my previous checks of this supplier."

What users need before connecting: nothing but an account to sign in with (Google, or e-mail
and password); no plan, key or setup. The connector only **reads** data.

### 5. Company

| Field | Value |
|-------|-------|
| Company name | AHA SOFTWARE Arkadiusz Halicki |
| Website | `https://kybvetter.dev` |
| Primary contact | owner's e-mail (review updates) |

### 6. Authentication

| Field | Value |
|-------|-------|
| Authentication requirement | Required for every tool |
| Methods | OAuth 2.1 (PKCE) with Client ID Metadata Documents; Dynamic Client Registration as fallback; Auth0 (EU) is the authorization server |
| OAuth client id / secret | None: Claude registers itself (CIMD/DCR) |

### 7. Data handling

- Underlying API: our own service (`mcp.kybvetter.dev`, same domain as the listing). It
  queries Polish public registers (Ministry of Finance VAT white list, KRS, CEIDG) that are
  open data for reuse; those registers receive only the identifiers looked up.
- Personal health data: no. Sponsored content: no.
- Collected: account subject id, identifiers looked up, register responses, timestamps.
  Stored: verification history 5 full years after year end (ADR-0022); counters 1 day; logs
  30 days. Processors: Google Cloud, Neon, Auth0, Cloudflare (DNS, support@ forwarding).
  Not sold, no advertising, no model training, no conversation data beyond the tool inputs.

### 8. Test & launch

Reviewer instructions (credentials are entered in the portal, visible to reviewers only):

1. Settings → Connectors → Add custom connector → URL `https://mcp.kybvetter.dev/mcp`.
2. Sign in with e-mail and password: user `reviewer@kybvetter.dev`, password from the portal
   field (Auth0 database user, `docs/auth0.md` §9). Accept the consent screen.
3. Try: "Verify the company with NIP 7740001454" (`verify_company`), "Is account
   61 1090 1014 0000 0712 1981 2874 registered to NIP 5451726954?" (`check_bank_account`),
   "Show my previous checks of NIP 7740001454" (`verification_history`).
4. The reviewer account is pre-populated with a few verifications so the history is not empty.

Confirmation: every tool was run in the MCP Inspector and as a Claude custom connector.

### 9. Compliance

Seven acknowledgments, all required: directory guidelines; first-party API usage (our own
server, own domain); no financial transactions (read-only lookups); no AI media generation;
prompt-injection handling (register text returned as structured fields, tested in CI); no
conversation data collection beyond tool inputs; public documentation at the docs URL.

## Owner steps before submitting

1. **support@ mailbox** (Cloudflare dashboard, zone `kybvetter.dev` → Email → Email Routing →
   Get started): add the owner's mailbox as a destination address and click the link in the
   verification e-mail; create the custom address `support@kybvetter.dev` → Send to the
   destination; let Cloudflare add the MX, SPF TXT and DKIM TXT records (they live outside
   Terraform, like the Search Console TXT; `docs/problems.md`). Test by e-mailing `support@`.
2. **Reviewer account** in Auth0: `docs/auth0.md` §9.
3. **Populate it**: add the connector in Claude signed in as the reviewer and run the three
   example prompts above, so `verification_history` returns rows.
4. **Terraform/Pages**: nothing; the site, DNS and `APP_WEBSITE_URL` are live since `v1.2.0`.
   After this change is pushed, confirm `https://kybvetter.dev/icon.png` and the operator name
   on `https://kybvetter.dev/privacy.html`.
5. Paid plan on claude.ai, then fill the portal from this file. Escalations:
   `mcp-review@anthropic.com`.
