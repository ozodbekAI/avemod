from __future__ import annotations

from pydantic import BaseModel


class EnumMetaResponse(BaseModel):
    enums: dict[str, dict[str, str]]


class EnumOption(BaseModel):
    value: str
    label: str


class EnumOptionListResponse(BaseModel):
    items: list[EnumOption]
