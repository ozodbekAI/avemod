"""Stage 2 completion patch: trusted costs and stock turnover metrics.

Revision ID: 20260516_000021
Revises: 20260516_000020
Create Date: 2026-05-18 09:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260516_000021"
down_revision = "20260516_000020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("manual_costs", sa.Column("is_placeholder", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))
    op.add_column("manual_costs", sa.Column("is_business_trusted", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")))
    op.execute(
        """
        UPDATE manual_costs
        SET is_placeholder = TRUE,
            is_business_trusted = FALSE
        WHERE UPPER(COALESCE(supplier, '')) = 'AUTO_TEMPLATE'
        """
    )

    op.add_column("mart_sku_daily", sa.Column("has_real_manual_cost", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))
    op.add_column("mart_sku_daily", sa.Column("has_placeholder_cost", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))
    op.add_column("mart_sku_daily", sa.Column("business_trusted", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))
    op.add_column("mart_sku_daily", sa.Column("cost_source", sa.String(length=64), nullable=True))

    op.add_column("mart_stock_daily", sa.Column("sales_7d", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mart_stock_daily", sa.Column("sales_14d", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mart_stock_daily", sa.Column("sales_30d", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("mart_stock_daily", sa.Column("avg_sales_per_day_30d", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_stock_daily", sa.Column("days_of_stock", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_stock_daily", sa.Column("turnover_rate", sa.Numeric(18, 4), nullable=True))
    op.add_column("mart_stock_daily", sa.Column("is_out_of_stock_risk", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))
    op.add_column("mart_stock_daily", sa.Column("is_dead_stock", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")))


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
