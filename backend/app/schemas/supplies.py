from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SupplyRead(BaseModel):
    id: int
    account_id: int
    supply_id: int
    create_date: datetime | None
    supply_date: datetime | None
    fact_date: datetime | None
    status_id: int | None
    warehouse_name: str | None
    actual_warehouse_name: str | None

    model_config = {"from_attributes": True}
