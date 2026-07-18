from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.schemas.control_tower import PriceSafetyRow
from app.schemas.money_management import (
    ArticleTrustBlock,
    CardAdsBlock,
    CardCogsBlock,
    CardExpenseBreakdown,
    CardMoneyBlock,
    CardProfitBlock,
    CardStockBlock,
    CardVerdict,
    CostCoverageBlock,
    DataTrustInfo,
    FinalityBlock,
    FinanceReconciliationBlock,
    MoneyCardAnswer,
    NextActionRead,
)
from app.services.control_tower import ControlTowerService
from app.services.money_management import MoneyManagementService
from app.services.trust import TRUST_STATE_TEST_ONLY


def _acceptance_summary_state() -> SimpleNamespace:
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
    return SimpleNamespace(
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
                stock_qty=12,
                stock_value=700,
                days_of_stock=12,
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
        finance_confirmed_revenue_total=Decimal("850"),
        finance_closed_mart_revenue_total=Decimal("1000"),
        finance_coverage_date_to=date(2026, 5, 20),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="miss",
        data_version_hash="acceptance-summary",
    )


@pytest.mark.asyncio
async def test_etap3_acceptance_summary_answers_store_money_question(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=_acceptance_summary_state()))
    monkeypatch.setattr(
        service,
        "_finance_reconciliation_summary",
        AsyncMock(
            return_value=FinanceReconciliationBlock(
                status="critical_mismatch",
                operational_revenue=1000.0,
                finance_confirmed_revenue=850.0,
                difference_amount=150.0,
                difference_percent=15.0,
                closed_finance_date_from=date(2026, 5, 1),
                closed_finance_date_to=date(2026, 5, 20),
                requested_date_from=date(2026, 5, 1),
                requested_date_to=date(2026, 5, 20),
                open_operational_period_revenue=0.0,
                is_final=False,
                recommendation="Close finance reconciliation",
            )
        ),
    )

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.revenue_sources.operational_revenue == 1000.0
    assert result.kpis.finance_confirmed_revenue == 850.0
    assert result.finance_reconciliation.status == "critical_mismatch"
    assert result.kpis.ads_source_spend == 100.0
    assert result.kpis.stock_value == 700.0
    assert result.kpis.unallocated_expenses == 80.0
    assert result.kpis.net_profit_after_ads == 550.0
    assert result.kpis.net_profit_after_overhead == 470.0
    assert result.meta.data_trust.state == TRUST_STATE_TEST_ONLY
    assert result.answer.business_status == "provisional"


@pytest.mark.asyncio
async def test_etap3_acceptance_articles_answer_card_question_at_nm_id_level(monkeypatch) -> None:
    service = MoneyManagementService()
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
        profit_rows=[
            SimpleNamespace(sku_id=101, realized_revenue=600.0, has_real_manual_cost=False),
            SimpleNamespace(sku_id=102, realized_revenue=400.0, has_real_manual_cost=False),
        ],
        purchase_rows={101: None, 102: None},
        price_rows={},
        actions_by_sku={},
        settings={"cost_trust_policy": "operator_baseline"},
        health=SimpleNamespace(
            trust_state=TRUST_STATE_TEST_ONLY,
            business_trusted=False,
            can_generate_business_actions=True,
            blocked_reasons=[],
            revenue_with_real_cost=0.0,
            supplier_confirmed_revenue_coverage_percent=0.0,
            trusted_revenue_cost_coverage_percent=100.0,
        ),
        ads_source_total=Decimal("18"),
        ads_source_by_nm={555: Decimal("18")},
        account_level_expense_total=Decimal("0"),
        computed_at=datetime(2026, 5, 20, 12, 0, 0),
        cache_status="hit",
        data_version_hash="acceptance-articles",
    )
    monkeypatch.setattr(service, "_load_runtime_state", AsyncMock(return_value=state))
    monkeypatch.setattr(
        service,
        "_aggregate_article_context",
        lambda **kwargs: {
            "row": SimpleNamespace(
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
                ad_spend=18.0,
                net_profit=382.0,
            ),
            "profit_row": SimpleNamespace(
                realized_revenue=1000.0,
                has_real_manual_cost=False,
                gross_units=10,
                return_units=0,
                net_units=10,
                finance_rows=1,
            ),
            "primary_row": row1,
            "purchase_row": None,
        },
    )
    monkeypatch.setattr(
        service,
        "_build_card_money",
        lambda *args, **kwargs: CardMoneyBlock(
            revenue=1000.0,
            for_pay=900.0,
            ads=CardAdsBlock(
                source_spend=18.0,
                allocated_spend=18.0,
                capped_allocated_spend=18.0,
                raw_allocated_spend=18.0,
                overallocated_spend=0.0,
                unallocated_spend=0.0,
                spend=18.0,
                drr_percent=1.8,
                drr_percent_source=1.8,
                status="matched",
                allocation_status="matched",
                profit_allocation_status="matched",
                allocation_method="revenue_share",
                allocation_confidence="high",
                final_profit_allowed=False,
            ),
            profit=CardProfitBlock(
                before_ads=400.0,
                after_source_ads=382.0,
                after_allocated_ads=382.0,
                after_overhead=382.0,
                with_allocated_overhead=382.0,
                after_ads=382.0,
                margin_after_ads_percent=38.2,
                roi_after_ads_percent=50.0,
                roi_on_cogs_percent=50.0,
                stock_roi_percent=54.57,
                roas_percent=5555.0,
                confidence="medium",
            ),
            wb_expenses=CardExpenseBreakdown(
                commission=0.0,
                acquiring_fee=0.0,
                logistics=0.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                direct=0.0,
                account_level=0.0,
                allocated_overhead=0.0,
                unallocated=0.0,
                confidence="medium",
                reason="",
                status="matched",
            ),
            cogs=CardCogsBlock(
                unit_cost=0.0,
                estimated_cogs=0.0,
                truth_level="operator_baseline",
                cost_truth_label="Operator baseline",
                supplier_confirmed=False,
                business_trusted=False,
                confidence="medium",
                reason="supplier_not_confirmed",
            ),
            wb_expenses_total=0.0,
            stock_value=700.0,
        ),
    )
    monkeypatch.setattr(
        service,
        "_build_card_stock",
        lambda *args, **kwargs: CardStockBlock(quantity=12.0, quantity_full=12.0, stock_value=700.0, days_of_stock=19.0, stock_status="ok"),
    )
    monkeypatch.setattr(service, "_build_card_verdict", lambda *args, **kwargs: CardVerdict(status="preliminary_profitable", label="Preliminary", short_text="ok", confidence="medium"))
    monkeypatch.setattr(service, "_finality_for_row", lambda *args, **kwargs: FinalityBlock(profit_final=False, restock_final=False, price_final=False, reasons=["supplier_cost_not_confirmed"]))
    monkeypatch.setattr(
        service,
        "_article_trust_block",
        lambda **kwargs: ArticleTrustBlock(
            state=TRUST_STATE_TEST_ONLY,
            business_trusted=False,
            operational_trusted=True,
            financial_final=False,
            confidence="medium",
            blocked_reasons=[],
            cost_truth_level="operator_baseline",
            supplier_confirmed=False,
            finance_status="critical_mismatch",
            human_message="Provisional",
            reason="supplier cost not confirmed",
        ),
    )
    monkeypatch.setattr(
        service,
        "_article_money_answer",
        lambda **kwargs: MoneyCardAnswer(status="preliminary_profitable", title="Good", short_text="Card is profitable but provisional", decision="watch", next_step="Review article"),
    )
    monkeypatch.setattr(
        service,
        "_data_trust_for_row",
        lambda row: DataTrustInfo(state=row.trust_state, business_trusted=False, can_generate_business_actions=True, confidence="medium", blocked_reasons=[], human_message="Provisional"),
    )
    monkeypatch.setattr(
        service,
        "_primary_row_action",
        lambda *args, **kwargs: NextActionRead(
            id=1,
            action_type="WATCH",
            action_group="business",
            category="watch",
            priority="medium",
            status="new",
            title="Review article",
            what_to_do="Review article",
            why="Because provisional",
            business_reason="Because provisional",
            next_step="Review article",
            how_to_fix=[],
            expected_effect_amount=0.0,
            priority_score=50.0,
            required_cash=0.0,
            recommended_qty=0,
            unit_cost=0.0,
            current_stock=12.0,
            days_of_stock=19.0,
            lead_time_days=0,
            safety_days=0,
            confidence="medium",
            financial_final=False,
            deadline_hint="",
            deadline_at=None,
            linked_entity={},
            affected_nm_ids=[555],
            affected_sku_ids=[101, 102],
            blocked_reasons=[],
            money_effect={},
            source_endpoint="/money/articles/555",
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
    assert [item.nm_id for item in result.items] == [555]
    assert result.summary.economic_profitable_count == 1
    assert result.summary.final_profitable_count == 0
    assert result.items[0].financial_final is False
    assert result.items[0].ads.allocation_status == "matched"
    assert result.items[0].stock.stock_value == 700.0


@pytest.mark.asyncio
async def test_etap3_acceptance_article_detail_answers_next_step_question(monkeypatch) -> None:
    service = MoneyManagementService()
    monkeypatch.setattr(
        service,
        "article_detail",
        AsyncMock(
            return_value=SimpleNamespace(
                money_answer=MoneyCardAnswer(
                    status="profitable_but_overstocked",
                    title="Good but overstocked",
                    short_text="Card is profitable, but final profit is provisional",
                    decision="liquidate",
                    next_step="Reduce stock and close finance mismatch",
                ),
                actions=[
                    SimpleNamespace(what_to_do="Reduce stock"),
                    SimpleNamespace(what_to_do="Close finance mismatch"),
                ],
                trust=SimpleNamespace(financial_final=False),
            )
        ),
    )

    result = await service.article_detail(
        SimpleNamespace(),
        account_id=1,
        nm_id=777,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert result.money_answer.short_text
    assert result.money_answer.next_step == "Reduce stock and close finance mismatch"
    assert len(result.actions) == 2
    assert result.trust.financial_final is False


@pytest.mark.asyncio
async def test_etap3_acceptance_owner_dashboard_matches_summary_truth() -> None:
    service = ControlTowerService()
    summary = SimpleNamespace(
        meta=SimpleNamespace(
            data_trust=SimpleNamespace(
                can_generate_business_actions=True,
                blocked_reasons=[],
                confidence="medium",
            )
        ),
        answer=SimpleNamespace(
            business_status="provisional",
            title="Operationally usable, financially provisional",
            short_text="Can operate, but final profit is preliminary.",
            main_problem="Finance mismatch and supplier cost not confirmed",
            main_next_step="Close finance reconciliation",
        ),
        revenue_sources=SimpleNamespace(
            operational_revenue=1000.0,
            reconciliation_status="critical_mismatch",
            difference_percent=15.0,
        ),
        quality=SimpleNamespace(
            supplier_confirmed_cost_coverage_percent=0.0,
            supplier_cost_coverage_percent=0.0,
            ads_overallocated_spend=10.0,
            ads_allocation_percent_capped=100.0,
        ),
        kpis=SimpleNamespace(
            net_profit_after_overhead=470.0,
            margin_after_overhead_percent=47.0,
            roi_on_cogs_percent=89.0,
            ad_spend=100.0,
            stock_value=700.0,
            unallocated_expenses=80.0,
            overstock_value=0.0,
            negative_profit_sku_count=0,
            blocked_data_sku_count=0,
            unallocated_expense_ratio_percent=8.0,
        ),
        risk_summary=SimpleNamespace(risks=[]),
        store_answer=SimpleNamespace(
            where_money_went="Costs and ads",
            where_money_is_now="Stock and WB balance",
            what_to_do_today=["Close finance reconciliation"],
        ),
        next_actions=[],
    )
    actions_page = SimpleNamespace(
        summary={"critical": 2, "high": 3, "medium": 1, "low": 0, "money_saving": 1, "growth": 1, "watch": 0, "top_focus_count": 5},
        groups=SimpleNamespace(global_blockers=[], data_fix=[], money_saving=[], growth=[], watch=[]),
        items=[],
    )

    class _FakeMoneyService:
        async def summary(self, session, *, account_id: int, date_from, date_to):
            return summary

        async def today_actions(self, session, *, account_id: int, date_from, date_to, group_by: str, limit: int, offset: int):
            return actions_page

    service._money_service = lambda: _FakeMoneyService()

    owner = await service.owner_dashboard(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert owner.trust.business_status == summary.answer.business_status
    assert owner.trust_state == "operational_provisional"
    assert owner.financial_final is False
    assert owner.net_profit == pytest.approx(470.0)


@pytest.mark.asyncio
async def test_etap3_acceptance_price_and_purchase_guardrails(monkeypatch) -> None:
    service = ControlTowerService()
    monkeypatch.setattr(
        service.dashboard,
        "data_health",
        AsyncMock(
            return_value=SimpleNamespace(
                business_trusted=True,
                operational_trusted=True,
                financial_final=False,
                trust_state="operational_provisional",
                cost_trust_policy="operator_baseline",
                supplier_confirmed_revenue_coverage_percent=0.0,
                operator_baseline_revenue_coverage_percent=99.6,
                trusted_revenue_cost_coverage_percent=99.6,
                financial_final_blockers_total=2,
                final_profit_blockers_total=2,
                all_open_issues_total=10,
                blocking_open_issues_total=2,
            )
        ),
    )
    price_row = PriceSafetyRow(
        sku_id=1,
        nm_id=1001,
        vendor_code="SKU-1",
        title="SKU 1",
        current_price=18900.0,
        current_discounted_price=10962.0,
        average_sale_price=10962.0,
        break_even_price=3436.13,
        target_margin_price=4295.16,
        safe_price_gap=7525.87,
        estimated_margin_at_current_price=44.0,
        estimated=False,
        confidence="high",
        action_hint=None,
        price_source="wb_price_snapshot",
        calculation_state="computed",
        not_computable_reason=None,
        not_computable_reasons=[],
        data_state="ready",
        mapping_status="mapped",
    )
    monkeypatch.setattr(
        service,
        "_build_control_rows",
        AsyncMock(
            return_value=(
                [],
                {1: price_row},
                {
                    1: SimpleNamespace(
                        sku_id=1,
                        nm_id=1001,
                        vendor_code="SKU-1",
                        title="SKU 1",
                        status="LIQUIDATE",
                        decision="LIQUIDATE",
                        trust_state=TRUST_STATE_TEST_ONLY,
                        sales_velocity_daily=1.0,
                        available_stock=454.0,
                        in_transit_qty=0.0,
                        days_of_stock=180.0,
                        lead_time_days=14,
                        safety_days=7,
                        recommended_qty=0,
                        required_cash=0.0,
                        expected_profit=100.0,
                        risk="overstock",
                        reason="Overstock",
                        main_reason="Overstock",
                        next_step="Reduce stock",
                        confidence="medium",
                        decision_confidence="medium",
                        financial_final=False,
                        money_effect={"affected_stock_value": 1304998.0, "expected_cash_release": 1304998.0},
                    )
                },
                service.DEFAULT_SETTINGS,
            )
        ),
    )
    monkeypatch.setattr(service, "_control_cache_meta", lambda **kwargs: {})

    price_page = await service.list_price_safety(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )
    purchase_page = await service.list_purchase_plan(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="sku",
    )

    assert price_page.items[0].current_price == 18900.0
    assert price_page.items[0].price_source == "wb_price_snapshot"
    assert purchase_page.items[0].status == "LIQUIDATE"
    assert purchase_page.items[0].required_cash == 0.0
