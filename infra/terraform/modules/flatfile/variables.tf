variable "project_id" { type = string }
variable "project_name" { type = string }
variable "region" { type = string }
variable "runtime_service_account_email" { type = string }
variable "mf_flatfile_base_url" {
  type    = string
  default = "https://wykazpodatnikowvat.mf.gov.pl/plikplaski"
}
variable "bootstrap_image" {
  type    = string
  default = "us-docker.pkg.dev/cloudrun/container/hello"
}
variable "schedules" {
  type        = map(string)
  description = "Cron expressions in Europe/Warsaw; the later ones retry a late publication"
  default     = { first = "15 1 * * *", retry = "15 5 * * *" }
}
