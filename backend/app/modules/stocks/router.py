from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.stocks import StockSnapshotRowRead
from app.services.auth import get_current_superuser
from app.services.stocks import StocksService

router = APIRouter(tags=["stocks"])
service = StocksService()


@router.get("/stocks/snapshots", response_model=Page[StockSnapshotRowRead])
async def list_stock_snapshots(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    barcode: str | None = Query(default=None),
    warehouse_name: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    subject: str | None = Query(default=None),
    in_stock_only: bool | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_snapshot_rows(
        session,
        account_id=account_id,
        nm_id=nm_id,
        barcode=barcode,
        warehouse_name=warehouse_name,
        brand=brand,
        subject=subject,
        in_stock_only=in_stock_only,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
