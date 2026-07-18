from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.data_quality import DataQualityIssue


class DataQualityRepository(SQLAlchemyRepository[DataQualityIssue]):
    def __init__(self) -> None:
        super().__init__(DataQualityIssue)

    async def get_open_issue(
        self,
        session: AsyncSession,
        *,
        domain: str,
        code: str,
        account_id: int | None,
        entity_key: str | None,
    ) -> DataQualityIssue | None:
        stmt = select(DataQualityIssue).where(
            DataQualityIssue.domain == domain,
            DataQualityIssue.code == code,
            DataQualityIssue.resolved_at.is_(None),
        )
        if account_id is None:
            stmt = stmt.where(DataQualityIssue.account_id.is_(None))
        else:
            stmt = stmt.where(DataQualityIssue.account_id == account_id)
        if entity_key is None:
            stmt = stmt.where(DataQualityIssue.entity_key.is_(None))
        else:
            stmt = stmt.where(DataQualityIssue.entity_key == entity_key)
        return (await session.execute(stmt.limit(1))).scalar_one_or_none()

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        only_open: bool = False,
        codes: list[str] | None = None,
        excluded_codes: list[str] | None = None,
        severities: list[str] | None = None,
        domains: list[str] | None = None,
        source_tables: list[str] | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        status: str | None = None,
        classification_statuses: list[str] | None = None,
        financial_final_blocker: bool | None = None,
        age_buckets: list[str] | None = None,
        detected_from: date | None = None,
        detected_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> Page[DataQualityIssue]:
        sort_map = {
            "detected_at": DataQualityIssue.detected_at,
            "resolved_at": DataQualityIssue.resolved_at,
            "severity": DataQualityIssue.severity,
            "code": DataQualityIssue.code,
            "domain": DataQualityIssue.domain,
            "sku_id": DataQualityIssue.sku_id,
            "nm_id": DataQualityIssue.nm_id,
        }
        sort_column = sort_map.get(sort_by or "", DataQualityIssue.detected_at)
        stmt = select(DataQualityIssue).order_by(
            apply_sort_direction(sort_column, sort_dir),
            DataQualityIssue.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(DataQualityIssue.account_id == account_id)
        if only_open or status == "open":
            stmt = stmt.where(DataQualityIssue.resolved_at.is_(None))
        elif status == "resolved":
            stmt = stmt.where(DataQualityIssue.resolved_at.is_not(None))
        elif status == "reopened":
            stmt = stmt.where(
                DataQualityIssue.resolved_at.is_(None),
                DataQualityIssue.payload["reopenComment"].astext.is_not(None),
            )
        if codes:
            stmt = stmt.where(DataQualityIssue.code.in_(codes))
        if excluded_codes:
            stmt = stmt.where(DataQualityIssue.code.notin_(excluded_codes))
        if severities:
            stmt = stmt.where(DataQualityIssue.severity.in_(severities))
        if domains:
            stmt = stmt.where(DataQualityIssue.domain.in_(domains))
        if source_tables:
            stmt = stmt.where(DataQualityIssue.source_table.in_(source_tables))
        if sku_id is not None:
            stmt = stmt.where(DataQualityIssue.sku_id == sku_id)
        if nm_id is not None:
            stmt = stmt.where(DataQualityIssue.nm_id == nm_id)
        if classification_statuses:
            stmt = stmt.where(
                func.lower(
                    func.coalesce(DataQualityIssue.classification_status, "")
                ).in_([value.lower() for value in classification_statuses])
            )
        if financial_final_blocker is True:
            stmt = stmt.where(
                DataQualityIssue.effective_financial_final_blocker.is_(True)
            )
        elif financial_final_blocker is False:
            stmt = stmt.where(
                DataQualityIssue.effective_financial_final_blocker.is_(False)
            )
        if age_buckets:
            stmt = stmt.where(
                DataQualityIssue.payload["ageBucket"].astext.in_(age_buckets)
            )
        if detected_from is not None:
            stmt = stmt.where(
                DataQualityIssue.detected_at
                >= datetime.combine(detected_from, time.min)
            )
        if detected_to is not None:
            stmt = stmt.where(
                DataQualityIssue.detected_at <= datetime.combine(detected_to, time.max)
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
