"""Add Dynamic Problem Engine admin audit table.

Revision ID: 20260706_000059
Revises: 20260706_000058
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260706_000059"
down_revision = "20260706_000058"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "problem_rule_admin_audit",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("old_value_json", JSONB, nullable=True),
        sa.Column("new_value_json", JSONB, nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("actor_user_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["actor_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_problem_rule_admin_audit_object", "problem_rule_admin_audit", ["object_type", "object_id"])
    op.create_index("ix_problem_rule_admin_audit_event_type", "problem_rule_admin_audit", ["event_type"])
    op.create_index("ix_problem_rule_admin_audit_actor_user_id", "problem_rule_admin_audit", ["actor_user_id"])


def downgrade() -> None:
    op.drop_index("ix_problem_rule_admin_audit_actor_user_id", table_name="problem_rule_admin_audit")
    op.drop_index("ix_problem_rule_admin_audit_event_type", table_name="problem_rule_admin_audit")
    op.drop_index("ix_problem_rule_admin_audit_object", table_name="problem_rule_admin_audit")
    op.drop_table("problem_rule_admin_audit")
