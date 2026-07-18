from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class TariffRead(BaseModel):
    id: int
    account_id: int
    collected_at: date
    parent_id: int | None = None
    parent_name: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    kgvp_pickup: float | None = None
    kgvp_booking: float | None = None
    kgvp_supplier: float | None = None
    kgvp_marketplace: float | None = None
    paid_storage_kgvp: float | None = None
    kgvp_supplier_express: float | None = None
    payload: dict
