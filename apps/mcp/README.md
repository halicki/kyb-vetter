# MCP server (stdio)

Thin adapter over `kyb_vetter_core` exposing two read-only tools:

| Tool | Input | Output |
|------|-------|--------|
| `verify_company` | `nip`, optional `date` (YYYY-MM-DD) | `CompanyVerification`: VAT status, registry name/addresses, KRS summary, warnings, receipts |
| `check_bank_account` | `nip`, `account`, optional `date` | `BankAccountVerification`: `assigned`, VAT status, warnings, receipts |

Both return structured content (JSON schema published in `tools/list`) and
map failures to `ToolError` messages the model can act on (ADR-0011).

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
to query the production register (counts against the daily quota).

## Tests

```sh
uv run pytest apps/mcp evals          # in-memory client, prompt-injection suite, eval scenarios
```

Evals are deterministic scenarios in `evals/scenarios/*.json`; see
`evals/README.md`.
