from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class StocksClient:
    BASE_URL = "https://seller-analytics-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def create_warehouse_remains_task(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/warehouse_remains",
            url=f"{self.BASE_URL}/api/v1/warehouse_remains",
            params={
                "groupByNm": True,
                "groupByBarcode": True,
                "groupBySize": True,
            },
            api_category="analytics",
        )

    async def task_status(self, session, *, account_id: int, task_id: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/warehouse_remains/tasks/{task_id}/status",
            url=f"{self.BASE_URL}/api/v1/warehouse_remains/tasks/{task_id}/status",
            api_category="analytics",
        )

    async def download_report(self, session, *, account_id: int, task_id: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/warehouse_remains/tasks/{task_id}/download",
            url=f"{self.BASE_URL}/api/v1/warehouse_remains/tasks/{task_id}/download",
            api_category="analytics",
        )
