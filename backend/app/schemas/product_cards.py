from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProductCardRead(BaseModel):
    id: int
    account_id: int
    nm_id: int
    imt_id: int | None
    subject_id: int | None
    subject_name: str | None
    vendor_code: str | None
    title: str | None
    description: str | None
    brand: str | None
    need_kiz: bool | None
    photos: list | dict | None = None
    updated_at_wb: datetime | None

    model_config = {"from_attributes": True}
