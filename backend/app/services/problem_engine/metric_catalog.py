from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ads import WBAdStatsDaily
from app.models.analytics import WBCardFunnelDaily
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.prices import WBPrice, WBPriceSize
from app.models.problem_engine import MetricCatalog
from app.models.sync import WBSyncCursor
from app.schemas.problem_engine import (
    MetricSourceReference,
    ProductMetricResolution,
    ResolvedMetricValue,
)


@dataclass(frozen=True, slots=True)
class MetricCatalogSeed:
    metric_code: str
    title: str
    description: str
    value_type: str
    unit: str | None
    grain: str
    entity_type: str
    source_module: str
    formula_json: dict[str, Any] | None = None
    source_tables_json: list[str] = field(default_factory=list)
    source_endpoints_json: list[str] = field(default_factory=list)
    required_metrics_json: list[str] = field(default_factory=list)
    trust_state: str = "provisional"
    is_admin_visible: bool = True
    is_deprecated: bool = False

    def model_kwargs(self) -> dict[str, Any]:
        return {
            "metric_code": self.metric_code,
            "title": self.title,
            "description": self.description,
            "value_type": self.value_type,
            "unit": self.unit,
            "grain": self.grain,
            "entity_type": self.entity_type,
            "source_module": self.source_module,
            "formula_json": self.formula_json,
            "source_tables_json": list(self.source_tables_json),
            "source_endpoints_json": list(self.source_endpoints_json),
            "required_metrics_json": list(self.required_metrics_json),
            "trust_state": self.trust_state,
            "is_admin_visible": self.is_admin_visible,
            "is_deprecated": self.is_deprecated,
        }


INITIAL_METRIC_DEFINITIONS: tuple[MetricCatalogSeed, ...] = (
    MetricCatalogSeed(
        metric_code="stock_qty",
        title="Stock quantity",
        description="Latest product stock quantity from stock mart snapshots.",
        value_type="count",
        unit="pcs",
        grain="product_day",
        entity_type="product",
        source_module="stock",
        source_tables_json=["mart_stock_daily", "wb_stock_snapshot_rows"],
        source_endpoints_json=["GET /api/v1/stocks"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        metric_code="avg_daily_sales_7d",
        title="Average daily sales, 7 days",
        description="Sales velocity over the latest seven-day product window.",
        value_type="number",
        unit="pcs/day",
        grain="product_period",
        entity_type="product",
        source_module="stock",
        formula_json={"/": [{"metric": "sales_7d"}, 7]},
        source_tables_json=["mart_stock_daily", "mart_sku_daily"],
        required_metrics_json=["sales_7d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        metric_code="avg_daily_sales_14d",
        title="Average daily sales, 14 days",
        description="Sales velocity over the latest fourteen-day product window.",
        value_type="number",
        unit="pcs/day",
        grain="product_period",
        entity_type="product",
        source_module="stock",
        formula_json={"/": [{"metric": "sales_14d"}, 14]},
        source_tables_json=["mart_stock_daily", "mart_sku_daily"],
        required_metrics_json=["sales_14d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        metric_code="avg_daily_sales_30d",
        title="Average daily sales, 30 days",
        description="Sales velocity over the latest thirty-day product window.",
        value_type="number",
        unit="pcs/day",
        grain="product_period",
        entity_type="product",
        source_module="stock",
        formula_json={"/": [{"metric": "sales_30d"}, 30]},
        source_tables_json=["mart_stock_daily", "mart_sku_daily"],
        required_metrics_json=["sales_30d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        metric_code="days_of_stock",
        title="Days of stock",
        description="Estimated days before current stock is depleted at the current sales velocity.",
        value_type="days",
        unit="days",
        grain="product_day",
        entity_type="product",
        source_module="stock",
        formula_json={
            "case": [
                {
                    "if": {">": [{"metric": "avg_daily_sales_30d"}, 0]},
                    "then": {
                        "/": [
                            {"metric": "stock_qty"},
                            {"metric": "avg_daily_sales_30d"},
                        ]
                    },
                },
                {"else": None},
            ]
        },
        source_tables_json=["mart_stock_daily"],
        required_metrics_json=["stock_qty", "avg_daily_sales_30d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "revenue_7d",
        "Revenue, 7 days",
        "Product revenue over the latest seven-day window.",
        "money",
        "RUB",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        source_endpoints_json=["GET /api/v1/marts/sku-daily"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "avg_daily_revenue_7d",
        "Average daily revenue, 7 days",
        "Product revenue per day over the latest seven-day window.",
        "money",
        "RUB/day",
        "product_period",
        "product",
        "money",
        formula_json={"/": [{"metric": "revenue_7d"}, 7]},
        source_tables_json=["mart_sku_daily"],
        source_endpoints_json=["GET /api/v1/marts/sku-daily"],
        required_metrics_json=["revenue_7d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "revenue_30d",
        "Revenue, 30 days",
        "Product revenue over the latest thirty-day window.",
        "money",
        "RUB",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        source_endpoints_json=["GET /api/v1/marts/sku-daily"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "orders_7d",
        "Orders, 7 days",
        "Product ordered units over the latest seven-day window.",
        "count",
        "pcs",
        "product_period",
        "product",
        "orders",
        source_tables_json=["mart_sku_daily", "wb_orders"],
        source_endpoints_json=["GET /api/v1/orders"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "orders_30d",
        "Orders, 30 days",
        "Product ordered units over the latest thirty-day window.",
        "count",
        "pcs",
        "product_period",
        "product",
        "orders",
        source_tables_json=["mart_sku_daily", "wb_orders"],
        source_endpoints_json=["GET /api/v1/orders"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "price_current",
        "Current price",
        "Current product list price from price payload or price size data.",
        "money",
        "RUB",
        "product_day",
        "product",
        "pricing",
        source_tables_json=["wb_prices", "wb_price_sizes", "mart_sku_daily"],
        source_endpoints_json=["GET /api/v1/prices"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "price_after_discount",
        "Price after discount",
        "Current product discounted price from price payload or price size data.",
        "money",
        "RUB",
        "product_day",
        "product",
        "pricing",
        source_tables_json=["wb_prices", "wb_price_sizes", "mart_sku_daily"],
        source_endpoints_json=["GET /api/v1/prices"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "commission_per_unit",
        "Commission per unit",
        "WB commission divided by net units for the product window.",
        "money",
        "RUB/unit",
        "product_period",
        "product",
        "money",
        formula_json={"/": [{"metric": "commission_total"}, {"metric": "sales_30d"}]},
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["sales_30d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "logistics_per_unit",
        "Logistics per unit",
        "WB logistics divided by net units for the product window.",
        "money",
        "RUB/unit",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["sales_30d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "acquiring_per_unit",
        "Acquiring per unit",
        "Acquiring fee divided by net units for the product window.",
        "money",
        "RUB/unit",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["sales_30d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "storage_fee_per_unit",
        "Storage fee per unit",
        "Storage fee divided by net units for the product window.",
        "money",
        "RUB/unit",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["sales_30d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "ad_spend_7d",
        "Ad spend, 7 days",
        "Promotion spend for the product over the latest seven-day window.",
        "money",
        "RUB",
        "product_period",
        "product",
        "ads",
        source_tables_json=["wb_ad_stats_daily"],
        source_endpoints_json=["GET /api/v1/ads/stats"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "ad_spend_30d",
        "Ad spend, 30 days",
        "Promotion spend for the product over the latest thirty-day window.",
        "money",
        "RUB",
        "product_period",
        "product",
        "ads",
        source_tables_json=["wb_ad_stats_daily"],
        source_endpoints_json=["GET /api/v1/ads/stats"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "promo_spend_30d",
        "Promo spend, 30 days",
        "Marketing deduction spend over the latest thirty-day window when finance data carries it.",
        "money",
        "RUB",
        "product_period",
        "product",
        "promotion",
        source_tables_json=["mart_sku_daily"],
        trust_state="provisional",
    ),
    MetricCatalogSeed(
        "cost_price",
        "Cost price",
        "Trusted product cost price from manual costs or populated SKU marts.",
        "money",
        "RUB",
        "product_day",
        "product",
        "costs",
        source_tables_json=["manual_costs", "mart_sku_daily"],
        source_endpoints_json=["GET /api/v1/costs/rows"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "unit_profit",
        "Unit profit",
        "Estimated profit after ads divided by net sold units when trusted cost data exists.",
        "money",
        "RUB/unit",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["cost_price", "sales_30d"],
        trust_state="estimated",
    ),
    MetricCatalogSeed(
        "margin_pct",
        "Margin percent",
        "Estimated product margin percent when trusted cost data exists.",
        "percent",
        "%",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["cost_price", "revenue_30d"],
        trust_state="estimated",
    ),
    MetricCatalogSeed(
        "return_rate",
        "Return rate",
        "Return units divided by sale units over the product window.",
        "percent",
        "%",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "conversion_rate",
        "Conversion rate",
        "Orders divided by product card opens over the latest thirty-day funnel window.",
        "percent",
        "%",
        "product_period",
        "product",
        "analytics",
        source_tables_json=["wb_card_funnel_daily"],
        source_endpoints_json=["GET /api/v1/analytics/card-funnel"],
        trust_state="provisional",
    ),
    MetricCatalogSeed(
        "views_30d",
        "Views, 30 days",
        "Product card opens over the latest thirty-day funnel window.",
        "count",
        "views",
        "product_period",
        "product",
        "analytics",
        source_tables_json=["wb_card_funnel_daily"],
        source_endpoints_json=["GET /api/v1/analytics/card-funnel"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "sales_7d",
        "Sales, 7 days",
        "Product sale units over the latest seven-day window.",
        "count",
        "pcs",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily", "mart_stock_daily"],
        source_endpoints_json=["GET /api/v1/marts/sku-daily"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "sales_30d",
        "Sales, 30 days",
        "Product sale units over the latest thirty-day window.",
        "count",
        "pcs",
        "product_period",
        "product",
        "money",
        source_tables_json=["mart_sku_daily", "mart_stock_daily"],
        source_endpoints_json=["GET /api/v1/marts/sku-daily"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "units_sold_7d",
        "Units sold, 7 days",
        "Alias for seven-day product sold units used by ad profitability rules.",
        "count",
        "pcs",
        "product_period",
        "product",
        "money",
        formula_json={"metric": "sales_7d"},
        source_tables_json=["mart_sku_daily", "mart_stock_daily"],
        source_endpoints_json=["GET /api/v1/marts/sku-daily"],
        required_metrics_json=["sales_7d"],
        trust_state="confirmed",
    ),
    MetricCatalogSeed(
        "unit_profit_after_ads",
        "Unit profit after ads",
        "Estimated profit after ads divided by net sold units when trusted cost data exists.",
        "money",
        "RUB/unit",
        "product_period",
        "product",
        "money",
        formula_json={"metric": "unit_profit"},
        source_tables_json=["mart_sku_daily"],
        required_metrics_json=["cost_price", "sales_30d", "unit_profit"],
        trust_state="estimated",
    ),
)


INITIAL_METRIC_CODES = frozenset(
    definition.metric_code for definition in INITIAL_METRIC_DEFINITIONS
)


class MetricCatalogService:
    def initial_definitions(self) -> list[MetricCatalogSeed]:
        return list(INITIAL_METRIC_DEFINITIONS)

    def initial_metric_codes(self) -> set[str]:
        return set(INITIAL_METRIC_CODES)

    async def seed_initial_metrics(self, session: AsyncSession) -> list[MetricCatalog]:
        definitions = self.initial_definitions()
        codes = [definition.metric_code for definition in definitions]
        result = await session.execute(
            select(MetricCatalog).where(MetricCatalog.metric_code.in_(codes))
        )
        existing_by_code = {metric.metric_code: metric for metric in result.scalars()}

        seeded: list[MetricCatalog] = []
        for definition in definitions:
            payload = definition.model_kwargs()
            metric = existing_by_code.get(definition.metric_code)
            if metric is None:
                metric = MetricCatalog(**payload)
                session.add(metric)
            else:
                for key, value in payload.items():
                    setattr(metric, key, value)
            seeded.append(metric)

        await session.flush()
        return seeded

    async def list_metrics(
        self,
        session: AsyncSession,
        *,
        admin_visible_only: bool = False,
        include_deprecated: bool = False,
    ) -> list[MetricCatalog]:
        stmt = select(MetricCatalog)
        if admin_visible_only:
            stmt = stmt.where(MetricCatalog.is_admin_visible.is_(True))
        if not include_deprecated:
            stmt = stmt.where(MetricCatalog.is_deprecated.is_(False))
        stmt = stmt.order_by(MetricCatalog.metric_code.asc())
        result = await session.execute(stmt)
        return list(result.scalars())

    async def metric_map(
        self,
        session: AsyncSession,
        metric_codes: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, MetricCatalog]:
        stmt = select(MetricCatalog).where(MetricCatalog.is_deprecated.is_(False))
        if metric_codes is not None:
            stmt = stmt.where(MetricCatalog.metric_code.in_(list(metric_codes)))
        result = await session.execute(stmt)
        return {metric.metric_code: metric for metric in result.scalars()}

    async def allowed_metric_codes(self, session: AsyncSession) -> set[str]:
        return set((await self.metric_map(session)).keys())


class ProductMetricResolver:
    def __init__(self, catalog_service: MetricCatalogService | None = None) -> None:
        self.catalog_service = catalog_service or MetricCatalogService()

    async def resolve_product_metrics(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
        metric_codes: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> ProductMetricResolution:
        if date_from > date_to:
            raise ValueError("date_from must be before or equal to date_to")

        requested_codes = (
            sorted(INITIAL_METRIC_CODES)
            if metric_codes is None
            else list(dict.fromkeys(metric_codes))
        )
        catalog_by_code = await self.catalog_service.metric_map(
            session, requested_codes
        )
        source_data = await self._load_source_data(
            session,
            account_id=account_id,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
        )
        resolution = ProductMetricResolution(
            account_id=account_id, nm_id=nm_id, date_from=date_from, date_to=date_to
        )

        for metric_code in requested_codes:
            catalog = catalog_by_code.get(metric_code)
            if catalog is None:
                resolution.metrics[metric_code] = self._missing_value(
                    metric_code,
                    value_type=None,
                    unit=None,
                    trust_state=None,
                    reason="unknown_metric",
                    evidence=MetricSourceReference(
                        source_module="metric_catalog",
                        source_table="metric_catalog",
                        date_from=date_from,
                        date_to=date_to,
                        row_count=0,
                        filters={"account_id": account_id, "nm_id": nm_id},
                        notes=["Metric code is not present in metric_catalog."],
                    ),
                )
                resolution.missing_metrics.append(metric_code)
                continue

            resolved = self._resolve_metric(
                metric_code,
                catalog=catalog,
                source_data=source_data,
                date_from=date_from,
                date_to=date_to,
                account_id=account_id,
                nm_id=nm_id,
            )
            resolution.metrics[metric_code] = resolved
            if resolved.is_missing:
                resolution.missing_metrics.append(metric_code)

        return resolution

    async def _load_source_data(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        freshness = await self._sync_freshness(session, account_id=account_id)
        source_data = {
            "freshness": freshness,
            "sku_7d": await self._sku_aggregate(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
                days=7,
            ),
            "sku_14d": await self._sku_aggregate(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
                days=14,
            ),
            "sku_30d": await self._sku_aggregate(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
                days=30,
            ),
            "stock_latest": await self._stock_latest(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
            ),
            "price_latest": await self._price_latest(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
            ),
            "manual_cost": await self._manual_cost_latest(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
            ),
            "ad_7d": await self._ad_aggregate(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
                days=7,
            ),
            "ad_30d": await self._ad_aggregate(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
                days=30,
            ),
            "funnel_30d": await self._funnel_aggregate(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
                days=30,
            ),
        }
        for value in source_data.values():
            if isinstance(value, dict):
                value.setdefault("freshness", freshness)
        return source_data

    async def _sync_freshness(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, Any]:
        try:
            result = await session.execute(
                select(WBSyncCursor).where(WBSyncCursor.account_id == account_id)
            )
        except SQLAlchemyError:
            return {"available": False}
        freshness: dict[str, Any] = {"available": True, "domains": {}}
        for cursor in result.scalars():
            freshness["domains"][cursor.domain] = {
                "last_synced_at": cursor.last_synced_at,
                "status": cursor.status,
                "cursor_key": cursor.cursor_key,
            }
        return freshness

    async def _sku_aggregate(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
        days: int,
    ) -> dict[str, Any]:
        window_start = self._window_start(
            date_from=date_from, date_to=date_to, days=days
        )
        stmt = select(
            func.count(MartSKUDaily.id).label("row_count"),
            func.max(MartSKUDaily.stat_date).label("latest_date"),
            func.sum(MartSKUDaily.final_revenue).label("revenue"),
            func.count(MartSKUDaily.final_revenue).label("revenue_count"),
            func.sum(MartSKUDaily.ordered_units).label("orders"),
            func.sum(MartSKUDaily.final_sales_qty).label("sales_qty"),
            func.sum(MartSKUDaily.final_return_qty).label("return_qty"),
            func.sum(MartSKUDaily.final_net_qty).label("net_qty"),
            func.sum(MartSKUDaily.commission).label("commission"),
            func.sum(MartSKUDaily.logistics).label("logistics"),
            func.sum(MartSKUDaily.acquiring_fee).label("acquiring"),
            func.sum(MartSKUDaily.storage).label("storage"),
            func.sum(MartSKUDaily.marketing_deduction).label("promo_spend"),
            func.count(MartSKUDaily.marketing_deduction).label("promo_spend_count"),
            func.sum(MartSKUDaily.estimated_profit_after_ads).label(
                "estimated_profit_after_ads"
            ),
            func.count(MartSKUDaily.estimated_profit_after_ads).label(
                "estimated_profit_after_ads_count"
            ),
            func.avg(MartSKUDaily.margin_percent).label("margin_percent"),
            func.count(MartSKUDaily.margin_percent).label("margin_percent_count"),
            func.count(MartSKUDaily.cost_price).label("cost_price_count"),
            func.max(MartSKUDaily.updated_at).label("latest_updated_at"),
        ).where(
            MartSKUDaily.account_id == account_id,
            MartSKUDaily.nm_id == nm_id,
            MartSKUDaily.stat_date >= window_start,
            MartSKUDaily.stat_date <= date_to,
        )
        row = (await session.execute(stmt)).mappings().one()
        latest_row = (
            await session.execute(
                select(MartSKUDaily)
                .where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.nm_id == nm_id,
                    MartSKUDaily.stat_date >= window_start,
                    MartSKUDaily.stat_date <= date_to,
                )
                .order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            **dict(row),
            "window_start": window_start,
            "window_end": date_to,
            "latest_row": latest_row,
        }

    async def _stock_latest(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        latest_date = (
            await session.execute(
                select(func.max(MartStockDaily.stat_date)).where(
                    MartStockDaily.account_id == account_id,
                    MartStockDaily.nm_id == nm_id,
                    MartStockDaily.stat_date >= date_from,
                    MartStockDaily.stat_date <= date_to,
                )
            )
        ).scalar_one_or_none()
        if latest_date is None:
            return {"row_count": 0, "latest_date": None}

        row = (
            (
                await session.execute(
                    select(
                        func.count(MartStockDaily.id).label("row_count"),
                        func.sum(MartStockDaily.quantity).label("quantity"),
                        func.count(MartStockDaily.quantity).label("quantity_count"),
                        func.sum(MartStockDaily.quantity_full).label("quantity_full"),
                        func.max(MartStockDaily.sales_7d).label("sales_7d"),
                        func.max(MartStockDaily.sales_14d).label("sales_14d"),
                        func.max(MartStockDaily.sales_30d).label("sales_30d"),
                        func.max(MartStockDaily.updated_at).label("latest_updated_at"),
                    ).where(
                        MartStockDaily.account_id == account_id,
                        MartStockDaily.nm_id == nm_id,
                        MartStockDaily.stat_date == latest_date,
                    )
                )
            )
            .mappings()
            .one()
        )
        stock = dict(row)
        stock["latest_date"] = latest_date
        quantity = self._decimal_or_none(stock.get("quantity"))
        quantity_full = self._decimal_or_none(stock.get("quantity_full"))
        stock["stock_qty"] = quantity if quantity is not None else quantity_full
        sales_30d = self._decimal_or_none(stock.get("sales_30d"))
        if stock["stock_qty"] is not None and sales_30d is not None and sales_30d > 0:
            stock["days_of_stock"] = stock["stock_qty"] / (sales_30d / Decimal("30"))
        else:
            stock["days_of_stock"] = None
        return stock

    async def _price_latest(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        price_row = (
            await session.execute(
                select(WBPrice)
                .where(WBPrice.account_id == account_id, WBPrice.nm_id == nm_id)
                .order_by(WBPrice.updated_at.desc(), WBPrice.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        payload_price = self._price_from_goods_payload(
            price_row.payload if price_row is not None else None
        )
        if payload_price is not None:
            return {
                **payload_price,
                "latest_updated_at": price_row.updated_at
                if price_row is not None
                else None,
                "window_start": date_from,
                "window_end": date_to,
                "source_table": "wb_prices",
            }

        row = (
            (
                await session.execute(
                    select(
                        func.count(WBPriceSize.id).label("row_count"),
                        func.min(WBPriceSize.price).label("price_current"),
                        func.min(WBPriceSize.discounted_price).label(
                            "price_after_discount"
                        ),
                        func.max(WBPriceSize.updated_at).label("latest_updated_at"),
                    ).where(
                        WBPriceSize.account_id == account_id, WBPriceSize.nm_id == nm_id
                    )
                )
            )
            .mappings()
            .one()
        )
        return {
            **dict(row),
            "window_start": date_from,
            "window_end": date_to,
            "source_table": "wb_price_sizes",
        }

    async def _manual_cost_latest(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        eligible_filters = (
            ManualCost.account_id == account_id,
            ManualCost.nm_id == nm_id,
            or_(ManualCost.valid_from.is_(None), ManualCost.valid_from <= date_to),
            or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= date_from),
            ManualCost.is_placeholder.is_(False),
            ManualCost.is_ambiguous.is_(False),
            ManualCost.is_business_trusted.is_(True),
        )
        row_count = (
            await session.execute(
                select(func.count(ManualCost.id)).where(*eligible_filters)
            )
        ).scalar_one()
        row = (
            await session.execute(
                select(ManualCost)
                .where(*eligible_filters)
                .order_by(
                    ManualCost.valid_from.desc().nullslast(), ManualCost.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return {
            "row_count": row_count,
            "latest_row": row,
            "window_start": date_from,
            "window_end": date_to,
        }

    async def _ad_aggregate(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
        days: int,
    ) -> dict[str, Any]:
        window_start = self._window_start(
            date_from=date_from, date_to=date_to, days=days
        )
        row = (
            (
                await session.execute(
                    select(
                        func.count(WBAdStatsDaily.id).label("row_count"),
                        func.sum(WBAdStatsDaily.sum).label("spend"),
                        func.count(WBAdStatsDaily.sum).label("spend_count"),
                        func.sum(WBAdStatsDaily.views).label("views"),
                        func.sum(WBAdStatsDaily.orders).label("orders"),
                        func.max(WBAdStatsDaily.stat_date).label("latest_date"),
                        func.max(WBAdStatsDaily.updated_at).label("latest_updated_at"),
                    ).where(
                        WBAdStatsDaily.account_id == account_id,
                        WBAdStatsDaily.nm_id == nm_id,
                        WBAdStatsDaily.stat_date >= window_start,
                        WBAdStatsDaily.stat_date <= date_to,
                    )
                )
            )
            .mappings()
            .one()
        )
        return {**dict(row), "window_start": window_start, "window_end": date_to}

    async def _funnel_aggregate(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
        days: int,
    ) -> dict[str, Any]:
        window_start = self._window_start(
            date_from=date_from, date_to=date_to, days=days
        )
        row = (
            (
                await session.execute(
                    select(
                        func.count(WBCardFunnelDaily.id).label("row_count"),
                        func.sum(WBCardFunnelDaily.open_count).label("views"),
                        func.sum(WBCardFunnelDaily.order_count).label("orders"),
                        func.max(WBCardFunnelDaily.stat_date).label("latest_date"),
                        func.max(WBCardFunnelDaily.updated_at).label(
                            "latest_updated_at"
                        ),
                    ).where(
                        WBCardFunnelDaily.account_id == account_id,
                        WBCardFunnelDaily.nm_id == nm_id,
                        WBCardFunnelDaily.stat_date >= window_start,
                        WBCardFunnelDaily.stat_date <= date_to,
                    )
                )
            )
            .mappings()
            .one()
        )
        return {**dict(row), "window_start": window_start, "window_end": date_to}

    def _resolve_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        source_data: dict[str, Any],
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        match metric_code:
            case "stock_qty":
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=source_data["stock_latest"].get("stock_qty"),
                    source_data=source_data["stock_latest"],
                    source_table="mart_stock_daily",
                    sync_domain="stocks",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "avg_daily_sales_7d":
                return self._average_sales_metric(
                    metric_code,
                    catalog=catalog,
                    stock=source_data["stock_latest"],
                    sku=source_data["sku_7d"],
                    days=7,
                    sync_domain="stocks",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "avg_daily_sales_14d":
                return self._average_sales_metric(
                    metric_code,
                    catalog=catalog,
                    stock=source_data["stock_latest"],
                    sku=source_data["sku_14d"],
                    days=14,
                    sync_domain="stocks",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "avg_daily_sales_30d":
                return self._average_sales_metric(
                    metric_code,
                    catalog=catalog,
                    stock=source_data["stock_latest"],
                    sku=source_data["sku_30d"],
                    days=30,
                    sync_domain="stocks",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "days_of_stock":
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=source_data["stock_latest"].get("days_of_stock"),
                    source_data=source_data["stock_latest"],
                    source_table="mart_stock_daily",
                    sync_domain="stocks",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "revenue_7d":
                return self._sku_sum_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_7d"],
                    field="revenue",
                    count_field="revenue_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "avg_daily_revenue_7d":
                return self._average_revenue_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_7d"],
                    days=7,
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "revenue_30d":
                return self._sku_sum_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    field="revenue",
                    count_field="revenue_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "orders_7d":
                return self._sku_sum_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_7d"],
                    field="orders",
                    count_field="row_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "orders_30d":
                return self._sku_sum_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    field="orders",
                    count_field="row_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "price_current":
                price_value = source_data["price_latest"].get("price_current")
                source = source_data["price_latest"]
                source_table = str(source.get("source_table") or "wb_price_sizes")
                if (
                    price_value is None
                    and source_data["sku_30d"].get("latest_row") is not None
                ):
                    price_value = source_data["sku_30d"]["latest_row"].current_price
                    source = source_data["sku_30d"]
                    source_table = "mart_sku_daily"
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=price_value,
                    source_data=source,
                    source_table=source_table,
                    sync_domain="prices",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "price_after_discount":
                price_value = source_data["price_latest"].get("price_after_discount")
                source = source_data["price_latest"]
                source_table = str(source.get("source_table") or "wb_price_sizes")
                if (
                    price_value is None
                    and source_data["sku_30d"].get("latest_row") is not None
                ):
                    price_value = source_data["sku_30d"][
                        "latest_row"
                    ].current_discounted_price
                    source = source_data["sku_30d"]
                    source_table = "mart_sku_daily"
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=price_value,
                    source_data=source,
                    source_table=source_table,
                    sync_domain="prices",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "commission_per_unit":
                return self._per_unit_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    amount_field="commission",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "logistics_per_unit":
                return self._per_unit_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    amount_field="logistics",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "acquiring_per_unit":
                return self._per_unit_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    amount_field="acquiring",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "storage_fee_per_unit":
                return self._per_unit_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    amount_field="storage",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "ad_spend_7d":
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=source_data["ad_7d"].get("spend"),
                    source_data=source_data["ad_7d"],
                    source_table="wb_ad_stats_daily",
                    sync_domain="ads",
                    count_field="spend_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "ad_spend_30d":
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=source_data["ad_30d"].get("spend"),
                    source_data=source_data["ad_30d"],
                    source_table="wb_ad_stats_daily",
                    sync_domain="ads",
                    count_field="spend_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "promo_spend_30d":
                return self._sku_sum_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    field="promo_spend",
                    count_field="promo_spend_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "cost_price":
                return self._cost_price_metric(
                    metric_code,
                    catalog=catalog,
                    source_data=source_data,
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "unit_profit":
                return self._unit_profit_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "margin_pct":
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=source_data["sku_30d"].get("margin_percent"),
                    source_data=source_data["sku_30d"],
                    source_table="mart_sku_daily",
                    sync_domain="finance",
                    count_field="margin_percent_count",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "return_rate":
                return self._return_rate_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "conversion_rate":
                return self._conversion_rate_metric(
                    metric_code,
                    catalog=catalog,
                    funnel=source_data["funnel_30d"],
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "views_30d":
                return self._from_source(
                    metric_code,
                    catalog=catalog,
                    value=source_data["funnel_30d"].get("views"),
                    source_data=source_data["funnel_30d"],
                    source_table="wb_card_funnel_daily",
                    sync_domain="analytics",
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "sales_7d" | "units_sold_7d":
                return self._sales_window_metric(
                    metric_code,
                    catalog=catalog,
                    stock=source_data["stock_latest"],
                    sku=source_data["sku_7d"],
                    days=7,
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "sales_30d":
                return self._sales_window_metric(
                    metric_code,
                    catalog=catalog,
                    stock=source_data["stock_latest"],
                    sku=source_data["sku_30d"],
                    days=30,
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case "unit_profit_after_ads":
                return self._unit_profit_metric(
                    metric_code,
                    catalog=catalog,
                    sku=source_data["sku_30d"],
                    date_from=date_from,
                    date_to=date_to,
                    account_id=account_id,
                    nm_id=nm_id,
                )
            case _:
                return self._missing_value(
                    metric_code,
                    value_type=catalog.value_type,
                    unit=catalog.unit,
                    trust_state=catalog.trust_state,
                    reason="metric_registered_but_not_resolvable",
                    evidence=self._evidence(
                        catalog=catalog,
                        source_table=(catalog.source_tables_json or [None])[0],
                        date_from=date_from,
                        date_to=date_to,
                        account_id=account_id,
                        nm_id=nm_id,
                        row_count=0,
                    ),
                )

    def _average_sales_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        stock: dict[str, Any],
        sku: dict[str, Any],
        days: int,
        sync_domain: str,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        sales_value = self._decimal_or_none(stock.get(f"sales_{days}d"))
        source = stock
        source_table = "mart_stock_daily"
        if sales_value is None and sku.get("row_count"):
            sales_value = self._decimal_or_none(sku.get("net_qty"))
            source = sku
            source_table = "mart_sku_daily"
        value = sales_value / Decimal(str(days)) if sales_value is not None else None
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=source,
            source_table=source_table,
            sync_domain=sync_domain,
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _average_revenue_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        sku: dict[str, Any],
        days: int,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        revenue_value = self._decimal_or_none(sku.get("revenue"))
        value = (
            revenue_value / Decimal(str(days)) if revenue_value is not None else None
        )
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=sku,
            source_table="mart_sku_daily",
            sync_domain="finance",
            count_field="revenue_count",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _sales_window_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        stock: dict[str, Any],
        sku: dict[str, Any],
        days: int,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        value = self._decimal_or_none(stock.get(f"sales_{days}d"))
        source = stock
        source_table = "mart_stock_daily"
        if value is None and sku.get("row_count"):
            value = self._decimal_or_none(sku.get("sales_qty"))
            source = sku
            source_table = "mart_sku_daily"
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=source,
            source_table=source_table,
            sync_domain="finance",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _sku_sum_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        sku: dict[str, Any],
        field: str,
        count_field: str,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=sku.get(field),
            source_data=sku,
            source_table="mart_sku_daily",
            sync_domain="finance",
            count_field=count_field,
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _per_unit_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        sku: dict[str, Any],
        amount_field: str,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        amount = self._decimal_or_none(sku.get(amount_field))
        net_qty = self._decimal_or_none(sku.get("net_qty"))
        value = (
            None
            if amount is None or net_qty is None or net_qty <= 0
            else amount / net_qty
        )
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=sku,
            source_table="mart_sku_daily",
            sync_domain="finance",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _cost_price_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        source_data: dict[str, Any],
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        cost_row = source_data["manual_cost"].get("latest_row")
        if cost_row is not None:
            return self._from_source(
                metric_code,
                catalog=catalog,
                value=cost_row.cost_price,
                source_data=source_data["manual_cost"],
                source_table="manual_costs",
                sync_domain="manual_costs",
                date_from=date_from,
                date_to=date_to,
                account_id=account_id,
                nm_id=nm_id,
            )
        sku_row = source_data["sku_30d"].get("latest_row")
        sku_cost = (
            getattr(sku_row, "cost_price", None)
            if sku_row is not None and getattr(sku_row, "has_manual_cost", False)
            else None
        )
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=sku_cost,
            source_data=source_data["sku_30d"],
            source_table="mart_sku_daily",
            sync_domain="finance",
            count_field="cost_price_count",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _unit_profit_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        sku: dict[str, Any],
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        profit = self._decimal_or_none(sku.get("estimated_profit_after_ads"))
        net_qty = self._decimal_or_none(sku.get("net_qty"))
        has_profit_source = int(sku.get("estimated_profit_after_ads_count") or 0) > 0
        has_cost_source = int(sku.get("cost_price_count") or 0) > 0
        value = (
            None
            if profit is None
            or net_qty is None
            or net_qty <= 0
            or not has_profit_source
            or not has_cost_source
            else profit / net_qty
        )
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=sku,
            source_table="mart_sku_daily",
            sync_domain="finance",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _return_rate_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        sku: dict[str, Any],
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        returns = self._decimal_or_none(sku.get("return_qty"))
        sales = self._decimal_or_none(sku.get("sales_qty"))
        value = (
            None
            if returns is None or sales is None or sales <= 0
            else (returns / sales) * Decimal("100")
        )
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=sku,
            source_table="mart_sku_daily",
            sync_domain="finance",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _conversion_rate_metric(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        funnel: dict[str, Any],
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
    ) -> ResolvedMetricValue:
        views = self._decimal_or_none(funnel.get("views"))
        orders = self._decimal_or_none(funnel.get("orders"))
        value = (
            None
            if views is None or orders is None or views <= 0
            else (orders / views) * Decimal("100")
        )
        return self._from_source(
            metric_code,
            catalog=catalog,
            value=value,
            source_data=funnel,
            source_table="wb_card_funnel_daily",
            sync_domain="analytics",
            date_from=date_from,
            date_to=date_to,
            account_id=account_id,
            nm_id=nm_id,
        )

    def _from_source(
        self,
        metric_code: str,
        *,
        catalog: MetricCatalog,
        value: Any,
        source_data: dict[str, Any],
        source_table: str,
        sync_domain: str,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
        count_field: str = "row_count",
    ) -> ResolvedMetricValue:
        row_count = int(source_data.get("row_count") or 0)
        evidence = self._evidence(
            catalog=catalog,
            source_table=source_table,
            date_from=source_data.get("window_start") or date_from,
            date_to=source_data.get("window_end") or date_to,
            account_id=account_id,
            nm_id=nm_id,
            row_count=row_count,
            latest_source_date=source_data.get("latest_date"),
            latest_updated_at=source_data.get("latest_updated_at"),
            sync_domain=sync_domain,
            freshness=source_data.get("freshness"),
        )
        if (
            value is None
            or row_count == 0
            or int(source_data.get(count_field) or row_count) == 0
        ):
            return self._missing_value(
                metric_code,
                value_type=catalog.value_type,
                unit=catalog.unit,
                trust_state=catalog.trust_state,
                reason="source_data_missing",
                evidence=evidence,
            )
        return ResolvedMetricValue(
            metric_code=metric_code,
            value=value,
            value_type=catalog.value_type,
            unit=catalog.unit,
            trust_state=catalog.trust_state,
            is_missing=False,
            evidence=evidence,
        )

    def _missing_value(
        self,
        metric_code: str,
        *,
        value_type: str | None,
        unit: str | None,
        trust_state: str | None,
        reason: str,
        evidence: MetricSourceReference,
    ) -> ResolvedMetricValue:
        return ResolvedMetricValue(
            metric_code=metric_code,
            value=None,
            value_type=value_type,
            unit=unit,
            trust_state=trust_state,
            is_missing=True,
            missing_reason=reason,
            evidence=evidence,
        )

    def _evidence(
        self,
        *,
        catalog: MetricCatalog,
        source_table: str | None,
        date_from: date,
        date_to: date,
        account_id: int,
        nm_id: int,
        row_count: int | None,
        latest_source_date: date | None = None,
        latest_updated_at: Any = None,
        sync_domain: str | None = None,
        freshness: dict[str, Any] | None = None,
    ) -> MetricSourceReference:
        freshness_payload: dict[str, Any] = {}
        if latest_source_date is not None:
            freshness_payload["latest_source_date"] = latest_source_date
        if latest_updated_at is not None:
            freshness_payload["latest_updated_at"] = latest_updated_at
        if sync_domain is not None:
            freshness_payload["sync_domain"] = sync_domain
            domain_freshness = (freshness or {}).get("domains", {}).get(sync_domain)
            if domain_freshness is not None:
                freshness_payload["sync_cursor"] = domain_freshness
        return MetricSourceReference(
            source_module=catalog.source_module,
            source_table=source_table,
            source_endpoint=(catalog.source_endpoints_json or [None])[0],
            source_service="ProductMetricResolver",
            date_from=date_from,
            date_to=date_to,
            row_count=row_count,
            freshness=freshness_payload,
            filters={"account_id": account_id, "nm_id": nm_id},
        )

    @staticmethod
    def _window_start(*, date_from: date, date_to: date, days: int) -> date:
        suffix_start = date_to.toordinal() - days + 1
        return max(date_from, date.fromordinal(suffix_start))

    @staticmethod
    def _decimal_or_none(value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))

    @classmethod
    def _price_from_goods_payload(cls, payload: Any) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        sizes = payload.get("sizes")
        if not isinstance(sizes, list):
            return None

        price_candidates: list[Decimal] = []
        discounted_candidates: list[Decimal] = []
        for size in sizes:
            if not isinstance(size, dict):
                continue
            price = cls._decimal_or_none(size.get("price"))
            discounted_raw = (
                size.get("discountedPrice")
                if size.get("discountedPrice") is not None
                else size.get("discounted_price")
            )
            discounted_price = cls._decimal_or_none(discounted_raw)
            if price is not None:
                price_candidates.append(price)
            if discounted_price is not None:
                discounted_candidates.append(discounted_price)

        if not price_candidates and not discounted_candidates:
            return None
        return {
            "row_count": len([size for size in sizes if isinstance(size, dict)]),
            "price_current": min(price_candidates) if price_candidates else None,
            "price_after_discount": min(discounted_candidates)
            if discounted_candidates
            else None,
        }
