# ADR-0025: Environment-bound workload identity for CI

Status: Accepted (2026-11-10). Amends ADR-0015 and ADR-0023.

## Context

A security review on 2026-11-10 found that the promotion rules of ADR-0023
("prod is deployed from a `v*` tag, the environment may require a reviewer")
existed only in the workflow file:

- The Workload Identity provider of each project accepted any GitHub OIDC
  token whose `repository` claim named this repository, from any workflow,
  job and ref.
- `ci.yml` granted `id-token: write` to the whole workflow, so the `check`
  job, which installs and runs every dependency, could request such a token.
- The GitHub environment `prod` had no reviewer and no tag policy; `main` was
  not protected.

Anything that executes inside a workflow run of this repository (a malicious
dependency release, a re-pointed action tag, a pushed branch) could therefore
become the prod deployer, roll an image of its choice as the runtime service
account and read the database secret. The repository has been public since
2026-10-31. Pull requests from forks were never affected: they get no OIDC
token.

## Decision

- **The provider condition names the environment and the ref**, per project:
  `repository` and `environment` must match, and the ref must be the one that
  environment deploys from: `refs/heads/main` for dev, `refs/tags/v*` for
  prod. `modules/github-wif` takes `github_environment` and `ref_condition`
  (a CEL fragment over `assertion`).
- **`id-token: write` only where a deploy happens.** `ci.yml` drops it at
  workflow level; the two jobs that call `deploy.yml` set it themselves.
  `check` keeps `contents: read`.
- **Actions are pinned to commit SHAs** with the release in a comment;
  Dependabot (already configured for `github-actions`) moves the pins.
- **GitHub settings are the human gate, the cloud condition is the
  enforcement.** Environment `prod`: deployment tags `v*` only and a required
  reviewer. Environment `dev`: branch `main` only. These are set by the owner
  in the repository settings (commands in `infra/terraform/README.md`).
- **The `sub` claim is not used in conditions.** Its format differs for
  repositories created after 2026-07-15 (immutable ids); `repository`,
  `environment` and `ref` are stable.

Considered and rejected: relying on GitHub environment protection alone (not
visible to the cloud, one settings change away from off); binding the service
account to `attribute.environment` instead of tightening the provider (the
provider condition rejects the token earlier and covers every future binding).

## Consequences

- A token from a job outside the named environment, or from another ref, is
  refused by Google before any service account is involved. A wrong condition
  fails closed: the deploy stops at the auth step and Terraform reverts it.
- Roll-out order matters: merge the workflow change first (it works with the
  old condition), apply dev, confirm that a push to `main` still deploys, then
  apply prod and confirm with the next tag.
- Deploying dev from a feature branch, or prod from anything but a `v*` tag,
  now needs a Terraform change on purpose.
- Not addressed here: every Cloud Run service and job still shares one runtime
  service account (`docs/problems.md`).
