from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.models.tariffs import WBTariffCommission


class TariffsService:
    @staticmethod
    def _as_float(value: object) -> float | None:
        if value in (None, ""):
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def list_tariffs(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        limit=50,
        offset=0,
    ) -> Page[dict]:
        stmt = select(WBTariffCommission).order_by(
            WBTariffCommission.collected_at.desc(), WBTariffCommission.id.desc()
        )
        count_stmt = select(func.count()).select_from(WBTariffCommission)
        if account_id is not None:
            stmt = stmt.where(WBTariffCommission.account_id == account_id)
            count_stmt = count_stmt.where(WBTariffCommission.account_id == account_id)
        total = int((await session.execute(count_stmt)).scalar_one())
        rows = list((await session.execute(stmt.limit(limit).offset(offset))).scalars())
        items: list[dict] = []
        for row in rows:
            payload = dict(row.payload or {})
            items.append(
                {
                    "id": row.id,
                    "account_id": row.account_id,
                    "collected_at": row.collected_at,
                    "parent_id": row.parent_id,
                    "parent_name": row.parent_name,
                    "subject_id": row.subject_id,
                    "subject_name": row.subject_name,
                    "kgvp_pickup": self._as_float(payload.get("kgvpPickup")),
                    "kgvp_booking": self._as_float(payload.get("kgvpBooking")),
                    "kgvp_supplier": self._as_float(payload.get("kgvpSupplier")),
                    "kgvp_marketplace": self._as_float(
                        row.kgvp_marketplace or payload.get("kgvpMarketplace")
                    ),
                    "paid_storage_kgvp": self._as_float(payload.get("paidStorageKgvp")),
                    "kgvp_supplier_express": self._as_float(
                        payload.get("kgvpSupplierExpress")
                    ),
                    "payload": payload,
                }
            )
        return Page(total=total, limit=limit, offset=offset, items=items)
