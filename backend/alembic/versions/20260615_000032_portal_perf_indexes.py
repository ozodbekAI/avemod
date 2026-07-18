"""Add focused portal performance indexes.

Revision ID: 20260615_000032
Revises: 20260612_000031
Create Date: 2026-06-15 00:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260615_000032"
down_revision = "20260612_000031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_unified_actions_account_created_id
        ON unified_actions (account_id, created_at DESC, id DESC)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_unified_actions_account_created_id")
