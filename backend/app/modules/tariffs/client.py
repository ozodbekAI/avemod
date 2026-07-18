from __future__ import annotations

from app.core.wb_sync import DomainSyncBase


class TariffsClient:
    BASE_URL = "https://common-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def commissions(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/tariffs/commission",
            url=f"{self.BASE_URL}/api/v1/tariffs/commission",
            params={"locale": "ru"},
            api_category="tariffs",
        )

    async def boxes(self, session, *, account_id: int, for_date: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/tariffs/box",
            url=f"{self.BASE_URL}/api/v1/tariffs/box",
            params={"date": for_date},
            api_category="tariffs",
        )

    async def pallets(self, session, *, account_id: int, for_date: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/tariffs/pallet",
            url=f"{self.BASE_URL}/api/v1/tariffs/pallet",
            params={"date": for_date},
            api_category="tariffs",
        )

    async def returns(self, session, *, account_id: int, for_date: str):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/tariffs/return",
            url=f"{self.BASE_URL}/api/v1/tariffs/return",
            params={"date": for_date},
            api_category="tariffs",
        )

    async def acceptance(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/tariffs/v1/acceptance/coefficients",
            url=f"{self.BASE_URL}/api/tariffs/v1/acceptance/coefficients",
            api_category="tariffs",
        )
