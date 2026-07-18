from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger, create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.data_quality import DataQualityIssue
from app.models.problem_engine import ProblemDefinition, ProblemInstance, ProblemInstanceHistory, ProblemRuleVersion
from app.services.data_quality import DataQualityService
from app.services.problem_engine.data_fix_bridge import DataFixProblemBridge


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

    async def get(self, model, ident):
        return self._session.get(model, ident)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()


def _session() -> tuple[Session, _AsyncSessionAdapter]:
    engine = create_engine("sqlite:///:memory:")
    for table in (
        WBAccount.__table__,
        DataQualityIssue.__table__,
        ProblemDefinition.__table__,
        ProblemRuleVersion.__table__,
        ProblemInstance.__table__,
        ProblemInstanceHistory.__table__,
    ):
        table.create(engine)
    sync_session = Session(engine)
    sync_session.add(WBAccount(id=1, name="Test account"))
    sync_session.flush()
    return sync_session, _AsyncSessionAdapter(sync_session)


def _issue(
    *,
    code: str,
    severity: str = "warning",
    payload: dict | None = None,
    source_table: str = "data_quality_issues",
) -> DataQualityIssue:
    return DataQualityIssue(
        account_id=1,
        domain="data_quality",
        severity=severity,
        code=code,
        entity_key=f"{code}:1001",
        entity_type="product",
        entity_id=1001,
        sku_id=10,
        nm_id=1001,
        source_table=source_table,
        message=f"{code} issue",
        payload={"nmId": 1001, "vendorCode": "VC-1", **(payload or {})},
        detected_at=datetime(2026, 7, 6, tzinfo=timezone.utc),
    )


async def _sync(sync_session: Session, async_session: _AsyncSessionAdapter, issue: DataQualityIssue) -> ProblemInstance:
    sync_session.add(issue)
    sync_session.flush()
    instance = await DataFixProblemBridge().sync_issue(
        async_session,
        issue,
        guided_definition=DataQualityService.guided_fix_definition_for_code(issue.code),
    )
    assert instance is not None
    return instance


@pytest.mark.asyncio
async def test_missing_cost_issue_maps_to_missing_cost_blocks_profit_problem() -> None:
    sync_session, async_session = _session()
    issue = _issue(
        code="missing_manual_cost",
        severity="error",
        payload={"affectedRevenue": "12000.00"},
        source_table="mart_sku_daily",
    )

    instance = await _sync(sync_session, async_session, issue)

    assert instance.problem_code == "missing_cost_blocks_profit"
    assert instance.status == "blocked"
    assert instance.impact_type == "data_blocker"
    assert instance.money_impact_amount == Decimal("12000.00")
    assert instance.evidence_ledger_json["formula_code"] == "missing_cost_blocks_profit.data_fix_bridge.v1"
    assert instance.evidence_ledger_json["data_fix"]["owner_type"] == "seller"
    assert instance.evidence_ledger_json["data_fix"]["fixability"] == "fix_in_platform"
    assert instance.evidence_ledger_json["data_fix"]["issue_nature"] == "data_blocker"
    assert instance.evidence_ledger_json["data_fix"]["can_user_fix_inside_platform"] is True
    assert instance.evidence_ledger_json["data_fix"]["is_manual_edit_allowed"] is True
    assert instance.evidence_ledger_json["data_fix"]["fix_component_type"] == "cost_inline_editor"


@pytest.mark.asyncio
async def test_unmatched_sku_issue_maps_to_sku_mapping_problem() -> None:
    sync_session, async_session = _session()
    issue = _issue(code="unmatched_sku", payload={"candidateSkuIds": [10, 11]}, source_table="wb_sales")

    instance = await _sync(sync_session, async_session, issue)

    assert instance.problem_code == "unmatched_sku"
    assert instance.status == "blocked"
    assert instance.evidence_ledger_json["data_fix"]["owner_type"] == "operator"
    assert instance.evidence_ledger_json["data_fix"]["fixability"] == "fix_in_platform"
    assert instance.evidence_ledger_json["data_fix"]["fix_component_type"] == "sku_mapping"
    assert "manual" not in " ".join(instance.evidence_ledger_json["calculation_warnings"]).lower()


@pytest.mark.asyncio
async def test_unclassified_expense_issue_maps_to_expense_classification_problem() -> None:
    sync_session, async_session = _session()
    issue = _issue(
        code="expense_unclassified",
        payload={"affectedAmount": "450.50", "sourceField": "unknown_operation"},
        source_table="mart_expense_daily",
    )

    instance = await _sync(sync_session, async_session, issue)

    assert instance.problem_code == "expense_unclassified"
    assert instance.impact_type == "data_blocker"
    assert instance.money_impact_amount == Decimal("450.50")
    assert instance.evidence_ledger_json["data_fix"]["fix_component_type"] == "expense_classification"
    assert instance.evidence_ledger_json["data_fix"]["primary_action_code"] == "classify_expense"
    assert instance.evidence_ledger_json["next_fix_action"]["screen_path"] == "/data-fix?code=expense_unclassified"


@pytest.mark.asyncio
async def test_finance_reconciliation_mismatch_is_hidden_from_dynamic_problem_instances() -> None:
    sync_session, async_session = _session()
    issue = _issue(
        code="finance_reconciliation_mismatch",
        payload={"revenueDelta": "500.00"},
        source_table="mart_finance_reconciliation",
    )
    sync_session.add(issue)
    sync_session.flush()

    instance = await DataFixProblemBridge().sync_issue(
        async_session,
        issue,
        guided_definition=DataQualityService.guided_fix_definition_for_code(issue.code),
    )

    assert instance is None
    assert sync_session.execute(select(ProblemInstance)).scalars().all() == []
