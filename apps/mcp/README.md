# MCP server (stdio)

Thin adapter over `kyb_vetter_core` exposing two read-only tools:

| Tool | Input | Output |
|------|-------|--------|
| `verify_company` | `nip`, optional `date` (YYYY-MM-DD) | `CompanyVerification`: VAT status, registry name/addresses, KRS summary, warnings, receipts |
| `check_bank_account` | `nip`, `account`, optional `date` | `BankAccountVerification`: `assigned`, VAT status, warnings, receipts |

Both return structured content (JSON schema published in `tools/list`) and
map failures to `ToolError` messages the model can act on (ADR-0011).

Every receipt in `sources` carries the `host` that answered and an
`environment` of `production` or `test`. Anything other than the official MF
and KRS hosts is `test`: the Ministry's sandbox knows only synthetic
companies, so a real NIP reported as "not found" there means nothing.
`skipped` names the registers that were not consulted and why (CEIDG until
a token is configured; KRS when the white list gives no KRS number).

## Run

```sh
uv run python -m kyb_vetter_mcp
```

Logs go to stderr; stdout is the protocol. Configuration via environment
(`APP_` prefix, see `kyb_vetter_core.config`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `APP_PROJECT_NAME` | `kyb-vetter` | Server name shown to clients |
| `APP_MF_BASE_URL` | `https://wykazpodatnikowvat.mf.gov.pl` | VAT white-list host; use `https://wykazpodatnikowvat-test.mf.gov.pl` for experiments |
| `APP_KRS_BASE_URL` | `https://api-krs.ms.gov.pl` | KRS host |
| `APP_HTTP_TIMEOUT_S` | `10` | Per-request timeout |

The production white-list host allows 100 `search` calls per day per IP and
blocks the IP until midnight when exceeded. Point manual experiments at the
test host.

## MCP Inspector

Requires Node 22.19+. Arguments before `--` form the server command; arguments
after `--` are Inspector options.

Web UI:

```sh
npx -y @modelcontextprotocol/inspector uv run --directory /abs/path/to/repo python -m kyb_vetter_mcp \
  -- -e APP_MF_BASE_URL=https://wykazpodatnikowvat-test.mf.gov.pl
```

CLI (scriptable; each call starts a fresh server process):

```sh
npx -y @modelcontextprotocol/inspector --cli \
  uv run --directory /abs/path/to/repo python -m kyb_vetter_mcp \
  -- -e APP_MF_BASE_URL=https://wykazpodatnikowvat-test.mf.gov.pl --format json \
  --method tools/list

npx -y @modelcontextprotocol/inspector --cli \
  uv run --directory /abs/path/to/repo python -m kyb_vetter_mcp \
  -- -e APP_MF_BASE_URL=https://wykazpodatnikowvat-test.mf.gov.pl --format json \
  --method tools/call --tool-name verify_company --tool-args-json '{"nip":"3245174504"}'

npx -y @modelcontextprotocol/inspector --cli \
  uv run --directory /abs/path/to/repo python -m kyb_vetter_mcp \
  -- -e APP_MF_BASE_URL=https://wykazpodatnikowvat-test.mf.gov.pl --format json \
  --method tools/call --tool-name check_bank_account \
  --tool-args-json '{"nip":"3245174504","account":"70506405335016096312945164"}'
```

Use `--tool-args-json`, not `--tool-arg nip=...`: the Inspector JSON-parses
`--tool-arg` values, so an all-digit NIP arrives as an integer and the tool
rejects it (the schema says string, and leading zeros matter).
`3245174504` and the account above come from the Ministry's published test
data; the test host answers with synthetic companies. Exit code `5` means the
tool returned `isError: true` (e.g. an invalid NIP); the message is in
`content[0].text`.

## Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(Settings → Developer → Edit Config) and add an entry under `mcpServers`.
Paths must be absolute; find `uv` with `which uv`.

```json
{
  "mcpServers": {
    "<connector name>": {
      "command": "/opt/homebrew/bin/uv",
      "args": ["run", "--directory", "/abs/path/to/repo", "python", "-m", "kyb_vetter_mcp"],
      "env": {
        "APP_MF_BASE_URL": "https://wykazpodatnikowvat-test.mf.gov.pl"
      }
    }
  }
}
```

Restart Claude Desktop. Server stderr lands in
`~/Library/Logs/Claude/mcp-server-<connector name>.log`. Drop the `env` block
to query the production register (counts against the daily quota). Name the
entry after the host it points at (for example `...-test`): with the sandbox
configured, every real NIP comes back as not on the white list, and only the
`environment: test` field in the receipt tells you why.

## Hosted (Streamable HTTP)

```sh
uv run python -m kyb_vetter_mcp http        # 0.0.0.0:$PORT (default 8080), /mcp and /health
npx -y @modelcontextprotocol/inspector --cli http://localhost:8080/mcp --transport http --method tools/list
```

Stateless, JSON responses, DNS-rebinding protection on: accepted hosts are
`localhost`, `127.0.0.1`, `APP_DOMAIN` and the JSON list in `APP_EXTRA_ALLOWED_HOSTS`.
The container image (`Dockerfile` at the repository root) runs this mode; Cloud Run
deployment is described in `infra/terraform/README.md`.

## Hosted with OAuth (ADR-0017)

Set `APP_AUTH_ISSUER` (and optionally `APP_AUTH_AUDIENCE`, default `https://$APP_DOMAIN/mcp`)
and the server becomes an OAuth 2.1 resource server: `/mcp` requires a bearer access token
issued by that issuer for that audience (RS256, verified against the issuer's JWKS), `/health`
stays public, and RFC 9728 metadata is served at `/.well-known/oauth-protected-resource/mcp`
(and at the root path for clients that probe it). The token's `sub` is the audit principal and
scopes `verification_history` to the caller.

```sh
APP_DOMAIN=mcp.example.dev APP_AUTH_ISSUER=https://tenant.eu.auth0.com/ uv run python -m kyb_vetter_mcp http
curl -i -X POST http://localhost:8080/mcp -H 'Content-Type: application/json' -d '{}'   # 401
npx -y @modelcontextprotocol/inspector --transport http https://mcp.example.dev/mcp         # OAuth in the browser
```

For scripts, pass `Authorization: Bearer <token>` on the `httpx2.AsyncClient` given to
`streamable_http_client` (see `apps/mcp/tests/test_auth_http.py`). Connector setup for Claude,
Gemini CLI and ChatGPT is in `docs/connectors.md`; the Auth0 tenant checklist in `docs/auth0.md`.

## Tests

```sh
uv run pytest apps/mcp evals          # in-memory client, prompt-injection suite, eval scenarios
```

Evals are deterministic scenarios in `evals/scenarios/*.json`; see
`evals/README.md`.
