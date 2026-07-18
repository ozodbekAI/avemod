from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.orders import WBOrder


class OrderRepository(SQLAlchemyRepository[WBOrder]):
    def __init__(self) -> None:
        super().__init__(WBOrder)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        srid: str | None = None,
        order_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        warehouse_name: str | None = None,
        region_name: str | None = None,
        is_cancel: bool | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ):
        sort_map = {
            "date": WBOrder.date,
            "last_change_date": WBOrder.last_change_date,
            "order_id": WBOrder.order_id,
            "nm_id": WBOrder.nm_id,
            "vendor_code": WBOrder.supplier_article,
            "barcode": WBOrder.barcode,
            "warehouse_name": WBOrder.warehouse_name,
            "region_name": WBOrder.region_name,
            "total_price": WBOrder.total_price,
            "finished_price": WBOrder.finished_price,
        }
        sort_column = sort_map.get(sort_by or "", WBOrder.last_change_date)
        stmt = select(WBOrder).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBOrder.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBOrder.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBOrder.nm_id == nm_id)
        if srid is not None:
            stmt = stmt.where(WBOrder.srid == srid)
        if order_id is not None:
            stmt = stmt.where(WBOrder.order_id == order_id)
        if vendor_code is not None:
            stmt = stmt.where(WBOrder.supplier_article.ilike(f"%{vendor_code}%"))
        if barcode is not None:
            stmt = stmt.where(WBOrder.barcode.ilike(f"%{barcode}%"))
        if warehouse_name is not None:
            stmt = stmt.where(WBOrder.warehouse_name.ilike(f"%{warehouse_name}%"))
        if region_name is not None:
            stmt = stmt.where(
                or_(
                    WBOrder.region_name.ilike(f"%{region_name}%"),
                    WBOrder.oblast_okrug_name.ilike(f"%{region_name}%"),
                    WBOrder.country_name.ilike(f"%{region_name}%"),
                )
            )
        if is_cancel is not None:
            stmt = stmt.where(WBOrder.is_cancel.is_(is_cancel))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBOrder.srid.ilike(pattern),
                    WBOrder.supplier_article.ilike(pattern),
                    WBOrder.barcode.ilike(pattern),
                    WBOrder.warehouse_name.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(WBOrder.date >= datetime.combine(date_from, time.min))
        if date_to is not None:
            stmt = stmt.where(WBOrder.date <= datetime.combine(date_to, time.max))
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
