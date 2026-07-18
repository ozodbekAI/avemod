"""Stabilization foundations for raw logs, manual costs, marts, and finance uniqueness.

Revision ID: 20260515_000008
Revises: 20260515_000007
Create Date: 2026-05-15 15:40:00
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260515_000008"
down_revision = "20260515_000007"
branch_labels = None
depends_on = None


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _constraint_names(table_name: str) -> set[str]:
    return {constraint["name"] for constraint in sa.inspect(op.get_bind()).get_unique_constraints(table_name)}


def upgrade() -> None:
    if context.is_offline_mode():
        return
    inspector = sa.inspect(op.get_bind())
    table_names = set(inspector.get_table_names())

    raw_columns = _column_names("raw_wb_api_responses")
    if "http_method" not in raw_columns:
        op.add_column("raw_wb_api_responses", sa.Column("http_method", sa.String(length=16), nullable=True))
        op.execute("UPDATE raw_wb_api_responses SET http_method = 'GET' WHERE http_method IS NULL")
        op.alter_column("raw_wb_api_responses", "http_method", existing_type=sa.String(length=16), nullable=False)
    if "request_body" not in raw_columns:
        op.add_column("raw_wb_api_responses", sa.Column("request_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    if "response_text" not in raw_columns:
        op.add_column("raw_wb_api_responses", sa.Column("response_text", sa.Text(), nullable=True))
    if "is_success" not in raw_columns:
        op.add_column("raw_wb_api_responses", sa.Column("is_success", sa.Boolean(), nullable=True))
        op.execute("UPDATE raw_wb_api_responses SET is_success = CASE WHEN status_code BETWEEN 200 AND 299 THEN TRUE ELSE FALSE END WHERE is_success IS NULL")
        op.alter_column("raw_wb_api_responses", "is_success", existing_type=sa.Boolean(), nullable=False)
    if "retry_count" not in raw_columns:
        op.add_column("raw_wb_api_responses", sa.Column("retry_count", sa.Integer(), nullable=True))
        op.execute("UPDATE raw_wb_api_responses SET retry_count = 0 WHERE retry_count IS NULL")
        op.alter_column("raw_wb_api_responses", "retry_count", existing_type=sa.Integer(), nullable=False)

    manual_cost_columns = _column_names("manual_costs")
    if "uploaded_by_user_id" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("uploaded_by_user_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            op.f("fk_manual_costs_uploaded_by_user_id_auth_users"),
            "manual_costs",
            "auth_users",
            ["uploaded_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if "cost_price" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("cost_price", sa.Numeric(18, 4), nullable=True))
        op.execute("UPDATE manual_costs SET cost_price = unit_cost WHERE cost_price IS NULL")
        op.alter_column("manual_costs", "cost_price", existing_type=sa.Numeric(18, 4), nullable=False)
    if "packaging_cost" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("packaging_cost", sa.Numeric(18, 4), nullable=True))
        op.execute("UPDATE manual_costs SET packaging_cost = 0 WHERE packaging_cost IS NULL")
        op.alter_column("manual_costs", "packaging_cost", existing_type=sa.Numeric(18, 4), nullable=False)
    if "inbound_logistics_cost" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("inbound_logistics_cost", sa.Numeric(18, 4), nullable=True))
        op.execute("UPDATE manual_costs SET inbound_logistics_cost = 0 WHERE inbound_logistics_cost IS NULL")
        op.alter_column("manual_costs", "inbound_logistics_cost", existing_type=sa.Numeric(18, 4), nullable=False)
    if "supplier" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("supplier", sa.String(length=255), nullable=True))
    if "source_file_name" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("source_file_name", sa.String(length=255), nullable=True))
        op.execute(
            """
            UPDATE manual_costs AS costs
            SET source_file_name = uploads.filename
            FROM manual_cost_uploads AS uploads
            WHERE costs.upload_id = uploads.id AND costs.source_file_name IS NULL
            """
        )
    if "uploaded_at" not in manual_cost_columns:
        op.add_column("manual_costs", sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True))
        op.execute(
            """
            UPDATE manual_costs AS costs
            SET uploaded_at = uploads.imported_at
            FROM manual_cost_uploads AS uploads
            WHERE costs.upload_id = uploads.id AND costs.uploaded_at IS NULL
            """
        )
    manual_constraints = _constraint_names("manual_costs")
    if "uq_manual_costs_account_id" not in manual_constraints:
        op.create_unique_constraint(
            "uq_manual_costs_account_id",
            "manual_costs",
            ["account_id", "vendor_code", "nm_id", "barcode", "tech_size", "valid_from"],
        )

    acquiring_constraints = _constraint_names("wb_acquiring_report_rows")
    if "uq_wb_acquiring_report_rows_account_id" not in acquiring_constraints:
        op.create_unique_constraint(
            "uq_wb_acquiring_report_rows_account_id",
            "wb_acquiring_report_rows",
            ["account_id", "report_id", "order_id", "srid", "shk_id", "nm_id"],
        )

    if "mart_sku_daily" not in table_names:
        op.create_table(
            "mart_sku_daily",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("nm_id", sa.Integer(), nullable=True),
            sa.Column("vendor_code", sa.String(length=255), nullable=True),
            sa.Column("barcode", sa.String(length=255), nullable=True),
            sa.Column("title", sa.String(length=500), nullable=True),
            sa.Column("brand", sa.String(length=255), nullable=True),
            sa.Column("subject_name", sa.String(length=255), nullable=True),
            sa.Column("order_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ordered_units", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cancelled_orders", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sale_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sold_units", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("return_units", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("finance_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("finance_net_units", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("realized_revenue", sa.Numeric(18, 4), nullable=True),
            sa.Column("for_pay", sa.Numeric(18, 4), nullable=True),
            sa.Column("commission", sa.Numeric(18, 4), nullable=True),
            sa.Column("acquiring_fee", sa.Numeric(18, 4), nullable=True),
            sa.Column("logistics", sa.Numeric(18, 4), nullable=True),
            sa.Column("paid_acceptance", sa.Numeric(18, 4), nullable=True),
            sa.Column("storage", sa.Numeric(18, 4), nullable=True),
            sa.Column("penalties", sa.Numeric(18, 4), nullable=True),
            sa.Column("deductions", sa.Numeric(18, 4), nullable=True),
            sa.Column("additional_payments", sa.Numeric(18, 4), nullable=True),
            sa.Column("ad_spend", sa.Numeric(18, 4), nullable=True),
            sa.Column("ad_views", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ad_clicks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("funnel_opens", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("funnel_carts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("funnel_orders", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("funnel_buyouts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("current_discounted_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("seller_discount", sa.Integer(), nullable=True),
            sa.Column("club_discount", sa.Integer(), nullable=True),
            sa.Column("cost_price", sa.Numeric(18, 4), nullable=True),
            sa.Column("packaging_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("inbound_logistics_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("total_unit_cost", sa.Numeric(18, 4), nullable=True),
            sa.Column("estimated_cogs", sa.Numeric(18, 4), nullable=True),
            sa.Column("estimated_profit_before_ads", sa.Numeric(18, 4), nullable=True),
            sa.Column("estimated_profit_after_ads", sa.Numeric(18, 4), nullable=True),
            sa.Column("has_manual_cost", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.UniqueConstraint("account_id", "stat_date", "nm_id", "vendor_code", "barcode", name="uq_mart_sku_daily_account_date_article"),
        )
        op.create_index("ix_mart_sku_daily_stat_date", "mart_sku_daily", ["stat_date"], unique=False)
        op.create_index("ix_mart_sku_daily_nm_id", "mart_sku_daily", ["nm_id"], unique=False)

    if "mart_stock_daily" not in table_names:
        op.create_table(
            "mart_stock_daily",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("nm_id", sa.Integer(), nullable=True),
            sa.Column("vendor_code", sa.String(length=255), nullable=True),
            sa.Column("barcode", sa.String(length=255), nullable=True),
            sa.Column("warehouse_id", sa.Integer(), nullable=True),
            sa.Column("warehouse_name", sa.String(length=255), nullable=True),
            sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
            sa.Column("quantity_full", sa.Numeric(18, 4), nullable=True),
            sa.Column("in_way_to_client", sa.Numeric(18, 4), nullable=True),
            sa.Column("in_way_from_client", sa.Numeric(18, 4), nullable=True),
            sa.Column("days_since_last_sale", sa.Integer(), nullable=True),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.UniqueConstraint(
                "account_id",
                "stat_date",
                "nm_id",
                "barcode",
                "warehouse_id",
                "warehouse_name",
                name="uq_mart_stock_daily_account_date_article_warehouse",
            ),
        )
        op.create_index("ix_mart_stock_daily_stat_date", "mart_stock_daily", ["stat_date"], unique=False)
        op.create_index("ix_mart_stock_daily_nm_id", "mart_stock_daily", ["nm_id"], unique=False)

    if "mart_finance_reconciliation" not in table_names:
        op.create_table(
            "mart_finance_reconciliation",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
            sa.Column("stat_date", sa.Date(), nullable=False),
            sa.Column("srid", sa.String(length=255), nullable=False),
            sa.Column("order_id", sa.BigInteger(), nullable=True),
            sa.Column("nm_id", sa.Integer(), nullable=True),
            sa.Column("vendor_code", sa.String(length=255), nullable=True),
            sa.Column("barcode", sa.String(length=255), nullable=True),
            sa.Column("order_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("sale_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("finance_rows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("has_order", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("has_sale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("has_finance", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("order_revenue", sa.Numeric(18, 4), nullable=True),
            sa.Column("sale_revenue", sa.Numeric(18, 4), nullable=True),
            sa.Column("finance_revenue", sa.Numeric(18, 4), nullable=True),
            sa.Column("sale_for_pay", sa.Numeric(18, 4), nullable=True),
            sa.Column("finance_for_pay", sa.Numeric(18, 4), nullable=True),
            sa.Column("revenue_delta", sa.Numeric(18, 4), nullable=True),
            sa.Column("for_pay_delta", sa.Numeric(18, 4), nullable=True),
            sa.Column("status", sa.String(length=64), nullable=False, server_default="matched"),
            sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.UniqueConstraint("account_id", "stat_date", "srid", "nm_id", name="uq_mart_finance_reconciliation_account_date_srid_nm"),
        )
        op.create_index("ix_mart_finance_reconciliation_stat_date", "mart_finance_reconciliation", ["stat_date"], unique=False)
        op.create_index("ix_mart_finance_reconciliation_srid", "mart_finance_reconciliation", ["srid"], unique=False)
        op.create_index("ix_mart_finance_reconciliation_nm_id", "mart_finance_reconciliation", ["nm_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for forward-only stabilization migrations.")
