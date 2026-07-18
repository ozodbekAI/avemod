"""Add Finance checker fixed-file entries.

Revision ID: 20260701_000055
Revises: 20260630_000054
Create Date: 2026-07-01
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260701_000055"
down_revision = "20260630_000054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "card_quality_fixed_file_entries",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("subject_name", sa.String(length=255), nullable=True),
        sa.Column("char_name", sa.String(length=255), nullable=False),
        sa.Column("fixed_value", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "nm_id", "char_name", name="uq_card_quality_fixed_account_nm_char"),
    )
    op.create_index("ix_card_quality_fixed_file_entries_account_id", "card_quality_fixed_file_entries", ["account_id"])
    op.create_index("ix_card_quality_fixed_file_entries_nm_id", "card_quality_fixed_file_entries", ["nm_id"])
    op.create_index("ix_card_quality_fixed_file_entries_created_by_user_id", "card_quality_fixed_file_entries", ["created_by_user_id"])
    op.create_index("ix_card_quality_fixed_account_nm", "card_quality_fixed_file_entries", ["account_id", "nm_id"])
    op.create_index("ix_card_quality_fixed_account_char", "card_quality_fixed_file_entries", ["account_id", "char_name"])


def downgrade() -> None:
    op.drop_index("ix_card_quality_fixed_account_char", table_name="card_quality_fixed_file_entries")
    op.drop_index("ix_card_quality_fixed_account_nm", table_name="card_quality_fixed_file_entries")
    op.drop_index("ix_card_quality_fixed_file_entries_created_by_user_id", table_name="card_quality_fixed_file_entries")
    op.drop_index("ix_card_quality_fixed_file_entries_nm_id", table_name="card_quality_fixed_file_entries")
    op.drop_index("ix_card_quality_fixed_file_entries_account_id", table_name="card_quality_fixed_file_entries")
    op.drop_table("card_quality_fixed_file_entries")
