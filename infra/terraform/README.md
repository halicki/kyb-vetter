# Infrastructure (Terraform)

Everything in GCP is created from here; the database is Neon (ADR-0014). Resource names
are prefixed with `var.project_name` (ADR-0004). Layout:

```text
modules/      project, registry, github-wif, neon, secrets, run (service + migrate job), flatfile (bucket, job, scheduler), budget
envs/dev/     main root: GCS backend (dev.backend.hcl)
envs/dev/bootstrap/   project + state bucket, LOCAL state (git-ignored)
```

## One-time setup

1. `gcloud auth login && gcloud auth application-default login`
2. Neon API key in the macOS Keychain (`security add-generic-password -s kyb-vetter-neon ...`),
   exported as `NEON_API_KEY` before running Terraform (the fish function `tf-env` does this).
   Same for the Cloudflare token (`-s kyb-vetter-cloudflare`, exported as `CLOUDFLARE_API_TOKEN`):
   an API token with `Zone:DNS:Edit` on the product zone only.
3. `envs/dev/terraform.tfvars` and `envs/dev/bootstrap/terraform.tfvars` (git-ignored): copy
   `dev.example.tfvars` and fill in `billing_account`, `project_suffix`, `neon_org_id`, e-mails.

## Bootstrap (once per environment)

```sh
terraform -chdir=infra/terraform/envs/dev/bootstrap init
terraform -chdir=infra/terraform/envs/dev/bootstrap apply
terraform -chdir=infra/terraform/envs/dev/bootstrap output -raw tfstate_bucket   # -> dev.backend.hcl
```

Keep `bootstrap/terraform.tfstate` outside git (it is ignored) and back it up; it only
holds the project and the bucket, both of which can also be imported again.

## Main root

The GCS backend and the Google provider bill API calls to the ADC *quota project*; point it at
the new project once bootstrap has created it (a closed billing account on the old quota
project yields `UserProjectAccountProblem` 403s):

```sh
gcloud auth application-default set-quota-project "$(terraform -chdir=infra/terraform/envs/dev/bootstrap output -raw project_id)"
```

```sh
terraform -chdir=infra/terraform/envs/dev init -backend-config=dev.backend.hcl
terraform -chdir=infra/terraform/envs/dev plan
terraform -chdir=infra/terraform/envs/dev apply
```

Outputs feed the GitHub Actions variables (not secrets) used by the deploy job:

| Variable | Output |
|----------|--------|
| `GCP_PROJECT_ID` | `project_id` |
| `GCP_REGION` | region from tfvars |
| `GCP_ARTIFACT_REPO` | `artifact_repository` |
| `GCP_WIF_PROVIDER` | `workload_identity_provider` |
| `GCP_DEPLOYER_SA` | `deployer_service_account` |
| `GCP_SERVICE` | `service_name` |
| `GCP_MIGRATE_JOB` | `migrate_job_name` |
| `GCP_FLATFILE_JOB` | `flatfile_job_name` |
| `GCP_API_SERVICE` | `api_service_name` (enables the REST deploy step, ADR-0020) |
| `MCP_PUBLIC` | `"true"` once `public = true` has been applied (enables the smoke tests) |

Set them with `gh variable set NAME --body "$(terraform -chdir=... output -raw ...)"`.

## Domain (ADR-0018)

One-time, by hand: buy the zone in Cloudflare Registrar, create the API token above, and verify
the zone for the Google account that runs Terraform (`gcloud domains verify <zone>` opens Search
Console; add the TXT record it shows in the Cloudflare zone). Then set `domain` (e.g.
`mcp.<zone>`) and `cloudflare_zone_id` (Cloudflare dashboard, zone overview) in `terraform.tfvars`
and apply: the `domain` module creates the Cloud Run domain mapping and a DNS-only CNAME to
`ghs.googlehosted.com`. The Google-managed certificate usually takes about 15 minutes, up to
24 hours; check with

```sh
gcloud beta run domain-mappings describe --domain "$(terraform -chdir=infra/terraform/envs/dev output -raw public_url | sed 's#https://##')" \
  --region europe-west1 --project "$(terraform -chdir=infra/terraform/envs/dev output -raw project_id)"
```

With `domain` set the app enforces its Host allow-list again (`APP_HOST_CHECK=true`); the
deterministic `run.app` host stays allowed through `APP_EXTRA_ALLOWED_HOSTS`.

## Auth (ADR-0017)

`auth_issuer` (the Auth0 tenant URL with its trailing slash) switches the app into OAuth
resource-server mode: `APP_AUTH_ISSUER` and `APP_AUTH_AUDIENCE = https://<domain>/mcp` are set on
the service. Only then may `public = true` grant `allUsers` the invoker role (a validation rule
refuses the combination without an issuer). Tenant setup is a checklist in `docs/auth0.md`.

## Who deploys what

- Terraform (run locally by the owner): project, APIs, registry, WIF, Neon project, secrets,
  Cloud Run service and job configuration, IAM, budget.
- GitHub Actions (keyless, WIF): builds the image, pushes it to Artifact Registry, runs the
  `migrate` job, rolls the new image onto the service. Terraform ignores image changes.

## Calling the dev service

Once `public = true` is applied, `/health` is public and `/mcp` answers `401` with a
`WWW-Authenticate` challenge pointing at `/.well-known/oauth-protected-resource/mcp`; any OAuth
capable MCP client (Inspector, Claude, Gemini CLI) completes the Auth0 flow from there:

```sh
URL=$(terraform -chdir=infra/terraform/envs/dev output -raw public_url)
curl "$URL/health"
curl -i -X POST "$URL/mcp" -H 'Content-Type: application/json' -d '{}'   # 401 + challenge
npx -y @modelcontextprotocol/inspector --transport http "$URL/mcp"       # browser OAuth flow
```

Before that (`public = false`) only `invoker_members` and the CI deployer may call the service,
and Cloud Run answers `403` to everyone else; the CI smoke test is skipped until `MCP_PUBLIC` is set.
