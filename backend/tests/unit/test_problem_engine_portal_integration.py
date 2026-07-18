from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.operator import ResultEvent
from app.models.problem_engine import ProblemDefinition, ProblemInstance, ProblemInstanceHistory, ProblemRuleVersion
from app.schemas.portal import PortalActionRead, PortalActionSourceUpdateRequest, build_action_center_solve_map
from app.services.problem_engine.problem_seeds import INITIAL_PROBLEM_DEFINITION_SEEDS
from app.services.portal import PortalService


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


def _ledger(problem_code: str) -> dict:
    return {
        "value": 100,
        "value_type": "money",
        "confidence": "estimated",
        "impact_type": "probable_loss",
        "formula_human": "dynamic formula",
        "formula_code": f"{problem_code}.v1",
        "formula_id": "rule:1",
        "input_facts": [
            {
                "label": "unit profit",
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
        "trust_notes": [],
        "recheck_rule_human": "Re-run after source metrics refresh.",
        "calculation_warnings": [],
    }


def _create_tables(engine) -> None:
    for table in (
        WBAccount.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
        ResultEvent.__table__,
    ):
        table.create(engine)


def _session() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=1, name="Test account"))
    sync_session.flush()
    return sync_session, _AsyncSessionAdapter(sync_session)


def _add_dynamic_problem(sync_session: Session, *, status: str = "new") -> ProblemInstance:
    now = datetime(2026, 7, 6, tzinfo=timezone.utc)
    definition = ProblemDefinition(
        problem_code="negative_unit_profit",
        source_module="problem_engine",
        category="profitability",
        entity_type="product",
        title_template="Negative unit profit",
        description_template="Unit profit is negative.",
        recommendation_template="Review price, cost, ads spend, promo, and logistics.",
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
        recheck_rule_json={"human": "Re-run after source metrics refresh."},
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
        vendor_code="SKU-1",
        dedup_key="1:negative_unit_profit:1001",
        title="Negative unit profit for 1001",
        explanation="Unit profit is negative.",
        recommendation="Review price, cost, ads spend, promo, and logistics.",
        severity="high",
        status=status,
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


def test_problem_instance_action_preserves_evidence_ledger_contract() -> None:
    service = PortalService()
    now = datetime(2026, 7, 6, tzinfo=timezone.utc)
    instance = ProblemInstance(
        id=10,
        account_id=1,
        problem_code="negative_unit_profit",
        problem_definition_id=100,
        rule_version_id=200,
        source_module="problem_engine",
        entity_type="product",
        entity_id="1001",
        nm_id=1001,
        vendor_code="SKU-1",
        dedup_key="1:negative_unit_profit:1001",
        title="Negative unit profit for 1001",
        explanation="Unit profit is negative.",
        recommendation="Review price, cost, ads spend, promo, and logistics.",
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
        created_at=now,
        updated_at=now,
    )

    action = service._problem_instance_action(instance)

    assert action.source_module == "problem_engine"
    assert action.action_type == "negative_unit_profit"
    assert action.detector_code == "negative_unit_profit"
    assert action.evidence_ledger is not None
    assert action.evidence_ledger.formula_code == "negative_unit_profit.v1"
    assert action.source_references[0]["source_table"] == "mart_sku_daily"
    assert action.can_update is True
    assert action.solve_map is not None
    assert action.solve_map.steps[0].step_id == "evidence"
    price_step = next(step for step in action.solve_map.steps if step.action_code == "open_price_review")
    assert price_step.target_href == "/products/1001?tab=price&problem_instance_id=10"


@pytest.mark.parametrize(
    ("problem_code", "allowed_actions", "expected_action"),
    [
        ("missing_cost_blocks_profit", ["open_data_fix", "upload_cost", "map_sku", "recheck"], "open_data_fix"),
        ("negative_unit_profit", ["review_price", "review_cost", "recheck"], "open_price_review"),
        ("overstock_slow_moving", ["safe_promo", "review_content", "recheck"], "open_promo_planner"),
        ("overstock_slow_moving", ["review_price", "review_content", "recheck"], "open_price_review"),
        ("low_stock_risk", ["plan_supply", "reduce_promo", "reduce_ads", "recheck"], "open_supply_planner"),
        ("ads_spend_without_profit", ["review_ads", "review_content", "recheck"], "open_ads_dashboard"),
        ("promo_not_profitable", ["review_promo", "reduce_promo", "review_price", "review_cost", "recheck"], "open_promo_planner"),
        ("price_below_safe_margin", ["review_price", "pricing_review", "review_cost", "recheck"], "open_price_review"),
        ("dead_stock", ["safe_promo", "bundle", "review_content", "review_ads", "recheck"], "open_promo_planner"),
        ("fast_stock_depletion", ["plan_supply", "reduce_promo", "reduce_ads", "recheck"], "open_supply_planner"),
        ("card_quality_issue", ["run_checker", "recheck"], "run_checker"),
    ],
)
def test_core_dynamic_problem_solve_maps_are_problem_specific(
    problem_code: str,
    allowed_actions: list[str],
    expected_action: str,
) -> None:
    price_safety = {
        "status": "ok",
        "missing_required_metrics": [],
        "can_recommend_price_decrease": True,
    }

    solve_map = build_action_center_solve_map(
        problem_code=problem_code,
        allowed_actions=allowed_actions,
        nm_id=1001,
        problem_instance_id=123,
        data_freshness={"source_status": "fresh", "blocking_sources": []},
        price_safety=price_safety,
    )

    assert solve_map is not None
    assert solve_map.steps[0].step_id == "evidence"
    assert solve_map.steps[0].status == "ready"
    available_actions = [
        step.action_code
        for step in solve_map.steps
        if step.action_code and step.target_href and step.status in {"ready", "available"}
    ]
    assert available_actions[0] == expected_action
    assert solve_map.primary_action_code == expected_action
    assert available_actions[0] != "open_product"
    first_available = next(
        step
        for step in solve_map.steps
        if step.action_code and step.target_href and step.status in {"ready", "available"}
    )
    assert "problem_instance_id=123" in first_available.target_href
    if expected_action in {"open_supply_planner", "open_ads_dashboard"}:
        assert "nm_id=1001" in first_available.target_href
    if expected_action == "open_price_review":
        assert first_available.target_href == "/products/1001?tab=price&problem_instance_id=123"
    if expected_action == "open_promo_planner":
        assert first_available.target_href == "/products/1001?tab=promo&problem_instance_id=123"
    if expected_action == "run_checker":
        assert first_available.target_href == "/checker/1001?problem_instance_id=123"


def test_every_seeded_problem_code_returns_solve_map() -> None:
    for seed in INITIAL_PROBLEM_DEFINITION_SEEDS:
        solve_map = build_action_center_solve_map(
            problem_code=seed.problem_code,
            allowed_actions=seed.allowed_actions_json,
            nm_id=1001,
            problem_instance_id=123,
            data_freshness={"source_status": "fresh", "blocking_sources": []},
            price_safety={
                "status": "ok",
                "missing_required_metrics": [],
                "can_recommend_price_decrease": True,
            },
        )

        assert solve_map is not None, seed.problem_code
        assert solve_map.primary_action_code is not None, seed.problem_code
        assert solve_map.primary_action_code != "open_product", seed.problem_code


def test_missing_cost_solve_map_primary_opens_cost_or_data_fix_workflow() -> None:
    seed = next(item for item in INITIAL_PROBLEM_DEFINITION_SEEDS if item.problem_code == "missing_cost_blocks_profit")

    solve_map = build_action_center_solve_map(
        problem_code=seed.problem_code,
        allowed_actions=seed.allowed_actions_json,
        nm_id=1001,
        problem_instance_id=123,
        data_freshness={"source_status": "fresh", "blocking_sources": []},
    )

    assert solve_map is not None
    assert solve_map.primary_action_code == "upload_cost"
    primary_step = next(step for step in solve_map.steps if step.action_code == solve_map.primary_action_code)
    assert primary_step.target_href == "/costs?focus=missing-costs&problem_instance_id=123&nm_id=1001"


def test_low_stock_risk_primary_action_is_supply_planner() -> None:
    solve_map = build_action_center_solve_map(
        problem_code="low_stock_risk",
        allowed_actions=["plan_supply", "reduce_promo", "reduce_ads", "create_task", "recheck"],
        nm_id=1001,
        problem_instance_id=123,
        data_freshness={"source_status": "fresh", "blocking_sources": []},
    )

    assert solve_map is not None
    assert solve_map.primary_action_code == "open_supply_planner"
    primary_step = next(step for step in solve_map.steps if step.action_code == solve_map.primary_action_code)
    assert primary_step.target_href == "/stock-control?tab=supply&problem_instance_id=123&nm_id=1001"


def test_negative_unit_profit_blocks_price_when_cost_is_missing() -> None:
    solve_map = build_action_center_solve_map(
        problem_code="negative_unit_profit",
        allowed_actions=["review_price", "review_cost", "create_task", "recheck"],
        nm_id=1001,
        problem_instance_id=123,
        data_freshness={"source_status": "fresh", "blocking_sources": []},
        price_safety={
            "status": "data_incomplete",
            "missing_required_metrics": ["cost_price"],
            "can_recommend_price_decrease": False,
        },
    )

    assert solve_map is not None
    price_step = next(step for step in solve_map.steps if step.action_code == "open_price_review")
    assert price_step.status == "blocked"
    assert price_step.blocking_reason == "Не хватает данных для безопасной цены или промо."
    assert solve_map.primary_action_code == "upload_cost"


def test_overstock_solve_map_falls_back_to_checker_when_price_safety_blocks_promo() -> None:
    solve_map = build_action_center_solve_map(
        problem_code="overstock_slow_moving",
        allowed_actions=["safe_promo", "review_content", "recheck"],
        nm_id=1001,
        data_freshness={"source_status": "fresh", "blocking_sources": []},
        price_safety={
            "status": "data_incomplete",
            "missing_required_metrics": ["cost_price"],
            "can_recommend_price_decrease": False,
        },
    )

    assert solve_map is not None
    promo = next(step for step in solve_map.steps if step.action_code == "open_promo_planner")
    checker = next(step for step in solve_map.steps if step.action_code == "run_checker")
    assert promo.status == "blocked"
    assert checker.status == "available"
    assert solve_map.primary_action_code == "run_checker"


def test_create_task_is_safe_fallback_when_no_specific_action_exists() -> None:
    solve_map = build_action_center_solve_map(
        problem_code="price_below_safe_margin",
        allowed_actions=["create_task", "recheck"],
        nm_id=1001,
        problem_instance_id=123,
        data_freshness={"source_status": "fresh", "blocking_sources": []},
        price_safety={
            "status": "data_incomplete",
            "missing_required_metrics": ["cost_price"],
            "can_recommend_price_decrease": False,
        },
    )

    assert solve_map is not None
    assert solve_map.primary_action_code == "create_task"
    task_step = next(step for step in solve_map.steps if step.action_code == "create_task")
    assert task_step.target_href == "/action-center?problem_instance_id=123&nm_id=1001"


def test_dynamic_problem_action_suppresses_matching_profit_doctor_legacy_row() -> None:
    service = PortalService()
    dynamic = PortalActionRead(
        id="problem_engine:10",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="10",
        account_id=1,
        nm_id=1001,
        action_type="negative_unit_profit",
        title="Negative unit profit for 1001",
        priority="P1",
        severity="high",
        payload={"problem_code": "negative_unit_profit"},
        evidence_ledger=_ledger("negative_unit_profit"),
    )
    legacy = PortalActionRead(
        id="generated:finance:profit_leak:1001",
        source="profit_doctor",
        source_module="finance",
        source_id="finance:profit_leak:1001",
        account_id=1,
        nm_id=1001,
        action_type="review_profit",
        title="Товар продается в минус",
        priority="P1",
        severity="high",
        payload={"diagnosis_id": "diagnosis:finance:profit_leak:1001"},
    )

    filtered = service._prefer_dynamic_problem_actions([legacy, dynamic])

    assert filtered == [dynamic]


def test_dynamic_problem_action_suppresses_matching_money_dq_and_cost_legacy_rows() -> None:
    service = PortalService()
    dynamic_ads = PortalActionRead(
        id="problem_engine:11",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="11",
        account_id=1,
        nm_id=1001,
        action_type="ads_spend_without_profit",
        title="Ads spend without profit",
        payload={"problem_code": "ads_spend_without_profit"},
        evidence_ledger=_ledger("ads_spend_without_profit"),
    )
    dynamic_cost = PortalActionRead(
        id="problem_engine:12",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="12",
        account_id=1,
        nm_id=1002,
        action_type="missing_cost_blocks_profit",
        title="Missing cost",
        payload={"problem_code": "missing_cost_blocks_profit"},
        evidence_ledger=_ledger("missing_cost_blocks_profit"),
    )
    legacy_money = PortalActionRead(
        id="finance:ads",
        source="finance_actions",
        source_module="finance",
        account_id=1,
        nm_id=1001,
        action_type="ADS_REVIEW",
        title="Проверить рекламу",
        reason="ads_spend_without_profit",
    )
    legacy_dq = PortalActionRead(
        id="data_quality:missing_manual_cost",
        source="dq_issues",
        source_module="data_quality",
        source_id="missing_manual_cost",
        account_id=1,
        nm_id=1002,
        action_type="DATA_FIX",
        title="Нет себестоимости",
        payload={"code": "missing_manual_cost"},
    )
    legacy_cost = PortalActionRead(
        id="costs:10",
        source="costs_unresolved",
        source_module="costs",
        source_id="10",
        account_id=1,
        nm_id=1002,
        action_type="COST_FIX",
        title="Разобрать непривязанную себестоимость",
        reason="missing_manual_cost",
    )

    filtered = service._prefer_dynamic_problem_actions([legacy_money, legacy_dq, legacy_cost, dynamic_ads, dynamic_cost])

    assert filtered == [dynamic_ads, dynamic_cost]


def test_legacy_problem_card_remains_as_fallback_when_dynamic_missing() -> None:
    service = PortalService()
    legacy = PortalActionRead(
        id="finance:overstock",
        source="finance_actions",
        source_module="finance",
        account_id=1,
        nm_id=1001,
        action_type="LIQUIDATE_STOCK",
        title="Залежавшийся остаток",
        reason="overstock",
        expected_effect_amount=12000,
    )

    filtered = service._prefer_dynamic_problem_actions([legacy])
    block = service._business_issues_block(filtered, unavailable_sources=[])

    assert filtered == [legacy]
    assert block.data["summary"]["open_count"] == 1
    assert block.data["open"][0]["payload"]["problem_code"] == "overstock_slow_moving"


def test_show_legacy_problem_cards_false_hides_mapped_legacy_rows() -> None:
    service = PortalService()
    legacy = PortalActionRead(
        id="finance:overstock",
        source="finance_actions",
        source_module="finance",
        account_id=1,
        nm_id=1001,
        action_type="LIQUIDATE_STOCK",
        title="Залежавшийся остаток",
        reason="overstock",
    )

    filtered = service._prefer_dynamic_problem_actions([legacy], show_legacy_problem_cards=False)

    assert filtered == []


def test_dynamic_problem_engine_feature_flag_and_rollout_allowlist() -> None:
    service = PortalService()
    service.settings = SimpleNamespace(
        dynamic_problem_engine_enabled=False,
        dynamic_problem_engine_test_account_ids=[],
        show_legacy_problem_cards=True,
    )
    assert service._dynamic_problem_engine_enabled(1) is False

    service.settings = SimpleNamespace(
        dynamic_problem_engine_enabled=True,
        dynamic_problem_engine_test_account_ids=[2],
        show_legacy_problem_cards=True,
    )
    assert service._dynamic_problem_engine_enabled(1) is False
    assert service._dynamic_problem_engine_enabled(2) is True

    service.settings = SimpleNamespace(
        dynamic_problem_engine_enabled=True,
        dynamic_problem_engine_test_account_ids=[],
        show_legacy_problem_cards=False,
    )
    assert service._dynamic_problem_engine_enabled(1) is True
    assert service._show_legacy_problem_cards() is False


@pytest.mark.asyncio
async def test_dynamic_problem_appears_in_action_center_with_allowed_actions() -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)

    actions = await PortalService()._problem_instance_actions(session, account_id=1)

    assert len(actions) == 1
    action = actions[0]
    assert action.source_id == str(instance.id)
    assert action.detector_code == "negative_unit_profit"
    assert action.allowed_actions == ["open_price_review", "upload_cost", "recheck", "dismiss"]
    assert action.evidence_ledger is not None
    assert action.payload["status_history"][0]["event_type"] == "first_seen"
    assert action.payload["result_summary"]["before_snapshot"]["money_impact_amount"] == 100.0
    assert action.payload["result_summary"]["status_flow"]["current_status"] == "new"


@pytest.mark.asyncio
async def test_dynamic_problem_results_can_be_listed_by_problem_instance_id(monkeypatch) -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)
    service = PortalService()

    async def _fake_windows(*args, **kwargs):
        return {}

    monkeypatch.setattr(service.result_tracking, "finance_window_summaries", _fake_windows)
    await service.result_tracking.ensure_problem_before_snapshot(
        session,
        problem_instance_id=instance.id,
        created_by=42,
    )

    page = await service.results(
        session,
        account_id=1,
        problem_instance_id=instance.id,
        source_module="problem_engine",
        limit=50,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].problem_instance_id == instance.id
    assert page.items[0].problem_code == "negative_unit_profit"
    assert page.items[0].source_module == "problem_engine"
    assert page.items[0].event_type == "before_snapshot"
    assert page.items[0].warnings == ["causality_not_claimed"]


@pytest.mark.asyncio
async def test_dynamic_problem_results_filter_by_problem_code(monkeypatch) -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)
    service = PortalService()

    async def _fake_windows(*args, **kwargs):
        return {}

    monkeypatch.setattr(service.result_tracking, "finance_window_summaries", _fake_windows)
    await service.result_tracking.create_problem_status_event(
        session,
        problem_instance_id=instance.id,
        old_status="new",
        new_status="in_progress",
        created_by=42,
    )

    page = await service.results(
        session,
        account_id=1,
        problem_code="negative_unit_profit",
        source_module="problem_engine",
        limit=50,
        offset=0,
    )
    empty = await service.results(
        session,
        account_id=1,
        problem_code="missing_cost_blocks_profit",
        source_module="problem_engine",
        limit=50,
        offset=0,
    )

    assert page.total == 2
    assert {item.event_type for item in page.items} == {"before_snapshot", "action_started"}
    assert {item.problem_code for item in page.items} == {"negative_unit_profit"}
    assert empty.total == 0


@pytest.mark.asyncio
async def test_dynamic_problem_status_update_persists_and_records_history() -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)

    action = await PortalService().update_action_by_source(
        session,
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="in_progress",
            comment="Taking this one",
            assigned_to_user_id=7,
        ),
        user_id=42,
    )

    sync_session.refresh(instance)
    events = list(sync_session.execute(select(ProblemInstanceHistory).order_by(ProblemInstanceHistory.id)).scalars())
    assert action.status == "in_progress"
    assert action.payload["status_history"][-1]["status"] == "in_progress"
    assert action.payload["result_summary"]["status_flow"]["changed"] is True
    assert instance.status == "in_progress"
    assert instance.calculation_snapshot_json["action_center"]["assigned_to_user_id"] == 7
    assert {event.event_type for event in events} >= {"status_changed", "assigned", "comment_added"}
    assert events[0].actor_user_id == 42
    result_events = list(sync_session.execute(select(ResultEvent).order_by(ResultEvent.id)).scalars())
    result_event_types = [event.event_type for event in result_events]
    assert "action_center_notification" in result_event_types
    assert [
        event.event_type
        for event in result_events
        if event.event_type != "action_center_notification"
    ] == ["before_snapshot", "action_started"]
    assert all(event.problem_instance_id == instance.id for event in result_events)
    assert all(event.problem_code == "negative_unit_profit" for event in result_events)


@pytest.mark.asyncio
async def test_dynamic_problem_dismiss_reason_persists() -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)

    await PortalService().update_action_by_source(
        session,
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="ignored",
            comment="Known exception for this SKU",
        ),
        user_id=42,
    )

    sync_session.refresh(instance)
    events = list(sync_session.execute(select(ProblemInstanceHistory).order_by(ProblemInstanceHistory.id)).scalars())
    assert instance.status == "ignored"
    assert instance.dismiss_reason == "Known exception for this SKU"
    assert instance.dismissed_at is not None
    assert "dismissed" in {event.event_type for event in events}


@pytest.mark.asyncio
async def test_dynamic_problem_recheck_records_history_without_shadow_status_drift() -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)

    await PortalService().update_action_by_source(
        session,
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="problem_engine",
            source_id=f"problem_engine:{instance.id}",
            status="new",
            comment="Recheck from Action Center",
            event_type="recheck",
        ),
        user_id=42,
    )

    sync_session.refresh(instance)
    events = list(sync_session.execute(select(ProblemInstanceHistory).order_by(ProblemInstanceHistory.id)).scalars())
    assert instance.status == "new"
    assert [event.event_type for event in events] == ["comment_added", "recheck_requested"]
    result_events = list(sync_session.execute(select(ResultEvent).order_by(ResultEvent.id)).scalars())
    assert [event.event_type for event in result_events] == ["before_snapshot", "recheck_result"]
    assert result_events[-1].payload_json["saved_money_claimed"] is False


@pytest.mark.asyncio
async def test_dynamic_problem_completed_event_does_not_claim_saved_money() -> None:
    sync_session, session = _session()
    instance = _add_dynamic_problem(sync_session)

    service = PortalService()
    await service.update_action_by_source(
        session,
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="in_progress",
            comment="Started checking price and costs",
        ),
        user_id=42,
    )

    await service.update_action_by_source(
        session,
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="problem_engine",
            source_id=str(instance.id),
            status="done",
            comment="Completed after checking price and costs",
        ),
        user_id=42,
    )

    sync_session.refresh(instance)
    result_events = list(sync_session.execute(select(ResultEvent).order_by(ResultEvent.id)).scalars())
    completed = [event for event in result_events if event.event_type == "action_completed"][0]
    read = PortalService().result_tracking._read(completed)
    assert completed.problem_instance_id == instance.id
    assert read.outcome == "not_enough_data"
    assert read.after_snapshot == {}
    assert completed.payload_json["saved_money_claimed"] is False
    assert "Ожидаемый эффект не считается сэкономленными деньгами" in completed.payload_json["money_note"]
    assert "saved_money" not in completed.message.lower()


def test_dynamic_problem_filters_by_problem_trust_and_impact() -> None:
    service = PortalService()
    dynamic = PortalActionRead(
        id="problem_engine:10",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="10",
        account_id=1,
        nm_id=1001,
        action_type="negative_unit_profit",
        title="Negative unit profit for 1001",
        priority="P1",
        severity="high",
        impact_type="probable_loss",
        trust_state="estimated",
        payload={"problem_code": "negative_unit_profit"},
        evidence_ledger=_ledger("negative_unit_profit"),
    )
    other = PortalActionRead(
        id="problem_engine:11",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="11",
        account_id=1,
        nm_id=1002,
        action_type="missing_cost_blocks_profit",
        title="Missing cost",
        priority="P0",
        severity="critical",
        impact_type="data_blocker",
        trust_state="blocked",
        payload={"problem_code": "missing_cost_blocks_profit"},
        evidence_ledger=_ledger("missing_cost_blocks_profit"),
    )

    filtered = service._filter_actions(
        [dynamic, other],
        status=None,
        source_module=["problem_engine"],
        priority=None,
        problem_code=["negative_unit_profit"],
        trust_state=["estimated"],
        impact_type=["probable_loss"],
    )

    assert filtered == [dynamic]


def test_product_business_issues_block_groups_open_resolved_and_money_trust() -> None:
    service = PortalService()
    open_problem = PortalActionRead(
        id="problem_engine:10",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="10",
        account_id=1,
        nm_id=1001,
        action_type="overstock_slow_moving",
        detector_code="overstock_slow_moving",
        title="Overstock",
        priority="P2",
        severity="medium",
        status="new",
        reason="Stock is slow moving.",
        next_step="Review promo.",
        expected_effect_amount=Decimal("5000"),
        impact_type="blocked_cash",
        trust_state="estimated",
        payload={"problem_code": "overstock_slow_moving", "category": "stock", "allowed_actions": ["safe_promo", "recheck"]},
        evidence_ledger=_ledger("overstock_slow_moving"),
        allowed_actions=["safe_promo", "recheck"],
    )
    resolved_problem = PortalActionRead(
        id="problem_engine:11",
        source="dynamic_problem_instances",
        source_module="problem_engine",
        source_id="11",
        account_id=1,
        nm_id=1001,
        action_type="negative_unit_profit",
        detector_code="negative_unit_profit",
        title="Negative profit",
        priority="P1",
        severity="high",
        status="done",
        expected_effect_amount=Decimal("1000"),
        impact_type="confirmed_loss",
        trust_state="estimated",
        payload={"problem_code": "negative_unit_profit", "category": "profitability"},
        raw={"status": "resolved"},
        evidence_ledger=_ledger("negative_unit_profit"),
    )

    block = service._business_issues_block([open_problem, resolved_problem], unavailable_sources=[])
    data = block.data

    assert block.status == "warning"
    assert data["summary"]["open_count"] == 1
    assert data["summary"]["resolved_count"] == 1
    assert data["summary"]["by_trust_state"]["estimated"] == 2
    assert data["summary"]["money_impact"]["confirmed_loss_amount"] == 0
    assert data["summary"]["money_impact"]["blocked_cash_amount"] == 5000
    assert data["summary"]["money_impact"]["non_confirmed_money_amount"] == 6000
    stock_group = next(group for group in data["groups"] if group["key"] == "stock")
    profitability_group = next(group for group in data["groups"] if group["key"] == "profitability")
    assert stock_group["open_count"] == 1
    assert profitability_group["resolved_count"] == 1
    assert data["open"][0]["evidence_ledger"]["formula_code"] == "overstock_slow_moving.v1"
