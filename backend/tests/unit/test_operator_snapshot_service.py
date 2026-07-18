from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from sqlalchemy.dialects import postgresql

from app.core.pagination import Page
from app.core.time import utcnow
from app.schemas.control_tower import PurchasePlanPage
from app.schemas.dashboard import DashboardDataHealth
from app.schemas.data_quality import DataQualityIssueRead, DataQualityIssueSummaryResponse
from app.schemas.marts import MartBusinessDailyRead
from app.services.operator_snapshots import OperatorEndpointSnapshotService, OperatorSnapshotSpec


@pytest.mark.asyncio
async def test_data_health_uses_db_snapshot_before_recomputing(monkeypatch) -> None:
    service = OperatorEndpointSnapshotService()
    snapshot = DashboardDataHealth.model_construct(account_id=1)
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=snapshot))
    compute = AsyncMock()
    monkeypatch.setattr(service.dashboard, "data_health", compute)

    result = await service.data_health(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result is snapshot
    assert compute.await_count == 0


@pytest.mark.asyncio
async def test_dq_issue_summary_computes_and_saves_snapshot_on_cache_miss(monkeypatch) -> None:
    service = OperatorEndpointSnapshotService()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    summary = DataQualityIssueSummaryResponse.model_construct(financial_final_blockers_total=8)
    compute = AsyncMock(return_value=summary)
    monkeypatch.setattr(service, "_build_dq_issue_summary", compute)

    result = await service.dq_issue_summary(
        None,  # type: ignore[arg-type]
        account_id=1,
    )

    assert result is summary
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


@pytest.mark.asyncio
async def test_dq_issues_computes_and_saves_snapshot_on_cache_miss(monkeypatch) -> None:
    service = OperatorEndpointSnapshotService()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    page = Page[DataQualityIssueRead].model_construct(total=0, limit=10, offset=0, items=[], cache_status="miss")
    compute = AsyncMock(return_value=page)
    monkeypatch.setattr(service.data_quality, "list_issues", compute)

    result = await service.dq_issues(
        None,  # type: ignore[arg-type]
        account_id=1,
        only_open=True,
        limit=10,
        offset=0,
    )

    assert result is page
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


@pytest.mark.asyncio
async def test_business_daily_reuses_runtime_snapshot_cache(monkeypatch) -> None:
    service = OperatorEndpointSnapshotService()
    service._response_cache.clear()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    page = Page[MartBusinessDailyRead].model_construct(
        total=0,
        limit=200,
        offset=0,
        items=[],
        cache_status="miss",
    )
    compute = AsyncMock(return_value=page)
    monkeypatch.setattr(service.marts, "list_business_daily", compute)

    first = await service.business_daily(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=200,
        offset=0,
    )
    second = await service.business_daily(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=200,
        offset=0,
    )

    assert first is page
    assert second is page
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


class _DummySnapshotResponse(BaseModel):
    value: int


def test_operator_snapshot_spec_sort_key_handles_missing_dates() -> None:
    service = OperatorEndpointSnapshotService()
    specs = [
        OperatorSnapshotSpec("dashboard", "dashboard_owner", 1, None, None, {}),
        OperatorSnapshotSpec("dashboard", "dashboard_owner", 1, date(2026, 5, 1), date(2026, 5, 31), {}),
    ]

    assert len(sorted(specs, key=service._spec_sort_key)) == 2


@pytest.mark.asyncio
async def test_operator_save_snapshot_uses_postgres_upsert_without_flush() -> None:
    service = OperatorEndpointSnapshotService()
    session = AsyncMock()
    response = _DummySnapshotResponse(value=1)

    await service._save_snapshot(
        session,
        namespace="dashboard",
        endpoint_key="dashboard_owner",
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        params={"limit": 10, "offset": 0},
        response=response,
        auto_commit=True,
    )

    assert session.execute.await_count == 2
    assert session.commit.await_count == 1
    assert session.flush.await_count == 0
    stmt = session.execute.await_args_list[-1].args[0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled


@pytest.mark.asyncio
async def test_operator_load_snapshot_backfills_purchase_plan_summary_from_old_payload() -> None:
    service = OperatorEndpointSnapshotService()
    now = utcnow()
    session = AsyncMock()
    row = SimpleNamespace(
        payload={
            "total": 1,
            "limit": 100,
            "offset": 0,
            "items": [],
            "computed_at": None,
            "cache_status": "db_snapshot_hit",
            "data_version_hash": "purchase-old-hash",
        },
        computed_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    execute_result = SimpleNamespace(scalar_one_or_none=lambda: row)
    session.execute.return_value = execute_result

    snapshot = await service._load_snapshot(
        session,  # type: ignore[arg-type]
        namespace="control_tower",
        endpoint_key="inventory_purchase_plan",
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        params={"limit": 100, "offset": 0},
        model_cls=PurchasePlanPage,
    )

    assert snapshot is not None
    assert snapshot.summary.total_count == 0
    assert snapshot.summary.total_required_cash == 0.0
    assert snapshot.summary.wait_data_reason_counts.finance == 0
