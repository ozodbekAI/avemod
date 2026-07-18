from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class StockSnapshotRowRead(BaseModel):
    id: int
    snapshot_id: int
    account_id: int
    nm_id: int | None
    barcode: str | None
    warehouse_name: str | None
    quantity: float | None
    quantity_full: float | None
    in_way_to_client: float | None
    in_way_from_client: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
