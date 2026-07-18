from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class WBSyncCursor(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "wb_sync_cursors"
    __table_args__ = (UniqueConstraint("account_id", "domain", "cursor_key"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    domain: Mapped[str] = mapped_column(String(64), index=True)
    cursor_key: Mapped[str] = mapped_column(String(128), default="default")
    cursor_value: Mapped[dict] = mapped_column(JSONB, default=dict)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="idle")


class WBSyncRun(BigIntPKMixin, Base):
    __tablename__ = "wb_sync_runs"

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    domain: Mapped[str] = mapped_column(String(64), index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="manual")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    is_backfill: Mapped[bool] = mapped_column(Boolean, default=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
