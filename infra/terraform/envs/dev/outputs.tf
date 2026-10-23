output "project_id" { value = local.project_id }
output "project_number" { value = local.project_number }
output "artifact_repository" { value = module.registry.repository }
output "service_name" { value = module.run.service_name }
output "service_uri" { value = module.run.service_uri }
output "public_url" { value = "https://${var.domain == "" ? module.run.run_host : var.domain}" }
output "migrate_job_name" { value = module.run.job_name }
output "workload_identity_provider" { value = module.github_wif.workload_identity_provider }
output "deployer_service_account" { value = module.github_wif.deployer_service_account }
output "neon_project_id" { value = module.neon.project_id }
output "flatfile_job_name" { value = module.flatfile.job_name }
output "flatfile_bucket" { value = module.flatfile.bucket }
