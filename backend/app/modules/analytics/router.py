from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.services.analytics import AnalyticsService
from app.models.auth import AuthUser
from app.schemas.analytics import AnalyticsOverviewRead, CardFunnelRead, RegionSalesRead
from app.services.auth import (
    get_current_superuser,
    get_current_user,
    require_account_role,
    resolve_user_account,
)

router = APIRouter(tags=["analytics"])
service = AnalyticsService()
READ_ROLES = {"viewer", "operator", "manager", "admin"}


async def _require_analytics_read(
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


@router.get("/analytics/overview", response_model=AnalyticsOverviewRead)
async def analytics_overview(
    account_id: int = Query(...),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    brand_name: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    region_name: str | None = Query(default=None),
    country_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    product_limit: int = Query(default=20, ge=1, le=100),
    region_limit: int = Query(default=15, ge=1, le=100),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AnalyticsOverviewRead:
    await _require_analytics_read(session, current_user, account_id=account_id)
    return await service.overview(
        session,
        account_id=account_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        brand_name=brand_name,
        subject_name=subject_name,
        region_name=region_name,
        country_name=country_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
        product_limit=product_limit,
        region_limit=region_limit,
    )


@router.get("/analytics/export.csv")
async def analytics_export_csv(
    account_id: int = Query(...),
    dataset: str = Query(default="products", pattern="^(products|regions|trend)$"),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    brand_name: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    region_name: str | None = Query(default=None),
    country_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _require_analytics_read(session, current_user, account_id=account_id)
    content = await service.export_csv(
        session,
        account_id=account_id,
        dataset=dataset,
        nm_id=nm_id,
        vendor_code=vendor_code,
        brand_name=brand_name,
        subject_name=subject_name,
        region_name=region_name,
        country_name=country_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
    )
    filename = f"analytics_{dataset}_{account_id}.csv"
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/analytics/funnel", response_model=Page[CardFunnelRead])
async def list_card_funnel(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    brand_name: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
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
    return await service.list_funnel(
        session,
        account_id=account_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        brand_name=brand_name,
        subject_name=subject_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/analytics/regions", response_model=Page[RegionSalesRead])
async def list_region_analytics(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    region_name: str | None = Query(default=None),
    country_name: str | None = Query(default=None),
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
    return await service.list_regions(
        session,
        account_id=account_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        region_name=region_name,
        country_name=country_name,
        search=search,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
