from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class Page(BaseModel, Generic[T]):
    total: int
    limit: int
    offset: int
    items: list[T]
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
