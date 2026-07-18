from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from app.core.config import get_settings
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.repositories.stocks import StockSnapshotRepository
from app.modules.stocks.client import StocksClient


class StocksSyncService(DomainSyncBase):
    domain = "stocks"
    category = "analytics"
    PENDING_CURSOR_KEY = "pending_task"
    PENDING_TASK_MAX_AGE_HOURS = get_settings().stocks_pending_task_max_age_hours

    def __init__(self) -> None:
        super().__init__()
        self.client = StocksClient(self)
        self.repo = StockSnapshotRepository()

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        pending_cursor = await self._get_cursor(
            session,
            account_id=account.id,
            cursor_key=self.PENDING_CURSOR_KEY,
        )
        pending_payload = pending_cursor.cursor_value if pending_cursor else {}
        task_id = pending_payload.get("taskId")
        created_at = pending_payload.get("createdAt")
        status_payload = None
        if task_id:
            created_at_dt = None
            if created_at:
                try:
                    created_at_dt = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                except ValueError:
                    created_at_dt = None
            if created_at_dt is not None and utcnow() - created_at_dt > timedelta(
                hours=self.PENDING_TASK_MAX_AGE_HOURS
            ):
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="stocks_task_failed",
                    message="Pending warehouse remains task exceeded max pending age and will be recreated",
                    severity="warning",
                    entity_key=task_id,
                    payload={
                        "taskId": task_id,
                        "createdAt": created_at,
                        "maxAgeHours": self.PENDING_TASK_MAX_AGE_HOURS,
                    },
                )
                task_id = None
            status = None
            if task_id is not None:
                status_payload = await self.client.task_status(
                    session, account_id=account.id, task_id=task_id
                )
                status = (
                    (status_payload if isinstance(status_payload, dict) else {})
                    .get("data", {})
                    .get("status")
                )
            if task_id is not None and status in {"failed", "not_found"}:
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="stocks_task_failed",
                    message=f"Pending warehouse remains task ended with status {status}",
                    severity="warning",
                    entity_key=task_id,
                )
                task_id = None
            elif task_id is not None and status != "done":
                await self._set_cursor(
                    session,
                    account_id=account.id,
                    cursor_key=self.PENDING_CURSOR_KEY,
                    cursor_value={"taskId": task_id, "createdAt": created_at},
                    status="running",
                )
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="stocks_task_not_ready",
                    message="Warehouse remains task is still processing",
                    severity="info",
                    entity_key=task_id,
                )
                return {
                    "status": "partial",
                    "rows": 0,
                    "taskId": task_id,
                    "reason": "pending_task_not_ready",
                }
        if not task_id:
            created = await self.client.create_warehouse_remains_task(
                session, account_id=account.id
            )
            created_payload = created if isinstance(created, dict) else {}
            task_id = created_payload.get("data", {}).get(
                "taskId"
            ) or created_payload.get("taskId")
            if not task_id:
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="stocks_task_missing",
                    message="Warehouse remains task was created without task id",
                )
                return {"status": "failed", "rows": 0}
            created_at = utcnow().isoformat()
            await self._set_cursor(
                session,
                account_id=account.id,
                cursor_key=self.PENDING_CURSOR_KEY,
                cursor_value={"taskId": task_id, "createdAt": created_at},
                status="running",
            )
        for _ in range(6):
            status_payload = await self.client.task_status(
                session, account_id=account.id, task_id=task_id
            )
            status_data = status_payload if isinstance(status_payload, dict) else {}
            if status_data.get("data", {}).get("status") == "done":
                break
            await asyncio.sleep(2)
        status_data = status_payload if isinstance(status_payload, dict) else {}
        if status_data.get("data", {}).get("status") != "done":
            await self._set_cursor(
                session,
                account_id=account.id,
                cursor_key=self.PENDING_CURSOR_KEY,
                cursor_value={"taskId": task_id, "createdAt": created_at},
                status="running",
            )
            await self._open_issue(
                session,
                account_id=account.id,
                code="stocks_task_not_ready",
                message="Warehouse remains task is still processing after polling window",
                severity="info",
                entity_key=task_id,
            )
            return {
                "status": "partial",
                "rows": 0,
                "taskId": task_id,
                "reason": "task_not_ready_after_poll",
            }
        report_payload = await self.client.download_report(
            session, account_id=account.id, task_id=task_id
        )
        snapshot = WBStockSnapshot(
            account_id=account.id,
            snapshot_at=utcnow(),
            task_id=task_id,
            payload=report_payload
            if isinstance(report_payload, dict)
            else {"report": report_payload},
        )
        session.add(snapshot)
        await session.flush()
        rows = report_payload
        if isinstance(report_payload, dict):
            rows = report_payload.get("data") or report_payload.get("report") or []
        if not isinstance(rows, list):
            rows = []
        for item in rows:
            warehouses = item.get("warehouses") if isinstance(item, dict) else None
            if isinstance(warehouses, list) and warehouses:
                for warehouse in warehouses:
                    warehouse_name = warehouse.get("warehouseName")
                    quantity = warehouse.get("quantity")
                    session.add(
                        WBStockSnapshotRow(
                            snapshot_id=snapshot.id,
                            account_id=account.id,
                            nm_id=item.get("nmId") or item.get("nmID"),
                            barcode=item.get("barcode"),
                            warehouse_name=warehouse_name,
                            quantity=None
                            if warehouse_name
                            in {
                                "В пути до получателей",
                                "В пути возвраты на склад WB",
                                "Всего находится на складах",
                            }
                            else quantity,
                            quantity_full=quantity
                            if warehouse_name == "Всего находится на складах"
                            else None,
                            in_way_to_client=quantity
                            if warehouse_name == "В пути до получателей"
                            else None,
                            in_way_from_client=quantity
                            if warehouse_name == "В пути возвраты на склад WB"
                            else None,
                            payload={"item": item, "warehouse": warehouse},
                        )
                    )
                continue
            session.add(
                WBStockSnapshotRow(
                    snapshot_id=snapshot.id,
                    account_id=account.id,
                    nm_id=item.get("nmId") or item.get("nmID"),
                    barcode=item.get("barcode"),
                    chrt_id=item.get("chrtID"),
                    size_id=item.get("sizeID"),
                    warehouse_id=item.get("warehouseID") or item.get("warehouseId"),
                    warehouse_name=item.get("warehouseName"),
                    quantity=item.get("quantity"),
                    quantity_full=item.get("quantityFull"),
                    in_way_to_client=item.get("inWayToClient"),
                    in_way_from_client=item.get("inWayFromClient"),
                    subject=item.get("subject") or item.get("subjectName"),
                    brand=item.get("brand"),
                    payload=item,
                )
            )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={
                "taskId": task_id,
                "snapshotAt": snapshot.snapshot_at.isoformat(),
            },
        )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_key=self.PENDING_CURSOR_KEY,
            cursor_value={
                "taskId": task_id,
                "createdAt": created_at,
                "completedAt": snapshot.snapshot_at.isoformat(),
            },
            status="completed",
        )
        await self.dq_service.resolve_issues(
            session,
            domain=self.domain,
            codes=["stocks_task_not_ready", "stocks_task_failed"],
            account_id=account.id,
        )
        return {"status": "completed", "rows": len(rows), "taskId": task_id}
