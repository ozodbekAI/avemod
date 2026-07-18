"""Add operational A/B tests.

Revision ID: 20260626_000043
Revises: 20260625_000042
Create Date: 2026-06-26 12:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260626_000043"
down_revision = "20260625_000042"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "ab_test_companies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("created_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("wb_advert_id", sa.BigInteger(), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=False),
        sa.Column("product_card_id", sa.BigInteger(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="created"),
        sa.Column("from_main", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("max_slots", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("keep_winner_as_main", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("delete_test_photos", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("photos_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("views_per_photo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cpm", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("spend_rub", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_total_shows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_total_clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_photo_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("winner_photo_order", sa.Integer(), nullable=True),
        sa.Column("original_media_json", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("current_uploaded_wb_url", sa.String(length=1024), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["auth_users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["product_card_id"], ["wb_product_cards.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ab_test_companies_account_id", "ab_test_companies", ["account_id"])
    op.create_index("ix_ab_test_companies_created_by_user_id", "ab_test_companies", ["created_by_user_id"])
    op.create_index("ix_ab_test_companies_nm_id", "ab_test_companies", ["nm_id"])
    op.create_index("ix_ab_test_companies_product_card_id", "ab_test_companies", ["product_card_id"])
    op.create_index("ix_ab_test_companies_status", "ab_test_companies", ["status"])
    op.create_index("ix_ab_test_companies_wb_advert_id", "ab_test_companies", ["wb_advert_id"])

    op.create_table(
        "ab_test_photos",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("company_id", sa.BigInteger(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.String(length=2048), nullable=False),
        sa.Column("wb_url", sa.String(length=2048), nullable=True),
        sa.Column("preview_url", sa.String(length=2048), nullable=True),
        sa.Column("shows", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("is_winner", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.ForeignKeyConstraint(["company_id"], ["ab_test_companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ab_test_photos_company_id", "ab_test_photos", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_ab_test_photos_company_id", table_name="ab_test_photos")
    op.drop_table("ab_test_photos")
    op.drop_index("ix_ab_test_companies_wb_advert_id", table_name="ab_test_companies")
    op.drop_index("ix_ab_test_companies_status", table_name="ab_test_companies")
    op.drop_index("ix_ab_test_companies_product_card_id", table_name="ab_test_companies")
    op.drop_index("ix_ab_test_companies_nm_id", table_name="ab_test_companies")
    op.drop_index("ix_ab_test_companies_created_by_user_id", table_name="ab_test_companies")
    op.drop_index("ix_ab_test_companies_account_id", table_name="ab_test_companies")
    op.drop_table("ab_test_companies")
