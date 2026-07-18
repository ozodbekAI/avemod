from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
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


class CardQualityAnalysisRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "card_quality_analysis_runs"
    __table_args__ = (
        Index("ix_card_quality_analysis_runs_account_status", "account_id", "status"),
        Index(
            "ix_card_quality_analysis_runs_account_started", "account_id", "started_at"
        ),
        Index(
            "ix_card_quality_analysis_runs_account_run_active",
            "account_id",
            "run_type",
            "status",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    run_type: Mapped[str] = mapped_column(
        String(64), default="single_product", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    cards_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    eligible_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_analyzed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_skipped_unchanged: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    cards_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_clean: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cards_with_issues: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issues_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    issues_resolved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_revision: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cursor_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    last_processed_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class CardQualitySnapshot(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "card_quality_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "nm_id",
            "source_revision",
            name="uq_card_quality_snapshots_account_nm_revision",
        ),
        Index("ix_card_quality_snapshots_account_nm", "account_id", "nm_id"),
        Index("ix_card_quality_snapshots_account_status", "account_id", "status"),
        Index("ix_card_quality_snapshots_analyzed_at", "analyzed_at"),
        Index(
            "ix_card_quality_snapshots_current_lookup",
            "account_id",
            "nm_id",
            "analyzed_at",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int] = mapped_column(BigInteger, index=True)
    source_card_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_product_cards.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source_revision: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    characteristics_json: Mapped[list | dict] = mapped_column(JSONB, default=list)
    media_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    photos_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    video_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    analyzed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="not_analyzed", nullable=False, index=True
    )
    summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class CardQualityFixedFileEntry(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "card_quality_fixed_file_entries"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "nm_id",
            "char_name",
            name="uq_card_quality_fixed_account_nm_char",
        ),
        Index("ix_card_quality_fixed_account_nm", "account_id", "nm_id"),
        Index("ix_card_quality_fixed_account_char", "account_id", "char_name"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int] = mapped_column(BigInteger, index=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    char_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fixed_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class CardQualityIssue(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "card_quality_issues"
    __table_args__ = (
        Index("ix_card_quality_issues_account_nm", "account_id", "nm_id"),
        Index(
            "ix_card_quality_issues_account_status_severity",
            "account_id",
            "status",
            "severity",
        ),
        Index("ix_card_quality_issues_fingerprint", "fingerprint"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int] = mapped_column(BigInteger, index=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("card_quality_snapshots.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    issue_code: Mapped[str] = mapped_column(String(128), index=True)
    category: Mapped[str] = mapped_column(String(64), index=True)
    severity: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(255))
    business_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    expected_value_json: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    alternatives_json: Mapped[list] = mapped_column(JSONB, default=list)
    charc_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    allowed_values_json: Mapped[list] = mapped_column(JSONB, default=list)
    error_details_json: Mapped[list] = mapped_column(JSONB, default=list)
    ai_suggested_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_alternatives_json: Mapped[list] = mapped_column(JSONB, default=list)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_human_check: Mapped[bool] = mapped_column(default=False, nullable=False)
    ai_reason_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_reason_full: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    ai_used_sources_json: Mapped[list] = mapped_column(JSONB, default=list)
    photo_evidence_json: Mapped[list] = mapped_column(JSONB, default=list)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score_impact: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    fixed_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    fixed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    fixed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    postponed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(128), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class CardQualityIssueStatusHistory(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "card_quality_issue_status_history"
    __table_args__ = (
        Index(
            "ix_card_quality_issue_status_history_account_issue",
            "account_id",
            "issue_id",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    issue_id: Mapped[int] = mapped_column(
        ForeignKey("card_quality_issues.id", ondelete="CASCADE"), index=True
    )
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    changed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
