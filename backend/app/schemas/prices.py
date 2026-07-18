from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PriceSizeRead(BaseModel):
    tech_size: str | None
    price: float | None
    discounted_price: float | None
    club_discounted_price: float | None


class PriceRead(BaseModel):
    id: int
    account_id: int
    nm_id: int
    vendor_code: str | None
    currency_iso_code: str | None
    discount: int | None
    club_discount: int | None
    editable_size_price: bool | None
    current_price: float | None
    discounted_price: float | None
    min_size_price: float | None
    max_size_price: float | None
    sizes: list[PriceSizeRead]
    created_at: datetime

    model_config = {"from_attributes": True}
