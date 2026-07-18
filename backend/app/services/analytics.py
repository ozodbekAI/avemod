from __future__ import annotations

import csv
import io
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLMemoryCache
from app.core.time import utcnow
from app.models.ads import WBAdStatsDaily
from app.models.analytics import WBCardFunnelDaily, WBHiddenProduct, WBRegionSalesDaily
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.prices import WBPrice, WBPriceQuarantine, WBPriceSize
from app.models.product_cards import WBProductCard
from app.repositories.analytics import CardFunnelRepository, RegionSalesRepository
from app.schemas.analytics import (
    AnalyticsAdSummary,
    AnalyticsApiCapability,
    AnalyticsComparisonMetric,
    AnalyticsDataSourceStatus,
    AnalyticsMoneySummary,
    AnalyticsOverviewRead,
    AnalyticsPeriod,
    AnalyticsPriceSummary,
    AnalyticsProductRow,
    AnalyticsRecommendation,
    AnalyticsRegionRow,
    AnalyticsStockSummary,
    AnalyticsSummary,
    AnalyticsTrendPoint,
)


class AnalyticsService:
    def __init__(self) -> None:
        self.funnel = CardFunnelRepository()
        self.regions = RegionSalesRepository()
        self._overview_cache: TTLMemoryCache[AnalyticsOverviewRead] = TTLMemoryCache(
            default_ttl_seconds=60
        )

    def clear_runtime_caches(self) -> None:
        self._overview_cache.clear()

    async def list_funnel(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        vendor_code: str | None = None,
        brand_name: str | None = None,
        subject_name: str | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.funnel.list_filtered(
            session,
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    async def list_regions(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        vendor_code: str | None = None,
        region_name: str | None = None,
        country_name: str | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.regions.list_filtered(
            session,
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            region_name=region_name,
            country_name=country_name,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    async def overview(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        brand_name: str | None = None,
        subject_name: str | None = None,
        region_name: str | None = None,
        country_name: str | None = None,
        search: str | None = None,
        product_limit: int = 20,
        region_limit: int = 15,
    ) -> AnalyticsOverviewRead:
        start, end = self._resolve_period(date_from, date_to)
        previous_start, previous_end = self._previous_period(start, end)
        geo_filtered = bool(region_name or country_name)
        cache_key = (
            "analytics_overview",
            int(account_id),
            start.isoformat(),
            end.isoformat(),
            nm_id,
            vendor_code,
            brand_name,
            subject_name,
            region_name,
            country_name,
            search,
            int(product_limit),
            int(region_limit),
        )
        cached = self._overview_cache.get(cache_key)
        if cached is not None:
            return cached.model_copy(deep=True)

        current_funnel = await self._aggregate_funnel(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        previous_funnel = await self._aggregate_funnel(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        current_regions = await self._aggregate_regions(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            region_name=region_name,
            country_name=country_name,
            search=search,
        )
        previous_regions = await self._aggregate_regions(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            region_name=region_name,
            country_name=country_name,
            search=search,
        )
        current_money = await self._aggregate_money(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        previous_money = await self._aggregate_money(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        current_ads = await self._aggregate_ads(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        previous_ads = await self._aggregate_ads(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        current_money = self._apply_real_ad_adjustment(current_money, current_ads)
        previous_money = self._apply_real_ad_adjustment(previous_money, previous_ads)
        stock = await self._stock_summary(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        prices = await self._price_summary(
            session,
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            search=search,
        )
        hidden_counts = await self._hidden_counts(session, account_id=account_id)
        trend = await self._trend(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            region_name=region_name,
            country_name=country_name,
            search=search,
            geo_filtered=geo_filtered,
        )
        products = await self._top_products(
            session,
            account_id=account_id,
            start=start,
            end=end,
            previous_start=previous_start,
            previous_end=previous_end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            region_name=region_name,
            country_name=country_name,
            search=search,
            limit=product_limit,
            geo_filtered=geo_filtered,
        )
        regions = await self._top_regions(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            region_name=region_name,
            country_name=country_name,
            search=search,
            limit=region_limit,
        )
        summary = self._summary(
            current_funnel=current_funnel,
            previous_funnel=previous_funnel,
            current_regions=current_regions,
            previous_regions=previous_regions,
            current_money=current_money,
            previous_money=previous_money,
            geo_filtered=geo_filtered,
            hidden_counts=hidden_counts,
        )
        data_sources = await self._data_sources(
            session,
            account_id=account_id,
            start=start,
            end=end,
        )
        money_summary = (
            self._regional_money_summary(current_regions, previous_regions)
            if geo_filtered
            else self._money_summary(current_money, previous_money)
        )
        ads_summary = (
            AnalyticsAdSummary()
            if geo_filtered
            else self._ads_summary(current_ads, previous_ads)
        )
        stock_summary = AnalyticsStockSummary() if geo_filtered else stock
        price_summary = AnalyticsPriceSummary() if geo_filtered else prices

        result = AnalyticsOverviewRead(
            account_id=account_id,
            period=AnalyticsPeriod(
                date_from=start,
                date_to=end,
                previous_date_from=previous_start,
                previous_date_to=previous_end,
            ),
            summary=summary,
            money=money_summary,
            ads=ads_summary,
            stock=stock_summary,
            prices=price_summary,
            trend=trend,
            products=products,
            regions=regions,
            data_sources=data_sources,
            api_capabilities=self._api_capabilities(),
            recommendations=self._recommendations(
                summary, products, regions, stock_summary, price_summary
            ),
            export_datasets=["products", "regions", "trend"],
        )
        self._overview_cache.set(cache_key, result.model_copy(deep=True))
        return result

    async def export_csv(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        dataset: str,
        date_from: date | None = None,
        date_to: date | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        brand_name: str | None = None,
        subject_name: str | None = None,
        region_name: str | None = None,
        country_name: str | None = None,
        search: str | None = None,
    ) -> str:
        overview = await self.overview(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            region_name=region_name,
            country_name=country_name,
            search=search,
            product_limit=500,
            region_limit=500,
        )
        output = io.StringIO()
        if dataset == "products":
            fieldnames = [
                "nm_id",
                "vendor_code",
                "title",
                "brand_name",
                "subject_name",
                "open_count",
                "cart_count",
                "order_count",
                "buyout_count",
                "cancel_count",
                "revenue",
                "units_sold",
                "for_pay",
                "profit",
                "margin_percent",
                "wb_expenses",
                "ad_spend",
                "drr_percent",
                "stock_qty",
                "days_of_stock",
                "current_price",
                "current_discounted_price",
                "return_count",
                "return_rate",
                "cart_rate",
                "order_rate",
                "buyout_rate",
                "status",
                "issue",
                "action",
            ]
            writer = csv.DictWriter(
                output, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            for row in overview.products:
                writer.writerow(row.model_dump())
        elif dataset == "regions":
            fieldnames = [
                "country_name",
                "region_name",
                "city_name",
                "federal_district",
                "revenue",
                "units_sold",
                "cards_count",
                "share_percent",
            ]
            writer = csv.DictWriter(
                output, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            for row in overview.regions:
                writer.writerow(row.model_dump())
        else:
            fieldnames = [
                "date",
                "open_count",
                "cart_count",
                "order_count",
                "buyout_count",
                "cancel_count",
                "revenue",
                "units_sold",
                "for_pay",
                "profit",
                "ad_spend",
                "stock_qty",
                "cart_rate",
                "order_rate",
                "buyout_rate",
            ]
            writer = csv.DictWriter(
                output, fieldnames=fieldnames, extrasaction="ignore"
            )
            writer.writeheader()
            for row in overview.trend:
                data = row.model_dump()
                data["date"] = row.date.isoformat()
                writer.writerow(data)
        return output.getvalue()

    @staticmethod
    def _resolve_period(
        date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        end = date_to or utcnow().date()
        start = date_from or (end - timedelta(days=29))
        if start > end:
            start, end = end, start
        return start, end

    @staticmethod
    def _previous_period(start: date, end: date) -> tuple[date, date]:
        days = (end - start).days + 1
        previous_end = start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=days - 1)
        return previous_start, previous_end

    @staticmethod
    def _to_float(value: Any) -> float:
        if value is None:
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        return float(value)

    @staticmethod
    def _pct(
        numerator: float | int | None, denominator: float | int | None
    ) -> float | None:
        den = float(denominator or 0)
        if den <= 0:
            return None
        return round(float(numerator or 0) / den * 100, 2)

    @staticmethod
    def _metric(
        value: float | int | None, previous_value: float | int | None
    ) -> AnalyticsComparisonMetric:
        current = None if value is None else float(value)
        previous = None if previous_value is None else float(previous_value)
        delta = None if current is None or previous is None else current - previous
        delta_percent = None
        if delta is not None and previous not in (None, 0):
            delta_percent = round(delta / previous * 100, 2)
        return AnalyticsComparisonMetric(
            value=current,
            previous_value=previous,
            delta=delta,
            delta_percent=delta_percent,
        )

    @staticmethod
    def _funnel_filters(
        *,
        account_id: int,
        start: date,
        end: date,
        nm_id: int | None,
        vendor_code: str | None,
        brand_name: str | None,
        subject_name: str | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = [
            WBCardFunnelDaily.account_id == account_id,
            WBCardFunnelDaily.stat_date >= start,
            WBCardFunnelDaily.stat_date <= end,
        ]
        if nm_id is not None:
            filters.append(WBCardFunnelDaily.nm_id == nm_id)
        if vendor_code:
            filters.append(WBCardFunnelDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if brand_name:
            filters.append(WBCardFunnelDaily.brand_name.ilike(f"%{brand_name}%"))
        if subject_name:
            filters.append(WBCardFunnelDaily.subject_name.ilike(f"%{subject_name}%"))
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    WBCardFunnelDaily.vendor_code.ilike(pattern),
                    WBCardFunnelDaily.title.ilike(pattern),
                    WBCardFunnelDaily.brand_name.ilike(pattern),
                    WBCardFunnelDaily.subject_name.ilike(pattern),
                )
            )
        return filters

    @staticmethod
    def _region_filters(
        *,
        account_id: int,
        start: date,
        end: date,
        nm_id: int | None,
        vendor_code: str | None,
        region_name: str | None,
        country_name: str | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = [
            WBRegionSalesDaily.account_id == account_id,
            WBRegionSalesDaily.stat_date >= start,
            WBRegionSalesDaily.stat_date <= end,
        ]
        if nm_id is not None:
            filters.append(WBRegionSalesDaily.nm_id == nm_id)
        if vendor_code:
            filters.append(WBRegionSalesDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if region_name:
            filters.append(WBRegionSalesDaily.region_name.ilike(f"%{region_name}%"))
        if country_name:
            filters.append(WBRegionSalesDaily.country_name.ilike(f"%{country_name}%"))
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    WBRegionSalesDaily.vendor_code.ilike(pattern),
                    WBRegionSalesDaily.region_name.ilike(pattern),
                    WBRegionSalesDaily.country_name.ilike(pattern),
                    WBRegionSalesDaily.city_name.ilike(pattern),
                )
            )
        return filters

    @staticmethod
    def _mart_filters(
        *,
        account_id: int,
        start: date,
        end: date,
        nm_id: int | None,
        vendor_code: str | None,
        brand_name: str | None,
        subject_name: str | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = [
            MartSKUDaily.account_id == account_id,
            MartSKUDaily.stat_date >= start,
            MartSKUDaily.stat_date <= end,
        ]
        if nm_id is not None:
            filters.append(MartSKUDaily.nm_id == nm_id)
        if vendor_code:
            filters.append(MartSKUDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if brand_name:
            filters.append(MartSKUDaily.brand.ilike(f"%{brand_name}%"))
        if subject_name:
            filters.append(MartSKUDaily.subject_name.ilike(f"%{subject_name}%"))
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    MartSKUDaily.vendor_code.ilike(pattern),
                    MartSKUDaily.title.ilike(pattern),
                    MartSKUDaily.brand.ilike(pattern),
                    MartSKUDaily.subject_name.ilike(pattern),
                )
            )
        return filters

    @staticmethod
    def _price_filters(
        *,
        account_id: int,
        nm_id: int | None,
        vendor_code: str | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = [WBPrice.account_id == account_id]
        if nm_id is not None:
            filters.append(WBPrice.nm_id == nm_id)
        if vendor_code:
            filters.append(WBPrice.vendor_code.ilike(f"%{vendor_code}%"))
        if search:
            pattern = f"%{search}%"
            filters.append(WBPrice.vendor_code.ilike(pattern))
        return filters

    @staticmethod
    def _stock_filters(
        *,
        account_id: int,
        stock_date: date,
        nm_id: int | None,
        vendor_code: str | None,
        brand_name: str | None,
        subject_name: str | None,
        search: str | None,
    ) -> list[Any]:
        filters: list[Any] = [
            MartStockDaily.account_id == account_id,
            MartStockDaily.stat_date == stock_date,
        ]
        if nm_id is not None:
            filters.append(MartStockDaily.nm_id == nm_id)
        if vendor_code:
            filters.append(MartStockDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if brand_name:
            filters.append(
                MartStockDaily.payload["brand"].as_string().ilike(f"%{brand_name}%")
            )
        if subject_name:
            filters.append(
                MartStockDaily.payload["subject"].as_string().ilike(f"%{subject_name}%")
            )
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    MartStockDaily.vendor_code.ilike(pattern),
                    MartStockDaily.warehouse_name.ilike(pattern),
                    MartStockDaily.payload["brand"].as_string().ilike(pattern),
                    MartStockDaily.payload["subject"].as_string().ilike(pattern),
                )
            )
        return filters

    async def _aggregate_funnel(
        self, session: AsyncSession, **kwargs: Any
    ) -> dict[str, float]:
        stmt = select(
            func.coalesce(func.sum(WBCardFunnelDaily.open_count), 0).label(
                "open_count"
            ),
            func.coalesce(func.sum(WBCardFunnelDaily.cart_count), 0).label(
                "cart_count"
            ),
            func.coalesce(func.sum(WBCardFunnelDaily.order_count), 0).label(
                "order_count"
            ),
            func.coalesce(func.sum(WBCardFunnelDaily.buyout_count), 0).label(
                "buyout_count"
            ),
            func.coalesce(func.sum(WBCardFunnelDaily.cancel_count), 0).label(
                "cancel_count"
            ),
            func.count(func.distinct(WBCardFunnelDaily.nm_id)).label("active_cards"),
            func.count(WBCardFunnelDaily.id).label("rows_count"),
        ).where(*self._funnel_filters(**kwargs))
        row = (await session.execute(stmt)).mappings().one()
        return {key: self._to_float(value) for key, value in row.items()}

    async def _aggregate_regions(
        self, session: AsyncSession, **kwargs: Any
    ) -> dict[str, float]:
        stmt = select(
            func.coalesce(func.sum(WBRegionSalesDaily.sale_amount), 0).label("revenue"),
            func.coalesce(func.sum(WBRegionSalesDaily.sale_quantity), 0).label(
                "units_sold"
            ),
            func.count(func.distinct(WBRegionSalesDaily.nm_id)).label("region_cards"),
            func.count(WBRegionSalesDaily.id).label("rows_count"),
        ).where(*self._region_filters(**kwargs))
        row = (await session.execute(stmt)).mappings().one()
        return {key: self._to_float(value) for key, value in row.items()}

    async def _aggregate_money(
        self, session: AsyncSession, **kwargs: Any
    ) -> dict[str, float]:
        stmt = select(
            func.coalesce(func.sum(MartSKUDaily.final_revenue), 0).label("revenue"),
            func.coalesce(func.sum(MartSKUDaily.final_for_pay), 0).label("for_pay"),
            func.coalesce(
                func.sum(MartSKUDaily.net_profit_after_all_expenses), 0
            ).label("profit"),
            func.coalesce(func.sum(MartSKUDaily.total_wb_expenses), 0).label(
                "wb_expenses"
            ),
            func.coalesce(func.sum(MartSKUDaily.total_seller_expenses), 0).label(
                "seller_expenses"
            ),
            func.coalesce(func.sum(MartSKUDaily.estimated_cogs), 0).label("cost_price"),
            func.coalesce(func.sum(MartSKUDaily.ordered_units), 0).label("orders"),
            func.coalesce(func.sum(MartSKUDaily.final_sales_qty), 0).label(
                "units_sold"
            ),
            func.coalesce(func.sum(MartSKUDaily.final_return_qty), 0).label("returns"),
            func.coalesce(func.sum(MartSKUDaily.ad_spend), 0).label("ad_spend"),
            func.count(MartSKUDaily.id).label("rows_count"),
        ).where(*self._mart_filters(**kwargs))
        row = (await session.execute(stmt)).mappings().one()
        result = {key: self._to_float(value) for key, value in row.items()}
        result["margin_percent"] = self._pct(
            result.get("profit"), result.get("revenue")
        )
        result["return_rate"] = self._pct(
            result.get("returns"), result.get("units_sold")
        )
        return result

    async def _aggregate_ads(
        self, session: AsyncSession, **kwargs: Any
    ) -> dict[str, float]:
        nm_ids = await self._ad_nm_ids_for_filters(session, **kwargs)
        filters: list[Any] = [
            WBAdStatsDaily.account_id == kwargs["account_id"],
            WBAdStatsDaily.stat_date >= kwargs["start"],
            WBAdStatsDaily.stat_date <= kwargs["end"],
        ]
        if nm_ids is not None:
            if not nm_ids:
                return {
                    "spend": 0,
                    "views": 0,
                    "clicks": 0,
                    "orders": 0,
                    "revenue": 0,
                    "ctr": None,
                    "cpc": None,
                    "drr_percent": None,
                    "roas": None,
                    "rows_count": 0,
                }
            filters.append(WBAdStatsDaily.nm_id.in_(nm_ids))
        stmt = select(
            func.coalesce(func.sum(WBAdStatsDaily.sum), 0).label("spend"),
            func.coalesce(func.sum(WBAdStatsDaily.views), 0).label("views"),
            func.coalesce(func.sum(WBAdStatsDaily.clicks), 0).label("clicks"),
            func.coalesce(func.sum(WBAdStatsDaily.orders), 0).label("orders"),
            func.coalesce(func.sum(WBAdStatsDaily.sum_price), 0).label("revenue"),
            func.count(WBAdStatsDaily.id).label("rows_count"),
        ).where(*filters)
        row = (await session.execute(stmt)).mappings().one()
        result = {key: self._to_float(value) for key, value in row.items()}
        result["ctr"] = self._pct(result.get("clicks"), result.get("views"))
        result["cpc"] = (
            round(result["spend"] / result["clicks"], 2)
            if result.get("clicks", 0) > 0
            else None
        )
        result["drr_percent"] = self._pct(result.get("spend"), result.get("revenue"))
        result["roas"] = (
            round(result["revenue"] / result["spend"], 2)
            if result.get("spend", 0) > 0
            else None
        )
        return result

    async def _ad_nm_ids_for_filters(
        self, session: AsyncSession, **kwargs: Any
    ) -> list[int] | None:
        if kwargs.get("nm_id") is not None:
            return [int(kwargs["nm_id"])]
        if not any(
            kwargs.get(key)
            for key in ("vendor_code", "brand_name", "subject_name", "search")
        ):
            return None
        stmt = (
            select(MartSKUDaily.nm_id)
            .where(*self._mart_filters(**kwargs), MartSKUDaily.nm_id.is_not(None))
            .distinct()
        )
        return [
            int(item)
            for item in (await session.execute(stmt)).scalars()
            if item is not None
        ]

    @staticmethod
    def _apply_real_ad_adjustment(
        money: dict[str, float], ads: dict[str, float]
    ) -> dict[str, float]:
        adjusted = dict(money)
        missing_ad_spend = max(
            float(ads.get("spend") or 0) - float(money.get("ad_spend") or 0), 0
        )
        if missing_ad_spend > 0:
            adjusted["profit"] = float(adjusted.get("profit") or 0) - missing_ad_spend
            adjusted["ad_spend"] = float(ads.get("spend") or 0)
            adjusted["margin_percent"] = AnalyticsService._pct(
                adjusted.get("profit"), adjusted.get("revenue")
            )
        return adjusted

    async def _latest_stock_date(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
    ) -> date | None:
        stmt = select(func.max(MartStockDaily.stat_date)).where(
            MartStockDaily.account_id == account_id,
            MartStockDaily.stat_date >= start,
            MartStockDaily.stat_date <= end,
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _stock_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_id: int | None,
        vendor_code: str | None,
        brand_name: str | None,
        subject_name: str | None,
        search: str | None,
    ) -> AnalyticsStockSummary:
        stock_date = await self._latest_stock_date(
            session, account_id=account_id, start=start, end=end
        )
        if stock_date is None:
            return AnalyticsStockSummary()
        filters = self._stock_filters(
            account_id=account_id,
            stock_date=stock_date,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        stmt = select(
            func.coalesce(func.sum(MartStockDaily.quantity), 0).label("stock_qty"),
            func.coalesce(func.sum(MartStockDaily.quantity_full), 0).label(
                "full_stock_qty"
            ),
            func.coalesce(func.sum(MartStockDaily.in_way_to_client), 0).label(
                "in_way_to_client"
            ),
            func.coalesce(func.sum(MartStockDaily.in_way_from_client), 0).label(
                "in_way_from_client"
            ),
            func.count(
                func.distinct(
                    case(
                        (
                            MartStockDaily.is_out_of_stock_risk.is_(True),
                            MartStockDaily.nm_id,
                        )
                    )
                )
            ).label("out_of_stock_risk"),
            func.count(
                func.distinct(
                    case((MartStockDaily.is_dead_stock.is_(True), MartStockDaily.nm_id))
                )
            ).label("dead_stock"),
            func.avg(MartStockDaily.days_of_stock).label("avg_days_of_stock"),
            func.count(MartStockDaily.id).label("rows_count"),
        ).where(*filters)
        row = (await session.execute(stmt)).mappings().one()
        return AnalyticsStockSummary(
            stock_qty=self._to_float(row["stock_qty"]),
            full_stock_qty=self._to_float(row["full_stock_qty"]),
            in_way_to_client=self._to_float(row["in_way_to_client"]),
            in_way_from_client=self._to_float(row["in_way_from_client"]),
            out_of_stock_risk=int(row["out_of_stock_risk"] or 0),
            dead_stock=int(row["dead_stock"] or 0),
            avg_days_of_stock=None
            if row["avg_days_of_stock"] is None
            else round(self._to_float(row["avg_days_of_stock"]), 1),
            latest_date=stock_date,
            rows_count=int(row["rows_count"] or 0),
        )

    async def _price_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None,
        vendor_code: str | None,
        search: str | None,
    ) -> AnalyticsPriceSummary:
        price_filters = self._price_filters(
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            search=search,
        )
        goods_stmt = select(
            func.count(WBPrice.id).label("goods_count"),
            func.count(case((WBPrice.is_bad_turnover.is_(True), 1))).label(
                "bad_turnover"
            ),
        ).where(*price_filters)
        sizes_filters = [WBPriceSize.account_id == account_id]
        quarantine_filters = [WBPriceQuarantine.account_id == account_id]
        if nm_id is not None:
            sizes_filters.append(WBPriceSize.nm_id == nm_id)
            quarantine_filters.append(WBPriceQuarantine.nm_id == nm_id)
        if vendor_code:
            sizes_filters.append(WBPriceSize.vendor_code.ilike(f"%{vendor_code}%"))
            quarantine_filters.append(
                WBPriceQuarantine.vendor_code.ilike(f"%{vendor_code}%")
            )
        if search:
            pattern = f"%{search}%"
            sizes_filters.append(WBPriceSize.vendor_code.ilike(pattern))
            quarantine_filters.append(WBPriceQuarantine.vendor_code.ilike(pattern))
        sizes_stmt = select(
            func.avg(WBPriceSize.price).label("avg_price"),
            func.avg(WBPriceSize.discounted_price).label("avg_discounted_price"),
            func.avg(WBPriceSize.discount).label("avg_discount_percent"),
            func.count(WBPriceSize.id).label("size_count"),
        ).where(*sizes_filters)
        quarantine_stmt = select(func.count(WBPriceQuarantine.id)).where(
            *quarantine_filters
        )
        goods = (await session.execute(goods_stmt)).mappings().one()
        sizes = (await session.execute(sizes_stmt)).mappings().one()
        quarantine = int((await session.execute(quarantine_stmt)).scalar_one() or 0)
        return AnalyticsPriceSummary(
            avg_price=None
            if sizes["avg_price"] is None
            else round(self._to_float(sizes["avg_price"]), 2),
            avg_discounted_price=None
            if sizes["avg_discounted_price"] is None
            else round(self._to_float(sizes["avg_discounted_price"]), 2),
            avg_discount_percent=None
            if sizes["avg_discount_percent"] is None
            else round(self._to_float(sizes["avg_discount_percent"]), 1),
            bad_turnover=int(goods["bad_turnover"] or 0),
            quarantine=quarantine,
            goods_count=int(goods["goods_count"] or 0),
            size_count=int(sizes["size_count"] or 0),
        )

    async def _hidden_counts(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, int]:
        stmt = (
            select(WBHiddenProduct.hidden_type, func.count(WBHiddenProduct.id))
            .where(WBHiddenProduct.account_id == account_id)
            .group_by(WBHiddenProduct.hidden_type)
        )
        rows = (await session.execute(stmt)).all()
        return {str(hidden_type): int(count) for hidden_type, count in rows}

    async def _trend(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_id: int | None,
        vendor_code: str | None,
        brand_name: str | None,
        subject_name: str | None,
        region_name: str | None,
        country_name: str | None,
        search: str | None,
        geo_filtered: bool,
    ) -> list[AnalyticsTrendPoint]:
        funnel_stmt = (
            select(
                WBCardFunnelDaily.stat_date.label("date"),
                func.coalesce(func.sum(WBCardFunnelDaily.open_count), 0).label(
                    "open_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.cart_count), 0).label(
                    "cart_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.order_count), 0).label(
                    "order_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.buyout_count), 0).label(
                    "buyout_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.cancel_count), 0).label(
                    "cancel_count"
                ),
            )
            .where(
                *self._funnel_filters(
                    account_id=account_id,
                    start=start,
                    end=end,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    brand_name=brand_name,
                    subject_name=subject_name,
                    search=search,
                )
            )
            .group_by(WBCardFunnelDaily.stat_date)
        )
        region_stmt = (
            select(
                WBRegionSalesDaily.stat_date.label("date"),
                func.coalesce(func.sum(WBRegionSalesDaily.sale_amount), 0).label(
                    "revenue"
                ),
                func.coalesce(func.sum(WBRegionSalesDaily.sale_quantity), 0).label(
                    "units_sold"
                ),
            )
            .where(
                *self._region_filters(
                    account_id=account_id,
                    start=start,
                    end=end,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    region_name=region_name,
                    country_name=country_name,
                    search=search,
                )
            )
            .group_by(WBRegionSalesDaily.stat_date)
        )
        mart_stmt = (
            select(
                MartSKUDaily.stat_date.label("date"),
                func.coalesce(func.sum(MartSKUDaily.final_revenue), 0).label("revenue"),
                func.coalesce(func.sum(MartSKUDaily.final_sales_qty), 0).label(
                    "units_sold"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_for_pay), 0).label("for_pay"),
                func.coalesce(
                    func.sum(MartSKUDaily.net_profit_after_all_expenses), 0
                ).label("profit"),
                func.coalesce(func.sum(MartSKUDaily.ad_spend), 0).label("ad_spend"),
                func.coalesce(func.sum(MartSKUDaily.closing_stock_qty), 0).label(
                    "stock_qty"
                ),
            )
            .where(
                *self._mart_filters(
                    account_id=account_id,
                    start=start,
                    end=end,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    brand_name=brand_name,
                    subject_name=subject_name,
                    search=search,
                )
            )
            .group_by(MartSKUDaily.stat_date)
        )
        ad_nm_ids = await self._ad_nm_ids_for_filters(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_id=nm_id,
            vendor_code=vendor_code,
            brand_name=brand_name,
            subject_name=subject_name,
            search=search,
        )
        ad_filters: list[Any] = [
            WBAdStatsDaily.account_id == account_id,
            WBAdStatsDaily.stat_date >= start,
            WBAdStatsDaily.stat_date <= end,
        ]
        if ad_nm_ids is not None:
            ad_filters.append(WBAdStatsDaily.nm_id.in_(ad_nm_ids or [-1]))
        ad_stmt = (
            select(
                WBAdStatsDaily.stat_date.label("date"),
                func.coalesce(func.sum(WBAdStatsDaily.sum), 0).label("ad_spend"),
            )
            .where(*ad_filters)
            .group_by(WBAdStatsDaily.stat_date)
        )
        by_date: dict[date, dict[str, float]] = {}
        if not geo_filtered:
            for row in (await session.execute(funnel_stmt)).mappings():
                day = row["date"]
                by_date.setdefault(day, {})
                by_date[day].update(
                    {
                        key: self._to_float(value)
                        for key, value in row.items()
                        if key != "date"
                    }
                )
        for row in (await session.execute(region_stmt)).mappings():
            day = row["date"]
            by_date.setdefault(day, {})
            by_date[day].update(
                {
                    key: self._to_float(value)
                    for key, value in row.items()
                    if key != "date"
                }
            )
        if not geo_filtered:
            for row in (await session.execute(mart_stmt)).mappings():
                day = row["date"]
                by_date.setdefault(day, {})
                by_date[day].update(
                    {
                        key: self._to_float(value)
                        for key, value in row.items()
                        if key != "date"
                    }
                )
            for row in (await session.execute(ad_stmt)).mappings():
                day = row["date"]
                by_date.setdefault(day, {})
                raw_ad_spend = self._to_float(row["ad_spend"])
                mart_ad_spend = self._to_float(by_date[day].get("ad_spend"))
                missing_ad_spend = max(raw_ad_spend - mart_ad_spend, 0)
                if missing_ad_spend:
                    by_date[day]["profit"] = (
                        self._to_float(by_date[day].get("profit")) - missing_ad_spend
                    )
                by_date[day]["ad_spend"] = raw_ad_spend

        result: list[AnalyticsTrendPoint] = []
        day = start
        while day <= end:
            item = by_date.get(day, {})
            open_count = item.get("open_count", 0)
            cart_count = item.get("cart_count", 0)
            order_count = item.get("order_count", 0)
            buyout_count = item.get("buyout_count", 0)
            result.append(
                AnalyticsTrendPoint(
                    date=day,
                    open_count=open_count,
                    cart_count=cart_count,
                    order_count=order_count,
                    buyout_count=buyout_count,
                    cancel_count=item.get("cancel_count", 0),
                    revenue=item.get("revenue", 0),
                    units_sold=item.get("units_sold", 0),
                    for_pay=item.get("for_pay", 0),
                    profit=item.get("profit", 0),
                    ad_spend=item.get("ad_spend", 0),
                    stock_qty=item.get("stock_qty", 0),
                    cart_rate=self._pct(cart_count, open_count),
                    order_rate=self._pct(order_count, cart_count),
                    buyout_rate=self._pct(buyout_count, order_count),
                )
            )
            day += timedelta(days=1)
        return result

    async def _top_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        previous_start: date,
        previous_end: date,
        nm_id: int | None,
        vendor_code: str | None,
        brand_name: str | None,
        subject_name: str | None,
        region_name: str | None,
        country_name: str | None,
        search: str | None,
        limit: int,
        geo_filtered: bool,
    ) -> list[AnalyticsProductRow]:
        open_sum = func.coalesce(func.sum(WBCardFunnelDaily.open_count), 0)
        order_sum = func.coalesce(func.sum(WBCardFunnelDaily.order_count), 0)
        funnel_stmt = (
            select(
                WBCardFunnelDaily.nm_id,
                func.max(WBCardFunnelDaily.vendor_code).label("vendor_code"),
                func.max(WBCardFunnelDaily.title).label("title"),
                func.max(WBCardFunnelDaily.brand_name).label("brand_name"),
                func.max(WBCardFunnelDaily.subject_name).label("subject_name"),
                open_sum.label("open_count"),
                func.coalesce(func.sum(WBCardFunnelDaily.cart_count), 0).label(
                    "cart_count"
                ),
                order_sum.label("order_count"),
                func.coalesce(func.sum(WBCardFunnelDaily.buyout_count), 0).label(
                    "buyout_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.cancel_count), 0).label(
                    "cancel_count"
                ),
            )
            .where(
                *self._funnel_filters(
                    account_id=account_id,
                    start=start,
                    end=end,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    brand_name=brand_name,
                    subject_name=subject_name,
                    search=search,
                )
            )
            .group_by(WBCardFunnelDaily.nm_id)
            .order_by(order_sum.desc(), open_sum.desc())
            .limit(limit)
        )
        mart_revenue_sum = func.coalesce(func.sum(MartSKUDaily.final_revenue), 0)
        mart_stmt = (
            select(
                MartSKUDaily.nm_id,
                func.max(MartSKUDaily.vendor_code).label("vendor_code"),
                func.max(MartSKUDaily.title).label("title"),
                func.max(MartSKUDaily.brand).label("brand_name"),
                func.max(MartSKUDaily.subject_name).label("subject_name"),
                mart_revenue_sum.label("revenue"),
            )
            .where(
                *self._mart_filters(
                    account_id=account_id,
                    start=start,
                    end=end,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    brand_name=brand_name,
                    subject_name=subject_name,
                    search=search,
                )
            )
            .group_by(MartSKUDaily.nm_id)
            .order_by(mart_revenue_sum.desc())
            .limit(limit)
        )
        funnel_rows = list((await session.execute(funnel_stmt)).mappings())
        mart_rows = list((await session.execute(mart_stmt)).mappings())

        combined: dict[int, dict[str, Any]] = {}
        for row in funnel_rows:
            if row["nm_id"] is None:
                continue
            nm = int(row["nm_id"])
            combined.setdefault(nm, {})
            combined[nm].update({key: row[key] for key in row.keys()})
            combined[nm]["row_source"] = "funnel"
        for row in mart_rows:
            if row["nm_id"] is None:
                continue
            nm = int(row["nm_id"])
            combined.setdefault(nm, {})
            for key in ("vendor_code", "title", "brand_name", "subject_name"):
                if not combined[nm].get(key):
                    combined[nm][key] = row[key]
            combined[nm].setdefault("row_source", "money")

        nm_ids = list(combined.keys())
        funnel_metrics = await self._product_funnel_map(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_ids=nm_ids,
        )
        for nm, metrics in funnel_metrics.items():
            row = combined.setdefault(nm, {"nm_id": nm})
            for key in ("vendor_code", "title", "brand_name", "subject_name"):
                if not row.get(key):
                    row[key] = metrics.get(key)
            for key in (
                "open_count",
                "cart_count",
                "order_count",
                "buyout_count",
                "cancel_count",
            ):
                row[key] = metrics.get(key, 0)
            row.setdefault("row_source", "funnel")

        previous = await self._product_previous_map(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_ids=nm_ids,
        )
        money = await self._product_money_map(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_ids=nm_ids,
        )
        previous_money = await self._product_money_map(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_ids=nm_ids,
        )
        product_ads = await self._product_ads_map(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_ids=nm_ids,
        )
        region_revenue = await self._product_revenue_map(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_ids=nm_ids,
            region_name=region_name,
            country_name=country_name,
        )
        previous_region_revenue = await self._product_revenue_map(
            session,
            account_id=account_id,
            start=previous_start,
            end=previous_end,
            nm_ids=nm_ids,
            region_name=region_name,
            country_name=country_name,
        )
        if geo_filtered:
            for region_nm in region_revenue:
                combined.setdefault(
                    region_nm, {"nm_id": region_nm, "row_source": "region"}
                )
            nm_ids = list(combined.keys())
        stock = await self._product_stock_map(
            session,
            account_id=account_id,
            start=start,
            end=end,
            nm_ids=nm_ids,
        )
        prices = await self._product_price_map(
            session,
            account_id=account_id,
            nm_ids=nm_ids,
        )

        result: list[AnalyticsProductRow] = []
        sorted_nm_ids = sorted(
            nm_ids,
            key=lambda item: (
                region_revenue.get(item, {}).get("revenue", 0)
                if geo_filtered
                else money.get(item, {}).get(
                    "revenue", region_revenue.get(item, {}).get("revenue", 0)
                ),
                self._to_float(combined.get(item, {}).get("order_count")),
                self._to_float(combined.get(item, {}).get("open_count")),
            ),
            reverse=True,
        )[:limit]
        for nm in sorted_nm_ids:
            row = combined.get(nm, {})
            open_count = self._to_float(row.get("open_count"))
            cart_count = self._to_float(row.get("cart_count"))
            order_count = self._to_float(row.get("order_count"))
            buyout_count = self._to_float(row.get("buyout_count"))
            if geo_filtered:
                open_count = 0
                cart_count = 0
                order_count = 0
                buyout_count = 0
            product_money = {} if geo_filtered else money.get(nm, {})
            previous_product_money = previous_money.get(nm, {})
            product_ad = {} if geo_filtered else product_ads.get(nm, {})
            if product_ad:
                missing_ad_spend = max(
                    product_ad.get("ad_spend", 0) - product_money.get("ad_spend", 0),
                    0,
                )
                if missing_ad_spend > 0:
                    product_money = dict(product_money)
                    product_money["profit"] = (
                        product_money.get("profit", 0) - missing_ad_spend
                    )
                    product_money["ad_spend"] = product_ad.get("ad_spend", 0)
                    product_money["drr_percent"] = self._pct(
                        product_money.get("ad_spend"),
                        product_money.get("revenue"),
                    )
                    product_money["margin_percent"] = self._pct(
                        product_money.get("profit"),
                        product_money.get("revenue"),
                    )
            product_revenue = (
                region_revenue.get(nm, {}).get("revenue", 0)
                if geo_filtered
                else product_money.get(
                    "revenue", region_revenue.get(nm, {}).get("revenue", 0)
                )
            )
            previous_revenue = (
                previous_region_revenue.get(nm, {}).get("revenue")
                if geo_filtered
                else previous_product_money.get(
                    "revenue",
                    previous_region_revenue.get(nm, {}).get("revenue"),
                )
            )
            prev = previous.get(nm, {})
            stock_row = stock.get(nm, {})
            price_row = prices.get(nm, {})
            status, issue, action = self._product_status(
                open_count=open_count,
                cart_count=cart_count,
                order_count=order_count,
                buyout_count=buyout_count,
                revenue=product_revenue,
                profit=product_money.get("profit", 0),
                stock_qty=stock_row.get("stock_qty", 0),
                ad_spend=product_money.get("ad_spend", 0),
            )
            result.append(
                AnalyticsProductRow(
                    nm_id=nm,
                    vendor_code=row.get("vendor_code"),
                    title=row.get("title"),
                    brand_name=row.get("brand_name"),
                    subject_name=row.get("subject_name"),
                    open_count=open_count,
                    cart_count=cart_count,
                    order_count=order_count,
                    buyout_count=buyout_count,
                    cancel_count=0
                    if geo_filtered
                    else self._to_float(row.get("cancel_count")),
                    revenue=product_revenue,
                    units_sold=(
                        region_revenue.get(nm, {}).get("units_sold", 0)
                        if geo_filtered
                        else product_money.get(
                            "units_sold",
                            region_revenue.get(nm, {}).get("units_sold", 0),
                        )
                    ),
                    for_pay=None if geo_filtered else product_money.get("for_pay", 0),
                    profit=None if geo_filtered else product_money.get("profit", 0),
                    margin_percent=product_money.get("margin_percent"),
                    wb_expenses=None
                    if geo_filtered
                    else product_money.get("wb_expenses", 0),
                    ad_spend=None if geo_filtered else product_money.get("ad_spend", 0),
                    drr_percent=product_money.get("drr_percent"),
                    stock_qty=None if geo_filtered else stock_row.get("stock_qty", 0),
                    days_of_stock=None
                    if geo_filtered
                    else stock_row.get("days_of_stock"),
                    current_price=price_row.get("current_price"),
                    current_discounted_price=price_row.get("current_discounted_price"),
                    return_count=None
                    if geo_filtered
                    else product_money.get("returns", 0),
                    return_rate=product_money.get("return_rate"),
                    row_source="region"
                    if geo_filtered
                    else str(row.get("row_source") or "funnel"),
                    cart_rate=self._pct(cart_count, open_count),
                    order_rate=self._pct(order_count, cart_count),
                    buyout_rate=self._pct(buyout_count, order_count),
                    open_delta_percent=self._delta_percent(
                        open_count, prev.get("open_count")
                    ),
                    order_delta_percent=self._delta_percent(
                        order_count, prev.get("order_count")
                    ),
                    revenue_delta_percent=self._delta_percent(
                        product_revenue,
                        previous_revenue,
                    ),
                    status=status,
                    issue=issue,
                    action=action,
                )
            )
        return result

    async def _product_funnel_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        if not nm_ids:
            return {}
        stmt = (
            select(
                WBCardFunnelDaily.nm_id,
                func.max(WBCardFunnelDaily.vendor_code).label("vendor_code"),
                func.max(WBCardFunnelDaily.title).label("title"),
                func.max(WBCardFunnelDaily.brand_name).label("brand_name"),
                func.max(WBCardFunnelDaily.subject_name).label("subject_name"),
                func.coalesce(func.sum(WBCardFunnelDaily.open_count), 0).label(
                    "open_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.cart_count), 0).label(
                    "cart_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.order_count), 0).label(
                    "order_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.buyout_count), 0).label(
                    "buyout_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.cancel_count), 0).label(
                    "cancel_count"
                ),
            )
            .where(
                WBCardFunnelDaily.account_id == account_id,
                WBCardFunnelDaily.stat_date >= start,
                WBCardFunnelDaily.stat_date <= end,
                WBCardFunnelDaily.nm_id.in_(nm_ids),
            )
            .group_by(WBCardFunnelDaily.nm_id)
        )
        return {
            int(row["nm_id"]): {
                key: self._to_float(value) if key.endswith("_count") else value
                for key, value in row.items()
                if key != "nm_id"
            }
            for row in (await session.execute(stmt)).mappings()
            if row["nm_id"] is not None
        }

    async def _product_previous_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_ids: list[int],
    ) -> dict[int, dict[str, float]]:
        if not nm_ids:
            return {}
        stmt = (
            select(
                WBCardFunnelDaily.nm_id,
                func.coalesce(func.sum(WBCardFunnelDaily.open_count), 0).label(
                    "open_count"
                ),
                func.coalesce(func.sum(WBCardFunnelDaily.order_count), 0).label(
                    "order_count"
                ),
            )
            .where(
                WBCardFunnelDaily.account_id == account_id,
                WBCardFunnelDaily.stat_date >= start,
                WBCardFunnelDaily.stat_date <= end,
                WBCardFunnelDaily.nm_id.in_(nm_ids),
            )
            .group_by(WBCardFunnelDaily.nm_id)
        )
        return {
            int(row["nm_id"]): {
                key: self._to_float(value)
                for key, value in row.items()
                if key != "nm_id"
            }
            for row in (await session.execute(stmt)).mappings()
        }

    async def _product_money_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_ids: list[int],
    ) -> dict[int, dict[str, float]]:
        if not nm_ids:
            return {}
        stmt = (
            select(
                MartSKUDaily.nm_id,
                func.coalesce(func.sum(MartSKUDaily.final_revenue), 0).label("revenue"),
                func.coalesce(func.sum(MartSKUDaily.final_for_pay), 0).label("for_pay"),
                func.coalesce(
                    func.sum(MartSKUDaily.net_profit_after_all_expenses), 0
                ).label("profit"),
                func.coalesce(func.sum(MartSKUDaily.total_wb_expenses), 0).label(
                    "wb_expenses"
                ),
                func.coalesce(func.sum(MartSKUDaily.ad_spend), 0).label("ad_spend"),
                func.coalesce(func.sum(MartSKUDaily.final_sales_qty), 0).label(
                    "units_sold"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_return_qty), 0).label(
                    "returns"
                ),
            )
            .where(
                MartSKUDaily.account_id == account_id,
                MartSKUDaily.stat_date >= start,
                MartSKUDaily.stat_date <= end,
                MartSKUDaily.nm_id.in_(nm_ids),
            )
            .group_by(MartSKUDaily.nm_id)
        )
        result: dict[int, dict[str, float]] = {}
        for row in (await session.execute(stmt)).mappings():
            nm_id = row["nm_id"]
            if nm_id is None:
                continue
            item = {
                key: self._to_float(value)
                for key, value in row.items()
                if key != "nm_id"
            }
            item["margin_percent"] = self._pct(item.get("profit"), item.get("revenue"))
            item["drr_percent"] = self._pct(item.get("ad_spend"), item.get("revenue"))
            item["return_rate"] = self._pct(item.get("returns"), item.get("units_sold"))
            result[int(nm_id)] = item
        return result

    async def _product_ads_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_ids: list[int],
    ) -> dict[int, dict[str, float]]:
        if not nm_ids:
            return {}
        stmt = (
            select(
                WBAdStatsDaily.nm_id,
                func.coalesce(func.sum(WBAdStatsDaily.sum), 0).label("ad_spend"),
                func.coalesce(func.sum(WBAdStatsDaily.views), 0).label("ad_views"),
                func.coalesce(func.sum(WBAdStatsDaily.clicks), 0).label("ad_clicks"),
                func.coalesce(func.sum(WBAdStatsDaily.orders), 0).label("ad_orders"),
                func.coalesce(func.sum(WBAdStatsDaily.sum_price), 0).label(
                    "ad_revenue"
                ),
            )
            .where(
                WBAdStatsDaily.account_id == account_id,
                WBAdStatsDaily.stat_date >= start,
                WBAdStatsDaily.stat_date <= end,
                WBAdStatsDaily.nm_id.in_(nm_ids),
            )
            .group_by(WBAdStatsDaily.nm_id)
        )
        return {
            int(row["nm_id"]): {
                key: self._to_float(value)
                for key, value in row.items()
                if key != "nm_id"
            }
            for row in (await session.execute(stmt)).mappings()
            if row["nm_id"] is not None
        }

    async def _product_stock_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_ids: list[int],
    ) -> dict[int, dict[str, float]]:
        if not nm_ids:
            return {}
        stock_date = await self._latest_stock_date(
            session, account_id=account_id, start=start, end=end
        )
        if stock_date is None:
            return {}
        stmt = (
            select(
                MartStockDaily.nm_id,
                func.coalesce(func.sum(MartStockDaily.quantity), 0).label("stock_qty"),
                func.avg(MartStockDaily.days_of_stock).label("days_of_stock"),
                func.count(
                    func.distinct(
                        case(
                            (
                                MartStockDaily.is_out_of_stock_risk.is_(True),
                                MartStockDaily.nm_id,
                            )
                        )
                    )
                ).label("risk_count"),
                func.count(
                    func.distinct(
                        case(
                            (
                                MartStockDaily.is_dead_stock.is_(True),
                                MartStockDaily.nm_id,
                            )
                        )
                    )
                ).label("dead_count"),
            )
            .where(
                MartStockDaily.account_id == account_id,
                MartStockDaily.stat_date == stock_date,
                MartStockDaily.nm_id.in_(nm_ids),
            )
            .group_by(MartStockDaily.nm_id)
        )
        return {
            int(row["nm_id"]): {
                "stock_qty": self._to_float(row["stock_qty"]),
                "days_of_stock": None
                if row["days_of_stock"] is None
                else round(self._to_float(row["days_of_stock"]), 1),
                "risk_count": int(row["risk_count"] or 0),
                "dead_count": int(row["dead_count"] or 0),
            }
            for row in (await session.execute(stmt)).mappings()
            if row["nm_id"] is not None
        }

    async def _product_price_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_ids: list[int],
    ) -> dict[int, dict[str, float]]:
        if not nm_ids:
            return {}
        stmt = (
            select(
                WBPriceSize.nm_id,
                func.avg(WBPriceSize.price).label("current_price"),
                func.avg(WBPriceSize.discounted_price).label(
                    "current_discounted_price"
                ),
            )
            .where(
                WBPriceSize.account_id == account_id,
                WBPriceSize.nm_id.in_(nm_ids),
            )
            .group_by(WBPriceSize.nm_id)
        )
        return {
            int(row["nm_id"]): {
                "current_price": None
                if row["current_price"] is None
                else round(self._to_float(row["current_price"]), 2),
                "current_discounted_price": None
                if row["current_discounted_price"] is None
                else round(self._to_float(row["current_discounted_price"]), 2),
            }
            for row in (await session.execute(stmt)).mappings()
            if row["nm_id"] is not None
        }

    async def _product_revenue_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_ids: list[int],
        region_name: str | None,
        country_name: str | None,
    ) -> dict[int, dict[str, float]]:
        if not nm_ids:
            return {}
        filters = [
            WBRegionSalesDaily.account_id == account_id,
            WBRegionSalesDaily.stat_date >= start,
            WBRegionSalesDaily.stat_date <= end,
            WBRegionSalesDaily.nm_id.in_(nm_ids),
        ]
        if region_name:
            filters.append(WBRegionSalesDaily.region_name.ilike(f"%{region_name}%"))
        if country_name:
            filters.append(WBRegionSalesDaily.country_name.ilike(f"%{country_name}%"))
        stmt = (
            select(
                WBRegionSalesDaily.nm_id,
                func.coalesce(func.sum(WBRegionSalesDaily.sale_amount), 0).label(
                    "revenue"
                ),
                func.coalesce(func.sum(WBRegionSalesDaily.sale_quantity), 0).label(
                    "units_sold"
                ),
            )
            .where(*filters)
            .group_by(WBRegionSalesDaily.nm_id)
        )
        return {
            int(row["nm_id"]): {
                key: self._to_float(value)
                for key, value in row.items()
                if key != "nm_id"
            }
            for row in (await session.execute(stmt)).mappings()
            if row["nm_id"] is not None
        }

    async def _top_regions(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        nm_id: int | None,
        vendor_code: str | None,
        region_name: str | None,
        country_name: str | None,
        search: str | None,
        limit: int,
    ) -> list[AnalyticsRegionRow]:
        revenue_sum = func.coalesce(func.sum(WBRegionSalesDaily.sale_amount), 0)
        stmt = (
            select(
                WBRegionSalesDaily.country_name,
                WBRegionSalesDaily.region_name,
                WBRegionSalesDaily.city_name,
                WBRegionSalesDaily.federal_district,
                revenue_sum.label("revenue"),
                func.coalesce(func.sum(WBRegionSalesDaily.sale_quantity), 0).label(
                    "units_sold"
                ),
                func.count(func.distinct(WBRegionSalesDaily.nm_id)).label(
                    "cards_count"
                ),
            )
            .where(
                *self._region_filters(
                    account_id=account_id,
                    start=start,
                    end=end,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    region_name=region_name,
                    country_name=country_name,
                    search=search,
                )
            )
            .group_by(
                WBRegionSalesDaily.country_name,
                WBRegionSalesDaily.region_name,
                WBRegionSalesDaily.city_name,
                WBRegionSalesDaily.federal_district,
            )
            .order_by(revenue_sum.desc())
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).mappings())
        total_revenue = sum(self._to_float(row["revenue"]) for row in rows)
        return [
            AnalyticsRegionRow(
                country_name=row["country_name"],
                region_name=row["region_name"],
                city_name=row["city_name"],
                federal_district=row["federal_district"],
                revenue=self._to_float(row["revenue"]),
                units_sold=self._to_float(row["units_sold"]),
                cards_count=int(row["cards_count"] or 0),
                share_percent=self._pct(self._to_float(row["revenue"]), total_revenue),
            )
            for row in rows
        ]

    def _summary(
        self,
        *,
        current_funnel: dict[str, float],
        previous_funnel: dict[str, float],
        current_regions: dict[str, float],
        previous_regions: dict[str, float],
        current_money: dict[str, float],
        previous_money: dict[str, float],
        geo_filtered: bool,
        hidden_counts: dict[str, int],
    ) -> AnalyticsSummary:
        if geo_filtered:
            return AnalyticsSummary(
                open_count=self._metric(None, None),
                cart_count=self._metric(None, None),
                order_count=self._metric(None, None),
                buyout_count=self._metric(None, None),
                cancel_count=self._metric(None, None),
                revenue=self._metric(
                    current_regions["revenue"], previous_regions["revenue"]
                ),
                units_sold=self._metric(
                    current_regions["units_sold"], previous_regions["units_sold"]
                ),
                active_cards=self._metric(
                    current_regions["region_cards"], previous_regions["region_cards"]
                ),
                cart_rate=self._metric(None, None),
                order_rate=self._metric(None, None),
                buyout_rate=self._metric(None, None),
                avg_order_value=self._metric(None, None),
                hidden_blocked=hidden_counts.get("blocked", 0),
                hidden_shadowed=hidden_counts.get("shadowed", 0),
            )
        cart_rate = self._pct(
            current_funnel["cart_count"], current_funnel["open_count"]
        )
        previous_cart_rate = self._pct(
            previous_funnel["cart_count"], previous_funnel["open_count"]
        )
        order_rate = self._pct(
            current_funnel["order_count"], current_funnel["cart_count"]
        )
        previous_order_rate = self._pct(
            previous_funnel["order_count"], previous_funnel["cart_count"]
        )
        buyout_rate = self._pct(
            current_funnel["buyout_count"], current_funnel["order_count"]
        )
        previous_buyout_rate = self._pct(
            previous_funnel["buyout_count"], previous_funnel["order_count"]
        )
        current_revenue = (
            current_money["revenue"]
            if current_money.get("rows_count", 0) > 0
            else current_regions["revenue"]
        )
        previous_revenue = (
            previous_money["revenue"]
            if previous_money.get("rows_count", 0) > 0
            else previous_regions["revenue"]
        )
        current_units = (
            current_money["units_sold"]
            if current_money.get("rows_count", 0) > 0
            else current_regions["units_sold"]
        )
        previous_units = (
            previous_money["units_sold"]
            if previous_money.get("rows_count", 0) > 0
            else previous_regions["units_sold"]
        )
        current_order_base = (
            current_money["orders"]
            if current_money.get("rows_count", 0) > 0
            else current_funnel["order_count"]
        )
        previous_order_base = (
            previous_money["orders"]
            if previous_money.get("rows_count", 0) > 0
            else previous_funnel["order_count"]
        )
        avg_order_value = (
            round(current_revenue / current_order_base, 2)
            if current_order_base > 0
            else None
        )
        previous_avg_order_value = (
            round(previous_revenue / previous_order_base, 2)
            if previous_order_base > 0
            else None
        )
        return AnalyticsSummary(
            open_count=self._metric(
                current_funnel["open_count"], previous_funnel["open_count"]
            ),
            cart_count=self._metric(
                current_funnel["cart_count"], previous_funnel["cart_count"]
            ),
            order_count=self._metric(
                current_funnel["order_count"], previous_funnel["order_count"]
            ),
            buyout_count=self._metric(
                current_funnel["buyout_count"], previous_funnel["buyout_count"]
            ),
            cancel_count=self._metric(
                current_funnel["cancel_count"], previous_funnel["cancel_count"]
            ),
            revenue=self._metric(current_revenue, previous_revenue),
            units_sold=self._metric(current_units, previous_units),
            active_cards=self._metric(
                current_funnel["active_cards"], previous_funnel["active_cards"]
            ),
            cart_rate=self._metric(cart_rate, previous_cart_rate),
            order_rate=self._metric(order_rate, previous_order_rate),
            buyout_rate=self._metric(buyout_rate, previous_buyout_rate),
            avg_order_value=self._metric(avg_order_value, previous_avg_order_value),
            hidden_blocked=hidden_counts.get("blocked", 0),
            hidden_shadowed=hidden_counts.get("shadowed", 0),
        )

    def _money_summary(
        self,
        current_money: dict[str, float],
        previous_money: dict[str, float],
    ) -> AnalyticsMoneySummary:
        return AnalyticsMoneySummary(
            revenue=self._metric(
                current_money.get("revenue"), previous_money.get("revenue")
            ),
            for_pay=self._metric(
                current_money.get("for_pay"), previous_money.get("for_pay")
            ),
            profit=self._metric(
                current_money.get("profit"), previous_money.get("profit")
            ),
            margin_percent=self._metric(
                current_money.get("margin_percent"),
                previous_money.get("margin_percent"),
            ),
            wb_expenses=self._metric(
                current_money.get("wb_expenses"), previous_money.get("wb_expenses")
            ),
            seller_expenses=self._metric(
                current_money.get("seller_expenses"),
                previous_money.get("seller_expenses"),
            ),
            cost_price=self._metric(
                current_money.get("cost_price"), previous_money.get("cost_price")
            ),
            orders=self._metric(
                current_money.get("orders"), previous_money.get("orders")
            ),
            returns=self._metric(
                current_money.get("returns"), previous_money.get("returns")
            ),
            return_rate=self._metric(
                current_money.get("return_rate"), previous_money.get("return_rate")
            ),
            rows_count=int(current_money.get("rows_count", 0)),
        )

    def _regional_money_summary(
        self,
        current_regions: dict[str, float],
        previous_regions: dict[str, float],
    ) -> AnalyticsMoneySummary:
        return AnalyticsMoneySummary(
            revenue=self._metric(
                current_regions.get("revenue"), previous_regions.get("revenue")
            ),
            rows_count=int(current_regions.get("rows_count", 0)),
        )

    def _ads_summary(
        self,
        current_ads: dict[str, float],
        previous_ads: dict[str, float],
    ) -> AnalyticsAdSummary:
        return AnalyticsAdSummary(
            spend=self._metric(current_ads.get("spend"), previous_ads.get("spend")),
            views=self._metric(current_ads.get("views"), previous_ads.get("views")),
            clicks=self._metric(current_ads.get("clicks"), previous_ads.get("clicks")),
            orders=self._metric(current_ads.get("orders"), previous_ads.get("orders")),
            ctr=self._metric(current_ads.get("ctr"), previous_ads.get("ctr")),
            cpc=self._metric(current_ads.get("cpc"), previous_ads.get("cpc")),
            drr_percent=self._metric(
                current_ads.get("drr_percent"), previous_ads.get("drr_percent")
            ),
            roas=self._metric(current_ads.get("roas"), previous_ads.get("roas")),
            rows_count=int(current_ads.get("rows_count", 0)),
        )

    async def _data_sources(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
    ) -> list[AnalyticsDataSourceStatus]:
        funnel_rows = int(
            (
                await session.execute(
                    select(func.count(WBCardFunnelDaily.id)).where(
                        WBCardFunnelDaily.account_id == account_id,
                        WBCardFunnelDaily.stat_date >= start,
                        WBCardFunnelDaily.stat_date <= end,
                    )
                )
            ).scalar_one()
            or 0
        )
        region_rows = int(
            (
                await session.execute(
                    select(func.count(WBRegionSalesDaily.id)).where(
                        WBRegionSalesDaily.account_id == account_id,
                        WBRegionSalesDaily.stat_date >= start,
                        WBRegionSalesDaily.stat_date <= end,
                    )
                )
            ).scalar_one()
            or 0
        )
        hidden_rows = int(
            (
                await session.execute(
                    select(func.count(WBHiddenProduct.id)).where(
                        WBHiddenProduct.account_id == account_id
                    )
                )
            ).scalar_one()
            or 0
        )
        mart_rows = int(
            (
                await session.execute(
                    select(func.count(MartSKUDaily.id)).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= start,
                        MartSKUDaily.stat_date <= end,
                    )
                )
            ).scalar_one()
            or 0
        )
        ad_rows = int(
            (
                await session.execute(
                    select(func.count(WBAdStatsDaily.id)).where(
                        WBAdStatsDaily.account_id == account_id,
                        WBAdStatsDaily.stat_date >= start,
                        WBAdStatsDaily.stat_date <= end,
                    )
                )
            ).scalar_one()
            or 0
        )
        stock_rows = int(
            (
                await session.execute(
                    select(func.count(MartStockDaily.id)).where(
                        MartStockDaily.account_id == account_id,
                        MartStockDaily.stat_date >= start,
                        MartStockDaily.stat_date <= end,
                    )
                )
            ).scalar_one()
            or 0
        )
        price_rows = int(
            (
                await session.execute(
                    select(func.count(WBPrice.id)).where(
                        WBPrice.account_id == account_id
                    )
                )
            ).scalar_one()
            or 0
        )
        card_rows = int(
            (
                await session.execute(
                    select(func.count(WBProductCard.id)).where(
                        WBProductCard.account_id == account_id
                    )
                )
            ).scalar_one()
            or 0
        )
        return [
            AnalyticsDataSourceStatus(
                key="sku_money",
                label="Финальная витрина по SKU",
                status="ok" if mart_rows else "empty",
                rows=mart_rows,
                note="mart_sku_daily: выручка, прибыль, расходы, реклама, цена",
            ),
            AnalyticsDataSourceStatus(
                key="sales_funnel",
                label="История воронки WB",
                status="ok" if funnel_rows else "empty",
                rows=funnel_rows,
                note="/api/analytics/v3/sales-funnel/products/history",
            ),
            AnalyticsDataSourceStatus(
                key="region_sales",
                label="Продажи WB по регионам",
                status="ok" if region_rows else "empty",
                rows=region_rows,
                note="/api/v1/analytics/region-sale",
            ),
            AnalyticsDataSourceStatus(
                key="ads",
                label="Реклама WB",
                status="ok" if ad_rows else "empty",
                rows=ad_rows,
                note="advert-api fullstats + mart_sku_daily.ad_spend",
            ),
            AnalyticsDataSourceStatus(
                key="stock",
                label="Остатки по складам",
                status="ok" if stock_rows else "empty",
                rows=stock_rows,
                note="warehouse_remains -> mart_stock_daily",
            ),
            AnalyticsDataSourceStatus(
                key="prices",
                label="Цены и скидки",
                status="ok" if price_rows else "empty",
                rows=price_rows,
                note="/api/v2/list/goods/filter + size/nm",
            ),
            AnalyticsDataSourceStatus(
                key="cards",
                label="Карточки товаров",
                status="ok" if card_rows else "empty",
                rows=card_rows,
                note="/content/v2/get/cards/list",
            ),
            AnalyticsDataSourceStatus(
                key="hidden_products",
                label="Скрытые и заблокированные карточки",
                status="ok" if hidden_rows else "empty",
                rows=hidden_rows,
                note="/api/v1/analytics/banned-products/*",
            ),
        ]

    @staticmethod
    def _delta_percent(value: float | None, previous: float | None) -> float | None:
        if previous in (None, 0):
            return None
        return round((float(value or 0) - float(previous)) / float(previous) * 100, 2)

    def _product_status(
        self,
        *,
        open_count: float,
        cart_count: float,
        order_count: float,
        buyout_count: float,
        revenue: float,
        profit: float,
        stock_qty: float,
        ad_spend: float,
    ) -> tuple[str, str | None, str | None]:
        cart_rate = self._pct(cart_count, open_count) or 0
        order_rate = self._pct(order_count, cart_count) or 0
        buyout_rate = self._pct(buyout_count, order_count) or 0
        if revenue > 0 and profit < 0:
            return (
                "danger",
                "Товар продаётся, но итоговая прибыль отрицательная.",
                "Проверить цену, себестоимость, комиссию WB, логистику и рекламный расход.",
            )
        if revenue > 0 and ad_spend > 0 and (self._pct(ad_spend, revenue) or 0) > 25:
            return (
                "warning",
                "Реклама забирает большую долю выручки.",
                "Сравнить ДРР, ставки кампаний и заказы по рекламным кластерам.",
            )
        if order_count > 0 and stock_qty <= 0:
            return (
                "danger",
                "Есть спрос, но по последнему stock-снимку нет остатка.",
                "Проверить остатки по складам и план поставки.",
            )
        if open_count >= 100 and cart_rate < 3:
            return (
                "danger",
                "Карточку открывают, но почти не добавляют в корзину.",
                "Проверить главный фото-блок, цену до скидки, рейтинг и первые 3 характеристики.",
            )
        if cart_count >= 20 and order_rate < 20:
            return (
                "warning",
                "Покупатели добавляют в корзину, но не оформляют заказ.",
                "Сравнить цену, срок доставки, остатки по складам и промо активность конкурентов.",
            )
        if order_count >= 5 and buyout_rate < 60:
            return (
                "warning",
                "Выкуп ниже нормы для текущих заказов.",
                "Проверить соответствие фото товару, размерную сетку, отзывы и причины возвратов.",
            )
        if revenue <= 0 and open_count > 0:
            return (
                "watch",
                "Есть трафик без подтвержденной выручки.",
                "Проверить свежесть mart_sku_daily, region-sale sync и связку nm_id в карточке.",
            )
        return ("ok", None, None)

    @staticmethod
    def _api_capabilities() -> list[AnalyticsApiCapability]:
        return [
            AnalyticsApiCapability(
                key="sales_funnel",
                label="Воронка по карточкам",
                endpoint="/api/analytics/v3/sales-funnel/products",
                status="active",
                note="Сравнение текущего периода с прошлым, обновление раз в час.",
            ),
            AnalyticsApiCapability(
                key="sales_funnel_history",
                label="История воронки по дням",
                endpoint="/api/analytics/v3/sales-funnel/products/history",
                status="active_sync",
                note="Используется текущей синхронизацией для дневного тренда.",
            ),
            AnalyticsApiCapability(
                key="finance_reports",
                label="Финансовые отчёты WB",
                endpoint="/api/finance/v1/sales-reports/detailed",
                status="active_sync",
                note="Источник выручки, выплат, комиссии, логистики и прибыли через mart_sku_daily.",
            ),
            AnalyticsApiCapability(
                key="ads_stats",
                label="Рекламная статистика",
                endpoint="/adv/v3/fullstats",
                status="active_sync",
                note="Расход, показы, клики и заказы по рекламным кампаниям.",
            ),
            AnalyticsApiCapability(
                key="prices",
                label="Цены и скидки",
                endpoint="/api/v2/list/goods/filter",
                status="active_sync",
                note="Текущие цены, скидки, размеры и карантин цен.",
            ),
            AnalyticsApiCapability(
                key="warehouse_remains",
                label="Остатки WB",
                endpoint="/api/v1/warehouse_remains",
                status="active_sync",
                note="Складские остатки, товары без запаса и неликвид.",
            ),
            AnalyticsApiCapability(
                key="search_queries",
                label="Поисковые запросы по товарам",
                endpoint="/api/v2/search-report/*",
                status="candidate",
                note="Нужен для поисковых фраз, позиций и заказов по запросам.",
            ),
            AnalyticsApiCapability(
                key="stocks_report",
                label="Остатки по складам WB",
                endpoint="/api/analytics/v1/stocks-report/wb-warehouses",
                status="candidate",
                note="Новый API остатков с постраничной выдачей и лимитом до 250 000 строк.",
            ),
            AnalyticsApiCapability(
                key="grouped_sales_funnel",
                label="Групповая воронка",
                endpoint="/api/analytics/v3/sales-funnel/grouped/history",
                status="candidate",
                note="Дневная воронка по предметам, брендам и меткам для сравнения категорий.",
            ),
            AnalyticsApiCapability(
                key="seller_csv",
                label="Большие табличные отчёты продавца",
                endpoint="/api/v2/nm-report/downloads",
                status="candidate",
                note="Асинхронные выгрузки для больших отчетов.",
            ),
        ]

    @staticmethod
    def _recommendations(
        summary: AnalyticsSummary,
        products: list[AnalyticsProductRow],
        regions: list[AnalyticsRegionRow],
        stock: AnalyticsStockSummary,
        prices: AnalyticsPriceSummary,
    ) -> list[AnalyticsRecommendation]:
        result: list[AnalyticsRecommendation] = []
        if (summary.open_count.value or 0) <= 0:
            result.append(
                AnalyticsRecommendation(
                    severity="warning",
                    title="Нет данных по воронке за период",
                    detail="UI готов к аналитике, но в выбранном окне нет строк sales funnel.",
                    action="Запустить sync analytics или расширить период.",
                    source="sales_funnel",
                )
            )
        if summary.hidden_blocked or summary.hidden_shadowed:
            result.append(
                AnalyticsRecommendation(
                    severity="danger",
                    title="Есть скрытые или заблокированные карточки",
                    detail=f"Blocked: {summary.hidden_blocked}, shadowed: {summary.hidden_shadowed}.",
                    action="Открыть список hidden products и устранить причины скрытия.",
                    source="hidden_products",
                )
            )
        weak_products = [row for row in products if row.status in {"danger", "warning"}]
        if weak_products:
            first = weak_products[0]
            result.append(
                AnalyticsRecommendation(
                    severity=first.status,
                    title=f"Слабое место воронки: {first.vendor_code or first.nm_id}",
                    detail=first.issue or "Карточка требует проверки.",
                    action=first.action or "Проверить карточку и цену.",
                    source="products",
                )
            )
        if (summary.cart_rate.value or 0) < 4 and (
            summary.open_count.value or 0
        ) >= 100:
            result.append(
                AnalyticsRecommendation(
                    severity="warning",
                    title="Низкий переход из открытия в корзину",
                    detail=f"Текущий open→cart: {(summary.cart_rate.value or 0):.2f}%.",
                    action="Сравнить фото, цену, рейтинг и оффер у топовых товаров категории.",
                    source="sales_funnel",
                )
            )
        if regions and regions[0].share_percent and regions[0].share_percent > 55:
            result.append(
                AnalyticsRecommendation(
                    severity="info",
                    title="Выручка сильно сконцентрирована в одном регионе",
                    detail=f"{regions[0].region_name or regions[0].country_name}: {regions[0].share_percent:.1f}% в топе регионов.",
                    action="Проверить остатки и доставку в соседних регионах, где есть спрос.",
                    source="regions",
                )
            )
        loss_products = [
            row
            for row in products
            if row.revenue > 0 and row.profit is not None and row.profit < 0
        ]
        if loss_products:
            first = loss_products[0]
            result.append(
                AnalyticsRecommendation(
                    severity="danger",
                    title=f"Минусовая прибыль: {first.vendor_code or first.nm_id}",
                    detail=f"Выручка {first.revenue:.2f}, прибыль {first.profit:.2f}.",
                    action="Проверить цену, комиссию WB, логистику, себестоимость и рекламу.",
                    source="money",
                )
            )
        if stock.out_of_stock_risk:
            result.append(
                AnalyticsRecommendation(
                    severity="warning",
                    title="Есть риск обнуления остатков",
                    detail=f"Карточек в зоне риска: {stock.out_of_stock_risk}.",
                    action="Открыть товары с остатком и подготовить поставку по складам.",
                    source="stock",
                )
            )
        if prices.quarantine:
            result.append(
                AnalyticsRecommendation(
                    severity="danger",
                    title="Есть товары в карантине цен",
                    detail=f"Строк карантина: {prices.quarantine}.",
                    action="Проверить последние изменения цены и скидки перед следующим обновлением.",
                    source="prices",
                )
            )
        return result[:5]
