from __future__ import annotations

from typing import Any

from app.core.wb_sync import DomainSyncBase


class ProductCardsClient:
    BASE_URL = "https://content-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def list_cards(
        self,
        session,
        *,
        account_id: int,
        cursor: dict[str, Any] | None = None,
        limit: int = 100,
        ascending: bool = True,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "settings": {
                "sort": {"ascending": ascending},
                "cursor": {"limit": limit},
                "filter": {"withPhoto": -1},
            }
        }
        if cursor:
            body["settings"]["cursor"].update(cursor)
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/content/v2/get/cards/list",
            url=f"{self.BASE_URL}/content/v2/get/cards/list",
            method="POST",
            json_body=body,
        )

    async def list_tags(self, session, *, account_id: int) -> dict[str, Any]:
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/content/v2/tags",
            url=f"{self.BASE_URL}/content/v2/tags",
        )
