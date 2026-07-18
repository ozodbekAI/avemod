from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.core.http import WBAPIError
from app.modules.prices.client import PricesClient
from app.models.prices import (
    WBPriceQuarantine,
    WBPriceSize,
    WBPriceSnapshot,
    WBPriceUploadTaskRow,
)
from app.repositories.prices import (
    PriceQuarantineRepository,
    PriceRepository,
    PriceSizeRepository,
    PriceSnapshotRepository,
    PriceUploadTaskRepository,
)


class PricesSyncService(DomainSyncBase):
    domain = "prices"
    category = "prices"
    STATE_PROBE_UPLOAD_ID = 1

    def __init__(self) -> None:
        super().__init__()
        self.client = PricesClient(self)
        self.repo = PriceRepository()
        self.snapshots = PriceSnapshotRepository()
        self.size_repo = PriceSizeRepository()
        self.tasks_repo = PriceUploadTaskRepository()
        self.quarantine_repo = PriceQuarantineRepository()

    @staticmethod
    def _extract_task_data(payload):
        if not isinstance(payload, dict):
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    @staticmethod
    def _price_size_row(
        *,
        account_id: int,
        item: dict,
        size: dict,
    ) -> dict | None:
        nm_id = size.get("nmID") if size.get("nmID") is not None else size.get("nmId")
        if nm_id is None:
            nm_id = (
                item.get("nmID") if item.get("nmID") is not None else item.get("nmId")
            )
        size_id = (
            size.get("sizeID") if size.get("sizeID") is not None else size.get("sizeId")
        )
        discounted_price = (
            size.get("discountedPrice")
            if size.get("discountedPrice") is not None
            else size.get("discounted_price")
        )
        club_discounted_price = (
            size.get("clubDiscountedPrice")
            if size.get("clubDiscountedPrice") is not None
            else size.get("club_discounted_price")
        )
        if nm_id is None or size_id is None:
            return None
        return {
            "account_id": account_id,
            "nm_id": nm_id,
            "size_id": size_id,
            "vendor_code": size.get("vendorCode")
            if size.get("vendorCode") is not None
            else item.get("vendorCode"),
            "tech_size_name": size.get("techSizeName")
            if size.get("techSizeName") is not None
            else size.get("techSize"),
            "price": size.get("price"),
            "discounted_price": discounted_price,
            "club_discounted_price": club_discounted_price,
            "discount": size.get("discount")
            if size.get("discount") is not None
            else item.get("discount"),
            "club_discount": size.get("clubDiscount")
            if size.get("clubDiscount") is not None
            else item.get("clubDiscount"),
            "payload": size,
        }

    async def _sync_upload_state(
        self, session: AsyncSession, *, account_id: int, source: str
    ) -> None:
        if source == "processed":
            state_payload = await self.client.processed_tasks(
                session,
                account_id=account_id,
                upload_id=self.STATE_PROBE_UPLOAD_ID,
            )
            details_loader = self.client.processed_task_goods
            rows_key = "historyGoods"
            issue_code = "prices_processed_history_unavailable"
        else:
            state_payload = await self.client.unprocessed_tasks(
                session,
                account_id=account_id,
                upload_id=self.STATE_PROBE_UPLOAD_ID,
            )
            details_loader = self.client.unprocessed_task_goods
            rows_key = "bufferGoods"
            issue_code = "prices_buffer_history_unavailable"

        state_data = self._extract_task_data(state_payload)
        if state_data is None:
            await self.dq_service.resolve_issues(
                session,
                domain=self.domain,
                codes=[issue_code],
                account_id=account_id,
            )
            return

        upload_id = state_data.get("uploadID") or state_data.get("uploadId")
        if upload_id is None:
            await self.dq_service.resolve_issues(
                session,
                domain=self.domain,
                codes=[issue_code],
                account_id=account_id,
            )
            return

        task_key = str(upload_id)
        await self.tasks_repo.upsert_many(
            session,
            [
                {
                    "account_id": account_id,
                    "source": source,
                    "task_key": task_key,
                    "status": str(state_data.get("status"))
                    if state_data.get("status") is not None
                    else None,
                    "payload": state_payload,
                }
            ],
            conflict_fields=["account_id", "source", "task_key"],
        )

        task_rows = []
        offset = 0
        limit = 1000
        while True:
            details_payload = await details_loader(
                session,
                account_id=account_id,
                upload_id=int(upload_id),
                limit=limit,
                offset=offset,
            )
            details_data = self._extract_task_data(details_payload) or {}
            items = details_data.get(rows_key) or []
            if not items:
                break
            for item in items:
                task_rows.append(
                    {
                        "upload_task_id": None,
                        "account_id": account_id,
                        "nm_id": item.get("nmID") or item.get("nmId"),
                        "vendor_code": item.get("vendorCode"),
                        "error_text": item.get("errorText"),
                        "payload": item | {"uploadID": upload_id, "source": source},
                    }
                )
            if len(items) < limit:
                break
            offset += limit

        if task_rows:
            upload_task = await self.tasks_repo.get_by_unique(
                session,
                account_id=account_id,
                source=source,
                task_key=task_key,
            )
            if upload_task is not None:
                await session.execute(
                    delete(WBPriceUploadTaskRow).where(
                        WBPriceUploadTaskRow.upload_task_id == upload_task.id
                    )
                )
                for row in task_rows:
                    row["upload_task_id"] = upload_task.id
                    session.add(WBPriceUploadTaskRow(**row))

        await self.dq_service.resolve_issues(
            session,
            domain=self.domain,
            codes=[issue_code],
            account_id=account_id,
        )

    async def run(
        self,
        session: AsyncSession,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        offset = 0
        limit = 1000
        total_rows = 0
        while True:
            payload = await self.client.list_goods(
                session, account_id=account.id, limit=limit, offset=offset
            )
            items = payload.get("data", {}).get("listGoods", [])
            if not items:
                break
            rows = []
            snapshot_rows = []
            batch_nm_ids = []
            batch_size_rows = []
            editable_nm_ids = []
            for item in items:
                nm_id = item.get("nmID")
                rows.append(
                    {
                        "account_id": account.id,
                        "nm_id": nm_id,
                        "vendor_code": item.get("vendorCode"),
                        "currency_iso_code": item.get("currencyIsoCode4217"),
                        "discount": item.get("discount"),
                        "club_discount": item.get("clubDiscount"),
                        "editable_size_price": item.get("editableSizePrice"),
                        "is_bad_turnover": item.get("isBadTurnover"),
                        "payload": item,
                    }
                )
                snapshot_rows.append(
                    {
                        "account_id": account.id,
                        "nm_id": nm_id,
                        "vendor_code": item.get("vendorCode"),
                        "snapshot_at": utcnow(),
                        "payload": item,
                    }
                )
                if nm_id is not None:
                    batch_nm_ids.append(nm_id)
                    for size in item.get("sizes") or []:
                        if not isinstance(size, dict):
                            continue
                        size_row = self._price_size_row(
                            account_id=account.id, item=item, size=size
                        )
                        if size_row is not None:
                            batch_size_rows.append(size_row)
                if item.get("editableSizePrice"):
                    editable_nm_ids.append(nm_id)
            await self.repo.upsert_many(
                session, rows, conflict_fields=["account_id", "nm_id"]
            )
            for snapshot in snapshot_rows:
                session.add(WBPriceSnapshot(**snapshot))
            if batch_nm_ids:
                await session.execute(
                    delete(WBPriceSize).where(
                        WBPriceSize.account_id == account.id,
                        WBPriceSize.nm_id.in_(batch_nm_ids),
                    )
                )
                for row in batch_size_rows:
                    session.add(WBPriceSize(**row))
            for nm_id in editable_nm_ids:
                if nm_id is None:
                    continue
                size_payload = await self.client.list_sizes(
                    session, account_id=account.id, nm_id=nm_id
                )
                size_rows = size_payload.get("data", {}).get("listGoods", [])
                await session.execute(
                    delete(WBPriceSize).where(
                        WBPriceSize.account_id == account.id,
                        WBPriceSize.nm_id == nm_id,
                    )
                )
                for size in size_rows:
                    if not isinstance(size, dict):
                        continue
                    size_row = self._price_size_row(
                        account_id=account.id, item={"nmID": nm_id}, size=size
                    )
                    if size_row is not None:
                        session.add(WBPriceSize(**size_row))
            total_rows += len(items)
            if len(items) < limit:
                break
            offset += limit
        for source in ("processed", "buffer"):
            try:
                await self._sync_upload_state(
                    session, account_id=account.id, source=source
                )
            except WBAPIError as exc:
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code=f"prices_{source}_history_unavailable",
                    message=str(exc),
                    severity="info",
                )
        try:
            await session.execute(
                delete(WBPriceQuarantine).where(
                    WBPriceQuarantine.account_id == account.id
                )
            )
            offset = 0
            limit = 1000
            quarantine_items = []
            while True:
                quarantine_payload = await self.client.quarantine_goods(
                    session,
                    account_id=account.id,
                    limit=limit,
                    offset=offset,
                )
                data = (
                    quarantine_payload.get("data")
                    if isinstance(quarantine_payload, dict)
                    else None
                )
                items = []
                if isinstance(data, dict):
                    items = data.get("quarantineGoods") or []
                elif isinstance(quarantine_payload, dict):
                    items = quarantine_payload.get("goods") or []
                if not items:
                    break
                quarantine_items.extend(items)
                if len(items) < limit:
                    break
                offset += limit
            for item in quarantine_items:
                session.add(
                    WBPriceQuarantine(
                        account_id=account.id,
                        nm_id=item.get("nmID") or item.get("nmId"),
                        vendor_code=item.get("vendorCode"),
                        snapshot_at=utcnow(),
                        payload=item,
                    )
                )
            await self.dq_service.resolve_issues(
                session,
                domain=self.domain,
                codes=["prices_quarantine_unavailable"],
                account_id=account.id,
            )
        except WBAPIError as exc:
            await self._open_issue(
                session,
                account_id=account.id,
                code="prices_quarantine_unavailable",
                message=str(exc),
                severity="info",
            )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={"lastRunAt": utcnow().isoformat()},
        )
        return {"status": "completed", "rows": total_rows}
