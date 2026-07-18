from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBPrice(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_prices"
    __table_args__ = (UniqueConstraint("account_id", "nm_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int] = mapped_column(index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    currency_iso_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    discount: Mapped[int | None] = mapped_column(nullable=True)
    club_discount: Mapped[int | None] = mapped_column(nullable=True)
    editable_size_price: Mapped[bool | None] = mapped_column(nullable=True)
    is_bad_turnover: Mapped[bool | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBPriceSnapshot(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_price_snapshots"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int] = mapped_column(index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBPriceSize(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_price_sizes"
    __table_args__ = (UniqueConstraint("account_id", "nm_id", "size_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int] = mapped_column(index=True)
    size_id: Mapped[int] = mapped_column(index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tech_size_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    discounted_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    club_discounted_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    discount: Mapped[int | None] = mapped_column(nullable=True)
    club_discount: Mapped[int | None] = mapped_column(nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBPriceUploadTask(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_price_upload_tasks"
    __table_args__ = (UniqueConstraint("account_id", "source", "task_key"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    source: Mapped[str] = mapped_column(String(32))
    task_key: Mapped[str] = mapped_column(String(128))
    status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBPriceUploadTaskRow(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_price_upload_task_rows"

    upload_task_id: Mapped[int] = mapped_column(
        ForeignKey("wb_price_upload_tasks.id", ondelete="CASCADE")
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_text: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class WBPriceQuarantine(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_price_quarantine"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
