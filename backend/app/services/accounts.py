from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_wb_token, encrypt_wb_token
from app.models.accounts import WBAPIToken, WBAccount
from app.repositories.accounts import WBAPITokenRepository, WBAccountRepository
from app.schemas.accounts import WBAccountCreate, WBTokenUpsert


class AccountService:
    def __init__(self) -> None:
        self.accounts = WBAccountRepository()
        self.tokens = WBAPITokenRepository()

    async def create_account(
        self, session: AsyncSession, payload: WBAccountCreate
    ) -> WBAccount:
        existing = (
            await session.execute(
                select(WBAccount).where(WBAccount.name == payload.name)
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Account already exists")
        return await self.accounts.create(session, **payload.model_dump())

    async def upsert_token(
        self,
        session: AsyncSession,
        account_id: int,
        payload: WBTokenUpsert,
    ) -> WBAPIToken:
        existing = await self.tokens.get_active_token(
            session, account_id, payload.category
        )
        encrypted = encrypt_wb_token(payload.token)
        if existing:
            existing.token_encrypted = encrypted
            existing.comment = payload.comment
            existing.is_active = payload.is_active
            await session.flush()
            return existing
        token = WBAPIToken(
            account_id=account_id,
            category=payload.category,
            token_encrypted=encrypted,
            comment=payload.comment,
            is_active=payload.is_active,
        )
        session.add(token)
        await session.flush()
        return token

    async def get_decrypted_token(
        self, session: AsyncSession, account_id: int, category: str
    ) -> str:
        token = await self.tokens.get_active_token(session, account_id, category)
        if token is None:
            raise HTTPException(
                status_code=400,
                detail=f"WB token for category '{category}' is not configured",
            )
        return decrypt_wb_token(token.token_encrypted)
