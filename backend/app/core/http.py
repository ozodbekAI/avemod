from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, ClassVar

import asyncio
import httpx

from app.core.config import get_settings
from app.core.time import utcnow

settings = get_settings()


class WBAPIError(RuntimeError):
    """Raised for non-success WB API responses."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        requested_at: Any,
        loaded_at: Any,
        response_text: str | None = None,
        payload: Any | None = None,
        retry_count: int = 0,
        response_headers: dict[str, str] | None = None,
        rate_limited_count: int = 0,
        last_rate_limit_retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.requested_at = requested_at
        self.loaded_at = loaded_at
        self.response_text = response_text
        self.payload = payload
        self.retry_count = retry_count
        self.response_headers = response_headers or {}
        self.rate_limited_count = rate_limited_count
        self.last_rate_limit_retry_after = last_rate_limit_retry_after


@dataclass(slots=True)
class WBResponse:
    status_code: int
    requested_at: Any
    loaded_at: Any
    payload: Any
    retry_count: int
    text: str | None = None
    headers: dict[str, str] | None = None
    rate_limited_count: int = 0
    last_rate_limit_retry_after: float | None = None


class WBHTTPClient:
    _last_request_started_at: ClassVar[dict[str, float]] = {}
    _domain_locks: ClassVar[dict[tuple[int, str], asyncio.Lock]] = {}
    _domain_min_spacing_seconds: ClassVar[dict[str, int]] = {
        "finance": 61,
        "ads_fullstats": 20,
        "analytics_funnel": 20,
        "documents": 10,
        "stocks": 10,
        "paid_storage_create": 60,
        "paid_storage_status": 5,
        "paid_storage_download": 60,
        "acceptance_report_create": 60,
        "acceptance_report_status": 5,
        "acceptance_report_download": 60,
        "marketplace_inventory": 1,
        "supplies_transit": 10,
    }

    def __init__(self, token: str, timeout: int | None = None) -> None:
        self._token = token
        self._timeout = timeout or settings.wb_http_timeout

    @classmethod
    def _rate_limit_key_for_url(cls, url: str) -> str | None:
        if "finance-api.wildberries.ru" in url:
            return "finance"
        if "/adv/v3/fullstats" in url or "/adv/v1/normquery/stats" in url:
            return "ads_fullstats"
        if "/api/analytics/v3/sales-funnel/products/history" in url:
            return "analytics_funnel"
        if "documents-api.wildberries.ru" in url:
            return "documents"
        if "/api/v1/warehouse_remains" in url:
            return "stocks"
        if "/api/v1/paid_storage/tasks/" in url and url.endswith("/status"):
            return "paid_storage_status"
        if "/api/v1/paid_storage/tasks/" in url and url.endswith("/download"):
            return "paid_storage_download"
        if "/api/v1/paid_storage" in url:
            return "paid_storage_create"
        if "/api/v1/acceptance_report/tasks/" in url and url.endswith("/status"):
            return "acceptance_report_status"
        if "/api/v1/acceptance_report/tasks/" in url and url.endswith("/download"):
            return "acceptance_report_download"
        if "/api/v1/acceptance_report" in url:
            return "acceptance_report_create"
        if "/api/v3/stocks/" in url or "/api/v3/warehouses" in url:
            return "marketplace_inventory"
        if "/api/v1/transit-tariffs" in url:
            return "supplies_transit"
        return None

    @classmethod
    async def _apply_pre_request_spacing(cls, url: str) -> None:
        key = cls._rate_limit_key_for_url(url)
        if key is None:
            return
        min_spacing = cls._domain_min_spacing_seconds.get(key)
        if not min_spacing:
            return
        loop_key = (id(asyncio.get_running_loop()), key)
        lock = cls._domain_locks.setdefault(loop_key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            last_started_at = cls._last_request_started_at.get(key)
            if last_started_at is not None:
                remaining = min_spacing - (now - last_started_at)
                if remaining > 0:
                    await asyncio.sleep(remaining)
            cls._last_request_started_at[key] = time.monotonic()

    @staticmethod
    def _extract_response_headers(
        headers: httpx.Headers | dict[str, str] | None,
    ) -> dict[str, str]:
        if headers is None:
            return {}
        if isinstance(headers, httpx.Headers):
            items = headers.items()
        else:
            items = headers.items()
        return {str(key).lower(): str(value) for key, value in items}

    @staticmethod
    def _fallback_retry_delay(attempt_count: int) -> float:
        return float(settings.wb_http_retry_backoff_seconds * attempt_count)

    @classmethod
    def _rate_limit_sleep_seconds(
        cls,
        headers: dict[str, str] | None,
        *,
        attempt_count: int,
    ) -> float:
        normalized = {
            str(key).lower(): str(value) for key, value in (headers or {}).items()
        }
        retry_value = normalized.get("x-ratelimit-retry") or normalized.get(
            "retry-after"
        )
        if retry_value:
            try:
                retry_seconds = float(retry_value)
            except ValueError:
                retry_seconds = None
            if retry_seconds is not None and retry_seconds >= 0:
                return retry_seconds
        reset_value = normalized.get("x-ratelimit-reset")
        if reset_value:
            try:
                parsed = float(reset_value)
            except ValueError:
                parsed = None
            if parsed is not None:
                if parsed > 1_000_000_000:
                    return max(0.0, parsed - time.time())
                if parsed >= 0:
                    return parsed
        return cls._fallback_retry_delay(attempt_count)

    async def request_json(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
    ) -> WBResponse:
        last_error: Exception | None = None
        attempt_count = 0
        rate_limited_count = 0
        last_rate_limit_retry_after: float | None = None
        for attempt in range(settings.wb_http_retry_attempts):
            attempt_count = attempt + 1
            requested_at = utcnow()
            try:
                await self._apply_pre_request_spacing(url)
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        params=params,
                        json=json_body,
                        headers={"Authorization": self._token},
                    )
                loaded_at = utcnow()
                response_headers = self._extract_response_headers(response.headers)
                payload: Any = (
                    {"noData": True}
                    if response.status_code == 204 and not response.text
                    else {}
                )
                if response.text:
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {"rawText": response.text}
                if response.status_code >= 500 or response.status_code == 429:
                    raise WBAPIError(
                        f"WB API error {response.status_code}: {response.text[:500]}",
                        status_code=response.status_code,
                        requested_at=requested_at,
                        loaded_at=loaded_at,
                        response_text=response.text,
                        payload=payload,
                        retry_count=attempt_count - 1,
                        response_headers=response_headers,
                        rate_limited_count=rate_limited_count,
                        last_rate_limit_retry_after=last_rate_limit_retry_after,
                    )
                if response.status_code >= 400:
                    raise WBAPIError(
                        f"WB API error {response.status_code}: {response.text[:500]}",
                        status_code=response.status_code,
                        requested_at=requested_at,
                        loaded_at=loaded_at,
                        response_text=response.text,
                        payload=payload,
                        retry_count=attempt_count - 1,
                        response_headers=response_headers,
                        rate_limited_count=rate_limited_count,
                        last_rate_limit_retry_after=last_rate_limit_retry_after,
                    )
                return WBResponse(
                    status_code=response.status_code,
                    requested_at=requested_at,
                    loaded_at=loaded_at,
                    payload=payload,
                    retry_count=attempt_count - 1,
                    text=response.text,
                    headers=response_headers,
                    rate_limited_count=rate_limited_count,
                    last_rate_limit_retry_after=last_rate_limit_retry_after,
                )
            except WBAPIError as exc:
                last_error = exc
                if exc.status_code not in {429} and exc.status_code < 500:
                    break
                if attempt_count == settings.wb_http_retry_attempts:
                    break
                retry_after = self._rate_limit_sleep_seconds(
                    exc.response_headers,
                    attempt_count=attempt_count,
                )
                if exc.status_code == 429:
                    rate_limited_count += 1
                    last_rate_limit_retry_after = retry_after
                await asyncio.sleep(retry_after)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt_count == settings.wb_http_retry_attempts:
                    break
                await asyncio.sleep(self._fallback_retry_delay(attempt_count))
        if isinstance(last_error, WBAPIError):
            raise last_error
        failed_at = utcnow()
        raise WBAPIError(
            f"WB API request failed: {last_error}",
            status_code=0,
            requested_at=failed_at,
            loaded_at=failed_at,
            response_text=str(last_error) if last_error else None,
            payload={"error": str(last_error)} if last_error else {},
            retry_count=max(0, attempt_count - 1),
            response_headers={},
            rate_limited_count=rate_limited_count,
            last_rate_limit_retry_after=last_rate_limit_retry_after,
        ) from last_error
