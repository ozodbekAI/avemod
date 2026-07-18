from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.supplies import SupplyRead
from app.services.auth import get_current_superuser
from app.services.supplies import SuppliesService

router = APIRouter(tags=["supplies"])
service = SuppliesService()


@router.get("/supplies", response_model=Page[SupplyRead])
async def list_supplies(
    account_id: int | None = Query(default=None),
    supply_id: int | None = Query(default=None),
    status_id: int | None = Query(default=None),
    warehouse_name: str | None = Query(default=None),
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
    return await service.list_supplies(
        session,
        account_id=account_id,
        supply_id=supply_id,
        status_id=status_id,
        warehouse_name=warehouse_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
