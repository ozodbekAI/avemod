from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi import HTTPException
import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.data_quality import DataQualityIssue
from app.models.finance import WBRealizationReportRow
from app.models.marts import MartExpenseDaily, MartFinanceReconciliation, MartSKUDaily
from app.models.orders import WBOrder
from app.models.operator import ResultEvent
from app.models.problem_engine import ProblemDefinition, ProblemInstance, ProblemInstanceHistory, ProblemRuleVersion
from app.models.product_cards import CoreSKU
from app.models.sales import WBSale
from app.schemas.data_quality import GuidedFixActionRequest
from app.schemas.money_management import DataBlockerRead
from app.services.data_quality import DataQualityService
from app.services.money_management import MoneyManagementService


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw) -> str:
    return "INTEGER"


PRIORITY_CODES = [
    "missing_manual_cost",
    "missing_cost_blocks_profit",
    "manual_cost_unresolved_sku",
    "manual_cost_ambiguous_match",
    "unmatched_sku",
    "expense_unclassified",
    "unclassified_finance_expense",
    "ad_spend_without_sku",
    "ads_overallocated_to_profitability",
    "finance_reconciliation_mismatch",
    "sale_without_finance",
    "finance_without_sale",
    "sales_without_stock",
    "stock_without_sales",
    "order_without_sale_or_return",
    "price_jump",
    "price_zero_or_too_low",
    "missing_chrt_id",
]


@pytest.mark.parametrize("code", PRIORITY_CODES)
def test_guided_fix_definition_exists_for_priority_codes(code: str) -> None:
    definition = DataQualityService.guided_fix_definition_for_code(code)

    assert definition.owner_type in {"seller", "operator", "system", "admin", "waiting", "business"}
    assert definition.fixability in {"fix_in_platform", "partial", "sync_required", "admin_only", "system_only", "wait", "business_decision"}
    assert definition.issue_nature in {"data_blocker", "sync_waiting", "system_check", "business_signal", "finance_investigation"}
    assert definition.primary_action_code
    assert definition.primary_action_label
    assert definition.target_href
    assert definition.fix_component_type in {
        "upload_cost_file",
        "map_sku",
        "classify_expense",
        "rerun_sync",
        "open_finance_reconciliation",
        "wait_for_wb_report",
        "review_price",
        "open_card_mapping",
        "admin_investigation",
        "cost_inline_editor",
        "sku_mapping",
        "expense_classification",
        "stock_decision",
        "sync_recheck",
        "ads_allocation_status",
        "card_mapping",
    }
    assert definition.affected_rows_query["endpoint"] == "GET /api/v1/dq/issues/{id}/resolution-context"
    assert definition.preview_before_change
    if code in {"missing_manual_cost", "missing_cost_blocks_profit"}:
        assert definition.apply_action["endpoint"] == "POST /api/v1/costs/inline-save"
        assert definition.apply_action["type"] == "save_costs_inline"
    else:
        assert definition.apply_action["endpoint"] == "POST /api/v1/dq/issues/{id}/guided-action"
    assert definition.recheck_query["action_type"] == "trigger_recheck"
    assert definition.success_state
    assert definition.failure_state


def test_guided_fix_marks_user_fixable_codes_inside_platform() -> None:
    expected = {
        "missing_manual_cost": "cost_inline_editor",
        "missing_cost_blocks_profit": "cost_inline_editor",
        "manual_cost_unresolved_sku": "sku_mapping",
        "manual_cost_ambiguous_match": "sku_mapping",
        "unmatched_sku": "sku_mapping",
        "expense_unclassified": "expense_classification",
        "unclassified_finance_expense": "expense_classification",
    }

    for code, component in expected.items():
        definition = DataQualityService.guided_fix_definition_for_code(code)
        assert definition.can_user_fix_inside_platform is True
        assert definition.fixability == "fix_in_platform"
        assert definition.issue_nature == "data_blocker"
        assert definition.fix_component_type == component
        assert definition.required_inputs


@pytest.mark.parametrize(
    "code",
    ["finance_reconciliation_mismatch", "sale_without_finance", "finance_without_sale"],
)
def test_finance_reconciliation_guided_fix_never_allows_manual_wb_fact_edits(code: str) -> None:
    definition = DataQualityService.guided_fix_definition_for_code(code)

    assert definition.can_user_fix_inside_platform is False
    assert definition.fixability in {"admin_only", "sync_required", "wait"}
    assert definition.is_manual_edit_allowed is False
    assert "manual_edit_wb_finance_facts" in definition.apply_action["forbidden"]
    assert any("read-only" in note.lower() for note in definition.safety_notes)


def test_guided_fix_audit_history_is_stored_on_issue_payload() -> None:
    issue = DataQualityIssue(
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="missing_manual_cost",
        entity_key="nm:123",
        source_table="mart_sku_daily",
        message="Missing cost",
        payload={"nmId": 123},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    issue.id = 10

    DataQualityService._append_guided_fix_audit(
        issue,
        action_type="mark_cost_upload_started",
        status="ok",
        message="Cost upload started",
        user_id=42,
        inputs={"filename": "costs.xlsx"},
        comment="uploaded from workbench",
    )

    history = DataQualityService._guided_fix_audit_history(issue)
    assert len(history) == 1
    assert history[0]["actionType"] == "mark_cost_upload_started"
    assert history[0]["status"] == "ok"
    assert history[0]["message"] == "Cost upload started"
    assert history[0]["userId"] == 42
    assert history[0]["createdAt"]


def test_data_quality_router_exposes_guided_workflow_endpoints() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    router_text = (repo_root / "app/modules/data_quality/router.py").read_text(encoding="utf-8")

    assert '"/dq/issues/{issue_id}/resolution-context"' in router_text
    assert '"/dq/issues/{issue_id}/affected-rows.csv"' in router_text
    assert '"/dq/issues/{issue_id}/guided-action"' in router_text
    assert '"/dq/issues/{issue_id}/recheck"' in router_text
    assert "GuidedFixActionRequest" in router_text
    assert "DataQualityIssueRecheckResponse" in router_text
    assert "DataQualityResolutionContext" in router_text


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self._rows


class _FakeSession:
    def __init__(self, *batches, issue=None):
        self.batches = list(batches)
        self.issue = issue

    async def execute(self, _stmt):
        if not self.batches:
            return _FakeResult([])
        return _FakeResult(self.batches.pop(0))

    async def get(self, _model, _id):
        return self.issue


class _SQLiteAsyncSessionAdapter:
    def __init__(self, sync_session: Session):
        self._session = sync_session

    async def execute(self, statement):
        return self._session.execute(statement)

    async def get(self, model, ident):
        return self._session.get(model, ident)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()

    async def refresh(self, instance) -> None:
        self._session.refresh(instance)


def _problem_result_session() -> tuple[Session, _SQLiteAsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    for table in (
        WBAccount.__table__,
        DataQualityIssue.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
        ResultEvent.__table__,
    ):
        table.create(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=1, name="Test account"))
    sync_session.flush()
    return sync_session, _SQLiteAsyncSessionAdapter(sync_session)


@pytest.mark.asyncio
async def test_missing_manual_cost_affected_rows_use_real_sku_and_mart_samples() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=101,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="missing_manual_cost",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Missing cost",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "vendorCode": "VC-1", "apiToken": "must-not-leak"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    core = CoreSKU(
        id=10,
        account_id=1,
        dedupe_key="core-10",
        nm_id=1001,
        vendor_code="VC-1",
        barcode="B-1",
        sku="SKU-1",
        title="Product",
        brand="Brand",
        is_active=True,
        status="active",
    )
    mart = MartSKUDaily(
        id=20,
        account_id=1,
        dedupe_key="mart-20",
        stat_date=date(2026, 7, 2),
        sku_id=10,
        nm_id=1001,
        vendor_code="VC-1",
        barcode="B-1",
        title="Product",
        sale_rows=3,
        final_sales_qty=3,
        final_revenue=Decimal("12000.00"),
        closing_stock_qty=Decimal("4"),
        current_discounted_price=Decimal("3000"),
        has_manual_cost=False,
        has_real_manual_cost=False,
        business_trusted=False,
    )

    rows, total = await service._affected_rows_for_issue(_FakeSession([core], [mart]), issue, limit=50, offset=0)

    assert total == 3
    assert any(row["source"] == "mart_sku_daily.missing_supplier_cost" for row in rows)
    mart_row = next(row for row in rows if row["source"] == "mart_sku_daily.missing_supplier_cost")
    assert mart_row["nm_id"] == 1001
    assert mart_row["vendor_code"] == "VC-1"
    assert mart_row["missing_or_invalid_value"] == "cost_price"
    assert mart_row["suggested_fix"]["action_type"] == "save_costs_inline"
    assert mart_row["suggested_fix"]["endpoint"] == "POST /api/v1/costs/inline-save"
    assert mart_row["row_status"] == "needs_cost"
    assert "apiToken" not in {key for row in rows for key in row}


@pytest.mark.asyncio
async def test_finance_reconciliation_affected_rows_include_source_documents() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=102,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="finance_reconciliation_mismatch",
        entity_key="srid-1",
        source_table="mart_finance_reconciliation",
        message="Mismatch",
        nm_id=1001,
        payload={"srid": "srid-1", "revenueDelta": "500"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    rec = MartFinanceReconciliation(
        id=1,
        account_id=1,
        dedupe_key="rec-1",
        stat_date=date(2026, 7, 1),
        srid="srid-1",
        nm_id=1001,
        order_rows=1,
        sale_rows=1,
        finance_rows=1,
        sale_revenue=Decimal("2000"),
        finance_revenue=Decimal("1500"),
        sale_for_pay=Decimal("1600"),
        finance_for_pay=Decimal("1200"),
        revenue_delta=Decimal("500"),
        for_pay_delta=Decimal("400"),
        status="mismatch",
    )
    sale = WBSale(
        id=2,
        account_id=1,
        dedupe_key="sale-1",
        srid="srid-1",
        last_change_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        nm_id=1001,
        sale_id="S1",
        finished_price=Decimal("2000"),
        for_pay=Decimal("1600"),
    )
    order = WBOrder(
        id=3,
        account_id=1,
        dedupe_key="order-1",
        srid="srid-1",
        last_change_date=datetime(2026, 7, 1, tzinfo=timezone.utc),
        nm_id=1001,
        order_id=9001,
        finished_price=Decimal("2000"),
    )
    report = WBRealizationReportRow(
        id=4,
        account_id=1,
        rrd_id=77,
        srid="srid-1",
        rr_date=date(2026, 7, 2),
        nm_id=1001,
        retail_amount=Decimal("1500"),
        for_pay=Decimal("1200"),
        is_reconcilable=True,
    )

    rows, total = await service._affected_rows_for_issue(
        _FakeSession([rec], [sale], [order], [report]),
        issue,
        limit=50,
        offset=0,
    )

    assert total == 5
    sources = {row["source"] for row in rows}
    assert "mart_finance_reconciliation.exact_delta" in sources
    assert "wb_sales.reconciliation_source" in sources
    assert "wb_orders.reconciliation_source" in sources
    assert "wb_realization_report_rows.reconciliation_source" in sources
    rec_row = next(row for row in rows if row["source"] == "mart_finance_reconciliation.exact_delta")
    assert rec_row["row_status"] == "admin_investigation"
    assert rec_row["suggested_fix"]["forbidden"] == ["manual_edit_wb_finance_facts"]
    assert rec_row["missing_or_invalid_value"] == {"revenue_delta": "500", "for_pay_delta": "400"}


@pytest.mark.asyncio
async def test_affected_rows_csv_uses_whitelisted_fields_and_pagination_source() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=103,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="missing_manual_cost",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Missing cost",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "apiToken": "must-not-leak"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    core = CoreSKU(id=10, account_id=1, dedupe_key="core-10", nm_id=1001, vendor_code="VC-1", is_active=True, status="active")
    mart = MartSKUDaily(
        id=20,
        account_id=1,
        dedupe_key="mart-20",
        stat_date=date(2026, 7, 2),
        sku_id=10,
        nm_id=1001,
        vendor_code="VC-1",
        final_revenue=Decimal("12000.00"),
        has_manual_cost=False,
        has_real_manual_cost=False,
    )

    csv_text = await service.affected_rows_csv(_FakeSession([core], [mart], issue=issue), issue_id=103)

    assert "source" in csv_text
    assert "mart_sku_daily.missing_supplier_cost" in csv_text
    assert "apiToken" not in csv_text
    assert "must-not-leak" not in csv_text


@pytest.mark.asyncio
async def test_resolution_context_exposes_paginated_affected_rows_metadata() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=104,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="missing_manual_cost",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Missing cost",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "apiToken": "must-not-leak"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    core = CoreSKU(
        id=10,
        account_id=1,
        dedupe_key="core-10",
        nm_id=1001,
        vendor_code="VC-1",
        is_active=True,
        status="active",
    )
    mart = MartSKUDaily(
        id=20,
        account_id=1,
        dedupe_key="mart-20",
        stat_date=date(2026, 7, 2),
        sku_id=10,
        nm_id=1001,
        vendor_code="VC-1",
        final_revenue=Decimal("12000.00"),
        has_manual_cost=False,
        has_real_manual_cost=False,
    )

    ctx = await service.resolution_context(
        _FakeSession([core], [mart], issue=issue),
        issue_id=104,
        affected_rows_limit=1,
        affected_rows_offset=1,
    )

    assert ctx.affected_rows_total == 3
    assert ctx.affected_rows_limit == 1
    assert ctx.affected_rows_offset == 1
    assert ctx.affected_rows_export_endpoint == "/dq/issues/104/affected-rows.csv"
    assert ctx.issue_id == 104
    assert ctx.issue_code == "missing_manual_cost"
    assert ctx.owner_type == "seller"
    assert ctx.fixability == "fix_in_platform"
    assert ctx.issue_nature == "data_blocker"
    assert ctx.can_user_fix_inside_platform is True
    assert ctx.is_manual_edit_allowed is True
    assert ctx.fix_component_type == "cost_inline_editor"
    assert ctx.preview_available is True
    assert ctx.apply_available is True
    assert ctx.recheck_available is True
    assert ctx.disabled_reason is None
    assert ctx.action_center_href == "/action-center?issue_code=missing_manual_cost&nm_id=1001"
    assert ctx.results_href == "/results?problem_code=missing_manual_cost&nm_id=1001"
    assert ctx.suggested_fix_action["endpoint"] == "POST /api/v1/costs/inline-save"
    assert ctx.resolver is not None
    assert ctx.resolver.component_type == "cost_inline_editor"
    assert ctx.resolver.affected_rows_endpoint == "/dq/issues/104/resolution-context"
    assert len(ctx.affected_rows) == 1
    affected_rows_fact = next(fact for fact in ctx.source_facts if fact.label == "Affected source rows")
    assert affected_rows_fact.row_count == 3
    assert "apiToken" not in {key for row in ctx.affected_rows for key in row}
    assert "raw_payload" not in ctx.affected_rows[0]


@pytest.mark.asyncio
async def test_missing_cost_blocks_profit_context_is_user_fixable_cost_workbench() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=105,
        account_id=1,
        domain="data_quality",
        severity="error",
        code="missing_cost_blocks_profit",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Missing cost blocks profit",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "vendorCode": "VC-1", "affectedRevenue": "12000"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    core = CoreSKU(id=10, account_id=1, dedupe_key="core-10", nm_id=1001, vendor_code="VC-1", barcode="B-1", is_active=True, status="active")
    mart = MartSKUDaily(
        id=20,
        account_id=1,
        dedupe_key="mart-20",
        stat_date=date(2026, 7, 2),
        sku_id=10,
        nm_id=1001,
        vendor_code="VC-1",
        barcode="B-1",
        final_revenue=Decimal("12000.00"),
        has_manual_cost=False,
        has_real_manual_cost=False,
    )

    ctx = await service.resolution_context(_FakeSession([core], [mart], issue=issue), issue_id=105)

    assert ctx.issue_id == 105
    assert ctx.problem_instance_id is None
    assert ctx.issue_code == "missing_cost_blocks_profit"
    assert ctx.owner_type == "seller"
    assert ctx.fixability == "fix_in_platform"
    assert ctx.issue_nature == "data_blocker"
    assert ctx.can_user_fix_inside_platform is True
    assert ctx.fix_component_type == "cost_inline_editor"
    assert ctx.required_inputs
    assert ctx.preview_available is True
    assert ctx.apply_available is True
    assert ctx.recheck_available is True
    assert ctx.suggested_fix_action["endpoint"] == "POST /api/v1/costs/inline-save"
    assert ctx.affected_rows[0]["source"] == "data_quality_issues"
    assert any(row["row_status"] == "needs_cost" for row in ctx.affected_rows)


@pytest.mark.asyncio
async def test_manual_cost_unresolved_sku_context_points_to_sku_mapping() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=106,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="manual_cost_unresolved_sku",
        entity_key="manual-cost:7",
        source_table="manual_costs",
        message="Unresolved manual cost SKU",
        sku_id=None,
        nm_id=1001,
        payload={"nmId": 1001, "vendorCode": "VC-1", "manualCostId": 7, "candidateSkuIds": [10]},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    core = CoreSKU(id=10, account_id=1, dedupe_key="core-10", nm_id=1001, vendor_code="VC-1", barcode="B-1", is_active=True, status="active")

    ctx = await service.resolution_context(_FakeSession([core], issue=issue), issue_id=106)

    assert ctx.owner_type == "operator"
    assert ctx.fixability == "fix_in_platform"
    assert ctx.issue_nature == "data_blocker"
    assert ctx.can_user_fix_inside_platform is True
    assert ctx.fix_component_type == "sku_mapping"
    assert ctx.apply_available is True
    assert ctx.suggested_fix_action["type"] == "map_sku"
    assert any(row["row_status"] == "needs_mapping" for row in ctx.affected_rows)
    assert all(row["suggested_fix"]["action_type"] == "map_sku" for row in ctx.affected_rows)


@pytest.mark.asyncio
async def test_expense_unclassified_context_points_to_expense_classification() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=107,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="expense_unclassified",
        entity_key="expense:unknown_operation",
        source_table="mart_expense_daily",
        message="Expense unclassified",
        nm_id=1001,
        payload={"nmId": 1001, "sourceField": "unknown_operation", "affectedAmount": "450.50"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    expense = MartExpenseDaily(
        id=5,
        account_id=1,
        dedupe_key="expense-5",
        stat_date=date(2026, 7, 2),
        rrd_id=77,
        nm_id=1001,
        barcode="B-1",
        expense_category="unknown",
        expense_source="finance_report",
        amount=Decimal("450.50"),
        amount_sign="expense",
        currency="RUB",
        source_field="unknown_operation",
        seller_oper_name="Unknown WB operation",
    )

    ctx = await service.resolution_context(_FakeSession([expense], issue=issue), issue_id=107)

    assert ctx.owner_type == "operator"
    assert ctx.fixability == "fix_in_platform"
    assert ctx.issue_nature == "data_blocker"
    assert ctx.can_user_fix_inside_platform is True
    assert ctx.fix_component_type == "expense_classification"
    assert ctx.apply_available is True
    assert ctx.suggested_fix_action["type"] == "classify_expense"
    assert any(row["source"] == "mart_expense_daily.unclassified_source" for row in ctx.affected_rows)
    assert all(row["row_status"] == "needs_classification" for row in ctx.affected_rows)


@pytest.mark.asyncio
async def test_finance_reconciliation_mismatch_context_cannot_be_manually_edited() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=108,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="finance_reconciliation_mismatch",
        entity_key=None,
        source_table="mart_finance_reconciliation",
        message="Mismatch",
        nm_id=1001,
        payload={"nmId": 1001, "revenueDelta": "500"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )
    rec = MartFinanceReconciliation(
        id=1,
        account_id=1,
        dedupe_key="rec-1",
        stat_date=date(2026, 7, 1),
        nm_id=1001,
        sale_rows=1,
        finance_rows=1,
        sale_revenue=Decimal("2000"),
        finance_revenue=Decimal("1500"),
        revenue_delta=Decimal("500"),
        for_pay_delta=Decimal("400"),
        status="mismatch",
    )

    ctx = await service.resolution_context(_FakeSession([rec], issue=issue), issue_id=108)

    assert ctx.owner_type == "admin"
    assert ctx.fixability == "admin_only"
    assert ctx.issue_nature == "finance_investigation"
    assert ctx.can_user_fix_inside_platform is False
    assert ctx.is_manual_edit_allowed is False
    assert ctx.fix_component_type == "admin_investigation"
    assert ctx.apply_available is False
    assert ctx.disabled_reason == "finance_reconciliation_mismatch_requires_system_or_admin_investigation"
    assert "manual_edit_wb_finance_facts" in ctx.suggested_fix_action["forbidden"]
    assert any(row["row_status"] == "admin_investigation" for row in ctx.affected_rows)


@pytest.mark.asyncio
async def test_price_jump_context_has_no_auto_price_change() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=109,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="price_jump",
        entity_key="nm:1001",
        source_table="wb_price_snapshots",
        message="Price jump",
        nm_id=1001,
        payload={"nmId": 1001, "currentPrice": "1500", "previousPrice": "1000", "changePercent": "50"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )

    ctx = await service.resolution_context(_FakeSession(issue=issue), issue_id=109)

    assert ctx.owner_type == "business"
    assert ctx.fixability == "business_decision"
    assert ctx.issue_nature == "business_signal"
    assert ctx.can_user_fix_inside_platform is False
    assert ctx.preview_available is True
    assert ctx.apply_available is False
    assert ctx.disabled_reason == "price_jump_check_only_no_auto_price_change"
    assert ctx.suggested_fix_action["allowed"] is False
    assert all(row["suggested_fix"].get("auto_price_change") is False for row in ctx.affected_rows)

    with pytest.raises(HTTPException) as exc:
        await service.apply_guided_fix(
            _FakeSession(issue=issue),
            issue_id=109,
            request=GuidedFixActionRequest(action_type="review_price", inputs={"reason": "checked"}),
            user_id=1,
        )
    assert exc.value.status_code == 400
    assert "check-only" in str(exc.value.detail)


def test_ads_allocation_without_mapping_ui_is_admin_system_check() -> None:
    definition = DataQualityService.guided_fix_definition_for_code("ads_not_allocated_to_profitability")

    assert definition.owner_type == "admin"
    assert definition.fixability == "admin_only"
    assert definition.issue_nature == "system_check"
    assert definition.can_user_fix_inside_platform is False
    assert definition.is_manual_edit_allowed is False
    assert definition.primary_action_code == "open_money_ads_detail"
    assert definition.primary_action_label == "Открыть рекламу в Деньгах"


@pytest.mark.asyncio
async def test_stock_without_sales_is_business_signal_not_data_blocker() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=110,
        account_id=1,
        domain="data_quality",
        severity="info",
        code="stock_without_sales",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Stock without sales",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "closingStockQty": "12"},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )

    ctx = await service.resolution_context(_FakeSession(issue=issue), issue_id=110)

    assert ctx.owner_type == "business"
    assert ctx.fixability == "business_decision"
    assert ctx.issue_nature == "business_signal"
    assert ctx.can_user_fix_inside_platform is False
    assert ctx.apply_available is False
    assert ctx.issue.money_trust.impact_kind != "data_blocker"


@pytest.mark.asyncio
async def test_sales_without_stock_requires_stock_sync_not_manual_fix() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=111,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="sales_without_stock",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Sales without stock",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "finalSalesQty": 3},
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )

    ctx = await service.resolution_context(_FakeSession(issue=issue), issue_id=111)

    assert ctx.owner_type == "system"
    assert ctx.fixability == "sync_required"
    assert ctx.issue_nature == "sync_waiting"
    assert ctx.primary_action_code == "trigger_stock_sync"
    assert ctx.can_user_fix_inside_platform is False
    assert ctx.is_manual_edit_allowed is False
    assert "Нужна синхронизация остатков" in ctx.seller_explanation


@pytest.mark.asyncio
async def test_fresh_order_without_sale_or_return_waits_for_next_sync() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=112,
        account_id=1,
        domain="data_quality",
        severity="info",
        code="order_without_sale_or_return",
        entity_key="srid-fresh",
        source_table="mart_finance_reconciliation",
        message="Order without followup",
        nm_id=1001,
        payload={"nmId": 1001, "ageBucket": "pending", "ageDays": 1, "statDate": "2026-07-11"},
        detected_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )

    ctx = await service.resolution_context(_FakeSession(issue=issue), issue_id=112)

    assert ctx.owner_type == "waiting"
    assert ctx.fixability == "wait"
    assert ctx.issue_nature == "sync_waiting"
    assert ctx.primary_action_code == "wait_next_sync"
    assert ctx.can_user_fix_inside_platform is False


@pytest.mark.asyncio
async def test_old_order_without_sale_or_return_becomes_finance_investigation() -> None:
    service = DataQualityService()
    issue = DataQualityIssue(
        id=113,
        account_id=1,
        domain="data_quality",
        severity="error",
        code="order_without_sale_or_return",
        entity_key="srid-old",
        source_table="mart_finance_reconciliation",
        message="Order without followup",
        nm_id=1001,
        payload={"nmId": 1001, "ageBucket": "error", "ageDays": 14, "statDate": "2026-06-28"},
        detected_at=datetime(2026, 7, 12, tzinfo=timezone.utc),
    )

    ctx = await service.resolution_context(_FakeSession(issue=issue), issue_id=113)

    assert ctx.owner_type == "admin"
    assert ctx.fixability == "admin_only"
    assert ctx.issue_nature == "finance_investigation"
    assert ctx.primary_action_code == "open_reconciliation"
    assert ctx.can_user_fix_inside_platform is False


def test_ads_allocation_current_target_and_unallocated_amount_are_explicit() -> None:
    service = MoneyManagementService()
    item = DataBlockerRead(
        code="ads_not_allocated_to_profitability",
        priority="high",
        title="Ads allocation",
        affected_sku_count=1,
        affected_revenue=1000,
        affected_amount=50,
        current_value=95,
        required_value=100,
        unit="процент аллокации рекламы",
        business_impact="impact",
        how_to_fix=[],
    )

    service._attach_data_blocker_calculation(
        item,
        state=SimpleNamespace(health=SimpleNamespace(issue_buckets=[])),
        revenue_total=Decimal("1000"),
        ads_metrics={
            "ads_source_spend": Decimal("1000"),
            "mart_ads_allocated_spend": Decimal("950"),
            "ads_allocated_spend": Decimal("950"),
            "ads_unallocated_spend": Decimal("50"),
            "ads_overallocated_spend": Decimal("0"),
            "ads_allocation_percent_raw": Decimal("95"),
        },
    )

    labels = {row["label"]: row for row in item.calculation_inputs}
    assert item.current_value == 95
    assert item.required_value == 100
    assert labels["Текущая аллокация"]["value"] == 95.0
    assert labels["Целевая аллокация"]["value"] == 100
    assert labels["Не распределено"]["value"] == 50.0


@pytest.mark.asyncio
async def test_data_fix_recheck_creates_linked_problem_history_and_result_event() -> None:
    sync_session, session = _problem_result_session()
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    issue = DataQualityIssue(
        id=110,
        account_id=1,
        domain="data_quality",
        severity="error",
        code="missing_manual_cost",
        entity_key="sku:10",
        source_table="mart_sku_daily",
        message="Missing cost",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "vendorCode": "VC-1"},
        detected_at=now,
    )
    definition = ProblemDefinition(
        id=1,
        problem_code="missing_cost_blocks_profit",
        source_module="data_quality",
        category="data_quality",
        entity_type="product",
        title_template="Missing cost",
        description_template="Missing cost",
        recommendation_template="Upload cost",
        impact_type_default="data_blocker",
        trust_state_default="blocked",
        severity_default="critical",
        allowed_actions_json=["upload_cost", "recheck"],
        status="active",
    )
    rule = ProblemRuleVersion(
        id=1,
        problem_definition_id=1,
        version=1,
        status="active",
        evaluation_grain="product_period",
        condition_json={},
        impact_formula_json={},
        severity_formula_json={},
        confidence_formula_json={},
        dedup_key_template="{account_id}:{problem_code}:sku:{sku_id}",
        recheck_rule_json={"human": "Re-check cost"},
        evidence_template_json={},
        published_at=now,
    )
    problem = ProblemInstance(
        id=1,
        account_id=1,
        problem_code="missing_cost_blocks_profit",
        problem_definition_id=1,
        rule_version_id=1,
        source_module="data_quality",
        entity_type="product",
        entity_id="1001",
        nm_id=1001,
        vendor_code="VC-1",
        dedup_key="1:missing_cost_blocks_profit:sku:10",
        title="Missing cost",
        explanation="Missing cost",
        recommendation="Upload cost",
        severity="critical",
        status="blocked",
        impact_type="data_blocker",
        trust_state="blocked",
        confidence="blocked",
        evidence_ledger_json={},
        calculation_snapshot_json={},
        first_seen_at=now,
        last_seen_at=now,
    )
    sync_session.add_all([issue, definition, rule, problem])
    sync_session.flush()

    service = DataQualityService()

    async def _linked_problem(_session, _issue):
        return problem

    service._sync_dynamic_problem_instance = _linked_problem  # type: ignore[method-assign]

    await service._record_linked_problem_recheck_requested(
        session,
        issue,
        user_id=42,
        inputs={"source": "test"},
        comment="Re-check from Data Fix",
    )

    history_events = list(sync_session.execute(select(ProblemInstanceHistory).order_by(ProblemInstanceHistory.id)).scalars())
    assert [event.event_type for event in history_events] == ["recheck_requested"]
    assert history_events[0].actor_user_id == 42
    result_events = list(sync_session.execute(select(ResultEvent).order_by(ResultEvent.id)).scalars())
    assert [event.event_type for event in result_events] == ["before_snapshot", "recheck_result"]
    assert result_events[-1].problem_instance_id == problem.id
    assert result_events[-1].payload_json["recheck_payload"]["source"] == "data_fix"
    assert result_events[-1].payload_json["saved_money_claimed"] is False


@pytest.mark.asyncio
async def test_data_fix_recheck_resolves_missing_cost_after_cost_appears() -> None:
    sync_session, session = _problem_result_session()
    now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    issue = DataQualityIssue(
        id=111,
        account_id=1,
        domain="data_quality",
        severity="error",
        code="missing_manual_cost",
        entity_key="nm:1001|vendor:VC-1",
        source_table="mart_sku_daily",
        message="Missing cost",
        sku_id=10,
        nm_id=1001,
        payload={"nmId": 1001, "vendorCode": "VC-1"},
        detected_at=now,
    )
    definition = ProblemDefinition(
        id=11,
        problem_code="missing_cost_blocks_profit",
        source_module="data_quality",
        category="data_quality",
        entity_type="product",
        title_template="Missing cost",
        description_template="Missing cost",
        recommendation_template="Upload cost",
        impact_type_default="data_blocker",
        trust_state_default="blocked",
        severity_default="critical",
        allowed_actions_json=["upload_cost", "recheck"],
        status="active",
    )
    rule = ProblemRuleVersion(
        id=11,
        problem_definition_id=11,
        version=1,
        status="active",
        evaluation_grain="product_period",
        condition_json={},
        impact_formula_json={},
        severity_formula_json={},
        confidence_formula_json={},
        dedup_key_template="{account_id}:{problem_code}:sku:{sku_id}",
        recheck_rule_json={"human": "Re-check cost"},
        evidence_template_json={},
        published_at=now,
    )
    problem = ProblemInstance(
        id=11,
        account_id=1,
        problem_code="missing_cost_blocks_profit",
        problem_definition_id=11,
        rule_version_id=11,
        source_module="data_quality",
        entity_type="product",
        entity_id="1001",
        nm_id=1001,
        vendor_code="VC-1",
        dedup_key="1:missing_cost_blocks_profit:missing_manual_cost:nm:1001|vendor:VC-1",
        title="Missing cost",
        explanation="Missing cost",
        recommendation="Upload cost",
        severity="critical",
        status="blocked",
        impact_type="data_blocker",
        trust_state="blocked",
        confidence="blocked",
        evidence_ledger_json={},
        calculation_snapshot_json={"action_center": {"review_status": "blocked"}},
        first_seen_at=now,
        last_seen_at=now,
    )
    sync_session.add_all([issue, definition, rule, problem])
    sync_session.flush()

    service = DataQualityService()

    async def _rows(_session, row_issue, **_kwargs):
        if row_issue.resolved_at is not None:
            return [], 0
        return [{"source": "mart_sku_daily", "nm_id": 1001, "missing_or_invalid_value": "cost_price"}], 1

    async def _run_checks(_session, *, account_id=None):
        issue.resolved_at = now
        service._refresh_issue_final_blocker_state(issue)
        return {"checked_accounts": 1, "opened_count": 0, "updated_count": 0, "resolved_count": 1, "active_count": 0}

    async def _linked_problem(_session, row_issue):
        if row_issue.resolved_at is not None:
            problem.status = "resolved"
            problem.resolved_at = row_issue.resolved_at
        else:
            problem.status = "blocked"
            problem.resolved_at = None
        return problem

    service._affected_rows_for_issue = _rows  # type: ignore[method-assign]
    service.run_checks = _run_checks  # type: ignore[method-assign]
    service._sync_dynamic_problem_instance = _linked_problem  # type: ignore[method-assign]

    response = await service.recheck_issue(session, issue_id=111, user_id=42)

    assert response.status == "completed"
    assert response.problem_instance_id == problem.id
    assert response.result_status == "improved"
    assert response.affected_rows_count == 1
    assert response.resolved_rows_count == 1
    assert response.still_missing_rows_count == 0
    assert response.action_center_update["new_status"] == "resolved"
    assert response.action_center_update["result_badge"] == "resolved_after_recheck"
    sync_session.refresh(problem)
    assert problem.status == "resolved"
    assert problem.calculation_snapshot_json["action_center"]["review_status"] == "done"
    event = sync_session.get(ResultEvent, response.result_event_id)
    assert event is not None
    assert event.event_type == "recheck_result"
    assert event.source_module == "data_quality"
    assert event.problem_instance_id == problem.id
    assert event.payload_json["saved_money_claimed"] is False
    history_events = [row.event_type for row in sync_session.execute(select(ProblemInstanceHistory)).scalars()]
    assert "recheck_completed" in history_events


@pytest.mark.asyncio
async def test_data_fix_recheck_remains_blocked_when_data_still_missing() -> None:
    sync_session, session = _problem_result_session()
    now = datetime(2026, 7, 12, tzinfo=timezone.utc)
    issue = DataQualityIssue(
        id=112,
        account_id=1,
        domain="data_quality",
        severity="error",
        code="missing_manual_cost",
        entity_key="nm:1002|vendor:VC-2",
        source_table="mart_sku_daily",
        message="Missing cost",
        sku_id=20,
        nm_id=1002,
        payload={"nmId": 1002, "vendorCode": "VC-2"},
        detected_at=now,
    )
    definition = ProblemDefinition(
        id=12,
        problem_code="missing_cost_blocks_profit",
        source_module="data_quality",
        category="data_quality",
        entity_type="product",
        title_template="Missing cost",
        description_template="Missing cost",
        recommendation_template="Upload cost",
        impact_type_default="data_blocker",
        trust_state_default="blocked",
        severity_default="critical",
        allowed_actions_json=["upload_cost", "recheck"],
        status="active",
    )
    rule = ProblemRuleVersion(
        id=12,
        problem_definition_id=12,
        version=1,
        status="active",
        evaluation_grain="product_period",
        condition_json={},
        impact_formula_json={},
        severity_formula_json={},
        confidence_formula_json={},
        dedup_key_template="{account_id}:{problem_code}:sku:{sku_id}",
        recheck_rule_json={"human": "Re-check cost"},
        evidence_template_json={},
        published_at=now,
    )
    problem = ProblemInstance(
        id=12,
        account_id=1,
        problem_code="missing_cost_blocks_profit",
        problem_definition_id=12,
        rule_version_id=12,
        source_module="data_quality",
        entity_type="product",
        entity_id="1002",
        nm_id=1002,
        vendor_code="VC-2",
        dedup_key="1:missing_cost_blocks_profit:missing_manual_cost:nm:1002|vendor:VC-2",
        title="Missing cost",
        explanation="Missing cost",
        recommendation="Upload cost",
        severity="critical",
        status="blocked",
        impact_type="data_blocker",
        trust_state="blocked",
        confidence="blocked",
        evidence_ledger_json={},
        calculation_snapshot_json={"action_center": {"review_status": "blocked"}},
        first_seen_at=now,
        last_seen_at=now,
    )
    sync_session.add_all([issue, definition, rule, problem])
    sync_session.flush()

    service = DataQualityService()

    async def _rows(_session, row_issue, **_kwargs):
        return [{"source": "mart_sku_daily", "nm_id": 1002, "missing_or_invalid_value": "cost_price"}], 1

    async def _run_checks(_session, *, account_id=None):
        return {"checked_accounts": 1, "opened_count": 0, "updated_count": 1, "resolved_count": 0, "active_count": 1}

    async def _linked_problem(_session, _row_issue):
        problem.status = "blocked"
        problem.resolved_at = None
        return problem

    service._affected_rows_for_issue = _rows  # type: ignore[method-assign]
    service.run_checks = _run_checks  # type: ignore[method-assign]
    service._sync_dynamic_problem_instance = _linked_problem  # type: ignore[method-assign]

    response = await service.recheck_issue(session, issue_id=112, user_id=42)

    assert response.status == "completed"
    assert response.result_status == "neutral"
    assert response.resolved_rows_count == 0
    assert response.still_missing_rows_count == 1
    assert response.action_center_update["new_status"] == "blocked"
    assert response.action_center_update["result_badge"] == "still_blocked_after_recheck"
    sync_session.refresh(problem)
    assert problem.status == "blocked"
    assert problem.calculation_snapshot_json["action_center"]["review_status"] == "blocked"
    event = sync_session.get(ResultEvent, response.result_event_id)
    assert event is not None
    assert event.payload_json["still_missing_rows_count"] == 1
