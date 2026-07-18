from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import BigInteger, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.operator import ResultEvent
from app.models.problem_engine import (
    ProblemDefinition,
    ProblemEvaluationRunLog,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleVersion,
)
from app.schemas.problem_engine import MetricSourceReference, ProductMetricResolution, ResolvedMetricValue
from app.services.problem_engine import ProblemEvaluatorService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService


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

    async def get(self, model, identity):
        return self._session.get(model, identity)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()

    async def refresh(self, instance) -> None:
        self._session.refresh(instance)


class _FakeMetricCatalog:
    async def allowed_metric_codes(self, _session) -> set[str]:
        return {"stock_qty"}


class _FakeMetricResolver:
    def __init__(self, values_by_nm: dict[int, dict[str, Any]]) -> None:
        self.values_by_nm = values_by_nm
        self.calls: list[int] = []

    async def resolve_product_metrics(
        self,
        _session,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
        metric_codes: list[str] | set[str] | tuple[str, ...] | None = None,
    ) -> ProductMetricResolution:
        self.calls.append(nm_id)
        values = self.values_by_nm.get(nm_id, {})
        resolution = ProductMetricResolution(account_id=account_id, nm_id=nm_id, date_from=date_from, date_to=date_to)
        for code in metric_codes or []:
            missing = code not in values
            resolution.metrics[code] = ResolvedMetricValue(
                metric_code=code,
                value=None if missing else values[code],
                value_type="count",
                unit="pcs",
                trust_state="blocked" if missing else "confirmed",
                is_missing=missing,
                missing_reason="source_data_missing" if missing else None,
                evidence=MetricSourceReference(
                    source_module="test",
                    source_table="test_metric_source",
                    source_endpoint="GET /test/source",
                    date_from=date_from,
                    date_to=date_to,
                    row_count=0 if missing else 1,
                    filters={"account_id": account_id, "nm_id": nm_id},
                ),
            )
            if missing:
                resolution.missing_metrics.append(code)
        return resolution


def _create_tables(engine) -> None:
    for table in (
        WBAccount.__table__,
        MartSKUDaily.__table__,
        MartStockDaily.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
        ProblemEvaluationRunLog.__table__,
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


def _add_rule(
    sync_session: Session,
    *,
    recheck_rule_json: dict[str, Any] | None = None,
) -> tuple[ProblemDefinition, ProblemRuleVersion]:
    definition = ProblemDefinition(
        problem_code="overstock_slow_moving",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Problem for {nm_id}",
        description_template="Stock is {stock_qty}",
        recommendation_template="Review stock",
        impact_type_default="blocked_cash",
        trust_state_default="confirmed",
        severity_default="medium",
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
        condition_json={">": [{"metric": "stock_qty"}, 50]},
        impact_formula_json={"*": [{"metric": "stock_qty"}, 10]},
        severity_formula_json="medium",
        confidence_formula_json="confirmed",
        dedup_key_template="{account_id}:{problem_code}:{nm_id}",
        recheck_rule_json=recheck_rule_json or {"human": "Refresh metrics and run again."},
        evidence_template_json={"formula_human": "stock_qty > 50", "money_currency": "RUB"},
    )
    sync_session.add(rule)
    sync_session.flush()
    return definition, rule


def _runner(resolver: _FakeMetricResolver) -> ProblemEvaluationRunnerService:
    evaluator = ProblemEvaluatorService(metric_resolver=resolver, metric_catalog=_FakeMetricCatalog())
    return ProblemEvaluationRunnerService(evaluator=evaluator)


def _problem_count(sync_session: Session) -> int:
    return sync_session.execute(select(func.count(ProblemInstance.id))).scalar_one()


@pytest.mark.asyncio
async def test_runner_is_idempotent_for_changed_products() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session)
        runner = _runner(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}}))

        first = await runner.evaluate_products(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_ids=[1001],
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            trigger="sync_stocks",
        )
        runner.evaluator.metric_resolver = _FakeMetricResolver({1001: {"stock_qty": Decimal("80")}})  # type: ignore[assignment]
        second = await runner.evaluate_products(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_ids=[1001],
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            trigger="sync_stocks",
        )
        count = _problem_count(sync_session)
        log_count = sync_session.execute(select(func.count(ProblemEvaluationRunLog.id))).scalar_one()

    assert count == 1
    assert log_count == 2
    assert first.status == "completed"
    assert first.issues_created == 1
    assert first.entities_evaluated == 1
    assert second.status == "completed"
    assert second.issues_updated == 1
    assert second.issues_created == 0


@pytest.mark.asyncio
async def test_recheck_resolves_problem_instance_and_records_history() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(
            sync_session,
            recheck_rule_json={
                "human": "Close when stock is back under threshold.",
                "resolved_when": {"<=": [{"metric": "stock_qty"}, 50]},
            },
        )
        runner = _runner(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}}))
        await runner.evaluate_products(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_ids=[1001],
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            trigger="sync_stocks",
        )
        instance = sync_session.execute(select(ProblemInstance)).scalar_one()

        runner.evaluator.metric_resolver = _FakeMetricResolver({1001: {"stock_qty": Decimal("10")}})  # type: ignore[assignment]
        log, refreshed = await runner.recheck_problem_instance(
            session,  # type: ignore[arg-type]
            problem_instance_id=instance.id,
            actor_user_id=7,
        )
        history_events = list(sync_session.execute(select(ProblemInstanceHistory.event_type)).scalars())
        result_events = list(sync_session.execute(select(ResultEvent).order_by(ResultEvent.id)).scalars())

    assert log.status == "completed"
    assert log.issues_resolved == 1
    assert refreshed.status == "resolved"
    assert "recheck_completed" in history_events
    problem_result_events = [event for event in result_events if event.source_module == "problem_engine"]
    notification_events = [event for event in result_events if event.source_module == "action_center_notifications"]
    assert [event.event_type for event in problem_result_events] == ["before_snapshot", "recheck_result", "action_completed"]
    assert problem_result_events[-1].problem_instance_id == instance.id
    assert problem_result_events[-1].problem_code == "overstock_slow_moving"
    assert problem_result_events[-1].status == "resolved"
    assert problem_result_events[-1].payload_json["saved_money_claimed"] is False
    assert any(
        event.payload_json["notification_type"] == "recheck_completed"
        for event in notification_events
    )


def test_extract_nm_ids_from_sync_details_is_conservative() -> None:
    details = {
        "rows_loaded": 12,
        "changedNmIds": ["1001", 1002],
        "items": [{"nm_id": 1003}, {"row_count": 9}],
        "nested": {"updated_nm_ids": [1002, "bad", None]},
    }

    assert ProblemEvaluationRunnerService.extract_nm_ids(details) == [1001, 1002, 1003]
