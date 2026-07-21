from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from sqlalchemy.dialects import postgresql

from app.core.pagination import Page
from app.core.time import utcnow
from app.schemas.control_tower import (
    OwnerAdsDailyPoint,
    OwnerAdsSummary,
    OwnerDashboardRead,
    OwnerWbDailyPoint,
    OwnerWbSummary,
    PurchasePlanPage,
)
from app.schemas.dashboard import DashboardDataHealth
from app.schemas.data_quality import (
    DataQualityIssueRead,
    DataQualityIssueSummaryResponse,
)
from app.schemas.marts import MartBusinessDailyRead, MartStockDailyRead
from app.services.operator_snapshots import (
    OperatorEndpointSnapshotService,
    OperatorSnapshotSpec,
)


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
async def test_dq_issue_summary_computes_and_saves_snapshot_on_cache_miss(
    monkeypatch,
) -> None:
    service = OperatorEndpointSnapshotService()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    summary = DataQualityIssueSummaryResponse.model_construct(
        financial_final_blockers_total=8
    )
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
    page = Page[DataQualityIssueRead].model_construct(
        total=0, limit=10, offset=0, items=[], cache_status="miss"
    )
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


@pytest.mark.asyncio
async def test_stock_daily_computes_and_saves_snapshot_on_cache_miss(
    monkeypatch,
) -> None:
    service = OperatorEndpointSnapshotService()
    service._response_cache.clear()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    page = Page[MartStockDailyRead].model_construct(
        total=0,
        limit=50,
        offset=0,
        items=[],
        cache_status="miss",
    )
    compute = AsyncMock(return_value=page)
    monkeypatch.setattr(service.marts, "list_stock_daily", compute)

    result = await service.stock_daily(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )

    assert result is page
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


@pytest.mark.asyncio
async def test_refresh_purchase_plan_keeps_filter_params(monkeypatch) -> None:
    service = OperatorEndpointSnapshotService()
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    page = PurchasePlanPage.model_construct(total=0, limit=100, offset=0, items=[])
    compute = AsyncMock(return_value=page)
    monkeypatch.setattr(service.control_tower, "list_purchase_plan", compute)

    await service._refresh_spec(
        None,  # type: ignore[arg-type]
        OperatorSnapshotSpec(
            "control_tower",
            "inventory_purchase_plan",
            1,
            date(2026, 5, 1),
            date(2026, 5, 31),
            {
                "group_by": "sku",
                "include_blocked": False,
                "sort_by": "required_cash",
                "sort_dir": "asc",
                "status_filter": "BUY",
                "search": "abc",
                "profit_filter": "profitable",
                "data_filter": "trusted",
                "stock_filter": "low",
                "limit": 25,
                "offset": 5,
            },
        ),
    )

    assert compute.await_count == 1
    kwargs = compute.await_args.kwargs
    assert kwargs["group_by"] == "sku"
    assert kwargs["include_blocked"] is False
    assert kwargs["status_filter"] == "BUY"
    assert kwargs["search"] == "abc"
    assert kwargs["profit_filter"] == "profitable"
    assert kwargs["data_filter"] == "trusted"
    assert kwargs["stock_filter"] == "low"


def test_operator_default_specs_match_primary_endpoint_params() -> None:
    service = OperatorEndpointSnapshotService()
    specs = service._default_specs_for_account(account_id=1)

    assert any(
        spec.endpoint_key == "control_skus"
        and spec.params.get("search") is None
        and spec.params.get("sku_status") is None
        and spec.params.get("limit") == 50
        for spec in specs
    )
    assert any(
        spec.endpoint_key == "marts_business_daily"
        and spec.params.get("snapshot_schema") == "ads_api_fallback_v1"
        and spec.params.get("limit") == 200
        for spec in specs
    )
    assert any(
        spec.endpoint_key == "marts_stock_daily"
        and spec.params.get("warehouse_name") is None
        and spec.params.get("limit") == 50
        for spec in specs
    )


class _DummySnapshotResponse(BaseModel):
    value: int
    computed_at: datetime | None = None
    cache_status: str = "miss"


@pytest.mark.asyncio
async def test_operator_load_snapshot_returns_expired_snapshot_as_stale() -> None:
    service = OperatorEndpointSnapshotService()
    now = utcnow()
    session = AsyncMock()
    row = SimpleNamespace(
        payload={"value": 1},
        computed_at=now - timedelta(days=2),
        expires_at=now - timedelta(days=1),
    )
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: row)

    snapshot = await service._load_snapshot(
        session,  # type: ignore[arg-type]
        namespace="dashboard",
        endpoint_key="dashboard_owner",
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        params={},
        model_cls=_DummySnapshotResponse,
    )

    assert snapshot is not None
    assert snapshot.value == 1
    assert snapshot.computed_at == row.computed_at
    assert snapshot.cache_status == "db_snapshot_stale"


@pytest.mark.asyncio
async def test_operator_load_snapshot_marks_snapshot_as_accessed(monkeypatch) -> None:
    service = OperatorEndpointSnapshotService()
    now = utcnow()
    touch = AsyncMock()
    monkeypatch.setattr(service, "_touch_snapshot_access", touch)
    session = AsyncMock()
    row = SimpleNamespace(
        id=42,
        payload={"value": 1},
        computed_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    session.execute.return_value = SimpleNamespace(scalar_one_or_none=lambda: row)

    snapshot = await service._load_snapshot(
        session,  # type: ignore[arg-type]
        namespace="dashboard",
        endpoint_key="dashboard_owner",
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        params={},
        model_cls=_DummySnapshotResponse,
    )

    assert snapshot is not None
    touch.assert_awaited_once_with(snapshot_id=42)


def test_operator_snapshot_spec_sort_key_handles_missing_dates() -> None:
    service = OperatorEndpointSnapshotService()
    specs = [
        OperatorSnapshotSpec("dashboard", "dashboard_owner", 1, None, None, {}),
        OperatorSnapshotSpec(
            "dashboard", "dashboard_owner", 1, date(2026, 5, 1), date(2026, 5, 31), {}
        ),
    ]

    assert len(sorted(specs, key=service._spec_sort_key)) == 2


def test_owner_dashboard_hash_uses_payload_version() -> None:
    service = OperatorEndpointSnapshotService()
    old_payload = {
        "endpoint_key": "dashboard_owner",
        "account_id": 1,
        "date_from": "2026-05-01",
        "date_to": "2026-05-31",
        "params": {},
    }
    old_hash = hashlib.sha1(
        json.dumps(
            old_payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8"),
        usedforsecurity=False,
    ).hexdigest()
    owner_hash = service._params_hash(
        endpoint_key="dashboard_owner",
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        params={},
    )

    assert service._payload_version("dashboard_owner") == 2
    assert service._payload_version("dashboard_data_health") == 1
    assert owner_hash != old_hash


@pytest.mark.asyncio
async def test_operator_invalidate_snapshots_marks_rows_not_ready() -> None:
    service = OperatorEndpointSnapshotService()
    session = AsyncMock()

    await service.invalidate_snapshots(session, account_id=1)

    stmt = session.execute.await_args.args[0]
    compiled = str(
        stmt.compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "snapshot_status" in compiled
    assert "invalidated" in compiled


@pytest.mark.asyncio
async def test_owner_dashboard_recomputes_snapshot_without_dense_daily(
    monkeypatch,
) -> None:
    service = OperatorEndpointSnapshotService()
    service._response_cache.clear()
    invalid_snapshot = OwnerDashboardRead.model_construct(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        wb_summary=OwnerWbSummary.model_construct(daily=[]),
        ads_summary=OwnerAdsSummary.model_construct(daily=[]),
    )
    valid_snapshot = OwnerDashboardRead.model_construct(
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        wb_summary=OwnerWbSummary.model_construct(
            daily=[
                OwnerWbDailyPoint(date=date(2026, 5, 1)),
                OwnerWbDailyPoint(date=date(2026, 5, 2)),
            ]
        ),
        ads_summary=OwnerAdsSummary.model_construct(
            daily=[
                OwnerAdsDailyPoint(date=date(2026, 5, 1)),
                OwnerAdsDailyPoint(date=date(2026, 5, 2)),
            ]
        ),
    )
    monkeypatch.setattr(
        service, "_load_snapshot", AsyncMock(return_value=invalid_snapshot)
    )
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    compute = AsyncMock(return_value=valid_snapshot)
    monkeypatch.setattr(service.control_tower, "owner_dashboard", compute)

    result = await service.owner_dashboard(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result is valid_snapshot
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


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
async def test_operator_load_snapshot_backfills_purchase_plan_summary_from_old_payload() -> (
    None
):
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
