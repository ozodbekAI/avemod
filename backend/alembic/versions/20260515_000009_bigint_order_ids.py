"""Promote operational and mart order identifiers to bigint.

Revision ID: 20260515_000009
Revises: 20260515_000008
Create Date: 2026-05-15 16:10:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision = "20260515_000009"
down_revision = "20260515_000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return

    inspector = sa.inspect(op.get_bind())

    def _alter_if_needed(table_name: str, column_name: str) -> None:
        columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        column = columns.get(column_name)
        if column is None:
            return
        if isinstance(column["type"], sa.BigInteger):
            return
        op.alter_column(table_name, column_name, existing_type=sa.INTEGER(), type_=sa.BigInteger())

    _alter_if_needed("wb_orders", "order_id")
    _alter_if_needed("wb_sales", "order_id")
    _alter_if_needed("mart_finance_reconciliation", "order_id")


def downgrade() -> None:
    raise NotImplementedError("Downgrade is not supported for forward-only stabilization migrations.")
