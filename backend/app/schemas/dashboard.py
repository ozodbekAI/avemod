from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field
from app.schemas.data_quality import DataQualityBucketSummary, DataQualitySummaryBlock


class SKUProfitabilityRow(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    finance_rows: int
    gross_units: int
    return_units: int
    net_units: int
    realized_revenue: float
    revenue_final: float = 0.0
    for_pay: float
    wb_commission: float = 0.0
    payment_processing: float = 0.0
    pvz_reward: float = 0.0
    wb_logistics: float = 0.0
    wb_logistics_rebill: float = 0.0
    acceptance: float = 0.0
    penalty: float = 0.0
    deduction: float = 0.0
    marketing_deduction: float = 0.0
    loyalty: float = 0.0
    other_wb_expenses: float = 0.0
    total_wb_expenses: float = 0.0
    commission: float
    acquiring_fee: float
    logistics: float
    paid_acceptance: float
    storage: float
    penalties: float
    deductions: float
    additional_payments: float
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_final: float = 0.0
    ad_spend_source: str = ""
    ad_spend_delta: float = 0.0
    ad_spend: float
    raw_ad_spend: float = 0.0
    source_ad_spend: float = 0.0
    capped_ad_spend: float = 0.0
    overallocated_ad_spend: float = 0.0
    unallocated_ad_spend: float = 0.0
    ads_allocation_status: str = ""
    final_profit_allowed: bool = True
    estimated_cogs: float
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_seller_costs: float = 0.0
    additional_income: float = 0.0
    net_profit_after_all_expenses: float | None = None
    expense_data_quality: str = "partial"
    matched_cost_rows: int
    estimated_profit: float | None
    margin_percent: float | None
    roi_percent: float | None
    drr_percent: float | None
    closing_stock_qty: float | None
    has_manual_cost: bool
    has_real_manual_cost: bool = False
    has_placeholder_cost: bool = False
    business_trusted: bool = False
    operational_trusted: bool = False
    financial_final: bool = False
    cost_source: str | None
    cost_truth_level: str | None = None
    trust_state: str = "blocked"
    cost_trust_policy: str | None = None
    supplier_confirmed_revenue_coverage_percent: float = 0.0
    operator_baseline_revenue_coverage_percent: float = 0.0
    trusted_revenue_cost_coverage_percent: float = 0.0
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    blocked_reasons: list[str] = []


class ArticleIdentity(BaseModel):
    nm_id: int
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None


class ArticleCompleteness(BaseModel):
    has_product_card: bool
    has_price: bool
    has_orders: bool
    has_sales: bool
    has_stock: bool
    has_finance: bool
    has_ads: bool
    has_funnel: bool
    has_manual_cost: bool


class ArticlePriceSnapshot(BaseModel):
    currency: str | None
    discount: int | None
    club_discount: int | None
    editable_size_price: bool | None
    sizes_count: int
    min_price: float | None
    max_price: float | None
    min_discounted_price: float | None
    max_discounted_price: float | None


class ArticleOperationsSummary(BaseModel):
    orders_count: int
    cancelled_orders_count: int
    orders_gross_amount: float
    orders_finished_amount: float
    sales_count: int
    returns_count: int
    sales_gross_amount: float
    sales_for_pay: float
    first_event_at: datetime | None
    last_event_at: datetime | None


class ArticleFinanceSummary(BaseModel):
    report_rows_count: int
    gross_units: int
    return_units: int
    net_units: int
    realized_revenue: float
    revenue_final: float = 0.0
    for_pay: float
    wb_commission: float = 0.0
    payment_processing: float = 0.0
    pvz_reward: float = 0.0
    wb_logistics: float = 0.0
    wb_logistics_rebill: float = 0.0
    acceptance: float = 0.0
    penalty: float = 0.0
    deduction: float = 0.0
    marketing_deduction: float = 0.0
    loyalty: float = 0.0
    other_wb_expenses: float = 0.0
    total_wb_expenses: float = 0.0
    commission: float
    acquiring_fee: float
    logistics: float
    paid_acceptance: float
    storage: float
    penalties: float
    deductions: float
    additional_payments: float
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_final: float = 0.0
    ad_spend_source: str = ""
    ad_spend_delta: float = 0.0
    estimated_cogs: float | None
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_seller_costs: float = 0.0
    additional_income: float = 0.0
    estimated_profit_before_ads: float | None
    net_profit_after_all_expenses: float | None = None
    expense_data_quality: str = "partial"
    first_report_date: date | None
    last_report_date: date | None


class ArticleAdsSummary(BaseModel):
    stats_rows_count: int
    spend: float
    operational_spend: float = 0.0
    finance_spend: float = 0.0
    final_spend: float = 0.0
    spend_source: str = ""
    spend_delta: float = 0.0
    raw_allocated_spend: float = 0.0
    capped_allocated_spend: float = 0.0
    overallocated_spend: float = 0.0
    unallocated_spend: float = 0.0
    allocation_status: str = ""
    final_profit_allowed: bool = True
    views: int
    clicks: int
    orders: int
    atbs: int


class ArticleFunnelSummary(BaseModel):
    days_count: int
    open_count: int
    cart_count: int
    order_count: int
    buyout_count: int
    cancel_count: int


class ArticleStockSummary(BaseModel):
    snapshot_at: datetime | None
    rows_count: int
    quantity: float
    quantity_full: float
    in_way_to_client: float
    in_way_from_client: float
    warehouses: list[str]


class ArticleManualCostMatch(BaseModel):
    matched: bool
    source: str | None
    unit_cost: float | None
    cost_price: float | None
    seller_other_expense: float | None = None
    packaging_cost: float | None
    inbound_logistics_cost: float | None
    total_unit_cost: float | None
    supplier: str | None
    currency: str | None
    valid_from: date | None
    valid_to: date | None
    comment: str | None
    is_placeholder: bool = False
    is_business_trusted: bool = True
    supplier_confirmed: bool = False
    confidence: str = ""
    reason: str = ""
    cost_truth_level: str | None = None
    cost_truth_label: str | None = None


class ArticleDailyEconomics(BaseModel):
    days_count: int
    sales_qty: int
    returns_qty: int
    net_qty: int
    revenue: float
    revenue_final: float = 0.0
    for_pay: float
    wb_expenses: float
    total_wb_expenses: float = 0.0
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_seller_costs: float = 0.0
    additional_income: float = 0.0
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_final: float = 0.0
    ad_spend_source: str = ""
    ad_spend_delta: float = 0.0
    ad_spend: float
    raw_ad_spend: float = 0.0
    source_ad_spend: float = 0.0
    overallocated_ad_spend: float = 0.0
    unallocated_ad_spend: float = 0.0
    ads_allocation_status: str = ""
    final_profit_allowed: bool = True
    estimated_cogs: float | None
    estimated_profit_before_ads: float | None
    estimated_profit_after_ads: float | None
    net_profit_after_all_expenses: float | None = None
    expense_data_quality: str = "partial"
    margin_percent: float | None
    roi_percent: float | None
    drr_percent: float | None


class ArticleDailyPoint(BaseModel):
    date: date
    revenue: float
    ad_spend: float
    profit: float | None
    units: int


class ArticleIssueSummary(BaseModel):
    id: int
    domain: str
    code: str
    severity: str
    message: str
    detected_at: datetime
    source_table: str | None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    age_bucket: str | None = None


class ArticleNote(BaseModel):
    at: datetime | None
    author: str | None
    text: str


class ArticleReconciliationSummary(BaseModel):
    pending_count: int
    warning_count: int
    error_count: int
    ignored_count: int
    mart_matches_article: bool = True
    mart_matches_finance: bool = False
    finance_matches_operational: bool | None = None
    revenue_matches_mart: bool
    mart_revenue_total: float
    article_revenue_total: float
    finance_report_revenue_total: float
    difference_amount: float
    difference_ratio: float | None
    difference_ratio_percent: float | None = None
    mismatch_reason: str | None = None


class ArticleAuditRead(BaseModel):
    operational_trusted: bool = False
    business_trusted: bool = False
    financial_final: bool = False
    trust_state: str = "blocked"
    cost_trust_policy: str | None = None
    supplier_confirmed_revenue_coverage_percent: float = 0.0
    operator_baseline_revenue_coverage_percent: float = 0.0
    trusted_revenue_cost_coverage_percent: float = 0.0
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    all_open_issues_total: int = 0
    blocking_open_issues_total: int = 0
    identity: ArticleIdentity
    completeness: ArticleCompleteness
    price: ArticlePriceSnapshot | None
    operations: ArticleOperationsSummary
    finance: ArticleFinanceSummary
    ads: ArticleAdsSummary
    funnel: ArticleFunnelSummary
    stock: ArticleStockSummary
    manual_cost: ArticleManualCostMatch | None
    daily_economics: ArticleDailyEconomics | None
    daily_series: list[ArticleDailyPoint]
    reconciliation: ArticleReconciliationSummary
    issues_total: int
    issues_limit: int
    issues_offset: int
    issues: list[ArticleIssueSummary]
    notes: list[ArticleNote]


class DashboardHealthIssueBucket(DataQualityBucketSummary):
    pass


class DashboardHealthDomainStatus(BaseModel):
    domain: str
    latest_status: str | None
    latest_finished_at: datetime | None
    last_successful_at: datetime | None
    latest_error_text: str | None
    cursor_status: str | None
    cursor_last_synced_at: datetime | None


class DashboardCostCoverageBlock(BaseModel):
    operational_cost_coverage_percent: float = 0.0
    operational_label: str = ""
    supplier_confirmed_cost_coverage_percent: float = 0.0
    supplier_confirmed_label: str = ""
    business_accepted_cost_coverage_percent: float = 0.0
    business_accepted_label: str = ""
    cost_policy: str = "operator_baseline"
    cost_truth_level: str = "missing"
    can_use_for_operations: bool = False
    can_use_for_final_profit: bool = False
    missing_cost_revenue: float = 0.0
    operator_baseline_revenue: float = 0.0
    supplier_confirmed_revenue: float = 0.0
    message: str = ""


class DashboardDataHealth(BaseModel):
    account_id: int
    open_issues_total: int
    all_open_issues_total: int = 0
    blocking_open_issues_total: int = 0
    data_health_blockers_total: int = 0
    dq_summary_blockers_total: int = 0
    trust_consistency_status: str = "consistent"
    trust_consistency_warning: str | None = None
    failed_domains: list[str]
    skipped_domains: list[str]
    missed_days_count: int
    missing_manual_cost_count: int
    unmatched_sku_count: int
    all_open_unmatched_sku_count: int = 0
    open_unmatched_sku_count: int = 0
    blocking_unmatched_sku_count: int = 0
    resolved_unmatched_sku_count: int = 0
    all_open_finance_mismatch_count: int = 0
    blocking_finance_mismatch_count: int = 0
    all_open_cost_issue_count: int = 0
    blocking_cost_issue_count: int = 0
    all_open_stock_issue_count: int = 0
    blocking_stock_issue_count: int = 0
    duplicate_srid_count: int
    active_sku_count: int
    active_sku_with_manual_cost_count: int
    placeholder_manual_cost_count: int
    real_manual_cost_count: int = 0
    trusted_manual_cost_count: int = 0
    revenue_rows_with_cost: int
    revenue_rows_without_cost: int
    revenue_with_cost: float
    revenue_without_cost: float
    revenue_with_real_cost: float = 0
    revenue_with_placeholder_cost: float = 0
    sku_cost_coverage_percent: float | None
    revenue_cost_coverage_percent: float | None
    real_revenue_cost_coverage_percent: float | None = None
    trusted_revenue_cost_coverage_percent: float | None = None
    supplier_confirmed_revenue_coverage_percent: float | None = None
    operator_baseline_revenue_coverage_percent: float | None = None
    cost_trust_policy: str = "operator_baseline"
    cost_coverage: DashboardCostCoverageBlock = Field(
        default_factory=DashboardCostCoverageBlock
    )
    classified_unmatched_sku_count: int = 0
    business_trusted: bool = False
    operational_trusted: bool = False
    financial_final: bool = False
    trust_state: str = "blocked"
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    blocked_reasons: list[str] = []
    can_generate_business_actions: bool = False
    ad_cluster_rows: int
    ad_cluster_state: str | None = None
    ad_cluster_reason: str | None = None
    latest_stocks_status: str | None = None
    issue_buckets: list[DashboardHealthIssueBucket]
    data_quality_summary: DataQualitySummaryBlock = Field(
        default_factory=DataQualitySummaryBlock
    )
    domains: list[DashboardHealthDomainStatus]
    notes: list[str]
