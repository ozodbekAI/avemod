"""Add local reputation module tables.

Revision ID: 20260621_000038
Revises: 20260619_000037
Create Date: 2026-06-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260621_000038"
down_revision = "20260619_000037"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "reputation_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("external_thread_id", sa.String(length=255), nullable=True),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("buyer_name_masked", sa.String(length=120), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="new", nullable=False),
        sa.Column("external_status", sa.String(length=32), server_default="not_created", nullable=False),
        sa.Column("sentiment", sa.String(length=32), nullable=True),
        sa.Column("priority", sa.String(length=8), server_default="P3", nullable=False),
        sa.Column("needs_reply", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_json", JSONB, server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "item_type", "external_id", name="uq_reputation_items_account_type_external"),
    )
    for column in (
        "account_id",
        "item_type",
        "external_id",
        "external_thread_id",
        "nm_id",
        "sku_id",
        "rating",
        "status",
        "external_status",
        "sentiment",
        "priority",
        "needs_reply",
        "received_at",
        "replied_at",
    ):
        op.create_index(f"ix_reputation_items_{column}", "reputation_items", [column])
    op.create_index("ix_reputation_items_account_received", "reputation_items", ["account_id", "received_at"])
    op.create_index("ix_reputation_items_account_status_priority", "reputation_items", ["account_id", "status", "priority"])
    op.create_index("ix_reputation_items_account_nm", "reputation_items", ["account_id", "nm_id"])

    op.create_table(
        "reputation_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("reply_mode", sa.String(length=32), server_default="semi", nullable=False),
        sa.Column("tone", sa.String(length=64), server_default="polite", nullable=False),
        sa.Column("language", sa.String(length=16), server_default="ru", nullable=False),
        sa.Column("signature", sa.String(length=255), nullable=True),
        sa.Column("templates_json", JSONB, server_default="[]", nullable=False),
        sa.Column("signatures_json", JSONB, server_default="[]", nullable=False),
        sa.Column("automation_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("auto_publish_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("chat_auto_reply_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", name="uq_reputation_settings_account"),
    )
    op.create_index("ix_reputation_settings_account_id", "reputation_settings", ["account_id"])


def downgrade() -> None:
    op.drop_index("ix_reputation_settings_account_id", table_name="reputation_settings")
    op.drop_table("reputation_settings")
    op.drop_index("ix_reputation_items_account_nm", table_name="reputation_items")
    op.drop_index("ix_reputation_items_account_status_priority", table_name="reputation_items")
    op.drop_index("ix_reputation_items_account_received", table_name="reputation_items")
    for column in (
        "replied_at",
        "received_at",
        "needs_reply",
        "priority",
        "sentiment",
        "external_status",
        "status",
        "rating",
        "sku_id",
        "nm_id",
        "external_thread_id",
        "external_id",
        "item_type",
        "account_id",
    ):
        op.drop_index(f"ix_reputation_items_{column}", table_name="reputation_items")
    op.drop_table("reputation_items")
