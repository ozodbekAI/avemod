"""Repair current-state grain and orders/sales dedupe parity.

Revision ID: 20260516_000016
Revises: 20260516_000015
Create Date: 2026-05-16 16:00:00
"""

from __future__ import annotations

from alembic import op


revision = "20260516_000016"
down_revision = "20260516_000015"
branch_labels = None
depends_on = None


ORDER_VIEW_COLUMNS = [
    "id",
    "created_at",
    "updated_at",
    "account_id",
    "dedupe_key",
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
    "dedupe_key",
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


def _iso_timestamptz_expression(column_name: str) -> str:
    return (
        f"CASE "
        f"WHEN {column_name} IS NULL THEN '<null>' "
        f"WHEN to_char(timezone('UTC', {column_name}), 'US') = '000000' "
        f"THEN to_char(timezone('UTC', {column_name}), 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00' "
        f"ELSE to_char(timezone('UTC', {column_name}), 'YYYY-MM-DD\"T\"HH24:MI:SS.US') || '+00:00' "
        f"END"
    )


def _qualified(columns: list[str]) -> str:
    return ",\n                ".join(f"ranked.{column}" for column in columns)


def _deduplicate_by_dedupe_key(table_name: str) -> None:
    op.execute(
        f"""
        DELETE FROM {table_name}
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY dedupe_key
                        ORDER BY id DESC
                    ) AS rn
                FROM {table_name}
                WHERE dedupe_key IS NOT NULL
            ) ranked
            WHERE ranked.rn > 1
        )
        """
    )


def _rebuild_order_dedupe_keys() -> None:
    op.execute(
        f"""
        UPDATE wb_orders
        SET dedupe_key = encode(
            digest(
                concat_ws(
                    '|',
                    COALESCE(account_id::text, '<null>'),
                    COALESCE(srid, '<null>'),
                    {_iso_timestamptz_expression("last_change_date")},
                    COALESCE(nm_id::text, '<null>'),
                    COALESCE(barcode, '<null>'),
                    COALESCE(order_id::text, '<null>')
                ),
                'sha256'
            ),
            'hex'
        )
        """
    )


def _rebuild_sale_dedupe_keys() -> None:
    op.execute(
        f"""
        UPDATE wb_sales
        SET dedupe_key = encode(
            digest(
                concat_ws(
                    '|',
                    COALESCE(account_id::text, '<null>'),
                    COALESCE(srid, '<null>'),
                    {_iso_timestamptz_expression("last_change_date")},
                    COALESCE(nm_id::text, '<null>'),
                    COALESCE(barcode, '<null>'),
                    COALESCE(sale_id, '<null>')
                ),
                'sha256'
            ),
            'hex'
        )
        """
    )


def _create_or_replace_views() -> None:
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


def upgrade() -> None:
    _rebuild_order_dedupe_keys()
    _rebuild_sale_dedupe_keys()
    _deduplicate_by_dedupe_key("wb_orders")
    _deduplicate_by_dedupe_key("wb_sales")
    _create_or_replace_views()


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
