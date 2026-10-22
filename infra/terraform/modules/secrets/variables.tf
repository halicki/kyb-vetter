variable "project_id" { type = string }
variable "project_name" { type = string }
variable "region" { type = string }
variable "secrets" {
  type      = map(string)
  sensitive = true
}
variable "accessor_service_account" { type = string }
