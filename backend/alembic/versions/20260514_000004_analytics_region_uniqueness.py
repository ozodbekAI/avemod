"""Enforce unique daily region analytics rows.

Revision ID: 20260514_000004
Revises: 20260514_000003
Create Date: 2026-05-14 17:45:00
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260514_000004"
down_revision = "20260514_000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    inspector = sa.inspect(op.get_bind())
    constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("wb_region_sales_daily")}
    op.execute(
        """
        DELETE FROM wb_region_sales_daily
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY account_id, stat_date, region_name, country_name
                        ORDER BY id DESC
                    ) AS row_num
                FROM wb_region_sales_daily
            ) duplicates
            WHERE duplicates.row_num > 1
        )
        """
    )
    if "uq_wb_region_sales_daily_account_date_region_country" not in constraints and "uq_wb_region_sales_daily_account_date_geo_article" not in constraints:
        op.create_unique_constraint(
            "uq_wb_region_sales_daily_account_date_region_country",
            "wb_region_sales_daily",
            ["account_id", "stat_date", "region_name", "country_name"],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_wb_region_sales_daily_account_date_region_country",
        "wb_region_sales_daily",
        type_="unique",
    )
