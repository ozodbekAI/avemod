from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class MartRefreshRequest(BaseModel):
    account_id: int
    date_from: date | None = None
    date_to: date | None = None


class MartRefreshResponse(BaseModel):
    account_id: int
    date_from: date
    date_to: date
    sku_rows: int
    stock_rows: int
    finance_rows: int
    account_expense_rows: int
    reconciliation_rows: int


class MartBusinessDailyRead(BaseModel):
    account_id: int
    stat_date: date
    revenue: float = 0.0
    payout: float = 0.0
    expenses: float = 0.0
    total_wb_expenses: float = 0.0
    total_seller_costs: float = 0.0
    ad_spend: float = 0.0
    profit: float = 0.0
    sku_rows: int = 0
    expense_rows: int = 0


class MartSKUDailyRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    order_rows: int
    ordered_units: int
    cancelled_orders: int
    sale_rows: int
    finance_rows: int
    operational_sales_qty: int
    operational_return_qty: int
    operational_revenue: float | None
    operational_for_pay: float | None
    finance_sales_qty: int
    finance_return_qty: int
    finance_net_units: int
    finance_revenue: float | None
    finance_for_pay: float | None
    final_sales_qty: int
    final_return_qty: int
    final_net_qty: int
    final_revenue: float | None
    revenue_final: float | None = None
    final_for_pay: float | None
    final_revenue_source: str | None
    wb_commission: float | None = None
    payment_processing: float | None = None
    pvz_reward: float | None = None
    wb_logistics: float | None = None
    wb_logistics_rebill: float | None = None
    acceptance: float | None = None
    penalty: float | None = None
    deduction: float | None = None
    marketing_deduction: float | None = None
    loyalty: float | None = None
    other_wb_expenses: float | None = None
    total_wb_expenses: float | None = None
    seller_cogs: float | None = None
    seller_other_expense: float | None = None
    total_seller_expenses: float | None = None
    total_seller_costs: float | None = None
    commission: float | None
    acquiring_fee: float | None
    logistics: float | None
    paid_acceptance: float | None
    storage: float | None
    penalties: float | None
    deductions: float | None
    additional_payments: float | None
    additional_income: float | None = None
    ad_spend_operational: float | None = None
    ad_spend_finance: float | None = None
    ad_spend_final: float | None = None
    ad_spend_source: str | None = None
    ad_spend_delta: float | None = None
    ad_spend: float | None
    ad_views: int
    ad_clicks: int
    funnel_opens: int
    funnel_carts: int
    funnel_orders: int
    funnel_buyouts: int
    opening_stock_qty: float | None
    closing_stock_qty: float | None
    in_way_to_client: float | None
    in_way_from_client: float | None
    current_price: float | None
    current_discounted_price: float | None
    avg_sale_price: float | None
    seller_discount: int | None
    club_discount: int | None
    cost_price: float | None
    packaging_cost: float | None
    inbound_logistics_cost: float | None
    total_unit_cost: float | None
    estimated_cogs: float | None
    estimated_profit_before_ads: float | None
    estimated_profit_after_ads: float | None
    net_profit_after_all_expenses: float | None = None
    expense_data_quality: str | None = None
    margin_percent: float | None
    roi_percent: float | None
    drr_percent: float | None
    has_manual_cost: bool
    has_real_manual_cost: bool
    has_placeholder_cost: bool
    business_trusted: bool
    cost_source: str | None
    has_open_issues: bool
    payload: dict

    model_config = {"from_attributes": True}


class MartStockDailyRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    warehouse_id: int | None
    warehouse_name: str | None
    quantity: float | None
    quantity_full: float | None
    in_way_to_client: float | None
    in_way_from_client: float | None
    days_since_last_sale: int | None
    sales_7d: int
    sales_14d: int
    sales_30d: int
    avg_sales_per_day_30d: float | None
    days_of_stock: float | None
    turnover_rate: float | None
    is_out_of_stock_risk: bool
    is_dead_stock: bool
    payload: dict

    model_config = {"from_attributes": True}


class MartFinanceReconciliationRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    srid: str
    sku_id: int | None
    order_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    order_date: date | None
    sale_date: date | None
    finance_sale_date: date | None
    finance_rr_date: date | None
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    order_rows: int
    sale_rows: int
    finance_rows: int
    has_order: bool
    has_sale: bool
    has_finance: bool
    order_revenue: float | None
    sale_revenue: float | None
    finance_revenue: float | None
    sale_for_pay: float | None
    finance_for_pay: float | None
    revenue_delta: float | None
    for_pay_delta: float | None
    status: str
    payload: dict

    model_config = {"from_attributes": True}


class MartAccountExpenseDailyRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    source_rows: int
    wb_commission: float | None = None
    payment_processing: float | None = None
    pvz_reward: float | None = None
    wb_logistics: float | None = None
    wb_logistics_rebill: float | None = None
    acceptance: float | None = None
    penalty: float | None = None
    deduction: float | None = None
    marketing_deduction: float | None = None
    loyalty: float | None = None
    other_wb_expenses: float | None = None
    total_wb_expenses: float | None = None
    commission: float | None
    acquiring_fee: float | None
    logistics: float | None
    paid_acceptance: float | None
    storage: float | None
    penalties: float | None
    deductions: float | None
    additional_payments: float | None
    ad_spend_operational: float | None = None
    ad_spend_finance: float | None = None
    ad_spend_final: float | None = None
    ad_spend_source: str | None = None
    ad_spend_delta: float | None = None
    seller_cogs: float | None = None
    seller_other_expense: float | None = None
    total_seller_expenses: float | None = None
    total_seller_costs: float | None = None
    net_profit_after_all_expenses: float | None = None
    total_expense: float | None
    additional_income: float | None = None
    expense_data_quality: str | None = None
    payload: dict

    model_config = {"from_attributes": True}


class MartReconciliationDailyRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    sku_id: int
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    orders_qty: int
    orders_amount: float | None
    sales_qty: int
    sales_amount: float | None
    returns_qty: int
    returns_amount: float | None
    finance_qty: int
    finance_revenue: float | None
    finance_for_pay: float | None
    ad_spend_operational: float | None = None
    ad_spend_finance: float | None = None
    ad_spend_final: float | None = None
    ad_spend_source: str | None = None
    ad_spend_delta: float | None = None
    ad_spend: float | None
    ad_orders: int
    opening_stock_qty: float | None
    closing_stock_qty: float | None
    avg_sale_price: float | None
    current_price: float | None
    current_discounted_price: float | None
    revenue_delta: float | None
    for_pay_delta: float | None
    status_bucket: str | None
    status_reason: str | None
    has_order_without_sale: bool
    has_sale_without_finance: bool
    has_finance_without_sale: bool
    has_stock_without_sales: bool
    has_ad_spend_without_sales: bool
    has_price_anomaly: bool
    payload: dict

    model_config = {"from_attributes": True}
