"""Simplify manual seller costs around seller_other_expense.

Revision ID: 20260603_000027
Revises: 20260603_000026
Create Date: 2026-06-03 15:40:00
"""

from __future__ import annotations

from alembic import op


revision = "20260603_000027"
down_revision = "20260603_000026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE manual_costs
        ADD COLUMN IF NOT EXISTS seller_other_expense NUMERIC(18, 4)
        """
    )
    op.execute(
        """
        UPDATE manual_costs
        SET seller_other_expense = COALESCE(
            seller_other_expense,
            COALESCE(packaging_cost, 0) + COALESCE(inbound_logistics_cost, 0)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE manual_costs
        ALTER COLUMN seller_other_expense SET DEFAULT 0
        """
    )
    op.execute(
        """
        UPDATE manual_costs
        SET seller_other_expense = 0
        WHERE seller_other_expense IS NULL
        """
    )
    op.execute(
        """
        ALTER TABLE manual_costs
        ALTER COLUMN seller_other_expense SET NOT NULL
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN manual_costs.seller_other_expense
        IS 'Primary seller-side per-unit extra expense field used by UI and APIs.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN manual_costs.packaging_cost
        IS 'Deprecated compatibility field. Legacy uploads only.'
        """
    )
    op.execute(
        """
        COMMENT ON COLUMN manual_costs.inbound_logistics_cost
        IS 'Deprecated compatibility field. Legacy uploads only.'
        """
    )

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
            cost.seller_other_expense,
            cost.packaging_cost,
            cost.inbound_logistics_cost,
            cost.supplier,
            cost.cost_source,
            CASE
                WHEN cost.id IS NULL THEN FALSE
                WHEN COALESCE(cost.is_placeholder, FALSE) THEN TRUE
                WHEN UPPER(COALESCE(cost.supplier, '')) LIKE '%%AUTO_TEMPLATE%%' THEN TRUE
                WHEN LOWER(COALESCE(cost.cost_source, '')) LIKE 'placeholder%%' THEN TRUE
                ELSE FALSE
            END AS has_placeholder_cost,
            CASE
                WHEN cost.id IS NULL THEN FALSE
                WHEN COALESCE(cost.is_supplier_confirmed, FALSE) THEN TRUE
                WHEN LOWER(COALESCE(cost.cost_source, '')) = 'supplier_confirmed' THEN TRUE
                ELSE FALSE
            END AS has_real_manual_cost,
            CASE
                WHEN cost.id IS NULL THEN FALSE
                WHEN COALESCE(cost.is_placeholder, FALSE) THEN FALSE
                WHEN UPPER(COALESCE(cost.supplier, '')) LIKE '%%AUTO_TEMPLATE%%' THEN FALSE
                WHEN LOWER(COALESCE(cost.cost_source, '')) LIKE 'placeholder%%' THEN FALSE
                WHEN COALESCE(cost.is_supplier_confirmed, FALSE) THEN TRUE
                WHEN LOWER(COALESCE(cost.cost_source, '')) = 'supplier_confirmed' THEN TRUE
                WHEN COALESCE(cost.is_business_trusted, FALSE) THEN TRUE
                WHEN UPPER(COALESCE(cost.supplier, '')) LIKE '%%OPERATOR_TRUSTED_COST%%' THEN TRUE
                WHEN LOWER(COALESCE(cost.cost_source, '')) IN ('operator_baseline', 'operator_trusted_manual') THEN TRUE
                ELSE FALSE
            END AS business_trusted,
            CASE
                WHEN cost.id IS NULL THEN FALSE
                WHEN COALESCE(cost.is_placeholder, FALSE) THEN FALSE
                WHEN UPPER(COALESCE(cost.supplier, '')) LIKE '%%AUTO_TEMPLATE%%' THEN FALSE
                WHEN LOWER(COALESCE(cost.cost_source, '')) LIKE 'placeholder%%' THEN FALSE
                WHEN COALESCE(cost.is_supplier_confirmed, FALSE) THEN TRUE
                WHEN LOWER(COALESCE(cost.cost_source, '')) = 'supplier_confirmed' THEN TRUE
                WHEN COALESCE(cost.is_business_trusted, FALSE) THEN TRUE
                WHEN UPPER(COALESCE(cost.supplier, '')) LIKE '%%OPERATOR_TRUSTED_COST%%' THEN TRUE
                WHEN LOWER(COALESCE(cost.cost_source, '')) IN ('operator_baseline', 'operator_trusted_manual') THEN TRUE
                ELSE FALSE
            END AS operational_trusted,
            CASE
                WHEN cost.id IS NULL THEN 'missing'
                WHEN COALESCE(cost.is_ambiguous, FALSE) THEN 'ambiguous'
                WHEN COALESCE(cost.is_placeholder, FALSE) OR UPPER(COALESCE(cost.supplier, '')) LIKE '%%AUTO_TEMPLATE%%' OR LOWER(COALESCE(cost.cost_source, '')) LIKE 'placeholder%%' THEN 'placeholder'
                WHEN COALESCE(cost.is_supplier_confirmed, FALSE) OR LOWER(COALESCE(cost.cost_source, '')) = 'supplier_confirmed' THEN 'supplier_confirmed'
                WHEN LOWER(COALESCE(cost.cost_source, '')) = 'estimated_range' THEN 'estimated_range'
                WHEN COALESCE(cost.is_business_trusted, FALSE) OR UPPER(COALESCE(cost.supplier, '')) LIKE '%%OPERATOR_TRUSTED_COST%%' OR LOWER(COALESCE(cost.cost_source, '')) IN ('operator_baseline', 'operator_trusted_manual') THEN 'operator_baseline'
                ELSE 'manual_untrusted'
            END AS cost_truth_level,
            (
                COALESCE(cost.cost_price, cost.unit_cost, 0)
                + COALESCE(
                    cost.seller_other_expense,
                    COALESCE(cost.packaging_cost, 0) + COALESCE(cost.inbound_logistics_cost, 0)
                )
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


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported")
