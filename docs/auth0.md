# Auth0 tenant checklist (ADR-0017)

Manual setup, one tenant per environment. Names use the project name, never a brand. The
MCP server needs nothing but the issuer URL (`APP_AUTH_ISSUER`); no client secrets live on it.

## 1. Tenant

- Create the tenant in the **EU** region (the region is chosen at creation and cannot change).
  Name: `<project_name>-<env>`, e.g. `kyb-vetter-dev`.
- Issuer = `https://<tenant>.eu.auth0.com/` (with the trailing slash; this is the `iss` claim).

## 2. API (resource server)

Applications → APIs → Create API:

- Name: `<project_name> MCP`; Identifier (audience): the public MCP URL, exactly
  `https://<domain>/mcp` (this must equal `APP_AUTH_AUDIENCE`, and the `resource` the server
  publishes in its RFC 9728 metadata).
- Signing algorithm **RS256**.
- Settings → **Allow Offline Access** on (refresh tokens for public clients).
- Settings → Access Settings → **Allow Skipping User Consent** off (third-party clients must consent).
- Permissions: none needed in M6 (the server requires no scopes).
- **Third-party applications**: allow third-party (dynamically registered CIMD/DCR) clients to
  access this API and set the default permissions (an empty list is fine, the switch is what
  matters). Without it every `/authorize` fails with `Client "tpc_..." is not authorized to
  access resource server "<identifier>"` and Claude reports "didn't finish" before any login page.

## 3. Tenant settings → General

- **Default Audience** = the API identifier above. Without it, tokens requested without an
  audience are opaque JWE, not verifiable JWTs.
- **OIDC Dynamic Application Registration** on (DCR fallback used by Claude when CIMD is unavailable
  and by Gemini CLI). Note: the registration endpoint is open to anyone on the free plan.
- **Client ID Metadata Document Registration** on; **Dynamic CIMD Registration** on if the plan
  allows it (otherwise `403 not_entitled` and clients fall back to DCR).
- **Resource Parameter Compatibility Profile** on, so the `resource` the MCP client sends
  (RFC 8707) ends up as the token's `aud`.

## 4. Login connection

Authentication → Database (Username-Password) or Social (Google): one connection is enough.
Third-party (dynamically registered) applications only see **domain-level** connections:
Connection → Settings → "Promote to domain level" (or enable it for third-party apps).

## 5. Pre-registered clients (only for clients without DCR/CIMD)

Applications → Create Application → Regular Web Application (confidential) when a client needs
a client id and secret, e.g. Gemini Enterprise. Allowed callback URLs by client:

| Client | Callback |
|--------|----------|
| Claude (claude.ai, desktop, mobile) | `https://claude.ai/api/mcp/auth_callback` |
| ChatGPT | `https://chatgpt.com/connector_platform_oauth_redirect` (needs RFC 9207 `iss`) |
| Gemini Enterprise | `https://vertexaisearch.cloud.google.com/oauth-redirect` |
| MCP Inspector, Gemini CLI, Claude Code | loopback: `http://localhost:*/...`, `http://127.0.0.1:*/...` |

Grant the application the API with the default audience; PKCE S256 is on for public clients.

## 6. Verify

```sh
curl -s https://<tenant>.eu.auth0.com/.well-known/oauth-authorization-server | jq '{
  issuer, code_challenge_methods_supported, token_endpoint_auth_methods_supported,
  client_id_metadata_document_supported, registration_endpoint }'
```

Expect `S256`, `none` among the token-endpoint auth methods, and the CIMD flag when enabled.
A token obtained through the Inspector must be a JWT whose `aud` contains the API identifier:

```sh
echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | jq '{iss, aud, sub, azp, scope, exp}'
```

## 7. Production tenant (ADR-0023)

Repeat steps 1–6 in a second tenant (`<project_name>-prod`, EU) with the prod hostnames
(`https://mcp.<zone>/mcp`) and **leave Dynamic Client Registration off**: Claude and ChatGPT
register through CIMD, Gemini Enterprise through a pre-registered application. The dev tenant
keeps DCR on and its API identifier changes to the dev hostname (`https://mcp.dev.<zone>/mcp`).

## 8. Server side

Terraform `auth_issuer = "https://<tenant>.eu.auth0.com/"` and `public = true`
(`infra/terraform/README.md`). The server fetches
`https://<tenant>.eu.auth0.com/.well-known/jwks.json` and caches the keys for 10 minutes.
