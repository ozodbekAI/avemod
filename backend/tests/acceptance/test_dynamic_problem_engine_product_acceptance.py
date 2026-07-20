from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.operator import ResultEvent
from app.models.problem_engine import (
    AdminRuleTestRun,
    MetricCatalog,
    ProblemDefinition,
    ProblemEvaluationRunLog,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleAdminAudit,
    ProblemRuleVersion,
)
from app.schemas.portal import PortalActionSourceUpdateRequest
from app.schemas.problem_engine import (
    AdminProblemDefinitionCreate,
    AdminProblemRuleVersionCreate,
    AdminRuleBacktestRequest,
    AdminRulePublishRequest,
    MetricSourceReference,
    ProductMetricResolution,
    ResolvedMetricValue,
)
from app.services.portal import PortalService
from app.services.problem_engine import (
    DynamicProblemSeedService,
    MetricCatalogService,
    ProblemEvaluatorService,
)
from app.services.problem_engine.admin_rules import ProblemRuleAdminService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw) -> str:
    return "INTEGER"


ACCOUNT_ID = 1
NM_ID = 1001
DATE_FROM = date(2026, 6, 7)
DATE_TO = date(2026, 7, 6)


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

    async def commit(self) -> None:
        self._session.commit()

    async def refresh(self, instance) -> None:
        self._session.refresh(instance)


class _FixtureMetricResolver:
    def __init__(
        self,
        values_by_nm: dict[int, dict[str, Any]],
        *,
        missing_by_nm: dict[int, set[str]] | None = None,
        trust_by_metric: dict[str, str] | None = None,
    ) -> None:
        self.values_by_nm = values_by_nm
        self.missing_by_nm = missing_by_nm or {}
        self.trust_by_metric = trust_by_metric or {}

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
        values = self.values_by_nm.get(nm_id, {})
        explicitly_missing = self.missing_by_nm.get(nm_id, set())
        resolution = ProductMetricResolution(account_id=account_id, nm_id=nm_id, date_from=date_from, date_to=date_to)
        for code in list(metric_codes or []):
            is_missing = code in explicitly_missing or code not in values or values.get(code) is None
            resolution.metrics[code] = ResolvedMetricValue(
                metric_code=code,
                value=None if is_missing else values[code],
                value_type=_value_type(code),
                unit=_unit(code),
                trust_state="blocked" if is_missing else self.trust_by_metric.get(code, "confirmed"),
                is_missing=is_missing,
                missing_reason="source_data_missing" if is_missing else None,
                evidence=MetricSourceReference(
                    source_module="acceptance_fixture",
                    source_table="acceptance_metric_fixture",
                    source_endpoint="fixture://dynamic-problem-engine/product",
                    date_from=date_from,
                    date_to=date_to,
                    row_count=0 if is_missing else 1,
                    filters={"account_id": account_id, "nm_id": nm_id, "metric_code": code},
                    freshness={"mode": "fixture", "external_network": False},
                ),
            )
            if is_missing:
                resolution.missing_metrics.append(code)
        return resolution


def _value_type(metric_code: str) -> str:
    if metric_code in {"margin_pct", "return_rate", "conversion_rate", "ad_ctr_7d"}:
        return "percent"
    if metric_code in {"days_of_stock"}:
        return "days"
    if metric_code in {
        "stock_qty",
        "sales_30d",
        "units_sold_7d",
        "sales_7d",
        "orders_7d",
        "orders_30d",
        "views_30d",
        "ad_views_7d",
        "ad_clicks_7d",
        "ad_orders_7d",
        "negative_reviews_30d",
        "unanswered_negative_reviews_30d",
        "unanswered_questions_30d",
    }:
        return "count"
    if metric_code in {"avg_daily_sales_7d", "avg_daily_sales_14d", "avg_rating_30d"}:
        return "number"
    return "money"


def _unit(metric_code: str) -> str:
    if metric_code in {"margin_pct", "return_rate", "conversion_rate", "ad_ctr_7d"}:
        return "%"
    if metric_code in {"days_of_stock"}:
        return "days"
    if metric_code in {
        "stock_qty",
        "sales_30d",
        "units_sold_7d",
        "sales_7d",
        "orders_7d",
        "orders_30d",
        "ad_orders_7d",
    }:
        return "pcs"
    if metric_code in {
        "negative_reviews_30d",
        "unanswered_negative_reviews_30d",
    }:
        return "reviews"
    if metric_code == "unanswered_questions_30d":
        return "questions"
    if metric_code in {"views_30d", "ad_views_7d"}:
        return "views"
    if metric_code == "ad_clicks_7d":
        return "clicks"
    if metric_code in {"avg_daily_sales_7d", "avg_daily_sales_14d"}:
        return "pcs/day"
    if metric_code == "avg_rating_30d":
        return "stars"
    if metric_code == "avg_daily_revenue_7d":
        return "RUB/day"
    if metric_code == "ad_cpo_7d":
        return "RUB/order"
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
        ProblemEvaluationRunLog.__table__,
        AdminRuleTestRun.__table__,
        ProblemRuleAdminAudit.__table__,
        ResultEvent.__table__,
    ):
        table.create(engine)


async def _session_with_seeded_rules() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=ACCOUNT_ID, name="Acceptance account"))
    session = _AsyncSessionAdapter(sync_session)
    await MetricCatalogService().seed_initial_metrics(session)  # type: ignore[arg-type]
    await DynamicProblemSeedService().seed_initial_problem_rules(session)  # type: ignore[arg-type]
    sync_session.flush()
    return sync_session, session


async def _session_with_metric_catalog_only() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=ACCOUNT_ID, name="Acceptance account"))
    session = _AsyncSessionAdapter(sync_session)
    await MetricCatalogService().seed_initial_metrics(session)  # type: ignore[arg-type]
    sync_session.flush()
    return sync_session, session


def _activate_only(sync_session: Session, *problem_codes: str) -> None:
    active = set(problem_codes)
    for definition in sync_session.execute(select(ProblemDefinition)).scalars():
        definition.status = "active" if definition.problem_code in active else "paused"
    sync_session.flush()


async def _evaluate_product(
    session: _AsyncSessionAdapter,
    resolver: _FixtureMetricResolver,
) -> Any:
    return await ProblemEvaluatorService(
        metric_resolver=resolver,
        metric_catalog=MetricCatalogService(),
    ).evaluate_product(
        session,  # type: ignore[arg-type]
        account_id=ACCOUNT_ID,
        nm_id=NM_ID,
        date_from=DATE_FROM,
        date_to=DATE_TO,
    )


def _instances(sync_session: Session) -> list[ProblemInstance]:
    return list(sync_session.execute(select(ProblemInstance).order_by(ProblemInstance.problem_code)).scalars())


def _instance(sync_session: Session, problem_code: str) -> ProblemInstance:
    return sync_session.execute(
        select(ProblemInstance).where(ProblemInstance.problem_code == problem_code)
    ).scalar_one()


def _definition(sync_session: Session, problem_code: str) -> ProblemDefinition:
    return sync_session.execute(
        select(ProblemDefinition).where(ProblemDefinition.problem_code == problem_code)
    ).scalar_one()


@pytest.mark.asyncio
async def test_scenario_missing_cost_creates_data_fix_blocker_and_not_negative_profit() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "missing_cost_blocks_profit", "negative_unit_profit")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "revenue_30d": Decimal("1200"),
                        "unit_profit": Decimal("-20"),
                        "margin_pct": Decimal("-5"),
                        "sales_30d": Decimal("3"),
                    }
                },
                missing_by_nm={NM_ID: {"cost_price"}},
            ),
        )

        instances = _instances(sync_session)
        missing_cost = _instance(sync_session, "missing_cost_blocks_profit")
        action = PortalService()._problem_instance_action(
            missing_cost,
            definition=_definition(sync_session, "missing_cost_blocks_profit"),
        )

    assert [instance.problem_code for instance in instances] == ["missing_cost_blocks_profit"]
    assert "negative_unit_profit" not in {instance.problem_code for instance in instances}
    assert missing_cost.status == "blocked"
    assert missing_cost.impact_type == "data_blocker"
    assert missing_cost.trust_state == "blocked"
    assert "cost_price: source_data_missing" in missing_cost.evidence_ledger_json["missing_data"]
    assert {"upload_cost", "map_sku"}.issubset(set(action.allowed_actions or []))


@pytest.mark.asyncio
async def test_scenario_negative_profit_uses_formula_evidence_and_estimated_trust() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "missing_cost_blocks_profit", "negative_unit_profit")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "revenue_30d": Decimal("1200"),
                        "cost_price": Decimal("90"),
                        "unit_profit": Decimal("-13"),
                        "margin_pct": Decimal("-13"),
                        "sales_30d": Decimal("4"),
                        "price_current": Decimal("100"),
                        "price_after_discount": Decimal("100"),
                        "commission_per_unit": Decimal("12"),
                        "logistics_per_unit": Decimal("8"),
                        "acquiring_per_unit": Decimal("2"),
                        "storage_fee_per_unit": Decimal("1"),
                    }
                },
                trust_by_metric={
                    "cost_price": "estimated",
                    "unit_profit": "estimated",
                    "margin_pct": "estimated",
                },
            ),
        )

        instances = _instances(sync_session)
        negative_profit = _instance(sync_session, "negative_unit_profit")
        metric_codes = {fact["metric_code"] for fact in negative_profit.evidence_ledger_json["input_facts"]}

    assert [instance.problem_code for instance in instances] == ["negative_unit_profit"]
    assert {"cost_price", "unit_profit", "margin_pct", "sales_30d"}.issubset(metric_codes)
    assert negative_profit.money_impact_amount == Decimal("52.0000")
    assert "проверьте себестоимость, рекламу, промо и логистику" in negative_profit.recommendation.lower()
    assert negative_profit.trust_state != "confirmed"
    assert negative_profit.evidence_ledger_json["formula_code"] == "negative_unit_profit.v1"


@pytest.mark.asyncio
async def test_scenario_overstock_calculates_blocked_cash_and_allows_discount_only_when_safe() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "overstock_slow_moving")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "stock_qty": Decimal("120"),
                        "days_of_stock": Decimal("90"),
                        "avg_daily_sales_14d": Decimal("1"),
                        "cost_price": Decimal("80"),
                        "price_current": Decimal("200"),
                        "price_after_discount": Decimal("200"),
                        "commission_per_unit": Decimal("10"),
                        "logistics_per_unit": Decimal("5"),
                        "acquiring_per_unit": Decimal("3"),
                        "storage_fee_per_unit": Decimal("2"),
                    }
                }
            ),
        )

        overstock = _instance(sync_session, "overstock_slow_moving")
        price_safety = overstock.calculation_snapshot_json["price_safety"]

    assert overstock.impact_type == "blocked_cash"
    assert overstock.trust_state == "estimated"
    assert overstock.money_impact_amount == Decimal("5600.0000")
    assert price_safety["status"] == "safe"
    assert price_safety["can_recommend_price_decrease"] is True
    assert "safe_promo" in overstock.calculation_snapshot_json["allowed_actions"]
    assert "Промо или скидка безопасна только до" in overstock.recommendation


@pytest.mark.asyncio
async def test_scenario_low_stock_points_to_supply_replenishment() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "low_stock_risk")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "days_of_stock": Decimal("3"),
                        "avg_daily_sales_7d": Decimal("2"),
                        "avg_daily_revenue_7d": Decimal("100"),
                    }
                }
            ),
        )

        low_stock = _instance(sync_session, "low_stock_risk")

    assert low_stock.impact_type == "lost_sales_risk"
    assert low_stock.impact_type != "confirmed_loss"
    assert low_stock.trust_state in {"provisional", "estimated"}
    assert low_stock.money_impact_amount == Decimal("400.0000")
    assert "запланируйте поставку или пополнение" in low_stock.recommendation.lower()
    assert low_stock.evidence_ledger_json["formula_code"] == "low_stock_risk.v1"


@pytest.mark.asyncio
async def test_scenario_ads_spend_without_orders_creates_ads_review_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "ads_spend_no_orders")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "ad_spend_7d": Decimal("1600"),
                        "orders_7d": Decimal("0"),
                    }
                }
            ),
        )

        ads_problem = _instance(sync_session, "ads_spend_no_orders")
        action = PortalService()._problem_instance_action(
            ads_problem,
            definition=_definition(sync_session, "ads_spend_no_orders"),
        )

    assert ads_problem.impact_type == "probable_loss"
    assert ads_problem.money_impact_amount == Decimal("1600.0000")
    assert ads_problem.evidence_ledger_json["formula_code"] == "ads_spend_no_orders.v1"
    assert "open_ads_dashboard" in set(action.allowed_actions or [])
    assert "run_checker" in set(action.allowed_actions or [])


@pytest.mark.asyncio
async def test_scenario_low_conversion_card_creates_content_opportunity_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "low_conversion_card")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "views_30d": Decimal("2400"),
                        "conversion_rate": Decimal("0.4"),
                        "orders_30d": Decimal("9"),
                        "revenue_30d": Decimal("18000"),
                    }
                }
            ),
        )

        conversion = _instance(sync_session, "low_conversion_card")
        action = PortalService()._problem_instance_action(
            conversion,
            definition=_definition(sync_session, "low_conversion_card"),
        )

    assert conversion.impact_type == "opportunity"
    assert conversion.trust_state == "opportunity"
    assert conversion.money_impact_amount == Decimal("18000.0000")
    assert conversion.evidence_ledger_json["formula_code"] == "low_conversion_card.v1"
    assert {"run_checker", "open_ads_dashboard", "open_price_review"}.issubset(
        set(action.allowed_actions or [])
    )


@pytest.mark.asyncio
async def test_scenario_high_return_rate_creates_card_quality_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "high_return_rate")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "sales_30d": Decimal("12"),
                        "return_rate": Decimal("35"),
                        "revenue_30d": Decimal("24000"),
                    }
                }
            ),
        )

        returns = _instance(sync_session, "high_return_rate")
        action = PortalService()._problem_instance_action(
            returns,
            definition=_definition(sync_session, "high_return_rate"),
        )

    assert returns.impact_type == "probable_loss"
    assert returns.money_impact_amount == Decimal("8400.0000")
    assert returns.evidence_ledger_json["formula_code"] == "high_return_rate.v1"
    assert "run_checker" in set(action.allowed_actions or [])


@pytest.mark.asyncio
async def test_scenario_jvo_ads_efficiency_tasks_create_ad_reviews() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(
            sync_session,
            "high_ad_drr",
            "high_ad_cpo",
            "low_ads_ctr",
            "ads_stockout_risk",
        )

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "ad_spend_7d": Decimal("6000"),
                        "revenue_7d": Decimal("10000"),
                        "ad_orders_7d": Decimal("5"),
                        "ad_cpo_7d": Decimal("1200"),
                        "ad_views_7d": Decimal("5000"),
                        "ad_clicks_7d": Decimal("15"),
                        "ad_ctr_7d": Decimal("0.3"),
                        "days_of_stock": Decimal("2"),
                        "avg_daily_sales_7d": Decimal("2"),
                    }
                }
            ),
        )

        problem_codes = {instance.problem_code for instance in _instances(sync_session)}
        high_drr = _instance(sync_session, "high_ad_drr")
        low_ctr = _instance(sync_session, "low_ads_ctr")

    assert {
        "high_ad_drr",
        "high_ad_cpo",
        "low_ads_ctr",
        "ads_stockout_risk",
    }.issubset(problem_codes)
    assert high_drr.money_impact_amount == Decimal("6000.0000")
    assert high_drr.evidence_ledger_json["formula_code"] == "high_ad_drr.v1"
    assert low_ctr.impact_type == "opportunity"
    assert low_ctr.evidence_ledger_json["formula_code"] == "low_ads_ctr.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_stockout_now_creates_critical_supply_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "stockout_now_with_recent_orders")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "stock_qty": Decimal("0"),
                        "orders_7d": Decimal("3"),
                        "avg_daily_revenue_7d": Decimal("700"),
                    }
                }
            ),
        )

        stockout = _instance(sync_session, "stockout_now_with_recent_orders")

    assert stockout.severity == "critical"
    assert stockout.impact_type == "lost_sales_risk"
    assert stockout.money_impact_amount == Decimal("4900.0000")
    assert stockout.evidence_ledger_json["formula_code"] == "stockout_now_with_recent_orders.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_stockout_14d_creates_planning_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "stockout_risk_14d")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "days_of_stock": Decimal("10"),
                        "avg_daily_sales_14d": Decimal("2"),
                        "avg_daily_revenue_7d": Decimal("900"),
                    }
                }
            ),
        )

        stockout = _instance(sync_session, "stockout_risk_14d")

    assert stockout.severity == "medium"
    assert stockout.impact_type == "lost_sales_risk"
    assert stockout.money_impact_amount == Decimal("3600.0000")
    assert stockout.evidence_ledger_json["formula_code"] == "stockout_risk_14d.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_storage_pressure_creates_stock_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "storage_cost_pressure")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "stock_qty": Decimal("120"),
                        "days_of_stock": Decimal("80"),
                        "storage_fee_per_unit": Decimal("6"),
                    }
                }
            ),
        )

        storage = _instance(sync_session, "storage_cost_pressure")

    assert storage.impact_type == "blocked_cash"
    assert storage.money_impact_amount == Decimal("720.0000")
    assert storage.evidence_ledger_json["formula_code"] == "storage_cost_pressure.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_views_without_orders_creates_card_offer_task() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "no_sales_with_views")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "views_30d": Decimal("2500"),
                        "orders_30d": Decimal("0"),
                    }
                }
            ),
        )

        card = _instance(sync_session, "no_sales_with_views")

    assert card.impact_type == "opportunity"
    assert card.money_impact_amount == Decimal("0.0000")
    assert card.evidence_ledger_json["formula_code"] == "no_sales_with_views.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_price_opportunities_create_price_reviews() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "price_offer_blocks_conversion")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "views_30d": Decimal("2400"),
                        "conversion_rate": Decimal("0.5"),
                        "margin_pct": Decimal("35"),
                        "revenue_30d": Decimal("18000"),
                    }
                }
            ),
        )

        price_offer = _instance(sync_session, "price_offer_blocks_conversion")

    assert price_offer.impact_type == "opportunity"
    assert price_offer.money_impact_amount == Decimal("18000.0000")
    assert price_offer.evidence_ledger_json["formula_code"] == "price_offer_blocks_conversion.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_high_demand_can_raise_price_to_protect_stock() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "raise_price_possible_high_demand")

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "orders_7d": Decimal("25"),
                        "days_of_stock": Decimal("5"),
                        "margin_pct": Decimal("18"),
                        "price_after_discount": Decimal("900"),
                        "avg_daily_revenue_7d": Decimal("1500"),
                    }
                }
            ),
        )

        price = _instance(sync_session, "raise_price_possible_high_demand")

    assert price.impact_type == "opportunity"
    assert price.money_impact_amount == Decimal("3000.0000")
    assert price.evidence_ledger_json["formula_code"] == "raise_price_possible_high_demand.v1"


@pytest.mark.asyncio
async def test_scenario_jvo_reputation_tasks_create_reply_and_rating_work() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(
            sync_session,
            "negative_reviews_need_reply",
            "questions_need_reply",
            "low_product_rating",
        )

        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "negative_reviews_30d": Decimal("3"),
                        "unanswered_negative_reviews_30d": Decimal("1"),
                        "unanswered_questions_30d": Decimal("2"),
                        "avg_rating_30d": Decimal("3.6"),
                        "revenue_30d": Decimal("22000"),
                    }
                }
            ),
        )

        problem_codes = {instance.problem_code for instance in _instances(sync_session)}
        reviews = _instance(sync_session, "negative_reviews_need_reply")
        rating = _instance(sync_session, "low_product_rating")

    assert {
        "negative_reviews_need_reply",
        "questions_need_reply",
        "low_product_rating",
    }.issubset(problem_codes)
    assert reviews.impact_type == "opportunity"
    assert reviews.evidence_ledger_json["formula_code"] == "negative_reviews_need_reply.v1"
    assert rating.severity == "high"
    assert rating.money_impact_amount == Decimal("22000.0000")


@pytest.mark.asyncio
async def test_scenario_action_center_status_update_is_canonical_and_survives_refresh() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "low_stock_risk")
        await _evaluate_product(
            session,
            _FixtureMetricResolver(
                {
                    NM_ID: {
                        "days_of_stock": Decimal("3"),
                        "avg_daily_sales_7d": Decimal("2"),
                        "avg_daily_revenue_7d": Decimal("100"),
                    }
                }
            ),
        )
        problem = _instance(sync_session, "low_stock_risk")

        updated = await PortalService().update_action_by_source(
            session,
            payload=PortalActionSourceUpdateRequest(
                account_id=ACCOUNT_ID,
                source_module="problem_engine",
                source_id=str(problem.id),
                status="in_progress",
                comment="Owner is replenishing stock.",
                assigned_to_user_id=7,
            ),
            user_id=42,
        )
        sync_session.refresh(problem)
        refreshed_actions = await PortalService()._problem_instance_actions(session, account_id=ACCOUNT_ID)
        history_events = list(sync_session.execute(select(ProblemInstanceHistory.event_type)).scalars())

    assert updated.status == "in_progress"
    assert problem.status == "in_progress"
    assert refreshed_actions[0].status == "in_progress"
    assert {"status_changed", "assigned", "comment_added"}.issubset(set(history_events))


@pytest.mark.asyncio
async def test_scenario_recheck_resolves_fixed_problem() -> None:
    sync_session, session = await _session_with_seeded_rules()
    with sync_session:
        _activate_only(sync_session, "low_stock_risk")
        resolver = _FixtureMetricResolver(
            {
                NM_ID: {
                    "days_of_stock": Decimal("3"),
                    "avg_daily_sales_7d": Decimal("2"),
                    "avg_daily_revenue_7d": Decimal("100"),
                }
            }
        )
        runner = ProblemEvaluationRunnerService(
            evaluator=ProblemEvaluatorService(metric_resolver=resolver, metric_catalog=MetricCatalogService())
        )
        await runner.evaluate_products(
            session,  # type: ignore[arg-type]
            account_id=ACCOUNT_ID,
            nm_ids=[NM_ID],
            date_from=DATE_FROM,
            date_to=DATE_TO,
            trigger="acceptance_fixture",
        )
        problem = _instance(sync_session, "low_stock_risk")

        resolver.values_by_nm[NM_ID] = {
            "days_of_stock": Decimal("14"),
            "avg_daily_sales_7d": Decimal("2"),
            "avg_daily_revenue_7d": Decimal("100"),
        }
        log, refreshed = await runner.recheck_problem_instance(
            session,  # type: ignore[arg-type]
            problem_instance_id=problem.id,
            actor_user_id=42,
        )
        history_events = list(sync_session.execute(select(ProblemInstanceHistory.event_type)).scalars())

    assert log.status == "completed"
    assert log.issues_resolved == 1
    assert refreshed.status == "resolved"
    assert "recheck_completed" in history_events


@pytest.mark.asyncio
async def test_scenario_admin_draft_rule_publishes_after_validation_and_backtest_then_generates_for_seller() -> None:
    sync_session, session = await _session_with_metric_catalog_only()
    with sync_session:
        resolver = _FixtureMetricResolver({NM_ID: {"stock_qty": Decimal("75")}})
        evaluator = ProblemEvaluatorService(metric_resolver=resolver, metric_catalog=MetricCatalogService())
        admin_service = ProblemRuleAdminService(evaluator=evaluator)

        definition = await admin_service.create_definition(
            session,  # type: ignore[arg-type]
            AdminProblemDefinitionCreate(
                problem_code="acceptance_high_stock",
                category="stock",
                entity_type="product",
                title_template="High stock acceptance rule for {nm_id}",
                description_template="Stock is {stock_qty}.",
                recommendation_template="Create task and review stock.",
                impact_type_default="blocked_cash",
                trust_state_default="estimated",
                severity_default="medium",
                allowed_actions_json=["run_checker", "recheck", "dismiss"],
            ),
            actor_user_id=42,
        )
        rule = await admin_service.create_version(
            session,  # type: ignore[arg-type]
            definition.id,
            AdminProblemRuleVersionCreate(
                condition_json={">": [{"metric": "stock_qty"}, 50]},
                impact_formula_json={"*": [{"metric": "stock_qty"}, 10]},
                severity_formula_json="medium",
                confidence_formula_json="estimated",
                dedup_key_template="{account_id}:{problem_code}:{nm_id}",
                recheck_rule_json={
                    "human": "Re-run after stock changes.",
                    "resolved_when": {"<=": [{"metric": "stock_qty"}, 50]},
                },
                evidence_template_json={
                    "formula_human": "stock_qty > 50",
                    "recheck_rule_human": "Re-run after stock changes.",
                    "money_currency": "RUB",
                    "selected_input_metrics": ["stock_qty"],
                    "solve_map_template": {
                        "title": "Карта решения: высокий остаток",
                        "summary": "Проверьте доказательства, откройте проверку карточки и перепроверьте остаток.",
                        "steps": [
                            {
                                "step_id": "evidence",
                                "order": 1,
                                "title": "Проверить доказательства",
                                "description": "Сверьте формулу, факт остатка и источник данных.",
                                "status": "ready",
                                "action_code": None,
                                "target_href": None,
                                "required_metrics": ["stock_qty"],
                                "blocking_reason": None,
                                "completion_signal": "Доказательства понятны.",
                            },
                            {
                                "step_id": "checker",
                                "order": 2,
                                "title": "Открыть проверку карточки",
                                "description": "Проверьте карточку товара перед действиями по остатку.",
                                "status": "available",
                                "action_code": "run_checker",
                                "target_href": None,
                                "required_metrics": ["stock_qty"],
                                "blocking_reason": None,
                                "completion_signal": "Карточка проверена.",
                            },
                            {
                                "step_id": "recheck",
                                "order": 3,
                                "title": "Перепроверить остаток",
                                "description": "Запустите повторную проверку после действия.",
                                "status": "available",
                                "action_code": "recheck",
                                "target_href": None,
                                "required_metrics": ["stock_qty"],
                                "blocking_reason": None,
                                "completion_signal": "Остаток пересчитан.",
                            },
                        ],
                    },
                },
            ),
            actor_user_id=42,
        )

        before_publish = await evaluator.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=ACCOUNT_ID,
            nm_id=NM_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )
        validation = await admin_service.validate_version(session, rule.id)
        backtest = await admin_service.backtest(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRuleBacktestRequest(account_id=ACCOUNT_ID, nm_id=NM_ID, date_from=DATE_FROM, date_to=DATE_TO),
            actor_user_id=42,
        )
        published = await admin_service.publish(
            session,  # type: ignore[arg-type]
            rule.id,
            AdminRulePublishRequest(),
            actor_user_id=42,
        )
        after_publish = await evaluator.evaluate_product(
            session,  # type: ignore[arg-type]
            account_id=ACCOUNT_ID,
            nm_id=NM_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )
        seller_actions = await PortalService()._problem_instance_actions(session, account_id=ACCOUNT_ID)

    assert before_publish.created_count == 0
    assert validation.valid is True
    assert backtest.matched_count == 1
    assert published.status == "active"
    assert after_publish.created_count == 1
    assert seller_actions[0].action_type == "acceptance_high_stock"
    assert seller_actions[0].evidence_ledger is not None
    assert seller_actions[0].solve_map is not None
    assert seller_actions[0].solve_map.title == "Карта решения: высокий остаток"
    assert seller_actions[0].solve_map.steps[1].action_code == "run_checker"
    assert seller_actions[0].solve_map.steps[1].target_href == f"/checker/{NM_ID}?problem_instance_id={seller_actions[0].source_id}"
