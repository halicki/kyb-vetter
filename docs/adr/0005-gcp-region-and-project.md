# ADR-0005: GCP, region `europe-west1`, project created by Terraform

Status: Accepted (2026-10-22)

## Context

Runtime target is Google Cloud (Cloud Run service + job, Cloud SQL or Neon,
Secret Manager, Scheduler, GCS, Artifact Registry). The owner has no existing
project to reuse and wants to learn Terraform on GCP. The data processed is
public register data plus per-user audit rows; EU residency is a requirement
for the regulated-customer positioning.

## Decision

- Region **`europe-west1`** (Belgium). Chosen over `europe-central2` (Warsaw)
  because it is cheaper for Cloud Run / Cloud SQL and all needed services and
  tiers are available there without waiting. It is in the EU, so residency
  holds. Latency to Polish government APIs is irrelevant at our request
  volumes.
- A **new GCP project is created by Terraform** (`google_project`) under the
  owner's account, attached to a billing account passed as a variable
  (`billing_account`, never committed). The project ID is derived from
  `var.project_name` plus an environment suffix.
- Terraform remote state in a GCS bucket; GitHub Actions authenticates via
  Workload Identity Federation (no service-account keys in the repo).
- Budget with alert thresholds is part of the Terraform root module from the
  first apply.

## Consequences

- Bootstrap chicken-and-egg: the state bucket must exist before the first
  `terraform init` with the GCS backend. M4 includes a documented one-time
  bootstrap step (local state -> migrate to GCS) or a tiny separate bootstrap
  module.
- Creating projects requires the owner's `gcloud` identity to hold
  `roles/billing.user` on the billing account; organisation-less (personal)
  accounts can still create projects.
- Before M4: refresh `gcloud auth login` (token found expired on 2026-10-22)
  and install `terraform` locally (not installed).
