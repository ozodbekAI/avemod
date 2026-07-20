from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import re
from typing import Any

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.problem_engine import MetricCatalog, ProblemDefinition, ProblemInstance, ProblemInstanceHistory, ProblemRuleVersion
from app.schemas.problem_engine import MetricSourceReference, ProductMetricResolution, ResolvedMetricValue
from app.services.problem_engine import DynamicProblemSeedCopyRepairService, DynamicProblemSeedService, MetricCatalogService, ProblemEvaluatorService
from app.services.problem_engine.problem_seeds import INITIAL_PROBLEM_RULE_SEEDS, OLD_SEEDED_DEFINITION_TEMPLATES
from app.services.problem_engine.seed_copy_repair import OLD_SEEDED_RULE_COPY


SEEDED_PROBLEM_CODES = {
    "missing_cost_blocks_profit",
    "negative_unit_profit",
    "overstock_slow_moving",
    "low_stock_risk",
    "ads_spend_without_profit",
    "promo_not_profitable",
    "price_below_safe_margin",
    "dead_stock",
    "fast_stock_depletion",
}


def _has_cyrillic(value: str | None) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", value or ""))


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


class _FakeMetricResolver:
    def __init__(self, values: dict[str, Any], missing: set[str] | None = None) -> None:
        self.values = values
        self.missing = missing or set()

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
        resolution = ProductMetricResolution(account_id=account_id, nm_id=nm_id, date_from=date_from, date_to=date_to)
        for code in list(metric_codes or []):
            is_missing = code in self.missing or code not in self.values or self.values.get(code) is None
            resolution.metrics[code] = ResolvedMetricValue(
                metric_code=code,
                value=None if is_missing else self.values[code],
                value_type=_value_type(code),
                unit=_unit(code),
                trust_state="blocked" if is_missing else "confirmed",
                is_missing=is_missing,
                missing_reason="source_data_missing" if is_missing else None,
                evidence=MetricSourceReference(
                    source_module="test",
                    source_table="test_metric_source",
                    source_endpoint="GET /test/metrics",
                    date_from=date_from,
                    date_to=date_to,
                    row_count=0 if is_missing else 1,
                    filters={"account_id": account_id, "nm_id": nm_id},
                ),
            )
            if is_missing:
                resolution.missing_metrics.append(code)
        return resolution


def _value_type(metric_code: str) -> str:
    if metric_code in {"margin_pct"}:
        return "percent"
    if metric_code in {"days_of_stock"}:
        return "days"
    if metric_code in {"stock_qty", "sales_30d", "units_sold_7d", "sales_7d"}:
        return "count"
    if metric_code in {"avg_daily_sales_7d", "avg_daily_sales_14d"}:
        return "number"
    return "money"


def _unit(metric_code: str) -> str:
    if metric_code in {"margin_pct"}:
        return "%"
    if metric_code in {"days_of_stock"}:
        return "days"
    if metric_code in {"stock_qty", "sales_30d", "units_sold_7d", "sales_7d"}:
        return "pcs"
    if metric_code == "avg_daily_sales_14d" or metric_code == "avg_daily_sales_7d":
        return "pcs/day"
    if metric_code == "avg_daily_revenue_7d":
        return "RUB/day"
    return "RUB"


def _create_tables(engine) -> None:
    for table in (
        WBAccount.__table__,
        MetricCatalog.__table__,
        MartSKUDaily.__table__,
        MartStockDaily.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
    ):
        table.create(engine)


async def _seed(sync_session: Session) -> _AsyncSessionAdapter:
    session = _AsyncSessionAdapter(sync_session)
    sync_session.add(WBAccount(id=1, name="Test account"))
    await MetricCatalogService().seed_initial_metrics(session)  # type: ignore[arg-type]
    await DynamicProblemSeedService().seed_initial_problem_rules(session)  # type: ignore[arg-type]
    sync_session.flush()
    return session


def _session() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    sync_session = Session(engine)
    return sync_session, _AsyncSessionAdapter(sync_session)


def _activate_only(sync_session: Session, *problem_codes: str) -> None:
    active = set(problem_codes)
    for definition in sync_session.execute(select(ProblemDefinition)).scalars():
        definition.status = "active" if definition.problem_code in active else "paused"
    sync_session.flush()


async def _evaluate(sync_session: Session, values: dict[str, Any], *, missing: set[str] | None = None) -> list[ProblemInstance]:
    session = _AsyncSessionAdapter(sync_session)
    result = await ProblemEvaluatorService(
        metric_resolver=_FakeMetricResolver(values, missing=missing),
        metric_catalog=MetricCatalogService(),
    ).evaluate_product(
        session,  # type: ignore[arg-type]
        account_id=1,
        nm_id=1001,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 7, 6),
    )
    assert result.created_count >= 1
    return list(sync_session.execute(select(ProblemInstance).order_by(ProblemInstance.problem_code)).scalars())


async def _evaluate_result(sync_session: Session, values: dict[str, Any], *, missing: set[str] | None = None) -> Any:
    session = _AsyncSessionAdapter(sync_session)
    return await ProblemEvaluatorService(
        metric_resolver=_FakeMetricResolver(values, missing=missing),
        metric_catalog=MetricCatalogService(),
    ).evaluate_product(
        session,  # type: ignore[arg-type]
        account_id=1,
        nm_id=1001,
        date_from=date(2026, 6, 7),
        date_to=date(2026, 7, 6),
    )


def _assert_evidence(instance: ProblemInstance) -> None:
    ledger = instance.evidence_ledger_json
    assert ledger["formula_code"] == f"{instance.problem_code}.v1"
    assert ledger["formula_human"]
    assert ledger["input_facts"]
    assert ledger["source_references"]
    assert ledger["recheck_rule_human"]


@pytest.mark.asyncio
async def test_initial_problem_rules_seed_active_catalog_rows() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        definitions = list(sync_session.execute(select(ProblemDefinition)).scalars())
        rules = list(sync_session.execute(select(ProblemRuleVersion)).scalars())

    definitions_by_code = {definition.problem_code: definition for definition in definitions}
    codes = set(definitions_by_code)
    assert SEEDED_PROBLEM_CODES.issubset(codes)
    assert all(definition.status == "active" for definition in definitions)
    assert all(definition.is_system_seeded for definition in definitions)
    assert len(rules) == len(INITIAL_PROBLEM_RULE_SEEDS)
    assert all(rule.status == "active" and rule.version == 1 for rule in rules)
    assert all(rule.is_system_seeded for rule in rules)
    for code in SEEDED_PROBLEM_CODES:
        definition = definitions_by_code[code]
        assert _has_cyrillic(definition.title_template)
        assert _has_cyrillic(definition.description_template)
        assert _has_cyrillic(definition.recommendation_template)
    for rule in rules:
        assert _has_cyrillic(rule.recheck_rule_json["human"])
        assert _has_cyrillic(rule.evidence_template_json["formula_human"])
        assert _has_cyrillic(rule.evidence_template_json["recheck_rule_human"])
        assert "Re-run" not in rule.recheck_rule_json["human"]
        assert "Re-run" not in rule.evidence_template_json["recheck_rule_human"]
        assert "cost_price exists" not in rule.evidence_template_json["formula_human"]


@pytest.mark.asyncio
async def test_problem_rule_seed_does_not_overwrite_custom_definition_copy() -> None:
    sync_session, session = _session()
    with sync_session:
        custom = ProblemDefinition(
            problem_code="negative_unit_profit",
            source_module="problem_engine",
            category="profitability",
            entity_type="product",
            title_template="Админское правило прибыльности",
            description_template="Кастомное описание администратора",
            recommendation_template="Кастомная рекомендация администратора",
            impact_type_default="probable_loss",
            trust_state_default="estimated",
            severity_default="high",
            allowed_actions_json=["create_task"],
            status="active",
            created_by_user_id=123,
        )
        sync_session.add(custom)
        sync_session.flush()

        await DynamicProblemSeedService().seed_initial_problem_rules(session)  # type: ignore[arg-type]
        sync_session.flush()

        definition = sync_session.execute(
            select(ProblemDefinition).where(ProblemDefinition.problem_code == "negative_unit_profit")
        ).scalar_one()

    assert definition.title_template == "Админское правило прибыльности"
    assert definition.description_template == "Кастомное описание администратора"
    assert definition.recommendation_template == "Кастомная рекомендация администратора"


def _add_old_seeded_definition_and_rule(
    sync_session: Session,
    problem_code: str,
) -> tuple[ProblemDefinition, ProblemRuleVersion]:
    old_title, old_description, old_recommendation = OLD_SEEDED_DEFINITION_TEMPLATES[problem_code]
    rule_copy = OLD_SEEDED_RULE_COPY[problem_code]
    definition = ProblemDefinition(
        problem_code=problem_code,
        source_module="problem_engine",
        category="stock" if problem_code in {"low_stock_risk", "overstock_slow_moving"} else "profitability",
        entity_type="product",
        title_template=old_title,
        description_template=old_description,
        recommendation_template=old_recommendation,
        impact_type_default="lost_sales_risk" if problem_code == "low_stock_risk" else "probable_loss",
        trust_state_default="provisional",
        severity_default="medium",
        allowed_actions_json=["create_task", "recheck"],
        status="active",
    )
    sync_session.add(definition)
    sync_session.flush()
    rule = ProblemRuleVersion(
        problem_definition_id=definition.id,
        version=1,
        status="active",
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={">": [{"metric": "days_of_stock"}, 0]},
        impact_formula_json={"metric": "avg_daily_revenue_7d"},
        severity_formula_json={"case": [{"else": "medium"}]},
        confidence_formula_json={"case": [{"else": "provisional"}]},
        dedup_key_template="{account_id}:{problem_code}:{nm_id}",
        recheck_rule_json={"human": rule_copy["recheck"]},
        evidence_template_json={
            "formula_human": rule_copy["formula"],
            "formula_code": f"{problem_code}.v1",
            "recheck_rule_human": rule_copy["evidence_recheck"],
            **({"trust_notes": rule_copy["trust_notes"]} if "trust_notes" in rule_copy else {}),
        },
    )
    sync_session.add(rule)
    sync_session.flush()
    return definition, rule


@pytest.mark.asyncio
async def test_seed_copy_repair_marks_and_updates_live_old_seeded_definitions() -> None:
    sync_session, session = _session()
    with sync_session:
        definition, rule = _add_old_seeded_definition_and_rule(sync_session, "low_stock_risk")

        result = await DynamicProblemSeedCopyRepairService().repair(session)  # type: ignore[arg-type]
        sync_session.flush()

    assert result.definitions_marked == 1
    assert result.definitions_updated == 1
    assert result.rules_marked == 1
    assert result.rules_updated == 1
    assert definition.is_system_seeded is True
    assert rule.is_system_seeded is True
    assert definition.title_template == "Риск низкого остатка по товару {nm_id}"
    assert definition.description_template.startswith("Запаса осталось")
    assert definition.recommendation_template.startswith("Запланируйте поставку")
    assert rule.recheck_rule_json["human"].startswith("Запустите повторную проверку")
    assert rule.evidence_template_json["formula_human"].startswith("Запаса меньше")
    assert rule.evidence_template_json["recheck_rule_human"].startswith("Перепроверьте")


@pytest.mark.asyncio
async def test_seed_copy_repair_does_not_overwrite_admin_custom_rules() -> None:
    sync_session, session = _session()
    with sync_session:
        old_title, old_description, old_recommendation = OLD_SEEDED_DEFINITION_TEMPLATES["negative_unit_profit"]
        definition = ProblemDefinition(
            problem_code="negative_unit_profit",
            source_module="problem_engine",
            category="profitability",
            entity_type="product",
            title_template=old_title,
            description_template=old_description,
            recommendation_template=old_recommendation,
            impact_type_default="probable_loss",
            trust_state_default="estimated",
            severity_default="high",
            allowed_actions_json=["create_task"],
            status="active",
            created_by_user_id=123,
        )
        sync_session.add(definition)
        sync_session.flush()
        rule_copy = OLD_SEEDED_RULE_COPY["negative_unit_profit"]
        rule = ProblemRuleVersion(
            problem_definition_id=definition.id,
            version=1,
            status="active",
            evaluation_grain="product_period",
            lookback_days=30,
            condition_json={">": [{"metric": "unit_profit"}, 0]},
            impact_formula_json={"metric": "unit_profit"},
            severity_formula_json={},
            confidence_formula_json={},
            dedup_key_template="{account_id}:{problem_code}:{nm_id}",
            recheck_rule_json={"human": rule_copy["recheck"]},
            evidence_template_json={
                "formula_human": rule_copy["formula"],
                "formula_code": "negative_unit_profit.v1",
                "recheck_rule_human": rule_copy["evidence_recheck"],
            },
            created_by_user_id=123,
        )
        sync_session.add(rule)
        sync_session.flush()

        result = await DynamicProblemSeedCopyRepairService().repair(session)  # type: ignore[arg-type]
        sync_session.flush()

    assert result.definitions_marked == 0
    assert result.definitions_updated == 0
    assert result.rules_marked == 0
    assert result.rules_updated == 0
    assert definition.is_system_seeded is False
    assert rule.is_system_seeded is False
    assert definition.title_template == old_title
    assert rule.recheck_rule_json["human"] == rule_copy["recheck"]


@pytest.mark.asyncio
async def test_seed_copy_repair_rerenders_existing_open_seeded_problem_instances() -> None:
    sync_session, session = _session()
    with sync_session:
        sync_session.add(WBAccount(id=1, name="Test account"))
        definition, rule = _add_old_seeded_definition_and_rule(sync_session, "low_stock_risk")
        now = datetime(2026, 7, 10, tzinfo=UTC)
        snapshot = {
            "rule_version": 1,
            "metrics": {
                "days_of_stock": {"value": 3},
                "avg_daily_sales_7d": {"value": 2},
                "avg_daily_revenue_7d": {"value": 100},
            },
        }
        old_title, old_description, old_recommendation = OLD_SEEDED_DEFINITION_TEMPLATES["low_stock_risk"]
        rule_copy = OLD_SEEDED_RULE_COPY["low_stock_risk"]
        instance = ProblemInstance(
            account_id=1,
            problem_code="low_stock_risk",
            problem_definition_id=definition.id,
            rule_version_id=rule.id,
            source_module="problem_engine",
            entity_type="product",
            entity_id="1001",
            nm_id=1001,
            vendor_code="SKU-1001",
            dedup_key="1:low_stock_risk:1001",
            title="Low stock risk for 1001",
            explanation="Days of stock is 3 while 7-day sales velocity is 2 pcs/day.",
            recommendation=old_recommendation,
            severity="medium",
            status="new",
            impact_type="lost_sales_risk",
            money_impact_amount=Decimal("400"),
            money_impact_currency="RUB",
            trust_state="provisional",
            confidence="provisional",
            evidence_ledger_json={
                "formula_human": rule_copy["formula"],
                "formula_code": "low_stock_risk.v1",
                "input_facts": [{"metric_code": "days_of_stock", "value": 3}],
                "source_references": [{"source_table": "mart_stock_daily"}],
                "recheck_rule_human": rule_copy["evidence_recheck"],
            },
            calculation_snapshot_json=snapshot,
            first_seen_at=now,
            last_seen_at=now,
        )
        customized = ProblemInstance(
            account_id=1,
            problem_code="low_stock_risk",
            problem_definition_id=definition.id,
            rule_version_id=rule.id,
            source_module="problem_engine",
            entity_type="product",
            entity_id="1002",
            nm_id=1002,
            vendor_code="SKU-1002",
            dedup_key="1:low_stock_risk:1002",
            title="Ручной заголовок",
            explanation="Ручное объяснение",
            recommendation="Ручная рекомендация",
            severity="medium",
            status="new",
            impact_type="lost_sales_risk",
            money_impact_amount=Decimal("400"),
            money_impact_currency="RUB",
            trust_state="provisional",
            confidence="provisional",
            evidence_ledger_json={
                "formula_human": rule_copy["formula"],
                "formula_code": "low_stock_risk.v1",
                "input_facts": [{"metric_code": "days_of_stock", "value": 3}],
                "source_references": [{"source_table": "mart_stock_daily"}],
                "recheck_rule_human": rule_copy["evidence_recheck"],
            },
            calculation_snapshot_json=snapshot,
            first_seen_at=now,
            last_seen_at=now,
        )
        sync_session.add_all([instance, customized])
        sync_session.flush()

        result = await DynamicProblemSeedCopyRepairService().repair(session)  # type: ignore[arg-type]
        sync_session.flush()

    assert result.instances_updated == 2
    assert instance.title == "Риск низкого остатка по товару 1001"
    assert instance.explanation == "Запаса осталось на 3 дней при средних продажах за 7 дней 2 шт./день."
    assert instance.recommendation.startswith("Запланируйте поставку")
    assert instance.evidence_ledger_json["formula_human"].startswith("Запаса меньше")
    assert instance.evidence_ledger_json["recheck_rule_human"].startswith("Перепроверьте")
    assert customized.title == "Ручной заголовок"
    assert customized.explanation == "Ручное объяснение"
    assert customized.recommendation == "Ручная рекомендация"
    assert customized.evidence_ledger_json["formula_human"].startswith("Запаса меньше")
    assert old_title.startswith("Low stock")
    assert old_description.startswith("Days of stock")


@pytest.mark.asyncio
async def test_missing_cost_blocks_profit_rule_generates_data_blocker_with_evidence() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "missing_cost_blocks_profit")
        instances = await _evaluate(sync_session, {"revenue_30d": Decimal("1200")}, missing={"cost_price"})
        instance = instances[0]

    assert instance.problem_code == "missing_cost_blocks_profit"
    assert instance.status == "blocked"
    assert instance.impact_type == "data_blocker"
    assert instance.trust_state == "blocked"
    assert instance.money_impact_amount == Decimal("1200.0000")
    assert "cost_price: source_data_missing" in instance.evidence_ledger_json["missing_data"]
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_missing_cost_blocker_respects_revenue_condition() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "missing_cost_blocks_profit")
        result = await _evaluate_result(sync_session, {"revenue_30d": Decimal("0")}, missing={"cost_price"})
        instances = list(sync_session.execute(select(ProblemInstance)).scalars())

    assert result.created_count == 0
    assert result.skipped_count == 1
    assert instances == []


@pytest.mark.asyncio
async def test_negative_unit_profit_rule_requires_cost_and_generates_loss() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "negative_unit_profit")
        instances = await _evaluate(
            sync_session,
            {
                "cost_price": Decimal("50"),
                "unit_profit": Decimal("-20"),
                "margin_pct": Decimal("-5"),
                "sales_30d": Decimal("3"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "negative_unit_profit"
    assert instance.impact_type == "probable_loss"
    assert instance.money_impact_amount == Decimal("60.0000")
    assert instance.trust_state == "estimated"
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_missing_cost_triggers_cost_blocker_not_negative_profit() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "missing_cost_blocks_profit", "negative_unit_profit")
        instances = await _evaluate(
            sync_session,
            {
                "revenue_30d": Decimal("1200"),
                "unit_profit": Decimal("-20"),
                "margin_pct": Decimal("-5"),
                "sales_30d": Decimal("3"),
            },
            missing={"cost_price"},
        )

    assert [instance.problem_code for instance in instances] == ["missing_cost_blocks_profit"]


@pytest.mark.asyncio
async def test_overstock_slow_moving_rule_generates_blocked_cash() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "overstock_slow_moving")
        instances = await _evaluate(
            sync_session,
            {
                "stock_qty": Decimal("120"),
                "days_of_stock": Decimal("90"),
                "avg_daily_sales_14d": Decimal("1"),
                "cost_price": Decimal("50"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "overstock_slow_moving"
    assert instance.impact_type == "blocked_cash"
    assert instance.money_impact_amount == Decimal("3500.0000")
    assert instance.trust_state == "estimated"
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_overstock_blocks_price_decrease_when_safe_margin_would_break() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "overstock_slow_moving")
        instances = await _evaluate(
            sync_session,
            {
                "stock_qty": Decimal("120"),
                "days_of_stock": Decimal("90"),
                "avg_daily_sales_14d": Decimal("1"),
                "cost_price": Decimal("80"),
                "price_current": Decimal("120"),
                "price_after_discount": Decimal("120"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            },
        )
        instance = instances[0]

    price_safety = instance.calculation_snapshot_json["price_safety"]
    assert price_safety["status"] == "unsafe"
    assert price_safety["can_recommend_price_decrease"] is False
    assert "safe_promo" not in instance.calculation_snapshot_json["allowed_actions"]
    assert "Не снижайте цену" in instance.recommendation
    assert "price_decrease_blocked_by_min_safe_price" in instance.evidence_ledger_json["calculation_warnings"]


@pytest.mark.asyncio
async def test_negative_unit_profit_recommends_calculated_target_price() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "negative_unit_profit")
        instances = await _evaluate(
            sync_session,
            {
                "cost_price": Decimal("90"),
                "unit_profit": Decimal("-13"),
                "margin_pct": Decimal("-13"),
                "sales_30d": Decimal("3"),
                "price_current": Decimal("100"),
                "price_after_discount": Decimal("100"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            },
        )
        instance = instances[0]

    assert instance.calculation_snapshot_json["price_safety"]["target_price"] == 125.56
    assert "Поднимите цену минимум до 125.56 RUB" in instance.recommendation
    assert "price_increase_target_calculated_from_unit_economics" in instance.evidence_ledger_json["calculation_warnings"]


@pytest.mark.asyncio
async def test_low_stock_risk_rule_generates_lost_sales_risk() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "low_stock_risk")
        instances = await _evaluate(
            sync_session,
            {
                "days_of_stock": Decimal("3"),
                "avg_daily_sales_7d": Decimal("2"),
                "avg_daily_revenue_7d": Decimal("100"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "low_stock_risk"
    assert instance.impact_type == "lost_sales_risk"
    assert instance.impact_type != "confirmed_loss"
    assert instance.money_impact_amount == Decimal("400.0000")
    assert instance.trust_state == "provisional"
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_ads_spend_without_profit_rule_generates_probable_loss() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "ads_spend_without_profit")
        instances = await _evaluate(
            sync_session,
            {
                "ad_spend_7d": Decimal("600"),
                "unit_profit_after_ads": Decimal("-20"),
                "units_sold_7d": Decimal("5"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "ads_spend_without_profit"
    assert instance.impact_type == "probable_loss"
    assert instance.money_impact_amount == Decimal("100.0000")
    assert instance.trust_state == "estimated"
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_promo_not_profitable_rule_generates_loss_and_blocks_deeper_discount() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "promo_not_profitable")
        instances = await _evaluate(
            sync_session,
            {
                "promo_spend_30d": Decimal("600"),
                "cost_price": Decimal("80"),
                "unit_profit": Decimal("-10"),
                "margin_pct": Decimal("-5"),
                "sales_30d": Decimal("4"),
                "price_current": Decimal("120"),
                "price_after_discount": Decimal("120"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "promo_not_profitable"
    assert instance.impact_type == "probable_loss"
    assert instance.money_impact_amount == Decimal("600.0000")
    assert instance.trust_state == "estimated"
    assert instance.calculation_snapshot_json["price_safety"]["status"] == "unsafe"
    assert "Не увеличивайте скидку" in instance.recommendation
    assert "promo_discount_blocked_by_min_safe_price" in instance.evidence_ledger_json["calculation_warnings"]
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_price_below_safe_margin_rule_recommends_safe_target_price() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "price_below_safe_margin")
        instances = await _evaluate(
            sync_session,
            {
                "cost_price": Decimal("90"),
                "unit_profit": Decimal("-13"),
                "margin_pct": Decimal("-13"),
                "sales_30d": Decimal("3"),
                "price_current": Decimal("100"),
                "price_after_discount": Decimal("100"),
                "commission_per_unit": Decimal("12"),
                "logistics_per_unit": Decimal("8"),
                "acquiring_per_unit": Decimal("2"),
                "storage_fee_per_unit": Decimal("1"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "price_below_safe_margin"
    assert instance.impact_type == "probable_loss"
    assert instance.money_impact_amount == Decimal("39.0000")
    assert instance.calculation_snapshot_json["price_safety"]["target_price"] == 125.56
    assert "Поднимите эффективную цену минимум до 125.56 RUB" in instance.recommendation
    assert "price_increase_target_calculated_from_unit_economics" in instance.evidence_ledger_json["calculation_warnings"]
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_dead_stock_rule_generates_blocked_cash_with_safe_liquidation_guard() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "dead_stock")
        instances = await _evaluate(
            sync_session,
            {
                "stock_qty": Decimal("25"),
                "sales_30d": Decimal("0"),
                "days_of_stock": Decimal("120"),
                "cost_price": Decimal("40"),
                "price_current": Decimal("120"),
                "price_after_discount": Decimal("120"),
                "commission_per_unit": Decimal("6"),
                "logistics_per_unit": Decimal("3"),
                "acquiring_per_unit": Decimal("1"),
                "storage_fee_per_unit": Decimal("0"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "dead_stock"
    assert instance.impact_type == "blocked_cash"
    assert instance.money_impact_amount == Decimal("1000.0000")
    assert instance.trust_state == "estimated"
    assert instance.calculation_snapshot_json["price_safety"]["status"] == "safe"
    assert "Распродажная скидка безопасна" in instance.recommendation
    _assert_evidence(instance)


@pytest.mark.asyncio
async def test_fast_stock_depletion_rule_generates_lost_sales_risk() -> None:
    sync_session, _session_adapter = _session()
    with sync_session:
        await _seed(sync_session)
        _activate_only(sync_session, "fast_stock_depletion")
        instances = await _evaluate(
            sync_session,
            {
                "days_of_stock": Decimal("2"),
                "avg_daily_sales_7d": Decimal("3"),
                "avg_daily_revenue_7d": Decimal("200"),
            },
        )
        instance = instances[0]

    assert instance.problem_code == "fast_stock_depletion"
    assert instance.impact_type == "lost_sales_risk"
    assert instance.money_impact_amount == Decimal("1000.0000")
    assert instance.severity == "high"
    assert instance.trust_state == "provisional"
    _assert_evidence(instance)
