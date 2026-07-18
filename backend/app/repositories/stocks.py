from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow


class StockSnapshotRepository(SQLAlchemyRepository[WBStockSnapshot]):
    def __init__(self) -> None:
        super().__init__(WBStockSnapshot)


class StockSnapshotRowRepository(SQLAlchemyRepository[WBStockSnapshotRow]):
    def __init__(self) -> None:
        super().__init__(WBStockSnapshotRow)

    async def list_filtered(
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
        sort_map = {
            "id": WBStockSnapshotRow.id,
            "nm_id": WBStockSnapshotRow.nm_id,
            "barcode": WBStockSnapshotRow.barcode,
            "warehouse_name": WBStockSnapshotRow.warehouse_name,
            "quantity": WBStockSnapshotRow.quantity,
            "quantity_full": WBStockSnapshotRow.quantity_full,
            "in_way_to_client": WBStockSnapshotRow.in_way_to_client,
            "in_way_from_client": WBStockSnapshotRow.in_way_from_client,
        }
        sort_column = sort_map.get(sort_by or "", WBStockSnapshotRow.id)
        stmt = select(WBStockSnapshotRow).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBStockSnapshotRow.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBStockSnapshotRow.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBStockSnapshotRow.nm_id == nm_id)
        if barcode is not None:
            stmt = stmt.where(WBStockSnapshotRow.barcode.ilike(f"%{barcode}%"))
        if warehouse_name is not None:
            stmt = stmt.where(
                WBStockSnapshotRow.warehouse_name.ilike(f"%{warehouse_name}%")
            )
        if brand is not None:
            stmt = stmt.where(WBStockSnapshotRow.brand.ilike(f"%{brand}%"))
        if subject is not None:
            stmt = stmt.where(WBStockSnapshotRow.subject.ilike(f"%{subject}%"))
        if in_stock_only:
            stmt = stmt.where(WBStockSnapshotRow.quantity > 0)
        if date_from is not None:
            stmt = stmt.where(
                WBStockSnapshotRow.snapshot_id.in_(
                    select(WBStockSnapshot.id).where(
                        WBStockSnapshot.id == WBStockSnapshotRow.snapshot_id,
                        WBStockSnapshot.snapshot_at
                        >= datetime.combine(date_from, time.min),
                    )
                )
            )
        if date_to is not None:
            stmt = stmt.where(
                WBStockSnapshotRow.snapshot_id.in_(
                    select(WBStockSnapshot.id).where(
                        WBStockSnapshot.id == WBStockSnapshotRow.snapshot_id,
                        WBStockSnapshot.snapshot_at
                        <= datetime.combine(date_to, time.max),
                    )
                )
            )
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBStockSnapshotRow.barcode.ilike(pattern),
                    WBStockSnapshotRow.warehouse_name.ilike(pattern),
                    WBStockSnapshotRow.brand.ilike(pattern),
                    WBStockSnapshotRow.subject.ilike(pattern),
                )
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
