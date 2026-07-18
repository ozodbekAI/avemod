from __future__ import annotations

import asyncio
import ast
import re
import time
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.cache import TTLMemoryCache
from app.core.config import get_settings
from app.core.wb_connector_inventory import WB_CONNECTOR_INVENTORY
from app.models.accounts import WBAPIToken, WBAccount
from app.models.auth import AuthUser, AuthUserAccountAccess
from app.models.card_quality import (
    CardQualityIssue,
    CardQualityIssueStatusHistory,
    CardQualitySnapshot,
)
from app.models.control_tower import ActionRecommendation
from app.models.data_quality import DataQualityIssue
from app.models.experiments import Experiment
from app.models.manual_costs import ManualCost
from app.models.operator import OperatorDraft, ResultEvent, UnifiedAction
from app.models.photo_studio import PhotoProject, PhotoVersion
from app.models.problem_engine import (
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
)
from app.models.product_cards import WBProductCard, WBProductCardCharacteristic
from app.models.raw import RawWBAPIResponse
from app.models.sync import WBSyncCursor, WBSyncRun
from app.schemas.operator import (
    ActionStatus,
    DraftOut,
    DraftType,
    ExternalStatus,
    ProfitDoctorOut,
    TrustState,
    UnifiedActionOut,
)
from app.schemas.control_tower import ActionRecommendationUpdateRequest
from app.schemas.data_quality import (
    issue_bucket_meta,
    issue_display_message,
    issue_fixability_contract,
    issue_resolution_guide,
)
from app.schemas.photo import PhotoExperimentCreateRequest
from app.schemas.portal import (
    PortalAccountSummary,
    PortalActionRead,
    PortalActionsPage,
    PortalAssignableUserRead,
    PortalManualActionCreateRequest,
    PortalActionSourceUpdateRequest,
    PortalActionUpdateRequest,
    PortalDataBlock,
    PortalDashboardAttentionItem,
    PortalDashboardBusinessVerdict,
    PortalDashboardDataConfidenceItem,
    PortalDashboardOnboardingState,
    PortalDashboardOverviewRead,
    PortalDashboardPlanItem,
    PortalDashboardPrimaryAction,
    PortalDashboardPulseCard,
    PortalDashboardSourceFreshness,
    PortalDashboardRecentResultsSummary,
    PortalDataReadinessRead,
    PortalDataReadinessSource,
    PortalDataSyncDomainStatus,
    PortalDataSyncRunSummary,
    PortalDataSyncStatusRead,
    PortalExperimentCreate,
    PortalExperimentEvaluationRead,
    PortalExperimentEventCreate,
    PortalExperimentEventRead,
    PortalExperimentEventsPage,
    PortalExperimentInterventionCreate,
    PortalExperimentInterventionRead,
    PortalExperimentMetricsPage,
    PortalExperimentRead,
    PortalExperimentsPage,
    PortalExperimentSettingsRead,
    PortalExperimentSettingsUpdate,
    PortalExperimentsStatusRead,
    PortalExperimentUpdate,
    PortalGroupingPreviewRead,
    PortalGroupingPreviewRequest,
    PortalModuleHealth,
    PortalModulesHealthRead,
    PortalOverviewRead,
    PortalProductGroupingRead,
    PortalProduct360Read,
    PortalProductQualityRead,
    PortalProductRead,
    PortalCostStatus,
    PortalNextStep,
    PortalReadinessBlocker,
    PortalProductsPage,
    PortalResultEventCreate,
    PortalResultEventRead,
    PortalResultEventsPage,
    PortalSafeAction,
    PortalStatusBlock,
    PortalStockOpsInsightsRead,
    PortalStockOpsRunRead,
    PortalStockOpsRunRequest,
    PortalStockOpsRunsPage,
    build_action_center_solve_map,
    build_action_center_solve_map_from_template,
)
from app.schemas.reputation import (
    ReputationAnalyticsOut,
    ReputationBrandsOut,
    ReputationBulkDraftDecisionOut,
    ReputationChatEventsOut,
    ReputationChatsOut,
    ReputationDraftDecisionRequest,
    ReputationDraftMutationOut,
    ReputationDraftRequest,
    ReputationDraftsOut,
    ReputationInboxOut,
    ReputationItemOut,
    ReputationLearningApplyRequest,
    ReputationLearningOut,
    ReputationLearningToggleRequest,
    ReputationNoReplyRequest,
    ReputationProductInsightOut,
    ReputationPromptUpdateRequest,
    ReputationPublishRequest,
    ReputationSettingsOut,
    ReputationSettingsUpdateRequest,
    ReputationSummaryOut,
    ReputationSyncOut,
)
from app.services.checker_adapter import CheckerAdapter
from app.services.checker_problem_bridge import build_checker_problem_bridge
from app.services.claims_adapter import ClaimsDefectAdapter
from app.services.claims_factory import ClaimsFactoryService
from app.services.card_quality import CardQualityAnalysisService
from app.services.control_tower import ControlTowerService
from app.services.data_quality import DataQualityService
from app.services.diagnosis.profit_doctor import ProfitDoctorService
from app.services.experiments import ExperimentEventService
from app.services.ab_tests import ABTestService
from app.services.grouping_adapter import GroupingAdapter
from app.services.grouping import GroupingBetaService
from app.services.guided_fixes import GuidedFixMapper
from app.services.manual_costs import ManualCostService
from app.services.module_registry import ModuleRegistryService
from app.services.photo_studio import PhotoStudioService
from app.services.reputation_adapter import ReputationAdapter
from app.services.reputation import ReputationService
from app.services.result_tracking import ResultTrackingService
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.operator_snapshots import OperatorEndpointSnapshotService
from app.services.stock_control import StockControlService
from app.services.stockops_adapter import StockOpsAdapter
from app.core.time import utcnow
from app.core.observability import (
    log_optional_module_failure,
    record_unavailable_source,
)


class PortalService:
    SHADOW_ACTION_SOURCES = {"profit_doctor"}
    SHADOW_ACTION_MODULES = {
        "checker",
        "stockops",
        "grouping_beta",
        "reputation",
        "claims",
        "photo",
        "experiments",
    }
    MVP_ACTION_MODULES = {"finance", "data_quality", "costs", "checker", "manual"}
    ACTIONS_CACHE_TTL_SECONDS = 30
    _shared_actions_cache: TTLMemoryCache[PortalActionsPage] = TTLMemoryCache(
        default_ttl_seconds=ACTIONS_CACHE_TTL_SECONDS
    )
    PRODUCT360_CACHE_TTL_SECONDS = 60
    _shared_product360_cache: TTLMemoryCache[PortalProduct360Read] = TTLMemoryCache(
        default_ttl_seconds=PRODUCT360_CACHE_TTL_SECONDS
    )
    PRODUCTS_CACHE_TTL_SECONDS = 120
    _shared_products_cache: TTLMemoryCache[PortalProductsPage] = TTLMemoryCache(
        default_ttl_seconds=PRODUCTS_CACHE_TTL_SECONDS
    )
    DASHBOARD_OVERVIEW_CACHE_TTL_SECONDS = 30
    _shared_dashboard_overview_cache: TTLMemoryCache[PortalDashboardOverviewRead] = (
        TTLMemoryCache(default_ttl_seconds=DASHBOARD_OVERVIEW_CACHE_TTL_SECONDS)
    )
    OVERVIEW_CACHE_TTL_SECONDS = 30
    _shared_overview_cache: TTLMemoryCache[PortalOverviewRead] = TTLMemoryCache(
        default_ttl_seconds=OVERVIEW_CACHE_TTL_SECONDS
    )
    DATA_SYNC_STATUS_CACHE_TTL_SECONDS = 30
    _shared_data_sync_status_cache: TTLMemoryCache[PortalDataSyncStatusRead] = (
        TTLMemoryCache(default_ttl_seconds=DATA_SYNC_STATUS_CACHE_TTL_SECONDS)
    )
    DATA_READINESS_CACHE_TTL_SECONDS = 30
    _shared_data_readiness_cache: TTLMemoryCache[PortalDataReadinessRead] = (
        TTLMemoryCache(default_ttl_seconds=DATA_READINESS_CACHE_TTL_SECONDS)
    )
    ACTION_CENTER_STATUSES = {
        "new",
        "acknowledged",
        "in_progress",
        "done",
        "postponed",
        "ignored",
        "blocked",
        "resolved",
        "dismissed",
        "reopened",
    }
    ACTION_CENTER_TRANSITIONS = {
        "new": {"acknowledged", "in_progress", "ignored", "postponed", "blocked"},
        "acknowledged": {"in_progress", "ignored", "postponed", "blocked"},
        "in_progress": {"done", "blocked", "postponed", "ignored"},
        "done": {"resolved", "reopened"},
        "ignored": {"reopened"},
        "postponed": {"in_progress", "ignored", "reopened"},
        "blocked": {"in_progress"},
        "resolved": {"reopened"},
        "dismissed": {"reopened"},
        "reopened": {"acknowledged", "in_progress", "ignored", "postponed", "blocked"},
    }
    ACTION_CENTER_DIRECT_SOURCE_STATUSES = {
        "new",
        "in_progress",
        "done",
        "postponed",
        "ignored",
        "blocked",
        "resolved",
    }
    ACTIVE_PROBLEM_INSTANCE_STATUSES = {
        "new",
        "acknowledged",
        "in_progress",
        "postponed",
        "ignored",
        "blocked",
        "done",
        "reopened",
    }
    HIDDEN_ACTION_CENTER_CODES = {"finance_reconciliation_mismatch"}
    PRODUCT_PROBLEM_INSTANCE_STATUSES = {
        "new",
        "acknowledged",
        "in_progress",
        "postponed",
        "ignored",
        "blocked",
        "done",
        "resolved",
        "dismissed",
        "reopened",
    }
    PRODUCT360_PROBLEM_GROUPS = {
        "profitability": "Profitability",
        "stock": "Stock",
        "price": "Price",
        "ads_promo": "Ads/Promo",
        "card_quality": "Card Quality",
        "data_blockers": "Data Blockers",
        "system_checks": "System Checks",
    }
    LEGACY_DYNAMIC_PROBLEM_MAP = {
        # Product/money/profit doctor legacy signals.
        "cost_missing": "missing_cost_blocks_profit",
        "missing_cost": "missing_cost_blocks_profit",
        "missing_manual_cost": "missing_cost_blocks_profit",
        "missing_cost_blocks_profit": "missing_cost_blocks_profit",
        "profit_leak": "negative_unit_profit",
        "negative_profit": "negative_unit_profit",
        "negative_unit_profit": "negative_unit_profit",
        "loss_making": "negative_unit_profit",
        "frozen_stock": "overstock_slow_moving",
        "overstock": "overstock_slow_moving",
        "liquidate_stock": "overstock_slow_moving",
        "discount_to_clear": "overstock_slow_moving",
        "overstock_slow_moving": "overstock_slow_moving",
        "stock_risk": "low_stock_risk",
        "low_stock": "low_stock_risk",
        "out_of_stock": "low_stock_risk",
        "reorder": "low_stock_risk",
        "restock": "low_stock_risk",
        "low_stock_risk": "low_stock_risk",
        "ads_eating_profit": "ads_spend_without_profit",
        "ads_review": "ads_spend_without_profit",
        "ads_spend_without_profit": "ads_spend_without_profit",
        "ad_spend_without_profit": "ads_spend_without_profit",
        "promo_not_profitable": "promo_not_profitable",
        "review_promo": "promo_not_profitable",
        "safe_promo": "promo_not_profitable",
        "price_below_safe_margin": "price_below_safe_margin",
        "price_increase_review": "price_below_safe_margin",
        "below_safe_margin": "price_below_safe_margin",
        "safe_price_gap": "price_below_safe_margin",
        "price_zero_or_too_low": "price_below_safe_margin",
        "dead_stock": "dead_stock",
        "fast_stock_depletion": "fast_stock_depletion",
        "depletion": "fast_stock_depletion",
        # Data Fix dynamic bridge signals.
        "manual_cost_unresolved_sku": "manual_cost_unresolved_sku",
        "manual_cost_ambiguous_match": "manual_cost_ambiguous_match",
        "unmatched_sku": "unmatched_sku",
        "unmatched_sku_detected": "unmatched_sku",
        "expense_unclassified": "expense_unclassified",
        "unclassified_finance_expense": "expense_unclassified",
        "sale_without_finance": "sale_without_finance",
        "finance_without_sale": "finance_without_sale",
    }
    DATA_SYNC_FRESHNESS_WINDOWS: dict[str, timedelta] = {
        "product_cards": timedelta(hours=24),
        "sales": timedelta(hours=12),
        "orders": timedelta(hours=12),
        "finance": timedelta(hours=36),
        "stocks": timedelta(hours=12),
        "ads": timedelta(hours=24),
        "prices": timedelta(hours=24),
        "analytics": timedelta(hours=24),
        "supplies": timedelta(days=3),
        "tariffs": timedelta(days=14),
        "documents": timedelta(days=7),
        "reputation": timedelta(hours=24),
    }
    DATA_SYNC_REQUIRED_FOR: dict[str, list[str]] = {
        "product_cards": ["Product 360", "Data Fix", "SKU mapping"],
        "sales": ["Dashboard", "Money preliminary revenue", "Data Fix reconciliation"],
        "orders": ["Operational order checks", "Data Fix reconciliation"],
        "finance": ["Final money numbers", "Finance reconciliation", "Confirmed loss"],
        "stocks": ["Stock value", "Stock Data Fix", "Product 360"],
        "ads": ["Ad spend allocation", "Money profitability"],
        "prices": ["Price anomalies", "Product 360"],
        "analytics": ["Checker opportunities", "Product funnel"],
        "supplies": ["Supply discrepancies", "Claims"],
        "tariffs": ["Logistics/tariff context"],
        "documents": ["Accounting documents"],
        "reputation": ["Feedbacks and questions"],
    }
    RAW_ENDPOINT_PREFIXES: dict[str, tuple[str, ...]] = {
        "product_cards": ("/content/v2/get/cards/list", "/content/v2/tags"),
        "prices": (
            "/api/v2/list/goods",
            "/api/v2/history",
            "/api/v2/buffer",
            "/api/v2/quarantine",
        ),
        "orders": ("/api/v1/supplier/orders",),
        "sales": ("/api/v1/supplier/sales",),
        "stocks": ("/api/v1/warehouse_remains",),
        "finance": (
            "/api/finance/v1/sales-reports",
            "/api/finance/v1/acquiring",
            "/api/v1/account/balance",
        ),
        "analytics": ("/api/analytics", "/api/v1/analytics"),
        "ads": ("/api/advert", "/adv/"),
        "tariffs": ("/api/v1/tariffs", "/api/tariffs"),
        "documents": ("/api/v1/documents",),
        "supplies": (
            "/api/v1/warehouses",
            "/api/v1/acceptance/options",
            "/api/v1/supplies",
        ),
        "reputation": ("/api/v1/feedbacks", "/api/v1/questions"),
    }
    DATA_READINESS_SOURCE_CATALOG: tuple[dict[str, Any], ...] = (
        {
            "source_code": "finance_reports_wb",
            "title": "Finance reports WB",
            "domains": ("finance",),
            "required_for": ["Money", "Data Fix", "Action Center"],
            "blocks_calculation": [
                "final_profit",
                "confirmed_loss",
                "finance_reconciliation",
            ],
            "target_href": "/settings?section=integrations&source=finance",
        },
        {
            "source_code": "sales_orders",
            "title": "Sales / orders",
            "domains": ("sales", "orders"),
            "required_for": ["Money", "Action Center", "Product360"],
            "blocks_calculation": [
                "operational_revenue",
                "order_conversion",
                "problem_engine",
            ],
            "target_href": "/settings?section=integrations&source=statistics",
        },
        {
            "source_code": "product_cards_content",
            "title": "Product cards / content",
            "domains": ("product_cards",),
            "required_for": ["Product360", "Data Fix", "Checker"],
            "blocks_calculation": ["sku_mapping", "content_quality", "problem_engine"],
            "target_href": "/settings?section=integrations&source=content",
        },
        {
            "source_code": "stocks",
            "title": "Stocks",
            "domains": ("stocks",),
            "required_for": ["Action Center", "Product360", "Stock control"],
            "blocks_calculation": ["stock_risk", "blocked_cash", "supply_plan"],
            "target_href": "/settings?section=integrations&source=analytics",
        },
        {
            "source_code": "prices",
            "title": "Prices",
            "domains": ("prices",),
            "required_for": ["Money", "Product360", "Action Center"],
            "blocks_calculation": ["price_safety", "margin", "promo_safety"],
            "target_href": "/settings?section=integrations&source=prices",
        },
        {
            "source_code": "ads",
            "title": "Ads",
            "domains": ("ads",),
            "required_for": ["Money", "Action Center", "Product360"],
            "blocks_calculation": ["ad_spend", "profit_after_ads", "ads_efficiency"],
            "target_href": "/settings?section=integrations&source=promotion",
        },
        {
            "source_code": "manual_costs",
            "title": "Cost price / manual costs",
            "domains": (),
            "required_for": ["Money", "Data Fix", "Action Center"],
            "blocks_calculation": [
                "unit_profit",
                "margin",
                "price_safety",
                "final_profit",
            ],
            "target_href": "/costs",
            "local_source": "manual_costs",
        },
        {
            "source_code": "expenses",
            "title": "Expenses",
            "domains": ("finance",),
            "required_for": ["Money", "Data Fix"],
            "blocks_calculation": ["expense_allocation", "net_profit", "final_profit"],
            "target_href": "/expenses",
        },
        {
            "source_code": "documents",
            "title": "Documents",
            "domains": ("documents",),
            "required_for": ["Money", "Settings"],
            "blocks_calculation": ["document_reconciliation", "accounting_evidence"],
            "target_href": "/settings?section=integrations&source=documents",
        },
        {
            "source_code": "checker_card_quality",
            "title": "Checker / card quality",
            "domains": (),
            "required_for": ["Checker", "Product360", "Action Center"],
            "blocks_calculation": ["content_quality", "card_quality_actions"],
            "target_href": "/products",
            "local_source": "checker",
        },
        {
            "source_code": "data_fix",
            "title": "Data Fix",
            "domains": (),
            "required_for": ["Data Fix", "Money", "Action Center"],
            "blocks_calculation": ["data_quality_resolution", "financial_finality"],
            "target_href": "/data-fix",
            "local_source": "data_fix",
        },
        {
            "source_code": "problem_engine",
            "title": "Problem engine",
            "domains": (),
            "required_for": ["Action Center", "Product360", "Results"],
            "blocks_calculation": [
                "dynamic_problem_generation",
                "seller_problem_tracking",
            ],
            "target_href": "/action-center",
            "local_source": "problem_engine",
        },
    )

    def __init__(self) -> None:
        self.settings = get_settings()
        self.money = MoneyEndpointSnapshotService()
        self.control_tower = ControlTowerService()
        self.data_quality = DataQualityService()
        self.manual_costs = ManualCostService()
        self.checker = CheckerAdapter()
        self.card_quality = CardQualityAnalysisService()
        self.stock_control = StockControlService()
        self.stockops = StockOpsAdapter()
        self.grouping = GroupingAdapter()
        self.grouping_beta = GroupingBetaService()
        self.reputation_adapter = ReputationAdapter()
        self.reputation = ReputationService()
        self.photo_studio = PhotoStudioService()
        self.claims_adapter = ClaimsDefectAdapter()
        self.claims_factory = ClaimsFactoryService()
        self.guided_fixes = GuidedFixMapper()
        self.experiments = ExperimentEventService()
        self.ab_photo_tests = ABTestService()
        self.result_tracking = ResultTrackingService()
        self.module_registry = ModuleRegistryService(
            checker=self.checker,
            stockops=self.stockops,
            grouping=self.grouping,
            reputation=self.reputation_adapter,
            stock_control=self.stock_control,
        )
        self.profit_doctor = ProfitDoctorService(
            money=self.money,
            checker=self.checker,
            card_quality=self.card_quality,
            module_registry=self.module_registry,
            reputation_adapter=self.reputation,
            claims_adapter=self.claims_adapter,
        )
        self.operator_snapshots = OperatorEndpointSnapshotService()
        self._actions_cache = type(self)._shared_actions_cache
        self._product360_cache = type(self)._shared_product360_cache
        self._products_cache = type(self)._shared_products_cache
        self._dashboard_overview_cache = type(self)._shared_dashboard_overview_cache
        self._overview_cache = type(self)._shared_overview_cache
        self._data_sync_status_cache = type(self)._shared_data_sync_status_cache
        self._data_readiness_cache = type(self)._shared_data_readiness_cache

    def _invalidate_actions_cache(self) -> None:
        self._actions_cache.clear()
        self._product360_cache.clear()
        self._products_cache.clear()
        self._dashboard_overview_cache.clear()
        self._overview_cache.clear()
        self._data_sync_status_cache.clear()
        self._data_readiness_cache.clear()

    @staticmethod
    def _actions_cache_date_key(value: date | None) -> str:
        return value.isoformat() if value is not None else ""

    def _actions_cache_filter_key(
        self,
        values: str | list[str] | None,
        *,
        normalize_source_module: bool = False,
        uppercase: bool = False,
    ) -> tuple[str, ...]:
        normalized = self._normalize_filter_values(values)
        if normalize_source_module:
            return tuple(
                sorted(self._normalize_source_module(value) for value in normalized)
            )
        if uppercase:
            return tuple(sorted(value.upper() for value in normalized))
        return tuple(sorted(normalized))

    def _actions_cache_key(
        self,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        status: str | None,
        source_module: list[str] | None,
        priority: list[str] | None,
        nm_id: int | None,
        action_type: list[str] | None,
        problem_code: list[str] | None,
        trust_state: list[str] | None,
        impact_type: list[str] | None,
        include_beta: bool,
        fetch_limit: int,
        dynamic_enabled: bool,
        show_legacy_problem_cards: bool,
    ) -> tuple[object, ...]:
        return (
            "portal_actions_v3",
            int(account_id),
            self._actions_cache_date_key(date_from),
            self._actions_cache_date_key(date_to),
            self._actions_cache_filter_key(status),
            self._actions_cache_filter_key(source_module, normalize_source_module=True),
            self._actions_cache_filter_key(priority, uppercase=True),
            int(nm_id) if nm_id is not None else None,
            self._actions_cache_filter_key(action_type),
            self._actions_cache_filter_key(problem_code),
            self._actions_cache_filter_key(trust_state),
            self._actions_cache_filter_key(impact_type),
            bool(include_beta),
            int(fetch_limit),
            bool(dynamic_enabled),
            bool(show_legacy_problem_cards),
        )

    def _product360_cache_key(
        self,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None,
        date_to: date | None,
        history_limit: int,
        actions_limit: int,
        claims_limit: int,
        dynamic_enabled: bool,
        show_legacy_problem_cards: bool,
    ) -> tuple[object, ...]:
        return (
            "product360_v2",
            int(account_id),
            int(nm_id),
            self._actions_cache_date_key(date_from),
            self._actions_cache_date_key(date_to),
            int(history_limit),
            int(actions_limit),
            int(claims_limit),
            bool(dynamic_enabled),
            bool(show_legacy_problem_cards),
        )

    def _products_cache_key(
        self,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        search: str | None,
        card_quality_status: str | None,
        sort_by: str,
        sort_dir: str,
        fetch_limit: int,
    ) -> tuple[object, ...]:
        return (
            "portal_products_v1",
            int(account_id),
            self._actions_cache_date_key(date_from),
            self._actions_cache_date_key(date_to),
            str(search or "").strip().lower(),
            str(card_quality_status or "").strip().lower(),
            str(sort_by or "priority_score"),
            str(sort_dir or "desc"),
            int(fetch_limit),
        )

    @staticmethod
    def _copy_products_page_slice(
        page: PortalProductsPage, *, limit: int, offset: int
    ) -> PortalProductsPage:
        page_items = list(page.items[offset : offset + limit])
        return PortalProductsPage(
            total=page.total,
            limit=limit,
            offset=offset,
            summary=page.summary,
            items=page_items,
            unavailable_sources=list(page.unavailable_sources or []),
        )

    def _dashboard_overview_cache_key(
        self,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> tuple[object, ...]:
        return (
            "dashboard_overview_v2",
            int(account_id),
            self._actions_cache_date_key(date_from),
            self._actions_cache_date_key(date_to),
            int(limit),
        )

    def _overview_cache_key(
        self,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> tuple[object, ...]:
        return (
            "portal_overview_v2",
            int(account_id),
            self._actions_cache_date_key(date_from),
            self._actions_cache_date_key(date_to),
            int(limit),
        )

    def _data_sync_status_cache_key(self, *, account_id: int) -> tuple[object, ...]:
        return ("data_sync_status_v2", int(account_id))

    def _data_readiness_cache_key(
        self,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[object, ...]:
        return (
            "data_readiness_v2",
            int(account_id),
            self._actions_cache_date_key(date_from),
            self._actions_cache_date_key(date_to),
        )

    @staticmethod
    def _copy_actions_page_slice(
        page: PortalActionsPage, *, limit: int, offset: int
    ) -> PortalActionsPage:
        page_items = list(page.items[offset : offset + limit])
        return PortalActionsPage(
            total=page.total,
            limit=limit,
            offset=offset,
            items=page_items,
            unavailable_sources=list(page.unavailable_sources or []),
        )

    def _dynamic_problem_engine_enabled(self, account_id: int | None) -> bool:
        settings = getattr(self, "settings", get_settings())
        if not bool(getattr(settings, "dynamic_problem_engine_enabled", True)):
            return False
        rollout_ids = list(
            getattr(settings, "dynamic_problem_engine_test_account_ids", []) or []
        )
        if rollout_ids and account_id is not None:
            return int(account_id) in {int(item) for item in rollout_ids}
        return True

    def _show_legacy_problem_cards(self) -> bool:
        settings = getattr(self, "settings", get_settings())
        return bool(getattr(settings, "show_legacy_problem_cards", True))

    async def assignable_users(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        user: AuthUser,
    ) -> list[PortalAssignableUserRead]:
        account = await session.get(WBAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        if not getattr(user, "is_superuser", False):
            access_role = (
                await session.execute(
                    select(AuthUserAccountAccess.role).where(
                        AuthUserAccountAccess.account_id == account_id,
                        AuthUserAccountAccess.user_id == int(user.id),
                    )
                )
            ).scalar_one_or_none()
            if access_role is None:
                raise HTTPException(status_code=403, detail="Account access forbidden")

        rows = list(
            (
                await session.execute(
                    select(AuthUser, AuthUserAccountAccess.role)
                    .join(
                        AuthUserAccountAccess,
                        AuthUserAccountAccess.user_id == AuthUser.id,
                    )
                    .where(
                        AuthUserAccountAccess.account_id == account_id,
                        AuthUser.is_active.is_(True),
                    )
                    .order_by(
                        AuthUser.full_name.asc(),
                        AuthUser.email.asc(),
                        AuthUser.id.asc(),
                    )
                )
            ).all()
        )
        superusers = list(
            (
                await session.execute(
                    select(AuthUser)
                    .where(
                        AuthUser.is_superuser.is_(True), AuthUser.is_active.is_(True)
                    )
                    .order_by(
                        AuthUser.full_name.asc(),
                        AuthUser.email.asc(),
                        AuthUser.id.asc(),
                    )
                )
            ).scalars()
        )

        by_id: dict[int, PortalAssignableUserRead] = {}
        for row_user, role in rows:
            display_name = (
                row_user.full_name or row_user.email or f"Пользователь {row_user.id}"
            )
            by_id[int(row_user.id)] = PortalAssignableUserRead(
                id=int(row_user.id),
                email=str(row_user.email),
                full_name=str(row_user.full_name or ""),
                display_name=display_name,
                role="superuser"
                if bool(row_user.is_superuser)
                else str(role or "viewer").lower(),
                is_active=bool(row_user.is_active),
                is_superuser=bool(row_user.is_superuser),
            )
        for row_user in superusers:
            if int(row_user.id) in by_id:
                continue
            display_name = (
                row_user.full_name or row_user.email or f"Пользователь {row_user.id}"
            )
            by_id[int(row_user.id)] = PortalAssignableUserRead(
                id=int(row_user.id),
                email=str(row_user.email),
                full_name=str(row_user.full_name or ""),
                display_name=display_name,
                role="superuser",
                is_active=bool(row_user.is_active),
                is_superuser=True,
            )
        return sorted(
            by_id.values(), key=lambda item: (item.display_name.lower(), item.id)
        )

    async def _latest_sync_runs_by_domain(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        statuses: set[str] | None = None,
        prefer_non_skipped: bool = False,
    ) -> dict[str, WBSyncRun]:
        filters = [WBSyncRun.account_id == account_id]
        if statuses:
            filters.append(WBSyncRun.status.in_(tuple(statuses)))
        order_by: list[Any] = []
        if prefer_non_skipped:
            order_by.append(case((WBSyncRun.status == "skipped", 1), else_=0).asc())
        order_by.extend([WBSyncRun.started_at.desc(), WBSyncRun.id.desc()])
        ranked = (
            select(
                WBSyncRun.id.label("run_id"),
                func.row_number()
                .over(partition_by=WBSyncRun.domain, order_by=tuple(order_by))
                .label("row_num"),
            )
            .where(*filters)
            .subquery()
        )
        rows = (
            await session.execute(
                select(WBSyncRun)
                .join(ranked, WBSyncRun.id == ranked.c.run_id)
                .where(ranked.c.row_num == 1)
            )
        ).scalars()
        return {str(row.domain): row for row in rows}

    async def data_sync_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> PortalDataSyncStatusRead:
        use_data_sync_cache = isinstance(session, AsyncSession)
        data_sync_cache_key = self._data_sync_status_cache_key(account_id=account_id)
        if use_data_sync_cache:
            cached_status = self._data_sync_status_cache.get(data_sync_cache_key)
            if cached_status is not None:
                return cached_status
        inventory_by_domain: dict[str, list[Any]] = {}
        for entry in WB_CONNECTOR_INVENTORY:
            if entry.status != "active":
                continue
            inventory_by_domain.setdefault(entry.domain, []).append(entry)
        domains = [
            "product_cards",
            "sales",
            "orders",
            "finance",
            "stocks",
            "ads",
            "prices",
            "analytics",
            "tariffs",
            "supplies",
            "documents",
            "reputation",
        ]
        if isinstance(session, AsyncSession):
            latest_run_by_domain = await self._latest_sync_runs_by_domain(
                session,
                account_id=account_id,
                prefer_non_skipped=True,
            )
            latest_success_by_domain = await self._latest_sync_runs_by_domain(
                session,
                account_id=account_id,
                statuses={"completed"},
            )
            latest_failed_by_domain = await self._latest_sync_runs_by_domain(
                session,
                account_id=account_id,
                statuses={"failed"},
            )
            current_runs = list(
                (
                    await session.execute(
                        select(WBSyncRun)
                        .where(
                            WBSyncRun.account_id == account_id,
                            WBSyncRun.status.in_(("running", "queued")),
                        )
                        .order_by(WBSyncRun.started_at.desc(), WBSyncRun.id.desc())
                        .limit(50)
                    )
                ).scalars()
            )
            failed_runs = list(
                (
                    await session.execute(
                        select(WBSyncRun)
                        .where(
                            WBSyncRun.account_id == account_id,
                            WBSyncRun.status == "failed",
                        )
                        .order_by(WBSyncRun.started_at.desc(), WBSyncRun.id.desc())
                        .limit(20)
                    )
                ).scalars()
            )
        else:
            runs = list(
                (
                    await session.execute(
                        select(WBSyncRun)
                        .where(WBSyncRun.account_id == account_id)
                        .order_by(WBSyncRun.started_at.desc(), WBSyncRun.id.desc())
                    )
                ).scalars()
            )
            latest_run_by_domain: dict[str, WBSyncRun] = {}
            latest_success_by_domain: dict[str, WBSyncRun] = {}
            latest_failed_by_domain: dict[str, WBSyncRun] = {}
            for run in runs:
                domain = str(run.domain)
                existing_latest = latest_run_by_domain.get(domain)
                if existing_latest is None or (
                    existing_latest.status == "skipped" and run.status != "skipped"
                ):
                    latest_run_by_domain[domain] = run
                if run.status == "completed":
                    latest_success_by_domain.setdefault(domain, run)
                elif run.status == "failed":
                    latest_failed_by_domain.setdefault(domain, run)
            current_runs = [run for run in runs if run.status in {"running", "queued"}][
                :50
            ]
            failed_runs = [run for run in runs if run.status == "failed"][:20]
        token_categories = {
            str(row)
            for row in (
                await session.execute(
                    select(WBAPIToken.category).where(
                        WBAPIToken.account_id == account_id,
                        WBAPIToken.is_active.is_(True),
                    )
                )
            ).scalars()
        }
        cursors = list(
            (
                await session.execute(
                    select(WBSyncCursor).where(
                        WBSyncCursor.account_id == account_id,
                    )
                )
            ).scalars()
        )
        raw_counts = await self._raw_response_counts_by_domain(
            session, account_id=account_id
        )
        cursor_by_domain: dict[str, WBSyncCursor] = {}
        for cursor in cursors:
            existing = cursor_by_domain.get(str(cursor.domain))
            if existing is None:
                cursor_by_domain[str(cursor.domain)] = cursor
                continue
            current_at = (
                existing.last_synced_at or existing.updated_at or existing.created_at
            )
            candidate_at = (
                cursor.last_synced_at or cursor.updated_at or cursor.created_at
            )
            if candidate_at and (current_at is None or candidate_at > current_at):
                cursor_by_domain[str(cursor.domain)] = cursor
        domain_names = sorted(
            {*domains, *latest_run_by_domain.keys(), *cursor_by_domain.keys()}
        )
        domain_statuses: list[PortalDataSyncDomainStatus] = []
        warnings: list[str] = []
        source_catalog_by_domain = self._readiness_catalog_by_domain()
        for domain in domain_names:
            entries = inventory_by_domain.get(domain) or []
            token_category = (
                entries[0].token_category
                if entries
                else self._fallback_token_category(domain)
            )
            token_configured = bool(
                token_category and token_category in token_categories
            )
            run = latest_run_by_domain.get(domain)
            success_run = latest_success_by_domain.get(domain)
            failed_run = latest_failed_by_domain.get(domain)
            cursor = cursor_by_domain.get(domain)
            raw_status = str(
                getattr(run, "status", None)
                or getattr(cursor, "status", None)
                or "not_started"
            )
            status = (
                raw_status
                if raw_status in {"completed", "failed", "running", "queued", "skipped"}
                else "not_started"
            )
            error_text = getattr(run, "error_text", None) or (
                (cursor.cursor_value or {}).get("lastErrorText") if cursor else None
            )
            last_successful_sync_at = (
                getattr(success_run, "finished_at", None)
                or getattr(cursor, "last_synced_at", None)
                or (
                    getattr(run, "finished_at", None) if status == "completed" else None
                )
            )
            last_failed_sync_at = getattr(failed_run, "finished_at", None)
            last_activity_at = getattr(run, "finished_at", None) or getattr(
                run, "started_at", None
            )
            raw_response_count = int(raw_counts.get(domain, 0))
            rows_loaded = self._rows_loaded_from_details(
                getattr(success_run or run, "details", None)
            )
            if rows_loaded <= 0:
                rows_loaded = raw_response_count
            permission_status = self._permission_status(
                token_configured=token_configured,
                error_text=error_text,
                has_success=bool(last_successful_sync_at or raw_response_count),
            )
            freshness_status = self._freshness_status(
                domain=domain,
                last_successful_sync_at=last_successful_sync_at,
                last_failed_sync_at=last_failed_sync_at,
                permission_status=permission_status,
            )
            next_action = "wait" if status == "running" else "sync"
            if permission_status == "missing":
                next_action = "fix_token"
                warnings.append(
                    f"{domain}: нужен токен WB категории `{token_category}`"
                )
            elif status == "failed":
                warnings.append(f"{domain}: последняя загрузка завершилась ошибкой")
            elif freshness_status == "stale":
                warnings.append(f"{domain}: данные устарели")
            elif freshness_status == "missing":
                warnings.append(f"{domain}: данных ещё нет")
            human_error = self._human_sync_error(
                error_text, token_category=token_category
            )
            source_status = self._source_status_from_sync(
                status=status,
                permission_status=permission_status,
                freshness_status=freshness_status,
            )
            user_facing_status = self._user_facing_sync_status(
                source_status=source_status, run_status=status
            )
            missing_reason = self._source_missing_reason(
                source_status=source_status,
                token_category=token_category,
                human_error=human_error,
                last_successful_sync_at=last_successful_sync_at,
                domain=domain,
            )
            freshness_minutes = self._freshness_minutes(last_successful_sync_at)
            action_code, action_label, target_href = self._next_data_source_action(
                source_status=source_status,
                run_status=status,
                token_category=token_category,
                target_href="/settings?section=integrations",
            )
            catalog_entries = source_catalog_by_domain.get(domain) or []
            first_catalog = catalog_entries[0] if catalog_entries else {}
            domain_statuses.append(
                PortalDataSyncDomainStatus(
                    domain=domain,
                    status=status,  # type: ignore[arg-type]
                    source_code=str(first_catalog.get("source_code") or domain),
                    title=str(
                        first_catalog.get("title") or domain.replace("_", " ").title()
                    ),
                    token_category=token_category,
                    token_configured=token_configured,
                    configured=token_configured,
                    permission_status=permission_status,  # type: ignore[arg-type]
                    permission_ok=True
                    if permission_status == "ok"
                    else False
                    if permission_status == "missing"
                    else None,
                    token_ok=True
                    if permission_status == "ok"
                    else False
                    if permission_status == "missing"
                    else None,
                    last_synced_at=last_successful_sync_at or last_activity_at,
                    last_successful_sync_at=last_successful_sync_at,
                    last_failed_sync_at=last_failed_sync_at,
                    last_error_text=error_text,
                    last_error_human_message=human_error,
                    rows_loaded=rows_loaded,
                    raw_response_count=raw_response_count,
                    freshness_status=freshness_status,  # type: ignore[arg-type]
                    source_status=source_status,  # type: ignore[arg-type]
                    user_facing_status=user_facing_status,
                    freshness_minutes=freshness_minutes,
                    freshness_hours=round(freshness_minutes / 60, 2)
                    if freshness_minutes is not None
                    else None,
                    missing_reason=missing_reason,
                    blocks_calculation=list(
                        dict.fromkeys(
                            block
                            for entry in catalog_entries
                            for block in entry.get("blocks_calculation", [])
                        )
                    ),
                    next_action=next_action,  # type: ignore[arg-type]
                    next_action_code=action_code,
                    next_action_label=action_label,
                    target_href=target_href,
                    next_recommended_action=self._next_sync_action(
                        domain=domain,
                        token_category=token_category,
                        permission_status=permission_status,
                        freshness_status=freshness_status,
                        status=status,
                    ),
                    required_for=self.DATA_SYNC_REQUIRED_FOR.get(domain, []),
                )
            )
        current_sync_runs = [self._sync_run_summary(run) for run in current_runs]
        failed_syncs = [self._sync_run_summary(run) for run in failed_runs]
        queued_syncs = [item for item in current_sync_runs if item.status == "queued"]
        active_sync_progress = [
            item for item in current_sync_runs if item.status == "running"
        ]
        local_source_counts = await self._portal_local_source_counts(
            session, account_id=account_id
        )
        readiness_sources = self._readiness_sources_from_sync(
            domain_statuses=domain_statuses,
            local_counts=local_source_counts,
        )
        if any(item.permission_status == "missing" for item in domain_statuses):
            overall_state = "failed"
        elif any(item.freshness_status == "failed" for item in domain_statuses):
            overall_state = "warning"
        elif any(
            item.status == "running" or item.freshness_status in {"stale", "missing"}
            for item in domain_statuses
        ):
            overall_state = "warning"
        elif any(item.freshness_status == "fresh" for item in domain_statuses):
            overall_state = "ok"
        else:
            overall_state = "unknown"
        user_facing_status = self._overall_user_facing_sync_status(
            domain_statuses=domain_statuses,
            current_sync_runs=current_sync_runs,
        )
        result = PortalDataSyncStatusRead(
            account_id=account_id,
            overall_state=overall_state,  # type: ignore[arg-type]
            user_facing_status=user_facing_status,
            domains=domain_statuses,
            sources=readiness_sources,
            current_sync_runs=current_sync_runs,
            last_successful_sync_by_source={
                item.source_code: item.last_synced_at for item in readiness_sources
            },
            failed_syncs=failed_syncs,
            queued_syncs=queued_syncs,
            active_sync_progress=active_sync_progress,
            safe_actions=[
                PortalSafeAction(
                    id="sync_latest",
                    label="Обновить реальные данные",
                    endpoint="POST /api/v1/sync/trigger",
                ),
                PortalSafeAction(
                    id="dq_run",
                    label="Перепроверить качество данных",
                    endpoint="POST /api/v1/dq/run",
                ),
            ],
            warnings=warnings,
        )
        if use_data_sync_cache:
            self._data_sync_status_cache.set(data_sync_cache_key, result)
        return result

    async def _raw_response_counts_by_domain(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, int]:
        prefixes = tuple(
            prefix
            for values in self.RAW_ENDPOINT_PREFIXES.values()
            for prefix in values
        )
        if not prefixes:
            return {}
        filters = [RawWBAPIResponse.endpoint.startswith(prefix) for prefix in prefixes]
        rows = (
            await session.execute(
                select(RawWBAPIResponse.endpoint, func.count(RawWBAPIResponse.id))
                .where(
                    RawWBAPIResponse.account_id == account_id,
                    or_(*filters),
                )
                .group_by(RawWBAPIResponse.endpoint)
            )
        ).all()
        counts = {domain: 0 for domain in self.RAW_ENDPOINT_PREFIXES}
        for endpoint, count in rows:
            endpoint_str = str(endpoint or "")
            for domain, domain_prefixes in self.RAW_ENDPOINT_PREFIXES.items():
                if any(endpoint_str.startswith(prefix) for prefix in domain_prefixes):
                    counts[domain] += int(count or 0)
                    break
        return counts

    @staticmethod
    def _fallback_token_category(domain: str) -> str | None:
        return {
            "product_cards": "content",
            "prices": "prices",
            "orders": "statistics",
            "sales": "statistics",
            "stocks": "analytics",
            "analytics": "analytics",
            "finance": "finance",
            "ads": "promotion",
            "tariffs": "tariffs",
            "supplies": "supplies",
            "documents": "documents",
            "reputation": "feedbacks_questions",
        }.get(domain)

    @classmethod
    def _rows_loaded_from_details(cls, details: Any) -> int:
        if not isinstance(details, dict):
            return 0
        candidate_keys = {
            "rowsloaded",
            "rowsreceived",
            "rowscreated",
            "rowsupdated",
            "rowscount",
            "rowcount",
            "received",
            "created",
            "updated",
            "loaded",
            "reportsloaded",
            "itemsloaded",
            "detailsrowsloaded",
        }
        values: list[int] = []
        for key, value in details.items():
            normalized = str(key).replace("_", "").lower()
            if normalized in candidate_keys and isinstance(value, int | float):
                values.append(max(0, int(value)))
            elif isinstance(value, dict):
                nested = cls._rows_loaded_from_details(value)
                if nested:
                    values.append(nested)
        return max(values, default=0)

    @staticmethod
    def _is_auth_error(error_text: Any) -> bool:
        lowered = str(error_text or "").lower()
        if any(
            token in lowered
            for token in (
                "token",
                "credential",
                "unauthorized",
                "forbidden",
                "permission",
            )
        ):
            return True
        return bool(
            re.search(
                r"\b(?:api|http|response|status|error)\b[^\n]{0,80}(?<![$\d])\b(?:401|403)\b(?!\d)",
                lowered,
            )
        )

    @classmethod
    def _permission_status(
        cls, *, token_configured: bool, error_text: Any, has_success: bool
    ) -> str:
        if not token_configured:
            return "missing"
        if cls._is_auth_error(error_text):
            return "missing"
        if has_success:
            return "ok"
        return "unknown"

    @classmethod
    def _freshness_status(
        cls,
        *,
        domain: str,
        last_successful_sync_at: Any,
        last_failed_sync_at: Any,
        permission_status: str,
    ) -> str:
        if permission_status == "missing":
            return "missing"
        if last_failed_sync_at is not None and (
            last_successful_sync_at is None
            or last_failed_sync_at >= last_successful_sync_at
        ):
            return "failed"
        if last_successful_sync_at is None:
            return "missing"
        window = cls.DATA_SYNC_FRESHNESS_WINDOWS.get(domain, timedelta(hours=24))
        try:
            age = utcnow() - last_successful_sync_at
        except TypeError:
            age = utcnow().replace(tzinfo=None) - last_successful_sync_at.replace(
                tzinfo=None
            )
        return "fresh" if age <= window else "stale"

    @classmethod
    def _human_sync_error(
        cls, error_text: Any, *, token_category: str | None
    ) -> str | None:
        if not error_text:
            return None
        if cls._is_auth_error(error_text):
            return f"Нет доступа WB. Нужен активный токен категории `{token_category}`."
        return str(error_text)[:500]

    @staticmethod
    def _next_sync_action(
        *,
        domain: str,
        token_category: str | None,
        permission_status: str,
        freshness_status: str,
        status: str,
    ) -> str:
        if permission_status == "missing":
            return f"Добавить или проверить WB токен категории `{token_category}`."
        if status == "running":
            return "Дождаться завершения текущей синхронизации."
        if freshness_status == "failed":
            return (
                "Открыть журнал sync, исправить ошибку и перезапустить синхронизацию."
            )
        if freshness_status == "stale":
            return f"Запустить синхронизацию домена `{domain}`."
        if freshness_status == "missing":
            return f"Запустить первую синхронизацию домена `{domain}`."
        return "Данные свежие. Действие не требуется."

    @classmethod
    def _readiness_catalog_by_domain(cls) -> dict[str, list[dict[str, Any]]]:
        by_domain: dict[str, list[dict[str, Any]]] = {}
        for entry in cls.DATA_READINESS_SOURCE_CATALOG:
            for domain in entry.get("domains", ()):
                by_domain.setdefault(str(domain), []).append(entry)
        return by_domain

    @classmethod
    def _source_status_from_sync(
        cls,
        *,
        status: str,
        permission_status: str,
        freshness_status: str,
    ) -> str:
        if permission_status == "missing":
            return "not_configured"
        if status == "failed" or freshness_status == "failed":
            return "error"
        if freshness_status == "fresh":
            return "fresh"
        if freshness_status == "stale":
            return "stale"
        return "missing"

    @staticmethod
    def _user_facing_sync_status(*, source_status: str, run_status: str) -> str:
        if run_status == "running":
            return "Синхронизация идёт"
        if source_status == "fresh":
            return "Данные свежие"
        if source_status == "not_configured":
            return "Источник не настроен"
        if source_status == "error":
            return "Ошибка синхронизации"
        return "Нужна синхронизация"

    @classmethod
    def _overall_user_facing_sync_status(
        cls,
        *,
        domain_statuses: list[PortalDataSyncDomainStatus],
        current_sync_runs: list[PortalDataSyncRunSummary],
    ) -> str:
        if any(item.status == "running" for item in current_sync_runs):
            return "Синхронизация идёт"
        if any(item.source_status == "error" for item in domain_statuses):
            return "Ошибка синхронизации"
        if any(item.source_status == "not_configured" for item in domain_statuses):
            return "Источник не настроен"
        if any(item.source_status in {"missing", "stale"} for item in domain_statuses):
            return "Нужна синхронизация"
        if any(item.source_status == "fresh" for item in domain_statuses):
            return "Данные свежие"
        return "Нужна синхронизация"

    @classmethod
    def _source_missing_reason(
        cls,
        *,
        source_status: str,
        token_category: str | None,
        human_error: str | None,
        last_successful_sync_at: datetime | None,
        domain: str,
    ) -> str | None:
        if source_status == "not_configured":
            return f"Не настроен активный WB токен категории `{token_category}`."
        if source_status == "error":
            return human_error or "Последняя синхронизация завершилась ошибкой."
        if source_status == "missing":
            return "Успешной синхронизации ещё не было."
        if source_status == "stale":
            return f"Последняя успешная синхронизация домена `{domain}` устарела."
        if source_status == "fresh" and last_successful_sync_at is None:
            return "Нет времени последней синхронизации."
        return None

    @staticmethod
    def _freshness_minutes(last_synced_at: datetime | None) -> int | None:
        if last_synced_at is None:
            return None
        now = utcnow()
        try:
            delta = now - last_synced_at
        except TypeError:
            delta = now.replace(tzinfo=None) - last_synced_at.replace(tzinfo=None)
        return max(0, int(delta.total_seconds() // 60))

    @staticmethod
    def _next_data_source_action(
        *,
        source_status: str,
        run_status: str,
        token_category: str | None,
        target_href: str | None,
    ) -> tuple[str, str, str | None]:
        if run_status == "running":
            return "wait_sync", "Дождаться синхронизации", target_href or "/settings"
        if source_status == "not_configured":
            label = (
                f"Настроить источник {token_category}"
                if token_category
                else "Настроить источник"
            )
            return "configure_source", label, target_href or "/settings"
        if source_status == "error":
            return (
                "retry_sync",
                "Исправить ошибку и повторить синхронизацию",
                target_href or "/settings",
            )
        if source_status in {"missing", "stale"}:
            return "run_sync", "Запустить синхронизацию", target_href or "/settings"
        return "none", "Действие не требуется", target_href

    @classmethod
    def _sync_run_summary(cls, run: WBSyncRun) -> PortalDataSyncRunSummary:
        rows_loaded = cls._rows_loaded_from_details(getattr(run, "details", None))
        details = getattr(run, "details", None)
        progress_percent: float | None = None
        if isinstance(details, dict):
            for key in ("progress_percent", "progress", "percent"):
                value = details.get(key)
                if isinstance(value, int | float):
                    progress_percent = max(0.0, min(100.0, float(value)))
                    break
        status = str(getattr(run, "status", "") or "unknown")
        source_status = (
            "fresh"
            if status == "completed"
            else "error"
            if status == "failed"
            else "missing"
        )
        return PortalDataSyncRunSummary(
            id=int(getattr(run, "id", 0) or 0),
            source_code=str(getattr(run, "domain", "") or ""),
            domain=str(getattr(run, "domain", "") or ""),
            status=status,
            trigger=str(getattr(run, "trigger", "") or "") or None,
            started_at=getattr(run, "started_at", None),
            finished_at=getattr(run, "finished_at", None),
            is_backfill=bool(getattr(run, "is_backfill", False)),
            progress_percent=progress_percent,
            rows_loaded=rows_loaded,
            error_text=getattr(run, "error_text", None),
            user_facing_status=cls._user_facing_sync_status(
                source_status=source_status, run_status=status
            ),
        )

    @classmethod
    def _readiness_sources_from_sync(
        cls,
        *,
        domain_statuses: list[PortalDataSyncDomainStatus],
        local_counts: dict[str, dict[str, Any]],
    ) -> list[PortalDataReadinessSource]:
        by_domain = {item.domain: item for item in domain_statuses}
        sources: list[PortalDataReadinessSource] = []
        for entry in cls.DATA_READINESS_SOURCE_CATALOG:
            source_code = str(entry["source_code"])
            domains = tuple(str(domain) for domain in entry.get("domains", ()))
            target_href = str(entry.get("target_href") or "/settings")
            if domains:
                source = cls._readiness_source_from_domain_entry(
                    entry=entry,
                    domain_statuses=[
                        by_domain[domain] for domain in domains if domain in by_domain
                    ],
                    missing_domains=[
                        domain for domain in domains if domain not in by_domain
                    ],
                    target_href=target_href,
                )
            else:
                source = cls._readiness_source_from_local_entry(
                    entry=entry,
                    local_signal=local_counts.get(source_code, {}),
                    target_href=target_href,
                )
            sources.append(source)
        return sources

    @classmethod
    def _readiness_source_from_domain_entry(
        cls,
        *,
        entry: dict[str, Any],
        domain_statuses: list[PortalDataSyncDomainStatus],
        missing_domains: list[str],
        target_href: str,
    ) -> PortalDataReadinessSource:
        if not domain_statuses:
            status = "missing"
            last_synced_at = None
            freshness_minutes = None
            missing_reason = (
                f"Нет sync-записей для доменов: {', '.join(missing_domains)}."
            )
            run_status = "not_started"
            token_category = None
        else:
            priority = {
                "error": 0,
                "not_configured": 1,
                "missing": 2,
                "stale": 3,
                "fresh": 4,
            }
            worst = min(
                domain_statuses,
                key=lambda item: priority.get(str(item.source_status or "missing"), 99),
            )
            status = str(worst.source_status or "missing")
            run_status = str(worst.status or "not_started")
            token_category = worst.token_category
            synced_values = [
                item.last_successful_sync_at or item.last_synced_at
                for item in domain_statuses
                if item.last_successful_sync_at or item.last_synced_at
            ]
            last_synced_at = (
                min(synced_values)
                if synced_values and status == "fresh"
                else max(synced_values)
                if synced_values
                else None
            )
            freshness_minutes = cls._freshness_minutes(last_synced_at)
            missing_reason = worst.missing_reason
            if status == "fresh" and any(
                item.source_status != "fresh" for item in domain_statuses
            ):
                status = "stale"
                missing_reason = "Не все обязательные домены источника свежие."
        action_code, action_label, action_href = cls._next_data_source_action(
            source_status=status,
            run_status=run_status,
            token_category=token_category,
            target_href=target_href,
        )
        return PortalDataReadinessSource(
            source_code=str(entry["source_code"]),
            title=str(entry["title"]),
            status=status,  # type: ignore[arg-type]
            last_synced_at=last_synced_at,
            freshness_minutes=freshness_minutes,
            freshness_hours=round(freshness_minutes / 60, 2)
            if freshness_minutes is not None
            else None,
            required_for=list(entry.get("required_for", [])),
            blocks_calculation=list(entry.get("blocks_calculation", []))
            if status != "fresh"
            else [],
            missing_reason=missing_reason,
            next_action_code=action_code,
            next_action_label=action_label,
            target_href=action_href,
        )

    @classmethod
    def _readiness_source_from_local_entry(
        cls,
        *,
        entry: dict[str, Any],
        local_signal: dict[str, Any],
        target_href: str,
    ) -> PortalDataReadinessSource:
        row_count = int(local_signal.get("row_count") or 0)
        configured = bool(local_signal.get("configured", True))
        has_error = bool(local_signal.get("error"))
        last_seen_at = local_signal.get("last_seen_at")
        if not configured:
            status = "not_configured"
            missing_reason = str(
                local_signal.get("missing_reason") or "Источник не настроен."
            )
        elif has_error:
            status = "error"
            missing_reason = str(local_signal.get("error"))
        elif row_count <= 0:
            status = "missing"
            missing_reason = str(
                local_signal.get("missing_reason") or "Данных по источнику ещё нет."
            )
        else:
            status = "fresh"
            missing_reason = None
        action_code, action_label, action_href = cls._next_data_source_action(
            source_status=status,
            run_status="not_started",
            token_category=None,
            target_href=target_href,
        )
        freshness_minutes = (
            cls._freshness_minutes(last_seen_at)
            if isinstance(last_seen_at, datetime)
            else None
        )
        return PortalDataReadinessSource(
            source_code=str(entry["source_code"]),
            title=str(entry["title"]),
            status=status,  # type: ignore[arg-type]
            last_synced_at=last_seen_at if isinstance(last_seen_at, datetime) else None,
            freshness_minutes=freshness_minutes,
            freshness_hours=round(freshness_minutes / 60, 2)
            if freshness_minutes is not None
            else None,
            required_for=list(entry.get("required_for", [])),
            blocks_calculation=list(entry.get("blocks_calculation", []))
            if status != "fresh"
            else [],
            missing_reason=missing_reason,
            next_action_code=action_code,
            next_action_label=action_label,
            target_href=action_href,
        )

    async def _portal_local_source_counts(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[str, dict[str, Any]]:
        manual_cost_rows = (
            await session.execute(
                select(
                    func.count(ManualCost.id), func.max(ManualCost.updated_at)
                ).where(ManualCost.account_id == account_id)
            )
        ).one()
        checker_rows = (
            await session.execute(
                select(
                    func.count(CardQualityIssue.id),
                    func.max(CardQualityIssue.updated_at),
                ).where(CardQualityIssue.account_id == account_id)
            )
        ).one()
        checker_snapshot_rows = (
            await session.execute(
                select(
                    func.count(CardQualitySnapshot.id),
                    func.max(CardQualitySnapshot.updated_at),
                ).where(CardQualitySnapshot.account_id == account_id)
            )
        ).one()
        data_fix_rows = (
            await session.execute(
                select(
                    func.count(DataQualityIssue.id),
                    func.max(DataQualityIssue.updated_at),
                ).where(DataQualityIssue.account_id == account_id)
            )
        ).one()
        problem_rows = (
            await session.execute(
                select(
                    func.count(ProblemInstance.id), func.max(ProblemInstance.updated_at)
                ).where(ProblemInstance.account_id == account_id)
            )
        ).one()
        active_problem_definitions = int(
            (
                await session.execute(
                    select(func.count(ProblemDefinition.id)).where(
                        ProblemDefinition.status == "active"
                    )
                )
            ).scalar_one()
            or 0
        )
        checker_count = int(checker_rows[0] or 0) + int(checker_snapshot_rows[0] or 0)
        checker_seen = max(
            [
                value
                for value in (checker_rows[1], checker_snapshot_rows[1])
                if value is not None
            ],
            default=None,
        )
        return {
            "manual_costs": {
                "row_count": int(manual_cost_rows[0] or 0),
                "last_seen_at": manual_cost_rows[1],
                "missing_reason": "Себестоимость не загружена или не сопоставлена.",
            },
            "checker_card_quality": {
                "row_count": checker_count,
                "last_seen_at": checker_seen,
                "missing_reason": "Проверки качества карточек ещё не запускались.",
            },
            "data_fix": {
                "row_count": int(data_fix_rows[0] or 0),
                "last_seen_at": data_fix_rows[1],
                "missing_reason": "Data Fix ещё не находил или не рассчитывал issues.",
            },
            "problem_engine": {
                "row_count": int(problem_rows[0] or 0),
                "last_seen_at": problem_rows[1],
                "configured": active_problem_definitions > 0,
                "missing_reason": "Нет активных правил problem engine."
                if active_problem_definitions <= 0
                else "Problem engine ещё не создавал проблем.",
            },
        }

    async def data_readiness(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> PortalDataReadinessRead:
        use_data_readiness_cache = isinstance(session, AsyncSession)
        data_readiness_cache_key = self._data_readiness_cache_key(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        if use_data_readiness_cache:
            cached_readiness = self._data_readiness_cache.get(data_readiness_cache_key)
            if cached_readiness is not None:
                return cached_readiness
        health = await self.operator_snapshots.data_health(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        blockers_payload = await self.money.data_blockers(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        dq_summary = await self.operator_snapshots.dq_issue_summary(
            session, account_id=account_id
        )
        sync_status = await self.data_sync_status(session, account_id=account_id)
        local_source_counts = await self._portal_local_source_counts(
            session, account_id=account_id
        )
        readiness_sources = self._readiness_sources_from_sync(
            domain_statuses=sync_status.domains,
            local_counts=local_source_counts,
        )
        last_successful_sync_by_source = {
            item.source_code: item.last_synced_at for item in readiness_sources
        }
        sync_status = sync_status.model_copy(
            update={
                "sources": readiness_sources,
                "last_successful_sync_by_source": last_successful_sync_by_source,
            }
        )
        blockers = self._readiness_blockers(
            getattr(blockers_payload, "blockers", []) or []
        )
        final_blockers_total = int(
            getattr(health, "final_profit_blockers_total", 0)
            or getattr(health, "financial_final_blockers_total", 0)
            or getattr(dq_summary, "financial_final_blockers_total", 0)
            or len(blockers)
        )
        operational_trusted = bool(
            getattr(health, "operational_trusted", False)
            or getattr(health, "can_generate_business_actions", False)
        )
        operational_state = "ok" if operational_trusted else "blocked"
        if operational_state == "ok" and (
            sync_status.overall_state in {"warning", "failed"}
            or getattr(blockers_payload, "warnings_count", 0)
        ):
            operational_state = "warning"
        final_state = (
            "final"
            if bool(getattr(health, "financial_final", False))
            and final_blockers_total == 0
            else "blocked"
        )
        if final_state != "final" and operational_trusted:
            final_state = "provisional"
        sync_by_domain = {item.domain: item for item in sync_status.domains}
        finance_sync = sync_by_domain.get("finance")
        operational_sync_exists = any(
            (
                sync_by_domain.get(domain)
                and sync_by_domain[domain].freshness_status in {"fresh", "stale"}
            )
            for domain in ("sales", "orders")
        )
        finance_not_final = bool(
            finance_sync
            and finance_sync.freshness_status in {"missing", "stale", "failed"}
        )
        readiness_warnings = [
            str(getattr(item, "title", None) or getattr(item, "code", None) or item)
            for item in (getattr(blockers_payload, "warnings", []) or [])
        ]
        if finance_not_final and operational_sync_exists:
            final_state = "provisional"
            readiness_warnings.append(
                "Финансовые данные WB отсутствуют, устарели или упали при синхронизации: деньги показаны предварительно, не финально."
            )
        missing_cost_revenue = float(
            getattr(getattr(health, "cost_coverage", None), "missing_cost_revenue", 0.0)
            or getattr(health, "revenue_without_cost", 0.0)
            or 0.0
        )
        missing_cost_count = int(
            getattr(health, "missing_manual_cost_count", 0)
            or max(
                0,
                int(getattr(health, "active_sku_count", 0) or 0)
                - int(getattr(health, "active_sku_with_manual_cost_count", 0) or 0),
            )
        )
        revenue_coverage = getattr(health, "revenue_cost_coverage_percent", None)
        cost_state = "ok"
        if missing_cost_count > 0 or missing_cost_revenue > 0:
            cost_state = "warning"
        if revenue_coverage is not None and float(revenue_coverage) < 95:
            cost_state = "blocked"
        next_steps = self._readiness_next_steps(
            blockers, missing_cost_count=missing_cost_count, sync_status=sync_status
        )
        result = PortalDataReadinessRead(
            account_id=account_id,
            operational_status=PortalStatusBlock(
                state=operational_state,
                title="Операционно можно работать"
                if operational_state in {"ok", "warning"}
                else "Операционные данные заблокированы",
                message="Данных достаточно для ежедневных решений"
                if operational_state in {"ok", "warning"}
                else "Есть блокеры, мешающие ежедневным решениям",
            ),
            final_profit_status=PortalStatusBlock(
                state=final_state,
                title="Финальная прибыль готова"
                if final_state == "final"
                else "Финальная прибыль пока предварительная",
                message="Финальная сверка не содержит блокеров"
                if final_state == "final"
                else f"Есть {final_blockers_total} блокера финальной сверки",
            ),
            cost_status=PortalCostStatus(
                sku_coverage_percent=getattr(health, "sku_cost_coverage_percent", None),
                revenue_coverage_percent=revenue_coverage,
                missing_cost_count=missing_cost_count,
                missing_cost_revenue=missing_cost_revenue,
                state=cost_state,  # type: ignore[arg-type]
            ),
            sources=readiness_sources,
            blockers=blockers,
            warnings=readiness_warnings,
            sync_status=sync_status,
            next_steps=next_steps,
        )
        if use_data_readiness_cache:
            self._data_readiness_cache.set(data_readiness_cache_key, result)
        return result

    @staticmethod
    def _readiness_blockers(raw_blockers: list[Any]) -> list[PortalReadinessBlocker]:
        priority_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        by_code: dict[str, PortalReadinessBlocker] = {}
        for item in raw_blockers:
            code = str(getattr(item, "code", "") or "")
            if not code or PortalService._is_hidden_code(code):
                continue
            current = by_code.get(code)
            candidate = PortalReadinessBlocker(
                code=code,
                priority=str(getattr(item, "priority", None) or "medium"),
                title=str(getattr(item, "title", None) or code),
                affected_sku_count=int(getattr(item, "affected_sku_count", 0) or 0),
                affected_revenue=float(getattr(item, "affected_revenue", 0.0) or 0.0),
                next_screen_path=str(getattr(item, "next_screen_path", None) or ""),
                primary_button_label=str(
                    getattr(item, "next_screen_label", None)
                    or getattr(item, "primary_button_label", None)
                    or "Открыть"
                ),
            )
            if current is None:
                by_code[code] = candidate
                continue
            current.affected_sku_count += candidate.affected_sku_count
            current.affected_revenue += candidate.affected_revenue
            if priority_rank.get(candidate.priority, 99) < priority_rank.get(
                current.priority, 99
            ):
                current.priority = candidate.priority
                current.title = candidate.title
        return sorted(
            by_code.values(),
            key=lambda item: (priority_rank.get(item.priority, 99), item.code),
        )

    @staticmethod
    def _readiness_next_steps(
        blockers: list[PortalReadinessBlocker],
        *,
        missing_cost_count: int,
        sync_status: PortalDataSyncStatusRead,
    ) -> list[PortalNextStep]:
        steps: dict[str, PortalNextStep] = {}
        if missing_cost_count > 0 or any(
            "cost" in blocker.code for blocker in blockers
        ):
            steps["fix_costs"] = PortalNextStep(
                id="fix_costs", label="Загрузить себестоимость", screen_path="/costs"
            )
        if any(
            blocker.code in {"unmatched_sku"} or "dq" in blocker.code
            for blocker in blockers
        ):
            steps["fix_data"] = PortalNextStep(
                id="fix_data", label="Открыть Data Fix", screen_path="/data-fix"
            )
        if sync_status.overall_state in {"warning", "failed", "unknown"}:
            steps["sync_latest"] = PortalNextStep(
                id="sync_latest",
                label="Обновить реальные данные",
                endpoint="POST /api/v1/sync/trigger",
            )
        steps["dq_run"] = PortalNextStep(
            id="dq_run",
            label="Перепроверить качество данных",
            endpoint="POST /api/v1/dq/run",
        )
        return list(steps.values())

    DASHBOARD_PULSE_ORDER: tuple[tuple[str, str], ...] = (
        ("sales", "Продажи"),
        ("profit_margin", "Прибыль и маржа"),
        ("money_at_risk", "Деньги под риском"),
        ("stock", "Остатки"),
        ("cards", "Карточки"),
        ("data", "Данные"),
    )
    DASHBOARD_PULSE_SOURCE_CODES: dict[str, tuple[str, ...]] = {
        "sales": ("sales_orders",),
        "profit_margin": (
            "sales_orders",
            "finance_reports_wb",
            "manual_costs",
            "expenses",
        ),
        "money_at_risk": ("sales_orders", "finance_reports_wb", "ads"),
        "stock": ("stocks", "sales_orders"),
        "cards": ("product_cards_content", "checker_card_quality"),
        "data": (
            "finance_reports_wb",
            "sales_orders",
            "product_cards_content",
            "stocks",
            "manual_costs",
            "ads",
            "data_fix",
        ),
    }
    DASHBOARD_PULSE_DEFAULTS: dict[str, dict[str, Any]] = {
        "sales": {
            "unit": "RUB",
            "impact_type": "business_signal",
            "ok_text": "Продажи проверены по свежим источникам.",
        },
        "profit_margin": {
            "unit": "%",
            "impact_type": "profitability",
            "ok_text": "Прибыль и маржа рассчитаны по свежим данным.",
        },
        "money_at_risk": {
            "unit": "RUB",
            "impact_type": "finance_investigation",
            "ok_text": "Финансовых расхождений и системных денежных рисков не видно.",
        },
        "stock": {
            "unit": "SKU",
            "impact_type": "business_signal",
            "ok_text": "Остатки проверены, открытых stock-сигналов нет.",
        },
        "cards": {
            "unit": "шт",
            "impact_type": "sync_waiting",
            "ok_text": "Карточки и варианты проверены.",
        },
        "data": {
            "unit": "issues",
            "impact_type": "system_check",
            "ok_text": "Источники свежие, открытых data-health buckets нет.",
        },
    }
    DASHBOARD_SEVERITY_RANK: dict[str, int] = {
        "critical": 0,
        "error": 1,
        "high": 1,
        "warning": 2,
        "medium": 2,
        "info": 3,
        "low": 3,
    }
    DASHBOARD_STATE_RANK: dict[str, int] = {
        "blocked": 0,
        "critical": 1,
        "missing_data": 2,
        "stale": 3,
        "syncing": 4,
        "warning": 5,
        "not_checked": 6,
        "ok": 7,
    }
    DASHBOARD_ISSUE_PULSE_MAP: dict[str, tuple[str, ...]] = {
        "stock_without_sales": ("stock",),
        "dead_stock": ("stock",),
        "sales_without_stock": ("stock", "data"),
        "stocks_task_not_ready": ("stock", "data"),
        "stocks_task_failed": ("stock", "data"),
        "latest_stocks_not_completed": ("stock", "data"),
        "missing_chrt_id": ("cards", "data"),
        "missing_manual_cost": ("profit_margin", "data"),
        "missing_cost_blocks_profit": ("profit_margin", "data"),
        "seller_other_expense_missing": ("profit_margin", "data"),
        "manual_cost_unresolved_sku": ("profit_margin", "data"),
        "manual_cost_ambiguous_match": ("profit_margin", "data"),
        "finance_without_sale": ("money_at_risk",),
        "sale_without_finance": ("money_at_risk",),
        "order_without_sale_or_return": ("money_at_risk",),
        "ads_not_allocated_to_profitability": ("money_at_risk", "data"),
        "ads_overallocated_to_profitability": ("money_at_risk", "data"),
        "ad_spend_without_sku": ("money_at_risk", "data"),
        "ad_spend_without_sales": ("money_at_risk", "data"),
        "expense_ad_double_count_risk": ("money_at_risk", "data"),
        "expense_unclassified": ("profit_margin", "data"),
        "unclassified_finance_expense": ("profit_margin", "data"),
        "expense_finance_report_missing": ("profit_margin", "data"),
        "expense_logistics_missing": ("profit_margin", "data"),
    }

    async def dashboard_overview(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        limit: int = 10,
    ) -> PortalDashboardOverviewRead:
        safe_limit = min(max(int(limit or 10), 1), 50)
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            not_checked = PortalDashboardSourceFreshness(
                status="not_checked", message="Аккаунт не выбран."
            )
            pulse = [
                PortalDashboardPulseCard(
                    code=code,  # type: ignore[arg-type]
                    title=title,
                    value=None,
                    unit=str(self.DASHBOARD_PULSE_DEFAULTS[code]["unit"]),
                    state="not_checked",
                    checked=False,
                    has_data=False,
                    has_risk=None,
                    short_explanation="Выберите аккаунт, чтобы проверить бизнес-состояние.",
                    source_freshness=not_checked,
                )
                for code, title in self.DASHBOARD_PULSE_ORDER
            ]
            return PortalDashboardOverviewRead(
                account=None,
                date_range=self._date_range(
                    date_from=date_from, date_to=date_to, money_summary=None
                ),
                business_verdict=PortalDashboardBusinessVerdict(
                    state="not_checked",
                    title="Аккаунт не выбран",
                    short_explanation="Dashboard Cockpit ждёт выбранный аккаунт.",
                    primary_action=PortalDashboardPrimaryAction(
                        label="Выбрать аккаунт", screen_path="/settings"
                    ),
                ),
                business_pulse=pulse,
                onboarding_state=PortalDashboardOnboardingState(
                    state="needs_account",
                    missing_steps=["account"],
                    next_step=PortalDashboardPrimaryAction(
                        label="Выбрать аккаунт", screen_path="/settings"
                    ),
                ),
                unavailable_sources=["account"],
            )

        unavailable: list[str] = []
        use_dashboard_cache = isinstance(session, AsyncSession)
        dashboard_cache_key = self._dashboard_overview_cache_key(
            account_id=int(account.id),
            date_from=date_from,
            date_to=date_to,
            limit=safe_limit,
        )
        if use_dashboard_cache:
            cached_dashboard = self._dashboard_overview_cache.get(dashboard_cache_key)
            if cached_dashboard is not None:
                return cached_dashboard
        money_summary = await self._safe_source(
            "money_summary",
            unavailable,
            self.money.summary(
                session, account_id=account.id, date_from=date_from, date_to=date_to
            ),
        )
        health = await self._safe_source(
            "dashboard_data_health",
            unavailable,
            self.operator_snapshots.data_health(
                session, account_id=account.id, date_from=date_from, date_to=date_to
            ),
        )
        blockers_payload = await self._safe_source(
            "data_blockers",
            unavailable,
            self.money.data_blockers(
                session, account_id=account.id, date_from=date_from, date_to=date_to
            ),
        )
        readiness = await self._safe_source(
            "data_readiness",
            unavailable,
            self.data_readiness(
                session, account_id=account.id, date_from=date_from, date_to=date_to
            ),
        )
        sync_status = (
            getattr(readiness, "sync_status", None) if readiness is not None else None
        )
        if sync_status is None:
            sync_status = await self._safe_source(
                "data_sync_status",
                unavailable,
                self.data_sync_status(session, account_id=account.id),
            )
        actions_page = await self._safe_source(
            "finance_actions",
            unavailable,
            self.money.today_actions(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
                priority=None,
                status=None,
                action_type=None,
                group_by="article",
                focus_limit=min(safe_limit, 20),
                limit=safe_limit,
                offset=0,
            ),
        )
        results_page = await self._safe_source(
            "result_events",
            unavailable,
            self.result_tracking.list_results(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
                limit=min(safe_limit, 10),
                offset=0,
            ),
        )

        money_dump = self._dump(money_summary) if money_summary is not None else {}
        issue_records = self._dashboard_issue_records(
            health=health, blockers_payload=blockers_payload
        )
        source_freshness = self._dashboard_source_freshness_by_pulse(
            sync_status=sync_status, readiness=readiness
        )
        business_pulse = self._dashboard_business_pulse(
            health=health,
            money_summary=money_dump,
            issue_records=issue_records,
            source_freshness=source_freshness,
        )
        top_attention_items = self._dashboard_attention_items(
            issue_records=issue_records,
            source_freshness=source_freshness,
            limit=safe_limit,
        )
        today_plan = self._dashboard_today_plan(
            attention_items=top_attention_items,
            actions_page=actions_page,
            limit=safe_limit,
        )
        data_confidence = self._dashboard_data_confidence(
            sync_status=sync_status, readiness=readiness
        )
        business_verdict = self._dashboard_business_verdict(
            business_pulse=business_pulse,
            attention_items=top_attention_items,
            data_confidence=data_confidence,
        )
        onboarding_state = self._dashboard_onboarding_state(
            business_pulse=business_pulse,
            data_confidence=data_confidence,
            attention_items=top_attention_items,
        )
        result = PortalDashboardOverviewRead(
            account=self._account_summary(account),
            date_range=self._date_range(
                date_from=date_from, date_to=date_to, money_summary=money_dump
            ),
            business_verdict=business_verdict,
            business_pulse=business_pulse,
            top_attention_items=top_attention_items,
            today_plan=today_plan,
            data_confidence=data_confidence,
            recent_results_summary=self._dashboard_recent_results_summary(results_page),
            onboarding_state=onboarding_state,
            unavailable_sources=self._dedupe_strings(unavailable),
        )
        if use_dashboard_cache:
            self._dashboard_overview_cache.set(dashboard_cache_key, result)
        return result

    @staticmethod
    def _dashboard_value(value: Any, key: str, default: Any = None) -> Any:
        if isinstance(value, dict):
            return value.get(key, default)
        return getattr(value, key, default)

    @classmethod
    def _dashboard_issue_state(
        cls, code: str, severity: str, *, issue_nature: str
    ) -> str:
        if code in {
            "missing_manual_cost",
            "missing_cost_blocks_profit",
            "seller_other_expense_missing",
        }:
            return "missing_data"
        if issue_nature == "data_blocker":
            return "blocked"
        if code == "sales_without_stock":
            return "stale"
        if str(severity or "").lower() in {"critical", "error"}:
            return "critical" if issue_nature != "finance_investigation" else "warning"
        return "warning"

    @classmethod
    def _dashboard_issue_records(
        cls, *, health: Any, blockers_payload: Any
    ) -> list[dict[str, Any]]:
        records_by_code: dict[str, dict[str, Any]] = {}

        def merge(record: dict[str, Any]) -> None:
            code = str(record.get("code") or "").strip()
            if not code or cls._is_hidden_code(code):
                return
            severity = str(
                record.get("severity") or record.get("priority") or "warning"
            ).lower()
            payload: dict[str, Any] = {}
            if code == "order_without_sale_or_return" and severity in {
                "info",
                "low",
                "warning",
                "medium",
            }:
                payload = {"ageBucket": "warning"}
            contract = issue_fixability_contract(code, payload, severity=severity)
            guide = issue_resolution_guide(code)
            issue_nature = str(
                record.get("issue_nature")
                or contract.get("issue_nature")
                or "system_check"
            )
            state = str(
                record.get("state")
                or cls._dashboard_issue_state(code, severity, issue_nature=issue_nature)
            )
            action = PortalDashboardPrimaryAction(
                label=str(
                    record.get("primary_action_label")
                    or contract.get("primary_action_label")
                    or guide.get("next_screen_label")
                    or "Открыть"
                ),
                screen_path=str(
                    record.get("next_screen_path")
                    or contract.get("target_href")
                    or guide.get("next_screen_path")
                    or ""
                ),
                endpoint=str(record.get("exact_next_endpoint") or ""),
                action_code=str(
                    record.get("primary_action_code")
                    or contract.get("primary_action_code")
                    or ""
                ),
                target_href=str(
                    record.get("target_href") or contract.get("target_href") or ""
                ),
            )
            candidate = {
                "code": code,
                "title": str(
                    record.get("title") or issue_display_message(code, code) or code
                ),
                "severity": severity,
                "priority": cls._dashboard_priority_from_severity(severity),
                "count": max(
                    0, int(record.get("count") or record.get("affected_sku_count") or 0)
                ),
                "state": state,
                "trust_state": str(
                    record.get("trust_state")
                    or ("blocked" if state == "blocked" else "provisional")
                ),
                "impact_type": str(record.get("impact_type") or issue_nature),
                "short_explanation": str(
                    record.get("short_explanation")
                    or record.get("business_impact")
                    or issue_bucket_meta(code).get("business_impact")
                    or guide.get("simple_reason")
                    or ""
                ),
                "primary_action": action,
                "evidence_available": bool(record.get("evidence_available", True)),
                "source": str(record.get("source") or "dashboard_data_health"),
            }
            current = records_by_code.get(code)
            if current is None:
                records_by_code[code] = candidate
                return
            current["count"] = max(
                int(current.get("count") or 0), int(candidate.get("count") or 0)
            )
            if cls.DASHBOARD_SEVERITY_RANK.get(
                candidate["severity"], 99
            ) < cls.DASHBOARD_SEVERITY_RANK.get(str(current.get("severity")), 99):
                current.update(candidate)
            elif (
                not str(
                    current.get("primary_action").screen_path
                    if current.get("primary_action")
                    else ""
                )
                and action.screen_path
            ):
                current["primary_action"] = action

        for bucket in list(getattr(health, "issue_buckets", []) or []):
            code = str(getattr(bucket, "code", "") or "")
            if not code:
                continue
            merge(
                {
                    "code": code,
                    "title": issue_display_message(code, code),
                    "severity": str(getattr(bucket, "severity", "") or "warning"),
                    "count": int(getattr(bucket, "count", 0) or 0),
                    "business_impact": str(
                        getattr(bucket, "business_impact", None)
                        or issue_bucket_meta(code).get("business_impact")
                        or ""
                    ),
                    "source": "dashboard_data_health",
                }
            )
        for source_name, items in (
            (
                "money_data_blockers",
                list(cls._dashboard_value(blockers_payload, "blockers", []) or []),
            ),
            (
                "money_data_warnings",
                list(cls._dashboard_value(blockers_payload, "warnings", []) or []),
            ),
        ):
            for item in items:
                code = str(cls._dashboard_value(item, "code", "") or "")
                if not code:
                    continue
                merge(
                    {
                        "code": code,
                        "title": cls._dashboard_value(item, "title", code),
                        "severity": cls._dashboard_value(item, "priority", "warning"),
                        "count": cls._dashboard_value(item, "affected_sku_count", 0),
                        "business_impact": cls._dashboard_value(
                            item, "business_impact", ""
                        ),
                        "issue_nature": cls._dashboard_value(item, "issue_nature", ""),
                        "primary_action_code": cls._dashboard_value(
                            item, "primary_action_code", ""
                        ),
                        "primary_action_label": cls._dashboard_value(
                            item, "primary_action_label", ""
                        ),
                        "target_href": cls._dashboard_value(item, "target_href", ""),
                        "next_screen_path": cls._dashboard_value(
                            item, "next_screen_path", ""
                        ),
                        "exact_next_endpoint": cls._dashboard_value(
                            item, "exact_next_endpoint", ""
                        ),
                        "state": "blocked"
                        if source_name == "money_data_blockers"
                        and cls._dashboard_value(item, "issue_nature", "")
                        == "data_blocker"
                        else None,
                        "source": source_name,
                    }
                )
        return sorted(
            records_by_code.values(),
            key=lambda item: (
                cls.DASHBOARD_SEVERITY_RANK.get(str(item.get("severity")), 99),
                cls.DASHBOARD_STATE_RANK.get(str(item.get("state")), 99),
                -int(item.get("count") or 0),
                str(item.get("code") or ""),
            ),
        )

    @classmethod
    def _dashboard_priority_from_severity(cls, severity: str) -> str:
        severity = str(severity or "").lower()
        if severity in {"critical", "error", "high"}:
            return "P1" if severity == "high" else "P0"
        if severity in {"warning", "medium"}:
            return "P2"
        return "P3"

    @classmethod
    def _dashboard_source_freshness_by_pulse(
        cls,
        *,
        sync_status: Any,
        readiness: Any,
    ) -> dict[str, PortalDashboardSourceFreshness]:
        sources = list(
            getattr(readiness, "sources", [])
            or getattr(sync_status, "sources", [])
            or []
        )
        by_source = {
            str(getattr(item, "source_code", "") or ""): item for item in sources
        }
        domain_by_source = {
            str(
                getattr(item, "source_code", "") or getattr(item, "domain", "") or ""
            ): item
            for item in list(getattr(sync_status, "domains", []) or [])
        }
        result: dict[str, PortalDashboardSourceFreshness] = {}
        for pulse_code, required_sources in cls.DASHBOARD_PULSE_SOURCE_CODES.items():
            required = list(required_sources)
            statuses: list[tuple[str, str, Any]] = []
            for source_code in required:
                item = by_source.get(source_code) or domain_by_source.get(source_code)
                status = str(
                    getattr(item, "status", None)
                    or getattr(item, "source_status", None)
                    or getattr(item, "freshness_status", None)
                    or "not_checked"
                )
                if status == "error" or status == "failed":
                    status = "stale"
                if status == "not_configured":
                    status = "missing"
                if getattr(item, "status", None) in {"running", "queued"}:
                    status = "syncing"
                statuses.append((source_code, status, item))
            if not statuses:
                result[pulse_code] = PortalDashboardSourceFreshness(
                    status="not_checked",
                    required_sources=required,
                    message="Свежесть источников ещё не проверена.",
                )
                continue
            missing = [
                code
                for code, status, _ in statuses
                if status in {"missing", "not_configured"}
            ]
            stale = [
                code
                for code, status, _ in statuses
                if status in {"stale", "error", "failed"}
            ]
            syncing = [
                code
                for code, status, _ in statuses
                if status in {"syncing", "running", "queued"}
            ]
            fresh = [code for code, status, _ in statuses if status == "fresh"]
            if missing:
                status = "missing"
            elif stale:
                status = "stale"
            elif syncing:
                status = "syncing"
            elif len(fresh) == len(statuses):
                status = "fresh"
            else:
                status = "not_checked"
            synced_values = [
                getattr(item, "last_synced_at", None)
                for _, _, item in statuses
                if getattr(item, "last_synced_at", None) is not None
            ]
            freshness_values = [
                float(getattr(item, "freshness_hours", 0) or 0)
                for _, _, item in statuses
                if getattr(item, "freshness_hours", None) is not None
            ]
            result[pulse_code] = PortalDashboardSourceFreshness(
                status=status,  # type: ignore[arg-type]
                required_sources=required,
                fresh_sources=fresh,
                stale_sources=stale,
                missing_sources=missing,
                syncing_sources=syncing,
                last_synced_at=max(synced_values) if synced_values else None,
                freshness_hours=max(freshness_values) if freshness_values else None,
                message=cls._dashboard_freshness_message(
                    status, missing=missing, stale=stale, syncing=syncing
                ),
            )
        return result

    @staticmethod
    def _dashboard_freshness_message(
        status: str, *, missing: list[str], stale: list[str], syncing: list[str]
    ) -> str:
        if status == "missing":
            return f"Нет данных источников: {', '.join(missing)}."
        if status == "stale":
            return f"Устарели источники: {', '.join(stale)}."
        if status == "syncing":
            return f"Синхронизация ещё идёт: {', '.join(syncing)}."
        if status == "fresh":
            return "Источники свежие."
        return "Источник ещё не проверен."

    @classmethod
    def _dashboard_business_pulse(
        cls,
        *,
        health: Any,
        money_summary: dict[str, Any],
        issue_records: list[dict[str, Any]],
        source_freshness: dict[str, PortalDashboardSourceFreshness],
    ) -> list[PortalDashboardPulseCard]:
        issues_by_pulse: dict[str, list[dict[str, Any]]] = {
            code: [] for code, _ in cls.DASHBOARD_PULSE_ORDER
        }
        for issue in issue_records:
            code = str(issue.get("code") or "")
            for pulse_code in cls.DASHBOARD_ISSUE_PULSE_MAP.get(code, ("data",)):
                issues_by_pulse.setdefault(pulse_code, []).append(issue)
        pulse_cards: list[PortalDashboardPulseCard] = []
        for code, title in cls.DASHBOARD_PULSE_ORDER:
            defaults = cls.DASHBOARD_PULSE_DEFAULTS[code]
            freshness = source_freshness.get(code) or PortalDashboardSourceFreshness(
                status="not_checked"
            )
            checked = health is not None
            has_data = freshness.status not in {"missing", "not_checked"} and checked
            state = "ok"
            trust_state = "trusted"
            impact_type = str(defaults["impact_type"])
            explanation = str(defaults["ok_text"])
            primary_action = PortalDashboardPrimaryAction()
            issues = issues_by_pulse.get(code, [])
            evidence_available = checked and freshness.status == "fresh"
            if not checked:
                state = "not_checked"
                has_data = False
                trust_state = "not_checked"
                explanation = "Проверка ещё не запускалась."
            elif freshness.status == "missing":
                state = "missing_data"
                has_data = False
                trust_state = "blocked"
                impact_type = "data_blocker"
                explanation = freshness.message or "Не хватает исходных данных."
                primary_action = PortalDashboardPrimaryAction(
                    label="Настроить источник", screen_path="/settings"
                )
            elif freshness.status == "stale":
                state = "stale"
                trust_state = "stale"
                explanation = freshness.message or "Источник данных устарел."
                primary_action = PortalDashboardPrimaryAction(
                    label="Обновить данные", screen_path="/admin"
                )
            elif freshness.status == "syncing":
                state = "syncing"
                trust_state = "syncing"
                explanation = freshness.message or "Синхронизация ещё идёт."
                primary_action = PortalDashboardPrimaryAction(
                    label="Открыть синхронизацию", screen_path="/admin"
                )
            elif issues:
                top = min(
                    issues,
                    key=lambda item: (
                        cls.DASHBOARD_STATE_RANK.get(str(item.get("state")), 99),
                        cls.DASHBOARD_SEVERITY_RANK.get(str(item.get("severity")), 99),
                    ),
                )
                state = str(top.get("state") or "warning")
                trust_state = str(top.get("trust_state") or "provisional")
                impact_type = str(top.get("impact_type") or impact_type)
                explanation = str(
                    top.get("short_explanation")
                    or top.get("title")
                    or "Есть открытые issue buckets."
                )
                primary_action = (
                    top.get("primary_action")
                    if isinstance(
                        top.get("primary_action"), PortalDashboardPrimaryAction
                    )
                    else PortalDashboardPrimaryAction()
                )
                evidence_available = True
            elif freshness.status == "not_checked":
                state = "not_checked"
                has_data = False
                trust_state = "not_checked"
                explanation = (
                    freshness.message
                    or "Свежесть источников и детектор ещё не проверены."
                )
            if code == "profit_margin" and any(
                item.get("code")
                in {
                    "missing_manual_cost",
                    "missing_cost_blocks_profit",
                    "seller_other_expense_missing",
                }
                for item in issues
            ):
                state = "missing_data"
                has_data = False
                trust_state = "blocked"
                impact_type = "data_blocker"
            if code == "data" and any(
                item.get("impact_type") == "data_blocker" for item in issues
            ):
                state = "blocked"
                trust_state = "blocked"
                impact_type = "data_blocker"
            has_risk = None
            if checked and has_data and freshness.status == "fresh":
                has_risk = bool(issues)
            pulse_cards.append(
                PortalDashboardPulseCard(
                    code=code,  # type: ignore[arg-type]
                    title=title,
                    value=cls._dashboard_pulse_value(
                        code,
                        money_summary=money_summary,
                        health=health,
                        issue_count=len(issues),
                    ),
                    unit=str(defaults["unit"]),
                    state=state,  # type: ignore[arg-type]
                    checked=checked,
                    has_data=has_data,
                    has_risk=has_risk,
                    trust_state=trust_state,
                    impact_type=impact_type,
                    short_explanation=explanation,
                    primary_action=primary_action,
                    evidence_available=evidence_available,
                    source_freshness=freshness,
                )
            )
        return pulse_cards

    @classmethod
    def _dashboard_pulse_value(
        cls, code: str, *, money_summary: dict[str, Any], health: Any, issue_count: int
    ) -> float | int | str | None:
        kpis = (
            money_summary.get("kpis")
            if isinstance(money_summary.get("kpis"), dict)
            else {}
        )
        cash_stock = (
            money_summary.get("cash_and_stock")
            if isinstance(money_summary.get("cash_and_stock"), dict)
            else {}
        )
        if code == "sales":
            return (
                kpis.get("revenue")
                or kpis.get("realized_revenue")
                or kpis.get("revenue_operational")
            )
        if code == "profit_margin":
            return (
                kpis.get("margin_percent")
                or kpis.get("net_margin_percent")
                or kpis.get("profit_margin_percent")
            )
        if code == "money_at_risk":
            return kpis.get("money_at_risk") or kpis.get("expected_loss_amount") or 0
        if code == "stock":
            return (
                cash_stock.get("stock_value")
                or kpis.get("stock_value")
                or getattr(health, "all_open_stock_issue_count", issue_count)
            )
        if code == "cards":
            return getattr(health, "active_sku_count", None)
        if code == "data":
            return getattr(health, "all_open_issues_total", None) or issue_count
        return None

    @classmethod
    def _dashboard_attention_items(
        cls,
        *,
        issue_records: list[dict[str, Any]],
        source_freshness: dict[str, PortalDashboardSourceFreshness],
        limit: int,
    ) -> list[PortalDashboardAttentionItem]:
        items: list[PortalDashboardAttentionItem] = []
        for issue in issue_records:
            code = str(issue.get("code") or "")
            pulse_code = cls.DASHBOARD_ISSUE_PULSE_MAP.get(code, ("data",))[0]
            items.append(
                PortalDashboardAttentionItem(
                    code=code,
                    title=str(issue.get("title") or code),
                    pulse_code=pulse_code,
                    severity=str(issue.get("severity") or "warning"),
                    priority=str(issue.get("priority") or "P2"),
                    count=int(issue.get("count") or 0),
                    state=str(issue.get("state") or "warning"),  # type: ignore[arg-type]
                    trust_state=str(issue.get("trust_state") or "provisional"),
                    impact_type=str(issue.get("impact_type") or "system_check"),
                    short_explanation=str(issue.get("short_explanation") or ""),
                    primary_action=issue.get("primary_action")
                    if isinstance(
                        issue.get("primary_action"), PortalDashboardPrimaryAction
                    )
                    else PortalDashboardPrimaryAction(),
                    evidence_available=bool(issue.get("evidence_available", True)),
                    source_freshness=source_freshness.get(
                        pulse_code, PortalDashboardSourceFreshness(status="not_checked")
                    ),
                    source=str(issue.get("source") or "dashboard_data_health"),
                )
            )
        items.sort(
            key=lambda item: (
                cls.DASHBOARD_STATE_RANK.get(item.state, 99),
                cls.DASHBOARD_SEVERITY_RANK.get(item.severity, 99),
                -item.count,
                item.code,
            )
        )
        return items[:limit]

    @classmethod
    def _dashboard_today_plan(
        cls,
        *,
        attention_items: list[PortalDashboardAttentionItem],
        actions_page: Any,
        limit: int,
    ) -> list[PortalDashboardPlanItem]:
        plan: list[PortalDashboardPlanItem] = []
        for item in attention_items:
            action = item.primary_action
            plan.append(
                PortalDashboardPlanItem(
                    id=f"issue:{item.code}",
                    title=action.label or item.title,
                    priority=item.priority,
                    source=item.source,
                    source_code=item.code,
                    screen_path=action.screen_path or action.target_href,
                    endpoint=action.endpoint,
                    action_code=action.action_code,
                    trust_state=item.trust_state,
                    impact_type=item.impact_type,
                    reason=item.short_explanation,
                    saved_money_claimed=False,
                )
            )
        for raw in list(
            getattr(actions_page, "owner_focus_actions", [])
            or getattr(actions_page, "items", [])
            or []
        ):
            if len(plan) >= limit:
                break
            action_type = str(cls._dashboard_value(raw, "action_type", "") or "")
            linked = cls._dashboard_value(raw, "linked_entity", {}) or {}
            if not isinstance(linked, dict):
                linked = {}
            plan.append(
                PortalDashboardPlanItem(
                    id=f"action:{cls._dashboard_value(raw, 'id', action_type) or action_type}",
                    title=str(
                        cls._dashboard_value(raw, "title", "")
                        or cls._dashboard_value(raw, "next_step", "")
                        or action_type
                    ),
                    priority=str(cls._dashboard_value(raw, "priority", "P3") or "P3"),
                    source="money_actions",
                    source_code=action_type,
                    screen_path=cls._dashboard_money_action_screen_path(
                        action_type, linked
                    ),
                    endpoint=str(
                        cls._dashboard_value(raw, "source_endpoint", "") or ""
                    ),
                    action_code=action_type,
                    trust_state="confirmed"
                    if bool(cls._dashboard_value(raw, "financial_final", False))
                    else "provisional",
                    impact_type="opportunity",
                    reason=str(
                        cls._dashboard_value(raw, "why", "")
                        or cls._dashboard_value(raw, "business_reason", "")
                        or ""
                    ),
                    expected_impact_amount=float(
                        cls._dashboard_value(raw, "expected_effect_amount", 0) or 0
                    ),
                    saved_money_claimed=False,
                )
            )
        deduped: list[PortalDashboardPlanItem] = []
        seen: set[tuple[str | None, str | None]] = set()
        for item in plan:
            key = (item.source_code, item.screen_path or item.endpoint)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped[:limit]

    @staticmethod
    def _dashboard_money_action_screen_path(
        action_type: str, linked: dict[str, Any]
    ) -> str:
        normalized = str(action_type or "").lower()
        nm_id = linked.get("nm_id")
        if "cost" in normalized:
            return "/costs?focus=missing-costs"
        if "stock" in normalized or "reorder" in normalized:
            return f"/products/{nm_id}" if nm_id else "/stock"
        if "ads" in normalized or "ad_" in normalized:
            return "/money?section=ads"
        if "price" in normalized:
            return f"/products/{nm_id}?tab=price" if nm_id else "/pricing"
        return "/money"

    @classmethod
    def _dashboard_data_confidence(
        cls, *, sync_status: Any, readiness: Any
    ) -> list[PortalDashboardDataConfidenceItem]:
        raw_sources = list(
            getattr(readiness, "sources", [])
            or getattr(sync_status, "sources", [])
            or []
        )
        if not raw_sources:
            raw_sources = list(getattr(sync_status, "domains", []) or [])
        items: list[PortalDashboardDataConfidenceItem] = []
        for source in raw_sources:
            raw_state = str(
                getattr(source, "status", None)
                or getattr(source, "source_status", None)
                or getattr(source, "freshness_status", None)
                or "not_checked"
            )
            state = raw_state
            if raw_state in {"failed"}:
                state = "error"
            if raw_state in {"not_configured"}:
                state = "missing"
            if state not in {
                "fresh",
                "stale",
                "missing",
                "syncing",
                "not_checked",
                "error",
            }:
                state = (
                    "syncing" if raw_state in {"running", "queued"} else "not_checked"
                )
            items.append(
                PortalDashboardDataConfidenceItem(
                    source_code=str(
                        getattr(source, "source_code", None)
                        or getattr(source, "domain", None)
                        or ""
                    ),
                    title=str(
                        getattr(source, "title", None)
                        or getattr(source, "domain", None)
                        or ""
                    ),
                    state=state,  # type: ignore[arg-type]
                    last_synced_at=getattr(source, "last_synced_at", None)
                    or getattr(source, "last_successful_sync_at", None),
                    freshness_hours=getattr(source, "freshness_hours", None),
                    required_for=list(getattr(source, "required_for", []) or []),
                    blocks_calculation=list(
                        getattr(source, "blocks_calculation", []) or []
                    ),
                    target_href=getattr(source, "target_href", None),
                    message=str(
                        getattr(source, "missing_reason", None)
                        or getattr(source, "user_facing_status", None)
                        or ""
                    ),
                )
            )
        rank = {
            "error": 0,
            "missing": 1,
            "stale": 2,
            "syncing": 3,
            "not_checked": 4,
            "fresh": 5,
        }
        return sorted(
            items, key=lambda item: (rank.get(item.state, 99), item.source_code)
        )

    @staticmethod
    def _dashboard_recent_results_summary(
        results_page: Any,
    ) -> PortalDashboardRecentResultsSummary:
        if results_page is None:
            return PortalDashboardRecentResultsSummary(status="unavailable", total=0)
        events = []
        for item in list(
            getattr(results_page, "recent_events", [])
            or getattr(results_page, "items", [])
            or []
        )[:5]:
            if hasattr(item, "model_dump"):
                events.append(item.model_dump(mode="json"))
            elif isinstance(item, dict):
                events.append(dict(item))
        summary = dict(getattr(results_page, "summary", {}) or {})
        summary["saved_money_claimed"] = False
        return PortalDashboardRecentResultsSummary(
            status=str(getattr(results_page, "status", "ok") or "ok"),
            total=int(getattr(results_page, "total", 0) or 0),
            summary=summary,
            by_outcome=dict(getattr(results_page, "by_outcome", {}) or {}),
            recent_events=events,
            saved_money_claimed=False,
        )

    @classmethod
    def _dashboard_business_verdict(
        cls,
        *,
        business_pulse: list[PortalDashboardPulseCard],
        attention_items: list[PortalDashboardAttentionItem],
        data_confidence: list[PortalDashboardDataConfidenceItem],
    ) -> PortalDashboardBusinessVerdict:
        state = "ok"
        title = "Можно работать"
        explanation = "Ключевые проверки свежие, открытых рисков не найдено."
        trust_state = "trusted"
        impact_type = "business_signal"
        primary_action = PortalDashboardPrimaryAction(
            label="Открыть действия", screen_path="/action-center"
        )
        if any(card.state == "blocked" for card in business_pulse):
            state = "blocked"
            title = "Есть блокеры данных"
            explanation = "Сначала закройте data blockers, затем считайте прибыль и действия надежными."
            trust_state = "blocked"
            impact_type = "data_blocker"
        elif any(card.state == "missing_data" for card in business_pulse):
            state = "missing_data"
            title = "Не хватает данных"
            explanation = "Часть бизнес-ответов нельзя считать без недостающих источников или себестоимости."
            trust_state = "blocked"
            impact_type = "data_blocker"
        elif any(card.state == "stale" for card in business_pulse):
            state = "stale"
            title = "Данные устарели"
            explanation = "Обновите источники перед выводом «всё в порядке»."
            trust_state = "stale"
            impact_type = "sync_waiting"
            primary_action = PortalDashboardPrimaryAction(
                label="Открыть синхронизацию", screen_path="/admin"
            )
        elif any(card.state in {"critical", "warning"} for card in business_pulse):
            state = "warning"
            top = attention_items[0] if attention_items else None
            title = "Есть зоны внимания"
            explanation = (
                top.short_explanation
                if top is not None and top.short_explanation
                else "Есть открытые issue buckets или бизнес-сигналы."
            )
            trust_state = "provisional"
            impact_type = top.impact_type if top is not None else "business_signal"
            primary_action = top.primary_action if top is not None else primary_action
        elif any(card.state in {"not_checked", "syncing"} for card in business_pulse):
            state = (
                "not_checked"
                if any(card.state == "not_checked" for card in business_pulse)
                else "syncing"
            )
            title = "Проверка ещё не финальная"
            explanation = "Дождитесь проверки или синхронизации источников."
            trust_state = state
            impact_type = "system_check"
        checked = all(card.checked for card in business_pulse)
        has_data = all(
            card.has_data for card in business_pulse if card.code != "data"
        ) and not any(item.state == "missing" for item in data_confidence)
        has_risk = None
        if (
            checked
            and has_data
            and not any(
                card.source_freshness.status != "fresh" for card in business_pulse
            )
        ):
            has_risk = state != "ok"
        return PortalDashboardBusinessVerdict(
            state=state,  # type: ignore[arg-type]
            title=title,
            short_explanation=explanation,
            trust_state=trust_state,
            impact_type=impact_type,
            checked=checked,
            has_data=has_data,
            has_risk=has_risk,
            primary_action=primary_action,
        )

    @staticmethod
    def _dashboard_onboarding_state(
        *,
        business_pulse: list[PortalDashboardPulseCard],
        data_confidence: list[PortalDashboardDataConfidenceItem],
        attention_items: list[PortalDashboardAttentionItem],
    ) -> PortalDashboardOnboardingState:
        missing_steps: list[str] = []
        if any(item.state in {"missing", "error"} for item in data_confidence):
            missing_steps.append("sync_sources")
        if any(
            card.code == "profit_margin" and card.state == "missing_data"
            for card in business_pulse
        ):
            missing_steps.append("costs")
        if any(item.impact_type == "data_blocker" for item in attention_items):
            missing_steps.append("data_fix")
        if "sync_sources" in missing_steps:
            return PortalDashboardOnboardingState(
                state="needs_sync",
                missing_steps=missing_steps,
                next_step=PortalDashboardPrimaryAction(
                    label="Открыть синхронизацию", screen_path="/admin"
                ),
            )
        if "costs" in missing_steps:
            return PortalDashboardOnboardingState(
                state="needs_costs",
                missing_steps=missing_steps,
                next_step=PortalDashboardPrimaryAction(
                    label="Загрузить себестоимость",
                    screen_path="/costs?focus=missing-costs",
                ),
            )
        if "data_fix" in missing_steps:
            return PortalDashboardOnboardingState(
                state="needs_data_fix",
                missing_steps=missing_steps,
                next_step=PortalDashboardPrimaryAction(
                    label="Открыть починку данных", screen_path="/data-fix"
                ),
            )
        return PortalDashboardOnboardingState(state="ready", missing_steps=[])

    async def overview(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
    ) -> PortalOverviewRead:
        safe_limit = min(max(int(limit or 10), 1), 50)
        account = await self._active_account(session, account_id=account_id)
        unavailable: list[str] = []
        if account is None:
            return PortalOverviewRead(
                account=None,
                date_range=self._date_range(
                    date_from=date_from, date_to=date_to, money_summary=None
                ),
                date_from=date_from,
                date_to=date_to,
                module_health=await self._module_health(account=None),
                unavailable_sources=["account"],
            )
        use_overview_cache = isinstance(session, AsyncSession)
        overview_cache_key = self._overview_cache_key(
            account_id=int(account.id),
            date_from=date_from,
            date_to=date_to,
            limit=safe_limit,
        )
        if use_overview_cache:
            cached_overview = self._overview_cache.get(overview_cache_key)
            if cached_overview is not None:
                return cached_overview
        module_health = await self._module_health(account=account)

        money_summary = await self._safe_source(
            "money_summary",
            unavailable,
            self.money.summary(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
            ),
        )
        blockers = await self._safe_source(
            "data_blockers",
            unavailable,
            self.money.data_blockers(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
            ),
        )
        actions_page = await self._safe_source(
            "finance_actions",
            unavailable,
            self.money.today_actions(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
                priority=None,
                status=None,
                action_type=None,
                group_by="article",
                focus_limit=min(safe_limit, 20),
                limit=safe_limit,
                offset=0,
            ),
        )
        products_page = await self._safe_source(
            "top_products",
            unavailable,
            self.money.articles(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
                search=None,
                status=None,
                trust_state=None,
                subject_name=None,
                brand=None,
                sort_by="priority_score",
                sort_dir="desc",
                limit=safe_limit,
                offset=0,
            ),
        )
        profit_doctor = await self._safe_source(
            "profit_doctor",
            unavailable,
            self.profit_doctor.diagnose(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
                limit=max(safe_limit, 20),
            ),
        )

        top_actions = []
        if actions_page is not None:
            top_actions.extend(self._money_actions(getattr(actions_page, "items", [])))
        if blockers is not None:
            top_actions.extend(self._blocker_actions(blockers))
        checker_actions, checker_unavailable = await self._safe_optional_actions(
            "checker",
            unavailable,
            self.checker.quality_actions(account, limit=safe_limit),
        )
        if checker_unavailable:
            unavailable.append(checker_unavailable)
        top_actions.extend(checker_actions)
        grouping_actions, grouping_unavailable = await self._safe_optional_actions(
            "grouping",
            unavailable,
            self.grouping.recommendation_actions(account, limit=safe_limit),
        )
        if grouping_unavailable:
            unavailable.append(grouping_unavailable)
        top_actions.extend(grouping_actions)
        local_grouping_actions = await self._safe_source(
            "grouping_beta",
            unavailable,
            self.grouping_beta.recommendation_actions(
                session, account_id=account.id, limit=safe_limit
            ),
        )
        top_actions.extend(local_grouping_actions or [])
        reputation_actions, reputation_unavailable = await self._safe_optional_actions(
            "reputation",
            unavailable,
            self.reputation.reputation_actions(session, account, limit=safe_limit),
        )
        if reputation_unavailable:
            unavailable.append(reputation_unavailable)
        top_actions.extend(reputation_actions)
        claims_actions, claims_unavailable = await self._safe_optional_actions(
            "claims",
            unavailable,
            self.claims_adapter.claims_actions(
                account, limit=safe_limit, session=session
            ),
        )
        if claims_unavailable:
            unavailable.append(claims_unavailable)
        top_actions.extend(claims_actions)
        stockops_actions, stockops_unavailable = await self._safe_optional_actions(
            "stockops",
            unavailable,
            self.stock_control.action_candidates(
                session, account_id=account.id, limit=safe_limit
            ),
        )
        if stockops_unavailable:
            unavailable.append(stockops_unavailable)
        top_actions.extend(stockops_actions)
        experiment_actions = await self._safe_source(
            "experiments",
            unavailable,
            self.experiments.action_candidates(
                session, account_id=account.id, limit=safe_limit
            ),
        )
        top_actions.extend(experiment_actions or [])
        top_actions = [
            item for item in top_actions if not self._is_hidden_action_center_item(item)
        ]
        top_actions = self._dedupe_actions(top_actions)
        top_actions.sort(key=self._action_sort_key)

        money_dump = self._overview_money_summary(money_summary)
        blockers_dump = (
            self._dump(blockers)
            if blockers is not None
            else self._unavailable_block("data_blockers")
        )
        top_products = (
            [self._product_row(item) for item in getattr(products_page, "items", [])]
            if products_page is not None
            else []
        )
        if profit_doctor is not None:
            unavailable.extend(
                list(getattr(profit_doctor, "unavailable_sources", []) or [])
            )
        result = PortalOverviewRead(
            account=self._account_summary(account),
            date_range=self._date_range(
                date_from=date_from, date_to=date_to, money_summary=money_dump
            ),
            date_from=date_from,
            date_to=date_to,
            money_summary=money_dump,
            doctor_summary=self._doctor_summary(profit_doctor),
            top_problems=self._doctor_top_problems(profit_doctor, limit=5),
            operator_actions=self._doctor_actions(profit_doctor, limit=5),
            product_risks=self._doctor_product_risks(profit_doctor, limit=5),
            reputation=self._reputation_block(module_health, profit_doctor),
            claims=self._claims_block(module_health, profit_doctor),
            data_trust=self._data_trust(money_dump, blockers_dump),
            data_blockers=blockers_dump,
            cost_status=self._cost_status(money_dump),
            top_actions=top_actions[:safe_limit],
            top_products=top_products[:safe_limit],
            module_health=module_health,
            unavailable_sources=self._dedupe_strings(unavailable),
        )
        if use_overview_cache:
            self._overview_cache.set(overview_cache_key, result)
        return result

    async def actions(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        status: str | None,
        source_module: list[str] | None = None,
        priority: list[str] | None = None,
        nm_id: int | None = None,
        action_type: list[str] | None = None,
        problem_code: list[str] | None = None,
        trust_state: list[str] | None = None,
        impact_type: list[str] | None = None,
        include_beta: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> PortalActionsPage:
        account = await self._active_account(session, account_id=account_id)
        unavailable: list[str] = []
        if account is None:
            return PortalActionsPage(
                total=0,
                limit=limit,
                offset=offset,
                items=[],
                unavailable_sources=["account"],
            )

        dynamic_enabled = self._dynamic_problem_engine_enabled(account.id)
        show_legacy_problem_cards = self._show_legacy_problem_cards()
        fetch_limit = min(max(limit + offset, limit), 200)
        use_actions_cache = isinstance(session, AsyncSession)
        actions_cache_key = self._actions_cache_key(
            account_id=account.id,
            date_from=date_from,
            date_to=date_to,
            status=status,
            source_module=source_module,
            priority=priority,
            nm_id=nm_id,
            action_type=action_type,
            problem_code=problem_code,
            trust_state=trust_state,
            impact_type=impact_type,
            include_beta=include_beta,
            fetch_limit=fetch_limit,
            dynamic_enabled=dynamic_enabled,
            show_legacy_problem_cards=show_legacy_problem_cards,
        )
        if use_actions_cache:
            cached_actions = self._actions_cache.get(actions_cache_key)
            if cached_actions is not None:
                return self._copy_actions_page_slice(
                    cached_actions, limit=limit, offset=offset
                )
        actions_page = await self._safe_source(
            "finance_actions",
            unavailable,
            self.money.today_actions(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
                priority=None,
                status=self._finance_status_filter(status),
                action_type=None,
                group_by="article",
                focus_limit=min(fetch_limit, 20),
                limit=fetch_limit,
                offset=0,
            ),
        )
        dq_page = await self._safe_source(
            "data_quality_issues",
            unavailable,
            self.data_quality.list_issues(
                session,
                account_id=account.id,
                only_open=True,
                financial_final_blocker=None,
                sort_by="detected_at",
                sort_dir="desc",
                limit=fetch_limit,
                offset=0,
            ),
        )
        cost_page = await self._safe_source(
            "unresolved_costs",
            unavailable,
            self.manual_costs.list_unresolved_costs_page(
                session,
                account_id=account.id,
                limit=fetch_limit,
                offset=0,
            ),
        )
        unified_rows = await self._safe_source(
            "unified_actions",
            unavailable,
            self._list_unified_actions(
                session, account_id=account.id, limit=fetch_limit
            ),
        )
        blockers = await self._safe_source(
            "data_blockers",
            unavailable,
            self.money.data_blockers(
                session,
                account_id=account.id,
                date_from=date_from,
                date_to=date_to,
            ),
        )
        problem_actions = (
            await self._safe_source(
                "dynamic_problem_instances",
                unavailable,
                self._problem_instance_actions(
                    session,
                    account_id=account.id,
                    nm_id=nm_id,
                    limit=fetch_limit,
                    include_finance_windows=False,
                ),
            )
            if dynamic_enabled
            else []
        )
        checker_actions, checker_unavailable = await self._safe_optional_actions(
            "checker",
            unavailable,
            self.checker.quality_actions(account, limit=fetch_limit),
        )
        local_quality_actions = await self._safe_source(
            "card_quality",
            unavailable,
            self.card_quality.quality_actions(
                session, account_id=account.id, limit=fetch_limit
            ),
        )
        if checker_unavailable:
            unavailable.append(checker_unavailable)
        grouping_actions: list[PortalActionRead] = []
        local_grouping_actions: list[PortalActionRead] = []
        reputation_actions: list[PortalActionRead] = []
        claims_actions: list[PortalActionRead] = []
        stockops_actions: list[PortalActionRead] = []
        experiment_actions: list[PortalActionRead] = []
        profit_doctor = None
        include_reputation_beta = include_beta
        if include_beta:
            grouping_actions, grouping_unavailable = await self._safe_optional_actions(
                "grouping",
                unavailable,
                self.grouping.recommendation_actions(account, limit=fetch_limit),
            )
            if grouping_unavailable:
                unavailable.append(grouping_unavailable)
            grouping_filter_requested = "grouping" in {
                self._normalize_source_module(value)
                for value in self._normalize_filter_values(source_module)
            }
            local_grouping_actions = (
                await self._safe_source(
                    "grouping_beta",
                    unavailable,
                    self.grouping_beta.recommendation_actions(
                        session,
                        account_id=account.id,
                        limit=fetch_limit,
                        include_reviewed=grouping_filter_requested,
                    ),
                )
                or []
            )
            claims_actions, claims_unavailable = await self._safe_optional_actions(
                "claims",
                unavailable,
                self.claims_adapter.claims_actions(
                    account, limit=fetch_limit, session=session
                ),
            )
            if claims_unavailable:
                unavailable.append(claims_unavailable)
            stockops_actions, stockops_unavailable = await self._safe_optional_actions(
                "stockops",
                unavailable,
                self.stock_control.action_candidates(
                    session, account_id=account.id, limit=fetch_limit
                ),
            )
            if stockops_unavailable:
                unavailable.append(stockops_unavailable)
            experiment_actions = (
                await self._safe_source(
                    "experiments",
                    unavailable,
                    self.experiments.action_candidates(
                        session, account_id=account.id, limit=fetch_limit
                    ),
                )
                or []
            )
            profit_doctor = await self._safe_source(
                "profit_doctor",
                unavailable,
                self.profit_doctor.diagnose(
                    session,
                    account_id=account.id,
                    date_from=date_from,
                    date_to=date_to,
                    limit=fetch_limit,
                ),
            )
            if profit_doctor is not None:
                unavailable.extend(
                    list(getattr(profit_doctor, "unavailable_sources", []) or [])
                )
        if include_reputation_beta:
            reputation_actions, reputation_unavailable = await self._reputation_actions(
                session,
                account=account,
                limit=fetch_limit,
                unavailable=unavailable,
                max_seconds=None,
            )
            if reputation_unavailable:
                unavailable.append(reputation_unavailable)
        module_statuses = self._module_status_map(
            await self._module_health(account=account)
        )
        unified_rows_list = list(unified_rows or [])
        shadow_overrides = self._shadow_status_overrides(unified_rows_list)

        items: list[PortalActionRead] = []
        if actions_page is not None:
            items.extend(self._money_actions(getattr(actions_page, "items", [])))
        if unified_rows is not None:
            items.extend(
                self._unified_action_rows(
                    [
                        row
                        for row in unified_rows_list
                        if not self._is_shadow_action(row)
                        and (
                            include_beta
                            or self._is_mvp_action_module(row.source_module)
                        )
                    ]
                )
            )
        if dq_page is not None:
            items.extend(self._dq_actions(getattr(dq_page, "items", [])))
        if cost_page is not None:
            items.extend(self._cost_actions(getattr(cost_page, "items", [])))
        if blockers is not None:
            items.extend(self._blocker_actions(blockers))
        items.extend(problem_actions or [])
        if not (local_quality_actions or checker_actions):
            items.extend(
                self._checker_setup_actions(
                    account_id=account.id, module_statuses=module_statuses
                )
            )
        items.extend(local_quality_actions or [])
        items.extend(checker_actions)
        items.extend(grouping_actions)
        items.extend(local_grouping_actions)
        items.extend(reputation_actions)
        items.extend(claims_actions)
        items.extend(stockops_actions)
        items.extend(experiment_actions)
        items.extend(self._doctor_action_rows(profit_doctor))
        items = [item for item in items if not self._is_hidden_action_center_item(item)]
        items = self._prefer_dynamic_problem_actions(
            items,
            show_legacy_problem_cards=show_legacy_problem_cards,
        )
        items = [
            self._apply_shadow_status(
                self._finalize_action(item, module_statuses=module_statuses),
                shadow_overrides=shadow_overrides,
            )
            for item in items
        ]
        items = self._dedupe_actions(items)
        items = self._filter_actions(
            items,
            status=status,
            source_module=source_module,
            priority=priority,
            nm_id=nm_id,
            action_type=action_type,
            problem_code=problem_code,
            trust_state=trust_state,
            impact_type=impact_type,
        )
        items.sort(key=self._action_sort_key)
        full_page = PortalActionsPage(
            total=len(items),
            limit=len(items),
            offset=0,
            items=items,
            unavailable_sources=self._dedupe_strings(unavailable),
        )
        if use_actions_cache:
            self._actions_cache.set(actions_cache_key, full_page)
        return self._copy_actions_page_slice(full_page, limit=limit, offset=offset)

    def _is_mvp_action_module(self, value: str | None) -> bool:
        return self._normalize_source_module(value) in self.MVP_ACTION_MODULES

    def _validate_action_status_transition(
        self,
        *,
        old_status: Any,
        new_status: Any,
        event_type: str | None = None,
        allow_initial_shadow_state: bool = False,
    ) -> tuple[str, str]:
        old = self._normalize_status(old_status)
        new = self._normalize_status(new_status)
        if new not in self.ACTION_CENTER_STATUSES:
            raise HTTPException(
                status_code=422, detail=f"Unsupported Action Center status: {new}"
            )
        if old == new:
            return old, new
        if allow_initial_shadow_state and old == "new":
            return old, new
        canonical_event = self._canonical_action_event_type(
            event_type, old_status=old, new_status=new
        )
        allowed = set(self.ACTION_CENTER_TRANSITIONS.get(old, set()))
        if new in allowed:
            if (
                old == "done"
                and new in {"resolved", "reopened"}
                and canonical_event not in {"recheck_completed", "reopened"}
            ):
                raise HTTPException(
                    status_code=409,
                    detail=f"Invalid Action Center status transition: {old} -> {new}. Re-check or explicit reopen is required.",
                )
            return old, new
        raise HTTPException(
            status_code=409,
            detail=f"Invalid Action Center status transition: {old} -> {new}",
        )

    def _canonical_action_event_type(
        self,
        event_type: str | None,
        *,
        old_status: str | None = None,
        new_status: str | None = None,
        field: str | None = None,
    ) -> str:
        raw = str(event_type or "").strip().lower()
        mapping = {
            "status_change": "status_changed",
            "status_changed": "status_changed",
            "dismiss": "dismissed",
            "dismissed": "dismissed",
            "assign": "assigned",
            "assigned": "assigned",
            "comment": "comment_added",
            "comment_added": "comment_added",
            "deadline": "deadline_changed",
            "deadline_changed": "deadline_changed",
            "recheck": "recheck_requested",
            "recheck_requested": "recheck_requested",
            "recheck_completed": "recheck_completed",
            "result_measured": "result_measured",
            "reopened": "reopened",
        }
        if raw in mapping:
            return mapping[raw]
        if field == "assigned_to_user_id":
            return "assigned"
        if field == "deadline_at":
            return "deadline_changed"
        if field == "comment":
            return "comment_added"
        new = self._normalize_status(new_status) if new_status else None
        old = self._normalize_status(old_status) if old_status else None
        if new == "ignored" or new == "dismissed":
            return "dismissed"
        if new == "postponed":
            return "postponed"
        if new == "blocked":
            return "blocked"
        if new == "reopened" or (
            old in {"ignored", "dismissed", "resolved", "done", "postponed"}
            and new == "new"
        ):
            return "reopened"
        return "status_changed"

    def _direct_source_status_for_action_center_status(self, status: str) -> str | None:
        normalized = self._normalize_status(status)
        return (
            normalized
            if normalized in self.ACTION_CENTER_DIRECT_SOURCE_STATUSES
            else None
        )

    def _audit_payload(
        self,
        *,
        event_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
        comment: str | None,
        status_reason: str | None = None,
        user_id: int | None,
    ) -> dict[str, Any]:
        return {
            "event_type": event_type,
            "old_value": jsonable_encoder(old_value) if old_value is not None else None,
            "new_value": jsonable_encoder(new_value) if new_value is not None else None,
            "actor_user_id": user_id,
            "comment": comment,
            "created_at": utcnow().isoformat(),
        }

    def _append_unified_action_history_event(
        self,
        row: UnifiedAction,
        *,
        event_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
        comment: str | None,
        user_id: int | None,
        status_reason: str | None = None,
    ) -> dict[str, Any]:
        payload_json = dict(row.payload_json or {})
        history = list(payload_json.get("action_history") or [])
        event = self._audit_payload(
            event_type=event_type,
            old_value=old_value,
            new_value=new_value,
            comment=comment,
            user_id=user_id,
        )
        history.append(event)
        payload_json["action_history"] = history[-50:]
        if event_type == "status_changed":
            payload_json["last_status_changed_at"] = event["created_at"]
        payload_json["last_changed_at"] = event["created_at"]
        payload_json["last_actor_user_id"] = user_id
        if user_id is not None:
            payload_json["last_changed_by_user_id"] = user_id
        if status_reason or comment:
            payload_json["status_reason"] = status_reason or comment
        row.payload_json = payload_json
        return event

    def _add_action_center_result_event(
        self,
        session: AsyncSession,
        *,
        row: UnifiedAction,
        account_id: int,
        event_type: str,
        status: str,
        message: str,
        payload: dict[str, Any],
        user_id: int | None,
    ) -> None:
        session.add(
            ResultEvent(
                account_id=account_id,
                action_id=getattr(row, "id", None),
                source_module="action_center",
                source_id=row.source_id or str(getattr(row, "id", "")),
                external_id=row.source_id or str(getattr(row, "id", "")),
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                event_type=event_type,
                status=status,
                message=message,
                payload_json={
                    **jsonable_encoder(payload),
                    "actor_user_id": user_id,
                    "saved_money_claimed": False,
                    "causality_note": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
                },
            )
        )

    def _add_action_center_notification_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        notification_type: str,
        message: str,
        source_module: str,
        source_id: str | None = None,
        action_id: int | None = None,
        problem_instance_id: int | None = None,
        problem_code: str | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        assigned_to_user_id: int | None = None,
        deadline_at: Any | None = None,
        outcome: str = "pending",
        payload: dict[str, Any] | None = None,
        user_id: int | None = None,
    ) -> None:
        normalized_type = str(notification_type or "").strip().lower()
        if not normalized_type:
            return
        payload_json = jsonable_encoder(
            {
                **jsonable_encoder(payload or {}),
                "notification_type": normalized_type,
                "actor_user_id": user_id,
                "assigned_to_user_id": assigned_to_user_id,
                "deadline_at": deadline_at,
                "outcome": outcome,
                "saved_money_claimed": False,
                "causality_note": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
            }
        )
        session.add(
            ResultEvent(
                account_id=account_id,
                action_id=action_id,
                problem_instance_id=problem_instance_id,
                problem_code=problem_code,
                source_module="action_center_notifications",
                source_id=source_id
                or (
                    str(problem_instance_id)
                    if problem_instance_id is not None
                    else None
                ),
                external_id=source_id
                or (
                    str(problem_instance_id)
                    if problem_instance_id is not None
                    else None
                ),
                nm_id=nm_id,
                vendor_code=vendor_code,
                event_type="action_center_notification",
                status="new",
                message=message,
                payload_json=payload_json,
            )
        )

    def _add_deadline_notification_if_needed(
        self,
        session: AsyncSession,
        *,
        row: UnifiedAction,
        old_deadline: Any,
        comment: str | None,
        user_id: int | None,
    ) -> None:
        if row.deadline_at is None or old_deadline == row.deadline_at:
            return
        now = utcnow()
        due_in_hours = (row.deadline_at - now).total_seconds() / 3600
        if due_in_hours < 0:
            notification_type = "overdue"
            message = "Action Center task is overdue."
            outcome = "blocked"
        elif due_in_hours <= 24:
            notification_type = "deadline_due_soon"
            message = "Action Center task deadline is due soon."
            outcome = "pending"
        else:
            return
        self._add_action_center_notification_event(
            session,
            account_id=row.account_id,
            notification_type=notification_type,
            message=message,
            source_module=row.source_module,
            source_id=row.source_id or str(row.id),
            action_id=row.id,
            nm_id=row.nm_id,
            vendor_code=row.vendor_code,
            assigned_to_user_id=row.assigned_to_user_id,
            deadline_at=row.deadline_at,
            outcome=outcome,
            payload={"comment": comment, "due_in_hours": due_in_hours},
            user_id=user_id,
        )

    def _add_problem_deadline_notification_if_needed(
        self,
        session: AsyncSession,
        *,
        instance: ProblemInstance,
        old_deadline: Any,
        new_deadline: Any,
        comment: str | None,
        user_id: int | None,
    ) -> None:
        parsed_deadline_raw = self._optional_datetime(new_deadline)
        if isinstance(parsed_deadline_raw, str):
            try:
                parsed_deadline = datetime.fromisoformat(
                    parsed_deadline_raw.replace("Z", "+00:00")
                )
            except ValueError:
                parsed_deadline = None
        else:
            parsed_deadline = parsed_deadline_raw
        if parsed_deadline is None or old_deadline == new_deadline:
            return
        if getattr(parsed_deadline, "tzinfo", None) is None:
            parsed_deadline = parsed_deadline.replace(tzinfo=UTC)
        now = utcnow()
        due_in_hours = (parsed_deadline - now).total_seconds() / 3600
        if due_in_hours < 0:
            notification_type = "overdue"
            message = "Dynamic problem deadline is overdue."
            outcome = "blocked"
        elif due_in_hours <= 24:
            notification_type = "deadline_due_soon"
            message = "Dynamic problem deadline is due soon."
            outcome = "pending"
        else:
            return
        assigned_to_user_id = self._optional_int(
            self._problem_action_state_value(instance, "assigned_to_user_id")
        )
        self._add_action_center_notification_event(
            session,
            account_id=instance.account_id,
            notification_type=notification_type,
            message=message,
            source_module="problem_engine",
            source_id=str(instance.id),
            problem_instance_id=instance.id,
            problem_code=instance.problem_code,
            nm_id=instance.nm_id,
            vendor_code=instance.vendor_code,
            assigned_to_user_id=assigned_to_user_id,
            deadline_at=parsed_deadline,
            outcome=outcome,
            payload={"comment": comment, "due_in_hours": due_in_hours},
            user_id=user_id,
        )

    async def _reputation_action_center_enabled(
        self, session: AsyncSession, account: WBAccount
    ) -> bool:
        try:
            return bool(await self.reputation.action_center_enabled(session, account))
        except Exception:
            return False

    async def _validate_manual_action_assignee(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        user_id: int,
    ) -> None:
        assignee = await session.get(AuthUser, int(user_id))
        if assignee is None or not assignee.is_active:
            raise HTTPException(status_code=422, detail="Assigned user is not active")
        if assignee.is_superuser:
            return
        access = (
            (
                await session.execute(
                    select(AuthUserAccountAccess)
                    .where(
                        AuthUserAccountAccess.account_id == account_id,
                        AuthUserAccountAccess.user_id == int(user_id),
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if access is None:
            raise HTTPException(
                status_code=422,
                detail="Assigned user does not have access to this account",
            )

    async def create_manual_action(
        self,
        session: AsyncSession,
        *,
        payload: PortalManualActionCreateRequest,
        user_id: int | None,
    ) -> PortalActionRead:
        account = await self._active_account(session, account_id=payload.account_id)
        if account is None:
            raise HTTPException(status_code=400, detail="account_id is required")
        await self._validate_manual_action_assignee(
            session,
            account_id=account.id,
            user_id=payload.assigned_to_user_id,
        )

        products = jsonable_encoder(
            [product.model_dump(mode="json") for product in payload.products]
        )
        primary_product = products[0] if products else {}
        nm_id = self._optional_int(primary_product.get("nm_id"))
        sku_id = self._optional_int(primary_product.get("sku_id"))
        vendor_code = str(primary_product.get("vendor_code") or "").strip() or None
        title = str(payload.title or "").strip()
        description = str(payload.description or "").strip()
        task_kind = re.sub(
            r"[^a-z0-9_]+",
            "_",
            str(payload.task_kind or "manual_review").strip().lower(),
        )
        task_kind = task_kind.strip("_") or "manual_review"
        if not task_kind.startswith("manual_"):
            task_kind = f"manual_{task_kind}"
        source_id = f"manual:{uuid4().hex}"
        product_count = len(products)
        primary_label = str(
            primary_product.get("title")
            or primary_product.get("vendor_code")
            or (f"nm {nm_id}" if nm_id else "1 товар")
        )
        product_label = (
            f"{product_count} товаров" if product_count != 1 else primary_label
        )
        summary = description or f"Ручная задача по выбранным товарам: {product_label}."
        payload_json = {
            "manual_task": True,
            "task_kind": task_kind,
            "instructions": description,
            "selected_products": products,
            "product_count": product_count,
            "sku_id": sku_id,
            "vendor_code": vendor_code,
            "photo_url": primary_product.get("photo_url"),
            "linked_entity": primary_product,
            "created_by_user_id": user_id,
            "allowed_actions": ["assign", "dismiss"],
            "impact_type": "opportunity",
            "trust_state": "provisional",
            "source_table": "unified_actions",
            "source_endpoint": "POST /api/v1/portal/actions/manual",
            "data_freshness": {
                "required_sources": ["manual_input"],
                "source_status": "fresh",
                "blocking_sources": [],
                "freshness_notes": ["Задача создана вручную оператором."],
            },
            "solve_map": {
                "title": "Порядок выполнения",
                "summary": "Ручная задача: проверьте выбранные товары, выполните работу и отметьте результат.",
                "steps": [
                    {
                        "step_id": "review_products",
                        "order": 1,
                        "title": "Проверить выбранные товары",
                        "description": f"В задачу добавлено: {product_label}. Убедитесь, что работа относится именно к ним.",
                        "status": "ready",
                        "action_code": None,
                        "required_metrics": ["nm_id"],
                        "completion_signal": "Список товаров понятен ответственному.",
                    },
                    {
                        "step_id": "do_manual_work",
                        "order": 2,
                        "title": title,
                        "description": description
                        or "Выполните ручную работу по выбранным товарам.",
                        "status": "ready",
                        "action_code": "assign",
                        "required_metrics": [],
                        "completion_signal": "Работа выполнена или передана ответственному с результатом.",
                    },
                    {
                        "step_id": "close_task",
                        "order": 3,
                        "title": "Закрыть задачу",
                        "description": "После выполнения отметьте задачу готовой, чтобы она ушла из очереди.",
                        "status": "available",
                        "action_code": "dismiss",
                        "required_metrics": [],
                        "completion_signal": "Статус задачи обновлён в Центре действий.",
                    },
                ],
            },
        }
        row = UnifiedAction(
            account_id=account.id,
            source_module="manual",
            source_id=source_id,
            external_id=source_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            action_type=task_kind,
            status="new",
            priority=str(payload.priority or "P2").upper(),
            trust_state="provisional",
            title=title,
            summary=summary,
            guided_fix_json={
                "route_key": "manual_task",
                "label": "Выполнить ручную задачу",
                "href": "",
            },
            payload_json=payload_json,
        )
        self._apply_unified_action_task_fields(
            row,
            status="new",
            assigned_to_user_id=payload.assigned_to_user_id,
            deadline_at=payload.deadline_at,
            review_status="new",
            user_id=user_id,
        )
        session.add(row)
        await session.flush()
        self._append_unified_action_history_event(
            row,
            event_type="manual_task_created",
            old_value=None,
            new_value={
                "title": title,
                "assigned_to_user_id": payload.assigned_to_user_id,
                "deadline_at": payload.deadline_at.isoformat(),
                "product_count": product_count,
            },
            comment=description or "Ручная задача создана в Центре действий",
            user_id=user_id,
        )
        self._add_action_center_result_event(
            session,
            row=row,
            account_id=account.id,
            event_type="manual_task_created",
            status="new",
            message="Manual Action Center task created.",
            payload={
                "title": title,
                "task_kind": task_kind,
                "product_count": product_count,
                "assigned_to_user_id": payload.assigned_to_user_id,
                "deadline_at": payload.deadline_at,
            },
            user_id=user_id,
        )
        await session.commit()
        self._invalidate_actions_cache()
        await session.refresh(row)
        return self._finalize_action(self._unified_action_row(row))

    async def update_action(
        self,
        session: AsyncSession,
        *,
        action_id: int,
        user_id: int | None,
        payload: PortalActionUpdateRequest,
    ) -> PortalActionRead:
        status = self._normalize_status(payload.status)
        existing_control_action = await session.get(ActionRecommendation, action_id)
        if existing_control_action is not None:
            self._validate_action_status_transition(
                old_status=getattr(existing_control_action, "status", "new"),
                new_status=status,
                event_type=getattr(payload, "event_type", None),
            )
        try:
            updated = await self.control_tower.update_action(
                session,
                action_id=action_id,
                user_id=user_id,
                payload=ActionRecommendationUpdateRequest(
                    status=status, comment=payload.comment
                ),
            )
            if status == "in_progress":
                await self.result_tracking.ensure_before_snapshot(
                    session,
                    account_id=updated.account_id,
                    action_id=action_id,
                    created_by=user_id,
                )
            if status == "done":
                await self.result_tracking.create_action_completed_event(
                    session,
                    account_id=updated.account_id,
                    action_id=action_id,
                    created_by=user_id,
                )
            await session.commit()
            self._invalidate_actions_cache()
            return self._finalize_action(self._control_action(updated))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
        unified = await session.get(UnifiedAction, action_id)
        if unified is None:
            raise HTTPException(status_code=404, detail="Action not found")
        old_status, status = self._validate_action_status_transition(
            old_status=unified.status,
            new_status=status,
            event_type=getattr(payload, "event_type", None),
        )
        old_assigned = unified.assigned_to_user_id
        old_deadline = unified.deadline_at
        old_comment = unified.last_comment
        payload_json = dict(unified.payload_json or {})
        unified.status = status
        unified.payload_json = payload_json
        self._apply_unified_action_task_fields(
            unified,
            status=status,
            comment=payload.comment,
            status_reason=getattr(payload, "status_reason", None),
            assigned_to_user_id=getattr(payload, "assigned_to_user_id", None),
            deadline_at=getattr(payload, "deadline_at", None),
            review_status=getattr(payload, "review_status", None),
            user_id=user_id,
        )
        if old_status != status:
            event_type = self._canonical_action_event_type(
                getattr(payload, "event_type", None),
                old_status=old_status,
                new_status=status,
            )
            self._append_unified_action_history_event(
                unified,
                event_type="status_changed",
                old_value={"status": old_status},
                new_value={"status": status},
                comment=payload.comment,
                status_reason=getattr(payload, "status_reason", None),
                user_id=user_id,
            )
            if event_type != "status_changed":
                self._append_unified_action_history_event(
                    unified,
                    event_type=event_type,
                    old_value={"status": old_status},
                    new_value={"status": status},
                    comment=payload.comment,
                    user_id=user_id,
                )
        if (
            getattr(payload, "assigned_to_user_id", None) is not None
            and old_assigned != unified.assigned_to_user_id
        ):
            self._append_unified_action_history_event(
                unified,
                event_type="assigned",
                old_value={"assigned_to_user_id": old_assigned},
                new_value={"assigned_to_user_id": unified.assigned_to_user_id},
                comment=payload.comment,
                status_reason=getattr(payload, "status_reason", None),
                user_id=user_id,
            )
            self._add_action_center_notification_event(
                session,
                account_id=unified.account_id,
                notification_type="assigned_to_user",
                message="Action Center task assigned to user.",
                source_module=unified.source_module,
                source_id=unified.source_id or str(unified.id),
                action_id=unified.id,
                nm_id=unified.nm_id,
                vendor_code=unified.vendor_code,
                assigned_to_user_id=unified.assigned_to_user_id,
                payload={
                    "old_assigned_to_user_id": old_assigned,
                    "comment": payload.comment,
                },
                user_id=user_id,
            )
        if (
            getattr(payload, "deadline_at", None) is not None
            and old_deadline != unified.deadline_at
        ):
            self._append_unified_action_history_event(
                unified,
                event_type="deadline_changed",
                old_value={
                    "deadline_at": old_deadline.isoformat()
                    if old_deadline is not None
                    else None
                },
                new_value={
                    "deadline_at": unified.deadline_at.isoformat()
                    if unified.deadline_at is not None
                    else None
                },
                comment=payload.comment,
                status_reason=getattr(payload, "status_reason", None),
                user_id=user_id,
            )
            self._add_deadline_notification_if_needed(
                session,
                row=unified,
                old_deadline=old_deadline,
                comment=payload.comment,
                user_id=user_id,
            )
        if payload.comment and payload.comment != old_comment:
            self._append_unified_action_history_event(
                unified,
                event_type="comment_added",
                old_value={"comment": old_comment},
                new_value={"comment": payload.comment},
                comment=payload.comment,
                user_id=user_id,
            )
        primary_event_type = (
            self._canonical_action_event_type(
                getattr(payload, "event_type", None),
                old_status=old_status,
                new_status=status,
            )
            if old_status != status
            else "assigned"
            if getattr(payload, "assigned_to_user_id", None) is not None
            and old_assigned != unified.assigned_to_user_id
            else "deadline_changed"
            if getattr(payload, "deadline_at", None) is not None
            and old_deadline != unified.deadline_at
            else "comment_added"
            if payload.comment and payload.comment != old_comment
            else self._canonical_action_event_type(
                getattr(payload, "event_type", None),
                old_status=old_status,
                new_status=status,
            )
        )
        self._add_action_center_result_event(
            session,
            row=unified,
            account_id=unified.account_id,
            event_type=primary_event_type,
            status=status,
            message="Action Center task update recorded.",
            payload={
                "old_value": {
                    "status": old_status,
                    "assigned_to_user_id": old_assigned,
                    "deadline_at": old_deadline,
                },
                "new_value": {
                    "status": status,
                    "assigned_to_user_id": unified.assigned_to_user_id,
                    "deadline_at": unified.deadline_at,
                },
                "comment": payload.comment,
            },
            user_id=user_id,
        )
        if status == "in_progress":
            await self.result_tracking.ensure_before_snapshot(
                session,
                account_id=unified.account_id,
                action_id=action_id,
                created_by=user_id,
            )
        if status == "done":
            await self.result_tracking.create_action_completed_event(
                session,
                account_id=unified.account_id,
                action_id=action_id,
                created_by=user_id,
            )
            self._add_grouping_review_result_event(
                session,
                account_id=unified.account_id,
                action_id=action_id,
                source_id=unified.source_id or str(action_id),
                nm_id=unified.nm_id,
                vendor_code=unified.vendor_code,
                status=status,
                comment=payload.comment,
                created_by=user_id,
                payload={
                    **dict(unified.payload_json or {}),
                    "source_module": unified.source_module,
                },
            )
            self._append_unified_action_history_event(
                unified,
                event_type="result_measured",
                old_value={"status": old_status},
                new_value={"status": status, "saved_money_claimed": False},
                comment=payload.comment,
                user_id=user_id,
            )
        if old_status != status and status == "reopened":
            self._add_action_center_notification_event(
                session,
                account_id=unified.account_id,
                notification_type="issue_reopened",
                message="Action Center task reopened.",
                source_module=unified.source_module,
                source_id=unified.source_id or str(unified.id),
                action_id=unified.id,
                nm_id=unified.nm_id,
                vendor_code=unified.vendor_code,
                payload={
                    "old_status": old_status,
                    "new_status": status,
                    "comment": payload.comment,
                },
                user_id=user_id,
            )
        await session.commit()
        self._invalidate_actions_cache()
        return self._finalize_action(self._unified_action_row(unified))

    async def upsert_synthetic_action(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action: PortalActionRead | UnifiedActionOut,
        status: str | None = None,
        comment: str | None = None,
        user_id: int | None = None,
        commit: bool = False,
    ) -> UnifiedAction:
        identity = self._synthetic_action_identity(account_id=account_id, action=action)
        row = await self._find_unified_action_by_source(
            session,
            account_id=account_id,
            source_module=identity["source_module"],
            source_id=identity["source_id"],
        )
        payload = self._synthetic_payload(action)
        payload.update(
            {
                "shadow_synthetic": True,
                "source_identity": identity,
                "marketplace_change": False,
                "can_confirm": False,
            }
        )
        if comment:
            payload["last_comment"] = comment
        if user_id is not None:
            payload["last_changed_by_user_id"] = user_id
        if row is None:
            row = UnifiedAction(
                account_id=account_id,
                source_module=identity["source_module"],
                source_id=identity["source_id"],
                external_id=identity["source_id"],
                nm_id=identity.get("nm_id"),
                vendor_code=identity.get("vendor_code"),
                action_type=identity["action_type"],
                status=self._normalize_status(
                    status or self._action_status_value(action) or "new"
                ),
                priority=self._action_priority_value(action),
                trust_state=self._action_trust_state_value(action),
                title=self._action_title_value(action),
                summary=self._action_summary_value(action),
                guided_fix_json=self._action_guided_fix_value(action),
                payload_json=payload,
            )
            self._apply_unified_action_task_fields(
                row, status=row.status, comment=comment, user_id=user_id
            )
            session.add(row)
            await session.flush()
        else:
            row.action_type = identity["action_type"]
            row.nm_id = identity.get("nm_id")
            row.vendor_code = identity.get("vendor_code")
            row.priority = self._action_priority_value(action)
            row.trust_state = self._action_trust_state_value(action)
            row.title = self._action_title_value(action)
            row.summary = self._action_summary_value(action)
            row.guided_fix_json = self._action_guided_fix_value(action)
            row.payload_json = {**dict(row.payload_json or {}), **payload}
            if status:
                row.status = self._normalize_status(status)
            self._apply_unified_action_task_fields(
                row, status=row.status, comment=comment, user_id=user_id
            )
        if commit:
            await session.commit()
            await session.refresh(row)
        return row

    async def update_action_by_source(
        self,
        session: AsyncSession,
        *,
        payload: PortalActionSourceUpdateRequest,
        user_id: int | None,
    ) -> PortalActionRead:
        source_module = self._normalize_source_module(payload.source_module)
        status = self._normalize_status(payload.status)
        if source_module == "problem_engine":
            instance, definition = await self._update_problem_instance_action_by_source(
                session,
                account_id=payload.account_id,
                source_id=payload.source_id,
                status=status,
                comment=payload.comment,
                status_reason=getattr(payload, "status_reason", None),
                assigned_to_user_id=getattr(payload, "assigned_to_user_id", None),
                deadline_at=getattr(payload, "deadline_at", None),
                review_status=getattr(payload, "review_status", None),
                event_type=getattr(payload, "event_type", None),
                user_id=user_id,
            )
            await session.commit()
            self._invalidate_actions_cache()
            return self._finalize_action(
                self._problem_instance_action(instance, definition=definition)
            )
        row = await self._find_unified_action_by_source(
            session,
            account_id=payload.account_id,
            source_module=source_module,
            source_id=payload.source_id,
        )
        old_shadow_status = row.status if row is not None else "new"
        if row is not None:
            self._validate_action_status_transition(
                old_status=old_shadow_status,
                new_status=status,
                event_type=getattr(payload, "event_type", None),
            )
        direct_source_status = self._direct_source_status_for_action_center_status(
            status
        )
        control_action = await self._maybe_update_control_action_by_source(
            session,
            source_module=source_module,
            source_id=payload.source_id,
            status=direct_source_status or "",
            comment=payload.comment,
            assigned_to_user_id=getattr(payload, "assigned_to_user_id", None),
            deadline_at=getattr(payload, "deadline_at", None),
            user_id=user_id,
        )
        checker_issue = await self._maybe_update_card_quality_action_by_source(
            session,
            account_id=payload.account_id,
            source_module=source_module,
            source_id=payload.source_id,
            status=direct_source_status or "",
            comment=payload.comment,
            postponed_until=getattr(payload, "deadline_at", None),
            event_type=getattr(payload, "event_type", None),
            user_id=user_id,
        )
        dq_issue = await self._maybe_update_data_quality_action_by_source(
            session,
            account_id=payload.account_id,
            source_module=source_module,
            source_id=payload.source_id,
            status=direct_source_status or "",
            comment=payload.comment,
            status_reason=getattr(payload, "status_reason", None),
            user_id=user_id,
        )
        cost_row = await self._maybe_update_cost_action_by_source(
            session,
            account_id=payload.account_id,
            source_module=source_module,
            source_id=payload.source_id,
            status=direct_source_status or "",
            comment=payload.comment,
            user_id=user_id,
        )
        reputation_shadow = await self._maybe_update_reputation_action_by_source(
            session,
            account_id=payload.account_id,
            source_module=source_module,
            source_id=payload.source_id,
            status=status,
            comment=payload.comment,
            user_id=user_id,
        )
        source_targets = [
            name
            for name, updated in (
                ("finance", control_action),
                ("checker", checker_issue),
                ("data_quality", dq_issue),
                ("costs", cost_row),
            )
            if updated is not None
        ]
        source_sync_state = (
            "source_updated"
            if source_targets
            else "shadow_updated"
            if reputation_shadow
            else "shadow_only"
        )
        source_sync_reason = (
            None
            if source_targets
            else (
                f"{source_module}_status_{status}_stored_as_action_center_shadow"
                if direct_source_status is None
                else f"{source_module}_source_not_found_or_not_directly_mutable"
            )
        )
        old_assigned = (
            getattr(row, "assigned_to_user_id", None) if row is not None else None
        )
        old_deadline = getattr(row, "deadline_at", None) if row is not None else None
        old_comment = getattr(row, "last_comment", None) if row is not None else None
        created_shadow_row = row is None
        if row is None:
            title = "Local action status"
            action_type = "MANUAL_REVIEW"
            if control_action is not None:
                control_read = self._control_action(control_action)
                title = control_read.title
                action_type = control_read.action_type or action_type
            elif checker_issue is not None:
                title = checker_issue.title
                action_type = "CARD_QUALITY_FIX"
            elif dq_issue is not None:
                title = dq_issue.message
                action_type = "DATA_FIX"
            elif cost_row is not None:
                title = "Проверить себестоимость"
                action_type = "COST_FIX"
            action = PortalActionRead(
                id=f"{source_module}:{payload.source_id}",
                source="shadow_source_update",
                source_module=source_module,
                source_id=payload.source_id,
                account_id=payload.account_id,
                action_type=action_type,
                title=title,
                status=status,
                nm_id=(
                    getattr(checker_issue, "nm_id", None)
                    or getattr(dq_issue, "nm_id", None)
                    or getattr(cost_row, "nm_id", None)
                ),
                sku_id=getattr(dq_issue, "sku_id", None)
                or getattr(cost_row, "sku_id", None),
                can_update_status=True,
                can_update=True,
                can_update_reason=source_sync_reason,
                source_sync_state=source_sync_state,  # type: ignore[arg-type]
                payload={
                    "source_sync_state": source_sync_state,
                    "source_update_targets": source_targets,
                    "can_update_reason": source_sync_reason,
                },
            )
            row = await self.upsert_synthetic_action(
                session,
                account_id=payload.account_id,
                action=action,
                status=status,
                comment=payload.comment,
                user_id=user_id,
            )
        else:
            row.status = status
            payload_json = dict(row.payload_json or {})
            payload_json["shadow_synthetic"] = True
            payload_json["marketplace_change"] = False
            payload_json["can_confirm"] = False
            payload_json["source_sync_state"] = source_sync_state
            payload_json["source_update_targets"] = source_targets
            if source_sync_reason:
                payload_json["can_update_reason"] = source_sync_reason
            row.payload_json = payload_json
        self._apply_unified_action_task_fields(
            row,
            status=status,
            comment=payload.comment,
            status_reason=getattr(payload, "status_reason", None),
            assigned_to_user_id=getattr(payload, "assigned_to_user_id", None),
            deadline_at=getattr(payload, "deadline_at", None),
            review_status=getattr(payload, "review_status", None),
            user_id=user_id,
        )
        if created_shadow_row or old_shadow_status != status:
            event_type = self._canonical_action_event_type(
                getattr(payload, "event_type", None),
                old_status=old_shadow_status,
                new_status=status,
            )
            self._append_unified_action_history_event(
                row,
                event_type="status_changed",
                old_value={
                    "status": old_shadow_status,
                    "initial_shadow_state": created_shadow_row,
                },
                new_value={"status": status},
                comment=payload.comment,
                user_id=user_id,
            )
            if event_type != "status_changed":
                self._append_unified_action_history_event(
                    row,
                    event_type=event_type,
                    old_value={
                        "status": old_shadow_status,
                        "initial_shadow_state": created_shadow_row,
                    },
                    new_value={"status": status},
                    comment=payload.comment,
                    user_id=user_id,
                )
        if (
            getattr(payload, "assigned_to_user_id", None) is not None
            and old_assigned != row.assigned_to_user_id
        ):
            self._append_unified_action_history_event(
                row,
                event_type="assigned",
                old_value={"assigned_to_user_id": old_assigned},
                new_value={"assigned_to_user_id": row.assigned_to_user_id},
                comment=payload.comment,
                user_id=user_id,
            )
            self._add_action_center_notification_event(
                session,
                account_id=payload.account_id,
                notification_type="assigned_to_user",
                message="Action Center task assigned to user.",
                source_module=row.source_module,
                source_id=row.source_id or payload.source_id,
                action_id=row.id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                assigned_to_user_id=row.assigned_to_user_id,
                payload={
                    "old_assigned_to_user_id": old_assigned,
                    "comment": payload.comment,
                },
                user_id=user_id,
            )
        if (
            getattr(payload, "deadline_at", None) is not None
            and old_deadline != row.deadline_at
        ):
            self._append_unified_action_history_event(
                row,
                event_type="deadline_changed",
                old_value={
                    "deadline_at": old_deadline.isoformat()
                    if old_deadline is not None
                    else None
                },
                new_value={
                    "deadline_at": row.deadline_at.isoformat()
                    if row.deadline_at is not None
                    else None
                },
                comment=payload.comment,
                user_id=user_id,
            )
            self._add_deadline_notification_if_needed(
                session,
                row=row,
                old_deadline=old_deadline,
                comment=payload.comment,
                user_id=user_id,
            )
        if payload.comment and payload.comment != old_comment:
            self._append_unified_action_history_event(
                row,
                event_type="comment_added",
                old_value={"comment": old_comment},
                new_value={"comment": payload.comment},
                comment=payload.comment,
                user_id=user_id,
            )
        primary_event_type = (
            self._canonical_action_event_type(
                getattr(payload, "event_type", None),
                old_status=old_shadow_status,
                new_status=status,
            )
            if created_shadow_row or old_shadow_status != status
            else "assigned"
            if getattr(payload, "assigned_to_user_id", None) is not None
            and old_assigned != row.assigned_to_user_id
            else "deadline_changed"
            if getattr(payload, "deadline_at", None) is not None
            and old_deadline != row.deadline_at
            else "comment_added"
            if payload.comment and payload.comment != old_comment
            else self._canonical_action_event_type(
                getattr(payload, "event_type", None),
                old_status=old_shadow_status,
                new_status=status,
            )
        )
        self._add_action_center_result_event(
            session,
            row=row,
            account_id=payload.account_id,
            event_type=primary_event_type,
            status=status,
            message="Action Center source update recorded.",
            payload={
                "source_module": source_module,
                "source_id": payload.source_id,
                "old_value": {
                    "status": old_shadow_status,
                    "assigned_to_user_id": old_assigned,
                    "deadline_at": old_deadline,
                    "comment": old_comment,
                },
                "new_value": {
                    "status": status,
                    "assigned_to_user_id": row.assigned_to_user_id,
                    "deadline_at": row.deadline_at,
                    "comment": payload.comment,
                },
                "source_sync_state": source_sync_state,
                "source_update_targets": source_targets,
                "can_update_reason": source_sync_reason,
            },
            user_id=user_id,
        )
        if reputation_shadow:
            row.payload_json = {
                **dict(row.payload_json or {}),
                **reputation_shadow,
                "shadow_synthetic": True,
                "source_sync_state": source_sync_state,
                "source_update_targets": source_targets,
                **(
                    {"can_update_reason": source_sync_reason}
                    if source_sync_reason
                    else {}
                ),
                "marketplace_change": False,
                "external_operation": False,
            }
        else:
            row.payload_json = {
                **dict(row.payload_json or {}),
                "source_sync_state": source_sync_state,
                "source_update_targets": source_targets,
                **(
                    {"can_update_reason": source_sync_reason}
                    if source_sync_reason
                    else {}
                ),
            }
        if status == "in_progress":
            await self.result_tracking.ensure_before_snapshot(
                session,
                account_id=payload.account_id,
                action_id=row.id,
                created_by=user_id,
            )
        if status == "done":
            await self.result_tracking.create_action_completed_event(
                session,
                account_id=payload.account_id,
                action_id=row.id,
                created_by=user_id,
            )
            self._add_grouping_review_result_event(
                session,
                account_id=payload.account_id,
                action_id=row.id,
                source_id=payload.source_id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                status=status,
                comment=payload.comment,
                created_by=user_id,
                payload={
                    **dict(row.payload_json or {}),
                    "source_module": row.source_module,
                },
            )
            self._add_stock_action_result_event(
                session,
                account_id=payload.account_id,
                action_id=row.id,
                source_id=payload.source_id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                status=status,
                comment=payload.comment,
                created_by=user_id,
                payload={
                    **dict(row.payload_json or {}),
                    "source_module": row.source_module,
                },
            )
            self._append_unified_action_history_event(
                row,
                event_type="result_measured",
                old_value={"status": old_shadow_status},
                new_value={"status": status, "saved_money_claimed": False},
                comment=payload.comment,
                user_id=user_id,
            )
        if (created_shadow_row or old_shadow_status != status) and status == "reopened":
            self._add_action_center_notification_event(
                session,
                account_id=payload.account_id,
                notification_type="issue_reopened",
                message="Action Center task reopened.",
                source_module=row.source_module,
                source_id=row.source_id or payload.source_id,
                action_id=row.id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                payload={
                    "old_status": old_shadow_status,
                    "new_status": status,
                    "comment": payload.comment,
                },
                user_id=user_id,
            )
        session.add(
            ResultEvent(
                account_id=payload.account_id,
                action_id=row.id,
                source_module="action_center",
                source_id=payload.source_id,
                external_id=payload.source_id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                event_type="local_action_status_updated",
                status=status,
                message="Local Action Center status updated. No external marketplace operation was performed.",
                payload_json={
                    "source_module": source_module,
                    "source_id": payload.source_id,
                    "old_status": old_shadow_status,
                    "status": status,
                    "comment": payload.comment,
                    "created_by": user_id,
                    "source_sync_state": source_sync_state,
                    "source_update_targets": source_targets,
                    "can_update_reason": source_sync_reason,
                    "external_operation": False,
                    "marketplace_change": False,
                    **reputation_shadow,
                },
            )
        )
        await session.commit()
        self._invalidate_actions_cache()
        return self._finalize_action(self._unified_action_row(row))

    async def _update_problem_instance_action_by_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_id: str,
        status: str,
        comment: str | None,
        status_reason: str | None,
        assigned_to_user_id: int | None,
        deadline_at: Any,
        review_status: str | None,
        event_type: str | None,
        user_id: int | None,
    ) -> tuple[ProblemInstance, ProblemDefinition | None]:
        instance_id = self._optional_int(str(source_id).split(":")[-1])
        if instance_id is None:
            raise HTTPException(
                status_code=404, detail="dynamic problem instance not found"
            )
        instance = await session.get(ProblemInstance, instance_id)
        if instance is None or int(instance.account_id) != int(account_id):
            raise HTTPException(
                status_code=404, detail="dynamic problem instance not found"
            )

        definition = await session.get(
            ProblemDefinition, instance.problem_definition_id
        )
        now = utcnow()
        old_status = str(instance.status or "new")
        old_dismiss_reason = instance.dismiss_reason
        old_assigned = self._problem_action_state_value(instance, "assigned_to_user_id")
        old_deadline = self._problem_action_state_value(instance, "deadline_at")
        old_review = self._problem_action_state_value(instance, "review_status")
        old_comment = self._problem_action_state_value(instance, "last_comment")

        old_status, status = self._validate_action_status_transition(
            old_status=old_status,
            new_status=status,
            event_type=event_type,
        )
        instance.status = status
        if status == "resolved":
            instance.resolved_at = instance.resolved_at or now
            instance.dismissed_at = None
            instance.dismiss_reason = None
        elif status == "done":
            instance.dismissed_at = None
            instance.dismiss_reason = None
        elif status in {"ignored", "dismissed"}:
            instance.dismissed_at = instance.dismissed_at or now
            instance.dismiss_reason = (
                status_reason or comment or instance.dismiss_reason
            )
        elif status in {
            "new",
            "acknowledged",
            "in_progress",
            "postponed",
            "blocked",
            "reopened",
        }:
            instance.resolved_at = None
            if old_status in {"ignored", "dismissed", "resolved", "done"}:
                instance.dismissed_at = None
                instance.dismiss_reason = None

        snapshot = dict(instance.calculation_snapshot_json or {})
        action_state = (
            dict(snapshot.get("action_center") or {})
            if isinstance(snapshot.get("action_center"), dict)
            else {}
        )
        if comment:
            action_state["last_comment"] = comment
        if assigned_to_user_id is not None:
            action_state["assigned_to_user_id"] = int(assigned_to_user_id)
        if deadline_at is not None:
            parsed_deadline = self._optional_datetime(deadline_at)
            action_state["deadline_at"] = (
                parsed_deadline.isoformat() if parsed_deadline is not None else None
            )
        action_state["review_status"] = self._normalize_review_status(
            review_status or self._review_status_for_action_status(status)
        )
        action_state["last_changed_at"] = now.isoformat()
        action_state["last_actor_user_id"] = user_id
        if status_reason or comment:
            action_state["status_reason"] = status_reason or comment
        if user_id is not None:
            action_state["last_changed_by_user_id"] = int(user_id)
        if old_status != status:
            action_state["last_status_changed_at"] = now.isoformat()
        if status in {"done", "resolved"}:
            action_state["closed_at"] = (instance.resolved_at or now).isoformat()
            action_state.pop("dismissed_at", None)
            action_state.pop("dismiss_reason", None)
        elif status in {"ignored", "dismissed"}:
            action_state["dismissed_at"] = (instance.dismissed_at or now).isoformat()
            if instance.dismiss_reason:
                action_state["dismiss_reason"] = instance.dismiss_reason
            action_state.pop("closed_at", None)
        else:
            action_state.pop("closed_at", None)
            if status != "ignored":
                action_state.pop("dismissed_at", None)
                action_state.pop("dismiss_reason", None)
        snapshot["action_center"] = action_state
        instance.calculation_snapshot_json = snapshot

        if old_status != status:
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="status_changed",
                old_value={"status": old_status},
                new_value={"status": status},
                comment=comment,
                user_id=user_id,
            )
            semantic_event = self._canonical_action_event_type(
                event_type, old_status=old_status, new_status=status
            )
            if semantic_event != "status_changed":
                self._add_problem_instance_history(
                    session,
                    instance=instance,
                    event_type=semantic_event,
                    old_value={"status": old_status},
                    new_value={"status": status},
                    comment=comment,
                    user_id=user_id,
                )
            if status == "reopened":
                self._add_action_center_notification_event(
                    session,
                    account_id=instance.account_id,
                    notification_type="issue_reopened",
                    message="Dynamic problem reopened.",
                    source_module="problem_engine",
                    source_id=str(instance.id),
                    problem_instance_id=instance.id,
                    problem_code=instance.problem_code,
                    nm_id=instance.nm_id,
                    vendor_code=instance.vendor_code,
                    payload={
                        "old_status": old_status,
                        "new_status": status,
                        "comment": comment,
                    },
                    user_id=user_id,
                )
        if status in {"ignored", "dismissed"} and (
            old_status not in {"ignored", "dismissed"}
            or comment
            or old_dismiss_reason != instance.dismiss_reason
        ):
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="dismissed",
                old_value={"status": old_status, "dismiss_reason": old_dismiss_reason},
                new_value={"status": status, "dismiss_reason": instance.dismiss_reason},
                comment=comment,
                user_id=user_id,
            )

        new_assigned = action_state.get("assigned_to_user_id")
        if old_assigned != new_assigned and new_assigned is not None:
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="assigned",
                old_value={"assigned_to_user_id": old_assigned},
                new_value={"assigned_to_user_id": new_assigned},
                comment=comment,
                user_id=user_id,
            )
            self._add_action_center_notification_event(
                session,
                account_id=instance.account_id,
                notification_type="assigned_to_user",
                message="Dynamic problem assigned to user.",
                source_module="problem_engine",
                source_id=str(instance.id),
                problem_instance_id=instance.id,
                problem_code=instance.problem_code,
                nm_id=instance.nm_id,
                vendor_code=instance.vendor_code,
                assigned_to_user_id=self._optional_int(new_assigned),
                payload={"old_assigned_to_user_id": old_assigned, "comment": comment},
                user_id=user_id,
            )
        new_deadline = action_state.get("deadline_at")
        if deadline_at is not None and old_deadline != new_deadline:
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="deadline_changed",
                old_value={"deadline_at": old_deadline},
                new_value={"deadline_at": new_deadline},
                comment=comment,
                user_id=user_id,
            )
            self._add_problem_deadline_notification_if_needed(
                session,
                instance=instance,
                old_deadline=old_deadline,
                new_deadline=new_deadline,
                comment=comment,
                user_id=user_id,
            )
        if comment and comment != old_comment:
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="comment_added",
                old_value={"comment": old_comment},
                new_value={"comment": comment},
                comment=comment,
                user_id=user_id,
            )
        if (
            self._canonical_action_event_type(
                event_type, old_status=old_status, new_status=status
            )
            == "recheck_requested"
        ):
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="recheck_requested",
                old_value={
                    "status": old_status,
                    "deadline_at": old_deadline,
                    "review_status": old_review,
                },
                new_value={
                    "status": status,
                    "deadline_at": action_state.get("deadline_at"),
                    "review_status": action_state.get("review_status"),
                },
                comment=comment,
                user_id=user_id,
            )

        if old_status != status:
            await self.result_tracking.create_problem_status_event(
                session,
                problem_instance_id=instance.id,
                old_status=old_status,
                new_status=status,
                comment=comment,
                created_by=user_id,
            )
        if old_status != status and status in {"done", "resolved"}:
            await self.result_tracking.create_problem_completed_event(
                session,
                problem_instance_id=instance.id,
                created_by=user_id,
                comment=comment,
            )
            self._add_problem_instance_history(
                session,
                instance=instance,
                event_type="result_measured",
                old_value={"status": old_status},
                new_value={"status": status, "saved_money_claimed": False},
                comment=comment,
                user_id=user_id,
            )
        if event_type == "recheck":
            await self.result_tracking.create_problem_recheck_event(
                session,
                problem_instance_id=instance.id,
                created_by=user_id,
                status=status,
                message=comment,
                payload={
                    "old_status": old_status,
                    "new_status": status,
                    "source": "action_center",
                },
            )

        await session.flush()
        return instance, definition if isinstance(
            definition, ProblemDefinition
        ) else None

    def _problem_action_state_value(self, instance: ProblemInstance, key: str) -> Any:
        snapshot = dict(instance.calculation_snapshot_json or {})
        action_state = snapshot.get("action_center")
        if not isinstance(action_state, dict):
            return None
        return action_state.get(key)

    def _add_problem_instance_history(
        self,
        session: AsyncSession,
        *,
        instance: ProblemInstance,
        event_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
        comment: str | None,
        user_id: int | None,
    ) -> None:
        session.add(
            ProblemInstanceHistory(
                problem_instance_id=instance.id,
                event_type=event_type,
                old_value_json=jsonable_encoder(old_value)
                if old_value is not None
                else None,
                new_value_json=jsonable_encoder(new_value)
                if new_value is not None
                else None,
                comment=comment,
                actor_user_id=user_id,
            )
        )

    async def _maybe_update_reputation_action_by_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_module: str,
        source_id: str,
        status: str,
        comment: str | None,
        user_id: int | None,
    ) -> dict[str, Any]:
        if source_module != "reputation":
            return {}
        try:
            return await self.reputation.update_action_center_shadow_status(
                session,
                account_id=account_id,
                source_id=source_id,
                status=status,
                comment=comment,
                user_id=user_id,
            )
        except Exception as exc:
            return {
                "reputation_shadow_update_failed": True,
                "reputation_shadow_update_error": str(exc),
                "external_operation": False,
                "marketplace_change": False,
            }

    async def _maybe_update_control_action_by_source(
        self,
        session: AsyncSession,
        *,
        source_module: str,
        source_id: str,
        status: str,
        comment: str | None,
        assigned_to_user_id: int | None,
        deadline_at: Any,
        user_id: int | None,
    ) -> Any | None:
        if source_module != "finance":
            return None
        if not status:
            return None
        action_id = self._optional_int(source_id)
        if action_id is None:
            return None
        try:
            updated = await self.control_tower.update_action(
                session,
                action_id=action_id,
                user_id=user_id,
                payload=ActionRecommendationUpdateRequest(
                    status=status,
                    assigned_to=assigned_to_user_id,
                    comment=comment,
                ),
            )
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise
        if deadline_at is not None:
            action = await session.get(ActionRecommendation, action_id)
            if action is not None:
                action.deadline_at = self._optional_datetime(deadline_at)
        return updated

    async def _maybe_update_card_quality_action_by_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_module: str,
        source_id: str,
        status: str,
        comment: str | None,
        postponed_until: Any,
        user_id: int | None,
        event_type: str | None = None,
    ) -> Any | None:
        if source_module != "checker":
            return None
        if not status:
            return None
        issue_id = self._optional_int(source_id)
        if issue_id is None:
            return None
        try:
            updated = await self.card_quality.update_issue_status(
                session,
                account_id=account_id,
                issue_id=issue_id,
                status=status,
                changed_by_user_id=user_id,
                reason=comment,
                postponed_until=self._optional_datetime(postponed_until),
            )
            if str(event_type or "").lower() == "recheck":
                session.add(
                    CardQualityIssueStatusHistory(
                        account_id=account_id,
                        issue_id=issue_id,
                        old_status=getattr(updated, "status", status),
                        new_status=getattr(updated, "status", status),
                        changed_by_user_id=user_id,
                        reason=comment or "recheck_requested_from_action_center",
                    )
                )
            return updated
        except ValueError as exc:
            if str(exc) == "issue_not_found":
                return None
            raise

    async def _maybe_update_data_quality_action_by_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_module: str,
        source_id: str,
        status: str,
        comment: str | None,
        status_reason: str | None = None,
        user_id: int | None,
    ) -> DataQualityIssue | None:
        if source_module != "data_quality":
            return None
        if not status:
            return None
        issue = await self._find_data_quality_issue_for_action(
            session, account_id=account_id, source_id=source_id
        )
        if issue is None:
            return None
        if status == "done":
            return await self.data_quality.resolve_issue_by_id(
                session, issue_id=int(issue.id), comment=comment
            )
        if status == "new":
            return await self.data_quality.reopen_issue_by_id(
                session, issue_id=int(issue.id), comment=comment
            )
        classification_status = {
            "in_progress": "real_issue",
            "blocked": "real_issue",
            "postponed": "expected_lag",
            "ignored": "ignored_with_reason",
        }.get(status, "real_issue")
        reason = (
            status_reason or comment or f"Action Center status changed to {status}."
        )
        return await self.data_quality.classify_issue_by_id(
            session,
            issue_id=int(issue.id),
            classification_status=classification_status,
            classification_reason=reason,
            financial_final_blocker_override=False if status == "ignored" else None,
            user_id=user_id,
            comment=comment,
        )

    async def _find_data_quality_issue_for_action(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_id: str,
    ) -> DataQualityIssue | None:
        issue_id = self._optional_int(source_id)
        if issue_id is not None:
            issue = await session.get(DataQualityIssue, issue_id)
            if issue is not None and int(issue.account_id or 0) == int(account_id):
                return issue
        result = await session.execute(
            select(DataQualityIssue)
            .where(
                DataQualityIssue.account_id == account_id,
                DataQualityIssue.code == str(source_id),
                DataQualityIssue.resolved_at.is_(None),
            )
            .order_by(DataQualityIssue.detected_at.desc(), DataQualityIssue.id.desc())
            .limit(1)
        )
        return next(iter(result.scalars()), None)

    async def _maybe_update_cost_action_by_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_module: str,
        source_id: str,
        status: str,
        comment: str | None,
        user_id: int | None,
    ) -> ManualCost | None:
        if source_module != "costs":
            return None
        if not status:
            return None
        cost = await self._find_manual_cost_for_action(
            session, account_id=account_id, source_id=source_id
        )
        if cost is None:
            return None
        note = f"Action Center status: {status}"
        if user_id is not None:
            note = f"{note}; user_id={user_id}"
        if comment:
            note = f"{note}; {comment}"
        cost.comment = note if not cost.comment else f"{cost.comment}\n{note}"
        if (
            status == "done"
            and cost.sku_id is not None
            and not cost.is_placeholder
            and not cost.is_ambiguous
        ):
            cost.is_business_trusted = True
            cost.cost_source = cost.cost_source or "action_center_reviewed_manual"
            cost.match_rule = cost.match_rule or "action_center_reviewed"
        if status in {"blocked", "postponed"} and cost.cost_source is None:
            cost.cost_source = "action_center_pending_review"
        await session.flush()
        return cost

    async def _find_manual_cost_for_action(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_id: str,
    ) -> ManualCost | None:
        cost_id = self._optional_int(source_id)
        if cost_id is not None:
            cost = await session.get(ManualCost, cost_id)
            if cost is not None and int(cost.account_id) == int(account_id):
                return cost
        result = await session.execute(
            select(ManualCost)
            .where(
                ManualCost.account_id == account_id,
                ManualCost.vendor_code == str(source_id),
            )
            .order_by(ManualCost.id.desc())
            .limit(1)
        )
        return next(iter(result.scalars()), None)

    def _add_grouping_review_result_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        source_id: str | None,
        nm_id: int | None,
        vendor_code: str | None,
        status: str,
        comment: str | None,
        created_by: int | None,
        payload: dict[str, Any],
    ) -> None:
        source_module = self._normalize_source_module(
            payload.get("source_module")
            or payload.get("source_identity", {}).get("source_module")
        )
        if source_module != "grouping_beta":
            return
        session.add(
            ResultEvent(
                account_id=account_id,
                action_id=action_id,
                source_module="grouping_beta",
                source_id=source_id,
                external_id=source_id,
                nm_id=nm_id,
                vendor_code=vendor_code,
                event_type="grouping_review_completed",
                status="done",
                message="Grouping Beta recommendation reviewed locally. No WB merge/apply operation was performed.",
                payload_json={
                    "status": status,
                    "comment": comment,
                    "created_by": created_by,
                    "external_operation": False,
                    "marketplace_change": False,
                    "auto_merge_enabled": False,
                    "candidate_group_id": payload.get("candidate_group_id"),
                    "nm_ids": payload.get("nm_ids") or [],
                    "risk_level": payload.get("risk_level"),
                    "risk_reasons": payload.get("risk_reasons") or [],
                    "review_needed": payload.get("review_needed"),
                },
            )
        )

    def _add_stock_action_result_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        source_id: str | None,
        nm_id: int | None,
        vendor_code: str | None,
        status: str,
        comment: str | None,
        created_by: int | None,
        payload: dict[str, Any],
    ) -> None:
        source_module = self._normalize_source_module(
            payload.get("source_module")
            or payload.get("source_identity", {}).get("source_module")
        )
        if source_module != "stockops":
            return
        session.add(
            ResultEvent(
                account_id=account_id,
                action_id=action_id,
                source_module="stockops",
                source_id=source_id,
                external_id=source_id,
                nm_id=nm_id,
                vendor_code=vendor_code,
                event_type="stock_action_done",
                status="done",
                message="StockOps recommendation marked done locally. No WB or warehouse operation was performed by Finance.",
                payload_json={
                    "status": status,
                    "comment": comment,
                    "created_by": created_by,
                    "external_operation": False,
                    "marketplace_change": False,
                    "run_id": payload.get("run_id"),
                    "run_type": payload.get("run_type"),
                    "sheet_id": payload.get("sheet_id"),
                    "quantity": payload.get("quantity"),
                    "write_status": "disabled",
                },
            )
        )

    async def products(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        search: str | None,
        card_quality_status: str | None = None,
        sort_by: str = "priority_score",
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> PortalProductsPage:
        account = await self._active_account(session, account_id=account_id)
        unavailable: list[str] = []
        if account is None:
            return PortalProductsPage(
                total=0,
                limit=limit,
                offset=offset,
                items=[],
                unavailable_sources=["account"],
            )

        account_id_value = int(account.id)
        actual_from, actual_to = self.money._normalize_window(date_from, date_to)
        fetch_limit = min(max(int(limit or 50) + int(offset or 0), int(limit or 50)), 200)
        use_products_cache = isinstance(session, AsyncSession)
        products_cache_key = self._products_cache_key(
            account_id=account_id_value,
            date_from=actual_from,
            date_to=actual_to,
            search=search,
            card_quality_status=card_quality_status,
            sort_by=sort_by,
            sort_dir=sort_dir,
            fetch_limit=fetch_limit,
        )
        if use_products_cache:
            cached_products = self._products_cache.get(products_cache_key)
            if cached_products is not None:
                return self._copy_products_page_slice(
                    cached_products, limit=limit, offset=offset
                )

        articles = await self._safe_source(
            "money_articles",
            unavailable,
            self.money.articles(
                session,
                account_id=account_id_value,
                date_from=actual_from,
                date_to=actual_to,
                search=search,
                status=None,
                trust_state=None,
                subject_name=None,
                brand=None,
                sort_by="priority_score",
                sort_dir="desc",
                limit=fetch_limit,
                offset=0,
            ),
        )
        if articles is None:
            return PortalProductsPage(
                total=0,
                limit=limit,
                offset=offset,
                items=[],
                unavailable_sources=unavailable,
        )
        rows = [self._product_row(item) for item in getattr(articles, "items", [])]
        rows = await self._enrich_product_rows_with_card_photos(
            session, account_id=account_id_value, rows=rows
        )
        rows = await self._enrich_product_rows_with_card_quality(
            session, account_id=account_id_value, rows=rows
        )
        rows = self._filter_sort_product_rows_by_card_quality(
            rows,
            status=card_quality_status,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        result = PortalProductsPage(
            total=len(rows)
            if card_quality_status
            else int(getattr(articles, "total", 0)),
            limit=fetch_limit,
            offset=0,
            summary=self._dump(getattr(articles, "summary", {})),
            items=rows,
            unavailable_sources=unavailable,
        )
        if use_products_cache:
            self._products_cache.set(products_cache_key, result)
        return self._copy_products_page_slice(result, limit=limit, offset=offset)

    async def _enrich_product_rows_with_card_photos(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        rows: list[PortalProductRead],
    ) -> list[PortalProductRead]:
        nm_ids = [int(row.nm_id) for row in rows if row.nm_id is not None]
        if not nm_ids:
            return rows
        cards = list(
            (
                await session.execute(
                    select(
                        WBProductCard.nm_id,
                        WBProductCard.photos,
                        WBProductCard.title,
                        WBProductCard.vendor_code,
                        WBProductCard.brand,
                        WBProductCard.subject_name,
                    ).where(
                        WBProductCard.account_id == account_id,
                        WBProductCard.nm_id.in_(nm_ids),
                    )
                )
            ).all()
        )
        card_by_nm: dict[
            int, tuple[Any, str | None, str | None, str | None, str | None]
        ] = {}
        for nm_id, photos, title, vendor_code, brand, subject_name in cards:
            if nm_id is not None:
                card_by_nm[int(nm_id)] = (
                    photos,
                    title,
                    vendor_code,
                    brand,
                    subject_name,
                )
        for row in rows:
            card = card_by_nm.get(int(row.nm_id))
            if card is None:
                continue
            photos, title, vendor_code, brand, subject_name = card
            photo_url = self._first_product_photo_url(photos)
            if photo_url and not row.photo:
                row.photo = photo_url
            if photo_url and not row.photo_url:
                row.photo_url = photo_url
            row.title = row.title or title
            row.name = row.name or title
            row.vendor_code = row.vendor_code or vendor_code
            row.article = row.article or vendor_code
            row.brand = row.brand or brand
            row.subject_name = row.subject_name or subject_name
            if isinstance(row.raw, dict):
                row.raw.setdefault("photos", photos)
                row.raw.setdefault("main_photo_url", photo_url)
        return rows

    def _first_product_photo_url(self, value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text if text.startswith(("http://", "https://")) else None
        if isinstance(value, list):
            for item in value:
                url = self._first_product_photo_url(item)
                if url:
                    return url
            return None
        if isinstance(value, dict):
            for key in (
                "big",
                "hq",
                "canonical_url",
                "url",
                "full",
                "photo",
                "src",
                "c516x688",
                "square",
                "c246x328",
                "tm",
            ):
                raw = value.get(key)
                if isinstance(raw, str) and raw.strip().startswith(
                    ("http://", "https://")
                ):
                    return raw.strip()
            for key in ("photos", "images", "media"):
                nested = value.get(key)
                if isinstance(nested, (list, dict)):
                    url = self._first_product_photo_url(nested)
                    if url:
                        return url
        return None

    async def _enrich_product_rows_with_card_quality(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        rows: list[PortalProductRead],
    ) -> list[PortalProductRead]:
        nm_ids = [int(row.nm_id) for row in rows if row.nm_id is not None]
        if not nm_ids:
            return rows
        latest_subq = (
            select(
                CardQualitySnapshot.nm_id.label("nm_id"),
                func.max(CardQualitySnapshot.analyzed_at).label("analyzed_at"),
            )
            .where(
                CardQualitySnapshot.account_id == account_id,
                CardQualitySnapshot.nm_id.in_(nm_ids),
            )
            .group_by(CardQualitySnapshot.nm_id)
            .subquery()
        )
        snapshots = list(
            (
                await session.execute(
                    select(CardQualitySnapshot)
                    .join(
                        latest_subq,
                        (CardQualitySnapshot.nm_id == latest_subq.c.nm_id)
                        & (
                            CardQualitySnapshot.analyzed_at == latest_subq.c.analyzed_at
                        ),
                    )
                    .where(
                        CardQualitySnapshot.account_id == account_id,
                        CardQualitySnapshot.nm_id.in_(nm_ids),
                    )
                )
            ).scalars()
        )
        snapshot_by_nm = {int(snapshot.nm_id): snapshot for snapshot in snapshots}
        issue_counts = {
            int(nm_id): int(count or 0)
            for nm_id, count in (
                await session.execute(
                    select(CardQualityIssue.nm_id, func.count(CardQualityIssue.id))
                    .where(
                        CardQualityIssue.account_id == account_id,
                        CardQualityIssue.nm_id.in_(nm_ids),
                        CardQualityIssue.status.in_(
                            ("new", "in_progress", "postponed")
                        ),
                        CardQualityIssue.resolved_at.is_(None),
                        CardQualityIssue.severity != "info",
                    )
                    .group_by(CardQualityIssue.nm_id)
                )
            ).all()
        }
        for row in rows:
            snapshot = snapshot_by_nm.get(int(row.nm_id))
            if snapshot is None:
                row.card_quality_state = "not_analyzed"
                row.card_quality_issue_count = 0
                continue
            row.card_quality_state = (
                "ok"
                if snapshot.status == "clean"
                else str(snapshot.status or "not_analyzed")
            )
            row.card_quality_score = snapshot.score
            row.card_quality_issue_count = issue_counts.get(int(row.nm_id), 0)
            row.card_quality_photo_count = snapshot.photos_count
            row.card_quality_analyzed_at = snapshot.analyzed_at
        return rows

    def _filter_sort_product_rows_by_card_quality(
        self,
        rows: list[PortalProductRead],
        *,
        status: str | None,
        sort_by: str,
        sort_dir: str,
    ) -> list[PortalProductRead]:
        normalized_status = str(status or "").strip().lower()
        filtered = [
            row
            for row in rows
            if not normalized_status
            or str(row.card_quality_state or "").lower() == normalized_status
        ]
        reverse = sort_dir != "asc"
        if sort_by == "quality_score":
            if reverse:
                filtered.sort(
                    key=lambda row: (
                        row.card_quality_score
                        if row.card_quality_score is not None
                        else -1
                    ),
                    reverse=True,
                )
            else:
                filtered.sort(
                    key=lambda row: (
                        row.card_quality_score
                        if row.card_quality_score is not None
                        else 101
                    )
                )
        elif sort_by == "quality_issues":
            filtered.sort(key=lambda row: row.card_quality_issue_count, reverse=reverse)
        elif sort_by == "revenue":
            filtered.sort(
                key=lambda row: row.revenue if row.revenue is not None else 0,
                reverse=reverse,
            )
        elif sort_by == "profit":
            filtered.sort(
                key=lambda row: row.profit if row.profit is not None else 0,
                reverse=reverse,
            )
        return filtered

    async def _fast_product_money_detail(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> Any:
        page_limit = 200
        for offset in range(0, 1000, page_limit):
            try:
                page = await self.money.articles(
                    session,
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                    search=None,
                    status=None,
                    trust_state=None,
                    subject_name=None,
                    brand=None,
                    sort_by="priority_score",
                    sort_dir="desc",
                    limit=page_limit,
                    offset=offset,
                )
            except Exception:
                break
            for item in getattr(page, "items", []) or []:
                if int(getattr(item, "nm_id", 0) or 0) != int(nm_id):
                    continue
                dumped = self._dump(item)
                summary = self._dump(getattr(page, "summary", {}))
                next_action = getattr(item, "next_action", None)
                return SimpleNamespace(
                    **dumped,
                    actions=[],
                    next_actions=[next_action] if next_action is not None else [],
                    issues=[],
                    problems=[],
                    operations={},
                    funnel={},
                    price_safety=None,
                    price=None,
                    cost_coverage=summary.get("cost_coverage")
                    or dumped.get("cost_coverage")
                    or {},
                )
            if offset + page_limit >= int(getattr(page, "total", 0) or 0):
                break
        detail_service = (
            self.money if isinstance(session, AsyncSession) else self.money.money
        )
        return await detail_service.article_detail(
            session,
            account_id=account_id,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
            include_audit=False,
        )

    async def product_360(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        nm_id: int,
        date_from: date | None,
        date_to: date | None,
        history_limit: int = 10,
        actions_limit: int = 10,
        claims_limit: int = 10,
    ) -> PortalProduct360Read:
        safe_history_limit = min(max(int(history_limit or 10), 1), 50)
        safe_actions_limit = min(max(int(actions_limit or 10), 1), 50)
        safe_claims_limit = min(max(int(claims_limit or 10), 1), 50)
        account = await self._active_account(session, account_id=account_id)
        unavailable: list[str] = []
        if account is None:
            return PortalProduct360Read(nm_id=nm_id, unavailable_sources=["account"])
        account_id_value = int(account.id)
        dynamic_enabled = self._dynamic_problem_engine_enabled(account_id_value)
        show_legacy_problem_cards = self._show_legacy_problem_cards()
        actual_from, actual_to = self.money._normalize_window(date_from, date_to)
        use_product360_cache = isinstance(session, AsyncSession)
        product360_cache_key = self._product360_cache_key(
            account_id=account_id_value,
            nm_id=nm_id,
            date_from=actual_from,
            date_to=actual_to,
            history_limit=safe_history_limit,
            actions_limit=safe_actions_limit,
            claims_limit=safe_claims_limit,
            dynamic_enabled=dynamic_enabled,
            show_legacy_problem_cards=show_legacy_problem_cards,
        )
        if use_product360_cache:
            cached = self._product360_cache.get(product360_cache_key)
            if cached is not None:
                return cached

        detail = await self._safe_source(
            "money_article_detail",
            unavailable,
            self._fast_product_money_detail(
                session,
                account_id=account_id_value,
                nm_id=nm_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
        )
        if detail is None:
            return PortalProduct360Read(nm_id=nm_id, unavailable_sources=unavailable)

        dumped = self._dump(detail)
        audit = (
            await self._safe_source(
                "article_audit",
                unavailable,
                self.money.money.dashboard.article_audit(
                    session,
                    account_id=account_id_value,
                    nm_id=nm_id,
                    date_from=actual_from,
                    date_to=actual_to,
                    issues_limit=safe_history_limit,
                    issues_offset=0,
                ),
            )
            if safe_history_limit > 20
            else None
        )
        if audit is not None:
            dumped = self._enrich_product_detail_with_audit(dumped, self._dump(audit))
        dq_page = await self._safe_source(
            "product_data_quality",
            unavailable,
            self.data_quality.list_issues(
                session,
                account_id=account_id_value,
                only_open=True,
                nm_id=nm_id,
                sort_by="detected_at",
                sort_dir="desc",
                limit=safe_history_limit,
                offset=0,
            ),
        )
        product_identifiers = self._product_cost_identifiers(
            dumped, fallback_nm_id=nm_id
        )
        product_cost_rows = await self._safe_source(
            "product_unresolved_costs",
            unavailable,
            self.manual_costs.list_unresolved_costs_for_product(
                session,
                account_id=account_id_value,
                **product_identifiers,
                limit=safe_claims_limit,
            ),
        )
        dq_items = (
            [self._dump(item) for item in getattr(dq_page, "items", [])]
            if dq_page is not None
            else []
        )
        checker_unavailable: list[str] = []
        grouping_unavailable: list[str] = []
        checker_quality_task = self._safe_source(
            "card_quality",
            checker_unavailable,
            self._with_optional_timeout(
                "checker_quality",
                self.product_quality(session, account_id=account_id_value, nm_id=nm_id),
                max_seconds=2.0,
            ),
        )
        grouping_task = self._safe_source(
            "grouping",
            grouping_unavailable,
            self._with_optional_timeout(
                "grouping",
                self.product_grouping(
                    session, account_id=account_id_value, nm_id=nm_id
                ),
                max_seconds=1.0,
            ),
        )
        reputation_task = self._reputation_product_block(
            session,
            account=account,
            nm_id=nm_id,
            detail=dumped,
            max_seconds=1.0,
        )
        claims_task = self._optional_product_module_block(
            source="claims",
            adapter=self.claims_adapter,
            account_id=account_id_value,
            nm_id=nm_id,
            detail=dumped,
            max_seconds=1.0,
        )
        stockops_task = self._with_optional_timeout(
            "stockops",
            self.stock_control.product_stock_insights(
                session,
                account_id=account_id_value,
                nm_id=nm_id,
                limit=safe_actions_limit,
            ),
            max_seconds=1.0,
        )
        photo_studio_task = self._safe_source(
            "photo",
            unavailable,
            self._with_optional_timeout(
                "photo",
                self.photo_studio.status(session, account_id=account_id_value),
                max_seconds=1.0,
            ),
        )
        (
            checker_quality,
            grouping,
            reputation,
            claims,
            stockops_insights,
            photo_status,
        ) = await asyncio.gather(
            checker_quality_task,
            grouping_task,
            reputation_task,
            claims_task,
            stockops_task,
            photo_studio_task,
            return_exceptions=True,
        )
        account = await self._recover_product360_session(
            session,
            account_id=account_id_value,
            unavailable=unavailable,
        )
        if isinstance(stockops_insights, Exception):
            stockops_insights = PortalStockOpsInsightsRead(
                status="unavailable",
                account_id=account_id_value,
                nm_id=nm_id,
                message="stockops service is unavailable",
                unavailable_sources=["stockops"],
            )
        unavailable.extend(checker_unavailable)
        unavailable.extend(grouping_unavailable)
        if checker_quality is None:
            checker_quality = PortalProductQualityRead(
                status="unavailable", nm_id=nm_id, message="card quality is unavailable"
            )
        if (
            checker_quality.status == "unavailable"
            and "checker_quality" not in unavailable
        ):
            unavailable.append("checker_quality")
        if grouping is None:
            grouping = PortalProductGroupingRead(
                status="unavailable",
                nm_id=nm_id,
                message="grouping beta is unavailable",
            )
        if grouping.status == "unavailable":
            unavailable.append("grouping")
        use_lightweight_product_doctor = dynamic_enabled and isinstance(
            session, AsyncSession
        )
        doctor = None
        if not use_lightweight_product_doctor:
            doctor = await self._safe_source(
                "profit_doctor",
                unavailable,
                self.profit_doctor.diagnose(
                    session,
                    account_id=account_id_value,
                    date_from=actual_from,
                    date_to=actual_to,
                    nm_id=nm_id,
                    limit=safe_actions_limit,
                ),
            )
        claims = await self._claims_block_with_local_cases(
            session,
            account_id=account_id_value,
            nm_id=nm_id,
            block=claims,
            unavailable=unavailable,
        )
        if reputation.status in {"not_configured", "unavailable"}:
            unavailable.append("reputation")
        if claims.status in {"not_configured", "unavailable"}:
            unavailable.append("claims")
        if stockops_insights.status == "unavailable":
            unavailable.append("stockops")
        if isinstance(photo_status, Exception) or photo_status is None:
            photo_status = None
            unavailable.append("photo")
        events_page = await self._safe_source(
            "experiment_events",
            unavailable,
            self.experiments.list_product_events(
                session,
                account_id=account_id_value,
                nm_id=nm_id,
                limit=safe_history_limit,
                offset=0,
            ),
        )
        results_page = await self._safe_source(
            "result_events",
            unavailable,
            self.result_tracking.list_results(
                session,
                account_id=account_id_value,
                nm_id=nm_id,
                limit=safe_history_limit,
                offset=0,
            ),
        )
        product_costs = (
            [
                self._dump_attrs(
                    item,
                    [
                        "id",
                        "account_id",
                        "sku_id",
                        "vendor_code",
                        "nm_id",
                        "barcode",
                        "tech_size",
                        "unit_cost",
                        "cost_price",
                        "seller_other_expense",
                        "is_ambiguous",
                        "is_placeholder",
                        "is_business_trusted",
                        "is_supplier_confirmed",
                        "cost_source",
                        "supplier",
                        "comment",
                    ],
                )
                for item in product_cost_rows or []
            ]
            if product_cost_rows is not None
            else []
        )
        detail_actions = [
            self._money_action(item)
            for item in getattr(detail, "actions", [])
            + getattr(detail, "next_actions", [])
        ]
        detail_actions.extend(self._dq_actions(dq_items))
        detail_actions.extend(self._cost_actions(product_costs))
        dynamic_problem_actions = (
            await self._safe_source(
                "dynamic_product_problems",
                unavailable,
                self._problem_instance_actions(
                    session,
                    account_id=account_id_value,
                    nm_id=nm_id,
                    limit=safe_actions_limit,
                    include_resolved=True,
                    include_finance_windows=False,
                ),
            )
            if dynamic_enabled
            else []
        )
        detail_actions.extend(dynamic_problem_actions or [])
        if doctor is None and use_lightweight_product_doctor:
            doctor = self._lightweight_product_doctor(
                account_id=account_id_value,
                nm_id=nm_id,
                date_from=actual_from,
                date_to=actual_to,
                detail=dumped,
                actions=dynamic_problem_actions or [],
                unavailable_sources=unavailable,
            )
        detail_actions.extend(
            self._checker_actions_from_quality(
                account_id=account_id_value, quality=checker_quality
            )
        )
        reputation_actions, reputation_unavailable = await self._reputation_actions(
            session,
            account=account,
            limit=safe_actions_limit,
            unavailable=unavailable,
            max_seconds=1.0,
        )
        if reputation_unavailable:
            unavailable.append(reputation_unavailable)
        detail_actions.extend(
            [action for action in reputation_actions if action.nm_id == nm_id]
        )
        claims_action_method = getattr(self.claims_adapter, "claims_actions", None)
        claims_actions, claims_unavailable = (
            await self._safe_optional_actions(
                "claims",
                unavailable,
                self._with_optional_timeout(
                    "claims",
                    claims_action_method(account, limit=safe_claims_limit),
                    max_seconds=1.0,
                ),
            )
            if claims_action_method is not None
            else ([], None)
        )
        if claims_unavailable:
            unavailable.append(claims_unavailable)
        detail_actions.extend(
            [action for action in claims_actions if action.nm_id == nm_id]
        )
        stockops_actions, stockops_unavailable = await self._safe_optional_actions(
            "stockops",
            unavailable,
            self._with_optional_timeout(
                "stockops",
                self.stock_control.action_candidates(
                    session,
                    account_id=account_id_value,
                    nm_id=nm_id,
                    limit=safe_actions_limit,
                ),
                max_seconds=1.0,
            ),
        )
        if stockops_unavailable:
            unavailable.append(stockops_unavailable)
        detail_actions.extend(stockops_actions)
        account = await self._recover_product360_session(
            session,
            account_id=account_id_value,
            unavailable=unavailable,
        )
        experiment_actions = await self._safe_source(
            "experiments",
            unavailable,
            self.experiments.action_candidates(
                session,
                account_id=account_id_value,
                nm_id=nm_id,
                limit=safe_actions_limit,
            ),
        )
        detail_actions.extend(experiment_actions or [])
        detail_actions.extend(self._doctor_action_rows(doctor))
        detail_actions = self._prefer_dynamic_problem_actions(
            detail_actions,
            show_legacy_problem_cards=show_legacy_problem_cards,
        )
        module_health = await self._module_health(account=account)
        module_statuses = self._module_status_map(module_health)
        detail_actions = [
            self._finalize_action(item, module_statuses=module_statuses)
            for item in self._dedupe_actions(detail_actions)
        ]
        detail_actions.sort(key=self._action_sort_key)
        next_best_action = self._product360_next_best_action(
            detail_actions,
            nm_id=nm_id,
            module_statuses=module_statuses,
        )
        business_issues_block = self._business_issues_block(
            detail_actions,
            unavailable_sources=unavailable,
            allow_legacy_fallback=show_legacy_problem_cards
            and (not dynamic_enabled or "dynamic_product_problems" in unavailable),
        )
        stock_data = dumped.get("stock")
        stock_block = self._stock_detail_block(stock_data, stockops_insights)
        ads_data = dumped.get("ads")
        issues = dq_items or list(dumped.get("issues") or dumped.get("problems") or [])
        history_data = {
            **self._history_detail_block(dumped),
            "events": [event.model_dump(mode="json") for event in events_page.items]
            if events_page is not None
            else [],
            "result_events": [
                event.model_dump(mode="json") for event in results_page.items
            ]
            if results_page is not None
            else [],
            "result_summary": getattr(results_page, "summary", {})
            if results_page is not None
            else {},
        }
        reputation = self._reputation_block_with_history(
            reputation, history_data.get("result_events") or []
        )
        experiments_block_data = await self._safe_source(
            "experiments",
            unavailable,
            self.experiments.product_block(
                session, account_id=account_id_value, nm_id=nm_id, limit=5
            ),
        )
        photo_ab_block_data = await self._safe_source(
            "ab_tests",
            unavailable,
            self.ab_photo_tests.product_block(
                session, account_id=account_id_value, nm_id=nm_id, limit=5
            ),
        )
        experiments_block_data = self._merge_product_experiment_blocks(
            experiments_block_data,
            photo_ab_block_data,
        )
        quality_block = PortalDataBlock(
            status=checker_quality.status,
            data=checker_quality.model_dump(mode="json"),
            message=checker_quality.message,
        )
        grouping_block = PortalDataBlock(
            status=grouping.status,
            data=grouping.model_dump(mode="json"),
            message=grouping.message,
        )
        photo_block = PortalDataBlock(
            status=getattr(photo_status, "status", "unavailable")
            if photo_status is not None
            else "unavailable",
            data=photo_status.model_dump(mode="json")
            if photo_status is not None
            else {},
            message=None if photo_status is not None else "Photo Studio is unavailable",
        )
        experiments_block = PortalDataBlock(
            status=(experiments_block_data or {}).get("status", "unavailable"),
            data=experiments_block_data or {},
            message=None
            if experiments_block_data is not None
            else "Experiments are unavailable",
        )
        problem_instances = self._product360_problem_instances(
            detail_actions, history_data=history_data
        )
        grouped_problems = self._product360_grouped_problems(
            detail_actions, history_data=history_data
        )
        checker_summary = self._product360_checker_summary(checker_quality)
        data_blockers_summary = self._product360_data_blockers_summary(
            grouped_problems, issues, nm_id=nm_id
        )
        product_identity = self._product360_product_identity(
            nm_id=nm_id,
            detail=dumped,
            stock_block=stock_block,
            pricing_data=dumped.get("price_safety") or dumped.get("price"),
        )
        account = await self._recover_product360_session(
            session,
            account_id=account_id_value,
            unavailable=unavailable,
        )
        product_identity.update(
            await self._product360_card_content(
                session,
                account_id=account_id_value,
                nm_id=nm_id,
            )
        )
        result_preview = self._product360_result_preview(
            problem_instances=problem_instances,
            result_history=history_data,
        )
        health_summary = self._product360_health_summary(
            business_issues=business_issues_block,
            grouped_problems=grouped_problems,
            checker_summary=checker_summary,
            data_blockers=data_blockers_summary,
            product_identity=product_identity,
            next_best_action=next_best_action,
        )
        result = PortalProduct360Read(
            nm_id=nm_id,
            product_identity=product_identity,
            health_summary=health_summary,
            problem_instances=problem_instances,
            grouped_problems=grouped_problems,
            result_preview=result_preview,
            checker_summary=checker_summary,
            data_blockers=data_blockers_summary,
            overview_diagnosis=self._product_diagnosis_block(doctor),
            identity=self._block(dumped.get("identity"), unavailable="identity"),
            money=self._block(self._money_detail_block(dumped), unavailable="money"),
            costs=self._block(
                self._costs_detail_block(dumped, product_costs), unavailable="costs"
            ),
            ads=self._block(ads_data, unavailable="ads"),
            stock=stock_block,
            pricing=self._block(
                dumped.get("price_safety") or dumped.get("price"), unavailable="pricing"
            ),
            data_quality=self._block(
                {
                    "trust": dumped.get("trust")
                    or (dumped.get("meta") or {}).get("data_trust"),
                    "issues": issues,
                    "problems": list(dumped.get("problems") or []),
                },
                unavailable="data_quality",
            ),
            quality=quality_block,
            card_quality=quality_block,
            reputation=reputation,
            claims=claims,
            photo_studio=photo_block,
            experiments=experiments_block,
            grouping=grouping_block,
            grouping_beta=grouping_block,
            business_issues=business_issues_block,
            actions=detail_actions,
            history=self._block(history_data, unavailable="history"),
            result_history=self._block(history_data, unavailable="history"),
            next_best_action=next_best_action,
            module_health=module_health,
            stock_summary=stock_block.data,
            ads_summary=ads_data,
            data_issues=issues,
            finance={
                "trust": dumped.get("trust"),
                "reconciliation": dumped.get("reconciliation"),
                "cost_coverage": dumped.get("cost_coverage"),
                "finality": dumped.get("finality"),
            },
            raw={
                **dumped,
                "grouping": grouping.model_dump(mode="json"),
                "stockops": stockops_insights.model_dump(mode="json"),
                "experiments": experiments_block_data or {},
            },
            unavailable_sources=self._dedupe_strings(unavailable),
        )
        if use_product360_cache:
            self._product360_cache.set(product360_cache_key, result)
        return result

    async def product_quality(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        nm_id: int,
    ) -> PortalProductQualityRead:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return PortalProductQualityRead(
                status="unavailable", nm_id=nm_id, message="account is not available"
            )
        try:
            local_quality = await self.card_quality.product_quality(
                session, account_id=account.id, nm_id=nm_id
            )
            if local_quality.status not in {
                "unavailable",
                "not_configured",
                "empty",
                "not_analyzed",
            }:
                return local_quality
        except Exception:
            local_quality = None
        try:
            return await self.checker.product_quality(account, nm_id=nm_id)
        except Exception:
            return PortalProductQualityRead(
                status="unavailable", nm_id=nm_id, message="card quality is unavailable"
            )

    async def create_experiment_event(
        self,
        session: AsyncSession,
        *,
        payload: PortalExperimentEventCreate,
        created_by: int | None,
    ) -> PortalExperimentEventRead:
        event = await self.experiments.create_event(
            session, payload=payload, created_by=created_by
        )
        await session.commit()
        self._invalidate_actions_cache()
        return event

    def experiments_status(self) -> PortalExperimentsStatusRead:
        return self.experiments.status()

    def _merge_product_experiment_blocks(
        self,
        general: dict[str, Any] | None,
        photo_ab: dict[str, Any] | None,
    ) -> dict[str, Any]:
        general_data = general if isinstance(general, dict) else {}
        photo_data = photo_ab if isinstance(photo_ab, dict) else {}
        general_items = list(
            general_data.get("items")
            or general_data.get("experiments")
            or general_data.get("active_experiments")
            or []
        )
        photo_items = list(photo_data.get("items") or [])
        items = [
            *[
                {**item, "source": item.get("source") or "experiments"}
                for item in general_items
                if isinstance(item, dict)
            ],
            *[
                {**item, "source": item.get("source") or "photo_ab_tests"}
                for item in photo_items
                if isinstance(item, dict)
            ],
        ]
        photo_summary = (
            photo_data.get("summary")
            if isinstance(photo_data.get("summary"), dict)
            else {}
        )
        active_general = list(general_data.get("active_experiments") or [])
        latest_results = list(general_data.get("latest_results") or [])
        latest_result = photo_data.get("latest_result") or general_data.get(
            "latest_result"
        )
        if latest_result is None and latest_results:
            latest_result = latest_results[0]
        active_count = int(photo_summary.get("active_count") or 0) + len(active_general)
        planned_count = int(photo_summary.get("planned_count") or 0) + sum(
            1
            for item in general_items
            if isinstance(item, dict)
            and str(item.get("status") or "").lower() in {"planned", "draft"}
        )
        finished_count = int(photo_summary.get("finished_count") or 0) + len(
            latest_results
        )
        failed_count = int(photo_summary.get("failed_count") or 0)
        status = "empty"
        if active_count:
            status = "running"
        elif failed_count:
            status = "warning"
        elif items or latest_result:
            status = "ok"
        return {
            "status": status,
            "items": items,
            "running": [
                item
                for item in items
                if isinstance(item, dict)
                and str(item.get("status") or "").lower()
                in {
                    "created",
                    "running",
                    "planned",
                    "baseline_collecting",
                    "ready_for_change",
                    "change_recorded",
                    "post_collecting",
                    "ready_for_evaluation",
                }
            ],
            "active_experiments": active_general,
            "latest_results": latest_results,
            "latest_result": latest_result,
            "recommended_experiment": general_data.get("recommended_experiment"),
            "warnings": sorted(
                set(
                    (general_data.get("warnings") or [])
                    + (photo_data.get("warnings") or [])
                )
            ),
            "last_evaluated_at": photo_data.get("last_evaluated_at")
            or general_data.get("last_evaluated_at"),
            "next_evaluation_at": photo_data.get("next_evaluation_at")
            or general_data.get("next_evaluation_at"),
            "summary": {
                "active_count": active_count,
                "running_count": int(photo_summary.get("running_count") or 0),
                "planned_count": planned_count,
                "pending_count": planned_count,
                "finished_count": finished_count,
                "completed_count": finished_count,
                "failed_count": failed_count,
                "total_count": len(items),
            },
            "sources": {
                "general_experiments": general_data,
                "photo_ab_tests": photo_data,
            },
        }

    async def experiment_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> PortalExperimentSettingsRead:
        return await self.experiments.settings(session, account_id=account_id)

    async def update_experiment_settings(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: PortalExperimentSettingsUpdate,
    ) -> PortalExperimentSettingsRead:
        settings = await self.experiments.update_settings(
            session, account_id=account_id, payload=payload
        )
        await session.commit()
        return settings

    async def create_experiment(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: PortalExperimentCreate,
        created_by: int | None,
    ) -> PortalExperimentRead:
        experiment = await self.experiments.create_experiment(
            session, account_id=account_id, payload=payload, created_by=created_by
        )
        await session.commit()
        self._invalidate_actions_cache()
        return experiment

    async def create_photo_experiment(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        project_id: int,
        version_id: int,
        payload: PhotoExperimentCreateRequest,
        created_by: int | None,
    ) -> PortalExperimentRead:
        project = await session.get(PhotoProject, project_id)
        if project is None or project.account_id != account_id:
            raise HTTPException(status_code=404, detail="photo_project_not_found")
        version = await session.get(PhotoVersion, version_id)
        if (
            version is None
            or version.account_id != account_id
            or version.project_id != project_id
        ):
            raise HTTPException(status_code=404, detail="photo_version_not_found")
        if version.status != "approved" or project.approved_version_id != version.id:
            raise HTTPException(status_code=400, detail="photo_version_not_approved")
        source_key = f"photo_project:{project.id}:version:{version.id}"
        existing = (
            await session.execute(
                select(Experiment).where(
                    Experiment.account_id == account_id,
                    Experiment.source_module == "photo",
                    Experiment.source_action_key == source_key,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return await self.experiments.get_experiment(
                session, account_id=account_id, experiment_id=existing.id
            )  # type: ignore[return-value]
        experiment = await self.experiments.create_experiment(
            session,
            account_id=account_id,
            payload=PortalExperimentCreate(
                account_id=account_id,
                nm_id=project.nm_id,
                sku_id=project.sku_id,
                name=f"Photo experiment for nm_id {project.nm_id}",
                description="Created from approved local Photo Studio version. WB apply is not performed by Finance.",
                experiment_type="before_after",
                intervention_type="photo",
                hypothesis=payload.hypothesis
                or "Approved photo version may improve product conversion; this must be evaluated as observed before/after only.",
                primary_metric=payload.primary_metric,
                secondary_metrics=payload.secondary_metrics,
                guardrail_metrics=payload.guardrail_metrics,
                baseline_days=payload.baseline_days,
                post_days=payload.post_days,
                evaluation_delay_days=payload.evaluation_delay_days,
                source_module="photo",
                source_action_key=source_key,
                source_project_id=str(project.id),
                is_test=payload.is_test,
            ),
            created_by=created_by,
        )
        session.add(
            ResultEvent(
                account_id=account_id,
                source_module="experiments",
                source_id=str(experiment.id),
                external_id=source_key,
                nm_id=project.nm_id,
                event_type="experiment_created_from_photo",
                status="new",
                external_status="draft",
                message="Черновик эксперимента создан из одобренной версии Фотостудии. Применение в WB остаётся ручным и отключено.",
                payload_json={
                    "experiment_id": experiment.id,
                    "project_id": project.id,
                    "version_id": version.id,
                    "asset_id": version.asset_id,
                    "marketplace_apply": "disabled",
                    "causality_note": "Оценка до/после показывает наблюдаемую связь, но не доказывает причинность.",
                },
            )
        )
        await session.commit()
        self._invalidate_actions_cache()
        return experiment

    async def list_experiments(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        status: str | None,
        intervention_type: str | None,
        nm_id: int | None,
        include_test: bool,
        limit: int,
        offset: int,
    ) -> PortalExperimentsPage:
        return await self.experiments.list_experiments(
            session,
            account_id=account_id,
            status=status,
            intervention_type=intervention_type,
            nm_id=nm_id,
            include_test=include_test,
            limit=limit,
            offset=offset,
        )

    async def get_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentRead | None:
        return await self.experiments.get_experiment(
            session, account_id=account_id, experiment_id=experiment_id
        )

    async def update_experiment(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
        payload: PortalExperimentUpdate,
    ) -> PortalExperimentRead | None:
        experiment = await self.experiments.update_experiment(
            session, account_id=account_id, experiment_id=experiment_id, payload=payload
        )
        if experiment is not None:
            await session.commit()
            self._invalidate_actions_cache()
        return experiment

    async def start_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentRead | None:
        experiment = await self.experiments.start_experiment(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if experiment is not None:
            await session.commit()
            self._invalidate_actions_cache()
        return experiment

    async def record_experiment_intervention(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
        payload: PortalExperimentInterventionCreate,
        user_id: int | None,
    ) -> PortalExperimentInterventionRead | None:
        intervention = await self.experiments.record_intervention(
            session,
            account_id=account_id,
            experiment_id=experiment_id,
            payload=payload,
            user_id=user_id,
        )
        if intervention is not None:
            await session.commit()
            self._invalidate_actions_cache()
        return intervention

    async def cancel_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentRead | None:
        experiment = await self.experiments.cancel_experiment(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if experiment is not None:
            await session.commit()
            self._invalidate_actions_cache()
        return experiment

    async def evaluate_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentEvaluationRead | None:
        evaluation = await self.experiments.evaluate_experiment(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if evaluation is not None:
            await session.commit()
            self._invalidate_actions_cache()
        return evaluation

    async def latest_experiment_evaluation(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
    ) -> PortalExperimentEvaluationRead | None:
        return await self.experiments.latest_evaluation(
            session, account_id=account_id, experiment_id=experiment_id
        )

    async def experiment_metrics(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
        limit: int,
        offset: int,
    ) -> PortalExperimentMetricsPage | None:
        return await self.experiments.metrics_page(
            session,
            account_id=account_id,
            experiment_id=experiment_id,
            limit=limit,
            offset=offset,
        )

    async def product_events(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        nm_id: int,
        limit: int,
        offset: int,
    ) -> PortalExperimentEventsPage:
        if account_id is None:
            return PortalExperimentEventsPage(
                total=0,
                limit=limit,
                offset=offset,
                items=[],
                unavailable_sources=["account"],
            )
        unavailable: list[str] = []
        events = await self._safe_source(
            "experiment_events",
            unavailable,
            self.experiments.list_product_events(
                session,
                account_id=account_id,
                nm_id=nm_id,
                limit=limit,
                offset=offset,
            ),
        )
        if events is None:
            return PortalExperimentEventsPage(
                total=0,
                limit=limit,
                offset=offset,
                items=[],
                unavailable_sources=unavailable,
            )
        if unavailable:
            events.unavailable_sources.extend(unavailable)
        return events

    async def results(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        action_id: int | None = None,
        problem_instance_id: int | None = None,
        problem_code: str | None = None,
        nm_id: int | None = None,
        source_module: str | None = None,
        event_type: str | None = None,
        result_status: str | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        trust_state: str | None = None,
        impact_type: str | None = None,
        limit: int,
        offset: int,
    ) -> PortalResultEventsPage:
        if account_id is None:
            return self.result_tracking.empty_page(
                limit=limit, offset=offset, unavailable_sources=["account"]
            )
        page = await self.result_tracking.list_results(
            session,
            account_id=account_id,
            action_id=action_id,
            problem_instance_id=problem_instance_id,
            problem_code=problem_code,
            nm_id=nm_id,
            source_module=self._normalize_source_module(source_module)
            if source_module
            else None,
            event_type=event_type,
            result_status=result_status,
            search=search,
            date_from=date_from,
            date_to=date_to,
            trust_state=trust_state,
            impact_type=impact_type,
            limit=limit,
            offset=offset,
        )
        if problem_instance_id is not None:
            instance = await session.get(ProblemInstance, problem_instance_id)
            if instance is not None and instance.account_id == account_id:
                return page.model_copy(
                    update={
                        "summary": self.result_tracking.problem_timeline_summary(
                            problem=instance,
                            items=page.items,
                            base_summary=page.summary,
                        )
                    }
                )
        return page

    async def problem_results(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        problem_instance_id: int,
        limit: int,
        offset: int,
        ensure_before_snapshot: bool = False,
        created_by: int | None = None,
    ) -> PortalResultEventsPage:
        if ensure_before_snapshot:
            await self.result_tracking.ensure_problem_before_snapshot(
                session,
                problem_instance_id=problem_instance_id,
                created_by=created_by,
            )
            await session.commit()
            self._invalidate_actions_cache()
        page = await self.result_tracking.list_results(
            session,
            account_id=account_id,
            problem_instance_id=problem_instance_id,
            source_module="problem_engine",
            limit=limit,
            offset=offset,
        )
        instance = await session.get(ProblemInstance, problem_instance_id)
        if instance is None:
            return page
        return page.model_copy(
            update={
                "summary": self.result_tracking.problem_timeline_summary(
                    problem=instance,
                    items=page.items,
                    base_summary=page.summary,
                )
            }
        )

    async def action_results(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        limit: int,
        offset: int,
    ) -> PortalResultEventsPage:
        return await self.result_tracking.list_results(
            session,
            account_id=account_id,
            action_id=action_id,
            limit=limit,
            offset=offset,
        )

    async def create_result_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        payload: PortalResultEventCreate,
        created_by: int | None,
    ) -> PortalResultEventRead:
        event = await self.result_tracking.create_event(
            session,
            account_id=account_id,
            action_id=action_id,
            payload=payload,
            created_by=created_by,
        )
        await session.commit()
        self._invalidate_actions_cache()
        return event

    async def modules_health(
        self, session: AsyncSession, *, account_id: int | None = None
    ) -> PortalModulesHealthRead:
        unavailable: list[str] = []
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            unavailable.append("account")
        modules = await self._module_health(account=account, session=session)
        modules = await self._modules_health_with_local_claims(
            session,
            modules=modules,
            account_id=account.id if account is not None else None,
            unavailable=unavailable,
        )
        return PortalModulesHealthRead(
            computed_at=utcnow(),
            modules=modules,
            unavailable_sources=unavailable,
        )

    async def stockops_run(
        self,
        session: AsyncSession,
        *,
        payload: PortalStockOpsRunRequest,
        user_id: int | None,
    ) -> PortalStockOpsRunRead:
        result = await self.stock_control.compatibility_run(
            session, payload, requested_by_user_id=user_id
        )
        await session.commit()
        self._invalidate_actions_cache()
        return result

    async def stockops_runs(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        run_type: str | None,
        limit: int,
        offset: int,
    ) -> PortalStockOpsRunsPage:
        return await self.stock_control.compatibility_runs(
            session,
            account_id=account_id,
            run_type=run_type,
            limit=limit,
            offset=offset,
        )

    async def grouping_preview(
        self,
        session: AsyncSession,
        payload: PortalGroupingPreviewRequest,
        *,
        user_id: int | None = None,
    ) -> PortalGroupingPreviewRead:
        account = await self._active_account(session, account_id=payload.account_id)
        if account is not None:
            return await self.grouping_beta.preview(
                session,
                account_id=account.id,
                nm_id=payload.nm_id,
                preset_key=payload.preset_key,
                recommendation_scenario_id=payload.recommendation_scenario_id,
                custom_config=payload.custom_config,
                requested_by_user_id=user_id,
            )
        return await self.grouping.preview(
            account,
            nm_id=payload.nm_id,
            preset_key=payload.preset_key,
            recommendation_scenario_id=payload.recommendation_scenario_id,
            custom_config=payload.custom_config,
        )

    async def product_grouping(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        nm_id: int,
    ) -> PortalProductGroupingRead:
        account = await self._active_account(session, account_id=account_id)
        if account is not None:
            local = await self.grouping_beta.product_grouping(
                session, account_id=account.id, nm_id=nm_id
            )
            if local.status != "empty" or not self.grouping.is_configured:
                return local
        return await self.grouping.product_grouping(account, nm_id=nm_id)

    async def update_grouping_candidate_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        candidate_id: int,
        status: str,
        actor_user_id: int | None,
        reason: str | None,
    ) -> dict[str, Any]:
        return await self.grouping_beta.update_candidate_status(
            session,
            account_id=account_id,
            candidate_id=candidate_id,
            status=status,
            actor_user_id=actor_user_id,
            reason=reason,
        )

    async def reputation_inbox(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        item_type: str | None,
        status: str | None,
        rating: int | None,
        sentiment: str | None,
        priority: str | None,
        nm_id: int | None,
        date_from: date | None,
        date_to: date | None,
        limit: int,
        offset: int,
    ) -> ReputationInboxOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationInboxOut(
                status="unavailable",
                account_id=account_id,
                limit=limit,
                offset=offset,
                unavailable_sources=["account"],
            )
        return await self.reputation.list_inbox(
            session,
            account,
            item_type=item_type,
            status=status,
            rating=rating,
            sentiment=sentiment,
            priority=priority,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
            offset=offset,
        )

    async def reputation_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
    ) -> ReputationSummaryOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationSummaryOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.summary(
            session, account, date_from=date_from, date_to=date_to
        )

    async def reputation_analytics(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date | None,
        date_to: date | None,
        granularity: str,
    ) -> ReputationAnalyticsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationAnalyticsOut(status="unavailable", account_id=account_id)
        return await self.reputation.analytics(
            session,
            account,
            date_from=date_from,
            date_to=date_to,
            granularity=granularity,
        )

    async def reputation_sync(
        self, session: AsyncSession, *, account_id: int | None
    ) -> ReputationSyncOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationSyncOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.sync_reputation(session, account)

    async def reputation_item(
        self, session: AsyncSession, *, account_id: int | None, item_id: str
    ) -> ReputationItemOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationItemOut(
                id=item_id,
                item_type="review",
                account_id=account_id,
                status="blocked",
                trust_state="unavailable",
                warnings=["account is not available"],
            )
        return await self.reputation.get_item(session, account, item_id=item_id)

    async def reputation_generate_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        item_id: str,
        payload: ReputationDraftRequest,
        user_id: int | None = None,
    ) -> ReputationDraftMutationOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        if payload.text:
            draft = await self._persist_reputation_draft(
                session,
                account_id=account.id,
                item_id=item_id,
                draft_type=payload.draft_type,
                text=payload.text,
                created_by=user_id,
                payload=payload.payload,
            )
            await session.commit()
            self._invalidate_actions_cache()
            return ReputationDraftMutationOut(
                status="ok",
                account_id=account.id,
                draft=draft,
                message="Reply draft saved locally in finance. Publishing remains disabled until manual confirmation.",
                warnings=["reputation_local_draft"],
                trust_state=TrustState.PROVISIONAL,
            )
        result = await self.reputation.generate_draft(
            session,
            account,
            item_id=item_id,
            draft_type=payload.draft_type,
            created_by=user_id,
            force_ai=bool(
                payload.force_ai
                if payload.force_ai is not None
                else (payload.payload or {}).get("force_ai", True)
            ),
        )
        return result

    async def reputation_drafts(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> ReputationDraftsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationDraftsOut(
                status="unavailable", account_id=account_id, limit=limit, offset=offset
            )
        return await self.reputation.list_drafts(
            session, account, status=status, limit=limit, offset=offset
        )

    async def reputation_approve_all_drafts(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        limit: int,
    ) -> ReputationBulkDraftDecisionOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationBulkDraftDecisionOut(
                status="unavailable", account_id=account_id
            )
        return await self.reputation.approve_all_drafts(session, account, limit=limit)

    async def reputation_chats(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        limit: int,
        offset: int,
    ) -> ReputationChatsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationChatsOut(
                status="unavailable",
                account_id=account_id,
                limit=limit,
                offset=offset,
                unavailable_sources=["account"],
            )
        return await self.reputation.list_chats(
            session, account, limit=limit, offset=offset
        )

    async def reputation_chat_events(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        chat_id: str,
    ) -> ReputationChatEventsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationChatEventsOut(
                status="unavailable", account_id=account_id, chat_id=chat_id
            )
        return await self.reputation.chat_events(session, account, chat_id=chat_id)

    async def reputation_approve_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        draft_id: str,
        approved_by: int | None = None,
    ) -> ReputationDraftMutationOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.approve_draft(
            session, account, draft_id=draft_id, approved_by=approved_by
        )

    async def reputation_regenerate_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        draft_id: str,
        payload: ReputationDraftDecisionRequest,
    ) -> ReputationDraftMutationOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.regenerate_draft(
            session, account, draft_id=draft_id, request=payload
        )

    async def reputation_reject_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        draft_id: str,
        payload: ReputationDraftDecisionRequest,
    ) -> ReputationDraftMutationOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationDraftMutationOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.reject_draft(
            session, account, draft_id=draft_id, request=payload
        )

    async def reputation_publish_reply(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        draft_id: str,
        payload: ReputationPublishRequest,
        user_id: int | None,
    ):
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            result = await self.reputation_adapter.publish_reply(
                self._fallback_account(account_id),
                draft_id=draft_id,
                request=payload.model_copy(update={"confirm": False}),
            )
        else:
            result = await self.reputation.publish_reply(
                session, account, draft_id=draft_id, request=payload, user_id=user_id
            )
        session.add(
            ResultEvent(
                account_id=account.id if account is not None else int(account_id or 0),
                source_module="reputation",
                source_id=draft_id,
                external_id=draft_id,
                event_type=str(result.event_type),
                status="done" if result.success else "blocked",
                external_status=str(result.external_status)
                if result.external_status is not None
                else None,
                message=result.message,
                payload_json={
                    "success": result.success,
                    "title": result.title,
                    "manual_confirm": bool(payload.confirm),
                    "created_by": user_id,
                    "data": result.data,
                    "warnings": result.warnings,
                },
            )
        )
        await session.commit()
        self._invalidate_actions_cache()
        return result

    async def reputation_mark_no_reply_needed(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        item_id: str,
        payload: ReputationNoReplyRequest,
        user_id: int | None,
    ):
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            result = await self.reputation_adapter.mark_no_reply_needed(
                self._fallback_account(account_id),
                item_id=item_id,
                request=payload.model_copy(update={"confirm": False}),
            )
        else:
            result = await self.reputation.mark_no_reply_needed(
                session, account, item_id=item_id, request=payload, user_id=user_id
            )
        session.add(
            ResultEvent(
                account_id=account.id if account is not None else int(account_id or 0),
                source_module="reputation",
                source_id=item_id,
                external_id=item_id,
                event_type=str(result.event_type),
                status="done" if result.success else "blocked",
                external_status=str(result.external_status)
                if result.external_status is not None
                else None,
                message=result.message,
                payload_json={
                    "success": result.success,
                    "title": result.title,
                    "manual_confirm": bool(payload.confirm),
                    "created_by": user_id,
                    "data": result.data,
                    "warnings": result.warnings,
                },
            )
        )
        await session.commit()
        self._invalidate_actions_cache()
        return result

    async def reputation_settings(
        self, session: AsyncSession, *, account_id: int | None
    ) -> ReputationSettingsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationSettingsOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.get_settings(session, account)

    async def reputation_brands(
        self, session: AsyncSession, *, account_id: int | None
    ) -> ReputationBrandsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationBrandsOut(
                status="unavailable",
                account_id=account_id,
                warnings=["account_unavailable"],
            )
        return await self.reputation.brands(session, account)

    async def reputation_update_settings(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        payload: ReputationSettingsUpdateRequest,
    ) -> ReputationSettingsOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationSettingsOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.update_settings(session, account, request=payload)

    async def reputation_learning(
        self, session: AsyncSession, *, account_id: int | None
    ) -> ReputationLearningOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationLearningOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.learning(session, account)

    async def reputation_toggle_learning(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        payload: ReputationLearningToggleRequest,
    ) -> ReputationLearningOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationLearningOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.toggle_learning(session, account, payload)

    async def reputation_update_prompts(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        payload: ReputationPromptUpdateRequest,
    ) -> ReputationLearningOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationLearningOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.update_prompts(session, account, payload)

    async def reputation_apply_learning(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        payload: ReputationLearningApplyRequest,
    ) -> ReputationLearningOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationLearningOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.apply_learning(session, account, payload)

    async def reputation_delete_learning_entry(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        entry_id: int,
    ) -> ReputationLearningOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationLearningOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.delete_learning_entry(session, account, entry_id)

    async def reputation_reset_learning(
        self, session: AsyncSession, *, account_id: int | None
    ) -> ReputationLearningOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationLearningOut(
                status="unavailable",
                account_id=account_id,
                unavailable_sources=["account"],
            )
        return await self.reputation.reset_learning(session, account)

    async def reputation_product_insights(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        nm_id: int,
    ) -> ReputationProductInsightOut:
        account = await self._active_account(session, account_id=account_id)
        if account is None:
            return ReputationProductInsightOut(
                status="unavailable",
                account_id=account_id,
                nm_id=nm_id,
                warnings=["account_unavailable"],
            )
        return await self.reputation.product_insights(session, account, nm_id=nm_id)

    async def _active_account(
        self, session: AsyncSession, *, account_id: int | None
    ) -> WBAccount | None:
        if account_id is None:
            return None
        return await session.get(WBAccount, account_id)

    async def _recover_product360_session(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        unavailable: list[str],
    ) -> WBAccount:
        try:
            await session.rollback()
            account = await session.get(WBAccount, account_id)
            if account is not None:
                return account
        except Exception as exc:
            unavailable.append("db_session_recovery")
            log_optional_module_failure(
                source="product_360",
                reason="db_session_recovery_exception",
                error_type=type(exc).__name__,
            )
        return self._fallback_account(account_id)

    def _fallback_account(self, account_id: int | None) -> WBAccount:
        return WBAccount(
            id=int(account_id or 0),
            name=str(account_id or "unknown"),
            external_account_id=None,
            timezone="Europe/Moscow",
            is_active=True,
        )

    def _account_summary(self, account: WBAccount) -> PortalAccountSummary:
        return PortalAccountSummary(
            id=account.id,
            name=account.name,
            seller_name=account.seller_name,
            external_account_id=account.external_account_id,
            timezone=account.timezone,
            is_active=account.is_active,
        )

    async def _module_health(
        self,
        *,
        account: WBAccount | None,
        session: AsyncSession | None = None,
    ) -> PortalModuleHealth:
        return await self.module_registry.health(account=account, session=session)

    async def _safe_source(self, name: str, unavailable: list[str], awaitable):
        started = time.perf_counter()
        try:
            return await awaitable
        except HTTPException as exc:
            unavailable.append(name)
            record_unavailable_source(name)
            log_optional_module_failure(
                source=name,
                reason="http_exception",
                duration_ms=(time.perf_counter() - started) * 1000,
                error_type=f"HTTPException:{exc.status_code}",
            )
            return None
        except Exception as exc:
            unavailable.append(name)
            record_unavailable_source(name)
            log_optional_module_failure(
                source=name,
                reason="exception",
                duration_ms=(time.perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
            )
            return None

    async def _safe_health(self, name: str, awaitable) -> tuple[str, str | None]:
        started = time.perf_counter()
        try:
            return await awaitable
        except Exception as exc:
            log_optional_module_failure(
                source=name,
                reason="health_exception",
                duration_ms=(time.perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
            )
            return "unavailable", f"{name} is unavailable"

    async def _safe_optional_actions(
        self, name: str, unavailable: list[str], awaitable
    ) -> tuple[list[PortalActionRead], str | None]:
        started = time.perf_counter()
        try:
            actions, source = await awaitable
            if source:
                record_unavailable_source(source)
            return list(actions or []), source
        except Exception as exc:
            unavailable.append(name)
            record_unavailable_source(name)
            log_optional_module_failure(
                source=name,
                reason="optional_actions_exception",
                duration_ms=(time.perf_counter() - started) * 1000,
                error_type=type(exc).__name__,
            )
            return [], name

    async def _wait_optional(self, source: str, awaitable, timeout: float | None):
        if timeout is None or timeout <= 0:
            return await awaitable
        try:
            return await asyncio.wait_for(awaitable, timeout=timeout)
        except asyncio.TimeoutError as exc:
            record_unavailable_source(source)
            log_optional_module_failure(
                source=source,
                reason="timeout",
                duration_ms=timeout * 1000,
                error_type=type(exc).__name__,
            )
            raise

    async def _with_optional_timeout(
        self, source: str, awaitable, *, max_seconds: float | None = None
    ):
        timeout = self._optional_module_timeout_seconds(source)
        if max_seconds is not None:
            timeout = (
                min(timeout, max_seconds)
                if timeout is not None and timeout > 0
                else max_seconds
            )
        return await self._wait_optional(source, awaitable, timeout)

    def _optional_module_timeout_seconds(self, source: str) -> float | None:
        normalized = str(source or "").strip().lower()
        adapter = {
            "checker": self.checker,
            "checker_quality": self.checker,
            "grouping": self.grouping,
            "grouping_beta": self.grouping,
            "reputation": self.reputation_adapter,
            "claims": self.claims_adapter,
            "stockops": self.stockops,
        }.get(normalized)
        settings = getattr(adapter, "settings", None)
        setting_name = {
            "checker_quality": "checker_http_timeout_seconds",
            "grouping_beta": "grouping_http_timeout_seconds",
        }.get(normalized, f"{normalized}_http_timeout_seconds")
        try:
            value = getattr(settings, setting_name)
        except Exception:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    async def _list_unified_actions(
        self, session: AsyncSession, *, account_id: int, limit: int
    ) -> list[UnifiedAction]:
        result = await session.execute(
            select(UnifiedAction)
            .where(UnifiedAction.account_id == account_id)
            .order_by(UnifiedAction.created_at.desc(), UnifiedAction.id.desc())
            .limit(max(int(limit or 50), 1))
        )
        return list(result.scalars())

    async def _find_unified_action_by_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        source_module: str,
        source_id: str,
    ) -> UnifiedAction | None:
        result = await session.execute(
            select(UnifiedAction)
            .where(
                UnifiedAction.account_id == account_id,
                UnifiedAction.source_module == source_module,
                UnifiedAction.source_id == source_id,
            )
            .limit(1)
        )
        return next(iter(result.scalars()), None)

    def _is_shadow_action(self, row: UnifiedAction) -> bool:
        payload = dict(row.payload_json or {})
        return bool(payload.get("shadow_synthetic"))

    def _shadow_status_overrides(
        self, rows: list[UnifiedAction]
    ) -> dict[tuple[str, str], UnifiedAction]:
        result: dict[tuple[str, str], UnifiedAction] = {}
        for row in rows:
            if not self._is_shadow_action(row):
                continue
            if not row.source_id:
                continue
            result[
                (self._normalize_source_module(row.source_module), str(row.source_id))
            ] = row
        return result

    def _apply_shadow_status(
        self,
        item: PortalActionRead,
        *,
        shadow_overrides: dict[tuple[str, str], UnifiedAction],
    ) -> PortalActionRead:
        key = (
            self._normalize_source_module(item.source_module),
            str(item.source_id or ""),
        )
        row = shadow_overrides.get(key)
        update = {
            "can_update_status": bool(
                item.can_update_status or self._has_safe_local_status_route(item)
            ),
            "can_update": bool(
                item.can_update
                or item.can_update_status
                or self._has_safe_local_status_route(item)
            ),
            "can_update_reason": item.can_update_reason,
        }
        if row is not None:
            row_payload = dict(row.payload_json or {})
            update.update(
                {
                    "action_id": row.id,
                    "status": self._normalize_status(row.status),
                    "assigned_to_user_id": getattr(row, "assigned_to_user_id", None)
                    or row_payload.get("assigned_to_user_id"),
                    "deadline_at": getattr(row, "deadline_at", None)
                    or self._optional_datetime(row_payload.get("deadline_at")),
                    "review_status": self._normalize_review_status(
                        getattr(row, "review_status", None)
                        or row_payload.get("review_status")
                    ),
                    "last_comment": getattr(row, "last_comment", None)
                    or row_payload.get("last_comment"),
                    "closed_at": getattr(row, "closed_at", None)
                    or self._optional_datetime(row_payload.get("closed_at")),
                    "dismissed_at": getattr(row, "dismissed_at", None)
                    or self._optional_datetime(row_payload.get("dismissed_at")),
                    "payload": {
                        **dict(item.payload or {}),
                        "shadow_action_id": row.id,
                        **row_payload,
                    },
                    "raw": {
                        **dict(item.raw or {}),
                        "shadow_action_id": row.id,
                        **row_payload,
                    },
                    "source_sync_state": row_payload.get("source_sync_state")
                    or item.source_sync_state,
                    "can_update_reason": row_payload.get("can_update_reason")
                    or item.can_update_reason,
                }
            )
        elif update["can_update_reason"] is None and not update["can_update"]:
            update["can_update_reason"] = item.can_update_reason
        return item.model_copy(update=update)

    def _has_safe_local_status_route(self, item: PortalActionRead) -> bool:
        source_module = self._normalize_source_module(item.source_module)
        return bool(item.source_id) and (
            source_module in self.MVP_ACTION_MODULES
            or source_module in self.SHADOW_ACTION_MODULES
            or item.source in self.SHADOW_ACTION_SOURCES
        )

    def _synthetic_action_identity(
        self, *, account_id: int, action: PortalActionRead | UnifiedActionOut
    ) -> dict[str, Any]:
        raw = self._dump(action)
        source_module = self._normalize_source_module(
            raw.get("source_module") or raw.get("module") or "manual"
        )
        action_type = str(raw.get("action_type") or "MANUAL_REVIEW")
        nm_id = self._optional_int(raw.get("nm_id"))
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        vendor_code = self._first_string(
            raw.get("vendor_code"), data.get("vendor_code"), payload.get("vendor_code")
        )
        source_id = self._first_string(raw.get("source_id"), raw.get("id"))
        if not source_id:
            source_id = self._deterministic_source_id(
                source_module=source_module,
                action_type=action_type,
                nm_id=nm_id,
                vendor_code=vendor_code,
            )
        return {
            "account_id": account_id,
            "source_module": source_module,
            "source_id": source_id,
            "action_type": action_type,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
        }

    def _deterministic_source_id(
        self,
        *,
        source_module: str,
        action_type: str,
        nm_id: int | None,
        vendor_code: str | None,
    ) -> str:
        parts = [source_module, action_type.lower()]
        if nm_id is not None:
            parts.append(f"nm:{nm_id}")
        if vendor_code:
            parts.append(f"vendor:{vendor_code}")
        return ":".join(parts)

    def _synthetic_payload(
        self, action: PortalActionRead | UnifiedActionOut
    ) -> dict[str, Any]:
        raw = self._dump(action)
        payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        return {
            **payload,
            "data": data,
            "reason": raw.get("reason") or raw.get("summary") or "",
            "next_step": raw.get("next_step") or "",
            "expected_effect_amount": raw.get("expected_effect_amount")
            or raw.get("expected_impact_amount"),
            "confidence": raw.get("confidence") or "medium",
            "original_action": raw,
        }

    def _overview_money_summary(self, money_summary: Any) -> dict[str, Any]:
        if money_summary is None:
            return self._unavailable_block("money_summary")
        dumped = self._dump(money_summary)
        if not dumped:
            return {"status": "empty"}
        return {"status": "ok", **dumped}

    def _unavailable_block(self, source: str) -> dict[str, Any]:
        return {"status": "unavailable", "message": f"{source} is not available"}

    def _data_trust(
        self, money_dump: dict[str, Any], blockers_dump: dict[str, Any]
    ) -> dict[str, Any]:
        trust = money_dump.get("trust") or (money_dump.get("meta") or {}).get(
            "data_trust"
        )
        if isinstance(trust, dict):
            return trust
        dq_summary = (
            blockers_dump.get("data_quality_summary")
            if isinstance(blockers_dump, dict)
            else None
        )
        if isinstance(dq_summary, dict) and dq_summary:
            return {
                "status": blockers_dump.get("overall_state") or "ok",
                "trust_state": dq_summary.get("trust_state"),
                "business_trusted": dq_summary.get("business_trusted"),
                "operational_trusted": dq_summary.get("operational_trusted"),
                "financial_final": dq_summary.get("financial_final"),
                "blocked_reasons": dq_summary.get("blocked_reasons") or [],
                "financial_final_blockers_total": dq_summary.get(
                    "financial_final_blockers_total"
                ),
            }
        return self._unavailable_block("data_trust")

    def _cost_status(self, money_dump: dict[str, Any]) -> dict[str, Any]:
        if money_dump.get("status") != "ok":
            return self._unavailable_block("cost_status")
        cost_coverage = money_dump.get("cost_coverage") or {}
        quality = money_dump.get("quality") or {}
        kpis = money_dump.get("kpis") or {}
        expenses = money_dump.get("expenses") or {}
        return {
            "status": "ok",
            "cost_coverage": cost_coverage,
            "cost_trust_policy": (money_dump.get("trust") or {}).get(
                "cost_trust_policy"
            )
            or ((money_dump.get("meta") or {}).get("data_trust") or {}).get(
                "cost_trust_policy"
            ),
            "supplier_confirmed_revenue_coverage_percent": quality.get(
                "supplier_confirmed_cost_coverage_percent"
            )
            if quality.get("supplier_confirmed_cost_coverage_percent") is not None
            else quality.get("supplier_cost_coverage_percent"),
            "trusted_revenue_cost_coverage_percent": (
                money_dump.get("trust") or {}
            ).get("trusted_revenue_cost_coverage_percent"),
            "unallocated_expenses": expenses.get("unallocated_expenses")
            if expenses.get("unallocated_expenses") is not None
            else kpis.get("account_level_expenses"),
            "expense_data_quality": kpis.get("expense_data_quality"),
        }

    def _cost_state(self, raw: dict[str, Any]) -> str:
        cost_coverage = (
            raw.get("cost_coverage")
            or (raw.get("money") or {}).get("cost_coverage")
            or {}
        )
        if isinstance(cost_coverage, dict):
            state = str(
                cost_coverage.get("status")
                or cost_coverage.get("cost_truth_level")
                or ""
            ).lower()
            if state in {"ok", "trusted", "final", "complete"}:
                return "ok"
            if state in {"missing", "blocked", "partial"}:
                return state
            if cost_coverage.get("can_use_for_final_profit") is False:
                return "blocked"
        finality = raw.get("finality") or {}
        if isinstance(finality, dict) and finality.get("profit_final") is False:
            return "blocked"
        return "unknown"

    def _stock_state(self, *, stock: dict[str, Any], stock_qty: float | None) -> str:
        raw_state = str(stock.get("status") or stock.get("stock_status") or "").lower()
        if raw_state:
            return raw_state
        days = self._optional_float(stock.get("days_of_stock"))
        if stock_qty is not None and stock_qty <= 3:
            return "low_stock"
        if days is not None and days <= 7:
            return "low_stock"
        if stock_qty is not None and stock_qty >= 100:
            return "overstock"
        if days is not None and days >= 60:
            return "overstock"
        if stock:
            return "ok"
        return "unknown"

    def _module_state(self, payload: Any) -> str:
        if payload is None:
            return "not_configured"
        if isinstance(payload, dict):
            return str(payload.get("status") or payload.get("state") or "ok")
        return "ok"

    def _doctor_summary(self, doctor: Any) -> dict[str, Any]:
        if doctor is None:
            return self._unavailable_block("profit_doctor")
        dumped = self._dump(doctor)
        return {
            "status": dumped.get("status") or "ok",
            "summary": dumped.get("summary"),
            "trust_state": dumped.get("trust_state"),
            "total_signals": dumped.get("total_signals", 0),
            "total_diagnoses": dumped.get("total_diagnoses", 0),
            "estimated_impact_amount": dumped.get("estimated_impact_amount"),
            "unavailable_sources": dumped.get("unavailable_sources") or [],
            "warnings": dumped.get("warnings") or [],
        }

    def _doctor_top_problems(self, doctor: Any, *, limit: int) -> list[dict[str, Any]]:
        dumped = self._dump(doctor)
        items = dumped.get("root_causes") or dumped.get("diagnoses") or []
        return [self._compact_operator_item(item) for item in list(items)[:limit]]

    def _doctor_actions(self, doctor: Any, *, limit: int) -> list[dict[str, Any]]:
        dumped = self._dump(doctor)
        items = dumped.get("today_plan") or dumped.get("actions") or []
        return [self._compact_operator_item(item) for item in list(items)[:limit]]

    def _doctor_product_risks(self, doctor: Any, *, limit: int) -> list[dict[str, Any]]:
        dumped = self._dump(doctor)
        items = dumped.get("product_diagnoses") or []
        return [self._compact_operator_item(item) for item in list(items)[:limit]]

    def _product_diagnosis_block(self, doctor: Any) -> PortalDataBlock:
        if doctor is None:
            return PortalDataBlock(
                status="unavailable", data={}, message="profit_doctor is not available"
            )
        dumped = self._dump(doctor)
        data = {
            "summary": dumped.get("summary"),
            "trust_state": dumped.get("trust_state"),
            "total_signals": dumped.get("total_signals", 0),
            "total_diagnoses": dumped.get("total_diagnoses", 0),
            "estimated_impact_amount": dumped.get("estimated_impact_amount"),
            "top_profit_leaks": dumped.get("top_profit_leaks") or [],
            "root_causes": dumped.get("root_causes") or [],
            "product_diagnoses": dumped.get("product_diagnoses") or [],
            "unavailable_sources": dumped.get("unavailable_sources") or [],
        }
        return PortalDataBlock(
            status=dumped.get("status") or "ok",
            data=data,
            message=dumped.get("summary"),
        )

    def _lightweight_product_doctor(
        self,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None,
        date_to: date | None,
        detail: dict[str, Any],
        actions: list[PortalActionRead],
        unavailable_sources: list[str],
    ) -> ProfitDoctorOut:
        problem_actions = [
            action
            for action in actions
            if self._normalize_source_module(getattr(action, "source_module", None))
            == "problem_engine"
        ]
        top_actions = list(problem_actions[:3] or actions[:3])
        money_answer = detail.get("money_answer") or detail.get("answer") or {}
        fallback_summary = (
            money_answer.get("headline")
            or money_answer.get("title")
            or money_answer.get("summary")
            or "Product diagnostics are ready."
        )
        summary = (
            str(getattr(top_actions[0], "title", None) or fallback_summary)
            if top_actions
            else str(fallback_summary)
        )
        critical_count = sum(
            1
            for action in top_actions
            if str(getattr(action, "priority", "") or "").upper() in {"P0", "P1"}
        )
        estimated_impact = sum(
            abs(
                float(
                    getattr(action, "expected_effect_amount", None)
                    or getattr(action, "expected_impact_amount", None)
                    or 0
                )
            )
            for action in top_actions
        )
        return ProfitDoctorOut(
            status="ok",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            trust_state=TrustState.PROVISIONAL,
            summary=summary,
            headline=summary,
            business_status="attention" if top_actions else "ok",
            critical_count=critical_count,
            total_signals=len(top_actions),
            total_diagnoses=len(problem_actions),
            estimated_impact_amount=estimated_impact or None,
            estimated_impact_confidence="medium" if estimated_impact else "low",
            estimated_impact_calculation_note="Aggregated from Product360 dynamic product actions.",
            top_sections={
                "product": {
                    "nm_id": nm_id,
                    "dynamic_problem_count": len(problem_actions),
                    "top_action_ids": [action.id for action in top_actions],
                }
            },
            today_plan=[],
            actions=[],
            product_diagnoses=[],
            data={
                "source": "product360_lightweight",
                "full_profit_doctor_skipped": True,
                "upstream_unavailable_sources": self._dedupe_strings(
                    unavailable_sources
                ),
            },
            warnings=["product360_lightweight_diagnosis"],
            unavailable_sources=[],
        )

    async def _optional_product_module_block(
        self,
        *,
        source: str,
        adapter: Any | None,
        account_id: int,
        nm_id: int,
        detail: dict[str, Any],
        max_seconds: float | None = None,
    ) -> PortalDataBlock:
        if adapter is None:
            return PortalDataBlock(
                status="not_configured",
                data={},
                message=f"{source} module is not configured",
            )
        for method_name in ("product_360", "product_summary", "product_block"):
            method = getattr(adapter, method_name, None)
            if method is None:
                continue
            started = time.perf_counter()
            try:
                payload = await self._with_optional_timeout(
                    source,
                    method(
                        account_id=account_id,
                        nm_id=nm_id,
                        vendor_code=(detail.get("identity") or {}).get("vendor_code")
                        or detail.get("vendor_code"),
                        barcode=(detail.get("identity") or {}).get("barcode")
                        or detail.get("barcode"),
                    ),
                    max_seconds=max_seconds,
                )
            except TypeError:
                payload = await self._with_optional_timeout(
                    source,
                    method(account_id=account_id, nm_id=nm_id),
                    max_seconds=max_seconds,
                )
            except Exception as exc:
                log_optional_module_failure(
                    source=source,
                    reason="product_block_exception",
                    account_id=account_id,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    error_type=type(exc).__name__,
                )
                return PortalDataBlock(
                    status="unavailable",
                    data={},
                    message=f"{source} module is unavailable",
                )
            if isinstance(payload, PortalDataBlock):
                safe_data = self._scrub_private_fields(payload.data)
                status = payload.status
                if source in {"reputation", "claims"} and status == "disabled":
                    status = "not_configured"
                return PortalDataBlock(
                    status=status
                    if status
                    in {
                        "ok",
                        "not_configured",
                        "unavailable",
                        "empty",
                        "beta",
                        "disabled",
                        "degraded",
                    }
                    else "ok",
                    data=safe_data,
                    message=payload.message,
                )
            safe_payload = self._scrub_private_fields(
                self._dump(payload)
                if not isinstance(payload, list)
                else {"items": payload}
            )
            status = str(safe_payload.get("status") or "ok")
            if source in {"reputation", "claims"} and status == "disabled":
                status = "not_configured"
            return PortalDataBlock(
                status=status
                if status
                in {
                    "ok",
                    "not_configured",
                    "unavailable",
                    "empty",
                    "beta",
                    "disabled",
                    "degraded",
                }
                else "ok",
                data=safe_payload,
            )
        return PortalDataBlock(
            status="not_configured",
            data={},
            message=f"{source} module is not configured",
        )

    async def _reputation_product_block(
        self,
        session: AsyncSession,
        *,
        account: WBAccount,
        nm_id: int,
        detail: dict[str, Any],
        max_seconds: float | None,
    ) -> PortalDataBlock:
        try:
            block = await self._with_optional_timeout(
                "reputation",
                self.reputation.product_360(
                    session, account_id=account.id, nm_id=nm_id
                ),
                max_seconds=max_seconds,
            )
            if getattr(block, "status", None) in {"ok", "empty", "degraded"}:
                return block
        except Exception:
            block = None
        fallback = await self._optional_product_module_block(
            source="reputation",
            adapter=self.reputation_adapter,
            account_id=account.id,
            nm_id=nm_id,
            detail=detail,
            max_seconds=max_seconds,
        )
        if block is None:
            return fallback
        if fallback.status in {"ok", "empty", "degraded"}:
            return fallback
        return block

    async def _reputation_actions(
        self,
        session: AsyncSession,
        *,
        account: WBAccount,
        limit: int,
        unavailable: list[str],
        max_seconds: float | None,
    ) -> tuple[list[PortalActionRead], str | None]:
        try:
            actions, source = await self._safe_optional_actions(
                "reputation",
                unavailable,
                self._with_optional_timeout(
                    "reputation",
                    self.reputation.reputation_actions(session, account, limit=limit),
                    max_seconds=max_seconds,
                ),
            )
            if actions or source is None:
                return actions, source
        except Exception:
            pass
        reputation_action_method = getattr(
            self.reputation_adapter, "reputation_actions", None
        )
        if reputation_action_method is None:
            return [], None
        return await self._safe_optional_actions(
            "reputation",
            unavailable,
            self._with_optional_timeout(
                "reputation",
                reputation_action_method(account, limit=limit),
                max_seconds=max_seconds,
            ),
        )

    def _reputation_block_with_history(
        self, block: PortalDataBlock, result_events: list[dict[str, Any]]
    ) -> PortalDataBlock:
        data = dict(block.data or {}) if isinstance(block.data, dict) else {}
        history = [
            self._scrub_private_fields(event)
            for event in result_events
            if "reputation" in str(event.get("event_type") or "").lower()
            or "reply" in str(event.get("event_type") or "").lower()
            or "review" in str(event.get("event_type") or "").lower()
            or "question" in str(event.get("event_type") or "").lower()
            or "chat" in str(event.get("event_type") or "").lower()
        ]
        if history:
            data["result_history"] = history
            if block.status in {"unavailable", "not_configured", "disabled"}:
                data.setdefault(
                    "history_note",
                    "Reputation service is unavailable, showing local result history only.",
                )
                status = "degraded" if block.status == "unavailable" else block.status
                return block.model_copy(
                    update={"status": status, "data": self._scrub_private_fields(data)}
                )
        else:
            data.setdefault("result_history", [])
        return block.model_copy(update={"data": self._scrub_private_fields(data)})

    async def _modules_health_with_local_claims(
        self,
        session: AsyncSession,
        *,
        modules: PortalModuleHealth,
        account_id: int | None,
        unavailable: list[str],
    ) -> PortalModuleHealth:
        if account_id is None:
            return modules
        try:
            page = await self.claims_factory.list_cases(
                session, account_id=account_id, limit=1, offset=0
            )
        except Exception:
            unavailable.append("local_claim_cases")
            return modules
        total = int(getattr(page, "total", 0) or 0)
        if total <= 0:
            return modules
        claims = modules.claims.model_copy(
            update={
                "visible": True,
                "navigation_group": "operator",
                "reason": "Claims Factory has local cases in finance for this account.",
                "warnings": list(modules.claims.warnings or [])
                + ["claims_visible_due_to_local_cases"],
            }
        )
        return modules.model_copy(update={"claims": claims})

    async def _claims_block_with_local_cases(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        block: PortalDataBlock,
        unavailable: list[str],
    ) -> PortalDataBlock:
        local_cases = await self._safe_source(
            "local_claim_cases",
            unavailable,
            self.claims_factory.list_cases(
                session,
                account_id=account_id,
                nm_id=nm_id,
                limit=50,
                offset=0,
            ),
        )
        if local_cases is None:
            return self._claims_product_defaults(block)
        cases = [item.model_dump(mode="json") for item in local_cases.items]
        data = dict(block.data or {}) if isinstance(block.data, dict) else {}
        candidates = list(data.get("candidates") or data.get("items") or [])
        candidates = [item for item in candidates if isinstance(item, dict)]
        local_source_ids = {
            str(
                item.get("source_id")
                or ((item.get("data") or {}).get("signal") or {}).get("source_id")
                or ""
            )
            for item in cases
            if item.get("source_id")
            or ((item.get("data") or {}).get("signal") or {}).get("source_id")
        }
        candidates = [
            item
            for item in candidates
            if not item.get("source_id")
            or str(item.get("source_id")) not in local_source_ids
        ]
        potential = self._optional_float(data.get("potential_compensation_amount"))
        if potential is None:
            potential = sum(
                self._optional_float(
                    item.get("estimated_amount")
                    or item.get("impact")
                    or item.get("amount_claimed")
                )
                or 0
                for item in candidates + cases
            )
        actions = list(data.get("actions") or [])
        next_claim_action = actions[0] if actions else None
        if next_claim_action is None and candidates:
            first = candidates[0]
            next_claim_action = {
                "source_module": "claims",
                "source_id": first.get("source_id"),
                "action_type": first.get("action_type") or "defect_claim_candidate",
                "title": first.get("title") or "Claims candidate",
                "nm_id": first.get("nm_id"),
            }
        data.update(
            {
                "local_cases": cases,
                "local_cases_count": len(cases),
                "candidates": candidates,
                "candidate_count": len(candidates),
                "potential_compensation_amount": potential
                if potential and potential > 0
                else None,
                "open_cases_count": len(cases),
                "next_claim_action": next_claim_action,
            }
        )
        data.pop("items", None)
        status = self._claims_product_status(
            block.status, local_cases_count=len(cases), candidate_count=len(candidates)
        )
        safe_data = self._scrub_private_fields(data)
        return block.model_copy(
            update={"status": status, "data": safe_data, "message": block.message}
        )

    def _claims_product_defaults(self, block: PortalDataBlock) -> PortalDataBlock:
        data = dict(block.data or {}) if isinstance(block.data, dict) else {}
        candidates = data.get("candidates") or data.get("items") or []
        if not isinstance(candidates, list):
            candidates = []
        local_cases = data.get("local_cases") or []
        if not isinstance(local_cases, list):
            local_cases = []
        data.setdefault("local_cases", local_cases)
        data.setdefault("local_cases_count", len(local_cases))
        data.setdefault(
            "candidates", [item for item in candidates if isinstance(item, dict)]
        )
        data.setdefault("candidate_count", len(data["candidates"]))
        data.setdefault(
            "potential_compensation_amount",
            self._optional_float(data.get("potential_compensation_amount")),
        )
        data.setdefault("open_cases_count", len(local_cases))
        data.setdefault("next_claim_action", None)
        data.pop("items", None)
        safe_data = self._scrub_private_fields(data)
        return block.model_copy(update={"data": safe_data})

    def _claims_product_status(
        self, raw_status: str, *, local_cases_count: int, candidate_count: int
    ) -> str:
        status = (
            raw_status
            if raw_status
            in {"ok", "empty", "not_configured", "unavailable", "degraded", "disabled"}
            else "unavailable"
        )
        if local_cases_count > 0:
            return "degraded" if status == "unavailable" else "ok"
        if candidate_count > 0:
            return (
                "ok"
                if status in {"ok", "empty", "not_configured", "disabled"}
                else "degraded"
            )
        if status in {"ok", "degraded"}:
            return "empty"
        return status

    def _compact_operator_item(self, item: Any) -> dict[str, Any]:
        raw = self._dump(item)
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        return {
            "id": raw.get("id"),
            "module": raw.get("module") or raw.get("source_module"),
            "source_module": raw.get("source_module") or raw.get("module"),
            "type": raw.get("diagnosis_type")
            or raw.get("action_type")
            or raw.get("signal_type"),
            "priority": raw.get("priority"),
            "status": raw.get("status"),
            "trust_state": raw.get("trust_state"),
            "title": raw.get("title"),
            "summary": raw.get("summary") or raw.get("reason") or raw.get("message"),
            "reason": raw.get("reason"),
            "next_step": raw.get("next_step"),
            "expected_effect_amount": raw.get("expected_effect_amount")
            or data.get("estimated_impact_amount"),
            "nm_id": raw.get("nm_id"),
            "sku_id": raw.get("sku_id"),
            "vendor_code": data.get("vendor_code"),
            "product_title": data.get("product_title"),
        }

    def _reputation_block(
        self, module_health: PortalModuleHealth, doctor: Any
    ) -> dict[str, Any]:
        health = module_health.reputation
        status = health.status
        reputation_items = [
            item
            for item in self._doctor_top_problems(doctor, limit=50)
            if item.get("module") == "reputation"
            or item.get("source_module") == "reputation"
        ]
        return {
            "status": status,
            "unanswered_reviews_count": None if status != "ok" else 0,
            "unanswered_questions_count": None if status != "ok" else 0,
            "negative_unanswered_count": len(reputation_items)
            if status == "ok"
            else None,
            "message": health.message or health.detail,
            "warnings": list(health.warnings or []),
        }

    def _claims_block(
        self, module_health: PortalModuleHealth, doctor: Any
    ) -> dict[str, Any]:
        health = module_health.claims
        status = health.status
        claims_items = [
            item
            for item in self._doctor_top_problems(doctor, limit=50)
            + self._doctor_actions(doctor, limit=50)
            if item.get("module") == "claims" or item.get("source_module") == "claims"
        ]
        compensation = sum(
            float(item.get("expected_effect_amount") or 0) for item in claims_items
        )
        return {
            "status": status,
            "open_cases_count": len(claims_items) if status == "ok" else None,
            "draft_ready_count": 0 if status == "ok" else None,
            "submitted_count": 0 if status == "ok" else None,
            "potential_compensation_amount": compensation if compensation > 0 else None,
            "message": health.message or health.detail,
            "warnings": list(health.warnings or []),
        }

    def _date_range(
        self,
        *,
        date_from: date | None,
        date_to: date | None,
        money_summary: dict[str, Any] | None,
    ) -> dict[str, Any]:
        reconciliation = (money_summary or {}).get("finance_reconciliation") or {}
        return {
            "date_from": date_from,
            "date_to": date_to,
            "closed_finance_date_to": reconciliation.get("closed_finance_date_to"),
            "closed_finance_period_label": reconciliation.get(
                "closed_finance_period_label"
            ),
        }

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
            record_unavailable_source(value)
        return result

    def _money_actions(self, items: list[Any]) -> list[PortalActionRead]:
        actions = [
            self._money_action(item)
            for item in items
            if not self._is_system_handled_money_action(item)
        ]
        return [
            action
            for action in actions
            if not self._is_hidden_action_center_item(action)
        ]

    @staticmethod
    def _is_system_handled_money_action(item: Any) -> bool:
        raw = (
            item
            if isinstance(item, dict)
            else getattr(item, "model_dump", lambda **_: {})()
        )
        action_type = (
            str(raw.get("action_type") or getattr(item, "action_type", "") or "")
            .strip()
            .upper()
        )
        category = (
            str(raw.get("category") or getattr(item, "category", "") or "")
            .strip()
            .lower()
        )
        return (
            action_type in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}
            or category == "finance_reconcile"
        )

    def _unified_action_rows(self, rows: list[UnifiedAction]) -> list[PortalActionRead]:
        return [self._unified_action_row(row) for row in rows]

    def _unified_action_row(self, row: UnifiedAction) -> PortalActionRead:
        payload = dict(row.payload_json or {})
        linked_entity = (
            payload.get("linked_entity")
            if isinstance(payload.get("linked_entity"), dict)
            else {}
        )
        guided_fix = dict(row.guided_fix_json or {}) or self._guided_fix(
            source_module=row.source_module,
            action_type=row.action_type,
            nm_id=row.nm_id,
            target_id=row.source_id or str(row.id),
        )
        expected = self._optional_float(
            payload.get("expected_effect_amount")
            or payload.get("expected_impact_amount")
        )
        priority = str(row.priority or "P3").upper()
        source_sync_state = str(payload.get("source_sync_state") or "unknown")
        if source_sync_state not in {
            "source_updated",
            "shadow_only",
            "shadow_updated",
            "unknown",
        }:
            source_sync_state = "unknown"
        return PortalActionRead(
            id=f"unified:{row.id}",
            action_id=row.id,
            source="unified_actions",
            source_module=self._normalize_source_module(row.source_module),
            source_id=row.source_id or str(row.id),
            account_id=row.account_id,
            nm_id=row.nm_id,
            sku_id=self._optional_int(
                payload.get("sku_id") or linked_entity.get("sku_id")
            ),
            action_type=str(row.action_type or ""),
            title=str(row.title or "Действие"),
            priority=priority if priority in {"P0", "P1", "P2", "P3", "P4"} else "P3",
            severity=self._severity_from_priority(priority),
            status=self._normalize_status(row.status),
            reason=str(row.summary or payload.get("reason") or ""),
            next_step=str(payload.get("next_step") or guided_fix.get("label") or ""),
            expected_effect_amount=expected,
            priority_score=self._priority_score(priority, expected),
            confidence=self._normalize_confidence(payload.get("confidence")),
            assigned_to_user_id=getattr(row, "assigned_to_user_id", None)
            or payload.get("assigned_to_user_id"),
            deadline_at=getattr(row, "deadline_at", None)
            or self._optional_datetime(payload.get("deadline_at")),
            review_status=self._normalize_review_status(
                getattr(row, "review_status", None) or payload.get("review_status")
            ),
            last_comment=getattr(row, "last_comment", None)
            or payload.get("last_comment"),
            last_status_changed_at=self._optional_datetime(
                payload.get("last_status_changed_at") or payload.get("last_changed_at")
            ),
            last_actor_user_id=self._optional_int(
                payload.get("last_actor_user_id")
                or payload.get("last_changed_by_user_id")
            ),
            status_reason=str(
                payload.get("status_reason") or payload.get("dismiss_reason")
            )
            if (payload.get("status_reason") or payload.get("dismiss_reason"))
            is not None
            else None,
            closed_at=getattr(row, "closed_at", None)
            or self._optional_datetime(payload.get("closed_at")),
            dismissed_at=getattr(row, "dismissed_at", None)
            or self._optional_datetime(payload.get("dismissed_at")),
            linked_entity=linked_entity,
            guided_fix=guided_fix,
            payload=payload,
            raw=payload,
            can_update_status=True,
            can_update=True,
            can_update_reason=payload.get("can_update_reason"),
            source_sync_state=source_sync_state,  # type: ignore[arg-type]
            source_references=payload.get("source_references")
            if isinstance(payload.get("source_references"), list)
            else [],
            recheck_rule=payload.get("recheck_rule")
            if isinstance(payload.get("recheck_rule"), str)
            else None,
            impact_type=payload.get("impact_type")
            if isinstance(payload.get("impact_type"), str)
            else None,
            trust_state=str(
                payload.get("trust_state") or row.trust_state or "provisional"
            ),
        )

    def _action_status_value(
        self, action: PortalActionRead | UnifiedActionOut
    ) -> str | None:
        raw = self._dump(action)
        value = raw.get("status")
        return self._normalize_status(value) if value else None

    def _apply_unified_action_task_fields(
        self,
        row: UnifiedAction,
        *,
        status: str,
        comment: str | None = None,
        status_reason: str | None = None,
        assigned_to_user_id: int | None = None,
        deadline_at: Any = None,
        review_status: str | None = None,
        user_id: int | None = None,
    ) -> None:
        payload_json = dict(row.payload_json or {})
        if comment:
            row.last_comment = comment
            payload_json["last_comment"] = comment
        if assigned_to_user_id is not None:
            row.assigned_to_user_id = int(assigned_to_user_id)
            payload_json["assigned_to_user_id"] = int(assigned_to_user_id)
        if deadline_at is not None:
            row.deadline_at = self._optional_datetime(deadline_at)
            payload_json["deadline_at"] = (
                row.deadline_at.isoformat() if row.deadline_at is not None else None
            )
        row.review_status = self._normalize_review_status(
            review_status or self._review_status_for_action_status(status)
        )
        payload_json["review_status"] = row.review_status
        now = utcnow()
        if status in {"done", "resolved"}:
            row.closed_at = row.closed_at or now
            row.dismissed_at = None
            payload_json["closed_at"] = row.closed_at.isoformat()
            payload_json.pop("dismissed_at", None)
            payload_json.pop("dismiss_reason", None)
        elif status in {"ignored", "dismissed"}:
            row.dismissed_at = row.dismissed_at or now
            row.closed_at = None
            payload_json["dismissed_at"] = row.dismissed_at.isoformat()
            if comment:
                payload_json["dismiss_reason"] = comment
            payload_json.pop("closed_at", None)
        else:
            row.closed_at = None
            row.dismissed_at = None
            payload_json.pop("closed_at", None)
            payload_json.pop("dismissed_at", None)
            payload_json.pop("dismiss_reason", None)
        payload_json["last_actor_user_id"] = user_id
        if status_reason or comment:
            payload_json["status_reason"] = status_reason or comment
        if user_id is not None:
            payload_json["last_changed_by_user_id"] = user_id
        row.payload_json = payload_json

    def _review_status_for_action_status(self, status: str) -> str:
        normalized = self._normalize_status(status)
        if normalized in {"done", "resolved"}:
            return "closed"
        if normalized in {"ignored", "dismissed"}:
            return "dismissed"
        if normalized in {"acknowledged", "in_progress", "reopened"}:
            return "in_progress"
        if normalized in {"blocked", "postponed"}:
            return "review"
        return "new"

    def _normalize_review_status(self, value: Any) -> str:
        normalized = str(value or "new").strip().lower()
        if normalized in {"closed", "done", "resolved"}:
            return "closed"
        if normalized in {"dismissed", "ignored", "cancelled", "canceled"}:
            return "dismissed"
        if normalized in {"review", "in_review"}:
            return "review"
        if normalized in {"in_progress", "progress", "working"}:
            return "in_progress"
        return "new"

    async def _persist_reputation_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        item_id: str,
        draft_type: DraftType | str | None,
        text: str,
        created_by: int | None,
        payload: dict[str, Any] | None = None,
    ) -> DraftOut:
        kind, external_id = self.reputation_adapter._split_item_id(item_id)
        effective_type = self.reputation_adapter._draft_type(kind, draft_type)
        source_id = f"reputation:{kind}:{external_id}:draft"
        existing = None
        try:
            existing = (
                (
                    await session.execute(
                        select(OperatorDraft)
                        .where(
                            OperatorDraft.account_id == account_id,
                            OperatorDraft.source_module == "reputation",
                            OperatorDraft.source_id == source_id,
                        )
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
        except Exception:
            existing = None
        row = existing or OperatorDraft(
            account_id=account_id,
            source_module="reputation",
            source_id=source_id,
            external_id=item_id,
            draft_type=effective_type.value
            if hasattr(effective_type, "value")
            else str(effective_type),
        )
        row.status = ActionStatus.NEW.value
        row.external_status = ExternalStatus.DRAFT_READY.value
        row.title = "Reply draft"
        row.body_text = text
        row.payload_json = {
            **dict(payload or {}),
            "source_type": kind,
            "source_id": external_id,
            "item_id": item_id,
            "created_by": created_by,
            "local_only": True,
            "external_submit_attempted": False,
            "marketplace_change": False,
        }
        if existing is None:
            session.add(row)
        await session.flush()
        return DraftOut(
            id=str(row.id) if row.id is not None else source_id,
            draft_type=effective_type,
            external_status=ExternalStatus.DRAFT_READY,
            account_id=account_id,
            source_type=kind,
            source_id=external_id,
            title=row.title or "Reply draft",
            text=text,
            status=ActionStatus.NEW,
            trust_state=TrustState.PROVISIONAL,
            requires_confirmation=True,
            created_by=created_by,
            data=row.payload_json,
        )

    def _action_priority_value(
        self, action: PortalActionRead | UnifiedActionOut
    ) -> str:
        raw = self._dump(action)
        priority = str(raw.get("priority") or "P3").upper()
        return priority if priority in {"P0", "P1", "P2", "P3", "P4"} else "P3"

    def _action_trust_state_value(
        self, action: PortalActionRead | UnifiedActionOut
    ) -> str:
        raw = self._dump(action)
        return str(raw.get("trust_state") or "provisional")

    def _action_title_value(self, action: PortalActionRead | UnifiedActionOut) -> str:
        raw = self._dump(action)
        return str(raw.get("title") or "Local action")

    def _action_summary_value(self, action: PortalActionRead | UnifiedActionOut) -> str:
        raw = self._dump(action)
        return str(
            raw.get("summary") or raw.get("reason") or raw.get("next_step") or ""
        )

    def _action_guided_fix_value(
        self, action: PortalActionRead | UnifiedActionOut
    ) -> dict[str, Any]:
        raw = self._dump(action)
        guided_fix = raw.get("guided_fix")
        return dict(guided_fix or {}) if isinstance(guided_fix, dict) else {}

    async def _problem_instance_actions(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        limit: int = 50,
        include_resolved: bool = False,
        include_finance_windows: bool = True,
    ) -> list[PortalActionRead]:
        statuses = (
            self.PRODUCT_PROBLEM_INSTANCE_STATUSES
            if include_resolved
            else self.ACTIVE_PROBLEM_INSTANCE_STATUSES
        )
        stmt = (
            select(ProblemInstance, ProblemDefinition)
            .outerjoin(
                ProblemDefinition,
                ProblemDefinition.id == ProblemInstance.problem_definition_id,
            )
            .where(
                ProblemInstance.account_id == account_id,
                ProblemInstance.status.in_(statuses),
            )
            .order_by(
                ProblemInstance.last_seen_at.desc(),
                ProblemInstance.id.desc(),
            )
            .limit(max(1, min(int(limit or 50), 200)))
        )
        if nm_id is not None:
            stmt = stmt.where(ProblemInstance.nm_id == nm_id)
        rows = (await session.execute(stmt)).all()
        instances: list[tuple[ProblemInstance, ProblemDefinition | None]] = []
        for row in rows:
            try:
                instance = row[0]
                definition = row[1] if len(row) > 1 else None
            except (TypeError, IndexError, KeyError):
                instance = getattr(row, "ProblemInstance", None)
                definition = getattr(row, "ProblemDefinition", None)
            if isinstance(instance, ProblemInstance):
                instances.append(
                    (
                        instance,
                        definition
                        if isinstance(definition, ProblemDefinition)
                        else None,
                    )
                )
        duplicate_data_fix_nms = {
            int(instance.nm_id)
            for instance, _definition in instances
            if instance.nm_id is not None
            and str(instance.problem_code or "").strip().lower()
            == "missing_cost_blocks_profit"
            and str(instance.source_module or "").strip().lower() == "data_quality"
        }
        dynamic_missing_cost_nms: set[int] = set()
        if duplicate_data_fix_nms:
            dynamic_rows = (
                (
                    await session.execute(
                        select(ProblemInstance.nm_id)
                        .where(
                            ProblemInstance.account_id == account_id,
                            ProblemInstance.problem_code
                            == "missing_cost_blocks_profit",
                            ProblemInstance.source_module != "data_quality",
                            ProblemInstance.status.in_(statuses),
                            ProblemInstance.nm_id.in_(duplicate_data_fix_nms),
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            dynamic_missing_cost_nms = {
                int(value) for value in dynamic_rows if value is not None
            }
        history_by_id = await self._problem_instance_history_by_ids(
            session,
            [
                instance.id
                for instance, _definition in instances
                if instance.id is not None
            ],
            limit_per_problem=12 if not include_finance_windows else None,
        )
        actions: list[PortalActionRead] = []
        for instance, definition in instances:
            if self._hide_data_fix_duplicate_problem_instance(
                instance, dynamic_missing_cost_nms
            ):
                continue
            if self._hide_problem_instance_from_action_center(instance):
                continue
            history_rows = history_by_id.get(int(instance.id), [])
            result_summary = (
                await self._problem_instance_result_summary(
                    session,
                    account_id=account_id,
                    instance=instance,
                    history_rows=history_rows,
                )
                if include_finance_windows
                else None
            )
            actions.append(
                self._problem_instance_action(
                    instance,
                    definition=definition,
                    history_rows=history_rows,
                    result_summary=result_summary,
                )
            )
        return actions

    async def _problem_instance_history_by_ids(
        self,
        session: AsyncSession,
        problem_instance_ids: list[int],
        *,
        limit_per_problem: int | None = None,
    ) -> dict[int, list[ProblemInstanceHistory]]:
        if not problem_instance_ids:
            return {}
        if limit_per_problem is not None:
            limit_per_problem = max(int(limit_per_problem or 0), 1)
        try:
            if limit_per_problem is None:
                stmt = (
                    select(ProblemInstanceHistory)
                    .where(
                        ProblemInstanceHistory.problem_instance_id.in_(
                            problem_instance_ids
                        )
                    )
                    .order_by(
                        ProblemInstanceHistory.created_at.asc(),
                        ProblemInstanceHistory.id.asc(),
                    )
                )
            else:
                ranked = (
                    select(
                        ProblemInstanceHistory,
                        func.row_number()
                        .over(
                            partition_by=ProblemInstanceHistory.problem_instance_id,
                            order_by=(
                                ProblemInstanceHistory.created_at.desc(),
                                ProblemInstanceHistory.id.desc(),
                            ),
                        )
                        .label("row_number"),
                    )
                    .where(
                        ProblemInstanceHistory.problem_instance_id.in_(
                            problem_instance_ids
                        )
                    )
                    .subquery()
                )
                history_alias = aliased(ProblemInstanceHistory, ranked)
                stmt = (
                    select(history_alias)
                    .where(ranked.c.row_number <= limit_per_problem)
                    .order_by(
                        history_alias.problem_instance_id.asc(),
                        history_alias.created_at.asc(),
                        history_alias.id.asc(),
                    )
                )
            result = await session.execute(stmt)
        except Exception:
            return {}
        grouped: dict[int, list[ProblemInstanceHistory]] = {}
        for row in result.scalars():
            grouped.setdefault(int(row.problem_instance_id), []).append(row)
        return grouped

    async def _problem_instance_result_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        instance: ProblemInstance,
        history_rows: list[ProblemInstanceHistory],
    ) -> dict[str, Any]:
        anchor = self._problem_result_anchor(instance, history_rows)
        finance_windows: dict[str, Any] = {}
        if instance.nm_id is not None and str(instance.status or "") in {
            "in_progress",
            "done",
            "resolved",
        }:
            for window_days in (7, 14):
                try:
                    finance_windows[
                        f"{window_days}d"
                    ] = await self.result_tracking.finance_window_summary(
                        session,
                        account_id=account_id,
                        nm_id=int(instance.nm_id),
                        window_days=window_days,
                        action_at=anchor.date() if anchor is not None else None,
                    )
                except Exception as exc:
                    finance_windows[f"{window_days}d"] = {
                        "window_days": window_days,
                        "status": "not_enough_data",
                        "comparison": "not_enough_data",
                        "metrics": {},
                        "explanation": f"Финансовое сравнение недоступно: {exc.__class__.__name__}",
                        "confidence": "low",
                        "calculation_note": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
                        "disclaimer": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
                    }
        return {
            "status_flow": self._problem_status_flow(instance, history_rows),
            "before_snapshot": self._problem_before_snapshot(instance),
            "current_snapshot": self._problem_current_snapshot(instance),
            "status_history": self._problem_instance_status_history(
                instance, history_rows
            ),
            "finance_windows": finance_windows,
            "money_at_risk": {
                "before": self._optional_float(instance.money_impact_amount),
                "after": None,
                "delta": None,
                "currency": instance.money_impact_currency or "RUB",
                "note": "Ожидаемый эффект не считается сэкономленными деньгами, пока нет измеренных данных после действия.",
            },
            "calculation_note": "Окна «до/после» показывают корреляцию, но не доказывают причинность.",
            "disclaimer": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
        }

    def _hide_problem_instance_from_action_center(
        self, instance: ProblemInstance
    ) -> bool:
        if self._hide_price_safe_negative_profit(instance):
            return True
        ledger = dict(instance.evidence_ledger_json or {})
        if not ledger.get("data_fix") and not str(
            ledger.get("formula_id") or ""
        ).startswith("data_quality_issue:"):
            return False
        input_facts = (
            ledger.get("input_facts")
            if isinstance(ledger.get("input_facts"), list)
            else []
        )
        for fact in input_facts:
            if not isinstance(fact, dict):
                continue
            sample_rows = (
                fact.get("sample_rows")
                if isinstance(fact.get("sample_rows"), list)
                else []
            )
            for row in sample_rows:
                if not isinstance(row, dict):
                    continue
                code = str(row.get("code") or instance.problem_code or "")
                source_domains = row.get("sourceDomains")
                if isinstance(source_domains, str):
                    try:
                        parsed = ast.literal_eval(source_domains)
                        source_domains = (
                            parsed if isinstance(parsed, list) else [source_domains]
                        )
                    except (SyntaxError, ValueError):
                        source_domains = [source_domains]
                payload = {
                    "sourceKind": row.get("sourceKind"),
                    "sourceDomains": source_domains,
                    "classificationReason": row.get("classificationReason"),
                    "classificationStatus": row.get("classificationStatus"),
                    "resolutionStatus": row.get("resolutionStatus"),
                }
                raw = {
                    "classification_status": row.get("classificationStatus"),
                    "classification_reason": row.get("classificationReason"),
                }
                if self._hide_dq_issue_from_action_center(code, raw, payload):
                    return True
        return False

    @staticmethod
    def _hide_price_safe_negative_profit(instance: ProblemInstance) -> bool:
        if str(instance.problem_code or "").strip().lower() != "negative_unit_profit":
            return False
        snapshot = dict(instance.calculation_snapshot_json or {})
        price_safety = snapshot.get("price_safety")
        if not isinstance(price_safety, dict):
            return False
        status = str(price_safety.get("status") or "").strip().lower()
        return (
            status == "price_ok"
            and price_safety.get("can_recommend_price_increase") is not True
        )

    @staticmethod
    def _hide_data_fix_duplicate_problem_instance(
        instance: ProblemInstance, dynamic_missing_cost_nms: set[int]
    ) -> bool:
        if (
            str(instance.problem_code or "").strip().lower()
            != "missing_cost_blocks_profit"
        ):
            return False
        if str(instance.source_module or "").strip().lower() != "data_quality":
            return False
        if instance.nm_id is None:
            return False
        return int(instance.nm_id) in dynamic_missing_cost_nms

    def _problem_instance_action(
        self,
        row: ProblemInstance,
        *,
        definition: ProblemDefinition | None = None,
        history_rows: list[ProblemInstanceHistory] | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> PortalActionRead:
        ledger = dict(row.evidence_ledger_json or {})
        source_refs = (
            ledger.get("source_references")
            if isinstance(ledger.get("source_references"), list)
            else []
        )
        category = str(
            getattr(definition, "category", "")
            or self._problem_category_from_code(row.problem_code)
        )
        snapshot = dict(row.calculation_snapshot_json or {})
        snapshot_allowed_actions = (
            snapshot.get("allowed_actions")
            if isinstance(snapshot.get("allowed_actions"), list)
            else None
        )
        allowed_actions = (
            [str(item) for item in snapshot_allowed_actions if str(item).strip()]
            if snapshot_allowed_actions is not None
            else self._problem_definition_allowed_actions(definition)
        )
        action_state = (
            dict(snapshot.get("action_center") or {})
            if isinstance(snapshot.get("action_center"), dict)
            else {}
        )
        price_safety = (
            snapshot.get("price_safety")
            if isinstance(snapshot.get("price_safety"), dict)
            else None
        )
        data_freshness = (
            snapshot.get("data_freshness")
            if isinstance(snapshot.get("data_freshness"), dict)
            else None
        )
        status_history = self._problem_instance_status_history(row, history_rows or [])
        solve_map = build_action_center_solve_map(
            problem_code=row.problem_code,
            allowed_actions=allowed_actions,
            nm_id=row.nm_id,
            problem_instance_id=row.id,
            data_freshness=data_freshness,
            price_safety=price_safety,
        )
        if solve_map is None:
            solve_map_template = snapshot.get("solve_map_template")
            solve_map = build_action_center_solve_map_from_template(
                template=solve_map_template
                if isinstance(solve_map_template, dict)
                else None,
                allowed_actions=allowed_actions,
                nm_id=row.nm_id,
                problem_instance_id=row.id,
                data_freshness=data_freshness,
                price_safety=price_safety,
            )
        payload = {
            "problem_instance_id": row.id,
            "problem_code": row.problem_code,
            "detector_code": row.problem_code,
            "problem_definition_id": row.problem_definition_id,
            "rule_version_id": row.rule_version_id,
            "category": category,
            "dedup_key": row.dedup_key,
            "impact_type": row.impact_type,
            "money_impact_amount": self._optional_float(row.money_impact_amount),
            "trust_state": row.trust_state,
            "confidence": row.confidence,
            "allowed_actions": allowed_actions,
            "source_references": source_refs,
            "evidence_ledger": ledger,
            "price_safety": price_safety,
            "data_freshness": data_freshness,
            "solve_map": solve_map.model_dump(mode="json")
            if solve_map is not None
            else None,
            "vendor_code": row.vendor_code,
            "source_sync_state": "source_updated",
            "status_history": status_history,
            "result_summary": result_summary
            or {
                "status_flow": self._problem_status_flow(row, history_rows or []),
                "before_snapshot": self._problem_before_snapshot(row),
                "current_snapshot": self._problem_current_snapshot(row),
                "status_history": status_history,
                "finance_windows": {},
                "money_at_risk": {
                    "before": self._optional_float(row.money_impact_amount),
                    "after": None,
                    "delta": None,
                    "currency": row.money_impact_currency or "RUB",
                },
                "calculation_note": "Окна «до/после» показывают корреляцию, но не доказывают причинность.",
                "disclaimer": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
            },
        }
        status = self._normalize_status(row.status)
        priority = self._priority_from_problem_instance(row)
        return PortalActionRead(
            id=f"problem_engine:{row.id}",
            source="dynamic_problem_instances",
            source_module="problem_engine",
            source_id=str(row.id),
            account_id=row.account_id,
            nm_id=row.nm_id,
            action_type=row.problem_code,
            detector_code=row.problem_code,
            title=row.title,
            priority=priority,
            severity=self._severity_from_priority(priority)
            if row.severity not in {"critical", "high", "medium", "low"}
            else row.severity,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
            reason=row.explanation,
            next_step=row.recommendation,
            expected_effect_amount=self._optional_float(row.money_impact_amount),
            priority_score=self._priority_score(
                priority, self._optional_float(row.money_impact_amount)
            ),
            confidence=self._confidence_from_problem_trust(
                row.trust_state, row.confidence
            ),
            created_at=self._optional_datetime(
                getattr(row, "created_at", None) or row.first_seen_at
            ),
            assigned_to_user_id=self._optional_int(
                action_state.get("assigned_to_user_id")
            ),
            deadline_at=self._optional_datetime(action_state.get("deadline_at")),
            review_status=str(action_state.get("review_status") or "new"),  # type: ignore[arg-type]
            last_comment=str(action_state.get("last_comment"))
            if action_state.get("last_comment") is not None
            else None,
            last_status_changed_at=self._optional_datetime(
                action_state.get("last_status_changed_at")
                or action_state.get("last_changed_at")
            ),
            last_actor_user_id=self._optional_int(
                action_state.get("last_actor_user_id")
                or action_state.get("last_changed_by_user_id")
            ),
            status_reason=str(
                action_state.get("status_reason") or action_state.get("dismiss_reason")
            )
            if (action_state.get("status_reason") or action_state.get("dismiss_reason"))
            is not None
            else None,
            closed_at=self._optional_datetime(row.resolved_at),
            dismissed_at=self._optional_datetime(row.dismissed_at),
            linked_entity={
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "vendor_code": row.vendor_code,
            },
            payload=payload,
            raw={
                **payload,
                "title": row.title,
                "explanation": row.explanation,
                "recommendation": row.recommendation,
                "status": row.status,
                "category": category,
                "calculation_snapshot": row.calculation_snapshot_json,
            },
            can_update_status=True,
            can_update=True,
            can_update_reason=None,
            source_references=source_refs,
            recheck_rule=ledger.get("recheck_rule_human")
            if isinstance(ledger.get("recheck_rule_human"), str)
            else None,
            impact_type=row.impact_type,
            trust_state=row.trust_state,
            source_sync_state="source_updated",
            evidence_ledger=ledger,
            solve_map=solve_map,
            allowed_actions=allowed_actions,
        )

    def _problem_instance_status_history(
        self,
        row: ProblemInstance,
        history_rows: list[ProblemInstanceHistory],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = [
            {
                "event_type": "first_seen",
                "status": "new",
                "new_status": "new",
                "comment": "Problem was first detected.",
                "created_at": row.first_seen_at.isoformat()
                if row.first_seen_at is not None
                else None,
            }
        ]
        for event in history_rows:
            old_value = dict(event.old_value_json or {})
            new_value = dict(event.new_value_json or {})
            status = (
                new_value.get("status")
                or new_value.get("review_status")
                or event.event_type
            )
            items.append(
                {
                    "event_type": event.event_type,
                    "status": status,
                    "old_status": old_value.get("status"),
                    "new_status": new_value.get("status"),
                    "old_value": old_value,
                    "new_value": new_value,
                    "comment": event.comment,
                    "actor_user_id": event.actor_user_id,
                    "created_at": event.created_at.isoformat()
                    if event.created_at is not None
                    else None,
                }
            )
        current_status = self._normalize_status(row.status)
        if not items or items[-1].get("status") != current_status:
            items.append(
                {
                    "event_type": "current_status",
                    "status": current_status,
                    "new_status": current_status,
                    "comment": "Current problem status.",
                    "created_at": row.updated_at.isoformat()
                    if getattr(row, "updated_at", None) is not None
                    else None,
                }
            )
        return items[-12:]

    def _problem_status_flow(
        self,
        row: ProblemInstance,
        history_rows: list[ProblemInstanceHistory],
    ) -> dict[str, Any]:
        first_change = next(
            (
                event
                for event in history_rows
                if event.event_type in {"status_change", "status_changed"}
            ),
            None,
        )
        initial_status = "new"
        if first_change is not None and isinstance(first_change.old_value_json, dict):
            initial_status = str(
                first_change.old_value_json.get("status") or initial_status
            )
        current_status = self._normalize_status(row.status)
        started = next(
            (
                event.created_at
                for event in history_rows
                if isinstance(event.new_value_json, dict)
                and str(event.new_value_json.get("status") or "")
                in {"in_progress", "done"}
            ),
            None,
        )
        completed = row.resolved_at or next(
            (
                event.created_at
                for event in reversed(history_rows)
                if isinstance(event.new_value_json, dict)
                and str(event.new_value_json.get("status") or "")
                in {"done", "resolved"}
            ),
            None,
        )
        return {
            "initial_status": initial_status,
            "current_status": current_status,
            "changed": initial_status != current_status,
            "started_at": started.isoformat() if started is not None else None,
            "completed_at": completed.isoformat() if completed is not None else None,
            "first_seen_at": row.first_seen_at.isoformat()
            if row.first_seen_at is not None
            else None,
            "last_seen_at": row.last_seen_at.isoformat()
            if row.last_seen_at is not None
            else None,
        }

    def _problem_before_snapshot(self, row: ProblemInstance) -> dict[str, Any]:
        ledger = dict(row.evidence_ledger_json or {})
        facts: dict[str, Any] = {}
        raw_facts = ledger.get("input_facts")
        if isinstance(raw_facts, list):
            for fact in raw_facts:
                if not isinstance(fact, dict):
                    continue
                code = str(fact.get("metric_code") or fact.get("label") or "").strip()
                if code:
                    facts[code] = fact.get("value")
        return {
            "status": "new",
            "money_impact_amount": self._optional_float(row.money_impact_amount),
            "money_impact_currency": row.money_impact_currency or "RUB",
            "impact_type": row.impact_type,
            "trust_state": row.trust_state,
            "severity": row.severity,
            "metrics": facts,
            "first_seen_at": row.first_seen_at.isoformat()
            if row.first_seen_at is not None
            else None,
        }

    def _problem_current_snapshot(self, row: ProblemInstance) -> dict[str, Any]:
        return {
            "status": self._normalize_status(row.status),
            "money_impact_amount": self._optional_float(row.money_impact_amount),
            "money_impact_currency": row.money_impact_currency or "RUB",
            "impact_type": row.impact_type,
            "trust_state": row.trust_state,
            "severity": row.severity,
            "last_seen_at": row.last_seen_at.isoformat()
            if row.last_seen_at is not None
            else None,
            "resolved_at": row.resolved_at.isoformat()
            if row.resolved_at is not None
            else None,
            "dismissed_at": row.dismissed_at.isoformat()
            if row.dismissed_at is not None
            else None,
        }

    def _problem_result_anchor(
        self,
        row: ProblemInstance,
        history_rows: list[ProblemInstanceHistory],
    ):
        for event in history_rows:
            if not isinstance(event.new_value_json, dict):
                continue
            if str(event.new_value_json.get("status") or "") in {
                "in_progress",
                "done",
                "resolved",
            }:
                return event.created_at
        return row.resolved_at or row.first_seen_at

    def _problem_definition_allowed_actions(
        self, definition: ProblemDefinition | None
    ) -> list[str]:
        raw = getattr(definition, "allowed_actions_json", None)
        if not isinstance(raw, list):
            return []
        return [str(item) for item in raw if str(item).strip()]

    def _product360_href(self, path: str, **params: Any) -> str:
        clean = {
            key: value
            for key, value in params.items()
            if value is not None and str(value).strip()
        }
        if not clean:
            return path
        separator = "&" if "?" in path else "?"
        return f"{path}{separator}{urlencode(clean)}"

    def _product360_positive_int(self, *values: Any) -> int | None:
        for value in values:
            if value is None:
                continue
            token = str(value).strip().rsplit(":", 1)[-1]
            try:
                parsed = int(token)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                return parsed
        return None

    def _product360_problem_instance_id(self, action: PortalActionRead) -> int | None:
        payload = action.payload or {}
        raw = action.raw or {}
        values: list[Any] = [
            payload.get("problem_instance_id"),
            raw.get("problem_instance_id"),
        ]
        if self._normalize_source_module(action.source_module) == "problem_engine":
            values.extend([action.source_id, action.id])
        return self._product360_positive_int(*values)

    def _product360_problem_code(self, action: PortalActionRead) -> str:
        payload = action.payload or {}
        raw = action.raw or {}
        return str(
            payload.get("problem_code")
            or payload.get("detector_code")
            or raw.get("problem_code")
            or raw.get("issue_code")
            or action.detector_code
            or action.action_type
            or "unknown_problem"
        )

    def _product360_action_center_href(self, action: PortalActionRead) -> str:
        problem_instance_id = self._product360_problem_instance_id(action)
        if problem_instance_id is not None:
            return self._product360_href(
                "/action-center",
                problem_instance_id=problem_instance_id,
                nm_id=action.nm_id,
            )
        return self._product360_href(
            "/action-center",
            source_module=action.source_module,
            source_id=action.source_id,
            nm_id=action.nm_id,
        )

    def _product360_results_href(self, action: PortalActionRead) -> str:
        problem_instance_id = self._product360_problem_instance_id(action)
        if problem_instance_id is not None:
            return self._product360_href(
                "/results", problem_instance_id=problem_instance_id, nm_id=action.nm_id
            )
        return self._product360_href(
            "/results",
            source_module=action.source_module,
            source_id=action.source_id,
            nm_id=action.nm_id,
        )

    def _product360_data_fix_href(self, action: PortalActionRead) -> str:
        return self._product360_href(
            "/data-fix",
            problem_instance_id=self._product360_problem_instance_id(action),
            nm_id=action.nm_id,
            code=self._product360_problem_code(action),
        )

    def _product360_action_evidence(self, action: PortalActionRead) -> dict[str, Any]:
        if action.evidence_ledger is not None:
            if hasattr(action.evidence_ledger, "model_dump"):
                return action.evidence_ledger.model_dump(mode="json")
            if isinstance(action.evidence_ledger, dict):
                return dict(action.evidence_ledger)
        payload = action.payload or {}
        raw = action.raw or {}
        payload_ledger = payload.get("evidence_ledger")
        raw_ledger = raw.get("evidence_ledger")
        if isinstance(payload_ledger, dict):
            return dict(payload_ledger)
        if isinstance(raw_ledger, dict):
            return dict(raw_ledger)
        return {}

    def _product360_evidence_state(
        self, action: PortalActionRead, evidence: dict[str, Any]
    ) -> str:
        missing_data = evidence.get("missing_data")
        has_missing_data = isinstance(missing_data, list) and bool(missing_data)
        if action.evidence_state == "missing_evidence" or has_missing_data:
            return "missing_data"
        if action.evidence_state == "full_evidence":
            return "ready"
        if action.evidence_state == "partial_evidence":
            return "partial"
        if action.evidence_state == "read_only_signal":
            return "read_only"
        return str(action.evidence_state or "missing_data")

    def _product360_latest_result_events_by_problem_id(
        self, history_data: dict[str, Any]
    ) -> dict[int, dict[str, Any]]:
        latest: dict[int, dict[str, Any]] = {}
        for event in history_data.get("result_events") or []:
            raw_event = self._dump(event)
            payload = (
                raw_event.get("payload")
                if isinstance(raw_event.get("payload"), dict)
                else {}
            )
            problem_instance_id = self._product360_positive_int(
                raw_event.get("problem_instance_id"),
                payload.get("problem_instance_id")
                if isinstance(payload, dict)
                else None,
            )
            if problem_instance_id is None or problem_instance_id in latest:
                continue
            latest[problem_instance_id] = jsonable_encoder(raw_event)
        return latest

    def _product360_is_checker_problem_action(self, action: PortalActionRead) -> bool:
        source_module = self._normalize_source_module(action.source_module)
        if source_module not in {"checker", "card_quality"}:
            return False
        payload = action.payload or {}
        raw = action.raw or {}
        text = " ".join(
            str(value or "")
            for value in (
                action.source,
                action.source_id,
                action.action_type,
                action.detector_code,
                action.title,
                payload.get("problem_code"),
                payload.get("issue_code"),
                payload.get("category"),
                raw.get("issue_code"),
                raw.get("category"),
            )
        ).lower()
        return (
            payload.get("content_quality_signal") is True
            or payload.get("checker_problem_bridge") is True
            or action.source in {"checker_issues", "card_quality_issues"}
            or "card_quality" in text
            or "content" in text
            or "checker" in text
        )

    def _product360_problem_actions(
        self, actions: list[PortalActionRead]
    ) -> list[PortalActionRead]:
        problem_actions: list[PortalActionRead] = []
        seen: set[tuple[str, str]] = set()
        for action in actions:
            candidate: PortalActionRead | None = None
            source_module = self._normalize_source_module(action.source_module)
            if source_module == "problem_engine":
                candidate = action
            elif self._product360_is_checker_problem_action(action):
                candidate = action
            elif (
                source_module in {"data_quality", "costs"}
                or str(action.impact_type or "").lower() == "data_blocker"
            ):
                candidate = action
            else:
                legacy_problem_code = self._legacy_dynamic_problem_code(action)
                if legacy_problem_code:
                    candidate = self._legacy_problem_fallback_action(
                        action, problem_code=legacy_problem_code
                    )
            if candidate is None:
                continue
            problem_instance_id = self._product360_problem_instance_id(candidate)
            dedupe_key = (
                str(problem_instance_id)
                if problem_instance_id is not None
                else str(candidate.id or candidate.source_id),
                self._product360_problem_code(candidate),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            problem_actions.append(candidate)
        return problem_actions

    def _product360_has_confirmed_financial_evidence(
        self,
        action: PortalActionRead,
        evidence: dict[str, Any],
    ) -> bool:
        payload = action.payload or {}
        if (
            payload.get("financial_final") is True
            or payload.get("financial_evidence_confirmed") is True
        ):
            return True
        source_refs = evidence.get("source_references")
        input_facts = evidence.get("input_facts")
        evidence_text = " ".join(
            str(value or "")
            for value in (
                evidence.get("source_table"),
                evidence.get("source_endpoint"),
                evidence.get("formula_code"),
                source_refs,
                input_facts,
            )
        ).lower()
        return any(
            token in evidence_text
            for token in (
                "finance",
                "financial",
                "realization",
                "wb_realization",
                "report",
            )
        )

    def _product360_problem_impact_type(
        self, action: PortalActionRead, evidence: dict[str, Any]
    ) -> str:
        payload = action.payload or {}
        impact_type = str(
            action.impact_type or payload.get("impact_type") or "opportunity"
        )
        if (
            self._product360_is_checker_problem_action(action)
            and impact_type == "confirmed_loss"
            and not self._product360_has_confirmed_financial_evidence(action, evidence)
        ):
            return "opportunity"
        return impact_type

    def _product360_problem_result_status(
        self,
        *,
        action: PortalActionRead,
        latest_result_event: dict[str, Any] | None,
        result_summary: dict[str, Any],
        evidence_state: str,
    ) -> str:
        if latest_result_event is not None:
            return str(
                latest_result_event.get("outcome")
                or latest_result_event.get("status")
                or "not_enough_data"
            )
        if evidence_state == "missing_data":
            return "missing_data"
        status_flow = (
            result_summary.get("status_flow")
            if isinstance(result_summary.get("status_flow"), dict)
            else {}
        )
        current_status = str(status_flow.get("current_status") or action.status or "")
        if current_status in {"done", "resolved"}:
            return "not_enough_data"
        return "pending"

    def _product360_problem_item(
        self,
        action: PortalActionRead,
        *,
        latest_result_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = action.payload or {}
        raw = action.raw or {}
        evidence = self._product360_action_evidence(action)
        evidence_state = self._product360_evidence_state(action, evidence)
        result_summary = (
            payload.get("result_summary")
            if isinstance(payload.get("result_summary"), dict)
            else {}
        )
        result_status = self._product360_problem_result_status(
            action=action,
            latest_result_event=latest_result_event,
            result_summary=result_summary,
            evidence_state=evidence_state,
        )
        problem_instance_id = self._product360_problem_instance_id(action)
        problem_code = self._product360_problem_code(action)
        action_center_href = self._product360_action_center_href(action)
        results_href = self._product360_results_href(action)
        allowed_actions = list(action.allowed_actions or [])
        item = {
            "id": problem_instance_id if problem_instance_id is not None else action.id,
            "problem_instance_id": problem_instance_id,
            "problem_code": problem_code,
            "source_module": str(
                payload.get("source_module")
                or raw.get("source_module")
                or action.source_module
            ),
            "title": action.title,
            "explanation": action.reason,
            "recommendation": action.next_step,
            "severity": action.severity,
            "status": action.status,
            "trust_state": action.trust_state,
            "impact_type": self._product360_problem_impact_type(action, evidence),
            "money_impact_amount": self._optional_float(
                payload.get("money_impact_amount")
                if payload.get("money_impact_amount") is not None
                else action.expected_impact_amount
                if action.expected_impact_amount is not None
                else action.expected_effect_amount
            ),
            "result_status": result_status,
            "evidence_ledger": evidence,
            "evidence_state": evidence_state,
            "allowed_actions": allowed_actions,
            "action_center_href": action_center_href,
            "results_href": results_href,
            "recheck_available": "recheck" in allowed_actions,
            "result_preview": {
                "status": result_status,
                "source": "result_ledger",
                "latest_event": latest_result_event,
                "summary": result_summary,
                "results_href": results_href,
            },
        }
        if self._business_issue_group_key(action) == "data_blockers":
            item["data_fix_href"] = self._product360_data_fix_href(action)
        return item

    def _product360_problem_instances(
        self,
        actions: list[PortalActionRead],
        *,
        history_data: dict[str, Any],
    ) -> list[dict[str, Any]]:
        latest_events = self._product360_latest_result_events_by_problem_id(
            history_data
        )
        return [
            self._product360_problem_item(
                action, latest_result_event=latest_events.get(problem_instance_id)
            )
            for action in self._product360_problem_actions(actions)
            if self._normalize_source_module(action.source_module) == "problem_engine"
            for problem_instance_id in [self._product360_problem_instance_id(action)]
            if problem_instance_id is not None
        ]

    def _product360_grouped_problems(
        self,
        actions: list[PortalActionRead],
        *,
        history_data: dict[str, Any],
    ) -> dict[str, Any]:
        latest_events = self._product360_latest_result_events_by_problem_id(
            history_data
        )
        groups = {
            key: {
                "key": key,
                "title": title,
                "items": [],
                "open_count": 0,
                "resolved_count": 0,
                "count": 0,
            }
            for key, title in self.PRODUCT360_PROBLEM_GROUPS.items()
        }
        for action in self._product360_problem_actions(actions):
            group_key = self._business_issue_group_key(action)
            group = groups.setdefault(
                group_key,
                {
                    "key": group_key,
                    "title": group_key.replace("_", " ").title(),
                    "items": [],
                    "open_count": 0,
                    "resolved_count": 0,
                    "count": 0,
                },
            )
            problem_instance_id = self._product360_problem_instance_id(action)
            item = self._product360_problem_item(
                action, latest_result_event=latest_events.get(problem_instance_id or -1)
            )
            is_resolved = str(item.get("status") or "").lower() in {
                "done",
                "resolved",
                "ignored",
                "dismissed",
            }
            group["items"].append(item)
            group["resolved_count" if is_resolved else "open_count"] += 1
            group["count"] += 1
        return groups

    def _product360_checker_summary(
        self, quality: PortalProductQualityRead
    ) -> dict[str, Any]:
        dumped = quality.model_dump(mode="json")
        issue_rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in (
            "issues",
            "title_issues",
            "description_issues",
            "characteristics_issues",
            "photo_video_issues",
        ):
            rows = dumped.get(key)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                issue_key = str(
                    row.get("id")
                    or row.get("code")
                    or row.get("issue_code")
                    or row.get("title")
                    or len(issue_rows)
                )
                if issue_key in seen:
                    continue
                seen.add(issue_key)
                issue_rows.append(row)
        open_issue_count = len(
            [
                row
                for row in issue_rows
                if str(row.get("status") or "new").lower()
                not in {"done", "resolved", "ignored", "dismissed", "fixed"}
            ]
        )
        if open_issue_count == 0 and not issue_rows:
            open_issue_count = int(quality.critical_issue_count or 0) + int(
                quality.warning_issue_count or 0
            )
        return {
            "score": quality.score,
            "open_issue_count": open_issue_count,
            "last_checked_at": dumped.get("analyzed_at") or dumped.get("updated_at"),
            "top_issues": issue_rows[:5],
            "checker_href": f"/checker/{quality.nm_id}",
            "status": quality.status,
        }

    def _product360_data_blockers_summary(
        self,
        grouped_problems: dict[str, Any],
        issues: list[dict[str, Any]],
        *,
        nm_id: int,
    ) -> dict[str, Any]:
        group = (
            grouped_problems.get("data_blockers")
            if isinstance(grouped_problems, dict)
            else None
        )
        group_items = list(group.get("items") or []) if isinstance(group, dict) else []
        top_blockers: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in group_items:
            code = str(item.get("problem_code") or item.get("id") or len(top_blockers))
            seen.add(code)
            top_blockers.append(
                {
                    "id": item.get("id"),
                    "problem_instance_id": item.get("problem_instance_id"),
                    "problem_code": item.get("problem_code"),
                    "title": item.get("title"),
                    "status": item.get("status"),
                    "data_fix_href": item.get("data_fix_href")
                    or self._product360_href(
                        "/data-fix",
                        problem_instance_id=item.get("problem_instance_id"),
                        nm_id=nm_id,
                        code=item.get("problem_code"),
                    ),
                }
            )
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            code = str(
                issue.get("code")
                or issue.get("issue_code")
                or issue.get("problem_code")
                or ""
            ).strip()
            if not code or code in seen:
                continue
            if not (
                issue.get("financial_final_blocker")
                or "missing" in code
                or "unclassified" in code
            ):
                continue
            seen.add(code)
            top_blockers.append(
                {
                    "id": issue.get("id"),
                    "problem_instance_id": issue.get("problem_instance_id"),
                    "problem_code": code,
                    "title": issue.get("title") or issue.get("message") or code,
                    "status": issue.get("status") or "open",
                    "data_fix_href": self._product360_href(
                        "/data-fix",
                        problem_instance_id=issue.get("problem_instance_id"),
                        nm_id=nm_id,
                        code=code,
                    ),
                }
            )
        data_fix_href = (
            top_blockers[0]["data_fix_href"]
            if top_blockers
            else self._product360_href("/data-fix", nm_id=nm_id)
        )
        return {
            "count": len(top_blockers),
            "top_blockers": top_blockers[:5],
            "data_fix_href": data_fix_href,
        }

    def _product360_product_identity(
        self,
        *,
        nm_id: int,
        detail: dict[str, Any],
        stock_block: PortalDataBlock,
        pricing_data: Any,
    ) -> dict[str, Any]:
        identity = dict(detail.get("identity") or {})
        money = dict(detail.get("money") or {})
        meta = dict(detail.get("meta") or {})
        stock = stock_block.data if isinstance(stock_block.data, dict) else {}
        pricing = pricing_data if isinstance(pricing_data, dict) else {}

        def pick(*values: Any) -> Any:
            for value in values:
                if value is not None and value != "":
                    return value
            return None

        sync_freshness = pick(
            identity.get("sync_freshness"),
            detail.get("sync_freshness"),
            detail.get("data_freshness"),
            meta.get("sync_freshness"),
            meta.get("data_freshness"),
            {"trust": detail.get("trust")} if detail.get("trust") else None,
        )
        return {
            "title": pick(
                identity.get("title"),
                identity.get("name"),
                detail.get("title"),
                detail.get("name"),
            ),
            "nm_id": self._optional_int(
                pick(identity.get("nm_id"), detail.get("nm_id"), nm_id)
            )
            or nm_id,
            "vendor_code": pick(
                identity.get("vendor_code"),
                identity.get("article"),
                detail.get("vendor_code"),
            ),
            "barcode": pick(identity.get("barcode"), detail.get("barcode")),
            "image": pick(
                identity.get("image"),
                identity.get("image_url"),
                identity.get("photo"),
                identity.get("photo_url"),
                detail.get("image"),
                detail.get("photo_url"),
            ),
            "category": pick(
                identity.get("category"),
                identity.get("subject_name"),
                identity.get("subject"),
                detail.get("category"),
            ),
            "price": self._optional_float(
                pick(
                    pricing.get("price"),
                    pricing.get("current_price"),
                    pricing.get("price_after_discount"),
                    money.get("price"),
                    detail.get("price"),
                )
            ),
            "stock": self._optional_float(
                pick(
                    stock.get("stock_qty"),
                    stock.get("quantity"),
                    stock.get("total"),
                    detail.get("stock_qty"),
                )
            ),
            "sync_freshness": sync_freshness or {},
        }

    async def _product360_card_content(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
    ) -> dict[str, Any]:
        try:
            card = (
                await session.execute(
                    select(WBProductCard).where(
                        WBProductCard.account_id == account_id,
                        WBProductCard.nm_id == nm_id,
                    )
                )
            ).scalar_one_or_none()
        except Exception as exc:
            log_optional_module_failure(
                source="product_card_content",
                reason="exception",
                account_id=account_id,
                duration_ms=0,
                error_type=type(exc).__name__,
            )
            try:
                await session.rollback()
            except Exception:
                pass
            return {}
        if card is None:
            return {}

        payload = card.payload if isinstance(card.payload, dict) else {}
        characteristics = payload.get("characteristics")
        if not isinstance(characteristics, list):
            try:
                rows = list(
                    (
                        await session.execute(
                            select(WBProductCardCharacteristic)
                            .where(
                                WBProductCardCharacteristic.account_id == account_id,
                                WBProductCardCharacteristic.product_card_id == card.id,
                            )
                            .order_by(WBProductCardCharacteristic.id)
                        )
                    ).scalars()
                )
            except Exception as exc:
                log_optional_module_failure(
                    source="product_card_characteristics",
                    reason="exception",
                    account_id=account_id,
                    duration_ms=0,
                    error_type=type(exc).__name__,
                )
                rows = []
                try:
                    await session.rollback()
                except Exception:
                    pass
            characteristics = [
                {
                    "id": row.char_id,
                    "name": row.name,
                    "value": row.value,
                }
                for row in rows
                if str(row.name or "").strip()
            ]

        description = card.description or payload.get("description")
        photos = card.photos if card.photos is not None else payload.get("photos")
        photo_url = self._first_product_photo_url(photos)
        updated_at_wb = (
            card.updated_at_wb.isoformat() if card.updated_at_wb is not None else None
        )
        created_at_wb = (
            card.created_at_wb.isoformat() if card.created_at_wb is not None else None
        )

        return jsonable_encoder(
            {
                "description": description,
                "characteristics": characteristics
                if isinstance(characteristics, list)
                else [],
                "photos": photos,
                "image": photo_url,
                "image_url": photo_url,
                "need_kiz": card.need_kiz,
                "kiz_marked": card.kiz_marked,
                "subject_id": card.subject_id,
                "updated_at_wb": updated_at_wb,
                "created_at_wb": created_at_wb,
            }
        )

    def _product360_result_preview(
        self,
        *,
        problem_instances: list[dict[str, Any]],
        result_history: dict[str, Any],
    ) -> dict[str, Any]:
        result_events = [
            jsonable_encoder(self._dump(event))
            for event in (result_history.get("result_events") or [])
        ]
        items = [
            {
                "problem_instance_id": item.get("problem_instance_id"),
                "problem_code": item.get("problem_code"),
                "status": item.get("result_status"),
                "results_href": item.get("results_href"),
                "latest_event": (item.get("result_preview") or {}).get("latest_event"),
                "summary": (item.get("result_preview") or {}).get("summary"),
            }
            for item in problem_instances
        ]
        return {
            "status": "ok" if items or result_events else "empty",
            "source": "result_ledger",
            "items": items,
            "recent_events": result_events[:5],
            "summary": result_history.get("result_summary") or {},
            "disclaimer": "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе.",
        }

    def _product360_health_summary(
        self,
        *,
        business_issues: PortalDataBlock,
        grouped_problems: dict[str, Any],
        checker_summary: dict[str, Any],
        data_blockers: dict[str, Any],
        product_identity: dict[str, Any],
        next_best_action: PortalActionRead | None,
    ) -> dict[str, Any]:
        groups = [
            group for group in grouped_problems.values() if isinstance(group, dict)
        ]
        all_items = [item for group in groups for item in group.get("items", [])]
        open_problem_count = sum(int(group.get("open_count") or 0) for group in groups)
        resolved_problem_count = sum(
            int(group.get("resolved_count") or 0) for group in groups
        )
        critical_count = sum(
            1 for item in all_items if item.get("severity") in {"critical", "high"}
        )
        status = business_issues.status
        if int(data_blockers.get("count") or 0) > 0:
            status = "blocked"
        elif critical_count > 0 and status in {"empty", "ok"}:
            status = "warning"
        return {
            "status": status,
            "open_problem_count": open_problem_count,
            "resolved_problem_count": resolved_problem_count,
            "critical_problem_count": critical_count,
            "data_blocker_count": int(data_blockers.get("count") or 0),
            "checker_score": checker_summary.get("score"),
            "checker_open_issue_count": checker_summary.get("open_issue_count"),
            "sync_freshness": product_identity.get("sync_freshness") or {},
            "next_best_action_id": next_best_action.id
            if next_best_action is not None
            else None,
        }

    def _business_issues_block(
        self,
        actions: list[PortalActionRead],
        *,
        unavailable_sources: list[str],
        allow_legacy_fallback: bool = True,
    ) -> PortalDataBlock:
        problem_actions: list[PortalActionRead] = []
        for action in actions:
            if self._normalize_source_module(action.source_module) == "problem_engine":
                problem_actions.append(action)
                continue
            if not allow_legacy_fallback or not self._show_legacy_problem_cards():
                continue
            legacy_problem_code = self._legacy_dynamic_problem_code(action)
            if legacy_problem_code:
                problem_actions.append(
                    self._legacy_problem_fallback_action(
                        action, problem_code=legacy_problem_code
                    )
                )
        groups = self._empty_business_issue_groups()
        open_items: list[dict[str, Any]] = []
        resolved_items: list[dict[str, Any]] = []
        by_severity: dict[str, int] = {}
        by_trust_state: dict[str, int] = {}
        by_impact_type: dict[str, int] = {}
        confirmed_loss_amount = 0.0
        non_confirmed_money_amount = 0.0
        probable_risk_amount = 0.0
        blocked_cash_amount = 0.0
        lost_sales_risk_amount = 0.0
        opportunity_amount = 0.0

        for action in problem_actions:
            dumped = action.model_dump(mode="json")
            raw_status = str(
                (action.raw or {}).get("status") or action.status or ""
            ).lower()
            status = raw_status or str(action.status or "").lower()
            is_resolved = status in {
                "done",
                "resolved",
                "dismissed",
            } or action.status in {"done", "ignored"}
            category_key = self._business_issue_group_key(action)
            group = groups[category_key]
            group["items"].append(dumped)
            group["resolved_count" if is_resolved else "open_count"] += 1
            (resolved_items if is_resolved else open_items).append(dumped)

            severity_key = str(action.severity or "medium").lower()
            trust_key = str(
                action.trust_state
                or (action.payload or {}).get("trust_state")
                or "provisional"
            ).lower()
            impact_key = str(
                action.impact_type
                or (action.payload or {}).get("impact_type")
                or "opportunity"
            ).lower()
            by_severity[severity_key] = by_severity.get(severity_key, 0) + 1
            by_trust_state[trust_key] = by_trust_state.get(trust_key, 0) + 1
            by_impact_type[impact_key] = by_impact_type.get(impact_key, 0) + 1
            amount = (
                self._optional_float(
                    action.expected_impact_amount
                    if action.expected_impact_amount is not None
                    else action.expected_effect_amount
                )
                or 0.0
            )
            money_trust = action.money_trust
            if (
                impact_key == "confirmed_loss"
                and money_trust is not None
                and money_trust.show_as_confirmed_money is True
                and money_trust.impact_trust_state == "confirmed"
            ):
                confirmed_loss_amount += abs(amount)
            elif impact_key in {"blocked_cash", "blocked_revenue"} and amount:
                blocked_cash_amount += abs(amount)
                non_confirmed_money_amount += abs(amount)
            elif impact_key == "lost_sales_risk" and amount:
                lost_sales_risk_amount += abs(amount)
                non_confirmed_money_amount += abs(amount)
            elif impact_key in {"opportunity", "estimated_opportunity"} and amount:
                opportunity_amount += abs(amount)
                non_confirmed_money_amount += abs(amount)
            elif impact_key in {"probable_loss", "probable_risk"} and amount:
                probable_risk_amount += abs(amount)
                non_confirmed_money_amount += abs(amount)
            elif amount:
                non_confirmed_money_amount += abs(amount)

        group_list = [
            group
            for group in groups.values()
            if group["items"] or group["key"] in self.PRODUCT360_PROBLEM_GROUPS
        ]
        for group in group_list:
            group["count"] = int(group["open_count"]) + int(group["resolved_count"])

        empty_state = self._business_issues_empty_state(
            problem_actions, unavailable_sources=unavailable_sources
        )
        status = "empty"
        if "dynamic_product_problems" in unavailable_sources:
            status = "unavailable"
        elif open_items:
            if by_impact_type.get("data_blocker") or by_trust_state.get("blocked"):
                status = "blocked"
            elif by_severity.get("critical") or by_severity.get("high"):
                status = "warning"
            else:
                status = "ok"
        elif resolved_items:
            status = "ok"

        return PortalDataBlock(
            status=status,
            data={
                "open": open_items,
                "resolved": resolved_items,
                "groups": group_list,
                "summary": {
                    "open_count": len(open_items),
                    "resolved_count": len(resolved_items),
                    "total_count": len(problem_actions),
                    "by_severity": by_severity,
                    "by_trust_state": by_trust_state,
                    "by_impact_type": by_impact_type,
                    "money_impact": {
                        "confirmed_loss_amount": confirmed_loss_amount,
                        "probable_risk_amount": probable_risk_amount,
                        "blocked_cash_amount": blocked_cash_amount,
                        "lost_sales_risk_amount": lost_sales_risk_amount,
                        "opportunity_amount": opportunity_amount,
                        "non_confirmed_money_amount": non_confirmed_money_amount,
                        "confirmed_loss_rule": "В подтверждённый убыток попадает только impact_type=confirmed_loss с impact_trust_state=confirmed и явным show_as_confirmed_money=true.",
                        "risk_rule": "Риск, оценка, возможность и подтверждённый убыток считаются отдельными корзинами.",
                    },
                },
                "empty_state": empty_state,
            },
            message=empty_state.get("message"),
        )

    def _empty_business_issue_groups(self) -> dict[str, dict[str, Any]]:
        return {
            key: {
                "key": key,
                "title": title,
                "items": [],
                "open_count": 0,
                "resolved_count": 0,
            }
            for key, title in self.PRODUCT360_PROBLEM_GROUPS.items()
        }

    def _business_issues_empty_state(
        self, actions: list[PortalActionRead], *, unavailable_sources: list[str]
    ) -> dict[str, str]:
        if "dynamic_product_problems" in unavailable_sources:
            return {
                "kind": "sync_not_completed",
                "message": "Dynamic problem data is not available yet. Refresh after sync or rule evaluation completes.",
            }
        if not actions:
            return {
                "kind": "no_issues_found",
                "message": "No dynamic business issues found for this product.",
            }
        if any(
            str(action.trust_state or "").lower() == "blocked"
            or str(action.impact_type or "").lower() == "data_blocker"
            for action in actions
        ):
            return {
                "kind": "data_missing",
                "message": "Some business issue calculations are blocked by missing data.",
            }
        return {
            "kind": "no_issues_found",
            "message": "No open dynamic business issues found for this product.",
        }

    def _business_issue_group_key(self, action: PortalActionRead) -> str:
        payload = action.payload or {}
        source_module = self._normalize_source_module(action.source_module)
        category = str(
            payload.get("category")
            or self._problem_category_from_code(action.action_type)
        ).lower()
        code = str(payload.get("problem_code") or action.action_type or "").lower()
        impact = str(action.impact_type or payload.get("impact_type") or "").lower()
        text = f"{source_module} {category} {code} {impact}"
        if "checker" in text or "card_quality" in text or "content_quality" in text:
            return "card_quality"
        if (
            "reconciliation" in text
            or "sale_without_finance" in text
            or "finance_without_sale" in text
            or impact == "system_warning"
        ):
            return "system_checks"
        if "data" in text or "missing_cost" in text or "blocker" in text:
            return "data_blockers"
        if "stock" in text or "overstock" in text or "depletion" in text:
            return "stock"
        if "price" in text or "margin" in text:
            return "price"
        if "ads" in text or "promo" in text:
            return "ads_promo"
        return "profitability"

    def _problem_category_from_code(self, problem_code: str | None) -> str:
        code = str(problem_code or "").lower()
        if "checker" in code or "card_quality" in code or "content_quality" in code:
            return "card_quality"
        if (
            "reconciliation" in code
            or "sale_without_finance" in code
            or "finance_without_sale" in code
        ):
            return "system_checks"
        if "stock" in code or "depletion" in code:
            return "stock"
        if "price" in code or "margin" in code:
            return "price"
        if "ads" in code or "promo" in code:
            return "ads_promo"
        if "missing" in code or "blocks" in code:
            return "data_quality"
        return "profitability"

    def _priority_from_problem_instance(self, row: ProblemInstance) -> str:
        if row.impact_type == "data_blocker" or row.status == "blocked":
            return "P0"
        if row.severity == "critical":
            return "P0"
        if row.severity == "high":
            return "P1"
        if row.severity == "low":
            return "P4"
        impact = abs(self._optional_float(row.money_impact_amount) or 0)
        if impact >= 100_000:
            return "P1"
        if impact >= 10_000:
            return "P2"
        return "P3"

    def _confidence_from_problem_trust(
        self, trust_state: str | None, confidence: str | None
    ) -> str:
        normalized = str(confidence or trust_state or "").strip().lower()
        if normalized in {"confirmed", "blocked"}:
            return "high"
        if normalized in {"estimated", "provisional", "opportunity", "test_only"}:
            return "medium"
        return self._normalize_confidence(normalized)

    def _prefer_dynamic_problem_actions(
        self,
        items: list[PortalActionRead],
        *,
        show_legacy_problem_cards: bool | None = None,
    ) -> list[PortalActionRead]:
        if show_legacy_problem_cards is None:
            show_legacy_problem_cards = self._show_legacy_problem_cards()
        dynamic_keys = {
            (
                item.account_id,
                item.nm_id,
                str((item.payload or {}).get("problem_code") or item.action_type),
            )
            for item in items
            if self._normalize_source_module(item.source_module) == "problem_engine"
        }
        filtered: list[PortalActionRead] = []
        for item in items:
            legacy_problem_code = self._legacy_dynamic_problem_code(item)
            if legacy_problem_code and not show_legacy_problem_cards:
                continue
            if (
                legacy_problem_code
                and (item.account_id, item.nm_id, legacy_problem_code) in dynamic_keys
            ):
                continue
            filtered.append(item)
        return filtered

    def _legacy_dynamic_problem_code(self, item: PortalActionRead) -> str | None:
        if self._normalize_source_module(item.source_module) == "problem_engine":
            return None
        raw = dict(item.raw or {})
        payload = dict(item.payload or {})
        haystack = " ".join(
            str(value or "")
            for value in (
                item.source,
                item.source_module,
                item.source_id,
                item.action_type,
                item.detector_code,
                item.title,
                item.reason,
                item.next_step,
                payload.get("code"),
                payload.get("problem_code"),
                payload.get("detector_code"),
                payload.get("raw_code"),
                payload.get("diagnosis_id"),
                payload.get("recommended_fix"),
                payload.get("category"),
                raw.get("code"),
                raw.get("issue_code"),
                raw.get("problem_code"),
                raw.get("action_type"),
                raw.get("diagnosis_type"),
                raw.get("source_id"),
                raw.get("title"),
                raw.get("reason"),
            )
        ).lower()
        for legacy_code, problem_code in self.LEGACY_DYNAMIC_PROBLEM_MAP.items():
            if legacy_code in haystack:
                return problem_code
        return None

    @classmethod
    def _is_hidden_code(cls, code: str | None) -> bool:
        return str(code or "").strip().lower() in cls.HIDDEN_ACTION_CENTER_CODES

    def _is_hidden_action_center_item(self, item: PortalActionRead) -> bool:
        payload = dict(item.payload or {})
        raw = dict(item.raw or {})
        candidates = (
            item.detector_code,
            item.action_type,
            item.source_id,
            payload.get("code"),
            payload.get("problem_code"),
            payload.get("detector_code"),
            payload.get("raw_code"),
            raw.get("code"),
            raw.get("issue_code"),
            raw.get("problem_code"),
            raw.get("action_type"),
        )
        return any(
            self._is_hidden_code(str(code)) for code in candidates if code is not None
        )

    def _legacy_problem_fallback_action(
        self, item: PortalActionRead, *, problem_code: str
    ) -> PortalActionRead:
        payload = {
            **dict(item.payload or {}),
            "problem_code": problem_code,
            "detector_code": problem_code,
            "legacy_problem_card": True,
            "legacy_source": item.source or item.source_module,
            "category": self._problem_category_from_code(problem_code),
        }
        raw = {
            **dict(item.raw or {}),
            "problem_code": problem_code,
            "legacy_problem_card": True,
            "legacy_source": item.source or item.source_module,
        }
        return item.model_copy(
            update={
                "action_type": problem_code,
                "detector_code": problem_code,
                "payload": payload,
                "raw": raw,
                "impact_type": item.impact_type or payload.get("impact_type"),
                "trust_state": item.trust_state or payload.get("trust_state"),
                "evidence_ledger": item.evidence_ledger,
            }
        )

    def _doctor_action_rows(self, doctor: Any) -> list[PortalActionRead]:
        dumped = self._dump(doctor)
        actions = dumped.get("today_plan") or dumped.get("actions") or []
        rows: list[PortalActionRead] = []
        for item in actions:
            raw = self._dump(item)
            source_module = self._normalize_source_module(
                raw.get("source_module") or raw.get("module") or "finance"
            )
            action_type = str(raw.get("action_type") or "manual_review")
            expected = self._optional_float(
                raw.get("expected_effect_amount") or raw.get("expected_impact_amount")
            )
            priority = str(raw.get("priority") or "P3").upper()
            source_id = str(
                raw.get("source_id")
                or raw.get("id")
                or f"{source_module}:{action_type}:{raw.get('nm_id') or len(rows) + 1}"
            )
            rows.append(
                PortalActionRead(
                    id=f"generated:{source_id}",
                    source="profit_doctor",
                    source_module=source_module,
                    source_id=source_id,
                    account_id=self._optional_int(raw.get("account_id")),
                    nm_id=self._optional_int(raw.get("nm_id")),
                    sku_id=self._optional_int(raw.get("sku_id")),
                    action_type=action_type,
                    title=str(raw.get("title") or "Действие"),
                    priority=priority
                    if priority in {"P0", "P1", "P2", "P3", "P4"}
                    else "P3",
                    severity=self._severity_from_priority(priority),
                    status=self._normalize_status(raw.get("status")),
                    reason=str(raw.get("reason") or raw.get("summary") or ""),
                    next_step=str(raw.get("next_step") or ""),
                    expected_effect_amount=expected,
                    priority_score=self._priority_score(priority, expected),
                    confidence=self._normalize_confidence(raw.get("confidence")),
                    guided_fix=self._guided_fix(
                        source_module=source_module,
                        action_type=action_type,
                        nm_id=self._optional_int(raw.get("nm_id")),
                        target_id=source_id,
                    ),
                    payload=self._dump(raw.get("data") or {}),
                    raw=raw,
                    can_update_status=False,
                    can_update=False,
                    can_update_reason="generated_recommendation_not_persisted",
                )
            )
        return rows

    def _money_action(self, item: Any) -> PortalActionRead:
        raw = self._dump(item)
        linked = raw.get("linked_entity") or {}
        action_id = (
            raw.get("id")
            if isinstance(raw.get("id"), int) and raw.get("id") > 0
            else None
        )
        priority = self._priority_from_finance(raw)
        severity = self._severity_from_priority(priority)
        return PortalActionRead(
            id=f"finance:{action_id}"
            if action_id is not None
            else f"finance:{raw.get('action_type', 'action')}:{raw.get('title', '')}",
            action_id=action_id,
            source="finance_actions",
            source_module="finance",
            source_id=str(action_id) if action_id is not None else None,
            account_id=self._optional_int(raw.get("account_id")),
            action_type=str(raw.get("action_type") or ""),
            title=str(raw.get("title") or raw.get("what_to_do") or "Действие"),
            priority=priority,
            severity=severity,
            status=self._normalize_status(raw.get("status")),
            reason=str(raw.get("why") or raw.get("business_reason") or ""),
            next_step=str(raw.get("next_step") or raw.get("what_to_do") or ""),
            expected_effect_amount=raw.get("expected_effect_amount"),
            confidence=self._normalize_confidence(raw.get("confidence")),
            nm_id=linked.get("nm_id") or self._first_int(raw.get("affected_nm_ids")),
            sku_id=linked.get("sku_id") or self._first_int(raw.get("affected_sku_ids")),
            created_at=self._optional_datetime(raw.get("created_at")),
            linked_entity=linked,
            payload=dict(raw.get("money_effect") or {}),
            raw=raw,
            can_update_status=action_id is not None,
        )

    def _control_action(self, item: Any) -> PortalActionRead:
        raw = self._dump(item)
        action_id = raw.get("id") if isinstance(raw.get("id"), int) else None
        priority = self._priority_from_finance(raw)
        return PortalActionRead(
            id=f"finance:{action_id}",
            action_id=action_id,
            source="finance_actions",
            source_module="finance",
            source_id=str(action_id) if action_id is not None else None,
            account_id=self._optional_int(raw.get("account_id")),
            action_type=str(raw.get("action_type") or ""),
            title=str(raw.get("title") or raw.get("what_to_do") or "Действие"),
            priority=priority,
            severity=self._severity_from_priority(priority),
            status=self._normalize_status(raw.get("status")),
            reason=str(
                raw.get("reason_short") or raw.get("reason") or raw.get("why") or ""
            ),
            next_step=str(raw.get("next_step") or ""),
            expected_effect_amount=raw.get("expected_effect_amount"),
            confidence=self._normalize_confidence(raw.get("confidence")),
            nm_id=raw.get("nm_id"),
            sku_id=raw.get("sku_id"),
            created_at=self._optional_datetime(raw.get("created_at")),
            linked_entity=raw.get("linked_entity") or {},
            payload=dict(raw.get("payload") or {}),
            raw=raw,
            can_update_status=action_id is not None,
        )

    @staticmethod
    def _data_quality_action_contract_fields(
        code: str, row: dict[str, Any], *, severity: str | None = None
    ) -> dict[str, Any]:
        payload = dict(row.get("payload") or {})
        payload.update(
            {
                key: value
                for key, value in row.items()
                if key not in {"payload", "raw"} and value is not None
            }
        )
        contract = issue_fixability_contract(
            code,
            payload,
            severity=severity or row.get("severity") or row.get("priority"),
        )
        issue_nature = str(
            row.get("issue_nature")
            or payload.get("issue_nature")
            or contract["issue_nature"]
        )
        affected_value = (
            row.get("affected_amount")
            or row.get("affectedAmount")
            or row.get("affected_revenue")
            or row.get("affectedRevenue")
            or row.get("expected_effect_amount")
        )
        has_amount = affected_value not in (None, "", 0, 0.0)
        if issue_nature == "data_blocker":
            impact_type = "data_blocker"
            trust_state = "blocked"
        elif issue_nature == "sync_waiting":
            impact_type = "system_warning"
            trust_state = (
                "stale"
                if code
                in {
                    "sales_without_stock",
                    "stocks_task_not_ready",
                    "stocks_task_failed",
                    "latest_stocks_not_completed",
                }
                else "provisional"
            )
        elif issue_nature == "system_check":
            impact_type = "system_warning"
            trust_state = "provisional"
        elif issue_nature == "business_signal":
            impact_type = (
                "blocked_cash"
                if code
                in {"stock_without_sales", "dead_stock", "overstock_slow_moving"}
                else "opportunity"
            )
            trust_state = "estimated"
        elif issue_nature == "finance_investigation":
            impact_type = "probable_loss" if has_amount else "system_warning"
            trust_state = "provisional"
        else:
            impact_type = "system_warning"
            trust_state = "provisional"
        return {
            "code": code,
            "owner_type": str(
                row.get("owner_type")
                or payload.get("owner_type")
                or contract["owner_type"]
            ),
            "fixability": str(
                row.get("fixability")
                or payload.get("fixability")
                or contract["fixability"]
            ),
            "issue_nature": issue_nature,
            "can_user_fix_inside_platform": bool(
                row.get("can_user_fix_inside_platform")
                if row.get("can_user_fix_inside_platform") is not None
                else payload.get("can_user_fix_inside_platform")
                if payload.get("can_user_fix_inside_platform") is not None
                else contract["can_user_fix_inside_platform"]
            ),
            "is_manual_edit_allowed": bool(
                row.get("is_manual_edit_allowed")
                if row.get("is_manual_edit_allowed") is not None
                else payload.get("is_manual_edit_allowed")
                if payload.get("is_manual_edit_allowed") is not None
                else contract["is_manual_edit_allowed"]
            ),
            "primary_action_code": str(
                row.get("primary_action_code")
                or payload.get("primary_action_code")
                or contract["primary_action_code"]
            ),
            "primary_action_label": str(
                row.get("primary_action_label")
                or payload.get("primary_action_label")
                or contract["primary_action_label"]
            ),
            "target_href": str(
                row.get("target_href")
                or payload.get("target_href")
                or row.get("next_screen_path")
                or contract["target_href"]
            ),
            "disabled_reason": str(
                row.get("disabled_reason")
                or payload.get("disabled_reason")
                or contract["disabled_reason"]
                or ""
            ),
            "recheck_mode": str(
                row.get("recheck_mode")
                or payload.get("recheck_mode")
                or contract["recheck_mode"]
            ),
            "seller_explanation": str(
                row.get("seller_explanation")
                or payload.get("seller_explanation")
                or contract["seller_explanation"]
            ),
            "admin_explanation": str(
                row.get("admin_explanation")
                or payload.get("admin_explanation")
                or contract["admin_explanation"]
            ),
            "impact_type": impact_type,
            "trust_state": trust_state,
        }

    def _blocker_actions(self, blockers: Any) -> list[PortalActionRead]:
        actions: list[PortalActionRead] = []
        dumped = self._dump(blockers)
        for source_name, rows in (
            ("data_blocker", dumped.get("blockers") or []),
            ("data_warning", dumped.get("warnings") or []),
        ):
            for row in rows:
                code = str(row.get("code") or row.get("title") or "blocker")
                if self._is_hidden_code(code):
                    continue
                contract_fields = self._data_quality_action_contract_fields(
                    code,
                    row,
                    severity="critical" if source_name == "data_blocker" else "warning",
                )
                payload = {**row, **contract_fields}
                is_data_blocker = contract_fields["issue_nature"] == "data_blocker"
                actions.append(
                    PortalActionRead(
                        id=f"{source_name}:{code}",
                        source=source_name,
                        source_module="data_quality",
                        source_id=code,
                        account_id=self._optional_int(
                            (dumped.get("meta") or {}).get("account_id")
                        ),
                        action_type="DATA_FIX",
                        detector_code=code,
                        title=str(row.get("title") or "Проверить данные"),
                        priority="P0" if is_data_blocker else "P2",
                        severity="critical" if is_data_blocker else "medium",
                        status="new",
                        reason=str(
                            row.get("business_impact") or row.get("simple_reason") or ""
                        ),
                        next_step=str(
                            contract_fields["primary_action_label"]
                            or row.get("first_action")
                            or row.get("wait_or_fix_hint")
                            or row.get("next_screen_label")
                            or ""
                        ),
                        expected_effect_amount=row.get("affected_amount")
                        or row.get("affected_revenue"),
                        confidence="high" if is_data_blocker else "medium",
                        impact_type=str(contract_fields["impact_type"]),
                        trust_state=str(contract_fields["trust_state"]),
                        guided_fix={
                            "label": str(contract_fields["primary_action_label"]),
                            "href": str(contract_fields["target_href"]),
                            "action_code": str(contract_fields["primary_action_code"]),
                        },
                        payload=payload,
                        raw=payload,
                    )
                )
        return actions

    @staticmethod
    def _hide_dq_issue_from_action_center(
        code: str, raw: dict[str, Any], payload: dict[str, Any]
    ) -> bool:
        classification_status = (
            str(
                raw.get("classification_status")
                or payload.get("classificationStatus")
                or payload.get("resolutionStatus")
                or ""
            )
            .strip()
            .lower()
        )
        if classification_status in {
            "archived",
            "ignored",
            "ignored_with_reason",
            "ignored_non_financial",
            "known_exception",
        }:
            return True

        if str(code or "").strip().lower() != "unmatched_sku":
            return False
        source_kind = str(payload.get("sourceKind") or "").strip().lower()
        source_domains = {
            str(item).strip().lower()
            for item in (payload.get("sourceDomains") or [])
            if str(item).strip()
        }
        classification_reason = (
            str(
                raw.get("classification_reason")
                or payload.get("classificationReason")
                or ""
            )
            .strip()
            .lower()
        )
        return (
            source_kind == "source_level"
            and source_domains == {"supplies"}
            and classification_reason in {"missing_nm_id", "source_level_missing_nm_id"}
        )

    def _dq_actions(self, issues: list[Any]) -> list[PortalActionRead]:
        actions: list[PortalActionRead] = []
        for issue in issues:
            raw = self._dump(issue)
            issue_id = raw.get("id")
            code = str(raw.get("code") or "data_quality_issue")
            if self._is_hidden_code(code):
                continue
            if not self._is_user_actionable_dq_code(code):
                continue
            meta = issue_bucket_meta(code)
            payload = dict(raw.get("payload") or {})
            if self._hide_dq_issue_from_action_center(code, raw, payload):
                continue
            is_blocker = bool(
                raw.get("effective_financial_final_blocker")
                or raw.get("financial_final_blocker")
            )
            priority = (
                "P0"
                if is_blocker
                else self._priority_from_issue(
                    code=code, severity=raw.get("severity"), payload=payload
                )
            )
            contract_fields = self._data_quality_action_contract_fields(
                code, {**raw, **payload}, severity=raw.get("severity")
            )
            is_blocker = contract_fields["issue_nature"] == "data_blocker"
            priority = "P0" if is_blocker else priority
            actions.append(
                PortalActionRead(
                    id=f"data_quality:{issue_id or code}",
                    source="dq_issues",
                    source_module="data_quality",
                    source_id=str(issue_id) if issue_id is not None else code,
                    account_id=self._optional_int(raw.get("account_id")),
                    nm_id=self._optional_int(raw.get("nm_id") or payload.get("nmId")),
                    sku_id=self._optional_int(
                        raw.get("sku_id") or payload.get("skuId")
                    ),
                    title=issue_display_message(code, raw.get("message"))
                    or str(raw.get("message") or "Проверить качество данных"),
                    reason=str(meta.get("business_impact") or raw.get("message") or ""),
                    action_type="DATA_FIX",
                    detector_code=code,
                    priority=priority,
                    severity=self._severity_from_dq(
                        raw.get("severity"), is_blocker=is_blocker
                    ),
                    confidence="high" if is_blocker else "medium",
                    expected_effect_amount=self._optional_float(
                        payload.get("affectedRevenue")
                        or payload.get("revenue")
                        or payload.get("amount")
                    ),
                    status="new",
                    created_at=self._optional_datetime(
                        raw.get("detected_at") or raw.get("created_at")
                    ),
                    impact_type=str(contract_fields["impact_type"]),
                    trust_state=str(contract_fields["trust_state"]),
                    next_step=str(contract_fields["primary_action_label"]),
                    guided_fix={
                        "label": str(contract_fields["primary_action_label"]),
                        "href": str(contract_fields["target_href"]),
                        "action_code": str(contract_fields["primary_action_code"]),
                    },
                    payload={
                        "code": code,
                        "domain": raw.get("domain"),
                        "source_table": raw.get("source_table"),
                        "recommended_fix": meta.get("recommended_fix"),
                        **contract_fields,
                        **payload,
                    },
                    raw=raw,
                )
            )
        return actions

    @staticmethod
    def _is_user_actionable_dq_code(code: str | None) -> bool:
        normalized = str(code or "").strip().lower()
        if not normalized:
            return False
        if normalized in {
            "missing_manual_cost",
            "seller_other_expense_missing",
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "manual_cost_old_fields_used",
            "manual_cost_overlap",
            "manual_cost_multiple_active_sku",
            "manual_cost_inactive_sku",
            "manual_cost_linked_to_inactive_sku",
            "unmatched_sku",
            "expense_unclassified",
            "unclassified_finance_expense",
            "ad_spend_without_sku",
            "ad_spend_without_sales",
            "ads_not_allocated_to_profitability",
            "ads_overallocated_to_profitability",
            "expense_ad_double_count_risk",
            "expense_finance_report_missing",
            "finance_without_sale",
            "missing_chrt_id",
            "order_without_sale_or_return",
            "price_zero_or_too_low",
            "price_jump",
            "sale_without_finance",
            "sales_without_stock",
            "stock_without_sales",
            "dead_stock",
        }:
            return True
        if normalized.startswith("manual_cost"):
            return True
        return False

    def _cost_actions(self, costs: list[Any]) -> list[PortalActionRead]:
        actions: list[PortalActionRead] = []
        for cost in costs:
            raw = self._dump_attrs(
                cost,
                [
                    "id",
                    "account_id",
                    "sku_id",
                    "vendor_code",
                    "nm_id",
                    "barcode",
                    "tech_size",
                    "is_ambiguous",
                    "is_placeholder",
                    "is_business_trusted",
                    "is_supplier_confirmed",
                    "comment",
                    "created_at",
                    "updated_at",
                    "cost_source",
                    "supplier",
                ],
            )
            cost_id = raw.get("id")
            is_ambiguous = bool(raw.get("is_ambiguous"))
            title = (
                "Разобрать неоднозначную себестоимость"
                if is_ambiguous
                else "Разобрать непривязанную себестоимость"
            )
            actions.append(
                PortalActionRead(
                    id=f"costs:{cost_id or raw.get('vendor_code')}",
                    source="costs_unresolved",
                    source_module="costs",
                    source_id=str(cost_id)
                    if cost_id is not None
                    else str(raw.get("vendor_code") or ""),
                    account_id=self._optional_int(raw.get("account_id")),
                    nm_id=self._optional_int(raw.get("nm_id")),
                    sku_id=self._optional_int(raw.get("sku_id")),
                    title=title,
                    reason="Себестоимость не привязана к карточке однозначно, поэтому прибыль может быть ненадежной.",
                    action_type="COST_FIX",
                    priority="P0",
                    severity="critical" if is_ambiguous else "high",
                    confidence="high",
                    status="new",
                    created_at=self._optional_datetime(raw.get("created_at")),
                    payload=raw,
                    raw=raw,
                )
            )
        return actions

    def _checker_actions_from_quality(
        self, *, account_id: int, quality: PortalProductQualityRead
    ) -> list[PortalActionRead]:
        actions: list[PortalActionRead] = []
        if quality.status != "ok":
            return actions
        for issue in quality.issues:
            if not isinstance(issue, dict):
                continue
            severity = "high" if issue.get("severity") == "critical" else "low"
            score_impact = self._optional_float(issue.get("score_impact")) or 0
            priority = (
                "P2"
                if issue.get("severity") == "critical" or score_impact >= 15
                else "P4"
            )
            source_id = (
                str(issue.get("id"))
                if issue.get("id") is not None
                else str(issue.get("code") or "")
            )
            bridge = build_checker_problem_bridge(
                issue,
                account_id=account_id,
                nm_id=quality.nm_id,
                issue_id=source_id,
            )
            payload = {
                "category": issue.get("category"),
                "code": issue.get("code"),
                "field_path": issue.get("field_path"),
                "score_impact": score_impact,
                **bridge.payload,
            }
            actions.append(
                PortalActionRead(
                    id=f"checker:{issue.get('id') or issue.get('code')}",
                    source="checker_issues",
                    source_module="checker",
                    source_id=source_id,
                    account_id=account_id,
                    nm_id=quality.nm_id,
                    action_type="CARD_QUALITY_FIX",
                    detector_code=str(issue.get("code") or "card_quality_issue"),
                    title=str(issue.get("title") or "Проверить качество карточки"),
                    reason=str(
                        issue.get("description") or issue.get("ai_reason") or ""
                    ),
                    next_step=str(
                        issue.get("suggested_value")
                        or issue.get("ai_suggested_value")
                        or "Открыть карточку и проверить рекомендацию"
                    ),
                    priority=priority,
                    severity=severity,
                    confidence="medium"
                    if issue.get("requires_human_check")
                    else "high",
                    status=self._normalize_status(issue.get("status")),
                    payload=payload,
                    evidence_ledger=bridge.evidence_ledger,
                    money_trust=bridge.money_trust,
                    trust_state=bridge.trust_state,
                    impact_type=bridge.impact_type,
                    allowed_actions=payload["allowed_actions"],
                    recheck_rule=payload["recheck_rule_human"],
                    raw=issue,
                )
            )
        return actions

    def _checker_setup_actions(
        self, *, account_id: int, module_statuses: dict[str, str]
    ) -> list[PortalActionRead]:
        if module_statuses.get("checker") != "not_configured":
            return []
        return [
            PortalActionRead(
                id=f"checker_setup:{account_id}",
                source="integration_setup",
                source_module="checker",
                source_id="connect_checker",
                account_id=account_id,
                action_type="integration_setup",
                title="Подключите Checker, чтобы видеть проблемы карточек",
                priority="P4",
                severity="low",
                status="new",
                reason="Checker не подключён, поэтому Product 360 не может показать качество карточек.",
                next_step="Откройте Settings и подключите Checker.",
                confidence="high",
                payload={
                    "integration": "checker",
                    "setup_action": "connect_checker_in_settings",
                    "product_issue": False,
                    "marketplace_change": False,
                },
            )
        ]

    def _product_row(self, item: Any) -> PortalProductRead:
        raw = self._dump(item)
        identity = raw.get("identity") or {}
        next_action_raw = raw.get("next_action")
        money = raw.get("money") or {}
        profit = money.get("profit") or {}
        ads = raw.get("ads") or money.get("ads") or {}
        stock = raw.get("stock") or {}
        data_trust = raw.get("data_trust") or raw.get("trust") or {}
        top_action = self._money_action(next_action_raw) if next_action_raw else None
        estimated_profit = self._first_present_float(
            profit.get("net_profit_after_all_expenses"),
            profit.get("after_source_ads"),
            raw.get("estimated_profit"),
            raw.get("profit"),
        )
        stock_qty = self._optional_float(
            stock.get("quantity")
            if stock.get("quantity") is not None
            else stock.get("stock_qty")
        )
        return PortalProductRead(
            nm_id=int(raw.get("nm_id") or identity.get("nm_id")),
            sku_id=identity.get("sku_id") or raw.get("sku_id"),
            title=raw.get("title") or identity.get("title"),
            name=raw.get("title") or identity.get("title"),
            vendor_code=raw.get("vendor_code") or identity.get("vendor_code"),
            article=raw.get("vendor_code") or identity.get("vendor_code"),
            photo=self._first_string(
                raw.get("photo"),
                raw.get("photo_url"),
                identity.get("photo"),
                identity.get("photo_url"),
            ),
            photo_url=self._first_string(
                raw.get("photo_url"),
                raw.get("photo"),
                identity.get("photo_url"),
                identity.get("photo"),
            ),
            brand=raw.get("brand") or identity.get("brand"),
            subject_name=raw.get("subject_name") or identity.get("subject_name"),
            revenue=self._first_present_float(money.get("revenue"), raw.get("revenue")),
            for_pay=self._first_present_float(money.get("for_pay"), raw.get("for_pay")),
            estimated_profit=estimated_profit,
            profit=estimated_profit,
            margin=self._first_present_float(
                profit.get("margin_after_ads_percent"), raw.get("margin_percent")
            ),
            ads_spend=self._optional_float(
                ads.get("spend")
                if ads.get("spend") is not None
                else ads.get("source_spend")
            ),
            stock_qty=stock_qty,
            cost_state=self._cost_state(raw),
            stock_state=self._stock_state(stock=stock, stock_qty=stock_qty),
            card_quality_state=self._module_state(
                raw.get("card_quality") or raw.get("quality")
            ),
            reputation_state=self._module_state(raw.get("reputation")),
            cases_state=self._module_state(raw.get("claims") or raw.get("cases")),
            stock_summary=stock or None,
            data_trust_state=data_trust.get("trust_state") or data_trust.get("state"),
            open_actions_count=1
            if top_action is not None and top_action.status not in {"done", "ignored"}
            else 0,
            top_action=top_action,
            status=(raw.get("business_verdict") or {}).get("status", ""),
            trust_state=(raw.get("data_trust") or raw.get("trust") or {}).get(
                "trust_state", ""
            ),
            priority_score=raw.get("priority_score"),
            money=raw.get("money"),
            stock=raw.get("stock"),
            ads=raw.get("ads"),
            next_action=top_action,
            raw=raw,
        )

    def _money_detail_block(self, dumped: dict[str, Any]) -> dict[str, Any]:
        money = dumped.get("money") or {}
        kpis = dumped.get("kpis") or {}
        waterfall = dumped.get("waterfall") or {}
        profit = (money.get("profit") or {}) if isinstance(money, dict) else {}
        return {
            "summary": {
                "revenue": self._first_present_float(
                    money.get("revenue") if isinstance(money, dict) else None,
                    kpis.get("revenue"),
                ),
                "for_pay": self._first_present_float(
                    money.get("for_pay") if isinstance(money, dict) else None,
                    kpis.get("for_pay"),
                ),
                "estimated_profit": self._first_present_float(
                    kpis.get("net_profit_after_all_expenses"),
                    profit.get("net_profit_after_all_expenses"),
                    kpis.get("profit_after_source_ads"),
                    profit.get("after_source_ads"),
                ),
                "margin_percent": self._optional_float(
                    profit.get("margin_after_ads_percent")
                ),
                "roi_percent": self._optional_float(
                    profit.get("roi_after_ads_percent")
                ),
            },
            "money": money,
            "kpis": kpis,
            "waterfall": waterfall,
            "ads": dumped.get("ads")
            or (money.get("ads") if isinstance(money, dict) else None),
            "finance": dumped.get("finance"),
            "operations": dumped.get("operations"),
            "reconciliation": dumped.get("reconciliation"),
            "stock": dumped.get("stock"),
            "article_audit": dumped.get("article_audit"),
            "answer": dumped.get("money_answer") or dumped.get("answer"),
            "profit_variants": dumped.get("profit_variants"),
        }

    @staticmethod
    def _enrich_product_detail_with_audit(
        dumped: dict[str, Any], audit: dict[str, Any]
    ) -> dict[str, Any]:
        if not audit:
            return dumped
        enriched = dict(dumped)
        money = (
            dict(enriched.get("money") or {})
            if isinstance(enriched.get("money"), dict)
            else {}
        )
        for key in ("ads", "operations", "finance", "reconciliation", "stock"):
            value = audit.get(key)
            if value is None:
                continue
            enriched[key] = value
        audit_ads = audit.get("ads")
        if isinstance(audit_ads, dict):
            existing_ads = (
                money.get("ads") if isinstance(money.get("ads"), dict) else {}
            )
            money["ads"] = {
                **existing_ads,
                **audit_ads,
                "spend": audit_ads.get(
                    "final_spend", audit_ads.get("spend", existing_ads.get("spend"))
                ),
                "source_spend": audit_ads.get(
                    "spend", existing_ads.get("source_spend")
                ),
                "raw_allocated_spend": audit_ads.get(
                    "raw_allocated_spend", existing_ads.get("raw_allocated_spend")
                ),
                "capped_allocated_spend": audit_ads.get(
                    "capped_allocated_spend", existing_ads.get("capped_allocated_spend")
                ),
                "allocated_spend": audit_ads.get(
                    "capped_allocated_spend", existing_ads.get("allocated_spend")
                ),
                "overallocated_spend": audit_ads.get(
                    "overallocated_spend", existing_ads.get("overallocated_spend")
                ),
                "unallocated_spend": audit_ads.get(
                    "unallocated_spend", existing_ads.get("unallocated_spend")
                ),
                "status": audit_ads.get(
                    "allocation_status", existing_ads.get("status")
                ),
                "allocation_status": audit_ads.get(
                    "allocation_status", existing_ads.get("allocation_status")
                ),
                "profit_allocation_status": audit_ads.get(
                    "allocation_status", existing_ads.get("profit_allocation_status")
                ),
            }
            enriched["ads"] = money["ads"]
        audit_finance = audit.get("finance")
        if isinstance(audit_finance, dict):
            for key in (
                "wb_commission",
                "payment_processing",
                "pvz_reward",
                "wb_logistics",
                "wb_logistics_rebill",
                "acceptance",
                "penalty",
                "deduction",
                "marketing_deduction",
                "loyalty",
                "other_wb_expenses",
                "total_wb_expenses",
                "commission",
                "acquiring_fee",
                "logistics",
                "paid_acceptance",
                "storage",
                "penalties",
                "deductions",
                "additional_payments",
                "expense_data_quality",
            ):
                if key in audit_finance:
                    money[key] = audit_finance[key]
        if money:
            enriched["money"] = money
        enriched["article_audit"] = audit
        return enriched

    def _product_cost_identifiers(
        self, dumped: dict[str, Any], *, fallback_nm_id: int
    ) -> dict[str, Any]:
        identity = (
            dumped.get("identity") if isinstance(dumped.get("identity"), dict) else {}
        )
        variants = (
            dumped.get("sku_breakdown")
            or dumped.get("variants")
            or dumped.get("profit_variants")
        )
        first_variant = (
            next((item for item in variants if isinstance(item, dict)), {})
            if isinstance(variants, list)
            else {}
        )
        return {
            "nm_id": self._optional_int(
                identity.get("nm_id")
                or dumped.get("nm_id")
                or first_variant.get("nm_id")
                or fallback_nm_id
            ),
            "sku_id": self._optional_int(
                identity.get("sku_id")
                or dumped.get("sku_id")
                or first_variant.get("sku_id")
            ),
            "vendor_code": self._first_string(
                identity.get("vendor_code"),
                identity.get("seller_article"),
                identity.get("article"),
                dumped.get("vendor_code"),
                dumped.get("seller_article"),
                dumped.get("article"),
                first_variant.get("vendor_code"),
                first_variant.get("seller_article"),
                first_variant.get("article"),
            ),
            "barcode": self._first_string(
                identity.get("barcode"),
                dumped.get("barcode"),
                first_variant.get("barcode"),
            ),
        }

    def _costs_detail_block(
        self, dumped: dict[str, Any], unresolved_costs: list[dict[str, Any]]
    ) -> dict[str, Any]:
        money = dumped.get("money") or {}
        cogs = money.get("cogs") if isinstance(money, dict) else None
        return {
            "cogs": cogs,
            "cost_coverage": dumped.get("cost_coverage"),
            "expense_breakdown": dumped.get("expense_breakdown"),
            "unresolved_costs": unresolved_costs,
        }

    def _history_detail_block(self, dumped: dict[str, Any]) -> dict[str, Any]:
        history_items = []
        for key in ("operations", "funnel", "finality"):
            value = dumped.get(key)
            if value:
                history_items.append({"type": key, "data": value})
        return {"items": history_items}

    def _stock_detail_block(
        self, stock_data: Any, stockops: PortalStockOpsInsightsRead
    ) -> PortalDataBlock:
        base = dict(stock_data or {}) if isinstance(stock_data, dict) else {}
        stockops_data = stockops.model_dump(mode="json")
        if stockops.status == "ok":
            return PortalDataBlock(
                status="ok",
                data={**base, "stockops": stockops_data},
                message=stockops.message,
            )
        if base:
            return PortalDataBlock(
                status="ok",
                data={**base, "stockops": stockops_data},
                message=stockops.message,
            )
        if stockops.status in {"not_configured", "empty", "disabled"}:
            return PortalDataBlock(status="empty", data={})
        if stockops.status == "unavailable":
            return PortalDataBlock(
                status=stockops.status,
                data={"stockops": stockops_data},
                message=stockops.message,
            )
        return PortalDataBlock(status="empty", data={})

    def _block(self, data: Any, *, unavailable: str) -> PortalDataBlock:
        if data is None:
            return PortalDataBlock(
                status="unavailable", data={}, message=f"{unavailable} is not available"
            )
        if data == {} or data == []:
            return PortalDataBlock(status="empty", data=data)
        return PortalDataBlock(status="ok", data=self._scrub_private_fields(data))

    def _dump(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return dict(value)

    def _dump_attrs(self, value: Any, attrs: list[str]) -> dict[str, Any]:
        dumped = (
            self._dump(value)
            if isinstance(value, dict) or hasattr(value, "model_dump")
            else {}
        )
        if dumped:
            return dumped
        return {attr: getattr(value, attr, None) for attr in attrs}

    def _scrub_private_fields(self, value: Any) -> Any:
        private_tokens = {
            "api_key",
            "authorization",
            "credential",
            "encrypted_token",
            "encryption_key",
            "headers",
            "jwt",
            "password",
            "refresh_token",
            "secret",
            "token",
            "phone",
            "email",
            "customer",
            "client",
            "buyer",
            "passport",
            "address",
            "full_name",
            "fio",
        }
        if isinstance(value, dict):
            return {
                key: self._scrub_private_fields(item)
                for key, item in value.items()
                if not any(token in str(key).lower() for token in private_tokens)
            }
        if isinstance(value, list):
            return [self._scrub_private_fields(item) for item in value]
        return value

    def _dedupe_actions(self, items: list[PortalActionRead]) -> list[PortalActionRead]:
        by_key: dict[tuple[Any, ...], PortalActionRead] = {}
        order: list[tuple[Any, ...]] = []
        for item in items:
            key = self._action_dedupe_key(item)
            current = by_key.get(key)
            if current is None:
                by_key[key] = self._with_action_source_metadata(
                    item, [self._action_source_reference(item)]
                )
                order.append(key)
                continue
            by_key[key] = self._merge_duplicate_action(current, item)
        return [by_key[key] for key in order]

    def _action_dedupe_key(self, item: PortalActionRead) -> tuple[Any, ...]:
        source_module = self._normalize_source_module(item.source_module)
        if (
            source_module == "checker"
            and str(item.source or "").strip().lower() == "card_quality_issues"
        ):
            issue_identity = str(item.source_id or item.id or "").strip()
            if issue_identity:
                return (
                    item.account_id,
                    source_module,
                    f"issue:{issue_identity}",
                )
        nm_identity = self._normalize_nm_id(item.nm_id)
        if nm_identity is None:
            nm_identity = f"source:{item.source_id or item.id}"
        return (
            item.account_id,
            source_module,
            nm_identity,
            self._normalize_action_type(item.action_type),
            self._normalize_action_root_cause(item),
        )

    def _merge_duplicate_action(
        self, current: PortalActionRead, candidate: PortalActionRead
    ) -> PortalActionRead:
        references = self._action_source_references(current)
        references.append(self._action_source_reference(candidate))
        winner = (
            candidate
            if self._duplicate_action_score(candidate)
            > self._duplicate_action_score(current)
            else current
        )
        loser = current if winner is candidate else candidate
        status_source = self._preferred_status_source(current, candidate)
        expected = self._max_optional_float(
            current.expected_effect_amount, candidate.expected_effect_amount
        )
        priority_score = (
            max(
                float(current.priority_score or 0), float(candidate.priority_score or 0)
            )
            or None
        )
        reason = self._richer_text(winner.reason, loser.reason)
        next_step = self._richer_text(winner.next_step, loser.next_step)
        payload = {
            **dict(winner.payload or {}),
            "source_references": self._dedupe_source_references(references),
            "dedupe_key": list(self._action_dedupe_key(winner)),
        }
        raw = {
            **dict(winner.raw or {}),
            "source_references": self._dedupe_source_references(references),
        }
        update: dict[str, Any] = {
            "reason": reason,
            "next_step": next_step,
            "expected_effect_amount": expected,
            "expected_impact_amount": expected,
            "priority_score": priority_score
            if priority_score is not None
            else winner.priority_score,
            "payload": payload,
            "raw": raw,
            "can_update_status": bool(
                winner.can_update_status or loser.can_update_status
            ),
            "can_update": bool(
                winner.can_update
                or loser.can_update
                or winner.can_update_status
                or loser.can_update_status
            ),
            "can_update_reason": None
            if winner.can_update
            or loser.can_update
            or winner.can_update_status
            or loser.can_update_status
            else winner.can_update_reason,
        }
        if status_source is not None:
            update.update(
                {
                    "status": status_source.status,
                    "action_id": status_source.action_id or winner.action_id,
                    "source_id": status_source.source_id or winner.source_id,
                    "external_id": status_source.external_id or winner.external_id,
                }
            )
        return winner.model_copy(update=update)

    def _duplicate_action_score(
        self, item: PortalActionRead
    ) -> tuple[int, int, float, int, int, str]:
        priority_rank = {"P0": 4, "P1": 3, "P2": 2, "P3": 1, "P4": 0}.get(
            item.priority, 0
        )
        severity_rank = {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(
            item.severity, 0
        )
        effect = abs(
            float(item.expected_effect_amount or item.expected_impact_amount or 0)
        )
        rich_text = len(str(item.reason or "").strip()) + len(
            str(item.next_step or "").strip()
        )
        persisted_status = 1 if self._has_persisted_user_status(item) else 0
        return (
            priority_rank,
            severity_rank,
            effect,
            rich_text,
            persisted_status,
            item.id,
        )

    def _preferred_status_source(
        self, *items: PortalActionRead
    ) -> PortalActionRead | None:
        candidates = [item for item in items if self._has_persisted_user_status(item)]
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda item: (item.status != "new", item.action_id or 0, item.id),
        )

    def _has_persisted_user_status(self, item: PortalActionRead) -> bool:
        payload = dict(item.payload or {})
        raw = dict(item.raw or {})
        return bool(
            payload.get("shadow_action_id")
            or raw.get("shadow_action_id")
            or payload.get("last_changed_by_user_id")
            or raw.get("last_changed_by_user_id")
            or payload.get("last_comment")
            or raw.get("last_comment")
        )

    def _action_source_reference(self, item: PortalActionRead) -> dict[str, Any]:
        return {
            "id": item.id,
            "source": item.source,
            "source_module": self._normalize_source_module(item.source_module),
            "source_id": item.source_id,
            "account_id": item.account_id,
            "nm_id": item.nm_id,
            "action_type": self._normalize_action_type(item.action_type),
            "root_cause": self._normalize_action_root_cause(item),
            "priority": item.priority,
            "severity": item.severity,
            "status": item.status,
        }

    def _action_source_references(self, item: PortalActionRead) -> list[dict[str, Any]]:
        payload = dict(item.payload or {})
        refs = payload.get("source_references")
        if isinstance(refs, list):
            return [dict(ref) for ref in refs if isinstance(ref, dict)]
        return [self._action_source_reference(item)]

    def _with_action_source_metadata(
        self, item: PortalActionRead, references: list[dict[str, Any]]
    ) -> PortalActionRead:
        payload = {
            **dict(item.payload or {}),
            "source_references": self._dedupe_source_references(references),
            "dedupe_key": list(self._action_dedupe_key(item)),
        }
        raw = {
            **dict(item.raw or {}),
            "source_references": self._dedupe_source_references(references),
        }
        return item.model_copy(update={"payload": payload, "raw": raw})

    def _dedupe_source_references(
        self, references: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for ref in references:
            key = (ref.get("source_module"), ref.get("source_id"), ref.get("id"))
            if key in seen:
                continue
            seen.add(key)
            result.append(ref)
        return result

    def _normalize_nm_id(self, value: Any) -> int | str | None:
        parsed = self._optional_int(value)
        if parsed is not None:
            return parsed
        text = str(value or "").strip().lower()
        return text or None

    def _normalize_action_type(self, value: Any) -> str:
        normalized = str(value or "manual_review").strip().lower().replace("-", "_")
        aliases = {
            "finance_review": "review_profit",
            "profit_review": "review_profit",
            "review_profit": "review_profit",
            "manual_review_profit": "review_profit",
            "cost_fix": "fix_costs",
            "fix_cost": "fix_costs",
            "fix_costs": "fix_costs",
            "data_fix": "fix_data",
            "fix_data": "fix_data",
            "card_quality": "card_quality_fix",
            "card_quality_fix": "card_quality_fix",
            "draft_claim": "draft_claim",
            "claim_appeal": "draft_claim",
            "report_anomaly_candidate": "draft_claim",
            "draft_reply": "draft_reply",
            "negative_review_unanswered": "draft_reply",
        }
        return aliases.get(normalized, normalized)

    def _normalize_action_root_cause(self, item: PortalActionRead) -> str:
        payload = dict(item.payload or {})
        raw = dict(item.raw or {})
        linked = dict(item.linked_entity or {})
        guided_fix = dict(item.guided_fix or {})
        value = self._first_string(
            raw.get("root_cause"),
            raw.get("root_cause_type"),
            raw.get("diagnosis_type"),
            raw.get("category"),
            raw.get("action_group"),
            raw.get("code"),
            payload.get("root_cause"),
            payload.get("root_cause_type"),
            payload.get("diagnosis_type"),
            payload.get("category"),
            payload.get("action_group"),
            payload.get("code"),
            linked.get("root_cause"),
            linked.get("category"),
            guided_fix.get("route_key"),
        )
        normalized = (
            str(value or self._normalize_action_type(item.action_type))
            .strip()
            .lower()
            .replace("-", "_")
        )
        aliases = {
            "profit_leak": "profit",
            "negative_profit": "profit",
            "loss": "profit",
            "save_money": "profit",
            "finance_review": "profit",
            "review_profit": "profit",
            "missing_manual_cost": "costs",
            "cost_missing": "costs",
            "cost_fix": "costs",
            "card": "card_quality",
            "quality": "card_quality",
        }
        return aliases.get(normalized, normalized)

    def _richer_text(self, first: str | None, second: str | None) -> str:
        first_text = str(first or "")
        second_text = str(second or "")
        return (
            first_text
            if len(first_text.strip()) >= len(second_text.strip())
            else second_text
        )

    def _max_optional_float(self, *values: Any) -> float | None:
        parsed = [
            value
            for value in (self._optional_float(value) for value in values)
            if value is not None
        ]
        if not parsed:
            return None
        return max(parsed, key=abs)

    def _filter_actions(
        self,
        items: list[PortalActionRead],
        *,
        status: str | None,
        source_module: list[str] | None,
        priority: list[str] | None,
        nm_id: int | None = None,
        action_type: list[str] | None = None,
        problem_code: list[str] | None = None,
        trust_state: list[str] | None = None,
        impact_type: list[str] | None = None,
    ) -> list[PortalActionRead]:
        statuses = self._normalize_filter_values(status)
        sources = {
            self._normalize_source_module(value)
            for value in self._normalize_filter_values(source_module)
        }
        priorities = {
            value.upper() for value in self._normalize_filter_values(priority)
        }
        action_types = {
            value.lower() for value in self._normalize_filter_values(action_type)
        }
        problem_codes = {
            value.lower() for value in self._normalize_filter_values(problem_code)
        }
        trust_states = {
            value.lower() for value in self._normalize_filter_values(trust_state)
        }
        impact_types = {
            value.lower() for value in self._normalize_filter_values(impact_type)
        }
        return [
            item
            for item in items
            if (not statuses or item.status in statuses)
            and (not sources or item.source_module in sources)
            and (not priorities or item.priority in priorities)
            and (nm_id is None or item.nm_id == nm_id)
            and (not action_types or item.action_type.lower() in action_types)
            and (
                not problem_codes
                or str(item.detector_code or "").lower() in problem_codes
                or str((item.payload or {}).get("problem_code") or "").lower()
                in problem_codes
                or item.action_type.lower() in problem_codes
            )
            and (
                not trust_states
                or str(item.trust_state or "").lower() in trust_states
                or str((item.payload or {}).get("trust_state") or "").lower()
                in trust_states
            )
            and (
                not impact_types
                or str(item.impact_type or "").lower() in impact_types
                or str((item.payload or {}).get("impact_type") or "").lower()
                in impact_types
            )
        ]

    def _action_sort_key(
        self, item: PortalActionRead
    ) -> tuple[int, int, float, float, str]:
        priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(
            item.priority, 9
        )
        severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
            item.severity, 9
        )
        effect = float(item.expected_effect_amount or 0)
        priority_score = float(item.priority_score or 0)
        return (priority_rank, severity_rank, -priority_score, -effect, item.id)

    def _product360_next_best_action(
        self,
        actions: list[PortalActionRead],
        *,
        nm_id: int,
        module_statuses: dict[str, str] | None = None,
    ) -> PortalActionRead | None:
        if not actions:
            return None
        top = actions[0]
        if self._normalize_source_module(top.source_module) != "stockops":
            return top
        guided_fix = self._guided_fix(
            source_module="finance",
            action_type="review_profit",
            nm_id=nm_id,
            target_id=str(top.source_id or top.id),
            module_statuses=module_statuses,
        )
        return top.model_copy(
            update={
                "guided_fix": guided_fix,
                "payload": {
                    **dict(top.payload or {}),
                    "product360_next_best_target": "product_360",
                },
            }
        )

    def _finalize_action(
        self, item: PortalActionRead, *, module_statuses: dict[str, str] | None = None
    ) -> PortalActionRead:
        source_id = item.source_id
        if not source_id and (
            self._normalize_source_module(item.source_module)
            in self.SHADOW_ACTION_MODULES
            or item.source in self.SHADOW_ACTION_SOURCES
        ):
            source_id = self._deterministic_source_id(
                source_module=self._normalize_source_module(item.source_module),
                action_type=item.action_type,
                nm_id=item.nm_id,
                vendor_code=self._first_string(
                    item.linked_entity.get("vendor_code"),
                    item.payload.get("vendor_code"),
                    item.raw.get("vendor_code"),
                ),
            )
        guided_fix = item.guided_fix or self._guided_fix(
            source_module=item.source_module,
            action_type=item.action_type,
            nm_id=item.nm_id,
            target_id=source_id or item.id,
            module_statuses=module_statuses,
        )
        expected = (
            item.expected_effect_amount
            if item.expected_effect_amount is not None
            else item.expected_impact_amount
        )
        return item.model_copy(
            update={
                "source_module": self._normalize_source_module(item.source_module),
                "source_id": source_id,
                "expected_effect_amount": expected,
                "expected_impact_amount": expected,
                "priority_score": item.priority_score
                if item.priority_score is not None
                else self._priority_score(item.priority, expected),
                "guided_fix": guided_fix,
                "can_update": bool(item.can_update or item.can_update_status),
                "can_update_reason": item.can_update_reason
                if item.can_update_reason
                else None
                if item.can_update or item.can_update_status
                else self._read_only_action_reason(item),
            }
        )

    def _read_only_action_reason(self, item: PortalActionRead) -> str:
        source_module = self._normalize_source_module(item.source_module)
        if source_module == "data_quality":
            return "data_quality_issue_requires_source_workflow"
        if source_module == "costs":
            return "cost_issue_requires_cost_upload_or_mapping"
        if source_module == "checker":
            return "checker_setup_or_external_issue_requires_source_workflow"
        if source_module == "finance":
            return "finance_recommendation_without_persisted_action_id"
        if source_module == "problem_engine":
            return "problem_instance_requires_dynamic_engine_workflow"
        return "read_only_recommendation"

    def _guided_fix(
        self,
        *,
        source_module: str,
        action_type: str,
        nm_id: int | None,
        target_id: str | None,
        module_statuses: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        normalized_source = self._normalize_source_module(source_module)
        preview = self.guided_fixes.map(
            source_module=normalized_source,
            action_type=action_type,
            nm_id=nm_id,
            target_id=target_id,
        )
        return self.guided_fixes.map(
            source_module=normalized_source,
            action_type=action_type,
            nm_id=nm_id,
            target_id=target_id,
            module_status=(module_statuses or {}).get(str(preview.get("module") or "")),
        )

    def _module_status_map(self, items: list[Any]) -> dict[str, str]:
        statuses: dict[str, str] = {}
        if hasattr(items, "model_dump"):
            raw_items = items.model_dump(mode="json") or {}
            iterable = raw_items.items() if isinstance(raw_items, dict) else []
        elif isinstance(items, dict):
            iterable = items.items()
        else:
            iterable = [(None, item) for item in (items or [])]
        for key, item in iterable:
            raw = self._dump(item)
            module = str(raw.get("module") or key or "").strip()
            status = str(raw.get("status") or "").strip()
            if module and status:
                statuses[module] = status
            if module == "grouping":
                statuses.setdefault("grouping_beta", status)
            if module == "stockops":
                statuses.setdefault("stock", status)
        return statuses

    def _normalize_source_module(self, value: Any) -> str:
        normalized = str(value or "manual").strip().lower().replace("-", "_")
        aliases = {
            "grouping_beta": "grouping_beta",
            "grouping": "grouping_beta",
            "stock": "stockops",
            "stock_ops": "stockops",
            "dataquality": "data_quality",
            "cost": "costs",
            "action_center": "result_tracking",
        }
        normalized = aliases.get(normalized, normalized)
        allowed = {
            "finance",
            "data_quality",
            "costs",
            "checker",
            "stockops",
            "grouping_beta",
            "reputation",
            "claims",
            "photo",
            "experiments",
            "profit_doctor",
            "problem_engine",
            "result_tracking",
            "manual",
        }
        return normalized if normalized in allowed else "manual"

    def _priority_score(self, priority: str, expected: float | None) -> float:
        base = {"P0": 500.0, "P1": 400.0, "P2": 300.0, "P3": 200.0, "P4": 100.0}.get(
            str(priority or "P3").upper(), 0.0
        )
        impact = min(abs(float(expected or 0)) / 1000.0, 99.0)
        return base + impact

    def _priority_from_finance(self, raw: dict[str, Any]) -> str:
        action_type = str(raw.get("action_type") or "").lower()
        category = str(raw.get("category") or raw.get("action_group") or "").lower()
        priority = str(raw.get("priority") or "").lower()
        title_reason = f"{raw.get('title') or ''} {raw.get('why') or ''} {raw.get('business_reason') or ''}".lower()
        expected = abs(float(raw.get("expected_effect_amount") or 0))
        if (
            "block" in category
            or "data" in category
            or "cost" in action_type
            or "себесто" in title_reason
        ):
            return "P0"
        if (
            "negative" in action_type
            or "loss" in action_type
            or "save_money" in category
            or "убыт" in title_reason
        ):
            return "P1"
        if priority in {"critical", "high"} and expected >= 10_000:
            return "P2"
        if any(
            token in action_type
            for token in ("stock", "ads", "ad_", "price", "pricing")
        ) or any(token in category for token in ("stock", "ads", "price")):
            return "P3"
        if "growth" in category or "grow" in action_type:
            return "P4"
        return {"critical": "P0", "high": "P2", "medium": "P3", "low": "P4"}.get(
            priority, "P3"
        )

    def _priority_from_issue(
        self, *, code: str, severity: Any, payload: dict[str, Any]
    ) -> str:
        normalized = code.lower()
        if "cost" in normalized or normalized in {
            "seller_other_expense_missing",
            "expense_finance_report_missing",
        }:
            return "P0"
        if "negative" in normalized:
            return "P1"
        affected_revenue = (
            self._optional_float(
                payload.get("affectedRevenue") or payload.get("revenue")
            )
            or 0
        )
        if affected_revenue >= 50_000:
            return "P2"
        if any(token in normalized for token in ("stock", "ad_", "price", "pricing")):
            return "P3"
        return {"critical": "P0", "error": "P1", "warning": "P2", "info": "P4"}.get(
            str(severity or "").lower(), "P3"
        )

    def _severity_from_priority(self, priority: str) -> str:
        return {
            "P0": "critical",
            "P1": "high",
            "P2": "high",
            "P3": "medium",
            "P4": "low",
        }.get(priority, "medium")

    def _severity_from_dq(self, value: Any, *, is_blocker: bool) -> str:
        if is_blocker:
            return "critical"
        normalized = str(value or "").lower()
        return {
            "critical": "critical",
            "error": "high",
            "warning": "medium",
            "info": "low",
        }.get(normalized, "medium")

    def _normalize_status(self, value: Any) -> str:
        normalized = str(value or "new").strip().lower()
        if normalized in {"todo", "open", "pending", "created"}:
            return "new"
        if normalized in {"acknowledge", "acknowledged", "accepted"}:
            return "acknowledged"
        if normalized in {"doing", "active", "processing", "working"}:
            return "in_progress"
        if normalized in {"completed", "complete", "closed"}:
            return "done"
        if normalized in {"resolved", "fixed"}:
            return "resolved"
        if normalized in {"deferred", "snoozed"}:
            return "postponed"
        if normalized in {"cancelled", "canceled", "skipped"}:
            return "ignored"
        if normalized in {"dismissed", "discarded"}:
            return "dismissed"
        if normalized in {"reopen", "reopened"}:
            return "reopened"
        if normalized in {
            "blocked",
            "failed",
            "error",
            "unavailable",
            "not_configured",
            "disabled",
        }:
            return "blocked"
        if normalized in self.ACTION_CENTER_STATUSES:
            return normalized
        return "new"

    def _normalize_confidence(self, value: Any) -> str:
        normalized = str(value or "medium").strip().lower()
        return normalized if normalized in {"high", "medium", "low"} else "medium"

    def _finance_status_filter(self, status: str | None) -> str | None:
        if not self._normalize_filter_values(status):
            return None
        normalized = self._normalize_status(status) if status else None
        return None if normalized == "new" and status is None else normalized

    def _normalize_filter_values(self, values: str | list[str] | None) -> set[str]:
        if values is None:
            return set()
        raw_values = [values] if isinstance(values, str) else values
        normalized: set[str] = set()
        for raw in raw_values:
            for item in str(raw).split(","):
                value = item.strip().lower()
                if value in {"all", "*", "any"}:
                    continue
                if value:
                    normalized.add(value)
        return normalized

    def _first_string(self, *values: Any) -> str | None:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _optional_int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def _optional_float(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def _first_present_float(self, *values: Any) -> float | None:
        for value in values:
            converted = self._optional_float(value)
            if converted is not None:
                return converted
        return None

    def _optional_datetime(self, value: Any):
        if value is None or isinstance(value, str):
            return value
        return value

    def _first_int(self, values: Any) -> int | None:
        if not values:
            return None
        try:
            return int(values[0])
        except (TypeError, ValueError, IndexError):
            return None
