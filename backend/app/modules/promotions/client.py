from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class PromotionsClient:
    BASE_URL = "https://dp-calendar-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def promotions(
        self,
        session,
        *,
        account_id: int,
        start_date_time: str,
        end_date_time: str,
        all_promo: bool = True,
        limit: int = 1000,
        offset: int = 0,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/calendar/promotions",
            url=f"{self.BASE_URL}/api/v1/calendar/promotions",
            params={
                "startDateTime": start_date_time,
                "endDateTime": end_date_time,
                "allPromo": all_promo,
                "limit": limit,
                "offset": offset,
            },
            api_category="promotion",
        )

    async def details(self, session, *, account_id: int, promotion_ids: list[int]):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/calendar/promotions/details",
            url=f"{self.BASE_URL}/api/v1/calendar/promotions/details",
            params={"promotionIDs": promotion_ids},
            api_category="promotion",
        )

    async def nomenclatures(
        self,
        session,
        *,
        account_id: int,
        promotion_id: int,
        in_action: bool,
        limit: int = 1000,
        offset: int = 0,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/calendar/promotions/nomenclatures",
            url=f"{self.BASE_URL}/api/v1/calendar/promotions/nomenclatures",
            params={
                "promotionID": promotion_id,
                "inAction": in_action,
                "limit": limit,
                "offset": offset,
            },
            api_category="promotion",
        )
