"""Normalize reputation manual attention score semantics.

Revision ID: 20260630_000054
Revises: 20260630_000053
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260630_000054"
down_revision = "20260630_000053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE reputation_items
            SET review_need_reply_score = 59,
                updated_at = now()
            WHERE review_requires_manual_attention IS TRUE
              AND (
                review_need_reply_score IS NULL
                OR review_need_reply_score >= 60
              )
            """
        )
    )


def downgrade() -> None:
    # This migration is a compatibility data correction. The previous high
    # scores cannot be reconstructed safely.
    pass
