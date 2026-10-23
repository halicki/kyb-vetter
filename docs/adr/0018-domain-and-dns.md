# ADR-0018: Working domain on Cloudflare, Cloud Run domain mapping in dev

Status: Accepted (2026-10-23)

## Context

OAuth and the connector clients need a stable public hostname with a
certificate from a public CA (Gemini rejects self-signed certificates; the
`resource` in Protected Resource Metadata must equal the URL users type).
Until M6 the service answered only on its `*.run.app` URL, gated by IAM.
The brand is not decided (SPEC backlog), so the domain is a working one and
must stay a configuration value (ADR-0004: `var.domain`, `APP_DOMAIN`).

Options compared on 2026-10-23 for buying the domain and hosting DNS:
Cloudflare (registrar at wholesale price, `cloudflare/cloudflare` Terraform
provider 5.x, `cf` CLI in beta and `flarectl` in maintenance), OVH (official
Terraform provider, no CLI for DNS), Vercel (DNS only useful for Vercel-hosted
apps). For attaching the hostname to Cloud Run: domain mapping (preview, free,
Google-managed certificate, `europe-west1` supported) versus a global external
Application Load Balancer with a serverless NEG (production-grade, about
18 USD per month before traffic).

## Decision

- **`kybvetter.dev` bought in Cloudflare Registrar** (about 12 USD per year);
  DNS zone on Cloudflare. The purchase has no Terraform resource and is a
  one-time manual step; everything after it is Terraform.
- **DNS records in Terraform** through the Cloudflare provider, token from
  `CLOUDFLARE_API_TOKEN` (Keychain, like `NEON_API_KEY`). Records are
  **DNS-only** (not proxied): Cloudflare's proxy breaks certificate issuance
  and TLS for Cloud Run domain mappings.
- **Cloud Run domain mapping in dev** (`mcp.<zone>` as a static CNAME to
  `ghs.googlehosted.com`), with the domain verified for the project. The
  mapping is a preview feature with known latency caveats; **prod (M8) uses the
  load balancer** if the preview proves inadequate.
- `APP_DOMAIN` becomes the custom hostname; the DNS-rebinding host check is
  switched back on, with the deterministic `run.app` host allow-listed through
  `APP_EXTRA_ALLOWED_HOSTS` for the CI smoke test and for clients that only
  accept `run.app` URLs.

## Consequences

- Rebranding is a new zone plus one tfvars change; nothing in code names the
  domain.
- The owner keeps the Cloudflare API token and the domain verification
  outside Terraform state.
- The `.dev` TLD is HSTS-preloaded: plain HTTP never works, which matches the
  OAuth requirements.
- Certificate issuance after the first apply can take up to 24 hours; the
  README explains how to check the mapping status.
