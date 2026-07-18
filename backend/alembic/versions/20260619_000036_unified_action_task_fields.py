"""Add task center fields to unified actions.

Revision ID: 20260619_000036
Revises: 20260619_000035
Create Date: 2026-06-19 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260619_000036"
down_revision = "20260619_000035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unified_actions", sa.Column("assigned_to_user_id", sa.BigInteger(), nullable=True))
    op.add_column("unified_actions", sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("unified_actions", sa.Column("review_status", sa.String(length=32), server_default="new", nullable=False))
    op.add_column("unified_actions", sa.Column("last_comment", sa.Text(), nullable=True))
    op.add_column("unified_actions", sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("unified_actions", sa.Column("dismissed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_unified_actions_assigned_to_user_id_auth_users",
        "unified_actions",
        "auth_users",
        ["assigned_to_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_unified_actions_assigned_to_user_id", "unified_actions", ["assigned_to_user_id"])
    op.create_index("ix_unified_actions_deadline_at", "unified_actions", ["deadline_at"])
    op.create_index("ix_unified_actions_review_status", "unified_actions", ["review_status"])
    op.create_index("ix_unified_actions_closed_at", "unified_actions", ["closed_at"])
    op.create_index("ix_unified_actions_dismissed_at", "unified_actions", ["dismissed_at"])


def downgrade() -> None:
    op.drop_index("ix_unified_actions_dismissed_at", table_name="unified_actions")
    op.drop_index("ix_unified_actions_closed_at", table_name="unified_actions")
    op.drop_index("ix_unified_actions_review_status", table_name="unified_actions")
    op.drop_index("ix_unified_actions_deadline_at", table_name="unified_actions")
    op.drop_index("ix_unified_actions_assigned_to_user_id", table_name="unified_actions")
    op.drop_constraint("fk_unified_actions_assigned_to_user_id_auth_users", "unified_actions", type_="foreignkey")
    op.drop_column("unified_actions", "dismissed_at")
    op.drop_column("unified_actions", "closed_at")
    op.drop_column("unified_actions", "last_comment")
    op.drop_column("unified_actions", "review_status")
    op.drop_column("unified_actions", "deadline_at")
    op.drop_column("unified_actions", "assigned_to_user_id")
