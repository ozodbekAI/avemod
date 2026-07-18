from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.evidence import EvidenceLedger


MetricValueType = Literal[
    "money", "number", "percent", "count", "days", "boolean", "text"
]
MetricGrain = Literal[
    "account_day", "product_day", "product_period", "campaign_day", "warehouse_day"
]
ProblemEntityType = Literal["account", "product", "campaign", "warehouse", "category"]
ProblemDefinitionStatus = Literal["draft", "testing", "active", "paused", "archived"]
ProblemRuleVersionStatus = Literal[
    "draft", "testing", "active", "paused", "retired", "archived"
]
ProblemInstanceStatus = Literal[
    "new",
    "acknowledged",
    "in_progress",
    "done",
    "postponed",
    "ignored",
    "blocked",
    "candidate_resolved",
    "resolved",
    "dismissed",
]
ProblemTrustState = Literal[
    "confirmed", "provisional", "estimated", "opportunity", "blocked", "test_only"
]
ProblemImpactType = Literal[
    "confirmed_loss",
    "probable_loss",
    "blocked_cash",
    "lost_sales_risk",
    "opportunity",
    "data_blocker",
    "system_warning",
]
ProblemSeverity = Literal["critical", "high", "medium", "low"]
ProblemVisibilityMode = Literal["admin_only", "beta", "seller"]


class ProblemVisibilityMixin(BaseModel):
    test_only: bool = False
    seller_visible: bool = True
    visibility_mode: ProblemVisibilityMode = "seller"

    @field_validator("test_only", mode="before")
    @classmethod
    def _default_test_only(cls, value: Any) -> bool:
        return bool(value) if value is not None else False

    @field_validator("seller_visible", mode="before")
    @classmethod
    def _default_seller_visible(cls, value: Any) -> bool:
        return bool(value) if value is not None else True

    @field_validator("visibility_mode", mode="before")
    @classmethod
    def _default_visibility_mode(cls, value: Any) -> str:
        return str(value or "seller")


class MetricCatalogBase(BaseModel):
    metric_code: str
    title: str
    description: str = ""
    value_type: MetricValueType
    unit: str | None = None
    grain: MetricGrain
    entity_type: ProblemEntityType
    source_module: str
    formula_json: dict[str, Any] | None = None
    source_tables_json: list[str] = Field(default_factory=list)
    source_endpoints_json: list[str] = Field(default_factory=list)
    required_metrics_json: list[str] = Field(default_factory=list)
    trust_state: ProblemTrustState = "provisional"
    is_admin_visible: bool = True
    is_deprecated: bool = False


class MetricCatalogCreate(MetricCatalogBase):
    pass


class MetricCatalogUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    value_type: MetricValueType | None = None
    unit: str | None = None
    grain: MetricGrain | None = None
    entity_type: ProblemEntityType | None = None
    source_module: str | None = None
    formula_json: dict[str, Any] | None = None
    source_tables_json: list[str] | None = None
    source_endpoints_json: list[str] | None = None
    required_metrics_json: list[str] | None = None
    trust_state: ProblemTrustState | None = None
    is_admin_visible: bool | None = None
    is_deprecated: bool | None = None


class MetricCatalogRead(MetricCatalogBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MetricSourceReference(BaseModel):
    source_module: str
    source_table: str | None = None
    source_endpoint: str | None = None
    source_service: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    row_count: int | None = None
    freshness: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ResolvedMetricValue(BaseModel):
    metric_code: str
    value: Decimal | int | float | bool | str | None = None
    value_type: MetricValueType | None = None
    unit: str | None = None
    trust_state: ProblemTrustState | None = None
    is_missing: bool = False
    missing_reason: str | None = None
    evidence: MetricSourceReference


class ProductMetricResolution(BaseModel):
    account_id: int
    nm_id: int
    date_from: date
    date_to: date
    metrics: dict[str, ResolvedMetricValue] = Field(default_factory=dict)
    missing_metrics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def values_for_formula(
        self,
    ) -> dict[str, Decimal | int | float | bool | str | None]:
        return {
            metric_code: metric.value
            for metric_code, metric in self.metrics.items()
            if not metric.is_missing
        }


class ProblemDefinitionBase(ProblemVisibilityMixin):
    problem_code: str
    source_module: str
    category: str
    entity_type: ProblemEntityType
    title_template: str
    description_template: str
    recommendation_template: str
    impact_type_default: ProblemImpactType
    trust_state_default: ProblemTrustState = "provisional"
    severity_default: ProblemSeverity = "medium"
    allowed_actions_json: list[str] = Field(default_factory=list)
    status: ProblemDefinitionStatus = "draft"
    is_system_seeded: bool = False
    created_by_user_id: int | None = None


class ProblemDefinitionCreate(ProblemDefinitionBase):
    pass


class ProblemDefinitionUpdate(BaseModel):
    source_module: str | None = None
    category: str | None = None
    entity_type: ProblemEntityType | None = None
    title_template: str | None = None
    description_template: str | None = None
    recommendation_template: str | None = None
    impact_type_default: ProblemImpactType | None = None
    trust_state_default: ProblemTrustState | None = None
    severity_default: ProblemSeverity | None = None
    allowed_actions_json: list[str] | None = None
    test_only: bool | None = None
    seller_visible: bool | None = None
    visibility_mode: ProblemVisibilityMode | None = None
    status: ProblemDefinitionStatus | None = None


class ProblemDefinitionRead(ProblemDefinitionBase):
    id: int
    total_instances: int = 0
    dismissed_count: int = 0
    resolved_count: int = 0
    active_count: int = 0
    false_positive_rate: float | None = None
    dismissed_rate: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProblemRuleVersionBase(ProblemVisibilityMixin):
    problem_definition_id: int
    version: int
    status: ProblemRuleVersionStatus = "draft"
    evaluation_grain: MetricGrain
    lookback_days: int = 30
    condition_json: dict[str, Any] = Field(default_factory=dict)
    impact_formula_json: Any = Field(default_factory=dict)
    severity_formula_json: Any = Field(default_factory=dict)
    confidence_formula_json: Any = Field(default_factory=dict)
    dedup_key_template: str
    recheck_rule_json: dict[str, Any] = Field(default_factory=dict)
    evidence_template_json: dict[str, Any] = Field(default_factory=dict)
    is_system_seeded: bool = False
    created_by_user_id: int | None = None
    published_by_user_id: int | None = None
    published_at: datetime | None = None


class ProblemRuleVersionCreate(ProblemRuleVersionBase):
    pass


class ProblemRuleVersionUpdate(BaseModel):
    status: ProblemRuleVersionStatus | None = None
    evaluation_grain: MetricGrain | None = None
    lookback_days: int | None = None
    condition_json: dict[str, Any] | None = None
    impact_formula_json: Any | None = None
    severity_formula_json: Any | None = None
    confidence_formula_json: Any | None = None
    dedup_key_template: str | None = None
    recheck_rule_json: dict[str, Any] | None = None
    evidence_template_json: dict[str, Any] | None = None
    test_only: bool | None = None
    seller_visible: bool | None = None
    visibility_mode: ProblemVisibilityMode | None = None
    published_by_user_id: int | None = None
    published_at: datetime | None = None


class ProblemRuleVersionRead(ProblemRuleVersionBase):
    id: int
    total_instances: int = 0
    dismissed_count: int = 0
    resolved_count: int = 0
    active_count: int = 0
    false_positive_rate: float | None = None
    dismissed_rate: float | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProblemInstanceBase(BaseModel):
    account_id: int
    problem_code: str
    problem_definition_id: int
    rule_version_id: int
    source_module: str
    entity_type: ProblemEntityType
    entity_id: str
    nm_id: int | None = None
    vendor_code: str | None = None
    dedup_key: str
    title: str
    explanation: str
    recommendation: str
    severity: ProblemSeverity
    status: ProblemInstanceStatus = "new"
    impact_type: ProblemImpactType
    money_impact_amount: Decimal | None = None
    money_impact_currency: str | None = None
    trust_state: ProblemTrustState
    confidence: str | None = None
    evidence_ledger_json: dict[str, Any] = Field(default_factory=dict)
    calculation_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None
    dismiss_reason: str | None = None


class ProblemInstanceCreate(ProblemInstanceBase):
    @model_validator(mode="after")
    def require_evidence_ledger(self) -> "ProblemInstanceCreate":
        if not self.evidence_ledger_json:
            raise ValueError("generated problem instances require evidence_ledger_json")
        ledger = EvidenceLedger.model_validate(self.evidence_ledger_json)
        if not ledger.formula_human:
            raise ValueError("generated problem evidence requires formula_human")
        if not (ledger.formula_id or ledger.formula_code):
            raise ValueError(
                "generated problem evidence requires formula_id or formula_code"
            )
        if not ledger.input_facts:
            raise ValueError("generated problem evidence requires input_facts")
        if not ledger.source_references:
            raise ValueError("generated problem evidence requires source_references")
        if ledger.recheck_rule_human is None:
            raise ValueError("generated problem evidence requires recheck_rule_human")
        return self


class ProblemInstanceUpdate(BaseModel):
    status: ProblemInstanceStatus | None = None
    title: str | None = None
    explanation: str | None = None
    recommendation: str | None = None
    severity: ProblemSeverity | None = None
    impact_type: ProblemImpactType | None = None
    money_impact_amount: Decimal | None = None
    money_impact_currency: str | None = None
    trust_state: ProblemTrustState | None = None
    confidence: str | None = None
    evidence_ledger_json: dict[str, Any] | None = None
    calculation_snapshot_json: dict[str, Any] | None = None
    last_seen_at: datetime | None = None
    resolved_at: datetime | None = None
    dismissed_at: datetime | None = None
    dismiss_reason: str | None = None


class ProblemInstanceRead(ProblemInstanceBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProblemInstanceHistoryBase(BaseModel):
    problem_instance_id: int
    event_type: str
    old_value_json: dict[str, Any] | None = None
    new_value_json: dict[str, Any] | None = None
    comment: str | None = None
    actor_user_id: int | None = None


class ProblemInstanceHistoryCreate(ProblemInstanceHistoryBase):
    pass


class ProblemInstanceHistoryRead(ProblemInstanceHistoryBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminRuleTestRunBase(BaseModel):
    rule_version_id: int
    account_id: int | None = None
    date_from: date
    date_to: date
    matched_count: int = 0
    sample_issues_json: list[dict[str, Any]] = Field(default_factory=list)
    total_impact_amount: Decimal | None = None
    warnings_json: list[str] = Field(default_factory=list)
    created_by_user_id: int | None = None


class AdminRuleTestRunCreate(AdminRuleTestRunBase):
    pass


class AdminRuleTestRunRead(AdminRuleTestRunBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProblemEvaluationRunLogRead(BaseModel):
    id: int
    account_id: int | None = None
    trigger: str
    scope: str
    sync_run_id: int | None = None
    problem_instance_id: int | None = None
    actor_user_id: int | None = None
    nm_ids_json: list[int] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime | None = None
    status: str
    rules_evaluated: int = 0
    entities_evaluated: int = 0
    issues_created: int = 0
    issues_updated: int = 0
    issues_resolved: int = 0
    issues_candidate_resolved: int = 0
    issues_skipped: int = 0
    errors_json: list[str] = Field(default_factory=list)
    warnings_json: list[str] = Field(default_factory=list)
    result_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class ProblemRuleAdminAuditBase(BaseModel):
    object_type: Literal["definition", "rule_version"]
    object_id: int
    event_type: str
    old_value_json: dict[str, Any] | None = None
    new_value_json: dict[str, Any] | None = None
    comment: str | None = None
    actor_user_id: int | None = None


class ProblemRuleAdminAuditRead(ProblemRuleAdminAuditBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProblemDefinitionWithVersionsRead(ProblemDefinitionRead):
    versions: list[ProblemRuleVersionRead] = Field(default_factory=list)
    audit: list[ProblemRuleAdminAuditRead] = Field(default_factory=list)


class AdminProblemDefinitionCreate(BaseModel):
    problem_code: str
    source_module: str = "problem_engine"
    category: str
    entity_type: ProblemEntityType
    title_template: str
    description_template: str
    recommendation_template: str
    impact_type_default: ProblemImpactType
    trust_state_default: ProblemTrustState = "provisional"
    severity_default: ProblemSeverity = "medium"
    allowed_actions_json: list[str] = Field(default_factory=list)
    test_only: bool = False
    seller_visible: bool = True
    visibility_mode: ProblemVisibilityMode = "seller"


class AdminProblemDefinitionUpdate(BaseModel):
    source_module: str | None = None
    category: str | None = None
    entity_type: ProblemEntityType | None = None
    title_template: str | None = None
    description_template: str | None = None
    recommendation_template: str | None = None
    impact_type_default: ProblemImpactType | None = None
    trust_state_default: ProblemTrustState | None = None
    severity_default: ProblemSeverity | None = None
    allowed_actions_json: list[str] | None = None
    test_only: bool | None = None
    seller_visible: bool | None = None
    visibility_mode: ProblemVisibilityMode | None = None
    status: Literal["draft", "testing", "paused", "archived"] | None = None


class AdminProblemRuleVersionCreate(BaseModel):
    evaluation_grain: MetricGrain = "product_period"
    lookback_days: int = Field(default=30, ge=1, le=365)
    condition_json: dict[str, Any]
    impact_formula_json: Any
    severity_formula_json: Any = Field(default_factory=dict)
    confidence_formula_json: Any = Field(default_factory=dict)
    dedup_key_template: str = "{account_id}:{problem_code}:{nm_id}"
    recheck_rule_json: dict[str, Any] = Field(default_factory=dict)
    evidence_template_json: dict[str, Any] = Field(default_factory=dict)
    test_only: bool = False
    seller_visible: bool = True
    visibility_mode: ProblemVisibilityMode = "seller"


class AdminProblemRuleVersionUpdate(BaseModel):
    evaluation_grain: MetricGrain | None = None
    lookback_days: int | None = Field(default=None, ge=1, le=365)
    condition_json: dict[str, Any] | None = None
    impact_formula_json: Any | None = None
    severity_formula_json: Any | None = None
    confidence_formula_json: Any | None = None
    dedup_key_template: str | None = None
    recheck_rule_json: dict[str, Any] | None = None
    evidence_template_json: dict[str, Any] | None = None
    test_only: bool | None = None
    seller_visible: bool | None = None
    visibility_mode: ProblemVisibilityMode | None = None


class AdminRuleValidationRequest(BaseModel):
    condition_json: dict[str, Any] | None = None
    impact_formula_json: Any | None = None
    severity_formula_json: Any | None = None
    confidence_formula_json: Any | None = None
    recheck_rule_json: dict[str, Any] | None = None


class AdminFormulaValidationDiagnostic(BaseModel):
    valid: bool
    error: str | None = None
    missing_metrics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AdminRuleValidationResponse(BaseModel):
    valid: bool
    formula_results: dict[str, AdminFormulaValidationDiagnostic]
    required_metrics: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AdminRuleBacktestRequest(BaseModel):
    account_id: int
    date_from: date
    date_to: date
    nm_id: int | None = None
    sample_limit: int = Field(default=20, ge=1, le=100)


class AdminRuleBacktestResponse(BaseModel):
    rule_version_id: int
    account_id: int
    date_from: date
    date_to: date
    matched_count: int
    evaluated_count: int
    sample_issues: list[dict[str, Any]] = Field(default_factory=list)
    total_impact_amount: Decimal | None = None
    total_expected_impact: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    missing_metric_stats: dict[str, int] = Field(default_factory=dict)
    sample_evidence: list[dict[str, Any]] = Field(default_factory=list)
    seller_preview_payload: dict[str, Any] = Field(default_factory=dict)
    test_run_id: int | None = None


class AdminRuleBacktestHistoryItem(AdminRuleTestRunRead):
    run_id: int
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["queued", "running", "completed", "failed"] = "completed"
    warnings: list[str] = Field(default_factory=list)
    evaluated_count: int | None = None
    total_expected_impact: dict[str, Any] = Field(default_factory=dict)
    missing_metric_stats: dict[str, int] = Field(default_factory=dict)
    sample_evidence: list[dict[str, Any]] = Field(default_factory=list)
    seller_preview_payload: dict[str, Any] = Field(default_factory=dict)


class AdminRuleBacktestHistoryPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    items: list[AdminRuleBacktestHistoryItem] = Field(default_factory=list)


class ProblemRuleInstanceItem(BaseModel):
    id: int
    problem_instance_id: int
    account_id: int
    nm_id: int | None = None
    problem_code: str
    title: str
    status: ProblemInstanceStatus
    severity: ProblemSeverity
    trust_state: ProblemTrustState
    impact_type: ProblemImpactType
    money_impact_amount: Decimal | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    dismissed_at: datetime | None = None
    dismiss_reason: str | None = None


class ProblemRuleInstancesPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    account_id: int | None = None
    status_filter: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    problem_code: str | None = None
    total_instances: int = 0
    dismissed_count: int = 0
    resolved_count: int = 0
    active_count: int = 0
    dismissed_rate: float | None = None
    false_positive_rate: float | None = None
    items: list[ProblemRuleInstanceItem] = Field(default_factory=list)


PublishBlockerKey = Literal[
    "invalid_formula",
    "unknown_metric_or_operator",
    "no_evidence",
    "no_backtest",
    "dangerous_action",
    "price_promo_missing_safety",
    "too_many_matches",
    "test_only_visibility_conflict",
    "high_missing_metric_rate",
    "no_recheck_rule",
    "no_allowed_action",
    "seller_preview_missing",
]


class AdminRulePublishBlocker(BaseModel):
    key: PublishBlockerKey
    message: str
    severity: Literal["blocker", "warning"] = "blocker"
    details: dict[str, Any] = Field(default_factory=dict)


class ProblemRuleSummaryDefinition(BaseModel):
    id: int
    problem_code: str
    title_template: str
    category: str
    entity_type: ProblemEntityType
    status: ProblemDefinitionStatus
    active_version_id: int | None = None
    latest_version_id: int | None = None
    total_instances: int = 0
    dismissed_count: int = 0
    resolved_count: int = 0
    active_count: int = 0
    generated_instances_count: int = 0
    active_instances_count: int = 0
    dismissed_instances_count: int = 0
    recent_matches_count: int = 0
    recent_created_instances: int = 0
    recent_resolved_instances: int = 0
    recent_dismissed_instances: int = 0
    false_positive_rate: float | None = None
    dismissed_rate: float | None = None


class ProblemRuleSummaryResponse(BaseModel):
    status: Literal["ok"] = "ok"
    total_definitions: int = 0
    active_definitions: int = 0
    total_versions: int = 0
    active_versions: int = 0
    testing_versions: int = 0
    draft_versions: int = 0
    paused_versions: int = 0
    generated_instances_count: int = 0
    total_instances: int = 0
    active_instances_count: int = 0
    active_count: int = 0
    dismissed_instances_count: int = 0
    dismissed_count: int = 0
    resolved_count: int = 0
    recent_matches_count: int = 0
    recent_created_instances: int = 0
    recent_resolved_instances: int = 0
    recent_dismissed_instances: int = 0
    false_positive_rate: float | None = None
    dismissed_rate: float | None = None
    compare_available: bool = False
    disabled_reason: str = "Сравнение версий будет доступно позже."
    capabilities: dict[str, Any] = Field(default_factory=dict)
    definitions: list[ProblemRuleSummaryDefinition] = Field(default_factory=list)


class ProblemRuleVersionCompareResponse(BaseModel):
    status: Literal["disabled"] = "disabled"
    definition_id: int
    left: int | None = None
    right: int | None = None
    compare_available: bool = False
    disabled_reason: str = "Сравнение версий будет доступно позже."


class ProblemRuleActionCatalogItem(BaseModel):
    action_code: str
    label: str
    module: str
    category: str
    is_navigation_only: bool = False
    is_local_only: bool = True
    is_external_write: bool = False
    is_dangerous: bool = False
    requires_preview: bool = True
    requires_confirm: bool = False
    requires_permission: bool = False
    requires_audit: bool = True
    allowed_in_rule_builder: bool = True
    allowed_for_rule_builder: bool = True
    allowed_for_seller: bool = True
    disabled_reason: str | None = None
    target_route_template: str | None = None


class ProblemRuleActionCatalogResponse(BaseModel):
    status: Literal["ok"] = "ok"
    items: list[ProblemRuleActionCatalogItem] = Field(default_factory=list)


class ProblemRuleAdminAuditPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    items: list[ProblemRuleAdminAuditRead] = Field(default_factory=list)


class AdminProblemEvaluationRequest(BaseModel):
    account_id: int
    nm_id: int | None = None
    nm_ids: list[int] = Field(default_factory=list)
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def merge_single_nm_id(self) -> "AdminProblemEvaluationRequest":
        merged = list(
            dict.fromkeys(
                [*self.nm_ids, *([self.nm_id] if self.nm_id is not None else [])]
            )
        )
        self.nm_ids = [int(value) for value in merged if value is not None]
        return self


class AdminRulePublishRequest(BaseModel):
    override: bool = False
    override_reason: str | None = None
