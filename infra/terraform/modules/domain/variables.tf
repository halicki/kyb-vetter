variable "project_id" { type = string }
variable "region" { type = string }
variable "service_name" {
  type        = string
  description = "Cloud Run service the hostname routes to"
}
variable "hostname" {
  type        = string
  description = "Fully qualified hostname, e.g. mcp.example.dev (must be a subdomain of the zone)"
}
variable "cloudflare_zone_id" {
  type        = string
  description = "Cloudflare zone that holds the hostname's DNS record"
}
