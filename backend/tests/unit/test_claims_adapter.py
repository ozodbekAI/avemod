from __future__ import annotations

import json
from pathlib import Path
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.schemas.claims import ClaimsDraftMutationOut, ClaimsProofCheckOut, ClaimsSubmitRequest
from app.schemas.operator import CaseType, DraftType, EvidenceOut
from app.services.claims_adapter import ClaimsDefectAdapter
from app.services.claims_case_templates import CLAIM_CASE_TEMPLATES


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "claims"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _candidate() -> dict:
    return {
        "id": "return-1",
        "nm_id": 1001,
        "vendor_code": "A-1",
        "order_id": "order-1",
        "srid": "srid-1",
        "action_type": "defect_claim_candidate",
        "title": "Defect compensation candidate",
        "reason": "Return reason indicates a defect and compensation may be available.",
        "priority": "P1",
        "estimated_amount": 1500.0,
        "buyer_email": "buyer@example.test",
        "token": "must-not-leak",
    }


def _backenddefect_case_candidate() -> dict:
    return _fixture("backenddefect_case_candidate.json")


class _SupplyRowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def __iter__(self):
        return iter(self._rows)


class _SupplySession:
    def __init__(self, rows):
        self.rows = rows

    async def execute(self, stmt):
        return _SupplyRowsResult(self.rows)


@pytest.mark.asyncio
async def test_claims_adapter_detects_mock_candidates_without_secrets() -> None:
    adapter = ClaimsDefectAdapter(Settings(), mock_candidates=[_candidate()])

    result = await adapter.detect_defect_candidates(1, None)

    assert result["status"] == "ok"
    assert result["items"][0]["nm_id"] == 1001
    assert result["items"][0]["action_type"] == "defect_claim_candidate"
    assert "must-not-leak" not in str(result)
    assert "buyer@example" not in str(result)


@pytest.mark.asyncio
async def test_claims_adapter_normalizes_backenddefect_case_payload_without_private_data() -> None:
    adapter = ClaimsDefectAdapter(Settings(), mock_candidates=[_backenddefect_case_candidate()])

    result = await adapter.detect_defect_candidates(1, None)

    assert result["status"] == "ok"
    candidate = result["items"][0]
    assert candidate["case_type"] == "defect"
    assert candidate["action_type"] == "defect_claim_candidate"
    assert candidate["source_id"] == "defect_case:DEF-2026-0042"
    assert candidate["estimated_amount"] == 2345.67
    assert candidate["nm_id"] == 1001
    assert candidate["order_id"] == "order-42"
    assert candidate["srid"] == "srid-42"
    assert candidate["finance_trace"]["candidate_row_count"] == 3
    assert candidate["evidence_snapshot"]["matched_return_record"]["barcode"] == "barcode-42"
    assert "must-not-leak" not in str(result)
    assert "buyer@example" not in str(result)
    assert "+7999" not in str(result)
    assert "Private Person" not in str(result)
    assert "address" not in str(result).lower()


@pytest.mark.asyncio
async def test_claims_adapter_falls_back_to_backenddefect_cases_endpoint() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(
            claims_enabled=True,
            claims_base_url="http://claims.internal/api",
            claims_internal_token="secret-token",
        )
    )
    response = httpx.Response(
        status_code=404,
        request=httpx.Request("GET", "http://claims.internal/api/defect-candidates"),
    )
    adapter._request = AsyncMock(
        side_effect=[
            httpx.HTTPStatusError("not found", request=response.request, response=response),
            [_backenddefect_case_candidate()],
        ]
    )

    result = await adapter.detect_defect_candidates(1, None, nm_id=1001)

    assert result["status"] == "ok"
    assert result["items"][0]["source_id"] == "defect_case:DEF-2026-0042"
    assert result["items"][0]["estimated_amount"] == 2345.67
    assert "secret-token" not in str(result)
    assert adapter._request.await_args_list[0].args[:2] == ("GET", "/defect-candidates")
    assert adapter._request.await_args_list[1].args[:2] == ("GET", "/cases")


@pytest.mark.asyncio
async def test_claims_adapter_configured_service_unavailable_degrades_safely() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(
            claims_enabled=True,
            claims_base_url="http://claims.internal/api",
        )
    )
    adapter._request = AsyncMock(side_effect=httpx.ConnectError("connection failed"))

    result = await adapter.detect_defect_candidates(1, None)

    assert result["status"] == "unavailable"
    assert result["items"] == []
    assert result["unavailable_sources"] == ["claims"]
    assert result["trust_state"] == "unavailable"


@pytest.mark.asyncio
async def test_claims_adapter_exposes_profit_doctor_signals_and_actions() -> None:
    adapter = ClaimsDefectAdapter(Settings(), mock_candidates=[_candidate()])
    account = SimpleNamespace(id=1, external_account_id=None, name="main")

    signals = await adapter.profit_doctor_signals(account_id=1)
    actions, unavailable = await adapter.claims_actions(account, limit=10)

    assert signals[0]["title"] == "Defect compensation candidate"
    assert signals[0]["next_step"].startswith("Open Claims Factory")
    assert unavailable is None
    assert actions[0].source_module == "claims"
    assert actions[0].action_type == "defect_claim_candidate"
    assert actions[0].guided_fix["method"] == "create_claim_case_from_signal"
    assert actions[0].guided_fix["legacy_method"] == "open_case"
    assert actions[0].guided_fix["endpoint"] == "/api/v1/portal/cases/from-signal"
    assert actions[0].can_update is False


@pytest.mark.asyncio
async def test_backenddefect_candidates_appear_in_profit_doctor_and_action_center() -> None:
    adapter = ClaimsDefectAdapter(Settings(), mock_candidates=[_backenddefect_case_candidate()])
    account = SimpleNamespace(id=1, external_account_id=None, name="main")

    signals = await adapter.profit_doctor_signals(account_id=1)
    actions, unavailable = await adapter.claims_actions(account, limit=10)

    assert unavailable is None
    assert signals[0]["source_id"] == "defect_case:DEF-2026-0042"
    assert signals[0]["diagnosis_type"] == "claim_opportunity"
    assert actions[0].source_module == "claims"
    assert actions[0].source_id == "defect_case:DEF-2026-0042"
    assert actions[0].guided_fix["payload"]["source_id"] == "defect_case:DEF-2026-0042"
    assert actions[0].can_update is False
    assert actions[0].can_update_status is False


@pytest.mark.asyncio
async def test_claims_adapter_creates_case_evidence_draft_and_proof_from_backenddefect_signal() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    calls: dict[str, object] = {}

    async def _fake_create_case(session, **kwargs):
        calls["create_case"] = kwargs
        return SimpleNamespace(id="10", status="candidate")

    async def _fake_attach_evidence(session, **kwargs):
        calls["attach_evidence"] = kwargs
        return EvidenceOut(
            id="e1",
            case_id=str(kwargs["case_id"]),
            evidence_type=kwargs["payload"].evidence_type,
            title=kwargs["payload"].title,
            source_id=kwargs["payload"].source_id,
            data=kwargs["payload"].payload,
        )

    async def _fake_generate_draft(session, **kwargs):
        calls["generate_draft"] = kwargs
        return ClaimsDraftMutationOut(
            account_id=kwargs["account_id"],
            case_id=str(kwargs["case_id"]),
            draft={
                "id": "d1",
                "draft_type": "support_appeal",
                "case_id": str(kwargs["case_id"]),
                "text": "Draft text",
                "requires_confirmation": True,
            },
        )

    async def _fake_proof_check(session, **kwargs):
        calls["proof_check"] = kwargs
        return ClaimsProofCheckOut(
            account_id=kwargs["account_id"],
            case_id=str(kwargs["case_id"]),
            passed=True,
            data={"evidence_count": 1, "draft_count": 1},
        )

    adapter.factory.create_case = _fake_create_case
    adapter.factory.attach_evidence = _fake_attach_evidence
    adapter.factory.generate_draft = _fake_generate_draft
    adapter.factory.proof_check = _fake_proof_check

    signal = _backenddefect_case_candidate()
    case = await adapter.create_defect_case_from_signal(SimpleNamespace(), account_id=1, signal=signal, created_by=2)
    evidence = await adapter.create_evidence_from_signal(SimpleNamespace(), account_id=1, case_id=10, signal=signal, created_by=2)
    draft = await adapter.generate_defect_claim_draft(SimpleNamespace(), account_id=1, case_id=10, created_by=2)
    proof = await adapter.proof_check(SimpleNamespace(), account_id=1, case_id=10)

    assert case.id == "10"
    create_payload = calls["create_case"]["payload"]
    assert create_payload.case_type == CaseType.DEFECT
    assert create_payload.source_id == "defect_case:DEF-2026-0042"
    assert create_payload.payload["adapter"] == "claims_defect"
    assert create_payload.payload["source_pattern"] == "backenddefect_reference"
    assert evidence.evidence_type == "finance_trace"
    assert evidence.source_id == "claims:evidence:defect_case:DEF-2026-0042"
    assert evidence.data["external_operation"] is False
    assert evidence.data["finance_trace"]["candidate_row_count"] == 3
    assert evidence.data["evidence_snapshot"]["matched_return_record"]["barcode"] == "barcode-42"
    dumped_evidence = str(evidence.model_dump(mode="json"))
    assert "must-not-leak" not in dumped_evidence
    assert "buyer@example" not in dumped_evidence
    assert "Private Person" not in dumped_evidence
    assert draft.draft is not None
    assert draft.draft.draft_type == DraftType.SUPPORT_APPEAL
    assert draft.draft.requires_confirmation is True
    assert proof.passed is True
    assert calls["generate_draft"]["payload"].draft_type == DraftType.SUPPORT_APPEAL


@pytest.mark.asyncio
async def test_claims_adapter_product_360_filters_candidates_by_nm_id() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(),
        mock_candidates=[
            _candidate(),
            {**_candidate(), "id": "return-2", "nm_id": 2002, "estimated_amount": 500.0},
            _backenddefect_case_candidate(),
        ],
    )

    result = await adapter.product_360(account_id=1, nm_id=1001)

    assert result["status"] == "ok"
    assert result["open_cases_count"] == 2
    assert result["potential_compensation_amount"] == 3845.67
    assert result["items"][0]["nm_id"] == 1001
    assert any(item["source_id"] == "defect_case:DEF-2026-0042" for item in result["items"])


@pytest.mark.asyncio
async def test_claims_adapter_detects_report_anomaly_from_data_quality_issue() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    adapter.data_quality.list_issues = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                SimpleNamespace(
                    id=77,
                    account_id=1,
                    domain="finance",
                    severity="error",
                    code="finance_reconciliation_mismatch",
                    entity_key="srid-1",
                    entity_type="srid",
                    entity_id=None,
                    sku_id=2001,
                    nm_id=1001,
                    source_table="mart_finance_reconciliation",
                    message="Finance report row does not match sale row.",
                    payload={
                        "vendorCode": "A-1",
                        "affectedRevenue": 2500.5,
                        "dateFrom": "2026-06-01",
                        "dateTo": "2026-06-10",
                    },
                    detected_at=datetime(2026, 6, 11),
                    resolved_at=None,
                    effective_financial_final_blocker=True,
                )
            ]
        )
    )

    result = await adapter.detect_report_anomaly_candidates(
        1,
        (date(2026, 6, 1), date(2026, 6, 10)),
        nm_id=1001,
        session=SimpleNamespace(),
    )

    assert result["status"] == "ok"
    candidate = result["items"][0]
    assert candidate["case_type"] == "report_anomaly"
    assert candidate["action_type"] == "report_anomaly_candidate"
    assert candidate["source_id"] == "report_anomaly:77"
    assert candidate["estimated_amount"] == 2500.5
    assert candidate["finance_trace"]["source"] == "data_quality.list_issues"
    assert "requires review" in candidate["reason"]
    adapter.data_quality.list_issues.assert_awaited_once()


@pytest.mark.asyncio
async def test_claims_adapter_detects_supply_discrepancy_from_supply_goods() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    supply = SimpleNamespace(
        id=10,
        supply_id=555,
        fact_date=datetime(2026, 6, 10),
        warehouse_name="Коледино",
        actual_warehouse_name=None,
        payload={},
    )
    good = SimpleNamespace(
        id=20,
        nm_id=1001,
        vendor_code="A-1",
        barcode="4607000000000",
        quantity=10,
        accepted_quantity=7,
        payload={"unit_price": 120.5, "token": "must-not-leak"},
    )

    result = await adapter.detect_supply_discrepancy_candidates(
        1,
        (date(2026, 6, 1), date(2026, 6, 15)),
        nm_id=1001,
        session=_SupplySession([(supply, good)]),
    )

    assert result["status"] == "ok"
    candidate = result["items"][0]
    assert candidate["case_type"] == "supply_discrepancy"
    assert candidate["action_type"] == "draft_claim"
    assert candidate["source_type"] == "supply_discrepancy_signal"
    assert candidate["source_id"] == "supply_discrepancy:555:1001"
    assert candidate["supply_id"] == 555
    assert candidate["nm_id"] == 1001
    assert candidate["vendor_code"] == "A-1"
    assert candidate["expected_qty"] == 10
    assert candidate["accepted_qty"] == 7
    assert candidate["diff_qty"] == 3
    assert candidate["estimated_amount"] == 361.5
    assert candidate["warehouse"] == "Коледино"
    assert candidate["date"].startswith("2026-06-10")
    assert candidate["evidence_refs"][0]["table"] == "wb_supplies"
    assert "must-not-leak" not in str(result)


@pytest.mark.asyncio
async def test_claims_adapter_supply_discrepancy_returns_not_enough_data_without_acceptance_quantities() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    supply = SimpleNamespace(id=10, supply_id=555, fact_date=datetime(2026, 6, 10), warehouse_name="Коледино", payload={})
    good = SimpleNamespace(id=20, nm_id=1001, vendor_code="A-1", barcode="4607", quantity=10, accepted_quantity=None, payload={})

    result = await adapter.detect_supply_discrepancy_candidates(1, None, session=_SupplySession([(supply, good)]))

    assert result["status"] == "not_enough_data"
    assert result["items"] == []
    assert result["unavailable_sources"] == ["supply_acceptance"]
    assert "supply_acceptance_not_synced" in result["warnings"]


@pytest.mark.asyncio
async def test_claims_adapter_supply_discrepancy_returns_empty_when_no_diff() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    supply = SimpleNamespace(id=10, supply_id=555, fact_date=datetime(2026, 6, 10), warehouse_name="Коледино", payload={})
    good = SimpleNamespace(id=20, nm_id=1001, vendor_code="A-1", barcode="4607", quantity=10, accepted_quantity=10, payload={})

    result = await adapter.detect_supply_discrepancy_candidates(1, None, session=_SupplySession([(supply, good)]))

    assert result["status"] == "empty"
    assert result["items"] == []


@pytest.mark.asyncio
async def test_claims_adapter_detects_missing_goods_from_zero_accepted_supply_goods() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    supply = SimpleNamespace(id=10, supply_id=555, fact_date=datetime(2026, 6, 10), warehouse_name="Коледино", payload={})
    good = SimpleNamespace(
        id=20,
        nm_id=1001,
        vendor_code="A-1",
        barcode="4607",
        quantity=10,
        accepted_quantity=0,
        payload={"unit_price": 50.0},
    )

    result = await adapter.detect_missing_goods_candidates(1, None, session=_SupplySession([(supply, good)]))

    assert result["status"] == "ok"
    candidate = result["items"][0]
    assert candidate["case_type"] == "missing_goods"
    assert candidate["source_type"] == "missing_goods_signal"
    assert candidate["source_id"] == "missing_goods:555:1001"
    assert candidate["expected_qty"] == 10
    assert candidate["accepted_qty"] == 0
    assert candidate["diff_qty"] == 10
    assert candidate["estimated_amount"] == 500.0


@pytest.mark.asyncio
async def test_claims_adapter_detects_compensation_underpayment_from_defect_and_finance_rows() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(),
        mock_candidates=[
            {
                **_candidate(),
                "source_id": "defect:901",
                "id": "defect-901",
                "expected_compensation_amount": 1000.0,
                "estimated_amount": 1000.0,
                "nm_id": 1001,
                "vendor_code": "A-1",
                "srid": "srid-1",
            }
        ],
    )
    finance_row = SimpleNamespace(
        id=501,
        rrd_id=9001,
        report_id=42,
        srid="srid-1",
        nm_id=1001,
        seller_oper_name="Компенсация брака",
        bonus_type_name="",
        doc_type_name="",
        operation_type="",
        additional_payment=400.0,
        for_pay=400.0,
    )

    result = await adapter.detect_compensation_underpayment_candidates(
        1,
        (date(2026, 6, 1), date(2026, 6, 10)),
        nm_id=1001,
        session=_SupplySession([finance_row]),
    )

    assert result["status"] == "ok"
    candidate = result["items"][0]
    assert candidate["case_type"] == "compensation_underpayment"
    assert candidate["action_type"] == "draft_claim"
    assert candidate["source_id"] == "compensation_underpayment:defect:901"
    assert candidate["nm_id"] == 1001
    assert candidate["vendor_code"] == "A-1"
    assert candidate["defect_id"] == "defect-901"
    assert candidate["return_id"] == "srid-1"
    assert candidate["expected_compensation_amount"] == 1000.0
    assert candidate["actual_compensation_amount"] == 400.0
    assert candidate["underpaid_amount"] == 600.0
    assert candidate["evidence_refs"][1]["table"] == "wb_realization_report_rows"


@pytest.mark.asyncio
async def test_claims_adapter_compensation_underpayment_returns_empty_when_fully_paid() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(),
        mock_candidates=[
            {
                **_candidate(),
                "source_id": "defect:902",
                "expected_compensation_amount": 1000.0,
                "estimated_amount": 1000.0,
                "nm_id": 1001,
                "srid": "srid-2",
            }
        ],
    )
    finance_row = SimpleNamespace(
        id=502,
        rrd_id=9002,
        report_id=42,
        srid="srid-2",
        nm_id=1001,
        seller_oper_name="Компенсация брака",
        bonus_type_name="",
        doc_type_name="",
        operation_type="",
        additional_payment=1000.0,
        for_pay=1000.0,
    )

    result = await adapter.detect_compensation_underpayment_candidates(1, None, session=_SupplySession([finance_row]))

    assert result["status"] == "empty"
    assert result["items"] == []


@pytest.mark.asyncio
async def test_claims_adapter_compensation_underpayment_returns_not_enough_data_when_expected_missing() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(),
        mock_candidates=[
            {
                **_candidate(),
                "source_id": "defect:903",
                "estimated_amount": None,
                "impact": None,
                "nm_id": 1001,
                "srid": "srid-3",
            }
        ],
    )

    result = await adapter.detect_compensation_underpayment_candidates(1, None, session=_SupplySession([]))

    assert result["status"] == "not_enough_data"
    assert result["items"] == []
    assert "expected_compensation_amount" in result["required_fields"]


@pytest.mark.asyncio
async def test_claims_adapter_actions_include_report_anomaly_from_data_quality() -> None:
    adapter = ClaimsDefectAdapter(Settings())
    adapter.data_quality.list_issues = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 78,
                    "account_id": 1,
                    "domain": "finance",
                    "severity": "warning",
                    "code": "sale_without_finance",
                    "nm_id": 1002,
                    "message": "Sale has no finance report row yet.",
                    "payload": {"affectedRevenue": 900.0},
                }
            ]
        )
    )

    actions, unavailable = await adapter.claims_actions(SimpleNamespace(id=1), session=SimpleNamespace(), limit=10)

    assert unavailable is None
    assert any(action.source_module == "claims" and action.action_type == "report_anomaly_candidate" for action in actions)
    action = next(action for action in actions if action.action_type == "report_anomaly_candidate")
    assert action.guided_fix["endpoint"] == "/api/v1/portal/cases/from-signal"
    assert action.guided_fix["payload"]["case_type"] == "report_anomaly"


@pytest.mark.asyncio
async def test_claims_adapter_unconfigured_live_submit_does_not_submit(monkeypatch) -> None:
    adapter = ClaimsDefectAdapter(Settings(enable_claims_submit=True))

    async def _unexpected_submit(*args, **kwargs):
        raise AssertionError("factory submit should not run when live support is not configured")

    monkeypatch.setattr(adapter.factory, "submit_case_manual_confirm", _unexpected_submit)

    result = await adapter.submit_to_support(
        SimpleNamespace(),
        account_id=1,
        case_id=10,
        confirm=True,
        draft_id="20",
        created_by=2,
    )

    assert result.success is False
    assert result.event_type == "submit_not_configured"
    assert result.warnings == ["claims_not_configured"]
    assert result.data.get("external_submit_attempted") is False
    assert result.data.get("external_write_enabled") is False
    assert result.data.get("local_only") is True


@pytest.mark.asyncio
async def test_claims_adapter_submit_disabled_by_default_even_when_configured(monkeypatch) -> None:
    adapter = ClaimsDefectAdapter(
        Settings(
            claims_enabled=True,
            claims_base_url="http://claims.internal",
        )
    )

    async def _unexpected_submit(*args, **kwargs):
        raise AssertionError("factory submit should not run when submit flag is disabled")

    monkeypatch.setattr(adapter.factory, "submit_case_manual_confirm", _unexpected_submit)

    result = await adapter.submit_to_support(
        SimpleNamespace(),
        account_id=1,
        case_id=10,
        confirm=True,
        draft_id="20",
        created_by=2,
    )

    assert result.success is False
    assert result.event_type == "submit_disabled_by_feature_flag"
    assert result.warnings == ["claims_submit_disabled"]
    assert result.data.get("external_submit_attempted") is False
    assert result.data.get("external_write_enabled") is False
    assert result.data.get("local_only") is True


@pytest.mark.asyncio
async def test_claims_adapter_confirm_false_delegates_to_local_guard(monkeypatch) -> None:
    adapter = ClaimsDefectAdapter(Settings())

    async def _fake_submit(session, **kwargs):
        assert kwargs["payload"] == ClaimsSubmitRequest(confirm=False, draft_id="20")
        return SimpleNamespace(success=False, event_type="submit_blocked_confirmation_required")

    monkeypatch.setattr(adapter.factory, "submit_case_manual_confirm", _fake_submit)

    result = await adapter.submit_to_support(SimpleNamespace(), account_id=1, case_id=10, confirm=False, draft_id="20")

    assert result.event_type == "submit_blocked_confirmation_required"
    assert result.success is False


def test_claim_case_templates_cover_all_case_types() -> None:
    assert set(CLAIM_CASE_TEMPLATES) == set(CaseType)

    for case_type, template in CLAIM_CASE_TEMPLATES.items():
        assert template.case_type == case_type
        assert template.required_evidence_types
        assert template.draft_type
        assert template.recommended_guided_fix["route_key"] == "claims"
        assert template.default_priority.value.startswith("P")


def test_claims_adapter_backenddefect_reference_endpoint_inventory_marks_dangerous_submit_routes() -> None:
    safe = set(ClaimsDefectAdapter.SAFE_REFERENCE_ENDPOINTS)
    compatibility = set(ClaimsDefectAdapter.COMPATIBILITY_ENDPOINTS)
    dangerous = set(ClaimsDefectAdapter.DANGEROUS_REFERENCE_ENDPOINTS)

    assert "GET /api/cases" in safe
    assert "POST /api/cases/{case_id}/generate-draft" in safe
    assert "POST /api/cases/{case_id}/proof-check" in safe
    assert "POST /api/wb/cases/{case_id}/finance-trace" in safe
    assert "GET /defect-candidates" in compatibility
    assert "POST /api/cases/{case_id}/submit" in dangerous
    assert "POST /api/cases/{case_id}/create-appeal" in dangerous
    assert "POST /api/cases/{case_id}/repeat-claim/send" in dangerous
    assert dangerous.isdisjoint(safe)


@pytest.mark.asyncio
async def test_claims_adapter_repeat_and_pretrial_detectors_use_defect_signals() -> None:
    adapter = ClaimsDefectAdapter(
        Settings(),
        mock_candidates=[
            {**_candidate(), "id": "repeat-1", "needs_repeat": True, "status": "needs_repeat"},
            {**_candidate(), "id": "pretrial-1", "pretrial_required": True, "priority": "P0"},
        ],
    )

    repeat = await adapter.detect_repeat_claim_candidates(1, None)
    pretrial = await adapter.detect_pretrial_candidates(1, None)

    assert repeat["status"] == "ok"
    assert repeat["case_type"] == CaseType.REPEAT_CLAIM.value
    assert repeat["items"][0]["action_type"] == "repeat_claim_needed"
    assert repeat["items"][0]["source_id"].startswith("repeat_claim:")
    assert pretrial["status"] == "ok"
    assert pretrial["case_type"] == CaseType.PRETRIAL.value
    assert pretrial["items"][0]["action_type"] == "pretrial_prepare"
    assert pretrial["items"][0]["source_id"].startswith("pretrial:")


@pytest.mark.asyncio
async def test_claims_adapter_repeat_and_pretrial_detectors_return_empty_without_signals() -> None:
    adapter = ClaimsDefectAdapter(Settings())

    repeat = await adapter.detect_repeat_claim_candidates(1, None)
    pretrial = await adapter.detect_pretrial_candidates(1, None)

    assert repeat["status"] == "not_configured"
    assert repeat["case_type"] == CaseType.REPEAT_CLAIM.value
    assert repeat["items"] == []
    assert repeat["item_count"] == 0
    assert pretrial["status"] == "not_configured"
    assert pretrial["case_type"] == CaseType.PRETRIAL.value
    assert pretrial["items"] == []
    assert pretrial["item_count"] == 0

    report_anomaly = await adapter.detect_report_anomaly_candidates(1, None)
    assert report_anomaly["status"] == "not_configured"
    assert report_anomaly["case_type"] == CaseType.REPORT_ANOMALY.value
    assert report_anomaly["items"] == []
    assert "requires a finance DB session" in report_anomaly["message"]
    assert report_anomaly["trust_state"] == "unavailable"


@pytest.mark.asyncio
async def test_claims_adapter_repeat_and_pretrial_detectors_return_empty_when_configured_without_matching_signals() -> None:
    adapter = ClaimsDefectAdapter(Settings(), mock_candidates=[_candidate()])

    repeat = await adapter.detect_repeat_claim_candidates(1, None)
    pretrial = await adapter.detect_pretrial_candidates(1, None)

    assert repeat["status"] == "empty"
    assert repeat["items"] == []
    assert pretrial["status"] == "empty"
    assert pretrial["items"] == []
