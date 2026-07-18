from __future__ import annotations

from decimal import Decimal, ROUND_FLOOR


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def largest_remainder_allocation(
    total: int, weights: dict[str, int | float | Decimal]
) -> dict[str, int]:
    """Allocate integer total across keys while preserving the exact sum."""

    safe_total = max(int(total or 0), 0)
    keys = list(weights)
    if safe_total <= 0:
        return {key: 0 for key in keys}
    positive = {
        key: _decimal(value) for key, value in weights.items() if _decimal(value) > 0
    }
    if not positive:
        allocation = {key: 0 for key in keys}
        if keys:
            allocation[keys[0]] = safe_total
        return allocation

    weight_sum = sum(positive.values(), Decimal("0"))
    allocation: dict[str, int] = {key: 0 for key in keys}
    remainders: list[tuple[Decimal, str]] = []
    allocated = 0
    for key, weight in positive.items():
        raw = (Decimal(safe_total) * weight) / weight_sum
        floor_value = int(raw.to_integral_value(rounding=ROUND_FLOOR))
        allocation[key] = floor_value
        allocated += floor_value
        remainders.append((raw - Decimal(floor_value), key))

    for _remainder, key in sorted(remainders, key=lambda item: (-item[0], item[1]))[
        : safe_total - allocated
    ]:
        allocation[key] += 1
    return allocation
