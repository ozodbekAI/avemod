from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from sqlalchemy.dialects import postgresql

from app.core.time import utcnow
from app.schemas.money_management import (
    ExpenseBreakdownSummaryRead,
    MoneyCardPage,
    MoneySummaryRead,
    ProfitCascadeRead,
)
from app.services.money_snapshots import MoneyEndpointSnapshotService


@pytest.mark.asyncio
async def test_summary_uses_db_snapshot_before_recomputing(monkeypatch) -> None:
    service = MoneyEndpointSnapshotService()
    snapshot = MoneySummaryRead.model_construct(cache_status="db_snapshot_hit")
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=snapshot))
    compute = AsyncMock()
    monkeypatch.setattr(service.money, "summary", compute)

    result = await service.summary(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result is snapshot
    assert compute.await_count == 0


@pytest.mark.asyncio
async def test_cards_computes_and_saves_snapshot_on_cache_miss(monkeypatch) -> None:
    service = MoneyEndpointSnapshotService()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    page = MoneyCardPage.model_construct(
        total=0, limit=8, offset=0, summary={}, items=[], cache_status="miss"
    )
    compute = AsyncMock(return_value=page)
    monkeypatch.setattr(service.money, "cards", compute)

    result = await service.cards(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=8,
        offset=0,
        sort_by="priority_score",
        sort_dir="desc",
    )

    assert result is page
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


@pytest.mark.asyncio
async def test_profit_cascade_uses_db_snapshot_before_recomputing(monkeypatch) -> None:
    service = MoneyEndpointSnapshotService()
    snapshot = ProfitCascadeRead.model_construct(account_id=1)
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=snapshot))
    compute = AsyncMock()
    monkeypatch.setattr(service.money, "profit_cascade", compute)

    result = await service.profit_cascade(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
    )

    assert result is snapshot
    assert compute.await_count == 0


@pytest.mark.asyncio
async def test_expense_breakdown_computes_and_saves_snapshot_on_cache_miss(
    monkeypatch,
) -> None:
    service = MoneyEndpointSnapshotService()
    monkeypatch.setattr(service, "_load_snapshot", AsyncMock(return_value=None))
    save_snapshot = AsyncMock()
    monkeypatch.setattr(service, "_save_snapshot", save_snapshot)
    breakdown = ExpenseBreakdownSummaryRead.model_construct(account_id=1)
    compute = AsyncMock(return_value=breakdown)
    monkeypatch.setattr(service.money, "expense_breakdown", compute)

    result = await service.expense_breakdown(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        group_by="category",
        include_unallocated=True,
    )

    assert result is breakdown
    assert compute.await_count == 1
    assert save_snapshot.await_count == 1


def test_money_default_specs_match_primary_endpoint_params() -> None:
    service = MoneyEndpointSnapshotService()
    specs = service._default_specs_for_account(account_id=1)

    assert any(
        spec.endpoint_key == "money_summary"
        and spec.params == {"formula_version": service.money.SUMMARY_FORMULA_VERSION}
        for spec in specs
    )
    assert any(
        spec.endpoint_key == "money_actions_today"
        and spec.params.get("priority") is None
        and spec.params.get("status") is None
        and spec.params.get("action_type") is None
        and spec.params.get("limit") == 100
        for spec in specs
    )
    assert any(
        spec.endpoint_key == "money_articles"
        and spec.params.get("summary_version") == 2
        and spec.params.get("search") is None
        and spec.params.get("limit") == 200
        for spec in specs
    )


class _DummySnapshotResponse(BaseModel):
    value: int
    computed_at: datetime | None = None
    cache_status: str = "miss"


@pytest.mark.asyncio
async def test_load_snapshot_returns_expired_snapshot_as_stale() -> None:
    service = MoneyEndpointSnapshotService()
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
        endpoint_key="money_summary",
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
async def test_load_snapshot_marks_snapshot_as_accessed(monkeypatch) -> None:
    service = MoneyEndpointSnapshotService()
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
        endpoint_key="money_summary",
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        params={},
        model_cls=_DummySnapshotResponse,
    )

    assert snapshot is not None
    touch.assert_awaited_once_with(snapshot_id=42)


@pytest.mark.asyncio
async def test_save_snapshot_uses_postgres_upsert_without_flush() -> None:
    service = MoneyEndpointSnapshotService()
    session = AsyncMock()
    response = _DummySnapshotResponse(value=1)

    await service._save_snapshot(
        session,
        endpoint_key="money_actions_today",
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
    lock_stmt = session.execute.await_args_list[0].args[0]
    assert "pg_advisory_xact_lock" in str(
        lock_stmt.compile(dialect=postgresql.dialect())
    )
    stmt = session.execute.await_args_list[1].args[0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled


@pytest.mark.asyncio
async def test_invalidate_snapshots_marks_rows_not_ready() -> None:
    service = MoneyEndpointSnapshotService()
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
