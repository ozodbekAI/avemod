from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.sales import WBSale


class SaleRepository(SQLAlchemyRepository[WBSale]):
    def __init__(self) -> None:
        super().__init__(WBSale)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        srid: str | None = None,
        sale_id: str | None = None,
        order_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        brand: str | None = None,
        subject: str | None = None,
        warehouse_name: str | None = None,
        is_cancel: bool | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        sort_map = {
            "date": WBSale.date,
            "last_change_date": WBSale.last_change_date,
            "sale_id": WBSale.sale_id,
            "order_id": WBSale.order_id,
            "nm_id": WBSale.nm_id,
            "vendor_code": WBSale.supplier_article,
            "barcode": WBSale.barcode,
            "brand": WBSale.brand,
            "subject": WBSale.subject,
            "warehouse_name": WBSale.warehouse_name,
            "total_price": WBSale.total_price,
            "for_pay": WBSale.for_pay,
        }
        sort_column = sort_map.get(sort_by or "", WBSale.last_change_date)
        stmt = select(WBSale).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBSale.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBSale.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBSale.nm_id == nm_id)
        if srid is not None:
            stmt = stmt.where(WBSale.srid == srid)
        if sale_id is not None:
            stmt = stmt.where(WBSale.sale_id == sale_id)
        if order_id is not None:
            stmt = stmt.where(WBSale.order_id == order_id)
        if vendor_code is not None:
            stmt = stmt.where(WBSale.supplier_article.ilike(f"%{vendor_code}%"))
        if barcode is not None:
            stmt = stmt.where(WBSale.barcode.ilike(f"%{barcode}%"))
        if brand is not None:
            stmt = stmt.where(WBSale.brand.ilike(f"%{brand}%"))
        if subject is not None:
            stmt = stmt.where(WBSale.subject.ilike(f"%{subject}%"))
        if warehouse_name is not None:
            stmt = stmt.where(WBSale.warehouse_name.ilike(f"%{warehouse_name}%"))
        if is_cancel is not None:
            stmt = stmt.where(WBSale.is_cancel.is_(is_cancel))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBSale.srid.ilike(pattern),
                    WBSale.sale_id.ilike(pattern),
                    WBSale.supplier_article.ilike(pattern),
                    WBSale.barcode.ilike(pattern),
                    WBSale.brand.ilike(pattern),
                    WBSale.subject.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(WBSale.date >= datetime.combine(date_from, time.min))
        if date_to is not None:
            stmt = stmt.where(WBSale.date <= datetime.combine(date_to, time.max))
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
