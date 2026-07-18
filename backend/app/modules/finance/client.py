from __future__ import annotations

from typing import Any

from app.core.wb_sync import DomainSyncBase


class FinanceClient:
    BASE_URL = "https://finance-api.wildberries.ru"

    def __init__(self, sync_base: DomainSyncBase) -> None:
        self.sync_base = sync_base

    async def balance(self, session, *, account_id: int):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/v1/account/balance",
            url=f"{self.BASE_URL}/api/v1/account/balance",
        )

    async def sales_reports_list(
        self, session, *, account_id: int, date_from: str, date_to: str
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/finance/v1/sales-reports/list",
            url=f"{self.BASE_URL}/api/finance/v1/sales-reports/list",
            method="POST",
            json_body={"dateFrom": date_from, "dateTo": date_to},
        )

    async def sales_reports_detailed(
        self,
        session,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
        rrd_id: int = 0,
        limit: int = 100000,
        fields: list[str] | None = None,
    ):
        body: dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "period": "weekly",
            "rrdId": rrd_id,
            "limit": limit,
        }
        if fields:
            body["fields"] = fields
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/finance/v1/sales-reports/detailed",
            url=f"{self.BASE_URL}/api/finance/v1/sales-reports/detailed",
            method="POST",
            json_body=body,
        )

    async def acquiring_reports_list(
        self, session, *, account_id: int, date_from: str, date_to: str
    ):
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/finance/v1/acquiring/list",
            url=f"{self.BASE_URL}/api/finance/v1/acquiring/list",
            method="POST",
            json_body={"dateFrom": date_from, "dateTo": date_to},
        )

    async def acquiring_reports_detailed(
        self,
        session,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
        rrd_id: int = 0,
        limit: int = 100000,
        fields: list[str] | None = None,
    ):
        body: dict[str, Any] = {
            "dateFrom": date_from,
            "dateTo": date_to,
            "rrdId": rrd_id,
            "limit": limit,
        }
        if fields:
            body["fields"] = fields
        return await self.sync_base._request_json(
            session,
            account_id=account_id,
            endpoint="/api/finance/v1/acquiring/detailed",
            url=f"{self.BASE_URL}/api/finance/v1/acquiring/detailed",
            method="POST",
            json_body=body,
        )
