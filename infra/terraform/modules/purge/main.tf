# Weekly retention job (ADR-0022): `python -m kyb_vetter_worker purge` against the direct
# (non-pooled) database endpoint, triggered by Cloud Scheduler with the shared scheduler account.

resource "google_cloud_run_v2_job" "purge" {
  project             = var.project_id
  name                = "${var.project_name}-purge"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = var.runtime_service_account_email
      max_retries     = 1
      timeout         = "600s"
      containers {
        image   = var.app_image
        command = ["python"]
        args    = ["-m", "kyb_vetter_worker", "purge"]
        env {
          name  = "APP_PROJECT_NAME"
          value = var.project_name
        }
        env {
          name  = "APP_LOG_FORMAT"
          value = "json"
        }
        env {
          name = "APP_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.database_url_direct_secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_job" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.purge.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.scheduler_service_account_email}"
}

resource "google_cloud_scheduler_job" "purge" {
  project   = var.project_id
  region    = var.region
  name      = "${var.project_name}-purge"
  schedule  = var.schedule
  time_zone = "Europe/Warsaw"
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.purge.name}:run"
    oauth_token {
      service_account_email = var.scheduler_service_account_email
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_runs_job]
}
