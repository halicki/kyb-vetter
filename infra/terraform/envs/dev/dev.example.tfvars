# Copy to terraform.tfvars (git-ignored) and fill in. Never commit real values.
project_name    = "kyb-vetter"
project_suffix  = "a1b2"
billing_account = "XXXXXX-XXXXXX-XXXXXX"
github_repo     = "owner/repo"
invoker_members = ["user:you@example.com"]
alert_email     = "you@example.com"
neon_org_id     = "org-xxxx-xxxx-00000000"
# M6 (ADR-0017/0018): fill in once the zone exists and the Auth0 tenant is configured.
domain             = "mcp.example.dev"
api_domain         = "api.example.dev"
cloudflare_zone_id = "0123456789abcdef0123456789abcdef"
auth_issuer        = "https://your-tenant.eu.auth0.com/"
public             = true
