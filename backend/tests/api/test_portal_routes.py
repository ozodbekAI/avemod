from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.db import get_db_session
from app.main import app
from app.models.accounts import WBAccount
from app.models.control_tower import ActionRecommendation
from app.models.operator import OperatorCase, UnifiedAction
from app.modules.portal import router as portal_router
from app.modules.stock_control import router as stock_control_router
from app.schemas.claims import CaseDetailOut, ClaimsCasesPage, ClaimsDraftMutationOut, ClaimsProofCheckOut
from app.schemas.operator import ProfitDoctorOut, ResultEventOut, TrustState
from app.schemas.portal import (
    PortalActionRead,
    PortalActionsPage,
    PortalDataBlock,
    PortalDashboardBusinessVerdict,
    PortalDashboardOverviewRead,
    PortalDashboardPulseCard,
    PortalDashboardSourceFreshness,
    PortalDataReadinessRead,
    PortalDataSyncDomainStatus,
    PortalDataSyncStatusRead,
    PortalExperimentEventRead,
    PortalExperimentEventsPage,
    PortalGroupingPreviewRead,
    PortalModuleHealth,
    PortalModuleHealthItem,
    PortalModulesHealthRead,
    PortalOverviewRead,
    PortalProduct360Read,
    PortalProductGroupingRead,
    PortalProductQualityRead,
    PortalProductRead,
    PortalProductsPage,
    PortalResultEventRead,
    PortalResultEventsPage,
    PortalCostStatus,
    PortalNextStep,
    PortalReadinessBlocker,
    PortalSafeAction,
    PortalStatusBlock,
    PortalStockOpsRunRead,
    PortalStockOpsRunsPage,
)
from app.schemas.reputation import ReputationInboxOut, ReputationItemOut, ReputationSettingsOut, ReputationSummaryOut
from app.schemas.stock_control import StockControlImportPreview, StockControlRunRead
from app.services.auth import get_current_user


class _FakeExecuteResult:
    def __init__(self, *, rows=None, scalars=None):
        self._rows = rows or []
        self._scalars = scalars or []

    def all(self):
        return self._rows

    def scalars(self):
        return self

    def scalar_one(self):
        return len(self._scalars)

    def __iter__(self):
        return iter(self._scalars)


class _FakeSession:
    def __init__(
        self,
        *,
        accounts: dict[int, SimpleNamespace] | None = None,
        allowed_account_ids: set[int] | None = None,
        account_roles: dict[int, str] | None = None,
        action_account_id: int = 1,
        case_account_id: int = 1,
    ) -> None:
        self.accounts = accounts or {
            1: SimpleNamespace(
                id=1,
                name="Account 1",
                seller_name=None,
                external_account_id=None,
                timezone="Europe/Moscow",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
            2: SimpleNamespace(
                id=2,
                name="Account 2",
                seller_name=None,
                external_account_id=None,
                timezone="Europe/Moscow",
                is_active=True,
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            ),
        }
        self.allowed_account_ids = allowed_account_ids if allowed_account_ids is not None else {1}
        self.account_roles = account_roles or {}
        self.action_account_id = action_account_id
        self.case_account_id = case_account_id

    async def get(self, model, key):
        if model is WBAccount:
            return self.accounts.get(int(key))
        if model is ActionRecommendation:
            return SimpleNamespace(id=int(key), account_id=self.action_account_id)
        if model is OperatorCase:
            return SimpleNamespace(id=int(key), account_id=self.case_account_id, source_module="claims")
        return None

    async def execute(self, stmt):
        allowed_accounts = [self.accounts[account_id] for account_id in sorted(self.allowed_account_ids) if account_id in self.accounts]
        rows = [(account.id, self.account_roles.get(int(account.id), "viewer")) for account in allowed_accounts]
        return _FakeExecuteResult(rows=rows, scalars=allowed_accounts)

    async def commit(self):
        return None

    def add(self, row):
        return None


def _session_factory(**kwargs):
    async def _override_session():
        yield _FakeSession(**kwargs)

    return _override_session


async def _override_session():
    yield _FakeSession()


def _override_superuser():
    return SimpleNamespace(id=1, is_superuser=True)


def _override_normal_user():
    return SimpleNamespace(id=2, is_superuser=False)


def _enable_legacy_diagnostics(monkeypatch) -> None:
    monkeypatch.setattr(
        portal_router,
        "get_settings",
        lambda: Settings(enable_legacy_diagnostics=True),
    )


def _module_health() -> PortalModuleHealth:
    return PortalModuleHealth(
        finance=PortalModuleHealthItem(status="ok"),
        checker=PortalModuleHealthItem(status="not_configured"),
        stockops=PortalModuleHealthItem(status="not_configured"),
        grouping=PortalModuleHealthItem(status="not_configured"),
    )


def _action() -> PortalActionRead:
    return PortalActionRead(
        id="finance:10",
        action_id=10,
        source="finance_actions",
        source_module="finance",
        source_id="10",
        account_id=1,
        action_type="ADS_REVIEW",
        title="Проверить рекламу",
        priority="P3",
        severity="medium",
        status="new",
        nm_id=223205606,
    )


def test_portal_routes_are_registered_in_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {
        "/api/v1/portal/overview",
        "/api/v1/portal/dashboard/overview",
        "/api/v1/portal/data-readiness",
        "/api/v1/portal/data-sync/status",
        "/api/v1/portal/doctor",
        "/api/v1/portal/actions",
        "/api/v1/portal/actions/by-source",
        "/api/v1/portal/actions/{action_id}",
        "/api/v1/portal/actions/{action_id}/results",
        "/api/v1/portal/actions/{action_id}/result-event",
        "/api/v1/portal/results",
        "/api/v1/portal/products",
        "/api/v1/portal/products/{nm_id}",
        "/api/v1/portal/products/{nm_id}/quality",
        "/api/v1/portal/products/{nm_id}/grouping",
        "/api/v1/portal/products/{nm_id}/events",
        "/api/v1/portal/card-quality/products/{nm_id}/recheck",
        "/api/v1/portal/card-quality/issues/{issue_id}/accept-local",
        "/api/v1/portal/card-quality/issues/{issue_id}/mark-fixed",
        "/api/v1/portal/card-quality/issues/{issue_id}/draft",
        "/api/v1/portal/card-quality/issues/{issue_id}/preview-wb",
        "/api/v1/portal/card-quality/issues/{issue_id}/apply-wb",
        "/api/v1/portal/card-quality/issues/{issue_id}/recheck",
        "/api/v1/portal/experiments/status",
        "/api/v1/portal/experiments/settings",
        "/api/v1/portal/experiments",
        "/api/v1/portal/experiments/{experiment_id}",
        "/api/v1/portal/experiments/{experiment_id}/start",
        "/api/v1/portal/experiments/{experiment_id}/record-intervention",
        "/api/v1/portal/experiments/{experiment_id}/cancel",
        "/api/v1/portal/experiments/{experiment_id}/evaluate",
        "/api/v1/portal/experiments/{experiment_id}/evaluation",
        "/api/v1/portal/experiments/{experiment_id}/metrics",
        "/api/v1/portal/experiments/{experiment_id}/events",
        "/api/v1/portal/experiments/events",
        "/api/v1/portal/photo/projects/{project_id}/versions/{version_id}/experiment",
        "/api/v1/portal/grouping/preview",
        "/api/v1/portal/stockops/run",
        "/api/v1/portal/stockops/runs",
        "/api/v1/portal/stock-control/status",
        "/api/v1/portal/stock-control/settings",
        "/api/v1/portal/stock-control/imports/regional-supply/preview",
        "/api/v1/portal/stock-control/imports/regional-supply",
        "/api/v1/portal/stock-control/templates/hand-stock",
        "/api/v1/portal/stock-control/imports/hand-stock/preview",
        "/api/v1/portal/stock-control/hand-stock-drafts",
        "/api/v1/portal/stock-control/hand-stock-drafts/{draft_id}",
        "/api/v1/portal/stock-control/runs",
        "/api/v1/portal/stock-control/runs/{run_id}",
        "/api/v1/portal/stock-control/runs/{run_id}/retry",
        "/api/v1/portal/stock-control/runs/{run_id}/cancel",
        "/api/v1/portal/stock-control/runs/{run_id}/overview",
        "/api/v1/portal/stock-control/runs/{run_id}/region-rows",
        "/api/v1/portal/stock-control/runs/{run_id}/movements",
        "/api/v1/portal/stock-control/runs/{run_id}/unmatched",
        "/api/v1/portal/stock-control/runs/{run_id}/export",
        "/api/v1/portal/reputation/inbox",
        "/api/v1/portal/reputation/summary",
        "/api/v1/portal/reputation/sync",
        "/api/v1/portal/reputation/items/{item_id}",
        "/api/v1/portal/reputation/items/{item_id}/draft",
        "/api/v1/portal/reputation/items/{item_id}/no-reply-needed",
        "/api/v1/portal/reputation/drafts/{draft_id}/approve",
        "/api/v1/portal/reputation/drafts/{draft_id}/regenerate",
        "/api/v1/portal/reputation/drafts/{draft_id}/reject",
        "/api/v1/portal/reputation/drafts/{draft_id}/publish",
        "/api/v1/portal/reputation/settings",
        "/api/v1/portal/cases",
        "/api/v1/portal/cases/from-signal",
        "/api/v1/portal/cases/detect/defects",
        "/api/v1/portal/cases/detect/supply-discrepancies",
        "/api/v1/portal/cases/detect/missing-goods",
        "/api/v1/portal/cases/detect/report-anomalies",
        "/api/v1/portal/cases/detect/compensation-underpayments",
        "/api/v1/portal/cases/detect/repeat-claims",
        "/api/v1/portal/cases/detect/pretrial",
        "/api/v1/portal/cases/{case_id}",
        "/api/v1/portal/cases/{case_id}/evidence",
        "/api/v1/portal/cases/{case_id}/generate-draft",
        "/api/v1/portal/cases/{case_id}/proof-check",
        "/api/v1/portal/cases/{case_id}/submit",
        "/api/v1/portal/cases/{case_id}/events",
        "/api/v1/portal/claims/scans",
        "/api/v1/portal/claims/scans/{run_id}",
        "/api/v1/portal/claims/scans/{run_id}/retry",
        "/api/v1/portal/claims/candidates",
        "/api/v1/portal/claims/candidates/{candidate_id}",
        "/api/v1/portal/claims/candidates/{candidate_id}/status",
        "/api/v1/portal/claims/candidates/{candidate_id}/create-case",
        "/api/v1/portal/modules/health",
    }.issubset(paths.keys())


def _doctor_response(**overrides) -> ProfitDoctorOut:
    base = {
        "status": "ok",
        "account_id": 1,
        "trust_state": TrustState.OPERATIONAL,
        "summary": "Legacy-диагностика прибыли не нашла срочных утечек прибыли в проанализированных данных.",
        "total_signals": 0,
        "total_diagnoses": 0,
    }
    base.update(overrides)
    return ProfitDoctorOut(**base)


def test_portal_doctor_requires_authentication() -> None:
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/doctor?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401


def test_portal_doctor_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_diagnose(session, **kwargs):
        raise AssertionError("doctor service should not be called for forbidden account")

    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/doctor?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_doctor_hidden_for_normal_user_by_default(monkeypatch) -> None:
    async def _fake_diagnose(session, **kwargs):
        raise AssertionError("legacy doctor should not be called for a normal user")

    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/doctor?account_id=1&period=custom&date_from=2026-06-01&date_to=2026-06-10&nm_id=223205606"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json()["detail"] == "Legacy diagnostics are disabled"


def test_portal_doctor_returns_valid_superuser_when_legacy_enabled(monkeypatch) -> None:
    _enable_legacy_diagnostics(monkeypatch)

    async def _fake_diagnose(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["nm_id"] == 223205606
        assert kwargs["date_from"].isoformat() == "2026-06-01"
        assert kwargs["date_to"].isoformat() == "2026-06-10"
        return _doctor_response(account_id=kwargs["account_id"], date_from=kwargs["date_from"], date_to=kwargs["date_to"])

    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/doctor?account_id=1&period=custom&date_from=2026-06-01&date_to=2026-06-10&nm_id=223205606"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["account_id"] == 1
    assert body["date_from"] == "2026-06-01"
    assert body["date_to"] == "2026-06-10"
    assert body["trust_state"] == "operational"


def test_portal_doctor_degrades_when_optional_modules_unavailable(monkeypatch) -> None:
    _enable_legacy_diagnostics(monkeypatch)

    async def _fake_diagnose(session, **kwargs):
        return _doctor_response(
            account_id=kwargs["account_id"],
            trust_state=TrustState.PROVISIONAL,
            unavailable_sources=["checker", "reputation", "claims"],
            warnings=["Optional sources are unavailable."],
        )

    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/doctor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["trust_state"] == "provisional"
    assert body["unavailable_sources"] == ["checker", "reputation", "claims"]


def test_portal_doctor_finance_data_missing_returns_safe_trust_state(monkeypatch) -> None:
    _enable_legacy_diagnostics(monkeypatch)

    async def _fake_diagnose(session, **kwargs):
        return _doctor_response(
            account_id=kwargs["account_id"],
            trust_state=TrustState.BLOCKED,
            summary="Legacy profit diagnostics are blocked by missing finance data.",
            unavailable_sources=["money_articles"],
            warnings=["Finance product data is missing."],
        )

    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/doctor?account_id=1&period=7d")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["trust_state"] == "blocked"
    assert body["unavailable_sources"] == ["money_articles"]


def test_portal_overview_returns_module_health(monkeypatch) -> None:
    async def _fake_overview(session, **kwargs):
        return PortalOverviewRead(
            module_health=_module_health(),
            money_summary={
                "kpis": {"cash_on_wb_current": None, "known_zero": 0},
                "token": "must-not-leak",
                "nested": {"api_key": "must-not-leak", "safe": True},
            },
            doctor_summary={"status": "ok", "summary": "1 issue", "total_diagnoses": 1, "trust_state": "provisional"},
            top_problems=[{"type": "profit_leak", "title": "Проверить прибыль"}],
            operator_actions=[{"type": "review_profit", "title": "Открыть Product 360"}],
            product_risks=[{"nm_id": 1001, "type": "profit_leak"}],
            reputation={"status": "not_configured", "unanswered_reviews_count": None},
            claims={"status": "not_configured", "open_cases_count": None},
            top_actions=[_action()],
        )

    monkeypatch.setattr(portal_router.service, "overview", _fake_overview)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/overview?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["module_health"]["finance"]["status"] == "ok"
    assert body["module_health"]["checker"]["status"] == "not_configured"
    assert body["doctor_summary"]["total_diagnoses"] == 1
    assert body["top_problems"][0]["type"] == "profit_leak"
    assert body["operator_actions"][0]["type"] == "review_profit"
    assert body["product_risks"][0]["nm_id"] == 1001
    assert body["reputation"]["status"] == "not_configured"
    assert body["claims"]["status"] == "not_configured"
    assert body["top_actions"][0]["source"] == "finance_actions"
    assert body["top_actions"][0]["source_module"] == "finance"
    assert body["top_actions"][0]["can_update_status"] is False
    assert body["money_summary"]["kpis"]["cash_on_wb_current"] is None
    assert body["money_summary"]["kpis"]["known_zero"] == 0
    assert "token" not in body["money_summary"]
    assert "api_key" not in body["money_summary"]["nested"]


def test_portal_dashboard_overview_returns_owner_cockpit_contract(monkeypatch) -> None:
    async def _fake_dashboard_overview(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["limit"] == 10
        freshness = PortalDashboardSourceFreshness(status="fresh", required_sources=["stocks"])
        return PortalDashboardOverviewRead(
            business_verdict=PortalDashboardBusinessVerdict(
                state="warning",
                title="Есть зоны внимания",
                short_explanation="Остатки требуют внимания.",
                checked=True,
                has_data=True,
                has_risk=True,
            ),
            business_pulse=[
                PortalDashboardPulseCard(
                    code="stock",
                    title="Остатки",
                    value=7,
                    unit="SKU",
                    state="warning",
                    checked=True,
                    has_data=True,
                    has_risk=True,
                    trust_state="provisional",
                    impact_type="business_signal",
                    short_explanation="Есть остатки без продаж.",
                    evidence_available=True,
                    source_freshness=freshness,
                )
            ],
        )

    monkeypatch.setattr(portal_router.service, "dashboard_overview", _fake_dashboard_overview)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/dashboard/overview?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert set(body) >= {
        "business_verdict",
        "business_pulse",
        "top_attention_items",
        "today_plan",
        "data_confidence",
        "recent_results_summary",
        "onboarding_state",
    }
    assert body["business_pulse"][0]["code"] == "stock"
    assert body["business_pulse"][0]["has_risk"] is True


def test_portal_data_readiness_separates_operational_and_final_status(monkeypatch) -> None:
    async def _fake_data_readiness(session, **kwargs):
        return PortalDataReadinessRead(
            account_id=kwargs["account_id"],
            operational_status=PortalStatusBlock(
                state="ok",
                title="Операционно можно работать",
                message="Данных достаточно для ежедневных решений",
            ),
            final_profit_status=PortalStatusBlock(
                state="blocked",
                title="Финальная прибыль пока предварительная",
                message="Есть 32 блокера финальной сверки",
            ),
            cost_status=PortalCostStatus(
                sku_coverage_percent=99.93,
                revenue_coverage_percent=99.62,
                missing_cost_count=1,
                missing_cost_revenue=28606.0,
                state="warning",
            ),
            blockers=[
                PortalReadinessBlocker(
                    code="finance_reconciliation_mismatch",
                    priority="critical",
                    title="Расхождение WB отчета и продаж",
                    affected_sku_count=28,
                    affected_revenue=6060049.23,
                    next_screen_path="/data-fix?code=finance_reconciliation_mismatch",
                    primary_button_label="Открыть расхождения",
                )
            ],
            sync_status=PortalDataSyncStatusRead(account_id=kwargs["account_id"], overall_state="ok"),
            next_steps=[PortalNextStep(id="fix_costs", label="Загрузить себестоимость", screen_path="/costs")],
        )

    monkeypatch.setattr(portal_router.service, "data_readiness", _fake_data_readiness)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/data-readiness?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["operational_status"]["state"] == "ok"
    assert body["final_profit_status"]["state"] == "blocked"
    assert body["cost_status"]["missing_cost_count"] == 1
    assert body["blockers"][0]["code"] == "finance_reconciliation_mismatch"


def test_portal_data_readiness_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_data_readiness(session, **kwargs):
        raise AssertionError("service should not run for forbidden account")

    monkeypatch.setattr(portal_router.service, "data_readiness", _fake_data_readiness)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/data-readiness?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_data_sync_status_route(monkeypatch) -> None:
    async def _fake_data_sync_status(session, **kwargs):
        return PortalDataSyncStatusRead(
            account_id=kwargs["account_id"],
            overall_state="warning",
            domains=[
                PortalDataSyncDomainStatus(
                    domain="product_cards",
                    status="failed",
                    last_error_text="Token expired",
                    next_action="fix_token",
                )
            ],
            safe_actions=[
                PortalSafeAction(id="sync_latest", label="Обновить реальные данные", endpoint="POST /api/v1/sync/trigger")
            ],
        )

    monkeypatch.setattr(portal_router.service, "data_sync_status", _fake_data_sync_status)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/data-sync/status?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["domains"][0]["next_action"] == "fix_token"
    assert body["safe_actions"][0]["endpoint"] == "POST /api/v1/sync/trigger"


def test_portal_routes_reject_invalid_date_range(monkeypatch) -> None:
    async def _fake_overview(session, **kwargs):
        raise AssertionError("service should not be called for invalid date range")

    monkeypatch.setattr(portal_router.service, "overview", _fake_overview)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/overview?account_id=1&date_from=2026-06-10&date_to=2026-06-01"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "date_from" in response.text


def test_portal_actions_update_accepts_mvp_statuses(monkeypatch) -> None:
    async def _fake_update_action(session, **kwargs):
        return _action().model_copy(update={"status": kwargs["payload"].status})

    monkeypatch.setattr(portal_router.service, "update_action", _fake_update_action)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.patch("/api/v1/portal/actions/10", json={"status": "postponed"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "postponed"


def test_portal_actions_by_source_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_update_action_by_source(session, **kwargs):
        raise AssertionError("service should not update a forbidden account")

    monkeypatch.setattr(portal_router.service, "update_action_by_source", _fake_update_action_by_source)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 2,
                    "source_module": "reputation",
                    "source_id": "review:123",
                    "status": "done",
                    "comment": "answered manually",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_viewer_can_get_but_cannot_mutate_actions(monkeypatch) -> None:
    async def _fake_actions(session, **kwargs):
        assert kwargs["account_id"] == 1
        return PortalActionsPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    async def _fake_update_action_by_source(session, **kwargs):
        raise AssertionError("viewer must not mutate action status")

    monkeypatch.setattr(portal_router.service, "actions", _fake_actions)
    monkeypatch.setattr(portal_router.service, "update_action_by_source", _fake_update_action_by_source)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            read_response = client.get("/api/v1/portal/actions?account_id=1")
            write_response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "reputation",
                    "source_id": "review:123",
                    "status": "done",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert read_response.status_code == 200
    assert write_response.status_code == 403
    assert "operator" in write_response.json()["detail"]


def test_portal_actions_forwards_include_beta_query(monkeypatch) -> None:
    seen: list[bool] = []

    async def _fake_actions(session, **kwargs):
        seen.append(kwargs["include_beta"])
        return PortalActionsPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    monkeypatch.setattr(portal_router.service, "actions", _fake_actions)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            default_response = client.get("/api/v1/portal/actions?account_id=1")
            beta_response = client.get("/api/v1/portal/actions?account_id=1&include_beta=true")
    finally:
        app.dependency_overrides.clear()

    assert default_response.status_code == 200
    assert beta_response.status_code == 200
    assert seen == [False, True]


def test_portal_operator_can_mark_action_and_generate_draft_but_cannot_publish(monkeypatch) -> None:
    async def _fake_update_action_by_source(session, **kwargs):
        return _action().model_copy(update={"status": kwargs["payload"].status, "source_module": "reputation", "source_id": "review:123"})

    async def _fake_generate_draft(session, **kwargs):
        return {"status": "ok", "account_id": kwargs["account_id"], "draft": {"id": "d1", "draft_type": "review_reply", "text": "Draft"}}

    async def _fake_publish(session, **kwargs):
        raise AssertionError("operator must not publish replies")

    async def _fake_approve(session, **kwargs):
        raise AssertionError("operator must not approve replies")

    monkeypatch.setattr(portal_router.service, "update_action_by_source", _fake_update_action_by_source)
    monkeypatch.setattr(portal_router.service, "reputation_generate_draft", _fake_generate_draft)
    monkeypatch.setattr(portal_router.service, "reputation_approve_draft", _fake_approve)
    monkeypatch.setattr(portal_router.service, "reputation_publish_reply", _fake_publish)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            status_response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "reputation",
                    "source_id": "review:123",
                    "status": "done",
                },
            )
            draft_response = client.post("/api/v1/portal/reputation/items/review:123/draft?account_id=1", json={})
            approve_response = client.post("/api/v1/portal/reputation/drafts/review:123/approve?account_id=1")
            publish_response = client.post(
                "/api/v1/portal/reputation/drafts/review:123/publish?account_id=1",
                json={"confirm": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert status_response.status_code == 200
    assert draft_response.status_code == 200
    assert approve_response.status_code == 403
    assert "manager" in approve_response.json()["detail"]
    assert publish_response.status_code == 403
    assert "manager" in publish_response.json()["detail"]


def test_portal_operator_can_update_action_status(monkeypatch) -> None:
    async def _fake_update_action_by_source(session, **kwargs):
        assert kwargs["payload"].status == "in_progress"
        assert kwargs["payload"].account_id == 1
        return _action().model_copy(
            update={
                "status": "in_progress",
                "source_module": "reputation",
                "source_id": "review:123",
            }
        )

    monkeypatch.setattr(portal_router.service, "update_action_by_source", _fake_update_action_by_source)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "reputation",
                    "source_id": "review:123",
                    "status": "in_progress",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


def test_portal_viewer_cannot_perform_manager_only_reputation_decision(monkeypatch) -> None:
    async def _fake_no_reply_needed(session, **kwargs):
        raise AssertionError("viewer must not perform manual reputation decisions")

    monkeypatch.setattr(portal_router.service, "reputation_mark_no_reply_needed", _fake_no_reply_needed)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/reputation/items/review:123/no-reply-needed?account_id=1",
                json={"confirm": True, "reason": "Handled outside portal"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    assert "manager" in response.json()["detail"]


def test_portal_manager_can_perform_allowed_manual_reputation_decision(monkeypatch) -> None:
    async def _fake_no_reply_needed(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["item_id"] == "review:123"
        assert kwargs["payload"].confirm is True
        assert kwargs["user_id"] == 2
        return ResultEventOut(
            id="result:1",
            module="reputation",
            account_id=1,
            event_type="no_reply_needed",
            message="Manual decision recorded.",
        )

    monkeypatch.setattr(portal_router.service, "reputation_mark_no_reply_needed", _fake_no_reply_needed)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/reputation/items/review:123/no-reply-needed?account_id=1",
                json={"confirm": True, "reason": "Handled outside portal"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["module"] == "reputation"
    assert response.json()["event_type"] == "no_reply_needed"


def test_portal_actions_by_source_updates_local_status_without_external_adapters(monkeypatch) -> None:
    class _BySourceSession(_FakeSession):
        def __init__(self) -> None:
            super().__init__()
            self.unified_actions = []
            self.added = []
            self.next_id = 100
            self.committed = False

        async def execute(self, stmt):
            if "unified_actions" in str(stmt):
                return _FakeExecuteResult(scalars=self.unified_actions)
            if "result_events" in str(stmt):
                return _FakeExecuteResult(scalars=[])
            return await super().execute(stmt)

        async def get(self, model, key):
            if model is UnifiedAction:
                for row in self.unified_actions:
                    if int(row.id or 0) == int(key):
                        return row
                return None
            return await super().get(model, key)

        def add(self, row):
            self.added.append(row)
            if isinstance(row, UnifiedAction) and row not in self.unified_actions:
                self.unified_actions.append(row)

        async def flush(self):
            for row in self.added:
                if getattr(row, "id", None) is None:
                    row.id = self.next_id
                    self.next_id += 1

        async def refresh(self, row):
            return None

        async def commit(self):
            self.committed = True

    async def _external_adapter_must_not_run(*args, **kwargs):
        raise AssertionError("by-source status update must not call external adapters")

    monkeypatch.setattr(portal_router.service.reputation_adapter, "publish_reply", _external_adapter_must_not_run)
    monkeypatch.setattr(portal_router.service.reputation_adapter, "mark_no_reply_needed", _external_adapter_must_not_run)
    monkeypatch.setattr(portal_router.service.claims_adapter, "submit_to_support", _external_adapter_must_not_run)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _session_factory()

    session = _BySourceSession()

    async def _session_override():
        yield session

    app.dependency_overrides[get_db_session] = _session_override
    try:
        with TestClient(app) as client:
            response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "reputation",
                    "source_id": "review:123",
                    "status": "done",
                    "comment": "answered manually",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["source_module"] == "reputation"
    assert body["source_id"] == "review:123"
    assert body["can_update_status"] is True
    assert session.committed is True
    assert len(session.unified_actions) == 1
    assert session.unified_actions[0].payload_json["shadow_synthetic"] is True
    assert any(getattr(row, "event_type", None) == "local_action_status_updated" for row in session.added)


def test_portal_product_routes_serialize_finance_only_payloads(monkeypatch) -> None:
    async def _fake_products(session, **kwargs):
        return PortalProductsPage(
            total=1,
            limit=50,
            offset=0,
            items=[
                PortalProductRead(
                    nm_id=223205606,
                    title="Article",
                    money={"revenue": 1000.0},
                    stock={"quantity": 3.0},
                    ads={"spend": 100.0},
                )
            ],
        )

    async def _fake_product_360(session, **kwargs):
        return PortalProduct360Read(
            nm_id=kwargs["nm_id"],
            money=PortalDataBlock(status="ok", data={"revenue": 1000.0}),
            stock=PortalDataBlock(status="ok", data={"quantity": 3.0}),
            stock_summary={"quantity": 3.0},
            ads=PortalDataBlock(status="ok", data={"spend": 100.0}),
            ads_summary={"spend": 100.0},
            quality=PortalDataBlock(status="not_configured", data={"status": "not_configured"}),
            actions=[_action()],
        )

    async def _fake_product_quality(session, **kwargs):
        return PortalProductQualityRead(
            status="ok",
            nm_id=kwargs["nm_id"],
            score=72,
            critical_issue_count=1,
            title_issues=[{"code": "title_short"}],
        )

    monkeypatch.setattr(portal_router.service, "products", _fake_products)
    monkeypatch.setattr(portal_router.service, "product_360", _fake_product_360)
    monkeypatch.setattr(portal_router.service, "product_quality", _fake_product_quality)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            list_response = client.get("/api/v1/portal/products?account_id=1")
            detail_response = client.get("/api/v1/portal/products/223205606?account_id=1")
            quality_response = client.get("/api/v1/portal/products/223205606/quality?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["nm_id"] == 223205606
    assert detail_response.status_code == 200
    assert detail_response.json()["stock"]["status"] == "ok"
    assert detail_response.json()["stock"]["data"]["quantity"] == 3.0
    assert detail_response.json()["quality"]["status"] == "not_configured"
    assert quality_response.status_code == 200
    assert quality_response.json()["score"] == 72


def test_portal_modules_health_route(monkeypatch) -> None:
    async def _fake_modules_health(session, **kwargs):
        modules = _module_health().model_copy(
            update={
                "reputation": PortalModuleHealthItem(
                    module="reputation",
                    status="ok",
                    enabled=True,
                    configured=True,
                    runtime_mode="local",
                    dangerous_actions_enabled=True,
                    publish_enabled=True,
                    auto_publish_enabled=False,
                    chat_send_enabled=True,
                )
            }
        )
        return PortalModulesHealthRead(computed_at="2026-06-09T00:00:00Z", modules=modules)

    monkeypatch.setattr(portal_router.service, "modules_health", _fake_modules_health)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/modules/health?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["modules"]["grouping"]["status"] == "not_configured"
    reputation = response.json()["modules"]["reputation"]
    assert reputation["runtime_mode"] == "local"
    assert reputation["dangerous_actions_enabled"] is True
    assert reputation["publish_enabled"] is True
    assert reputation["auto_publish_enabled"] is False
    assert reputation["chat_send_enabled"] is True


def test_portal_modules_health_real_registry_degrades_when_optional_modules_missing() -> None:
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/modules/health?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    modules = response.json()["modules"]
    assert modules["finance"]["status"] == "ok"
    assert modules["finance"]["visible"] is True
    assert modules["finance"]["navigation_group"] == "core"
    assert modules["doctor"]["status"] == "disabled"
    assert modules["doctor"]["visible"] is False
    assert modules["actions"]["visible"] is True
    assert modules["products"]["visible"] is True
    assert modules["checker"]["status"] == "not_configured"
    assert modules["checker"]["visible"] is True
    assert modules["stockops"]["status"] in {"empty", "unavailable", "running", "degraded", "ok"}
    assert modules["stockops"]["mode"] == "local"
    assert modules["stockops"]["configured"] is True
    assert modules["stockops"]["navigation_group"] == "beta"
    assert modules["grouping"]["status"] == "disabled"
    assert modules["grouping"]["visible"] is False
    assert modules["reputation"]["status"] == "disabled"
    assert modules["reputation"]["visible"] is False
    assert modules["claims"]["status"] == "disabled"
    assert modules["photo"]["status"] == "disabled"
    assert modules["experiments"]["status"] == "ok"
    assert modules["results"]["visible"] is True


def test_portal_stockops_routes_use_local_stock_control_alias(monkeypatch) -> None:
    async def _fake_stockops_run(session, *, payload, user_id=None):
        return PortalStockOpsRunRead(
            status="queued",
            run_type=payload.run_type,
            account_id=payload.account_id,
            run_id=77,
            message="Local Stock Control run queued",
            raw={"mode": "local", "marketplace_change": False, "can_execute": False},
        )

    async def _fake_stockops_runs(session, **kwargs):
        return PortalStockOpsRunsPage(
            status="ok",
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            items=[
                PortalStockOpsRunRead(
                    status="queued",
                    run_type=kwargs["run_type"],
                    account_id=kwargs["account_id"],
                    run_id=77,
                    raw={"mode": "local", "marketplace_change": False, "can_execute": False},
                )
            ],
        )

    monkeypatch.setattr(portal_router.service, "stockops_run", _fake_stockops_run)
    monkeypatch.setattr(portal_router.service, "stockops_runs", _fake_stockops_runs)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            run_response = client.post(
                "/api/v1/portal/stockops/run",
                json={"run_type": "return_excess", "account_id": 1, "payload": {}},
            )
            runs_response = client.get("/api/v1/portal/stockops/runs?run_type=return_excess")
    finally:
        app.dependency_overrides.clear()

    assert run_response.status_code == 200
    assert run_response.json()["status"] == "queued"
    assert run_response.json()["raw"]["mode"] == "local"
    assert run_response.json()["raw"]["marketplace_change"] is False
    assert runs_response.status_code == 200
    assert runs_response.json()["status"] == "ok"
    assert runs_response.json()["items"][0]["raw"]["mode"] == "local"


def test_stock_control_run_create_is_local_queued_and_scrubs_payload(monkeypatch) -> None:
    async def _fake_create_run(session, *, payload, requested_by_user_id=None):
        assert payload.account_id == 1
        assert payload.run_type == "return_excess"
        assert requested_by_user_id == 1
        return StockControlRunRead(
            id=99,
            account_id=payload.account_id,
            run_type=payload.run_type,
            status="queued",
            source_mode=payload.source_mode,
            allocation_mode=payload.allocation_mode,
            requested_by_user_id=requested_by_user_id,
            input_summary_json={"mode": "local"},
            result_summary_json={"marketplace_change": False, "can_execute": False},
            created_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
            updated_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(stock_control_router.service, "create_run", _fake_create_run)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/stock-control/runs",
                json={
                    "account_id": 1,
                    "run_type": "return_excess",
                    "settings_override": {"api_token": "must-not-leak", "minimum_keep_per_size": 1},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["result_summary_json"]["marketplace_change"] is False
    assert "must-not-leak" not in response.text
    assert "api_token" not in response.text


def test_stock_control_rejects_store_balance_phase_1() -> None:
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/stock-control/runs",
                json={"account_id": 1, "run_type": "store_balance"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "phase 2" in response.text


def test_stock_control_import_preview_reports_invalid_template(monkeypatch) -> None:
    async def _fake_preview_import(*, file_name, content, import_type):
        assert import_type == "regional_supply"
        assert file_name == "bad.csv"
        assert content == b"bad"
        return StockControlImportPreview(
            file_name=file_name,
            rows_total=0,
            warnings=["Invalid template: required columns are missing"],
            sample_rows=[],
        )

    monkeypatch.setattr(stock_control_router.service, "preview_import", _fake_preview_import)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/stock-control/imports/regional-supply/preview?account_id=1",
                files={"file": ("bad.csv", b"bad", "text/csv")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["warnings"] == ["Invalid template: required columns are missing"]


def test_portal_grouping_routes_are_beta_recommendation_only(monkeypatch) -> None:
    async def _fake_product_grouping(session, **kwargs):
        return PortalProductGroupingRead(
            status="beta",
            account_id=kwargs["account_id"],
            nm_id=kwargs["nm_id"],
            recommendations=[{"nm_id": 2002, "article": "VC-2"}],
            recommendation_count=1,
        )

    async def _fake_grouping_preview(session, payload):
        return PortalGroupingPreviewRead(
            status="beta",
            account_id=payload.account_id,
            nm_id=payload.nm_id,
            summary={"dry_run": True},
            recommendations=[{"nm_id": 2002, "article": "VC-2"}],
        )

    monkeypatch.setattr(portal_router.service, "product_grouping", _fake_product_grouping)
    monkeypatch.setattr(portal_router.service, "grouping_preview", _fake_grouping_preview)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            grouping_response = client.get("/api/v1/portal/products/1001/grouping?account_id=1")
            preview_response = client.post(
                "/api/v1/portal/grouping/preview",
                json={"account_id": 1, "nm_id": 1001, "custom_config": {}},
            )
    finally:
        app.dependency_overrides.clear()

    assert grouping_response.status_code == 200
    assert grouping_response.json()["status"] == "beta"
    assert grouping_response.json()["recommendation_count"] == 1
    assert preview_response.status_code == 200
    assert preview_response.json()["summary"]["dry_run"] is True


def test_portal_create_case_from_signal_returns_case_and_does_not_call_external_support(monkeypatch) -> None:
    async def _fake_create_case_from_signal(session, **kwargs):
        payload = kwargs["payload"]
        assert payload.account_id == 1
        assert payload.source_id == "defect_claim_candidate:1001"
        return CaseDetailOut(
            id="10",
            account_id=payload.account_id,
            case_type=payload.case_type,
            nm_id=payload.nm_id,
            title=payload.title,
            summary=payload.summary,
            amount_claimed=payload.estimated_amount,
            data={"signal": payload.model_dump(mode="json")},
            result_events=[
                ResultEventOut(
                    module="claims",
                    event_type="case_created_from_signal",
                    case_id="10",
                    success=True,
                )
            ],
        )

    async def _external_support_must_not_run(*args, **kwargs):
        raise AssertionError("from-signal must not submit external support tickets")

    monkeypatch.setattr(portal_router.claims_service, "create_case_from_signal", _fake_create_case_from_signal)
    monkeypatch.setattr(portal_router.doctor_service.claims_adapter, "submit_to_support", _external_support_must_not_run)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/cases/from-signal",
                json={
                    "account_id": 1,
                    "source_module": "claims",
                    "source_id": "defect_claim_candidate:1001",
                    "case_type": "defect",
                    "nm_id": 1001,
                    "vendor_code": "A-1",
                    "title": "Defect compensation candidate",
                    "summary": "Return reason indicates a defect.",
                    "estimated_amount": 1500.0,
                    "payload": {"reason": "defect"},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "10"
    assert body["data"]["signal"]["source_id"] == "defect_claim_candidate:1001"
    assert body["result_events"][0]["event_type"] == "case_created_from_signal"


def test_portal_create_supply_discrepancy_case_from_signal_uses_existing_case_flow(monkeypatch) -> None:
    async def _fake_create_case_from_signal(session, **kwargs):
        payload = kwargs["payload"]
        assert payload.account_id == 1
        assert payload.case_type == "supply_discrepancy"
        assert payload.source_id == "supply_discrepancy:555:1001"
        assert payload.payload["diff_qty"] == 3
        return CaseDetailOut(
            id="11",
            account_id=payload.account_id,
            case_type=payload.case_type,
            nm_id=payload.nm_id,
            title=payload.title,
            summary=payload.summary,
            amount_claimed=payload.estimated_amount,
            data={"signal": payload.model_dump(mode="json")},
            result_events=[
                ResultEventOut(
                    module="claims",
                    event_type="case_created_from_signal",
                    case_id="11",
                    success=True,
                )
            ],
        )

    async def _external_support_must_not_run(*args, **kwargs):
        raise AssertionError("from-signal must not submit external support tickets")

    monkeypatch.setattr(portal_router.claims_service, "create_case_from_signal", _fake_create_case_from_signal)
    monkeypatch.setattr(portal_router.doctor_service.claims_adapter, "submit_to_support", _external_support_must_not_run)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/cases/from-signal",
                json={
                    "account_id": 1,
                    "source_module": "claims",
                    "source_id": "supply_discrepancy:555:1001",
                    "case_type": "supply_discrepancy",
                    "nm_id": 1001,
                    "vendor_code": "A-1",
                    "title": "Supply discrepancy candidate",
                    "summary": "Accepted quantity is below expected quantity.",
                    "estimated_amount": 361.5,
                    "payload": {
                        "supply_id": 555,
                        "expected_qty": 10,
                        "accepted_qty": 7,
                        "diff_qty": 3,
                        "evidence_refs": [{"table": "wb_supplies", "source_id": "555"}],
                    },
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "11"
    assert body["case_type"] == "supply_discrepancy"
    assert body["data"]["signal"]["payload"]["diff_qty"] == 3


def test_portal_create_case_from_signal_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_create_case_from_signal(session, **kwargs):
        raise AssertionError("service should not create case for forbidden account")

    monkeypatch.setattr(portal_router.claims_service, "create_case_from_signal", _fake_create_case_from_signal)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/cases/from-signal",
                json={
                    "account_id": 2,
                    "source_module": "claims",
                    "source_id": "defect_claim_candidate:1001",
                    "case_type": "defect",
                    "nm_id": 1001,
                    "title": "Defect compensation candidate",
                    "summary": "Return reason indicates a defect.",
                    "estimated_amount": 1500.0,
                    "payload": {},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_detect_defects_returns_mock_candidates_without_secrets(monkeypatch) -> None:
    async def _fake_detect_defect_candidates(account_id, date_range, *, nm_id=None):
        assert account_id == 1
        assert nm_id == 1001
        assert date_range[0].isoformat() == "2026-06-01"
        assert date_range[1].isoformat() == "2026-06-10"
        return {
            "status": "ok",
            "trust_state": "provisional",
            "items": [
                {
                    "source_id": "defect_claim_candidate:1001",
                    "nm_id": 1001,
                    "vendor_code": "A-1",
                    "title": "Defect compensation candidate",
                    "estimated_amount": 1500.0,
                    "buyer_email": "buyer@example.test",
                    "token": "must-not-leak",
                }
            ],
        }

    monkeypatch.setattr(portal_router.claims_detection_adapter, "detect_defect_candidates", _fake_detect_defect_candidates)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/cases/detect/defects?account_id=1&nm_id=1001&date_from=2026-06-01&date_to=2026-06-10"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["case_type"] == "defect"
    assert body["account_id"] == 1
    assert body["items"][0]["nm_id"] == 1001
    assert body["template"]["required_evidence_types"]
    assert "must-not-leak" not in str(body)
    assert "buyer@example" not in str(body)


def test_portal_detect_supply_discrepancies_uses_finance_detector_without_secrets(monkeypatch) -> None:
    async def _fake_detect_supply_discrepancy_candidates(account_id, date_range, *, nm_id=None, session=None):
        assert account_id == 1
        assert nm_id == 1001
        assert date_range[0].isoformat() == "2026-06-01"
        assert date_range[1].isoformat() == "2026-06-10"
        assert session is not None
        return {
            "status": "ok",
            "case_type": "supply_discrepancy",
            "account_id": 1,
            "trust_state": "provisional",
            "items": [
                {
                    "account_id": 1,
                    "case_type": "supply_discrepancy",
                    "action_type": "draft_claim",
                    "source_id": "supply_discrepancy:555:1001",
                    "supply_id": 555,
                    "nm_id": 1001,
                    "vendor_code": "A-1",
                    "expected_qty": 10,
                    "accepted_qty": 7,
                    "diff_qty": 3,
                    "estimated_amount": 361.5,
                    "warehouse": "Коледино",
                    "date": "2026-06-10T00:00:00",
                    "evidence_refs": [{"table": "wb_supplies", "source_id": "555"}],
                    "token": "must-not-leak",
                }
            ],
        }

    monkeypatch.setattr(
        portal_router.claims_detection_adapter,
        "detect_supply_discrepancy_candidates",
        _fake_detect_supply_discrepancy_candidates,
    )
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/cases/detect/supply-discrepancies?account_id=1&nm_id=1001&date_from=2026-06-01&date_to=2026-06-10"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["case_type"] == "supply_discrepancy"
    assert body["items"][0]["supply_id"] == 555
    assert body["items"][0]["expected_qty"] == 10
    assert body["items"][0]["accepted_qty"] == 7
    assert body["items"][0]["diff_qty"] == 3
    assert body["items"][0]["evidence_refs"]
    assert body["template"]["case_type"] == "supply_discrepancy"
    assert "must-not-leak" not in str(body)


def test_portal_detect_compensation_underpayments_uses_finance_detector(monkeypatch) -> None:
    async def _fake_detect_compensation_underpayment_candidates(account_id, date_range, *, nm_id=None, session=None):
        assert account_id == 1
        assert nm_id == 1001
        assert date_range[0].isoformat() == "2026-06-01"
        assert date_range[1].isoformat() == "2026-06-10"
        assert session is not None
        return {
            "status": "ok",
            "case_type": "compensation_underpayment",
            "account_id": 1,
            "trust_state": "provisional",
            "items": [
                {
                    "account_id": 1,
                    "case_type": "compensation_underpayment",
                    "action_type": "draft_claim",
                    "source_id": "compensation_underpayment:defect:901",
                    "nm_id": 1001,
                    "vendor_code": "A-1",
                    "defect_id": "defect-901",
                    "return_id": "srid-1",
                    "expected_compensation_amount": 1000.0,
                    "actual_compensation_amount": 400.0,
                    "underpaid_amount": 600.0,
                    "evidence_refs": [{"table": "wb_realization_report_rows", "source_id": "9001"}],
                    "token": "must-not-leak",
                }
            ],
        }

    monkeypatch.setattr(
        portal_router.claims_detection_adapter,
        "detect_compensation_underpayment_candidates",
        _fake_detect_compensation_underpayment_candidates,
    )
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/cases/detect/compensation-underpayments?account_id=1&nm_id=1001&date_from=2026-06-01&date_to=2026-06-10"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["case_type"] == "compensation_underpayment"
    assert body["items"][0]["expected_compensation_amount"] == 1000.0
    assert body["items"][0]["actual_compensation_amount"] == 400.0
    assert body["items"][0]["underpaid_amount"] == 600.0
    assert body["template"]["case_type"] == "compensation_underpayment"
    assert "must-not-leak" not in str(body)


def test_portal_future_claim_detections_are_transparent_and_do_not_create_fake_claims(monkeypatch) -> None:
    async def _unexpected_create_case(*args, **kwargs):
        raise AssertionError("future detection endpoints must not create fake claims")

    monkeypatch.setattr(portal_router.claims_service, "create_case", _unexpected_create_case)
    expected = {
        "/api/v1/portal/cases/detect/missing-goods?account_id=1": ("missing_goods", {"empty", "not_enough_data", "not_configured"}),
        "/api/v1/portal/cases/detect/repeat-claims?account_id=1": ("repeat_claim", {"empty", "not_configured"}),
        "/api/v1/portal/cases/detect/pretrial?account_id=1": ("pretrial", {"empty", "not_configured"}),
    }
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            responses = {path: client.get(path) for path in expected}
    finally:
        app.dependency_overrides.clear()

    for path, response in responses.items():
        case_type, allowed_statuses = expected[path]
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in allowed_statuses
        assert body["case_type"] == case_type
        assert body["items"] == []
        assert body["item_count"] == 0
        assert body["message"]
        assert body["trust_state"] in {"provisional", "unavailable"}
        assert body["template"]["case_type"] == case_type
        assert body["template"]["case_type"] == case_type
        assert body["template"]["required_evidence_types"]


def test_portal_claim_detection_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_detect_defect_candidates(*args, **kwargs):
        raise AssertionError("claims detection should not run for forbidden account")

    monkeypatch.setattr(portal_router.claims_detection_adapter, "detect_defect_candidates", _fake_detect_defect_candidates)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/cases/detect/defects?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_experiment_event_routes_create_and_list(monkeypatch) -> None:
    async def _fake_create_experiment_event(session, **kwargs):
        payload = kwargs["payload"]
        return PortalExperimentEventRead(
            id=1,
            account_id=payload.account_id,
            nm_id=payload.nm_id,
            sku_id=payload.sku_id,
            action_id=payload.action_id,
            event_type=payload.event_type,
            before_json=payload.before_json,
            after_json=payload.after_json,
            changed_at="2026-06-09T00:00:00Z",
            created_by=kwargs["created_by"],
            created_at="2026-06-09T00:00:01Z",
        )

    async def _fake_product_events(session, **kwargs):
        return PortalExperimentEventsPage(
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            items=[
                PortalExperimentEventRead(
                    id=1,
                    account_id=kwargs["account_id"],
                    nm_id=kwargs["nm_id"],
                    event_type="manual_note",
                    before_json={},
                    after_json={"note": "Проверено"},
                    changed_at="2026-06-09T00:00:00Z",
                    created_by=1,
                    created_at="2026-06-09T00:00:01Z",
                )
            ],
        )

    monkeypatch.setattr(portal_router.service, "create_experiment_event", _fake_create_experiment_event)
    monkeypatch.setattr(portal_router.service, "product_events", _fake_product_events)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/v1/portal/experiments/events",
                json={
                    "account_id": 1,
                    "nm_id": 1001,
                    "event_type": "manual_note",
                    "before_json": {},
                    "after_json": {"note": "Проверено"},
                },
            )
            list_response = client.get("/api/v1/portal/products/1001/events?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 200
    assert create_response.json()["created_by"] == 1
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["event_type"] == "manual_note"


def test_portal_normal_user_can_access_allowed_account(monkeypatch) -> None:
    async def _fake_overview(session, **kwargs):
        assert kwargs["account_id"] == 1
        return PortalOverviewRead(module_health=_module_health(), top_actions=[])

    monkeypatch.setattr(portal_router.service, "overview", _fake_overview)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/overview?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_portal_normal_user_cannot_access_other_account(monkeypatch) -> None:
    async def _fake_overview(session, **kwargs):
        raise AssertionError("service should not be called for forbidden account")

    monkeypatch.setattr(portal_router.service, "overview", _fake_overview)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/overview?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_accounts_list_returns_only_normal_users_allowed_accounts() -> None:
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/accounts")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [1]


def test_portal_rbac_audit_core_reads_allowed_for_normal_user(monkeypatch) -> None:
    async def _fake_modules_health(session, **kwargs):
        assert kwargs["account_id"] == 1
        return PortalModulesHealthRead(computed_at=datetime(2026, 6, 1, tzinfo=timezone.utc), modules=_module_health())

    async def _fake_diagnose(session, **kwargs):
        assert kwargs["account_id"] == 1
        return _doctor_response(account_id=1)

    async def _fake_actions(session, **kwargs):
        assert kwargs["account_id"] == 1
        return PortalActionsPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    async def _fake_products(session, **kwargs):
        assert kwargs["account_id"] == 1
        return PortalProductsPage(total=1, limit=kwargs["limit"], offset=kwargs["offset"], items=[PortalProductRead(nm_id=223205606)])

    async def _fake_product_360(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["nm_id"] == 223205606
        return PortalProduct360Read(nm_id=223205606)

    monkeypatch.setattr(portal_router.service, "modules_health", _fake_modules_health)
    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    monkeypatch.setattr(portal_router.service, "actions", _fake_actions)
    monkeypatch.setattr(portal_router.service, "products", _fake_products)
    monkeypatch.setattr(portal_router.service, "product_360", _fake_product_360)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            responses = [
                client.get("/api/v1/portal/modules/health?account_id=1"),
                client.get("/api/v1/portal/doctor?account_id=1"),
                client.get("/api/v1/portal/actions?account_id=1"),
                client.get("/api/v1/portal/products?account_id=1"),
                client.get("/api/v1/portal/products/223205606?account_id=1"),
            ]
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [200, 404, 200, 200, 200]


def test_portal_rbac_audit_core_reads_forbidden_for_normal_user(monkeypatch) -> None:
    async def _must_not_call(session, **kwargs):
        raise AssertionError("portal service should not be called for forbidden account")

    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _must_not_call)
    monkeypatch.setattr(portal_router.service, "actions", _must_not_call)
    monkeypatch.setattr(portal_router.service, "products", _must_not_call)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            responses = [
                client.get("/api/v1/portal/doctor?account_id=2"),
                client.get("/api/v1/portal/actions?account_id=2"),
                client.get("/api/v1/portal/products?account_id=2"),
            ]
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [403, 403, 403]


def test_portal_rbac_audit_superuser_can_access_any_account(monkeypatch) -> None:
    _enable_legacy_diagnostics(monkeypatch)

    async def _fake_modules_health(session, **kwargs):
        assert kwargs["account_id"] == 2
        return PortalModulesHealthRead(computed_at=datetime(2026, 6, 1, tzinfo=timezone.utc), modules=_module_health())

    async def _fake_diagnose(session, **kwargs):
        assert kwargs["account_id"] == 2
        return _doctor_response(account_id=2)

    async def _fake_actions(session, **kwargs):
        assert kwargs["account_id"] == 2
        return PortalActionsPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    async def _fake_products(session, **kwargs):
        assert kwargs["account_id"] == 2
        return PortalProductsPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    monkeypatch.setattr(portal_router.service, "modules_health", _fake_modules_health)
    monkeypatch.setattr(portal_router.doctor_service, "diagnose", _fake_diagnose)
    monkeypatch.setattr(portal_router.service, "actions", _fake_actions)
    monkeypatch.setattr(portal_router.service, "products", _fake_products)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            responses = [
                client.get("/api/v1/portal/modules/health?account_id=2"),
                client.get("/api/v1/portal/doctor?account_id=2"),
                client.get("/api/v1/portal/actions?account_id=2"),
                client.get("/api/v1/portal/products?account_id=2"),
            ]
    finally:
        app.dependency_overrides.clear()

    assert [response.status_code for response in responses] == [200, 200, 200, 200]


def test_portal_required_account_id_returns_validation_error_when_ambiguous() -> None:
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1, 2})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/doctor")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert response.json()["detail"] == "account_id is required"


def test_portal_operator_can_update_allowed_action_by_source(monkeypatch) -> None:
    async def _fake_actions(session, **kwargs):
        assert kwargs["account_id"] == 1
        return PortalActionsPage(
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            items=[_action().model_copy(update={"can_update_status": True})],
        )

    async def _fake_update_action_by_source(session, **kwargs):
        assert kwargs["payload"].account_id == 1
        assert kwargs["payload"].source_module == "finance"
        assert kwargs["payload"].source_id == "10"
        assert kwargs["payload"].status == "in_progress"
        return _action().model_copy(update={"status": "in_progress", "can_update_status": True})

    monkeypatch.setattr(portal_router.service, "actions", _fake_actions)
    monkeypatch.setattr(portal_router.service, "update_action_by_source", _fake_update_action_by_source)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            read_response = client.get("/api/v1/portal/actions?account_id=1")
            first_action = read_response.json()["items"][0]
            patch_response = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": first_action["source_module"],
                    "source_id": first_action["source_id"],
                    "status": "in_progress",
                    "comment": "RBAC audit status update",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert read_response.status_code == 200
    assert patch_response.status_code == 200
    assert patch_response.json()["status"] == "in_progress"


def test_portal_read_without_inferable_account_returns_safe_empty(monkeypatch) -> None:
    async def _fake_overview(session, **kwargs):
        assert kwargs["account_id"] is None
        return PortalOverviewRead(
            account=None,
            module_health=_module_health(),
            unavailable_sources=["account"],
        )

    monkeypatch.setattr(portal_router.service, "overview", _fake_overview)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids=set())
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/overview")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["unavailable_sources"] == ["account"]


def test_portal_update_action_cannot_update_other_account(monkeypatch) -> None:
    async def _fake_update_action(session, **kwargs):
        raise AssertionError("service should not update a forbidden action")

    monkeypatch.setattr(portal_router.service, "update_action", _fake_update_action)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, action_account_id=2)
    try:
        with TestClient(app) as client:
            response = client.patch("/api/v1/portal/actions/10", json={"status": "postponed"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_result_tracking_routes_use_action_account_access(monkeypatch) -> None:
    async def _fake_results(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["action_id"] == 10
        assert kwargs["nm_id"] == 1001
        assert kwargs["source_module"] == "claims"
        assert kwargs["event_type"] == "price_changed"
        assert kwargs["result_status"] == "improved"
        assert kwargs["date_from"].isoformat() == "2026-07-01"
        assert kwargs["date_to"].isoformat() == "2026-07-11"
        assert kwargs["trust_state"] == "confirmed"
        assert kwargs["impact_type"] == "confirmed_loss"
        return PortalResultEventsPage(
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            items=[
                PortalResultEventRead(
                    id="1",
                    account_id=1,
                    action_id=10,
                    source_module="claims",
                    source_id="case:10",
                    nm_id=1001,
                    event_type="price_changed",
                    outcome="improved",
                    before_snapshot={"profit": 100},
                    after_snapshot={"profit": 150},
                    comparison={"outcome": "improved"},
                    message="Metrics improved after the action window.",
                )
            ],
        )

    async def _fake_action_results(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["action_id"] == 10
        return PortalResultEventsPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    async def _fake_create_result_event(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["action_id"] == 10
        assert kwargs["payload"].event_type == "photo_fix_started"
        return PortalResultEventRead(
            id="2",
            account_id=1,
            action_id=10,
            nm_id=1001,
            event_type="photo_fix_started",
            outcome="pending",
            before_snapshot=kwargs["payload"].before_snapshot,
            after_snapshot=kwargs["payload"].after_snapshot,
            comparison={"outcome": "pending"},
            message="Photo fix started in Photo Studio. No marketplace upload was performed.",
        )

    monkeypatch.setattr(portal_router.service, "results", _fake_results)
    monkeypatch.setattr(portal_router.service, "action_results", _fake_action_results)
    monkeypatch.setattr(portal_router.service, "create_result_event", _fake_create_result_event)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(
        allowed_account_ids={1},
        account_roles={1: "operator"},
        action_account_id=1,
    )
    try:
        with TestClient(app) as client:
            results = client.get(
                "/api/v1/portal/results?account_id=1&action_id=10&nm_id=1001&source_module=claims"
                "&event_type=price_changed&result_status=improved&date_from=2026-07-01"
                "&date_to=2026-07-11&trust_state=confirmed&impact_type=confirmed_loss"
            )
            action_results = client.get("/api/v1/portal/actions/10/results")
            created = client.post(
                "/api/v1/portal/actions/10/result-event",
                json={
                    "event_type": "photo_fix_started",
                    "nm_id": 1001,
                    "payload": {"source_issue_id": "78", "target_module": "photo_studio"},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert results.status_code == 200
    assert results.json()["items"][0]["outcome"] == "improved"
    assert action_results.status_code == 200
    assert created.status_code == 200
    assert created.json()["event_type"] == "photo_fix_started"
    assert created.json()["outcome"] == "pending"


def test_portal_reputation_inbox_uses_finance_account_access(monkeypatch) -> None:
    async def _fake_reputation_inbox(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["item_type"] == "review"
        assert kwargs["rating"] == 1
        assert kwargs["sentiment"] == "negative"
        assert kwargs["priority"] == "P1"
        assert kwargs["nm_id"] == 1001
        assert kwargs["date_from"].isoformat() == "2026-06-01"
        assert kwargs["date_to"].isoformat() == "2026-06-12"
        return ReputationInboxOut(
            status="ok",
            account_id=1,
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            items=[
                ReputationItemOut(
                    id="review:fb1",
                    item_type="review",
                    external_id="fb1",
                    account_id=1,
                    nm_id=1001,
                    rating=1,
                    title="Product",
                    text="Bad quality",
                    priority="P1",
                    status="new",
                    needs_reply=True,
                )
            ],
            summary={"negative_unanswered_count": 1},
        )

    monkeypatch.setattr(portal_router.service, "reputation_inbox", _fake_reputation_inbox)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/portal/reputation/inbox"
                "?account_id=1&item_type=review&rating=1&sentiment=negative"
                "&priority=P1&nm_id=1001&date_from=2026-06-01&date_to=2026-06-12"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["items"][0]["id"] == "review:fb1"
    assert "token" not in str(payload).lower()


def test_portal_reputation_summary_and_settings_contract(monkeypatch) -> None:
    async def _fake_summary(session, **kwargs):
        assert kwargs["account_id"] == 1
        return ReputationSummaryOut(
            status="ok",
            account_id=1,
            unanswered_reviews_count=1,
            unanswered_questions_count=2,
            unread_chats_count=3,
            negative_unanswered_count=1,
            draft_ready_count=4,
            average_rating=4.2,
            sentiment={"negative": 1, "positive": 5},
            priority={"P1": 1, "P2": 2},
            runtime_mode="local",
            dangerous_actions_enabled=True,
            publish_enabled=True,
            auto_publish_enabled=False,
            chat_send_enabled=True,
        )

    async def _fake_settings(session, **kwargs):
        return ReputationSettingsOut(
            status="ok",
            account_id=kwargs["account_id"],
            reply_mode="manual",
            tone="friendly",
            language="ru",
            auto_publish_enabled=False,
            automation_enabled=False,
            chat_auto_reply_enabled=False,
            runtime_mode="local",
            dangerous_actions_enabled=True,
            publish_enabled=True,
            chat_send_enabled=True,
        )

    async def _fake_update_settings(session, **kwargs):
        assert kwargs["payload"].tone == "formal"
        return ReputationSettingsOut(
            status="ok",
            account_id=kwargs["account_id"],
            reply_mode="manual",
            tone="formal",
            language="ru",
            auto_publish_enabled=False,
            automation_enabled=False,
            chat_auto_reply_enabled=False,
            warnings=["auto_publish_forced_off"],
            runtime_mode="local",
            dangerous_actions_enabled=True,
            publish_enabled=True,
            chat_send_enabled=True,
        )

    monkeypatch.setattr(portal_router.service, "reputation_summary", _fake_summary)
    monkeypatch.setattr(portal_router.service, "reputation_settings", _fake_settings)
    monkeypatch.setattr(portal_router.service, "reputation_update_settings", _fake_update_settings)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            summary = client.get("/api/v1/portal/reputation/summary?account_id=1")
            settings = client.get("/api/v1/portal/reputation/settings?account_id=1")
            updated = client.put("/api/v1/portal/reputation/settings?account_id=1", json={"tone": "formal", "payload": {"auto_publish": True}})
    finally:
        app.dependency_overrides.clear()

    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["negative_unanswered_count"] == 1
    assert summary_body["runtime_mode"] == "local"
    assert summary_body["dangerous_actions_enabled"] is True
    assert summary_body["publish_enabled"] is True
    assert summary_body["auto_publish_enabled"] is False
    assert summary_body["chat_send_enabled"] is True
    assert settings.status_code == 200
    settings_body = settings.json()
    assert settings_body["runtime_mode"] == summary_body["runtime_mode"]
    assert settings_body["dangerous_actions_enabled"] is summary_body["dangerous_actions_enabled"]
    assert settings_body["publish_enabled"] is summary_body["publish_enabled"]
    assert settings_body["auto_publish_enabled"] is False
    assert settings_body["chat_send_enabled"] is summary_body["chat_send_enabled"]
    assert updated.status_code == 200
    updated_body = updated.json()
    assert updated_body["warnings"] == ["auto_publish_forced_off"]
    assert updated_body["runtime_mode"] == "local"


def test_portal_reputation_rejects_forbidden_account(monkeypatch) -> None:
    async def _fake_reputation_inbox(session, **kwargs):
        raise AssertionError("service should not be called for forbidden account")

    monkeypatch.setattr(portal_router.service, "reputation_inbox", _fake_reputation_inbox)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/reputation/inbox?account_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_reputation_publish_requires_confirm(monkeypatch) -> None:
    async def _fake_publish(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["payload"].confirm is False
        return ResultEventOut(
            module="reputation",
            event_type="publish_blocked_confirmation_required",
            account_id=1,
            draft_id=kwargs["draft_id"],
            title="Требуется ручное подтверждение",
            message="Публикация требует явного confirm=true.",
            success=False,
            occurred_at="2026-06-12T00:00:00Z",
            warnings=["manual_confirm_required"],
        )

    monkeypatch.setattr(portal_router.service, "reputation_publish_reply", _fake_publish)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/reputation/drafts/review:fb1/publish?account_id=1",
                json={"confirm": False},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["success"] is False
    assert response.json()["event_type"] == "publish_blocked_confirmation_required"


def test_portal_viewer_cannot_publish_reputation_reply(monkeypatch) -> None:
    async def _fake_publish(session, **kwargs):
        raise AssertionError("viewer must not reach reputation publish service")

    monkeypatch.setattr(portal_router.service, "reputation_publish_reply", _fake_publish)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "viewer"})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/reputation/drafts/review:fb1/publish?account_id=1",
                json={"confirm": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_reputation_draft_and_no_reply_contracts(monkeypatch) -> None:
    async def _fake_regenerate(session, **kwargs):
        assert kwargs["draft_id"] == "review:fb1"
        return {"status": "ok", "account_id": 1, "draft": {"id": "d2", "draft_type": "review_reply", "text": "New draft"}}

    async def _fake_reject(session, **kwargs):
        assert kwargs["payload"].reason == "bad tone"
        return {"status": "ok", "account_id": 1, "draft": {"id": "d2", "draft_type": "review_reply", "status": "ignored"}}

    async def _fake_no_reply(session, **kwargs):
        assert kwargs["payload"].confirm is False
        return ResultEventOut(
            module="reputation",
            event_type="no_reply_blocked_confirmation_required",
            account_id=1,
            title="Требуется ручное подтверждение",
            message="Отметка «ответ не нужен» требует явного confirm=true.",
            success=False,
            occurred_at="2026-06-12T00:00:00Z",
            warnings=["manual_confirm_required"],
        )

    monkeypatch.setattr(portal_router.service, "reputation_regenerate_draft", _fake_regenerate)
    monkeypatch.setattr(portal_router.service, "reputation_reject_draft", _fake_reject)
    monkeypatch.setattr(portal_router.service, "reputation_mark_no_reply_needed", _fake_no_reply)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "manager"})
    try:
        with TestClient(app) as client:
            regenerated = client.post("/api/v1/portal/reputation/drafts/review:fb1/regenerate?account_id=1", json={})
            rejected = client.post("/api/v1/portal/reputation/drafts/review:fb1/reject?account_id=1", json={"reason": "bad tone"})
            no_reply = client.post("/api/v1/portal/reputation/items/review:fb1/no-reply-needed?account_id=1", json={"confirm": False})
    finally:
        app.dependency_overrides.clear()

    assert regenerated.status_code == 200
    assert regenerated.json()["draft"]["text"] == "New draft"
    assert rejected.status_code == 200
    assert rejected.json()["draft"]["status"] == "ignored"
    assert no_reply.status_code == 200
    assert no_reply.json()["event_type"] == "no_reply_blocked_confirmation_required"


def test_portal_claims_cases_use_finance_account_access(monkeypatch) -> None:
    async def _fake_list_cases(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert kwargs["case_type"] == "defect"
        assert kwargs["status"] == "candidate"
        assert kwargs["nm_id"] == 1001
        return ClaimsCasesPage(
            account_id=1,
            total=1,
            limit=kwargs["limit"],
            offset=kwargs["offset"],
            items=[
                {
                    "id": "10",
                    "case_type": "defect",
                    "account_id": 1,
                    "nm_id": 1001,
                    "title": "Defect candidate",
                    "priority": "P1",
                    "status": "candidate",
                    "amount_claimed": 1500.0,
                }
            ],
        )

    async def _fake_create_case(session, **kwargs):
        assert kwargs["payload"].account_id == 1
        return CaseDetailOut(
            id="10",
            case_type="defect",
            account_id=1,
            nm_id=1001,
            title="Defect candidate",
            priority="P1",
            status="candidate",
        )

    monkeypatch.setattr(portal_router.claims_service, "list_cases", _fake_list_cases)
    monkeypatch.setattr(portal_router.claims_service, "create_case", _fake_create_case)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, account_roles={1: "operator"})
    try:
        with TestClient(app) as client:
            listed = client.get("/api/v1/portal/cases?account_id=1&case_type=defect&status=candidate&nm_id=1001")
            created = client.post(
                "/api/v1/portal/cases",
                json={
                    "account_id": 1,
                    "case_type": "defect",
                    "nm_id": 1001,
                    "title": "Defect candidate",
                    "priority": "P1",
                    "estimated_amount": 1500,
                    "payload": {"token": "must-not-leak", "reason": "defect"},
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "candidate"
    assert created.status_code == 200
    assert created.json()["id"] == "10"
    assert "must-not-leak" not in str(created.json())


def test_portal_claims_rejects_forbidden_case_account(monkeypatch) -> None:
    async def _fake_get_case(session, **kwargs):
        raise AssertionError("claims service should not be called for forbidden account")

    monkeypatch.setattr(portal_router.claims_service, "get_case", _fake_get_case)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1}, case_account_id=2)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/cases/10")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_claims_draft_proof_submit_and_events_contracts(monkeypatch) -> None:
    async def _fake_get_case(session, **kwargs):
        return CaseDetailOut(
            id=str(kwargs["case_id"]),
            case_type="defect",
            account_id=kwargs["account_id"],
            title="Defect candidate",
            status="draft_ready",
            evidence=[{"id": "e1", "case_id": str(kwargs["case_id"]), "evidence_type": "photo", "title": "Photo"}],
        )

    async def _fake_attach_evidence(session, **kwargs):
        assert kwargs["payload"].evidence_type == "photo"
        return {"id": "e1", "case_id": str(kwargs["case_id"]), "evidence_type": "photo", "title": kwargs["payload"].title}

    async def _fake_generate_draft(session, **kwargs):
        return ClaimsDraftMutationOut(
            account_id=kwargs["account_id"],
            case_id=str(kwargs["case_id"]),
            draft={
                "id": "20",
                "draft_type": "support_appeal",
                "case_id": str(kwargs["case_id"]),
                "text": "Draft text",
                "requires_confirmation": True,
            },
        )

    async def _fake_proof_check(session, **kwargs):
        return ClaimsProofCheckOut(
            account_id=kwargs["account_id"],
            case_id=str(kwargs["case_id"]),
            passed=False,
            missing_evidence=["order_or_return_identity"],
            recommendations=["Add order_id or srid."],
            warnings=["case_not_ready_to_submit"],
        )

    async def _fake_submit(session, **kwargs):
        assert kwargs["payload"].confirm is False
        return ResultEventOut(
            module="claims",
            event_type="submit_blocked_confirmation_required",
            account_id=kwargs["account_id"],
            case_id=str(kwargs["case_id"]),
            title="Требуется ручное подтверждение",
            message="Отправка претензии требует явного confirm=true.",
            success=False,
            warnings=["manual_confirm_required"],
        )

    async def _fake_events(session, **kwargs):
        return [
            ResultEventOut(
                module="claims",
                event_type="draft_generated",
                account_id=kwargs["account_id"],
                case_id=str(kwargs["case_id"]),
                success=True,
            )
        ]

    monkeypatch.setattr(portal_router.claims_service, "get_case", _fake_get_case)
    monkeypatch.setattr(portal_router.claims_service, "attach_evidence", _fake_attach_evidence)
    monkeypatch.setattr(portal_router.claims_service, "generate_draft", _fake_generate_draft)
    monkeypatch.setattr(portal_router.claims_service, "proof_check", _fake_proof_check)
    monkeypatch.setattr(portal_router.claims_service, "submit_case_manual_confirm", _fake_submit)
    monkeypatch.setattr(portal_router.claims_service, "result_events", _fake_events)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(
        allowed_account_ids={1},
        account_roles={1: "manager"},
        case_account_id=1,
    )
    try:
        with TestClient(app) as client:
            evidence = client.post("/api/v1/portal/cases/10/evidence", json={"evidence_type": "photo", "title": "Photo"})
            draft = client.post("/api/v1/portal/cases/10/generate-draft", json={"draft_type": "support_appeal"})
            proof = client.post("/api/v1/portal/cases/10/proof-check", json={})
            submit = client.post("/api/v1/portal/cases/10/submit", json={"confirm": False})
            events = client.get("/api/v1/portal/cases/10/events")
    finally:
        app.dependency_overrides.clear()

    assert evidence.status_code == 200
    assert evidence.json()["evidence"][0]["id"] == "e1"
    assert draft.status_code == 200
    assert draft.json()["draft"]["requires_confirmation"] is True
    assert proof.status_code == 200
    assert proof.json()["passed"] is False
    assert submit.status_code == 200
    assert submit.json()["event_type"] == "submit_blocked_confirmation_required"
    assert events.status_code == 200
    assert events.json()[0]["event_type"] == "draft_generated"


def test_portal_operator_can_attach_claim_evidence_but_cannot_submit(monkeypatch) -> None:
    async def _fake_get_case(session, **kwargs):
        return CaseDetailOut(
            id=str(kwargs["case_id"]),
            case_type="defect",
            account_id=kwargs["account_id"],
            title="Defect candidate",
            evidence=[{"id": "e1", "case_id": str(kwargs["case_id"]), "evidence_type": "photo", "title": "Photo"}],
        )

    async def _fake_attach_evidence(session, **kwargs):
        return {"id": "e1", "case_id": str(kwargs["case_id"]), "evidence_type": kwargs["payload"].evidence_type}

    async def _fake_submit(session, **kwargs):
        raise AssertionError("operator must not submit claims")

    monkeypatch.setattr(portal_router.claims_service, "get_case", _fake_get_case)
    monkeypatch.setattr(portal_router.claims_service, "attach_evidence", _fake_attach_evidence)
    monkeypatch.setattr(portal_router.claims_service, "submit_case_manual_confirm", _fake_submit)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(
        allowed_account_ids={1},
        account_roles={1: "operator"},
        case_account_id=1,
    )
    try:
        with TestClient(app) as client:
            evidence = client.post("/api/v1/portal/cases/10/evidence", json={"evidence_type": "photo", "title": "Photo"})
            submit = client.post("/api/v1/portal/cases/10/submit", json={"confirm": True})
    finally:
        app.dependency_overrides.clear()

    assert evidence.status_code == 200
    assert submit.status_code == 403
    assert "manager" in submit.json()["detail"]


def test_portal_manager_can_manual_confirm_when_service_allows(monkeypatch) -> None:
    async def _fake_submit(session, **kwargs):
        assert kwargs["payload"].confirm is True
        return ResultEventOut(
            module="claims",
            event_type="submit_confirmed",
            account_id=kwargs["account_id"],
            case_id=str(kwargs["case_id"]),
            title="Claims submission confirmed",
            success=True,
        )

    monkeypatch.setattr(portal_router.claims_service, "submit_case_manual_confirm", _fake_submit)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(
        allowed_account_ids={1},
        account_roles={1: "manager"},
        case_account_id=1,
    )
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/portal/cases/10/submit", json={"confirm": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["event_type"] == "submit_confirmed"


def test_portal_reputation_admin_debug_requires_superuser(monkeypatch) -> None:
    async def _must_not_reach(*args, **kwargs):
        raise AssertionError("viewer must not reach reputation admin debug service")

    monkeypatch.setattr(portal_router.service.reputation, "admin_provider_status", _must_not_reach)
    app.dependency_overrides[get_current_user] = _override_normal_user
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/portal/admin/reputation/provider-status?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_portal_reputation_prompt_probe_dry_run_does_not_call_external_network(monkeypatch) -> None:
    async def _fake_probe(session, account, *, item_id, payload=None):
        assert item_id == "review:fb1"
        assert payload == {"dry_run": True}
        return {
            "status": "ok",
            "account_id": int(account.id),
            "item": {"id": item_id, "buyer_name_masked": "A***"},
            "probe": {"dry_run": True, "network_attempted": False},
            "instructions": "System instructions",
            "input_text": "Customer data",
        }

    monkeypatch.setattr(portal_router.service.reputation, "admin_prompt_probe", _fake_probe)
    app.dependency_overrides[get_current_user] = _override_superuser
    app.dependency_overrides[get_db_session] = _session_factory(allowed_account_ids={1})
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/portal/admin/reputation/prompt-probe?account_id=1&item_id=review:fb1",
                json={"dry_run": True},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["probe"]["dry_run"] is True
    assert body["probe"]["network_attempted"] is False
    assert body["item"]["buyer_name_masked"] == "A***"
