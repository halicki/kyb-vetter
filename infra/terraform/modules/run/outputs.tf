output "service_name" { value = google_cloud_run_v2_service.mcp.name }
output "service_uri" { value = google_cloud_run_v2_service.mcp.uri }
output "job_name" { value = google_cloud_run_v2_job.migrate.name }
output "runtime_service_account_email" { value = google_service_account.runtime.email }
output "runtime_service_account_name" { value = google_service_account.runtime.name }
