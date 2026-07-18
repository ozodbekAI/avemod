from __future__ import annotations

from datetime import date, datetime
from typing import Any


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).replace("Z", "+00:00")
    if "T" in text:
        return datetime.fromisoformat(text).date()
    return date.fromisoformat(text)
