# Neon Free plan: history retention capped at 6 h, scale-to-zero after 5 min (ADR-0014).
resource "neon_project" "this" {
  name                      = "${var.project_name}-${var.environment}"
  org_id                    = var.neon_org_id
  region_id                 = var.neon_region
  pg_version                = 17
  history_retention_seconds = 21600
}
