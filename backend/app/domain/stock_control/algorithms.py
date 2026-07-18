from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.stock_control.allocation import largest_remainder_allocation
from app.domain.stock_control.regions import (
    normalize_excluded_regions,
    normalize_region,
)


@dataclass(frozen=True)
class DemandRow:
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    chrt_id: int | None
    size_name: str | None
    region: str
    orders_qty: int
    subject: str | None = None
    brand: str | None = None
    source: str = "finance_orders"


@dataclass(frozen=True)
class StockRow:
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    chrt_id: int | None
    size_name: str | None
    region: str | None
    warehouse_id: int | None
    warehouse_name: str | None
    quantity: int
    subject: str | None = None
    brand: str | None = None
    source: str = "finance_stock_snapshot"


@dataclass(frozen=True)
class HandStockRow:
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    size_name: str | None
    available_qty: int
    source_name: str | None = None


def _product_key(nm_id: int | None, vendor_code: str | None) -> tuple[str, str]:
    return (str(nm_id or ""), str(vendor_code or "").strip().casefold())


def _size_key(
    nm_id: int | None,
    vendor_code: str | None,
    barcode: str | None,
    chrt_id: int | None,
    size_name: str | None,
) -> tuple[str, str, str, str, str]:
    return (
        str(nm_id or ""),
        str(vendor_code or "").strip().casefold(),
        str(barcode or "").strip().casefold(),
        str(chrt_id or ""),
        str(size_name or "").strip().casefold(),
    )


def _row_identity(row: DemandRow | StockRow) -> tuple[str, str, str, str, str]:
    return _size_key(
        row.nm_id, row.vendor_code, row.barcode, row.chrt_id, row.size_name
    )


def _hand_identity(row: HandStockRow) -> tuple[str, str, str, str, str]:
    return _size_key(row.nm_id, row.vendor_code, row.barcode, None, row.size_name)


def _int(value: Any) -> int:
    try:
        return max(int(Decimal(str(value or 0))), 0)
    except Exception:
        return 0


def _float(value: Decimal | int | float) -> float:
    return float(value)


def compute_return_excess(
    *,
    demand_rows: list[DemandRow],
    stock_rows: list[StockRow],
    excluded_regions: list[str] | set[str] | tuple[str, ...] | None = None,
    minimum_keep_per_size: int = 0,
) -> dict[str, Any]:
    excluded = normalize_excluded_regions(excluded_regions)
    demand_by_key_region: dict[tuple[tuple[str, str, str, str, str], str], int] = (
        defaultdict(int)
    )
    meta_by_key: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in demand_rows:
        region = normalize_region(row.region)
        if region in excluded:
            continue
        key = _row_identity(row)
        demand_by_key_region[(key, region)] += _int(row.orders_qty)
        meta_by_key.setdefault(
            key,
            {
                "nm_id": row.nm_id,
                "vendor_code": row.vendor_code,
                "barcode": row.barcode,
                "chrt_id": row.chrt_id,
                "size_name": row.size_name,
                "subject": row.subject,
                "brand": row.brand,
            },
        )

    stock_by_key_region: dict[tuple[tuple[str, str, str, str, str], str], int] = (
        defaultdict(int)
    )
    warehouse_by_key_region: dict[
        tuple[tuple[str, str, str, str, str], str], dict[str, Any]
    ] = {}
    for row in stock_rows:
        region = normalize_region(row.region or row.warehouse_name)
        if region in excluded:
            continue
        key = _row_identity(row)
        qty = _int(row.quantity)
        stock_by_key_region[(key, region)] += qty
        meta_by_key.setdefault(
            key,
            {
                "nm_id": row.nm_id,
                "vendor_code": row.vendor_code,
                "barcode": row.barcode,
                "chrt_id": row.chrt_id,
                "size_name": row.size_name,
                "subject": row.subject,
                "brand": row.brand,
            },
        )
        if qty > 0 and (key, region) not in warehouse_by_key_region:
            warehouse_by_key_region[(key, region)] = {
                "warehouse_id": row.warehouse_id,
                "warehouse_name": row.warehouse_name,
            }

    region_rows: list[dict[str, Any]] = []
    movements: list[dict[str, Any]] = []
    for key in sorted(meta_by_key):
        regions = {
            region for item_key, region in demand_by_key_region if item_key == key
        }
        regions.update(
            region for item_key, region in stock_by_key_region if item_key == key
        )
        if not regions:
            continue
        demand_weights = {
            region: demand_by_key_region.get((key, region), 0) for region in regions
        }
        total_demand = sum(demand_weights.values())
        total_stock = sum(
            stock_by_key_region.get((key, region), 0) for region in regions
        )
        target_by_region = largest_remainder_allocation(total_stock, demand_weights)
        if total_demand == 0:
            target_by_region = largest_remainder_allocation(
                total_stock, {region: 1 for region in regions}
            )

        meta = meta_by_key[key]
        donors: list[dict[str, Any]] = []
        recipients: list[dict[str, Any]] = []
        for region in sorted(regions):
            current_stock = stock_by_key_region.get((key, region), 0)
            target_stock = target_by_region.get(region, 0)
            keep = max(_int(minimum_keep_per_size), 0)
            delta = target_stock - current_stock
            if delta < 0 and keep:
                delta = max(delta, -(max(current_stock - keep, 0)))
            status = "shortage" if delta > 0 else "excess" if delta < 0 else "balanced"
            orders = demand_by_key_region.get((key, region), 0)
            share = (
                (Decimal(orders) / Decimal(total_demand))
                if total_demand
                else Decimal("0")
            )
            warehouse = warehouse_by_key_region.get((key, region), {})
            row = {
                **meta,
                "region": region,
                "warehouse_id": warehouse.get("warehouse_id"),
                "warehouse_name": warehouse.get("warehouse_name"),
                "orders_qty": orders,
                "local_orders_qty": orders,
                "region_share": _float(share),
                "current_stock_qty": current_stock,
                "target_stock_qty": target_stock,
                "delta_qty": delta,
                "status": status,
                "localization_pct": _float(share * Decimal("100"))
                if total_demand
                else None,
                "impact_pct": abs(delta) / total_stock * 100 if total_stock else None,
                "distribution_source": "finance_orders"
                if total_demand
                else "equal_no_demand",
                "source_metadata_json": {
                    "total_demand": total_demand,
                    "total_stock": total_stock,
                },
            }
            region_rows.append(row)
            if delta < 0:
                donors.append({**row, "remaining": abs(delta)})
            elif delta > 0:
                recipients.append({**row, "remaining": delta})
        movements.extend(
            _allocate_movements(
                donors, recipients, movement_type="regional_redistribution"
            )
        )

    return {
        "region_rows": region_rows,
        "movements": movements,
        "summary": _summary(region_rows, movements),
    }


def compute_ship_from_hand(
    *,
    demand_rows: list[DemandRow],
    stock_rows: list[StockRow],
    hand_rows: list[HandStockRow],
    excluded_regions: list[str] | set[str] | tuple[str, ...] | None = None,
    allocation_mode: str = "redistribute",
    ship_all_available: bool = False,
    default_il_profile: dict[str, float] | None = None,
    minimum_history_orders: int = 10,
) -> dict[str, Any]:
    excluded = normalize_excluded_regions(excluded_regions)
    base = compute_return_excess(
        demand_rows=demand_rows, stock_rows=stock_rows, excluded_regions=excluded
    )
    demand_by_identity_region: dict[tuple[tuple[str, str, str, str, str], str], int] = (
        defaultdict(int)
    )
    demand_by_product: dict[tuple[str, str], list[DemandRow]] = defaultdict(list)
    for row in demand_rows:
        region = normalize_region(row.region)
        if region in excluded:
            continue
        demand_by_identity_region[(_row_identity(row), region)] += _int(row.orders_qty)
        demand_by_product[_product_key(row.nm_id, row.vendor_code)].append(row)

    current_by_identity_region: dict[
        tuple[tuple[str, str, str, str, str], str], int
    ] = defaultdict(int)
    for row in stock_rows:
        region = normalize_region(row.region or row.warehouse_name)
        if region in excluded:
            continue
        current_by_identity_region[(_row_identity(row), region)] += _int(row.quantity)

    movements: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    fallback_rows: list[dict[str, Any]] = []
    for hand in hand_rows:
        qty = _int(hand.available_qty)
        if qty <= 0:
            continue
        key = _hand_identity(hand)
        fallback_weights: dict[str, int | float] | None = None
        exact_regions = {
            region
            for identity, region in set(demand_by_identity_region)
            | set(current_by_identity_region)
            if identity == key
        }
        if not exact_regions:
            product_rows = demand_by_product.get(
                _product_key(hand.nm_id, hand.vendor_code), []
            )
            product_sizes = {
                str(item.size_name or "").strip().casefold()
                for item in product_rows
                if item.size_name
            }
            hand_size = str(hand.size_name or "").strip().casefold()
            if hand_size and product_sizes:
                size_rows = [
                    item
                    for item in product_rows
                    if str(item.size_name or "").strip().casefold() == hand_size
                ]
                if not size_rows:
                    unmatched.append(
                        _unmatched_hand_row(hand, qty=qty, reason="size_mismatch")
                    )
                    continue
                product_rows = size_rows
            elif not hand_size and len(product_sizes) > 1:
                unmatched.append(
                    _unmatched_hand_row(hand, qty=qty, reason="article_size_ambiguous")
                )
                continue
            elif hand_size and product_sizes and hand_size not in product_sizes:
                unmatched.append(
                    _unmatched_hand_row(hand, qty=qty, reason="size_mismatch")
                )
                continue
            exact_regions = {
                normalize_region(item.region)
                for item in product_rows
                if normalize_region(item.region) not in excluded
            }
            if exact_regions:
                fallback_weights = defaultdict(int)
                for item in product_rows:
                    region = normalize_region(item.region)
                    if region not in excluded:
                        fallback_weights[region] += _int(item.orders_qty)
            if not exact_regions and default_il_profile:
                exact_regions = {
                    normalize_region(region)
                    for region in default_il_profile
                    if normalize_region(region) not in excluded
                }
                fallback_weights = {
                    normalize_region(region): weight
                    for region, weight in default_il_profile.items()
                    if normalize_region(region) in exact_regions
                }
                fallback_rows.append(
                    {
                        "vendor_code": hand.vendor_code,
                        "nm_id": hand.nm_id,
                        "quantity": qty,
                        "distribution_source": "default_il_no_demand",
                    }
                )
            if not exact_regions:
                unmatched.append(
                    _unmatched_hand_row(hand, qty=qty, reason="no_matching_demand")
                )
                continue

        weights = (
            dict(fallback_weights)
            if fallback_weights is not None
            else _ship_weights(
                key=key,
                regions=exact_regions,
                demand_by_identity_region=demand_by_identity_region,
                current_by_identity_region=current_by_identity_region,
                allocation_mode=allocation_mode,
                default_il_profile=default_il_profile,
                minimum_history_orders=minimum_history_orders,
            )
        )
        allocated = largest_remainder_allocation(qty, weights)
        if not ship_all_available:
            need_total = sum(max(weight, 0) for weight in weights.values())
            allowed_total = min(qty, int(need_total))
            allocated = largest_remainder_allocation(allowed_total, weights)
            leftover = qty - allowed_total
            if leftover > 0:
                unmatched.append(
                    _unmatched_hand_row(
                        hand, qty=leftover, reason="leftover_after_need_cover"
                    )
                )
        for region, allocated_qty in allocated.items():
            if allocated_qty <= 0:
                continue
            movements.append(
                {
                    "nm_id": hand.nm_id,
                    "vendor_code": hand.vendor_code,
                    "barcode": hand.barcode,
                    "size_name": hand.size_name,
                    "movement_type": "ship_from_hand",
                    "donor_region": hand.source_name or "hand_stock",
                    "donor_warehouse": hand.source_name,
                    "recipient_region": region,
                    "recipient_warehouse": None,
                    "quantity": allocated_qty,
                    "priority": "P2",
                    "reason_code": allocation_mode,
                    "business_explanation": "Распределить товар из наличия по регионам дефицита. WB автоматически не изменяется.",
                    "confidence": "medium",
                    "status": "new",
                }
            )

    summary = _summary(base["region_rows"], movements)
    summary["unmatched"] = len(unmatched)
    summary["unmatched_supply_total"] = sum(
        int(row["available_qty"]) for row in unmatched
    )
    summary["fallback_localization_total"] = sum(
        int(row["quantity"]) for row in fallback_rows
    )
    summary["ship_all_available"] = bool(ship_all_available)
    summary["allocation_mode"] = allocation_mode
    return {
        "region_rows": base["region_rows"],
        "movements": movements,
        "unmatched": unmatched,
        "fallback_rows": fallback_rows,
        "summary": summary,
    }


def compute_store_balance(
    *,
    source_stock_rows: list[StockRow],
    target_stock_rows: list[StockRow],
    mode: str = "donor_recipient",
    min_source_stock: int = 0,
    max_target_stock: int | None = None,
    size_aware: bool = True,
    excluded_nm_ids: list[int] | set[int] | tuple[int, ...] | None = None,
) -> dict[str, Any]:
    excluded = {int(value) for value in (excluded_nm_ids or []) if value is not None}
    source_by_key, source_meta = _stock_totals_for_balance(
        source_stock_rows, size_aware=size_aware, excluded_nm_ids=excluded
    )
    target_by_key, target_meta = _stock_totals_for_balance(
        target_stock_rows, size_aware=size_aware, excluded_nm_ids=excluded
    )
    shared_keys = sorted(set(source_by_key) & set(target_by_key))
    region_rows: list[dict[str, Any]] = []
    movements: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for key in shared_keys:
        source_qty = source_by_key.get(key, 0)
        target_qty = target_by_key.get(key, 0)
        if source_qty <= 0:
            continue
        meta = {**target_meta.get(key, {}), **source_meta.get(key, {})}
        if mode == "equalize":
            target_each = (source_qty + target_qty) // 2
            movable = max(source_qty - max(target_each, _int(min_source_stock)), 0)
            needed = max(target_each - target_qty, 0)
            target_stock = target_each
        else:
            movable = max(source_qty - _int(min_source_stock), 0)
            needed = (
                movable
                if max_target_stock in (None, 0)
                else max(_int(max_target_stock) - target_qty, 0)
            )
            target_stock = target_qty + min(movable, needed)
        qty = min(movable, needed)
        source_row = {
            **meta,
            "region": "source_account",
            "orders_qty": 0,
            "local_orders_qty": 0,
            "region_share": 0,
            "current_stock_qty": source_qty,
            "target_stock_qty": source_qty - qty,
            "delta_qty": -qty,
            "status": "excess" if qty > 0 else "balanced",
            "localization_pct": None,
            "impact_pct": (qty / source_qty * 100) if source_qty else None,
            "distribution_source": "store_balance",
            "source_metadata_json": {
                "mode": mode,
                "size_aware": size_aware,
                "role": "source",
            },
        }
        target_row = {
            **meta,
            "region": "target_account",
            "orders_qty": 0,
            "local_orders_qty": 0,
            "region_share": 0,
            "current_stock_qty": target_qty,
            "target_stock_qty": target_stock,
            "delta_qty": qty,
            "status": "shortage" if qty > 0 else "balanced",
            "localization_pct": None,
            "impact_pct": (qty / max(target_qty, 1) * 100) if qty else None,
            "distribution_source": "store_balance",
            "source_metadata_json": {
                "mode": mode,
                "size_aware": size_aware,
                "role": "target",
            },
        }
        region_rows.extend([source_row, target_row])
        if qty <= 0:
            unmatched.append(
                {
                    **meta,
                    "source_qty": source_qty,
                    "target_qty": target_qty,
                    "reason_code": "no_movable_quantity",
                }
            )
            continue
        movements.append(
            {
                **meta,
                "movement_type": "store_balance",
                "donor_region": "source_account",
                "donor_warehouse": None,
                "recipient_region": "target_account",
                "recipient_warehouse": None,
                "quantity": qty,
                "priority": "P2",
                "reason_code": mode,
                "business_explanation": "Локальный план балансировки между аккаунтами. WB автоматически не изменяется.",
                "confidence": "medium",
                "status": "new",
            }
        )
    missing_target = sorted(set(source_by_key) - set(target_by_key))
    for key in missing_target:
        meta = source_meta.get(key, {})
        unmatched.append(
            {
                **meta,
                "source_qty": source_by_key.get(key, 0),
                "target_qty": 0,
                "reason_code": "no_shared_target_sku",
            }
        )
    summary = _summary(region_rows, movements)
    summary.update(
        {
            "run_type": "store_balance",
            "mode": mode,
            "size_aware": bool(size_aware),
            "source_skus_count": len(source_by_key),
            "target_skus_count": len(target_by_key),
            "shared_skus_count": len(shared_keys),
            "source_excess_units": sum(
                int(item.get("quantity") or 0) for item in movements
            ),
            "target_shortage_units": sum(
                int(item.get("quantity") or 0) for item in movements
            ),
            "planned_units": sum(int(item.get("quantity") or 0) for item in movements),
            "skus_count": len(
                {
                    (
                        item.get("nm_id"),
                        item.get("vendor_code"),
                        item.get("barcode"),
                        item.get("size_name"),
                    )
                    for item in movements
                }
            ),
            "unmatched": len(unmatched),
        }
    )
    return {
        "region_rows": region_rows,
        "movements": movements,
        "unmatched": unmatched,
        "summary": summary,
    }


def _stock_totals_for_balance(
    rows: list[StockRow],
    *,
    size_aware: bool,
    excluded_nm_ids: set[int],
) -> tuple[dict[tuple[str, ...], int], dict[tuple[str, ...], dict[str, Any]]]:
    totals: dict[tuple[str, ...], int] = defaultdict(int)
    meta: dict[tuple[str, ...], dict[str, Any]] = {}
    for row in rows:
        if row.nm_id is not None and int(row.nm_id) in excluded_nm_ids:
            continue
        key = (
            _row_identity(row)
            if size_aware
            else _product_key(row.nm_id, row.vendor_code)
        )
        qty = _int(row.quantity)
        totals[key] += qty
        meta.setdefault(
            key,
            {
                "nm_id": row.nm_id,
                "vendor_code": row.vendor_code,
                "barcode": row.barcode if size_aware else None,
                "chrt_id": row.chrt_id if size_aware else None,
                "size_name": row.size_name if size_aware else None,
                "subject": row.subject,
                "brand": row.brand,
            },
        )
    return totals, meta


def _ship_weights(
    *,
    key: tuple[str, str, str, str, str],
    regions: set[str],
    demand_by_identity_region: dict[tuple[tuple[str, str, str, str, str], str], int],
    current_by_identity_region: dict[tuple[tuple[str, str, str, str, str], str], int],
    allocation_mode: str,
    default_il_profile: dict[str, float] | None,
    minimum_history_orders: int,
) -> dict[str, int | float]:
    demand = {
        region: demand_by_identity_region.get((key, region), 0) for region in regions
    }
    total_demand = sum(demand.values())
    if total_demand < max(int(minimum_history_orders or 0), 0) and default_il_profile:
        return {
            normalize_region(region): weight
            for region, weight in default_il_profile.items()
            if normalize_region(region) in regions
        }
    if allocation_mode == "balance":
        current = {
            region: current_by_identity_region.get((key, region), 0)
            for region in regions
        }
        pool = sum(current.values()) + max(sum(demand.values()), 1)
        target = largest_remainder_allocation(
            pool, demand if total_demand else {region: 1 for region in regions}
        )
        return {
            region: max(target.get(region, 0) - current.get(region, 0), 0)
            for region in regions
        }
    return {
        region: max(
            demand.get(region, 0) - current_by_identity_region.get((key, region), 0), 0
        )
        for region in regions
    }


def _allocate_movements(
    donors: list[dict[str, Any]],
    recipients: list[dict[str, Any]],
    *,
    movement_type: str,
) -> list[dict[str, Any]]:
    movements: list[dict[str, Any]] = []
    donor_index = 0
    recipient_index = 0
    donors = sorted(
        donors, key=lambda row: (-int(row["remaining"]), str(row["region"]))
    )
    recipients = sorted(
        recipients, key=lambda row: (-int(row["remaining"]), str(row["region"]))
    )
    while donor_index < len(donors) and recipient_index < len(recipients):
        donor = donors[donor_index]
        recipient = recipients[recipient_index]
        qty = min(int(donor["remaining"]), int(recipient["remaining"]))
        if qty > 0:
            movements.append(
                {
                    "nm_id": donor.get("nm_id") or recipient.get("nm_id"),
                    "vendor_code": donor.get("vendor_code")
                    or recipient.get("vendor_code"),
                    "barcode": donor.get("barcode") or recipient.get("barcode"),
                    "size_name": donor.get("size_name") or recipient.get("size_name"),
                    "movement_type": movement_type,
                    "donor_region": donor.get("region"),
                    "donor_warehouse": donor.get("warehouse_name"),
                    "recipient_region": recipient.get("region"),
                    "recipient_warehouse": recipient.get("warehouse_name"),
                    "quantity": qty,
                    "priority": "P2" if movement_type == "ship_from_hand" else "P1",
                    "reason_code": "regional_delta",
                    "business_explanation": "Рекомендация по региональному перераспределению. WB автоматически не изменяется.",
                    "confidence": "medium",
                    "status": "new",
                }
            )
        donor["remaining"] = int(donor["remaining"]) - qty
        recipient["remaining"] = int(recipient["remaining"]) - qty
        if donor["remaining"] <= 0:
            donor_index += 1
        if recipient["remaining"] <= 0:
            recipient_index += 1
    return movements


def _unmatched_hand_row(hand: HandStockRow, *, qty: int, reason: str) -> dict[str, Any]:
    return {
        "nm_id": hand.nm_id,
        "vendor_code": hand.vendor_code,
        "barcode": hand.barcode,
        "size_name": hand.size_name,
        "available_qty": qty,
        "source_name": hand.source_name,
        "matching_status": "unmatched",
        "reason_code": reason,
        "comment": "Несовпадение размера / size mismatch"
        if reason == "size_mismatch"
        else reason,
    }


def _summary(
    region_rows: list[dict[str, Any]], movements: list[dict[str, Any]]
) -> dict[str, Any]:
    statuses = defaultdict(int)
    for row in region_rows:
        statuses[str(row.get("status") or "unknown")] += 1
    movement_qty = sum(int(item.get("quantity") or 0) for item in movements)
    return {
        "region_rows": len(region_rows),
        "shortage_regions": statuses["shortage"],
        "excess_regions": statuses["excess"],
        "balanced_regions": statuses["balanced"],
        "movements": len(movements),
        "movement_qty": movement_qty,
        "products": len(
            {(row.get("nm_id"), row.get("vendor_code")) for row in region_rows}
        ),
        "regions": len({row.get("region") for row in region_rows}),
        "marketplace_change": False,
        "can_execute": False,
    }
