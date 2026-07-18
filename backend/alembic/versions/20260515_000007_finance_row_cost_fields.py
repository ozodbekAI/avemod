"""Add detailed finance row cost fields.

Revision ID: 20260515_000007
Revises: 20260514_000006
Create Date: 2026-05-15 00:10:00
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import context, op

# revision identifiers, used by Alembic.
revision = "20260515_000007"
down_revision = "20260514_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        return
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("wb_realization_report_rows")}
    if "office_name" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("office_name", sa.String(length=255), nullable=True))
    if "seller_oper_name" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("seller_oper_name", sa.String(length=255), nullable=True))
    if "bonus_type_name" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("bonus_type_name", sa.String(length=255), nullable=True))
    if "retail_price" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("retail_price", sa.Numeric(18, 4), nullable=True))
    if "delivery_amount" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("delivery_amount", sa.Numeric(18, 4), nullable=True))
    if "delivery_service" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("delivery_service", sa.Numeric(18, 4), nullable=True))
    if "paid_acceptance" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("paid_acceptance", sa.Numeric(18, 4), nullable=True))
    if "additional_payment" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("additional_payment", sa.Numeric(18, 4), nullable=True))
    if "rebill_logistic_cost" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("rebill_logistic_cost", sa.Numeric(18, 4), nullable=True))
    if "return_amount" not in columns:
        op.add_column("wb_realization_report_rows", sa.Column("return_amount", sa.Numeric(18, 4), nullable=True))

    op.execute(
        """
        UPDATE wb_realization_report_rows
        SET
            office_name = payload->>'officeName',
            seller_oper_name = payload->>'sellerOperName',
            bonus_type_name = payload->>'bonusTypeName',
            retail_price = NULLIF(payload->>'retailPrice', '')::numeric,
            delivery_amount = NULLIF(payload->>'deliveryAmount', '')::numeric,
            delivery_service = NULLIF(payload->>'deliveryService', '')::numeric,
            paid_acceptance = NULLIF(payload->>'paidAcceptance', '')::numeric,
            additional_payment = NULLIF(payload->>'additionalPayment', '')::numeric,
            rebill_logistic_cost = NULLIF(payload->>'rebillLogisticCost', '')::numeric,
            return_amount = NULLIF(payload->>'returnAmount', '')::numeric
        WHERE payload IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("wb_realization_report_rows", "return_amount")
    op.drop_column("wb_realization_report_rows", "rebill_logistic_cost")
    op.drop_column("wb_realization_report_rows", "additional_payment")
    op.drop_column("wb_realization_report_rows", "paid_acceptance")
    op.drop_column("wb_realization_report_rows", "delivery_service")
    op.drop_column("wb_realization_report_rows", "delivery_amount")
    op.drop_column("wb_realization_report_rows", "retail_price")
    op.drop_column("wb_realization_report_rows", "bonus_type_name")
    op.drop_column("wb_realization_report_rows", "seller_oper_name")
    op.drop_column("wb_realization_report_rows", "office_name")
