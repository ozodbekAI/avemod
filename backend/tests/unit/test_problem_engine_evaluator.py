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
from app.models.problem_engine import ProblemDefinition, ProblemInstance, ProblemInstanceHistory, ProblemRuleVersion
from app.schemas.problem_engine import MetricSourceReference, ProductMetricResolution, ResolvedMetricValue
from app.services.problem_engine import ProblemEvaluatorService


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

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()


class _FakeMetricCatalog:
    def __init__(self, allowed: set[str] | None = None) -> None:
        self.allowed = allowed or {
            "stock_qty",
            "unit_profit",
            "cost_price",
            "days_of_stock",
        }

    async def allowed_metric_codes(self, _session) -> set[str]:
        return set(self.allowed)


class _FakeMetricResolver:
    def __init__(self, values_by_nm: dict[int, dict[str, Any]], missing_by_nm: dict[int, set[str]] | None = None) -> None:
        self.values_by_nm = values_by_nm
        self.missing_by_nm = missing_by_nm or {}
        self.calls: list[tuple[int, tuple[str, ...]]] = []

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
        codes = list(metric_codes or [])
        self.calls.append((nm_id, tuple(codes)))
        values = self.values_by_nm.get(nm_id, {})
        missing = self.missing_by_nm.get(nm_id, set())
        resolution = ProductMetricResolution(account_id=account_id, nm_id=nm_id, date_from=date_from, date_to=date_to)
        for code in codes:
            is_missing = code in missing or code not in values or values.get(code) is None
            resolution.metrics[code] = ResolvedMetricValue(
                metric_code=code,
                value=None if is_missing else values[code],
                value_type="money" if code in {"unit_profit", "cost_price"} else "count",
                unit="RUB" if code in {"unit_profit", "cost_price"} else "pcs",
                trust_state="blocked" if is_missing else "confirmed",
                is_missing=is_missing,
                missing_reason="source_data_missing" if is_missing else None,
                evidence=MetricSourceReference(
                    source_module="test",
                    source_table="test_metric_source",
                    source_endpoint="GET /test/source",
                    date_from=date_from,
                    date_to=date_to,
                    row_count=0 if is_missing else 1,
                    filters={"account_id": account_id, "nm_id": nm_id},
                ),
            )
            if is_missing:
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
    condition_json: dict[str, Any],
    problem_code: str = "overstock_slow_moving",
    title_template: str = "Problem {problem_code} for {nm_id}",
    description_template: str = "Stock is {stock_qty}; impact {impact_amount}",
    recommendation_template: str = "Review {vendor_code}",
    impact_type_default: str = "blocked_cash",
    trust_state_default: str = "confirmed",
    severity_default: str = "medium",
    impact_formula_json: dict[str, Any] | None = None,
    severity_formula_json: dict[str, Any] | None = None,
    confidence_formula_json: dict[str, Any] | None = None,
    recheck_rule_json: dict[str, Any] | None = None,
    evidence_template_json: dict[str, Any] | None = None,
) -> tuple[ProblemDefinition, ProblemRuleVersion]:
    definition = ProblemDefinition(
        problem_code=problem_code,
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template=title_template,
        description_template=description_template,
        recommendation_template=recommendation_template,
        impact_type_default=impact_type_default,
        trust_state_default=trust_state_default,
        severity_default=severity_default,
        allowed_actions_json=["review"],
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
        condition_json=condition_json,
        impact_formula_json=impact_formula_json or {"*": [{"metric": "stock_qty"}, 10]},
        severity_formula_json=severity_formula_json or {"case": [{ "if": {">": [{"metric": "stock_qty"}, 100]}, "then": "high" }, {"else": "medium"}]},
        confidence_formula_json=confidence_formula_json or "confirmed",
        dedup_key_template="{account_id}:{problem_code}:{nm_id}",
        recheck_rule_json=recheck_rule_json or {"human": "Refresh metrics and run the rule again."},
        evidence_template_json=evidence_template_json or {"formula_human": "stock_qty > threshold", "money_currency": "RUB"},
    )
    sync_session.add(rule)
    sync_session.flush()
    return definition, rule


def _service(resolver: _FakeMetricResolver) -> ProblemEvaluatorService:
    return ProblemEvaluatorService(metric_resolver=resolver, metric_catalog=_FakeMetricCatalog())


def _problem_count(sync_session: Session) -> int:
    return sync_session.execute(select(func.count(ProblemInstance.id))).scalar_one()


def _problem(sync_session: Session) -> ProblemInstance:
    return sync_session.execute(select(ProblemInstance)).scalar_one()


@pytest.mark.asyncio
async def test_condition_true_creates_problem_instance_with_evidence() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session, condition_json={">": [{"metric": "stock_qty"}, 50]})
        result = await _service(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}})).evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )

        instance = _problem(sync_session)

    assert result.created_count == 1
    assert instance.dedup_key == "1:overstock_slow_moving:1001"
    assert instance.title == "Problem overstock_slow_moving for 1001"
    assert instance.money_impact_amount == Decimal("600.0000")
    assert instance.evidence_ledger_json["formula_code"] == "overstock_slow_moving.v1"
    assert instance.evidence_ledger_json["input_facts"][0]["metric_code"] == "stock_qty"
    assert instance.evidence_ledger_json["source_references"]


@pytest.mark.asyncio
async def test_condition_false_creates_no_problem_instance() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session, condition_json={">": [{"metric": "stock_qty"}, 50]})
        result = await _service(_FakeMetricResolver({1001: {"stock_qty": Decimal("10")}})).evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        count = _problem_count(sync_session)

    assert result.created_count == 0
    assert result.skipped_count == 1
    assert count == 0


@pytest.mark.asyncio
async def test_repeated_run_deduplicates_existing_problem_instance() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session, condition_json={">": [{"metric": "stock_qty"}, 50]})
        service = _service(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}}))

        first = await service.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        service.metric_resolver = _FakeMetricResolver({1001: {"stock_qty": Decimal("80")}})  # type: ignore[assignment]
        second = await service.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        count = _problem_count(sync_session)
        instance = _problem(sync_session)

    assert first.created_count == 1
    assert second.updated_count == 1
    assert count == 1
    assert instance.calculation_snapshot_json["metrics"]["stock_qty"]["value"] == 80


@pytest.mark.asyncio
async def test_rerun_preserves_user_lifecycle_status() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session, condition_json={">": [{"metric": "stock_qty"}, 50]})
        service = _service(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}}))
        await service.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        instance = _problem(sync_session)
        instance.status = "ignored"
        sync_session.flush()

        result = await service.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )

    assert result.previews[0].action == "preserved"
    assert instance.status == "ignored"
    assert instance.evidence_ledger_json["input_facts"][0]["metric_code"] == "stock_qty"


@pytest.mark.asyncio
async def test_resolved_when_closes_existing_problem_instance() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(
            sync_session,
            condition_json={">": [{"metric": "stock_qty"}, 50]},
            recheck_rule_json={
                "human": "Close when stock is back under threshold.",
                "resolved_when": {"<=": [{"metric": "stock_qty"}, 50]},
            },
        )
        service = _service(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}}))
        await service.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        service.metric_resolver = _FakeMetricResolver({1001: {"stock_qty": Decimal("10")}})  # type: ignore[assignment]
        result = await service.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        instance = _problem(sync_session)

    assert result.resolved_count == 1
    assert instance.status == "resolved"
    assert instance.resolved_at is not None


@pytest.mark.asyncio
async def test_missing_metrics_create_data_blocker_when_configured() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(
            sync_session,
            problem_code="missing_cost_blocks_profit",
            condition_json={">": [{"metric": "cost_price"}, 0]},
            title_template="Missing cost for {nm_id}",
            description_template="Cost data is required.",
            recommendation_template="Upload cost.",
            impact_type_default="data_blocker",
            trust_state_default="blocked",
            impact_formula_json={"metric": "cost_price"},
            recheck_rule_json={"human": "Upload costs and re-run.", "missing_metrics_policy": "data_blocker"},
            evidence_template_json={"formula_human": "cost_price is required"},
        )
        result = await _service(
            _FakeMetricResolver({1001: {}}, missing_by_nm={1001: {"cost_price"}})
        ).evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )
        instance = _problem(sync_session)

    assert result.created_count == 1
    assert instance.impact_type == "data_blocker"
    assert instance.status == "blocked"
    assert instance.trust_state == "blocked"
    assert "cost_price: source_data_missing" in instance.evidence_ledger_json["missing_data"]


@pytest.mark.asyncio
async def test_test_mode_returns_preview_without_persisting() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session, condition_json={">": [{"metric": "stock_qty"}, 50]})
        result = await _service(_FakeMetricResolver({1001: {"stock_qty": Decimal("60")}})).evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            test_mode=True,
        )
        count = _problem_count(sync_session)

    assert result.test_mode is True
    assert result.matched_count == 1
    assert result.previews[0].action == "preview_create"
    assert result.previews[0].evidence_ledger_json["input_facts"]
    assert count == 0


@pytest.mark.asyncio
async def test_evaluate_account_runs_active_rules_for_all_eligible_products() -> None:
    sync_session, session = _session()
    with sync_session:
        _add_rule(sync_session, condition_json={">": [{"metric": "stock_qty"}, 50]})
        sync_session.add_all(
            [
                MartStockDaily(
                    account_id=1,
                    dedupe_key="stock-1",
                    stat_date=date(2026, 7, 6),
                    nm_id=1001,
                    vendor_code="SKU-1",
                    barcode="BC-1",
                    warehouse_id=1,
                    warehouse_name="Main",
                    quantity=Decimal("60"),
                ),
                MartStockDaily(
                    account_id=1,
                    dedupe_key="stock-2",
                    stat_date=date(2026, 7, 6),
                    nm_id=1002,
                    vendor_code="SKU-2",
                    barcode="BC-2",
                    warehouse_id=1,
                    warehouse_name="Main",
                    quantity=Decimal("70"),
                ),
            ]
        )
        sync_session.flush()

        result = await _service(
            _FakeMetricResolver(
                {
                    1001: {"stock_qty": Decimal("60")},
                    1002: {"stock_qty": Decimal("70")},
                }
            )
        ).evaluate_account(
            session,  # type: ignore[arg-type]
            account_id=1,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
        )

    assert result.created_count == 2
    assert {preview.nm_id for preview in result.previews if preview.matched} == {1001, 1002}
