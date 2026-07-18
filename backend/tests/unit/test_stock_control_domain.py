from __future__ import annotations

from app.domain.stock_control.allocation import largest_remainder_allocation
from app.domain.stock_control.algorithms import (
    DemandRow,
    HandStockRow,
    StockRow,
    compute_store_balance,
    compute_return_excess,
    compute_ship_from_hand,
)
from app.domain.stock_control.regions import normalize_excluded_regions, normalize_region


def test_region_normalization_and_exclusion_aliases() -> None:
    assert normalize_region(" Северо западный федеральный округ ") == "Северо-Западный"
    assert normalize_region("Центральный федеральный округ") == "Центральный"
    assert normalize_excluded_regions(["южный федеральный округ"]) == {"Южный"}


def test_largest_remainder_preserves_total_quantity() -> None:
    allocation = largest_remainder_allocation(7, {"Центральный": 3, "Южный": 2, "Сибирский": 1})

    assert sum(allocation.values()) == 7
    assert allocation == {"Центральный": 4, "Южный": 2, "Сибирский": 1}
    assert largest_remainder_allocation(3, {"a": 0, "b": 0}) == {"a": 3, "b": 0}


def test_return_excess_excludes_regions_and_creates_non_zero_movements() -> None:
    result = compute_return_excess(
        demand_rows=[
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", orders_qty=8),
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Южный", orders_qty=2),
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Сибирский", orders_qty=50),
        ],
        stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", warehouse_id=1, warehouse_name="Коледино", quantity=1),
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Южный", warehouse_id=2, warehouse_name="Краснодар", quantity=9),
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Сибирский", warehouse_id=3, warehouse_name="Новосибирск", quantity=20),
        ],
        excluded_regions=["сибирский федеральный округ"],
    )

    regions = {row["region"] for row in result["region_rows"]}
    assert regions == {"Центральный", "Южный"}
    assert all(item["quantity"] > 0 for item in result["movements"])
    assert result["movements"][0]["donor_region"] == "Южный"
    assert result["movements"][0]["recipient_region"] == "Центральный"


def test_return_excess_zero_demand_uses_stock_as_donors_without_fake_demand() -> None:
    result = compute_return_excess(
        demand_rows=[],
        stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", warehouse_id=1, warehouse_name="Коледино", quantity=9),
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Южный", warehouse_id=2, warehouse_name="Краснодар", quantity=1),
        ],
        minimum_keep_per_size=2,
    )

    row_by_region = {row["region"]: row for row in result["region_rows"]}
    assert row_by_region["Центральный"]["distribution_source"] == "equal_no_demand"
    assert row_by_region["Центральный"]["status"] == "excess"
    assert row_by_region["Южный"]["status"] == "shortage"
    assert sum(item["quantity"] for item in result["movements"]) == 4


def test_ship_from_hand_size_safe_matching_and_article_fallback() -> None:
    demand_rows = [
        DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", orders_qty=6),
        DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Южный", orders_qty=4),
        DemandRow(nm_id=1002, vendor_code="VC-2", barcode=None, chrt_id=None, size_name="M", region="Центральный", orders_qty=10),
    ]
    result = compute_ship_from_hand(
        demand_rows=demand_rows,
        stock_rows=[],
        hand_rows=[
            HandStockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", size_name="S", available_qty=5),
            HandStockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-M", size_name="M", available_qty=3),
            HandStockRow(nm_id=1002, vendor_code="VC-2", barcode=None, size_name="M", available_qty=4),
        ],
        allocation_mode="redistribute",
    )

    assert sum(item["quantity"] for item in result["movements"]) == 9
    assert all(item["quantity"] > 0 for item in result["movements"])
    assert [item["reason_code"] for item in result["unmatched"]] == ["size_mismatch"]
    assert result["summary"]["unmatched"] == 1


def test_ship_from_hand_rejects_article_only_when_size_is_ambiguous() -> None:
    result = compute_ship_from_hand(
        demand_rows=[
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", orders_qty=6),
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-M", chrt_id=2, size_name="M", region="Южный", orders_qty=4),
        ],
        stock_rows=[],
        hand_rows=[HandStockRow(nm_id=1001, vendor_code="VC-1", barcode=None, size_name=None, available_qty=5)],
    )

    assert result["movements"] == []
    assert result["unmatched"][0]["reason_code"] == "article_size_ambiguous"


def test_ship_from_hand_balance_mode_and_ship_all_available() -> None:
    result = compute_ship_from_hand(
        demand_rows=[
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", orders_qty=8),
            DemandRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Южный", orders_qty=2),
        ],
        stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Центральный", warehouse_id=1, warehouse_name="Коледино", quantity=8),
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="Южный", warehouse_id=2, warehouse_name="Краснодар", quantity=0),
        ],
        hand_rows=[HandStockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", size_name="S", available_qty=6)],
        allocation_mode="balance",
        ship_all_available=True,
    )

    assert sum(item["quantity"] for item in result["movements"]) == 6
    assert {item["movement_type"] for item in result["movements"]} == {"ship_from_hand"}


def test_store_balance_is_size_safe_and_preserves_planned_quantity() -> None:
    result = compute_store_balance(
        source_stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="source", warehouse_id=1, warehouse_name="Donor", quantity=10),
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-M", chrt_id=2, size_name="M", region="source", warehouse_id=1, warehouse_name="Donor", quantity=7),
        ],
        target_stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="target", warehouse_id=2, warehouse_name="Target", quantity=1),
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-M", chrt_id=2, size_name="M", region="target", warehouse_id=2, warehouse_name="Target", quantity=6),
        ],
        mode="donor_recipient",
        min_source_stock=2,
        max_target_stock=5,
        size_aware=True,
    )

    assert result["summary"]["run_type"] == "store_balance"
    assert result["summary"]["shared_skus_count"] == 2
    assert sum(item["quantity"] for item in result["movements"]) == result["summary"]["planned_units"]
    assert all(item["movement_type"] == "store_balance" for item in result["movements"])
    assert all(item["marketplace_change"] is False for item in [result["summary"]])
    by_size = {item["size_name"]: item["quantity"] for item in result["movements"]}
    assert by_size == {"S": 4}


def test_store_balance_excludes_nm_ids() -> None:
    result = compute_store_balance(
        source_stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="source", warehouse_id=1, warehouse_name="Donor", quantity=10),
        ],
        target_stock_rows=[
            StockRow(nm_id=1001, vendor_code="VC-1", barcode="BC-S", chrt_id=1, size_name="S", region="target", warehouse_id=2, warehouse_name="Target", quantity=0),
        ],
        excluded_nm_ids=[1001],
    )

    assert result["movements"] == []
    assert result["summary"]["shared_skus_count"] == 0
