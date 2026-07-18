from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class DataQualityIssue(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "data_quality_issues"

    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    domain: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), default="warning")
    code: Mapped[str] = mapped_column(String(128), index=True)
    entity_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    source_table: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    classification_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    classification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    classified_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
    )
    classified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    financial_final_blocker_override: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    effective_financial_final_blocker: Mapped[bool] = mapped_column(
        Boolean, default=False, index=True
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
