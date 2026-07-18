"""Repair current-state views to preserve multi-line SRID rows.

Revision ID: 20260515_000011
Revises: 20260515_000010
Create Date: 2026-05-15 23:15:00
"""
from __future__ import annotations

from alembic import op


revision = "20260515_000011"
down_revision = "20260515_000010"
branch_labels = None
depends_on = None


ORDER_VIEW_COLUMNS = [
    "id",
    "created_at",
    "updated_at",
    "account_id",
    "date",
    "last_change_date",
    "srid",
    "g_number",
    "order_id",
    "nm_id",
    "supplier_article",
    "barcode",
    "warehouse_name",
    "warehouse_type",
    "region_name",
    "oblast_okrug_name",
    "country_name",
    "total_price",
    "discount_percent",
    "spp",
    "finished_price",
    "price_with_disc",
    "is_cancel",
    "cancel_date",
]
SALE_VIEW_COLUMNS = [
    "id",
    "created_at",
    "updated_at",
    "account_id",
    "date",
    "last_change_date",
    "srid",
    "sale_id",
    "order_id",
    "nm_id",
    "supplier_article",
    "barcode",
    "warehouse_name",
    "total_price",
    "discount_percent",
    "price_with_disc",
    "finished_price",
    "for_pay",
    "spp",
    "is_supply",
    "is_realization",
    "is_cancel",
    "sticker",
    "category",
    "subject",
    "brand",
]


def _qualified(columns: list[str]) -> str:
    return ",\n                ".join(f"ranked.{column}" for column in columns)


def upgrade() -> None:
    op.execute(
        "DROP VIEW IF EXISTS v_wb_orders_current"
    )
    op.execute(
        f"""
        CREATE VIEW v_wb_orders_current AS
        SELECT
                {_qualified(ORDER_VIEW_COLUMNS)}
        FROM (
            SELECT
                wb_orders.*,
                row_number() OVER (
                    PARTITION BY wb_orders.account_id, wb_orders.srid, wb_orders.nm_id, wb_orders.barcode, wb_orders.order_id
                    ORDER BY wb_orders.last_change_date DESC, wb_orders.id DESC
                ) AS rn
            FROM wb_orders
        ) ranked
        WHERE ranked.rn = 1
        """
    )
    op.execute(
        "DROP VIEW IF EXISTS v_wb_sales_current"
    )
    op.execute(
        f"""
        CREATE VIEW v_wb_sales_current AS
        SELECT
                {_qualified(SALE_VIEW_COLUMNS)}
        FROM (
            SELECT
                wb_sales.*,
                row_number() OVER (
                    PARTITION BY wb_sales.account_id, wb_sales.srid, wb_sales.nm_id, wb_sales.barcode, wb_sales.sale_id
                    ORDER BY wb_sales.last_change_date DESC, wb_sales.id DESC
                ) AS rn
            FROM wb_sales
        ) ranked
        WHERE ranked.rn = 1
        """
    )


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported")
