# Connecting AI clients (M6)

The hosted MCP server is `https://<domain>/mcp` (`public_url` output + `/mcp`). It speaks
Streamable HTTP, requires OAuth (Auth0, ADR-0017) and publishes RFC 9728 metadata at
`/.well-known/oauth-protected-resource/mcp`. Clients discover the authorization server from it;
nothing has to be typed besides the URL unless the client lacks dynamic registration.

Status of each guide: **tested** means the flow was run against the dev environment on the date
given; **untested** means the steps come from the vendor's documentation only.

## Claude (claude.ai, desktop, mobile) - tested: pending (M6a checkpoint)

1. Settings → Connectors → *Add custom connector*.
2. Name: anything; URL: `https://<domain>/mcp`.
3. Advanced: leave *Use Claude's published identity* (CIMD) selected; Claude falls back to
   automatic registration (DCR) when the authorization server does not advertise CIMD.
4. *Add* → Claude opens the Auth0 login; sign in → consent → connector shows as connected.
5. In a chat, enable the connector and ask: "Verify the Polish company with NIP 3245174504"
   (dev points at the ministry's test host, so only synthetic companies are known).

Notes: Claude requires a hard `401` on `/mcp` and that the `resource` in the metadata equals the
URL typed in step 2 (hence `APP_AUTH_AUDIENCE = https://<domain>/mcp`). Claude's egress range
`160.79.104.0/21` must reach both the server and Auth0 (no WAF challenge in front of either).

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
shows the tools. Gemini CLI registers through DCR.

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
| 421 from the server | Host header not allow-listed: the hostname is neither `APP_DOMAIN` nor in `APP_EXTRA_ALLOWED_HOSTS` |
