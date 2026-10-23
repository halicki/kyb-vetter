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
  description = "Public hostname of the MCP service (e.g. mcp.example.dev); empty means the run.app URL only."
  default     = ""
}
variable "cloudflare_zone_id" {
  type        = string
  description = "Cloudflare zone holding `domain`; with `domain` set, creates the domain mapping and DNS record (ADR-0018)."
  default     = ""
}
variable "auth_issuer" {
  type        = string
  description = "OAuth issuer URL of the identity provider (Auth0 tenant, with trailing slash); empty disables auth (ADR-0017)."
  default     = ""
}
variable "public" {
  type        = bool
  description = "Grant allUsers the invoker role. Only true once auth_issuer is set: the app then enforces OAuth."
  default     = false

  validation {
    condition     = !var.public || var.auth_issuer != ""
    error_message = "public = true requires auth_issuer: the service must enforce OAuth before it is opened."
  }
}
variable "github_repo" { type = string }
variable "invoker_members" {
  type        = list(string)
  description = "IAM members allowed to call the service while it is not public (e.g. user:you@example.com)."
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
