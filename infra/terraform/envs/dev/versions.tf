terraform {
  required_version = ">= 1.14"
  required_providers {
    google = { source = "hashicorp/google", version = "~> 8.8" }
    neon   = { source = "kislerdm/neon", version = "0.18.0" } # switch to neondatabase/neon once published (ADR-0014)
  }
  backend "gcs" {} # configured with -backend-config=dev.backend.hcl (see README)
}
