from __future__ import annotations

from decimal import Decimal
from typing import Any


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def manual_cost_price(cost: Any | None) -> Decimal:
    if cost is None:
        return Decimal("0")
    return _decimal(
        getattr(cost, "cost_price", None) or getattr(cost, "unit_cost", None)
    )


def manual_cost_seller_other_expense(cost: Any | None) -> Decimal:
    if cost is None:
        return Decimal("0")
    explicit_value = getattr(cost, "seller_other_expense", None)
    if explicit_value is not None:
        return _decimal(explicit_value)
    return _decimal(getattr(cost, "packaging_cost", None)) + _decimal(
        getattr(cost, "inbound_logistics_cost", None)
    )


def manual_cost_total_unit_cost(cost: Any | None) -> Decimal:
    return manual_cost_price(cost) + manual_cost_seller_other_expense(cost)
