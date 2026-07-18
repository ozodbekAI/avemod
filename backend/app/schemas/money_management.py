from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, model_validator
from app.schemas.data_quality import (
    DataQualitySummaryBlock,
    ProblemResolver,
    build_problem_resolver,
    issue_fixability_contract,
)
from app.schemas.evidence import (
    EvidenceLedger,
    confidence_from_trust_state,
    evidence_ledger,
)
from app.schemas.money_trust import MoneyTrustInfo, classify_money_trust
from app.services.evidence import issue_evidence, money_kpi_evidence


class DataTrustInfo(BaseModel):
    state: str
    trust_state: str = ""
    business_trusted: bool
    operational_trusted: bool = False
    financial_final: bool = False
    can_generate_business_actions: bool
    confidence: str
    cost_trust_policy: str | None = None
    supplier_confirmed_revenue_coverage_percent: float = 0.0
    operator_baseline_revenue_coverage_percent: float = 0.0
    trusted_revenue_cost_coverage_percent: float = 0.0
    financial_final_blockers_total: int = 0
    final_profit_blockers_total: int = 0
    all_open_issues_total: int = 0
    blocking_open_issues_total: int = 0
    blocked_reasons: list[str] = Field(default_factory=list)
    human_message: str


class MoneyMeta(BaseModel):
    account_id: int
    date_from: date
    date_to: date
    currency: str = "RUB"
    generated_at: datetime
    data_trust: DataTrustInfo


class BusinessAnswer(BaseModel):
    business_status: str
    title: str
    short_text: str
    main_problem: str = ""
    main_next_step: str = ""


class StoreAnswer(BaseModel):
    what_is_happening: str
    where_money_came_from: str
    where_money_went: str
    where_money_is_now: str
    what_to_do_today: list[str] = Field(default_factory=list)


class RevenueSources(BaseModel):
    operational_revenue: float = 0.0
    operational_revenue_label: str = ""
    finance_confirmed_revenue: float = 0.0
    finance_confirmed_revenue_label: str = ""
    mart_revenue: float = 0.0
    comparison_mart_revenue: float = 0.0
    open_period_revenue: float = 0.0
    open_period_revenue_label: str = ""
    supplier_cost_confirmed_revenue: float = 0.0
    difference_amount: float = 0.0
    difference_percent: float = 0.0
    source_of_truth: str = "mixed"
    reconciliation_status: str = ""
    finance_coverage_date_to: date | None = None
    mismatch_reason: str = ""


class FinanceReconciliationClassifiedDifference(BaseModel):
    expected_lag: float = 0.0
    return_timing: float = 0.0
    finance_only: float = 0.0
    operational_only: float = 0.0
    unallocated_expense: float = 0.0
    account_level_expense: float = 0.0
    unknown: float = 0.0


class FinanceReconciliationBlock(BaseModel):
    status: str = "not_available"
    operational_revenue: float = 0.0
    operational_revenue_label: str = ""
    finance_confirmed_revenue: float = 0.0
    finance_confirmed_revenue_label: str = ""
    difference_amount: float = 0.0
    difference_percent: float = 0.0
    closed_finance_date_from: date | None = None
    closed_finance_date_to: date | None = None
    requested_date_from: date
    requested_date_to: date
    requested_period_label: str = ""
    closed_finance_period_label: str = ""
    open_operational_period_revenue: float = 0.0
    open_operational_period_revenue_label: str = ""
    comparison_scope_label: str = ""
    classified_difference: FinanceReconciliationClassifiedDifference = Field(
        default_factory=FinanceReconciliationClassifiedDifference
    )
    is_final: bool = False
    recommendation: str = ""


class CostCoverageBlock(BaseModel):
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


class MoneyQuality(BaseModel):
    supplier_cost_coverage_percent: float = 0.0
    supplier_confirmed_cost_coverage_percent: float = 0.0
    business_cost_coverage_percent: float = 0.0
    cost_coverage_status: str = ""
    raw_ads_allocated_spend: float = 0.0
    capped_ads_allocated_spend: float = 0.0
    ads_allocation_percent: float = 0.0
    ads_allocation_percent_capped: float = 0.0
    ads_duplicate_ignored_spend: float = 0.0
    ads_overallocated_spend: float = 0.0
    final_profit_allowed: bool = True
    finance_difference_amount: float = 0.0
    finance_difference_percent: float = 0.0
    final_finance_ready: bool = False
    finance_reconciliation_status: str = ""


class MoneyFlowItem(BaseModel):
    code: str
    label: str
    amount: float = 0.0
    direction: str
    confidence: str
    reason: str = ""


class MoneyFlowBlock(BaseModel):
    incoming: list[MoneyFlowItem] = Field(default_factory=list)
    outgoing: list[MoneyFlowItem] = Field(default_factory=list)
    cash_and_stock: list[MoneyFlowItem] = Field(default_factory=list)


class CashAndStockBlock(BaseModel):
    cash_on_wb: float = 0.0
    available_for_withdraw: float = 0.0
    cash_on_wb_current: float = 0.0
    available_for_withdraw_current: float = 0.0
    cash_on_wb_period_end: float = 0.0
    available_for_withdraw_period_end: float = 0.0
    balance_snapshot_at_current: datetime | None = None
    balance_snapshot_at_period_end: datetime | None = None
    stock_value: float = 0.0
    overstock_value: float = 0.0
    in_transit_value: float = 0.0
    frozen_stock_value: float = 0.0
    confidence: str = ""
    reason: str = ""


class MoneySummaryKpis(BaseModel):
    revenue: float
    revenue_final: float = 0.0
    finance_confirmed_revenue: float = 0.0
    finance_reconciliation_operational_revenue: float = 0.0
    finance_difference_amount: float = 0.0
    finance_difference_percent: float = 0.0
    finance_reconciliation_status: str = ""
    supplier_cost_confirmed_revenue: float = 0.0
    supplier_cost_confirmed_revenue_percent: float = 0.0
    business_cost_coverage_percent: float = 0.0
    cost_coverage_status: str = ""
    for_pay: float = 0.0
    net_profit_after_ads: float = 0.0
    profit_after_allocated_ads: float = 0.0
    profit_after_source_ads: float = 0.0
    net_profit_after_overhead: float = 0.0
    margin_percent: float = 0.0
    margin_after_overhead_percent: float = 0.0
    roi_percent: float = 0.0
    roi_on_cogs_percent: float = 0.0
    stock_roi_percent: float = 0.0
    roas_percent: float = 0.0
    profit_confidence: str = ""
    cash_on_wb: float = 0.0
    available_for_withdraw: float = 0.0
    cash_on_wb_current: float = 0.0
    available_for_withdraw_current: float = 0.0
    cash_on_wb_period_end: float = 0.0
    available_for_withdraw_period_end: float = 0.0
    balance_snapshot_at_current: datetime | None = None
    balance_snapshot_at_period_end: datetime | None = None
    wb_expenses_total: float = 0.0
    direct_wb_expenses: float = 0.0
    account_level_expenses: float = 0.0
    allocated_overhead_expenses: float = 0.0
    stock_value: float = 0.0
    overstock_value: float = 0.0
    in_transit_value: float = 0.0
    stock_value_confidence: str = ""
    stock_value_reason: str = ""
    ad_spend: float = 0.0
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_final: float = 0.0
    ad_spend_source: str = ""
    ad_spend_delta: float = 0.0
    ads_source_spend: float = 0.0
    raw_ads_allocated_spend: float = 0.0
    capped_ads_allocated_spend: float = 0.0
    ads_allocated_spend: float = 0.0
    ads_unallocated_spend: float = 0.0
    ads_duplicate_ignored_spend: float = 0.0
    ads_overallocated_spend: float = 0.0
    ads_allocation_status: str = ""
    wb_commission: float = 0.0
    payment_processing: float = 0.0
    pvz_reward: float = 0.0
    wb_logistics: float = 0.0
    wb_logistics_rebill: float = 0.0
    storage: float = 0.0
    acceptance: float = 0.0
    penalty: float = 0.0
    deduction: float = 0.0
    marketing_deduction: float = 0.0
    loyalty: float = 0.0
    additional_payment: float = 0.0
    other_wb_expenses: float = 0.0
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_seller_costs: float = 0.0
    additional_income: float = 0.0
    net_profit_after_all_expenses: float = 0.0
    expense_data_quality: str = "partial"
    logistics_share_percent: float = 0.0
    unallocated_expenses: float = 0.0
    unallocated_expense_ratio_percent: float = 0.0
    negative_profit_sku_count: int = 0
    blocked_data_sku_count: int = 0
    evidence_ledger: dict[str, EvidenceLedger] = Field(default_factory=dict)


class ExpenseComponentBreakdown(BaseModel):
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
    commission: float = 0.0
    acquiring_fee: float = 0.0
    logistics: float = 0.0
    paid_acceptance: float = 0.0
    storage: float = 0.0
    penalties: float = 0.0
    deductions: float = 0.0
    additional_payments: float = 0.0


class AccountLevelExpenseBreakdown(BaseModel):
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
    storage: float = 0.0
    deductions: float = 0.0
    wb_promotion_deductions: float = 0.0
    penalties: float = 0.0
    logistics_unallocated: float = 0.0
    other: float = 0.0


class StoreExpenseWaterfall(BaseModel):
    direct_sku_expenses: ExpenseComponentBreakdown = Field(
        default_factory=ExpenseComponentBreakdown
    )
    account_level_expenses: AccountLevelExpenseBreakdown = Field(
        default_factory=AccountLevelExpenseBreakdown
    )
    unallocated_expenses: float = 0.0
    allocation_status: str = ""
    message: str = ""


class ExpenseBreakdownItemRead(BaseModel):
    group_key: str = ""
    label: str = ""
    amount: float = 0.0
    share_percent: float = 0.0
    category: str | None = None
    source: str | None = None
    is_final: bool = False
    sku_id: int | None = None
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    stat_date: date | None = None
    row_count: int = 0


class ExpenseBreakdownSummaryRead(BaseModel):
    account_id: int = 0
    date_from: date | None = None
    date_to: date | None = None
    group_by: str = "category"
    include_unallocated: bool = True
    revenue_final: float = 0.0
    net_profit_after_all_expenses: float = 0.0
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    ad_spend_final: float = 0.0
    additional_income: float = 0.0
    total_expenses: float = 0.0
    total_wb_expenses: float = 0.0
    total_seller_expenses: float = 0.0
    total_ad_expenses: float = 0.0
    logistics_total: float = 0.0
    logistics_share_base_kind: str = "wb_expenses"
    logistics_share_base_amount: float = 0.0
    logistics_share_percent: float = 0.0
    data_version_hash: str | None = None
    source_of_truth: str = "mixed"
    items: list[ExpenseBreakdownItemRead] = Field(default_factory=list)


class ProfitCascadeRevenueRead(BaseModel):
    code: str = "revenue"
    label: str = "Выручка"
    amount: float = 0.0
    sign: str = "income"


class ProfitCascadeChildRead(BaseModel):
    code: str
    label: str
    amount: float = 0.0
    share_percent: float = 0.0
    source: str = ""
    ad_spend_operational: float = 0.0
    ad_spend_finance: float = 0.0
    ad_spend_source: str = ""


class ProfitCascadeGroupRead(BaseModel):
    code: str
    label: str
    amount: float = 0.0
    sign: str = "expense"
    children: list[ProfitCascadeChildRead] = Field(default_factory=list)


class ProfitCascadeTotalsRead(BaseModel):
    gross_revenue: float = 0.0
    seller_cogs: float = 0.0
    seller_other_expense: float = 0.0
    total_seller_expenses: float = 0.0
    total_wb_expenses: float = 0.0
    total_ad_expenses: float = 0.0
    additional_income: float = 0.0
    net_profit_after_all_expenses: float = 0.0
    logistics_total: float = 0.0
    logistics_share_percent: float = 0.0


class ProfitCascadeValidationRead(BaseModel):
    groups_match_children: bool = True
    profit_formula_valid: bool = True
    issues: list[str] = Field(default_factory=list)


class ProfitCascadeBodyRead(BaseModel):
    revenue: ProfitCascadeRevenueRead = Field(default_factory=ProfitCascadeRevenueRead)
    groups: list[ProfitCascadeGroupRead] = Field(default_factory=list)
    totals: ProfitCascadeTotalsRead = Field(default_factory=ProfitCascadeTotalsRead)
    validation: ProfitCascadeValidationRead = Field(
        default_factory=ProfitCascadeValidationRead
    )


class ProfitCascadeRead(BaseModel):
    account_id: int
    date_from: date
    date_to: date
    currency: str = "RUB"
    source_of_truth: str = "mixed"
    data_version_hash: str | None = None
    financial_final: bool = False
    operational_trusted: bool = False
    trust_state: str = ""
    cascade: ProfitCascadeBodyRead = Field(default_factory=ProfitCascadeBodyRead)


class MoneyExpenseLogisticsRead(BaseModel):
    account_id: int
    date_from: date
    date_to: date
    include_unallocated: bool = True
    total_logistics: float = 0.0
    total_wb_logistics: float = 0.0
    total_wb_logistics_rebill: float = 0.0
    logistics_share_base_kind: str = "wb_expenses"
    logistics_share_base_amount: float = 0.0
    logistics_share_percent: float = 0.0
    delivery_to_client: float = 0.0
    return_from_client: float = 0.0
    cancellation_to_client: float = 0.0
    cancellation_from_client: float = 0.0
    seller_initiated_return: float = 0.0
    defect_return: float = 0.0
    unknown: float = 0.0
    by_category: list[ExpenseBreakdownItemRead] = Field(default_factory=list)
    by_logistics_type: list[ExpenseBreakdownItemRead] = Field(default_factory=list)
    by_bonus_type_name: list[ExpenseBreakdownItemRead] = Field(default_factory=list)
    by_seller_oper_name: list[ExpenseBreakdownItemRead] = Field(default_factory=list)
    by_sku: list[ExpenseBreakdownItemRead] = Field(default_factory=list)
    by_nm: list[ExpenseBreakdownItemRead] = Field(default_factory=list)
    by_day: list[ExpenseBreakdownItemRead] = Field(default_factory=list)


class RiskItem(BaseModel):
    code: str
    title: str
    business_impact: str
    priority: str
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "RiskItem":
        trust = classify_money_trust(
            value=self.title,
            value_type="text",
            confidence="provisional",
            impact_type="probable_loss",
            source_module="money",
            source_endpoint="GET /api/v1/money/summary",
            action_type=self.code,
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = issue_evidence(
                code=self.code,
                title=self.title,
                value=self.title,
                source_table="mart_sku_daily",
                source_endpoint="GET /api/v1/money/summary",
                severity=self.priority,
                next_screen_path="/data-fix"
                if self.priority in {"critical", "high"}
                else "/money",
                next_screen_label="Открыть источник",
            )
        if self.money_trust is None:
            self.money_trust = trust
        self.evidence_ledger.money_trust = self.money_trust
        return self


class RiskSummary(BaseModel):
    critical_count: int = 0
    risks: list[RiskItem] = Field(default_factory=list)


class TopCardPreview(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    title: str | None
    revenue: float
    net_profit: float = 0.0
    stock_value: float = 0.0
    priority_score: float
    status: str
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "TopCardPreview":
        trust = classify_money_trust(
            value=self.net_profit,
            value_type="money",
            confidence="provisional",
            impact_type="opportunity" if self.net_profit >= 0 else "probable_loss",
            source_module="money",
            source_table="mart_sku_daily",
            source_endpoint="GET /api/v1/money/summary",
            action_type=self.status,
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = evidence_ledger(
                value=self.net_profit,
                value_type="money",
                confidence="provisional",
                impact_type="opportunity" if self.net_profit >= 0 else "probable_loss",
                formula_human="Карточка попала в топ по прибыли, риску стока или блокеру данных.",
                formula_code="money_summary.top_cards",
                formula_id=f"top_card:{self.nm_id or self.sku_id or 'unknown'}",
                label=self.title
                or self.vendor_code
                or str(self.nm_id or self.sku_id or "card"),
                unit="RUB",
                source_table="mart_sku_daily",
                source_endpoint="GET /api/v1/money/summary",
                filters={"nm_id": self.nm_id, "sku_id": self.sku_id},
                sample_rows=[
                    {
                        "nm_id": self.nm_id,
                        "sku_id": self.sku_id,
                        "revenue": self.revenue,
                        "net_profit": self.net_profit,
                        "stock_value": self.stock_value,
                    }
                ],
                recheck_rule="Refresh /money/summary after finance/cost/sales sync.",
                money_trust=trust,
            )
        if self.money_trust is None:
            self.money_trust = trust
        self.evidence_ledger.money_trust = self.money_trust
        return self


class TopCardsBlock(BaseModel):
    profitable: list[TopCardPreview] = Field(default_factory=list)
    loss_making: list[TopCardPreview] = Field(default_factory=list)
    stock_risk: list[TopCardPreview] = Field(default_factory=list)
    data_blocked: list[TopCardPreview] = Field(default_factory=list)


class NextActionRead(BaseModel):
    id: int = 0
    action_type: str
    action_group: str = "business"
    category: str = ""
    priority: str
    status: str = "new"
    title: str
    what_to_do: str
    why: str
    business_reason: str = ""
    next_step: str = ""
    how_to_fix: list[str] = Field(default_factory=list)
    expected_effect_amount: float = 0.0
    priority_score: float = 0.0
    required_cash: float = 0.0
    recommended_qty: int = 0
    unit_cost: float = 0.0
    current_stock: float = 0.0
    days_of_stock: float = 0.0
    lead_time_days: int = 0
    safety_days: int = 0
    confidence: str
    financial_final: bool = False
    deadline_hint: str = ""
    deadline_at: datetime | None = None
    linked_entity: dict = Field(default_factory=dict)
    affected_nm_ids: list[int] = Field(default_factory=list)
    affected_sku_ids: list[int] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    money_effect: dict = Field(default_factory=dict)
    source_endpoint: str = ""
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "NextActionRead":
        trust = classify_money_trust(
            value=self.expected_effect_amount,
            value_type="money",
            confidence="confirmed" if self.financial_final else self.confidence,
            impact_type="data_blocker"
            if self.action_group == "data_fix"
            else "opportunity",
            trust_state="confirmed" if self.financial_final else None,
            financial_final=self.financial_final,
            source_module="money",
            source_endpoint=self.source_endpoint or "GET /api/v1/money/summary",
            action_type=self.action_type,
            payload=self.money_effect,
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = evidence_ledger(
                value=self.expected_effect_amount,
                value_type="money",
                confidence=confidence_from_trust_state(
                    "confirmed" if self.financial_final else self.confidence
                ),
                impact_type="data_blocker"
                if self.action_group == "data_fix"
                else "opportunity",
                formula_human=self.why
                or "Действие создано backend-правилом из денежных и операционных сигналов.",
                formula_code=f"money_action.{self.action_type}",
                formula_id=f"money_action:{self.id or self.action_type}",
                label=self.title,
                unit="RUB",
                source_table="mart_sku_daily",
                source_endpoint=self.source_endpoint or "GET /api/v1/money/summary",
                filters={
                    "sku_id": self.linked_entity.get("sku_id"),
                    "nm_id": self.linked_entity.get("nm_id"),
                    "action_type": self.action_type,
                },
                sample_rows=[
                    {
                        **self.linked_entity,
                        "expected_effect_amount": self.expected_effect_amount,
                    }
                ],
                missing_data=self.blocked_reasons,
                next_fix_action={
                    "label": self.next_step or self.title,
                    "source_endpoint": self.source_endpoint
                    or "GET /api/v1/money/summary",
                    "action_type": self.action_type,
                },
                recheck_rule="Mark action done or refresh after the related data source changes.",
                money_trust=trust,
            )
        if self.money_trust is None:
            self.money_trust = self.evidence_ledger.money_trust or trust
        self.evidence_ledger.money_trust = self.money_trust
        return self


class MoneyControlPanelCard(BaseModel):
    code: str
    title: str
    amount: float = 0.0
    currency: str = "RUB"
    trust_state: str = ""
    impact_type: str = ""
    evidence_ledger: EvidenceLedger | None = None
    saved_money_claimed: bool = False


class MoneySourceCoverageItem(BaseModel):
    source: str
    source_code: str | None = None
    status: str = "missing"
    last_synced_at: datetime | None = None
    blocks_calculation: list[str] = Field(default_factory=list)
    action_hint: str = ""

    @model_validator(mode="after")
    def fill_source_code(self) -> "MoneySourceCoverageItem":
        if not self.source_code:
            self.source_code = self.source
        return self


class MoneyProblemActionItem(BaseModel):
    problem_instance_id: int | None = None
    action_id: int | None = None
    code: str = ""
    title: str
    explanation: str = ""
    recommendation: str = ""
    amount: float = 0.0
    trust_state: str = ""
    impact_type: str = ""
    evidence_ledger: EvidenceLedger | None = None
    action_center_href: str | None = None
    data_fix_href: str | None = None
    results_href: str | None = None
    recheck_available: bool = True
    saved_money_claimed: bool = False


class MoneyUnitEconomicsRead(BaseModel):
    price: float | None = None
    cost_price: float | None = None
    commission: float | None = None
    logistics: float | None = None
    ads: float | None = None
    other_expenses: float | None = None
    unit_profit: float | None = None
    margin_pct: float | None = None
    trust_state: str = ""
    blockers: list[str] = Field(default_factory=list)


class MoneyProblemGroups(BaseModel):
    reconciliation: list[MoneyProblemActionItem] = Field(default_factory=list)
    cost: list[MoneyProblemActionItem] = Field(default_factory=list)
    margin_profit: list[MoneyProblemActionItem] = Field(default_factory=list)
    expenses: list[MoneyProblemActionItem] = Field(default_factory=list)
    ads: list[MoneyProblemActionItem] = Field(default_factory=list)
    documents: list[MoneyProblemActionItem] = Field(default_factory=list)
    data_blockers: list[MoneyProblemActionItem] = Field(default_factory=list)
    system_checks: list[MoneyProblemActionItem] = Field(default_factory=list)


class MoneyControlPanel(BaseModel):
    confirmed_money: MoneyControlPanelCard | None = None
    provisional_sales: MoneyControlPanelCard | None = None
    probable_risks: MoneyControlPanelCard | None = None
    blocked_cash: MoneyControlPanelCard | None = None
    calculation_blockers: MoneyControlPanelCard | None = None
    growth_opportunities: MoneyControlPanelCard | None = None
    source_coverage: list[MoneySourceCoverageItem] = Field(default_factory=list)
    grouped_problems: MoneyProblemGroups = Field(default_factory=MoneyProblemGroups)
    unit_economics: MoneyUnitEconomicsRead = Field(
        default_factory=MoneyUnitEconomicsRead
    )


class MoneySummaryRead(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    meta: MoneyMeta
    trust: DataTrustInfo | None = None
    answer: BusinessAnswer
    store_answer: StoreAnswer
    revenue_sources: RevenueSources
    finance_reconciliation: FinanceReconciliationBlock
    cost_coverage: CostCoverageBlock = Field(default_factory=CostCoverageBlock)
    quality: MoneyQuality
    kpis: MoneySummaryKpis
    expenses: StoreExpenseWaterfall = Field(default_factory=StoreExpenseWaterfall)
    expense_breakdown: ExpenseBreakdownSummaryRead | None = None
    profit_cascade: ProfitCascadeRead | None = None
    money_flow: MoneyFlowBlock
    cash_and_stock: CashAndStockBlock = Field(default_factory=CashAndStockBlock)
    risk_summary: RiskSummary
    top_cards: TopCardsBlock
    next_actions: list[NextActionRead] = Field(default_factory=list)
    control_panel: MoneyControlPanel = Field(default_factory=MoneyControlPanel)
    evidence_ledger: dict[str, EvidenceLedger] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "MoneySummaryRead":
        trust = self.trust or self.meta.data_trust
        trust_state = trust.trust_state or trust.state
        financial_final = bool(trust.financial_final)
        for key, value in self.kpis.model_dump(exclude={"evidence_ledger"}).items():
            if key in self.kpis.evidence_ledger:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                self.kpis.evidence_ledger[key] = money_kpi_evidence(
                    key=key,
                    value=value,
                    account_id=self.meta.account_id,
                    date_from=self.meta.date_from,
                    date_to=self.meta.date_to,
                    trust_state=trust_state,
                    financial_final=financial_final,
                )
        if not self.evidence_ledger:
            self.evidence_ledger = {
                "summary": evidence_ledger(
                    value=self.answer.business_status,
                    value_type="status",
                    confidence=confidence_from_trust_state(
                        trust_state, final=financial_final
                    ),
                    impact_type="system_warning"
                    if not financial_final
                    else "opportunity",
                    formula_human="Money Summary combines sales, finance, costs, ads, stock and DQ signals for the selected account and period.",
                    formula_code="money_summary",
                    formula_id="money_summary",
                    label="Money Summary",
                    source_table="mart_sku_daily",
                    source_endpoint="GET /api/v1/money/summary",
                    date_from=self.meta.date_from,
                    date_to=self.meta.date_to,
                    filters={"account_id": self.meta.account_id},
                    missing_data=[] if financial_final else ["financial_final=false"],
                    recheck_rule="Refresh /money/summary after sync or data-fix changes.",
                )
            }
        if self.control_panel:
            card_evidence_keys = {
                "confirmed_money": "finance_confirmed_revenue",
                "provisional_sales": "revenue",
                "probable_risks": "net_profit_after_all_expenses",
                "blocked_cash": "stock_value",
                "calculation_blockers": "supplier_cost_confirmed_revenue_percent",
                "growth_opportunities": "revenue",
            }
            for panel_field, evidence_key in card_evidence_keys.items():
                card = getattr(self.control_panel, panel_field, None)
                if card is not None and card.evidence_ledger is None:
                    card.evidence_ledger = self.kpis.evidence_ledger.get(evidence_key)
        return self


class CardVerdict(BaseModel):
    status: str
    label: str
    short_text: str
    confidence: str


class CardExpenseBreakdown(BaseModel):
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
    commission: float = 0.0
    acquiring_fee: float = 0.0
    logistics: float = 0.0
    paid_acceptance: float = 0.0
    storage: float = 0.0
    penalties: float = 0.0
    deductions: float = 0.0
    additional_payments: float = 0.0
    direct: float = 0.0
    account_level: float = 0.0
    account_level_logistics: float = 0.0
    allocated_overhead: float = 0.0
    unallocated: float = 0.0
    unallocated_logistics: float = 0.0
    logistics_mapping_status: str = ""
    confidence: str = ""
    reason: str = ""
    status: str = ""


class CardCogsBlock(BaseModel):
    unit_cost: float = 0.0
    estimated_cogs: float = 0.0
    truth_level: str = ""
    cost_truth_label: str = ""
    supplier_confirmed: bool = False
    business_trusted: bool = False
    confidence: str = ""
    reason: str = ""


class CardProfitBlock(BaseModel):
    before_ads: float = 0.0
    after_allocated_ads: float = 0.0
    after_source_ads: float = 0.0
    after_overhead: float = 0.0
    with_allocated_overhead: float = 0.0
    after_ads: float = 0.0
    net_profit_after_all_expenses: float = 0.0
    margin_after_ads_percent: float = 0.0
    roi_after_ads_percent: float = 0.0
    roi_on_cogs_percent: float = 0.0
    stock_roi_percent: float = 0.0
    roas_percent: float = 0.0
    confidence: str


class CardMoneyBlock(BaseModel):
    revenue: float
    revenue_final: float = 0.0
    for_pay: float = 0.0
    wb_expenses: CardExpenseBreakdown
    ads: "CardAdsBlock"
    cogs: CardCogsBlock
    profit: CardProfitBlock
    wb_expenses_total: float = 0.0
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
    net_profit_after_all_expenses: float = 0.0
    expense_data_quality: str = "partial"
    stock_value: float = 0.0
    unit_economics: MoneyUnitEconomicsRead = Field(
        default_factory=MoneyUnitEconomicsRead
    )


class ProfitVariants(BaseModel):
    before_ads: float = 0.0
    after_allocated_ads: float = 0.0
    after_source_ads: float = 0.0
    after_overhead: float = 0.0
    with_allocated_overhead: float = 0.0


class FinalityBlock(BaseModel):
    profit_final: bool = False
    restock_final: bool = False
    price_final: bool = False
    reasons: list[str] = Field(default_factory=list)


class CardOperationsBlock(BaseModel):
    orders_count: int = 0
    cancelled_orders_count: int = 0
    cancel_rate_percent: float = 0.0
    sales_count: int = 0
    returns_count: int = 0
    return_rate_percent: float = 0.0
    net_units: int = 0
    issue: str = ""


class CardFunnelBlock(BaseModel):
    open_count: int = 0
    cart_count: int = 0
    order_count: int = 0
    buyout_count: int = 0
    cart_conversion_percent: float = 0.0
    order_conversion_percent: float = 0.0
    buyout_rate_percent: float = 0.0
    issue: str = ""


class CardStockBlock(BaseModel):
    quantity: float = 0.0
    quantity_full: float = 0.0
    stock_value: float = 0.0
    stock_value_confidence: str = ""
    stock_value_reason: str = ""
    days_of_stock: float = 0.0
    sales_velocity_daily: float = 0.0
    overstock_value: float = 0.0
    stock_status: str = ""
    in_transit_qty: float = 0.0
    in_transit_value: float = 0.0


class CardPriceBlock(BaseModel):
    current_price: float = 0.0
    current_discounted_price: float = 0.0
    discount: int = 0
    break_even_price: float = 0.0
    break_even_price_final: float = 0.0
    break_even_price_estimated: float = 0.0
    target_margin_price: float = 0.0
    target_margin_price_final: float = 0.0
    target_margin_price_estimated: float = 0.0
    safe_price_gap: float = 0.0
    safe_price_gap_unit: str = "RUB"
    safe_price_gap_kind: str = "currency_amount"
    safe_price_gap_final: float = 0.0
    safe_price_gap_estimated: float = 0.0
    estimated_margin_percent: float | None = None
    status: str
    confidence: str = ""
    price_source: str = ""
    not_computable_reason: str = ""


class CardAdsBlock(BaseModel):
    spend: float = 0.0
    source_spend: float = 0.0
    raw_allocated_spend: float = 0.0
    capped_allocated_spend: float = 0.0
    allocated_spend: float = 0.0
    unallocated_spend: float = 0.0
    overallocated_spend: float = 0.0
    drr_percent: float = 0.0
    drr_percent_source: float = 0.0
    stats_rows_count: int = 0
    views: int = 0
    clicks: int = 0
    orders: int = 0
    atbs: int = 0
    status: str
    allocation_status: str = ""
    profit_allocation_status: str = ""
    allocation_method: str = ""
    allocation_confidence: str = ""
    final_profit_allowed: bool = True


class ArticleSummaryPreview(BaseModel):
    nm_id: int | None
    title: str | None
    revenue: float = 0.0
    stock_qty: float = 0.0
    stock_value: float = 0.0
    ads_source_spend: float = 0.0
    variant_count: int = 0


class MoneyCardRow(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    business_verdict: CardVerdict
    money: CardMoneyBlock
    operations: CardOperationsBlock
    stock: CardStockBlock
    price: CardPriceBlock
    ads: CardAdsBlock
    profit_variants: ProfitVariants = Field(default_factory=ProfitVariants)
    finality: FinalityBlock = Field(default_factory=FinalityBlock)
    article_summary_preview: ArticleSummaryPreview | None = None
    data_trust: DataTrustInfo
    next_action: NextActionRead
    priority_score: float


class MoneyCardListSummary(BaseModel):
    profitable_count: int = 0
    loss_count: int = 0
    data_blocked_count: int = 0
    stock_risk_count: int = 0
    overstock_count: int = 0
    ad_risk_count: int = 0
    price_risk_count: int = 0


class MoneyCardPage(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    total: int
    limit: int
    offset: int
    summary: MoneyCardListSummary
    items: list[MoneyCardRow]


class MoneyIdentity(BaseModel):
    sku_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None


class MoneyCardAnswer(BaseModel):
    status: str
    title: str
    short_text: str
    decision: str
    next_step: str = ""
    main_next_step: str = ""
    main_reason: str = ""


class MoneyArticleIdentity(BaseModel):
    nm_id: int
    title: str | None
    brand: str | None
    subject_name: str | None


class MoneyArticleRow(BaseModel):
    nm_id: int
    title: str | None
    brand: str | None
    subject_name: str | None
    identity: MoneyArticleIdentity | None = None
    trust: ArticleTrustBlock | None = None
    variant_count: int = 0
    business_verdict: CardVerdict
    money_answer: MoneyCardAnswer
    money: CardMoneyBlock
    stock: CardStockBlock
    ads: CardAdsBlock
    profit_variants: ProfitVariants = Field(default_factory=ProfitVariants)
    finality: FinalityBlock = Field(default_factory=FinalityBlock)
    financial_final: bool = False
    data_trust: DataTrustInfo
    next_action: NextActionRead
    priority_score: float


class MoneyArticleListSummary(BaseModel):
    profitable_count: int = 0
    loss_count: int = 0
    economic_profitable_count: int = 0
    economic_loss_count: int = 0
    final_profitable_count: int = 0
    final_loss_count: int = 0
    data_blocked_count: int = 0
    stock_risk_count: int = 0
    overstock_count: int = 0
    provisional_count: int = 0
    cost_coverage: CostCoverageBlock = Field(default_factory=CostCoverageBlock)


class MoneyArticlePage(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    total: int
    limit: int
    offset: int
    summary: MoneyArticleListSummary
    items: list[MoneyArticleRow]


class VariantBreakdownRow(BaseModel):
    sku_id: int | None
    barcode: str | None
    vendor_code: str | None
    title: str | None
    revenue: float = 0.0
    stock_qty: float = 0.0
    stock_value: float = 0.0
    allocated_ads_spend: float = 0.0
    source_ads_spend: float = 0.0
    net_profit_after_source_ads: float = 0.0
    next_action: NextActionRead


class ArticleSummaryBlock(BaseModel):
    nm_id: int
    title: str | None
    revenue: float = 0.0
    profit_before_ads: float = 0.0
    ads_source_spend: float = 0.0
    profit_after_ads: float = 0.0
    stock_qty: float = 0.0
    stock_value: float = 0.0
    cancel_rate_percent: float = 0.0
    return_rate_percent: float = 0.0
    decision: str = "watch"


class ArticleExpenseBreakdown(BaseModel):
    direct_expenses: ExpenseComponentBreakdown = Field(
        default_factory=ExpenseComponentBreakdown
    )
    allocated_overhead: float = 0.0
    account_level_total: float = 0.0
    account_level_logistics: float = 0.0
    unallocated_total: float = 0.0
    unallocated_logistics: float = 0.0
    total_wb_expenses: float = 0.0
    unallocated_warning: bool = False
    not_linked_reason: str = ""
    message: str = ""


class CardReconciliationBlock(BaseModel):
    mart_matches_article: bool = True
    mart_matches_finance: bool = False
    finance_matches_operational: bool = False
    revenue_matches_mart: bool
    mart_revenue_total: float
    article_revenue_total: float
    finance_report_revenue_total: float
    difference_amount: float
    difference_ratio_percent: float = 0.0
    status: str
    mismatch_reason: str = ""
    root_cause_candidates: list[str] = Field(default_factory=list)
    next_debug_endpoint: str = ""
    business_effect: str = ""


class CardProblem(BaseModel):
    code: str
    severity: str
    title: str
    business_impact: str
    fix_hint: str


class ArticleTrustBlock(BaseModel):
    state: str
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
    confidence: str = ""
    blocked_reasons: list[str] = Field(default_factory=list)
    cost_truth_level: str = ""
    supplier_confirmed: bool = False
    finance_status: str = ""
    human_message: str = ""
    reason: str = ""


class ArticleKpisBlock(BaseModel):
    revenue: float = 0.0
    revenue_final: float = 0.0
    for_pay: float = 0.0
    profit_before_ads: float = 0.0
    profit_after_allocated_ads: float = 0.0
    profit_after_source_ads: float = 0.0
    profit_after_overhead: float = 0.0
    wb_expenses_total: float = 0.0
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
    net_profit_after_all_expenses: float = 0.0
    expense_data_quality: str = "partial"
    stock_qty: float = 0.0
    stock_value: float = 0.0
    ads_source_spend: float = 0.0
    ads_allocated_spend: float = 0.0
    cancel_rate_percent: float = 0.0
    return_rate_percent: float = 0.0


class ArticleWaterfallBlock(BaseModel):
    revenue: float = 0.0
    cogs: float = 0.0
    direct_wb_expenses: float = 0.0
    ads_source_spend: float = 0.0
    allocated_overhead: float = 0.0
    profit_before_ads: float = 0.0
    profit_after_source_ads: float = 0.0
    profit_after_overhead: float = 0.0


class ArticlePurchasePlanBlock(BaseModel):
    decision: str = "WATCH"
    main_reason: str = ""
    next_step: str = ""
    recommended_qty: int = 0
    required_cash: float = 0.0
    money_effect: dict = Field(default_factory=dict)
    confidence: str = ""
    decision_confidence: str = ""
    financial_final: bool = False
    available_stock: float = 0.0
    in_transit_qty: float = 0.0
    days_of_stock: float | None = None
    lead_time_days: int = 0
    safety_days: int = 0
    variant_count: int = 0
    size_breakdown: list[dict] = Field(default_factory=list)


class MoneyCardDetailRead(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    meta: MoneyMeta
    identity: MoneyIdentity
    answer: MoneyCardAnswer
    cost_coverage: CostCoverageBlock = Field(default_factory=CostCoverageBlock)
    money: CardMoneyBlock
    expense_breakdown: ArticleExpenseBreakdown | None = None
    operations: CardOperationsBlock
    funnel: CardFunnelBlock
    stock: CardStockBlock
    price: CardPriceBlock
    reconciliation: CardReconciliationBlock
    problems: list[CardProblem] = Field(default_factory=list)
    next_actions: list[NextActionRead] = Field(default_factory=list)
    article_summary: ArticleSummaryBlock | None = None
    variant_breakdown: list[VariantBreakdownRow] = Field(default_factory=list)
    profit_variants: ProfitVariants = Field(default_factory=ProfitVariants)
    finality: FinalityBlock = Field(default_factory=FinalityBlock)


class MoneyArticleDetailRead(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    meta: MoneyMeta
    nm_id: int
    identity: MoneyArticleIdentity
    trust: ArticleTrustBlock
    money_answer: MoneyCardAnswer
    kpis: ArticleKpisBlock = Field(default_factory=ArticleKpisBlock)
    waterfall: ArticleWaterfallBlock = Field(default_factory=ArticleWaterfallBlock)
    cost_coverage: CostCoverageBlock = Field(default_factory=CostCoverageBlock)
    money: CardMoneyBlock
    expense_breakdown: ArticleExpenseBreakdown | None = None
    ads: CardAdsBlock
    stock: CardStockBlock
    operations: CardOperationsBlock
    funnel: CardFunnelBlock
    price_safety: CardPriceBlock
    purchase_plan: ArticlePurchasePlanBlock | None = None
    reconciliation: CardReconciliationBlock
    actions: list[NextActionRead] = Field(default_factory=list)
    issues: list[CardProblem] = Field(default_factory=list)
    sku_breakdown: list[VariantBreakdownRow] = Field(default_factory=list)
    article_summary: ArticleSummaryBlock | None = None
    profit_variants: ProfitVariants = Field(default_factory=ProfitVariants)
    finality: FinalityBlock = Field(default_factory=FinalityBlock)
    answer: MoneyCardAnswer
    price: CardPriceBlock
    next_actions: list[NextActionRead] = Field(default_factory=list)
    problems: list[CardProblem] = Field(default_factory=list)
    variant_breakdown: list[VariantBreakdownRow] = Field(default_factory=list)


class DataBlockerRead(BaseModel):
    code: str
    priority: str
    title: str
    affected_sku_count: int = 0
    affected_revenue: float = 0.0
    affected_amount: float = 0.0
    current_value: float = 0.0
    required_value: float = 0.0
    unit: str = ""
    business_impact: str
    how_to_fix: list[str] = Field(default_factory=list)
    simple_reason: str = ""
    first_action: str = ""
    success_check: list[str] = Field(default_factory=list)
    wait_or_fix_hint: str = ""
    related_endpoints: list[str] = Field(default_factory=list)
    exact_next_endpoint: str = ""
    next_screen_path: str = ""
    next_screen_label: str = ""
    owner_type: str = "admin"
    fixability: str = "admin_only"
    issue_nature: str = "system_check"
    can_user_fix_inside_platform: bool = False
    is_manual_edit_allowed: bool = False
    primary_action_code: str = ""
    primary_action_label: str = ""
    target_href: str = ""
    disabled_reason: str = ""
    recheck_mode: str = "manual_admin"
    seller_explanation: str = ""
    admin_explanation: str = ""
    calculation_title: str = ""
    calculation_formula: str = ""
    calculation_inputs: list[dict[str, object]] = Field(default_factory=list)
    source_endpoints: list[str] = Field(default_factory=list)
    evidence_ledger: EvidenceLedger | None = None
    money_trust: MoneyTrustInfo | None = None
    resolver: ProblemResolver | None = None

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "DataBlockerRead":
        payload = {"nmId": None}
        contract = issue_fixability_contract(self.code, payload)
        self.owner_type = str(contract["owner_type"])
        self.fixability = str(contract["fixability"])
        self.issue_nature = str(contract["issue_nature"])
        self.can_user_fix_inside_platform = bool(
            contract["can_user_fix_inside_platform"]
        )
        self.is_manual_edit_allowed = bool(contract["is_manual_edit_allowed"])
        self.primary_action_code = str(contract["primary_action_code"])
        self.primary_action_label = str(contract["primary_action_label"])
        self.target_href = str(contract["target_href"])
        self.disabled_reason = str(contract["disabled_reason"] or "")
        self.recheck_mode = str(contract["recheck_mode"])
        self.seller_explanation = str(contract["seller_explanation"])
        self.admin_explanation = str(contract["admin_explanation"])
        if self.target_href:
            self.next_screen_path = self.target_href
            self.next_screen_label = self.primary_action_label or self.next_screen_label
        if self.resolver is None:
            self.resolver = build_problem_resolver(
                self.code,
                guide={
                    "simple_reason": self.simple_reason,
                    "first_action": self.first_action,
                    "success_check": self.success_check,
                    "wait_or_fix_hint": self.wait_or_fix_hint,
                },
            )
        trust = classify_money_trust(
            value=self.affected_amount
            or self.affected_revenue
            or self.affected_sku_count,
            value_type="money"
            if (self.affected_amount or self.affected_revenue)
            else "count",
            confidence="blocked"
            if self.issue_nature == "data_blocker"
            else "provisional",
            impact_type="data_blocker"
            if self.issue_nature == "data_blocker"
            else "informational",
            source_module="data_quality",
            source_table="data_quality_issues",
            source_endpoint=self.exact_next_endpoint
            or (
                self.related_endpoints[0]
                if self.related_endpoints
                else "GET /api/v1/money/data-blockers"
            ),
            action_type=self.code,
            affected_amount=self.affected_amount,
            affected_revenue=self.affected_revenue,
        )
        if self.evidence_ledger is None:
            self.evidence_ledger = issue_evidence(
                code=self.code,
                title=self.title,
                value=self.affected_amount
                or self.affected_revenue
                or self.affected_sku_count,
                source_table="data_quality_issues",
                source_endpoint=self.exact_next_endpoint
                or (
                    self.related_endpoints[0]
                    if self.related_endpoints
                    else "GET /api/v1/money/data-blockers"
                ),
                row_count=self.affected_sku_count,
                severity=self.priority,
                next_screen_path=self.next_screen_path,
                next_screen_label=self.next_screen_label,
                sample_rows=[dict(item) for item in self.calculation_inputs[:3]],
            )
            if self.calculation_formula:
                self.evidence_ledger.formula_human = self.calculation_formula
        if self.calculation_title:
            self.evidence_ledger.formula_id = self.calculation_title
        if self.money_trust is None:
            self.money_trust = trust
        self.evidence_ledger.money_trust = self.money_trust
        return self


class DataBlockersRead(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    meta: MoneyMeta
    overall_state: str
    overall_message: str = ""
    can_generate_business_actions: bool
    blockers_count: int = 0
    warnings_count: int = 0
    blockers: list[DataBlockerRead] = Field(default_factory=list)
    warnings: list[DataBlockerRead] = Field(default_factory=list)
    open_issue_summary: dict[str, int] = Field(default_factory=dict)
    data_quality_summary: DataQualitySummaryBlock = Field(
        default_factory=DataQualitySummaryBlock
    )
    evidence_ledger: dict[str, EvidenceLedger] = Field(default_factory=dict)

    @model_validator(mode="after")
    def fill_evidence_ledger(self) -> "DataBlockersRead":
        for item in [*self.blockers, *self.warnings]:
            if item.evidence_ledger and item.evidence_ledger.input_facts:
                fact = item.evidence_ledger.input_facts[0]
                if fact.date_range is not None:
                    fact.date_range.date_from = self.meta.date_from
                    fact.date_range.date_to = self.meta.date_to
                fact.filters = {**fact.filters, "account_id": self.meta.account_id}
        if not self.evidence_ledger:
            self.evidence_ledger = {
                "overall_state": evidence_ledger(
                    value=self.overall_state,
                    value_type="status",
                    confidence="blocked"
                    if self.overall_state == "data_blocked"
                    else "provisional",
                    impact_type="data_blocker"
                    if self.blockers_count
                    else "system_warning",
                    formula_human="Aggregates open data blockers and warnings for the selected period.",
                    formula_code="money.data_blockers.overall_state",
                    formula_id="money_data_blockers",
                    label="Data blockers",
                    source_table="data_quality_issues",
                    source_endpoint="GET /api/v1/money/data-blockers",
                    date_from=self.meta.date_from,
                    date_to=self.meta.date_to,
                    filters={"account_id": self.meta.account_id},
                    row_count=self.blockers_count + self.warnings_count,
                    sample_rows=[
                        {
                            "blockers_count": self.blockers_count,
                            "warnings_count": self.warnings_count,
                        }
                    ],
                    next_fix_action={
                        "label": "Открыть Data Fix",
                        "screen_path": "/data-fix",
                        "source_endpoint": "GET /api/v1/money/data-blockers",
                        "action_type": "data_fix",
                    },
                    recheck_rule="Resolve data issues, then refresh /money/data-blockers.",
                )
            }
        return self


class ExpenseReportRowRead(BaseModel):
    report_id: int | None = None
    rrd_id: int | None = None
    date: date
    nm_id: int | None = None
    sku_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    category: str
    category_label: str = ""
    amount: float = 0.0
    source: str = ""
    source_field: str | None = None
    seller_oper_name: str | None = None
    bonus_type_name: str | None = None
    logistics_type: str | None = None
    srid: str | None = None
    order_id: int | None = None
    is_allocated_to_sku: bool = False


class FilterOption(BaseModel):
    key: str
    label: str


class ActionGroups(BaseModel):
    save_money: list[NextActionRead] = Field(default_factory=list)
    release_cash: list[NextActionRead] = Field(default_factory=list)
    protect_revenue: list[NextActionRead] = Field(default_factory=list)
    finance_reconcile: list[NextActionRead] = Field(default_factory=list)
    global_blockers: list[NextActionRead] = Field(default_factory=list)
    money_saving: list[NextActionRead] = Field(default_factory=list)
    growth: list[NextActionRead] = Field(default_factory=list)
    data_fix: list[NextActionRead] = Field(default_factory=list)
    watch: list[NextActionRead] = Field(default_factory=list)


class MoneyFiltersRead(BaseModel):
    date_presets: list[FilterOption] = Field(default_factory=list)
    card_statuses: list[FilterOption] = Field(default_factory=list)
    trust_states: list[FilterOption] = Field(default_factory=list)
    action_types: list[FilterOption] = Field(default_factory=list)
    brands: list[FilterOption] = Field(default_factory=list)
    subjects: list[FilterOption] = Field(default_factory=list)
    sort_options: list[FilterOption] = Field(default_factory=list)
    presets: list[FilterOption] = Field(default_factory=list)


class TodayActionsPage(BaseModel):
    computed_at: datetime | None = None
    cache_status: str = "miss"
    data_version_hash: str | None = None
    total: int
    limit: int
    offset: int
    summary: dict[str, int]
    groups: ActionGroups
    items: list[NextActionRead]
    owner_focus_actions: list[NextActionRead] = Field(default_factory=list)
