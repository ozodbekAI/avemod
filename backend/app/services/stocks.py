from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import stable_hash, table_signature
from app.core.config import get_settings
from app.core.pagination import Page
from app.core.time import utcnow
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.repositories.stocks import StockSnapshotRowRepository
from app.schemas.stocks import StockSnapshotRowRead


class StocksService:
    RESPONSE_CACHE_TTL_SECONDS = get_settings().heavy_endpoint_cache_ttl_seconds
    _shared_page_cache: dict[
        tuple[object, ...], tuple[datetime, Page[StockSnapshotRowRead]]
    ] = {}

    def __init__(self) -> None:
        self.repo = StockSnapshotRowRepository()
        self._page_cache = type(self)._shared_page_cache

    @staticmethod
    def _cache_is_fresh(cached_at: datetime, *, ttl_seconds: int) -> bool:
        return (utcnow() - cached_at) <= timedelta(seconds=ttl_seconds)

    @staticmethod
    def _with_page_cache_meta(
        page: Page[StockSnapshotRowRead],
        *,
        computed_at: datetime,
        cache_status: str,
        data_version_hash: str,
    ) -> Page[StockSnapshotRowRead]:
        return page.model_copy(
            deep=True,
            update={
                "computed_at": computed_at,
                "cache_status": cache_status,
                "data_version_hash": data_version_hash,
            },
        )

    async def _page_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
    ) -> str:
        range_end = date_to + timedelta(days=1) if date_to is not None else None
        snapshot_filters: list[Any] = []
        if account_id is not None:
            snapshot_filters.append(WBStockSnapshot.account_id == account_id)
        if date_from is not None:
            snapshot_filters.append(WBStockSnapshot.snapshot_at >= date_from)
        if range_end is not None:
            snapshot_filters.append(WBStockSnapshot.snapshot_at < range_end)
        snapshot_ids = select(WBStockSnapshot.id).where(*snapshot_filters)
        snapshot_hash = await table_signature(
            session,
            model=WBStockSnapshot,
            account_id=account_id,
            date_column=WBStockSnapshot.snapshot_at,
            date_from=date_from,
            date_to=range_end,
        )
        row_hash = await table_signature(
            session,
            model=WBStockSnapshotRow,
            account_id=account_id,
            extra_filters=[WBStockSnapshotRow.snapshot_id.in_(snapshot_ids)],
        )
        return stable_hash(
            "stocks-snapshots",
            account_id,
            date_from.isoformat() if date_from is not None else "",
            date_to.isoformat() if date_to is not None else "",
            snapshot_hash,
            row_hash,
        )

    async def list_snapshot_rows(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        barcode: str | None = None,
        warehouse_name: str | None = None,
        brand: str | None = None,
        subject: str | None = None,
        in_stock_only: bool | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        data_version_hash = await self._page_version_hash(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        cache_key = (
            account_id,
            nm_id,
            barcode or "",
            warehouse_name or "",
            brand or "",
            subject or "",
            in_stock_only,
            date_from,
            date_to,
            search or "",
            sort_by or "",
            sort_dir,
            limit,
            offset,
            data_version_hash,
        )
        cached_page = self._page_cache.get(cache_key)
        if cached_page is not None:
            cached_at, page = cached_page
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.RESPONSE_CACHE_TTL_SECONDS
            ):
                return self._with_page_cache_meta(
                    page,
                    computed_at=cached_at,
                    cache_status="hit",
                    data_version_hash=data_version_hash,
                )

        page = await self.repo.list_filtered(
            session,
            account_id=account_id,
            nm_id=nm_id,
            barcode=barcode,
            warehouse_name=warehouse_name,
            brand=brand,
            subject=subject,
            in_stock_only=in_stock_only,
            date_from=date_from,
            date_to=date_to,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        computed_at = utcnow()
        cached_page_value = self._with_page_cache_meta(
            page,
            computed_at=computed_at,
            cache_status="miss",
            data_version_hash=data_version_hash,
        )
        self._page_cache[cache_key] = (
            computed_at,
            cached_page_value.model_copy(deep=True),
        )
        return cached_page_value
