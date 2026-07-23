from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.action_registry import (
    ACTION_ALIASES,
    normalize_action_codes,
)
from app.core.redaction import redact_sensitive_text
from app.schemas.data_quality import issue_fixability_contract
from app.schemas.evidence import (
    EvidenceLedger,
    confidence_from_trust_state,
    evidence_ledger,
)
from app.schemas.money_trust import MoneyTrustInfo, classify_money_trust


PortalStatus = Literal[
    "ok",
    "not_configured",
    "unavailable",
    "empty",
    "beta",
    "disabled",
    "degraded",
    "blocked",
    "clean",
    "warning",
    "critical",
    "not_analyzed",
    "running",
    "collecting",
    "ready",
    "partial",
    "failed",
]
ModuleRuntimeStatus = Literal[
    "disabled",
    "not_configured",
    "beta_readonly",
    "beta_draft_only",
    "enabled_safe",
    "enabled_write_actions",
]
PortalModuleName = Literal[
    "finance",
    "expenses",
    "doctor",
    "actions",
    "products",
    "checker",
    "stockops",
    "grouping",
    "reputation",
    "claims",
    "photo",
    "experiments",
    "results",
]

SECRET_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "credential",
    "encrypted_token",
    "encryption_key",
    "headers",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
)
SAFE_SECRET_FIELD_NAMES = {
    "configured_token_categories",
    "missing_token_categories",
    "required_token_categories",
    "token_categories",
    "token_category",
    "token_configured",
    "token_ok",
    "required_token_category",
}


def _scrub_portal_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_portal_secrets(item)
            for key, item in value.items()
            if str(key).lower() in SAFE_SECRET_FIELD_NAMES
            or not any(token in str(key).lower() for token in SECRET_FIELD_TOKENS)
        }
    if isinstance(value, list):
        return [_scrub_portal_secrets(item) for item in value]
    return value


class PortalBaseModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def scrub_secret_fields(cls, data: Any) -> Any:
        return _scrub_portal_secrets(data)


class PortalAccountSummary(PortalBaseModel):
    id: int
    name: str
    seller_name: str | None = None
    external_account_id: str | None = None
    timezone: str
    is_active: bool


class PortalModuleHealthItem(PortalBaseModel):
    status: PortalStatus
    module: PortalModuleName | None = None
    enabled: bool = False
    configured: bool = False
    visible: bool = False
    beta: bool = False
    navigation_group: Literal["core", "operator", "beta", "hidden"] = "hidden"
    reason: str | None = None
    required_env_keys: list[str] = Field(default_factory=list)
    last_checked_at: datetime | None = None
    message: str | None = None
    detail: str | None = None
    warnings: list[str] = Field(default_factory=list)
    mode: str | None = None
    eligible_products: int | None = None
    unique_products_analyzed: int | None = None
    coverage_percent: float | None = None
    actionable_open_issues: int | None = None
    informational_observations: int | None = None
    last_run_id: int | None = None
    last_success_at: datetime | None = None
    analyzed_products: int | None = None
    regions_count: int | None = None
    movements_count: int | None = None
    unmapped_warehouses: int | None = None
    source_freshness: dict[str, Any] = Field(default_factory=dict)
    runtime_mode: Literal["local", "external_adapter", "disabled"] = "disabled"
    runtime_status: ModuleRuntimeStatus = "disabled"
    marketplace_write_policy: dict[str, Any] = Field(default_factory=dict)
    dangerous_actions_enabled: bool = False
    publish_enabled: bool = False
    auto_publish_enabled: bool = False
    chat_send_enabled: bool = False

    @model_validator(mode="after")
    def fill_legacy_detail(self) -> "PortalModuleHealthItem":
        if self.detail is None and self.message is not None:
            self.detail = self.message
        if self.message is None and self.detail is not None:
            self.message = self.detail
        if self.reason is None:
            self.reason = self.message or self.detail
        return self


class PortalModuleHealth(PortalBaseModel):
    finance: PortalModuleHealthItem
    expenses: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="expenses",
            status="ok",
            enabled=True,
            configured=True,
            visible=True,
            navigation_group="core",
            message="Expenses use finance reports and money marts",
        )
    )
    doctor: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="doctor",
            status="disabled",
            enabled=False,
            configured=False,
            visible=False,
            navigation_group="core",
            message="Legacy profit diagnostics are hidden; Action Center is the primary problem surface",
        )
    )
    actions: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="actions",
            status="ok",
            enabled=True,
            configured=True,
            visible=True,
            navigation_group="core",
            message="Action Center uses finance database",
        )
    )
    products: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="products",
            status="ok",
            enabled=True,
            configured=True,
            visible=True,
            navigation_group="core",
            message="Products and Product 360 use finance data",
        )
    )
    checker: PortalModuleHealthItem
    stockops: PortalModuleHealthItem
    grouping: PortalModuleHealthItem
    reputation: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="reputation",
            status="disabled",
            enabled=False,
            configured=False,
            message="reputation module is disabled",
        )
    )
    claims: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="claims",
            status="disabled",
            enabled=False,
            configured=False,
            message="claims module is disabled",
        )
    )
    photo: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="photo",
            status="disabled",
            enabled=False,
            configured=False,
            message="photo module is disabled",
        )
    )
    experiments: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="experiments",
            status="ok",
            enabled=True,
            configured=True,
            visible=True,
            navigation_group="operator",
            message="experiments module uses finance database",
        )
    )
    results: PortalModuleHealthItem = Field(
        default_factory=lambda: PortalModuleHealthItem(
            module="results",
            status="ok",
            enabled=True,
            configured=True,
            visible=True,
            navigation_group="operator",
            message="Result tracking uses finance database",
        )
    )


class PortalOverviewRead(PortalBaseModel):
    account: PortalAccountSummary | None = None
    date_range: dict[str, Any] = Field(default_factory=dict)
    date_from: date | None = None
    date_to: date | None = None
    money_summary: dict[str, Any] | None = None
    data_trust: dict[str, Any] | None = None
    data_blockers: dict[str, Any] | None = None
    cost_status: dict[str, Any] = Field(default_factory=dict)
    doctor_summary: dict[str, Any] = Field(default_factory=dict)
    top_problems: list[dict[str, Any]] = Field(default_factory=list)
    operator_actions: list[dict[str, Any]] = Field(default_factory=list)
    product_risks: list[dict[str, Any]] = Field(default_factory=list)
    reputation: dict[str, Any] = Field(default_factory=dict)
    claims: dict[str, Any] = Field(default_factory=dict)
    top_actions: list["PortalActionRead"] = Field(default_factory=list)
    top_products: list["PortalProductRead"] = Field(default_factory=list)
    module_health: PortalModuleHealth
    unavailable_sources: list[str] = Field(default_factory=list)


PortalDashboardPulseState = Literal[
    "ok",
    "warning",
    "critical",
    "blocked",
    "not_checked",
    "missing_data",
    "stale",
    "syncing",
]


class PortalDashboardPrimaryAction(PortalBaseModel):
    label: str = ""
    screen_path: str | None = None
    endpoint: str | None = None
    action_code: str | None = None
    target_href: str | None = None


class PortalDashboardSourceFreshness(PortalBaseModel):
    status: Literal["fresh", "stale", "missing", "syncing", "not_checked"] = (
        "not_checked"
    )
    required_sources: list[str] = Field(default_factory=list)
    fresh_sources: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    syncing_sources: list[str] = Field(default_factory=list)
    last_synced_at: datetime | None = None
    freshness_hours: float | None = None
    message: str = ""


class PortalDashboardBusinessVerdict(PortalBaseModel):
    state: PortalDashboardPulseState = "not_checked"
    title: str
    short_explanation: str
    trust_state: str = "not_checked"
    impact_type: str = "system_check"
    checked: bool = False
    has_data: bool = False
    has_risk: bool | None = None
    primary_action: PortalDashboardPrimaryAction = Field(
        default_factory=PortalDashboardPrimaryAction
    )


class PortalDashboardPulseCard(PortalBaseModel):
    code: Literal["sales", "profit_margin", "money_at_risk", "stock", "cards", "data"]
    title: str
    value: float | int | str | None = None
    unit: str = ""
    state: PortalDashboardPulseState
    checked: bool
    has_data: bool
    has_risk: bool | None = None
    trust_state: str = "not_checked"
    impact_type: str = "system_check"
    short_explanation: str
    primary_action: PortalDashboardPrimaryAction = Field(
        default_factory=PortalDashboardPrimaryAction
    )
    evidence_available: bool = False
    source_freshness: PortalDashboardSourceFreshness = Field(
        default_factory=PortalDashboardSourceFreshness
    )


class PortalDashboardAttentionItem(PortalBaseModel):
    code: str
    title: str
    pulse_code: str
    severity: str = "warning"
    priority: str = "P2"
    count: int = 0
    state: PortalDashboardPulseState = "warning"
    trust_state: str = "provisional"
    impact_type: str = "system_check"
    short_explanation: str = ""
    primary_action: PortalDashboardPrimaryAction = Field(
        default_factory=PortalDashboardPrimaryAction
    )
    evidence_available: bool = False
    source_freshness: PortalDashboardSourceFreshness = Field(
        default_factory=PortalDashboardSourceFreshness
    )
    source: str = "dashboard_data_health"


class PortalDashboardPlanItem(PortalBaseModel):
    id: str
    title: str
    priority: str = "P2"
    source: str = ""
    source_code: str | None = None
    screen_path: str | None = None
    endpoint: str | None = None
    action_code: str | None = None
    trust_state: str = "provisional"
    impact_type: str = "system_check"
    reason: str = ""
    expected_impact_amount: float | None = None
    saved_money_claimed: bool = False


class PortalDashboardDataConfidenceItem(PortalBaseModel):
    source_code: str
    title: str
    state: Literal["fresh", "stale", "missing", "syncing", "not_checked", "error"] = (
        "not_checked"
    )
    last_synced_at: datetime | None = None
    freshness_hours: float | None = None
    required_for: list[str] = Field(default_factory=list)
    blocks_calculation: list[str] = Field(default_factory=list)
    target_href: str | None = None
    message: str = ""


class PortalDashboardRecentResultsSummary(PortalBaseModel):
    status: str = "ok"
    total: int = 0
    summary: dict[str, Any] = Field(default_factory=dict)
    by_outcome: dict[str, int] = Field(default_factory=dict)
    recent_events: list[dict[str, Any]] = Field(default_factory=list)
    saved_money_claimed: bool = False


class PortalDashboardOnboardingState(PortalBaseModel):
    state: Literal[
        "ready", "needs_account", "needs_sync", "needs_costs", "needs_data_fix"
    ] = "ready"
    missing_steps: list[str] = Field(default_factory=list)
    next_step: PortalDashboardPrimaryAction | None = None


class PortalDashboardOverviewRead(PortalBaseModel):
    account: PortalAccountSummary | None = None
    date_range: dict[str, Any] = Field(default_factory=dict)
    business_verdict: PortalDashboardBusinessVerdict
    business_pulse: list[PortalDashboardPulseCard] = Field(default_factory=list)
    top_attention_items: list[PortalDashboardAttentionItem] = Field(
        default_factory=list
    )
    today_plan: list[PortalDashboardPlanItem] = Field(default_factory=list)
    data_confidence: list[PortalDashboardDataConfidenceItem] = Field(
        default_factory=list
    )
    recent_results_summary: PortalDashboardRecentResultsSummary = Field(
        default_factory=PortalDashboardRecentResultsSummary
    )
    onboarding_state: PortalDashboardOnboardingState = Field(
        default_factory=PortalDashboardOnboardingState
    )
    unavailable_sources: list[str] = Field(default_factory=list)


ActionCenterEvidenceState = Literal[
    "full_evidence",
    "partial_evidence",
    "missing_evidence",
    "read_only_signal",
]

ACTION_CENTER_ACTION_ALIASES = dict(ACTION_ALIASES)


def normalize_action_center_allowed_actions(actions: list[str]) -> list[str]:
    return normalize_action_codes(actions, allowed_for_seller=True)


ActionCenterSourceStatus = Literal["fresh", "stale", "missing", "not_configured"]
ActionCenterSolveStepStatus = Literal[
    "ready", "available", "blocked", "waiting_for_data", "done"
]


class ActionCenterDataFreshness(PortalBaseModel):
    required_sources: list[str] = Field(default_factory=list)
    source_status: ActionCenterSourceStatus = "fresh"
    last_synced_at: datetime | str | None = None
    blocking_sources: list[str] = Field(default_factory=list)
    freshness_notes: list[str] = Field(default_factory=list)

    @field_validator("source_status", mode="before")
    @classmethod
    def normalize_source_status(cls, value: Any) -> str:
        status = str(value or "fresh").strip().lower().replace("-", "_")
        return (
            status
            if status in {"fresh", "stale", "missing", "not_configured"}
            else "fresh"
        )

    @field_validator(
        "required_sources", "blocking_sources", "freshness_notes", mode="before"
    )
    @classmethod
    def normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class ActionCenterSolveMapStep(PortalBaseModel):
    step_id: str
    order: int
    title: str
    description: str = ""
    status: ActionCenterSolveStepStatus = "available"
    action_code: str | None = None
    target_href: str | None = None
    required_metrics: list[str] = Field(default_factory=list)
    blocking_reason: str | None = None
    completion_signal: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: Any) -> str:
        status = str(value or "available").strip().lower().replace("-", "_")
        return (
            status
            if status in {"ready", "available", "blocked", "waiting_for_data", "done"}
            else "available"
        )

    @field_validator("required_metrics", mode="before")
    @classmethod
    def normalize_metrics(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class ActionCenterSolveMap(PortalBaseModel):
    title: str = "Карта решения"
    summary: str = ""
    steps: list[ActionCenterSolveMapStep] = Field(default_factory=list)
    primary_action_code: str | None = None
    secondary_action_codes: list[str] = Field(default_factory=list)
    recheck_description: str = ""

    @field_validator("secondary_action_codes", mode="before")
    @classmethod
    def normalize_secondary_action_codes(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value.strip()] if value.strip() else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []

    @model_validator(mode="after")
    def fill_action_contract(self) -> "ActionCenterSolveMap":
        ordered_steps = sorted(self.steps, key=lambda item: item.order)
        available_actions: list[str] = []
        for step in ordered_steps:
            action_code = str(step.action_code or "").strip()
            if not action_code or step.status not in {"ready", "available"}:
                continue
            if action_code in {
                "assign",
                "dismiss",
                "open_product",
                "open_results",
                "recheck",
            }:
                continue
            if action_code not in available_actions:
                available_actions.append(action_code)
        if self.primary_action_code not in available_actions:
            self.primary_action_code = (
                available_actions[0] if available_actions else None
            )
        if not self.secondary_action_codes:
            self.secondary_action_codes = [
                action
                for action in available_actions
                if action != self.primary_action_code
            ]
        if not str(self.recheck_description or "").strip():
            recheck_step = next(
                (step for step in ordered_steps if step.action_code == "recheck"), None
            )
            self.recheck_description = (
                recheck_step.description
                if recheck_step is not None and recheck_step.description
                else "Повторите проверку после выполнения шагов и обновления данных источников."
            )
        return self


def _action_center_source_key(value: Any) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return None
    if any(token in text for token in ("stock", "остат", "inventory")):
        return "stocks"
    if any(
        token in text
        for token in (
            "sales",
            "sale_",
            "orders",
            "order_",
            "sku_daily",
            "продаж",
            "заказ",
        )
    ):
        return "sales"
    if any(
        token in text
        for token in ("cost", "cogs", "unit_cost", "manual_cost", "себестоим")
    ):
        return "costs"
    if any(token in text for token in ("price", "pricing", "цен")):
        return "prices"
    if any(token in text for token in ("finance", "realization", "report", "финанс")):
        return "finance"
    if any(token in text for token in ("ads", "advert", "реклам")):
        return "ads"
    if any(token in text for token in ("promo", "promotion", "акци")):
        return "promotions"
    if any(token in text for token in ("checker", "card", "content", "карточ")):
        return "cards"
    return None


def _unique_source_keys(values: list[Any]) -> list[str]:
    items: list[str] = []
    for value in values:
        key = _action_center_source_key(value)
        if key and key not in items:
            items.append(key)
    return items


def _source_keys_from_records(records: Any) -> list[str]:
    if not isinstance(records, list):
        return []
    values: list[Any] = []
    for item in records:
        if not isinstance(item, dict):
            continue
        values.extend(
            [
                item.get("source"),
                item.get("source_table"),
                item.get("table"),
                item.get("source_endpoint"),
                item.get("wb_endpoint"),
                item.get("metric_code"),
                item.get("label"),
            ]
        )
    return _unique_source_keys(values)


def _is_content_quality_freshness_action(
    payload: dict[str, Any], raw: dict[str, Any], problem_code: str | None
) -> bool:
    code = (
        str(
            problem_code
            or payload.get("detector_code")
            or payload.get("issue_code")
            or raw.get("detector_code")
            or raw.get("issue_code")
            or ""
        )
        .strip()
        .lower()
    )
    action_type = (
        str(payload.get("action_type") or raw.get("action_type") or "").strip().lower()
    )
    source_module = (
        str(payload.get("source_module") or raw.get("source_module") or "")
        .strip()
        .lower()
    )
    source = str(payload.get("source") or raw.get("source") or "").strip().lower()
    return bool(
        payload.get("content_quality_signal")
        or payload.get("checker_problem_bridge")
        or raw.get("content_quality_signal")
        or raw.get("checker_problem_bridge")
        or action_type == "card_quality_fix"
        or source in {"card_quality_issues", "checker_issues"}
        or (
            source_module == "checker"
            and any(
                token in code
                for token in (
                    "title",
                    "description",
                    "photo",
                    "media",
                    "card_quality",
                    "content",
                )
            )
        )
    )


def _is_content_quality_data_blocked(
    payload: dict[str, Any], raw: dict[str, Any]
) -> bool:
    impact_type = (
        str(payload.get("impact_type") or raw.get("impact_type") or "").strip().lower()
    )
    trust_state = (
        str(payload.get("trust_state") or raw.get("trust_state") or "").strip().lower()
    )
    if impact_type == "data_blocker" or trust_state == "blocked":
        return True
    for value in (
        payload.get("missing_data"),
        raw.get("missing_data"),
        payload.get("missing_metrics"),
        raw.get("missing_metrics"),
    ):
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def _inferred_required_sources(problem_code: str | None) -> list[str]:
    code = str(problem_code or "").strip().lower()
    if code in {"low_stock_risk", "fast_stock_depletion"}:
        return ["stocks", "sales"]
    if code == "missing_cost_blocks_profit":
        return ["costs"]
    if code == "negative_unit_profit":
        return ["sales", "finance", "costs"]
    if code in {"overstock_slow_moving", "dead_stock", "promo_not_profitable"}:
        return ["stocks", "sales"]
    if code == "price_below_safe_margin":
        return ["prices", "costs"]
    if code == "ads_spend_without_profit":
        return ["ads", "sales", "costs"]
    if code == "card_quality_issue":
        return ["cards"]
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _action_center_data_freshness(
    *,
    payload: dict[str, Any],
    raw: dict[str, Any],
    evidence_ledger_value: EvidenceLedger | None,
    source_references: list[dict[str, Any]],
    problem_code: str | None,
) -> ActionCenterDataFreshness:
    explicit = (
        payload.get("data_freshness")
        or raw.get("data_freshness")
        or payload.get("source_freshness")
        or raw.get("source_freshness")
    )
    explicit_dict = explicit if isinstance(explicit, dict) else {}
    required_sources: list[str] = []
    content_quality_action = _is_content_quality_freshness_action(
        payload, raw, problem_code
    )
    content_quality_data_blocked = _is_content_quality_data_blocked(payload, raw)
    content_quality_local_only = (
        content_quality_action
        and not content_quality_data_blocked
        and not bool(
            payload.get("business_metric_evidence")
            or raw.get("business_metric_evidence")
        )
    )
    for item in _string_list(explicit_dict.get("required_sources")) + _string_list(
        explicit_dict.get("requiredSources")
    ):
        key = _action_center_source_key(item) or str(item).strip().lower()
        if key and key not in required_sources:
            required_sources.append(key)
    for item in (
        _source_keys_from_records(source_references)
        + _source_keys_from_records(
            [
                fact.model_dump(mode="json")
                for fact in (
                    evidence_ledger_value.input_facts if evidence_ledger_value else []
                )
            ]
        )
        + _inferred_required_sources(problem_code)
    ):
        if item and item not in required_sources:
            required_sources.append(item)
    missing_values: list[Any] = []
    if evidence_ledger_value is not None:
        missing_values.extend(evidence_ledger_value.missing_data)
    missing_values.extend(_string_list(payload.get("missing_data")))
    missing_values.extend(_string_list(raw.get("missing_data")))
    missing_values.extend(_string_list(payload.get("missing_metrics")))
    missing_values.extend(_string_list(raw.get("missing_metrics")))
    price_safety = (
        payload.get("price_safety")
        if isinstance(payload.get("price_safety"), dict)
        else raw.get("price_safety")
    )
    if isinstance(price_safety, dict):
        missing_values.extend(
            _string_list(price_safety.get("missing_required_metrics"))
        )
    blocking_sources: list[str] = []
    for item in (
        _string_list(explicit_dict.get("blocking_sources"))
        + _string_list(explicit_dict.get("blockingSources"))
        + _unique_source_keys(missing_values)
    ):
        key = _action_center_source_key(item) or str(item).strip().lower()
        if key and key not in blocking_sources:
            blocking_sources.append(key)
    if content_quality_local_only:
        required_sources = ["cards"]
        blocking_sources = []
    raw_status = (
        explicit_dict.get("source_status")
        or explicit_dict.get("status")
        or payload.get("source_status")
        or raw.get("source_status")
        or ("missing" if blocking_sources else "fresh")
    )
    status = str(raw_status or "fresh").strip().lower().replace("-", "_")
    if status not in {"fresh", "stale", "missing", "not_configured"}:
        status = "fresh"
    if content_quality_local_only and status in {"stale", "missing", "not_configured"}:
        status = "fresh"
    notes = _string_list(explicit_dict.get("freshness_notes")) + _string_list(
        explicit_dict.get("notes")
    )
    if status != "fresh" and not notes:
        notes.append(
            "Источник устарел: выводы предварительные до новой синхронизации."
            if status == "stale"
            else "Источник не готов: доказательства и денежное влияние заблокированы до синхронизации."
        )
    last_synced_at = (
        explicit_dict.get("last_synced_at")
        or explicit_dict.get("lastSyncedAt")
        or payload.get("last_synced_at")
        or raw.get("last_synced_at")
    )
    return ActionCenterDataFreshness(
        required_sources=required_sources,
        source_status=status,  # type: ignore[arg-type]
        last_synced_at=last_synced_at,
        blocking_sources=blocking_sources,
        freshness_notes=notes,
    )


def _freshness_blocks_solve_map_action(
    data_freshness: ActionCenterDataFreshness | None,
) -> bool:
    return bool(
        data_freshness is not None
        and (
            data_freshness.source_status != "fresh"
            or bool(data_freshness.blocking_sources)
        )
    )


def _append_query(path: str, **values: Any) -> str:
    base, _, existing = path.partition("?")
    params = dict(parse_qsl(existing, keep_blank_values=False))
    for key, value in values.items():
        if value is None:
            continue
        text = str(value).strip()
        if text:
            params[key] = text
    query = urlencode(params)
    return f"{base}?{query}" if query else base


def _positive_int_from(*values: Any) -> int | None:
    for value in values:
        if value is None:
            continue
        try:
            parsed = int(str(value).split(":")[-1])
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return None


def _solve_map_target_href(
    action_code: str | None,
    nm_id: int | None = None,
    problem_instance_id: int | None = None,
) -> str | None:
    if action_code == "create_task":
        return _append_query(
            "/action-center", problem_instance_id=problem_instance_id, nm_id=nm_id
        )
    if action_code == "open_data_fix":
        return _append_query(
            "/data-fix", problem_instance_id=problem_instance_id, nm_id=nm_id
        )
    if action_code == "upload_cost":
        return _append_query(
            "/costs?focus=missing-costs",
            problem_instance_id=problem_instance_id,
            nm_id=nm_id,
        )
    if action_code == "map_sku":
        return _append_query(
            "/data-fix?code=unmatched_sku",
            problem_instance_id=problem_instance_id,
            nm_id=nm_id,
        )
    if action_code == "open_supply_planner":
        return _append_query(
            "/stock-control?tab=supply",
            problem_instance_id=problem_instance_id,
            nm_id=nm_id,
        )
    if action_code == "open_ads_dashboard":
        return _append_query(
            "/ads", problem_instance_id=problem_instance_id, nm_id=nm_id
        )
    if action_code == "open_price_review":
        return _append_query(
            f"/products/{nm_id}?tab=price" if nm_id is not None else "/products",
            problem_instance_id=problem_instance_id,
        )
    if action_code == "open_promo_planner":
        return _append_query(
            f"/products/{nm_id}?tab=promo" if nm_id is not None else "/products",
            problem_instance_id=problem_instance_id,
        )
    if action_code == "open_product":
        return _append_query(
            f"/products/{nm_id}" if nm_id is not None else "/products",
            problem_instance_id=problem_instance_id,
        )
    if action_code == "run_checker":
        return _append_query(
            f"/checker/{nm_id}" if nm_id is not None else "/products",
            problem_instance_id=problem_instance_id,
        )
    if action_code == "open_results":
        return _append_query(
            "/results", problem_instance_id=problem_instance_id, nm_id=nm_id
        )
    if action_code == "open_reputation":
        return _append_query(
            "/reputation", problem_instance_id=problem_instance_id, nm_id=nm_id
        )
    return None


def _price_safety_blocks_solve_map_action(price_safety: dict[str, Any] | None) -> bool:
    if not isinstance(price_safety, dict) or not price_safety:
        return True
    missing = price_safety.get("missing_required_metrics")
    if isinstance(missing, list) and missing:
        return True
    status = str(price_safety.get("status") or "").strip().lower()
    if status in {"data_incomplete", "not_enough_data", "missing"}:
        return True
    if price_safety.get("can_recommend_price_decrease") is False:
        return True
    return False


def _solve_map_blocking_reason(
    *,
    action_code: str | None,
    allowed_actions: list[str],
    data_freshness: ActionCenterDataFreshness | None,
    price_safety: dict[str, Any] | None,
    price_safety_required: bool = False,
) -> str | None:
    if action_code and action_code not in allowed_actions and action_code != "recheck":
        return "Действие не разрешено текущим правилом."
    if action_code in {
        "open_price_review",
        "open_promo_planner",
        "open_ads_dashboard",
    } and _freshness_blocks_solve_map_action(data_freshness):
        return "Нужна синхронизация"
    if price_safety_required and _price_safety_blocks_solve_map_action(price_safety):
        return "Не хватает данных для безопасной цены или промо."
    return None


def _solve_map_step(
    *,
    step_id: str,
    order: int,
    title: str,
    description: str,
    action_code: str | None = None,
    nm_id: int | None = None,
    problem_instance_id: int | None = None,
    required_metrics: list[str] | None = None,
    completion_signal: str | None = None,
    data_freshness: ActionCenterDataFreshness | None = None,
    allowed_actions: list[str] | None = None,
    price_safety: dict[str, Any] | None = None,
    price_safety_required: bool = False,
    force_status: ActionCenterSolveStepStatus | None = None,
) -> ActionCenterSolveMapStep:
    normalized_allowed = allowed_actions or []
    blocking_reason = _solve_map_blocking_reason(
        action_code=action_code,
        allowed_actions=normalized_allowed,
        data_freshness=data_freshness,
        price_safety=price_safety,
        price_safety_required=price_safety_required,
    )
    if force_status:
        status = force_status
    elif blocking_reason == "Нужна синхронизация":
        status = "waiting_for_data"
    elif blocking_reason:
        status = "blocked"
    elif action_code is None:
        status = "ready"
    else:
        status = "available"
    return ActionCenterSolveMapStep(
        step_id=step_id,
        order=order,
        title=title,
        description=description,
        status=status,  # type: ignore[arg-type]
        action_code=action_code,
        target_href=_solve_map_target_href(action_code, nm_id, problem_instance_id),
        required_metrics=required_metrics or [],
        blocking_reason=blocking_reason,
        completion_signal=completion_signal,
    )


def _solve_map_has_primary_action(steps: list[ActionCenterSolveMapStep]) -> bool:
    return any(
        step.action_code
        and step.status in {"ready", "available"}
        and step.action_code
        not in {"assign", "dismiss", "open_product", "open_results", "recheck"}
        and bool(step.target_href)
        for step in steps
    )


def _append_create_task_fallback_step(
    steps: list[ActionCenterSolveMapStep],
    *,
    allowed_actions: list[str],
    nm_id: int | None = None,
    problem_instance_id: int | None = None,
) -> list[ActionCenterSolveMapStep]:
    if _solve_map_has_primary_action(steps) or "create_task" not in allowed_actions:
        return steps
    steps.append(
        _solve_map_step(
            step_id="create_task",
            order=max((step.order for step in steps), default=0) + 1,
            title="Создать задачу владельцу",
            description="Нет доступного точного рабочего экрана: создайте безопасную задачу с владельцем, сроком и комментарием.",
            action_code="create_task",
            nm_id=nm_id,
            problem_instance_id=problem_instance_id,
            required_metrics=[],
            completion_signal="Задача создана и назначена владельцу.",
            allowed_actions=allowed_actions,
        )
    )
    return steps


_GENERIC_SOLVE_ACTION_TITLES: dict[str, tuple[str, str, list[str]]] = {
    "open_data_fix": (
        "Открыть исправление данных",
        "Проверьте строки и источники, из-за которых задача не может быть решена автоматически.",
        ["data_quality", "source_rows"],
    ),
    "upload_cost": (
        "Заполнить себестоимость",
        "Загрузите или сопоставьте себестоимость, чтобы пересчитать прибыль и безопасные действия.",
        ["cost_price", "manual_cost"],
    ),
    "open_supply_planner": (
        "Открыть план поставок",
        "Проверьте остаток, скорость продаж и план пополнения по товару.",
        ["stock_qty", "days_of_stock", "sales_velocity"],
    ),
    "open_ads_dashboard": (
        "Открыть рекламный review",
        "Проверьте расход, заказы, ставки и кампании до изменения рекламы.",
        ["ad_spend", "orders_7d", "drr"],
    ),
    "run_checker": (
        "Проверить карточку",
        "Откройте Checker, чтобы разобрать контент, фото, характеристики и конверсию.",
        ["card_quality_score", "conversion_rate"],
    ),
    "open_price_review": (
        "Проверить цену",
        "Откройте цену товара и сверите безопасную маржу перед изменениями.",
        ["price", "cost_price", "margin_pct"],
    ),
    "open_promo_planner": (
        "Открыть промо-план",
        "Проверьте скидку, промо и маржу перед ускорением продаж.",
        ["promo_spend", "price_after_discount", "margin_pct"],
    ),
    "open_reputation": (
        "Открыть репутацию",
        "Проверьте отзывы, вопросы и черновики ответов, связанные с товаром.",
        ["avg_rating", "negative_reviews", "unanswered_questions"],
    ),
    "create_task": (
        "Создать задачу владельцу",
        "Зафиксируйте владельца, срок и безопасный следующий шаг для ручной проверки.",
        [],
    ),
}


def _generic_solve_action(problem_code: str, allowed_actions: list[str]) -> str | None:
    preferences: list[str] = []
    code = problem_code.lower()
    if any(token in code for token in ("cost", "cogs", "expense")):
        preferences.extend(["upload_cost", "open_data_fix"])
    if any(token in code for token in ("stockout", "stock", "depletion", "supply")):
        preferences.append("open_supply_planner")
    if any(token in code for token in ("ad_", "ads", "drr", "cpo", "ctr")):
        preferences.append("open_ads_dashboard")
    if any(token in code for token in ("review", "rating", "question", "reputation")):
        preferences.append("open_reputation")
    if any(token in code for token in ("conversion", "card", "return", "content")):
        preferences.append("run_checker")
    if "price" in code:
        preferences.append("open_price_review")
    if any(token in code for token in ("promo", "storage", "dead", "overstock")):
        preferences.append("open_promo_planner")
    preferences.extend(
        [
            "open_data_fix",
            "upload_cost",
            "open_supply_planner",
            "open_ads_dashboard",
            "run_checker",
            "open_price_review",
            "open_promo_planner",
            "open_reputation",
            "create_task",
        ]
    )
    for action in preferences:
        if action in allowed_actions:
            return action
    return None


def _generic_action_center_solve_map(
    *,
    problem_code: str,
    allowed_actions: list[str],
    nm_id: int | None,
    problem_instance_id: int | None,
    data_freshness: ActionCenterDataFreshness | None,
    evidence_status: ActionCenterSolveStepStatus,
) -> ActionCenterSolveMap:
    action_code = _generic_solve_action(problem_code, allowed_actions)
    title, description, metrics = _GENERIC_SOLVE_ACTION_TITLES.get(
        action_code or "create_task",
        _GENERIC_SOLVE_ACTION_TITLES["create_task"],
    )
    steps = [
        _solve_map_step(
            step_id="evidence",
            order=1,
            title="Проверить доказательства",
            description="Откройте «Как посчитано?» и проверьте формулу, факты, источники и свежесть данных.",
            required_metrics=metrics,
            completion_signal="Доказательства и источники понятны.",
            data_freshness=data_freshness,
            allowed_actions=allowed_actions,
            force_status=evidence_status,
            problem_instance_id=problem_instance_id,
        )
    ]
    if action_code:
        steps.append(
            _solve_map_step(
                step_id="primary_action",
                order=2,
                title=title,
                description=description,
                action_code=action_code,
                nm_id=nm_id,
                problem_instance_id=problem_instance_id,
                required_metrics=metrics,
                completion_signal="Следующий безопасный шаг выполнен или передан владельцу.",
                data_freshness=data_freshness,
                allowed_actions=allowed_actions,
            )
        )
    steps.append(
        _solve_map_step(
            step_id="recheck",
            order=3,
            title="Перепроверить результат",
            description="Повторите проверку после действия и обновления данных источников.",
            action_code="recheck",
            nm_id=nm_id,
            problem_instance_id=problem_instance_id,
            required_metrics=metrics,
            completion_signal="Проблема перепроверена на свежих данных.",
            data_freshness=data_freshness,
            allowed_actions=allowed_actions,
        )
    )
    steps = _append_create_task_fallback_step(
        steps,
        allowed_actions=allowed_actions,
        nm_id=nm_id,
        problem_instance_id=problem_instance_id,
    )
    return ActionCenterSolveMap(
        title="Карта решения",
        summary="Проверьте доказательства, откройте самый близкий рабочий экран и перепроверьте проблему после действия.",
        steps=steps,
        recheck_description="Повторите проверку после выполнения шага и обновления WB/finance данных.",
    )


def build_action_center_solve_map(
    *,
    problem_code: str | None,
    allowed_actions: list[str],
    nm_id: int | None = None,
    problem_instance_id: int | None = None,
    data_freshness: ActionCenterDataFreshness | dict[str, Any] | None = None,
    price_safety: dict[str, Any] | None = None,
) -> ActionCenterSolveMap | None:
    code = str(problem_code or "").strip().lower()
    if code in {"card_quality_fix", "checker_card_quality", "content_quality_issue"}:
        code = "card_quality_issue"
    if not code:
        return None
    normalized_allowed = normalize_action_center_allowed_actions(allowed_actions)
    freshness = (
        data_freshness
        if isinstance(data_freshness, ActionCenterDataFreshness)
        else ActionCenterDataFreshness.model_validate(data_freshness)
        if isinstance(data_freshness, dict)
        else None
    )
    freshness_waiting = _freshness_blocks_solve_map_action(freshness)
    evidence_status: ActionCenterSolveStepStatus = (
        "waiting_for_data" if freshness_waiting else "ready"
    )

    maps: dict[str, dict[str, Any]] = {
        "missing_cost_blocks_profit": {
            "title": "Карта решения: себестоимость",
            "summary": "Сначала покажите, где не хватает себестоимости, затем загрузите или сопоставьте стоимость и перепроверьте прибыльность.",
            "metrics": ["cost_price", "manual_cost"],
            "recheck_description": "После загрузки или сопоставления себестоимости перепроверьте прибыльность товара.",
            "steps": [
                (
                    "open_data_fix",
                    "Открыть исправление данных",
                    "Перейдите в рабочий экран, где показаны строки без себестоимости.",
                    "open_data_fix",
                    ["cost_price"],
                    "Строка с товаром открыта в исправлении данных.",
                    False,
                ),
                (
                    "upload_cost",
                    "Загрузить или сопоставить себестоимость",
                    "Загрузите стоимость или сопоставьте SKU, если стоимость есть в другом справочнике.",
                    "upload_cost",
                    ["cost_price", "sku_mapping"],
                    "Стоимость заполнена или SKU сопоставлен.",
                    False,
                ),
                (
                    "recheck_profit",
                    "Перепроверить прибыльность",
                    "Запустите повторную проверку после загрузки себестоимости.",
                    "recheck",
                    ["unit_profit", "cost_price"],
                    "Прибыльность рассчитана с себестоимостью.",
                    False,
                ),
            ],
        },
        "negative_unit_profit": {
            "title": "Карта решения: отрицательная маржа",
            "summary": "Разберите цену, себестоимость, рекламу и промо; цену открывайте только когда есть безопасная экономика товара.",
            "metrics": [
                "unit_profit",
                "price",
                "cost_price",
                "ads_spend",
                "promo_spend",
            ],
            "recheck_description": "После исправления цены, затрат, рекламы или промо перепроверьте маржу и прибыль на единицу.",
            "steps": [
                (
                    "breakdown",
                    "Проверить разбор цены, себестоимости, рекламы и промо",
                    "Сверьте, какая часть делает маржу отрицательной.",
                    None,
                    ["unit_profit", "price", "cost_price", "ads_spend", "promo_spend"],
                    "Причина отрицательной маржи понятна.",
                    False,
                ),
                (
                    "price_review",
                    "Открыть пересмотр цены",
                    "Проверьте цену и безопасную маржу перед изменениями.",
                    "open_price_review",
                    ["price", "cost_price", "margin_pct"],
                    "Цена или план исправления маржи выбран.",
                    True,
                ),
                (
                    "cost_review",
                    "Исправить себестоимость",
                    "Если цена небезопасна из-за неполных затрат, сначала заполните себестоимость и комиссии.",
                    "upload_cost",
                    ["cost_price", "commission", "logistics_cost"],
                    "Себестоимость и комиссии заполнены.",
                    False,
                ),
                (
                    "recheck_margin",
                    "Перепроверить маржу",
                    "Повторите проверку после изменения цены, затрат, рекламы или промо.",
                    "recheck",
                    ["unit_profit", "margin_pct"],
                    "Маржа пересчитана после действия.",
                    False,
                ),
            ],
        },
        "overstock_slow_moving": {
            "title": "Карта решения: медленный остаток",
            "summary": "Сначала проверьте безопасность цены, затем используйте промо/цену, если маржа подтверждена, или улучшите карточку через проверку.",
            "metrics": [
                "stock_qty",
                "days_of_stock",
                "sales_velocity",
                "cost_price",
                "min_margin",
            ],
            "recheck_description": "После безопасного промо, изменения цены или улучшения карточки перепроверьте дни остатка и скорость продаж.",
            "steps": [
                (
                    "price_safety",
                    "Проверить безопасность цены и промо",
                    "Убедитесь, что снижение цены или промо не уводит товар в минус.",
                    None,
                    ["cost_price", "min_margin", "price"],
                    "Безопасность цены понятна.",
                    True,
                ),
                (
                    "promo_or_price",
                    "Открыть план промо или цены",
                    "Если маржа безопасна, спланируйте промо или пересмотр цены для ускорения продаж.",
                    "open_promo_planner",
                    ["cost_price", "min_margin", "sales_velocity"],
                    "Промо или цена запланированы безопасно.",
                    True,
                ),
                (
                    "checker_review",
                    "Запустить проверку карточки",
                    "Если цена небезопасна, проверьте контент карточки как альтернативный путь ускорения продаж.",
                    "run_checker",
                    ["card_quality_score", "sales_velocity"],
                    "Карточка проверена и улучшения зафиксированы.",
                    False,
                ),
                (
                    "recheck_stock",
                    "Перепроверить дни остатка и скорость продаж",
                    "После действия проверьте, меняются ли дни остатка и скорость продаж.",
                    "recheck",
                    ["days_of_stock", "sales_velocity"],
                    "Скорость продаж и дни остатка пересчитаны.",
                    False,
                ),
            ],
        },
        "low_stock_risk": {
            "title": "Карта решения: риск низкого остатка",
            "summary": "Проверьте запас, откройте план поставки, назначьте владельца и срок или снизьте промо/рекламу, затем перепроверьте дни остатка.",
            "metrics": ["stock_qty", "days_of_stock", "orders_7d", "sales_velocity"],
            "recheck_description": "После обновления поставки, остатков или спроса перепроверьте дни остатка.",
            "steps": [
                (
                    "supply_plan",
                    "Открыть поставки",
                    "Перейдите в план поставок и создайте пополнение, владельца или срок.",
                    "open_supply_planner",
                    ["stock_qty", "days_of_stock", "orders_7d"],
                    "План пополнения, владелец или срок зафиксированы.",
                    False,
                ),
                (
                    "demand_control",
                    "Снизить промо или рекламу",
                    "Если поставка не успевает, уменьшите стимулы спроса до восстановления остатка.",
                    "open_promo_planner",
                    ["days_of_stock", "promo_calendar"],
                    "Спрос временно ограничен или причина передана владельцу.",
                    False,
                ),
                (
                    "recheck_stock_days",
                    "Перепроверить дни остатка",
                    "Повторите проверку после обновления остатков, заказов или плана поставки.",
                    "recheck",
                    ["days_of_stock", "stock_qty"],
                    "Дни остатка пересчитаны.",
                    False,
                ),
            ],
        },
        "ads_spend_without_profit": {
            "title": "Карта решения: реклама без прибыли",
            "summary": "Проверьте доказательства, откройте рекламу, снизьте или поставьте кампанию на паузу либо улучшите карточку, затем перепроверьте прибыль после рекламы.",
            "metrics": ["ad_spend", "unit_profit_after_ads", "orders_7d", "cost_price"],
            "recheck_description": "После изменения рекламы, карточки или цены перепроверьте прибыль после рекламы.",
            "steps": [
                (
                    "ads_dashboard",
                    "Открыть рекламный кабинет",
                    "Найдите кампанию, которая тратит бюджет без прибыли.",
                    "open_ads_dashboard",
                    ["ad_spend", "unit_profit_after_ads"],
                    "Ставка, бюджет или статус кампании изменены.",
                    False,
                ),
                (
                    "checker_review",
                    "Запустить проверку карточки",
                    "Если реклама не конвертирует, проверьте карточку и исправьте контент.",
                    "run_checker",
                    ["card_quality_score", "conversion_rate"],
                    "Карточка проверена или улучшения созданы.",
                    False,
                ),
                (
                    "price_review",
                    "Проверить цену",
                    "Открывайте пересмотр цены только когда себестоимость и безопасная маржа посчитаны.",
                    "open_price_review",
                    ["price", "cost_price", "margin_pct"],
                    "Цена проверена с безопасной маржей.",
                    True,
                ),
                (
                    "recheck_ads_profit",
                    "Перепроверить прибыль после рекламы",
                    "Повторите проверку после новых данных по рекламе, заказам и себестоимости.",
                    "recheck",
                    ["unit_profit_after_ads", "ad_spend"],
                    "Прибыль после рекламы пересчитана.",
                    False,
                ),
            ],
        },
        "promo_not_profitable": {
            "title": "Карта решения: невыгодное промо",
            "summary": "Сначала проверьте себестоимость и безопасную цену, затем уменьшите или остановите промо и перепроверьте маржу.",
            "metrics": [
                "promo_spend",
                "unit_profit",
                "margin_pct",
                "cost_price",
                "price_after_discount",
            ],
            "recheck_description": "После изменения промо или цены перепроверьте маржу и прибыль на единицу.",
            "steps": [
                (
                    "promo_safety",
                    "Проверить экономику промо",
                    "Убедитесь, что скидка, цена и себестоимость позволяют считать безопасную маржу.",
                    None,
                    ["promo_spend", "cost_price", "margin_pct"],
                    "Экономика промо понятна.",
                    True,
                ),
                (
                    "promo_review",
                    "Открыть промо",
                    "Уменьшите или остановите промо только после проверки безопасной маржи.",
                    "open_promo_planner",
                    ["promo_spend", "price_after_discount", "min_margin"],
                    "Промо уменьшено, остановлено или передано владельцу.",
                    True,
                ),
                (
                    "price_review",
                    "Проверить цену",
                    "Если промо нельзя исправить отдельно, проверьте цену с учётом безопасной маржи.",
                    "open_price_review",
                    ["price_after_discount", "cost_price", "margin_pct"],
                    "Цена проверена с безопасной маржей.",
                    True,
                ),
                (
                    "cost_review",
                    "Исправить себестоимость",
                    "Если безопасная маржа не считается, сначала заполните себестоимость и комиссии.",
                    "upload_cost",
                    ["cost_price", "commission", "logistics_cost"],
                    "Себестоимость и комиссии заполнены.",
                    False,
                ),
                (
                    "recheck_promo",
                    "Перепроверить промо",
                    "Повторите проверку после изменения промо, цены или затрат.",
                    "recheck",
                    ["unit_profit", "margin_pct", "promo_spend"],
                    "Экономика промо пересчитана.",
                    False,
                ),
            ],
        },
        "price_below_safe_margin": {
            "title": "Карта решения: цена ниже безопасной маржи",
            "summary": "Проверьте, что себестоимость и комиссии заполнены, затем откройте пересмотр цены и перепроверьте безопасную маржу.",
            "metrics": [
                "price_after_discount",
                "margin_pct",
                "cost_price",
                "min_safe_price",
            ],
            "recheck_description": "После изменения цены или заполнения затрат перепроверьте безопасную маржу.",
            "steps": [
                (
                    "price_safety",
                    "Проверить безопасную цену",
                    "Убедитесь, что есть себестоимость, комиссии и минимальная безопасная цена.",
                    None,
                    ["cost_price", "commission", "min_safe_price"],
                    "Безопасная цена посчитана.",
                    True,
                ),
                (
                    "price_review",
                    "Открыть пересмотр цены",
                    "Поднимайте цену только после проверки полной экономики товара.",
                    "open_price_review",
                    ["price_after_discount", "margin_pct", "min_safe_price"],
                    "Цена проверена или запланирована безопасно.",
                    True,
                ),
                (
                    "cost_review",
                    "Исправить себестоимость",
                    "Если безопасная цена не считается, сначала заполните себестоимость и комиссии.",
                    "upload_cost",
                    ["cost_price", "commission", "logistics_cost"],
                    "Себестоимость и комиссии заполнены.",
                    False,
                ),
                (
                    "recheck_price",
                    "Перепроверить маржу",
                    "Повторите проверку после изменения цены или затрат.",
                    "recheck",
                    ["margin_pct", "min_safe_price"],
                    "Маржа пересчитана.",
                    False,
                ),
            ],
        },
        "dead_stock": {
            "title": "Карта решения: зависший остаток",
            "summary": "Проверьте безопасность распродажи, затем используйте промо/комплект только при подтверждённой марже или улучшите карточку и рекламу.",
            "metrics": [
                "stock_qty",
                "sales_30d",
                "days_of_stock",
                "cost_price",
                "min_margin",
            ],
            "recheck_description": "После безопасной распродажи, улучшения карточки или рекламы перепроверьте продажи и дни остатка.",
            "steps": [
                (
                    "price_safety",
                    "Проверить безопасность распродажи",
                    "Убедитесь, что распродажа или комплект не уводит товар ниже безопасной маржи.",
                    None,
                    ["cost_price", "min_margin", "price"],
                    "Безопасность распродажи понятна.",
                    True,
                ),
                (
                    "promo_or_bundle",
                    "Открыть промо или комплект",
                    "Если маржа безопасна, спланируйте распродажу или комплект для вывода остатка.",
                    "open_promo_planner",
                    ["cost_price", "min_margin", "stock_qty"],
                    "Промо, комплект или задача владельцу зафиксированы.",
                    True,
                ),
                (
                    "checker_review",
                    "Запустить проверку карточки",
                    "Если скидка небезопасна, сначала улучшите карточку и причины низкого спроса.",
                    "run_checker",
                    ["card_quality_score", "sales_30d"],
                    "Карточка проверена и улучшения зафиксированы.",
                    False,
                ),
                (
                    "ads_review",
                    "Проверить рекламу",
                    "Если карточка в порядке, проверьте кампании и трафик для остатка.",
                    "open_ads_dashboard",
                    ["ad_spend", "orders_7d"],
                    "Реклама проверена или скорректирована.",
                    False,
                ),
                (
                    "recheck_dead_stock",
                    "Перепроверить остаток",
                    "Повторите проверку после изменения промо, карточки, рекламы или комплекта.",
                    "recheck",
                    ["stock_qty", "days_of_stock", "sales_30d"],
                    "Остаток и продажи пересчитаны.",
                    False,
                ),
            ],
        },
        "fast_stock_depletion": {
            "title": "Карта решения: товар быстро заканчивается",
            "summary": "Откройте срочное пополнение, назначьте владельца и срок; если поставка не успевает, временно снизьте спрос.",
            "metrics": ["stock_qty", "days_of_stock", "orders_7d", "sales_velocity"],
            "recheck_description": "После срочного пополнения или ограничения спроса перепроверьте дни остатка.",
            "steps": [
                (
                    "urgent_supply_plan",
                    "Открыть срочную поставку",
                    "Перейдите в план поставок и создайте срочное пополнение с владельцем и сроком.",
                    "open_supply_planner",
                    ["stock_qty", "days_of_stock", "orders_7d"],
                    "Срочная поставка или владелец зафиксированы.",
                    False,
                ),
                (
                    "demand_control",
                    "Снизить промо или рекламу",
                    "Если поставка не успевает, временно уменьшите стимулы спроса до восстановления остатка.",
                    "open_promo_planner",
                    ["days_of_stock", "promo_calendar"],
                    "Спрос временно ограничен или причина передана владельцу.",
                    False,
                ),
                (
                    "recheck_stock_days",
                    "Перепроверить дни остатка",
                    "Повторите проверку после обновления остатков, заказов или плана поставки.",
                    "recheck",
                    ["days_of_stock", "stock_qty"],
                    "Дни остатка пересчитаны.",
                    False,
                ),
            ],
        },
        "card_quality_issue": {
            "title": "Карта решения: качество карточки",
            "summary": "Откройте проверку карточки, посмотрите diff, примените локальную правку или отправьте в WB с подтверждением и перепроверьте качество.",
            "metrics": [
                "card_quality_score",
                "photos",
                "description",
                "characteristics",
            ],
            "recheck_description": "После локальной правки или ответа WB запустите проверку карточки повторно.",
            "steps": [
                (
                    "checker",
                    "Открыть проверку карточки",
                    "Перейдите в карточку проверки и посмотрите найденные проблемы.",
                    "run_checker",
                    ["card_quality_score"],
                    "Проверка карточки открыта.",
                    False,
                ),
                (
                    "preview_diff",
                    "Посмотреть diff перед применением",
                    "Сравните текущую карточку и предлагаемую правку перед записью.",
                    None,
                    ["card_quality_score"],
                    "Diff просмотрен.",
                    False,
                ),
                (
                    "apply_or_local_fix",
                    "Сохранить локально или отправить в WB с подтверждением",
                    "Сначала сохраните локальную правку; запись в WB требует предпросмотра и подтверждения.",
                    "run_checker",
                    ["wb_content_diff"],
                    "Правка сохранена локально или отправлена в WB после подтверждения.",
                    False,
                ),
                (
                    "recheck_card",
                    "Перепроверить качество карточки",
                    "Повторите проверку после локальной правки или ответа WB.",
                    "recheck",
                    ["card_quality_score"],
                    "Качество карточки пересчитано.",
                    False,
                ),
            ],
        },
    }

    spec = maps.get(code)
    if spec is None:
        return _generic_action_center_solve_map(
            problem_code=code,
            allowed_actions=normalized_allowed,
            nm_id=nm_id,
            problem_instance_id=problem_instance_id,
            data_freshness=freshness,
            evidence_status=evidence_status,
        )
    steps = [
        _solve_map_step(
            step_id="evidence",
            order=1,
            title="Проверить доказательства",
            description="Откройте «Как посчитано?» и проверьте формулу, факты, источники и свежесть данных.",
            required_metrics=spec["metrics"],
            completion_signal="Доказательства и источники понятны.",
            data_freshness=freshness,
            allowed_actions=normalized_allowed,
            force_status=evidence_status,
            problem_instance_id=problem_instance_id,
        )
    ]
    for index, (
        step_id,
        title,
        description,
        action_code,
        metrics,
        completion_signal,
        price_required,
    ) in enumerate(spec["steps"], start=2):
        selected_action_code = action_code
        if (
            code in {"low_stock_risk", "fast_stock_depletion"}
            and step_id == "demand_control"
        ):
            if (
                "open_promo_planner" not in normalized_allowed
                and "open_ads_dashboard" in normalized_allowed
            ):
                selected_action_code = "open_ads_dashboard"
        if code in {"overstock_slow_moving", "dead_stock"} and step_id in {
            "promo_or_price",
            "promo_or_bundle",
        }:
            if (
                "open_promo_planner" not in normalized_allowed
                and "open_price_review" in normalized_allowed
            ):
                selected_action_code = "open_price_review"
        steps.append(
            _solve_map_step(
                step_id=step_id,
                order=index,
                title=title,
                description=description,
                action_code=selected_action_code,
                nm_id=nm_id,
                problem_instance_id=problem_instance_id,
                required_metrics=metrics,
                completion_signal=completion_signal,
                data_freshness=freshness,
                allowed_actions=normalized_allowed,
                price_safety=price_safety,
                price_safety_required=price_required,
            )
        )
    steps = _append_create_task_fallback_step(
        steps,
        allowed_actions=normalized_allowed,
        nm_id=nm_id,
        problem_instance_id=problem_instance_id,
    )
    return ActionCenterSolveMap(
        title=spec["title"],
        summary=spec["summary"],
        steps=steps,
        recheck_description=str(spec.get("recheck_description") or ""),
    )


def build_action_center_solve_map_from_template(
    *,
    template: dict[str, Any] | None,
    allowed_actions: list[str],
    nm_id: int | None = None,
    problem_instance_id: int | None = None,
    data_freshness: ActionCenterDataFreshness | dict[str, Any] | None = None,
    price_safety: dict[str, Any] | None = None,
) -> ActionCenterSolveMap | None:
    if not isinstance(template, dict):
        return None
    raw_steps = template.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return None
    normalized_allowed = normalize_action_center_allowed_actions(allowed_actions)
    freshness = (
        data_freshness
        if isinstance(data_freshness, ActionCenterDataFreshness)
        else ActionCenterDataFreshness.model_validate(data_freshness)
        if isinstance(data_freshness, dict)
        else None
    )
    steps: list[ActionCenterSolveMapStep] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        if not isinstance(raw_step, dict):
            continue
        raw_action = str(raw_step.get("action_code") or "").strip()
        normalized_action = normalize_action_center_allowed_actions([raw_action])
        action_code = normalized_action[0] if normalized_action else raw_action or None
        template_status = (
            str(raw_step.get("status") or "").strip().lower().replace("-", "_")
        )
        force_status: ActionCenterSolveStepStatus | None = None
        if action_code is None and template_status in {
            "ready",
            "available",
            "blocked",
            "waiting_for_data",
            "done",
        }:
            force_status = template_status  # type: ignore[assignment]
        step = _solve_map_step(
            step_id=str(raw_step.get("step_id") or f"step_{index}"),
            order=int(raw_step.get("order") or index),
            title=str(raw_step.get("title") or "Шаг решения"),
            description=str(raw_step.get("description") or ""),
            action_code=action_code,
            nm_id=nm_id,
            problem_instance_id=problem_instance_id,
            required_metrics=_string_list(raw_step.get("required_metrics")),
            completion_signal=str(raw_step.get("completion_signal") or "") or None,
            data_freshness=freshness,
            allowed_actions=normalized_allowed,
            price_safety=price_safety,
            price_safety_required=bool(raw_step.get("price_safety_required")),
            force_status=force_status,
        )
        if (
            step.blocking_reason is None
            and str(raw_step.get("blocking_reason") or "").strip()
        ):
            step = step.model_copy(
                update={
                    "blocking_reason": str(raw_step.get("blocking_reason")).strip(),
                    "status": "blocked",
                }
            )
        if step.target_href is None and str(raw_step.get("target_href") or "").strip():
            step = step.model_copy(
                update={"target_href": str(raw_step.get("target_href")).strip()}
            )
        steps.append(step)
    if not steps:
        return None
    steps = _append_create_task_fallback_step(
        steps,
        allowed_actions=normalized_allowed,
        nm_id=nm_id,
        problem_instance_id=problem_instance_id,
    )
    primary_action = normalize_action_center_allowed_actions(
        [str(template.get("primary_action_code") or "")]
    )
    return ActionCenterSolveMap(
        title=str(template.get("title") or "Карта решения"),
        summary=str(template.get("summary") or ""),
        steps=steps,
        primary_action_code=primary_action[0] if primary_action else None,
        secondary_action_codes=normalize_action_center_allowed_actions(
            _string_list(template.get("secondary_action_codes"))
        ),
        recheck_description=str(template.get("recheck_description") or ""),
    )


_DQ_BUSINESS_BLOCKED_CASH_CODES = {
    "stock_without_sales",
    "dead_stock",
    "overstock_slow_moving",
}
_DQ_ADS_SYSTEM_CHECK_CODES = {
    "ads_not_allocated_to_profitability",
    "ads_overallocated_to_profitability",
    "ad_spend_without_sku",
    "ad_spend_without_sales",
    "expense_ad_double_count_risk",
}


def _data_quality_issue_code(
    action_type: str | None,
    detector_code: str | None,
    payload: dict[str, Any],
    raw: dict[str, Any],
) -> str:
    for value in (
        payload.get("code"),
        payload.get("problem_code"),
        payload.get("detector_code"),
        raw.get("code"),
        raw.get("problem_code"),
        raw.get("detector_code"),
        detector_code,
        action_type,
    ):
        code = str(value or "").strip()
        if code and code.upper() != "DATA_FIX":
            return code
    return "data_quality_issue"


def _data_quality_contract_for_action(action: "PortalActionRead") -> dict[str, Any]:
    payload = action.payload if isinstance(action.payload, dict) else {}
    raw = action.raw if isinstance(action.raw, dict) else {}
    code = _data_quality_issue_code(
        action.action_type, action.detector_code, payload, raw
    )
    contract_payload = dict(payload)
    for raw_key, contract_key in (("nm_id", "nmId"), ("sku_id", "skuId")):
        value = raw.get(raw_key) or getattr(action, raw_key, None)
        if value is not None:
            contract_payload.setdefault(contract_key, value)
    severity = raw.get("severity") or action.severity
    contract = issue_fixability_contract(code, contract_payload, severity=severity)
    issue_nature = str(
        payload.get("issue_nature")
        or raw.get("issue_nature")
        or contract["issue_nature"]
    )
    fixability = str(
        payload.get("fixability") or raw.get("fixability") or contract["fixability"]
    )
    owner_type = str(
        payload.get("owner_type") or raw.get("owner_type") or contract["owner_type"]
    )
    can_user_fix = payload.get("can_user_fix_inside_platform")
    if can_user_fix is None:
        can_user_fix = raw.get("can_user_fix_inside_platform")
    if can_user_fix is None:
        can_user_fix = contract["can_user_fix_inside_platform"]
    manual_edit = payload.get("is_manual_edit_allowed")
    if manual_edit is None:
        manual_edit = raw.get("is_manual_edit_allowed")
    if manual_edit is None:
        manual_edit = contract["is_manual_edit_allowed"]
    impact_type, trust_state = _data_quality_impact_and_trust(
        code=code,
        issue_nature=issue_nature,
        payload=payload,
        action=action,
    )
    payload_trust = (
        payload.get("money_trust")
        if isinstance(payload.get("money_trust"), dict)
        else raw.get("money_trust")
    )
    if isinstance(payload_trust, dict):
        normalized_nature = issue_nature.strip().lower()
        impact_kind = str(payload_trust.get("impact_kind") or "").strip()
        impact_trust_state = str(
            payload_trust.get("impact_trust_state") or payload_trust.get("state") or ""
        ).strip()
        if normalized_nature == "data_blocker":
            impact_type = "data_blocker"
            trust_state = "blocked"
        elif normalized_nature == "business_signal" and impact_kind in {
            "blocked_cash",
            "opportunity",
        }:
            impact_type = impact_kind
        elif (
            normalized_nature == "finance_investigation"
            and impact_kind == "probable_loss"
        ):
            impact_type = "probable_loss"
        elif (
            normalized_nature
            in {"sync_waiting", "system_check", "finance_investigation"}
            and impact_kind == "informational"
        ):
            impact_type = "system_warning"
        if impact_trust_state:
            normalized_trust = impact_trust_state.lower()
            if normalized_nature == "business_signal" and normalized_trust in {
                "estimated",
                "opportunity",
            }:
                trust_state = "estimated"
            elif normalized_nature == "sync_waiting" and normalized_trust in {
                "provisional",
                "stale",
            }:
                trust_state = normalized_trust
            elif normalized_nature == "finance_investigation" and normalized_trust in {
                "provisional",
                "estimated",
            }:
                trust_state = "provisional"
    return {
        "code": code,
        "issue_nature": issue_nature,
        "fixability": fixability,
        "owner_type": owner_type,
        "can_user_fix_inside_platform": bool(can_user_fix),
        "is_manual_edit_allowed": bool(manual_edit),
        "primary_action_code": str(
            payload.get("primary_action_code")
            or raw.get("primary_action_code")
            or contract["primary_action_code"]
        ),
        "primary_action_label": str(
            payload.get("primary_action_label")
            or raw.get("primary_action_label")
            or contract["primary_action_label"]
        ),
        "target_href": str(
            payload.get("target_href")
            or raw.get("target_href")
            or contract["target_href"]
        ),
        "disabled_reason": str(
            payload.get("disabled_reason")
            or raw.get("disabled_reason")
            or contract["disabled_reason"]
            or ""
        ),
        "recheck_mode": str(
            payload.get("recheck_mode")
            or raw.get("recheck_mode")
            or contract["recheck_mode"]
        ),
        "seller_explanation": str(
            payload.get("seller_explanation")
            or raw.get("seller_explanation")
            or contract["seller_explanation"]
        ),
        "admin_explanation": str(
            payload.get("admin_explanation")
            or raw.get("admin_explanation")
            or contract["admin_explanation"]
        ),
        "impact_type": impact_type,
        "trust_state": trust_state,
    }


def _data_quality_impact_and_trust(
    *,
    code: str,
    issue_nature: str,
    payload: dict[str, Any],
    action: "PortalActionRead",
) -> tuple[str, str]:
    normalized_code = str(code or "").strip().lower()
    normalized_nature = str(issue_nature or "").strip().lower()
    if normalized_nature == "data_blocker":
        return "data_blocker", "blocked"
    if normalized_nature == "sync_waiting":
        source_status = ""
        freshness = payload.get("data_freshness")
        if isinstance(freshness, dict):
            source_status = str(
                freshness.get("source_status") or freshness.get("status") or ""
            )
        stale_codes = {
            "sales_without_stock",
            "stocks_task_not_ready",
            "stocks_task_failed",
            "latest_stocks_not_completed",
        }
        return (
            "system_warning",
            "stale"
            if normalized_code in stale_codes or source_status == "stale"
            else "provisional",
        )
    if normalized_nature == "system_check":
        return "system_warning", "provisional"
    if normalized_nature == "business_signal":
        impact = (
            "blocked_cash"
            if normalized_code in _DQ_BUSINESS_BLOCKED_CASH_CODES
            else "opportunity"
        )
        return impact, "estimated"
    if normalized_nature == "finance_investigation":
        has_amount = any(
            value not in (None, "", 0, 0.0)
            for value in (
                action.expected_impact_amount,
                action.expected_effect_amount,
                payload.get("affected_amount"),
                payload.get("affectedAmount"),
                payload.get("affected_revenue"),
                payload.get("affectedRevenue"),
            )
        )
        return "probable_loss" if has_amount else "system_warning", "provisional"
    if normalized_code in _DQ_ADS_SYSTEM_CHECK_CODES:
        return "system_warning", "provisional"
    return "system_warning", "provisional"


class PortalActionRead(PortalBaseModel):
    id: str
    external_id: str | None = None
    action_id: int | None = None
    source: str
    source_module: Literal[
        "finance",
        "data_quality",
        "costs",
        "checker",
        "stockops",
        "grouping",
        "grouping_beta",
        "reputation",
        "claims",
        "photo",
        "experiments",
        "problem_engine",
        "manual",
    ]
    source_id: str | None = None
    account_id: int | None = None
    action_type: str
    detector_code: str | None = None
    title: str
    priority: Literal["P0", "P1", "P2", "P3", "P4"] = "P3"
    severity: Literal["critical", "high", "medium", "low"] = "medium"
    status: Literal[
        "new",
        "acknowledged",
        "in_progress",
        "done",
        "postponed",
        "ignored",
        "blocked",
        "resolved",
        "dismissed",
        "reopened",
    ] = "new"
    reason: str = ""
    next_step: str = ""
    expected_effect_amount: float | None = None
    expected_impact_amount: float | None = None
    priority_score: float | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
    nm_id: int | None = None
    sku_id: int | None = None
    created_at: datetime | None = None
    assigned_to_user_id: int | None = None
    deadline_at: datetime | None = None
    review_status: Literal["new", "in_progress", "review", "closed", "dismissed"] = (
        "new"
    )
    last_comment: str | None = None
    last_status_changed_at: datetime | None = None
    last_actor_user_id: int | None = None
    status_reason: str | None = None
    is_overdue: bool = False
    due_in_hours: float | None = None
    sla_state: Literal["ok", "due_soon", "overdue", "no_deadline"] = "no_deadline"
    closed_at: datetime | None = None
    dismissed_at: datetime | None = None
    linked_entity: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)
    can_execute: bool = False
    can_update_status: bool = False
    can_update: bool = False
    can_update_reason: str | None = None
    source_references: list[dict[str, Any]] = Field(default_factory=list)
    recheck_rule: str | None = None
    impact_type: str | None = None
    trust_state: str | None = None
    source_sync_state: Literal[
        "source_updated", "shadow_only", "shadow_updated", "unknown"
    ] = "unknown"
    guided_fix: dict[str, Any] = Field(default_factory=dict)
    evidence_ledger: EvidenceLedger | None = None
    evidence_state: ActionCenterEvidenceState = "missing_evidence"
    data_freshness: ActionCenterDataFreshness | None = None
    solve_map: ActionCenterSolveMap | None = None
    money_trust: MoneyTrustInfo | None = None
    allowed_actions: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def fill_frontend_contract_defaults(self) -> "PortalActionRead":
        payload_refs = self.payload.get("source_references")
        raw_refs = self.raw.get("source_references")
        refs = (
            payload_refs
            if isinstance(payload_refs, list)
            else raw_refs
            if isinstance(raw_refs, list)
            else []
        )
        if not self.source_references and refs:
            self.source_references = [
                dict(ref) for ref in refs if isinstance(ref, dict)
            ]
        if not self.source_references:
            self.source_references = [
                {
                    "source_module": self.source_module,
                    "source": self.source,
                    "source_id": self.source_id,
                    "account_id": self.account_id,
                    "nm_id": self.nm_id,
                    "sku_id": self.sku_id,
                    "action_type": self.action_type,
                    "status": self.status,
                }
            ]
        if self.source_sync_state == "unknown":
            self.source_sync_state = str(
                self.payload.get("source_sync_state")
                or self.raw.get("source_sync_state")
                or "unknown"
            )  # type: ignore[assignment]
            if self.source_sync_state not in {
                "source_updated",
                "shadow_only",
                "shadow_updated",
                "unknown",
            }:
                self.source_sync_state = "unknown"
        if self.external_id is None:
            self.external_id = self.source_id
        if self.expected_impact_amount is None:
            self.expected_impact_amount = self.expected_effect_amount
        if self.detector_code is None:
            self.detector_code = str(
                self.payload.get("detector_code")
                or self.payload.get("problem_code")
                or self.raw.get("detector_code")
                or self.raw.get("problem_code")
                or self.action_type
            )
        if not self.allowed_actions:
            raw_allowed = (
                self.payload.get("allowed_actions")
                or self.raw.get("allowed_actions")
                or []
            )
            if isinstance(raw_allowed, list):
                self.allowed_actions = [
                    str(item) for item in raw_allowed if str(item).strip()
                ]
        self.allowed_actions = normalize_action_center_allowed_actions(
            self.allowed_actions
        )
        if self.solve_map is None:
            raw_solve_map = self.payload.get("solve_map") or self.raw.get("solve_map")
            if isinstance(raw_solve_map, dict):
                self.solve_map = ActionCenterSolveMap.model_validate(raw_solve_map)
        if self.money_trust is None:
            raw_money_trust = self.payload.get("money_trust") or self.raw.get(
                "money_trust"
            )
            if isinstance(raw_money_trust, dict):
                try:
                    self.money_trust = MoneyTrustInfo.model_validate(raw_money_trust)
                except Exception:
                    self.money_trust = None
        if self.source_module == "data_quality":
            dq_contract = _data_quality_contract_for_action(self)
            self.detector_code = dq_contract["code"]
            self.payload.setdefault("code", dq_contract["code"])
            for field in (
                "owner_type",
                "fixability",
                "issue_nature",
                "can_user_fix_inside_platform",
                "is_manual_edit_allowed",
                "primary_action_code",
                "primary_action_label",
                "target_href",
                "disabled_reason",
                "recheck_mode",
                "seller_explanation",
                "admin_explanation",
            ):
                self.payload[field] = dq_contract[field]
            self.impact_type = str(dq_contract["impact_type"])
            self.trust_state = str(dq_contract["trust_state"])
            if not str(self.next_step or "").strip():
                self.next_step = str(dq_contract["primary_action_label"])
            if not self.guided_fix:
                self.guided_fix = {
                    "label": str(dq_contract["primary_action_label"]),
                    "href": str(dq_contract["target_href"]),
                    "action_code": str(dq_contract["primary_action_code"]),
                }
            money_trust_is_blocker = self.money_trust is not None and str(
                self.money_trust.impact_kind
            ) in {"data_blocker", "blocked_revenue", "data_blocked"}
            if (
                self.money_trust is None
                or (
                    money_trust_is_blocker
                    and dq_contract["issue_nature"] != "data_blocker"
                )
                or (
                    not money_trust_is_blocker
                    and dq_contract["issue_nature"] == "data_blocker"
                )
            ):
                self.money_trust = classify_money_trust(
                    value=self.expected_impact_amount
                    if self.expected_impact_amount is not None
                    else self.expected_effect_amount,
                    value_type="money"
                    if (
                        self.expected_impact_amount is not None
                        or self.expected_effect_amount is not None
                    )
                    else "text",
                    confidence="blocked"
                    if dq_contract["issue_nature"] == "data_blocker"
                    else "provisional",
                    impact_type=str(dq_contract["impact_type"]),
                    trust_state="provisional"
                    if dq_contract["trust_state"] == "stale"
                    else str(dq_contract["trust_state"]),
                    source_module=self.source_module,
                    source_table=str(
                        self.payload.get("source_table")
                        or self.raw.get("source_table")
                        or self.source
                    ),
                    source_endpoint=str(
                        self.payload.get("source_endpoint")
                        or self.raw.get("source_endpoint")
                        or "GET /api/v1/portal/actions"
                    ),
                    action_type=str(dq_contract["code"]),
                    payload=self.payload,
                )
        if self.trust_state is None:
            self.trust_state = str(
                self.payload.get("trust_state")
                or self.raw.get("trust_state")
                or self.confidence
                or "provisional"
            )
        if self.can_update is False and self.can_update_status:
            self.can_update = True
        if self.can_update_reason is None and not self.can_update:
            self.can_update_reason = "read_only_recommendation"
        if self.evidence_ledger is None:
            source_endpoint = str(
                self.payload.get("source_endpoint")
                or self.raw.get("source_endpoint")
                or ""
            )
            trust_state = str(
                self.payload.get("trust_state") or self.raw.get("trust_state") or ""
            )
            synthetic_impact_type = self.impact_type or (
                "data_blocker" if self.source_module == "costs" else "opportunity"
            )
            action_money_trust = self.money_trust or classify_money_trust(
                value=self.expected_impact_amount
                if self.expected_impact_amount is not None
                else self.expected_effect_amount,
                value_type="money"
                if (
                    self.expected_impact_amount is not None
                    or self.expected_effect_amount is not None
                )
                else "text",
                confidence=self.evidence_ledger.confidence
                if self.evidence_ledger is not None
                else self.confidence,
                impact_type=synthetic_impact_type,
                trust_state=trust_state or str(self.trust_state or ""),
                source_module=self.source_module,
                source_table=str(
                    self.payload.get("source_table")
                    or self.raw.get("source_table")
                    or self.source
                ),
                source_endpoint=source_endpoint or "GET /api/v1/portal/actions",
                action_type=self.detector_code or self.action_type,
                payload=self.payload,
            )
            self.evidence_ledger = evidence_ledger(
                value=self.expected_impact_amount
                if self.expected_impact_amount is not None
                else self.expected_effect_amount,
                value_type="money"
                if (
                    self.expected_impact_amount is not None
                    or self.expected_effect_amount is not None
                )
                else "text",
                confidence=confidence_from_trust_state(trust_state or self.confidence),
                impact_type=synthetic_impact_type,
                formula_human=self.reason
                or self.next_step
                or "Сигнал создан Центром действий на основе данных модуля.",
                formula_code=f"portal_action.{self.source_module}.{self.action_type}",
                formula_id=self.id,
                label=self.title,
                unit="RUB"
                if (
                    self.expected_impact_amount is not None
                    or self.expected_effect_amount is not None
                )
                else None,
                source_table=str(
                    self.payload.get("source_table")
                    or self.raw.get("source_table")
                    or self.source
                ),
                source_endpoint=source_endpoint or "GET /api/v1/portal/actions",
                filters={
                    "account_id": self.account_id,
                    "source_module": self.source_module,
                    "source_id": self.source_id,
                    "nm_id": self.nm_id,
                    "sku_id": self.sku_id,
                },
                row_count=1,
                sample_rows=[
                    {
                        "id": self.id,
                        "source": self.source,
                        "source_module": self.source_module,
                        "source_id": self.source_id,
                        "nm_id": self.nm_id,
                        "sku_id": self.sku_id,
                        **self.linked_entity,
                    }
                ],
                source_references=self.source_references,
                missing_data=[
                    str(item)
                    for item in self.payload.get("missing_data", [])
                    if str(item).strip()
                ]
                if isinstance(self.payload.get("missing_data"), list)
                else [],
                next_fix_action={
                    "label": str(
                        self.guided_fix.get("label")
                        or self.next_step
                        or "Открыть действие"
                    ),
                    "screen_path": str(self.guided_fix.get("href") or ""),
                    "source_endpoint": source_endpoint or "GET /api/v1/portal/actions",
                    "action_type": self.action_type,
                },
                recheck_rule="Выполните действие или обновите Центр действий после изменения данных источника.",
                money_trust=action_money_trust,
                is_synthetic=True,
            )
        if self.data_freshness is None:
            self.data_freshness = _action_center_data_freshness(
                payload={
                    **self.payload,
                    "source": self.payload.get("source") or self.source,
                    "source_module": self.payload.get("source_module")
                    or self.source_module,
                    "action_type": self.payload.get("action_type") or self.action_type,
                    "detector_code": self.payload.get("detector_code")
                    or self.detector_code,
                },
                raw={
                    **self.raw,
                    "source": self.raw.get("source") or self.source,
                    "source_module": self.raw.get("source_module")
                    or self.source_module,
                    "action_type": self.raw.get("action_type") or self.action_type,
                    "detector_code": self.raw.get("detector_code")
                    or self.detector_code,
                },
                evidence_ledger_value=self.evidence_ledger,
                source_references=self.source_references,
                problem_code=self.detector_code or self.action_type,
            )
        if self.solve_map is None and self.source_module in {
            "problem_engine",
            "checker",
        }:
            price_safety = (
                self.payload.get("price_safety")
                if isinstance(self.payload.get("price_safety"), dict)
                else self.raw.get("price_safety")
            )
            problem_instance_id = _positive_int_from(
                self.payload.get("problem_instance_id"),
                self.raw.get("problem_instance_id"),
            )
            if self.source_module == "problem_engine":
                problem_instance_id = _positive_int_from(
                    self.payload.get("problem_instance_id"),
                    self.raw.get("problem_instance_id"),
                    self.source_id,
                )
            solve_problem_code = self.detector_code or self.action_type
            if self.source_module == "checker" and (
                self.payload.get("checker_problem_bridge")
                or self.payload.get("content_quality_signal")
                or str(self.action_type or "").upper() == "CARD_QUALITY_FIX"
            ):
                solve_problem_code = "card_quality_issue"
            self.solve_map = build_action_center_solve_map(
                problem_code=solve_problem_code,
                allowed_actions=self.allowed_actions,
                nm_id=self.nm_id,
                problem_instance_id=problem_instance_id,
                data_freshness=self.data_freshness,
                price_safety=price_safety if isinstance(price_safety, dict) else None,
            )
        if not self.source_references and self.evidence_ledger.source_references:
            self.source_references = [
                ref.model_dump(mode="json")
                for ref in self.evidence_ledger.source_references
            ]
        if self.recheck_rule is None:
            self.recheck_rule = self.evidence_ledger.recheck_rule
        if self.impact_type is None:
            self.impact_type = self.evidence_ledger.impact_type
        if self.money_trust is None:
            self.money_trust = self.evidence_ledger.money_trust or classify_money_trust(
                value=self.expected_impact_amount
                if self.expected_impact_amount is not None
                else self.expected_effect_amount,
                value_type="money"
                if (
                    self.expected_impact_amount is not None
                    or self.expected_effect_amount is not None
                )
                else "text",
                confidence=self.evidence_ledger.confidence
                if self.evidence_ledger is not None
                else self.confidence,
                impact_type=self.impact_type,
                trust_state=str(
                    self.trust_state
                    or self.payload.get("trust_state")
                    or self.raw.get("trust_state")
                    or ""
                ),
                source_module=self.source_module,
                source_table=str(
                    self.payload.get("source_table")
                    or self.raw.get("source_table")
                    or self.source
                ),
                source_endpoint=str(
                    self.payload.get("source_endpoint")
                    or self.raw.get("source_endpoint")
                    or "GET /api/v1/portal/actions"
                ),
                action_type=self.action_type,
                payload=self.payload,
            )
        action_code = str(self.action_type or self.detector_code or "").strip().lower()
        if action_code in {"low_stock_risk", "fast_stock_depletion"} and (
            self.impact_type == "confirmed_loss"
            or self.money_trust.impact_kind == "confirmed_loss"
        ):
            self.impact_type = "lost_sales_risk"
            if self.trust_state == "confirmed":
                self.trust_state = "provisional"
            self.money_trust = self.money_trust.model_copy(
                update={
                    "state": "provisional"
                    if self.money_trust.state == "confirmed"
                    else self.money_trust.state,
                    "impact_kind": "lost_sales_risk",
                    "display_label": "Риск потери продаж",
                    "amount_label": "Риск потери продаж",
                    "show_as_confirmed_money": False,
                    "impact_trust_state": "provisional",
                    "saved_money_claimed": False,
                }
            )
        if action_code in {"overstock_slow_moving", "dead_stock"} and (
            self.impact_type in {None, "", "confirmed_loss", "opportunity"}
            or self.money_trust.impact_kind in {"confirmed_loss", "opportunity"}
        ):
            self.impact_type = "blocked_cash"
            if self.trust_state == "confirmed":
                self.trust_state = "estimated"
            self.money_trust = self.money_trust.model_copy(
                update={
                    "state": "estimated"
                    if self.money_trust.state == "confirmed"
                    else self.money_trust.state,
                    "impact_kind": "blocked_cash",
                    "display_label": "Замороженные деньги",
                    "amount_label": "Замороженные деньги",
                    "show_as_confirmed_money": False,
                    "impact_trust_state": "estimated",
                    "saved_money_claimed": False,
                }
            )
        if self.data_freshness is not None and (
            self.data_freshness.source_status != "fresh"
            or bool(self.data_freshness.blocking_sources)
        ):
            blocked = self.data_freshness.source_status in {"missing", "not_configured"}
            next_trust = "blocked" if blocked else "provisional"
            impact_kind = self.money_trust.impact_kind
            display_label = self.money_trust.display_label
            amount_label = self.money_trust.amount_label
            if impact_kind == "confirmed_loss":
                impact_kind = "probable_risk"
                display_label = "Данные предварительные"
                amount_label = "Вероятный риск"
                if self.impact_type == "confirmed_loss":
                    self.impact_type = "probable_risk"
            if self.trust_state == "confirmed":
                self.trust_state = next_trust
            self.money_trust = self.money_trust.model_copy(
                update={
                    "state": next_trust
                    if self.money_trust.state == "confirmed" or blocked
                    else self.money_trust.state,
                    "impact_kind": impact_kind,
                    "display_label": display_label,
                    "amount_label": amount_label,
                    "show_as_confirmed_money": False,
                    "evidence_trust_state": "blocked" if blocked else "provisional",
                    "impact_trust_state": next_trust,
                    "saved_money_claimed": False,
                    "reason": self.money_trust.reason
                    or "Источник требует синхронизации, поэтому денежное влияние предварительное.",
                }
            )
        self.evidence_ledger.money_trust = self.money_trust
        self.evidence_state = self._derive_evidence_state()
        self.payload["money_trust"] = self.money_trust.model_dump(mode="json")
        self.payload["data_freshness"] = (
            self.data_freshness.model_dump(mode="json") if self.data_freshness else None
        )
        self.payload["solve_map"] = (
            self.solve_map.model_dump(mode="json") if self.solve_map else None
        )
        self.payload.setdefault(
            "evidence_ledger", self.evidence_ledger.model_dump(mode="json")
        )
        self.payload["evidence_state"] = self.evidence_state
        self.payload.setdefault("source_references", self.source_references)
        self.payload.setdefault("detector_code", self.detector_code)
        self.payload["allowed_actions"] = self.allowed_actions
        self.payload.setdefault("recheck_rule", self.recheck_rule)
        self.payload["impact_type"] = self.impact_type
        self.payload["trust_state"] = self.trust_state
        self.payload.setdefault("source_sync_state", self.source_sync_state)
        if self.last_status_changed_at is None:
            changed_at = (
                self.payload.get("last_status_changed_at")
                or self.payload.get("last_changed_at")
                or self.raw.get("last_status_changed_at")
                or self.raw.get("last_changed_at")
            )
            if isinstance(changed_at, datetime):
                self.last_status_changed_at = changed_at
            elif isinstance(changed_at, str) and changed_at.strip():
                try:
                    self.last_status_changed_at = datetime.fromisoformat(
                        changed_at.replace("Z", "+00:00")
                    )
                except ValueError:
                    self.last_status_changed_at = None
        if self.last_actor_user_id is None:
            actor = (
                self.payload.get("last_actor_user_id")
                or self.payload.get("last_changed_by_user_id")
                or self.raw.get("last_actor_user_id")
                or self.raw.get("last_changed_by_user_id")
            )
            self.last_actor_user_id = (
                int(actor)
                if isinstance(actor, int)
                or (isinstance(actor, str) and actor.isdigit())
                else None
            )
        if self.status_reason is None:
            reason = (
                self.payload.get("status_reason")
                or self.payload.get("dismiss_reason")
                or self.raw.get("status_reason")
            )
            self.status_reason = str(reason) if reason is not None else None
        if self.deadline_at is not None:
            now = datetime.now(timezone.utc)
            deadline = self.deadline_at
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            due_hours = (deadline - now).total_seconds() / 3600
            closed_statuses = {
                "done",
                "resolved",
                "closed",
                "ignored",
                "dismissed",
                "rejected",
            }
            self.due_in_hours = round(due_hours, 2)
            self.is_overdue = due_hours < 0 and self.status not in closed_statuses
            if self.is_overdue:
                self.sla_state = "overdue"
            elif self.status in closed_statuses:
                self.sla_state = "ok"
            elif due_hours <= 24:
                self.sla_state = "due_soon"
            else:
                self.sla_state = "ok"
        else:
            self.due_in_hours = None
            self.is_overdue = False
            self.sla_state = "no_deadline"
        self.payload.setdefault("is_overdue", self.is_overdue)
        self.payload.setdefault("due_in_hours", self.due_in_hours)
        self.payload.setdefault("sla_state", self.sla_state)
        return self

    def _derive_evidence_state(self) -> ActionCenterEvidenceState:
        freshness_blocked = bool(
            self.data_freshness is not None
            and (
                self.data_freshness.source_status != "fresh"
                or bool(self.data_freshness.blocking_sources)
            )
        )
        explicit_state = str(
            self.payload.get("evidence_state") or self.raw.get("evidence_state") or ""
        ).strip()
        if explicit_state in {
            "full_evidence",
            "partial_evidence",
            "missing_evidence",
            "read_only_signal",
        }:
            if freshness_blocked and explicit_state == "full_evidence":
                if self.data_freshness and self.data_freshness.source_status in {
                    "missing",
                    "not_configured",
                }:
                    return "missing_evidence"
                return "partial_evidence"
            return explicit_state  # type: ignore[return-value]
        if (
            freshness_blocked
            and self.data_freshness
            and self.data_freshness.source_status in {"missing", "not_configured"}
        ):
            return "missing_evidence"
        if self.evidence_ledger is None:
            return "read_only_signal" if not self.can_update else "missing_evidence"
        formula_code = str(self.evidence_ledger.formula_code or "")
        formula_human = str(self.evidence_ledger.formula_human or "")
        synthetic = bool(self.evidence_ledger.is_synthetic) or formula_code.startswith("portal_action.")
        has_formula = bool(
            formula_human.strip()
            or formula_code.strip()
            or self.evidence_ledger.formula_id
        )
        has_facts = bool(self.evidence_ledger.input_facts)
        has_sources = bool(self.evidence_ledger.source_references)
        has_missing = bool(self.evidence_ledger.missing_data)
        has_warnings = bool(self.evidence_ledger.calculation_warnings)
        if not self.can_update and synthetic:
            return "read_only_signal"
        if not has_formula and not has_facts and not has_sources:
            return "read_only_signal" if not self.can_update else "missing_evidence"
        if synthetic or has_missing or has_warnings or not has_facts or not has_sources:
            return "partial_evidence"
        if freshness_blocked:
            return "partial_evidence"
        return "full_evidence"


class PortalActionsPage(PortalBaseModel):
    total: int
    limit: int
    offset: int
    items: list[PortalActionRead]
    unavailable_sources: list[str] = Field(default_factory=list)


ActionCenterCapabilityDetectStatus = Literal[
    "ready",
    "partial",
    "manual",
    "planned",
    "not_supported",
]
ActionCenterCapabilityExecuteStatus = Literal[
    "ready",
    "preview_only",
    "manual",
    "missing_wb_write",
    "planned",
    "not_supported",
]


class PortalActionCenterCapabilityRead(PortalBaseModel):
    key: str
    domain: str
    title: str
    description: str
    detect_status: ActionCenterCapabilityDetectStatus = "planned"
    execute_status: ActionCenterCapabilityExecuteStatus = "planned"
    executor_key: str | None = None
    safe_write: bool = False
    confirm_required: bool = True
    required_token_categories: list[str] = Field(default_factory=list)
    problem_codes: list[str] = Field(default_factory=list)
    action_codes: list[str] = Field(default_factory=list)
    task_examples: list[str] = Field(default_factory=list)
    ui_route: str | None = None
    jvo_reference_urls: list[str] = Field(default_factory=list)
    wb_connector_ids: list[str] = Field(default_factory=list)
    wb_api_endpoints: list[str] = Field(default_factory=list)
    wb_reference_urls: list[str] = Field(default_factory=list)
    wb_tracking_status: str = "partial"
    token_categories: list[str] = Field(default_factory=list)
    rate_limit_notes: list[str] = Field(default_factory=list)
    unknown_connector_ids: list[str] = Field(default_factory=list)
    implementation_gaps: list[str] = Field(default_factory=list)
    safety_requirements: list[str] = Field(default_factory=list)
    current_support_note: str | None = None


class PortalActionCenterDomainRead(PortalBaseModel):
    key: str
    title: str
    description: str
    priority: int = 0
    icon: str | None = None
    first_step: str | None = None
    capabilities: list[PortalActionCenterCapabilityRead] = Field(default_factory=list)
    jvo_reference_urls: list[str] = Field(default_factory=list)


class PortalActionCenterCapabilitiesRead(PortalBaseModel):
    protocol: Literal["action-center-capabilities-v1"] = (
        "action-center-capabilities-v1"
    )
    domains: list[PortalActionCenterDomainRead] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    source_notes: list[str] = Field(default_factory=list)


class PortalAssignableUserRead(PortalBaseModel):
    id: int
    email: str
    full_name: str
    display_name: str
    role: str
    is_active: bool
    is_superuser: bool = False


ActionCenterStatus = Literal[
    "new",
    "acknowledged",
    "in_progress",
    "done",
    "postponed",
    "ignored",
    "blocked",
    "resolved",
    "dismissed",
    "reopened",
]

ActionCenterEventType = Literal[
    "status_change",
    "status_changed",
    "dismiss",
    "dismissed",
    "assign",
    "assigned",
    "comment",
    "comment_added",
    "deadline_changed",
    "postponed",
    "blocked",
    "recheck",
    "recheck_requested",
    "recheck_completed",
    "result_measured",
    "reopened",
]


class PortalActionUpdateRequest(PortalBaseModel):
    status: ActionCenterStatus
    comment: str | None = None
    status_reason: str | None = None
    assigned_to_user_id: int | None = None
    deadline_at: datetime | None = None
    review_status: (
        Literal["new", "in_progress", "review", "closed", "dismissed"] | None
    ) = None
    event_type: ActionCenterEventType | None = None


class PortalActionSourceUpdateRequest(PortalBaseModel):
    account_id: int
    source_module: str = "result_tracking"
    source_id: str
    status: ActionCenterStatus
    comment: str | None = None
    status_reason: str | None = None
    assigned_to_user_id: int | None = None
    deadline_at: datetime | None = None
    review_status: (
        Literal["new", "in_progress", "review", "closed", "dismissed"] | None
    ) = None
    event_type: ActionCenterEventType | None = None


class PortalManualActionProduct(PortalBaseModel):
    nm_id: int
    sku_id: int | None = None
    title: str | None = Field(default=None, max_length=255)
    vendor_code: str | None = Field(default=None, max_length=255)
    photo_url: str | None = Field(default=None, max_length=1024)


class PortalManualActionCreateRequest(PortalBaseModel):
    account_id: int
    title: str = Field(min_length=3, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    task_kind: str = Field(default="manual_review", max_length=64)
    priority: Literal["P0", "P1", "P2", "P3", "P4"] = "P2"
    assigned_to_user_id: int
    deadline_at: datetime
    products: list[PortalManualActionProduct] = Field(min_length=1, max_length=100)


class PortalManualTaskItemUpdateRequest(PortalBaseModel):
    account_id: int | None = None
    status: Literal["pending", "done", "skipped"]
    comment: str | None = Field(default=None, max_length=1000)


class PortalDataBlock(PortalBaseModel):
    status: PortalStatus = "empty"
    data: dict[str, Any] | list[Any] | None = Field(default_factory=dict)
    message: str | None = None
    evidence_ledger: EvidenceLedger | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "PortalDataBlock":
        if self.evidence_ledger is None:
            self.evidence_ledger = evidence_ledger(
                value=self.status,
                value_type="status",
                confidence="blocked"
                if self.status in {"critical", "failed"}
                else "provisional",
                impact_type="system_warning"
                if self.status not in {"critical", "failed"}
                else "data_blocker",
                formula_human=self.message
                or "Статус раздела обзора товара вернул ответственный модуль.",
                formula_code="portal.product_360.section",
                formula_id=f"portal_section:{self.status}",
                label="Раздел обзора товара",
                source_endpoint="GET /api/v1/portal/products/{nm_id}",
                row_count=1 if self.data else 0,
                sample_rows=[{"status": self.status, "message": self.message}],
                recheck_rule="Обновите обзор товара после синхронизации или анализа исходного модуля.",
                is_synthetic=True,
            )
        return self


class PortalProductRead(PortalBaseModel):
    nm_id: int
    sku_id: int | None = None
    title: str | None = None
    name: str | None = None
    vendor_code: str | None = None
    article: str | None = None
    photo: str | None = None
    photo_url: str | None = None
    brand: str | None = None
    subject_name: str | None = None
    revenue: float | None = None
    for_pay: float | None = None
    estimated_profit: float | None = None
    profit: float | None = None
    margin: float | None = None
    ads_spend: float | None = None
    stock_qty: float | None = None
    cost_state: str = "unknown"
    stock_state: str = "unknown"
    card_quality_state: str = "not_configured"
    card_quality_score: int | None = None
    card_quality_issue_count: int = 0
    card_quality_photo_count: int | None = None
    card_quality_analyzed_at: datetime | None = None
    reputation_state: str = "not_configured"
    cases_state: str = "not_configured"
    stock_summary: dict[str, Any] | None = None
    data_trust_state: str | None = None
    open_actions_count: int = 0
    top_action: "PortalActionRead | None" = None
    status: str = ""
    trust_state: str = ""
    priority_score: float | None = None
    money: dict[str, Any] | None = None
    stock: dict[str, Any] | None = None
    ads: dict[str, Any] | None = None
    next_action: PortalActionRead | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "PortalProductRead":
        trust = classify_money_trust(
            value=self.profit if self.profit is not None else self.revenue,
            value_type="money",
            confidence=confidence_from_trust_state(
                self.trust_state or self.data_trust_state
            ),
            impact_type="opportunity" if (self.profit or 0) >= 0 else "probable_loss",
            source_module="portal",
            source_table="mart_sku_daily",
            source_endpoint="GET /api/v1/portal/products",
            action_type=self.status or self.stock_state or self.card_quality_state,
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = evidence_ledger(
                value=self.profit if self.profit is not None else self.revenue,
                value_type="money",
                confidence=confidence_from_trust_state(
                    self.trust_state or self.data_trust_state
                ),
                impact_type="opportunity"
                if (self.profit or 0) >= 0
                else "probable_loss",
                formula_human="Строка товара объединяет деньги, остатки, качество карточки и сигналы действий для этого nmID.",
                formula_code="portal.products.row",
                formula_id=f"portal_product:{self.nm_id}",
                label=self.title or self.name or str(self.nm_id),
                unit="RUB",
                source_table="mart_sku_daily",
                source_endpoint="GET /api/v1/portal/products",
                filters={"nm_id": self.nm_id, "sku_id": self.sku_id},
                row_count=1,
                sample_rows=[
                    {
                        "nm_id": self.nm_id,
                        "sku_id": self.sku_id,
                        "revenue": self.revenue,
                        "profit": self.profit,
                        "card_quality_state": self.card_quality_state,
                        "open_actions_count": self.open_actions_count,
                    }
                ],
                recheck_rule="Обновите список товаров после синхронизации денег, проверки карточек или изменения действий.",
                money_trust=trust,
                is_synthetic=True,
            )
        if self.money_trust is None:
            self.money_trust = self.evidence_ledger.money_trust or trust
        self.evidence_ledger.money_trust = self.money_trust
        return self


class PortalProductsPage(PortalBaseModel):
    total: int
    limit: int
    offset: int
    items: list[PortalProductRead]
    summary: dict[str, Any] = Field(default_factory=dict)
    unavailable_sources: list[str] = Field(default_factory=list)


class PortalProduct360Read(PortalBaseModel):
    nm_id: int
    product_identity: dict[str, Any] = Field(default_factory=dict)
    health_summary: dict[str, Any] = Field(default_factory=dict)
    problem_instances: list[dict[str, Any]] = Field(default_factory=list)
    grouped_problems: dict[str, Any] = Field(default_factory=dict)
    result_preview: dict[str, Any] = Field(default_factory=dict)
    checker_summary: dict[str, Any] = Field(default_factory=dict)
    data_blockers: dict[str, Any] = Field(default_factory=dict)
    overview_diagnosis: PortalDataBlock = Field(default_factory=PortalDataBlock)
    identity: PortalDataBlock = Field(default_factory=PortalDataBlock)
    money: PortalDataBlock = Field(default_factory=PortalDataBlock)
    costs: PortalDataBlock = Field(default_factory=PortalDataBlock)
    ads: PortalDataBlock = Field(default_factory=PortalDataBlock)
    stock: PortalDataBlock = Field(default_factory=PortalDataBlock)
    pricing: PortalDataBlock = Field(default_factory=PortalDataBlock)
    data_quality: PortalDataBlock = Field(default_factory=PortalDataBlock)
    quality: PortalDataBlock = Field(default_factory=PortalDataBlock)
    card_quality: PortalDataBlock = Field(default_factory=PortalDataBlock)
    reputation: PortalDataBlock = Field(default_factory=PortalDataBlock)
    claims: PortalDataBlock = Field(default_factory=PortalDataBlock)
    photo_studio: PortalDataBlock = Field(default_factory=PortalDataBlock)
    experiments: PortalDataBlock = Field(default_factory=PortalDataBlock)
    grouping: PortalDataBlock = Field(default_factory=PortalDataBlock)
    grouping_beta: PortalDataBlock = Field(default_factory=PortalDataBlock)
    business_issues: PortalDataBlock = Field(default_factory=PortalDataBlock)
    actions: list[PortalActionRead] = Field(default_factory=list)
    history: PortalDataBlock = Field(default_factory=PortalDataBlock)
    result_history: PortalDataBlock = Field(default_factory=PortalDataBlock)
    next_best_action: PortalActionRead | None = None
    module_health: PortalModuleHealth | None = None
    stock_summary: dict[str, Any] = Field(default_factory=dict)
    ads_summary: dict[str, Any] = Field(default_factory=dict)
    data_issues: list[dict[str, Any]] = Field(default_factory=list)
    finance: dict[str, Any] = Field(default_factory=dict)
    unavailable_sources: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    evidence_ledger: dict[str, EvidenceLedger] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "PortalProduct360Read":
        if not self.evidence_ledger:
            self.evidence_ledger = {
                "product_360": evidence_ledger(
                    value=self.nm_id,
                    value_type="count",
                    confidence="provisional",
                    impact_type="system_warning",
                    formula_human="Обзор товара объединяет разделы модулей по одному nmID.",
                    formula_code="portal.product_360",
                    formula_id=f"portal_product_360:{self.nm_id}",
                    label=f"Обзор товара {self.nm_id}",
                    source_endpoint="GET /api/v1/portal/products/{nm_id}",
                    filters={"nm_id": self.nm_id},
                    row_count=1,
                    sample_rows=[
                        {
                            "nm_id": self.nm_id,
                            "unavailable_sources": ",".join(self.unavailable_sources),
                        }
                    ],
                    missing_data=self.unavailable_sources,
                    recheck_rule="Обновите страницу после завершения синхронизации или анализа исходных модулей.",
                    is_synthetic=True,
                )
            }
        return self


class PortalProductQualityRead(PortalBaseModel):
    status: PortalStatus = "not_configured"
    module: str = "checker"
    store_id: int | None = None
    card_id: int | None = None
    nm_id: int
    score: int | None = None
    severity: str | None = None
    source: str = "checker"
    updated_at: datetime | None = None
    action: str | None = None
    score_breakdown: dict[str, Any] = Field(default_factory=dict)
    critical_issue_count: int = 0
    warning_issue_count: int = 0
    issues_by_category: dict[str, int] = Field(default_factory=dict)
    title_issues: list[dict[str, Any]] = Field(default_factory=list)
    description_issues: list[dict[str, Any]] = Field(default_factory=list)
    characteristics_issues: list[dict[str, Any]] = Field(default_factory=list)
    photo_video_issues: list[dict[str, Any]] = Field(default_factory=list)
    issues: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[Any] = Field(default_factory=list)
    message: str | None = None
    mode: str | None = None
    category_scores: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    analyzed_at: datetime | None = None
    source_revision: str | None = None
    analysis_available: bool | None = None
    analyze_endpoint: str | None = None
    next_recommended_action: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_quality_contract_defaults(self) -> "PortalProductQualityRead":
        if self.status == "not_configured":
            if self.message is None:
                self.message = "Checker не подключён"
            if self.action is None:
                self.action = "connect_checker_in_settings"
        if self.severity is None:
            if self.status != "ok":
                self.severity = self.status
            elif self.critical_issue_count > 0 or any(
                isinstance(issue, dict)
                and issue.get("severity") in {"critical", "high"}
                for issue in self.issues
            ):
                self.severity = "critical"
            elif (
                self.issues
                or self.warning_issue_count > 0
                or (self.score is not None and self.score < 90)
            ):
                self.severity = "warning"
            else:
                self.severity = "good"
        return self


class PortalStockOpsRunRequest(PortalBaseModel):
    run_type: Literal["return_excess", "ship_from_hand", "store_balance"]
    account_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PortalStockOpsRunRead(PortalBaseModel):
    status: Literal[
        "not_configured",
        "unavailable",
        "disabled",
        "not_started",
        "queued",
        "running",
        "completed",
        "failed",
    ]
    run_type: str | None = None
    run_id: int | str | None = None
    account_id: int | None = None
    summary: dict[str, Any] | None = None
    export_url: str | None = None
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PortalStockOpsRunsPage(PortalBaseModel):
    status: Literal["not_configured", "unavailable", "disabled", "ok"]
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[PortalStockOpsRunRead] = Field(default_factory=list)
    message: str | None = None


class PortalStockOpsInsightsRead(PortalBaseModel):
    status: PortalStatus = "empty"
    account_id: int | None = None
    nm_id: int | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    latest_runs: list[PortalStockOpsRunRead] = Field(default_factory=list)
    regional_candidates: list[dict[str, Any]] = Field(default_factory=list)
    action_candidates: list[dict[str, Any]] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    message: str | None = None


class PortalGroupingPreviewRequest(PortalBaseModel):
    account_id: int | None = None
    nm_id: int | None = None
    preset_key: str | None = None
    recommendation_scenario_id: int | None = None
    custom_config: dict[str, Any] = Field(default_factory=dict)


class PortalGroupingPreviewRead(PortalBaseModel):
    status: PortalStatus = "not_configured"
    beta_label: str = "Grouping Beta"
    beta_notice: str = "Beta / recommendation only. WB merge/apply is disabled."
    auto_merge_enabled: bool = False
    account_id: int | None = None
    nm_id: int | None = None
    summary: dict[str, Any] = Field(default_factory=dict)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class PortalGroupingCandidateStatusUpdate(PortalBaseModel):
    status: Literal["new", "reviewing", "accepted", "rejected", "postponed", "expired"]
    reason: str | None = None


class PortalProductGroupingRead(PortalBaseModel):
    status: PortalStatus = "not_configured"
    beta_label: str = "Grouping Beta"
    beta_notice: str = "Beta / recommendation only. WB merge/apply is disabled."
    auto_merge_enabled: bool = False
    account_id: int | None = None
    nm_id: int
    source: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    recommendation_count: int = 0
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


ExperimentType = Literal["before_after", "controlled_split", "observational"]
ExperimentInterventionType = Literal[
    "photo",
    "title",
    "description",
    "price",
    "ads",
    "grouping",
    "stock",
    "reputation",
    "manual_other",
]
ExperimentStatus = Literal[
    "draft",
    "planned",
    "baseline_collecting",
    "ready_for_change",
    "change_recorded",
    "post_collecting",
    "ready_for_evaluation",
    "evaluated",
    "inconclusive",
    "cancelled",
    "failed",
]
ExperimentOutcome = Literal[
    "improved", "worse", "neutral", "inconclusive", "not_enough_data", "invalidated"
]


class PortalExperimentsStatusRead(PortalBaseModel):
    status: Literal["ok", "disabled"] = "ok"
    enabled: bool = True
    supported_experiment_types: list[str] = Field(
        default_factory=lambda: ["before_after", "observational"]
    )
    unsupported_experiment_types: list[str] = Field(
        default_factory=lambda: ["controlled_split"]
    )
    supported_intervention_types: list[str] = Field(default_factory=list)
    disclaimer: str = "Сравнение до/после показывает наблюдаемую связь, но не доказывает причинность; causality not proven."


class PortalExperimentSettingsRead(PortalBaseModel):
    account_id: int
    default_baseline_days: int = 7
    default_post_days: int = 7
    default_evaluation_delay_days: int = 0
    minimum_orders: int = 3
    minimum_revenue: float = 0.0
    minimum_views: int | None = None
    maximum_stockout_days: int = 1
    allow_overlapping_experiments: bool = False
    weekday_matched_baseline: bool = False


class PortalExperimentSettingsUpdate(PortalBaseModel):
    default_baseline_days: int | None = Field(default=None, ge=3, le=30)
    default_post_days: int | None = Field(default=None, ge=3, le=30)
    default_evaluation_delay_days: int | None = Field(default=None, ge=0, le=14)
    minimum_orders: int | None = Field(default=None, ge=0, le=100000)
    minimum_revenue: float | None = Field(default=None, ge=0)
    minimum_views: int | None = Field(default=None, ge=0)
    maximum_stockout_days: int | None = Field(default=None, ge=0, le=30)
    allow_overlapping_experiments: bool | None = None
    weekday_matched_baseline: bool | None = None


class PortalExperimentCreate(PortalBaseModel):
    account_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    experiment_type: ExperimentType = "before_after"
    intervention_type: ExperimentInterventionType = "manual_other"
    hypothesis: str = Field(min_length=1)
    primary_metric: str = "revenue"
    secondary_metrics: list[str] = Field(default_factory=list)
    guardrail_metrics: list[str] = Field(default_factory=lambda: ["stockout_days"])
    baseline_days: int | None = Field(default=None, ge=3, le=30)
    post_days: int | None = Field(default=None, ge=3, le=30)
    evaluation_delay_days: int | None = Field(default=None, ge=0, le=14)
    planned_start_at: datetime | None = None
    source_module: str | None = None
    source_action_key: str | None = None
    source_project_id: str | None = None
    is_test: bool = False


class PortalExperimentUpdate(PortalBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    hypothesis: str | None = Field(default=None, min_length=1)
    primary_metric: str | None = None
    secondary_metrics: list[str] | None = None
    guardrail_metrics: list[str] | None = None
    planned_start_at: datetime | None = None


class PortalExperimentMetricSnapshotRead(PortalBaseModel):
    id: int
    experiment_id: int
    window_type: Literal["baseline", "post", "comparison_reference"]
    metric_date: date
    metric_name: str
    metric_value: float | None = None
    metric_unit: str = "number"
    source: str
    data_status: str
    is_complete: bool = True
    warnings: list[str] = Field(default_factory=list)
    data_freshness_at: datetime | None = None
    created_at: datetime | None = None


class PortalExperimentInterventionCreate(PortalBaseModel):
    applied_at: datetime
    application_mode: Literal[
        "manual_record",
        "photo_project",
        "price_module",
        "ads_module",
        "reputation_module",
        "grouping_review",
        "stock_action",
        "sync_confirmed",
    ] = "manual_record"
    change_summary: str = Field(min_length=1)
    before_reference: dict[str, Any] = Field(default_factory=dict)
    after_reference: dict[str, Any] = Field(default_factory=dict)
    external_reference: str | None = None
    confirmed_by_sync: bool = False


class PortalExperimentInterventionRead(PortalBaseModel):
    id: int
    experiment_id: int
    intervention_type: str
    applied_at: datetime
    applied_by_user_id: int | None = None
    application_mode: str
    change_summary: str
    before_reference: dict[str, Any] = Field(default_factory=dict)
    after_reference: dict[str, Any] = Field(default_factory=dict)
    external_reference: str | None = None
    confirmed_by_sync: bool = False
    confirmed_at: datetime | None = None


class PortalExperimentEvaluationRead(PortalBaseModel):
    id: int
    experiment_id: int
    status: str
    evaluation_version: str = "before_after_v1"
    evaluated_at: datetime
    baseline_window: dict[str, Any] = Field(default_factory=dict)
    post_window: dict[str, Any] = Field(default_factory=dict)
    primary_result: dict[str, Any] = Field(default_factory=dict)
    secondary_results: list[dict[str, Any]] = Field(default_factory=list)
    guardrail_results: list[dict[str, Any]] = Field(default_factory=list)
    data_sufficiency: dict[str, Any] = Field(default_factory=dict)
    confounders: list[dict[str, Any]] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "low"
    outcome: ExperimentOutcome
    seller_summary: str
    technical_summary: dict[str, Any] = Field(default_factory=dict)


class PortalExperimentRead(PortalBaseModel):
    id: int
    account_id: int
    nm_id: int | None = None
    sku_id: int | None = None
    name: str
    description: str | None = None
    experiment_type: str
    intervention_type: str
    status: ExperimentStatus
    hypothesis: str
    primary_metric: str
    secondary_metrics: list[str] = Field(default_factory=list)
    guardrail_metrics: list[str] = Field(default_factory=list)
    baseline_days: int
    post_days: int
    evaluation_delay_days: int
    planned_start_at: datetime | None = None
    started_at: datetime | None = None
    intervention_at: datetime | None = None
    evaluation_due_at: datetime | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_by_user_id: int | None = None
    source_module: str | None = None
    source_action_key: str | None = None
    source_project_id: str | None = None
    is_test: bool = False
    baseline_summary: dict[str, Any] = Field(default_factory=dict)
    progress: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    latest_evaluation: PortalExperimentEvaluationRead | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PortalExperimentsPage(PortalBaseModel):
    status: str = "ok"
    total: int
    limit: int
    offset: int
    items: list[PortalExperimentRead] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    unavailable_sources: list[str] = Field(default_factory=list)


class PortalExperimentMetricsPage(PortalBaseModel):
    total: int
    limit: int
    offset: int
    items: list[PortalExperimentMetricSnapshotRead] = Field(default_factory=list)


class PortalExperimentEventCreate(PortalBaseModel):
    account_id: int
    nm_id: int
    sku_id: int | None = None
    action_id: int | None = None
    event_type: Literal[
        "title_changed",
        "description_changed",
        "photo_changed",
        "price_changed",
        "ad_changed",
        "stock_action_done",
        "grouping_previewed",
        "manual_note",
    ]
    before_json: dict[str, Any] = Field(default_factory=dict)
    after_json: dict[str, Any] = Field(default_factory=dict)
    changed_at: datetime | None = None


class PortalExperimentEventRead(PortalBaseModel):
    id: int
    account_id: int
    nm_id: int
    sku_id: int | None = None
    action_id: int | None = None
    event_type: str
    before_json: dict[str, Any] = Field(default_factory=dict)
    after_json: dict[str, Any] = Field(default_factory=dict)
    changed_at: datetime
    created_by: int | None = None
    created_at: datetime


class PortalExperimentEventsPage(PortalBaseModel):
    total: int
    limit: int
    offset: int
    items: list[PortalExperimentEventRead] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


RESULT_TRACKING_EVENT_TYPES = (
    "before_snapshot",
    "action_started",
    "action_completed",
    "after_snapshot",
    "measured_comparison",
    "result_evaluated",
    "recheck_result",
    "cost_uploaded",
    "card_issue_fixed",
    "photo_changed",
    "photo_fix_started",
    "photo_fix_completed",
    "photo_fix_skipped",
    "title_changed",
    "description_changed",
    "price_changed",
    "ad_review_done",
    "reputation_reply_published",
    "claim_submitted",
    "claim_approved",
    "stock_action_done",
    "grouping_previewed",
    "grouping_review_completed",
)


class PortalResultEventCreate(PortalBaseModel):
    event_type: Literal[
        "before_snapshot",
        "action_started",
        "action_completed",
        "after_snapshot",
        "measured_comparison",
        "result_evaluated",
        "recheck_result",
        "cost_uploaded",
        "card_issue_fixed",
        "photo_changed",
        "photo_fix_started",
        "photo_fix_completed",
        "photo_fix_skipped",
        "title_changed",
        "description_changed",
        "price_changed",
        "ad_review_done",
        "reputation_reply_published",
        "claim_submitted",
        "claim_approved",
        "stock_action_done",
        "grouping_previewed",
        "grouping_review_completed",
    ]
    nm_id: int | None = None
    sku_id: int | None = None
    before_snapshot: dict[str, Any] = Field(default_factory=dict)
    after_snapshot: dict[str, Any] = Field(default_factory=dict)
    snapshot_day: Literal[0, 7, 14, 30] | None = None
    message: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class PortalResultEventRead(PortalBaseModel):
    id: str
    account_id: int
    action_id: int | None = None
    problem_instance_id: int | None = None
    problem_code: str | None = None
    source_module: str = "result_tracking"
    source_id: str | None = None
    external_id: str | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    vendor_code: str | None = None
    product_title: str | None = None
    impact_type: str | None = None
    trust_state: str | None = None
    event_type: str
    outcome: Literal[
        "improved", "worse", "neutral", "pending", "blocked", "not_enough_data"
    ] = "not_enough_data"
    result_status: Literal[
        "pending_data", "improved", "worse", "neutral", "not_enough_data"
    ] = "pending_data"
    comparison: dict[str, Any] = Field(default_factory=dict)
    measured_comparison: dict[str, Any] | None = None
    product_identity: dict[str, Any] = Field(default_factory=dict)
    before_snapshot: dict[str, Any] = Field(default_factory=dict)
    after_snapshot: dict[str, Any] = Field(default_factory=dict)
    evidence_ledger: dict[str, Any] = Field(default_factory=dict)
    snapshot_day: int | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: str | None = "low"
    saved_money_claimed: bool = False
    action_center_href: str | None = None
    product_href: str | None = None
    results_href: str | None = None
    data_fix_href: str | None = None
    checker_href: str | None = None
    metric_template_code: str | None = None
    relevant_metric_keys: list[str] = Field(default_factory=list)
    missing_metric_keys: list[str] = Field(default_factory=list)
    calculation_note: str = "События результата показывают корреляцию, но сами по себе не доказывают причинность."
    created_by: int | None = None
    created_at: datetime | None = None
    last_recheck_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)


class PortalResultEventsPage(PortalBaseModel):
    status: str = "ok"
    total: int
    limit: int
    offset: int
    summary: dict[str, Any] = Field(default_factory=dict)
    by_module: dict[str, Any] = Field(default_factory=dict)
    by_outcome: dict[str, int] = Field(default_factory=dict)
    recent_events: list[PortalResultEventRead] = Field(default_factory=list)
    pending_followups: list[dict[str, Any]] = Field(default_factory=list)
    finance_windows: dict[str, Any] = Field(default_factory=dict)
    disclaimer: str = "корреляция, причинность не гарантирована"
    items: list[PortalResultEventRead] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class PortalModulesHealthRead(PortalBaseModel):
    computed_at: datetime
    modules: PortalModuleHealth
    unavailable_sources: list[str] = Field(default_factory=list)


class PortalStatusBlock(PortalBaseModel):
    state: str
    title: str
    message: str


class PortalCostStatus(PortalBaseModel):
    sku_coverage_percent: float | None = None
    revenue_coverage_percent: float | None = None
    missing_cost_count: int = 0
    missing_cost_revenue: float = 0.0
    state: Literal["ok", "warning", "blocked", "unknown"] = "unknown"
    evidence_ledger: EvidenceLedger | None = None


class PortalReadinessBlocker(PortalBaseModel):
    code: str
    priority: str
    title: str
    affected_sku_count: int = 0
    affected_revenue: float = 0.0
    next_screen_path: str = ""
    primary_button_label: str = ""
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "PortalReadinessBlocker":
        trust = classify_money_trust(
            value=self.affected_revenue or self.affected_sku_count,
            value_type="money" if self.affected_revenue else "count",
            confidence="blocked"
            if self.priority in {"critical", "high"}
            else "provisional",
            impact_type="data_blocker",
            source_module="data_quality",
            source_table="data_quality_issues",
            source_endpoint="GET /api/v1/portal/data-readiness",
            action_type=self.code,
            affected_amount=0 if self.affected_revenue else None,
            affected_revenue=self.affected_revenue,
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = evidence_ledger(
                value=self.affected_revenue or self.affected_sku_count,
                value_type="money" if self.affected_revenue else "count",
                confidence="blocked"
                if self.priority in {"critical", "high"}
                else "provisional",
                impact_type="data_blocker",
                formula_human=f"Блокер готовности `{self.code}` рассчитан по проверкам качества данных и покрытия себестоимости.",
                formula_code=f"portal.data_readiness.{self.code}",
                formula_id=f"readiness:{self.code}",
                label=self.title,
                unit="RUB" if self.affected_revenue else "sku",
                source_table="data_quality_issues",
                source_endpoint="GET /api/v1/portal/data-readiness",
                row_count=self.affected_sku_count,
                sample_rows=[
                    {
                        "code": self.code,
                        "affected_sku_count": self.affected_sku_count,
                        "affected_revenue": self.affected_revenue,
                    }
                ],
                next_fix_action={
                    "label": self.primary_button_label or "Открыть исправление",
                    "screen_path": self.next_screen_path,
                    "source_endpoint": "GET /api/v1/portal/data-readiness",
                    "action_type": self.code,
                },
                recheck_rule="Исправьте блокер, запустите синхронизацию или проверку качества данных, затем обновите готовность данных.",
                money_trust=trust,
                is_synthetic=True,
            )
        if self.money_trust is None:
            self.money_trust = self.evidence_ledger.money_trust or trust
        self.evidence_ledger.money_trust = self.money_trust
        return self


class PortalNextStep(PortalBaseModel):
    id: str
    label: str
    screen_path: str | None = None
    endpoint: str | None = None


class PortalSafeAction(PortalBaseModel):
    id: str
    label: str
    endpoint: str


PortalReadinessSourceStatus = Literal[
    "fresh", "stale", "missing", "not_configured", "error"
]


class PortalDataReadinessSource(PortalBaseModel):
    source_code: str
    title: str
    status: PortalReadinessSourceStatus
    last_synced_at: datetime | None = None
    freshness_minutes: int | None = None
    freshness_hours: float | None = None
    required_for: list[str] = Field(default_factory=list)
    blocks_calculation: list[str] = Field(default_factory=list)
    missing_reason: str | None = None
    next_action_code: str | None = None
    next_action_label: str | None = None
    target_href: str | None = None


class PortalDataSyncRunSummary(PortalBaseModel):
    id: int
    source_code: str
    domain: str
    status: str
    trigger: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    is_backfill: bool = False
    progress_percent: float | None = None
    rows_loaded: int = 0
    error_text: str | None = None
    user_facing_status: str | None = None

    @field_validator("error_text", mode="before")
    @classmethod
    def scrub_error_text(cls, value: Any) -> Any:
        return redact_sensitive_text(value)


class PortalDataSyncDomainStatus(PortalBaseModel):
    domain: str
    status: Literal[
        "completed",
        "failed",
        "not_started",
        "running",
        "queued",
        "partial",
        "skipped",
        "unknown",
    ]
    source_code: str | None = None
    title: str | None = None
    token_category: str | None = None
    token_configured: bool = False
    configured: bool = False
    permission_status: Literal["ok", "missing", "unknown"] = "unknown"
    permission_ok: bool | None = None
    token_ok: bool | None = None
    last_synced_at: datetime | None = None
    last_successful_sync_at: datetime | None = None
    last_failed_sync_at: datetime | None = None
    data_watermark_at: datetime | None = None
    last_error_text: str | None = None
    last_error_human_message: str | None = None
    rows_loaded: int = 0
    raw_response_count: int = 0
    freshness_status: Literal["fresh", "stale", "missing", "failed"] = "missing"
    source_status: PortalReadinessSourceStatus | None = None
    user_facing_status: str | None = None
    freshness_minutes: int | None = None
    freshness_hours: float | None = None
    missing_reason: str | None = None
    blocks_calculation: list[str] = Field(default_factory=list)
    next_action: Literal["sync", "wait", "fix_token"] = "sync"
    next_action_code: str | None = None
    next_action_label: str | None = None
    target_href: str | None = None
    next_recommended_action: str = "Запустить синхронизацию источника"
    required_for: list[str] = Field(default_factory=list)

    @field_validator("last_error_text", mode="before")
    @classmethod
    def scrub_last_error_text(cls, value: Any) -> Any:
        return redact_sensitive_text(value)

    @field_validator("last_error_human_message", mode="before")
    @classmethod
    def scrub_last_error_human_message(cls, value: Any) -> Any:
        return redact_sensitive_text(value)


class PortalDataSyncStatusRead(PortalBaseModel):
    account_id: int
    overall_state: Literal["ok", "warning", "failed", "unknown"]
    user_facing_status: str | None = None
    has_active_sync: bool = False
    has_stale_running_sync: bool = False
    data_alignment_status: Literal[
        "aligned", "new_account", "misaligned", "insufficient_data"
    ] = "insufficient_data"
    data_alignment_warnings: list[str] = Field(default_factory=list)
    data_alignment_domains: list[str] = Field(default_factory=list)
    last_calculated_at: datetime | None = None
    calculation_cache_status: Literal["fresh", "stale", "missing", "unknown"] = (
        "missing"
    )
    calculation_refresh_status: Literal[
        "ready", "pending", "blocked", "stale", "unknown"
    ] = "unknown"
    calculation_refresh_message: str | None = None
    domains: list[PortalDataSyncDomainStatus] = Field(default_factory=list)
    sources: list[PortalDataReadinessSource] = Field(default_factory=list)
    current_sync_runs: list[PortalDataSyncRunSummary] = Field(default_factory=list)
    last_successful_sync_by_source: dict[str, datetime | None] = Field(
        default_factory=dict
    )
    failed_syncs: list[PortalDataSyncRunSummary] = Field(default_factory=list)
    queued_syncs: list[PortalDataSyncRunSummary] = Field(default_factory=list)
    active_sync_progress: list[PortalDataSyncRunSummary] = Field(default_factory=list)
    safe_actions: list[PortalSafeAction] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PortalDataReadinessRead(PortalBaseModel):
    account_id: int
    operational_status: PortalStatusBlock
    final_profit_status: PortalStatusBlock
    cost_status: PortalCostStatus
    sources: list[PortalDataReadinessSource] = Field(default_factory=list)
    blockers: list[PortalReadinessBlocker] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sync_status: PortalDataSyncStatusRead
    next_steps: list[PortalNextStep] = Field(default_factory=list)
    evidence_ledger: dict[str, EvidenceLedger] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "PortalDataReadinessRead":
        if not self.evidence_ledger:
            self.evidence_ledger = {
                "final_profit_status": evidence_ledger(
                    value=self.final_profit_status.state,
                    value_type="status",
                    confidence="blocked"
                    if self.final_profit_status.state == "blocked"
                    else "provisional",
                    impact_type="data_blocker" if self.blockers else "system_warning",
                    formula_human="Готовность данных объединяет операционный статус, финальную прибыль, покрытие себестоимости и состояние синхронизации.",
                    formula_code="portal.data_readiness.final_profit_status",
                    formula_id="portal_data_readiness",
                    label=self.final_profit_status.title,
                    source_endpoint="GET /api/v1/portal/data-readiness",
                    filters={"account_id": self.account_id},
                    row_count=len(self.blockers),
                    sample_rows=[
                        {
                            "operational_status": self.operational_status.state,
                            "final_profit_status": self.final_profit_status.state,
                            "blockers": len(self.blockers),
                            "warnings": len(self.warnings),
                        }
                    ],
                    missing_data=self.warnings,
                    next_fix_action={
                        "label": self.next_steps[0].label
                        if self.next_steps
                        else "Открыть Data Fix",
                        "screen_path": self.next_steps[0].screen_path
                        if self.next_steps
                        else "/data-fix",
                        "source_endpoint": "GET /api/v1/portal/data-readiness",
                        "action_type": "data_readiness",
                    },
                    recheck_rule="Выполните следующие шаги и обновите готовность данных.",
                    is_synthetic=True,
                )
            }
        return self
