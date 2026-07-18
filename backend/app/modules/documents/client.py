from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class DocumentsClient:
    BASE_URL = "https://documents-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def categories(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/documents/categories",
            url=f"{self.BASE_URL}/api/v1/documents/categories",
            params={"locale": "ru"},
            api_category="documents",
        )

    async def documents(
        self, session, *, account_id: int, begin_time: str, end_time: str
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/documents/list",
            url=f"{self.BASE_URL}/api/v1/documents/list",
            params={
                "locale": "ru",
                "beginTime": begin_time,
                "endTime": end_time,
                "sort": "date",
                "order": "desc",
            },
            api_category="documents",
        )
