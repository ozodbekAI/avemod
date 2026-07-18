from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Iterable


@dataclass(frozen=True)
class StockSnapshotState:
    stat_date: date
    quantity: Decimal
    quantity_full: Decimal
    in_way_to_client: Decimal
    in_way_from_client: Decimal
    avg_sales_per_day_30d: Decimal | None
    days_of_stock: Decimal | None


def optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def is_total_stock_row(warehouse_name: str | None) -> bool:
    return "всего" in str(warehouse_name or "").strip().lower()


def _row_has_quantity(row: Any) -> bool:
    return (
        optional_decimal(getattr(row, "quantity", None)) is not None
        or optional_decimal(getattr(row, "quantity_full", None)) is not None
    )


def _row_quantity_value(row: Any, *, prefer_quantity_full: bool) -> Decimal:
    quantity = optional_decimal(getattr(row, "quantity", None))
    quantity_full = optional_decimal(getattr(row, "quantity_full", None))
    if prefer_quantity_full:
        return quantity_full or quantity or Decimal("0")
    return quantity if quantity is not None else quantity_full or Decimal("0")


def _aggregate_same_day_rows(rows: list[Any], *, stat_date: date) -> StockSnapshotState:
    quantity_rows = [row for row in rows if _row_has_quantity(row)]
    total_rows = [
        row
        for row in quantity_rows
        if is_total_stock_row(getattr(row, "warehouse_name", None))
    ]
    quantity_source = total_rows or quantity_rows or rows

    latest_rows = rows
    transit_rows = [row for row in latest_rows if not _row_has_quantity(row)]
    transit_source = transit_rows or quantity_source

    quantity = sum(
        (
            _row_quantity_value(
                row,
                prefer_quantity_full=bool(total_rows),
            )
            for row in quantity_source
        ),
        start=Decimal("0"),
    )
    in_way_to_client = sum(
        (
            optional_decimal(getattr(row, "in_way_to_client", None)) or Decimal("0")
            for row in transit_source
        ),
        start=Decimal("0"),
    )
    in_way_from_client = sum(
        (
            optional_decimal(getattr(row, "in_way_from_client", None)) or Decimal("0")
            for row in transit_source
        ),
        start=Decimal("0"),
    )

    avg_sales_candidates = [
        optional_decimal(getattr(row, "avg_sales_per_day_30d", None))
        for row in quantity_source
        if optional_decimal(getattr(row, "avg_sales_per_day_30d", None)) is not None
    ]
    avg_sales = max(avg_sales_candidates, default=None)
    days_of_stock = (
        (quantity / avg_sales) if avg_sales is not None and avg_sales > 0 else None
    )
    return StockSnapshotState(
        stat_date=stat_date,
        quantity=quantity,
        quantity_full=quantity,
        in_way_to_client=in_way_to_client,
        in_way_from_client=in_way_from_client,
        avg_sales_per_day_30d=avg_sales,
        days_of_stock=days_of_stock,
    )


def latest_stock_snapshot(rows: Iterable[Any]) -> StockSnapshotState | None:
    rows_list = list(rows)
    if not rows_list:
        return None
    rows_by_date: dict[date, list[Any]] = defaultdict(list)
    for row in rows_list:
        rows_by_date[getattr(row, "stat_date")].append(row)

    sorted_dates = sorted(rows_by_date.keys(), reverse=True)
    latest_quantity_date = next(
        (
            stat_date
            for stat_date in sorted_dates
            if any(_row_has_quantity(row) for row in rows_by_date[stat_date])
        ),
        sorted_dates[0],
    )
    snapshot = _aggregate_same_day_rows(
        rows_by_date[latest_quantity_date], stat_date=latest_quantity_date
    )

    latest_date = sorted_dates[0]
    if latest_date != latest_quantity_date:
        latest_rows = rows_by_date[latest_date]
        transit_rows = [row for row in latest_rows if not _row_has_quantity(row)]
        if transit_rows:
            snapshot = StockSnapshotState(
                stat_date=latest_date,
                quantity=snapshot.quantity,
                quantity_full=snapshot.quantity_full,
                in_way_to_client=sum(
                    (
                        optional_decimal(getattr(row, "in_way_to_client", None))
                        or Decimal("0")
                        for row in transit_rows
                    ),
                    start=Decimal("0"),
                ),
                in_way_from_client=sum(
                    (
                        optional_decimal(getattr(row, "in_way_from_client", None))
                        or Decimal("0")
                        for row in transit_rows
                    ),
                    start=Decimal("0"),
                ),
                avg_sales_per_day_30d=snapshot.avg_sales_per_day_30d,
                days_of_stock=snapshot.days_of_stock,
            )
    return snapshot


def stock_snapshot_on_or_before(
    rows: Iterable[Any], *, target_date: date, strict_before: bool = False
) -> StockSnapshotState | None:
    if strict_before:
        relevant_rows = [row for row in rows if getattr(row, "stat_date") < target_date]
    else:
        relevant_rows = [
            row for row in rows if getattr(row, "stat_date") <= target_date
        ]
    return latest_stock_snapshot(relevant_rows)
