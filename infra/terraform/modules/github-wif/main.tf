# Keyless deploys from GitHub Actions: the workflow exchanges its OIDC token for the deployer
# service account through Workload Identity Federation. The token must come from one repository,
# from a job bound to one GitHub environment, on a ref that environment deploys from (ADR-0025):
# a job elsewhere in the repository (a test job, another branch) cannot become the deployer.
locals {
  attribute_condition = join(" && ", [
    "assertion.repository == \"${var.github_repo}\"",
    "assertion.environment == \"${var.github_environment}\"",
    "(${var.ref_condition})",
  ])
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "${var.project_name}-deployer"
  display_name = "GitHub Actions deployer"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "${var.project_name}-github"
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"
  attribute_mapping = {
    "google.subject"             = "assertion.sub"
    "attribute.repository"       = "assertion.repository"
    "attribute.repository_owner" = "assertion.repository_owner"
    "attribute.ref"              = "assertion.ref"
    "attribute.environment"      = "assertion.environment"
  }
  attribute_condition = local.attribute_condition
  oidc { issuer_uri = "https://token.actions.githubusercontent.com" }
}

resource "google_service_account_iam_member" "github_impersonation" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

resource "google_project_iam_member" "deployer" {
  for_each = toset(["roles/run.developer", "roles/artifactregistry.writer"])
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.deployer.email}"
}

# Cloud Run deploys need permission to run the service as its runtime identity.
resource "google_service_account_iam_member" "deployer_acts_as_runtime" {
  service_account_id = var.runtime_service_account_name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
