"""Profitability-ready repair.

Revision ID: 20260515_000013
Revises: 20260515_000012
Create Date: 2026-05-15 23:10:00
"""

from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

revision = "20260515_000013"
down_revision = "20260515_000012"
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


def _replace_core_sku_enriched_view() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW v_core_sku_enriched AS
        SELECT
            sku.id,
            sku.account_id,
            sku.nm_id,
            sku.vendor_code,
            sku.barcode,
            sku.tech_size,
            sku.title,
            sku.brand,
            sku.subject_id,
            sku.subject_name,
            price_meta.currency_iso_code,
            price_meta.discount,
            price_meta.club_discount,
            price_values.current_price,
            price_values.current_discounted_price,
            cost.id AS manual_cost_id,
            cost.cost_price,
            cost.packaging_cost,
            cost.inbound_logistics_cost,
            (
                COALESCE(cost.cost_price, cost.unit_cost, 0)
                + COALESCE(cost.packaging_cost, 0)
                + COALESCE(cost.inbound_logistics_cost, 0)
            ) AS total_unit_cost,
            stock.snapshot_at AS latest_stock_snapshot_at,
            stock.quantity AS latest_quantity,
            stock.quantity_full AS latest_quantity_full,
            stock.in_way_to_client AS latest_in_way_to_client,
            stock.in_way_from_client AS latest_in_way_from_client
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
        WHERE sku.is_active = TRUE
        """
    )


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "core_sku",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        )
        op.create_index("ix_core_sku_is_active", "core_sku", ["is_active"], unique=False)
        op.add_column(
            "raw_wb_api_responses",
            sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )
        _replace_core_sku_enriched_view()
        return

    if not _has_column("core_sku", "is_active"):
        op.add_column(
            "core_sku",
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        )
    op.execute("UPDATE core_sku SET is_active = TRUE WHERE is_active IS NULL")
    if not _index_exists("core_sku", "ix_core_sku_is_active"):
        op.create_index("ix_core_sku_is_active", "core_sku", ["is_active"], unique=False)

    if not _has_column("raw_wb_api_responses", "response_headers"):
        op.add_column(
            "raw_wb_api_responses",
            sa.Column("response_headers", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        )

    _replace_core_sku_enriched_view()


def downgrade() -> None:
    raise NotImplementedError("Downgrades are intentionally not supported.")
