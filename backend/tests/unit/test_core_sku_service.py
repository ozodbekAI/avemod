from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.core_sku import CoreSKUListItem
from app.services.core_sku import CoreSKUService


def test_extract_payload_prices_for_sku_prefers_matching_tech_size() -> None:
    service = CoreSKUService()

    price, discounted = service._extract_payload_prices_for_sku(
        {
            "sizes": [
                {"sizeID": 10, "techSizeName": "44", "price": 19900, "discountedPrice": 11962},
                {"sizeID": 11, "techSizeName": "48", "price": 18900, "discountedPrice": 10962},
            ]
        },
        size_id=None,
        tech_size="48",
    )

    assert price == Decimal("18900")
    assert discounted == Decimal("10962")


def test_extract_payload_prices_for_sku_falls_back_to_min_when_exact_match_missing() -> None:
    service = CoreSKUService()

    price, discounted = service._extract_payload_prices_for_sku(
        {
            "sizes": [
                {"sizeID": 10, "techSizeName": "44", "price": 19900, "discountedPrice": 11962},
                {"sizeID": 11, "techSizeName": "46", "price": 18900, "discountedPrice": 10962},
            ]
        },
        size_id=None,
        tech_size="50",
    )

    assert price == Decimal("18900")
    assert discounted == Decimal("10962")


def test_extract_size_row_prices_for_sku_prefers_exact_size() -> None:
    service = CoreSKUService()

    price, discounted = service._extract_size_row_prices_for_sku(
        [
            SimpleNamespace(size_id=10, tech_size_name="44", price=Decimal("19900"), discounted_price=Decimal("11962")),
            SimpleNamespace(size_id=11, tech_size_name="48", price=Decimal("18900"), discounted_price=Decimal("10962")),
        ],
        size_id=11,
        tech_size="48",
    )

    assert price == Decimal("18900")
    assert discounted == Decimal("10962")


def test_aggregate_stock_snapshot_rows_uses_total_row_and_keeps_transit_rows() -> None:
    service = CoreSKUService()

    quantity, quantity_full, in_way_to_client, in_way_from_client = service._aggregate_stock_snapshot_rows(
        [
            SimpleNamespace(
                warehouse_name="Всего находится на складах",
                quantity=None,
                quantity_full=Decimal("29"),
                in_way_to_client=None,
                in_way_from_client=None,
            ),
            SimpleNamespace(
                warehouse_name="В пути до получателей",
                quantity=None,
                quantity_full=None,
                in_way_to_client=Decimal("10"),
                in_way_from_client=None,
            ),
            SimpleNamespace(
                warehouse_name="В пути возвраты на склад WB",
                quantity=None,
                quantity_full=None,
                in_way_to_client=None,
                in_way_from_client=Decimal("12"),
            ),
            SimpleNamespace(
                warehouse_name="Коледино",
                quantity=Decimal("5"),
                quantity_full=None,
                in_way_to_client=None,
                in_way_from_client=None,
            ),
        ]
    )

    assert quantity == Decimal("29")
    assert quantity_full == Decimal("29")
    assert in_way_to_client == Decimal("10")
    assert in_way_from_client == Decimal("12")


def test_core_sku_schema_exposes_cost_trust_fields() -> None:
    fields = CoreSKUListItem.model_fields

    assert "has_real_manual_cost" in fields
    assert "has_placeholder_cost" in fields
    assert "business_trusted" in fields
    assert "operational_trusted" in fields
    assert "cost_source" in fields
    assert "cost_truth_level" in fields


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _ScalarsResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return list(self._values)


class _FakeSession:
    def __init__(self, *results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("Unexpected extra execute() call")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_list_skus_reuses_cached_page(monkeypatch) -> None:
    service = CoreSKUService()
    monkeypatch.setattr(service, "_list_version_hash", AsyncMock(return_value="v1"))
    service._load_enriched_rows = AsyncMock(
        return_value=[
            CoreSKUListItem(
                id=1,
                account_id=1,
                nm_id=101,
                vendor_code="ABC",
                supplier_article=None,
                barcode="111",
                chrt_id=None,
                size_id=None,
                tech_size=None,
                title="Item",
                brand="Brand",
                subject_id=None,
                subject_name="Subject",
                is_active=True,
                status="active",
                comment=None,
                source_updated_at=None,
                current_price=100.0,
                current_discounted_price=90.0,
                seller_discount=None,
                club_discount=None,
                latest_quantity=None,
                latest_quantity_full=None,
                latest_in_way_to_client=None,
                latest_in_way_from_client=None,
                latest_stock_snapshot_at=None,
                latest_sale_date=None,
                manual_cost_id=None,
                cost_price=None,
                seller_other_expense=None,
                packaging_cost=None,
                inbound_logistics_cost=None,
                total_unit_cost=None,
                supplier=None,
                has_manual_cost=False,
                open_issue_count=0,
                has_open_issues=False,
                last_30d_sales_qty=0,
                last_30d_revenue=0.0,
            )
        ]
    )
    session = _FakeSession(
        _ScalarResult(1),
        _ScalarsResult([1]),
    )

    first = await service.list_skus(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )
    second = await service.list_skus(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert second.data_version_hash == "v1"
    assert service._load_enriched_rows.await_count == 1
