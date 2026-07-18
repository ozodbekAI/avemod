from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
from typing import Generic, TypeVar

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow

T = TypeVar("T")


@dataclass
class TTLCacheEntry(Generic[T]):
    value: T
    expires_at: datetime


class TTLMemoryCache(Generic[T]):
    def __init__(self, *, default_ttl_seconds: int = 600) -> None:
        self.default_ttl_seconds = default_ttl_seconds
        self._entries: dict[object, TTLCacheEntry[T]] = {}

    def get(self, key: object) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at < utcnow():
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: object, value: T, *, ttl_seconds: int | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        self._entries[key] = TTLCacheEntry(
            value=value,
            expires_at=utcnow() + timedelta(seconds=max(int(ttl), 1)),
        )

    def clear(self) -> None:
        self._entries.clear()


def stable_hash(*parts: object) -> str:
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()


def _row_value(row: object, key: str) -> object | None:
    if hasattr(row, key):
        return getattr(row, key)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and key in mapping:
        return mapping[key]
    return None


async def table_signature(
    session: AsyncSession,
    *,
    model: type,
    account_id: int | None = None,
    account_column: object | None = None,
    date_column: object | None = None,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
    extra_filters: list[object] | None = None,
) -> str:
    filters: list[object] = []
    resolved_account_column = (
        account_column
        if account_column is not None
        else getattr(model, "account_id", None)
    )
    if resolved_account_column is not None and account_id is not None:
        filters.append(resolved_account_column == account_id)
    if extra_filters:
        filters.extend(extra_filters)
    if date_column is not None and date_from is not None:
        filters.append(date_column >= date_from)
    if date_column is not None and date_to is not None:
        filters.append(date_column <= date_to)
    updated_at_col = getattr(model, "updated_at", None)
    stmt = select(
        func.count().label("row_count"),
        func.max(updated_at_col).label("updated_at")
        if updated_at_col is not None
        else sa.literal(None).label("updated_at"),
        func.max(date_column).label("max_date")
        if date_column is not None
        else sa.literal(None).label("max_date"),
    ).where(*filters)
    row = (await session.execute(stmt)).one()
    payload = "|".join(
        [
            getattr(model, "__tablename__", getattr(model, "__name__", "unknown")),
            str(account_id or ""),
            str(
                date_from.isoformat()
                if hasattr(date_from, "isoformat")
                else date_from or ""
            ),
            str(
                date_to.isoformat() if hasattr(date_to, "isoformat") else date_to or ""
            ),
            str(_row_value(row, "row_count") or 0),
            str(_row_value(row, "updated_at") or ""),
            str(_row_value(row, "max_date") or ""),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()
