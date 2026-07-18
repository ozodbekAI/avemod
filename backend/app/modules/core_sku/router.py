from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.core_sku import CoreSKUDetail, CoreSKUListItem
from app.services.auth import get_current_superuser
from app.services.core_sku import CoreSKUService

router = APIRouter(tags=["core-sku"])
service = CoreSKUService()


@router.get("/core-sku", response_model=Page[CoreSKUListItem])
async def list_core_sku(
    account_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    has_manual_cost: bool | None = Query(default=None),
    has_open_issues: bool | None = Query(default=None),
    has_price: bool | None = Query(default=None),
    has_sales: bool | None = Query(default=None),
    has_revenue: bool | None = Query(default=None),
    has_stock: bool | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[CoreSKUListItem]:
    return await service.list_skus(
        session,
        account_id=account_id,
        search=search,
        nm_id=nm_id,
        vendor_code=vendor_code,
        barcode=barcode,
        brand=brand,
        subject_name=subject_name,
        status=status,
        has_manual_cost=has_manual_cost,
        has_open_issues=has_open_issues,
        has_price=has_price,
        has_sales=has_sales,
        has_revenue=has_revenue,
        has_stock=has_stock,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/core-sku/{sku_id}", response_model=CoreSKUDetail)
async def get_core_sku(
    sku_id: int,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> CoreSKUDetail:
    item = await service.get_sku_detail(
        session, sku_id=sku_id, date_from=date_from, date_to=date_to
    )
    if item is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return item
