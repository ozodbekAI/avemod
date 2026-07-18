from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.models.data_quality import DataQualityIssue
from app.models.manual_costs import ManualCost
from app.models.operator import UnifiedAction
from app.schemas.portal import PortalActionSourceUpdateRequest
from app.services.portal import PortalService


class _EmptyExecuteResult:
    def scalars(self):
        return self

    def __iter__(self):
        return iter(())


class _FakeSession:
    def __init__(self, *, dq_issue: DataQualityIssue | None = None, cost: ManualCost | None = None) -> None:
        self.dq_issue = dq_issue
        self.cost = cost
        self.added = []
        self.committed = False
        self._next_id = 900

    async def get(self, model, key):
        if model is DataQualityIssue and self.dq_issue is not None and int(key) == int(self.dq_issue.id):
            return self.dq_issue
        if model is ManualCost and self.cost is not None and int(key) == int(self.cost.id):
            return self.cost
        return None

    async def execute(self, _stmt):
        return _EmptyExecuteResult()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if isinstance(obj, UnifiedAction) and obj.id is None:
                obj.id = self._next_id
                self._next_id += 1

    async def refresh(self, _obj):
        return None

    async def commit(self):
        self.committed = True


def _dq_issue() -> DataQualityIssue:
    return DataQualityIssue(
        id=30,
        account_id=1,
        domain="costs",
        severity="critical",
        code="missing_manual_cost",
        message="Missing manual cost",
        payload={},
        classification_status="detected",
        effective_financial_final_blocker=True,
        detected_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
    )


def _manual_cost() -> ManualCost:
    return ManualCost(
        id=50,
        account_id=1,
        dedupe_key="cost-50",
        sku_id=100,
        vendor_code="VC-1",
        nm_id=1001,
        barcode="123",
        unit_cost=Decimal("100.00"),
        cost_price=Decimal("100.00"),
        seller_other_expense=Decimal("0"),
        packaging_cost=Decimal("0"),
        inbound_logistics_cost=Decimal("0"),
        is_placeholder=False,
        is_business_trusted=False,
        is_ambiguous=False,
    )


@pytest.mark.asyncio
async def test_action_center_update_marks_data_quality_source_issue() -> None:
    service = PortalService()
    issue = _dq_issue()
    session = _FakeSession(dq_issue=issue)

    result = await service.update_action_by_source(
        session,  # type: ignore[arg-type]
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="data_quality",
            source_id="30",
            status="ignored",
            comment="Owner accepted the exception",
        ),
        user_id=7,
    )

    assert issue.classification_status == "ignored_with_reason"
    assert issue.classification_reason == "Owner accepted the exception"
    assert issue.classified_by_user_id == 7
    assert issue.financial_final_blocker_override is False
    assert result.source_sync_state == "source_updated"
    assert result.payload["source_update_targets"] == ["data_quality"]
    assert session.committed is True


@pytest.mark.asyncio
async def test_action_center_update_marks_manual_cost_source_state() -> None:
    service = PortalService()
    cost = _manual_cost()
    session = _FakeSession(cost=cost)

    result = await service.update_action_by_source(
        session,  # type: ignore[arg-type]
        payload=PortalActionSourceUpdateRequest(
            account_id=1,
            source_module="costs",
            source_id="50",
            status="done",
            comment="Checked by owner",
        ),
        user_id=7,
    )

    assert cost.is_business_trusted is True
    assert cost.cost_source == "action_center_reviewed_manual"
    assert "Action Center status: done" in (cost.comment or "")
    assert "Checked by owner" in (cost.comment or "")
    assert result.source_sync_state == "source_updated"
    assert result.payload["source_update_targets"] == ["costs"]
    assert session.committed is True
