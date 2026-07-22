from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Iterable

import sqlalchemy as sa
from sqlalchemy import String, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import stable_hash, table_signature
from app.core.config import get_settings
from app.core.manual_cost_math import (
    manual_cost_price,
    manual_cost_seller_other_expense,
    manual_cost_total_unit_cost,
)
from app.core.pagination import Page
from app.core.current_state import orders_current_subquery, sales_current_subquery
from app.core.enums_meta import get_enum_mapping
from app.core.expense_taxonomy import (
    AD_SPEND_SOURCE_FINANCE,
    AD_SPEND_SOURCE_NONE,
    AD_SPEND_SOURCE_OPERATIONAL,
    EXPENSE_CATEGORY_ACCEPTANCE,
    EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
    EXPENSE_CATEGORY_DEDUCTION,
    EXPENSE_CATEGORY_LOYALTY,
    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
    EXPENSE_CATEGORY_PAYMENT_PROCESSING,
    EXPENSE_CATEGORY_PENALTY,
    EXPENSE_CATEGORY_PVZ_REWARD,
    EXPENSE_CATEGORY_STORAGE,
    EXPENSE_CATEGORY_UNCLASSIFIED,
    EXPENSE_CATEGORY_WB_COMMISSION,
    EXPENSE_CATEGORY_WB_LOGISTICS,
    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
    additional_income as expense_additional_income,
    expense_data_quality as compute_expense_data_quality,
    merge_expense_data_quality,
    normalized_wb_expenses_total,
    revenue_final as compute_revenue_final,
)
from app.core.time import utcnow
from app.models.ads import WBAdClusterStat, WBAdStatsDaily
from app.models.analytics import WBCardFunnelDaily
from app.models.control_tower import UserBusinessSetting
from app.core.issue_refs import extract_issue_refs
from app.models.data_quality import DataQualityIssue
from app.models.finance import WBRealizationReportRow
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily
from app.models.prices import WBPrice, WBPriceSize
from app.models.product_cards import CoreSKU, WBProductCard
from app.models.raw import RawWBAPIResponse
from app.models.sync import WBSyncCursor, WBSyncRun
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.schemas.dashboard import (
    ArticleAdsSummary,
    ArticleAuditRead,
    ArticleCompleteness,
    ArticleDailyEconomics,
    ArticleDailyPoint,
    ArticleFinanceSummary,
    ArticleFunnelSummary,
    ArticleIdentity,
    ArticleIssueSummary,
    ArticleManualCostMatch,
    ArticleNote,
    ArticleOperationsSummary,
    ArticlePriceSnapshot,
    ArticleReconciliationSummary,
    ArticleStockSummary,
    DashboardCostCoverageBlock,
    DashboardDataHealth,
    DashboardHealthDomainStatus,
    DashboardHealthIssueBucket,
    SKUProfitabilityRow,
)
from app.schemas.data_quality import (
    DataQualitySummaryBlock,
    issue_bucket_meta,
    issue_is_operational_only_non_final,
)
from app.services.trust import (
    GLOBAL_HARD_BLOCKER_REASONS,
    build_cost_coverage_decision,
    build_global_trust_decision,
    build_public_trust_snapshot,
    blocked_reasons_for_profit_row,
    cost_policy_owner_approves_final,
    cost_truth_level_from_cost,
    cost_truth_level_from_flags,
    effective_cost_is_business_trusted,
    final_cost_is_accepted,
    normalize_blocked_reasons_for_cost_policy,
)


class DashboardService:
    DATA_HEALTH_CACHE_TTL_SECONDS = 300
    RESPONSE_CACHE_TTL_SECONDS = get_settings().heavy_endpoint_cache_ttl_seconds
    _shared_data_health_cache: dict[
        tuple[int, date, date, str], tuple[datetime, DashboardDataHealth]
    ] = {}
    _shared_profitability_page_cache: dict[
        tuple[object, ...], tuple[datetime, Page[SKUProfitabilityRow]]
    ] = {}
    CLASSIFIED_ISSUE_STATUSES = {
        "classified",
        "ignored",
        "ignored_with_reason",
        "mapped",
        "archived",
    }
    TRANSIENT_SYNC_FAILURE_GRACE_HOURS = 72
    STOCK_SNAPSHOT_FRESHNESS_HOURS = 72
    BUSINESS_CRITICAL_SYNC_DOMAINS = {
        "product_cards",
        "prices",
        "orders",
        "sales",
        "stocks",
        "finance",
        "supplies",
        "ads",
    }

    def __init__(self) -> None:
        self._data_health_cache = type(self)._shared_data_health_cache
        self._profitability_page_cache = type(self)._shared_profitability_page_cache
        self._data_quality_service = None

    def _get_data_quality_service(self):
        if self._data_quality_service is None:
            from app.services.data_quality import DataQualityService

            self._data_quality_service = DataQualityService()
        return self._data_quality_service

    @staticmethod
    def _cache_is_fresh(cached_at: datetime, *, ttl_seconds: int) -> bool:
        return (utcnow() - cached_at) <= timedelta(seconds=ttl_seconds)

    @staticmethod
    def _with_page_cache_meta(
        page: Page[SKUProfitabilityRow],
        *,
        computed_at: datetime,
        cache_status: str,
        data_version_hash: str,
    ) -> Page[SKUProfitabilityRow]:
        return page.model_copy(
            deep=True,
            update={
                "computed_at": computed_at,
                "cache_status": cache_status,
                "data_version_hash": data_version_hash,
            },
        )

    async def _sku_profitability_page_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> str:
        if session is None:
            return "session-unavailable"
        mart_hash = await table_signature(
            session,
            model=MartSKUDaily,
            account_id=account_id,
            date_column=MartSKUDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        cost_hash = await table_signature(
            session,
            model=ManualCost,
            account_id=account_id,
            extra_filters=[
                or_(ManualCost.valid_from.is_(None), ManualCost.valid_from <= date_to),
                or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= date_from),
            ],
        )
        dq_hash = await table_signature(
            session,
            model=DataQualityIssue,
            account_id=account_id,
            extra_filters=[DataQualityIssue.resolved_at.is_(None)],
        )
        cluster_hash = await table_signature(
            session,
            model=WBAdClusterStat,
            account_id=account_id,
            date_column=WBAdClusterStat.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        sync_run_hash = await table_signature(
            session, model=WBSyncRun, account_id=account_id
        )
        sync_cursor_hash = await table_signature(
            session, model=WBSyncCursor, account_id=account_id
        )
        return stable_hash(
            "dashboard-sku-profitability",
            account_id,
            date_from.isoformat(),
            date_to.isoformat(),
            mart_hash,
            cost_hash,
            dq_hash,
            cluster_hash,
            sync_run_hash,
            sync_cursor_hash,
        )

    FINANCIAL_FINAL_DQ_SEVERITIES = {"error", "critical"}
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
        "sync_issues": {"failed_sync_domains", "scheduler_instability"},
    }

    @staticmethod
    def _percent(part: int | Decimal, whole: int | Decimal) -> float | None:
        whole_decimal = Decimal(str(whole or 0))
        if whole_decimal <= 0:
            return None
        return float((Decimal(str(part or 0)) / whole_decimal) * Decimal("100"))

    @staticmethod
    def _data_quality_summary_message(
        *,
        global_blockers_total: int,
        open_issues_total: int,
        financial_final_blockers_total: int,
        final_profit_allowed: bool,
    ) -> str:
        if global_blockers_total > 0:
            return "Есть глобальные блокеры данных: сначала закройте их, затем возвращайтесь к business actions."
        if open_issues_total > 0 and (
            financial_final_blockers_total > 0 or not final_profit_allowed
        ):
            return "Глобальных блокеров нет, но есть открытые issues; финальная прибыль предварительная."
        if open_issues_total > 0:
            return "Глобальных блокеров нет, но есть открытые issues; данные не полностью clean."
        return "Глобальных блокеров и открытых issues нет."

    def _build_data_quality_summary(
        self,
        *,
        issue_buckets: list[DashboardHealthIssueBucket],
        blocked_reasons: list[str],
        final_profit_allowed: bool,
        all_open_issues_total: int,
        blocking_open_issues_total: int,
        financial_final_blockers_total: int,
    ) -> DataQualitySummaryBlock:
        critical_total = sum(
            bucket.count for bucket in issue_buckets if bucket.severity == "critical"
        )
        error_total = sum(
            bucket.count for bucket in issue_buckets if bucket.severity == "error"
        )
        warning_total = sum(
            bucket.count for bucket in issue_buckets if bucket.severity == "warning"
        )
        info_total = sum(
            bucket.count for bucket in issue_buckets if bucket.severity == "info"
        )
        global_blockers_total = sum(
            1
            for reason in set(blocked_reasons)
            if reason in GLOBAL_HARD_BLOCKER_REASONS
        )
        return DataQualitySummaryBlock(
            global_blockers_total=global_blockers_total,
            financial_final_blockers_total=financial_final_blockers_total,
            open_issues_total=all_open_issues_total,
            all_open_issues_total=all_open_issues_total,
            blocking_open_issues_total=blocking_open_issues_total,
            critical_total=critical_total,
            error_total=error_total,
            warning_total=warning_total,
            info_total=info_total,
            message=self._data_quality_summary_message(
                global_blockers_total=global_blockers_total,
                open_issues_total=all_open_issues_total,
                financial_final_blockers_total=financial_final_blockers_total,
                final_profit_allowed=final_profit_allowed,
            ),
            buckets=issue_buckets,
        )

    def _operator_baseline_revenue_coverage_percent(
        self,
        *,
        total_revenue: Decimal,
        supplier_confirmed_revenue: Decimal,
        trusted_revenue: Decimal,
    ) -> float:
        operator_revenue = max(
            Decimal("0"), trusted_revenue - supplier_confirmed_revenue
        )
        return self._percent(operator_revenue, total_revenue) or 0.0

    async def _cost_trust_policy(
        self, session: AsyncSession, *, account_id: int
    ) -> str:
        try:
            row = (
                await session.execute(
                    select(UserBusinessSetting)
                    .where(UserBusinessSetting.account_id == account_id)
                    .limit(1)
                )
            ).scalar_one_or_none()
        except Exception:
            return "operator_baseline"
        settings = (
            row.settings_json
            if row is not None and isinstance(row.settings_json, dict)
            else {}
        )
        return str(settings.get("cost_trust_policy") or "operator_baseline")

    @staticmethod
    def _normalized_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _is_total_stock_row(warehouse_name: str | None) -> bool:
        return "всего" in str(warehouse_name or "").strip().lower()

    @classmethod
    def _aggregate_article_stock_rows(
        cls,
        rows: list[WBStockSnapshotRow],
    ) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        if not rows:
            return Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0")
        total_rows = [
            row for row in rows if cls._is_total_stock_row(row.warehouse_name)
        ]
        quantity_rows = total_rows or rows
        transit_rows = [
            row
            for row in rows
            if cls._decimal(getattr(row, "quantity", None)) == 0
            and cls._decimal(getattr(row, "quantity_full", None)) == 0
        ]
        transit_source = transit_rows or quantity_rows
        quantity = sum(
            (
                cls._decimal(getattr(row, "quantity_full", None))
                if total_rows
                else cls._decimal(getattr(row, "quantity", None))
            )
            for row in quantity_rows
        )
        quantity_full = quantity
        in_way_to_client = sum(
            (
                cls._decimal(getattr(row, "in_way_to_client", None))
                for row in transit_source
            ),
            start=Decimal("0"),
        )
        in_way_from_client = sum(
            (
                cls._decimal(getattr(row, "in_way_from_client", None))
                for row in transit_source
            ),
            start=Decimal("0"),
        )
        return quantity, quantity_full, in_way_to_client, in_way_from_client

    @classmethod
    def _issue_classification_status(cls, issue: DataQualityIssue) -> str:
        payload = dict(issue.payload or {})
        return str(
            payload.get("classificationStatus") or payload.get("resolutionStatus") or ""
        ).lower()

    @classmethod
    def _issue_is_classified_for_acceptance(cls, issue: DataQualityIssue) -> bool:
        return cls._issue_classification_status(issue) in cls.CLASSIFIED_ISSUE_STATUSES

    @classmethod
    def _issue_payload(cls, issue: DataQualityIssue) -> dict:
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
        source_domains = cls._issue_source_domains(issue)
        classification_reason = (
            str(payload.get("classificationReason") or "").strip().lower()
        )
        return (
            cls._issue_source_kind(issue) == "source_level"
            and source_domains == {"supplies"}
            and classification_reason in {"missing_nm_id", "source_level_missing_nm_id"}
        )

    @classmethod
    def _issue_blocks_business_analysis(cls, issue: DataQualityIssue) -> bool:
        if str(issue.severity or "").lower() not in {"error", "critical"}:
            return False
        if cls._issue_is_classified_for_acceptance(issue):
            return False
        if cls._issue_is_supply_source_unmatched(issue):
            return False
        return True

    @classmethod
    def _blocking_open_issue_count(cls, issues: Iterable[DataQualityIssue]) -> int:
        return sum(1 for issue in issues if cls._issue_blocks_business_analysis(issue))

    @classmethod
    def _issue_is_financial_final_blocker(cls, issue: DataQualityIssue) -> bool:
        if issue_is_operational_only_non_final(
            str(getattr(issue, "code", None) or ""), getattr(issue, "payload", None)
        ):
            return False
        if cls._issue_is_supply_source_unmatched(issue):
            return False
        if getattr(issue, "effective_financial_final_blocker", None) is not None:
            return bool(issue.effective_financial_final_blocker)
        meta = issue_bucket_meta(str(issue.code or ""))
        if not bool(meta.get("financial_final_blocker")):
            return False
        if str(issue.severity or "").lower() not in {"error", "warning", "critical"}:
            return False
        return not cls._issue_is_classified_for_acceptance(issue)

    @classmethod
    def _issue_group(cls, code: str) -> str:
        for group, codes in cls.ISSUE_GROUP_MAP.items():
            if code in codes:
                return group
        return "info_non_blocking"

    @classmethod
    def _public_row_trust_state(
        cls,
        *,
        effective_business_trusted: bool,
        cost_final_accepted: bool,
        has_placeholder_cost: bool,
        finance_rows: int,
        blocked_reasons: list[str],
    ) -> str:
        operational_trusted = bool(effective_business_trusted and not blocked_reasons)
        if operational_trusted and cost_final_accepted and finance_rows > 0:
            return "financial_final"
        if operational_trusted:
            return "operational_provisional"
        if has_placeholder_cost:
            return "test_only"
        if blocked_reasons:
            return "blocked"
        return "unknown"

    @classmethod
    def _is_transient_failed_domain(
        cls,
        item: DashboardHealthDomainStatus,
        *,
        reference_at: datetime,
    ) -> bool:
        if item.latest_status != "failed" or item.last_successful_at is None:
            return False
        error_text = str(item.latest_error_text or "").lower()
        if "429" not in error_text and "too many requests" not in error_text:
            return False
        last_successful_at = cls._normalized_datetime(item.last_successful_at)
        normalized_reference_at = cls._normalized_datetime(reference_at)
        if last_successful_at is None or normalized_reference_at is None:
            return False
        return last_successful_at >= normalized_reference_at - timedelta(
            hours=cls.TRANSIENT_SYNC_FAILURE_GRACE_HOURS
        )

    @classmethod
    def _effective_stocks_status(
        cls,
        *,
        latest_run: WBSyncRun | None,
        default_cursor: WBSyncCursor | None,
        latest_snapshot_at: datetime | None,
        reference_at: datetime,
    ) -> str | None:
        if latest_run is not None and latest_run.status == "completed":
            return "completed"
        if (
            default_cursor is not None
            and default_cursor.status == "completed"
            and cls._normalized_datetime(latest_snapshot_at) is not None
            and cls._normalized_datetime(reference_at) is not None
            and cls._normalized_datetime(latest_snapshot_at)
            >= cls._normalized_datetime(reference_at)
            - timedelta(hours=cls.STOCK_SNAPSHOT_FRESHNESS_HOURS)
        ):
            return "completed"
        if latest_run is not None:
            return latest_run.status
        if default_cursor is not None:
            return default_cursor.status
        return None

    @classmethod
    def _is_business_trusted(
        cls,
        *,
        trusted_revenue_coverage_percent: float | None,
        failed_domains: list[str],
        unmatched_sku_count: int,
        latest_stocks_status: str | None,
        open_issues: Iterable[DataQualityIssue],
        article_audit_consistent: bool | None = None,
        scheduler_stable: bool = True,
    ) -> bool:
        return build_global_trust_decision(
            supplier_confirmed_revenue_coverage_percent=trusted_revenue_coverage_percent,
            failed_domains=failed_domains,
            unresolved_unmatched_sku_count=unmatched_sku_count,
            latest_stocks_status=latest_stocks_status,
            blocking_open_issue_count=cls._blocking_open_issue_count(open_issues),
            article_audit_consistent=article_audit_consistent,
            scheduler_stable=scheduler_stable,
        ).business_trusted

    @staticmethod
    def _filter_sort_profitability_items(
        items: list[SKUProfitabilityRow],
        *,
        search: str | None,
        vendor_code: str | None,
        barcode: str | None,
        brand: str | None,
        subject_name: str | None,
        has_manual_cost: bool | None,
        business_trusted: bool | None,
        sort: str,
    ) -> list[SKUProfitabilityRow]:
        filtered = list(items)
        if search:
            pattern = search.strip().lower()
            filtered = [
                item
                for item in filtered
                if pattern in str(item.nm_id or "").lower()
                or pattern in (item.vendor_code or "").lower()
                or pattern in (item.barcode or "").lower()
                or pattern in (item.title or "").lower()
                or pattern in (item.brand or "").lower()
                or pattern in (item.subject_name or "").lower()
            ]
        if has_manual_cost is not None:
            filtered = [
                item for item in filtered if item.has_manual_cost is has_manual_cost
            ]
        if vendor_code:
            pattern = vendor_code.strip().lower()
            filtered = [
                item for item in filtered if pattern in (item.vendor_code or "").lower()
            ]
        if barcode:
            pattern = barcode.strip().lower()
            filtered = [
                item for item in filtered if pattern in (item.barcode or "").lower()
            ]
        if brand:
            pattern = brand.strip().lower()
            filtered = [
                item for item in filtered if pattern in (item.brand or "").lower()
            ]
        if subject_name:
            pattern = subject_name.strip().lower()
            filtered = [
                item
                for item in filtered
                if pattern in (item.subject_name or "").lower()
            ]
        if business_trusted is not None:
            filtered = [
                item for item in filtered if item.business_trusted is business_trusted
            ]

        def profit_key(item: SKUProfitabilityRow) -> float:
            return (
                item.estimated_profit
                if item.estimated_profit is not None
                else float("-inf")
            )

        if sort == "profit_asc":
            filtered.sort(
                key=lambda item: (
                    item.estimated_profit
                    if item.estimated_profit is not None
                    else float("inf")
                )
            )
        elif sort == "margin_asc":
            filtered.sort(
                key=lambda item: (
                    item.margin_percent
                    if item.margin_percent is not None
                    else float("inf")
                )
            )
        elif sort == "margin_desc":
            filtered.sort(
                key=lambda item: (
                    item.margin_percent
                    if item.margin_percent is not None
                    else float("-inf")
                ),
                reverse=True,
            )
        elif sort == "ad_spend_asc":
            filtered.sort(key=lambda item: item.ad_spend)
        elif sort == "ad_spend_desc":
            filtered.sort(key=lambda item: item.ad_spend, reverse=True)
        elif sort == "revenue_asc":
            filtered.sort(key=lambda item: item.realized_revenue)
        elif sort == "revenue_desc":
            filtered.sort(key=lambda item: item.realized_revenue, reverse=True)
        elif sort == "vendor_code_asc":
            filtered.sort(key=lambda item: ((item.vendor_code or ""), item.nm_id or 0))
        elif sort == "vendor_code_desc":
            filtered.sort(
                key=lambda item: ((item.vendor_code or ""), item.nm_id or 0),
                reverse=True,
            )
        elif sort == "nm_id_asc":
            filtered.sort(key=lambda item: (item.nm_id or 0, item.vendor_code or ""))
        elif sort == "nm_id_desc":
            filtered.sort(
                key=lambda item: (item.nm_id or 0, item.vendor_code or ""), reverse=True
            )
        elif sort == "no_cost_first":
            filtered.sort(
                key=lambda item: (item.has_manual_cost, -(item.estimated_profit or 0))
            )
        else:
            filtered.sort(key=profit_key, reverse=True)
        return filtered

    @staticmethod
    def _normalize_profitability_sort(
        *,
        sort: str,
        sort_by: str | None,
        sort_dir: str,
    ) -> str:
        if not sort_by:
            return sort
        mapping = {
            "estimated_profit": {"asc": "profit_asc", "desc": "profit_desc"},
            "margin_percent": {"asc": "margin_asc", "desc": "margin_desc"},
            "ad_spend": {"asc": "ad_spend_asc", "desc": "ad_spend_desc"},
            "realized_revenue": {"asc": "revenue_asc", "desc": "revenue_desc"},
            "vendor_code": {"asc": "vendor_code_asc", "desc": "vendor_code_desc"},
            "nm_id": {"asc": "nm_id_asc", "desc": "nm_id_desc"},
        }
        return mapping.get(sort_by, {}).get(sort_dir, sort)

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value or 0))

    @staticmethod
    def _ad_spend_from_rows(ad_rows: list[WBAdStatsDaily] | None) -> Decimal:
        return sum(
            (
                DashboardService._decimal(getattr(row, "sum", None))
                for row in (ad_rows or [])
            ),
            start=Decimal("0"),
        )

    @staticmethod
    def _ad_spend_by_date(ad_rows: list[WBAdStatsDaily] | None) -> dict[date, Decimal]:
        grouped: dict[date, Decimal] = defaultdict(lambda: Decimal("0"))
        for row in ad_rows or []:
            if row.stat_date is None:
                continue
            grouped[row.stat_date] += DashboardService._decimal(
                getattr(row, "sum", None)
            )
        return dict(grouped)

    @staticmethod
    def _expense_value(
        row: Any, field: str, legacy_field: str | None = None
    ) -> Decimal:
        value = getattr(row, field, None)
        if value in (None, "") and legacy_field:
            value = getattr(row, legacy_field, None)
        return DashboardService._decimal(value)

    @staticmethod
    def _row_ad_components(
        row: Any, *, source_ad_spend: Decimal = Decimal("0")
    ) -> dict[str, Decimal | str]:
        ad_source = str(getattr(row, "ad_spend_source", "") or "")
        ad_finance = DashboardService._decimal(getattr(row, "ad_spend_finance", None))
        ad_operational = DashboardService._decimal(
            getattr(row, "ad_spend_operational", None)
        )
        ad_final = DashboardService._decimal(
            getattr(row, "ad_spend_final", getattr(row, "ad_spend", None))
        )
        if ad_source == AD_SPEND_SOURCE_FINANCE or ad_finance > 0:
            final_spend = ad_final if ad_final > 0 else ad_finance
            return {
                "ad_spend_operational": ad_operational
                if ad_operational > 0
                else source_ad_spend,
                "ad_spend_finance": ad_finance if ad_finance > 0 else final_spend,
                "ad_spend_final": final_spend,
                "ad_spend_source": AD_SPEND_SOURCE_FINANCE,
                "ad_spend_delta": DashboardService._decimal(
                    getattr(row, "ad_spend_delta", None)
                )
                if getattr(row, "ad_spend_delta", None) is not None
                else (ad_operational if ad_operational > 0 else source_ad_spend)
                - ad_finance,
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
                else DashboardService._decimal(getattr(row, "ad_spend", None))
            )
            return {
                "ad_spend_operational": ad_operational
                if ad_operational > 0
                else final_spend,
                "ad_spend_finance": Decimal("0"),
                "ad_spend_final": final_spend,
                "ad_spend_source": AD_SPEND_SOURCE_OPERATIONAL,
                "ad_spend_delta": DashboardService._decimal(
                    getattr(row, "ad_spend_delta", None)
                )
                if getattr(row, "ad_spend_delta", None) is not None
                else final_spend,
            }
        return {
            "ad_spend_operational": Decimal("0"),
            "ad_spend_finance": Decimal("0"),
            "ad_spend_final": DashboardService._decimal(getattr(row, "ad_spend", None)),
            "ad_spend_source": AD_SPEND_SOURCE_NONE,
            "ad_spend_delta": Decimal("0"),
        }

    @staticmethod
    def _ads_allocation_metrics(
        *,
        mart_ad_spend: Decimal,
        source_ad_spend: Decimal,
    ) -> dict[str, Decimal | str | bool]:
        raw_ad_spend = max(mart_ad_spend, source_ad_spend, Decimal("0"))
        if source_ad_spend <= 0:
            return {
                "raw_ad_spend": raw_ad_spend,
                "capped_ad_spend": Decimal("0"),
                "overallocated_ad_spend": Decimal("0"),
                "unallocated_ad_spend": Decimal("0"),
                "ads_allocation_status": "no_source_data",
                "final_profit_allowed": False,
            }
        capped_ad_spend = min(raw_ad_spend, source_ad_spend)
        overallocated_ad_spend = max(Decimal("0"), raw_ad_spend - source_ad_spend)
        unallocated_ad_spend = max(Decimal("0"), source_ad_spend - capped_ad_spend)
        if overallocated_ad_spend > 0:
            status = "overallocated"
        elif unallocated_ad_spend > 0:
            status = "partial"
        else:
            status = "matched"
        return {
            "raw_ad_spend": raw_ad_spend,
            "capped_ad_spend": capped_ad_spend,
            "overallocated_ad_spend": overallocated_ad_spend,
            "unallocated_ad_spend": unallocated_ad_spend,
            "ads_allocation_status": status,
            "final_profit_allowed": overallocated_ad_spend <= 0,
        }

    @staticmethod
    def _finance_row_is_reconcilable(row: WBRealizationReportRow) -> bool:
        if row.is_reconcilable is not None:
            return bool(row.is_reconcilable)
        doc_type = (row.doc_type_name or "").strip().lower()
        return doc_type in {"продажа", "возврат", "sale", "return"}

    @classmethod
    def _signed_finance_amount(
        cls, row: WBRealizationReportRow, value: object
    ) -> Decimal:
        amount = cls._decimal(value)
        if amount == 0:
            return amount
        if cls._row_sign(row) < 0 and amount > 0:
            return -amount
        return amount

    @staticmethod
    def _build_article_manual_cost_match(
        matched_cost: object | None,
        *,
        source: str | None,
        total_unit_cost: Decimal | None,
    ) -> ArticleManualCostMatch | None:
        if matched_cost is None:
            return None
        is_placeholder = bool(getattr(matched_cost, "is_placeholder", False)) or (
            str(getattr(matched_cost, "supplier", "") or "").strip().upper()
            == "AUTO_TEMPLATE"
        )
        truth_level = cost_truth_level_from_cost(matched_cost)
        is_business_trusted = truth_level == "supplier_confirmed"
        confidence = (
            "high"
            if truth_level == "supplier_confirmed"
            else "medium"
            if truth_level == "operator_baseline"
            else "low"
        )
        reason = (
            ""
            if truth_level == "supplier_confirmed"
            else "operator_baseline_not_supplier_confirmed"
            if truth_level == "operator_baseline"
            else "placeholder_cost"
            if truth_level == "placeholder"
            else "missing_cost"
        )
        return ArticleManualCostMatch(
            matched=True,
            source=source,
            unit_cost=float(
                DashboardService._decimal(getattr(matched_cost, "unit_cost", None))
            ),
            cost_price=float(manual_cost_price(matched_cost)),
            seller_other_expense=float(manual_cost_seller_other_expense(matched_cost)),
            packaging_cost=float(
                DashboardService._decimal(getattr(matched_cost, "packaging_cost", None))
            ),
            inbound_logistics_cost=float(
                DashboardService._decimal(
                    getattr(matched_cost, "inbound_logistics_cost", None)
                )
            ),
            total_unit_cost=float(total_unit_cost)
            if total_unit_cost is not None
            else None,
            supplier=getattr(matched_cost, "supplier", None),
            currency=getattr(matched_cost, "currency", None),
            valid_from=getattr(matched_cost, "valid_from", None),
            valid_to=getattr(matched_cost, "valid_to", None),
            comment=getattr(matched_cost, "comment", None),
            is_placeholder=is_placeholder,
            is_business_trusted=is_business_trusted,
            supplier_confirmed=truth_level == "supplier_confirmed",
            confidence=confidence,
            reason=reason,
            cost_truth_level=truth_level,
            cost_truth_label=get_enum_mapping("cost_truth_level").get(
                truth_level, truth_level
            )
            if truth_level is not None
            else None,
        )

    @staticmethod
    def _build_article_daily_economics(
        mart_rows: list[MartSKUDaily],
        ad_rows: list[WBAdStatsDaily] | None = None,
    ) -> ArticleDailyEconomics | None:
        if not mart_rows:
            return None
        revenue = sum(
            (compute_revenue_final(item) for item in mart_rows), start=Decimal("0")
        )
        for_pay = sum(
            (DashboardService._decimal(item.final_for_pay) for item in mart_rows),
            start=Decimal("0"),
        )
        wb_expenses = sum(
            (normalized_wb_expenses_total(item) for item in mart_rows), Decimal("0")
        )
        source_ad_spend_total = DashboardService._ad_spend_from_rows(ad_rows)
        ad_rows_totals = [
            DashboardService._row_ad_components(item) for item in mart_rows
        ]
        ad_operational_total = sum(
            (
                DashboardService._decimal(item["ad_spend_operational"])
                for item in ad_rows_totals
            ),
            start=Decimal("0"),
        )
        ad_finance_total = sum(
            (
                DashboardService._decimal(item["ad_spend_finance"])
                for item in ad_rows_totals
            ),
            start=Decimal("0"),
        )
        ad_final_total = sum(
            (
                DashboardService._decimal(item["ad_spend_final"])
                for item in ad_rows_totals
            ),
            start=Decimal("0"),
        )
        mart_ad_spend_total = (
            ad_operational_total if ad_operational_total > 0 else ad_final_total
        )
        if ad_finance_total > 0 or any(
            str(item["ad_spend_source"]) == AD_SPEND_SOURCE_FINANCE
            for item in ad_rows_totals
        ):
            operational_reference = (
                ad_operational_total
                if ad_operational_total > 0
                else source_ad_spend_total
            )
            ad_spend_total = ad_final_total if ad_final_total > 0 else ad_finance_total
            ads_metrics = {
                "raw_ad_spend": ad_spend_total,
                "capped_ad_spend": ad_spend_total,
                "overallocated_ad_spend": Decimal("0"),
                "unallocated_ad_spend": max(
                    Decimal("0"), source_ad_spend_total - operational_reference
                ),
                "ads_allocation_status": "finance_final",
                "final_profit_allowed": True,
            }
            ad_spend_source = AD_SPEND_SOURCE_FINANCE
        else:
            ads_metrics = DashboardService._ads_allocation_metrics(
                mart_ad_spend=mart_ad_spend_total,
                source_ad_spend=source_ad_spend_total,
            )
            ad_spend_total = DashboardService._decimal(ads_metrics["capped_ad_spend"])
            ad_spend_source = (
                AD_SPEND_SOURCE_OPERATIONAL
                if ad_spend_total > 0
                else AD_SPEND_SOURCE_NONE
            )
        cogs_total = sum(
            (
                DashboardService._decimal(item.estimated_cogs)
                for item in mart_rows
                if item.estimated_cogs is not None
            ),
            start=Decimal("0"),
        )
        seller_cogs = sum(
            (
                DashboardService._decimal(
                    getattr(item, "seller_cogs", getattr(item, "estimated_cogs", None))
                )
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        seller_other_expense = sum(
            (
                DashboardService._decimal(getattr(item, "seller_other_expense", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        seller_expense_total = seller_cogs + seller_other_expense
        additional_income = sum(
            (expense_additional_income(item) for item in mart_rows), start=Decimal("0")
        )
        has_normalized_ad_fields = any(
            getattr(item, "ad_spend_operational", None) is not None
            or getattr(item, "ad_spend_finance", None) is not None
            or getattr(item, "ad_spend_final", None) is not None
            or str(getattr(item, "ad_spend_source", "") or "") != ""
            for item in mart_rows
        )
        profit_before_ads = sum(
            (
                DashboardService._decimal(
                    getattr(item, "estimated_profit_before_ads", None)
                )
                for item in mart_rows
                if getattr(item, "estimated_profit_before_ads", None) is not None
            ),
            start=Decimal("0"),
        )
        profit_after_ads_sum = sum(
            (
                DashboardService._decimal(item.estimated_profit_after_ads)
                for item in mart_rows
                if item.estimated_profit_after_ads is not None
            ),
            start=Decimal("0"),
        )
        net_profit_after_all_expenses_sum = sum(
            (
                DashboardService._decimal(
                    getattr(item, "net_profit_after_all_expenses", None)
                )
                for item in mart_rows
                if getattr(item, "net_profit_after_all_expenses", None) is not None
            ),
            start=Decimal("0"),
        )
        if profit_before_ads == 0 and revenue > 0:
            profit_before_ads = (
                revenue - wb_expenses - seller_expense_total + additional_income
            )
        profit_after_ads = (
            profit_after_ads_sum
            if has_normalized_ad_fields and profit_after_ads_sum != 0
            else profit_before_ads - ad_spend_total
        )
        net_profit_all_expenses = (
            net_profit_after_all_expenses_sum
            if has_normalized_ad_fields and net_profit_after_all_expenses_sum != 0
            else revenue
            - wb_expenses
            - seller_expense_total
            - ad_spend_total
            + additional_income
        )
        has_cost_for_all = all(item.has_manual_cost for item in mart_rows)
        margin_percent = (
            float((profit_after_ads / revenue) * Decimal("100"))
            if revenue > 0 and has_cost_for_all
            else None
        )
        roi_percent = (
            float((profit_after_ads / cogs_total) * Decimal("100"))
            if cogs_total > 0 and has_cost_for_all
            else None
        )
        drr_percent = (
            float((ad_spend_total / revenue) * Decimal("100")) if revenue > 0 else None
        )
        distinct_days = len(
            {item.stat_date for item in mart_rows if item.stat_date is not None}
        )
        expense_quality = merge_expense_data_quality(
            [compute_expense_data_quality(item) for item in mart_rows]
        )
        return ArticleDailyEconomics(
            days_count=distinct_days,
            sales_qty=sum((item.final_sales_qty or 0) for item in mart_rows),
            returns_qty=sum((item.final_return_qty or 0) for item in mart_rows),
            net_qty=sum((item.final_net_qty or 0) for item in mart_rows),
            revenue=float(revenue),
            revenue_final=float(revenue),
            for_pay=float(for_pay),
            wb_expenses=float(wb_expenses),
            total_wb_expenses=float(wb_expenses),
            seller_cogs=float(seller_cogs),
            seller_other_expense=float(seller_other_expense),
            total_seller_expenses=float(seller_expense_total),
            total_seller_costs=float(seller_expense_total),
            additional_income=float(additional_income),
            ad_spend_operational=float(
                ad_operational_total
                if ad_operational_total > 0
                else source_ad_spend_total
            ),
            ad_spend_finance=float(ad_finance_total),
            ad_spend_final=float(ad_spend_total),
            ad_spend_source=ad_spend_source,
            ad_spend_delta=float(
                (
                    ad_operational_total
                    if ad_operational_total > 0
                    else source_ad_spend_total
                )
                - ad_finance_total
            ),
            ad_spend=float(ad_spend_total),
            raw_ad_spend=float(DashboardService._decimal(ads_metrics["raw_ad_spend"])),
            source_ad_spend=float(source_ad_spend_total),
            overallocated_ad_spend=float(
                DashboardService._decimal(ads_metrics["overallocated_ad_spend"])
            ),
            unallocated_ad_spend=float(
                DashboardService._decimal(ads_metrics["unallocated_ad_spend"])
            ),
            ads_allocation_status=str(ads_metrics["ads_allocation_status"]),
            final_profit_allowed=bool(ads_metrics["final_profit_allowed"]),
            estimated_cogs=float(cogs_total) if has_cost_for_all else None,
            estimated_profit_before_ads=float(profit_before_ads)
            if has_cost_for_all
            else None,
            estimated_profit_after_ads=float(profit_after_ads)
            if has_cost_for_all
            else None,
            net_profit_after_all_expenses=float(net_profit_all_expenses)
            if has_cost_for_all
            else None,
            expense_data_quality=expense_quality,
            margin_percent=margin_percent,
            roi_percent=roi_percent,
            drr_percent=drr_percent,
        )

    @staticmethod
    def _build_article_daily_series(
        mart_rows: list[MartSKUDaily],
        ad_rows: list[WBAdStatsDaily] | None = None,
    ) -> list[ArticleDailyPoint]:
        if not mart_rows:
            return []
        grouped: dict[date, dict[str, Decimal | int | bool]] = defaultdict(
            lambda: {
                "revenue": Decimal("0"),
                "ad_spend_operational": Decimal("0"),
                "ad_spend_finance": Decimal("0"),
                "ad_spend_final": Decimal("0"),
                "profit_before_ads": Decimal("0"),
                "profit_after_ads": Decimal("0"),
                "units": 0,
                "has_profit_before": False,
                "has_profit_after": False,
                "has_normalized_ad_fields": False,
            }
        )
        for row in mart_rows:
            if row.stat_date is None:
                continue
            bucket = grouped[row.stat_date]
            row_ad = DashboardService._row_ad_components(row)
            bucket["revenue"] = DashboardService._decimal(
                bucket["revenue"]
            ) + DashboardService._decimal(row.final_revenue)
            bucket["ad_spend_operational"] = DashboardService._decimal(
                bucket["ad_spend_operational"]
            ) + DashboardService._decimal(row_ad["ad_spend_operational"])
            bucket["ad_spend_finance"] = DashboardService._decimal(
                bucket["ad_spend_finance"]
            ) + DashboardService._decimal(row_ad["ad_spend_finance"])
            bucket["ad_spend_final"] = DashboardService._decimal(
                bucket["ad_spend_final"]
            ) + DashboardService._decimal(row_ad["ad_spend_final"])
            bucket["has_normalized_ad_fields"] = bool(
                bucket["has_normalized_ad_fields"]
            ) or (
                getattr(row, "ad_spend_operational", None) is not None
                or getattr(row, "ad_spend_finance", None) is not None
                or getattr(row, "ad_spend_final", None) is not None
                or str(getattr(row, "ad_spend_source", "") or "") != ""
            )
            bucket["units"] = int(bucket["units"]) + int(row.final_net_qty or 0)
            if row.estimated_profit_before_ads is not None:
                bucket["profit_before_ads"] = DashboardService._decimal(
                    bucket["profit_before_ads"]
                ) + DashboardService._decimal(row.estimated_profit_before_ads)
                bucket["has_profit_before"] = True
            if row.estimated_profit_after_ads is not None:
                bucket["profit_after_ads"] = DashboardService._decimal(
                    bucket["profit_after_ads"]
                ) + DashboardService._decimal(row.estimated_profit_after_ads)
                bucket["has_profit_after"] = True
        source_ads_by_date = DashboardService._ad_spend_by_date(ad_rows)
        points: list[ArticleDailyPoint] = []
        for stat_date in sorted(set(grouped) | set(source_ads_by_date)):
            bucket = grouped.get(stat_date)
            revenue = (
                DashboardService._decimal(bucket["revenue"])
                if bucket is not None
                else Decimal("0")
            )
            ad_operational = (
                DashboardService._decimal(bucket["ad_spend_operational"])
                if bucket is not None
                else Decimal("0")
            )
            ad_finance = (
                DashboardService._decimal(bucket["ad_spend_finance"])
                if bucket is not None
                else Decimal("0")
            )
            ad_final = (
                DashboardService._decimal(bucket["ad_spend_final"])
                if bucket is not None
                else Decimal("0")
            )
            source_ad = source_ads_by_date.get(stat_date, Decimal("0"))
            if ad_finance > 0:
                effective_ad = ad_final if ad_final > 0 else ad_finance
            else:
                ads_metrics = DashboardService._ads_allocation_metrics(
                    mart_ad_spend=ad_operational if ad_operational > 0 else ad_final,
                    source_ad_spend=source_ad,
                )
                effective_ad = DashboardService._decimal(ads_metrics["capped_ad_spend"])
            profit = None
            if (
                bucket is not None
                and bool(bucket["has_profit_after"])
                and bool(bucket["has_normalized_ad_fields"])
            ):
                profit = DashboardService._decimal(bucket["profit_after_ads"])
            elif bucket is not None and bool(bucket["has_profit_before"]):
                profit = DashboardService._decimal(bucket["profit_before_ads"]) - max(
                    Decimal("0"), effective_ad - ad_finance
                )
            elif bucket is not None and bool(bucket["has_profit_after"]):
                profit = (
                    DashboardService._decimal(bucket["profit_after_ads"])
                    + ad_final
                    - effective_ad
                )
            elif effective_ad > 0 and revenue == 0:
                profit = -effective_ad
            points.append(
                ArticleDailyPoint(
                    date=stat_date,
                    revenue=float(revenue),
                    ad_spend=float(effective_ad),
                    profit=float(profit) if profit is not None else None,
                    units=int(bucket["units"]) if bucket is not None else 0,
                )
            )
        return points

    @staticmethod
    def _build_article_finance_summary(
        mart_rows: list[MartSKUDaily],
        finance_rows: list[WBRealizationReportRow],
    ) -> ArticleFinanceSummary:
        if not mart_rows and not finance_rows:
            return ArticleFinanceSummary(
                report_rows_count=len(finance_rows),
                gross_units=0,
                return_units=0,
                net_units=0,
                realized_revenue=0.0,
                for_pay=0.0,
                commission=0.0,
                acquiring_fee=0.0,
                logistics=0.0,
                paid_acceptance=0.0,
                storage=0.0,
                penalties=0.0,
                deductions=0.0,
                additional_payments=0.0,
                estimated_cogs=None,
                estimated_profit_before_ads=None,
                first_report_date=min(
                    (row.rr_date for row in finance_rows if row.rr_date is not None),
                    default=None,
                ),
                last_report_date=max(
                    (row.rr_date for row in finance_rows if row.rr_date is not None),
                    default=None,
                ),
            )
        mart_revenue = sum(
            (compute_revenue_final(item) for item in mart_rows), start=Decimal("0")
        )
        mart_for_pay = sum(
            (DashboardService._decimal(item.final_for_pay) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_wb_commission = sum(
            (
                DashboardService._decimal(getattr(item, "wb_commission", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_payment_processing = sum(
            (
                DashboardService._decimal(getattr(item, "payment_processing", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_pvz_reward = sum(
            (
                DashboardService._decimal(getattr(item, "pvz_reward", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_wb_logistics = sum(
            (
                DashboardService._decimal(getattr(item, "wb_logistics", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_wb_logistics_rebill = sum(
            (
                DashboardService._decimal(getattr(item, "wb_logistics_rebill", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_acceptance = sum(
            (
                DashboardService._decimal(getattr(item, "acceptance", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_penalty = sum(
            (
                DashboardService._decimal(getattr(item, "penalty", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_deduction = sum(
            (
                DashboardService._decimal(getattr(item, "deduction", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_marketing_deduction = sum(
            (
                DashboardService._decimal(getattr(item, "marketing_deduction", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_loyalty = sum(
            (
                DashboardService._decimal(getattr(item, "loyalty", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_other_wb_expenses = sum(
            (
                DashboardService._decimal(getattr(item, "other_wb_expenses", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        mart_total_wb_expenses = sum(
            (normalized_wb_expenses_total(item) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_commission = sum(
            (DashboardService._decimal(item.commission) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_acquiring_fee = sum(
            (DashboardService._decimal(item.acquiring_fee) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_logistics = sum(
            (DashboardService._decimal(item.logistics) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_paid_acceptance = sum(
            (DashboardService._decimal(item.paid_acceptance) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_storage = sum(
            (DashboardService._decimal(item.storage) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_penalties = sum(
            (DashboardService._decimal(item.penalties) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_deductions = sum(
            (DashboardService._decimal(item.deductions) for item in mart_rows),
            start=Decimal("0"),
        )
        mart_additional_payments = sum(
            (DashboardService._decimal(item.additional_payments) for item in mart_rows),
            start=Decimal("0"),
        )
        direct_finance_totals = (
            DashboardService._aggregate_article_direct_finance_totals(finance_rows)
        )
        revenue = (
            direct_finance_totals["realized_revenue"] if finance_rows else mart_revenue
        )
        for_pay = direct_finance_totals["for_pay"] if finance_rows else mart_for_pay
        wb_commission = (
            direct_finance_totals[EXPENSE_CATEGORY_WB_COMMISSION]
            if finance_rows
            else mart_wb_commission
        )
        payment_processing = (
            direct_finance_totals[EXPENSE_CATEGORY_PAYMENT_PROCESSING]
            if finance_rows
            else mart_payment_processing
        )
        pvz_reward = (
            direct_finance_totals[EXPENSE_CATEGORY_PVZ_REWARD]
            if finance_rows
            else mart_pvz_reward
        )
        wb_logistics = (
            direct_finance_totals[EXPENSE_CATEGORY_WB_LOGISTICS]
            if finance_rows
            else mart_wb_logistics
        )
        wb_logistics_rebill = (
            direct_finance_totals[EXPENSE_CATEGORY_WB_LOGISTICS_REBILL]
            if finance_rows
            else mart_wb_logistics_rebill
        )
        acceptance = (
            direct_finance_totals[EXPENSE_CATEGORY_ACCEPTANCE]
            if finance_rows
            else mart_acceptance
        )
        penalty = (
            direct_finance_totals[EXPENSE_CATEGORY_PENALTY]
            if finance_rows
            else mart_penalty
        )
        deduction = (
            direct_finance_totals[EXPENSE_CATEGORY_DEDUCTION]
            if finance_rows
            else mart_deduction
        )
        marketing_deduction = (
            direct_finance_totals[EXPENSE_CATEGORY_MARKETING_DEDUCTION]
            if finance_rows
            else mart_marketing_deduction
        )
        loyalty = (
            direct_finance_totals[EXPENSE_CATEGORY_LOYALTY]
            if finance_rows
            else mart_loyalty
        )
        other_wb_expenses = (
            direct_finance_totals["other_wb_expenses"]
            if finance_rows
            else mart_other_wb_expenses
        )
        total_wb_expenses = (
            direct_finance_totals["total_wb_expenses"]
            if finance_rows
            else mart_total_wb_expenses
        )
        commission = wb_commission if finance_rows else mart_commission
        acquiring_fee = payment_processing if finance_rows else mart_acquiring_fee
        logistics = (
            (wb_logistics + wb_logistics_rebill) if finance_rows else mart_logistics
        )
        paid_acceptance = acceptance if finance_rows else mart_paid_acceptance
        storage = (
            direct_finance_totals[EXPENSE_CATEGORY_STORAGE]
            if finance_rows
            else mart_storage
        )
        penalties = penalty if finance_rows else mart_penalties
        deductions = (
            deduction + marketing_deduction + loyalty + other_wb_expenses
            if finance_rows
            else mart_deductions
        )
        additional_payments = (
            direct_finance_totals["additional_income"]
            if finance_rows
            else mart_additional_payments
        )
        ad_components = [
            DashboardService._row_ad_components(item) for item in mart_rows
        ]
        ad_spend_operational = sum(
            (
                DashboardService._decimal(item["ad_spend_operational"])
                for item in ad_components
            ),
            start=Decimal("0"),
        )
        mart_ad_spend_finance = sum(
            (
                DashboardService._decimal(item["ad_spend_finance"])
                for item in ad_components
            ),
            start=Decimal("0"),
        )
        ad_spend_final = sum(
            (
                DashboardService._decimal(item["ad_spend_final"])
                for item in ad_components
            ),
            start=Decimal("0"),
        )
        ad_spend_finance = (
            marketing_deduction if finance_rows else mart_ad_spend_finance
        )
        final_ad_spend = (
            ad_spend_finance
            if ad_spend_finance > 0
            else ad_spend_final
            if ad_spend_final > 0
            else ad_spend_operational
        )
        cogs = sum(
            (
                DashboardService._decimal(item.estimated_cogs)
                for item in mart_rows
                if item.estimated_cogs is not None
            ),
            start=Decimal("0"),
        )
        seller_cogs = sum(
            (
                DashboardService._decimal(
                    getattr(item, "seller_cogs", getattr(item, "estimated_cogs", None))
                )
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        seller_other_expense = sum(
            (
                DashboardService._decimal(getattr(item, "seller_other_expense", None))
                for item in mart_rows
            ),
            start=Decimal("0"),
        )
        additional_income = sum(
            (expense_additional_income(item) for item in mart_rows), start=Decimal("0")
        )
        profit_before_ads = sum(
            (
                DashboardService._decimal(
                    getattr(item, "estimated_profit_before_ads", None)
                )
                for item in mart_rows
                if getattr(item, "estimated_profit_before_ads", None) is not None
            ),
            start=Decimal("0"),
        )
        net_profit_after_all_expenses = sum(
            (
                DashboardService._decimal(
                    getattr(item, "net_profit_after_all_expenses", None)
                )
                for item in mart_rows
                if getattr(item, "net_profit_after_all_expenses", None) is not None
            ),
            start=Decimal("0"),
        )
        has_cost_for_all = bool(mart_rows) and all(
            bool(getattr(item, "has_manual_cost", False)) for item in mart_rows
        )
        additional_income_out = (
            direct_finance_totals["additional_income"]
            if finance_rows
            else additional_income
        )
        expense_quality = merge_expense_data_quality(
            [
                *(compute_expense_data_quality(item) for item in mart_rows),
                direct_finance_totals["expense_data_quality"],
            ]
        )
        return ArticleFinanceSummary(
            report_rows_count=len(finance_rows),
            gross_units=int(direct_finance_totals["gross_units"])
            if finance_rows
            else sum((item.final_sales_qty or 0) for item in mart_rows),
            return_units=int(direct_finance_totals["return_units"])
            if finance_rows
            else sum((item.final_return_qty or 0) for item in mart_rows),
            net_units=int(direct_finance_totals["net_units"])
            if finance_rows
            else sum((item.final_net_qty or 0) for item in mart_rows),
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
            total_wb_expenses=float(total_wb_expenses),
            commission=float(commission),
            acquiring_fee=float(acquiring_fee),
            logistics=float(logistics),
            paid_acceptance=float(paid_acceptance),
            storage=float(storage),
            penalties=float(penalties),
            deductions=float(deductions),
            additional_payments=float(
                additional_payments if finance_rows else additional_income
            ),
            ad_spend_operational=float(ad_spend_operational),
            ad_spend_finance=float(ad_spend_finance),
            ad_spend_final=float(final_ad_spend),
            ad_spend_source=(
                AD_SPEND_SOURCE_FINANCE
                if ad_spend_finance > 0
                else AD_SPEND_SOURCE_OPERATIONAL
                if (ad_spend_operational > 0 or ad_spend_final > 0)
                else AD_SPEND_SOURCE_NONE
            ),
            ad_spend_delta=float(ad_spend_operational - ad_spend_finance),
            estimated_cogs=float(cogs) if has_cost_for_all else None,
            seller_cogs=float(seller_cogs),
            seller_other_expense=float(seller_other_expense),
            total_seller_expenses=float(seller_cogs + seller_other_expense),
            total_seller_costs=float(seller_cogs + seller_other_expense),
            additional_income=float(additional_income_out),
            estimated_profit_before_ads=float(profit_before_ads)
            if has_cost_for_all
            else None,
            net_profit_after_all_expenses=float(net_profit_after_all_expenses)
            if has_cost_for_all
            else None,
            expense_data_quality=expense_quality,
            first_report_date=min(
                (row.rr_date for row in finance_rows if row.rr_date is not None),
                default=None,
            ),
            last_report_date=max(
                (row.rr_date for row in finance_rows if row.rr_date is not None),
                default=None,
            ),
        )

    @classmethod
    def _aggregate_article_direct_finance_totals(
        cls, finance_rows: list[WBRealizationReportRow]
    ) -> dict[str, Decimal | str | int]:
        from app.services.marts import MartService

        totals: dict[str, Decimal] = {
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
        realized_revenue = Decimal("0")
        for_pay = Decimal("0")
        gross_units = 0
        return_units = 0
        has_unclassified = False
        for row in finance_rows:
            if cls._finance_row_is_reconcilable(row):
                quantity = abs(int(getattr(row, "quantity", 0) or 0))
                if cls._row_sign(row) < 0:
                    return_units += quantity
                else:
                    gross_units += quantity
                realized_revenue += cls._signed_finance_amount(
                    row, getattr(row, "retail_amount", None)
                )
                for_pay += cls._signed_finance_amount(
                    row, getattr(row, "for_pay", None)
                )
            details = MartService._finance_expense_details(row)
            detail_totals = details.get("totals") or {}
            for category in totals:
                totals[category] += cls._decimal(detail_totals.get(category))
            if cls._decimal(detail_totals.get(EXPENSE_CATEGORY_UNCLASSIFIED)) != 0:
                has_unclassified = True
        total_wb_expenses = (
            totals[EXPENSE_CATEGORY_WB_COMMISSION]
            + totals[EXPENSE_CATEGORY_PAYMENT_PROCESSING]
            + totals[EXPENSE_CATEGORY_PVZ_REWARD]
            + totals[EXPENSE_CATEGORY_WB_LOGISTICS]
            + totals[EXPENSE_CATEGORY_WB_LOGISTICS_REBILL]
            + totals[EXPENSE_CATEGORY_STORAGE]
            + totals[EXPENSE_CATEGORY_ACCEPTANCE]
            + totals[EXPENSE_CATEGORY_PENALTY]
            + totals[EXPENSE_CATEGORY_DEDUCTION]
            + totals[EXPENSE_CATEGORY_LOYALTY]
            + totals[EXPENSE_CATEGORY_UNCLASSIFIED]
        )
        return {
            **totals,
            "gross_units": Decimal(str(gross_units)),
            "return_units": Decimal(str(return_units)),
            "net_units": Decimal(str(gross_units - return_units)),
            "realized_revenue": realized_revenue,
            "for_pay": for_pay,
            "other_wb_expenses": totals[EXPENSE_CATEGORY_UNCLASSIFIED],
            "total_wb_expenses": total_wb_expenses,
            "additional_income": (
                totals[EXPENSE_CATEGORY_ADDITIONAL_PAYMENT]
                if totals[EXPENSE_CATEGORY_ADDITIONAL_PAYMENT] > 0
                else Decimal("0")
            ),
            "expense_data_quality": (
                "unclassified_present" if has_unclassified else "complete"
            ),
        }

    @staticmethod
    def _build_article_reconciliation_summary(
        mart_rows: list[MartSKUDaily],
        issues: list[DataQualityIssue],
        *,
        finance_rows: list[WBRealizationReportRow],
        operational_revenue_total: Decimal | None = None,
    ) -> ArticleReconciliationSummary:
        pending_count = 0
        warning_count = 0
        error_count = 0
        ignored_count = 0
        for issue in issues:
            payload = issue.payload or {}
            classification_status = str(
                payload.get("classificationStatus") or ""
            ).lower()
            age_bucket = str(payload.get("ageBucket") or "").lower()
            if classification_status == "ignored":
                ignored_count += 1
                continue
            if age_bucket == "pending":
                pending_count += 1
            elif age_bucket == "warning" or issue.severity == "warning":
                warning_count += 1
            elif issue.severity == "error":
                error_count += 1
        mart_revenue_total = sum(
            (DashboardService._decimal(item.final_revenue) for item in mart_rows),
            start=Decimal("0"),
        )
        finance_report_revenue_total = sum(
            (
                DashboardService._signed_finance_amount(row, row.retail_amount)
                for row in finance_rows
                if DashboardService._finance_row_is_reconcilable(row)
            ),
            start=Decimal("0"),
        )
        article_revenue_total = mart_revenue_total
        difference_amount = finance_report_revenue_total - mart_revenue_total
        difference_ratio = None
        if mart_revenue_total != 0:
            difference_ratio = float(
                (difference_amount / mart_revenue_total) * Decimal("100")
            )
        mart_matches_finance = abs(difference_amount) <= Decimal("0.01")
        finance_matches_operational = None
        if operational_revenue_total is not None:
            finance_matches_operational = abs(
                finance_report_revenue_total - operational_revenue_total
            ) <= Decimal("0.01")
        mismatch_reason = None
        if not mart_matches_finance:
            mismatch_reason = "finance_vs_mart_revenue_mismatch"
        return ArticleReconciliationSummary(
            pending_count=pending_count,
            warning_count=warning_count,
            error_count=error_count,
            ignored_count=ignored_count,
            mart_matches_article=True,
            mart_matches_finance=mart_matches_finance,
            finance_matches_operational=finance_matches_operational,
            revenue_matches_mart=mart_matches_finance,
            mart_revenue_total=float(mart_revenue_total),
            article_revenue_total=float(article_revenue_total),
            finance_report_revenue_total=float(finance_report_revenue_total),
            difference_amount=float(difference_amount),
            difference_ratio=difference_ratio,
            difference_ratio_percent=difference_ratio,
            mismatch_reason=mismatch_reason,
        )

    @staticmethod
    def _date_for_row(row: WBRealizationReportRow) -> date | None:
        return row.rr_date or (row.sale_dt.date() if row.sale_dt else None)

    @staticmethod
    def _total_unit_cost(cost: ManualCost) -> Decimal:
        return manual_cost_total_unit_cost(cost)

    @staticmethod
    def _row_sign(row: WBRealizationReportRow) -> int:
        doc_type = (getattr(row, "doc_type_name", None) or "").lower()
        if "возврат" in doc_type or "return" in doc_type:
            return -1
        if (
            DashboardService._decimal(getattr(row, "retail_amount", None)) < 0
            or DashboardService._decimal(getattr(row, "for_pay", None)) < 0
        ):
            return -1
        return 1

    @staticmethod
    def _cost_is_active(cost: ManualCost, at_date: date | None) -> bool:
        if at_date is None:
            return True
        if cost.valid_from is not None and cost.valid_from > at_date:
            return False
        if cost.valid_to is not None and cost.valid_to < at_date:
            return False
        return True

    @staticmethod
    def _resolve_sku(
        sku_rows: Iterable[CoreSKU],
        *,
        vendor_code: str | None,
        nm_id: int | None,
        barcode: str | None,
        tech_size: str | None = None,
    ) -> CoreSKU | None:
        rules = [
            [
                sku
                for sku in sku_rows
                if sku.vendor_code == vendor_code
                and sku.barcode == barcode
                and sku.tech_size == tech_size
            ],
            [sku for sku in sku_rows if sku.nm_id == nm_id and sku.barcode == barcode],
            [sku for sku in sku_rows if sku.barcode == barcode],
            [
                sku
                for sku in sku_rows
                if sku.nm_id == nm_id and sku.tech_size == tech_size
            ],
            [
                sku
                for sku in sku_rows
                if sku.vendor_code == vendor_code and sku.tech_size == tech_size
            ],
            [sku for sku in sku_rows if sku.vendor_code == vendor_code],
        ]
        for matches in rules:
            if len(matches) == 1:
                return matches[0]
        return None

    def _match_cost_for_sku(
        self,
        costs: Iterable[ManualCost],
        *,
        sku_id: int | None,
        at_date: date | None,
    ) -> ManualCost | None:
        if sku_id is None:
            return None
        candidates = [
            cost
            for cost in costs
            if cost.sku_id == sku_id and self._cost_is_active(cost, at_date)
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda cost: (cost.valid_from or date.min, cost.id), reverse=True
        )
        return candidates[0]

    async def _load_current_orders(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        orders_current = orders_current_subquery()
        stmt = select(orders_current).where(orders_current.c.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(orders_current.c.nm_id == nm_id)
        if date_from is not None:
            stmt = stmt.where(
                orders_current.c.date
                >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                orders_current.c.date <= datetime.combine(date_to, datetime.max.time())
            )
        return [dict(row) for row in (await session.execute(stmt)).mappings().all()]

    async def _load_current_sales(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[dict]:
        sales_current = sales_current_subquery()
        stmt = select(sales_current).where(sales_current.c.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(sales_current.c.nm_id == nm_id)
        if date_from is not None:
            stmt = stmt.where(
                sales_current.c.date >= datetime.combine(date_from, datetime.min.time())
            )
        if date_to is not None:
            stmt = stmt.where(
                sales_current.c.date <= datetime.combine(date_to, datetime.max.time())
            )
        return [dict(row) for row in (await session.execute(stmt)).mappings().all()]

    def _match_cost(
        self,
        costs: Iterable[ManualCost],
        *,
        vendor_code: str | None,
        nm_id: int | None,
        barcode: str | None,
        at_date: date | None,
    ) -> tuple[ManualCost | None, str | None]:
        candidates: list[tuple[int, date, ManualCost, str]] = []
        for cost in costs:
            if not self._cost_is_active(cost, at_date):
                continue
            if vendor_code and cost.vendor_code == vendor_code:
                candidates.append((0, cost.valid_from or date.min, cost, "vendor_code"))
            elif nm_id is not None and cost.nm_id == nm_id:
                candidates.append((1, cost.valid_from or date.min, cost, "nm_id"))
            elif barcode and cost.barcode == barcode:
                candidates.append((2, cost.valid_from or date.min, cost, "barcode"))
        if not candidates:
            return None, None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=False)
        same_priority = [item for item in candidates if item[0] == candidates[0][0]]
        same_priority.sort(key=lambda item: item[1], reverse=True)
        best = same_priority[0]
        return best[2], best[3]

    async def _load_cost_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[ManualCost]:
        stmt = select(ManualCost).where(ManualCost.account_id == account_id)
        if date_to is not None:
            stmt = stmt.where(
                or_(ManualCost.valid_from.is_(None), ManualCost.valid_from <= date_to)
            )
        if date_from is not None:
            stmt = stmt.where(
                or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= date_from)
            )
        return list(
            (
                await session.execute(
                    stmt.order_by(ManualCost.valid_from.desc().nullslast())
                )
            ).scalars()
        )

    @staticmethod
    def _sku_profitability_mart_columns() -> tuple[Any, ...]:
        return (
            MartSKUDaily.sku_id,
            MartSKUDaily.nm_id,
            MartSKUDaily.vendor_code,
            MartSKUDaily.barcode,
            MartSKUDaily.title,
            MartSKUDaily.brand,
            MartSKUDaily.subject_name,
            MartSKUDaily.finance_rows,
            MartSKUDaily.sale_rows,
            MartSKUDaily.final_sales_qty,
            MartSKUDaily.final_return_qty,
            MartSKUDaily.final_net_qty,
            MartSKUDaily.final_revenue,
            MartSKUDaily.final_for_pay,
            MartSKUDaily.final_revenue_source,
            MartSKUDaily.wb_commission,
            MartSKUDaily.payment_processing,
            MartSKUDaily.pvz_reward,
            MartSKUDaily.wb_logistics,
            MartSKUDaily.wb_logistics_rebill,
            MartSKUDaily.acceptance,
            MartSKUDaily.penalty,
            MartSKUDaily.deduction,
            MartSKUDaily.marketing_deduction,
            MartSKUDaily.loyalty,
            MartSKUDaily.other_wb_expenses,
            MartSKUDaily.total_wb_expenses,
            MartSKUDaily.commission,
            MartSKUDaily.acquiring_fee,
            MartSKUDaily.logistics,
            MartSKUDaily.paid_acceptance,
            MartSKUDaily.storage,
            MartSKUDaily.penalties,
            MartSKUDaily.deductions,
            MartSKUDaily.additional_payments,
            MartSKUDaily.ad_spend_operational,
            MartSKUDaily.ad_spend_finance,
            MartSKUDaily.ad_spend_final,
            MartSKUDaily.ad_spend_source,
            MartSKUDaily.ad_spend_delta,
            MartSKUDaily.ad_spend,
            MartSKUDaily.estimated_cogs,
            MartSKUDaily.seller_cogs,
            MartSKUDaily.seller_other_expense,
            MartSKUDaily.total_seller_expenses,
            MartSKUDaily.estimated_profit_before_ads,
            MartSKUDaily.estimated_profit_after_ads,
            MartSKUDaily.net_profit_after_all_expenses,
            MartSKUDaily.closing_stock_qty,
            MartSKUDaily.has_manual_cost,
            MartSKUDaily.has_real_manual_cost,
            MartSKUDaily.has_placeholder_cost,
            MartSKUDaily.cost_source,
        )

    async def _load_sku_profitability_mart_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> list[Any]:
        mart_stmt = select(*self._sku_profitability_mart_columns()).where(
            MartSKUDaily.account_id == account_id
        )
        if date_from is not None:
            mart_stmt = mart_stmt.where(MartSKUDaily.stat_date >= date_from)
        if date_to is not None:
            mart_stmt = mart_stmt.where(MartSKUDaily.stat_date <= date_to)
        result = await session.execute(mart_stmt)
        rows = list(result.all())
        if rows and hasattr(rows[0], "_mapping"):
            return [SimpleNamespace(**dict(row._mapping)) for row in rows]
        scalar_rows = result.scalars() if hasattr(result, "scalars") else []
        return list(scalar_rows)

    async def sku_profitability(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[SKUProfitabilityRow]:
        mart_rows = await self._load_sku_profitability_mart_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )

        if not mart_rows:
            return []

        cost_trust_policy = await self._cost_trust_policy(
            session, account_id=account_id
        )
        source_ads_by_nm: dict[int, Decimal] = {}
        if session is not None:
            ad_stmt = select(
                WBAdStatsDaily.nm_id, func.coalesce(func.sum(WBAdStatsDaily.sum), 0)
            ).where(
                WBAdStatsDaily.account_id == account_id,
                WBAdStatsDaily.nm_id.is_not(None),
            )
            if date_from is not None:
                ad_stmt = ad_stmt.where(WBAdStatsDaily.stat_date >= date_from)
            if date_to is not None:
                ad_stmt = ad_stmt.where(WBAdStatsDaily.stat_date <= date_to)
            ad_stmt = ad_stmt.group_by(WBAdStatsDaily.nm_id)
            source_ads_by_nm = {
                int(nm_id): self._decimal(total)
                for nm_id, total in (await session.execute(ad_stmt)).all()
                if nm_id is not None
            }
        buckets: dict[tuple[object, ...], dict[str, object]] = {}
        for row in mart_rows:
            key = (
                ("sku", row.sku_id)
                if row.sku_id is not None
                else ("fallback", row.nm_id, row.vendor_code, row.barcode)
            )
            bucket = buckets.setdefault(
                key,
                {
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "barcode": row.barcode,
                    "title": row.title,
                    "brand": row.brand,
                    "subject_name": row.subject_name,
                    "finance_rows": 0,
                    "gross_units": 0,
                    "return_units": 0,
                    "net_units": 0,
                    "realized_revenue": Decimal("0"),
                    "for_pay": Decimal("0"),
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
                    "ad_spend": Decimal("0"),
                    "estimated_cogs": Decimal("0"),
                    "seller_cogs": Decimal("0"),
                    "seller_other_expense": Decimal("0"),
                    "total_seller_expenses": Decimal("0"),
                    "additional_income": Decimal("0"),
                    "estimated_profit_before_ads": Decimal("0"),
                    "estimated_profit_after_ads": Decimal("0"),
                    "net_profit_after_all_expenses": Decimal("0"),
                    "matched_cost_rows": 0,
                    "has_manual_cost": False,
                    "cost_required_rows": 0,
                    "cost_ready_rows": 0,
                    "real_cost_ready_rows": 0,
                    "placeholder_cost_rows": 0,
                    "closing_stock_qty": None,
                    "cost_sources": set(),
                },
            )
            bucket["sku_id"] = bucket["sku_id"] or row.sku_id
            bucket["nm_id"] = bucket["nm_id"] or row.nm_id
            bucket["vendor_code"] = bucket["vendor_code"] or row.vendor_code
            bucket["barcode"] = bucket["barcode"] or row.barcode
            bucket["title"] = bucket["title"] or row.title
            bucket["brand"] = bucket["brand"] or row.brand
            bucket["subject_name"] = bucket["subject_name"] or row.subject_name
            bucket["finance_rows"] = int(bucket["finance_rows"]) + int(
                row.finance_rows or 0
            )
            bucket["gross_units"] = int(bucket["gross_units"]) + int(
                row.final_sales_qty or 0
            )
            bucket["return_units"] = int(bucket["return_units"]) + int(
                row.final_return_qty or 0
            )
            bucket["net_units"] = int(bucket["net_units"]) + int(row.final_net_qty or 0)
            bucket["realized_revenue"] = self._decimal(
                bucket["realized_revenue"]
            ) + self._decimal(row.final_revenue)
            bucket["for_pay"] = self._decimal(bucket["for_pay"]) + self._decimal(
                row.final_for_pay
            )
            bucket["commission"] = self._decimal(bucket["commission"]) + self._decimal(
                row.commission
            )
            bucket["acquiring_fee"] = self._decimal(
                bucket["acquiring_fee"]
            ) + self._decimal(row.acquiring_fee)
            bucket["logistics"] = self._decimal(bucket["logistics"]) + self._decimal(
                row.logistics
            )
            bucket["paid_acceptance"] = self._decimal(
                bucket["paid_acceptance"]
            ) + self._decimal(row.paid_acceptance)
            bucket["storage"] = self._decimal(bucket["storage"]) + self._decimal(
                row.storage
            )
            bucket["penalties"] = self._decimal(bucket["penalties"]) + self._decimal(
                row.penalties
            )
            bucket["deductions"] = self._decimal(bucket["deductions"]) + self._decimal(
                row.deductions
            )
            bucket["additional_payments"] = self._decimal(
                bucket["additional_payments"]
            ) + self._decimal(row.additional_payments)
            bucket["wb_commission"] = self._decimal(
                bucket["wb_commission"]
            ) + self._decimal(getattr(row, "wb_commission", None))
            bucket["payment_processing"] = self._decimal(
                bucket["payment_processing"]
            ) + self._decimal(getattr(row, "payment_processing", None))
            bucket["pvz_reward"] = self._decimal(bucket["pvz_reward"]) + self._decimal(
                getattr(row, "pvz_reward", None)
            )
            bucket["wb_logistics"] = self._decimal(
                bucket["wb_logistics"]
            ) + self._decimal(getattr(row, "wb_logistics", None))
            bucket["wb_logistics_rebill"] = self._decimal(
                bucket["wb_logistics_rebill"]
            ) + self._decimal(getattr(row, "wb_logistics_rebill", None))
            bucket["acceptance"] = self._decimal(bucket["acceptance"]) + self._decimal(
                getattr(row, "acceptance", None)
            )
            bucket["penalty"] = self._decimal(bucket["penalty"]) + self._decimal(
                getattr(row, "penalty", None)
            )
            bucket["deduction"] = self._decimal(bucket["deduction"]) + self._decimal(
                getattr(row, "deduction", None)
            )
            bucket["marketing_deduction"] = self._decimal(
                bucket["marketing_deduction"]
            ) + self._decimal(getattr(row, "marketing_deduction", None))
            bucket["loyalty"] = self._decimal(bucket["loyalty"]) + self._decimal(
                getattr(row, "loyalty", None)
            )
            bucket["other_wb_expenses"] = self._decimal(
                bucket["other_wb_expenses"]
            ) + self._decimal(getattr(row, "other_wb_expenses", None))
            bucket["total_wb_expenses"] = self._decimal(
                bucket["total_wb_expenses"]
            ) + normalized_wb_expenses_total(row)
            row_ad = self._row_ad_components(row)
            bucket["ad_spend_operational"] = self._decimal(
                bucket["ad_spend_operational"]
            ) + self._decimal(row_ad["ad_spend_operational"])
            bucket["ad_spend_finance"] = self._decimal(
                bucket["ad_spend_finance"]
            ) + self._decimal(row_ad["ad_spend_finance"])
            bucket["ad_spend_final"] = self._decimal(
                bucket["ad_spend_final"]
            ) + self._decimal(row_ad["ad_spend_final"])
            bucket["ad_spend_delta"] = self._decimal(
                bucket["ad_spend_delta"]
            ) + self._decimal(row_ad["ad_spend_delta"])
            bucket["ad_spend"] = self._decimal(bucket["ad_spend"]) + self._decimal(
                row_ad["ad_spend_final"]
            )
            bucket["estimated_cogs"] = self._decimal(
                bucket["estimated_cogs"]
            ) + self._decimal(row.estimated_cogs)
            bucket["seller_cogs"] = self._decimal(
                bucket["seller_cogs"]
            ) + self._decimal(
                getattr(row, "seller_cogs", getattr(row, "estimated_cogs", None))
            )
            bucket["seller_other_expense"] = self._decimal(
                bucket["seller_other_expense"]
            ) + self._decimal(getattr(row, "seller_other_expense", None))
            bucket["total_seller_expenses"] = self._decimal(
                bucket["total_seller_expenses"]
            ) + self._decimal(getattr(row, "total_seller_expenses", None))
            bucket["additional_income"] = self._decimal(
                bucket["additional_income"]
            ) + expense_additional_income(row)
            bucket["estimated_profit_before_ads"] = self._decimal(
                bucket["estimated_profit_before_ads"]
            ) + self._decimal(getattr(row, "estimated_profit_before_ads", None))
            bucket["estimated_profit_after_ads"] = self._decimal(
                bucket["estimated_profit_after_ads"]
            ) + self._decimal(getattr(row, "estimated_profit_after_ads", None))
            bucket["net_profit_after_all_expenses"] = self._decimal(
                bucket["net_profit_after_all_expenses"]
            ) + self._decimal(getattr(row, "net_profit_after_all_expenses", None))
            bucket["closing_stock_qty"] = (
                row.closing_stock_qty
                if row.closing_stock_qty is not None
                else bucket["closing_stock_qty"]
            )
            requires_cost = bool(
                int(row.final_sales_qty or 0)
                or int(row.final_return_qty or 0)
                or int(row.final_net_qty or 0)
                or self._decimal(row.final_revenue) != 0
                or row.sale_rows
                or row.finance_rows
            )
            if requires_cost:
                bucket["cost_required_rows"] = int(bucket["cost_required_rows"]) + 1
            if row.has_manual_cost:
                bucket["matched_cost_rows"] = int(bucket["matched_cost_rows"]) + 1
                bucket["has_manual_cost"] = True
                if requires_cost:
                    bucket["cost_ready_rows"] = int(bucket["cost_ready_rows"]) + 1
                if row.has_real_manual_cost and requires_cost:
                    bucket["real_cost_ready_rows"] = (
                        int(bucket["real_cost_ready_rows"]) + 1
                    )
                if row.has_placeholder_cost and requires_cost:
                    bucket["placeholder_cost_rows"] = (
                        int(bucket["placeholder_cost_rows"]) + 1
                    )
                source = row.cost_source or row.final_revenue_source or "unknown"
                cast_sources = bucket["cost_sources"]
                if isinstance(cast_sources, set):
                    cast_sources.add(source)

        revenue_by_nm: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
        units_by_nm: dict[int, int] = defaultdict(int)
        count_by_nm: dict[int, int] = defaultdict(int)
        for key, bucket in buckets.items():
            nm_key = bucket["nm_id"]
            if nm_key is None:
                continue
            count_by_nm[int(nm_key)] += 1
            bucket_revenue = self._decimal(bucket["realized_revenue"])
            if bucket_revenue > 0:
                revenue_by_nm[int(nm_key)] += bucket_revenue
            bucket_units = int(bucket["net_units"] or bucket["gross_units"] or 0)
            units_by_nm[int(nm_key)] += max(0, bucket_units)

        result: list[SKUProfitabilityRow] = []
        for key, bucket in buckets.items():
            cost_sources = bucket["cost_sources"]
            cost_source = None
            if isinstance(cost_sources, set) and cost_sources:
                cost_source = (
                    next(iter(cost_sources)) if len(cost_sources) == 1 else "mixed"
                )
            realized_revenue = self._decimal(bucket["realized_revenue"])
            estimated_cogs = self._decimal(bucket["estimated_cogs"])
            ad_spend_operational = self._decimal(bucket["ad_spend_operational"])
            ad_spend_finance = self._decimal(bucket["ad_spend_finance"])
            ad_spend_final = self._decimal(bucket["ad_spend_final"])
            mart_ad_spend = (
                ad_spend_operational
                if ad_spend_operational > 0
                else self._decimal(bucket["ad_spend"])
            )
            nm_id_for_ads = (
                int(bucket["nm_id"]) if bucket["nm_id"] is not None else None
            )
            source_ad_spend = Decimal("0")
            if nm_id_for_ads is not None:
                nm_source_total = source_ads_by_nm.get(nm_id_for_ads, Decimal("0"))
                if nm_source_total > 0:
                    nm_revenue = revenue_by_nm.get(nm_id_for_ads, Decimal("0"))
                    nm_units = units_by_nm.get(nm_id_for_ads, 0)
                    if nm_revenue > 0:
                        if realized_revenue > 0:
                            source_ad_spend = (
                                nm_source_total * realized_revenue / nm_revenue
                            )
                    elif nm_units > 0:
                        bucket_units = max(
                            0, int(bucket["net_units"] or bucket["gross_units"] or 0)
                        )
                        if bucket_units > 0:
                            source_ad_spend = (
                                nm_source_total
                                * Decimal(bucket_units)
                                / Decimal(nm_units)
                            )
                    elif count_by_nm.get(nm_id_for_ads, 0) > 0:
                        source_ad_spend = nm_source_total / Decimal(
                            count_by_nm[nm_id_for_ads]
                        )
            if ad_spend_finance > 0:
                effective_ad_spend = (
                    ad_spend_final if ad_spend_final > 0 else ad_spend_finance
                )
                ads_metrics = {
                    "raw_ad_spend": effective_ad_spend,
                    "capped_ad_spend": effective_ad_spend,
                    "overallocated_ad_spend": Decimal("0"),
                    "unallocated_ad_spend": max(
                        Decimal("0"),
                        source_ad_spend
                        - (
                            ad_spend_operational
                            if ad_spend_operational > 0
                            else source_ad_spend
                        ),
                    ),
                    "ads_allocation_status": "finance_final",
                    "final_profit_allowed": True,
                }
                ad_spend_source = AD_SPEND_SOURCE_FINANCE
            else:
                ads_metrics = self._ads_allocation_metrics(
                    mart_ad_spend=mart_ad_spend,
                    source_ad_spend=source_ad_spend,
                )
                effective_ad_spend = self._decimal(ads_metrics["capped_ad_spend"])
                ad_spend_source = (
                    AD_SPEND_SOURCE_OPERATIONAL
                    if effective_ad_spend > 0
                    else AD_SPEND_SOURCE_NONE
                )
            required_cost_rows = int(bucket["cost_required_rows"])
            has_complete_manual_cost = (
                required_cost_rows == 0
                or int(bucket["cost_ready_rows"]) == required_cost_rows
            )
            has_complete_real_cost = (
                required_cost_rows == 0
                or int(bucket["real_cost_ready_rows"]) == required_cost_rows
            )
            has_placeholder_cost = int(bucket["placeholder_cost_rows"]) > 0
            profit = None
            margin_percent = None
            roi_percent = None
            total_wb_expenses = self._decimal(bucket["total_wb_expenses"])
            seller_cogs = self._decimal(bucket["seller_cogs"])
            seller_other_expense = self._decimal(bucket["seller_other_expense"])
            total_seller_expenses = self._decimal(bucket["total_seller_expenses"])
            additional_income = self._decimal(bucket["additional_income"])
            net_profit_after_all_expenses_value = self._decimal(
                bucket["net_profit_after_all_expenses"]
            )
            if has_complete_manual_cost:
                computed_profit = (
                    realized_revenue
                    - total_wb_expenses
                    - total_seller_expenses
                    - effective_ad_spend
                    + additional_income
                )
                profit = computed_profit
                margin_percent = (
                    float((computed_profit / realized_revenue) * Decimal("100"))
                    if realized_revenue > 0
                    else None
                )
                roi_percent = (
                    float((computed_profit / estimated_cogs) * Decimal("100"))
                    if estimated_cogs > 0
                    else None
                )
                net_profit_after_all_expenses_value = computed_profit
            drr_percent = (
                float((effective_ad_spend / realized_revenue) * Decimal("100"))
                if realized_revenue > 0
                else None
            )
            finance_rows_value = int(bucket["finance_rows"] or 0)
            expense_quality = compute_expense_data_quality(
                SimpleNamespace(
                    final_revenue_source="finance"
                    if finance_rows_value > 0
                    else "operational",
                    finance_rows=finance_rows_value,
                    other_wb_expenses=bucket["other_wb_expenses"],
                    ad_spend_operational=ad_spend_operational,
                    ad_spend_finance=ad_spend_finance,
                    ad_spend_final=effective_ad_spend,
                    ad_spend_source=ad_spend_source,
                )
            )
            truth_level = cost_truth_level_from_flags(
                has_manual_cost=has_complete_manual_cost,
                has_real_manual_cost=has_complete_real_cost,
                has_placeholder_cost=has_placeholder_cost,
                cost_source=cost_source,
            )
            raw_blocked_reasons = blocked_reasons_for_profit_row(
                has_manual_cost=has_complete_manual_cost,
                has_real_manual_cost=has_complete_real_cost,
                has_placeholder_cost=has_placeholder_cost,
                finance_rows=int(bucket["finance_rows"]),
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            blocked_reasons = normalize_blocked_reasons_for_cost_policy(
                raw_blocked_reasons,
                has_manual_cost=has_complete_manual_cost,
                has_real_manual_cost=has_complete_real_cost,
                has_placeholder_cost=has_placeholder_cost,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            effective_business_trusted = effective_cost_is_business_trusted(
                has_manual_cost=has_complete_manual_cost,
                has_real_manual_cost=has_complete_real_cost,
                has_placeholder_cost=has_placeholder_cost,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            cost_final_accepted = final_cost_is_accepted(
                has_manual_cost=has_complete_manual_cost,
                has_real_manual_cost=has_complete_real_cost,
                has_placeholder_cost=has_placeholder_cost,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            public_trust_state = self._public_row_trust_state(
                effective_business_trusted=effective_business_trusted,
                cost_final_accepted=cost_final_accepted,
                has_placeholder_cost=has_placeholder_cost,
                finance_rows=int(bucket["finance_rows"]),
                blocked_reasons=blocked_reasons,
            )
            operational_trusted = public_trust_state in {
                "operational_provisional",
                "financial_final",
            }
            result.append(
                SKUProfitabilityRow(
                    sku_id=bucket["sku_id"],
                    nm_id=bucket["nm_id"],
                    vendor_code=bucket["vendor_code"],
                    barcode=bucket["barcode"],
                    title=bucket["title"],
                    brand=bucket["brand"],
                    subject_name=bucket["subject_name"],
                    finance_rows=int(bucket["finance_rows"]),
                    gross_units=int(bucket["gross_units"]),
                    return_units=int(bucket["return_units"]),
                    net_units=int(bucket["net_units"]),
                    realized_revenue=float(self._decimal(bucket["realized_revenue"])),
                    revenue_final=float(self._decimal(bucket["realized_revenue"])),
                    for_pay=float(self._decimal(bucket["for_pay"])),
                    wb_commission=float(self._decimal(bucket["wb_commission"])),
                    payment_processing=float(
                        self._decimal(bucket["payment_processing"])
                    ),
                    pvz_reward=float(self._decimal(bucket["pvz_reward"])),
                    wb_logistics=float(self._decimal(bucket["wb_logistics"])),
                    wb_logistics_rebill=float(
                        self._decimal(bucket["wb_logistics_rebill"])
                    ),
                    acceptance=float(self._decimal(bucket["acceptance"])),
                    penalty=float(self._decimal(bucket["penalty"])),
                    deduction=float(self._decimal(bucket["deduction"])),
                    marketing_deduction=float(
                        self._decimal(bucket["marketing_deduction"])
                    ),
                    loyalty=float(self._decimal(bucket["loyalty"])),
                    other_wb_expenses=float(self._decimal(bucket["other_wb_expenses"])),
                    total_wb_expenses=float(total_wb_expenses),
                    commission=float(self._decimal(bucket["commission"])),
                    acquiring_fee=float(self._decimal(bucket["acquiring_fee"])),
                    logistics=float(self._decimal(bucket["logistics"])),
                    paid_acceptance=float(self._decimal(bucket["paid_acceptance"])),
                    storage=float(self._decimal(bucket["storage"])),
                    penalties=float(self._decimal(bucket["penalties"])),
                    deductions=float(self._decimal(bucket["deductions"])),
                    additional_payments=float(
                        self._decimal(bucket["additional_income"])
                    ),
                    ad_spend=float(effective_ad_spend),
                    ad_spend_operational=float(
                        ad_spend_operational
                        if ad_spend_operational > 0
                        else source_ad_spend
                    ),
                    ad_spend_finance=float(ad_spend_finance),
                    ad_spend_final=float(effective_ad_spend),
                    ad_spend_source=ad_spend_source,
                    ad_spend_delta=float(
                        (
                            ad_spend_operational
                            if ad_spend_operational > 0
                            else source_ad_spend
                        )
                        - ad_spend_finance
                    ),
                    raw_ad_spend=float(self._decimal(ads_metrics["raw_ad_spend"])),
                    source_ad_spend=float(source_ad_spend),
                    capped_ad_spend=float(effective_ad_spend),
                    overallocated_ad_spend=float(
                        self._decimal(ads_metrics["overallocated_ad_spend"])
                    ),
                    unallocated_ad_spend=float(
                        self._decimal(ads_metrics["unallocated_ad_spend"])
                    ),
                    ads_allocation_status=str(ads_metrics["ads_allocation_status"]),
                    final_profit_allowed=bool(ads_metrics["final_profit_allowed"]),
                    estimated_cogs=float(self._decimal(bucket["estimated_cogs"])),
                    seller_cogs=float(seller_cogs),
                    seller_other_expense=float(seller_other_expense),
                    total_seller_expenses=float(total_seller_expenses),
                    total_seller_costs=float(total_seller_expenses),
                    additional_income=float(additional_income),
                    net_profit_after_all_expenses=float(
                        net_profit_after_all_expenses_value
                    )
                    if has_complete_manual_cost
                    else None,
                    expense_data_quality=expense_quality,
                    matched_cost_rows=int(bucket["matched_cost_rows"]),
                    estimated_profit=float(profit) if profit is not None else None,
                    margin_percent=margin_percent,
                    roi_percent=roi_percent,
                    drr_percent=drr_percent,
                    closing_stock_qty=(
                        float(self._decimal(bucket["closing_stock_qty"]))
                        if bucket["closing_stock_qty"] is not None
                        else None
                    ),
                    has_manual_cost=has_complete_manual_cost,
                    has_real_manual_cost=has_complete_real_cost,
                    has_placeholder_cost=has_placeholder_cost,
                    business_trusted=operational_trusted,
                    operational_trusted=operational_trusted,
                    financial_final=public_trust_state == "financial_final",
                    cost_source=cost_source,
                    cost_truth_level=truth_level,
                    trust_state=public_trust_state,
                    cost_trust_policy=cost_trust_policy,
                    supplier_confirmed_revenue_coverage_percent=0.0,
                    operator_baseline_revenue_coverage_percent=0.0,
                    trusted_revenue_cost_coverage_percent=0.0,
                    financial_final_blockers_total=0,
                    final_profit_blockers_total=0,
                    blocked_reasons=blocked_reasons,
                )
            )
        result.sort(
            key=lambda item: (
                item.estimated_profit
                if item.estimated_profit is not None
                else float("-inf")
            ),
            reverse=True,
        )
        return result

    async def sku_profitability_page(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        brand: str | None = None,
        subject_name: str | None = None,
        has_manual_cost: bool | None = None,
        business_trusted: bool | None = None,
        sort: str = "profit_desc",
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[SKUProfitabilityRow]:
        actual_from = date_from or (utcnow().date() - timedelta(days=30))
        actual_to = date_to or utcnow().date()
        data_version_hash = await self._sku_profitability_page_version_hash(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        cache_key = (
            account_id,
            actual_from,
            actual_to,
            search or "",
            vendor_code or "",
            barcode or "",
            brand or "",
            subject_name or "",
            has_manual_cost,
            business_trusted,
            sort,
            sort_by or "",
            sort_dir,
            limit,
            offset,
            data_version_hash,
        )
        cached_page = self._profitability_page_cache.get(cache_key)
        if cached_page is not None:
            cached_at, page = cached_page
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.RESPONSE_CACHE_TTL_SECONDS
            ):
                return self._with_page_cache_meta(
                    page,
                    computed_at=cached_at,
                    cache_status="hit",
                    data_version_hash=data_version_hash,
                )
        normalized_sort = self._normalize_profitability_sort(
            sort=sort,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        items = await self.sku_profitability(
            session,  # type: ignore[arg-type]
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        health = await self.data_health(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        filtered = self._filter_sort_profitability_items(
            items,
            search=search,
            vendor_code=vendor_code,
            barcode=barcode,
            brand=brand,
            subject_name=subject_name,
            has_manual_cost=has_manual_cost,
            business_trusted=business_trusted,
            sort=normalized_sort,
        )
        enriched = [
            item.model_copy(
                update={
                    "business_trusted": bool(
                        item.operational_trusted or health.business_trusted
                    ),
                    "operational_trusted": bool(
                        item.operational_trusted or health.operational_trusted
                    ),
                    "financial_final": bool(
                        health.financial_final
                        and bool(item.has_real_manual_cost)
                        and item.trust_state not in {"blocked", "data_blocked"}
                    ),
                    "trust_state": (
                        "financial_final"
                        if health.financial_final
                        and bool(item.has_real_manual_cost)
                        and item.trust_state not in {"blocked", "data_blocked"}
                        else "operational_provisional"
                        if bool(item.operational_trusted or health.operational_trusted)
                        else "blocked"
                    ),
                    "cost_trust_policy": health.cost_trust_policy,
                    "supplier_confirmed_revenue_coverage_percent": float(
                        health.supplier_confirmed_revenue_coverage_percent or 0.0
                    ),
                    "operator_baseline_revenue_coverage_percent": float(
                        health.operator_baseline_revenue_coverage_percent or 0.0
                    ),
                    "trusted_revenue_cost_coverage_percent": float(
                        health.trusted_revenue_cost_coverage_percent or 0.0
                    ),
                    "financial_final_blockers_total": int(
                        health.financial_final_blockers_total or 0
                    ),
                    "final_profit_blockers_total": int(
                        health.final_profit_blockers_total or 0
                    ),
                }
            )
            for item in filtered
        ]
        total = len(enriched)
        computed_at = utcnow()
        result = self._with_page_cache_meta(
            Page(
                total=total,
                limit=limit,
                offset=offset,
                items=enriched[offset : offset + limit],
            ),
            computed_at=computed_at,
            cache_status="miss",
            data_version_hash=data_version_hash,
        )
        self._profitability_page_cache[cache_key] = (
            computed_at,
            result.model_copy(deep=True),
        )
        return result

        if session is None:  # test helper path
            items = await self.sku_profitability(
                session,  # type: ignore[arg-type]
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
            )
            filtered = self._filter_sort_profitability_items(
                items,
                search=search,
                vendor_code=vendor_code,
                barcode=barcode,
                brand=brand,
                subject_name=subject_name,
                has_manual_cost=has_manual_cost,
                business_trusted=business_trusted,
                sort=normalized_sort,
            )
            total = len(filtered)
            return Page(
                total=total,
                limit=limit,
                offset=offset,
                items=filtered[offset : offset + limit],
            )

        base_filters = [MartSKUDaily.account_id == account_id]
        if date_from is not None:
            base_filters.append(MartSKUDaily.stat_date >= date_from)
        if date_to is not None:
            base_filters.append(MartSKUDaily.stat_date <= date_to)

        requires_cost_expr = or_(
            MartSKUDaily.final_sales_qty != 0,
            MartSKUDaily.final_return_qty != 0,
            MartSKUDaily.final_net_qty != 0,
            MartSKUDaily.final_revenue != 0,
            MartSKUDaily.sale_rows != 0,
            MartSKUDaily.finance_rows != 0,
        )
        cost_required_rows = func.sum(case((requires_cost_expr, 1), else_=0))
        cost_ready_rows = func.sum(
            case(
                (and_(requires_cost_expr, MartSKUDaily.has_manual_cost.is_(True)), 1),
                else_=0,
            )
        )
        real_cost_ready_rows = func.sum(
            case(
                (
                    and_(
                        requires_cost_expr, MartSKUDaily.has_real_manual_cost.is_(True)
                    ),
                    1,
                ),
                else_=0,
            )
        )
        placeholder_cost_rows = func.sum(
            case(
                (
                    and_(
                        requires_cost_expr, MartSKUDaily.has_placeholder_cost.is_(True)
                    ),
                    1,
                ),
                else_=0,
            )
        )
        aggregate_subquery = (
            select(
                MartSKUDaily.nm_id.label("nm_id"),
                MartSKUDaily.vendor_code.label("vendor_code"),
                MartSKUDaily.barcode.label("barcode"),
                func.max(MartSKUDaily.sku_id).label("sku_id"),
                func.max(MartSKUDaily.title).label("title"),
                func.max(MartSKUDaily.brand).label("brand"),
                func.max(MartSKUDaily.subject_name).label("subject_name"),
                func.coalesce(func.sum(MartSKUDaily.finance_rows), 0).label(
                    "finance_rows"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_sales_qty), 0).label(
                    "gross_units"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_return_qty), 0).label(
                    "return_units"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_net_qty), 0).label(
                    "net_units"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_revenue), 0).label(
                    "realized_revenue"
                ),
                func.coalesce(func.sum(MartSKUDaily.final_for_pay), 0).label("for_pay"),
                func.coalesce(func.sum(MartSKUDaily.commission), 0).label("commission"),
                func.coalesce(func.sum(MartSKUDaily.acquiring_fee), 0).label(
                    "acquiring_fee"
                ),
                func.coalesce(func.sum(MartSKUDaily.logistics), 0).label("logistics"),
                func.coalesce(func.sum(MartSKUDaily.paid_acceptance), 0).label(
                    "paid_acceptance"
                ),
                func.coalesce(func.sum(MartSKUDaily.storage), 0).label("storage"),
                func.coalesce(func.sum(MartSKUDaily.penalties), 0).label("penalties"),
                func.coalesce(func.sum(MartSKUDaily.deductions), 0).label("deductions"),
                func.coalesce(func.sum(MartSKUDaily.additional_payments), 0).label(
                    "additional_payments"
                ),
                func.coalesce(func.sum(MartSKUDaily.ad_spend), 0).label("ad_spend"),
                func.coalesce(func.sum(MartSKUDaily.estimated_cogs), 0).label(
                    "estimated_cogs"
                ),
                func.coalesce(
                    func.sum(
                        case((MartSKUDaily.has_manual_cost.is_(True), 1), else_=0)
                    ),
                    0,
                ).label("matched_cost_rows"),
                func.coalesce(cost_required_rows, 0).label("cost_required_rows"),
                func.coalesce(cost_ready_rows, 0).label("cost_ready_rows"),
                func.coalesce(real_cost_ready_rows, 0).label("real_cost_ready_rows"),
                func.coalesce(placeholder_cost_rows, 0).label("placeholder_cost_rows"),
                func.string_agg(
                    sa.distinct(
                        func.coalesce(
                            MartSKUDaily.cost_source,
                            MartSKUDaily.final_revenue_source,
                            sa.literal("unknown"),
                        )
                    ),
                    ",",
                ).label("cost_sources_raw"),
            )
            .where(*base_filters)
            .group_by(
                MartSKUDaily.nm_id, MartSKUDaily.vendor_code, MartSKUDaily.barcode
            )
            .subquery()
        )

        ranked_stock = (
            select(
                MartSKUDaily.nm_id.label("nm_id"),
                MartSKUDaily.vendor_code.label("vendor_code"),
                MartSKUDaily.barcode.label("barcode"),
                MartSKUDaily.closing_stock_qty.label("closing_stock_qty"),
                func.row_number()
                .over(
                    partition_by=(
                        MartSKUDaily.nm_id,
                        MartSKUDaily.vendor_code,
                        MartSKUDaily.barcode,
                    ),
                    order_by=(MartSKUDaily.stat_date.desc(), MartSKUDaily.id.desc()),
                )
                .label("rn"),
            )
            .where(*base_filters)
            .subquery()
        )
        latest_stock = (
            select(
                ranked_stock.c.nm_id,
                ranked_stock.c.vendor_code,
                ranked_stock.c.barcode,
                ranked_stock.c.closing_stock_qty,
            )
            .where(ranked_stock.c.rn == 1)
            .subquery()
        )

        join_condition = and_(
            sa.tuple_(
                aggregate_subquery.c.nm_id,
                aggregate_subquery.c.vendor_code,
                aggregate_subquery.c.barcode,
            )
            == sa.tuple_(
                latest_stock.c.nm_id,
                latest_stock.c.vendor_code,
                latest_stock.c.barcode,
            )
        )
        has_complete_manual_cost = or_(
            aggregate_subquery.c.cost_required_rows == 0,
            aggregate_subquery.c.cost_ready_rows
            == aggregate_subquery.c.cost_required_rows,
        )
        has_complete_real_cost = or_(
            aggregate_subquery.c.cost_required_rows == 0,
            aggregate_subquery.c.real_cost_ready_rows
            == aggregate_subquery.c.cost_required_rows,
        )
        has_placeholder_cost = aggregate_subquery.c.placeholder_cost_rows > 0
        profit_expr = (
            aggregate_subquery.c.realized_revenue
            + aggregate_subquery.c.additional_payments
            - aggregate_subquery.c.commission
            - aggregate_subquery.c.acquiring_fee
            - aggregate_subquery.c.logistics
            - aggregate_subquery.c.paid_acceptance
            - aggregate_subquery.c.storage
            - aggregate_subquery.c.penalties
            - aggregate_subquery.c.deductions
            - aggregate_subquery.c.ad_spend
            - aggregate_subquery.c.estimated_cogs
        )
        page_source = (
            select(
                aggregate_subquery.c.sku_id,
                aggregate_subquery.c.nm_id,
                aggregate_subquery.c.vendor_code,
                aggregate_subquery.c.barcode,
                aggregate_subquery.c.title,
                aggregate_subquery.c.brand,
                aggregate_subquery.c.subject_name,
                aggregate_subquery.c.finance_rows,
                aggregate_subquery.c.gross_units,
                aggregate_subquery.c.return_units,
                aggregate_subquery.c.net_units,
                aggregate_subquery.c.realized_revenue,
                aggregate_subquery.c.for_pay,
                aggregate_subquery.c.commission,
                aggregate_subquery.c.acquiring_fee,
                aggregate_subquery.c.logistics,
                aggregate_subquery.c.paid_acceptance,
                aggregate_subquery.c.storage,
                aggregate_subquery.c.penalties,
                aggregate_subquery.c.deductions,
                aggregate_subquery.c.additional_payments,
                aggregate_subquery.c.ad_spend,
                aggregate_subquery.c.estimated_cogs,
                aggregate_subquery.c.matched_cost_rows,
                latest_stock.c.closing_stock_qty.label("closing_stock_qty"),
                aggregate_subquery.c.cost_sources_raw,
                has_complete_manual_cost.label("has_manual_cost"),
                has_complete_real_cost.label("has_real_manual_cost"),
                has_placeholder_cost.label("has_placeholder_cost"),
                has_complete_real_cost.label("business_trusted"),
                case((has_complete_manual_cost, profit_expr), else_=None).label(
                    "estimated_profit"
                ),
                case(
                    (
                        and_(
                            has_complete_manual_cost,
                            aggregate_subquery.c.realized_revenue > 0,
                        ),
                        (profit_expr / aggregate_subquery.c.realized_revenue) * 100,
                    ),
                    else_=None,
                ).label("margin_percent"),
                case(
                    (
                        and_(
                            has_complete_manual_cost,
                            aggregate_subquery.c.estimated_cogs > 0,
                        ),
                        (profit_expr / aggregate_subquery.c.estimated_cogs) * 100,
                    ),
                    else_=None,
                ).label("roi_percent"),
                case(
                    (
                        aggregate_subquery.c.realized_revenue > 0,
                        (
                            aggregate_subquery.c.ad_spend
                            / aggregate_subquery.c.realized_revenue
                        )
                        * 100,
                    ),
                    else_=None,
                ).label("drr_percent"),
            )
            .select_from(aggregate_subquery.outerjoin(latest_stock, join_condition))
            .subquery()
        )

        filtered_stmt = select(page_source)
        if search:
            pattern = f"%{search.strip()}%"
            filtered_stmt = filtered_stmt.where(
                or_(
                    sa.cast(page_source.c.nm_id, String).ilike(pattern),
                    page_source.c.vendor_code.ilike(pattern),
                    page_source.c.barcode.ilike(pattern),
                    page_source.c.title.ilike(pattern),
                    page_source.c.brand.ilike(pattern),
                    page_source.c.subject_name.ilike(pattern),
                )
            )
        if has_manual_cost is not None:
            filtered_stmt = filtered_stmt.where(
                page_source.c.has_manual_cost.is_(has_manual_cost)
            )
        if vendor_code:
            filtered_stmt = filtered_stmt.where(
                page_source.c.vendor_code.ilike(f"%{vendor_code}%")
            )
        if barcode:
            filtered_stmt = filtered_stmt.where(
                page_source.c.barcode.ilike(f"%{barcode}%")
            )
        if brand:
            filtered_stmt = filtered_stmt.where(page_source.c.brand.ilike(f"%{brand}%"))
        if subject_name:
            filtered_stmt = filtered_stmt.where(
                page_source.c.subject_name.ilike(f"%{subject_name}%")
            )
        if business_trusted is not None:
            filtered_stmt = filtered_stmt.where(
                page_source.c.business_trusted.is_(business_trusted)
            )

        if normalized_sort == "profit_asc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.estimated_profit.asc().nulls_last()
            )
        elif normalized_sort == "margin_asc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.margin_percent.asc().nulls_last()
            )
        elif normalized_sort == "margin_desc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.margin_percent.desc().nulls_last()
            )
        elif normalized_sort == "ad_spend_asc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.ad_spend.asc().nulls_last()
            )
        elif normalized_sort == "ad_spend_desc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.ad_spend.desc().nulls_last()
            )
        elif normalized_sort == "revenue_asc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.realized_revenue.asc().nulls_last()
            )
        elif normalized_sort == "revenue_desc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.realized_revenue.desc().nulls_last()
            )
        elif normalized_sort == "vendor_code_asc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.vendor_code.asc().nulls_last(),
                page_source.c.nm_id.asc().nulls_last(),
            )
        elif normalized_sort == "vendor_code_desc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.vendor_code.desc().nulls_last(),
                page_source.c.nm_id.desc().nulls_last(),
            )
        elif normalized_sort == "nm_id_asc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.nm_id.asc().nulls_last(),
                page_source.c.vendor_code.asc().nulls_last(),
            )
        elif normalized_sort == "nm_id_desc":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.nm_id.desc().nulls_last(),
                page_source.c.vendor_code.desc().nulls_last(),
            )
        elif normalized_sort == "no_cost_first":
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.has_manual_cost.asc(),
                page_source.c.estimated_profit.desc().nulls_last(),
            )
        else:
            filtered_stmt = filtered_stmt.order_by(
                page_source.c.estimated_profit.desc().nulls_last()
            )

        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(filtered_stmt.subquery())
                )
            ).scalar_one()
        )
        rows = (
            (await session.execute(filtered_stmt.limit(limit).offset(offset)))
            .mappings()
            .all()
        )
        items: list[SKUProfitabilityRow] = []
        cost_trust_policy = await self._cost_trust_policy(
            session, account_id=account_id
        )
        for row in rows:
            cost_sources_raw = row["cost_sources_raw"]
            cost_source = None
            if isinstance(cost_sources_raw, str) and cost_sources_raw:
                parts = [part for part in cost_sources_raw.split(",") if part]
                cost_source = parts[0] if len(set(parts)) == 1 else "mixed"
            has_manual_cost_value = bool(row["has_manual_cost"])
            has_real_manual_cost_value = bool(row["has_real_manual_cost"])
            has_placeholder_cost_value = bool(row["has_placeholder_cost"])
            finance_rows_value = int(row["finance_rows"] or 0)
            truth_level = cost_truth_level_from_flags(
                has_manual_cost=has_manual_cost_value,
                has_real_manual_cost=has_real_manual_cost_value,
                has_placeholder_cost=has_placeholder_cost_value,
                cost_source=cost_source,
            )
            raw_blocked_reasons = blocked_reasons_for_profit_row(
                has_manual_cost=has_manual_cost_value,
                has_real_manual_cost=has_real_manual_cost_value,
                has_placeholder_cost=has_placeholder_cost_value,
                finance_rows=finance_rows_value,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            blocked_reasons = normalize_blocked_reasons_for_cost_policy(
                raw_blocked_reasons,
                has_manual_cost=has_manual_cost_value,
                has_real_manual_cost=has_real_manual_cost_value,
                has_placeholder_cost=has_placeholder_cost_value,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            effective_business_trusted = effective_cost_is_business_trusted(
                has_manual_cost=has_manual_cost_value,
                has_real_manual_cost=has_real_manual_cost_value,
                has_placeholder_cost=has_placeholder_cost_value,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            cost_final_accepted = final_cost_is_accepted(
                has_manual_cost=has_manual_cost_value,
                has_real_manual_cost=has_real_manual_cost_value,
                has_placeholder_cost=has_placeholder_cost_value,
                cost_source=cost_source,
                cost_truth_level=truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            public_trust_state = self._public_row_trust_state(
                effective_business_trusted=effective_business_trusted,
                cost_final_accepted=cost_final_accepted,
                has_placeholder_cost=has_placeholder_cost_value,
                finance_rows=finance_rows_value,
                blocked_reasons=blocked_reasons,
            )
            operational_trusted = public_trust_state in {
                "operational_provisional",
                "financial_final",
            }
            items.append(
                SKUProfitabilityRow(
                    sku_id=row["sku_id"],
                    nm_id=row["nm_id"],
                    vendor_code=row["vendor_code"],
                    barcode=row["barcode"],
                    title=row["title"],
                    brand=row["brand"],
                    subject_name=row["subject_name"],
                    finance_rows=finance_rows_value,
                    gross_units=int(row["gross_units"] or 0),
                    return_units=int(row["return_units"] or 0),
                    net_units=int(row["net_units"] or 0),
                    realized_revenue=float(self._decimal(row["realized_revenue"])),
                    for_pay=float(self._decimal(row["for_pay"])),
                    commission=float(self._decimal(row["commission"])),
                    acquiring_fee=float(self._decimal(row["acquiring_fee"])),
                    logistics=float(self._decimal(row["logistics"])),
                    paid_acceptance=float(self._decimal(row["paid_acceptance"])),
                    storage=float(self._decimal(row["storage"])),
                    penalties=float(self._decimal(row["penalties"])),
                    deductions=float(self._decimal(row["deductions"])),
                    additional_payments=float(
                        self._decimal(row["additional_payments"])
                    ),
                    ad_spend=float(self._decimal(row["ad_spend"])),
                    estimated_cogs=float(self._decimal(row["estimated_cogs"])),
                    matched_cost_rows=int(row["matched_cost_rows"] or 0),
                    estimated_profit=float(row["estimated_profit"])
                    if row["estimated_profit"] is not None
                    else None,
                    margin_percent=float(row["margin_percent"])
                    if row["margin_percent"] is not None
                    else None,
                    roi_percent=float(row["roi_percent"])
                    if row["roi_percent"] is not None
                    else None,
                    drr_percent=float(row["drr_percent"])
                    if row["drr_percent"] is not None
                    else None,
                    closing_stock_qty=float(self._decimal(row["closing_stock_qty"]))
                    if row["closing_stock_qty"] is not None
                    else None,
                    has_manual_cost=has_manual_cost_value,
                    has_real_manual_cost=has_real_manual_cost_value,
                    has_placeholder_cost=has_placeholder_cost_value,
                    business_trusted=operational_trusted,
                    operational_trusted=operational_trusted,
                    financial_final=public_trust_state == "financial_final",
                    cost_source=cost_source,
                    cost_truth_level=truth_level,
                    trust_state=public_trust_state,
                    cost_trust_policy=cost_trust_policy,
                    supplier_confirmed_revenue_coverage_percent=0.0,
                    operator_baseline_revenue_coverage_percent=0.0,
                    trusted_revenue_cost_coverage_percent=0.0,
                    financial_final_blockers_total=0,
                    final_profit_blockers_total=0,
                    blocked_reasons=blocked_reasons,
                )
            )
        return Page(total=total, limit=limit, offset=offset, items=items)

    async def data_health(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DashboardDataHealth:
        today = utcnow().date()
        actual_from = date_from or (today - timedelta(days=29))
        actual_to = date_to or today
        cost_trust_policy = await self._cost_trust_policy(
            session, account_id=account_id
        )
        cache_key = (account_id, actual_from, actual_to, cost_trust_policy)
        cached = self._data_health_cache.get(cache_key)
        if cached is not None:
            cached_at, cached_health = cached
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.DATA_HEALTH_CACHE_TTL_SECONDS
            ):
                return cached_health.model_copy(deep=True)
        reference_date = actual_to
        reference_at = datetime.combine(reference_date, datetime.max.time())
        # Open unresolved DQ issues should stay visible even if they were first
        # detected before the selected revenue window.
        issue_filters = [
            DataQualityIssue.account_id == account_id,
            DataQualityIssue.resolved_at.is_(None),
            DataQualityIssue.code.notin_(sorted(self.HIDDEN_USER_ISSUE_CODES)),
        ]
        open_issues = list(
            (
                await session.execute(select(DataQualityIssue).where(*issue_filters))
            ).scalars()
        )
        dq_summary_payload = await self._get_data_quality_service().list_issue_summary(
            session,
            account_id=account_id,
        )
        dq_summary_blockers_total = max(
            int(dq_summary_payload.get("financial_final_blockers_total") or 0), 0
        )
        dq_summary_blocking_open_issues_total = max(
            int(dq_summary_payload.get("blocking_open_issues_total") or 0), 0
        )
        issue_buckets_map: dict[str, dict[str, Any]] = {}
        severity_rank = {"critical": 4, "error": 3, "warning": 2, "info": 1}
        for issue in open_issues:
            if issue.code == "unmatched_sku" and self._issue_is_supply_source_unmatched(
                issue
            ):
                continue
            code = str(issue.code or "")
            severity = str(issue.severity or "info")
            bucket = issue_buckets_map.setdefault(
                code,
                {"count": 0, "severity": severity, "financial_final_blocker": False},
            )
            bucket["count"] += 1
            if severity_rank.get(severity, 0) > severity_rank.get(
                str(bucket["severity"]), 0
            ):
                bucket["severity"] = severity
            if self._issue_is_financial_final_blocker(issue):
                bucket["financial_final_blocker"] = True
        issue_buckets = [
            DashboardHealthIssueBucket(
                code=code,
                severity=str(values["severity"]),
                count=int(values["count"]),
                business_impact=str(
                    issue_bucket_meta(code).get("business_impact") or ""
                ),
                recommended_fix=str(
                    issue_bucket_meta(code).get("recommended_fix") or ""
                ),
                financial_final_blocker=bool(values["financial_final_blocker"]),
            )
            for code, values in sorted(
                issue_buckets_map.items(),
                key=lambda item: (-int(item[1]["count"]), item[0]),
            )
        ]

        runs = list(
            (
                await session.execute(
                    select(WBSyncRun)
                    .where(WBSyncRun.account_id == account_id)
                    .order_by(WBSyncRun.id.desc())
                )
            ).scalars()
        )
        latest_run_by_domain: dict[str, WBSyncRun] = {}
        latest_success_by_domain: dict[str, WBSyncRun] = {}
        for run in runs:
            latest_run_by_domain.setdefault(run.domain, run)
            if run.status == "completed":
                latest_success_by_domain.setdefault(run.domain, run)
        cursors = list(
            (
                await session.execute(
                    select(WBSyncCursor).where(WBSyncCursor.account_id == account_id)
                )
            ).scalars()
        )
        cursor_by_domain = {
            cursor.domain: cursor
            for cursor in cursors
            if cursor.cursor_key == "default"
        }
        domains = sorted({*latest_run_by_domain.keys(), *cursor_by_domain.keys()})
        domain_statuses = [
            DashboardHealthDomainStatus(
                domain=domain,
                latest_status=latest_run_by_domain.get(domain).status
                if latest_run_by_domain.get(domain)
                else None,
                latest_finished_at=(
                    latest_run_by_domain.get(domain).finished_at
                    if latest_run_by_domain.get(domain)
                    else None
                ),
                last_successful_at=(
                    latest_success_by_domain.get(domain).finished_at
                    if latest_success_by_domain.get(domain)
                    else None
                ),
                latest_error_text=(
                    latest_run_by_domain.get(domain).error_text
                    if latest_run_by_domain.get(domain)
                    else None
                ),
                cursor_status=cursor_by_domain.get(domain).status
                if cursor_by_domain.get(domain)
                else None,
                cursor_last_synced_at=(
                    cursor_by_domain.get(domain).last_synced_at
                    if cursor_by_domain.get(domain)
                    else None
                ),
            )
            for domain in domains
        ]
        transient_failed_domains = [
            item.domain
            for item in domain_statuses
            if self._is_transient_failed_domain(item, reference_at=reference_at)
        ]
        non_blocking_failed_domains = [
            item.domain
            for item in domain_statuses
            if item.latest_status == "failed"
            and item.domain not in transient_failed_domains
            and item.domain not in self.BUSINESS_CRITICAL_SYNC_DOMAINS
        ]
        failed_domains = [
            item.domain
            for item in domain_statuses
            if item.latest_status == "failed"
            and item.domain not in transient_failed_domains
            and item.domain in self.BUSINESS_CRITICAL_SYNC_DOMAINS
        ]
        skipped_domains = [
            item.domain for item in domain_statuses if item.latest_status == "skipped"
        ]
        missed_days_count = sum(
            1 for issue in open_issues if issue.code == "missed_load"
        )
        missing_manual_cost_count = sum(
            1 for issue in open_issues if issue.code == "missing_manual_cost"
        )
        all_open_issues_total = len(open_issues)
        classified_unmatched_sku_count = sum(
            1
            for issue in open_issues
            if issue.code == "unmatched_sku"
            and self._issue_is_classified_for_acceptance(issue)
        )
        all_open_unmatched_sku_count = sum(
            1 for issue in open_issues if issue.code == "unmatched_sku"
        )
        open_unmatched_sku_count = sum(
            1 for issue in open_issues if issue.code == "unmatched_sku"
        )
        blocking_unmatched_sku_count = sum(
            1
            for issue in open_issues
            if issue.code == "unmatched_sku"
            and self._issue_is_financial_final_blocker(issue)
        )
        unmatched_sku_count = all_open_unmatched_sku_count
        local_financial_final_blockers_total = sum(
            1 for issue in open_issues if self._issue_is_financial_final_blocker(issue)
        )
        local_blocking_open_issue_count = local_financial_final_blockers_total
        effective_blocking_open_issue_count = dq_summary_blocking_open_issues_total
        effective_financial_final_blockers_total = dq_summary_blockers_total
        trust_consistency_status = (
            "consistent"
            if (
                local_blocking_open_issue_count == dq_summary_blocking_open_issues_total
                and local_financial_final_blockers_total == dq_summary_blockers_total
            )
            else "mismatch"
        )
        trust_consistency_warning = (
            None
            if trust_consistency_status == "consistent"
            else (
                "Dashboard data health local blocker counts differed from dq/issues/summary; "
                "dq/issues/summary is used as the source of truth."
            )
        )
        finance_issue_codes = {
            "finance_without_sale",
            "sale_without_finance",
            "order_without_sale_or_return",
        }
        cost_issue_codes = {
            "missing_manual_cost",
            "manual_cost_overlap",
            "manual_cost_linked_to_inactive_sku",
            "manual_cost_unresolved_sku",
            "manual_cost_ambiguous_match",
            "manual_cost_old_fields_used",
            "seller_other_expense_missing",
        }
        stock_issue_codes = {
            "sales_without_stock",
            "stock_without_sales",
            "stocks_task_not_ready",
        }
        all_open_finance_mismatch_count = sum(
            1 for issue in open_issues if issue.code in finance_issue_codes
        )
        blocking_finance_mismatch_count = sum(
            1
            for issue in open_issues
            if issue.code in finance_issue_codes
            and self._issue_is_financial_final_blocker(issue)
        )
        all_open_cost_issue_count = sum(
            1 for issue in open_issues if issue.code in cost_issue_codes
        )
        blocking_cost_issue_count = sum(
            1
            for issue in open_issues
            if issue.code in cost_issue_codes
            and self._issue_is_financial_final_blocker(issue)
        )
        all_open_stock_issue_count = sum(
            1 for issue in open_issues if issue.code in stock_issue_codes
        )
        blocking_stock_issue_count = sum(
            1
            for issue in open_issues
            if issue.code in stock_issue_codes
            and self._issue_blocks_business_analysis(issue)
        )
        duplicate_srid_count = sum(
            1 for issue in open_issues if issue.code == "duplicate_srid"
        )
        active_sku_stats = (
            await session.execute(
                select(
                    func.count(CoreSKU.id),
                    func.count(CoreSKU.id).filter(
                        sa.exists(
                            select(ManualCost.id).where(
                                ManualCost.account_id == CoreSKU.account_id,
                                ManualCost.sku_id == CoreSKU.id,
                            )
                        )
                    ),
                ).where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.is_active.is_(True),
                )
            )
        ).one()
        active_sku_count = int(active_sku_stats[0] or 0)
        active_sku_with_manual_cost_count = int(active_sku_stats[1] or 0)
        placeholder_manual_cost_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ManualCost)
                    .where(
                        ManualCost.account_id == account_id,
                        or_(
                            ManualCost.is_placeholder.is_(True),
                            ManualCost.supplier == "AUTO_TEMPLATE",
                        ),
                    )
                )
            ).scalar_one()
        )
        supplier_confirmed_manual_cost_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ManualCost)
                    .where(
                        ManualCost.account_id == account_id,
                        or_(
                            ManualCost.is_supplier_confirmed.is_(True),
                            ManualCost.cost_source == "supplier_confirmed",
                        ),
                    )
                )
            ).scalar_one()
        )
        trusted_manual_cost_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ManualCost)
                    .where(
                        ManualCost.account_id == account_id,
                        ManualCost.is_placeholder.is_not(True),
                        or_(
                            ManualCost.cost_source == "supplier_confirmed",
                            ManualCost.cost_source == "operator_trusted_manual",
                            ManualCost.cost_source == "operator_baseline",
                            ManualCost.is_business_trusted.is_(True),
                            ManualCost.supplier == "OPERATOR_TRUSTED_COST",
                        ),
                    )
                )
            ).scalar_one()
        )
        mart_revenue_stats = (
            await session.execute(
                select(
                    func.count(MartSKUDaily.id).filter(
                        and_(
                            MartSKUDaily.final_revenue.is_not(None),
                            MartSKUDaily.final_revenue > 0,
                            MartSKUDaily.has_manual_cost.is_(True),
                        )
                    ),
                    func.count(MartSKUDaily.id).filter(
                        and_(
                            MartSKUDaily.final_revenue.is_not(None),
                            MartSKUDaily.final_revenue > 0,
                            MartSKUDaily.has_manual_cost.is_(False),
                        )
                    ),
                    func.coalesce(
                        func.sum(MartSKUDaily.final_revenue).filter(
                            and_(
                                MartSKUDaily.final_revenue.is_not(None),
                                MartSKUDaily.final_revenue > 0,
                                MartSKUDaily.has_manual_cost.is_(True),
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(MartSKUDaily.final_revenue).filter(
                            and_(
                                MartSKUDaily.final_revenue.is_not(None),
                                MartSKUDaily.final_revenue > 0,
                                MartSKUDaily.has_manual_cost.is_(False),
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(MartSKUDaily.final_revenue).filter(
                            and_(
                                MartSKUDaily.final_revenue.is_not(None),
                                MartSKUDaily.final_revenue > 0,
                                MartSKUDaily.has_real_manual_cost.is_(True),
                            )
                        ),
                        0,
                    ),
                    func.coalesce(
                        func.sum(MartSKUDaily.final_revenue).filter(
                            and_(
                                MartSKUDaily.final_revenue.is_not(None),
                                MartSKUDaily.final_revenue > 0,
                                MartSKUDaily.has_placeholder_cost.is_(True),
                            )
                        ),
                        0,
                    ),
                ).where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.stat_date >= actual_from,
                    MartSKUDaily.stat_date <= actual_to,
                )
            )
        ).one()
        revenue_rows_with_cost = int(mart_revenue_stats[0] or 0)
        revenue_rows_without_cost = int(mart_revenue_stats[1] or 0)
        revenue_with_cost_decimal = self._decimal(mart_revenue_stats[2])
        revenue_without_cost_decimal = self._decimal(mart_revenue_stats[3])
        revenue_with_cost = float(revenue_with_cost_decimal)
        revenue_without_cost = float(revenue_without_cost_decimal)
        revenue_with_real_cost_decimal = self._decimal(mart_revenue_stats[4])
        revenue_with_placeholder_cost_decimal = self._decimal(mart_revenue_stats[5])
        revenue_with_real_cost = float(revenue_with_real_cost_decimal)
        revenue_with_placeholder_cost = float(revenue_with_placeholder_cost_decimal)
        revenue_with_supplier_confirmed_cost_decimal = revenue_with_real_cost_decimal
        revenue_with_supplier_confirmed_cost = float(
            revenue_with_supplier_confirmed_cost_decimal
        )
        revenue_with_trusted_cost_decimal = max(
            Decimal("0"),
            revenue_with_cost_decimal - revenue_with_placeholder_cost_decimal,
        )
        revenue_with_trusted_cost = float(revenue_with_trusted_cost_decimal)
        supplier_confirmed_revenue_coverage_percent = self._percent(
            revenue_with_supplier_confirmed_cost_decimal,
            revenue_with_cost_decimal + revenue_without_cost_decimal,
        )
        trusted_revenue_cost_coverage_percent = self._percent(
            revenue_with_trusted_cost_decimal,
            revenue_with_cost_decimal + revenue_without_cost_decimal,
        )
        ad_cluster_rows = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(WBAdClusterStat)
                    .where(WBAdClusterStat.account_id == account_id)
                )
            ).scalar_one()
        )
        latest_cluster_raw = (
            await session.execute(
                select(RawWBAPIResponse)
                .where(
                    RawWBAPIResponse.account_id == account_id,
                    RawWBAPIResponse.endpoint == "/adv/v1/normquery/stats",
                )
                .order_by(RawWBAPIResponse.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        ad_cluster_state = "loaded" if ad_cluster_rows > 0 else "stage3_not_loaded"
        ad_cluster_reason = None
        if ad_cluster_rows == 0 and latest_cluster_raw is not None:
            payload = (
                latest_cluster_raw.response_json
                if isinstance(latest_cluster_raw.response_json, dict)
                else {}
            )
            if payload.get("items") is None and payload:
                ad_cluster_state = "wb_no_data"
                ad_cluster_reason = (
                    "WB пока не вернул данные по подходящим рекламным кластерам"
                )
            elif latest_cluster_raw.status_code >= 400:
                ad_cluster_state = "request_failed"
                ad_cluster_reason = (
                    latest_cluster_raw.error_text
                    or f"Запрос по рекламным кластерам завершился ошибкой HTTP {latest_cluster_raw.status_code}"
                )
            else:
                ad_cluster_state = "parser_or_mapping_gap"
                ad_cluster_reason = (
                    "WB вернул данные по кластерам, но они не сохранились в базе"
                )
        latest_stock_snapshot_at = (
            await session.execute(
                select(func.max(WBStockSnapshot.snapshot_at)).where(
                    WBStockSnapshot.account_id == account_id
                )
            )
        ).scalar_one()
        latest_stocks_status = self._effective_stocks_status(
            latest_run=latest_run_by_domain.get("stocks"),
            default_cursor=cursor_by_domain.get("stocks"),
            latest_snapshot_at=latest_stock_snapshot_at,
            reference_at=reference_at,
        )
        notes: list[str] = []
        if (
            cost_trust_policy in {"operator_baseline", "mixed"}
            and (trusted_revenue_cost_coverage_percent or 0) >= 95
            and (supplier_confirmed_revenue_coverage_percent or 0) < 95
        ):
            notes.append(
                "Система временно принимает текущую себестоимость для бизнес-решений. Покрытие подтвержденной реальной себестоимостью показано отдельно."
            )
        if cost_policy_owner_approves_final(cost_trust_policy):
            notes.append(
                "Включен режим временного ручного принятия. Текущая себестоимость и открытые проблемы видны в отчете, но верхний статус временно считается принятым до обновления реальных данных."
            )
        if placeholder_manual_cost_count > 0:
            notes.append(
                "Себестоимость загружена из шаблона. Это подходит для проверки интерфейса, но не для финальной прибыли."
            )
        if revenue_without_cost > 0:
            notes.append(
                "Часть выручки еще не покрыта себестоимостью или привязкой к карточке. Расчет прибыли по таким строкам неполный."
            )
        if ad_cluster_rows == 0:
            notes.append(
                f"Детальная статистика по рекламным кластерам пока не готова. {ad_cluster_reason or 'Экран рекламы и детализация расхождений по рекламным расходам будут неполными.'}"
            )
        if (
            latest_run_by_domain.get("stocks") is not None
            and latest_run_by_domain["stocks"].status != "completed"
            and latest_stocks_status == "completed"
        ):
            notes.append(
                "Последняя загрузка остатков завершилась неидеально, но используется свежий снимок из предыдущей успешной загрузки."
            )
        if failed_domains:
            notes.append(
                f"Есть разделы, где последняя загрузка завершилась ошибкой: {', '.join(failed_domains)}."
            )
        if non_blocking_failed_domains:
            notes.append(
                f"Есть ошибки загрузки, которые сейчас не мешают денежной аналитике: {', '.join(non_blocking_failed_domains)}."
            )
        if transient_failed_domains:
            notes.append(
                f"Были временные ошибки лимита API, но используются последние успешные данные: {', '.join(transient_failed_domains)}."
            )
        supply_only_unmatched_count = sum(
            1 for issue in open_issues if self._issue_is_supply_source_unmatched(issue)
        )
        if supply_only_unmatched_count > 0:
            notes.append(
                f"{supply_only_unmatched_count} проблем с непривязанными карточками относятся только к поставкам и не блокируют денежную аналитику."
            )
        if (
            effective_blocking_open_issue_count > 0
            and not cost_policy_owner_approves_final(cost_trust_policy)
        ):
            notes.append(
                f"Есть незакрытые блокирующие проблемы качества данных уровня error/critical: {effective_blocking_open_issue_count}. Надежный бизнес-статус еще не подтвержден."
            )
        trust_decision = build_global_trust_decision(
            supplier_confirmed_revenue_coverage_percent=supplier_confirmed_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=trusted_revenue_cost_coverage_percent,
            cost_trust_policy=cost_trust_policy,
            failed_domains=failed_domains,
            unresolved_unmatched_sku_count=blocking_unmatched_sku_count,
            latest_stocks_status=latest_stocks_status,
            blocking_open_issue_count=effective_blocking_open_issue_count,
            article_audit_consistent=None,
            scheduler_stable=True,
        )
        cost_coverage_decision = build_cost_coverage_decision(
            total_revenue=float(
                revenue_with_cost_decimal + revenue_without_cost_decimal
            ),
            supplier_confirmed_revenue=float(
                revenue_with_supplier_confirmed_cost_decimal
            ),
            operator_baseline_revenue=float(
                max(
                    Decimal("0"),
                    revenue_with_trusted_cost_decimal
                    - revenue_with_supplier_confirmed_cost_decimal,
                )
            ),
            missing_cost_revenue=float(
                max(
                    Decimal("0"),
                    revenue_with_cost_decimal
                    + revenue_without_cost_decimal
                    - revenue_with_trusted_cost_decimal,
                )
            ),
            cost_trust_policy=cost_trust_policy,
        )
        data_quality_summary = self._build_data_quality_summary(
            issue_buckets=issue_buckets,
            blocked_reasons=trust_decision.blocked_reasons,
            final_profit_allowed=cost_coverage_decision.can_use_for_final_profit,
            all_open_issues_total=all_open_issues_total,
            blocking_open_issues_total=effective_blocking_open_issue_count,
            financial_final_blockers_total=effective_financial_final_blockers_total,
        )
        operator_baseline_revenue_coverage_percent = (
            self._operator_baseline_revenue_coverage_percent(
                total_revenue=(
                    revenue_with_cost_decimal + revenue_without_cost_decimal
                ),
                supplier_confirmed_revenue=revenue_with_supplier_confirmed_cost_decimal,
                trusted_revenue=revenue_with_trusted_cost_decimal,
            )
        )
        public_trust = build_public_trust_snapshot(
            operational_trusted=bool(trust_decision.can_generate_business_actions),
            supplier_confirmed_revenue_coverage_percent=supplier_confirmed_revenue_coverage_percent,
            operator_baseline_revenue_coverage_percent=operator_baseline_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=trusted_revenue_cost_coverage_percent,
            financial_final_blockers_total=data_quality_summary.financial_final_blockers_total,
            cost_trust_policy=cost_trust_policy,
            finance_reconciliation_clean=data_quality_summary.financial_final_blockers_total
            == 0,
            blocked_reasons=trust_decision.blocked_reasons,
            placeholder_only=placeholder_manual_cost_count > 0
            and trusted_manual_cost_count == 0
            and supplier_confirmed_manual_cost_count == 0,
            all_open_issues_total=all_open_issues_total,
            blocking_open_issues_total=effective_blocking_open_issue_count,
            preserve_blocker_counts=True,
        )
        result = DashboardDataHealth(
            account_id=account_id,
            open_issues_total=data_quality_summary.open_issues_total,
            all_open_issues_total=all_open_issues_total,
            blocking_open_issues_total=public_trust.blocking_open_issues_total,
            data_health_blockers_total=local_financial_final_blockers_total,
            dq_summary_blockers_total=dq_summary_blockers_total,
            trust_consistency_status=trust_consistency_status,
            trust_consistency_warning=trust_consistency_warning,
            failed_domains=failed_domains,
            skipped_domains=skipped_domains,
            missed_days_count=missed_days_count,
            missing_manual_cost_count=missing_manual_cost_count,
            unmatched_sku_count=unmatched_sku_count,
            all_open_unmatched_sku_count=all_open_unmatched_sku_count,
            open_unmatched_sku_count=open_unmatched_sku_count,
            blocking_unmatched_sku_count=blocking_unmatched_sku_count,
            resolved_unmatched_sku_count=0,
            all_open_finance_mismatch_count=all_open_finance_mismatch_count,
            blocking_finance_mismatch_count=blocking_finance_mismatch_count,
            all_open_cost_issue_count=all_open_cost_issue_count,
            blocking_cost_issue_count=blocking_cost_issue_count,
            all_open_stock_issue_count=all_open_stock_issue_count,
            blocking_stock_issue_count=blocking_stock_issue_count,
            duplicate_srid_count=duplicate_srid_count,
            active_sku_count=active_sku_count,
            active_sku_with_manual_cost_count=active_sku_with_manual_cost_count,
            placeholder_manual_cost_count=placeholder_manual_cost_count,
            real_manual_cost_count=supplier_confirmed_manual_cost_count,
            trusted_manual_cost_count=trusted_manual_cost_count,
            revenue_rows_with_cost=revenue_rows_with_cost,
            revenue_rows_without_cost=revenue_rows_without_cost,
            revenue_with_cost=revenue_with_cost,
            revenue_without_cost=revenue_without_cost,
            revenue_with_real_cost=revenue_with_supplier_confirmed_cost,
            revenue_with_placeholder_cost=revenue_with_placeholder_cost,
            sku_cost_coverage_percent=self._percent(
                active_sku_with_manual_cost_count, active_sku_count
            ),
            revenue_cost_coverage_percent=self._percent(
                revenue_with_cost_decimal,
                revenue_with_cost_decimal + revenue_without_cost_decimal,
            ),
            real_revenue_cost_coverage_percent=supplier_confirmed_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=trusted_revenue_cost_coverage_percent,
            supplier_confirmed_revenue_coverage_percent=supplier_confirmed_revenue_coverage_percent,
            operator_baseline_revenue_coverage_percent=operator_baseline_revenue_coverage_percent,
            cost_trust_policy=cost_trust_policy,
            cost_coverage=DashboardCostCoverageBlock(
                operational_cost_coverage_percent=cost_coverage_decision.operational_cost_coverage_percent,
                operational_label="Покрыто текущей себестоимостью",
                supplier_confirmed_cost_coverage_percent=cost_coverage_decision.supplier_confirmed_cost_coverage_percent,
                supplier_confirmed_label="Покрыто подтвержденной себестоимостью",
                business_accepted_cost_coverage_percent=cost_coverage_decision.business_accepted_cost_coverage_percent,
                business_accepted_label="Покрыто принятой себестоимостью",
                cost_policy=cost_coverage_decision.cost_policy,
                cost_truth_level=cost_coverage_decision.cost_truth_level,
                can_use_for_operations=cost_coverage_decision.can_use_for_operations,
                can_use_for_final_profit=cost_coverage_decision.can_use_for_final_profit,
                missing_cost_revenue=cost_coverage_decision.missing_cost_revenue,
                operator_baseline_revenue=cost_coverage_decision.operator_baseline_revenue,
                supplier_confirmed_revenue=cost_coverage_decision.supplier_confirmed_revenue,
                message=cost_coverage_decision.message,
            ),
            classified_unmatched_sku_count=classified_unmatched_sku_count,
            business_trusted=public_trust.business_trusted,
            operational_trusted=public_trust.operational_trusted,
            financial_final=public_trust.financial_final,
            trust_state=public_trust.trust_state,
            financial_final_blockers_total=public_trust.financial_final_blockers_total,
            final_profit_blockers_total=public_trust.final_profit_blockers_total,
            blocked_reasons=trust_decision.blocked_reasons,
            can_generate_business_actions=public_trust.operational_trusted,
            ad_cluster_rows=ad_cluster_rows,
            ad_cluster_state=ad_cluster_state,
            ad_cluster_reason=ad_cluster_reason,
            latest_stocks_status=latest_stocks_status,
            issue_buckets=issue_buckets,
            data_quality_summary=data_quality_summary,
            domains=domain_statuses,
            notes=notes,
        )
        self._data_health_cache[cache_key] = (utcnow(), result.model_copy(deep=True))
        return result

    async def article_audit(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        issues_limit: int = 50,
        issues_offset: int = 0,
    ) -> ArticleAuditRead:
        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.nm_id == nm_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        price = (
            await session.execute(
                select(WBPrice).where(
                    WBPrice.account_id == account_id, WBPrice.nm_id == nm_id
                )
            )
        ).scalar_one_or_none()
        product_card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == nm_id,
                )
            )
        ).scalar_one_or_none()
        current_orders = await self._load_current_orders(
            session,
            account_id=account_id,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
        )
        current_sales = await self._load_current_sales(
            session,
            account_id=account_id,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
        )
        latest_order = max(
            current_orders,
            key=lambda row: (
                row.get("last_change_date") or row.get("date") or datetime.min
            ),
            default=None,
        )
        latest_sale = max(
            current_sales,
            key=lambda row: (
                row.get("last_change_date") or row.get("date") or datetime.min
            ),
            default=None,
        )
        latest_stock_row = (
            await session.execute(
                select(WBStockSnapshotRow)
                .where(
                    WBStockSnapshotRow.account_id == account_id,
                    WBStockSnapshotRow.nm_id == nm_id,
                )
                .order_by(WBStockSnapshotRow.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        identity = ArticleIdentity(
            nm_id=nm_id,
            vendor_code=(
                (product_card.vendor_code if product_card else None)
                or (price.vendor_code if price else None)
                or (latest_sale.get("supplier_article") if latest_sale else None)
                or (latest_order.get("supplier_article") if latest_order else None)
            ),
            barcode=(
                (latest_stock_row.barcode if latest_stock_row else None)
                or (latest_sale.get("barcode") if latest_sale else None)
                or (latest_order.get("barcode") if latest_order else None)
            ),
            title=product_card.title if product_card else None,
            brand=(
                (product_card.brand if product_card else None)
                or (latest_sale.get("brand") if latest_sale else None)
                or (latest_stock_row.brand if latest_stock_row else None)
            ),
            subject_name=(
                (product_card.subject_name if product_card else None)
                or (latest_sale.get("subject") if latest_sale else None)
                or (latest_stock_row.subject if latest_stock_row else None)
            ),
        )

        price_sizes = list(
            (
                await session.execute(
                    select(WBPriceSize).where(
                        WBPriceSize.account_id == account_id, WBPriceSize.nm_id == nm_id
                    )
                )
            ).scalars()
        )

        finance_stmt = select(WBRealizationReportRow).where(
            WBRealizationReportRow.account_id == account_id,
            WBRealizationReportRow.nm_id == nm_id,
        )
        ads_stmt = select(WBAdStatsDaily).where(
            WBAdStatsDaily.account_id == account_id, WBAdStatsDaily.nm_id == nm_id
        )
        funnel_stmt = select(WBCardFunnelDaily).where(
            WBCardFunnelDaily.account_id == account_id,
            WBCardFunnelDaily.nm_id == nm_id,
        )
        if date_from is not None:
            finance_stmt = finance_stmt.where(
                WBRealizationReportRow.rr_date >= date_from
            )
            ads_stmt = ads_stmt.where(WBAdStatsDaily.stat_date >= date_from)
            funnel_stmt = funnel_stmt.where(WBCardFunnelDaily.stat_date >= date_from)
        if date_to is not None:
            finance_stmt = finance_stmt.where(WBRealizationReportRow.rr_date <= date_to)
            ads_stmt = ads_stmt.where(WBAdStatsDaily.stat_date <= date_to)
            funnel_stmt = funnel_stmt.where(WBCardFunnelDaily.stat_date <= date_to)

        orders = current_orders
        sales = current_sales
        finance_rows = list((await session.execute(finance_stmt)).scalars())
        ad_rows = list((await session.execute(ads_stmt)).scalars())
        funnel_rows = list((await session.execute(funnel_stmt)).scalars())
        mart_stmt = select(MartSKUDaily).where(
            MartSKUDaily.account_id == account_id,
            MartSKUDaily.nm_id == nm_id,
        )
        if date_from is not None:
            mart_stmt = mart_stmt.where(MartSKUDaily.stat_date >= date_from)
        if date_to is not None:
            mart_stmt = mart_stmt.where(MartSKUDaily.stat_date <= date_to)
        mart_rows = list((await session.execute(mart_stmt)).scalars())
        cost_rows = await self._load_cost_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        resolved_sku = self._resolve_sku(
            core_skus,
            vendor_code=identity.vendor_code,
            nm_id=nm_id,
            barcode=identity.barcode,
        )
        matched_cost = self._match_cost_for_sku(
            cost_rows,
            sku_id=resolved_sku.id if resolved_sku is not None else None,
            at_date=date_to or date_from,
        )
        cost_source = (
            getattr(matched_cost, "cost_source", None) or matched_cost.match_rule
            if matched_cost is not None
            else None
        )

        latest_snapshot_id = latest_stock_row.snapshot_id if latest_stock_row else None
        latest_snapshot = (
            await session.get(WBStockSnapshot, latest_snapshot_id)
            if latest_snapshot_id is not None
            else None
        )
        stock_rows: list[WBStockSnapshotRow] = []
        if latest_snapshot_id is not None:
            stock_rows = list(
                (
                    await session.execute(
                        select(WBStockSnapshotRow).where(
                            WBStockSnapshotRow.account_id == account_id,
                            WBStockSnapshotRow.snapshot_id == latest_snapshot_id,
                            WBStockSnapshotRow.nm_id == nm_id,
                        )
                    )
                ).scalars()
            )

        operations_dates = [
            item.get("date") for item in orders if item.get("date") is not None
        ] + [item.get("date") for item in sales if item.get("date") is not None]
        operations = ArticleOperationsSummary(
            orders_count=len(orders),
            cancelled_orders_count=sum(1 for item in orders if item.get("is_cancel")),
            orders_gross_amount=float(
                sum(
                    (self._decimal(item.get("total_price")) for item in orders),
                    start=Decimal("0"),
                )
            ),
            orders_finished_amount=float(
                sum(
                    (self._decimal(item.get("finished_price")) for item in orders),
                    start=Decimal("0"),
                )
            ),
            sales_count=sum(
                1 for item in sales if self._decimal(item.get("total_price")) >= 0
            ),
            returns_count=sum(
                1 for item in sales if self._decimal(item.get("total_price")) < 0
            ),
            sales_gross_amount=float(
                sum(
                    (self._decimal(item.get("total_price")) for item in sales),
                    start=Decimal("0"),
                )
            ),
            sales_for_pay=float(
                sum(
                    (self._decimal(item.get("for_pay")) for item in sales),
                    start=Decimal("0"),
                )
            ),
            first_event_at=min(operations_dates) if operations_dates else None,
            last_event_at=max(operations_dates) if operations_dates else None,
        )

        source_article_ad_spend = sum(
            (self._decimal(item.sum) for item in ad_rows), start=Decimal("0")
        )
        article_ad_rows = [self._row_ad_components(item) for item in mart_rows]
        operational_article_ad_spend = sum(
            (self._decimal(item["ad_spend_operational"]) for item in article_ad_rows),
            start=Decimal("0"),
        )
        finance_article_ad_spend = sum(
            (self._decimal(item["ad_spend_finance"]) for item in article_ad_rows),
            start=Decimal("0"),
        )
        final_article_ad_spend = sum(
            (self._decimal(item["ad_spend_final"]) for item in article_ad_rows),
            start=Decimal("0"),
        )
        if finance_article_ad_spend > 0:
            article_ads_metrics = {
                "raw_ad_spend": final_article_ad_spend
                if final_article_ad_spend > 0
                else finance_article_ad_spend,
                "capped_ad_spend": final_article_ad_spend
                if final_article_ad_spend > 0
                else finance_article_ad_spend,
                "overallocated_ad_spend": Decimal("0"),
                "unallocated_ad_spend": max(
                    Decimal("0"),
                    source_article_ad_spend
                    - (
                        operational_article_ad_spend
                        if operational_article_ad_spend > 0
                        else source_article_ad_spend
                    ),
                ),
                "ads_allocation_status": "finance_final",
                "final_profit_allowed": True,
            }
            article_ad_source = AD_SPEND_SOURCE_FINANCE
        else:
            article_ads_metrics = self._ads_allocation_metrics(
                mart_ad_spend=operational_article_ad_spend
                if operational_article_ad_spend > 0
                else final_article_ad_spend,
                source_ad_spend=source_article_ad_spend,
            )
            article_ad_source = (
                AD_SPEND_SOURCE_OPERATIONAL
                if self._decimal(article_ads_metrics["capped_ad_spend"]) > 0
                else AD_SPEND_SOURCE_NONE
            )
        ads = ArticleAdsSummary(
            stats_rows_count=len(ad_rows),
            spend=float(self._decimal(article_ads_metrics["capped_ad_spend"])),
            operational_spend=float(
                operational_article_ad_spend
                if operational_article_ad_spend > 0
                else source_article_ad_spend
            ),
            finance_spend=float(finance_article_ad_spend),
            final_spend=float(self._decimal(article_ads_metrics["capped_ad_spend"])),
            spend_source=article_ad_source,
            spend_delta=float(
                (
                    operational_article_ad_spend
                    if operational_article_ad_spend > 0
                    else source_article_ad_spend
                )
                - finance_article_ad_spend
            ),
            raw_allocated_spend=float(
                self._decimal(article_ads_metrics["raw_ad_spend"])
            ),
            capped_allocated_spend=float(
                self._decimal(article_ads_metrics["capped_ad_spend"])
            ),
            overallocated_spend=float(
                self._decimal(article_ads_metrics["overallocated_ad_spend"])
            ),
            unallocated_spend=float(
                self._decimal(article_ads_metrics["unallocated_ad_spend"])
            ),
            allocation_status=str(article_ads_metrics["ads_allocation_status"]),
            final_profit_allowed=bool(article_ads_metrics["final_profit_allowed"]),
            views=sum((item.views or 0) for item in ad_rows),
            clicks=sum((item.clicks or 0) for item in ad_rows),
            orders=sum((item.orders or 0) for item in ad_rows),
            atbs=sum((item.atbs or 0) for item in ad_rows),
        )

        funnel = ArticleFunnelSummary(
            days_count=len(funnel_rows),
            open_count=sum((item.open_count or 0) for item in funnel_rows),
            cart_count=sum((item.cart_count or 0) for item in funnel_rows),
            order_count=sum((item.order_count or 0) for item in funnel_rows),
            buyout_count=sum((item.buyout_count or 0) for item in funnel_rows),
            cancel_count=sum((item.cancel_count or 0) for item in funnel_rows),
        )

        stock_quantity, stock_quantity_full, in_way_to_client, in_way_from_client = (
            self._aggregate_article_stock_rows(stock_rows)
        )
        stock = ArticleStockSummary(
            snapshot_at=latest_snapshot.snapshot_at if latest_snapshot else None,
            rows_count=len(stock_rows),
            quantity=float(stock_quantity),
            quantity_full=float(stock_quantity_full),
            in_way_to_client=float(in_way_to_client),
            in_way_from_client=float(in_way_from_client),
            warehouses=sorted(
                {item.warehouse_name for item in stock_rows if item.warehouse_name}
            ),
        )

        price_snapshot = None
        if price is not None:
            payload_sizes = (
                ((price.payload or {}).get("sizes") or [])
                if isinstance(price.payload, dict)
                else []
            )
            payload_prices = [
                self._decimal(size.get("price"))
                for size in payload_sizes
                if isinstance(size, dict) and size.get("price") is not None
            ]
            payload_discounted = [
                self._decimal(size.get("discountedPrice"))
                for size in payload_sizes
                if isinstance(size, dict) and size.get("discountedPrice") is not None
            ]
            prices = [
                self._decimal(size.price)
                for size in price_sizes
                if size.price is not None
            ] or payload_prices
            discounted = [
                self._decimal(size.discounted_price)
                for size in price_sizes
                if size.discounted_price is not None
            ] or payload_discounted
            price_snapshot = ArticlePriceSnapshot(
                currency=price.currency_iso_code,
                discount=price.discount,
                club_discount=price.club_discount,
                editable_size_price=price.editable_size_price,
                sizes_count=len(price_sizes) or len(payload_sizes),
                min_price=float(min(prices)) if prices else None,
                max_price=float(max(prices)) if prices else None,
                min_discounted_price=float(min(discounted)) if discounted else None,
                max_discounted_price=float(max(discounted)) if discounted else None,
            )

        completeness = ArticleCompleteness(
            has_product_card=product_card is not None,
            has_price=price is not None,
            has_orders=bool(orders),
            has_sales=bool(sales),
            has_stock=bool(stock_rows),
            has_finance=bool(finance_rows),
            has_ads=bool(ad_rows),
            has_funnel=bool(funnel_rows),
            has_manual_cost=matched_cost is not None,
        )

        manual_cost = self._build_article_manual_cost_match(
            matched_cost,
            source=cost_source,
            total_unit_cost=self._total_unit_cost(matched_cost)
            if matched_cost is not None
            else None,
        )

        daily_economics = self._build_article_daily_economics(
            mart_rows, ad_rows=ad_rows
        )
        daily_series = self._build_article_daily_series(mart_rows, ad_rows=ad_rows)
        finance = self._build_article_finance_summary(mart_rows, finance_rows)

        all_issue_rows = list(
            (
                await session.execute(
                    select(DataQualityIssue)
                    .where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                        DataQualityIssue.code.notin_(
                            sorted(self.HIDDEN_USER_ISSUE_CODES)
                        ),
                    )
                    .order_by(DataQualityIssue.detected_at.desc())
                )
            ).scalars()
        )
        issue_rows: list[DataQualityIssue] = []
        for item in all_issue_rows:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=item.sku_id,
                nm_id=item.nm_id,
                entity_key=item.entity_key,
                payload=item.payload,
            )
            if resolved_sku is not None and issue_sku_id == resolved_sku.id:
                issue_rows.append(item)
            elif issue_nm_id == nm_id:
                issue_rows.append(item)
        issues_total = len(issue_rows)
        paged_issue_rows = issue_rows[issues_offset : issues_offset + issues_limit]
        issues = [
            ArticleIssueSummary(
                id=item.id,
                domain=item.domain,
                code=item.code,
                severity=item.severity,
                message=item.message,
                detected_at=item.detected_at,
                source_table=item.source_table,
                first_seen_at=(dict(item.payload or {}).get("firstSeenAt")),
                last_seen_at=(dict(item.payload or {}).get("lastSeenAt")),
                age_bucket=(dict(item.payload or {}).get("ageBucket")),
            )
            for item in paged_issue_rows
        ]
        reconciliation = self._build_article_reconciliation_summary(
            mart_rows,
            issue_rows,
            finance_rows=finance_rows,
            operational_revenue_total=Decimal(str(operations.sales_gross_amount)),
        )

        notes: list[ArticleNote] = []
        if not completeness.has_product_card:
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="Карточка товара по этому артикулу не загружена, поэтому данные собраны из цен, заказов, продаж и остатков.",
                )
            )
        if not completeness.has_finance:
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="За этот период еще нет строк из финансового отчета WB, поэтому точная прибыль пока недоступна.",
                )
            )
        if not completeness.has_manual_cost:
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="По этому артикулу не настроена себестоимость, поэтому расчет прибыли неполный.",
                )
            )
        if completeness.has_sales and not completeness.has_stock:
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="Продажи есть, но свежего снимка остатков по этому артикулу нет.",
                )
            )
        if manual_cost is not None and manual_cost.supplier == "AUTO_TEMPLATE":
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="Текущая себестоимость по этой карточке взята из шаблона, а не из реального файла поставщика.",
                )
            )
        elif manual_cost is not None and not manual_cost.is_business_trusted:
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="Себестоимость загружена, но еще не принята как надежная для бизнес-решений.",
                )
            )
        if any(item.final_revenue_source == "operational" for item in mart_rows):
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="В выбранном периоде есть выручка по оперативным данным. Расходы WB за эти дни могут быть еще не полностью закрыты отчетом WB.",
                )
            )
        if any(
            item.final_revenue_source == "finance" and not item.has_manual_cost
            for item in mart_rows
        ):
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="Выручка по отчету WB уже есть, но часть ее все еще не связана с себестоимостью на уровне карточки.",
                )
            )
        if not reconciliation.revenue_matches_mart:
            notes.append(
                ArticleNote(
                    at=None,
                    author="system",
                    text="Выручка в аудите артикула не совпадает с расчетной выручкой за выбранный период. Нужна сверка.",
                )
            )

        health = await self.data_health(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        local_operational_trusted = bool(
            health.operational_trusted
            and manual_cost is not None
            and not manual_cost.is_placeholder
        )
        local_financial_blockers = int(health.financial_final_blockers_total or 0)
        if not reconciliation.revenue_matches_mart:
            local_financial_blockers += 1
        article_trust = build_public_trust_snapshot(
            operational_trusted=local_operational_trusted,
            supplier_confirmed_revenue_coverage_percent=health.supplier_confirmed_revenue_coverage_percent
            or 0.0,
            operator_baseline_revenue_coverage_percent=health.operator_baseline_revenue_coverage_percent
            or 0.0,
            trusted_revenue_cost_coverage_percent=health.trusted_revenue_cost_coverage_percent
            or 0.0,
            financial_final_blockers_total=local_financial_blockers,
            cost_trust_policy=health.cost_trust_policy,
            finance_reconciliation_clean=bool(reconciliation.revenue_matches_mart),
            blocked_reasons=list(health.blocked_reasons or []),
            placeholder_only=bool(manual_cost and manual_cost.is_placeholder),
            all_open_issues_total=int(getattr(health, "all_open_issues_total", 0) or 0),
            blocking_open_issues_total=int(
                getattr(health, "blocking_open_issues_total", 0) or 0
            ),
            preserve_blocker_counts=True,
        )

        return ArticleAuditRead(
            operational_trusted=article_trust.operational_trusted,
            business_trusted=article_trust.business_trusted,
            financial_final=article_trust.financial_final,
            trust_state=article_trust.trust_state,
            cost_trust_policy=article_trust.cost_trust_policy,
            supplier_confirmed_revenue_coverage_percent=article_trust.supplier_confirmed_revenue_coverage_percent,
            operator_baseline_revenue_coverage_percent=article_trust.operator_baseline_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=article_trust.trusted_revenue_cost_coverage_percent,
            financial_final_blockers_total=article_trust.financial_final_blockers_total,
            final_profit_blockers_total=article_trust.final_profit_blockers_total,
            all_open_issues_total=article_trust.all_open_issues_total,
            blocking_open_issues_total=article_trust.blocking_open_issues_total,
            identity=identity,
            completeness=completeness,
            price=price_snapshot,
            operations=operations,
            finance=finance,
            ads=ads,
            funnel=funnel,
            stock=stock,
            manual_cost=manual_cost,
            daily_economics=daily_economics,
            daily_series=daily_series,
            reconciliation=reconciliation,
            issues_total=issues_total,
            issues_limit=issues_limit,
            issues_offset=issues_offset,
            issues=issues,
            notes=notes,
        )
