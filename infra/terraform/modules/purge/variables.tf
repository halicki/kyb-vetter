variable "project_id" { type = string }
variable "project_name" { type = string }
variable "region" { type = string }
variable "runtime_service_account_email" { type = string }
variable "scheduler_service_account_email" { type = string }
variable "database_url_direct_secret_id" { type = string }
variable "app_image" {
  type        = string
  description = "Application image; the job overrides the command, so the placeholder image cannot start it"
}
variable "schedule" {
  type    = string
  default = "30 3 * * 0" # Sundays 03:30 Europe/Warsaw
}
