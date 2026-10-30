# Public website on GitHub Pages at the zone apex (documentation, privacy policy for the
# connector directory listing). GitHub serves apex domains from fixed anycast addresses; the
# `www` host is a CNAME to the account's Pages origin. Not proxied: GitHub issues the
# certificate itself and needs to see the records directly. The custom domain itself is set in
# the repository's Pages settings (a CNAME file is ignored for Actions deployments).

locals {
  pages_ipv4 = ["185.199.108.153", "185.199.109.153", "185.199.110.153", "185.199.111.153"]
  pages_ipv6 = ["2606:50c0:8000::153", "2606:50c0:8001::153", "2606:50c0:8002::153", "2606:50c0:8003::153"]
}

resource "cloudflare_dns_record" "apex_a" {
  for_each = toset(local.pages_ipv4)
  zone_id  = var.cloudflare_zone_id
  name     = var.hostname
  type     = "A"
  content  = each.value
  ttl      = 300
  proxied  = false
  comment  = "GitHub Pages apex (managed by Terraform)"
}

resource "cloudflare_dns_record" "apex_aaaa" {
  for_each = toset(local.pages_ipv6)
  zone_id  = var.cloudflare_zone_id
  name     = var.hostname
  type     = "AAAA"
  content  = each.value
  ttl      = 300
  proxied  = false
  comment  = "GitHub Pages apex (managed by Terraform)"
}

resource "cloudflare_dns_record" "www" {
  zone_id = var.cloudflare_zone_id
  name    = "www.${var.hostname}"
  type    = "CNAME"
  content = "${var.github_owner}.github.io"
  ttl     = 300
  proxied = false
  comment = "GitHub Pages www alias (managed by Terraform)"
}
