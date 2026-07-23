from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.finance import WBRealizationReportRow
from app.schemas.logistics import (
    LogisticsDataSourceStatus,
    LogisticsProductRow,
    LogisticsWarehouseRow,
)
from app.services.logistics import LogisticsService


def _warehouse_item(**overrides):
    item = {
        "warehouse_name": "Коледино",
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
        "delivery_base": None,
        "delivery_liter": None,
        "storage_base": None,
        "box_type_ids": set(),
        "supply_count": 0,
        "open_supply_count": 0,
    }
    item.update(overrides)
    return item


@pytest.mark.asyncio
async def test_overview_kpis_are_calculated_before_warehouse_limit(monkeypatch) -> None:
    service = LogisticsService()

    monkeypatch.setattr(service, "_merge_orders", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_merge_sales", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_merge_finance", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_merge_tariffs", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "_region_demand", AsyncMock(return_value={}))
    monkeypatch.setattr(
        service,
        "_data_sources",
        AsyncMock(
            return_value=[
                LogisticsDataSourceStatus(key="test", label="test", status="ok", rows=1)
            ]
        ),
    )

    async def _merge_stock(session, *, account_id, warehouse_map, stock_totals):
        del session, account_id
        stock_totals["in_way_to_client"] = 7.0
        for idx, name in enumerate(("A", "B", "C"), start=1):
            warehouse_map[name].update(
                _warehouse_item(
                    warehouse_name=name,
                    stock_units=idx * 10,
                    sales_qty=idx,
                    sales_revenue=idx * 100,
                    sales_for_pay=idx * 70,
                )
            )
        return None

    async def _supplies(session, *, account_id, start, end, limit, warehouse_map):
        del session, account_id, start, end, limit, warehouse_map
        return []

    monkeypatch.setattr(service, "_merge_stock", _merge_stock)
    monkeypatch.setattr(service, "_supplies", _supplies)
    monkeypatch.setattr(service, "_products", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_paid_storage_details", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_acceptance_details", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_transit_tariffs", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_seller_warehouses", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service,
        "_detail_kpi_totals",
        AsyncMock(
            return_value={
                "paid_storage_detail_cost": 0,
                "paid_storage_detail_rows": 0,
                "acceptance_detail_cost": 0,
                "acceptance_detail_rows": 0,
                "transit_route_count": 0,
                "seller_warehouse_count": 0,
                "seller_stock_units": 0,
            }
        ),
    )

    overview = await service.overview(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 30),
        warehouse_limit=1,
    )

    assert len(overview.warehouses) == 1
    assert overview.kpis.stock_units == pytest.approx(60)
    assert overview.kpis.revenue == pytest.approx(600)
    assert overview.kpis.in_way_to_client == pytest.approx(7)


def test_product_row_builds_sku_level_shipment_metrics() -> None:
    service = LogisticsService()

    row = service._product_row(
        {
            "warehouse_name": "Тула",
            "region_name": "Южный федеральный округ",
            "nm_id": 123456,
            "vendor_code": "SKU-1",
            "barcode": "460000000001",
            "title": "Тестовый товар",
            "brand": "Brand",
            "subject_name": "Категория",
            "stock_units": 3.0,
            "in_way_to_client": 1.0,
            "in_way_from_client": 2.0,
            "orders_qty": 12.0,
            "cancelled_orders_qty": 2.0,
            "cancelled_revenue": 2400.0,
            "sales_qty": 10.0,
            "sales_revenue": 0.0,
            "sales_for_pay": 0.0,
            "finance_revenue": 11_000.0,
            "finance_for_pay": 7_400.0,
            "finance_rows": 10,
            "finance_money_rows": 10,
            "logistics_cost": 900.0,
            "storage_cost": 100.0,
            "acceptance_cost": 50.0,
            "return_logistics_cost": 150.0,
        },
        day_count=10,
    )

    assert row.revenue_source == "finance"
    assert row.avg_daily_sales == pytest.approx(1)
    assert row.turnover_days == pytest.approx(3)
    assert row.recommended_supply_14 == pytest.approx(11)
    assert row.recommended_supply_30 == pytest.approx(27)
    assert row.potential_orders_qty == pytest.approx(7)
    assert row.potential_revenue == pytest.approx(7700)
    assert row.expected_net_effect == pytest.approx(3020)
    assert row.risk_level == "warning"
    assert "14 дней" in row.tags


def test_product_row_blends_closed_finance_with_open_sales_tail() -> None:
    service = LogisticsService()

    row = service._product_row(
        {
            "warehouse_name": "Тула",
            "region_name": "Южный федеральный округ",
            "nm_id": 123456,
            "vendor_code": "SKU-1",
            "barcode": "460000000001",
            "title": "Тестовый товар",
            "brand": "Brand",
            "subject_name": "Категория",
            "stock_units": 20.0,
            "in_way_to_client": 0.0,
            "in_way_from_client": 0.0,
            "orders_qty": 12.0,
            "cancelled_orders_qty": 0.0,
            "cancelled_revenue": 0.0,
            "sales_qty": 10.0,
            "sales_revenue": 1_000.0,
            "sales_for_pay": 700.0,
            "finance_revenue": 9_000.0,
            "finance_for_pay": 6_300.0,
            "finance_rows": 9,
            "finance_money_rows": 9,
            "logistics_cost": 500.0,
            "storage_cost": 100.0,
            "acceptance_cost": 50.0,
            "return_logistics_cost": 0.0,
        },
        day_count=10,
    )

    assert row.revenue == pytest.approx(10_000)
    assert row.for_pay == pytest.approx(7_000)
    assert row.revenue_source == "finance+sales"


def test_warehouse_row_uses_finance_without_false_missed() -> None:
    service = LogisticsService()

    row = service._warehouse_row(
        _warehouse_item(
            region_name="Центральный федеральный округ",
            stock_units=100,
            orders_qty=12,
            cancelled_orders_qty=3,
            cancelled_revenue=300,
            sales_qty=10,
            sales_revenue=0,
            sales_for_pay=0,
            finance_revenue=900,
            finance_for_pay=620,
            finance_rows=5,
            finance_money_rows=5,
            logistics_cost=100,
        ),
        day_count=10,
        region_demand={
            "центральный": {
                "sales_qty": 50.0,
                "sales_amount": 5000.0,
                "share_percent": 25.0,
            }
        },
    )

    assert row.revenue == pytest.approx(900)
    assert row.for_pay == pytest.approx(620)
    assert row.revenue_source == "finance"
    assert row.finance_rows == 5
    assert row.cancelled_orders_qty == pytest.approx(3)
    assert row.missed_orders_qty == 0
    assert row.region_sales_qty == pytest.approx(50)


def test_warehouse_row_blends_closed_finance_with_open_sales_tail() -> None:
    service = LogisticsService()

    row = service._warehouse_row(
        _warehouse_item(
            stock_units=30,
            orders_qty=12,
            sales_qty=10,
            sales_revenue=1000,
            sales_for_pay=700,
            finance_revenue=9000,
            finance_for_pay=6300,
            finance_rows=9,
            finance_money_rows=9,
            logistics_cost=500,
        ),
        day_count=10,
        region_demand={},
    )

    assert row.revenue == pytest.approx(10_000)
    assert row.for_pay == pytest.approx(7_000)
    assert row.revenue_source == "finance+sales"


def test_warehouse_row_keeps_zero_net_finance_instead_of_sales_fallback() -> None:
    service = LogisticsService()

    row = service._warehouse_row(
        _warehouse_item(
            stock_units=10,
            orders_qty=2,
            sales_qty=1,
            sales_revenue=0,
            sales_for_pay=0,
            finance_revenue=0,
            finance_for_pay=0,
            finance_rows=2,
            finance_money_rows=2,
        ),
        day_count=10,
        region_demand={},
    )

    assert row.revenue == pytest.approx(0)
    assert row.for_pay == pytest.approx(0)
    assert row.revenue_source == "finance"


def test_warehouse_row_counts_return_logistics_once_in_margin_and_share() -> None:
    service = LogisticsService()

    row = service._warehouse_row(
        _warehouse_item(
            stock_units=100,
            orders_qty=10,
            sales_qty=10,
            finance_revenue=1000,
            finance_for_pay=700,
            finance_rows=3,
            finance_money_rows=3,
            logistics_cost=100,
            return_logistics_cost=40,
            storage_cost=20,
            acceptance_cost=10,
        ),
        day_count=10,
        region_demand={},
    )

    assert row.logistics_share_percent == pytest.approx(17)
    assert row.margin_percent == pytest.approx(53)


def test_finance_return_rows_are_signed_before_logistics_margin_math() -> None:
    service = LogisticsService()
    sale = WBRealizationReportRow(
        doc_type_name="Продажа",
        is_reconcilable=True,
        retail_amount=Decimal("1000"),
        retail_price_with_disc=Decimal("900"),
        for_pay=Decimal("620"),
    )
    returned = WBRealizationReportRow(
        doc_type_name="Возврат",
        is_reconcilable=True,
        retail_amount=Decimal("1000"),
        retail_price_with_disc=Decimal("900"),
        for_pay=Decimal("620"),
    )
    service_row = WBRealizationReportRow(
        doc_type_name="Логистика",
        is_reconcilable=False,
        retail_amount=Decimal("500"),
        for_pay=Decimal("500"),
    )

    revenue = service._signed_finance_amount(
        sale, sale.retail_amount
    ) + service._signed_finance_amount(returned, returned.retail_amount)
    for_pay = service._signed_finance_amount(
        sale, sale.for_pay
    ) + service._signed_finance_amount(returned, returned.for_pay)

    assert service._is_reconcilable_finance_row(sale) is True
    assert service._is_reconcilable_finance_row(returned) is True
    assert service._is_reconcilable_finance_row(service_row) is False
    assert revenue == Decimal("0")
    assert for_pay == Decimal("0")


def test_operational_sales_start_skips_closed_finance_period() -> None:
    service = LogisticsService()

    assert service._operational_sales_start(
        start=date(2026, 7, 1), closed_finance_date_to=None
    ) == date(2026, 7, 1)
    assert service._operational_sales_start(
        start=date(2026, 7, 1), closed_finance_date_to=date(2026, 6, 30)
    ) == date(2026, 7, 1)
    assert service._operational_sales_start(
        start=date(2026, 7, 1), closed_finance_date_to=date(2026, 7, 10)
    ) == date(2026, 7, 11)


def test_acceptance_requires_allow_unload_and_parses_best_slot_details() -> None:
    service = LogisticsService()

    assert service._acceptance_status("0", None) == "unknown"
    assert service._acceptance_status("1", True) == "available"
    assert service._acceptance_status("3", True) == "expensive"
    assert service._acceptance_status("0", False) == "closed"

    option = service._acceptance_option(
        SimpleNamespace(
            coefficient="1",
            allow_unload=True,
            payload={"date": "2026-07-21", "boxTypeID": 5},
        )
    )

    assert option["status"] == "available"
    assert option["date"] == date(2026, 7, 21)
    assert option["box_type_id"] == 5


def test_recommended_supply_does_not_treat_client_returns_as_ready_stock() -> None:
    service = LogisticsService()
    row = LogisticsWarehouseRow(
        warehouse_name="Коледино",
        stock_units=0,
        in_way_from_client=100,
        sales_qty=14,
        revenue=1400,
    )

    assert service._recommended_supply(row, target_days=14, day_count=14) == 14


def test_regional_shipments_use_region_sale_demand_without_local_sales() -> None:
    service = LogisticsService()
    row = LogisticsWarehouseRow(
        warehouse_name="Казань",
        region_name="Приволжский федеральный округ",
        stock_units=0,
        sales_qty=0,
        orders_qty=0,
        revenue=1400,
        for_pay=900,
        region_sales_qty=28,
        region_sales_amount=2800,
        region_sales_share_percent=12.5,
        logistics_cost=140,
        acceptance_status="available",
    )

    shipments = service._regional_shipments([row], day_count=14)

    assert shipments
    assert shipments[0].recommended_supply_qty == pytest.approx(60)
    assert shipments[0].region_sales_qty == pytest.approx(28)
    assert "Региональная аналитика" in shipments[0].reason


@pytest.mark.asyncio
async def test_shipment_planning_uses_stock_control_scope_and_exclusions() -> None:
    service = LogisticsService()
    service.stock_control_repo = SimpleNamespace(
        latest_successful_run=AsyncMock(
            return_value=SimpleNamespace(
                id=44,
                run_type="return_excess",
                finished_at=None,
                settings_snapshot_json={"excluded_regions_json": ["Центральный"]},
                result_summary_json={"products": 1},
            )
        ),
        list_region_rows=AsyncMock(
            return_value=(
                1,
                [
                    SimpleNamespace(
                        id=1,
                        region="Центральный",
                        warehouse_name="Коледино",
                        nm_id=1001,
                        barcode="4601",
                        vendor_code="SKU-1",
                        chrt_id=None,
                        current_stock_qty=3,
                        target_stock_qty=11,
                        delta_qty=8,
                    )
                ],
            )
        ),
        list_movements=AsyncMock(
            return_value=(
                1,
                [
                    SimpleNamespace(
                        id=5,
                        movement_type="regional_redistribution",
                        nm_id=1001,
                        vendor_code="SKU-1",
                        barcode="4601",
                        size_name="M",
                        donor_region="Южный",
                        donor_warehouse="Тула",
                        recipient_region="Центральный",
                        recipient_warehouse="Коледино",
                        quantity=8,
                        priority="P1",
                        reason_code="regional_shortage",
                        business_explanation="Дефицит по региону.",
                        confidence="high",
                        status="new",
                    )
                ],
            )
        ),
    )

    planning = await service._shipment_planning(
        SimpleNamespace(),  # type: ignore[arg-type]
        account_id=1,
        rows=[
            LogisticsWarehouseRow(
                warehouse_name="Коледино",
                region_name="Центральный",
                stock_units=3,
                sales_qty=10,
                revenue=1000,
                acceptance_status="available",
            )
        ],
        products=[
            LogisticsProductRow(
                id="product:kol:1001",
                nm_id=1001,
                vendor_code="SKU-1",
                barcode="4601",
                warehouse_name="Коледино",
                region_name="Центральный",
            )
        ],
        day_count=10,
    )

    assert planning.status == "stock_control"
    assert planning.formula.title == "Формула контроля остатков"
    assert planning.excluded_regions == ["Центральный"]
    assert planning.regions[0].label == "Центральный"
    assert planning.regions[0].enabled_by_default is False
    assert planning.regions[0].shortage_qty == pytest.approx(8)
    assert planning.warehouses[0].inbound_qty == pytest.approx(8)
    assert planning.movements[0].quantity == pytest.approx(8)
