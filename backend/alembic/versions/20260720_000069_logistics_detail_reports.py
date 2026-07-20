"""Add logistics detail report tables.

Revision ID: 20260720_000069
Revises: 20260718_000068
Create Date: 2026-07-20
"""

from __future__ import annotations

from alembic import op


revision = "20260720_000069"
down_revision = "20260718_000068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_logistics_paid_storage_rows (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            dedupe_key VARCHAR(64) NOT NULL UNIQUE,
            report_date DATE,
            nm_id BIGINT,
            vendor_code VARCHAR(255),
            barcode VARCHAR(255),
            title VARCHAR(500),
            brand VARCHAR(255),
            subject_name VARCHAR(255),
            warehouse_name VARCHAR(255),
            quantity NUMERIC(18, 4),
            amount NUMERIC(18, 4),
            storage_cost NUMERIC(18, 4),
            currency VARCHAR(16),
            task_id VARCHAR(128),
            source_row_key VARCHAR(255),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_logistics_paid_storage_rows_dedupe_key "
        "ON wb_logistics_paid_storage_rows (dedupe_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_logistics_paid_storage_rows_report_date "
        "ON wb_logistics_paid_storage_rows (report_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_logistics_paid_storage_rows_nm_id "
        "ON wb_logistics_paid_storage_rows (nm_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_logistics_paid_storage_rows_barcode "
        "ON wb_logistics_paid_storage_rows (barcode)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_logistics_acceptance_report_rows (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            dedupe_key VARCHAR(64) NOT NULL UNIQUE,
            operation_date DATE,
            nm_id BIGINT,
            vendor_code VARCHAR(255),
            barcode VARCHAR(255),
            title VARCHAR(500),
            brand VARCHAR(255),
            subject_name VARCHAR(255),
            warehouse_name VARCHAR(255),
            operation_name VARCHAR(255),
            quantity NUMERIC(18, 4),
            amount NUMERIC(18, 4),
            acceptance_cost NUMERIC(18, 4),
            currency VARCHAR(16),
            task_id VARCHAR(128),
            source_row_key VARCHAR(255),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_acceptance_report_rows_dedupe_key "
        "ON wb_logistics_acceptance_report_rows (dedupe_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_acceptance_report_rows_operation_date "
        "ON wb_logistics_acceptance_report_rows (operation_date)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_acceptance_report_rows_nm_id "
        "ON wb_logistics_acceptance_report_rows (nm_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_acceptance_report_rows_barcode "
        "ON wb_logistics_acceptance_report_rows (barcode)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_logistics_transit_tariffs (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            dedupe_key VARCHAR(64) NOT NULL UNIQUE,
            collected_at TIMESTAMPTZ NOT NULL,
            source_warehouse_id BIGINT,
            source_warehouse_name VARCHAR(255),
            transit_warehouse_id BIGINT,
            transit_warehouse_name VARCHAR(255),
            destination_warehouse_id BIGINT,
            destination_warehouse_name VARCHAR(255),
            box_type_id INTEGER,
            coefficient VARCHAR(64),
            delivery_base NUMERIC(18, 4),
            delivery_liter NUMERIC(18, 4),
            amount NUMERIC(18, 4),
            currency VARCHAR(16),
            transit_time_days NUMERIC(18, 4),
            route_label VARCHAR(500),
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_logistics_transit_tariffs_dedupe_key "
        "ON wb_logistics_transit_tariffs (dedupe_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_logistics_transit_tariffs_collected_at "
        "ON wb_logistics_transit_tariffs (collected_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_transit_tariffs_source_warehouse_id "
        "ON wb_logistics_transit_tariffs (source_warehouse_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_transit_tariffs_transit_warehouse_id "
        "ON wb_logistics_transit_tariffs (transit_warehouse_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS "
        "ix_wb_logistics_transit_tariffs_destination_warehouse_id "
        "ON wb_logistics_transit_tariffs (destination_warehouse_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_seller_warehouses (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            warehouse_id BIGINT NOT NULL,
            name VARCHAR(255),
            office_id BIGINT,
            delivery_type VARCHAR(64),
            cargo_type VARCHAR(64),
            address VARCHAR(500),
            is_active BOOLEAN,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_wb_seller_warehouses_account_id
            UNIQUE (account_id, warehouse_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_seller_warehouses_warehouse_id "
        "ON wb_seller_warehouses (warehouse_id)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wb_seller_warehouse_stocks (
            id BIGSERIAL PRIMARY KEY,
            account_id BIGINT NOT NULL REFERENCES wb_accounts(id) ON DELETE CASCADE,
            warehouse_id BIGINT NOT NULL,
            warehouse_name VARCHAR(255),
            chrt_id BIGINT NOT NULL,
            nm_id BIGINT,
            vendor_code VARCHAR(255),
            barcode VARCHAR(255),
            quantity NUMERIC(18, 4),
            reserved NUMERIC(18, 4),
            in_way NUMERIC(18, 4),
            updated_at_wb TIMESTAMPTZ,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_wb_seller_warehouse_stocks_account_id
            UNIQUE (account_id, warehouse_id, chrt_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_seller_warehouse_stocks_warehouse_id "
        "ON wb_seller_warehouse_stocks (warehouse_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_seller_warehouse_stocks_chrt_id "
        "ON wb_seller_warehouse_stocks (chrt_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_seller_warehouse_stocks_nm_id "
        "ON wb_seller_warehouse_stocks (nm_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wb_seller_warehouse_stocks_barcode "
        "ON wb_seller_warehouse_stocks (barcode)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wb_seller_warehouse_stocks")
    op.execute("DROP TABLE IF EXISTS wb_seller_warehouses")
    op.execute("DROP TABLE IF EXISTS wb_logistics_transit_tariffs")
    op.execute("DROP TABLE IF EXISTS wb_logistics_acceptance_report_rows")
    op.execute("DROP TABLE IF EXISTS wb_logistics_paid_storage_rows")
