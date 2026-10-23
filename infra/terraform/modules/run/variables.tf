variable "project_id" { type = string }
variable "project_number" { type = string }
variable "project_name" { type = string }
variable "region" { type = string }
variable "domain" { type = string }
variable "mf_base_url" { type = string }
variable "krs_base_url" { type = string }
variable "extra_env" {
  type    = map(string)
  default = {}
}
variable "bootstrap_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}
variable "database_url_secret_id" { type = string }
variable "database_url_direct_secret_id" { type = string }
variable "invoker_members" { type = list(string) }
variable "public" {
  type        = bool
  description = "allUsers may invoke the service (auth is enforced by the app)"
  default     = false
}
