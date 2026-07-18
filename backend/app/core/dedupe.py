from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Iterable

NULL_SENTINEL = "<null>"


def normalize_dedupe_value(value: Any) -> str:
    if value is None:
        return NULL_SENTINEL
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, datetime):
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(timezone.utc).isoformat()
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True, default=str)
    return str(value)


def compute_dedupe_key_from_mapping(
    fields: Iterable[str], values: dict[str, Any]
) -> str:
    payload = "|".join(normalize_dedupe_value(values.get(field)) for field in fields)
    return sha256(payload.encode("utf-8")).hexdigest()


def compute_dedupe_key_for_instance(instance: Any) -> str | None:
    fields = getattr(instance, "__dedupe_fields__", None)
    if not fields:
        return None
    values = {field: getattr(instance, field, None) for field in fields}
    return compute_dedupe_key_from_mapping(fields, values)
