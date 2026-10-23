variable "project_id" { type = string }
variable "region" { type = string }
variable "service_name" {
  type        = string
  description = "Cloud Run service the hostname routes to"
}
variable "hostname" {
  type        = string
  description = "Fully qualified hostname, e.g. mcp.example.dev (must be a subdomain of the zone)"

  validation {
    condition     = length(split(".", var.hostname)) >= 3
    error_message = "hostname must be a subdomain (e.g. mcp.example.dev): the module maps it with a CNAME to ghs.googlehosted.com, which Google does not accept for a zone apex (A/AAAA records would be needed)."
  }
}
variable "cloudflare_zone_id" {
  type        = string
  description = "Cloudflare zone that holds the hostname's DNS record"
}
