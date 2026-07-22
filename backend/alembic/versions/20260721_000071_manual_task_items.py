"""Add manual task item progress table.

Revision ID: 20260721_000071
Revises: 20260721_000070
Create Date: 2026-07-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260721_000071"
down_revision = "20260721_000070"
branch_labels = None
depends_on = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "manual_task_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("account_id", sa.BigInteger(), nullable=False),
        sa.Column("action_id", sa.BigInteger(), nullable=False),
        sa.Column("item_key", sa.String(length=64), nullable=False),
        sa.Column("nm_id", sa.BigInteger(), nullable=True),
        sa.Column("sku_id", sa.BigInteger(), nullable=True),
        sa.Column("vendor_code", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("photo_url", sa.String(length=1024), nullable=True),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("skipped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skipped_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("last_comment", sa.Text(), nullable=True),
        sa.Column("product_json", JSONB, server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["wb_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["action_id"], ["unified_actions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["skipped_by_user_id"], ["auth_users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "action_id", "item_key", name="uq_manual_task_items_action_item_key"
        ),
    )
    op.create_index(
        "ix_manual_task_items_account_id", "manual_task_items", ["account_id"]
    )
    op.create_index(
        "ix_manual_task_items_action_id", "manual_task_items", ["action_id"]
    )
    op.create_index("ix_manual_task_items_nm_id", "manual_task_items", ["nm_id"])
    op.create_index("ix_manual_task_items_sku_id", "manual_task_items", ["sku_id"])
    op.create_index("ix_manual_task_items_status", "manual_task_items", ["status"])
    op.create_index(
        "ix_manual_task_items_vendor_code", "manual_task_items", ["vendor_code"]
    )
    op.create_index(
        "ix_manual_task_items_completed_at",
        "manual_task_items",
        ["completed_at"],
    )
    op.create_index(
        "ix_manual_task_items_completed_by_user_id",
        "manual_task_items",
        ["completed_by_user_id"],
    )
    op.create_index(
        "ix_manual_task_items_skipped_at", "manual_task_items", ["skipped_at"]
    )
    op.create_index(
        "ix_manual_task_items_skipped_by_user_id",
        "manual_task_items",
        ["skipped_by_user_id"],
    )
    op.create_index(
        "ix_manual_task_items_account_status",
        "manual_task_items",
        ["account_id", "status"],
    )
    op.create_index(
        "ix_manual_task_items_action_status",
        "manual_task_items",
        ["action_id", "status"],
    )
    op.create_index(
        "ix_manual_task_items_nm_status", "manual_task_items", ["nm_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_manual_task_items_nm_status", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_action_status", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_account_status", table_name="manual_task_items")
    op.drop_index(
        "ix_manual_task_items_skipped_by_user_id", table_name="manual_task_items"
    )
    op.drop_index("ix_manual_task_items_skipped_at", table_name="manual_task_items")
    op.drop_index(
        "ix_manual_task_items_completed_by_user_id", table_name="manual_task_items"
    )
    op.drop_index("ix_manual_task_items_completed_at", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_vendor_code", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_status", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_sku_id", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_nm_id", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_action_id", table_name="manual_task_items")
    op.drop_index("ix_manual_task_items_account_id", table_name="manual_task_items")
    op.drop_table("manual_task_items")
