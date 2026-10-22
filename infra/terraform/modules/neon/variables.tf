variable "project_name" { type = string }
variable "environment" { type = string }
variable "neon_org_id" { type = string }
variable "neon_region" {
  type    = string
  default = "aws-eu-central-1" # Frankfurt
}
