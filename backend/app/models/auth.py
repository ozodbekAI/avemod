from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class AuthUser(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "auth_users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    refresh_tokens: Mapped[list["AuthRefreshToken"]] = relationship(
        back_populates="user"
    )
    account_access: Mapped[list["AuthUserAccountAccess"]] = relationship(
        back_populates="user"
    )


class AuthUserAccountAccess(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "auth_user_account_access"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "account_id", name="uq_auth_user_account_access_user_account"
        ),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), default="viewer", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[AuthUser] = relationship(back_populates="account_access")


class AuthRefreshToken(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "auth_refresh_tokens"
    __table_args__ = (UniqueConstraint("token_fingerprint"),)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE")
    )
    token_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[AuthUser] = relationship(back_populates="refresh_tokens")
