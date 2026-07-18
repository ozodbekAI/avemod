from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.models.auth import AuthRefreshToken, AuthUser


class AuthUserRepository(SQLAlchemyRepository[AuthUser]):
    def __init__(self) -> None:
        super().__init__(AuthUser)

    async def get_by_email(self, session: AsyncSession, email: str) -> AuthUser | None:
        return (
            await session.execute(select(AuthUser).where(AuthUser.email == email))
        ).scalar_one_or_none()


class AuthRefreshTokenRepository(SQLAlchemyRepository[AuthRefreshToken]):
    def __init__(self) -> None:
        super().__init__(AuthRefreshToken)

    async def get_by_fingerprint(
        self, session: AsyncSession, fingerprint: str
    ) -> AuthRefreshToken | None:
        return (
            await session.execute(
                select(AuthRefreshToken).where(
                    AuthRefreshToken.token_fingerprint == fingerprint
                )
            )
        ).scalar_one_or_none()
