# Claude connector directory listing (draft, 2026-10-31)

Submission: claude.ai/directory/manage → Submit new → MCP connector (Pro plan or higher).
Requirements checked against claude.com/docs/connectors/building/submission.

| Field | Value |
|-------|-------|
| Name | KYB Vetter |
| One-liner (≤200) | Verify Polish companies against the VAT white list and KRS, with a receipt for every check. |
| Server URL | `https://mcp.kybvetter.dev/mcp` |
| Auth type | OAuth (CIMD preferred, DCR fallback) |
| Categories | Data & analytics, Finance (or Productivity), Developer tools |
| Documentation URL | `https://kybvetter.dev/docs.html` |
| Privacy policy URL | `https://kybvetter.dev/privacy.html` |
| Support contact | support@kybvetter.dev |
| Slug | `kyb-vetter` |
| Icon | TODO (square PNG; no size stated in the docs) |
| Test account | Auth0 user in the shared tenant (`docs/auth0.md`), e-mail + password for the reviewer |

## Description (≤2000)

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

## Use cases

- "Is NIP 7740001454 an active VAT payer and who represents the company?"
- "Before I pay this invoice: is account 61 1090 1014 0000 0712 1981 2874 registered to NIP 5451726954?"
- "Show my previous checks of this supplier."

## Data-handling answers (portal step)

Collected: account subject id, identifiers looked up, register responses, timestamps.
Stored: verification history 5 full years after year end (ADR-0022); counters 1 day; logs 30
days. Shared with: Google Cloud, Neon, Auth0 (processors); Polish public registers receive the
identifiers queried. Not sold, no advertising, no model training.

## Before submitting (owner)

1. Repository public, Pages deployed, custom domain set in Settings → Pages (`kybvetter.dev`).
2. Terraform prod apply (apex A/AAAA + www records, `APP_WEBSITE_URL`), tag pushed.
3. Fill the operator's legal name and address in `site/privacy.md`; create `support@` mailbox
   (Cloudflare Email Routing to the owner's inbox is enough).
4. Test account in Auth0; icon file.
