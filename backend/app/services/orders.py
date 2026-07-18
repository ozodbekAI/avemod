from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.orders import OrderRepository


class OrderService:
    def __init__(self) -> None:
        self.repo = OrderRepository()

    async def list_orders(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
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
        limit=50,
        offset=0,
    ):
        return await self.repo.list_filtered(
            session,
            account_id=account_id,
            nm_id=nm_id,
            srid=srid,
            order_id=order_id,
            vendor_code=vendor_code,
            barcode=barcode,
            warehouse_name=warehouse_name,
            region_name=region_name,
            is_cancel=is_cancel,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
