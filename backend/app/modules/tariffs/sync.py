from __future__ import annotations

from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.modules.tariffs.client import TariffsClient
from app.repositories.tariffs import (
    TariffAcceptanceRepository,
    TariffBoxRepository,
    TariffCommissionRepository,
    TariffPalletRepository,
    TariffReturnRepository,
)


class TariffsSyncService(DomainSyncBase):
    domain = "tariffs"
    category = "tariffs"

    def __init__(self) -> None:
        super().__init__()
        self.client = TariffsClient(self)
        self.commissions = TariffCommissionRepository()
        self.boxes_repo = TariffBoxRepository()
        self.pallets_repo = TariffPalletRepository()
        self.returns_repo = TariffReturnRepository()
        self.acceptance_repo = TariffAcceptanceRepository()

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        today = utcnow().date().isoformat()
        commission_payload = await self.client.commissions(
            session, account_id=account.id
        )
        commission_rows = []
        for item in (
            commission_payload.get("report", [])
            if isinstance(commission_payload, dict)
            else []
        ):
            commission_rows.append(
                {
                    "account_id": account.id,
                    "collected_at": utcnow().date(),
                    "parent_id": item.get("parentID"),
                    "parent_name": item.get("parentName"),
                    "subject_id": item.get("subjectID"),
                    "subject_name": item.get("subjectName"),
                    "kgvp_marketplace": item.get("kgvpMarketplace"),
                    "payload": item,
                }
            )
        await self.commissions.upsert_many(
            session, commission_rows, conflict_fields=["dedupe_key"]
        )
        for cls, payload in (
            (
                self.boxes_repo,
                await self.client.boxes(session, account_id=account.id, for_date=today),
            ),
            (
                self.pallets_repo,
                await self.client.pallets(
                    session, account_id=account.id, for_date=today
                ),
            ),
            (
                self.returns_repo,
                await self.client.returns(
                    session, account_id=account.id, for_date=today
                ),
            ),
        ):
            rows = []
            warehouse_list = (
                payload.get("response", {}).get("data", {}).get("warehouseList", [])
                if isinstance(payload, dict)
                else []
            )
            for item in warehouse_list:
                rows.append(
                    {
                        "account_id": account.id,
                        "collected_at": utcnow().date(),
                        "warehouse_name": item.get("warehouseName"),
                        "payload": item,
                    }
                )
            await cls.upsert_many(session, rows, conflict_fields=["dedupe_key"])
        acceptance_payload = await self.client.acceptance(
            session, account_id=account.id
        )
        acceptance_items = acceptance_payload
        if isinstance(acceptance_payload, dict):
            acceptance_items = (
                acceptance_payload.get("report") or acceptance_payload.get("data") or []
            )
        acceptance_rows = []
        if isinstance(acceptance_items, list):
            for item in acceptance_items:
                acceptance_rows.append(
                    {
                        "account_id": account.id,
                        "collected_at": utcnow().date(),
                        "warehouse_id": item.get("warehouseID")
                        or item.get("warehouseId"),
                        "warehouse_name": item.get("warehouseName"),
                        "coefficient": str(item.get("coefficient"))
                        if item.get("coefficient") is not None
                        else None,
                        "allow_unload": item.get("allowUnload"),
                        "payload": item,
                    }
                )
        await self.acceptance_repo.upsert_many(
            session, acceptance_rows, conflict_fields=["dedupe_key"]
        )
        await self._set_cursor(
            session, account_id=account.id, cursor_value={"collectedAt": today}
        )
        return {"status": "completed"}
