from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.db import get_db_session
from app.main import app
from app.models.accounts import WBAccount
from app.models.auth import AuthUser, AuthUserAccountAccess
from app.models.operator import OperatorCase, OperatorDraft, ResultEvent, UnifiedAction
from app.models.problem_engine import (
    ProblemDefinition,
    ProblemEvaluationRunLog,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleVersion,
)
from app.modules.portal import router as portal_router
from app.schemas.operator import ProfitDoctorOut
from app.schemas.portal import (
    PortalDataBlock,
    PortalModuleHealth,
    PortalModuleHealthItem,
    PortalProductGroupingRead,
    PortalProductQualityRead,
    PortalStockOpsInsightsRead,
)
from app.services.auth import get_current_user
from app.services.problem_engine.evaluator import ProblemEvaluationPreview, ProblemEvaluationResult


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw) -> str:
    return "INTEGER"


class _AsyncSessionAdapter:
    def __init__(self, sync_session: Session):
        self._session = sync_session

    async def execute(self, statement):
        return self._session.execute(statement)

    async def get(self, model, ident):
        return self._session.get(model, ident)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()

    async def commit(self) -> None:
        self._session.commit()

    async def refresh(self, instance) -> None:
        self._session.refresh(instance)


def _create_tables(engine) -> None:
    for table in (
        WBAccount.__table__,
        AuthUser.__table__,
        AuthUserAccountAccess.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
        ProblemEvaluationRunLog.__table__,
        UnifiedAction.__table__,
        OperatorCase.__table__,
        OperatorDraft.__table__,
        ResultEvent.__table__,
    ):
        table.create(engine)


def _session() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    _create_tables(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=1, name="Integration account", timezone="Europe/Moscow", is_active=True))
    sync_session.add(
        AuthUser(
            id=42,
            email="admin@example.test",
            full_name="Администратор",
            password_hash="not-used",
            is_active=True,
            is_superuser=True,
        )
    )
    sync_session.add(
        AuthUser(
            id=77,
            email="operator@example.test",
            full_name="Мария Оператор",
            password_hash="not-used",
            is_active=True,
            is_superuser=False,
        )
    )
    sync_session.add(AuthUserAccountAccess(user_id=77, account_id=1, role="operator", is_default=True))
    sync_session.flush()
    return sync_session, _AsyncSessionAdapter(sync_session)


def _ledger(problem_code: str) -> dict:
    return {
        "value": 100,
        "value_type": "money",
        "confidence": "estimated",
        "impact_type": "probable_loss",
        "formula_human": "Прибыль на единицу ниже нуля.",
        "formula_code": f"{problem_code}.v1",
        "formula_id": "rule:negative_unit_profit:v1",
        "input_facts": [
            {
                "label": "Прибыль на единицу",
                "metric_code": "unit_profit",
                "value": -20,
                "unit": "RUB",
                "trust_state": "confirmed",
                "source": "money",
                "source_table": "mart_sku_daily",
                "source_endpoint": "GET /api/v1/marts/sku-daily",
                "date_range": {"date_from": "2026-06-07", "date_to": "2026-07-06"},
            }
        ],
        "source_references": [
            {
                "source_table": "mart_sku_daily",
                "source_endpoint": "GET /api/v1/marts/sku-daily",
                "date_range": {"date_from": "2026-06-07", "date_to": "2026-07-06"},
                "row_count": 1,
            }
        ],
        "missing_data": [],
        "trust_notes": ["Расчёт использует подтверждённые финансовые строки."],
        "recheck_rule_human": "Перепроверьте после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
        "calculation_warnings": [],
    }


def _add_dynamic_problem(sync_session: Session) -> ProblemInstance:
    now = datetime(2026, 7, 6, tzinfo=timezone.utc)
    definition = ProblemDefinition(
        problem_code="negative_unit_profit",
        source_module="problem_engine",
        category="profitability",
        entity_type="product",
        title_template="Товар {nm_id} продаётся в минус",
        description_template="Прибыль на единицу отрицательная.",
        recommendation_template="Проверьте цену, себестоимость, рекламу, промо и логистику.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=["review_price", "review_cost", "recheck", "dismiss"],
        status="active",
    )
    sync_session.add(definition)
    sync_session.flush()
    rule = ProblemRuleVersion(
        problem_definition_id=definition.id,
        version=1,
        status="active",
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={"<": [{"metric": "unit_profit"}, 0]},
        impact_formula_json={"abs": {"metric": "unit_profit"}},
        severity_formula_json="high",
        confidence_formula_json="estimated",
        dedup_key_template="{account_id}:{problem_code}:{nm_id}",
        recheck_rule_json={"human": "Перепроверьте после обновления исходных метрик."},
        evidence_template_json={"formula_human": "unit_profit < 0"},
    )
    sync_session.add(rule)
    sync_session.flush()
    instance = ProblemInstance(
        account_id=1,
        problem_code="negative_unit_profit",
        problem_definition_id=definition.id,
        rule_version_id=rule.id,
        source_module="problem_engine",
        entity_type="product",
        entity_id="1001",
        nm_id=1001,
        vendor_code="SKU-1001",
        dedup_key="1:negative_unit_profit:1001",
        title="Товар 1001 продаётся в минус",
        explanation="Прибыль на единицу отрицательная.",
        recommendation="Проверьте цену, себестоимость, рекламу, промо и логистику.",
        severity="high",
        status="new",
        impact_type="probable_loss",
        money_impact_amount=Decimal("100"),
        money_impact_currency="RUB",
        trust_state="estimated",
        confidence="estimated",
        evidence_ledger_json=_ledger("negative_unit_profit"),
        calculation_snapshot_json={"matched": True},
        first_seen_at=now,
        last_seen_at=now,
    )
    sync_session.add(instance)
    sync_session.flush()
    return instance


def _add_context_problem(
    sync_session: Session,
    *,
    problem_code: str,
    source_module: str = "problem_engine",
    nm_id: int = 1001,
    vendor_code: str = "SKU-1001",
    impact_type: str = "probable_loss",
    trust_state: str = "estimated",
    evidence_ledger: dict | None = None,
) -> ProblemInstance:
    now = datetime(2026, 7, 6, tzinfo=timezone.utc)
    definition = ProblemDefinition(
        problem_code=problem_code,
        source_module=source_module,
        category="data_quality" if impact_type == "data_blocker" else "card_quality",
        entity_type="product",
        title_template=f"{problem_code} {{nm_id}}",
        description_template=f"{problem_code} description",
        recommendation_template=f"{problem_code} recommendation",
        impact_type_default=impact_type,
        trust_state_default=trust_state,
        severity_default="high",
        allowed_actions_json=["recheck"],
        status="active",
    )
    sync_session.add(definition)
    sync_session.flush()
    rule = ProblemRuleVersion(
        problem_definition_id=definition.id,
        version=1,
        status="active",
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={"==": [{"metric": problem_code}, True]},
        impact_formula_json={"const": 0},
        severity_formula_json="high",
        confidence_formula_json=trust_state,
        dedup_key_template="{account_id}:{problem_code}:{nm_id}",
        recheck_rule_json={"human": "Перепроверьте после обновления исходных метрик."},
        evidence_template_json={"formula_human": problem_code},
    )
    sync_session.add(rule)
    sync_session.flush()
    instance = ProblemInstance(
        account_id=1,
        problem_code=problem_code,
        problem_definition_id=definition.id,
        rule_version_id=rule.id,
        source_module=source_module,
        entity_type="product",
        entity_id=str(nm_id),
        nm_id=nm_id,
        vendor_code=vendor_code,
        dedup_key=f"1:{problem_code}:{nm_id}",
        title=f"{problem_code} for {nm_id}",
        explanation=f"{problem_code} explanation",
        recommendation=f"{problem_code} recommendation",
        severity="high",
        status="done",
        impact_type=impact_type,
        money_impact_amount=Decimal("100"),
        money_impact_currency="RUB",
        trust_state=trust_state,
        confidence=trust_state,
        evidence_ledger_json=evidence_ledger or _ledger(problem_code),
        calculation_snapshot_json={"matched": True},
        first_seen_at=now,
        last_seen_at=now,
    )
    sync_session.add(instance)
    sync_session.flush()
    return instance


def _module_health() -> PortalModuleHealth:
    return PortalModuleHealth(
        finance=PortalModuleHealthItem(status="ok"),
        checker=PortalModuleHealthItem(status="ok"),
        stockops=PortalModuleHealthItem(status="ok"),
        grouping=PortalModuleHealthItem(status="disabled"),
        actions=PortalModuleHealthItem(status="ok"),
        products=PortalModuleHealthItem(status="ok"),
        results=PortalModuleHealthItem(status="ok"),
    )


def _patch_optional_portal_sources(monkeypatch) -> None:
    service = portal_router.service
    service.settings = SimpleNamespace(
        dynamic_problem_engine_enabled=True,
        dynamic_problem_engine_test_account_ids=[],
        show_legacy_problem_cards=False,
    )
    monkeypatch.setattr(service, "_module_health", AsyncMock(return_value=_module_health()))
    monkeypatch.setattr(service, "_list_unified_actions", AsyncMock(return_value=[]))
    monkeypatch.setattr(service.result_tracking, "finance_window_summary", AsyncMock(return_value={}))
    monkeypatch.setattr(service.result_tracking, "finance_window_summaries", AsyncMock(return_value={}))

    monkeypatch.setattr(service.money, "today_actions", AsyncMock(return_value=SimpleNamespace(items=[])))
    monkeypatch.setattr(service.money, "data_blockers", AsyncMock(return_value={"meta": {"account_id": 1}, "blockers": [], "warnings": []}))
    monkeypatch.setattr(service.data_quality, "list_issues", AsyncMock(return_value=SimpleNamespace(items=[])))
    monkeypatch.setattr(service.manual_costs, "list_unresolved_costs_page", AsyncMock(return_value=SimpleNamespace(items=[])))
    monkeypatch.setattr(service.manual_costs, "list_unresolved_costs_for_product", AsyncMock(return_value=[]))
    monkeypatch.setattr(service.checker, "quality_actions", AsyncMock(return_value=([], None)))
    monkeypatch.setattr(service.card_quality, "quality_actions", AsyncMock(return_value=[]))
    monkeypatch.setattr(service.grouping, "recommendation_actions", AsyncMock(return_value=([], None)))
    monkeypatch.setattr(service.grouping_beta, "recommendation_actions", AsyncMock(return_value=[]))
    monkeypatch.setattr(service.claims_adapter, "claims_actions", AsyncMock(return_value=([], None)))
    monkeypatch.setattr(service.stock_control, "action_candidates", AsyncMock(return_value=([], None)))
    monkeypatch.setattr(service.experiments, "action_candidates", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service.profit_doctor,
        "diagnose",
        AsyncMock(return_value=ProfitDoctorOut(status="ok", account_id=1, summary="", total_signals=0, total_diagnoses=0)),
    )
    monkeypatch.setattr(service.reputation, "action_center_enabled", AsyncMock(return_value=False))
    monkeypatch.setattr(service.reputation, "reputation_actions", AsyncMock(return_value=([], None)))
    monkeypatch.setattr(service.reputation_adapter, "reputation_actions", AsyncMock(return_value=([], None)))

    async def _product_money_detail(*args, **kwargs):
        nm_id = kwargs["nm_id"]
        return {
            "identity": {"nm_id": nm_id, "vendor_code": "SKU-1001", "title": "Integration SKU"},
            "money": {
                "revenue": 1000.0,
                "for_pay": 850.0,
                "profit": {
                    "net_profit_after_all_expenses": -20.0,
                    "margin_after_ads_percent": -2.0,
                    "roi_after_ads_percent": -4.0,
                },
            },
            "kpis": {"revenue": 1000.0, "net_profit_after_all_expenses": -20.0},
            "stock": {"quantity": 7.0},
            "ads": {"spend": 100.0},
            "price": {"current_price": 500.0},
            "actions": [],
            "next_actions": [],
        }

    monkeypatch.setattr(service, "_fast_product_money_detail", _product_money_detail)
    monkeypatch.setattr(service.money.money.dashboard, "article_audit", AsyncMock(return_value=None))
    monkeypatch.setattr(service, "product_quality", AsyncMock(return_value=PortalProductQualityRead(status="ok", nm_id=1001, score=94)))
    monkeypatch.setattr(service, "product_grouping", AsyncMock(return_value=PortalProductGroupingRead(status="not_configured", nm_id=1001)))
    monkeypatch.setattr(service, "_reputation_product_block", AsyncMock(return_value=PortalDataBlock(status="not_configured", data={})))
    monkeypatch.setattr(service, "_optional_product_module_block", AsyncMock(return_value=PortalDataBlock(status="not_configured", data={})))
    monkeypatch.setattr(service, "_claims_block_with_local_cases", AsyncMock(return_value=PortalDataBlock(status="not_configured", data={})))
    monkeypatch.setattr(service.stock_control, "product_stock_insights", AsyncMock(return_value=PortalStockOpsInsightsRead(status="empty", account_id=1, nm_id=1001)))
    monkeypatch.setattr(service.photo_studio, "status", AsyncMock(return_value=SimpleNamespace(status="disabled", model_dump=lambda mode="json": {"status": "disabled"})))
    monkeypatch.setattr(service.experiments, "list_product_events", AsyncMock(return_value=SimpleNamespace(items=[])))
    monkeypatch.setattr(service.experiments, "product_block", AsyncMock(return_value={"status": "empty", "items": []}))
    monkeypatch.setattr(service.ab_photo_tests, "product_block", AsyncMock(return_value={"status": "empty", "items": []}))


def _install_test_overrides(sync_session: Session, session: _AsyncSessionAdapter):
    async def _override_session():
        yield session

    def _override_user():
        return SimpleNamespace(id=42, is_superuser=True)

    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session

    return sync_session


def _result_events(sync_session: Session) -> list[ResultEvent]:
    return list(sync_session.execute(select(ResultEvent).order_by(ResultEvent.id)).scalars())


def test_action_center_dynamic_problem_api_result_ledger_lifecycle(monkeypatch) -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)
    _patch_optional_portal_sources(monkeypatch)
    _install_test_overrides(sync_session, session)

    async def _still_matching_recheck(session, *, account_id, nm_id, date_from=None, date_to=None):
        refreshed = await session.get(ProblemInstance, instance.id)
        assert refreshed is not None
        return ProblemEvaluationResult(
            evaluated_count=1,
            matched_count=1,
            updated_count=1,
            previews=[
                ProblemEvaluationPreview(
                    account_id=account_id,
                    nm_id=nm_id,
                    problem_code="negative_unit_profit",
                    dedup_key="1:negative_unit_profit:1001",
                    matched=True,
                    action="updated",
                    status=str(refreshed.status),
                    title=refreshed.title,
                    explanation=refreshed.explanation,
                    recommendation=refreshed.recommendation,
                    severity=refreshed.severity,
                    impact_type=refreshed.impact_type,
                    money_impact_amount=Decimal("100"),
                    confidence=refreshed.confidence,
                    trust_state=refreshed.trust_state,
                    evidence_ledger_json=refreshed.evidence_ledger_json,
                    calculation_snapshot_json=refreshed.calculation_snapshot_json,
                    existing_instance_id=refreshed.id,
                )
            ],
            instances=[refreshed],
        )

    monkeypatch.setattr(portal_router.problem_evaluation_runner.evaluator, "evaluate_product", _still_matching_recheck)

    try:
        with TestClient(app) as client:
            actions = client.get("/api/v1/portal/actions?account_id=1&source_module=problem_engine")
            assert actions.status_code == 200
            action_items = actions.json()["items"]
            assert len(action_items) == 1
            action = action_items[0]
            assert action["id"] == f"problem_engine:{instance.id}"
            assert action["source_module"] == "problem_engine"
            assert action["payload"]["problem_instance_id"] == instance.id
            assert action["payload"]["result_summary"]["before_snapshot"]["money_impact_amount"] == 100.0
            assert action["evidence_ledger"]["formula_human"] == "Прибыль на единицу ниже нуля."
            assert {"open_price_review", "upload_cost", "recheck", "dismiss"}.issubset(set(action["allowed_actions"]))

            assignable = client.get("/api/v1/portal/assignable-users?account_id=1")
            assert assignable.status_code == 200
            assignable_users = assignable.json()
            assert any(
                user["id"] == 77
                and user["display_name"] == "Мария Оператор"
                and user["role"] == "operator"
                for user in assignable_users
            )

            before_page = client.get(f"/api/v1/portal/problems/{instance.id}/results")
            assert before_page.status_code == 200
            before_body = before_page.json()
            assert before_body["total"] == 1
            assert before_body["items"][0]["event_type"] == "before_snapshot"
            assert before_body["items"][0]["before_snapshot"]["problem_instance_id"] == instance.id
            assert before_body["items"][0]["before_snapshot"]["title"] == "Товар 1001 продаётся в минус"
            assert before_body["items"][0]["payload"]["title"] == "Товар 1001 продаётся в минус"

            update = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "problem_engine",
                    "source_id": str(instance.id),
                    "status": "in_progress",
                    "assigned_to_user_id": 77,
                    "deadline_at": "2026-07-10T12:00:00Z",
                    "comment": "Берём в работу",
                },
            )
            assert update.status_code == 200
            updated = update.json()
            assert updated["status"] == "in_progress"
            assert updated["assigned_to_user_id"] == 77
            assert updated["last_comment"] == "Берём в работу"

            sync_session.refresh(instance)
            assert instance.status == "in_progress"
            action_state = instance.calculation_snapshot_json["action_center"]
            assert action_state["assigned_to_user_id"] == 77
            assert action_state["last_comment"] == "Берём в работу"
            assert action_state["deadline_at"].startswith("2026-07-10T12:00:00")

            refreshed_actions = client.get("/api/v1/portal/actions?account_id=1&source_module=problem_engine")
            assert refreshed_actions.status_code == 200
            refreshed_action = refreshed_actions.json()["items"][0]
            assert refreshed_action["status"] == "in_progress"
            assert refreshed_action["assigned_to_user_id"] == 77
            assert refreshed_action["deadline_at"].startswith("2026-07-10T12:00:00")
            assert refreshed_action["last_comment"] == "Берём в работу"

            done = client.patch(
                "/api/v1/portal/actions/by-source",
                json={
                    "account_id": 1,
                    "source_module": "problem_engine",
                    "source_id": str(instance.id),
                    "status": "done",
                    "comment": "Проверили цену и себестоимость",
                },
            )
            assert done.status_code == 200
            assert done.json()["status"] == "done"

            history_events = [
                row.event_type
                for row in sync_session.execute(select(ProblemInstanceHistory).order_by(ProblemInstanceHistory.id)).scalars()
            ]
            assert {"status_changed", "assigned", "deadline_changed", "comment_added", "result_measured"}.issubset(set(history_events))
            result_events = _result_events(sync_session)
            assert {"before_snapshot", "action_started", "action_completed"}.issubset({event.event_type for event in result_events})
            completed = next(event for event in result_events if event.event_type == "action_completed")
            assert completed.payload_json["saved_money_claimed"] is False
            assert "saved money" not in str(completed.message or "").lower()

            filtered = client.get(
                "/api/v1/portal/results"
                f"?account_id=1&problem_instance_id={instance.id}"
                "&problem_code=negative_unit_profit&nm_id=1001&source_module=problem_engine"
                "&result_status=pending_data&trust_state=estimated&impact_type=probable_loss"
            )
            assert filtered.status_code == 200
            filtered_body = filtered.json()
            assert filtered_body["total"] >= 3
            assert {item["problem_instance_id"] for item in filtered_body["items"]} == {instance.id}
            assert {item["problem_code"] for item in filtered_body["items"]} == {"negative_unit_profit"}
            assert {item["source_module"] for item in filtered_body["items"]} == {"problem_engine"}
            assert filtered_body["summary"]["problem_instance_id"] == instance.id
            assert filtered_body["summary"]["problem_code"] == "negative_unit_profit"
            assert filtered_body["summary"]["result_status"] == "pending_data"
            assert filtered_body["summary"]["is_measured"] is False
            assert filtered_body["summary"]["saved_money_claimed"] is False
            assert filtered_body["summary"]["measured_comparison"] is None
            assert filtered_body["summary"]["after_snapshot"] == {}
            assert filtered_body["summary"]["correlation_disclaimer"] == (
                "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
            )
            assert "Ожидаемый эффект не считается сэкономленными деньгами" in filtered_body["summary"]["money_note"]

            product_results = client.get("/api/v1/portal/results?account_id=1&nm_id=1001")
            assert product_results.status_code == 200
            assert product_results.json()["total"] >= 3
            assert {item["nm_id"] for item in product_results.json()["items"]} == {1001}

            recheck = client.post(f"/api/v1/portal/problems/{instance.id}/recheck")
            assert recheck.status_code == 200
            rechecked_action = recheck.json()
            assert rechecked_action["status"] == "reopened"
            assert rechecked_action["payload"]["result_summary"]["status_flow"]["current_status"] == "reopened"

            post_recheck_events = _result_events(sync_session)
            recheck_event = next(event for event in post_recheck_events if event.event_type == "recheck_result")
            assert recheck_event.payload_json["saved_money_claimed"] is False
            sync_session.refresh(instance)
            assert instance.status == "reopened"
            history_after_recheck = [
                row.event_type
                for row in sync_session.execute(select(ProblemInstanceHistory).order_by(ProblemInstanceHistory.id)).scalars()
            ]
            assert "recheck_completed" in history_after_recheck
            assert "reopened" in history_after_recheck

            product = client.get("/api/v1/portal/products/1001?account_id=1")
            assert product.status_code == 200
            product_body = product.json()
            product_action = next(item for item in product_body["actions"] if item["source_module"] == "problem_engine")
            assert product_action["source_id"] == str(instance.id)
            assert product_action["status"] == "reopened"
            open_problem = product_body["business_issues"]["data"]["open"][0]
            assert open_problem["payload"]["problem_instance_id"] == instance.id
            assert open_problem["payload"]["result_summary"]["status_flow"]["current_status"] == "reopened"
            product_result_events = product_body["result_history"]["data"]["result_events"]
            assert {item["event_type"] for item in product_result_events} >= {
                "before_snapshot",
                "action_started",
                "action_completed",
                "recheck_result",
            }

            results_timeline = client.get(f"/api/v1/portal/problems/{instance.id}/results")
            assert results_timeline.status_code == 200
            timeline_body = results_timeline.json()
            timeline_events = timeline_body["items"]
            assert {item["event_type"] for item in timeline_events} >= {
                "before_snapshot",
                "action_started",
                "action_completed",
                "recheck_result",
            }
            assert all(item["payload"]["saved_money_claimed"] is False for item in timeline_events)
            assert {
                item["payload"]["title"] for item in timeline_events if item["source_module"] == "problem_engine"
            } == {"Товар 1001 продаётся в минус"}
            assert timeline_body["summary"]["problem_identity"] == {
                "problem_instance_id": instance.id,
                "problem_code": "negative_unit_profit",
                "title": "Товар 1001 продаётся в минус",
                "source_module": "problem_engine",
                "nm_id": 1001,
                "vendor_code": "SKU-1001",
            }
            assert timeline_body["summary"]["result_status"] == "pending_data"
            assert timeline_body["summary"]["action_events"]
            assert timeline_body["summary"]["recheck_events"][0]["event_type"] == "recheck_result"
            assert timeline_body["summary"]["product_href"] == f"/products/1001?problem_instance_id={instance.id}"
            assert timeline_body["summary"]["action_center_href"] == f"/action-center?problem_instance_id={instance.id}&nm_id=1001"
    finally:
        app.dependency_overrides.clear()


def test_result_items_include_data_blocker_context_links() -> None:
    sync_session, session = _session()
    instance = _add_context_problem(
        sync_session,
        problem_code="missing_cost_blocks_profit",
        impact_type="data_blocker",
        trust_state="blocked",
        evidence_ledger={
            "formula_human": "Себестоимость отсутствует и блокирует финальный profit.",
            "input_facts": [{"metric_code": "unit_profit", "value": None}],
            "missing_data": ["cost_price"],
        },
    )
    sync_session.add(
        ResultEvent(
            account_id=1,
            problem_instance_id=instance.id,
            problem_code=instance.problem_code,
            source_module="problem_engine",
            source_id=str(instance.id),
            external_id=str(instance.id),
            nm_id=instance.nm_id,
            vendor_code=instance.vendor_code,
            event_type="action_completed",
            status="done",
            message="Cost task marked done without measured after-data.",
            created_at=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
            payload_json={
                "problem_instance_id": instance.id,
                "problem_code": instance.problem_code,
                "product_identity": {"title": "Integration SKU", "vendor_code": "SKU-1001"},
                "before_snapshot": {
                    "unit_profit": None,
                    "impact_type": "data_blocker",
                    "trust_state": "blocked",
                },
                "after_snapshot": {},
                "comparison": {"outcome": "not_enough_data", "metrics": {}},
                "outcome": "not_enough_data",
                "confidence": "blocked",
                "saved_money_claimed": True,
            },
        )
    )
    sync_session.flush()
    _install_test_overrides(sync_session, session)

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/portal/results?account_id=1&problem_instance_id={instance.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["problem_instance_id"] == instance.id
    assert item["problem_code"] == "missing_cost_blocks_profit"
    assert item["vendor_code"] == "SKU-1001"
    assert item["product_title"] == "Integration SKU"
    assert item["impact_type"] == "data_blocker"
    assert item["trust_state"] == "blocked"
    assert "confidence" in item
    assert item["result_status"] == "pending_data"
    assert item["measured_comparison"] is None
    assert item["data_fix_href"].startswith("/data-fix")
    assert f"problem_instance_id={instance.id}" in item["data_fix_href"]
    assert item["product_href"] == f"/products/1001?problem_instance_id={instance.id}"
    assert item["results_href"] == f"/results?problem_instance_id={instance.id}&nm_id=1001"
    assert item["saved_money_claimed"] is False
    assert item["payload"]["saved_money_claimed"] is False


def test_result_items_include_checker_context_and_metric_hints() -> None:
    sync_session, session = _session()
    instance = _add_context_problem(
        sync_session,
        problem_code="card_quality_issue",
        source_module="checker",
        nm_id=1002,
        vendor_code="SKU-1002",
        impact_type="opportunity",
        trust_state="estimated",
        evidence_ledger={
            "formula_human": "Card quality score below target.",
            "input_facts": [
                {"metric_code": "card_quality_score", "value": 62},
                {"metric_code": "card_quality_issue_count", "value": 4},
            ],
            "missing_data": [],
        },
    )
    sync_session.add_all(
        [
            ResultEvent(
                account_id=1,
                problem_instance_id=instance.id,
                problem_code=instance.problem_code,
                source_module="checker",
                source_id=str(instance.id),
                external_id=str(instance.id),
                nm_id=instance.nm_id,
                vendor_code=instance.vendor_code,
                event_type="action_completed",
                status="done",
                message="Checker task done; waiting for re-check data.",
                created_at=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
                payload_json={
                    "problem_instance_id": instance.id,
                    "problem_code": instance.problem_code,
                    "product_identity": {"title": "Checker SKU", "vendor_code": "SKU-1002"},
                    "before_snapshot": {"quality_score": 62, "open_issue_count": 4},
                    "after_snapshot": {},
                    "comparison": {"outcome": "not_enough_data", "metrics": {}},
                    "outcome": "not_enough_data",
                    "saved_money_claimed": False,
                },
            ),
            ResultEvent(
                account_id=1,
                problem_instance_id=instance.id,
                problem_code=instance.problem_code,
                source_module="checker",
                source_id=str(instance.id),
                external_id=str(instance.id),
                nm_id=instance.nm_id,
                vendor_code=instance.vendor_code,
                event_type="recheck_result",
                status="done",
                message="Checker re-check still lacks after metrics.",
                created_at=datetime(2026, 7, 6, 13, 0, tzinfo=timezone.utc),
                payload_json={
                    "problem_instance_id": instance.id,
                    "problem_code": instance.problem_code,
                    "product_identity": {"title": "Checker SKU", "vendor_code": "SKU-1002"},
                    "before_snapshot": {"quality_score": 62, "open_issue_count": 4},
                    "after_snapshot": {},
                    "comparison": {"outcome": "not_enough_data", "metrics": {}},
                    "outcome": "not_enough_data",
                    "saved_money_claimed": False,
                },
            ),
        ]
    )
    sync_session.flush()
    _install_test_overrides(sync_session, session)

    try:
        with TestClient(app) as client:
            response = client.get(f"/api/v1/portal/results?account_id=1&problem_instance_id={instance.id}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert {item["problem_instance_id"] for item in body["items"]} == {instance.id}
    first = body["items"][0]
    assert first["checker_href"] == f"/checker/1002?problem_instance_id={instance.id}"
    assert first["data_fix_href"] is None
    assert first["metric_template_code"] == "card_quality_issue"
    assert first["relevant_metric_keys"] == ["quality_score", "open_issue_count"]
    assert first["missing_metric_keys"] == ["quality_score", "open_issue_count"]
    assert first["last_recheck_at"].startswith("2026-07-06T13:00:00")
    assert first["result_status"] == "pending_data"
    assert first["saved_money_claimed"] is False
