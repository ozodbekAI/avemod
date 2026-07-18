"""Add admin problem rule visibility metadata.

Revision ID: 20260712_000065
Revises: 20260710_000064
Create Date: 2026-07-12
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260712_000065"
down_revision = "20260710_000064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table_name in ("problem_definitions", "problem_rule_versions"):
        op.add_column(
            table_name,
            sa.Column("test_only", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        )
        op.add_column(
            table_name,
            sa.Column("seller_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        )
        op.add_column(
            table_name,
            sa.Column("visibility_mode", sa.String(length=32), server_default="seller", nullable=False),
        )
        op.create_index(f"ix_{table_name}_test_only", table_name, ["test_only"])
        op.create_index(f"ix_{table_name}_seller_visible", table_name, ["seller_visible"])
        op.create_index(f"ix_{table_name}_visibility_mode", table_name, ["visibility_mode"])


def downgrade() -> None:
    for table_name in ("problem_rule_versions", "problem_definitions"):
        op.drop_index(f"ix_{table_name}_visibility_mode", table_name=table_name)
        op.drop_index(f"ix_{table_name}_seller_visible", table_name=table_name)
        op.drop_index(f"ix_{table_name}_test_only", table_name=table_name)
        op.drop_column(table_name, "visibility_mode")
        op.drop_column(table_name, "seller_visible")
        op.drop_column(table_name, "test_only")
