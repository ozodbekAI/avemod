from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.services.auth import (
    get_current_superuser,
    get_current_user,
    require_account_role,
    resolve_user_account,
)
from app.schemas.dashboard import ArticleAuditRead, SKUProfitabilityRow
from app.schemas.dashboard import DashboardDataHealth
from app.services.dashboard import DashboardService
from app.services.operator_snapshots import OperatorEndpointSnapshotService

router = APIRouter(tags=["dashboard"])
service = DashboardService()
snapshot_service = OperatorEndpointSnapshotService()
snapshot_service.dashboard = service
READ_ROLES = {"viewer", "operator", "manager", "admin"}


@router.get("/dashboard/sku-profitability", response_model=Page[SKUProfitabilityRow])
async def sku_profitability(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    has_manual_cost: bool | None = Query(default=None),
    business_trusted: bool | None = Query(default=None),
    sort: str = Query(default="profit_desc"),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[SKUProfitabilityRow]:
    return await snapshot_service.sku_profitability(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        vendor_code=vendor_code,
        barcode=barcode,
        brand=brand,
        subject_name=subject_name,
        has_manual_cost=has_manual_cost,
        business_trusted=business_trusted,
        sort=sort,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/dashboard/article-audit", response_model=ArticleAuditRead)
async def article_audit(
    account_id: int = Query(...),
    nm_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    issues_limit: int = Query(default=50, ge=1, le=500),
    issues_offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> ArticleAuditRead:
    return await snapshot_service.article_audit(
        session,
        account_id=account_id,
        nm_id=nm_id,
        date_from=date_from,
        date_to=date_to,
        issues_limit=issues_limit,
        issues_offset=issues_offset,
    )


@router.get("/dashboard/data-health", response_model=DashboardDataHealth)
async def data_health(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DashboardDataHealth:
    await resolve_user_account(
        session, current_user, account_id=account_id, require_account=True
    )
    await require_account_role(
        session, current_user, account_id=account_id, allowed_roles=READ_ROLES
    )
    return await snapshot_service.data_health(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )
