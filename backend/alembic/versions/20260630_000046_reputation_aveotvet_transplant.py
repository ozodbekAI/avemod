"""Expand reputation operator with AVEOTVET fields.

Revision ID: 20260630_000046
Revises: 20260629_000045
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260630_000046"
down_revision = "20260629_000045"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    for column in (
        sa.Column("pros", sa.Text(), nullable=True),
        sa.Column("cons", sa.Text(), nullable=True),
        sa.Column("answer_text", sa.Text(), nullable=True),
        sa.Column("answer_state", sa.String(length=32), nullable=True),
        sa.Column("answer_editable", sa.Boolean(), nullable=True),
        sa.Column("review_type", sa.String(length=64), nullable=True),
        sa.Column("review_need_reply_score", sa.Integer(), nullable=True),
        sa.Column("review_requires_manual_attention", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("product_details_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("media_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("bables_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_categories_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("review_category_matches_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    ):
        op.add_column("reputation_items", column)
    op.create_index("ix_reputation_items_answer_state", "reputation_items", ["answer_state"])
    op.create_index("ix_reputation_items_review_type", "reputation_items", ["review_type"])
    op.create_index("ix_reputation_items_review_requires_manual_attention", "reputation_items", ["review_requires_manual_attention"])

    for column in (
        sa.Column("auto_sync", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("auto_draft", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("auto_draft_limit_per_sync", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("questions_reply_mode", sa.String(length=32), nullable=False, server_default="semi"),
        sa.Column("questions_auto_draft", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("questions_auto_publish", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("chat_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_feedback_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_questions_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_chat_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_full_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("chat_next_ms", sa.BigInteger(), nullable=True),
        sa.Column("analytics_ready", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("analytics_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("analytics_period", sa.String(length=16), nullable=True),
        sa.Column("analytics_status", sa.String(length=48), nullable=False, server_default="activation_required"),
        sa.Column("analytics_status_reason", sa.String(length=128), nullable=True),
        sa.Column("analytics_status_updated_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("reputation_settings", column)


def downgrade() -> None:
    for column in (
        "analytics_status_updated_at",
        "analytics_status_reason",
        "analytics_status",
        "analytics_period",
        "analytics_enabled",
        "analytics_ready",
        "chat_next_ms",
        "last_full_sync_at",
        "last_chat_sync_at",
        "last_questions_sync_at",
        "last_feedback_created_at",
        "last_sync_at",
        "chat_enabled",
        "questions_auto_publish",
        "questions_auto_draft",
        "questions_reply_mode",
        "auto_draft_limit_per_sync",
        "auto_draft",
        "auto_sync",
    ):
        op.drop_column("reputation_settings", column)
    op.drop_index("ix_reputation_items_review_requires_manual_attention", table_name="reputation_items")
    op.drop_index("ix_reputation_items_review_type", table_name="reputation_items")
    op.drop_index("ix_reputation_items_answer_state", table_name="reputation_items")
    for column in (
        "review_category_matches_json",
        "review_categories_json",
        "bables_json",
        "media_json",
        "product_details_json",
        "review_requires_manual_attention",
        "review_need_reply_score",
        "review_type",
        "answer_editable",
        "answer_state",
        "answer_text",
        "cons",
        "pros",
    ):
        op.drop_column("reputation_items", column)
