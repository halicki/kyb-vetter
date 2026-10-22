# A fresh GCP project per environment. The id is deterministic (name-env-suffix) so that
# provider blocks can reference it at plan time; the suffix guarantees global uniqueness.
resource "google_project" "this" {
  name            = "${var.project_name}-${var.environment}"
  project_id      = "${var.project_name}-${var.environment}-${var.project_suffix}"
  billing_account = var.billing_account
  deletion_policy = var.deletion_policy
  labels          = { app = var.project_name, env = var.environment }
}

resource "google_project_service" "this" {
  for_each           = toset(var.services)
  project            = google_project.this.project_id
  service            = each.value
  disable_on_destroy = false
}

# Remote state bucket for this environment. Created with local state first, then migrated (README).
resource "google_storage_bucket" "tfstate" {
  project                     = google_project.this.project_id
  name                        = "${google_project.this.project_id}-tfstate"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  versioning { enabled = true }
  depends_on = [google_project_service.this]
}
