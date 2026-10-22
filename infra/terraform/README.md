# Infrastructure (Terraform, GCP)

Populated in milestone 4. Planned layout:

```
modules/      reusable modules (project, run-service, run-job, database, secrets, wif, budget)
envs/dev/     dev environment root module
envs/prod/    prod environment root module (milestone 8)
```

Every resource name is prefixed with `var.project_name` (ADR-0004). Region
`europe-west1`, remote state in GCS, GitHub Actions via Workload Identity
Federation (ADR-0005).
