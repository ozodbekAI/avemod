from __future__ import annotations

from typing import Any


def _coerce_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _extract_from_entity_key(entity_key: str | None, prefix: str) -> int | None:
    if not entity_key or not entity_key.startswith(prefix):
        return None
    raw = entity_key[len(prefix) :].split("|", 1)[0].strip()
    return _coerce_int(raw)


def extract_issue_refs(
    *,
    sku_id: int | None = None,
    nm_id: int | None = None,
    entity_key: str | None = None,
    payload: dict[str, Any] | None = None,
) -> tuple[int | None, int | None]:
    normalized_payload = payload if isinstance(payload, dict) else {}

    resolved_sku_id = _coerce_int(sku_id)
    if resolved_sku_id is None:
        resolved_sku_id = _coerce_int(normalized_payload.get("skuId"))
    if resolved_sku_id is None:
        resolved_sku_id = _coerce_int(normalized_payload.get("sku_id"))
    if resolved_sku_id is None:
        resolved_sku_id = _extract_from_entity_key(entity_key, "sku:")

    resolved_nm_id = _coerce_int(nm_id)
    if resolved_nm_id is None:
        resolved_nm_id = _coerce_int(normalized_payload.get("nmId"))
    if resolved_nm_id is None:
        resolved_nm_id = _coerce_int(normalized_payload.get("nm_id"))
    if resolved_nm_id is None:
        resolved_nm_id = _extract_from_entity_key(entity_key, "nm:")

    return resolved_sku_id, resolved_nm_id
