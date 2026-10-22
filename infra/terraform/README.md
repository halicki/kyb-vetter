# Infrastructure (Terraform)

Everything in GCP is created from here; the database is Neon (ADR-0014). Resource names
are prefixed with `var.project_name` (ADR-0004). Layout:

```text
modules/      project, registry, github-wif, neon, secrets, run (service + migrate job), budget
envs/dev/     main root: GCS backend (dev.backend.hcl)
envs/dev/bootstrap/   project + state bucket, LOCAL state (git-ignored)
```

## One-time setup

1. `gcloud auth login && gcloud auth application-default login`
2. Neon API key in the macOS Keychain (`security add-generic-password -s kyb-vetter-neon ...`),
   exported as `NEON_API_KEY` before running Terraform (the fish function `tf-env` does this).
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

Set them with `gh variable set NAME --body "$(terraform -chdir=... output -raw ...)"`.

## Who deploys what

- Terraform (run locally by the owner): project, APIs, registry, WIF, Neon project, secrets,
  Cloud Run service and job configuration, IAM, budget.
- GitHub Actions (keyless, WIF): builds the image, pushes it to Artifact Registry, runs the
  `migrate` job, rolls the new image onto the service. Terraform ignores image changes.

## Calling the dev service

The service has no public invoker until OAuth lands (M6). Cloud Run accepts ID tokens whose
audience is the service URL; plain `gcloud auth print-identity-token` for a user account is
rejected when gcloud runs with a non-default OAuth client. Mint the token by impersonating the
deployer service account (admins hold `roles/iam.serviceAccountTokenCreator` on it):

```sh
URL=$(terraform -chdir=infra/terraform/envs/dev output -raw service_uri)
SA=$(terraform -chdir=infra/terraform/envs/dev output -raw deployer_service_account)
TOK=$(gcloud auth print-identity-token --impersonate-service-account="$SA" --audiences="$URL")
curl -H "Authorization: Bearer $TOK" "$URL/health"
```

The MCP Inspector CLI starts its own OAuth flow on 401, so for scripted checks use the Python
SDK client with an `Authorization` header (see `apps/mcp/README.md`).
