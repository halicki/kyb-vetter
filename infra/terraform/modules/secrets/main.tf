locals {
  # Keys are resource names (not secret); only the values are sensitive.
  secret_names = toset(nonsensitive(keys(var.secrets)))
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.secret_names
  project   = var.project_id
  secret_id = "${var.project_name}-${each.key}"
  replication {
    user_managed {
      replicas { location = var.region }
    }
  }
}

resource "google_secret_manager_secret_version" "this" {
  for_each    = local.secret_names
  secret      = google_secret_manager_secret.this[each.key].id
  secret_data = var.secrets[each.key]
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = local.secret_names
  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.accessor_service_account}"
}
