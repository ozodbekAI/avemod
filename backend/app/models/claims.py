from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin


class ClaimDetectionRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "claim_detection_runs"
    __table_args__ = (
        Index(
            "ix_claim_detection_runs_account_detector_started",
            "account_id",
            "detector_type",
            "started_at",
        ),
        Index("ix_claim_detection_runs_account_status", "account_id", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    detector_type: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    date_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    date_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    source_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    cursor_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    candidates_found: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidates_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class ClaimCandidate(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "claim_candidates"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "fingerprint", name="uq_claim_candidates_account_fingerprint"
        ),
        Index(
            "ix_claim_candidates_account_detector_status",
            "account_id",
            "detector_type",
            "status",
        ),
        Index("ix_claim_candidates_account_nm", "account_id", "nm_id"),
        Index("ix_claim_candidates_account_case", "account_id", "case_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    detector_type: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    source_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    external_reference: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sku_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    supply_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    report_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    order_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sale_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    warehouse_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    business_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason_code: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    severity: Mapped[str] = mapped_column(
        String(32), default="medium", nullable=False, index=True
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    expected_amount: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity_affected: Mapped[float | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence_summary_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    source_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detection_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("claim_detection_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    case_id: Mapped[int | None] = mapped_column(
        ForeignKey("operator_cases.id", ondelete="SET NULL"), nullable=True, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
