# Bootstrap root: the project and its state bucket. State is LOCAL (git-ignored *.tfstate),
# because the GCS bucket that holds the main root's state cannot exist before this applies.
terraform {
  required_version = ">= 1.14"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 8.8" }
  }
}

provider "google" {
  region = var.region
}

module "project" {
  source          = "../../../modules/project"
  project_name    = var.project_name
  environment     = var.environment
  project_suffix  = var.project_suffix
  billing_account = var.billing_account
  region          = var.region
}

variable "project_name" { type = string }
variable "environment" {
  type    = string
  default = "dev"
}
variable "project_suffix" { type = string }
variable "billing_account" {
  type      = string
  sensitive = true
}
variable "region" {
  type    = string
  default = "europe-west1"
}

output "project_id" { value = module.project.project_id }
output "project_number" { value = module.project.project_number }
output "tfstate_bucket" { value = module.project.tfstate_bucket }
