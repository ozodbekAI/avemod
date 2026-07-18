from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.documents import DocumentRepository


class DocumentsService:
    def __init__(self) -> None:
        self.repo = DocumentRepository()

    async def list_documents(
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
        return await self.repo.list_filtered(
            session,
            account_id=account_id,
            category=category,
            document_key=document_key,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
