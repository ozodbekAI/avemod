from __future__ import annotations

import json
import logging
import time
from contextvars import ContextVar
from typing import Any

from fastapi import Request, Response


logger = logging.getLogger("app.observability")

_unavailable_sources: ContextVar[list[str] | None] = ContextVar(
    "unavailable_sources", default=None
)

SECRET_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "credential",
    "encrypted_token",
    "encryption_key",
    "headers",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
    "wb_payload",
    "raw_wb",
)


def scrub_log_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): scrub_log_fields(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in SECRET_FIELD_TOKENS)
        }
    if isinstance(value, list):
        return [scrub_log_fields(item) for item in value]
    if isinstance(value, tuple):
        return [scrub_log_fields(item) for item in value]
    return value


def reset_unavailable_sources():
    return _unavailable_sources.set([])


def restore_unavailable_sources(token: Any) -> None:
    _unavailable_sources.reset(token)


def record_unavailable_source(source: str | None) -> None:
    normalized = str(source or "").strip()
    if not normalized:
        return
    current = _unavailable_sources.get()
    if current is None:
        current = []
        _unavailable_sources.set(current)
    if normalized not in current:
        current.append(normalized)


def get_unavailable_sources() -> list[str]:
    return list(_unavailable_sources.get() or [])


def log_optional_module_failure(
    *,
    source: str,
    reason: str,
    account_id: int | None = None,
    duration_ms: float | None = None,
    error_type: str | None = None,
) -> None:
    record_unavailable_source(source)
    fields: dict[str, Any] = {
        "event": "portal_optional_source_unavailable",
        "source": source,
        "reason": reason,
    }
    if account_id is not None:
        fields["account_id"] = account_id
    if duration_ms is not None:
        fields["duration_ms"] = round(float(duration_ms), 2)
    if error_type:
        fields["error_type"] = error_type
    logger.warning(json.dumps(scrub_log_fields(fields), sort_keys=True))


def _safe_int(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_account_id(request: Request) -> int | None:
    query_account_id = _safe_int(request.query_params.get("account_id"))
    if query_account_id is not None:
        return query_account_id
    try:
        return _safe_int(request.path_params.get("account_id"))
    except Exception:
        return None


async def request_timing_middleware(request: Request, call_next) -> Response:
    token = reset_unavailable_sources()
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        unavailable = get_unavailable_sources()
        route = request.scope.get("route")
        endpoint_path = getattr(route, "path", request.url.path)
        fields: dict[str, Any] = {
            "event": "http_request",
            "endpoint_path": endpoint_path,
            "method": request.method,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "unavailable_sources_count": len(unavailable),
            "unavailable_sources": unavailable,
        }
        account_id = _safe_account_id(request)
        if account_id is not None:
            fields["account_id"] = account_id
        logger.info(json.dumps(scrub_log_fields(fields), sort_keys=True))
        restore_unavailable_sources(token)
