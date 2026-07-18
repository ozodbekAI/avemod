"""Add final-blocker classification fields and supplier-confirmed manual cost metadata.

Revision ID: 20260528_000025
Revises: 20260528_000024
Create Date: 2026-05-28 22:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260528_000025"
down_revision = "20260528_000024"
branch_labels = None
depends_on = None


FINANCIAL_FINAL_BLOCKER_CODES = (
    "finance_reconciliation_mismatch",
    "finance_without_sale",
    "sale_without_finance",
    "order_without_sale_or_return",
    "missing_manual_cost",
    "manual_cost_unresolved_sku",
    "manual_cost_ambiguous_match",
    "unmatched_sku",
)


def upgrade() -> None:
    op.add_column(
        "data_quality_issues",
        sa.Column("classification_status", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "data_quality_issues",
        sa.Column("classification_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "data_quality_issues",
        sa.Column("classified_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "data_quality_issues",
        sa.Column("classified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "data_quality_issues",
        sa.Column("financial_final_blocker_override", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "data_quality_issues",
        sa.Column(
            "effective_financial_final_blocker",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.create_foreign_key(
        "fk_data_quality_issues_classified_by_user_id_auth_users",
        "data_quality_issues",
        "auth_users",
        ["classified_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_data_quality_issues_classification_status",
        "data_quality_issues",
        ["classification_status"],
        unique=False,
    )
    op.create_index(
        "ix_data_quality_issues_effective_financial_final_blocker",
        "data_quality_issues",
        ["effective_financial_final_blocker"],
        unique=False,
    )

    op.add_column(
        "manual_costs",
        sa.Column(
            "is_supplier_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "manual_costs",
        sa.Column("supplier_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "manual_costs",
        sa.Column("supplier_confirmed_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_manual_costs_supplier_confirmed_by_user_id_auth_users",
        "manual_costs",
        "auth_users",
        ["supplier_confirmed_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        """
        UPDATE data_quality_issues
        SET
            classification_status = COALESCE(NULLIF(LOWER(payload->>'classificationStatus'), ''), NULLIF(LOWER(payload->>'resolutionStatus'), ''), 'unclassified'),
            classification_reason = NULLIF(payload->>'classificationReason', ''),
            effective_financial_final_blocker = CASE
                WHEN resolved_at IS NOT NULL THEN FALSE
                WHEN COALESCE(financial_final_blocker_override, FALSE) = FALSE
                     AND financial_final_blocker_override IS NOT NULL THEN FALSE
                WHEN LOWER(COALESCE(payload->>'classificationStatus', payload->>'resolutionStatus', 'unclassified')) IN ('expected_lag', 'known_exception', 'ignored_non_financial') THEN FALSE
                WHEN LOWER(severity) NOT IN ('error', 'warning', 'critical') THEN FALSE
                WHEN code IN (
                    'finance_reconciliation_mismatch',
                    'finance_without_sale',
                    'sale_without_finance',
                    'order_without_sale_or_return',
                    'missing_manual_cost',
                    'manual_cost_unresolved_sku',
                    'manual_cost_ambiguous_match',
                    'unmatched_sku'
                ) THEN TRUE
                ELSE FALSE
            END
        """
    )

    op.execute(
        """
        UPDATE manual_costs
        SET
            is_supplier_confirmed = CASE
                WHEN LOWER(COALESCE(cost_source, '')) = 'supplier_confirmed' THEN TRUE
                ELSE FALSE
            END,
            supplier_confirmed_at = CASE
                WHEN LOWER(COALESCE(cost_source, '')) = 'supplier_confirmed' THEN COALESCE(uploaded_at, created_at, updated_at)
                ELSE supplier_confirmed_at
            END,
            supplier_confirmed_by_user_id = CASE
                WHEN LOWER(COALESCE(cost_source, '')) = 'supplier_confirmed' THEN COALESCE(uploaded_by_user_id, supplier_confirmed_by_user_id)
                ELSE supplier_confirmed_by_user_id
            END
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

    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_account_status ON data_quality_issues (account_id, resolved_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_account_status_severity ON data_quality_issues (account_id, resolved_at, severity)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_account_status_issue_type ON data_quality_issues (account_id, resolved_at, code)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_account_status_effective_final ON data_quality_issues (account_id, resolved_at, effective_financial_final_blocker)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_account_sku ON data_quality_issues (account_id, sku_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_account_nm ON data_quality_issues (account_id, nm_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_data_quality_issues_created_at ON data_quality_issues (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mart_stock_daily_account_stat_date ON mart_stock_daily (account_id, stat_date)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mart_stock_daily_account_dead_stock ON mart_stock_daily (account_id, is_dead_stock)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mart_stock_daily_account_oos_risk ON mart_stock_daily (account_id, is_out_of_stock_risk)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_status ON action_recommendations (account_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_created_at ON action_recommendations (account_id, created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_priority ON action_recommendations (account_id, priority)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_action_type ON action_recommendations (account_id, action_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_sku ON action_recommendations (account_id, sku_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_action_recommendations_account_nm ON action_recommendations (account_id, nm_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_sku ON manual_costs (account_id, sku_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_nm ON manual_costs (account_id, nm_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_barcode ON manual_costs (account_id, barcode)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_cost_source ON manual_costs (account_id, cost_source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_business_trusted ON manual_costs (account_id, is_business_trusted)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_placeholder ON manual_costs (account_id, is_placeholder)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_manual_costs_account_valid_window ON manual_costs (account_id, valid_from, valid_to)")


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
