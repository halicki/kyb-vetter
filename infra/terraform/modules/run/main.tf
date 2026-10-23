resource "google_service_account" "runtime" {
  project      = var.project_id
  account_id   = "${var.project_name}-run"
  display_name = "Cloud Run runtime (MCP server, REST API, jobs)"
}

locals {
  # Two services from one image (ADR-0020): the MCP server (image CMD) and the REST API.
  services = {
    mcp = { command = [], domain = var.domain }
    api = { command = ["python", "-m", "kyb_vetter_api"], domain = var.api_domain }
  }
  # Cloud Run v2 deterministic URL: https://<service>-<project number>.<region>.run.app
  # (the service also answers on a legacy *.a.run.app URL with an unpredictable hash).
  run_hosts = {
    for k, _ in local.services : k => "${var.project_name}-${k}-${var.project_number}.${var.region}.run.app"
  }
  env = {
    for k, svc in local.services : k => merge({
      APP_PROJECT_NAME = var.project_name
      APP_DOMAIN       = svc.domain == "" ? local.run_hosts[k] : svc.domain
      APP_MF_BASE_URL  = var.mf_base_url
      APP_KRS_BASE_URL = var.krs_base_url
      # With a custom domain the MCP Host allow-list is enforced again (ADR-0018): the domain plus
      # the deterministic run.app host (CI smoke test, clients that only take run.app URLs).
      # Without a domain the platform-owned hostname is trustworthy and the legacy *.a.run.app hash
      # cannot be allow-listed ahead of time, so the check stays off. The REST app ignores both.
      APP_HOST_CHECK          = svc.domain == "" ? "false" : "true"
      APP_EXTRA_ALLOWED_HOSTS = jsonencode([local.run_hosts[k]])
    }, var.extra_env)
  }
  invokers = var.public ? ["allUsers"] : var.invoker_members
  invoker_bindings = {
    for pair in setproduct(keys(local.services), local.invokers) :
    "${pair[0]}/${pair[1]}" => { service = pair[0], member = pair[1] }
  }
}

moved {
  from = google_cloud_run_v2_service.mcp
  to   = google_cloud_run_v2_service.this["mcp"]
}

moved {
  from = google_cloud_run_v2_service_iam_member.invokers["allUsers"]
  to   = google_cloud_run_v2_service_iam_member.invokers["mcp/allUsers"]
}

# The image is rolled by CI (deploy-cloudrun); Terraform owns everything else.
resource "google_cloud_run_v2_service" "this" {
  for_each            = local.services
  project             = var.project_id
  name                = "${var.project_name}-${each.key}"
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
      image   = var.bootstrap_image
      command = length(each.value.command) == 0 ? null : each.value.command
      ports { container_port = 8080 }
      resources {
        limits            = { cpu = "1", memory = "1Gi" } # ~60 MB flat-file index in memory
        cpu_idle          = true
        startup_cpu_boost = true
      }
      dynamic "env" {
        for_each = local.env[each.key]
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
      # /health reads the flat-file manifest from GCS on a cold start, so give it a real timeout and
      # a full minute: a cold instance with a 60 MB index behind it must not be killed by the probe.
      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 2
        period_seconds        = 5
        timeout_seconds       = 3
        failure_threshold     = 12
      }
    }
  }

  lifecycle {
    ignore_changes = [template[0].containers[0].image, client, client_version]
  }
}

# Public once the apps enforce auth (ADR-0017, ADR-0020); administrators and the CI deployer otherwise.
resource "google_cloud_run_v2_service_iam_member" "invokers" {
  for_each = local.invoker_bindings
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.this[each.value.service].name
  role     = "roles/run.invoker"
  member   = each.value.member
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
