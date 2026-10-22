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
  mf_base_url                   = var.mf_base_url
  krs_base_url                  = var.krs_base_url
  database_url_secret_id        = module.secrets.secret_ids["database-url"]
  database_url_direct_secret_id = module.secrets.secret_ids["database-url-direct"]
  # Administrators plus the CI deployer (smoke test after each roll-out). The deployer's e-mail is
  # deterministic, which avoids a dependency cycle with module.github_wif.
  invoker_members = concat(
    var.invoker_members,
    ["serviceAccount:${var.project_name}-deployer@${local.project_id}.iam.gserviceaccount.com"],
  )
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
  token_creator_members        = var.invoker_members
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
