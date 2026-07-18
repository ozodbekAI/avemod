from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.ads import (
    WBAdCampaign,
    WBAdCampaignItem,
    WBAdClusterStat,
    WBAdStatsDaily,
)


class AdCampaignRepository(SQLAlchemyRepository[WBAdCampaign]):
    def __init__(self) -> None:
        super().__init__(WBAdCampaign)

    async def list_filtered(
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
        sort_map = {
            "change_time": WBAdCampaign.change_time,
            "advert_id": WBAdCampaign.advert_id,
            "status": WBAdCampaign.status,
            "campaign_type": WBAdCampaign.campaign_type,
            "name": WBAdCampaign.name,
        }
        sort_column = sort_map.get(sort_by or "", WBAdCampaign.change_time)
        stmt = select(WBAdCampaign).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBAdCampaign.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBAdCampaign.account_id == account_id)
        if advert_id is not None:
            stmt = stmt.where(WBAdCampaign.advert_id == advert_id)
        if status is not None:
            stmt = stmt.where(WBAdCampaign.status == status)
        if campaign_type is not None:
            stmt = stmt.where(WBAdCampaign.campaign_type == campaign_type)
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBAdCampaign.name.ilike(pattern),
                    WBAdCampaign.bid_type.ilike(pattern),
                )
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)

    async def get_by_advert_id(
        self, session: AsyncSession, *, account_id: int, advert_id: int
    ):
        stmt = select(WBAdCampaign).where(
            WBAdCampaign.account_id == account_id,
            WBAdCampaign.advert_id == advert_id,
        )
        return (await session.execute(stmt)).scalars().first()


class AdCampaignItemRepository(SQLAlchemyRepository[WBAdCampaignItem]):
    def __init__(self) -> None:
        super().__init__(WBAdCampaignItem)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        campaign_fk_id: int | None = None,
        nm_id: int | None = None,
        limit=200,
        offset=0,
    ):
        stmt = select(WBAdCampaignItem).order_by(
            WBAdCampaignItem.nm_id.asc(), WBAdCampaignItem.id.asc()
        )
        if account_id is not None:
            stmt = stmt.where(WBAdCampaignItem.account_id == account_id)
        if campaign_fk_id is not None:
            stmt = stmt.where(WBAdCampaignItem.campaign_fk_id == campaign_fk_id)
        if nm_id is not None:
            stmt = stmt.where(WBAdCampaignItem.nm_id == nm_id)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class AdStatsRepository(SQLAlchemyRepository[WBAdStatsDaily]):
    def __init__(self) -> None:
        super().__init__(WBAdStatsDaily)

    async def list_filtered(
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
        sort_map = {
            "stat_date": WBAdStatsDaily.stat_date,
            "nm_id": WBAdStatsDaily.nm_id,
            "advert_id": WBAdStatsDaily.advert_id,
            "views": WBAdStatsDaily.views,
            "clicks": WBAdStatsDaily.clicks,
            "orders": WBAdStatsDaily.orders,
            "spend": WBAdStatsDaily.sum,
        }
        sort_column = sort_map.get(sort_by or "", WBAdStatsDaily.stat_date)
        stmt = select(WBAdStatsDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBAdStatsDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBAdStatsDaily.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBAdStatsDaily.nm_id == nm_id)
        if advert_id is not None:
            stmt = stmt.where(WBAdStatsDaily.advert_id == advert_id)
        if date_from is not None:
            stmt = stmt.where(WBAdStatsDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBAdStatsDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class AdClusterStatsRepository(SQLAlchemyRepository[WBAdClusterStat]):
    def __init__(self) -> None:
        super().__init__(WBAdClusterStat)

    async def list_filtered(
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
        sort_map = {
            "stat_date": WBAdClusterStat.stat_date,
            "nm_id": WBAdClusterStat.nm_id,
            "advert_id": WBAdClusterStat.advert_id,
            "views": WBAdClusterStat.views,
            "clicks": WBAdClusterStat.clicks,
            "orders": WBAdClusterStat.orders,
            "spend": WBAdClusterStat.sum,
            "avg_position": WBAdClusterStat.avg_position,
        }
        sort_column = sort_map.get(sort_by or "", WBAdClusterStat.sum)
        stmt = select(WBAdClusterStat).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBAdClusterStat.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBAdClusterStat.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBAdClusterStat.nm_id == nm_id)
        if advert_id is not None:
            stmt = stmt.where(WBAdClusterStat.advert_id == advert_id)
        if date_from is not None:
            stmt = stmt.where(WBAdClusterStat.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBAdClusterStat.stat_date <= date_to)
        if search is not None:
            stmt = stmt.where(WBAdClusterStat.cluster.ilike(f"%{search}%"))
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
