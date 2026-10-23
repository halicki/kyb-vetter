# The project itself is created by ./bootstrap (local state); here it is read back.
data "google_project" "this" {
  provider   = google.bootstrap
  project_id = local.project_id
}

locals {
  project_number = data.google_project.this.number
}

module "registry" {
  source       = "../../modules/registry"
  project_id   = local.project_id
  project_name = var.project_name
  region       = var.region
}

module "neon" {
  source       = "../../modules/neon"
  project_name = var.project_name
  environment  = var.environment
  neon_org_id  = var.neon_org_id
}

module "run" {
  source                        = "../../modules/run"
  project_id                    = local.project_id
  project_number                = local.project_number
  project_name                  = var.project_name
  region                        = var.region
  domain                        = var.domain
  api_domain                    = var.api_domain
  mf_base_url                   = var.mf_base_url
  krs_base_url                  = var.krs_base_url
  database_url_secret_id        = module.secrets.secret_ids["database-url"]
  database_url_direct_secret_id = module.secrets.secret_ids["database-url-direct"]
  # Administrators plus the CI deployer (smoke test after each roll-out). The deployer's e-mail is
  # deterministic, which avoids a dependency cycle with module.github_wif.
  extra_env = merge(
    { APP_FLATFILE_BUCKET = "${local.project_id}-flatfile" },
    var.auth_issuer == "" ? {} : {
      APP_AUTH_ISSUER   = var.auth_issuer
      APP_AUTH_AUDIENCE = "https://${var.domain == "" ? module.run.run_host : var.domain}/mcp"
    },
  )
  public = var.public
  invoker_members = concat(
    var.invoker_members,
    ["serviceAccount:${var.project_name}-deployer@${local.project_id}.iam.gserviceaccount.com"],
  )
}

# REST API hostname (ADR-0020), same zone; skipped until configured.
module "api_domain" {
  count              = var.api_domain != "" && var.cloudflare_zone_id != "" ? 1 : 0
  source             = "../../modules/domain"
  project_id         = local.project_id
  region             = var.region
  service_name       = module.run.api_service_name
  hostname           = var.api_domain
  cloudflare_zone_id = var.cloudflare_zone_id
}

# Custom hostname (ADR-0018); skipped until the zone and hostname are configured.
module "domain" {
  count              = var.domain != "" && var.cloudflare_zone_id != "" ? 1 : 0
  source             = "../../modules/domain"
  project_id         = local.project_id
  region             = var.region
  service_name       = module.run.service_name
  hostname           = var.domain
  cloudflare_zone_id = var.cloudflare_zone_id
}

# The runtime SA is created in module.run; secrets need its email, run needs the secret ids:
# both are known at plan time, no cycle (the SA email is deterministic from its account_id).
module "secrets" {
  source       = "../../modules/secrets"
  project_id   = local.project_id
  project_name = var.project_name
  region       = var.region
  secrets = {
    "database-url"        = module.neon.connection_uri_pooler
    "database-url-direct" = module.neon.connection_uri_direct
  }
  accessor_service_account = "${var.project_name}-run@${local.project_id}.iam.gserviceaccount.com"
}

module "github_wif" {
  source                       = "../../modules/github-wif"
  project_id                   = local.project_id
  project_name                 = var.project_name
  github_repo                  = var.github_repo
  runtime_service_account_name = module.run.runtime_service_account_name
}

module "budget" {
  source          = "../../modules/budget"
  project_id      = local.project_id
  project_number  = local.project_number
  project_name    = var.project_name
  environment     = var.environment
  billing_account = var.billing_account
  alert_email     = var.alert_email
  amount          = var.budget_amount
  currency        = var.budget_currency
}

module "flatfile" {
  source                        = "../../modules/flatfile"
  project_id                    = local.project_id
  project_name                  = var.project_name
  region                        = var.region
  runtime_service_account_email = module.run.runtime_service_account_email
}
