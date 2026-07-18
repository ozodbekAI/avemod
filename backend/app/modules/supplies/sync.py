from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import and_, delete, or_, select, tuple_

from app.core.parsing import parse_datetime
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.models.product_cards import CoreSKU
from app.models.orders import WBOrder
from app.models.sales import WBSale
from app.models.stocks import WBStockSnapshotRow
from app.modules.supplies.client import SuppliesClient
from app.models.supplies import (
    WBSupply,
    WBSupplyAcceptanceOption,
    WBSupplyGood,
    WBSupplyPackage,
)
from app.repositories.supplies import (
    SupplyAcceptanceOptionRepository,
    SupplyRepository,
    SupplyWarehouseRepository,
)


class SuppliesSyncService(DomainSyncBase):
    domain = "supplies"
    category = "supplies"
    ENRICHMENT_BATCH_SIZE = 25
    MAX_ENRICHMENT_BATCHES_PER_RUN = 4
    REQUEST_PAUSE_SECONDS = 0.35

    def __init__(self) -> None:
        super().__init__()
        self.client = SuppliesClient(self)
        self.repo = SupplyRepository()
        self.warehouses = SupplyWarehouseRepository()
        self.acceptance = SupplyAcceptanceOptionRepository()

    async def _pause(self) -> None:
        await asyncio.sleep(self.REQUEST_PAUSE_SECONDS)

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        return "429" in str(exc) and "Too Many Requests" in str(exc)

    async def _sync_headers(self, session, *, account_id: int) -> int:
        normalized = []
        offset = 0
        limit = 1000
        while True:
            supplies_payload = await self.client.supplies(
                session,
                account_id=account_id,
                limit=limit,
                offset=offset,
            )
            supply_items = (
                supplies_payload
                if isinstance(supplies_payload, list)
                else supplies_payload.get("supplies")
                or supplies_payload.get("data")
                or []
            )
            if not isinstance(supply_items, list) or not supply_items:
                break
            for item in supply_items:
                supply_id = item.get("supplyID") or item.get("ID") or item.get("id")
                if supply_id is None:
                    continue
                normalized.append(
                    {
                        "account_id": account_id,
                        "supply_id": supply_id,
                        "preorder_id": item.get("preorderID"),
                        "create_date": parse_datetime(item.get("createDate")),
                        "supply_date": parse_datetime(item.get("supplyDate")),
                        "fact_date": parse_datetime(item.get("factDate")),
                        "updated_date": parse_datetime(item.get("updatedDate")),
                        "status_id": item.get("statusID"),
                        "warehouse_id": item.get("warehouseID"),
                        "warehouse_name": item.get("warehouseName"),
                        "actual_warehouse_id": item.get("actualWarehouseID"),
                        "actual_warehouse_name": item.get("actualWarehouseName"),
                        "box_type_id": item.get("boxTypeID"),
                        "payload": item,
                    }
                )
            if len(supply_items) < limit:
                break
            offset += limit
        await self.repo.upsert_many(
            session, normalized, conflict_fields=["account_id", "supply_id"]
        )
        return len(normalized)

    async def _select_supplies_for_enrichment(
        self,
        session,
        *,
        account_id: int,
        last_updated_date: str | None,
        last_supply_id: int | None,
    ) -> list[WBSupply]:
        recent_threshold = utcnow() - timedelta(days=30)
        stmt = (
            select(WBSupply)
            .where(
                WBSupply.account_id == account_id,
                or_(
                    WBSupply.last_enriched_at.is_(None),
                    and_(
                        WBSupply.updated_date.is_not(None),
                        WBSupply.last_enriched_at.is_not(None),
                        WBSupply.updated_date > WBSupply.last_enriched_at,
                    ),
                    WBSupply.fact_date.is_(None),
                    and_(
                        WBSupply.updated_date.is_not(None),
                        WBSupply.updated_date >= recent_threshold,
                    ),
                ),
            )
            .order_by(
                WBSupply.updated_date.asc().nullsfirst(),
                WBSupply.supply_id.asc(),
            )
        )
        marker_datetime = (
            parse_datetime(last_updated_date) if last_updated_date else None
        )
        if marker_datetime is not None and last_supply_id is not None:
            stmt = stmt.where(
                or_(
                    WBSupply.updated_date.is_(None),
                    tuple_(WBSupply.updated_date, WBSupply.supply_id)
                    > tuple_(marker_datetime, last_supply_id),
                )
            )
        return list(
            (await session.execute(stmt.limit(self.ENRICHMENT_BATCH_SIZE))).scalars()
        )

    async def _enrich_supply(
        self, session, *, account_id: int, supply: WBSupply
    ) -> None:
        detail = await self.client.supply_details(
            session, account_id=account_id, supply_id=supply.supply_id
        )
        supply.payload = detail
        supply.warehouse_id = detail.get("warehouseID") or supply.warehouse_id
        supply.warehouse_name = detail.get("warehouseName") or supply.warehouse_name
        supply.actual_warehouse_id = (
            detail.get("actualWarehouseID") or supply.actual_warehouse_id
        )
        supply.actual_warehouse_name = (
            detail.get("actualWarehouseName") or supply.actual_warehouse_name
        )
        supply.updated_date = (
            parse_datetime(detail.get("updatedDate")) or supply.updated_date
        )
        supply.status_id = detail.get("statusID") or supply.status_id
        await self._pause()
        await session.execute(
            delete(WBSupplyGood).where(WBSupplyGood.supply_fk_id == supply.id)
        )
        goods_offset = 0
        goods_limit = 1000
        while True:
            goods = await self.client.supply_goods(
                session,
                account_id=account_id,
                supply_id=supply.supply_id,
                limit=goods_limit,
                offset=goods_offset,
            )
            goods_items = goods if isinstance(goods, list) else goods.get("data", [])
            if not goods_items:
                break
            for item in goods_items:
                session.add(
                    WBSupplyGood(
                        supply_fk_id=supply.id,
                        account_id=account_id,
                        nm_id=item.get("nmID") or item.get("nmId"),
                        vendor_code=item.get("vendorCode"),
                        barcode=item.get("barcode"),
                        tech_size=item.get("techSize"),
                        quantity=item.get("quantity") or item.get("supplierBoxAmount"),
                        accepted_quantity=item.get("acceptedQuantity"),
                        payload=item,
                    )
                )
            if len(goods_items) < goods_limit:
                break
            goods_offset += goods_limit
            await self._pause()
        supply.goods_synced_at = utcnow()
        await self._pause()
        packages = await self.client.supply_package(
            session, account_id=account_id, supply_id=supply.supply_id
        )
        await session.execute(
            delete(WBSupplyPackage).where(WBSupplyPackage.supply_fk_id == supply.id)
        )
        package_items = (
            packages if isinstance(packages, list) else packages.get("data", [])
        )
        for item in package_items:
            session.add(
                WBSupplyPackage(
                    supply_fk_id=supply.id,
                    account_id=account_id,
                    package_code=item.get("packageCode"),
                    quantity=item.get("quantity"),
                    barcodes=item.get("barcodes", []),
                    payload=item,
                )
            )
        supply.packages_synced_at = utcnow()
        supply.last_enriched_at = utcnow()
        await self._pause()

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        warehouses_payload = await self.client.warehouses(
            session, account_id=account.id
        )
        warehouse_items = (
            warehouses_payload
            if isinstance(warehouses_payload, list)
            else warehouses_payload.get("warehouses")
            or warehouses_payload.get("data")
            or []
        )
        normalized_warehouses = []
        if isinstance(warehouse_items, list):
            for item in warehouse_items:
                warehouse_id = (
                    item.get("warehouseID")
                    or item.get("warehouseId")
                    or item.get("ID")
                    or item.get("id")
                )
                if warehouse_id is None:
                    continue
                normalized_warehouses.append(
                    {
                        "account_id": account.id,
                        "warehouse_id": warehouse_id,
                        "name": item.get("name") or item.get("warehouseName"),
                        "address": item.get("address"),
                        "payload": item,
                    }
                )
        await self.warehouses.upsert_many(
            session,
            normalized_warehouses,
            conflict_fields=["account_id", "warehouse_id"],
        )
        warehouse_names = {
            int(item["warehouse_id"]): item.get("name")
            for item in normalized_warehouses
            if item.get("warehouse_id") is not None
        }
        barcode_candidates: list[str] = []
        for model in (CoreSKU, WBStockSnapshotRow, WBOrder, WBSale):
            barcodes = list(
                (
                    await session.execute(
                        select(model.barcode)
                        .where(
                            model.account_id == account.id, model.barcode.is_not(None)
                        )
                        .distinct()
                        .limit(50)
                    )
                ).scalars()
            )
            for barcode in barcodes:
                if barcode and barcode not in barcode_candidates:
                    barcode_candidates.append(barcode)
                if len(barcode_candidates) >= 20:
                    break
            if len(barcode_candidates) >= 20:
                break
        if barcode_candidates:
            request_items = [
                {"barcode": barcode, "quantity": 1} for barcode in barcode_candidates
            ]
            try:
                acceptance_payload = await self.client.acceptance_options(
                    session, account_id=account.id, items=request_items
                )
                await session.execute(
                    delete(WBSupplyAcceptanceOption).where(
                        WBSupplyAcceptanceOption.account_id == account.id
                    )
                )
                options = (
                    acceptance_payload.get("result")
                    or acceptance_payload.get("options")
                    or acceptance_payload.get("data")
                    or acceptance_payload
                )
                if isinstance(options, list):
                    for item in options:
                        if isinstance(item, dict) and isinstance(
                            item.get("warehouses"), list
                        ):
                            barcode = item.get("barcode")
                            for warehouse in item.get("warehouses") or []:
                                warehouse_id = warehouse.get(
                                    "warehouseID"
                                ) or warehouse.get("warehouseId")
                                session.add(
                                    WBSupplyAcceptanceOption(
                                        account_id=account.id,
                                        warehouse_id=warehouse_id,
                                        warehouse_name=warehouse.get("warehouseName")
                                        or warehouse_names.get(int(warehouse_id))
                                        if warehouse_id is not None
                                        else None,
                                        box_type_id=warehouse.get("boxTypeID")
                                        or warehouse.get("boxTypeId"),
                                        coefficient=str(warehouse.get("coefficient"))
                                        if warehouse.get("coefficient") is not None
                                        else None,
                                        allow_unload=any(
                                            bool(warehouse.get(flag))
                                            for flag in (
                                                "allowUnload",
                                                "canBox",
                                                "canMonopallet",
                                                "canSupersafe",
                                            )
                                        ),
                                        payload={"barcode": barcode, **warehouse},
                                    )
                                )
                        else:
                            session.add(
                                WBSupplyAcceptanceOption(
                                    account_id=account.id,
                                    warehouse_id=item.get("warehouseID")
                                    or item.get("warehouseId"),
                                    warehouse_name=item.get("warehouseName"),
                                    box_type_id=item.get("boxTypeID")
                                    or item.get("boxTypeId"),
                                    coefficient=str(item.get("coefficient"))
                                    if item.get("coefficient") is not None
                                    else None,
                                    allow_unload=item.get("allowUnload"),
                                    payload=item,
                                )
                            )
            except Exception as exc:
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="acceptance_options_sync_skipped",
                    message=str(exc),
                    severity="info",
                )
        header_rows = await self._sync_headers(session, account_id=account.id)
        enrichment_cursor = await self._get_cursor(
            session,
            account_id=account.id,
            cursor_key="enrichment",
        )
        last_supply_id = 0
        last_updated_date: str | None = None
        if enrichment_cursor and not force_full:
            last_supply_id = int(
                enrichment_cursor.cursor_value.get("lastSupplyId", 0) or 0
            )
            last_updated_date = enrichment_cursor.cursor_value.get("lastUpdatedDate")
        processed_supplies = 0
        stopped_due_to_rate_limit = False
        last_error: str | None = None
        for _ in range(self.MAX_ENRICHMENT_BATCHES_PER_RUN):
            db_supplies = await self._select_supplies_for_enrichment(
                session,
                account_id=account.id,
                last_updated_date=last_updated_date,
                last_supply_id=last_supply_id,
            )
            if not db_supplies:
                break
            for supply in db_supplies:
                try:
                    await self._enrich_supply(
                        session, account_id=account.id, supply=supply
                    )
                except Exception as exc:
                    last_error = str(exc)
                    if self._is_rate_limited(exc):
                        stopped_due_to_rate_limit = True
                        break
                    await self._open_issue(
                        session,
                        account_id=account.id,
                        code="supply_enrichment_failed",
                        message=str(exc),
                        severity="warning",
                        entity_key=str(supply.supply_id),
                    )
                    continue
                processed_supplies += 1
                last_supply_id = supply.supply_id
                last_updated_date = (
                    supply.updated_date.isoformat()
                    if supply.updated_date is not None
                    else last_updated_date
                )
            if stopped_due_to_rate_limit:
                break
        remaining_batch = await self._select_supplies_for_enrichment(
            session,
            account_id=account.id,
            last_updated_date=last_updated_date,
            last_supply_id=last_supply_id,
        )
        enrichment_done = not remaining_batch
        await self._set_cursor(
            session, account_id=account.id, cursor_value={"lastSync": "daily"}
        )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_key="enrichment",
            cursor_value={
                "lastSupplyId": last_supply_id,
                "lastUpdatedDate": last_updated_date,
                "processedSupplies": processed_supplies,
                "lastError": last_error,
                "done": enrichment_done,
            },
            status="rate_limited"
            if stopped_due_to_rate_limit
            else ("completed" if enrichment_done else "running"),
        )
        return {
            "status": "completed" if enrichment_done else "partial",
            "rows": header_rows,
            "processedSupplies": processed_supplies,
            "lastSupplyId": last_supply_id,
            "lastUpdatedDate": last_updated_date,
            "enrichmentDone": enrichment_done,
            "reason": "supplies_rate_limited" if stopped_due_to_rate_limit else None,
        }
