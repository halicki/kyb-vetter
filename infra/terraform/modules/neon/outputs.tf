output "project_id" { value = neon_project.this.id }
output "database_host" { value = neon_project.this.database_host }
# Neon hands out `postgres://...?sslmode=require`; SQLAlchemy needs the asyncpg dialect and
# asyncpg takes `ssl=require` (it has no `sslmode` keyword).
locals {
  to_asyncpg = { for k, v in {
    pooler = neon_project.this.connection_uri_pooler
    direct = neon_project.this.connection_uri
  } : k => replace(replace(v, "/^postgres(ql)?:/", "postgresql+asyncpg:"), "sslmode=require", "ssl=require") }
}

# Pooled URI for the service (PgBouncer, transaction mode); direct URI for Alembic.
output "connection_uri_pooler" {
  value     = local.to_asyncpg["pooler"]
  sensitive = true
}
output "connection_uri_direct" {
  value     = local.to_asyncpg["direct"]
  sensitive = true
}
