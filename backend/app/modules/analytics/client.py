from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class AnalyticsClient:
    BASE_URL = "https://seller-analytics-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def funnel_history(
        self,
        session,
        *,
        account_id: int,
        nm_ids: list[int],
        start_date: str,
        end_date: str,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/analytics/v3/sales-funnel/products/history",
            url=f"{self.BASE_URL}/api/analytics/v3/sales-funnel/products/history",
            method="POST",
            json_body={
                "selectedPeriod": {"start": start_date, "end": end_date},
                "nmIds": nm_ids,
                "skipDeletedNm": True,
                "aggregationLevel": "day",
            },
            api_category="analytics",
        )

    async def region_sales(
        self, session, *, account_id: int, date_from: str, date_to: str
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/analytics/region-sale",
            url=f"{self.BASE_URL}/api/v1/analytics/region-sale",
            params={"dateFrom": date_from, "dateTo": date_to},
            api_category="analytics",
        )

    async def blocked_products(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/analytics/banned-products/blocked",
            url=f"{self.BASE_URL}/api/v1/analytics/banned-products/blocked",
            params={"sort": "nmId", "order": "asc"},
            api_category="analytics",
        )

    async def shadowed_products(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/analytics/banned-products/shadowed",
            url=f"{self.BASE_URL}/api/v1/analytics/banned-products/shadowed",
            params={"sort": "nmId", "order": "asc"},
            api_category="analytics",
        )
