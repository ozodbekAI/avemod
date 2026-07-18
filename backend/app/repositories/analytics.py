from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.analytics import WBCardFunnelDaily, WBHiddenProduct, WBRegionSalesDaily


class CardFunnelRepository(SQLAlchemyRepository[WBCardFunnelDaily]):
    def __init__(self) -> None:
        super().__init__(WBCardFunnelDaily)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        vendor_code: str | None = None,
        brand_name: str | None = None,
        subject_name: str | None = None,
        search: str | None = None,
        date_from=None,
        date_to=None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        sort_map = {
            "stat_date": WBCardFunnelDaily.stat_date,
            "nm_id": WBCardFunnelDaily.nm_id,
            "vendor_code": WBCardFunnelDaily.vendor_code,
            "brand_name": WBCardFunnelDaily.brand_name,
            "subject_name": WBCardFunnelDaily.subject_name,
            "open_count": WBCardFunnelDaily.open_count,
            "order_count": WBCardFunnelDaily.order_count,
            "buyout_count": WBCardFunnelDaily.buyout_count,
        }
        sort_column = sort_map.get(sort_by or "", WBCardFunnelDaily.stat_date)
        stmt = select(WBCardFunnelDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBCardFunnelDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBCardFunnelDaily.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBCardFunnelDaily.nm_id == nm_id)
        if vendor_code is not None:
            stmt = stmt.where(WBCardFunnelDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if brand_name is not None:
            stmt = stmt.where(WBCardFunnelDaily.brand_name.ilike(f"%{brand_name}%"))
        if subject_name is not None:
            stmt = stmt.where(WBCardFunnelDaily.subject_name.ilike(f"%{subject_name}%"))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBCardFunnelDaily.vendor_code.ilike(pattern),
                    WBCardFunnelDaily.title.ilike(pattern),
                    WBCardFunnelDaily.brand_name.ilike(pattern),
                    WBCardFunnelDaily.subject_name.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(WBCardFunnelDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBCardFunnelDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class RegionSalesRepository(SQLAlchemyRepository[WBRegionSalesDaily]):
    def __init__(self) -> None:
        super().__init__(WBRegionSalesDaily)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        vendor_code: str | None = None,
        region_name: str | None = None,
        country_name: str | None = None,
        search: str | None = None,
        date_from=None,
        date_to=None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        sort_map = {
            "stat_date": WBRegionSalesDaily.stat_date,
            "nm_id": WBRegionSalesDaily.nm_id,
            "vendor_code": WBRegionSalesDaily.vendor_code,
            "region_name": WBRegionSalesDaily.region_name,
            "country_name": WBRegionSalesDaily.country_name,
            "sale_quantity": WBRegionSalesDaily.sale_quantity,
            "sale_amount": WBRegionSalesDaily.sale_amount,
        }
        sort_column = sort_map.get(sort_by or "", WBRegionSalesDaily.stat_date)
        stmt = select(WBRegionSalesDaily).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBRegionSalesDaily.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBRegionSalesDaily.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBRegionSalesDaily.nm_id == nm_id)
        if vendor_code is not None:
            stmt = stmt.where(WBRegionSalesDaily.vendor_code.ilike(f"%{vendor_code}%"))
        if region_name is not None:
            stmt = stmt.where(WBRegionSalesDaily.region_name.ilike(f"%{region_name}%"))
        if country_name is not None:
            stmt = stmt.where(
                WBRegionSalesDaily.country_name.ilike(f"%{country_name}%")
            )
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBRegionSalesDaily.vendor_code.ilike(pattern),
                    WBRegionSalesDaily.region_name.ilike(pattern),
                    WBRegionSalesDaily.country_name.ilike(pattern),
                    WBRegionSalesDaily.city_name.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(WBRegionSalesDaily.stat_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBRegionSalesDaily.stat_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class HiddenProductRepository(SQLAlchemyRepository[WBHiddenProduct]):
    def __init__(self) -> None:
        super().__init__(WBHiddenProduct)
