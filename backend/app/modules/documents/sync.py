from __future__ import annotations

from datetime import timedelta

from app.core.parsing import parse_date
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.modules.documents.client import DocumentsClient
from app.repositories.documents import DocumentCategoryRepository, DocumentRepository


class DocumentsSyncService(DomainSyncBase):
    domain = "documents"
    category = "documents"

    def __init__(self) -> None:
        super().__init__()
        self.client = DocumentsClient(self)
        self.categories_repo = DocumentCategoryRepository()
        self.documents_repo = DocumentRepository()

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        categories_payload = await self.client.categories(
            session, account_id=account.id
        )
        categories = categories_payload.get("data", {}).get("categories", [])
        await self.categories_repo.upsert_many(
            session,
            [
                {
                    "account_id": account.id,
                    "name": item.get("name"),
                    "title": item.get("title"),
                    "locale": "ru",
                    "payload": item,
                }
                for item in categories
            ],
            conflict_fields=["account_id", "name"],
        )
        begin_time = (
            backfill_from or (utcnow().date() - timedelta(days=30))
        ).isoformat()
        end_time = (backfill_to or utcnow().date()).isoformat()
        documents_payload = await self.client.documents(
            session, account_id=account.id, begin_time=begin_time, end_time=end_time
        )
        documents = documents_payload.get("data", {}).get(
            "documents", []
        ) or documents_payload.get("documents", [])
        await self.documents_repo.upsert_many(
            session,
            [
                {
                    "account_id": account.id,
                    "document_key": str(
                        item.get("id") or item.get("number") or item.get("name")
                    ),
                    "title": item.get("title") or item.get("name"),
                    "category": item.get("category"),
                    "document_date": parse_date(item.get("date")),
                    "payload": item,
                }
                for item in documents
            ],
            conflict_fields=["account_id", "document_key"],
        )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={"beginTime": begin_time, "endTime": end_time},
        )
        return {"status": "completed", "documents": len(documents)}
