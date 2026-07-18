from __future__ import annotations

from dataclasses import dataclass, field

from app.models.manual_costs import ManualCost


COST_TRUTH_SUPPLIER_CONFIRMED = "supplier_confirmed"
COST_TRUTH_OPERATOR_BASELINE = "operator_baseline"
COST_TRUTH_PLACEHOLDER = "placeholder"

TRUST_STATE_TRUSTED = "trusted"
TRUST_STATE_TEST_ONLY = "test_only"
TRUST_STATE_DATA_BLOCKED = "data_blocked"
TRUST_STATE_OPERATIONAL_PROVISIONAL = "operational_provisional"
TRUST_STATE_FINANCIAL_FINAL = "financial_final"
TRUST_STATE_BLOCKED = "blocked"
TRUST_STATE_UNKNOWN = "unknown"

PLACEHOLDER_SUPPLIER = "AUTO_TEMPLATE"
OPERATOR_BASELINE_SUPPLIER = "OPERATOR_TRUSTED_COST"

COST_TRUST_POLICY_SUPPLIER_ONLY = "supplier_only"
COST_TRUST_POLICY_OPERATOR_BASELINE = "operator_baseline"
COST_TRUST_POLICY_MIXED = "mixed"
COST_TRUST_POLICY_OWNER_APPROVED_FINAL = "owner_approved_final"
COST_TRUST_POLICIES_ACCEPTING_OPERATOR = {
    COST_TRUST_POLICY_OPERATOR_BASELINE,
    COST_TRUST_POLICY_MIXED,
    COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
}
GLOBAL_HARD_BLOCKER_REASONS = {
    "failed_sync_domains",
    "unmatched_sku_detected",
    "latest_stocks_not_completed",
    "open_blocking_dq_issues",
    "scheduler_instability",
}


@dataclass
class TrustDecision:
    business_trusted: bool
    trust_state: str
    blocked_reasons: list[str] = field(default_factory=list)
    can_generate_business_actions: bool = False


@dataclass
class CostCoverageDecision:
    operational_cost_coverage_percent: float
    supplier_confirmed_cost_coverage_percent: float
    business_accepted_cost_coverage_percent: float
    cost_policy: str
    cost_truth_level: str
    can_use_for_operations: bool
    can_use_for_final_profit: bool
    missing_cost_revenue: float
    operator_baseline_revenue: float
    supplier_confirmed_revenue: float
    message: str


@dataclass
class PublicTrustSnapshot:
    operational_trusted: bool
    business_trusted: bool
    financial_final: bool
    trust_state: str
    cost_trust_policy: str | None
    supplier_confirmed_revenue_coverage_percent: float
    operator_baseline_revenue_coverage_percent: float
    trusted_revenue_cost_coverage_percent: float
    financial_final_blockers_total: int
    final_profit_blockers_total: int
    all_open_issues_total: int
    blocking_open_issues_total: int


def _normalized_supplier(value: str | None) -> str:
    return str(value or "").strip().upper()


def _decimal0(value: float | int | str | None) -> float:
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return 0.0


def _percent0(part: float, whole: float) -> float:
    if whole <= 0:
        return 0.0
    return (part / whole) * 100.0


def is_placeholder_manual_cost(cost: ManualCost | None) -> bool:
    if cost is None:
        return False
    return (
        bool(getattr(cost, "is_placeholder", False))
        or _normalized_supplier(getattr(cost, "supplier", None)) == PLACEHOLDER_SUPPLIER
    )


def is_operator_baseline_manual_cost(cost: ManualCost | None) -> bool:
    if cost is None:
        return False
    supplier = _normalized_supplier(getattr(cost, "supplier", None))
    source = str(getattr(cost, "cost_source", None) or "").strip().lower()
    return supplier == OPERATOR_BASELINE_SUPPLIER or source in {
        "operator_trusted_manual",
        "operator_baseline",
    }


def is_supplier_confirmed_manual_cost(cost: ManualCost | None) -> bool:
    if cost is None or is_placeholder_manual_cost(cost):
        return False
    if bool(getattr(cost, "is_supplier_confirmed", False)):
        return True
    cost_source = str(getattr(cost, "cost_source", None) or "").strip().lower()
    if cost_source != "supplier_confirmed":
        return False
    try:
        return (
            float(
                getattr(cost, "cost_price", None)
                or getattr(cost, "unit_cost", None)
                or 0
            )
            > 0
        )
    except (TypeError, ValueError):
        return False


def core_sku_cost_trust_snapshot(cost: ManualCost | None) -> dict[str, object]:
    if cost is None:
        return {
            "has_real_manual_cost": False,
            "has_placeholder_cost": False,
            "business_trusted": False,
            "operational_trusted": False,
            "cost_source": None,
            "cost_truth_level": "missing",
        }

    supplier = _normalized_supplier(getattr(cost, "supplier", None))
    raw_cost_source = str(getattr(cost, "cost_source", None) or "").strip()
    normalized_cost_source = raw_cost_source.lower()
    is_placeholder = (
        bool(getattr(cost, "is_placeholder", False)) or PLACEHOLDER_SUPPLIER in supplier
    )
    is_supplier_confirmed = (
        normalized_cost_source == "supplier_confirmed"
        or is_supplier_confirmed_manual_cost(cost)
    )
    is_operator_baseline = (
        bool(getattr(cost, "is_business_trusted", False))
        or OPERATOR_BASELINE_SUPPLIER in supplier
        or normalized_cost_source in {"operator_baseline", "operator_trusted_manual"}
    )
    is_ambiguous = bool(getattr(cost, "is_ambiguous", False))

    if is_placeholder:
        truth_level = "placeholder"
        has_placeholder_cost = True
        has_real_manual_cost = False
        operational_trusted = False
    elif is_supplier_confirmed:
        truth_level = COST_TRUTH_SUPPLIER_CONFIRMED
        has_placeholder_cost = False
        has_real_manual_cost = True
        operational_trusted = True
    elif is_operator_baseline:
        truth_level = COST_TRUTH_OPERATOR_BASELINE
        has_placeholder_cost = False
        has_real_manual_cost = False
        operational_trusted = True
    elif is_ambiguous:
        truth_level = "ambiguous"
        has_placeholder_cost = False
        has_real_manual_cost = False
        operational_trusted = False
    elif normalized_cost_source == "estimated_range":
        truth_level = "estimated_range"
        has_placeholder_cost = False
        has_real_manual_cost = False
        operational_trusted = bool(getattr(cost, "is_business_trusted", False))
    else:
        truth_level = "manual_untrusted"
        has_placeholder_cost = False
        has_real_manual_cost = False
        operational_trusted = False

    return {
        "has_real_manual_cost": has_real_manual_cost,
        "has_placeholder_cost": has_placeholder_cost,
        "business_trusted": operational_trusted,
        "operational_trusted": operational_trusted,
        "cost_source": raw_cost_source or None,
        "cost_truth_level": truth_level,
    }


def cost_truth_level_from_cost(cost: ManualCost | None) -> str | None:
    if cost is None:
        return None
    if bool(getattr(cost, "is_ambiguous", False)):
        return "ambiguous"
    if is_placeholder_manual_cost(cost):
        return COST_TRUTH_PLACEHOLDER
    if is_supplier_confirmed_manual_cost(cost):
        return COST_TRUTH_SUPPLIER_CONFIRMED
    if is_operator_baseline_manual_cost(cost):
        return COST_TRUTH_OPERATOR_BASELINE
    source = str(getattr(cost, "cost_source", None) or "").strip().lower()
    if source == "estimated_range":
        return "estimated_range"
    if bool(getattr(cost, "is_business_trusted", False)):
        return COST_TRUTH_OPERATOR_BASELINE
    return "manual_untrusted"


def cost_truth_level_from_flags(
    *,
    has_manual_cost: bool,
    has_real_manual_cost: bool,
    has_placeholder_cost: bool,
    cost_source: str | None,
) -> str | None:
    if not has_manual_cost:
        return None
    source = str(cost_source or "").strip().lower()
    if has_placeholder_cost or source == "placeholder_auto_template":
        return COST_TRUTH_PLACEHOLDER
    if source == "estimated_range":
        return "estimated_range"
    if has_real_manual_cost:
        return COST_TRUTH_SUPPLIER_CONFIRMED
    if source in {"operator_trusted_manual", "operator_baseline", "manual_upload", ""}:
        return COST_TRUTH_OPERATOR_BASELINE
    return "manual_untrusted"


def cost_policy_accepts_operator_baseline(cost_trust_policy: str | None) -> bool:
    return (
        str(cost_trust_policy or COST_TRUST_POLICY_SUPPLIER_ONLY).strip().lower()
        in COST_TRUST_POLICIES_ACCEPTING_OPERATOR
    )


def cost_policy_owner_approves_final(cost_trust_policy: str | None) -> bool:
    return (
        str(cost_trust_policy or "").strip().lower()
        == COST_TRUST_POLICY_OWNER_APPROVED_FINAL
    )


def effective_cost_is_business_trusted(
    *,
    has_manual_cost: bool,
    has_real_manual_cost: bool,
    has_placeholder_cost: bool = False,
    cost_source: str | None = None,
    cost_truth_level: str | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_SUPPLIER_ONLY,
) -> bool:
    if has_real_manual_cost:
        return True
    if not has_manual_cost or has_placeholder_cost:
        return False
    if not cost_policy_accepts_operator_baseline(cost_trust_policy):
        return False
    normalized_truth = str(cost_truth_level or "").strip().lower()
    normalized_source = str(cost_source or "").strip().lower()
    return normalized_truth in {
        COST_TRUTH_OPERATOR_BASELINE,
        "",
    } or normalized_source in {"operator_trusted_manual", "mixed", "manual_upload", ""}


def final_cost_is_accepted(
    *,
    has_manual_cost: bool,
    has_real_manual_cost: bool,
    has_placeholder_cost: bool = False,
    cost_source: str | None = None,
    cost_truth_level: str | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_SUPPLIER_ONLY,
) -> bool:
    if has_real_manual_cost:
        return True
    if not cost_policy_owner_approves_final(cost_trust_policy):
        return False
    return effective_cost_is_business_trusted(
        has_manual_cost=has_manual_cost,
        has_real_manual_cost=has_real_manual_cost,
        has_placeholder_cost=has_placeholder_cost,
        cost_source=cost_source,
        cost_truth_level=cost_truth_level,
        cost_trust_policy=cost_trust_policy,
    )


def normalize_blocked_reasons_for_cost_policy(
    blocked_reasons: list[str],
    *,
    has_manual_cost: bool,
    has_real_manual_cost: bool,
    has_placeholder_cost: bool = False,
    cost_source: str | None = None,
    cost_truth_level: str | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_SUPPLIER_ONLY,
) -> list[str]:
    if not effective_cost_is_business_trusted(
        has_manual_cost=has_manual_cost,
        has_real_manual_cost=has_real_manual_cost,
        has_placeholder_cost=has_placeholder_cost,
        cost_source=cost_source,
        cost_truth_level=cost_truth_level,
        cost_trust_policy=cost_trust_policy,
    ):
        return list(dict.fromkeys(blocked_reasons))
    return [
        reason
        for reason in list(dict.fromkeys(blocked_reasons))
        if reason
        not in {"supplier_cost_not_confirmed", "supplier_cost_coverage_below_threshold"}
    ]


def trust_state_for_row(
    *,
    has_manual_cost: bool,
    has_real_manual_cost: bool,
    blocked_reasons: list[str],
    has_placeholder_cost: bool = False,
    cost_source: str | None = None,
    cost_truth_level: str | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_SUPPLIER_ONLY,
) -> str:
    effective_cost_trusted = effective_cost_is_business_trusted(
        has_manual_cost=has_manual_cost,
        has_real_manual_cost=has_real_manual_cost,
        has_placeholder_cost=has_placeholder_cost,
        cost_source=cost_source,
        cost_truth_level=cost_truth_level,
        cost_trust_policy=cost_trust_policy,
    )
    normalized_reasons = normalize_blocked_reasons_for_cost_policy(
        blocked_reasons,
        has_manual_cost=has_manual_cost,
        has_real_manual_cost=has_real_manual_cost,
        has_placeholder_cost=has_placeholder_cost,
        cost_source=cost_source,
        cost_truth_level=cost_truth_level,
        cost_trust_policy=cost_trust_policy,
    )
    if effective_cost_trusted and not normalized_reasons:
        return TRUST_STATE_TRUSTED
    if not has_manual_cost:
        return TRUST_STATE_DATA_BLOCKED
    non_severe_reasons = {"supplier_cost_not_confirmed", "finance_not_confirmed"}
    if normalized_reasons and set(normalized_reasons).issubset(non_severe_reasons):
        return TRUST_STATE_TEST_ONLY
    if not normalized_reasons:
        return TRUST_STATE_TEST_ONLY
    return TRUST_STATE_DATA_BLOCKED


def blocked_reasons_for_profit_row(
    *,
    has_manual_cost: bool,
    has_real_manual_cost: bool,
    has_placeholder_cost: bool,
    finance_rows: int,
    cost_source: str | None = None,
    cost_truth_level: str | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_SUPPLIER_ONLY,
) -> list[str]:
    reasons: list[str] = []
    effective_cost_trusted = effective_cost_is_business_trusted(
        has_manual_cost=has_manual_cost,
        has_real_manual_cost=has_real_manual_cost,
        has_placeholder_cost=has_placeholder_cost,
        cost_source=cost_source,
        cost_truth_level=cost_truth_level,
        cost_trust_policy=cost_trust_policy,
    )
    if not has_manual_cost:
        reasons.append("missing_manual_cost")
    elif not effective_cost_trusted:
        reasons.append("supplier_cost_not_confirmed")
    if has_placeholder_cost:
        reasons.append("placeholder_cost")
    if finance_rows <= 0:
        reasons.append("finance_not_confirmed")
    return reasons


def build_global_trust_decision(
    *,
    supplier_confirmed_revenue_coverage_percent: float | None,
    failed_domains: list[str],
    unresolved_unmatched_sku_count: int,
    latest_stocks_status: str | None,
    blocking_open_issue_count: int,
    article_audit_consistent: bool | None,
    scheduler_stable: bool = True,
    trusted_revenue_cost_coverage_percent: float | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_SUPPLIER_ONLY,
) -> TrustDecision:
    blocked_reasons: list[str] = []
    policy_accepts_operator = cost_policy_accepts_operator_baseline(cost_trust_policy)
    owner_approved_final = cost_policy_owner_approves_final(cost_trust_policy)
    effective_cost_coverage = (
        trusted_revenue_cost_coverage_percent
        if policy_accepts_operator and trusted_revenue_cost_coverage_percent is not None
        else supplier_confirmed_revenue_coverage_percent
    )
    if (
        owner_approved_final
        and effective_cost_coverage is not None
        and effective_cost_coverage >= 95
    ):
        return TrustDecision(
            business_trusted=True,
            trust_state=TRUST_STATE_TRUSTED,
            blocked_reasons=[],
            can_generate_business_actions=True,
        )
    if effective_cost_coverage is None or effective_cost_coverage < 95:
        blocked_reasons.append("supplier_cost_coverage_below_threshold")
    if failed_domains:
        blocked_reasons.append("failed_sync_domains")
    if unresolved_unmatched_sku_count > 0:
        blocked_reasons.append("unmatched_sku_detected")
    if latest_stocks_status != "completed":
        blocked_reasons.append("latest_stocks_not_completed")
    if blocking_open_issue_count > 0:
        blocked_reasons.append("open_blocking_dq_issues")
    if article_audit_consistent is False:
        blocked_reasons.append("article_audit_mismatch")
    if not scheduler_stable:
        blocked_reasons.append("scheduler_instability")

    business_trusted = len(blocked_reasons) == 0
    if business_trusted:
        trust_state = TRUST_STATE_TRUSTED
    else:
        trust_state = (
            TRUST_STATE_DATA_BLOCKED
            if any(reason in GLOBAL_HARD_BLOCKER_REASONS for reason in blocked_reasons)
            else TRUST_STATE_TEST_ONLY
        )
    return TrustDecision(
        business_trusted=business_trusted,
        trust_state=trust_state,
        blocked_reasons=blocked_reasons,
        can_generate_business_actions=trust_state != TRUST_STATE_DATA_BLOCKED,
    )


def build_cost_coverage_decision(
    *,
    total_revenue: float | int | str | None,
    supplier_confirmed_revenue: float | int | str | None,
    operator_baseline_revenue: float | int | str | None,
    missing_cost_revenue: float | int | str | None = None,
    cost_trust_policy: str | None = COST_TRUST_POLICY_OPERATOR_BASELINE,
    final_threshold_percent: float = 95.0,
) -> CostCoverageDecision:
    total = _decimal0(total_revenue)
    supplier_confirmed = _decimal0(supplier_confirmed_revenue)
    operator_baseline = _decimal0(operator_baseline_revenue)
    if missing_cost_revenue is None:
        missing = max(total - supplier_confirmed - operator_baseline, 0.0)
    else:
        missing = _decimal0(missing_cost_revenue)
    policy = (
        str(cost_trust_policy or COST_TRUST_POLICY_OPERATOR_BASELINE).strip().lower()
    )
    operator_allowed = cost_policy_accepts_operator_baseline(policy)
    owner_approved_final = cost_policy_owner_approves_final(policy)
    operational_revenue = supplier_confirmed + (
        operator_baseline if operator_allowed else 0.0
    )
    business_accepted_revenue = operational_revenue
    operational_percent = _percent0(operational_revenue, total)
    supplier_percent = _percent0(supplier_confirmed, total)
    business_percent = _percent0(business_accepted_revenue, total)
    can_use_for_operations = operational_percent >= final_threshold_percent
    can_use_for_final_profit = (
        business_percent >= final_threshold_percent
        if owner_approved_final
        else supplier_percent >= final_threshold_percent
    )

    has_supplier = supplier_confirmed > 0
    has_operator = operator_baseline > 0
    if total <= 0 or (supplier_confirmed + operator_baseline) <= 0:
        truth_level = "missing"
    elif has_supplier and has_operator:
        truth_level = "mixed"
    elif has_supplier:
        truth_level = COST_TRUTH_SUPPLIER_CONFIRMED
    elif has_operator:
        truth_level = COST_TRUTH_OPERATOR_BASELINE
    else:
        truth_level = "missing"

    if total <= 0:
        message = "Нет выручки, поэтому покрытие себестоимостью не оценивается"
    elif can_use_for_final_profit and owner_approved_final:
        message = "Текущая себестоимость временно принята как итоговая до загрузки обновленных реальных данных"
    elif can_use_for_final_profit:
        message = (
            "Подтвержденной реальной себестоимости достаточно для итоговой прибыли"
        )
    elif can_use_for_operations:
        message = "Текущей себестоимости достаточно для работы, но подтвержденной реальной себестоимости пока не хватает"
    elif operator_baseline > 0 and not operator_allowed:
        message = "Себестоимость есть только во временно принятом виде, но текущие правила не разрешают использовать ее даже для операционной работы"
    elif supplier_confirmed + operator_baseline > 0:
        message = "Себестоимость покрывает выручку только частично, поэтому решения нужно принимать осторожно"
    else:
        message = "Себестоимости недостаточно, итоговую прибыль считать нельзя"

    return CostCoverageDecision(
        operational_cost_coverage_percent=operational_percent,
        supplier_confirmed_cost_coverage_percent=supplier_percent,
        business_accepted_cost_coverage_percent=business_percent,
        cost_policy=policy,
        cost_truth_level=truth_level,
        can_use_for_operations=can_use_for_operations,
        can_use_for_final_profit=can_use_for_final_profit,
        missing_cost_revenue=missing,
        operator_baseline_revenue=operator_baseline,
        supplier_confirmed_revenue=supplier_confirmed,
        message=message,
    )


def build_public_trust_snapshot(
    *,
    operational_trusted: bool,
    supplier_confirmed_revenue_coverage_percent: float | int | str | None,
    operator_baseline_revenue_coverage_percent: float | int | str | None,
    trusted_revenue_cost_coverage_percent: float | int | str | None,
    financial_final_blockers_total: int,
    cost_trust_policy: str | None,
    finance_reconciliation_clean: bool,
    blocked_reasons: list[str] | None = None,
    placeholder_only: bool = False,
    all_open_issues_total: int = 0,
    blocking_open_issues_total: int = 0,
    final_threshold_percent: float = 90.0,
    preserve_blocker_counts: bool = False,
) -> PublicTrustSnapshot:
    blocked_reasons = list(blocked_reasons or [])
    supplier_percent = _decimal0(supplier_confirmed_revenue_coverage_percent)
    operator_percent = _decimal0(operator_baseline_revenue_coverage_percent)
    trusted_percent = _decimal0(trusted_revenue_cost_coverage_percent)
    owner_approved_final = cost_policy_owner_approves_final(cost_trust_policy)
    blockers_total = max(int(financial_final_blockers_total or 0), 0)
    public_blockers_total = (
        blockers_total
        if preserve_blocker_counts
        else (0 if owner_approved_final else blockers_total)
    )
    hard_blocked = any(
        reason in GLOBAL_HARD_BLOCKER_REASONS for reason in blocked_reasons
    )
    business_trusted = bool(operational_trusted)
    effective_final_percent = (
        trusted_percent if owner_approved_final else supplier_percent
    )
    financial_final = (
        business_trusted
        and effective_final_percent >= final_threshold_percent
        and public_blockers_total == 0
        and (True if owner_approved_final else finance_reconciliation_clean)
    )
    if hard_blocked and not owner_approved_final:
        trust_state = TRUST_STATE_BLOCKED
        business_trusted = False
        operational_trusted = False
        financial_final = False
    elif financial_final:
        trust_state = TRUST_STATE_FINANCIAL_FINAL
    elif business_trusted:
        trust_state = TRUST_STATE_OPERATIONAL_PROVISIONAL
    elif placeholder_only:
        trust_state = TRUST_STATE_TEST_ONLY
    elif trusted_percent > 0 or operator_percent > 0:
        trust_state = (
            TRUST_STATE_OPERATIONAL_PROVISIONAL
            if operational_trusted
            else TRUST_STATE_TEST_ONLY
        )
    else:
        trust_state = (
            TRUST_STATE_UNKNOWN
            if blockers_total <= 0 and not blocked_reasons
            else TRUST_STATE_BLOCKED
        )

    return PublicTrustSnapshot(
        operational_trusted=bool(operational_trusted),
        business_trusted=bool(business_trusted),
        financial_final=bool(financial_final),
        trust_state=trust_state,
        cost_trust_policy=(
            str(cost_trust_policy).strip().lower()
            if cost_trust_policy is not None
            else None
        ),
        supplier_confirmed_revenue_coverage_percent=supplier_percent,
        operator_baseline_revenue_coverage_percent=operator_percent,
        trusted_revenue_cost_coverage_percent=trusted_percent,
        financial_final_blockers_total=public_blockers_total,
        final_profit_blockers_total=public_blockers_total,
        all_open_issues_total=max(int(all_open_issues_total or 0), 0),
        blocking_open_issues_total=(
            max(int(blocking_open_issues_total or 0), 0)
            if preserve_blocker_counts
            else (
                0
                if owner_approved_final
                else max(int(blocking_open_issues_total or 0), 0)
            )
        ),
    )
