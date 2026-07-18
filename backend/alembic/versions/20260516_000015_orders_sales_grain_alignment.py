"""Align orders/sales dedupe grain with IDs and strict event-date semantics.

Revision ID: 20260516_000015
Revises: 20260515_000014
Create Date: 2026-05-16 14:10:00
"""

from __future__ import annotations

from alembic import context, op
from sqlalchemy import inspect

revision = "20260516_000015"
down_revision = "20260515_000014"
branch_labels = None
depends_on = None


def _index_exists(table_name: str, index_name: str) -> bool:
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    return index_name in {index["name"] for index in inspect(bind).get_indexes(table_name)}


def _unique_constraint_names(table_name: str) -> set[str]:
    if context.is_offline_mode():
        return set()
    bind = op.get_bind()
    return {constraint["name"] for constraint in inspect(bind).get_unique_constraints(table_name)}


def _iso_timestamptz_expression(column_name: str) -> str:
    return (
        f"CASE "
        f"WHEN {column_name} IS NULL THEN '<null>' "
        f"WHEN to_char(timezone('UTC', {column_name}), 'US') = '000000' "
        f"THEN to_char(timezone('UTC', {column_name}), 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00' "
        f"ELSE to_char(timezone('UTC', {column_name}), 'YYYY-MM-DD\"T\"HH24:MI:SS.US') || '+00:00' "
        f"END"
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


def upgrade() -> None:
    _rebuild_order_dedupe_keys()
    _rebuild_sale_dedupe_keys()

    if context.is_offline_mode():
        op.drop_constraint("uq_wb_orders_account_srid_change_nm_barcode", "wb_orders", type_="unique")
        op.drop_constraint("uq_wb_sales_account_srid_change_nm_barcode", "wb_sales", type_="unique")
        op.create_unique_constraint(
            "uq_wb_orders_account_srid_change_nm_barcode_order",
            "wb_orders",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode", "order_id"],
        )
        op.create_unique_constraint(
            "uq_wb_sales_account_srid_change_nm_barcode_sale",
            "wb_sales",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode", "sale_id"],
        )
        return

    order_constraints = _unique_constraint_names("wb_orders")
    sales_constraints = _unique_constraint_names("wb_sales")
    if "uq_wb_orders_account_srid_change_nm_barcode" in order_constraints:
        op.drop_constraint("uq_wb_orders_account_srid_change_nm_barcode", "wb_orders", type_="unique")
    if "uq_wb_sales_account_srid_change_nm_barcode" in sales_constraints:
        op.drop_constraint("uq_wb_sales_account_srid_change_nm_barcode", "wb_sales", type_="unique")

    order_constraints = _unique_constraint_names("wb_orders")
    sales_constraints = _unique_constraint_names("wb_sales")
    if "uq_wb_orders_account_srid_change_nm_barcode_order" not in order_constraints:
        op.create_unique_constraint(
            "uq_wb_orders_account_srid_change_nm_barcode_order",
            "wb_orders",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode", "order_id"],
        )
    if "uq_wb_sales_account_srid_change_nm_barcode_sale" not in sales_constraints:
        op.create_unique_constraint(
            "uq_wb_sales_account_srid_change_nm_barcode_sale",
            "wb_sales",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode", "sale_id"],
        )


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
