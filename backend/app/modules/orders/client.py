from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class OrdersClient:
    URL = "https://statistics-api.wildberries.ru/api/v1/supplier/orders"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def fetch_orders(self, session, *, account_id: int, date_from: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/supplier/orders",
            url=self.URL,
            params={"dateFrom": date_from},
            api_category="statistics",
        )
