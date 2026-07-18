from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.models.accounts import WBAPIToken, WBAccount


class WBAccountRepository(SQLAlchemyRepository[WBAccount]):
    def __init__(self) -> None:
        super().__init__(WBAccount)


class WBAPITokenRepository(SQLAlchemyRepository[WBAPIToken]):
    def __init__(self) -> None:
        super().__init__(WBAPIToken)

    async def list_for_account(
        self, session: AsyncSession, account_id: int
    ) -> list[WBAPIToken]:
        return list(
            (
                await session.execute(
                    select(WBAPIToken)
                    .where(WBAPIToken.account_id == account_id)
                    .order_by(WBAPIToken.category)
                )
            ).scalars()
        )

    async def get_active_token(
        self, session: AsyncSession, account_id: int, category: str
    ) -> WBAPIToken | None:
        return (
            await session.execute(
                select(WBAPIToken).where(
                    WBAPIToken.account_id == account_id,
                    WBAPIToken.category == category,
                    WBAPIToken.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
