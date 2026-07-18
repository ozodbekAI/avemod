"""Seed Dynamic Problem Engine metric catalog.

Revision ID: 20260706_000057
Revises: 20260706_000056
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260706_000057"
down_revision = "20260706_000056"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def _metric(
    metric_code: str,
    title: str,
    description: str,
    value_type: str,
    unit: str | None,
    grain: str,
    entity_type: str,
    source_module: str,
    *,
    source_tables: list[str],
    source_endpoints: list[str] | None = None,
    required_metrics: list[str] | None = None,
    formula: dict | None = None,
    trust_state: str = "provisional",
) -> dict:
    return {
        "metric_code": metric_code,
        "title": title,
        "description": description,
        "value_type": value_type,
        "unit": unit,
        "grain": grain,
        "entity_type": entity_type,
        "source_module": source_module,
        "formula_json": formula,
        "source_tables_json": source_tables,
        "source_endpoints_json": source_endpoints or [],
        "required_metrics_json": required_metrics or [],
        "trust_state": trust_state,
        "is_admin_visible": True,
        "is_deprecated": False,
    }


METRICS = [
    _metric("stock_qty", "Stock quantity", "Latest product stock quantity from stock mart snapshots.", "count", "pcs", "product_day", "product", "stock", source_tables=["mart_stock_daily", "wb_stock_snapshot_rows"], source_endpoints=["GET /api/v1/stocks"], trust_state="confirmed"),
    _metric("avg_daily_sales_7d", "Average daily sales, 7 days", "Sales velocity over the latest seven-day product window.", "number", "pcs/day", "product_period", "product", "stock", source_tables=["mart_stock_daily", "mart_sku_daily"], required_metrics=["sales_7d"], formula={"/": [{"metric": "sales_7d"}, 7]}, trust_state="confirmed"),
    _metric("avg_daily_sales_14d", "Average daily sales, 14 days", "Sales velocity over the latest fourteen-day product window.", "number", "pcs/day", "product_period", "product", "stock", source_tables=["mart_stock_daily", "mart_sku_daily"], required_metrics=["sales_14d"], formula={"/": [{"metric": "sales_14d"}, 14]}, trust_state="confirmed"),
    _metric("avg_daily_sales_30d", "Average daily sales, 30 days", "Sales velocity over the latest thirty-day product window.", "number", "pcs/day", "product_period", "product", "stock", source_tables=["mart_stock_daily", "mart_sku_daily"], required_metrics=["sales_30d"], formula={"/": [{"metric": "sales_30d"}, 30]}, trust_state="confirmed"),
    _metric("days_of_stock", "Days of stock", "Estimated days before current stock is depleted at the current sales velocity.", "days", "days", "product_day", "product", "stock", source_tables=["mart_stock_daily"], required_metrics=["stock_qty", "avg_daily_sales_30d"], formula={"case": [{"if": {">": [{"metric": "avg_daily_sales_30d"}, 0]}, "then": {"/": [{"metric": "stock_qty"}, {"metric": "avg_daily_sales_30d"}]}}, {"else": None}]}, trust_state="confirmed"),
    _metric("revenue_7d", "Revenue, 7 days", "Product revenue over the latest seven-day window.", "money", "RUB", "product_period", "product", "money", source_tables=["mart_sku_daily"], source_endpoints=["GET /api/v1/marts/sku-daily"], trust_state="confirmed"),
    _metric("revenue_30d", "Revenue, 30 days", "Product revenue over the latest thirty-day window.", "money", "RUB", "product_period", "product", "money", source_tables=["mart_sku_daily"], source_endpoints=["GET /api/v1/marts/sku-daily"], trust_state="confirmed"),
    _metric("orders_7d", "Orders, 7 days", "Product ordered units over the latest seven-day window.", "count", "pcs", "product_period", "product", "orders", source_tables=["mart_sku_daily", "wb_orders"], source_endpoints=["GET /api/v1/orders"], trust_state="confirmed"),
    _metric("orders_30d", "Orders, 30 days", "Product ordered units over the latest thirty-day window.", "count", "pcs", "product_period", "product", "orders", source_tables=["mart_sku_daily", "wb_orders"], source_endpoints=["GET /api/v1/orders"], trust_state="confirmed"),
    _metric("price_current", "Current price", "Current product list price from price size data.", "money", "RUB", "product_day", "product", "pricing", source_tables=["wb_price_sizes", "mart_sku_daily"], source_endpoints=["GET /api/v1/prices"], trust_state="confirmed"),
    _metric("price_after_discount", "Price after discount", "Current product discounted price from price size data.", "money", "RUB", "product_day", "product", "pricing", source_tables=["wb_price_sizes", "mart_sku_daily"], source_endpoints=["GET /api/v1/prices"], trust_state="confirmed"),
    _metric("commission_per_unit", "Commission per unit", "WB commission divided by net units for the product window.", "money", "RUB/unit", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["sales_30d"], trust_state="confirmed"),
    _metric("logistics_per_unit", "Logistics per unit", "WB logistics divided by net units for the product window.", "money", "RUB/unit", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["sales_30d"], trust_state="confirmed"),
    _metric("acquiring_per_unit", "Acquiring per unit", "Acquiring fee divided by net units for the product window.", "money", "RUB/unit", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["sales_30d"], trust_state="confirmed"),
    _metric("storage_fee_per_unit", "Storage fee per unit", "Storage fee divided by net units for the product window.", "money", "RUB/unit", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["sales_30d"], trust_state="confirmed"),
    _metric("ad_spend_7d", "Ad spend, 7 days", "Promotion spend for the product over the latest seven-day window.", "money", "RUB", "product_period", "product", "ads", source_tables=["wb_ad_stats_daily"], source_endpoints=["GET /api/v1/ads/stats"], trust_state="confirmed"),
    _metric("ad_spend_30d", "Ad spend, 30 days", "Promotion spend for the product over the latest thirty-day window.", "money", "RUB", "product_period", "product", "ads", source_tables=["wb_ad_stats_daily"], source_endpoints=["GET /api/v1/ads/stats"], trust_state="confirmed"),
    _metric("promo_spend_30d", "Promo spend, 30 days", "Marketing deduction spend over the latest thirty-day window when finance data carries it.", "money", "RUB", "product_period", "product", "promotion", source_tables=["mart_sku_daily"], trust_state="provisional"),
    _metric("cost_price", "Cost price", "Trusted product cost price from manual costs or populated SKU marts.", "money", "RUB", "product_day", "product", "costs", source_tables=["manual_costs", "mart_sku_daily"], source_endpoints=["GET /api/v1/costs/rows"], trust_state="confirmed"),
    _metric("unit_profit", "Unit profit", "Estimated profit after ads divided by net sold units when trusted cost data exists.", "money", "RUB/unit", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["cost_price", "sales_30d"], trust_state="estimated"),
    _metric("margin_pct", "Margin percent", "Estimated product margin percent when trusted cost data exists.", "percent", "%", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["cost_price", "revenue_30d"], trust_state="estimated"),
    _metric("return_rate", "Return rate", "Return units divided by sale units over the product window.", "percent", "%", "product_period", "product", "money", source_tables=["mart_sku_daily"], trust_state="confirmed"),
    _metric("conversion_rate", "Conversion rate", "Orders divided by product card opens over the latest thirty-day funnel window.", "percent", "%", "product_period", "product", "analytics", source_tables=["wb_card_funnel_daily"], source_endpoints=["GET /api/v1/analytics/card-funnel"], trust_state="provisional"),
    _metric("views_30d", "Views, 30 days", "Product card opens over the latest thirty-day funnel window.", "count", "views", "product_period", "product", "analytics", source_tables=["wb_card_funnel_daily"], source_endpoints=["GET /api/v1/analytics/card-funnel"], trust_state="confirmed"),
    _metric("sales_30d", "Sales, 30 days", "Product sale units over the latest thirty-day window.", "count", "pcs", "product_period", "product", "money", source_tables=["mart_sku_daily", "mart_stock_daily"], source_endpoints=["GET /api/v1/marts/sku-daily"], trust_state="confirmed"),
]


def _metric_table() -> sa.TableClause:
    return sa.table(
        "metric_catalog",
        sa.column("metric_code", sa.String),
        sa.column("title", sa.String),
        sa.column("description", sa.Text),
        sa.column("value_type", sa.String),
        sa.column("unit", sa.String),
        sa.column("grain", sa.String),
        sa.column("entity_type", sa.String),
        sa.column("source_module", sa.String),
        sa.column("formula_json", JSONB),
        sa.column("source_tables_json", JSONB),
        sa.column("source_endpoints_json", JSONB),
        sa.column("required_metrics_json", JSONB),
        sa.column("trust_state", sa.String),
        sa.column("is_admin_visible", sa.Boolean),
        sa.column("is_deprecated", sa.Boolean),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    metric_table = _metric_table()
    stmt = postgresql.insert(metric_table).values(METRICS)
    updatable_columns = {
        key: getattr(stmt.excluded, key)
        for key in (
            "title",
            "description",
            "value_type",
            "unit",
            "grain",
            "entity_type",
            "source_module",
            "formula_json",
            "source_tables_json",
            "source_endpoints_json",
            "required_metrics_json",
            "trust_state",
            "is_admin_visible",
            "is_deprecated",
        )
    }
    updatable_columns["updated_at"] = sa.func.now()
    op.get_bind().execute(
        stmt.on_conflict_do_update(
            index_elements=["metric_code"],
            set_=updatable_columns,
        )
    )


def downgrade() -> None:
    metric_table = _metric_table()
    op.get_bind().execute(metric_table.delete().where(metric_table.c.metric_code.in_([metric["metric_code"] for metric in METRICS])))
