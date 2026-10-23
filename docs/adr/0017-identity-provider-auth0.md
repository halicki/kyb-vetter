# ADR-0017: Auth0 (EU tenant) as the identity provider for MCP OAuth

Status: Accepted (2026-10-23)

## Context

The MCP specification (revision 2026-07-28) makes the MCP server an OAuth 2.1
*resource server*: it publishes Protected Resource Metadata (RFC 9728), the
client discovers the authorization server from it (RFC 8414), registers
through a Client ID Metadata Document (CIMD; Dynamic Client Registration is
deprecated but still used by some clients), runs PKCE (S256) with a
`resource` indicator (RFC 8707), and the server validates the audience of
every bearer token. The SPEC forbids writing our own authorization server
and asks for a comparison on MCP-auth compliance, starting cost and EU data
residency. Facts below were verified on 2026-10-23 against vendor docs.

| Provider | MCP support | CIMD / DCR | `aud` = our URL | Free tier | EU region |
|----------|-------------|------------|-----------------|-----------|-----------|
| Auth0 | "Auth for MCP" GA 2026-05 | both (toggles) | yes, with the Resource Parameter Compatibility Profile and a default audience | 25 000 MAU | yes, chosen at tenant creation |
| Descope | Agentic Identity Hub | both | yes | 7 500 MAU | Frankfurt, officially on Growth/Enterprise plans |
| WorkOS AuthKit | yes | both | yes (resource indicators) | 1 000 000 MAU | no; DPA names the USA as storage location |
| Stytch | Connected Apps | DCR, CIMD beta | `aud` = project id, no `resource` support documented | 10 000 MAU | no |
| Google Identity Platform | none | none | none | - | - |

Google Identity Platform is not an authorization server at all (its discovery
document has no `authorization_endpoint`); WorkOS and Stytch keep data in the
US, which contradicts the product's EU/GDPR positioning; Descope's EU region is
not guaranteed on the free plan. Connector clients add their own constraints:
Claude uses CIMD when the authorization-server metadata advertises it and
falls back to DCR otherwise; ChatGPT prefers CIMD; Gemini Enterprise only
accepts a pre-registered client id and secret.

## Decision

- **Auth0, one tenant per environment, created in the EU region.** The
  tenant holds an API (resource server) whose identifier is the public MCP
  URL (`https://<domain>/mcp`), RS256 access tokens, offline access for
  refresh tokens, a default audience, and the toggles for CIMD, DCR and the
  resource-parameter compatibility profile. Setup is manual and recorded as a
  checklist in `docs/auth0.md`; the `auth0/auth0` Terraform provider is a
  possible follow-up, not part of M6.
- **The MCP server is a resource server only.** It verifies JWT access
  tokens against the tenant's JWKS (PyJWT, already in the lockfile as a
  dependency of `mcp`), checks `iss`, `aud`, `exp` and `sub`, and hands the
  SDK an `AccessToken` whose `resource` is our URL. The SDK supplies the 401
  challenge, the RFC 9728 document and the request-scoped principal
  (`get_access_token()`). No client secrets live on the server.
- **Principal = the token's `sub`.** It is the key of per-user state: audit
  rows, `verification_history`, and (M6b) per-user limits and API keys.
  The issuer is kept in the audit input for traceability.
- **Configuration, not code, selects the provider:** `APP_AUTH_ISSUER` and
  `APP_AUTH_AUDIENCE`. Switching to Descope (the runner-up) is an env change
  plus a superseding ADR. Auth is off when the issuer is unset (stdio, tests).

## Consequences

- A manual, toggle-heavy tenant setup; the checklist must be kept current.
- Dynamic Client Registration leaves an open registration endpoint on the
  free plan (tenant ACLs are an Enterprise feature). Acceptable for dev; prod
  (M8) should prefer CIMD-only or pre-registered clients.
- Dynamic CIMD may be unavailable on the free plan (`403 not_entitled`);
  Claude then registers through DCR, which it supports by default.
- Tokens are verified locally; a compromised Auth0 signing key is the trust
  boundary, as with any external IdP.
- ChatGPT (needs RFC 9207 `iss` in authorization responses) and Gemini
  Enterprise (pre-registered client) are documented but untested in M6.
