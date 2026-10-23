output "hostname" { value = google_cloud_run_domain_mapping.mcp.name }
output "resource_records" {
  description = "What Google asks for in DNS; informational, the CNAME above already satisfies it"
  value       = google_cloud_run_domain_mapping.mcp.status[0].resource_records
}
