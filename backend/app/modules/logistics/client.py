from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class LogisticsClient:
    ANALYTICS_BASE_URL = "https://seller-analytics-api.wildberries.ru"
    SUPPLIES_BASE_URL = "https://supplies-api.wildberries.ru"
    MARKETPLACE_BASE_URL = "https://marketplace-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def create_paid_storage_report(
        self,
        session,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/paid_storage",
            url=f"{self.ANALYTICS_BASE_URL}/api/v1/paid_storage",
            params={"dateFrom": date_from, "dateTo": date_to},
            api_category="analytics",
            token_category="analytics",
        )

    async def paid_storage_status(self, session, *, account_id: int, task_id: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/paid_storage/tasks/{task_id}/status",
            url=(
                f"{self.ANALYTICS_BASE_URL}/api/v1/paid_storage/tasks/"
                f"{task_id}/status"
            ),
            api_category="analytics",
            token_category="analytics",
        )

    async def paid_storage_download(self, session, *, account_id: int, task_id: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/paid_storage/tasks/{task_id}/download",
            url=(
                f"{self.ANALYTICS_BASE_URL}/api/v1/paid_storage/tasks/"
                f"{task_id}/download"
            ),
            api_category="analytics",
            token_category="analytics",
        )

    async def create_acceptance_report(
        self,
        session,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/acceptance_report",
            url=f"{self.ANALYTICS_BASE_URL}/api/v1/acceptance_report",
            params={"dateFrom": date_from, "dateTo": date_to},
            api_category="analytics",
            token_category="analytics",
        )

    async def acceptance_report_status(self, session, *, account_id: int, task_id: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/acceptance_report/tasks/{task_id}/status",
            url=(
                f"{self.ANALYTICS_BASE_URL}/api/v1/acceptance_report/tasks/"
                f"{task_id}/status"
            ),
            api_category="analytics",
            token_category="analytics",
        )

    async def acceptance_report_download(
        self, session, *, account_id: int, task_id: str
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/acceptance_report/tasks/{task_id}/download",
            url=(
                f"{self.ANALYTICS_BASE_URL}/api/v1/acceptance_report/tasks/"
                f"{task_id}/download"
            ),
            api_category="analytics",
            token_category="analytics",
        )

    async def transit_tariffs(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/transit-tariffs",
            url=f"{self.SUPPLIES_BASE_URL}/api/v1/transit-tariffs",
            api_category="supplies",
            token_category="supplies",
        )

    async def seller_warehouses(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v3/warehouses",
            url=f"{self.MARKETPLACE_BASE_URL}/api/v3/warehouses",
            api_category="marketplace",
            token_category="marketplace",
        )

    async def seller_stocks(
        self,
        session,
        *,
        account_id: int,
        warehouse_id: int,
        chrt_ids: list[int],
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v3/stocks/{warehouseId}",
            url=f"{self.MARKETPLACE_BASE_URL}/api/v3/stocks/{warehouse_id}",
            method="POST",
            json_body={"chrtIds": chrt_ids},
            api_category="marketplace",
            token_category="marketplace",
        )
