"""Add Action Center performance indexes.

Revision ID: 20260718_000067
Revises: 20260718_000066
Create Date: 2026-07-18
"""

from __future__ import annotations

from alembic import op


revision = "20260718_000067"
down_revision = "20260718_000066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_problem_instance_history_problem_created_id
        ON problem_instance_history (problem_instance_id, created_at, id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_problem_instances_account_status_last_seen_id
        ON problem_instances (account_id, status, last_seen_at, id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_problem_instances_account_status_last_seen_id")
    op.execute("DROP INDEX IF EXISTS ix_problem_instance_history_problem_created_id")
