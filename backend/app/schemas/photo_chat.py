from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


class PhotoChatQuickActionIn(BaseModel):
    model_config = {"protected_namespaces": ()}

    type: str | None = None
    action: str | None = None
    pose_prompt_id: int | None = None
    prompt_id: int | None = None
    scene_item_id: int | None = None
    item_id: int | None = None
    model_item_id: int | None = None
    new_model_prompt: str | None = None
    level: str | None = None
    prompt: str | None = None
    model: str | None = None
    duration: int | None = None
    resolution: str | None = None


class PhotoChatStreamRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    message: str = ""
    asset_ids: list[int] = Field(default_factory=list)
    photo_urls: list[str] = Field(default_factory=list)
    photo_url: str | None = None
    quick_action: PhotoChatQuickActionIn | dict[str, Any] | None = None
    account_id: int | None = None
    nm_id: int | None = None
    thread_id: int | None = None
    request_id: str | None = None
    locale: str | None = None
    client_session_id: str | None = None
    planner_model: str | None = None
    generation_model: str | None = None
    model_profile: str | None = None
    allow_quality_fallback: bool | None = None

    @field_validator("asset_ids", mode="before")
    @classmethod
    def _normalize_asset_ids(cls, value: object) -> list[int]:
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        normalized: list[int] = []
        for item in value:
            try:
                normalized.append(int(item))
            except (TypeError, ValueError):
                continue
        return normalized

    @field_validator("photo_urls", mode="before")
    @classmethod
    def _normalize_photo_urls(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @field_validator("message", mode="before")
    @classmethod
    def _normalize_message(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator(
        "account_id",
        "nm_id",
        "thread_id",
        mode="before",
    )
    @classmethod
    def _normalize_optional_ints(cls, value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @field_validator(
        "photo_url",
        "request_id",
        "locale",
        "client_session_id",
        "planner_model",
        "generation_model",
        "model_profile",
        mode="before",
    )
    @classmethod
    def _normalize_optional_strings(cls, value: object) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class PhotoChatRequest(PhotoChatStreamRequest):
    pass
