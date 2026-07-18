from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import BigInteger, create_engine, func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.problem_engine import (
    AdminRuleTestRun,
    MetricCatalog,
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleAdminAudit,
    ProblemRuleVersion,
)
from app.schemas.problem_engine import (
    AdminProblemDefinitionCreate,
    AdminProblemRuleVersionCreate,
    AdminProblemRuleVersionUpdate,
    AdminRuleBacktestRequest,
    AdminRulePublishRequest,
    AdminRuleValidationRequest,
)
from app.services.problem_engine.admin_rules import ProblemRuleAdminService
from app.services.problem_engine.evaluator import ProblemEvaluationPreview, ProblemEvaluationResult
from app.services.problem_engine.metric_catalog import MetricCatalogService


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

    async def get(self, model, key):
        return self._session.get(model, key)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()


class _FakeEvaluator:
    async def evaluate_rule_version(self, _session, **_kwargs) -> ProblemEvaluationResult:
        return ProblemEvaluationResult(
            evaluated_count=2,
            matched_count=1,
            test_mode=True,
            previews=[
                ProblemEvaluationPreview(
                    account_id=1,
                    nm_id=1001,
                    problem_code="overstock_slow_moving",
                    dedup_key="1:overstock_slow_moving:1001",
                    matched=True,
                    action="preview_create",
                    status="new",
                    title="Overstock",
                    explanation="Stock is high.",
                    recommendation="Review stock.",
                    severity="medium",
                    impact_type="blocked_cash",
                    money_impact_amount=Decimal("1200"),
                    trust_state="estimated",
                    evidence_ledger_json={"missing_data": ["cost_price: missing during formula evaluation"]},
                    calculation_snapshot_json={"missing_metrics": ["cost_price"]},
                ),
                ProblemEvaluationPreview(
                    account_id=1,
                    nm_id=1002,
                    problem_code="overstock_slow_moving",
                    dedup_key="1:overstock_slow_moving:1002",
                    matched=False,
                    action="skipped",
                    status="not_created",
                    calculation_snapshot_json={"missing_metrics": []},
                ),
            ],
        )


class _BroadMatchEvaluator:
    async def evaluate_rule_version(self, _session, **_kwargs) -> ProblemEvaluationResult:
        previews: list[ProblemEvaluationPreview] = []
        for index in range(40):
            matched = index < 30
            previews.append(
                ProblemEvaluationPreview(
                    account_id=1,
                    nm_id=2000 + index,
                    problem_code="overstock_slow_moving",
                    dedup_key=f"1:overstock_slow_moving:{2000 + index}",
                    matched=matched,
                    action="preview_create" if matched else "skipped",
                    status="new" if matched else "not_created",
                    title="Overstock",
                    explanation="Stock is high.",
                    recommendation="Review stock.",
                    severity="medium",
                    impact_type="blocked_cash",
                    money_impact_amount=Decimal("100") if matched else None,
                    trust_state="estimated",
                    evidence_ledger_json={},
                    calculation_snapshot_json={"missing_metrics": []},
                ),
            )
        return ProblemEvaluationResult(
            evaluated_count=40,
            matched_count=30,
            test_mode=True,
            previews=previews,
        )


def _create_tables(engine) -> None:
    for table in (
        WBAccount.__table__,
        MetricCatalog.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
        AdminRuleTestRun.__table__,
        ProblemRuleAdminAudit.__table__,
    ):
        table.create(engine)


async def _session() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=1, name="Test account"))
    adapter = _AsyncSessionAdapter(sync_session)
    await MetricCatalogService().seed_initial_metrics(adapter)  # type: ignore[arg-type]
    sync_session.flush()
    return sync_session, adapter


def _definition_payload(problem_code: str = "overstock_slow_moving") -> AdminProblemDefinitionCreate:
    return AdminProblemDefinitionCreate(
        problem_code=problem_code,
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Overstock {nm_id}",
        description_template="Stock is {stock_qty}.",
        recommendation_template="Review stock.",
        impact_type_default="blocked_cash",
        trust_state_default="estimated",
        severity_default="medium",
        allowed_actions_json=["run_checker", "recheck", "dismiss"],
    )


def _solve_map_template(action_code: str = "run_checker") -> dict[str, Any]:
    return {
        "title": "Карта решения: тестовое правило",
        "summary": "Показываем доказательства, открываем рабочий экран и запускаем перепроверку.",
        "steps": [
            {
                "step_id": "evidence",
                "order": 1,
                "title": "Проверить доказательства",
                "description": "Проверьте формулу, факты и источники.",
                "status": "ready",
                "action_code": None,
                "target_href": None,
                "required_metrics": ["stock_qty"],
                "blocking_reason": None,
                "completion_signal": "Доказательства понятны.",
            },
            {
                "step_id": "workbench",
                "order": 2,
                "title": "Открыть рабочий экран",
                "description": "Перейдите в экран, где можно исправить проблему.",
                "status": "available",
                "action_code": action_code,
                "target_href": None,
                "required_metrics": ["stock_qty"],
                "blocking_reason": None,
                "completion_signal": "Рабочий экран открыт.",
            },
            {
                "step_id": "recheck",
                "order": 3,
                "title": "Перепроверить",
                "description": "Запустите повторную проверку после действия.",
                "status": "available",
                "action_code": "recheck",
                "target_href": None,
                "required_metrics": ["stock_qty"],
                "blocking_reason": None,
                "completion_signal": "Правило пересчитано.",
            },
        ],
    }


def _price_definition_payload(problem_code: str = "unsafe_price_rule") -> AdminProblemDefinitionCreate:
    return AdminProblemDefinitionCreate(
        problem_code=problem_code,
        source_module="problem_engine",
        category="price",
        entity_type="product",
        title_template="Unsafe price {nm_id}",
        description_template="Price action needs margin evidence.",
        recommendation_template="Review price only with margin evidence.",
        impact_type_default="system_warning",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=["review_price", "safe_promo", "create_task", "recheck"],
    )


def _version_payload(
    condition_json: dict[str, Any] | None = None,
    *,
    solve_action: str = "run_checker",
    evidence_template_json: dict[str, Any] | None = None,
) -> AdminProblemRuleVersionCreate:
    return AdminProblemRuleVersionCreate(
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json=condition_json or {">": [{"metric": "stock_qty"}, 50]},
        impact_formula_json={"metric": "stock_qty"},
        severity_formula_json="medium",
        confidence_formula_json="estimated",
        dedup_key_template="{account_id}:{problem_code}:{nm_id}",
        recheck_rule_json={"human": "Refresh metrics and rerun.", "resolved_when": {"<=": [{"metric": "stock_qty"}, 50]}},
        evidence_template_json=evidence_template_json or {
            "formula_human": "stock_qty > 50",
            "recheck_rule_human": "Refresh metrics and rerun.",
            "selected_input_metrics": ["stock_qty"],
            "solve_map_template": _solve_map_template(solve_action),
        },
    )


def _problem_instance(
    *,
    definition: ProblemDefinition,
    rule: ProblemRuleVersion,
    account_id: int = 1,
    nm_id: int = 1001,
    status: str = "new",
    last_seen_at: datetime | None = None,
) -> ProblemInstance:
    seen_at = last_seen_at or datetime(2026, 7, 6, tzinfo=timezone.utc)
    return ProblemInstance(
        account_id=account_id,
        problem_code=definition.problem_code,
        problem_definition_id=definition.id,
        rule_version_id=rule.id,
        source_module=definition.source_module,
        entity_type=definition.entity_type,
        entity_id=str(nm_id),
        nm_id=nm_id,
        vendor_code=f"SKU-{nm_id}",
        dedup_key=f"{account_id}:{definition.problem_code}:{nm_id}",
        title=f"Problem {nm_id}",
        explanation="Generated problem",
        recommendation="Review",
        severity=definition.severity_default,
        status=status,
        impact_type=definition.impact_type_default,
        money_impact_amount=Decimal("100"),
        money_impact_currency="RUB",
        trust_state=definition.trust_state_default,
        confidence="estimated",
        evidence_ledger_json={"formula_human": "stock_qty > 50"},
        calculation_snapshot_json={"metrics": {"stock_qty": 80}},
        first_seen_at=seen_at,
        last_seen_at=seen_at,
        resolved_at=None,
        dismissed_at=seen_at if status == "dismissed" else None,
        dismiss_reason="false positive" if status == "dismissed" else None,
    )


@pytest.mark.asyncio
async def test_admin_rule_service_rejects_unsafe_formula_on_create_version() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("unsafe_formula_test"), actor_user_id=1)  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as exc:
            await service.create_version(
                session,  # type: ignore[arg-type]
                definition.id,
                _version_payload(condition_json={"__import__": ["os"]}),
                actor_user_id=1,
            )

        with pytest.raises(HTTPException) as sql_exc:
            await service.create_version(
                session,  # type: ignore[arg-type]
                definition.id,
                _version_payload(condition_json={"==": ["SELECT * FROM problem_instances", "x"]}),
                actor_user_id=1,
            )

        rule_count = sync_session.execute(select(func.count(ProblemRuleVersion.id))).scalar_one()

    assert exc.value.status_code == 422
    assert "unknown operator" in str(exc.value.detail)
    assert sql_exc.value.status_code == 422
    assert "unsafe formula literal" in str(sql_exc.value.detail)
    assert rule_count == 0


@pytest.mark.asyncio
async def test_admin_rule_validation_reports_unknown_metrics_without_saving() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("unknown_metric_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]

        result = await service.validate_version(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleValidationRequest(condition_json={">": [{"metric": "not_in_catalog"}, 0]}),
        )

    assert result.valid is False
    assert result.formula_results["condition"].error == "unknown metric: not_in_catalog"


@pytest.mark.asyncio
async def test_publish_distinguishes_unknown_metric_or_operator_from_invalid_formula() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("publish_formula_key_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]

        rule.condition_json = {">": [{"metric": "not_in_catalog"}, 0]}
        sync_session.flush()
        with pytest.raises(HTTPException) as unknown_exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

        rule.condition_json = {"and": []}
        sync_session.flush()
        with pytest.raises(HTTPException) as invalid_exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert unknown_exc.value.detail["blockers"][0]["key"] == "unknown_metric_or_operator"
    assert invalid_exc.value.detail["blockers"][0]["key"] == "invalid_formula"


@pytest.mark.asyncio
async def test_publish_requires_backtest_and_writes_audit() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("publish_gate_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(
            session,
            definition.id,
            _version_payload(),
            actor_user_id=1,
        )  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as override_exc:
            await service.publish(
                session,  # type: ignore[arg-type]
                rule.id,
                AdminRulePublishRequest(override=True, override_reason="manual smoke test"),
                actor_user_id=1,
            )

        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(
                account_id=1,
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
            ),
            actor_user_id=1,
        )
        published = await service.publish(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRulePublishRequest(),
            actor_user_id=1,
        )
        audit_events = list(sync_session.execute(select(ProblemRuleAdminAudit.event_type)).scalars())
        sync_session.refresh(definition)

    assert exc.value.status_code == 409
    assert exc.value.detail["blocker_keys"] == ["no_backtest"]
    assert "no_backtest" in exc.value.detail["known_blocker_keys"]
    assert exc.value.detail["blockers"][0]["key"] == "no_backtest"
    assert override_exc.value.status_code == 409
    assert published.status == "active"
    assert published.published_by_user_id == 1
    assert definition.status == "active"
    assert "published" in audit_events


@pytest.mark.asyncio
async def test_active_rule_edit_creates_new_draft_version_without_mutating_active() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("active_edit_draft_test"), actor_user_id=1)  # type: ignore[arg-type]
        active_rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            active_rule.id,
            AdminRuleBacktestRequest(account_id=1, date_from=date(2026, 6, 7), date_to=date(2026, 7, 6)),
            actor_user_id=1,
        )
        await service.publish(session, active_rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

        draft = await service.update_version(
            session,  # type: ignore[arg-type]
            active_rule.id,
            AdminProblemRuleVersionUpdate(condition_json={">": [{"metric": "stock_qty"}, 80]}),
            actor_user_id=7,
        )
        sync_session.refresh(active_rule)
        audit_events = list(sync_session.execute(select(ProblemRuleAdminAudit.event_type)).scalars())

    assert active_rule.status == "active"
    assert active_rule.condition_json == {">": [{"metric": "stock_qty"}, 50]}
    assert draft.id != active_rule.id
    assert draft.status == "draft"
    assert draft.version == 2
    assert draft.condition_json == {">": [{"metric": "stock_qty"}, 80]}
    assert draft.created_by_user_id == 7
    assert "active_edit_created_draft" in audit_events
    assert "created_from_active_edit" in audit_events


@pytest.mark.asyncio
async def test_publish_archives_previous_active_version() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("replace_active_test"), actor_user_id=1)  # type: ignore[arg-type]
        first = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            first.id,
            AdminRuleBacktestRequest(account_id=1, date_from=date(2026, 6, 7), date_to=date(2026, 7, 6)),
            actor_user_id=1,
        )
        await service.publish(session, first.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]
        second = await service.create_version(
            session,
            definition.id,
            _version_payload(condition_json={">": [{"metric": "stock_qty"}, 60]}),
            actor_user_id=2,
        )  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            second.id,
            AdminRuleBacktestRequest(account_id=1, date_from=date(2026, 6, 7), date_to=date(2026, 7, 6)),
            actor_user_id=2,
        )

        published = await service.publish(session, second.id, AdminRulePublishRequest(), actor_user_id=2)  # type: ignore[arg-type]
        sync_session.refresh(first)

    assert published.status == "active"
    assert first.status == "archived"


@pytest.mark.asyncio
async def test_admin_rule_audit_history_can_be_listed() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("audit_history_test"), actor_user_id=9)  # type: ignore[arg-type]

        page = await service.list_audit(
            session,  # type: ignore[arg-type]
            object_type="definition",
            object_id=definition.id,
            limit=10,
            offset=0,
        )

    assert page.total == 1
    assert page.items[0].event_type == "created"
    assert page.items[0].actor_user_id == 9


@pytest.mark.asyncio
async def test_publish_blocks_rule_without_solve_map_template() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("missing_solve_map_gate"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(
            session,
            definition.id,
            _version_payload(
                evidence_template_json={
                    "formula_human": "stock_qty > 50",
                    "recheck_rule_human": "Refresh metrics and rerun.",
                    "selected_input_metrics": ["stock_qty"],
                },
            ),
            actor_user_id=1,
        )  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(
                account_id=1,
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
            ),
            actor_user_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert "solve_map_template" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_publish_blocks_rule_without_evidence_fields() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("missing_evidence_gate"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(
            session,
            definition.id,
            _version_payload(
                evidence_template_json={
                    "solve_map_template": _solve_map_template(),
                },
            ),
            actor_user_id=1,
        )  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert "evidence_template_json.formula_human" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_backtest_returns_sample_total_missing_stats_and_audit() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("backtest_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(
            session,
            definition.id,
            _version_payload(),
            actor_user_id=1,
        )  # type: ignore[arg-type]

        result = await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(
                account_id=1,
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
                sample_limit=10,
            ),
            actor_user_id=1,
        )
        run_count = sync_session.execute(select(func.count(AdminRuleTestRun.id))).scalar_one()
        seller_issue_count = sync_session.execute(select(func.count(ProblemInstance.id))).scalar_one()
        audit_events = list(sync_session.execute(select(ProblemRuleAdminAudit.event_type)).scalars())

    assert result.matched_count == 1
    assert result.evaluated_count == 2
    assert result.total_impact_amount == Decimal("1200")
    assert result.total_expected_impact["amount"] == "1200"
    assert result.total_expected_impact["by_trust_state"] == {"estimated": "1200"}
    assert result.total_expected_impact["by_impact_type"] == {"blocked_cash": "1200"}
    assert result.total_expected_impact["claim"] == "expected_impact_not_saved_money"
    assert result.sample_issues[0]["nm_id"] == 1001
    assert result.sample_evidence[0]["nm_id"] == 1001
    assert result.sample_evidence[0]["evidence_ledger"]["missing_data"] == ["cost_price: missing during formula evaluation"]
    assert result.seller_preview_payload["problem_code"] == "backtest_test"
    assert result.seller_preview_payload["sample_actions"][0]["nm_id"] == 1001
    assert {
        "action_center_preview",
        "product360_preview",
        "data_fix_preview",
        "money_preview",
        "results_preview",
    }.issubset(result.seller_preview_payload)
    assert result.missing_metric_stats["cost_price"] >= 1
    assert run_count == 1
    assert seller_issue_count == 0
    assert "backtested" in audit_events


@pytest.mark.asyncio
async def test_backtest_history_returns_saved_runs_with_seller_preview_payload() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("backtest_history_runs"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(account_id=1, date_from=date(2026, 6, 7), date_to=date(2026, 7, 6)),
            actor_user_id=1,
        )

        page = await service.list_backtests(
            session,  # type: ignore[arg-type]
            definition_id=definition.id,
            limit=10,
            offset=0,
        )
        version_page = await service.list_backtests_for_version(
            session,  # type: ignore[arg-type]
            version_id=rule.id,
            limit=10,
            offset=0,
        )

    assert page.total == 1
    assert page.items[0].rule_version_id == rule.id
    assert page.items[0].run_id == page.items[0].id
    assert page.items[0].status == "completed"
    assert page.items[0].started_at == page.items[0].created_at
    assert page.items[0].finished_at == page.items[0].created_at
    assert page.items[0].matched_count == 1
    assert page.items[0].evaluated_count == 2
    assert page.items[0].seller_preview_payload["action_center_preview"]["items"][0]["nm_id"] == 1001
    assert page.items[0].sample_evidence[0]["nm_id"] == 1001
    assert version_page.total == 1
    assert version_page.items[0].run_id == page.items[0].run_id


@pytest.mark.asyncio
async def test_generated_problem_instances_filter_by_status_date_and_account() -> None:
    sync_session, session = await _session()
    with sync_session:
        sync_session.add(WBAccount(id=2, name="Second account"))
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("instance_filter_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]
        sync_session.add_all(
            [
                _problem_instance(
                    definition=definition,
                    rule=rule,
                    account_id=1,
                    nm_id=1001,
                    status="new",
                    last_seen_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
                ),
                _problem_instance(
                    definition=definition,
                    rule=rule,
                    account_id=1,
                    nm_id=1002,
                    status="dismissed",
                    last_seen_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                ),
                _problem_instance(
                    definition=definition,
                    rule=rule,
                    account_id=2,
                    nm_id=1003,
                    status="new",
                    last_seen_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
                ),
            ]
        )
        sync_session.flush()

        page = await service.list_instances(
            session,  # type: ignore[arg-type]
            definition_id=definition.id,
            status_filter="new",
            account_id=1,
            date_from=date(2026, 7, 5),
            date_to=date(2026, 7, 7),
            problem_code=definition.problem_code,
            limit=10,
            offset=0,
        )
        empty = await service.list_instances(
            session,  # type: ignore[arg-type]
            definition_id=definition.id,
            problem_code="different_problem_code",
            limit=10,
            offset=0,
        )

    assert page.total == 1
    assert page.items[0].account_id == 1
    assert page.items[0].status == "new"
    assert page.items[0].nm_id == 1001
    assert page.items[0].problem_instance_id == page.items[0].id
    assert page.items[0].problem_code == "instance_filter_test"
    assert empty.total == 0


@pytest.mark.asyncio
async def test_dismissed_rate_is_computed_from_problem_instance_history() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("dismiss_rate_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]
        kept = _problem_instance(definition=definition, rule=rule, nm_id=1001, status="new")
        dismissed = _problem_instance(definition=definition, rule=rule, nm_id=1002, status="dismissed")
        resolved = _problem_instance(definition=definition, rule=rule, nm_id=1003, status="resolved")
        resolved.resolved_at = datetime(2026, 7, 6, tzinfo=timezone.utc)
        sync_session.add_all([kept, dismissed, resolved])
        sync_session.flush()
        sync_session.add(
            ProblemInstanceHistory(
                problem_instance_id=dismissed.id,
                event_type="dismissed",
                old_value_json={"status": "new"},
                new_value_json={"status": "dismissed"},
                comment="not relevant",
                actor_user_id=1,
            )
        )
        sync_session.flush()

        instances = await service.list_instances(session, definition_id=definition.id, limit=10, offset=0)  # type: ignore[arg-type]
        detail = await service.get_definition(session, definition.id)  # type: ignore[arg-type]
        summary = await service.summary(session, recent_days=3650)  # type: ignore[arg-type]

    assert instances.dismissed_count == 1
    assert instances.resolved_count == 1
    assert instances.active_count == 1
    assert instances.dismissed_rate == 0.3333
    assert instances.false_positive_rate == 0.3333
    assert detail.total_instances == 3
    assert detail.dismissed_count == 1
    assert detail.resolved_count == 1
    assert detail.active_count == 1
    assert detail.dismissed_rate == 0.3333
    assert detail.false_positive_rate == 0.3333
    assert detail.versions[0].dismissed_count == 1
    assert detail.versions[0].resolved_count == 1
    assert detail.versions[0].dismissed_rate == 0.3333
    assert summary.dismissed_rate == 0.3333
    assert summary.total_instances == 3
    assert summary.resolved_count == 1
    assert summary.active_count == 1
    assert summary.recent_created_instances == 3
    assert summary.recent_resolved_instances == 1
    assert summary.recent_dismissed_instances == 1
    assert summary.definitions[0].recent_matches_count == 3
    assert summary.definitions[0].recent_created_instances == 3
    assert summary.definitions[0].recent_resolved_instances == 1
    assert summary.definitions[0].recent_dismissed_instances == 1


@pytest.mark.asyncio
async def test_version_compare_returns_disabled_capability() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        definition = await service.create_definition(session, _definition_payload("compare_capability_test"), actor_user_id=1)  # type: ignore[arg-type]

        response = await service.compare_versions_capability(
            session,  # type: ignore[arg-type]
            definition_id=definition.id,
            left=1,
            right=2,
        )

    assert response.compare_available is False
    assert response.disabled_reason == "Сравнение версий будет доступно позже."
    assert response.left == 1
    assert response.right == 2


@pytest.mark.asyncio
async def test_dangerous_action_catalog_marks_external_unsafe_actions() -> None:
    service = ProblemRuleAdminService()

    catalog = await service.action_catalog()
    by_code = {item.action_code: item for item in catalog.items}

    assert by_code["send_to_wb"].is_external_write is True
    assert by_code["send_to_wb"].is_dangerous is True
    assert by_code["send_to_wb"].requires_preview is True
    assert by_code["send_to_wb"].requires_confirm is True
    assert by_code["send_to_wb"].requires_permission is True
    assert by_code["send_to_wb"].requires_audit is True
    assert by_code["send_to_wb"].allowed_in_rule_builder is False
    assert by_code["send_to_wb"].allowed_for_rule_builder is False
    assert by_code["pause_ads"].is_external_write is True
    assert by_code["pause_ads"].is_dangerous is True
    assert by_code["pause_ads"].requires_confirm is True
    assert by_code["pause_ads"].requires_audit is True
    assert by_code["pause_ads"].allowed_in_rule_builder is False
    assert by_code["pause_ads"].allowed_for_rule_builder is False
    assert by_code["pause_ads"].disabled_reason
    assert by_code["update_price"].is_dangerous is True
    assert by_code["update_price"].allowed_in_rule_builder is False
    assert by_code["open_price_review"].is_navigation_only is True
    assert by_code["open_price_review"].allowed_in_rule_builder is True
    assert by_code["open_data_fix"].allowed_in_rule_builder is True
    assert by_code["classify_expense"].module == "data_fix"
    assert by_code["classify_expense"].is_local_only is True
    assert by_code["classify_expense"].is_external_write is False
    assert by_code["run_checker"].allowed_for_rule_builder is True
    assert by_code["run_checker"].is_dangerous is False


@pytest.mark.asyncio
async def test_publish_blocks_unsafe_price_action_without_margin_or_cost_metrics() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _price_definition_payload(), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(
            session,
            definition.id,
            _version_payload(solve_action="open_price_review"),
            actor_user_id=1,
        )  # type: ignore[arg-type]

        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(
                account_id=1,
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
            ),
            actor_user_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert "margin/cost" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_publish_blocks_wide_match_without_override_reason() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_BroadMatchEvaluator())  # type: ignore[arg-type]
        definition = await service.create_definition(session, _definition_payload("broad_match_test"), actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]

        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(
                account_id=1,
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
            ),
            actor_user_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as missing_reason_exc:
            await service.publish(
                session,  # type: ignore[arg-type]
                rule.id,
                AdminRulePublishRequest(override=True),
                actor_user_id=1,
            )

        published = await service.publish(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRulePublishRequest(
                override=True,
                override_reason="Широкое правило запускаем как общий аудит остатков.",
            ),
            actor_user_id=1,
        )

    assert exc.value.status_code == 409
    assert "too many products" in str(exc.value.detail)
    assert missing_reason_exc.value.status_code == 422
    assert published.status == "active"


@pytest.mark.asyncio
async def test_publish_blocks_test_only_rules_for_seller_visibility() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        payload = _definition_payload("test_only_publish_gate")
        payload.trust_state_default = "test_only"
        definition = await service.create_definition(session, payload, actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]

        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(
                account_id=1,
                date_from=date(2026, 6, 7),
                date_to=date(2026, 7, 6),
            ),
            actor_user_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert "test_only" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_publish_blocks_explicit_test_only_seller_visibility_conflict() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        payload = _definition_payload("explicit_test_only_visibility_gate")
        payload.test_only = True
        payload.seller_visible = True
        payload.visibility_mode = "seller"
        definition = await service.create_definition(session, payload, actor_user_id=1)  # type: ignore[arg-type]
        version_payload = _version_payload()
        version_payload.test_only = True
        version_payload.seller_visible = True
        version_payload.visibility_mode = "seller"
        rule = await service.create_version(session, definition.id, version_payload, actor_user_id=1)  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(account_id=1, date_from=date(2026, 6, 7), date_to=date(2026, 7, 6)),
            actor_user_id=1,
        )
        detail = await service.get_definition(session, definition.id)  # type: ignore[arg-type]

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert detail.test_only is True
    assert detail.seller_visible is True
    assert detail.visibility_mode == "seller"
    assert detail.versions[0].test_only is True
    assert detail.versions[0].seller_visible is True
    assert detail.versions[0].visibility_mode == "seller"
    assert exc.value.status_code == 422
    assert exc.value.detail["blockers"][0]["key"] == "test_only_visibility_conflict"


@pytest.mark.asyncio
async def test_publish_blocks_seller_visible_rule_without_recheck_action() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        payload = _definition_payload("missing_recheck_action_gate")
        payload.allowed_actions_json = ["run_checker", "dismiss"]
        definition = await service.create_definition(session, payload, actor_user_id=1)  # type: ignore[arg-type]
        rule = await service.create_version(session, definition.id, _version_payload(), actor_user_id=1)  # type: ignore[arg-type]
        await service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(account_id=1, date_from=date(2026, 6, 7), date_to=date(2026, 7, 6)),
            actor_user_id=1,
        )

        with pytest.raises(HTTPException) as exc:
            await service.publish(session, rule.id, AdminRulePublishRequest(), actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert exc.value.detail["blockers"][0]["key"] == "no_recheck_rule"


@pytest.mark.asyncio
async def test_rule_builder_blocks_dangerous_direct_action() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService(evaluator=_FakeEvaluator())  # type: ignore[arg-type]
        payload = _definition_payload("dangerous_action_gate")
        payload.allowed_actions_json = ["pause_ads", "run_checker", "recheck"]

        with pytest.raises(HTTPException) as exc:
            await service.create_definition(session, payload, actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert exc.value.detail["blocker_key"] == "dangerous_action"
    assert exc.value.detail["dangerous_actions"] == ["pause_ads"]


@pytest.mark.asyncio
async def test_rule_builder_blocks_unknown_action() -> None:
    sync_session, session = await _session()
    with sync_session:
        service = ProblemRuleAdminService()
        payload = _definition_payload("unknown_action_gate")
        payload.allowed_actions_json = ["open_data_fix", "totally_unknown_action"]

        with pytest.raises(HTTPException) as exc:
            await service.create_definition(session, payload, actor_user_id=1)  # type: ignore[arg-type]

    assert exc.value.status_code == 422
    assert exc.value.detail["invalid_actions"] == ["totally_unknown_action"]
