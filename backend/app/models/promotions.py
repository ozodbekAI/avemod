from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBPromotionCalendar(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_promotion_calendar"
    __table_args__ = (UniqueConstraint("account_id", "promotion_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    promotion_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    promo_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    advantages: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    in_promo_action_leftovers: Mapped[int | None] = mapped_column(nullable=True)
    in_promo_action_total: Mapped[int | None] = mapped_column(nullable=True)
    not_in_promo_action_leftovers: Mapped[int | None] = mapped_column(nullable=True)
    not_in_promo_action_total: Mapped[int | None] = mapped_column(nullable=True)
    participation_percentage: Mapped[int | None] = mapped_column(nullable=True)
    exception_products_count: Mapped[int | None] = mapped_column(nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBPromotionNomenclature(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_promotion_nomenclatures"
    __table_args__ = (
        UniqueConstraint("account_id", "promotion_id", "nm_id", "in_action"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    promotion_id: Mapped[int] = mapped_column(index=True)
    nm_id: Mapped[int] = mapped_column(index=True)
    in_action: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    plan_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    discount: Mapped[int | None] = mapped_column(nullable=True)
    plan_discount: Mapped[int | None] = mapped_column(nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
