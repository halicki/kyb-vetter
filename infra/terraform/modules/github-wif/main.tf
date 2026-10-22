# Keyless deploys from GitHub Actions: the workflow exchanges its OIDC token for the deployer
# service account through Workload Identity Federation, restricted to one repository.
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
  }
  attribute_condition = "assertion.repository == \"${var.github_repo}\""
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

# Administrators mint ID tokens for the service by impersonating the deployer (user tokens from a
# non-default gcloud OAuth client are rejected by Cloud Run).
resource "google_service_account_iam_member" "admin_token_creators" {
  for_each           = toset(var.token_creator_members)
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = each.value
}
