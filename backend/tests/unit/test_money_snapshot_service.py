from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel
from sqlalchemy.dialects import postgresql

from app.schemas.money_management import MoneyCardPage, MoneySummaryRead
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
    page = MoneyCardPage.model_construct(total=0, limit=8, offset=0, summary={}, items=[], cache_status="miss")
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


class _DummySnapshotResponse(BaseModel):
    value: int


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
    assert "pg_advisory_xact_lock" in str(lock_stmt.compile(dialect=postgresql.dialect()))
    stmt = session.execute.await_args_list[1].args[0]
    compiled = str(stmt.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT" in compiled
