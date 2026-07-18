"""Add status metadata to local card quality issues.

Revision ID: 20260630_000053
Revises: 20260630_000052
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260630_000053"
down_revision = "20260630_000052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("card_quality_issues", sa.Column("fixed_value", sa.Text(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("fixed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("card_quality_issues", sa.Column("fixed_by_user_id", sa.BigInteger(), nullable=True))
    op.add_column("card_quality_issues", sa.Column("postponed_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("card_quality_issues", sa.Column("status_reason", sa.Text(), nullable=True))
    op.create_index("ix_card_quality_issues_fixed_at", "card_quality_issues", ["fixed_at"])
    op.create_index("ix_card_quality_issues_fixed_by_user_id", "card_quality_issues", ["fixed_by_user_id"])
    op.create_index("ix_card_quality_issues_postponed_until", "card_quality_issues", ["postponed_until"])
    op.create_foreign_key(
        "fk_card_quality_issues_fixed_by_user_id_auth_users",
        "card_quality_issues",
        "auth_users",
        ["fixed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_card_quality_issues_fixed_by_user_id_auth_users", "card_quality_issues", type_="foreignkey")
    op.drop_index("ix_card_quality_issues_postponed_until", table_name="card_quality_issues")
    op.drop_index("ix_card_quality_issues_fixed_by_user_id", table_name="card_quality_issues")
    op.drop_index("ix_card_quality_issues_fixed_at", table_name="card_quality_issues")
    op.drop_column("card_quality_issues", "status_reason")
    op.drop_column("card_quality_issues", "postponed_until")
    op.drop_column("card_quality_issues", "fixed_by_user_id")
    op.drop_column("card_quality_issues", "fixed_at")
    op.drop_column("card_quality_issues", "fixed_value")
