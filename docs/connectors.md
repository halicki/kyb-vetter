# Connecting AI clients (M6)

The hosted MCP server is `https://<domain>/mcp` (`public_url` output + `/mcp`). It speaks
Streamable HTTP, requires OAuth (Auth0, ADR-0017) and publishes RFC 9728 metadata at
`/.well-known/oauth-protected-resource/mcp`. Clients discover the authorization server from it;
nothing has to be typed besides the URL unless the client lacks dynamic registration.

Status of each guide: **tested** means the flow was run against the dev environment on the date
given; **untested** means the steps come from the vendor's documentation only.

## Claude (claude.ai, desktop, mobile) - tested 2026-10-23 on dev

1. Settings → Connectors → *Add custom connector*.
2. URL: `https://<domain>/mcp`. The dialog detects OAuth from the `401` challenge
   (*Sign in now* - Detected) and CIMD from the Auth0 metadata (*Use Claude's published
   identity* - Detected). Leave both as detected; *Register automatically* (DCR) is the fallback
   when the authorization server does not advertise CIMD.
3. *Add* → Auth0 login (Google or password connection) → consent screen → connector connected.
4. In a chat, enable the connector and ask: "Verify the Polish company with NIP 3245174504"
   (dev points at the ministry's test host, so only synthetic companies are known; the model sees
   `environment: test` in the receipts and says so).

What Claude sends to Auth0 (from the tenant log): `client_id` =
`https://claude.ai/oauth/mcp-oauth-client-metadata` (Claude's CIMD), `redirect_uri` =
`https://claude.ai/api/mcp/auth_callback`, `scope=offline_access`, `prompt=consent`,
`resource=https://<domain>/mcp`, PKCE S256.

Notes: Claude requires a hard `401` on `/mcp` and that the `resource` in the metadata equals the
URL typed in step 2 (hence `APP_AUTH_AUDIENCE = https://<domain>/mcp`). Claude's egress range
`160.79.104.0/21` must reach both the server and Auth0 (no WAF challenge in front of either).
The first attempt failed with "started connecting but didn't finish" before any login page: the
API in Auth0 had no default permissions for third-party applications (see Troubleshooting).

## Gemini CLI - tested: pending (M6a checkpoint)

`~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "<name>": {
      "httpUrl": "https://<domain>/mcp",
      "oauth": { "enabled": true }
    }
  }
}
```

Then `gemini`, `/mcp auth <name>` (browser login through Auth0, loopback redirect), `/mcp list`
shows the tools. Gemini CLI registers through DCR, so the tenant must have *Dynamic Client
Registration* enabled (Auth0 → Settings → Advanced); Auth0 warns that this is open registration
(anyone can create a third-party application in the tenant). Accepted in dev (ADR-0017); prod
should stay CIMD-only.

## ChatGPT (Developer Mode) - untested

Settings → Connectors → Advanced → *Developer mode* on → *Create* → URL `https://<domain>/mcp`,
authentication *OAuth*. ChatGPT registers with its CIMD (`https://chatgpt.com/oauth/client.json`)
and redirects to `https://chatgpt.com/connector_platform_oauth_redirect`, which requires the
authorization server to return RFC 9207 `iss` in authorization responses; verify this in Auth0
before relying on it. Requires a paid ChatGPT plan.

## Gemini Enterprise - untested

Custom MCP server connector: *OAuth 2.0* with a pre-registered client id and secret (Auth0
Regular Web Application, callback `https://vertexaisearch.cloud.google.com/oauth-redirect`),
Authorization URL `https://<tenant>.eu.auth0.com/authorize`, Token URL
`https://<tenant>.eu.auth0.com/oauth/token`, extra authorization parameter
`audience=https://<domain>/mcp` (the client sends no `resource`), PKCE on. No DCR or CIMD.

## MCP Inspector (debugging)

```sh
npx -y @modelcontextprotocol/inspector --transport http https://<domain>/mcp
```

The Inspector runs the same discovery and OAuth flow as the products above and shows every
request, which makes it the first thing to try when a connector fails.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| Client says the server needs no auth | `/mcp` answered 200 instead of 401: `APP_AUTH_ISSUER` unset on the service |
| `invalid_token` after a successful login | `aud` mismatch: Auth0 default audience / API identifier differs from `APP_AUTH_AUDIENCE` |
| Token is not a JWT (five dots, JWE) | Auth0 default audience missing |
| Claude: "Authorization failed" after consent | Auth0 or the server unreachable from Claude's egress range (WAF, proxy) |
| Claude: "started connecting but didn't finish", no login page; Auth0 log / replayed `/authorize` says `Client "tpc_..." is not authorized to access resource server` | The API does not allow third-party (CIMD/DCR) clients: enable third-party access and default permissions on the API in Auth0 (`docs/auth0.md` step 2) |
| 421 from the server | Host header not allow-listed: the hostname is neither `APP_DOMAIN` nor in `APP_EXTRA_ALLOWED_HOSTS` |
