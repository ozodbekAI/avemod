from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class PricesClient:
    BASE_URL = "https://discounts-prices-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def list_goods(self, session, *, account_id: int, limit: int, offset: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/list/goods/filter",
            url=f"{self.BASE_URL}/api/v2/list/goods/filter",
            params={"limit": limit, "offset": offset},
        )

    async def list_sizes(self, session, *, account_id: int, nm_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/list/goods/size/nm",
            url=f"{self.BASE_URL}/api/v2/list/goods/size/nm",
            params={"limit": 1000, "offset": 0, "nmID": nm_id},
        )

    async def processed_tasks(self, session, *, account_id: int, upload_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/history/tasks",
            url=f"{self.BASE_URL}/api/v2/history/tasks",
            params={"uploadID": upload_id},
        )

    async def processed_task_goods(
        self,
        session,
        *,
        account_id: int,
        upload_id: int,
        limit: int = 1000,
        offset: int = 0,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/history/goods/task",
            url=f"{self.BASE_URL}/api/v2/history/goods/task",
            params={"uploadID": upload_id, "limit": limit, "offset": offset},
        )

    async def unprocessed_tasks(self, session, *, account_id: int, upload_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/buffer/tasks",
            url=f"{self.BASE_URL}/api/v2/buffer/tasks",
            params={"uploadID": upload_id},
        )

    async def unprocessed_task_goods(
        self,
        session,
        *,
        account_id: int,
        upload_id: int,
        limit: int = 1000,
        offset: int = 0,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/buffer/goods/task",
            url=f"{self.BASE_URL}/api/v2/buffer/goods/task",
            params={"uploadID": upload_id, "limit": limit, "offset": offset},
        )

    async def quarantine_goods(
        self, session, *, account_id: int, limit: int = 1000, offset: int = 0
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v2/quarantine/goods",
            url=f"{self.BASE_URL}/api/v2/quarantine/goods",
            params={"limit": limit, "offset": offset},
        )
