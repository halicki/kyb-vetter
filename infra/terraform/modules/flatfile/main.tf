# Daily MF flat file: a bucket for the compact index, a Cloud Run job that builds it and two
# Cloud Scheduler triggers (the ministry publishes around midnight; the second run is the retry).
resource "google_storage_bucket" "flatfile" {
  project                     = var.project_id
  name                        = "${var.project_id}-flatfile"
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = true
  lifecycle_rule {
    action { type = "Delete" }
    condition { age = 35 }
  }
}

resource "google_storage_bucket_iam_member" "runtime_rw" {
  bucket = google_storage_bucket.flatfile.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.runtime_service_account_email}"
}

resource "google_cloud_run_v2_job" "flatfile" {
  project             = var.project_id
  name                = "${var.project_name}-flatfile"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = var.runtime_service_account_email
      max_retries     = 1
      timeout         = "1800s"
      containers {
        image   = var.bootstrap_image
        command = ["python"]
        args    = ["-m", "kyb_vetter_worker", "flatfile"]
        resources {
          limits = { cpu = "1", memory = "2Gi" }
        }
        env {
          name  = "APP_FLATFILE_BUCKET"
          value = google_storage_bucket.flatfile.name
        }
        env {
          name  = "APP_MF_FLATFILE_BASE_URL"
          value = var.mf_flatfile_base_url
        }
        env {
          name  = "APP_PROJECT_NAME"
          value = var.project_name
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].template[0].containers[0].image, client, client_version]
  }
}

resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "${var.project_name}-scheduler"
  display_name = "Cloud Scheduler (runs the flat-file job)"
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_runs_job" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.flatfile.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_scheduler_job" "flatfile" {
  for_each  = var.schedules
  project   = var.project_id
  region    = var.region
  name      = "${var.project_name}-flatfile-${each.key}"
  schedule  = each.value
  time_zone = "Europe/Warsaw"
  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.flatfile.name}:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
  depends_on = [google_cloud_run_v2_job_iam_member.scheduler_runs_job]
}
