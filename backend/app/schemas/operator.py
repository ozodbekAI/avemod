from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


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


def _scrub_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_secret_fields(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in SECRET_FIELD_TOKENS)
        }
    if isinstance(value, list):
        return [_scrub_secret_fields(item) for item in value]
    return value


class OperatorBaseModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def scrub_secret_fields(cls, data: Any) -> Any:
        return _scrub_secret_fields(data)


class OperatorModule(StrEnum):
    FINANCE = "finance"
    CHECKER = "checker"
    STOCKOPS = "stockops"
    GROUPING = "grouping"
    REPUTATION = "reputation"
    CLAIMS = "claims"
    PHOTO = "photo"
    EXPERIMENTS = "experiments"


class SignalType(StrEnum):
    PROFIT = "profit"
    MARGIN = "margin"
    CASHFLOW = "cashflow"
    COST_COVERAGE = "cost_coverage"
    DATA_QUALITY = "data_quality"
    CARD_QUALITY = "card_quality"
    STOCK = "stock"
    GROUPING = "grouping"
    REVIEW = "review"
    QUESTION = "question"
    CHAT = "chat"
    CLAIM = "claim"
    EVIDENCE = "evidence"
    EXPERIMENT = "experiment"
    MODULE_HEALTH = "module_health"


class DiagnosisType(StrEnum):
    PROFIT_LEAK = "profit_leak"
    COST_MISSING = "cost_missing"
    ADS_EATING_PROFIT = "ads_eating_profit"
    DATA_BLOCKER = "data_blocker"
    STOCK_RISK = "stock_risk"
    FROZEN_STOCK = "frozen_stock"
    CARD_QUALITY_RISK = "card_quality_risk"
    GROUPING_OPPORTUNITY = "grouping_opportunity"
    REPUTATION_RISK = "reputation_risk"
    CLAIM_OPPORTUNITY = "claim_opportunity"
    EXPERIMENT_OPPORTUNITY = "experiment_opportunity"
    REPORT_ANOMALY = "report_anomaly"
    MODULE_UNAVAILABLE = "module_unavailable"


class ActionType(StrEnum):
    REVIEW_PROFIT = "review_profit"
    FIX_COSTS = "fix_costs"
    FIX_DATA = "fix_data"
    CARD_QUALITY_FIX = "card_quality_fix"
    GROUPING_REVIEW = "grouping_review"
    STOCK_RECOMMENDATION = "stock_recommendation"
    DRAFT_REPLY = "draft_reply"
    DRAFT_CLAIM = "draft_claim"
    OPEN_CASE = "open_case"
    SUBMIT_WITH_CONFIRM = "submit_with_confirm"
    EXPERIMENT_REVIEW = "experiment_review"
    GUIDED_FIX = "guided_fix"
    MANUAL_REVIEW = "manual_review"


class ActionStatus(StrEnum):
    NEW = "new"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    POSTPONED = "postponed"
    IGNORED = "ignored"
    BLOCKED = "blocked"


class Priority(StrEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class TrustState(StrEnum):
    FINAL = "final"
    OPERATIONAL = "operational"
    PROVISIONAL = "provisional"
    BLOCKED = "blocked"
    UNAVAILABLE = "unavailable"


class CaseType(StrEnum):
    DEFECT = "defect"
    SUPPLY_DISCREPANCY = "supply_discrepancy"
    MISSING_GOODS = "missing_goods"
    REPORT_ANOMALY = "report_anomaly"
    COMPENSATION_UNDERPAYMENT = "compensation_underpayment"
    REPEAT_CLAIM = "repeat_claim"
    PRETRIAL = "pretrial"


class DraftType(StrEnum):
    REVIEW_REPLY = "review_reply"
    QUESTION_REPLY = "question_reply"
    CHAT_REPLY = "chat_reply"
    SUPPORT_APPEAL = "support_appeal"
    CLAIM_TEXT = "claim_text"
    OBJECTION = "objection"
    PRETRIAL = "pretrial"


class ExternalStatus(StrEnum):
    NOT_CREATED = "not_created"
    DRAFT_READY = "draft_ready"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REPEAT = "needs_repeat"
    CLOSED = "closed"


class ModuleHealthOut(OperatorBaseModel):
    module: OperatorModule
    status: str = "unavailable"
    trust_state: TrustState = TrustState.UNAVAILABLE
    detail: str | None = None
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    checked_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class SignalOut(OperatorBaseModel):
    id: str | None = None
    module: OperatorModule = OperatorModule.FINANCE
    signal_type: SignalType
    account_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    source_id: str | None = None
    title: str = ""
    message: str = ""
    value: float | str | bool | None = None
    unit: str | None = None
    priority: Priority = Priority.P3
    trust_state: TrustState = TrustState.PROVISIONAL
    observed_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DiagnosisOut(OperatorBaseModel):
    id: str | None = None
    diagnosis_type: DiagnosisType
    module: OperatorModule = OperatorModule.FINANCE
    account_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    title: str = ""
    summary: str = ""
    reason: str = ""
    priority: Priority = Priority.P3
    confidence: str = "medium"
    trust_state: TrustState = TrustState.PROVISIONAL
    signal_ids: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class GuidedFixStepOut(OperatorBaseModel):
    id: str | None = None
    title: str
    description: str = ""
    status: ActionStatus = ActionStatus.NEW
    required: bool = True
    can_auto_check: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class GuidedFixOut(OperatorBaseModel):
    id: str | None = None
    module: OperatorModule = OperatorModule.FINANCE
    title: str
    summary: str = ""
    status: ActionStatus = ActionStatus.NEW
    trust_state: TrustState = TrustState.PROVISIONAL
    steps: list[GuidedFixStepOut] = Field(default_factory=list)
    confirm_required: bool = False
    audit_required: bool = False
    marketplace_change: bool = False
    safety_note: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class UnifiedActionOut(OperatorBaseModel):
    id: str
    action_type: ActionType
    status: ActionStatus = ActionStatus.NEW
    priority: Priority = Priority.P3
    module: OperatorModule = OperatorModule.FINANCE
    source_module: OperatorModule | None = None
    source_type: str | None = None
    source_id: str | None = None
    account_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    case_id: str | None = None
    title: str
    summary: str = ""
    reason: str = ""
    next_step: str = ""
    trust_state: TrustState = TrustState.PROVISIONAL
    assigned_to_user_id: int | None = None
    deadline_at: datetime | None = None
    review_status: str = "new"
    last_comment: str | None = None
    closed_at: datetime | None = None
    dismissed_at: datetime | None = None
    expected_effect_amount: float | None = None
    confidence: str = "medium"
    guided_fix: GuidedFixOut | None = None
    can_preview: bool = False
    can_confirm: bool = False
    marketplace_change: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class EvidenceOut(OperatorBaseModel):
    id: str | None = None
    case_id: str | None = None
    module: OperatorModule | None = None
    evidence_type: str = ""
    title: str = ""
    description: str = ""
    source_type: str | None = None
    source_id: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    url: str | None = None
    captured_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class DraftOut(OperatorBaseModel):
    id: str | None = None
    draft_type: DraftType
    external_status: ExternalStatus = ExternalStatus.NOT_CREATED
    account_id: int | None = None
    case_id: str | None = None
    source_type: str | None = None
    source_id: str | None = None
    title: str = ""
    text: str = ""
    language: str | None = None
    status: ActionStatus = ActionStatus.NEW
    trust_state: TrustState = TrustState.PROVISIONAL
    requires_confirmation: bool = True
    created_by: int | None = None
    approved_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ResultEventOut(OperatorBaseModel):
    id: str | None = None
    module: OperatorModule
    event_type: str
    external_status: ExternalStatus | None = None
    account_id: int | None = None
    action_id: str | None = None
    case_id: str | None = None
    draft_id: str | None = None
    title: str = ""
    message: str = ""
    success: bool | None = None
    occurred_at: datetime | None = None
    created_by: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ProfitDoctorOut(OperatorBaseModel):
    status: str = "unavailable"
    account_id: int | None = None
    date_from: date | datetime | None = None
    date_to: date | datetime | None = None
    trust_state: TrustState = TrustState.UNAVAILABLE
    summary: str = ""
    headline: str = ""
    business_status: str = "unavailable"
    critical_count: int = 0
    money_at_risk_amount: float | None = None
    money_at_risk_confidence: str = "low"
    money_at_risk_calculation_note: str = ""
    top_sections: dict[str, Any] = Field(default_factory=dict)
    today_plan_summary: str = ""
    total_signals: int = 0
    total_diagnoses: int = 0
    estimated_impact_amount: float | None = None
    estimated_impact_confidence: str = "low"
    estimated_impact_calculation_note: str = ""
    top_profit_leaks: list[DiagnosisOut] = Field(default_factory=list)
    root_causes: list[DiagnosisOut] = Field(default_factory=list)
    today_plan: list[UnifiedActionOut] = Field(default_factory=list)
    product_diagnoses: list[DiagnosisOut] = Field(default_factory=list)
    module_health: list[ModuleHealthOut] = Field(default_factory=list)
    signals: list[SignalOut] = Field(default_factory=list)
    diagnoses: list[DiagnosisOut] = Field(default_factory=list)
    actions: list[UnifiedActionOut] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class Product360Out(OperatorBaseModel):
    status: str = "unavailable"
    account_id: int | None = None
    nm_id: int
    sku_id: int | None = None
    trust_state: TrustState = TrustState.UNAVAILABLE
    identity: dict[str, Any] = Field(default_factory=dict)
    finance: dict[str, Any] = Field(default_factory=dict)
    stock: dict[str, Any] = Field(default_factory=dict)
    pricing: dict[str, Any] = Field(default_factory=dict)
    quality: dict[str, Any] = Field(default_factory=dict)
    grouping: dict[str, Any] = Field(default_factory=dict)
    reputation: dict[str, Any] = Field(default_factory=dict)
    claims: dict[str, Any] = Field(default_factory=dict)
    signals: list[SignalOut] = Field(default_factory=list)
    diagnoses: list[DiagnosisOut] = Field(default_factory=list)
    actions: list[UnifiedActionOut] = Field(default_factory=list)
    module_health: list[ModuleHealthOut] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class OperatorOverviewOut(OperatorBaseModel):
    status: str = "unavailable"
    account_id: int | None = None
    trust_state: TrustState = TrustState.UNAVAILABLE
    module_health: list[ModuleHealthOut] = Field(default_factory=list)
    profit_doctor: ProfitDoctorOut | None = None
    top_signals: list[SignalOut] = Field(default_factory=list)
    top_diagnoses: list[DiagnosisOut] = Field(default_factory=list)
    top_actions: list[UnifiedActionOut] = Field(default_factory=list)
    products: list[Product360Out] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
