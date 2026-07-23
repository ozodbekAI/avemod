from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.schemas.evidence import EvidenceLedger, evidence_ledger
from app.schemas.money_trust import MoneyTrustInfo, classify_money_trust


CHECKER_DATA_BLOCKER_CODES = {
    "source_data_missing",
    "source_card_missing",
    "card_not_found",
    "card_unavailable",
    "snapshot_missing",
    "not_analyzed",
    "analysis_blocked",
}

CHECKER_DATA_BLOCKER_CATEGORIES = {"data", "source", "sync", "identity_blocker"}
CHECKER_BUSINESS_EVIDENCE_KEYS = {
    "business_metrics",
    "business_evidence",
    "sales_metrics",
    "conversion_metrics",
    "financial_evidence",
    "confirmed_financial_evidence",
    "confirmed_money_impact_amount",
    "confirmed_loss_amount",
    "measured_loss_amount",
    "financial_final",
    "orders_delta",
    "revenue_delta",
    "profit_delta",
}
CHECKER_SEVERITY_WEIGHTS = {
    "critical": 25.0,
    "high": 15.0,
    "medium": 7.0,
    "low": 3.0,
    "info": 0.0,
}


@dataclass(frozen=True)
class CheckerProblemBridge:
    payload: dict[str, Any]
    evidence_ledger: EvidenceLedger
    money_trust: MoneyTrustInfo
    trust_state: str
    impact_type: str
    bridge_kind: str


def _get(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _first(source: Any, *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = _get(source, key)
        if value not in (None, ""):
            return value
    return default


def _text(source: Any, *keys: str, default: str = "") -> str:
    value = _first(source, *keys, default=default)
    return str(value or "").strip()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed == parsed else None


def _evidence_dict(issue: Any) -> dict[str, Any]:
    raw = _first(issue, "ai_evidence_json", "ai_evidence", "evidence", default={})
    return raw if isinstance(raw, dict) else {}


def _has_business_metrics(evidence: dict[str, Any]) -> bool:
    if not evidence:
        return False
    if any(key in evidence for key in CHECKER_BUSINESS_EVIDENCE_KEYS):
        return True
    nested = evidence.get("metrics")
    return isinstance(nested, dict) and any(
        key in nested for key in CHECKER_BUSINESS_EVIDENCE_KEYS
    )


def _confirmed_money_amount(evidence: dict[str, Any]) -> float | None:
    for key in (
        "confirmed_money_impact_amount",
        "confirmed_loss_amount",
        "measured_loss_amount",
    ):
        value = _number(evidence.get(key))
        if value is not None:
            return value
    return None


def checker_bridge_semantics(issue: Any) -> dict[str, Any]:
    code = _text(issue, "issue_code", "code").lower()
    category = _text(issue, "category", "type").lower()
    field_name = _text(issue, "field_name", "field_path").lower()
    evidence = _evidence_dict(issue)
    has_business_metrics = _has_business_metrics(evidence)
    confirmed_amount = _confirmed_money_amount(evidence)
    financial_final = bool(
        evidence.get("financial_final") or evidence.get("confirmed_financial_evidence")
    )

    data_blocker = (
        code in CHECKER_DATA_BLOCKER_CODES
        or category in CHECKER_DATA_BLOCKER_CATEGORIES
        or "source_data_missing" in code
        or "analysis_blocked" in code
        or field_name in {"nm_id", "vendor_code", "subject_name", "source_card"}
    )
    if confirmed_amount is not None and financial_final:
        return {
            "bridge_kind": "business_metrics",
            "trust_state": "confirmed",
            "impact_type": "confirmed_loss",
            "value": abs(confirmed_amount),
            "value_type": "money",
            "unit": "RUB",
            "has_business_metrics": True,
            "financial_loss_confirmed": True,
        }
    if data_blocker:
        return {
            "bridge_kind": "content_data_blocker",
            "trust_state": "blocked",
            "impact_type": "data_blocker",
            "value": None,
            "value_type": "text",
            "unit": None,
            "has_business_metrics": has_business_metrics,
            "financial_loss_confirmed": False,
        }
    score = _number(_first(issue, "score_impact", "estimated_opportunity_score"))
    if score is None:
        score = CHECKER_SEVERITY_WEIGHTS.get(_text(issue, "severity").lower(), 0.0)
    return {
        "bridge_kind": "business_metrics"
        if has_business_metrics
        else "content_quality",
        "trust_state": "opportunity",
        "impact_type": "opportunity",
        "value": score,
        "value_type": "count",
        "unit": "баллов",
        "has_business_metrics": has_business_metrics,
        "financial_loss_confirmed": False,
    }


def build_checker_problem_bridge(
    issue: Any,
    *,
    account_id: int | None,
    nm_id: int | None,
    issue_id: Any = None,
    source_endpoint: str = "GET /api/v1/portal/card-quality/issues",
) -> CheckerProblemBridge:
    code = _text(issue, "issue_code", "code", default="card_quality_issue")
    category = _text(issue, "category", "type", default="content")
    field_name = _text(issue, "field_name", "field_path")
    title = _text(issue, "title", default="Проверить карточку")
    reason = _text(
        issue,
        "business_explanation",
        "description",
        "ai_reason",
        "ai_reason_short",
        default="Проверка карточки нашла возможность улучшить карточку товара.",
    )
    next_step = _text(
        issue,
        "recommended_fix",
        "suggested_value",
        "ai_suggested_value",
        default="Откройте проверку карточки, проверьте рекомендацию и исправьте карточку.",
    )
    source_id = str(
        issue_id
        if issue_id is not None
        else _first(issue, "id", "source_id", "code", default=code)
    )
    semantics = checker_bridge_semantics(issue)
    score_impact = _number(_first(issue, "score_impact", "estimated_opportunity_score"))
    if score_impact is None:
        score_impact = CHECKER_SEVERITY_WEIGHTS.get(
            _text(issue, "severity").lower(), 0.0
        )
    evidence = _evidence_dict(issue)
    missing_data = (
        ["Не хватает исходных данных карточки для проверки"]
        if semantics["impact_type"] == "data_blocker"
        else []
    )
    trust_notes = [
        "Контентный сигнал Checker не является подтверждённым финансовым убытком.",
        "Финансовый статус повышается только при явных бизнес-метриках и подтверждённых after-data.",
    ]
    if semantics["has_business_metrics"]:
        trust_notes.append(
            "В сигнале есть бизнес-метрики, но влияние остаётся возможностью до подтверждения финансовыми данными."
        )
    money_trust = classify_money_trust(
        value=semantics["value"],
        value_type=semantics["value_type"],
        confidence=semantics["trust_state"],
        trust_state=semantics["trust_state"],
        impact_type=semantics["impact_type"],
        financial_final=bool(semantics["financial_loss_confirmed"]),
        source_module="checker",
        source_table="card_quality_issues",
        source_endpoint=source_endpoint,
        action_type=code,
        payload={
            "code": code,
            "category": category,
            "trust_state": semantics["trust_state"],
            "impact_type": semantics["impact_type"],
        },
    )
    ledger = evidence_ledger(
        value=semantics["value"],
        value_type=semantics["value_type"],
        confidence=semantics["trust_state"],
        impact_type=semantics["impact_type"],
        formula_human=reason,
        formula_code=f"checker.card_quality.{code}",
        formula_id=f"checker:{source_id}",
        label="Оценка качества карточки",
        unit=semantics["unit"],
        source_table="card_quality_issues",
        source_endpoint=source_endpoint,
        filters={"account_id": account_id, "nm_id": nm_id, "issue_code": code},
        row_count=1,
        sample_rows=[
            {
                "id": source_id,
                "nm_id": nm_id,
                "issue_code": code,
                "category": category,
                "field_name": field_name,
                "score_impact": score_impact,
            }
        ],
        trust_notes=trust_notes,
        missing_data=missing_data,
        next_fix_action={
            "label": "Проверить карточку",
            "screen_path": f"/checker/{nm_id}" if nm_id else "/products",
            "source_endpoint": source_endpoint,
            "action_type": "CARD_QUALITY_FIX",
        },
        recheck_rule="После исправления карточки запустите проверку карточки повторно. Статус обновится после новой проверки.",
        recheck_rule_human="После исправления карточки запустите проверку карточки повторно. Статус обновится после новой проверки.",
        calculation_warnings=[]
        if semantics["financial_loss_confirmed"]
        else [
            "Это возможность улучшения контента, а не подтверждённая финансовая потеря."
        ],
        money_trust=money_trust,
    )
    payload = {
        "checker_problem_bridge": True,
        "problem_ux_contract": True,
        "content_quality_signal": True,
        "bridge_kind": semantics["bridge_kind"],
        "source_module": "checker",
        "problem_code": code,
        "detector_code": code,
        "issue_code": code,
        "title": title,
        "category": category,
        "field_path": field_name,
        "field_name": field_name,
        "trust_state": semantics["trust_state"],
        "impact_type": semantics["impact_type"],
        "allowed_actions": ["check_card_quality", "recheck", "dismiss"],
        "can_user_fix_inside_platform": True,
        "evidence_quality": "partial"
        if not semantics["financial_loss_confirmed"]
        else "full",
        "business_metric_evidence": bool(semantics["has_business_metrics"]),
        "financial_loss_confirmed": bool(semantics["financial_loss_confirmed"]),
        "estimated_opportunity_score": score_impact,
        "impact_kind": "estimated_opportunity"
        if semantics["impact_type"] == "opportunity"
        else semantics["impact_type"],
        "impact_note": "Контентная возможность Checker, не подтверждённый финансовый убыток.",
        "reason": reason,
        "recommendation": next_step,
        "what_to_do": next_step,
        "recheck_rule": ledger.recheck_rule_human,
        "recheck_rule_human": ledger.recheck_rule_human,
        "source_table": "card_quality_issues",
        "source_endpoint": source_endpoint,
        "evidence_ledger": ledger.model_dump(mode="json"),
        "money_trust": money_trust.model_dump(mode="json"),
        "business_evidence": evidence,
    }
    return CheckerProblemBridge(
        payload=payload,
        evidence_ledger=ledger,
        money_trust=money_trust,
        trust_state=semantics["trust_state"],
        impact_type=semantics["impact_type"],
        bridge_kind=semantics["bridge_kind"],
    )
