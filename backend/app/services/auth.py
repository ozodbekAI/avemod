from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    fingerprint,
    hash_password,
    verify_password,
)
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.auth import AuthRefreshToken, AuthUser, AuthUserAccountAccess
from app.repositories.auth import AuthRefreshTokenRepository, AuthUserRepository
from app.schemas.auth import (
    CurrentUserRead,
    LoginRequest,
    TokenPair,
    UserAccountAccess,
    UserCreate,
)

bearer_scheme = HTTPBearer(auto_error=False)


class AuthService:
    def __init__(self) -> None:
        self.users = AuthUserRepository()
        self.refresh_tokens = AuthRefreshTokenRepository()

    async def create_user(
        self,
        session: AsyncSession,
        payload: UserCreate,
        *,
        is_superuser: bool = False,
    ) -> AuthUser:
        existing = await self.users.get_by_email(session, payload.email)
        if existing:
            raise HTTPException(status_code=409, detail="User already exists")
        existing_user_count = (
            await session.execute(select(func.count()).select_from(AuthUser))
        ).scalar_one()
        effective_superuser = is_superuser or existing_user_count == 0
        user = await self.users.create(
            session,
            email=payload.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            is_active=True,
            is_superuser=effective_superuser,
        )
        return user

    async def login(self, session: AsyncSession, payload: LoginRequest) -> TokenPair:
        user = await self.users.get_by_email(session, payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Inactive user")
        return await self._issue_tokens(session, user)

    async def refresh(self, session: AsyncSession, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token, refresh=True)
        except TokenError as exc:
            raise HTTPException(
                status_code=401, detail="Invalid refresh token"
            ) from exc
        token_row = await self.refresh_tokens.get_by_fingerprint(
            session, fingerprint(refresh_token)
        )
        if (
            token_row is None
            or token_row.revoked_at is not None
            or token_row.expires_at < utcnow()
        ):
            raise HTTPException(
                status_code=401, detail="Refresh token expired or revoked"
            )
        user = await session.get(AuthUser, int(payload["sub"]))
        if user is None or not user.is_active:
            raise HTTPException(status_code=401, detail="User not found")
        token_row.revoked_at = utcnow()
        tokens = await self._issue_tokens(session, user)
        return tokens

    async def _issue_tokens(self, session: AsyncSession, user: AuthUser) -> TokenPair:
        last_error: IntegrityError | None = None
        for _ in range(3):
            access_token = create_access_token(str(user.id))
            refresh_token = create_refresh_token(str(user.id))
            session.add(
                AuthRefreshToken(
                    user_id=user.id,
                    token_fingerprint=fingerprint(refresh_token),
                    expires_at=utcnow() + timedelta(days=14),
                )
            )
            try:
                await session.flush()
                return TokenPair(access_token=access_token, refresh_token=refresh_token)
            except IntegrityError as exc:
                await session.rollback()
                last_error = exc
        raise HTTPException(
            status_code=409, detail="Could not issue refresh token"
        ) from last_error

    async def get_current_user_read(
        self, session: AsyncSession, user: AuthUser
    ) -> CurrentUserRead:
        roles = ["superuser"] if user.is_superuser else ["user"]
        permissions = (
            [
                "accounts:read",
                "accounts:write",
                "sync:run",
                "control_tower:write",
                "dq:write",
            ]
            if user.is_superuser
            else ["accounts:read"]
        )
        account_rows = await list_user_account_access(session, user)
        return CurrentUserRead(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            is_active=user.is_active,
            is_superuser=user.is_superuser,
            created_at=user.created_at,
            roles=roles,
            accounts=[
                UserAccountAccess(id=int(account_id), role=role)
                for account_id, role in account_rows
            ],
            permissions=permissions,
        )

    async def logout(self, session: AsyncSession, user: AuthUser) -> int:
        rows = list(
            (
                await session.execute(
                    select(AuthRefreshToken).where(
                        AuthRefreshToken.user_id == user.id,
                        AuthRefreshToken.revoked_at.is_(None),
                    )
                )
            ).scalars()
        )
        revoked = 0
        now = utcnow()
        for row in rows:
            row.revoked_at = now
            revoked += 1
        await session.flush()
        return revoked


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db_session),
) -> AuthUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    user = await session.get(AuthUser, int(payload["sub"]))
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


async def get_current_superuser(
    user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return user


async def list_user_account_access(
    session: AsyncSession, user: AuthUser
) -> list[tuple[int, str]]:
    if user.is_superuser:
        account_ids = list(
            (
                await session.execute(select(WBAccount.id).order_by(WBAccount.id))
            ).scalars()
        )
        return [(int(account_id), "admin") for account_id in account_ids]

    rows = list(
        (
            await session.execute(
                select(AuthUserAccountAccess.account_id, AuthUserAccountAccess.role)
                .join(WBAccount, WBAccount.id == AuthUserAccountAccess.account_id)
                .where(
                    AuthUserAccountAccess.user_id == user.id,
                    WBAccount.is_active.is_(True),
                )
                .order_by(
                    AuthUserAccountAccess.is_default.desc(),
                    AuthUserAccountAccess.account_id.asc(),
                )
            )
        ).all()
    )
    return [(int(account_id), str(role or "viewer")) for account_id, role in rows]


async def resolve_user_account(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
    require_account: bool = False,
) -> WBAccount | None:
    if account_id is not None:
        account = await session.get(WBAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if user.is_superuser:
            return account
        allowed_ids = {
            item[0] for item in await list_user_account_access(session, user)
        }
        if int(account.id) not in allowed_ids:
            raise HTTPException(status_code=403, detail="Account access forbidden")
        return account

    if user.is_superuser:
        rows = list(
            (
                await session.execute(
                    select(WBAccount)
                    .where(WBAccount.is_active.is_(True))
                    .order_by(WBAccount.id)
                )
            ).scalars()
        )
    else:
        rows = list(
            (
                await session.execute(
                    select(WBAccount)
                    .join(
                        AuthUserAccountAccess,
                        AuthUserAccountAccess.account_id == WBAccount.id,
                    )
                    .where(
                        AuthUserAccountAccess.user_id == user.id,
                        WBAccount.is_active.is_(True),
                    )
                    .order_by(
                        AuthUserAccountAccess.is_default.desc(), WBAccount.id.asc()
                    )
                )
            ).scalars()
        )

    if len(rows) == 1:
        return rows[0]
    if require_account:
        detail = (
            "account_id is required" if rows else "No accessible account is available"
        )
        raise HTTPException(status_code=400, detail=detail)
    return None


async def resolve_user_account_role(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int,
) -> str:
    """Return the user's finance account role after account access is resolved."""
    if user.is_superuser:
        return "superuser"
    for accessible_account_id, role in await list_user_account_access(session, user):
        if int(accessible_account_id) == int(account_id):
            return str(role or "viewer").lower()
    raise HTTPException(status_code=403, detail="Account access forbidden")


async def require_account_role(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int,
    allowed_roles: set[str],
) -> str:
    """Require an account-scoped role without weakening superuser access."""
    role = await resolve_user_account_role(session, user, account_id=account_id)
    normalized_role = str(role or "viewer").lower()
    normalized_allowed = {str(item).lower() for item in allowed_roles}
    if normalized_role == "superuser" or normalized_role in normalized_allowed:
        return normalized_role
    raise HTTPException(status_code=403, detail="Account role is not allowed")


async def allow_bootstrap_or_superuser(
    session: AsyncSession = Depends(get_db_session),
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthUser | None:
    user_count = (
        await session.execute(select(func.count()).select_from(AuthUser))
    ).scalar_one()
    if user_count == 0:
        return None
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid access token") from exc
    user = await session.get(AuthUser, int(payload["sub"]))
    if user is None or not user.is_active or not user.is_superuser:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user
