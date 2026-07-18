"""Move emotional reputation category after concrete categories.

Revision ID: 20260630_000052
Revises: 20260630_000051
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260630_000052"
down_revision = "20260630_000051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE reputation_review_categories
            SET sort_order = 130,
                updated_at = now()
            WHERE scope = 'global'
              AND code = 'emotional_negative'
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE reputation_review_categories
            SET sort_order = 70,
                updated_at = now()
            WHERE scope = 'global'
              AND code = 'emotional_negative'
            """
        )
    )
