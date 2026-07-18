from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.auth import (
    CurrentUserRead,
    LoginRequest,
    MessageResponse,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from app.services.auth import (
    AuthService,
    allow_bootstrap_or_superuser,
    get_current_user,
    get_current_superuser,
)

router = APIRouter(tags=["auth"])
auth_service = AuthService()


@router.post("/auth/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPair:
    tokens = await auth_service.login(session, payload)
    await session.commit()
    return tokens


@router.post("/auth/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenPair:
    tokens = await auth_service.refresh(session, payload.refresh_token)
    await session.commit()
    return tokens


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    _: AuthUser | None = Depends(allow_bootstrap_or_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> UserRead:
    user = await auth_service.create_user(session, payload)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/users", response_model=Page[UserRead])
async def list_users(
    limit: int = 50,
    offset: int = 0,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> Page[UserRead]:
    total = int(
        (await session.execute(select(func.count()).select_from(AuthUser))).scalar_one()
    )
    items = list(
        (
            await session.execute(
                select(AuthUser).order_by(AuthUser.id).limit(limit).offset(offset)
            )
        ).scalars()
    )
    return Page(total=total, limit=limit, offset=offset, items=items)


@router.get("/auth/me", response_model=CurrentUserRead)
async def me(
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CurrentUserRead:
    return await auth_service.get_current_user_read(session, current_user)


@router.post("/auth/logout", response_model=MessageResponse)
async def logout(
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    revoked = await auth_service.logout(session, current_user)
    await session.commit()
    return MessageResponse(message=f"revoked {revoked} refresh tokens")


@router.get("/auth/ping", response_model=MessageResponse)
async def auth_ping(
    _: AuthUser = Depends(get_current_superuser),
) -> MessageResponse:
    return MessageResponse(message="authenticated")
