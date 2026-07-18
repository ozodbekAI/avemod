from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.services.auth import get_current_superuser
from app.schemas.prices import PriceRead
from app.services.prices import PriceService

router = APIRouter(tags=["prices"])
service = PriceService()


@router.get("/prices", response_model=Page[PriceRead])
async def list_prices(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    currency: str | None = Query(default=None),
    is_bad_turnover: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_prices(
        session,
        account_id=account_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        currency=currency,
        is_bad_turnover=is_bad_turnover,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
