from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
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


class PhotoProject(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "photo_projects"
    __table_args__ = (
        Index("ix_photo_projects_account_nm", "account_id", "nm_id"),
        Index("ix_photo_projects_account_status", "account_id", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int] = mapped_column(index=True)
    sku_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="draft", nullable=False, index=True
    )
    source_issue_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    source_action_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    preferred_version_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    approved_version_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PhotoAsset(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "photo_assets"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "checksum",
            "source_url",
            name="uq_photo_assets_source_checksum",
        ),
        Index("ix_photo_assets_account_nm", "account_id", "nm_id"),
        Index("ix_photo_assets_project", "project_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    storage_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    exif_removed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_assets.id", ondelete="SET NULL"), nullable=True
    )
    is_test: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PhotoVersion(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "photo_versions"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "project_id",
            "version_number",
            name="uq_photo_versions_project_number",
        ),
        Index("ix_photo_versions_project_status", "project_id", "status"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("photo_projects.id", ondelete="CASCADE"), index=True
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("photo_assets.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), default="ready", nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brief_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    generation_job_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    approved_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class PhotoGenerationJob(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "photo_generation_jobs"
    __table_args__ = (
        Index("ix_photo_jobs_account_status", "account_id", "status"),
        Index("ix_photo_jobs_project", "project_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("photo_projects.id", ondelete="CASCADE"), index=True
    )
    input_asset_ids_json: Mapped[list[int]] = mapped_column(JSONB, default=list)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="queued", nullable=False, index=True
    )
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sanitized_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    settings_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    requested_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
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
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_asset_ids_json: Mapped[list[int]] = mapped_column(JSONB, default=list)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class PhotoProjectMessage(BigIntPKMixin, Base):
    __tablename__ = "photo_project_messages"
    __table_args__ = (
        Index("ix_photo_messages_project_created", "project_id", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("photo_projects.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    author_type: Mapped[str] = mapped_column(String(32), default="user", nullable=False)
    message_type: Mapped[str] = mapped_column(
        String(32), default="comment", nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    linked_asset_ids_json: Mapped[list[int]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PhotoProjectEvent(BigIntPKMixin, Base):
    __tablename__ = "photo_project_events"
    __table_args__ = (
        Index("ix_photo_events_project_created", "project_id", "created_at"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("photo_projects.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"), nullable=True
    )
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PhotoSettings(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "photo_settings"
    __table_args__ = (UniqueConstraint("account_id", name="uq_photo_settings_account"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    provider_mode: Mapped[str] = mapped_column(
        String(32), default="manual", nullable=False
    )
    default_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    default_aspect_ratio: Mapped[str | None] = mapped_column(String(32), nullable=True)
    default_output_format: Mapped[str] = mapped_column(
        String(16), default="jpeg", nullable=False
    )
    max_upload_mb: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    allowed_mime_types_json: Mapped[list[str]] = mapped_column(JSONB, default=list)
    generation_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    editing_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    external_apply_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
