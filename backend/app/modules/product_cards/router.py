from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.services.auth import get_current_superuser
from app.schemas.product_cards import ProductCardRead
from app.services.product_cards import ProductCardService

router = APIRouter(tags=["products"])
service = ProductCardService()


@router.get("/products", response_model=Page[ProductCardRead])
async def list_products(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[ProductCardRead]:
    return await service.list_cards(
        session,
        account_id=account_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        barcode=barcode,
        brand=brand,
        subject_name=subject_name,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
