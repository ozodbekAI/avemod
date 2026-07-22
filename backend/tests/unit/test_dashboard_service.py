from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from unittest.mock import AsyncMock

from app.services.dashboard import DashboardService
from app.schemas.dashboard import ArticleManualCostMatch, SKUProfitabilityRow


def test_profit_formula_shape() -> None:
    service = DashboardService()
    bucket = {
        "for_pay": Decimal("100"),
        "acquiring_fee": Decimal("5"),
        "storage": Decimal("2"),
        "penalties": Decimal("1"),
        "deductions": Decimal("3"),
        "ad_spend": Decimal("10"),
        "estimated_cogs": Decimal("20"),
    }
    profit = (
        bucket["for_pay"]
        - bucket["acquiring_fee"]
        - bucket["storage"]
        - bucket["penalties"]
        - bucket["deductions"]
        - bucket["ad_spend"]
        - bucket["estimated_cogs"]
    )
    assert float(profit) == 59.0


def test_match_cost_uses_vendor_code_before_nm_and_barcode() -> None:
    service = DashboardService()
    costs = [
        SimpleNamespace(
            vendor_code="A-1",
            nm_id=100,
            barcode="123",
            unit_cost=Decimal("10"),
            valid_from=date(2026, 1, 1),
            valid_to=None,
            currency="RUB",
            comment=None,
        ),
        SimpleNamespace(
            vendor_code="B-2",
            nm_id=100,
            barcode="123",
            unit_cost=Decimal("20"),
            valid_from=date(2026, 1, 1),
            valid_to=None,
            currency="RUB",
            comment=None,
        ),
    ]

    matched, source = service._match_cost(
        costs,
        vendor_code="A-1",
        nm_id=100,
        barcode="123",
        at_date=date(2026, 5, 14),
    )

    assert matched is costs[0]
    assert source == "vendor_code"


@pytest.mark.asyncio
async def test_sku_profitability_page_filters_and_paginates() -> None:
    service = DashboardService()
    service._sku_profitability_page_version_hash = AsyncMock(return_value="v1")
    service.sku_profitability = AsyncMock(
        return_value=[
            SKUProfitabilityRow(
                sku_id=1,
                nm_id=101,
                vendor_code="ABC-1",
                barcode="111",
                title="Alpha",
                brand="Brand A",
                subject_name="Cat A",
                finance_rows=1,
                gross_units=1,
                return_units=0,
                net_units=1,
                realized_revenue=150.0,
                for_pay=140.0,
                commission=0.0,
                acquiring_fee=0.0,
                logistics=0.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                estimated_profit=150.0,
                margin_percent=15.0,
                ad_spend=10.0,
                estimated_cogs=50.0,
                matched_cost_rows=1,
                roi_percent=10.0,
                drr_percent=5.0,
                closing_stock_qty=1.0,
                has_manual_cost=True,
                cost_source="operator_baseline",
            ),
            SKUProfitabilityRow(
                sku_id=2,
                nm_id=202,
                vendor_code="XYZ-2",
                barcode="222",
                title="Beta",
                brand="Brand B",
                subject_name="Cat B",
                finance_rows=0,
                gross_units=0,
                return_units=0,
                net_units=0,
                realized_revenue=0.0,
                for_pay=0.0,
                commission=0.0,
                acquiring_fee=0.0,
                logistics=0.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                estimated_profit=None,
                margin_percent=None,
                ad_spend=5.0,
                estimated_cogs=0.0,
                matched_cost_rows=0,
                roi_percent=None,
                drr_percent=None,
                closing_stock_qty=None,
                has_manual_cost=False,
                cost_source=None,
            ),
        ]
    )
    service.data_health = AsyncMock(
        return_value=SimpleNamespace(
            business_trusted=True,
            operational_trusted=True,
            financial_final=False,
            trust_state="operational_provisional",
            cost_trust_policy="operator_baseline",
            supplier_confirmed_revenue_coverage_percent=0.0,
            operator_baseline_revenue_coverage_percent=99.6,
            trusted_revenue_cost_coverage_percent=99.6,
            financial_final_blockers_total=1,
            final_profit_blockers_total=1,
            blocked_reasons=[],
        )
    )

    page = await service.sku_profitability_page(
        None,  # type: ignore[arg-type]
        account_id=1,
        search="ABC",
        has_manual_cost=True,
        sort="profit_desc",
        limit=10,
        offset=0,
    )

    assert page.total == 1
    assert len(page.items) == 1
    assert page.items[0].vendor_code == "ABC-1"


@pytest.mark.asyncio
async def test_sku_profitability_page_reuses_cached_response(monkeypatch) -> None:
    service = DashboardService()
    monkeypatch.setattr(service, "_sku_profitability_page_version_hash", AsyncMock(return_value="v1"))
    service.sku_profitability = AsyncMock(
        return_value=[
            SKUProfitabilityRow(
                sku_id=1,
                nm_id=101,
                vendor_code="ABC-1",
                barcode="111",
                title="Alpha",
                brand="Brand A",
                subject_name="Cat A",
                finance_rows=1,
                gross_units=1,
                return_units=0,
                net_units=1,
                realized_revenue=150.0,
                for_pay=140.0,
                commission=0.0,
                acquiring_fee=0.0,
                logistics=0.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                estimated_profit=150.0,
                margin_percent=15.0,
                ad_spend=10.0,
                estimated_cogs=50.0,
                matched_cost_rows=1,
                roi_percent=10.0,
                drr_percent=5.0,
                closing_stock_qty=1.0,
                has_manual_cost=True,
                cost_source="operator_baseline",
            ),
        ]
    )
    service.data_health = AsyncMock(
        return_value=SimpleNamespace(
            business_trusted=True,
            operational_trusted=True,
            financial_final=False,
            trust_state="operational_provisional",
            cost_trust_policy="operator_baseline",
            supplier_confirmed_revenue_coverage_percent=0.0,
            operator_baseline_revenue_coverage_percent=99.6,
            trusted_revenue_cost_coverage_percent=99.6,
            financial_final_blockers_total=1,
            final_profit_blockers_total=1,
            blocked_reasons=[],
        )
    )

    first = await service.sku_profitability_page(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )
    second = await service.sku_profitability_page(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert second.data_version_hash == "v1"
    assert service.sku_profitability.await_count == 1
    assert service.data_health.await_count == 1


def test_article_daily_economics_subtracts_source_spend_once_not_duplicated_mart_spend() -> None:
    service = DashboardService()
    mart_rows = [
        SimpleNamespace(
            final_revenue=Decimal("250"),
            final_for_pay=Decimal("225"),
            commission=Decimal("0"),
            acquiring_fee=Decimal("0"),
            logistics=Decimal("0"),
            storage=Decimal("0"),
            paid_acceptance=Decimal("0"),
            penalties=Decimal("0"),
            deductions=Decimal("0"),
            additional_payments=Decimal("0"),
            ad_spend=Decimal("1000"),
            estimated_cogs=Decimal("50"),
            estimated_profit_before_ads=Decimal("150"),
            estimated_profit_after_ads=Decimal("-850"),
            has_manual_cost=True,
            stat_date=date(2026, 5, 20),
            final_sales_qty=1,
            final_return_qty=0,
            final_net_qty=1,
        )
        for _ in range(4)
    ]
    ad_rows = [
        SimpleNamespace(stat_date=date(2026, 5, 20), sum=Decimal("1000")),
    ]

    economics = service._build_article_daily_economics(mart_rows, ad_rows=ad_rows)

    assert economics is not None
    assert economics.ad_spend == 1000.0
    assert economics.raw_ad_spend == 4000.0
    assert economics.overallocated_ad_spend == 3000.0
    assert economics.estimated_profit_before_ads == 600.0
    assert economics.estimated_profit_after_ads == -400.0
    assert economics.final_profit_allowed is False


def test_article_manual_cost_match_propagates_placeholder_flags() -> None:
    manual_cost = DashboardService._build_article_manual_cost_match(
        SimpleNamespace(
            unit_cost=Decimal("2200"),
            cost_price=Decimal("2200"),
            seller_other_expense=Decimal("0"),
            packaging_cost=Decimal("0"),
            inbound_logistics_cost=Decimal("0"),
            supplier="AUTO_TEMPLATE",
            currency="RUB",
            valid_from=date(2026, 4, 16),
            valid_to=None,
            comment="placeholder",
            is_placeholder=True,
            is_business_trusted=False,
        ),
        source="vendor_code+nm_id+barcode+tech_size",
        total_unit_cost=Decimal("2200"),
    )

    assert manual_cost is not None
    assert manual_cost.seller_other_expense == 0.0
    assert manual_cost.is_placeholder is True
    assert manual_cost.is_business_trusted is False


def test_article_daily_economics_counts_distinct_days() -> None:
    def item(stat_date, revenue):
        return SimpleNamespace(
            stat_date=stat_date,
            final_sales_qty=1,
            final_return_qty=0,
            final_net_qty=1,
            final_revenue=Decimal(revenue),
            final_for_pay=Decimal(revenue),
            commission=Decimal("0"),
            acquiring_fee=Decimal("0"),
            logistics=Decimal("0"),
            storage=Decimal("0"),
            paid_acceptance=Decimal("0"),
            penalties=Decimal("0"),
            deductions=Decimal("0"),
            additional_payments=Decimal("0"),
            ad_spend=Decimal("0"),
            estimated_cogs=Decimal("10"),
            estimated_profit_before_ads=Decimal("90"),
            estimated_profit_after_ads=Decimal("90"),
            has_manual_cost=True,
        )
    economics = DashboardService._build_article_daily_economics(
        [
            item(date(2026, 5, 1), "100"),
            item(date(2026, 5, 1), "100"),
            item(date(2026, 5, 2), "100"),
        ]
    )

    assert economics is not None
    assert economics.days_count == 2


@pytest.mark.asyncio
async def test_sku_profitability_does_not_require_cost_for_zero_activity_rows() -> None:
    service = DashboardService()
    zero_activity_row = SimpleNamespace(
        account_id=1,
        stat_date=date(2026, 5, 20),
        sku_id=19098,
        nm_id=323108780,
        vendor_code="SKU-ZERO",
        barcode="BAR-ZERO",
        title="Zero activity variant",
        brand="Avemod",
        subject_name="Kostyumy",
        finance_rows=0,
        final_sales_qty=0,
        final_return_qty=0,
        final_net_qty=0,
        final_revenue=Decimal("0"),
        final_for_pay=Decimal("0"),
        sale_rows=0,
        commission=Decimal("0"),
        acquiring_fee=Decimal("0"),
        logistics=Decimal("0"),
        paid_acceptance=Decimal("0"),
        storage=Decimal("0"),
        penalties=Decimal("0"),
        deductions=Decimal("0"),
        additional_payments=Decimal("0"),
        wb_commission=Decimal("0"),
        payment_processing=Decimal("0"),
        pvz_reward=Decimal("0"),
        wb_logistics=Decimal("0"),
        wb_logistics_rebill=Decimal("0"),
        acceptance=Decimal("0"),
        penalty=Decimal("0"),
        deduction=Decimal("0"),
        marketing_deduction=Decimal("0"),
        loyalty=Decimal("0"),
        other_wb_expenses=Decimal("0"),
        total_wb_expenses=Decimal("0"),
        ad_spend=Decimal("0"),
        ad_spend_operational=Decimal("0"),
        ad_spend_finance=Decimal("0"),
        ad_spend_final=Decimal("0"),
        ad_spend_source="",
        ad_spend_delta=Decimal("0"),
        estimated_cogs=Decimal("0"),
        seller_cogs=Decimal("0"),
        seller_other_expense=Decimal("0"),
        total_seller_expenses=Decimal("0"),
        estimated_profit_before_ads=Decimal("0"),
        estimated_profit_after_ads=Decimal("0"),
        net_profit_after_all_expenses=Decimal("0"),
        has_manual_cost=False,
        has_real_manual_cost=False,
        has_placeholder_cost=False,
        cost_source=None,
        final_revenue_source=None,
        closing_stock_qty=Decimal("0"),
    )
    session = _FakeSession(
        [
            _FakeExecuteResult(scalars_list=[zero_activity_row]),
            _FakeExecuteResult(scalars_list=[]),
            _FakeExecuteResult(scalar=SimpleNamespace(settings_json={"cost_trust_policy": "owner_approved_final"})),
        ]
    )

    rows = await service.sku_profitability(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert len(rows) == 1
    assert "missing_manual_cost" not in rows[0].blocked_reasons
    assert rows[0].has_manual_cost is True
    assert rows[0].has_real_manual_cost is True


@pytest.mark.asyncio
async def test_sku_profitability_subtracts_read_time_source_ads_from_profit() -> None:
    service = DashboardService()
    mart_row = SimpleNamespace(
        account_id=1,
        stat_date=date(2026, 5, 20),
        sku_id=19099,
        nm_id=323108780,
        vendor_code="SKU-ADS",
        barcode="BAR-ADS",
        title="Ads allocation row",
        brand="Avemod",
        subject_name="Kostyumy",
        finance_rows=1,
        final_sales_qty=1,
        final_return_qty=0,
        final_net_qty=1,
        final_revenue=Decimal("100"),
        final_for_pay=Decimal("90"),
        sale_rows=1,
        commission=Decimal("10"),
        acquiring_fee=Decimal("0"),
        logistics=Decimal("0"),
        paid_acceptance=Decimal("0"),
        storage=Decimal("0"),
        penalties=Decimal("0"),
        deductions=Decimal("0"),
        additional_payments=Decimal("0"),
        wb_commission=Decimal("10"),
        payment_processing=Decimal("0"),
        pvz_reward=Decimal("0"),
        wb_logistics=Decimal("0"),
        wb_logistics_rebill=Decimal("0"),
        acceptance=Decimal("0"),
        penalty=Decimal("0"),
        deduction=Decimal("0"),
        marketing_deduction=Decimal("0"),
        loyalty=Decimal("0"),
        other_wb_expenses=Decimal("0"),
        total_wb_expenses=Decimal("10"),
        ad_spend=Decimal("0"),
        ad_spend_operational=Decimal("0"),
        ad_spend_finance=Decimal("0"),
        ad_spend_final=Decimal("0"),
        ad_spend_source="",
        ad_spend_delta=Decimal("0"),
        estimated_cogs=Decimal("40"),
        seller_cogs=Decimal("40"),
        seller_other_expense=Decimal("0"),
        total_seller_expenses=Decimal("40"),
        estimated_profit_before_ads=Decimal("50"),
        estimated_profit_after_ads=Decimal("50"),
        net_profit_after_all_expenses=Decimal("50"),
        has_manual_cost=True,
        has_real_manual_cost=True,
        has_placeholder_cost=False,
        cost_source="supplier_upload",
        final_revenue_source="finance",
        closing_stock_qty=Decimal("1"),
    )
    session = _FakeSession(
        [
            _FakeExecuteResult(scalars_list=[mart_row]),
            _FakeExecuteResult(
                scalar=SimpleNamespace(
                    settings_json={"cost_trust_policy": "owner_approved_final"}
                )
            ),
            _FakeExecuteResult(rows=[(323108780, Decimal("30"))]),
        ]
    )

    rows = await service.sku_profitability(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert len(rows) == 1
    assert rows[0].ad_spend_final == 30.0
    assert rows[0].estimated_profit == 20.0
    assert rows[0].net_profit_after_all_expenses == 20.0
    assert rows[0].margin_percent == 20.0
    assert rows[0].roi_percent == 50.0


def test_article_finance_summary_aligns_with_mart_rows() -> None:
    mart_row = SimpleNamespace(
        final_sales_qty=2,
        final_return_qty=1,
        final_net_qty=1,
        final_revenue=Decimal("150"),
        final_for_pay=Decimal("140"),
        commission=Decimal("10"),
        acquiring_fee=Decimal("3"),
        logistics=Decimal("4"),
        paid_acceptance=Decimal("2"),
        storage=Decimal("1"),
        penalties=Decimal("0.5"),
        deductions=Decimal("0.25"),
        additional_payments=Decimal("0"),
        estimated_cogs=Decimal("50"),
        estimated_profit_before_ads=Decimal("79.25"),
        has_manual_cost=True,
    )

    finance = DashboardService._build_article_finance_summary([mart_row], [])

    assert finance.realized_revenue == 150.0
    assert finance.for_pay == 140.0
    assert finance.estimated_cogs == 50.0
    assert finance.estimated_profit_before_ads == 79.25


def test_article_reconciliation_uses_finance_report_total_for_match_check() -> None:
    mart_row = SimpleNamespace(final_revenue=Decimal("150"))
    finance_row = SimpleNamespace(
        retail_amount=Decimal("120"),
        doc_type_name="Продажа",
        is_reconcilable=True,
    )

    reconciliation = DashboardService._build_article_reconciliation_summary(
        [mart_row],
        [],
        finance_rows=[finance_row],
    )

    assert reconciliation.mart_revenue_total == 150.0
    assert reconciliation.article_revenue_total == 150.0
    assert reconciliation.finance_report_revenue_total == 120.0
    assert reconciliation.difference_amount == -30.0
    assert reconciliation.revenue_matches_mart is False


class _FakeExecuteResult:
    def __init__(self, *, scalar=None, scalars_list=None, rows=None):
        self._scalar = scalar
        self._scalars_list = list(scalars_list or [])
        self._rows = list(rows or [])

    def scalar_one(self):
        return self._scalar

    def scalar_one_or_none(self):
        return self._scalar

    def one(self):
        return self._scalar

    def scalars(self):
        return self._scalars_list

    def all(self):
        return self._rows


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _stmt):
        if not self._results:
            raise AssertionError("Unexpected extra execute() call")
        return self._results.pop(0)

    async def get(self, _model, _identity):
        return None


@pytest.mark.asyncio
async def test_data_health_uses_dq_summary_blockers_as_source_of_truth() -> None:
    service = DashboardService()
    service._get_data_quality_service = lambda: SimpleNamespace(  # type: ignore[method-assign]
        list_issue_summary=AsyncMock(
            return_value={
                "financial_final_blockers_total": 27,
                "blocking_open_issues_total": 27,
            }
        )
    )
    session = _FakeSession(
        [
            _FakeExecuteResult(
                scalar=SimpleNamespace(settings_json={"cost_trust_policy": "owner_approved_final"})
            ),
            _FakeExecuteResult(
                scalars_list=[
                    SimpleNamespace(
                        code="manual_cost_old_fields_used",
                        severity="warning",
                        payload={},
                        resolved_at=None,
                        effective_financial_final_blocker=None,
                    )
                ]
            ),
            _FakeExecuteResult(scalars_list=[]),
            _FakeExecuteResult(scalars_list=[]),
            _FakeExecuteResult(scalar=(10, 10)),
            _FakeExecuteResult(scalar=0),
            _FakeExecuteResult(scalar=10),
            _FakeExecuteResult(scalar=10),
            _FakeExecuteResult(
                scalar=(
                    10,
                    0,
                    Decimal("1000"),
                    Decimal("0"),
                    Decimal("1000"),
                    Decimal("0"),
                )
            ),
            _FakeExecuteResult(scalar=1),
            _FakeExecuteResult(scalar=None),
            _FakeExecuteResult(scalar=datetime(2026, 5, 31)),
        ]
    )

    result = await service.data_health(
        session,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result.financial_final is False
    assert result.trust_state == "operational_provisional"
    assert result.financial_final_blockers_total == 27
    assert result.blocking_open_issues_total == 27
    assert result.data_health_blockers_total == 0
    assert result.dq_summary_blockers_total == 27
    assert result.trust_consistency_status == "mismatch"
    assert result.trust_consistency_warning is not None
    assert "dq/issues/summary" in result.trust_consistency_warning
    assert result.data_quality_summary.financial_final_blockers_total == 27
    assert result.data_quality_summary.blocking_open_issues_total == 27


@pytest.mark.asyncio
async def test_article_audit_does_not_use_mart_rows_before_query(monkeypatch) -> None:
    service = DashboardService()
    monkeypatch.setattr(service, "_load_current_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_current_sales", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_cost_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service,
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
                financial_final_blockers_total=1,
                final_profit_blockers_total=1,
                blocked_reasons=[],
            )
        ),
    )

    session = _FakeSession(
        [
            _FakeExecuteResult(scalars_list=[]),  # core skus
            _FakeExecuteResult(scalar=None),  # price
            _FakeExecuteResult(scalar=None),  # product card
            _FakeExecuteResult(scalar=None),  # latest stock row
            _FakeExecuteResult(scalars_list=[]),  # price sizes
            _FakeExecuteResult(scalars_list=[]),  # finance rows
            _FakeExecuteResult(scalars_list=[]),  # ad rows
            _FakeExecuteResult(scalars_list=[]),  # funnel rows
            _FakeExecuteResult(scalars_list=[]),  # mart rows
            _FakeExecuteResult(scalars_list=[]),  # stock rows
            _FakeExecuteResult(scalars_list=[]),  # issue rows
        ]
    )

    result = await service.article_audit(
        session,  # type: ignore[arg-type]
        account_id=1,
        nm_id=223205606,
        date_from=date(2026, 4, 28),
        date_to=date(2026, 5, 28),
    )

    assert result.identity.nm_id == 223205606
    assert result.ads.spend == 0.0
    assert result.daily_economics is None


def test_build_article_finance_summary_falls_back_to_raw_finance_rows_for_finance_truth() -> None:
    finance_row = SimpleNamespace(
        sale_dt=None,
        rr_date=date(2026, 5, 18),
        is_reconcilable=True,
        doc_type_name="Продажа",
        retail_amount=Decimal("565941.05"),
        for_pay=Decimal("450000"),
        quantity=3,
        delivery_service=Decimal("205974.56"),
        rebill_logistic_cost=Decimal("5746.59"),
        paid_storage=Decimal("0"),
        paid_acceptance=Decimal("0"),
        penalty=Decimal("1319.60"),
        deduction=Decimal("0"),
        additional_payment=Decimal("0"),
        acquiring_fee=Decimal("33169.28"),
        ppvz_sales_commission=Decimal("19308.26678688524"),
        seller_oper_name="Продажа",
        bonus_type_name=None,
        payload={},
        account_id=1,
        report_id=10,
        rrd_id=20,
        nm_id=223205606,
        barcode="1",
        srid="SRID-1",
        order_id=111,
        currency="RUB",
    )
    mart_row = SimpleNamespace(
        final_sales_qty=3,
        final_return_qty=0,
        final_net_qty=3,
        final_revenue=Decimal("542650.07"),
        revenue_final=Decimal("542650.07"),
        final_for_pay=Decimal("450000"),
        wb_commission=Decimal("0"),
        payment_processing=Decimal("0"),
        pvz_reward=Decimal("0"),
        wb_logistics=Decimal("0"),
        wb_logistics_rebill=Decimal("0"),
        acceptance=Decimal("0"),
        penalty=Decimal("0"),
        deduction=Decimal("0"),
        marketing_deduction=Decimal("0"),
        loyalty=Decimal("0"),
        other_wb_expenses=Decimal("0"),
        commission=Decimal("0"),
        acquiring_fee=Decimal("0"),
        logistics=Decimal("0"),
        paid_acceptance=Decimal("0"),
        storage=Decimal("0"),
        penalties=Decimal("0"),
        deductions=Decimal("0"),
        additional_payments=Decimal("0"),
        estimated_cogs=Decimal("100"),
        seller_cogs=Decimal("100"),
        seller_other_expense=Decimal("10"),
        ad_spend_operational=Decimal("0"),
        ad_spend_finance=Decimal("0"),
        ad_spend_final=Decimal("0"),
        ad_spend=Decimal("0"),
        has_manual_cost=True,
        net_profit_after_all_expenses=Decimal("50"),
    )

    result = DashboardService._build_article_finance_summary([mart_row], [finance_row])  # type: ignore[arg-type]

    assert result.realized_revenue == pytest.approx(565941.05)
    assert result.total_wb_expenses == pytest.approx(265518.29678688524)
    assert result.wb_logistics == pytest.approx(205974.56)
    assert result.payment_processing == pytest.approx(33169.28)


@pytest.mark.asyncio
async def test_article_audit_preserves_global_blocker_counts_even_for_owner_approved_cost_policy(monkeypatch) -> None:
    service = DashboardService()
    monkeypatch.setattr(service, "_load_current_orders", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_current_sales", AsyncMock(return_value=[]))
    monkeypatch.setattr(service, "_load_cost_rows", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        service,
        "_build_article_manual_cost_match",
        lambda matched_cost, **kwargs: ArticleManualCostMatch(
            matched=True,
            source="manual",
            unit_cost=10.0,
            cost_price=10.0,
            seller_other_expense=0.0,
            packaging_cost=0.0,
            inbound_logistics_cost=0.0,
            total_unit_cost=10.0,
            supplier="REAL",
            currency="RUB",
            valid_from=None,
            valid_to=None,
            comment=None,
            is_placeholder=False,
            is_business_trusted=True,
            supplier_confirmed=True,
            confidence="high",
            reason="test",
            cost_truth_level="owner_approved_current_cost",
            cost_truth_label="Owner approved",
        ),
    )
    monkeypatch.setattr(
        service,
        "data_health",
        AsyncMock(
            return_value=SimpleNamespace(
                operational_trusted=True,
                business_trusted=True,
                financial_final=False,
                trust_state="operational_provisional",
                cost_trust_policy="owner_approved_final",
                supplier_confirmed_revenue_coverage_percent=100.0,
                operator_baseline_revenue_coverage_percent=100.0,
                trusted_revenue_cost_coverage_percent=100.0,
                financial_final_blockers_total=8,
                blocking_open_issues_total=8,
                all_open_issues_total=2200,
                blocked_reasons=[],
            )
        ),
    )

    session = _FakeSession(
        [
            _FakeExecuteResult(scalars_list=[]),  # core skus
            _FakeExecuteResult(scalar=None),  # price
            _FakeExecuteResult(scalar=None),  # product card
            _FakeExecuteResult(scalar=None),  # latest stock row
            _FakeExecuteResult(scalars_list=[]),  # price sizes
            _FakeExecuteResult(scalars_list=[]),  # finance rows
            _FakeExecuteResult(scalars_list=[]),  # ad rows
            _FakeExecuteResult(scalars_list=[]),  # funnel rows
            _FakeExecuteResult(scalars_list=[]),  # mart rows
            _FakeExecuteResult(scalars_list=[]),  # stock rows
            _FakeExecuteResult(scalars_list=[]),  # issue rows
        ]
    )

    result = await service.article_audit(
        session,  # type: ignore[arg-type]
        account_id=1,
        nm_id=223205606,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result.financial_final is False
    assert result.financial_final_blockers_total == 8
    assert result.blocking_open_issues_total == 8


def test_article_stock_aggregation_keeps_in_transit_rows_when_total_row_exists() -> None:
    quantity, quantity_full, in_way_to_client, in_way_from_client = DashboardService._aggregate_article_stock_rows(
        [
            SimpleNamespace(
                warehouse_name="Всего находится на складах",
                quantity=None,
                quantity_full=Decimal("29"),
                in_way_to_client=None,
                in_way_from_client=None,
            ),
            SimpleNamespace(
                warehouse_name="В пути до получателей",
                quantity=None,
                quantity_full=None,
                in_way_to_client=Decimal("10"),
                in_way_from_client=None,
            ),
            SimpleNamespace(
                warehouse_name="В пути возвраты на склад WB",
                quantity=None,
                quantity_full=None,
                in_way_to_client=None,
                in_way_from_client=Decimal("12"),
            ),
        ]
    )

    assert quantity == Decimal("29")
    assert quantity_full == Decimal("29")
    assert in_way_to_client == Decimal("10")
    assert in_way_from_client == Decimal("12")


def test_business_trusted_stays_false_while_unclassified_error_issues_remain() -> None:
    open_issue = SimpleNamespace(severity="error", payload={"classificationStatus": "detected"})

    is_trusted = DashboardService._is_business_trusted(
        trusted_revenue_coverage_percent=100.0,
        failed_domains=[],
        unmatched_sku_count=0,
        latest_stocks_status="completed",
        open_issues=[open_issue],
    )

    assert is_trusted is False


def test_business_trusted_allows_classified_blockers_to_be_excluded() -> None:
    classified_issue = SimpleNamespace(severity="error", payload={"classificationStatus": "classified"})

    is_trusted = DashboardService._is_business_trusted(
        trusted_revenue_coverage_percent=100.0,
        failed_domains=[],
        unmatched_sku_count=0,
        latest_stocks_status="completed",
        open_issues=[classified_issue],
    )

    assert is_trusted is True


def test_supply_source_level_unmatched_issue_is_not_business_blocker() -> None:
    issue = SimpleNamespace(
        code="unmatched_sku",
        severity="error",
        payload={
            "classificationStatus": "detected",
            "sourceKind": "source_level",
            "sourceDomains": ["supplies"],
            "classificationReason": "missing_nm_id",
        },
    )

    assert DashboardService._issue_blocks_business_analysis(issue) is False


def test_supply_source_level_unmatched_issue_is_not_financial_final_blocker_even_if_stored_true() -> None:
    issue = SimpleNamespace(
        code="unmatched_sku",
        severity="error",
        effective_financial_final_blocker=True,
        payload={
            "classificationStatus": "detected",
            "sourceKind": "source_level",
            "sourceDomains": ["supplies"],
            "classificationReason": "missing_nm_id",
        },
    )

    assert DashboardService._issue_is_financial_final_blocker(issue) is False


def test_order_without_sale_or_return_is_not_financial_final_blocker() -> None:
    issue = SimpleNamespace(
        code="order_without_sale_or_return",
        severity="error",
        effective_financial_final_blocker=True,
        payload={"classificationStatus": "classified", "classificationReason": "missing_followup"},
    )

    assert DashboardService._issue_is_financial_final_blocker(issue) is False


def test_payout_only_finance_mismatch_is_not_financial_final_blocker() -> None:
    issue = SimpleNamespace(
        code="finance_reconciliation_mismatch",
        severity="error",
        effective_financial_final_blocker=True,
        payload={
            "classificationStatus": "classified",
            "classificationReason": "real_mismatch",
            "revenueDelta": "0",
            "forPayDelta": "456.43",
        },
    )

    assert DashboardService._issue_is_financial_final_blocker(issue) is False


def test_transient_429_failed_domain_is_tolerated_when_recent_success_exists() -> None:
    status = SimpleNamespace(
        latest_status="failed",
        last_successful_at=datetime(2026, 5, 21, 10, 0, 0),
        latest_error_text="WB API error 429: Too Many Requests",
    )

    assert DashboardService._is_transient_failed_domain(status, reference_at=datetime(2026, 5, 21, 12, 0, 0)) is True


def test_action_recommendation_foreign_keys_resolve_after_model_registry_load() -> None:
    from app.core.model_registry import load_all_models
    from app.models.control_tower import ActionRecommendation

    load_all_models()

    foreign_table_names = {fk.column.table.name for fk in ActionRecommendation.__table__.foreign_keys}

    assert "wb_accounts" in foreign_table_names
    assert "core_sku" in foreign_table_names


def test_article_daily_economics_prefers_finance_marketing_without_double_count() -> None:
    service = DashboardService()
    mart_rows = [
        SimpleNamespace(
            stat_date=date(2026, 5, 20),
            final_sales_qty=2,
            final_return_qty=0,
            final_net_qty=2,
            final_revenue=Decimal("1000"),
            final_for_pay=Decimal("900"),
            wb_commission=Decimal("50"),
            payment_processing=Decimal("10"),
            pvz_reward=Decimal("0"),
            wb_logistics=Decimal("80"),
            wb_logistics_rebill=Decimal("0"),
            storage=Decimal("20"),
            acceptance=Decimal("0"),
            penalty=Decimal("0"),
            deduction=Decimal("0"),
            marketing_deduction=Decimal("40"),
            loyalty=Decimal("0"),
            other_wb_expenses=Decimal("0"),
            ad_spend_operational=Decimal("120"),
            ad_spend_finance=Decimal("40"),
            ad_spend_final=Decimal("40"),
            ad_spend_source="finance_report",
            ad_spend_delta=Decimal("80"),
            ad_spend=Decimal("40"),
            additional_payments=Decimal("0"),
            seller_cogs=Decimal("300"),
            seller_other_expense=Decimal("20"),
            estimated_cogs=Decimal("300"),
            estimated_profit_before_ads=Decimal("520"),
            estimated_profit_after_ads=Decimal("480"),
            net_profit_after_all_expenses=Decimal("480"),
            has_manual_cost=True,
        )
    ]
    ad_rows = [SimpleNamespace(stat_date=date(2026, 5, 20), sum=Decimal("120"))]

    economics = service._build_article_daily_economics(mart_rows, ad_rows=ad_rows)

    assert economics is not None
    assert economics.total_wb_expenses == 160.0
    assert economics.total_seller_costs == 320.0
    assert economics.ad_spend_operational == 120.0
    assert economics.ad_spend_finance == 40.0
    assert economics.ad_spend_final == 40.0
    assert economics.ad_spend_source == "finance_report"
    assert economics.estimated_profit_after_ads == 480.0
    assert economics.net_profit_after_all_expenses == 480.0


def test_article_daily_economics_additional_income_increases_profit() -> None:
    service = DashboardService()
    mart_rows = [
        SimpleNamespace(
            stat_date=date(2026, 5, 21),
            final_sales_qty=1,
            final_return_qty=0,
            final_net_qty=1,
            final_revenue=Decimal("500"),
            final_for_pay=Decimal("450"),
            wb_commission=Decimal("25"),
            payment_processing=Decimal("5"),
            pvz_reward=Decimal("0"),
            wb_logistics=Decimal("40"),
            wb_logistics_rebill=Decimal("0"),
            storage=Decimal("10"),
            acceptance=Decimal("0"),
            penalty=Decimal("0"),
            deduction=Decimal("0"),
            marketing_deduction=Decimal("0"),
            loyalty=Decimal("0"),
            other_wb_expenses=Decimal("0"),
            additional_payments=Decimal("15"),
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
            net_profit_after_all_expenses=Decimal("215"),
            has_manual_cost=True,
        )
    ]

    economics = service._build_article_daily_economics(mart_rows, ad_rows=None)

    assert economics is not None
    assert economics.additional_income == 15.0
    assert economics.total_wb_expenses == 80.0
    assert economics.net_profit_after_all_expenses == 215.0
