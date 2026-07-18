"""Stage 2 final closure fields for trusted costs and reconciliation buckets.

Revision ID: 20260519_000022
Revises: 20260516_000021
Create Date: 2026-05-19 10:15:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260519_000022"
down_revision = "20260516_000021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manual_costs", sa.Column("cost_source", sa.String(length=64), nullable=True))
    op.execute(
        """
        UPDATE manual_costs
        SET cost_source = CASE
            WHEN UPPER(COALESCE(supplier, '')) = 'AUTO_TEMPLATE' OR COALESCE(is_placeholder, FALSE) = TRUE
                THEN 'placeholder_auto_template'
            WHEN UPPER(COALESCE(supplier, '')) = 'OPERATOR_TRUSTED_COST'
                THEN 'operator_trusted_manual'
            ELSE 'manual_upload'
        END
        WHERE cost_source IS NULL
        """
    )

    op.add_column("mart_reconciliation_daily", sa.Column("status_bucket", sa.String(length=32), nullable=True))
    op.add_column("mart_reconciliation_daily", sa.Column("status_reason", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_mart_reconciliation_daily_status_bucket",
        "mart_reconciliation_daily",
        ["status_bucket"],
        unique=False,
    )
    op.execute(
        """
        UPDATE mart_reconciliation_daily
        SET status_bucket = CASE
                WHEN COALESCE(has_sale_without_finance, FALSE) OR COALESCE(has_finance_without_sale, FALSE) OR COALESCE(has_order_without_sale, FALSE)
                    THEN CASE
                        WHEN (CURRENT_DATE - stat_date) <= 3 THEN 'pending'
                        WHEN (CURRENT_DATE - stat_date) <= 7 THEN 'warning'
                        ELSE 'error'
                    END
                WHEN COALESCE(has_price_anomaly, FALSE) THEN 'warning'
                WHEN COALESCE(has_ad_spend_without_sales, FALSE) THEN 'warning'
                WHEN COALESCE(has_stock_without_sales, FALSE) THEN 'warning'
                ELSE 'ok'
            END,
            status_reason = CASE
                WHEN COALESCE(has_order_without_sale, FALSE) AND (CURRENT_DATE - stat_date) <= 3 THEN 'expected_lag'
                WHEN COALESCE(has_sale_without_finance, FALSE) AND (CURRENT_DATE - stat_date) <= 3 THEN 'expected_lag'
                WHEN COALESCE(has_finance_without_sale, FALSE) AND (CURRENT_DATE - stat_date) <= 3 THEN 'expected_lag'
                WHEN COALESCE(has_order_without_sale, FALSE) THEN 'missing_followup'
                WHEN COALESCE(has_sale_without_finance, FALSE) AND (CURRENT_DATE - stat_date) <= 7 THEN 'finance_lag'
                WHEN COALESCE(has_finance_without_sale, FALSE) AND (CURRENT_DATE - stat_date) <= 7 THEN 'finance_lag'
                WHEN COALESCE(has_sale_without_finance, FALSE) THEN 'missing_finance'
                WHEN COALESCE(has_finance_without_sale, FALSE) THEN 'missing_sale'
                WHEN COALESCE(has_price_anomaly, FALSE) THEN 'price_anomaly'
                WHEN COALESCE(has_ad_spend_without_sales, FALSE) THEN 'ad_spend_without_sales'
                WHEN COALESCE(has_stock_without_sales, FALSE) THEN 'stock_without_sales'
                ELSE 'matched'
            END
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
