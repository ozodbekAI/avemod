"""Allow large WB product card imt ids.

Revision ID: 20260626_000044
Revises: 20260626_000043
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260626_000044"
down_revision = "20260626_000043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "wb_product_cards",
        "imt_id",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "wb_product_cards",
        "imt_id",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
    )
