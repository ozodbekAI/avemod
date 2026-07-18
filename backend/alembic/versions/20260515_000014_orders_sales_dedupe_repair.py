"""Repair orders and sales dedupe grain.

Revision ID: 20260515_000014
Revises: 20260515_000013
Create Date: 2026-05-15 23:55:00
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "20260515_000014"
down_revision = "20260515_000013"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    if context.is_offline_mode():
        return False
    bind = op.get_bind()
    return column_name in {column["name"] for column in inspect(bind).get_columns(table_name)}


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


def _populate_dedupe_key(table_name: str, prefix: str) -> None:
    del prefix
    op.execute(
        f"""
        UPDATE {table_name}
        SET dedupe_key = encode(
            digest(
                concat_ws(
                    '|',
                    COALESCE(account_id::text, '<null>'),
                    COALESCE(srid, '<null>'),
                    {_iso_timestamptz_expression("last_change_date")},
                    COALESCE(nm_id::text, '<null>'),
                    COALESCE(barcode, '<null>')
                ),
                'sha256'
            ),
            'hex'
        )
        WHERE dedupe_key IS NULL
        """
    )


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column("wb_orders", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
        op.add_column("wb_sales", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
        _populate_dedupe_key("wb_orders", "orders")
        _populate_dedupe_key("wb_sales", "sales")
        op.alter_column("wb_orders", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
        op.alter_column("wb_sales", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
        op.create_index("ix_wb_orders_dedupe_key", "wb_orders", ["dedupe_key"], unique=True)
        op.create_index("ix_wb_sales_dedupe_key", "wb_sales", ["dedupe_key"], unique=True)
        op.drop_constraint("uq_wb_orders_account_id", "wb_orders", type_="unique")
        op.drop_constraint("uq_wb_sales_account_id", "wb_sales", type_="unique")
        op.create_unique_constraint(
            "uq_wb_orders_account_srid_change_nm_barcode",
            "wb_orders",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode"],
        )
        op.create_unique_constraint(
            "uq_wb_sales_account_srid_change_nm_barcode",
            "wb_sales",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode"],
        )
        return

    if not _has_column("wb_orders", "dedupe_key"):
        op.add_column("wb_orders", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    if not _has_column("wb_sales", "dedupe_key"):
        op.add_column("wb_sales", sa.Column("dedupe_key", sa.String(length=64), nullable=True))

    _populate_dedupe_key("wb_orders", "orders")
    _populate_dedupe_key("wb_sales", "sales")

    op.alter_column("wb_orders", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
    op.alter_column("wb_sales", "dedupe_key", existing_type=sa.String(length=64), nullable=False)

    if not _index_exists("wb_orders", "ix_wb_orders_dedupe_key"):
        op.create_index("ix_wb_orders_dedupe_key", "wb_orders", ["dedupe_key"], unique=True)
    if not _index_exists("wb_sales", "ix_wb_sales_dedupe_key"):
        op.create_index("ix_wb_sales_dedupe_key", "wb_sales", ["dedupe_key"], unique=True)

    order_constraints = _unique_constraint_names("wb_orders")
    sales_constraints = _unique_constraint_names("wb_sales")
    if "uq_wb_orders_account_id" in order_constraints:
        op.drop_constraint("uq_wb_orders_account_id", "wb_orders", type_="unique")
    if "uq_wb_sales_account_id" in sales_constraints:
        op.drop_constraint("uq_wb_sales_account_id", "wb_sales", type_="unique")
    order_constraints = _unique_constraint_names("wb_orders")
    sales_constraints = _unique_constraint_names("wb_sales")
    if "uq_wb_orders_account_srid_change_nm_barcode" not in order_constraints:
        op.create_unique_constraint(
            "uq_wb_orders_account_srid_change_nm_barcode",
            "wb_orders",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode"],
        )
    if "uq_wb_sales_account_srid_change_nm_barcode" not in sales_constraints:
        op.create_unique_constraint(
            "uq_wb_sales_account_srid_change_nm_barcode",
            "wb_sales",
            ["account_id", "srid", "last_change_date", "nm_id", "barcode"],
        )


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
