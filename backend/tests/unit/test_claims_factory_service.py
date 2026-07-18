from __future__ import annotations

import pytest

from app.core.config import Settings
from app.models.claims import ClaimCandidate, ClaimDetectionRun
from app.models.operator import OperatorCase, OperatorDraft
from app.schemas.claims import ClaimCandidateStatusUpdate, ClaimsCaseCreate, ClaimsCaseFromSignalCreate, ClaimsSubmitRequest
from app.schemas.operator import CaseType
from app.services.claims_factory import ClaimsFactoryService


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def scalar_one(self):
        return self._rows[0] if self._rows else 0

    def scalar(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, *, case: OperatorCase, draft: OperatorDraft | None = None) -> None:
        self.case = case
        self.draft = draft
        self.added = []
        self.committed = False

    async def get(self, model, key):
        if model is OperatorCase and int(key) == self.case.id:
            return self.case
        if model is OperatorDraft and self.draft is not None and int(key) == self.draft.id:
            return self.draft
        return None

    async def execute(self, stmt):
        return _ScalarResult([self.draft] if self.draft is not None else [])

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def refresh(self, row):
        return None


class _CreateSession:
    def __init__(self) -> None:
        self.added = []
        self.case = None
        self.next_id = 100

    def add(self, row):
        self.added.append(row)
        if isinstance(row, OperatorCase):
            self.case = row

    async def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = self.next_id
                self.next_id += 1

    async def commit(self):
        return None

    async def refresh(self, row):
        return None

    async def get(self, model, key):
        if model is OperatorCase and self.case is not None and int(key) == self.case.id:
            return self.case
        return None

    async def execute(self, stmt):
        return _ScalarResult([])


class _SignalSession(_CreateSession):
    def __init__(self) -> None:
        super().__init__()
        self.cases = []
        self.events = []
        self.commits = 0

    def add(self, row):
        super().add(row)
        if isinstance(row, OperatorCase) and row not in self.cases:
            self.cases.append(row)
        if row.__class__.__name__ == "ResultEvent":
            self.events.append(row)

    async def commit(self):
        self.commits += 1

    async def get(self, model, key):
        if model is OperatorCase:
            for case in self.cases:
                if int(case.id) == int(key):
                    return case
        return await super().get(model, key)

    async def execute(self, stmt):
        text = str(stmt)
        if "operator_evidence" in text or "operator_drafts" in text:
            return _ScalarResult([])
        if "result_events" in text:
            return _ScalarResult(self.events)
        if "operator_cases" in text:
            return _ScalarResult(self.cases)
        return _ScalarResult([])


class _ClaimsScanSession(_SignalSession):
    def __init__(self) -> None:
        super().__init__()
        self.runs = []
        self.candidates = []

    def add(self, row):
        super().add(row)
        if isinstance(row, ClaimDetectionRun) and row not in self.runs:
            self.runs.append(row)
        if isinstance(row, ClaimCandidate) and row not in self.candidates:
            self.candidates.append(row)

    async def get(self, model, key):
        if model is ClaimCandidate:
            for candidate in self.candidates:
                if int(candidate.id) == int(key):
                    return candidate
        if model is ClaimDetectionRun:
            for run in self.runs:
                if int(run.id) == int(key):
                    return run
        return await super().get(model, key)

    async def execute(self, stmt):
        text = str(stmt)
        is_count_query = "count(" in text.lower()
        if "claim_candidates" in text and is_count_query:
            return _ScalarResult([len(self.candidates)])
        if "claim_detection_runs" in text and is_count_query:
            return _ScalarResult([len(self.runs)])
        if "claim_candidates" in text:
            return _ScalarResult(self.candidates)
        if "claim_detection_runs" in text:
            return _ScalarResult(self.runs)
        return await super().execute(stmt)


class _FakeClaimsDetector:
    async def detect_supply_discrepancy_candidates(self, account_id, date_range=None, session=None):
        return {
            "status": "ok",
            "items": [
                {
                    "source_id": "supply:SUP-1:1001",
                    "title": "Supply discrepancy",
                    "summary": "Finance supply quantity differs from acceptance rows.",
                    "nm_id": 1001,
                    "supply_id": "SUP-1",
                    "quantity": 2,
                    "estimated_amount": 1500.0,
                    "confidence": "high",
                    "priority": "P1",
                    "token": "must-not-leak",
                }
            ],
        }


def _case() -> OperatorCase:
    return OperatorCase(
        id=10,
        account_id=1,
        source_module="claims",
        source_id="claims:case:10",
        nm_id=1001,
        case_type="defect",
        status="draft_ready",
        external_status="draft_ready",
        title="Defect candidate",
        payload_json={"order_id": "order-1"},
    )


def _draft() -> OperatorDraft:
    return OperatorDraft(
        id=20,
        account_id=1,
        case_id=10,
        source_module="claims",
        source_id="claims:draft:20",
        draft_type="support_appeal",
        status="new",
        external_status="draft_ready",
        title="Draft",
        body_text="Draft text",
        payload_json={},
    )


@pytest.mark.asyncio
async def test_claims_submit_requires_manual_confirm_and_records_event() -> None:
    service = ClaimsFactoryService()
    session = _FakeSession(case=_case(), draft=_draft())

    result = await service.submit_case_manual_confirm(
        session,
        account_id=1,
        case_id=10,
        payload=ClaimsSubmitRequest(confirm=False, draft_id="20"),
        created_by=2,
    )

    assert result.success is False
    assert result.event_type == "submit_blocked_confirmation_required"
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_submit_enabled"] is False
    assert result.data["external_ticket_created"] is False
    assert result.data["local_status"] == "draft_ready"
    assert result.warnings == ["manual_confirm_required"]
    assert session.committed is True
    assert len(session.added) == 1
    event = session.added[0]
    assert event.source_module == "claims"
    assert event.status == "blocked"
    assert event.payload_json["manual_confirm"] is False
    assert "token" not in str(event.payload_json).lower()


@pytest.mark.asyncio
async def test_claims_submit_confirm_true_default_records_local_only() -> None:
    service = ClaimsFactoryService()
    case = _case()
    session = _FakeSession(case=case, draft=_draft())

    result = await service.submit_case_manual_confirm(
        session,
        account_id=1,
        case_id=10,
        payload=ClaimsSubmitRequest(confirm=True, draft_id="20"),
        created_by=2,
    )

    assert result.success is True
    assert result.event_type == "manual_submission_recorded"
    assert result.external_status == "not_created"
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_submit_enabled"] is False
    assert result.data["external_ticket_created"] is False
    assert result.data["local_status"] == "manual_submission_recorded"
    assert result.warnings == ["claims_external_submit_disabled"]
    assert case.status == "in_review"
    assert case.external_status == "not_created"
    assert all(item.__class__.__name__ != "ExternalTicket" for item in session.added)
    assert session.committed is True


@pytest.mark.asyncio
async def test_claims_submit_external_ticket_tracking_requires_feature_flag() -> None:
    service = ClaimsFactoryService(Settings(enable_claims_submit=True))
    case = _case()
    session = _FakeSession(case=case, draft=_draft())

    result = await service.submit_case_manual_confirm(
        session,
        account_id=1,
        case_id=10,
        payload=ClaimsSubmitRequest(confirm=True, draft_id="20"),
        created_by=2,
    )

    assert result.success is True
    assert result.event_type == "submit_confirmed"
    assert result.data["external_submit_attempted"] is False
    assert result.data["external_submit_enabled"] is True
    assert result.data["external_ticket_created"] is True
    assert result.data["local_status"] == "submitted"
    assert any(item.__class__.__name__ == "ExternalTicket" for item in session.added)
    assert case.status == "submitted"
    assert case.external_status == "submitted"


@pytest.mark.asyncio
async def test_claims_proof_check_requires_evidence_identity_and_draft(monkeypatch) -> None:
    service = ClaimsFactoryService()
    case = _case()
    case.nm_id = None
    case.payload_json = {}
    session = _FakeSession(case=case, draft=None)

    async def _no_evidence(*args, **kwargs):
        return []

    async def _no_drafts(*args, **kwargs):
        return []

    monkeypatch.setattr(service, "_case_evidence", _no_evidence)
    monkeypatch.setattr(service, "_case_drafts", _no_drafts)

    result = await service.proof_check(session, account_id=1, case_id=10)

    assert result.passed is False
    assert set(result.missing_evidence) == {"evidence", "product_identity", "order_or_return_identity", "draft"}
    assert "case_not_ready_to_submit" in result.warnings
    assert case.status == "evidence_needed"


@pytest.mark.asyncio
async def test_claims_factory_accepts_all_case_types_with_template_metadata() -> None:
    service = ClaimsFactoryService()

    for case_type in CaseType:
        session = _CreateSession()
        result = await service.create_case(
            session,
            payload=ClaimsCaseCreate(
                account_id=1,
                case_type=case_type,
                title=f"{case_type.value} candidate",
                priority="P2",
            ),
            created_by=2,
        )

        assert result.case_type == case_type
        assert result.status == "candidate"
        assert result.data["case_template"]["required_evidence_types"]
        assert result.data["case_template"]["recommended_guided_fix"]["route_key"] == "claims"


@pytest.mark.asyncio
async def test_claims_create_case_from_signal_is_idempotent_and_records_event() -> None:
    service = ClaimsFactoryService()
    session = _SignalSession()
    payload = ClaimsCaseFromSignalCreate(
        account_id=1,
        source_module="claims",
        source_id="defect_claim_candidate:1001",
        case_type=CaseType.DEFECT,
        nm_id=1001,
        vendor_code="A-1",
        title="Defect compensation candidate",
        summary="Return reason indicates a defect.",
        estimated_amount=1500.0,
        payload={"reason": "defect"},
    )

    first = await service.create_case_from_signal(session, payload=payload, created_by=2)
    second = await service.create_case_from_signal(session, payload=payload, created_by=2)

    assert first.id == second.id
    assert len(session.cases) == 1
    assert first.data["signal"]["source_id"] == "defect_claim_candidate:1001"
    assert any(event.event_type == "case_created_from_signal" for event in session.events)


@pytest.mark.asyncio
async def test_claims_detection_scan_persists_safe_candidates() -> None:
    service = ClaimsFactoryService()
    session = _ClaimsScanSession()

    result = await service.start_detection_scan(
        session,
        account_id=1,
        detector_types=["supply_discrepancy"],
        date_from=None,
        date_to=None,
        requested_by_user_id=2,
        detector=_FakeClaimsDetector(),
    )

    assert result.status == "ok"
    assert result.run_ids == ["100"]
    assert result.runs[0].candidates_created == 1
    assert len(session.runs) == 1
    assert len(session.candidates) == 1
    candidate = session.candidates[0]
    assert candidate.detector_type == "supply_discrepancy"
    assert candidate.nm_id == 1001
    assert candidate.status == "new"
    assert candidate.confidence == 0.85
    assert "token" not in str(candidate.payload_json).lower()
    assert session.commits == 1


@pytest.mark.asyncio
async def test_claims_candidate_status_and_case_creation_link_candidate() -> None:
    service = ClaimsFactoryService()
    session = _ClaimsScanSession()
    candidate = ClaimCandidate(
        id=10,
        account_id=1,
        detector_type="missing_goods",
        source_id="missing:SUP-2:1001",
        nm_id=1001,
        supply_id="SUP-2",
        title="Missing goods candidate",
        business_explanation="Three goods are missing from accepted supply.",
        severity="high",
        confidence=0.8,
        expected_amount=3000.0,
        quantity_affected=3,
        status="new",
        fingerprint="candidate-fingerprint",
        evidence_summary_json={"supply_id": "SUP-2"},
        payload_json={"order_id": "order-2"},
    )
    session.add(candidate)

    updated = await service.update_candidate_status(
        session,
        account_id=1,
        candidate_id=10,
        payload=ClaimCandidateStatusUpdate(status="reviewing", reason="looks plausible"),
        updated_by=2,
    )
    detail = await service.create_case_from_candidate(session, account_id=1, candidate_id=10, created_by=2)

    assert updated.status == "reviewing"
    assert detail.case_type == CaseType.MISSING_GOODS
    assert detail.nm_id == 1001
    assert candidate.case_id == int(detail.id)
    assert candidate.status == "case_created"
    assert detail.data["candidate_id"] == 10
    assert detail.data["evidence_summary"] == {"supply_id": "SUP-2"}


@pytest.mark.asyncio
async def test_claims_list_cases_hides_synthetic_seller_rows() -> None:
    service = ClaimsFactoryService()
    session = _SignalSession()
    session.cases = [
        OperatorCase(
            id=10,
            account_id=1,
            source_module="claims",
            source_id="claims:real:10",
            case_type="defect",
            status="candidate",
            title="Real defect case",
            payload_json={"order_id": "order-10"},
        ),
        OperatorCase(
            id=11,
            account_id=1,
            source_module="claims",
            source_id="claims:synthetic:11",
            case_type="defect",
            status="candidate",
            title="Synthetic runtime audit case",
            payload_json={"synthetic": True},
        ),
        OperatorCase(
            id=12,
            account_id=1,
            source_module="claims",
            source_id="claims:audit:12",
            case_type="defect",
            status="candidate",
            title="Runtime audit claim",
            payload_json={"shadow_synthetic": True},
        ),
    ]

    page = await service.list_cases(session, account_id=1, limit=50, offset=0)

    assert page.total == 1
    assert [item.id for item in page.items] == ["10"]


def test_claims_qr_text_extracts_backenddefect_wb_identifiers() -> None:
    service = ClaimsFactoryService()
    raw = (
        "https://example.test/qr?"
        "barcode=4311001523761&"
        "shkId=32591063543&"
        "stickerId=44633744017&"
        "srid=7c3f9bf41e4642d7b10b4f468c27d4d0&"
        "nmId=203979308"
    )

    fields = service._extract_order_fields_from_text(raw)
    codes = service._classify_extracted_codes(
        "4311001523761 32591063543 7c3f9bf41e4642d7b10b4f468c27d4d0",
        source="barcode",
    )

    assert fields == {
        "nm_id": "203979308",
        "barcode": "4311001523761",
        "shk_id": "32591063543",
        "sticker_id": "44633744017",
        "srid": "7c3f9bf41e4642d7b10b4f468c27d4d0",
    }
    assert {"code_type": "barcode", "source": "barcode", "value": "4311001523761", "confidence": 0.96} in codes
    assert any(item["code_type"] == "srid" and item["value"] == "7c3f9bf41e4642d7b10b4f468c27d4d0" for item in codes)
