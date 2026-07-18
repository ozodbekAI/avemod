from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
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


class ReputationItem(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "reputation_items"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "item_type",
            "external_id",
            name="uq_reputation_items_account_type_external",
        ),
        Index("ix_reputation_items_account_received", "account_id", "received_at"),
        Index(
            "ix_reputation_items_account_status_priority",
            "account_id",
            "status",
            "priority",
        ),
        Index("ix_reputation_items_account_nm", "account_id", "nm_id"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    item_type: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    external_thread_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sku_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    pros: Mapped[str | None] = mapped_column(Text, nullable=True)
    cons: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_name_masked: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="new", nullable=False, index=True
    )
    external_status: Mapped[str] = mapped_column(
        String(32), default="not_created", nullable=False, index=True
    )
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_state: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    answer_editable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(
        String(8), default="P3", nullable=False, index=True
    )
    review_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    review_need_reply_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_requires_manual_attention: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    needs_reply: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    replied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    product_details_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    media_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    bables_json: Mapped[list[dict[str, Any]] | list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    review_categories_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    review_category_matches_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    raw_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )


class ReputationSettings(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "reputation_settings"
    __table_args__ = (
        UniqueConstraint("account_id", name="uq_reputation_settings_account"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True
    )
    reply_mode: Mapped[str] = mapped_column(String(32), default="semi", nullable=False)
    tone: Mapped[str] = mapped_column(String(64), default="polite", nullable=False)
    language: Mapped[str] = mapped_column(String(16), default="ru", nullable=False)
    signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    auto_sync: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_draft: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_draft_limit_per_sync: Mapped[int] = mapped_column(
        Integer, default=30, nullable=False
    )
    templates_json: Mapped[dict[str, Any] | list[dict[str, Any]]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    signatures_json: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    rating_mode_map_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=lambda: {
            "1": "manual",
            "2": "manual",
            "3": "semi",
            "4": "auto",
            "5": "auto",
        },
        nullable=False,
    )
    config_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    blacklist_keywords_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    whitelist_keywords_json: Mapped[list[str]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    ai_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ai_provider: Mapped[str] = mapped_column(
        String(32), default="openai", nullable=False
    )
    ai_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    automation_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    auto_publish_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    chat_auto_reply_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    questions_reply_mode: Mapped[str] = mapped_column(
        String(32), default="semi", nullable=False
    )
    questions_auto_draft: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    questions_auto_publish: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    chat_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_feedback_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_questions_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_chat_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_full_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    chat_next_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    analytics_ready: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    analytics_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    analytics_period: Mapped[str | None] = mapped_column(String(16), nullable=True)
    analytics_status: Mapped[str] = mapped_column(
        String(48), default="activation_required", nullable=False
    )
    analytics_status_reason: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    analytics_status_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReputationPromptRecord(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "reputation_prompt_records"
    __table_args__ = (
        UniqueConstraint("scope", "key", name="uq_reputation_prompt_records_scope_key"),
        Index("ix_reputation_prompt_records_scope", "scope"),
        Index("ix_reputation_prompt_records_key", "key"),
    )

    scope: Mapped[str] = mapped_column(String(64), default="global", nullable=False)
    key: Mapped[str] = mapped_column(String(96), nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSONB, nullable=True
    )


class ReputationReviewCategory(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "reputation_review_categories"
    __table_args__ = (
        UniqueConstraint(
            "scope", "code", name="uq_reputation_review_categories_scope_code"
        ),
        Index("ix_reputation_review_categories_scope", "scope"),
        Index("ix_reputation_review_categories_code", "code"),
    )

    scope: Mapped[str] = mapped_column(String(64), default="global", nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    positive_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )

    def prompt_for_sentiment(self, sentiment: str | None) -> str:
        if (sentiment or "").strip().lower() == "positive":
            return self.positive_prompt or self.negative_prompt
        return self.negative_prompt or self.positive_prompt


class ReputationLearningEntry(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "reputation_learning_entries"
    __table_args__ = (
        Index(
            "ix_reputation_learning_entries_account_active", "account_id", "is_active"
        ),
        Index("ix_reputation_learning_entries_account_nm", "account_id", "nm_id"),
        Index("ix_reputation_learning_entries_target", "target_type"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reputation_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("reputation_items.id", ondelete="SET NULL"), nullable=True
    )
    nm_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    category_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    sentiment_scope: Mapped[str | None] = mapped_column(String(16), nullable=True)
    user_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    applied_text: Mapped[str] = mapped_column(Text, nullable=False)
    stop_word: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True
    )
