from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ABTestPhotoIn(BaseModel):
    order: int
    file_url: str


class ABTestCreateRequest(BaseModel):
    account_id: int
    nm_id: int
    product_card_id: int | None = None
    card_id: int | None = None
    title: str
    from_main: bool = False
    main_photo_url: str | None = None
    max_slots: int = 5
    keep_winner_as_main: bool = True
    delete_test_photos: bool = True
    photos: list[ABTestPhotoIn] = Field(default_factory=list)
    photos_count: int = 0
    preview_confirmed: bool = False
    confirm: bool = False

    @field_validator("photos")
    @classmethod
    def _validate_photos(cls, value: list[ABTestPhotoIn]) -> list[ABTestPhotoIn]:
        if len(value) < 2:
            raise ValueError("At least two photo variants are required")
        return value


class ABTestUpdateRequest(BaseModel):
    account_id: int
    id_company: int | None = None
    company_id: int | None = None
    nm_id: int
    product_card_id: int | None = None
    card_id: int | None = None
    title: str
    title_changed: bool = False
    from_main: bool = False
    max_slots: int = 5
    keep_winner_as_main: bool = True
    delete_test_photos: bool = True
    photos_count: int = 0
    views_per_photo: int
    cpm: int
    spend_rub: int = 0
    estimated_spend_rub: int | None = None
    auto_deposit: bool = True
    deposit_rub: int | None = None
    payment_source: str | None = None
    use_promo_bonus: bool | None = None
    photos: list[ABTestPhotoIn] = Field(default_factory=list)
    preview_confirmed: bool = False
    confirm: bool = False

    @field_validator("views_per_photo")
    @classmethod
    def _validate_views(cls, value: int) -> int:
        if int(value) < 1000:
            raise ValueError("views_per_photo must be at least 1000")
        return value

    @field_validator("cpm")
    @classmethod
    def _validate_cpm(cls, value: int) -> int:
        if int(value) <= 0:
            raise ValueError("cpm must be positive")
        return value


class ABTestPhotoOut(BaseModel):
    order: int
    file_url: str
    wb_url: str | None = None
    preview_url: str | None = None
    shows: int = 0
    clicks: int = 0
    ctr: float = 0.0
    is_winner: bool = False
    winner_score: float | None = None
    winner_score_confidence: float | None = None
    winner_score_conversion_source: str | None = None
    winner_score_reason: str | None = None


class ABTestCompanyOut(BaseModel):
    id_company: int
    company_id: int | None = None
    wb_advert_id: int | None = None
    account_id: int
    nm_id: int
    product_card_id: int | None = None
    card_id: int | None = None
    title: str
    status: str
    spend_rub: int
    estimated_spend_rub: int = 0
    winner_decision: str | None = None
    views_per_photo: int
    photos_count: int
    current_photo_order: int
    winner_photo_order: int | None = None
    last_error: str | None = None
    can_start: bool = False
    can_stop: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None
    photos: list[ABTestPhotoOut] = Field(default_factory=list)


class ABTestPageOut(BaseModel):
    items: list[ABTestCompanyOut]
    pagination: dict[str, int]


class ABTestBalanceOut(BaseModel):
    balance: int = 0
    promo_bonus_rub: int = 0
    raw: Any | None = None
