from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class CardFunnelRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    nm_id: int
    vendor_code: str | None
    title: str | None
    brand_name: str | None = None
    subject_id: int | None = None
    subject_name: str | None = None
    open_count: int | None
    cart_count: int | None
    order_count: int | None
    buyout_count: int | None
    cancel_count: int | None = None
    add_to_cart_conversion: float | None = None
    cart_to_order_conversion: float | None = None
    buyout_percent: float | None = None

    model_config = {"from_attributes": True}


class RegionSalesRead(BaseModel):
    id: int
    account_id: int
    stat_date: date
    region_name: str | None
    country_name: str | None
    city_name: str | None
    federal_district: str | None
    nm_id: int | None
    vendor_code: str | None
    sale_amount: float | None
    sale_amount_percent: float | None
    sale_quantity: int | None
    payload: dict

    model_config = {"from_attributes": True}


class AnalyticsPeriod(BaseModel):
    date_from: date
    date_to: date
    previous_date_from: date
    previous_date_to: date


class AnalyticsComparisonMetric(BaseModel):
    value: float | None = None
    previous_value: float | None = None
    delta: float | None = None
    delta_percent: float | None = None


class AnalyticsSummary(BaseModel):
    open_count: AnalyticsComparisonMetric
    cart_count: AnalyticsComparisonMetric
    order_count: AnalyticsComparisonMetric
    buyout_count: AnalyticsComparisonMetric
    cancel_count: AnalyticsComparisonMetric
    revenue: AnalyticsComparisonMetric
    units_sold: AnalyticsComparisonMetric
    active_cards: AnalyticsComparisonMetric
    cart_rate: AnalyticsComparisonMetric
    order_rate: AnalyticsComparisonMetric
    buyout_rate: AnalyticsComparisonMetric
    avg_order_value: AnalyticsComparisonMetric
    hidden_blocked: int = 0
    hidden_shadowed: int = 0


class AnalyticsMoneySummary(BaseModel):
    revenue: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    for_pay: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    profit: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    margin_percent: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    wb_expenses: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    seller_expenses: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    cost_price: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    orders: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    returns: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    return_rate: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    rows_count: int = 0


class AnalyticsAdSummary(BaseModel):
    spend: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    views: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    clicks: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    orders: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    ctr: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    cpc: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    drr_percent: AnalyticsComparisonMetric = Field(
        default_factory=AnalyticsComparisonMetric
    )
    roas: AnalyticsComparisonMetric = Field(default_factory=AnalyticsComparisonMetric)
    rows_count: int = 0


class AnalyticsStockSummary(BaseModel):
    stock_qty: float = 0
    full_stock_qty: float = 0
    in_way_to_client: float = 0
    in_way_from_client: float = 0
    out_of_stock_risk: int = 0
    dead_stock: int = 0
    avg_days_of_stock: float | None = None
    latest_date: date | None = None
    rows_count: int = 0


class AnalyticsPriceSummary(BaseModel):
    avg_price: float | None = None
    avg_discounted_price: float | None = None
    avg_discount_percent: float | None = None
    bad_turnover: int = 0
    quarantine: int = 0
    goods_count: int = 0
    size_count: int = 0


class AnalyticsTrendPoint(BaseModel):
    date: date
    open_count: float = 0
    cart_count: float = 0
    order_count: float = 0
    buyout_count: float = 0
    cancel_count: float = 0
    revenue: float = 0
    units_sold: float = 0
    for_pay: float = 0
    profit: float = 0
    ad_spend: float = 0
    stock_qty: float = 0
    cart_rate: float | None = None
    order_rate: float | None = None
    buyout_rate: float | None = None


class AnalyticsProductRow(BaseModel):
    nm_id: int
    vendor_code: str | None = None
    title: str | None = None
    brand_name: str | None = None
    subject_name: str | None = None
    open_count: float = 0
    cart_count: float = 0
    order_count: float = 0
    buyout_count: float = 0
    cancel_count: float = 0
    revenue: float = 0
    units_sold: float = 0
    for_pay: float | None = None
    profit: float | None = None
    margin_percent: float | None = None
    wb_expenses: float | None = None
    ad_spend: float | None = None
    drr_percent: float | None = None
    stock_qty: float | None = None
    days_of_stock: float | None = None
    current_price: float | None = None
    current_discounted_price: float | None = None
    return_count: float | None = None
    return_rate: float | None = None
    row_source: str = "funnel"
    cart_rate: float | None = None
    order_rate: float | None = None
    buyout_rate: float | None = None
    open_delta_percent: float | None = None
    order_delta_percent: float | None = None
    revenue_delta_percent: float | None = None
    status: str = "ok"
    issue: str | None = None
    action: str | None = None


class AnalyticsRegionRow(BaseModel):
    country_name: str | None = None
    region_name: str | None = None
    city_name: str | None = None
    federal_district: str | None = None
    revenue: float = 0
    units_sold: float = 0
    cards_count: int = 0
    share_percent: float | None = None


class AnalyticsDataSourceStatus(BaseModel):
    key: str
    label: str
    status: str
    rows: int = 0
    note: str | None = None


class AnalyticsApiCapability(BaseModel):
    key: str
    label: str
    endpoint: str
    status: str
    note: str | None = None


class AnalyticsRecommendation(BaseModel):
    severity: str
    title: str
    detail: str
    action: str
    source: str | None = None


class AnalyticsOverviewRead(BaseModel):
    account_id: int
    period: AnalyticsPeriod
    summary: AnalyticsSummary
    money: AnalyticsMoneySummary = Field(default_factory=AnalyticsMoneySummary)
    ads: AnalyticsAdSummary = Field(default_factory=AnalyticsAdSummary)
    stock: AnalyticsStockSummary = Field(default_factory=AnalyticsStockSummary)
    prices: AnalyticsPriceSummary = Field(default_factory=AnalyticsPriceSummary)
    trend: list[AnalyticsTrendPoint]
    products: list[AnalyticsProductRow]
    regions: list[AnalyticsRegionRow]
    data_sources: list[AnalyticsDataSourceStatus]
    api_capabilities: list[AnalyticsApiCapability]
    recommendations: list[AnalyticsRecommendation]
    export_datasets: list[str]
