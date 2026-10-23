locals {
  project_id = "${var.project_name}-${var.environment}-${var.project_suffix}"
}

provider "google" {
  region                = var.region
  user_project_override = true
  billing_project       = local.project_id
}

# Project creation and service enablement must not bill the project that does not exist yet.
provider "google" {
  alias  = "bootstrap"
  region = var.region
}

provider "neon" {} # NEON_API_KEY from the environment

provider "cloudflare" {} # CLOUDFLARE_API_TOKEN from the environment (Zone:DNS:Edit on the zone)
