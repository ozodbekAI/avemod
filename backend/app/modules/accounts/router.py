from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.accounts import WBAccount
from app.models.auth import AuthUser
from app.schemas.accounts import (
    WBAccountCreate,
    WBAccountRead,
    WBTokenRead,
    WBTokenUpsert,
)
from app.services.accounts import AccountService
from app.services.auth import (
    get_current_superuser,
    get_current_user,
    list_user_account_access,
)

router = APIRouter(tags=["accounts"])
service = AccountService()


@router.get("/accounts", response_model=Page[WBAccountRead])
async def list_accounts(
    include_inactive: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[WBAccountRead]:
    stmt = select(WBAccount).order_by(WBAccount.id)
    count_stmt = select(func.count()).select_from(WBAccount)
    if not include_inactive:
        stmt = stmt.where(WBAccount.is_active.is_(True))
        count_stmt = count_stmt.where(WBAccount.is_active.is_(True))
    if not current_user.is_superuser:
        allowed_account_ids = [
            account_id
            for account_id, _role in await list_user_account_access(
                session, current_user
            )
        ]
        stmt = stmt.where(WBAccount.id.in_(allowed_account_ids))
        count_stmt = count_stmt.where(WBAccount.id.in_(allowed_account_ids))
    total = int((await session.execute(count_stmt)).scalar_one())
    items = list((await session.execute(stmt.limit(limit).offset(offset))).scalars())
    return Page(total=total, limit=limit, offset=offset, items=items)


@router.post(
    "/accounts", response_model=WBAccountRead, status_code=status.HTTP_201_CREATED
)
async def create_account(
    payload: WBAccountCreate,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> WBAccountRead:
    account = await service.create_account(session, payload)
    await session.commit()
    await session.refresh(account)
    return account


@router.get("/accounts/{account_id}/tokens", response_model=Page[WBTokenRead])
async def list_tokens(
    account_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[WBTokenRead]:
    items = await service.tokens.list_for_account(session, account_id)
    total = len(items)
    return Page(
        total=total, limit=limit, offset=offset, items=items[offset : offset + limit]
    )


@router.post(
    "/accounts/{account_id}/tokens",
    response_model=WBTokenRead,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_token(
    account_id: int,
    payload: WBTokenUpsert,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> WBTokenRead:
    token = await service.upsert_token(session, account_id, payload)
    await session.commit()
    await session.refresh(token)
    return token
