from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
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


class GroupingSettings(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "grouping_settings"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_grouping_settings_account"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="beta", nullable=False)
    default_scenario: Mapped[str] = mapped_column(
        String(64), default="article_family", nullable=False
    )
    minimum_confidence: Mapped[float] = mapped_column(
        Numeric(18, 4), default=0.55, nullable=False
    )
    maximum_risk: Mapped[float] = mapped_column(
        Numeric(18, 4), default=0.65, nullable=False
    )
    allow_cross_brand: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    allow_cross_subject: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    require_color_compatibility: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    require_identity_evidence: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    include_low_data_products: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    scenario_settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class GroupingRun(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "grouping_runs"
    __table_args__ = (
        Index("ix_grouping_runs_account_created_id", "account_id", "created_at", "id"),
        Index("ix_grouping_runs_account_status", "account_id", "status"),
        Index("ix_grouping_runs_account_scenario", "account_id", "scenario"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    scenario: Mapped[str] = mapped_column(
        String(64), default="article_family", nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cursor_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    eligible_products: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    products_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_pairs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    candidate_groups: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    recommendations_created: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    recommendations_updated: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    recommendations_rejected_by_constraints: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class GroupingProductSnapshot(BigIntPKMixin, Base):
    __tablename__ = "grouping_product_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "run_id", "nm_id", name="uq_grouping_snapshots_account_run_nm"
        ),
        Index("ix_grouping_snapshots_account_nm", "account_id", "nm_id"),
        Index("ix_grouping_snapshots_run", "run_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("grouping_runs.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int] = mapped_column(index=True)
    imt_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    article_core: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    article_base_core: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    subject_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    color_normalized: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True
    )
    characteristics_json: Mapped[list | dict] = mapped_column(JSONB, default=list)
    sizes_json: Mapped[list | dict] = mapped_column(JSONB, default=list)
    barcodes_json: Mapped[list | dict] = mapped_column(JSONB, default=list)
    media_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    stock_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    finance_summary_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    source_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class GroupingCandidate(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "grouping_candidates"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "scenario",
            "fingerprint",
            name="uq_grouping_candidates_account_scenario_fingerprint",
        ),
        Index("ix_grouping_candidates_account_status", "account_id", "status"),
        Index("ix_grouping_candidates_account_anchor", "account_id", "anchor_nm_id"),
        Index("ix_grouping_candidates_run", "run_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("grouping_runs.id", ondelete="CASCADE"), index=True
    )
    candidate_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    anchor_nm_id: Mapped[int] = mapped_column(index=True)
    member_nm_ids_json: Mapped[list[int]] = mapped_column(JSONB, default=list)
    scenario: Mapped[str] = mapped_column(
        String(64), default="article_family", nullable=False, index=True
    )
    candidate_type: Mapped[str] = mapped_column(
        String(64), default="article_family", nullable=False
    )
    confidence: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(32), default="low", nullable=False, index=True
    )
    risk_score: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    risk_reasons_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    conflicts_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    reviewed_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class GroupingRecommendation(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "grouping_recommendations"
    __table_args__ = (Index("ix_grouping_recommendations_candidate", "candidate_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("grouping_candidates.id", ondelete="CASCADE"), index=True
    )
    recommendation_type: Mapped[str] = mapped_column(
        String(64), default="merge_preview", nullable=False
    )
    source_nm_id: Mapped[int] = mapped_column(index=True)
    target_group_key: Mapped[str] = mapped_column(String(255), nullable=False)
    target_imt_id: Mapped[int | None] = mapped_column(nullable=True)
    proposed_members_json: Mapped[list[int]] = mapped_column(JSONB, default=list)
    preview_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    expected_effect_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    confidence: Mapped[float] = mapped_column(Numeric(18, 4), default=0, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), default="low", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )


class GroupingReviewHistory(BigIntPKMixin, Base):
    __tablename__ = "grouping_review_history"
    __table_args__ = (Index("ix_grouping_review_history_candidate", "candidate_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("grouping_candidates.id", ondelete="CASCADE"), index=True
    )
    old_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class GroupingExportArtifact(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "grouping_export_artifacts"
    __table_args__ = (Index("ix_grouping_export_artifacts_run", "run_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int] = mapped_column(
        ForeignKey("grouping_runs.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(
        String(64), default="merge_preview_json", nullable=False
    )
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
