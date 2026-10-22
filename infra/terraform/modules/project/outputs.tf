output "project_id" { value = google_project.this.project_id }
output "project_number" { value = google_project.this.number }
output "tfstate_bucket" { value = google_storage_bucket.tfstate.name }
output "services_ready" { value = [for s in google_project_service.this : s.id] }
