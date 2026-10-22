"""initial: quota counters, audit events, registry cache

Revision ID: 0001
Revises:
Create Date: 2026-10-22
"""

lazy from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quota_counters",
        sa.Column("bucket", sa.String(), primary_key=True),
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("principal", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("nip", sa.String(), nullable=True),
        sa.Column("input", postgresql.JSONB(), nullable=False),
        sa.Column("outcome", sa.String(), nullable=False),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("request_ids", postgresql.JSONB(), nullable=False),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("response_sha256", sa.String(), nullable=True),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("from_cache", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_audit_events_nip_ts", "audit_events", ["nip", "ts"])
    op.create_table(
        "registry_cache",
        sa.Column("source", sa.String(), primary_key=True),
        sa.Column("cache_key", sa.String(), primary_key=True),
        sa.Column("queried_date", sa.Date(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("registry_cache")
    op.drop_index("ix_audit_events_nip_ts", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("quota_counters")
