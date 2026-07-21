from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.expense_taxonomy import (
    EXPENSE_CATEGORY_DEDUCTION,
    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
    EXPENSE_CATEGORY_PAYMENT_PROCESSING,
    EXPENSE_CATEGORY_PENALTY,
    EXPENSE_CATEGORY_PVZ_REWARD,
    EXPENSE_CATEGORY_STORAGE,
    EXPENSE_CATEGORY_UNCLASSIFIED,
    EXPENSE_CATEGORY_WB_LOGISTICS,
    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
    additional_income,
    revenue_final,
    total_seller_expenses,
    total_seller_costs,
)
from app.models.data_quality import DataQualityIssue
from app.models.finance import WBRealizationReportRow
from app.models.marts import MartAccountExpenseDaily, MartSKUDaily
from app.schemas.data_quality import DataQualityIssueRead, issue_resolution_guide
from app.services.data_quality import DataQualityService
from app.services.marts import MartService


class _FakePage:
    def __init__(self) -> None:
        self.total = 0
        self.limit = 100
        self.offset = 0
        self.items = []


def _scalar_result(value):
    return SimpleNamespace(
        scalar_one=lambda: value,
        scalar_one_or_none=lambda: value,
    )


def _scalars_result(items):
    return SimpleNamespace(scalars=lambda: items)


def _finance_row(**overrides) -> WBRealizationReportRow:
    payload = {
        "ppvzReward": 0,
    }
    payload.update(overrides.pop("payload", {}))
    base = {
        "account_id": 1,
        "report_id": 101,
        "rrd_id": 202,
        "rr_date": date(2026, 5, 20),
        "doc_type_name": "Продажа",
        "retail_amount": Decimal("1000"),
        "for_pay": Decimal("900"),
        "payload": payload,
    }
    base.update(overrides)
    return WBRealizationReportRow(**base)


def test_expense_taxonomy_properties_do_not_recurse_on_orm_models() -> None:
    sku_row = MartSKUDaily(
        account_id=1,
        dedupe_key="sku-row",
        stat_date=date(2026, 5, 20),
        finance_revenue=Decimal("120"),
        seller_cogs=Decimal("40"),
        seller_other_expense=Decimal("10"),
        additional_payments=Decimal("5"),
    )
    account_expense_row = MartAccountExpenseDaily(
        account_id=1,
        dedupe_key="expense-row",
        stat_date=date(2026, 5, 20),
        additional_payments=Decimal("7"),
    )

    assert revenue_final(sku_row) == Decimal("120")
    assert total_seller_costs(sku_row) == Decimal("50")
    assert additional_income(sku_row) == Decimal("5")
    assert sku_row.revenue_final == Decimal("120")
    assert sku_row.total_seller_costs == Decimal("50")
    assert sku_row.additional_income == Decimal("5")
    account_expense_row.seller_cogs = Decimal("40")
    account_expense_row.seller_other_expense = Decimal("10")
    account_expense_row.total_seller_expenses = Decimal("50")
    assert account_expense_row.total_seller_costs == Decimal("50")
    assert account_expense_row.additional_income == Decimal("7")


def test_extract_snapshot_price_picks_lowest_visible_price() -> None:
    price = DataQualityService._extract_snapshot_price(
        {
            "sizes": [
                {"discountedPrice": "199.90"},
                {"discountedPrice": "149.90"},
            ]
        }
    )

    assert price == Decimal("149.90")


def test_issue_bucket_meta_marks_finance_reconciliation_as_system_reconciliation() -> None:
    meta = DataQualityService.issue_bucket_meta("finance_reconciliation_mismatch")

    assert meta["financial_final_blocker"] is False
    assert "автоматическая сверка" in str(meta["business_impact"]).lower()


def test_issue_bucket_meta_marks_order_followup_as_operational_only() -> None:
    meta = DataQualityService.issue_bucket_meta("order_without_sale_or_return")

    assert meta["financial_final_blocker"] is False


def test_issue_resolution_guide_for_sale_without_finance_is_beginner_friendly() -> None:
    guide = issue_resolution_guide(
        "sale_without_finance",
        {"statDate": "2026-06-01", "nmId": 12345},
    )

    assert guide["next_screen_path"] == "/finance"
    assert "вручную исправлять не нужно" in str(guide["first_action"]).lower()
    assert len(list(guide["step_by_step"])) >= 3
    assert len(list(guide["success_check"])) >= 2


def test_issue_resolution_guide_for_stocks_task_not_ready_is_not_generic() -> None:
    guide = issue_resolution_guide("stocks_task_not_ready", {})

    assert guide["next_screen_path"] == "/admin"
    assert "остатк" in str(guide["simple_reason"]).lower()
    assert "синхронизация" in str(guide["first_action"]).lower()
    assert len(list(guide["step_by_step"])) >= 4


def test_operational_sales_are_only_used_after_closed_finance_period() -> None:
    assert (
        MartService._should_use_operational_sale(
            date(2026, 7, 19), date(2026, 7, 19)
        )
        is False
    )
    assert (
        MartService._should_use_operational_sale(
            date(2026, 7, 20), date(2026, 7, 19)
        )
        is True
    )
    assert MartService._should_use_operational_sale(date(2026, 7, 19), None) is True


def test_issue_resolution_guide_for_dead_stock_is_not_generic() -> None:
    guide = issue_resolution_guide("dead_stock", {})

    assert guide["next_screen_path"] == "/money"
    assert "заморож" in str(guide["simple_reason"]).lower() or "лежит" in str(guide["simple_reason"]).lower()
    assert "денег" in str(guide["first_action"]).lower()
    assert len(list(guide["step_by_step"])) >= 4


def test_data_quality_issue_read_includes_resolution_guide_fields() -> None:
    issue = DataQualityIssue(
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="missing_manual_cost",
        entity_key="nm:123",
        message="У активной карточки нет загруженной себестоимости",
        payload={"nmId": 123, "vendorCode": "ABC-1", "statDate": "2026-05-20"},
        detected_at=datetime(2026, 6, 5, tzinfo=timezone.utc),
    )
    issue.id = 10

    read = DataQualityIssueRead.from_issue(issue)

    assert read.next_screen_path == "/costs"
    assert "себестоимость" in read.next_screen_label.lower()
    assert "abc-1" in read.simple_reason.lower()
    assert len(read.step_by_step) >= 4


@pytest.mark.asyncio
async def test_list_issues_applies_financial_final_blocker_and_only_open_filters() -> None:
    service = DataQualityService()
    captured: dict[str, object] = {}

    class _Repo:
        async def list_filtered(self, session, **kwargs):
            captured.update(kwargs)
            return _FakePage()

    service.repo = _Repo()

    await service.list_issues(
        None,
        account_id=1,
        only_open=True,
        issue_types=["finance_reconciliation_mismatch,missing_manual_cost"],
        severities=["error,warning"],
        financial_final_blocker=True,
    )

    assert captured["only_open"] is True
    assert set(captured["codes"]) == {"missing_manual_cost"}
    assert set(captured["severities"]) == {"error", "warning"}


@pytest.mark.asyncio
async def test_list_issues_passes_source_table_and_severity_filters() -> None:
    service = DataQualityService()
    captured: dict[str, object] = {}

    class _Repo:
        async def list_filtered(self, session, **kwargs):
            captured.update(kwargs)
            return _FakePage()

    service.repo = _Repo()

    await service.list_issues(
        None,
        account_id=1,
        source_tables=["wb_realization_report_rows,manual_costs"],
        severities=["warning"],
    )

    assert set(captured["source_tables"]) == {"wb_realization_report_rows", "manual_costs"}
    assert captured["severities"] == ["warning"]


@pytest.mark.asyncio
async def test_issue_summary_counts_financial_final_blockers_and_groups() -> None:
    service = DataQualityService()
    issues = [
        DataQualityIssue(
            id=1,
            account_id=1,
            domain="finance",
            severity="error",
            code="finance_reconciliation_mismatch",
            source_table="wb_realization_report_rows",
            message="Mismatch",
            payload={},
            detected_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
        ),
        DataQualityIssue(
            id=2,
            account_id=1,
            domain="catalog",
            severity="warning",
            code="missing_chrt_id",
            source_table="core_sku",
            message="Missing chrt",
            payload={},
            detected_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
        ),
        DataQualityIssue(
            id=3,
            account_id=1,
            domain="supplies",
            severity="error",
            code="unmatched_sku",
            source_table="wb_supply_goods",
            message="Supply-level unmatched",
            payload={
                "sourceKind": "source_level",
                "sourceDomains": ["supplies"],
                "classificationReason": "missing_nm_id",
            },
            detected_at=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
            effective_financial_final_blocker=True,
        ),
        DataQualityIssue(
            id=4,
            account_id=1,
            domain="sales",
            severity="error",
            code="unmatched_sku",
            source_table="wb_sales",
            message="Revenue unmatched",
            payload={"sourceDomains": ["sales"]},
            detected_at=datetime(2026, 5, 23, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
            effective_financial_final_blocker=True,
        ),
    ]

    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(scalars=lambda: issues)
        )
    )

    payload = await service.list_issue_summary(session, account_id=1)

    assert payload["open_issues_total"] == 3
    assert payload["blocking_open_issues_total"] == 1
    assert payload["financial_final_blockers_total"] == 1
    assert payload["by_severity"]["error"] == 2
    assert payload["by_issue_type"]["unmatched_sku"] == 2
    assert "finance_mismatch" not in payload["by_group"]
    assert payload["by_group_all_open"]["sku_mapping"] == 3
    assert "finance_mismatch" not in payload["by_group_blocking"]
    assert payload["by_group_blocking"]["sku_mapping"] == 1


@pytest.mark.asyncio
async def test_issue_summary_groups_expense_manual_cost_and_ad_reconciliation() -> None:
    service = DataQualityService()
    issues = [
        DataQualityIssue(
            id=1,
            account_id=1,
            domain="data_quality",
            severity="warning",
            code="expense_large_logistics_share",
            source_table="mart_expense_daily",
            message="Large logistics share",
            payload={},
            detected_at=datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
        ),
        DataQualityIssue(
            id=2,
            account_id=1,
            domain="data_quality",
            severity="warning",
            code="manual_cost_old_fields_used",
            source_table="manual_cost_uploads",
            message="Legacy manual cost fields",
            payload={},
            detected_at=datetime(2026, 5, 21, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
        ),
        DataQualityIssue(
            id=3,
            account_id=1,
            domain="data_quality",
            severity="error",
            code="expense_ad_double_count_risk",
            source_table="mart_sku_daily",
            message="Ad double count risk",
            payload={},
            detected_at=datetime(2026, 5, 22, 12, 0, tzinfo=timezone.utc),
            resolved_at=None,
        ),
    ]
    session = SimpleNamespace(
        execute=AsyncMock(return_value=SimpleNamespace(scalars=lambda: issues))
    )

    payload = await service.list_issue_summary(session, account_id=1)

    assert payload["by_group"]["expense_accounting"] == 1
    assert payload["by_group"]["manual_costs"] == 1
    assert payload["by_group"]["ad_reconciliation"] == 1


@pytest.mark.asyncio
async def test_backfill_stock_fields_uses_previous_quantity_snapshot_when_current_day_has_only_transit() -> None:
    service = MartService()
    row = SimpleNamespace(
        account_id=1,
        stat_date=date(2026, 5, 31),
        sku_id=1001,
        opening_stock_qty=None,
        closing_stock_qty=None,
        in_way_to_client=None,
        in_way_from_client=None,
    )
    stock_rows = [
        SimpleNamespace(
            account_id=1,
            stat_date=date(2026, 5, 30),
            sku_id=1001,
            warehouse_name="Всего находится на складах",
            quantity=None,
            quantity_full=Decimal("12"),
            in_way_to_client=None,
            in_way_from_client=None,
            avg_sales_per_day_30d=Decimal("2"),
        ),
        SimpleNamespace(
            account_id=1,
            stat_date=date(2026, 5, 31),
            sku_id=1001,
            warehouse_name="В пути возвраты на склад WB",
            quantity=None,
            quantity_full=None,
            in_way_to_client=None,
            in_way_from_client=Decimal("3"),
            avg_sales_per_day_30d=Decimal("0"),
        ),
    ]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_scalars_result(stock_rows))

    await service._backfill_stock_fields(session, rows=[row])

    assert row.opening_stock_qty == Decimal("12")
    assert row.closing_stock_qty == Decimal("12")
    assert row.in_way_to_client == Decimal("0")
    assert row.in_way_from_client == Decimal("3")


@pytest.mark.asyncio
async def test_list_issues_financial_final_blocker_filter_hides_finance_mismatch() -> None:
    service = DataQualityService()
    issue_supply_only = DataQualityIssue(
        id=1,
        account_id=1,
        domain="supplies",
        severity="error",
        code="unmatched_sku",
        source_table="wb_supply_goods",
        message="Supply-level unmatched",
        payload={
            "sourceKind": "source_level",
            "sourceDomains": ["supplies"],
            "classificationReason": "missing_nm_id",
        },
        detected_at=datetime.now(timezone.utc),
        resolved_at=None,
        effective_financial_final_blocker=True,
    )
    issue_finance = DataQualityIssue(
        id=2,
        account_id=1,
        domain="finance",
        severity="error",
        code="finance_reconciliation_mismatch",
        source_table="mart_finance_reconciliation",
        message="Mismatch",
        payload={},
        detected_at=datetime.now(timezone.utc),
        resolved_at=None,
        effective_financial_final_blocker=True,
    )

    class _Repo:
        async def list_filtered(self, session, **kwargs):
            return SimpleNamespace(
                total=2,
                limit=kwargs["limit"],
                offset=kwargs["offset"],
                items=[issue_supply_only, issue_finance],
            )

    service.repo = _Repo()

    page = await service.list_issues(
        None,
        account_id=1,
        only_open=True,
        financial_final_blocker=True,
        limit=50,
        offset=0,
    )

    assert page.total == 0
    assert page.items == []


def test_extract_price_supports_flat_payload() -> None:
    base_price, discounted_price = MartService._extract_price(
        {"price": "320", "discountedPrice": "250"}
    )

    assert base_price == Decimal("320")
    assert discounted_price == Decimal("250")


def test_manual_cost_amounts_use_cost_price_plus_seller_other_expense() -> None:
    amounts = MartService._manual_cost_amounts(
        SimpleNamespace(
            cost_price=Decimal("100"),
            unit_cost=Decimal("100"),
            seller_other_expense=Decimal("15"),
            packaging_cost=Decimal("4"),
            inbound_logistics_cost=Decimal("6"),
        ),
        net_qty=3,
    )

    assert amounts["cost_price"] == Decimal("100")
    assert amounts["seller_other_expense_unit"] == Decimal("15")
    assert amounts["total_unit_cost"] == Decimal("115")
    assert amounts["seller_cogs_total"] == Decimal("300")
    assert amounts["seller_other_expense_total"] == Decimal("45")
    assert amounts["estimated_cogs_total"] == Decimal("345")


def test_manual_cost_totals_do_not_include_wb_logistics() -> None:
    seller_expense_total = total_seller_expenses(
        SimpleNamespace(
            seller_cogs=Decimal("300"),
            seller_other_expense=Decimal("45"),
            wb_logistics=Decimal("90"),
        )
    )

    assert seller_expense_total == Decimal("345")


def test_reconciliation_finance_row_filter_only_keeps_sale_docs() -> None:
    sale_row = WBRealizationReportRow(doc_type_name="Продажа")
    service_row = WBRealizationReportRow(doc_type_name=None)

    assert MartService._is_reconcilable_finance_row(sale_row) is True
    assert MartService._is_reconcilable_finance_row(service_row) is False


def test_reconciliation_should_ignore_finance_rows_without_nm_id() -> None:
    row = WBRealizationReportRow(doc_type_name="Продажа", nm_id=None)

    assert MartService._is_reconcilable_finance_row(row) is True
    assert row.nm_id is None


@pytest.mark.parametrize(
    ("field_name", "field_value", "payload", "expected_category"),
    [
        ("delivery_service", Decimal("100"), {}, EXPENSE_CATEGORY_WB_LOGISTICS),
        ("rebill_logistic_cost", Decimal("40"), {}, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL),
        ("paid_storage", Decimal("20"), {}, EXPENSE_CATEGORY_STORAGE),
        ("penalty", Decimal("30"), {}, EXPENSE_CATEGORY_PENALTY),
        ("acquiring_fee", Decimal("10"), {}, EXPENSE_CATEGORY_PAYMENT_PROCESSING),
        ("ignored", Decimal("0"), {"ppvzReward": 5}, EXPENSE_CATEGORY_PVZ_REWARD),
    ],
)
def test_finance_expense_details_map_normalized_categories(
    field_name: str,
    field_value: Decimal,
    payload: dict[str, object],
    expected_category: str,
) -> None:
    kwargs = {"payload": payload}
    if field_name != "ignored":
        kwargs[field_name] = field_value
    row = _finance_row(**kwargs)

    details = MartService._finance_expense_details(row, sku_id=55)

    assert details["issues"] == []
    expected_amount = field_value if field_name != "ignored" else Decimal("5")
    assert details["totals"][expected_category] == expected_amount
    categories = {entry["expense_category"] for entry in details["entries"]}
    assert expected_category in categories


def test_finance_expense_details_classifies_marketing_deduction_by_text() -> None:
    row = _finance_row(
        deduction=Decimal("50"),
        seller_oper_name="Оказание услуг «WB Продвижение»",
    )

    details = MartService._finance_expense_details(row, sku_id=55)

    assert details["totals"][EXPENSE_CATEGORY_MARKETING_DEDUCTION] == Decimal("50")
    assert details["totals"][EXPENSE_CATEGORY_DEDUCTION] == Decimal("0")


def test_finance_expense_details_keeps_generic_deduction_without_marketing_text() -> None:
    row = _finance_row(
        deduction=Decimal("50"),
        seller_oper_name="Удержание по возврату",
    )

    details = MartService._finance_expense_details(row, sku_id=55)

    assert details["totals"][EXPENSE_CATEGORY_DEDUCTION] == Decimal("50")
    assert details["totals"][EXPENSE_CATEGORY_MARKETING_DEDUCTION] == Decimal("0")


def test_finance_expense_details_creates_unclassified_issue_for_unknown_non_zero_amount() -> None:
    row = _finance_row(payload={"mysteryCharge": 17})

    details = MartService._finance_expense_details(row, sku_id=55)

    assert details["totals"][EXPENSE_CATEGORY_UNCLASSIFIED] == Decimal("17")
    assert len(details["issues"]) == 1
    assert details["issues"][0]["code"] == "expense_unclassified"
    assert details["issues"][0]["payload"]["sourceField"] == "mysteryCharge"


def test_finance_expense_details_ignores_technical_numeric_payload_fields() -> None:
    row = _finance_row(
        payload={
            "shkId": 987654321012345,
            "reportId": 123456789,
            "commissionPercent": 19.5,
            "deliveryCoef": 2.3,
        }
    )

    details = MartService._finance_expense_details(row, sku_id=55)

    assert details["totals"][EXPENSE_CATEGORY_UNCLASSIFIED] == Decimal("0")
    assert details["issues"] == []


@pytest.mark.asyncio
async def test_check_expense_finance_report_missing_opens_issue_when_sales_exist() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _scalar_result(0),
                _scalar_result(8),
                _scalar_result(0),
            ]
        )
    )

    touched = await service._check_expense_finance_report_missing(
        session,
        account_id=1,
        today=date(2026, 6, 3),
    )

    assert touched == 1
    assert service.open_issue.await_args.kwargs["code"] == "expense_finance_report_missing"
    assert service.open_issue.await_args.kwargs["payload"]["salesRowCount"] == 8


@pytest.mark.asyncio
async def test_check_expense_logistics_missing_opens_issue_when_logistics_zero() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _scalar_result(12),
                _scalar_result(5),
                _scalar_result(0),
            ]
        )
    )

    touched = await service._check_expense_logistics_missing(
        session,
        account_id=1,
        today=date(2026, 6, 3),
    )

    assert touched == 1
    assert service.open_issue.await_args.kwargs["code"] == "expense_logistics_missing"
    assert service.open_issue.await_args.kwargs["payload"]["deliveryReturnRowCount"] == 5


@pytest.mark.asyncio
async def test_check_expense_ad_double_count_risk_opens_issue_for_operational_final_source() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    rows = [
        SimpleNamespace(
            stat_date=date(2026, 6, 2),
            sku_id=77,
            nm_id=7007,
            marketing_deduction=Decimal("40"),
            ad_spend_operational=Decimal("65"),
            ad_spend_source="ads_api",
            ad_spend_final=Decimal("65"),
        )
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=_scalars_result(rows)))

    touched = await service._check_expense_ad_double_count_risk(
        session,
        account_id=1,
        today=date(2026, 6, 3),
    )

    assert touched == 1
    assert service.open_issue.await_args.kwargs["code"] == "expense_ad_double_count_risk"
    assert service.open_issue.await_args.kwargs["sku_id"] == 77


@pytest.mark.asyncio
async def test_check_expense_negative_unexpected_opens_issue_for_income_signed_expense_row() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    rows = [
        SimpleNamespace(
            stat_date=date(2026, 6, 1),
            report_id=11,
            rrd_id=22,
            expense_category="wb_logistics",
            amount=Decimal("9"),
            source_field="delivery_service",
            seller_oper_name="Корректировка логистики",
            bonus_type_name=None,
            sku_id=1,
            nm_id=1001,
        )
    ]
    session = SimpleNamespace(execute=AsyncMock(return_value=_scalars_result(rows)))

    touched = await service._check_expense_negative_unexpected(
        session,
        account_id=1,
        today=date(2026, 6, 3),
    )

    assert touched == 1
    assert service.open_issue.await_args.kwargs["code"] == "expense_negative_unexpected"
    assert service.open_issue.await_args.kwargs["payload"]["amount"] == "9"


@pytest.mark.asyncio
async def test_check_expense_large_logistics_share_opens_warning_with_payload() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                SimpleNamespace(one=lambda: (Decimal("80"), Decimal("80"), Decimal("0"), Decimal("0"), 2)),
                SimpleNamespace(one=lambda: (Decimal("10"), Decimal("10"), Decimal("0"))),
                _scalar_result({"large_logistics_share_threshold_percent": 70}),
            ]
        )
    )

    touched = await service._check_expense_large_logistics_share(
        session,
        account_id=1,
        today=date(2026, 6, 3),
    )

    assert touched == 1
    kwargs = service.open_issue.await_args.kwargs
    assert kwargs["code"] == "expense_large_logistics_share"
    assert kwargs["severity"] == "warning"
    assert kwargs["payload"]["logisticsTotal"] == "80"
    assert kwargs["payload"]["expenseBaseKind"] == "wb_expenses"
    assert kwargs["payload"]["sharePercent"] == "100.00"


@pytest.mark.asyncio
async def test_check_expense_no_drilldown_rows_opens_issue_when_signals_exist_without_rows() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _scalar_result(4),
                _scalar_result(0),
            ]
        )
    )

    touched = await service._check_expense_no_drilldown_rows(
        session,
        account_id=1,
        today=date(2026, 6, 3),
    )

    assert touched == 1
    assert service.open_issue.await_args.kwargs["code"] == "expense_no_drilldown_rows"


@pytest.mark.asyncio
async def test_check_manual_cost_upload_warnings_opens_latest_upload_issues() -> None:
    service = DataQualityService()
    service.open_issue = AsyncMock()
    upload = SimpleNamespace(
        id=99,
        summary={
            "legacyFieldMappedRows": 3,
            "legacyFieldNames": ["packaging_cost", "inbound_logistics_cost"],
            "sellerOtherExpenseRequiredByConfig": True,
            "sellerOtherExpenseMissingRows": 2,
        },
    )
    session = SimpleNamespace(execute=AsyncMock(return_value=_scalar_result(upload)))

    touched = await service._check_manual_cost_upload_warnings(session, account_id=1)

    assert touched == 2
    assert service.open_issue.await_count == 2
    opened_codes = [call.kwargs["code"] for call in service.open_issue.await_args_list]
    assert opened_codes == ["manual_cost_old_fields_used", "seller_other_expense_missing"]


def test_finance_row_date_prefers_sale_datetime() -> None:
    row = WBRealizationReportRow(
        rr_date=date(2026, 5, 15),
        sale_dt=datetime(2026, 5, 14, 12, 0, tzinfo=timezone.utc),
    )

    assert MartService._finance_row_date(row) == date(2026, 5, 14)


@pytest.mark.asyncio
async def test_classify_issue_as_expected_lag_keeps_issue_open_but_removes_final_blocker() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=1,
        account_id=1,
        domain="finance",
        severity="error",
        code="finance_reconciliation_mismatch",
        source_table="wb_realization_report_rows",
        message="Mismatch",
        payload={},
        detected_at=datetime.now(timezone.utc),
        resolved_at=None,
    )
    service._refresh_issue_final_blocker_state(issue)
    session = SimpleNamespace(
        get=AsyncMock(return_value=issue),
        flush=AsyncMock(),
    )

    result = await service.classify_issue_by_id(
        session,
        issue_id=1,
        classification_status="expected_lag",
        classification_reason="WB finance report not closed yet",
        user_id=99,
    )

    assert result.classification_status == "expected_lag"
    assert result.classified_by_user_id == 99
    assert result.resolved_at is None
    assert result.effective_financial_final_blocker is False


@pytest.mark.asyncio
async def test_bulk_classify_updates_multiple_issues() -> None:
    service = DataQualityService()
    first = DataQualityIssue(
        id=1,
        account_id=1,
        domain="finance",
        severity="warning",
        code="sale_without_finance",
        source_table="wb_realization_report_rows",
        message="Missing finance row",
        payload={},
        detected_at=datetime.now(timezone.utc),
        resolved_at=None,
    )
    second = DataQualityIssue(
        id=2,
        account_id=1,
        domain="cost",
        severity="warning",
        code="missing_manual_cost",
        source_table="manual_costs",
        message="Missing cost",
        payload={},
        detected_at=datetime.now(timezone.utc),
        resolved_at=None,
    )
    issues = {1: first, 2: second}
    session = SimpleNamespace(
        get=AsyncMock(side_effect=lambda _model, issue_id: issues.get(issue_id)),
        flush=AsyncMock(),
    )

    updated = await service.bulk_update_issues(
        session,
        ids=[1, 2],
        action="classify",
        classification_status="known_exception",
        classification_reason="Accepted for audit window",
        financial_final_blocker_override=False,
        user_id=55,
    )

    assert updated == 2
    assert first.classification_status == "known_exception"
    assert second.classification_status == "known_exception"
    assert first.effective_financial_final_blocker is False
    assert second.effective_financial_final_blocker is False


def test_normalize_issue_runtime_flags_downgrades_payout_only_finance_mismatch() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=1,
        account_id=1,
        domain="finance",
        severity="error",
        code="finance_reconciliation_mismatch",
        source_table="mart_finance_reconciliation",
        message="Payout-only mismatch",
        payload={
            "classificationStatus": "classified",
            "classificationReason": "real_mismatch",
            "revenueDelta": "0",
            "forPayDelta": "315.44",
        },
        detected_at=datetime.now(timezone.utc),
        resolved_at=None,
        effective_financial_final_blocker=True,
    )

    normalized = service._normalize_issue_runtime_flags(issue)

    assert normalized.effective_financial_final_blocker is False


def test_reconciliation_bucket_uses_pending_warning_error_by_age() -> None:
    pending = MartService._reconciliation_bucket(
        age_days=2,
        has_order_without_sale=True,
        has_sale_without_finance=False,
        has_finance_without_sale=False,
        has_stock_without_sales=False,
        has_ad_spend_without_sales=False,
        has_price_anomaly=False,
    )
    warning = MartService._reconciliation_bucket(
        age_days=5,
        has_order_without_sale=False,
        has_sale_without_finance=True,
        has_finance_without_sale=False,
        has_stock_without_sales=False,
        has_ad_spend_without_sales=False,
        has_price_anomaly=False,
    )
    error = MartService._reconciliation_bucket(
        age_days=10,
        has_order_without_sale=False,
        has_sale_without_finance=True,
        has_finance_without_sale=False,
        has_stock_without_sales=False,
        has_ad_spend_without_sales=False,
        has_price_anomaly=False,
    )

    assert pending == ("pending", "expected_lag")
    assert warning == ("warning", "finance_lag")
    assert error == ("error", "missing_finance")


def test_aggregate_sku_items_groups_week_and_recomputes_ratios() -> None:
    rows = [
        SimpleNamespace(
            account_id=1,
            stat_date=date(2026, 5, 18),
            sku_id=10,
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="111",
            title="Alpha",
            brand="Brand",
            subject_name="Cat",
            final_revenue_source="finance",
            opening_stock_qty=Decimal("8"),
            closing_stock_qty=Decimal("6"),
            in_way_to_client=Decimal("1"),
            in_way_from_client=Decimal("0"),
            current_price=Decimal("300"),
            current_discounted_price=Decimal("250"),
            avg_sale_price=Decimal("250"),
            seller_discount=10,
            club_discount=0,
            cost_price=Decimal("100"),
            packaging_cost=Decimal("10"),
            inbound_logistics_cost=Decimal("5"),
            total_unit_cost=Decimal("115"),
            has_manual_cost=True,
            has_real_manual_cost=True,
            has_placeholder_cost=False,
            business_trusted=True,
            cost_source="manual_upload",
            has_open_issues=False,
            payload={},
            order_rows=1,
            ordered_units=2,
            cancelled_orders=0,
            sale_rows=1,
            finance_rows=1,
            operational_sales_qty=1,
            operational_return_qty=0,
            operational_revenue=Decimal("100"),
            operational_for_pay=Decimal("90"),
            finance_sales_qty=1,
            finance_return_qty=0,
            finance_net_units=1,
            finance_revenue=Decimal("100"),
            finance_for_pay=Decimal("90"),
            final_sales_qty=1,
            final_return_qty=0,
            final_net_qty=1,
            final_revenue=Decimal("100"),
            final_for_pay=Decimal("90"),
            commission=Decimal("5"),
            acquiring_fee=Decimal("2"),
            logistics=Decimal("1"),
            paid_acceptance=Decimal("0"),
            storage=Decimal("0"),
            penalties=Decimal("0"),
            deductions=Decimal("0"),
            additional_payments=Decimal("0"),
            ad_spend=Decimal("10"),
            ad_views=100,
            ad_clicks=10,
            funnel_opens=50,
            funnel_carts=5,
            funnel_orders=2,
            funnel_buyouts=1,
            estimated_cogs=Decimal("40"),
            estimated_profit_before_ads=Decimal("52"),
            estimated_profit_after_ads=Decimal("42"),
        ),
        SimpleNamespace(
            account_id=1,
            stat_date=date(2026, 5, 20),
            sku_id=10,
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="111",
            title="Alpha",
            brand="Brand",
            subject_name="Cat",
            final_revenue_source="finance",
            opening_stock_qty=Decimal("6"),
            closing_stock_qty=Decimal("4"),
            in_way_to_client=Decimal("0"),
            in_way_from_client=Decimal("1"),
            current_price=Decimal("320"),
            current_discounted_price=Decimal("260"),
            avg_sale_price=Decimal("260"),
            seller_discount=12,
            club_discount=0,
            cost_price=Decimal("100"),
            packaging_cost=Decimal("10"),
            inbound_logistics_cost=Decimal("5"),
            total_unit_cost=Decimal("115"),
            has_manual_cost=True,
            has_real_manual_cost=True,
            has_placeholder_cost=False,
            business_trusted=True,
            cost_source="manual_upload",
            has_open_issues=False,
            payload={},
            order_rows=1,
            ordered_units=1,
            cancelled_orders=0,
            sale_rows=1,
            finance_rows=1,
            operational_sales_qty=1,
            operational_return_qty=0,
            operational_revenue=Decimal("50"),
            operational_for_pay=Decimal("45"),
            finance_sales_qty=1,
            finance_return_qty=0,
            finance_net_units=1,
            finance_revenue=Decimal("50"),
            finance_for_pay=Decimal("45"),
            final_sales_qty=1,
            final_return_qty=0,
            final_net_qty=1,
            final_revenue=Decimal("50"),
            final_for_pay=Decimal("45"),
            commission=Decimal("3"),
            acquiring_fee=Decimal("1"),
            logistics=Decimal("1"),
            paid_acceptance=Decimal("0"),
            storage=Decimal("0"),
            penalties=Decimal("0"),
            deductions=Decimal("0"),
            additional_payments=Decimal("0"),
            ad_spend=Decimal("5"),
            ad_views=50,
            ad_clicks=5,
            funnel_opens=25,
            funnel_carts=2,
            funnel_orders=1,
            funnel_buyouts=1,
            estimated_cogs=Decimal("20"),
            estimated_profit_before_ads=Decimal("25"),
            estimated_profit_after_ads=Decimal("20"),
        ),
    ]

    page = MartService._aggregate_sku_items(rows, aggregate="week", sort_by="stat_date", sort_dir="desc", limit=50, offset=0)

    assert page.total == 1
    item = page.items[0]
    assert item.stat_date == date(2026, 5, 18)
    assert item.final_revenue == 150.0
    assert item.ad_spend == 15.0
    assert round(item.margin_percent or 0, 2) == 41.33
    assert round(item.roi_percent or 0, 2) == 103.33
    assert round(item.drr_percent or 0, 2) == 10.0
    assert item.current_price == 320.0
    assert item.opening_stock_qty == 8.0
    assert item.closing_stock_qty == 4.0


def test_aggregate_reconciliation_items_keeps_worst_status_in_period() -> None:
    rows = [
        SimpleNamespace(
            account_id=1,
            stat_date=date(2026, 5, 18),
            sku_id=10,
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="111",
            title="Alpha",
            brand="Brand",
            subject_name="Cat",
            orders_qty=1,
            orders_amount=Decimal("100"),
            sales_qty=0,
            sales_amount=Decimal("0"),
            returns_qty=0,
            returns_amount=Decimal("0"),
            finance_qty=0,
            finance_revenue=Decimal("0"),
            finance_for_pay=Decimal("0"),
            ad_spend=Decimal("0"),
            ad_orders=0,
            opening_stock_qty=Decimal("10"),
            closing_stock_qty=Decimal("9"),
            avg_sale_price=Decimal("0"),
            current_price=Decimal("300"),
            current_discounted_price=Decimal("250"),
            revenue_delta=Decimal("100"),
            for_pay_delta=Decimal("90"),
            status_bucket="pending",
            status_reason="expected_lag",
            has_order_without_sale=True,
            has_sale_without_finance=False,
            has_finance_without_sale=False,
            has_stock_without_sales=False,
            has_ad_spend_without_sales=False,
            has_price_anomaly=False,
            payload={},
        ),
        SimpleNamespace(
            account_id=1,
            stat_date=date(2026, 5, 20),
            sku_id=10,
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="111",
            title="Alpha",
            brand="Brand",
            subject_name="Cat",
            orders_qty=0,
            orders_amount=Decimal("0"),
            sales_qty=1,
            sales_amount=Decimal("50"),
            returns_qty=0,
            returns_amount=Decimal("0"),
            finance_qty=0,
            finance_revenue=Decimal("0"),
            finance_for_pay=Decimal("0"),
            ad_spend=Decimal("5"),
            ad_orders=1,
            opening_stock_qty=Decimal("9"),
            closing_stock_qty=Decimal("7"),
            avg_sale_price=Decimal("50"),
            current_price=Decimal("320"),
            current_discounted_price=Decimal("260"),
            revenue_delta=Decimal("50"),
            for_pay_delta=Decimal("45"),
            status_bucket="error",
            status_reason="missing_finance",
            has_order_without_sale=False,
            has_sale_without_finance=True,
            has_finance_without_sale=False,
            has_stock_without_sales=False,
            has_ad_spend_without_sales=True,
            has_price_anomaly=False,
            payload={},
        ),
    ]

    page = MartService._aggregate_reconciliation_items(rows, aggregate="week", sort_by="stat_date", sort_dir="desc", limit=50, offset=0)

    assert page.total == 1
    item = page.items[0]
    assert item.stat_date == date(2026, 5, 18)
    assert item.status_bucket == "error"
    assert item.status_reason == "missing_finance"
    assert item.orders_qty == 1
    assert item.sales_qty == 1
    assert item.ad_spend == 5.0
    assert item.current_price == 320.0


def test_detected_issue_status_is_not_treated_as_classified() -> None:
    issue = SimpleNamespace(payload={"classificationStatus": "detected"})

    assert DataQualityService._issue_is_classified(issue) is False


@pytest.mark.asyncio
async def test_load_cost_rows_fetches_costs_overlapping_requested_range() -> None:
    service = MartService()
    session = object()
    expected_rows = [object()]
    service.cost_repo.list_overlapping_for_account = AsyncMock(return_value=expected_rows)

    result = await service._load_cost_rows(
        session,
        account_id=1,
        date_from=date(2026, 3, 29),
        date_to=date(2026, 5, 19),
    )

    service.cost_repo.list_overlapping_for_account.assert_awaited_once_with(
        session,
        account_id=1,
        date_from=date(2026, 3, 29),
        date_to=date(2026, 5, 19),
    )
    assert result == expected_rows
