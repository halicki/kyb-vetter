variable "project_id" { type = string }
variable "project_name" { type = string }
variable "github_repo" {
  type        = string
  description = "owner/name of the GitHub repository allowed to deploy"
}
variable "github_environment" {
  type        = string
  description = "GitHub environment whose jobs may deploy here; the token's `environment` claim must equal it"
}
variable "ref_condition" {
  type        = string
  description = "CEL over `assertion` the triggering git ref must satisfy, e.g. assertion.ref == \"refs/heads/main\""
}
variable "runtime_service_account_name" {
  type        = string
  description = "Full resource name of the Cloud Run runtime service account"
}
