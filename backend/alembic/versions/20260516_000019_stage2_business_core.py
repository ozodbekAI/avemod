"""Stage 2 business core and data quality expansion.

Revision ID: 20260516_000019
Revises: 20260516_000018
Create Date: 2026-05-16 14:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260516_000019"
down_revision = "20260516_000018"
branch_labels = None
depends_on = None


def _replace_core_sku_enriched_view() -> None:
    op.execute("DROP VIEW IF EXISTS v_core_sku_enriched")
    op.execute(
        """
        CREATE VIEW v_core_sku_enriched AS
        SELECT
            sku.id,
            sku.account_id,
            sku.nm_id,
            sku.vendor_code,
            sku.supplier_article,
            sku.barcode,
            sku.chrt_id,
            sku.size_id,
            sku.tech_size,
            sku.title,
            sku.brand,
            sku.subject_id,
            sku.subject_name,
            sku.is_active,
            sku.status,
            sku.comment,
            sku.source_updated_at,
            price_meta.currency_iso_code,
            price_meta.discount AS seller_discount,
            price_meta.club_discount,
            price_values.current_price,
            price_values.current_discounted_price,
            cost.id AS manual_cost_id,
            cost.cost_price,
            cost.packaging_cost,
            cost.inbound_logistics_cost,
            cost.supplier,
            (
                COALESCE(cost.cost_price, cost.unit_cost, 0)
                + COALESCE(cost.packaging_cost, 0)
                + COALESCE(cost.inbound_logistics_cost, 0)
            ) AS total_unit_cost,
            stock.snapshot_at AS latest_stock_snapshot_at,
            stock.quantity AS latest_quantity,
            stock.quantity_full AS latest_quantity_full,
            stock.in_way_to_client AS latest_in_way_to_client,
            stock.in_way_from_client AS latest_in_way_from_client,
            latest_sale.latest_sale_date,
            issue_meta.open_issue_count,
            issue_meta.has_open_issues
        FROM core_sku sku
        LEFT JOIN LATERAL (
            SELECT p.*
            FROM wb_prices p
            WHERE p.account_id = sku.account_id AND p.nm_id = sku.nm_id
            ORDER BY p.id DESC
            LIMIT 1
        ) price_meta ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                MIN(ps.price) AS current_price,
                MIN(ps.discounted_price) AS current_discounted_price
            FROM wb_price_sizes ps
            WHERE ps.account_id = sku.account_id AND ps.nm_id = sku.nm_id
        ) price_values ON TRUE
        LEFT JOIN LATERAL (
            SELECT mc.*
            FROM manual_costs mc
            WHERE mc.account_id = sku.account_id
              AND mc.sku_id = sku.id
              AND (mc.valid_from IS NULL OR mc.valid_from <= CURRENT_DATE)
              AND (mc.valid_to IS NULL OR mc.valid_to >= CURRENT_DATE)
            ORDER BY mc.valid_from DESC NULLS LAST, mc.id DESC
            LIMIT 1
        ) cost ON TRUE
        LEFT JOIN LATERAL (
            SELECT snap.snapshot_at, row.quantity, row.quantity_full, row.in_way_to_client, row.in_way_from_client
            FROM wb_stock_snapshot_rows row
            JOIN wb_stock_snapshots snap ON snap.id = row.snapshot_id
            WHERE row.account_id = sku.account_id
              AND row.nm_id = sku.nm_id
              AND row.barcode IS NOT DISTINCT FROM sku.barcode
            ORDER BY snap.snapshot_at DESC, row.id DESC
            LIMIT 1
        ) stock ON TRUE
        LEFT JOIN LATERAL (
            SELECT MAX(date::date) AS latest_sale_date
            FROM v_wb_sales_current sale
            WHERE sale.account_id = sku.account_id
              AND sale.nm_id IS NOT DISTINCT FROM sku.nm_id
              AND sale.barcode IS NOT DISTINCT FROM sku.barcode
        ) latest_sale ON TRUE
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*)::bigint AS open_issue_count,
                (COUNT(*) > 0) AS has_open_issues
            FROM data_quality_issues issue
            WHERE issue.account_id = sku.account_id
              AND issue.resolved_at IS NULL
              AND (
                issue.sku_id = sku.id
                OR (
                    issue.sku_id IS NULL
                    AND issue.nm_id IS NOT NULL
                    AND issue.nm_id = sku.nm_id
                )
              )
        ) issue_meta ON TRUE
        WHERE sku.is_active = TRUE
        """
    )


def upgrade() -> None:
    op.add_column("core_sku", sa.Column("status", sa.String(length=32), nullable=False, server_default="active"))
    op.add_column("core_sku", sa.Column("comment", sa.Text(), nullable=True))
    op.create_index("ix_core_sku_status", "core_sku", ["status"], unique=False)
    op.execute("UPDATE core_sku SET status = CASE WHEN is_active THEN 'active' ELSE 'archived' END WHERE status IS NULL")

    op.add_column("data_quality_issues", sa.Column("entity_type", sa.String(length=64), nullable=True))
    op.add_column("data_quality_issues", sa.Column("entity_id", sa.BigInteger(), nullable=True))
    op.add_column("data_quality_issues", sa.Column("sku_id", sa.BigInteger(), nullable=True))
    op.add_column("data_quality_issues", sa.Column("nm_id", sa.Integer(), nullable=True))
    op.add_column("data_quality_issues", sa.Column("source_table", sa.String(length=128), nullable=True))
    op.create_foreign_key(
        "fk_data_quality_issues_sku_id_core_sku",
        "data_quality_issues",
        "core_sku",
        ["sku_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_data_quality_issues_entity_type", "data_quality_issues", ["entity_type"], unique=False)
    op.create_index("ix_data_quality_issues_entity_id", "data_quality_issues", ["entity_id"], unique=False)
    op.create_index("ix_data_quality_issues_sku_id", "data_quality_issues", ["sku_id"], unique=False)
    op.create_index("ix_data_quality_issues_nm_id", "data_quality_issues", ["nm_id"], unique=False)

    op.add_column("mart_sku_daily", sa.Column("opening_stock_qty", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("closing_stock_qty", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("in_way_to_client", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("in_way_from_client", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("avg_sale_price", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("margin_percent", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("roi_percent", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("drr_percent", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_sku_daily", sa.Column("has_open_issues", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))

    op.create_table(
        "mart_reconciliation_daily",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dedupe_key", sa.String(length=64), nullable=False),
        sa.Column("stat_date", sa.Date(), nullable=False),
        sa.Column("sku_id", sa.BigInteger(), sa.ForeignKey("core_sku.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nm_id", sa.Integer(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("barcode", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("subject_name", sa.String(length=255), nullable=True),
        sa.Column("orders_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("orders_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("sales_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sales_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("returns_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("returns_amount", sa.Numeric(18, 4), nullable=True),
        sa.Column("finance_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("finance_revenue", sa.Numeric(18, 4), nullable=True),
        sa.Column("finance_for_pay", sa.Numeric(18, 4), nullable=True),
        sa.Column("ad_spend", sa.Numeric(18, 4), nullable=True),
        sa.Column("ad_orders", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opening_stock_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("closing_stock_qty", sa.Numeric(18, 4), nullable=True),
        sa.Column("avg_sale_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("current_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("current_discounted_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("revenue_delta", sa.Numeric(18, 4), nullable=True),
        sa.Column("for_pay_delta", sa.Numeric(18, 4), nullable=True),
        sa.Column("has_order_without_sale", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("has_sale_without_finance", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("has_finance_without_sale", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("has_stock_without_sales", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("has_ad_spend_without_sales", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("has_price_anomaly", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("ix_mart_reconciliation_daily_dedupe_key", "mart_reconciliation_daily", ["dedupe_key"], unique=True)
    op.create_index("ix_mart_reconciliation_daily_stat_date", "mart_reconciliation_daily", ["stat_date"], unique=False)
    op.create_index("ix_mart_reconciliation_daily_sku_id", "mart_reconciliation_daily", ["sku_id"], unique=False)
    op.create_unique_constraint(
        "uq_mart_reconciliation_daily_account_date_sku",
        "mart_reconciliation_daily",
        ["account_id", "stat_date", "sku_id"],
    )

    _replace_core_sku_enriched_view()


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
