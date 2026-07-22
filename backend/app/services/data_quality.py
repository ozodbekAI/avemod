from __future__ import annotations

import csv
from collections import defaultdict
from io import StringIO
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.action_registry import get_action
from app.core.current_state import orders_current_subquery, sales_current_subquery
from app.core.issue_refs import extract_issue_refs
from app.core.parsing import parse_datetime
from app.core.time import utcnow
from app.models.accounts import WBAPICategory, WBAPIToken, WBAccount
from app.models.ads import WBAdStatsDaily
from app.models.control_tower import UserBusinessSetting
from app.models.data_quality import DataQualityIssue
from app.models.finance import WBRealizationReportRow
from app.models.manual_costs import ManualCost, ManualCostUpload
from app.models.orders import WBOrder
from app.models.marts import (
    MartExpenseDaily,
    MartFinanceReconciliation,
    MartSKUDaily,
    MartStockDaily,
)
from app.models.operator import ResultEvent
from app.models.prices import WBPriceQuarantine, WBPriceSnapshot
from app.models.product_cards import CoreSKU, WBProductCard, WBProductCardSize
from app.models.sales import WBSale
from app.models.stocks import WBStockSnapshotRow
from app.models.supplies import WBSupplyGood
from app.models.sync import WBSyncCursor, WBSyncRun
from app.core.pagination import Page
from app.repositories.data_quality import DataQualityRepository
from app.schemas.data_quality import (
    DataQualityIssueRead,
    DataQualityIssueRecheckResponse,
    DataQualityResolutionContext,
    GuidedFixActionRequest,
    GuidedFixActionResponse,
    GuidedFixDefinition,
    GuidedFixSourceFact,
    ISSUE_BUCKET_META,
    build_problem_resolver,
    issue_fixability_contract,
    issue_bucket_meta,
    issue_is_operational_only_non_final,
    issue_resolution_guide,
)
from app.schemas.evidence import safe_sample_row
from app.services.marts import MartService


def _guided_definition(
    *,
    owner_type: str,
    can_user_fix_inside_platform: bool,
    fix_component_type: str,
    required_inputs: list[str],
    source_tables: list[str],
    preview: str,
    action_type: str,
    action_label: str,
    recheck: str,
    success: str,
    failure: str,
    safety_notes: list[str] | None = None,
    apply_endpoint: str = "POST /api/v1/dq/issues/{id}/guided-action",
    apply_allowed: bool | None = None,
    apply_description: str | None = None,
) -> dict[str, object]:
    resolved_apply_allowed = (
        can_user_fix_inside_platform if apply_allowed is None else apply_allowed
    )
    return {
        "owner_type": owner_type,
        "can_user_fix_inside_platform": can_user_fix_inside_platform,
        "fix_component_type": fix_component_type,
        "required_inputs": required_inputs,
        "affected_rows_query": {
            "endpoint": "GET /api/v1/dq/issues/{id}/resolution-context",
            "filters": ["account_id", "code", "sku_id", "nm_id", "entity_key"],
            "source_tables": source_tables,
            "limit": 50,
        },
        "preview_before_change": {
            "available": True,
            "description": preview,
            "shows": [
                "current issue row",
                "matched source rows",
                "safe payload fields",
            ],
        },
        "apply_action": {
            "type": action_type,
            "label": action_label,
            "method": "POST",
            "endpoint": apply_endpoint,
            "allowed": resolved_apply_allowed,
            "description": apply_description or action_label,
            "forbidden": ["manual_edit_wb_finance_facts"],
        },
        "recheck_query": {
            "endpoint": "POST /api/v1/dq/issues/{id}/guided-action",
            "action_type": "trigger_recheck",
            "rule": recheck,
        },
        "success_state": {"state": "closed_or_classified", "description": success},
        "failure_state": {"state": "still_open", "description": failure},
        "safety_notes": safety_notes or [],
    }


_NO_WB_FACT_EDIT_NOTE = "WB financial facts are read-only in Data Fix. Re-sync, reconcile, or investigate imports instead of editing facts to fit totals."

GUIDED_FIX_DEFINITIONS: dict[str, dict[str, object]] = {
    "missing_manual_cost": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="cost_inline_editor",
        required_inputs=["Себестоимость", "Прочие расходы", "SKU/nmId/артикул"],
        source_tables=["manual_costs", "core_sku", "mart_sku_daily"],
        preview="Показывает карточки/SKU, где не хватает себестоимости, чтобы заполнить цену прямо в платформе.",
        action_type="save_costs_inline",
        action_label="Сохранить себестоимость",
        recheck="After cost upload/confirmation, rerun DQ checks and verify the SKU has trusted manual cost.",
        success="The SKU/card has confirmed cost and missing_manual_cost disappears.",
        failure="Cost row is still absent, unresolved, ambiguous, or not trusted.",
        apply_endpoint="POST /api/v1/costs/inline-save",
        apply_description="Save safe local manual-cost rows through the Costs inline-save endpoint, then run Data Fix re-check.",
    ),
    "missing_cost_blocks_profit": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="cost_inline_editor",
        required_inputs=["Себестоимость", "Прочие расходы", "SKU/nmId/артикул"],
        source_tables=["manual_costs", "core_sku", "mart_sku_daily"],
        preview="Показывает карточки/SKU, где отсутствующая себестоимость блокирует расчет прибыли.",
        action_type="save_costs_inline",
        action_label="Сохранить себестоимость",
        recheck="After cost upload/confirmation, rerun DQ checks and verify the SKU has trusted manual cost.",
        success="The SKU/card has confirmed cost and missing_cost_blocks_profit disappears.",
        failure="Cost row is still absent, unresolved, ambiguous, or not trusted.",
        apply_endpoint="POST /api/v1/costs/inline-save",
        apply_description="Save safe local manual-cost rows through the Costs inline-save endpoint, then run Data Fix re-check.",
    ),
    "seller_other_expense_missing": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="cost_inline_editor",
        required_inputs=["Прочие расходы", "SKU/nmId/артикул"],
        source_tables=["manual_costs", "core_sku", "mart_sku_daily"],
        preview="Показывает карточки/SKU, где обязательные прочие расходы продавца не заполнены.",
        action_type="save_costs_inline",
        action_label="Сохранить прочие расходы",
        recheck="After seller other expense is filled, rerun DQ checks and rebuild profitability marts.",
        success="Seller other expense is explicitly filled with a real value or 0 and the issue disappears.",
        failure="Seller other expense is still empty or the row is not trusted.",
        apply_endpoint="POST /api/v1/costs/inline-save",
        apply_description="Save seller_other_expense through the Costs inline-save endpoint, then run Data Fix re-check.",
    ),
    "manual_cost_unresolved_sku": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="sku_mapping",
        required_inputs=["mapped_sku_id", "reason"],
        source_tables=["manual_costs", "core_sku"],
        preview="Shows the unresolved manual cost row and candidate SKU identifiers.",
        action_type="map_sku",
        action_label="Map manual cost row to SKU",
        recheck="After SKU mapping, rerun DQ checks and cost marts.",
        success="The manual cost row maps to exactly one SKU.",
        failure="The mapping is missing, invalid, or points to an inactive/incorrect SKU.",
    ),
    "manual_cost_ambiguous_match": _guided_definition(
        owner_type="mixed",
        can_user_fix_inside_platform=True,
        fix_component_type="sku_mapping",
        required_inputs=["mapped_sku_id", "why this SKU is correct"],
        source_tables=["manual_costs", "core_sku"],
        preview="Shows ambiguous cost matches and the candidate SKU list.",
        action_type="map_sku",
        action_label="Choose the correct SKU",
        recheck="After selecting one SKU, rerun DQ checks and cost marts.",
        success="The ambiguous row has one confirmed SKU.",
        failure="Multiple possible matches remain or the selected SKU is not trusted.",
    ),
    "unmatched_sku": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="sku_mapping",
        required_inputs=["mapped_sku_id", "source identifier checked by user"],
        source_tables=[
            "core_sku",
            "manual_costs",
            "mart_sku_daily",
            "wb_sales",
            "wb_orders",
            "wb_stock_snapshot_rows",
        ],
        preview="Shows the unmapped SKU/nm/barcode/vendor code and nearby catalog candidates.",
        action_type="map_sku",
        action_label="Map source row to catalog SKU",
        recheck="After mapping, rerun DQ checks and confirm no open unmatched_sku remains for this entity.",
        success="The source identifier is attached to a catalog SKU.",
        failure="The source identifier still cannot be mapped or candidates conflict.",
    ),
    "expense_unclassified": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="expense_classification",
        required_inputs=["expense_category", "classification_reason"],
        source_tables=["mart_expense_daily", "wb_realization_report_rows"],
        preview="Shows the unclassified expense row, source field, operation name and amount.",
        action_type="classify_expense",
        action_label="Classify expense",
        recheck="After classifying, rerun DQ checks and verify expense_data_quality is clean.",
        success="The expense has a stable category and is included in profit correctly.",
        failure="The category is missing or the source field still has no taxonomy mapping.",
    ),
    "unclassified_finance_expense": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="expense_classification",
        required_inputs=["expense_category", "classification_reason"],
        source_tables=["mart_expense_daily", "wb_realization_report_rows"],
        preview="Shows the unclassified finance-report expense row and its raw operation fields.",
        action_type="classify_expense",
        action_label="Classify finance expense",
        recheck="After classifying, rerun DQ checks and expense marts.",
        success="The finance expense has a stable category and no longer blocks final profit.",
        failure="The source field still resolves to unknown expense category.",
    ),
    "ad_spend_without_sku": _guided_definition(
        owner_type="mixed",
        can_user_fix_inside_platform=True,
        fix_component_type="ads_allocation_status",
        required_inputs=["sync/recheck confirmation"],
        source_tables=["wb_ad_stats_daily", "mart_sku_daily", "mart_expense_daily"],
        preview="Shows ad spend rows that could not be allocated to a product card.",
        action_type="trigger_recheck",
        action_label="Re-sync ads and re-check allocation",
        recheck="Rerun ad sync/DQ checks and verify ad spend has nm_id/sku allocation or admin investigation is opened.",
        success="Ad spend is allocated or explicitly marked admin-only.",
        failure="Ad spend remains unallocated after sync and needs mapping/integration investigation.",
    ),
    "ads_overallocated_to_profitability": _guided_definition(
        owner_type="admin",
        can_user_fix_inside_platform=False,
        fix_component_type="ads_allocation_status",
        required_inputs=["admin investigation note"],
        source_tables=["mart_sku_daily", "mart_expense_daily", "wb_ad_stats_daily"],
        preview="Shows ad allocation rows where profitability may receive too much ad spend.",
        action_type="mark_admin_investigation",
        action_label="Open admin investigation",
        recheck="Admin verifies allocation formula and reruns mart/DQ checks.",
        success="Ad allocation no longer overstates product spend.",
        failure="Allocation still exceeds source totals or cannot be explained.",
    ),
    "ads_not_allocated_to_profitability": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="ads_allocation_status",
        required_inputs=["recheck or admin investigation"],
        source_tables=["mart_sku_daily", "mart_expense_daily", "wb_ad_stats_daily"],
        preview="Показывает рекламные расходы, которые пока не попали в прибыль карточек.",
        action_type="trigger_recheck",
        action_label="Перепроверить аллокацию рекламы",
        recheck="Rerun ad allocation and verify source ad spend is either allocated or safely reported as unallocated.",
        success="Ad spend is allocated once or explicitly left unallocated without double counting.",
        failure="Allocation is still missing and needs admin/integration investigation.",
        safety_notes=[_NO_WB_FACT_EDIT_NOTE],
    ),
    "expense_ad_double_count_risk": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="ads_allocation_status",
        required_inputs=["recheck or admin investigation"],
        source_tables=[
            "mart_expense_daily",
            "mart_sku_daily",
            "wb_realization_report_rows",
            "wb_ad_stats_daily",
        ],
        preview="Показывает риск, что рекламный расход может быть учтен и в WB finance, и в рекламной загрузке.",
        action_type="trigger_recheck",
        action_label="Перепроверить защиту от двойного учета",
        recheck="Rerun expenses/ads/profitability checks and verify ad spend is not subtracted twice.",
        success="Advertising spend is taken from one source and duplicate excess is ignored.",
        failure="Double-count risk remains and needs admin review.",
        safety_notes=[_NO_WB_FACT_EDIT_NOTE],
    ),
    "stock_without_sales": _guided_definition(
        owner_type="business",
        can_user_fix_inside_platform=True,
        fix_component_type="stock_decision",
        required_inputs=["business stock decision"],
        source_tables=["mart_stock_daily", "mart_sku_daily"],
        preview="Показывает остатки, по которым нет подтвержденного спроса.",
        action_type="mark_admin_investigation",
        action_label="Зафиксировать решение по остатку",
        recheck="After decision or stock update, rerun stock/DQ checks.",
        success="Stock starts selling, decreases, is handled by a business action, or the data issue disappears after recheck.",
        failure="Stock remains without sales and no decision is recorded.",
    ),
    "sales_without_stock": _guided_definition(
        owner_type="business",
        can_user_fix_inside_platform=True,
        fix_component_type="stock_decision",
        required_inputs=["availability or replenishment decision"],
        source_tables=["mart_stock_daily", "mart_sku_daily"],
        preview="Показывает продажи, для которых нет свежего подтвержденного остатка.",
        action_type="trigger_recheck",
        action_label="Обновить остатки или зафиксировать действие",
        recheck="After stock sync or business decision, rerun stock/DQ checks.",
        success="Fresh stock appears, a replenishment/availability task is recorded, or the warning disappears.",
        failure="Sales remain without confirmed stock after recheck.",
    ),
    "stocks_task_not_ready": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="sync_recheck",
        required_inputs=["sync status"],
        source_tables=["wb_sync_runs", "wb_stock_snapshots"],
        preview="Показывает, что последняя загрузка остатков еще не завершилась.",
        action_type="mark_system_wait",
        action_label="Отметить ожидание sync",
        recheck="Wait for stock sync completion, then rerun stock/DQ checks.",
        success="A completed stock snapshot exists and the issue disappears.",
        failure="Stock sync is still running or failed.",
    ),
    "stocks_task_failed": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="sync_recheck",
        required_inputs=["sync retry or admin investigation"],
        source_tables=["wb_sync_runs", "wb_stock_snapshots"],
        preview="Показывает, что последняя загрузка остатков завершилась ошибкой.",
        action_type="mark_admin_investigation",
        action_label="Повторить sync или передать администратору",
        recheck="Retry stock sync, then rerun stock/DQ checks.",
        success="A completed stock snapshot exists and the issue disappears.",
        failure="Stock sync keeps failing and needs admin investigation.",
    ),
    "finance_reconciliation_mismatch": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="admin_investigation",
        required_inputs=["sync run or admin reconciliation note"],
        source_tables=[
            "mart_finance_reconciliation",
            "wb_sales",
            "wb_realization_report_rows",
        ],
        preview="Shows sales/finance rows used in reconciliation and their deltas.",
        action_type="mark_admin_investigation",
        action_label="Open finance reconciliation",
        recheck="Rerun finance/sales sync, rebuild reconciliation mart, then verify deltas are explained.",
        success="Sales and WB finance rows match or the mismatch is marked as expected system lag.",
        failure="Mismatch remains after sync and needs import/deduplication investigation.",
        safety_notes=[_NO_WB_FACT_EDIT_NOTE],
    ),
    "sale_without_finance": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="sync_recheck",
        required_inputs=["next WB finance report or sync run"],
        source_tables=[
            "mart_finance_reconciliation",
            "wb_sales",
            "wb_realization_report_rows",
        ],
        preview="Shows sale rows waiting for a matching WB finance report row.",
        action_type="mark_system_wait",
        action_label="Mark as WB report wait",
        recheck="Wait for the next WB finance report, rerun sync, then verify the sale has finance rows.",
        success="WB finance report row arrives and closes the reconciliation issue.",
        failure="The sale is still unmatched after the expected WB reporting window.",
        safety_notes=[_NO_WB_FACT_EDIT_NOTE],
    ),
    "finance_without_sale": _guided_definition(
        owner_type="system",
        can_user_fix_inside_platform=False,
        fix_component_type="sync_recheck",
        required_inputs=["sales/orders sync run"],
        source_tables=[
            "mart_finance_reconciliation",
            "wb_sales",
            "wb_orders",
            "wb_realization_report_rows",
        ],
        preview="Shows finance rows waiting for a matching operational sale/order row.",
        action_type="mark_system_wait",
        action_label="Mark as source-data wait",
        recheck="Rerun sales/orders sync, rebuild reconciliation, then verify the finance row is matched.",
        success="Operational sale/order row appears and reconciles with WB finance.",
        failure="The finance row remains unmatched after sync.",
        safety_notes=[_NO_WB_FACT_EDIT_NOTE],
    ),
    "price_jump": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=False,
        fix_component_type="review_price",
        required_inputs=["price review result", "comment"],
        source_tables=["wb_price_snapshots", "mart_sku_daily"],
        preview="Shows latest price snapshots and the size of the price change.",
        action_type="review_price",
        action_label="Confirm or flag price change",
        recheck="After review or a new price sync, verify current price is valid.",
        success="The price change is confirmed or corrected in the source and no longer appears as a data issue.",
        failure="The price remains unexplained, zero, or outside configured safety bounds.",
        apply_allowed=False,
        apply_description="Check-only: Data Fix can show evidence and request re-check, but it must not change WB prices.",
        safety_notes=[
            "Data Fix does not auto-change WB prices for price_jump. Confirm or correct prices in a safe price workflow, then re-check."
        ],
    ),
    "price_zero_or_too_low": _guided_definition(
        owner_type="user",
        can_user_fix_inside_platform=True,
        fix_component_type="review_price",
        required_inputs=["price review result", "expected price or comment"],
        source_tables=["wb_price_snapshots", "mart_sku_daily"],
        preview="Shows current price and recent revenue rows for the card.",
        action_type="review_price",
        action_label="Review suspicious price",
        recheck="After source price correction or confirmation, rerun price/DQ checks.",
        success="Price is corrected or explicitly confirmed as intentional.",
        failure="Price remains zero/too low or cannot be verified.",
    ),
    "missing_chrt_id": _guided_definition(
        owner_type="admin",
        can_user_fix_inside_platform=False,
        fix_component_type="card_mapping",
        required_inputs=["trusted card sync or admin mapping"],
        source_tables=["core_sku", "wb_product_card_sizes"],
        preview="Shows the card variant missing chrt_id and nearby SKU/card identifiers.",
        action_type="mark_admin_investigation",
        action_label="Open card sync/admin mapping",
        recheck="After card/catalog sync or mapping, verify the variant has chrt_id.",
        success="The size variant has chrt_id and card analytics can group sizes.",
        failure="The variant still lacks chrt_id after catalog sync.",
    ),
}


class DataQualityService:
    MAX_ISSUES_PER_CODE = 200
    MIN_AD_SPEND_WITHOUT_SALES = Decimal("100")
    CLASSIFIED_STATUSES = {
        "classified",
        "ignored",
        "ignored_with_reason",
        "mapped",
        "archived",
    }
    DEFAULT_CLASSIFICATION_STATUS = "unclassified"
    FINAL_BLOCKER_NON_BLOCKING_CLASSIFICATIONS = {
        "expected_lag",
        "known_exception",
        "ignored_non_financial",
        "ignored",
        "ignored_with_reason",
        "archived",
    }
    CLASSIFICATION_STATUSES = {
        DEFAULT_CLASSIFICATION_STATUS,
        "expected_lag",
        "known_exception",
        "real_issue",
        "resolved_by_data",
        "ignored_non_financial",
        "detected",
        "mapped",
        "archived",
        "ignored_with_reason",
        "classified",
    }
    FINANCIAL_FINAL_FILTER_SEVERITIES = {"error", "warning", "critical"}
    HIDDEN_USER_ISSUE_CODES = {"finance_reconciliation_mismatch"}
    ISSUE_GROUP_MAP = {
        "sku_mapping": {"unmatched_sku", "missing_chrt_id"},
        "finance_mismatch": {
            "finance_without_sale",
            "sale_without_finance",
            "order_without_sale_or_return",
        },
        "stock_issues": {
            "sales_without_stock",
            "stock_without_sales",
            "stocks_task_not_ready",
        },
        "manual_costs": {
            "missing_manual_cost",
            "manual_cost_overlap",
            "manual_cost_linked_to_inactive_sku",
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "manual_cost_old_fields_used",
            "seller_other_expense_missing",
        },
        "ad_reconciliation": {
            "ad_spend_without_sales",
            "ad_spend_without_sku",
            "expense_ad_double_count_risk",
        },
        "expense_accounting": {
            "expense_unclassified",
            "unclassified_finance_expense",
            "expense_logistics_missing",
            "expense_finance_report_missing",
            "expense_negative_unexpected",
            "expense_large_logistics_share",
            "expense_no_drilldown_rows",
        },
        "sync_issues": {
            "failed_sync_domains",
            "missed_load",
            "scheduler_instability",
            "sync_date_mismatch",
        },
    }
    SYNC_DATE_ALIGNMENT_RULES: tuple[dict[str, object], ...] = (
        {
            "key": "sales_orders",
            "label": "Sales / orders",
            "domains": ("sales", "orders"),
            "max_delta_hours": 2,
        },
        {
            "key": "money_sources",
            "label": "Money sources",
            "domains": ("sales", "orders", "finance"),
            "max_delta_hours": 36,
        },
        {
            "key": "stock_sales",
            "label": "Stock / sales",
            "domains": ("stocks", "sales"),
            "max_delta_hours": 12,
        },
        {
            "key": "ads_sales",
            "label": "Ads / sales",
            "domains": ("ads", "sales"),
            "max_delta_hours": 24,
        },
    )
    DEFAULT_LARGE_LOGISTICS_SHARE_THRESHOLD_PERCENT = Decimal("70")

    def __init__(self) -> None:
        self.repo = DataQualityRepository()
        self.marts = MartService()
        self._run_metrics: dict[str, int] | None = None

    async def _sync_dynamic_problem_instance(
        self, session: AsyncSession, issue: DataQualityIssue
    ):
        if not hasattr(session, "add"):
            return None
        from app.services.problem_engine.data_fix_bridge import DataFixProblemBridge

        try:
            return await DataFixProblemBridge().sync_issue(
                session,
                issue,
                guided_definition=self.guided_fix_definition_for_code(issue.code),
            )
        except AttributeError:
            return None

    @staticmethod
    def _dynamic_problem_ref(instance) -> dict[str, object] | None:
        if instance is None:
            return None
        return {
            "id": int(instance.id),
            "problem_code": str(instance.problem_code),
            "status": str(instance.status),
            "source_module": str(instance.source_module),
            "source_id": str(instance.id),
            "action_center_source_module": "problem_engine",
            "action_center_source_id": str(instance.id),
            "impact_type": str(instance.impact_type),
            "trust_state": str(instance.trust_state),
            "evidence_ledger": dict(instance.evidence_ledger_json or {}),
        }

    @classmethod
    def issue_bucket_meta(cls, code: str) -> dict[str, str | bool]:
        return issue_bucket_meta(code)

    @staticmethod
    def _normalize_multi_values(values: list[str] | None) -> list[str] | None:
        if not values:
            return None
        normalized: list[str] = []
        for value in values:
            if value is None:
                continue
            for item in str(value).split(","):
                item = item.strip()
                if item:
                    normalized.append(item)
        return list(dict.fromkeys(normalized)) or None

    @classmethod
    def _financial_final_blocker_codes(cls) -> set[str]:
        return {
            code
            for code, meta in ISSUE_BUCKET_META.items()
            if bool(meta.get("financial_final_blocker"))
            and code not in cls.HIDDEN_USER_ISSUE_CODES
        }

    @classmethod
    def _is_hidden_user_issue_code(cls, code: str | None) -> bool:
        return str(code or "").strip().lower() in cls.HIDDEN_USER_ISSUE_CODES

    @classmethod
    def _issue_group(cls, code: str) -> str:
        for group, codes in cls.ISSUE_GROUP_MAP.items():
            if code in codes:
                return group
        return "info_non_blocking"

    @classmethod
    def _normalize_classification_status(cls, value: str | None) -> str:
        normalized = str(value or cls.DEFAULT_CLASSIFICATION_STATUS).strip().lower()
        return normalized or cls.DEFAULT_CLASSIFICATION_STATUS

    @classmethod
    def _base_financial_final_blocker(
        cls, *, code: str | None, severity: str | None
    ) -> bool:
        return (
            str(code or "") in cls._financial_final_blocker_codes()
            and str(severity or "").lower() in cls.FINANCIAL_FINAL_FILTER_SEVERITIES
        )

    @staticmethod
    def _issue_payload(issue: DataQualityIssue) -> dict:
        return dict(issue.payload or {})

    @classmethod
    def _issue_source_domains(cls, issue: DataQualityIssue) -> set[str]:
        payload = cls._issue_payload(issue)
        value = payload.get("sourceDomains") or []
        if not isinstance(value, list):
            return set()
        return {str(item).strip().lower() for item in value if str(item).strip()}

    @classmethod
    def _issue_source_kind(cls, issue: DataQualityIssue) -> str:
        return str(cls._issue_payload(issue).get("sourceKind") or "").strip().lower()

    @classmethod
    def _issue_is_supply_source_unmatched(cls, issue: DataQualityIssue) -> bool:
        if str(getattr(issue, "code", None) or "").lower() != "unmatched_sku":
            return False
        payload = cls._issue_payload(issue)
        classification_reason = (
            str(payload.get("classificationReason") or "").strip().lower()
        )
        return (
            cls._issue_source_kind(issue) == "source_level"
            and cls._issue_source_domains(issue) == {"supplies"}
            and classification_reason in {"missing_nm_id", "source_level_missing_nm_id"}
        )

    @classmethod
    def _effective_financial_final_blocker_value(
        cls,
        *,
        code: str | None,
        severity: str | None,
        resolved_at: datetime | None,
        classification_status: str | None,
        financial_final_blocker_override: bool | None,
    ) -> bool:
        if resolved_at is not None:
            return False
        if financial_final_blocker_override is False:
            return False
        if financial_final_blocker_override is True:
            return True
        if not cls._base_financial_final_blocker(code=code, severity=severity):
            return False
        normalized_status = cls._normalize_classification_status(classification_status)
        return normalized_status not in cls.FINAL_BLOCKER_NON_BLOCKING_CLASSIFICATIONS

    @classmethod
    def _refresh_issue_final_blocker_state(cls, issue: DataQualityIssue) -> None:
        issue.effective_financial_final_blocker = (
            cls._effective_financial_final_blocker_value(
                code=issue.code,
                severity=issue.severity,
                resolved_at=issue.resolved_at,
                classification_status=issue.classification_status,
                financial_final_blocker_override=issue.financial_final_blocker_override,
            )
        )
        if issue_is_operational_only_non_final(
            str(getattr(issue, "code", None) or ""), getattr(issue, "payload", None)
        ):
            issue.effective_financial_final_blocker = False
        if cls._issue_is_supply_source_unmatched(issue):
            issue.effective_financial_final_blocker = False

    @classmethod
    def _issue_is_effective_financial_final_blocker(
        cls, issue: DataQualityIssue
    ) -> bool:
        if issue_is_operational_only_non_final(
            str(getattr(issue, "code", None) or ""), getattr(issue, "payload", None)
        ):
            return False
        if cls._issue_is_supply_source_unmatched(issue):
            return False
        stored = getattr(issue, "effective_financial_final_blocker", None)
        if stored is not None:
            return bool(stored)
        return cls._effective_financial_final_blocker_value(
            code=issue.code,
            severity=issue.severity,
            resolved_at=issue.resolved_at,
            classification_status=getattr(issue, "classification_status", None),
            financial_final_blocker_override=getattr(
                issue, "financial_final_blocker_override", None
            ),
        )

    @classmethod
    def _normalize_issue_runtime_flags(
        cls, issue: DataQualityIssue
    ) -> DataQualityIssue:
        issue.effective_financial_final_blocker = (
            cls._issue_is_effective_financial_final_blocker(issue)
        )
        return issue

    async def open_issue(
        self,
        session: AsyncSession,
        *,
        domain: str,
        code: str,
        message: str,
        account_id: int | None = None,
        severity: str = "warning",
        entity_key: str | None = None,
        entity_type: str | None = None,
        entity_id: int | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        source_table: str | None = None,
        payload: dict | None = None,
    ) -> DataQualityIssue:
        normalized_payload = payload or {}
        normalized_sku_id, normalized_nm_id = extract_issue_refs(
            sku_id=sku_id,
            nm_id=nm_id,
            entity_key=entity_key,
            payload=normalized_payload,
        )
        existing = await self.repo.get_open_issue(
            session,
            domain=domain,
            code=code,
            account_id=account_id,
            entity_key=entity_key,
        )
        if existing is not None:
            existing_payload = dict(existing.payload or {})
            merged_payload = dict(normalized_payload)
            existing_status = self._normalize_classification_status(
                existing.classification_status
            )
            incoming_status = self._normalize_classification_status(
                merged_payload.get("classificationStatus")
            )
            if (
                existing_status != self.DEFAULT_CLASSIFICATION_STATUS
                and incoming_status in {"detected", "classified"}
            ):
                merged_payload["classificationStatus"] = existing_status
                if existing.classification_reason:
                    merged_payload["classificationReason"] = (
                        existing.classification_reason
                    )
            for preserved_key in (
                "comments",
                "resolutionComment",
                "reopenComment",
                "classificationStatus",
                "classificationReason",
                "ageBucket",
                "sourceDomains",
                "candidateSkuIds",
            ):
                if (
                    preserved_key not in merged_payload
                    and preserved_key in existing_payload
                ):
                    merged_payload[preserved_key] = existing_payload[preserved_key]
            existing.message = message
            existing.payload = merged_payload
            existing.severity = severity
            existing.entity_type = entity_type
            existing.entity_id = entity_id
            existing.sku_id = normalized_sku_id
            existing.nm_id = normalized_nm_id
            existing.source_table = source_table
            existing.classification_status = (
                self._normalize_classification_status(
                    merged_payload.get("classificationStatus")
                )
                if merged_payload.get("classificationStatus") is not None
                else existing.classification_status
                or self.DEFAULT_CLASSIFICATION_STATUS
            )
            existing.classification_reason = (
                str(merged_payload.get("classificationReason"))
                if merged_payload.get("classificationReason") not in (None, "")
                else existing.classification_reason
            )
            existing.detected_at = utcnow()
            self._refresh_issue_final_blocker_state(existing)
            await session.flush()
            await self._sync_dynamic_problem_instance(session, existing)
            if self._run_metrics is not None:
                self._run_metrics["updated_count"] += 1
            return existing

        issue = DataQualityIssue(
            account_id=account_id,
            domain=domain,
            severity=severity,
            code=code,
            entity_key=entity_key,
            entity_type=entity_type,
            entity_id=entity_id,
            sku_id=normalized_sku_id,
            nm_id=normalized_nm_id,
            source_table=source_table,
            message=message,
            payload=normalized_payload,
            classification_status=self._normalize_classification_status(
                normalized_payload.get("classificationStatus")
            ),
            classification_reason=(
                str(normalized_payload.get("classificationReason"))
                if normalized_payload.get("classificationReason") not in (None, "")
                else None
            ),
            detected_at=utcnow(),
        )
        self._refresh_issue_final_blocker_state(issue)
        session.add(issue)
        await session.flush()
        await self._sync_dynamic_problem_instance(session, issue)
        if self._run_metrics is not None:
            self._run_metrics["opened_count"] += 1
        return issue

    async def get_issue(
        self, session: AsyncSession, *, issue_id: int
    ) -> DataQualityIssue | None:
        return await session.get(DataQualityIssue, issue_id)

    @classmethod
    def guided_fix_definition_for_code(cls, code: str | None) -> GuidedFixDefinition:
        normalized = str(code or "").strip().lower()
        payload = GUIDED_FIX_DEFINITIONS.get(normalized)
        if payload is None:
            payload = _guided_definition(
                owner_type="mixed",
                can_user_fix_inside_platform=False,
                fix_component_type="admin_investigation",
                required_inputs=["admin investigation note"],
                source_tables=["data_quality_issues"],
                preview="Shows the DQ issue row and safe payload fields for investigation.",
                action_type="mark_admin_investigation",
                action_label="Open investigation",
                recheck="After source data or mapping changes, rerun DQ checks and verify the issue is closed.",
                success="The issue disappears or is classified with a clear owner.",
                failure="The issue remains open and needs a deeper source-data investigation.",
            )
        definition = GuidedFixDefinition.model_validate(payload)
        contract = issue_fixability_contract(normalized)
        apply_action = {
            **dict(definition.apply_action or {}),
            **contract,
            "type": (definition.apply_action or {}).get("type")
            or contract["primary_action_code"],
            "label": (definition.apply_action or {}).get("label")
            or contract["primary_action_label"],
            "allowed": bool(
                contract["fixability"] == "fix_in_platform"
                and contract["can_user_fix_inside_platform"]
            ),
        }
        return definition.model_copy(
            update={
                "owner_type": contract["owner_type"],
                "can_user_fix_inside_platform": bool(
                    contract["can_user_fix_inside_platform"]
                ),
                "fixability": contract["fixability"],
                "issue_nature": contract["issue_nature"],
                "is_manual_edit_allowed": bool(contract["is_manual_edit_allowed"]),
                "primary_action_code": str(contract["primary_action_code"]),
                "primary_action_label": str(contract["primary_action_label"]),
                "target_href": str(contract["target_href"]),
                "disabled_reason": str(contract["disabled_reason"] or ""),
                "recheck_mode": str(contract["recheck_mode"]),
                "seller_explanation": str(contract["seller_explanation"]),
                "admin_explanation": str(contract["admin_explanation"]),
                "apply_action": apply_action,
            }
        )

    @staticmethod
    def _to_safe_row(source: str, values: dict[str, object]) -> dict[str, object]:
        return safe_sample_row({"_source": source, **values}, max_fields=32)

    @staticmethod
    def _payload_candidate_int(payload: dict, *keys: str) -> int | None:
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _payload_candidate_str(payload: dict, *keys: str) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @classmethod
    def _append_guided_fix_audit(
        cls,
        issue: DataQualityIssue,
        *,
        action_type: str,
        status: str,
        message: str,
        user_id: int | None = None,
        inputs: dict | None = None,
        comment: str | None = None,
    ) -> None:
        payload = dict(issue.payload or {})
        history = list(payload.get("guidedFixAudit") or [])
        history.append(
            safe_sample_row(
                {
                    "actionType": action_type,
                    "status": status,
                    "message": message,
                    "userId": user_id,
                    "inputs": inputs or {},
                    "comment": comment,
                    "createdAt": utcnow().isoformat(),
                },
                max_fields=16,
            )
        )
        payload["guidedFixAudit"] = history[-50:]
        issue.payload = payload

    @classmethod
    def _guided_fix_audit_history(
        cls, issue: DataQualityIssue
    ) -> list[dict[str, object]]:
        payload = dict(issue.payload or {})
        return [
            safe_sample_row(dict(item), max_fields=16)
            for item in (payload.get("guidedFixAudit") or [])
            if isinstance(item, dict)
        ]

    async def _record_linked_problem_recheck_requested(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        user_id: int | None,
        inputs: dict | None = None,
        comment: str | None = None,
    ) -> None:
        linked_problem = await self._sync_dynamic_problem_instance(session, issue)
        if linked_problem is None:
            return
        from app.models.problem_engine import ProblemInstanceHistory
        from app.services.result_tracking import ResultTrackingService

        payload = {
            "source": "data_fix",
            "data_quality_issue_id": issue.id,
            "issue_code": issue.code,
            "action_type": "trigger_recheck",
            "inputs": safe_sample_row(dict(inputs or {}), max_fields=16),
            "comment": comment,
        }
        session.add(
            ProblemInstanceHistory(
                problem_instance_id=linked_problem.id,
                event_type="recheck_requested",
                old_value_json={"status": linked_problem.status},
                new_value_json=payload,
                comment=comment or "Data Fix guided re-check requested.",
                actor_user_id=user_id,
            )
        )
        await session.flush()
        await ResultTrackingService().create_problem_recheck_event(
            session,
            problem_instance_id=linked_problem.id,
            created_by=user_id,
            status=linked_problem.status,
            message="Data Fix re-check requested. Result remains correlation-only until measured after-data exists.",
            payload={
                **payload,
                "after_snapshot": {
                    "status": linked_problem.status,
                    "problem_instance_id": linked_problem.id,
                    "problem_code": linked_problem.problem_code,
                    "data_quality_issue_id": issue.id,
                },
            },
        )

    async def recheck_issue(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        user_id: int | None = None,
        inputs: dict | None = None,
        comment: str | None = None,
    ) -> DataQualityIssueRecheckResponse:
        from fastapi import HTTPException
        from app.models.problem_engine import ProblemInstanceHistory

        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="Data quality issue not found")
        if issue.account_id is None:
            raise HTTPException(
                status_code=400,
                detail="Issue has no account_id; cannot run account DQ checks",
            )

        self._normalize_issue_runtime_flags(issue)
        before_rows, before_total = await self._affected_rows_for_issue(
            session, issue, limit=200, offset=0
        )
        affected_rows_count = self._recheck_affected_rows_count(
            before_rows, before_total
        )
        previous_state = self._recheck_issue_state(
            issue, affected_rows_count=affected_rows_count
        )
        linked_before = await self._sync_dynamic_problem_instance(session, issue)
        old_problem_status = (
            str(getattr(linked_before, "status", "") or "")
            if linked_before is not None
            else None
        )

        try:
            run_metrics = await self.run_checks(session, account_id=issue.account_id)
        except Exception as exc:
            return DataQualityIssueRecheckResponse(
                issue_id=int(issue.id),
                problem_instance_id=int(linked_before.id)
                if linked_before is not None
                else None,
                status="failed",
                previous_state=previous_state,
                new_state=previous_state,
                affected_rows_count=affected_rows_count,
                resolved_rows_count=0,
                still_missing_rows_count=affected_rows_count,
                result_status="not_enough_data",
                action_center_update=None,
                message=f"Data Fix re-check failed: {exc.__class__.__name__}",
            )

        refreshed = await session.get(DataQualityIssue, issue_id)
        target_issue = await self._find_recheck_target_issue(
            session, original=refreshed or issue
        )
        if target_issue is None:
            target_issue = refreshed or issue
        self._normalize_issue_runtime_flags(target_issue)
        after_rows, after_total = await self._affected_rows_for_issue(
            session, target_issue, limit=200, offset=0
        )
        still_missing_rows_count = (
            self._recheck_affected_rows_count(after_rows, after_total)
            if target_issue.resolved_at is None
            else 0
        )
        resolved_rows_count = max(affected_rows_count - still_missing_rows_count, 0)
        new_state = self._recheck_issue_state(
            target_issue, affected_rows_count=still_missing_rows_count
        )
        result_status = self._data_fix_recheck_result_status(
            previous_count=affected_rows_count,
            still_missing_count=still_missing_rows_count,
            source_resolved=target_issue.resolved_at is not None,
        )
        linked_problem = await self._sync_dynamic_problem_instance(
            session, target_issue
        )
        action_center_update = self._apply_data_fix_recheck_action_center_update(
            session,
            linked_problem,
            old_status=old_problem_status,
            result_status=result_status,
            still_missing_rows_count=still_missing_rows_count,
            user_id=user_id,
            comment=comment,
        )
        result_event_id = await self._record_data_fix_recheck_event(
            session,
            issue=target_issue,
            linked_problem=linked_problem,
            previous_state=previous_state,
            new_state=new_state,
            affected_rows_count=affected_rows_count,
            resolved_rows_count=resolved_rows_count,
            still_missing_rows_count=still_missing_rows_count,
            result_status=result_status,
            run_metrics=run_metrics,
            action_center_update=action_center_update,
            created_by=user_id,
            inputs=inputs,
            comment=comment,
        )
        self._append_guided_fix_audit(
            target_issue,
            action_type="trigger_recheck",
            status="ok",
            message="DQ re-check completed and result recorded.",
            user_id=user_id,
            inputs=inputs or {},
            comment=comment,
        )
        await session.flush()
        if linked_problem is not None:
            session.add(
                ProblemInstanceHistory(
                    problem_instance_id=linked_problem.id,
                    event_type="recheck_completed",
                    old_value_json={"status": old_problem_status, **previous_state},
                    new_value_json={
                        "status": linked_problem.status,
                        "result_status": result_status,
                        "still_missing_rows_count": still_missing_rows_count,
                    },
                    comment=comment or "Data Fix re-check completed.",
                    actor_user_id=user_id,
                )
            )
        return DataQualityIssueRecheckResponse(
            issue_id=int(issue.id),
            problem_instance_id=int(linked_problem.id)
            if linked_problem is not None
            else None,
            status="completed",
            previous_state=previous_state,
            new_state=new_state,
            affected_rows_count=affected_rows_count,
            resolved_rows_count=resolved_rows_count,
            still_missing_rows_count=still_missing_rows_count,
            result_status=result_status,  # type: ignore[arg-type]
            result_event_id=result_event_id,
            action_center_update=action_center_update,
            message="Data Fix re-check completed.",
        )

    async def _find_recheck_target_issue(
        self,
        session: AsyncSession,
        *,
        original: DataQualityIssue,
    ) -> DataQualityIssue | None:
        if original.resolved_at is None:
            return original
        filters = [
            DataQualityIssue.account_id == original.account_id,
            DataQualityIssue.code == original.code,
            DataQualityIssue.resolved_at.is_(None),
            DataQualityIssue.id != original.id,
        ]
        if original.entity_key:
            filters.append(DataQualityIssue.entity_key == original.entity_key)
        else:
            ref_filters = []
            if original.sku_id is not None:
                ref_filters.append(DataQualityIssue.sku_id == original.sku_id)
            if original.nm_id is not None:
                ref_filters.append(DataQualityIssue.nm_id == original.nm_id)
            if ref_filters:
                filters.append(or_(*ref_filters))
        return (
            await session.execute(
                select(DataQualityIssue)
                .where(*filters)
                .order_by(
                    DataQualityIssue.detected_at.desc(), DataQualityIssue.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    @staticmethod
    def _recheck_affected_rows_count(rows: list[dict[str, object]], total: int) -> int:
        has_issue_reference = any(
            str(row.get("source") or "") == "data_quality_issues" for row in rows
        )
        return max(int(total or 0) - (1 if has_issue_reference else 0), 0)

    def _recheck_issue_state(
        self, issue: DataQualityIssue, *, affected_rows_count: int
    ) -> dict[str, object]:
        return {
            "issue_id": int(issue.id),
            "state": "resolved" if issue.resolved_at is not None else "open",
            "code": str(issue.code or ""),
            "classification_status": self._normalize_classification_status(
                issue.classification_status
            ),
            "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
            "effective_financial_final_blocker": self._issue_is_effective_financial_final_blocker(
                issue
            ),
            "affected_rows_count": affected_rows_count,
            "still_missing_rows_count": 0
            if issue.resolved_at is not None
            else affected_rows_count,
        }

    @staticmethod
    def _data_fix_recheck_result_status(
        *,
        previous_count: int,
        still_missing_count: int,
        source_resolved: bool,
    ) -> str:
        if source_resolved and still_missing_count == 0:
            return "improved"
        if previous_count <= 0:
            return "not_enough_data"
        if still_missing_count < previous_count:
            return "improved"
        if still_missing_count > previous_count:
            return "worse"
        return "neutral"

    def _apply_data_fix_recheck_action_center_update(
        self,
        session: AsyncSession,
        linked_problem,
        *,
        old_status: str | None,
        result_status: str,
        still_missing_rows_count: int,
        user_id: int | None,
        comment: str | None,
    ) -> dict[str, object] | None:
        if linked_problem is None:
            return None
        now = utcnow()
        source_resolved = still_missing_rows_count == 0 and result_status == "improved"
        previous_status = str(linked_problem.status or "")
        if source_resolved:
            linked_problem.status = "resolved"
            linked_problem.resolved_at = linked_problem.resolved_at or now
        elif previous_status in {"done", "resolved"}:
            linked_problem.status = "reopened"
            linked_problem.resolved_at = None
            linked_problem.dismissed_at = None
            linked_problem.dismiss_reason = None
        snapshot = dict(linked_problem.calculation_snapshot_json or {})
        action_state = (
            dict(snapshot.get("action_center") or {})
            if isinstance(snapshot.get("action_center"), dict)
            else {}
        )
        review_status = (
            "done"
            if source_resolved
            else "blocked"
            if still_missing_rows_count > 0
            else "in_progress"
        )
        result_badge = (
            "resolved_after_recheck"
            if source_resolved
            else "still_blocked_after_recheck"
            if still_missing_rows_count > 0
            else "not_enough_data_after_recheck"
        )
        action_state.update(
            {
                "review_status": review_status,
                "result_badge": result_badge,
                "last_recheck_at": now.isoformat(),
                "last_changed_at": now.isoformat(),
                "last_status_changed_at": now.isoformat(),
                "last_actor_user_id": user_id,
                "last_changed_by_user_id": user_id,
                "status_reason": comment or result_badge,
                "still_missing_rows_count": still_missing_rows_count,
            }
        )
        if source_resolved:
            action_state["closed_at"] = now.isoformat()
        else:
            action_state.pop("closed_at", None)
        snapshot["action_center"] = action_state
        linked_problem.calculation_snapshot_json = snapshot
        return {
            "problem_instance_id": int(linked_problem.id),
            "old_status": old_status,
            "new_status": str(linked_problem.status or ""),
            "review_status": review_status,
            "result_badge": result_badge,
            "still_missing_rows_count": still_missing_rows_count,
        }

    async def _record_data_fix_recheck_event(
        self,
        session: AsyncSession,
        *,
        issue: DataQualityIssue,
        linked_problem,
        previous_state: dict[str, object],
        new_state: dict[str, object],
        affected_rows_count: int,
        resolved_rows_count: int,
        still_missing_rows_count: int,
        result_status: str,
        run_metrics: dict[str, int],
        action_center_update: dict[str, object] | None,
        created_by: int | None,
        inputs: dict | None,
        comment: str | None,
    ) -> int | None:
        before_snapshot = {
            "problem_instance_id": int(linked_problem.id)
            if linked_problem is not None
            else None,
            "data_quality_issue_id": int(issue.id),
            "source_module": "data_quality",
            "open_issue_count": 1 if previous_state.get("state") == "open" else 0,
            "still_missing_rows_count": affected_rows_count,
            "affected_rows_count": affected_rows_count,
        }
        after_snapshot = {
            "problem_instance_id": int(linked_problem.id)
            if linked_problem is not None
            else None,
            "data_quality_issue_id": int(issue.id),
            "source_module": "data_quality",
            "open_issue_count": 0
            if new_state.get("state") == "resolved" and still_missing_rows_count == 0
            else 1,
            "still_missing_rows_count": still_missing_rows_count,
            "affected_rows_count": still_missing_rows_count,
        }
        comparison = {
            "outcome": result_status
            if result_status in {"improved", "worse", "neutral"}
            else "not_enough_data",
            "metrics": {
                "open_issue_count": {
                    "before": before_snapshot["open_issue_count"],
                    "after": after_snapshot["open_issue_count"],
                    "delta": int(after_snapshot["open_issue_count"])
                    - int(before_snapshot["open_issue_count"]),
                    "direction": (
                        "improved"
                        if int(after_snapshot["open_issue_count"])
                        < int(before_snapshot["open_issue_count"])
                        else "worse"
                        if int(after_snapshot["open_issue_count"])
                        > int(before_snapshot["open_issue_count"])
                        else "neutral"
                    ),
                },
                "still_missing_rows_count": {
                    "before": affected_rows_count,
                    "after": still_missing_rows_count,
                    "delta": still_missing_rows_count - affected_rows_count,
                    "direction": (
                        "improved"
                        if still_missing_rows_count < affected_rows_count
                        else "worse"
                        if still_missing_rows_count > affected_rows_count
                        else "neutral"
                    ),
                },
            },
            "causality": "not_claimed",
        }
        event = ResultEvent(
            account_id=int(issue.account_id),
            problem_instance_id=int(linked_problem.id)
            if linked_problem is not None
            else None,
            problem_code=str(
                getattr(linked_problem, "problem_code", None) or issue.code or ""
            ),
            source_module="data_quality",
            source_id=str(issue.id),
            external_id=str(issue.id),
            nm_id=issue.nm_id,
            event_type="recheck_result",
            status=result_status,
            message=comment or "Data Fix re-check completed.",
            payload_json={
                "source_module": "data_quality",
                "source": "data_fix",
                "data_quality_issue_id": int(issue.id),
                "problem_instance_id": int(linked_problem.id)
                if linked_problem is not None
                else None,
                "issue_code": issue.code,
                "before_snapshot": before_snapshot,
                "after_snapshot": after_snapshot,
                "comparison": comparison,
                "outcome": comparison["outcome"],
                "previous_state": previous_state,
                "new_state": new_state,
                "affected_rows_count": affected_rows_count,
                "resolved_rows_count": resolved_rows_count,
                "still_missing_rows_count": still_missing_rows_count,
                "run_metrics": run_metrics,
                "action_center_update": action_center_update,
                "inputs": safe_sample_row(dict(inputs or {}), max_fields=16),
                "comment": comment,
                "created_by": created_by,
                "saved_money_claimed": False,
            },
        )
        session.add(event)
        await session.flush()
        return int(event.id) if event.id is not None else None

    def _issue_identifiers(self, issue: DataQualityIssue) -> dict[str, object]:
        payload = dict(issue.payload or {})
        entity_key = str(issue.entity_key or "")
        return {
            "payload": payload,
            "nm_id": issue.nm_id
            or self._payload_candidate_int(payload, "nmId", "nm_id"),
            "sku_id": issue.sku_id
            or self._payload_candidate_int(payload, "skuId", "sku_id", "mappedSkuId"),
            "vendor_code": self._payload_candidate_str(
                payload, "vendorCode", "vendor_code"
            ),
            "barcode": self._payload_candidate_str(payload, "barcode"),
            "manual_cost_id": self._payload_candidate_int(
                payload, "manualCostId", "manual_cost_id"
            ),
            "source_field": self._payload_candidate_str(
                payload, "sourceField", "source_field"
            ),
            "srid": (
                self._payload_candidate_str(payload, "srid", "sridId")
                or (
                    entity_key.split(":", 1)[1]
                    if entity_key.startswith("srid:")
                    else entity_key or None
                )
            ),
        }

    @classmethod
    def _issue_reference_row(cls, issue: DataQualityIssue) -> dict[str, object]:
        payload = dict(issue.payload or {})
        whitelisted_payload = {
            key: payload.get(key)
            for key in (
                "nmId",
                "skuId",
                "vendorCode",
                "barcode",
                "statDate",
                "sourceKind",
                "sourceDomains",
                "candidateSkuIds",
                "manualCostId",
                "srid",
                "rows",
                "affectedAmount",
                "affectedRevenue",
                "currentPrice",
                "currentDiscountedPrice",
                "previousPrice",
                "changePercent",
                "revenueDelta",
                "forPayDelta",
            )
            if payload.get(key) is not None
        }
        return cls._to_safe_row(
            "data_quality_issues",
            {
                "id": issue.id,
                "account_id": issue.account_id,
                "code": issue.code,
                "domain": issue.domain,
                "severity": issue.severity,
                "entity_key": issue.entity_key,
                "entity_type": issue.entity_type,
                "entity_id": issue.entity_id,
                "sku_id": issue.sku_id,
                "nm_id": issue.nm_id,
                "source_table": issue.source_table,
                "message": issue.message,
                **whitelisted_payload,
            },
        )

    @staticmethod
    def _slice_rows(
        rows: list[dict[str, object]],
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[dict[str, object]], int]:
        safe_limit = max(1, min(int(limit or 50), 200))
        safe_offset = max(0, int(offset or 0))
        return rows[safe_offset : safe_offset + safe_limit], len(rows)

    @staticmethod
    def _query_cap(limit: int, offset: int) -> int:
        return max(50, min(max(limit + offset, limit), 500))

    @staticmethod
    def _frontend_href(path: str, **params: object) -> str:
        query = {
            key: value for key, value in params.items() if value not in (None, "", [])
        }
        if not query:
            return path
        return f"{path}?{urlencode(query)}"

    @staticmethod
    def _resolution_owner_type(owner_type: str | None) -> str:
        normalized = str(owner_type or "").strip().lower()
        if normalized in {
            "seller",
            "operator",
            "admin",
            "system",
            "waiting",
            "business",
        }:
            return normalized
        if normalized == "user":
            return "operator"
        if normalized == "mixed":
            return "operator"
        return "admin"

    @staticmethod
    def _normal_row_value(row: dict[str, object], *keys: str) -> object | None:
        for key in keys:
            value = row.get(key)
            if value not in (None, ""):
                return value
        return None

    def _suggested_fix_for_row(
        self, issue: DataQualityIssue, row: dict[str, object]
    ) -> dict[str, object]:
        code = str(issue.code or "").strip().lower()
        issue_id = getattr(issue, "id", None)
        if code in {
            "missing_manual_cost",
            "missing_cost_blocks_profit",
            "seller_other_expense_missing",
        }:
            return {
                "action_type": "save_costs_inline",
                "endpoint": "POST /api/v1/costs/inline-save",
                "next_recheck_endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
                "required_inputs": ["account_id", "rows[].sku_id", "rows[].cost_price"],
            }
        if code in {
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "unmatched_sku",
        }:
            return {
                "action_type": "map_sku",
                "endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
                "required_inputs": ["mapped_sku_id", "reason"],
            }
        if code in {"expense_unclassified", "unclassified_finance_expense"}:
            return {
                "action_type": "classify_expense",
                "endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
                "required_inputs": ["expense_category", "classification_reason"],
            }
        if code == "price_jump":
            return {
                "action_type": "check_price_only",
                "endpoint": "/pricing",
                "auto_price_change": False,
                "next_recheck_endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
            }
        if code == "price_zero_or_too_low":
            return {
                "action_type": "review_price",
                "endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
                "auto_price_change": False,
                "required_inputs": ["price review result", "comment"],
            }
        if code in {
            "finance_reconciliation_mismatch",
            "sale_without_finance",
            "finance_without_sale",
        }:
            return {
                "action_type": "trigger_recheck_or_admin_investigation",
                "endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
                "forbidden": ["manual_edit_wb_finance_facts"],
            }
        return {
            "action_type": "trigger_recheck",
            "endpoint": f"POST /api/v1/dq/issues/{issue_id}/guided-action",
        }

    def _current_value_for_row(
        self, issue: DataQualityIssue, row: dict[str, object]
    ) -> object | None:
        code = str(issue.code or "").strip().lower()
        if code in {
            "missing_manual_cost",
            "missing_cost_blocks_profit",
            "seller_other_expense_missing",
        }:
            return safe_sample_row(
                {
                    "cost_price": row.get("cost_price"),
                    "seller_other_expense": row.get("seller_other_expense"),
                    "has_manual_cost": row.get("has_manual_cost"),
                    "has_real_manual_cost": row.get("has_real_manual_cost"),
                    "business_trusted": row.get("business_trusted"),
                },
                max_fields=8,
            )
        if code in {
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "unmatched_sku",
        }:
            return safe_sample_row(
                {
                    "sku_id": row.get("sku_id"),
                    "mapped_sku_id": row.get("mapped_sku_id"),
                    "candidate_sku_ids": row.get("candidateSkuIds")
                    or row.get("candidate_sku_ids"),
                    "source_identifier": row.get("entity_key")
                    or row.get("srid")
                    or row.get("id"),
                },
                max_fields=8,
            )
        if code in {"expense_unclassified", "unclassified_finance_expense"}:
            return safe_sample_row(
                {
                    "expense_category": row.get("expense_category"),
                    "amount": row.get("amount") or row.get("affectedAmount"),
                    "source_field": row.get("source_field") or row.get("sourceField"),
                    "operation": row.get("seller_oper_name")
                    or row.get("operation_type"),
                },
                max_fields=8,
            )
        if code in {
            "finance_reconciliation_mismatch",
            "sale_without_finance",
            "finance_without_sale",
        }:
            return safe_sample_row(
                {
                    "operational_revenue": row.get("operational_revenue"),
                    "finance_revenue": row.get("finance_revenue"),
                    "revenue_delta": row.get("revenue_delta")
                    or row.get("revenueDelta"),
                    "for_pay_delta": row.get("for_pay_delta") or row.get("forPayDelta"),
                    "status": row.get("status"),
                },
                max_fields=8,
            )
        if code in {"price_jump", "price_zero_or_too_low"}:
            return safe_sample_row(
                {
                    "current_price": row.get("current_price")
                    or row.get("currentPrice"),
                    "current_discounted_price": row.get("current_discounted_price")
                    or row.get("currentDiscountedPrice"),
                    "previous_price": row.get("previous_price")
                    or row.get("previousPrice"),
                    "change_percent": row.get("change_percent")
                    or row.get("changePercent"),
                },
                max_fields=8,
            )
        return self._normal_row_value(row, "current_value", "value", "status")

    @staticmethod
    def _missing_or_invalid_value_for_row(
        issue: DataQualityIssue, row: dict[str, object]
    ) -> object | None:
        code = str(issue.code or "").strip().lower()
        if code in {"missing_manual_cost", "missing_cost_blocks_profit"}:
            return "cost_price"
        if code == "seller_other_expense_missing":
            return "seller_other_expense"
        if code in {
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "unmatched_sku",
        }:
            return "sku_mapping"
        if code in {"expense_unclassified", "unclassified_finance_expense"}:
            return (
                row.get("source_field") or row.get("sourceField") or "expense_category"
            )
        if code in {
            "finance_reconciliation_mismatch",
            "sale_without_finance",
            "finance_without_sale",
        }:
            return safe_sample_row(
                {
                    "revenue_delta": row.get("revenue_delta")
                    or row.get("revenueDelta"),
                    "for_pay_delta": row.get("for_pay_delta") or row.get("forPayDelta"),
                },
                max_fields=4,
            )
        if code in {"price_jump", "price_zero_or_too_low"}:
            return (
                row.get("change_percent")
                or row.get("changePercent")
                or "price_outside_expected_range"
            )
        return row.get("missing_or_invalid_value") or issue.code

    @staticmethod
    def _row_status_for_issue(issue: DataQualityIssue) -> str:
        code = str(issue.code or "").strip().lower()
        if code in {
            "missing_manual_cost",
            "missing_cost_blocks_profit",
            "seller_other_expense_missing",
        }:
            return "needs_cost"
        if code in {
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "unmatched_sku",
        }:
            return "needs_mapping"
        if code in {"expense_unclassified", "unclassified_finance_expense"}:
            return "needs_classification"
        if code == "finance_reconciliation_mismatch":
            return "admin_investigation"
        if code in {"sale_without_finance", "finance_without_sale"}:
            return "system_wait"
        if code == "price_jump":
            return "check_only"
        if code == "price_zero_or_too_low":
            return "needs_price_review"
        return "needs_review"

    def _normalize_affected_row(
        self,
        issue: DataQualityIssue,
        row: dict[str, object],
        *,
        include_debug: bool = False,
    ) -> dict[str, object]:
        payload = dict(issue.payload or {})
        source = str(
            row.get("_source")
            or row.get("source")
            or issue.source_table
            or "data_quality_issues"
        )
        normalized = {
            "nm_id": self._normal_row_value(row, "nm_id", "nmId")
            or payload.get("nmId")
            or issue.nm_id,
            "vendor_code": self._normal_row_value(row, "vendor_code", "vendorCode")
            or payload.get("vendorCode"),
            "barcode": self._normal_row_value(row, "barcode") or payload.get("barcode"),
            "source": source,
            "current_value": self._current_value_for_row(issue, row),
            "missing_or_invalid_value": self._missing_or_invalid_value_for_row(
                issue, row
            ),
            "suggested_fix": self._suggested_fix_for_row(issue, row),
            "confidence": "blocked"
            if self._issue_is_effective_financial_final_blocker(issue)
            else "provisional",
            "row_status": self._row_status_for_issue(issue),
        }
        if include_debug:
            normalized["raw_payload"] = safe_sample_row(dict(row), max_fields=32)
        return {
            key: value for key, value in normalized.items() if value not in (None, "")
        }

    @staticmethod
    def _apply_available_for_definition(
        code: str, definition: GuidedFixDefinition
    ) -> bool:
        if str(code or "").strip().lower() == "price_jump":
            return False
        if str(getattr(definition, "fixability", "") or "") != "fix_in_platform":
            return False
        return bool((definition.apply_action or {}).get("allowed"))

    @classmethod
    def _disabled_reason_for_definition(
        cls, code: str, definition: GuidedFixDefinition, *, apply_available: bool
    ) -> str | None:
        normalized = str(code or "").strip().lower()
        if apply_available:
            return None
        if normalized == "price_jump":
            return "price_jump_check_only_no_auto_price_change"
        if getattr(definition, "disabled_reason", None):
            return str(definition.disabled_reason)
        if not bool(definition.can_user_fix_inside_platform):
            owner = cls._resolution_owner_type(definition.owner_type)
            if normalized == "finance_reconciliation_mismatch":
                return "finance_reconciliation_mismatch_requires_system_or_admin_investigation"
            return f"{owner}_owned_issue_not_user_fixable_inside_platform"
        return "apply_action_not_available_for_this_issue"

    async def _core_sku_rows_for_issue(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        core_filters = []
        if ids["sku_id"] is not None:
            core_filters.append(CoreSKU.id == ids["sku_id"])
        if ids["nm_id"] is not None:
            core_filters.append(CoreSKU.nm_id == ids["nm_id"])
        if ids["vendor_code"]:
            core_filters.append(CoreSKU.vendor_code == ids["vendor_code"])
        if ids["barcode"]:
            core_filters.append(CoreSKU.barcode == ids["barcode"])
        payload = ids["payload"]
        if isinstance(payload, dict):
            candidate_ids = [
                int(value)
                for value in (payload.get("candidateSkuIds") or [])
                if value is not None
            ]
            if candidate_ids:
                core_filters.append(CoreSKU.id.in_(candidate_ids))
        if not core_filters or issue.account_id is None:
            return []
        rows = list(
            (
                await session.execute(
                    select(CoreSKU)
                    .where(CoreSKU.account_id == issue.account_id, or_(*core_filters))
                    .order_by(CoreSKU.is_active.desc(), CoreSKU.id.desc())
                    .limit(query_cap)
                )
            ).scalars()
        )
        return [
            self._to_safe_row(
                "core_sku.candidate_or_card",
                {
                    "id": row.id,
                    "sku_id": row.id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "barcode": row.barcode,
                    "sku": row.sku,
                    "chrt_id": row.chrt_id,
                    "tech_size": row.tech_size,
                    "title": row.title,
                    "brand": row.brand,
                    "is_active": row.is_active,
                    "status": row.status,
                },
            )
            for row in rows
        ]

    async def _rows_missing_manual_cost(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows = await self._core_sku_rows_for_issue(session, issue, query_cap=query_cap)
        filters = []
        if ids["sku_id"] is not None:
            filters.append(MartSKUDaily.sku_id == ids["sku_id"])
        if ids["nm_id"] is not None:
            filters.append(MartSKUDaily.nm_id == ids["nm_id"])
        if ids["vendor_code"]:
            filters.append(MartSKUDaily.vendor_code == ids["vendor_code"])
        if ids["barcode"]:
            filters.append(MartSKUDaily.barcode == ids["barcode"])
        if filters and issue.account_id is not None:
            mart_rows = list(
                (
                    await session.execute(
                        select(MartSKUDaily)
                        .where(
                            MartSKUDaily.account_id == issue.account_id,
                            or_(*filters),
                            or_(
                                MartSKUDaily.has_real_manual_cost.is_not(True),
                                MartSKUDaily.has_manual_cost.is_not(True),
                                MartSKUDaily.cost_price.is_(None),
                            ),
                        )
                        .order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            for row in mart_rows:
                revenue = self._decimal(row.final_revenue)
                stock_qty = self._decimal(row.closing_stock_qty)
                price = self._decimal(row.current_discounted_price or row.current_price)
                rows.append(
                    self._to_safe_row(
                        "mart_sku_daily.missing_supplier_cost",
                        {
                            "id": row.id,
                            "stat_date": row.stat_date,
                            "sku_id": row.sku_id,
                            "nm_id": row.nm_id,
                            "vendor_code": row.vendor_code,
                            "barcode": row.barcode,
                            "title": row.title,
                            "final_revenue": row.final_revenue,
                            "sale_rows": row.sale_rows,
                            "final_sales_qty": row.final_sales_qty,
                            "closing_stock_qty": row.closing_stock_qty,
                            "estimated_stock_value": stock_qty * price
                            if stock_qty and price
                            else None,
                            "cost_price": row.cost_price,
                            "has_manual_cost": row.has_manual_cost,
                            "has_real_manual_cost": row.has_real_manual_cost,
                            "business_trusted": row.business_trusted,
                            "revenue_impact": revenue,
                        },
                    )
                )
        return rows

    async def _rows_seller_other_expense_missing(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        if issue.account_id is None:
            return []
        cost_rows = list(
            (
                await session.execute(
                    select(ManualCost)
                    .where(
                        ManualCost.account_id == issue.account_id,
                        ManualCost.seller_other_expense.is_(None),
                        ManualCost.is_placeholder.is_not(True),
                    )
                    .order_by(
                        ManualCost.valid_from.desc().nullslast(), ManualCost.id.desc()
                    )
                    .limit(query_cap)
                )
            ).scalars()
        )
        return [
            self._to_safe_row(
                "manual_costs.missing_seller_other_expense",
                {
                    "id": row.id,
                    "cost_id": row.id,
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "barcode": row.barcode,
                    "tech_size": row.tech_size,
                    "cost_price": row.cost_price,
                    "seller_other_expense": row.seller_other_expense,
                    "valid_from": row.valid_from,
                    "supplier": row.supplier,
                    "is_business_trusted": row.is_business_trusted,
                },
            )
            for row in cost_rows
        ]

    async def _rows_unmatched_sku(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows = await self._core_sku_rows_for_issue(session, issue, query_cap=query_cap)
        if issue.account_id is None:
            return rows
        source_filters = []
        if ids["nm_id"] is not None:
            source_filters.append(("nm_id", ids["nm_id"]))
        if ids["barcode"]:
            source_filters.append(("barcode", ids["barcode"]))
        if ids["vendor_code"]:
            source_filters.append(("vendor_code", ids["vendor_code"]))
            source_filters.append(("supplier_article", ids["vendor_code"]))

        def _or_for(model, *allowed: str):
            filters = []
            for attr, value in source_filters:
                if attr in allowed and hasattr(model, attr):
                    filters.append(getattr(model, attr) == value)
            return or_(*filters) if filters else None

        source_table = str(issue.source_table or "").lower()
        if source_table in {"wb_sales", "sales"}:
            condition = _or_for(WBSale, "nm_id", "barcode", "supplier_article")
            if condition is not None:
                sales = list(
                    (
                        await session.execute(
                            select(WBSale)
                            .where(WBSale.account_id == issue.account_id, condition)
                            .order_by(WBSale.last_change_date.desc())
                            .limit(query_cap)
                        )
                    ).scalars()
                )
                rows.extend(
                    self._to_safe_row(
                        "wb_sales.unmatched_source",
                        {
                            "id": row.id,
                            "date": row.date,
                            "last_change_date": row.last_change_date,
                            "srid": row.srid,
                            "sale_id": row.sale_id,
                            "order_id": row.order_id,
                            "nm_id": row.nm_id,
                            "barcode": row.barcode,
                            "vendor_code": row.supplier_article,
                            "finished_price": row.finished_price,
                            "for_pay": row.for_pay,
                        },
                    )
                    for row in sales
                )
        elif source_table in {"wb_orders", "orders"}:
            condition = _or_for(WBOrder, "nm_id", "barcode", "supplier_article")
            if condition is not None:
                orders = list(
                    (
                        await session.execute(
                            select(WBOrder)
                            .where(WBOrder.account_id == issue.account_id, condition)
                            .order_by(WBOrder.last_change_date.desc())
                            .limit(query_cap)
                        )
                    ).scalars()
                )
                rows.extend(
                    self._to_safe_row(
                        "wb_orders.unmatched_source",
                        {
                            "id": row.id,
                            "date": row.date,
                            "last_change_date": row.last_change_date,
                            "srid": row.srid,
                            "order_id": row.order_id,
                            "nm_id": row.nm_id,
                            "barcode": row.barcode,
                            "vendor_code": row.supplier_article,
                            "finished_price": row.finished_price,
                            "is_cancel": row.is_cancel,
                        },
                    )
                    for row in orders
                )
        elif source_table in {"wb_stock_snapshot_rows", "stocks"}:
            condition = _or_for(WBStockSnapshotRow, "nm_id", "barcode")
            if condition is not None:
                stock = list(
                    (
                        await session.execute(
                            select(WBStockSnapshotRow)
                            .where(
                                WBStockSnapshotRow.account_id == issue.account_id,
                                condition,
                            )
                            .order_by(WBStockSnapshotRow.id.desc())
                            .limit(query_cap)
                        )
                    ).scalars()
                )
                rows.extend(
                    self._to_safe_row(
                        "wb_stock_snapshot_rows.unmatched_source",
                        {
                            "id": row.id,
                            "snapshot_id": row.snapshot_id,
                            "nm_id": row.nm_id,
                            "barcode": row.barcode,
                            "chrt_id": row.chrt_id,
                            "warehouse_id": row.warehouse_id,
                            "warehouse_name": row.warehouse_name,
                            "quantity": row.quantity,
                            "quantity_full": row.quantity_full,
                        },
                    )
                    for row in stock
                )
        elif source_table == "wb_supply_goods":
            condition = _or_for(WBSupplyGood, "nm_id", "barcode", "vendor_code")
            if condition is not None:
                goods = list(
                    (
                        await session.execute(
                            select(WBSupplyGood)
                            .where(
                                WBSupplyGood.account_id == issue.account_id, condition
                            )
                            .order_by(WBSupplyGood.id.desc())
                            .limit(query_cap)
                        )
                    ).scalars()
                )
                rows.extend(
                    self._to_safe_row(
                        "wb_supply_goods.unmatched_source",
                        {
                            "id": row.id,
                            "supply_fk_id": row.supply_fk_id,
                            "nm_id": row.nm_id,
                            "vendor_code": row.vendor_code,
                            "barcode": row.barcode,
                            "tech_size": row.tech_size,
                            "quantity": row.quantity,
                            "accepted_quantity": row.accepted_quantity,
                        },
                    )
                    for row in goods
                )
        return rows

    async def _rows_finance_reconciliation(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows: list[dict[str, object]] = []
        if issue.account_id is None:
            return rows
        rec_filters = []
        if ids["sku_id"] is not None:
            rec_filters.append(MartFinanceReconciliation.sku_id == ids["sku_id"])
        if ids["nm_id"] is not None:
            rec_filters.append(MartFinanceReconciliation.nm_id == ids["nm_id"])
        if ids["srid"]:
            rec_filters.append(MartFinanceReconciliation.srid == ids["srid"])
        if rec_filters:
            rec_rows = list(
                (
                    await session.execute(
                        select(MartFinanceReconciliation)
                        .where(
                            MartFinanceReconciliation.account_id == issue.account_id,
                            or_(*rec_filters),
                        )
                        .order_by(
                            MartFinanceReconciliation.stat_date.desc(),
                            MartFinanceReconciliation.id.desc(),
                        )
                        .limit(query_cap)
                    )
                ).scalars()
            )
            for row in rec_rows:
                operational_revenue = (
                    row.sale_revenue
                    if row.sale_revenue is not None
                    else row.order_revenue
                )
                rows.append(
                    self._to_safe_row(
                        "mart_finance_reconciliation.exact_delta",
                        {
                            "id": row.id,
                            "stat_date": row.stat_date,
                            "srid": row.srid,
                            "order_id": row.order_id,
                            "sku_id": row.sku_id,
                            "nm_id": row.nm_id,
                            "vendor_code": row.vendor_code,
                            "order_rows": row.order_rows,
                            "sale_rows": row.sale_rows,
                            "finance_rows": row.finance_rows,
                            "operational_revenue": operational_revenue,
                            "finance_revenue": row.finance_revenue,
                            "revenue_delta": row.revenue_delta,
                            "operational_for_pay": row.sale_for_pay,
                            "finance_for_pay": row.finance_for_pay,
                            "for_pay_delta": row.for_pay_delta,
                            "status": row.status,
                        },
                    )
                )
        if ids["srid"]:
            sales = list(
                (
                    await session.execute(
                        select(WBSale)
                        .where(
                            WBSale.account_id == issue.account_id,
                            WBSale.srid == ids["srid"],
                        )
                        .order_by(WBSale.last_change_date.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            orders = list(
                (
                    await session.execute(
                        select(WBOrder)
                        .where(
                            WBOrder.account_id == issue.account_id,
                            WBOrder.srid == ids["srid"],
                        )
                        .order_by(WBOrder.last_change_date.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            report_rows = list(
                (
                    await session.execute(
                        select(WBRealizationReportRow)
                        .where(
                            WBRealizationReportRow.account_id == issue.account_id,
                            WBRealizationReportRow.srid == ids["srid"],
                        )
                        .order_by(
                            WBRealizationReportRow.rr_date.desc().nullslast(),
                            WBRealizationReportRow.id.desc(),
                        )
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "wb_sales.reconciliation_source",
                    {
                        "id": row.id,
                        "date": row.date,
                        "last_change_date": row.last_change_date,
                        "srid": row.srid,
                        "sale_id": row.sale_id,
                        "order_id": row.order_id,
                        "nm_id": row.nm_id,
                        "barcode": row.barcode,
                        "vendor_code": row.supplier_article,
                        "finished_price": row.finished_price,
                        "for_pay": row.for_pay,
                    },
                )
                for row in sales
            )
            rows.extend(
                self._to_safe_row(
                    "wb_orders.reconciliation_source",
                    {
                        "id": row.id,
                        "date": row.date,
                        "last_change_date": row.last_change_date,
                        "srid": row.srid,
                        "order_id": row.order_id,
                        "nm_id": row.nm_id,
                        "barcode": row.barcode,
                        "vendor_code": row.supplier_article,
                        "finished_price": row.finished_price,
                        "is_cancel": row.is_cancel,
                    },
                )
                for row in orders
            )
            rows.extend(
                self._to_safe_row(
                    "wb_realization_report_rows.reconciliation_source",
                    {
                        "id": row.id,
                        "rrd_id": row.rrd_id,
                        "rr_date": row.rr_date,
                        "sale_dt": row.sale_dt,
                        "srid": row.srid,
                        "order_id": row.order_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                        "barcode": row.barcode,
                        "doc_type_name": row.doc_type_name,
                        "operation_type": row.operation_type,
                        "retail_amount": row.retail_amount,
                        "for_pay": row.for_pay,
                        "is_reconcilable": row.is_reconcilable,
                    },
                )
                for row in report_rows
            )
        return rows

    async def _rows_stock_without_sales(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows: list[dict[str, object]] = []
        if issue.account_id is None:
            return rows
        filters = []
        if ids["sku_id"] is not None:
            filters.append(MartStockDaily.sku_id == ids["sku_id"])
        if ids["nm_id"] is not None:
            filters.append(MartStockDaily.nm_id == ids["nm_id"])
        if ids["barcode"]:
            filters.append(MartStockDaily.barcode == ids["barcode"])
        if filters:
            stock_rows = list(
                (
                    await session.execute(
                        select(MartStockDaily)
                        .where(
                            MartStockDaily.account_id == issue.account_id, or_(*filters)
                        )
                        .order_by(
                            MartStockDaily.stat_date.desc(), MartStockDaily.id.desc()
                        )
                        .limit(query_cap)
                    )
                ).scalars()
            )
            for row in stock_rows:
                quantity = self._decimal(row.quantity_full or row.quantity)
                rows.append(
                    self._to_safe_row(
                        "mart_stock_daily.stock_without_sales",
                        {
                            "id": row.id,
                            "stat_date": row.stat_date,
                            "sku_id": row.sku_id,
                            "nm_id": row.nm_id,
                            "barcode": row.barcode,
                            "warehouse_id": row.warehouse_id,
                            "warehouse_name": row.warehouse_name,
                            "quantity": row.quantity,
                            "quantity_full": row.quantity_full,
                            "recent_sales_7d": row.sales_7d,
                            "recent_sales_14d": row.sales_14d,
                            "recent_sales_30d": row.sales_30d,
                            "days_since_last_sale": row.days_since_last_sale,
                            "stock_quantity_for_value": quantity,
                        },
                    )
                )
        return rows

    async def _rows_sales_without_stock(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows: list[dict[str, object]] = []
        if issue.account_id is None:
            return rows
        mart_filters = []
        sale_filters = []
        stock_filters = []
        if ids["sku_id"] is not None:
            mart_filters.append(MartSKUDaily.sku_id == ids["sku_id"])
        if ids["nm_id"] is not None:
            mart_filters.append(MartSKUDaily.nm_id == ids["nm_id"])
            sale_filters.append(WBSale.nm_id == ids["nm_id"])
            stock_filters.append(WBStockSnapshotRow.nm_id == ids["nm_id"])
        if ids["barcode"]:
            sale_filters.append(WBSale.barcode == ids["barcode"])
            stock_filters.append(WBStockSnapshotRow.barcode == ids["barcode"])
        if mart_filters:
            mart_rows = list(
                (
                    await session.execute(
                        select(MartSKUDaily)
                        .where(
                            MartSKUDaily.account_id == issue.account_id,
                            or_(*mart_filters),
                        )
                        .order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "mart_sku_daily.sales_without_stock",
                    {
                        "id": row.id,
                        "stat_date": row.stat_date,
                        "sku_id": row.sku_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                        "barcode": row.barcode,
                        "final_sales_qty": row.final_sales_qty,
                        "sale_rows": row.sale_rows,
                        "final_revenue": row.final_revenue,
                        "closing_stock_qty": row.closing_stock_qty,
                        "stock_snapshot_available": row.closing_stock_qty is not None,
                    },
                )
                for row in mart_rows
            )
        if sale_filters:
            sales = list(
                (
                    await session.execute(
                        select(WBSale)
                        .where(
                            WBSale.account_id == issue.account_id, or_(*sale_filters)
                        )
                        .order_by(WBSale.last_change_date.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "wb_sales.sale_without_stock_source",
                    {
                        "id": row.id,
                        "date": row.date,
                        "last_change_date": row.last_change_date,
                        "srid": row.srid,
                        "sale_id": row.sale_id,
                        "order_id": row.order_id,
                        "nm_id": row.nm_id,
                        "barcode": row.barcode,
                        "vendor_code": row.supplier_article,
                        "finished_price": row.finished_price,
                        "for_pay": row.for_pay,
                    },
                )
                for row in sales
            )
        if stock_filters:
            stocks = list(
                (
                    await session.execute(
                        select(WBStockSnapshotRow)
                        .where(
                            WBStockSnapshotRow.account_id == issue.account_id,
                            or_(*stock_filters),
                        )
                        .order_by(WBStockSnapshotRow.id.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "wb_stock_snapshot_rows.latest_availability",
                    {
                        "id": row.id,
                        "snapshot_id": row.snapshot_id,
                        "nm_id": row.nm_id,
                        "barcode": row.barcode,
                        "warehouse_id": row.warehouse_id,
                        "warehouse_name": row.warehouse_name,
                        "quantity": row.quantity,
                        "quantity_full": row.quantity_full,
                    },
                )
                for row in stocks
            )
        return rows

    async def _rows_ad_allocation(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows: list[dict[str, object]] = []
        if issue.account_id is None:
            return rows
        ad_filters = []
        if str(issue.code or "").lower() == "ad_spend_without_sku":
            ad_filters.append(
                or_(WBAdStatsDaily.nm_id.is_(None), WBAdStatsDaily.nm_id == 0)
            )
        elif ids["nm_id"] is not None:
            ad_filters.append(WBAdStatsDaily.nm_id == ids["nm_id"])
        if ad_filters:
            ads = list(
                (
                    await session.execute(
                        select(WBAdStatsDaily)
                        .where(
                            WBAdStatsDaily.account_id == issue.account_id,
                            or_(*ad_filters),
                        )
                        .order_by(
                            WBAdStatsDaily.stat_date.desc(), WBAdStatsDaily.id.desc()
                        )
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "wb_ad_stats_daily.ad_source_spend",
                    {
                        "id": row.id,
                        "advert_id": row.advert_id,
                        "stat_date": row.stat_date,
                        "nm_id": row.nm_id,
                        "source_spend": row.sum,
                        "views": row.views,
                        "clicks": row.clicks,
                        "orders": row.orders,
                        "nm_id_mapping_status": "missing"
                        if not row.nm_id
                        else "mapped",
                    },
                )
                for row in ads
            )
        mart_filters = []
        if ids["nm_id"] is not None:
            mart_filters.append(MartSKUDaily.nm_id == ids["nm_id"])
        if mart_filters:
            mart_rows = list(
                (
                    await session.execute(
                        select(MartSKUDaily)
                        .where(
                            MartSKUDaily.account_id == issue.account_id,
                            or_(*mart_filters),
                        )
                        .order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "mart_sku_daily.ad_allocated_spend",
                    {
                        "id": row.id,
                        "stat_date": row.stat_date,
                        "sku_id": row.sku_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                        "allocated_spend": row.ad_spend,
                        "ad_spend_operational": row.ad_spend_operational,
                        "ad_spend_finance": row.ad_spend_finance,
                        "ad_spend_final": row.ad_spend_final,
                        "ad_spend_delta": row.ad_spend_delta,
                        "ad_spend_source": row.ad_spend_source,
                    },
                )
                for row in mart_rows
            )
        return rows

    async def _rows_expense_classification(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows: list[dict[str, object]] = []
        if issue.account_id is None:
            return rows
        expense_filters = []
        if ids["sku_id"] is not None:
            expense_filters.append(MartExpenseDaily.sku_id == ids["sku_id"])
        if ids["nm_id"] is not None:
            expense_filters.append(MartExpenseDaily.nm_id == ids["nm_id"])
        if ids["source_field"]:
            expense_filters.append(MartExpenseDaily.source_field == ids["source_field"])
        if not expense_filters:
            expense_filters.append(
                MartExpenseDaily.expense_category.in_(["unknown", "unclassified"])
            )
        expense_rows = list(
            (
                await session.execute(
                    select(MartExpenseDaily)
                    .where(
                        MartExpenseDaily.account_id == issue.account_id,
                        or_(*expense_filters),
                    )
                    .order_by(
                        MartExpenseDaily.stat_date.desc(), MartExpenseDaily.id.desc()
                    )
                    .limit(query_cap)
                )
            ).scalars()
        )
        return [
            self._to_safe_row(
                "mart_expense_daily.unclassified_source",
                {
                    "id": row.id,
                    "stat_date": row.stat_date,
                    "report_id": row.report_id,
                    "rrd_id": row.rrd_id,
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "barcode": row.barcode,
                    "expense_category": row.expense_category,
                    "expense_source": row.expense_source,
                    "amount": row.amount,
                    "amount_sign": row.amount_sign,
                    "currency": row.currency,
                    "source_field": row.source_field,
                    "source_reason": row.source_reason,
                    "seller_oper_name": row.seller_oper_name,
                    "bonus_type_name": row.bonus_type_name,
                    "logistics_type": row.logistics_type,
                    "is_allocated_to_sku": row.is_allocated_to_sku,
                    "allocation_method": row.allocation_method,
                },
            )
            for row in expense_rows
        ]

    async def _rows_price_issues(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows: list[dict[str, object]] = []
        if issue.account_id is None or ids["nm_id"] is None:
            return rows
        mart_rows = list(
            (
                await session.execute(
                    select(MartSKUDaily)
                    .where(
                        MartSKUDaily.account_id == issue.account_id,
                        MartSKUDaily.nm_id == ids["nm_id"],
                    )
                    .order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc())
                    .limit(query_cap)
                )
            ).scalars()
        )
        rows.extend(
            self._to_safe_row(
                "mart_sku_daily.price_issue",
                {
                    "id": row.id,
                    "stat_date": row.stat_date,
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "current_price": row.current_price,
                    "current_discounted_price": row.current_discounted_price,
                    "avg_sale_price": row.avg_sale_price,
                    "final_revenue": row.final_revenue,
                    "sale_rows": row.sale_rows,
                },
            )
            for row in mart_rows
        )
        snapshots = list(
            (
                await session.execute(
                    select(WBPriceSnapshot)
                    .where(
                        WBPriceSnapshot.account_id == issue.account_id,
                        WBPriceSnapshot.nm_id == ids["nm_id"],
                    )
                    .order_by(
                        WBPriceSnapshot.snapshot_at.desc(), WBPriceSnapshot.id.desc()
                    )
                    .limit(query_cap)
                )
            ).scalars()
        )
        for index, row in enumerate(snapshots):
            current_price = self._extract_snapshot_price(row.payload)
            previous_price = (
                self._extract_snapshot_price(snapshots[index + 1].payload)
                if index + 1 < len(snapshots)
                else None
            )
            change_percent = None
            if current_price not in (None, Decimal("0")) and previous_price not in (
                None,
                Decimal("0"),
            ):
                change_percent = (
                    (current_price - previous_price) / previous_price * Decimal("100")
                ).quantize(Decimal("0.01"))
            rows.append(
                self._to_safe_row(
                    "wb_price_snapshots.wb_price_source",
                    {
                        "id": row.id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                        "snapshot_at": row.snapshot_at,
                        "current_price": current_price,
                        "previous_price": previous_price,
                        "change_percent": change_percent,
                        "wb_price_source": "wb_price_snapshots",
                    },
                )
            )
        quarantine = list(
            (
                await session.execute(
                    select(WBPriceQuarantine)
                    .where(
                        WBPriceQuarantine.account_id == issue.account_id,
                        WBPriceQuarantine.nm_id == ids["nm_id"],
                    )
                    .order_by(
                        WBPriceQuarantine.snapshot_at.desc(),
                        WBPriceQuarantine.id.desc(),
                    )
                    .limit(query_cap)
                )
            ).scalars()
        )
        rows.extend(
            self._to_safe_row(
                "wb_price_quarantine",
                {
                    "id": row.id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "snapshot_at": row.snapshot_at,
                    "quarantine_reason": (row.payload or {}).get("reason"),
                    "current_price": (row.payload or {}).get("currentPrice")
                    or (row.payload or {}).get("price"),
                    "previous_price": (row.payload or {}).get("previousPrice"),
                },
            )
            for row in quarantine
        )
        return rows

    async def _rows_generic_issue_context(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        query_cap: int,
    ) -> list[dict[str, object]]:
        ids = self._issue_identifiers(issue)
        rows = await self._core_sku_rows_for_issue(session, issue, query_cap=query_cap)
        if issue.account_id is None:
            return rows
        filters = []
        if ids["sku_id"] is not None:
            filters.append(MartSKUDaily.sku_id == ids["sku_id"])
        if ids["nm_id"] is not None:
            filters.append(MartSKUDaily.nm_id == ids["nm_id"])
        if filters:
            mart_rows = list(
                (
                    await session.execute(
                        select(MartSKUDaily)
                        .where(
                            MartSKUDaily.account_id == issue.account_id, or_(*filters)
                        )
                        .order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc())
                        .limit(query_cap)
                    )
                ).scalars()
            )
            rows.extend(
                self._to_safe_row(
                    "mart_sku_daily.context",
                    {
                        "id": row.id,
                        "stat_date": row.stat_date,
                        "sku_id": row.sku_id,
                        "nm_id": row.nm_id,
                        "vendor_code": row.vendor_code,
                        "barcode": row.barcode,
                        "sale_rows": row.sale_rows,
                        "finance_rows": row.finance_rows,
                        "final_revenue": row.final_revenue,
                        "closing_stock_qty": row.closing_stock_qty,
                        "current_price": row.current_price,
                        "current_discounted_price": row.current_discounted_price,
                    },
                )
                for row in mart_rows
            )
        return rows

    async def _affected_rows_for_issue(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        limit: int = 50,
        offset: int = 0,
        include_debug: bool = False,
    ) -> tuple[list[dict[str, object]], int]:
        rows: list[dict[str, object]] = [self._issue_reference_row(issue)]
        code = str(issue.code or "").lower()
        query_cap = self._query_cap(limit, offset)
        if code in {"missing_manual_cost", "missing_cost_blocks_profit"}:
            rows.extend(
                await self._rows_missing_manual_cost(
                    session, issue, query_cap=query_cap
                )
            )
        elif code == "seller_other_expense_missing":
            rows.extend(
                await self._rows_seller_other_expense_missing(
                    session, issue, query_cap=query_cap
                )
            )
        elif code in {
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "unmatched_sku",
            "missing_chrt_id",
        }:
            rows.extend(
                await self._rows_unmatched_sku(session, issue, query_cap=query_cap)
            )
        elif code in {
            "finance_reconciliation_mismatch",
            "sale_without_finance",
            "finance_without_sale",
        }:
            rows.extend(
                await self._rows_finance_reconciliation(
                    session, issue, query_cap=query_cap
                )
            )
        elif code == "stock_without_sales":
            rows.extend(
                await self._rows_stock_without_sales(
                    session, issue, query_cap=query_cap
                )
            )
        elif code == "sales_without_stock":
            rows.extend(
                await self._rows_sales_without_stock(
                    session, issue, query_cap=query_cap
                )
            )
        elif code in {
            "ad_spend_without_sku",
            "ads_overallocated_to_profitability",
            "ad_spend_without_sales",
            "expense_ad_double_count_risk",
        }:
            rows.extend(
                await self._rows_ad_allocation(session, issue, query_cap=query_cap)
            )
        elif code in {"price_jump", "price_zero_or_too_low"}:
            rows.extend(
                await self._rows_price_issues(session, issue, query_cap=query_cap)
            )
        elif code in {"expense_unclassified", "unclassified_finance_expense"}:
            rows.extend(
                await self._rows_expense_classification(
                    session, issue, query_cap=query_cap
                )
            )
        else:
            rows.extend(
                await self._rows_generic_issue_context(
                    session, issue, query_cap=query_cap
                )
            )
        sliced, total = self._slice_rows(rows, limit=limit, offset=offset)
        return [
            self._normalize_affected_row(issue, row, include_debug=include_debug)
            for row in sliced
        ], total

    def _source_facts_for_issue(
        self,
        issue: DataQualityIssue,
        *,
        affected_rows: list[dict[str, object]],
        affected_rows_total: int | None = None,
    ) -> list[GuidedFixSourceFact]:
        payload = dict(issue.payload or {})
        source_tables = sorted(
            {
                str(row.get("source") or row.get("_source") or "")
                for row in affected_rows
                if row.get("source") or row.get("_source")
            }
        )
        total_rows = int(
            affected_rows_total
            if affected_rows_total is not None
            else len(affected_rows)
        )
        facts: list[GuidedFixSourceFact] = [
            GuidedFixSourceFact(
                label="DQ issue",
                value=issue.code,
                source_table="data_quality_issues",
                source_endpoint="GET /api/v1/dq/issues",
                filters={"issue_id": issue.id, "account_id": issue.account_id},
                row_count=1,
                sample_rows=affected_rows[:1],
            ),
            GuidedFixSourceFact(
                label="Affected source rows",
                value=total_rows,
                unit="rows",
                source_table=", ".join(source_tables)
                if source_tables
                else issue.source_table,
                source_endpoint="GET /api/v1/dq/issues/{id}/resolution-context",
                filters={
                    "code": issue.code,
                    "sku_id": issue.sku_id,
                    "nm_id": issue.nm_id,
                    "entity_key": issue.entity_key,
                },
                row_count=total_rows,
                sample_rows=affected_rows[:3],
            ),
        ]
        affected_amount = payload.get("affectedAmount") or payload.get(
            "affected_amount"
        )
        affected_revenue = payload.get("affectedRevenue") or payload.get(
            "affected_revenue"
        )
        if affected_amount is not None or affected_revenue is not None:
            facts.append(
                GuidedFixSourceFact(
                    label="Reported impact",
                    value=affected_amount
                    if affected_amount is not None
                    else affected_revenue,
                    unit="RUB",
                    source_table=issue.source_table or "data_quality_issues",
                    source_endpoint="GET /api/v1/dq/issues",
                    filters={"issue_id": issue.id},
                    row_count=1,
                    sample_rows=[
                        safe_sample_row(
                            {
                                "affectedAmount": affected_amount,
                                "affectedRevenue": affected_revenue,
                            }
                        )
                    ],
                )
            )
        return facts

    async def resolution_context(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        affected_rows_limit: int = 50,
        affected_rows_offset: int = 0,
        include_debug_rows: bool = False,
    ) -> DataQualityResolutionContext:
        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Data quality issue not found")
        self._normalize_issue_runtime_flags(issue)
        definition = self.guided_fix_definition_for_code(issue.code)
        rows, rows_total = await self._affected_rows_for_issue(
            session,
            issue,
            limit=affected_rows_limit,
            offset=affected_rows_offset,
            include_debug=include_debug_rows,
        )
        dynamic_problem = await self._sync_dynamic_problem_instance(session, issue)
        issue_read = DataQualityIssueRead.from_issue(issue)
        issue_contract_payload = dict(issue.payload or {})
        if issue.nm_id is not None:
            issue_contract_payload.setdefault("nmId", issue.nm_id)
        issue_contract = issue_fixability_contract(
            issue.code, issue_contract_payload, severity=issue.severity
        )
        definition = definition.model_copy(
            update={
                "owner_type": issue_contract["owner_type"],
                "can_user_fix_inside_platform": bool(
                    issue_contract["can_user_fix_inside_platform"]
                ),
                "fixability": issue_contract["fixability"],
                "issue_nature": issue_contract["issue_nature"],
                "is_manual_edit_allowed": bool(
                    issue_contract["is_manual_edit_allowed"]
                ),
                "primary_action_code": str(issue_contract["primary_action_code"]),
                "primary_action_label": str(issue_contract["primary_action_label"]),
                "target_href": str(issue_contract["target_href"]),
                "disabled_reason": str(issue_contract["disabled_reason"] or ""),
                "recheck_mode": str(issue_contract["recheck_mode"]),
                "seller_explanation": str(issue_contract["seller_explanation"]),
                "admin_explanation": str(issue_contract["admin_explanation"]),
                "apply_action": {
                    **dict(definition.apply_action or {}),
                    **issue_contract,
                    "type": (definition.apply_action or {}).get("type")
                    or issue_contract["primary_action_code"],
                    "label": (definition.apply_action or {}).get("label")
                    or issue_contract["primary_action_label"],
                    "allowed": bool(
                        issue_contract["fixability"] == "fix_in_platform"
                        and issue_contract["can_user_fix_inside_platform"]
                    ),
                },
            }
        )
        recheck_rule = str(definition.recheck_query.get("rule") or "")
        resolver = build_problem_resolver(
            issue.code,
            issue_id=issue_id,
            guide=issue_resolution_guide(issue.code, dict(issue.payload or {})),
            guided_definition=definition,
        )
        dynamic_problem_id = (
            int(dynamic_problem.id) if dynamic_problem is not None else None
        )
        problem_code = (
            str(dynamic_problem.problem_code)
            if dynamic_problem is not None
            else str(issue.code or "")
        )
        owner_type = self._resolution_owner_type(definition.owner_type)
        apply_available = self._apply_available_for_definition(issue.code, definition)
        recheck_available = bool(
            issue.account_id is not None and definition.recheck_query
        )
        preview_available = bool(definition.preview_before_change)
        disabled_reason = self._disabled_reason_for_definition(
            issue.code, definition, apply_available=apply_available
        )
        if dynamic_problem_id is not None:
            action_center_href = self._frontend_href(
                "/action-center",
                problem_instance_id=dynamic_problem_id,
                nm_id=issue.nm_id,
            )
            results_href = self._frontend_href(
                "/results", problem_instance_id=dynamic_problem_id, nm_id=issue.nm_id
            )
        else:
            action_center_href = self._frontend_href(
                "/action-center", issue_code=issue.code, nm_id=issue.nm_id
            )
            results_href = self._frontend_href(
                "/results", problem_code=issue.code, nm_id=issue.nm_id
            )
        evidence_ledger = (
            issue_read.evidence_ledger.model_dump(mode="json")
            if issue_read.evidence_ledger is not None
            else {}
        )
        return DataQualityResolutionContext(
            issue_id=int(issue.id),
            problem_instance_id=dynamic_problem_id,
            problem_code=problem_code,
            issue_code=str(issue.code or ""),
            title=issue_read.message or str(issue.code or ""),
            explanation=issue_read.simple_reason or issue_read.message or "",
            why_it_matters=issue_read.business_impact
            or issue_read.recommended_fix
            or "",
            owner_type=owner_type,  # type: ignore[arg-type]
            fixability=str(definition.fixability),
            issue_nature=str(definition.issue_nature),
            can_user_fix_inside_platform=bool(
                definition.can_user_fix_inside_platform and apply_available
            ),
            is_manual_edit_allowed=bool(definition.is_manual_edit_allowed),
            fix_component_type=str(definition.fix_component_type),
            required_inputs=list(definition.required_inputs or []),
            primary_action_code=str(definition.primary_action_code),
            primary_action_label=str(definition.primary_action_label),
            target_href=str(definition.target_href),
            recheck_mode=str(definition.recheck_mode),
            seller_explanation=str(definition.seller_explanation),
            admin_explanation=str(definition.admin_explanation),
            issue=issue_read,
            definition=definition,
            resolver=resolver,
            affected_rows=rows,
            affected_rows_total=rows_total,
            affected_rows_limit=max(1, min(int(affected_rows_limit or 50), 200)),
            affected_rows_offset=max(0, int(affected_rows_offset or 0)),
            affected_rows_export_endpoint=f"/dq/issues/{issue_id}/affected-rows.csv",
            source_facts=self._source_facts_for_issue(
                issue, affected_rows=rows, affected_rows_total=rows_total
            ),
            evidence_ledger=evidence_ledger,
            preview_available=preview_available,
            apply_available=apply_available,
            recheck_available=recheck_available,
            disabled_reason=disabled_reason,
            action_center_href=action_center_href,
            results_href=results_href,
            suggested_fix_action=dict(definition.apply_action),
            recheck_rule=recheck_rule,
            audit_history=self._guided_fix_audit_history(issue),
            safe_to_apply=apply_available,
            dynamic_problem_instance=self._dynamic_problem_ref(dynamic_problem),
        )

    async def affected_rows_csv(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        limit: int = 1000,
    ) -> str:
        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Data quality issue not found")
        rows, _ = await self._affected_rows_for_issue(
            session,
            issue,
            limit=max(1, min(int(limit or 1000), 1000)),
            offset=0,
        )
        columns: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    columns.append(key)
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in columns})
        return output.getvalue()

    async def apply_guided_fix(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        request: GuidedFixActionRequest,
        user_id: int | None = None,
    ) -> GuidedFixActionResponse:
        from fastapi import HTTPException

        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            raise HTTPException(status_code=404, detail="Data quality issue not found")
        code = str(issue.code or "").strip().lower()
        action_type = str(request.action_type)
        inputs = dict(request.inputs or {})
        definition = self.guided_fix_definition_for_code(code)
        registry_action = get_action(action_type)
        if registry_action is None:
            raise HTTPException(status_code=400, detail="Unsupported guided fix action")
        if registry_action.is_external_write:
            raise HTTPException(
                status_code=400,
                detail=f"{registry_action.action_code} is not allowed from Data Fix guided workflows",
            )
        if action_type == "classify_expense" and not (
            registry_action.module == "data_fix"
            and registry_action.category == "data_fix"
            and registry_action.is_local_only
            and not registry_action.is_external_write
        ):
            raise HTTPException(
                status_code=400,
                detail="classify_expense must remain a local Data Fix action",
            )

        status = "ok"
        message = "Guided fix action recorded."

        if code == "price_jump" and action_type == "review_price":
            raise HTTPException(
                status_code=400,
                detail="price_jump is check-only in Data Fix; no platform price change or local price confirmation apply is available.",
            )

        if action_type == "map_sku":
            if code not in {
                "unmatched_sku",
                "manual_cost_unresolved_sku",
                "manual_cost_ambiguous_match",
                "missing_chrt_id",
            }:
                raise HTTPException(
                    status_code=400, detail="map_sku is not allowed for this issue code"
                )
            mapped_sku_id = self._payload_candidate_int(
                inputs, "mapped_sku_id", "mappedSkuId", "sku_id", "skuId"
            )
            if mapped_sku_id is None:
                raise HTTPException(status_code=400, detail="mapped_sku_id is required")
            sku = await session.get(CoreSKU, mapped_sku_id)
            if sku is None or (
                issue.account_id is not None and sku.account_id != issue.account_id
            ):
                raise HTTPException(
                    status_code=400,
                    detail="mapped_sku_id does not belong to this account",
                )
            payload = dict(issue.payload or {})
            manual_cost_id = self._payload_candidate_int(
                payload, "manualCostId", "manual_cost_id"
            )
            if manual_cost_id is not None and code in {
                "manual_cost_unresolved_sku",
                "manual_cost_ambiguous_match",
            }:
                cost = await session.get(ManualCost, manual_cost_id)
                if cost is None or cost.account_id != issue.account_id:
                    raise HTTPException(
                        status_code=404, detail="Manual cost row not found"
                    )
                cost.sku_id = mapped_sku_id
                cost.is_ambiguous = False
                cost.match_rule = "guided_fix_manual_mapping"
                cost.comment = "Mapped from Data Fix guided workflow."
                message = "Manual cost row mapped to SKU. Re-check to close the issue."
            else:
                message = "SKU mapping decision recorded. Re-check will verify whether source rows are now mapped."
            issue = await self.classify_issue_by_id(
                session,
                issue_id=issue_id,
                classification_status="mapped",
                classification_reason=str(
                    inputs.get("reason") or "Mapped in Data Fix guided workflow."
                ),
                user_id=user_id,
                comment=request.comment,
                mapped_sku_id=mapped_sku_id,
            )
        elif action_type == "classify_expense":
            if code not in {"expense_unclassified", "unclassified_finance_expense"}:
                raise HTTPException(
                    status_code=400,
                    detail="classify_expense is not allowed for this issue code",
                )
            category = str(
                inputs.get("expense_category") or inputs.get("category") or ""
            ).strip()
            if not category:
                raise HTTPException(
                    status_code=400, detail="expense_category is required"
                )
            payload = dict(issue.payload or {})
            payload["guidedExpenseCategory"] = category
            issue.payload = payload
            issue = await self.classify_issue_by_id(
                session,
                issue_id=issue_id,
                classification_status="classified",
                classification_reason=str(
                    inputs.get("classification_reason")
                    or f"Expense classified as {category}."
                ),
                user_id=user_id,
                comment=request.comment,
            )
            message = "Expense classification recorded. Re-check will verify taxonomy coverage."
        elif action_type == "mark_system_wait":
            if code not in {
                "sale_without_finance",
                "finance_without_sale",
                "finance_reconciliation_mismatch",
                "stocks_task_not_ready",
                "stocks_task_failed",
                "missed_load",
                "sync_date_mismatch",
                "failed_sync_domains",
                "latest_stocks_not_completed",
            }:
                raise HTTPException(
                    status_code=400,
                    detail="mark_system_wait is not allowed for this issue code",
                )
            issue = await self.classify_issue_by_id(
                session,
                issue_id=issue_id,
                classification_status="expected_lag",
                classification_reason=str(
                    inputs.get("reason")
                    or "Waiting for WB report or source sync; no manual fact edits allowed."
                ),
                financial_final_blocker_override=False,
                user_id=user_id,
                comment=request.comment,
            )
            message = "Marked as system/WB report wait. WB facts remain read-only."
        elif action_type == "mark_admin_investigation":
            issue = await self.classify_issue_by_id(
                session,
                issue_id=issue_id,
                classification_status="real_issue",
                classification_reason=str(
                    inputs.get("reason")
                    or "Admin investigation requested from Data Fix guided workflow."
                ),
                user_id=user_id,
                comment=request.comment,
            )
            message = "Admin investigation recorded."
        elif action_type == "mark_cost_upload_started":
            if code not in {"missing_manual_cost"}:
                raise HTTPException(
                    status_code=400,
                    detail="mark_cost_upload_started is only allowed for missing manual cost",
                )
            self._append_guided_fix_audit(
                issue,
                action_type=action_type,
                status="ok",
                message="Cost upload/check started from Data Fix.",
                user_id=user_id,
                inputs=inputs,
                comment=request.comment,
            )
            await session.flush()
            context = await self.resolution_context(session, issue_id=issue_id)
            return GuidedFixActionResponse(
                status="ok",
                message="Open /costs upload, then run re-check.",
                context=context,
            )
        elif action_type == "review_price":
            if code not in {"price_jump", "price_zero_or_too_low"}:
                raise HTTPException(
                    status_code=400,
                    detail="review_price is not allowed for this issue code",
                )
            issue = await self.classify_issue_by_id(
                session,
                issue_id=issue_id,
                classification_status="classified",
                classification_reason=str(
                    inputs.get("reason")
                    or "Price reviewed in Data Fix guided workflow."
                ),
                user_id=user_id,
                comment=request.comment,
            )
            message = "Price review recorded. Re-check will verify latest source price."
        elif action_type == "trigger_recheck":
            result = await self.recheck_issue(
                session,
                issue_id=issue_id,
                user_id=user_id,
                inputs=inputs,
                comment=request.comment,
            )
            context = await self.resolution_context(session, issue_id=issue_id)
            return GuidedFixActionResponse(
                status="ok",
                message=result.message or "Re-check completed.",
                context=context,
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported guided fix action")

        if not bool(definition.can_user_fix_inside_platform) and action_type not in {
            "mark_system_wait",
            "mark_admin_investigation",
            "trigger_recheck",
        }:
            status = "blocked"
            message = "This issue is not user-fixable inside the platform."

        self._append_guided_fix_audit(
            issue,
            action_type=action_type,
            status=status,
            message=message,
            user_id=user_id,
            inputs=inputs,
            comment=request.comment,
        )
        await session.flush()
        context = await self.resolution_context(session, issue_id=issue_id)
        return GuidedFixActionResponse(status=status, message=message, context=context)

    async def resolve_issue_by_id(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        comment: str | None = None,
    ) -> DataQualityIssue:
        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Data quality issue not found")
        payload = dict(issue.payload or {})
        if comment:
            payload["resolutionComment"] = comment
        issue.payload = payload
        if (
            not issue.classification_status
            or issue.classification_status == self.DEFAULT_CLASSIFICATION_STATUS
        ):
            issue.classification_status = "resolved_by_data"
            issue.classification_reason = (
                issue.classification_reason
                or "Resolved through data refresh or manual fix."
            )
            issue.classified_at = utcnow()
        issue.resolved_at = utcnow()
        self._refresh_issue_final_blocker_state(issue)
        await session.flush()
        await self._sync_dynamic_problem_instance(session, issue)
        return issue

    async def reopen_issue_by_id(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        comment: str | None = None,
    ) -> DataQualityIssue:
        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Data quality issue not found")
        payload = dict(issue.payload or {})
        if comment:
            payload["reopenComment"] = comment
        issue.payload = payload
        issue.resolved_at = None
        if (
            self._normalize_classification_status(issue.classification_status)
            == "resolved_by_data"
        ):
            issue.classification_status = self.DEFAULT_CLASSIFICATION_STATUS
            issue.classification_reason = None
        issue.detected_at = utcnow()
        self._refresh_issue_final_blocker_state(issue)
        await session.flush()
        await self._sync_dynamic_problem_instance(session, issue)
        return issue

    async def comment_issue_by_id(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        comment: str,
    ) -> DataQualityIssue:
        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Data quality issue not found")
        payload = dict(issue.payload or {})
        comments = list(payload.get("comments") or [])
        comments.append({"text": comment, "createdAt": utcnow().isoformat()})
        payload["comments"] = comments
        issue.payload = payload
        self._refresh_issue_final_blocker_state(issue)
        await session.flush()
        await self._sync_dynamic_problem_instance(session, issue)
        return issue

    async def classify_issue_by_id(
        self,
        session: AsyncSession,
        *,
        issue_id: int,
        classification_status: str,
        classification_reason: str,
        financial_final_blocker_override: bool | None = None,
        user_id: int | None = None,
        comment: str | None = None,
        mapped_sku_id: int | None = None,
    ) -> DataQualityIssue:
        issue = await self.get_issue(session, issue_id=issue_id)
        if issue is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Data quality issue not found")
        normalized_status = self._normalize_classification_status(classification_status)
        if normalized_status not in self.CLASSIFICATION_STATUSES:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400, detail="Unsupported classification status"
            )
        if normalized_status == "ignored_with_reason" and not (
            classification_reason.strip() or comment
        ):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400, detail="Ignored issues require an explicit reason"
            )
        payload = dict(issue.payload or {})
        payload["classificationStatus"] = normalized_status
        payload["classificationReason"] = classification_reason
        if comment:
            comments = list(payload.get("comments") or [])
            comments.append(
                {
                    "text": comment,
                    "createdAt": utcnow().isoformat(),
                    "kind": "classification",
                }
            )
            payload["comments"] = comments
        if mapped_sku_id is not None:
            payload["mappedSkuId"] = mapped_sku_id
        issue.payload = payload
        issue.classification_status = normalized_status
        issue.classification_reason = classification_reason
        issue.classified_at = utcnow()
        if user_id is not None:
            issue.classified_by_user_id = user_id
        if financial_final_blocker_override is not None:
            issue.financial_final_blocker_override = financial_final_blocker_override
        issue.detected_at = utcnow()
        self._refresh_issue_final_blocker_state(issue)
        await session.flush()
        await self._sync_dynamic_problem_instance(session, issue)
        return issue

    async def list_issues(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        only_open: bool = False,
        codes: list[str] | None = None,
        issue_types: list[str] | None = None,
        severities: list[str] | None = None,
        domains: list[str] | None = None,
        source_tables: list[str] | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        status: str | None = None,
        classification_statuses: list[str] | None = None,
        age_buckets: list[str] | None = None,
        detected_from: date | None = None,
        detected_to: date | None = None,
        financial_final_blocker: bool | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> Page[DataQualityIssueRead]:
        normalized_codes = self._normalize_multi_values(codes)
        normalized_issue_types = self._normalize_multi_values(issue_types)
        normalized_severities = self._normalize_multi_values(severities)
        normalized_domains = self._normalize_multi_values(domains)
        normalized_source_tables = self._normalize_multi_values(source_tables)
        if normalized_issue_types:
            normalized_codes = list(
                dict.fromkeys((normalized_codes or []) + normalized_issue_types)
            )
        if normalized_codes:
            normalized_codes = [
                code
                for code in normalized_codes
                if not self._is_hidden_user_issue_code(code)
            ] or ["__hidden_issue_code__"]
        if financial_final_blocker:
            blocker_codes = self._financial_final_blocker_codes()
            normalized_codes = sorted(
                blocker_codes.intersection(normalized_codes)
                if normalized_codes
                else blocker_codes
            )
            if not normalized_codes:
                normalized_codes = ["__hidden_issue_code__"]
            final_blocker_severities = self.FINANCIAL_FINAL_FILTER_SEVERITIES
            normalized_severities = sorted(
                final_blocker_severities.intersection(normalized_severities)
                if normalized_severities
                else final_blocker_severities
            )
        if financial_final_blocker is None:
            page = await self.repo.list_filtered(
                session,
                account_id=account_id,
                only_open=only_open,
                codes=normalized_codes,
                excluded_codes=sorted(self.HIDDEN_USER_ISSUE_CODES),
                severities=normalized_severities,
                domains=normalized_domains,
                source_tables=normalized_source_tables,
                sku_id=sku_id,
                nm_id=nm_id,
                status=status,
                classification_statuses=classification_statuses,
                financial_final_blocker=None,
                age_buckets=age_buckets,
                detected_from=detected_from,
                detected_to=detected_to,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            )
            normalized_items = [
                self._normalize_issue_runtime_flags(issue)
                for issue in page.items
                if not self._is_hidden_user_issue_code(issue.code)
            ]
            return Page(
                total=page.total
                if len(normalized_items) == len(page.items)
                else len(normalized_items),
                limit=page.limit,
                offset=page.offset,
                items=[
                    DataQualityIssueRead.from_issue(issue) for issue in normalized_items
                ],
            )

        fetch_limit = max(limit + offset, 10_000)
        raw_page = await self.repo.list_filtered(
            session,
            account_id=account_id,
            only_open=only_open,
            codes=normalized_codes,
            excluded_codes=sorted(self.HIDDEN_USER_ISSUE_CODES),
            severities=normalized_severities,
            domains=normalized_domains,
            source_tables=normalized_source_tables,
            sku_id=sku_id,
            nm_id=nm_id,
            status=status,
            classification_statuses=classification_statuses,
            financial_final_blocker=None,
            age_buckets=age_buckets,
            detected_from=detected_from,
            detected_to=detected_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=fetch_limit,
            offset=0,
        )
        filtered_items = [
            self._normalize_issue_runtime_flags(issue)
            for issue in raw_page.items
            if not self._is_hidden_user_issue_code(issue.code)
            and self._issue_is_effective_financial_final_blocker(issue)
            is financial_final_blocker
        ]
        return Page(
            total=len(filtered_items),
            limit=limit,
            offset=offset,
            items=[
                DataQualityIssueRead.from_issue(issue)
                for issue in filtered_items[offset : offset + limit]
            ],
        )

    async def list_investigator_issues(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        code: str,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[DataQualityIssueRead]:
        return await self.list_issues(
            session,
            account_id=account_id,
            only_open=True,
            codes=[code],
            limit=limit,
            offset=offset,
            sort_by="detected_at",
            sort_dir="desc",
        )

    async def list_issue_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
    ) -> dict[str, object]:
        stmt = select(
            DataQualityIssue.code.label("code"),
            DataQualityIssue.domain.label("domain"),
            DataQualityIssue.severity.label("severity"),
            DataQualityIssue.source_table.label("source_table"),
            func.count(DataQualityIssue.id)
            .filter(DataQualityIssue.resolved_at.is_(None))
            .label("open_count"),
            func.count(DataQualityIssue.id)
            .filter(
                DataQualityIssue.resolved_at.is_(None),
                DataQualityIssue.effective_financial_final_blocker.is_(True),
            )
            .label("blocking_open_count"),
            func.count(DataQualityIssue.id)
            .filter(DataQualityIssue.resolved_at.is_not(None))
            .label("resolved_count"),
            func.min(DataQualityIssue.detected_at).label("first_seen"),
            func.max(DataQualityIssue.detected_at).label("last_seen"),
        )
        if account_id is not None:
            stmt = stmt.where(DataQualityIssue.account_id == account_id)
        stmt = stmt.where(
            DataQualityIssue.code.notin_(sorted(self.HIDDEN_USER_ISSUE_CODES))
        )
        stmt = stmt.group_by(
            DataQualityIssue.code,
            DataQualityIssue.domain,
            DataQualityIssue.severity,
            DataQualityIssue.source_table,
        )
        result = await session.execute(stmt)
        if not hasattr(result, "mappings"):
            issues = [
                self._normalize_issue_runtime_flags(issue) for issue in result.scalars()
            ]
            return self._issue_summary_payload_from_issues(issues)
        items = [
            {
                "code": str(row["code"] or ""),
                "domain": str(row["domain"] or ""),
                "severity": str(row["severity"] or ""),
                "source_table": row["source_table"],
                "open_count": int(row["open_count"] or 0),
                "blocking_open_count": int(row["blocking_open_count"] or 0),
                "resolved_count": int(row["resolved_count"] or 0),
                "first_seen": row["first_seen"],
                "last_seen": row["last_seen"],
                "business_impact": str(
                    issue_bucket_meta(str(row["code"] or "")).get("business_impact")
                    or ""
                ),
                "recommended_fix": str(
                    issue_bucket_meta(str(row["code"] or "")).get("recommended_fix")
                    or ""
                ),
            }
            for row in result.mappings().all()
        ]
        return self._issue_summary_payload_from_items(items)

    def _issue_summary_payload_from_issues(
        self, issues: list[DataQualityIssue]
    ) -> dict[str, object]:
        grouped: dict[tuple[str, str, str, str | None], dict[str, object]] = {}
        for issue in issues:
            if self._is_hidden_user_issue_code(issue.code):
                continue
            key = (
                str(issue.code or ""),
                str(issue.domain or ""),
                str(issue.severity or ""),
                issue.source_table,
            )
            bucket = grouped.setdefault(
                key,
                {
                    "code": key[0],
                    "domain": key[1],
                    "severity": key[2],
                    "source_table": key[3],
                    "open_count": 0,
                    "blocking_open_count": 0,
                    "resolved_count": 0,
                    "first_seen": issue.detected_at,
                    "last_seen": issue.detected_at,
                    "business_impact": str(
                        issue_bucket_meta(key[0]).get("business_impact") or ""
                    ),
                    "recommended_fix": str(
                        issue_bucket_meta(key[0]).get("recommended_fix") or ""
                    ),
                },
            )
            bucket["first_seen"] = (
                min(bucket["first_seen"], issue.detected_at)
                if bucket["first_seen"] is not None
                else issue.detected_at
            )
            bucket["last_seen"] = (
                max(bucket["last_seen"], issue.detected_at)
                if bucket["last_seen"] is not None
                else issue.detected_at
            )
            if issue.resolved_at is None:
                bucket["open_count"] = int(bucket["open_count"]) + 1
                if self._issue_is_effective_financial_final_blocker(issue):
                    bucket["blocking_open_count"] = (
                        int(bucket["blocking_open_count"]) + 1
                    )
            else:
                bucket["resolved_count"] = int(bucket["resolved_count"]) + 1
        items = sorted(
            grouped.values(),
            key=lambda item: item["last_seen"] or datetime.min,
            reverse=True,
        )
        return self._issue_summary_payload_from_items(items)

    def _issue_summary_payload_from_items(
        self, items: list[dict[str, object]]
    ) -> dict[str, object]:
        items = sorted(
            items, key=lambda item: item["last_seen"] or datetime.min, reverse=True
        )
        open_issues_total = sum(int(item["open_count"]) for item in items)
        blocking_open_issues_total = sum(
            int(item["blocking_open_count"]) for item in items
        )
        financial_final_blockers_total = blocking_open_issues_total
        by_severity: dict[str, int] = defaultdict(int)
        by_issue_type: dict[str, int] = defaultdict(int)
        by_source_table: dict[str, int] = defaultdict(int)
        by_group: dict[str, int] = defaultdict(int)
        by_group_blocking: dict[str, int] = defaultdict(int)
        by_group_all_open: dict[str, int] = defaultdict(int)
        for item in items:
            open_count = int(item["open_count"])
            blocking_count = int(item["blocking_open_count"])
            severity = str(item["severity"])
            code = str(item["code"])
            source_table = str(item["source_table"] or "unknown")
            group = self._issue_group(code)
            by_severity[severity] += open_count
            by_issue_type[code] += open_count
            by_source_table[source_table] += open_count
            by_group[group] += open_count
            by_group_all_open[group] += open_count
            by_group_blocking[group] += blocking_count
        return {
            "items": items,
            "open_issues_total": open_issues_total,
            "all_open_issues_total": open_issues_total,
            "blocking_open_issues_total": blocking_open_issues_total,
            "financial_final_blockers_total": financial_final_blockers_total,
            "by_severity": dict(by_severity),
            "by_issue_type": dict(by_issue_type),
            "by_source_table": dict(by_source_table),
            "by_group": dict(by_group),
            "by_group_blocking": dict(by_group_blocking),
            "by_group_all_open": dict(by_group_all_open),
        }

    async def bulk_update_issues(
        self,
        session: AsyncSession,
        *,
        ids: list[int],
        action: str,
        comment: str | None = None,
        classification_status: str | None = None,
        classification_reason: str | None = None,
        financial_final_blocker_override: bool | None = None,
        mapped_sku_id: int | None = None,
        user_id: int | None = None,
    ) -> int:
        updated = 0
        normalized_action = action.strip().lower()
        for issue_id in ids:
            try:
                if normalized_action == "resolve":
                    await self.resolve_issue_by_id(
                        session, issue_id=issue_id, comment=comment
                    )
                elif normalized_action == "reopen":
                    await self.reopen_issue_by_id(
                        session, issue_id=issue_id, comment=comment
                    )
                elif normalized_action == "comment":
                    await self.comment_issue_by_id(
                        session, issue_id=issue_id, comment=comment or ""
                    )
                elif normalized_action == "classify":
                    if not classification_status or classification_reason is None:
                        raise ValueError("classification parameters are required")
                    await self.classify_issue_by_id(
                        session,
                        issue_id=issue_id,
                        classification_status=classification_status,
                        classification_reason=classification_reason,
                        financial_final_blocker_override=financial_final_blocker_override,
                        user_id=user_id,
                        comment=comment,
                        mapped_sku_id=mapped_sku_id,
                    )
                else:
                    raise ValueError(f"Unsupported bulk action: {action}")
                updated += 1
            except Exception:
                continue
        return updated

    async def resolve_issues(
        self,
        session: AsyncSession,
        *,
        domain: str,
        codes: list[str],
        account_id: int | None = None,
        entity_key: str | None = None,
    ) -> int:
        if not codes:
            return 0
        stmt = select(DataQualityIssue).where(
            DataQualityIssue.domain == domain,
            DataQualityIssue.code.in_(codes),
            DataQualityIssue.resolved_at.is_(None),
        )
        if account_id is not None:
            stmt = stmt.where(DataQualityIssue.account_id == account_id)
        if entity_key is not None:
            stmt = stmt.where(DataQualityIssue.entity_key == entity_key)
        result = await session.execute(stmt)
        if not hasattr(result, "scalars"):
            resolved_count = int(getattr(result, "rowcount", 0) or 0)
            if self._run_metrics is not None:
                self._run_metrics["resolved_count"] += resolved_count
            return resolved_count
        issues = list(result.scalars())
        resolved_at = utcnow()
        for issue in issues:
            issue.resolved_at = resolved_at
            self._refresh_issue_final_blocker_state(issue)
            await session.flush()
            await self._sync_dynamic_problem_instance(session, issue)
        resolved_count = len(issues)
        if self._run_metrics is not None:
            self._run_metrics["resolved_count"] += resolved_count
        return resolved_count

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value or 0))

    @staticmethod
    def _percent(
        part: Decimal | int | float | None, whole: Decimal | int | float | None
    ) -> Decimal:
        whole_decimal = Decimal(str(whole or 0))
        if whole_decimal <= 0:
            return Decimal("0")
        return (Decimal(str(part or 0)) / whole_decimal) * Decimal("100")

    async def _load_account_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, object]:
        settings_json = (
            await session.execute(
                select(UserBusinessSetting.settings_json).where(
                    UserBusinessSetting.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        if not isinstance(settings_json, dict):
            return {}
        return dict(settings_json)

    async def _expense_totals(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Decimal]:
        finance_stmt = select(
            func.coalesce(
                func.sum(MartExpenseDaily.amount).filter(
                    MartExpenseDaily.amount_sign == "expense"
                ),
                0,
            ),
            func.coalesce(
                func.sum(MartExpenseDaily.amount).filter(
                    MartExpenseDaily.expense_category == "wb_logistics"
                ),
                0,
            ),
            func.coalesce(
                func.sum(MartExpenseDaily.amount).filter(
                    MartExpenseDaily.expense_category == "wb_logistics_rebill"
                ),
                0,
            ),
            func.coalesce(
                func.sum(MartExpenseDaily.amount).filter(
                    MartExpenseDaily.expense_category == "marketing_deduction"
                ),
                0,
            ),
            func.coalesce(func.count(MartExpenseDaily.id), 0),
        ).where(
            MartExpenseDaily.account_id == account_id,
            MartExpenseDaily.stat_date >= date_from,
            MartExpenseDaily.stat_date <= date_to,
            MartExpenseDaily.expense_category != "additional_payment",
        )
        (
            finance_total,
            logistics_total,
            logistics_rebill_total,
            marketing_total,
            expense_row_count,
        ) = (await session.execute(finance_stmt)).one()
        seller_stmt = select(
            func.coalesce(func.sum(MartSKUDaily.seller_cogs), 0),
            func.coalesce(func.sum(MartSKUDaily.seller_other_expense), 0),
            func.coalesce(
                func.sum(
                    case(
                        (
                            func.coalesce(MartSKUDaily.ad_spend_final, 0)
                            > func.coalesce(MartSKUDaily.ad_spend_finance, 0),
                            func.coalesce(MartSKUDaily.ad_spend_final, 0)
                            - func.coalesce(MartSKUDaily.ad_spend_finance, 0),
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        ).where(
            MartSKUDaily.account_id == account_id,
            MartSKUDaily.stat_date >= date_from,
            MartSKUDaily.stat_date <= date_to,
        )
        seller_cogs_total, seller_other_total, ads_operational_total = (
            await session.execute(seller_stmt)
        ).one()
        total_wb_expenses = self._decimal(finance_total)
        total_seller_expenses = self._decimal(seller_cogs_total) + self._decimal(
            seller_other_total
        )
        total_ad_expenses = self._decimal(marketing_total) + self._decimal(
            ads_operational_total
        )
        logistics_combined = self._decimal(logistics_total) + self._decimal(
            logistics_rebill_total
        )
        return {
            "total_expenses": total_wb_expenses
            + total_seller_expenses
            + total_ad_expenses,
            "total_wb_expenses": total_wb_expenses,
            "total_seller_expenses": total_seller_expenses,
            "total_ad_expenses": total_ad_expenses,
            "logistics_total": logistics_combined,
            "expense_row_count": self._decimal(expense_row_count),
        }

    @staticmethod
    def _severity_for_age(
        age_days: int,
        *,
        pending_days: int = 2,
        warning_days: int = 7,
    ) -> tuple[str, str]:
        if age_days <= pending_days:
            return "pending", "info"
        if age_days <= warning_days:
            return "warning", "warning"
        return "error", "error"

    @staticmethod
    def _issue_is_classified(issue: DataQualityIssue) -> bool:
        payload = dict(issue.payload or {})
        return (
            DataQualityService._normalize_classification_status(
                getattr(issue, "classification_status", None)
                or payload.get("classificationStatus")
                or payload.get("resolutionStatus")
            )
            in DataQualityService.CLASSIFIED_STATUSES
        )

    @staticmethod
    def _classified_payload(
        *,
        classification_status: str,
        classification_reason: str,
        source_domains: list[str] | None = None,
        candidate_sku_ids: list[int] | None = None,
        age_bucket: str | None = None,
        **extra: object,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "classificationStatus": classification_status,
            "classificationReason": classification_reason,
        }
        if source_domains:
            payload["sourceDomains"] = source_domains
        if candidate_sku_ids:
            payload["candidateSkuIds"] = candidate_sku_ids
        if age_bucket is not None:
            payload["ageBucket"] = age_bucket
        payload.update(extra)
        return payload

    async def _attempt_relink_missing_chrt_ids(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        sku_rows = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                        CoreSKU.chrt_id.is_(None),
                    )
                )
            ).scalars()
        )
        if not sku_rows:
            return 0
        card_ids_by_nm = {
            row.nm_id: row.id
            for row in (
                await session.execute(
                    select(WBProductCard.nm_id, WBProductCard.id).where(
                        WBProductCard.account_id == account_id,
                        WBProductCard.nm_id.in_(
                            [sku.nm_id for sku in sku_rows if sku.nm_id is not None]
                        ),
                    )
                )
            ).all()
        }
        size_rows = list(
            (
                await session.execute(
                    select(WBProductCardSize).where(
                        WBProductCardSize.account_id == account_id,
                        WBProductCardSize.product_card_id.in_(
                            list(card_ids_by_nm.values()) or [-1]
                        ),
                    )
                )
            ).scalars()
        )
        sizes_by_nm: dict[int, list[WBProductCardSize]] = defaultdict(list)
        product_nm_by_card_id = {
            card_id: nm_id for nm_id, card_id in card_ids_by_nm.items()
        }
        for size in size_rows:
            nm_id = product_nm_by_card_id.get(size.product_card_id)
            if nm_id is not None:
                sizes_by_nm[int(nm_id)].append(size)
        recent_barcodes_by_nm: dict[int, str] = {}
        recent_stock_rows = (
            await session.execute(
                select(WBStockSnapshotRow.nm_id, WBStockSnapshotRow.barcode).where(
                    WBStockSnapshotRow.account_id == account_id,
                    WBStockSnapshotRow.nm_id.in_(
                        [sku.nm_id for sku in sku_rows if sku.nm_id is not None]
                    ),
                    WBStockSnapshotRow.barcode.is_not(None),
                )
            )
        ).all()
        recent_order_rows = (
            await session.execute(
                select(WBOrder.nm_id, WBOrder.barcode).where(
                    WBOrder.account_id == account_id,
                    WBOrder.nm_id.in_(
                        [sku.nm_id for sku in sku_rows if sku.nm_id is not None]
                    ),
                    WBOrder.barcode.is_not(None),
                )
            )
        ).all()
        recent_sale_rows = (
            await session.execute(
                select(WBSale.nm_id, WBSale.barcode).where(
                    WBSale.account_id == account_id,
                    WBSale.nm_id.in_(
                        [sku.nm_id for sku in sku_rows if sku.nm_id is not None]
                    ),
                    WBSale.barcode.is_not(None),
                )
            )
        ).all()
        for nm_id, barcode in [
            *recent_stock_rows,
            *recent_order_rows,
            *recent_sale_rows,
        ]:
            if (
                nm_id is not None
                and barcode
                and int(nm_id) not in recent_barcodes_by_nm
            ):
                recent_barcodes_by_nm[int(nm_id)] = str(barcode)

        relinked = 0
        for sku in sku_rows:
            if sku.nm_id is None:
                continue
            candidates = sizes_by_nm.get(int(sku.nm_id), [])
            if not candidates:
                continue
            candidate_barcode = sku.barcode or recent_barcodes_by_nm.get(int(sku.nm_id))
            exact_matches = [
                size
                for size in candidates
                if candidate_barcode is not None
                and isinstance(size.skus, list)
                and candidate_barcode in size.skus
                and (sku.tech_size is None or sku.tech_size == size.tech_size)
            ]
            barcode_matches = [
                size
                for size in candidates
                if candidate_barcode is not None
                and isinstance(size.skus, list)
                and candidate_barcode in size.skus
            ]
            size_matches = [
                size
                for size in candidates
                if sku.tech_size is not None and sku.tech_size == size.tech_size
            ]
            if len(exact_matches) == 1:
                match = exact_matches[0]
            elif len(barcode_matches) == 1:
                match = barcode_matches[0]
            elif len(size_matches) == 1:
                match = size_matches[0]
            elif len(candidates) == 1:
                match = candidates[0]
            else:
                continue
            sku.chrt_id = match.chrt_id
            sku.size_id = sku.size_id or match.size_id
            sku.tech_size = sku.tech_size or match.tech_size
            if sku.barcode is None:
                if candidate_barcode is not None:
                    sku.barcode = str(candidate_barcode)
                elif isinstance(match.skus, list) and len(match.skus) == 1:
                    sku.barcode = str(match.skus[0])
            relinked += 1
        if relinked:
            await session.flush()
        return relinked

    @staticmethod
    def _extract_snapshot_price(payload: dict | None) -> Decimal | None:
        if not isinstance(payload, dict):
            return None
        sizes = payload.get("sizes")
        values = sizes if isinstance(sizes, list) else [payload]
        candidates: list[Decimal] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            value = (
                item.get("discountedPrice")
                or item.get("price")
                or item.get("basicPrice")
            )
            if value not in (None, ""):
                candidates.append(Decimal(str(value)))
        return min(candidates) if candidates else None

    async def run_checks(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
    ) -> dict[str, int]:
        self._run_metrics = {
            "opened_count": 0,
            "updated_count": 0,
            "resolved_count": 0,
        }
        accounts = (
            [await session.get(WBAccount, account_id)]
            if account_id is not None
            else list(
                (
                    await session.execute(
                        select(WBAccount).where(WBAccount.is_active.is_(True))
                    )
                ).scalars()
            )
        )
        checked_accounts = 0
        for account in accounts:
            if account is None:
                continue
            checked_accounts += 1
            await self._run_account_checks(session, account_id=account.id)
        active_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(DataQualityIssue)
                    .where(DataQualityIssue.resolved_at.is_(None))
                )
            ).scalar_one()
        )
        metrics = self._run_metrics
        self._run_metrics = None
        return {
            "checked_accounts": checked_accounts,
            "opened_count": metrics["opened_count"] if metrics else 0,
            "updated_count": metrics["updated_count"] if metrics else 0,
            "resolved_count": metrics["resolved_count"] if metrics else 0,
            "active_count": active_count,
        }

    async def _run_account_checks(
        self, session: AsyncSession, *, account_id: int
    ) -> None:
        today = utcnow().date()
        issue_codes = [
            "missing_manual_cost",
            "manual_cost_old_fields_used",
            "seller_other_expense_missing",
            "unmatched_sku",
            "duplicate_srid",
            "barcode_multiple_nm_id",
            "vendor_code_multiple_nm_id",
            "missing_chrt_id",
            "missed_load",
            "sync_date_mismatch",
            "manual_cost_overlap",
            "manual_cost_linked_to_inactive_sku",
            "manual_cost_ambiguous_match",
            "manual_cost_unresolved_sku",
            "stocks_task_not_ready",
            "stock_without_sales",
            "sales_without_stock",
            "order_without_sale_or_return",
            "price_zero_or_too_low",
            "sale_without_finance",
            "finance_without_sale",
            "ad_spend_without_sales",
            "ad_spend_without_sku",
            "expense_unclassified",
            "expense_logistics_missing",
            "expense_finance_report_missing",
            "expense_ad_double_count_risk",
            "expense_negative_unexpected",
            "expense_large_logistics_share",
            "expense_no_drilldown_rows",
            "dead_stock",
            "price_jump",
            "finance_reconciliation_mismatch",
        ]
        await self.resolve_issues(
            session, domain="data_quality", codes=issue_codes, account_id=account_id
        )
        await self.marts.refresh_account(
            session,
            account_id=account_id,
            date_from=today - timedelta(days=30),
            date_to=today,
        )

        await self._check_missing_manual_cost(
            session, account_id=account_id, today=today
        )
        await self._check_unmatched_sku(session, account_id=account_id)
        await self._check_duplicate_srid(session, account_id=account_id, today=today)
        await self._check_barcode_conflicts(session, account_id=account_id)
        await self._check_vendor_code_conflicts(session, account_id=account_id)
        await self._check_missing_chrt_id(session, account_id=account_id)
        await self._check_missed_load(session, account_id=account_id)
        await self._check_sync_date_alignment(session, account_id=account_id)
        await self._check_pending_stocks_task(session, account_id=account_id)
        await self._check_manual_cost_overlap(session, account_id=account_id)
        await self._check_manual_cost_linkage(session, account_id=account_id)
        await self._check_manual_cost_upload_warnings(session, account_id=account_id)
        await self._check_finance_reconciliation(
            session, account_id=account_id, today=today
        )
        await self._check_expense_finance_report_missing(
            session, account_id=account_id, today=today
        )
        await self._check_expense_logistics_missing(
            session, account_id=account_id, today=today
        )
        await self._check_expense_ad_double_count_risk(
            session, account_id=account_id, today=today
        )
        await self._check_expense_negative_unexpected(
            session, account_id=account_id, today=today
        )
        await self._check_expense_large_logistics_share(
            session, account_id=account_id, today=today
        )
        await self._check_expense_no_drilldown_rows(
            session, account_id=account_id, today=today
        )
        await self._check_stock_without_sales(
            session, account_id=account_id, today=today
        )
        await self._check_sales_without_stock(
            session, account_id=account_id, today=today
        )
        await self._check_order_without_sale_or_return(
            session, account_id=account_id, today=today
        )
        await self._check_price_zero_or_too_low(
            session, account_id=account_id, today=today
        )
        await self._check_ad_spend_without_sales(session, account_id=account_id)
        await self._check_ad_spend_without_sku(session, account_id=account_id)
        await self._check_dead_stock(session, account_id=account_id)
        await self._check_price_jump(session, account_id=account_id)
        await self._apply_issue_flags_to_marts(session, account_id=account_id)

    async def _check_missing_manual_cost(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= today - timedelta(days=30),
                        (MartSKUDaily.finance_rows > 0) | (MartSKUDaily.sale_rows > 0),
                        MartSKUDaily.has_manual_cost.is_(False),
                    )
                )
            ).scalars()
        )
        total_cost_rows = (
            await session.execute(
                select(func.count())
                .select_from(ManualCost)
                .where(ManualCost.account_id == account_id)
            )
        ).scalar_one()
        if total_cost_rows == 0:
            if rows:
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="missing_manual_cost",
                    message="По магазину не загружена себестоимость",
                    severity="warning",
                    entity_key=f"account:{account_id}",
                    payload={
                        "accountId": account_id,
                        "affectedSkuCount": len(
                            {(row.nm_id, row.vendor_code) for row in rows}
                        ),
                        "windowDays": 30,
                    },
                )
                return 1
            return 0
        touched = 0
        seen: set[str] = set()
        for row in rows:
            normalized_vendor = str(row.vendor_code or "").strip().casefold()
            entity_key = (
                f"sku:{row.sku_id}"
                if row.sku_id is not None
                else f"nm:{row.nm_id}|vendor:{normalized_vendor}"
            )
            if entity_key in seen:
                continue
            seen.add(entity_key)
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="missing_manual_cost",
                message="У активной карточки нет загруженной себестоимости",
                severity="warning",
                entity_key=entity_key,
                entity_type="sku",
                entity_id=row.sku_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_sku_daily",
                payload={
                    "nmId": row.nm_id,
                    "vendorCode": row.vendor_code,
                    "statDate": row.stat_date.isoformat(),
                },
            )
            touched += 1
        return touched

    async def _check_unmatched_sku(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        core_nm_ids = set(
            (
                await session.execute(
                    select(CoreSKU.nm_id).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.nm_id.is_not(None),
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        inactive_core_nm_ids = set(
            (
                await session.execute(
                    select(CoreSKU.nm_id).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.nm_id.is_not(None),
                        CoreSKU.is_active.is_(False),
                    )
                )
            ).scalars()
        )
        product_card_nm_ids = set(
            (
                await session.execute(
                    select(WBProductCard.nm_id).where(
                        WBProductCard.account_id == account_id,
                        WBProductCard.nm_id.is_not(None),
                    )
                )
            ).scalars()
        )
        ad_nm_ids = set(
            (
                await session.execute(
                    select(WBAdStatsDaily.nm_id).where(
                        WBAdStatsDaily.account_id == account_id,
                        WBAdStatsDaily.nm_id.is_not(None),
                    )
                )
            ).scalars()
        )
        mart_nm_ids = set(
            (
                await session.execute(
                    select(MartSKUDaily.nm_id).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.nm_id.is_not(None),
                    )
                )
            ).scalars()
        )
        finance_nm_ids = set(
            (
                await session.execute(
                    select(WBRealizationReportRow.nm_id).where(
                        WBRealizationReportRow.account_id == account_id,
                        WBRealizationReportRow.nm_id.is_not(None),
                    )
                )
            ).scalars()
        )
        supply_nm_ids = set(
            (
                await session.execute(
                    select(WBSupplyGood.nm_id).where(
                        WBSupplyGood.account_id == account_id,
                        WBSupplyGood.nm_id.is_not(None),
                    )
                )
            ).scalars()
        )
        orders_current = orders_current_subquery("dq_orders_current")
        sales_current = sales_current_subquery("dq_sales_current")
        order_nm_ids = {
            row["nm_id"]
            for row in (
                await session.execute(
                    select(orders_current).where(
                        orders_current.c.account_id == account_id
                    )
                )
            ).mappings()
            if row.get("nm_id") is not None
        }
        sale_nm_ids = {
            row["nm_id"]
            for row in (
                await session.execute(
                    select(sales_current).where(
                        sales_current.c.account_id == account_id
                    )
                )
            ).mappings()
            if row.get("nm_id") is not None
        }
        stock_nm_ids = set(
            (
                await session.execute(
                    select(WBStockSnapshotRow.nm_id).where(
                        WBStockSnapshotRow.account_id == account_id,
                        WBStockSnapshotRow.nm_id.is_not(None),
                    )
                )
            ).scalars()
        )
        touched = 0
        for nm_id in sorted(
            (
                ad_nm_ids
                | mart_nm_ids
                | finance_nm_ids
                | supply_nm_ids
                | order_nm_ids
                | sale_nm_ids
                | stock_nm_ids
            )
            - core_nm_ids
        ):
            source_domains = sorted(
                domain
                for domain, values in {
                    "ads": ad_nm_ids,
                    "marts": mart_nm_ids,
                    "finance": finance_nm_ids,
                    "supplies": supply_nm_ids,
                    "orders": order_nm_ids,
                    "sales": sale_nm_ids,
                    "stocks": stock_nm_ids,
                }.items()
                if nm_id in values
            )
            candidate_sku_ids = list(
                (
                    await session.execute(
                        select(CoreSKU.id).where(
                            CoreSKU.account_id == account_id,
                            CoreSKU.nm_id == nm_id,
                        )
                    )
                ).scalars()
            )
            classification_status = "detected"
            classification_reason = "missing_core_sku"
            if nm_id in inactive_core_nm_ids:
                classification_reason = "archived_candidate"
            elif nm_id not in product_card_nm_ids:
                classification_status = "archived"
                classification_reason = "source_level_missing_nm_id"
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="unmatched_sku",
                message="Есть данные по продажам или расходам, но карточка не привязана",
                severity="error",
                entity_key=f"nm:{nm_id}",
                entity_type="sku",
                nm_id=nm_id,
                payload=self._classified_payload(
                    classification_status=classification_status,
                    classification_reason=classification_reason,
                    source_domains=source_domains,
                    candidate_sku_ids=[int(value) for value in candidate_sku_ids],
                    nmId=nm_id,
                    sourceKind="source_level",
                ),
            )
            touched += 1
        return touched

    async def _check_duplicate_srid(
        self, session: AsyncSession, *, account_id: int, today: date
    ) -> int:
        srid_map: dict[str, set[int | None]] = defaultdict(set)
        orders_current = orders_current_subquery()
        sales_current = sales_current_subquery()
        current_order_rows = (
            await session.execute(
                select(orders_current.c.srid, orders_current.c.nm_id).where(
                    orders_current.c.account_id == account_id,
                    orders_current.c.last_change_date
                    >= datetime.combine(
                        today - timedelta(days=30), datetime.min.time()
                    ),
                )
            )
        ).all()
        current_sale_rows = (
            await session.execute(
                select(sales_current.c.srid, sales_current.c.nm_id).where(
                    sales_current.c.account_id == account_id,
                    sales_current.c.last_change_date
                    >= datetime.combine(
                        today - timedelta(days=30), datetime.min.time()
                    ),
                )
            )
        ).all()
        for srid, nm_id in [*current_order_rows, *current_sale_rows]:
            if srid:
                srid_map[srid].add(nm_id)
        touched = 0
        for srid, nm_ids in srid_map.items():
            if len({nm for nm in nm_ids if nm is not None}) <= 1:
                continue
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="duplicate_srid",
                message="Один заказ связан с несколькими артикулами",
                severity="warning",
                entity_key=srid,
                entity_type="order",
                source_table="v_wb_orders_current",
                payload={
                    "srid": srid,
                    "nmIds": sorted(nm for nm in nm_ids if nm is not None),
                },
            )
            touched += 1
        return touched

    async def _check_barcode_conflicts(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        rows = (
            await session.execute(
                select(CoreSKU.barcode, CoreSKU.nm_id).where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.is_active.is_(True),
                    CoreSKU.barcode.is_not(None),
                    CoreSKU.nm_id.is_not(None),
                )
            )
        ).all()
        barcode_map: dict[str, set[int]] = defaultdict(set)
        for barcode, nm_id in rows:
            if barcode and nm_id is not None:
                barcode_map[str(barcode)].add(int(nm_id))
        touched = 0
        for barcode, nm_ids in barcode_map.items():
            if len(nm_ids) <= 1:
                continue
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="barcode_multiple_nm_id",
                message="Один штрихкод привязан к нескольким артикулам WB",
                severity="warning",
                entity_key=f"barcode:{barcode}",
                entity_type="sku",
                source_table="core_sku",
                payload={"barcode": barcode, "nmIds": sorted(nm_ids)},
            )
            touched += 1
        return touched

    async def _check_vendor_code_conflicts(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        rows = (
            await session.execute(
                select(CoreSKU.vendor_code, CoreSKU.nm_id).where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.is_active.is_(True),
                    CoreSKU.vendor_code.is_not(None),
                    CoreSKU.nm_id.is_not(None),
                )
            )
        ).all()
        vendor_map: dict[str, set[int]] = defaultdict(set)
        for vendor_code, nm_id in rows:
            if vendor_code and nm_id is not None:
                vendor_map[str(vendor_code)].add(int(nm_id))
        touched = 0
        for vendor_code, nm_ids in vendor_map.items():
            if len(nm_ids) <= 1:
                continue
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="vendor_code_multiple_nm_id",
                message="Один артикул продавца привязан к нескольким артикулам WB",
                severity="warning",
                entity_key=f"vendor:{vendor_code}",
                entity_type="sku",
                source_table="core_sku",
                payload={"vendorCode": vendor_code, "nmIds": sorted(nm_ids)},
            )
            touched += 1
        return touched

    async def _check_missing_chrt_id(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        await self._attempt_relink_missing_chrt_ids(session, account_id=account_id)
        sku_rows = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                        CoreSKU.chrt_id.is_(None),
                    )
                )
            ).scalars()
        )
        touched = 0
        for sku in sku_rows:
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="missing_chrt_id",
                message="У позиции не заполнен идентификатор размера",
                severity="warning",
                entity_key=f"sku:{sku.id}",
                entity_type="sku",
                entity_id=sku.id,
                sku_id=sku.id,
                nm_id=sku.nm_id,
                source_table="core_sku",
                payload=self._classified_payload(
                    classification_status="classified",
                    classification_reason="missing_chrt_id",
                    skuId=sku.id,
                    nmId=sku.nm_id,
                    vendorCode=sku.vendor_code,
                    barcode=sku.barcode,
                ),
            )
            touched += 1
        return touched

    async def _enabled_domains(
        self, session: AsyncSession, *, account_id: int
    ) -> set[str]:
        tokens = list(
            (
                await session.execute(
                    select(WBAPIToken.category).where(
                        WBAPIToken.account_id == account_id,
                        WBAPIToken.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        categories = {str(category) for category in tokens}
        mapping = {
            "product_cards": {WBAPICategory.CONTENT.value},
            "prices": {WBAPICategory.PRICES.value},
            "orders": {WBAPICategory.STATISTICS.value},
            "sales": {WBAPICategory.STATISTICS.value},
            "stocks": {WBAPICategory.ANALYTICS.value},
            "finance": {WBAPICategory.FINANCE.value},
            "supplies": {WBAPICategory.SUPPLIES.value},
            "ads": {WBAPICategory.PROMOTION.value},
            "promotions": {WBAPICategory.PROMOTION.value},
            "analytics": {WBAPICategory.ANALYTICS.value},
            "tariffs": {WBAPICategory.TARIFFS.value},
            "logistics": {
                WBAPICategory.ANALYTICS.value,
                WBAPICategory.SUPPLIES.value,
                WBAPICategory.MARKETPLACE.value,
            },
            "documents": {WBAPICategory.DOCUMENTS.value},
        }
        return {
            domain
            for domain, required_categories in mapping.items()
            if categories & required_categories
        }

    async def _check_missed_load(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        thresholds = {
            "orders": 2,
            "sales": 2,
            "stocks": 6,
            "product_cards": 36,
            "prices": 24,
            "finance": 48,
            "supplies": 48,
            "ads": 24,
            "promotions": 24,
            "analytics": 6,
            "tariffs": 48,
            "logistics": 48,
            "documents": 48,
        }
        enabled_domains = await self._enabled_domains(session, account_id=account_id)
        cursors = list(
            (
                await session.execute(
                    select(WBSyncCursor).where(
                        WBSyncCursor.account_id == account_id,
                        WBSyncCursor.cursor_key == "default",
                    )
                )
            ).scalars()
        )
        cursor_by_domain = {cursor.domain: cursor for cursor in cursors}
        latest_runs = list(
            (
                await session.execute(
                    select(WBSyncRun)
                    .where(WBSyncRun.account_id == account_id)
                    .order_by(WBSyncRun.id.desc())
                )
            ).scalars()
        )
        latest_run_by_domain: dict[str, WBSyncRun] = {}
        for run in latest_runs:
            latest_run_by_domain.setdefault(run.domain, run)
        touched = 0
        now = utcnow()
        for domain, threshold_hours in thresholds.items():
            if domain not in enabled_domains:
                continue
            cursor = cursor_by_domain.get(domain)
            latest_run = latest_run_by_domain.get(domain)
            activity_at = cursor.last_synced_at if cursor is not None else None
            if latest_run is not None:
                run_activity_at = latest_run.finished_at or latest_run.started_at
                if activity_at is None or (
                    run_activity_at is not None and run_activity_at > activity_at
                ):
                    activity_at = run_activity_at
            if cursor is None or cursor.last_synced_at is None:
                if activity_at is None:
                    await self.open_issue(
                        session,
                        account_id=account_id,
                        domain="data_quality",
                        code="missed_load",
                        message=f"По разделу {domain} еще не было полной загрузки",
                        severity="warning",
                        entity_key=domain,
                        payload={"domain": domain},
                    )
                    touched += 1
                    continue
            if activity_at is None:
                continue
            age_hours = (now - activity_at).total_seconds() / 3600
            if age_hours > threshold_hours:
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="missed_load",
                    message=f"По разделу {domain} данные давно не обновлялись",
                    severity="warning",
                    entity_key=domain,
                    payload={
                        "domain": domain,
                        "ageHours": round(age_hours, 2),
                        "thresholdHours": threshold_hours,
                        "cursorStatus": cursor.status if cursor is not None else None,
                        "latestRunStatus": latest_run.status
                        if latest_run is not None
                        else None,
                    },
                )
                touched += 1
        return touched

    @staticmethod
    def _sync_watermark_value(value: object) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            parsed = value
        else:
            try:
                parsed = parse_datetime(value)
            except (TypeError, ValueError):
                return None
        if parsed is None:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    @classmethod
    def _sync_watermark_from_cursor(
        cls, cursor: WBSyncCursor | None
    ) -> datetime | None:
        if cursor is None or not isinstance(cursor.cursor_value, dict):
            return None
        for key in (
            "lastChangeDate",
            "snapshotAt",
            "completedAt",
            "dateTo",
            "endTime",
            "endDate",
            "lastRunAt",
            "syncedAt",
            "collectedAt",
            "updatedAt",
        ):
            parsed = cls._sync_watermark_value(cursor.cursor_value.get(key))
            if parsed is not None:
                return parsed
        return None

    async def _check_sync_date_alignment(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        enabled_domains = await self._enabled_domains(session, account_id=account_id)
        cursors = list(
            (
                await session.execute(
                    select(WBSyncCursor).where(
                        WBSyncCursor.account_id == account_id,
                        WBSyncCursor.cursor_key == "default",
                    )
                )
            ).scalars()
        )
        cursor_by_domain = {str(cursor.domain): cursor for cursor in cursors}
        touched = 0
        for rule in self.SYNC_DATE_ALIGNMENT_RULES:
            rule_domains = [
                str(domain)
                for domain in rule["domains"]  # type: ignore[index]
                if str(domain) in enabled_domains
            ]
            if len(rule_domains) < 2:
                continue
            available = [
                (domain, watermark)
                for domain in rule_domains
                if (
                    watermark := self._sync_watermark_from_cursor(
                        cursor_by_domain.get(domain)
                    )
                )
                is not None
            ]
            if len(available) < 2:
                continue
            newest_domain, newest_at = max(available, key=lambda item: item[1])
            oldest_domain, oldest_at = min(available, key=lambda item: item[1])
            delta_hours = (newest_at - oldest_at).total_seconds() / 3600
            threshold_hours = float(rule["max_delta_hours"])
            if delta_hours <= threshold_hours:
                continue
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="sync_date_mismatch",
                message=(
                    f"{rule['label']}: даты WB-источников расходятся. "
                    f"{oldest_domain} отстаёт от {newest_domain} на "
                    f"{round(delta_hours, 2)} ч."
                ),
                severity="warning",
                entity_key=str(rule["key"]),
                payload={
                    "rule": rule["key"],
                    "domains": rule_domains,
                    "oldestDomain": oldest_domain,
                    "oldestAt": oldest_at.isoformat(),
                    "newestDomain": newest_domain,
                    "newestAt": newest_at.isoformat(),
                    "deltaHours": round(delta_hours, 2),
                    "thresholdHours": threshold_hours,
                },
            )
            touched += 1
        return touched

    async def _check_pending_stocks_task(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        latest_stocks_run = (
            await session.execute(
                select(WBSyncRun)
                .where(
                    WBSyncRun.account_id == account_id,
                    WBSyncRun.domain == "stocks",
                )
                .order_by(WBSyncRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if latest_stocks_run is not None and latest_stocks_run.status == "completed":
            await self.resolve_issues(
                session,
                domain="data_quality",
                codes=["stocks_task_not_ready", "stocks_task_failed"],
                account_id=account_id,
            )
            await self.resolve_issues(
                session,
                domain="stocks",
                codes=["stocks_task_not_ready", "stocks_task_failed"],
                account_id=account_id,
            )
            return 0
        cursor = (
            await session.execute(
                select(WBSyncCursor).where(
                    WBSyncCursor.account_id == account_id,
                    WBSyncCursor.domain == "stocks",
                    WBSyncCursor.cursor_key == "pending_task",
                    WBSyncCursor.status == "running",
                )
            )
        ).scalar_one_or_none()
        if cursor is None:
            return 0
        await self.open_issue(
            session,
            account_id=account_id,
            domain="data_quality",
            code="stocks_task_not_ready",
            message="Загрузка остатков еще не завершилась",
            severity="info",
            entity_key="stocks:pending_task",
            payload=self._classified_payload(
                classification_status="classified",
                classification_reason="expected_pending_task",
                age_bucket="pending",
                sourceKind="source_level",
                cursorValue=cursor.cursor_value,
            ),
        )
        return 1

    async def _check_manual_cost_overlap(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        cost_rows = list(
            (
                await session.execute(
                    select(ManualCost)
                    .where(ManualCost.account_id == account_id)
                    .order_by(ManualCost.sku_id, ManualCost.valid_from)
                )
            ).scalars()
        )
        touched = 0
        grouped: dict[int, list[ManualCost]] = defaultdict(list)
        for row in cost_rows:
            if row.sku_id is not None:
                grouped[row.sku_id].append(row)
        for sku_id, rows in grouped.items():
            previous: ManualCost | None = None
            for row in rows:
                if previous is None:
                    previous = row
                    continue
                previous_to = previous.valid_to or date.max
                current_from = row.valid_from or date.min
                if previous_to >= current_from:
                    await self.open_issue(
                        session,
                        account_id=account_id,
                        domain="data_quality",
                        code="manual_cost_overlap",
                        message="По одной карточке загружено несколько пересекающихся строк себестоимости",
                        severity="warning",
                        entity_key=f"sku:{sku_id}",
                        payload={
                            "skuId": sku_id,
                            "sourceKind": "source_level",
                            "previousRowId": previous.id,
                            "currentRowId": row.id,
                        },
                    )
                    touched += 1
                    break
                previous = row
        return touched

    @staticmethod
    def _resolve_manual_cost_candidates(
        sku_index: dict[str, dict[object, list[CoreSKU]]],
        *,
        cost: ManualCost,
    ) -> tuple[list[CoreSKU], str | None]:
        rules: list[tuple[str, list[CoreSKU]]] = [
            (
                "vendor_code+barcode+tech_size",
                sku_index["vendor_barcode_size"].get(
                    (cost.vendor_code, cost.barcode, cost.tech_size),
                    [],
                ),
            ),
            (
                "nm_id+barcode",
                sku_index["nm_barcode"].get((cost.nm_id, cost.barcode), []),
            ),
            (
                "barcode",
                sku_index["barcode"].get(cost.barcode, []),
            ),
            (
                "nm_id+tech_size",
                sku_index["nm_size"].get((cost.nm_id, cost.tech_size), []),
            ),
            (
                "vendor_code+tech_size",
                sku_index["vendor_size"].get((cost.vendor_code, cost.tech_size), []),
            ),
            (
                "vendor_code",
                sku_index["vendor"].get(cost.vendor_code, []),
            ),
        ]
        for rule, matches in rules:
            if matches:
                return matches, rule
        return [], None

    async def _check_manual_cost_linkage(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        active_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        all_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(CoreSKU.account_id == account_id)
                )
            ).scalars()
        )
        active_sku_index = self.marts._build_core_sku_index(active_skus)
        all_by_id = {sku.id: sku for sku in all_skus}
        costs = list(
            (
                await session.execute(
                    select(ManualCost).where(ManualCost.account_id == account_id)
                )
            ).scalars()
        )
        touched = 0
        for cost in costs:
            linked_sku = all_by_id.get(cost.sku_id) if cost.sku_id is not None else None
            active_matches, match_rule = self._resolve_manual_cost_candidates(
                active_sku_index, cost=cost
            )
            if len(active_matches) > 1 or cost.is_ambiguous:
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="manual_cost_ambiguous_match",
                    message="Строка себестоимости подходит сразу к нескольким активным карточкам",
                    severity="warning",
                    entity_key=f"manual_cost:{cost.id}",
                    payload={
                        "manualCostId": cost.id,
                        "skuId": cost.sku_id,
                        "vendorCode": cost.vendor_code,
                        "nmId": cost.nm_id,
                        "barcode": cost.barcode,
                        "techSize": cost.tech_size,
                        "matchRule": match_rule,
                        "candidateSkuIds": [sku.id for sku in active_matches],
                    },
                )
                touched += 1
                continue
            if linked_sku is not None and not linked_sku.is_active:
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="manual_cost_linked_to_inactive_sku",
                    message="Себестоимость привязана к архивной карточке",
                    severity="warning",
                    entity_key=f"manual_cost:{cost.id}",
                    payload={
                        "manualCostId": cost.id,
                        "inactiveSkuId": linked_sku.id,
                        "vendorCode": cost.vendor_code,
                        "nmId": cost.nm_id,
                        "barcode": cost.barcode,
                        "techSize": cost.tech_size,
                        "activeCandidateSkuIds": [sku.id for sku in active_matches],
                        "matchRule": match_rule,
                    },
                )
                touched += 1
                continue
            if not active_matches:
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="manual_cost_unresolved_sku",
                    message="Себестоимость не удалось привязать ни к одной активной карточке",
                    severity="warning",
                    entity_key=f"manual_cost:{cost.id}",
                    payload={
                        "manualCostId": cost.id,
                        "skuId": cost.sku_id,
                        "vendorCode": cost.vendor_code,
                        "nmId": cost.nm_id,
                        "barcode": cost.barcode,
                        "techSize": cost.tech_size,
                        "matchRule": match_rule,
                    },
                )
                touched += 1
        return touched

    async def _check_manual_cost_upload_warnings(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        upload = (
            await session.execute(
                select(ManualCostUpload)
                .where(ManualCostUpload.account_id == account_id)
                .order_by(
                    ManualCostUpload.created_at.desc(), ManualCostUpload.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if upload is None:
            return 0
        summary = dict(upload.summary or {})
        touched = 0
        legacy_rows = int(summary.get("legacyFieldMappedRows") or 0)
        if legacy_rows > 0:
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="manual_cost_old_fields_used",
                message="В загрузке использованы устаревшие поля packaging/inbound logistics",
                severity="warning",
                entity_key=f"account:{account_id}:manual_cost_old_fields_used",
                entity_type="account",
                entity_id=account_id,
                source_table="manual_cost_uploads",
                payload={
                    "accountId": account_id,
                    "uploadId": upload.id,
                    "rowsAffected": legacy_rows,
                    "legacyFieldNames": list(summary.get("legacyFieldNames") or []),
                    "mappedToField": "seller_other_expense",
                },
            )
            touched += 1
        missing_rows = int(summary.get("sellerOtherExpenseMissingRows") or 0)
        if bool(summary.get("sellerOtherExpenseRequiredByConfig")) and missing_rows > 0:
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="seller_other_expense_missing",
                message="Не заполнены прочие расходы продавца в обязательном поле seller_other_expense",
                severity="warning",
                entity_key=f"account:{account_id}:seller_other_expense_missing",
                entity_type="account",
                entity_id=account_id,
                source_table="manual_cost_uploads",
                payload={
                    "accountId": account_id,
                    "uploadId": upload.id,
                    "rowsAffected": missing_rows,
                    "requiredByConfig": True,
                    "targetField": "seller_other_expense",
                },
            )
            touched += 1
        return touched

    async def _check_expense_finance_report_missing(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        date_from = today - timedelta(days=30)
        finance_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WBRealizationReportRow)
                    .where(
                        WBRealizationReportRow.account_id == account_id,
                        WBRealizationReportRow.rr_date >= date_from,
                        WBRealizationReportRow.rr_date <= today,
                    )
                )
            ).scalar_one()
            or 0
        )
        if finance_rows > 0:
            return 0
        sales_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WBSale)
                    .where(
                        WBSale.account_id == account_id,
                        func.date(WBSale.date) >= date_from,
                        func.date(WBSale.date) <= today,
                    )
                )
            ).scalar_one()
            or 0
        )
        order_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WBOrder)
                    .where(
                        WBOrder.account_id == account_id,
                        func.date(WBOrder.date) >= date_from,
                        func.date(WBOrder.date) <= today,
                    )
                )
            ).scalar_one()
            or 0
        )
        if sales_rows == 0 and order_rows == 0:
            return 0
        await self.open_issue(
            session,
            account_id=account_id,
            domain="data_quality",
            code="expense_finance_report_missing",
            message="Операционные продажи есть, а финансовый отчет WB за период отсутствует",
            severity="error",
            entity_key=f"account:{account_id}:expense_finance_report_missing",
            entity_type="account",
            entity_id=account_id,
            source_table="wb_realization_report_rows",
            payload={
                "accountId": account_id,
                "dateFrom": date_from.isoformat(),
                "dateTo": today.isoformat(),
                "financeRowCount": finance_rows,
                "salesRowCount": sales_rows,
                "orderRowCount": order_rows,
            },
        )
        return 1

    async def _check_expense_logistics_missing(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        date_from = today - timedelta(days=30)
        finance_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WBRealizationReportRow)
                    .where(
                        WBRealizationReportRow.account_id == account_id,
                        WBRealizationReportRow.rr_date >= date_from,
                        WBRealizationReportRow.rr_date <= today,
                    )
                )
            ).scalar_one()
            or 0
        )
        if finance_rows == 0:
            return 0
        delivery_return_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(MartSKUDaily)
                    .where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= date_from,
                        MartSKUDaily.stat_date <= today,
                        (MartSKUDaily.final_sales_qty > 0)
                        | (MartSKUDaily.final_return_qty > 0),
                    )
                )
            ).scalar_one()
            or 0
        )
        if delivery_return_rows == 0:
            return 0
        logistics_total = self._decimal(
            (
                await session.execute(
                    select(func.coalesce(func.sum(MartExpenseDaily.amount), 0)).where(
                        MartExpenseDaily.account_id == account_id,
                        MartExpenseDaily.stat_date >= date_from,
                        MartExpenseDaily.stat_date <= today,
                        MartExpenseDaily.expense_category.in_(
                            ["wb_logistics", "wb_logistics_rebill"]
                        ),
                        MartExpenseDaily.amount_sign == "expense",
                    )
                )
            ).scalar_one()
            or 0
        )
        if logistics_total != 0:
            return 0
        await self.open_issue(
            session,
            account_id=account_id,
            domain="data_quality",
            code="expense_logistics_missing",
            message="Есть продажи или возвраты, но логистика WB в расходах отсутствует",
            severity="error",
            entity_key=f"account:{account_id}:expense_logistics_missing",
            entity_type="account",
            entity_id=account_id,
            source_table="mart_expense_daily",
            payload={
                "accountId": account_id,
                "dateFrom": date_from.isoformat(),
                "dateTo": today.isoformat(),
                "financeRowCount": finance_rows,
                "deliveryReturnRowCount": delivery_return_rows,
                "logisticsTotal": str(logistics_total),
            },
        )
        return 1

    async def _check_expense_ad_double_count_risk(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        date_from = today - timedelta(days=30)
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= date_from,
                        MartSKUDaily.stat_date <= today,
                        MartSKUDaily.marketing_deduction > 0,
                        MartSKUDaily.ad_spend_operational > 0,
                    )
                )
            ).scalars()
        )
        touched = 0
        for row in rows[: self.MAX_ISSUES_PER_CODE]:
            ad_source = str(row.ad_spend_source or "").strip().lower()
            ad_spend_final = self._decimal(row.ad_spend_final)
            finance_ad = self._decimal(row.marketing_deduction)
            if ad_source != "ads_api" and ad_spend_final <= finance_ad + Decimal(
                "0.01"
            ):
                continue
            entity_key = f"expense-ad-risk:{row.stat_date}:{row.sku_id or 'none'}:{row.nm_id or 'none'}"
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="expense_ad_double_count_risk",
                message="Есть риск двойного учета рекламных расходов",
                severity="error",
                entity_key=entity_key,
                entity_type="sku",
                entity_id=row.sku_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_sku_daily",
                payload={
                    "statDate": row.stat_date.isoformat(),
                    "skuId": row.sku_id,
                    "nmId": row.nm_id,
                    "marketingDeduction": str(finance_ad),
                    "adSpendOperational": str(self._decimal(row.ad_spend_operational)),
                    "adSpendFinal": str(ad_spend_final),
                    "adSpendSource": row.ad_spend_source,
                },
            )
            touched += 1
        return touched

    async def _check_expense_negative_unexpected(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        date_from = today - timedelta(days=30)
        rows = list(
            (
                await session.execute(
                    select(MartExpenseDaily).where(
                        MartExpenseDaily.account_id == account_id,
                        MartExpenseDaily.stat_date >= date_from,
                        MartExpenseDaily.stat_date <= today,
                        MartExpenseDaily.amount_sign == "income",
                        MartExpenseDaily.expense_category != "additional_payment",
                        MartExpenseDaily.amount > 0,
                    )
                )
            ).scalars()
        )
        touched = 0
        for row in rows[: self.MAX_ISSUES_PER_CODE]:
            entity_key = f"expense-negative:{row.rrd_id}:{row.expense_category}:{row.source_field}"
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="expense_negative_unexpected",
                message="Обнаружена нетипичная отрицательная строка расхода",
                severity="warning",
                entity_key=entity_key,
                entity_type="finance_expense",
                entity_id=row.rrd_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_expense_daily",
                payload={
                    "statDate": row.stat_date.isoformat(),
                    "reportId": row.report_id,
                    "rrdId": row.rrd_id,
                    "category": row.expense_category,
                    "amount": str(self._decimal(row.amount)),
                    "sourceField": row.source_field,
                    "sellerOperName": row.seller_oper_name,
                    "bonusTypeName": row.bonus_type_name,
                },
            )
            touched += 1
        return touched

    async def _check_expense_large_logistics_share(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        date_from = today - timedelta(days=30)
        totals = await self._expense_totals(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=today,
        )
        total_wb_expenses = self._decimal(totals["total_wb_expenses"])
        expense_base = (
            total_wb_expenses
            if total_wb_expenses > 0
            else self._decimal(totals["total_expenses"])
        )
        if expense_base <= 0:
            return 0
        settings = await self._load_account_settings(session, account_id=account_id)
        threshold = self._decimal(
            settings.get(
                "large_logistics_share_threshold_percent",
                self.DEFAULT_LARGE_LOGISTICS_SHARE_THRESHOLD_PERCENT,
            )
        )
        logistics_total = self._decimal(totals["logistics_total"])
        share_percent = self._percent(logistics_total, expense_base)
        if share_percent <= threshold:
            return 0
        await self.open_issue(
            session,
            account_id=account_id,
            domain="data_quality",
            code="expense_large_logistics_share",
            message="Доля логистики в расходах аномально высокая",
            severity="warning",
            entity_key=f"account:{account_id}:expense_large_logistics_share",
            entity_type="account",
            entity_id=account_id,
            source_table="mart_expense_daily",
            payload={
                "accountId": account_id,
                "dateFrom": date_from.isoformat(),
                "dateTo": today.isoformat(),
                "logisticsTotal": str(logistics_total),
                "expenseBase": str(expense_base),
                "expenseBaseKind": "wb_expenses"
                if total_wb_expenses > 0
                else "all_expenses",
                "sharePercent": str(share_percent.quantize(Decimal("0.01"))),
                "thresholdPercent": str(threshold),
                "logistics_total": str(logistics_total),
                "expense_base": str(expense_base),
                "expense_base_kind": "wb_expenses"
                if total_wb_expenses > 0
                else "all_expenses",
                "share_percent": str(share_percent.quantize(Decimal("0.01"))),
            },
        )
        return 1

    async def _check_expense_no_drilldown_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        date_from = today - timedelta(days=30)
        finance_signal_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WBRealizationReportRow)
                    .where(
                        WBRealizationReportRow.account_id == account_id,
                        WBRealizationReportRow.rr_date >= date_from,
                        WBRealizationReportRow.rr_date <= today,
                        or_(
                            WBRealizationReportRow.delivery_service != 0,
                            WBRealizationReportRow.rebill_logistic_cost != 0,
                            WBRealizationReportRow.paid_storage != 0,
                            WBRealizationReportRow.paid_acceptance != 0,
                            WBRealizationReportRow.penalty != 0,
                            WBRealizationReportRow.deduction != 0,
                            WBRealizationReportRow.acquiring_fee != 0,
                            WBRealizationReportRow.ppvz_sales_commission != 0,
                            WBRealizationReportRow.additional_payment != 0,
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )
        if finance_signal_count == 0:
            return 0
        expense_row_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(MartExpenseDaily)
                    .where(
                        MartExpenseDaily.account_id == account_id,
                        MartExpenseDaily.stat_date >= date_from,
                        MartExpenseDaily.stat_date <= today,
                    )
                )
            ).scalar_one()
            or 0
        )
        if expense_row_count > 0:
            return 0
        await self.open_issue(
            session,
            account_id=account_id,
            domain="data_quality",
            code="expense_no_drilldown_rows",
            message="Для расходов нет детальных drilldown строк",
            severity="error",
            entity_key=f"account:{account_id}:expense_no_drilldown_rows",
            entity_type="account",
            entity_id=account_id,
            source_table="mart_expense_daily",
            payload={
                "accountId": account_id,
                "dateFrom": date_from.isoformat(),
                "dateTo": today.isoformat(),
                "financeSignalCount": finance_signal_count,
                "expenseRowCount": expense_row_count,
            },
        )
        return 1

    async def _check_finance_reconciliation(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartFinanceReconciliation).where(
                        MartFinanceReconciliation.account_id == account_id,
                        MartFinanceReconciliation.stat_date
                        >= today - timedelta(days=30),
                    )
                )
            ).scalars()
        )
        touched = 0
        eligible_rows = [
            row for row in rows if row.stat_date <= today - timedelta(days=2)
        ]
        for row in eligible_rows[: self.MAX_ISSUES_PER_CODE]:
            age_days = max((today - row.stat_date).days, 0)
            age_bucket, severity = self._severity_for_age(age_days)
            if row.status == "missing_finance":
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="sale_without_finance",
                    message="Продажа есть, а строки в отчете WB пока нет",
                    severity=severity,
                    entity_key=row.srid,
                    entity_type="sale",
                    entity_id=row.order_id,
                    sku_id=row.sku_id,
                    nm_id=row.nm_id,
                    source_table="mart_finance_reconciliation",
                    payload=self._classified_payload(
                        classification_status="expected_lag"
                        if age_bucket in {"pending", "warning"}
                        else "classified",
                        classification_reason=(
                            "expected_lag"
                            if age_bucket in {"pending", "warning"}
                            else "missing_finance"
                        ),
                        age_bucket=age_bucket,
                        ageDays=age_days,
                        srid=row.srid,
                        nmId=row.nm_id,
                        statDate=row.stat_date.isoformat(),
                    ),
                )
                touched += 1
            elif row.status == "missing_sale":
                await self.open_issue(
                    session,
                    account_id=account_id,
                    domain="data_quality",
                    code="finance_without_sale",
                    message="В отчете WB есть строка, а продажи в операционных данных нет",
                    severity=severity,
                    entity_key=row.srid,
                    entity_type="finance",
                    entity_id=row.order_id,
                    sku_id=row.sku_id,
                    nm_id=row.nm_id,
                    source_table="mart_finance_reconciliation",
                    payload=self._classified_payload(
                        classification_status="expected_lag"
                        if age_bucket in {"pending", "warning"}
                        else "classified",
                        classification_reason=(
                            "expected_lag"
                            if age_bucket in {"pending", "warning"}
                            else "missing_sale"
                        ),
                        age_bucket=age_bucket,
                        ageDays=age_days,
                        srid=row.srid,
                        nmId=row.nm_id,
                        statDate=row.stat_date.isoformat(),
                    ),
                )
                touched += 1
            elif row.status == "mismatch":
                continue
        return touched

    async def _check_stock_without_sales(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= today - timedelta(days=30),
                        MartSKUDaily.closing_stock_qty.is_not(None),
                        MartSKUDaily.closing_stock_qty > 0,
                        MartSKUDaily.final_sales_qty == 0,
                    )
                )
            ).scalars()
        )
        touched = 0
        seen: set[int] = set()
        for row in rows:
            if row.sku_id is None or row.sku_id in seen:
                continue
            seen.add(row.sku_id)
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="stock_without_sales",
                message="Остаток есть, а продаж по этой карточке не было",
                severity="info",
                entity_key=f"sku:{row.sku_id}",
                entity_type="sku",
                entity_id=row.sku_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_sku_daily",
                payload={
                    "statDate": row.stat_date.isoformat(),
                    "closingStockQty": str(row.closing_stock_qty or 0),
                },
            )
            touched += 1
        return touched

    async def _check_sales_without_stock(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= today - timedelta(days=30),
                        MartSKUDaily.final_sales_qty > 0,
                        or_(
                            MartSKUDaily.closing_stock_qty.is_(None),
                            MartSKUDaily.closing_stock_qty <= 0,
                        ),
                    )
                )
            ).scalars()
        )
        touched = 0
        seen: set[int] = set()
        for row in rows:
            if row.sku_id is None or row.sku_id in seen:
                continue
            seen.add(row.sku_id)
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="sales_without_stock",
                message="Продажи есть, а свежего остатка по карточке нет",
                severity="warning",
                entity_key=f"sku:{row.sku_id}",
                entity_type="sku",
                entity_id=row.sku_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_sku_daily",
                payload={
                    "statDate": row.stat_date.isoformat(),
                    "finalSalesQty": row.final_sales_qty,
                },
            )
            touched += 1
        return touched

    async def _check_order_without_sale_or_return(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartFinanceReconciliation).where(
                        MartFinanceReconciliation.account_id == account_id,
                        MartFinanceReconciliation.stat_date
                        >= today - timedelta(days=30),
                        MartFinanceReconciliation.status == "order_without_followup",
                    )
                )
            ).scalars()
        )
        touched = 0
        for row in rows[: self.MAX_ISSUES_PER_CODE]:
            age_days = max((today - row.stat_date).days, 0)
            age_bucket, severity = self._severity_for_age(age_days)
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="order_without_sale_or_return",
                message="Заказ есть, но потом нет ни продажи, ни возврата",
                severity=severity,
                entity_key=row.srid,
                entity_type="order",
                entity_id=row.order_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_finance_reconciliation",
                payload=self._classified_payload(
                    classification_status="classified",
                    classification_reason="expected_lag"
                    if age_bucket in {"pending", "warning"}
                    else "missing_followup",
                    age_bucket=age_bucket,
                    ageDays=age_days,
                    srid=row.srid,
                    statDate=row.stat_date.isoformat(),
                ),
            )
            touched += 1
        return touched

    async def _check_price_zero_or_too_low(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        today: date,
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= today - timedelta(days=30),
                        or_(
                            MartSKUDaily.current_discounted_price <= 0,
                            MartSKUDaily.current_price <= 0,
                        ),
                    )
                )
            ).scalars()
        )
        touched = 0
        seen: set[int] = set()
        for row in rows:
            if row.sku_id is None or row.sku_id in seen:
                continue
            seen.add(row.sku_id)
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="price_zero_or_too_low",
                message="Цена нулевая или подозрительно низкая",
                severity="warning",
                entity_key=f"sku:{row.sku_id}",
                entity_type="sku",
                entity_id=row.sku_id,
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                source_table="mart_sku_daily",
                payload={
                    "statDate": row.stat_date.isoformat(),
                    "currentPrice": str(row.current_price or 0),
                    "currentDiscountedPrice": str(row.current_discounted_price or 0),
                },
            )
            touched += 1
        return touched

    async def _check_ad_spend_without_sales(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.ad_spend > 0,
                        MartSKUDaily.sale_rows == 0,
                        MartSKUDaily.finance_rows == 0,
                    )
                )
            ).scalars()
        )
        touched = 0
        aggregated: dict[int | None, dict[str, Decimal | date | None]] = {}
        for row in rows:
            key = row.nm_id
            current = aggregated.setdefault(
                key,
                {"ad_spend": Decimal("0"), "last_date": row.stat_date},
            )
            current["ad_spend"] = self._decimal(current["ad_spend"]) + self._decimal(
                row.ad_spend
            )
            current["last_date"] = (
                max(row.stat_date, current["last_date"])
                if current["last_date"]
                else row.stat_date
            )
        for nm_id, payload in list(aggregated.items())[: self.MAX_ISSUES_PER_CODE]:
            if self._decimal(payload["ad_spend"]) < self.MIN_AD_SPEND_WITHOUT_SALES:
                continue
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="ad_spend_without_sales",
                message="Есть рекламные расходы, но нет продаж или подтверждения в отчете WB",
                severity="info",
                entity_key=f"nm:{nm_id}",
                entity_type="sku",
                nm_id=nm_id,
                source_table="mart_sku_daily",
                payload={
                    "nmId": nm_id,
                    "lastDate": payload["last_date"].isoformat()
                    if payload["last_date"]
                    else None,
                    "adSpend": str(payload["ad_spend"]),
                },
            )
            touched += 1
        return touched

    async def _check_ad_spend_without_sku(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        rows = list(
            (
                await session.execute(
                    select(WBAdStatsDaily).where(
                        WBAdStatsDaily.account_id == account_id,
                        or_(WBAdStatsDaily.nm_id.is_(None), WBAdStatsDaily.nm_id == 0),
                    )
                )
            ).scalars()
        )
        if not rows:
            return 0
        await self.open_issue(
            session,
            account_id=account_id,
            domain="data_quality",
            code="ad_spend_without_sku",
            message="Есть рекламные строки, которые не привязаны ни к одной карточке",
            severity="warning",
            entity_key=f"account:{account_id}:ads_unmatched",
            entity_type="account",
            entity_id=account_id,
            source_table="wb_ad_stats_daily",
            payload={"rows": len(rows)},
        )
        return 1

    async def _check_dead_stock(self, session: AsyncSession, *, account_id: int) -> int:
        rows = list(
            (
                await session.execute(
                    select(MartStockDaily).where(
                        MartStockDaily.account_id == account_id,
                        (MartStockDaily.quantity > 0)
                        | (MartStockDaily.quantity_full > 0),
                    )
                )
            ).scalars()
        )
        touched = 0
        aggregated: dict[int | None, dict[str, object]] = {}
        for row in rows:
            if row.days_since_last_sale is None or row.days_since_last_sale <= 45:
                continue
            key = row.nm_id
            current = aggregated.setdefault(
                key,
                {
                    "warehouse_names": set(),
                    "days_since_last_sale": row.days_since_last_sale,
                    "quantity": Decimal("0"),
                    "quantity_full": Decimal("0"),
                },
            )
            current["days_since_last_sale"] = max(
                int(current["days_since_last_sale"]),
                int(row.days_since_last_sale),
            )
            warehouse_names = current["warehouse_names"]
            if isinstance(warehouse_names, set) and row.warehouse_name:
                warehouse_names.add(row.warehouse_name)
            current["quantity"] = self._decimal(current["quantity"]) + self._decimal(
                row.quantity
            )
            current["quantity_full"] = self._decimal(
                current["quantity_full"]
            ) + self._decimal(row.quantity_full)
        for nm_id, payload in list(aggregated.items())[: self.MAX_ISSUES_PER_CODE]:
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="dead_stock",
                message="Остаток лежит давно, а недавних продаж не было",
                severity="info",
                entity_key=f"nm:{nm_id}",
                payload={
                    "nmId": nm_id,
                    "warehouseNames": sorted(payload["warehouse_names"]),
                    "daysSinceLastSale": payload["days_since_last_sale"],
                    "quantity": str(payload["quantity"]),
                    "quantityFull": str(payload["quantity_full"]),
                },
            )
            touched += 1
        return touched

    async def _check_price_jump(self, session: AsyncSession, *, account_id: int) -> int:
        snapshots = list(
            (
                await session.execute(
                    select(WBPriceSnapshot)
                    .where(WBPriceSnapshot.account_id == account_id)
                    .order_by(WBPriceSnapshot.snapshot_at.desc())
                )
            ).scalars()
        )
        by_nm: dict[int, list[WBPriceSnapshot]] = defaultdict(list)
        for row in snapshots:
            by_nm[row.nm_id].append(row)
        touched = 0
        for nm_id, rows in by_nm.items():
            if len(rows) < 2:
                continue
            current_price = self._extract_snapshot_price(rows[0].payload)
            previous_price = self._extract_snapshot_price(rows[1].payload)
            if current_price in (None, Decimal("0")) or previous_price in (
                None,
                Decimal("0"),
            ):
                continue
            change = abs((current_price - previous_price) / previous_price)
            if change < Decimal("0.30"):
                continue
            await self.open_issue(
                session,
                account_id=account_id,
                domain="data_quality",
                code="price_jump",
                message="Цена резко изменилась между последними загрузками",
                severity="warning",
                entity_key=f"nm:{nm_id}",
                payload={
                    "nmId": nm_id,
                    "currentPrice": str(current_price),
                    "previousPrice": str(previous_price),
                    "changePercent": str((change * 100).quantize(Decimal("0.01"))),
                },
            )
            touched += 1
        return touched

    async def _apply_issue_flags_to_marts(
        self, session: AsyncSession, *, account_id: int
    ) -> None:
        await session.execute(
            update(MartSKUDaily)
            .where(MartSKUDaily.account_id == account_id)
            .values(has_open_issues=False)
        )
        open_issues = list(
            (
                await session.execute(
                    select(DataQualityIssue).where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                    )
                )
            ).scalars()
        )
        open_sku_ids: set[int] = set()
        open_nm_ids: set[int] = set()
        for issue in open_issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if issue_sku_id is not None:
                open_sku_ids.add(issue_sku_id)
            if issue_nm_id is not None:
                open_nm_ids.add(issue_nm_id)
        if open_sku_ids:
            await session.execute(
                update(MartSKUDaily)
                .where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.sku_id.in_(open_sku_ids),
                )
                .values(has_open_issues=True)
            )
        if open_nm_ids:
            await session.execute(
                update(MartSKUDaily)
                .where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.nm_id.in_(open_nm_ids),
                )
                .values(has_open_issues=True)
            )
