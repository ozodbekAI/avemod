from __future__ import annotations

from app.schemas.claims import CaseDetailOut, CaseListItemOut
from app.schemas.operator import (
    ActionStatus,
    ActionType,
    CaseType,
    DiagnosisOut,
    DiagnosisType,
    DraftOut,
    DraftType,
    EvidenceOut,
    ExternalStatus,
    GuidedFixOut,
    ModuleHealthOut,
    OperatorModule,
    OperatorOverviewOut,
    Priority,
    Product360Out,
    ProfitDoctorOut,
    ResultEventOut,
    SignalOut,
    SignalType,
    TrustState,
    UnifiedActionOut,
)
from app.schemas.reputation import ReputationInboxOut, ReputationItemOut


def test_operator_schema_enums_serialize_as_frontend_strings() -> None:
    action = UnifiedActionOut(
        id="action-1",
        action_type=ActionType.CARD_QUALITY_FIX,
        module=OperatorModule.CHECKER,
        status=ActionStatus.BLOCKED,
        priority=Priority.P1,
        title="Fix card",
        trust_state=TrustState.BLOCKED,
    )

    payload = action.model_dump(mode="json")

    assert payload["action_type"] == "card_quality_fix"
    assert payload["module"] == "checker"
    assert payload["status"] == "blocked"
    assert payload["priority"] == "P1"
    assert payload["trust_state"] == "blocked"


def test_operator_base_scrubs_secret_like_payload_fields() -> None:
    signal = SignalOut(
        signal_type=SignalType.PROFIT,
        title="Profit signal",
        data={
            "safe": True,
            "token": "must-not-leak",
            "nested": {
                "api_key": "must-not-leak",
                "value": 10,
            },
        },
    )

    payload = signal.model_dump(mode="json")

    assert payload["data"] == {"safe": True, "nested": {"value": 10}}


def test_operator_overview_and_product360_allow_unavailable_modules() -> None:
    health = ModuleHealthOut(
        module=OperatorModule.REPUTATION,
        status="not_configured",
        trust_state=TrustState.UNAVAILABLE,
        unavailable_sources=["reputation"],
    )
    diagnosis = DiagnosisOut(
        diagnosis_type=DiagnosisType.MODULE_UNAVAILABLE,
        module=OperatorModule.REPUTATION,
        title="Reputation is unavailable",
        trust_state=TrustState.UNAVAILABLE,
    )
    product = Product360Out(
        status="ok",
        account_id=1,
        nm_id=123,
        trust_state=TrustState.OPERATIONAL,
        module_health=[health],
        diagnoses=[diagnosis],
        unavailable_sources=["reputation"],
    )
    overview = OperatorOverviewOut(
        status="ok",
        account_id=1,
        trust_state=TrustState.OPERATIONAL,
        module_health=[health],
        products=[product],
        unavailable_sources=["reputation"],
    )

    payload = overview.model_dump(mode="json")

    assert payload["module_health"][0]["module"] == "reputation"
    assert payload["products"][0]["nm_id"] == 123
    assert payload["unavailable_sources"] == ["reputation"]


def test_profit_doctor_guided_fix_and_result_tracking_shapes() -> None:
    guided_fix = GuidedFixOut(
        title="Confirm claim draft",
        confirm_required=True,
        audit_required=True,
    )
    action = UnifiedActionOut(
        id="claims:case-1",
        action_type=ActionType.DRAFT_CLAIM,
        module=OperatorModule.CLAIMS,
        title="Prepare appeal",
        guided_fix=guided_fix,
        can_preview=True,
        can_confirm=False,
        marketplace_change=True,
    )
    result = ResultEventOut(
        module=OperatorModule.CLAIMS,
        event_type="claim_preview_created",
        external_status=ExternalStatus.DRAFT_READY,
        action_id=action.id,
        success=True,
    )
    doctor = ProfitDoctorOut(
        status="ok",
        trust_state=TrustState.PROVISIONAL,
        actions=[action],
        data={"result_event": result.model_dump(mode="json")},
    )

    payload = doctor.model_dump(mode="json")

    assert payload["actions"][0]["guided_fix"]["confirm_required"] is True
    assert payload["actions"][0]["marketplace_change"] is True
    assert payload["data"]["result_event"]["external_status"] == "draft_ready"


def test_reputation_contracts_support_drafts_and_actions() -> None:
    draft = DraftOut(
        draft_type=DraftType.REVIEW_REPLY,
        external_status=ExternalStatus.DRAFT_READY,
        text="Спасибо за отзыв",
    )
    item = ReputationItemOut(
        id="feedback-1",
        item_type="feedback",
        account_id=1,
        nm_id=123,
        rating=4,
        text="Good",
        needs_reply=True,
        draft=draft,
    )
    inbox = ReputationInboxOut(
        status="ok",
        account_id=1,
        total=1,
        items=[item],
        trust_state=TrustState.OPERATIONAL,
    )

    payload = inbox.model_dump(mode="json")

    assert payload["module"] == "reputation"
    assert payload["items"][0]["draft"]["draft_type"] == "review_reply"
    assert payload["items"][0]["needs_reply"] is True


def test_claims_contracts_support_evidence_drafts_and_events() -> None:
    case = CaseListItemOut(
        id="case-1",
        case_type=CaseType.DEFECT,
        account_id=1,
        title="Defect return",
        evidence_count=1,
        draft_count=1,
    )
    detail = CaseDetailOut(
        **case.model_dump(),
        evidence=[
            EvidenceOut(
                id="evidence-1",
                case_id=case.id,
                evidence_type="finance_trace",
                title="Finance trace",
            )
        ],
        drafts=[
            DraftOut(
                id="draft-1",
                draft_type=DraftType.SUPPORT_APPEAL,
                external_status=ExternalStatus.DRAFT_READY,
                case_id=case.id,
            )
        ],
        result_events=[
            ResultEventOut(
                module=OperatorModule.CLAIMS,
                event_type="draft_created",
                case_id=case.id,
                external_status=ExternalStatus.DRAFT_READY,
            )
        ],
    )

    payload = detail.model_dump(mode="json")

    assert payload["case_type"] == "defect"
    assert payload["module"] == "claims"
    assert payload["evidence"][0]["evidence_type"] == "finance_trace"
    assert payload["drafts"][0]["draft_type"] == "support_appeal"
    assert payload["result_events"][0]["external_status"] == "draft_ready"
