from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.orders import OrderRead
from app.services.auth import get_current_superuser
from app.services.orders import OrderService

router = APIRouter(tags=["orders"])
service = OrderService()


@router.get("/orders", response_model=Page[OrderRead])
async def list_orders(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    srid: str | None = Query(default=None),
    order_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    warehouse_name: str | None = Query(default=None),
    region_name: str | None = Query(default=None),
    is_cancel: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_orders(
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
