from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.current_state import orders_current_subquery, sales_current_subquery
from app.core.time import utcnow
from app.models.analytics import WBRegionSalesDaily
from app.models.finance import WBRealizationReport, WBRealizationReportRow
from app.models.logistics import (
    WBLogisticsAcceptanceReportRow,
    WBLogisticsPaidStorageRow,
    WBLogisticsTransitTariff,
    WBSellerWarehouse,
    WBSellerWarehouseStock,
)
from app.models.orders import WBOrder
from app.models.product_cards import CoreSKU
from app.models.sales import WBSale
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.models.supplies import WBSupply, WBSupplyGood
from app.models.tariffs import WBTariffAcceptance, WBTariffBox
from app.schemas.logistics import (
    LogisticsAcceptanceDetailRow,
    LogisticsApiCapability,
    LogisticsDataSourceStatus,
    LogisticsKpis,
    LogisticsOverviewRead,
    LogisticsPeriod,
    LogisticsPaidStorageDetailRow,
    LogisticsProductRow,
    LogisticsRecommendation,
    LogisticsRegionalShipmentRow,
    LogisticsSellerWarehouseRow,
    LogisticsSupplyRow,
    LogisticsTaskRow,
    LogisticsTransitTariffRow,
    LogisticsWarehouseControlRow,
    LogisticsWarehouseRow,
)


SPECIAL_STOCK_WAREHOUSES = {
    "В пути до получателей",
    "В пути возвраты на склад WB",
    "Всего находится на складах",
}

SUPPLY_STATUS_LABELS = {
    1: "Не запланирована",
    2: "Запланирована",
    3: "Отгрузка разрешена",
    4: "Принимается",
    5: "Принята",
    6: "Разгружена у ворот",
}

OOS_FAST_DAYS = 14
OOS_PLANNING_DAYS = 30
MOSCOW_TZ_NAME = "Europe/Moscow"
MOSCOW_TZ = ZoneInfo(MOSCOW_TZ_NAME)
STOCK_FRESHNESS_DAYS = 2
TARIFF_FRESHNESS_DAYS = 2


class LogisticsService:
    async def overview(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        warehouse_limit: int = 50,
        supply_limit: int = 20,
        product_limit: int = 120,
    ) -> LogisticsOverviewRead:
        start, end = self._resolve_period(date_from, date_to)
        search_norm = (search or "").strip().casefold()

        warehouse_map: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "warehouse_name": "",
                "warehouse_id": None,
                "region_name": None,
                "stock_units": 0.0,
                "in_way_to_client": 0.0,
                "in_way_from_client": 0.0,
                "orders_qty": 0.0,
                "cancelled_orders_qty": 0.0,
                "cancelled_revenue": 0.0,
                "sales_qty": 0.0,
                "sales_revenue": 0.0,
                "sales_for_pay": 0.0,
                "finance_revenue": 0.0,
                "finance_for_pay": 0.0,
                "finance_rows": 0,
                "finance_money_rows": 0,
                "logistics_cost": 0.0,
                "storage_cost": 0.0,
                "acceptance_cost": 0.0,
                "return_logistics_cost": 0.0,
                "missed_orders_qty": 0.0,
                "missed_revenue": 0.0,
                "acceptance_coefficient": None,
                "allow_unload": None,
                "acceptance_next_available_at": None,
                "acceptance_box_type_id": None,
                "acceptance_option": None,
                "delivery_base": None,
                "delivery_liter": None,
                "storage_base": None,
                "box_type_ids": set(),
                "supply_count": 0,
                "open_supply_count": 0,
            }
        )
        region_votes: dict[str, Counter[str]] = defaultdict(Counter)
        stock_totals = {
            "in_way_to_client": 0.0,
            "in_way_from_client": 0.0,
        }
        closed_finance_date_to = await self._finance_closed_through_date(
            session,
            account_id=account_id,
            start=start,
            end=end,
        )

        await self._merge_orders(
            session,
            account_id=account_id,
            start=start,
            end=end,
            warehouse_map=warehouse_map,
            region_votes=region_votes,
        )
        await self._merge_sales(
            session,
            account_id=account_id,
            start=start,
            end=end,
            closed_finance_date_to=closed_finance_date_to,
            warehouse_map=warehouse_map,
        )
        await self._merge_finance(
            session,
            account_id=account_id,
            start=start,
            end=end,
            warehouse_map=warehouse_map,
        )
        latest_stock_at = await self._merge_stock(
            session,
            account_id=account_id,
            warehouse_map=warehouse_map,
            stock_totals=stock_totals,
        )
        await self._merge_tariffs(
            session,
            account_id=account_id,
            warehouse_map=warehouse_map,
            region_votes=region_votes,
        )
        supplies = await self._supplies(
            session,
            account_id=account_id,
            start=start,
            end=end,
            limit=supply_limit,
            warehouse_map=warehouse_map,
        )
        region_demand = await self._region_demand(
            session,
            account_id=account_id,
            start=start,
            end=end,
        )

        filtered_rows = []
        day_count = max((end - start).days + 1, 1)
        for key, item in warehouse_map.items():
            item["warehouse_name"] = item["warehouse_name"] or key
            if item["region_name"] is None and region_votes[key]:
                item["region_name"] = region_votes[key].most_common(1)[0][0]
            row = self._warehouse_row(
                item, day_count=day_count, region_demand=region_demand
            )
            if search_norm and search_norm not in (
                f"{row.warehouse_name} {row.region_name or ''}".casefold()
            ):
                continue
            filtered_rows.append(row)
        filtered_rows.sort(
            key=lambda row: (
                self._risk_sort(row.risk_level),
                -(row.missed_revenue or 0),
                -(row.revenue or 0),
                row.warehouse_name,
            )
        )
        visible_rows = filtered_rows[:warehouse_limit]

        kpis = self._kpis(
            filtered_rows,
            stock_totals=None if search_norm else stock_totals,
        )
        data_sources = await self._data_sources(
            session,
            account_id=account_id,
            start=start,
            end=end,
            latest_stock_at=latest_stock_at,
        )
        tasks = self._tasks(filtered_rows, day_count=day_count)
        products = await self._products(
            session,
            account_id=account_id,
            start=start,
            end=end,
            day_count=day_count,
            warehouse_rows=filtered_rows,
            search_norm=search_norm,
            limit=product_limit,
            latest_stock_at=latest_stock_at,
            closed_finance_date_to=closed_finance_date_to,
        )
        regional_shipments = self._regional_shipments(
            filtered_rows, day_count=day_count
        )
        warehouse_controls = self._warehouse_controls(filtered_rows, tasks)
        paid_storage_details = await self._paid_storage_details(
            session, account_id=account_id, start=start, end=end, limit=80
        )
        acceptance_details = await self._acceptance_details(
            session, account_id=account_id, start=start, end=end, limit=80
        )
        transit_tariffs = await self._transit_tariffs(
            session, account_id=account_id, limit=80
        )
        seller_warehouses = await self._seller_warehouses(
            session, account_id=account_id, limit=80
        )
        detail_totals = await self._detail_kpi_totals(
            session, account_id=account_id, start=start, end=end
        )
        self._augment_kpis_with_details(
            kpis,
            detail_totals=detail_totals,
        )
        recommendations = self._recommendations(kpis, filtered_rows, data_sources)
        return LogisticsOverviewRead(
            account_id=account_id,
            period=LogisticsPeriod(date_from=start, date_to=end),
            kpis=kpis,
            warehouses=visible_rows,
            supplies=supplies,
            tasks=tasks,
            products=products,
            regional_shipments=regional_shipments,
            warehouse_controls=warehouse_controls,
            paid_storage_details=paid_storage_details,
            acceptance_details=acceptance_details,
            transit_tariffs=transit_tariffs,
            seller_warehouses=seller_warehouses,
            data_sources=data_sources,
            api_capabilities=self._api_capabilities(),
            recommendations=recommendations,
            generated_at=utcnow(),
        )

    async def export_csv(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        dataset: str,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        disabled_warehouses: set[str] | None = None,
    ) -> str:
        overview = await self.overview(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
            warehouse_limit=200,
            supply_limit=100,
            product_limit=500,
        )
        disabled = {name for name in (disabled_warehouses or set()) if name}
        output = io.StringIO()
        if dataset == "tasks":
            columns = [
                "severity",
                "task_type",
                "title",
                "warehouse_name",
                "region_name",
                "recommended_supply_qty",
                "potential_orders_qty",
                "potential_revenue",
                "expected_net_effect",
                "stockout_in_days",
                "logistics_share_percent",
                "buyout_percent",
                "confidence",
                "tags",
                "action",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.tasks:
                if row.warehouse_name in disabled:
                    continue
                writer.writerow(
                    {
                        **row.model_dump(),
                        "tags": ", ".join(row.tags),
                    }
                )
        elif dataset == "regional":
            columns = [
                "priority",
                "warehouse_name",
                "region_name",
                "recommended_supply_qty",
                "potential_orders_qty",
                "potential_revenue",
                "expected_logistics_cost",
                "expected_net_effect",
                "current_stock_units",
                "turnover_days",
                "acceptance_status",
                "acceptance_coefficient",
                "tags",
                "reason",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.regional_shipments:
                if row.warehouse_name in disabled:
                    continue
                writer.writerow(
                    {
                        **row.model_dump(),
                        "tags": ", ".join(row.tags),
                    }
                )
        elif dataset == "controls":
            columns = [
                "warehouse_name",
                "region_name",
                "mode",
                "recommended_mode",
                "task_count",
                "potential_revenue",
                "stock_units",
                "turnover_days",
                "acceptance_status",
                "logistics_share_percent",
                "reason",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.warehouse_controls:
                if row.warehouse_name in disabled:
                    continue
                writer.writerow(row.model_dump())
        elif dataset in {"products", "shipment"}:
            columns = [
                "risk_level",
                "warehouse_name",
                "region_name",
                "nm_id",
                "vendor_code",
                "barcode",
                "title",
                "brand",
                "subject_name",
                "stock_units",
                "orders_qty",
                "sales_qty",
                "cancelled_orders_qty",
                "revenue",
                "recommended_supply_14",
                "recommended_supply_30",
                "potential_orders_qty",
                "potential_revenue",
                "expected_net_effect",
                "turnover_days",
                "buyout_percent",
                "logistics_share_percent",
                "tags",
                "reason",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.products:
                if row.warehouse_name in disabled:
                    continue
                if dataset == "shipment" and row.recommended_supply_30 <= 0:
                    continue
                writer.writerow(
                    {
                        **row.model_dump(),
                        "tags": ", ".join(row.tags),
                    }
                )
        elif dataset == "paid_storage":
            columns = [
                "report_date",
                "warehouse_name",
                "nm_id",
                "vendor_code",
                "barcode",
                "title",
                "brand",
                "subject_name",
                "quantity",
                "amount",
                "amount_per_unit",
                "share_percent",
                "task_id",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.paid_storage_details:
                writer.writerow(row.model_dump())
        elif dataset == "acceptance":
            columns = [
                "operation_date",
                "warehouse_name",
                "operation_name",
                "nm_id",
                "vendor_code",
                "barcode",
                "title",
                "brand",
                "subject_name",
                "quantity",
                "amount",
                "amount_per_unit",
                "share_percent",
                "task_id",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.acceptance_details:
                writer.writerow(row.model_dump())
        elif dataset == "transit":
            columns = [
                "route_label",
                "source_warehouse_name",
                "transit_warehouse_name",
                "destination_warehouse_name",
                "box_type_id",
                "coefficient",
                "delivery_base",
                "delivery_liter",
                "amount",
                "currency",
                "transit_time_days",
                "score",
                "collected_at",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.transit_tariffs:
                writer.writerow(row.model_dump())
        elif dataset == "seller_warehouses":
            columns = [
                "warehouse_id",
                "name",
                "office_id",
                "delivery_type",
                "delivery_type_label",
                "cargo_type",
                "is_active",
                "stock_rows",
                "stock_units",
                "latest_stock_at",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.seller_warehouses:
                writer.writerow(row.model_dump())
        else:
            columns = [
                "warehouse_name",
                "region_name",
                "risk_level",
                "stock_units",
                "turnover_days",
                "orders_qty",
                "sales_qty",
                "revenue",
                "missed_orders_qty",
                "missed_revenue",
                "logistics_share_percent",
                "buyout_percent",
                "margin_percent",
                "acceptance_status",
                "acceptance_coefficient",
                "recommendation",
            ]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for row in overview.warehouses:
                writer.writerow(row.model_dump())
        return output.getvalue()

    @staticmethod
    def _resolve_period(
        date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        today = utcnow().astimezone(MOSCOW_TZ).date()
        end = date_to or today
        start = date_from or (end - timedelta(days=29))
        if start > end:
            start, end = end, start
        return start, end

    @staticmethod
    def _date_bounds(start: date, end: date) -> tuple[datetime, datetime]:
        start_dt = datetime.combine(start, time.min, tzinfo=MOSCOW_TZ)
        end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=MOSCOW_TZ)
        return start_dt, end_dt

    @staticmethod
    def _warehouse_key(value: str | None) -> str:
        text = (value or "Не указан").strip()
        return text or "Не указан"

    @staticmethod
    def _region_key(value: str | None) -> str:
        text = (value or "").strip().casefold()
        if not text:
            return ""
        for suffix in (
            "федеральный округ",
            "федерального округа",
            " фо",
        ):
            text = text.replace(suffix, "")
        return " ".join(text.replace("-", " ").split())

    def _region_demand_for_name(
        self,
        region_name: str | None,
        region_demand: dict[str, dict[str, float | str | None]] | None,
    ) -> dict[str, float | str | None]:
        if not region_demand:
            return {"sales_qty": 0.0, "sales_amount": 0.0, "share_percent": None}
        return region_demand.get(self._region_key(region_name)) or {
            "sales_qty": 0.0,
            "sales_amount": 0.0,
            "share_percent": None,
        }

    @staticmethod
    def _float(value: Any) -> float:
        if value is None:
            return 0.0
        try:
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float | None:
        if not denominator:
            return None
        return numerator / denominator * 100

    @staticmethod
    def _parse_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, int | float | Decimal):
            return float(value)
        text = str(value).strip().replace("\u00a0", "").replace(" ", "")
        if not text:
            return None
        text = text.replace(",", ".")
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _first_payload_number(
        payload: dict[str, Any], keys: tuple[str, ...]
    ) -> float | None:
        for key in keys:
            parsed = LogisticsService._parse_number(payload.get(key))
            if parsed is not None:
                return parsed
        return None

    async def _merge_orders(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        warehouse_map: dict[str, dict[str, Any]],
        region_votes: dict[str, Counter[str]],
    ) -> None:
        start_dt, end_dt = self._date_bounds(start, end)
        orders_current = orders_current_subquery("logistics_orders_current")
        cancelled_in_period = and_(
            orders_current.c.is_cancel.is_(True),
            orders_current.c.cancel_date.is_not(None),
            orders_current.c.cancel_date >= start_dt,
            orders_current.c.cancel_date < end_dt,
        )
        value_expr = func.coalesce(
            orders_current.c.finished_price,
            orders_current.c.price_with_disc,
            orders_current.c.total_price,
            0,
        )
        stmt = (
            select(
                orders_current.c.warehouse_name.label("warehouse_name"),
                orders_current.c.oblast_okrug_name.label("region_name"),
                func.count(orders_current.c.id).label("orders_qty"),
                func.sum(case((cancelled_in_period, 1), else_=0)).label(
                    "cancelled_orders_qty"
                ),
                func.sum(value_expr).label("order_revenue"),
                func.sum(case((cancelled_in_period, value_expr), else_=0)).label(
                    "cancelled_revenue"
                ),
            )
            .where(
                orders_current.c.account_id == account_id,
                orders_current.c.date.is_not(None),
                orders_current.c.date >= start_dt,
                orders_current.c.date < end_dt,
            )
            .group_by(
                orders_current.c.warehouse_name, orders_current.c.oblast_okrug_name
            )
        )
        for row in (await session.execute(stmt)).mappings():
            key = self._warehouse_key(row["warehouse_name"])
            item = warehouse_map[key]
            item["warehouse_name"] = key
            item["orders_qty"] += self._float(row["orders_qty"])
            item["cancelled_orders_qty"] += self._float(row["cancelled_orders_qty"])
            item["cancelled_revenue"] += self._float(row["cancelled_revenue"])
            if row["region_name"]:
                region_votes[key][str(row["region_name"])] += int(
                    row["orders_qty"] or 1
                )

    async def _merge_sales(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        closed_finance_date_to: date | None,
        warehouse_map: dict[str, dict[str, Any]],
    ) -> None:
        sales_start = self._operational_sales_start(
            start=start, closed_finance_date_to=closed_finance_date_to
        )
        if sales_start > end:
            return
        start_dt, end_dt = self._date_bounds(sales_start, end)
        sales_current = sales_current_subquery("logistics_sales_current")
        value_expr = func.coalesce(
            sales_current.c.finished_price,
            sales_current.c.price_with_disc,
            sales_current.c.total_price,
            0,
        )
        for_pay_expr = func.coalesce(sales_current.c.for_pay, 0)
        sale_return_condition = self._sale_return_condition(sales_current)
        positive_sale_expr = case((sale_return_condition, 0), else_=1)
        stmt = (
            select(
                sales_current.c.warehouse_name.label("warehouse_name"),
                func.sum(positive_sale_expr).label("sales_qty"),
                func.sum(self._signed_sale_sql_expr(value_expr, sales_current)).label(
                    "revenue"
                ),
                func.sum(self._signed_sale_sql_expr(for_pay_expr, sales_current)).label(
                    "for_pay"
                ),
            )
            .where(
                sales_current.c.account_id == account_id,
                sales_current.c.date.is_not(None),
                sales_current.c.date >= start_dt,
                sales_current.c.date < end_dt,
            )
            .group_by(sales_current.c.warehouse_name)
        )
        for row in (await session.execute(stmt)).mappings():
            key = self._warehouse_key(row["warehouse_name"])
            item = warehouse_map[key]
            item["warehouse_name"] = key
            item["sales_qty"] += self._float(row["sales_qty"])
            item["sales_revenue"] += self._float(row["revenue"])
            item["sales_for_pay"] += self._float(row["for_pay"])

    @staticmethod
    def _operational_sales_start(
        *, start: date, closed_finance_date_to: date | None
    ) -> date:
        if closed_finance_date_to is None:
            return start
        return max(start, closed_finance_date_to + timedelta(days=1))

    async def _finance_closed_through_date(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
    ) -> date | None:
        if session is None:
            return None
        reports = (
            (
                await session.execute(
                    select(
                        WBRealizationReport.date_from,
                        WBRealizationReport.date_to,
                        WBRealizationReport.create_date,
                    ).where(WBRealizationReport.account_id == account_id)
                )
            )
            .mappings()
            .all()
        )
        closed_to_candidates = []
        for report in reports:
            closed_to = report["date_to"] or report["create_date"]
            closed_from = report["date_from"] or closed_to
            if closed_to is None or closed_from is None:
                continue
            if closed_to >= start and closed_from <= end:
                closed_to_candidates.append(closed_to)
        if closed_to_candidates:
            return min(max(closed_to_candidates), end)
        return (
            await session.execute(
                select(func.max(WBRealizationReportRow.rr_date)).where(
                    WBRealizationReportRow.account_id == account_id,
                    WBRealizationReportRow.rr_date >= start,
                    WBRealizationReportRow.rr_date <= end,
                )
            )
        ).scalar_one_or_none()

    async def _merge_finance(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        warehouse_map: dict[str, dict[str, Any]],
    ) -> None:
        stmt = (
            select(
                WBRealizationReportRow.office_name.label("warehouse_name"),
                func.sum(
                    func.coalesce(WBRealizationReportRow.delivery_service, 0)
                ).label("delivery_service"),
                func.sum(
                    func.coalesce(WBRealizationReportRow.rebill_logistic_cost, 0)
                ).label("rebill_logistic_cost"),
                func.sum(func.coalesce(WBRealizationReportRow.paid_storage, 0)).label(
                    "paid_storage"
                ),
                func.sum(
                    func.coalesce(WBRealizationReportRow.paid_acceptance, 0)
                ).label("paid_acceptance"),
                func.count(WBRealizationReportRow.id).label("finance_rows"),
            )
            .where(
                WBRealizationReportRow.account_id == account_id,
                self._finance_period_filter(start=start, end=end),
            )
            .group_by(WBRealizationReportRow.office_name)
        )
        for row in (await session.execute(stmt)).mappings():
            key = self._warehouse_key(row["warehouse_name"])
            item = warehouse_map[key]
            item["warehouse_name"] = key
            delivery = self._float(row["delivery_service"])
            rebill = self._float(row["rebill_logistic_cost"])
            item["finance_rows"] += int(row["finance_rows"] or 0)
            item["logistics_cost"] += delivery
            item["return_logistics_cost"] += rebill
            item["storage_cost"] += self._float(row["paid_storage"])
            item["acceptance_cost"] += self._float(row["paid_acceptance"])
        await self._merge_resolved_finance_money(
            session,
            account_id=account_id,
            start=start,
            end=end,
            warehouse_map=warehouse_map,
        )

    async def _core_sku_matcher(
        self, session: AsyncSession, *, account_id: int
    ) -> tuple[Any, dict[str, dict[Any, list[CoreSKU]]]]:
        from app.services.marts import MartService

        mart_service = MartService()
        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        return mart_service, mart_service._build_core_sku_index(core_skus)

    @staticmethod
    def _finance_row_resolves_to_core_sku(
        row: WBRealizationReportRow,
        *,
        mart_service: Any,
        core_index: dict[str, dict[Any, list[CoreSKU]]],
    ) -> bool:
        barcode = mart_service._finance_row_barcode(row)
        return (
            mart_service._resolve_core_sku(
                core_index,
                vendor_code=row.vendor_code,
                nm_id=row.nm_id,
                barcode=barcode,
                tech_size=None,
            )
            is not None
        )

    async def _merge_resolved_finance_money(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        warehouse_map: dict[str, dict[str, Any]],
    ) -> None:
        mart_service, core_index = await self._core_sku_matcher(
            session, account_id=account_id
        )
        rows = list(
            (
                await session.execute(
                    select(WBRealizationReportRow).where(
                        WBRealizationReportRow.account_id == account_id,
                        self._finance_period_filter(start=start, end=end),
                    )
                )
            ).scalars()
        )
        for row in rows:
            if not self._is_reconcilable_finance_row(row):
                continue
            if not self._finance_row_resolves_to_core_sku(
                row, mart_service=mart_service, core_index=core_index
            ):
                continue
            revenue = self._signed_finance_amount(row, row.retail_amount)
            for_pay = self._signed_finance_amount(row, row.for_pay)
            item = warehouse_map[self._warehouse_key(row.office_name)]
            item["warehouse_name"] = self._warehouse_key(row.office_name)
            if revenue != 0 or for_pay != 0:
                item["finance_money_rows"] += 1
            if self._finance_row_sign(row) > 0:
                item["sales_qty"] += self._float(row.quantity or 1)
            item["finance_revenue"] += self._float(revenue)
            item["finance_for_pay"] += self._float(for_pay)

    @staticmethod
    def _source_column(source: Any, name: str) -> Any:
        columns = getattr(source, "c", None)
        return getattr(columns, name) if columns is not None else getattr(source, name)

    @classmethod
    def _sale_return_condition(cls, source: Any = WBSale) -> Any:
        sale_id = func.lower(func.coalesce(cls._source_column(source, "sale_id"), ""))
        for_pay = cls._source_column(source, "for_pay")
        is_cancel = cls._source_column(source, "is_cancel")
        return or_(
            is_cancel.is_(True),
            sale_id.like("r%"),
            func.coalesce(for_pay, 0) < 0,
        )

    @classmethod
    def _signed_sale_sql_expr(cls, value_expr: Any, source: Any = WBSale) -> Any:
        return case(
            (and_(cls._sale_return_condition(source), value_expr > 0), -value_expr),
            else_=value_expr,
        )

    @staticmethod
    def _reconcilable_finance_condition() -> Any:
        doc_type = func.lower(func.coalesce(WBRealizationReportRow.doc_type_name, ""))
        return or_(
            WBRealizationReportRow.is_reconcilable.is_(True),
            and_(
                WBRealizationReportRow.is_reconcilable.is_(None),
                doc_type.in_(("продажа", "возврат", "sale", "return")),
            ),
        )

    @staticmethod
    def _finance_return_condition() -> Any:
        doc_type = func.lower(func.coalesce(WBRealizationReportRow.doc_type_name, ""))
        return or_(
            WBRealizationReportRow.is_return_operation.is_(True),
            doc_type.like("%возврат%"),
            doc_type.like("%return%"),
            func.coalesce(WBRealizationReportRow.retail_amount, 0) < 0,
            func.coalesce(WBRealizationReportRow.for_pay, 0) < 0,
        )

    @classmethod
    def _signed_finance_sql_expr(cls, value_expr: Any) -> Any:
        return case(
            (and_(cls._finance_return_condition(), value_expr > 0), -value_expr),
            else_=value_expr,
        )

    @staticmethod
    def _finance_period_filter(*, start: date, end: date) -> Any:
        sale_date_expr = func.date(
            func.timezone(MOSCOW_TZ_NAME, WBRealizationReportRow.sale_dt)
        )
        return or_(
            and_(
                WBRealizationReportRow.sale_dt.is_not(None),
                sale_date_expr >= start,
                sale_date_expr <= end,
            ),
            and_(
                WBRealizationReportRow.sale_dt.is_(None),
                WBRealizationReportRow.rr_date.is_not(None),
                WBRealizationReportRow.rr_date >= start,
                WBRealizationReportRow.rr_date <= end,
            ),
        )

    @staticmethod
    def _finance_row_sign(row: WBRealizationReportRow) -> int:
        doc_type = (row.doc_type_name or "").lower()
        if (
            row.is_return_operation is True
            or "возврат" in doc_type
            or "return" in doc_type
        ):
            return -1
        if (
            Decimal(str(row.retail_amount or 0)) < 0
            or Decimal(str(row.for_pay or 0)) < 0
        ):
            return -1
        return 1

    @staticmethod
    def _is_reconcilable_finance_row(row: WBRealizationReportRow) -> bool:
        if row.is_reconcilable is not None:
            return bool(row.is_reconcilable)
        doc_type = (row.doc_type_name or "").strip().lower()
        return doc_type in {"продажа", "возврат", "sale", "return"}

    @classmethod
    def _signed_finance_amount(cls, row: WBRealizationReportRow, value: Any) -> Decimal:
        amount = Decimal(str(value or 0))
        if amount == 0:
            return amount
        if cls._finance_row_sign(row) < 0 and amount > 0:
            return -amount
        return amount

    async def _merge_stock(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        warehouse_map: dict[str, dict[str, Any]],
        stock_totals: dict[str, float],
    ) -> datetime | None:
        snapshot = (
            (
                await session.execute(
                    select(WBStockSnapshot)
                    .where(WBStockSnapshot.account_id == account_id)
                    .order_by(
                        WBStockSnapshot.snapshot_at.desc(), WBStockSnapshot.id.desc()
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if snapshot is None:
            return None
        rows = list(
            (
                await session.execute(
                    select(WBStockSnapshotRow).where(
                        WBStockSnapshotRow.snapshot_id == snapshot.id,
                        WBStockSnapshotRow.account_id == account_id,
                    )
                )
            ).scalars()
        )
        for row in rows:
            key = self._warehouse_key(row.warehouse_name)
            quantity = self._float(row.quantity)
            if key == "В пути до получателей":
                stock_totals["in_way_to_client"] += (
                    self._float(row.in_way_to_client) or quantity
                )
                continue
            if key == "В пути возвраты на склад WB":
                stock_totals["in_way_from_client"] += (
                    self._float(row.in_way_from_client) or quantity
                )
                continue
            if key == "Всего находится на складах":
                continue
            item = warehouse_map[key]
            item["warehouse_name"] = key
            if row.warehouse_id is not None:
                item["warehouse_id"] = row.warehouse_id
            item["stock_units"] += quantity or self._float(row.quantity_full)
            item["in_way_to_client"] += self._float(row.in_way_to_client)
            item["in_way_from_client"] += self._float(row.in_way_from_client)
            stock_totals["in_way_to_client"] += self._float(row.in_way_to_client)
            stock_totals["in_way_from_client"] += self._float(row.in_way_from_client)
        return snapshot.snapshot_at

    async def _merge_tariffs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        warehouse_map: dict[str, dict[str, Any]],
        region_votes: dict[str, Counter[str]],
    ) -> None:
        acceptance_date = (
            await session.execute(
                select(func.max(WBTariffAcceptance.collected_at)).where(
                    WBTariffAcceptance.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        if acceptance_date is not None:
            rows = (
                (
                    await session.execute(
                        select(WBTariffAcceptance).where(
                            WBTariffAcceptance.account_id == account_id,
                            WBTariffAcceptance.collected_at == acceptance_date,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                key = self._warehouse_key(row.warehouse_name)
                item = warehouse_map[key]
                item["warehouse_name"] = key
                if row.warehouse_id is not None:
                    item["warehouse_id"] = row.warehouse_id
                box_type_id = row.payload.get("boxTypeID") or row.payload.get(
                    "boxTypeId"
                )
                if box_type_id is not None:
                    try:
                        item["box_type_ids"].add(int(box_type_id))
                    except Exception:
                        pass
                option = self._acceptance_option(row)
                current = item.get("acceptance_option")
                if current is None or option["sort_key"] < current["sort_key"]:
                    item["acceptance_option"] = option
                    item["acceptance_coefficient"] = row.coefficient
                    item["allow_unload"] = row.allow_unload
                    item["acceptance_next_available_at"] = option["date"]
                    item["acceptance_box_type_id"] = option["box_type_id"]

        box_date = (
            await session.execute(
                select(func.max(WBTariffBox.collected_at)).where(
                    WBTariffBox.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        if box_date is None:
            return
        rows = (
            (
                await session.execute(
                    select(WBTariffBox).where(
                        WBTariffBox.account_id == account_id,
                        WBTariffBox.collected_at == box_date,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            key = self._warehouse_key(row.warehouse_name)
            item = warehouse_map[key]
            payload = row.payload or {}
            item["warehouse_name"] = key
            item["delivery_base"] = self._first_payload_number(
                payload, ("boxDeliveryBase", "boxDeliveryMarketplaceBase")
            )
            item["delivery_liter"] = self._first_payload_number(
                payload, ("boxDeliveryLiter", "boxDeliveryMarketplaceLiter")
            )
            item["storage_base"] = self._first_payload_number(
                payload, ("boxStorageBase",)
            )
            geo_name = payload.get("geoName")
            if geo_name:
                region_votes[key][str(geo_name)] += 1

    async def _supplies(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        limit: int,
        warehouse_map: dict[str, dict[str, Any]],
    ) -> list[LogisticsSupplyRow]:
        start_dt, end_dt = self._date_bounds(start, end)
        date_expr = func.coalesce(
            WBSupply.fact_date,
            WBSupply.supply_date,
            WBSupply.updated_date,
            WBSupply.create_date,
        )
        supplies = list(
            (
                await session.execute(
                    select(WBSupply)
                    .where(
                        WBSupply.account_id == account_id,
                        or_(
                            WBSupply.supply_date.between(start_dt, end_dt),
                            WBSupply.fact_date.between(start_dt, end_dt),
                            WBSupply.create_date.between(start_dt, end_dt),
                            WBSupply.updated_date.between(start_dt, end_dt),
                        ),
                    )
                    .order_by(date_expr.desc().nullslast(), WBSupply.id.desc())
                    .limit(limit)
                )
            ).scalars()
        )
        if not supplies:
            return []
        supply_ids = [supply.id for supply in supplies]
        goods_rows = (
            await session.execute(
                select(
                    WBSupplyGood.supply_fk_id.label("supply_fk_id"),
                    func.sum(func.coalesce(WBSupplyGood.quantity, 0)).label(
                        "planned_qty"
                    ),
                    func.sum(func.coalesce(WBSupplyGood.accepted_quantity, 0)).label(
                        "accepted_qty"
                    ),
                )
                .where(WBSupplyGood.supply_fk_id.in_(supply_ids))
                .group_by(WBSupplyGood.supply_fk_id)
            )
        ).mappings()
        goods_by_supply = {row["supply_fk_id"]: row for row in goods_rows}

        result = []
        for supply in supplies:
            key = self._warehouse_key(
                supply.actual_warehouse_name or supply.warehouse_name
            )
            item = warehouse_map[key]
            item["warehouse_name"] = key
            item["warehouse_id"] = supply.actual_warehouse_id or supply.warehouse_id
            item["supply_count"] += 1
            if supply.status_id not in {5, 6}:
                item["open_supply_count"] += 1
            goods = goods_by_supply.get(supply.id, {})
            planned = self._float(goods.get("planned_qty"))
            accepted = self._float(goods.get("accepted_qty"))
            result.append(
                LogisticsSupplyRow(
                    supply_id=supply.supply_id,
                    preorder_id=supply.preorder_id,
                    warehouse_name=supply.warehouse_name,
                    actual_warehouse_name=supply.actual_warehouse_name,
                    status_id=supply.status_id,
                    status_label=SUPPLY_STATUS_LABELS.get(
                        int(supply.status_id or 0), "Неизвестно"
                    ),
                    supply_date=supply.supply_date,
                    fact_date=supply.fact_date,
                    planned_qty=planned,
                    accepted_qty=accepted,
                    gap_qty=max(planned - accepted, 0),
                    box_type_id=supply.box_type_id,
                    last_enriched_at=supply.last_enriched_at,
                )
            )
        return result

    async def _region_demand(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
    ) -> dict[str, dict[str, float | str | None]]:
        stmt = (
            select(
                WBRegionSalesDaily.region_name.label("region_name"),
                WBRegionSalesDaily.federal_district.label("federal_district"),
                WBRegionSalesDaily.country_name.label("country_name"),
                func.sum(func.coalesce(WBRegionSalesDaily.sale_quantity, 0)).label(
                    "sales_qty"
                ),
                func.sum(func.coalesce(WBRegionSalesDaily.sale_amount, 0)).label(
                    "sales_amount"
                ),
            )
            .where(
                WBRegionSalesDaily.account_id == account_id,
                WBRegionSalesDaily.stat_date >= start,
                WBRegionSalesDaily.stat_date <= end,
            )
            .group_by(
                WBRegionSalesDaily.region_name,
                WBRegionSalesDaily.federal_district,
                WBRegionSalesDaily.country_name,
            )
        )
        raw_rows = list((await session.execute(stmt)).mappings())
        total_qty = sum(self._float(row["sales_qty"]) for row in raw_rows)
        demand: dict[str, dict[str, float | str | None]] = {}
        for row in raw_rows:
            qty = self._float(row["sales_qty"])
            amount = self._float(row["sales_amount"])
            for name in (
                row["region_name"],
                row["federal_district"],
                row["country_name"],
            ):
                key = self._region_key(name)
                if not key:
                    continue
                entry = demand.setdefault(
                    key,
                    {
                        "name": str(name),
                        "sales_qty": 0.0,
                        "sales_amount": 0.0,
                        "share_percent": None,
                    },
                )
                entry["sales_qty"] = self._float(entry["sales_qty"]) + qty
                entry["sales_amount"] = self._float(entry["sales_amount"]) + amount
        for entry in demand.values():
            entry["share_percent"] = self._ratio(
                self._float(entry["sales_qty"]), total_qty
            )
        return demand

    async def _products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        day_count: int,
        warehouse_rows: list[LogisticsWarehouseRow],
        search_norm: str,
        limit: int,
        latest_stock_at: datetime | None,
        closed_finance_date_to: date | None,
    ) -> list[LogisticsProductRow]:
        product_map: dict[str, dict[str, Any]] = defaultdict(self._empty_product)
        region_by_warehouse = {
            row.warehouse_name: row.region_name for row in warehouse_rows
        }
        await self._merge_product_orders(
            session,
            account_id=account_id,
            start=start,
            end=end,
            product_map=product_map,
        )
        await self._merge_product_sales(
            session,
            account_id=account_id,
            start=start,
            end=end,
            closed_finance_date_to=closed_finance_date_to,
            product_map=product_map,
        )
        await self._merge_product_finance(
            session,
            account_id=account_id,
            start=start,
            end=end,
            product_map=product_map,
        )
        await self._merge_product_stock(
            session,
            account_id=account_id,
            latest_stock_at=latest_stock_at,
            product_map=product_map,
        )

        result = []
        for item in product_map.values():
            warehouse_name = item.get("warehouse_name")
            if not warehouse_name:
                continue
            item["region_name"] = item.get("region_name") or region_by_warehouse.get(
                str(warehouse_name)
            )
            row = self._product_row(item, day_count=day_count)
            haystack = " ".join(
                str(value or "")
                for value in (
                    row.warehouse_name,
                    row.region_name,
                    row.nm_id,
                    row.vendor_code,
                    row.barcode,
                    row.title,
                    row.brand,
                    row.subject_name,
                )
            ).casefold()
            if search_norm and search_norm not in haystack:
                continue
            result.append(row)
        result.sort(
            key=lambda row: (
                self._risk_sort(row.risk_level),
                -max(row.expected_net_effect, 0),
                -row.recommended_supply_30,
                -row.revenue,
                row.warehouse_name,
                row.nm_id or 0,
            )
        )
        return result[:limit]

    @staticmethod
    def _empty_product() -> dict[str, Any]:
        return {
            "warehouse_name": "",
            "region_name": None,
            "nm_id": None,
            "vendor_code": None,
            "barcode": None,
            "title": None,
            "brand": None,
            "subject_name": None,
            "stock_units": 0.0,
            "in_way_to_client": 0.0,
            "in_way_from_client": 0.0,
            "orders_qty": 0.0,
            "cancelled_orders_qty": 0.0,
            "cancelled_revenue": 0.0,
            "sales_qty": 0.0,
            "sales_revenue": 0.0,
            "sales_for_pay": 0.0,
            "finance_revenue": 0.0,
            "finance_for_pay": 0.0,
            "finance_rows": 0,
            "finance_money_rows": 0,
            "logistics_cost": 0.0,
            "storage_cost": 0.0,
            "acceptance_cost": 0.0,
            "return_logistics_cost": 0.0,
        }

    def _product_entry(
        self,
        product_map: dict[str, dict[str, Any]],
        *,
        warehouse_name: str | None,
        nm_id: int | None = None,
        barcode: str | None = None,
        vendor_code: str | None = None,
    ) -> dict[str, Any]:
        warehouse = self._warehouse_key(warehouse_name)
        product_key = str(nm_id or barcode or vendor_code or "unknown")
        key = f"{warehouse}|{product_key}"
        item = product_map[key]
        item["warehouse_name"] = warehouse
        if nm_id is not None:
            item["nm_id"] = nm_id
        if barcode and not item.get("barcode"):
            item["barcode"] = str(barcode)
        if vendor_code and not item.get("vendor_code"):
            item["vendor_code"] = str(vendor_code)
        return item

    async def _merge_product_orders(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        product_map: dict[str, dict[str, Any]],
    ) -> None:
        start_dt, end_dt = self._date_bounds(start, end)
        orders_current = orders_current_subquery("logistics_product_orders_current")
        cancelled_in_period = and_(
            orders_current.c.is_cancel.is_(True),
            orders_current.c.cancel_date.is_not(None),
            orders_current.c.cancel_date >= start_dt,
            orders_current.c.cancel_date < end_dt,
        )
        value_expr = func.coalesce(
            orders_current.c.finished_price,
            orders_current.c.price_with_disc,
            orders_current.c.total_price,
            0,
        )
        stmt = (
            select(
                orders_current.c.warehouse_name.label("warehouse_name"),
                orders_current.c.nm_id.label("nm_id"),
                orders_current.c.supplier_article.label("vendor_code"),
                orders_current.c.barcode.label("barcode"),
                orders_current.c.oblast_okrug_name.label("region_name"),
                func.count(orders_current.c.id).label("orders_qty"),
                func.sum(case((cancelled_in_period, 1), else_=0)).label(
                    "cancelled_orders_qty"
                ),
                func.sum(case((cancelled_in_period, value_expr), else_=0)).label(
                    "cancelled_revenue"
                ),
            )
            .where(
                orders_current.c.account_id == account_id,
                orders_current.c.date.is_not(None),
                orders_current.c.date >= start_dt,
                orders_current.c.date < end_dt,
            )
            .group_by(
                orders_current.c.warehouse_name,
                orders_current.c.nm_id,
                orders_current.c.supplier_article,
                orders_current.c.barcode,
                orders_current.c.oblast_okrug_name,
            )
        )
        for row in (await session.execute(stmt)).mappings():
            item = self._product_entry(
                product_map,
                warehouse_name=row["warehouse_name"],
                nm_id=row["nm_id"],
                barcode=row["barcode"],
                vendor_code=row["vendor_code"],
            )
            item["region_name"] = item.get("region_name") or row["region_name"]
            item["orders_qty"] += self._float(row["orders_qty"])
            item["cancelled_orders_qty"] += self._float(row["cancelled_orders_qty"])
            item["cancelled_revenue"] += self._float(row["cancelled_revenue"])

    async def _merge_product_sales(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        closed_finance_date_to: date | None,
        product_map: dict[str, dict[str, Any]],
    ) -> None:
        sales_start = self._operational_sales_start(
            start=start, closed_finance_date_to=closed_finance_date_to
        )
        if sales_start > end:
            return
        start_dt, end_dt = self._date_bounds(sales_start, end)
        sales_current = sales_current_subquery("logistics_product_sales_current")
        value_expr = func.coalesce(
            sales_current.c.finished_price,
            sales_current.c.price_with_disc,
            sales_current.c.total_price,
            0,
        )
        for_pay_expr = func.coalesce(sales_current.c.for_pay, 0)
        sale_return_condition = self._sale_return_condition(sales_current)
        positive_sale_expr = case((sale_return_condition, 0), else_=1)
        stmt = (
            select(
                sales_current.c.warehouse_name.label("warehouse_name"),
                sales_current.c.nm_id.label("nm_id"),
                sales_current.c.supplier_article.label("vendor_code"),
                sales_current.c.barcode.label("barcode"),
                func.max(sales_current.c.brand).label("brand"),
                func.max(sales_current.c.subject).label("subject_name"),
                func.sum(positive_sale_expr).label("sales_qty"),
                func.sum(self._signed_sale_sql_expr(value_expr, sales_current)).label(
                    "revenue"
                ),
                func.sum(self._signed_sale_sql_expr(for_pay_expr, sales_current)).label(
                    "for_pay"
                ),
            )
            .where(
                sales_current.c.account_id == account_id,
                sales_current.c.date.is_not(None),
                sales_current.c.date >= start_dt,
                sales_current.c.date < end_dt,
            )
            .group_by(
                sales_current.c.warehouse_name,
                sales_current.c.nm_id,
                sales_current.c.supplier_article,
                sales_current.c.barcode,
            )
        )
        for row in (await session.execute(stmt)).mappings():
            item = self._product_entry(
                product_map,
                warehouse_name=row["warehouse_name"],
                nm_id=row["nm_id"],
                barcode=row["barcode"],
                vendor_code=row["vendor_code"],
            )
            item["brand"] = item.get("brand") or row["brand"]
            item["subject_name"] = item.get("subject_name") or row["subject_name"]
            item["sales_qty"] += self._float(row["sales_qty"])
            item["sales_revenue"] += self._float(row["revenue"])
            item["sales_for_pay"] += self._float(row["for_pay"])

    async def _merge_product_finance(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        product_map: dict[str, dict[str, Any]],
    ) -> None:
        mart_service, core_index = await self._core_sku_matcher(
            session, account_id=account_id
        )
        rows = list(
            (
                await session.execute(
                    select(WBRealizationReportRow).where(
                        WBRealizationReportRow.account_id == account_id,
                        self._finance_period_filter(start=start, end=end),
                    )
                )
            ).scalars()
        )
        for row in rows:
            if not self._finance_row_resolves_to_core_sku(
                row, mart_service=mart_service, core_index=core_index
            ):
                continue
            finance_barcode = mart_service._finance_row_barcode(row)
            item = self._product_entry(
                product_map,
                warehouse_name=row.office_name,
                nm_id=row.nm_id,
                barcode=finance_barcode,
                vendor_code=row.vendor_code,
            )
            item["title"] = item.get("title") or row.title
            item["brand"] = item.get("brand") or row.brand
            item["subject_name"] = item.get("subject_name") or row.subject_name
            item["finance_rows"] += 1
            item["logistics_cost"] += self._float(row.delivery_service)
            item["return_logistics_cost"] += self._float(row.rebill_logistic_cost)
            item["storage_cost"] += self._float(row.paid_storage)
            item["acceptance_cost"] += self._float(row.paid_acceptance)
            if not self._is_reconcilable_finance_row(row):
                continue
            revenue = self._signed_finance_amount(row, row.retail_amount)
            for_pay = self._signed_finance_amount(row, row.for_pay)
            if revenue != 0 or for_pay != 0:
                item["finance_money_rows"] += 1
            if self._finance_row_sign(row) > 0:
                item["sales_qty"] += self._float(row.quantity or 1)
            item["finance_revenue"] += self._float(revenue)
            item["finance_for_pay"] += self._float(for_pay)

    async def _merge_product_stock(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        latest_stock_at: datetime | None,
        product_map: dict[str, dict[str, Any]],
    ) -> None:
        if latest_stock_at is None:
            return
        snapshot_id = (
            await session.execute(
                select(WBStockSnapshot.id)
                .where(
                    WBStockSnapshot.account_id == account_id,
                    WBStockSnapshot.snapshot_at == latest_stock_at,
                )
                .order_by(WBStockSnapshot.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if snapshot_id is None:
            return
        rows = (
            (
                await session.execute(
                    select(WBStockSnapshotRow).where(
                        WBStockSnapshotRow.snapshot_id == snapshot_id,
                        WBStockSnapshotRow.account_id == account_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            warehouse = self._warehouse_key(row.warehouse_name)
            if warehouse in SPECIAL_STOCK_WAREHOUSES:
                continue
            item = self._product_entry(
                product_map,
                warehouse_name=warehouse,
                nm_id=row.nm_id,
                barcode=row.barcode,
            )
            item["brand"] = item.get("brand") or row.brand
            item["subject_name"] = item.get("subject_name") or row.subject
            item["stock_units"] += self._float(row.quantity) or self._float(
                row.quantity_full
            )
            item["in_way_to_client"] += self._float(row.in_way_to_client)
            item["in_way_from_client"] += self._float(row.in_way_from_client)

    @staticmethod
    def _revenue_source(*, has_finance_money: bool, has_sales_money: bool) -> str:
        if has_finance_money and has_sales_money:
            return "finance+sales"
        if has_finance_money:
            return "finance"
        return "sales"

    def _product_row(
        self,
        item: dict[str, Any],
        *,
        day_count: int,
    ) -> LogisticsProductRow:
        orders_qty = self._float(item["orders_qty"])
        sales_qty = self._float(item["sales_qty"])
        finance_revenue = self._float(item["finance_revenue"])
        finance_for_pay = self._float(item["finance_for_pay"])
        sales_revenue = self._float(item["sales_revenue"])
        sales_for_pay = self._float(item["sales_for_pay"])
        has_finance_money = int(item.get("finance_money_rows") or 0) > 0
        has_sales_money = bool(sales_revenue or sales_for_pay)
        revenue = (
            finance_revenue + sales_revenue if has_finance_money else sales_revenue
        )
        for_pay = (
            finance_for_pay + sales_for_pay if has_finance_money else sales_for_pay
        )
        revenue_source = self._revenue_source(
            has_finance_money=has_finance_money, has_sales_money=has_sales_money
        )
        stock_units = self._float(item["stock_units"])
        avg_daily_sales = self._safe_div(sales_qty, day_count)
        turnover_days = stock_units / avg_daily_sales if avg_daily_sales > 0 else None
        supply_14 = max(round(avg_daily_sales * OOS_FAST_DAYS - stock_units), 0)
        supply_30 = max(round(avg_daily_sales * OOS_PLANNING_DAYS - stock_units), 0)
        logistics_total = (
            self._float(item["logistics_cost"])
            + self._float(item["return_logistics_cost"])
            + self._float(item["storage_cost"])
            + self._float(item["acceptance_cost"])
        )
        avg_order_value = self._safe_div(revenue, sales_qty or orders_qty)
        potential_orders = max(
            self._float(item["cancelled_orders_qty"]),
            min(supply_14, avg_daily_sales * 7) if supply_14 else 0,
        )
        potential_revenue = max(
            self._float(item["cancelled_revenue"]),
            potential_orders * avg_order_value,
        )
        margin_percent = self._ratio(for_pay - logistics_total, revenue)
        margin_factor = (
            max((margin_percent or 0) / 100, 0.05)
            if margin_percent is not None
            else 0.35
        )
        logistics_per_sale = self._safe_div(logistics_total, sales_qty)
        expected_net = potential_revenue * margin_factor - logistics_per_sale * max(
            supply_14,
            potential_orders,
        )
        buyout = self._ratio(sales_qty, orders_qty)
        logistics_share = self._ratio(logistics_total, revenue)
        risk_level, reason = self._product_risk(
            stock_units=stock_units,
            turnover_days=turnover_days,
            cancelled_orders=self._float(item["cancelled_orders_qty"]),
            logistics_share=logistics_share,
            buyout=buyout,
            orders_qty=orders_qty,
        )
        tags = self._product_tags(
            risk_level=risk_level,
            stock_units=stock_units,
            turnover_days=turnover_days,
            buyout=buyout,
            logistics_share=logistics_share,
            cancelled_orders=self._float(item["cancelled_orders_qty"]),
        )
        product_id = item.get("nm_id") or item.get("barcode") or item.get("vendor_code")
        return LogisticsProductRow(
            id=f"product:{self._slug(str(item['warehouse_name']))}:{product_id or 'unknown'}",
            nm_id=item.get("nm_id"),
            vendor_code=item.get("vendor_code"),
            barcode=item.get("barcode"),
            title=item.get("title"),
            brand=item.get("brand"),
            subject_name=item.get("subject_name"),
            warehouse_name=str(item["warehouse_name"]),
            region_name=item.get("region_name"),
            stock_units=stock_units,
            in_way_to_client=self._float(item["in_way_to_client"]),
            in_way_from_client=self._float(item["in_way_from_client"]),
            orders_qty=orders_qty,
            sales_qty=sales_qty,
            cancelled_orders_qty=self._float(item["cancelled_orders_qty"]),
            cancelled_revenue=self._float(item["cancelled_revenue"]),
            revenue=revenue,
            for_pay=for_pay,
            revenue_source=revenue_source,
            finance_rows=int(item["finance_rows"] or 0),
            logistics_cost=self._float(item["logistics_cost"]),
            storage_cost=self._float(item["storage_cost"]),
            acceptance_cost=self._float(item["acceptance_cost"]),
            return_logistics_cost=self._float(item["return_logistics_cost"]),
            buyout_percent=buyout,
            logistics_share_percent=logistics_share,
            margin_percent=margin_percent,
            avg_daily_sales=avg_daily_sales,
            turnover_days=turnover_days,
            recommended_supply_14=supply_14,
            recommended_supply_30=supply_30,
            potential_orders_qty=potential_orders,
            potential_revenue=potential_revenue,
            expected_net_effect=expected_net,
            risk_level=risk_level,
            reason=reason,
            tags=tags,
        )

    @staticmethod
    def _product_risk(
        *,
        stock_units: float,
        turnover_days: float | None,
        cancelled_orders: float,
        logistics_share: float | None,
        buyout: float | None,
        orders_qty: float,
    ) -> tuple[str, str | None]:
        if stock_units <= 0 and (cancelled_orders > 0 or orders_qty > 0):
            return "danger", "SKU закончился на складе: нужен быстрый довоз."
        if turnover_days is not None and turnover_days < OOS_FAST_DAYS:
            return "warning", "Остатка меньше логистического плеча 14 дней."
        if logistics_share is not None and logistics_share >= 25:
            return "warning", "Высокая доля логистики по SKU."
        if buyout is not None and buyout < 70 and orders_qty >= 20:
            return "warning", "Низкий процент выкупа по SKU."
        if turnover_days is not None and turnover_days > 90:
            return "watch", "Низкая оборачиваемость и риск заморозки денег."
        return "ok", None

    @staticmethod
    def _product_tags(
        *,
        risk_level: str,
        stock_units: float,
        turnover_days: float | None,
        buyout: float | None,
        logistics_share: float | None,
        cancelled_orders: float,
    ) -> list[str]:
        tags = []
        if stock_units <= 0:
            tags.append("OOS")
        if turnover_days is not None and turnover_days < OOS_FAST_DAYS:
            tags.append("14 дней")
        if turnover_days is not None and turnover_days < OOS_PLANNING_DAYS:
            tags.append("30 дней")
        if cancelled_orders:
            tags.append("отмены")
        if logistics_share is not None and logistics_share >= 20:
            tags.append("логистика")
        if buyout is not None and buyout < 70:
            tags.append("выкуп")
        if risk_level == "watch":
            tags.append("оборачиваемость")
        return tags or ["норма"]

    def _warehouse_row(
        self,
        item: dict[str, Any],
        *,
        day_count: int,
        region_demand: dict[str, dict[str, float | str | None]] | None = None,
    ) -> LogisticsWarehouseRow:
        orders_qty = self._float(item["orders_qty"])
        sales_qty = self._float(item["sales_qty"])
        finance_revenue = self._float(item["finance_revenue"])
        finance_for_pay = self._float(item["finance_for_pay"])
        sales_revenue = self._float(item["sales_revenue"])
        sales_for_pay = self._float(item["sales_for_pay"])
        has_finance_money = int(item.get("finance_money_rows") or 0) > 0
        has_sales_money = bool(sales_revenue or sales_for_pay)
        revenue = (
            finance_revenue + sales_revenue if has_finance_money else sales_revenue
        )
        for_pay = (
            finance_for_pay + sales_for_pay if has_finance_money else sales_for_pay
        )
        revenue_source = self._revenue_source(
            has_finance_money=has_finance_money, has_sales_money=has_sales_money
        )
        logistics_total = (
            self._float(item["logistics_cost"])
            + self._float(item["return_logistics_cost"])
            + self._float(item["storage_cost"])
            + self._float(item["acceptance_cost"])
        )
        stock_units = self._float(item["stock_units"])
        avg_daily_sales = sales_qty / day_count if day_count else 0
        turnover_days = stock_units / avg_daily_sales if avg_daily_sales > 0 else None
        logistics_share = self._ratio(logistics_total, revenue)
        margin = self._ratio(for_pay - logistics_total, revenue)
        buyout = self._ratio(sales_qty, orders_qty)
        acceptance_status = self._acceptance_status(
            item.get("acceptance_coefficient"), item.get("allow_unload")
        )
        cancelled_orders = self._float(item["cancelled_orders_qty"])
        cancelled_revenue = self._float(item["cancelled_revenue"])
        cancel_has_logistics_risk = (
            stock_units <= 0
            or (turnover_days is not None and turnover_days < OOS_FAST_DAYS)
            or acceptance_status == "closed"
        )
        missed_orders = cancelled_orders if cancel_has_logistics_risk else 0.0
        missed_revenue = cancelled_revenue if cancel_has_logistics_risk else 0.0
        demand = self._region_demand_for_name(item.get("region_name"), region_demand)
        risk_level, recommendation = self._row_risk(
            stock_units=stock_units,
            turnover_days=turnover_days,
            missed_orders=missed_orders,
            logistics_share=logistics_share,
            acceptance_status=acceptance_status,
        )
        return LogisticsWarehouseRow(
            warehouse_name=str(item["warehouse_name"]),
            warehouse_id=item.get("warehouse_id"),
            region_name=item.get("region_name"),
            stock_units=stock_units,
            in_way_to_client=self._float(item["in_way_to_client"]),
            in_way_from_client=self._float(item["in_way_from_client"]),
            orders_qty=orders_qty,
            sales_qty=sales_qty,
            revenue=revenue,
            for_pay=for_pay,
            revenue_source=revenue_source,
            finance_rows=int(item["finance_rows"] or 0),
            logistics_cost=self._float(item["logistics_cost"]),
            storage_cost=self._float(item["storage_cost"]),
            acceptance_cost=self._float(item["acceptance_cost"]),
            return_logistics_cost=self._float(item["return_logistics_cost"]),
            cancelled_orders_qty=cancelled_orders,
            cancelled_revenue=cancelled_revenue,
            missed_orders_qty=missed_orders,
            missed_revenue=missed_revenue,
            buyout_percent=buyout,
            logistics_share_percent=logistics_share,
            margin_percent=margin,
            turnover_days=turnover_days,
            acceptance_coefficient=item.get("acceptance_coefficient"),
            acceptance_status=acceptance_status,
            allow_unload=item.get("allow_unload"),
            acceptance_next_available_at=item.get("acceptance_next_available_at"),
            acceptance_box_type_id=item.get("acceptance_box_type_id"),
            box_type_ids=sorted(item.get("box_type_ids") or []),
            delivery_base=item.get("delivery_base"),
            delivery_liter=item.get("delivery_liter"),
            storage_base=item.get("storage_base"),
            region_sales_qty=self._float(demand.get("sales_qty")),
            region_sales_amount=self._float(demand.get("sales_amount")),
            region_sales_share_percent=demand.get("share_percent"),
            supply_count=int(item["supply_count"] or 0),
            open_supply_count=int(item["open_supply_count"] or 0),
            risk_level=risk_level,
            recommendation=recommendation,
        )

    def _acceptance_option(self, row: WBTariffAcceptance) -> dict[str, Any]:
        status = self._acceptance_status(row.coefficient, row.allow_unload)
        numeric = self._parse_number(row.coefficient)
        payload = row.payload or {}
        box_type_id = payload.get("boxTypeID") or payload.get("boxTypeId")
        try:
            parsed_box_type_id = int(box_type_id) if box_type_id is not None else None
        except Exception:
            parsed_box_type_id = None
        option_date = self._parse_payload_date(
            payload,
            (
                "date",
                "acceptanceDate",
                "deliveryDate",
                "warehouseDate",
                "coefficientDate",
            ),
        )
        priority = {"available": 0, "expensive": 1, "closed": 2, "unknown": 3}.get(
            status, 3
        )
        numeric_sort = numeric if numeric is not None else 9999.0
        date_sort = option_date or date.max
        return {
            "status": status,
            "coefficient": row.coefficient,
            "allow_unload": row.allow_unload,
            "date": option_date,
            "box_type_id": parsed_box_type_id,
            "sort_key": (priority, numeric_sort, date_sort),
        }

    @staticmethod
    def _parse_payload_date(
        payload: dict[str, Any], keys: tuple[str, ...]
    ) -> date | None:
        for key in keys:
            value = payload.get(key)
            if value is None:
                continue
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            text = str(value).strip()
            if not text:
                continue
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
            except ValueError:
                try:
                    return date.fromisoformat(text[:10])
                except ValueError:
                    continue
        return None

    @staticmethod
    def _acceptance_status(coefficient: str | None, allow_unload: bool | None) -> str:
        if coefficient is None and allow_unload is None:
            return "unknown"
        if allow_unload is False:
            return "closed"
        try:
            numeric = float(str(coefficient).replace(",", "."))
        except Exception:
            numeric = None
        if allow_unload is True and numeric is not None and numeric <= 1:
            return "available"
        if allow_unload is True and numeric is not None and numeric > 1:
            return "expensive"
        return "unknown"

    @staticmethod
    def _row_risk(
        *,
        stock_units: float,
        turnover_days: float | None,
        missed_orders: float,
        logistics_share: float | None,
        acceptance_status: str,
    ) -> tuple[str, str | None]:
        if stock_units <= 0 and missed_orders > 0:
            return (
                "danger",
                "Нет остатка при отменённых заказах: нужен быстрый план поставки.",
            )
        if acceptance_status == "closed":
            return "danger", "Приёмка закрыта: ищем альтернативный склад или дату."
        if logistics_share is not None and logistics_share >= 25:
            return (
                "warning",
                "Логистика забирает высокую долю выручки: проверьте склад и габариты.",
            )
        if turnover_days is not None and turnover_days < 7:
            return "warning", "Запас меньше недели: есть риск out-of-stock."
        if turnover_days is not None and turnover_days > 90:
            return "watch", "Большой запас: проверьте заморозку денег и хранение."
        if acceptance_status == "expensive":
            return (
                "watch",
                "Коэффициент приёмки повышен: лучше дождаться выгодного слота.",
            )
        return "ok", None

    def _kpis(
        self,
        rows: list[LogisticsWarehouseRow],
        *,
        stock_totals: dict[str, float] | None = None,
    ) -> LogisticsKpis:
        orders = sum(row.orders_qty for row in rows)
        sales = sum(row.sales_qty for row in rows)
        revenue = sum(row.revenue for row in rows)
        logistics = sum(row.logistics_cost for row in rows)
        return_logistics = sum(row.return_logistics_cost for row in rows)
        storage = sum(row.storage_cost for row in rows)
        acceptance = sum(row.acceptance_cost for row in rows)
        logistics_total = logistics + return_logistics + storage + acceptance
        for_pay = sum(row.for_pay for row in rows)
        return LogisticsKpis(
            orders_qty=orders,
            sales_qty=sales,
            revenue=revenue,
            for_pay=for_pay,
            logistics_cost=logistics,
            storage_cost=storage,
            acceptance_cost=acceptance,
            return_logistics_cost=return_logistics,
            missed_orders_qty=sum(row.missed_orders_qty for row in rows),
            missed_revenue=sum(row.missed_revenue for row in rows),
            cancelled_orders_qty=sum(row.cancelled_orders_qty for row in rows),
            cancelled_revenue=sum(row.cancelled_revenue for row in rows),
            stock_units=sum(row.stock_units for row in rows),
            in_way_to_client=(
                stock_totals.get("in_way_to_client", 0.0)
                if stock_totals is not None
                else sum(row.in_way_to_client for row in rows)
            ),
            in_way_from_client=(
                stock_totals.get("in_way_from_client", 0.0)
                if stock_totals is not None
                else sum(row.in_way_from_client for row in rows)
            ),
            active_warehouses=len(
                [
                    row
                    for row in rows
                    if row.stock_units or row.orders_qty or row.sales_qty
                ]
            ),
            risky_warehouses=len(
                [row for row in rows if row.risk_level in {"danger", "warning"}]
            ),
            available_acceptance_slots=len(
                [row for row in rows if row.acceptance_status == "available"]
            ),
            avg_logistics_per_order=(logistics_total / orders) if orders else None,
            logistics_share_percent=self._ratio(logistics_total, revenue),
            buyout_percent=self._ratio(sales, orders),
            margin_percent=self._ratio(for_pay - logistics_total, revenue),
        )

    async def _detail_kpi_totals(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
    ) -> dict[str, float | int]:
        paid_amount_expr = func.coalesce(
            WBLogisticsPaidStorageRow.storage_cost,
            WBLogisticsPaidStorageRow.amount,
            0,
        )
        paid = (
            (
                await session.execute(
                    select(
                        func.count(WBLogisticsPaidStorageRow.id).label("rows"),
                        func.coalesce(func.sum(paid_amount_expr), 0).label("amount"),
                    ).where(
                        WBLogisticsPaidStorageRow.account_id == account_id,
                        WBLogisticsPaidStorageRow.report_date >= start,
                        WBLogisticsPaidStorageRow.report_date <= end,
                    )
                )
            )
            .mappings()
            .one()
        )

        acceptance_amount_expr = func.coalesce(
            WBLogisticsAcceptanceReportRow.acceptance_cost,
            WBLogisticsAcceptanceReportRow.amount,
            0,
        )
        acceptance = (
            (
                await session.execute(
                    select(
                        func.count(WBLogisticsAcceptanceReportRow.id).label("rows"),
                        func.coalesce(func.sum(acceptance_amount_expr), 0).label(
                            "amount"
                        ),
                    ).where(
                        WBLogisticsAcceptanceReportRow.account_id == account_id,
                        WBLogisticsAcceptanceReportRow.operation_date >= start,
                        WBLogisticsAcceptanceReportRow.operation_date <= end,
                    )
                )
            )
            .mappings()
            .one()
        )

        latest_transit_at = (
            await session.execute(
                select(func.max(WBLogisticsTransitTariff.collected_at)).where(
                    WBLogisticsTransitTariff.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        transit_route_count = 0
        if latest_transit_at is not None:
            transit_route_count = int(
                (
                    await session.execute(
                        select(func.count(WBLogisticsTransitTariff.id)).where(
                            WBLogisticsTransitTariff.account_id == account_id,
                            WBLogisticsTransitTariff.collected_at == latest_transit_at,
                        )
                    )
                ).scalar_one()
                or 0
            )

        seller_warehouse_count = int(
            (
                await session.execute(
                    select(func.count(WBSellerWarehouse.id)).where(
                        WBSellerWarehouse.account_id == account_id
                    )
                )
            ).scalar_one()
            or 0
        )
        seller_stock_units = self._float(
            (
                await session.execute(
                    select(
                        func.coalesce(
                            func.sum(func.coalesce(WBSellerWarehouseStock.quantity, 0)),
                            0,
                        )
                    ).where(WBSellerWarehouseStock.account_id == account_id)
                )
            ).scalar_one_or_none()
        )

        return {
            "paid_storage_detail_cost": self._float(paid["amount"]),
            "paid_storage_detail_rows": int(paid["rows"] or 0),
            "acceptance_detail_cost": self._float(acceptance["amount"]),
            "acceptance_detail_rows": int(acceptance["rows"] or 0),
            "transit_route_count": transit_route_count,
            "seller_warehouse_count": seller_warehouse_count,
            "seller_stock_units": seller_stock_units,
        }

    @staticmethod
    def _augment_kpis_with_details(
        kpis: LogisticsKpis, *, detail_totals: dict[str, float | int]
    ) -> None:
        kpis.paid_storage_detail_cost = float(
            detail_totals.get("paid_storage_detail_cost") or 0
        )
        kpis.paid_storage_detail_rows = int(
            detail_totals.get("paid_storage_detail_rows") or 0
        )
        kpis.acceptance_detail_cost = float(
            detail_totals.get("acceptance_detail_cost") or 0
        )
        kpis.acceptance_detail_rows = int(
            detail_totals.get("acceptance_detail_rows") or 0
        )
        kpis.transit_route_count = int(detail_totals.get("transit_route_count") or 0)
        kpis.seller_warehouse_count = int(
            detail_totals.get("seller_warehouse_count") or 0
        )
        kpis.seller_stock_units = float(detail_totals.get("seller_stock_units") or 0)

    async def _paid_storage_details(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        limit: int,
    ) -> list[LogisticsPaidStorageDetailRow]:
        amount_expr = func.coalesce(
            WBLogisticsPaidStorageRow.storage_cost,
            WBLogisticsPaidStorageRow.amount,
            0,
        )
        total = self._float(
            (
                await session.execute(
                    select(func.sum(amount_expr)).where(
                        WBLogisticsPaidStorageRow.account_id == account_id,
                        WBLogisticsPaidStorageRow.report_date >= start,
                        WBLogisticsPaidStorageRow.report_date <= end,
                    )
                )
            ).scalar_one_or_none()
        )
        rows = list(
            (
                await session.execute(
                    select(WBLogisticsPaidStorageRow)
                    .where(
                        WBLogisticsPaidStorageRow.account_id == account_id,
                        WBLogisticsPaidStorageRow.report_date >= start,
                        WBLogisticsPaidStorageRow.report_date <= end,
                    )
                    .order_by(amount_expr.desc(), WBLogisticsPaidStorageRow.id.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        result: list[LogisticsPaidStorageDetailRow] = []
        for row in rows:
            amount = self._float(
                row.storage_cost if row.storage_cost is not None else row.amount
            )
            quantity = self._float(row.quantity)
            result.append(
                LogisticsPaidStorageDetailRow(
                    id=int(row.id),
                    report_date=row.report_date,
                    warehouse_name=row.warehouse_name,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    barcode=row.barcode,
                    title=row.title,
                    brand=row.brand,
                    subject_name=row.subject_name,
                    quantity=quantity,
                    amount=amount,
                    amount_per_unit=(amount / quantity) if quantity else None,
                    share_percent=self._ratio(amount, total),
                    task_id=row.task_id,
                    source_row_key=row.source_row_key,
                )
            )
        return result

    async def _acceptance_details(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        limit: int,
    ) -> list[LogisticsAcceptanceDetailRow]:
        amount_expr = func.coalesce(
            WBLogisticsAcceptanceReportRow.acceptance_cost,
            WBLogisticsAcceptanceReportRow.amount,
            0,
        )
        total = self._float(
            (
                await session.execute(
                    select(func.sum(amount_expr)).where(
                        WBLogisticsAcceptanceReportRow.account_id == account_id,
                        WBLogisticsAcceptanceReportRow.operation_date >= start,
                        WBLogisticsAcceptanceReportRow.operation_date <= end,
                    )
                )
            ).scalar_one_or_none()
        )
        rows = list(
            (
                await session.execute(
                    select(WBLogisticsAcceptanceReportRow)
                    .where(
                        WBLogisticsAcceptanceReportRow.account_id == account_id,
                        WBLogisticsAcceptanceReportRow.operation_date >= start,
                        WBLogisticsAcceptanceReportRow.operation_date <= end,
                    )
                    .order_by(
                        amount_expr.desc(), WBLogisticsAcceptanceReportRow.id.desc()
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        result: list[LogisticsAcceptanceDetailRow] = []
        for row in rows:
            amount = self._float(
                row.acceptance_cost if row.acceptance_cost is not None else row.amount
            )
            quantity = self._float(row.quantity)
            result.append(
                LogisticsAcceptanceDetailRow(
                    id=int(row.id),
                    operation_date=row.operation_date,
                    warehouse_name=row.warehouse_name,
                    operation_name=row.operation_name,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    barcode=row.barcode,
                    title=row.title,
                    brand=row.brand,
                    subject_name=row.subject_name,
                    quantity=quantity,
                    amount=amount,
                    amount_per_unit=(amount / quantity) if quantity else None,
                    share_percent=self._ratio(amount, total),
                    task_id=row.task_id,
                    source_row_key=row.source_row_key,
                )
            )
        return result

    async def _transit_tariffs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        limit: int,
    ) -> list[LogisticsTransitTariffRow]:
        latest_at = (
            await session.execute(
                select(func.max(WBLogisticsTransitTariff.collected_at)).where(
                    WBLogisticsTransitTariff.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        if latest_at is None:
            return []
        rows = list(
            (
                await session.execute(
                    select(WBLogisticsTransitTariff)
                    .where(
                        WBLogisticsTransitTariff.account_id == account_id,
                        WBLogisticsTransitTariff.collected_at == latest_at,
                    )
                    .order_by(
                        func.coalesce(WBLogisticsTransitTariff.amount, 0).asc(),
                        WBLogisticsTransitTariff.id.desc(),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        result: list[LogisticsTransitTariffRow] = []
        for row in rows:
            amount = self._float(row.amount)
            days = self._float(row.transit_time_days)
            score = amount + days * 100 if amount or days else None
            result.append(
                LogisticsTransitTariffRow(
                    id=int(row.id),
                    collected_at=row.collected_at,
                    route_label=row.route_label,
                    source_warehouse_id=row.source_warehouse_id,
                    source_warehouse_name=row.source_warehouse_name,
                    transit_warehouse_id=row.transit_warehouse_id,
                    transit_warehouse_name=row.transit_warehouse_name,
                    destination_warehouse_id=row.destination_warehouse_id,
                    destination_warehouse_name=row.destination_warehouse_name,
                    box_type_id=row.box_type_id,
                    coefficient=row.coefficient,
                    delivery_base=(
                        self._float(row.delivery_base)
                        if row.delivery_base is not None
                        else None
                    ),
                    delivery_liter=(
                        self._float(row.delivery_liter)
                        if row.delivery_liter is not None
                        else None
                    ),
                    amount=amount if row.amount is not None else None,
                    currency=row.currency,
                    transit_time_days=days
                    if row.transit_time_days is not None
                    else None,
                    score=score,
                )
            )
        return result

    async def _seller_warehouses(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        limit: int,
    ) -> list[LogisticsSellerWarehouseRow]:
        stock_rows = (
            await session.execute(
                select(
                    WBSellerWarehouseStock.warehouse_id,
                    func.count(WBSellerWarehouseStock.id).label("stock_rows"),
                    func.coalesce(
                        func.sum(func.coalesce(WBSellerWarehouseStock.quantity, 0)), 0
                    ).label("stock_units"),
                    func.max(WBSellerWarehouseStock.updated_at_wb).label(
                        "latest_stock_at"
                    ),
                )
                .where(WBSellerWarehouseStock.account_id == account_id)
                .group_by(WBSellerWarehouseStock.warehouse_id)
            )
        ).mappings()
        stock_by_warehouse = {
            int(row["warehouse_id"]): {
                "stock_rows": int(row["stock_rows"] or 0),
                "stock_units": self._float(row["stock_units"]),
                "latest_stock_at": row["latest_stock_at"],
            }
            for row in stock_rows
        }
        warehouses = list(
            (
                await session.execute(
                    select(WBSellerWarehouse)
                    .where(WBSellerWarehouse.account_id == account_id)
                    .order_by(WBSellerWarehouse.name.asc().nullslast())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        result: list[LogisticsSellerWarehouseRow] = []
        for row in warehouses:
            stock = stock_by_warehouse.get(int(row.warehouse_id), {})
            delivery_type = (
                str(row.delivery_type) if row.delivery_type is not None else None
            )
            result.append(
                LogisticsSellerWarehouseRow(
                    id=int(row.id),
                    warehouse_id=int(row.warehouse_id),
                    name=row.name,
                    office_id=row.office_id,
                    delivery_type=delivery_type,
                    delivery_type_label=self._seller_delivery_type_label(delivery_type),
                    cargo_type=str(row.cargo_type)
                    if row.cargo_type is not None
                    else None,
                    address=row.address,
                    is_active=row.is_active,
                    stock_rows=int(stock.get("stock_rows") or 0),
                    stock_units=self._float(stock.get("stock_units")),
                    latest_stock_at=stock.get("latest_stock_at"),
                )
            )
        return result

    @staticmethod
    def _seller_delivery_type_label(value: str | None) -> str | None:
        if value is None:
            return None
        return {
            "1": "FBS",
            "2": "DBS",
            "3": "DBW курьер",
        }.get(value, value)

    async def _data_sources(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        start: date,
        end: date,
        latest_stock_at: datetime | None,
    ) -> list[LogisticsDataSourceStatus]:
        start_dt, end_dt = self._date_bounds(start, end)
        supply_date_expr = func.coalesce(
            WBSupply.fact_date,
            WBSupply.supply_date,
            WBSupply.updated_date,
            WBSupply.create_date,
        )
        source_specs = [
            (
                "orders",
                "Заказы WB",
                select(func.count(WBOrder.id), func.max(WBOrder.date)).where(
                    WBOrder.account_id == account_id,
                    WBOrder.date >= start_dt,
                    WBOrder.date < end_dt,
                ),
            ),
            (
                "sales",
                "Продажи и возвраты",
                select(func.count(WBSale.id), func.max(WBSale.date)).where(
                    WBSale.account_id == account_id,
                    WBSale.date >= start_dt,
                    WBSale.date < end_dt,
                ),
            ),
            (
                "finance",
                "Финансовый отчёт",
                select(
                    func.count(WBRealizationReportRow.id),
                    func.max(WBRealizationReportRow.rr_date),
                ).where(
                    WBRealizationReportRow.account_id == account_id,
                    self._finance_period_filter(start=start, end=end),
                ),
            ),
            (
                "supplies",
                "Поставки FBO",
                select(func.count(WBSupply.id), func.max(supply_date_expr)).where(
                    WBSupply.account_id == account_id,
                    or_(
                        WBSupply.supply_date.between(start_dt, end_dt),
                        WBSupply.fact_date.between(start_dt, end_dt),
                        WBSupply.create_date.between(start_dt, end_dt),
                        WBSupply.updated_date.between(start_dt, end_dt),
                    ),
                ),
            ),
            (
                "region_sales",
                "Продажи по регионам",
                select(
                    func.count(WBRegionSalesDaily.id),
                    func.max(WBRegionSalesDaily.stat_date),
                ).where(
                    WBRegionSalesDaily.account_id == account_id,
                    WBRegionSalesDaily.stat_date >= start,
                    WBRegionSalesDaily.stat_date <= end,
                ),
            ),
            (
                "tariffs",
                "Тарифы и коэффициенты",
                select(
                    func.count(WBTariffAcceptance.id),
                    func.max(WBTariffAcceptance.collected_at),
                ).where(WBTariffAcceptance.account_id == account_id),
            ),
            (
                "paid_storage_detail",
                "Детализация платного хранения",
                select(
                    func.count(WBLogisticsPaidStorageRow.id),
                    func.max(WBLogisticsPaidStorageRow.report_date),
                ).where(
                    WBLogisticsPaidStorageRow.account_id == account_id,
                    WBLogisticsPaidStorageRow.report_date >= start,
                    WBLogisticsPaidStorageRow.report_date <= end,
                ),
            ),
            (
                "acceptance_detail",
                "Детализация расходов приёмки",
                select(
                    func.count(WBLogisticsAcceptanceReportRow.id),
                    func.max(WBLogisticsAcceptanceReportRow.operation_date),
                ).where(
                    WBLogisticsAcceptanceReportRow.account_id == account_id,
                    WBLogisticsAcceptanceReportRow.operation_date >= start,
                    WBLogisticsAcceptanceReportRow.operation_date <= end,
                ),
            ),
            (
                "transit_tariffs",
                "Транзитные тарифы поставок",
                select(
                    func.count(WBLogisticsTransitTariff.id),
                    func.max(WBLogisticsTransitTariff.collected_at),
                ).where(WBLogisticsTransitTariff.account_id == account_id),
            ),
            (
                "seller_warehouses",
                "Склады продавца FBS/DBW",
                select(
                    func.count(WBSellerWarehouse.id),
                    func.max(WBSellerWarehouse.updated_at),
                ).where(WBSellerWarehouse.account_id == account_id),
            ),
        ]
        result: list[LogisticsDataSourceStatus] = []
        wb_today = utcnow().astimezone(MOSCOW_TZ).date()
        for key, label, stmt in source_specs:
            count_value, latest = (await session.execute(stmt)).one()
            rows = int(count_value or 0)
            status = "ok" if rows else "empty"
            note = None if rows else "Данных пока нет: запустите соответствующий sync."
            if rows and key == "tariffs" and latest is not None:
                latest_date = latest if isinstance(latest, date) else latest.date()
                if latest_date < wb_today - timedelta(days=TARIFF_FRESHNESS_DAYS):
                    status = "stale"
                    note = (
                        "Тарифы устарели: обновите sync перед планированием поставок."
                    )
            result.append(
                LogisticsDataSourceStatus(
                    key=key,
                    label=label,
                    status=status,
                    rows=rows,
                    latest_at=latest,
                    note=note,
                )
            )
        stock_rows = 0
        if latest_stock_at is not None:
            snapshot_id = (
                await session.execute(
                    select(WBStockSnapshot.id)
                    .where(
                        WBStockSnapshot.account_id == account_id,
                        WBStockSnapshot.snapshot_at == latest_stock_at,
                    )
                    .order_by(WBStockSnapshot.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if snapshot_id is not None:
                stock_rows = int(
                    (
                        await session.execute(
                            select(func.count(WBStockSnapshotRow.id)).where(
                                WBStockSnapshotRow.snapshot_id == snapshot_id
                            )
                        )
                    ).scalar_one()
                    or 0
                )
        stock_status = "ok" if stock_rows else "empty"
        stock_note = None if stock_rows else "Нет свежего warehouse remains snapshot."
        if latest_stock_at is not None:
            stock_age_days = (
                utcnow().astimezone(MOSCOW_TZ).date()
                - latest_stock_at.astimezone(MOSCOW_TZ).date()
            ).days
            if stock_age_days > STOCK_FRESHNESS_DAYS:
                stock_status = "stale"
                stock_note = "Остатки устарели: обновите warehouse remains snapshot."
        result.insert(
            2,
            LogisticsDataSourceStatus(
                key="stocks",
                label="Остатки WB по складам",
                status=stock_status,
                rows=stock_rows,
                latest_at=latest_stock_at,
                note=stock_note,
            ),
        )
        return result

    def _recommendations(
        self,
        kpis: LogisticsKpis,
        rows: list[LogisticsWarehouseRow],
        data_sources: list[LogisticsDataSourceStatus],
    ) -> list[LogisticsRecommendation]:
        result: list[LogisticsRecommendation] = []
        missing = [
            source.label
            for source in data_sources
            if source.status in {"empty", "stale"}
        ]
        if missing:
            result.append(
                LogisticsRecommendation(
                    severity="warning",
                    title="Не все источники данных готовы",
                    detail=", ".join(missing),
                    action="Запустите sync по доменам stocks, supplies, tariffs, orders, sales, finance, analytics и logistics.",
                    source="data_sources",
                )
            )
        if kpis.missed_orders_qty:
            result.append(
                LogisticsRecommendation(
                    severity="danger" if kpis.missed_revenue > 100_000 else "warning",
                    title="Есть отменённые или потерянные заказы",
                    detail=f"Потенциально потеряно {kpis.missed_orders_qty:.0f} заказов на {kpis.missed_revenue:.0f}.",
                    action="Откройте склады с красным риском и проверьте запас, плечо доставки и ближайшие слоты приёмки.",
                    source="orders",
                )
            )
        if kpis.logistics_share_percent and kpis.logistics_share_percent >= 20:
            result.append(
                LogisticsRecommendation(
                    severity="warning",
                    title="Высокая доля логистики",
                    detail=f"Логистика, хранение и приёмка занимают {kpis.logistics_share_percent:.1f}% выручки.",
                    action="Сравните склады с высокой долей логистики и перенесите подсортировку в более выгодные регионы.",
                    source="finance",
                )
            )
        no_acceptance = [row for row in rows if row.acceptance_status == "closed"]
        if no_acceptance:
            result.append(
                LogisticsRecommendation(
                    severity="warning",
                    title="Часть складов закрыта для приёмки",
                    detail=f"Закрытых складов: {len(no_acceptance)}.",
                    action="Планируйте поставку через склады с коэффициентом 0–1 и allowUnload=true.",
                    source="tariffs",
                )
            )
        for row in rows[:8]:
            if row.risk_level in {"danger", "warning"} and row.recommendation:
                result.append(
                    LogisticsRecommendation(
                        severity=row.risk_level,
                        title=row.warehouse_name,
                        detail=row.recommendation,
                        action="Проверьте строку склада и сформируйте план подсортировки.",
                        source="warehouse",
                    )
                )
        return result[:10]

    def _tasks(
        self,
        rows: list[LogisticsWarehouseRow],
        *,
        day_count: int,
    ) -> list[LogisticsTaskRow]:
        result: list[LogisticsTaskRow] = []
        for row in rows:
            avg_daily_sales = self._safe_div(row.sales_qty, day_count)
            avg_order_value = self._avg_order_value(row)
            stockout_in_days = (
                row.stock_units / avg_daily_sales if avg_daily_sales > 0 else None
            )
            supply_14 = self._recommended_supply(row, OOS_FAST_DAYS, day_count)
            supply_30 = self._recommended_supply(row, OOS_PLANNING_DAYS, day_count)

            if row.stock_units <= 0 and (row.orders_qty or row.sales_qty):
                result.append(
                    self._task(
                        row,
                        task_type="oos_fast",
                        severity="danger",
                        title=f"OOS на складе {row.warehouse_name}",
                        detail=(
                            "Товар закончился на складе: карточка теряет скорость "
                            "доставки, показы и заказы в этом регионе."
                        ),
                        action=(
                            "Сформируйте быструю подсортировку на 14 дней и "
                            "проверьте ближайший слот приёмки."
                        ),
                        forecast_days=OOS_FAST_DAYS,
                        stockout_in_days=0,
                        recommended_supply_qty=max(supply_14, row.missed_orders_qty),
                        potential_orders_qty=max(
                            row.missed_orders_qty, avg_daily_sales * 7
                        ),
                        potential_revenue=max(
                            row.missed_revenue, avg_order_value * max(supply_14, 1)
                        ),
                        tags=["OOS", "14 дней", "критично"],
                    )
                )
            elif stockout_in_days is not None and stockout_in_days < OOS_FAST_DAYS:
                result.append(
                    self._task(
                        row,
                        task_type="oos_fast",
                        severity="warning",
                        title=f"Запас на {stockout_in_days:.0f} дн.: {row.warehouse_name}",
                        detail=(
                            "Запас заканчивается быстрее логистического плеча. "
                            "Если не довезти товар, склад попадёт в OOS."
                        ),
                        action="Довезите товар до покрытия минимум на 14 дней.",
                        forecast_days=OOS_FAST_DAYS,
                        stockout_in_days=stockout_in_days,
                        recommended_supply_qty=supply_14,
                        potential_orders_qty=max(
                            row.missed_orders_qty, avg_daily_sales * 7
                        ),
                        potential_revenue=max(
                            row.missed_revenue, avg_order_value * max(supply_14, 1)
                        ),
                        tags=["near OOS", "14 дней"],
                    )
                )
            elif stockout_in_days is not None and stockout_in_days < OOS_PLANNING_DAYS:
                result.append(
                    self._task(
                        row,
                        task_type="oos_planning",
                        severity="watch",
                        title=f"OOS прогноз на 30 дней: {row.warehouse_name}",
                        detail=(
                            "Остатка хватает меньше чем на месяц. Это ранний "
                            "сигнал для плановой поставки."
                        ),
                        action="Запланируйте подсортировку до 30-дневного покрытия.",
                        forecast_days=OOS_PLANNING_DAYS,
                        stockout_in_days=stockout_in_days,
                        recommended_supply_qty=supply_30,
                        potential_orders_qty=avg_daily_sales * 14,
                        potential_revenue=avg_order_value * max(supply_30, 1),
                        tags=["OOS forecast", "30 дней"],
                    )
                )

            if row.missed_orders_qty > 0:
                result.append(
                    self._task(
                        row,
                        task_type="missed_orders",
                        severity="danger"
                        if row.missed_revenue > 100_000
                        else "warning",
                        title=f"Упущенные заказы: {row.warehouse_name}",
                        detail=(
                            f"За период потеряно {row.missed_orders_qty:.0f} заказов. "
                            "Это может быть OOS, закрытая приёмка или слабое покрытие региона."
                        ),
                        action="Сверьте остаток, приёмку и цену доставки; затем сформируйте поставку.",
                        forecast_days=OOS_FAST_DAYS,
                        stockout_in_days=stockout_in_days,
                        recommended_supply_qty=max(supply_14, row.missed_orders_qty),
                        potential_orders_qty=row.missed_orders_qty,
                        potential_revenue=row.missed_revenue,
                        tags=["упущенные заказы", "потенциал"],
                    )
                )

            if (
                row.logistics_share_percent is not None
                and row.logistics_share_percent >= 20
            ):
                target_logistics_cost = row.revenue * 0.15
                potential_saving = max(
                    row.logistics_cost
                    + row.return_logistics_cost
                    + row.storage_cost
                    + row.acceptance_cost
                    - target_logistics_cost,
                    0,
                )
                result.append(
                    self._task(
                        row,
                        task_type="high_logistics",
                        severity="warning",
                        title=f"Высокая логистика: {row.warehouse_name}",
                        detail=(
                            f"Логистика, хранение и приёмка занимают "
                            f"{row.logistics_share_percent:.1f}% выручки."
                        ),
                        action="Проверьте габариты, тариф склада и альтернативные регионы отгрузки.",
                        logistics_share_percent=row.logistics_share_percent,
                        potential_revenue=potential_saving,
                        expected_net_effect=potential_saving,
                        tags=["логистика", "юнит-экономика"],
                    )
                )

            if (
                row.buyout_percent is not None
                and row.buyout_percent < 70
                and row.orders_qty >= 20
            ):
                result.append(
                    self._task(
                        row,
                        task_type="buyout_drop",
                        severity="warning",
                        title=f"Выкуп просел: {row.warehouse_name}",
                        detail=(
                            f"Выкуп {row.buyout_percent:.1f}% ниже безопасного уровня. "
                            "Проверьте OOS по складам, цену, отзывы и упаковку."
                        ),
                        action="Откройте анализ причин и устраните факторы до новой поставки.",
                        buyout_percent=row.buyout_percent,
                        potential_orders_qty=max(row.orders_qty - row.sales_qty, 0),
                        potential_revenue=max(row.orders_qty - row.sales_qty, 0)
                        * avg_order_value,
                        tags=self._buyout_tags(row),
                    )
                )

            if row.turnover_days is not None and row.turnover_days > 90:
                excess_units = max(row.stock_units - avg_daily_sales * 60, 0)
                frozen_stock_effect = max(
                    row.storage_cost,
                    avg_order_value * excess_units * 0.05,
                )
                result.append(
                    self._task(
                        row,
                        task_type="low_turnover",
                        severity="watch",
                        title=f"Низкая оборачиваемость: {row.warehouse_name}",
                        detail=(
                            f"Остатка хватит примерно на {row.turnover_days:.0f} дней. "
                            "Деньги заморожены, хранение может съедать маржу."
                        ),
                        action="Остановите лишние поставки, проверьте промо или перенос в регион спроса.",
                        stockout_in_days=row.turnover_days,
                        potential_revenue=frozen_stock_effect,
                        expected_net_effect=frozen_stock_effect,
                        tags=["низкая оборачиваемость", "хранение"],
                    )
                )

            if row.acceptance_status in {"closed", "expensive"}:
                result.append(
                    self._task(
                        row,
                        task_type="acceptance_slot",
                        severity="danger"
                        if row.acceptance_status == "closed"
                        else "watch",
                        title=f"Приёмка: {row.warehouse_name}",
                        detail=(
                            "Склад закрыт для разгрузки."
                            if row.acceptance_status == "closed"
                            else "Коэффициент приёмки повышен: поставка может стать дороже."
                        ),
                        action="Найдите слот с коэффициентом 0–1 или альтернативный склад.",
                        recommended_supply_qty=supply_14,
                        potential_revenue=row.missed_revenue,
                        tags=["приёмка", f"k={row.acceptance_coefficient or '—'}"],
                    )
                )

        result.sort(
            key=lambda task: (
                self._risk_sort(task.severity),
                -max(task.expected_net_effect, 0),
                -task.potential_revenue,
                task.title,
            )
        )
        return result[:80]

    def _regional_shipments(
        self,
        rows: list[LogisticsWarehouseRow],
        *,
        day_count: int,
    ) -> list[LogisticsRegionalShipmentRow]:
        result: list[LogisticsRegionalShipmentRow] = []
        for row in rows:
            regional_daily_sales = max(
                self._safe_div(row.sales_qty, day_count),
                self._safe_div(row.region_sales_qty, day_count),
            )
            recommended_qty = max(
                round(regional_daily_sales * OOS_PLANNING_DAYS - row.stock_units),
                0,
            )
            if recommended_qty <= 0 and row.missed_orders_qty <= 0:
                continue
            if row.acceptance_status == "closed":
                priority = "blocked"
            elif row.risk_level in {"danger", "warning"}:
                priority = "recommended"
            else:
                priority = "planned"

            avg_order_value = self._avg_order_value(row)
            demand_cover_orders = (
                min(recommended_qty, regional_daily_sales * OOS_FAST_DAYS)
                if row.region_sales_qty
                else 0
            )
            potential_orders = max(
                row.missed_orders_qty,
                min(
                    recommended_qty,
                    max(
                        self._safe_div(row.sales_qty, day_count) * OOS_FAST_DAYS,
                        demand_cover_orders,
                    ),
                ),
            )
            potential_revenue = max(
                row.missed_revenue, potential_orders * avg_order_value
            )
            logistics_per_sale = self._safe_div(
                row.logistics_cost
                + row.return_logistics_cost
                + row.storage_cost
                + row.acceptance_cost,
                row.sales_qty,
            )
            expected_logistics = logistics_per_sale * max(
                recommended_qty, potential_orders
            )
            margin_factor = (
                max((row.margin_percent or 0) / 100, 0.05)
                if row.margin_percent is not None
                else 0.35
            )
            result.append(
                LogisticsRegionalShipmentRow(
                    id=f"regional:{self._slug(row.warehouse_name)}",
                    warehouse_name=row.warehouse_name,
                    region_name=row.region_name,
                    recommended_supply_qty=recommended_qty,
                    potential_orders_qty=potential_orders,
                    potential_revenue=potential_revenue,
                    region_sales_qty=row.region_sales_qty,
                    region_sales_amount=row.region_sales_amount,
                    region_sales_share_percent=row.region_sales_share_percent,
                    expected_logistics_cost=expected_logistics,
                    expected_net_effect=potential_revenue * margin_factor
                    - expected_logistics,
                    current_stock_units=row.stock_units,
                    turnover_days=row.turnover_days,
                    acceptance_status=row.acceptance_status,
                    acceptance_coefficient=row.acceptance_coefficient,
                    priority=priority,
                    reason=self._regional_reason(row),
                    tags=[
                        "региональная отгрузка",
                        f"{OOS_PLANNING_DAYS} дней",
                        f"приёмка {row.acceptance_status}",
                    ],
                )
            )
        result.sort(
            key=lambda row: (
                {"recommended": 0, "planned": 1, "blocked": 2}.get(row.priority, 3),
                -row.expected_net_effect,
            )
        )
        return result[:40]

    def _warehouse_controls(
        self,
        rows: list[LogisticsWarehouseRow],
        tasks: list[LogisticsTaskRow],
    ) -> list[LogisticsWarehouseControlRow]:
        tasks_by_warehouse: Counter[str] = Counter(
            task.warehouse_name for task in tasks if task.warehouse_name
        )
        revenue_by_warehouse: defaultdict[str, float] = defaultdict(float)
        for task in tasks:
            if task.warehouse_name:
                revenue_by_warehouse[task.warehouse_name] += task.potential_revenue

        result = []
        for row in rows:
            recommended_mode = "active"
            reason = "Склад участвует в расчёте задач."
            if row.acceptance_status == "closed" and not row.open_supply_count:
                recommended_mode = "pause_tasks"
                reason = "Приёмка закрыта: задачи поставки лучше переводить на альтернативные склады."
            elif (
                row.turnover_days is not None
                and row.turnover_days > 120
                and not row.missed_orders_qty
            ):
                recommended_mode = "pause_replenishment"
                reason = "Запас избыточный: новые задачи поставки лучше временно не создавать."
            elif (
                row.logistics_share_percent is not None
                and row.logistics_share_percent >= 30
            ):
                recommended_mode = "review_economics"
                reason = (
                    "Логистика выше 30% выручки: склад требует проверки юнит-экономики."
                )

            result.append(
                LogisticsWarehouseControlRow(
                    warehouse_name=row.warehouse_name,
                    region_name=row.region_name,
                    mode="active",
                    recommended_mode=recommended_mode,
                    task_count=tasks_by_warehouse[row.warehouse_name],
                    potential_revenue=revenue_by_warehouse[row.warehouse_name],
                    stock_units=row.stock_units,
                    turnover_days=row.turnover_days,
                    acceptance_status=row.acceptance_status,
                    logistics_share_percent=row.logistics_share_percent,
                    reason=reason,
                )
            )
        result.sort(
            key=lambda row: (
                row.recommended_mode == "active",
                -row.task_count,
                -row.potential_revenue,
                row.warehouse_name,
            )
        )
        return result

    def _task(
        self,
        row: LogisticsWarehouseRow,
        *,
        task_type: str,
        severity: str,
        title: str,
        detail: str,
        action: str,
        forecast_days: int | None = None,
        stockout_in_days: float | None = None,
        recommended_supply_qty: float = 0,
        potential_orders_qty: float = 0,
        potential_revenue: float = 0,
        expected_net_effect: float | None = None,
        logistics_share_percent: float | None = None,
        buyout_percent: float | None = None,
        tags: list[str] | None = None,
    ) -> LogisticsTaskRow:
        margin_factor = (
            max((row.margin_percent or 0) / 100, 0.05)
            if row.margin_percent is not None
            else 0.35
        )
        logistics_per_sale = self._safe_div(
            row.logistics_cost
            + row.return_logistics_cost
            + row.storage_cost
            + row.acceptance_cost,
            row.sales_qty,
        )
        expected_net = potential_revenue * margin_factor - logistics_per_sale * max(
            recommended_supply_qty, potential_orders_qty
        )
        if expected_net_effect is not None:
            expected_net = expected_net_effect
        confidence = "high" if row.sales_qty >= 30 and row.revenue else "medium"
        if row.sales_qty < 10 and not row.missed_orders_qty:
            confidence = "low"
        return LogisticsTaskRow(
            id=f"{task_type}:{self._slug(row.warehouse_name)}",
            task_type=task_type,
            severity=severity,
            title=title,
            warehouse_name=row.warehouse_name,
            region_name=row.region_name,
            detail=detail,
            action=action,
            forecast_days=forecast_days,
            stockout_in_days=stockout_in_days,
            recommended_supply_qty=max(recommended_supply_qty, 0),
            potential_orders_qty=max(potential_orders_qty, 0),
            potential_revenue=max(potential_revenue, 0),
            expected_net_effect=expected_net,
            logistics_share_percent=logistics_share_percent
            if logistics_share_percent is not None
            else row.logistics_share_percent,
            buyout_percent=buyout_percent
            if buyout_percent is not None
            else row.buyout_percent,
            confidence=confidence,
            tags=tags or [],
        )

    @staticmethod
    def _safe_div(numerator: float, denominator: float) -> float:
        return numerator / denominator if denominator else 0.0

    def _recommended_supply(
        self,
        row: LogisticsWarehouseRow,
        target_days: int,
        day_count: int,
    ) -> float:
        avg_daily_sales = self._safe_div(row.sales_qty, day_count)
        target_stock = avg_daily_sales * target_days
        return max(round(target_stock - row.stock_units), 0)

    def _avg_order_value(self, row: LogisticsWarehouseRow) -> float:
        return self._safe_div(row.revenue, row.sales_qty or row.orders_qty) or 0.0

    @staticmethod
    def _slug(value: str) -> str:
        return (
            value.casefold()
            .replace(" ", "-")
            .replace("/", "-")
            .replace("\\", "-")
            .replace(":", "-")
        )

    @staticmethod
    def _buyout_tags(row: LogisticsWarehouseRow) -> list[str]:
        tags = ["выкуп"]
        if row.stock_units <= 0 or (
            row.turnover_days is not None and row.turnover_days < 14
        ):
            tags.append("OOS")
        if (
            row.logistics_share_percent is not None
            and row.logistics_share_percent >= 20
        ):
            tags.append("дорогая доставка")
        if row.missed_orders_qty:
            tags.append("отмены")
        tags.extend(["цена", "отзывы"])
        return tags

    @staticmethod
    def _regional_reason(row: LogisticsWarehouseRow) -> str:
        if row.missed_orders_qty:
            return (
                f"В регионе есть {row.missed_orders_qty:.0f} упущенных заказов: "
                "отгрузка может вернуть видимость и скорость доставки."
            )
        if row.region_sales_qty:
            return (
                f"Region-sale показывает спрос {row.region_sales_qty:.0f} шт. "
                f"за период, доля региона {row.region_sales_share_percent or 0:.1f}%."
            )
        if row.turnover_days is not None and row.turnover_days < OOS_PLANNING_DAYS:
            return "Остаток ниже 30-дневного покрытия: нужна плановая региональная поставка."
        return "Есть спрос и экономический смысл довезти товар в региональный склад."

    @staticmethod
    def _api_capabilities() -> list[LogisticsApiCapability]:
        return [
            LogisticsApiCapability(
                key="orders",
                label="Заказы по складам, регионам и отменам",
                endpoint="GET statistics-api /api/v1/supplier/orders",
                token_category="statistics",
                status="active",
            ),
            LogisticsApiCapability(
                key="sales",
                label="Продажи, выкупы и предварительная выручка",
                endpoint="GET statistics-api /api/v1/supplier/sales",
                token_category="statistics",
                status="active",
            ),
            LogisticsApiCapability(
                key="warehouse_remains",
                label="Остатки WB по складам",
                endpoint="GET seller-analytics-api /api/v1/warehouse_remains + status/download",
                token_category="analytics",
                status="active",
            ),
            LogisticsApiCapability(
                key="fbw_supplies",
                label="Склады, поставки, товары и упаковки FBO",
                endpoint="GET/POST supplies-api /api/v1/warehouses, /acceptance/options, /supplies",
                token_category="supplies",
                status="active",
            ),
            LogisticsApiCapability(
                key="tariffs",
                label="Короба, паллеты, возвраты и коэффициенты приёмки",
                endpoint="GET common-api /api/v1/tariffs/*, /api/tariffs/v1/acceptance/coefficients",
                token_category="tariffs",
                status="active",
            ),
            LogisticsApiCapability(
                key="finance_rows",
                label="Фактические расходы логистики, хранения и приёмки",
                endpoint="POST finance-api /api/finance/v1/sales-reports/detailed",
                token_category="finance",
                status="active",
            ),
            LogisticsApiCapability(
                key="region_sales",
                label="Спрос и продажи по регионам",
                endpoint="GET seller-analytics-api /api/v1/analytics/region-sale",
                token_category="analytics",
                status="active",
            ),
            LogisticsApiCapability(
                key="paid_storage",
                label="Детальный отчёт платного хранения",
                endpoint="GET seller-analytics-api /api/v1/paid_storage + status/download",
                token_category="analytics",
                status="active",
                note="Отдельный logistics sync даёт детализацию хранения по товарам, складам и датам.",
            ),
            LogisticsApiCapability(
                key="acceptance_expenses",
                label="Детальный отчёт расходов приёмки",
                endpoint="GET seller-analytics-api /api/v1/acceptance_report + status/download",
                token_category="analytics",
                status="active",
                note="Отдельный logistics sync нужен для сверки расходов приёмки по операциям.",
            ),
            LogisticsApiCapability(
                key="transit_tariffs",
                label="Транзитные направления и тарифы поставок",
                endpoint="GET supplies-api /api/v1/transit-tariffs",
                token_category="supplies",
                status="active",
                note="Используется для выбора маршрута через транзитный склад.",
            ),
            LogisticsApiCapability(
                key="seller_warehouses",
                label="Склады продавца FBS/DBW и их остатки",
                endpoint="GET marketplace-api /api/v3/warehouses, POST /api/v3/stocks/{warehouseId}",
                token_category="marketplace",
                status="active",
                note="Складской контур продавца синхронизирует FBS/DBW склады и остатки по chrtId.",
            ),
        ]

    @staticmethod
    def _risk_sort(level: str) -> int:
        return {"danger": 0, "warning": 1, "watch": 2, "ok": 3}.get(level, 4)
