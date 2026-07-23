from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.problem_engine import MetricSourceReference, ProductMetricResolution, ResolvedMetricValue
from app.services.problem_engine.price_safety import PriceSafetyCalculator


def _resolution(values: dict[str, Any], *, missing: set[str] | None = None, problem_code: str = "overstock_slow_moving") -> ProductMetricResolution:
    missing = missing or set()
    result = ProductMetricResolution(
        account_id=1,
        nm_id=1001,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 7, 6),
    )
    metric_codes = list(dict.fromkeys([*PriceSafetyCalculator().required_metric_codes(problem_code), *values.keys(), *(missing or set())]))
    for code in metric_codes:
        is_missing = code in missing or code not in values or values.get(code) is None
        result.metrics[code] = ResolvedMetricValue(
            metric_code=code,
            value=None if is_missing else values[code],
            value_type="percent" if code == "margin_pct" else "money",
            unit="%" if code == "margin_pct" else "RUB",
            trust_state="blocked" if is_missing else "confirmed",
            is_missing=is_missing,
            missing_reason="source_data_missing" if is_missing else None,
            evidence=MetricSourceReference(
                source_module="test",
                source_table="test_unit_economics",
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
                row_count=0 if is_missing else 1,
            ),
        )
        if is_missing:
            result.missing_metrics.append(code)
    return result


def test_price_decrease_blocked_when_discount_would_break_target_margin() -> None:
    safety = PriceSafetyCalculator(target_margin_pct=Decimal("10"), proposed_discount_pct=Decimal("10")).evaluate(
        problem_code="overstock_slow_moving",
        resolved=_resolution(
            {
                "price_current": Decimal("120"),
                "price_after_discount": Decimal("120"),
                "cost_price": Decimal("80"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            }
        ),
    )

    assert safety is not None
    assert safety.min_safe_price == Decimal("114.44")
    assert safety.margin_after_discount == Decimal("4.63")
    assert safety.can_recommend_price_decrease is False
    assert "price_decrease_blocked_by_min_safe_price" in safety.warnings


def test_missing_cost_blocks_price_decrease_recommendation() -> None:
    safety = PriceSafetyCalculator().evaluate(
        problem_code="overstock_slow_moving",
        resolved=_resolution(
            {
                "price_current": Decimal("160"),
                "price_after_discount": Decimal("150"),
                "commission_per_unit": Decimal("10"),
                "logistics_per_unit": Decimal("5"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            },
            missing={"cost_price"},
        ),
    )

    assert safety is not None
    assert safety.status == "data_incomplete"
    assert safety.can_recommend_price_decrease is False
    assert "cost_price" in safety.missing_required_metrics
    assert safety.linked_data_blocker and safety.linked_data_blocker["problem_code"] == "missing_cost_blocks_profit"


def test_safe_discount_calculated_from_min_safe_price() -> None:
    safety = PriceSafetyCalculator(target_margin_pct=Decimal("10"), proposed_discount_pct=Decimal("10")).evaluate(
        problem_code="overstock_slow_moving",
        resolved=_resolution(
            {
                "price_current": Decimal("200"),
                "price_after_discount": Decimal("200"),
                "cost_price": Decimal("90"),
                "commission_per_unit": Decimal("10"),
                "logistics_per_unit": Decimal("5"),
                "acquiring_per_unit": Decimal("3"),
                "storage_fee_per_unit": Decimal("1"),
            }
        ),
    )

    assert safety is not None
    assert safety.min_safe_price == Decimal("121.11")
    assert safety.max_safe_discount_pct == Decimal("39.44")
    assert safety.margin_after_discount == Decimal("39.44")
    assert safety.can_recommend_price_decrease is True


def test_negative_profit_recommendation_produces_target_price() -> None:
    calculator = PriceSafetyCalculator(target_margin_pct=Decimal("10"))
    safety = calculator.evaluate(
        problem_code="negative_unit_profit",
        resolved=_resolution(
            {
                "price_current": Decimal("100"),
                "price_after_discount": Decimal("100"),
                "cost_price": Decimal("90"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
                "unit_profit": Decimal("-13"),
                "margin_pct": Decimal("-13"),
            },
            problem_code="negative_unit_profit",
        ),
    )
    recommendation = calculator.recommendation(
        problem_code="negative_unit_profit",
        base_recommendation="Проверьте цену.",
        price_safety=safety,
    )

    assert safety is not None
    assert safety.target_price == Decimal("125.56")
    assert safety.can_recommend_price_increase is True
    assert "Поднимите цену минимум до 125.56 RUB" in recommendation
    assert "себестоимость" in recommendation
    assert "Increase price" not in recommendation


def test_negative_profit_recommendation_does_not_raise_price_when_current_price_is_safe() -> None:
    calculator = PriceSafetyCalculator(target_margin_pct=Decimal("10"))
    safety = calculator.evaluate(
        problem_code="negative_unit_profit",
        resolved=_resolution(
            {
                "price_current": Decimal("18900"),
                "price_after_discount": Decimal("15876"),
                "cost_price": Decimal("3773"),
                "commission_per_unit": Decimal("1589.72"),
                "logistics_per_unit": Decimal("2694.54"),
                "acquiring_per_unit": Decimal("553.89"),
                "storage_fee_per_unit": Decimal("0"),
                "unit_profit": Decimal("-2385.19"),
                "margin_pct": Decimal("35.91"),
            },
            problem_code="negative_unit_profit",
        ),
    )
    recommendation = calculator.recommendation(
        problem_code="negative_unit_profit",
        base_recommendation="Проверьте цену.",
        price_safety=safety,
    )

    assert safety is not None
    assert safety.target_price == Decimal("9567.94")
    assert safety.can_recommend_price_increase is False
    assert safety.status == "price_ok"
    assert "Поднимите цену" not in recommendation
    assert "Цена уже выше безопасного минимума" in recommendation


def test_price_below_safe_margin_does_not_raise_when_current_effective_price_is_safe() -> None:
    calculator = PriceSafetyCalculator(target_margin_pct=Decimal("10"))
    safety = calculator.evaluate(
        problem_code="price_below_safe_margin",
        resolved=_resolution(
            {
                "price_current": Decimal("18900"),
                "price_after_discount": Decimal("15876"),
                "cost_price": Decimal("3773"),
                "commission_per_unit": Decimal("1589.72"),
                "logistics_per_unit": Decimal("2694.54"),
                "acquiring_per_unit": Decimal("553.89"),
                "storage_fee_per_unit": Decimal("0"),
                "unit_profit": Decimal("-2385.19"),
                "margin_pct": Decimal("35.91"),
            },
            problem_code="price_below_safe_margin",
        ),
    )
    recommendation = calculator.recommendation(
        problem_code="price_below_safe_margin",
        base_recommendation="Проверьте цену.",
        price_safety=safety,
    )

    assert safety is not None
    assert safety.target_price == Decimal("9567.94")
    assert safety.can_recommend_price_increase is False
    assert "Поднимите эффективную цену" not in recommendation
    assert "Не повышайте цену автоматически" in recommendation
    assert "формулу маржи" in recommendation


def test_dead_stock_safe_promo_is_blocked_when_margin_would_break() -> None:
    calculator = PriceSafetyCalculator(target_margin_pct=Decimal("10"), proposed_discount_pct=Decimal("10"))
    safety = calculator.evaluate(
        problem_code="dead_stock",
        resolved=_resolution(
            {
                "price_current": Decimal("120"),
                "price_after_discount": Decimal("120"),
                "cost_price": Decimal("80"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            },
            problem_code="dead_stock",
        ),
    )
    actions = calculator.allowed_actions(
        base_actions=["safe_promo", "bundle", "review_content"],
        price_safety=safety,
    )
    recommendation = calculator.recommendation(
        problem_code="dead_stock",
        base_recommendation="Review safe liquidation.",
        price_safety=safety,
    )

    assert safety is not None
    assert safety.can_recommend_price_decrease is False
    assert "safe_promo" not in actions
    assert "Не снижайте цену" in recommendation
    assert "Do not lower price" not in recommendation
