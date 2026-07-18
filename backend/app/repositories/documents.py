from __future__ import annotations

from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.documents import WBDocument, WBDocumentCategory


class DocumentCategoryRepository(SQLAlchemyRepository[WBDocumentCategory]):
    def __init__(self) -> None:
        super().__init__(WBDocumentCategory)


class DocumentRepository(SQLAlchemyRepository[WBDocument]):
    def __init__(self) -> None:
        super().__init__(WBDocument)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        category: str | None = None,
        document_key: str | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        sort_map = {
            "document_date": WBDocument.document_date,
            "document_key": WBDocument.document_key,
            "category": WBDocument.category,
            "title": WBDocument.title,
        }
        sort_column = sort_map.get(sort_by or "", WBDocument.document_date)
        stmt = select(WBDocument).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBDocument.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBDocument.account_id == account_id)
        if category is not None:
            stmt = stmt.where(WBDocument.category.ilike(f"%{category}%"))
        if document_key is not None:
            stmt = stmt.where(WBDocument.document_key.ilike(f"%{document_key}%"))
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBDocument.document_key.ilike(pattern),
                    WBDocument.title.ilike(pattern),
                    WBDocument.category.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(WBDocument.document_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBDocument.document_date <= date_to)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
