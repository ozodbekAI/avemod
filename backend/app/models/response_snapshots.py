from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class APIResponseSnapshot(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "api_response_snapshots"
    __table_args__ = (
        UniqueConstraint("namespace", "endpoint_key", "account_id", "params_hash"),
        Index(
            "ix_api_snapshots_lookup_ready",
            "namespace",
            "endpoint_key",
            "account_id",
            "params_hash",
            "snapshot_status",
        ),
        Index(
            "ix_api_snapshots_refresh_due",
            "namespace",
            "account_id",
            "snapshot_status",
            "expires_at",
            "access_count",
            "last_accessed_at",
        ),
    )

    namespace: Mapped[str] = mapped_column(String(64), index=True)
    endpoint_key: Mapped[str] = mapped_column(String(128), index=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    params_hash: Mapped[str] = mapped_column(String(64), index=True)
    request_params: Mapped[dict] = mapped_column(JSONB, default=dict)
    response_model: Mapped[str] = mapped_column(String(128), default="")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    snapshot_status: Mapped[str] = mapped_column(
        String(32), default="ready", index=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_accessed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
