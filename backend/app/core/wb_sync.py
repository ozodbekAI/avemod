from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import WBAPIError, WBHTTPClient
from app.core.time import utcnow
from app.services.accounts import AccountService
from app.services.data_quality import DataQualityService
from app.services.raw import RawResponseService
from app.models.sync import WBSyncCursor
from app.repositories.sync import WBSyncCursorRepository
from app.services.sync import BaseDomainSyncService


class DomainSyncBase(BaseDomainSyncService):
    domain: str = ""
    category: str = ""

    def __init__(self) -> None:
        self.account_service = AccountService()
        self.raw_service = RawResponseService()
        self.cursor_repo = WBSyncCursorRepository()
        self.dq_service = DataQualityService()
        self._rate_limited_count = 0
        self._last_rate_limit_retry_after: float | None = None
        self._progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = (
            None
        )

    def set_progress_callback(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]] | None,
    ) -> None:
        self._progress_callback = callback

    async def _progress(self, **payload: Any) -> None:
        if self._progress_callback is None:
            return
        await self._progress_callback(payload)

    def _record_rate_limit_observation(
        self,
        *,
        count: int = 0,
        retry_after: float | None = None,
    ) -> None:
        if count > 0:
            self._rate_limited_count += count
        if retry_after is not None:
            self._last_rate_limit_retry_after = retry_after

    def runtime_details(self) -> dict[str, Any]:
        return {
            "rate_limited_count": self._rate_limited_count,
            "last_rate_limit_retry_after": self._last_rate_limit_retry_after,
        }

    async def _get_cursor(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        cursor_key: str = "default",
    ) -> WBSyncCursor | None:
        return await self.cursor_repo.get_for_domain(
            session,
            account_id=account_id,
            domain=self.domain,
            cursor_key=cursor_key,
        )

    async def _set_cursor(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        cursor_value: dict[str, Any],
        cursor_key: str = "default",
        status: str = "completed",
    ) -> None:
        cursor = await self._get_cursor(
            session, account_id=account_id, cursor_key=cursor_key
        )
        if cursor is None:
            session.add(
                WBSyncCursor(
                    account_id=account_id,
                    domain=self.domain,
                    cursor_key=cursor_key,
                    cursor_value=cursor_value,
                    last_synced_at=utcnow(),
                    status=status,
                )
            )
        else:
            cursor.cursor_value = cursor_value
            cursor.last_synced_at = utcnow()
            cursor.status = status
        await session.flush()

    async def _request_json(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        endpoint: str,
        url: str,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        api_category: str | None = None,
    ) -> Any:
        token = await self.account_service.get_decrypted_token(
            session, account_id, self.category
        )
        client = WBHTTPClient(token)
        try:
            response = await client.request_json(
                method, url, params=params, json_body=json_body
            )
            await self.raw_service.store(
                session,
                account_id=account_id,
                api_category=api_category or self.category,
                endpoint=endpoint,
                http_method=method,
                request_params=params or {},
                request_body=json_body,
                response_json=response.payload,
                response_text=response.text,
                response_headers=response.headers,
                status_code=response.status_code,
                is_success=True,
                retry_count=response.retry_count,
                requested_at=response.requested_at,
                loaded_at=response.loaded_at,
            )
            self._record_rate_limit_observation(
                count=response.rate_limited_count,
                retry_after=response.last_rate_limit_retry_after,
            )
            return response.payload
        except WBAPIError as exc:
            await self.raw_service.store(
                session,
                account_id=account_id,
                api_category=api_category or self.category,
                endpoint=endpoint,
                http_method=method,
                request_params=params or {},
                request_body=json_body,
                response_json=exc.payload or {"error": str(exc)},
                response_text=exc.response_text,
                response_headers=exc.response_headers,
                status_code=exc.status_code,
                is_success=False,
                retry_count=exc.retry_count,
                requested_at=exc.requested_at,
                loaded_at=exc.loaded_at,
                error_text=str(exc),
            )
            self._record_rate_limit_observation(
                count=exc.rate_limited_count,
                retry_after=exc.last_rate_limit_retry_after,
            )
            raise

    async def _open_issue(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        code: str,
        message: str,
        severity: str = "warning",
        entity_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        await self.dq_service.open_issue(
            session,
            account_id=account_id,
            domain=self.domain,
            code=code,
            message=message,
            severity=severity,
            entity_key=entity_key,
            payload=payload,
        )

    async def run(
        self,
        session: AsyncSession,
        *,
        account: Any,
        force_full: bool = False,
        backfill_from: date | None = None,
        backfill_to: date | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError
