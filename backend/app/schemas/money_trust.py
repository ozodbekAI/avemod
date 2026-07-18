from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


MoneyTrustState = Literal[
    "confirmed",
    "provisional",
    "estimated",
    "opportunity",
    "test_only",
    "blocked",
]

MoneyImpactKind = Literal[
    "confirmed_loss",
    "probable_loss",
    "probable_risk",
    "blocked_cash",
    "lost_sales_risk",
    "opportunity",
    "estimated_opportunity",
    "blocked_revenue",
    "data_blocker",
    "data_blocked",
    "test_only",
    "informational",
]


class MoneyTrustInfo(BaseModel):
    state: MoneyTrustState
    impact_kind: MoneyImpactKind
    display_label: str
    amount_label: str
    show_as_confirmed_money: bool = False
    seller_visible_by_default: bool = True
    reason: str = ""
    evidence_trust_state: MoneyTrustState | None = None
    impact_trust_state: MoneyTrustState | None = None
    saved_money_claimed: bool = False


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _has_any(text: str, needles: set[str]) -> bool:
    return any(needle in text for needle in needles)


def classify_money_trust(
    *,
    value: Any = None,
    value_type: str | None = None,
    confidence: str | None = None,
    impact_type: str | None = None,
    trust_state: str | None = None,
    financial_final: bool | None = None,
    source_module: str | None = None,
    source_table: str | None = None,
    source_endpoint: str | None = None,
    action_type: str | None = None,
    payload: dict[str, Any] | None = None,
    affected_amount: float | int | None = None,
    affected_revenue: float | int | None = None,
) -> MoneyTrustInfo:
    """Classify visible money so UI never turns weak signals into real losses."""

    payload = payload or {}
    text = " ".join(
        _norm(part)
        for part in (
            confidence,
            impact_type,
            trust_state,
            source_module,
            source_table,
            source_endpoint,
            action_type,
            payload.get("trust_state"),
            payload.get("runtime_mode"),
            payload.get("source"),
            payload.get("code"),
        )
    )
    module = _norm(source_module)
    impact = _norm(impact_type)
    conf = _norm(confidence)
    trust = _norm(trust_state or payload.get("trust_state"))
    evidence_trust = _trust_state_for_contract(
        payload.get("evidence_trust_state") or conf or trust
    )
    impact_trust = _trust_state_for_contract(
        payload.get("impact_trust_state") or trust or conf
    )
    action = _norm(action_type)
    if action in {"low_stock_risk", "fast_stock_depletion"}:
        impact = "lost_sales_risk"
    elif action in {"overstock_slow_moving", "dead_stock"} and impact in {
        "",
        "confirmed_loss",
        "opportunity",
    }:
        impact = "blocked_cash"
    numeric_value = _to_float(value)
    amount = _to_float(affected_amount)
    revenue = _to_float(affected_revenue)

    if (
        trust in {"test_only", "test", "mock", "demo"}
        or conf in {"test_only", "test"}
        or payload.get("test_only") is True
        or payload.get("beta") is True
        or module == "grouping_beta"
    ):
        return MoneyTrustInfo(
            state="test_only",
            impact_kind="test_only",
            display_label="Тестовый сигнал",
            amount_label="Не деньги продавца",
            show_as_confirmed_money=False,
            seller_visible_by_default=False,
            reason="Generated/test-only signal is hidden from the default seller view.",
            evidence_trust_state=evidence_trust,
            impact_trust_state="test_only",
            saved_money_claimed=False,
        )

    if (
        conf == "blocked"
        or impact == "data_blocker"
        or trust in {"blocked", "data_blocked"}
    ):
        blocked_revenue_only = (amount in {None, 0.0}) and revenue not in {None, 0.0}
        return MoneyTrustInfo(
            state="blocked",
            impact_kind="blocked_revenue" if blocked_revenue_only else "data_blocker",
            display_label="Данные заблокированы",
            amount_label="Блокированная выручка"
            if blocked_revenue_only
            else "Не хватает данных",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="Required source data is missing or invalid, so final money cannot be computed.",
            evidence_trust_state="blocked",
            impact_trust_state="blocked",
            saved_money_claimed=False,
        )

    if impact == "lost_sales_risk":
        risk_trust: MoneyTrustState = (
            impact_trust
            if impact_trust in {"provisional", "estimated"}
            else "provisional"
        )
        return MoneyTrustInfo(
            state=risk_trust,
            impact_kind="lost_sales_risk",
            display_label="Риск потери продаж",
            amount_label="Риск потери продаж",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="Low stock can create a sales-loss risk, but it is not a confirmed loss until after-data proves missed sales.",
            evidence_trust_state=evidence_trust,
            impact_trust_state=risk_trust,
            saved_money_claimed=False,
        )

    if impact == "blocked_cash":
        blocked_cash_trust: MoneyTrustState = (
            "confirmed"
            if financial_final is True and impact_trust == "confirmed"
            else "estimated"
        )
        return MoneyTrustInfo(
            state=blocked_cash_trust,
            impact_kind="blocked_cash",
            display_label="Замороженные деньги",
            amount_label="Замороженные деньги",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="Overstock ties up cash in inventory; it is not a confirmed realized loss.",
            evidence_trust_state=evidence_trust,
            impact_trust_state=blocked_cash_trust,
            saved_money_claimed=False,
        )

    if impact in {"probable_loss", "probable_risk"}:
        risk_trust: MoneyTrustState = (
            impact_trust
            if impact_trust in {"provisional", "estimated"}
            else "estimated"
        )
        return MoneyTrustInfo(
            state=risk_trust,
            impact_kind="probable_loss"
            if impact == "probable_loss"
            else "probable_risk",
            display_label="Вероятный убыток"
            if impact == "probable_loss"
            else "Вероятный риск",
            amount_label="Вероятный убыток"
            if impact == "probable_loss"
            else "Вероятный риск",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="The impact is a risk estimate and must not be shown as a confirmed loss.",
            evidence_trust_state=evidence_trust,
            impact_trust_state=risk_trust,
            saved_money_claimed=False,
        )

    finance_source = _has_any(
        text, {"finance", "financial", "realization", "report", "wb_realization"}
    )
    if impact == "confirmed_loss" and (
        financial_final is True or conf == "confirmed" or finance_source
    ):
        return MoneyTrustInfo(
            state="confirmed",
            impact_kind="confirmed_loss",
            display_label="Подтверждённый убыток",
            amount_label="Подтверждённый убыток",
            show_as_confirmed_money=True,
            seller_visible_by_default=True,
            reason="Confirmed by WB finance/report rows or user-confirmed source data.",
            evidence_trust_state=evidence_trust,
            impact_trust_state="confirmed",
            saved_money_claimed=False,
        )

    if module == "checker" or _has_any(
        text, {"checker", "card_quality", "content", "photo", "description"}
    ):
        return MoneyTrustInfo(
            state="opportunity",
            impact_kind="estimated_opportunity",
            display_label="Оценочная возможность",
            amount_label="Оценочная возможность",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="Checker/content improvements are conversion opportunities, not confirmed financial losses.",
            evidence_trust_state=evidence_trust,
            impact_trust_state="opportunity",
            saved_money_claimed=False,
        )

    if impact in {"opportunity", "estimated_opportunity"}:
        return MoneyTrustInfo(
            state="opportunity"
            if conf not in {"estimated", "estimate"}
            else "estimated",
            impact_kind="opportunity"
            if impact == "opportunity"
            else "estimated_opportunity",
            display_label="Возможность роста"
            if impact == "opportunity"
            else "Оценочная возможность",
            amount_label="Возможность роста"
            if impact == "opportunity"
            else "Оценочная возможность",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="The value is an expected effect, not confirmed money already lost.",
            evidence_trust_state=evidence_trust,
            impact_trust_state="opportunity"
            if conf not in {"estimated", "estimate"}
            else "estimated",
            saved_money_claimed=False,
        )

    if conf in {"estimated", "estimate"} or _has_any(
        text, {"estimated", "estimate", "allocation", "model"}
    ):
        return MoneyTrustInfo(
            state="estimated",
            impact_kind="probable_risk"
            if (numeric_value or 0) < 0
            else "estimated_opportunity",
            display_label="Оценка",
            amount_label="Оценочная возможность"
            if (numeric_value or 0) >= 0
            else "Вероятный риск",
            show_as_confirmed_money=False,
            seller_visible_by_default=True,
            reason="The value is inferred, allocated, or model-based.",
            evidence_trust_state=evidence_trust,
            impact_trust_state="estimated",
            saved_money_claimed=False,
        )

    if financial_final is True or (conf == "confirmed" and finance_source):
        return MoneyTrustInfo(
            state="confirmed",
            impact_kind="informational",
            display_label="Подтверждённые деньги",
            amount_label="Подтверждённые деньги",
            show_as_confirmed_money=True,
            seller_visible_by_default=True,
            reason="Confirmed by WB finance/report rows or user-confirmed source data.",
            evidence_trust_state=evidence_trust,
            impact_trust_state="confirmed",
            saved_money_claimed=False,
        )

    return MoneyTrustInfo(
        state="provisional",
        impact_kind="probable_risk"
        if impact in {"probable_loss", "probable_risk"}
        else "informational",
        display_label="Предварительно",
        amount_label="Вероятный риск"
        if impact in {"probable_loss", "probable_risk"}
        else "Предварительные деньги",
        show_as_confirmed_money=False,
        seller_visible_by_default=True,
        reason="Operational money before final finance/source confirmation.",
        evidence_trust_state=evidence_trust,
        impact_trust_state="provisional",
        saved_money_claimed=False,
    )


def _trust_state_for_contract(value: Any) -> MoneyTrustState:
    normalized = _norm(value)
    if normalized in {"confirmed", "trusted", "final", "high"}:
        return "confirmed"
    if normalized in {"estimated", "estimate", "medium"}:
        return "estimated"
    if normalized in {"opportunity", "chance"}:
        return "opportunity"
    if normalized in {"test_only", "test", "mock", "demo"}:
        return "test_only"
    if normalized in {"blocked", "data_blocked", "data_blocker"}:
        return "blocked"
    return "provisional"


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
