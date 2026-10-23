# Custom hostname for the Cloud Run service (ADR-0018): a Cloud Run domain mapping (preview,
# free, Google-managed certificate) plus the DNS record on Cloudflare. The record is a fixed
# CNAME for subdomains, so it does not depend on the mapping's status (which is unknown at
# plan time). Not proxied: Cloudflare's proxy breaks certificate issuance for the mapping.
#
# Prerequisite (once, by hand): the account running Terraform must be a verified owner of the
# zone in Google Search Console (`gcloud domains verify <zone>`), see README.

resource "google_cloud_run_domain_mapping" "mcp" {
  project  = var.project_id
  location = var.region
  name     = var.hostname

  metadata {
    namespace = var.project_id
  }

  spec {
    route_name = var.service_name
  }
}

resource "cloudflare_dns_record" "mcp" {
  zone_id = var.cloudflare_zone_id
  name    = var.hostname
  type    = "CNAME"
  content = "ghs.googlehosted.com"
  ttl     = 300
  proxied = false
  comment = "Cloud Run domain mapping for ${var.service_name} (managed by Terraform)"
}
