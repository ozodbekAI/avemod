"""Rebuild orders/sales dedupe keys using canonical UTC ISO strings.

Revision ID: 20260516_000017
Revises: 20260516_000016
Create Date: 2026-05-16 17:10:00
"""

from __future__ import annotations

from alembic import op


revision = "20260516_000017"
down_revision = "20260516_000016"
branch_labels = None
depends_on = None


def _iso_timestamptz_expression(column_name: str) -> str:
    return (
        f"CASE "
        f"WHEN {column_name} IS NULL THEN '<null>' "
        f"WHEN to_char(timezone('UTC', {column_name}), 'US') = '000000' "
        f"THEN to_char(timezone('UTC', {column_name}), 'YYYY-MM-DD\"T\"HH24:MI:SS') || '+00:00' "
        f"ELSE to_char(timezone('UTC', {column_name}), 'YYYY-MM-DD\"T\"HH24:MI:SS.US') || '+00:00' "
        f"END"
    )


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


def upgrade() -> None:
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
    _deduplicate_by_dedupe_key("wb_orders")
    _deduplicate_by_dedupe_key("wb_sales")


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
