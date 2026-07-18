from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class ABTestCompany(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "ab_test_companies"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    wb_advert_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    nm_id: Mapped[int] = mapped_column(BigInteger, index=True)
    product_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_product_cards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(32), default="created", nullable=False, index=True
    )
    from_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_slots: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    keep_winner_as_main: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    delete_test_photos: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    photos_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    views_per_photo: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cpm: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    spend_rub: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_total_shows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_total_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_photo_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    winner_photo_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    original_media_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    current_uploaded_wb_url: Mapped[str | None] = mapped_column(
        String(1024), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    photos: Mapped[list["ABTestPhoto"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        order_by="ABTestPhoto.order",
    )


class ABTestPhoto(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "ab_test_photos"

    company_id: Mapped[int] = mapped_column(
        ForeignKey("ab_test_companies.id", ondelete="CASCADE"), index=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)
    file_url: Mapped[str] = mapped_column(String(2048))
    wb_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    preview_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    shows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_winner: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    company: Mapped[ABTestCompany] = relationship(back_populates="photos")
