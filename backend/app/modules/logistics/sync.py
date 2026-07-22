from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, select

from app.core.parsing import parse_date, parse_datetime
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.models.accounts import WBAPICategory, WBAPIToken
from app.models.logistics import (
    WBLogisticsAcceptanceReportRow,
    WBLogisticsPaidStorageRow,
    WBLogisticsTransitTariff,
    WBSellerWarehouseStock,
)
from app.models.product_cards import CoreSKU
from app.modules.logistics.client import LogisticsClient
from app.repositories.logistics import (
    LogisticsAcceptanceReportRepository,
    LogisticsPaidStorageRepository,
    LogisticsTransitTariffRepository,
    SellerWarehouseRepository,
    SellerWarehouseStockRepository,
)


class LogisticsSyncService(DomainSyncBase):
    domain = "logistics"
    category = WBAPICategory.ANALYTICS.value

    PAID_STORAGE_CURSOR_KEY = "paid_storage_task"
    ACCEPTANCE_CURSOR_KEY = "acceptance_report_task"
    PAID_STORAGE_WINDOW_DAYS = 31
    PAID_STORAGE_CHUNK_DAYS = 8
    ACCEPTANCE_WINDOW_DAYS = 31
    REPORT_STATUS_POLL_ATTEMPTS = 3
    REPORT_STATUS_POLL_SECONDS = 5
    MARKETPLACE_STOCK_CHUNK_SIZE = 1000

    def __init__(self) -> None:
        super().__init__()
        self.client = LogisticsClient(self)
        self.paid_storage_repo = LogisticsPaidStorageRepository()
        self.acceptance_repo = LogisticsAcceptanceReportRepository()
        self.transit_repo = LogisticsTransitTariffRepository()
        self.seller_warehouse_repo = SellerWarehouseRepository()
        self.seller_stock_repo = SellerWarehouseStockRepository()

    async def _token_configured(
        self, session, *, account_id: int, category: str
    ) -> bool:
        token_id = (
            await session.execute(
                select(WBAPIToken.id).where(
                    WBAPIToken.account_id == account_id,
                    WBAPIToken.category == category,
                    WBAPIToken.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        return token_id is not None

    @staticmethod
    def _window(
        *,
        backfill_from: date | None,
        backfill_to: date | None,
        default_days: int,
        max_days: int,
    ) -> tuple[date, date, bool]:
        today = utcnow().date()
        end = backfill_to or today
        start = backfill_from or (end - timedelta(days=default_days - 1))
        if start > end:
            start, end = end, start
        clamped = False
        if (end - start).days + 1 > max_days:
            start = end - timedelta(days=max_days - 1)
            clamped = True
        return start, end, clamped

    @staticmethod
    def _date_chunks(
        *, date_from: date, date_to: date, max_days: int
    ) -> list[tuple[date, date]]:
        chunks: list[tuple[date, date]] = []
        cursor = date_from
        while cursor <= date_to:
            chunk_to = min(cursor + timedelta(days=max_days - 1), date_to)
            chunks.append((cursor, chunk_to))
            cursor = chunk_to + timedelta(days=1)
        return chunks

    @staticmethod
    def _data(payload: Any) -> Any:
        if isinstance(payload, dict):
            data = payload.get("data")
            if data is not None:
                return data
        return payload

    @classmethod
    def _task_id(cls, payload: Any) -> str | None:
        data = cls._data(payload)
        if isinstance(data, dict):
            value = data.get("taskId") or data.get("id") or data.get("task_id")
            return str(value) if value else None
        if isinstance(payload, dict):
            value = payload.get("taskId") or payload.get("id") or payload.get("task_id")
            return str(value) if value else None
        return None

    @classmethod
    def _task_status(cls, payload: Any) -> str | None:
        data = cls._data(payload)
        status = None
        if isinstance(data, dict):
            status = data.get("status")
        if status is None and isinstance(payload, dict):
            status = payload.get("status")
        return str(status).casefold() if status is not None else None

    @staticmethod
    def _is_done(status: str | None) -> bool:
        return status in {"done", "ready", "completed", "complete", "success"}

    @staticmethod
    def _is_failed(status: str | None) -> bool:
        return status in {"failed", "error", "not_found", "notfound", "canceled"}

    @classmethod
    def _rows(cls, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("report", "reports", "data", "details", "items", "rows", "stocks"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
            if isinstance(value, dict):
                nested = cls._rows(value)
                if nested:
                    return nested
        return []

    @staticmethod
    def _first(payload: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in payload and payload.get(key) not in (None, ""):
                return payload.get(key)
        return None

    @classmethod
    def _text(cls, payload: dict[str, Any], *keys: str) -> str | None:
        value = cls._first(payload, *keys)
        if value in (None, ""):
            return None
        return str(value)

    @classmethod
    def _int(cls, payload: dict[str, Any], *keys: str) -> int | None:
        value = cls._first(payload, *keys)
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _decimal(cls, payload: dict[str, Any], *keys: str) -> Decimal | None:
        value = cls._first(payload, *keys)
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "."))
        except (InvalidOperation, ValueError):
            return None

    @classmethod
    def _date(cls, payload: dict[str, Any], *keys: str) -> date | None:
        value = cls._first(payload, *keys)
        if value in (None, ""):
            return None
        try:
            return parse_date(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            return parse_datetime(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _route_label(*parts: str | None) -> str | None:
        clean = [str(part).strip() for part in parts if str(part or "").strip()]
        return " -> ".join(clean) if clean else None

    async def _sync_async_report(
        self,
        session,
        *,
        account_id: int,
        cursor_key: str,
        date_from: date,
        date_to: date,
        create_call,
        status_call,
        download_call,
        report_label: str,
    ) -> tuple[str, str | None, list[dict[str, Any]], str | None]:
        cursor = await self._get_cursor(
            session, account_id=account_id, cursor_key=cursor_key
        )
        state = cursor.cursor_value if cursor is not None else {}
        task_id = None
        created_at = None
        if (
            state.get("dateFrom") == date_from.isoformat()
            and state.get("dateTo") == date_to.isoformat()
            and state.get("taskId")
            and not state.get("done")
        ):
            task_id = str(state.get("taskId"))
            created_at = state.get("createdAt")
        if task_id is None:
            created = await create_call(
                session,
                account_id=account_id,
                date_from=date_from.isoformat(),
                date_to=date_to.isoformat(),
            )
            task_id = self._task_id(created)
            created_at = utcnow().isoformat()
            if not task_id:
                await self._open_issue(
                    session,
                    account_id=account_id,
                    code=f"{report_label}_task_missing",
                    message=f"{report_label} task was created without task id",
                )
                return "failed", None, [], "task_missing"
            await self._set_cursor(
                session,
                account_id=account_id,
                cursor_key=cursor_key,
                cursor_value={
                    "taskId": task_id,
                    "createdAt": created_at,
                    "dateFrom": date_from.isoformat(),
                    "dateTo": date_to.isoformat(),
                    "done": False,
                },
                status="running",
            )

        status_payload = None
        status = None
        for attempt in range(self.REPORT_STATUS_POLL_ATTEMPTS):
            status_payload = await status_call(
                session, account_id=account_id, task_id=task_id
            )
            status = self._task_status(status_payload)
            if self._is_done(status) or self._is_failed(status):
                break
            if attempt + 1 < self.REPORT_STATUS_POLL_ATTEMPTS:
                await asyncio.sleep(self.REPORT_STATUS_POLL_SECONDS)

        if self._is_failed(status):
            await self._set_cursor(
                session,
                account_id=account_id,
                cursor_key=cursor_key,
                cursor_value={
                    "taskId": task_id,
                    "createdAt": created_at,
                    "dateFrom": date_from.isoformat(),
                    "dateTo": date_to.isoformat(),
                    "status": status,
                    "done": False,
                },
                status="failed",
            )
            await self._open_issue(
                session,
                account_id=account_id,
                code=f"{report_label}_task_failed",
                message=f"{report_label} task ended with status {status}",
                severity="warning",
                entity_key=task_id,
                payload=status_payload if isinstance(status_payload, dict) else None,
            )
            return "failed", task_id, [], status

        if not self._is_done(status):
            await self._set_cursor(
                session,
                account_id=account_id,
                cursor_key=cursor_key,
                cursor_value={
                    "taskId": task_id,
                    "createdAt": created_at,
                    "dateFrom": date_from.isoformat(),
                    "dateTo": date_to.isoformat(),
                    "status": status,
                    "done": False,
                },
                status="running",
            )
            await self._open_issue(
                session,
                account_id=account_id,
                code=f"{report_label}_task_not_ready",
                message=f"{report_label} task is still processing",
                severity="info",
                entity_key=task_id,
                payload=status_payload if isinstance(status_payload, dict) else None,
            )
            return "partial", task_id, [], status

        report_payload = await download_call(
            session, account_id=account_id, task_id=task_id
        )
        rows = self._rows(report_payload)
        completed_at = utcnow().isoformat()
        await self._set_cursor(
            session,
            account_id=account_id,
            cursor_key=cursor_key,
            cursor_value={
                "taskId": task_id,
                "createdAt": created_at,
                "completedAt": completed_at,
                "dateFrom": date_from.isoformat(),
                "dateTo": date_to.isoformat(),
                "status": status,
                "rows": len(rows),
                "done": True,
            },
            status="completed",
        )
        await self.dq_service.resolve_issues(
            session,
            domain=self.domain,
            account_id=account_id,
            codes=[f"{report_label}_task_not_ready", f"{report_label}_task_failed"],
        )
        return "completed", task_id, rows, status

    def _paid_storage_row(
        self,
        *,
        account_id: int,
        task_id: str | None,
        item: dict[str, Any],
        fallback_date: date,
        index: int,
    ) -> dict[str, Any]:
        report_date = (
            self._date(item, "date", "reportDate", "dateFrom", "originalDate")
            or fallback_date
        )
        amount = self._decimal(
            item,
            "warehousePrice",
            "storageCost",
            "paidStorage",
            "total",
            "sum",
            "amount",
            "price",
        )
        return {
            "account_id": account_id,
            "report_date": report_date,
            "nm_id": self._int(item, "nmId", "nmID", "nm_id"),
            "vendor_code": self._text(item, "vendorCode", "supplierArticle", "sa"),
            "barcode": self._text(item, "barcode", "sku"),
            "title": self._text(item, "title", "name"),
            "brand": self._text(item, "brand", "brandName"),
            "subject_name": self._text(item, "subjectName", "subject", "category"),
            "warehouse_name": self._text(
                item, "warehouse", "warehouseName", "officeName"
            ),
            "quantity": self._decimal(
                item, "quantity", "qty", "count", "barcodesCount"
            ),
            "amount": amount,
            "storage_cost": amount,
            "currency": self._text(item, "currency", "currencyCode"),
            "task_id": task_id,
            "source_row_key": str(
                self._first(item, "id", "giId", "chrtId", "nmId", "nmID") or index
            ),
            "payload": item,
        }

    def _acceptance_row(
        self,
        *,
        account_id: int,
        task_id: str | None,
        item: dict[str, Any],
        fallback_date: date,
        index: int,
    ) -> dict[str, Any]:
        operation_date = (
            self._date(
                item,
                "date",
                "operationDate",
                "reportDate",
                "giCreateDate",
                "shkCreateDate",
            )
            or fallback_date
        )
        amount = self._decimal(
            item, "total", "sum", "amount", "acceptanceCost", "paidAcceptance"
        )
        return {
            "account_id": account_id,
            "operation_date": operation_date,
            "nm_id": self._int(item, "nmID", "nmId", "nm_id"),
            "vendor_code": self._text(item, "vendorCode", "supplierArticle", "sa"),
            "barcode": self._text(item, "barcode", "sku"),
            "title": self._text(item, "title", "name"),
            "brand": self._text(item, "brand", "brandName"),
            "subject_name": self._text(item, "subjectName", "subject", "category"),
            "warehouse_name": self._text(
                item, "warehouse", "warehouseName", "officeName"
            ),
            "operation_name": self._text(
                item, "operationName", "operation", "calcType", "type"
            ),
            "quantity": self._decimal(item, "quantity", "qty", "count"),
            "amount": amount,
            "acceptance_cost": amount,
            "currency": self._text(item, "currency", "currencyCode"),
            "task_id": task_id,
            "source_row_key": str(
                self._first(item, "id", "incomeId", "shkId", "nmID", "nmId") or index
            ),
            "payload": item,
        }

    def _transit_row(
        self,
        *,
        account_id: int,
        collected_at,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        source_name = self._text(
            item,
            "sourceWarehouseName",
            "fromWarehouseName",
            "warehouseNameFrom",
            "warehouseFrom",
            "srcWarehouseName",
        )
        transit_name = self._text(
            item,
            "transitWarehouseName",
            "transitWarehouse",
            "viaWarehouseName",
            "middleWarehouseName",
        )
        destination_name = self._text(
            item,
            "destinationWarehouseName",
            "destWarehouseName",
            "toWarehouseName",
            "warehouseNameTo",
            "warehouseTo",
        )
        return {
            "account_id": account_id,
            "collected_at": collected_at,
            "source_warehouse_id": self._int(
                item,
                "sourceWarehouseID",
                "sourceWarehouseId",
                "fromWarehouseID",
                "fromWarehouseId",
                "warehouseIDFrom",
                "warehouseIdFrom",
            ),
            "source_warehouse_name": source_name,
            "transit_warehouse_id": self._int(
                item,
                "transitWarehouseID",
                "transitWarehouseId",
                "viaWarehouseID",
                "viaWarehouseId",
            ),
            "transit_warehouse_name": transit_name,
            "destination_warehouse_id": self._int(
                item,
                "destinationWarehouseID",
                "destinationWarehouseId",
                "destWarehouseID",
                "destWarehouseId",
                "toWarehouseID",
                "toWarehouseId",
                "warehouseIDTo",
                "warehouseIdTo",
            ),
            "destination_warehouse_name": destination_name,
            "box_type_id": self._int(item, "boxTypeID", "boxTypeId"),
            "coefficient": self._text(
                item, "coefficient", "warehouseCoef", "logWarehouseCoef"
            ),
            "delivery_base": self._decimal(
                item, "deliveryBase", "boxDeliveryBase", "basePrice"
            ),
            "delivery_liter": self._decimal(
                item, "deliveryLiter", "boxDeliveryLiter", "literPrice"
            ),
            "amount": self._decimal(
                item, "amount", "total", "price", "tariff", "deliveryPrice", "cost"
            ),
            "currency": self._text(item, "currency", "currencyCode"),
            "transit_time_days": self._decimal(
                item, "transitTime", "deliveryTime", "days", "durationDays"
            ),
            "route_label": self._route_label(
                source_name, transit_name, destination_name
            ),
            "payload": item,
        }

    async def _sync_paid_storage(
        self,
        session,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        cursor_key: str | None = None,
    ) -> dict[str, Any]:
        status, task_id, rows, task_status = await self._sync_async_report(
            session,
            account_id=account_id,
            cursor_key=cursor_key or self.PAID_STORAGE_CURSOR_KEY,
            date_from=date_from,
            date_to=date_to,
            create_call=self.client.create_paid_storage_report,
            status_call=self.client.paid_storage_status,
            download_call=self.client.paid_storage_download,
            report_label="paid_storage",
        )
        if status != "completed":
            return {
                "status": status,
                "rows": 0,
                "taskId": task_id,
                "taskStatus": task_status,
            }
        await session.execute(
            delete(WBLogisticsPaidStorageRow).where(
                WBLogisticsPaidStorageRow.account_id == account_id,
                WBLogisticsPaidStorageRow.report_date >= date_from,
                WBLogisticsPaidStorageRow.report_date <= date_to,
            )
        )
        normalized = [
            self._paid_storage_row(
                account_id=account_id,
                task_id=task_id,
                item=item,
                fallback_date=date_from,
                index=index,
            )
            for index, item in enumerate(rows, start=1)
        ]
        await self.paid_storage_repo.upsert_many(
            session, normalized, conflict_fields=["dedupe_key"]
        )
        return {"status": "completed", "rows": len(normalized), "taskId": task_id}

    async def _sync_acceptance(
        self,
        session,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        status, task_id, rows, task_status = await self._sync_async_report(
            session,
            account_id=account_id,
            cursor_key=self.ACCEPTANCE_CURSOR_KEY,
            date_from=date_from,
            date_to=date_to,
            create_call=self.client.create_acceptance_report,
            status_call=self.client.acceptance_report_status,
            download_call=self.client.acceptance_report_download,
            report_label="acceptance_report",
        )
        if status != "completed":
            return {
                "status": status,
                "rows": 0,
                "taskId": task_id,
                "taskStatus": task_status,
            }
        await session.execute(
            delete(WBLogisticsAcceptanceReportRow).where(
                WBLogisticsAcceptanceReportRow.account_id == account_id,
                WBLogisticsAcceptanceReportRow.operation_date >= date_from,
                WBLogisticsAcceptanceReportRow.operation_date <= date_to,
            )
        )
        normalized = [
            self._acceptance_row(
                account_id=account_id,
                task_id=task_id,
                item=item,
                fallback_date=date_from,
                index=index,
            )
            for index, item in enumerate(rows, start=1)
        ]
        await self.acceptance_repo.upsert_many(
            session, normalized, conflict_fields=["dedupe_key"]
        )
        return {"status": "completed", "rows": len(normalized), "taskId": task_id}

    async def _sync_transit_tariffs(
        self, session, *, account_id: int
    ) -> dict[str, Any]:
        if not await self._token_configured(
            session, account_id=account_id, category=WBAPICategory.SUPPLIES.value
        ):
            await self._open_issue(
                session,
                account_id=account_id,
                code="logistics_supplies_token_missing",
                message="Supplies token is required for transit tariff sync",
                severity="info",
            )
            return {"status": "skipped", "rows": 0, "reason": "supplies_token_missing"}
        payload = await self.client.transit_tariffs(session, account_id=account_id)
        rows = self._rows(payload)
        collected_at = utcnow()
        await session.execute(
            delete(WBLogisticsTransitTariff).where(
                WBLogisticsTransitTariff.account_id == account_id
            )
        )
        normalized = [
            self._transit_row(
                account_id=account_id, collected_at=collected_at, item=item
            )
            for item in rows
        ]
        await self.transit_repo.upsert_many(
            session, normalized, conflict_fields=["dedupe_key"]
        )
        return {"status": "completed", "rows": len(normalized)}

    async def _chrt_candidates(self, session, *, account_id: int) -> dict[int, CoreSKU]:
        candidates: dict[int, CoreSKU] = {}
        rows = (
            (
                await session.execute(
                    select(CoreSKU)
                    .where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.chrt_id.is_not(None),
                        CoreSKU.is_active.is_(True),
                    )
                    .order_by(CoreSKU.updated_at.desc(), CoreSKU.id.desc())
                    .limit(self.MARKETPLACE_STOCK_CHUNK_SIZE)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if row.chrt_id is not None:
                candidates[int(row.chrt_id)] = row
        return candidates

    async def _sync_seller_warehouses(
        self, session, *, account_id: int
    ) -> dict[str, Any]:
        if not await self._token_configured(
            session, account_id=account_id, category=WBAPICategory.MARKETPLACE.value
        ):
            await self._open_issue(
                session,
                account_id=account_id,
                code="logistics_marketplace_token_missing",
                message=(
                    "Marketplace token is required for seller warehouses "
                    "and FBS/DBW stocks"
                ),
                severity="info",
            )
            return {
                "status": "skipped",
                "warehouses": 0,
                "stocks": 0,
                "reason": "marketplace_token_missing",
            }
        payload = await self.client.seller_warehouses(session, account_id=account_id)
        warehouse_items = self._rows(payload)
        warehouses = []
        warehouse_names: dict[int, str | None] = {}
        for item in warehouse_items:
            warehouse_id = self._int(item, "id", "warehouseId", "warehouseID")
            if warehouse_id is None:
                continue
            name = self._text(item, "name", "warehouseName")
            warehouse_names[warehouse_id] = name
            is_active = None
            if "isDeleting" in item:
                is_active = not bool(item.get("isDeleting"))
            elif "isActive" in item:
                is_active = bool(item.get("isActive"))
            warehouses.append(
                {
                    "account_id": account_id,
                    "warehouse_id": warehouse_id,
                    "name": name,
                    "office_id": self._int(item, "officeId", "officeID"),
                    "delivery_type": self._text(item, "deliveryType"),
                    "cargo_type": self._text(item, "cargoType"),
                    "address": self._text(item, "address"),
                    "is_active": is_active,
                    "payload": item,
                }
            )
        await self.seller_warehouse_repo.upsert_many(
            session, warehouses, conflict_fields=["account_id", "warehouse_id"]
        )

        candidates = await self._chrt_candidates(session, account_id=account_id)
        if not candidates:
            await self._open_issue(
                session,
                account_id=account_id,
                code="logistics_marketplace_stock_candidates_missing",
                message=(
                    "No active CoreSKU chrt_id values were found for FBS/DBW stock sync"
                ),
                severity="info",
            )
            return {
                "status": "completed",
                "warehouses": len(warehouses),
                "stocks": 0,
                "reason": "chrt_candidates_missing",
            }
        chrt_ids = list(candidates.keys())
        stock_rows: list[dict[str, Any]] = []
        for warehouse_id, warehouse_name in warehouse_names.items():
            await session.execute(
                delete(WBSellerWarehouseStock).where(
                    WBSellerWarehouseStock.account_id == account_id,
                    WBSellerWarehouseStock.warehouse_id == warehouse_id,
                )
            )
            for offset in range(0, len(chrt_ids), self.MARKETPLACE_STOCK_CHUNK_SIZE):
                chunk = chrt_ids[offset : offset + self.MARKETPLACE_STOCK_CHUNK_SIZE]
                stock_payload = await self.client.seller_stocks(
                    session,
                    account_id=account_id,
                    warehouse_id=warehouse_id,
                    chrt_ids=chunk,
                )
                for item in self._rows(stock_payload):
                    chrt_id = self._int(item, "chrtId", "chrtID")
                    if chrt_id is None:
                        continue
                    sku = candidates.get(chrt_id)
                    amount = self._decimal(item, "amount", "quantity", "qty")
                    stock_rows.append(
                        {
                            "account_id": account_id,
                            "warehouse_id": warehouse_id,
                            "warehouse_name": warehouse_name,
                            "chrt_id": chrt_id,
                            "nm_id": self._int(item, "nmId", "nmID")
                            or (sku.nm_id if sku is not None else None),
                            "vendor_code": self._text(item, "vendorCode")
                            or (sku.vendor_code if sku is not None else None),
                            "barcode": self._text(item, "barcode", "sku")
                            or (sku.barcode if sku is not None else None),
                            "quantity": amount,
                            "reserved": self._decimal(item, "reserved", "reservedQty"),
                            "in_way": self._decimal(item, "inWay", "inWayQty"),
                            "updated_at_wb": self._datetime(item.get("updatedAt")),
                            "payload": item,
                        }
                    )
        await self.seller_stock_repo.upsert_many(
            session,
            stock_rows,
            conflict_fields=["account_id", "warehouse_id", "chrt_id"],
        )
        return {
            "status": "completed",
            "warehouses": len(warehouses),
            "stocks": len(stock_rows),
        }

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        paid_from, paid_to, paid_clamped = self._window(
            backfill_from=backfill_from,
            backfill_to=backfill_to,
            default_days=self.PAID_STORAGE_WINDOW_DAYS,
            max_days=self.PAID_STORAGE_WINDOW_DAYS,
        )
        acceptance_from, acceptance_to, acceptance_clamped = self._window(
            backfill_from=backfill_from,
            backfill_to=backfill_to,
            default_days=self.ACCEPTANCE_WINDOW_DAYS,
            max_days=self.ACCEPTANCE_WINDOW_DAYS,
        )
        if paid_clamped or acceptance_clamped:
            await self._open_issue(
                session,
                account_id=account.id,
                code="logistics_window_clamped_to_wb_limits",
                message="Logistics report windows were clamped to WB API limits",
                severity="info",
                payload={
                    "paidStorage": {
                        "dateFrom": paid_from.isoformat(),
                        "dateTo": paid_to.isoformat(),
                        "maxDays": self.PAID_STORAGE_WINDOW_DAYS,
                        "chunkDays": self.PAID_STORAGE_CHUNK_DAYS,
                    },
                    "acceptanceReport": {
                        "dateFrom": acceptance_from.isoformat(),
                        "dateTo": acceptance_to.isoformat(),
                        "maxDays": self.ACCEPTANCE_WINDOW_DAYS,
                    },
                },
            )

        await self._progress(stage="logistics_paid_storage", progress_percent=20)
        paid_storage_chunks = []
        paid_storage_rows = 0
        for chunk_from, chunk_to in self._date_chunks(
            date_from=paid_from,
            date_to=paid_to,
            max_days=self.PAID_STORAGE_CHUNK_DAYS,
        ):
            chunk = await self._sync_paid_storage(
                session,
                account_id=account.id,
                date_from=chunk_from,
                date_to=chunk_to,
                cursor_key=(
                    f"{self.PAID_STORAGE_CURSOR_KEY}:"
                    f"{chunk_from.isoformat()}:{chunk_to.isoformat()}"
                ),
            )
            chunk["dateFrom"] = chunk_from.isoformat()
            chunk["dateTo"] = chunk_to.isoformat()
            paid_storage_chunks.append(chunk)
            paid_storage_rows += int(chunk.get("rows") or 0)
        paid_storage_status = (
            "failed"
            if any(item.get("status") == "failed" for item in paid_storage_chunks)
            else "partial"
            if any(item.get("status") == "partial" for item in paid_storage_chunks)
            else "completed"
        )
        paid_storage = {
            "status": paid_storage_status,
            "rows": paid_storage_rows,
            "chunks": paid_storage_chunks,
        }
        await self._progress(stage="logistics_acceptance_report", progress_percent=45)
        acceptance = await self._sync_acceptance(
            session,
            account_id=account.id,
            date_from=acceptance_from,
            date_to=acceptance_to,
        )
        await self._progress(stage="logistics_transit_tariffs", progress_percent=70)
        transit = await self._sync_transit_tariffs(session, account_id=account.id)
        await self._progress(stage="logistics_seller_warehouses", progress_percent=88)
        seller_warehouses = await self._sync_seller_warehouses(
            session, account_id=account.id
        )

        has_partial = any(
            item.get("status") in {"partial", "failed"}
            for item in (paid_storage, acceptance, transit, seller_warehouses)
        )
        details = {
            "paidStorage": paid_storage,
            "acceptanceReport": acceptance,
            "transitTariffs": transit,
            "sellerWarehouses": seller_warehouses,
            "windows": {
                "paidStorage": {
                    "dateFrom": paid_from.isoformat(),
                    "dateTo": paid_to.isoformat(),
                    "chunkDays": self.PAID_STORAGE_CHUNK_DAYS,
                },
                "acceptanceReport": {
                    "dateFrom": acceptance_from.isoformat(),
                    "dateTo": acceptance_to.isoformat(),
                },
            },
        }
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value=details,
            status="partial" if has_partial else "completed",
        )
        await self._progress(stage="logistics_done", progress_percent=100)
        return {
            "status": "partial" if has_partial else "completed",
            "rows": int(paid_storage.get("rows") or 0)
            + int(acceptance.get("rows") or 0)
            + int(transit.get("rows") or 0)
            + int(seller_warehouses.get("warehouses") or 0)
            + int(seller_warehouses.get("stocks") or 0),
            **details,
        }
