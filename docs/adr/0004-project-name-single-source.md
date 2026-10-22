# ADR-0004: Project name and domain come from one place per layer

Status: Accepted (2026-10-22)

## Context

`kyb-vetter` is a working name. The brand and domain are undecided, and a
rebrand must be a change of a few lines, not a repository-wide search and
replace with the risk of breaking resource names in the cloud.

## Decision

The name is spelled out exactly once per layer:

| Layer | Location | Mechanism |
|-------|----------|-----------|
| Packaging | root `pyproject.toml` `[project].name` | metadata only |
| Code | `kyb_vetter_core.config.DEFAULT_PROJECT_NAME` (default of `Settings.project_name`) | overridable via `APP_PROJECT_NAME` |
| Infra | Terraform variable `project_name` (M4) | prefix of every GCP resource name |

The public hostname follows the same rule: `Settings.domain` in code
(`APP_DOMAIN`, placeholder `localhost`) and Terraform variable `domain`.
The connector name shown to Claude/ChatGPT/Gemini users is derived from
`Settings`, never typed into code.

Environment variables use the neutral prefix `APP_` so that variable names do
not need to change on rebrand.

Python import packages are named `kyb_vetter_*`. That is a deliberate,
bounded cost: renaming them is a mechanical refactor with no runtime risk,
unlike cloud resource names.

## Consequences

- Code review rule: any literal `kyb-vetter` / `kyb_vetter` outside the three
  locations above (and package names) is a defect.
- Terraform resource names are built as `"${var.project_name}-..."`; the GCP
  project ID will also be derived from it (M4).
- Docs and README may use the working name freely; they are prose, not
  configuration.
