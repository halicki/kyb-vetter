resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "${var.project_name}-run"
  display_name = "Cloud Run runtime (MCP server, jobs)"
}

locals {
  # Cloud Run v2 deterministic URL: https://<service>-<project number>.<region>.run.app
  # (the service also answers on a legacy *.a.run.app URL with an unpredictable hash).
  run_host = "${var.project_name}-mcp-${var.project_number}.${var.region}.run.app"
  env = merge({
    APP_PROJECT_NAME = var.project_name
    APP_DOMAIN       = var.domain == "" ? local.run_host : var.domain
    APP_MF_BASE_URL  = var.mf_base_url
    APP_KRS_BASE_URL = var.krs_base_url
    # Cloud Run terminates TLS on platform-owned hostnames: the Host header is trustworthy here,
    # and the legacy URL's hash cannot be allow-listed ahead of time.
    APP_HOST_CHECK = "false"
  }, var.extra_env)
}

# The image is rolled by CI (deploy-cloudrun); Terraform owns everything else.
resource "google_cloud_run_v2_service" "mcp" {
  project             = var.project_id
  name                = "${var.project_name}-mcp"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account                  = google_service_account.runtime.email
    max_instance_request_concurrency = 40
    timeout                          = "60s"
    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }
    containers {
      image = var.bootstrap_image
      ports { container_port = 8080 }
      resources {
        limits            = { cpu = "1", memory = "512Mi" }
        cpu_idle          = true
        startup_cpu_boost = true
      }
      dynamic "env" {
        for_each = local.env
        content {
          name  = env.key
          value = env.value
        }
      }
      env {
        name = "APP_DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.database_url_secret_id
            version = "latest"
          }
        }
      }
      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 2
        period_seconds        = 5
        failure_threshold     = 6
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# Until OAuth lands (M6) only the administrators may invoke the service.
resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = toset(var.invoker_members)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.mcp.name
  role     = "roles/run.invoker"
  member   = each.value
}

# Schema migrations run as a job from the same image, against the direct (non-pooled) endpoint.
resource "google_cloud_run_v2_job" "migrate" {
  project             = var.project_id
  name                = "${var.project_name}-migrate"
  location            = var.region
  deletion_protection = false

  template {
    template {
      service_account = google_service_account.runtime.email
      max_retries     = 0
      containers {
        image   = var.bootstrap_image
        command = ["alembic"]
        args    = ["-c", "/app/packages/core/alembic.ini", "upgrade", "head"]
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
