from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.schemas.problem_engine import ProductMetricResolution


PRICE_SAFETY_PROBLEM_CODES = frozenset(
    {
        "overstock_slow_moving",
        "negative_unit_profit",
        "promo_not_profitable",
        "price_below_safe_margin",
        "dead_stock",
    }
)

PRICE_DECREASE_ACTIONS = frozenset(
    {"safe_promo", "review_promo", "reduce_promo", "review_price"}
)
PRICE_SAFETY_METRICS = (
    "price_current",
    "price_after_discount",
    "cost_price",
    "commission_per_unit",
    "logistics_per_unit",
    "acquiring_per_unit",
    "storage_fee_per_unit",
    "unit_profit",
    "margin_pct",
)
REQUIRED_UNIT_ECONOMICS_METRICS = (
    "cost_price",
    "commission_per_unit",
    "logistics_per_unit",
    "acquiring_per_unit",
    "storage_fee_per_unit",
)


@dataclass(slots=True)
class PriceSafetyResult:
    problem_code: str
    target_margin_pct: Decimal
    proposed_discount_pct: Decimal
    current_price: Decimal | None
    price_after_discount: Decimal | None
    reference_price: Decimal | None
    min_safe_price: Decimal | None
    break_even_price: Decimal | None
    target_price: Decimal | None
    max_safe_discount_pct: Decimal | None
    margin_after_discount: Decimal | None
    margin_after_recommended_price: Decimal | None
    total_unit_economics_cost: Decimal | None
    missing_required_metrics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    trust_notes: list[str] = field(default_factory=list)
    component_breakdown: list[dict[str, Any]] = field(default_factory=list)
    linked_data_blocker: dict[str, Any] | None = None

    @property
    def is_data_complete(self) -> bool:
        return not self.missing_required_metrics and self.reference_price is not None

    @property
    def can_recommend_price_decrease(self) -> bool:
        return bool(
            self.is_data_complete
            and self.max_safe_discount_pct is not None
            and self.max_safe_discount_pct > 0
            and self.margin_after_discount is not None
            and self.margin_after_discount >= self.target_margin_pct
        )

    @property
    def can_recommend_price_increase(self) -> bool:
        return bool(
            self.is_data_complete
            and self.reference_price is not None
            and self.target_price is not None
            and self.reference_price < self.target_price
        )

    @property
    def status(self) -> str:
        if not self.is_data_complete:
            return "data_incomplete"
        if self.problem_code == "negative_unit_profit":
            return (
                "increase_recommended"
                if self.can_recommend_price_increase
                else "price_ok"
            )
        return "safe" if self.can_recommend_price_decrease else "unsafe"

    @property
    def reason(self) -> str:
        if not self.is_data_complete:
            missing = self._metric_list(self.missing_required_metrics)
            return f"Рекомендация по цене заблокирована, пока не заполнена экономика единицы товара: {missing}."
        if (
            self.problem_code == "negative_unit_profit"
            and self.can_recommend_price_increase
        ):
            return f"Текущая цена ниже цены для целевой маржи: {self._money(self.target_price)}."
        if (
            self.problem_code == "negative_unit_profit"
            and self.reference_price is not None
            and self.min_safe_price is not None
            and self.reference_price >= self.min_safe_price
        ):
            return f"Текущая цена выше безопасного минимума: {self._money(self.min_safe_price)}."
        if self.can_recommend_price_decrease:
            return f"Скидка остаётся безопасной, пока цена не ниже {self._money(self.min_safe_price)}."
        return f"Текущая цена уже на уровне безопасного минимума или ниже: {self._money(self.min_safe_price)}."

    def render_values(self) -> dict[str, Any]:
        return {
            "target_margin_pct": self.target_margin_pct,
            "min_safe_price": self.min_safe_price,
            "break_even_price": self.break_even_price,
            "target_price": self.target_price,
            "max_safe_discount_pct": self.max_safe_discount_pct,
            "margin_after_discount": self.margin_after_discount,
            "margin_after_recommended_price": self.margin_after_recommended_price,
            "price_safety_status": self.status,
            "price_safety_reason": self.reason,
        }

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "problem_code": self.problem_code,
            "status": self.status,
            "reason": self.reason,
            "target_margin_pct": self.target_margin_pct,
            "proposed_discount_pct": self.proposed_discount_pct,
            "current_price": self.current_price,
            "price_after_discount": self.price_after_discount,
            "reference_price": self.reference_price,
            "min_safe_price": self.min_safe_price,
            "break_even_price": self.break_even_price,
            "target_price": self.target_price,
            "safe_price_range": {
                "min": self.min_safe_price,
                "max": self.reference_price,
                "currency": "RUB",
            },
            "max_safe_discount_pct": self.max_safe_discount_pct,
            "margin_after_discount": self.margin_after_discount,
            "margin_after_recommended_price": self.margin_after_recommended_price,
            "total_unit_economics_cost": self.total_unit_economics_cost,
            "missing_required_metrics": list(self.missing_required_metrics),
            "can_recommend_price_decrease": self.can_recommend_price_decrease,
            "can_recommend_price_increase": self.can_recommend_price_increase,
            "component_breakdown": list(self.component_breakdown),
            "linked_data_blocker": self.linked_data_blocker,
            "warnings": list(self.warnings),
            "trust_notes": list(self.trust_notes),
        }

    @staticmethod
    def _money(value: Decimal | None) -> str:
        if value is None:
            return "неизвестно"
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)} RUB"

    @classmethod
    def _metric_label(cls, code: str) -> str:
        labels = {
            "price_current": "текущая цена",
            "price_after_discount": "эффективная цена после скидки",
            "price_after_discount_or_price_current": "эффективная или текущая цена",
            "cost_price": "себестоимость",
            "commission_per_unit": "комиссия",
            "logistics_per_unit": "логистика",
            "acquiring_per_unit": "эквайринг",
            "storage_fee_per_unit": "хранение",
            "unit_profit": "прибыль на единицу",
            "margin_pct": "маржа",
        }
        return labels.get(str(code), str(code))

    @classmethod
    def _metric_list(cls, codes: list[str]) -> str:
        return ", ".join(cls._metric_label(code) for code in codes)


class PriceSafetyCalculator:
    """Unit-economics guard for dynamic price, promo, and margin recommendations."""

    def __init__(
        self,
        *,
        target_margin_pct: Decimal | int | str = Decimal("10"),
        proposed_discount_pct: Decimal | int | str = Decimal("10"),
    ) -> None:
        self.target_margin_pct = self._decimal(target_margin_pct) or Decimal("10")
        self.proposed_discount_pct = self._decimal(proposed_discount_pct) or Decimal(
            "10"
        )

    @classmethod
    def _metric_label(cls, code: str) -> str:
        return PriceSafetyResult._metric_label(code)

    @classmethod
    def _metric_list(cls, codes: list[str]) -> str:
        return ", ".join(cls._metric_label(code) for code in codes)

    def required_metric_codes(self, problem_code: str) -> list[str]:
        problem_code = str(problem_code)
        if problem_code not in PRICE_SAFETY_PROBLEM_CODES:
            return []
        if problem_code in {"overstock_slow_moving", "dead_stock"}:
            return [
                "price_current",
                "price_after_discount",
                *REQUIRED_UNIT_ECONOMICS_METRICS,
            ]
        return list(PRICE_SAFETY_METRICS)

    def evaluate(
        self, *, problem_code: str, resolved: ProductMetricResolution
    ) -> PriceSafetyResult | None:
        if str(problem_code) not in PRICE_SAFETY_PROBLEM_CODES:
            return None

        values = {
            code: self._metric_decimal(resolved, code) for code in PRICE_SAFETY_METRICS
        }
        current_price = values.get("price_current")
        price_after_discount = values.get("price_after_discount")
        reference_price = self._positive(price_after_discount) or self._positive(
            current_price
        )
        missing = [
            code
            for code in REQUIRED_UNIT_ECONOMICS_METRICS
            if self._metric_missing(resolved, code) or values.get(code) is None
        ]
        if reference_price is None:
            missing.append("price_after_discount_or_price_current")
        missing = list(dict.fromkeys(missing))

        component_breakdown = self._component_breakdown(
            values, reference_price=reference_price
        )
        total_cost = self._total_unit_cost(values) if not missing else None
        break_even = (
            self._quantize_money(total_cost) if total_cost is not None else None
        )
        min_safe_price = (
            self._min_safe_price(total_cost) if total_cost is not None else None
        )
        target_price = min_safe_price
        max_discount = self._max_safe_discount_pct(
            reference_price=reference_price, min_safe_price=min_safe_price
        )
        proposed_price = self._discounted_price(
            reference_price, self.proposed_discount_pct
        )
        margin_after_discount = self._margin_pct(proposed_price, total_cost)
        margin_after_recommended_price = self._margin_pct(target_price, total_cost)

        result = PriceSafetyResult(
            problem_code=str(problem_code),
            target_margin_pct=self._quantize_pct(self.target_margin_pct),
            proposed_discount_pct=self._quantize_pct(self.proposed_discount_pct),
            current_price=self._quantize_money(current_price),
            price_after_discount=self._quantize_money(price_after_discount),
            reference_price=self._quantize_money(reference_price),
            min_safe_price=self._quantize_money(min_safe_price),
            break_even_price=break_even,
            target_price=self._quantize_money(target_price),
            max_safe_discount_pct=self._quantize_pct(max_discount),
            margin_after_discount=self._quantize_pct(margin_after_discount),
            margin_after_recommended_price=self._quantize_pct(
                margin_after_recommended_price
            ),
            total_unit_economics_cost=self._quantize_money(total_cost),
            missing_required_metrics=missing,
            component_breakdown=component_breakdown,
            linked_data_blocker=self._linked_data_blocker(missing),
        )
        result.warnings = self._warnings(result)
        result.trust_notes = self._trust_notes(result)
        return result

    def allowed_actions(
        self, *, base_actions: list[str], price_safety: PriceSafetyResult | None
    ) -> list[str]:
        if price_safety is None:
            return list(base_actions)
        if (
            price_safety.problem_code in {"overstock_slow_moving", "dead_stock"}
            and not price_safety.can_recommend_price_decrease
        ):
            actions = [
                action
                for action in base_actions
                if action not in PRICE_DECREASE_ACTIONS
            ]
            if price_safety.missing_required_metrics:
                for action in ("upload_cost", "map_sku", "review_cost"):
                    if action not in actions:
                        actions.insert(0, action)
            return actions
        return list(base_actions)

    def recommendation(
        self,
        *,
        problem_code: str,
        base_recommendation: str,
        price_safety: PriceSafetyResult | None,
    ) -> str:
        if price_safety is None:
            return base_recommendation
        if problem_code in {"overstock_slow_moving", "dead_stock"}:
            if price_safety.missing_required_metrics:
                missing = self._metric_list(price_safety.missing_required_metrics)
                return (
                    "Пока не снижайте цену и не запускайте скидку: не хватает данных по себестоимости или комиссиям "
                    f"({missing}). Сначала исправьте данные, а параллельно проверьте карточку, рекламу, комплекты и качество спроса."
                )
            if price_safety.can_recommend_price_decrease:
                opening = (
                    "Распродажная скидка"
                    if problem_code == "dead_stock"
                    else "Промо или скидка"
                )
                return (
                    f"{opening} безопасна только до {price_safety.max_safe_discount_pct}%: держите цену после скидки "
                    f"не ниже {price_safety.min_safe_price} RUB, чтобы сохранить маржу {price_safety.target_margin_pct}%. "
                    "Дополнительно проверьте карточку, рекламу и комплекты для ускорения продаж."
                )
            return (
                f"Не снижайте цену: безопасный минимум {price_safety.min_safe_price} RUB, а текущая эффективная цена "
                f"{price_safety.reference_price} RUB. Вместо скидки проверьте карточку, рекламу, комплекты или структуру затрат."
            )
        if problem_code == "negative_unit_profit":
            if price_safety.missing_required_metrics:
                missing = self._metric_list(price_safety.missing_required_metrics)
                return (
                    "Пока не показывайте рекомендацию по цене: не хватает данных по себестоимости или комиссиям "
                    f"({missing}). Исправьте данные, затем перепроверьте цену, рекламу, промо, логистику и себестоимость."
                )
            if price_safety.target_price is not None:
                drivers = ", ".join(
                    item["label"]
                    for item in price_safety.component_breakdown[:3]
                    if item.get("kind") == "cost"
                )
                suffix = (
                    f" Основные причины отрицательной прибыли: {drivers}."
                    if drivers
                    else ""
                )
                if not price_safety.can_recommend_price_increase:
                    return (
                        f"Цена уже выше безопасного минимума {price_safety.min_safe_price} RUB для маржи "
                        f"{price_safety.target_margin_pct}%.{suffix} Проверьте себестоимость, рекламу, промо, "
                        "логистику, комиссии и возвраты вместо автоматического повышения цены."
                    )
                return (
                    f"Поднимите цену минимум до {price_safety.target_price} RUB, чтобы выйти на целевую маржу "
                    f"{price_safety.target_margin_pct}%.{suffix} Затем проверьте себестоимость, рекламу, промо и логистику."
                )
        if problem_code == "price_below_safe_margin":
            if price_safety.missing_required_metrics:
                missing = self._metric_list(price_safety.missing_required_metrics)
                return (
                    "Пока не показывайте целевую цену: не хватает данных по себестоимости или комиссиям "
                    f"({missing}). Исправьте данные, затем перепроверьте безопасную маржу."
                )
            if price_safety.target_price is not None:
                if not price_safety.can_recommend_price_increase:
                    return (
                        f"Не повышайте цену автоматически: безопасный минимум {price_safety.min_safe_price} RUB, "
                        f"а текущая эффективная цена {price_safety.reference_price} RUB. Проверьте формулу маржи, "
                        "себестоимость, комиссии, логистику, скидки и СПП, затем перепроверьте безопасную маржу."
                    )
                return (
                    f"Поднимите эффективную цену минимум до {price_safety.target_price} RUB, чтобы сохранить "
                    f"целевую маржу {price_safety.target_margin_pct}%. Если рынок не принимает такую цену, проверьте себестоимость и комиссии."
                )
        if problem_code == "promo_not_profitable":
            if price_safety.missing_required_metrics:
                missing = self._metric_list(price_safety.missing_required_metrics)
                return (
                    "Пока не запускайте и не усиливайте промо: не хватает данных по себестоимости или комиссиям "
                    f"({missing}). Сначала исправьте данные, затем перепроверьте экономику промо."
                )
            if not price_safety.can_recommend_price_decrease:
                return (
                    f"Не увеличивайте скидку: безопасный минимум {price_safety.min_safe_price} RUB, а текущая эффективная цена "
                    f"{price_safety.reference_price} RUB. Снизьте или остановите промо, проверьте цену, себестоимость и качество трафика."
                )
            return (
                f"Промо должно оставаться в рамках экономики единицы: держите эффективную цену не ниже {price_safety.min_safe_price} RUB "
                f"и скидку не выше {price_safety.max_safe_discount_pct}%. В первую очередь сократите убыточные расходы на промо."
            )
        return base_recommendation

    @staticmethod
    def _metric_missing(resolved: ProductMetricResolution, code: str) -> bool:
        metric = resolved.metrics.get(code)
        return metric is None or bool(metric.is_missing)

    @classmethod
    def _metric_decimal(
        cls, resolved: ProductMetricResolution, code: str
    ) -> Decimal | None:
        metric = resolved.metrics.get(code)
        if metric is None or metric.is_missing:
            return None
        return cls._decimal(metric.value)

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

    @staticmethod
    def _positive(value: Decimal | None) -> Decimal | None:
        return value if value is not None and value > 0 else None

    @staticmethod
    def _quantize_money(value: Decimal | None) -> Decimal | None:
        return (
            value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if value is not None
            else None
        )

    @staticmethod
    def _quantize_pct(value: Decimal | None) -> Decimal | None:
        return (
            value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            if value is not None
            else None
        )

    def _total_unit_cost(self, values: dict[str, Decimal | None]) -> Decimal | None:
        parts = [values.get(code) for code in REQUIRED_UNIT_ECONOMICS_METRICS]
        if any(value is None for value in parts):
            return None
        return sum((value or Decimal("0")) for value in parts)

    def _min_safe_price(self, total_cost: Decimal | None) -> Decimal | None:
        if total_cost is None or total_cost <= 0:
            return None
        denominator = Decimal("1") - (self.target_margin_pct / Decimal("100"))
        if denominator <= Decimal("0"):
            return None
        return total_cost / denominator

    @staticmethod
    def _max_safe_discount_pct(
        *, reference_price: Decimal | None, min_safe_price: Decimal | None
    ) -> Decimal | None:
        if reference_price is None or reference_price <= 0 or min_safe_price is None:
            return None
        discount = ((reference_price - min_safe_price) / reference_price) * Decimal(
            "100"
        )
        return max(Decimal("0"), discount)

    @staticmethod
    def _discounted_price(
        reference_price: Decimal | None, discount_pct: Decimal
    ) -> Decimal | None:
        if reference_price is None or reference_price <= 0:
            return None
        return reference_price * (Decimal("1") - discount_pct / Decimal("100"))

    @staticmethod
    def _margin_pct(
        price: Decimal | None, total_cost: Decimal | None
    ) -> Decimal | None:
        if price is None or price <= 0 or total_cost is None:
            return None
        return ((price - total_cost) / price) * Decimal("100")

    def _component_breakdown(
        self, values: dict[str, Decimal | None], *, reference_price: Decimal | None
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        if reference_price is not None:
            items.append(
                {
                    "label": "текущая эффективная цена",
                    "metric_code": "price_after_discount",
                    "kind": "revenue",
                    "value": self._quantize_money(reference_price),
                }
            )
        for code in REQUIRED_UNIT_ECONOMICS_METRICS:
            value = values.get(code)
            if value is None:
                continue
            items.append(
                {
                    "label": self._metric_label(code),
                    "metric_code": code,
                    "kind": "cost",
                    "value": self._quantize_money(value),
                }
            )
        unit_profit = values.get("unit_profit")
        if unit_profit is not None:
            items.append(
                {
                    "label": "прибыль на единицу",
                    "metric_code": "unit_profit",
                    "kind": "result",
                    "value": self._quantize_money(unit_profit),
                }
            )
        return sorted(
            items,
            key=lambda item: (
                item["kind"] != "cost",
                -(Decimal(str(item.get("value") or 0)).copy_abs()),
            ),
        )

    @staticmethod
    def _linked_data_blocker(missing: list[str]) -> dict[str, Any] | None:
        if not missing:
            return None
        problem_code = "missing_cost_blocks_profit" if "cost_price" in missing else None
        return {
            "problem_code": problem_code,
            "missing_metrics": list(missing),
            "reason": "Для рекомендации по цене или промо нужна полная экономика единицы товара.",
        }

    def _warnings(self, result: PriceSafetyResult) -> list[str]:
        if result.missing_required_metrics:
            return [
                "price_recommendation_blocked_missing_unit_economics",
                *[
                    f"missing_required_metric:{metric}"
                    for metric in result.missing_required_metrics
                ],
            ]
        if (
            result.problem_code in {"overstock_slow_moving", "dead_stock"}
            and not result.can_recommend_price_decrease
        ):
            return ["price_decrease_blocked_by_min_safe_price"]
        if (
            result.problem_code == "negative_unit_profit"
            and result.can_recommend_price_increase
        ):
            return ["price_increase_target_calculated_from_unit_economics"]
        if (
            result.problem_code == "price_below_safe_margin"
            and result.can_recommend_price_increase
        ):
            return ["price_increase_target_calculated_from_unit_economics"]
        if (
            result.problem_code == "promo_not_profitable"
            and not result.can_recommend_price_decrease
        ):
            return ["promo_discount_blocked_by_min_safe_price"]
        return ["price_safety_checked"]

    def _trust_notes(self, result: PriceSafetyResult) -> list[str]:
        notes = [
            "Проверка безопасной цены использует себестоимость, комиссию, логистику, эквайринг и хранение на единицу.",
            f"Целевая маржа: {result.target_margin_pct}%; снижение цены блокируется ниже минимальной безопасной цены.",
        ]
        if result.linked_data_blocker:
            notes.append(
                "Перед рекомендацией по снижению цены нужно связать или создать блокер данных."
            )
        return notes
