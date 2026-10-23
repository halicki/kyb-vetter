"""history per principal: index on (principal, nip, ts)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23
"""

lazy from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_audit_events_principal_nip_ts", "audit_events", ["principal", "nip", "ts"])


def downgrade() -> None:
    op.drop_index("ix_audit_events_principal_nip_ts", table_name="audit_events")
