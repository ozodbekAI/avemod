from __future__ import annotations

from dataclasses import dataclass

from app.schemas.operator import CaseType, DraftType, Priority


@dataclass(frozen=True)
class ClaimCaseTemplate:
    case_type: CaseType
    required_evidence_types: tuple[str, ...]
    draft_type: DraftType
    recommended_guided_fix: dict[str, str]
    default_priority: Priority
    requires_external_ticket: bool = True


CLAIM_CASE_TEMPLATES: dict[CaseType, ClaimCaseTemplate] = {
    CaseType.DEFECT: ClaimCaseTemplate(
        case_type=CaseType.DEFECT,
        required_evidence_types=(
            "return_record",
            "product_identity",
            "photo_or_video",
            "finance_trace",
        ),
        draft_type=DraftType.SUPPORT_APPEAL,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Review defect claim",
        },
        default_priority=Priority.P1,
    ),
    CaseType.SUPPLY_DISCREPANCY: ClaimCaseTemplate(
        case_type=CaseType.SUPPLY_DISCREPANCY,
        required_evidence_types=(
            "supply_document",
            "acceptance_report",
            "goods_identity",
            "warehouse_response",
        ),
        draft_type=DraftType.CLAIM_TEXT,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Review supply discrepancy",
        },
        default_priority=Priority.P1,
    ),
    CaseType.MISSING_GOODS: ClaimCaseTemplate(
        case_type=CaseType.MISSING_GOODS,
        required_evidence_types=(
            "supply_document",
            "barcode_or_srid",
            "warehouse_report",
            "finance_trace",
        ),
        draft_type=DraftType.CLAIM_TEXT,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Review missing goods",
        },
        default_priority=Priority.P1,
    ),
    CaseType.REPORT_ANOMALY: ClaimCaseTemplate(
        case_type=CaseType.REPORT_ANOMALY,
        required_evidence_types=(
            "finance_report_row",
            "expected_calculation",
            "period_context",
        ),
        draft_type=DraftType.OBJECTION,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Review report anomaly",
        },
        default_priority=Priority.P2,
    ),
    CaseType.COMPENSATION_UNDERPAYMENT: ClaimCaseTemplate(
        case_type=CaseType.COMPENSATION_UNDERPAYMENT,
        required_evidence_types=(
            "compensation_match",
            "finance_trace",
            "return_or_order_identity",
        ),
        draft_type=DraftType.SUPPORT_APPEAL,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Review compensation",
        },
        default_priority=Priority.P1,
    ),
    CaseType.REPEAT_CLAIM: ClaimCaseTemplate(
        case_type=CaseType.REPEAT_CLAIM,
        required_evidence_types=(
            "original_ticket",
            "support_response",
            "repeat_reason",
            "updated_evidence",
        ),
        draft_type=DraftType.CLAIM_TEXT,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Prepare repeat claim",
        },
        default_priority=Priority.P2,
    ),
    CaseType.PRETRIAL: ClaimCaseTemplate(
        case_type=CaseType.PRETRIAL,
        required_evidence_types=(
            "case_history",
            "support_tickets",
            "finance_trace",
            "legal_review",
        ),
        draft_type=DraftType.PRETRIAL,
        recommended_guided_fix={
            "route_key": "claims",
            "method": "open_case",
            "label": "Prepare pretrial package",
        },
        default_priority=Priority.P0,
    ),
}


def get_claim_case_template(case_type: CaseType | str) -> ClaimCaseTemplate:
    return CLAIM_CASE_TEMPLATES[CaseType(str(case_type))]


def claim_case_template_metadata(case_type: CaseType | str) -> dict:
    template = get_claim_case_template(case_type)
    return {
        "case_type": template.case_type.value,
        "required_evidence_types": list(template.required_evidence_types),
        "draft_type": template.draft_type.value,
        "recommended_guided_fix": dict(template.recommended_guided_fix),
        "default_priority": template.default_priority.value,
        "requires_external_ticket": template.requires_external_ticket,
    }


FUTURE_CLAIM_STAGE_LABELS: dict[CaseType, str] = {
    CaseType.SUPPLY_DISCREPANCY: "claims_supply_discrepancies",
    CaseType.MISSING_GOODS: "claims_missing_goods",
    CaseType.COMPENSATION_UNDERPAYMENT: "claims_compensation_underpayments",
    CaseType.REPEAT_CLAIM: "claims_repeat_claims",
    CaseType.PRETRIAL: "claims_pretrial",
}

FUTURE_CLAIM_MESSAGES_RU: dict[CaseType, str] = {
    CaseType.SUPPLY_DISCREPANCY: "Поиск расхождений по поставкам будет добавлен в следующем этапе.",
    CaseType.MISSING_GOODS: "Поиск недостающих товаров будет добавлен в следующем этапе.",
    CaseType.COMPENSATION_UNDERPAYMENT: "Поиск недоплат по компенсациям будет добавлен в следующем этапе.",
    CaseType.REPEAT_CLAIM: "Повторные претензии будут добавлены в следующем этапе.",
    CaseType.PRETRIAL: "Досудебные кейсы будут добавлены в следующем этапе.",
}


def not_implemented_detection(*, account_id: int, case_type: CaseType | str) -> dict:
    normalized = CaseType(str(case_type))
    next_stage = FUTURE_CLAIM_STAGE_LABELS.get(normalized, f"claims_{normalized.value}")
    return {
        "status": "not_implemented",
        "case_type": normalized.value,
        "account_id": account_id,
        "items": [],
        "item_count": 0,
        "message": FUTURE_CLAIM_MESSAGES_RU.get(
            normalized, "Этот тип претензий будет добавлен в следующем этапе."
        ),
        "next_stage": next_stage,
        "trust_state": "unavailable",
        "unavailable_sources": [],
        "template": claim_case_template_metadata(normalized),
    }
