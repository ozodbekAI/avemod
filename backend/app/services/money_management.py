from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.core.enums_meta import get_enum_mapping
from app.core.cache import stable_hash, table_signature
from app.core.config import get_settings
from app.core.expense_taxonomy import (
    AD_SPEND_SOURCE_FINANCE,
    AD_SPEND_SOURCE_NONE,
    AD_SPEND_SOURCE_OPERATIONAL,
    EXPENSE_DATA_QUALITY_UNCLASSIFIED_PRESENT,
    EXPENSE_CATEGORY_ACCEPTANCE,
    EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
    EXPENSE_CATEGORY_DEDUCTION,
    EXPENSE_CATEGORY_LOYALTY,
    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
    EXPENSE_CATEGORY_PAYMENT_PROCESSING,
    EXPENSE_CATEGORY_PENALTY,
    EXPENSE_CATEGORY_PVZ_REWARD,
    EXPENSE_CATEGORY_SELLER_COGS,
    EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE,
    EXPENSE_CATEGORY_STORAGE,
    EXPENSE_CATEGORY_UNCLASSIFIED,
    EXPENSE_CATEGORY_WB_COMMISSION,
    EXPENSE_CATEGORY_WB_LOGISTICS,
    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
    EXPENSE_SIGN_INCOME,
    additional_income as expense_additional_income,
    expense_data_quality as compute_expense_data_quality,
    extra_ad_spend_not_in_wb_expenses,
    merge_expense_data_quality,
    normalized_wb_expenses_total,
    revenue_final as compute_revenue_final,
    total_seller_costs,
)
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.data_quality import DataQualityIssue
from app.models.finance import (
    WBBalanceSnapshot,
    WBRealizationReport,
    WBRealizationReportRow,
)
from app.models.marts import MartAccountExpenseDaily, MartExpenseDaily, MartSKUDaily
from app.models.product_cards import CoreSKU
from app.models.sales import WBSale
from app.services.marts import MartService
from app.schemas.data_quality import (
    DataQualitySummaryBlock,
    issue_bucket_meta,
    issue_display_message,
    issue_resolution_guide,
)
from app.schemas.money_management import (
    AccountLevelExpenseBreakdown,
    ArticleSummaryBlock,
    ArticleExpenseBreakdown,
    ArticleKpisBlock,
    ArticlePurchasePlanBlock,
    ArticleSummaryPreview,
    ArticleTrustBlock,
    ArticleWaterfallBlock,
    BusinessAnswer,
    CardAdsBlock,
    CardCogsBlock,
    CardExpenseBreakdown,
    CardFunnelBlock,
    CardPriceBlock,
    CardProblem,
    CardProfitBlock,
    CardReconciliationBlock,
    CardStockBlock,
    CardVerdict,
    CashAndStockBlock,
    DataBlockerRead,
    DataBlockersRead,
    CostCoverageBlock,
    DataTrustInfo,
    ExpenseBreakdownItemRead,
    ExpenseBreakdownSummaryRead,
    ExpenseComponentBreakdown,
    ExpenseReportRowRead,
    FilterOption,
    FinanceReconciliationBlock,
    FinanceReconciliationClassifiedDifference,
    FinalityBlock,
    MoneyCardAnswer,
    MoneyCardDetailRead,
    MoneyCardListSummary,
    MoneyCardPage,
    MoneyCardRow,
    MoneyControlPanel,
    MoneyControlPanelCard,
    MoneyExpenseLogisticsRead,
    MoneyArticleIdentity,
    MoneyArticleDetailRead,
    MoneyArticleListSummary,
    MoneyArticlePage,
    MoneyArticleRow,
    MoneyFiltersRead,
    MoneyFlowBlock,
    MoneyFlowItem,
    MoneyIdentity,
    MoneyMeta,
    MoneyProblemActionItem,
    MoneyProblemGroups,
    MoneyQuality,
    MoneySourceCoverageItem,
    ProfitCascadeBodyRead,
    ProfitCascadeChildRead,
    ProfitCascadeGroupRead,
    ProfitCascadeRead,
    ProfitCascadeRevenueRead,
    ProfitCascadeTotalsRead,
    ProfitCascadeValidationRead,
    ProfitVariants,
    RevenueSources,
    MoneyUnitEconomicsRead,
    MoneySummaryKpis,
    MoneySummaryRead,
    NextActionRead,
    RiskItem,
    RiskSummary,
    StoreAnswer,
    StoreExpenseWaterfall,
    TodayActionsPage,
    TopCardPreview,
    TopCardsBlock,
    VariantBreakdownRow,
    CardMoneyBlock,
    CardOperationsBlock,
)
from app.services.control_tower import ControlTowerService
from app.services.core_sku import CoreSKUService
from app.services.dashboard import DashboardService
from app.services.trust import (
    TRUST_STATE_BLOCKED,
    TRUST_STATE_DATA_BLOCKED,
    TRUST_STATE_FINANCIAL_FINAL,
    TRUST_STATE_OPERATIONAL_PROVISIONAL,
    TRUST_STATE_TEST_ONLY,
    TRUST_STATE_TRUSTED,
    TRUST_STATE_UNKNOWN,
    build_cost_coverage_decision,
    cost_policy_owner_approves_final,
    final_cost_is_accepted,
)


FIX_ACTION_TYPES = {
    "FIX_COST_TRUST",
    "MAP_UNMATCHED_SKU",
    "FIX_STOCK_SYNC",
    "RECONCILE_FINANCE",
    "FIX_AD_ALLOCATION",
    "FIX_PRICE_MAPPING",
}

OPEN_ACTION_STATUSES = {"new", "in_progress", "snoozed"}


@dataclass
class MoneyRuntimeState:
    health: Any
    profit_rows: list[Any]
    control_rows: list[Any]
    price_rows: dict[int, Any]
    purchase_rows: dict[int, Any]
    settings: dict[str, Any]
    trust_decision: Any
    action_reads: list[Any]
    actions_by_sku: dict[int, list[Any]]
    ads_source_total: Decimal
    ads_source_by_nm: dict[int, Decimal]
    account_expense_rows: list[Any]
    account_level_expense_total: Decimal
    latest_balance: Any | None
    period_end_balance: Any | None
    finance_confirmed_revenue_total: Decimal
    finance_closed_mart_revenue_total: Decimal
    finance_coverage_date_to: date | None
    computed_at: datetime
    cache_status: str = "miss"
    data_version_hash: str = ""
    account_level_logistics_total: Decimal = Decimal("0")


@dataclass
class ReconciliationEntry:
    key: str
    srid: str | None
    nm_id: int | None
    event_date: date | None
    report_date: date | None
    signed_amount: Decimal
    is_return: bool


@dataclass
class FinanceReconciliationSourceRow:
    rrd_id: int | None
    srid: str | None
    nm_id: int | None
    rr_date: date | None
    sale_dt: datetime | None
    retail_amount: Decimal | None
    for_pay: Decimal | None
    doc_type_name: str | None
    is_reconcilable: bool | None
    is_return_operation: bool | None


class MoneyManagementService:
    SUMMARY_FORMULA_VERSION = "source_ads_profit_v2"
    RUNTIME_CACHE_TTL_SECONDS = 600
    WARM_RUNTIME_CACHE_TTL_SECONDS = 120
    WARM_SUMMARY_CACHE_TTL_SECONDS = 120
    EXPENSE_REPORT_ROWS_CACHE_TTL_SECONDS = (
        get_settings().heavy_endpoint_cache_ttl_seconds
    )
    HIDDEN_USER_PROBLEM_CODES = {"finance_reconciliation_mismatch"}
    _shared_runtime_cache: dict[
        tuple[int, date, date, str], tuple[datetime, MoneyRuntimeState]
    ] = {}
    _shared_runtime_window_cache: dict[
        tuple[int, date, date], tuple[datetime, MoneyRuntimeState]
    ] = {}
    _shared_runtime_inflight: dict[
        tuple[int, tuple[int, date, date]], asyncio.Task[MoneyRuntimeState]
    ] = {}
    _shared_summary_cache: dict[
        tuple[int, date, date, str], tuple[datetime, MoneySummaryRead]
    ] = {}
    _shared_summary_window_cache: dict[
        tuple[int, date, date], tuple[datetime, MoneySummaryRead]
    ] = {}
    _shared_expense_report_rows_cache: dict[
        tuple[object, ...], tuple[datetime, Page[ExpenseReportRowRead]]
    ] = {}
    EXPENSE_BREAKDOWN_CATEGORY_ORDER = (
        EXPENSE_CATEGORY_WB_LOGISTICS,
        EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
        EXPENSE_CATEGORY_STORAGE,
        EXPENSE_CATEGORY_ACCEPTANCE,
        EXPENSE_CATEGORY_WB_COMMISSION,
        EXPENSE_CATEGORY_PAYMENT_PROCESSING,
        EXPENSE_CATEGORY_PVZ_REWARD,
        EXPENSE_CATEGORY_PENALTY,
        EXPENSE_CATEGORY_DEDUCTION,
        EXPENSE_CATEGORY_MARKETING_DEDUCTION,
        EXPENSE_CATEGORY_LOYALTY,
        EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
        EXPENSE_CATEGORY_UNCLASSIFIED,
        EXPENSE_CATEGORY_SELLER_COGS,
        EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE,
        "ads_operational",
    )
    EXPENSE_CATEGORY_PRIMARY_SOURCE = {
        EXPENSE_CATEGORY_WB_COMMISSION: "finance_report",
        EXPENSE_CATEGORY_PAYMENT_PROCESSING: "finance_report",
        EXPENSE_CATEGORY_PVZ_REWARD: "finance_report",
        EXPENSE_CATEGORY_WB_LOGISTICS: "finance_report",
        EXPENSE_CATEGORY_WB_LOGISTICS_REBILL: "finance_report",
        EXPENSE_CATEGORY_STORAGE: "finance_report",
        EXPENSE_CATEGORY_ACCEPTANCE: "finance_report",
        EXPENSE_CATEGORY_PENALTY: "finance_report",
        EXPENSE_CATEGORY_DEDUCTION: "finance_report",
        EXPENSE_CATEGORY_MARKETING_DEDUCTION: "finance_report",
        EXPENSE_CATEGORY_LOYALTY: "finance_report",
        EXPENSE_CATEGORY_ADDITIONAL_PAYMENT: "finance_report",
        EXPENSE_CATEGORY_UNCLASSIFIED: "finance_report",
        EXPENSE_CATEGORY_SELLER_COGS: "manual_cost",
        EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE: "manual_cost",
        "ads_operational": "ads_api",
    }
    PROFIT_CASCADE_GROUP_LABELS = {
        "seller_cogs": "Себестоимость",
        "seller_other_expenses": "Прочие расходы продавца",
        "wb_direct_expenses": "Прямые расходы WB",
        "ad_expenses": "Реклама / продвижение",
        "additional_income": "Доплаты / компенсации",
    }
    PROFIT_CASCADE_CHILD_LABELS = {
        "revenue": "Выручка",
        "seller_cogs": "Себестоимость",
        "seller_other_expense": "Прочие расходы продавца",
        EXPENSE_CATEGORY_WB_LOGISTICS: "Логистика WB",
        EXPENSE_CATEGORY_WB_LOGISTICS_REBILL: "Перевыставленная логистика WB",
        EXPENSE_CATEGORY_PAYMENT_PROCESSING: "Эквайринг",
        EXPENSE_CATEGORY_PVZ_REWARD: "ПВЗ",
        EXPENSE_CATEGORY_STORAGE: "Хранение",
        EXPENSE_CATEGORY_DEDUCTION: "Удержания",
        EXPENSE_CATEGORY_PENALTY: "Штрафы",
        EXPENSE_CATEGORY_ACCEPTANCE: "Приемка",
        EXPENSE_CATEGORY_WB_COMMISSION: "Комиссия WB",
        "other_wb_expenses": "Прочие WB расходы",
        "unclassified_wb_expenses": "Прочие WB расходы",
        "ad_spend_final": "Реклама / продвижение",
        "additional_payment": "Доплаты / компенсации",
        "other_or_rounding_delta": "Прочие / округление",
    }
    PROFIT_CASCADE_SOURCE_OF_TRUTH_MAP = {
        "finance": "finance_report",
        "finance_report": "finance_report",
        "mixed": "mixed",
        "mart": "operational",
        "operational": "operational",
    }
    BLOCKED_REASON_LABELS: dict[str, str] = {
        "supplier_cost_coverage_below_threshold": "нехватка подтвержденной себестоимости",
        "unmatched_sku_detected": "есть несопоставленные SKU",
        "latest_stocks_not_completed": "последняя синхронизация остатков не завершена",
        "open_blocking_dq_issues": "есть блокирующие проблемы качества данных",
        "failed_sync_domains": "есть ошибки в загрузке данных",
        "article_audit_mismatch": "есть расхождение в аудите артикула",
        "finance_not_confirmed": "финансовые данные не подтверждены",
        "missing_manual_cost": "отсутствует ручная себестоимость",
        "supplier_cost_not_confirmed": "себестоимость поставщика не подтверждена",
        "price_not_mapped": "цена не сопоставлена",
    }

    def __init__(self) -> None:
        self.dashboard = DashboardService()
        self.control = ControlTowerService()
        self.core_sku = CoreSKUService()
        self._runtime_cache = type(self)._shared_runtime_cache
        self._runtime_window_cache = type(self)._shared_runtime_window_cache
        self._runtime_inflight = type(self)._shared_runtime_inflight
        self._summary_cache = type(self)._shared_summary_cache
        self._summary_window_cache = type(self)._shared_summary_window_cache
        self._expense_report_rows_cache = type(self)._shared_expense_report_rows_cache
        self._local_runtime_cache: dict[
            tuple[int, date, date, str], tuple[datetime, MoneyRuntimeState]
        ] = {}
        self._local_runtime_window_cache: dict[
            tuple[int, date, date], tuple[datetime, MoneyRuntimeState]
        ] = {}
        self._local_summary_cache: dict[
            tuple[int, date, date, str], tuple[datetime, MoneySummaryRead]
        ] = {}
        self._local_summary_window_cache: dict[
            tuple[int, date, date], tuple[datetime, MoneySummaryRead]
        ] = {}

    @classmethod
    def _is_hidden_user_problem_code(cls, code: str | None) -> bool:
        return str(code or "").strip().lower() in cls.HIDDEN_USER_PROBLEM_CODES

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value or 0))

    @staticmethod
    def _float(value: Decimal | float | int | None) -> float | None:
        if value is None:
            return None
        return float(value)

    @staticmethod
    def _float0(value: Decimal | float | int | None) -> float:
        return float(value or 0)

    @staticmethod
    def _int0(value: Decimal | float | int | None) -> int:
        return int(value or 0)

    @staticmethod
    def _text(value: str | None, fallback: str = "") -> str:
        return value or fallback

    @staticmethod
    def _balance_amount(balance: Any | None) -> float:
        return float(getattr(balance, "current", None) or 0.0)

    @staticmethod
    def _available_for_withdraw_amount(balance: Any | None) -> float:
        if balance is None:
            return 0.0
        explicit = getattr(balance, "for_withdraw", None)
        if explicit is not None:
            return float(explicit or 0.0)
        return float(getattr(balance, "current", None) or 0.0)

    @staticmethod
    def _percent(
        part: Decimal | int | float, whole: Decimal | int | float
    ) -> float | None:
        whole_decimal = Decimal(str(whole or 0))
        if whole_decimal <= 0:
            return None
        return float((Decimal(str(part or 0)) / whole_decimal) * Decimal("100"))

    def _percent0(
        self, part: Decimal | int | float, whole: Decimal | int | float
    ) -> float:
        return self._percent(part, whole) or 0.0

    @staticmethod
    def _runtime_cache_key(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        data_version_hash: str | None = None,
    ) -> tuple[int, date, date, str]:
        return (account_id, date_from, date_to, data_version_hash or "")

    @staticmethod
    def _runtime_window_key(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> tuple[int, date, date]:
        return (account_id, date_from, date_to)

    @staticmethod
    def _cache_is_fresh(cached_at: datetime, *, ttl_seconds: int) -> bool:
        return (utcnow() - cached_at) <= timedelta(seconds=ttl_seconds)

    def _runtime_cache_store(
        self,
        session: AsyncSession | None,
    ) -> dict[tuple[int, date, date, str], tuple[datetime, MoneyRuntimeState]]:
        return self._local_runtime_cache if session is None else self._runtime_cache

    def _runtime_window_cache_store(
        self,
        session: AsyncSession | None,
    ) -> dict[tuple[int, date, date], tuple[datetime, MoneyRuntimeState]]:
        return (
            self._local_runtime_window_cache
            if session is None
            else self._runtime_window_cache
        )

    @staticmethod
    def _runtime_inflight_key(
        window_key: tuple[int, date, date],
    ) -> tuple[int, tuple[int, date, date]]:
        return (id(asyncio.get_running_loop()), window_key)

    def _summary_cache_store(
        self,
        session: AsyncSession | None,
    ) -> dict[tuple[int, date, date, str], tuple[datetime, MoneySummaryRead]]:
        return self._local_summary_cache if session is None else self._summary_cache

    def _summary_window_cache_store(
        self,
        session: AsyncSession | None,
    ) -> dict[tuple[int, date, date], tuple[datetime, MoneySummaryRead]]:
        return (
            self._local_summary_window_cache
            if session is None
            else self._summary_window_cache
        )

    @staticmethod
    def _with_page_cache_meta(
        page: Page[Any],
        *,
        computed_at: datetime,
        cache_status: str,
        data_version_hash: str,
    ) -> Page[Any]:
        return page.model_copy(
            deep=True,
            update={
                "computed_at": computed_at,
                "cache_status": cache_status,
                "data_version_hash": data_version_hash,
            },
        )

    def _runtime_snapshot_hash(
        self,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        health: Any,
        profit_rows: list[Any],
        control_rows: list[Any],
        action_reads: list[Any],
        ads_source_total: Decimal,
        account_level_expense_total: Decimal,
        latest_balance: Any | None,
        period_end_balance: Any | None,
        finance_confirmed_revenue_total: Decimal,
        finance_coverage_date_to: date | None,
    ) -> str:
        payload = "|".join(
            [
                str(account_id),
                date_from.isoformat(),
                date_to.isoformat(),
                str(getattr(health, "trust_state", "")),
                str(getattr(health, "latest_stocks_status", "")),
                str(getattr(health, "open_issues_total", 0)),
                str(getattr(health, "supplier_confirmed_revenue_coverage_percent", 0)),
                str(len(profit_rows)),
                str(len(control_rows)),
                str(len(action_reads)),
                str(ads_source_total),
                str(account_level_expense_total),
                str(finance_confirmed_revenue_total),
                str(
                    finance_coverage_date_to.isoformat()
                    if finance_coverage_date_to is not None
                    else ""
                ),
                str(getattr(latest_balance, "snapshot_at", "")),
                str(getattr(period_end_balance, "snapshot_at", "")),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()

    async def _runtime_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> str:
        if session is None:
            return f"session-unavailable:{self.SUMMARY_FORMULA_VERSION}"
        mart_hash = await table_signature(
            session,
            model=MartSKUDaily,
            account_id=account_id,
            date_column=MartSKUDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        expense_hash = await table_signature(
            session,
            model=MartAccountExpenseDaily,
            account_id=account_id,
            date_column=MartAccountExpenseDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        finance_hash = await table_signature(
            session,
            model=WBRealizationReportRow,
            account_id=account_id,
            date_column=WBRealizationReportRow.rr_date,
            date_from=date_from,
            date_to=date_to,
        )
        dq_hash = await table_signature(
            session,
            model=DataQualityIssue,
            account_id=account_id,
            extra_filters=[DataQualityIssue.resolved_at.is_(None)],
        )
        balance_hash = await table_signature(
            session,
            model=WBBalanceSnapshot,
            account_id=account_id,
            date_column=WBBalanceSnapshot.snapshot_at,
            date_to=date_to,
        )
        current_balance_hash = await table_signature(
            session,
            model=WBBalanceSnapshot,
            account_id=account_id,
            date_column=WBBalanceSnapshot.snapshot_at,
        )
        payload = "|".join(
            [
                self.SUMMARY_FORMULA_VERSION,
                mart_hash,
                expense_hash,
                finance_hash,
                dq_hash,
                balance_hash,
                current_balance_hash,
            ]
        )
        return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()

    async def _expense_report_rows_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> str:
        mart_expense_hash = await table_signature(
            session,
            model=MartExpenseDaily,
            account_id=account_id,
            date_column=MartExpenseDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        core_hash = await table_signature(session, model=CoreSKU, account_id=account_id)
        return stable_hash(
            "money-expense-report-rows",
            account_id,
            date_from.isoformat(),
            date_to.isoformat(),
            mart_expense_hash,
            core_hash,
        )

    @staticmethod
    def _response_cache_fields(state: Any) -> dict[str, Any]:
        return {
            "computed_at": getattr(state, "computed_at", None),
            "cache_status": str(getattr(state, "cache_status", "miss") or "miss"),
            "data_version_hash": getattr(state, "data_version_hash", None),
        }

    @staticmethod
    def _finance_row_is_reconcilable(row: WBRealizationReportRow) -> bool:
        if row.is_reconcilable is not None:
            return bool(row.is_reconcilable)
        doc_type = (row.doc_type_name or "").strip().lower()
        return doc_type in {"продажа", "возврат", "sale", "return"}

    @staticmethod
    def _finance_row_sign(row: WBRealizationReportRow) -> int:
        doc_type = (row.doc_type_name or "").lower()
        if (
            row.is_return_operation is True
            or "возврат" in doc_type
            or "return" in doc_type
        ):
            return -1
        if (
            Decimal(str(row.retail_amount or 0)) < 0
            or Decimal(str(row.for_pay or 0)) < 0
        ):
            return -1
        return 1

    @classmethod
    def _signed_finance_amount(
        cls, row: WBRealizationReportRow, value: object
    ) -> Decimal:
        amount = cls._decimal(value)
        if amount == 0:
            return amount
        if cls._finance_row_sign(row) < 0 and amount > 0:
            return -amount
        return amount

    @staticmethod
    def _action_group(action_type: str) -> str:
        return (
            "data_fix"
            if action_type in FIX_ACTION_TYPES
            or action_type in {"DATA_FIX_REQUIRED", "RECONCILIATION_REVIEW"}
            else "business"
        )

    def _action_category(self, action_type: str) -> str:
        return self.control._action_category(action_type)

    @staticmethod
    def _action_source_endpoint(
        action_type: str, linked_entity: dict[str, Any] | None
    ) -> str:
        entity = dict(linked_entity or {})
        nm_id = entity.get("nm_id")
        sku_id = entity.get("sku_id")
        if nm_id not in (None, 0, ""):
            return f"/money/articles/{int(nm_id)}"
        if sku_id not in (None, 0, ""):
            return f"/money/cards/{int(sku_id)}"
        if action_type in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}:
            return "/money/summary"
        return "/money/data-blockers"

    @staticmethod
    def _action_affected_ids(
        linked_entity: dict[str, Any] | None,
    ) -> tuple[list[int], list[int]]:
        entity = dict(linked_entity or {})
        nm_ids = (
            [int(entity["nm_id"])] if entity.get("nm_id") not in (None, 0, "") else []
        )
        sku_ids = (
            [int(entity["sku_id"])] if entity.get("sku_id") not in (None, 0, "") else []
        )
        return nm_ids, sku_ids

    @staticmethod
    def _action_primary_amount(action: NextActionRead) -> float:
        if action.action_type == "LIQUIDATE_STOCK":
            return float(
                action.money_effect.get("affected_stock_value")
                or action.money_effect.get("expected_cash_release")
                or action.expected_effect_amount
                or 0
            )
        if action.action_type == "REORDER":
            return float(
                action.money_effect.get("expected_profit_impact")
                or action.expected_effect_amount
                or 0
            )
        if action.action_type == "PROTECT_STOCK":
            return float(
                action.money_effect.get("protected_revenue")
                or action.expected_effect_amount
                or 0
            )
        if action.action_type in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}:
            return float(
                action.money_effect.get("risk_amount")
                or action.money_effect.get("difference_amount")
                or action.expected_effect_amount
                or 0
            )
        if action.action_type in {
            "DO_NOT_REORDER",
            "AD_PAUSE_REVIEW",
            "PRICE_INCREASE_REVIEW",
        }:
            return float(
                action.money_effect.get("save_amount")
                or action.money_effect.get("expected_profit_impact")
                or action.expected_effect_amount
                or 0
            )
        return float(action.expected_effect_amount or 0)

    @staticmethod
    def _confidence_weight(confidence: str) -> float:
        return {"high": 1.0, "medium": 0.7, "low": 0.45}.get(confidence or "", 0.55)

    def _urgency_weight(self, action: NextActionRead) -> float:
        category = action.category or ""
        if category == "protect_revenue":
            return 1.5 if action.days_of_stock and action.days_of_stock <= 7 else 1.2
        if category == "release_cash":
            return (
                1.3
                if float(action.money_effect.get("affected_stock_value") or 0) >= 250000
                else 1.1
            )
        if category == "finance_reconcile":
            return 1.15
        if category == "growth":
            return (
                1.2
                if action.days_of_stock
                and action.days_of_stock <= max(action.lead_time_days, 1)
                else 1.0
            )
        if category == "save_money":
            return 1.1
        if category == "data_fix":
            return 0.55
        return 0.8

    @staticmethod
    def _trust_weight(action: NextActionRead) -> float:
        if action.financial_final:
            return 1.0
        if action.category in {"finance_reconcile", "data_fix"}:
            return 0.9
        if action.blocked_reasons:
            return 0.08
        return 0.8

    def _owner_priority_score(self, action: NextActionRead) -> float:
        base_amount = self._action_primary_amount(action)
        score = (
            base_amount
            * self._confidence_weight(action.confidence)
            * self._urgency_weight(action)
            * self._trust_weight(action)
        )
        return round(score, 2)

    def _owner_priority_label(self, action: NextActionRead, *, score: float) -> str:
        category = action.category or ""
        if (
            action.blocked_reasons
            and not action.financial_final
            and category not in {"data_fix", "finance_reconcile"}
        ):
            if score >= 500_000:
                return "high"
            if score >= 150_000:
                return "medium"
            return "low"
        if category == "data_fix":
            if score >= 1_000_000 and self._is_account_level_linked_entity(
                action.linked_entity
            ):
                return "critical"
            if score >= 250_000:
                return "high"
            if score >= 50_000:
                return "medium"
            return "low"
        if category == "finance_reconcile":
            if score >= 500_000:
                return "critical"
            if score >= 125_000:
                return "high"
            if score >= 25_000:
                return "medium"
            return "low"
        if score >= 750_000:
            return "critical"
        if score >= 150_000:
            return "high"
        if score >= 25_000:
            return "medium"
        return "low"

    def _owner_action_title(self, action: NextActionRead) -> str:
        entity = action.linked_entity or {}
        card_name = (
            self._text(entity.get("vendor_code"))
            or self._text(entity.get("title"))
            or (
                f"карточка {entity.get('nm_id')}"
                if entity.get("nm_id") not in (None, 0, "")
                else action.title
            )
        )
        if action.category == "release_cash":
            return f"Разгрузить замороженный остаток по {card_name}"
        if action.category == "finance_reconcile":
            return f"Закрыть расхождение по выручке для {card_name}"
        if action.category == "protect_revenue":
            return f"Защитить выручку по {card_name}"
        if action.category == "growth":
            return f"Ускорить рост по {card_name}"
        if action.category == "save_money":
            return f"Снизить утечку денег по {card_name}"
        if action.category == "data_fix" and self._is_account_level_linked_entity(
            entity
        ):
            return "Закрыть глобальный блокер данных"
        return action.title

    def _owner_action_enriched(self, action: NextActionRead) -> NextActionRead:
        category = action.category or self._action_category(action.action_type)
        nm_ids = list(
            dict.fromkeys(
                int(value) for value in (action.affected_nm_ids or []) if value
            )
        )
        sku_ids = list(
            dict.fromkeys(
                int(value) for value in (action.affected_sku_ids or []) if value
            )
        )
        if not nm_ids and not sku_ids:
            derived_nm_ids, derived_sku_ids = self._action_affected_ids(
                action.linked_entity
            )
            nm_ids = derived_nm_ids
            sku_ids = derived_sku_ids
        money_effect = dict(action.money_effect or {})
        primary_amount = self._action_primary_amount(action)
        if primary_amount > 0:
            money_effect.setdefault("primary_amount", primary_amount)
        if category == "release_cash":
            money_effect.setdefault("primary_label", "affected_stock_value")
        elif category == "growth":
            money_effect.setdefault("primary_label", "expected_profit_impact")
        elif category == "protect_revenue":
            money_effect.setdefault("primary_label", "protected_revenue")
        elif category == "finance_reconcile":
            money_effect.setdefault("primary_label", "risk_amount")
        elif category == "save_money":
            money_effect.setdefault("primary_label", "save_amount")
        score = self._owner_priority_score(
            action.model_copy(update={"category": category})
        )
        return action.model_copy(
            update={
                "category": category,
                "business_reason": action.business_reason or action.why,
                "next_step": action.next_step or action.what_to_do,
                "title": self._owner_action_title(
                    action.model_copy(update={"category": category})
                ),
                "expected_effect_amount": primary_amount,
                "priority_score": score,
                "priority": self._owner_priority_label(
                    action.model_copy(update={"category": category}), score=score
                ),
                "affected_nm_ids": nm_ids,
                "affected_sku_ids": sku_ids,
                "source_endpoint": action.source_endpoint
                or self._action_source_endpoint(
                    action.action_type, action.linked_entity
                ),
                "money_effect": money_effect,
            },
            deep=True,
        )

    def _owner_focus_actions(
        self, actions: list[NextActionRead], *, focus_limit: int
    ) -> list[NextActionRead]:
        focus_candidates = [
            item
            for item in actions
            if item.category in {"data_fix", "finance_reconcile"}
            or (item.financial_final and not item.blocked_reasons)
        ]
        sorted_actions = sorted(
            focus_candidates,
            key=lambda item: (
                2
                if item.category == "data_fix"
                else 1
                if item.financial_final and not item.blocked_reasons
                else 0,
                self._priority_rank(item.priority),
                item.priority_score or 0,
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        )
        return sorted_actions[:focus_limit]

    @staticmethod
    def _source_of_truth_label(
        *, finance_confirmed_revenue: Decimal, mart_revenue: Decimal
    ) -> str:
        if finance_confirmed_revenue > 0 and mart_revenue > 0:
            return "mixed"
        if finance_confirmed_revenue > 0:
            return "finance"
        if mart_revenue > 0:
            return "mart"
        return "operational"

    @staticmethod
    def _reconciliation_status(
        *, finance_confirmed_revenue: Decimal, mart_revenue: Decimal
    ) -> str:
        if finance_confirmed_revenue <= 0 and mart_revenue <= 0:
            return "not_ready"
        if finance_confirmed_revenue <= 0 or mart_revenue <= 0:
            return "partial"
        diff = abs(finance_confirmed_revenue - mart_revenue)
        ratio = (
            (diff / mart_revenue * Decimal("100")) if mart_revenue > 0 else Decimal("0")
        )
        if ratio > Decimal("10"):
            return "critical_mismatch"
        if ratio > Decimal("3"):
            return "warning_mismatch"
        return "matched"

    @staticmethod
    def _sale_row_date(row: Any) -> date | None:
        sale_date = getattr(row, "date", None)
        if isinstance(sale_date, datetime):
            return sale_date.date()
        change_date = getattr(row, "last_change_date", None)
        if isinstance(change_date, datetime):
            return change_date.date()
        return None

    @classmethod
    def _signed_sale_amount(cls, row: Any) -> Decimal:
        amount = cls._decimal(
            getattr(row, "finished_price", None)
            or getattr(row, "price_with_disc", None)
            or getattr(row, "total_price", None)
        )
        if amount == 0:
            return amount
        if (
            bool(getattr(row, "is_cancel", False))
            or cls._decimal(getattr(row, "for_pay", None)) < 0
        ):
            return -abs(amount)
        return abs(amount)

    @staticmethod
    def _entry_amount_matches(
        left: ReconciliationEntry,
        right: ReconciliationEntry,
        *,
        tolerance: Decimal = Decimal("1.00"),
    ) -> bool:
        if (left.signed_amount < 0) != (right.signed_amount < 0):
            return False
        return abs(abs(left.signed_amount) - abs(right.signed_amount)) <= tolerance

    @staticmethod
    def _entry_dates_close(
        left: date | None, right: date | None, *, days: int = 1
    ) -> bool:
        if left is None or right is None:
            return False
        return abs((left - right).days) <= days

    async def _finance_closed_period(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> tuple[date | None, date | None]:
        reports = list(
            (
                await session.execute(
                    select(WBRealizationReport).where(
                        WBRealizationReport.account_id == account_id
                    )
                )
            ).scalars()
        )
        overlapping_reports = [
            report
            for report in reports
            if (report.date_to or report.create_date) is not None
            and (report.date_to or report.create_date) >= date_from
            and (report.date_from or report.date_to or report.create_date) <= date_to
        ]
        closed_to = None
        if overlapping_reports:
            closed_to = max(
                (report.date_to or report.create_date)
                for report in overlapping_reports
                if (report.date_to or report.create_date) is not None
            )
        if closed_to is None:
            closed_to = await self._finance_coverage_date_to(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
            )
        if closed_to is None:
            return None, None
        closed_to = min(closed_to, date_to)
        closed_from_candidates = [
            report.date_from
            for report in overlapping_reports
            if report.date_from is not None
        ]
        closed_from = (
            max(date_from, min(closed_from_candidates))
            if closed_from_candidates
            else date_from
        )
        if closed_from > closed_to:
            closed_from = date_from if date_from <= closed_to else closed_to
        return closed_from, closed_to

    async def _operational_sales_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[WBSale]:
        start_dt = datetime.combine(date_from, datetime.min.time())
        end_dt = datetime.combine(date_to, datetime.max.time())
        return list(
            (
                await session.execute(
                    select(WBSale).where(
                        WBSale.account_id == account_id,
                        or_(
                            WBSale.last_change_date.between(start_dt, end_dt),
                            WBSale.date.between(start_dt, end_dt),
                        ),
                    )
                )
            ).scalars()
        )

    async def _finance_rows_for_period(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[FinanceReconciliationSourceRow]:
        doc_type = func.lower(
            func.trim(func.coalesce(WBRealizationReportRow.doc_type_name, ""))
        )
        reconcilable_clause = or_(
            WBRealizationReportRow.is_reconcilable.is_(True),
            and_(
                WBRealizationReportRow.is_reconcilable.is_(None),
                doc_type.in_(("продажа", "возврат", "sale", "return")),
            ),
        )
        rows = (
            await session.execute(
                select(
                    WBRealizationReportRow.rrd_id,
                    WBRealizationReportRow.srid,
                    WBRealizationReportRow.nm_id,
                    WBRealizationReportRow.rr_date,
                    WBRealizationReportRow.sale_dt,
                    WBRealizationReportRow.retail_amount,
                    WBRealizationReportRow.for_pay,
                    WBRealizationReportRow.doc_type_name,
                    WBRealizationReportRow.is_reconcilable,
                    WBRealizationReportRow.is_return_operation,
                ).where(
                    WBRealizationReportRow.account_id == account_id,
                    WBRealizationReportRow.rr_date >= date_from,
                    WBRealizationReportRow.rr_date <= date_to,
                    reconcilable_clause,
                )
            )
        ).all()
        return [
            FinanceReconciliationSourceRow(
                rrd_id=row.rrd_id,
                srid=row.srid,
                nm_id=row.nm_id,
                rr_date=row.rr_date,
                sale_dt=row.sale_dt,
                retail_amount=row.retail_amount,
                for_pay=row.for_pay,
                doc_type_name=row.doc_type_name,
                is_reconcilable=row.is_reconcilable,
                is_return_operation=row.is_return_operation,
            )
            for row in rows
        ]

    def _build_finance_reconciliation(
        self,
        *,
        requested_date_from: date,
        requested_date_to: date,
        closed_finance_date_from: date | None,
        closed_finance_date_to: date | None,
        operational_rows: list[Any],
        finance_rows: list[FinanceReconciliationSourceRow],
        account_level_expense_total: Decimal = Decimal("0"),
        closed_mart_revenue: Decimal | None = None,
        full_mart_revenue: Decimal | None = None,
    ) -> FinanceReconciliationBlock:
        if closed_finance_date_to is None:
            return FinanceReconciliationBlock(
                status="not_available",
                requested_date_from=requested_date_from,
                requested_date_to=requested_date_to,
                closed_finance_date_from=closed_finance_date_from,
                closed_finance_date_to=closed_finance_date_to,
                operational_revenue_label="Операционная выручка в выбранном периоде",
                finance_confirmed_revenue_label="Выручка по закрытым отчетам WB",
                requested_period_label=f"Запрошенный период: {requested_date_from.isoformat()} — {requested_date_to.isoformat()}",
                closed_finance_period_label="Период отчётов WB пока не закрыт",
                open_operational_period_revenue_label="Выручка вне закрытого периода WB",
                comparison_scope_label="Сравнение станет полным, когда WB закроет отчет за выбранные даты.",
                classified_difference=FinanceReconciliationClassifiedDifference(
                    account_level_expense=self._float0(account_level_expense_total),
                ),
                recommendation="За выбранный период еще нет закрытого отчета WB. Дождитесь его или загрузите отчет.",
            )

        closed_from = closed_finance_date_from or requested_date_from
        closed_to = min(closed_finance_date_to, requested_date_to)

        operational_entries: list[ReconciliationEntry] = []
        for idx, row in enumerate(operational_rows):
            row_date = self._sale_row_date(row)
            if (
                row_date is None
                or row_date < requested_date_from
                or row_date > requested_date_to
            ):
                continue
            amount = self._signed_sale_amount(row)
            operational_entries.append(
                ReconciliationEntry(
                    key=f"sale:{getattr(row, 'srid', None) or idx}:{idx}",
                    srid=getattr(row, "srid", None),
                    nm_id=int(getattr(row, "nm_id"))
                    if getattr(row, "nm_id", None) is not None
                    else None,
                    event_date=row_date,
                    report_date=row_date,
                    signed_amount=amount,
                    is_return=amount < 0,
                )
            )

        finance_entries: list[ReconciliationEntry] = []
        for idx, row in enumerate(finance_rows):
            if not self._finance_row_is_reconcilable(row):
                continue
            if (
                row.rr_date is None
                or row.rr_date < requested_date_from
                or row.rr_date > requested_date_to
            ):
                continue
            amount = self._signed_finance_amount(row, row.retail_amount)
            finance_entries.append(
                ReconciliationEntry(
                    key=f"finance:{row.rrd_id or idx}",
                    srid=row.srid,
                    nm_id=int(row.nm_id) if row.nm_id is not None else None,
                    event_date=row.sale_dt.date()
                    if row.sale_dt is not None
                    else row.rr_date,
                    report_date=row.rr_date,
                    signed_amount=amount,
                    is_return=amount < 0,
                )
            )

        closed_operational_entries = [
            entry
            for entry in operational_entries
            if entry.event_date is not None
            and closed_from <= entry.event_date <= closed_to
        ]
        open_operational_entries = [
            entry
            for entry in operational_entries
            if entry.event_date is not None
            and (entry.event_date < closed_from or entry.event_date > closed_to)
        ]
        closed_finance_entries = [
            entry
            for entry in finance_entries
            if entry.report_date is not None
            and closed_from <= entry.report_date <= closed_to
        ]

        row_operational_revenue = sum(
            (entry.signed_amount for entry in closed_operational_entries),
            start=Decimal("0"),
        )
        finance_confirmed_revenue = sum(
            (entry.signed_amount for entry in closed_finance_entries),
            start=Decimal("0"),
        )
        row_open_operational_period_revenue = sum(
            (entry.signed_amount for entry in open_operational_entries),
            start=Decimal("0"),
        )
        use_mart_revenue = closed_mart_revenue is not None and closed_mart_revenue > 0
        operational_revenue = (
            closed_mart_revenue if use_mart_revenue else row_operational_revenue
        )
        open_operational_period_revenue = (
            max(
                Decimal("0"),
                (full_mart_revenue or Decimal("0"))
                - (closed_mart_revenue or Decimal("0")),
            )
            if use_mart_revenue and full_mart_revenue is not None
            else row_open_operational_period_revenue
        )

        matched_operational: set[str] = set()
        matched_finance: set[str] = set()
        return_timing = Decimal("0")
        finance_only = Decimal("0")
        operational_only = Decimal("0")
        unknown = Decimal("0")

        def mark_match(
            finance_entry: ReconciliationEntry, operational_entry: ReconciliationEntry
        ) -> None:
            matched_finance.add(finance_entry.key)
            matched_operational.add(operational_entry.key)

        # 1. Exact-ish SRID match.
        for finance_entry in closed_finance_entries:
            if finance_entry.srid is None or finance_entry.key in matched_finance:
                continue
            candidate = next(
                (
                    operational_entry
                    for operational_entry in closed_operational_entries
                    if operational_entry.key not in matched_operational
                    and operational_entry.srid == finance_entry.srid
                    and self._entry_amount_matches(finance_entry, operational_entry)
                ),
                None,
            )
            if candidate is not None:
                mark_match(finance_entry, candidate)

        # 2. Fallback by nm_id + date + amount.
        for finance_entry in closed_finance_entries:
            if finance_entry.key in matched_finance or finance_entry.nm_id is None:
                continue
            candidate = next(
                (
                    operational_entry
                    for operational_entry in closed_operational_entries
                    if operational_entry.key not in matched_operational
                    and operational_entry.nm_id == finance_entry.nm_id
                    and self._entry_amount_matches(finance_entry, operational_entry)
                    and self._entry_dates_close(
                        finance_entry.event_date, operational_entry.event_date, days=1
                    )
                ),
                None,
            )
            if candidate is not None:
                mark_match(finance_entry, candidate)

        # 3. Return timing across different days.
        for finance_entry in closed_finance_entries:
            if finance_entry.key in matched_finance or not finance_entry.is_return:
                continue
            candidate = next(
                (
                    operational_entry
                    for operational_entry in closed_operational_entries
                    if operational_entry.key not in matched_operational
                    and operational_entry.is_return
                    and (
                        (
                            finance_entry.srid
                            and finance_entry.srid == operational_entry.srid
                        )
                        or (
                            finance_entry.nm_id is not None
                            and finance_entry.nm_id == operational_entry.nm_id
                        )
                    )
                    and self._entry_amount_matches(finance_entry, operational_entry)
                ),
                None,
            )
            if candidate is not None:
                return_timing += min(
                    abs(finance_entry.signed_amount), abs(candidate.signed_amount)
                )
                mark_match(finance_entry, candidate)

        # 4. Partial mismatch on same SRID/nm_id bucket counts as unknown delta.
        for finance_entry in closed_finance_entries:
            if finance_entry.key in matched_finance:
                continue
            candidate = next(
                (
                    operational_entry
                    for operational_entry in closed_operational_entries
                    if operational_entry.key not in matched_operational
                    and (
                        (
                            finance_entry.srid
                            and finance_entry.srid == operational_entry.srid
                        )
                        or (
                            finance_entry.nm_id is not None
                            and finance_entry.nm_id == operational_entry.nm_id
                            and self._entry_dates_close(
                                finance_entry.event_date,
                                operational_entry.event_date,
                                days=1,
                            )
                        )
                    )
                    and (finance_entry.signed_amount < 0)
                    == (operational_entry.signed_amount < 0)
                ),
                None,
            )
            if candidate is not None:
                unknown += abs(
                    abs(finance_entry.signed_amount) - abs(candidate.signed_amount)
                )
                mark_match(finance_entry, candidate)

        for finance_entry in closed_finance_entries:
            if finance_entry.key in matched_finance:
                continue
            finance_only += abs(finance_entry.signed_amount)

        for operational_entry in closed_operational_entries:
            if operational_entry.key in matched_operational:
                continue
            operational_only += abs(operational_entry.signed_amount)

        difference_amount = abs(operational_revenue - finance_confirmed_revenue)
        if use_mart_revenue:
            return_timing = Decimal("0")
            finance_only = Decimal("0")
            operational_only = Decimal("0")
            unknown = difference_amount
        difference_percent = self._percent0(
            difference_amount,
            abs(operational_revenue)
            if operational_revenue != 0
            else abs(finance_confirmed_revenue),
        )
        unknown_percent = self._percent0(
            unknown,
            abs(operational_revenue)
            if operational_revenue != 0
            else abs(finance_confirmed_revenue),
        )

        if difference_amount <= Decimal("1") and unknown <= Decimal("1"):
            status = "matched"
        elif unknown_percent > 10 or difference_percent > 10:
            status = "critical_mismatch"
        elif unknown_percent > 3 or difference_percent > 3:
            status = "warning_mismatch"
        else:
            status = "matched"

        if status == "matched":
            recommendation = (
                "Продажи и отчет WB совпадают. Этот период можно считать итоговым."
            )
        elif status == "warning_mismatch":
            recommendation = "Есть небольшое расхождение. Проверьте строки только в отчете WB, только в продажах и возвраты по датам."
        else:
            recommendation = "Есть заметное расхождение. Сначала разберите строки только в отчете WB, только в продажах и неясную разницу."

        return FinanceReconciliationBlock(
            status=status,
            operational_revenue=self._float0(operational_revenue),
            operational_revenue_label=(
                "Выручка mart_sku_daily в закрытом периоде WB"
                if use_mart_revenue
                else "Выручка по операционным продажам в закрытом периоде WB"
            ),
            finance_confirmed_revenue=self._float0(finance_confirmed_revenue),
            finance_confirmed_revenue_label="Выручка по закрытым отчетам WB",
            difference_amount=self._float0(difference_amount),
            difference_percent=difference_percent,
            closed_finance_date_from=closed_from,
            closed_finance_date_to=closed_to,
            requested_date_from=requested_date_from,
            requested_date_to=requested_date_to,
            requested_period_label=f"Запрошенный период: {requested_date_from.isoformat()} — {requested_date_to.isoformat()}",
            closed_finance_period_label=f"Период отчётов WB: {closed_from.isoformat()} — {closed_to.isoformat()}",
            open_operational_period_revenue=self._float0(
                open_operational_period_revenue
            ),
            open_operational_period_revenue_label="Операционная выручка после последней закрытой даты WB",
            comparison_scope_label=(
                "Сравнение идет по финальной витрине mart_sku_daily за даты, закрытые отчетом WB. Остальная выручка показана отдельно."
                if use_mart_revenue
                else "Сравнение идет только по тем датам, за которые уже есть закрытый отчет WB. Остальная выручка показана отдельно."
            ),
            classified_difference=FinanceReconciliationClassifiedDifference(
                expected_lag=self._float0(abs(open_operational_period_revenue)),
                return_timing=self._float0(return_timing),
                finance_only=self._float0(finance_only),
                operational_only=self._float0(operational_only),
                unallocated_expense=0.0,
                account_level_expense=self._float0(account_level_expense_total),
                unknown=self._float0(unknown),
            ),
            is_final=status == "matched",
            recommendation=recommendation,
        )

    def _ads_allocation_metrics(
        self,
        *,
        ads_source_spend: Decimal,
        mart_ads_allocated_spend: Decimal,
        ads_allocatable_source_spend: Decimal,
    ) -> dict[str, Decimal | float | str]:
        """Return store-level ad allocation quality without double-counting.

        WBAdStatsDaily.sum is the real cash source.  mart_sku_daily.ad_spend
        and nm-level allocation can describe the same advertising spend at
        different grains.  They must not be added together and must never make
        allocated spend exceed the WB source spend.
        """
        if ads_source_spend <= 0:
            raw_ads_allocated = max(
                mart_ads_allocated_spend, ads_allocatable_source_spend, Decimal("0")
            )
            return {
                "raw_ads_allocated": raw_ads_allocated,
                "capped_ads_allocated_spend": Decimal("0"),
                "ads_allocated_spend": Decimal("0"),
                "ads_unallocated_spend": Decimal("0"),
                "ads_duplicate_ignored_spend": raw_ads_allocated,
                "ads_overallocated_spend": Decimal("0"),
                "ads_allocation_percent_raw": 0.0,
                "ads_allocation_percent_capped": 0.0,
                "ads_allocation_status": "no_source_data",
                "final_profit_allowed": False,
            }
        source_backed_allocated = max(ads_allocatable_source_spend, Decimal("0"))
        raw_ads_allocated = max(
            mart_ads_allocated_spend, source_backed_allocated, Decimal("0")
        )
        capped_ads_allocated_spend = min(
            max(raw_ads_allocated, Decimal("0")), ads_source_spend
        )
        ads_unallocated_spend = max(
            Decimal("0"), ads_source_spend - capped_ads_allocated_spend
        )
        ads_overallocated_spend = max(
            Decimal("0"), raw_ads_allocated - ads_source_spend
        )
        rounding_tolerance = max(
            Decimal("0.01"),
            min(Decimal("1.00"), ads_source_spend * Decimal("0.000001")),
        )
        if Decimal("0") < ads_unallocated_spend <= rounding_tolerance:
            raw_ads_allocated = ads_source_spend
            capped_ads_allocated_spend = ads_source_spend
            ads_unallocated_spend = Decimal("0")
        elif Decimal("0") < ads_overallocated_spend <= rounding_tolerance:
            raw_ads_allocated = ads_source_spend
            capped_ads_allocated_spend = ads_source_spend
            ads_overallocated_spend = Decimal("0")
        ads_duplicate_ignored_spend = ads_overallocated_spend
        ads_allocation_percent_raw = self._percent0(raw_ads_allocated, ads_source_spend)
        ads_allocation_percent_capped = min(
            100.0, self._percent0(capped_ads_allocated_spend, ads_source_spend)
        )
        if ads_overallocated_spend > 0:
            status = "overallocated"
        elif ads_unallocated_spend > 0:
            status = "partial"
        else:
            status = "matched"
        return {
            "raw_ads_allocated": raw_ads_allocated,
            "capped_ads_allocated_spend": capped_ads_allocated_spend,
            "ads_allocated_spend": capped_ads_allocated_spend,
            "ads_unallocated_spend": ads_unallocated_spend,
            "ads_duplicate_ignored_spend": ads_duplicate_ignored_spend,
            "ads_overallocated_spend": ads_overallocated_spend,
            "ads_allocation_percent_raw": ads_allocation_percent_raw,
            "ads_allocation_percent_capped": ads_allocation_percent_capped,
            "ads_allocation_status": status,
            "final_profit_allowed": ads_overallocated_spend <= 0,
        }

    @staticmethod
    def _cost_truth_label(truth_level: str | None) -> str:
        if not truth_level:
            return ""
        return get_enum_mapping("cost_truth_level").get(truth_level, truth_level)

    @staticmethod
    def _positive_part(value: Decimal | float | int | None) -> Decimal:
        decimal_value = Decimal(str(value or 0))
        return decimal_value if decimal_value > 0 else Decimal("0")

    @staticmethod
    def _negative_part_abs(value: Decimal | float | int | None) -> Decimal:
        decimal_value = Decimal(str(value or 0))
        return abs(decimal_value) if decimal_value < 0 else Decimal("0")

    @classmethod
    def _expense_value(
        cls, row: Any, field: str, legacy_field: str | None = None
    ) -> Decimal:
        value = getattr(row, field, None)
        if value in (None, "") and legacy_field:
            value = getattr(row, legacy_field, None)
        return cls._decimal(value)

    @staticmethod
    def _expense_signed_amount_expr() -> Any:
        return case(
            (MartExpenseDaily.amount_sign == "income", -MartExpenseDaily.amount),
            else_=MartExpenseDaily.amount,
        )

    @staticmethod
    def _expense_category_label(category: str | None) -> str:
        if not category:
            return ""
        return get_enum_mapping("expense_category").get(category, category)

    @staticmethod
    def _expense_source_label(source: str | None) -> str:
        labels = {
            "finance_report": "Финансовый отчет WB",
            "manual_cost": "Ручная себестоимость продавца",
            "ads_api": "Операционная реклама",
            "computed": "Вычислено",
            "mixed": "Смешанный источник",
        }
        if not source:
            return ""
        return labels.get(source, source)

    @staticmethod
    def _logistics_share_base(
        *,
        total_wb_expenses: Decimal,
        total_expenses: Decimal,
    ) -> tuple[str, Decimal]:
        if total_wb_expenses > 0:
            return ("wb_expenses", total_wb_expenses)
        return ("all_expenses", total_expenses)

    @classmethod
    def _expense_is_final(
        cls, *, category: str | None = None, source: str | None = None
    ) -> bool:
        actual_source = source or cls.EXPENSE_CATEGORY_PRIMARY_SOURCE.get(
            category or "", ""
        )
        return actual_source in {"finance_report", "manual_cost"}

    @classmethod
    def _expense_breakdown_sort_key(
        cls, item: ExpenseBreakdownItemRead
    ) -> tuple[int, float, str]:
        category = item.category or ""
        try:
            order = cls.EXPENSE_BREAKDOWN_CATEGORY_ORDER.index(category)
        except ValueError:
            order = len(cls.EXPENSE_BREAKDOWN_CATEGORY_ORDER)
        return (order, -float(item.amount or 0), item.label or item.group_key)

    def _summary_expense_breakdown(
        self,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        kpis: MoneySummaryKpis,
        data_version_hash: str | None = None,
        source_of_truth: str = "mixed",
    ) -> ExpenseBreakdownSummaryRead:
        total_wb_expenses = self._decimal(getattr(kpis, "wb_expenses_total", 0.0))
        total_seller_expenses = self._decimal(
            getattr(
                kpis, "total_seller_costs", getattr(kpis, "total_seller_expenses", 0.0)
            )
        )
        total_ad_expenses = self._decimal(getattr(kpis, "ad_spend_final", 0.0))
        total_expenses = total_wb_expenses + total_seller_expenses + total_ad_expenses
        item_specs = [
            (
                EXPENSE_CATEGORY_WB_LOGISTICS,
                self._decimal(getattr(kpis, "wb_logistics", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
                self._decimal(getattr(kpis, "wb_logistics_rebill", 0.0)),
            ),
            (EXPENSE_CATEGORY_STORAGE, self._decimal(getattr(kpis, "storage", 0.0))),
            (
                EXPENSE_CATEGORY_ACCEPTANCE,
                self._decimal(getattr(kpis, "acceptance", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_WB_COMMISSION,
                self._decimal(getattr(kpis, "wb_commission", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_PAYMENT_PROCESSING,
                self._decimal(getattr(kpis, "payment_processing", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_PVZ_REWARD,
                self._decimal(getattr(kpis, "pvz_reward", 0.0)),
            ),
            (EXPENSE_CATEGORY_PENALTY, self._decimal(getattr(kpis, "penalty", 0.0))),
            (
                EXPENSE_CATEGORY_DEDUCTION,
                self._decimal(getattr(kpis, "deduction", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_MARKETING_DEDUCTION,
                self._decimal(getattr(kpis, "marketing_deduction", 0.0)),
            ),
            (EXPENSE_CATEGORY_LOYALTY, self._decimal(getattr(kpis, "loyalty", 0.0))),
            (
                EXPENSE_CATEGORY_UNCLASSIFIED,
                self._decimal(getattr(kpis, "other_wb_expenses", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_SELLER_COGS,
                self._decimal(getattr(kpis, "seller_cogs", 0.0)),
            ),
            (
                EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE,
                self._decimal(getattr(kpis, "seller_other_expense", 0.0)),
            ),
            (
                "ads_operational",
                max(
                    Decimal("0"),
                    total_ad_expenses
                    - self._decimal(getattr(kpis, "marketing_deduction", 0.0)),
                ),
            ),
        ]
        items = [
            ExpenseBreakdownItemRead(
                group_key=category,
                label=self._expense_category_label(category),
                amount=self._float0(amount),
                share_percent=self._percent0(amount, total_expenses)
                if total_expenses > 0
                else 0.0,
                category=category,
                source=self.EXPENSE_CATEGORY_PRIMARY_SOURCE.get(category, "mixed"),
                is_final=self._expense_is_final(category=category),
            )
            for category, amount in item_specs
            if amount != 0
        ]
        items.sort(key=self._expense_breakdown_sort_key)
        logistics_total = self._decimal(
            getattr(kpis, "wb_logistics", 0.0)
        ) + self._decimal(getattr(kpis, "wb_logistics_rebill", 0.0))
        logistics_share_base_kind, logistics_share_base_amount = (
            self._logistics_share_base(
                total_wb_expenses=total_wb_expenses,
                total_expenses=total_expenses,
            )
        )
        return ExpenseBreakdownSummaryRead(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            group_by="category",
            include_unallocated=True,
            revenue_final=self._float0(
                getattr(kpis, "revenue_final", None) or getattr(kpis, "revenue", 0.0)
            ),
            net_profit_after_all_expenses=self._float0(
                getattr(kpis, "net_profit_after_all_expenses", 0.0)
            ),
            seller_cogs=self._float0(getattr(kpis, "seller_cogs", 0.0)),
            seller_other_expense=self._float0(
                getattr(kpis, "seller_other_expense", 0.0)
            ),
            ad_spend_final=self._float0(getattr(kpis, "ad_spend_final", 0.0)),
            additional_income=self._float0(getattr(kpis, "additional_income", 0.0)),
            total_expenses=self._float0(total_expenses),
            total_wb_expenses=self._float0(total_wb_expenses),
            total_seller_expenses=self._float0(total_seller_expenses),
            total_ad_expenses=self._float0(total_ad_expenses),
            logistics_total=self._float0(logistics_total),
            logistics_share_base_kind=logistics_share_base_kind,
            logistics_share_base_amount=self._float0(logistics_share_base_amount),
            logistics_share_percent=self._percent0(
                logistics_total, logistics_share_base_amount
            )
            if logistics_share_base_amount > 0
            else 0.0,
            data_version_hash=data_version_hash,
            source_of_truth=source_of_truth,
            items=items,
        )

    @classmethod
    def _profit_cascade_label(cls, code: str, *, group: bool = False) -> str:
        mapping = (
            cls.PROFIT_CASCADE_GROUP_LABELS
            if group
            else cls.PROFIT_CASCADE_CHILD_LABELS
        )
        return mapping.get(code, code)

    @classmethod
    def _profit_cascade_source_of_truth(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        return cls.PROFIT_CASCADE_SOURCE_OF_TRUTH_MAP.get(normalized, "mixed")

    @staticmethod
    def _profit_cascade_ad_source(
        *,
        ad_spend_final: Decimal,
        ad_spend_finance: Decimal,
        ad_spend_operational: Decimal,
        ad_spend_source: str | None,
    ) -> str:
        normalized_source = str(ad_spend_source or "").strip().lower()
        if ad_spend_finance > 0 and ad_spend_operational > 0:
            if normalized_source in {
                AD_SPEND_SOURCE_FINANCE,
                AD_SPEND_SOURCE_OPERATIONAL,
                "mixed",
            }:
                return normalized_source
            if ad_spend_final == ad_spend_finance:
                return AD_SPEND_SOURCE_FINANCE
            if ad_spend_final == ad_spend_operational:
                return AD_SPEND_SOURCE_OPERATIONAL
            return "mixed"
        if ad_spend_finance > 0:
            return AD_SPEND_SOURCE_FINANCE
        if ad_spend_operational > 0 or ad_spend_final > 0:
            return AD_SPEND_SOURCE_OPERATIONAL
        return AD_SPEND_SOURCE_NONE

    def _profit_cascade_child(
        self,
        *,
        code: str,
        amount: Decimal,
        source: str,
        share_base: Decimal = Decimal("0"),
        label: str | None = None,
        ad_spend_operational: Decimal = Decimal("0"),
        ad_spend_finance: Decimal = Decimal("0"),
        ad_spend_source: str = "",
    ) -> ProfitCascadeChildRead:
        return ProfitCascadeChildRead(
            code=code,
            label=label or self._profit_cascade_label(code),
            amount=self._float0(amount),
            share_percent=self._percent0(amount, share_base) if share_base > 0 else 0.0,
            source=source,
            ad_spend_operational=self._float0(ad_spend_operational),
            ad_spend_finance=self._float0(ad_spend_finance),
            ad_spend_source=ad_spend_source,
        )

    def _profit_cascade_group(
        self,
        *,
        code: str,
        amount: Decimal,
        sign: str,
        children: list[ProfitCascadeChildRead],
        issues: list[str],
    ) -> tuple[ProfitCascadeGroupRead, bool]:
        target_amount = self._decimal(amount)
        child_sum = sum(
            (self._decimal(item.amount) for item in children), start=Decimal("0")
        )
        groups_match_children = True
        delta = target_amount - child_sum
        if abs(delta) > Decimal("0.01"):
            groups_match_children = False
            issues.append(f"group:{code}:children_sum_delta={self._float0(delta):.2f}")
            children.append(
                self._profit_cascade_child(
                    code="other_or_rounding_delta",
                    label=self._profit_cascade_label("other_or_rounding_delta"),
                    amount=delta,
                    source="computed",
                )
            )
            child_sum += delta
        share_base = target_amount if target_amount > 0 else child_sum
        finalized_children = [
            item.model_copy(
                update={
                    "share_percent": self._percent0(item.amount, share_base)
                    if share_base > 0
                    else 0.0,
                }
            )
            for item in children
        ]
        return (
            ProfitCascadeGroupRead(
                code=code,
                label=self._profit_cascade_label(code, group=True),
                amount=self._float0(target_amount),
                sign=sign,
                children=finalized_children,
            ),
            groups_match_children,
        )

    def _build_profit_cascade(
        self,
        *,
        meta: MoneyMeta,
        revenue_sources: RevenueSources,
        kpis: MoneySummaryKpis,
        data_version_hash: str | None = None,
    ) -> ProfitCascadeRead:
        gross_revenue = self._decimal(
            getattr(kpis, "revenue_final", None) or getattr(kpis, "revenue", 0.0)
        )
        seller_cogs = self._decimal(getattr(kpis, "seller_cogs", 0.0))
        seller_other_expense = self._decimal(getattr(kpis, "seller_other_expense", 0.0))
        total_seller_expenses = seller_cogs + seller_other_expense
        wb_commission = self._decimal(getattr(kpis, "wb_commission", 0.0))
        payment_processing = self._decimal(getattr(kpis, "payment_processing", 0.0))
        pvz_reward = self._decimal(getattr(kpis, "pvz_reward", 0.0))
        wb_logistics = self._decimal(getattr(kpis, "wb_logistics", 0.0))
        wb_logistics_rebill = self._decimal(getattr(kpis, "wb_logistics_rebill", 0.0))
        storage = self._decimal(getattr(kpis, "storage", 0.0))
        acceptance = self._decimal(getattr(kpis, "acceptance", 0.0))
        penalty = self._decimal(getattr(kpis, "penalty", 0.0))
        deduction = self._decimal(getattr(kpis, "deduction", 0.0))
        loyalty = self._decimal(getattr(kpis, "loyalty", 0.0))
        unclassified_wb_expenses = self._decimal(
            getattr(kpis, "other_wb_expenses", 0.0)
        )
        other_wb_expenses = loyalty
        wb_expense_formula_total = (
            wb_commission
            + payment_processing
            + pvz_reward
            + wb_logistics
            + wb_logistics_rebill
            + storage
            + acceptance
            + penalty
            + deduction
            + other_wb_expenses
            + unclassified_wb_expenses
        )
        reported_total_wb_expenses = self._decimal(
            getattr(kpis, "wb_expenses_total", 0.0)
        )
        total_wb_expenses = (
            reported_total_wb_expenses
            if reported_total_wb_expenses > 0 or wb_expense_formula_total == 0
            else wb_expense_formula_total
        )
        ad_spend_finance = self._decimal(getattr(kpis, "ad_spend_finance", 0.0))
        ad_spend_operational = self._decimal(getattr(kpis, "ad_spend_operational", 0.0))
        ad_spend_final = self._decimal(getattr(kpis, "ad_spend_final", 0.0))
        ad_spend_source = self._profit_cascade_ad_source(
            ad_spend_final=ad_spend_final,
            ad_spend_finance=ad_spend_finance,
            ad_spend_operational=ad_spend_operational,
            ad_spend_source=getattr(kpis, "ad_spend_source", ""),
        )
        additional_income = self._decimal(getattr(kpis, "additional_income", 0.0))
        net_profit_after_all_expenses = self._decimal(
            getattr(kpis, "net_profit_after_all_expenses", 0.0)
        )
        logistics_total = wb_logistics + wb_logistics_rebill
        issues: list[str] = []
        groups_match_children = True
        if reported_total_wb_expenses > 0 and abs(
            reported_total_wb_expenses - wb_expense_formula_total
        ) > Decimal("0.01"):
            issues.append(
                "total_wb_expenses_formula_delta="
                f"{self._float0(reported_total_wb_expenses - wb_expense_formula_total):.2f}"
            )

        seller_cogs_group, seller_cogs_match = self._profit_cascade_group(
            code="seller_cogs",
            amount=seller_cogs,
            sign="expense",
            children=[
                self._profit_cascade_child(
                    code="seller_cogs",
                    amount=seller_cogs,
                    source="manual_cost",
                    share_base=seller_cogs,
                )
            ],
            issues=issues,
        )
        groups_match_children = groups_match_children and seller_cogs_match

        seller_other_group, seller_other_match = self._profit_cascade_group(
            code="seller_other_expenses",
            amount=seller_other_expense,
            sign="expense",
            children=[
                self._profit_cascade_child(
                    code="seller_other_expense",
                    amount=seller_other_expense,
                    source="manual_cost",
                    share_base=seller_other_expense,
                )
            ],
            issues=issues,
        )
        groups_match_children = groups_match_children and seller_other_match

        wb_group, wb_group_match = self._profit_cascade_group(
            code="wb_direct_expenses",
            amount=total_wb_expenses,
            sign="expense",
            children=[
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_WB_LOGISTICS,
                    amount=wb_logistics,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
                    amount=wb_logistics_rebill,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_PAYMENT_PROCESSING,
                    amount=payment_processing,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_PVZ_REWARD,
                    amount=pvz_reward,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_STORAGE,
                    amount=storage,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_DEDUCTION,
                    amount=deduction,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_PENALTY,
                    amount=penalty,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_ACCEPTANCE,
                    amount=acceptance,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code=EXPENSE_CATEGORY_WB_COMMISSION,
                    amount=wb_commission,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code="other_wb_expenses",
                    amount=other_wb_expenses,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
                self._profit_cascade_child(
                    code="unclassified_wb_expenses",
                    amount=unclassified_wb_expenses,
                    source="finance_report",
                    share_base=total_wb_expenses,
                ),
            ],
            issues=issues,
        )
        groups_match_children = groups_match_children and wb_group_match

        ad_group, ad_group_match = self._profit_cascade_group(
            code="ad_expenses",
            amount=ad_spend_final,
            sign="expense",
            children=[
                self._profit_cascade_child(
                    code="ad_spend_final",
                    amount=ad_spend_final,
                    source=ad_spend_source,
                    share_base=ad_spend_final,
                    ad_spend_operational=ad_spend_operational,
                    ad_spend_finance=ad_spend_finance,
                    ad_spend_source=ad_spend_source,
                )
            ],
            issues=issues,
        )
        groups_match_children = groups_match_children and ad_group_match

        additional_income_group, additional_income_match = self._profit_cascade_group(
            code="additional_income",
            amount=additional_income,
            sign="income",
            children=[
                self._profit_cascade_child(
                    code="additional_payment",
                    amount=additional_income,
                    source="finance_report",
                    share_base=additional_income,
                )
            ],
            issues=issues,
        )
        groups_match_children = groups_match_children and additional_income_match

        expected_profit = (
            gross_revenue
            - total_seller_expenses
            - total_wb_expenses
            - ad_spend_final
            + additional_income
        )
        profit_formula_valid = abs(
            expected_profit - net_profit_after_all_expenses
        ) <= Decimal("0.01")
        if not profit_formula_valid:
            issues.append(
                "profit_formula_delta="
                f"{self._float0(net_profit_after_all_expenses - expected_profit):.2f}"
            )

        return ProfitCascadeRead(
            account_id=meta.account_id,
            date_from=meta.date_from,
            date_to=meta.date_to,
            currency=meta.currency,
            source_of_truth=self._profit_cascade_source_of_truth(
                revenue_sources.source_of_truth
            ),
            data_version_hash=data_version_hash,
            financial_final=bool(meta.data_trust.financial_final),
            operational_trusted=bool(meta.data_trust.operational_trusted),
            trust_state=str(meta.data_trust.trust_state or meta.data_trust.state),
            cascade=ProfitCascadeBodyRead(
                revenue=ProfitCascadeRevenueRead(
                    code="revenue",
                    label=self._profit_cascade_label("revenue"),
                    amount=self._float0(gross_revenue),
                    sign="income",
                ),
                groups=[
                    seller_cogs_group,
                    seller_other_group,
                    wb_group,
                    ad_group,
                    additional_income_group,
                ],
                totals=ProfitCascadeTotalsRead(
                    gross_revenue=self._float0(gross_revenue),
                    seller_cogs=self._float0(seller_cogs),
                    seller_other_expense=self._float0(seller_other_expense),
                    total_seller_expenses=self._float0(total_seller_expenses),
                    total_wb_expenses=self._float0(total_wb_expenses),
                    total_ad_expenses=self._float0(ad_spend_final),
                    additional_income=self._float0(additional_income),
                    net_profit_after_all_expenses=self._float0(
                        net_profit_after_all_expenses
                    ),
                    logistics_total=self._float0(logistics_total),
                    logistics_share_percent=self._percent0(
                        logistics_total, total_wb_expenses
                    )
                    if total_wb_expenses > 0
                    else 0.0,
                ),
                validation=ProfitCascadeValidationRead(
                    groups_match_children=groups_match_children,
                    profit_formula_valid=profit_formula_valid,
                    issues=issues,
                ),
            ),
        )

    @staticmethod
    def _sku_extra_ad_expr() -> Any:
        ad_diff = func.coalesce(MartSKUDaily.ad_spend_final, 0) - func.coalesce(
            MartSKUDaily.ad_spend_finance, 0
        )
        return case((ad_diff > 0, ad_diff), else_=0)

    @staticmethod
    def _expense_base_filters(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[Any]:
        return [
            MartExpenseDaily.account_id == account_id,
            MartExpenseDaily.stat_date >= date_from,
            MartExpenseDaily.stat_date <= date_to,
        ]

    @staticmethod
    def _account_expense_base_filters(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[Any]:
        return [
            MartAccountExpenseDaily.account_id == account_id,
            MartAccountExpenseDaily.stat_date >= date_from,
            MartAccountExpenseDaily.stat_date <= date_to,
        ]

    @staticmethod
    def _raw_finance_date_filters(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        timezone_name: str | None = None,
    ) -> list[Any]:
        return [
            WBRealizationReportRow.account_id == account_id,
            MartService._finance_stat_date_filter(
                date_from=date_from,
                date_to=date_to,
                timezone_name=timezone_name,
            ),
        ]

    async def _account_timezone(self, session: AsyncSession, *, account_id: int) -> str:
        if not hasattr(session, "scalar"):
            return MartService.DEFAULT_FINANCE_TIMEZONE
        value = await session.scalar(
            select(WBAccount.timezone).where(WBAccount.id == account_id)
        )
        return str(value or MartService.DEFAULT_FINANCE_TIMEZONE)

    async def _raw_finance_expense_entries(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        categories: set[str] | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
    ) -> list[dict[str, Any]]:
        timezone_name = await self._account_timezone(session, account_id=account_id)
        raw_filters = self._raw_finance_date_filters(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            timezone_name=timezone_name,
        )
        if nm_id is not None:
            raw_filters.append(WBRealizationReportRow.nm_id == nm_id)
        if categories == {
            EXPENSE_CATEGORY_WB_LOGISTICS,
            EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
        }:
            raw_filters.append(
                or_(
                    func.coalesce(WBRealizationReportRow.delivery_service, 0) != 0,
                    func.coalesce(WBRealizationReportRow.rebill_logistic_cost, 0) != 0,
                )
            )
        core_skus = (
            list(
                (
                    await session.execute(
                        select(CoreSKU).where(
                            CoreSKU.account_id == account_id,
                            CoreSKU.is_active.is_(True),
                        )
                    )
                ).scalars()
            )
            if hasattr(session, "scalar")
            else []
        )
        core_index = MartService._build_core_sku_index(core_skus)
        sku_resolver = MartService()
        stmt = select(WBRealizationReportRow).where(*raw_filters)
        rows = list((await session.execute(stmt)).scalars())
        entries: list[dict[str, Any]] = []
        for finance_row_value in rows:
            tuple_sku_id = None
            tuple_vendor_code = None
            finance_row = finance_row_value
            if isinstance(finance_row_value, tuple):
                finance_row = finance_row_value[0]
                tuple_sku_id = (
                    finance_row_value[1] if len(finance_row_value) > 1 else None
                )
                tuple_vendor_code = (
                    finance_row_value[2] if len(finance_row_value) > 2 else None
                )
            finance_barcode = MartService._finance_row_barcode(finance_row)
            resolved_sku = sku_resolver._resolve_core_sku(
                core_index,
                vendor_code=finance_row.vendor_code,
                nm_id=finance_row.nm_id,
                barcode=finance_barcode,
                tech_size=None,
            )
            core_sku_id = resolved_sku.id if resolved_sku is not None else tuple_sku_id
            core_vendor_code = (
                resolved_sku.vendor_code
                if resolved_sku is not None
                else tuple_vendor_code
            )
            if sku_id is not None and core_sku_id != sku_id:
                continue
            try:
                try:
                    details = MartService._finance_expense_details(
                        finance_row,
                        sku_id=core_sku_id,
                        timezone_name=timezone_name,
                    )
                except TypeError:
                    details = MartService._finance_expense_details(
                        finance_row, sku_id=core_sku_id
                    )
            except Exception:
                raw_payload = dict(getattr(finance_row, "payload", None) or {})
                safe_payload: dict[str, Any] = {}
                for payload_key, payload_value in raw_payload.items():
                    if payload_value in (None, "", False):
                        continue
                    if isinstance(payload_value, (int, float, Decimal)):
                        try:
                            Decimal(str(payload_value or 0))
                        except Exception:
                            continue
                    safe_payload[payload_key] = payload_value
                safe_values = {
                    key: value
                    for key, value in vars(finance_row).items()
                    if key not in {"_sa_instance_state", "payload"}
                }
                safe_values["payload"] = safe_payload
                safe_row = SimpleNamespace(**safe_values)
                try:
                    details = MartService._finance_expense_details(
                        safe_row,
                        sku_id=core_sku_id,
                        timezone_name=timezone_name,
                    )
                except TypeError:
                    details = MartService._finance_expense_details(
                        safe_row, sku_id=core_sku_id
                    )
            for entry in details.get("entries", []):
                entry_category = str(entry.get("expense_category") or "")
                if categories is not None and entry_category not in categories:
                    continue
                if entry_category == EXPENSE_CATEGORY_UNCLASSIFIED and str(
                    entry.get("source_field") or ""
                ).startswith("payload."):
                    continue
                item = dict(entry)
                item["vendor_code"] = finance_row.vendor_code or core_vendor_code
                item["nm_id"] = finance_row.nm_id
                item["barcode"] = finance_barcode
                item["seller_oper_name"] = finance_row.seller_oper_name
                item["bonus_type_name"] = finance_row.bonus_type_name
                item["srid"] = finance_row.srid
                item["order_id"] = finance_row.order_id
                item["report_id"] = finance_row.report_id
                item["rrd_id"] = finance_row.rrd_id
                item["raw_payload"] = getattr(finance_row, "payload", None) or {}
                entries.append(item)
        return entries

    @classmethod
    def _raw_finance_totals_from_entries(
        cls, entries: list[dict[str, Any]]
    ) -> dict[str, Decimal]:
        totals = {
            "total_wb_expenses": Decimal("0"),
            "total_ad_expenses": Decimal("0"),
            "logistics_total": Decimal("0"),
        }
        for entry in entries:
            category = str(entry.get("expense_category") or "")
            amount = cls._decimal(MartService._entry_signed_amount(entry))
            if category == EXPENSE_CATEGORY_MARKETING_DEDUCTION:
                totals["total_ad_expenses"] += amount
                continue
            if category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT:
                continue
            totals["total_wb_expenses"] += amount
            if category in {
                EXPENSE_CATEGORY_WB_LOGISTICS,
                EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
            }:
                totals["logistics_total"] += amount
        return totals

    @classmethod
    def _raw_finance_category_totals(
        cls, entries: list[dict[str, Any]]
    ) -> dict[str, Decimal]:
        totals = {
            EXPENSE_CATEGORY_WB_COMMISSION: Decimal("0"),
            EXPENSE_CATEGORY_PAYMENT_PROCESSING: Decimal("0"),
            EXPENSE_CATEGORY_PVZ_REWARD: Decimal("0"),
            EXPENSE_CATEGORY_WB_LOGISTICS: Decimal("0"),
            EXPENSE_CATEGORY_WB_LOGISTICS_REBILL: Decimal("0"),
            EXPENSE_CATEGORY_STORAGE: Decimal("0"),
            EXPENSE_CATEGORY_ACCEPTANCE: Decimal("0"),
            EXPENSE_CATEGORY_PENALTY: Decimal("0"),
            EXPENSE_CATEGORY_DEDUCTION: Decimal("0"),
            EXPENSE_CATEGORY_MARKETING_DEDUCTION: Decimal("0"),
            EXPENSE_CATEGORY_LOYALTY: Decimal("0"),
            EXPENSE_CATEGORY_UNCLASSIFIED: Decimal("0"),
            EXPENSE_CATEGORY_ADDITIONAL_PAYMENT: Decimal("0"),
        }
        for entry in entries:
            category = str(entry.get("expense_category") or "")
            if category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT:
                raw_amount = cls._decimal(entry.get("amount"))
                if (
                    str(entry.get("amount_sign") or "") == EXPENSE_SIGN_INCOME
                    and raw_amount > 0
                ):
                    totals[EXPENSE_CATEGORY_ADDITIONAL_PAYMENT] += raw_amount
                continue
            if category not in totals:
                continue
            totals[category] += cls._decimal(MartService._entry_signed_amount(entry))
        return totals

    def _synthesized_account_expense_rows_from_raw_entries(
        self,
        *,
        account_id: int,
        entries: list[dict[str, Any]],
    ) -> list[Any]:
        buckets: dict[date, dict[str, Any]] = {}

        def get_bucket(stat_date: date) -> dict[str, Any]:
            bucket = buckets.get(stat_date)
            if bucket is None:
                bucket = {
                    "account_id": account_id,
                    "stat_date": stat_date,
                    "source_rows": 0,
                    "wb_commission": Decimal("0"),
                    "payment_processing": Decimal("0"),
                    "pvz_reward": Decimal("0"),
                    "wb_logistics": Decimal("0"),
                    "wb_logistics_rebill": Decimal("0"),
                    "acceptance": Decimal("0"),
                    "penalty": Decimal("0"),
                    "deduction": Decimal("0"),
                    "marketing_deduction": Decimal("0"),
                    "loyalty": Decimal("0"),
                    "other_wb_expenses": Decimal("0"),
                    "total_wb_expenses": Decimal("0"),
                    "commission": Decimal("0"),
                    "acquiring_fee": Decimal("0"),
                    "logistics": Decimal("0"),
                    "paid_acceptance": Decimal("0"),
                    "storage": Decimal("0"),
                    "penalties": Decimal("0"),
                    "deductions": Decimal("0"),
                    "additional_payments": Decimal("0"),
                    "ad_spend_operational": Decimal("0"),
                    "ad_spend_finance": Decimal("0"),
                    "ad_spend_final": Decimal("0"),
                    "ad_spend_source": AD_SPEND_SOURCE_NONE,
                    "ad_spend_delta": Decimal("0"),
                    "seller_cogs": Decimal("0"),
                    "seller_other_expense": Decimal("0"),
                    "total_seller_expenses": Decimal("0"),
                    "net_profit_after_all_expenses": Decimal("0"),
                    "total_expense": Decimal("0"),
                    "payload": {"source": "raw_finance_fallback"},
                }
                buckets[stat_date] = bucket
            return bucket

        for entry in entries:
            stat_date = entry.get("stat_date")
            if stat_date is None:
                continue
            bucket = get_bucket(stat_date)
            bucket["source_rows"] += 1
            category = str(entry.get("expense_category") or "")
            signed_amount = self._decimal(MartService._entry_signed_amount(entry))
            if category in bucket:
                bucket[category] += signed_amount
            elif category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT:
                raw_amount = self._decimal(entry.get("amount"))
                if (
                    str(entry.get("amount_sign") or "") == EXPENSE_SIGN_INCOME
                    and raw_amount > 0
                ):
                    bucket["additional_payments"] += raw_amount
            elif category == EXPENSE_CATEGORY_UNCLASSIFIED:
                bucket["other_wb_expenses"] += signed_amount

        rows: list[Any] = []
        for stat_date in sorted(buckets.keys()):
            bucket = buckets[stat_date]
            bucket["ad_spend_finance"] = self._decimal(bucket["marketing_deduction"])
            bucket["total_wb_expenses"] = normalized_wb_expenses_total(
                SimpleNamespace(**bucket)
            )
            MartService._apply_compatibility_expense_fields(bucket)
            bucket["ad_spend_final"] = self._decimal(bucket["ad_spend_finance"])
            bucket["ad_spend_source"] = (
                AD_SPEND_SOURCE_FINANCE
                if self._decimal(bucket["ad_spend_finance"]) > 0
                else AD_SPEND_SOURCE_NONE
            )
            bucket["ad_spend_delta"] = Decimal("0") - self._decimal(
                bucket["ad_spend_finance"]
            )
            bucket["total_expense"] = self._decimal(bucket["total_wb_expenses"])
            rows.append(SimpleNamespace(**bucket))
        return rows

    @staticmethod
    def _sku_daily_base_filters(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[Any]:
        return [
            MartSKUDaily.account_id == account_id,
            MartSKUDaily.stat_date >= date_from,
            MartSKUDaily.stat_date <= date_to,
        ]

    @classmethod
    def _account_level_expense_category_amounts(
        cls, row: Any
    ) -> list[tuple[str, Decimal]]:
        return [
            (
                EXPENSE_CATEGORY_WB_COMMISSION,
                cls._expense_value(row, EXPENSE_CATEGORY_WB_COMMISSION, "commission"),
            ),
            (
                EXPENSE_CATEGORY_PAYMENT_PROCESSING,
                cls._expense_value(
                    row, EXPENSE_CATEGORY_PAYMENT_PROCESSING, "acquiring_fee"
                ),
            ),
            (
                EXPENSE_CATEGORY_PVZ_REWARD,
                cls._expense_value(row, EXPENSE_CATEGORY_PVZ_REWARD),
            ),
            (
                EXPENSE_CATEGORY_WB_LOGISTICS,
                cls._expense_value(row, EXPENSE_CATEGORY_WB_LOGISTICS, "logistics"),
            ),
            (
                EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
                cls._expense_value(row, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL),
            ),
            (
                EXPENSE_CATEGORY_STORAGE,
                cls._expense_value(row, EXPENSE_CATEGORY_STORAGE, "storage"),
            ),
            (
                EXPENSE_CATEGORY_ACCEPTANCE,
                cls._expense_value(row, EXPENSE_CATEGORY_ACCEPTANCE, "paid_acceptance"),
            ),
            (
                EXPENSE_CATEGORY_PENALTY,
                cls._expense_value(row, EXPENSE_CATEGORY_PENALTY, "penalties"),
            ),
            (
                EXPENSE_CATEGORY_DEDUCTION,
                cls._expense_value(row, EXPENSE_CATEGORY_DEDUCTION, "deductions"),
            ),
            (
                EXPENSE_CATEGORY_MARKETING_DEDUCTION,
                cls._expense_value(row, EXPENSE_CATEGORY_MARKETING_DEDUCTION),
            ),
            (
                EXPENSE_CATEGORY_LOYALTY,
                cls._expense_value(row, EXPENSE_CATEGORY_LOYALTY),
            ),
            (
                EXPENSE_CATEGORY_UNCLASSIFIED,
                cls._expense_value(row, "other_wb_expenses"),
            ),
        ]

    @classmethod
    def _wb_total_from_category_totals(cls, totals: dict[str, Decimal]) -> Decimal:
        return (
            cls._decimal(totals.get(EXPENSE_CATEGORY_WB_COMMISSION))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_PAYMENT_PROCESSING))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_PVZ_REWARD))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_WB_LOGISTICS))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_WB_LOGISTICS_REBILL))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_STORAGE))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_ACCEPTANCE))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_PENALTY))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_DEDUCTION))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_LOYALTY))
            + cls._decimal(totals.get(EXPENSE_CATEGORY_UNCLASSIFIED))
        )

    @classmethod
    def _logistics_total_from_category_totals(
        cls, totals: dict[str, Decimal]
    ) -> Decimal:
        return cls._decimal(totals.get(EXPENSE_CATEGORY_WB_LOGISTICS)) + cls._decimal(
            totals.get(EXPENSE_CATEGORY_WB_LOGISTICS_REBILL)
        )

    @classmethod
    def _account_level_logistics_total_from_rows(cls, rows: list[Any]) -> Decimal:
        return sum(
            (
                cls._expense_value(row, EXPENSE_CATEGORY_WB_LOGISTICS, "logistics")
                + cls._expense_value(row, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL)
                for row in rows
            ),
            start=Decimal("0"),
        )

    @classmethod
    def _account_level_wb_expense_total(cls, row: Any) -> Decimal:
        explicit_total = cls._decimal(getattr(row, "total_wb_expenses", None))
        legacy_total = cls._decimal(getattr(row, "total_expense", None))
        if (
            explicit_total == 0
            and legacy_total > 0
            and cls._account_level_finance_ad_total(row) <= 0
        ):
            explicit_total = legacy_total
        if explicit_total == 0:
            explicit_total = sum(
                (
                    amount
                    for _, amount in cls._account_level_expense_category_amounts(row)
                    if _ != EXPENSE_CATEGORY_MARKETING_DEDUCTION
                ),
                start=Decimal("0"),
            )
        return explicit_total

    @classmethod
    def _account_level_finance_ad_total(cls, row: Any) -> Decimal:
        explicit_total = cls._decimal(getattr(row, "ad_spend_finance", None))
        if explicit_total != 0:
            return explicit_total
        return cls._expense_value(row, EXPENSE_CATEGORY_MARKETING_DEDUCTION)

    @classmethod
    def _account_level_expense_total_with_finance_ads(cls, row: Any) -> Decimal:
        return cls._account_level_wb_expense_total(
            row
        ) + cls._account_level_finance_ad_total(row)

    def _finance_category_totals_from_rows(
        self,
        *,
        profit_rows: list[Any],
        account_expense_rows: list[Any],
    ) -> dict[str, Decimal]:
        totals = {
            EXPENSE_CATEGORY_WB_COMMISSION: Decimal("0"),
            EXPENSE_CATEGORY_PAYMENT_PROCESSING: Decimal("0"),
            EXPENSE_CATEGORY_PVZ_REWARD: Decimal("0"),
            EXPENSE_CATEGORY_WB_LOGISTICS: Decimal("0"),
            EXPENSE_CATEGORY_WB_LOGISTICS_REBILL: Decimal("0"),
            EXPENSE_CATEGORY_STORAGE: Decimal("0"),
            EXPENSE_CATEGORY_ACCEPTANCE: Decimal("0"),
            EXPENSE_CATEGORY_PENALTY: Decimal("0"),
            EXPENSE_CATEGORY_DEDUCTION: Decimal("0"),
            EXPENSE_CATEGORY_MARKETING_DEDUCTION: Decimal("0"),
            EXPENSE_CATEGORY_LOYALTY: Decimal("0"),
            EXPENSE_CATEGORY_UNCLASSIFIED: Decimal("0"),
            EXPENSE_CATEGORY_ADDITIONAL_PAYMENT: Decimal("0"),
        }
        row_groups = (profit_rows, account_expense_rows)
        for rows in row_groups:
            for row in rows:
                totals[EXPENSE_CATEGORY_WB_COMMISSION] += self._expense_value(
                    row, EXPENSE_CATEGORY_WB_COMMISSION, "commission"
                )
                totals[EXPENSE_CATEGORY_PAYMENT_PROCESSING] += self._expense_value(
                    row, EXPENSE_CATEGORY_PAYMENT_PROCESSING, "acquiring_fee"
                )
                totals[EXPENSE_CATEGORY_PVZ_REWARD] += self._expense_value(
                    row, EXPENSE_CATEGORY_PVZ_REWARD
                )
                totals[EXPENSE_CATEGORY_WB_LOGISTICS] += self._expense_value(
                    row, EXPENSE_CATEGORY_WB_LOGISTICS, "logistics"
                )
                totals[EXPENSE_CATEGORY_WB_LOGISTICS_REBILL] += self._expense_value(
                    row, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL
                )
                totals[EXPENSE_CATEGORY_STORAGE] += self._expense_value(
                    row, EXPENSE_CATEGORY_STORAGE, "storage"
                )
                totals[EXPENSE_CATEGORY_ACCEPTANCE] += self._expense_value(
                    row, EXPENSE_CATEGORY_ACCEPTANCE, "paid_acceptance"
                )
                totals[EXPENSE_CATEGORY_PENALTY] += self._expense_value(
                    row, EXPENSE_CATEGORY_PENALTY, "penalties"
                )
                totals[EXPENSE_CATEGORY_DEDUCTION] += self._expense_value(
                    row, EXPENSE_CATEGORY_DEDUCTION
                )
                totals[EXPENSE_CATEGORY_MARKETING_DEDUCTION] += self._expense_value(
                    row, EXPENSE_CATEGORY_MARKETING_DEDUCTION
                )
                totals[EXPENSE_CATEGORY_LOYALTY] += self._expense_value(
                    row, EXPENSE_CATEGORY_LOYALTY
                )
                totals[EXPENSE_CATEGORY_UNCLASSIFIED] += self._expense_value(
                    row, "other_wb_expenses"
                )
                totals[EXPENSE_CATEGORY_ADDITIONAL_PAYMENT] += (
                    expense_additional_income(row)
                )
        return totals

    async def _summary_finance_category_totals(
        self,
        session: AsyncSession | None,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        profit_rows: list[Any],
        account_expense_rows: list[Any],
    ) -> dict[str, Decimal]:
        totals = self._finance_category_totals_from_rows(
            profit_rows=profit_rows,
            account_expense_rows=account_expense_rows,
        )
        mart_has_non_zero_finance_totals = any(
            amount != 0
            for category, amount in totals.items()
            if category != EXPENSE_CATEGORY_UNCLASSIFIED
        )
        if session is None:
            return totals
        if mart_has_non_zero_finance_totals:
            return totals
        raw_entries = await self._raw_finance_expense_entries(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        raw_totals = self._raw_finance_category_totals(raw_entries)
        raw_wb_total = self._wb_total_from_category_totals(raw_totals)
        raw_finance_total = raw_wb_total + self._decimal(
            raw_totals.get(EXPENSE_CATEGORY_MARKETING_DEDUCTION)
        )
        mart_wb_total = self._wb_total_from_category_totals(totals)
        mart_finance_total = mart_wb_total + self._decimal(
            totals.get(EXPENSE_CATEGORY_MARKETING_DEDUCTION)
        )
        raw_logistics_total = self._logistics_total_from_category_totals(raw_totals)
        mart_logistics_total = self._logistics_total_from_category_totals(totals)
        raw_is_materially_fresher = (
            raw_entries
            and raw_wb_total > 0
            and (
                not mart_has_non_zero_finance_totals
                or abs(raw_finance_total - mart_finance_total) > Decimal("1")
                or abs(raw_logistics_total - mart_logistics_total) > Decimal("1")
            )
        )
        if raw_is_materially_fresher:
            for category in raw_totals:
                totals[category] = raw_totals[category]
        return totals

    async def _expense_totals(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        include_unallocated: bool,
    ) -> dict[str, Decimal]:
        signed_amount = self._expense_signed_amount_expr()
        finance_filters = self._expense_base_filters(
            account_id=account_id, date_from=date_from, date_to=date_to
        )
        if not include_unallocated:
            finance_filters.append(MartExpenseDaily.is_allocated_to_sku.is_(True))
        finance_totals_stmt = select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            MartExpenseDaily.expense_category.notin_(
                                [
                                    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
                                    EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
                                ]
                            ),
                            signed_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            MartExpenseDaily.expense_category
                            == EXPENSE_CATEGORY_MARKETING_DEDUCTION,
                            signed_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            MartExpenseDaily.expense_category
                            == EXPENSE_CATEGORY_WB_LOGISTICS,
                            signed_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            MartExpenseDaily.expense_category
                            == EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
                            signed_amount,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(*finance_filters)
        (
            finance_total,
            finance_ad_total,
            wb_logistics_total,
            wb_logistics_rebill_total,
        ) = (await session.execute(finance_totals_stmt)).one()

        account_total = Decimal("0")
        account_ad_total = Decimal("0")
        account_wb_logistics_total = Decimal("0")
        account_wb_logistics_rebill_total = Decimal("0")
        if include_unallocated:
            account_totals_stmt = select(
                func.coalesce(func.sum(MartAccountExpenseDaily.total_wb_expenses), 0),
                func.coalesce(func.sum(MartAccountExpenseDaily.ad_spend_finance), 0),
                func.coalesce(func.sum(MartAccountExpenseDaily.wb_logistics), 0),
                func.coalesce(func.sum(MartAccountExpenseDaily.wb_logistics_rebill), 0),
            ).where(
                *self._account_expense_base_filters(
                    account_id=account_id, date_from=date_from, date_to=date_to
                )
            )
            (
                account_total,
                account_ad_total,
                account_wb_logistics_total,
                account_wb_logistics_rebill_total,
            ) = (await session.execute(account_totals_stmt)).one()

        sku_totals_stmt = select(
            func.coalesce(func.sum(MartSKUDaily.seller_cogs), 0),
            func.coalesce(func.sum(MartSKUDaily.seller_other_expense), 0),
            func.coalesce(func.sum(self._sku_extra_ad_expr()), 0),
        ).where(
            *self._sku_daily_base_filters(
                account_id=account_id, date_from=date_from, date_to=date_to
            )
        )
        seller_cogs_total, seller_other_total, ads_total = (
            await session.execute(sku_totals_stmt)
        ).one()

        row_level_wb_expenses = self._decimal(finance_total)
        row_level_ad_expenses = self._decimal(finance_ad_total)
        account_level_wb_expenses = self._decimal(account_total)
        account_level_ad_expenses = self._decimal(account_ad_total)
        use_account_level_finance = (
            include_unallocated
            and (account_level_wb_expenses + account_level_ad_expenses) > Decimal("0")
            and (row_level_wb_expenses + row_level_ad_expenses)
            < (account_level_wb_expenses + account_level_ad_expenses)
        )

        finance_mode = "account_level" if use_account_level_finance else "row_level"
        selected_finance_wb_expenses = (
            account_level_wb_expenses
            if use_account_level_finance
            else row_level_wb_expenses
        )
        selected_finance_ad_expenses = (
            account_level_ad_expenses
            if use_account_level_finance
            else row_level_ad_expenses
        )
        selected_wb_logistics = (
            self._decimal(account_wb_logistics_total)
            if use_account_level_finance
            else self._decimal(wb_logistics_total)
        )
        selected_wb_logistics_rebill = (
            self._decimal(account_wb_logistics_rebill_total)
            if use_account_level_finance
            else self._decimal(wb_logistics_rebill_total)
        )

        if include_unallocated and (
            (selected_finance_wb_expenses + selected_finance_ad_expenses)
            == Decimal("0")
            or (selected_wb_logistics + selected_wb_logistics_rebill) == Decimal("0")
        ):
            raw_entries = await self._raw_finance_expense_entries(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
            )
            raw_totals = self._raw_finance_totals_from_entries(raw_entries)
            raw_total = (
                raw_totals["total_wb_expenses"] + raw_totals["total_ad_expenses"]
            )
            selected_total = selected_finance_wb_expenses + selected_finance_ad_expenses
            raw_logistics_total = raw_totals["logistics_total"]
            selected_logistics_total = (
                selected_wb_logistics + selected_wb_logistics_rebill
            )
            should_use_raw = (
                selected_total == Decimal("0")
                or (
                    selected_logistics_total == Decimal("0")
                    and selected_total < Decimal("1")
                )
                or raw_total > selected_total
                or raw_logistics_total > selected_logistics_total
            )
            if should_use_raw:
                finance_mode = "raw_finance"
                selected_finance_wb_expenses = raw_totals["total_wb_expenses"]
                selected_finance_ad_expenses = raw_totals["total_ad_expenses"]
                selected_wb_logistics = raw_totals["logistics_total"]
                selected_wb_logistics_rebill = Decimal("0")

        total_wb_expenses = selected_finance_wb_expenses
        total_seller_expenses = self._decimal(seller_cogs_total) + self._decimal(
            seller_other_total
        )
        total_ad_expenses = selected_finance_ad_expenses + self._decimal(ads_total)
        logistics_total = selected_wb_logistics + selected_wb_logistics_rebill
        total_expenses = total_wb_expenses + total_seller_expenses + total_ad_expenses
        return {
            "total_expenses": total_expenses,
            "total_wb_expenses": total_wb_expenses,
            "total_seller_expenses": total_seller_expenses,
            "total_ad_expenses": total_ad_expenses,
            "logistics_total": logistics_total,
            "finance_ad_expenses": selected_finance_ad_expenses,
            "finance_mode": finance_mode,
        }

    @staticmethod
    def _merge_expense_bucket(
        buckets: dict[str, dict[str, Any]],
        *,
        bucket_key: str,
        amount: Decimal,
        source: str | None = None,
        category: str | None = None,
        label: str | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        stat_date: date | None = None,
        row_count: int = 0,
    ) -> None:
        bucket = buckets.setdefault(
            bucket_key,
            {
                "amount": Decimal("0"),
                "sources": set(),
                "category": category,
                "label": label or "",
                "sku_id": sku_id,
                "nm_id": nm_id,
                "vendor_code": vendor_code,
                "barcode": barcode,
                "stat_date": stat_date,
                "row_count": 0,
            },
        )
        bucket["amount"] = Decimal(str(bucket["amount"])) + amount
        if source:
            cast_sources = bucket["sources"]
            if isinstance(cast_sources, set):
                cast_sources.add(source)
        if category and not bucket.get("category"):
            bucket["category"] = category
        if label and not bucket.get("label"):
            bucket["label"] = label
        if sku_id is not None and bucket.get("sku_id") is None:
            bucket["sku_id"] = sku_id
        if nm_id is not None and bucket.get("nm_id") is None:
            bucket["nm_id"] = nm_id
        if vendor_code and not bucket.get("vendor_code"):
            bucket["vendor_code"] = vendor_code
        if barcode and not bucket.get("barcode"):
            bucket["barcode"] = barcode
        if stat_date and not bucket.get("stat_date"):
            bucket["stat_date"] = stat_date
        bucket["row_count"] = int(bucket.get("row_count", 0)) + row_count

    def _expense_breakdown_items_from_buckets(
        self,
        *,
        buckets: dict[str, dict[str, Any]],
        total_expenses: Decimal,
        group_by: str,
    ) -> list[ExpenseBreakdownItemRead]:
        items: list[ExpenseBreakdownItemRead] = []
        for bucket_key, payload in buckets.items():
            amount = self._decimal(payload.get("amount"))
            if amount == 0:
                continue
            sources = payload.get("sources") or set()
            source = None
            if isinstance(sources, set) and sources:
                source = next(iter(sources)) if len(sources) == 1 else "mixed"
            label = str(payload.get("label") or "")
            if not label:
                if group_by == "source":
                    label = self._expense_source_label(source)
                elif group_by == "day" and payload.get("stat_date") is not None:
                    label = str(payload["stat_date"])
                elif group_by == "sku":
                    label = str(
                        payload.get("vendor_code")
                        or f"SKU {payload.get('sku_id') or 'unallocated'}"
                    )
                elif group_by == "nm":
                    label = str(payload.get("nm_id") or "Не распределено по nmId")
                else:
                    label = self._expense_category_label(payload.get("category"))
            items.append(
                ExpenseBreakdownItemRead(
                    group_key=bucket_key,
                    label=label,
                    amount=self._float0(amount),
                    share_percent=self._percent0(amount, total_expenses)
                    if total_expenses > 0
                    else 0.0,
                    category=payload.get("category"),
                    source=source,
                    is_final=self._expense_is_final(
                        category=payload.get("category"), source=source
                    ),
                    sku_id=payload.get("sku_id"),
                    nm_id=payload.get("nm_id"),
                    vendor_code=payload.get("vendor_code"),
                    barcode=payload.get("barcode"),
                    stat_date=payload.get("stat_date"),
                    row_count=int(payload.get("row_count", 0)),
                )
            )
        if group_by == "category":
            items.sort(key=self._expense_breakdown_sort_key)
        else:
            items.sort(
                key=lambda item: (
                    -float(item.amount or 0),
                    item.label or item.group_key,
                )
            )
        return items

    @staticmethod
    def _trim_expense_items(
        items: list[ExpenseBreakdownItemRead], *, top_n: int | None
    ) -> list[ExpenseBreakdownItemRead]:
        if top_n is None or top_n <= 0 or len(items) <= top_n:
            return items
        return items[:top_n]

    @classmethod
    def _row_ad_components(
        cls, row: Any, *, fallback_source: Decimal | None = None
    ) -> dict[str, Decimal | str]:
        ad_source = str(getattr(row, "ad_spend_source", "") or "")
        ad_finance = cls._decimal(getattr(row, "ad_spend_finance", None))
        ad_operational = cls._decimal(getattr(row, "ad_spend_operational", None))
        ad_final = cls._decimal(getattr(row, "ad_spend_final", None))
        if ad_source == AD_SPEND_SOURCE_FINANCE or ad_finance > 0:
            final_spend = ad_final if ad_final > 0 else ad_finance
            return {
                "ad_spend_operational": ad_operational,
                "ad_spend_finance": ad_finance if ad_finance > 0 else final_spend,
                "ad_spend_final": final_spend,
                "ad_spend_source": AD_SPEND_SOURCE_FINANCE,
                "ad_spend_delta": cls._decimal(getattr(row, "ad_spend_delta", None))
                if getattr(row, "ad_spend_delta", None) is not None
                else ad_operational - ad_finance,
            }
        if (
            ad_source == AD_SPEND_SOURCE_OPERATIONAL
            or ad_operational > 0
            or ad_final > 0
        ):
            final_spend = (
                ad_final
                if ad_final > 0
                else ad_operational
                if ad_operational > 0
                else cls._decimal(getattr(row, "ad_spend", None))
            )
            return {
                "ad_spend_operational": ad_operational
                if ad_operational > 0
                else final_spend,
                "ad_spend_finance": Decimal("0"),
                "ad_spend_final": final_spend,
                "ad_spend_source": AD_SPEND_SOURCE_OPERATIONAL,
                "ad_spend_delta": cls._decimal(getattr(row, "ad_spend_delta", None))
                if getattr(row, "ad_spend_delta", None) is not None
                else final_spend,
            }
        final_spend = cls._decimal(getattr(row, "ad_spend", None))
        operational = (
            cls._decimal(fallback_source)
            if fallback_source is not None
            else cls._decimal(getattr(row, "source_ad_spend", None))
        )
        if final_spend > 0:
            return {
                "ad_spend_operational": operational if operational > 0 else final_spend,
                "ad_spend_finance": Decimal("0"),
                "ad_spend_final": final_spend,
                "ad_spend_source": AD_SPEND_SOURCE_OPERATIONAL
                if final_spend > 0
                else AD_SPEND_SOURCE_NONE,
                "ad_spend_delta": final_spend,
            }
        return {
            "ad_spend_operational": Decimal("0"),
            "ad_spend_finance": Decimal("0"),
            "ad_spend_final": Decimal("0"),
            "ad_spend_source": AD_SPEND_SOURCE_NONE,
            "ad_spend_delta": Decimal("0"),
        }

    @staticmethod
    def _action_group_bucket(action: NextActionRead) -> str:
        if action.category == "finance_reconcile":
            return "finance_reconcile"
        if action.category == "data_fix":
            if action.priority == "critical" and action.linked_entity.get(
                "sku_id", 0
            ) in (0, None):
                return "global_blockers"
            return "data_fix"
        if action.category == "growth":
            return "growth"
        if action.category == "release_cash":
            return "release_cash"
        if action.category == "protect_revenue":
            return "protect_revenue"
        if action.category == "save_money":
            return "save_money"
        if action.action_type in {
            "LIQUIDATE_STOCK",
            "DO_NOT_REORDER",
            "AD_PAUSE_REVIEW",
            "PRICE_INCREASE_REVIEW",
        }:
            return "money_saving"
        return "watch"

    @staticmethod
    def _frontend_href(path: str, **params: object) -> str:
        clean = {
            key: value for key, value in params.items() if value not in (None, "", [])
        }
        if not clean:
            return path
        query = "&".join(f"{key}={value}" for key, value in clean.items())
        return f"{path}?{query}"

    @staticmethod
    def _finance_problem_group_key(code: str) -> str:
        normalized = str(code or "").lower()
        if any(
            token in normalized
            for token in (
                "reconciliation",
                "finance_without_sale",
                "sale_without_finance",
            )
        ):
            return "reconciliation"
        if any(
            token in normalized
            for token in ("cost", "cogs", "supplier", "manual_cost", "seller_other")
        ):
            return "cost"
        if any(token in normalized for token in ("margin", "profit", "loss", "roi")):
            return "margin_profit"
        if any(
            token in normalized
            for token in (
                "expense",
                "deduction",
                "commission",
                "logistics",
                "storage",
                "penalt",
            )
        ):
            return "expenses"
        if any(token in normalized for token in ("ads", "ad_", "advert")):
            return "ads"
        if any(token in normalized for token in ("document", "doc", "report")):
            return "documents"
        if any(
            token in normalized
            for token in ("data", "dq", "missing", "unmatched", "blocker", "blocking")
        ):
            return "data_blockers"
        return "system_checks"

    def _finance_problem_amount(
        self,
        code: str,
        *,
        kpis: MoneySummaryKpis,
        cost_coverage: CostCoverageBlock,
        finance_reconciliation: FinanceReconciliationBlock,
    ) -> float:
        normalized = str(code or "").lower()
        if any(
            token in normalized
            for token in (
                "reconciliation",
                "finance_without_sale",
                "sale_without_finance",
            )
        ):
            return abs(self._float0(finance_reconciliation.difference_amount))
        if any(token in normalized for token in ("cost", "supplier", "manual_cost")):
            return self._float0(cost_coverage.missing_cost_revenue)
        if "ads" in normalized:
            return self._float0(
                kpis.ads_unallocated_spend + kpis.ads_overallocated_spend
            )
        if any(token in normalized for token in ("expense", "deduction", "logistics")):
            return self._float0(kpis.unallocated_expenses)
        if any(token in normalized for token in ("profit", "loss", "margin")):
            return abs(min(0.0, self._float0(kpis.net_profit_after_all_expenses)))
        return 0.0

    @staticmethod
    def _finance_problem_impact_type(code: str, *, action_category: str = "") -> str:
        normalized = str(code or "").lower()
        category = str(action_category or "").lower()
        if category == "data_fix" or any(
            token in normalized
            for token in (
                "missing",
                "unmatched",
                "blocker",
                "blocking",
                "dq",
                "cost",
                "sync",
            )
        ):
            return "data_blocker"
        if category in {"growth", "save_money", "release_cash", "protect_revenue"}:
            return "expected_impact"
        if any(
            token in normalized
            for token in ("risk", "loss", "profit", "expense", "ads")
        ):
            return "probable_loss"
        return "expected_impact"

    def _finance_problem_links(
        self,
        *,
        code: str,
        action_id: int | None = None,
        nm_id: int | None = None,
        group_key: str | None = None,
    ) -> tuple[str, str, str | None]:
        action_center_href = self._frontend_href(
            "/action-center",
            action_id=action_id,
            problem_code=None if action_id else code,
            source_module="finance" if not action_id else None,
            nm_id=nm_id,
        )
        results_href = self._frontend_href(
            "/results",
            action_id=action_id,
            problem_code=None if action_id else code,
            source_module="finance" if not action_id else None,
            nm_id=nm_id,
        )
        data_fix_href = None
        if (
            group_key in {"data_blockers", "cost", "reconciliation", "expenses", "ads"}
            or self._finance_problem_impact_type(code) == "data_blocker"
        ):
            data_fix_href = self._frontend_href("/data-fix", code=code, nm_id=nm_id)
        return action_center_href, results_href, data_fix_href

    def _money_problem_item_from_risk(
        self,
        risk: RiskItem,
        *,
        meta: MoneyMeta,
        kpis: MoneySummaryKpis,
        cost_coverage: CostCoverageBlock,
        finance_reconciliation: FinanceReconciliationBlock,
    ) -> MoneyProblemActionItem:
        group_key = self._finance_problem_group_key(risk.code)
        action_center_href, results_href, data_fix_href = self._finance_problem_links(
            code=risk.code, group_key=group_key
        )
        amount = self._finance_problem_amount(
            risk.code,
            kpis=kpis,
            cost_coverage=cost_coverage,
            finance_reconciliation=finance_reconciliation,
        )
        return MoneyProblemActionItem(
            code=risk.code,
            title=risk.title,
            explanation=risk.business_impact,
            recommendation="Открыть источник проблемы, закрыть блокер и затем повторить проверку денег.",
            amount=amount,
            trust_state="data_blocked"
            if group_key in {"data_blockers", "cost", "reconciliation"}
            else meta.data_trust.trust_state,
            impact_type=self._finance_problem_impact_type(risk.code),
            evidence_ledger=risk.evidence_ledger,
            action_center_href=action_center_href,
            data_fix_href=data_fix_href,
            results_href=results_href,
            recheck_available=True,
            saved_money_claimed=False,
        )

    def _money_problem_item_from_action(
        self, action: NextActionRead, *, meta: MoneyMeta
    ) -> MoneyProblemActionItem:
        code = action.action_type
        group_key = self._finance_problem_group_key(code)
        nm_id = (
            action.affected_nm_ids[0]
            if action.affected_nm_ids
            else action.linked_entity.get("nm_id") or None
        )
        nm_id = int(nm_id) if nm_id not in (None, "", 0) else None
        action_center_href, results_href, data_fix_href = self._finance_problem_links(
            code=code,
            action_id=action.id or None,
            nm_id=nm_id,
            group_key=group_key,
        )
        recommendation = action.what_to_do or action.next_step
        if code in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}:
            recommendation = "Сверить исходные строки и запустить повторную синхронизацию; суммы отчета WB остаются read-only."
        return MoneyProblemActionItem(
            action_id=action.id or None,
            code=code,
            title=action.title,
            explanation=action.why or action.business_reason,
            recommendation=recommendation,
            amount=self._float0(action.expected_effect_amount),
            trust_state="confirmed"
            if action.financial_final
            else meta.data_trust.trust_state,
            impact_type=self._finance_problem_impact_type(
                code, action_category=action.category
            ),
            evidence_ledger=action.evidence_ledger,
            action_center_href=action_center_href,
            data_fix_href=data_fix_href,
            results_href=results_href,
            recheck_available=True,
            saved_money_claimed=False,
        )

    def _money_grouped_problems(
        self,
        *,
        meta: MoneyMeta,
        risks: list[RiskItem],
        actions: list[NextActionRead],
        kpis: MoneySummaryKpis,
        cost_coverage: CostCoverageBlock,
        finance_reconciliation: FinanceReconciliationBlock,
    ) -> MoneyProblemGroups:
        grouped: dict[str, list[MoneyProblemActionItem]] = {
            "reconciliation": [],
            "cost": [],
            "margin_profit": [],
            "expenses": [],
            "ads": [],
            "documents": [],
            "data_blockers": [],
            "system_checks": [],
        }
        if finance_reconciliation.status == "not_available":
            code = "finance_report_missing"
            action_center_href, results_href, data_fix_href = (
                self._finance_problem_links(code=code, group_key="reconciliation")
            )
            grouped["reconciliation"].append(
                MoneyProblemActionItem(
                    code=code,
                    title="Финансовая сверка не закрыта",
                    explanation="Отчет WB и операционные продажи пока не дают финальную прибыль без проверки.",
                    recommendation="Сверить исходные строки и запустить повторную синхронизацию; суммы отчета WB остаются read-only.",
                    amount=abs(self._float0(finance_reconciliation.difference_amount)),
                    trust_state="operational_provisional",
                    impact_type="data_blocker",
                    action_center_href=action_center_href,
                    data_fix_href=data_fix_href,
                    results_href=results_href,
                    recheck_available=True,
                    saved_money_claimed=False,
                )
            )
        for risk in risks:
            item = self._money_problem_item_from_risk(
                risk,
                meta=meta,
                kpis=kpis,
                cost_coverage=cost_coverage,
                finance_reconciliation=finance_reconciliation,
            )
            grouped[self._finance_problem_group_key(item.code)].append(item)
        for action in actions:
            item = self._money_problem_item_from_action(action, meta=meta)
            grouped[self._finance_problem_group_key(item.code)].append(item)
        return MoneyProblemGroups(**grouped)

    @staticmethod
    def _source_aliases() -> dict[str, set[str]]:
        return {
            "finance_reports_wb": {
                "finance",
                "finance_report",
                "finance_reports",
                "realization",
                "realization_reports",
            },
            "orders_sales": {
                "orders",
                "sales",
                "orders_sales",
                "sales_orders",
                "operational_sales",
            },
            "cost_price": {
                "cost",
                "costs",
                "manual_cost",
                "manual_costs",
                "cost_price",
            },
            "expenses": {
                "expenses",
                "expense",
                "finance",
                "finance_report",
                "finance_reports",
                "finance_expenses",
                "account_expenses",
            },
            "ads": {"ads", "advertising", "ad_stats", "campaigns"},
            "stocks": {"stocks", "stock", "warehouse_stocks"},
            "prices": {"prices", "price", "wb_prices"},
            "documents": {"documents", "docs", "wb_documents", "finance_documents"},
        }

    @staticmethod
    def _domain_last_synced_at(domain: Any | None) -> datetime | None:
        if domain is None:
            return None
        for attr in (
            "cursor_last_synced_at",
            "last_successful_at",
            "latest_finished_at",
        ):
            value = getattr(domain, attr, None)
            if value is not None:
                return value
        return None

    def _coverage_domain_for_source(self, health: Any, source: str) -> Any | None:
        aliases = self._source_aliases().get(source, {source})
        for domain in getattr(health, "domains", []) or []:
            name = str(getattr(domain, "domain", "") or "").lower()
            if name in aliases or any(alias in name for alias in aliases):
                return domain
        return None

    @staticmethod
    def _source_action_hint(source: str, status: str, blocks: list[str]) -> str:
        if source == "cost_price" and blocks:
            return "Open Costs/Data Fix and upload or confirm supplier cost rows."
        if source == "finance_reports_wb" and blocks:
            return "Re-sync WB finance reports and review reconciliation rows."
        if source == "orders_sales" and blocks:
            return "Re-sync orders and sales before trusting provisional sales."
        if source == "expenses" and blocks:
            return "Review finance expense mapping and unallocated WB report rows."
        if source == "ads" and blocks:
            return "Review ads allocation and refresh profitability marts."
        if source == "stocks" and blocks:
            return "Re-sync stocks before using cash-in-stock or purchase decisions."
        if source == "prices" and blocks:
            return "Refresh prices before using price and margin actions."
        if source == "documents" and status == "not_configured":
            return "Connect documents when document-backed reconciliation is needed."
        if status == "fresh":
            return "Source is usable for the selected money calculation."
        return "Refresh or configure this source before treating affected metrics as final."

    def _source_blocks_calculation(
        self,
        source: str,
        *,
        status: str,
        health: Any,
        quality: MoneyQuality,
        cost_coverage: CostCoverageBlock,
    ) -> list[str]:
        if status == "fresh" and source not in {"cost_price", "ads", "expenses"}:
            return []
        blocked_reasons = set(getattr(health, "blocked_reasons", []) or [])
        blocks: list[str] = []
        if source == "finance_reports_wb":
            if status != "fresh":
                blocks.extend(
                    ["confirmed_money", "finance_reconciliation", "final_profit"]
                )
        elif source == "orders_sales":
            if status != "fresh":
                blocks.extend(["provisional_sales", "unit_economics"])
        elif source == "cost_price":
            if status != "fresh" or not cost_coverage.can_use_for_final_profit:
                blocks.extend(
                    ["cost_price", "unit_profit", "margin_pct", "final_profit"]
                )
        elif source == "expenses":
            if status != "fresh":
                blocks.extend(["net_profit", "unit_profit"])
        elif source == "ads":
            if (
                status != "fresh"
                or quality.ads_overallocated_spend > 0
                or (
                    quality.ads_allocation_percent_capped
                    and quality.ads_allocation_percent_capped < 95
                )
            ):
                blocks.extend(["profit_after_ads", "unit_profit"])
        elif source == "stocks":
            if status != "fresh" or "latest_stocks_not_completed" in blocked_reasons:
                blocks.extend(["blocked_cash", "purchase_recommendations"])
        elif source == "prices":
            if status != "fresh":
                blocks.extend(["price", "price_actions", "unit_economics"])
        elif source == "documents":
            if status not in {"fresh", "not_configured"}:
                blocks.append("document_evidence")
        return list(dict.fromkeys(blocks))

    def _coverage_status(
        self,
        *,
        source: str,
        domain: Any | None,
        has_data: bool,
        default_not_configured: bool = False,
        calculation_blocked: bool = False,
    ) -> str:
        if domain is not None:
            latest_status = str(getattr(domain, "latest_status", "") or "").lower()
            cursor_status = str(getattr(domain, "cursor_status", "") or "").lower()
            last_synced_at = self._domain_last_synced_at(domain)
            if latest_status in {
                "not_configured",
                "disabled",
                "skipped",
            } or cursor_status in {"not_configured", "disabled", "skipped"}:
                return "not_configured"
            if latest_status in {"failed", "error", "cancelled"} or cursor_status in {
                "failed",
                "error",
            }:
                return "stale" if last_synced_at or has_data else "missing"
            if (
                last_synced_at
                or latest_status in {"completed", "success", "ok", "finished"}
                or cursor_status in {"ok", "synced", "completed"}
            ):
                return "stale" if calculation_blocked else "fresh"
        if has_data:
            return "stale" if calculation_blocked else "fresh"
        if default_not_configured:
            return "not_configured"
        return "missing"

    def _money_source_coverage(
        self,
        *,
        state: MoneyRuntimeState,
        kpis: MoneySummaryKpis,
        quality: MoneyQuality,
        cost_coverage: CostCoverageBlock,
        finance_reconciliation: FinanceReconciliationBlock,
    ) -> list[MoneySourceCoverageItem]:
        health = state.health
        source_has_data = {
            "finance_reports_wb": bool(
                finance_reconciliation.closed_finance_date_to
                or finance_reconciliation.finance_confirmed_revenue > 0
            ),
            "orders_sales": bool(kpis.revenue > 0 or state.profit_rows),
            "cost_price": bool(
                cost_coverage.business_accepted_cost_coverage_percent > 0
                or cost_coverage.supplier_confirmed_cost_coverage_percent > 0
            ),
            "expenses": bool(kpis.wb_expenses_total > 0 or state.account_expense_rows),
            "ads": bool(kpis.ad_spend > 0 or kpis.ads_source_spend > 0),
            "stocks": bool(kpis.stock_value > 0 or state.control_rows),
            "prices": bool(state.price_rows),
            "documents": False,
        }
        calculation_blocked = {
            "finance_reports_wb": finance_reconciliation.status
            not in {"matched", "ok"},
            "orders_sales": "failed_sync_domains"
            in set(getattr(health, "blocked_reasons", []) or []),
            "cost_price": not cost_coverage.can_use_for_final_profit,
            "expenses": False,
            "ads": quality.ads_overallocated_spend > 0
            or (
                quality.ads_allocation_percent_capped
                and quality.ads_allocation_percent_capped < 95
            ),
            "stocks": "latest_stocks_not_completed"
            in set(getattr(health, "blocked_reasons", []) or []),
            "prices": not bool(state.price_rows),
            "documents": False,
        }
        coverage: list[MoneySourceCoverageItem] = []
        for source in self._source_aliases():
            domain = self._coverage_domain_for_source(health, source)
            status = self._coverage_status(
                source=source,
                domain=domain,
                has_data=source_has_data[source],
                default_not_configured=source in {"ads", "documents"}
                and not source_has_data[source]
                and domain is None,
                calculation_blocked=bool(calculation_blocked[source]),
            )
            blocks = self._source_blocks_calculation(
                source,
                status=status,
                health=health,
                quality=quality,
                cost_coverage=cost_coverage,
            )
            coverage.append(
                MoneySourceCoverageItem(
                    source=source,
                    status=status,
                    last_synced_at=self._domain_last_synced_at(domain),
                    blocks_calculation=blocks,
                    action_hint=self._source_action_hint(source, status, blocks),
                )
            )
        return coverage

    def _summary_unit_economics(
        self,
        *,
        kpis: MoneySummaryKpis,
        profit_rows: list[Any],
        meta: MoneyMeta,
        cost_coverage: CostCoverageBlock,
    ) -> MoneyUnitEconomicsRead:
        net_units = sum(
            (self._decimal(getattr(item, "net_units", None)) for item in profit_rows),
            start=Decimal("0"),
        )
        blockers: list[str] = []
        if net_units <= 0:
            blockers.append("net_units_missing")
        if not cost_coverage.can_use_for_operations:
            blockers.append("missing_cost")
        elif not cost_coverage.can_use_for_final_profit:
            blockers.append("supplier_cost_not_confirmed")

        def per_unit(value: float | Decimal) -> float | None:
            return (
                self._float0(self._decimal(value) / net_units)
                if net_units > 0
                else None
            )

        can_compute_profit = net_units > 0 and cost_coverage.can_use_for_operations
        return MoneyUnitEconomicsRead(
            price=per_unit(kpis.revenue),
            cost_price=per_unit(kpis.seller_cogs)
            if cost_coverage.can_use_for_operations
            else None,
            commission=per_unit(kpis.wb_commission),
            logistics=per_unit(kpis.wb_logistics + kpis.wb_logistics_rebill),
            ads=per_unit(kpis.ad_spend),
            other_expenses=per_unit(
                kpis.payment_processing
                + kpis.pvz_reward
                + kpis.storage
                + kpis.acceptance
                + kpis.penalty
                + kpis.deduction
                + kpis.loyalty
                + kpis.other_wb_expenses
                + kpis.seller_other_expense
                + kpis.unallocated_expenses
            ),
            unit_profit=per_unit(kpis.net_profit_after_all_expenses)
            if can_compute_profit
            else None,
            margin_pct=kpis.margin_after_overhead_percent
            if can_compute_profit
            else None,
            trust_state=meta.data_trust.trust_state,
            blockers=list(dict.fromkeys(blockers)),
        )

    def _card_unit_economics(
        self,
        *,
        profit_row: Any,
        row: Any,
        price_row: Any | None,
        revenue: Decimal,
        wb_expenses_total: Decimal,
        seller_cost_total: Decimal,
        ad_spend: Decimal,
        profit_after_source_ads: Decimal,
        allocated_overhead: Decimal,
    ) -> MoneyUnitEconomicsRead:
        net_units = self._decimal(getattr(profit_row, "net_units", None))
        blockers = list(
            dict.fromkeys(
                str(item)
                for item in list(getattr(row, "blocked_reasons", []) or [])
                if str(item)
            )
        )
        truth_level = str(getattr(profit_row, "cost_truth_level", "") or "")
        cost_ready = (
            truth_level not in {"", "missing"}
            and self._decimal(getattr(profit_row, "estimated_cogs", None)) > 0
        )
        if net_units <= 0:
            blockers.append("net_units_missing")
        if not cost_ready:
            blockers.append("missing_cost")
        elif not self._profit_row_cost_final_accepted(profit_row):
            blockers.append("supplier_cost_not_confirmed")

        def per_unit(value: Decimal | float | int) -> float | None:
            return (
                self._float0(self._decimal(value) / net_units)
                if net_units > 0
                else None
            )

        price_value = None
        if price_row is not None:
            price_value = self._float0(
                getattr(price_row, "current_discounted_price", None)
                or getattr(price_row, "current_price", None)
            )
        if not price_value:
            price_value = per_unit(revenue)
        logistics_total = self._decimal(
            getattr(profit_row, "logistics", None)
        ) + self._decimal(getattr(profit_row, "paid_acceptance", None))
        other_expenses_total = max(
            Decimal("0"),
            wb_expenses_total
            - self._decimal(getattr(profit_row, "commission", None))
            - logistics_total
            + self._decimal(getattr(profit_row, "seller_other_expense", None))
            + allocated_overhead,
        )
        can_compute_profit = net_units > 0 and cost_ready
        return MoneyUnitEconomicsRead(
            price=price_value,
            cost_price=per_unit(getattr(profit_row, "estimated_cogs", None))
            if cost_ready
            else None,
            commission=per_unit(getattr(profit_row, "commission", None)),
            logistics=per_unit(logistics_total),
            ads=per_unit(ad_spend),
            other_expenses=per_unit(other_expenses_total),
            unit_profit=per_unit(profit_after_source_ads - allocated_overhead)
            if can_compute_profit
            else None,
            margin_pct=self._percent0(
                profit_after_source_ads - allocated_overhead, revenue
            )
            if can_compute_profit
            else None,
            trust_state=str(getattr(row, "trust_state", "") or ""),
            blockers=list(dict.fromkeys(blockers)),
        )

    def _money_control_panel(
        self,
        *,
        state: MoneyRuntimeState,
        meta: MoneyMeta,
        revenue_sources: RevenueSources,
        finance_reconciliation: FinanceReconciliationBlock,
        cost_coverage: CostCoverageBlock,
        quality: MoneyQuality,
        kpis: MoneySummaryKpis,
        risks: list[RiskItem],
        actions: list[NextActionRead],
    ) -> MoneyControlPanel:
        currency = meta.currency
        trust_state = meta.data_trust.trust_state
        risk_amount = sum(
            self._finance_problem_amount(
                item.code,
                kpis=kpis,
                cost_coverage=cost_coverage,
                finance_reconciliation=finance_reconciliation,
            )
            for item in risks
        )
        if risk_amount <= 0 and kpis.net_profit_after_all_expenses < 0:
            risk_amount = abs(kpis.net_profit_after_all_expenses)
        calculation_blockers_amount = (
            self._float0(cost_coverage.missing_cost_revenue)
            + abs(self._float0(finance_reconciliation.difference_amount))
            + self._float0(kpis.ads_unallocated_spend + kpis.ads_overallocated_spend)
            + self._float0(kpis.unallocated_expenses)
        )
        growth_amount = sum(
            self._float0(action.expected_effect_amount)
            for action in actions
            if action.category
            in {"growth", "protect_revenue", "release_cash", "save_money"}
        )
        return MoneyControlPanel(
            confirmed_money=MoneyControlPanelCard(
                code="confirmed_money",
                title="Confirmed WB finance money",
                amount=self._float0(kpis.finance_confirmed_revenue),
                currency=currency,
                trust_state="financial_final"
                if finance_reconciliation.is_final
                else trust_state,
                impact_type="confirmed_money",
                saved_money_claimed=False,
            ),
            provisional_sales=MoneyControlPanelCard(
                code="provisional_sales",
                title="Operational sales not yet final",
                amount=self._float0(
                    revenue_sources.open_period_revenue
                    or max(kpis.revenue - kpis.finance_confirmed_revenue, 0.0)
                ),
                currency=currency,
                trust_state="operational_provisional",
                impact_type="provisional_money",
                saved_money_claimed=False,
            ),
            probable_risks=MoneyControlPanelCard(
                code="probable_risks",
                title="Probable financial risks",
                amount=self._float0(risk_amount),
                currency=currency,
                trust_state=trust_state,
                impact_type="probable_loss",
                saved_money_claimed=False,
            ),
            blocked_cash=MoneyControlPanelCard(
                code="blocked_cash",
                title="Cash blocked in stock",
                amount=self._float0(kpis.overstock_value + kpis.in_transit_value),
                currency=currency,
                trust_state=trust_state
                if kpis.stock_value_confidence != "low"
                else "operational_provisional",
                impact_type="blocked_cash",
                saved_money_claimed=False,
            ),
            calculation_blockers=MoneyControlPanelCard(
                code="calculation_blockers",
                title="Money blocked by calculation issues",
                amount=self._float0(calculation_blockers_amount),
                currency=currency,
                trust_state="data_blocked"
                if calculation_blockers_amount > 0
                else trust_state,
                impact_type="data_blocker"
                if calculation_blockers_amount > 0
                else "system_check",
                saved_money_claimed=False,
            ),
            growth_opportunities=MoneyControlPanelCard(
                code="growth_opportunities",
                title="Expected growth opportunities",
                amount=self._float0(growth_amount),
                currency=currency,
                trust_state="operational_provisional"
                if growth_amount > 0
                else trust_state,
                impact_type="expected_impact",
                saved_money_claimed=False,
            ),
            source_coverage=self._money_source_coverage(
                state=state,
                kpis=kpis,
                quality=quality,
                cost_coverage=cost_coverage,
                finance_reconciliation=finance_reconciliation,
            ),
            grouped_problems=self._money_grouped_problems(
                meta=meta,
                risks=risks,
                actions=actions,
                kpis=kpis,
                cost_coverage=cost_coverage,
                finance_reconciliation=finance_reconciliation,
            ),
            unit_economics=self._summary_unit_economics(
                kpis=kpis,
                profit_rows=state.profit_rows,
                meta=meta,
                cost_coverage=cost_coverage,
            ),
        )

    @staticmethod
    def _payload_number(payload: dict[str, Any], key: str) -> float:
        value = payload.get(key)
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _payload_int(payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _is_account_level_linked_entity(linked_entity: dict[str, Any] | None) -> bool:
        sku_id = (linked_entity or {}).get("sku_id")
        return sku_id in (None, 0, "")

    def _action_sort_key(self, action: Any) -> tuple[int, float]:
        return (
            self._priority_rank(action.priority),
            float(getattr(action, "expected_effect_amount", 0) or 0),
        )

    @staticmethod
    def _is_system_handled_action(action: Any) -> bool:
        action_type = str(getattr(action, "action_type", "") or "").strip().upper()
        category = str(getattr(action, "category", "") or "").strip().lower()
        return (
            action_type in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}
            or category == "finance_reconcile"
        )

    def _group_action_key(
        self, action: NextActionRead, *, group_by: str
    ) -> tuple[str, int]:
        linked_entity = action.linked_entity or {}
        if group_by == "article":
            entity_id = int(
                linked_entity.get("nm_id") or linked_entity.get("sku_id") or 0
            )
        else:
            entity_id = int(
                linked_entity.get("sku_id") or linked_entity.get("nm_id") or 0
            )
        return (action.action_type, entity_id)

    def _merge_grouped_actions(
        self, actions: list[NextActionRead], *, group_by: str
    ) -> tuple[list[NextActionRead], int]:
        if group_by == "sku":
            return list(actions), len(actions)
        grouped: dict[tuple[str, int], NextActionRead] = {}
        raw_total = len(actions)

        def merge_money_effect(
            left: dict[str, Any], right: dict[str, Any]
        ) -> dict[str, Any]:
            merged = dict(left or {})
            for key, value in dict(right or {}).items():
                if isinstance(value, (int, float)) and isinstance(
                    merged.get(key), (int, float)
                ):
                    merged[key] = float(merged.get(key) or 0) + float(value or 0)
                elif key not in merged:
                    merged[key] = value
            return merged

        def merge_int_lists(left: list[int], right: list[int]) -> list[int]:
            return list(dict.fromkeys([*list(left or []), *list(right or [])]))

        for action in actions:
            key = self._group_action_key(action, group_by=group_by)
            current = grouped.get(key)
            if current is None:
                grouped[key] = action.model_copy(deep=True)
                continue
            total_expected_effect = float(current.expected_effect_amount or 0) + float(
                action.expected_effect_amount or 0
            )
            total_required_cash = float(current.required_cash or 0) + float(
                action.required_cash or 0
            )
            total_recommended_qty = int(current.recommended_qty or 0) + int(
                action.recommended_qty or 0
            )
            total_current_stock = float(current.current_stock or 0) + float(
                action.current_stock or 0
            )
            merged_money_effect = merge_money_effect(
                current.money_effect, action.money_effect
            )
            affected_nm_ids = merge_int_lists(
                current.affected_nm_ids, action.affected_nm_ids
            )
            affected_sku_ids = merge_int_lists(
                current.affected_sku_ids, action.affected_sku_ids
            )
            financial_final = bool(current.financial_final and action.financial_final)
            if action.action_type == "LIQUIDATE_STOCK":
                affected = float(merged_money_effect.get("affected_stock_value") or 0)
                cash_release = float(
                    merged_money_effect.get("expected_cash_release") or 0
                )
                total_expected_effect = affected or total_expected_effect
                merged_money_effect["expected_cash_release"] = (
                    cash_release or total_expected_effect
                )
                merged_money_effect["affected_stock_value"] = (
                    affected or total_expected_effect
                )
                total_required_cash = 0.0
                total_recommended_qty = 0
            elif action.action_type == "REORDER":
                expected_profit = float(
                    merged_money_effect.get("expected_profit_impact")
                    or total_expected_effect
                )
                merged_money_effect["expected_profit_impact"] = expected_profit
                total_expected_effect = expected_profit
            elif action.action_type == "PROTECT_STOCK":
                protected_revenue = float(
                    merged_money_effect.get("protected_revenue")
                    or total_expected_effect
                )
                merged_money_effect["protected_revenue"] = protected_revenue
                total_expected_effect = protected_revenue
            if self._action_sort_key(action) > self._action_sort_key(current):
                grouped[key] = action.model_copy(
                    update={
                        "expected_effect_amount": total_expected_effect,
                        "required_cash": total_required_cash,
                        "recommended_qty": total_recommended_qty,
                        "current_stock": total_current_stock,
                        "money_effect": merged_money_effect,
                        "affected_nm_ids": affected_nm_ids,
                        "affected_sku_ids": affected_sku_ids,
                        "financial_final": financial_final,
                    },
                    deep=True,
                )
            else:
                current.expected_effect_amount = total_expected_effect
                current.required_cash = total_required_cash
                current.recommended_qty = total_recommended_qty
                current.current_stock = total_current_stock
                current.money_effect = merged_money_effect
                current.affected_nm_ids = affected_nm_ids
                current.affected_sku_ids = affected_sku_ids
                current.financial_final = financial_final
        grouped_actions = sorted(
            grouped.values(),
            key=lambda item: (
                self._priority_rank(item.priority),
                1 if self._is_account_level_linked_entity(item.linked_entity) else 0,
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        )
        return grouped_actions, raw_total

    def _stock_value_confidence(
        self, truth_level: str | None, *, business_trusted: bool
    ) -> tuple[str, str]:
        if truth_level == "supplier_confirmed" and business_trusted:
            return "high", ""
        if truth_level == "operator_baseline":
            return "medium", "estimated_from_operator_baseline_cost"
        if truth_level == "placeholder":
            return "low", "estimated_from_placeholder_cost"
        return "low", "stock_value_not_computable"

    def _unit_cost_from_profit_row(self, profit_row: Any) -> Decimal | None:
        estimated_cogs = self._decimal(getattr(profit_row, "estimated_cogs", None))
        net_units = int(getattr(profit_row, "net_units", 0) or 0)
        if estimated_cogs > 0 and net_units > 0:
            return estimated_cogs / Decimal(str(net_units))
        return None

    def _row_unit_cost(self, row: Any, profit_row: Any) -> Decimal | None:
        stock_qty = self._decimal(getattr(row, "stock_qty", None))
        stock_value = self._decimal(getattr(row, "stock_value", None))
        if stock_qty > 0 and stock_value > 0:
            return stock_value / stock_qty
        return self._unit_cost_from_profit_row(profit_row)

    def _stock_value_components(
        self,
        row: Any,
        profit_row: Any,
        purchase_row: Any | None,
        *,
        business_trusted: bool,
    ) -> dict[str, Any]:
        stock_qty = self._decimal(getattr(row, "stock_qty", None))
        unit_cost = self._row_unit_cost(row, profit_row)
        stock_value = (
            (stock_qty * unit_cost)
            if stock_qty > 0 and unit_cost is not None and unit_cost > 0
            else Decimal("0")
        )
        in_transit_qty = (
            self._decimal(getattr(purchase_row, "in_transit_qty", None))
            if purchase_row is not None
            else Decimal("0")
        )
        in_transit_value = (
            (in_transit_qty * unit_cost)
            if in_transit_qty > 0 and unit_cost is not None and unit_cost > 0
            else Decimal("0")
        )
        confidence, reason = self._stock_value_confidence(
            getattr(profit_row, "cost_truth_level", None),
            business_trusted=business_trusted,
        )
        if stock_value <= 0:
            reason = "stock_value_not_computable"
        return {
            "unit_cost": unit_cost,
            "stock_value": stock_value,
            "in_transit_value": in_transit_value,
            "stock_value_confidence": confidence if stock_value > 0 else "low",
            "stock_value_reason": reason,
        }

    def _article_metric_weights_by_sku(
        self,
        *,
        article_rows: list[tuple[Any, Any, Any | None]],
    ) -> dict[int, Decimal]:
        if not article_rows:
            return {}
        revenue_by_sku: dict[int, Decimal] = {}
        units_by_sku: dict[int, Decimal] = {}
        total_revenue = Decimal("0")
        total_units = Decimal("0")
        eligible_skus: list[int] = []
        for row, profit_row, _purchase in article_rows:
            if row.sku_id is None:
                continue
            sku_id = int(row.sku_id)
            eligible_skus.append(sku_id)
            revenue = compute_revenue_final(profit_row)
            units = Decimal(
                str(
                    self._int0(
                        getattr(profit_row, "net_units", None)
                        or getattr(profit_row, "gross_units", None)
                    )
                )
            )
            revenue_by_sku[sku_id] = revenue_by_sku.get(sku_id, Decimal("0")) + max(
                revenue, Decimal("0")
            )
            units_by_sku[sku_id] = units_by_sku.get(sku_id, Decimal("0")) + max(
                units, Decimal("0")
            )
            total_revenue += max(revenue, Decimal("0"))
            total_units += max(units, Decimal("0"))
        if not eligible_skus:
            return {}
        if total_revenue > 0:
            return {
                sku_id: revenue_by_sku.get(sku_id, Decimal("0")) / total_revenue
                for sku_id in eligible_skus
            }
        if total_units > 0:
            return {
                sku_id: units_by_sku.get(sku_id, Decimal("0")) / total_units
                for sku_id in eligible_skus
            }
        even_share = Decimal("1") / Decimal(str(len(eligible_skus)))
        return {sku_id: even_share for sku_id in eligible_skus}

    def _allocate_article_count_metric_by_sku(
        self,
        *,
        article_rows: list[tuple[Any, Any, Any | None]],
        total_value: int | None,
    ) -> dict[int, int]:
        total = max(int(total_value or 0), 0)
        if total <= 0:
            return {}
        weights = self._article_metric_weights_by_sku(article_rows=article_rows)
        if not weights:
            return {}
        raw_allocations = {
            sku_id: Decimal(str(total)) * weight for sku_id, weight in weights.items()
        }
        allocations = {sku_id: int(value) for sku_id, value in raw_allocations.items()}
        remainder = total - sum(allocations.values())
        if remainder > 0:
            ranked = sorted(
                (
                    (
                        raw_allocations[sku_id] - Decimal(str(allocations[sku_id])),
                        sku_id,
                    )
                    for sku_id in raw_allocations
                ),
                key=lambda item: (item[0], item[1]),
                reverse=True,
            )
            for _fraction, sku_id in ranked[:remainder]:
                allocations[sku_id] += 1
        return allocations

    def _article_ads_allocation_by_sku(
        self,
        *,
        article_rows: list[tuple[Any, Any, Any | None]],
        ads_source_spend: Decimal,
    ) -> dict[int, Decimal]:
        """Allocate full nm_id/article ad spend to SKU variants for UI and math.

        The article/nm_id owns the source spend. Variant rows receive only their
        proportional share, so the frontend does not display the full article spend
        multiple times on every size/barcode row.
        """
        if not article_rows or ads_source_spend <= 0:
            return {}
        total_revenue = sum(
            (
                compute_revenue_final(profit_row)
                for _row, profit_row, _purchase in article_rows
            ),
            start=Decimal("0"),
        )
        total_units = sum(
            (
                Decimal(
                    str(
                        self._int0(
                            getattr(profit_row, "net_units", None)
                            or getattr(profit_row, "gross_units", None)
                        )
                    )
                )
                for _row, profit_row, _purchase in article_rows
            ),
            start=Decimal("0"),
        )
        allocations: dict[int, Decimal] = {}
        count = len(article_rows)
        for row, profit_row, _purchase in article_rows:
            if row.sku_id is None:
                continue
            if total_revenue > 0:
                base = compute_revenue_final(profit_row)
                allocations[int(row.sku_id)] = (
                    ads_source_spend * base / total_revenue
                    if base > 0
                    else Decimal("0")
                )
            elif total_units > 0:
                units = Decimal(
                    str(
                        self._int0(
                            getattr(profit_row, "net_units", None)
                            or getattr(profit_row, "gross_units", None)
                        )
                    )
                )
                allocations[int(row.sku_id)] = (
                    ads_source_spend * units / total_units
                    if units > 0
                    else Decimal("0")
                )
            else:
                allocations[int(row.sku_id)] = ads_source_spend / Decimal(
                    str(max(count, 1))
                )
        return allocations

    def _ads_block_with_metrics(
        self,
        ads: CardAdsBlock,
        *,
        stats_rows_count: int = 0,
        views: int = 0,
        clicks: int = 0,
        orders: int = 0,
        atbs: int = 0,
    ) -> CardAdsBlock:
        return ads.model_copy(
            update={
                "stats_rows_count": self._int0(stats_rows_count),
                "views": self._int0(views),
                "clicks": self._int0(clicks),
                "orders": self._int0(orders),
                "atbs": self._int0(atbs),
            }
        )

    def _row_sales_velocity_daily(
        self, row: Any, purchase_row: Any | None = None
    ) -> float:
        row_value = getattr(row, "sales_velocity_daily", None)
        if row_value not in (None, ""):
            return self._float0(row_value)
        purchase_value = (
            getattr(purchase_row, "sales_velocity_daily", None)
            if purchase_row is not None
            else None
        )
        if purchase_value not in (None, ""):
            return self._float0(purchase_value)
        stock_qty = self._decimal(getattr(row, "stock_qty", None))
        days_of_stock = self._decimal(getattr(row, "days_of_stock", None))
        if stock_qty > 0 and days_of_stock > 0:
            return self._float0(stock_qty / days_of_stock)
        return 0.0

    def _action_from_recommendation(self, action: Any) -> NextActionRead:
        payload = dict(getattr(action, "payload", {}) or {})
        money_effect = dict(
            getattr(action, "money_effect", {}) or payload.get("moneyEffect") or {}
        )
        if getattr(action, "action_type", "") == "LIQUIDATE_STOCK":
            affected_stock_value = (
                self._payload_number(money_effect, "affected_stock_value")
                or self._payload_number(money_effect, "affectedStockValue")
                or float(getattr(action, "expected_effect_amount", 0) or 0)
            )
            expected_cash_release = (
                self._payload_number(money_effect, "expected_cash_release")
                or self._payload_number(money_effect, "expectedCashRelease")
                or float(getattr(action, "expected_effect_amount", 0) or 0)
                or affected_stock_value
            )
            money_effect = {
                **money_effect,
                "affected_stock_value": affected_stock_value,
                "expected_cash_release": expected_cash_release,
            }
        raw_linked_entity = dict(action.linked_entity or {})
        linked_entity = {
            "sku_id": int(raw_linked_entity.get("sku_id") or 0),
            "nm_id": int(raw_linked_entity.get("nm_id") or 0),
            "vendor_code": self._text(raw_linked_entity.get("vendor_code")),
            "title": self._text(
                raw_linked_entity.get("title"),
                self._text(
                    raw_linked_entity.get("vendor_code"),
                    self._text(getattr(action, "title", None)),
                ),
            ),
        }
        category = getattr(action, "category", "") or self._action_category(
            action.action_type
        )
        affected_nm_ids, affected_sku_ids = self._action_affected_ids(linked_entity)
        financial_final = bool(
            getattr(action, "financial_final", False) or payload.get("financialFinal")
        )
        primary_amount = float(getattr(action, "expected_effect_amount", 0) or 0)
        if action.action_type == "LIQUIDATE_STOCK":
            primary_amount = float(
                money_effect.get("affected_stock_value") or primary_amount
            )
        elif action.action_type == "REORDER":
            primary_amount = float(
                money_effect.get("expected_profit_impact") or primary_amount
            )
        elif action.action_type == "PROTECT_STOCK":
            primary_amount = float(
                money_effect.get("protected_revenue") or primary_amount
            )
        return NextActionRead(
            id=int(action.id),
            action_type=action.action_type,
            action_group=self._action_group(action.action_type),
            category=category,
            priority=action.priority,
            status=action.status,
            title=action.title or action.reason_short or action.reason,
            what_to_do=action.what_to_do or action.reason,
            why=action.why or action.reason,
            business_reason=action.why or action.reason,
            next_step=action.what_to_do or action.reason,
            how_to_fix=list(action.how_to_fix or []),
            expected_effect_amount=primary_amount,
            priority_score=float(
                getattr(action, "priority_score", 0) or primary_amount
            ),
            required_cash=float(action.required_cash or 0),
            recommended_qty=self._payload_int(payload, "recommendedQty"),
            unit_cost=self._payload_number(payload, "unitCost"),
            current_stock=self._payload_number(payload, "currentStock"),
            days_of_stock=self._payload_number(payload, "daysOfStock"),
            lead_time_days=self._payload_int(payload, "leadTimeDays"),
            safety_days=self._payload_int(payload, "safetyDays"),
            confidence=action.confidence,
            financial_final=financial_final,
            deadline_hint=action.deadline_hint or "",
            deadline_at=getattr(action, "deadline_at", None),
            linked_entity=linked_entity,
            affected_nm_ids=affected_nm_ids,
            affected_sku_ids=affected_sku_ids,
            blocked_reasons=list(action.blocked_reasons or []),
            money_effect=money_effect,
            source_endpoint=getattr(action, "source_endpoint", "")
            or self._action_source_endpoint(action.action_type, linked_entity),
        )

    @staticmethod
    def _is_open_action_status(status: str | None) -> bool:
        return (status or "new") in OPEN_ACTION_STATUSES

    def _wb_expenses_total(self, profit_row: Any) -> Decimal:
        total = normalized_wb_expenses_total(profit_row)
        if total != 0:
            return total
        return (
            self._decimal(getattr(profit_row, "commission", None))
            + self._decimal(getattr(profit_row, "acquiring_fee", None))
            + self._decimal(getattr(profit_row, "logistics", None))
            + self._decimal(getattr(profit_row, "paid_acceptance", None))
            + self._decimal(getattr(profit_row, "storage", None))
            + self._decimal(getattr(profit_row, "penalties", None))
            + self._decimal(getattr(profit_row, "deductions", None))
        )

    def _expense_components_from_profit_rows(
        self, profit_rows: list[Any]
    ) -> ExpenseComponentBreakdown:
        return ExpenseComponentBreakdown(
            wb_commission=self._float0(
                sum(
                    (
                        self._expense_value(
                            item, EXPENSE_CATEGORY_WB_COMMISSION, "commission"
                        )
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            payment_processing=self._float0(
                sum(
                    (
                        self._expense_value(
                            item, EXPENSE_CATEGORY_PAYMENT_PROCESSING, "acquiring_fee"
                        )
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            pvz_reward=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_PVZ_REWARD)
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            wb_logistics=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_WB_LOGISTICS)
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            wb_logistics_rebill=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL)
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            acceptance=self._float0(
                sum(
                    (
                        self._expense_value(
                            item, EXPENSE_CATEGORY_ACCEPTANCE, "paid_acceptance"
                        )
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            penalty=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_PENALTY, "penalties")
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            deduction=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_DEDUCTION)
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            marketing_deduction=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_MARKETING_DEDUCTION)
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            loyalty=self._float0(
                sum(
                    (
                        self._expense_value(item, EXPENSE_CATEGORY_LOYALTY)
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            other_wb_expenses=self._float0(
                sum(
                    (
                        self._expense_value(item, "other_wb_expenses")
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            total_wb_expenses=self._float0(
                sum(
                    (self._wb_expenses_total(item) for item in profit_rows),
                    start=Decimal("0"),
                )
            ),
            commission=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "commission", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            acquiring_fee=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "acquiring_fee", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            logistics=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "logistics", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            paid_acceptance=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "paid_acceptance", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            storage=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "storage", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            penalties=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "penalties", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            deductions=self._float0(
                sum(
                    (
                        self._decimal(getattr(item, "deductions", None))
                        for item in profit_rows
                    ),
                    start=Decimal("0"),
                )
            ),
            additional_payments=self._float0(
                sum(
                    (expense_additional_income(item) for item in profit_rows),
                    start=Decimal("0"),
                )
            ),
        )

    def _account_level_expense_breakdown_from_rows(
        self, expense_rows: list[Any]
    ) -> AccountLevelExpenseBreakdown:
        wb_commission = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_WB_COMMISSION, "commission")
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        payment_processing = sum(
            (
                self._expense_value(
                    item, EXPENSE_CATEGORY_PAYMENT_PROCESSING, "acquiring_fee"
                )
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        pvz_reward = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_PVZ_REWARD)
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        wb_logistics = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_WB_LOGISTICS, "logistics")
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        wb_logistics_rebill = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL)
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        acceptance = sum(
            (
                self._expense_value(
                    item, EXPENSE_CATEGORY_ACCEPTANCE, "paid_acceptance"
                )
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        penalty = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_PENALTY, "penalties")
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        deduction = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_DEDUCTION, "deductions")
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        marketing_deduction = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_MARKETING_DEDUCTION)
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        loyalty = sum(
            (
                self._expense_value(item, EXPENSE_CATEGORY_LOYALTY)
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        other_wb_expenses = sum(
            (self._expense_value(item, "other_wb_expenses") for item in expense_rows),
            start=Decimal("0"),
        )
        storage = sum(
            (self._decimal(getattr(item, "storage", None)) for item in expense_rows),
            start=Decimal("0"),
        )
        deductions = sum(
            (self._decimal(getattr(item, "deductions", None)) for item in expense_rows),
            start=Decimal("0"),
        )
        penalties = sum(
            (self._decimal(getattr(item, "penalties", None)) for item in expense_rows),
            start=Decimal("0"),
        )
        logistics_unallocated = sum(
            (
                self._decimal(getattr(item, "logistics", None))
                + self._decimal(getattr(item, "paid_acceptance", None))
                for item in expense_rows
            ),
            start=Decimal("0"),
        )
        total_wb_expenses = sum(
            (self._account_level_wb_expense_total(item) for item in expense_rows),
            start=Decimal("0"),
        )
        categorized_total = (
            wb_commission
            + payment_processing
            + pvz_reward
            + wb_logistics
            + wb_logistics_rebill
            + storage
            + acceptance
            + penalty
            + deduction
            + marketing_deduction
            + loyalty
            + other_wb_expenses
        )
        other = max(Decimal("0"), total_wb_expenses - categorized_total)
        return AccountLevelExpenseBreakdown(
            wb_commission=self._float0(wb_commission),
            payment_processing=self._float0(payment_processing),
            pvz_reward=self._float0(pvz_reward),
            wb_logistics=self._float0(wb_logistics),
            wb_logistics_rebill=self._float0(wb_logistics_rebill),
            acceptance=self._float0(acceptance),
            penalty=self._float0(penalty),
            deduction=self._float0(deduction),
            marketing_deduction=self._float0(marketing_deduction),
            loyalty=self._float0(loyalty),
            other_wb_expenses=self._float0(other_wb_expenses),
            total_wb_expenses=self._float0(total_wb_expenses),
            storage=self._float0(storage),
            deductions=self._float0(deductions),
            wb_promotion_deductions=self._float0(marketing_deduction),
            penalties=self._float0(penalties),
            logistics_unallocated=self._float0(logistics_unallocated),
            other=self._float0(other),
        )

    @staticmethod
    def _expense_allocation_status(
        *, direct_total: Decimal, account_level_total: Decimal
    ) -> str:
        if account_level_total <= 0:
            return "matched"
        if direct_total <= 0:
            return "needs_review"
        return "partial"

    def _store_expenses_waterfall(
        self,
        *,
        profit_rows: list[Any],
        account_expense_rows: list[Any],
        unallocated_expenses: Decimal,
    ) -> StoreExpenseWaterfall:
        direct_components = self._expense_components_from_profit_rows(profit_rows)
        account_level_components = self._account_level_expense_breakdown_from_rows(
            account_expense_rows
        )
        direct_total = self._decimal(direct_components.total_wb_expenses)
        if direct_total == 0:
            direct_total = (
                self._decimal(direct_components.commission)
                + self._decimal(direct_components.acquiring_fee)
                + self._decimal(direct_components.logistics)
                + self._decimal(direct_components.paid_acceptance)
                + self._decimal(direct_components.storage)
                + self._decimal(direct_components.penalties)
                + self._decimal(direct_components.deductions)
            )
        account_level_total = self._decimal(unallocated_expenses)
        allocation_status = self._expense_allocation_status(
            direct_total=direct_total,
            account_level_total=account_level_total,
        )
        if account_level_total > 0:
            message = "Часть расходов WB не привязана к карточкам и учтена как общие расходы магазина."
        elif direct_total > 0:
            message = "Расходы WB привязаны к карточкам на прямом уровне."
        else:
            message = "В выбранном окне прямые расходы WB не выявлены."
        return StoreExpenseWaterfall(
            direct_sku_expenses=direct_components,
            account_level_expenses=account_level_components,
            unallocated_expenses=self._float0(unallocated_expenses),
            allocation_status=allocation_status,
            message=message,
        )

    def _article_expense_breakdown(
        self, wb_expenses: CardExpenseBreakdown
    ) -> ArticleExpenseBreakdown:
        direct_expenses = ExpenseComponentBreakdown(
            commission=wb_expenses.commission,
            acquiring_fee=wb_expenses.acquiring_fee,
            logistics=wb_expenses.logistics,
            paid_acceptance=wb_expenses.paid_acceptance,
            storage=wb_expenses.storage,
            penalties=wb_expenses.penalties,
            deductions=wb_expenses.deductions,
            additional_payments=wb_expenses.additional_payments,
        )
        has_account_level = (wb_expenses.account_level or 0) > 0 or (
            wb_expenses.unallocated or 0
        ) > 0
        has_account_level_logistics = (
            getattr(wb_expenses, "account_level_logistics", 0) or 0
        ) > 0 or (getattr(wb_expenses, "unallocated_logistics", 0) or 0) > 0
        direct_zero = (wb_expenses.direct or 0) <= 0
        direct_logistics_zero = (
            (getattr(wb_expenses, "wb_logistics", 0) or 0)
            + (getattr(wb_expenses, "wb_logistics_rebill", 0) or 0)
            + (getattr(wb_expenses, "logistics", 0) or 0)
        ) <= 0
        logistics_not_linked = (
            wb_expenses.status
            in {
                "account_level_logistics_not_allocated",
                "account_level_logistics_partially_allocated",
            }
            or has_account_level_logistics
        )
        unallocated_warning = (
            wb_expenses.status == "suspicious_zero_expenses"
            or logistics_not_linked
            or (direct_zero and has_account_level)
        )
        not_linked_reason = (
            "логистика WB есть в финансовом отчете, но строки не содержат SKU/баркод и не привязаны к карточке"
            if logistics_not_linked and direct_logistics_zero
            else "часть логистики WB остается на уровне аккаунта и не распределена по SKU/карточке"
            if logistics_not_linked
            else "строки финансового отчета не содержат номера артикула или штрихкода либо относятся к расходам магазина целиком"
            if unallocated_warning
            else ""
        )
        message = (
            "Логистика WB не привязана к SKU/карточке; прибыль карточки без распределения этой логистики предварительная."
            if logistics_not_linked and direct_logistics_zero
            else "Логистика WB привязана к карточке только частично; account-level логистика еще не распределена."
            if logistics_not_linked
            else "Прямые расходы по карточке видны не полностью, часть WB-расходов остается в общих расходах магазина."
            if unallocated_warning
            else "Прямые WB-расходы по карточке видны без явного разрыва с общими расходами магазина."
        )
        return ArticleExpenseBreakdown(
            direct_expenses=direct_expenses,
            allocated_overhead=wb_expenses.allocated_overhead,
            account_level_total=wb_expenses.account_level,
            account_level_logistics=getattr(wb_expenses, "account_level_logistics", 0),
            unallocated_total=wb_expenses.unallocated,
            unallocated_logistics=getattr(wb_expenses, "unallocated_logistics", 0),
            total_wb_expenses=getattr(wb_expenses, "total_wb_expenses", None)
            or wb_expenses.direct,
            unallocated_warning=unallocated_warning,
            not_linked_reason=not_linked_reason,
            message=message,
        )

    def _article_trust_block(
        self,
        *,
        row: Any,
        profit_row: Any,
        finality: FinalityBlock,
        reconciliation_status: str,
    ) -> ArticleTrustBlock:
        data_trust = self._data_trust_for_row(row)
        reason_parts: list[str] = []
        if not finality.profit_final:
            if reconciliation_status != "matched":
                reason_parts.append("есть расхождение между отчетом WB и продажами")
            if not getattr(profit_row, "has_real_manual_cost", False):
                reason_parts.append("не хватает подтвержденной реальной себестоимости")
            if "wb_expenses_not_fully_mapped" in list(finality.reasons or []):
                reason_parts.append("часть расходов WB не привязана к этой карточке")
            if "ads_overallocated" in list(
                finality.reasons or []
            ) or "ads_not_allocated" in list(finality.reasons or []):
                reason_parts.append(
                    "рекламные расходы по карточке распределены не полностью"
                )
        return ArticleTrustBlock(
            state=data_trust.state,
            trust_state=data_trust.trust_state,
            business_trusted=data_trust.business_trusted,
            operational_trusted=data_trust.operational_trusted,
            financial_final=finality.profit_final,
            cost_trust_policy=data_trust.cost_trust_policy,
            supplier_confirmed_revenue_coverage_percent=data_trust.supplier_confirmed_revenue_coverage_percent,
            operator_baseline_revenue_coverage_percent=data_trust.operator_baseline_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=data_trust.trusted_revenue_cost_coverage_percent,
            financial_final_blockers_total=data_trust.financial_final_blockers_total,
            final_profit_blockers_total=data_trust.final_profit_blockers_total,
            all_open_issues_total=data_trust.all_open_issues_total,
            blocking_open_issues_total=data_trust.blocking_open_issues_total,
            confidence=data_trust.confidence,
            blocked_reasons=list(data_trust.blocked_reasons),
            cost_truth_level=str(getattr(profit_row, "cost_truth_level", "") or ""),
            supplier_confirmed=self._profit_row_cost_final_accepted(profit_row),
            finance_status=reconciliation_status,
            human_message=data_trust.human_message,
            reason="; ".join(reason_parts),
        )

    def _article_money_answer(
        self,
        *,
        verdict: CardVerdict,
        finality: FinalityBlock,
        trust: ArticleTrustBlock,
        stock: CardStockBlock,
        purchase_plan: ArticlePurchasePlanBlock | None,
        top_action: NextActionRead,
        profit_after_source_ads: float,
    ) -> MoneyCardAnswer:
        if trust.state == TRUST_STATE_BLOCKED:
            status = "fix_data_first"
            title = "Сначала закройте блокеры данных"
            short_text = "По карточке уже видны продажи и расходы, но сначала нужно закрыть блокеры данных."
        elif profit_after_source_ads <= 0:
            status = "loss_making"
            title = "Карточка теряет деньги"
            short_text = "Карточка выглядит убыточной и требует осторожного решения по закупке, цене или рекламе."
        elif stock.stock_status == "overstock":
            status = "profitable_but_overstocked"
            title = "Карточка прибыльная, но остаток слишком большой"
            short_text = "Карточка зарабатывает деньги, но часть капитала заморожена в большом остатке."
        elif purchase_plan is not None and purchase_plan.decision == "REORDER":
            status = "growth_ready"
            title = "Карточка подходит для роста"
            short_text = (
                "Карточка операционно готова к дозакупке."
                if finality.profit_final
                else "Карточка выглядит сильной для роста, но финальная прибыль еще предварительная."
            )
        elif finality.profit_final:
            status = "profitable"
            title = "Карточка выглядит здоровой"
            short_text = "Карточка по артикулу выглядит прибыльной и без явных денежных блокеров."
        else:
            status = "provisional"
            title = "Карточка управляемая, но финальная прибыль предварительная"
            short_text = "Операционные цифры уже полезны, но итоговая прибыль по карточке еще не подтверждена."
        decision = (
            purchase_plan.decision.lower()
            if purchase_plan and purchase_plan.decision
            else ""
        ) or ("fix_data_first" if trust.state == TRUST_STATE_BLOCKED else "watch")
        return MoneyCardAnswer(
            status=status,
            title=title,
            short_text=short_text,
            decision=decision,
            next_step=top_action.what_to_do,
            main_next_step=top_action.what_to_do,
            main_reason=top_action.why,
        )

    def _article_kpis(
        self,
        *,
        money: CardMoneyBlock,
        stock: CardStockBlock,
        operations: CardOperationsBlock,
    ) -> ArticleKpisBlock:
        return ArticleKpisBlock(
            revenue=money.revenue,
            for_pay=money.for_pay,
            profit_before_ads=money.profit.before_ads,
            profit_after_allocated_ads=money.profit.after_allocated_ads,
            profit_after_source_ads=money.profit.after_source_ads,
            profit_after_overhead=money.profit.after_overhead,
            wb_expenses_total=money.wb_expenses_total,
            stock_qty=stock.quantity,
            stock_value=stock.stock_value,
            ads_source_spend=money.ads.source_spend,
            ads_allocated_spend=money.ads.allocated_spend,
            cancel_rate_percent=operations.cancel_rate_percent,
            return_rate_percent=operations.return_rate_percent,
        )

    def _article_waterfall(
        self,
        *,
        money: CardMoneyBlock,
    ) -> ArticleWaterfallBlock:
        return ArticleWaterfallBlock(
            revenue=money.revenue,
            cogs=money.cogs.estimated_cogs,
            direct_wb_expenses=money.wb_expenses.direct,
            ads_source_spend=money.ads.source_spend,
            allocated_overhead=money.wb_expenses.allocated_overhead,
            profit_before_ads=money.profit.before_ads,
            profit_after_source_ads=money.profit.after_source_ads,
            profit_after_overhead=money.profit.after_overhead,
        )

    def _article_purchase_plan(
        self,
        *,
        state: MoneyRuntimeState,
        nm_id: int,
    ) -> ArticlePurchasePlanBlock | None:
        article_purchase_rows = self.control._group_purchase_rows_by_article(
            control_rows=state.control_rows,
            purchase_rows=state.purchase_rows,
            settings=state.settings,
        )
        purchase = next(
            (item for item in article_purchase_rows if int(item.nm_id or 0) == nm_id),
            None,
        )
        if purchase is None:
            return None
        return ArticlePurchasePlanBlock(
            decision=purchase.decision or purchase.status,
            main_reason=purchase.main_reason or purchase.reason,
            next_step=purchase.next_step,
            recommended_qty=purchase.recommended_qty,
            required_cash=purchase.required_cash,
            money_effect=dict(purchase.money_effect or {}),
            confidence=purchase.confidence,
            decision_confidence=purchase.decision_confidence or purchase.confidence,
            financial_final=bool(purchase.financial_final),
            available_stock=purchase.available_stock,
            in_transit_qty=purchase.in_transit_qty,
            days_of_stock=purchase.days_of_stock,
            lead_time_days=purchase.lead_time_days,
            safety_days=purchase.safety_days,
            variant_count=purchase.variant_count,
            size_breakdown=list(purchase.size_breakdown or []),
        )

    def _root_cause_candidates(
        self, *, audit: Any, row: Any, profit_row: Any
    ) -> list[str]:
        reasons: list[str] = []
        if audit.reconciliation.mart_matches_finance is False:
            reasons.append(
                "в финансовом отчете есть строки, которые не совпадают с этой карточкой по уровню детализации"
            )
        if not audit.reconciliation.finance_matches_operational:
            reasons.append(
                "продажи и финансовый отчет не совпадают по артикулу или дате"
            )
        if "supplier_cost_not_confirmed" in list(
            row.blocked_reasons or []
        ) or not getattr(profit_row, "has_real_manual_cost", False):
            reasons.append(
                "по этой карточке еще не хватает подтвержденной реальной себестоимости"
            )
        if (
            self._decimal(getattr(audit.ads, "spend", None)) > 0
            and self._decimal(getattr(profit_row, "ad_spend", None)) <= 0
        ):
            reasons.append(
                "расходы на рекламу есть в источнике, но еще не распределены по прибыли карточки"
            )
        if not reasons:
            reasons.append(
                "сравните строки финансового отчета, продажи и аудит карточки по исходным данным"
            )
        return reasons

    def _actions_for_sku(
        self, state: MoneyRuntimeState, sku_id: int | None
    ) -> list[Any]:
        if sku_id is None:
            return []
        return list(state.actions_by_sku.get(int(sku_id), []))

    def _primary_row_action(
        self,
        state: MoneyRuntimeState,
        row: Any,
        *,
        price_row: Any | None,
        purchase_row: Any | None,
    ) -> NextActionRead:
        persisted = self._actions_for_sku(
            state, int(row.sku_id) if row.sku_id is not None else None
        )
        if persisted:
            persisted.sort(key=self._action_sort_key, reverse=True)
            return self._action_from_recommendation(persisted[0])
        synthesized = self._synthesized_row_action(
            row, price_row=price_row, purchase_row=purchase_row
        )
        return synthesized or self._default_row_action(row)

    @staticmethod
    def _date_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
        today = utcnow().date()
        return date_from or (today - timedelta(days=29)), date_to or today

    @staticmethod
    def _priority_rank(priority: str) -> int:
        return {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(priority, 0)

    @staticmethod
    def _trust_confidence(state: str) -> str:
        if state in {TRUST_STATE_TRUSTED, "financial_final"}:
            return "high"
        if state in {TRUST_STATE_TEST_ONLY, "operational_provisional"}:
            return "medium"
        return "low"

    @staticmethod
    def _trust_message(
        *, business_trusted: bool, blocked_reasons: list[str], trust_state: str
    ) -> str:
        if trust_state == "financial_final":
            return "Данные подтверждены для финальной прибыли и управленческих решений."
        if business_trusted:
            return "Данных достаточно для принятия бизнес-решений."
        if trust_state in {TRUST_STATE_TEST_ONLY, "operational_provisional"}:
            if blocked_reasons:
                return (
                    "Бизнес-анализ и предварительные действия доступны, "
                    f"но интерпретировать их нужно осторожно: {', '.join(blocked_reasons)}."
                )
            return "Бизнес-анализ доступен, но часть слоев пока работает в предварительном режиме."
        if not blocked_reasons:
            return "Данные пока неполные, интерпретируйте их осторожно."
        return (
            "Данные пока недостаточно надежны для окончательных бизнес-решений. "
            f"Основные блокеры: {', '.join(blocked_reasons)}."
        )

    def _blocked_reason_labels(self, reasons: list[str]) -> list[str]:
        return [self.BLOCKED_REASON_LABELS.get(reason, reason) for reason in reasons]

    @staticmethod
    def _profit_row_cost_final_accepted(profit_row: Any) -> bool:
        return final_cost_is_accepted(
            has_manual_cost=bool(getattr(profit_row, "has_manual_cost", False)),
            has_real_manual_cost=bool(
                getattr(profit_row, "has_real_manual_cost", False)
            ),
            has_placeholder_cost=bool(
                getattr(profit_row, "has_placeholder_cost", False)
            ),
            cost_source=getattr(profit_row, "cost_source", None),
            cost_truth_level=getattr(profit_row, "cost_truth_level", None),
            cost_trust_policy=getattr(profit_row, "cost_trust_policy", None),
        )

    def _meta(
        self, *, account_id: int, date_from: date, date_to: date, health: Any
    ) -> MoneyMeta:
        trust = DataTrustInfo(
            state=health.trust_state,
            trust_state=health.trust_state,
            business_trusted=bool(health.business_trusted),
            operational_trusted=bool(
                getattr(
                    health, "operational_trusted", health.can_generate_business_actions
                )
            ),
            financial_final=bool(getattr(health, "financial_final", False)),
            can_generate_business_actions=bool(health.can_generate_business_actions),
            confidence=self._trust_confidence(health.trust_state),
            cost_trust_policy=getattr(health, "cost_trust_policy", None),
            supplier_confirmed_revenue_coverage_percent=self._float0(
                getattr(health, "supplier_confirmed_revenue_coverage_percent", 0)
            ),
            operator_baseline_revenue_coverage_percent=self._float0(
                getattr(health, "operator_baseline_revenue_coverage_percent", 0)
            ),
            trusted_revenue_cost_coverage_percent=self._float0(
                getattr(health, "trusted_revenue_cost_coverage_percent", 0)
            ),
            financial_final_blockers_total=int(
                getattr(health, "financial_final_blockers_total", 0) or 0
            ),
            final_profit_blockers_total=int(
                getattr(health, "final_profit_blockers_total", 0) or 0
            ),
            all_open_issues_total=int(
                getattr(
                    health,
                    "all_open_issues_total",
                    getattr(health, "open_issues_total", 0),
                )
                or 0
            ),
            blocking_open_issues_total=int(
                getattr(health, "blocking_open_issues_total", 0) or 0
            ),
            blocked_reasons=list(health.blocked_reasons or []),
            human_message=self._trust_message(
                business_trusted=bool(health.business_trusted),
                blocked_reasons=self._blocked_reason_labels(
                    list(health.blocked_reasons or [])
                ),
                trust_state=health.trust_state,
            ),
        )
        return MoneyMeta(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            generated_at=utcnow(),
            data_trust=trust,
        )

    def _build_store_answer(
        self,
        *,
        health: Any,
        answer: BusinessAnswer,
        revenue: Decimal,
        cogs: Decimal,
        direct_wb_expenses: Decimal,
        ad_spend_final: Decimal,
        unallocated_expenses: Decimal,
        latest_balance: Any | None,
        stock_value: Decimal,
        in_transit_value: Decimal,
        next_actions: list[NextActionRead],
    ) -> StoreAnswer:
        what_is_happening = answer.short_text or (
            "Магазин показывает подтвержденный денежный поток и готов к финальным решениям."
            if health.business_trusted
            else "Магазин показывает денежный поток и предварительную прибыль, но часть слоев пока требует подтверждения."
        )
        where_money_came_from = (
            f"Основной входящий поток сейчас формируется выручкой {self._float0(revenue):.2f} ₽."
            if revenue > 0
            else "В выбранном окне не найден подтвержденный входящий денежный поток."
        )
        wb_total = direct_wb_expenses + unallocated_expenses
        where_money_went = (
            f"Деньги уходят в себестоимость {self._float0(cogs):.2f} ₽, WB-расходы {self._float0(wb_total):.2f} ₽"
            f" (из них общие магазинные {self._float0(unallocated_expenses):.2f} ₽), рекламу {self._float0(ad_spend_final):.2f} ₽."
        )
        balance_amount = self._balance_amount(latest_balance)
        where_money_is_now = f"Сейчас деньги находятся на балансе WB {balance_amount:.2f} ₽, в остатках {self._float0(stock_value):.2f} ₽ и в пути {self._float0(in_transit_value):.2f} ₽."
        what_to_do_today = [
            action.what_to_do for action in next_actions[:3] if action.what_to_do
        ]
        return StoreAnswer(
            what_is_happening=what_is_happening,
            where_money_came_from=where_money_came_from,
            where_money_went=where_money_went,
            where_money_is_now=where_money_is_now,
            what_to_do_today=what_to_do_today,
        )

    def _build_revenue_sources(
        self,
        *,
        health: Any,
        revenue: Decimal,
        finance_confirmed_revenue: Decimal,
        mart_revenue: Decimal,
        full_mart_revenue: Decimal | None = None,
        finance_coverage_date_to: date | None = None,
        requested_date_to: date | None = None,
    ) -> RevenueSources:
        comparison_mart_revenue = mart_revenue
        full_revenue = full_mart_revenue if full_mart_revenue is not None else revenue
        difference_amount = abs(finance_confirmed_revenue - comparison_mart_revenue)
        difference_percent = self._percent0(difference_amount, comparison_mart_revenue)
        status = self._reconciliation_status(
            finance_confirmed_revenue=finance_confirmed_revenue,
            mart_revenue=comparison_mart_revenue,
        )
        mismatch_reason = ""
        if finance_coverage_date_to is None:
            mismatch_reason = "finance_report_not_loaded"
        elif (
            requested_date_to is not None
            and finance_coverage_date_to < requested_date_to
        ):
            mismatch_reason = "finance_report_lag_open_period"
            if status == "matched":
                status = "partial_finance_lag"
        elif status != "matched":
            mismatch_reason = "finance_vs_mart_revenue_mismatch"
        return RevenueSources(
            operational_revenue=self._float0(revenue),
            operational_revenue_label="Выручка по текущей выборке",
            finance_confirmed_revenue=self._float0(finance_confirmed_revenue),
            finance_confirmed_revenue_label="Выручка по подтверждённым финансовым отчетам WB",
            mart_revenue=self._float0(comparison_mart_revenue),
            comparison_mart_revenue=self._float0(comparison_mart_revenue),
            open_period_revenue=self._float0(
                max(Decimal("0"), full_revenue - comparison_mart_revenue)
            ),
            open_period_revenue_label="Выручка вне закрытого периода WB",
            supplier_cost_confirmed_revenue=self._float0(health.revenue_with_real_cost),
            difference_amount=self._float0(difference_amount),
            difference_percent=difference_percent,
            source_of_truth=self._source_of_truth_label(
                finance_confirmed_revenue=finance_confirmed_revenue,
                mart_revenue=comparison_mart_revenue,
            ),
            reconciliation_status=status,
            finance_coverage_date_to=finance_coverage_date_to,
            mismatch_reason=mismatch_reason,
        )

    def _cost_coverage_status(self, health: Any) -> tuple[float, float, str]:
        cost_coverage = self._cost_coverage_from_health(health)
        supplier_percent = cost_coverage.supplier_confirmed_cost_coverage_percent
        business_percent = cost_coverage.business_accepted_cost_coverage_percent
        if cost_coverage.can_use_for_final_profit:
            if cost_policy_owner_approves_final(
                getattr(health, "cost_trust_policy", None)
            ):
                return supplier_percent, business_percent, "owner_approved_final"
            return supplier_percent, business_percent, "supplier_confirmed"
        if cost_coverage.can_use_for_operations:
            return supplier_percent, business_percent, "operator_baseline_accepted"
        return supplier_percent, business_percent, "insufficient"

    def _cost_coverage_block(
        self,
        *,
        total_revenue: Decimal,
        supplier_confirmed_revenue: Decimal,
        operator_baseline_revenue: Decimal,
        missing_cost_revenue: Decimal,
        cost_trust_policy: str | None,
    ) -> CostCoverageBlock:
        decision = build_cost_coverage_decision(
            total_revenue=self._float0(total_revenue),
            supplier_confirmed_revenue=self._float0(supplier_confirmed_revenue),
            operator_baseline_revenue=self._float0(operator_baseline_revenue),
            missing_cost_revenue=self._float0(missing_cost_revenue),
            cost_trust_policy=cost_trust_policy or "operator_baseline",
        )
        return CostCoverageBlock(
            operational_cost_coverage_percent=decision.operational_cost_coverage_percent,
            operational_label="Покрыто текущей себестоимостью",
            supplier_confirmed_cost_coverage_percent=decision.supplier_confirmed_cost_coverage_percent,
            supplier_confirmed_label="Покрыто подтвержденной себестоимостью",
            business_accepted_cost_coverage_percent=decision.business_accepted_cost_coverage_percent,
            business_accepted_label="Покрыто принятой себестоимостью",
            cost_policy=decision.cost_policy,
            cost_truth_level=decision.cost_truth_level,
            can_use_for_operations=decision.can_use_for_operations,
            can_use_for_final_profit=decision.can_use_for_final_profit,
            missing_cost_revenue=decision.missing_cost_revenue,
            operator_baseline_revenue=decision.operator_baseline_revenue,
            supplier_confirmed_revenue=decision.supplier_confirmed_revenue,
            message=decision.message,
        )

    def _cost_coverage_from_health(self, health: Any) -> CostCoverageBlock:
        revenue_with_cost = self._decimal(getattr(health, "revenue_with_cost", 0))
        revenue_without_cost = self._decimal(getattr(health, "revenue_without_cost", 0))
        supplier_confirmed_revenue = self._decimal(
            getattr(health, "revenue_with_real_cost", 0)
        )
        placeholder_revenue = self._decimal(
            getattr(health, "revenue_with_placeholder_cost", 0)
        )
        operator_baseline_revenue = max(
            Decimal("0"),
            revenue_with_cost - placeholder_revenue - supplier_confirmed_revenue,
        )
        total_revenue = revenue_with_cost + revenue_without_cost
        missing_cost_revenue = max(
            Decimal("0"),
            total_revenue - supplier_confirmed_revenue - operator_baseline_revenue,
        )
        return self._cost_coverage_block(
            total_revenue=total_revenue,
            supplier_confirmed_revenue=supplier_confirmed_revenue,
            operator_baseline_revenue=operator_baseline_revenue,
            missing_cost_revenue=missing_cost_revenue,
            cost_trust_policy=str(
                getattr(health, "cost_trust_policy", "operator_baseline")
                or "operator_baseline"
            ),
        )

    def _cost_coverage_from_profit_rows(
        self,
        profit_rows: list[Any],
        *,
        cost_trust_policy: str | None,
    ) -> CostCoverageBlock:
        total_revenue = Decimal("0")
        supplier_confirmed_revenue = Decimal("0")
        operator_baseline_revenue = Decimal("0")
        missing_cost_revenue = Decimal("0")
        for profit_row in profit_rows:
            revenue = self._decimal(getattr(profit_row, "realized_revenue", None))
            total_revenue += revenue
            has_manual_cost = bool(getattr(profit_row, "has_manual_cost", False))
            has_real_manual_cost = bool(
                getattr(profit_row, "has_real_manual_cost", False)
            )
            has_placeholder_cost = bool(
                getattr(profit_row, "has_placeholder_cost", False)
            )
            if has_real_manual_cost:
                supplier_confirmed_revenue += revenue
            elif has_manual_cost and not has_placeholder_cost:
                operator_baseline_revenue += revenue
            else:
                missing_cost_revenue += revenue
        return self._cost_coverage_block(
            total_revenue=total_revenue,
            supplier_confirmed_revenue=supplier_confirmed_revenue,
            operator_baseline_revenue=operator_baseline_revenue,
            missing_cost_revenue=missing_cost_revenue,
            cost_trust_policy=cost_trust_policy or "operator_baseline",
        )

    def _build_quality(
        self,
        *,
        health: Any,
        ads_metrics: dict[str, Decimal | float | str],
        revenue_sources: RevenueSources,
    ) -> MoneyQuality:
        cost_coverage = self._cost_coverage_from_health(health)
        supplier_percent, business_percent, cost_status = self._cost_coverage_status(
            health
        )
        return MoneyQuality(
            supplier_cost_coverage_percent=cost_coverage.supplier_confirmed_cost_coverage_percent,
            supplier_confirmed_cost_coverage_percent=cost_coverage.supplier_confirmed_cost_coverage_percent,
            business_cost_coverage_percent=cost_coverage.business_accepted_cost_coverage_percent,
            cost_coverage_status=cost_status,
            raw_ads_allocated_spend=self._float0(
                ads_metrics.get("raw_ads_allocated", 0)
            ),
            capped_ads_allocated_spend=self._float0(
                ads_metrics.get(
                    "capped_ads_allocated_spend",
                    ads_metrics.get("ads_allocated_spend", 0),
                )
            ),
            ads_allocation_percent=self._float0(
                ads_metrics["ads_allocation_percent_capped"]
            ),
            ads_allocation_percent_capped=self._float0(
                ads_metrics["ads_allocation_percent_capped"]
            ),
            ads_duplicate_ignored_spend=self._float0(
                ads_metrics.get("ads_duplicate_ignored_spend", 0)
            ),
            ads_overallocated_spend=self._float0(
                ads_metrics["ads_overallocated_spend"]
            ),
            final_profit_allowed=bool(ads_metrics.get("final_profit_allowed", True)),
            finance_difference_amount=revenue_sources.difference_amount,
            finance_difference_percent=revenue_sources.difference_percent,
            final_finance_ready=revenue_sources.reconciliation_status == "matched",
            finance_reconciliation_status=revenue_sources.reconciliation_status,
        )

    def _profit_variants(
        self,
        *,
        profit_before_ads: Decimal,
        ads_allocated_spend: Decimal,
        ads_source_spend: Decimal,
        allocated_overhead: Decimal = Decimal("0"),
    ) -> ProfitVariants:
        after_allocated_ads = profit_before_ads - ads_allocated_spend
        after_source_ads = profit_before_ads - ads_source_spend
        after_overhead = after_source_ads - allocated_overhead
        return ProfitVariants(
            before_ads=self._float0(profit_before_ads),
            after_allocated_ads=self._float0(after_allocated_ads),
            after_source_ads=self._float0(after_source_ads),
            after_overhead=self._float0(after_overhead),
            with_allocated_overhead=self._float0(after_overhead),
        )

    def _allocated_overhead(
        self,
        *,
        revenue: Decimal,
        total_revenue: Decimal,
        account_level_expense_total: Decimal,
    ) -> Decimal:
        if revenue <= 0 or total_revenue <= 0 or account_level_expense_total <= 0:
            return Decimal("0")
        return account_level_expense_total * revenue / total_revenue

    def _finality_for_row(
        self,
        row: Any,
        *,
        price_row: Any | None,
        ads_unallocated: Decimal,
        ads_overallocated: Decimal = Decimal("0"),
        finance_ready: bool = True,
        supplier_confirmed: bool = True,
        expense_mapping_final: bool = True,
    ) -> FinalityBlock:
        reasons = list(row.blocked_reasons or [])
        if ads_unallocated > 0:
            reasons.append("ads_not_allocated")
        if ads_overallocated > 0:
            reasons.append("ads_overallocated")
        if not finance_ready:
            reasons.append("finance_reconciliation_mismatch")
        if not supplier_confirmed:
            reasons.append("supplier_cost_not_confirmed")
        if not expense_mapping_final:
            reasons.append("wb_expenses_not_fully_mapped")
        if price_row is not None and price_row.not_computable_reason:
            reasons.append(price_row.not_computable_reason)
        unique_reasons = [
            reason
            for reason in dict.fromkeys(reasons)
            if not self._is_hidden_user_problem_code(reason)
        ]
        profit_final = (
            row.trust_state == TRUST_STATE_TRUSTED
            and ads_unallocated <= 0
            and ads_overallocated <= 0
            and finance_ready
            and supplier_confirmed
            and expense_mapping_final
        )
        return FinalityBlock(
            profit_final=profit_final,
            restock_final=profit_final,
            price_final=(
                row.trust_state == TRUST_STATE_TRUSTED
                and supplier_confirmed
                and price_row is not None
                and not bool(price_row.not_computable_reason)
            ),
            reasons=unique_reasons,
        )

    async def _load_runtime_state(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        runtime_version_hash: str | None = None,
    ) -> MoneyRuntimeState:
        window_key = self._runtime_window_key(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        runtime_version_hash = runtime_version_hash or await self._runtime_version_hash(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        runtime_window_cache = self._runtime_window_cache_store(session)
        warm_cached = runtime_window_cache.get(window_key)
        if warm_cached is not None:
            cached_at, cached_state = warm_cached
            if (
                self._cache_is_fresh(
                    cached_at, ttl_seconds=self.WARM_RUNTIME_CACHE_TTL_SECONDS
                )
                and str(getattr(cached_state, "data_version_hash", "") or "")
                == runtime_version_hash
            ):
                return replace(cached_state, cache_status="hit")
        inflight_key = self._runtime_inflight_key(window_key)
        inflight_task = self._runtime_inflight.get(inflight_key)
        if inflight_task is not None and not inflight_task.done():
            shared_state = await inflight_task
            return replace(shared_state, cache_status="hit")
        task = asyncio.create_task(
            self._compute_runtime_state(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                runtime_version_hash=runtime_version_hash,
            )
        )
        self._runtime_inflight[inflight_key] = task
        try:
            return await task
        finally:
            if self._runtime_inflight.get(inflight_key) is task:
                self._runtime_inflight.pop(inflight_key, None)

    async def _compute_runtime_state(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        runtime_version_hash: str | None = None,
    ) -> MoneyRuntimeState:
        window_key = self._runtime_window_key(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        runtime_version_hash = runtime_version_hash or await self._runtime_version_hash(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        cache_key = self._runtime_cache_key(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            data_version_hash=runtime_version_hash,
        )
        runtime_cache = self._runtime_cache_store(session)
        runtime_window_cache = self._runtime_window_cache_store(session)
        cached = runtime_cache.get(cache_key)
        if cached is not None:
            cached_at, cached_state = cached
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.RUNTIME_CACHE_TTL_SECONDS
            ):
                cached_state.cache_status = "hit"
                cached_state.data_version_hash = runtime_version_hash
                runtime_window_cache[window_key] = (cached_at, cached_state)
                return cached_state
        health = await self.dashboard.data_health(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        profit_rows = await self.dashboard.sku_profitability(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        (
            control_rows,
            price_rows,
            purchase_rows,
            settings,
        ) = await self.control._build_control_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            profit_rows=profit_rows,
        )
        trust_decision = await self.control._trust_decision(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            settings=settings,
            health=health,
        )
        ads_source_by_nm, ads_source_total = await self.control._load_ads_source_by_nm(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        latest_balance = await self._current_balance(session, account_id=account_id)
        period_end_balance = await self._period_end_balance(
            session, account_id=account_id, date_to=date_to
        )
        finance_confirmed_revenue_total = await self._finance_confirmed_revenue_total(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        finance_coverage_date_to = await self._finance_coverage_date_to(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        finance_closed_mart_revenue_total = (
            await self._mart_revenue_until(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=finance_coverage_date_to,
            )
            if finance_coverage_date_to is not None
            else Decimal("0")
        )
        synced_actions = await self.control._sync_recommendations_cached(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            control_rows=control_rows,
            price_rows=price_rows,
            purchase_rows=purchase_rows,
            trust_decision=trust_decision,
        )
        action_rows = synced_actions
        action_reads = [self.control._action_read(row) for row in action_rows]
        actions_by_sku: dict[int, list[Any]] = {}
        for action in action_reads:
            if action.sku_id is None or not self._is_open_action_status(action.status):
                continue
            actions_by_sku.setdefault(int(action.sku_id), []).append(action)
        account_expense_rows = await self._account_level_expense_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        account_level_expense_total = sum(
            (
                self._account_level_wb_expense_total(item)
                for item in account_expense_rows
            ),
            start=Decimal("0"),
        )
        account_level_logistics_total = self._account_level_logistics_total_from_rows(
            account_expense_rows
        )
        computed_at = utcnow()
        data_version_hash = runtime_version_hash
        state = MoneyRuntimeState(
            health=health,
            profit_rows=profit_rows,
            control_rows=control_rows,
            price_rows=price_rows,
            purchase_rows=purchase_rows,
            settings=settings,
            trust_decision=trust_decision,
            action_reads=action_reads,
            actions_by_sku=actions_by_sku,
            ads_source_total=ads_source_total,
            ads_source_by_nm=ads_source_by_nm,
            account_expense_rows=account_expense_rows,
            account_level_expense_total=account_level_expense_total,
            account_level_logistics_total=account_level_logistics_total,
            latest_balance=latest_balance,
            period_end_balance=period_end_balance,
            finance_confirmed_revenue_total=finance_confirmed_revenue_total,
            finance_closed_mart_revenue_total=finance_closed_mart_revenue_total,
            finance_coverage_date_to=finance_coverage_date_to,
            computed_at=computed_at,
            cache_status="miss",
            data_version_hash=data_version_hash,
        )
        runtime_cache[cache_key] = (computed_at, state)
        runtime_window_cache[window_key] = (computed_at, state)
        return state

    async def _current_balance(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> WBBalanceSnapshot | None:
        return (
            await session.execute(
                select(WBBalanceSnapshot)
                .where(WBBalanceSnapshot.account_id == account_id)
                .order_by(
                    WBBalanceSnapshot.snapshot_at.desc(), WBBalanceSnapshot.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _period_end_balance(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_to: date,
    ) -> WBBalanceSnapshot | None:
        return (
            await session.execute(
                select(WBBalanceSnapshot)
                .where(
                    WBBalanceSnapshot.account_id == account_id,
                    WBBalanceSnapshot.snapshot_at
                    <= datetime.combine(date_to, datetime.max.time()),
                )
                .order_by(
                    WBBalanceSnapshot.snapshot_at.desc(), WBBalanceSnapshot.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def _account_level_expense_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[Any]:
        rows = list(
            (
                await session.execute(
                    select(MartAccountExpenseDaily).where(
                        MartAccountExpenseDaily.account_id == account_id,
                        MartAccountExpenseDaily.stat_date >= date_from,
                        MartAccountExpenseDaily.stat_date <= date_to,
                    )
                )
            ).scalars()
        )
        current_wb_total = sum(
            (self._account_level_wb_expense_total(item) for item in rows),
            start=Decimal("0"),
        )
        current_finance_ad_total = sum(
            (self._account_level_finance_ad_total(item) for item in rows),
            start=Decimal("0"),
        )
        current_logistics_total = self._account_level_logistics_total_from_rows(rows)
        if rows and (current_wb_total + current_finance_ad_total) > Decimal("0"):
            return rows
        raw_entries = await self._raw_finance_expense_entries(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        raw_unallocated_entries = [
            entry for entry in raw_entries if not bool(entry.get("is_allocated_to_sku"))
        ]
        if not raw_unallocated_entries:
            return rows
        raw_totals = self._raw_finance_category_totals(raw_unallocated_entries)
        raw_wb_total = self._wb_total_from_category_totals(raw_totals)
        raw_finance_ad_total = raw_totals[EXPENSE_CATEGORY_MARKETING_DEDUCTION]
        raw_logistics_total = self._logistics_total_from_category_totals(raw_totals)
        current_total = current_wb_total + current_finance_ad_total
        raw_total = raw_wb_total + raw_finance_ad_total
        if (
            not rows
            or raw_total > current_total + Decimal("1")
            or raw_logistics_total > current_logistics_total + Decimal("1")
        ):
            return self._synthesized_account_expense_rows_from_raw_entries(
                account_id=account_id,
                entries=raw_unallocated_entries,
            )
        return rows

    async def _finance_confirmed_revenue_total(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> Decimal:
        doc_type = func.lower(func.coalesce(WBRealizationReportRow.doc_type_name, ""))
        normalized_doc_type = func.lower(
            func.trim(func.coalesce(WBRealizationReportRow.doc_type_name, ""))
        )
        reconcilable_clause = or_(
            WBRealizationReportRow.is_reconcilable.is_(True),
            and_(
                WBRealizationReportRow.is_reconcilable.is_(None),
                normalized_doc_type.in_(("продажа", "возврат", "sale", "return")),
            ),
        )
        signed_retail_amount = case(
            (
                and_(
                    or_(
                        WBRealizationReportRow.is_return_operation.is_(True),
                        doc_type.like("%возврат%"),
                        doc_type.like("%return%"),
                        func.coalesce(WBRealizationReportRow.retail_amount, 0) < 0,
                        func.coalesce(WBRealizationReportRow.for_pay, 0) < 0,
                    ),
                    func.coalesce(WBRealizationReportRow.retail_amount, 0) > 0,
                ),
                -func.coalesce(WBRealizationReportRow.retail_amount, 0),
            ),
            else_=func.coalesce(WBRealizationReportRow.retail_amount, 0),
        )
        value = (
            await session.execute(
                select(func.coalesce(func.sum(signed_retail_amount), 0)).where(
                    WBRealizationReportRow.account_id == account_id,
                    WBRealizationReportRow.rr_date >= date_from,
                    WBRealizationReportRow.rr_date <= date_to,
                    reconcilable_clause,
                )
            )
        ).scalar_one()
        return self._decimal(value)

    async def _finance_coverage_date_to(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> date | None:
        value = (
            await session.execute(
                select(func.max(WBRealizationReportRow.rr_date)).where(
                    WBRealizationReportRow.account_id == account_id,
                    WBRealizationReportRow.rr_date >= date_from,
                    WBRealizationReportRow.rr_date <= date_to,
                )
            )
        ).scalar_one_or_none()
        return value

    async def _mart_revenue_until(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> Decimal:
        value = (
            await session.execute(
                select(func.coalesce(func.sum(MartSKUDaily.final_revenue), 0)).where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.stat_date >= date_from,
                    MartSKUDaily.stat_date <= date_to,
                )
            )
        ).scalar_one()
        return self._decimal(value)

    async def _finance_reconciliation_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        requested_date_from: date,
        requested_date_to: date,
        account_level_expense_total: Decimal,
        closed_mart_revenue: Decimal | None = None,
        full_mart_revenue: Decimal | None = None,
    ) -> FinanceReconciliationBlock:
        (
            closed_finance_date_from,
            closed_finance_date_to,
        ) = await self._finance_closed_period(
            session,
            account_id=account_id,
            date_from=requested_date_from,
            date_to=requested_date_to,
        )
        operational_rows = await self._operational_sales_rows(
            session,
            account_id=account_id,
            date_from=requested_date_from,
            date_to=requested_date_to,
        )
        finance_rows: list[FinanceReconciliationSourceRow] = []
        if closed_finance_date_to is not None:
            closed_from = closed_finance_date_from or requested_date_from
            closed_to = min(closed_finance_date_to, requested_date_to)
            finance_rows = await self._finance_rows_for_period(
                session,
                account_id=account_id,
                date_from=closed_from,
                date_to=closed_to,
            )
        return self._build_finance_reconciliation(
            requested_date_from=requested_date_from,
            requested_date_to=requested_date_to,
            closed_finance_date_from=closed_finance_date_from,
            closed_finance_date_to=closed_finance_date_to,
            operational_rows=operational_rows,
            finance_rows=finance_rows,
            account_level_expense_total=account_level_expense_total,
            closed_mart_revenue=closed_mart_revenue,
            full_mart_revenue=full_mart_revenue,
        )

    def _blocked_reason_to_action(self, reason: str, *, health: Any) -> NextActionRead:
        mapping: dict[str, dict[str, Any]] = {
            "supplier_cost_coverage_below_threshold": {
                "action_type": "FIX_COST_TRUST",
                "title": "Подтвердите реальную себестоимость",
                "what_to_do": "Загрузите файл себестоимости поставщика или подтвердите уже загруженные реальные записи.",
                "why": "Без подтвержденной себестоимости нельзя финализировать прибыль, окупаемость, закупки и безопасную цену.",
                "how_to_fix": [
                    "Скачайте шаблон себестоимости",
                    "Заполните реальные себестоимости",
                    "Загрузите файл и подтвердите импорт",
                    "Пересчитайте аналитические таблицы и запустите проверку качества данных",
                ],
                "current_value": health.supplier_confirmed_revenue_coverage_percent,
                "required_value": 95.0,
                "unit": "процент покрытия выручки",
            },
            "unmatched_sku_detected": {
                "action_type": "MAP_UNMATCHED_SKU",
                "title": "Свяжите несопоставленные SKU",
                "what_to_do": "Через разбор проблем качества данных привяжите несопоставленный SKU к нужной карточке или классифицируйте проблему.",
                "why": "Без маппинга финансы, остатки и себестоимость попадают в карточки неверно.",
                "how_to_fix": [
                    "Откройте проблему несопоставленного SKU в сводке качества данных",
                    "Проверьте кандидатов на привязку",
                    "Свяжите SKU или укажите причину исключения",
                    "Повторно запустите проверку качества данных",
                ],
            },
            "latest_stocks_not_completed": {
                "action_type": "FIX_STOCK_SYNC",
                "title": "Доведите синхронизацию остатков до завершения",
                "what_to_do": "Перезапустите незавершенную загрузку остатков.",
                "why": "Чтобы остатки, стоимость склада и закупочные рекомендации были полными, последний снимок остатков должен завершиться успешно.",
                "how_to_fix": [
                    "Проверьте историю синхронизаций и курсоры",
                    "Запустите загрузку остатков повторно",
                    "Убедитесь, что новый снимок остатков завершен успешно",
                ],
            },
            "open_blocking_dq_issues": {
                "action_type": "RECONCILE_FINANCE",
                "title": "Закройте блокирующие проблемы качества данных",
                "what_to_do": "Классифицируйте критичные проблемы качества данных и устраните первопричину в исходных данных.",
                "why": "Открытые блокирующие проблемы останавливают бизнес-действия.",
                "how_to_fix": [
                    "Откройте главные типы проблем в сводке качества данных",
                    "Классифицируйте или закройте проблемные записи",
                    "Проверьте результат после повторной проверки качества данных",
                ],
            },
            "article_audit_mismatch": {
                "action_type": "RECONCILE_FINANCE",
                "title": "Закройте расхождение в аудите артикула",
                "what_to_do": "Проверьте расхождение между расчетной выручкой и выручкой из финансового отчета WB на уровне исходных строк.",
                "why": "Пока расхождение не закрыто, прибыли карточки доверять нельзя.",
                "how_to_fix": [
                    "Откройте детализацию аудита артикула",
                    "Сравните выручку из отчета WB и расчетную выручку",
                    "Классифицируйте причину расхождения",
                ],
            },
            "failed_sync_domains": {
                "action_type": "FIX_STOCK_SYNC",
                "title": "Восстановите загрузку данных с ошибками",
                "what_to_do": "Перезапустите участки загрузки, которые завершились с ошибкой, и устраните причину.",
                "why": "Если загрузка данных падает, следующие аналитические слои тоже становятся ненадежными.",
                "how_to_fix": [
                    "Проверьте список синхронизаций",
                    "Повторно запустите участки с ошибками",
                    "Разберите и устраните причину по тексту ошибки",
                ],
            },
        }
        payload = mapping.get(
            reason,
            {
                "action_type": "DATA_FIX_REQUIRED",
                "title": "Устраните блокер данных",
                "what_to_do": "Разберите блокирующую причину и устраните проблему в исходных данных.",
                "why": "Блокер данных не дает принять бизнес-решение.",
                "how_to_fix": [
                    "Проверьте проблему и статус синхронизации",
                    "Устраните причину",
                    "Повторно запустите проверку качества данных",
                ],
            },
        )
        return NextActionRead(
            action_type=payload["action_type"],
            priority="critical",
            title=payload["title"],
            what_to_do=payload["what_to_do"],
            why=payload["why"],
            how_to_fix=list(payload["how_to_fix"]),
            confidence="high",
            blocked_reasons=[reason],
        )

    def _data_trust_for_row(self, row: Any) -> DataTrustInfo:
        operational_trusted = row.trust_state != TRUST_STATE_DATA_BLOCKED
        blocked_reasons = list(row.blocked_reasons or [])
        cost_truth_level = (
            str(getattr(row, "cost_truth_level", "") or "").strip().lower()
        )
        placeholder_only = cost_truth_level == "placeholder"
        cost_final_accepted = self._profit_row_cost_final_accepted(row)
        financial_final = (
            row.trust_state in {TRUST_STATE_TRUSTED, TRUST_STATE_FINANCIAL_FINAL}
            and not blocked_reasons
            and bool(getattr(row, "final_profit_allowed", True))
            and cost_final_accepted
        )
        if financial_final:
            public_trust_state = TRUST_STATE_FINANCIAL_FINAL
        elif operational_trusted:
            public_trust_state = TRUST_STATE_OPERATIONAL_PROVISIONAL
        elif placeholder_only:
            public_trust_state = TRUST_STATE_TEST_ONLY
        elif blocked_reasons:
            public_trust_state = TRUST_STATE_BLOCKED
        else:
            public_trust_state = TRUST_STATE_UNKNOWN
        return DataTrustInfo(
            state=public_trust_state,
            trust_state=public_trust_state,
            business_trusted=operational_trusted,
            operational_trusted=operational_trusted,
            financial_final=financial_final,
            can_generate_business_actions=operational_trusted,
            confidence=self._trust_confidence(public_trust_state),
            blocked_reasons=blocked_reasons,
            human_message=self._trust_message(
                business_trusted=operational_trusted,
                blocked_reasons=self._blocked_reason_labels(blocked_reasons),
                trust_state=public_trust_state,
            ),
        )

    @staticmethod
    def _screen_from_endpoint(endpoint: str | None) -> tuple[str, str]:
        value = str(endpoint or "")
        if "/costs" in value:
            return ("/costs", "Открыть себестоимость")
        if "/marts/reconciliation-daily" in value or "/dq/issues/investigator" in value:
            return ("/discrepancies", "Открыть расхождения")
        if "/ads/efficiency" in value:
            return ("/money?section=ads", "Открыть рекламу в Деньгах")
        if "/money/" in value:
            return ("/money", "Открыть финансовый обзор")
        if "/sync/" in value:
            return ("/admin", "Открыть синхронизацию")
        if "/dashboard/data-health" in value or "/dq/issues" in value:
            return ("/data-fix", "Открыть починку данных")
        return ("/data-fix", "Открыть починку данных")

    def _warning_from_issue_bucket(
        self, bucket: Any, *, revenue_total: Decimal
    ) -> DataBlockerRead | None:
        if self._is_hidden_user_problem_code(getattr(bucket, "code", None)):
            return None
        labels = {
            "order_without_sale_or_return": (
                "Есть заказы без итоговой продажи или возврата",
                "GET /dashboard/data-health",
            ),
            "sales_without_stock": (
                "Есть продажи без подтвержденного остатка",
                "GET /dashboard/data-health",
            ),
            "missing_chrt_id": (
                "Есть варианты без идентификатора размера",
                "GET /dashboard/data-health",
            ),
            "stock_without_sales": ("Есть остатки без продаж", "GET /money/articles"),
        }
        meta = labels.get(bucket.code)
        if meta is None:
            return None
        title, endpoint = meta
        bucket_meta = issue_bucket_meta(bucket.code)
        guide = issue_resolution_guide(bucket.code)
        next_screen_path, next_screen_label = self._screen_from_endpoint(endpoint)
        priority = "high" if bucket.severity == "error" else "medium"
        return DataBlockerRead(
            code=bucket.code,
            priority=priority,
            title=title,
            affected_sku_count=self._int0(bucket.count),
            affected_revenue=self._float0(revenue_total)
            if bucket.code in {"order_without_sale_or_return"}
            else 0.0,
            business_impact=str(
                getattr(bucket, "business_impact", None)
                or bucket_meta.get("business_impact")
                or ""
            ),
            how_to_fix=[
                str(item)
                for item in (
                    guide.get("step_by_step")
                    or (
                        [
                            str(
                                getattr(bucket, "recommended_fix", None)
                                or bucket_meta.get("recommended_fix")
                                or ""
                            )
                        ]
                        if str(
                            getattr(bucket, "recommended_fix", None)
                            or bucket_meta.get("recommended_fix")
                            or ""
                        )
                        else []
                    )
                )
                if str(item).strip()
            ],
            simple_reason=str(guide.get("simple_reason") or ""),
            first_action=str(guide.get("first_action") or ""),
            success_check=[
                str(item)
                for item in (guide.get("success_check") or [])
                if str(item).strip()
            ],
            wait_or_fix_hint=str(guide.get("wait_or_fix_hint") or ""),
            exact_next_endpoint=endpoint,
            next_screen_path=next_screen_path,
            next_screen_label=next_screen_label,
        )

    @staticmethod
    def _issue_bucket_endpoint(code: str | None) -> str:
        normalized_code = str(code or "").strip().lower()
        mapping = {
            "finance_without_sale": "GET /marts/reconciliation-daily",
            "sale_without_finance": "GET /marts/reconciliation-daily",
            "missing_manual_cost": "GET /costs",
            "seller_other_expense_missing": "GET /costs",
            "manual_cost_old_fields_used": "GET /costs",
            "manual_cost_unresolved_sku": "GET /costs",
            "manual_cost_ambiguous_match": "GET /costs",
            "unmatched_sku": "GET /costs",
            "missing_chrt_id": "GET /dashboard/data-health",
            "expense_unclassified": "GET /money/expenses/report-rows",
            "unclassified_finance_expense": "GET /money/expenses/report-rows",
            "expense_finance_report_missing": "GET /dashboard/data-health",
            "expense_logistics_missing": "GET /money/expenses/logistics",
            "expense_ad_double_count_risk": "GET /money/expenses/breakdown",
            "stocks_task_not_ready": "GET /sync/runs",
            "scheduler_job_failed": "GET /sync/runs",
            "price_jump": "GET /prices",
            "stock_without_sales": "GET /money/articles",
            "sales_without_stock": "GET /dashboard/data-health",
            "order_without_sale_or_return": "GET /dashboard/data-health",
        }
        return mapping.get(normalized_code, "GET /dq/issues")

    def _blocker_from_issue_bucket(
        self, bucket: Any, *, revenue_total: Decimal
    ) -> DataBlockerRead | None:
        if self._is_hidden_user_problem_code(getattr(bucket, "code", None)):
            return None
        bucket_meta = issue_bucket_meta(bucket.code)
        if (
            not bool(getattr(bucket, "financial_final_blocker", False))
            or self._int0(bucket.count) <= 0
        ):
            return None
        guide = issue_resolution_guide(bucket.code)
        endpoint = self._issue_bucket_endpoint(bucket.code)
        next_screen_path = str(guide.get("next_screen_path") or "")
        next_screen_label = str(guide.get("next_screen_label") or "")
        if str(bucket.code or "") in {"finance_without_sale", "sale_without_finance"}:
            next_screen_path = "/discrepancies"
            next_screen_label = "Открыть расхождения"
        if not next_screen_path or not next_screen_label:
            next_screen_path, next_screen_label = self._screen_from_endpoint(endpoint)
        title = issue_display_message(
            bucket.code, str(getattr(bucket, "code", "") or "")
        )
        revenue_affected_codes = {
            "finance_without_sale",
            "sale_without_finance",
            "expense_unclassified",
            "unclassified_finance_expense",
            "expense_finance_report_missing",
            "expense_logistics_missing",
            "expense_ad_double_count_risk",
        }
        priority = (
            "critical"
            if str(getattr(bucket, "severity", "") or "").lower()
            in {"critical", "error"}
            else "high"
        )
        return DataBlockerRead(
            code=str(bucket.code or ""),
            priority=priority,
            title=title,
            affected_sku_count=self._int0(bucket.count),
            affected_revenue=self._float0(revenue_total)
            if str(bucket.code or "") in revenue_affected_codes
            else 0.0,
            affected_amount=0.0,
            current_value=0.0,
            required_value=0.0,
            unit="",
            business_impact=str(
                getattr(bucket, "business_impact", None)
                or bucket_meta.get("business_impact")
                or ""
            ),
            how_to_fix=[
                str(item)
                for item in (
                    guide.get("step_by_step")
                    or (
                        [
                            str(
                                getattr(bucket, "recommended_fix", None)
                                or bucket_meta.get("recommended_fix")
                                or ""
                            )
                        ]
                        if str(
                            getattr(bucket, "recommended_fix", None)
                            or bucket_meta.get("recommended_fix")
                            or ""
                        )
                        else []
                    )
                )
                if str(item).strip()
            ],
            simple_reason=str(guide.get("simple_reason") or ""),
            first_action=str(guide.get("first_action") or ""),
            success_check=[
                str(item)
                for item in (guide.get("success_check") or [])
                if str(item).strip()
            ],
            wait_or_fix_hint=str(guide.get("wait_or_fix_hint") or ""),
            exact_next_endpoint=endpoint,
            next_screen_path=next_screen_path,
            next_screen_label=next_screen_label,
        )

    def _attach_data_blocker_calculation(
        self,
        item: DataBlockerRead,
        *,
        state: Any,
        revenue_total: Decimal,
        ads_metrics: dict[str, Decimal],
    ) -> DataBlockerRead:
        code = str(item.code or "").strip().lower()
        issue_count = 0
        for bucket in getattr(state.health, "issue_buckets", []) or []:
            if self._is_hidden_user_problem_code(getattr(bucket, "code", None)):
                continue
            if str(getattr(bucket, "code", "") or "").strip().lower() == code:
                issue_count += self._int0(getattr(bucket, "count", 0))

        def money(value: Decimal | float | int | None) -> float:
            return self._float0(value)

        def inp(
            label: str, value: object, unit: str = "", source: str = ""
        ) -> dict[str, object]:
            row: dict[str, object] = {"label": label, "value": value}
            if unit:
                row["unit"] = unit
            if source:
                row["source"] = source
            return row

        if code == "supplier_cost_coverage_below_threshold":
            item.calculation_title = (
                "Покрытие выручки подтвержденной себестоимостью ниже порога"
            )
            item.calculation_formula = "supplier_confirmed_revenue_coverage_percent = supplier_confirmed_revenue / realized_revenue * 100; blocker если результат < 95%"
            item.calculation_inputs = [
                inp(
                    "Выручка за период",
                    money(revenue_total),
                    "RUB",
                    "profit_rows.realized_revenue",
                ),
                inp(
                    "Выручка с подтвержденной себестоимостью",
                    money(getattr(state.health, "supplier_confirmed_revenue", 0)),
                    "RUB",
                    "dashboard.data_health",
                ),
                inp(
                    "Текущее покрытие",
                    self._float0(
                        getattr(
                            state.health,
                            "supplier_confirmed_revenue_coverage_percent",
                            0,
                        )
                    ),
                    "%",
                    "dashboard.data_health.supplier_confirmed_revenue_coverage_percent",
                ),
                inp("Минимум для финальной прибыли", 95, "%", "business rule"),
                inp(
                    "SKU без реальной себестоимости",
                    item.affected_sku_count,
                    "SKU",
                    "profit_rows.has_real_manual_cost=false",
                ),
            ]
        elif code in {
            "missing_manual_cost",
            "seller_other_expense_missing",
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
        }:
            item.calculation_title = "Открытые DQ-проблемы по себестоимости"
            item.calculation_formula = "blocker если есть открытые issues этого типа, влияющие на финальную прибыль; count = число таких открытых issues"
            item.calculation_inputs = [
                inp(
                    "Открытых issues этого типа",
                    issue_count or item.affected_sku_count,
                    "issues",
                    "GET /dashboard/data-health.issue_buckets",
                ),
                inp(
                    "SKU без себестоимости",
                    self._int0(getattr(state.health, "missing_manual_cost_count", 0)),
                    "SKU",
                    "dashboard.data_health.missing_manual_cost_count",
                ),
                inp(
                    "Выручка без себестоимости",
                    self._float0(getattr(state.health, "revenue_without_cost", 0)),
                    "RUB",
                    "dashboard.data_health.revenue_without_cost",
                ),
                inp(
                    "Покрытие себестоимостью",
                    self._float0(
                        getattr(
                            state.health,
                            "supplier_confirmed_revenue_coverage_percent",
                            0,
                        )
                    ),
                    "%",
                    "dashboard.data_health.supplier_confirmed_revenue_coverage_percent",
                ),
            ]
        elif code in {"unmatched_sku", "unmatched_sku_detected"}:
            item.calculation_title = "SKU из источников не сопоставились с карточками"
            item.calculation_formula = "blocker если blocking_unmatched_sku_count > 0; affected_sku_count = blocking_unmatched_sku_count"
            item.calculation_inputs = [
                inp(
                    "Все открытые unmatched SKU",
                    self._int0(getattr(state.health, "open_unmatched_sku_count", 0)),
                    "SKU",
                    "dashboard.data_health.open_unmatched_sku_count",
                ),
                inp(
                    "Блокирующие unmatched SKU",
                    self._int0(
                        getattr(state.health, "blocking_unmatched_sku_count", 0)
                    ),
                    "SKU",
                    "dashboard.data_health.blocking_unmatched_sku_count",
                ),
                inp(
                    "Классифицированные unmatched SKU",
                    self._int0(
                        getattr(state.health, "classified_unmatched_sku_count", 0)
                    ),
                    "SKU",
                    "dashboard.data_health.classified_unmatched_sku_count",
                ),
            ]
        elif code in {
            "ads_not_allocated_to_profitability",
            "ads_overallocated_to_profitability",
        }:
            item.calculation_title = (
                "Сверка рекламы из источника с рекламой в прибыли карточек"
            )
            item.calculation_formula = "current_allocation_percent = allocated_ad_spend / ads_source_spend * 100; target_allocation_percent = 100; warning если есть unallocated_spend или overallocated_spend"
            item.calculation_inputs = [
                inp(
                    "Реклама в источнике WB",
                    money(ads_metrics.get("ads_source_spend")),
                    "RUB",
                    "ads source",
                ),
                inp(
                    "Реклама, попавшая в карточки",
                    money(ads_metrics.get("mart_ads_allocated_spend")),
                    "RUB",
                    "mart_sku_daily.ad_spend",
                ),
                inp(
                    "Распределенная аллоцируемая реклама",
                    money(ads_metrics.get("ads_allocated_spend")),
                    "RUB",
                    "allocation metrics",
                ),
                inp(
                    "Не распределено",
                    money(ads_metrics.get("ads_unallocated_spend")),
                    "RUB",
                    "allocation metrics",
                ),
                inp(
                    "Перераспределено сверх источника",
                    money(ads_metrics.get("ads_overallocated_spend")),
                    "RUB",
                    "allocation metrics",
                ),
                inp(
                    "Текущая аллокация",
                    money(ads_metrics.get("ads_allocation_percent_raw")),
                    "%",
                    "allocation metrics",
                ),
                inp("Целевая аллокация", 100, "%", "business rule"),
            ]
        elif code in {"finance_without_sale", "sale_without_finance"}:
            item.calculation_title = "Открытые расхождения между операционными продажами и финансовым отчетом WB"
            item.calculation_formula = "count = число открытых DQ issues по сверке finance/sales; financial_final_blocker берется из effective_financial_final_blocker"
            item.calculation_inputs = [
                inp(
                    "Открытых issues этого типа",
                    issue_count or item.affected_sku_count,
                    "issues",
                    "GET /dashboard/data-health.issue_buckets",
                ),
                inp(
                    "Финальных finance mismatch блокеров",
                    self._int0(
                        getattr(state.health, "blocking_finance_mismatch_count", 0)
                    ),
                    "issues",
                    "dashboard.data_health.blocking_finance_mismatch_count",
                ),
                inp(
                    "Затронутая выручка периода",
                    money(revenue_total),
                    "RUB",
                    "profit_rows.realized_revenue",
                ),
            ]
        elif code == "failed_sync_domains":
            failed_domains = list(getattr(state.health, "failed_domains", []) or [])
            item.calculation_title = "Домены синхронизации завершились ошибкой"
            item.calculation_formula = "blocker если failed_domains не пустой; count = число доменов с последней ошибкой"
            item.calculation_inputs = [
                inp(
                    "Доменов с ошибкой",
                    len(failed_domains),
                    "domains",
                    "dashboard.data_health.failed_domains",
                ),
                inp(
                    "Список доменов",
                    ", ".join(str(x) for x in failed_domains) or "—",
                    "",
                    "dashboard.data_health.failed_domains",
                ),
            ]
        elif code == "latest_stocks_not_completed":
            item.calculation_title = "Последняя загрузка остатков не завершена"
            item.calculation_formula = "blocker если latest_stocks_status не completed/success; affected_sku_count = число карточек в контроле"
            item.calculation_inputs = [
                inp(
                    "Последний статус остатков",
                    str(getattr(state.health, "latest_stocks_status", "") or "unknown"),
                    "",
                    "dashboard.data_health.latest_stocks_status",
                ),
                inp(
                    "Карточек под контролем",
                    len(getattr(state, "control_rows", []) or []),
                    "cards",
                    "control_rows",
                ),
                inp(
                    "Выручка периода",
                    money(revenue_total),
                    "RUB",
                    "profit_rows.realized_revenue",
                ),
            ]
        else:
            item.calculation_title = "Открытые проблемы качества данных"
            item.calculation_formula = "count = число открытых issues с этим code; blocker/warning определяется severity и financial_final_blocker"
            item.calculation_inputs = [
                inp(
                    "Открытых issues этого типа",
                    issue_count or item.affected_sku_count,
                    "issues",
                    "GET /dashboard/data-health.issue_buckets",
                ),
                inp(
                    "Затронутая выручка периода",
                    money(revenue_total)
                    if item.affected_revenue
                    else item.affected_revenue,
                    "RUB",
                    "profit_rows.realized_revenue",
                ),
            ]

        endpoints = list(
            dict.fromkeys(
                [
                    item.exact_next_endpoint,
                    *item.related_endpoints,
                    "GET /money/data-blockers",
                    "GET /dashboard/data-health",
                ]
            )
        )
        item.source_endpoints = [endpoint for endpoint in endpoints if endpoint]
        return item

    @staticmethod
    def _data_blockers_message(
        *, blockers_count: int, warnings_count: int, can_generate_business_actions: bool
    ) -> str:
        if blockers_count > 0:
            return "Есть блокеры финальной сверки: сначала разберите их, затем считайте прибыль финальной."
        if warnings_count > 0 and can_generate_business_actions:
            return "Глобальных блокеров нет, но открытые предупреждения и ошибки снижают доверие к части прибыли и решениям по карточкам."
        if warnings_count > 0:
            return "Есть предупреждения по данным, которые требуют внимания перед финальными решениями."
        return "Критичных блокеров и существенных слоев риска не обнаружено."

    def _build_card_verdict(self, row: Any, price_row: Any | None) -> CardVerdict:
        status = "watch"
        label = "Наблюдение"
        text = "По карточке сейчас не видно резкого риска."
        if row.trust_state == TRUST_STATE_DATA_BLOCKED:
            status = "data_blocked"
            label = "Сначала исправьте данные"
            text = "Данных по карточке недостаточно для окончательного бизнес-решения."
        elif row.trust_state == TRUST_STATE_TEST_ONLY:
            status = "provisional"
            label = "Предварительный анализ"
            text = "По карточке есть бизнес-анализ, но себестоимость поставщика еще не подтверждена полностью."
        elif row.net_profit is not None and row.net_profit < 0:
            status = "loss"
            label = "Убыточная карточка"
            text = (
                "В текущем периоде карточка показывает убыток или прибыль около нуля."
            )
        elif row.sku_status == "PROTECT_STOCK":
            status = "stock_risk"
            label = "Риск остатка"
            text = "Остаток может быстро закончиться относительно спроса."
        elif row.sku_status == "LIQUIDATE":
            status = "overstock"
            label = "Замороженный остаток"
            text = "Остаток слишком глубокий относительно спроса, деньги заморожены в товаре."
        elif (
            price_row is not None
            and price_row.safe_price_gap is not None
            and price_row.safe_price_gap < 0
        ):
            status = "price_risk"
            label = "Риск цены"
            text = (
                "Текущая цена может быть ниже точки безубыточности или целевой маржи."
            )
        elif row.ad_spend > 0 and row.net_profit is not None and row.net_profit <= 0:
            status = "ad_risk"
            label = "Риск рекламы"
            text = "Реклама активна, но чистая прибыль не положительная."
        elif row.net_profit is not None and row.net_profit > 0:
            status = "profitable"
            label = "Прибыльная"
            text = "Карточка приносит прибыль, и текущая экономика положительная."
        return CardVerdict(
            status=status,
            label=label,
            short_text=text,
            confidence=self._trust_confidence(row.trust_state),
        )

    def _synthesized_row_action(
        self, row: Any, *, price_row: Any | None, purchase_row: Any | None
    ) -> NextActionRead | None:
        if row.trust_state == TRUST_STATE_DATA_BLOCKED:
            reasons = list(row.blocked_reasons or [])
            if (
                "missing_manual_cost" in reasons
                or "supplier_cost_not_confirmed" in reasons
            ):
                return NextActionRead(
                    action_type="FIX_COST_TRUST",
                    priority="critical",
                    title="Нужно подтвердить себестоимость",
                    what_to_do="Подтвердите реальную себестоимость поставщика через загрузку файла себестоимости.",
                    why="Без подтвержденной себестоимости прибыль и закупочные рекомендации могут быть неверными.",
                    how_to_fix=[
                        "Загрузите файл себестоимости",
                        "Подтвердите импорт",
                        "Пересчитайте аналитические таблицы",
                    ],
                    confidence="high",
                    linked_entity={
                        "sku_id": row.sku_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                    },
                    blocked_reasons=reasons,
                )
            if (
                "finance_not_confirmed" in reasons
                or "open_blocking_dq_issues" in reasons
            ):
                return NextActionRead(
                    action_type="RECONCILE_FINANCE",
                    priority="critical",
                    title="Нужно закрыть расхождение по выручке",
                    what_to_do="Проверьте и устраните расхождения между финансовым отчетом WB и продажами.",
                    why="Пока финансы не подтверждены, прибыль карточки не окончательная.",
                    how_to_fix=[
                        "Откройте детализацию аудита артикула",
                        "Классифицируйте расхождение",
                        "Повторно запустите проверку качества данных",
                    ],
                    confidence="high",
                    linked_entity={
                        "sku_id": row.sku_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                    },
                    blocked_reasons=reasons,
                )
            if price_row is not None and price_row.not_computable_reason in {
                "price_not_mapped",
                "missing_price",
            }:
                return NextActionRead(
                    action_type="FIX_PRICE_MAPPING",
                    priority="high",
                    title="Нужно исправить маппинг цены",
                    what_to_do="Заполните сопоставление цены или данные о цене по размерам.",
                    why="Если цена не найдена, нельзя посчитать безопасную цену и защиту маржи.",
                    how_to_fix=[
                        "Проверьте цены WB по размерам",
                        "Подтвердите сопоставление цены в данных карточки",
                    ],
                    confidence="medium",
                    linked_entity={
                        "sku_id": row.sku_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                    },
                    blocked_reasons=reasons,
                )
            return NextActionRead(
                action_type="DATA_FIX_REQUIRED",
                priority="critical",
                title="Сначала нужно закрыть проблему в данных",
                what_to_do="Исправьте блокирующие данные по карточке.",
                why="Пока данные заблокированы, окончательное действие рекомендовать нельзя.",
                how_to_fix=[
                    "Проверьте причины блокировки",
                    "Устраните проблему в исходных данных",
                    "Перезапустите проверку качества данных и аналитические таблицы",
                ],
                confidence="medium",
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
                blocked_reasons=reasons,
            )
        if (
            purchase_row is not None
            and purchase_row.status == "REORDER"
            and purchase_row.recommended_qty > 0
        ):
            return NextActionRead(
                action_type="REORDER",
                priority="high",
                title="Нужно дозаказать",
                what_to_do="Подготовьте дозаказ по рекомендованному количеству.",
                why=purchase_row.reason,
                how_to_fix=[
                    "Проверьте рекомендованное количество",
                    "Подтвердите бюджет",
                    "Разместите закупку",
                ],
                expected_effect_amount=self._float0(row.net_profit),
                required_cash=self._float0(purchase_row.required_cash),
                confidence="high"
                if row.trust_state == TRUST_STATE_TRUSTED
                else "medium",
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
            )
        if purchase_row is not None and purchase_row.status == "PROTECT_STOCK":
            return NextActionRead(
                action_type="PROTECT_STOCK",
                priority="medium",
                title="Нужно защитить остаток",
                what_to_do="Не усиливайте спрос по карточке, пока не придет товар в пути.",
                why=purchase_row.reason,
                business_reason=purchase_row.reason,
                next_step="Не усиливайте спрос по карточке, пока не придет товар в пути.",
                how_to_fix=[
                    "Проверьте входящий транзит",
                    "Не запускайте агрессивные промо",
                    "Пересмотрите состояние после прихода товара",
                ],
                confidence=getattr(
                    purchase_row, "confidence", self._trust_confidence(row.trust_state)
                ),
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
                money_effect={
                    "protected_revenue": self._float0(getattr(row, "revenue", None)),
                    **dict(getattr(purchase_row, "money_effect", {}) or {}),
                },
            )
        if row.net_profit is not None and row.net_profit < 0:
            action_type = (
                "PRICE_INCREASE_REVIEW"
                if price_row is not None
                and price_row.safe_price_gap is not None
                and price_row.safe_price_gap < 0
                else "DO_NOT_REORDER"
            )
            return NextActionRead(
                action_type=action_type,
                priority="high",
                title="Нужно пересмотреть экономику карточки",
                what_to_do="Проверьте цену, рекламу и себестоимость, чтобы закрыть причину убытка.",
                why="В текущем периоде карточка не дает положительной прибыли.",
                how_to_fix=[
                    "Проверьте безопасную цену",
                    "Проверьте рекламные расходы",
                    "Подтвердите себестоимость",
                ],
                expected_effect_amount=abs(float(row.net_profit)),
                confidence="high",
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
            )
        if purchase_row is not None and purchase_row.status == "LIQUIDATE":
            return NextActionRead(
                action_type="LIQUIDATE_STOCK",
                priority="high",
                title="Нужно снизить остаток",
                what_to_do="Сократите остаток через промо или распродажу.",
                why=purchase_row.reason,
                how_to_fix=["Выберите промо-стратегию", "Ограничьте повторную закупку"],
                expected_effect_amount=self._float0(row.stock_value),
                required_cash=0.0,
                confidence="medium",
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
                money_effect=dict(getattr(purchase_row, "money_effect", {}) or {}),
            )
        if (
            price_row is not None
            and price_row.safe_price_gap is not None
            and price_row.safe_price_gap < 0
        ):
            return NextActionRead(
                action_type="PRICE_INCREASE_REVIEW",
                priority="high",
                title="Нужно проверить повышение цены",
                what_to_do="Перепроверьте цену относительно минимальной цены без убытка и целевой маржи.",
                why="Текущая цена может быть слишком низкой для защиты прибыли.",
                how_to_fix=[
                    "Подтвердите текущую цену",
                    "Сравните с минимальной ценой без убытка",
                    "Обновите цену при необходимости",
                ],
                expected_effect_amount=abs(float(price_row.safe_price_gap)),
                confidence=price_row.confidence,
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
            )
        if row.ad_spend > 0 and row.net_profit is not None and row.net_profit <= 0:
            return NextActionRead(
                action_type="AD_PAUSE_REVIEW",
                priority="medium",
                title="Нужно проверить остановку рекламы",
                what_to_do="Приостановите убыточные кампании и пересмотрите долю рекламы в выручке.",
                why="Рекламные расходы съедают прибыль.",
                how_to_fix=[
                    "Проверьте долю рекламы в выручке",
                    "Отсортируйте кампании",
                    "Перенастройте ставки",
                ],
                expected_effect_amount=float(row.ad_spend),
                confidence="medium",
                linked_entity={
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                },
            )
        return None

    def _default_row_action(self, row: Any) -> NextActionRead:
        return NextActionRead(
            action_type="WATCH",
            priority="low",
            title="Оставьте карточку под наблюдением",
            what_to_do="Пока оставьте карточку под наблюдением и регулярно проверяйте динамику.",
            why="Сейчас не выявлено действия, которое нужно выполнить немедленно.",
            how_to_fix=[
                "Следите за ключевыми показателями",
                "Проверяйте тренд по цене, остаткам и прибыли",
            ],
            confidence=self._trust_confidence(row.trust_state),
            linked_entity={
                "sku_id": row.sku_id,
                "nm_id": row.nm_id,
                "vendor_code": row.vendor_code,
            },
        )

    async def _missing_money_card_detail(
        self,
        session: AsyncSession,
        *,
        state: MoneyRuntimeState,
        account_id: int,
        sku_id: int,
        date_from: date,
        date_to: date,
    ) -> MoneyCardDetailRead | None:
        detail = await self.core_sku.get_sku_detail(
            session,
            sku_id=sku_id,
            date_from=date_from,
            date_to=date_to,
        )
        if detail is None or detail.sku.account_id != account_id:
            return None

        sku = detail.sku
        unit_cost = self._decimal(sku.total_unit_cost or sku.cost_price)
        stock_qty = self._decimal(sku.latest_quantity)
        stock_value = (
            stock_qty * unit_cost if stock_qty > 0 and unit_cost > 0 else Decimal("0")
        )
        sales_velocity = Decimal(
            str(max(int(sku.last_30d_sales_qty or 0), 0))
        ) / Decimal("30")
        days_of_stock = (
            stock_qty / sales_velocity
            if stock_qty > 0 and sales_velocity > 0
            else Decimal("0")
        )
        trust = DataTrustInfo(
            state=TRUST_STATE_BLOCKED,
            trust_state=TRUST_STATE_BLOCKED,
            business_trusted=False,
            operational_trusted=False,
            financial_final=False,
            can_generate_business_actions=False,
            confidence="low",
            cost_trust_policy=str(
                state.settings.get("cost_trust_policy") or "operator_baseline"
            ),
            blocked_reasons=["money_card_not_in_selected_period"],
            human_message="SKU найден в каталоге, но в выбранном периоде нет денежных строк для карточки.",
        )
        meta = MoneyMeta(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            generated_at=utcnow(),
            data_trust=trust,
        )
        ads = CardAdsBlock(
            spend=0.0,
            source_spend=0.0,
            raw_allocated_spend=0.0,
            capped_allocated_spend=0.0,
            allocated_spend=0.0,
            unallocated_spend=0.0,
            overallocated_spend=0.0,
            drr_percent=0.0,
            drr_percent_source=0.0,
            status="no_ads",
            allocation_status="no_source_data",
            profit_allocation_status="no_source_data",
            allocation_method="",
            allocation_confidence="low",
            final_profit_allowed=False,
        )
        account_level_logistics_total = getattr(
            state, "account_level_logistics_total", Decimal("0")
        )
        wb_expenses = CardExpenseBreakdown(
            total_wb_expenses=0.0,
            direct=0.0,
            account_level=self._float0(state.account_level_expense_total),
            account_level_logistics=self._float0(account_level_logistics_total),
            allocated_overhead=0.0,
            unallocated=self._float0(state.account_level_expense_total),
            unallocated_logistics=self._float0(account_level_logistics_total),
            logistics_mapping_status="not_linked_to_sku"
            if account_level_logistics_total > 0
            else "",
            confidence="low",
            reason="money_card_not_in_selected_period",
            status="no_money_rows",
        )
        money = CardMoneyBlock(
            revenue=0.0,
            revenue_final=0.0,
            for_pay=0.0,
            wb_expenses=wb_expenses,
            ads=ads,
            cogs=CardCogsBlock(
                unit_cost=self._float0(unit_cost),
                estimated_cogs=0.0,
                truth_level=sku.cost_truth_level or "",
                cost_truth_label=self._cost_truth_label(sku.cost_truth_level),
                supplier_confirmed=bool(sku.has_real_manual_cost),
                business_trusted=bool(sku.business_trusted),
                confidence="medium" if sku.has_manual_cost else "low",
                reason="" if sku.has_manual_cost else "missing_cost",
            ),
            profit=CardProfitBlock(
                before_ads=0.0,
                after_allocated_ads=0.0,
                after_source_ads=0.0,
                after_overhead=0.0,
                with_allocated_overhead=0.0,
                after_ads=0.0,
                net_profit_after_all_expenses=0.0,
                margin_after_ads_percent=0.0,
                roi_after_ads_percent=0.0,
                roi_on_cogs_percent=0.0,
                stock_roi_percent=0.0,
                roas_percent=0.0,
                confidence="low",
            ),
            wb_expenses_total=0.0,
            seller_cogs=0.0,
            seller_other_expense=0.0,
            total_seller_expenses=0.0,
            total_seller_costs=0.0,
            additional_income=0.0,
            ad_spend_operational=0.0,
            ad_spend_finance=0.0,
            ad_spend_final=0.0,
            ad_spend_source=AD_SPEND_SOURCE_NONE,
            ad_spend_delta=0.0,
            net_profit_after_all_expenses=0.0,
            expense_data_quality="missing_money_rows",
            stock_value=self._float0(stock_value),
            unit_economics=MoneyUnitEconomicsRead(
                price=self._float0(sku.current_discounted_price or sku.current_price),
                cost_price=self._float0(unit_cost) if unit_cost > 0 else None,
                ads=0.0,
                unit_profit=None,
                margin_pct=None,
                trust_state=TRUST_STATE_BLOCKED,
                blockers=["money_card_not_in_selected_period"],
            ),
        )
        action = NextActionRead(
            action_type="CHECK_PERIOD_OR_SYNC",
            action_group="data_fix",
            priority="low",
            title="Нет денежных строк по SKU в выбранном периоде",
            what_to_do="Расширьте период или проверьте, были ли продажи, финансы и витрина mart_sku_daily по этому SKU.",
            why="SKU есть в каталоге, но за выбранные даты нет строки прибыльности, поэтому деньги и прибыль по нему не считаются.",
            how_to_fix=[
                "Проверьте другой период",
                "Откройте карточку товара по nm_id",
                "Если продажи должны быть, перезапустите синхронизацию продаж/финансов и пересчет mart_sku_daily",
            ],
            confidence="high",
            linked_entity={
                "sku_id": sku.id,
                "nm_id": sku.nm_id,
                "vendor_code": sku.vendor_code,
            },
            affected_nm_ids=[int(sku.nm_id)] if sku.nm_id is not None else [],
            affected_sku_ids=[int(sku.id)],
            blocked_reasons=["money_card_not_in_selected_period"],
            source_endpoint=f"GET /api/v1/money/cards/{sku.id}",
        )
        current_price = self._float0(sku.current_price)
        discounted_price = self._float0(sku.current_discounted_price)
        return MoneyCardDetailRead(
            **self._response_cache_fields(state),
            meta=meta,
            identity=MoneyIdentity(
                sku_id=sku.id,
                nm_id=sku.nm_id,
                vendor_code=sku.vendor_code,
                barcode=sku.barcode,
                title=sku.title,
                brand=sku.brand,
                subject_name=sku.subject_name,
            ),
            answer=MoneyCardAnswer(
                status="no_money_data",
                title="SKU найден, но денежных данных за период нет",
                short_text="Каталожная карточка существует, однако в выбранном окне нет продаж/финансовых строк для расчета прибыли.",
                decision="watch",
                main_next_step=action.what_to_do,
                main_reason=action.why,
            ),
            cost_coverage=CostCoverageBlock(
                cost_truth_level=sku.cost_truth_level or "missing",
                can_use_for_operations=bool(sku.operational_trusted),
                can_use_for_final_profit=False,
                message="Себестоимость показана из каталога SKU; финальная прибыль недоступна без денежных строк периода.",
            ),
            money=money,
            expense_breakdown=self._article_expense_breakdown(wb_expenses),
            operations=CardOperationsBlock(issue="Нет продаж в выбранном периоде"),
            funnel=CardFunnelBlock(issue="Нет воронки в выбранном периоде"),
            stock=CardStockBlock(
                quantity=self._float0(stock_qty),
                quantity_full=self._float0(
                    sku.latest_quantity_full
                    if sku.latest_quantity_full is not None
                    else stock_qty
                ),
                stock_value=self._float0(stock_value),
                stock_value_confidence="medium" if stock_value > 0 else "low",
                stock_value_reason=""
                if stock_value > 0
                else "stock_value_not_computable",
                days_of_stock=self._float0(days_of_stock),
                sales_velocity_daily=self._float0(sales_velocity),
                overstock_value=0.0,
                stock_status="unknown" if stock_qty <= 0 else "ok",
                in_transit_qty=self._float0(
                    (sku.latest_in_way_to_client or 0)
                    + (sku.latest_in_way_from_client or 0)
                ),
                in_transit_value=0.0,
            ),
            price=CardPriceBlock(
                current_price=current_price,
                current_discounted_price=discounted_price,
                discount=self._price_discount_percent(
                    current_price=current_price,
                    current_discounted_price=discounted_price,
                    explicit_discount=sku.seller_discount,
                ),
                status="ready"
                if current_price > 0 or discounted_price > 0
                else "not_computable",
                confidence="medium"
                if current_price > 0 or discounted_price > 0
                else "low",
                price_source="core_sku",
                not_computable_reason=""
                if current_price > 0 or discounted_price > 0
                else "price_not_loaded",
            ),
            reconciliation=CardReconciliationBlock(
                mart_matches_article=False,
                mart_matches_finance=False,
                finance_matches_operational=False,
                revenue_matches_mart=False,
                mart_revenue_total=0.0,
                article_revenue_total=0.0,
                finance_report_revenue_total=0.0,
                difference_amount=0.0,
                difference_ratio_percent=0.0,
                status="no_money_rows",
                mismatch_reason="money_card_not_in_selected_period",
                root_cause_candidates=["no_mart_sku_daily_rows_for_period"],
                next_debug_endpoint=f"/core-sku/{sku.id}",
                business_effect="profit_not_computable",
            ),
            problems=[
                CardProblem(
                    code="money_card_not_in_selected_period",
                    severity="info",
                    title="Нет денежных строк за выбранный период",
                    business_impact="Прибыль, маржа и ROI по этому SKU не рассчитываются для текущего окна.",
                    fix_hint="Расширьте период или проверьте синхронизацию продаж/финансов и пересчет витрин.",
                )
            ],
            next_actions=[action],
            article_summary=ArticleSummaryBlock(
                nm_id=int(sku.nm_id) if sku.nm_id is not None else 0,
                title=sku.title,
                decision="watch",
            )
            if sku.nm_id is not None
            else None,
            variant_breakdown=[],
            profit_variants=ProfitVariants(),
            finality=FinalityBlock(
                profit_final=False,
                restock_final=False,
                price_final=False,
                reasons=["money_card_not_in_selected_period"],
            ),
        )

    def _build_card_money(
        self,
        profit_row: Any,
        row: Any,
        *,
        price_row: Any | None,
        purchase_row: Any | None = None,
        ads_source_spend: Decimal = Decimal("0"),
        account_level_expense_total: Decimal = Decimal("0"),
        account_level_logistics_total: Decimal = Decimal("0"),
        allocated_overhead: Decimal = Decimal("0"),
    ) -> CardMoneyBlock:
        wb_status = ""
        revenue_value = compute_revenue_final(profit_row)
        seller_cost_total = total_seller_costs(profit_row)
        additional_income_value = expense_additional_income(profit_row)
        row_ad = self._row_ad_components(profit_row, fallback_source=ads_source_spend)
        operational_ad_spend = self._decimal(row_ad["ad_spend_operational"])
        finance_ad_spend = self._decimal(row_ad["ad_spend_finance"])
        final_ad_spend = self._decimal(row_ad["ad_spend_final"])
        ad_spend_source = str(row_ad["ad_spend_source"])
        ad_spend_delta = self._decimal(row_ad["ad_spend_delta"])
        effective_source_spend = (
            operational_ad_spend
            if operational_ad_spend > 0
            else self._decimal(getattr(row, "source_ad_spend", None))
            if getattr(row, "source_ad_spend", None) is not None
            else ads_source_spend
        )
        if effective_source_spend <= 0 and ads_source_spend > 0:
            effective_source_spend = ads_source_spend
        if ad_spend_source == AD_SPEND_SOURCE_FINANCE:
            raw_ads_allocated = final_ad_spend
            ads_allocated = final_ad_spend
            ads_overallocated = Decimal("0")
            ads_unallocated = max(
                Decimal("0"), effective_source_spend - operational_ad_spend
            )
            allocation_status = "finance_final"
            final_profit_allowed = True
        else:
            raw_ads_allocated = self._decimal(getattr(row, "raw_ad_spend", None))
            ads_allocated = self._decimal(
                getattr(row, "capped_ad_spend", None)
                if getattr(row, "capped_ad_spend", None) is not None
                else final_ad_spend
            )
            if raw_ads_allocated <= 0:
                raw_ads_allocated = max(ads_allocated, effective_source_spend)
            ads_overallocated = self._decimal(
                getattr(row, "overallocated_ad_spend", None)
            )
            if ads_overallocated <= 0 and effective_source_spend > 0:
                ads_overallocated = max(
                    Decimal("0"), raw_ads_allocated - effective_source_spend
                )
            ads_unallocated = self._decimal(getattr(row, "unallocated_ad_spend", None))
            if ads_unallocated <= 0 and effective_source_spend > 0:
                ads_unallocated = max(
                    Decimal("0"), effective_source_spend - ads_allocated
                )
            allocation_status = str(
                getattr(row, "ads_allocation_status", None)
                or (
                    "overallocated"
                    if ads_overallocated > 0
                    else "matched"
                    if effective_source_spend > 0 and ads_unallocated <= 0
                    else "partial"
                    if effective_source_spend > 0
                    else "no_source_data"
                )
            )
            final_profit_allowed = bool(
                getattr(row, "final_profit_allowed", ads_overallocated <= 0)
            )
        ad_spend = self._float0(final_ad_spend if final_ad_spend > 0 else ads_allocated)
        drr_percent = (
            self._percent0(final_ad_spend, revenue_value)
            if final_ad_spend > 0
            else self._float0(row.drr_percent)
        )
        drr_percent_source = self._percent0(effective_source_spend, revenue_value)
        unit_cost_decimal = (
            self._decimal(profit_row.estimated_cogs)
            / Decimal(str(profit_row.net_units))
            if int(profit_row.net_units or 0) > 0
            and self._decimal(profit_row.estimated_cogs) > 0
            else Decimal("0")
        )
        stock_components = self._stock_value_components(
            row,
            profit_row,
            purchase_row,
            business_trusted=row.trust_state == TRUST_STATE_TRUSTED,
        )
        wb_expenses_total = self._wb_expenses_total(profit_row)
        direct_logistics_total = self._expense_value(
            profit_row, EXPENSE_CATEGORY_WB_LOGISTICS, "logistics"
        ) + self._expense_value(profit_row, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL)
        has_account_level_logistics = account_level_logistics_total > Decimal("0.01")
        logistics_not_linked_to_sku = (
            has_account_level_logistics and direct_logistics_total <= Decimal("0.01")
        )
        logistics_partially_linked_to_sku = (
            has_account_level_logistics and direct_logistics_total > Decimal("0.01")
        )
        explicit_profit_before_ads = getattr(
            profit_row, "estimated_profit_before_ads", None
        )
        if explicit_profit_before_ads is not None:
            profit_before_ads = self._decimal(explicit_profit_before_ads)
        else:
            profit_before_ads = (
                revenue_value
                + additional_income_value
                - wb_expenses_total
                - seller_cost_total
            )
        explicit_profit_after_ads = getattr(
            profit_row, "estimated_profit_after_ads", None
        )
        if explicit_profit_after_ads is not None:
            profit_after_allocated_ads = self._decimal(explicit_profit_after_ads)
        elif getattr(row, "net_profit", None) is not None:
            profit_after_allocated_ads = self._decimal(getattr(row, "net_profit", None))
        elif getattr(profit_row, "estimated_profit", None) is not None:
            profit_after_allocated_ads = self._decimal(
                getattr(profit_row, "estimated_profit", None)
            )
        else:
            profit_after_allocated_ads = profit_before_ads - final_ad_spend
        profit_after_source_ads = profit_before_ads - effective_source_spend
        explicit_net_profit = getattr(profit_row, "net_profit_after_all_expenses", None)
        if explicit_net_profit is not None:
            net_profit_all_expenses = self._decimal(explicit_net_profit)
        else:
            net_profit_all_expenses = (
                revenue_value
                + additional_income_value
                - wb_expenses_total
                - seller_cost_total
                - extra_ad_spend_not_in_wb_expenses(profit_row)
            )
        truth_level = profit_row.cost_truth_level or ""
        cost_confidence = (
            "high"
            if truth_level == "supplier_confirmed"
            and row.trust_state == TRUST_STATE_TRUSTED
            else "medium"
            if truth_level == "operator_baseline"
            else "low"
        )
        cost_reason = (
            ""
            if truth_level == "supplier_confirmed"
            else "operator_baseline_not_supplier_confirmed"
            if truth_level == "operator_baseline"
            else "placeholder_cost"
            if truth_level == "placeholder"
            else "missing_cost"
        )
        if logistics_not_linked_to_sku:
            wb_status = "account_level_logistics_not_allocated"
        elif logistics_partially_linked_to_sku:
            wb_status = "account_level_logistics_partially_allocated"
        elif (
            float(profit_row.commission or 0) == 0
            and float(profit_row.logistics or 0) == 0
            and float(profit_row.storage or 0) == 0
            and int(profit_row.finance_rows or 0) > 0
        ):
            wb_status = "suspicious_zero_expenses"
        elif wb_expenses_total <= 0 and account_level_expense_total > 0:
            wb_status = "account_level_overhead_only"
        wb_reason = ""
        if wb_status == "account_level_logistics_not_allocated":
            wb_reason = "wb_logistics_not_linked_to_sku"
        elif wb_status == "account_level_logistics_partially_allocated":
            wb_reason = "wb_logistics_partially_linked_to_sku"
        elif wb_status == "suspicious_zero_expenses":
            wb_reason = "finance_expenses_not_linked_to_sku_grain"
        elif wb_status == "account_level_overhead_only":
            wb_reason = "строки финансового отчета не содержат номера артикула или штрихкода либо относятся к расходам магазина целиком"
        return CardMoneyBlock(
            revenue=self._float0(revenue_value),
            revenue_final=self._float0(revenue_value),
            for_pay=self._float0(profit_row.for_pay),
            wb_expenses=CardExpenseBreakdown(
                wb_commission=self._float0(
                    getattr(
                        profit_row,
                        EXPENSE_CATEGORY_WB_COMMISSION,
                        getattr(profit_row, "commission", 0),
                    )
                ),
                payment_processing=self._float0(
                    getattr(
                        profit_row,
                        EXPENSE_CATEGORY_PAYMENT_PROCESSING,
                        getattr(profit_row, "acquiring_fee", 0),
                    )
                ),
                pvz_reward=self._float0(
                    getattr(profit_row, EXPENSE_CATEGORY_PVZ_REWARD, 0)
                ),
                wb_logistics=self._float0(
                    getattr(profit_row, EXPENSE_CATEGORY_WB_LOGISTICS, 0)
                ),
                wb_logistics_rebill=self._float0(
                    getattr(profit_row, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL, 0)
                ),
                acceptance=self._float0(
                    getattr(
                        profit_row,
                        EXPENSE_CATEGORY_ACCEPTANCE,
                        getattr(profit_row, "paid_acceptance", 0),
                    )
                ),
                penalty=self._float0(
                    getattr(
                        profit_row,
                        EXPENSE_CATEGORY_PENALTY,
                        getattr(profit_row, "penalties", 0),
                    )
                ),
                deduction=self._float0(
                    getattr(profit_row, EXPENSE_CATEGORY_DEDUCTION, 0)
                ),
                marketing_deduction=self._float0(
                    getattr(profit_row, EXPENSE_CATEGORY_MARKETING_DEDUCTION, 0)
                ),
                loyalty=self._float0(getattr(profit_row, EXPENSE_CATEGORY_LOYALTY, 0)),
                other_wb_expenses=self._float0(
                    getattr(profit_row, "other_wb_expenses", 0)
                ),
                total_wb_expenses=self._float0(wb_expenses_total),
                commission=self._float0(profit_row.commission),
                acquiring_fee=self._float0(profit_row.acquiring_fee),
                logistics=self._float0(profit_row.logistics),
                paid_acceptance=self._float0(profit_row.paid_acceptance),
                storage=self._float0(profit_row.storage),
                penalties=self._float0(profit_row.penalties),
                deductions=self._float0(profit_row.deductions),
                additional_payments=self._float0(additional_income_value),
                direct=self._float0(wb_expenses_total),
                account_level=self._float0(account_level_expense_total),
                account_level_logistics=self._float0(account_level_logistics_total),
                allocated_overhead=self._float0(allocated_overhead),
                unallocated=self._float0(
                    max(account_level_expense_total - allocated_overhead, Decimal("0"))
                ),
                unallocated_logistics=self._float0(account_level_logistics_total),
                logistics_mapping_status="not_linked_to_sku"
                if logistics_not_linked_to_sku
                else "partial_account_level"
                if logistics_partially_linked_to_sku
                else "linked"
                if direct_logistics_total > 0
                else "",
                confidence="low"
                if wb_status
                in {
                    "suspicious_zero_expenses",
                    "account_level_overhead_only",
                    "account_level_logistics_not_allocated",
                    "account_level_logistics_partially_allocated",
                }
                else "medium"
                if int(getattr(profit_row, "finance_rows", 0) or 0) > 0
                else "low",
                reason=wb_reason
                if wb_reason
                else ""
                if int(getattr(profit_row, "finance_rows", 0) or 0) > 0
                else "account_level_expenses_not_allocated",
                status=wb_status,
            ),
            ads=CardAdsBlock(
                spend=ad_spend,
                source_spend=self._float0(effective_source_spend),
                raw_allocated_spend=self._float0(raw_ads_allocated),
                capped_allocated_spend=ad_spend,
                allocated_spend=ad_spend,
                unallocated_spend=self._float0(ads_unallocated),
                overallocated_spend=self._float0(ads_overallocated),
                drr_percent=drr_percent,
                drr_percent_source=drr_percent_source,
                status=allocation_status,
                allocation_status=allocation_status,
                profit_allocation_status=(
                    "finance_final"
                    if ad_spend_source == AD_SPEND_SOURCE_FINANCE
                    else "overallocated"
                    if ads_overallocated > 0
                    else "linked"
                    if effective_source_spend > 0 and ads_unallocated <= 0
                    else "partial"
                    if effective_source_spend > 0
                    else "no_source_data"
                ),
                allocation_method="nm_revenue_weighted"
                if effective_source_spend > 0
                and getattr(row, "nm_id", None) is not None
                else "",
                allocation_confidence="high"
                if ad_spend_source == AD_SPEND_SOURCE_FINANCE
                or (
                    effective_source_spend > 0
                    and ads_overallocated <= 0
                    and ads_unallocated <= 0
                )
                else "medium"
                if effective_source_spend > 0
                else "low",
                final_profit_allowed=final_profit_allowed,
            ),
            cogs=CardCogsBlock(
                unit_cost=self._float0(unit_cost_decimal),
                estimated_cogs=self._float0(profit_row.estimated_cogs),
                truth_level=truth_level,
                cost_truth_label=self._cost_truth_label(truth_level),
                supplier_confirmed=self._profit_row_cost_final_accepted(profit_row),
                business_trusted=bool(profit_row.has_real_manual_cost),
                confidence=cost_confidence,
                reason=cost_reason,
            ),
            profit=CardProfitBlock(
                before_ads=self._float0(profit_before_ads),
                after_allocated_ads=self._float0(profit_after_allocated_ads),
                after_source_ads=self._float0(profit_after_source_ads),
                after_overhead=self._float0(
                    profit_after_source_ads - allocated_overhead
                ),
                with_allocated_overhead=self._float0(
                    profit_after_source_ads - allocated_overhead
                ),
                after_ads=self._float0(profit_after_source_ads),
                net_profit_after_all_expenses=self._float0(net_profit_all_expenses),
                margin_after_ads_percent=self._percent0(
                    profit_after_source_ads, revenue_value
                ),
                roi_after_ads_percent=self._percent0(
                    profit_after_source_ads, getattr(profit_row, "estimated_cogs", 0)
                ),
                roi_on_cogs_percent=self._percent0(
                    profit_after_source_ads, getattr(profit_row, "estimated_cogs", 0)
                ),
                stock_roi_percent=self._percent0(
                    profit_after_source_ads, stock_components["stock_value"]
                ),
                roas_percent=self._percent0(revenue_value, effective_source_spend),
                confidence=self._trust_confidence(row.trust_state),
            ),
            wb_expenses_total=self._float0(wb_expenses_total),
            seller_cogs=self._float0(
                getattr(
                    profit_row, "seller_cogs", getattr(profit_row, "estimated_cogs", 0)
                )
            ),
            seller_other_expense=self._float0(
                getattr(profit_row, "seller_other_expense", 0)
            ),
            total_seller_expenses=self._float0(seller_cost_total),
            total_seller_costs=self._float0(seller_cost_total),
            additional_income=self._float0(additional_income_value),
            ad_spend_operational=self._float0(operational_ad_spend),
            ad_spend_finance=self._float0(finance_ad_spend),
            ad_spend_final=self._float0(final_ad_spend),
            ad_spend_source=ad_spend_source,
            ad_spend_delta=self._float0(ad_spend_delta),
            net_profit_after_all_expenses=self._float0(net_profit_all_expenses),
            expense_data_quality=compute_expense_data_quality(profit_row),
            stock_value=self._float0(stock_components["stock_value"]),
            unit_economics=self._card_unit_economics(
                profit_row=profit_row,
                row=row,
                price_row=price_row,
                revenue=revenue_value,
                wb_expenses_total=wb_expenses_total,
                seller_cost_total=seller_cost_total,
                ad_spend=final_ad_spend
                if ad_spend_source == AD_SPEND_SOURCE_FINANCE
                else effective_source_spend,
                profit_after_source_ads=profit_after_source_ads,
                allocated_overhead=allocated_overhead,
            ),
        )

    def _build_card_price(
        self,
        price_row: Any | None,
        *,
        profit_row: Any | None = None,
        settings: dict[str, Any] | None = None,
    ) -> CardPriceBlock:
        if price_row is None:
            return CardPriceBlock(
                current_price=0.0,
                current_discounted_price=0.0,
                discount=0,
                break_even_price=0.0,
                target_margin_price=0.0,
                safe_price_gap=0.0,
                safe_price_gap_unit="RUB",
                safe_price_gap_kind="currency_amount",
                estimated_margin_percent=None,
                status="not_computable",
                confidence="low",
                price_source="",
                not_computable_reason="price_not_loaded",
            )
        break_even_value = self._float0(price_row.break_even_price)
        target_margin_value = self._float0(price_row.target_margin_price)
        safe_gap_value = self._float0(price_row.safe_price_gap)
        estimated_flag = bool(price_row.estimated)
        not_computable_reason = price_row.not_computable_reason or ""
        if (
            profit_row is not None
            and price_row.break_even_price is None
            and not_computable_reason in {"cost_not_confirmed", "missing_cost"}
        ):
            unit_cost = self._unit_cost_from_profit_row(profit_row)
            (
                fallback_break_even,
                fallback_target_margin,
                fallback_safe_gap,
                _estimated_margin,
                _,
            ) = self.control._safe_price_metrics(
                current_price=self._decimal(getattr(price_row, "current_price", None)),
                current_discounted_price=self._decimal(
                    getattr(price_row, "current_discounted_price", None)
                ),
                average_sale_price=self._decimal(
                    getattr(price_row, "average_sale_price", None)
                ),
                total_unit_cost=unit_cost,
                revenue=compute_revenue_final(profit_row),
                ad_spend=self._decimal(getattr(profit_row, "ad_spend", None)),
                net_units=int(getattr(profit_row, "net_units", 0) or 0),
                commission=self._decimal(getattr(profit_row, "commission", None)),
                acquiring_fee=self._decimal(getattr(profit_row, "acquiring_fee", None)),
                deductions=self._decimal(getattr(profit_row, "deductions", None)),
                additional_payments=expense_additional_income(profit_row),
                logistics=self._decimal(getattr(profit_row, "logistics", None)),
                paid_acceptance=self._decimal(
                    getattr(profit_row, "paid_acceptance", None)
                ),
                storage=self._decimal(getattr(profit_row, "storage", None)),
                penalties=self._decimal(getattr(profit_row, "penalties", None)),
                target_margin_rate=Decimal(
                    str((settings or {}).get("target_margin_rate") or 0.2)
                ),
            )
            if fallback_break_even is not None:
                break_even_value = self._float0(fallback_break_even)
                target_margin_value = self._float0(fallback_target_margin)
                safe_gap_value = self._float0(fallback_safe_gap)
                estimated_flag = True
        status = "ready"
        if not_computable_reason and break_even_value <= 0:
            status = "not_computable"
        elif safe_gap_value < 0:
            status = "below_break_even"
        elif estimated_flag:
            status = "estimated_safe"
        current_price_value = self._float0(price_row.current_price)
        discounted_price_value = self._float0(price_row.current_discounted_price)
        return CardPriceBlock(
            current_price=current_price_value,
            current_discounted_price=discounted_price_value,
            discount=self._price_discount_percent(
                current_price=current_price_value,
                current_discounted_price=discounted_price_value,
                explicit_discount=getattr(price_row, "discount", None),
            ),
            break_even_price=break_even_value,
            break_even_price_final=0.0 if estimated_flag else break_even_value,
            break_even_price_estimated=break_even_value if estimated_flag else 0.0,
            target_margin_price=target_margin_value,
            target_margin_price_final=0.0 if estimated_flag else target_margin_value,
            target_margin_price_estimated=target_margin_value
            if estimated_flag
            else 0.0,
            safe_price_gap=safe_gap_value,
            safe_price_gap_unit="RUB",
            safe_price_gap_kind="currency_amount",
            safe_price_gap_final=0.0 if estimated_flag else safe_gap_value,
            safe_price_gap_estimated=safe_gap_value if estimated_flag else 0.0,
            estimated_margin_percent=(
                self._float0(
                    getattr(
                        price_row,
                        "estimated_margin_percent",
                        getattr(price_row, "estimated_margin_at_current_price", None),
                    )
                )
                if getattr(
                    price_row,
                    "estimated_margin_percent",
                    getattr(price_row, "estimated_margin_at_current_price", None),
                )
                is not None
                else None
            ),
            status=status,
            confidence=price_row.confidence or "low",
            price_source=price_row.price_source or "",
            not_computable_reason=not_computable_reason
            if break_even_value <= 0
            else "",
        )

    def _price_discount_percent(
        self,
        *,
        current_price: float,
        current_discounted_price: float,
        explicit_discount: Any | None,
    ) -> int:
        explicit = self._int0(explicit_discount)
        if explicit > 0:
            return explicit
        if (
            current_price <= 0
            or current_discounted_price <= 0
            or current_discounted_price >= current_price
        ):
            return 0
        return max(
            0,
            min(100, int(round((1 - current_discounted_price / current_price) * 100))),
        )

    def _build_card_stock(
        self, row: Any, profit_row: Any | None = None, purchase_row: Any | None = None
    ) -> CardStockBlock:
        if row.stock_qty is None:
            stock_status = "unknown"
        elif row.days_of_stock is not None and row.days_of_stock <= 7:
            stock_status = (
                "low_stock_but_blocked"
                if row.trust_state == TRUST_STATE_DATA_BLOCKED
                else "low_stock"
            )
        elif (
            purchase_row is not None
            and getattr(purchase_row, "status", None) == "WAIT_DATA"
            and row.trust_state == TRUST_STATE_DATA_BLOCKED
        ) or (
            row.trust_state == TRUST_STATE_DATA_BLOCKED and row.days_of_stock is None
        ):
            stock_status = "unknown"
        elif (
            purchase_row is not None
            and getattr(purchase_row, "status", None) == "LIQUIDATE"
        ) or row.sku_status == "LIQUIDATE":
            stock_status = "overstock"
        else:
            stock_status = "ok"
        stock_components = self._stock_value_components(
            row,
            profit_row or object(),
            purchase_row,
            business_trusted=row.trust_state == TRUST_STATE_TRUSTED,
        )
        in_transit_qty = (
            self._float0(purchase_row.in_transit_qty)
            if purchase_row is not None
            else 0.0
        )
        overstock_value = self._float0(getattr(row, "overstock_value", None))
        if overstock_value <= 0 and stock_status == "overstock":
            overstock_value = self._float0(stock_components["stock_value"])
        return CardStockBlock(
            quantity=self._float0(row.stock_qty),
            quantity_full=self._float0(row.stock_qty),
            stock_value=self._float0(stock_components["stock_value"]),
            stock_value_confidence=stock_components["stock_value_confidence"],
            stock_value_reason=stock_components["stock_value_reason"],
            days_of_stock=self._float0(row.days_of_stock),
            sales_velocity_daily=self._row_sales_velocity_daily(row, purchase_row),
            overstock_value=overstock_value,
            stock_status=stock_status or "",
            in_transit_qty=in_transit_qty,
            in_transit_value=self._float0(stock_components["in_transit_value"]),
        )

    def _article_summary_preview(
        self,
        *,
        nm_id: int | None,
        title: str | None,
        article_rows: list[tuple[Any, Any, Any | None]],
        ads_source_spend: Decimal,
    ) -> ArticleSummaryPreview | None:
        if nm_id is None:
            return None
        revenue = Decimal("0")
        stock_qty = Decimal("0")
        stock_value = Decimal("0")
        for row, profit_row, purchase_row in article_rows:
            revenue += compute_revenue_final(profit_row)
            stock_qty += self._decimal(getattr(row, "stock_qty", None))
            stock_value += self._decimal(
                self._build_card_stock(row, profit_row, purchase_row).stock_value
            )
        return ArticleSummaryPreview(
            nm_id=nm_id,
            title=title,
            revenue=self._float0(revenue),
            stock_qty=self._float0(stock_qty),
            stock_value=self._float0(stock_value),
            ads_source_spend=self._float0(ads_source_spend),
            variant_count=len(article_rows),
        )

    def _article_summary_block(
        self,
        *,
        nm_id: int,
        title: str | None,
        article_rows: list[tuple[Any, Any, Any | None]],
        ads_source_spend: Decimal,
        decision: str,
        audit: Any | None = None,
    ) -> ArticleSummaryBlock:
        revenue = Decimal("0")
        stock_qty = Decimal("0")
        stock_value = Decimal("0")
        profit_before_ads = Decimal("0")
        profit_after_ads = Decimal("0")
        final_ad_spend_total = Decimal("0")
        has_profit_after_ads = False
        sales_count = 0
        returns_count = 0
        for row, profit_row, purchase_row in article_rows:
            revenue_value = compute_revenue_final(profit_row)
            row_ad = self._row_ad_components(
                profit_row, fallback_source=ads_source_spend
            )
            revenue += revenue_value
            final_ad_spend_total += self._decimal(row_ad["ad_spend_final"])
            stock_qty += self._decimal(getattr(row, "stock_qty", None))
            stock_value += self._decimal(
                self._build_card_stock(row, profit_row, purchase_row).stock_value
            )
            explicit_profit_before_ads = getattr(
                profit_row, "estimated_profit_before_ads", None
            )
            if explicit_profit_before_ads is not None:
                profit_before_ads += self._decimal(explicit_profit_before_ads)
            else:
                profit_before_ads += (
                    revenue_value
                    + expense_additional_income(profit_row)
                    - self._wb_expenses_total(profit_row)
                    - total_seller_costs(profit_row)
                )
            explicit_profit_after_ads = getattr(
                profit_row, "estimated_profit_after_ads", None
            )
            if explicit_profit_after_ads is not None:
                profit_after_ads += self._decimal(explicit_profit_after_ads)
                has_profit_after_ads = True
            sales_count += self._int0(getattr(profit_row, "gross_units", None))
            returns_count += self._int0(getattr(profit_row, "return_units", None))
        if not has_profit_after_ads:
            effective_final_ad_spend = (
                final_ad_spend_total if final_ad_spend_total > 0 else ads_source_spend
            )
            profit_after_ads = profit_before_ads - effective_final_ad_spend
        cancel_rate_percent = 0.0
        return_rate_percent = self._percent0(returns_count, sales_count)
        if audit is not None:
            cancel_rate_percent = self._percent0(
                getattr(audit.operations, "cancelled_orders_count", None),
                getattr(audit.operations, "orders_count", None),
            )
            return_rate_percent = self._percent0(
                getattr(audit.operations, "returns_count", None),
                getattr(audit.operations, "sales_count", None),
            )
        return ArticleSummaryBlock(
            nm_id=nm_id,
            title=title,
            revenue=self._float0(revenue),
            profit_before_ads=self._float0(profit_before_ads),
            ads_source_spend=self._float0(ads_source_spend),
            profit_after_ads=self._float0(profit_after_ads),
            stock_qty=self._float0(stock_qty),
            stock_value=self._float0(stock_value),
            cancel_rate_percent=cancel_rate_percent,
            return_rate_percent=return_rate_percent,
            decision=decision,
        )

    def _variant_breakdown_rows(
        self,
        *,
        state: MoneyRuntimeState,
        article_rows: list[tuple[Any, Any, Any | None]],
        ads_source_spend: Decimal,
    ) -> list[VariantBreakdownRow]:
        total_revenue = sum(
            (
                compute_revenue_final(profit_row)
                for _row, profit_row, _purchase in article_rows
            ),
            start=Decimal("0"),
        )
        total_orders = sum(
            (
                Decimal(str(self._int0(getattr(profit_row, "gross_units", None))))
                for _row, profit_row, _purchase in article_rows
            ),
            start=Decimal("0"),
        )
        count = len(article_rows)
        results: list[VariantBreakdownRow] = []
        for row, profit_row, purchase_row in article_rows:
            revenue = compute_revenue_final(profit_row)
            order_units = Decimal(
                str(self._int0(getattr(profit_row, "gross_units", None)))
            )
            if ads_source_spend <= 0:
                allocated_source = Decimal("0")
            elif total_revenue > 0:
                allocated_source = ads_source_spend * revenue / total_revenue
            elif total_orders > 0:
                allocated_source = ads_source_spend * order_units / total_orders
            else:
                allocated_source = ads_source_spend / Decimal(str(count or 1))
            next_action = self._primary_row_action(
                state,
                row,
                price_row=state.price_rows.get(int(row.sku_id))
                if row.sku_id is not None
                else None,
                purchase_row=purchase_row,
            )
            stock = self._build_card_stock(row, profit_row, purchase_row)
            explicit_profit_before_ads = getattr(
                profit_row, "estimated_profit_before_ads", None
            )
            if explicit_profit_before_ads is not None:
                before_ads = self._decimal(explicit_profit_before_ads)
            else:
                before_ads = (
                    revenue
                    + expense_additional_income(profit_row)
                    - self._wb_expenses_total(profit_row)
                    - total_seller_costs(profit_row)
                )
            results.append(
                VariantBreakdownRow(
                    sku_id=row.sku_id,
                    barcode=row.barcode,
                    vendor_code=row.vendor_code,
                    title=row.title,
                    revenue=self._float0(revenue),
                    stock_qty=stock.quantity,
                    stock_value=stock.stock_value,
                    allocated_ads_spend=self._float0(
                        self._decimal(
                            getattr(row, "capped_ad_spend", None)
                            if getattr(row, "capped_ad_spend", None) is not None
                            else getattr(
                                profit_row,
                                "ad_spend_final",
                                getattr(profit_row, "ad_spend", None),
                            )
                        )
                    ),
                    source_ads_spend=self._float0(allocated_source),
                    net_profit_after_source_ads=self._float0(
                        before_ads - allocated_source
                    ),
                    next_action=next_action,
                )
            )
        results.sort(key=lambda item: item.revenue, reverse=True)
        return results

    def _aggregate_article_context(
        self,
        *,
        article_rows: list[tuple[Any, Any, Any | None]],
        ads_source_spend: Decimal,
    ) -> dict[str, Any]:
        primary_row, primary_profit_row, primary_purchase_row = max(
            article_rows,
            key=lambda item: float(getattr(item[0], "priority_score", 0) or 0),
        )
        revenue = Decimal("0")
        for_pay = Decimal("0")
        cogs = Decimal("0")
        seller_cogs = Decimal("0")
        seller_other_expense = Decimal("0")
        additional_income = Decimal("0")
        ads_allocated = Decimal("0")
        raw_ads_allocated = Decimal("0")
        ads_overallocated = Decimal("0")
        ads_unallocated = Decimal("0")
        ad_spend_operational = Decimal("0")
        ad_spend_finance = Decimal("0")
        ad_spend_final = Decimal("0")
        wb_commission = Decimal("0")
        payment_processing = Decimal("0")
        pvz_reward = Decimal("0")
        wb_logistics = Decimal("0")
        wb_logistics_rebill = Decimal("0")
        acceptance = Decimal("0")
        penalty = Decimal("0")
        deduction = Decimal("0")
        marketing_deduction = Decimal("0")
        loyalty = Decimal("0")
        other_wb_expenses = Decimal("0")
        commission = Decimal("0")
        acquiring_fee = Decimal("0")
        logistics = Decimal("0")
        paid_acceptance = Decimal("0")
        storage = Decimal("0")
        penalties = Decimal("0")
        deductions = Decimal("0")
        wb_expenses_total = Decimal("0")
        stock_qty = Decimal("0")
        stock_value = Decimal("0")
        overstock_value = Decimal("0")
        sales_velocity_daily = Decimal("0")
        blocked_reasons: list[str] = []
        trust_states: list[str] = []
        for row, profit_row, purchase_row in article_rows:
            revenue_value = compute_revenue_final(profit_row)
            row_ad = self._row_ad_components(
                profit_row, fallback_source=ads_source_spend
            )
            revenue += revenue_value
            for_pay += self._decimal(getattr(profit_row, "for_pay", None))
            cogs += self._decimal(getattr(profit_row, "estimated_cogs", None))
            seller_cogs += self._decimal(
                getattr(
                    profit_row,
                    "seller_cogs",
                    getattr(profit_row, "estimated_cogs", None),
                )
            )
            seller_other_expense += self._decimal(
                getattr(profit_row, "seller_other_expense", None)
            )
            additional_income += expense_additional_income(profit_row)
            ads_allocated += self._decimal(
                getattr(row, "capped_ad_spend", None)
                if getattr(row, "capped_ad_spend", None) is not None
                else getattr(row, "ad_spend", None)
            )
            raw_ads_allocated += self._decimal(
                getattr(row, "raw_ad_spend", None)
                if getattr(row, "raw_ad_spend", None) is not None
                else getattr(row, "ad_spend", None)
            )
            ads_overallocated += self._decimal(
                getattr(row, "overallocated_ad_spend", None)
            )
            ads_unallocated += self._decimal(getattr(row, "unallocated_ad_spend", None))
            ad_spend_operational += self._decimal(row_ad["ad_spend_operational"])
            ad_spend_finance += self._decimal(row_ad["ad_spend_finance"])
            ad_spend_final += self._decimal(row_ad["ad_spend_final"])
            wb_commission += self._expense_value(
                profit_row, EXPENSE_CATEGORY_WB_COMMISSION, "commission"
            )
            payment_processing += self._expense_value(
                profit_row, EXPENSE_CATEGORY_PAYMENT_PROCESSING, "acquiring_fee"
            )
            pvz_reward += self._expense_value(profit_row, EXPENSE_CATEGORY_PVZ_REWARD)
            wb_logistics += self._expense_value(
                profit_row, EXPENSE_CATEGORY_WB_LOGISTICS
            )
            wb_logistics_rebill += self._expense_value(
                profit_row, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL
            )
            acceptance += self._expense_value(
                profit_row, EXPENSE_CATEGORY_ACCEPTANCE, "paid_acceptance"
            )
            penalty += self._expense_value(
                profit_row, EXPENSE_CATEGORY_PENALTY, "penalties"
            )
            deduction += self._expense_value(profit_row, EXPENSE_CATEGORY_DEDUCTION)
            marketing_deduction += self._expense_value(
                profit_row, EXPENSE_CATEGORY_MARKETING_DEDUCTION
            )
            loyalty += self._expense_value(profit_row, EXPENSE_CATEGORY_LOYALTY)
            other_wb_expenses += self._expense_value(profit_row, "other_wb_expenses")
            commission += self._decimal(getattr(profit_row, "commission", None))
            acquiring_fee += self._decimal(getattr(profit_row, "acquiring_fee", None))
            logistics += self._decimal(getattr(profit_row, "logistics", None))
            paid_acceptance += self._decimal(
                getattr(profit_row, "paid_acceptance", None)
            )
            storage += self._decimal(getattr(profit_row, "storage", None))
            penalties += self._decimal(getattr(profit_row, "penalties", None))
            deductions += self._decimal(getattr(profit_row, "deductions", None))
            wb_expenses_total += self._wb_expenses_total(profit_row)
            stock_block = self._build_card_stock(row, profit_row, purchase_row)
            stock_qty += self._decimal(stock_block.quantity)
            stock_value += self._decimal(stock_block.stock_value)
            overstock_value += self._decimal(stock_block.overstock_value)
            sales_velocity_daily += self._decimal(stock_block.sales_velocity_daily)
            blocked_reasons.extend(list(getattr(row, "blocked_reasons", []) or []))
            trust_states.append(getattr(row, "trust_state", TRUST_STATE_DATA_BLOCKED))
        if any(state == TRUST_STATE_DATA_BLOCKED for state in trust_states):
            trust_state = TRUST_STATE_DATA_BLOCKED
        elif any(state == TRUST_STATE_TEST_ONLY for state in trust_states):
            trust_state = TRUST_STATE_TEST_ONLY
        else:
            trust_state = TRUST_STATE_TRUSTED
        aggregated_days_of_stock = (
            float(stock_qty / sales_velocity_daily)
            if stock_qty > 0 and sales_velocity_daily > 0
            else getattr(primary_row, "days_of_stock", None)
        )
        aggregated_sku_status = (
            "LIQUIDATE"
            if any(
                str(getattr(item[0], "sku_status", "") or "").upper() == "LIQUIDATE"
                for item in article_rows
            )
            else getattr(primary_row, "sku_status", "watch")
        )
        article_ad_spend_final = (
            ad_spend_final
            if ad_spend_final > 0
            else ads_source_spend
            if ads_source_spend > 0
            else ad_spend_operational
        )
        article_ad_spend_source = (
            AD_SPEND_SOURCE_FINANCE
            if ad_spend_finance > 0
            else AD_SPEND_SOURCE_OPERATIONAL
            if (
                ad_spend_operational > 0
                or ads_source_spend > 0
                or article_ad_spend_final > 0
            )
            else AD_SPEND_SOURCE_NONE
        )
        total_seller_cost_value = seller_cogs + seller_other_expense
        profit_before_ads = (
            revenue - wb_expenses_total - total_seller_cost_value + additional_income
        )
        profit_after_ads = profit_before_ads - article_ad_spend_final
        aggregated_row = SimpleNamespace(
            sku_id=None,
            nm_id=primary_row.nm_id,
            vendor_code=primary_row.vendor_code,
            barcode=None,
            title=primary_row.title,
            brand=primary_row.brand,
            subject_name=primary_row.subject_name,
            stock_qty=float(stock_qty),
            stock_value=float(stock_value),
            overstock_value=float(overstock_value),
            days_of_stock=aggregated_days_of_stock,
            sales_velocity_daily=float(sales_velocity_daily),
            ad_spend=float(ads_allocated),
            raw_ad_spend=float(raw_ads_allocated),
            source_ad_spend=float(ads_source_spend),
            capped_ad_spend=float(ads_allocated),
            overallocated_ad_spend=float(ads_overallocated),
            unallocated_ad_spend=float(ads_unallocated),
            ads_allocation_status=(
                "finance_final"
                if article_ad_spend_source == AD_SPEND_SOURCE_FINANCE
                else "overallocated"
                if ads_overallocated > 0
                else "partial"
                if ads_unallocated > 0
                else "matched"
                if ads_source_spend > 0
                else "no_source_data"
            ),
            final_profit_allowed=article_ad_spend_source == AD_SPEND_SOURCE_FINANCE
            or ads_overallocated <= 0,
            drr_percent=self._percent0(article_ad_spend_final, revenue),
            revenue=float(revenue),
            revenue_final=float(revenue),
            net_profit=float(profit_after_ads),
            margin_percent=self._percent0(profit_after_ads, revenue),
            trust_state=trust_state,
            blocked_reasons=list(dict.fromkeys(blocked_reasons)),
            sku_status=aggregated_sku_status,
            priority_score=max(
                float(getattr(item[0], "priority_score", 0) or 0)
                for item in article_rows
            ),
        )
        aggregated_profit = SimpleNamespace(
            realized_revenue=float(revenue),
            revenue_final=float(revenue),
            for_pay=float(for_pay),
            wb_commission=float(wb_commission),
            payment_processing=float(payment_processing),
            pvz_reward=float(pvz_reward),
            wb_logistics=float(wb_logistics),
            wb_logistics_rebill=float(wb_logistics_rebill),
            acceptance=float(acceptance),
            penalty=float(penalty),
            deduction=float(deduction),
            marketing_deduction=float(marketing_deduction),
            loyalty=float(loyalty),
            other_wb_expenses=float(other_wb_expenses),
            total_wb_expenses=float(wb_expenses_total),
            commission=float(commission),
            acquiring_fee=float(acquiring_fee),
            logistics=float(logistics),
            paid_acceptance=float(paid_acceptance),
            storage=float(storage),
            penalties=float(penalties),
            deductions=float(deductions),
            additional_payments=float(additional_income),
            finance_rows=sum(
                self._int0(getattr(item[1], "finance_rows", None))
                for item in article_rows
            ),
            estimated_cogs=float(cogs),
            seller_cogs=float(seller_cogs),
            seller_other_expense=float(seller_other_expense),
            total_seller_expenses=float(total_seller_cost_value),
            total_seller_costs=float(total_seller_cost_value),
            additional_income=float(additional_income),
            net_units=sum(
                self._int0(getattr(item[1], "net_units", None)) for item in article_rows
            ),
            has_real_manual_cost=all(
                bool(getattr(item[1], "has_real_manual_cost", False))
                for item in article_rows
            ),
            estimated_profit_before_ads=float(profit_before_ads),
            estimated_profit_after_ads=float(profit_after_ads),
            estimated_profit=float(profit_after_ads),
            net_profit_after_all_expenses=float(profit_after_ads),
            ad_spend=float(article_ad_spend_final),
            ad_spend_operational=float(
                ad_spend_operational if ad_spend_operational > 0 else ads_source_spend
            ),
            ad_spend_finance=float(ad_spend_finance),
            ad_spend_final=float(article_ad_spend_final),
            ad_spend_source=article_ad_spend_source,
            ad_spend_delta=float(
                (ad_spend_operational if ad_spend_operational > 0 else ads_source_spend)
                - ad_spend_finance
            ),
            raw_ad_spend=float(raw_ads_allocated),
            source_ad_spend=float(ads_source_spend),
            capped_ad_spend=float(ads_allocated),
            overallocated_ad_spend=float(ads_overallocated),
            unallocated_ad_spend=float(ads_unallocated),
            ads_allocation_status=(
                "finance_final"
                if article_ad_spend_source == AD_SPEND_SOURCE_FINANCE
                else "overallocated"
                if ads_overallocated > 0
                else "partial"
                if ads_unallocated > 0
                else "matched"
                if ads_source_spend > 0
                else "no_source_data"
            ),
            final_profit_allowed=article_ad_spend_source == AD_SPEND_SOURCE_FINANCE
            or ads_overallocated <= 0,
            margin_percent=self._percent0(profit_after_ads, revenue),
            roi_percent=self._percent0(profit_after_ads, cogs),
            cost_truth_level="supplier_confirmed"
            if all(
                bool(getattr(item[1], "has_real_manual_cost", False))
                for item in article_rows
            )
            else "operator_baseline",
            expense_data_quality=compute_expense_data_quality(
                SimpleNamespace(
                    final_revenue_source="finance"
                    if sum(
                        self._int0(getattr(item[1], "finance_rows", None))
                        for item in article_rows
                    )
                    > 0
                    else "operational",
                    finance_rows=sum(
                        self._int0(getattr(item[1], "finance_rows", None))
                        for item in article_rows
                    ),
                    other_wb_expenses=float(other_wb_expenses),
                    ad_spend_operational=float(ad_spend_operational),
                    ad_spend_finance=float(ad_spend_finance),
                    ad_spend_final=float(article_ad_spend_final),
                    ad_spend_source=article_ad_spend_source,
                )
            ),
        )
        return {
            "row": aggregated_row,
            "profit_row": aggregated_profit,
            "purchase_row": primary_purchase_row,
            "primary_row": primary_row,
            "primary_profit_row": primary_profit_row,
        }

    def _top_cards_block(self, control_rows: list[Any]) -> TopCardsBlock:
        def pack(rows: list[Any]) -> list[TopCardPreview]:
            return [
                TopCardPreview(
                    sku_id=row.sku_id,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    title=row.title,
                    revenue=self._float0(row.revenue),
                    net_profit=self._float0(row.net_profit),
                    stock_value=self._float0(row.stock_value),
                    priority_score=self._float0(row.priority_score),
                    status=row.sku_status or "",
                )
                for row in rows[:5]
            ]

        profitable = [
            row
            for row in control_rows
            if row.trust_state != TRUST_STATE_DATA_BLOCKED and (row.net_profit or 0) > 0
        ]
        loss = [
            row
            for row in control_rows
            if row.net_profit is not None and row.net_profit < 0
        ]
        stock_risk = [row for row in control_rows if row.sku_status == "PROTECT_STOCK"]
        blocked = [
            row for row in control_rows if row.trust_state == TRUST_STATE_DATA_BLOCKED
        ]
        return TopCardsBlock(
            profitable=pack(profitable),
            loss_making=pack(loss),
            stock_risk=pack(stock_risk),
            data_blocked=pack(blocked),
        )

    def _summary_answer(
        self,
        health: Any,
        *,
        revenue_sources: RevenueSources,
        quality: MoneyQuality,
        unallocated_expense_ratio_percent: float,
    ) -> BusinessAnswer:
        finance_ready = revenue_sources.reconciliation_status == "matched"
        supplier_ready = (quality.supplier_cost_coverage_percent or 0) >= 95
        ads_ready = quality.ads_overallocated_spend <= 0 and (
            (quality.ads_allocation_percent_capped or 0) >= 95
            or quality.ads_allocation_percent_capped == 0
        )
        overhead_ready = unallocated_expense_ratio_percent <= 5
        owner_approved_final = bool(
            getattr(health, "financial_final", False)
        ) and cost_policy_owner_approves_final(
            getattr(health, "cost_trust_policy", None)
        )
        if owner_approved_final and finance_ready and ads_ready and overhead_ready:
            return BusinessAnswer(
                business_status="healthy",
                title="Текущий срез временно принят как итоговый.",
                short_text="Система работает в режиме временного ручного подтверждения: деньги, прибыль и действия доступны как итоговые до загрузки обновленных реальных данных.",
                main_problem="",
                main_next_step="Продолжайте работу в обычном режиме и позже замените временное подтверждение реальными данными по себестоимости.",
            )
        if owner_approved_final:
            reasons: list[str] = []
            if not finance_ready:
                reasons.append("есть расхождение между отчетом WB и продажами")
            if quality.ads_overallocated_spend > 0:
                reasons.append("реклама распределена с ошибкой")
            elif (quality.ads_allocation_percent_capped or 0) < 95 and (
                quality.ads_allocation_percent or 0
            ) > 0:
                reasons.append("рекламные расходы распределены не полностью")
            if not overhead_ready:
                reasons.append("есть крупные общие расходы без привязки к карточкам")
            main_problem = "Временное ручное подтверждение включено, но часть итоговых проверок еще не закрыта."
            if reasons:
                main_problem = f"Временное ручное подтверждение включено, но еще нужно закрыть: {', '.join(reasons)}."
            return BusinessAnswer(
                business_status="provisional",
                title="Магазин работает в режиме временного ручного подтверждения.",
                short_text="Основные цифры уже можно использовать, но часть итоговых проверок еще не закрыта.",
                main_problem=main_problem,
                main_next_step="Сначала закройте расхождение по выручке и прочие оставшиеся проверки, затем оставьте только реальные подтвержденные данные.",
            )
        if (
            health.business_trusted
            and finance_ready
            and supplier_ready
            and ads_ready
            and overhead_ready
        ):
            return BusinessAnswer(
                business_status="healthy",
                title="Данные магазина готовы для управления деньгами.",
                short_text="Денежный поток, прибыльность карточек и следующие действия доступны на надежном уровне.",
                main_problem="",
                main_next_step="Масштабируйте прибыльные карточки и отдельно контролируйте рискованные.",
            )
        if bool(health.can_generate_business_actions):
            reasons: list[str] = []
            if not finance_ready:
                reasons.append("есть расхождение между отчетом WB и продажами")
            if not supplier_ready:
                reasons.append("нет подтвержденной реальной себестоимости")
            if quality.ads_overallocated_spend > 0:
                reasons.append("реклама распределена с ошибкой")
            elif (quality.ads_allocation_percent_capped or 0) < 95 and (
                quality.ads_allocation_percent or 0
            ) > 0:
                reasons.append("рекламные расходы распределены не полностью")
            if not overhead_ready:
                reasons.append("есть крупные общие расходы без привязки к карточкам")
            main_problem = "Финальная прибыль еще не закрыта."
            if reasons:
                main_problem = (
                    f"Финальная прибыль еще не закрыта: {', '.join(reasons)}."
                )
            return BusinessAnswer(
                business_status="provisional",
                title="Магазин готов к управлению, но финальная прибыль еще предварительная.",
                short_text="Можно принимать ежедневные решения, но выручка, себестоимость или рекламные расходы еще не сверены до конца.",
                main_problem=main_problem,
                main_next_step="Сначала закройте расхождение по выручке, подтвердите себестоимость и доведите распределение рекламных расходов до конца. До этого принимайте только осторожные решения.",
            )
        main_problem = "Часть денежного потока пока не привязана к экономике карточек надежным образом."
        if health.blocked_reasons:
            main_problem = f"Основной блокер: {self.BLOCKED_REASON_LABELS.get(health.blocked_reasons[0], health.blocked_reasons[0])}."
        return BusinessAnswer(
            business_status="data_blocked",
            title="Движение денег по магазину видно, но данные еще не готовы для окончательных решений.",
            short_text="Сигналы по выручке и расходам уже есть, но подтвержденной себестоимости, завершенной загрузки остатков или полной сверки выручки с отчетом WB пока недостаточно.",
            main_problem=main_problem,
            main_next_step="Сначала закройте блокеры данных, затем применяйте бизнес-действия.",
        )

    async def summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> MoneySummaryRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        summary_window_key = self._runtime_window_key(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        runtime_version_hash = await self._runtime_version_hash(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        summary_window_cache = self._summary_window_cache_store(session)
        warm_cached_summary = summary_window_cache.get(summary_window_key)
        if warm_cached_summary is not None:
            cached_at, cached_response = warm_cached_summary
            if (
                self._cache_is_fresh(
                    cached_at, ttl_seconds=self.WARM_SUMMARY_CACHE_TTL_SECONDS
                )
                and str(getattr(cached_response, "data_version_hash", "") or "")
                == runtime_version_hash
            ):
                return cached_response.model_copy(
                    deep=True,
                    update={
                        "cache_status": "hit",
                        "data_version_hash": runtime_version_hash,
                    },
                )
        summary_cache_key = self._runtime_cache_key(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            data_version_hash=runtime_version_hash,
        )
        summary_cache = self._summary_cache_store(session)
        cached_summary = summary_cache.get(summary_cache_key)
        if cached_summary is not None:
            cached_at, cached_response = cached_summary
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.RUNTIME_CACHE_TTL_SECONDS
            ):
                return cached_response.model_copy(
                    deep=True,
                    update={
                        "cache_status": "hit",
                        "data_version_hash": runtime_version_hash,
                    },
                )
        state = await self._load_runtime_state(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            runtime_version_hash=runtime_version_hash,
        )
        meta = self._meta(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            health=state.health,
        )
        latest_balance = state.latest_balance
        period_end_balance = getattr(state, "period_end_balance", latest_balance)
        current_balance_amount = self._balance_amount(latest_balance)
        current_withdrawable_amount = self._available_for_withdraw_amount(
            latest_balance
        )
        period_end_balance_amount = self._balance_amount(period_end_balance)
        period_end_withdrawable_amount = self._available_for_withdraw_amount(
            period_end_balance
        )
        unallocated_expenses = state.account_level_expense_total
        revenue = sum(
            (compute_revenue_final(item) for item in state.profit_rows),
            start=Decimal("0"),
        )
        for_pay = sum(
            (self._decimal(item.for_pay) for item in state.profit_rows),
            start=Decimal("0"),
        )
        finance_category_totals = await self._summary_finance_category_totals(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            profit_rows=state.profit_rows,
            account_expense_rows=state.account_expense_rows,
        )
        wb_commission = finance_category_totals[EXPENSE_CATEGORY_WB_COMMISSION]
        payment_processing = finance_category_totals[
            EXPENSE_CATEGORY_PAYMENT_PROCESSING
        ]
        pvz_reward = finance_category_totals[EXPENSE_CATEGORY_PVZ_REWARD]
        wb_logistics = finance_category_totals[EXPENSE_CATEGORY_WB_LOGISTICS]
        wb_logistics_rebill = finance_category_totals[
            EXPENSE_CATEGORY_WB_LOGISTICS_REBILL
        ]
        storage = finance_category_totals[EXPENSE_CATEGORY_STORAGE]
        acceptance = finance_category_totals[EXPENSE_CATEGORY_ACCEPTANCE]
        penalty = finance_category_totals[EXPENSE_CATEGORY_PENALTY]
        deduction = finance_category_totals[EXPENSE_CATEGORY_DEDUCTION]
        marketing_deduction = finance_category_totals[
            EXPENSE_CATEGORY_MARKETING_DEDUCTION
        ]
        loyalty = finance_category_totals[EXPENSE_CATEGORY_LOYALTY]
        other_wb_expenses = finance_category_totals[EXPENSE_CATEGORY_UNCLASSIFIED]
        additional_income = finance_category_totals[EXPENSE_CATEGORY_ADDITIONAL_PAYMENT]
        commission = wb_commission
        acquiring_fee = payment_processing
        logistics = wb_logistics + wb_logistics_rebill
        paid_acceptance = acceptance
        penalties = penalty
        deductions = deduction + loyalty + other_wb_expenses
        row_ad_spend_operational = sum(
            (
                self._decimal(getattr(item, "ad_spend_operational", None))
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        row_ad_spend_final = sum(
            (
                self._decimal(
                    getattr(item, "ad_spend_final", getattr(item, "ad_spend", None))
                )
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        seller_cogs = sum(
            (
                self._decimal(
                    getattr(item, "seller_cogs", getattr(item, "estimated_cogs", None))
                )
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        seller_other_expense = sum(
            (
                self._decimal(getattr(item, "seller_other_expense", None))
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        mart_ads_allocated_spend = sum(
            (
                self._decimal(
                    getattr(item, "raw_ad_spend", None)
                    if getattr(item, "raw_ad_spend", None) is not None
                    else getattr(item, "ad_spend", None)
                )
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        ads_source_spend = self._decimal(state.ads_source_total)
        ads_allocatable_source_spend = sum(
            (
                self._decimal(
                    getattr(item, "capped_ad_spend", None)
                    if getattr(item, "capped_ad_spend", None) is not None
                    else getattr(item, "ad_spend", None)
                )
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        ads_metrics = self._ads_allocation_metrics(
            ads_source_spend=ads_source_spend,
            mart_ads_allocated_spend=mart_ads_allocated_spend,
            ads_allocatable_source_spend=ads_allocatable_source_spend,
        )
        raw_ads_allocated_spend = self._decimal(ads_metrics["raw_ads_allocated"])
        ads_allocated_spend = self._decimal(ads_metrics["ads_allocated_spend"])
        ads_unallocated_spend = self._decimal(ads_metrics["ads_unallocated_spend"])
        ads_duplicate_ignored_spend = self._decimal(
            ads_metrics.get("ads_duplicate_ignored_spend", Decimal("0"))
        )
        ads_overallocated_spend = self._decimal(ads_metrics["ads_overallocated_spend"])
        cogs = seller_cogs
        row_profit_after_ads = sum(
            (
                self._decimal(item.estimated_profit)
                for item in state.profit_rows
                if item.estimated_profit is not None
            ),
            start=Decimal("0"),
        )
        wb_expenses_total = (
            wb_commission
            + payment_processing
            + pvz_reward
            + wb_logistics
            + wb_logistics_rebill
            + storage
            + acceptance
            + penalty
            + deduction
            + loyalty
            + other_wb_expenses
        )
        total_seller_expense_value = seller_cogs + seller_other_expense
        direct_wb_expenses = max(Decimal("0"), wb_expenses_total - unallocated_expenses)
        ad_spend_finance = marketing_deduction
        ad_spend_operational = max(row_ad_spend_operational, ads_source_spend)
        if ad_spend_finance > 0:
            final_store_ad_spend = ad_spend_finance
            final_ad_source = AD_SPEND_SOURCE_FINANCE
        elif ad_spend_operational > 0:
            final_store_ad_spend = ad_spend_operational
            final_ad_source = AD_SPEND_SOURCE_OPERATIONAL
        else:
            final_store_ad_spend = row_ad_spend_final
            final_ad_source = (
                AD_SPEND_SOURCE_OPERATIONAL
                if row_ad_spend_final > 0
                else AD_SPEND_SOURCE_NONE
            )
        profit_before_ads = (
            revenue
            - direct_wb_expenses
            - total_seller_expense_value
            + additional_income
        )
        if profit_before_ads == 0 and row_profit_after_ads != 0:
            profit_before_ads = row_profit_after_ads + final_store_ad_spend
        ads_allocated_profit_spend = (
            ads_allocated_spend if ads_source_spend > 0 else final_store_ad_spend
        )
        ads_source_profit_spend = (
            ads_source_spend if ads_source_spend > 0 else final_store_ad_spend
        )
        profit_after_allocated_ads = profit_before_ads - ads_allocated_profit_spend
        profit_after_source_ads = profit_before_ads - ads_source_profit_spend
        profit_after_overhead = profit_after_source_ads - unallocated_expenses
        net_profit_all_expenses = (
            revenue
            - wb_expenses_total
            - total_seller_expense_value
            - final_store_ad_spend
            + additional_income
        )
        finance_confirmed_revenue = state.finance_confirmed_revenue_total
        mart_revenue = (
            state.finance_closed_mart_revenue_total
            if state.finance_coverage_date_to is not None
            else revenue
        )
        profit_by_sku = {
            int(item.sku_id): item
            for item in state.profit_rows
            if item.sku_id is not None
        }
        stock_value = Decimal("0")
        overstock_value = Decimal("0")
        in_transit_value = Decimal("0")
        stock_confidence_rank = {"low": 1, "medium": 2, "high": 3}
        stock_confidence = "low"
        stock_reason = "stock_value_not_computable"
        for row in state.control_rows:
            if row.sku_id is None:
                continue
            profit_row = profit_by_sku.get(int(row.sku_id))
            if profit_row is None:
                continue
            purchase_row = state.purchase_rows.get(int(row.sku_id))
            components = self._stock_value_components(
                row,
                profit_row,
                purchase_row,
                business_trusted=state.health.business_trusted,
            )
            row_stock_value = self._decimal(components["stock_value"])
            row_in_transit_value = self._decimal(components["in_transit_value"])
            stock_value += row_stock_value
            in_transit_value += row_in_transit_value
            if row.sku_status == "LIQUIDATE":
                overstock_value += row_stock_value
            row_confidence = components["stock_value_confidence"]
            if (
                row_stock_value > 0
                and stock_confidence_rank[row_confidence]
                >= stock_confidence_rank[stock_confidence]
            ):
                stock_confidence = row_confidence
                stock_reason = components["stock_value_reason"]
        active_actions = [
            self._action_from_recommendation(action)
            for action in state.action_reads
            if self._is_open_action_status(action.status)
        ]
        active_actions.sort(
            key=lambda item: (
                self._priority_rank(item.priority),
                1 if self._is_account_level_linked_entity(item.linked_entity) else 0,
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        )
        finance_reconciliation = await self._finance_reconciliation_summary(
            session,
            account_id=account_id,
            requested_date_from=actual_from,
            requested_date_to=actual_to,
            account_level_expense_total=unallocated_expenses,
            closed_mart_revenue=state.finance_closed_mart_revenue_total,
            full_mart_revenue=revenue,
        )
        revenue_sources = self._build_revenue_sources(
            health=state.health,
            revenue=revenue,
            finance_confirmed_revenue=finance_confirmed_revenue,
            mart_revenue=mart_revenue,
            full_mart_revenue=revenue,
            finance_coverage_date_to=state.finance_coverage_date_to,
            requested_date_to=actual_to,
        )
        revenue_sources.operational_revenue = finance_reconciliation.operational_revenue
        revenue_sources.operational_revenue_label = (
            finance_reconciliation.operational_revenue_label
        )
        revenue_sources.finance_confirmed_revenue = (
            finance_reconciliation.finance_confirmed_revenue
        )
        revenue_sources.finance_confirmed_revenue_label = (
            finance_reconciliation.finance_confirmed_revenue_label
        )
        revenue_sources.mart_revenue = finance_reconciliation.operational_revenue
        revenue_sources.comparison_mart_revenue = (
            finance_reconciliation.operational_revenue
        )
        revenue_sources.open_period_revenue = (
            finance_reconciliation.open_operational_period_revenue
        )
        revenue_sources.open_period_revenue_label = (
            finance_reconciliation.open_operational_period_revenue_label
        )
        revenue_sources.difference_amount = finance_reconciliation.difference_amount
        revenue_sources.difference_percent = finance_reconciliation.difference_percent
        revenue_sources.reconciliation_status = finance_reconciliation.status
        revenue_sources.finance_coverage_date_to = (
            finance_reconciliation.closed_finance_date_to
        )
        revenue_sources.mismatch_reason = (
            "finance_report_not_loaded"
            if finance_reconciliation.status == "not_available"
            else "finance_vs_operational_partially_classified"
            if finance_reconciliation.status != "matched"
            else ""
        )
        quality = self._build_quality(
            health=state.health,
            ads_metrics=ads_metrics,
            revenue_sources=revenue_sources,
        )
        summary_cost_coverage = self._cost_coverage_from_health(state.health)
        quality.finance_difference_amount = finance_reconciliation.difference_amount
        quality.finance_difference_percent = finance_reconciliation.difference_percent
        quality.final_finance_ready = finance_reconciliation.is_final
        quality.finance_reconciliation_status = finance_reconciliation.status
        expense_quality = merge_expense_data_quality(
            [compute_expense_data_quality(item) for item in state.profit_rows]
            + [
                compute_expense_data_quality(item)
                for item in state.account_expense_rows
            ]
            + (
                [EXPENSE_DATA_QUALITY_UNCLASSIFIED_PRESENT]
                if other_wb_expenses > 0
                else []
            )
        )
        unallocated_expense_ratio_percent = (
            self._percent0(unallocated_expenses, revenue) if revenue > 0 else 0.0
        )
        answer = self._summary_answer(
            state.health,
            revenue_sources=revenue_sources,
            quality=quality,
            unallocated_expense_ratio_percent=unallocated_expense_ratio_percent,
        )
        profit_confidence = (
            "high"
            if answer.business_status == "healthy"
            else "medium"
            if answer.business_status == "provisional"
            else "low"
        )
        commission_out = self._positive_part(commission)
        acquiring_fee_out = self._positive_part(acquiring_fee)
        logistics_out = self._positive_part(logistics)
        paid_acceptance_out = self._positive_part(paid_acceptance)
        storage_out = self._positive_part(storage)
        penalties_out = self._positive_part(penalties)
        deductions_out = self._positive_part(deductions)
        incoming_adjustments = (
            self._negative_part_abs(commission)
            + self._negative_part_abs(acquiring_fee)
            + self._negative_part_abs(logistics)
            + self._negative_part_abs(paid_acceptance)
            + self._negative_part_abs(storage)
            + self._negative_part_abs(penalties)
            + self._negative_part_abs(deductions)
        )
        kpis = MoneySummaryKpis(
            revenue=float(revenue),
            revenue_final=float(revenue),
            finance_confirmed_revenue=self._float0(finance_confirmed_revenue),
            finance_reconciliation_operational_revenue=finance_reconciliation.operational_revenue,
            finance_difference_amount=finance_reconciliation.difference_amount,
            finance_difference_percent=finance_reconciliation.difference_percent,
            finance_reconciliation_status=finance_reconciliation.status,
            supplier_cost_confirmed_revenue=self._float0(
                state.health.revenue_with_real_cost
            ),
            supplier_cost_confirmed_revenue_percent=self._float0(
                state.health.supplier_confirmed_revenue_coverage_percent
            ),
            business_cost_coverage_percent=quality.business_cost_coverage_percent,
            cost_coverage_status=quality.cost_coverage_status,
            for_pay=float(for_pay),
            net_profit_after_ads=float(profit_after_source_ads),
            profit_after_allocated_ads=float(profit_after_allocated_ads),
            profit_after_source_ads=float(profit_after_source_ads),
            net_profit_after_overhead=float(profit_after_overhead),
            margin_percent=self._percent0(profit_after_source_ads, revenue),
            margin_after_overhead_percent=self._percent0(
                profit_after_overhead, revenue
            ),
            roi_percent=self._percent0(profit_after_source_ads, cogs)
            if cogs > 0
            else 0.0,
            roi_on_cogs_percent=self._percent0(profit_after_source_ads, cogs)
            if cogs > 0
            else 0.0,
            stock_roi_percent=self._percent0(profit_after_source_ads, stock_value)
            if stock_value > 0
            else 0.0,
            roas_percent=self._percent0(
                revenue,
                final_store_ad_spend if final_store_ad_spend > 0 else ads_source_spend,
            )
            if (final_store_ad_spend > 0 or ads_source_spend > 0)
            else 0.0,
            profit_confidence=profit_confidence,
            cash_on_wb=current_balance_amount,
            available_for_withdraw=current_withdrawable_amount,
            cash_on_wb_current=current_balance_amount,
            available_for_withdraw_current=current_withdrawable_amount,
            cash_on_wb_period_end=period_end_balance_amount,
            available_for_withdraw_period_end=period_end_withdrawable_amount,
            balance_snapshot_at_current=getattr(latest_balance, "snapshot_at", None),
            balance_snapshot_at_period_end=getattr(
                period_end_balance, "snapshot_at", None
            ),
            wb_expenses_total=float(wb_expenses_total),
            direct_wb_expenses=float(direct_wb_expenses),
            account_level_expenses=float(unallocated_expenses),
            allocated_overhead_expenses=0.0,
            stock_value=float(stock_value),
            overstock_value=float(overstock_value),
            in_transit_value=float(in_transit_value),
            stock_value_confidence=stock_confidence if stock_value > 0 else "low",
            stock_value_reason="" if stock_value > 0 else stock_reason,
            ad_spend=float(final_store_ad_spend),
            ad_spend_operational=float(ad_spend_operational),
            ad_spend_finance=float(ad_spend_finance),
            ad_spend_final=float(final_store_ad_spend),
            ad_spend_source=final_ad_source,
            ad_spend_delta=float(ad_spend_operational - ad_spend_finance),
            ads_source_spend=float(ads_source_spend),
            raw_ads_allocated_spend=float(raw_ads_allocated_spend),
            capped_ads_allocated_spend=float(ads_allocated_spend),
            ads_allocated_spend=float(ads_allocated_spend),
            ads_unallocated_spend=float(ads_unallocated_spend),
            ads_duplicate_ignored_spend=float(ads_duplicate_ignored_spend),
            ads_overallocated_spend=float(ads_overallocated_spend),
            ads_allocation_status=str(ads_metrics["ads_allocation_status"]),
            wb_commission=float(wb_commission),
            payment_processing=float(payment_processing),
            pvz_reward=float(pvz_reward),
            wb_logistics=float(wb_logistics),
            wb_logistics_rebill=float(wb_logistics_rebill),
            storage=float(storage),
            acceptance=float(acceptance),
            penalty=float(penalty),
            deduction=float(deduction),
            marketing_deduction=float(marketing_deduction),
            loyalty=float(loyalty),
            additional_payment=float(additional_income),
            other_wb_expenses=float(other_wb_expenses),
            seller_cogs=float(seller_cogs),
            seller_other_expense=float(seller_other_expense),
            total_seller_expenses=float(total_seller_expense_value),
            total_seller_costs=float(total_seller_expense_value),
            additional_income=float(additional_income),
            net_profit_after_all_expenses=float(net_profit_all_expenses),
            expense_data_quality=expense_quality,
            logistics_share_percent=self._percent0(logistics, wb_expenses_total)
            if wb_expenses_total > 0
            else 0.0,
            unallocated_expenses=float(unallocated_expenses),
            unallocated_expense_ratio_percent=unallocated_expense_ratio_percent,
            negative_profit_sku_count=sum(
                1
                for item in state.control_rows
                if item.net_profit is not None and item.net_profit < 0
            ),
            blocked_data_sku_count=sum(
                1
                for item in state.control_rows
                if item.trust_state == TRUST_STATE_DATA_BLOCKED
            ),
        )
        expenses = self._store_expenses_waterfall(
            profit_rows=state.profit_rows,
            account_expense_rows=state.account_expense_rows,
            unallocated_expenses=unallocated_expenses,
        )
        incoming_items = [
            MoneyFlowItem(
                code="sales_revenue",
                label="Выручка от продаж",
                amount=float(revenue),
                direction="in",
                confidence="medium",
            ),
            MoneyFlowItem(
                code="additional_payments",
                label="Доплаты",
                amount=float(additional_income),
                direction="in",
                confidence="medium",
            ),
        ]
        if incoming_adjustments > 0:
            incoming_items.append(
                MoneyFlowItem(
                    code="adjustments",
                    label="Корректировки и возвраты",
                    amount=self._float0(incoming_adjustments),
                    direction="in",
                    confidence="medium",
                    reason="expense_corrections_or_refunds",
                )
            )
        money_flow = MoneyFlowBlock(
            incoming=incoming_items,
            outgoing=[
                MoneyFlowItem(
                    code="commission",
                    label="WB комиссия",
                    amount=self._float0(commission_out),
                    direction="out",
                    confidence="medium" if commission_out > 0 else "low",
                    reason="" if commission_out > 0 else "expense_correction",
                ),
                MoneyFlowItem(
                    code="acquiring_fee",
                    label="Эквайринг",
                    amount=self._float0(acquiring_fee_out),
                    direction="out",
                    confidence="medium" if acquiring_fee_out > 0 else "low",
                    reason="" if acquiring_fee_out > 0 else "expense_correction",
                ),
                MoneyFlowItem(
                    code="logistics",
                    label="Логистика",
                    amount=self._float0(logistics_out + paid_acceptance_out),
                    direction="out",
                    confidence="medium"
                    if logistics_out + paid_acceptance_out > 0
                    else "low",
                    reason=""
                    if logistics_out + paid_acceptance_out > 0
                    else "partially_account_level",
                ),
                MoneyFlowItem(
                    code="storage",
                    label="Хранение",
                    amount=self._float0(storage_out),
                    direction="out",
                    confidence="medium" if storage_out > 0 else "low",
                    reason="" if storage_out > 0 else "partially_account_level",
                ),
                MoneyFlowItem(
                    code="penalties_and_deductions",
                    label="Штрафы и удержания",
                    amount=self._float0(penalties_out + deductions_out),
                    direction="out",
                    confidence="medium"
                    if penalties_out + deductions_out > 0
                    else "low",
                    reason=""
                    if penalties_out + deductions_out > 0
                    else "expense_correction",
                ),
                MoneyFlowItem(
                    code="ads",
                    label="Реклама",
                    amount=float(final_store_ad_spend),
                    direction="out",
                    confidence="medium" if final_store_ad_spend > 0 else "low",
                    reason=""
                    if final_store_ad_spend > 0
                    and ads_unallocated_spend <= 0
                    and ads_overallocated_spend <= 0
                    else "ads_not_fully_allocated",
                ),
                MoneyFlowItem(
                    code="cogs",
                    label="Себестоимость",
                    amount=float(cogs),
                    direction="out",
                    confidence="high" if state.health.business_trusted else "low",
                    reason="" if cogs > 0 else "supplier_cost_not_confirmed",
                ),
                MoneyFlowItem(
                    code="unallocated_expenses",
                    label="Неаллокированные расходы",
                    amount=float(unallocated_expenses),
                    direction="out",
                    confidence="low",
                    reason="" if unallocated_expenses > 0 else "not_allocated_to_sku",
                ),
            ],
            cash_and_stock=[
                MoneyFlowItem(
                    code="wb_balance",
                    label="Баланс WB",
                    amount=current_balance_amount,
                    direction="asset",
                    confidence="high" if latest_balance is not None else "low",
                ),
                MoneyFlowItem(
                    code="stock_value",
                    label="Деньги в остатках",
                    amount=float(stock_value),
                    direction="asset",
                    confidence=stock_confidence if stock_value > 0 else "low",
                    reason="" if stock_value > 0 else stock_reason,
                ),
                MoneyFlowItem(
                    code="in_transit_value",
                    label="Деньги в пути",
                    amount=float(in_transit_value),
                    direction="asset",
                    confidence=stock_confidence if in_transit_value > 0 else "low",
                    reason="" if in_transit_value > 0 else stock_reason,
                ),
            ],
        )
        risk_titles = {
            "supplier_cost_coverage_below_threshold": (
                "Нет подтвержденной реальной себестоимости",
                "Итоговая прибыль и окупаемость пока не подтверждены.",
            ),
            "unmatched_sku_detected": (
                "Не закрыта привязка товаров к карточкам",
                "Деньги могут распределяться по карточкам неверно",
            ),
            "latest_stocks_not_completed": (
                "Синхронизация остатков не завершена",
                "Остатки и закупочные рекомендации ненадежны",
            ),
            "open_blocking_dq_issues": (
                "Есть блокирующие проблемы качества данных",
                "Бизнес-действия заблокированы, пока эти проблемы не разобраны.",
            ),
            "failed_sync_domains": (
                "Есть ошибки в загрузке данных",
                "Часть исходных данных может быть неполной.",
            ),
            "article_audit_mismatch": (
                "Есть расхождение в аудите артикула",
                "Доверие к прибыли карточки снижено",
            ),
        }
        risks = [
            RiskItem(
                code=reason,
                title=risk_titles.get(
                    reason,
                    (
                        "Блокер данных",
                        "Пока блокер не закрыт, безопасные бизнес-решения невозможны.",
                    ),
                )[0],
                business_impact=risk_titles.get(
                    reason,
                    (
                        "Блокер данных",
                        "Пока блокер не закрыт, безопасные бизнес-решения невозможны.",
                    ),
                )[1],
                priority="critical",
            )
            for reason in state.health.blocked_reasons
        ]
        # Finance reconciliation mismatches are handled by system sync/matching.
        # They must not be shown to the owner as a manual top risk.
        if (quality.supplier_cost_coverage_percent or 0) < 95:
            risks.append(
                RiskItem(
                    code="supplier_cost_not_final",
                    title="Не хватает подтвержденной реальной себестоимости",
                    business_impact="Итоговая прибыль и окупаемость пока считаются предварительно.",
                    priority="high",
                )
            )
        if ads_source_spend > 0 and (
            quality.ads_overallocated_spend > 0
            or (quality.ads_allocation_percent_capped or 0) < 95
        ):
            risks.append(
                RiskItem(
                    code="ads_allocation_issue",
                    title="Рекламные расходы распределены не полностью",
                    business_impact="Часть рекламных расходов привязана к прибыли некорректно или неполно.",
                    priority="high",
                )
            )
        if unallocated_expense_ratio_percent > 5:
            risks.append(
                RiskItem(
                    code="large_unallocated_expenses",
                    title="Слишком много общих расходов без привязки к карточкам",
                    business_impact="Прибыль магазина заметно ниже прибыли по карточкам, потому что часть расходов пока не распределена.",
                    priority="high",
                )
            )
        deduped_risks: list[RiskItem] = []
        seen_risk_codes: set[str] = set()
        for risk in risks:
            if risk.code in seen_risk_codes:
                continue
            seen_risk_codes.add(risk.code)
            deduped_risks.append(risk)
        profit_cascade = self._build_profit_cascade(
            meta=meta,
            revenue_sources=revenue_sources,
            kpis=kpis,
            data_version_hash=state.data_version_hash,
        )
        expense_breakdown = self._summary_expense_breakdown(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            kpis=kpis,
            data_version_hash=state.data_version_hash,
            source_of_truth=profit_cascade.source_of_truth,
        )
        result = MoneySummaryRead(
            **self._response_cache_fields(state),
            meta=meta,
            trust=meta.data_trust,
            answer=answer,
            store_answer=self._build_store_answer(
                health=state.health,
                answer=answer,
                revenue=revenue,
                cogs=cogs,
                direct_wb_expenses=direct_wb_expenses,
                ad_spend_final=final_store_ad_spend,
                unallocated_expenses=unallocated_expenses,
                latest_balance=latest_balance,
                stock_value=stock_value,
                in_transit_value=in_transit_value,
                next_actions=active_actions,
            ),
            revenue_sources=revenue_sources,
            finance_reconciliation=finance_reconciliation,
            cost_coverage=summary_cost_coverage,
            quality=quality,
            kpis=kpis,
            expenses=expenses,
            expense_breakdown=expense_breakdown,
            profit_cascade=profit_cascade,
            money_flow=money_flow,
            cash_and_stock=CashAndStockBlock(
                cash_on_wb=kpis.cash_on_wb,
                available_for_withdraw=kpis.available_for_withdraw,
                cash_on_wb_current=kpis.cash_on_wb_current,
                available_for_withdraw_current=kpis.available_for_withdraw_current,
                cash_on_wb_period_end=kpis.cash_on_wb_period_end,
                available_for_withdraw_period_end=kpis.available_for_withdraw_period_end,
                balance_snapshot_at_current=kpis.balance_snapshot_at_current,
                balance_snapshot_at_period_end=kpis.balance_snapshot_at_period_end,
                stock_value=kpis.stock_value,
                overstock_value=kpis.overstock_value,
                in_transit_value=kpis.in_transit_value,
                frozen_stock_value=kpis.stock_value + kpis.in_transit_value,
                confidence=kpis.stock_value_confidence,
                reason=kpis.stock_value_reason,
            ),
            risk_summary=RiskSummary(
                critical_count=sum(
                    1 for item in deduped_risks if item.priority == "critical"
                ),
                risks=deduped_risks,
            ),
            top_cards=self._top_cards_block(state.control_rows),
            next_actions=active_actions[:10],
            control_panel=self._money_control_panel(
                state=state,
                meta=meta,
                revenue_sources=revenue_sources,
                finance_reconciliation=finance_reconciliation,
                cost_coverage=summary_cost_coverage,
                quality=quality,
                kpis=kpis,
                risks=deduped_risks,
                actions=active_actions,
            ),
        )
        summary_cache[summary_cache_key] = (utcnow(), result.model_copy(deep=True))
        summary_window_cache[summary_window_key] = (
            utcnow(),
            result.model_copy(deep=True),
        )
        return result

    async def profit_cascade(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ProfitCascadeRead:
        summary = await self.summary(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        if summary.profit_cascade is not None:
            return summary.profit_cascade.model_copy(deep=True)
        return self._build_profit_cascade(
            meta=summary.meta,
            revenue_sources=summary.revenue_sources,
            kpis=summary.kpis,
            data_version_hash=summary.data_version_hash,
        )

    async def expense_breakdown(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        group_by: str = "category",
        include_unallocated: bool = True,
    ) -> ExpenseBreakdownSummaryRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        summary: MoneySummaryRead | None = None
        summary_breakdown: ExpenseBreakdownSummaryRead | None = None
        summary_profit_cascade: ProfitCascadeRead | None = None
        summary_total_expenses: Decimal | None = None
        summary_total_wb_expenses: Decimal | None = None
        summary_total_seller_expenses: Decimal | None = None
        summary_total_ad_expenses: Decimal | None = None
        summary_logistics_total: Decimal | None = None
        summary_logistics_share_base_kind: str | None = None
        summary_logistics_share_base_amount: Decimal | None = None
        if include_unallocated:
            summary = await self.summary(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            )
            summary_breakdown = (
                summary.expense_breakdown.model_copy(deep=True)
                if summary.expense_breakdown is not None
                else None
            )
            summary_profit_cascade = (
                summary.profit_cascade.model_copy(deep=True)
                if summary.profit_cascade is not None
                else None
            )
            if summary_profit_cascade is not None:
                cascade_totals = summary_profit_cascade.cascade.totals
                summary_total_wb_expenses = self._decimal(
                    cascade_totals.total_wb_expenses
                )
                summary_total_seller_expenses = self._decimal(
                    cascade_totals.total_seller_expenses
                )
                summary_total_ad_expenses = self._decimal(
                    cascade_totals.total_ad_expenses
                )
                summary_total_expenses = (
                    summary_total_wb_expenses
                    + summary_total_seller_expenses
                    + summary_total_ad_expenses
                )
                summary_logistics_total = self._decimal(cascade_totals.logistics_total)
            if summary_breakdown is not None:
                summary_logistics_share_base_kind = (
                    summary_breakdown.logistics_share_base_kind
                )
                summary_logistics_share_base_amount = self._decimal(
                    summary_breakdown.logistics_share_base_amount
                )
                if summary_total_expenses is None:
                    summary_total_expenses = self._decimal(
                        summary_breakdown.total_expenses
                    )
                if summary_total_wb_expenses is None:
                    summary_total_wb_expenses = self._decimal(
                        summary_breakdown.total_wb_expenses
                    )
                if summary_total_seller_expenses is None:
                    summary_total_seller_expenses = self._decimal(
                        summary_breakdown.total_seller_expenses
                    )
                if summary_total_ad_expenses is None:
                    summary_total_ad_expenses = self._decimal(
                        summary_breakdown.total_ad_expenses
                    )
                if summary_logistics_total is None:
                    summary_logistics_total = self._decimal(
                        summary_breakdown.logistics_total
                    )
            if group_by == "category" and summary_breakdown is not None:
                return summary_breakdown.model_copy(
                    deep=True,
                    update={
                        "group_by": group_by,
                        "include_unallocated": include_unallocated,
                    },
                )
        totals = await self._expense_totals(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            include_unallocated=include_unallocated,
        )
        total_expenses = self._decimal(totals["total_expenses"])
        total_wb_expenses = self._decimal(totals["total_wb_expenses"])
        logistics_share_base_kind, logistics_share_base_amount = (
            self._logistics_share_base(
                total_wb_expenses=total_wb_expenses,
                total_expenses=total_expenses,
            )
        )
        response_total_expenses = (
            summary_total_expenses
            if summary_total_expenses is not None
            else total_expenses
        )
        response_total_wb_expenses = (
            summary_total_wb_expenses
            if summary_total_wb_expenses is not None
            else total_wb_expenses
        )
        response_total_seller_expenses = (
            summary_total_seller_expenses
            if summary_total_seller_expenses is not None
            else self._decimal(totals["total_seller_expenses"])
        )
        response_total_ad_expenses = (
            summary_total_ad_expenses
            if summary_total_ad_expenses is not None
            else self._decimal(totals["total_ad_expenses"])
        )
        response_logistics_total = (
            summary_logistics_total
            if summary_logistics_total is not None
            else self._decimal(totals["logistics_total"])
        )
        response_logistics_share_base_kind = (
            summary_logistics_share_base_kind or logistics_share_base_kind
        )
        response_logistics_share_base_amount = (
            summary_logistics_share_base_amount
            if summary_logistics_share_base_amount is not None
            and summary_logistics_share_base_amount > 0
            else logistics_share_base_amount
        )
        buckets: dict[str, dict[str, Any]] = {}
        finance_mode = str(totals.get("finance_mode", "row_level") or "row_level")
        if finance_mode == "raw_finance":
            raw_entries = await self._raw_finance_expense_entries(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            )
            if group_by == "category":
                for entry in raw_entries:
                    category = str(entry.get("expense_category") or "")
                    if category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT:
                        continue
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=category,
                        amount=self._decimal(MartService._entry_signed_amount(entry)),
                        source=self.EXPENSE_CATEGORY_PRIMARY_SOURCE.get(
                            category, "finance_report"
                        ),
                        category=category,
                        label=self._expense_category_label(category),
                        row_count=1,
                    )
            elif group_by == "source":
                finance_total = sum(
                    (
                        self._decimal(MartService._entry_signed_amount(entry))
                        for entry in raw_entries
                        if str(entry.get("expense_category") or "")
                        != EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                    ),
                    start=Decimal("0"),
                )
                if finance_total != 0:
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key="finance_report",
                        amount=finance_total,
                        source="finance_report",
                        label=self._expense_source_label("finance_report"),
                        row_count=len(raw_entries),
                    )
            elif group_by == "day":
                for entry in raw_entries:
                    if (
                        str(entry.get("expense_category") or "")
                        == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                    ):
                        continue
                    stat_date = entry.get("stat_date")
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=str(stat_date),
                        amount=self._decimal(MartService._entry_signed_amount(entry)),
                        source="finance_report",
                        stat_date=stat_date,
                        row_count=1,
                    )
            elif group_by == "sku":
                for entry in raw_entries:
                    if (
                        str(entry.get("expense_category") or "")
                        == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                    ):
                        continue
                    raw_sku_id = entry.get("sku_id")
                    bucket_key = (
                        f"sku:{raw_sku_id}"
                        if raw_sku_id is not None
                        else "sku:unallocated"
                    )
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=bucket_key,
                        amount=self._decimal(MartService._entry_signed_amount(entry)),
                        source="finance_report",
                        sku_id=raw_sku_id,
                        nm_id=entry.get("nm_id"),
                        vendor_code=entry.get("vendor_code"),
                        barcode=entry.get("barcode"),
                        label=entry.get("vendor_code")
                        or (
                            "Не распределено по SKU"
                            if raw_sku_id is None
                            else f"SKU {raw_sku_id}"
                        ),
                        row_count=1,
                    )
            elif group_by == "nm":
                for entry in raw_entries:
                    if (
                        str(entry.get("expense_category") or "")
                        == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                    ):
                        continue
                    raw_nm_id = entry.get("nm_id")
                    bucket_key = (
                        f"nm:{raw_nm_id}" if raw_nm_id is not None else "nm:unallocated"
                    )
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=bucket_key,
                        amount=self._decimal(MartService._entry_signed_amount(entry)),
                        source="finance_report",
                        nm_id=raw_nm_id,
                        label=str(raw_nm_id)
                        if raw_nm_id is not None
                        else "Не распределено по nmId",
                        row_count=1,
                    )
            else:
                raise HTTPException(
                    status_code=400, detail="Unsupported group_by value"
                )
        elif finance_mode == "account_level":
            account_rows = (
                await self._account_level_expense_rows(
                    session,
                    account_id=account_id,
                    date_from=actual_from,
                    date_to=actual_to,
                )
                if include_unallocated
                else []
            )
            if group_by == "category":
                for row in account_rows:
                    for (
                        category,
                        amount,
                    ) in self._account_level_expense_category_amounts(row):
                        if amount == 0:
                            continue
                        self._merge_expense_bucket(
                            buckets,
                            bucket_key=category,
                            amount=amount,
                            source=self.EXPENSE_CATEGORY_PRIMARY_SOURCE.get(
                                category, "finance_report"
                            ),
                            category=category,
                            label=self._expense_category_label(category),
                            row_count=1,
                        )
            elif group_by == "source":
                finance_total = sum(
                    (
                        self._account_level_expense_total_with_finance_ads(row)
                        for row in account_rows
                    ),
                    start=Decimal("0"),
                )
                if finance_total != 0:
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key="finance_report",
                        amount=finance_total,
                        source="finance_report",
                        label=self._expense_source_label("finance_report"),
                        row_count=len(account_rows),
                    )
            elif group_by == "day":
                for row in account_rows:
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=str(row.stat_date),
                        amount=self._account_level_expense_total_with_finance_ads(row),
                        source="finance_report",
                        stat_date=row.stat_date,
                        row_count=1,
                    )
            elif group_by == "sku":
                finance_total = sum(
                    (
                        self._account_level_expense_total_with_finance_ads(row)
                        for row in account_rows
                    ),
                    start=Decimal("0"),
                )
                if finance_total != 0:
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key="sku:unallocated",
                        amount=finance_total,
                        source="finance_report",
                        label="Не распределено по SKU",
                        row_count=len(account_rows),
                    )
            elif group_by == "nm":
                finance_total = sum(
                    (
                        self._account_level_expense_total_with_finance_ads(row)
                        for row in account_rows
                    ),
                    start=Decimal("0"),
                )
                if finance_total != 0:
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key="nm:unallocated",
                        amount=finance_total,
                        source="finance_report",
                        label="Не распределено по nmId",
                        row_count=len(account_rows),
                    )
            else:
                raise HTTPException(
                    status_code=400, detail="Unsupported group_by value"
                )
        else:
            signed_amount = self._expense_signed_amount_expr()
            finance_filters = self._expense_base_filters(
                account_id=account_id, date_from=actual_from, date_to=actual_to
            )
            if not include_unallocated:
                finance_filters.append(MartExpenseDaily.is_allocated_to_sku.is_(True))
            expense_group_filters = [
                *finance_filters,
                MartExpenseDaily.expense_category
                != EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
            ]
            if group_by == "category":
                finance_stmt = (
                    select(
                        MartExpenseDaily.expense_category,
                        func.coalesce(func.sum(signed_amount), 0),
                        func.count(),
                    )
                    .where(*expense_group_filters)
                    .group_by(MartExpenseDaily.expense_category)
                )
                for category, amount, row_count in (
                    await session.execute(finance_stmt)
                ).all():
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=str(category or "unknown"),
                        amount=self._decimal(amount),
                        source=self.EXPENSE_CATEGORY_PRIMARY_SOURCE.get(
                            str(category or ""), "finance_report"
                        ),
                        category=str(category or ""),
                        label=self._expense_category_label(str(category or "")),
                        row_count=int(row_count or 0),
                    )
            elif group_by == "source":
                finance_stmt = (
                    select(
                        MartExpenseDaily.expense_source,
                        func.coalesce(func.sum(signed_amount), 0),
                        func.count(),
                    )
                    .where(*expense_group_filters)
                    .group_by(MartExpenseDaily.expense_source)
                )
                for source, amount, row_count in (
                    await session.execute(finance_stmt)
                ).all():
                    source_key = str(source or "finance_report")
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=source_key,
                        amount=self._decimal(amount),
                        source=source_key,
                        label=self._expense_source_label(source_key),
                        row_count=int(row_count or 0),
                    )
            elif group_by == "day":
                finance_stmt = (
                    select(
                        MartExpenseDaily.stat_date,
                        func.coalesce(func.sum(signed_amount), 0),
                        func.count(),
                    )
                    .where(*expense_group_filters)
                    .group_by(MartExpenseDaily.stat_date)
                )
                for stat_date, amount, row_count in (
                    await session.execute(finance_stmt)
                ).all():
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=str(stat_date),
                        amount=self._decimal(amount),
                        source="finance_report",
                        stat_date=stat_date,
                        row_count=int(row_count or 0),
                    )
            elif group_by == "sku":
                finance_stmt = (
                    select(
                        MartExpenseDaily.sku_id,
                        MartExpenseDaily.nm_id,
                        CoreSKU.vendor_code,
                        MartExpenseDaily.barcode,
                        func.coalesce(func.sum(signed_amount), 0),
                        func.count(),
                    )
                    .select_from(MartExpenseDaily)
                    .outerjoin(CoreSKU, CoreSKU.id == MartExpenseDaily.sku_id)
                    .where(*expense_group_filters)
                    .group_by(
                        MartExpenseDaily.sku_id,
                        MartExpenseDaily.nm_id,
                        CoreSKU.vendor_code,
                        MartExpenseDaily.barcode,
                    )
                )
                for sku_id, nm_id, vendor_code, barcode, amount, row_count in (
                    await session.execute(finance_stmt)
                ).all():
                    bucket_key = (
                        f"sku:{sku_id}" if sku_id is not None else "sku:unallocated"
                    )
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=bucket_key,
                        amount=self._decimal(amount),
                        source="finance_report",
                        sku_id=sku_id,
                        nm_id=nm_id,
                        vendor_code=vendor_code,
                        barcode=barcode,
                        label="Не распределено по SKU"
                        if sku_id is None
                        else vendor_code or f"SKU {sku_id}",
                        row_count=int(row_count or 0),
                    )
            elif group_by == "nm":
                finance_stmt = (
                    select(
                        MartExpenseDaily.nm_id,
                        func.coalesce(func.sum(signed_amount), 0),
                        func.count(),
                    )
                    .where(*expense_group_filters)
                    .group_by(MartExpenseDaily.nm_id)
                )
                for nm_id, amount, row_count in (
                    await session.execute(finance_stmt)
                ).all():
                    bucket_key = (
                        f"nm:{nm_id}" if nm_id is not None else "nm:unallocated"
                    )
                    self._merge_expense_bucket(
                        buckets,
                        bucket_key=bucket_key,
                        amount=self._decimal(amount),
                        source="finance_report",
                        nm_id=nm_id,
                        label=str(nm_id)
                        if nm_id is not None
                        else "Не распределено по nmId",
                        row_count=int(row_count or 0),
                    )
            else:
                raise HTTPException(
                    status_code=400, detail="Unsupported group_by value"
                )

        if group_by == "category":
            seller_stmt = select(
                func.coalesce(func.sum(MartSKUDaily.seller_cogs), 0),
                func.coalesce(func.sum(MartSKUDaily.seller_other_expense), 0),
                func.coalesce(func.sum(self._sku_extra_ad_expr()), 0),
            ).where(
                *self._sku_daily_base_filters(
                    account_id=account_id, date_from=actual_from, date_to=actual_to
                )
            )
            seller_cogs_total, seller_other_total, ads_total = (
                await session.execute(seller_stmt)
            ).one()
            synthetic_specs = [
                (EXPENSE_CATEGORY_SELLER_COGS, self._decimal(seller_cogs_total)),
                (
                    EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE,
                    self._decimal(seller_other_total),
                ),
                ("ads_operational", self._decimal(ads_total)),
            ]
            for category, amount in synthetic_specs:
                if amount == 0:
                    continue
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=category,
                    amount=amount,
                    source=self.EXPENSE_CATEGORY_PRIMARY_SOURCE.get(category, "mixed"),
                    category=category,
                    label=self._expense_category_label(category),
                )
        elif group_by == "source":
            if self._decimal(totals["total_seller_expenses"]) != 0:
                self._merge_expense_bucket(
                    buckets,
                    bucket_key="manual_cost",
                    amount=self._decimal(totals["total_seller_expenses"]),
                    source="manual_cost",
                    label=self._expense_source_label("manual_cost"),
                )
            finance_ad_total = self._decimal(totals.get("finance_ad_expenses"))
            ads_api_total = (
                self._decimal(totals["total_ad_expenses"]) - finance_ad_total
            )
            if ads_api_total != 0:
                self._merge_expense_bucket(
                    buckets,
                    bucket_key="ads_api",
                    amount=ads_api_total,
                    source="ads_api",
                    label=self._expense_source_label("ads_api"),
                )
        elif group_by == "day":
            sku_stmt = (
                select(
                    MartSKUDaily.stat_date,
                    func.coalesce(func.sum(MartSKUDaily.seller_cogs), 0),
                    func.coalesce(func.sum(MartSKUDaily.seller_other_expense), 0),
                    func.coalesce(func.sum(self._sku_extra_ad_expr()), 0),
                )
                .where(
                    *self._sku_daily_base_filters(
                        account_id=account_id, date_from=actual_from, date_to=actual_to
                    )
                )
                .group_by(MartSKUDaily.stat_date)
            )
            for stat_date, seller_cogs_total, seller_other_total, ads_total in (
                await session.execute(sku_stmt)
            ).all():
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=str(stat_date),
                    amount=self._decimal(seller_cogs_total)
                    + self._decimal(seller_other_total),
                    source="manual_cost",
                    stat_date=stat_date,
                )
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=str(stat_date),
                    amount=self._decimal(ads_total),
                    source="ads_api",
                    stat_date=stat_date,
                )
        elif group_by == "sku":
            sku_stmt = (
                select(
                    MartSKUDaily.sku_id,
                    MartSKUDaily.nm_id,
                    MartSKUDaily.vendor_code,
                    MartSKUDaily.barcode,
                    func.coalesce(func.sum(MartSKUDaily.seller_cogs), 0),
                    func.coalesce(func.sum(MartSKUDaily.seller_other_expense), 0),
                    func.coalesce(func.sum(self._sku_extra_ad_expr()), 0),
                )
                .where(
                    *self._sku_daily_base_filters(
                        account_id=account_id, date_from=actual_from, date_to=actual_to
                    )
                )
                .group_by(
                    MartSKUDaily.sku_id,
                    MartSKUDaily.nm_id,
                    MartSKUDaily.vendor_code,
                    MartSKUDaily.barcode,
                )
            )
            for (
                sku_id,
                nm_id,
                vendor_code,
                barcode,
                seller_cogs_total,
                seller_other_total,
                ads_total,
            ) in (await session.execute(sku_stmt)).all():
                bucket_key = (
                    f"sku:{sku_id}" if sku_id is not None else "sku:unallocated"
                )
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=bucket_key,
                    amount=self._decimal(seller_cogs_total)
                    + self._decimal(seller_other_total),
                    source="manual_cost",
                    sku_id=sku_id,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    barcode=barcode,
                    label="Не распределено по SKU"
                    if sku_id is None
                    else vendor_code or f"SKU {sku_id}",
                )
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=bucket_key,
                    amount=self._decimal(ads_total),
                    source="ads_api",
                    sku_id=sku_id,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    barcode=barcode,
                    label="Не распределено по SKU"
                    if sku_id is None
                    else vendor_code or f"SKU {sku_id}",
                )
        elif group_by == "nm":
            sku_stmt = (
                select(
                    MartSKUDaily.nm_id,
                    func.coalesce(func.sum(MartSKUDaily.seller_cogs), 0),
                    func.coalesce(func.sum(MartSKUDaily.seller_other_expense), 0),
                    func.coalesce(func.sum(self._sku_extra_ad_expr()), 0),
                )
                .where(
                    *self._sku_daily_base_filters(
                        account_id=account_id, date_from=actual_from, date_to=actual_to
                    )
                )
                .group_by(MartSKUDaily.nm_id)
            )
            for nm_id, seller_cogs_total, seller_other_total, ads_total in (
                await session.execute(sku_stmt)
            ).all():
                bucket_key = f"nm:{nm_id}" if nm_id is not None else "nm:unallocated"
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=bucket_key,
                    amount=self._decimal(seller_cogs_total)
                    + self._decimal(seller_other_total),
                    source="manual_cost",
                    nm_id=nm_id,
                    label=str(nm_id)
                    if nm_id is not None
                    else "Не распределено по nmId",
                )
                self._merge_expense_bucket(
                    buckets,
                    bucket_key=bucket_key,
                    amount=self._decimal(ads_total),
                    source="ads_api",
                    nm_id=nm_id,
                    label=str(nm_id)
                    if nm_id is not None
                    else "Не распределено по nmId",
                )

        return ExpenseBreakdownSummaryRead(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            group_by=group_by,
            include_unallocated=include_unallocated,
            revenue_final=self._float0(getattr(summary.kpis, "revenue_final", 0.0))
            if summary is not None
            else 0.0,
            net_profit_after_all_expenses=self._float0(
                getattr(summary.kpis, "net_profit_after_all_expenses", 0.0)
            )
            if summary is not None
            else 0.0,
            seller_cogs=self._float0(getattr(summary.kpis, "seller_cogs", 0.0))
            if summary is not None
            else 0.0,
            seller_other_expense=self._float0(
                getattr(summary.kpis, "seller_other_expense", 0.0)
            )
            if summary is not None
            else 0.0,
            ad_spend_final=self._float0(getattr(summary.kpis, "ad_spend_final", 0.0))
            if summary is not None
            else 0.0,
            additional_income=self._float0(
                getattr(summary.kpis, "additional_income", 0.0)
            )
            if summary is not None
            else 0.0,
            total_expenses=self._float0(response_total_expenses),
            total_wb_expenses=self._float0(response_total_wb_expenses),
            total_seller_expenses=self._float0(response_total_seller_expenses),
            total_ad_expenses=self._float0(response_total_ad_expenses),
            logistics_total=self._float0(response_logistics_total),
            logistics_share_base_kind=response_logistics_share_base_kind,
            logistics_share_base_amount=self._float0(
                response_logistics_share_base_amount
            ),
            logistics_share_percent=self._percent0(
                response_logistics_total, response_logistics_share_base_amount
            )
            if response_logistics_share_base_amount > 0
            else 0.0,
            data_version_hash=summary.data_version_hash
            if summary is not None
            else None,
            source_of_truth=str(
                getattr(summary_profit_cascade, "source_of_truth", "mixed") or "mixed"
            ),
            items=self._expense_breakdown_items_from_buckets(
                buckets=buckets,
                total_expenses=response_total_expenses,
                group_by=group_by,
            ),
        )

    @staticmethod
    def _expense_text(*parts: Any) -> str:
        normalized: list[str] = []
        for part in parts:
            if isinstance(part, str) and part.strip():
                normalized.append(part.strip().lower())
        return " ".join(normalized)

    @classmethod
    def _logistics_bucket_label(cls, bucket: str) -> str:
        labels = {
            "delivery_to_client": "Доставка до клиента",
            "return_from_client": "Возврат от клиента",
            "cancellation_to_client": "Отмена в пути к клиенту",
            "cancellation_from_client": "Отмена обратной логистики",
            "seller_initiated_return": "Возврат по инициативе продавца",
            "defect_return": "Возврат по браку",
            "unknown": "Неопределенная логистика",
        }
        return labels.get(bucket, bucket)

    @classmethod
    def _logistics_bucket_expr(cls) -> Any:
        haystack = func.lower(
            func.concat_ws(
                " ",
                func.coalesce(MartExpenseDaily.logistics_type, ""),
                func.coalesce(MartExpenseDaily.seller_oper_name, ""),
                func.coalesce(MartExpenseDaily.bonus_type_name, ""),
                func.coalesce(MartExpenseDaily.source_field, ""),
            )
        )
        has_cancel = or_(haystack.like("%отмен%"), haystack.like("%cancel%"))
        has_return = or_(
            haystack.like("%возврат%"),
            haystack.like("%return%"),
            haystack.like("%обратн%"),
        )
        has_defect = or_(haystack.like("%брак%"), haystack.like("%defect%"))
        has_seller = or_(haystack.like("%продавц%"), haystack.like("%seller%"))
        has_from_client = or_(
            haystack.like("%от клиента%"),
            haystack.like("%from client%"),
            haystack.like("%обрат%"),
        )
        has_to_client = or_(
            haystack.like("%к клиент%"),
            haystack.like("%to client%"),
            haystack.like("%delivery%"),
            haystack.like("%доставк%"),
        )
        return case(
            (has_defect, "defect_return"),
            (and_(has_cancel, has_from_client), "cancellation_from_client"),
            (has_cancel, "cancellation_to_client"),
            (and_(has_return, has_seller), "seller_initiated_return"),
            (
                or_(
                    has_return,
                    MartExpenseDaily.logistics_type == "rebill_logistic_cost",
                ),
                "return_from_client",
            ),
            (
                or_(
                    has_to_client, MartExpenseDaily.logistics_type == "delivery_service"
                ),
                "delivery_to_client",
            ),
            else_="unknown",
        )

    @classmethod
    def _classify_logistics_bucket(
        cls,
        *,
        logistics_type: str | None,
        seller_oper_name: str | None,
        bonus_type_name: str | None,
        source_field: str | None,
        raw_payload: dict[str, Any] | None,
    ) -> str:
        payload = raw_payload or {}
        haystack = cls._expense_text(
            logistics_type,
            seller_oper_name,
            bonus_type_name,
            source_field,
            payload.get("sellerOperName"),
            payload.get("seller_oper_name"),
            payload.get("bonusTypeName"),
            payload.get("bonus_type_name"),
            payload.get("logisticsType"),
            payload.get("logistics_type"),
        )
        has_cancel = any(keyword in haystack for keyword in ("отмен", "cancel"))
        has_return = any(
            keyword in haystack for keyword in ("возврат", "return", "обратн")
        )
        has_defect = any(keyword in haystack for keyword in ("брак", "defect"))
        has_seller = any(keyword in haystack for keyword in ("продавц", "seller"))
        has_from_client = any(
            keyword in haystack for keyword in ("от клиента", "from client", "обрат")
        )
        has_to_client = any(
            keyword in haystack
            for keyword in ("к клиент", "to client", "delivery", "доставк")
        )
        if has_defect:
            return "defect_return"
        if has_cancel and has_from_client:
            return "cancellation_from_client"
        if has_cancel:
            return "cancellation_to_client"
        if has_return and has_seller:
            return "seller_initiated_return"
        if has_return or logistics_type == "rebill_logistic_cost":
            return "return_from_client"
        if has_to_client or logistics_type == "delivery_service":
            return "delivery_to_client"
        return "unknown"

    async def expense_logistics(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        include_unallocated: bool = True,
        top_n: int = 100,
    ) -> MoneyExpenseLogisticsRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        summary: MoneySummaryRead | None = None
        summary_total_expenses: Decimal | None = None
        summary_total_wb_expenses: Decimal | None = None
        summary_logistics_total: Decimal | None = None
        summary_logistics_share_base_kind: str | None = None
        summary_logistics_share_base_amount: Decimal | None = None
        if include_unallocated:
            summary = await self.summary(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            )
            if summary.profit_cascade is not None:
                cascade_totals = summary.profit_cascade.cascade.totals
                summary_total_wb_expenses = self._decimal(
                    cascade_totals.total_wb_expenses
                )
                summary_total_expenses = (
                    summary_total_wb_expenses
                    + self._decimal(cascade_totals.total_seller_expenses)
                    + self._decimal(cascade_totals.total_ad_expenses)
                )
                summary_logistics_total = self._decimal(cascade_totals.logistics_total)
            if summary.expense_breakdown is not None:
                summary_logistics_share_base_kind = (
                    summary.expense_breakdown.logistics_share_base_kind
                )
                summary_logistics_share_base_amount = self._decimal(
                    summary.expense_breakdown.logistics_share_base_amount
                )
        totals = await self._expense_totals(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            include_unallocated=include_unallocated,
        )
        response_total_expenses = (
            summary_total_expenses
            if summary_total_expenses is not None
            else self._decimal(totals["total_expenses"])
        )
        response_total_wb_expenses = (
            summary_total_wb_expenses
            if summary_total_wb_expenses is not None
            else self._decimal(totals["total_wb_expenses"])
        )
        response_logistics_total = (
            summary_logistics_total
            if summary_logistics_total is not None
            else self._decimal(totals["logistics_total"])
        )
        if (
            summary_logistics_share_base_kind is not None
            and summary_logistics_share_base_amount is not None
            and summary_logistics_share_base_amount > 0
        ):
            logistics_share_base_kind = summary_logistics_share_base_kind
            logistics_share_base_amount = summary_logistics_share_base_amount
        else:
            logistics_share_base_kind, logistics_share_base_amount = (
                self._logistics_share_base(
                    total_wb_expenses=response_total_wb_expenses,
                    total_expenses=response_total_expenses,
                )
            )

        finance_mode = str(totals.get("finance_mode", "row_level") or "row_level")
        rows: list[tuple[Any, ...]]
        by_category: dict[str, dict[str, Any]] = {}
        by_logistics_type: dict[str, dict[str, Any]] = {}
        by_bonus_type_name: dict[str, dict[str, Any]] = {}
        by_seller_oper_name: dict[str, dict[str, Any]] = {}
        by_sku: dict[str, dict[str, Any]] = {}
        by_nm: dict[str, dict[str, Any]] = {}
        by_day: dict[str, dict[str, Any]] = {}
        logistics_bucket_totals = {
            "delivery_to_client": Decimal("0"),
            "return_from_client": Decimal("0"),
            "cancellation_to_client": Decimal("0"),
            "cancellation_from_client": Decimal("0"),
            "seller_initiated_return": Decimal("0"),
            "defect_return": Decimal("0"),
            "unknown": Decimal("0"),
        }

        if finance_mode == "row_level":
            signed_amount = self._expense_signed_amount_expr()
            bucket_expr = self._logistics_bucket_expr().label("logistics_bucket")
            filters = self._expense_base_filters(
                account_id=account_id, date_from=actual_from, date_to=actual_to
            )
            filters.append(
                MartExpenseDaily.expense_category.in_(
                    [
                        EXPENSE_CATEGORY_WB_LOGISTICS,
                        EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
                    ]
                )
            )
            if not include_unallocated:
                filters.append(MartExpenseDaily.is_allocated_to_sku.is_(True))

            category_stmt = (
                select(
                    MartExpenseDaily.expense_category,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .where(*filters)
                .group_by(MartExpenseDaily.expense_category)
            )
            for category, amount, row_count in (
                await session.execute(category_stmt)
            ).all():
                category_key = str(category or "unknown")
                self._merge_expense_bucket(
                    by_category,
                    bucket_key=category_key,
                    amount=self._decimal(amount),
                    source="finance_report",
                    category=category_key,
                    label=self._expense_category_label(category_key),
                    row_count=int(row_count or 0),
                )

            logistics_type_stmt = (
                select(
                    bucket_expr,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .where(*filters)
                .group_by(bucket_expr)
            )
            for logistics_bucket, amount, row_count in (
                await session.execute(logistics_type_stmt)
            ).all():
                bucket_key = str(logistics_bucket or "unknown")
                decimal_amount = self._decimal(amount)
                logistics_bucket_totals[bucket_key] = (
                    logistics_bucket_totals.get(bucket_key, Decimal("0"))
                    + decimal_amount
                )
                self._merge_expense_bucket(
                    by_logistics_type,
                    bucket_key=bucket_key,
                    amount=decimal_amount,
                    source="finance_report",
                    label=self._logistics_bucket_label(bucket_key),
                    row_count=int(row_count or 0),
                )

            bonus_stmt = (
                select(
                    MartExpenseDaily.bonus_type_name,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .where(*filters)
                .group_by(MartExpenseDaily.bonus_type_name)
                .order_by(func.coalesce(func.sum(signed_amount), 0).desc())
                .limit(top_n)
            )
            for bonus_type_name, amount, row_count in (
                await session.execute(bonus_stmt)
            ).all():
                self._merge_expense_bucket(
                    by_bonus_type_name,
                    bucket_key=str(bonus_type_name or "unknown"),
                    amount=self._decimal(amount),
                    source="finance_report",
                    label=str(bonus_type_name or "unknown"),
                    row_count=int(row_count or 0),
                )

            seller_stmt = (
                select(
                    MartExpenseDaily.seller_oper_name,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .where(*filters)
                .group_by(MartExpenseDaily.seller_oper_name)
                .order_by(func.coalesce(func.sum(signed_amount), 0).desc())
                .limit(top_n)
            )
            for seller_oper_name, amount, row_count in (
                await session.execute(seller_stmt)
            ).all():
                self._merge_expense_bucket(
                    by_seller_oper_name,
                    bucket_key=str(seller_oper_name or "unknown"),
                    amount=self._decimal(amount),
                    source="finance_report",
                    label=str(seller_oper_name or "unknown"),
                    row_count=int(row_count or 0),
                )

            sku_stmt = (
                select(
                    MartExpenseDaily.sku_id,
                    MartExpenseDaily.nm_id,
                    CoreSKU.vendor_code,
                    MartExpenseDaily.barcode,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .select_from(MartExpenseDaily)
                .outerjoin(CoreSKU, CoreSKU.id == MartExpenseDaily.sku_id)
                .where(*filters)
                .group_by(
                    MartExpenseDaily.sku_id,
                    MartExpenseDaily.nm_id,
                    CoreSKU.vendor_code,
                    MartExpenseDaily.barcode,
                )
                .order_by(func.coalesce(func.sum(signed_amount), 0).desc())
            )
            for sku_id, nm_id, vendor_code, barcode, amount, row_count in (
                await session.execute(sku_stmt)
            ).all():
                bucket_key = (
                    f"sku:{sku_id}" if sku_id is not None else "sku:unallocated"
                )
                self._merge_expense_bucket(
                    by_sku,
                    bucket_key=bucket_key,
                    amount=self._decimal(amount),
                    source="finance_report",
                    sku_id=sku_id,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    barcode=barcode,
                    label="Не распределено по SKU"
                    if sku_id is None
                    else vendor_code or f"SKU {sku_id}",
                    row_count=int(row_count or 0),
                )

            nm_stmt = (
                select(
                    MartExpenseDaily.nm_id,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .where(*filters)
                .group_by(MartExpenseDaily.nm_id)
                .order_by(func.coalesce(func.sum(signed_amount), 0).desc())
                .limit(top_n)
            )
            for nm_id, amount, row_count in (await session.execute(nm_stmt)).all():
                bucket_key = f"nm:{nm_id}" if nm_id is not None else "nm:unallocated"
                self._merge_expense_bucket(
                    by_nm,
                    bucket_key=bucket_key,
                    amount=self._decimal(amount),
                    source="finance_report",
                    nm_id=nm_id,
                    label=str(nm_id)
                    if nm_id is not None
                    else "Не распределено по nmId",
                    row_count=int(row_count or 0),
                )

            day_stmt = (
                select(
                    MartExpenseDaily.stat_date,
                    func.coalesce(func.sum(signed_amount), 0),
                    func.count(),
                )
                .where(*filters)
                .group_by(MartExpenseDaily.stat_date)
                .order_by(MartExpenseDaily.stat_date.desc())
                .limit(top_n)
            )
            for stat_date, amount, row_count in (await session.execute(day_stmt)).all():
                self._merge_expense_bucket(
                    by_day,
                    bucket_key=str(stat_date),
                    amount=self._decimal(amount),
                    source="finance_report",
                    stat_date=stat_date,
                    row_count=int(row_count or 0),
                )
        elif finance_mode in {"account_level", "raw_finance"}:
            rows = []
            for entry in await self._raw_finance_expense_entries(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                categories={
                    EXPENSE_CATEGORY_WB_LOGISTICS,
                    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
                },
            ):
                rows.append(
                    (
                        entry.get("stat_date"),
                        entry.get("expense_category"),
                        entry.get("logistics_type"),
                        entry.get("seller_oper_name"),
                        entry.get("bonus_type_name"),
                        entry.get("source_field"),
                        entry.get("sku_id"),
                        entry.get("nm_id"),
                        entry.get("vendor_code"),
                        entry.get("barcode"),
                        MartService._entry_signed_amount(entry),
                        entry.get("raw_payload") or {},
                    )
                )
            for (
                stat_date,
                category,
                logistics_type,
                seller_oper_name,
                bonus_type_name,
                source_field,
                sku_id,
                nm_id,
                vendor_code,
                barcode,
                amount,
                raw_payload,
            ) in rows:
                decimal_amount = self._decimal(amount)
                category_key = str(category or "unknown")
                logistics_bucket = self._classify_logistics_bucket(
                    logistics_type=logistics_type,
                    seller_oper_name=seller_oper_name,
                    bonus_type_name=bonus_type_name,
                    source_field=source_field,
                    raw_payload=raw_payload,
                )
                logistics_bucket_totals[logistics_bucket] += decimal_amount
                self._merge_expense_bucket(
                    by_category,
                    bucket_key=category_key,
                    amount=decimal_amount,
                    source="finance_report",
                    category=category_key,
                    label=self._expense_category_label(category_key),
                    row_count=1,
                )
                self._merge_expense_bucket(
                    by_logistics_type,
                    bucket_key=logistics_bucket,
                    amount=decimal_amount,
                    source="finance_report",
                    label=self._logistics_bucket_label(logistics_bucket),
                    row_count=1,
                )
                self._merge_expense_bucket(
                    by_bonus_type_name,
                    bucket_key=str(bonus_type_name or "unknown"),
                    amount=decimal_amount,
                    source="finance_report",
                    label=str(bonus_type_name or "unknown"),
                    row_count=1,
                )
                self._merge_expense_bucket(
                    by_seller_oper_name,
                    bucket_key=str(seller_oper_name or "unknown"),
                    amount=decimal_amount,
                    source="finance_report",
                    label=str(seller_oper_name or "unknown"),
                    row_count=1,
                )
                sku_bucket_key = (
                    f"sku:{sku_id}" if sku_id is not None else "sku:unallocated"
                )
                self._merge_expense_bucket(
                    by_sku,
                    bucket_key=sku_bucket_key,
                    amount=decimal_amount,
                    source="finance_report",
                    sku_id=sku_id,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    barcode=barcode,
                    label="Не распределено по SKU"
                    if sku_id is None
                    else vendor_code or f"SKU {sku_id}",
                    row_count=1,
                )
                nm_bucket_key = f"nm:{nm_id}" if nm_id is not None else "nm:unallocated"
                self._merge_expense_bucket(
                    by_nm,
                    bucket_key=nm_bucket_key,
                    amount=decimal_amount,
                    source="finance_report",
                    nm_id=nm_id,
                    label=str(nm_id)
                    if nm_id is not None
                    else "Не распределено по nmId",
                    row_count=1,
                )
                self._merge_expense_bucket(
                    by_day,
                    bucket_key=str(stat_date),
                    amount=decimal_amount,
                    source="finance_report",
                    stat_date=stat_date,
                    row_count=1,
                )
        else:
            raise HTTPException(
                status_code=400, detail="Unsupported finance_mode value"
            )

        total_logistics = sum(
            (self._decimal(amount) for amount in logistics_bucket_totals.values()),
            start=Decimal("0"),
        )
        response_total_logistics = (
            response_logistics_total
            if response_logistics_total > 0
            else total_logistics
        )
        by_bonus_items = self._trim_expense_items(
            self._expense_breakdown_items_from_buckets(
                buckets=by_bonus_type_name,
                total_expenses=response_total_logistics,
                group_by="source",
            ),
            top_n=top_n,
        )
        by_seller_items = self._trim_expense_items(
            self._expense_breakdown_items_from_buckets(
                buckets=by_seller_oper_name,
                total_expenses=response_total_logistics,
                group_by="source",
            ),
            top_n=top_n,
        )
        by_sku_items = self._trim_expense_items(
            self._expense_breakdown_items_from_buckets(
                buckets=by_sku,
                total_expenses=response_total_logistics,
                group_by="sku",
            ),
            top_n=top_n,
        )
        by_nm_items = self._trim_expense_items(
            self._expense_breakdown_items_from_buckets(
                buckets=by_nm,
                total_expenses=response_total_logistics,
                group_by="nm",
            ),
            top_n=top_n,
        )
        by_day_items = self._trim_expense_items(
            self._expense_breakdown_items_from_buckets(
                buckets=by_day,
                total_expenses=response_total_logistics,
                group_by="day",
            ),
            top_n=top_n,
        )

        return MoneyExpenseLogisticsRead(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            include_unallocated=include_unallocated,
            total_logistics=self._float0(response_total_logistics),
            total_wb_logistics=self._float0(
                sum(
                    (
                        self._decimal(payload.get("amount"))
                        for key, payload in by_category.items()
                        if key == EXPENSE_CATEGORY_WB_LOGISTICS
                    ),
                    start=Decimal("0"),
                )
            ),
            total_wb_logistics_rebill=self._float0(
                sum(
                    (
                        self._decimal(payload.get("amount"))
                        for key, payload in by_category.items()
                        if key == EXPENSE_CATEGORY_WB_LOGISTICS_REBILL
                    ),
                    start=Decimal("0"),
                )
            ),
            logistics_share_base_kind=logistics_share_base_kind,
            logistics_share_base_amount=self._float0(logistics_share_base_amount),
            logistics_share_percent=self._percent0(
                response_total_logistics, logistics_share_base_amount
            )
            if logistics_share_base_amount > 0
            else 0.0,
            delivery_to_client=self._float0(
                logistics_bucket_totals["delivery_to_client"]
            ),
            return_from_client=self._float0(
                logistics_bucket_totals["return_from_client"]
            ),
            cancellation_to_client=self._float0(
                logistics_bucket_totals["cancellation_to_client"]
            ),
            cancellation_from_client=self._float0(
                logistics_bucket_totals["cancellation_from_client"]
            ),
            seller_initiated_return=self._float0(
                logistics_bucket_totals["seller_initiated_return"]
            ),
            defect_return=self._float0(logistics_bucket_totals["defect_return"]),
            unknown=self._float0(logistics_bucket_totals["unknown"]),
            by_category=self._expense_breakdown_items_from_buckets(
                buckets=by_category,
                total_expenses=response_total_logistics,
                group_by="category",
            ),
            by_logistics_type=self._expense_breakdown_items_from_buckets(
                buckets=by_logistics_type,
                total_expenses=response_total_logistics,
                group_by="category",
            ),
            by_bonus_type_name=by_bonus_items,
            by_seller_oper_name=by_seller_items,
            by_sku=by_sku_items,
            by_nm=by_nm_items,
            by_day=by_day_items,
        )

    async def expense_report_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        category: str | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        amount_min: float | None = None,
        amount_max: float | None = None,
        amount_exact: float | None = None,
        search: str | None = None,
        source_field: str | None = None,
        seller_oper_name: str | None = None,
        allocated: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ExpenseReportRowRead]:
        actual_from, actual_to = self._date_range(date_from, date_to)
        signed_amount = self._expense_signed_amount_expr()
        amount_abs = func.abs(signed_amount)
        amount_exact_decimal = (
            self._decimal(amount_exact) if amount_exact is not None else None
        )
        amount_min_decimal = (
            self._decimal(amount_min) if amount_min is not None else None
        )
        amount_max_decimal = (
            self._decimal(amount_max) if amount_max is not None else None
        )
        normalized_search = (search or "").strip().lower()
        data_version_hash = await self._expense_report_rows_version_hash(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        cache_key = (
            account_id,
            actual_from,
            actual_to,
            category or "",
            sku_id,
            nm_id,
            str(amount_min_decimal) if amount_min_decimal is not None else "",
            str(amount_max_decimal) if amount_max_decimal is not None else "",
            str(amount_exact_decimal) if amount_exact_decimal is not None else "",
            normalized_search,
            source_field or "",
            seller_oper_name or "",
            allocated,
            limit,
            offset,
            data_version_hash,
        )
        cached_page = self._expense_report_rows_cache.get(cache_key)
        if cached_page is not None:
            cached_at, page = cached_page
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.EXPENSE_REPORT_ROWS_CACHE_TTL_SECONDS
            ):
                return self._with_page_cache_meta(
                    page,
                    computed_at=cached_at,
                    cache_status="hit",
                    data_version_hash=data_version_hash,
                )
        filters = self._expense_base_filters(
            account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        if category is not None:
            filters.append(MartExpenseDaily.expense_category == category)
        if sku_id is not None:
            filters.append(MartExpenseDaily.sku_id == sku_id)
        if nm_id is not None:
            filters.append(MartExpenseDaily.nm_id == nm_id)
        if source_field:
            filters.append(MartExpenseDaily.source_field == source_field)
        if seller_oper_name:
            filters.append(
                MartExpenseDaily.seller_oper_name.ilike(f"%{seller_oper_name}%")
            )
        if allocated is not None:
            filters.append(MartExpenseDaily.is_allocated_to_sku.is_(allocated))
        if amount_exact_decimal is not None:
            lower = max(
                Decimal("0"), amount_exact_decimal.copy_abs() - Decimal("0.005")
            )
            upper = amount_exact_decimal.copy_abs() + Decimal("0.005")
            filters.append(amount_abs.between(lower, upper))
        else:
            if amount_min_decimal is not None:
                filters.append(amount_abs >= amount_min_decimal.copy_abs())
            if amount_max_decimal is not None:
                filters.append(amount_abs <= amount_max_decimal.copy_abs())
        if normalized_search:
            pattern = f"%{normalized_search}%"
            filters.append(
                or_(
                    CoreSKU.vendor_code.ilike(pattern),
                    MartExpenseDaily.barcode.ilike(pattern),
                    MartExpenseDaily.srid.ilike(pattern),
                    cast(MartExpenseDaily.order_id, String).ilike(pattern),
                    cast(MartExpenseDaily.rrd_id, String).ilike(pattern),
                    MartExpenseDaily.seller_oper_name.ilike(pattern),
                    MartExpenseDaily.bonus_type_name.ilike(pattern),
                    MartExpenseDaily.source_field.ilike(pattern),
                )
            )
        total_stmt = (
            select(func.count())
            .select_from(MartExpenseDaily)
            .outerjoin(CoreSKU, CoreSKU.id == MartExpenseDaily.sku_id)
            .where(*filters)
        )
        total = int((await session.execute(total_stmt)).scalar_one() or 0)
        if total == 0:
            fallback_items: list[ExpenseReportRowRead] = []
            category_filter = {category} if category is not None else None
            for entry in await self._raw_finance_expense_entries(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                categories=category_filter,
                sku_id=sku_id,
                nm_id=nm_id,
            ):
                entry_amount = self._decimal(MartService._entry_signed_amount(entry))
                if not self._expense_report_entry_matches_filters(
                    entry,
                    amount=entry_amount,
                    amount_min=amount_min_decimal,
                    amount_max=amount_max_decimal,
                    amount_exact=amount_exact_decimal,
                    search=normalized_search,
                    source_field=source_field,
                    seller_oper_name=seller_oper_name,
                    allocated=allocated,
                ):
                    continue
                entry_category = str(entry.get("expense_category") or "")
                fallback_items.append(
                    ExpenseReportRowRead(
                        report_id=entry.get("report_id"),
                        rrd_id=entry.get("rrd_id"),
                        date=entry.get("stat_date"),
                        nm_id=entry.get("nm_id"),
                        sku_id=entry.get("sku_id"),
                        vendor_code=entry.get("vendor_code"),
                        barcode=entry.get("barcode"),
                        category=entry_category,
                        category_label=self._expense_category_label(entry_category),
                        amount=self._float0(entry_amount),
                        source=str(entry.get("expense_source") or "finance_report"),
                        source_field=entry.get("source_field"),
                        seller_oper_name=entry.get("seller_oper_name"),
                        bonus_type_name=entry.get("bonus_type_name"),
                        logistics_type=entry.get("logistics_type"),
                        srid=entry.get("srid"),
                        order_id=entry.get("order_id"),
                        is_allocated_to_sku=bool(entry.get("sku_id") is not None),
                    )
                )
            fallback_items.sort(
                key=lambda item: (item.date, item.rrd_id or 0), reverse=True
            )
            paged_items = fallback_items[offset : offset + limit]
            computed_at = utcnow()
            result = self._with_page_cache_meta(
                Page[ExpenseReportRowRead](
                    total=len(fallback_items),
                    limit=limit,
                    offset=offset,
                    items=paged_items,
                ),
                computed_at=computed_at,
                cache_status="miss",
                data_version_hash=data_version_hash,
            )
            self._expense_report_rows_cache[cache_key] = (
                computed_at,
                result.model_copy(deep=True),
            )
            return result
        rows_stmt = (
            select(
                MartExpenseDaily.report_id,
                MartExpenseDaily.rrd_id,
                MartExpenseDaily.stat_date,
                MartExpenseDaily.nm_id,
                MartExpenseDaily.sku_id,
                CoreSKU.vendor_code,
                MartExpenseDaily.barcode,
                MartExpenseDaily.expense_category,
                signed_amount,
                MartExpenseDaily.expense_source,
                MartExpenseDaily.source_field,
                MartExpenseDaily.seller_oper_name,
                MartExpenseDaily.bonus_type_name,
                MartExpenseDaily.logistics_type,
                MartExpenseDaily.srid,
                MartExpenseDaily.order_id,
                MartExpenseDaily.is_allocated_to_sku,
            )
            .select_from(MartExpenseDaily)
            .outerjoin(CoreSKU, CoreSKU.id == MartExpenseDaily.sku_id)
            .where(*filters)
            .order_by(MartExpenseDaily.stat_date.desc(), MartExpenseDaily.id.desc())
            .limit(limit)
            .offset(offset)
        )
        items = [
            ExpenseReportRowRead(
                report_id=report_id,
                rrd_id=rrd_id,
                date=stat_date,
                nm_id=row_nm_id,
                sku_id=row_sku_id,
                vendor_code=vendor_code,
                barcode=barcode,
                category=str(expense_category),
                category_label=self._expense_category_label(str(expense_category)),
                amount=self._float0(amount),
                source=str(expense_source or ""),
                source_field=source_field,
                seller_oper_name=seller_oper_name,
                bonus_type_name=bonus_type_name,
                logistics_type=logistics_type,
                srid=srid,
                order_id=order_id,
                is_allocated_to_sku=bool(is_allocated_to_sku),
            )
            for (
                report_id,
                rrd_id,
                stat_date,
                row_nm_id,
                row_sku_id,
                vendor_code,
                barcode,
                expense_category,
                amount,
                expense_source,
                source_field,
                seller_oper_name,
                bonus_type_name,
                logistics_type,
                srid,
                order_id,
                is_allocated_to_sku,
            ) in (await session.execute(rows_stmt)).all()
        ]
        computed_at = utcnow()
        result = self._with_page_cache_meta(
            Page[ExpenseReportRowRead](
                total=total,
                limit=limit,
                offset=offset,
                items=items,
            ),
            computed_at=computed_at,
            cache_status="miss",
            data_version_hash=data_version_hash,
        )
        self._expense_report_rows_cache[cache_key] = (
            computed_at,
            result.model_copy(deep=True),
        )
        return result

    def _expense_report_entry_matches_filters(
        self,
        entry: dict[str, Any],
        *,
        amount: Decimal,
        amount_min: Decimal | None,
        amount_max: Decimal | None,
        amount_exact: Decimal | None,
        search: str,
        source_field: str | None,
        seller_oper_name: str | None,
        allocated: bool | None,
    ) -> bool:
        amount_abs = amount.copy_abs()
        if amount_exact is not None:
            lower = max(Decimal("0"), amount_exact.copy_abs() - Decimal("0.005"))
            upper = amount_exact.copy_abs() + Decimal("0.005")
            if not (lower <= amount_abs <= upper):
                return False
        else:
            if amount_min is not None and amount_abs < amount_min.copy_abs():
                return False
            if amount_max is not None and amount_abs > amount_max.copy_abs():
                return False
        if source_field and str(entry.get("source_field") or "") != source_field:
            return False
        if seller_oper_name:
            haystack = str(entry.get("seller_oper_name") or "").lower()
            if seller_oper_name.lower() not in haystack:
                return False
        if allocated is not None:
            entry_allocated = entry.get("sku_id") is not None
            if entry_allocated is not allocated:
                return False
        if search:
            haystack = " ".join(
                str(entry.get(key) or "")
                for key in (
                    "vendor_code",
                    "barcode",
                    "srid",
                    "order_id",
                    "rrd_id",
                    "seller_oper_name",
                    "bonus_type_name",
                    "source_field",
                )
            ).lower()
            if search not in haystack:
                return False
        return True

    def _filter_money_cards(
        self,
        rows: list[Any],
        *,
        search: str | None,
        status: str | None,
        next_action: str | None,
        trust_state: str | None,
        subject_name: str | None,
        brand: str | None,
        state: MoneyRuntimeState,
    ) -> list[Any]:
        filtered = list(rows)
        if search:
            pattern = search.strip().lower()
            filtered = [
                row
                for row in filtered
                if pattern in str(row.nm_id or "").lower()
                or pattern in str(row.vendor_code or "").lower()
                or pattern in str(row.barcode or "").lower()
                or pattern in str(row.title or "").lower()
                or pattern in str(row.brand or "").lower()
            ]
        if trust_state:
            filtered = [
                row
                for row in filtered
                if self._data_trust_for_row(row).trust_state == trust_state
            ]
        if subject_name:
            pattern = subject_name.strip().lower()
            filtered = [
                row
                for row in filtered
                if pattern in str(row.subject_name or "").lower()
            ]
        if brand:
            pattern = brand.strip().lower()
            filtered = [
                row for row in filtered if pattern in str(row.brand or "").lower()
            ]
        if status:
            status_map = {
                "profitable": lambda r, p: (
                    r.trust_state != TRUST_STATE_DATA_BLOCKED
                    and (r.net_profit or 0) > 0
                ),
                "loss": lambda r, p: r.net_profit is not None and r.net_profit < 0,
                "data_blocked": lambda r, p: r.trust_state == TRUST_STATE_DATA_BLOCKED,
                "stock_risk": lambda r, p: r.sku_status == "PROTECT_STOCK",
                "overstock": lambda r, p: r.sku_status == "LIQUIDATE",
                "ad_risk": lambda r, p: (
                    r.ad_spend > 0 and r.net_profit is not None and r.net_profit <= 0
                ),
                "price_risk": lambda r, p: (
                    p is not None
                    and p.safe_price_gap is not None
                    and p.safe_price_gap < 0
                ),
            }
            predicate = status_map.get(status)
            if predicate is not None:
                filtered = [
                    row
                    for row in filtered
                    if predicate(
                        row,
                        state.price_rows.get(int(row.sku_id))
                        if row.sku_id is not None
                        else None,
                    )
                ]
        if next_action:
            filtered = [
                row
                for row in filtered
                if (
                    any(
                        action.action_type == next_action
                        for action in self._actions_for_sku(
                            state, int(row.sku_id) if row.sku_id is not None else None
                        )
                    )
                    or (
                        (
                            action := self._synthesized_row_action(
                                row,
                                price_row=state.price_rows.get(int(row.sku_id))
                                if row.sku_id is not None
                                else None,
                                purchase_row=state.purchase_rows.get(int(row.sku_id))
                                if row.sku_id is not None
                                else None,
                            )
                        )
                        is not None
                        and action.action_type == next_action
                    )
                )
            ]
        return filtered

    async def cards(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        status: str | None = None,
        next_action: str | None = None,
        trust_state: str | None = None,
        subject_name: str | None = None,
        brand: str | None = None,
        sort_by: str = "priority_score",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MoneyCardPage:
        actual_from, actual_to = self._date_range(date_from, date_to)
        state = await self._load_runtime_state(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        total_revenue_all = sum(
            (self._decimal(item.realized_revenue) for item in state.profit_rows),
            start=Decimal("0"),
        )
        profit_by_sku = {
            int(row.sku_id): row for row in state.profit_rows if row.sku_id is not None
        }
        article_rows_by_nm: dict[int, list[tuple[Any, Any, Any | None]]] = {}
        for control_row in state.control_rows:
            if control_row.sku_id is None or control_row.nm_id is None:
                continue
            profit_row = profit_by_sku.get(int(control_row.sku_id))
            if profit_row is None:
                continue
            article_rows_by_nm.setdefault(int(control_row.nm_id), []).append(
                (
                    control_row,
                    profit_row,
                    state.purchase_rows.get(int(control_row.sku_id)),
                )
            )
        filtered = self._filter_money_cards(
            state.control_rows,
            search=search,
            status=status,
            next_action=next_action,
            trust_state=trust_state,
            subject_name=subject_name,
            brand=brand,
            state=state,
        )
        reverse = sort_dir != "asc"
        sort_attr = {
            "priority_score": "priority_score",
            "revenue": "revenue",
            "profit": "net_profit",
            "margin": "margin_percent",
            "stock_value": "stock_value",
            "days_of_stock": "days_of_stock",
            "ad_spend": "ad_spend",
            "drr": "drr_percent",
        }.get(sort_by, "priority_score")
        filtered.sort(
            key=lambda row: (
                getattr(row, sort_attr)
                if getattr(row, sort_attr) is not None
                else float("-inf")
            ),
            reverse=reverse,
        )
        items: list[MoneyCardRow] = []
        for row in filtered[offset : offset + limit]:
            if row.sku_id is None:
                continue
            profit_row = profit_by_sku.get(int(row.sku_id))
            if profit_row is None:
                continue
            price_row = state.price_rows.get(int(row.sku_id))
            purchase_row = state.purchase_rows.get(int(row.sku_id))
            article_rows = (
                article_rows_by_nm.get(int(row.nm_id), [])
                if row.nm_id is not None
                else []
            )
            article_source_spend = (
                state.ads_source_by_nm.get(int(row.nm_id), Decimal("0"))
                if row.nm_id is not None
                else Decimal("0")
            )
            row_source_allocations = self._article_ads_allocation_by_sku(
                article_rows=article_rows, ads_source_spend=article_source_spend
            )
            ads_source_spend = row_source_allocations.get(
                int(row.sku_id), self._decimal(getattr(row, "ad_spend", None))
            )
            allocated_overhead = self._allocated_overhead(
                revenue=self._decimal(getattr(profit_row, "realized_revenue", None)),
                total_revenue=total_revenue_all,
                account_level_expense_total=state.account_level_expense_total,
            )
            next_row_action = self._primary_row_action(
                state, row, price_row=price_row, purchase_row=purchase_row
            )
            row_money = self._build_card_money(
                profit_row,
                row,
                price_row=price_row,
                purchase_row=purchase_row,
                ads_source_spend=ads_source_spend,
                account_level_expense_total=state.account_level_expense_total,
                account_level_logistics_total=getattr(
                    state, "account_level_logistics_total", Decimal("0")
                ),
                allocated_overhead=allocated_overhead,
            )
            row_profit_variants = self._profit_variants(
                profit_before_ads=self._decimal(row_money.profit.before_ads),
                ads_allocated_spend=self._decimal(row_money.ads.allocated_spend),
                ads_source_spend=self._decimal(row_money.ads.source_spend),
                allocated_overhead=allocated_overhead,
            )
            row_expense_breakdown = self._article_expense_breakdown(
                row_money.wb_expenses
            )
            row_finality = self._finality_for_row(
                row,
                price_row=price_row,
                ads_unallocated=self._decimal(row_money.ads.unallocated_spend),
                ads_overallocated=self._decimal(row_money.ads.overallocated_spend),
                finance_ready="finance_not_confirmed"
                not in list(row.blocked_reasons or []),
                supplier_confirmed=self._profit_row_cost_final_accepted(profit_row),
                expense_mapping_final=not row_expense_breakdown.unallocated_warning,
            )
            items.append(
                MoneyCardRow(
                    sku_id=row.sku_id,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    barcode=row.barcode,
                    title=row.title,
                    brand=row.brand,
                    subject_name=row.subject_name,
                    business_verdict=self._build_card_verdict(row, price_row),
                    money=row_money,
                    operations=CardOperationsBlock(
                        orders_count=0,
                        cancelled_orders_count=0,
                        cancel_rate_percent=0.0,
                        sales_count=self._int0(profit_row.gross_units),
                        returns_count=self._int0(profit_row.return_units),
                        return_rate_percent=self._percent0(
                            profit_row.return_units, profit_row.gross_units
                        ),
                        net_units=self._int0(profit_row.net_units),
                        issue="Финансы по карточке еще не подтверждены"
                        if profit_row.finance_rows <= 0
                        else "",
                    ),
                    stock=self._build_card_stock(row, profit_row, purchase_row),
                    price=self._build_card_price(
                        price_row, profit_row=profit_row, settings=state.settings
                    ),
                    ads=row_money.ads,
                    profit_variants=row_profit_variants,
                    finality=row_finality,
                    article_summary_preview=self._article_summary_preview(
                        nm_id=int(row.nm_id) if row.nm_id is not None else None,
                        title=row.title,
                        article_rows=article_rows,
                        ads_source_spend=article_source_spend,
                    ),
                    data_trust=self._data_trust_for_row(row),
                    next_action=next_row_action,
                    priority_score=self._float0(row.priority_score),
                )
            )
        summary = MoneyCardListSummary(
            profitable_count=sum(
                1
                for row in filtered
                if row.trust_state != TRUST_STATE_DATA_BLOCKED
                and (row.net_profit or 0) > 0
            ),
            loss_count=sum(
                1
                for row in filtered
                if row.net_profit is not None and row.net_profit < 0
            ),
            data_blocked_count=sum(
                1 for row in filtered if row.trust_state == TRUST_STATE_DATA_BLOCKED
            ),
            stock_risk_count=sum(
                1 for row in filtered if row.sku_status == "PROTECT_STOCK"
            ),
            overstock_count=sum(1 for row in filtered if row.sku_status == "LIQUIDATE"),
            ad_risk_count=sum(
                1
                for row in filtered
                if row.ad_spend > 0
                and row.net_profit is not None
                and row.net_profit <= 0
            ),
            price_risk_count=sum(
                1
                for row in filtered
                if (
                    state.price_rows.get(int(row.sku_id)).safe_price_gap
                    if row.sku_id is not None
                    and state.price_rows.get(int(row.sku_id)) is not None
                    else None
                )
                is not None
                and state.price_rows[int(row.sku_id)].safe_price_gap < 0
            ),
        )
        return MoneyCardPage(
            **self._response_cache_fields(state),
            total=len(filtered),
            limit=limit,
            offset=offset,
            summary=summary,
            items=items,
        )

    async def articles(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        status: str | None = None,
        trust_state: str | None = None,
        subject_name: str | None = None,
        brand: str | None = None,
        sort_by: str = "priority_score",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MoneyArticlePage:
        actual_from, actual_to = self._date_range(date_from, date_to)
        state = await self._load_runtime_state(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        total_revenue_all = sum(
            (self._decimal(item.realized_revenue) for item in state.profit_rows),
            start=Decimal("0"),
        )
        profit_by_sku = {
            int(row.sku_id): row for row in state.profit_rows if row.sku_id is not None
        }
        filtered = self._filter_money_cards(
            state.control_rows,
            search=search,
            status=status,
            next_action=None,
            trust_state=trust_state,
            subject_name=subject_name,
            brand=brand,
            state=state,
        )
        grouped: dict[int, list[tuple[Any, Any, Any | None]]] = {}
        for row in filtered:
            if row.sku_id is None or row.nm_id is None:
                continue
            profit_row = profit_by_sku.get(int(row.sku_id))
            if profit_row is None:
                continue
            grouped.setdefault(int(row.nm_id), []).append(
                (row, profit_row, state.purchase_rows.get(int(row.sku_id)))
            )
        items: list[MoneyArticleRow] = []
        article_profit_rows: list[Any] = []
        for nm_id, article_rows in grouped.items():
            context = self._aggregate_article_context(
                article_rows=article_rows,
                ads_source_spend=state.ads_source_by_nm.get(nm_id, Decimal("0")),
            )
            row = context["row"]
            profit_row = context["profit_row"]
            article_profit_rows.extend(
                item[1] for item in article_rows if item[1] is not None
            )
            price_row = (
                state.price_rows.get(int(context["primary_row"].sku_id))
                if context["primary_row"].sku_id is not None
                else None
            )
            purchase_row = context["purchase_row"]
            ads_source_spend = state.ads_source_by_nm.get(nm_id, Decimal("0"))
            allocated_overhead = self._allocated_overhead(
                revenue=self._decimal(getattr(profit_row, "realized_revenue", None)),
                total_revenue=total_revenue_all,
                account_level_expense_total=state.account_level_expense_total,
            )
            next_action = self._primary_row_action(
                state,
                context["primary_row"],
                price_row=price_row,
                purchase_row=purchase_row,
            )
            article_money = self._build_card_money(
                profit_row,
                row,
                price_row=price_row,
                purchase_row=purchase_row,
                ads_source_spend=ads_source_spend,
                account_level_expense_total=state.account_level_expense_total,
                account_level_logistics_total=getattr(
                    state, "account_level_logistics_total", Decimal("0")
                ),
                allocated_overhead=allocated_overhead,
            )
            article_expense_breakdown = self._article_expense_breakdown(
                article_money.wb_expenses
            )
            article_stock = self._build_card_stock(row, profit_row, purchase_row)
            article_finality = self._finality_for_row(
                row,
                price_row=price_row,
                ads_unallocated=self._decimal(article_money.ads.unallocated_spend),
                ads_overallocated=self._decimal(article_money.ads.overallocated_spend),
                finance_ready="finance_not_confirmed"
                not in list(row.blocked_reasons or []),
                supplier_confirmed=self._profit_row_cost_final_accepted(profit_row),
                expense_mapping_final=not article_expense_breakdown.unallocated_warning,
            )
            verdict = self._build_card_verdict(row, price_row)
            article_trust = self._article_trust_block(
                row=row,
                profit_row=profit_row,
                finality=article_finality,
                reconciliation_status="matched"
                if "finance_not_confirmed" not in list(row.blocked_reasons or [])
                else "warning_mismatch",
            )
            article_answer = self._article_money_answer(
                verdict=verdict,
                finality=article_finality,
                trust=article_trust,
                stock=article_stock,
                purchase_plan=None,
                top_action=next_action,
                profit_after_source_ads=article_money.profit.after_source_ads,
            )
            items.append(
                MoneyArticleRow(
                    nm_id=nm_id,
                    title=row.title,
                    brand=row.brand,
                    subject_name=row.subject_name,
                    identity=MoneyArticleIdentity(
                        nm_id=nm_id,
                        title=row.title,
                        brand=row.brand,
                        subject_name=row.subject_name,
                    ),
                    trust=article_trust,
                    variant_count=len(article_rows),
                    business_verdict=verdict,
                    money_answer=article_answer,
                    money=article_money,
                    stock=article_stock,
                    ads=article_money.ads,
                    profit_variants=self._profit_variants(
                        profit_before_ads=self._decimal(
                            article_money.profit.before_ads
                        ),
                        ads_allocated_spend=self._decimal(
                            article_money.ads.allocated_spend
                        ),
                        ads_source_spend=self._decimal(article_money.ads.source_spend),
                        allocated_overhead=allocated_overhead,
                    ),
                    finality=article_finality,
                    financial_final=article_finality.profit_final,
                    data_trust=self._data_trust_for_row(row),
                    next_action=next_action,
                    priority_score=self._float0(row.priority_score),
                )
            )
        reverse = sort_dir != "asc"
        if sort_by == "revenue":
            items.sort(key=lambda item: item.money.revenue, reverse=reverse)
        elif sort_by == "profit":
            items.sort(
                key=lambda item: item.money.profit.after_source_ads, reverse=reverse
            )
        else:
            items.sort(key=lambda item: item.priority_score, reverse=reverse)
        paged = items[offset : offset + limit]
        economic_profitable_count = sum(
            1 for item in items if item.money.profit.after_source_ads > 0
        )
        economic_loss_count = sum(
            1 for item in items if item.money.profit.after_source_ads < 0
        )
        final_profitable_count = sum(
            1
            for item in items
            if item.money.profit.after_source_ads > 0 and item.finality.profit_final
        )
        final_loss_count = sum(
            1
            for item in items
            if item.money.profit.after_source_ads < 0 and item.finality.profit_final
        )
        summary = MoneyArticleListSummary(
            profitable_count=economic_profitable_count,
            loss_count=economic_loss_count,
            economic_profitable_count=economic_profitable_count,
            economic_loss_count=economic_loss_count,
            final_profitable_count=final_profitable_count,
            final_loss_count=final_loss_count,
            data_blocked_count=sum(
                1 for item in items if item.data_trust.state == TRUST_STATE_BLOCKED
            ),
            stock_risk_count=sum(
                1 for item in items if item.business_verdict.status == "stock_risk"
            ),
            overstock_count=sum(
                1 for item in items if item.business_verdict.status == "overstock"
            ),
            provisional_count=sum(
                1
                for item in items
                if not item.finality.profit_final
                and item.data_trust.state != TRUST_STATE_BLOCKED
            ),
            cost_coverage=self._cost_coverage_from_profit_rows(
                article_profit_rows,
                cost_trust_policy=str(
                    state.settings.get("cost_trust_policy") or "operator_baseline"
                ),
            ),
        )
        return MoneyArticlePage(
            **self._response_cache_fields(state),
            total=len(items),
            limit=limit,
            offset=offset,
            summary=summary,
            items=paged,
        )

    async def article_detail(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        include_audit: bool = True,
    ) -> MoneyArticleDetailRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        state = await self._load_runtime_state(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        total_revenue_all = sum(
            (self._decimal(item.realized_revenue) for item in state.profit_rows),
            start=Decimal("0"),
        )
        profit_by_sku = {
            int(row.sku_id): row for row in state.profit_rows if row.sku_id is not None
        }
        article_rows = [
            (
                row,
                profit_by_sku.get(int(row.sku_id)),
                state.purchase_rows.get(int(row.sku_id)),
            )
            for row in state.control_rows
            if row.sku_id is not None
            and row.nm_id == nm_id
            and profit_by_sku.get(int(row.sku_id)) is not None
        ]
        if not article_rows:
            raise HTTPException(
                status_code=404, detail="Денежная карточка по артикулу не найдена"
            )
        context = self._aggregate_article_context(
            article_rows=article_rows,
            ads_source_spend=state.ads_source_by_nm.get(nm_id, Decimal("0")),
        )
        row = context["row"]
        profit_row = context["profit_row"]
        price_row = (
            state.price_rows.get(int(context["primary_row"].sku_id))
            if context["primary_row"].sku_id is not None
            else None
        )
        purchase_row = context["purchase_row"]
        if include_audit:
            audit = await self.dashboard.article_audit(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=actual_from,
                date_to=actual_to,
            )
        else:
            audit = self._fast_article_audit_preview(
                account_id=account_id,
                nm_id=nm_id,
                row=row,
                profit_row=profit_row,
                actual_from=actual_from,
                actual_to=actual_to,
            )
        next_actions = [
            self._primary_row_action(
                state,
                item[0],
                price_row=state.price_rows.get(int(item[0].sku_id))
                if item[0].sku_id is not None
                else None,
                purchase_row=item[2],
            )
            for item in article_rows
        ]
        deduped_actions: list[NextActionRead] = []
        seen: set[tuple[str, int]] = set()
        for action in sorted(
            next_actions,
            key=lambda item: (
                self._priority_rank(item.priority),
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        ):
            key = (
                action.action_type,
                int(
                    action.linked_entity.get("nm_id")
                    or action.linked_entity.get("sku_id")
                    or 0
                ),
            )
            if key in seen:
                continue
            seen.add(key)
            deduped_actions.append(action)
        top_action = (
            deduped_actions[0] if deduped_actions else self._default_row_action(row)
        )
        allocated_overhead = self._allocated_overhead(
            revenue=self._decimal(getattr(profit_row, "realized_revenue", None)),
            total_revenue=total_revenue_all,
            account_level_expense_total=state.account_level_expense_total,
        )
        article_money = self._build_card_money(
            profit_row,
            row,
            price_row=price_row,
            purchase_row=purchase_row,
            ads_source_spend=state.ads_source_by_nm.get(nm_id, Decimal("0")),
            account_level_expense_total=state.account_level_expense_total,
            account_level_logistics_total=getattr(
                state, "account_level_logistics_total", Decimal("0")
            ),
            allocated_overhead=allocated_overhead,
        )
        article_money = article_money.model_copy(
            update={
                "ads": self._ads_block_with_metrics(
                    article_money.ads,
                    stats_rows_count=self._int0(
                        getattr(audit.ads, "stats_rows_count", 0)
                    ),
                    views=self._int0(getattr(audit.ads, "views", 0)),
                    clicks=self._int0(getattr(audit.ads, "clicks", 0)),
                    orders=self._int0(getattr(audit.ads, "orders", 0)),
                    atbs=self._int0(getattr(audit.ads, "atbs", 0)),
                )
            }
        )
        article_expense_breakdown = self._article_expense_breakdown(
            article_money.wb_expenses
        )
        article_stock = self._build_card_stock(row, profit_row, purchase_row)
        article_price = self._build_card_price(
            price_row, profit_row=profit_row, settings=state.settings
        )
        decision = (
            "fix_data_first" if row.trust_state == TRUST_STATE_DATA_BLOCKED else "watch"
        )
        article_problems: list[CardProblem] = []
        cancel_rate = self._percent(
            audit.operations.cancelled_orders_count, audit.operations.orders_count
        )
        return_rate = self._percent(
            audit.operations.returns_count, audit.operations.sales_count
        )
        if cancel_rate is not None and cancel_rate >= 50:
            article_problems.append(
                CardProblem(
                    code="high_cancel_rate",
                    severity="warning",
                    title="Высокая доля отмен по карточке",
                    business_impact="Спрос и фактическая конверсия карточки искажаются.",
                    fix_hint="Проверьте причины отмен, контент и размерную сетку.",
                )
            )
        if return_rate is not None and return_rate >= 20:
            article_problems.append(
                CardProblem(
                    code="high_return_rate",
                    severity="warning",
                    title="Высокая доля возвратов по карточке",
                    business_impact="Прибыль и оборачиваемость по карточке ухудшаются.",
                    fix_hint="Проверьте качество товара и ожидания покупателя.",
                )
            )
        article_finality = self._finality_for_row(
            row,
            price_row=price_row,
            ads_unallocated=self._decimal(article_money.ads.unallocated_spend),
            ads_overallocated=self._decimal(article_money.ads.overallocated_spend),
            finance_ready=bool(audit.reconciliation.mart_matches_finance),
            supplier_confirmed=self._profit_row_cost_final_accepted(profit_row),
            expense_mapping_final=not article_expense_breakdown.unallocated_warning,
        )
        article_verdict = self._build_card_verdict(row, price_row)
        article_cost_coverage = self._cost_coverage_from_profit_rows(
            [item[1] for item in article_rows if item[1] is not None],
            cost_trust_policy=str(
                state.settings.get("cost_trust_policy") or "operator_baseline"
            ),
        )
        if not article_cost_coverage.can_use_for_final_profit:
            article_problems.append(
                CardProblem(
                    code="supplier_cost_not_confirmed",
                    severity="warning",
                    title="По карточке не хватает подтвержденной реальной себестоимости",
                    business_impact="Операционные числа уже полезны, но финальная прибыль по карточке остается предварительной.",
                    fix_hint="Загрузите или подтвердите реальную себестоимость, чтобы итоговая прибыль по карточке стала надежной.",
                )
            )
        if (
            article_money.ads.overallocated_spend > 0
            or article_money.ads.unallocated_spend > 0
        ):
            article_problems.append(
                CardProblem(
                    code="ads_allocation_not_final",
                    severity="warning",
                    title="Рекламные расходы по карточке еще не закрыты окончательно",
                    business_impact="Прибыль после рекламы по карточке пока нельзя считать полностью финальной.",
                    fix_hint="Проверьте, полностью ли рекламные расходы распределены по артикулу и его размерам.",
                )
            )
        if article_expense_breakdown.unallocated_warning:
            logistics_problem = article_expense_breakdown.account_level_logistics > 0
            article_problems.append(
                CardProblem(
                    code="wb_logistics_not_linked_to_sku"
                    if logistics_problem
                    else "wb_expenses_not_fully_mapped",
                    severity="warning",
                    title="Логистика WB не привязана к SKU/карточке"
                    if logistics_problem
                    else "Часть WB-расходов не привязана к карточке напрямую",
                    business_impact=(
                        "Логистика может полностью съедать прибыль, но WB отдал её без SKU/баркода; прибыль по карточке пока предварительная."
                        if logistics_problem
                        else "Прибыль по карточке еще предварительная, пока часть общих расходов магазина не распределена точнее."
                    ),
                    fix_hint=(
                        "Откройте строки отчета по логистике WB и проверьте строки без SKU/баркода; до распределения логистики не считайте прибыль карточки финальной."
                        if logistics_problem
                        else "Проверьте строки финансового отчета без номера артикула или штрихкода и распределение общих расходов магазина."
                    ),
                )
            )
        operations_block = CardOperationsBlock(
            orders_count=self._int0(audit.operations.orders_count),
            cancelled_orders_count=self._int0(audit.operations.cancelled_orders_count),
            cancel_rate_percent=cancel_rate or 0.0,
            sales_count=self._int0(audit.operations.sales_count),
            returns_count=self._int0(audit.operations.returns_count),
            return_rate_percent=return_rate or 0.0,
            net_units=self._int0(audit.finance.net_units),
            issue="",
        )
        funnel_block = CardFunnelBlock(
            open_count=self._int0(audit.funnel.open_count),
            cart_count=self._int0(audit.funnel.cart_count),
            order_count=self._int0(audit.funnel.order_count),
            buyout_count=self._int0(audit.funnel.buyout_count),
            cart_conversion_percent=self._percent0(
                audit.funnel.cart_count, audit.funnel.open_count
            ),
            order_conversion_percent=self._percent0(
                audit.funnel.order_count, audit.funnel.open_count
            ),
            buyout_rate_percent=self._percent0(
                audit.funnel.buyout_count, audit.funnel.order_count
            ),
            issue="",
        )
        reconciliation_block = CardReconciliationBlock(
            mart_matches_article=audit.reconciliation.mart_matches_article,
            mart_matches_finance=audit.reconciliation.mart_matches_finance,
            finance_matches_operational=bool(
                audit.reconciliation.finance_matches_operational
            ),
            revenue_matches_mart=audit.reconciliation.revenue_matches_mart,
            mart_revenue_total=self._float0(audit.reconciliation.mart_revenue_total),
            article_revenue_total=self._float0(
                audit.reconciliation.article_revenue_total
            ),
            finance_report_revenue_total=self._float0(
                audit.reconciliation.finance_report_revenue_total
            ),
            difference_amount=self._float0(audit.reconciliation.difference_amount),
            difference_ratio_percent=self._float0(
                audit.reconciliation.difference_ratio_percent
            ),
            status="critical_mismatch"
            if audit.reconciliation.mart_matches_finance is False
            else "matched",
            mismatch_reason=audit.reconciliation.mismatch_reason or "",
            root_cause_candidates=self._root_cause_candidates(
                audit=audit,
                row=context["primary_row"],
                profit_row=context["primary_profit_row"],
            ),
            next_debug_endpoint=f"/dashboard/article-audit?account_id={account_id}&nm_id={nm_id}&date_from={actual_from.isoformat()}&date_to={actual_to.isoformat()}",
            business_effect="profit_not_final"
            if audit.reconciliation.mart_matches_finance is False
            else "ok",
        )
        trust_block = self._article_trust_block(
            row=row,
            profit_row=profit_row,
            finality=article_finality,
            reconciliation_status=reconciliation_block.status,
        )
        purchase_plan = self._article_purchase_plan(state=state, nm_id=nm_id)
        answer = self._article_money_answer(
            verdict=article_verdict,
            finality=article_finality,
            trust=trust_block,
            stock=article_stock,
            purchase_plan=purchase_plan,
            top_action=top_action,
            profit_after_source_ads=article_money.profit.after_source_ads,
        )
        article_summary = self._article_summary_block(
            nm_id=nm_id,
            title=context["primary_row"].title,
            article_rows=article_rows,
            ads_source_spend=state.ads_source_by_nm.get(nm_id, Decimal("0")),
            decision=decision,
            audit=audit,
        )
        sku_breakdown = self._variant_breakdown_rows(
            state=state,
            article_rows=article_rows,
            ads_source_spend=state.ads_source_by_nm.get(nm_id, Decimal("0")),
        )
        profit_variants = self._profit_variants(
            profit_before_ads=self._decimal(article_money.profit.before_ads),
            ads_allocated_spend=self._decimal(article_money.ads.allocated_spend),
            ads_source_spend=self._decimal(article_money.ads.source_spend),
            allocated_overhead=allocated_overhead,
        )
        return MoneyArticleDetailRead(
            **self._response_cache_fields(state),
            meta=self._meta(
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                health=state.health,
            ),
            nm_id=nm_id,
            identity=MoneyArticleIdentity(
                nm_id=nm_id,
                title=context["primary_row"].title,
                brand=context["primary_row"].brand,
                subject_name=context["primary_row"].subject_name,
            ),
            trust=trust_block,
            money_answer=answer,
            kpis=self._article_kpis(
                money=article_money,
                stock=article_stock,
                operations=operations_block,
            ),
            waterfall=self._article_waterfall(money=article_money),
            cost_coverage=article_cost_coverage,
            money=article_money,
            expense_breakdown=article_expense_breakdown,
            ads=article_money.ads,
            stock=article_stock,
            operations=operations_block,
            funnel=funnel_block,
            price_safety=article_price,
            purchase_plan=purchase_plan,
            reconciliation=reconciliation_block,
            actions=deduped_actions[:3],
            issues=article_problems,
            sku_breakdown=sku_breakdown,
            article_summary=article_summary,
            profit_variants=profit_variants,
            finality=article_finality,
            answer=answer,
            price=article_price,
            next_actions=deduped_actions[:10],
            problems=article_problems,
            variant_breakdown=sku_breakdown,
        )

    def _fast_article_audit_preview(
        self,
        *,
        account_id: int,
        nm_id: int,
        row: Any,
        profit_row: Any,
        actual_from: date,
        actual_to: date,
    ) -> SimpleNamespace:
        revenue = self._float0(getattr(profit_row, "realized_revenue", 0))
        net_units = self._int0(getattr(profit_row, "net_units", 0))
        return SimpleNamespace(
            operations=SimpleNamespace(
                orders_count=self._int0(getattr(profit_row, "orders_count", 0)),
                cancelled_orders_count=self._int0(
                    getattr(profit_row, "cancelled_orders_count", 0)
                ),
                sales_count=self._int0(getattr(profit_row, "sales_count", 0)),
                returns_count=self._int0(getattr(profit_row, "returns_count", 0)),
            ),
            finance=SimpleNamespace(net_units=net_units),
            ads=SimpleNamespace(
                stats_rows_count=0, views=0, clicks=0, orders=0, atbs=0
            ),
            funnel=SimpleNamespace(
                open_count=0, cart_count=0, order_count=0, buyout_count=0
            ),
            reconciliation=SimpleNamespace(
                mart_matches_article=True,
                mart_matches_finance=False,
                finance_matches_operational=None,
                revenue_matches_mart=True,
                mart_revenue_total=revenue,
                article_revenue_total=revenue,
                finance_report_revenue_total=0.0,
                difference_amount=0.0,
                difference_ratio_percent=0.0,
                mismatch_reason="audit_skipped_for_fast_product_360_preview",
            ),
            stock=SimpleNamespace(quantity=self._float0(getattr(row, "stock_qty", 0))),
            meta=SimpleNamespace(
                account_id=account_id,
                nm_id=nm_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
        )

    async def card_detail(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> MoneyCardDetailRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        state = await self._load_runtime_state(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        total_revenue_all = sum(
            (self._decimal(item.realized_revenue) for item in state.profit_rows),
            start=Decimal("0"),
        )
        row = next((item for item in state.control_rows if item.sku_id == sku_id), None)
        if row is None:
            fallback = await self._missing_money_card_detail(
                session,
                state=state,
                account_id=account_id,
                sku_id=sku_id,
                date_from=actual_from,
                date_to=actual_to,
            )
            if fallback is not None:
                return fallback
            raise HTTPException(status_code=404, detail="Денежная карточка не найдена")
        price_row = state.price_rows.get(sku_id)
        purchase_row = state.purchase_rows.get(sku_id)
        profit_row = next(
            (item for item in state.profit_rows if item.sku_id == sku_id), None
        )
        if profit_row is None:
            fallback = await self._missing_money_card_detail(
                session,
                state=state,
                account_id=account_id,
                sku_id=sku_id,
                date_from=actual_from,
                date_to=actual_to,
            )
            if fallback is not None:
                return fallback
            raise HTTPException(
                status_code=404, detail="Данные по прибыльности карточки не найдены"
            )
        article_rows = [
            (item, next_profit, state.purchase_rows.get(int(item.sku_id)))
            for item in state.control_rows
            if item.sku_id is not None
            and item.nm_id == row.nm_id
            and (
                next_profit := next(
                    (p for p in state.profit_rows if p.sku_id == item.sku_id), None
                )
            )
            is not None
        ]
        audit = await self.dashboard.article_audit(
            session,
            account_id=account_id,
            nm_id=int(row.nm_id),
            date_from=actual_from,
            date_to=actual_to,
        )
        meta = self._meta(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            health=state.health,
        )
        next_actions: list[NextActionRead] = []
        persisted_actions = self._actions_for_sku(state, sku_id)
        persisted_actions.sort(key=self._action_sort_key, reverse=True)
        next_actions.extend(
            self._action_from_recommendation(item) for item in persisted_actions
        )
        if audit.reconciliation.mart_matches_finance is False and not persisted_actions:
            if not any(
                item.action_type == "RECONCILE_FINANCE" for item in next_actions
            ):
                next_actions.append(
                    NextActionRead(
                        action_type="RECONCILE_FINANCE",
                        action_group="data_fix",
                        priority="critical",
                        title="Нужно проверить расхождение по выручке",
                        what_to_do="Разберите расхождение между выручкой из отчета WB и расчетной выручкой на уровне исходных строк.",
                        why="Пока расхождение не закрыто, прибыли карточки доверять нельзя.",
                        how_to_fix=[
                            "Откройте аудит артикула",
                            "Сравните исходные строки",
                            "Классифицируйте расхождение",
                        ],
                        expected_effect_amount=abs(
                            self._float0(audit.reconciliation.difference_amount)
                        ),
                        confidence="high",
                        linked_entity={
                            "sku_id": sku_id,
                            "nm_id": row.nm_id,
                            "vendor_code": row.vendor_code,
                        },
                    )
                )
        if (
            audit.ads.spend > 0
            and float(profit_row.ad_spend or 0) == 0
            and not persisted_actions
        ):
            if not any(
                item.action_type == "FIX_AD_ALLOCATION" for item in next_actions
            ):
                next_actions.append(
                    NextActionRead(
                        action_type="FIX_AD_ALLOCATION",
                        action_group="data_fix",
                        priority="high",
                        title="Нужно привязать рекламные расходы к прибыли карточки",
                        what_to_do="Сверьте исходные рекламные расходы с расчетом рекламы по карточке и исправьте привязку.",
                        why="В аудите артикула реклама есть, но в слое прибыльности она видна не полностью.",
                        how_to_fix=[
                            "Сравните исходные рекламные данные и расчеты по карточкам",
                            "Проверьте привязку по артикулу",
                        ],
                        expected_effect_amount=self._float0(audit.ads.spend),
                        confidence="high",
                        linked_entity={
                            "sku_id": sku_id,
                            "nm_id": row.nm_id,
                            "vendor_code": row.vendor_code,
                        },
                    )
                )
        if not next_actions:
            next_actions.append(self._default_row_action(row))
        next_actions.sort(
            key=lambda item: (
                self._priority_rank(item.priority),
                1 if self._is_account_level_linked_entity(item.linked_entity) else 0,
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        )
        decision = "watch"
        if row.trust_state == TRUST_STATE_DATA_BLOCKED:
            decision = "fix_data_first"
        elif purchase_row is not None and purchase_row.status == "REORDER":
            decision = "reorder"
        elif purchase_row is not None and purchase_row.status == "DO_NOT_BUY":
            decision = "do_not_reorder"
        elif purchase_row is not None and purchase_row.status == "PROTECT_STOCK":
            decision = "protect_stock"
        elif purchase_row is not None and purchase_row.status == "LIQUIDATE":
            decision = "liquidate_stock"
        elif (
            price_row is not None
            and price_row.safe_price_gap is not None
            and price_row.safe_price_gap < 0
        ):
            decision = "review_price"
        problems: list[CardProblem] = []
        cancel_rate = self._percent(
            audit.operations.cancelled_orders_count, audit.operations.orders_count
        )
        if cancel_rate is not None and cancel_rate >= 50:
            problems.append(
                CardProblem(
                    code="high_cancel_rate",
                    severity="warning",
                    title="Высокая доля отмен",
                    business_impact="Может быть проблема со спросом, качеством карточки или размерной сеткой",
                    fix_hint="Проверьте причины отмен и проблемы с контентом или размерами",
                )
            )
        return_rate = self._percent(
            audit.operations.returns_count, audit.operations.sales_count
        )
        if return_rate is not None and return_rate >= 20:
            problems.append(
                CardProblem(
                    code="high_return_rate",
                    severity="warning",
                    title="Высокая доля возвратов",
                    business_impact="Чистая прибыль и оборачиваемость остатков ухудшаются",
                    fix_hint="Проверьте качество товара, размеры и расхождение ожиданий покупателя",
                )
            )
        allocated_overhead = self._allocated_overhead(
            revenue=self._decimal(getattr(profit_row, "realized_revenue", None)),
            total_revenue=total_revenue_all,
            account_level_expense_total=state.account_level_expense_total,
        )
        card_money = self._build_card_money(
            profit_row,
            row,
            price_row=price_row,
            purchase_row=purchase_row,
            ads_source_spend=self._decimal(getattr(row, "ad_spend", None)),
            account_level_expense_total=state.account_level_expense_total,
            account_level_logistics_total=getattr(
                state, "account_level_logistics_total", Decimal("0")
            ),
            allocated_overhead=allocated_overhead,
        )
        ads_views_by_sku = self._allocate_article_count_metric_by_sku(
            article_rows=article_rows,
            total_value=self._int0(getattr(audit.ads, "views", 0)),
        )
        ads_clicks_by_sku = self._allocate_article_count_metric_by_sku(
            article_rows=article_rows,
            total_value=self._int0(getattr(audit.ads, "clicks", 0)),
        )
        ads_orders_by_sku = self._allocate_article_count_metric_by_sku(
            article_rows=article_rows,
            total_value=self._int0(getattr(audit.ads, "orders", 0)),
        )
        ads_atbs_by_sku = self._allocate_article_count_metric_by_sku(
            article_rows=article_rows,
            total_value=self._int0(getattr(audit.ads, "atbs", 0)),
        )
        card_money = card_money.model_copy(
            update={
                "ads": self._ads_block_with_metrics(
                    card_money.ads,
                    stats_rows_count=self._int0(
                        getattr(audit.ads, "stats_rows_count", 0)
                    ),
                    views=ads_views_by_sku.get(sku_id, 0),
                    clicks=ads_clicks_by_sku.get(sku_id, 0),
                    orders=ads_orders_by_sku.get(sku_id, 0),
                    atbs=ads_atbs_by_sku.get(sku_id, 0),
                )
            }
        )
        card_expense_breakdown = self._article_expense_breakdown(card_money.wb_expenses)
        if card_expense_breakdown.unallocated_warning:
            logistics_problem = card_expense_breakdown.account_level_logistics > 0
            problems.append(
                CardProblem(
                    code="wb_logistics_not_linked_to_sku"
                    if logistics_problem
                    else "wb_expenses_not_fully_mapped",
                    severity="warning",
                    title="Логистика WB не привязана к SKU/карточке"
                    if logistics_problem
                    else "Часть WB-расходов не привязана к карточке напрямую",
                    business_impact=(
                        "Логистика может полностью съедать прибыль, но WB отдал её без SKU/баркода; прибыль по SKU пока предварительная."
                        if logistics_problem
                        else "Прибыль по SKU еще предварительная, пока часть общих расходов магазина не распределена точнее."
                    ),
                    fix_hint=(
                        "Откройте строки отчета по логистике WB и проверьте строки без SKU/баркода; до распределения логистики не считайте прибыль SKU финальной."
                        if logistics_problem
                        else "Проверьте строки финансового отчета без номера артикула или штрихкода и распределение общих расходов магазина."
                    ),
                )
            )
        card_finality = self._finality_for_row(
            row,
            price_row=price_row,
            ads_unallocated=self._decimal(card_money.ads.unallocated_spend),
            ads_overallocated=self._decimal(card_money.ads.overallocated_spend),
            finance_ready=bool(audit.reconciliation.mart_matches_finance),
            supplier_confirmed=self._profit_row_cost_final_accepted(profit_row),
            expense_mapping_final=not card_expense_breakdown.unallocated_warning,
        )
        card_verdict = self._build_card_verdict(row, price_row)
        answer = MoneyCardAnswer(
            status=card_verdict.status
            if card_verdict.status == "data_blocked" or card_finality.profit_final
            else "provisional",
            title=(
                "Экономика карточки и следующий шаг определены"
                if card_finality.profit_final
                else "Экономика карточки и следующий шаг готовы в предварительном режиме"
            ),
            short_text=(
                "Данных достаточно, чтобы выбрать следующий шаг по карточке."
                if card_finality.profit_final
                else "По карточке видны продажи, остатки и прибыль, но итоговое решение нужно трактовать осторожно."
            ),
            decision=decision,
            main_next_step=next_actions[0].what_to_do if next_actions else "",
            main_reason=next_actions[0].why if next_actions else "",
        )
        card_cost_coverage = self._cost_coverage_from_profit_rows(
            [profit_row],
            cost_trust_policy=str(
                state.settings.get("cost_trust_policy") or "operator_baseline"
            ),
        )
        return MoneyCardDetailRead(
            **self._response_cache_fields(state),
            meta=meta,
            identity=MoneyIdentity(
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                barcode=row.barcode,
                title=row.title,
                brand=row.brand,
                subject_name=row.subject_name,
            ),
            answer=answer,
            cost_coverage=card_cost_coverage,
            money=card_money,
            expense_breakdown=card_expense_breakdown,
            operations=CardOperationsBlock(
                orders_count=self._int0(audit.operations.orders_count),
                cancelled_orders_count=self._int0(
                    audit.operations.cancelled_orders_count
                ),
                cancel_rate_percent=cancel_rate or 0.0,
                sales_count=self._int0(audit.operations.sales_count),
                returns_count=self._int0(audit.operations.returns_count),
                return_rate_percent=return_rate or 0.0,
                net_units=self._int0(audit.finance.net_units),
                issue="Высокая доля отмен"
                if cancel_rate is not None and cancel_rate >= 50
                else "",
            ),
            funnel=CardFunnelBlock(
                open_count=self._int0(audit.funnel.open_count),
                cart_count=self._int0(audit.funnel.cart_count),
                order_count=self._int0(audit.funnel.order_count),
                buyout_count=self._int0(audit.funnel.buyout_count),
                cart_conversion_percent=self._percent0(
                    audit.funnel.cart_count, audit.funnel.open_count
                ),
                order_conversion_percent=self._percent0(
                    audit.funnel.order_count, audit.funnel.open_count
                ),
                buyout_rate_percent=self._percent0(
                    audit.funnel.buyout_count, audit.funnel.order_count
                ),
                issue=(
                    "Низкий выкуп или требуется дополнительная проверка расхождений"
                    if audit.funnel.order_count > 0
                    and self._percent0(
                        audit.funnel.buyout_count, audit.funnel.order_count
                    )
                    < 20
                    else ""
                ),
            ),
            stock=self._build_card_stock(row, profit_row, purchase_row),
            price=self._build_card_price(
                price_row, profit_row=profit_row, settings=state.settings
            ),
            reconciliation=CardReconciliationBlock(
                mart_matches_article=audit.reconciliation.mart_matches_article,
                mart_matches_finance=audit.reconciliation.mart_matches_finance,
                finance_matches_operational=bool(
                    audit.reconciliation.finance_matches_operational
                ),
                revenue_matches_mart=audit.reconciliation.revenue_matches_mart,
                mart_revenue_total=self._float0(
                    audit.reconciliation.mart_revenue_total
                ),
                article_revenue_total=self._float0(
                    audit.reconciliation.article_revenue_total
                ),
                finance_report_revenue_total=self._float0(
                    audit.reconciliation.finance_report_revenue_total
                ),
                difference_amount=self._float0(audit.reconciliation.difference_amount),
                difference_ratio_percent=self._float0(
                    audit.reconciliation.difference_ratio_percent
                ),
                status="critical_mismatch"
                if audit.reconciliation.mart_matches_finance is False
                else "matched",
                mismatch_reason=audit.reconciliation.mismatch_reason or "",
                root_cause_candidates=self._root_cause_candidates(
                    audit=audit, row=row, profit_row=profit_row
                ),
                next_debug_endpoint=f"/dashboard/article-audit?account_id={account_id}&nm_id={int(row.nm_id)}&date_from={actual_from.isoformat()}&date_to={actual_to.isoformat()}"
                if row.nm_id is not None
                else "",
                business_effect="profit_not_final"
                if audit.reconciliation.mart_matches_finance is False
                else "ok",
            ),
            problems=problems,
            next_actions=next_actions,
            article_summary=self._article_summary_block(
                nm_id=int(row.nm_id),
                title=row.title,
                article_rows=article_rows,
                ads_source_spend=state.ads_source_by_nm.get(
                    int(row.nm_id), Decimal("0")
                )
                if row.nm_id is not None
                else Decimal("0"),
                decision=decision,
                audit=audit,
            ),
            variant_breakdown=self._variant_breakdown_rows(
                state=state,
                article_rows=article_rows,
                ads_source_spend=state.ads_source_by_nm.get(
                    int(row.nm_id), Decimal("0")
                )
                if row.nm_id is not None
                else Decimal("0"),
            ),
            profit_variants=self._profit_variants(
                profit_before_ads=self._decimal(card_money.profit.before_ads),
                ads_allocated_spend=self._decimal(card_money.ads.allocated_spend),
                ads_source_spend=self._decimal(card_money.ads.source_spend),
                allocated_overhead=allocated_overhead,
            ),
            finality=card_finality,
        )

    async def today_actions(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        priority: str | None = None,
        status: str | None = None,
        action_type: str | None = None,
        group_by: str = "article",
        focus_limit: int = 10,
        limit: int = 100,
        offset: int = 0,
    ) -> TodayActionsPage:
        actual_from, actual_to = self._date_range(date_from, date_to)
        state = await self._load_runtime_state(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        filtered = [
            self._action_from_recommendation(action)
            for action in state.action_reads
            if self._is_open_action_status(action.status)
        ]
        filtered = [
            item for item in filtered if not self._is_system_handled_action(item)
        ]
        if priority:
            filtered = [item for item in filtered if item.priority == priority]
        if status:
            filtered = [item for item in filtered if item.status == status]
        if action_type:
            filtered = [item for item in filtered if item.action_type == action_type]
        filtered.sort(
            key=lambda item: (
                self._priority_rank(item.priority),
                1 if self._is_account_level_linked_entity(item.linked_entity) else 0,
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        )
        grouped_actions, total_raw = self._merge_grouped_actions(
            filtered, group_by=group_by
        )
        owner_ready_grouped = sorted(
            [self._owner_action_enriched(item) for item in grouped_actions],
            key=lambda item: (
                self._priority_rank(item.priority),
                item.priority_score or 0,
                item.expected_effect_amount or 0,
            ),
            reverse=True,
        )
        focus_limit = max(1, min(focus_limit, 20))
        owner_focus_actions = self._owner_focus_actions(
            owner_ready_grouped, focus_limit=focus_limit
        )
        buckets = {
            "save_money": [],
            "release_cash": [],
            "protect_revenue": [],
            "finance_reconcile": [],
            "global_blockers": [],
            "money_saving": [],
            "growth": [],
            "data_fix": [],
            "watch": [],
        }
        for item in owner_ready_grouped:
            bucket = self._action_group_bucket(item)
            buckets[bucket].append(item)
            if bucket in {"save_money", "release_cash"}:
                buckets["money_saving"].append(item)
        summary = {
            "critical": sum(
                1 for item in owner_ready_grouped if item.priority == "critical"
            ),
            "high": sum(1 for item in owner_ready_grouped if item.priority == "high"),
            "medium": sum(
                1 for item in owner_ready_grouped if item.priority == "medium"
            ),
            "low": sum(1 for item in owner_ready_grouped if item.priority == "low"),
            "global_blockers": len(buckets["global_blockers"]),
            "save_money": len(buckets["save_money"]),
            "release_cash": len(buckets["release_cash"]),
            "protect_revenue": len(buckets["protect_revenue"]),
            "growth": len(buckets["growth"]),
            "data_fix": len(buckets["data_fix"]),
            "finance_reconcile": len(buckets["finance_reconcile"]),
            "money_saving": len(buckets["money_saving"]),
            "watch": len(buckets["watch"]),
            "total_raw": total_raw,
            "total_grouped": len(owner_ready_grouped),
            "top_focus_count": len(owner_focus_actions),
        }
        return TodayActionsPage(
            **self._response_cache_fields(state),
            total=len(owner_ready_grouped),
            limit=limit,
            offset=offset,
            summary=summary,
            groups=buckets,
            items=owner_ready_grouped[offset : offset + limit],
            owner_focus_actions=owner_focus_actions,
        )

    async def data_blockers(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DataBlockersRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        state = await self._load_runtime_state(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        meta = self._meta(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            health=state.health,
        )
        revenue_total = sum(
            (self._decimal(item.realized_revenue) for item in state.profit_rows),
            start=Decimal("0"),
        )
        mart_ads_allocated_total = sum(
            (
                self._decimal(getattr(item, "ad_spend", None))
                for item in state.profit_rows
            ),
            start=Decimal("0"),
        )
        ads_allocatable_total = sum(state.ads_source_by_nm.values(), start=Decimal("0"))
        ads_metrics = self._ads_allocation_metrics(
            ads_source_spend=self._decimal(state.ads_source_total),
            mart_ads_allocated_spend=mart_ads_allocated_total,
            ads_allocatable_source_spend=ads_allocatable_total,
        )
        ads_metrics["ads_source_spend"] = self._decimal(state.ads_source_total)
        ads_metrics["mart_ads_allocated_spend"] = mart_ads_allocated_total
        ads_metrics["ads_allocatable_source_spend"] = ads_allocatable_total
        blockers: list[DataBlockerRead] = []
        warnings: list[DataBlockerRead] = []
        for reason in state.health.blocked_reasons:
            if self._is_hidden_user_problem_code(reason):
                continue
            if reason == "supplier_cost_coverage_below_threshold":
                blockers.append(
                    DataBlockerRead(
                        code=reason,
                        priority="critical",
                        title="Недостаточно подтвержденной реальной себестоимости",
                        affected_sku_count=sum(
                            1
                            for row in state.profit_rows
                            if not row.has_real_manual_cost
                        ),
                        affected_revenue=float(revenue_total),
                        current_value=self._float0(
                            state.health.supplier_confirmed_revenue_coverage_percent
                        ),
                        required_value=95.0,
                        unit="процент покрытия выручки",
                        business_impact="Прибыль, окупаемость, план закупок и безопасная цена пока ненадежны.",
                        how_to_fix=[
                            "Скачайте шаблон себестоимости",
                            "Заполните реальные данные поставщика",
                            "Загрузите и подтвердите импорт",
                            "Пересчитайте аналитические таблицы",
                        ],
                        simple_reason="Слишком большая часть выручки все еще считается без подтвержденной себестоимости поставщика.",
                        first_action="Сначала откройте экран «Себестоимость» и загрузите или подтвердите недостающие строки.",
                        success_check=[
                            "Покрытие подтвержденной себестоимостью выросло до 95% или выше.",
                            "Блокер по покрытию себестоимости исчез из списка.",
                        ],
                        wait_or_fix_hint="Этот блокер сам не исчезнет: себестоимость нужно загрузить или подтвердить.",
                        related_endpoints=[
                            "GET /costs/template",
                            "POST /costs/upload",
                            "POST /costs/uploads/{upload_id}/confirm",
                            "POST /marts/refresh",
                        ],
                        exact_next_endpoint="GET /costs/template",
                        next_screen_path="/costs",
                        next_screen_label="Открыть себестоимость",
                    )
                )
            elif reason == "unmatched_sku_detected":
                blockers.append(
                    DataBlockerRead(
                        code=reason,
                        priority="critical",
                        title="Есть данные по товару, но SKU не привязан к карточке",
                        affected_sku_count=self._int0(state.health.unmatched_sku_count),
                        affected_revenue=0.0,
                        current_value=0.0,
                        required_value=0.0,
                        unit="",
                        business_impact="Продажи, остатки или себестоимость могут попасть не в ту карточку, пока SKU не сопоставлен с каталогом.",
                        how_to_fix=[
                            "Откройте «Себестоимость» и найдите блок «Перепривязать SKU».",
                            "Проверьте проблемные строки по nm_id, баркоду или артикулу продавца.",
                            "Если ошибка пришла из файла себестоимости, исправьте файл и загрузите его заново.",
                            "Нажмите «Перепривязать SKU», чтобы система заново сопоставила строки с карточками.",
                            "Если строки остались, передайте их администратору: нужно проверить правила сопоставления или импорт каталога.",
                            "После привязки повторно запустите проверку качества данных.",
                        ],
                        simple_reason="В продажах, остатках или себестоимости есть товарный идентификатор, который система не смогла надежно сопоставить с карточкой каталога.",
                        first_action="Сначала откройте «Себестоимость» → блок «Перепривязать SKU» и найдите проблемную строку по nm_id, баркоду или артикулу продавца.",
                        success_check=[
                            "Количество несвязанных SKU стало 0.",
                            "Проблема больше не блокирует финальный расчёт.",
                            "Выручка, остатки и себестоимость попали в правильную карточку.",
                        ],
                        wait_or_fix_hint="Ждать имеет смысл только если данные только что загрузились. Если проблема осталась после повторной синхронизации, SKU нужно привязать.",
                        related_endpoints=[
                            "GET /dq/issues",
                            "GET /dq/issues/investigator",
                            "PATCH /dq/issues/{issue_id}/classify",
                            "POST /dq/issues/{issue_id}/resolve",
                        ],
                        exact_next_endpoint="GET /dq/issues/investigator",
                        next_screen_path="/costs",
                        next_screen_label="Перепривязать SKU",
                    )
                )
            elif reason == "latest_stocks_not_completed":
                blockers.append(
                    DataBlockerRead(
                        code=reason,
                        priority="critical",
                        title="Последняя синхронизация остатков не завершена",
                        affected_sku_count=len(state.control_rows),
                        affected_revenue=float(revenue_total)
                        if revenue_total > 0
                        else 0.0,
                        current_value=0.0,
                        required_value=0.0,
                        unit="",
                        business_impact="Остатки и закупочные рекомендации ненадежны.",
                        how_to_fix=[
                            "Откройте «Админка» → «Синхронизация».",
                            "В фильтре домена выберите «Остатки».",
                            "Найдите последний запуск со статусом ошибки или зависания.",
                            "Запустите повторную загрузку остатков.",
                            "Дождитесь нового завершённого снимка.",
                        ],
                        simple_reason="Последняя загрузка остатков не закончилась, поэтому текущие остатки могут быть неполными или старыми.",
                        first_action="Сначала откройте «Админка» → «Синхронизация» и проверьте последний запуск по остаткам.",
                        success_check=[
                            "Появился новый завершённый снимок остатков.",
                            "Блокер по остаткам исчез из списка.",
                        ],
                        wait_or_fix_hint="Если загрузка остатков прямо сейчас выполняется, сначала дождитесь её завершения.",
                        related_endpoints=[
                            "GET /sync/runs",
                            "GET /sync/cursors",
                            "POST /sync/trigger",
                        ],
                        exact_next_endpoint="GET /sync/runs",
                        next_screen_path="/admin",
                        next_screen_label="Открыть синхронизацию",
                    )
                )
            elif reason == "open_blocking_dq_issues":
                blockers.append(
                    DataBlockerRead(
                        code=reason,
                        priority="critical",
                        title="Есть блокирующие проблемы качества данных",
                        affected_sku_count=self._int0(state.health.open_issues_total),
                        affected_revenue=float(revenue_total)
                        if revenue_total > 0
                        else 0.0,
                        current_value=0.0,
                        required_value=0.0,
                        unit="",
                        business_impact="Бизнес-действия заблокированы, а экономика карточек находится под риском.",
                        how_to_fix=[
                            "Откройте текущий список ниже на экране «Починка данных».",
                            "Начните с карточек с приоритетом «Критично».",
                            "Закройте ручные блокеры: себестоимость, привязка SKU, расходы или контент.",
                            "После исправления нажмите «Обновить» и проверьте, что блокер исчез.",
                        ],
                        simple_reason="Есть открытые проблемы качества данных, из-за которых система не готова показывать финальную прибыль как надежную.",
                        first_action="Сначала посмотрите список блокеров ниже и откройте первый критичный пункт.",
                        success_check=[
                            "Финальные блокеры уменьшились до нуля.",
                            "Статус доверия больше не заблокирован.",
                        ],
                        wait_or_fix_hint="Этот блокер исчезнет только тогда, когда будут закрыты конкретные проблемы внутри списка.",
                        related_endpoints=[
                            "GET /dashboard/data-health",
                            "GET /dq/issues",
                            "POST /dq/run",
                        ],
                        exact_next_endpoint="GET /dashboard/data-health",
                        next_screen_path="/data-fix",
                        next_screen_label="Открыть список блокеров",
                    )
                )
            elif reason == "failed_sync_domains":
                blockers.append(
                    DataBlockerRead(
                        code=reason,
                        priority="critical",
                        title="Есть ошибки в загрузке данных",
                        affected_sku_count=len(state.control_rows),
                        affected_revenue=0.0,
                        affected_amount=self._float0(state.ads_source_total),
                        current_value=0.0,
                        required_value=0.0,
                        unit="",
                        business_impact="Часть исходных данных может быть неполной.",
                        how_to_fix=[
                            "Откройте «Админка» → «Синхронизация».",
                            "Найдите домен со статусом ошибки: продажи, финансы, остатки, реклама или себестоимость.",
                            "Откройте последний запуск и посмотрите короткую причину ошибки.",
                            "Запустите повторную загрузку этого домена.",
                            "Если ошибка повторилась, передайте домен и время запуска администратору.",
                        ],
                        simple_reason="Один или несколько источников данных загрузились с ошибкой, поэтому часть цифр может быть неполной.",
                        first_action="Сначала откройте «Админка» → «Синхронизация» и посмотрите, какой домен загрузился с ошибкой.",
                        success_check=[
                            "У проблемного домена появился успешный завершённый запуск.",
                            "Ошибка синхронизации исчезла из блокеров.",
                        ],
                        wait_or_fix_hint="Если причина ошибки временная, повторная загрузка часто решает проблему.",
                        related_endpoints=[
                            "GET /sync/runs",
                            "POST /sync/trigger",
                            "POST /sync/backfill",
                        ],
                        exact_next_endpoint="GET /sync/runs",
                        next_screen_path="/admin",
                        next_screen_label="Открыть синхронизацию",
                    )
                )
        blocker_codes = {item.code for item in blockers}
        open_issue_summary: dict[str, int] = {}
        for bucket in getattr(state.health, "issue_buckets", []) or []:
            if self._is_hidden_user_problem_code(getattr(bucket, "code", None)):
                continue
            if self._int0(bucket.count) <= 0:
                continue
            open_issue_summary[bucket.code] = open_issue_summary.get(
                bucket.code, 0
            ) + self._int0(bucket.count)
            if bucket.code not in blocker_codes:
                blocker_item = self._blocker_from_issue_bucket(
                    bucket, revenue_total=revenue_total
                )
                if blocker_item is not None:
                    if blocker_item.code == "unmatched_sku":
                        blocker_item.affected_sku_count = self._int0(
                            getattr(state.health, "blocking_unmatched_sku_count", 0)
                        )
                    elif blocker_item.code == "missing_manual_cost":
                        blocker_item.affected_sku_count = self._int0(
                            getattr(state.health, "missing_manual_cost_count", 0)
                        )
                    blockers.append(blocker_item)
                    blocker_codes.add(blocker_item.code)
                    continue
        ads_unallocated_total = self._decimal(ads_metrics["ads_unallocated_spend"])
        ads_overallocated_total = self._decimal(ads_metrics["ads_overallocated_spend"])
        if ads_unallocated_total > 0 or ads_overallocated_total > 0:
            ads_is_overallocated = ads_overallocated_total > 0
            ads_warning_code = (
                "ads_overallocated_to_profitability"
                if ads_is_overallocated
                else "ads_not_allocated_to_profitability"
            )
            ads_warning_title = (
                "Рекламные расходы привязаны к прибыли с риском двойного учета"
                if ads_is_overallocated
                else "Рекламные расходы не полностью привязаны к прибыли"
            )
            ads_warning_impact = (
                "Прибыль после рекламы остается предварительной, потому что по карточкам распределено больше рекламы, чем видно в источнике WB."
                if ads_is_overallocated
                else "Прибыль после рекламы остается предварительной, пока рекламные расходы из источника не доведены до карточек."
            )
            ads_warning_reason = (
                "Сумма рекламы в карточках выше исходной суммы WB. Излишек игнорируется в финальной сумме, но требует проверки маппинга."
                if ads_is_overallocated
                else "Часть рекламных расходов есть на уровне источника, но она еще не распределена по карточкам товара."
            )
            ads_warning_success = (
                [
                    "Сырая аллокация рекламы не превышает сумму из источника WB.",
                    "Предупреждение о двойном учете рекламы исчезло.",
                ]
                if ads_is_overallocated
                else [
                    "Доля распределенной рекламы стала близка к 100%.",
                    "Предупреждение об аллокации рекламы исчезло.",
                ]
            )
            warnings.append(
                DataBlockerRead(
                    code=ads_warning_code,
                    priority="high",
                    title=ads_warning_title,
                    affected_sku_count=sum(
                        1
                        for row in state.control_rows
                        if self._decimal(getattr(row, "ad_spend", None)) <= 0
                        and self._decimal(
                            state.ads_source_by_nm.get(int(row.nm_id), Decimal("0"))
                            if row.nm_id is not None
                            else Decimal("0")
                        )
                        > 0
                    ),
                    affected_revenue=float(revenue_total),
                    affected_amount=self._float0(
                        ads_unallocated_total + ads_overallocated_total
                    ),
                    current_value=(
                        self._float0(ads_metrics["ads_allocation_percent_raw"])
                        if ads_is_overallocated
                        else self._float0(ads_metrics["ads_allocation_percent_capped"])
                    ),
                    required_value=100.0,
                    unit="процент сырой аллокации рекламы"
                    if ads_is_overallocated
                    else "процент аллокации рекламы",
                    business_impact=ads_warning_impact,
                    how_to_fix=[
                        "Сверьте исходные рекламные расходы и расчеты по карточкам",
                        "Проверьте маппинг по nm_id",
                        "Пересчитайте аналитические таблицы",
                    ],
                    simple_reason=ads_warning_reason,
                    first_action="Сначала откройте рекламу в Деньгах и проверьте рекламу по карточкам.",
                    success_check=ads_warning_success,
                    wait_or_fix_hint="Это warning: деньги уже видны в общем объеме, но прибыль по карточкам еще предварительная.",
                    related_endpoints=["GET /ads/efficiency", "POST /marts/refresh"],
                    exact_next_endpoint="GET /ads/efficiency",
                    next_screen_path="/money?section=ads",
                    next_screen_label="Открыть рекламу в Деньгах",
                )
            )
        for bucket in getattr(state.health, "issue_buckets", []) or []:
            if self._is_hidden_user_problem_code(getattr(bucket, "code", None)):
                continue
            if self._int0(bucket.count) <= 0:
                continue
            warning_item = self._warning_from_issue_bucket(
                bucket, revenue_total=revenue_total
            )
            if warning_item is not None:
                warnings.append(warning_item)
        if any(item.code != "open_blocking_dq_issues" for item in blockers):
            blockers = [
                item for item in blockers if item.code != "open_blocking_dq_issues"
            ]
        deduped_blockers: list[DataBlockerRead] = []
        seen_blocker_codes: set[str] = set()
        for blocker in blockers:
            if blocker.code in seen_blocker_codes:
                continue
            seen_blocker_codes.add(blocker.code)
            deduped_blockers.append(blocker)
        deduped_warnings: list[DataBlockerRead] = []
        seen_warning_codes: set[str] = set()
        for warning in warnings:
            if warning.code in seen_warning_codes:
                continue
            seen_warning_codes.add(warning.code)
            deduped_warnings.append(warning)
        for item in [*deduped_blockers, *deduped_warnings]:
            self._attach_data_blocker_calculation(
                item,
                state=state,
                revenue_total=revenue_total,
                ads_metrics=ads_metrics,
            )
        data_quality_summary = (
            getattr(state.health, "data_quality_summary", None)
            or DataQualitySummaryBlock()
        )
        visible_summary_buckets = [
            bucket
            for bucket in list(getattr(data_quality_summary, "buckets", []) or [])
            if not self._is_hidden_user_problem_code(getattr(bucket, "code", None))
        ]
        if len(visible_summary_buckets) != len(
            list(getattr(data_quality_summary, "buckets", []) or [])
        ):
            visible_open_total = sum(
                self._int0(getattr(bucket, "count", 0))
                for bucket in visible_summary_buckets
            )
            visible_blocking_total = sum(
                self._int0(getattr(bucket, "count", 0))
                for bucket in visible_summary_buckets
                if bool(getattr(bucket, "financial_final_blocker", False))
            )
            data_quality_summary = data_quality_summary.model_copy(
                update={
                    "buckets": visible_summary_buckets,
                    "open_issues_total": visible_open_total,
                    "all_open_issues_total": visible_open_total,
                    "blocking_open_issues_total": visible_blocking_total,
                    "financial_final_blockers_total": visible_blocking_total,
                    "critical_total": sum(
                        self._int0(getattr(bucket, "count", 0))
                        for bucket in visible_summary_buckets
                        if str(getattr(bucket, "severity", "")).lower() == "critical"
                    ),
                    "error_total": sum(
                        self._int0(getattr(bucket, "count", 0))
                        for bucket in visible_summary_buckets
                        if str(getattr(bucket, "severity", "")).lower() == "error"
                    ),
                    "warning_total": sum(
                        self._int0(getattr(bucket, "count", 0))
                        for bucket in visible_summary_buckets
                        if str(getattr(bucket, "severity", "")).lower() == "warning"
                    ),
                    "info_total": sum(
                        self._int0(getattr(bucket, "count", 0))
                        for bucket in visible_summary_buckets
                        if str(getattr(bucket, "severity", "")).lower() == "info"
                    ),
                    "message": getattr(data_quality_summary, "message", "")
                    if visible_open_total > 0
                    else "",
                }
            )
        visible_open_issues_total = sum(open_issue_summary.values())
        overall_state = (
            "data_blocked"
            if deduped_blockers
            else "accepted_with_warnings"
            if deduped_warnings or visible_open_issues_total > 0
            else "trusted"
        )
        if deduped_blockers:
            overall_message = (
                f"Есть блокеры финальной сверки: {self._int0(getattr(data_quality_summary, 'financial_final_blockers_total', 0))} "
                "открытых финальных проблем мешают считать прибыль окончательной."
            )
        else:
            overall_message = (
                getattr(data_quality_summary, "message", "")
                if visible_open_issues_total > 0
                else ""
            ) or self._data_blockers_message(
                blockers_count=len(deduped_blockers),
                warnings_count=len(deduped_warnings),
                can_generate_business_actions=bool(
                    state.health.can_generate_business_actions
                ),
            )
        return DataBlockersRead(
            **self._response_cache_fields(state),
            meta=meta,
            overall_state=overall_state,
            overall_message=overall_message,
            can_generate_business_actions=bool(
                state.health.can_generate_business_actions
            ),
            blockers_count=len(deduped_blockers),
            warnings_count=len(deduped_warnings),
            blockers=deduped_blockers,
            warnings=deduped_warnings,
            open_issue_summary=open_issue_summary,
            data_quality_summary=data_quality_summary,
        )

    async def filters(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> MoneyFiltersRead:
        brands = [
            value
            for value in (
                await session.execute(
                    select(CoreSKU.brand)
                    .where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                        CoreSKU.brand.is_not(None),
                    )
                    .distinct()
                    .order_by(CoreSKU.brand.asc())
                )
            ).scalars()
            if value
        ]
        subjects = [
            value
            for value in (
                await session.execute(
                    select(CoreSKU.subject_name)
                    .where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                        CoreSKU.subject_name.is_not(None),
                    )
                    .distinct()
                    .order_by(CoreSKU.subject_name.asc())
                )
            ).scalars()
            if value
        ]
        card_statuses = [
            FilterOption(key="data_blocked", label="Сначала исправить данные"),
            FilterOption(key="profitable", label="Прибыльные"),
            FilterOption(key="stock_risk", label="Риск по остаткам"),
            FilterOption(key="loss", label="Убыточные"),
            FilterOption(key="overstock", label="Замороженный остаток"),
            FilterOption(key="price_risk", label="Риск цены"),
            FilterOption(key="ad_risk", label="Риск рекламы"),
        ]
        action_types = [
            FilterOption(key=key, label=label)
            for key, label in get_enum_mapping("action_type").items()
            if key in FIX_ACTION_TYPES
            or key
            in {
                "REORDER",
                "DO_NOT_REORDER",
                "LIQUIDATE_STOCK",
                "PRICE_INCREASE_REVIEW",
                "AD_PAUSE_REVIEW",
            }
        ]
        return MoneyFiltersRead(
            date_presets=[
                FilterOption(key="7d", label="7 дней"),
                FilterOption(key="30d", label="30 дней"),
                FilterOption(key="90d", label="90 дней"),
            ],
            card_statuses=card_statuses,
            trust_states=[
                FilterOption(
                    key=TRUST_STATE_FINANCIAL_FINAL, label="Финально подтвержденные"
                ),
                FilterOption(
                    key=TRUST_STATE_OPERATIONAL_PROVISIONAL,
                    label="Операционно предварительные",
                ),
                FilterOption(key=TRUST_STATE_TEST_ONLY, label="Только тестовые данные"),
                FilterOption(key=TRUST_STATE_BLOCKED, label="Данные заблокированы"),
            ],
            action_types=action_types,
            brands=[FilterOption(key=item, label=item) for item in brands],
            subjects=[FilterOption(key=item, label=item) for item in subjects],
            sort_options=[
                FilterOption(key="priority_score", label="Приоритет"),
                FilterOption(key="revenue", label="Выручка"),
                FilterOption(key="profit", label="Прибыль"),
                FilterOption(key="margin", label="Маржа"),
                FilterOption(key="stock_value", label="Стоимость остатка"),
                FilterOption(key="days_of_stock", label="Дней остатка"),
                FilterOption(key="ad_spend", label="Рекламные расходы"),
                FilterOption(key="drr", label="Доля рекламы в выручке"),
            ],
            presets=[
                FilterOption(key="all", label="Все"),
                FilterOption(key="data_blocked", label="Сначала исправить данные"),
                FilterOption(key="profit", label="Прибыльные карточки"),
                FilterOption(key="loss", label="Убыточные карточки"),
                FilterOption(key="stock_risk", label="Риск по остаткам"),
            ],
        )
