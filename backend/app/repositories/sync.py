from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.models.sync import WBSyncCursor, WBSyncRun


class WBSyncCursorRepository(SQLAlchemyRepository[WBSyncCursor]):
    def __init__(self) -> None:
        super().__init__(WBSyncCursor)

    async def get_for_domain(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        domain: str,
        cursor_key: str = "default",
    ) -> WBSyncCursor | None:
        return (
            await session.execute(
                select(WBSyncCursor).where(
                    WBSyncCursor.account_id == account_id,
                    WBSyncCursor.domain == domain,
                    WBSyncCursor.cursor_key == cursor_key,
                )
            )
        ).scalar_one_or_none()


class WBSyncRunRepository(SQLAlchemyRepository[WBSyncRun]):
    def __init__(self) -> None:
        super().__init__(WBSyncRun)
