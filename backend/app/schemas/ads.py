from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class AdCampaignRead(BaseModel):
    id: int
    account_id: int
    advert_id: int
    campaign_type: int | None
    status: int | None
    bid_type: str | None
    name: str | None
    change_time: datetime | None

    model_config = {"from_attributes": True}


class AdCampaignItemRead(BaseModel):
    id: int
    account_id: int
    campaign_fk_id: int
    nm_id: int | None
    name: str | None
    payload: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class AdCampaignDetailRead(AdCampaignRead):
    payload: dict = Field(default_factory=dict)
    items: list[AdCampaignItemRead] = Field(default_factory=list)


class AdStatRead(BaseModel):
    id: int
    account_id: int
    advert_id: int
    stat_date: date
    nm_id: int | None
    views: int | None
    clicks: int | None
    ctr: float | None
    cr: float | None
    cpc: float | None
    cpm: float | None
    atbs: int | None
    sum: float | None
    sum_price: float | None
    orders: int | None
    shks: int | None
    canceled: int | None
    payload: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class AdClusterStatRead(BaseModel):
    id: int
    account_id: int
    advert_id: int
    stat_date: date
    cluster: str | None
    nm_id: int | None
    views: int | None
    clicks: int | None
    ctr: float | None
    cpc: float | None
    cpm: float | None
    orders: int | None
    atbs: int | None
    shks: int | None
    sum: float | None
    avg_position: float | None
    payload: dict = Field(default_factory=dict)

    model_config = {"from_attributes": True}
