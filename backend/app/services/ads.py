from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.ads import (
    AdCampaignItemRepository,
    AdCampaignRepository,
    AdClusterStatsRepository,
    AdStatsRepository,
)


class AdsService:
    def __init__(self) -> None:
        self.campaigns = AdCampaignRepository()
        self.items = AdCampaignItemRepository()
        self.stats = AdStatsRepository()
        self.cluster_stats = AdClusterStatsRepository()

    async def list_campaigns(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        advert_id: int | None = None,
        status: int | None = None,
        campaign_type: int | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.campaigns.list_filtered(
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

    async def get_campaign_detail(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        advert_id: int,
    ):
        campaign = await self.campaigns.get_by_advert_id(
            session,
            account_id=account_id,
            advert_id=advert_id,
        )
        if campaign is None:
            return None
        items = await self.items.list_filtered(
            session,
            account_id=account_id,
            campaign_fk_id=campaign.id,
            limit=200,
            offset=0,
        )
        campaign.items = items.items
        return campaign

    async def list_stats(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        advert_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.stats.list_filtered(
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

    async def list_cluster_stats(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        advert_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.cluster_stats.list_filtered(
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
