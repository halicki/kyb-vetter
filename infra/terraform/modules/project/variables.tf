variable "project_name" { type = string }
variable "environment" { type = string }
variable "project_suffix" { type = string }
variable "billing_account" { type = string }
variable "region" { type = string }
variable "deletion_policy" {
  type    = string
  default = "DELETE"
}
variable "services" {
  type = list(string)
  default = [
    "cloudresourcemanager.googleapis.com",
    "serviceusage.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudbilling.googleapis.com",
    "billingbudgets.googleapis.com",
    "storage.googleapis.com",
    "cloudscheduler.googleapis.com",
  ]
}
