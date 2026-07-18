"""Expand core SKU uniqueness.

Revision ID: 20260514_000003
Revises: 20260514_000002
Create Date: 2026-05-14 17:18:00
"""
from __future__ import annotations

from alembic import context, op
import sqlalchemy as sa


revision = "20260514_000003"
down_revision = "20260514_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    inspector = sa.inspect(op.get_bind())
    constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("core_sku")}
    if "uq_core_sku_account_id" in constraints:
        op.drop_constraint("uq_core_sku_account_id", "core_sku", type_="unique")
    if "uq_core_sku_account_variant" not in constraints:
        op.create_unique_constraint(
            "uq_core_sku_account_variant",
            "core_sku",
            ["account_id", "nm_id", "vendor_code", "tech_size", "chrt_id", "size_id", "barcode"],
        )


def downgrade() -> None:
    op.drop_constraint("uq_core_sku_account_variant", "core_sku", type_="unique")
    op.create_unique_constraint(
        "uq_core_sku_account_id",
        "core_sku",
        ["account_id", "nm_id", "vendor_code", "tech_size"],
    )
