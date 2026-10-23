"""api keys for the REST API (ADR-0019)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-23
"""

lazy from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("principal", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("prefix", sa.String(), nullable=False, unique=True),
        sa.Column("key_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_api_keys_principal", "api_keys", ["principal"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_principal", table_name="api_keys")
    op.drop_table("api_keys")
