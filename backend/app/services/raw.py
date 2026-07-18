from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw import RawWBAPIResponse
from app.repositories.raw import RawResponseRepository


class RawResponseService:
    def __init__(self) -> None:
        self.repo = RawResponseRepository()

    async def store(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        api_category: str,
        endpoint: str,
        http_method: str,
        request_params: dict[str, Any] | None,
        request_body: Any | None,
        response_json: Any,
        response_text: str | None,
        response_headers: dict[str, str] | None,
        status_code: int,
        is_success: bool,
        retry_count: int,
        requested_at: Any,
        loaded_at: Any,
        error_text: str | None = None,
    ) -> RawWBAPIResponse:
        request_params = request_params or {}
        request_fingerprint = sha256(
            json.dumps(
                {
                    "account_id": account_id,
                    "api_category": api_category,
                    "endpoint": endpoint,
                    "http_method": http_method,
                    "request_params": request_params,
                    "request_body": request_body,
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        response_fingerprint = sha256(
            json.dumps(
                {
                    "response_json": response_json,
                    "response_text": response_text,
                    "response_headers": response_headers,
                    "status_code": status_code,
                    "is_success": is_success,
                    "error_text": error_text,
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        payload_hash = sha256(
            json.dumps(
                {
                    "request_fingerprint": request_fingerprint,
                    "response_fingerprint": response_fingerprint,
                },
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        return await self.repo.create(
            session,
            account_id=account_id,
            api_category=api_category,
            endpoint=endpoint,
            request_params=request_params,
            http_method=http_method,
            request_body=request_body,
            response_json=response_json,
            response_text=response_text,
            response_headers=response_headers,
            status_code=status_code,
            is_success=is_success,
            retry_count=retry_count,
            requested_at=requested_at,
            loaded_at=loaded_at,
            hash=payload_hash,
            request_fingerprint=request_fingerprint,
            response_fingerprint=response_fingerprint,
            error_text=error_text,
        )
