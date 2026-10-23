variable "project_id" { type = string }
variable "project_name" { type = string }
variable "github_repo" {
  type        = string
  description = "owner/name of the GitHub repository allowed to deploy"
}
variable "runtime_service_account_name" {
  type        = string
  description = "Full resource name of the Cloud Run runtime service account"
}
