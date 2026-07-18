from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin


class RawWBAPIResponse(BigIntPKMixin, Base):
    __tablename__ = "raw_wb_api_responses"
    __table_args__ = (
        Index("ix_raw_wb_api_responses_account_endpoint", "account_id", "endpoint"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    api_category: Mapped[str] = mapped_column(String(64), index=True)
    endpoint: Mapped[str] = mapped_column(String(255), index=True)
    http_method: Mapped[str] = mapped_column(String(16), default="GET")
    request_params: Mapped[dict] = mapped_column(JSONB, default=dict)
    request_body: Mapped[dict | list | None] = mapped_column(JSONB, nullable=True)
    response_json: Mapped[dict | list] = mapped_column(JSONB)
    response_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer)
    is_success: Mapped[bool] = mapped_column(Boolean, default=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hash: Mapped[str] = mapped_column(String(64), index=True)
    request_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    response_fingerprint: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
