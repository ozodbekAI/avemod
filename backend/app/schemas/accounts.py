from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class WBAccountCreate(BaseModel):
    name: str
    seller_name: str | None = None
    external_account_id: str | None = None
    timezone: str = "Europe/Moscow"
    is_active: bool = True


class WBAccountRead(BaseModel):
    id: int
    name: str
    seller_name: str | None
    external_account_id: str | None
    timezone: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WBTokenUpsert(BaseModel):
    category: str
    token: str
    comment: str | None = None
    is_active: bool = True


class WBTokenRead(BaseModel):
    id: int
    account_id: int
    category: str
    comment: str | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
