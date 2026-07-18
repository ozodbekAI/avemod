from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.money_trust import MoneyTrustInfo, classify_money_trust


EvidenceValueType = Literal[
    "money",
    "number",
    "percent",
    "count",
    "days",
    "boolean",
    "date",
    "status",
    "text",
]
EvidenceConfidence = Literal[
    "confirmed", "provisional", "estimated", "opportunity", "test_only", "blocked"
]
EvidenceImpactType = Literal[
    "confirmed_loss",
    "probable_loss",
    "blocked_cash",
    "lost_sales_risk",
    "opportunity",
    "data_blocker",
    "system_warning",
]

SENSITIVE_FIELD_TOKENS = {
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
}


class EvidenceDateRange(BaseModel):
    from_: date | str | None = Field(default=None, alias="from")
    to: date | str | None = None
    start: date | str | None = None
    end: date | str | None = None
    date_from: date | str | None = None
    date_to: date | str | None = None

    model_config = {"populate_by_name": True}


class EvidenceInputFact(BaseModel):
    label: str
    metric_code: str | None = None
    value: Any = None
    unit: str | None = None
    trust_state: EvidenceConfidence = "provisional"
    source: str | None = None
    source_table: str | None = None
    source_endpoint: str | None = None
    date_range: EvidenceDateRange | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    row_count: int = 0
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceSourceReference(BaseModel):
    source_table: str | None = None
    source_endpoint: str | None = None
    date_range: EvidenceDateRange | None = None
    row_count: int | None = None
    sync_run_id: str | int | None = None
    table: str | None = None
    primary_key: str | int | None = None
    id: str | int | None = None
    raw_snapshot_id: str | int | None = None
    wb_endpoint: str | None = None
    loaded_at: datetime | str | None = None

    @model_validator(mode="after")
    def fill_explicit_contract_fields(self) -> "EvidenceSourceReference":
        if self.source_table is None and self.table is not None:
            self.source_table = self.table
        if self.table is None and self.source_table is not None:
            self.table = self.source_table
        if self.source_endpoint is None and self.wb_endpoint is not None:
            self.source_endpoint = self.wb_endpoint
        if self.wb_endpoint is None and self.source_endpoint is not None:
            self.wb_endpoint = self.source_endpoint
        return self


class EvidenceFixAction(BaseModel):
    label: str
    screen_path: str | None = None
    source_endpoint: str | None = None
    action_type: str | None = None


class EvidenceLedger(BaseModel):
    value: Any = None
    value_type: EvidenceValueType = "text"
    confidence: EvidenceConfidence = "provisional"
    impact_type: EvidenceImpactType = "system_warning"
    formula_human: str = ""
    formula_code: str | None = None
    formula_id: str | None = None
    input_facts: list[EvidenceInputFact] = Field(default_factory=list)
    source_references: list[EvidenceSourceReference] = Field(default_factory=list)
    trust_notes: list[str] = Field(default_factory=list)
    missing_data: list[str] = Field(default_factory=list)
    next_fix_action: EvidenceFixAction | None = None
    recheck_rule: str | None = None
    recheck_rule_human: str | None = None
    calculation_warnings: list[str] = Field(default_factory=list)
    money_trust: MoneyTrustInfo | None = None
    is_synthetic: bool = False

    @model_validator(mode="after")
    def fill_recheck_alias(self) -> "EvidenceLedger":
        if self.recheck_rule_human is None and self.recheck_rule is not None:
            self.recheck_rule_human = self.recheck_rule
        if self.recheck_rule is None and self.recheck_rule_human is not None:
            self.recheck_rule = self.recheck_rule_human
        return self


def safe_sample_row(
    row: dict[str, Any] | None, *, max_fields: int = 12
) -> dict[str, Any]:
    if not row:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if len(cleaned) >= max_fields:
            break
        lower_key = str(key).lower()
        if any(token in lower_key for token in SENSITIVE_FIELD_TOKENS):
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            cleaned[str(key)] = value if not isinstance(value, str) else value[:240]
        elif isinstance(value, (date, datetime)):
            cleaned[str(key)] = value.isoformat()
        else:
            cleaned[str(key)] = str(value)[:240]
    return cleaned


def evidence_ledger(
    *,
    value: Any = None,
    value_type: EvidenceValueType = "text",
    confidence: EvidenceConfidence = "provisional",
    impact_type: EvidenceImpactType = "system_warning",
    formula_human: str = "",
    formula_code: str | None = None,
    formula_id: str | None = None,
    label: str = "Значение",
    unit: str | None = None,
    source_table: str | None = None,
    source_endpoint: str | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    filters: dict[str, Any] | None = None,
    row_count: int = 0,
    sample_rows: list[dict[str, Any]] | None = None,
    metric_code: str | None = None,
    trust_state: EvidenceConfidence | None = None,
    source: str | None = None,
    source_references: list[EvidenceSourceReference | dict[str, Any]] | None = None,
    trust_notes: list[str] | None = None,
    missing_data: list[str] | None = None,
    next_fix_action: EvidenceFixAction | dict[str, Any] | None = None,
    recheck_rule: str | None = None,
    recheck_rule_human: str | None = None,
    calculation_warnings: list[str] | None = None,
    money_trust: MoneyTrustInfo | None = None,
    is_synthetic: bool = False,
) -> EvidenceLedger:
    samples = [safe_sample_row(row) for row in (sample_rows or [])[:3]]
    if not samples and value is not None:
        samples = [safe_sample_row({"value": value, "unit": unit})]
    refs = [
        ref
        if isinstance(ref, EvidenceSourceReference)
        else EvidenceSourceReference.model_validate(ref)
        for ref in (source_references or [])
    ]
    if source_table and not refs:
        refs = [
            EvidenceSourceReference(
                source_table=source_table,
                source_endpoint=source_endpoint,
                date_range=EvidenceDateRange(date_from=date_from, date_to=date_to),
                row_count=max(0, int(row_count or 0)),
            )
        ]
    fix_action = (
        next_fix_action
        if isinstance(next_fix_action, EvidenceFixAction) or next_fix_action is None
        else EvidenceFixAction.model_validate(next_fix_action)
    )
    return EvidenceLedger(
        value=value,
        value_type=value_type,
        confidence=confidence,
        impact_type=impact_type,
        formula_human=formula_human or label,
        formula_code=formula_code,
        formula_id=formula_id,
        input_facts=[
            EvidenceInputFact(
                label=label,
                metric_code=metric_code,
                value=value,
                unit=unit,
                trust_state=trust_state or confidence,
                source=source or source_table or source_endpoint,
                source_table=source_table,
                source_endpoint=source_endpoint,
                date_range=EvidenceDateRange(date_from=date_from, date_to=date_to),
                filters=filters or {},
                row_count=max(0, int(row_count or 0)),
                sample_rows=samples,
            )
        ],
        source_references=refs,
        trust_notes=trust_notes or [],
        missing_data=missing_data or [],
        next_fix_action=fix_action,
        recheck_rule=recheck_rule,
        recheck_rule_human=recheck_rule_human or recheck_rule,
        calculation_warnings=calculation_warnings or [],
        money_trust=money_trust
        or classify_money_trust(
            value=value,
            value_type=value_type,
            confidence=confidence,
            impact_type=impact_type,
            source_table=source_table,
            source_endpoint=source_endpoint,
        ),
        is_synthetic=is_synthetic,
    )


def confidence_from_trust_state(
    value: str | None, *, final: bool | None = None
) -> EvidenceConfidence:
    normalized = str(value or "").strip().lower()
    if normalized in {"trusted", "confirmed", "final"} or final is True:
        return "confirmed"
    if normalized in {"blocked", "data_blocked"}:
        return "blocked"
    if normalized in {"test_only", "test"}:
        return "test_only"
    if normalized in {"estimated", "estimate"}:
        return "estimated"
    if normalized in {"opportunity", "chance"}:
        return "opportunity"
    return "provisional"
