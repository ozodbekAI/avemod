"""Repair schema for backend-correctness marts, dedupe, raw fingerprints, and views.

Revision ID: 20260515_000010
Revises: 20260515_000009
Create Date: 2026-05-15 20:30:00
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260515_000010"
down_revision = "20260515_000009"
branch_labels = None
depends_on = None


def _inspector():
    return sa.inspect(op.get_bind())


def _table_names() -> set[str]:
    return set(_inspector().get_table_names())


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in _inspector().get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in _inspector().get_indexes(table_name)}


def _constraint_names(table_name: str) -> set[str]:
    return {constraint["name"] for constraint in _inspector().get_unique_constraints(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _column_names(table_name):
        op.add_column(table_name, column)


def _create_index_if_missing(table_name: str, name: str, columns: list[str], *, unique: bool = False) -> None:
    if name not in _index_names(table_name):
        op.create_index(name, table_name, columns, unique=unique)


def _create_unique_constraint_if_missing(table_name: str, name: str, columns: list[str]) -> None:
    if name not in _constraint_names(table_name):
        op.create_unique_constraint(name, table_name, columns)


def _backfill_sha256(table_name: str, target_column: str, expressions: list[str]) -> None:
    joined = ", ".join(expressions)
    op.execute(
        f"""
        UPDATE {table_name}
        SET {target_column} = encode(digest(concat_ws('|', {joined}), 'sha256'), 'hex')
        WHERE {target_column} IS NULL
        """
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


def _create_or_replace_views() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW v_wb_orders_current AS
        SELECT *
        FROM (
            SELECT
                wb_orders.*,
                row_number() OVER (
                    PARTITION BY wb_orders.account_id, wb_orders.srid
                    ORDER BY wb_orders.last_change_date DESC, wb_orders.id DESC
                ) AS rn
            FROM wb_orders
        ) ranked
        WHERE ranked.rn = 1
        """
    )
    op.execute(
        """
        CREATE OR REPLACE VIEW v_wb_sales_current AS
        SELECT *
        FROM (
            SELECT
                wb_sales.*,
                row_number() OVER (
                    PARTITION BY wb_sales.account_id, wb_sales.srid
                    ORDER BY wb_sales.last_change_date DESC, wb_sales.id DESC
                ) AS rn
            FROM wb_sales
        ) ranked
        WHERE ranked.rn = 1
        """
    )
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
        """
    )


def upgrade() -> None:
    if context.is_offline_mode():
        return

    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    _add_column_if_missing("raw_wb_api_responses", sa.Column("request_fingerprint", sa.String(length=64), nullable=True))
    _add_column_if_missing("raw_wb_api_responses", sa.Column("response_fingerprint", sa.String(length=64), nullable=True))
    _backfill_sha256(
        "raw_wb_api_responses",
        "request_fingerprint",
        [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(api_category, '<null>')",
            "COALESCE(endpoint, '<null>')",
            "COALESCE(http_method, '<null>')",
            "COALESCE(request_params::text, '<null>')",
            "COALESCE(request_body::text, '<null>')",
        ],
    )
    _backfill_sha256(
        "raw_wb_api_responses",
        "response_fingerprint",
        [
            "COALESCE(status_code::text, '<null>')",
            "COALESCE(is_success::text, '<null>')",
            "COALESCE(response_json::text, '<null>')",
            "COALESCE(response_text, '<null>')",
            "COALESCE(error_text, '<null>')",
        ],
    )
    _create_index_if_missing("raw_wb_api_responses", "ix_raw_wb_api_responses_request_fingerprint", ["request_fingerprint"])
    _create_index_if_missing("raw_wb_api_responses", "ix_raw_wb_api_responses_response_fingerprint", ["response_fingerprint"])

    _add_column_if_missing("core_sku", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    _backfill_sha256(
        "core_sku",
        "dedupe_key",
        [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
            "COALESCE(vendor_code, '<null>')",
            "COALESCE(tech_size, '<null>')",
            "COALESCE(chrt_id::text, '<null>')",
            "COALESCE(size_id::text, '<null>')",
            "COALESCE(barcode, '<null>')",
        ],
    )
    op.alter_column("core_sku", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
    _deduplicate_by_dedupe_key("core_sku")
    _create_index_if_missing("core_sku", "ix_core_sku_dedupe_key", ["dedupe_key"], unique=True)

    _add_column_if_missing("manual_costs", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    _add_column_if_missing("manual_costs", sa.Column("sku_id", sa.BigInteger(), nullable=True))
    _add_column_if_missing("manual_costs", sa.Column("match_rule", sa.String(length=64), nullable=True))
    _add_column_if_missing("manual_costs", sa.Column("is_ambiguous", sa.Boolean(), nullable=True))
    if "sku_id" in _column_names("manual_costs"):
        fk_names = {fk["name"] for fk in _inspector().get_foreign_keys("manual_costs")}
        if "fk_manual_costs_sku_id_core_sku" not in fk_names:
            op.create_foreign_key(
                "fk_manual_costs_sku_id_core_sku",
                "manual_costs",
                "core_sku",
                ["sku_id"],
                ["id"],
                ondelete="SET NULL",
            )
    op.execute("UPDATE manual_costs SET is_ambiguous = FALSE WHERE is_ambiguous IS NULL")
    _backfill_sha256(
        "manual_costs",
        "dedupe_key",
        [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(sku_id::text, '<null>')",
            "COALESCE(vendor_code, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
            "COALESCE(barcode, '<null>')",
            "COALESCE(tech_size, '<null>')",
            "COALESCE(valid_from::text, '<null>')",
        ],
    )
    op.alter_column("manual_costs", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
    op.alter_column("manual_costs", "is_ambiguous", existing_type=sa.Boolean(), nullable=False)
    _deduplicate_by_dedupe_key("manual_costs")
    _create_index_if_missing("manual_costs", "ix_manual_costs_dedupe_key", ["dedupe_key"], unique=True)
    _create_index_if_missing("manual_costs", "ix_manual_costs_sku_id", ["sku_id"])

    for table_name, expressions in {
        "wb_ad_stats_daily": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(stat_date::text, '<null>')",
            "COALESCE(advert_id::text, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
        ],
        "wb_ad_cluster_stats": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(stat_date::text, '<null>')",
            "COALESCE(advert_id::text, '<null>')",
            "COALESCE(cluster, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
        ],
        "wb_region_sales_daily": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(stat_date::text, '<null>')",
            "COALESCE(region_name, '<null>')",
            "COALESCE(country_name, '<null>')",
            "COALESCE(city_name, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
            "COALESCE(vendor_code, '<null>')",
        ],
        "wb_acquiring_report_rows": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(report_id::text, '<null>')",
            "COALESCE(order_id::text, '<null>')",
            "COALESCE(srid, '<null>')",
            "COALESCE(shk_id::text, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
        ],
        "wb_tariff_commissions": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(collected_at::text, '<null>')",
            "COALESCE(parent_id::text, '<null>')",
            "COALESCE(subject_id::text, '<null>')",
            "COALESCE(payload::text, '<null>')",
        ],
        "wb_tariff_boxes": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(collected_at::text, '<null>')",
            "COALESCE(warehouse_name, '<null>')",
            "COALESCE(payload::text, '<null>')",
        ],
        "wb_tariff_pallets": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(collected_at::text, '<null>')",
            "COALESCE(warehouse_name, '<null>')",
            "COALESCE(payload::text, '<null>')",
        ],
        "wb_tariff_returns": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(collected_at::text, '<null>')",
            "COALESCE(warehouse_name, '<null>')",
            "COALESCE(payload::text, '<null>')",
        ],
        "wb_tariff_acceptance": [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(collected_at::text, '<null>')",
            "COALESCE(warehouse_id::text, '<null>')",
            "COALESCE(warehouse_name, '<null>')",
            "COALESCE(coefficient, '<null>')",
            "COALESCE(payload::text, '<null>')",
        ],
    }.items():
        _add_column_if_missing(table_name, sa.Column("dedupe_key", sa.String(length=64), nullable=True))
        _backfill_sha256(table_name, "dedupe_key", expressions)
        op.alter_column(table_name, "dedupe_key", existing_type=sa.String(length=64), nullable=False)
        _deduplicate_by_dedupe_key(table_name)
        _create_index_if_missing(table_name, f"ix_{table_name}_dedupe_key", ["dedupe_key"], unique=True)

    _add_column_if_missing("mart_sku_daily", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("sku_id", sa.BigInteger(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("operational_sales_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("operational_return_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("operational_revenue", sa.Numeric(18, 4), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("operational_for_pay", sa.Numeric(18, 4), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("finance_sales_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("finance_return_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("finance_revenue", sa.Numeric(18, 4), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("finance_for_pay", sa.Numeric(18, 4), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("final_sales_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("final_return_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("final_net_qty", sa.Integer(), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("final_revenue", sa.Numeric(18, 4), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("final_for_pay", sa.Numeric(18, 4), nullable=True))
    _add_column_if_missing("mart_sku_daily", sa.Column("final_revenue_source", sa.String(length=32), nullable=True))
    _backfill_sha256(
        "mart_sku_daily",
        "dedupe_key",
        [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(stat_date::text, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
            "COALESCE(vendor_code, '<null>')",
            "COALESCE(barcode, '<null>')",
        ],
    )
    mart_sku_columns = _column_names("mart_sku_daily")
    for target_column, source_column in (
        ("operational_sales_qty", "sale_rows"),
        ("operational_return_qty", "return_units"),
        ("operational_revenue", "realized_revenue"),
        ("operational_for_pay", "for_pay"),
        ("finance_sales_qty", "sold_units"),
        ("finance_return_qty", "return_units"),
        ("finance_revenue", "realized_revenue"),
        ("finance_for_pay", "for_pay"),
    ):
        if source_column in mart_sku_columns:
            op.execute(
                f"UPDATE mart_sku_daily SET {target_column} = COALESCE({source_column}, 0) "
                f"WHERE {target_column} IS NULL"
            )
    op.execute("UPDATE mart_sku_daily SET final_sales_qty = COALESCE(finance_sales_qty, operational_sales_qty, 0) WHERE final_sales_qty IS NULL")
    op.execute("UPDATE mart_sku_daily SET final_return_qty = COALESCE(finance_return_qty, operational_return_qty, 0) WHERE final_return_qty IS NULL")
    op.execute("UPDATE mart_sku_daily SET final_net_qty = COALESCE(finance_net_units, final_sales_qty - final_return_qty, 0) WHERE final_net_qty IS NULL")
    op.execute("UPDATE mart_sku_daily SET final_revenue = COALESCE(finance_revenue, operational_revenue, 0) WHERE final_revenue IS NULL")
    op.execute("UPDATE mart_sku_daily SET final_for_pay = COALESCE(finance_for_pay, operational_for_pay, 0) WHERE final_for_pay IS NULL")
    op.execute(
        """
        UPDATE mart_sku_daily
        SET final_revenue_source = CASE
            WHEN COALESCE(finance_rows, 0) > 0 THEN 'finance'
            ELSE 'operational'
        END
        WHERE final_revenue_source IS NULL
        """
    )
    op.alter_column("mart_sku_daily", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
    _deduplicate_by_dedupe_key("mart_sku_daily")
    _create_index_if_missing("mart_sku_daily", "ix_mart_sku_daily_dedupe_key", ["dedupe_key"], unique=True)
    _create_index_if_missing("mart_sku_daily", "ix_mart_sku_daily_sku_id", ["sku_id"])

    _add_column_if_missing("mart_stock_daily", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    _add_column_if_missing("mart_stock_daily", sa.Column("sku_id", sa.BigInteger(), nullable=True))
    _backfill_sha256(
        "mart_stock_daily",
        "dedupe_key",
        [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(stat_date::text, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
            "COALESCE(barcode, '<null>')",
            "COALESCE(warehouse_id::text, '<null>')",
            "COALESCE(warehouse_name, '<null>')",
        ],
    )
    op.alter_column("mart_stock_daily", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
    _deduplicate_by_dedupe_key("mart_stock_daily")
    _create_index_if_missing("mart_stock_daily", "ix_mart_stock_daily_dedupe_key", ["dedupe_key"], unique=True)
    _create_index_if_missing("mart_stock_daily", "ix_mart_stock_daily_sku_id", ["sku_id"])

    _add_column_if_missing("mart_finance_reconciliation", sa.Column("dedupe_key", sa.String(length=64), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("sku_id", sa.BigInteger(), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("order_date", sa.Date(), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("sale_date", sa.Date(), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("finance_sale_date", sa.Date(), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("finance_rr_date", sa.Date(), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing("mart_finance_reconciliation", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    _backfill_sha256(
        "mart_finance_reconciliation",
        "dedupe_key",
        [
            "COALESCE(account_id::text, '<null>')",
            "COALESCE(srid, '<null>')",
            "COALESCE(nm_id::text, '<null>')",
        ],
    )
    op.alter_column("mart_finance_reconciliation", "dedupe_key", existing_type=sa.String(length=64), nullable=False)
    _deduplicate_by_dedupe_key("mart_finance_reconciliation")
    _create_index_if_missing("mart_finance_reconciliation", "ix_mart_finance_reconciliation_dedupe_key", ["dedupe_key"], unique=True)
    _create_index_if_missing("mart_finance_reconciliation", "ix_mart_finance_reconciliation_sku_id", ["sku_id"])

    _add_column_if_missing("wb_realization_report_rows", sa.Column("operation_type", sa.String(length=64), nullable=True))
    _add_column_if_missing("wb_realization_report_rows", sa.Column("is_sale_operation", sa.Boolean(), nullable=True))
    _add_column_if_missing("wb_realization_report_rows", sa.Column("is_return_operation", sa.Boolean(), nullable=True))
    _add_column_if_missing("wb_realization_report_rows", sa.Column("is_expense_operation", sa.Boolean(), nullable=True))
    _add_column_if_missing("wb_realization_report_rows", sa.Column("is_reconcilable", sa.Boolean(), nullable=True))
    op.execute(
        """
        UPDATE wb_realization_report_rows
        SET
            operation_type = CASE
                WHEN LOWER(COALESCE(doc_type_name, '')) IN ('продажа', 'sale') THEN 'sale'
                WHEN LOWER(COALESCE(doc_type_name, '')) IN ('возврат', 'return') THEN 'return'
                ELSE 'expense'
            END,
            is_sale_operation = CASE WHEN LOWER(COALESCE(doc_type_name, '')) IN ('продажа', 'sale') THEN TRUE ELSE FALSE END,
            is_return_operation = CASE WHEN LOWER(COALESCE(doc_type_name, '')) IN ('возврат', 'return') THEN TRUE ELSE FALSE END,
            is_expense_operation = CASE WHEN LOWER(COALESCE(doc_type_name, '')) IN ('продажа', 'sale', 'возврат', 'return') THEN FALSE ELSE TRUE END,
            is_reconcilable = CASE WHEN LOWER(COALESCE(doc_type_name, '')) IN ('продажа', 'sale', 'возврат', 'return') THEN TRUE ELSE FALSE END
        WHERE operation_type IS NULL
        """
    )

    for column_name in ("last_enriched_at", "goods_synced_at", "packages_synced_at"):
        _add_column_if_missing("wb_supplies", sa.Column(column_name, sa.DateTime(timezone=True), nullable=True))

    _create_or_replace_views()


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for forward-only repair migrations.")
