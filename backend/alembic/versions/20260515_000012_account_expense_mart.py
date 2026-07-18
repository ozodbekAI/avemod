"""Add account-level daily mart for unallocated finance expense rows.

Revision ID: 20260515_000012
Revises: 20260515_000011
Create Date: 2026-05-15 23:55:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260515_000012"
down_revision = "20260515_000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mart_account_expense_daily",
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("source_rows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commission", sa.Numeric(18, 4), nullable=True),
        sa.Column("acquiring_fee", sa.Numeric(18, 4), nullable=True),
        sa.Column("logistics", sa.Numeric(18, 4), nullable=True),
        sa.Column("paid_acceptance", sa.Numeric(18, 4), nullable=True),
        sa.Column("storage", sa.Numeric(18, 4), nullable=True),
        sa.Column("penalties", sa.Numeric(18, 4), nullable=True),
        sa.Column("deductions", sa.Numeric(18, 4), nullable=True),
        sa.Column("additional_payments", sa.Numeric(18, 4), nullable=True),
        sa.Column("total_expense", sa.Numeric(18, 4), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_account_expense_daily")),
        sa.UniqueConstraint("account_id", "stat_date"),
    )
    op.create_index("ix_mart_account_expense_daily_dedupe_key", "mart_account_expense_daily", ["dedupe_key"], unique=True)
    op.create_index(op.f("ix_mart_account_expense_daily_stat_date"), "mart_account_expense_daily", ["stat_date"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported")
