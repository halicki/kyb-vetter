variable "project_name" {
  type        = string
  description = "Single source of the product name for every cloud resource (ADR-0004)."
}
variable "environment" {
  type    = string
  default = "dev"
}
variable "project_suffix" {
  type        = string
  description = "Short random suffix making the GCP project id globally unique (e.g. 4 hex chars)."
}
variable "billing_account" {
  type      = string
  sensitive = true
}
variable "region" {
  type    = string
  default = "europe-west1"
}
variable "domain" {
  type        = string
  description = "Public hostname; empty means the run.app URL (placeholder until M6)."
  default     = ""
}
variable "github_repo" { type = string }
variable "invoker_members" {
  type        = list(string)
  description = "IAM members allowed to call the service before OAuth (e.g. user:you@example.com)."
}
variable "alert_email" { type = string }
variable "neon_org_id" { type = string }
variable "mf_base_url" {
  type        = string
  description = "White-list host for this environment; dev points at the ministry test host."
  default     = "https://wykazpodatnikowvat-test.mf.gov.pl"
}
variable "krs_base_url" {
  type    = string
  default = "https://api-krs.ms.gov.pl"
}
variable "budget_amount" {
  type    = number
  default = 20
}
variable "budget_currency" {
  type    = string
  default = "PLN"
}
