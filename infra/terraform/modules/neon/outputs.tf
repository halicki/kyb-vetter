output "project_id" { value = neon_project.this.id }
output "database_host" { value = neon_project.this.database_host }
# Pooled URI for the service (PgBouncer, transaction mode); direct URI for Alembic.
output "connection_uri_pooler" {
  value     = replace(neon_project.this.connection_uri_pooler, "postgresql://", "postgresql+asyncpg://")
  sensitive = true
}
output "connection_uri_direct" {
  value     = replace(neon_project.this.connection_uri, "postgresql://", "postgresql+asyncpg://")
  sensitive = true
}
