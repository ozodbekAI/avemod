"""Deactivate legacy reputation prompt categories.

Revision ID: 20260630_000050
Revises: 20260630_000049
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260630_000050"
down_revision = "20260630_000049"
branch_labels = None
depends_on = None


LEGACY_CODES = (
    "product_quality",
    "size_fit",
    "packaging_delivery",
    "appearance_expectation",
    "price_value",
    "service_communication",
)


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE reputation_review_categories
            SET is_active = FALSE
            WHERE scope = 'global'
              AND code IN :codes
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": LEGACY_CODES},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE reputation_review_categories
            SET is_active = TRUE
            WHERE scope = 'global'
              AND code IN :codes
            """
        ).bindparams(sa.bindparam("codes", expanding=True)),
        {"codes": LEGACY_CODES},
    )
