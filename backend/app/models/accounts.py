from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Boolean, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBAPICategory(StrEnum):
    CONTENT = "content"
    PRICES = "prices"
    STATISTICS = "statistics"
    ANALYTICS = "analytics"
    FINANCE = "finance"
    PROMOTION = "promotion"
    FEEDBACKS_QUESTIONS = "feedbacks_questions"
    BUYER_CHAT = "buyer_chat"
    BUYER_RETURNS = "buyer_returns"
    SUPPLIES = "supplies"
    DOCUMENTS = "documents"
    TARIFFS = "tariffs"
    USERS = "users"


class WBAccount(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_accounts"

    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    api_tokens: Mapped[list["WBAPIToken"]] = relationship(back_populates="account")


class WBAPIToken(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_api_tokens"
    __table_args__ = (UniqueConstraint("account_id", "category"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    category: Mapped[str] = mapped_column(String(64), index=True)
    token_encrypted: Mapped[str] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    account: Mapped[WBAccount] = relationship(back_populates="api_tokens")
