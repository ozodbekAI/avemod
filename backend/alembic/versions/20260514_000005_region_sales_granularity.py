"""Add granular fields for region sales analytics.

Revision ID: 20260514_000005
Revises: 20260514_000004
Create Date: 2026-05-14 18:05:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision = "20260514_000005"
down_revision = "20260514_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("wb_region_sales_daily")}
    indexes = {index["name"] for index in inspector.get_indexes("wb_region_sales_daily")}
    constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("wb_region_sales_daily")}
    if "city_name" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("city_name", sa.String(length=255), nullable=True))
    if "federal_district" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("federal_district", sa.String(length=255), nullable=True))
    if "nm_id" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("nm_id", sa.Integer(), nullable=True))
    if "vendor_code" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("vendor_code", sa.String(length=255), nullable=True))
    if "sale_amount" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("sale_amount", sa.Numeric(18, 4), nullable=True))
    if "sale_amount_percent" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("sale_amount_percent", sa.Numeric(18, 4), nullable=True))
    if "sale_quantity" not in columns:
        op.add_column("wb_region_sales_daily", sa.Column("sale_quantity", sa.Integer(), nullable=True))
    if op.f("ix_wb_region_sales_daily_nm_id") not in indexes:
        op.create_index(op.f("ix_wb_region_sales_daily_nm_id"), "wb_region_sales_daily", ["nm_id"], unique=False)

    op.execute(
        """
        UPDATE wb_region_sales_daily
        SET
            city_name = payload ->> 'cityName',
            federal_district = payload ->> 'foName',
            nm_id = NULLIF(COALESCE(payload ->> 'nmId', payload ->> 'nmID'), '')::integer,
            vendor_code = COALESCE(payload ->> 'vendorCode', payload ->> 'sa'),
            sale_amount = NULLIF(payload ->> 'saleInvoiceCostPrice', '')::numeric,
            sale_amount_percent = NULLIF(payload ->> 'saleInvoiceCostPricePerc', '')::numeric,
            sale_quantity = NULLIF(payload ->> 'saleItemInvoiceQty', '')::integer
        """
    )

    if "uq_wb_region_sales_daily_account_date_region_country" in constraints:
        op.drop_constraint(
            "uq_wb_region_sales_daily_account_date_region_country",
            "wb_region_sales_daily",
            type_="unique",
        )
    op.execute(
        """
        DELETE FROM wb_region_sales_daily
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY
                            account_id,
                            stat_date,
                            country_name,
                            region_name,
                            city_name,
                            nm_id,
                            vendor_code
                        ORDER BY id DESC
                    ) AS row_num
                FROM wb_region_sales_daily
            ) duplicates
            WHERE duplicates.row_num > 1
        )
        """
    )
    if "uq_wb_region_sales_daily_account_date_geo_article" not in constraints:
        op.create_unique_constraint(
            "uq_wb_region_sales_daily_account_date_geo_article",
            "wb_region_sales_daily",
            [
                "account_id",
                "stat_date",
                "country_name",
                "region_name",
                "city_name",
                "nm_id",
                "vendor_code",
            ],
        )


def downgrade() -> None:
    op.drop_constraint(
        "uq_wb_region_sales_daily_account_date_geo_article",
        "wb_region_sales_daily",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_wb_region_sales_daily_account_date_region_country",
        "wb_region_sales_daily",
        ["account_id", "stat_date", "region_name", "country_name"],
    )
    op.drop_index(op.f("ix_wb_region_sales_daily_nm_id"), table_name="wb_region_sales_daily")
    op.drop_column("wb_region_sales_daily", "sale_quantity")
    op.drop_column("wb_region_sales_daily", "sale_amount_percent")
    op.drop_column("wb_region_sales_daily", "sale_amount")
    op.drop_column("wb_region_sales_daily", "vendor_code")
    op.drop_column("wb_region_sales_daily", "nm_id")
    op.drop_column("wb_region_sales_daily", "federal_district")
    op.drop_column("wb_region_sales_daily", "city_name")
