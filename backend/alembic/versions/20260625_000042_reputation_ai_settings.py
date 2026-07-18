"""Add reputation rating and AI settings.

Revision ID: 20260625_000042
Revises: 20260623_000041
Create Date: 2026-06-25 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260625_000042"
down_revision = "20260623_000041"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "reputation_settings",
        sa.Column(
            "rating_mode_map_json",
            JSONB,
            nullable=False,
            server_default=sa.text('\'{"1":"manual","2":"manual","3":"semi","4":"auto","5":"auto"}\'::jsonb'),
        ),
    )
    op.add_column(
        "reputation_settings",
        sa.Column("config_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.add_column(
        "reputation_settings",
        sa.Column("blacklist_keywords_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "reputation_settings",
        sa.Column("whitelist_keywords_json", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "reputation_settings",
        sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )
    op.add_column(
        "reputation_settings",
        sa.Column("ai_provider", sa.String(length=32), nullable=False, server_default="openai"),
    )
    op.add_column("reputation_settings", sa.Column("ai_model", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("reputation_settings", "ai_model")
    op.drop_column("reputation_settings", "ai_provider")
    op.drop_column("reputation_settings", "ai_enabled")
    op.drop_column("reputation_settings", "whitelist_keywords_json")
    op.drop_column("reputation_settings", "blacklist_keywords_json")
    op.drop_column("reputation_settings", "config_json")
    op.drop_column("reputation_settings", "rating_mode_map_json")
