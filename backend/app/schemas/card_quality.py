from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.schemas.evidence import EvidenceLedger, evidence_ledger
from app.schemas.money_trust import MoneyTrustInfo, classify_money_trust
from app.services.checker_problem_bridge import checker_bridge_semantics
from app.services.evidence import issue_evidence

CheckerImpactType = Literal[
    "opportunity", "data_blocker", "system_warning", "confirmed_loss"
]
CheckerTrustState = Literal[
    "opportunity", "estimated", "blocked", "provisional", "confirmed"
]
CheckerIssueGroup = Literal[
    "title",
    "description",
    "characteristics",
    "media",
    "category",
    "completeness",
    "data_blocker",
    "opportunity",
    "system_check",
]
CheckerScoreBand = Literal["good", "warning", "critical", "not_checked"]

CHECKER_SYSTEM_CODES = {
    "wb_catalog_unavailable",
    "checker_catalog_unavailable",
    "analysis_failed",
    "analysis_not_available",
}
CHECKER_CONTENT_GROUPS = {
    "title",
    "description",
    "characteristics",
    "media",
    "category",
    "completeness",
}
CHECKER_ACTIVE_STATUSES = {"new", "in_progress", "postponed", "blocked"}
CHECKER_CLOSED_STATUSES = {"done", "resolved", "ignored"}
CHECKER_SEVERITY_WEIGHTS = {
    "critical": 25.0,
    "high": 15.0,
    "medium": 7.0,
    "low": 3.0,
    "info": 0.0,
}


def _checker_norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _checker_has_suggestion(issue: Any) -> bool:
    return bool(
        str(
            getattr(issue, "ai_suggested_value", None)
            or getattr(issue, "suggested_value", None)
            or ""
        ).strip()
    )


def _checker_has_fixed_or_suggested_value(issue: Any) -> bool:
    return bool(
        str(
            getattr(issue, "fixed_value", None)
            or getattr(issue, "ai_suggested_value", None)
            or getattr(issue, "suggested_value", None)
            or ""
        ).strip()
    )


def _checker_status_disabled_reason(issue: Any) -> str | None:
    status = _checker_norm(getattr(issue, "status", None))
    if status in CHECKER_CLOSED_STATUSES:
        return f"issue_status_{status}"
    return None


def _checker_has_nm_id(issue: Any) -> bool:
    try:
        return int(getattr(issue, "nm_id", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def _checker_canonical_apply_field_path(
    field_path: str | None, category: str | None = None
) -> str:
    raw = str(field_path or "").strip()
    lower = raw.lower()
    if not lower:
        cat = _checker_norm(category)
        if cat == "title":
            return "title"
        if cat in {"description", "seo"}:
            return "description"
        return ""
    if lower in {"subject", "subject_name", "category"}:
        return "subject_name"
    if lower.startswith("characteristics."):
        return f"characteristics.{raw.split('.', 1)[1].strip().lower()}"
    return lower


def checker_issue_group(issue: Any) -> CheckerIssueGroup:
    code = _checker_norm(getattr(issue, "issue_code", None))
    category = _checker_norm(getattr(issue, "category", None))
    field_name = _checker_norm(getattr(issue, "field_name", None))
    semantics = checker_bridge_semantics(issue)
    explicit_category_issue = category in {
        "category",
        "subject",
        "identity",
    } or field_name in {"subject_name", "subject", "category"}
    if semantics["impact_type"] == "data_blocker" and not explicit_category_issue:
        return "data_blocker"
    if code in CHECKER_SYSTEM_CODES or category in {
        "system",
        "sync_check",
        "catalog_check",
    }:
        return "system_check"
    if (
        category in {"title"}
        or field_name == "title"
        or code.startswith("title_")
        or code in {"no_title", "title_missing"}
    ):
        return "title"
    if (
        category in {"description", "seo"}
        or field_name == "description"
        or code.startswith("description_")
        or code in {"no_description", "description_missing"}
    ):
        return "description"
    if (
        category in {"media", "photo", "photos", "video"}
        or field_name.startswith(("photos", "photo", "videos", "video"))
        or any(token in code for token in ("photo", "photos", "video", "media"))
    ):
        return "media"
    if (
        category in {"characteristics", "characteristic", "attributes"}
        or field_name.startswith("characteristics.")
        or code.startswith(("wb_", "characteristic"))
    ):
        return "characteristics"
    if category in {"category", "subject", "identity"} or field_name in {
        "subject_name",
        "subject",
        "category",
    }:
        return "category"
    if any(token in code for token in ("missing", "empty", "completeness", "no_")):
        return "completeness"
    return "opportunity"


def checker_apply_disabled_reason(issue: Any) -> str | None:
    semantics = checker_bridge_semantics(issue)
    group = checker_issue_group(issue)
    if semantics["impact_type"] == "data_blocker" and group != "category":
        return "data_blocker_requires_source_fix"
    if (
        _checker_norm(getattr(issue, "issue_code", None)) in CHECKER_SYSTEM_CODES
        or group == "system_check"
    ):
        return "system_check_requires_recheck"
    if bool(getattr(issue, "requires_human_check", False)):
        return "human_check_required"
    if not _checker_has_fixed_or_suggested_value(issue):
        return "fixed_value_required"
    category = _checker_norm(getattr(issue, "category", None))
    canonical = _checker_canonical_apply_field_path(
        getattr(issue, "field_name", None), category
    )
    if category in {"media", "photos", "photo", "video"}:
        return f"unsupported_wb_apply_field:{getattr(issue, 'field_name', None) or getattr(issue, 'category', None) or getattr(issue, 'issue_code', None)}"
    if canonical in {"title", "description"} or canonical.startswith(
        "characteristics."
    ):
        return None
    return f"unsupported_wb_apply_field:{getattr(issue, 'field_name', None) or getattr(issue, 'category', None) or getattr(issue, 'issue_code', None)}"


def checker_preview_wb_disabled_reason(issue: Any) -> str | None:
    status_reason = _checker_status_disabled_reason(issue)
    if status_reason:
        return status_reason
    semantics = checker_bridge_semantics(issue)
    group = checker_issue_group(issue)
    if semantics["impact_type"] == "data_blocker" and group != "category":
        return "data_blocker_requires_source_fix"
    if (
        _checker_norm(getattr(issue, "issue_code", None)) in CHECKER_SYSTEM_CODES
        or group == "system_check"
    ):
        return "system_check_requires_recheck"
    if not _checker_has_fixed_or_suggested_value(issue):
        return "fixed_value_required"
    category = _checker_norm(getattr(issue, "category", None))
    canonical = _checker_canonical_apply_field_path(
        getattr(issue, "field_name", None), category
    )
    if category in {"media", "photos", "photo", "video"}:
        return f"unsupported_wb_apply_field:{getattr(issue, 'field_name', None) or getattr(issue, 'category', None) or getattr(issue, 'issue_code', None)}"
    if canonical in {"title", "description"} or canonical.startswith(
        "characteristics."
    ):
        return None
    return f"unsupported_wb_apply_field:{getattr(issue, 'field_name', None) or getattr(issue, 'category', None) or getattr(issue, 'issue_code', None)}"


def checker_action_capabilities(issue: Any) -> dict[str, Any]:
    semantics = checker_bridge_semantics(issue)
    impact_type = str(semantics["impact_type"])
    group = checker_issue_group(issue)
    status_reason = _checker_status_disabled_reason(issue)
    data_blocker_reason = (
        "data_blocker_requires_source_fix"
        if impact_type == "data_blocker" and group != "category"
        else None
    )
    system_reason = (
        "system_check_requires_recheck"
        if _checker_norm(getattr(issue, "issue_code", None)) in CHECKER_SYSTEM_CODES
        or group == "system_check"
        else None
    )
    has_value = _checker_has_fixed_or_suggested_value(issue)
    field_name = str(getattr(issue, "field_name", None) or "").strip()
    editable_draft_group = group in {
        "title",
        "description",
        "characteristics",
        "category",
        "completeness",
        "opportunity",
    }

    accept_local_reason = status_reason or data_blocker_reason or system_reason
    if accept_local_reason is None and bool(
        getattr(issue, "requires_human_check", False)
    ):
        accept_local_reason = "human_check_requires_manual_review"
    if accept_local_reason is None and not has_value:
        accept_local_reason = "fixed_value_required"
    if accept_local_reason is None and group == "media":
        accept_local_reason = "media_requires_dedicated_media_flow"

    mark_fixed_reason = status_reason or data_blocker_reason or system_reason

    save_draft_reason = status_reason or data_blocker_reason or system_reason
    if save_draft_reason is None and group == "media":
        save_draft_reason = "media_requires_dedicated_media_flow"
    if save_draft_reason is None and not editable_draft_group:
        save_draft_reason = "unsupported_local_draft_field"
    if save_draft_reason is None and not (field_name or has_value):
        save_draft_reason = "draft_field_required"

    preview_wb_reason = checker_preview_wb_disabled_reason(issue)
    apply_wb_reason = status_reason or checker_apply_disabled_reason(issue)

    recheck_reason = None if _checker_has_nm_id(issue) else "nm_id_required"

    return {
        "can_accept_local": accept_local_reason is None,
        "accept_local_disabled_reason": accept_local_reason,
        "can_mark_fixed": mark_fixed_reason is None,
        "mark_fixed_disabled_reason": mark_fixed_reason,
        "can_save_draft": save_draft_reason is None,
        "save_draft_disabled_reason": save_draft_reason,
        "can_preview_wb": preview_wb_reason is None,
        "preview_wb_disabled_reason": preview_wb_reason,
        "can_apply_to_wb": apply_wb_reason is None,
        "apply_wb_disabled_reason": apply_wb_reason,
        "can_recheck": recheck_reason is None,
        "recheck_disabled_reason": recheck_reason,
    }


def checker_score_band(issue: Any) -> CheckerScoreBand:
    code = _checker_norm(getattr(issue, "issue_code", None))
    severity = _checker_norm(getattr(issue, "severity", None))
    status = _checker_norm(getattr(issue, "status", None))
    if (
        code in {"not_analyzed", "analysis_not_available", "snapshot_missing"}
        or severity == "info"
    ):
        return "not_checked"
    if status in {"done", "resolved", "ignored"}:
        return "good"
    if severity in {"critical", "high"}:
        return "critical"
    if severity in {"medium", "low", "warning"}:
        return "warning"
    return "not_checked"


def checker_result_status(issue: Any) -> str:
    status = _checker_norm(getattr(issue, "status", None))
    if status == "ignored":
        return "not_enough_data"
    return "pending_data"


def checker_missing_data(issue: Any) -> list[str]:
    semantics = checker_bridge_semantics(issue)
    if semantics["impact_type"] != "data_blocker":
        return []
    code = _checker_norm(getattr(issue, "issue_code", None))
    if code in {"source_card_missing", "card_not_found", "card_unavailable"}:
        return ["product_card_source_missing"]
    if code in {"not_analyzed", "snapshot_missing"}:
        return ["card_quality_snapshot_missing"]
    if code in {"analysis_blocked", "analysis_failed"}:
        return ["card_quality_analysis_blocked"]
    return ["source_data_missing"]


def checker_contract_fields(issue: Any) -> dict[str, Any]:
    semantics = checker_bridge_semantics(issue)
    impact_type = str(semantics["impact_type"])
    trust_state = str(semantics["trust_state"])
    group = checker_issue_group(issue)
    if group == "category" and impact_type == "data_blocker":
        impact_type = "opportunity"
        trust_state = "opportunity"
    if impact_type not in {
        "opportunity",
        "data_blocker",
        "system_warning",
        "confirmed_loss",
    }:
        impact_type = "opportunity"
    if impact_type == "opportunity" and trust_state == "provisional":
        trust_state = "estimated"
    code = _checker_norm(getattr(issue, "issue_code", None))
    if code in CHECKER_SYSTEM_CODES and impact_type not in {
        "data_blocker",
        "confirmed_loss",
    }:
        impact_type = "system_warning"
        trust_state = "provisional"
    if impact_type == "data_blocker":
        trust_state = "blocked"
    if impact_type == "confirmed_loss":
        trust_state = "confirmed"
    apply_disabled = _checker_status_disabled_reason(
        issue
    ) or checker_apply_disabled_reason(issue)
    capabilities = checker_action_capabilities(issue)
    opportunity_score = None
    expected_opportunity_count = None
    if impact_type == "opportunity":
        raw_score = getattr(issue, "score_impact", None)
        if raw_score in (None, ""):
            raw_score = CHECKER_SEVERITY_WEIGHTS.get(
                _checker_norm(getattr(issue, "severity", None)), 0.0
            )
        opportunity_score = float(raw_score or 0.0)
        expected_opportunity_count = 1
    return {
        "impact_type": impact_type,
        "trust_state": trust_state,
        "issue_group": group,
        "can_fix_locally": impact_type in {"opportunity", "system_warning"}
        and bool(
            _checker_has_suggestion(issue)
            or str(getattr(issue, "recommended_fix", None) or "").strip()
            or group == "media"
        ),
        "can_apply_to_wb": capabilities["can_apply_to_wb"],
        "apply_disabled_reason": apply_disabled,
        "score_band": checker_score_band(issue),
        "opportunity_score": opportunity_score,
        "expected_opportunity_count": expected_opportunity_count,
        "recheck_available": capabilities["can_recheck"],
        "result_status": checker_result_status(issue),
        "missing_data": checker_missing_data(issue),
    }


class CardQualityAnalyzeRequest(BaseModel):
    account_id: int | None = None
    force: bool = False
    limit: int = Field(default=100, ge=1, le=1000)


class CardQualityProductAnalyzeRequest(BaseModel):
    account_id: int | None = None
    force: bool = False


class CardQualityAnalyzeResponse(BaseModel):
    status: Literal[
        "queued", "running", "completed", "partial", "failed", "already_running"
    ]
    run_id: int | None = None
    account_id: int
    run_type: str
    cards_total: int = 0
    eligible_total: int = 0
    cards_processed: int = 0
    cards_analyzed: int = 0
    cards_skipped_unchanged: int = 0
    cards_failed: int = 0
    cards_clean: int = 0
    cards_with_issues: int = 0
    issues_created: int = 0
    issues_resolved: int = 0
    message: str | None = None


class CardQualityProductRecheckResponse(BaseModel):
    run_id: int | None = None
    job_id: int | None = None
    nm_id: int
    status: Literal["queued", "running", "completed", "failed"]
    previous_score: int | None = None
    new_score: int | None = None
    previous_open_issue_count: int = 0
    new_open_issue_count: int | None = None
    resolved_issue_ids: list[int] = Field(default_factory=list)
    reopened_issue_ids: list[int] = Field(default_factory=list)
    result_status: Literal[
        "pending_data", "improved", "worse", "neutral", "not_enough_data"
    ]
    result_event_id: int | None = None
    action_center_updates: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None

    @model_validator(mode="after")
    def fill_job_id(self) -> "CardQualityProductRecheckResponse":
        if self.job_id is None:
            self.job_id = self.run_id
        if self.run_id is None:
            self.run_id = self.job_id
        return self


class CardQualityProductListItem(BaseModel):
    account_id: int
    nm_id: int
    title: str | None = None
    vendor_code: str | None = None
    brand: str | None = None
    subject_name: str | None = None
    thumbnail_url: str | None = None
    photos_count: int = 0
    video_count: int = 0
    source_updated_at: datetime | None = None
    updated_at: datetime | None = None
    score: int | None = None
    status: str = "not_analyzed"
    analyzed_at: datetime | None = None
    source_revision: str | None = None
    issue_count: int = 0
    actionable_issue_count: int = 0
    critical_issue_count: int = 0
    warning_issue_count: int = 0
    ai_issue_count: int = 0
    no_solution_ai_issue_count: int = 0
    top_issue_title: str | None = None
    top_issue_category: str | None = None
    top_issue_severity: str | None = None
    top_issue_source: str | None = None
    top_issue_recommended_fix: str | None = None
    analysis_available: bool = True


class CardQualityProductsPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    items: list[CardQualityProductListItem]
    summary: dict[str, Any] = Field(default_factory=dict)


class CardQualityRunRead(BaseModel):
    id: int
    account_id: int
    run_type: str
    status: str
    requested_by_user_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cards_total: int = 0
    eligible_total: int = 0
    cards_processed: int = 0
    cards_analyzed: int = 0
    cards_skipped_unchanged: int = 0
    cards_failed: int = 0
    cards_clean: int = 0
    cards_with_issues: int = 0
    issues_created: int = 0
    issues_resolved: int = 0
    source_revision: str | None = None
    cursor_json: dict[str, Any] = Field(default_factory=dict)
    last_processed_key: str | None = None
    heartbeat_at: datetime | None = None
    attempt: int = 1
    error_summary: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CardQualityRunsPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    items: list[CardQualityRunRead]


class CardQualityIssueRead(BaseModel):
    id: int
    issue_id: int | None = None
    account_id: int
    nm_id: int
    problem_instance_id: int | None = None
    action_id: str | None = None
    snapshot_id: int | None = None
    issue_code: str
    category: str
    severity: str
    title: str
    business_explanation: str | None = None
    recommended_fix: str | None = None
    field_name: str | None = None
    current_value: Any = None
    current_value_json: Any = None
    expected_value_json: Any = None
    suggested_value: str | None = None
    alternatives_json: list[Any] = Field(default_factory=list)
    charc_id: int | None = None
    allowed_values_json: list[Any] = Field(default_factory=list)
    error_details_json: list[Any] = Field(default_factory=list)
    ai_suggested_value: str | None = None
    ai_reason: str | None = None
    ai_alternatives_json: list[Any] = Field(default_factory=list)
    ai_confidence: float | None = None
    requires_human_check: bool = False
    ai_reason_short: str | None = None
    ai_reason_full: str | None = None
    ai_evidence_json: dict[str, Any] = Field(default_factory=dict)
    ai_used_sources_json: list[Any] = Field(default_factory=list)
    photo_evidence_json: list[Any] = Field(default_factory=list)
    source: str | None = None
    score_impact: int = 0
    confidence: float | None = None
    status: str
    fixed_value: str | None = None
    fixed_at: datetime | None = None
    fixed_by_user_id: int | None = None
    postponed_until: datetime | None = None
    status_reason: str | None = None
    fingerprint: str
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    resolved_at: datetime | None = None
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None
    impact_type: CheckerImpactType = "opportunity"
    trust_state: CheckerTrustState = "estimated"
    issue_group: CheckerIssueGroup = "opportunity"
    can_fix_locally: bool = False
    can_apply_to_wb: bool = False
    apply_disabled_reason: str | None = None
    can_accept_local: bool = False
    accept_local_disabled_reason: str | None = None
    can_mark_fixed: bool = False
    mark_fixed_disabled_reason: str | None = None
    can_save_draft: bool = False
    save_draft_disabled_reason: str | None = None
    can_preview_wb: bool = False
    preview_wb_disabled_reason: str | None = None
    apply_wb_disabled_reason: str | None = None
    can_recheck: bool = True
    recheck_disabled_reason: str | None = None
    score_band: CheckerScoreBand = "not_checked"
    opportunity_score: float | None = None
    expected_opportunity_count: int | None = None
    recheck_available: bool = True
    result_status: str = "pending_data"
    missing_data: list[str] = Field(default_factory=list)

    @field_validator(
        "alternatives_json",
        "allowed_values_json",
        "error_details_json",
        "ai_alternatives_json",
        "ai_used_sources_json",
        "photo_evidence_json",
        mode="before",
    )
    @classmethod
    def default_list_fields(cls, value: Any) -> list[Any]:
        return [] if value is None else value

    @field_validator("ai_evidence_json", mode="before")
    @classmethod
    def default_dict_fields(cls, value: Any) -> dict[str, Any]:
        return {} if value is None else value

    @field_validator("requires_human_check", mode="before")
    @classmethod
    def default_bool_fields(cls, value: Any) -> bool:
        return bool(value) if value is not None else False

    @field_validator("score_impact", mode="before")
    @classmethod
    def default_score_impact(cls, value: Any) -> int:
        return int(value or 0)

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "CardQualityIssueRead":
        contract = checker_contract_fields(self)
        capabilities = checker_action_capabilities(self)
        self.issue_id = self.id
        self.problem_instance_id = self.problem_instance_id
        self.action_id = self.action_id or f"card_quality:{self.id}"
        self.current_value = self.current_value_json
        self.impact_type = contract["impact_type"]
        self.trust_state = contract["trust_state"]
        self.issue_group = contract["issue_group"]
        self.can_fix_locally = contract["can_fix_locally"]
        self.can_apply_to_wb = contract["can_apply_to_wb"]
        self.apply_disabled_reason = contract["apply_disabled_reason"]
        self.can_accept_local = capabilities["can_accept_local"]
        self.accept_local_disabled_reason = capabilities["accept_local_disabled_reason"]
        self.can_mark_fixed = capabilities["can_mark_fixed"]
        self.mark_fixed_disabled_reason = capabilities["mark_fixed_disabled_reason"]
        self.can_save_draft = capabilities["can_save_draft"]
        self.save_draft_disabled_reason = capabilities["save_draft_disabled_reason"]
        self.can_preview_wb = capabilities["can_preview_wb"]
        self.preview_wb_disabled_reason = capabilities["preview_wb_disabled_reason"]
        self.can_apply_to_wb = capabilities["can_apply_to_wb"]
        self.apply_wb_disabled_reason = capabilities["apply_wb_disabled_reason"]
        self.can_recheck = capabilities["can_recheck"]
        self.recheck_disabled_reason = capabilities["recheck_disabled_reason"]
        self.score_band = contract["score_band"]
        self.opportunity_score = contract["opportunity_score"]
        self.expected_opportunity_count = contract["expected_opportunity_count"]
        self.recheck_available = self.can_recheck
        self.result_status = contract["result_status"]
        self.missing_data = contract["missing_data"]
        trust = classify_money_trust(
            value=self.opportunity_score
            if self.impact_type == "opportunity"
            else self.score_impact,
            value_type="count",
            confidence=self.trust_state,
            impact_type=self.impact_type,
            trust_state=self.trust_state,
            financial_final=self.impact_type == "confirmed_loss",
            source_module="checker",
            source_table="card_quality_issues",
            source_endpoint="GET /api/v1/portal/card-quality/issues",
            action_type=self.issue_code,
            payload={
                "category": self.category,
                "source": self.source,
                "trust_state": self.trust_state,
                "impact_type": self.impact_type,
            },
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = issue_evidence(
                code=self.issue_code,
                title=self.title,
                value=self.score_impact,
                source_table="card_quality_issues",
                source_endpoint="GET /api/v1/portal/card-quality/issues",
                account_id=self.account_id,
                row_count=1,
                severity=self.severity,
                next_screen_path=f"/checker/{self.nm_id}",
                next_screen_label="Открыть Checker",
                sample_rows=[
                    {
                        "id": self.id,
                        "nm_id": self.nm_id,
                        "issue_code": self.issue_code,
                        "category": self.category,
                        "issue_group": self.issue_group,
                        "field_name": self.field_name,
                        "current_value": self.current_value_json,
                        "expected_value": self.expected_value_json,
                        "score_impact": self.score_impact,
                        "impact_type": self.impact_type,
                        "trust_state": self.trust_state,
                    }
                ],
            )
            self.evidence_ledger.formula_human = (
                self.business_explanation
                or self.recommended_fix
                or f"Checker rule `{self.issue_code}` evaluated card content and created an issue."
            )
        self.evidence_ledger.impact_type = (
            self.impact_type
            if self.impact_type != "system_warning"
            else "system_warning"
        )
        self.evidence_ledger.confidence = (
            self.trust_state
            if self.trust_state
            in {"confirmed", "provisional", "estimated", "opportunity", "blocked"}
            else "provisional"
        )
        self.evidence_ledger.missing_data = list(
            dict.fromkeys([*self.evidence_ledger.missing_data, *self.missing_data])
        )
        if self.money_trust is None:
            self.money_trust = trust
        self.evidence_ledger.money_trust = self.money_trust
        return self

    @computed_field(return_type=str)
    @property
    def suggestion_kind(self) -> str:
        has_value = bool(
            str(self.ai_suggested_value or self.suggested_value or "").strip()
        )
        category = str(self.category or "").lower()
        field_name = str(self.field_name or "").lower()
        code = str(self.issue_code or "").lower()
        if not has_value:
            return "no_safe_fix"
        if (
            category in {"media", "photo", "photos", "video"}
            or field_name.startswith(("photos", "videos"))
            or code
            in {"media_no_images", "media_too_few_images", "media_no_video_info"}
        ):
            return "no_safe_fix"
        if field_name in {"title", "description"} or category in {
            "title",
            "description",
        }:
            return "draft_text" if self.requires_human_check else "exact_fix"
        return "candidate" if self.requires_human_check else "exact_fix"

    @computed_field(return_type=bool)
    @property
    def has_confirmed_suggestion(self) -> bool:
        return (
            bool(str(self.ai_suggested_value or self.suggested_value or "").strip())
            and not self.requires_human_check
            and self.suggestion_kind == "exact_fix"
        )

    @computed_field(return_type=bool)
    @property
    def is_user_actionable(self) -> bool:
        if str(self.category or "").lower() in {"media", "photo", "photos", "video"}:
            return True
        if self.suggestion_kind in {"exact_fix", "candidate", "draft_text"}:
            return True
        return bool(str(self.recommended_fix or "").strip())


class CardQualityIssuesPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    items: list[CardQualityIssueRead]
    summary: dict[str, Any] = Field(default_factory=dict)
    evidence_ledger: dict[str, EvidenceLedger] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "CardQualityIssuesPage":
        if not self.evidence_ledger:
            self.evidence_ledger = {
                "total": evidence_ledger(
                    value=self.total,
                    value_type="count",
                    confidence="provisional",
                    impact_type="data_blocker" if self.total else "system_warning",
                    formula_human="Counts card-quality issues after account/category/status filters.",
                    formula_code="portal.card_quality.issues.total",
                    formula_id="card_quality_issues_total",
                    label="Card quality issues",
                    unit="issues",
                    source_table="card_quality_issues",
                    source_endpoint="GET /api/v1/portal/card-quality/issues",
                    row_count=self.total,
                    sample_rows=[
                        {
                            "total": self.total,
                            "limit": self.limit,
                            "offset": self.offset,
                        }
                    ],
                    next_fix_action={
                        "label": "Открыть Checker",
                        "screen_path": "/checker",
                        "source_endpoint": "GET /api/v1/portal/card-quality/issues",
                        "action_type": "card_quality_fix",
                    },
                    recheck_rule="Analyze card quality again or update issue status, then refresh this endpoint.",
                )
            }
        return self


class CardQualityIssuesGrouped(BaseModel):
    status: Literal["ok"] = "ok"
    bucket: str = "actionable"
    critical: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    media: list[dict[str, Any]] = Field(default_factory=list)
    postponed: list[dict[str, Any]] = Field(default_factory=list)
    totals: dict[str, int] = Field(default_factory=dict)
    critical_count: int = 0
    warnings_count: int = 0
    media_count: int = 0
    postponed_count: int = 0


class CardQualityQueueProgress(BaseModel):
    total: int = 0
    pending: int = 0
    fixed: int = 0
    skipped: int = 0
    postponed: int = 0
    progress_percent: float = 0.0


class CardQualityIssueStatusUpdate(BaseModel):
    status: Literal[
        "new", "in_progress", "done", "postponed", "ignored", "blocked", "resolved"
    ]
    reason: str | None = None
    fixed_value: str | None = None
    postponed_until: datetime | None = None


class CardQualityIssueFixRequest(BaseModel):
    fixed_value: str | None = None
    apply_to_wb: bool = False
    confirm: bool = False
    reason: str | None = None


class CardQualityIssueDraftRequest(BaseModel):
    fixed_value: str | None = None
    reason: str | None = None


class CardQualityIssueMarkFixedRequest(BaseModel):
    fixed_value: str | None = None
    reason: str | None = None


class CardQualityIssueApplyPreview(BaseModel):
    issue_id: int
    nm_id: int
    field_path: str | None = None
    current_value: Any = None
    fixed_value: Any = None
    diff: dict[str, Any] = Field(default_factory=dict)
    can_apply_to_wb: bool = False
    requires_confirm: bool = True
    blocked_reason: str | None = None
    apply_disabled_reason: str | None = None
    wb_write_status: Literal["preview_ready", "blocked"] = "preview_ready"
    audit: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_apply_disabled_reason(self) -> "CardQualityIssueApplyPreview":
        if self.apply_disabled_reason is None and self.blocked_reason is not None:
            self.apply_disabled_reason = self.blocked_reason
        if self.blocked_reason is None and self.apply_disabled_reason is not None:
            self.blocked_reason = self.apply_disabled_reason
        return self


class CardQualityIssueFixResponse(BaseModel):
    status: Literal[
        "fixed_local",
        "confirmation_required",
        "submitted_to_wb",
        "applied_to_wb",
        "blocked",
        "wb_submit_failed",
    ]
    issue: CardQualityIssueRead
    preview: CardQualityIssueApplyPreview | None = None
    apply_result: dict[str, Any] | None = None
    wb_write_status: Literal[
        "not_requested",
        "confirmation_required",
        "submitted_waiting_validation",
        "blocked",
        "failed",
    ] = "not_requested"
    message: str | None = None


class CardQualityFixedFileStatus(BaseModel):
    has_fixed_file: bool
    total: int = 0
    total_cards: int = 0
    total_brands: int = 0
    total_subjects: int = 0
    total_characteristics: int = 0
    last_updated_at: datetime | None = None


class CardQualityFixedFileEntryRead(BaseModel):
    id: int
    account_id: int
    nm_id: int
    brand: str | None = None
    subject_name: str | None = None
    char_name: str
    fixed_value: str
    created_by_user_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CardQualityFixedFileEntriesPage(BaseModel):
    status: Literal["ok"] = "ok"
    total: int
    limit: int
    offset: int
    summary: CardQualityFixedFileStatus | None = None
    items: list[CardQualityFixedFileEntryRead]


class CardQualityFixedFileEntryMutation(BaseModel):
    nm_id: int | None = None
    brand: str | None = None
    subject_name: str | None = None
    char_name: str | None = None
    fixed_value: str | None = None


class CardQualityFixedFileUploadResponse(BaseModel):
    status: Literal["ok"] = "ok"
    upserted: int
    message: str
    total: int | None = None
