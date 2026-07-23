from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.models.accounts import WBAccount
from app.models.card_quality import CardQualityIssue
from app.models.operator import (
    ManualTaskItem,
    OperatorDraft,
    ResultEvent,
    UnifiedAction,
)
from app.models.problem_engine import (
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
)
from app.schemas.card_quality import CardQualityIssueRead
from app.schemas.claims import CaseListItemOut, ClaimsCasesPage
from app.schemas.evidence import EvidenceLedger, evidence_ledger
from app.schemas.operator import CaseType
from app.schemas.operator import (
    ActionStatus,
    DiagnosisOut,
    DiagnosisType,
    DraftOut,
    DraftType,
    ExternalStatus,
    Priority,
    ProfitDoctorOut,
    TrustState,
    UnifiedActionOut,
    ActionType,
)
from app.schemas.portal import (
    PortalActionRead,
    PortalDataBlock,
    PortalDataSyncStatusRead,
    PortalDataReadinessSource,
    PortalModuleHealth,
    PortalModuleHealthItem,
    PortalManualTaskItemUpdateRequest,
    PortalProductGroupingRead,
    PortalProductQualityRead,
    PortalResultEventRead,
    PortalResultEventsPage,
    PortalStockOpsInsightsRead,
)
from app.schemas.reputation import ReputationItemOut
from app.services.portal import PortalService
from app.services.reputation_adapter import ReputationAdapter
from app.core.config import Settings


class _FakeExecuteResult:
    def __init__(self, scalars=None):
        self._scalars = scalars or []

    def all(self):
        return []

    def scalars(self):
        return self

    def first(self):
        return self._scalars[0] if self._scalars else None

    def __iter__(self):
        return iter(self._scalars)


class _FakeSession:
    def __init__(self, *, unified_actions=None, manual_task_items=None):
        self.unified_actions = unified_actions or []
        self.manual_task_items = manual_task_items or []
        self.committed = False
        self.added = []
        self.next_id = 1000

    async def get(self, model, key):
        if model is UnifiedAction:
            for action in self.unified_actions:
                if getattr(action, "id", None) == key:
                    return action
            return None
        if model is not WBAccount:
            return None
        return SimpleNamespace(
            id=key,
            name="Test account",
            seller_name=None,
            external_account_id=None,
            timezone="Europe/Moscow",
            is_active=True,
        )

    async def execute(self, stmt):
        if "manual_task_items" in str(stmt):
            return _FakeExecuteResult(scalars=self.manual_task_items)
        return _FakeExecuteResult(scalars=self.unified_actions)

    def add(self, row):
        self.added.append(row)
        if isinstance(row, UnifiedAction) and row not in self.unified_actions:
            self.unified_actions.append(row)
        if isinstance(row, ManualTaskItem) and row not in self.manual_task_items:
            self.manual_task_items.append(row)

    def add_all(self, rows):
        for row in rows:
            self.add(row)

    async def flush(self):
        for row in self.added:
            if getattr(row, "id", None) is None:
                row.id = self.next_id
                self.next_id += 1

    async def refresh(self, row):
        return None

    async def commit(self):
        self.committed = True


class _FakeCheckerIssueSession(_FakeSession):
    def __init__(self, issue: CardQualityIssue, *, unified_actions=None):
        super().__init__(unified_actions=unified_actions)
        self.issue = issue

    async def get(self, model, key):
        if model is CardQualityIssue:
            return self.issue if key == self.issue.id else None
        return await super().get(model, key)


class _FakeProblemSession(_FakeSession):
    def __init__(
        self, instance: ProblemInstance, definition: ProblemDefinition | None = None
    ):
        super().__init__()
        self.instance = instance
        self.definition = definition

    async def get(self, model, key):
        if model is ProblemInstance:
            return self.instance if key == self.instance.id else None
        if model is ProblemDefinition:
            return (
                self.definition
                if self.definition is not None and key == self.definition.id
                else None
            )
        return await super().get(model, key)


def _empty_action_center_service() -> PortalService:
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health_checker_ok())
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.card_quality.quality_actions = AsyncMock(return_value=[])
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.grouping_beta.recommendation_actions = AsyncMock(return_value=[])
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.stock_control.action_candidates = AsyncMock(return_value=([], None))
    service.experiments.action_candidates = AsyncMock(return_value=[])
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )
    service.reputation.action_center_enabled = AsyncMock(return_value=False)
    service.reputation.reputation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    return service


def _checker_issue(status: str = "new") -> CardQualityIssue:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return CardQualityIssue(
        id=44,
        account_id=1,
        nm_id=245405620,
        issue_code="media_no_images",
        category="media",
        severity="critical",
        title="No images",
        business_explanation="Images are required.",
        recommended_fix="Add product photos.",
        status=status,
        fingerprint="fp",
        first_seen_at=now,
        last_seen_at=now,
    )


def _problem_instance(status: str = "new") -> ProblemInstance:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return ProblemInstance(
        id=101,
        account_id=1,
        problem_code="negative_unit_profit",
        problem_definition_id=201,
        rule_version_id=301,
        source_module="problem_engine",
        entity_type="product",
        entity_id="1001",
        nm_id=1001,
        vendor_code="VC-1",
        dedup_key="negative_unit_profit:1001",
        title="Товар продаётся в минус",
        explanation="Маржа ниже нуля.",
        recommendation="Проверьте цену и себестоимость.",
        severity="high",
        status=status,
        impact_type="confirmed_loss",
        money_impact_amount=5000,
        money_impact_currency="RUB",
        trust_state="confirmed",
        confidence="high",
        evidence_ledger_json={"formula_human": "profit < 0"},
        calculation_snapshot_json={},
        first_seen_at=now,
        last_seen_at=now,
    )


def _module_health() -> PortalModuleHealth:
    return PortalModuleHealth(
        finance=PortalModuleHealthItem(status="ok"),
        checker=PortalModuleHealthItem(status="not_configured"),
        stockops=PortalModuleHealthItem(status="not_configured"),
        grouping=PortalModuleHealthItem(status="disabled"),
    )


def _module_health_checker_ok() -> PortalModuleHealth:
    return PortalModuleHealth(
        finance=PortalModuleHealthItem(status="ok"),
        checker=PortalModuleHealthItem(status="ok"),
        stockops=PortalModuleHealthItem(status="not_configured"),
        grouping=PortalModuleHealthItem(status="disabled"),
    )


def _dashboard_bucket(code: str, *, severity: str = "warning", count: int = 1):
    return SimpleNamespace(
        code=code,
        severity=severity,
        count=count,
        business_impact=f"{code} impact",
        recommended_fix=f"{code} fix",
        financial_final_blocker=code
        in {"missing_manual_cost", "missing_cost_blocks_profit"},
    )


def _dashboard_health(*, issue_buckets=None):
    buckets = list(issue_buckets or [])
    return SimpleNamespace(
        account_id=1,
        issue_buckets=buckets,
        all_open_issues_total=sum(
            int(getattr(item, "count", 0) or 0) for item in buckets
        ),
        open_issues_total=sum(int(getattr(item, "count", 0) or 0) for item in buckets),
        active_sku_count=42,
        all_open_stock_issue_count=sum(
            int(getattr(item, "count", 0) or 0)
            for item in buckets
            if getattr(item, "code", "")
            in {"stock_without_sales", "dead_stock", "sales_without_stock"}
        ),
        missing_manual_cost_count=sum(
            int(getattr(item, "count", 0) or 0)
            for item in buckets
            if getattr(item, "code", "") == "missing_manual_cost"
        ),
        trust_state="trusted" if not buckets else "operational_provisional",
    )


def _dashboard_sources(
    status_by_code: dict[str, str] | None = None,
) -> list[PortalDataReadinessSource]:
    status_by_code = status_by_code or {}
    source_codes = sorted(
        {
            source
            for sources in PortalService.DASHBOARD_PULSE_SOURCE_CODES.values()
            for source in sources
        }
    )
    return [
        PortalDataReadinessSource(
            source_code=source_code,
            title=source_code,
            status=status_by_code.get(source_code, "fresh"),  # type: ignore[arg-type]
            last_synced_at=datetime(2026, 7, 12, 8, 0, tzinfo=timezone.utc),
            freshness_hours=1.0,
            required_for=["Dashboard"],
            blocks_calculation=[]
            if status_by_code.get(source_code, "fresh") == "fresh"
            else ["Dashboard"],
            target_href="/admin",
        )
        for source_code in source_codes
    ]


def _dashboard_sync(
    status_by_code: dict[str, str] | None = None,
) -> PortalDataSyncStatusRead:
    sources = _dashboard_sources(status_by_code)
    return PortalDataSyncStatusRead(
        account_id=1,
        overall_state="ok"
        if all(item.status == "fresh" for item in sources)
        else "warning",
        sources=sources,
    )


def _dashboard_service(
    *,
    issue_buckets=None,
    source_statuses: dict[str, str] | None = None,
    blockers=None,
    warnings=None,
) -> PortalService:
    service = PortalService()
    sync_status = _dashboard_sync(source_statuses)
    health = _dashboard_health(issue_buckets=issue_buckets)
    service.money.summary = AsyncMock(
        return_value={
            "kpis": {
                "revenue": 100000.0,
                "margin_percent": 18.5,
                "stock_value": 45000.0,
            },
            "cash_and_stock": {"stock_value": 45000.0},
        }
    )
    service.operator_snapshots.data_health = AsyncMock(return_value=health)
    service.money.data_blockers = AsyncMock(
        return_value=SimpleNamespace(
            blockers=list(blockers or []), warnings=list(warnings or [])
        )
    )
    service.data_sync_status = AsyncMock(return_value=sync_status)
    service.data_readiness = AsyncMock(
        return_value=SimpleNamespace(
            sources=sync_status.sources, sync_status=sync_status
        )
    )
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(items=[], owner_focus_actions=[])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=SimpleNamespace(
            status="ok", total=0, summary={}, by_outcome={}, recent_events=[], items=[]
        )
    )
    return service


def _pulse(overview, code: str):
    return next(item for item in overview.business_pulse if item.code == code)


def _doctor_result() -> ProfitDoctorOut:
    diagnosis = DiagnosisOut(
        id="diagnosis:finance:profit_leak:1001",
        diagnosis_type=DiagnosisType.PROFIT_LEAK,
        module="finance",
        account_id=1,
        nm_id=1001,
        title="Отрицательная прибыль по товару",
        summary="Прибыль товара ниже нуля.",
        reason="Прибыль товара ниже нуля.",
        priority=Priority.P1,
        trust_state=TrustState.PROVISIONAL,
        data={
            "estimated_impact_amount": 5000.0,
            "vendor_code": "VC-1",
            "product_title": "Article",
        },
    )
    action = UnifiedActionOut(
        id="action:finance:profit_leak:1001",
        action_type=ActionType.REVIEW_PROFIT,
        module="finance",
        source_module="finance",
        account_id=1,
        nm_id=1001,
        title="Проверить прибыль товара",
        summary="Проверить цену, себестоимость и рекламу.",
        reason="Прибыль товара ниже нуля.",
        next_step="Открыть Product 360.",
        priority=Priority.P1,
        expected_effect_amount=5000.0,
    )
    return ProfitDoctorOut(
        status="ok",
        account_id=1,
        trust_state=TrustState.PROVISIONAL,
        summary="Legacy-диагностика прибыли нашла 1 пункт для проверки.",
        total_signals=1,
        total_diagnoses=1,
        estimated_impact_amount=5000.0,
        top_profit_leaks=[diagnosis],
        root_causes=[diagnosis],
        today_plan=[action],
        product_diagnoses=[diagnosis],
        diagnoses=[diagnosis],
        actions=[action],
        unavailable_sources=["checker", "reputation", "claims"],
    )


def _product360_problem_action(
    *,
    problem_instance_id: int,
    problem_code: str,
    category: str,
    status: str = "new",
    severity: str = "high",
    impact_type: str = "probable_loss",
    trust_state: str = "estimated",
    amount: float | None = 1000.0,
    allowed_actions: list[str] | None = None,
    ledger: EvidenceLedger | None = None,
) -> PortalActionRead:
    allowed = allowed_actions or ["create_task", "recheck"]
    evidence = ledger or evidence_ledger(
        value=amount,
        value_type="money" if amount is not None else "text",
        confidence="blocked" if trust_state == "blocked" else "estimated",
        impact_type=impact_type,  # type: ignore[arg-type]
        formula_human=f"{problem_code} evidence",
        formula_code=f"{problem_code}.test",
        formula_id=f"{problem_code}:{problem_instance_id}",
        label=problem_code,
        source_table="mart_sku_daily",
        source_endpoint="GET /api/v1/portal/products/{nm_id}",
        row_count=1,
        sample_rows=[{"nm_id": 1001, "problem_code": problem_code}],
        missing_data=["cost_price: source_data_missing"]
        if impact_type == "data_blocker"
        else [],
        recheck_rule="Re-check after source data changes.",
    )
    return PortalActionRead(
        id=f"problem_engine:{problem_instance_id}",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id=str(problem_instance_id),
        account_id=1,
        nm_id=1001,
        action_type=problem_code,
        detector_code=problem_code,
        title=f"{problem_code} title",
        reason=f"{problem_code} explanation",
        next_step=f"{problem_code} recommendation",
        priority="P0" if impact_type == "data_blocker" else "P1",
        severity=severity,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        expected_effect_amount=amount,
        confidence="high" if trust_state in {"confirmed", "blocked"} else "medium",
        payload={
            "problem_instance_id": problem_instance_id,
            "problem_code": problem_code,
            "detector_code": problem_code,
            "category": category,
            "impact_type": impact_type,
            "money_impact_amount": amount,
            "trust_state": trust_state,
            "allowed_actions": allowed,
            "evidence_ledger": evidence.model_dump(mode="json"),
            "result_summary": {
                "status_flow": {
                    "initial_status": "new",
                    "current_status": status,
                    "changed": status != "new",
                },
                "before_snapshot": {
                    "money_impact_amount": amount,
                    "impact_type": impact_type,
                },
                "current_snapshot": {
                    "status": status,
                    "money_impact_amount": amount,
                    "impact_type": impact_type,
                },
                "finance_windows": {},
                "money_at_risk": {
                    "before": amount,
                    "after": None,
                    "delta": None,
                    "currency": "RUB",
                },
            },
        },
        evidence_ledger=evidence,
        impact_type=impact_type,
        trust_state=trust_state,
        allowed_actions=allowed,
        can_update=True,
        can_update_status=True,
    )


def _product360_result_event(
    problem_instance_id: int, *, outcome: str = "neutral"
) -> PortalResultEventRead:
    return PortalResultEventRead(
        id=f"result:{problem_instance_id}",
        account_id=1,
        problem_instance_id=problem_instance_id,
        problem_code="negative_unit_profit",
        source_module="result_tracking",
        source_id=f"problem:{problem_instance_id}",
        nm_id=1001,
        event_type="recheck_result",
        outcome=outcome,  # type: ignore[arg-type]
        message="Result ledger event",
        created_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_dashboard_overview_stock_without_sales_prevents_stock_all_clear() -> (
    None
):
    service = _dashboard_service(
        issue_buckets=[
            _dashboard_bucket("stock_without_sales", severity="warning", count=7)
        ]
    )

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    stock = _pulse(overview, "stock")
    assert stock.state == "warning"
    assert stock.has_risk is True
    assert stock.impact_type == "business_signal"
    assert stock.primary_action.screen_path == "/products"
    assert any(
        item.code == "stock_without_sales" for item in overview.top_attention_items
    )


@pytest.mark.asyncio
async def test_dashboard_overview_sales_or_stocks_stale_prevents_ok_state() -> None:
    service = _dashboard_service(
        source_statuses={"sales_orders": "stale", "stocks": "stale"}
    )

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    assert _pulse(overview, "sales").state == "stale"
    stock = _pulse(overview, "stock")
    assert stock.state == "stale"
    assert stock.has_risk is None
    assert overview.business_verdict.state == "stale"


@pytest.mark.asyncio
async def test_dashboard_overview_missing_cost_blocks_profit_and_data() -> None:
    service = _dashboard_service(
        issue_buckets=[
            _dashboard_bucket("missing_manual_cost", severity="critical", count=3)
        ]
    )

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    profit = _pulse(overview, "profit_margin")
    data = _pulse(overview, "data")
    assert profit.state == "missing_data"
    assert profit.has_data is False
    assert data.state == "blocked"
    assert data.impact_type == "data_blocker"
    assert overview.top_attention_items[0].code == "missing_manual_cost"
    assert overview.today_plan[0].screen_path == "/costs?focus=missing-costs"


@pytest.mark.asyncio
async def test_dashboard_overview_finance_mismatch_is_hidden_from_owner_attention() -> (
    None
):
    service = _dashboard_service(
        issue_buckets=[
            _dashboard_bucket(
                "finance_reconciliation_mismatch", severity="error", count=2
            )
        ]
    )

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    money = _pulse(overview, "money_at_risk")
    data = _pulse(overview, "data")
    assert money.state == "ok"
    assert money.impact_type == "finance_investigation"
    assert data.state == "ok"
    assert overview.top_attention_items == []


@pytest.mark.asyncio
async def test_dashboard_overview_clean_fresh_checked_detector_can_return_ok_and_no_risk() -> (
    None
):
    service = _dashboard_service()

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    stock = _pulse(overview, "stock")
    assert stock.state == "ok"
    assert stock.checked is True
    assert stock.has_data is True
    assert stock.has_risk is False
    assert overview.business_verdict.state == "ok"
    assert overview.business_verdict.has_risk is False


@pytest.mark.asyncio
async def test_dashboard_overview_top_attention_items_use_highest_severity_buckets() -> (
    None
):
    service = _dashboard_service(
        issue_buckets=[
            _dashboard_bucket("stock_without_sales", severity="warning", count=10),
            _dashboard_bucket("missing_chrt_id", severity="warning", count=5),
            _dashboard_bucket("missing_manual_cost", severity="critical", count=1),
        ]
    )

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    assert overview.top_attention_items[0].code == "missing_manual_cost"
    assert {item.code for item in overview.top_attention_items[:3]} == {
        "missing_manual_cost",
        "missing_chrt_id",
        "stock_without_sales",
    }


@pytest.mark.asyncio
async def test_dashboard_overview_next_action_routes_to_exact_screen() -> None:
    service = _dashboard_service(
        issue_buckets=[
            _dashboard_bucket("sales_without_stock", severity="warning", count=1)
        ]
    )

    overview = await service.dashboard_overview(
        _FakeSession(), account_id=1, date_from=None, date_to=None, limit=10
    )

    attention = overview.top_attention_items[0]
    assert attention.code == "sales_without_stock"
    assert attention.primary_action.screen_path == "/admin?domain=stocks"
    assert overview.today_plan[0].screen_path == "/admin?domain=stocks"


def _data_warning_action(code: str, **extra):
    service = PortalService()
    rows = [{"code": code, "title": extra.pop("title", code), **extra}]
    return service._blocker_actions(
        SimpleNamespace(meta={"account_id": 1}, blockers=[], warnings=rows)
    )[0]


def _data_blocker_action(code: str, **extra):
    service = PortalService()
    rows = [{"code": code, "title": extra.pop("title", code), **extra}]
    return service._blocker_actions(
        SimpleNamespace(meta={"account_id": 1}, blockers=rows, warnings=[])
    )[0]


def test_portal_blocker_actions_stock_without_sales_is_business_signal_not_data_blocker() -> (
    None
):
    action = _data_warning_action("stock_without_sales", affected_amount=12000.0)

    assert action.source_module == "data_quality"
    assert action.source == "data_warning"
    assert action.impact_type == "blocked_cash"
    assert action.trust_state == "estimated"
    assert action.next_step == "Открыть товар"
    assert action.payload["issue_nature"] == "business_signal"
    assert action.payload["fixability"] == "business_decision"
    assert action.payload["owner_type"] == "business"
    assert action.payload["can_user_fix_inside_platform"] is False
    assert action.money_trust is not None
    assert action.money_trust.impact_kind == "blocked_cash"


def test_portal_blocker_actions_missing_chrt_id_is_sync_warning_not_user_blocker() -> (
    None
):
    action = _data_warning_action("missing_chrt_id")

    assert action.impact_type == "system_warning"
    assert action.trust_state == "provisional"
    assert action.next_step == "Запустить синхронизацию карточек"
    assert action.payload["issue_nature"] == "sync_waiting"
    assert action.payload["fixability"] == "sync_required"
    assert action.payload["owner_type"] == "system"
    assert action.payload["can_user_fix_inside_platform"] is False
    assert action.money_trust is not None
    assert action.money_trust.impact_kind != "data_blocker"


def test_portal_blocker_actions_finance_mismatch_is_hidden() -> None:
    service = PortalService()
    rows = [
        {
            "code": "finance_reconciliation_mismatch",
            "title": "finance_reconciliation_mismatch",
            "affected_revenue": 5000.0,
        }
    ]

    actions = service._blocker_actions(
        SimpleNamespace(meta={"account_id": 1}, blockers=[], warnings=rows)
    )

    assert actions == []


def test_portal_blocker_actions_missing_manual_cost_remains_data_blocker() -> None:
    action = _data_blocker_action("missing_manual_cost", affected_revenue=5000.0)

    assert action.impact_type == "data_blocker"
    assert action.trust_state == "blocked"
    assert action.next_step == "Загрузить или заполнить себестоимость"
    assert action.payload["issue_nature"] == "data_blocker"
    assert action.payload["fixability"] == "fix_in_platform"
    assert action.payload["owner_type"] == "seller"
    assert action.payload["can_user_fix_inside_platform"] is True
    assert action.money_trust is not None
    assert action.money_trust.impact_kind in {"data_blocker", "blocked_revenue"}


def test_portal_action_read_data_quality_payload_issue_nature_overrides_data_blocker_default() -> (
    None
):
    action = PortalActionRead(
        id="data_warning:stock_without_sales",
        source="data_warning",
        source_module="data_quality",
        source_id="stock_without_sales",
        account_id=1,
        action_type="DATA_FIX",
        title="Остатки без продаж",
        priority="P2",
        severity="medium",
        status="new",
        impact_type="data_blocker",
        trust_state="blocked",
        payload={
            "code": "stock_without_sales",
            "issue_nature": "business_signal",
            "fixability": "business_decision",
            "owner_type": "business",
            "can_user_fix_inside_platform": False,
            "money_trust": {
                "state": "blocked",
                "impact_kind": "data_blocker",
                "display_label": "Данные заблокированы",
                "amount_label": "Не хватает данных",
                "show_as_confirmed_money": False,
                "seller_visible_by_default": True,
                "reason": "Legacy data warning was flattened as a blocker.",
                "evidence_trust_state": "blocked",
                "impact_trust_state": "blocked",
                "saved_money_claimed": False,
            },
        },
    )

    assert action.impact_type == "blocked_cash"
    assert action.trust_state == "estimated"
    assert action.payload["issue_nature"] == "business_signal"
    assert action.payload["fixability"] == "business_decision"
    assert action.payload["owner_type"] == "business"
    assert action.payload["can_user_fix_inside_platform"] is False
    assert action.money_trust is not None
    assert action.money_trust.impact_kind == "blocked_cash"


def _product360_control_panel_service(
    *,
    problem_actions: list[PortalActionRead] | None = None,
    checker_quality: PortalProductQualityRead | None = None,
    data_issues: list[dict[str, object]] | None = None,
    result_events: list[PortalResultEventRead] | None = None,
) -> PortalService:
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health_checker_ok())
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={
                "nm_id": 1001,
                "title": "Article",
                "vendor_code": "VC-1",
                "barcode": "BC-1",
                "photo_url": "https://cdn.example.test/card.jpg",
                "subject_name": "Sneakers",
                "sync_freshness": {"finance": "fresh"},
            },
            money={
                "revenue": 1000.0,
                "for_pay": 900.0,
                "profit": {"after_source_ads": 250.0},
                "price": 1990.0,
            },
            kpis={"revenue": 1000.0},
            stock={"quantity": 7.0, "days_left": 5},
            ads={"spend": 50.0},
            price_safety={"price": 1990.0, "status": "safe"},
            cost_coverage={"cost_truth_level": "trusted"},
            expense_breakdown=None,
            trust={"state": "trusted"},
            reconciliation={"status": "ok"},
            finality={"profit_final": True},
            actions=[],
            next_actions=[],
            issues=[],
            problems=[],
            operations={},
            funnel={},
        )
    )
    service.money.money.dashboard.article_audit = AsyncMock(return_value=None)
    service.data_quality.list_issues = AsyncMock(
        return_value=SimpleNamespace(items=list(data_issues or []))
    )
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.checker.product_quality = AsyncMock(
        return_value=checker_quality
        or PortalProductQualityRead(status="ok", nm_id=1001, score=88)
    )
    service.grouping_beta.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(
            status="disabled", nm_id=1001, message="grouping beta is disabled"
        )
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )
    service._problem_instance_actions = AsyncMock(
        return_value=list(problem_actions or [])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=PortalResultEventsPage(
            total=len(result_events or []),
            limit=10,
            offset=0,
            items=list(result_events or []),
            summary={"result_event_count": len(result_events or [])},
        )
    )
    service.experiments.list_product_events = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.experiments.product_block = AsyncMock(
        return_value={"status": "empty", "active_experiments": [], "latest_results": []}
    )
    service.experiments.action_candidates = AsyncMock(return_value=[])
    service.ab_photo_tests.product_block = AsyncMock(return_value=None)
    service.photo_studio.status = AsyncMock(
        return_value=PortalDataBlock(status="empty", data={})
    )
    service.stock_control.product_stock_insights = AsyncMock(
        return_value=PortalStockOpsInsightsRead(
            status="empty", account_id=1, nm_id=1001
        )
    )
    service.stock_control.action_candidates = AsyncMock(return_value=([], None))
    service.claims_adapter.product_360 = AsyncMock(
        return_value={"status": "not_configured", "items": []}
    )
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.claims_factory.list_cases = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.reputation.product_360 = AsyncMock(
        return_value=PortalDataBlock(status="not_configured", data={})
    )
    service.reputation.reputation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    return service


@pytest.mark.asyncio
async def test_portal_overview_success_uses_money_summary_blockers_actions_and_products() -> (
    None
):
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health())
    service.money.summary = AsyncMock(
        return_value={
            "trust": {
                "trust_state": "operational_provisional",
                "blocked_reasons": ["finance_mismatch"],
            },
            "finance_reconciliation": {"closed_finance_date_to": "2026-05-31"},
            "cost_coverage": {"status": "partial"},
            "quality": {"supplier_cost_coverage_percent": 80.0},
            "kpis": {"expense_data_quality": "partial", "cash_on_wb_current": None},
            "expenses": {"unallocated_expenses": 1234.0},
        }
    )
    service.money.data_blockers = AsyncMock(
        return_value={
            "overall_state": "blocked",
            "blockers": [{"code": "finance_mismatch", "title": "Сверить финансы"}],
            "warnings": [],
        }
    )
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 10,
                    "account_id": 1,
                    "action_type": "FINANCE_REVIEW",
                    "title": "Проверить расхождение",
                    "priority": "high",
                    "status": "new",
                }
            ]
        )
    )
    service.money.articles = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "nm_id": 1001,
                    "title": "Article",
                    "money": {"revenue": 1000.0, "profit": {"after_source_ads": 200.0}},
                    "stock": {"quantity": 3},
                    "ads": {"spend": 50.0},
                    "data_trust": {"trust_state": "trusted"},
                }
            ]
        )
    )
    service.profit_doctor.diagnose = AsyncMock(return_value=_doctor_result())
    service.checker.quality_actions = AsyncMock(return_value=([], "checker"))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))

    overview = await service.overview(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        limit=1,
    )

    assert overview.account is not None
    assert overview.money_summary["status"] == "ok"
    assert overview.money_summary["kpis"]["cash_on_wb_current"] is None
    assert overview.data_trust["trust_state"] == "operational_provisional"
    assert overview.cost_status["unallocated_expenses"] == 1234.0
    assert overview.doctor_summary["total_diagnoses"] == 1
    assert overview.doctor_summary["trust_state"] == "provisional"
    assert overview.top_problems[0]["type"] == "profit_leak"
    assert overview.operator_actions[0]["type"] == "review_profit"
    assert overview.product_risks[0]["nm_id"] == 1001
    assert overview.reputation["status"] == "disabled"
    assert overview.claims["status"] == "disabled"
    assert len(overview.top_actions) == 1
    assert len(overview.top_products) == 1
    assert overview.top_products[0].nm_id == 1001
    assert "checker" in overview.unavailable_sources


@pytest.mark.asyncio
async def test_portal_overview_without_account_returns_safe_empty() -> None:
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health_checker_ok())

    overview = await service.overview(
        _FakeSession(),
        account_id=None,
        date_from=None,
        date_to=None,
        limit=10,
    )

    assert overview.account is None
    assert overview.unavailable_sources == ["account"]
    assert overview.money_summary is None


@pytest.mark.asyncio
async def test_portal_overview_money_unavailable_preserves_unknown_values_as_unavailable() -> (
    None
):
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health())
    service.money.summary = AsyncMock(side_effect=RuntimeError("boom"))
    service.money.data_blockers = AsyncMock(
        return_value={"blockers": [], "warnings": []}
    )
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.articles = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.profit_doctor.diagnose = AsyncMock(return_value=_doctor_result())
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))

    overview = await service.overview(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        limit=10,
    )

    assert overview.money_summary == {
        "status": "unavailable",
        "message": "money_summary is not available",
    }
    assert overview.cost_status["status"] == "unavailable"
    assert "money_summary" in overview.unavailable_sources


@pytest.mark.asyncio
async def test_portal_overview_optional_module_action_failure_does_not_500() -> None:
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health())
    service.money.summary = AsyncMock(
        return_value={"trust": {"trust_state": "trusted"}, "kpis": {}}
    )
    service.money.data_blockers = AsyncMock(
        return_value={"blockers": [], "warnings": []}
    )
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.articles = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.profit_doctor.diagnose = AsyncMock(return_value=_doctor_result())
    service.checker.quality_actions = AsyncMock(
        side_effect=RuntimeError("checker down")
    )
    service.grouping.recommendation_actions = AsyncMock(
        side_effect=RuntimeError("grouping down")
    )

    overview = await service.overview(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        limit=10,
    )

    assert overview.top_actions == []
    assert {"checker", "grouping"}.issubset(set(overview.unavailable_sources))


@pytest.mark.asyncio
async def test_portal_overview_profit_doctor_failure_does_not_500() -> None:
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health())
    service.money.summary = AsyncMock(
        return_value={"trust": {"trust_state": "trusted"}, "kpis": {}}
    )
    service.money.data_blockers = AsyncMock(
        return_value={"blockers": [], "warnings": []}
    )
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.articles = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.profit_doctor.diagnose = AsyncMock(side_effect=RuntimeError("doctor down"))
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))

    overview = await service.overview(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        limit=10,
    )

    assert overview.doctor_summary["status"] == "unavailable"
    assert "profit_doctor" in overview.unavailable_sources
    assert overview.top_problems == []
    assert overview.operator_actions == []


@pytest.mark.asyncio
async def test_portal_actions_aggregates_and_filters_finance_dq_and_costs() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(
            total=1,
            items=[
                {
                    "id": 10,
                    "account_id": 1,
                    "action_type": "ADS_REVIEW",
                    "title": "Проверить рекламу",
                    "priority": "medium",
                    "status": "new",
                    "confidence": "medium",
                    "linked_entity": {"nm_id": 1001, "sku_id": 11},
                }
            ],
        )
    )
    service.money.data_blockers = AsyncMock(
        return_value={
            "meta": {"account_id": 1},
            "blockers": [
                {
                    "code": "missing_manual_cost",
                    "title": "Нет себестоимости",
                    "business_impact": "Прибыль ненадежна",
                    "affected_revenue": 50000.0,
                }
            ],
            "warnings": [],
        }
    )
    service.data_quality.list_issues = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 20,
                    "account_id": 1,
                    "code": "expense_finance_report_missing",
                    "severity": "error",
                    "effective_financial_final_blocker": True,
                    "message": "Нет finance report",
                    "payload": {"affectedRevenue": 100000.0},
                }
            ]
        )
    )
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 30,
                    "account_id": 1,
                    "nm_id": 1002,
                    "sku_id": None,
                    "vendor_code": "VC-1",
                    "is_ambiguous": True,
                }
            ]
        )
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["data_quality"],
        priority=["P0"],
        limit=20,
        offset=0,
    )

    assert page.total == 2
    assert {item.source_module for item in page.items} == {"data_quality"}
    assert {item.priority for item in page.items} == {"P0"}
    assert any(item.source_id == "20" for item in page.items)
    assert any(item.source_id == "missing_manual_cost" for item in page.items)


@pytest.mark.asyncio
async def test_portal_actions_includes_checker_quality_actions() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="checker:77",
                    source="checker_issues",
                    source_module="checker",
                    source_id="77",
                    account_id=1,
                    action_type="CARD_QUALITY_FIX",
                    title="Улучшить название",
                    priority="P2",
                    severity="high",
                    status="new",
                    reason="Название слишком короткое",
                    nm_id=1001,
                    payload={"category": "title"},
                )
            ],
            None,
        )
    )
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["checker"],
        priority=None,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].source_module == "checker"
    assert page.items[0].action_type == "CARD_QUALITY_FIX"
    assert page.items[0].can_update_status is True
    assert page.items[0].can_update is True
    assert page.items[0].guided_fix["method"] == "open_card_quality"
    assert page.items[0].guided_fix["legacy_method"] == "open_product"


@pytest.mark.asyncio
async def test_portal_actions_default_excludes_beta_sources() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.card_quality.quality_actions = AsyncMock(return_value=[])
    service._module_health = AsyncMock(return_value=_module_health_checker_ok())
    service.grouping.recommendation_actions = AsyncMock(
        side_effect=AssertionError("grouping must be beta gated")
    )
    service.grouping_beta.recommendation_actions = AsyncMock(
        side_effect=AssertionError("grouping_beta must be beta gated")
    )
    service.reputation_adapter.reputation_actions = AsyncMock(
        side_effect=AssertionError("reputation must be beta gated")
    )
    service.claims_adapter.claims_actions = AsyncMock(
        side_effect=AssertionError("claims must be beta gated")
    )
    service.stock_control.action_candidates = AsyncMock(
        side_effect=AssertionError("stockops must be beta gated")
    )
    service.experiments.action_candidates = AsyncMock(
        side_effect=AssertionError("experiments must be beta gated")
    )
    service.profit_doctor.diagnose = AsyncMock(
        side_effect=AssertionError("profit doctor must be beta gated")
    )
    beta_unified = UnifiedAction(
        id=900,
        account_id=1,
        source_module="claims",
        source_id="claim:900",
        action_type="DRAFT_CLAIM",
        status="new",
        priority="P1",
        title="Prepare claim",
    )
    manual_unified = UnifiedAction(
        id=901,
        account_id=1,
        source_module="manual",
        source_id="manual:901",
        action_type="MANUAL_REVIEW",
        status="new",
        priority="P3",
        title="Manual action",
    )

    page = await service.actions(
        _FakeSession(unified_actions=[beta_unified, manual_unified]),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].source_module == "manual"
    assert {item.source_module for item in page.items}.isdisjoint(
        {"grouping_beta", "stockops", "reputation", "claims", "experiments"}
    )


@pytest.mark.asyncio
async def test_portal_actions_dynamic_problem_flag_disables_dynamic_source_but_keeps_legacy_fallback() -> (
    None
):
    service = PortalService()
    service.settings = SimpleNamespace(
        dynamic_problem_engine_enabled=False,
        dynamic_problem_engine_test_account_ids=[],
        show_legacy_problem_cards=True,
    )
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service._problem_instance_actions = AsyncMock(
        side_effect=AssertionError("dynamic source must be skipped")
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.card_quality.quality_actions = AsyncMock(return_value=[])
    service._module_health = AsyncMock(return_value=_module_health_checker_ok())

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        limit=20,
        offset=0,
    )

    assert page.total == 0
    service._problem_instance_actions.assert_not_awaited()


@pytest.mark.asyncio
async def test_portal_actions_include_beta_true_keeps_wide_sources() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.card_quality.quality_actions = AsyncMock(return_value=[])
    service._module_health = AsyncMock(return_value=_module_health())
    service.grouping.recommendation_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="grouping:1",
                    source="grouping_recommendations",
                    source_module="grouping",
                    source_id="group:1",
                    account_id=1,
                    action_type="GROUPING_RECOMMENDATION",
                    title="Review grouping",
                )
            ],
            None,
        )
    )
    service.grouping_beta.recommendation_actions = AsyncMock(return_value=[])
    service.reputation_adapter.reputation_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="reputation:1",
                    source="reputation_adapter",
                    source_module="reputation",
                    source_id="review:1",
                    account_id=1,
                    action_type="DRAFT_REPLY",
                    title="Reply to review",
                )
            ],
            None,
        )
    )
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.stock_control.action_candidates = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="stockops:1",
                    source="stock_control",
                    source_module="stockops",
                    source_id="stock:1",
                    account_id=1,
                    action_type="regional_redistribution",
                    title="Review stock",
                )
            ],
            None,
        )
    )
    service.experiments.action_candidates = AsyncMock(return_value=[])
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        include_beta=True,
        limit=20,
        offset=0,
    )

    modules = {item.source_module for item in page.items}
    assert {"grouping_beta", "reputation", "stockops"}.issubset(modules)
    service.grouping.recommendation_actions.assert_awaited_once()
    service.reputation_adapter.reputation_actions.assert_awaited_once()
    service.stock_control.action_candidates.assert_awaited_once()


@pytest.mark.asyncio
async def test_portal_actions_default_items_have_frontend_contract_fields() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 10,
                    "account_id": 1,
                    "action_type": "FINANCE_REVIEW",
                    "title": "Проверить финансы",
                    "priority": "high",
                    "status": "new",
                    "expected_effect_amount": 5000.0,
                    "linked_entity": {"nm_id": 1001},
                }
            ]
        )
    )
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 20,
                    "account_id": 1,
                    "domain": "finance",
                    "severity": "error",
                    "code": "missing_manual_cost",
                    "message": "Missing cost.",
                    "payload": {"affectedRevenue": 1000.0},
                    "effective_financial_final_blocker": True,
                }
            ]
        )
    )
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="checker:77",
                    source="checker_issues",
                    source_module="checker",
                    source_id="77",
                    account_id=1,
                    action_type="CARD_QUALITY_FIX",
                    title="Улучшить название",
                    priority="P2",
                    severity="high",
                    status="new",
                    reason="Название слишком короткое",
                    nm_id=1002,
                    payload={"category": "title"},
                    can_update_status=True,
                )
            ],
            None,
        )
    )
    service.card_quality.quality_actions = AsyncMock(return_value=[])
    service._module_health = AsyncMock(return_value=_module_health())
    manual_unified = UnifiedAction(
        id=901,
        account_id=1,
        source_module="manual",
        source_id="manual:901",
        action_type="MANUAL_REVIEW",
        status="new",
        priority="P3",
        title="Manual action",
        summary="Manual follow-up",
    )

    page = await service.actions(
        _FakeSession(unified_actions=[manual_unified]),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        limit=20,
        offset=0,
    )

    required = {
        "id",
        "source",
        "source_module",
        "source_id",
        "account_id",
        "action_type",
        "title",
        "priority",
        "severity",
        "status",
        "reason",
        "next_step",
        "expected_effect_amount",
        "expected_impact_amount",
        "confidence",
        "can_update_status",
        "can_update",
        "can_update_reason",
        "guided_fix",
        "evidence_state",
        "payload",
    }
    assert page.total == 4
    for item in page.items:
        dumped = item.model_dump()
        assert required.issubset(dumped)
        assert item.id
        assert item.source
        assert item.source_module in PortalService.MVP_ACTION_MODULES
        assert item.evidence_state in {
            "full_evidence",
            "partial_evidence",
            "missing_evidence",
            "read_only_signal",
        }
        assert item.source_id
        assert item.account_id == 1
        assert item.action_type
        assert item.title
        assert item.priority in {"P0", "P1", "P2", "P3", "P4"}
        assert item.severity in {"critical", "high", "medium", "low"}
        assert item.status in {
            "new",
            "in_progress",
            "done",
            "postponed",
            "ignored",
            "blocked",
        }
        assert item.confidence in {"high", "medium", "low"}
        assert isinstance(item.can_update_status, bool)
        assert isinstance(item.can_update, bool)
        assert isinstance(item.guided_fix, dict)
        assert isinstance(item.payload, dict)
        if not item.can_update:
            assert item.can_update_status is False
            assert item.can_update_reason


@pytest.mark.asyncio
async def test_portal_update_manual_task_item_persists_product_progress() -> None:
    row = UnifiedAction(
        id=901,
        account_id=1,
        source_module="manual",
        source_id="manual:901",
        action_type="MANUAL_REVIEW",
        status="new",
        priority="P2",
        title="Проверить товары",
        payload_json={
            "manual_task": True,
            "selected_products": [
                {"nm_id": 111, "title": "Первый товар"},
                {
                    "nm_id": 222,
                    "title": "Второй товар",
                    "manual_task_item_key": "custom-2",
                },
            ],
        },
    )
    session = _FakeSession(unified_actions=[row])

    result = await PortalService().update_manual_task_item(
        session,
        account_id=1,
        action_id=901,
        item_key="product-1",
        payload=PortalManualTaskItemUpdateRequest(
            account_id=1,
            status="done",
            comment="Первый товар исправлен.",
        ),
        user_id=5,
    )

    assert session.committed is True
    assert row.status == "in_progress"
    assert [item.item_key for item in session.manual_task_items] == [
        "product-1",
        "custom-2",
    ]
    assert [item.status for item in session.manual_task_items] == ["done", "pending"]
    progress = result.payload["manual_task_progress"]
    assert progress["total"] == 2
    assert progress["done"] == 1
    assert progress["pending"] == 1
    assert progress["items"][0]["item_key"] == "product-1"
    assert progress["items"][0]["status"] == "done"


@pytest.mark.asyncio
async def test_portal_actions_not_configured_checker_adds_setup_action_without_fake_product_issue() -> (
    None
):
    service = PortalService()
    service._module_health = AsyncMock(return_value=_module_health())
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["checker"],
        priority=None,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].source == "integration_setup"
    assert page.items[0].action_type == "integration_setup"
    assert page.items[0].title == "Подключите Checker, чтобы видеть проблемы карточек"
    assert page.items[0].payload["product_issue"] is False
    assert page.items[0].nm_id is None
    assert all(item.action_type != "CARD_QUALITY_FIX" for item in page.items)


@pytest.mark.asyncio
async def test_portal_actions_includes_stockops_signal_actions_without_external_write() -> (
    None
):
    service = PortalService()
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.stock_control.action_candidates = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="stockops:1:plan:1001",
                    source="stockops_signals",
                    source_module="stockops",
                    source_id="1:plan:regional_redistribution:1001",
                    account_id=1,
                    nm_id=1001,
                    action_type="regional_redistribution",
                    title="Review stock redistribution candidate",
                    priority="P1",
                    severity="high",
                    payload={
                        "run_id": 1,
                        "write_status": "disabled",
                        "marketplace_change": False,
                    },
                )
            ],
            None,
        )
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["stockops"],
        priority=None,
        include_beta=True,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].source_module == "stockops"
    assert page.items[0].action_type == "regional_redistribution"
    assert page.items[0].can_update_status is True
    assert page.items[0].guided_fix["method"] == "open_stock_planner"
    assert page.items[0].payload["marketplace_change"] is False


@pytest.mark.asyncio
async def test_portal_actions_includes_claims_report_anomaly_action() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    service.claims_adapter.data_quality.list_issues = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 79,
                    "account_id": 1,
                    "domain": "finance",
                    "severity": "error",
                    "code": "finance_without_sale",
                    "nm_id": 1003,
                    "message": "Finance row has no matching sale.",
                    "payload": {"affectedRevenue": 1700.0},
                    "effective_financial_final_blocker": True,
                }
            ]
        )
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["claims"],
        priority=None,
        include_beta=True,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].source_module == "claims"
    assert page.items[0].action_type == "report_anomaly_candidate"
    assert page.items[0].linked_entity["case_type"] == "report_anomaly"
    assert page.items[0].guided_fix["payload"]["case_type"] == "report_anomaly"


@pytest.mark.asyncio
async def test_portal_actions_merge_unified_and_generated_modules_with_filters_and_priority() -> (
    None
):
    service = PortalService()
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 10,
                    "account_id": 1,
                    "action_type": "FINANCE_REVIEW",
                    "title": "Проверить финансы",
                    "priority": "high",
                    "status": "new",
                    "expected_effect_amount": 5000.0,
                    "linked_entity": {"nm_id": 1001},
                }
            ]
        )
    )
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="checker:card:1002",
                    source="checker_issues",
                    source_module="checker",
                    source_id="card:1002",
                    account_id=1,
                    action_type="CARD_QUALITY_FIX",
                    title="Исправить карточку",
                    priority="P2",
                    nm_id=1002,
                )
            ],
            None,
        )
    )
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    reputation_action = UnifiedActionOut(
        id="action:reputation:review:900",
        action_type=ActionType.DRAFT_REPLY,
        module="reputation",
        source_module="reputation",
        source_id="review:900",
        account_id=1,
        nm_id=1003,
        title="Ответить на негативный отзыв",
        priority=Priority.P2,
        expected_effect_amount=3000.0,
    )
    claims_action = UnifiedActionOut(
        id="action:claims:defect:901",
        action_type=ActionType.DRAFT_CLAIM,
        module="claims",
        source_module="claims",
        source_id="defect:901",
        account_id=1,
        nm_id=1004,
        title="Подготовить претензию",
        priority=Priority.P1,
        expected_effect_amount=25000.0,
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok",
            account_id=1,
            summary="plan",
            total_signals=2,
            total_diagnoses=2,
            today_plan=[reputation_action, claims_action],
        )
    )
    persisted = UnifiedAction(
        id=501,
        account_id=1,
        source_module="costs",
        source_id="cost:501",
        nm_id=1005,
        action_type="FIX_COSTS",
        status="new",
        priority="P0",
        title="Заполнить себестоимость",
        summary="Нет себестоимости.",
        payload_json={"expected_effect_amount": 100000.0},
    )
    shadow_claim = UnifiedAction(
        id=777,
        account_id=1,
        source_module="claims",
        source_id="defect:901",
        nm_id=1004,
        action_type="draft_claim",
        status="done",
        priority="P1",
        title="Подготовить претензию",
        payload_json={"shadow_synthetic": True, "last_comment": "handled locally"},
    )

    page = await service.actions(
        _FakeSession(unified_actions=[persisted, shadow_claim]),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        include_beta=True,
        limit=20,
        offset=0,
    )

    modules = {item.source_module for item in page.items}
    assert {"finance", "checker", "reputation", "claims", "costs"}.issubset(modules)
    assert page.items[0].source_module == "costs"
    assert page.items[0].can_update is True
    assert page.items[0].guided_fix["method"] == "upload_costs"
    assert page.items[0].guided_fix["legacy_method"] == "upload_cost"
    assert any(
        item.source_module == "claims"
        and item.can_update is True
        and item.status == "done"
        for item in page.items
    )

    claims_only = await service.actions(
        _FakeSession(unified_actions=[persisted, shadow_claim]),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["claims"],
        priority=["P1"],
        nm_id=1004,
        action_type=["draft_claim"],
        include_beta=True,
        limit=20,
        offset=0,
    )

    assert claims_only.total == 1
    assert claims_only.items[0].source_module == "claims"
    assert claims_only.items[0].status == "done"
    assert claims_only.items[0].guided_fix["method"] == "generate_claim_draft"
    assert claims_only.items[0].guided_fix["legacy_method"] == "open_case"


@pytest.mark.asyncio
async def test_portal_actions_dedupes_finance_and_doctor_for_same_problem() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 10,
                    "account_id": 1,
                    "action_type": "FINANCE_REVIEW",
                    "title": "Проверить финансы",
                    "priority": "high",
                    "status": "new",
                    "expected_effect_amount": 5000.0,
                    "linked_entity": {"nm_id": 1001},
                    "category": "profit_leak",
                    "why": "Маржа стала отрицательной.",
                }
            ]
        )
    )
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok",
            account_id=1,
            summary="plan",
            total_signals=1,
            total_diagnoses=1,
            today_plan=[
                UnifiedActionOut(
                    id="action:finance:profit_leak:1001",
                    action_type=ActionType.REVIEW_PROFIT,
                    module="finance",
                    source_module="finance",
                    source_id="doctor:profit:1001",
                    account_id=1,
                    nm_id=1001,
                    title="Проверить прибыль товара",
                    priority=Priority.P1,
                    expected_effect_amount=7000.0,
                    reason="Legacy-диагностика прибыли нашла устойчивую просадку прибыли по карточке.",
                    next_step="Открыть Product 360 и проверить цену, себестоимость и рекламу.",
                    data={"diagnosis_type": "profit_leak"},
                )
            ],
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["finance"],
        priority=None,
        nm_id=1001,
        action_type=None,
        include_beta=True,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    item = page.items[0]
    assert item.priority == "P1"
    assert item.expected_effect_amount == 7000.0
    assert "Product 360" in item.next_step
    assert len(item.payload["source_references"]) == 2
    assert {ref["source"] for ref in item.payload["source_references"]} == {
        "finance_actions",
        "profit_doctor",
    }


@pytest.mark.asyncio
async def test_portal_actions_dedupes_duplicate_actions_from_same_source() -> None:
    service = PortalService()
    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    duplicate_a = PortalActionRead(
        id="checker:card:1001:a",
        source="checker_issues",
        source_module="checker",
        source_id="card:1001:a",
        account_id=1,
        nm_id=1001,
        action_type="CARD_QUALITY_FIX",
        title="Исправить карточку",
        priority="P2",
        status="new",
        expected_effect_amount=1000.0,
        reason="Title is weak.",
    )
    duplicate_b = duplicate_a.model_copy(
        update={
            "id": "checker:card:1001:b",
            "source_id": "card:1001:b",
            "priority": "P1",
            "expected_effect_amount": 2500.0,
            "next_step": "Open Product 360 and fix title.",
        }
    )
    service.checker.quality_actions = AsyncMock(
        return_value=([duplicate_a, duplicate_b], None)
    )
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["checker"],
        priority=None,
        nm_id=1001,
        action_type=None,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].priority == "P1"
    assert page.items[0].expected_effect_amount == 2500.0
    assert len(page.items[0].payload["source_references"]) == 2


def test_portal_action_dedupe_keeps_local_card_quality_issues_separate() -> None:
    service = PortalService()
    issue_a = PortalActionRead(
        id="card_quality:6175",
        source="card_quality_issues",
        source_module="checker",
        source_id="6175",
        account_id=1,
        nm_id=268593818,
        action_type="CARD_QUALITY_FIX",
        title="Характеристика «Рисунок» не проходит проверку WB",
        priority="P1",
        severity="critical",
        status="new",
        reason="Нужно заполнить характеристику.",
        next_step="Проверить значение в Checker.",
    )
    issue_b = issue_a.model_copy(
        update={
            "id": "card_quality:6176",
            "source_id": "6176",
            "title": "Характеристика «Декоративные элементы» не проходит проверку WB",
            "reason": "Нужно проверить отдельную характеристику.",
        }
    )

    deduped = service._dedupe_actions([issue_a, issue_b])

    assert [item.source_id for item in deduped] == ["6175", "6176"]


def test_portal_checker_content_opportunity_priority_is_capped() -> None:
    service = PortalService()

    assert (
        service._priority_from_issue(
            code="title_too_short",
            severity="critical",
            payload={
                "content_quality_signal": True,
                "impact_type": "opportunity",
                "trust_state": "opportunity",
            },
        )
        == "P3"
    )

    actions = service._checker_actions_from_quality(
        account_id=1,
        quality=PortalProductQualityRead(
            status="ok",
            nm_id=1001,
            issues=[
                {
                    "id": 77,
                    "code": "title_too_short",
                    "severity": "critical",
                    "category": "title",
                    "title": "Название короткое",
                    "score_impact": 20,
                    "status": "pending",
                }
            ],
        ),
    )

    assert len(actions) == 1
    assert actions[0].priority == "P3"
    assert actions[0].severity == "medium"
    assert actions[0].impact_type == "opportunity"
    assert actions[0].trust_state == "opportunity"


def test_portal_checker_data_blocker_stays_urgent() -> None:
    service = PortalService()

    actions = service._checker_actions_from_quality(
        account_id=1,
        quality=PortalProductQualityRead(
            status="ok",
            nm_id=1001,
            issues=[
                {
                    "id": 78,
                    "code": "source_data_missing",
                    "severity": "critical",
                    "category": "data",
                    "title": "Нет исходной карточки",
                    "status": "pending",
                }
            ],
        ),
    )

    assert len(actions) == 1
    assert actions[0].priority == "P0"
    assert actions[0].severity == "critical"
    assert actions[0].impact_type == "data_blocker"
    assert actions[0].trust_state == "blocked"


@pytest.mark.asyncio
async def test_portal_actions_preserves_user_status_after_regeneration() -> None:
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="card:1001",
            status="done",
            comment="fixed",
            assigned_to_user_id=7,
            deadline_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            review_status=None,
        ),
        user_id=7,
    )

    service.money.today_actions = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="checker:card:1001",
                    source="checker_issues",
                    source_module="checker",
                    source_id="card:1001",
                    account_id=1,
                    nm_id=1001,
                    action_type="CARD_QUALITY_FIX",
                    title="Исправить карточку",
                    priority="P2",
                    status="new",
                )
            ],
            None,
        )
    )
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.reputation_adapter.reputation_actions = AsyncMock(return_value=([], None))
    service.claims_adapter.claims_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        session,
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=["checker"],
        priority=None,
        nm_id=1001,
        action_type=None,
        limit=20,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].status == "done"
    assert page.items[0].action_id == session.unified_actions[0].id
    assert page.items[0].assigned_to_user_id == 7
    assert page.items[0].deadline_at == datetime(2026, 6, 20, tzinfo=timezone.utc)
    assert page.items[0].review_status == "closed"
    assert page.items[0].last_comment == "fixed"
    assert page.items[0].closed_at is not None
    assert page.items[0].payload["shadow_action_id"] == session.unified_actions[0].id


@pytest.mark.asyncio
async def test_portal_update_action_by_source_ignored_sets_dismissed_audit_fields() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="data_quality",
            source_id="dq:missing-cost",
            status="ignored",
            comment="not relevant for this account",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
        ),
        user_id=7,
    )

    row = session.unified_actions[0]
    assert result.status == "ignored"
    assert result.review_status == "dismissed"
    assert result.dismissed_at is not None
    assert row.dismissed_at is not None
    assert row.closed_at is None
    assert row.last_comment == "not relevant for this account"
    assert row.payload_json["dismiss_reason"] == "not relevant for this account"
    assert row.payload_json["last_changed_by_user_id"] == 7


@pytest.mark.asyncio
async def test_action_center_problem_valid_transition_tracks_history_and_task_fields() -> (
    None
):
    service = PortalService()
    service.result_tracking.create_problem_status_event = AsyncMock()
    service.result_tracking.create_problem_completed_event = AsyncMock()
    service.result_tracking.create_problem_recheck_event = AsyncMock()
    instance = _problem_instance("new")
    deadline = datetime(2026, 7, 9, 12, 0, tzinfo=timezone.utc)
    session = _FakeProblemSession(instance)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="acknowledged",
            comment="Приняли в работу",
            assigned_to_user_id=7,
            deadline_at=deadline,
            review_status=None,
            event_type=None,
        ),
        user_id=7,
    )

    history_events = [
        row.event_type
        for row in session.added
        if isinstance(row, ProblemInstanceHistory)
    ]
    action_state = instance.calculation_snapshot_json["action_center"]
    assert result.status == "acknowledged"
    assert instance.status == "acknowledged"
    assert {"status_changed", "assigned", "deadline_changed", "comment_added"}.issubset(
        set(history_events)
    )
    assert action_state["assigned_to_user_id"] == 7
    assert action_state["deadline_at"] == "2026-07-09T12:00:00+00:00"
    assert action_state["last_actor_user_id"] == 7
    assert action_state["status_reason"] == "Приняли в работу"
    assert action_state["last_status_changed_at"]
    service.result_tracking.create_problem_status_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_center_problem_update_creates_assignment_and_deadline_notifications() -> (
    None
):
    service = PortalService()
    service.result_tracking.create_problem_status_event = AsyncMock()
    service.result_tracking.create_problem_completed_event = AsyncMock()
    service.result_tracking.create_problem_recheck_event = AsyncMock()
    instance = _problem_instance("new")
    deadline = datetime.now(timezone.utc) + timedelta(hours=2)
    session = _FakeProblemSession(instance)

    await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="acknowledged",
            comment="Назначили ответственного",
            assigned_to_user_id=7,
            deadline_at=deadline,
            review_status=None,
            event_type=None,
        ),
        user_id=9,
    )

    notifications = [
        row
        for row in session.added
        if isinstance(row, ResultEvent)
        and row.source_module == "action_center_notifications"
        and row.event_type == "action_center_notification"
    ]
    notification_types = {
        row.payload_json["notification_type"] for row in notifications
    }
    assert {"assigned_to_user", "deadline_due_soon"}.issubset(notification_types)
    assigned = next(
        row
        for row in notifications
        if row.payload_json["notification_type"] == "assigned_to_user"
    )
    assert assigned.problem_instance_id == instance.id
    assert assigned.payload_json["assigned_to_user_id"] == 7
    assert assigned.payload_json["saved_money_claimed"] is False
    due_soon = next(
        row
        for row in notifications
        if row.payload_json["notification_type"] == "deadline_due_soon"
    )
    assert due_soon.payload_json["outcome"] == "pending"
    assert due_soon.payload_json["saved_money_claimed"] is False


@pytest.mark.asyncio
async def test_action_center_problem_invalid_transition_is_rejected_without_history() -> (
    None
):
    service = PortalService()
    service.result_tracking.create_problem_status_event = AsyncMock()
    service.result_tracking.create_problem_completed_event = AsyncMock()
    service.result_tracking.create_problem_recheck_event = AsyncMock()
    instance = _problem_instance("new")
    session = _FakeProblemSession(instance)

    with pytest.raises(HTTPException) as exc:
        await service.update_action_by_source(
            session,
            payload=SimpleNamespace(
                account_id=1,
                source_module="problem_engine",
                source_id=str(instance.id),
                status="done",
                comment="skip lifecycle",
                assigned_to_user_id=None,
                deadline_at=None,
                review_status=None,
                event_type=None,
            ),
            user_id=7,
        )

    assert exc.value.status_code == 409
    assert instance.status == "new"
    assert [
        row for row in session.added if isinstance(row, ProblemInstanceHistory)
    ] == []
    service.result_tracking.create_problem_status_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_action_center_problem_done_creates_completion_result_event_without_saved_money_claim() -> (
    None
):
    service = PortalService()
    service.result_tracking.create_problem_status_event = AsyncMock()
    service.result_tracking.create_problem_completed_event = AsyncMock()
    service.result_tracking.create_problem_recheck_event = AsyncMock()
    instance = _problem_instance("in_progress")
    session = _FakeProblemSession(instance)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="done",
            comment="Исправили цену",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
            event_type=None,
        ),
        user_id=7,
    )

    history_events = [
        row for row in session.added if isinstance(row, ProblemInstanceHistory)
    ]
    assert result.status == "done"
    assert instance.status == "done"
    assert "result_measured" in [row.event_type for row in history_events]
    result_event = next(
        row for row in history_events if row.event_type == "result_measured"
    )
    assert result_event.new_value_json["saved_money_claimed"] is False
    service.result_tracking.create_problem_completed_event.assert_awaited_once_with(
        session,
        problem_instance_id=instance.id,
        created_by=7,
        comment="Исправили цену",
    )


@pytest.mark.asyncio
async def test_action_center_problem_recheck_request_creates_recheck_history_and_result_event() -> (
    None
):
    service = PortalService()
    service.result_tracking.create_problem_status_event = AsyncMock()
    service.result_tracking.create_problem_completed_event = AsyncMock()
    service.result_tracking.create_problem_recheck_event = AsyncMock()
    instance = _problem_instance("in_progress")
    session = _FakeProblemSession(instance)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="in_progress",
            comment="Запросили перепроверку",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
            event_type="recheck",
        ),
        user_id=7,
    )

    history_events = [
        row.event_type
        for row in session.added
        if isinstance(row, ProblemInstanceHistory)
    ]
    assert result.status == "in_progress"
    assert "recheck_requested" in history_events
    service.result_tracking.create_problem_recheck_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_problem_results_ensures_before_snapshot_and_filters_to_problem_engine() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_problem_before_snapshot = AsyncMock()
    service.result_tracking.list_results = AsyncMock(
        return_value=PortalResultEventsPage(total=0, limit=50, offset=0, items=[])
    )
    instance = _problem_instance("new")
    session = _FakeProblemSession(instance)

    page = await service.problem_results(
        session,
        account_id=1,
        problem_instance_id=instance.id,
        limit=50,
        offset=0,
        ensure_before_snapshot=True,
        created_by=7,
    )

    assert page.total == 0
    assert page.summary["problem_instance_id"] == instance.id
    assert page.summary["problem_code"] == instance.problem_code
    assert page.summary["nm_id"] == instance.nm_id
    assert page.summary["title"] == instance.title
    assert session.committed is True
    service.result_tracking.ensure_problem_before_snapshot.assert_awaited_once_with(
        session,
        problem_instance_id=instance.id,
        created_by=7,
    )
    service.result_tracking.list_results.assert_awaited_once_with(
        session,
        account_id=1,
        problem_instance_id=instance.id,
        source_module="problem_engine",
        limit=50,
        offset=0,
    )


@pytest.mark.asyncio
async def test_portal_update_action_by_source_preserves_finance_recommendation_update_flow() -> (
    None
):
    service = PortalService()
    service.control_tower.update_action = AsyncMock(
        return_value=SimpleNamespace(
            id=10,
            account_id=1,
            action_type="FINANCE_REVIEW",
            title="Проверить финансы",
            priority="P1",
            status="in_progress",
            reason="Needs review",
            payload={},
        )
    )
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="finance",
            source_id="10",
            status="in_progress",
            comment="owner accepted",
            assigned_to_user_id=7,
            deadline_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            review_status=None,
        ),
        user_id=7,
    )

    service.control_tower.update_action.assert_awaited_once()
    update_payload = service.control_tower.update_action.await_args.kwargs["payload"]
    assert update_payload.status == "in_progress"
    assert update_payload.assigned_to == 7
    assert update_payload.comment == "owner accepted"
    assert result.source_module == "finance"
    assert result.status == "in_progress"
    assert result.assigned_to_user_id == 7


@pytest.mark.asyncio
async def test_portal_update_action_by_source_updates_checker_issue_and_shadow_task_fields() -> (
    None
):
    service = PortalService()
    updated_issue = CardQualityIssueRead(
        id=44,
        account_id=1,
        nm_id=245405620,
        issue_code="media_no_images",
        category="media",
        severity="critical",
        title="No images",
        business_explanation="Images are required.",
        recommended_fix="Add product photos.",
        status="in_progress",
        fingerprint="fp",
        first_seen_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )
    service.card_quality.update_issue_status = AsyncMock(return_value=updated_issue)
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="in_progress",
            comment="owner started",
            assigned_to_user_id=7,
            deadline_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            review_status=None,
        ),
        user_id=7,
    )

    service.card_quality.update_issue_status.assert_awaited_once()
    assert service.card_quality.update_issue_status.await_args.kwargs["issue_id"] == 44
    assert (
        service.card_quality.update_issue_status.await_args.kwargs["status"]
        == "in_progress"
    )
    assert (
        service.card_quality.update_issue_status.await_args.kwargs["reason"]
        == "owner started"
    )
    assert result.source_module == "checker"
    assert result.action_type == "CARD_QUALITY_FIX"
    assert result.title == "No images"
    assert result.status == "in_progress"
    assert result.nm_id == 245405620
    assert result.assigned_to_user_id == 7
    assert result.deadline_at == datetime(2026, 6, 20, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_portal_update_action_by_source_checker_in_progress_persists_in_issue() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    issue = _checker_issue()
    session = _FakeCheckerIssueSession(issue)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="in_progress",
            comment="owner started",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
        ),
        user_id=7,
    )

    assert issue.status == "in_progress"
    assert issue.status_reason == "owner started"
    assert result.status == "in_progress"
    assert service.card_quality._issue_payload(issue)["status"] == "in_progress"


@pytest.mark.asyncio
async def test_portal_update_action_by_source_checker_done_creates_history_and_same_status() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    issue = _checker_issue("in_progress")
    session = _FakeCheckerIssueSession(issue)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="done",
            comment="fixed",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
        ),
        user_id=7,
    )

    histories = [
        row
        for row in session.added
        if row.__class__.__name__ == "CardQualityIssueStatusHistory"
    ]
    assert issue.status == "done"
    assert issue.fixed_at is not None
    assert issue.fixed_by_user_id == 7
    assert histories[-1].old_status == "in_progress"
    assert histories[-1].new_status == "done"
    assert result.status == "done"


@pytest.mark.asyncio
async def test_portal_update_action_by_source_checker_postponed_keeps_deadline_and_reason() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    issue = _checker_issue()
    postponed_until = datetime(2026, 7, 10, tzinfo=timezone.utc)
    session = _FakeCheckerIssueSession(issue)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="postponed",
            comment="waiting for supplier",
            assigned_to_user_id=None,
            deadline_at=postponed_until,
            review_status=None,
        ),
        user_id=7,
    )

    assert issue.status == "postponed"
    assert issue.status_reason == "waiting for supplier"
    assert issue.postponed_until == postponed_until
    assert result.status == "postponed"
    assert result.deadline_at == postponed_until


@pytest.mark.asyncio
async def test_portal_update_action_by_source_checker_blocked_visible_after_refresh() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    issue = _checker_issue()
    session = _FakeCheckerIssueSession(issue)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="blocked",
            comment="needs supplier data",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
        ),
        user_id=7,
    )

    issue_payload = service.card_quality._issue_payload(issue)
    action = service.card_quality._action_from_issue(account_id=1, issue=issue)
    assert issue.status == "blocked"
    assert result.status == "blocked"
    assert issue_payload["status"] == "blocked"
    assert issue_payload["status_reason"] == "needs supplier data"
    assert action.status == "blocked"


@pytest.mark.asyncio
async def test_portal_update_action_by_source_checker_recheck_creates_history_without_financial_overclaim() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    issue = _checker_issue()
    session = _FakeCheckerIssueSession(issue)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="new",
            comment="Перепроверка Checker",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
            event_type="recheck",
        ),
        user_id=7,
    )

    histories = [
        row
        for row in session.added
        if row.__class__.__name__ == "CardQualityIssueStatusHistory"
    ]
    action = service.card_quality._action_from_issue(account_id=1, issue=issue)
    assert result.source_module == "checker"
    assert result.status == "new"
    assert histories
    assert histories[-1].old_status == "new"
    assert histories[-1].new_status == "new"
    assert histories[-1].reason == "Перепроверка Checker"
    assert action.trust_state == "opportunity"
    assert action.impact_type == "opportunity"
    assert action.money_trust is not None
    assert action.money_trust.show_as_confirmed_money is False


@pytest.mark.asyncio
async def test_action_center_checker_update_source_endpoint_and_product360_share_status() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    issue = _checker_issue()
    session = _FakeCheckerIssueSession(issue)

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="checker",
            source_id="44",
            status="blocked",
            comment="needs supplier photos",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
        ),
        user_id=7,
    )
    source_read = CardQualityIssueRead.model_validate(issue, from_attributes=True)
    source_payload = service.card_quality._issue_payload(issue)

    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=issue.nm_id,
            identity={"nm_id": issue.nm_id, "title": "Article"},
            money={"revenue": 1000.0},
            stock={},
            ads={},
            actions=[],
            next_actions=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(
            status="ok", nm_id=issue.nm_id, issues=[source_payload]
        )
    )
    service.grouping_beta.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(status="disabled", nm_id=issue.nm_id)
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(status="ok", account_id=1)
    )
    service.experiments.list_product_events = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )

    detail = await service.product_360(
        session,
        account_id=1,
        nm_id=int(issue.nm_id),
        date_from=None,
        date_to=None,
    )

    product360_action = next(
        item
        for item in detail.actions
        if item.source_module == "checker" and item.source_id == "44"
    )
    assert result.status == "blocked"
    assert source_read.status == "blocked"
    assert source_payload["status"] == "blocked"
    assert product360_action.status == "blocked"


@pytest.mark.asyncio
async def test_portal_update_action_by_source_checker_failure_is_not_shadow_masked() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    service.card_quality.update_issue_status = AsyncMock(
        side_effect=ValueError("illegal_status_transition")
    )
    session = _FakeSession()

    with pytest.raises(ValueError, match="illegal_status_transition"):
        await service.update_action_by_source(
            session,
            payload=SimpleNamespace(
                account_id=1,
                source_module="checker",
                source_id="44",
                status="blocked",
                comment="backend rejected transition",
                assigned_to_user_id=None,
                deadline_at=None,
                review_status=None,
            ),
            user_id=7,
        )

    assert session.unified_actions == []


@pytest.mark.asyncio
async def test_portal_stockops_action_completion_records_local_stock_result_event() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="stockops",
            source_id="1:plan:regional_redistribution:1001",
            status="done",
            comment="moved manually",
        ),
        user_id=7,
    )

    stock_events = [
        row
        for row in session.added
        if getattr(row, "source_module", None) == "stockops"
        and getattr(row, "event_type", None) == "stock_action_done"
    ]
    assert result.source_module == "stockops"
    assert result.status == "done"
    assert stock_events
    assert stock_events[0].payload_json["external_operation"] is False
    assert stock_events[0].payload_json["marketplace_change"] is False
    service.result_tracking.create_action_completed_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_portal_actions_represents_blocked_status_consistently() -> None:
    service = PortalService()
    session = _FakeSession()

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="claims",
            source_id="claim:blocked:1",
            status="blocked",
            comment="missing proof",
        ),
        user_id=7,
    )

    assert result.status == "blocked"
    assert session.unified_actions[0].status == "blocked"
    assert session.added[-1].payload_json["status"] == "blocked"


def test_portal_action_priority_sort_is_stable() -> None:
    service = PortalService()
    items = [
        PortalActionRead(
            id="finance:b",
            source="finance_actions",
            source_module="finance",
            action_type="REVIEW_PROFIT",
            title="B",
            priority="P1",
            severity="high",
        ),
        PortalActionRead(
            id="finance:a",
            source="finance_actions",
            source_module="finance",
            action_type="REVIEW_PROFIT",
            title="A",
            priority="P1",
            severity="high",
        ),
        PortalActionRead(
            id="finance:c",
            source="finance_actions",
            source_module="finance",
            action_type="REVIEW_PROFIT",
            title="C",
            priority="P0",
            severity="critical",
        ),
    ]

    assert [item.id for item in sorted(items, key=service._action_sort_key)] == [
        "finance:c",
        "finance:a",
        "finance:b",
    ]


@pytest.mark.asyncio
async def test_synthetic_action_upsert_is_idempotent() -> None:
    service = PortalService()
    session = _FakeSession()
    action = PortalActionRead(
        id="reputation:review:123",
        source="reputation_adapter",
        source_module="reputation",
        source_id="review:123",
        account_id=1,
        nm_id=1001,
        action_type="negative_review_unanswered",
        title="Ответить на отзыв",
        priority="P2",
    )

    first = await service.upsert_synthetic_action(
        session,
        account_id=1,
        action=action,
        status="done",
        comment="answered",
        user_id=7,
    )
    second = await service.upsert_synthetic_action(
        session,
        account_id=1,
        action=action,
        status="ignored",
        comment="duplicate",
        user_id=7,
    )

    assert first is second
    assert len(session.unified_actions) == 1
    assert second.status == "ignored"
    assert second.source_module == "reputation"
    assert second.source_id == "review:123"
    assert second.payload_json["shadow_synthetic"] is True
    assert second.payload_json["marketplace_change"] is False


def test_reputation_action_center_contract_marks_manual_attention_beta() -> None:
    service = PortalService()
    draft = DraftOut(
        id="501",
        draft_type=DraftType.REVIEW_REPLY,
        external_status=ExternalStatus.DRAFT_READY,
        account_id=1,
        source_type="review",
        source_id="fb1",
        title="Reply draft",
        text="Здравствуйте, проверим ситуацию.",
        status=ActionStatus.IN_PROGRESS,
        requires_confirmation=True,
    )
    item = ReputationItemOut(
        id="review:fb1",
        item_type="review",
        external_id="fb1",
        account_id=1,
        nm_id=1001,
        rating=2,
        title="Плохо",
        text="Товар пришел с дефектом, нужна помощь",
        sentiment="negative",
        priority=Priority.P2,
        review_need_reply_score=42,
        review_requires_manual_attention=True,
        review_categories=["quality_defect"],
        needs_reply=True,
        draft=draft,
    )

    action = service.reputation._action_from_item(item)

    assert action.source_module == "reputation"
    assert action.source_id == "review:fb1"
    assert action.action_type == "REPUTATION_MANUAL_ATTENTION"
    assert action.priority == "P0"
    assert action.status == "in_progress"
    assert action.can_update_status is True
    assert action.payload["beta"] is True
    assert action.payload["rating"] == 2
    assert action.payload["need_reply_score"] == 42
    assert action.payload["manual_attention"] is True
    assert action.payload["draft_id"] == "501"
    assert action.payload["classification"]["categories"] == ["quality_defect"]
    assert "дефектом" in action.payload["text_excerpt"]
    assert action.payload["marketplace_change"] is False


@pytest.mark.asyncio
async def test_portal_actions_excludes_reputation_by_default() -> None:
    service = _empty_action_center_service()
    service.reputation.reputation_actions = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="reputation:review:fb1",
                    source="reputation",
                    source_module="reputation",
                    source_id="review:fb1",
                    action_type="REPUTATION_REPLY",
                    title="Ответить на отзыв",
                    priority="P2",
                    payload={"beta": True},
                )
            ],
            None,
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        include_beta=False,
        limit=20,
        offset=0,
    )

    assert [item.source_module for item in page.items] == []
    service.reputation.action_center_enabled.assert_not_awaited()
    service.reputation.reputation_actions.assert_not_awaited()


@pytest.mark.asyncio
async def test_portal_actions_includes_reputation_only_with_beta_flag() -> None:
    action = PortalActionRead(
        id="reputation:review:fb1",
        source="reputation",
        source_module="reputation",
        source_id="review:fb1",
        action_type="REPUTATION_REPLY",
        title="Ответить на отзыв",
        priority="P2",
        payload={"beta": True},
    )
    beta_service = _empty_action_center_service()
    beta_service.reputation.reputation_actions = AsyncMock(
        return_value=([action], None)
    )
    beta_page = await beta_service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        include_beta=True,
        limit=20,
        offset=0,
    )

    no_beta_service = _empty_action_center_service()
    no_beta_service.reputation.action_center_enabled = AsyncMock(return_value=True)
    no_beta_service.reputation.reputation_actions = AsyncMock(
        return_value=([action], None)
    )
    no_beta_page = await no_beta_service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        nm_id=None,
        action_type=None,
        include_beta=False,
        limit=20,
        offset=0,
    )

    assert [item.source_module for item in beta_page.items] == ["reputation"]
    assert [item.source_module for item in no_beta_page.items] == []
    no_beta_service.reputation.reputation_actions.assert_not_awaited()


@pytest.mark.asyncio
async def test_portal_update_action_by_source_updates_reputation_shadow_only() -> None:
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    item = SimpleNamespace(
        status="new",
        needs_reply=True,
        review_requires_manual_attention=False,
        raw_json={},
    )
    draft = SimpleNamespace(
        id=55, status="new", external_status="draft_ready", payload_json={}
    )
    service.reputation._find_item = AsyncMock(return_value=item)
    service.reputation._find_draft = AsyncMock(return_value=draft)
    service.reputation_adapter.publish_reply = AsyncMock(
        side_effect=AssertionError("must not publish from Action Center")
    )
    session = _FakeSession()

    result = await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="reputation",
            source_id="review:fb1",
            status="ignored",
            comment="no answer needed here",
            assigned_to_user_id=None,
            deadline_at=None,
            review_status=None,
        ),
        user_id=7,
    )

    assert result.source_module == "reputation"
    assert result.status == "ignored"
    assert item.status == "ignored"
    assert item.needs_reply is False
    assert draft.status == "rejected"
    assert draft.payload_json["marketplace_change"] is False
    assert session.unified_actions[0].payload_json["reputation_item_updated"] is True
    assert session.unified_actions[0].payload_json["reputation_draft_updated"] is True
    assert session.unified_actions[0].payload_json["external_operation"] is False
    service.reputation_adapter.publish_reply.assert_not_awaited()


@pytest.mark.asyncio
async def test_portal_update_action_updates_persisted_unified_action_status() -> None:
    service = PortalService()
    service.control_tower.update_action = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Action not found")
    )
    persisted = UnifiedAction(
        id=501,
        account_id=1,
        source_module="claims",
        source_id="claim:501",
        nm_id=1004,
        action_type="DRAFT_CLAIM",
        status="new",
        priority="P1",
        title="Подготовить претензию",
        payload_json={"expected_effect_amount": 25000.0},
    )
    session = _FakeSession(unified_actions=[persisted])

    result = await service.update_action(
        session,
        action_id=501,
        user_id=7,
        payload=SimpleNamespace(
            status="in_progress",
            comment="Берем в работу",
            assigned_to_user_id=7,
            deadline_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
            review_status=None,
        ),
    )

    assert result.status == "in_progress"
    assert result.can_update is True
    assert persisted.status == "in_progress"
    assert persisted.assigned_to_user_id == 7
    assert persisted.deadline_at == datetime(2026, 6, 20, tzinfo=timezone.utc)
    assert persisted.review_status == "in_progress"
    assert persisted.last_comment == "Берем в работу"
    assert persisted.payload_json["last_comment"] == "Берем в работу"
    assert persisted.payload_json["assigned_to_user_id"] == 7
    assert persisted.payload_json["deadline_at"] == "2026-06-20T00:00:00+00:00"
    assert result.assigned_to_user_id == 7
    assert result.deadline_at == datetime(2026, 6, 20, tzinfo=timezone.utc)
    assert result.review_status == "in_progress"
    assert result.last_comment == "Берем в работу"
    assert session.committed is True


@pytest.mark.asyncio
async def test_portal_update_action_tracks_before_and_completion_events() -> None:
    service = PortalService()
    service.control_tower.update_action = AsyncMock(
        side_effect=HTTPException(status_code=404, detail="Action not found")
    )
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    persisted = UnifiedAction(
        id=502,
        account_id=1,
        source_module="claims",
        source_id="claim:502",
        nm_id=1004,
        action_type="DRAFT_CLAIM",
        status="new",
        priority="P1",
        title="Подготовить претензию",
        payload_json={"expected_effect_amount": 25000.0},
    )
    session = _FakeSession(unified_actions=[persisted])

    await service.update_action(
        session,
        action_id=502,
        user_id=7,
        payload=SimpleNamespace(status="in_progress", comment=None),
    )
    await service.update_action(
        session,
        action_id=502,
        user_id=7,
        payload=SimpleNamespace(status="done", comment=None),
    )

    service.result_tracking.ensure_before_snapshot.assert_any_await(
        session,
        account_id=1,
        action_id=502,
        created_by=7,
    )
    service.result_tracking.create_action_completed_event.assert_awaited_once_with(
        session,
        account_id=1,
        action_id=502,
        created_by=7,
    )


@pytest.mark.asyncio
async def test_reputation_generate_draft_persists_manual_text_locally() -> None:
    service = PortalService()
    service.reputation_adapter.generate_draft = AsyncMock()
    session = _FakeSession()

    result = await service.reputation_generate_draft(
        session,
        account_id=1,
        item_id="review:fb1",
        payload=SimpleNamespace(
            draft_type="review_reply",
            text="Спасибо за отзыв.",
            payload={"tone": "neutral"},
        ),
        user_id=7,
    )

    drafts = [row for row in session.added if isinstance(row, OperatorDraft)]
    assert result.status == "ok"
    assert result.draft is not None
    assert result.draft.text == "Спасибо за отзыв."
    assert result.draft.requires_confirmation is True
    assert drafts[0].source_module == "reputation"
    assert drafts[0].source_id == "reputation:review:fb1:draft"
    assert drafts[0].payload_json["external_submit_attempted"] is False
    assert drafts[0].payload_json["marketplace_change"] is False
    assert session.committed is True
    service.reputation_adapter.generate_draft.assert_not_called()


@pytest.mark.asyncio
async def test_portal_update_action_by_source_tracks_synthetic_result_events() -> None:
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="reputation",
            source_id="review:123",
            status="done",
            comment="answered manually",
        ),
        user_id=7,
    )

    row = session.unified_actions[0]
    assert row.source_module == "reputation"
    assert row.source_id == "review:123"
    assert row.status == "done"
    service.result_tracking.create_action_completed_event.assert_awaited_once_with(
        session,
        account_id=1,
        action_id=row.id,
        created_by=7,
    )
    assert any(
        getattr(event, "event_type", None) == "local_action_status_updated"
        for event in session.added
    )


@pytest.mark.asyncio
async def test_portal_completing_grouping_review_records_grouping_result_event() -> (
    None
):
    service = PortalService()
    service.result_tracking.ensure_before_snapshot = AsyncMock()
    service.result_tracking.create_action_completed_event = AsyncMock()
    session = _FakeSession()

    await service.update_action_by_source(
        session,
        payload=SimpleNamespace(
            account_id=1,
            source_module="grouping",
            source_id="candidate:1001",
            status="done",
            comment="reviewed, do not merge",
        ),
        user_id=7,
    )

    grouping_events = [
        event
        for event in session.added
        if isinstance(event, ResultEvent)
        and getattr(event, "event_type", None) == "grouping_review_completed"
    ]
    assert len(grouping_events) == 1
    event = grouping_events[0]
    assert event.source_module == "grouping_beta"
    assert event.status == "done"
    assert event.payload_json["marketplace_change"] is False
    assert event.payload_json["auto_merge_enabled"] is False
    assert "No WB merge/apply" in event.message


@pytest.mark.asyncio
async def test_portal_products_exposes_frontend_friendly_money_columns() -> None:
    service = PortalService()
    service._enrich_product_rows_with_card_quality = AsyncMock(
        side_effect=lambda _session, *, account_id, rows: rows
    )
    service.money.articles = AsyncMock(
        return_value=SimpleNamespace(
            total=1,
            limit=50,
            offset=0,
            summary={"profitable_count": 1},
            items=[
                {
                    "nm_id": 1001,
                    "title": "Article",
                    "vendor_code": "VC-1",
                    "photo_url": "https://cdn.example.test/card.jpg",
                    "money": {
                        "revenue": 1000.0,
                        "for_pay": 900.0,
                        "profit": {
                            "after_source_ads": 250.0,
                            "margin_after_ads_percent": 25.0,
                        },
                    },
                    "ads": {"spend": 50.0},
                    "stock": {"quantity": 7.0},
                    "cost_coverage": {"status": "ok"},
                    "quality": {"status": "ok"},
                    "data_trust": {"trust_state": "trusted"},
                    "next_action": {
                        "id": 10,
                        "account_id": 1,
                        "action_type": "ADS_REVIEW",
                        "title": "Проверить рекламу",
                        "priority": "medium",
                        "status": "new",
                        "confidence": "medium",
                        "linked_entity": {"nm_id": 1001},
                    },
                }
            ],
        )
    )

    page = await service.products(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        search=None,
        limit=50,
        offset=0,
    )

    row = page.items[0]
    assert row.nm_id == 1001
    assert row.vendor_code == "VC-1"
    assert row.photo_url == "https://cdn.example.test/card.jpg"
    assert row.revenue == 1000.0
    assert row.for_pay == 900.0
    assert row.estimated_profit == 250.0
    assert row.profit == 250.0
    assert row.margin == 25.0
    assert row.ads_spend == 50.0
    assert row.stock_qty == 7.0
    assert row.cost_state == "ok"
    assert row.stock_state == "ok"
    assert row.card_quality_state == "ok"
    assert row.reputation_state == "not_configured"
    assert row.cases_state == "not_configured"
    assert row.data_trust_state == "trusted"
    assert row.open_actions_count == 1
    assert row.top_action is not None


@pytest.mark.asyncio
async def test_portal_product_360_returns_blocks_and_graceful_empty_sections() -> None:
    service = PortalService()
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={"nm_id": 1001, "title": "Article"},
            money={"revenue": 0.0, "for_pay": 0.0, "profit": {"after_source_ads": 0.0}},
            kpis={"revenue": 0.0},
            stock={},
            ads={"spend": 0.0},
            price_safety=None,
            cost_coverage={"cost_truth_level": "missing"},
            expense_breakdown=None,
            trust={"state": "data_blocked"},
            reconciliation={"status": "missing"},
            finality={"profit_final": False},
            actions=[],
            next_actions=[],
            issues=[],
            problems=[],
            operations={},
            funnel={},
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.checker.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(
            status="ok",
            nm_id=1001,
            score=64,
            critical_issue_count=1,
            title_issues=[
                {
                    "id": 77,
                    "code": "title_short",
                    "severity": "critical",
                    "category": "title",
                    "title": "Название короткое",
                    "score_impact": 20,
                    "status": "pending",
                }
            ],
            issues=[
                {
                    "id": 77,
                    "code": "title_short",
                    "severity": "critical",
                    "category": "title",
                    "title": "Название короткое",
                    "score_impact": 20,
                    "status": "pending",
                }
            ],
        )
    )
    service.grouping_beta.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(
            status="disabled", nm_id=1001, message="grouping beta is disabled"
        )
    )
    service.profit_doctor.diagnose = AsyncMock(return_value=_doctor_result())

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert detail.identity.status == "ok"
    assert detail.overview_diagnosis.status == "ok"
    assert detail.money.status == "ok"
    assert detail.money.data["summary"]["revenue"] == 0.0
    assert detail.stock.status == "empty"
    assert detail.stock.data == {}
    assert detail.stock_summary == {}
    assert detail.ads_summary == {"spend": 0.0}
    assert detail.pricing.status == "unavailable"
    assert detail.pricing.data == {}
    assert detail.data_quality.status == "ok"
    assert detail.quality.status == "ok"
    assert detail.card_quality.status == "ok"
    assert detail.quality.data["score"] == 64
    assert detail.grouping.status == "disabled"
    assert detail.grouping_beta.status == "disabled"
    assert detail.business_issues.status == "empty"
    assert detail.business_issues.data["summary"]["open_count"] == 0
    assert detail.reputation.status == "not_configured"
    assert detail.reputation.data["unanswered_reviews_count"] is None
    assert detail.reputation.data["unanswered_questions_count"] is None
    assert detail.reputation.data["negative_unanswered_count"] is None
    assert detail.reputation.data["unread_chats_count"] is None
    assert detail.reputation.data["last_items"] == []
    assert detail.reputation.data["draft_ready_count"] is None
    assert detail.reputation.data["next_reputation_action"] is None
    assert detail.claims.status == "not_configured"
    assert detail.result_history.status == "ok"
    assert detail.next_best_action is not None
    assert detail.next_best_action.nm_id == 1001
    assert detail.module_health is not None
    assert any(item.source_module == "checker" for item in detail.actions)


@pytest.mark.asyncio
async def test_product360_returns_grouped_dynamic_problems() -> None:
    negative_profit = _product360_problem_action(
        problem_instance_id=101,
        problem_code="negative_unit_profit",
        category="profitability",
        status="in_progress",
        impact_type="probable_loss",
        trust_state="estimated",
        allowed_actions=["review_price", "recheck"],
    )
    missing_cost = _product360_problem_action(
        problem_instance_id=102,
        problem_code="missing_cost_blocks_profit",
        category="data_quality",
        status="blocked",
        severity="critical",
        impact_type="data_blocker",
        trust_state="blocked",
        allowed_actions=["upload_cost", "map_sku", "recheck"],
    )
    service = _product360_control_panel_service(
        problem_actions=[negative_profit, missing_cost]
    )

    detail = await service.product_360(
        _FakeSession(), account_id=1, nm_id=1001, date_from=None, date_to=None
    )

    assert detail.product_identity["title"] == "Article"
    assert detail.product_identity["vendor_code"] == "VC-1"
    assert detail.product_identity["price"] == 1990.0
    assert detail.product_identity["stock"] == 7.0
    assert set(detail.grouped_problems) == set(service.PRODUCT360_PROBLEM_GROUPS)
    assert {item["problem_instance_id"] for item in detail.problem_instances} == {
        101,
        102,
    }
    assert (
        detail.grouped_problems["profitability"]["items"][0]["problem_code"]
        == "negative_unit_profit"
    )
    assert (
        detail.grouped_problems["data_blockers"]["items"][0]["problem_code"]
        == "missing_cost_blocks_profit"
    )
    assert detail.health_summary["open_problem_count"] == 2


@pytest.mark.asyncio
async def test_product360_action_center_link_contains_problem_instance_id() -> None:
    action = _product360_problem_action(
        problem_instance_id=101,
        problem_code="negative_unit_profit",
        category="profitability",
        status="in_progress",
        allowed_actions=["review_price", "recheck"],
    )
    service = _product360_control_panel_service(problem_actions=[action])

    detail = await service.product_360(
        _FakeSession(), account_id=1, nm_id=1001, date_from=None, date_to=None
    )

    problem = detail.problem_instances[0]
    product360_action = next(
        item for item in detail.actions if item.source_module == "problem_engine"
    )
    assert "problem_instance_id=101" in problem["action_center_href"]
    assert problem["status"] == product360_action.status


@pytest.mark.asyncio
async def test_product360_results_link_contains_problem_instance_id_and_uses_result_ledger() -> (
    None
):
    action = _product360_problem_action(
        problem_instance_id=101,
        problem_code="negative_unit_profit",
        category="profitability",
        status="done",
        allowed_actions=["review_price", "recheck"],
    )
    service = _product360_control_panel_service(
        problem_actions=[action],
        result_events=[_product360_result_event(101, outcome="neutral")],
    )

    detail = await service.product_360(
        _FakeSession(), account_id=1, nm_id=1001, date_from=None, date_to=None
    )

    problem = detail.problem_instances[0]
    assert "problem_instance_id=101" in problem["results_href"]
    assert problem["result_status"] == "neutral"
    assert problem["result_preview"]["source"] == "result_ledger"
    assert detail.result_preview["source"] == "result_ledger"
    assert detail.result_preview["items"][0]["problem_instance_id"] == 101


@pytest.mark.asyncio
async def test_product360_checker_content_issue_not_confirmed_loss() -> None:
    checker_action = PortalActionRead(
        id="checker:77",
        source="checker_issues",
        source_module="checker",
        source_id="77",
        account_id=1,
        nm_id=1001,
        action_type="CARD_QUALITY_FIX",
        detector_code="title_short",
        title="Title is too short",
        reason="Checker found a content issue.",
        next_step="Open checker and improve the card.",
        priority="P2",
        severity="high",
        status="new",
        expected_effect_amount=1200.0,
        confidence="high",
        impact_type="confirmed_loss",
        trust_state="confirmed",
        payload={
            "content_quality_signal": True,
            "problem_code": "card_quality_issue",
            "category": "card_quality",
            "allowed_actions": ["run_checker", "recheck"],
        },
        evidence_ledger=evidence_ledger(
            value=1200.0,
            value_type="money",
            confidence="confirmed",
            impact_type="confirmed_loss",
            formula_human="Checker score impact is not finance evidence.",
            formula_code="checker.card_quality.test",
            label="Checker score impact",
            source_table="checker_issues",
            row_count=1,
        ),
        allowed_actions=["run_checker", "recheck"],
    )
    service = _product360_control_panel_service(
        checker_quality=PortalProductQualityRead(
            status="ok", nm_id=1001, score=72, critical_issue_count=1
        )
    )
    service._checker_actions_from_quality = lambda **_: [checker_action]

    detail = await service.product_360(
        _FakeSession(), account_id=1, nm_id=1001, date_from=None, date_to=None
    )

    item = detail.grouped_problems["card_quality"]["items"][0]
    assert item["problem_code"] == "card_quality_issue"
    assert item["impact_type"] == "opportunity"


@pytest.mark.asyncio
async def test_product360_data_blocker_links_to_data_fix() -> None:
    missing_cost = _product360_problem_action(
        problem_instance_id=102,
        problem_code="missing_cost_blocks_profit",
        category="data_quality",
        status="blocked",
        severity="critical",
        impact_type="data_blocker",
        trust_state="blocked",
        allowed_actions=["upload_cost", "map_sku", "recheck"],
    )
    service = _product360_control_panel_service(problem_actions=[missing_cost])

    detail = await service.product_360(
        _FakeSession(), account_id=1, nm_id=1001, date_from=None, date_to=None
    )

    assert detail.data_blockers["count"] == 1
    assert detail.data_blockers["data_fix_href"].startswith("/data-fix")
    assert "problem_instance_id=102" in detail.data_blockers["data_fix_href"]
    assert (
        detail.data_blockers["top_blockers"][0]["problem_code"]
        == "missing_cost_blocks_profit"
    )


@pytest.mark.asyncio
async def test_product360_missing_evidence_produces_missing_data_state() -> None:
    action = _product360_problem_action(
        problem_instance_id=103,
        problem_code="negative_unit_profit",
        category="profitability",
        status="new",
        impact_type="probable_loss",
        trust_state="estimated",
        ledger=EvidenceLedger(),
    )
    service = _product360_control_panel_service(problem_actions=[action])

    detail = await service.product_360(
        _FakeSession(), account_id=1, nm_id=1001, date_from=None, date_to=None
    )

    problem = detail.problem_instances[0]
    assert problem["evidence_state"] == "missing_data"
    assert problem["result_status"] == "missing_data"


@pytest.mark.asyncio
async def test_portal_product_360_uses_exact_unresolved_cost_lookup_beyond_first_page() -> (
    None
):
    service = PortalService()
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={
                "nm_id": 1001,
                "sku_id": 501,
                "title": "Article",
                "vendor_code": "VC-1",
                "barcode": "BC-1",
            },
            money={"revenue": 1000.0},
            stock={},
            ads={},
            actions=[],
            next_actions=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(
            items=[{"id": idx, "nm_id": 9000 + idx} for idx in range(100)]
        )
    )
    matching_cost = {
        "id": 1000,
        "account_id": 1,
        "nm_id": 1001,
        "sku_id": 501,
        "vendor_code": "VC-1",
        "barcode": "BC-1",
        "cost_price": 100.0,
        "unit_cost": 100.0,
        "is_ambiguous": True,
    }
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(
        return_value=[matching_cost]
    )
    service.checker.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(status="not_configured", nm_id=1001)
    )
    service.grouping.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(status="disabled", nm_id=1001)
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(status="ok", account_id=1)
    )
    service.experiments.list_product_events = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert detail.costs.data["unresolved_costs"] == [matching_cost]
    assert detail.card_quality.status == "not_configured"
    assert detail.card_quality.data["status"] == "not_configured"
    assert detail.card_quality.data["severity"] == "not_configured"
    assert any(
        action.source_module == "costs" and action.source_id == "1000"
        for action in detail.actions
    )
    service.manual_costs.list_unresolved_costs_page.assert_not_awaited()
    service.manual_costs.list_unresolved_costs_for_product.assert_awaited_once()
    assert service.manual_costs.list_unresolved_costs_for_product.await_args.kwargs == {
        "account_id": 1,
        "nm_id": 1001,
        "sku_id": 501,
        "vendor_code": "VC-1",
        "barcode": "BC-1",
        "limit": 10,
    }


@pytest.mark.asyncio
async def test_portal_product_360_caps_slow_stockops_optional_call() -> None:
    service = PortalService()
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={"nm_id": 1001, "title": "Article"},
            money={"revenue": 1000.0},
            stock={},
            ads={},
            actions=[],
            next_actions=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.checker.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(status="not_configured", nm_id=1001)
    )
    service.grouping.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(status="disabled", nm_id=1001)
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(status="ok", account_id=1)
    )
    service.experiments.list_product_events = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )

    async def _slow_stockops(*args, **kwargs):
        await asyncio.sleep(2)
        return PortalStockOpsInsightsRead(status="ok", account_id=1, nm_id=1001)

    service.stock_control.product_stock_insights = _slow_stockops
    started = asyncio.get_running_loop().time()

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert asyncio.get_running_loop().time() - started < 1.5
    assert detail.stock.status == "unavailable"
    assert "stockops" in detail.unavailable_sources


@pytest.mark.asyncio
async def test_portal_product_360_optional_module_timeout_returns_unavailable() -> None:
    service = PortalService()
    service.checker.settings = Settings(checker_http_timeout_seconds=0.001)
    service.checker.settings.checker_http_timeout_seconds = 0.001
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={"nm_id": 1001, "title": "Article"},
            money={"revenue": 1000.0},
            stock={},
            ads={},
            actions=[],
            next_actions=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])

    async def _slow_checker_quality(*args, **kwargs):
        await asyncio.sleep(0.05)
        return PortalProductQualityRead(status="ok", nm_id=1001)

    service.checker.product_quality = _slow_checker_quality
    service.grouping.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(status="disabled", nm_id=1001)
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(status="ok", account_id=1)
    )
    service.experiments.list_product_events = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert detail.card_quality.status == "unavailable"
    assert detail.quality.status == "unavailable"
    assert "checker_quality" in detail.unavailable_sources
    assert detail.money.status == "ok"


@pytest.mark.asyncio
async def test_portal_product_360_claims_block_includes_local_cases() -> None:
    service = PortalService()
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={"nm_id": 1001, "title": "Article"},
            money={"revenue": 1000.0},
            stock={},
            ads={},
            actions=[],
            next_actions=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.checker.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(status="not_configured", nm_id=1001)
    )
    service.grouping.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(status="disabled", nm_id=1001)
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(status="ok", account_id=1)
    )
    service.claims_adapter.product_360 = AsyncMock(
        return_value={"status": "not_configured", "items": []}
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(
            account_id=1,
            total=1,
            items=[
                CaseListItemOut(
                    id="10",
                    case_type=CaseType.DEFECT,
                    account_id=1,
                    nm_id=1001,
                    title="Defect case",
                )
            ],
        )
    )

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert detail.claims.status == "ok"
    assert detail.claims.data["local_cases_count"] == 1
    assert detail.claims.data["candidate_count"] == 0
    assert detail.claims.data["local_cases"][0]["id"] == "10"
    assert detail.claims.data["candidates"] == []


@pytest.mark.asyncio
async def test_portal_product_360_reputation_block_uses_inbox_counts_and_next_action() -> (
    None
):
    service = PortalService()
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={"nm_id": 1001, "title": "Article"},
            money={"revenue": 1000.0},
            stock={},
            ads={},
            actions=[],
            next_actions=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.checker.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(status="ok", nm_id=1001, score=90)
    )
    service.grouping.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(status="disabled", nm_id=1001)
    )
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(status="ok", account_id=1)
    )
    service.experiments.list_product_events = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.result_tracking.list_results = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.claims_adapter.product_360 = AsyncMock(
        return_value={"status": "not_configured", "items": []}
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )
    reputation = ReputationAdapter(
        Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"1": 10},
        )
    )
    inbox_payloads = [
        {
            "items": [
                {
                    "wb_id": "fb1",
                    "rating": 1,
                    "text": "Bad",
                    "created_date": "2026-06-10T10:00:00+00:00",
                    "product_details": {"nmId": 1001, "productName": "Article"},
                    "buyer_email": "buyer@example.test",
                }
            ]
        },
        {
            "items": [
                {
                    "id": "q1",
                    "text": "Is it waterproof?",
                    "created_at": "2026-06-10T11:00:00+00:00",
                    "product_details": {"nmId": 1001, "productName": "Article"},
                }
            ]
        },
        {
            "items": [
                {
                    "chat_id": "c1",
                    "unread_count": 2,
                    "last_message": {"text": "Need help"},
                    "created_at": "2026-06-10T12:00:00+00:00",
                    "good_card": {"nmID": 1001, "title": "Article"},
                    "draft": {"id": "draft-c1", "text": "Hello"},
                }
            ]
        },
    ]
    reputation._request = AsyncMock(side_effect=inbox_payloads + inbox_payloads)
    service.reputation_adapter = reputation

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert detail.reputation.status == "ok"
    assert detail.reputation.data["unanswered_reviews_count"] == 1
    assert detail.reputation.data["unanswered_questions_count"] == 1
    assert detail.reputation.data["negative_unanswered_count"] == 1
    assert detail.reputation.data["unread_chats_count"] == 1
    assert detail.reputation.data["draft_ready_count"] == 1
    assert len(detail.reputation.data["last_items"]) == 3
    assert (
        detail.reputation.data["next_reputation_action"]["action_type"]
        == "negative_review_unanswered"
    )
    assert "buyer@example" not in str(detail.reputation.data)
    assert any(
        action.source_module == "reputation"
        and action.action_type == "negative_review_unanswered"
        for action in detail.actions
    )
    assert detail.next_best_action is not None
    assert detail.next_best_action.source_module == "reputation"
    assert detail.next_best_action.action_type == "negative_review_unanswered"


def test_portal_reputation_block_includes_local_result_history_when_adapter_down() -> (
    None
):
    service = PortalService()

    block = service._reputation_block_with_history(
        PortalDataBlock(
            status="unavailable",
            data={"last_items": []},
            message="reputation module is unavailable",
        ),
        [
            {
                "event_type": "reputation_reply_published",
                "message": "Reply was published manually.",
                "buyer_email": "buyer@example.test",
            },
            {"event_type": "price_changed", "message": "Not reputation."},
        ],
    )

    assert block.status == "degraded"
    assert len(block.data["result_history"]) == 1
    assert block.data["result_history"][0]["event_type"] == "reputation_reply_published"
    assert "buyer@example" not in str(block.data)


@pytest.mark.asyncio
async def test_portal_modules_health_local_claims_make_claims_visible() -> None:
    service = PortalService()
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=1, items=[])
    )

    health = await service.modules_health(_FakeSession(), account_id=1)

    assert health.modules.claims.status == "disabled"
    assert health.modules.claims.visible is True
    assert health.modules.claims.navigation_group == "operator"
    assert "local cases" in str(health.modules.claims.reason).lower()
    assert "claims_visible_due_to_local_cases" in health.modules.claims.warnings


@pytest.mark.asyncio
async def test_portal_product_360_claims_block_returns_candidates_when_present() -> (
    None
):
    service = PortalService()
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )

    block = await service._claims_block_with_local_cases(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        block=PortalDataBlock(
            status="ok",
            data={
                "items": [
                    {
                        "source_id": "defect_claim_candidate:1001",
                        "nm_id": 1001,
                        "estimated_amount": 1500.0,
                        "buyer_email": "buyer@example.test",
                    }
                ],
                "potential_compensation_amount": 1500.0,
            },
        ),
        unavailable=[],
    )

    assert block.status == "ok"
    assert block.data["local_cases_count"] == 0
    assert block.data["candidate_count"] == 1
    assert block.data["potential_compensation_amount"] == 1500.0
    assert block.data["candidates"][0]["source_id"] == "defect_claim_candidate:1001"
    assert "buyer_email" not in str(block.data)


@pytest.mark.asyncio
async def test_portal_product_360_claims_block_combines_local_cases_and_candidates_without_duplicates() -> (
    None
):
    service = PortalService()
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(
            account_id=1,
            total=1,
            items=[
                CaseListItemOut(
                    id="10",
                    case_type=CaseType.DEFECT,
                    account_id=1,
                    nm_id=1001,
                    title="Existing defect case",
                    amount_claimed=1500.0,
                    data={"signal": {"source_id": "defect_claim_candidate:1001"}},
                )
            ],
        )
    )

    block = await service._claims_block_with_local_cases(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        block=PortalDataBlock(
            status="ok",
            data={
                "items": [
                    {
                        "source_id": "defect_claim_candidate:1001",
                        "nm_id": 1001,
                        "estimated_amount": 1500.0,
                    },
                    {
                        "source_id": "defect_claim_candidate:1001-new",
                        "nm_id": 1001,
                        "estimated_amount": 500.0,
                    },
                ],
                "actions": [
                    {
                        "source_id": "defect_claim_candidate:1001-new",
                        "title": "Create claim case",
                    }
                ],
            },
        ),
        unavailable=[],
    )

    assert block.status == "ok"
    assert block.data["local_cases_count"] == 1
    assert block.data["candidate_count"] == 1
    assert block.data["local_cases"][0]["id"] == "10"
    assert block.data["candidates"][0]["source_id"] == "defect_claim_candidate:1001-new"
    assert (
        block.data["next_claim_action"]["source_id"]
        == "defect_claim_candidate:1001-new"
    )


@pytest.mark.asyncio
async def test_portal_product_360_claims_block_missing_service_stays_unavailable_without_breaking() -> (
    None
):
    service = PortalService()
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(account_id=1, total=0, items=[])
    )

    block = await service._claims_block_with_local_cases(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        block=PortalDataBlock(
            status="unavailable", data={}, message="claims module is unavailable"
        ),
        unavailable=[],
    )

    assert block.status == "unavailable"
    assert block.data["local_cases_count"] == 0
    assert block.data["candidate_count"] == 0
    assert block.data["local_cases"] == []
    assert block.data["candidates"] == []


@pytest.mark.asyncio
async def test_portal_product_360_merges_optional_module_data_safely() -> None:
    service = PortalService()
    service.money.money.article_detail = AsyncMock(
        return_value=SimpleNamespace(
            nm_id=1001,
            identity={
                "nm_id": 1001,
                "title": "Article",
                "vendor_code": "VC-1",
                "barcode": "123",
            },
            money={
                "revenue": 120000.0,
                "for_pay": 100000.0,
                "profit": {"after_source_ads": 20000.0},
            },
            kpis={"revenue": 120000.0},
            stock={"quantity": 4},
            ads={"spend": 10000.0},
            price_safety={"status": "ok"},
            cost_coverage={"status": "ok"},
            trust={"trust_state": "trusted"},
            reconciliation={"status": "matched"},
            finality={"profit_final": True},
            actions=[],
            next_actions=[],
            issues=[],
            problems=[],
        )
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_for_product = AsyncMock(return_value=[])
    service.checker.product_quality = AsyncMock(
        return_value=PortalProductQualityRead(
            status="ok", nm_id=1001, score=88, recommendations=["Keep content fresh"]
        )
    )
    service.grouping_beta.product_grouping = AsyncMock(
        return_value=PortalProductGroupingRead(
            status="beta",
            nm_id=1001,
            recommendations=[{"nm_id": 1002, "vendor_code": "VC-2"}],
            recommendation_count=1,
        )
    )
    service.reputation_adapter = SimpleNamespace(
        product_360=AsyncMock(
            return_value={
                "status": "ok",
                "unanswered_reviews_count": 2,
                "negative_unanswered_count": 1,
                "customer_phone": "+79999999999",
            }
        )
    )
    service.claims_adapter = SimpleNamespace(
        product_360=AsyncMock(
            return_value={
                "status": "ok",
                "open_cases_count": 1,
                "potential_compensation_amount": 1500.0,
                "buyer_email": "buyer@example.test",
            }
        )
    )
    service.claims_factory.list_cases = AsyncMock(
        return_value=ClaimsCasesPage(
            account_id=1,
            total=1,
            items=[
                CaseListItemOut(
                    id="case-1",
                    case_type=CaseType.DEFECT,
                    account_id=1,
                    nm_id=1001,
                    title="Defect claim",
                    amount_claimed=1500.0,
                )
            ],
        )
    )
    service.stock_control.product_stock_insights = AsyncMock(
        return_value=PortalStockOpsInsightsRead(
            status="ok",
            account_id=1,
            nm_id=1001,
            summary={"candidate_count": 1, "write_status": "disabled"},
            action_candidates=[
                {
                    "source_module": "stockops",
                    "source_id": "1:plan:regional_redistribution:1001",
                    "action_type": "regional_redistribution",
                    "nm_id": 1001,
                    "quantity": 5,
                    "write_status": "disabled",
                }
            ],
        )
    )
    service.stock_control.action_candidates = AsyncMock(
        return_value=(
            [
                PortalActionRead(
                    id="stockops:1:plan:1001",
                    source="stockops_signals",
                    source_module="stockops",
                    source_id="1:plan:regional_redistribution:1001",
                    account_id=1,
                    nm_id=1001,
                    action_type="regional_redistribution",
                    title="Review stock redistribution candidate",
                    priority="P1",
                    severity="high",
                    payload={"write_status": "disabled", "marketplace_change": False},
                )
            ],
            None,
        )
    )
    service.profit_doctor.diagnose = AsyncMock(return_value=_doctor_result())

    detail = await service.product_360(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        date_from=None,
        date_to=None,
    )

    assert detail.money.status == "ok"
    assert detail.card_quality.status == "ok"
    assert detail.card_quality.data["score"] == 88
    assert detail.reputation.status == "ok"
    assert detail.reputation.data["negative_unanswered_count"] == 1
    assert "customer_phone" not in detail.reputation.data
    assert detail.claims.status == "ok"
    assert detail.claims.data["potential_compensation_amount"] == 1500.0
    assert detail.claims.data["candidate_count"] == 0
    assert "buyer_email" not in detail.claims.data
    assert detail.stock.status == "ok"
    assert detail.stock.data["stockops"]["status"] == "ok"
    assert detail.stock.data["stockops"]["summary"]["write_status"] == "disabled"
    assert detail.grouping_beta.status == "beta"
    assert (
        detail.grouping_beta.data["beta_notice"]
        == "Beta / recommendation only. WB merge/apply is disabled."
    )
    assert detail.grouping_beta.data["auto_merge_enabled"] is False
    assert any(action.source_module == "stockops" for action in detail.actions)
    assert detail.next_best_action is not None
    assert detail.next_best_action.guided_fix["method"] == "open_product_360"


@pytest.mark.asyncio
async def test_portal_actions_mark_patchable_finance_actions_and_preserve_null_amounts() -> (
    None
):
    service = PortalService()
    service.money.today_actions = AsyncMock(
        return_value=SimpleNamespace(
            items=[
                {
                    "id": 10,
                    "account_id": 1,
                    "action_type": "PRICE_REVIEW",
                    "title": "Проверить цену",
                    "priority": "medium",
                    "status": "new",
                    "expected_effect_amount": None,
                    "linked_entity": {"nm_id": 1001},
                }
            ],
        )
    )
    service.money.data_blockers = AsyncMock(
        return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}
    )
    service.data_quality.list_issues = AsyncMock(return_value=SimpleNamespace(items=[]))
    service.manual_costs.list_unresolved_costs_page = AsyncMock(
        return_value=SimpleNamespace(items=[])
    )
    service.checker.quality_actions = AsyncMock(return_value=([], None))
    service.grouping.recommendation_actions = AsyncMock(return_value=([], None))
    service.profit_doctor.diagnose = AsyncMock(
        return_value=ProfitDoctorOut(
            status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0
        )
    )

    page = await service.actions(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
        status=None,
        source_module=None,
        priority=None,
        limit=20,
        offset=0,
    )

    assert page.items[0].id == "finance:10"
    assert page.items[0].external_id == "10"
    assert page.items[0].expected_effect_amount is None
    assert page.items[0].can_update_status is True


@pytest.mark.asyncio
async def test_portal_product_quality_returns_not_configured_when_checker_missing() -> (
    None
):
    service = PortalService()

    quality = await service.product_quality(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
    )

    assert quality.status == "not_configured"
    assert quality.module == "checker"
    assert quality.message == "Checker не подключён"
    assert quality.action == "connect_checker_in_settings"
    assert quality.issues == []
    assert quality.score is None


@pytest.mark.asyncio
async def test_action_center_capabilities_expose_jvo_like_domains_and_write_gaps() -> (
    None
):
    service = PortalService()

    result = await service.action_center_capabilities(_FakeSession(), account_id=1)

    domains = {domain.key: domain for domain in result.domains}
    assert {
        "data_blockers",
        "card_quality",
        "price",
        "ads_promo",
        "stock",
        "manual_tasks",
        "system_checks",
    }.issubset(domains)
    assert result.summary["domain_count"] == len(result.domains)
    assert result.summary["execute_missing_wb_write"] >= 2
    assert result.summary["wb_unknown_connectors"] == 0
    assert result.summary["wb_api_write_gap"] >= 2
    assert any(
        capability.key == "missing_cost_inline_fix"
        and capability.execute_status == "ready"
        for capability in domains["data_blockers"].capabilities
    )
    assert any(
        capability.key == "manual_task_creation"
        and capability.execute_status == "ready"
        for capability in domains["manual_tasks"].capabilities
    )
    assert any(
        capability.key == "wb_price_discount_write"
        and capability.execute_status == "missing_wb_write"
        for capability in domains["price"].capabilities
    )
    price_write = next(
        capability
        for capability in domains["price"].capabilities
        if capability.key == "wb_price_discount_write"
    )
    assert price_write.wb_tracking_status == "write_gap"
    assert (
        "https://discounts-prices-api.wildberries.ru/api/v2/upload/task"
        in price_write.wb_api_endpoints
    )
    assert price_write.implementation_gaps
    assert price_write.safety_requirements
    card_text = next(
        capability
        for capability in domains["card_quality"].capabilities
        if capability.key == "card_text_inline_fix"
    )
    assert card_text.wb_tracking_status == "tracked"
    assert "product_cards.update_card" in card_text.wb_connector_ids
    assert "content" in card_text.token_categories
    assert any(
        capability.key == "ads_campaign_control"
        and capability.execute_status == "missing_wb_write"
        for capability in domains["ads_promo"].capabilities
    )
    for domain in result.domains:
        for capability in domain.capabilities:
            if capability.execute_status == "missing_wb_write":
                assert capability.implementation_gaps
                assert capability.safety_requirements
