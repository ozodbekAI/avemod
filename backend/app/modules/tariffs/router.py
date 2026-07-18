from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.tariffs import TariffRead
from app.services.auth import get_current_superuser
from app.services.tariffs import TariffsService

router = APIRouter(tags=["tariffs"])
service = TariffsService()


@router.get("/tariffs", response_model=Page[TariffRead])
async def list_tariffs(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_tariffs(
        session, account_id=account_id, limit=limit, offset=offset
    )
