from __future__ import annotations

from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest

from app.core.pagination import Page
from app.schemas.stocks import StockSnapshotRowRead
from app.services.stocks import StocksService


@pytest.mark.asyncio
async def test_list_snapshot_rows_reuses_cached_page(monkeypatch) -> None:
    service = StocksService()
    monkeypatch.setattr(service, "_page_version_hash", AsyncMock(return_value="v1"))
    service.repo.list_filtered = AsyncMock(
        return_value=Page(
            total=1,
            limit=50,
            offset=0,
            items=[
                StockSnapshotRowRead(
                    id=1,
                    snapshot_id=10,
                    account_id=1,
                    nm_id=101,
                    barcode="111",
                    warehouse_name="WH",
                    quantity=1.0,
                    quantity_full=1.0,
                    in_way_to_client=0.0,
                    in_way_from_client=0.0,
                    created_at=datetime(2026, 5, 31, 12, 0, 0),
                )
            ],
        )
    )

    first = await service.list_snapshot_rows(
        None,  # type: ignore[arg-type]
        account_id=1,
        date_from=date(2026, 5, 1),
        date_to=date(2026, 5, 31),
        limit=50,
        offset=0,
    )
    second = await service.list_snapshot_rows(
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
    assert service.repo.list_filtered.await_count == 1
