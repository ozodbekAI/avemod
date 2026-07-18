from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, BigIntPKMixin, TimestampMixin
from app.core.expense_taxonomy import (
    additional_income as compute_additional_income,
    expense_data_quality as compute_expense_data_quality,
    revenue_final as compute_revenue_final,
    total_seller_costs as compute_total_seller_costs,
)


class MartSKUDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "mart_sku_daily"
    __dedupe_fields__ = ("account_id", "stat_date", "nm_id", "vendor_code", "barcode")
    __table_args__ = (
        UniqueConstraint("account_id", "stat_date", "nm_id", "vendor_code", "barcode"),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_rows: Mapped[int] = mapped_column(default=0)
    ordered_units: Mapped[int] = mapped_column(default=0)
    cancelled_orders: Mapped[int] = mapped_column(default=0)
    sale_rows: Mapped[int] = mapped_column(default=0)
    finance_rows: Mapped[int] = mapped_column(default=0)
    operational_sales_qty: Mapped[int] = mapped_column(default=0)
    operational_return_qty: Mapped[int] = mapped_column(default=0)
    operational_revenue: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    operational_for_pay: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    finance_sales_qty: Mapped[int] = mapped_column(default=0)
    finance_return_qty: Mapped[int] = mapped_column(default=0)
    finance_net_units: Mapped[int] = mapped_column(default=0)
    finance_revenue: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    finance_for_pay: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    final_sales_qty: Mapped[int] = mapped_column(default=0)
    final_return_qty: Mapped[int] = mapped_column(default=0)
    final_net_qty: Mapped[int] = mapped_column(default=0)
    final_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    final_for_pay: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    final_revenue_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    wb_commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    payment_processing: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    pvz_reward: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    wb_logistics: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    wb_logistics_rebill: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    acceptance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    penalty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    deduction: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    marketing_deduction: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    loyalty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    other_wb_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    total_wb_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    seller_cogs: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    seller_other_expense: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    total_seller_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    acquiring_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    logistics: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    paid_acceptance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    storage: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    penalties: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    deductions: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    additional_payments: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_operational: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_finance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_final: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ad_spend_delta: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    ad_views: Mapped[int] = mapped_column(default=0)
    ad_clicks: Mapped[int] = mapped_column(default=0)
    funnel_opens: Mapped[int] = mapped_column(default=0)
    funnel_carts: Mapped[int] = mapped_column(default=0)
    funnel_orders: Mapped[int] = mapped_column(default=0)
    funnel_buyouts: Mapped[int] = mapped_column(default=0)
    opening_stock_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    closing_stock_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    in_way_to_client: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    in_way_from_client: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    current_discounted_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    avg_sale_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    seller_discount: Mapped[int | None] = mapped_column(nullable=True)
    club_discount: Mapped[int | None] = mapped_column(nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    packaging_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    inbound_logistics_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    total_unit_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    estimated_cogs: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    estimated_profit_before_ads: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    estimated_profit_after_ads: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    net_profit_after_all_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    margin_percent: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    roi_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    drr_percent: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    has_manual_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    has_real_manual_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    has_placeholder_cost: Mapped[bool] = mapped_column(Boolean, default=False)
    business_trusted: Mapped[bool] = mapped_column(Boolean, default=False)
    cost_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_open_issues: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    @property
    def revenue_final(self) -> Decimal:
        return compute_revenue_final(self)

    @property
    def total_seller_costs(self) -> Decimal:
        return compute_total_seller_costs(self)

    @property
    def additional_income(self) -> Decimal:
        return compute_additional_income(self)

    @property
    def expense_data_quality(self) -> str:
        return compute_expense_data_quality(self)


class MartStockDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "mart_stock_daily"
    __dedupe_fields__ = (
        "account_id",
        "stat_date",
        "nm_id",
        "barcode",
        "warehouse_id",
        "warehouse_name",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "stat_date",
            "nm_id",
            "barcode",
            "warehouse_id",
            "warehouse_name",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warehouse_id: Mapped[int | None] = mapped_column(nullable=True)
    warehouse_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    quantity_full: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    in_way_to_client: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    in_way_from_client: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    days_since_last_sale: Mapped[int | None] = mapped_column(nullable=True)
    sales_7d: Mapped[int] = mapped_column(default=0)
    sales_14d: Mapped[int] = mapped_column(default=0)
    sales_30d: Mapped[int] = mapped_column(default=0)
    avg_sales_per_day_30d: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    days_of_stock: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    turnover_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_out_of_stock_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    is_dead_stock: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class MartFinanceReconciliation(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "mart_finance_reconciliation"
    __dedupe_fields__ = ("account_id", "srid", "nm_id")
    __table_args__ = (UniqueConstraint("account_id", "stat_date", "srid", "nm_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    srid: Mapped[str] = mapped_column(String(255), index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    finance_sale_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    finance_rr_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    first_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    order_rows: Mapped[int] = mapped_column(default=0)
    sale_rows: Mapped[int] = mapped_column(default=0)
    finance_rows: Mapped[int] = mapped_column(default=0)
    has_order: Mapped[bool] = mapped_column(Boolean, default=False)
    has_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    has_finance: Mapped[bool] = mapped_column(Boolean, default=False)
    order_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    sale_revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    finance_revenue: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    sale_for_pay: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    finance_for_pay: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    revenue_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    for_pay_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="matched")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class MartAccountExpenseDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "mart_account_expense_daily"
    __dedupe_fields__ = ("account_id", "stat_date")
    __table_args__ = (UniqueConstraint("account_id", "stat_date"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    source_rows: Mapped[int] = mapped_column(default=0)
    wb_commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    payment_processing: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    pvz_reward: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    wb_logistics: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    wb_logistics_rebill: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    acceptance: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    penalty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    deduction: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    marketing_deduction: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    loyalty: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    other_wb_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    total_wb_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    commission: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    acquiring_fee: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    logistics: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    paid_acceptance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    storage: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    penalties: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    deductions: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    additional_payments: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_operational: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_finance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_final: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ad_spend_delta: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    seller_cogs: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    seller_other_expense: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    total_seller_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    net_profit_after_all_expenses: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    total_expense: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)

    @property
    def total_seller_costs(self) -> Decimal:
        return compute_total_seller_costs(self)

    @property
    def additional_income(self) -> Decimal:
        return compute_additional_income(self)

    @property
    def expense_data_quality(self) -> str:
        return compute_expense_data_quality(self)


class MartReconciliationDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "mart_reconciliation_daily"
    __dedupe_fields__ = ("account_id", "stat_date", "sku_id")
    __table_args__ = (UniqueConstraint("account_id", "stat_date", "sku_id"),)

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    sku_id: Mapped[int] = mapped_column(
        ForeignKey("core_sku.id", ondelete="CASCADE"), index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    vendor_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orders_qty: Mapped[int] = mapped_column(default=0)
    orders_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    sales_qty: Mapped[int] = mapped_column(default=0)
    sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    returns_qty: Mapped[int] = mapped_column(default=0)
    returns_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    finance_qty: Mapped[int] = mapped_column(default=0)
    finance_revenue: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    finance_for_pay: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_operational: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_finance: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_final: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    ad_spend_delta: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    ad_spend: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    ad_orders: Mapped[int] = mapped_column(default=0)
    opening_stock_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    closing_stock_qty: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    avg_sale_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    current_discounted_price: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    revenue_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    for_pay_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    status_bucket: Mapped[str | None] = mapped_column(
        String(32), nullable=True, index=True
    )
    status_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    has_order_without_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    has_sale_without_finance: Mapped[bool] = mapped_column(Boolean, default=False)
    has_finance_without_sale: Mapped[bool] = mapped_column(Boolean, default=False)
    has_stock_without_sales: Mapped[bool] = mapped_column(Boolean, default=False)
    has_ad_spend_without_sales: Mapped[bool] = mapped_column(Boolean, default=False)
    has_price_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)


class MartExpenseDaily(BigIntPKMixin, TimestampMixin, Base):
    __tablename__ = "mart_expense_daily"
    __dedupe_fields__ = (
        "account_id",
        "stat_date",
        "rrd_id",
        "expense_category",
        "source_field",
        "sku_id",
        "nm_id",
        "barcode",
    )
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "stat_date",
            "rrd_id",
            "expense_category",
            "source_field",
            "sku_id",
            "nm_id",
            "barcode",
        ),
    )

    account_id: Mapped[int] = mapped_column(
        ForeignKey("wb_accounts.id", ondelete="CASCADE")
    )
    dedupe_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    stat_date: Mapped[date] = mapped_column(Date, index=True)
    report_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    rrd_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sku_id: Mapped[int | None] = mapped_column(
        ForeignKey("core_sku.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nm_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    barcode: Mapped[str | None] = mapped_column(String(255), nullable=True)
    srid: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    expense_category: Mapped[str] = mapped_column(String(64), index=True)
    expense_source: Mapped[str] = mapped_column(String(32), index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    amount_sign: Mapped[str] = mapped_column(String(16), index=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_field: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_oper_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bonus_type_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    logistics_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_allocated_to_sku: Mapped[bool] = mapped_column(Boolean, default=False)
    allocation_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
