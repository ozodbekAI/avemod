from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class SuppliesClient:
    BASE_URL = "https://supplies-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def warehouses(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/warehouses",
            url=f"{self.BASE_URL}/api/v1/warehouses",
        )

    async def acceptance_options(self, session, *, account_id: int, items: list[dict]):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/acceptance/options",
            url=f"{self.BASE_URL}/api/v1/acceptance/options",
            method="POST",
            json_body=items,
        )

    async def supplies(
        self, session, *, account_id: int, limit: int = 1000, offset: int = 0
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/supplies",
            url=f"{self.BASE_URL}/api/v1/supplies",
            method="POST",
            params={"limit": limit, "offset": offset},
            json_body={},
        )

    async def supply_details(self, session, *, account_id: int, supply_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/supplies/{ID}",
            url=f"{self.BASE_URL}/api/v1/supplies/{supply_id}",
        )

    async def supply_goods(
        self,
        session,
        *,
        account_id: int,
        supply_id: int,
        limit: int = 1000,
        offset: int = 0,
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/supplies/{ID}/goods",
            url=f"{self.BASE_URL}/api/v1/supplies/{supply_id}/goods",
            params={"limit": limit, "offset": offset},
        )

    async def supply_package(self, session, *, account_id: int, supply_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/supplies/{ID}/package",
            url=f"{self.BASE_URL}/api/v1/supplies/{supply_id}/package",
        )
