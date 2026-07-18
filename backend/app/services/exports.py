from __future__ import annotations

import hashlib
from datetime import date, datetime
from io import BytesIO
from typing import Iterable

from openpyxl import Workbook
import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLMemoryCache
from app.models.data_quality import DataQualityIssue
from app.models.manual_costs import ManualCost
from app.models.marts import MartFinanceReconciliation, MartSKUDaily, MartStockDaily
from app.models.product_cards import CoreSKU


class ExportService:
    CACHE_TTL_SECONDS = 600

    def __init__(self) -> None:
        self._cache: TTLMemoryCache[bytes] = TTLMemoryCache(
            default_ttl_seconds=self.CACHE_TTL_SECONDS
        )

    @staticmethod
    def excel_scalar(value: object) -> object:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (dict, list, tuple, set)):
            return str(value)
        return value

    def _xlsx_bytes(
        self, headers: list[str], rows: Iterable[Iterable[object]]
    ) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = "export"
        ws.append(headers)
        for row in rows:
            ws.append(list(row))
        output = BytesIO()
        wb.save(output)
        return output.getvalue()

    @staticmethod
    def _result_value(row: object, key: str) -> object | None:
        if hasattr(row, key):
            return getattr(row, key)
        mapping = getattr(row, "_mapping", None)
        if mapping is not None and key in mapping:
            return mapping[key]
        return None

    @staticmethod
    async def _table_signature(
        session: AsyncSession,
        *,
        model: type,
        account_id: int,
        date_column: object | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        extra_filters: list[object] | None = None,
    ) -> str:
        filters = [model.account_id == account_id]
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
        row_count = ExportService._result_value(row, "row_count") or 0
        updated_at = ExportService._result_value(row, "updated_at")
        max_date = ExportService._result_value(row, "max_date")
        payload = "|".join(
            [
                model.__tablename__,
                str(account_id),
                date_from.isoformat() if date_from is not None else "",
                date_to.isoformat() if date_to is not None else "",
                str(row_count),
                str(updated_at or ""),
                str(max_date or ""),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()

    @staticmethod
    def _cache_key(
        *,
        export_type: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        extra_key: str = "",
        data_version_hash: str,
    ) -> tuple[str, int, str | None, str | None, str, str]:
        return (
            export_type,
            account_id,
            date_from.isoformat() if date_from is not None else None,
            date_to.isoformat() if date_to is not None else None,
            extra_key,
            data_version_hash,
        )

    async def export_cached(
        self,
        *,
        session: AsyncSession,
        export_type: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        headers: list[str],
        rows: Iterable[Iterable[object]],
        data_version_hash: str,
        extra_key: str = "",
    ) -> tuple[bytes, str]:
        cache_key = self._cache_key(
            export_type=export_type,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            extra_key=extra_key,
            data_version_hash=data_version_hash,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached, "hit"
        payload = self._xlsx_bytes(headers, rows)
        self._cache.set(cache_key, payload)
        return payload, "miss"

    async def profit_by_sku_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> str:
        return await self._table_signature(
            session,
            model=MartSKUDaily,
            account_id=account_id,
            date_column=MartSKUDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )

    async def stock_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> str:
        return await self._table_signature(
            session,
            model=MartStockDaily,
            account_id=account_id,
            date_column=MartStockDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )

    async def reconciliation_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> str:
        return await self._table_signature(
            session,
            model=MartFinanceReconciliation,
            account_id=account_id,
            date_column=MartFinanceReconciliation.stat_date,
            date_from=date_from,
            date_to=date_to,
        )

    async def data_quality_version_hash(
        self, session: AsyncSession, *, account_id: int, only_open: bool
    ) -> str:
        extra_filters = [DataQualityIssue.resolved_at.is_(None)] if only_open else []
        return await self._table_signature(
            session,
            model=DataQualityIssue,
            account_id=account_id,
            extra_filters=extra_filters,
        )

    async def missing_costs_version_hash(
        self, session: AsyncSession, *, account_id: int
    ) -> str:
        core_hash = await self._table_signature(
            session, model=CoreSKU, account_id=account_id
        )
        cost_hash = await self._table_signature(
            session, model=ManualCost, account_id=account_id
        )
        return hashlib.sha1(
            f"{core_hash}|{cost_hash}".encode("utf-8"), usedforsecurity=False
        ).hexdigest()
