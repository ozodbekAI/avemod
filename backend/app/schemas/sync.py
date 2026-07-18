from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.core.redaction import redact_sensitive_text, scrub_sensitive_payload


class SyncTriggerRequest(BaseModel):
    account_id: int
    domain: str
    force_full: bool = False


class SyncBackfillRequest(BaseModel):
    account_id: int
    domain: str
    date_from: date | None = None
    date_to: date | None = None
    force_full: bool = False


class SyncRunRead(BaseModel):
    id: int
    account_id: int
    domain: str
    trigger: str
    status: str
    is_backfill: bool
    started_at: datetime
    finished_at: datetime | None
    details: dict
    error_text: str | None

    model_config = {"from_attributes": True}

    @field_validator("details", mode="before")
    @classmethod
    def scrub_details(cls, value):
        return scrub_sensitive_payload(value or {})

    @field_validator("error_text", mode="before")
    @classmethod
    def scrub_error_text(cls, value):
        return redact_sensitive_text(value)


class SyncCursorRead(BaseModel):
    id: int
    account_id: int
    domain: str
    cursor_key: str
    cursor_value: dict
    last_synced_at: datetime | None
    status: str
    next_scheduled_at: datetime | None = None
    last_error_text: str | None = None
    last_error_at: datetime | None = None

    model_config = {"from_attributes": True}

    @field_validator("cursor_value", mode="before")
    @classmethod
    def scrub_cursor_value(cls, value):
        return scrub_sensitive_payload(value or {})

    @field_validator("last_error_text", mode="before")
    @classmethod
    def scrub_last_error_text(cls, value):
        return redact_sensitive_text(value)
