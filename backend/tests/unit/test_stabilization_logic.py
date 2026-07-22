from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.modules.finance.sync import FinanceSyncService
from app.services.dashboard import DashboardService
from app.services.manual_costs import ManualCostService
from app.services.marts import MartService


def test_dashboard_cost_match_uses_resolved_sku_id() -> None:
    service = DashboardService()
    costs = [
        SimpleNamespace(id=1, sku_id=10, valid_from=date(2026, 1, 1), valid_to=None),
        SimpleNamespace(id=2, sku_id=11, valid_from=date(2026, 2, 1), valid_to=None),
    ]

    matched = service._match_cost_for_sku(costs, sku_id=11, at_date=date(2026, 5, 15))

    assert matched is costs[1]


def test_manual_cost_candidate_resolution_prefers_exact_barcode_and_size() -> None:
    sku_rows = [
        SimpleNamespace(id=1, vendor_code="SKU-1", nm_id=100, barcode="111", tech_size="42"),
        SimpleNamespace(id=2, vendor_code="SKU-1", nm_id=100, barcode="222", tech_size="42"),
    ]

    matches, rule = ManualCostService._resolve_sku_candidates(
        sku_rows,
        vendor_code="SKU-1",
        nm_id=100,
        barcode="222",
        tech_size="42",
    )

    assert rule == "vendor_code+barcode+tech_size"
    assert [sku.id for sku in matches] == [2]


def test_manual_cost_candidate_resolution_is_case_insensitive_for_vendor() -> None:
    sku_rows = [
        SimpleNamespace(
            id=1,
            vendor_code="СС 1183 бутылочный",
            nm_id=100,
            barcode="111",
            tech_size="46",
        ),
    ]

    matches, rule = ManualCostService._resolve_sku_candidates(
        sku_rows,
        vendor_code="сс 1183 бутылочный",
        nm_id=100,
        barcode="111",
        tech_size="46",
    )

    assert rule == "vendor_code+barcode+tech_size"
    assert [sku.id for sku in matches] == [1]


def test_mart_cost_match_falls_back_to_same_article_size_when_barcode_changes() -> None:
    service = MartService()
    costs = [
        SimpleNamespace(
            id=1,
            sku_id=10,
            nm_id=100,
            vendor_code="СС 1108 красный",
            barcode="old-barcode",
            tech_size="48",
            valid_from=date(2026, 1, 1),
            valid_to=None,
        )
    ]
    cost_index = service._build_cost_index(costs)  # type: ignore[arg-type]

    matched = service._match_cost_from_index(
        cost_index,
        sku_id=20,
        nm_id=100,
        vendor_code="сс 1108 красный",
        tech_size="48",
        at_date=date(2026, 7, 21),
    )

    assert matched is costs[0]


def test_operational_sale_returns_reduce_open_period_revenue() -> None:
    sale = {
        "sale_id": "S123",
        "finished_price": Decimal("100"),
        "for_pay": Decimal("90"),
        "is_cancel": False,
    }
    returned = {
        "sale_id": "R123",
        "finished_price": Decimal("30"),
        "for_pay": Decimal("-27"),
        "is_cancel": True,
    }

    assert MartService._sale_sign(sale) == 1
    assert MartService._signed_sale_amount(sale, sale["finished_price"]) == Decimal(
        "100"
    )
    assert MartService._sale_sign(returned) == -1
    assert MartService._signed_sale_amount(
        returned, returned["finished_price"]
    ) == Decimal("-30")
    assert MartService._signed_sale_amount(returned, returned["for_pay"]) == Decimal(
        "-27"
    )


def test_finance_row_classification_marks_reconcilable_sales_and_returns() -> None:
    sale = FinanceSyncService._classify_finance_row_payload({"docTypeName": "Продажа"})
    ret = FinanceSyncService._classify_finance_row_payload({"docTypeName": "Return"})
    expense = FinanceSyncService._classify_finance_row_payload({"docTypeName": "Хранение"})

    assert sale["operation_type"] == "sale"
    assert sale["is_reconcilable"] is True
    assert ret["operation_type"] == "return"
    assert ret["is_return_operation"] is True
    assert expense["operation_type"] == "expense"
    assert expense["is_expense_operation"] is True


def test_total_unit_cost_uses_cost_price_plus_seller_other_expense() -> None:
    cost = SimpleNamespace(
        cost_price=Decimal("120"),
        unit_cost=Decimal("120"),
        seller_other_expense=Decimal("12.5"),
        packaging_cost=Decimal("5"),
        inbound_logistics_cost=Decimal("7.5"),
    )

    assert DashboardService._total_unit_cost(cost) == Decimal("132.5")


def test_total_unit_cost_falls_back_to_legacy_manual_cost_columns() -> None:
    cost = SimpleNamespace(
        cost_price=Decimal("120"),
        unit_cost=Decimal("120"),
        seller_other_expense=None,
        packaging_cost=Decimal("5"),
        inbound_logistics_cost=Decimal("7.5"),
    )

    assert DashboardService._total_unit_cost(cost) == Decimal("132.5")
