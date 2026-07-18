from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.prices import (
    WBPrice,
    WBPriceQuarantine,
    WBPriceSize,
    WBPriceSnapshot,
    WBPriceUploadTask,
    WBPriceUploadTaskRow,
)


class PriceRepository(SQLAlchemyRepository[WBPrice]):
    def __init__(self) -> None:
        super().__init__(WBPrice)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        currency: str | None = None,
        is_bad_turnover: bool | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ):
        sort_map = {
            "id": WBPrice.id,
            "nm_id": WBPrice.nm_id,
            "vendor_code": WBPrice.vendor_code,
            "currency": WBPrice.currency_iso_code,
            "discount": WBPrice.discount,
            "club_discount": WBPrice.club_discount,
        }
        sort_column = sort_map.get(sort_by or "", WBPrice.id)
        stmt = select(WBPrice).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBPrice.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBPrice.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBPrice.nm_id == nm_id)
        if vendor_code is not None:
            stmt = stmt.where(WBPrice.vendor_code.ilike(f"%{vendor_code}%"))
        if currency is not None:
            stmt = stmt.where(WBPrice.currency_iso_code == currency)
        if is_bad_turnover is not None:
            stmt = stmt.where(WBPrice.is_bad_turnover.is_(is_bad_turnover))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBPrice.vendor_code.ilike(pattern),
                )
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class PriceSizeRepository(SQLAlchemyRepository[WBPriceSize]):
    def __init__(self) -> None:
        super().__init__(WBPriceSize)


class PriceSnapshotRepository(SQLAlchemyRepository[WBPriceSnapshot]):
    def __init__(self) -> None:
        super().__init__(WBPriceSnapshot)


class PriceUploadTaskRepository(SQLAlchemyRepository[WBPriceUploadTask]):
    def __init__(self) -> None:
        super().__init__(WBPriceUploadTask)

    async def get_by_unique(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source: str,
        task_key: str,
    ) -> WBPriceUploadTask | None:
        return (
            await session.execute(
                select(WBPriceUploadTask).where(
                    WBPriceUploadTask.account_id == account_id,
                    WBPriceUploadTask.source == source,
                    WBPriceUploadTask.task_key == task_key,
                )
            )
        ).scalar_one_or_none()


class PriceUploadTaskRowRepository(SQLAlchemyRepository[WBPriceUploadTaskRow]):
    def __init__(self) -> None:
        super().__init__(WBPriceUploadTaskRow)


class PriceQuarantineRepository(SQLAlchemyRepository[WBPriceQuarantine]):
    def __init__(self) -> None:
        super().__init__(WBPriceQuarantine)
