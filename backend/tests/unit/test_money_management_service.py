from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.money_management import (
    ArticlePurchasePlanBlock,
    ArticleSummaryBlock,
    BusinessAnswer,
    CardPriceBlock,
    CardStockBlock,
    CardVerdict,
    CostCoverageBlock,
    DataTrustInfo,
    ExpenseBreakdownSummaryRead,
    FinalityBlock,
    FinanceReconciliationBlock,
    MoneyControlPanel,
    MoneyControlPanelCard,
    MoneyFlowBlock,
    MoneyMeta,
    MoneyQuality,
    MoneySummaryRead,
    MoneySummaryKpis,
    NextActionRead,
    ProfitCascadeRead,
    RevenueSources,
    RiskItem,
    RiskSummary,
    StoreAnswer,
    TopCardsBlock,
    VariantBreakdownRow,
)
from app.schemas.data_quality import DataQualitySummaryBlock
from app.services.money_management import MoneyManagementService, MoneyRuntimeState
from app.services.marts import MartService
from app.services.trust import TRUST_STATE_DATA_BLOCKED, TRUST_STATE_TEST_ONLY, TRUST_STATE_TRUSTED


class _FakeExecuteResult:
    def __init__(self, value) -> None:
        self.value = value

    def __iter__(self):
        if isinstance(self.value, list):
            return iter(self.value)
        return iter([self.value])

    def all(self):
        return self.value

    def one(self):
        return self.value

    def scalar_one(self):
        return self.value

    def first(self):
        if isinstance(self.value, list):
            return self.value[0] if self.value else None
        return self.value

    def scalars(self):
        return self


class _FakeAsyncSession:
    def __init__(self, results: list[object]) -> None:
        self._results = list(results)
        self.statements: list[object] = []

    async def execute(self, statement):
        self.statements.append(statement)
        if not self._results:
            raise AssertionError("No fake result prepared for execute()")
        return _FakeExecuteResult(self._results.pop(0))


def _summary_stub(
    *,
    account_id: int,
    date_from: date,
    date_to: date,
    expense_breakdown: ExpenseBreakdownSummaryRead,
    profit_cascade: ProfitCascadeRead,
    kpis: MoneySummaryKpis,
    data_version_hash: str = "summary-hash-1",
):
    return SimpleNamespace(
        expense_breakdown=expense_breakdown,
        profit_cascade=profit_cascade,
        kpis=kpis,
        data_version_hash=data_version_hash,
    )


def _test_money_meta(*, trust_state: str = "operational_provisional", financial_final: bool = False) -> MoneyMeta:
    return MoneyMeta(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        currency="RUB",
        generated_at=datetime(2026, 5, 20, 12, 0, 0),
        data_trust=DataTrustInfo(
            state=trust_state,
            trust_state=trust_state,
            business_trusted=trust_state != "data_blocked",
            operational_trusted=True,
            financial_final=financial_final,
            can_generate_business_actions=True,
            confidence="high" if financial_final else "medium",
            human_message="test trust",
        ),
    )


def test_money_date_range_uses_rolling_30_day_window(monkeypatch) -> None:
    monkeypatch.setattr("app.services.money_management.utcnow", lambda: datetime(2026, 5, 2, 12, 0, 0))
    service = MoneyManagementService()

    date_from, date_to = service._date_range(None, None)

    assert date_from == date(2026, 4, 3)
    assert date_to == date(2026, 5, 2)


def test_runtime_cache_key_changes_when_date_window_changes() -> None:
    service = MoneyManagementService()

    key_one = service._runtime_cache_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )
    key_two = service._runtime_cache_key(
        account_id=1,
        date_from=date(2026, 5, 2),
        date_to=date(2026, 5, 20),
    )

    assert key_one != key_two


def test_card_unit_economics_missing_cost_blocks_profit_instead_of_negative_profit() -> None:
    service = MoneyManagementService()

    unit = service._card_unit_economics(
        profit_row=SimpleNamespace(
            net_units=10,
            estimated_cogs=Decimal("0"),
            cost_truth_level="missing",
            has_manual_cost=False,
            has_real_manual_cost=False,
            has_placeholder_cost=False,
            cost_source=None,
            cost_trust_policy=None,
            commission=Decimal("100"),
            logistics=Decimal("20"),
            paid_acceptance=Decimal("0"),
            seller_other_expense=Decimal("0"),
        ),
        row=SimpleNamespace(
            blocked_reasons=["missing_manual_cost"],
            trust_state=TRUST_STATE_DATA_BLOCKED,
        ),
        price_row=None,
        revenue=Decimal("1000"),
        wb_expenses_total=Decimal("120"),
        seller_cost_total=Decimal("0"),
        ad_spend=Decimal("50"),
        profit_after_source_ads=Decimal("-100"),
        allocated_overhead=Decimal("0"),
    )

    assert unit.cost_price is None
    assert unit.unit_profit is None
    assert "missing_cost" in unit.blockers
    assert unit.trust_state == TRUST_STATE_DATA_BLOCKED


def test_money_control_panel_separates_confirmed_provisional_and_expected_money() -> None:
    service = MoneyManagementService()
    meta = _test_money_meta()
    state = SimpleNamespace(
        health=SimpleNamespace(blocked_reasons=[], domains=[]),
        profit_rows=[SimpleNamespace(net_units=10)],
        control_rows=[],
        price_rows={},
        account_expense_rows=[],
    )
    kpis = MoneySummaryKpis(
        revenue=1000.0,
        finance_confirmed_revenue=700.0,
        net_profit_after_all_expenses=120.0,
        seller_cogs=400.0,
    )
    action = NextActionRead(
        id=7,
        action_type="GROWTH_REVIEW",
        category="growth",
        priority="medium",
        status="new",
        title="Scale profitable product",
        what_to_do="Review growth lever",
        why="Expected impact is not measured yet.",
        expected_effect_amount=900.0,
        confidence="medium",
        linked_entity={"nm_id": 101, "sku_id": 0},
    )

    panel = service._money_control_panel(
        state=state,  # type: ignore[arg-type]
        meta=meta,
        revenue_sources=RevenueSources(open_period_revenue=300.0),
        finance_reconciliation=FinanceReconciliationBlock(
            status="matched",
            finance_confirmed_revenue=700.0,
            requested_date_from=meta.date_from,
            requested_date_to=meta.date_to,
            is_final=False,
        ),
        cost_coverage=CostCoverageBlock(
            can_use_for_operations=True,
            can_use_for_final_profit=True,
            business_accepted_cost_coverage_percent=100.0,
            supplier_confirmed_cost_coverage_percent=100.0,
        ),
        quality=MoneyQuality(final_finance_ready=False, finance_reconciliation_status="matched"),
        kpis=kpis,
        risks=[],
        actions=[action],
    )

    assert panel.confirmed_money is not None
    assert panel.confirmed_money.amount == 700.0
    assert panel.provisional_sales is not None
    assert panel.provisional_sales.amount == 300.0
    assert panel.growth_opportunities is not None
    assert panel.growth_opportunities.impact_type == "expected_impact"
    assert panel.growth_opportunities.saved_money_claimed is False
    assert panel.grouped_problems.system_checks[0].results_href == "/results?action_id=7&nm_id=101"
    assert panel.grouped_problems.system_checks[0].saved_money_claimed is False


def test_money_source_coverage_missing_and_stale_sources_block_final_metrics() -> None:
    service = MoneyManagementService()
    failed_finance_domain = SimpleNamespace(
        domain="finance",
        latest_status="failed",
        cursor_status="error",
        cursor_last_synced_at=None,
        last_successful_at=datetime(2026, 5, 10, 2, 0, 0),
        latest_finished_at=datetime(2026, 5, 20, 2, 0, 0),
    )
    state = SimpleNamespace(
        health=SimpleNamespace(
            blocked_reasons=["failed_sync_domains"],
            domains=[failed_finance_domain],
        ),
        profit_rows=[SimpleNamespace()],
        control_rows=[],
        price_rows={},
        account_expense_rows=[],
    )

    coverage = service._money_source_coverage(
        state=state,  # type: ignore[arg-type]
        kpis=MoneySummaryKpis(revenue=1000.0, finance_confirmed_revenue=0.0),
        quality=MoneyQuality(finance_reconciliation_status="critical_mismatch"),
        cost_coverage=CostCoverageBlock(can_use_for_operations=False, can_use_for_final_profit=False),
        finance_reconciliation=FinanceReconciliationBlock(
            status="not_available",
            requested_date_from=date(2026, 5, 1),
            requested_date_to=date(2026, 5, 20),
        ),
    )

    by_source = {item.source: item for item in coverage}
    assert by_source["finance_reports_wb"].status == "stale"
    assert "confirmed_money" in by_source["finance_reports_wb"].blocks_calculation
    assert by_source["prices"].status == "missing"
    assert "price_actions" in by_source["prices"].blocks_calculation


def test_money_source_coverage_expenses_are_configured_when_finance_expenses_are_accounted() -> None:
    service = MoneyManagementService()
    synced_at = datetime(2026, 7, 12, 12, 0, 0)
    finance_domain = SimpleNamespace(
        domain="finance",
        latest_status="completed",
        cursor_status="ok",
        cursor_last_synced_at=synced_at,
        last_successful_at=None,
        latest_finished_at=None,
    )
    state = SimpleNamespace(
        health=SimpleNamespace(blocked_reasons=[], domains=[finance_domain]),
        profit_rows=[SimpleNamespace()],
        control_rows=[],
        price_rows={1: SimpleNamespace()},
        account_expense_rows=[SimpleNamespace()],
    )

    coverage = service._money_source_coverage(
        state=state,  # type: ignore[arg-type]
        kpis=MoneySummaryKpis(
            revenue=1000.0,
            finance_confirmed_revenue=1000.0,
            wb_expenses_total=120.0,
            unallocated_expenses=30.0,
        ),
        quality=MoneyQuality(finance_reconciliation_status="matched"),
        cost_coverage=CostCoverageBlock(can_use_for_operations=True, can_use_for_final_profit=True),
        finance_reconciliation=FinanceReconciliationBlock(
            status="matched",
            finance_confirmed_revenue=1000.0,
            requested_date_from=date(2026, 7, 1),
            requested_date_to=date(2026, 7, 12),
        ),
    )

    expenses = {item.source: item for item in coverage}["expenses"]
    assert expenses.source_code == "expenses"
    assert expenses.status == "fresh"
    assert expenses.last_synced_at == synced_at
    assert expenses.blocks_calculation == []


def test_money_grouped_problem_links_data_fix_and_hides_finance_reconciliation_mismatch() -> None:
    service = MoneyManagementService()
    meta = _test_money_meta()
    risk = RiskItem(
        code="open_blocking_dq_issues",
        title="Data blockers exist",
        business_impact="Money cannot be final until blockers are resolved.",
        priority="critical",
    )

    groups = service._money_grouped_problems(
        meta=meta,
        risks=[risk],
        actions=[],
        kpis=MoneySummaryKpis(revenue=1000.0),
        cost_coverage=CostCoverageBlock(can_use_for_operations=False, can_use_for_final_profit=False),
        finance_reconciliation=FinanceReconciliationBlock(
            status="critical_mismatch",
            difference_amount=125.0,
            requested_date_from=meta.date_from,
            requested_date_to=meta.date_to,
        ),
    )

    blocker = groups.data_blockers[0]
    assert blocker.data_fix_href == "/data-fix?code=open_blocking_dq_issues"
    assert blocker.results_href == "/results?problem_code=open_blocking_dq_issues&source_module=finance"
    assert groups.reconciliation == []


def test_money_control_panel_cards_receive_evidence_when_values_are_shown() -> None:
    meta = _test_money_meta()
    summary = MoneySummaryRead(
        meta=meta,
        answer=BusinessAnswer(
            business_status="provisional",
            title="Money summary",
            short_text="Numbers are provisional.",
        ),
        store_answer=StoreAnswer(
            what_is_happening="Sales are visible.",
            where_money_came_from="WB finance and sales.",
            where_money_went="Costs and expenses.",
            where_money_is_now="WB balance and stock.",
        ),
        revenue_sources=RevenueSources(),
        finance_reconciliation=FinanceReconciliationBlock(
            requested_date_from=meta.date_from,
            requested_date_to=meta.date_to,
        ),
        quality=MoneyQuality(),
        kpis=MoneySummaryKpis(revenue=1000.0, finance_confirmed_revenue=700.0),
        money_flow=MoneyFlowBlock(),
        risk_summary=RiskSummary(),
        top_cards=TopCardsBlock(),
        control_panel=MoneyControlPanel(
            confirmed_money=MoneyControlPanelCard(
                code="confirmed_money",
                title="Confirmed money",
                amount=700.0,
                impact_type="confirmed_money",
            )
        ),
    )

    assert summary.control_panel.confirmed_money is not None
    assert summary.control_panel.confirmed_money.evidence_ledger is not None


@pytest.mark.asyncio
async def test_load_runtime_state_dedupes_parallel_inflight_requests(monkeypatch) -> None:
    service = MoneyManagementService()
    service._runtime_cache.clear()
    service._runtime_window_cache.clear()
    service._runtime_inflight.clear()
    calls = 0
    expected = service._runtime_window_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )
    state = MoneyRuntimeState(
        health=SimpleNamespace(),
        profit_rows=[],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={},
        trust_decision=SimpleNamespace(),
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        period_end_balance=None,
        finance_confirmed_revenue_total=Decimal("0"),
        finance_closed_mart_revenue_total=Decimal("0"),
        finance_coverage_date_to=None,
        computed_at=datetime(2026, 5, 31, 12, 0, 0),
        cache_status="miss",
        data_version_hash="hash-1",
    )

    async def fake_compute(_session, *, account_id, date_from, date_to, runtime_version_hash=None):
        nonlocal calls
        assert service._runtime_window_key(account_id=account_id, date_from=date_from, date_to=date_to) == expected
        calls += 1
        await asyncio.sleep(0.01)
        return state

    monkeypatch.setattr(service, "_compute_runtime_state", fake_compute)

    left, right = await asyncio.gather(
        service._load_runtime_state(None, account_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)),
        service._load_runtime_state(None, account_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)),
    )

    assert calls == 1
    assert left is state
    assert right.cache_status == "hit"


def test_action_from_recommendation_falls_back_linked_entity_title_to_vendor_code() -> None:
    service = MoneyManagementService()
    action = SimpleNamespace(
        id=1,
        action_type="LIQUIDATE_STOCK",
        priority="high",
        status="new",
        title="Разгрузить остаток",
        reason_short="",
        reason="Разгрузить остаток",
        what_to_do="Снизить остаток",
        why="Товар заморожен",
        how_to_fix=[],
        expected_effect_amount=1200.0,
        priority_score=15.0,
        required_cash=0.0,
        confidence="medium",
        financial_final=False,
        deadline_hint="",
        deadline_at=None,
        linked_entity={"sku_id": 10, "nm_id": 20, "vendor_code": "SKU-10", "title": ""},
        blocked_reasons=[],
        money_effect={},
        payload={},
    )

    result = service._action_from_recommendation(action)

    assert result.linked_entity["title"] == "SKU-10"


def test_synthesized_row_action_returns_fix_action_for_data_blocked_row() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(
        trust_state=TRUST_STATE_DATA_BLOCKED,
        blocked_reasons=["missing_manual_cost"],
        sku_id=10,
        nm_id=20,
        vendor_code="SKU-10",
        net_profit=125.0,
        ad_spend=0.0,
        stock_value=500.0,
        revenue=1000.0,
        priority_score=1500.0,
        sku_status="PROTECT_STOCK",
    )

    action = service._synthesized_row_action(
        row,
        price_row=SimpleNamespace(safe_price_gap=None, not_computable_reason=None, confidence="medium"),
        purchase_row=SimpleNamespace(status="REORDER", recommended_qty=10, required_cash=1000.0, reason="Need reorder"),
    )

    assert action is not None
    assert action.action_type == "FIX_COST_TRUST"
    assert action.priority == "critical"


def test_synthesized_row_action_returns_price_review_for_trusted_row() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(
        trust_state=TRUST_STATE_TRUSTED,
        blocked_reasons=[],
        sku_id=10,
        nm_id=20,
        vendor_code="SKU-10",
        net_profit=20.0,
        ad_spend=0.0,
        stock_value=500.0,
        revenue=1000.0,
        priority_score=1500.0,
        sku_status="STABLE",
    )

    action = service._synthesized_row_action(
        row,
        price_row=SimpleNamespace(safe_price_gap=-35.0, not_computable_reason=None, confidence="high"),
        purchase_row=None,
    )

    assert action is not None
    assert action.action_type == "PRICE_INCREASE_REVIEW"
    assert action.linked_entity == {"sku_id": 10, "nm_id": 20, "vendor_code": "SKU-10"}


def test_synthesized_row_action_allows_provisional_reorder_for_test_only_row() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=["supplier_cost_not_confirmed"],
        sku_id=10,
        nm_id=20,
        vendor_code="SKU-10",
        net_profit=220.0,
        ad_spend=0.0,
        stock_value=500.0,
        revenue=1000.0,
        priority_score=1500.0,
        sku_status="PROTECT_STOCK",
    )

    action = service._synthesized_row_action(
        row,
        price_row=SimpleNamespace(safe_price_gap=None, not_computable_reason=None, confidence="medium"),
        purchase_row=SimpleNamespace(status="REORDER", recommended_qty=12, required_cash=1200.0, reason="Provisional reorder"),
    )

    assert action is not None
    assert action.action_type == "REORDER"
    assert action.confidence == "medium"


def test_build_card_price_returns_zero_defaults_when_price_missing() -> None:
    service = MoneyManagementService()

    price = service._build_card_price(None)

    assert price.current_price == 0.0
    assert price.current_discounted_price == 0.0
    assert price.break_even_price == 0.0
    assert price.target_margin_price == 0.0
    assert price.safe_price_gap == 0.0
    assert price.safe_price_gap_unit == "RUB"
    assert price.safe_price_gap_kind == "currency_amount"
    assert price.discount == 0
    assert price.status == "not_computable"
    assert price.price_source == ""
    assert price.not_computable_reason == "price_not_loaded"


def test_build_card_price_exposes_gap_as_currency_and_margin_as_percent() -> None:
    service = MoneyManagementService()

    price = service._build_card_price(
        SimpleNamespace(
            current_price=18900.0,
            current_discounted_price=10962.0,
            break_even_price=16360.0,
            target_margin_price=20500.0,
            safe_price_gap=-5398.08,
            estimated_margin_at_current_price=-68.0,
            estimated=False,
            confidence="high",
            price_source="wb_price_snapshot",
            not_computable_reason=None,
        )
    )

    assert price.safe_price_gap == -5398.08
    assert price.safe_price_gap_unit == "RUB"
    assert price.safe_price_gap_kind == "currency_amount"
    assert price.estimated_margin_percent == pytest.approx(-68.0)
    assert price.discount == 42


def test_build_card_stock_returns_zero_defaults() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(stock_qty=None, stock_value=None, days_of_stock=None, trust_state=TRUST_STATE_TEST_ONLY, sku_status="STABLE")

    stock = service._build_card_stock(row, purchase_row=None)

    assert stock.quantity == 0.0
    assert stock.quantity_full == 0.0
    assert stock.stock_value == 0.0
    assert stock.days_of_stock == 0.0
    assert stock.sales_velocity_daily == 0.0
    assert stock.overstock_value == 0.0
    assert stock.stock_status == "unknown"
    assert stock.in_transit_qty == 0.0


def test_build_card_stock_exposes_sales_velocity_and_overstock_value() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(
        stock_qty=407.0,
        stock_value=1168548.0,
        days_of_stock=91.88074254640915,
        trust_state=TRUST_STATE_TRUSTED,
        sku_status="LIQUIDATE",
    )
    profit_row = SimpleNamespace(cost_truth_level="supplier_confirmed", stock_value=1168548.0)
    purchase_row = SimpleNamespace(in_transit_qty=20.0, sales_velocity_daily=4.43)

    stock = service._build_card_stock(row, profit_row=profit_row, purchase_row=purchase_row)

    assert stock.stock_value == pytest.approx(1168548.0)
    assert stock.sales_velocity_daily == pytest.approx(4.43)
    assert stock.overstock_value == pytest.approx(1168548.0)
    assert stock.stock_status == "overstock"


def test_build_card_stock_uses_purchase_plan_to_mark_overstock() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(
        stock_qty=167.0,
        stock_value=None,
        days_of_stock=None,
        trust_state=TRUST_STATE_TEST_ONLY,
        sku_status="WATCH",
    )
    profit_row = SimpleNamespace(cost_truth_level="operator_baseline", estimated_cogs=0.0, net_units=0, stock_value=None)
    purchase_row = SimpleNamespace(status="LIQUIDATE", in_transit_qty=5.0, sales_velocity_daily=0.0)

    stock = service._build_card_stock(row, profit_row=profit_row, purchase_row=purchase_row)

    assert stock.stock_status == "overstock"


def test_build_card_stock_marks_blocked_wait_data_sku_as_unknown() -> None:
    service = MoneyManagementService()
    row = SimpleNamespace(
        stock_qty=167.0,
        stock_value=None,
        days_of_stock=None,
        trust_state=TRUST_STATE_DATA_BLOCKED,
        sku_status="DATA_BLOCKED",
    )
    profit_row = SimpleNamespace(cost_truth_level="operator_baseline", estimated_cogs=0.0, net_units=0, stock_value=None)
    purchase_row = SimpleNamespace(status="WAIT_DATA", in_transit_qty=5.0, sales_velocity_daily=0.0)

    stock = service._build_card_stock(row, profit_row=profit_row, purchase_row=purchase_row)

    assert stock.stock_status == "unknown"


def test_allocate_article_count_metric_by_sku_uses_revenue_weights() -> None:
    service = MoneyManagementService()
    article_rows = [
        (SimpleNamespace(sku_id=1), SimpleNamespace(realized_revenue=80.0, net_units=8), None),
        (SimpleNamespace(sku_id=2), SimpleNamespace(realized_revenue=20.0, net_units=2), None),
    ]

    allocations = service._allocate_article_count_metric_by_sku(article_rows=article_rows, total_value=10)

    assert allocations == {1: 8, 2: 2}


def test_build_card_money_returns_zero_defaults_for_optional_metrics() -> None:
    service = MoneyManagementService()
    profit_row = SimpleNamespace(
        realized_revenue=1500.0,
        for_pay=None,
        commission=None,
        acquiring_fee=None,
        logistics=None,
        paid_acceptance=None,
        storage=None,
        penalties=None,
        deductions=None,
        additional_payments=None,
        finance_rows=0,
        estimated_cogs=None,
        net_units=0,
        has_real_manual_cost=False,
        estimated_profit=None,
        ad_spend=None,
        margin_percent=None,
        roi_percent=None,
        cost_truth_level=None,
    )
    row = SimpleNamespace(ad_spend=None, drr_percent=None, stock_value=None, trust_state=TRUST_STATE_TEST_ONLY)

    money = service._build_card_money(profit_row, row, price_row=None)

    assert money.revenue == 1500.0
    assert money.for_pay == 0.0
    assert money.wb_expenses.commission == 0.0
    assert money.ads.spend == 0.0
    assert money.ads.drr_percent == 0.0
    assert money.cogs.unit_cost == 0.0
    assert money.cogs.estimated_cogs == 0.0
    assert money.profit.before_ads == 1500.0
    assert money.profit.after_ads == 1500.0
    assert money.profit.margin_after_ads_percent == 100.0
    assert money.profit.roi_after_ads_percent == 0.0
    assert money.stock_value == 0.0


def test_build_quality_caps_ads_allocation_and_marks_overallocated() -> None:
    service = MoneyManagementService()

    quality = service._build_quality(
        health=SimpleNamespace(supplier_confirmed_revenue_coverage_percent=0.0),
        ads_metrics={
            "raw_ads_allocated": 1110.0,
            "capped_ads_allocated_spend": 1000.0,
            "ads_allocation_percent_raw": 111.38,
            "ads_allocation_percent_capped": 100.0,
            "ads_overallocated_spend": 44068.7,
            "final_profit_allowed": False,
        },
        revenue_sources=RevenueSources(
            operational_revenue=1000.0,
            finance_confirmed_revenue=850.0,
            mart_revenue=1000.0,
            supplier_cost_confirmed_revenue=0.0,
            difference_amount=150.0,
            difference_percent=15.0,
            source_of_truth="mixed",
            reconciliation_status="critical_mismatch",
        ),
    )

    assert quality.ads_allocation_percent == 100.0
    assert quality.ads_allocation_percent_capped == 100.0
    assert quality.ads_overallocated_spend == 44068.7
    assert quality.raw_ads_allocated_spend == 1110.0
    assert quality.capped_ads_allocated_spend == 1000.0
    assert quality.final_profit_allowed is False
    assert quality.final_finance_ready is False


def test_ads_allocation_metrics_caps_duplicate_raw_allocation() -> None:
    service = MoneyManagementService()

    metrics = service._ads_allocation_metrics(
        ads_source_spend=Decimal("1000"),
        mart_ads_allocated_spend=Decimal("4000"),
        ads_allocatable_source_spend=Decimal("1000"),
    )

    assert metrics["raw_ads_allocated"] == Decimal("4000")
    assert metrics["capped_ads_allocated_spend"] == Decimal("1000")
    assert metrics["ads_allocated_spend"] == Decimal("1000")
    assert metrics["ads_overallocated_spend"] == Decimal("3000")
    assert metrics["ads_unallocated_spend"] == Decimal("0")
    assert metrics["ads_allocation_status"] == "overallocated"
    assert metrics["final_profit_allowed"] is False


def test_cost_coverage_from_health_exposes_operator_baseline_as_operational_not_final() -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        revenue_with_cost=Decimal("996"),
        revenue_without_cost=Decimal("4"),
        revenue_with_real_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=99.6,
        supplier_confirmed_revenue_coverage_percent=0.0,
        cost_trust_policy="operator_baseline",
    )

    block = service._cost_coverage_from_health(health)

    assert block.operational_cost_coverage_percent == 99.6
    assert block.supplier_confirmed_cost_coverage_percent == 0.0
    assert block.business_accepted_cost_coverage_percent == 99.6
    assert block.can_use_for_operations is True
    assert block.can_use_for_final_profit is False


def test_summary_answer_is_provisional_for_finance_mismatch_even_when_health_trusted() -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=True,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TRUSTED,
        blocked_reasons=[],
    )
    revenue_sources = RevenueSources(reconciliation_status="critical_mismatch")
    quality = SimpleNamespace(
        supplier_cost_coverage_percent=99.6,
        ads_overallocated_spend=0.0,
        ads_allocation_percent_capped=100.0,
    )

    answer = service._summary_answer(
        health,
        revenue_sources=revenue_sources,
        quality=quality,
        unallocated_expense_ratio_percent=4.0,
    )

    assert answer.business_status == "provisional"
    assert "расхождение между отчетом WB и продажами" in answer.main_problem


def test_summary_answer_owner_approved_final_stays_provisional_until_finance_matches() -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=True,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TRUSTED,
        blocked_reasons=[],
        financial_final=True,
        cost_trust_policy="owner_approved_final",
    )
    revenue_sources = RevenueSources(reconciliation_status="warning_mismatch")
    quality = SimpleNamespace(
        supplier_cost_coverage_percent=99.6,
        ads_overallocated_spend=0.0,
        ads_allocation_percent=100.0,
        ads_allocation_percent_capped=100.0,
    )

    answer = service._summary_answer(
        health,
        revenue_sources=revenue_sources,
        quality=quality,
        unallocated_expense_ratio_percent=4.0,
    )

    assert answer.business_status == "provisional"
    assert "режиме временного ручного подтверждения" in answer.title.lower()
    assert "расхождение между отчетом WB и продажами" in answer.main_problem


def test_article_summary_block_uses_audit_operations_for_cancel_rate() -> None:
    service = MoneyManagementService()
    article_rows = [
        (
            SimpleNamespace(stock_qty=Decimal("3"), days_of_stock=12, trust_state=TRUST_STATE_TEST_ONLY, sku_status="STABLE"),
            SimpleNamespace(
                realized_revenue=Decimal("100"),
                estimated_profit=Decimal("40"),
                ad_spend=Decimal("10"),
                gross_units=5,
                return_units=1,
                estimated_cogs=Decimal("20"),
                net_units=2,
                cost_truth_level="operator_baseline",
            ),
            None,
        )
    ]
    audit = SimpleNamespace(
        operations=SimpleNamespace(
            orders_count=32,
            cancelled_orders_count=21,
            sales_count=25,
            returns_count=4,
        )
    )

    block = service._article_summary_block(
        nm_id=123,
        title="Article",
        article_rows=article_rows,
        ads_source_spend=Decimal("12"),
        decision="watch",
        audit=audit,
    )

    assert block.cancel_rate_percent == 65.625
    assert block.return_rate_percent == 16.0


def test_merge_grouped_actions_groups_duplicate_article_actions() -> None:
    service = MoneyManagementService()
    actions = [
        NextActionRead(
            id=1,
            action_type="LIQUIDATE_STOCK",
            category="release_cash",
            action_group="business",
            priority="high",
            status="new",
            title="A",
            what_to_do="Do A",
            why="Because A",
            expected_effect_amount=100.0,
            confidence="medium",
            linked_entity={"sku_id": 10, "nm_id": 77, "vendor_code": "A"},
            affected_nm_ids=[77],
            affected_sku_ids=[10],
            money_effect={"affected_stock_value": 100.0, "expected_cash_release": 100.0},
        ),
        NextActionRead(
            id=2,
            action_type="LIQUIDATE_STOCK",
            category="release_cash",
            action_group="business",
            priority="high",
            status="new",
            title="B",
            what_to_do="Do B",
            why="Because B",
            expected_effect_amount=150.0,
            confidence="medium",
            linked_entity={"sku_id": 11, "nm_id": 77, "vendor_code": "B"},
            affected_nm_ids=[77],
            affected_sku_ids=[11],
            money_effect={"affected_stock_value": 150.0, "expected_cash_release": 150.0},
        ),
    ]

    grouped, raw_total = service._merge_grouped_actions(actions, group_by="article")

    assert raw_total == 2
    assert len(grouped) == 1
    assert grouped[0].expected_effect_amount == 250.0
    assert grouped[0].required_cash == 0.0
    assert grouped[0].money_effect["affected_stock_value"] == 250.0
    assert grouped[0].money_effect["expected_cash_release"] == 250.0
    assert grouped[0].affected_nm_ids == [77]
    assert grouped[0].affected_sku_ids == [10, 11]


@pytest.mark.asyncio
async def test_today_actions_limits_owner_focus_actions_to_ten_by_default() -> None:
    service = MoneyManagementService()
    service._load_runtime_state = AsyncMock(
        return_value=SimpleNamespace(
            action_reads=[
                SimpleNamespace(
                    id=index,
                    action_type="LIQUIDATE_STOCK" if index % 2 == 0 else "REORDER",
                    priority="critical",
                    status="new",
                    title=f"Action {index}",
                    what_to_do="Do it",
                    why="Because",
                    how_to_fix=[],
                    expected_effect_amount=100000.0 - index,
                    required_cash=0.0,
                    confidence="medium",
                    deadline_hint="",
                    linked_entity={"sku_id": index, "nm_id": 1000 + index, "vendor_code": f"SKU-{index}"},
                    blocked_reasons=[],
                    money_effect={"affected_stock_value": 100000.0 - index, "expected_cash_release": 100000.0 - index},
                    payload={},
                    deadline_at=None,
                    financial_final=True,
                    category="release_cash" if index % 2 == 0 else "growth",
                )
                for index in range(1, 16)
            ]
        )
    )

    page = await service.today_actions(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert len(page.owner_focus_actions) <= 10
    assert sum(1 for item in page.owner_focus_actions if item.priority == "critical") <= 10


@pytest.mark.asyncio
async def test_today_actions_owner_focus_excludes_blocked_provisional_business_actions() -> None:
    service = MoneyManagementService()
    service._load_runtime_state = AsyncMock(
        return_value=SimpleNamespace(
            action_reads=[
                SimpleNamespace(
                    id=1,
                    action_type="FIX_COST_TRUST",
                    priority="low",
                    status="new",
                    title="Fix cost",
                    what_to_do="Load cost",
                    why="Missing cost",
                    how_to_fix=[],
                    expected_effect_amount=0.0,
                    required_cash=0.0,
                    confidence="high",
                    deadline_hint="",
                    linked_entity={"sku_id": 1, "nm_id": 101, "vendor_code": "SKU-101"},
                    blocked_reasons=["missing_manual_cost", "finance_not_confirmed"],
                    money_effect={},
                    payload={},
                    deadline_at=None,
                    financial_final=False,
                    category="data_fix",
                ),
                SimpleNamespace(
                    id=2,
                    action_type="LIQUIDATE_STOCK",
                    priority="high",
                    status="new",
                    title="Liquidate",
                    what_to_do="Promo",
                    why="Frozen stock",
                    how_to_fix=[],
                    expected_effect_amount=250000.0,
                    required_cash=0.0,
                    confidence="high",
                    deadline_hint="",
                    linked_entity={"sku_id": 2, "nm_id": 102, "vendor_code": "SKU-102"},
                    blocked_reasons=["finance_not_confirmed"],
                    money_effect={"affected_stock_value": 250000.0, "expected_cash_release": 250000.0},
                    payload={},
                    deadline_at=None,
                    financial_final=False,
                    category="release_cash",
                ),
            ]
        )
    )

    page = await service.today_actions(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert [item.action_type for item in page.owner_focus_actions] == ["FIX_COST_TRUST"]
    assert page.items[0].action_type == "LIQUIDATE_STOCK"


def test_finance_reconciliation_excludes_open_operational_period_from_mismatch() -> None:
    service = MoneyManagementService()
    operational_rows = [
        SimpleNamespace(
            srid="SRID-1",
            nm_id=101,
            date=datetime(2026, 5, 10, 10, 0, 0),
            last_change_date=datetime(2026, 5, 10, 11, 0, 0),
            finished_price=Decimal("100"),
            price_with_disc=None,
            total_price=None,
            for_pay=Decimal("90"),
            is_cancel=False,
        ),
        SimpleNamespace(
            srid="SRID-2",
            nm_id=101,
            date=datetime(2026, 5, 18, 10, 0, 0),
            last_change_date=datetime(2026, 5, 18, 11, 0, 0),
            finished_price=Decimal("60"),
            price_with_disc=None,
            total_price=None,
            for_pay=Decimal("54"),
            is_cancel=False,
        ),
    ]
    finance_rows = [
        SimpleNamespace(
            rrd_id=1,
            srid="SRID-1",
            nm_id=101,
            rr_date=date(2026, 5, 10),
            sale_dt=datetime(2026, 5, 10, 10, 0, 0),
            retail_amount=Decimal("100"),
            for_pay=Decimal("90"),
            doc_type_name="Продажа",
            is_return_operation=False,
            is_reconcilable=True,
        )
    ]

    block = service._build_finance_reconciliation(
        requested_date_from=date(2026, 5, 1),
        requested_date_to=date(2026, 5, 20),
        closed_finance_date_from=date(2026, 5, 1),
        closed_finance_date_to=date(2026, 5, 10),
        operational_rows=operational_rows,
        finance_rows=finance_rows,
        account_level_expense_total=Decimal("0"),
    )

    assert block.status == "matched"
    assert block.operational_revenue == 100.0
    assert block.finance_confirmed_revenue == 100.0
    assert block.difference_amount == 0.0
    assert block.open_operational_period_revenue == 60.0
    assert block.classified_difference.expected_lag == 60.0


def test_finance_reconciliation_return_row_reduces_revenue_correctly() -> None:
    service = MoneyManagementService()
    operational_rows = [
        SimpleNamespace(
            srid="SRID-SALE",
            nm_id=202,
            date=datetime(2026, 5, 10, 10, 0, 0),
            last_change_date=datetime(2026, 5, 10, 11, 0, 0),
            finished_price=Decimal("100"),
            price_with_disc=None,
            total_price=None,
            for_pay=Decimal("90"),
            is_cancel=False,
        ),
        SimpleNamespace(
            srid="SRID-RETURN",
            nm_id=202,
            date=datetime(2026, 5, 12, 10, 0, 0),
            last_change_date=datetime(2026, 5, 12, 11, 0, 0),
            finished_price=Decimal("30"),
            price_with_disc=None,
            total_price=None,
            for_pay=Decimal("-27"),
            is_cancel=True,
        ),
    ]
    finance_rows = [
        SimpleNamespace(
            rrd_id=11,
            srid="SRID-SALE",
            nm_id=202,
            rr_date=date(2026, 5, 10),
            sale_dt=datetime(2026, 5, 10, 10, 0, 0),
            retail_amount=Decimal("100"),
            for_pay=Decimal("90"),
            doc_type_name="Продажа",
            is_return_operation=False,
            is_reconcilable=True,
        ),
        SimpleNamespace(
            rrd_id=12,
            srid="SRID-RETURN",
            nm_id=202,
            rr_date=date(2026, 5, 12),
            sale_dt=datetime(2026, 5, 12, 10, 0, 0),
            retail_amount=Decimal("30"),
            for_pay=Decimal("-27"),
            doc_type_name="Возврат",
            is_return_operation=True,
            is_reconcilable=True,
        ),
    ]

    block = service._build_finance_reconciliation(
        requested_date_from=date(2026, 5, 1),
        requested_date_to=date(2026, 5, 20),
        closed_finance_date_from=date(2026, 5, 1),
        closed_finance_date_to=date(2026, 5, 20),
        operational_rows=operational_rows,
        finance_rows=finance_rows,
        account_level_expense_total=Decimal("0"),
    )

    assert block.status == "matched"
    assert block.operational_revenue == 70.0
    assert block.finance_confirmed_revenue == 70.0
    assert block.difference_amount == 0.0


def test_finance_reconciliation_keeps_account_level_expense_outside_revenue_mismatch() -> None:
    service = MoneyManagementService()
    operational_rows = [
        SimpleNamespace(
            srid="SRID-OK",
            nm_id=303,
            date=datetime(2026, 5, 10, 10, 0, 0),
            last_change_date=datetime(2026, 5, 10, 11, 0, 0),
            finished_price=Decimal("100"),
            price_with_disc=None,
            total_price=None,
            for_pay=Decimal("90"),
            is_cancel=False,
        )
    ]
    finance_rows = [
        SimpleNamespace(
            rrd_id=21,
            srid="SRID-OK",
            nm_id=303,
            rr_date=date(2026, 5, 10),
            sale_dt=datetime(2026, 5, 10, 10, 0, 0),
            retail_amount=Decimal("100"),
            for_pay=Decimal("90"),
            doc_type_name="Продажа",
            is_return_operation=False,
            is_reconcilable=True,
        )
    ]

    block = service._build_finance_reconciliation(
        requested_date_from=date(2026, 5, 1),
        requested_date_to=date(2026, 5, 20),
        closed_finance_date_from=date(2026, 5, 1),
        closed_finance_date_to=date(2026, 5, 20),
        operational_rows=operational_rows,
        finance_rows=finance_rows,
        account_level_expense_total=Decimal("250"),
    )

    assert block.status == "matched"
    assert block.difference_amount == 0.0
    assert block.classified_difference.account_level_expense == 250.0
    assert block.classified_difference.unknown == 0.0


def test_finance_reconciliation_unknown_above_three_percent_is_critical() -> None:
    service = MoneyManagementService()
    operational_rows = [
        SimpleNamespace(
            srid="SRID-DIFF",
            nm_id=404,
            date=datetime(2026, 5, 10, 10, 0, 0),
            last_change_date=datetime(2026, 5, 10, 11, 0, 0),
            finished_price=Decimal("100"),
            price_with_disc=None,
            total_price=None,
            for_pay=Decimal("90"),
            is_cancel=False,
        )
    ]
    finance_rows = [
        SimpleNamespace(
            rrd_id=31,
            srid="SRID-DIFF",
            nm_id=404,
            rr_date=date(2026, 5, 10),
            sale_dt=datetime(2026, 5, 10, 10, 0, 0),
            retail_amount=Decimal("60"),
            for_pay=Decimal("54"),
            doc_type_name="Продажа",
            is_return_operation=False,
            is_reconcilable=True,
        )
    ]

    block = service._build_finance_reconciliation(
        requested_date_from=date(2026, 5, 1),
        requested_date_to=date(2026, 5, 20),
        closed_finance_date_from=date(2026, 5, 1),
        closed_finance_date_to=date(2026, 5, 20),
        operational_rows=operational_rows,
        finance_rows=finance_rows,
        account_level_expense_total=Decimal("0"),
    )

    assert block.status == "critical_mismatch"
    assert block.difference_amount == 40.0
    assert block.classified_difference.unknown == 40.0


def test_direct_article_expenses_are_mapped_from_profit_row_values() -> None:
    service = MoneyManagementService()
    profit_row = SimpleNamespace(
        realized_revenue=1500.0,
        for_pay=1300.0,
        commission=120.0,
        acquiring_fee=15.0,
        logistics=20.0,
        paid_acceptance=5.0,
        storage=10.0,
        penalties=3.0,
        deductions=7.0,
        additional_payments=0.0,
        finance_rows=2,
        estimated_cogs=500.0,
        net_units=5,
        has_real_manual_cost=True,
        estimated_profit=820.0,
        ad_spend=25.0,
        margin_percent=54.6,
        roi_percent=164.0,
        cost_truth_level="supplier_confirmed",
    )
    row = SimpleNamespace(
        ad_spend=25.0,
        raw_ad_spend=25.0,
        capped_ad_spend=25.0,
        overallocated_ad_spend=0.0,
        unallocated_ad_spend=0.0,
        drr_percent=1.67,
        stock_value=0.0,
        trust_state=TRUST_STATE_TRUSTED,
    )

    money = service._build_card_money(
        profit_row,
        row,
        price_row=None,
        account_level_expense_total=Decimal("0"),
        allocated_overhead=Decimal("0"),
    )
    expense_breakdown = service._article_expense_breakdown(money.wb_expenses)

    assert expense_breakdown.direct_expenses.commission == 120.0
    assert expense_breakdown.direct_expenses.logistics == 20.0
    assert expense_breakdown.direct_expenses.storage == 10.0
    assert expense_breakdown.unallocated_warning is False


def test_account_level_expense_rows_are_classified_into_overhead_buckets() -> None:
    service = MoneyManagementService()
    rows = [
        SimpleNamespace(
            storage=Decimal("10"),
            deductions=Decimal("20"),
            penalties=Decimal("5"),
            logistics=Decimal("7"),
            paid_acceptance=Decimal("3"),
            total_expense=Decimal("60"),
        )
    ]

    breakdown = service._account_level_expense_breakdown_from_rows(rows)

    assert breakdown.storage == 10.0
    assert breakdown.deductions == 20.0
    assert breakdown.penalties == 5.0
    assert breakdown.logistics_unallocated == 10.0
    assert breakdown.other == 15.0


@pytest.mark.asyncio
async def test_account_level_expense_rows_skips_raw_finance_fallback_when_mart_has_non_zero_totals(monkeypatch) -> None:
    service = MoneyManagementService()
    session = _FakeAsyncSession(
        [
            [
                SimpleNamespace(
                    logistics=Decimal("10"),
                    storage=Decimal("5"),
                    deductions=Decimal("3"),
                    penalties=Decimal("1"),
                    total_expense=Decimal("19"),
                    wb_logistics=Decimal("10"),
                    wb_logistics_rebill=Decimal("0"),
                    marketing_deduction=Decimal("0"),
                )
            ]
        ]
    )
    raw_fallback = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "_raw_finance_expense_entries", raw_fallback)

    rows = await service._account_level_expense_rows(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert len(rows) == 1
    assert raw_fallback.await_count == 0


@pytest.mark.asyncio
async def test_summary_finance_category_totals_skips_raw_fallback_when_mart_totals_are_non_zero(monkeypatch) -> None:
    service = MoneyManagementService()
    raw_fallback = AsyncMock(return_value=[])
    monkeypatch.setattr(service, "_raw_finance_expense_entries", raw_fallback)

    totals = await service._summary_finance_category_totals(
        _FakeAsyncSession([]),  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        profit_rows=[SimpleNamespace(wb_logistics=Decimal("12"), payment_processing=Decimal("3"))],
        account_expense_rows=[],
    )

    assert totals["wb_logistics"] == Decimal("12")
    assert totals["payment_processing"] == Decimal("3")
    assert raw_fallback.await_count == 0


def test_article_expense_breakdown_warns_when_direct_zero_but_account_level_positive() -> None:
    service = MoneyManagementService()
    breakdown = service._article_expense_breakdown(
        SimpleNamespace(
            commission=0.0,
            acquiring_fee=0.0,
            logistics=0.0,
            paid_acceptance=0.0,
            storage=0.0,
            penalties=0.0,
            deductions=0.0,
            additional_payments=0.0,
            direct=0.0,
            account_level=250.0,
            allocated_overhead=50.0,
            unallocated=200.0,
            status="account_level_overhead_only",
        )
    )

    assert breakdown.unallocated_warning is True
    assert breakdown.not_linked_reason == "строки финансового отчета не содержат номера артикула или штрихкода либо относятся к расходам магазина целиком"
    assert "общих расходах магазина" in breakdown.message


def test_store_expenses_waterfall_marks_direct_zero_plus_account_level_as_needs_review() -> None:
    service = MoneyManagementService()
    waterfall = service._store_expenses_waterfall(
        profit_rows=[
            SimpleNamespace(
                commission=0.0,
                acquiring_fee=0.0,
                logistics=0.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
            )
        ],
        account_expense_rows=[
            SimpleNamespace(
                storage=Decimal("12"),
                deductions=Decimal("8"),
                penalties=Decimal("0"),
                logistics=Decimal("5"),
                paid_acceptance=Decimal("0"),
                total_expense=Decimal("30"),
            )
        ],
        unallocated_expenses=Decimal("30"),
    )

    assert waterfall.allocation_status == "needs_review"
    assert waterfall.unallocated_expenses == 30.0
    assert "общие расходы магазина" in waterfall.message


@pytest.mark.asyncio
async def test_expense_breakdown_totals_equal_item_sums_and_unclassified_is_visible(monkeypatch) -> None:
    service = MoneyManagementService()
    session = _FakeAsyncSession(results=[])
    expense_breakdown = ExpenseBreakdownSummaryRead(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="category",
        include_unallocated=True,
        revenue_final=420.0,
        net_profit_after_all_expenses=235.0,
        seller_cogs=40.0,
        seller_other_expense=10.0,
        ad_spend_final=15.0,
        additional_income=5.0,
        total_expenses=190.0,
        total_wb_expenses=125.0,
        total_seller_expenses=50.0,
        total_ad_expenses=15.0,
        logistics_total=100.0,
        logistics_share_base_kind="wb_expenses",
        logistics_share_base_amount=125.0,
        logistics_share_percent=80.0,
        data_version_hash="summary-hash-1",
        source_of_truth="finance_report",
        items=[
            {"group_key": "wb_logistics", "label": "Логистика WB", "amount": 100.0, "share_percent": 52.63, "category": "wb_logistics", "source": "finance_report", "is_final": True, "row_count": 2},
            {"group_key": "storage", "label": "Хранение", "amount": 20.0, "share_percent": 10.53, "category": "storage", "source": "finance_report", "is_final": True, "row_count": 1},
            {"group_key": "unclassified", "label": "Прочее WB", "amount": 5.0, "share_percent": 2.63, "category": "unclassified", "source": "finance_report", "is_final": True, "row_count": 1},
            {"group_key": "seller_cogs", "label": "Себестоимость продавца", "amount": 40.0, "share_percent": 21.05, "category": "seller_cogs", "source": "manual_cost", "is_final": False, "row_count": 0},
            {"group_key": "seller_other_expense", "label": "Прочие расходы продавца", "amount": 10.0, "share_percent": 5.26, "category": "seller_other_expense", "source": "manual_cost", "is_final": False, "row_count": 0},
            {"group_key": "ads_operational", "label": "Реклама / продвижение", "amount": 15.0, "share_percent": 7.89, "category": "ads_operational", "source": "ads_api", "is_final": False, "row_count": 0},
        ],
    )
    profit_cascade = ProfitCascadeRead(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        source_of_truth="finance_report",
        data_version_hash="summary-hash-1",
        cascade={
            "totals": {
                "gross_revenue": 420.0,
                "seller_cogs": 40.0,
                "seller_other_expense": 10.0,
                "total_seller_expenses": 50.0,
                "total_wb_expenses": 125.0,
                "total_ad_expenses": 15.0,
                "additional_income": 5.0,
                "net_profit_after_all_expenses": 235.0,
                "logistics_total": 100.0,
                "logistics_share_percent": 80.0,
            }
        },
    )
    monkeypatch.setattr(
        service,
        "summary",
        AsyncMock(
            return_value=_summary_stub(
                account_id=1,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 20),
                expense_breakdown=expense_breakdown,
                profit_cascade=profit_cascade,
                kpis=MoneySummaryKpis(
                    revenue=420.0,
                    revenue_final=420.0,
                    seller_cogs=40.0,
                    seller_other_expense=10.0,
                    ad_spend_final=15.0,
                    additional_income=5.0,
                    net_profit_after_all_expenses=235.0,
                ),
            )
        ),
    )

    result = await service.expense_breakdown(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="category",
        include_unallocated=True,
    )

    assert result.total_expenses == pytest.approx(190.0)
    assert sum(item.amount for item in result.items) == pytest.approx(190.0)
    assert any(item.category == "unclassified" and item.amount == pytest.approx(5.0) for item in result.items)
    assert result.net_profit_after_all_expenses == pytest.approx(235.0)
    assert result.revenue_final == pytest.approx(420.0)
    assert result.total_wb_expenses == pytest.approx(125.0)
    assert result.total_seller_expenses == pytest.approx(50.0)
    assert result.total_ad_expenses == pytest.approx(15.0)
    assert result.data_version_hash == "summary-hash-1"
    assert result.source_of_truth == "finance_report"
    assert result.logistics_share_base_kind == "wb_expenses"
    assert result.logistics_share_base_amount == pytest.approx(125.0)
    assert result.logistics_share_percent == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_expense_totals_fall_back_to_account_level_when_row_level_is_empty(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(service, "_raw_finance_expense_entries", AsyncMock(return_value=[]))
    session = _FakeAsyncSession(
        results=[
            (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")),
            (Decimal("125"), Decimal("25"), Decimal("100"), Decimal("20")),
            (Decimal("40"), Decimal("10"), Decimal("15")),
        ]
    )

    totals = await service._expense_totals(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        include_unallocated=True,
    )

    assert totals["finance_mode"] == "account_level"
    assert totals["total_wb_expenses"] == Decimal("125")
    assert totals["finance_ad_expenses"] == Decimal("25")
    assert totals["total_ad_expenses"] == Decimal("40")
    assert totals["logistics_total"] == Decimal("120")


@pytest.mark.asyncio
async def test_expense_breakdown_falls_back_to_account_level_rows(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(
        service,
        "summary",
        AsyncMock(
            return_value=_summary_stub(
                account_id=1,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 20),
                expense_breakdown=ExpenseBreakdownSummaryRead(
                    account_id=1,
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 5, 20),
                    total_expenses=190.0,
                    total_wb_expenses=125.0,
                    total_seller_expenses=50.0,
                    total_ad_expenses=15.0,
                    logistics_total=100.0,
                    logistics_share_base_kind="wb_expenses",
                    logistics_share_base_amount=125.0,
                    logistics_share_percent=80.0,
                ),
                profit_cascade=ProfitCascadeRead(
                    account_id=1,
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 5, 20),
                    source_of_truth="finance_report",
                    data_version_hash="summary-hash-2",
                    cascade={
                        "totals": {
                            "gross_revenue": 420.0,
                            "seller_cogs": 40.0,
                            "seller_other_expense": 10.0,
                            "total_seller_expenses": 50.0,
                            "total_wb_expenses": 125.0,
                            "total_ad_expenses": 15.0,
                            "additional_income": 0.0,
                            "net_profit_after_all_expenses": 230.0,
                            "logistics_total": 100.0,
                            "logistics_share_percent": 80.0,
                        }
                    },
                ),
                kpis=MoneySummaryKpis(
                    revenue=420.0,
                    revenue_final=420.0,
                    seller_cogs=40.0,
                    seller_other_expense=10.0,
                    ad_spend_final=15.0,
                    net_profit_after_all_expenses=230.0,
                ),
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_expense_totals",
        AsyncMock(
            return_value={
                "total_expenses": Decimal("190"),
                "total_wb_expenses": Decimal("125"),
                "total_seller_expenses": Decimal("50"),
                "total_ad_expenses": Decimal("15"),
                "logistics_total": Decimal("100"),
                "finance_ad_expenses": Decimal("0"),
                "finance_mode": "account_level",
            }
        ),
    )
    monkeypatch.setattr(
        service,
        "_account_level_expense_rows",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    stat_date=date(2026, 5, 10),
                    wb_logistics=Decimal("100"),
                    wb_logistics_rebill=Decimal("0"),
                    storage=Decimal("20"),
                    marketing_deduction=Decimal("0"),
                    other_wb_expenses=Decimal("5"),
                    total_wb_expenses=Decimal("125"),
                    ad_spend_finance=Decimal("0"),
                )
            ]
        ),
    )
    session = _FakeAsyncSession(results=[])

    result = await service.expense_breakdown(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="source",
        include_unallocated=True,
    )

    assert result.total_wb_expenses == pytest.approx(125.0)
    assert result.total_seller_expenses == pytest.approx(50.0)
    assert result.total_ad_expenses == pytest.approx(15.0)
    assert any(item.group_key == "finance_report" and item.amount == pytest.approx(125.0) for item in result.items)
    assert any(item.group_key == "manual_cost" and item.amount == pytest.approx(50.0) for item in result.items)
    assert any(item.group_key == "ads_api" and item.amount == pytest.approx(15.0) for item in result.items)
    assert result.logistics_share_percent == pytest.approx(80.0)


@pytest.mark.asyncio
async def test_expense_logistics_groups_rows_by_derived_logistics_type(monkeypatch) -> None:
    service = MoneyManagementService()
    session = _FakeAsyncSession(
        results=[
            [
                ("wb_logistics", Decimal("60"), 1),
                ("wb_logistics_rebill", Decimal("30"), 3),
            ],
            [
                ("delivery_to_client", Decimal("60"), 1),
                ("return_from_client", Decimal("15"), 1),
                ("cancellation_to_client", Decimal("10"), 1),
                ("defect_return", Decimal("5"), 1),
            ],
            [],
            [],
            [
                (10, 1001, "SKU-10", "BAR-10", Decimal("60"), 1),
                (11, 1002, "SKU-11", "BAR-11", Decimal("15"), 1),
                (12, 1003, "SKU-12", "BAR-12", Decimal("5"), 1),
            ],
            [
                (1001, Decimal("60"), 1),
                (1002, Decimal("15"), 1),
                (1003, Decimal("5"), 1),
                (None, Decimal("10"), 1),
            ],
            [
                (date(2026, 5, 10), Decimal("60"), 1),
                (date(2026, 5, 11), Decimal("15"), 1),
                (date(2026, 5, 12), Decimal("10"), 1),
                (date(2026, 5, 13), Decimal("5"), 1),
            ],
        ]
    )
    monkeypatch.setattr(
        service,
        "summary",
        AsyncMock(
            return_value=_summary_stub(
                account_id=1,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 20),
                expense_breakdown=ExpenseBreakdownSummaryRead(
                    account_id=1,
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 5, 20),
                    total_expenses=200.0,
                    total_wb_expenses=90.0,
                    total_seller_expenses=0.0,
                    total_ad_expenses=0.0,
                    logistics_total=90.0,
                    logistics_share_base_kind="wb_expenses",
                    logistics_share_base_amount=90.0,
                    logistics_share_percent=100.0,
                ),
                profit_cascade=ProfitCascadeRead(
                    account_id=1,
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 5, 20),
                    source_of_truth="finance_report",
                    data_version_hash="summary-hash-3",
                    cascade={"totals": {"total_wb_expenses": 90.0, "total_seller_expenses": 0.0, "total_ad_expenses": 0.0, "logistics_total": 90.0}},
                ),
                kpis=MoneySummaryKpis(revenue=0.0),
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_expense_totals",
        AsyncMock(
            return_value={
                "total_expenses": Decimal("200"),
                "total_wb_expenses": Decimal("90"),
                "total_seller_expenses": Decimal("0"),
                "total_ad_expenses": Decimal("0"),
                "logistics_total": Decimal("90"),
                "finance_mode": "row_level",
            }
        ),
    )

    result = await asyncio.wait_for(
        service.expense_logistics(
            session,  # type: ignore[arg-type]
            account_id=1,
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 20),
            include_unallocated=True,
        ),
        timeout=1.0,
    )

    assert result.total_logistics == pytest.approx(90.0)
    assert result.logistics_share_base_kind == "wb_expenses"
    assert result.logistics_share_base_amount == pytest.approx(90.0)
    assert result.logistics_share_percent == pytest.approx(100.0)
    assert result.delivery_to_client == pytest.approx(60.0)
    assert result.return_from_client == pytest.approx(15.0)
    assert result.cancellation_to_client == pytest.approx(10.0)
    assert result.defect_return == pytest.approx(5.0)
    assert any(item.group_key == "delivery_to_client" for item in result.by_logistics_type)


@pytest.mark.asyncio
async def test_expense_logistics_falls_back_to_raw_finance_rows(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(
        service,
        "summary",
        AsyncMock(
            return_value=_summary_stub(
                account_id=1,
                date_from=date(2026, 5, 1),
                date_to=date(2026, 5, 20),
                expense_breakdown=ExpenseBreakdownSummaryRead(
                    account_id=1,
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 5, 20),
                    total_expenses=200.0,
                    total_wb_expenses=90.0,
                    total_seller_expenses=0.0,
                    total_ad_expenses=0.0,
                    logistics_total=90.0,
                    logistics_share_base_kind="wb_expenses",
                    logistics_share_base_amount=90.0,
                    logistics_share_percent=100.0,
                ),
                profit_cascade=ProfitCascadeRead(
                    account_id=1,
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 5, 20),
                    source_of_truth="finance_report",
                    data_version_hash="summary-hash-4",
                    cascade={"totals": {"total_wb_expenses": 90.0, "total_seller_expenses": 0.0, "total_ad_expenses": 0.0, "logistics_total": 90.0}},
                ),
                kpis=MoneySummaryKpis(revenue=0.0),
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_expense_totals",
        AsyncMock(
            return_value={
                "total_expenses": Decimal("200"),
                "total_wb_expenses": Decimal("90"),
                "total_seller_expenses": Decimal("0"),
                "total_ad_expenses": Decimal("0"),
                "logistics_total": Decimal("90"),
                "finance_ad_expenses": Decimal("0"),
                "finance_mode": "account_level",
            }
        ),
    )
    session = _FakeAsyncSession(
        results=[
            [
                (
                    SimpleNamespace(
                        report_id=1001,
                        rrd_id=5001,
                        nm_id=223205606,
                        vendor_code="SKU-18516",
                        barcode="123456",
                        seller_oper_name="Доставка покупателю",
                        bonus_type_name=None,
                        srid="SRID-1",
                        order_id=101,
                        payload={},
                    ),
                    18516,
                    "SKU-18516",
                ),
                (
                    SimpleNamespace(
                        report_id=1002,
                        rrd_id=5002,
                        nm_id=223205607,
                        vendor_code="SKU-18517",
                        barcode="654321",
                        seller_oper_name="Возврат от клиента",
                        bonus_type_name=None,
                        srid="SRID-2",
                        order_id=102,
                        payload={},
                    ),
                    18517,
                    "SKU-18517",
                ),
            ]
        ]
    )
    monkeypatch.setattr(
        MartService,
        "_finance_expense_details",
        staticmethod(
            lambda row, sku_id=None: {
                "entries": [
                    {
                        "stat_date": date(2026, 5, 10 if row.report_id == 1001 else 11),
                        "expense_category": "wb_logistics" if row.report_id == 1001 else "wb_logistics_rebill",
                        "logistics_type": "delivery_service" if row.report_id == 1001 else "rebill_logistic_cost",
                        "source_field": "delivery_service" if row.report_id == 1001 else "rebill_logistic_cost",
                        "sku_id": sku_id,
                        "expense_source": "finance_report",
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(
        MartService,
        "_entry_signed_amount",
        staticmethod(lambda entry: Decimal("60") if entry["expense_category"] == "wb_logistics" else Decimal("30")),
    )

    result = await service.expense_logistics(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        include_unallocated=True,
    )

    assert result.total_logistics == pytest.approx(90.0)
    assert result.logistics_share_percent == pytest.approx(100.0)
    assert result.delivery_to_client == pytest.approx(60.0)
    assert result.return_from_client == pytest.approx(30.0)
    assert any(item.group_key == "sku:18516" for item in result.by_sku)


@pytest.mark.asyncio
async def test_expense_report_rows_filters_by_category(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(service, "_expense_report_rows_version_hash", AsyncMock(return_value="expense-hash-1"))
    session = _FakeAsyncSession(
        results=[
            1,
            [
                (
                    1001,
                    5001,
                    date(2026, 5, 10),
                    223205606,
                    18516,
                    "SKU-18516",
                    "123456",
                    "wb_logistics",
                    Decimal("1200"),
                    "finance_report",
                    "delivery_service",
                    "Логистика",
                    None,
                    "delivery_service",
                    "SRID-1",
                    101,
                    True,
                )
            ],
        ]
    )

    page = await service.expense_report_rows(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        category="wb_logistics",
        limit=50,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].category == "wb_logistics"
    compiled = str(session.statements[1].compile(compile_kwargs={"literal_binds": True}))
    assert "expense_category" in compiled
    assert "wb_logistics" in compiled


@pytest.mark.asyncio
async def test_expense_report_rows_fall_back_to_raw_finance_rows(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(service, "_expense_report_rows_version_hash", AsyncMock(return_value="expense-hash-1"))
    session = _FakeAsyncSession(
        results=[
            0,
            [
                (
                    SimpleNamespace(
                        report_id=1001,
                        rrd_id=5001,
                        nm_id=223205606,
                        vendor_code="SKU-18516",
                        barcode="123456",
                        seller_oper_name="Логистика",
                        bonus_type_name=None,
                        srid="SRID-1",
                        order_id=101,
                    ),
                    18516,
                    "SKU-18516",
                )
            ],
        ]
    )
    monkeypatch.setattr(
        MartService,
        "_finance_expense_details",
        staticmethod(
            lambda row, sku_id=None: {
                "entries": [
                    {
                        "stat_date": date(2026, 5, 10),
                        "expense_category": "wb_logistics",
                        "logistics_type": "delivery_service",
                        "source_field": "delivery_service",
                        "sku_id": sku_id,
                        "expense_source": "finance_report",
                    }
                ]
            }
        ),
    )
    monkeypatch.setattr(MartService, "_entry_signed_amount", staticmethod(lambda entry: Decimal("1200")))

    page = await service.expense_report_rows(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        category="wb_logistics",
        limit=50,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].category == "wb_logistics"
    assert page.items[0].source_field == "delivery_service"
    assert page.items[0].sku_id == 18516


@pytest.mark.asyncio
async def test_expense_report_rows_filters_raw_fallback_by_trace_fields(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(service, "_expense_report_rows_version_hash", AsyncMock(return_value="expense-hash-2"))
    session = _FakeAsyncSession(results=[0])
    monkeypatch.setattr(MartService, "_entry_signed_amount", staticmethod(lambda entry: Decimal(str(entry["amount"]))))
    monkeypatch.setattr(
        service,
        "_raw_finance_expense_entries",
        AsyncMock(
            return_value=[
                {
                    "report_id": 10,
                    "rrd_id": 501,
                    "stat_date": date(2026, 5, 10),
                    "nm_id": 223205606,
                    "sku_id": 18516,
                    "vendor_code": "SKU-18516",
                    "barcode": "123456",
                    "expense_category": "wb_logistics",
                    "expense_source": "finance_report",
                    "source_field": "delivery_service",
                    "seller_oper_name": "Логистика",
                    "bonus_type_name": None,
                    "logistics_type": "delivery_service",
                    "srid": "SRID-1",
                    "order_id": 101,
                    "amount": Decimal("1.00"),
                },
                {
                    "report_id": 10,
                    "rrd_id": 502,
                    "stat_date": date(2026, 5, 10),
                    "nm_id": None,
                    "sku_id": None,
                    "vendor_code": None,
                    "barcode": None,
                    "expense_category": "storage",
                    "expense_source": "finance_report",
                    "source_field": "storage_fee",
                    "seller_oper_name": "Хранение",
                    "bonus_type_name": None,
                    "logistics_type": None,
                    "srid": "SRID-2",
                    "order_id": 102,
                    "amount": Decimal("5.00"),
                },
            ]
        ),
    )

    page = await service.expense_report_rows(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        amount_exact=1,
        search="sku-18516",
        source_field="delivery_service",
        seller_oper_name="лог",
        allocated=True,
        limit=50,
        offset=0,
    )

    assert page.total == 1
    assert page.items[0].rrd_id == 501
    assert page.items[0].amount == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_summary_net_profit_after_overhead_subtracts_unallocated_expenses(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=False,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("0"),
        supplier_confirmed_revenue_coverage_percent=0.0,
        revenue_with_cost=Decimal("1000"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("1000"),
                for_pay=Decimal("900"),
                commission=Decimal("50"),
                acquiring_fee=Decimal("0"),
                logistics=Decimal("0"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("0"),
                penalties=Decimal("0"),
                deductions=Decimal("0"),
                additional_payments=Decimal("0"),
                estimated_cogs=Decimal("300"),
                estimated_profit=Decimal("600"),
                net_units=5,
                finance_rows=1,
                has_real_manual_cost=False,
                cost_truth_level="operator_baseline",
                ad_spend=Decimal("100"),
            )
        ],
        control_rows=[
            SimpleNamespace(
                sku_id=1,
                nm_id=10,
                vendor_code="SKU-1",
                title="Alpha",
                brand="Brand",
                subject_name="Cat",
                stock_qty=0,
                stock_value=0,
                days_of_stock=0,
                ad_spend=100.0,
                raw_ad_spend=100.0,
                capped_ad_spend=100.0,
                overallocated_ad_spend=0.0,
                unallocated_ad_spend=0.0,
                drr_percent=10.0,
                priority_score=10.0,
                trust_state=TRUST_STATE_TEST_ONLY,
                blocked_reasons=[],
                sku_status="STABLE",
                revenue=1000.0,
                net_profit=550.0,
            )
        ],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("100"),
        ads_source_by_nm={10: Decimal("100")},
        account_expense_rows=[
            SimpleNamespace(
                storage=Decimal("80"),
                deductions=Decimal("0"),
                penalties=Decimal("0"),
                logistics=Decimal("0"),
                paid_acceptance=Decimal("0"),
                total_expense=Decimal("80"),
            )
        ],
        account_level_expense_total=Decimal("80"),
        latest_balance=None,
        finance_confirmed_revenue_total=Decimal("1000"),
        finance_closed_mart_revenue_total=Decimal("1000"),
        finance_coverage_date_to=date(2026, 5, 20),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="hit",
        data_version_hash="runtime-hash-1",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="runtime-hash-1"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=1000.0,
                finance_confirmed_revenue=1000.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 20),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 20),
                open_operational_period_revenue=0.0,
                is_final=False,
                recommendation="",
            )
        ),
    )

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.kpis.net_profit_after_ads == 550.0
    assert result.kpis.net_profit_after_overhead == 470.0
    assert result.kpis.unallocated_expenses == 80.0
    assert result.computed_at == datetime(2026, 5, 20, 12, 0, 0)
    assert result.cache_status == "hit"
    assert result.data_version_hash == "runtime-hash-1"


@pytest.mark.asyncio
async def test_summary_uses_current_balance_and_exposes_period_end_balance(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=True,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TRUSTED,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("1000"),
        supplier_confirmed_revenue_coverage_percent=100.0,
        revenue_with_cost=Decimal("1000"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="supplier_confirmed",
        financial_final=True,
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("1000"),
                for_pay=Decimal("900"),
                wb_commission=Decimal("50"),
                payment_processing=Decimal("10"),
                pvz_reward=Decimal("0"),
                wb_logistics=Decimal("0"),
                wb_logistics_rebill=Decimal("0"),
                commission=Decimal("50"),
                acquiring_fee=Decimal("10"),
                logistics=Decimal("0"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("0"),
                penalties=Decimal("0"),
                deductions=Decimal("0"),
                additional_payments=Decimal("0"),
                marketing_deduction=Decimal("0"),
                ad_spend_operational=Decimal("0"),
                ad_spend_finance=Decimal("0"),
                ad_spend_final=Decimal("0"),
                ad_spend_source="none",
                ad_spend=Decimal("0"),
                seller_cogs=Decimal("300"),
                seller_other_expense=Decimal("20"),
                estimated_cogs=Decimal("300"),
                estimated_profit=Decimal("620"),
                net_profit=Decimal("620"),
                total_orders=1,
                total_returns=0,
                total_sales_qty=1,
                total_returns_qty=0,
                status="ok",
                trust_state=TRUST_STATE_TRUSTED,
                blocked_reasons=[],
                stock_value=Decimal("0"),
                opening_stock_qty=0,
                closing_stock_qty=0,
                in_transit_qty=0,
                data_quality_status="ok",
            )
        ],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={},
        trust_decision=SimpleNamespace(
            trust_state=TRUST_STATE_TRUSTED,
            business_trusted=True,
            operational_trusted=True,
            financial_final=True,
            can_generate_business_actions=True,
            confidence="high",
            supplier_confirmed_revenue_coverage_percent=100.0,
            operator_baseline_revenue_coverage_percent=100.0,
            trusted_revenue_cost_coverage_percent=100.0,
            cost_trust_policy="supplier_confirmed",
            financial_final_blockers_total=0,
            final_profit_blockers_total=0,
            all_open_issues_total=0,
            blocking_open_issues_total=0,
            blocked_reasons=[],
        ),
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=SimpleNamespace(
            current=Decimal("1508147.40"),
            for_withdraw=Decimal("75000"),
            snapshot_at=datetime(2026, 6, 2, 22, 0, 0),
        ),
        period_end_balance=SimpleNamespace(
            current=Decimal("706130.75"),
            for_withdraw=None,
            snapshot_at=datetime(2026, 5, 24, 22, 0, 0),
        ),
        finance_confirmed_revenue_total=Decimal("1000"),
        finance_closed_mart_revenue_total=Decimal("1000"),
        finance_coverage_date_to=date(2026, 5, 25),
        computed_at=datetime(2026, 6, 4, 12, 0, 0),
        cache_status="miss",
        data_version_hash="runtime-hash-balance",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="runtime-hash-balance"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=1000.0,
                finance_confirmed_revenue=1000.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 25),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 25),
                open_operational_period_revenue=0.0,
                is_final=True,
                recommendation="",
            )
        ),
    )

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 25),
    )

    assert result.kpis.cash_on_wb == 1508147.40
    assert result.kpis.available_for_withdraw == 75000.0
    assert result.kpis.cash_on_wb_current == 1508147.40
    assert result.kpis.cash_on_wb_period_end == 706130.75
    assert result.kpis.available_for_withdraw_period_end == 706130.75
    assert result.cash_and_stock.cash_on_wb == 1508147.40
    assert result.cash_and_stock.cash_on_wb_period_end == 706130.75


def test_profit_cascade_formula_matches_groups_and_cogs_parent_is_not_zero() -> None:
    service = MoneyManagementService()
    meta = MoneyMeta(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        currency="RUB",
        generated_at=datetime(2026, 5, 31, 12, 0, 0),
        data_trust=DataTrustInfo(
            state="operational_provisional",
            trust_state="operational_provisional",
            business_trusted=True,
            operational_trusted=True,
            financial_final=False,
            can_generate_business_actions=True,
            confidence="medium",
            human_message="ok",
        ),
    )
    revenue_sources = RevenueSources(source_of_truth="finance")
    kpis = MoneySummaryKpis(
        revenue=1000.0,
        revenue_final=1000.0,
        seller_cogs=300.0,
        seller_other_expense=50.0,
        total_seller_costs=350.0,
        wb_commission=40.0,
        payment_processing=10.0,
        pvz_reward=5.0,
        wb_logistics=80.0,
        wb_logistics_rebill=20.0,
        storage=15.0,
        acceptance=5.0,
        penalty=10.0,
        deduction=25.0,
        loyalty=12.0,
        other_wb_expenses=8.0,
        wb_expenses_total=230.0,
        ad_spend_operational=60.0,
        ad_spend_finance=40.0,
        ad_spend_final=40.0,
        ad_spend_source="finance_report",
        additional_income=30.0,
        net_profit_after_all_expenses=410.0,
    )

    result = service._build_profit_cascade(
        meta=meta,
        revenue_sources=revenue_sources,
        kpis=kpis,
    )

    assert result.source_of_truth == "finance_report"
    assert result.cascade.groups[0].code == "seller_cogs"
    assert result.cascade.groups[0].amount == pytest.approx(300.0)
    assert result.cascade.groups[0].children[0].amount == pytest.approx(300.0)
    assert result.cascade.groups[1].amount == pytest.approx(50.0)
    assert result.cascade.groups[2].amount == pytest.approx(230.0)
    assert result.cascade.groups[3].children[0].ad_spend_finance == pytest.approx(40.0)
    assert result.cascade.totals.total_seller_expenses == pytest.approx(350.0)
    assert result.cascade.totals.total_wb_expenses == pytest.approx(230.0)
    assert result.cascade.totals.net_profit_after_all_expenses == pytest.approx(410.0)
    assert result.cascade.validation.groups_match_children is True
    assert result.cascade.validation.profit_formula_valid is True
    assert result.cascade.validation.issues == []


def test_profit_cascade_adds_delta_row_when_wb_total_differs_from_visible_children() -> None:
    service = MoneyManagementService()
    meta = MoneyMeta(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        currency="RUB",
        generated_at=datetime(2026, 5, 31, 12, 0, 0),
        data_trust=DataTrustInfo(
            state="test_only",
            trust_state="test_only",
            business_trusted=False,
            operational_trusted=True,
            financial_final=False,
            can_generate_business_actions=True,
            confidence="low",
            human_message="test",
        ),
    )
    revenue_sources = RevenueSources(source_of_truth="mixed")
    kpis = MoneySummaryKpis(
        revenue=500.0,
        revenue_final=500.0,
        seller_cogs=100.0,
        seller_other_expense=20.0,
        total_seller_costs=120.0,
        wb_logistics=80.0,
        wb_expenses_total=100.0,
        ad_spend_final=0.0,
        additional_income=0.0,
        net_profit_after_all_expenses=280.0,
    )

    result = service._build_profit_cascade(
        meta=meta,
        revenue_sources=revenue_sources,
        kpis=kpis,
    )

    wb_group = next(group for group in result.cascade.groups if group.code == "wb_direct_expenses")
    delta_row = next(child for child in wb_group.children if child.code == "other_or_rounding_delta")

    assert wb_group.amount == pytest.approx(100.0)
    assert delta_row.amount == pytest.approx(20.0)
    assert result.cascade.validation.groups_match_children is False
    assert any("total_wb_expenses_formula_delta" in issue for issue in result.cascade.validation.issues)
    assert any("group:wb_direct_expenses:children_sum_delta" in issue for issue in result.cascade.validation.issues)


@pytest.mark.asyncio
async def test_summary_response_cache_reuses_final_payload(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=False,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("0"),
        supplier_confirmed_revenue_coverage_percent=0.0,
        revenue_with_cost=Decimal("1000"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("1000"),
                for_pay=Decimal("900"),
                commission=Decimal("50"),
                acquiring_fee=Decimal("0"),
                logistics=Decimal("0"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("0"),
                penalties=Decimal("0"),
                deductions=Decimal("0"),
                additional_payments=Decimal("0"),
                estimated_cogs=Decimal("300"),
                estimated_profit=Decimal("600"),
                net_units=5,
                finance_rows=1,
                has_real_manual_cost=False,
                cost_truth_level="operator_baseline",
                ad_spend=Decimal("100"),
            )
        ],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("100"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        finance_confirmed_revenue_total=Decimal("1000"),
        finance_closed_mart_revenue_total=Decimal("1000"),
        finance_coverage_date_to=date(2026, 5, 20),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="miss",
        data_version_hash="runtime-hash-1",
    )
    load_runtime_state = AsyncMock(return_value=state)
    monkeypatch.setattr(service, "_load_runtime_state", load_runtime_state)
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="runtime-hash-1"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=1000.0,
                finance_confirmed_revenue=1000.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 20),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 20),
                open_operational_period_revenue=0.0,
                is_final=True,
                recommendation="",
            )
        ),
    )

    first = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )
    second = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert second.kpis.revenue == first.kpis.revenue
    assert load_runtime_state.await_count == 1
    assert service._runtime_version_hash.await_count == 2


def test_runtime_cache_key_changes_when_data_version_hash_changes() -> None:
    service = MoneyManagementService()

    first = service._runtime_cache_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        data_version_hash="hash-1",
    )
    second = service._runtime_cache_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        data_version_hash="hash-2",
    )

    assert first != second


@pytest.mark.asyncio
async def test_summary_warm_cache_is_bypassed_when_runtime_version_hash_changes(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=False,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("0"),
        supplier_confirmed_revenue_coverage_percent=0.0,
        revenue_with_cost=Decimal("1000"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
        financial_final=False,
        financial_final_blockers_total=8,
        final_profit_blockers_total=8,
        all_open_issues_total=100,
        blocking_open_issues_total=8,
        operational_trusted=True,
    )
    first_state = SimpleNamespace(
        health=health,
        profit_rows=[],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        period_end_balance=None,
        finance_confirmed_revenue_total=Decimal("0"),
        finance_closed_mart_revenue_total=Decimal("0"),
        finance_coverage_date_to=date(2026, 5, 20),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="miss",
        data_version_hash="runtime-hash-1",
    )
    second_health = SimpleNamespace(**{**health.__dict__, "financial_final_blockers_total": 33, "final_profit_blockers_total": 33, "blocking_open_issues_total": 33})
    second_state = SimpleNamespace(**{**first_state.__dict__, "health": second_health, "data_version_hash": "runtime-hash-2"})

    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(side_effect=[first_state, second_state]))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(side_effect=["runtime-hash-1", "runtime-hash-2"]))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=0.0,
                finance_confirmed_revenue=0.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 20),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 20),
                open_operational_period_revenue=0.0,
                is_final=False,
                recommendation="",
            )
        ),
    )

    first = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )
    second = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "miss"
    assert first.meta.data_trust.financial_final_blockers_total == 8
    assert second.meta.data_trust.financial_final_blockers_total == 33
    assert service._load_runtime_state.await_count == 2


@pytest.mark.asyncio
async def test_expense_report_rows_reuses_cached_page(monkeypatch) -> None:
    service = MoneyManagementService()
    session = _FakeAsyncSession([0])
    monkeypatch.setattr(service, "_expense_report_rows_version_hash", AsyncMock(return_value="expense-hash-1"))
    monkeypatch.setattr(
        service,
        "_raw_finance_expense_entries",
        AsyncMock(
            return_value=[
                {
                    "report_id": 10,
                    "rrd_id": 20,
                    "stat_date": date(2026, 5, 20),
                    "nm_id": 101,
                    "sku_id": 1,
                    "vendor_code": "ABC",
                    "barcode": "111",
                    "expense_category": "wb_logistics",
                    "expense_source": "finance_report",
                    "source_field": "delivery_rub",
                    "seller_oper_name": "Логистика",
                    "bonus_type_name": None,
                    "logistics_type": "delivery_to_client",
                    "srid": "srid-1",
                    "order_id": 999,
                    "delivery_rub": Decimal("120"),
                }
            ]
        ),
    )

    first = await service.expense_report_rows(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )
    second = await service.expense_report_rows(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert second.data_version_hash == "expense-hash-1"
    assert service._raw_finance_expense_entries.await_count == 1
    assert len(session.statements) == 1


@pytest.mark.asyncio
async def test_articles_returns_single_article_row_per_nm_id(monkeypatch) -> None:
    service = MoneyManagementService()
    real_build_card_money = service._build_card_money
    row1 = SimpleNamespace(
        sku_id=101,
        nm_id=555,
        vendor_code="A-101",
        title="Article 555",
        brand="Brand",
        subject_name="Subject",
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        priority_score=50.0,
        sku_status="WATCH",
        stock_qty=5,
        days_of_stock=20,
        net_profit=120.0,
        ad_spend=10.0,
    )
    row2 = SimpleNamespace(
        sku_id=102,
        nm_id=555,
        vendor_code="A-102",
        title="Article 555",
        brand="Brand",
        subject_name="Subject",
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        priority_score=40.0,
        sku_status="WATCH",
        stock_qty=7,
        days_of_stock=18,
        net_profit=80.0,
        ad_spend=8.0,
    )
    state = SimpleNamespace(
        control_rows=[row1, row2],
        profit_rows=[SimpleNamespace(sku_id=101, realized_revenue=600.0), SimpleNamespace(sku_id=102, realized_revenue=400.0)],
        purchase_rows={101: None, 102: None},
        price_rows={},
        ads_source_by_nm={555: Decimal("100")},
        account_level_expense_total=Decimal("0"),
        settings={"cost_trust_policy": "operator_baseline"},
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_filter_money_cards", lambda rows, **kwargs: list(rows))
    monkeypatch.setattr(
        service,
        "_aggregate_article_context",
        lambda **kwargs: {
            "row": SimpleNamespace(
                sku_id=None,
                nm_id=555,
                vendor_code="ART-555",
                title="Article 555",
                brand="Brand",
                subject_name="Subject",
                trust_state=TRUST_STATE_TEST_ONLY,
                blocked_reasons=[],
                priority_score=50.0,
                sku_status="WATCH",
            ),
            "profit_row": SimpleNamespace(realized_revenue=1000.0, has_real_manual_cost=False, cost_truth_level="operator_baseline"),
            "purchase_row": None,
            "primary_row": row1,
            "primary_profit_row": SimpleNamespace(realized_revenue=600.0),
        },
    )
    monkeypatch.setattr(
        service,
        "_primary_row_action",
        lambda *args, **kwargs: NextActionRead(
            action_type="WATCH",
            priority="medium",
            title="Watch",
            what_to_do="Review article",
            why="Keep it under control",
            confidence="medium",
            linked_entity={"sku_id": 101, "nm_id": 555, "vendor_code": "A-101"},
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_card_money",
        lambda *args, **kwargs: real_build_card_money(
            SimpleNamespace(
                realized_revenue=1000.0,
                for_pay=900.0,
                commission=50.0,
                acquiring_fee=0.0,
                logistics=20.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                finance_rows=1,
                estimated_cogs=300.0,
                net_units=10,
                has_real_manual_cost=False,
                estimated_profit=450.0,
                ad_spend=100.0,
                cost_truth_level="operator_baseline",
            ),
            SimpleNamespace(
                ad_spend=100.0,
                drr_percent=10.0,
                stock_value=700.0,
                trust_state=TRUST_STATE_TEST_ONLY,
                nm_id=555,
                capped_ad_spend=100.0,
                raw_ad_spend=100.0,
                overallocated_ad_spend=0.0,
                unallocated_ad_spend=0.0,
                ads_allocation_status="matched",
                final_profit_allowed=True,
            ),
            price_row=None,
            ads_source_spend=Decimal("100"),
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_card_stock",
        lambda *args, **kwargs: CardStockBlock(quantity=12.0, quantity_full=12.0, stock_value=700.0, days_of_stock=19.0, stock_status="ok"),
    )
    monkeypatch.setattr(service, "_build_card_verdict", lambda *args, **kwargs: CardVerdict(status="healthy", label="Healthy", short_text="ok", confidence="medium"))
    monkeypatch.setattr(service, "_finality_for_row", lambda *args, **kwargs: FinalityBlock(profit_final=False, restock_final=False, price_final=False, reasons=["supplier_cost_not_confirmed"]))
    monkeypatch.setattr(
        service,
        "_data_trust_for_row",
        lambda row: DataTrustInfo(
            state=row.trust_state,
            business_trusted=False,
            can_generate_business_actions=True,
            confidence="medium",
            blocked_reasons=[],
            human_message="Provisional",
        ),
    )
    monkeypatch.setattr(service, "_cost_coverage_from_profit_rows", lambda *args, **kwargs: CostCoverageBlock())

    result = await service.articles(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].nm_id == 555
    assert result.items[0].variant_count == 2
    assert result.items[0].identity is not None
    assert result.items[0].money_answer.next_step == "Review article"


@pytest.mark.asyncio
async def test_article_detail_keeps_card_totals_unduplicated_and_exposes_sku_breakdown(monkeypatch) -> None:
    service = MoneyManagementService()
    real_build_card_money = service._build_card_money
    row1 = SimpleNamespace(
        sku_id=201,
        nm_id=777,
        vendor_code="B-201",
        title="Article 777",
        brand="Brand",
        subject_name="Subject",
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        priority_score=70.0,
        sku_status="LIQUIDATE",
    )
    row2 = SimpleNamespace(
        sku_id=202,
        nm_id=777,
        vendor_code="B-202",
        title="Article 777",
        brand="Brand",
        subject_name="Subject",
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        priority_score=60.0,
        sku_status="LIQUIDATE",
    )
    profit1 = SimpleNamespace(sku_id=201, realized_revenue=600.0)
    profit2 = SimpleNamespace(sku_id=202, realized_revenue=400.0)
    state = SimpleNamespace(
        control_rows=[row1, row2],
        profit_rows=[profit1, profit2],
        purchase_rows={201: None, 202: None},
        price_rows={201: None},
        ads_source_by_nm={777: Decimal("100")},
        account_level_expense_total=Decimal("50"),
        settings={"cost_trust_policy": "operator_baseline"},
        health=SimpleNamespace(
            trust_state=TRUST_STATE_TEST_ONLY,
            business_trusted=False,
            can_generate_business_actions=True,
            blocked_reasons=[],
        ),
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(
        service.dashboard,
        "article_audit",
        AsyncMock(
            return_value=SimpleNamespace(
                operations=SimpleNamespace(orders_count=10, cancelled_orders_count=2, sales_count=8, returns_count=1),
                funnel=SimpleNamespace(open_count=100, cart_count=20, order_count=10, buyout_count=8),
                finance=SimpleNamespace(net_units=7),
                reconciliation=SimpleNamespace(
                    mart_matches_article=True,
                    mart_matches_finance=False,
                    finance_matches_operational=False,
                    revenue_matches_mart=False,
                    mart_revenue_total=1000.0,
                    article_revenue_total=1000.0,
                    finance_report_revenue_total=900.0,
                    difference_amount=100.0,
                    difference_ratio_percent=10.0,
                    mismatch_reason="finance_gap",
                ),
                ads=SimpleNamespace(spend=100.0),
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_aggregate_article_context",
        lambda **kwargs: {
            "row": SimpleNamespace(
                sku_id=None,
                nm_id=777,
                vendor_code="ART-777",
                title="Article 777",
                brand="Brand",
                subject_name="Subject",
                trust_state=TRUST_STATE_TEST_ONLY,
                blocked_reasons=[],
                priority_score=70.0,
                sku_status="LIQUIDATE",
            ),
            "profit_row": SimpleNamespace(realized_revenue=1000.0, has_real_manual_cost=False, cost_truth_level="operator_baseline"),
            "purchase_row": None,
            "primary_row": row1,
            "primary_profit_row": SimpleNamespace(realized_revenue=600.0, has_real_manual_cost=False, cost_truth_level="operator_baseline"),
        },
    )
    monkeypatch.setattr(
        service,
        "_primary_row_action",
        lambda *args, **kwargs: NextActionRead(
            action_type="LIQUIDATE_STOCK",
            priority="high",
            title="Liquidate",
            what_to_do="Reduce stock",
            why="Too much stock",
            confidence="medium",
            linked_entity={"sku_id": 201, "nm_id": 777, "vendor_code": "B-201"},
            money_effect={"affected_stock_value": 1300.0, "expected_cash_release": 1300.0},
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_card_money",
        lambda *args, **kwargs: real_build_card_money(
            SimpleNamespace(
                realized_revenue=1000.0,
                for_pay=900.0,
                commission=40.0,
                acquiring_fee=0.0,
                logistics=20.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                finance_rows=1,
                estimated_cogs=300.0,
                net_units=10,
                has_real_manual_cost=False,
                estimated_profit=500.0,
                ad_spend=100.0,
                cost_truth_level="operator_baseline",
            ),
            SimpleNamespace(
                ad_spend=100.0,
                drr_percent=10.0,
                stock_value=1300.0,
                trust_state=TRUST_STATE_TEST_ONLY,
                nm_id=777,
                capped_ad_spend=100.0,
                raw_ad_spend=100.0,
                overallocated_ad_spend=0.0,
                unallocated_ad_spend=0.0,
                ads_allocation_status="matched",
                final_profit_allowed=True,
            ),
            price_row=None,
            ads_source_spend=Decimal("100"),
            account_level_expense_total=Decimal("50"),
            allocated_overhead=Decimal("50"),
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_card_stock",
        lambda *args, **kwargs: CardStockBlock(quantity=12.0, quantity_full=12.0, stock_value=1300.0, days_of_stock=120.0, stock_status="overstock"),
    )
    monkeypatch.setattr(
        service,
        "_build_card_price",
        lambda *args, **kwargs: CardPriceBlock(
            current_price=18900.0,
            current_discounted_price=10962.0,
            break_even_price=3400.0,
            target_margin_price=4200.0,
            safe_price_gap=6762.0,
            status="ready",
            confidence="medium",
            price_source="article_price",
        ),
    )
    monkeypatch.setattr(service, "_build_card_verdict", lambda *args, **kwargs: CardVerdict(status="overstock", label="Overstock", short_text="overstock", confidence="medium"))
    monkeypatch.setattr(service, "_finality_for_row", lambda *args, **kwargs: FinalityBlock(profit_final=False, restock_final=False, price_final=True, reasons=["finance_reconciliation_mismatch"]))
    monkeypatch.setattr(
        service,
        "_cost_coverage_from_profit_rows",
        lambda *args, **kwargs: CostCoverageBlock(
            operational_cost_coverage_percent=99.6,
            supplier_confirmed_cost_coverage_percent=0.0,
            business_accepted_cost_coverage_percent=99.6,
            can_use_for_operations=True,
            can_use_for_final_profit=False,
            cost_policy="operator_baseline",
            cost_truth_level="operator_baseline",
            message="Operational cost only",
        ),
    )
    monkeypatch.setattr(
        service,
        "_variant_breakdown_rows",
        lambda **kwargs: [
            VariantBreakdownRow(sku_id=201, barcode="1", vendor_code="B-201", title="46", revenue=600.0, stock_qty=5.0, stock_value=650.0, source_ads_spend=60.0, net_profit_after_source_ads=180.0, next_action=NextActionRead(action_type="WATCH", priority="low", title="w", what_to_do="w", why="w", confidence="low")),
            VariantBreakdownRow(sku_id=202, barcode="2", vendor_code="B-202", title="48", revenue=400.0, stock_qty=7.0, stock_value=650.0, source_ads_spend=40.0, net_profit_after_source_ads=120.0, next_action=NextActionRead(action_type="WATCH", priority="low", title="w", what_to_do="w", why="w", confidence="low")),
        ],
    )
    monkeypatch.setattr(
        service,
        "_article_summary_block",
        lambda **kwargs: ArticleSummaryBlock(
            nm_id=777,
            title="Article 777",
            revenue=1000.0,
            profit_before_ads=500.0,
            ads_source_spend=100.0,
            profit_after_ads=400.0,
            stock_qty=12.0,
            stock_value=1300.0,
            cancel_rate_percent=20.0,
            return_rate_percent=12.5,
            decision="liquidate",
        ),
    )
    monkeypatch.setattr(
        service,
        "_article_purchase_plan",
        lambda **kwargs: ArticlePurchasePlanBlock(
            decision="LIQUIDATE",
            main_reason="Too much stock",
            next_step="Reduce stock",
            recommended_qty=0,
            required_cash=0.0,
            money_effect={"affected_stock_value": 1300.0, "expected_cash_release": 1300.0},
            confidence="medium",
            decision_confidence="medium",
            financial_final=False,
            variant_count=2,
        ),
    )

    result = await service.article_detail(
        SimpleNamespace(),
        account_id=1,
        nm_id=777,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.nm_id == 777
    assert len(result.sku_breakdown) == 2
    assert sum(item.revenue for item in result.sku_breakdown) == 1000.0
    assert result.money.revenue == 1000.0
    assert result.kpis.revenue == 1000.0
    assert result.money_answer.next_step == "Reduce stock"
    assert result.actions[0].what_to_do == "Reduce stock"


@pytest.mark.asyncio
async def test_data_blockers_hides_finance_reconciliation_mismatch_bucket(monkeypatch) -> None:
    service = MoneyManagementService()
    state = SimpleNamespace(
        health=SimpleNamespace(
            trust_state=TRUST_STATE_TEST_ONLY,
            business_trusted=False,
            can_generate_business_actions=True,
            blocked_reasons=[],
            open_issues_total=1977,
            issue_buckets=[
                SimpleNamespace(
                    code="finance_reconciliation_mismatch",
                    severity="error",
                    count=20,
                    business_impact="Profit may be wrong",
                    recommended_fix="Close reconciliation",
                    financial_final_blocker=True,
                ),
                SimpleNamespace(
                    code="stock_without_sales",
                    severity="warning",
                    count=100,
                    business_impact="Frozen stock",
                    recommended_fix="Review overstock",
                    financial_final_blocker=False,
                ),
            ],
            data_quality_summary=DataQualitySummaryBlock(
                global_blockers_total=0,
                financial_final_blockers_total=20,
                open_issues_total=1977,
                critical_total=0,
                error_total=282,
                warning_total=884,
                info_total=792,
                message="Глобальных блокеров нет, но есть открытые issues; финальная прибыль предварительная.",
                buckets=[],
            ),
        ),
        profit_rows=[SimpleNamespace(realized_revenue=Decimal("1000"), has_real_manual_cost=False)],
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        control_rows=[],
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))

    result = await service.data_blockers(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.overall_state == "accepted_with_warnings"
    assert "финальной сверки" not in result.overall_message.lower()
    assert result.blockers_count == 0
    assert result.warnings_count >= 1
    assert "finance_reconciliation_mismatch" not in result.open_issue_summary
    assert all(item.code != "finance_reconciliation_mismatch" for item in [*result.blockers, *result.warnings])
    assert result.warnings[0].simple_reason != ""


@pytest.mark.asyncio
async def test_summary_kpis_include_logistics_and_finance_ad_without_double_count(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=False,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("0"),
        supplier_confirmed_revenue_coverage_percent=0.0,
        revenue_with_cost=Decimal("1000"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
        financial_final=False,
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("1000"),
                for_pay=Decimal("900"),
                wb_commission=Decimal("50"),
                payment_processing=Decimal("10"),
                pvz_reward=Decimal("0"),
                wb_logistics=Decimal("80"),
                wb_logistics_rebill=Decimal("0"),
                commission=Decimal("50"),
                acquiring_fee=Decimal("10"),
                logistics=Decimal("80"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("20"),
                penalties=Decimal("0"),
                deductions=Decimal("40"),
                additional_payments=Decimal("0"),
                marketing_deduction=Decimal("40"),
                ad_spend_operational=Decimal("120"),
                ad_spend_finance=Decimal("40"),
                ad_spend_final=Decimal("40"),
                ad_spend_source="finance_report",
                ad_spend=Decimal("40"),
                seller_cogs=Decimal("300"),
                seller_other_expense=Decimal("20"),
                estimated_cogs=Decimal("300"),
                estimated_profit_before_ads=Decimal("520"),
                estimated_profit_after_ads=Decimal("480"),
                estimated_profit=Decimal("480"),
                net_profit_after_all_expenses=Decimal("480"),
                net_units=5,
                finance_rows=1,
                has_real_manual_cost=False,
                cost_truth_level="operator_baseline",
            )
        ],
        control_rows=[
            SimpleNamespace(
                sku_id=1,
                nm_id=10,
                vendor_code="SKU-1",
                title="Alpha",
                stock_qty=10,
                stock_value=200,
                days_of_stock=10,
                ad_spend=40.0,
                raw_ad_spend=40.0,
                capped_ad_spend=40.0,
                overallocated_ad_spend=0.0,
                unallocated_ad_spend=80.0,
                drr_percent=4.0,
                priority_score=10.0,
                trust_state=TRUST_STATE_TEST_ONLY,
                blocked_reasons=[],
                sku_status="STABLE",
                revenue=1000.0,
                net_profit=480.0,
            )
        ],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("120"),
        ads_source_by_nm={10: Decimal("120")},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        finance_confirmed_revenue_total=Decimal("1000"),
        finance_closed_mart_revenue_total=Decimal("1000"),
        finance_coverage_date_to=date(2026, 5, 20),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="miss",
        data_version_hash="normalized-expense-summary",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="normalized-expense-summary"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=1000.0,
                finance_confirmed_revenue=1000.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 20),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 20),
                open_operational_period_revenue=0.0,
                is_final=False,
                recommendation="",
            )
        ),
    )

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.kpis.wb_logistics == 80.0
    assert result.kpis.wb_expenses_total == 160.0
    assert result.kpis.total_seller_costs == 320.0
    assert result.kpis.logistics_share_percent == pytest.approx(50.0)
    assert result.kpis.ad_spend_operational == 120.0
    assert result.kpis.ad_spend_finance == 40.0
    assert result.kpis.ad_spend_final == 40.0
    assert result.kpis.ad_spend_source == "finance_report"
    assert result.kpis.ads_source_spend == 120.0
    assert result.kpis.ads_allocated_spend == 40.0
    assert result.kpis.ads_unallocated_spend == 80.0
    assert result.kpis.profit_after_allocated_ads == 480.0
    assert result.kpis.profit_after_source_ads == 400.0
    assert result.kpis.net_profit_after_ads == 400.0
    assert result.kpis.net_profit_after_all_expenses == 480.0
    assert result.kpis.expense_data_quality == "complete"


@pytest.mark.asyncio
async def test_summary_uses_raw_finance_fallback_for_store_level_expenses(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=False,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("0"),
        supplier_confirmed_revenue_coverage_percent=0.0,
        revenue_with_cost=Decimal("1000"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
        financial_final=False,
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("1000"),
                for_pay=Decimal("900"),
                wb_commission=Decimal("0"),
                payment_processing=Decimal("0"),
                pvz_reward=Decimal("0"),
                wb_logistics=Decimal("0"),
                wb_logistics_rebill=Decimal("0"),
                commission=Decimal("0"),
                acquiring_fee=Decimal("0"),
                logistics=Decimal("0"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("0"),
                penalties=Decimal("0"),
                deductions=Decimal("0"),
                additional_payments=Decimal("0"),
                marketing_deduction=Decimal("0"),
                ad_spend_operational=Decimal("0"),
                ad_spend_finance=Decimal("0"),
                ad_spend_final=Decimal("0"),
                ad_spend_source="none",
                ad_spend=Decimal("0"),
                seller_cogs=Decimal("300"),
                seller_other_expense=Decimal("20"),
                estimated_cogs=Decimal("300"),
                estimated_profit_before_ads=Decimal("680"),
                estimated_profit_after_ads=Decimal("680"),
                estimated_profit=Decimal("680"),
                net_profit_after_all_expenses=Decimal("680"),
                net_units=5,
                finance_rows=1,
                has_real_manual_cost=False,
                cost_truth_level="operator_baseline",
            )
        ],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        finance_confirmed_revenue_total=Decimal("1000"),
        finance_closed_mart_revenue_total=Decimal("1000"),
        finance_coverage_date_to=date(2026, 5, 20),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="miss",
        data_version_hash="summary-raw-finance-fallback",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="summary-raw-finance-fallback"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=1000.0,
                finance_confirmed_revenue=1000.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 20),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 20),
                open_operational_period_revenue=0.0,
                is_final=False,
                recommendation="",
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_raw_finance_expense_entries",
        AsyncMock(
            return_value=[
                {"expense_category": "wb_logistics", "amount": Decimal("80"), "amount_sign": "expense", "stat_date": date(2026, 5, 10)},
                {"expense_category": "storage", "amount": Decimal("20"), "amount_sign": "expense", "stat_date": date(2026, 5, 10)},
                {"expense_category": "marketing_deduction", "amount": Decimal("40"), "amount_sign": "expense", "stat_date": date(2026, 5, 11)},
            ]
        ),
    )

    result = await service.summary(
        object(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.kpis.wb_logistics == 80.0
    assert result.kpis.storage == 20.0
    assert result.kpis.wb_expenses_total == 100.0
    assert result.kpis.marketing_deduction == 40.0
    assert result.kpis.ad_spend_finance == 40.0
    assert result.kpis.ad_spend_final == 40.0
    assert result.kpis.net_profit_after_all_expenses == 540.0


@pytest.mark.asyncio
async def test_summary_kpis_additional_income_increases_profit(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=True,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TRUSTED,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("500"),
        supplier_confirmed_revenue_coverage_percent=100.0,
        revenue_with_cost=Decimal("500"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
        financial_final=True,
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("500"),
                for_pay=Decimal("450"),
                wb_commission=Decimal("25"),
                payment_processing=Decimal("5"),
                pvz_reward=Decimal("0"),
                wb_logistics=Decimal("40"),
                wb_logistics_rebill=Decimal("0"),
                commission=Decimal("25"),
                acquiring_fee=Decimal("5"),
                logistics=Decimal("40"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("10"),
                penalties=Decimal("0"),
                deductions=Decimal("0"),
                additional_payments=Decimal("15"),
                marketing_deduction=Decimal("0"),
                ad_spend_operational=Decimal("0"),
                ad_spend_finance=Decimal("0"),
                ad_spend_final=Decimal("0"),
                ad_spend_source="none",
                ad_spend=Decimal("0"),
                seller_cogs=Decimal("200"),
                seller_other_expense=Decimal("20"),
                estimated_cogs=Decimal("200"),
                estimated_profit_before_ads=Decimal("215"),
                estimated_profit_after_ads=Decimal("215"),
                estimated_profit=Decimal("215"),
                net_profit_after_all_expenses=Decimal("215"),
                net_units=2,
                finance_rows=1,
                has_real_manual_cost=True,
                cost_truth_level="supplier_confirmed",
            )
        ],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        finance_confirmed_revenue_total=Decimal("500"),
        finance_closed_mart_revenue_total=Decimal("500"),
        finance_coverage_date_to=date(2026, 5, 21),
        computed_at=datetime(2026, 5, 21, 12, 0, 0),
        cache_status="miss",
        data_version_hash="additional-income-summary",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="additional-income-summary"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=500.0,
                finance_confirmed_revenue=500.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 21),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 21),
                open_operational_period_revenue=0.0,
                is_final=True,
                recommendation="",
            )
        ),
    )

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 21),
    )

    assert result.kpis.additional_income == 15.0
    assert result.kpis.total_seller_costs == 220.0
    assert result.kpis.wb_expenses_total == 80.0
    assert result.kpis.net_profit_after_all_expenses == 215.0


@pytest.mark.asyncio
async def test_summary_kpis_unclassified_expense_is_included_and_flagged(monkeypatch) -> None:
    service = MoneyManagementService()
    health = SimpleNamespace(
        business_trusted=False,
        can_generate_business_actions=True,
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        revenue_with_real_cost=Decimal("0"),
        supplier_confirmed_revenue_coverage_percent=0.0,
        revenue_with_cost=Decimal("300"),
        revenue_without_cost=Decimal("0"),
        revenue_with_placeholder_cost=Decimal("0"),
        trusted_revenue_cost_coverage_percent=100.0,
        cost_trust_policy="operator_baseline",
        financial_final=False,
    )
    state = SimpleNamespace(
        health=health,
        profit_rows=[
            SimpleNamespace(
                sku_id=1,
                realized_revenue=Decimal("300"),
                for_pay=Decimal("270"),
                wb_commission=Decimal("10"),
                payment_processing=Decimal("0"),
                pvz_reward=Decimal("0"),
                wb_logistics=Decimal("20"),
                wb_logistics_rebill=Decimal("0"),
                other_wb_expenses=Decimal("17"),
                commission=Decimal("10"),
                acquiring_fee=Decimal("0"),
                logistics=Decimal("20"),
                paid_acceptance=Decimal("0"),
                storage=Decimal("0"),
                penalties=Decimal("0"),
                deductions=Decimal("17"),
                additional_payments=Decimal("0"),
                marketing_deduction=Decimal("0"),
                ad_spend_operational=Decimal("0"),
                ad_spend_finance=Decimal("0"),
                ad_spend_final=Decimal("0"),
                ad_spend_source="none",
                ad_spend=Decimal("0"),
                seller_cogs=Decimal("100"),
                seller_other_expense=Decimal("10"),
                estimated_cogs=Decimal("100"),
                estimated_profit_before_ads=Decimal("143"),
                estimated_profit_after_ads=Decimal("143"),
                estimated_profit=Decimal("143"),
                net_profit_after_all_expenses=Decimal("143"),
                net_units=2,
                finance_rows=1,
                has_real_manual_cost=False,
                cost_truth_level="operator_baseline",
            )
        ],
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        trust_decision=None,
        action_reads=[],
        actions_by_sku={},
        ads_source_total=Decimal("0"),
        ads_source_by_nm={},
        account_expense_rows=[],
        account_level_expense_total=Decimal("0"),
        latest_balance=None,
        finance_confirmed_revenue_total=Decimal("300"),
        finance_closed_mart_revenue_total=Decimal("300"),
        finance_coverage_date_to=date(2026, 5, 22),
        computed_at=datetime(2026, 5, 22, 12, 0, 0),
        cache_status="miss",
        data_version_hash="unclassified-expense-summary",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(service, "_runtime_version_hash", AsyncMock(return_value="unclassified-expense-summary"))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="matched",
                operational_revenue=300.0,
                finance_confirmed_revenue=300.0,
                difference_amount=0.0,
                difference_percent=0.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 22),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 22),
                open_operational_period_revenue=0.0,
                is_final=False,
                recommendation="",
            )
        ),
    )

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 22),
    )

    assert result.kpis.wb_expenses_total == 47.0
    assert result.kpis.other_wb_expenses == 17.0
    assert result.kpis.expense_data_quality == "unclassified_present"
    assert result.kpis.net_profit_after_all_expenses == 143.0
