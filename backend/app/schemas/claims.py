from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field

from app.schemas.operator import (
    CaseType,
    DraftType,
    DraftOut,
    EvidenceOut,
    ExternalStatus,
    OperatorBaseModel,
    OperatorModule,
    Priority,
    ResultEventOut,
    TrustState,
    UnifiedActionOut,
)


class ClaimsCaseStatus(StrEnum):
    CANDIDATE = "candidate"
    EVIDENCE_NEEDED = "evidence_needed"
    DRAFT_READY = "draft_ready"
    READY_TO_SUBMIT = "ready_to_submit"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REPEAT = "needs_repeat"
    CLOSED = "closed"


class ClaimsCaseCreate(OperatorBaseModel):
    account_id: int
    case_type: CaseType = CaseType.DEFECT
    nm_id: int | None = None
    vendor_code: str | None = None
    order_id: str | None = None
    srid: str | None = None
    title: str
    summary: str = ""
    priority: Priority = Priority.P3
    estimated_amount: float | None = None
    source_id: str | None = None
    external_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimsCaseFromSignalCreate(OperatorBaseModel):
    account_id: int
    source_module: str = "claims"
    source_id: str
    case_type: CaseType = CaseType.DEFECT
    nm_id: int | None = None
    vendor_code: str | None = None
    title: str
    summary: str = ""
    priority: Priority = Priority.P1
    estimated_amount: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimsCaseUpdate(OperatorBaseModel):
    status: ClaimsCaseStatus | None = None
    priority: Priority | None = None
    estimated_amount: float | None = None
    title: str | None = None
    summary: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimsEvidenceCreate(OperatorBaseModel):
    evidence_type: str = "manual"
    title: str
    description: str = ""
    source_id: str | None = None
    external_id: str | None = None
    file_name: str | None = None
    content_type: str | None = None
    url: str | None = None
    captured_at: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimsDraftGenerateRequest(OperatorBaseModel):
    draft_type: DraftType = DraftType.SUPPORT_APPEAL
    tone: str | None = None
    language: str = "ru"
    instructions: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimsQrExtractOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    order_fields: dict[str, Any] = Field(default_factory=dict)
    raw_text: str | None = None
    confidence: float | None = None
    warnings: list[str] = Field(default_factory=list)


class ClaimsOrderLookupRequest(OperatorBaseModel):
    account_id: int | None = None
    order_fields: dict[str, Any] = Field(default_factory=dict)


class ClaimsSupportSubcategoryOut(OperatorBaseModel):
    label: str
    value: str
    index: int | None = None


class ClaimsSupportCategoryOut(OperatorBaseModel):
    label: str
    value: str
    index: int | None = None
    subcategories: list[ClaimsSupportSubcategoryOut] = Field(default_factory=list)


class ClaimsSupportCategoriesOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    categories: list[ClaimsSupportCategoryOut] = Field(default_factory=list)
    source_system: str = "local"
    cached: bool = True


class ClaimsAppealDraftRequest(OperatorBaseModel):
    account_id: int | None = None
    category: str
    subcategory: str
    order_fields: dict[str, Any] = Field(default_factory=dict)
    defect_description: str = ""
    operator_note: str = ""
    video_url: str | None = None


class ClaimsAppealDraftOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    category: str
    subcategory: str
    subject: str = ""
    body: str = ""
    facts_used: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    model_name: str = "fallback-template"
    warnings: list[str] = Field(default_factory=list)


class ClaimsProofCheckRequest(OperatorBaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimsSubmitRequest(OperatorBaseModel):
    confirm: bool = False
    draft_id: str | None = None
    external_ticket_id: str | None = None
    ticket_number: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ClaimScanRequest(OperatorBaseModel):
    account_id: int | None = None
    detector_types: list[str] = Field(default_factory=lambda: ["all"])
    date_from: date | None = None
    date_to: date | None = None
    force: bool = False


class ClaimCandidateOut(OperatorBaseModel):
    id: str
    account_id: int
    detector_type: str
    source_type: str | None = None
    source_id: str | None = None
    external_id: str | None = None
    external_reference: str | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    supply_id: str | None = None
    report_id: str | None = None
    order_id: str | None = None
    sale_id: str | None = None
    warehouse_id: str | None = None
    period_from: date | None = None
    period_to: date | None = None
    title: str
    business_explanation: str | None = None
    reason_code: str | None = None
    severity: str = "medium"
    confidence: float | None = None
    expected_amount: float | None = None
    quantity_affected: float | None = None
    status: str = "new"
    fingerprint: str
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    source_revision: str | None = None
    detection_run_id: str | None = None
    case_id: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ClaimCandidatesPage(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[ClaimCandidateOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class ClaimCandidateStatusUpdate(OperatorBaseModel):
    status: str
    reason: str | None = None


class ClaimDetectionRunOut(OperatorBaseModel):
    id: str
    account_id: int
    detector_type: str
    status: str
    requested_by_user_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    candidates_found: int = 0
    candidates_created: int = 0
    candidates_updated: int = 0
    candidates_skipped: int = 0
    rows_failed: int = 0
    error_code: str | None = None
    error_summary: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ClaimDetectionRunsPage(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[ClaimDetectionRunOut] = Field(default_factory=list)


class ClaimScanStartOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int
    run_ids: list[str] = Field(default_factory=list)
    runs: list[ClaimDetectionRunOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class ClaimsDetectionOut(OperatorBaseModel):
    status: Literal[
        "ok",
        "disabled",
        "not_configured",
        "not_implemented",
        "not_enough_data",
        "unavailable",
        "empty",
    ] = "empty"
    case_type: CaseType
    account_id: int
    items: list[dict[str, Any]] = Field(default_factory=list)
    item_count: int = 0
    trust_state: TrustState = TrustState.UNAVAILABLE
    message: str | None = None
    next_stage: str | None = None
    unavailable_sources: list[str] = Field(default_factory=list)
    required_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    template: dict[str, Any] = Field(default_factory=dict)


class ClaimsCasesPage(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list["CaseListItemOut"] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.OPERATIONAL


class ClaimsDraftMutationOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    case_id: str | None = None
    draft: DraftOut | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.OPERATIONAL


class ClaimsProofCheckOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.CLAIMS
    account_id: int | None = None
    case_id: str | None = None
    passed: bool = False
    missing_evidence: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.PROVISIONAL
    data: dict[str, Any] = Field(default_factory=dict)


class CaseListItemOut(OperatorBaseModel):
    id: str
    case_type: CaseType
    external_id: str | None = None
    external_status: ExternalStatus = ExternalStatus.NOT_CREATED
    account_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    order_id: str | None = None
    srid: str | None = None
    title: str = ""
    summary: str = ""
    priority: Priority = Priority.P3
    status: ClaimsCaseStatus = ClaimsCaseStatus.CANDIDATE
    trust_state: TrustState = TrustState.PROVISIONAL
    amount_claimed: float | None = None
    amount_approved: float | None = None
    opened_at: datetime | None = None
    updated_at: datetime | None = None
    deadline_at: datetime | None = None
    evidence_count: int = 0
    draft_count: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class CaseDetailOut(CaseListItemOut):
    module: OperatorModule = OperatorModule.CLAIMS
    description: str = ""
    finance_trace: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    drafts: list[DraftOut] = Field(default_factory=list)
    actions: list[UnifiedActionOut] = Field(default_factory=list)
    result_events: list[ResultEventOut] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
