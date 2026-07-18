from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class CoreSKU(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "core_sku"
    __dedupe_fields__ = (
        "account_id",
        "nm_id",
        "vendor_code",
        "tech_size",
        "chrt_id",
        "size_id",
        "barcode",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "nm_id",
            "vendor_code",
            "tech_size",
            "chrt_id",
            "size_id",
            "barcode",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nm_id: Mapped[int | None] = mapped_column(index=True, nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), index=True, nullable=True
    )
    supplier_article: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    sku: Mapped[str | None] = mapped_column(String(255), nullable=True)
    chrt_id: Mapped[int | None] = mapped_column(nullable=True)
    size_id: Mapped[int | None] = mapped_column(nullable=True)
    tech_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="active", nullable=False, index=True
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WBProductCard(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_product_cards"
    __table_args__ = (UniqueConstraint("account_id", "nm_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int] = mapped_column(index=True)
    imt_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nm_uuid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subject_id: Mapped[int | None] = mapped_column(nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), index=True, nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    need_kiz: Mapped[bool | None] = mapped_column(nullable=True)
    kiz_marked: Mapped[bool | None] = mapped_column(nullable=True)
    photos: Mapped[list | dict | None] = mapped_column(JSONB, nullable=True)
    video: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    dimensions: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at_wb: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at_wb: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBProductCardSize(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_product_card_sizes"

    product_card_id: Mapped[int] = mapped_column(
        ForeignKey("wb_product_cards.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    chrt_id: Mapped[int | None] = mapped_column(nullable=True)
    size_id: Mapped[int | None] = mapped_column(nullable=True)
    tech_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    skus: Mapped[list] = mapped_column(JSONB, default=list)


class WBProductCardCharacteristic(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_product_card_characteristics"

    product_card_id: Mapped[int] = mapped_column(
        ForeignKey("wb_product_cards.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    char_id: Mapped[int | None] = mapped_column(nullable=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value: Mapped[list | dict | str | None] = mapped_column(JSONB, nullable=True)


class WBProductCardTag(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_product_card_tags"

    product_card_id: Mapped[int] = mapped_column(
        ForeignKey("wb_product_cards.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    tag_id: Mapped[int] = mapped_column(index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    color: Mapped[str | None] = mapped_column(String(32), nullable=True)
