from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SaleRead(BaseModel):
    id: int
    account_id: int
    srid: str
    nm_id: int | None
    supplier_article: str | None
    total_price: float | None
    price_with_disc: float | None
    for_pay: float | None
    last_change_date: datetime
    is_cancel: bool | None

    model_config = {"from_attributes": True}
