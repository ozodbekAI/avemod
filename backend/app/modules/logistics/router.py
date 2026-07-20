from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.schemas.logistics import LogisticsOverviewRead
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
)
from app.services.logistics import LogisticsService

router = APIRouter(tags=["logistics"])
service = LogisticsService()

READ_ROLES = {"viewer", "operator", "manager", "admin"}


async def _require_logistics_read(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int,
) -> None:
    await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )
    await require_account_role(
        session, user, account_id=account_id, allowed_roles=READ_ROLES
    )


@router.get("/portal/logistics/overview", response_model=LogisticsOverviewRead)
async def logistics_overview(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    warehouse_limit: int = Query(default=50, ge=1, le=200),
    supply_limit: int = Query(default=20, ge=1, le=100),
    product_limit: int = Query(default=120, ge=1, le=500),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> LogisticsOverviewRead:
    await _require_logistics_read(session, current_user, account_id=account_id)
    return await service.overview(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        warehouse_limit=warehouse_limit,
        supply_limit=supply_limit,
        product_limit=product_limit,
    )


@router.get("/portal/logistics/export.csv")
async def logistics_export_csv(
    account_id: int = Query(...),
    dataset: str = Query(
        default="tasks",
        pattern=(
            "^(tasks|regional|controls|warehouses|products|shipment|"
            "paid_storage|acceptance|transit|seller_warehouses)$"
        ),
    ),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    disabled_warehouses: list[str] | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _require_logistics_read(session, current_user, account_id=account_id)
    content = await service.export_csv(
        session,
        account_id=account_id,
        dataset=dataset,
        date_from=date_from,
        date_to=date_to,
        search=search,
        disabled_warehouses=set(disabled_warehouses or []),
    )
    filename = f"logistics_{dataset}_{account_id}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
