from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.services.ads import AdsService
from app.models.auth import AuthUser
from app.schemas.ads import (
    AdCampaignDetailRead,
    AdCampaignRead,
    AdClusterStatRead,
    AdStatRead,
)
from app.services.auth import get_current_superuser

router = APIRouter(tags=["ads"])
service = AdsService()


@router.get("/ads/campaigns", response_model=Page[AdCampaignRead])
async def list_ad_campaigns(
    account_id: int | None = Query(default=None),
    advert_id: int | None = Query(default=None),
    status: int | None = Query(default=None),
    campaign_type: int | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_campaigns(
        session,
        account_id=account_id,
        advert_id=advert_id,
        status=status,
        campaign_type=campaign_type,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/ads/campaigns/{advert_id}", response_model=AdCampaignDetailRead)
async def get_ad_campaign(
    advert_id: int,
    account_id: int = Query(...),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    campaign = await service.get_campaign_detail(
        session,
        account_id=account_id,
        advert_id=advert_id,
    )
    if campaign is None:
        raise HTTPException(status_code=404, detail="Ad campaign not found")
    return campaign


@router.get("/ads/stats", response_model=Page[AdStatRead])
async def list_ad_stats(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    advert_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_stats(
        session,
        account_id=account_id,
        nm_id=nm_id,
        advert_id=advert_id,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/ads/clusters", response_model=Page[AdClusterStatRead])
async def list_ad_cluster_stats(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    advert_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_cluster_stats(
        session,
        account_id=account_id,
        nm_id=nm_id,
        advert_id=advert_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
