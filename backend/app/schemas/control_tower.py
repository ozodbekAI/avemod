from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator
from app.schemas.money_trust import MoneyTrustInfo

from app.schemas.money_management import ExpenseBreakdownSummaryRead, ProfitCascadeRead


class OwnerActionSummary(BaseModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    data_blocked_count: int = 0
    business_actionable_count: int = 0


class OwnerDashboardItem(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    title: str | None
    action_type: str
    priority: str
    confidence: str
    trust_state: str
    reason: str
    expected_effect_amount: float | None


class OwnerDashboardTrust(BaseModel):
    status: str = ""
    business_status: str = ""
    trust_state: str = ""
    business_trusted: bool = False
    operational_trusted: bool = False
    financial_final: bool = False
    cost_trust_policy: str | None = None
    supplier_confirmed_revenue_coverage_percent: float = 0.0
    operator_baseline_revenue_coverage_percent: float = 0.0
    trusted_revenue_cost_coverage_percent: float = 0.0
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    all_open_issues_total: int = 0
    blocking_open_issues_total: int = 0
    blocked_reasons: list[str] = Field(default_factory=list)
    confidence: str = ""
    human_message: str = ""


class OwnerMessage(BaseModel):
    status: str = ""
    title: str = ""
    reason: str = ""
    today_focus: str = ""


class OwnerWbDailyPoint(BaseModel):
    date: date
    orders_amount: float = 0.0
    sales_amount: float = 0.0
    open_count: int = 0
    cart_count: int = 0
    order_count: int = 0
    buyout_count: int = 0
    cart_conversion_percent: float | None = None
    order_conversion_percent: float | None = None
    buyout_percent: float | None = None
    wb_expenses_total: float = 0.0


class OwnerAdsDailyPoint(BaseModel):
    date: date
    source_spend: float = 0.0
    impressions: int = 0
    card_views: int = 0
    ctr_percent: float | None = None
    orders_count: int = 0
    orders_amount: float = 0.0
    source_drr_percent: float | None = None
    avg_position: float | None = None


class OwnerWbSummary(BaseModel):
    rows_count: int = 0
    sku_count: int = 0
    nm_count: int = 0
    orders_amount: float = 0.0
    orders_count: int = 0
    sales_amount: float = 0.0
    sales_count: int = 0
    returns_count: int = 0
    buyout_count: int = 0
    funnel_orders_count: int = 0
    open_count: int = 0
    cart_count: int = 0
    cart_conversion_percent: float | None = None
    order_conversion_percent: float | None = None
    buyout_percent: float | None = None
    margin_amount: float | None = None
    margin_percent: float | None = None
    cogs: float = 0.0
    wb_expenses_total: float = 0.0
    wb_commission: float = 0.0
    logistics: float = 0.0
    acceptance: float = 0.0
    penalties: float = 0.0
    storage: float = 0.0
    missed_orders_amount: float = 0.0
    missed_orders_count: int = 0
    card_views: int = 0
    turnover_days: float | None = None
    stock_qty: float = 0.0
    daily: list[OwnerWbDailyPoint] = Field(default_factory=list)


class OwnerAdsSummary(BaseModel):
    rows_count: int = 0
    campaign_count: int = 0
    impressions: int = 0
    card_views: int = 0
    ctr_percent: float | None = None
    spend: float = 0.0
    profit_spend: float = 0.0
    source_spend: float = 0.0
    allocation_gap: float = 0.0
    drr_percent: float | None = None
    source_drr_percent: float | None = None
    orders_amount: float = 0.0
    orders_count: int = 0
    cpc: float | None = None
    roas: float | None = None
    daily: list[OwnerAdsDailyPoint] = Field(default_factory=list)


class OwnerDashboardRead(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    account_id: int
    date_from: date
    date_to: date
    trust_state: str
    blocked_reasons: list[str] = Field(default_factory=list)
    can_generate_business_actions: bool = False
    business_trusted: bool = False
    operational_trusted: bool = False
    financial_final: bool = False
    cost_trust_policy: str | None = None
    supplier_confirmed_revenue_coverage_percent: float = 0.0
    operator_baseline_revenue_coverage_percent: float = 0.0
    trusted_revenue_cost_coverage_percent: float = 0.0
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    all_open_issues_total: int = 0
    blocking_open_issues_total: int = 0
    trust: OwnerDashboardTrust = Field(default_factory=OwnerDashboardTrust)
    owner_message: OwnerMessage = Field(default_factory=OwnerMessage)
    primary_message: str | None = None
    revenue: float
    revenue_final: float = 0.0
    net_profit: float | None
    margin_percent: float | None
    roi_percent: float | None
    ad_spend: float
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_final: float = 0.0
    ad_spend_source: str = ""
    ad_spend_delta: float = 0.0
    stock_value: float
    unallocated_expenses: float = 0.0
    total_wb_expenses: float = 0.0
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_seller_costs: float = 0.0
    additional_income: float = 0.0
    expense_breakdown: ExpenseBreakdownSummaryRead | None = None
    profit_cascade: ProfitCascadeRead | None = None
    net_profit_after_all_expenses: float | None = None
    expense_data_quality: str = "partial"
    overstock_value: float
    out_of_stock_risk_count: int
    negative_profit_sku_count: int
    blocked_data_sku_count: int
    action_summary: OwnerActionSummary
    wb_summary: OwnerWbSummary = Field(default_factory=OwnerWbSummary)
    ads_summary: OwnerAdsSummary = Field(default_factory=OwnerAdsSummary)
    top_risks: list[OwnerDashboardItem] = Field(default_factory=list)
    top_opportunities: list[OwnerDashboardItem] = Field(default_factory=list)
    next_actions_preview: list[OwnerDashboardItem] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ControlTowerSkuRow(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    revenue: float
    revenue_final: float = 0.0
    net_profit: float | None
    net_profit_after_all_expenses: float | None = None
    margin_percent: float | None
    roi_percent: float | None
    ad_spend: float
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_final: float = 0.0
    ad_spend_source: str = ""
    ad_spend_delta: float = 0.0
    raw_ad_spend: float = 0.0
    source_ad_spend: float = 0.0
    capped_ad_spend: float = 0.0
    overallocated_ad_spend: float = 0.0
    unallocated_ad_spend: float = 0.0
    ads_allocation_status: str = ""
    final_profit_allowed: bool = True
    drr_percent: float | None
    total_wb_expenses: float = 0.0
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_seller_costs: float = 0.0
    additional_income: float = 0.0
    expense_data_quality: str = "partial"
    stock_qty: float | None
    days_of_stock: float | None
    stock_value: float | None
    safe_price_gap: float | None
    cost_truth_level: str | None
    trust_state: str
    blocked_reasons: list[str] = Field(default_factory=list)
    sku_status: str
    priority_score: float
    open_action_count: int = 0


class ControlTowerSkuDetail(BaseModel):
    summary: ControlTowerSkuRow
    actions: list["ActionRecommendationRead"] = Field(default_factory=list)
    price_safety: "PriceSafetyRow | None" = None
    purchase_plan: "PurchasePlanRow | None" = None
    notes: list[str] = Field(default_factory=list)


class ActionRecommendationRead(BaseModel):
    id: int
    account_id: int
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    title: str | None
    action_type: str
    category: str = ""
    priority: str
    status: str
    reason_code: str
    reason: str
    reason_short: str
    reason_full: str
    business_reason: str = ""
    next_step: str = ""
    calculation_basis: str | None
    expected_effect_amount: float | None
    priority_score: float = 0.0
    confidence: str
    trust_state: str
    financial_final: bool = False
    blocked_reasons: list[str] = Field(default_factory=list)
    source_date_from: date | None
    source_date_to: date | None
    source_snapshot_hash: str | None
    assigned_to: int | None
    deadline_at: datetime | None
    resolved_at: datetime | None
    user_comment: str | None
    payload: dict = Field(default_factory=dict)
    what_to_do: str | None = None
    why: str | None = None
    how_to_fix: list[str] = Field(default_factory=list)
    required_cash: float | None = None
    money_effect: dict = Field(default_factory=dict)
    deadline_hint: str | None = None
    linked_entity: dict | None = None
    affected_nm_ids: list[int] = Field(default_factory=list)
    affected_sku_ids: list[int] = Field(default_factory=list)
    source_endpoint: str = ""
    money_trust: MoneyTrustInfo | None = None
    seller_visible_by_default: bool = True
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ActionRecommendationListItem(BaseModel):
    id: int
    account_id: int
    status: str
    priority: str
    action_type: str
    title: str | None
    short_reason: str
    expected_effect_amount: float | None
    confidence: str
    money_trust: MoneyTrustInfo | None = None
    seller_visible_by_default: bool = True
    linked_entity_type: str | None = None
    linked_entity_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    created_at: datetime
    updated_at: datetime


class ActionRecommendationUpdateRequest(BaseModel):
    status: str | None = None
    assigned_to: int | None = None
    comment: str | None = None


class ActionRecommendationBulkUpdateRequest(BaseModel):
    ids: list[int]
    status: str
    assigned_to: int | None = None
    comment: str | None = None


class AlertBulkUpdateRequest(BaseModel):
    ids: list[int]
    status: str
    snoozed_until: datetime | None = None


class BulkMutationResponse(BaseModel):
    updated_count: int


class PurchasePlanRow(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    title: str | None
    brand: str | None = None
    subject_name: str | None = None
    barcode: str | None = None
    tech_size: str | None = None
    photo_url: str | None = None
    image_url: str | None = None
    status: str
    decision: str = ""
    trust_state: str
    sales_velocity_daily: float
    sales_7d: int = 0
    sales_14d: int = 0
    sales_30d: int = 0
    sales_trend_units: int = 0
    sales_trend_percent: float | None = None
    sales_trend_direction: str = "flat"
    days_since_last_sale: int | None = None
    available_stock: float
    in_transit_qty: float
    days_of_stock: float | None
    lead_time_days: int
    safety_days: int
    recommended_qty: int
    required_cash: float
    expected_profit: float | None
    stock_value: float = 0.0
    frozen_cash: float = 0.0
    current_price: float | None = None
    current_discounted_price: float | None = None
    avg_sale_price: float | None = None
    unit_cost: float | None = None
    net_profit_per_unit: float | None = None
    margin_percent: float | None = None
    roi_percent: float | None = None
    is_profitable: bool | None = None
    risk: str | None
    reason: str
    main_reason: str = ""
    missing_data: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    wait_data_reasons: list[str] = Field(default_factory=list)
    next_step: str = ""
    confidence: str = ""
    decision_confidence: str = ""
    cost_source: str | None = None
    cost_truth: str | None = None
    cost_truth_level: str | None = None
    financial_final: bool = False
    money_effect: dict = Field(default_factory=dict)
    variant_count: int = 1
    size_breakdown: list[dict] = Field(default_factory=list)
    region_breakdown: list[dict] = Field(default_factory=list)
    warehouse_breakdown: list[dict] = Field(default_factory=list)


class PurchasePlanWaitDataReasonCounts(BaseModel):
    finance: int = 0
    cost: int = 0
    stock: int = 0
    velocity: int = 0
    sales: int = 0


class PurchasePlanSummary(BaseModel):
    total_count: int = 0
    page_count: int = 0
    total_positions: int = 0
    total_items: int = 0
    reorder_count: int = 0
    liquidate_count: int = 0
    do_not_buy_count: int = 0
    watch_count: int = 0
    wait_data_count: int = 0
    required_cash_total: float = 0.0
    expected_profit_total: float = 0.0
    stock_value_total: float = 0.0
    frozen_cash_total: float = 0.0
    total_required_cash: float = 0.0
    total_expected_profit: float = 0.0
    total_stock_value: float = 0.0
    wait_data_reason_counts: PurchasePlanWaitDataReasonCounts = Field(
        default_factory=PurchasePlanWaitDataReasonCounts
    )


class PurchasePlanPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PurchasePlanRow]
    summary: PurchasePlanSummary = Field(default_factory=PurchasePlanSummary)
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None


class PriceSafetyPromotion(BaseModel):
    promotion_id: int
    name: str | None = None
    promo_type: str | None = None
    status: str
    in_action: bool = False
    start_at: datetime | None = None
    end_at: datetime | None = None
    price: float | None = None
    currency_code: str | None = None
    plan_price: float | None = None
    discount: int | None = None
    plan_discount: int | None = None
    plan_safe_gap: float | None = None
    plan_target_gap: float | None = None
    plan_state: str | None = None
    participation_percentage: int | None = None
    in_promo_action_leftovers: int | None = None
    in_promo_action_total: int | None = None
    not_in_promo_action_leftovers: int | None = None
    not_in_promo_action_total: int | None = None
    exception_products_count: int | None = None
    advantages: list[str] = Field(default_factory=list)
    description: str | None = None


class PriceSafetyRow(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    title: str | None
    current_price: float | None
    current_discounted_price: float | None
    average_sale_price: float | None
    reference_price: float | None = None
    break_even_price: float | None
    target_margin_price: float | None
    safe_price_gap: float | None
    safe_price_gap_unit: str = "RUB"
    safe_price_gap_kind: str = "currency_amount"
    target_margin_gap: float | None = None
    target_margin_gap_unit: str = "RUB"
    target_margin_gap_kind: str = "currency_amount"
    estimated_margin_at_current_price: float | None
    estimated_margin_percent: float | None = None
    estimated: bool
    confidence: str
    action_hint: str | None
    price_source: str | None = None
    calculation_state: str = "not_computable"
    not_computable_reason: str | None = None
    not_computable_reasons: list[str] = Field(default_factory=list)
    data_state: str | None = None
    mapping_status: str | None = None
    currency_iso_code: str | None = None
    discount: int | None = None
    club_discount: int | None = None
    editable_size_price: bool | None = None
    is_bad_turnover: bool | None = None
    sizes_count: int = 0
    min_size_price: float | None = None
    max_size_price: float | None = None
    min_discounted_price: float | None = None
    max_discounted_price: float | None = None
    min_club_discounted_price: float | None = None
    max_club_discounted_price: float | None = None
    wholesale_discount_thresholds: list[dict[str, Any]] = Field(default_factory=list)
    quarantine: bool = False
    quarantine_new_price: float | None = None
    quarantine_old_price: float | None = None
    quarantine_new_discount: int | None = None
    quarantine_old_discount: int | None = None
    quarantine_price_diff: float | None = None
    promotion_calendar_synced: bool = False
    promotion_active_count: int = 0
    promotion_available_count: int = 0
    promotion_names: list[str] = Field(default_factory=list)
    promotion_nearest_name: str | None = None
    promotion_nearest_starts_at: datetime | None = None
    promotion_min_plan_price: float | None = None
    promotion_max_plan_discount: int | None = None
    promotion_plan_safe_gap: float | None = None
    promotion_plan_target_gap: float | None = None
    promotion_plan_state: str | None = None
    promotion_details: list[PriceSafetyPromotion] = Field(default_factory=list)


class PriceSafetySummary(BaseModel):
    total_count: int = 0
    computed_count: int = 0
    below_break_even_count: int = 0
    not_computable_count: int = 0
    price_increase_review_count: int = 0
    safe_count: int = 0
    below_target_margin_count: int = 0
    editable_size_price_count: int = 0
    bad_turnover_count: int = 0
    quarantine_count: int = 0
    wholesale_discount_count: int = 0
    promotion_calendar_synced_count: int = 0
    promotion_active_count: int = 0
    promotion_available_count: int = 0
    promotion_plan_below_break_even_count: int = 0
    promotion_plan_below_target_count: int = 0
    promotion_plan_safe_count: int = 0


class PriceSafetyPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[PriceSafetyRow]
    summary: PriceSafetySummary = Field(default_factory=PriceSafetySummary)
    operational_trusted: bool = False
    business_trusted: bool = False
    financial_final: bool = False
    trust_state: str = "unknown"
    cost_trust_policy: str | None = None
    supplier_confirmed_revenue_coverage_percent: float = 0.0
    operator_baseline_revenue_coverage_percent: float = 0.0
    trusted_revenue_cost_coverage_percent: float = 0.0
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    all_open_issues_total: int = 0
    blocking_open_issues_total: int = 0
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None


class PriceSimulationRequest(BaseModel):
    account_id: int
    sku_id: int | None = None
    nm_id: int | None = None
    price: float = Field(ge=0)
    sales_drop_assumption_percent: float = 0
    expected_sales_drop_percent: float | None = Field(default=None, exclude=True)
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def normalize_legacy_sales_drop_field(self) -> "PriceSimulationRequest":
        if (
            self.expected_sales_drop_percent is not None
            and not self.sales_drop_assumption_percent
        ):
            self.sales_drop_assumption_percent = self.expected_sales_drop_percent
        return self


class PriceSimulationResponse(BaseModel):
    sku_id: int | None
    nm_id: int | None
    simulated_price: float
    expected_revenue: float | None
    expected_profit: float | None
    expected_margin_percent: float | None
    expected_roi_percent: float | None
    break_even_price: float | None
    target_margin_price: float | None
    risk_flag: str | None
    estimated: bool
    confidence: str


class AdsEfficiencySummary(BaseModel):
    total_count: int = 0
    source_ad_spend: float = 0.0
    allocated_ad_spend: float = 0.0
    overallocated_ad_spend: float = 0.0
    unallocated_ad_spend: float = 0.0
    ads_allocation_status: str = ""
    ads_allocation_status_label: str = ""
    drr_percent: float = 0.0
    profit_after_ads: float = 0.0
    source_revenue: float = 0.0
    ctr_percent: float | None = None
    cpc: float | None = None
    cr_percent: float | None = None
    views: int = 0
    clicks: int = 0
    orders: int = 0
    atbs: int = 0
    shks: int = 0
    canceled: int = 0
    matched_count: int = 0
    partial_count: int = 0
    overallocated_count: int = 0
    no_source_count: int = 0
    high_drr_count: int = 0
    negative_profit_count: int = 0
    low_confidence_count: int = 0
    scale_candidate_count: int = 0
    pause_review_count: int = 0
    data_fix_first_count: int = 0


class AdsEfficiencyRow(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    title: str | None
    level: str = "sku"
    level_label: str = "по размеру"
    advert_id: int | None = None
    campaign_name: str | None = None
    campaign_count: int = 0
    advert_ids: list[int] = Field(default_factory=list)
    stats_rows_count: int = 0
    views: int = 0
    clicks: int = 0
    ctr_percent: float | None = None
    cr_percent: float | None = None
    cpc: float | None = None
    orders: int = 0
    atbs: int = 0
    shks: int = 0
    canceled: int = 0
    source_revenue: float = 0.0
    ad_revenue: float = 0.0
    spend_share_percent: float | None = None
    revenue: float
    ad_spend: float
    raw_ad_spend: float = 0.0
    source_ad_spend: float = 0.0
    overallocated_ad_spend: float = 0.0
    unallocated_ad_spend: float = 0.0
    ads_allocation_status: str = ""
    ads_allocation_status_label: str = ""
    final_profit_allowed: bool = True
    net_profit: float | None
    profit_after_ads: float | None = None
    drr_percent: float | None
    stock_qty: float | None
    days_of_stock: float | None
    confidence: str
    action_hint: str | None
    action_label: str = ""
    trust_state: str = ""
    blocked_reasons: list[str] = Field(default_factory=list)


class AdsEfficiencyPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[AdsEfficiencyRow]
    summary: AdsEfficiencySummary = Field(default_factory=AdsEfficiencySummary)
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None


class BusinessSettingsRead(BaseModel):
    account_id: int
    settings: dict
    updated_at: datetime | None = None
    comment: str | None = None


class BusinessPolicyOption(BaseModel):
    value: str
    label: str
    description: str


class BusinessPoliciesRead(BaseModel):
    cost_trust_policy: list[BusinessPolicyOption]


class BusinessSettingsUpdateRequest(BaseModel):
    settings: dict
    comment: str | None = None


class AlertRead(BaseModel):
    id: int
    account_id: int
    action_id: int | None
    alert_type: str
    severity: str
    status: str
    title: str
    message: str
    confidence: str
    payload: dict = Field(default_factory=dict)
    snoozed_until: datetime | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AlertUpdateRequest(BaseModel):
    status: str
    snoozed_until: datetime | None = None


ControlTowerSkuDetail.model_rebuild()
