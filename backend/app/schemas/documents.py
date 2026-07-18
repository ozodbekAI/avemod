from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DocumentRead(BaseModel):
    id: int
    account_id: int
    document_key: str
    title: str | None
    category: str | None
    document_date: date | None
    created_at: datetime

    model_config = {"from_attributes": True}
