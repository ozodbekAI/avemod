from __future__ import annotations

import asyncio
from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi import HTTPException
import pytest
from sqlalchemy.exc import ProgrammingError

from app.core.manual_cost_math import manual_cost_total_unit_cost
from app.core.time import utcnow
from app.schemas.control_tower import PriceSafetyRow, PriceSimulationRequest, PurchasePlanRow
from app.services.control_tower import CachedControlRowsSnapshot, ControlTowerService, PriceSnapshot
from app.services.trust import TRUST_STATE_DATA_BLOCKED, TRUST_STATE_TEST_ONLY, TRUST_STATE_TRUSTED


def _purchase_plan_row(
    *,
    sku_id: int,
    status: str,
    nm_id: int | None = None,
    reason: str = "",
    risk: str | None = None,
    required_cash: float = 0.0,
    expected_profit: float | None = 0.0,
    trust_state: str = TRUST_STATE_TRUSTED,
    missing_data: list[str] | None = None,
    cost_source: str | None = None,
    cost_truth_level: str | None = None,
) -> PurchasePlanRow:
    return PurchasePlanRow(
        sku_id=sku_id,
        nm_id=nm_id if nm_id is not None else 1000 + sku_id,
        vendor_code=f"SKU-{sku_id}",
        title=f"SKU {sku_id}",
        status=status,
        decision=status,
        trust_state=trust_state,
        sales_velocity_daily=1.0,
        available_stock=5.0,
        in_transit_qty=0.0,
        days_of_stock=10.0,
        lead_time_days=14,
        safety_days=7,
        recommended_qty=3 if status == "REORDER" else 0,
        required_cash=required_cash,
        expected_profit=expected_profit,
        risk=risk,
        reason=reason,
        main_reason=reason,
        missing_data=list(missing_data or []),
        missing_fields=list(missing_data or []),
        wait_data_reasons=list(missing_data or []),
        confidence="high",
        decision_confidence="high",
        cost_source=cost_source,
        cost_truth=cost_truth_level,
        cost_truth_level=cost_truth_level,
        financial_final=status != "WAIT_DATA",
    )


def test_control_tower_classification_can_return_new_sku() -> None:
    service = ControlTowerService()

    status = service._classify_sku_status(
        trust_state=TRUST_STATE_TRUSTED,
        profit=Decimal("120"),
        days_of_stock=Decimal("30"),
        ad_spend=Decimal("0"),
        safe_price_gap=Decimal("50"),
        overstock_threshold_days=90,
        finance_rows=2,
        net_units=2,
    )

    assert status == "NEW_SKU"


def test_allocate_source_ads_by_sku_distributes_total_once_across_sizes() -> None:
    service = ControlTowerService()
    rows = [
        SimpleNamespace(sku_id=1, nm_id=777, realized_revenue=Decimal("100"), net_units=1, gross_units=1),
        SimpleNamespace(sku_id=2, nm_id=777, realized_revenue=Decimal("200"), net_units=1, gross_units=1),
        SimpleNamespace(sku_id=3, nm_id=777, realized_revenue=Decimal("300"), net_units=1, gross_units=1),
        SimpleNamespace(sku_id=4, nm_id=777, realized_revenue=Decimal("400"), net_units=1, gross_units=1),
    ]

    allocated = service._allocate_source_ads_by_sku(
        rows=rows,
        ads_source_by_nm={777: Decimal("1000")},
    )

    assert sum(allocated.values(), start=Decimal("0")) == Decimal("1000")
    assert allocated[1] == Decimal("100")
    assert allocated[2] == Decimal("200")
    assert allocated[3] == Decimal("300")
    assert allocated[4] == Decimal("400")


def test_ads_allocation_metrics_report_overallocated_duplicate_spend() -> None:
    service = ControlTowerService()

    metrics = service._ads_allocation_metrics(
        mart_ad_spend=Decimal("1400"),
        source_ad_spend=Decimal("1000"),
    )

    assert metrics["raw_ad_spend"] == Decimal("1400")
    assert metrics["capped_ad_spend"] == Decimal("1000")
    assert metrics["overallocated_ad_spend"] == Decimal("400")
    assert metrics["unallocated_ad_spend"] == Decimal("0")
    assert metrics["ads_allocation_status"] == "overallocated"
    assert metrics["final_profit_allowed"] is False


@pytest.mark.asyncio
async def test_build_control_rows_dedupes_parallel_inflight_requests(monkeypatch) -> None:
    service = ControlTowerService()
    service._control_rows_cache.clear()
    service._control_rows_window_cache.clear()
    service._control_rows_inflight.clear()
    service._control_rows_last_meta.clear()
    calls = 0
    snapshot = CachedControlRowsSnapshot(
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        computed_at=utcnow(),
        data_version_hash="hash-control-1",
    )

    async def fake_uncached(_session, *, account_id, date_from, date_to, profit_rows=None):
        nonlocal calls
        calls += 1
        assert account_id == 1
        assert date_from == date(2026, 5, 1)
        assert date_to == date(2026, 5, 31)
        await asyncio.sleep(0.01)
        return snapshot, "miss"

    monkeypatch.setattr(service, "_build_control_rows_uncached", fake_uncached)

    left, right = await asyncio.gather(
        service._build_control_rows(None, account_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)),
        service._build_control_rows(None, account_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31)),
    )

    assert calls == 1
    assert left == (snapshot.control_rows, snapshot.price_rows, snapshot.purchase_rows, snapshot.settings)
    assert right == left


@pytest.mark.asyncio
async def test_build_control_rows_uses_warm_window_cache_before_uncached_work(monkeypatch) -> None:
    service = ControlTowerService()
    service._control_rows_cache.clear()
    service._control_rows_window_cache.clear()
    service._control_rows_inflight.clear()
    service._control_rows_last_meta.clear()
    window_key = service._control_rows_window_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )
    snapshot = CachedControlRowsSnapshot(
        control_rows=[],
        price_rows={},
        purchase_rows={},
        settings={"cost_trust_policy": "operator_baseline"},
        computed_at=utcnow(),
        data_version_hash="hash-control-warm",
    )
    service._control_rows_window_cache[window_key] = snapshot

    async def fail_uncached(*args, **kwargs):
        raise AssertionError("warm cache should bypass uncached control row rebuild")

    monkeypatch.setattr(service, "_build_control_rows_uncached", fail_uncached)

    result = await service._build_control_rows(
        None,
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result == (snapshot.control_rows, snapshot.price_rows, snapshot.purchase_rows, snapshot.settings)
    assert service._control_cache_meta(account_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 31))[
        "cache_status"
    ] == "hit"


@pytest.mark.asyncio
async def test_action_sync_cache_regenerates_when_cached_storage_is_empty() -> None:
    service = ControlTowerService()
    cache_key = service._action_sync_cache_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )
    service._action_sync_cache[cache_key] = (utcnow(), "stale-empty")
    generated = SimpleNamespace(
        action_type="RECONCILE_FINANCE",
        expected_effect_amount=Decimal("10"),
        status="new",
    )
    service._load_existing_action_rows = AsyncMock(side_effect=[[], [generated]])
    service._sync_recommendations = AsyncMock(return_value=[generated])
    service._sync_alerts_from_actions = AsyncMock(return_value=[])

    result = await service._sync_recommendations_cached(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        control_rows=[],
        price_rows={},
        purchase_rows={},
        trust_decision=SimpleNamespace(blocked_reasons=[], can_generate_business_actions=True, trust_state=TRUST_STATE_TRUSTED),
    )

    assert result == [generated]
    service._sync_recommendations.assert_awaited_once()


@pytest.mark.asyncio
async def test_action_sync_loads_only_current_window_rows(monkeypatch) -> None:
    service = ControlTowerService()
    date_from = date(2026, 5, 1)
    date_to = date(2026, 5, 31)
    existing = SimpleNamespace(
        source_date_from=date_from,
        source_date_to=date_to,
        status="new",
        action_unique_key="old-window-action",
        resolved_at=None,
        user_comment=None,
    )
    session = SimpleNamespace(flush=AsyncMock())
    load_existing = AsyncMock(return_value=[existing])
    monkeypatch.setattr(service, "_load_existing_action_rows", load_existing)

    result = await service._sync_recommendations(
        session,
        account_id=1,
        date_from=date_from,
        date_to=date_to,
        control_rows=[],
        price_rows={},
        purchase_rows={},
        trust_decision=SimpleNamespace(
            blocked_reasons=[],
            can_generate_business_actions=True,
            trust_state=TRUST_STATE_TRUSTED,
        ),
    )

    assert result == []
    load_existing.assert_awaited_once_with(
        session,
        account_id=1,
        date_from=date_from,
        date_to=date_to,
    )
    assert existing.status == "resolved"
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_open_action_counts_uses_aggregated_rows() -> None:
    class FakeResult:
        def all(self):
            return [(101, 3), (202, 1), (None, 5)]

    class FakeSession:
        async def execute(self, stmt):
            return FakeResult()

    service = ControlTowerService()

    assert await service._load_open_action_counts(FakeSession(), account_id=1) == {101: 3, 202: 1}


def test_purchase_status_contract_uses_plan_statuses() -> None:
    service = ControlTowerService()

    reorder = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TRUSTED,
        estimated_profit=Decimal("50"),
        days_of_stock=Decimal("5"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=24,
        in_transit_qty=Decimal("0"),
        margin_percent=Decimal("24"),
        roi_percent=Decimal("80"),
    )
    blocked = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_DATA_BLOCKED,
        estimated_profit=Decimal("50"),
        days_of_stock=Decimal("5"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=24,
        in_transit_qty=Decimal("0"),
        margin_percent=Decimal("24"),
        roi_percent=Decimal("80"),
    )
    provisional = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TEST_ONLY,
        estimated_profit=Decimal("50"),
        days_of_stock=Decimal("5"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=24,
        in_transit_qty=Decimal("0"),
        margin_percent=Decimal("24"),
        roi_percent=Decimal("80"),
    )
    loss = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TRUSTED,
        estimated_profit=Decimal("-1"),
        days_of_stock=Decimal("5"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=24,
        in_transit_qty=Decimal("0"),
        margin_percent=Decimal("24"),
        roi_percent=Decimal("80"),
    )

    assert reorder.status == "REORDER"
    assert reorder.risk in {"out_of_stock", "low_stock"}
    assert blocked.status == "WAIT_DATA"
    assert provisional.status == "REORDER"
    assert provisional.confidence == "medium"
    assert "предвар" in provisional.reason.lower()
    assert loss.status == "DO_NOT_BUY"


def test_liquidate_status_returns_zero_cash_and_expected_cash_release() -> None:
    service = ControlTowerService()

    decision = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TEST_ONLY,
        estimated_profit=Decimal("120"),
        days_of_stock=Decimal("140"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=0,
        in_transit_qty=Decimal("0"),
        sales_velocity_daily=Decimal("0.1"),
        stock_value=Decimal("1304998"),
        margin_percent=Decimal("22"),
        roi_percent=Decimal("70"),
        final_profit_allowed=False,
    )

    assert decision.status == "LIQUIDATE"
    assert decision.confidence == "medium"
    assert decision.financial_final is False


def test_wait_data_not_returned_when_only_supplier_final_is_missing() -> None:
    service = ControlTowerService()

    decision = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TEST_ONLY,
        estimated_profit=Decimal("80"),
        days_of_stock=Decimal("4"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        blocked_reasons=["supplier_cost_not_confirmed"],
        recommended_qty=18,
        in_transit_qty=Decimal("0"),
        margin_percent=Decimal("25"),
        roi_percent=Decimal("90"),
        final_profit_allowed=True,
    )

    assert decision.status == "REORDER"
    assert decision.status != "WAIT_DATA"
    assert decision.confidence == "medium"


def test_stock_with_zero_recent_sales_is_not_marked_as_missing_stock_data() -> None:
    service = ControlTowerService()

    decision = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TEST_ONLY,
        estimated_profit=Decimal("80"),
        days_of_stock=None,
        available_stock_qty=Decimal("25"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=0,
        in_transit_qty=Decimal("0"),
        sales_velocity_daily=Decimal("0"),
        stock_value=Decimal("250000"),
        margin_percent=Decimal("25"),
        roi_percent=Decimal("90"),
        final_profit_allowed=False,
    )

    assert decision.status == "LIQUIDATE"
    assert decision.risk == "overstock"
    assert "продаж не было" in decision.reason.lower()


def test_reorder_requires_positive_recommended_qty() -> None:
    service = ControlTowerService()

    decision = service._purchase_status_and_reason(
        trust_state=TRUST_STATE_TRUSTED,
        estimated_profit=Decimal("80"),
        days_of_stock=Decimal("4"),
        lead_time_days=14,
        safety_days=7,
        overstock_threshold_days=90,
        recommended_qty=0,
        in_transit_qty=Decimal("8"),
        margin_percent=Decimal("25"),
        roi_percent=Decimal("90"),
        final_profit_allowed=True,
    )

    assert decision.status != "REORDER"
    assert decision.status == "PROTECT_STOCK"


def test_group_purchase_rows_by_article_sums_size_stock_correctly() -> None:
    service = ControlTowerService()
    control_rows = [
        SimpleNamespace(
            sku_id=1,
            nm_id=777,
            vendor_code="A",
            title="Card A 42",
            blocked_reasons=[],
            stock_value=Decimal("1000"),
            revenue=Decimal("5000"),
            net_profit=Decimal("1000"),
            margin_percent=Decimal("20"),
            roi_percent=Decimal("60"),
            final_profit_allowed=False,
        ),
        SimpleNamespace(
            sku_id=2,
            nm_id=777,
            vendor_code="A",
            title="Card A 44",
            blocked_reasons=[],
            stock_value=Decimal("2000"),
            revenue=Decimal("6000"),
            net_profit=Decimal("1200"),
            margin_percent=Decimal("20"),
            roi_percent=Decimal("60"),
            final_profit_allowed=False,
        ),
    ]
    purchase_rows = {
        1: PurchasePlanRow(
            sku_id=1,
            nm_id=777,
            vendor_code="A",
            title="Card A 42",
            status="LIQUIDATE",
            decision="LIQUIDATE",
            trust_state=TRUST_STATE_TEST_ONLY,
            sales_velocity_daily=1.0,
            available_stock=200.0,
            in_transit_qty=10.0,
            days_of_stock=200.0,
            lead_time_days=14,
            safety_days=7,
            recommended_qty=0,
            required_cash=0.0,
            expected_profit=1000.0,
            risk="overstock",
            reason="Slow stock",
            confidence="medium",
            decision_confidence="medium",
            financial_final=False,
            money_effect={"affected_stock_value": 1000.0, "expected_cash_release": 1000.0},
        ),
        2: PurchasePlanRow(
            sku_id=2,
            nm_id=777,
            vendor_code="A",
            title="Card A 44",
            status="LIQUIDATE",
            decision="LIQUIDATE",
            trust_state=TRUST_STATE_TEST_ONLY,
            sales_velocity_daily=2.0,
            available_stock=254.0,
            in_transit_qty=5.0,
            days_of_stock=127.0,
            lead_time_days=14,
            safety_days=7,
            recommended_qty=0,
            required_cash=0.0,
            expected_profit=1200.0,
            risk="overstock",
            reason="Slow stock",
            confidence="medium",
            decision_confidence="medium",
            financial_final=False,
            money_effect={"affected_stock_value": 2000.0, "expected_cash_release": 2000.0},
        ),
    }

    grouped = service._group_purchase_rows_by_article(
        control_rows=control_rows,
        purchase_rows=purchase_rows,
        settings=service.DEFAULT_SETTINGS,
    )

    assert len(grouped) == 1
    assert grouped[0].nm_id == 777
    assert grouped[0].available_stock == pytest.approx(454.0)
    assert grouped[0].in_transit_qty == pytest.approx(15.0)
    assert grouped[0].variant_count == 2
    assert grouped[0].status == "LIQUIDATE"


def test_group_purchase_rows_by_article_uses_available_stock_when_sales_velocity_is_zero() -> None:
    service = ControlTowerService()
    control_rows = [
        SimpleNamespace(
            sku_id=1,
            nm_id=888,
            vendor_code="B",
            title="Card B",
            blocked_reasons=[],
            stock_value=Decimal("500"),
            revenue=Decimal("0"),
            net_profit=Decimal("50"),
            margin_percent=None,
            roi_percent=None,
            final_profit_allowed=False,
        ),
    ]
    purchase_rows = {
        1: PurchasePlanRow(
            sku_id=1,
            nm_id=888,
            vendor_code="B",
            title="Card B",
            status="WAIT_DATA",
            decision="WAIT_DATA",
            trust_state=TRUST_STATE_TEST_ONLY,
            sales_velocity_daily=0.0,
            available_stock=5.0,
            in_transit_qty=1.0,
            days_of_stock=None,
            lead_time_days=14,
            safety_days=7,
            recommended_qty=0,
            required_cash=0.0,
            expected_profit=50.0,
            risk="stock_data_missing",
            reason="No stock data",
            confidence="medium",
            decision_confidence="medium",
            financial_final=False,
            money_effect={"affected_stock_value": 500.0, "expected_cash_release": 500.0},
        ),
    }

    grouped = service._group_purchase_rows_by_article(
        control_rows=control_rows,
        purchase_rows=purchase_rows,
        settings=service.DEFAULT_SETTINGS,
    )

    assert len(grouped) == 1
    assert grouped[0].status == "LIQUIDATE"
    assert "продаж не было" in grouped[0].reason.lower()


def test_formula_audit_result_flags_broken_contracts() -> None:
    service = ControlTowerService()
    price_rows = {
        1: PriceSafetyRow(
            sku_id=1,
            nm_id=1001,
            vendor_code="SKU-1",
            title="SKU 1",
            current_price=100,
            current_discounted_price=95,
            average_sale_price=100,
            break_even_price=90,
            target_margin_price=110,
            safe_price_gap=5,
            estimated_margin_at_current_price=10,
            estimated=False,
            confidence="high",
            action_hint="PRICE_INCREASE_REVIEW",
        )
    }
    purchase_rows = {
        1: PurchasePlanRow(
            sku_id=1,
            nm_id=1001,
            vendor_code="SKU-1",
            title="SKU 1",
            status="REORDER",
            trust_state=TRUST_STATE_DATA_BLOCKED,
            sales_velocity_daily=2,
            available_stock=3,
            in_transit_qty=0,
            days_of_stock=3,
            lead_time_days=14,
            safety_days=7,
            recommended_qty=12,
            required_cash=1200,
            expected_profit=50,
            risk="out_of_stock",
            reason="Need reorder",
        )
    }
    passed, payload = service._formula_audit_result(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        trust_decision=SimpleNamespace(
            business_trusted=True,
            trust_state=TRUST_STATE_TRUSTED,
            blocked_reasons=[],
            can_generate_business_actions=True,
        ),
        price_rows=price_rows,
        purchase_rows=purchase_rows,
        article_samples=[
            {
                "sku_id": 1,
                "nm_id": 1001,
                "vendor_code": "SKU-1",
                "revenue_matches_mart": False,
                "difference_amount": 14.5,
                "difference_ratio": 3.2,
            }
        ],
    )

    assert passed is False
    assert set(payload["failed_checks"]) == {
        "price_safety_contract",
        "purchase_plan_gate",
        "article_audit_consistency",
    }


@pytest.mark.asyncio
async def test_purchase_plan_summary_counts_global_items_not_current_page() -> None:
    service = ControlTowerService()
    service._build_control_rows = AsyncMock(
        return_value=(
            [],
            {},
            {
                1: _purchase_plan_row(sku_id=1, status="REORDER", required_cash=1200.0, expected_profit=300.0),
                2: _purchase_plan_row(sku_id=2, status="LIQUIDATE", expected_profit=50.0),
                3: _purchase_plan_row(sku_id=3, status="DO_NOT_BUY", expected_profit=-10.0),
                4: _purchase_plan_row(sku_id=4, status="WATCH", expected_profit=20.0),
                5: _purchase_plan_row(
                    sku_id=5,
                    status="WAIT_DATA",
                    reason="Финансовые данные еще не подтверждены.",
                    risk="finance_not_confirmed",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                ),
            },
            service.DEFAULT_SETTINGS,
        )
    )

    page = await service.list_purchase_plan(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="sku",
        limit=2,
        offset=0,
    )

    assert page.total == 5
    assert len(page.items) == 2
    assert page.summary.total_count == 5
    assert page.summary.page_count == 2
    assert page.summary.total_positions == 5
    assert page.summary.total_items == 5
    assert page.summary.reorder_count == 1
    assert page.summary.liquidate_count == 1
    assert page.summary.do_not_buy_count == 1
    assert page.summary.watch_count == 1
    assert page.summary.wait_data_count == 1
    assert page.summary.required_cash_total == pytest.approx(1200.0)
    assert page.summary.total_required_cash == pytest.approx(1200.0)
    assert page.summary.expected_profit_total == pytest.approx(300.0)
    assert page.summary.total_expected_profit == pytest.approx(300.0)
    assert page.summary.wait_data_reason_counts.finance == 1


@pytest.mark.asyncio
async def test_purchase_plan_summary_wait_data_reason_counts_are_bucketed() -> None:
    service = ControlTowerService()
    service._build_control_rows = AsyncMock(
        return_value=(
            [],
            {},
            {
                1: _purchase_plan_row(
                    sku_id=1,
                    status="WAIT_DATA",
                    reason="Финансовые данные еще не подтверждены.",
                    risk="finance_not_confirmed",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                ),
                2: _purchase_plan_row(
                    sku_id=2,
                    status="WAIT_DATA",
                    reason="Себестоимость поставщика не подтверждена.",
                    risk="supplier_cost_not_confirmed",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                ),
                3: _purchase_plan_row(
                    sku_id=3,
                    status="WAIT_DATA",
                    reason="По этому SKU пока нет достаточных данных по остаткам.",
                    risk="stock_data_missing",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                ),
                4: _purchase_plan_row(
                    sku_id=4,
                    status="WAIT_DATA",
                    reason="Скорость продаж пока не подтверждена.",
                    risk="velocity_data_missing",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                ),
                5: _purchase_plan_row(
                    sku_id=5,
                    status="WAIT_DATA",
                    reason="По этому SKU пока нет достаточных данных о продажах.",
                    risk="sales_data_missing",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                ),
            },
            service.DEFAULT_SETTINGS,
        )
    )

    page = await service.list_purchase_plan(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="sku",
        limit=10,
        offset=0,
    )

    assert page.summary.wait_data_count == 5
    assert page.summary.wait_data_reason_counts.finance == 1
    assert page.summary.wait_data_reason_counts.cost == 1
    assert page.summary.wait_data_reason_counts.stock == 1
    assert page.summary.wait_data_reason_counts.velocity == 1
    assert page.summary.wait_data_reason_counts.sales == 1


def test_purchase_wait_data_reasons_deduplicate_and_preserve_priority_order() -> None:
    service = ControlTowerService()

    reasons = service._purchase_wait_data_reasons(
        status="WAIT_DATA",
        blocked_reasons=[
            "stocks_task_not_ready",
            "supplier_cost_not_confirmed",
            "finance_not_confirmed",
            "stocks_not_completed",
        ],
        risk="stock_data_missing",
        reason="Финансовые данные и себестоимость еще не готовы.",
        main_reason="Остатки тоже не досинхронизированы.",
    )

    assert reasons == ["finance", "cost", "stock"]


@pytest.mark.asyncio
async def test_purchase_plan_summary_counts_all_row_wait_data_reasons() -> None:
    service = ControlTowerService()
    service._build_control_rows = AsyncMock(
        return_value=(
            [],
            {},
            {
                1: _purchase_plan_row(
                    sku_id=1,
                    status="WAIT_DATA",
                    reason="Данных пока недостаточно.",
                    risk="finance_not_confirmed",
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                    missing_data=["finance", "cost", "stock"],
                ),
            },
            service.DEFAULT_SETTINGS,
        )
    )

    page = await service.list_purchase_plan(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        group_by="sku",
        limit=10,
        offset=0,
    )

    assert page.summary.wait_data_count == 1
    assert page.summary.wait_data_reason_counts.finance == 1
    assert page.summary.wait_data_reason_counts.cost == 1
    assert page.summary.wait_data_reason_counts.stock == 1


def test_group_purchase_rows_by_article_unions_wait_data_reasons_and_merges_cost_truth() -> None:
    service = ControlTowerService()
    control_rows = [
        SimpleNamespace(
            sku_id=1,
            nm_id=999,
            vendor_code="A",
            title="Card A 42",
            blocked_reasons=["finance_not_confirmed"],
            stock_value=Decimal("100"),
            revenue=Decimal("500"),
            net_profit=Decimal("50"),
            margin_percent=Decimal("10"),
            roi_percent=Decimal("20"),
            final_profit_allowed=False,
        ),
        SimpleNamespace(
            sku_id=2,
            nm_id=999,
            vendor_code="A",
            title="Card A 44",
            blocked_reasons=["finance_not_confirmed"],
            stock_value=Decimal("120"),
            revenue=Decimal("400"),
            net_profit=Decimal("40"),
            margin_percent=Decimal("10"),
            roi_percent=Decimal("20"),
            final_profit_allowed=False,
        ),
    ]
    purchase_rows = {
        1: _purchase_plan_row(
            sku_id=1,
            status="WAIT_DATA",
            nm_id=999,
            reason="Финансовые данные еще не подтверждены.",
            risk="finance_not_confirmed",
            trust_state=TRUST_STATE_DATA_BLOCKED,
            missing_data=["finance", "cost"],
            cost_source="operator_trusted_manual",
            cost_truth_level="operator_baseline",
        ),
        2: _purchase_plan_row(
            sku_id=2,
            status="WAIT_DATA",
            nm_id=999,
            reason="Финансовые данные еще не подтверждены.",
            risk="finance_not_confirmed",
            trust_state=TRUST_STATE_DATA_BLOCKED,
            missing_data=["stock"],
            cost_source="supplier_confirmed",
            cost_truth_level="supplier_confirmed",
        ),
    }

    grouped = service._group_purchase_rows_by_article(
        control_rows=control_rows,
        purchase_rows=purchase_rows,
        settings=service.DEFAULT_SETTINGS,
    )

    assert len(grouped) == 1
    assert grouped[0].status == "WAIT_DATA"
    assert grouped[0].missing_data == ["finance", "cost", "stock"]
    assert grouped[0].missing_fields == ["finance", "cost", "stock"]
    assert grouped[0].wait_data_reasons == ["finance", "cost", "stock"]
    assert grouped[0].cost_source == "mixed"
    assert grouped[0].cost_truth == "mixed"
    assert grouped[0].cost_truth_level == "mixed"


def test_aggregate_latest_stock_rows_prefers_total_row_without_double_count() -> None:
    service = ControlTowerService()

    aggregated = service._aggregate_latest_stock_rows(
        [
            SimpleNamespace(
                stat_date=date(2026, 5, 20),
                warehouse_name="Всего",
                quantity=None,
                quantity_full=Decimal("15"),
                in_way_to_client=Decimal("2"),
                in_way_from_client=Decimal("1"),
                avg_sales_per_day_30d=Decimal("3"),
            ),
            SimpleNamespace(
                stat_date=date(2026, 5, 20),
                warehouse_name="Коледино",
                quantity=Decimal("9"),
                quantity_full=Decimal("9"),
                in_way_to_client=Decimal("2"),
                in_way_from_client=Decimal("0"),
                avg_sales_per_day_30d=Decimal("3"),
            ),
            SimpleNamespace(
                stat_date=date(2026, 5, 20),
                warehouse_name="Электросталь",
                quantity=Decimal("6"),
                quantity_full=Decimal("6"),
                in_way_to_client=Decimal("0"),
                in_way_from_client=Decimal("1"),
                avg_sales_per_day_30d=Decimal("3"),
            ),
        ]
    )

    assert aggregated.quantity == Decimal("15")
    assert aggregated.quantity_full == Decimal("15")
    assert aggregated.in_way_to_client == Decimal("2")
    assert aggregated.in_way_from_client == Decimal("1")
    assert aggregated.days_of_stock == Decimal("5")


def test_aggregate_latest_stock_rows_keeps_transit_rows_when_total_row_is_separate() -> None:
    service = ControlTowerService()

    aggregated = service._aggregate_latest_stock_rows(
        [
            SimpleNamespace(
                stat_date=date(2026, 5, 20),
                warehouse_name="Всего находится на складах",
                quantity=None,
                quantity_full=Decimal("29"),
                in_way_to_client=None,
                in_way_from_client=None,
                avg_sales_per_day_30d=Decimal("2"),
            ),
            SimpleNamespace(
                stat_date=date(2026, 5, 20),
                warehouse_name="В пути до получателей",
                quantity=None,
                quantity_full=None,
                in_way_to_client=Decimal("10"),
                in_way_from_client=None,
                avg_sales_per_day_30d=Decimal("2"),
            ),
            SimpleNamespace(
                stat_date=date(2026, 5, 20),
                warehouse_name="В пути возвраты на склад WB",
                quantity=None,
                quantity_full=None,
                in_way_to_client=None,
                in_way_from_client=Decimal("12"),
                avg_sales_per_day_30d=Decimal("2"),
            ),
        ]
    )

    assert aggregated.quantity == Decimal("29")
    assert aggregated.quantity_full == Decimal("29")
    assert aggregated.in_way_to_client == Decimal("10")
    assert aggregated.in_way_from_client == Decimal("12")


def test_aggregate_latest_stock_rows_uses_latest_quantity_snapshot_when_latest_day_is_transit_only() -> None:
    service = ControlTowerService()

    aggregated = service._aggregate_latest_stock_rows(
        [
            SimpleNamespace(
                stat_date=date(2026, 5, 30),
                warehouse_name="Всего находится на складах",
                quantity=None,
                quantity_full=Decimal("21"),
                in_way_to_client=None,
                in_way_from_client=None,
                avg_sales_per_day_30d=Decimal("3"),
            ),
            SimpleNamespace(
                stat_date=date(2026, 5, 31),
                warehouse_name="В пути возвраты на склад WB",
                quantity=None,
                quantity_full=None,
                in_way_to_client=None,
                in_way_from_client=Decimal("4"),
                avg_sales_per_day_30d=Decimal("0"),
            ),
        ]
    )

    assert aggregated.stat_date == date(2026, 5, 31)
    assert aggregated.quantity == Decimal("21")
    assert aggregated.quantity_full == Decimal("21")
    assert aggregated.in_way_to_client == Decimal("0")
    assert aggregated.in_way_from_client == Decimal("4")
    assert aggregated.days_of_stock == Decimal("7")


def test_control_tower_classification_allows_test_only_rows_to_keep_business_status() -> None:
    service = ControlTowerService()

    status = service._classify_sku_status(
        trust_state=TRUST_STATE_TEST_ONLY,
        profit=Decimal("120"),
        days_of_stock=Decimal("5"),
        ad_spend=Decimal("0"),
        safe_price_gap=Decimal("50"),
        overstock_threshold_days=90,
        finance_rows=10,
        net_units=10,
    )

    assert status == "PROTECT_STOCK"


def test_resolve_price_inputs_uses_price_snapshot_fallback_when_core_price_missing() -> None:
    service = ControlTowerService()

    resolved = service._resolve_price_inputs(
        core_sku=SimpleNamespace(current_price=None, current_discounted_price=None),
        price_snapshot=PriceSnapshot(
            current_price=Decimal("145"),
            current_discounted_price=Decimal("119"),
            price_source="wb_price_sizes.discounted_price",
            mapping_status="mapped",
        ),
    )

    assert resolved.current_price == Decimal("145")
    assert resolved.current_discounted_price == Decimal("119")
    assert resolved.price_source == "wb_price_snapshot"
    assert resolved.mapping_status == "mapped"


def test_resolve_price_inputs_uses_average_sale_when_no_other_price_sources_exist() -> None:
    service = ControlTowerService()

    resolved = service._resolve_price_inputs(
        core_sku=SimpleNamespace(current_price=None, current_discounted_price=None),
        price_snapshot=None,
        article_price_snapshot=None,
        average_sale_price=Decimal("187"),
    )

    assert resolved.current_price == Decimal("187")
    assert resolved.current_discounted_price is None
    assert resolved.price_source == "average_sale"
    assert resolved.mapping_status == "fallback"


def test_price_not_computable_reasons_return_missing_price_without_zero_defaults() -> None:
    reasons = ControlTowerService._price_not_computable_reasons(
        current_price=None,
        current_discounted_price=None,
        average_sale_price=None,
        total_unit_cost=Decimal("120"),
        revenue=Decimal("1000"),
        net_units=5,
        break_even=None,
    )

    assert "missing_price" in reasons
    assert "formula_not_computable" in reasons


def test_safe_price_metrics_use_cost_price_plus_seller_other_expense() -> None:
    service = ControlTowerService()
    total_unit_cost = manual_cost_total_unit_cost(
        SimpleNamespace(
            cost_price=Decimal("100"),
            unit_cost=Decimal("100"),
            seller_other_expense=Decimal("15"),
            packaging_cost=Decimal("4"),
            inbound_logistics_cost=Decimal("6"),
        )
    )

    break_even, target_margin_price, safe_gap, estimated_margin, estimated = service._safe_price_metrics(
        current_price=Decimal("140"),
        current_discounted_price=Decimal("140"),
        average_sale_price=Decimal("140"),
        total_unit_cost=total_unit_cost,
        revenue=Decimal("1400"),
        ad_spend=Decimal("0"),
        net_units=10,
        commission=Decimal("0"),
        acquiring_fee=Decimal("0"),
        deductions=Decimal("0"),
        additional_payments=Decimal("0"),
        logistics=Decimal("0"),
        paid_acceptance=Decimal("0"),
        storage=Decimal("0"),
        penalties=Decimal("0"),
        target_margin_rate=Decimal("0.2"),
    )

    assert break_even == Decimal("115")
    assert target_margin_price == Decimal("143.75")
    assert safe_gap == Decimal("25")
    assert float(estimated_margin) == pytest.approx(17.8571428571)
    assert estimated is False


def test_resolve_price_inputs_returns_missing_snapshot_when_no_sources_exist() -> None:
    service = ControlTowerService()

    resolved = service._resolve_price_inputs(
        core_sku=SimpleNamespace(current_price=None, current_discounted_price=None),
        price_snapshot=None,
        article_price_snapshot=None,
        average_sale_price=None,
    )

    assert resolved.current_price is None
    assert resolved.current_discounted_price is None
    assert resolved.price_source == "missing"


@pytest.mark.asyncio
async def test_list_alerts_returns_empty_page_when_alert_table_is_missing() -> None:
    service = ControlTowerService()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=ProgrammingError(
                "SELECT * FROM alert_events",
                {},
                Exception('relation "alert_events" does not exist'),
            )
        )
    )

    page = await service.list_alerts(session, account_id=1, limit=100, offset=0)

    assert page.total == 0
    assert page.items == []


@pytest.mark.asyncio
async def test_update_alert_raises_clear_storage_error_when_table_is_missing() -> None:
    service = ControlTowerService()
    session = SimpleNamespace(
        get=AsyncMock(
            side_effect=ProgrammingError(
                "SELECT * FROM alert_events",
                {},
                Exception('relation "alert_events" does not exist'),
            )
        )
    )

    try:
        await service.update_alert(session, alert_id=1, payload=SimpleNamespace(status="resolved", snoozed_until=None))
    except HTTPException as exc:
        assert exc.status_code == 503
        assert "alembic upgrade head" in str(exc.detail)
    else:
        raise AssertionError("Expected HTTPException")


def _owner_summary_fixture(
    *,
    business_status: str = "provisional",
    can_generate_business_actions: bool = True,
    operational_revenue: float = 8966760.87,
    net_profit_after_overhead: float = 3384883.70,
    margin_after_overhead_percent: float = 37.75,
    roi_on_cogs_percent: float = 89.31,
    ad_spend: float = 387398.37,
    stock_value: float = 16962343.0,
    unallocated_expenses: float = 1344774.07,
    overstock_value: float = 13835367.0,
    difference_percent: float = 15.97,
    supplier_confirmed_cost_coverage_percent: float = 0.0,
    ads_overallocated_spend: float = 44068.7,
    ads_allocation_percent_capped: float = 100.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        meta=SimpleNamespace(
            data_trust=SimpleNamespace(
                can_generate_business_actions=can_generate_business_actions,
                blocked_reasons=[],
                confidence="medium",
            )
        ),
        answer=SimpleNamespace(
            business_status=business_status,
            title="Магазин готов к управлению, но финальная прибыль еще предварительная.",
            short_text="Можно принимать операционные решения, но финальная прибыль еще не закрыта полностью.",
            main_problem="Финальная прибыль еще не закрыта: есть finance mismatch, нет supplier-confirmed себестоимости.",
            main_next_step="Закройте finance reconciliation и supplier cost",
        ),
        revenue_sources=SimpleNamespace(
            operational_revenue=operational_revenue,
            reconciliation_status="critical_mismatch" if business_status != "healthy" else "matched",
            difference_percent=difference_percent,
        ),
        quality=SimpleNamespace(
            supplier_confirmed_cost_coverage_percent=supplier_confirmed_cost_coverage_percent,
            supplier_cost_coverage_percent=supplier_confirmed_cost_coverage_percent,
            ads_overallocated_spend=ads_overallocated_spend,
            ads_allocation_percent_capped=ads_allocation_percent_capped,
        ),
        kpis=SimpleNamespace(
            net_profit_after_overhead=net_profit_after_overhead,
            margin_after_overhead_percent=margin_after_overhead_percent,
            roi_on_cogs_percent=roi_on_cogs_percent,
            ad_spend=ad_spend,
            stock_value=stock_value,
            unallocated_expenses=unallocated_expenses,
            overstock_value=overstock_value,
            negative_profit_sku_count=77,
            blocked_data_sku_count=1274,
            unallocated_expense_ratio_percent=15.0,
        ),
        risk_summary=SimpleNamespace(
            risks=[
                SimpleNamespace(
                    title="Есть finance mismatch",
                    business_impact="Финальная прибыль остается предварительной.",
                )
            ]
        ),
        store_answer=SimpleNamespace(
            where_money_went="Деньги уходят в себестоимость, WB-расходы, рекламу и неаллокированные расходы.",
            where_money_is_now="Деньги находятся на балансе, в остатках и в пути.",
            what_to_do_today=["Закройте finance reconciliation"],
        ),
        next_actions=[],
    )


class _FakeMoneyService:
    def __init__(self, *, summary: SimpleNamespace, actions_page: SimpleNamespace) -> None:
        self._summary = summary
        self._actions_page = actions_page

    async def summary(self, session, *, account_id: int, date_from, date_to):
        return self._summary

    async def today_actions(self, session, *, account_id: int, date_from, date_to, group_by: str, limit: int, offset: int):
        return self._actions_page


@pytest.mark.asyncio
async def test_owner_dashboard_never_says_trusted_final_when_money_summary_is_operational_provisional() -> None:
    service = ControlTowerService()
    summary = _owner_summary_fixture()
    actions_page = SimpleNamespace(
        summary={"critical": 18, "high": 7, "medium": 2, "low": 1, "money_saving": 3, "growth": 5, "watch": 1, "top_focus_count": 10},
        groups=SimpleNamespace(global_blockers=[], data_fix=[], money_saving=[], growth=[], watch=[]),
        items=[],
    )
    service._money_service = lambda: _FakeMoneyService(summary=summary, actions_page=actions_page)

    owner = await service.owner_dashboard(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 4, 25),
        date_to=date(2026, 5, 25),
    )

    assert owner.trust_state == "operational_provisional"
    assert owner.financial_final is False
    assert owner.can_generate_business_actions is True
    assert owner.trust.status == "operational_provisional"
    assert owner.trust.business_status == "provisional"
    assert "предварительная" in owner.owner_message.title.lower()


@pytest.mark.asyncio
async def test_owner_dashboard_net_profit_uses_profit_after_overhead_from_money_summary() -> None:
    service = ControlTowerService()
    summary = _owner_summary_fixture(
        net_profit_after_overhead=3384883.70,
        unallocated_expenses=1344774.07,
        margin_after_overhead_percent=37.75,
    )
    actions_page = SimpleNamespace(
        summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "money_saving": 0, "growth": 0, "watch": 0, "top_focus_count": 0},
        groups=SimpleNamespace(global_blockers=[], data_fix=[], money_saving=[], growth=[], watch=[]),
        items=[],
    )
    service._money_service = lambda: _FakeMoneyService(summary=summary, actions_page=actions_page)

    owner = await service.owner_dashboard(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 4, 25),
        date_to=date(2026, 5, 25),
    )

    assert owner.net_profit == pytest.approx(3384883.70)
    assert owner.margin_percent == pytest.approx(37.75)
    assert owner.unallocated_expenses == pytest.approx(1344774.07)


@pytest.mark.asyncio
async def test_owner_dashboard_passes_through_profit_cascade_from_money_summary() -> None:
    service = ControlTowerService()
    service._owner_dashboard_cache.clear()
    summary = _owner_summary_fixture()
    summary.profit_cascade = {
        "account_id": 1,
        "date_from": "2026-04-25",
        "date_to": "2026-05-25",
        "currency": "RUB",
        "source_of_truth": "finance_report",
        "financial_final": False,
        "operational_trusted": True,
        "trust_state": "operational_provisional",
        "cascade": {
            "revenue": {"code": "revenue", "label": "Выручка", "amount": 1000.0, "sign": "income"},
            "groups": [],
            "totals": {
                "gross_revenue": 1000.0,
                "seller_cogs": 300.0,
                "seller_other_expense": 20.0,
                "total_seller_expenses": 320.0,
                "total_wb_expenses": 150.0,
                "total_ad_expenses": 40.0,
                "additional_income": 10.0,
                "net_profit_after_all_expenses": 500.0,
                "logistics_total": 80.0,
                "logistics_share_percent": 53.33,
            },
            "validation": {
                "groups_match_children": True,
                "profit_formula_valid": True,
                "issues": [],
            },
        },
    }
    actions_page = SimpleNamespace(
        summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "money_saving": 0, "growth": 0, "watch": 0, "top_focus_count": 0},
        groups=SimpleNamespace(global_blockers=[], data_fix=[], money_saving=[], growth=[], watch=[]),
        items=[],
    )
    service._money_service = lambda: _FakeMoneyService(summary=summary, actions_page=actions_page)

    owner = await service.owner_dashboard(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 4, 25),
        date_to=date(2026, 5, 25),
    )

    assert owner.profit_cascade is not None
    assert owner.profit_cascade.source_of_truth == "finance_report"
    assert owner.profit_cascade.cascade.totals.net_profit_after_all_expenses == pytest.approx(500.0)


@pytest.mark.asyncio
async def test_owner_dashboard_reuses_short_ttl_cache() -> None:
    service = ControlTowerService()
    service._owner_dashboard_cache.clear()
    summary_mock = AsyncMock(return_value=_owner_summary_fixture())
    actions_mock = AsyncMock(
        return_value=SimpleNamespace(
            summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "money_saving": 0, "growth": 0, "watch": 0, "top_focus_count": 0},
            groups=SimpleNamespace(global_blockers=[], data_fix=[], money_saving=[], growth=[], watch=[]),
            items=[],
        )
    )
    service._money_service = lambda: SimpleNamespace(
        summary=summary_mock,
        today_actions=actions_mock,
    )

    first = await service.owner_dashboard(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 4, 25),
        date_to=date(2026, 5, 25),
    )
    second = await service.owner_dashboard(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 4, 25),
        date_to=date(2026, 5, 25),
    )

    assert first.cache_status == "miss"
    assert second.cache_status == "hit"
    assert summary_mock.await_count == 1
    assert actions_mock.await_count == 1


@pytest.mark.asyncio
async def test_action_status_persists_through_update_and_subsequent_list() -> None:
    service = ControlTowerService()
    action = SimpleNamespace(
        id=1,
        account_id=1,
        sku_id=10,
        nm_id=77,
        vendor_code="SKU-10",
        title="SKU 10",
        action_type="LIQUIDATE_STOCK",
        priority="high",
        status="new",
        reason_code="overstock",
        reason="Слишком глубокий остаток",
        calculation_basis=None,
        expected_effect_amount=1000.0,
        confidence="medium",
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        source_date_from=date(2026, 5, 1),
        source_date_to=date(2026, 5, 20),
        source_snapshot_hash="hash",
        assigned_to=None,
        deadline_at=None,
        resolved_at=None,
        user_comment=None,
        payload={"moneyEffect": {"affected_stock_value": 1000.0, "expected_cash_release": 1000.0}},
        created_at=datetime(2026, 5, 20, 10, 0, 0),
        updated_at=datetime(2026, 5, 20, 10, 0, 0),
    )

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self._rows

        def scalar_one(self):
            return len(self._rows)

    session = SimpleNamespace(
        get=AsyncMock(return_value=action),
        add=lambda _obj: None,
        flush=AsyncMock(),
        execute=AsyncMock(return_value=_Result([action])),
    )
    service._build_control_rows = AsyncMock(return_value=([], {}, {}, {}))
    service._trust_decision = AsyncMock(return_value=SimpleNamespace())
    service._sync_recommendations_cached = AsyncMock(return_value=[action])

    updated = await service.update_action(
        session,
        action_id=1,
        user_id=99,
        payload=SimpleNamespace(status="done", assigned_to=None, comment="ok"),
    )
    page = await service.list_actions(
        session,
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        limit=100,
        offset=0,
    )

    assert updated.status == "done"
    assert page.items[0].status == "done"


@pytest.mark.asyncio
async def test_ads_efficiency_uses_final_allocated_spend_not_duplicated_raw_spend() -> None:
    service = ControlTowerService()
    service.dashboard.data_health = AsyncMock(return_value=SimpleNamespace(ad_cluster_rows=1))
    service._build_control_rows = AsyncMock(
        return_value=(
            [
                SimpleNamespace(
                    sku_id=1,
                    nm_id=777,
                    vendor_code="A",
                    title="A",
                    revenue=100.0,
                    ad_spend=100.0,
                    raw_ad_spend=1000.0,
                    source_ad_spend=100.0,
                    overallocated_ad_spend=900.0,
                    unallocated_ad_spend=0.0,
                    ads_allocation_status="overallocated",
                    final_profit_allowed=False,
                    net_profit=10.0,
                    drr_percent=100.0,
                    stock_qty=1.0,
                    days_of_stock=1.0,
                    trust_state=TRUST_STATE_TEST_ONLY,
                ),
                SimpleNamespace(
                    sku_id=2,
                    nm_id=777,
                    vendor_code="B",
                    title="B",
                    revenue=200.0,
                    ad_spend=200.0,
                    raw_ad_spend=1000.0,
                    source_ad_spend=200.0,
                    overallocated_ad_spend=800.0,
                    unallocated_ad_spend=0.0,
                    ads_allocation_status="overallocated",
                    final_profit_allowed=False,
                    net_profit=20.0,
                    drr_percent=100.0,
                    stock_qty=1.0,
                    days_of_stock=1.0,
                    trust_state=TRUST_STATE_TEST_ONLY,
                ),
                SimpleNamespace(
                    sku_id=3,
                    nm_id=777,
                    vendor_code="C",
                    title="C",
                    revenue=300.0,
                    ad_spend=300.0,
                    raw_ad_spend=1000.0,
                    source_ad_spend=300.0,
                    overallocated_ad_spend=700.0,
                    unallocated_ad_spend=0.0,
                    ads_allocation_status="overallocated",
                    final_profit_allowed=False,
                    net_profit=30.0,
                    drr_percent=100.0,
                    stock_qty=1.0,
                    days_of_stock=1.0,
                    trust_state=TRUST_STATE_TEST_ONLY,
                ),
                SimpleNamespace(
                    sku_id=4,
                    nm_id=777,
                    vendor_code="D",
                    title="D",
                    revenue=400.0,
                    ad_spend=400.0,
                    raw_ad_spend=1000.0,
                    source_ad_spend=400.0,
                    overallocated_ad_spend=600.0,
                    unallocated_ad_spend=0.0,
                    ads_allocation_status="overallocated",
                    final_profit_allowed=False,
                    net_profit=40.0,
                    drr_percent=100.0,
                    stock_qty=1.0,
                    days_of_stock=1.0,
                    trust_state=TRUST_STATE_TEST_ONLY,
                ),
            ],
            {},
            {},
            {},
        )
    )
    service._load_ads_source_by_nm = AsyncMock(return_value=({777: Decimal("1000")}, Decimal("1000")))

    page = await service.list_ads_efficiency(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        limit=100,
        offset=0,
    )

    assert sum(item.ad_spend for item in page.items) == pytest.approx(1000.0)
    assert sum(item.raw_ad_spend for item in page.items) == pytest.approx(4000.0)


@pytest.mark.asyncio
async def test_ads_efficiency_exposes_summary_campaign_and_allocated_signal_metrics() -> None:
    service = ControlTowerService()
    service._build_control_rows = AsyncMock(
        return_value=(
            [
                SimpleNamespace(
                    sku_id=1,
                    nm_id=777,
                    vendor_code="A",
                    title="A",
                    revenue=100.0,
                    ad_spend=100.0,
                    raw_ad_spend=100.0,
                    source_ad_spend=120.0,
                    overallocated_ad_spend=0.0,
                    unallocated_ad_spend=20.0,
                    ads_allocation_status="partial",
                    final_profit_allowed=False,
                    net_profit=-10.0,
                    drr_percent=100.0,
                    stock_qty=5.0,
                    days_of_stock=30.0,
                    trust_state=TRUST_STATE_DATA_BLOCKED,
                    blocked_reasons=["missing_manual_cost"],
                ),
                SimpleNamespace(
                    sku_id=2,
                    nm_id=777,
                    vendor_code="B",
                    title="B",
                    revenue=300.0,
                    ad_spend=300.0,
                    raw_ad_spend=300.0,
                    source_ad_spend=360.0,
                    overallocated_ad_spend=0.0,
                    unallocated_ad_spend=60.0,
                    ads_allocation_status="partial",
                    final_profit_allowed=False,
                    net_profit=50.0,
                    drr_percent=100.0,
                    stock_qty=8.0,
                    days_of_stock=40.0,
                    trust_state=TRUST_STATE_TRUSTED,
                    blocked_reasons=[],
                ),
            ],
            {},
            {},
            {},
        )
    )
    service._load_ads_efficiency_stats_by_nm = AsyncMock(
        return_value={
            777: {
                "advert_id": 123,
                "campaign_name": "Campaign 123",
                "campaign_count": 1,
                "advert_ids": [123],
                "stats_rows_count": 4,
                "views": 1000,
                "clicks": 80,
                "orders": 20,
                "atbs": 40,
                "shks": 24,
                "canceled": 4,
                "source_ad_spend": Decimal("480"),
                "source_revenue": Decimal("1600"),
            }
        }
    )

    page = await service.list_ads_efficiency(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        limit=100,
        offset=0,
    )

    assert page.summary.total_count == 2
    assert page.summary.source_ad_spend == pytest.approx(480.0)
    assert page.summary.allocated_ad_spend == pytest.approx(400.0)
    assert page.summary.unallocated_ad_spend == pytest.approx(80.0)
    assert page.summary.ads_allocation_status == "partial"
    assert page.summary.source_revenue == pytest.approx(1600.0)
    assert page.summary.cr_percent == pytest.approx(25.0)
    assert page.summary.cpc == pytest.approx(6.0)
    assert page.items[0].advert_id == 123
    assert page.items[0].campaign_name == "Campaign 123"
    assert sum(item.views for item in page.items) == 1000
    assert sum(item.clicks for item in page.items) == 80
    assert sum(item.orders for item in page.items) == 20
    assert sum(item.atbs for item in page.items) == 40
    assert sum(item.shks for item in page.items) == 24
    assert sum(item.canceled for item in page.items) == 4
    assert sum(item.source_revenue for item in page.items) == pytest.approx(1600.0)
    assert sum(item.source_ad_spend for item in page.items) == pytest.approx(480.0)
    assert sum(item.spend_share_percent or 0 for item in page.items) == pytest.approx(100.0)
    assert any(item.action_label == "Сначала исправить данные" for item in page.items)


@pytest.mark.asyncio
async def test_simulate_price_uses_same_break_even_formula_as_price_safety() -> None:
    service = ControlTowerService()
    price_row = PriceSafetyRow(
        sku_id=1,
        nm_id=1001,
        vendor_code="SKU-1",
        title="SKU 1",
        current_price=100.0,
        current_discounted_price=95.0,
        average_sale_price=100.0,
        break_even_price=90.0,
        target_margin_price=110.0,
        safe_price_gap=5.0,
        safe_price_gap_unit="RUB",
        safe_price_gap_kind="currency_amount",
        estimated_margin_at_current_price=5.26,
        estimated_margin_percent=5.26,
        estimated=False,
        confidence="high",
        action_hint=None,
        price_source="current_sku",
        calculation_state="computed",
        not_computable_reason=None,
        not_computable_reasons=[],
        data_state="ready",
        mapping_status="mapped",
    )
    service._build_control_rows = AsyncMock(
        return_value=(
            [
                SimpleNamespace(
                    sku_id=1,
                    nm_id=1001,
                    revenue=1000.0,
                    net_profit=200.0,
                )
            ],
            {1: price_row},
            {},
            {},
        )
    )

    result = await service.simulate_price(
        SimpleNamespace(),
        payload=PriceSimulationRequest(
            account_id=1,
            sku_id=1,
            price=120.0,
            sales_drop_assumption_percent=0.0,
            date_from=date(2026, 5, 1),
            date_to=date(2026, 5, 20),
        ),
    )

    assert result.break_even_price == 90.0
    assert result.target_margin_price == 110.0
    assert result.expected_profit == pytest.approx(300.0)


@pytest.mark.asyncio
async def test_list_price_safety_exposes_cache_metadata(monkeypatch) -> None:
    service = ControlTowerService()
    computed_at = datetime(2026, 5, 26, 10, 30, 0)
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
    monkeypatch.setattr(
        service,
        "_build_control_rows",
        AsyncMock(
            return_value=(
                [],
                {
                    1: PriceSafetyRow(
                        sku_id=1,
                        nm_id=1001,
                        vendor_code="SKU-1",
                        title="SKU 1",
                        current_price=150.0,
                        current_discounted_price=120.0,
                    average_sale_price=120.0,
                    break_even_price=90.0,
                    target_margin_price=110.0,
                    safe_price_gap=30.0,
                    safe_price_gap_unit="RUB",
                    safe_price_gap_kind="currency_amount",
                    estimated_margin_at_current_price=25.0,
                    estimated_margin_percent=25.0,
                    estimated=False,
                    confidence="high",
                    action_hint=None,
                )
                },
                {},
                service.DEFAULT_SETTINGS,
            )
        ),
    )
    monkeypatch.setattr(
        service,
        "_control_cache_meta",
        lambda **kwargs: {
            "computed_at": computed_at,
            "cache_status": "hit",
            "data_version_hash": "control-hash-1",
        },
    )

    page = await service.list_price_safety(
        SimpleNamespace(),
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
    )

    assert page.computed_at == computed_at
    assert page.cache_status == "hit"
    assert page.data_version_hash == "control-hash-1"
    assert page.items[0].safe_price_gap_unit == "RUB"
    assert page.items[0].safe_price_gap_kind == "currency_amount"


def test_control_rows_cache_key_changes_when_data_version_hash_changes() -> None:
    service = ControlTowerService()

    first = service._control_rows_cache_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        data_version_hash="hash-1",
    )
    second = service._control_rows_cache_key(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        data_version_hash="hash-2",
    )

    assert first != second


@pytest.mark.asyncio
async def test_list_actions_open_alias_returns_lightweight_items() -> None:
    service = ControlTowerService()
    service._ensure_actions_for_window = AsyncMock()

    action = SimpleNamespace(
        id=11,
        account_id=1,
        sku_id=10,
        nm_id=777,
        vendor_code="SKU-10",
        title="Разгрузить остаток",
        action_type="LIQUIDATE_STOCK",
        priority="high",
        status="new",
        reason="Слишком большой остаток",
        expected_effect_amount=Decimal("1250"),
        confidence="medium",
        payload={"linkedEntity": {"type": "article", "id": 777}},
        created_at=datetime(2026, 5, 28, 10, 0, 0),
        updated_at=datetime(2026, 5, 28, 10, 5, 0),
    )

    class _CountResult:
        def scalar_one(self):
            return 1

    class _RowsResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self._rows

    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[_CountResult(), _RowsResult([action])]),
    )
    service._action_sync_last_meta[service._action_sync_cache_key(account_id=1, date_from=date(2026, 5, 1), date_to=date(2026, 5, 20))] = {
        "computed_at": datetime(2026, 5, 28, 10, 0, 0),
        "cache_status": "bypassed",
        "data_version_hash": "hash",
    }

    page = await service.list_actions(
        session,
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 20),
        status="open",
        limit=50,
        offset=0,
    )

    assert page.items[0].status == "new"
    assert page.items[0].short_reason
    assert not hasattr(page.items[0], "payload")


@pytest.mark.asyncio
async def test_get_action_detail_returns_heavy_payload() -> None:
    service = ControlTowerService()
    action = SimpleNamespace(
        id=1,
        account_id=1,
        sku_id=10,
        nm_id=777,
        vendor_code="SKU-10",
        title="Разгрузить остаток",
        action_type="LIQUIDATE_STOCK",
        priority="high",
        status="new",
        reason_code="overstock",
        reason="Слишком большой остаток",
        calculation_basis="stock_value",
        expected_effect_amount=Decimal("1250"),
        confidence="medium",
        trust_state=TRUST_STATE_TEST_ONLY,
        blocked_reasons=[],
        source_date_from=date(2026, 5, 1),
        source_date_to=date(2026, 5, 20),
        source_snapshot_hash="hash",
        assigned_to=None,
        deadline_at=None,
        resolved_at=None,
        user_comment=None,
        payload={"howToFix": ["Run promo"], "moneyEffect": {"affected_stock_value": 1250}},
        created_at=datetime(2026, 5, 28, 10, 0, 0),
        updated_at=datetime(2026, 5, 28, 10, 5, 0),
    )
    session = SimpleNamespace(get=AsyncMock(return_value=action))

    detail = await service.get_action_detail(session, action_id=1)

    assert detail.payload["moneyEffect"]["affected_stock_value"] == 1250
    assert detail.how_to_fix == ["Run promo"]


def test_price_safety_summary_is_case_insensitive() -> None:
    service = ControlTowerService()
    summary = service._price_safety_summary(
        [
            PriceSafetyRow(
                sku_id=1,
                nm_id=1,
                vendor_code="A",
                title="A",
                current_price=100,
                current_discounted_price=90,
                average_sale_price=95,
                break_even_price=110,
                target_margin_price=130,
                safe_price_gap=-10,
                estimated_margin_at_current_price=-5,
                estimated=False,
                confidence="high",
                action_hint="PRICE_INCREASE_REVIEW",
                price_source="current_sku",
                calculation_state="COMPUTED",
            ),
            PriceSafetyRow(
                sku_id=2,
                nm_id=2,
                vendor_code="B",
                title="B",
                current_price=None,
                current_discounted_price=None,
                average_sale_price=None,
                break_even_price=None,
                target_margin_price=None,
                safe_price_gap=None,
                estimated_margin_at_current_price=None,
                estimated=True,
                confidence="low",
                action_hint=None,
                price_source="missing",
                calculation_state="not_computable",
            ),
        ]
    )

    assert summary.total_count == 2
    assert summary.computed_count == 1
    assert summary.below_break_even_count == 1
    assert summary.not_computable_count == 1
    assert summary.price_increase_review_count == 1
