from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class AdsClient:
    BASE_URL = "https://advert-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def campaigns(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/advert/v2/adverts",
            url=f"{self.BASE_URL}/api/advert/v2/adverts",
        )

    async def full_stats(
        self,
        session,
        *,
        account_id: int,
        ids: list[int],
        begin_date: str,
        end_date: str,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/adv/v3/fullstats",
            url=f"{self.BASE_URL}/adv/v3/fullstats",
            params={
                "ids": ",".join(str(item) for item in ids),
                "beginDate": begin_date,
                "endDate": end_date,
            },
        )

    async def cluster_stats(
        self,
        session,
        *,
        account_id: int,
        items: list[dict],
        date_from: str,
        date_to: str,
    ):
        request_items = []
        for item in items:
            advert_id = item.get("advertId") or item.get("advert_id")
            nm_id = item.get("nmId") or item.get("nm_id")
            if advert_id is None or nm_id is None:
                continue
            request_items.append({"advertId": int(advert_id), "nmId": int(nm_id)})
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/adv/v1/normquery/stats",
            url=f"{self.BASE_URL}/adv/v1/normquery/stats",
            method="POST",
            json_body={"from": date_from, "to": date_to, "items": request_items},
        )
