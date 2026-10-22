# ADR-0015: Development infrastructure on GCP with Terraform

Status: Accepted (2026-10-23)

## Context

Milestone 4 hosts the MCP server (Streamable HTTP) on Cloud Run with a Neon
database, deploys from GitHub Actions without service-account keys, and keeps
every resource name derived from `project_name` (ADR-0004). The owner runs
Terraform locally with their own credentials; the project is new and must be
created by Terraform too.

## Decision

- **Two roots per environment.** `envs/dev/bootstrap` (local, git-ignored
  state) creates the project, enables APIs and creates the state bucket;
  `envs/dev` uses that bucket as GCS backend and reads the project through a
  data source. Project id is deterministic: `<name>-<env>-<suffix>`, with the
  suffix from tfvars, so provider blocks can reference it at plan time.
- **Terraform owns configuration, CI owns the image.** The Cloud Run service
  and the `migrate` job are created with a public placeholder image and
  `lifecycle.ignore_changes` on the image; the `deploy-dev` job builds, pushes
  (`:sha` and `:latest`), runs the migration job and rolls the service with
  `google-github-actions/deploy-cloudrun` (image only; env and secrets stay
  as Terraform set them).
- **Keyless CI.** Workload Identity Federation pool + GitHub OIDC provider
  restricted to one repository (`attribute_condition`), impersonating a
  deployer service account with `run.developer`, `artifactregistry.writer` and
  `iam.serviceAccountUser` on the runtime account.
- **Database.** Neon project per environment (Frankfurt, PG 17, Free-plan
  retention 21600 s) through the `kislerdm/neon` 0.18.0 provider (verified by a
  create/destroy round-trip; Neon's own `neondatabase/neon` is the same code
  and will replace the `source` once published). Pooled URI feeds the service,
  direct URI feeds Alembic; both live in Secret Manager, readable only by the
  runtime service account.
- **Dev is private and harmless.** No `allUsers` invoker until OAuth (M6);
  `invoker_members` from tfvars. `APP_MF_BASE_URL` points at the ministry test
  host so dev can never consume the production white-list quota.
- **Hosted transport.** `python -m kyb_vetter_mcp http` serves the SDK's
  Starlette app (stateless, JSON responses) plus `/healthz`. DNS-rebinding
  protection (Host allow-list) is on for local runs and off on Cloud Run
  (`APP_HOST_CHECK=false`): the platform terminates TLS on its own hostnames,
  and the legacy `*.a.run.app` URL carries a hash that cannot be allow-listed
  before the service exists.
- **Image.** Multi-stage build on `ghcr.io/astral-sh/uv:python3.15-trixie-slim`
  (dependency layer from the lockfile, then workspace install with
  `--package kyb-vetter-mcp --no-editable`), runtime `python:3.15-slim-trixie`,
  non-root user, Alembic files copied next to the venv for the job.
- **Budget** with 50/90/100 % e-mail alerts, amount and currency from tfvars.

## Consequences

- Bootstrap state must be backed up by the owner; losing it means importing
  the project and bucket (both deterministic names).
- The first CI deploy replaces the placeholder image; until then `/healthz`
  returns the placeholder's page.
- A prod environment is a copy of `envs/dev` with its own tfvars and backend
  file (M8).
- `gcloud run jobs execute --wait` in CI makes migrations part of the deploy;
  a failing migration stops the roll-out.
