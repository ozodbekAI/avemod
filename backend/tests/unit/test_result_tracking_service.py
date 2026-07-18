from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.models.control_tower import ActionRecommendation
from app.models.operator import ResultEvent
from app.models.problem_engine import ProblemInstance
from app.schemas.portal import PortalResultEventCreate, PortalResultEventRead
from app.services.result_tracking import ResultTrackingService


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "portal"


class _ScalarResult:
    def __init__(self, rows=None, scalar=0):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def scalar_one(self):
        return self._scalar

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self) -> None:
        self.action = ActionRecommendation(
            id=10,
            account_id=1,
            nm_id=1001,
            sku_id=11,
            vendor_code="VC-1",
            action_type="PRICE_REVIEW",
            priority="P2",
            reason_code="price",
            reason="Review price",
            action_unique_key="a",
        )
        self.action.payload = {"before_snapshot": {"profit": 100.0, "ad_spend": 20.0}}
        self.added = []

    async def get(self, model, key):
        if model is ActionRecommendation and int(key) == self.action.id:
            return self.action
        return None

    def add(self, row):
        self.added.append(row)

    async def flush(self):
        for index, row in enumerate(self.added, start=1):
            if getattr(row, "id", None) is None:
                row.id = index

    async def refresh(self, row):
        return None

    async def execute(self, stmt):
        rows = [row for row in self.added if isinstance(row, ResultEvent)]
        return _ScalarResult(rows=rows, scalar=len(rows))


def test_result_tracking_compare_uses_safe_outcomes() -> None:
    service = ResultTrackingService()

    improved = service.compare({"profit": 100, "ad_spend": 50}, {"profit": 120, "ad_spend": 40})
    worse = service.compare({"profit": 100}, {"profit": 80})
    neutral = service.compare({"profit": 100}, {"profit": 100})
    missing = service.compare({"profit": 100}, {"rating": 5})

    assert improved["outcome"] == "improved"
    assert worse["outcome"] == "worse"
    assert neutral["outcome"] == "neutral"
    assert missing["outcome"] == "not_enough_data"
    assert improved["causality"] == "not_claimed"


@pytest.mark.asyncio
async def test_result_tracking_create_event_stores_before_after_and_comparison() -> None:
    service = ResultTrackingService()
    session = _FakeSession()

    result = await service.create_event(
        session,
        account_id=1,
        action_id=10,
        payload=PortalResultEventCreate(
            event_type="price_changed",
            nm_id=1001,
            before_snapshot={"profit": 100},
            after_snapshot={"profit": 125},
            snapshot_day=7,
        ),
        created_by=2,
    )

    assert result.outcome == "improved"
    assert result.comparison["metrics"]["profit"]["delta"] == 25
    assert result.warnings == ["causality_not_claimed"]
    assert session.added[0].source_module == "result_tracking"
    assert session.added[0].payload_json["causality_note"] == "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
    notification = next(
        row
        for row in session.added
        if isinstance(row, ResultEvent)
        and row.source_module == "action_center_notifications"
        and row.event_type == "action_center_notification"
    )
    assert notification.payload_json["notification_type"] == "result_improved"
    assert notification.payload_json["outcome"] == "improved"
    assert notification.payload_json["saved_money_claimed"] is False


def test_result_tracking_read_preserves_experiment_evidence_payload() -> None:
    service = ResultTrackingService()
    event = ResultEvent(
        id=99,
        account_id=1,
        source_module="experiments",
        source_id="44",
        external_id="44",
        nm_id=1001,
        event_type="experiment_evaluated",
        status="done",
        external_status="improved",
        message="Наблюдаемое улучшение. Это наблюдаемая связь, а не доказанная причинность.",
        created_at=datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc),
        payload_json={
            "experiment_id": 44,
            "outcome": "improved",
            "confidence": "medium",
            "baseline_window": {"day_count": 7},
            "post_window": {"day_count": 14},
            "primary_metric": "conversion_rate",
            "primary_result": {"metric": "conversion_rate", "relative_change_percent": 6.5, "unit": "percent"},
            "data_sufficiency": {"post_orders": 12, "stockout_days": 0, "missing_post_days": 0},
            "confounders": [],
            "causality_note": "Это наблюдаемая связь, а не доказанная причинность.",
        },
    )

    read = service._read(event)

    assert read.outcome == "improved"
    assert read.payload["baseline_window"]["day_count"] == 7
    assert read.payload["post_window"]["day_count"] == 14
    assert read.payload["primary_result"]["relative_change_percent"] == 6.5
    assert "причинность" in read.calculation_note.lower()


@pytest.mark.asyncio
async def test_result_tracking_before_snapshot_is_idempotent() -> None:
    service = ResultTrackingService()
    session = _FakeSession()

    await service.ensure_before_snapshot(session, account_id=1, action_id=10, created_by=2)
    await service.ensure_before_snapshot(session, account_id=1, action_id=10, created_by=2)

    assert len(session.added) == 1
    assert session.added[0].event_type == "before_snapshot"
    assert session.added[0].payload_json["before_snapshot"]["profit"] == 100.0


@pytest.mark.asyncio
async def test_result_tracking_action_completed_without_after_data_is_honest() -> None:
    service = ResultTrackingService()
    session = _FakeSession()

    result = await service.create_action_completed_event(session, account_id=1, action_id=10, created_by=2)

    assert result.event_type == "action_completed"
    assert result.outcome == "not_enough_data"
    assert result.before_snapshot["profit"] == 100.0
    assert result.after_snapshot == {}
    assert len([row for row in session.added if row.event_type == "before_snapshot"]) == 1
    completed_events = [row for row in session.added if row.event_type == "action_completed"]
    assert len(completed_events) == 1
    assert completed_events[0].payload_json["saved_money_claimed"] is False
    assert completed_events[0].payload_json.get("saved_money_amount") is None
    assert [
        row
        for row in session.added
        if isinstance(row, ResultEvent)
        and row.source_module == "action_center_notifications"
    ] == []


def test_problem_before_snapshot_contains_business_and_evidence_context() -> None:
    service = ResultTrackingService()
    problem = ProblemInstance(
        id=55,
        account_id=1,
        problem_code="negative_unit_profit",
        entity_type="product",
        entity_id="1001",
        dedup_key="1:negative_unit_profit:1001",
        nm_id=1001,
        vendor_code="VC-1",
        title="Товар 1001 продаётся в минус",
        explanation="Прибыль на единицу ниже нуля.",
        recommendation="Проверьте цену и себестоимость.",
        status="new",
        severity="high",
        source_module="problem_engine",
        trust_state="confirmed",
        impact_type="confirmed_loss",
        money_impact_amount=1250.0,
        money_impact_currency="RUB",
        evidence_ledger_json={
            "formula_human": "profit < 0",
            "formula_code": "profit.negative.v1",
            "input_facts": [
                {"metric_code": "price", "value": 850},
                {"metric_code": "stock_qty", "value": 18},
                {"metric_code": "orders", "value": 7},
                {"metric_code": "revenue", "value": 5950},
                {"metric_code": "profit", "value": -1250},
            ],
            "source_refs": [{"source": "finance"}],
            "missing_data": [],
        },
    )

    snapshot = service._problem_before_snapshot(problem)

    assert snapshot["status"] == "new"
    assert snapshot["title"] == "Товар 1001 продаётся в минус"
    assert snapshot["explanation"] == "Прибыль на единицу ниже нуля."
    assert snapshot["recommendation"] == "Проверьте цену и себестоимость."
    assert snapshot["price"] == 850
    assert snapshot["stock"] == 18
    assert snapshot["orders"] == 7
    assert snapshot["revenue"] == 5950
    assert snapshot["profit"] == -1250
    assert snapshot["money_at_risk"] == {
        "amount": 1250.0,
        "currency": "RUB",
        "impact_type": "confirmed_loss",
        "trust_state": "confirmed",
    }
    assert snapshot["formula_human"] == "profit < 0"
    assert snapshot["evidence_snapshot"]["formula_code"] == "profit.negative.v1"
    assert snapshot["evidence_snapshot"]["source_refs"] == [{"source": "finance"}]


def test_problem_before_snapshot_promotes_product_specific_result_metrics() -> None:
    service = ResultTrackingService()
    cases = [
        (
            "low_stock_risk",
            [
                {"metric_code": "stock_days_left", "value": 2},
                {"metric_code": "orders_7d", "value": 18},
                {"metric_code": "stockout_days", "value": 1},
            ],
            {"stock_days_left": 2, "orders": 18, "stockout_days": 1},
        ),
        (
            "overstock_slow_moving",
            [
                {"metric_code": "days_of_stock", "value": 120},
                {"metric_code": "sales_velocity_daily", "value": 1.5},
                {"metric_code": "overstock_qty", "value": 80},
            ],
            {"days_of_stock": 120, "sales_velocity": 1.5, "surplus_stock": 80},
        ),
        (
            "negative_unit_profit",
            [
                {"metric_code": "unit_profit", "value": -120},
                {"metric_code": "margin_pct", "value": -8},
            ],
            {"unit_profit": -120, "margin_pct": -8},
        ),
        (
            "ads_spend_without_profit",
            [
                {"metric_code": "ad_spend_7d", "value": 1000},
                {"metric_code": "unit_profit_after_ads", "value": -50},
                {"metric_code": "roas", "value": 1.4},
                {"metric_code": "drr_percent", "value": 18},
            ],
            {"ad_spend": 1000, "unit_profit_after_ads": -50, "roas": 1.4, "drr": 18},
        ),
        (
            "card_quality_issue",
            [
                {"metric_code": "card_quality_score", "value": 62},
                {"metric_code": "card_quality_issue_count", "value": 4},
            ],
            {"quality_score": 62, "open_issue_count": 4},
        ),
    ]

    for problem_code, input_facts, expected in cases:
        problem = ProblemInstance(
            id=55,
            account_id=1,
            problem_code=problem_code,
            entity_type="product",
            entity_id="1001",
            dedup_key=f"1:{problem_code}:1001",
            nm_id=1001,
            vendor_code="VC-1",
            title="Problem",
            status="new",
            severity="high",
            source_module="problem_engine",
            trust_state="estimated",
            impact_type="probable_risk",
            evidence_ledger_json={"input_facts": input_facts},
        )

        snapshot = service._problem_before_snapshot(problem)

        assert snapshot["result_metrics"] == expected
        for key, value in expected.items():
            assert snapshot[key] == value
        assert snapshot["result_metric_keys"] == list(expected.keys())


def test_result_tracking_effect_summary_uses_product_specific_metrics_and_after_data_gate() -> None:
    service = ResultTrackingService()
    cases = [
        (
            "low_stock_risk",
            {"stock_days_left": 2, "orders": 18, "stockout_days": 1, "profit": -500},
            {"stock_days_left": 7, "orders": 21, "stockout_days": 0, "profit": 200},
            ("stock_days_left", "orders", "stockout_days"),
        ),
        (
            "overstock_slow_moving",
            {"days_of_stock": 120, "sales_velocity": 1.5, "surplus_stock": 80, "profit": 100},
            {"days_of_stock": 70, "sales_velocity": 2.5, "surplus_stock": 30, "profit": 150},
            ("days_of_stock", "sales_velocity", "surplus_stock"),
        ),
        (
            "negative_unit_profit",
            {"unit_profit": -120, "margin_pct": -8, "orders": 10},
            {"unit_profit": 30, "margin_pct": 12, "orders": 12},
            ("unit_profit", "margin_pct"),
        ),
        (
            "ads_spend_without_profit",
            {"ad_spend": 1000, "unit_profit_after_ads": -50, "roas": 1.4, "drr": 18},
            {"ad_spend": 700, "unit_profit_after_ads": 20, "roas": 2.1, "drr": 11},
            ("ad_spend", "unit_profit_after_ads", "roas", "drr"),
        ),
        (
            "card_quality_issue",
            {"quality_score": 62, "open_issue_count": 4, "orders": 5},
            {"quality_score": 86, "open_issue_count": 1, "orders": 7},
            ("quality_score", "open_issue_count"),
        ),
    ]

    for problem_code, before, after, expected_keys in cases:
        event = PortalResultEventRead(
            id=f"{problem_code}-event",
            account_id=1,
            problem_instance_id=55,
            problem_code=problem_code,
            source_module="problem_engine",
            event_type="recheck_result",
            outcome="improved",
            before_snapshot=before,
            after_snapshot=after,
            comparison=service.compare(before, after, problem_code=problem_code),
            confidence="medium",
        )

        summary = service.effect_summary([event])

        assert summary["comparison"] == "improved"
        assert set(summary["metrics"]) == set(expected_keys)
        assert summary["saved_money_claimed"] is False
        assert summary["result_metric_keys"] == list(expected_keys)

    waiting = PortalResultEventRead(
        id="waiting-low-stock",
        account_id=1,
        problem_instance_id=56,
        problem_code="low_stock_risk",
        source_module="problem_engine",
        event_type="action_completed",
        outcome="improved",
        before_snapshot={"stock_days_left": 2, "orders": 18},
        after_snapshot={},
        comparison={
            "outcome": "improved",
            "metrics": {"stock_days_left": {"before": 2, "after": 7, "delta": 5, "direction": "improved"}},
        },
        confidence="high",
    )
    waiting_summary = service.effect_summary([waiting])

    assert waiting_summary["comparison"] == "not_enough_data"
    assert waiting_summary["metrics"] == {}
    assert waiting_summary["saved_money_claimed"] is False


def test_result_tracking_read_does_not_accept_improved_outcome_without_after_snapshot() -> None:
    service = ResultTrackingService()
    event = ResultEvent(
        id=77,
        account_id=1,
        problem_instance_id=56,
        problem_code="low_stock_risk",
        source_module="problem_engine",
        source_id="56",
        event_type="action_completed",
        status="done",
        payload_json={
            "outcome": "improved",
            "before_snapshot": {"stock_days_left": 2},
            "after_snapshot": {},
            "comparison": {
                "outcome": "improved",
                "metrics": {"stock_days_left": {"before": 2, "after": 7, "delta": 5, "direction": "improved"}},
            },
            "saved_money_claimed": True,
        },
    )

    read = service._read(event)

    assert read.outcome == "not_enough_data"
    assert read.after_snapshot == {}
    assert read.confidence == "low"
    assert read.payload["saved_money_claimed"] is False


def test_problem_timeline_summary_exposes_professional_contract_for_pending_data() -> None:
    service = ResultTrackingService()
    problem = ProblemInstance(
        id=56,
        account_id=1,
        problem_code="low_stock_risk",
        entity_type="product",
        entity_id="1001",
        dedup_key="1:low_stock_risk:1001",
        nm_id=1001,
        vendor_code="VC-1",
        title="Stock will run out",
        explanation="Low stock days left.",
        recommendation="Plan supply.",
        status="done",
        severity="high",
        source_module="problem_engine",
        trust_state="estimated",
        impact_type="probable_risk",
        evidence_ledger_json={
            "formula_human": "stock_days_left < 3",
            "input_facts": [{"metric_code": "stock_days_left", "value": 2}],
            "missing_data": [],
        },
    )
    before = {
        "problem_instance_id": 56,
        "problem_code": "low_stock_risk",
        "stock_days_left": 2,
        "orders": 18,
        "result_metrics": {"stock_days_left": 2, "orders": 18},
        "money_at_risk": {"amount": 500.0, "currency": "RUB", "impact_type": "probable_risk"},
    }
    items = [
        PortalResultEventRead(
            id="1",
            account_id=1,
            problem_instance_id=56,
            problem_code="low_stock_risk",
            source_module="problem_engine",
            event_type="before_snapshot",
            outcome="not_enough_data",
            before_snapshot=before,
            payload={"saved_money_claimed": False},
            created_at=datetime(2026, 7, 6, 10, 0, tzinfo=timezone.utc),
        ),
        PortalResultEventRead(
            id="2",
            account_id=1,
            problem_instance_id=56,
            problem_code="low_stock_risk",
            source_module="problem_engine",
            event_type="action_completed",
            outcome="not_enough_data",
            before_snapshot=before,
            after_snapshot={},
            payload={"saved_money_claimed": False},
            created_at=datetime(2026, 7, 6, 11, 0, tzinfo=timezone.utc),
        ),
        PortalResultEventRead(
            id="3",
            account_id=1,
            problem_instance_id=56,
            problem_code="low_stock_risk",
            source_module="problem_engine",
            event_type="recheck_result",
            outcome="not_enough_data",
            before_snapshot=before,
            after_snapshot={},
            payload={"saved_money_claimed": False},
            created_at=datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc),
        ),
    ]

    summary = service.problem_timeline_summary(problem=problem, items=items, base_summary=service.effect_summary(items))

    assert summary["problem_instance_id"] == 56
    assert summary["problem_identity"]["problem_code"] == "low_stock_risk"
    assert summary["before_snapshot"]["stock_days_left"] == 2
    assert len(summary["action_events"]) == 1
    assert summary["action_events"][0]["event_type"] == "action_completed"
    assert len(summary["recheck_events"]) == 1
    assert summary["after_snapshot"] == {}
    assert summary["measured_comparison"] is None
    assert summary["result_status"] == "pending_data"
    assert summary["is_measured"] is False
    assert summary["saved_money_claimed"] is False
    assert summary["correlation_disclaimer"] == "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
    assert summary["action_center_href"] == "/action-center?problem_instance_id=56&nm_id=1001"
    assert summary["product_href"] == "/products/1001?problem_instance_id=56"
    assert summary["evidence_ledger"]["formula_human"] == "stock_days_left < 3"
    assert "missing_after_snapshot" in summary["warnings"]


def test_problem_timeline_summary_exposes_measured_comparison_without_saved_money_claim() -> None:
    service = ResultTrackingService()
    problem = ProblemInstance(
        id=57,
        account_id=1,
        problem_code="low_stock_risk",
        entity_type="product",
        entity_id="1001",
        dedup_key="1:low_stock_risk:1001",
        nm_id=1001,
        vendor_code="VC-1",
        title="Stock will run out",
        explanation="Low stock days left.",
        recommendation="Plan supply.",
        status="done",
        severity="high",
        source_module="problem_engine",
        trust_state="estimated",
        impact_type="probable_risk",
        evidence_ledger_json={"input_facts": [{"metric_code": "stock_days_left", "value": 2}]},
    )
    before = {"stock_days_left": 2, "orders": 18}
    after = {"stock_days_left": 8, "orders": 20}
    event = PortalResultEventRead(
        id="4",
        account_id=1,
        problem_instance_id=57,
        problem_code="low_stock_risk",
        source_module="problem_engine",
        event_type="recheck_result",
        outcome="improved",
        before_snapshot=before,
        after_snapshot=after,
        comparison=service.compare(before, after, problem_code="low_stock_risk"),
        payload={"saved_money_claimed": False},
        created_at=datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc),
    )

    summary = service.problem_timeline_summary(problem=problem, items=[event], base_summary=service.effect_summary([event]))

    assert summary["result_status"] == "improved"
    assert summary["measured_comparison"]["metrics"]["stock_days_left"]["direction"] == "improved"
    assert summary["measured_comparison"]["saved_money_claimed"] is False
    assert summary["saved_money_claimed"] is False
    assert summary["is_measured"] is True


@pytest.mark.asyncio
async def test_result_tracking_records_photo_fix_lifecycle_without_marketplace_apply() -> None:
    service = ResultTrackingService()
    session = _FakeSession()

    started = await service.create_event(
        session,
        account_id=1,
        action_id=10,
        payload=PortalResultEventCreate(
            event_type="photo_fix_started",
            nm_id=1001,
            payload={"source_issue_id": "78", "target_module": "photo_studio", "marketplace_change": False},
        ),
        created_by=2,
    )
    completed = await service.create_event(
        session,
        account_id=1,
        action_id=10,
        payload=PortalResultEventCreate(
            event_type="photo_fix_completed",
            nm_id=1001,
            before_snapshot={"rating": 4.0},
            after_snapshot={"rating": 4.3},
            payload={"source_issue_id": "78", "target_module": "photo_studio", "marketplace_change": False},
        ),
        created_by=2,
    )
    skipped = await service.create_event(
        session,
        account_id=1,
        action_id=10,
        payload=PortalResultEventCreate(
            event_type="photo_fix_skipped",
            nm_id=1001,
            payload={"source_issue_id": "78", "target_module": "photo_studio", "marketplace_change": False},
        ),
        created_by=2,
    )

    assert started.outcome == "pending"
    assert completed.outcome == "improved"
    assert skipped.outcome == "neutral"
    assert service._result_module(started) == "photo"
    assert {row.event_type for row in session.added} >= {"photo_fix_started", "photo_fix_completed", "photo_fix_skipped"}
    assert all((row.payload_json or {}).get("marketplace_change") is False for row in session.added)


@pytest.mark.asyncio
async def test_result_tracking_list_results_includes_unified_source_modules(monkeypatch) -> None:
    service = ResultTrackingService()
    session = _FakeSession()
    async def _fake_windows(*args, **kwargs):
        return {}

    monkeypatch.setattr(service, "finance_window_summaries", _fake_windows)
    session.added.extend(
        [
            ResultEvent(
                id=1,
                account_id=1,
                action_id=10,
                source_module="result_tracking",
                source_id="10",
                external_id="10",
                nm_id=1001,
                event_type="action_completed",
                status="done",
                message="Action marked done.",
                created_at=datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc),
                payload_json={
                    "action_id": 10,
                    "before_snapshot": {"profit": 100},
                    "after_snapshot": {"profit": 125},
                    "comparison": service.compare({"profit": 100}, {"profit": 125}),
                    "outcome": "improved",
                    "created_by": 2,
                },
            ),
            ResultEvent(
                id=2,
                account_id=1,
                source_module="claims",
                source_id="case:10",
                external_id="case:10",
                nm_id=1001,
                event_type="submit_blocked_confirmation_required",
                status="blocked",
                message="Отправка претензии требует явного confirm=true.",
                created_at=datetime(2026, 6, 12, 10, 5, tzinfo=timezone.utc),
                payload_json={"created_by": 2, "data": {"support_token": "must-not-leak"}},
            ),
            ResultEvent(
                id=3,
                account_id=1,
                source_module="reputation",
                source_id="draft-review-fb1",
                external_id="draft-review-fb1",
                nm_id=1001,
                event_type="publish_blocked_confirmation_required",
                status="blocked",
                message="Публикация требует явного confirm=true.",
                created_at=datetime(2026, 6, 12, 10, 10, tzinfo=timezone.utc),
                payload_json={"created_by": 2, "data": {"customer_email": "buyer@example.test"}},
            ),
            ResultEvent(
                id=4,
                account_id=1,
                source_module="claims",
                source_id="case:11",
                external_id="case:11",
                nm_id=1001,
                event_type="claim_submitted",
                status="pending",
                message="Claim submitted and waiting for marketplace response.",
                created_at=datetime(2026, 6, 12, 10, 15, tzinfo=timezone.utc),
                payload_json={"created_by": 2},
            ),
        ]
    )

    page = await service.list_results(session, account_id=1, nm_id=1001)

    assert page.total == 4
    assert {item.source_module for item in page.items} == {"result_tracking", "claims", "reputation"}
    assert {item.event_type for item in page.items} >= {
        "action_completed",
        "submit_blocked_confirmation_required",
        "publish_blocked_confirmation_required",
        "claim_submitted",
    }
    assert all(item.source_id for item in page.items)
    assert [item for item in page.items if item.event_type == "submit_blocked_confirmation_required"][0].outcome == "blocked"
    assert [item for item in page.items if item.event_type == "publish_blocked_confirmation_required"][0].outcome == "blocked"
    assert [item for item in page.items if item.event_type == "claim_submitted"][0].outcome == "pending"
    assert page.by_module["action_center"]["outcomes"]["improved"] == 1
    assert page.by_module["claims"]["total"] == 2
    assert page.by_module["reputation"]["outcomes"]["blocked"] == 1
    assert page.by_outcome["pending"] == 1
    assert page.by_outcome["blocked"] == 2
    assert len(page.pending_followups) == 3
    assert page.recent_events == page.items
    assert "must-not-leak" not in str(page.model_dump(mode="json"))
    assert "buyer@example" not in str(page.model_dump(mode="json"))


def test_result_tracking_effect_summary_filters_metrics_and_scrubs_snapshots() -> None:
    service = ResultTrackingService()
    event = ResultEvent(
        id=1,
        account_id=1,
        source_module="result_tracking",
        source_id="10",
        event_type="action_completed",
        status="done",
        payload_json={
            "action_id": 10,
            "before_snapshot": {"profit": 100, "token": "must-not-leak", "customer_email": "buyer@example.test"},
            "after_snapshot": {"profit": 120, "rating": 4.8, "authorization": "secret"},
            "comparison": service.compare({"profit": 100}, {"profit": 120}),
            "outcome": "improved",
        },
    )

    item = service._read(event)
    summary = service.effect_summary([item])

    assert summary["comparison"] == "improved"
    assert summary["metrics"]["profit"]["delta"] == 20
    assert summary["disclaimer"] == "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
    assert "must-not-leak" not in str(summary)
    assert "buyer@example" not in str(summary)
    assert "secret" not in str(summary)


def test_result_tracking_by_module_covers_operator_modules_and_alias_filters() -> None:
    service = ResultTrackingService()
    items = [
        PortalResultEventRead(id="1", account_id=1, source_module="result_tracking", event_type="action_completed", outcome="improved"),
        PortalResultEventRead(id="2", account_id=1, source_module="profit_doctor", event_type="doctor_action_done", outcome="neutral"),
        PortalResultEventRead(id="3", account_id=1, source_module="claims", event_type="claim_submitted", outcome="pending"),
        PortalResultEventRead(id="4", account_id=1, source_module="reputation", event_type="reply_draft_ready", outcome="pending"),
        PortalResultEventRead(id="5", account_id=1, source_module="experiments", event_type="experiment_finished", outcome="not_enough_data"),
        PortalResultEventRead(id="6", account_id=1, source_module="checker", event_type="card_issue_fixed", outcome="improved"),
        PortalResultEventRead(id="7", account_id=1, source_module="grouping_beta", event_type="grouping_previewed", outcome="blocked"),
        PortalResultEventRead(id="8", account_id=1, source_module="stock", event_type="stock_action_done", outcome="worse"),
    ]

    by_module = service.by_module_summary(items)
    by_outcome = service.by_outcome_summary(items)

    assert by_module["action_center"]["outcomes"]["improved"] == 1
    assert by_module["profit_doctor"]["total"] == 1
    assert by_module["claims"]["pending_followups"] == 1
    assert by_module["reputation"]["outcomes"]["pending"] == 1
    assert by_module["experiments"]["outcomes"]["not_enough_data"] == 1
    assert by_module["checker"]["outcomes"]["improved"] == 1
    assert by_module["grouping"]["outcomes"]["blocked"] == 1
    assert by_module["stockops"]["outcomes"]["worse"] == 1
    assert by_outcome == {
        "improved": 2,
        "worse": 1,
        "neutral": 1,
        "pending": 2,
        "blocked": 1,
        "not_enough_data": 1,
    }
    assert service._source_module_filter_values("grouping") == ["grouping", "grouping_beta"]
    assert service._source_module_filter_values("stockops") == ["stockops", "stock_ops", "stock"]
    assert "result_tracking" in service._source_module_filter_values("action_center")


def test_result_tracking_empty_page_has_stable_aggregate_shape() -> None:
    service = ResultTrackingService()

    page = service.empty_page(limit=25, offset=0)

    assert page.status == "ok"
    assert page.total == 0
    assert page.items == []
    assert page.recent_events == []
    assert page.pending_followups == []
    assert page.by_outcome == {
        "improved": 0,
        "worse": 0,
        "neutral": 0,
        "pending": 0,
        "blocked": 0,
        "not_enough_data": 0,
    }
    for module in ("action_center", "profit_doctor", "claims", "reputation", "experiments", "checker", "photo", "grouping", "stockops"):
        assert page.by_module[module]["total"] == 0
        assert set(page.by_module[module]["outcomes"]) == set(page.by_outcome)
    assert page.summary["comparison"] == "not_enough_data"
    assert page.summary["confidence"] == "low"


@pytest.mark.asyncio
async def test_result_tracking_finance_window_summary_compares_real_metrics(monkeypatch) -> None:
    service = ResultTrackingService()
    snapshots = [
        {"_rows_count": 7, "revenue": 7000.0, "profit": 1000.0, "orders": 70.0},
        {"_rows_count": 7, "revenue": 9000.0, "profit": 1400.0, "orders": 90.0},
    ]

    async def _fake_snapshot(*args, **kwargs):
        return snapshots.pop(0)

    monkeypatch.setattr(service, "_finance_window_snapshot", _fake_snapshot)

    summary = await service.finance_window_summary(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        window_days=7,
        action_at=date(2026, 5, 20),
    )

    assert summary["status"] == "improved"
    assert summary["before_window"] == {"date_from": "2026-05-13", "date_to": "2026-05-19"}
    assert summary["after_window"] == {"date_from": "2026-05-20", "date_to": "2026-05-26"}
    assert summary["metrics"]["revenue"]["delta"] == 2000.0
    assert summary["metrics"]["profit"]["direction"] == "improved"
    assert summary["disclaimer"] == "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."


@pytest.mark.asyncio
async def test_result_tracking_finance_windows_return_not_enough_data(monkeypatch) -> None:
    service = ResultTrackingService()

    async def _fake_snapshot(*args, **kwargs):
        return {"_rows_count": 0}

    monkeypatch.setattr(service, "_finance_window_snapshot", _fake_snapshot)

    summary = await service.finance_window_summary(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        window_days=14,
        action_at=date(2026, 5, 20),
    )

    assert summary["status"] == "not_enough_data"
    assert summary["metrics"] == {}
    assert "finance mart rows are missing" in summary["explanation"]


@pytest.mark.asyncio
async def test_result_tracking_finance_window_requires_complete_after_window() -> None:
    service = ResultTrackingService()

    summary = await service.finance_window_summary(
        _FakeSession(),
        account_id=1,
        nm_id=1001,
        window_days=14,
        action_at=date.today() - timedelta(days=1),
    )

    assert summary["status"] == "not_enough_data"
    assert "after window is incomplete" in summary["explanation"]


@pytest.mark.asyncio
async def test_result_tracking_summary_windows_match_fixture(monkeypatch) -> None:
    service = ResultTrackingService()
    fixture = json.loads((FIXTURE_DIR / "result_summary_windows_ok.json").read_text(encoding="utf-8"))
    snapshots = [
        {"_rows_count": 7, "revenue": 7000.0, "profit": 1000.0, "orders": 70.0},
        {"_rows_count": 7, "revenue": 9000.0, "profit": 1400.0, "orders": 90.0},
        {"_rows_count": 0},
        {"_rows_count": 0},
    ]

    async def _fake_snapshot(*args, **kwargs):
        return snapshots.pop(0)

    monkeypatch.setattr(service, "_finance_window_snapshot", _fake_snapshot)
    event = PortalResultEventRead(
        id="1",
        account_id=1,
        action_id=10,
        nm_id=1001,
        event_type="action_completed",
        outcome="improved",
        before_snapshot={"profit": 100.0},
        after_snapshot={"profit": 125.0},
        comparison=service.compare({"profit": 100.0}, {"profit": 125.0}),
        created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        warnings=["causality_not_claimed"],
    )
    summary = service.effect_summary([event])
    summary["windows"] = await service.finance_window_summaries(
        _FakeSession(),
        account_id=1,
        action_id=10,
        items=[event],
    )

    assert summary["comparison"] == fixture["comparison"]
    assert summary["metrics"]["profit"]["delta"] == fixture["metrics"]["profit"]["delta"]
    assert summary["windows"]["7d"]["status"] == fixture["windows"]["7d"]["status"]
    assert summary["windows"]["7d"]["metrics"]["orders"]["delta"] == fixture["windows"]["7d"]["metrics"]["orders"]["delta"]
    assert summary["windows"]["14d"]["status"] == fixture["windows"]["14d"]["status"]


@pytest.mark.asyncio
async def test_result_tracking_result_center_exposes_finance_windows_and_product_identity(monkeypatch) -> None:
    service = ResultTrackingService()
    session = _FakeSession()
    event = ResultEvent(
        id=1,
        account_id=1,
        action_id=10,
        source_module="result_tracking",
        source_id="10",
        external_id="10",
        nm_id=1001,
        vendor_code="VC-1",
        event_type="action_completed",
        status="done",
        message="Action marked done.",
        created_at=datetime(2026, 5, 20, tzinfo=timezone.utc),
        payload_json={
            "action_id": 10,
            "before_snapshot": {"profit": 100},
            "after_snapshot": {"profit": 125},
            "comparison": service.compare({"profit": 100}, {"profit": 125}),
            "outcome": "improved",
        },
    )
    session.added.append(event)

    async def _fake_identities(*args, **kwargs):
        return {1001: {"nm_id": 1001, "vendor_code": "VC-1", "title": "Test product", "brand": "Brand"}}

    async def _fake_windows(*args, **kwargs):
        return {"7d": {"status": "improved", "metrics": {"profit": {"delta": 400}}}}

    monkeypatch.setattr(service, "_product_identities", _fake_identities)
    monkeypatch.setattr(service, "finance_window_summaries", _fake_windows)

    page = await service.list_results(session, account_id=1, action_id=10)

    assert page.finance_windows["7d"]["status"] == "improved"
    assert page.summary["windows"] == page.finance_windows
    assert page.items[0].product_identity["title"] == "Test product"
    assert page.items[0].calculation_note
    assert page.items[0].confidence == "medium"


@pytest.mark.asyncio
async def test_result_tracking_empty_state_is_stable(monkeypatch) -> None:
    service = ResultTrackingService()
    session = _FakeSession()
    session.added.clear()

    async def _fake_windows(*args, **kwargs):
        return {}

    monkeypatch.setattr(service, "finance_window_summaries", _fake_windows)

    page = await service.list_results(session, account_id=1)

    assert page.status == "ok"
    assert page.total == 0
    assert page.items == []
    assert page.recent_events == []
    assert page.pending_followups == []
    assert set(page.by_module) >= {"action_center", "profit_doctor", "claims", "reputation", "experiments", "checker", "grouping", "stockops"}
    assert page.by_outcome == {
        "improved": 0,
        "worse": 0,
        "neutral": 0,
        "pending": 0,
        "blocked": 0,
        "not_enough_data": 0,
    }
    assert page.summary["comparison"] == "not_enough_data"
    assert page.finance_windows == {}
    assert page.disclaimer == "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."


@pytest.mark.asyncio
async def test_result_tracking_list_results_filters_by_professional_result_status(monkeypatch) -> None:
    service = ResultTrackingService()
    session = _FakeSession()
    session.added.clear()

    async def _fake_windows(*args, **kwargs):
        return {}

    monkeypatch.setattr(service, "finance_window_summaries", _fake_windows)
    session.added.extend(
        [
            ResultEvent(
                id=1,
                account_id=1,
                source_module="problem_engine",
                source_id="56",
                problem_instance_id=56,
                problem_code="low_stock_risk",
                nm_id=1001,
                event_type="recheck_result",
                status="done",
                payload_json={
                    "before_snapshot": {"stock_days_left": 2},
                    "after_snapshot": {"stock_days_left": 8},
                    "comparison": service.compare({"stock_days_left": 2}, {"stock_days_left": 8}, problem_code="low_stock_risk"),
                    "outcome": "improved",
                    "saved_money_claimed": False,
                },
            ),
            ResultEvent(
                id=2,
                account_id=1,
                source_module="problem_engine",
                source_id="57",
                problem_instance_id=57,
                problem_code="low_stock_risk",
                nm_id=1002,
                event_type="action_completed",
                status="done",
                payload_json={
                    "before_snapshot": {"stock_days_left": 2},
                    "after_snapshot": {},
                    "comparison": {"outcome": "not_enough_data", "metrics": {}},
                    "outcome": "not_enough_data",
                    "saved_money_claimed": False,
                },
            ),
        ]
    )

    improved = await service.list_results(session, account_id=1, result_status="improved")
    pending = await service.list_results(session, account_id=1, result_status="pending_data")

    assert improved.total == 1
    assert improved.items[0].problem_instance_id == 56
    assert pending.total == 1
    assert pending.items[0].problem_instance_id == 57
