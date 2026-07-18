"""Add normalized expense accounting marts and ad reconciliation fields.

Revision ID: 20260603_000026
Revises: 20260528_000025
Create Date: 2026-06-03 10:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260603_000026"
down_revision = "20260528_000025"
branch_labels = None
depends_on = None


def _add_numeric(table_name: str, column_name: str) -> None:
    op.add_column(table_name, sa.Column(column_name, sa.Numeric(18, 4), nullable=True))


def upgrade() -> None:
    op.create_table(
        "mart_expense_daily",
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=True),
        sa.Column("rrd_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("srid", sa.String(length=255), nullable=True),
        sa.Column("order_id", sa.BigInteger(), nullable=True),
        sa.Column("expense_category", sa.String(length=64), nullable=False),
        sa.Column("expense_source", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("amount_sign", sa.String(length=16), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("source_field", sa.String(length=128), nullable=True),
        sa.Column("source_reason", sa.String(length=255), nullable=True),
        sa.Column("seller_oper_name", sa.String(length=255), nullable=True),
        sa.Column("bonus_type_name", sa.String(length=255), nullable=True),
        sa.Column("logistics_type", sa.String(length=64), nullable=True),
        sa.Column("is_allocated_to_sku", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("allocation_method", sa.String(length=64), nullable=True),
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sku_id"], ["core_sku.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_mart_expense_daily")),
        sa.UniqueConstraint(
            "account_id",
            "stat_date",
            "rrd_id",
            "expense_category",
            "source_field",
            "sku_id",
            "nm_id",
            "barcode",
        ),
    )
    op.create_index("ix_mart_expense_daily_dedupe_key", "mart_expense_daily", ["dedupe_key"], unique=True)
    op.create_index(op.f("ix_mart_expense_daily_stat_date"), "mart_expense_daily", ["stat_date"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_report_id"), "mart_expense_daily", ["report_id"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_rrd_id"), "mart_expense_daily", ["rrd_id"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_sku_id"), "mart_expense_daily", ["sku_id"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_nm_id"), "mart_expense_daily", ["nm_id"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_srid"), "mart_expense_daily", ["srid"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_order_id"), "mart_expense_daily", ["order_id"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_expense_category"), "mart_expense_daily", ["expense_category"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_expense_source"), "mart_expense_daily", ["expense_source"], unique=False)
    op.create_index(op.f("ix_mart_expense_daily_amount_sign"), "mart_expense_daily", ["amount_sign"], unique=False)

    for column_name in (
        "wb_commission",
        "payment_processing",
        "pvz_reward",
        "wb_logistics",
        "wb_logistics_rebill",
        "acceptance",
        "penalty",
        "deduction",
        "marketing_deduction",
        "loyalty",
        "other_wb_expenses",
        "total_wb_expenses",
        "seller_cogs",
        "seller_other_expense",
        "total_seller_expenses",
        "ad_spend_operational",
        "ad_spend_finance",
        "ad_spend_final",
        "ad_spend_delta",
        "net_profit_after_all_expenses",
    ):
        _add_numeric("mart_sku_daily", column_name)
    op.add_column("mart_sku_daily", sa.Column("ad_spend_source", sa.String(length=32), nullable=True))

    for column_name in (
        "wb_commission",
        "payment_processing",
        "pvz_reward",
        "wb_logistics",
        "wb_logistics_rebill",
        "acceptance",
        "penalty",
        "deduction",
        "marketing_deduction",
        "loyalty",
        "other_wb_expenses",
        "total_wb_expenses",
        "ad_spend_operational",
        "ad_spend_finance",
        "ad_spend_final",
        "ad_spend_delta",
        "seller_cogs",
        "seller_other_expense",
        "total_seller_expenses",
        "net_profit_after_all_expenses",
    ):
        _add_numeric("mart_account_expense_daily", column_name)
    op.add_column("mart_account_expense_daily", sa.Column("ad_spend_source", sa.String(length=32), nullable=True))

    for column_name in (
        "ad_spend_operational",
        "ad_spend_finance",
        "ad_spend_final",
        "ad_spend_delta",
    ):
        _add_numeric("mart_reconciliation_daily", column_name)
    op.add_column("mart_reconciliation_daily", sa.Column("ad_spend_source", sa.String(length=32), nullable=True))


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported")
