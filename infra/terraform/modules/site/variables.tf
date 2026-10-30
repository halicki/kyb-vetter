variable "hostname" {
  type        = string
  description = "Zone apex the site is served at (e.g. example.dev)."
}
variable "cloudflare_zone_id" { type = string }
variable "github_owner" {
  type        = string
  description = "GitHub user or organisation owning the repository (Pages origin <owner>.github.io)."
}
