from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from math import ceil
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import table_signature
from app.core.enums_meta import get_enum_mapping
from app.core.expense_taxonomy import (
    additional_income as expense_additional_income,
    expense_data_quality as compute_expense_data_quality,
)
from app.core.issue_refs import extract_issue_refs
from app.core.pagination import Page
from app.core.stock_fallback import latest_stock_snapshot
from app.core.time import utcnow
from app.models.ads import WBAdCampaign, WBAdStatsDaily
from app.models.control_tower import (
    ActionRecommendation,
    ActionRecommendationHistory,
    AlertEvent,
    FormulaAuditRun,
    UserBusinessSetting,
    UserBusinessSettingAudit,
)
from app.models.data_quality import DataQualityIssue
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.prices import WBPrice, WBPriceQuarantine, WBPriceSize
from app.models.product_cards import CoreSKU, WBProductCard
from app.models.promotions import WBPromotionCalendar, WBPromotionNomenclature
from app.models.sync import WBSyncCursor
from app.schemas.control_tower import (
    ActionRecommendationListItem,
    ActionRecommendationRead,
    ActionRecommendationUpdateRequest,
    AdsEfficiencyPage,
    AdsEfficiencyRow,
    AdsEfficiencySummary,
    AlertRead,
    AlertUpdateRequest,
    BusinessPoliciesRead,
    BusinessPolicyOption,
    BusinessSettingsRead,
    BusinessSettingsUpdateRequest,
    ControlTowerSkuDetail,
    ControlTowerSkuRow,
    OwnerActionSummary,
    OwnerDashboardItem,
    OwnerDashboardTrust,
    OwnerDashboardRead,
    OwnerMessage,
    PriceSafetyPage,
    PriceSafetyPromotion,
    PriceSafetyRow,
    PriceSafetySummary,
    PriceSimulationRequest,
    PriceSimulationResponse,
    PurchasePlanPage,
    PurchasePlanRow,
    PurchasePlanSummary,
    PurchasePlanWaitDataReasonCounts,
)
from app.schemas.money_trust import classify_money_trust
from app.services.dashboard import DashboardService
from app.services.trust import (
    COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
    TRUST_STATE_DATA_BLOCKED,
    TRUST_STATE_TEST_ONLY,
    TRUST_STATE_TRUSTED,
    build_global_trust_decision,
    cost_truth_level_from_flags,
    normalize_blocked_reasons_for_cost_policy,
    trust_state_for_row,
)


@dataclass
class AggregatedLatestStock:
    stat_date: date
    quantity: Decimal | None
    quantity_full: Decimal | None
    in_way_to_client: Decimal | None
    in_way_from_client: Decimal | None
    avg_sales_per_day_30d: Decimal | None
    days_of_stock: Decimal | None
    sales_7d: int = 0
    sales_14d: int = 0
    sales_30d: int = 0
    days_since_last_sale: int | None = None
    turnover_rate: Decimal | None = None


@dataclass
class PriceSnapshot:
    current_price: Decimal | None
    current_discounted_price: Decimal | None
    price_source: str | None
    mapping_status: str | None


@dataclass
class PurchaseDecision:
    status: str
    reason: str
    risk: str | None
    confidence: str
    next_step: str
    financial_final: bool


@dataclass
class CachedControlRowsSnapshot:
    control_rows: list[ControlTowerSkuRow]
    price_rows: dict[int, PriceSafetyRow]
    purchase_rows: dict[int, PurchasePlanRow]
    settings: dict[str, Any]
    computed_at: datetime
    data_version_hash: str


class ControlTowerService:
    CONTROL_ROWS_CACHE_TTL_SECONDS = 600
    WARM_CONTROL_ROWS_CACHE_TTL_SECONDS = 120
    ADS_SOURCE_CACHE_TTL_SECONDS = 600
    ACTION_SYNC_CACHE_TTL_SECONDS = 600
    OWNER_DASHBOARD_CACHE_TTL_SECONDS = 120
    PURCHASE_WAIT_DATA_REASON_ORDER = ("finance", "cost", "stock", "velocity", "sales")
    PURCHASE_WAIT_DATA_REASON_BY_CODE = {
        "finance_not_confirmed": "finance",
        "article_audit_mismatch": "finance",
        "open_blocking_dq_issues": "finance",
        "sale_without_finance": "finance",
        "finance_reconciliation_mismatch": "finance",
        "supplier_cost_not_confirmed": "cost",
        "missing_manual_cost": "cost",
        "supplier_cost_coverage_below_threshold": "cost",
        "stock_data_missing": "stock",
        "latest_stocks_not_completed": "stock",
        "stocks_task_not_ready": "stock",
        "stocks_not_completed": "stock",
        "velocity_data_missing": "velocity",
        "sales_data_missing": "sales",
        "profit_data_missing": "sales",
    }
    _shared_control_rows_cache: dict[
        tuple[int, date, date, str], CachedControlRowsSnapshot
    ] = {}
    _shared_control_rows_window_cache: dict[
        tuple[int, date, date], CachedControlRowsSnapshot
    ] = {}
    _shared_control_rows_inflight: dict[
        tuple[int, date, date], asyncio.Task[tuple[CachedControlRowsSnapshot, str]]
    ] = {}
    _shared_control_rows_last_meta: dict[tuple[int, date, date], dict[str, Any]] = {}
    _shared_ads_source_cache: dict[
        tuple[int, date, date], tuple[datetime, dict[int, Decimal], Decimal]
    ] = {}
    _shared_action_sync_cache: dict[
        tuple[int, date, date], tuple[datetime, str | None]
    ] = {}
    _shared_action_sync_last_meta: dict[tuple[int, date, date], dict[str, Any]] = {}
    _shared_owner_dashboard_cache: dict[
        tuple[int, date, date], tuple[datetime, OwnerDashboardRead]
    ] = {}
    STORAGE_NOT_READY_DETAIL = (
        "Control Tower storage is not initialized. Run `alembic upgrade head`."
    )
    DEFAULT_SETTINGS: dict[str, Any] = {
        "target_margin_rate": 0.2,
        "target_roi_percent": 30,
        "lead_time_days": 14,
        "safety_days": 7,
        "overstock_threshold_days": 90,
        "oos_threshold_days": 7,
        "min_profit_threshold": 0,
        "ad_drr_threshold_percent": 25,
        "large_logistics_share_threshold_percent": 70,
        "pack_multiple": 1,
        "cost_trust_policy": "operator_baseline",
        "require_seller_other_expense": False,
        "issue_aging": {"pending_days": 2, "warning_days": 7},
    }
    COST_TRUST_POLICIES: tuple[dict[str, str], ...] = (
        {
            "value": "supplier_only",
            "label": "Только подтвержденная себестоимость",
            "description": "Использовать только реальную загруженную поставщиком себестоимость.",
        },
        {
            "value": "operator_baseline",
            "label": "Операторская базовая себестоимость",
            "description": "Разрешить операторскую базовую себестоимость как резервный вариант для внутренних оценок.",
        },
        {
            "value": "mixed",
            "label": "Смешанный режим",
            "description": "Приоритет подтвержденной себестоимости с резервным использованием временных данных для мониторинга витрин и предупреждений.",
        },
        {
            "value": COST_TRUST_POLICY_OWNER_APPROVED_FINAL,
            "label": "Временно принять как финальное",
            "description": "Владелец временно принимает текущую операционную себестоимость и открытые блокеры качества данных до обновления реальных данных.",
        },
    )

    def __init__(self) -> None:
        self.dashboard = DashboardService()
        self._money_management_service = None
        self._control_rows_cache = type(self)._shared_control_rows_cache
        self._control_rows_window_cache = type(self)._shared_control_rows_window_cache
        self._control_rows_inflight = type(self)._shared_control_rows_inflight
        self._control_rows_last_meta = type(self)._shared_control_rows_last_meta
        self._ads_source_cache = type(self)._shared_ads_source_cache
        self._action_sync_cache = type(self)._shared_action_sync_cache
        self._action_sync_last_meta = type(self)._shared_action_sync_last_meta
        self._owner_dashboard_cache = type(self)._shared_owner_dashboard_cache

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value or 0))

    @staticmethod
    def _optional_decimal(value: object) -> Decimal | None:
        if value in (None, ""):
            return None
        return Decimal(str(value))

    @staticmethod
    def _date_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
        today = utcnow().date()
        return date_from or (today - timedelta(days=29)), date_to or today

    @staticmethod
    def _float(value: Decimal | None) -> float | None:
        return float(value) if value is not None else None

    @staticmethod
    def _float0(value: Decimal | float | int | None) -> float:
        return float(value or 0)

    @staticmethod
    def _int0(value: object) -> int:
        try:
            return int(Decimal(str(value or 0)))
        except Exception:
            return 0

    @staticmethod
    def _safe_percent(
        delta: int | Decimal | float, base: int | Decimal | float
    ) -> float | None:
        base_decimal = Decimal(str(base or 0))
        if base_decimal == 0:
            return None
        return float((Decimal(str(delta or 0)) / base_decimal) * Decimal("100"))

    @staticmethod
    def _trend_direction(delta: int | Decimal | float) -> str:
        delta_decimal = Decimal(str(delta or 0))
        if delta_decimal > 0:
            return "up"
        if delta_decimal < 0:
            return "down"
        return "flat"

    @staticmethod
    def _payload_first_text(payload: dict[str, Any] | None, *keys: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @classmethod
    def _first_product_photo_url(cls, value: Any) -> str | None:
        if isinstance(value, str):
            text = value.strip()
            return text if text.startswith(("http://", "https://")) else None
        if isinstance(value, list):
            for item in value:
                url = cls._first_product_photo_url(item)
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
                    url = cls._first_product_photo_url(nested)
                    if url:
                        return url
        return None

    @staticmethod
    def _percent0(
        part: Decimal | int | float | None, whole: Decimal | int | float | None
    ) -> float:
        whole_decimal = Decimal(str(whole or 0))
        if whole_decimal <= 0:
            return 0.0
        return float((Decimal(str(part or 0)) / whole_decimal) * Decimal("100"))

    @staticmethod
    def _cache_is_fresh(cached_at: datetime, *, ttl_seconds: int) -> bool:
        return (utcnow() - cached_at) <= timedelta(seconds=ttl_seconds)

    @staticmethod
    def _control_rows_window_key(
        *, account_id: int, date_from: date, date_to: date
    ) -> tuple[int, date, date]:
        return (account_id, date_from, date_to)

    @staticmethod
    def _control_rows_cache_key(
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        data_version_hash: str | None = None,
    ) -> tuple[int, date, date, str]:
        return (account_id, date_from, date_to, data_version_hash or "")

    @staticmethod
    def _ads_source_cache_key(
        *, account_id: int, date_from: date, date_to: date
    ) -> tuple[int, date, date]:
        return (account_id, date_from, date_to)

    @staticmethod
    def _action_sync_cache_key(
        *, account_id: int, date_from: date, date_to: date
    ) -> tuple[int, date, date]:
        return (account_id, date_from, date_to)

    def _control_rows_snapshot_hash(
        self,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        settings: dict[str, Any],
        control_rows: list[ControlTowerSkuRow],
        price_rows: dict[int, PriceSafetyRow],
        purchase_rows: dict[int, PurchasePlanRow],
    ) -> str:
        revenue_total = sum(
            (self._decimal(item.revenue) for item in control_rows), start=Decimal("0")
        )
        ad_spend_total = sum(
            (self._decimal(item.ad_spend) for item in control_rows), start=Decimal("0")
        )
        stock_value_total = sum(
            (self._decimal(item.stock_value) for item in control_rows),
            start=Decimal("0"),
        )
        payload = "|".join(
            [
                str(account_id),
                date_from.isoformat(),
                date_to.isoformat(),
                str(settings.get("cost_trust_policy") or "operator_baseline"),
                str(len(control_rows)),
                str(len(price_rows)),
                str(len(purchase_rows)),
                str(revenue_total),
                str(ad_spend_total),
                str(stock_value_total),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _control_cache_meta(
        self, *, account_id: int, date_from: date, date_to: date
    ) -> dict[str, Any]:
        return dict(
            self._control_rows_last_meta.get(
                self._control_rows_window_key(
                    account_id=account_id, date_from=date_from, date_to=date_to
                ),
                {},
            )
        )

    def _action_sync_meta(
        self, *, account_id: int, date_from: date, date_to: date
    ) -> dict[str, Any]:
        return dict(
            self._action_sync_last_meta.get(
                self._action_sync_cache_key(
                    account_id=account_id, date_from=date_from, date_to=date_to
                ),
                {},
            )
        )

    def _control_rows_result_from_snapshot(
        self,
        *,
        window_key: tuple[int, date, date],
        snapshot: CachedControlRowsSnapshot,
        cache_status: str,
    ) -> tuple[
        list[ControlTowerSkuRow],
        dict[int, PriceSafetyRow],
        dict[int, PurchasePlanRow],
        dict[int, Any],
    ]:
        self._control_rows_last_meta[window_key] = {
            "computed_at": snapshot.computed_at,
            "cache_status": cache_status,
            "data_version_hash": snapshot.data_version_hash,
        }
        return (
            snapshot.control_rows,
            snapshot.price_rows,
            snapshot.purchase_rows,
            snapshot.settings,
        )

    async def _control_rows_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> str:
        mart_hash = await table_signature(
            session,
            model=MartSKUDaily,
            account_id=account_id,
            date_column=MartSKUDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        stock_hash = await table_signature(
            session,
            model=MartStockDaily,
            account_id=account_id,
            date_column=MartStockDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        ads_hash = await table_signature(
            session,
            model=WBAdStatsDaily,
            account_id=account_id,
            date_column=WBAdStatsDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        dq_hash = await table_signature(
            session,
            model=DataQualityIssue,
            account_id=account_id,
            extra_filters=[DataQualityIssue.resolved_at.is_(None)],
        )
        settings_hash = await table_signature(
            session,
            model=UserBusinessSetting,
            account_id=account_id,
        )
        payload = "|".join([mart_hash, stock_hash, ads_hash, dq_hash, settings_hash])
        return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()

    @staticmethod
    def _with_page_cache_meta(page: Page[Any], meta: dict[str, Any]) -> Page[Any]:
        page.computed_at = meta.get("computed_at")
        page.cache_status = str(meta.get("cache_status") or "miss")
        page.data_version_hash = meta.get("data_version_hash")
        return page

    @staticmethod
    def _action_status_filter_values(status: str | None) -> set[str] | None:
        normalized = str(status or "").strip().lower()
        if not normalized or normalized == "all":
            return None
        if normalized == "open":
            return {"new"}
        return {normalized}

    @staticmethod
    def _price_safety_summary(items: list[PriceSafetyRow]) -> PriceSafetySummary:
        summary = PriceSafetySummary(total_count=len(items))
        for item in items:
            state = str(item.calculation_state or "").strip().lower()
            action_hint = str(item.action_hint or "").strip().upper()
            if state == "computed":
                summary.computed_count += 1
                if item.safe_price_gap is not None and item.safe_price_gap < 0:
                    summary.below_break_even_count += 1
                if item.safe_price_gap is not None and item.safe_price_gap >= 0:
                    summary.safe_count += 1
                reference_price = (
                    item.reference_price
                    if item.reference_price is not None
                    else item.current_discounted_price
                    if item.current_discounted_price is not None
                    else item.current_price
                    if item.current_price is not None
                    else item.average_sale_price
                )
                target_gap = item.target_margin_gap
                if (
                    target_gap is None
                    and reference_price is not None
                    and item.target_margin_price is not None
                ):
                    target_gap = reference_price - item.target_margin_price
                if target_gap is not None and target_gap < 0:
                    summary.below_target_margin_count += 1
            else:
                summary.not_computable_count += 1
            if action_hint == "PRICE_INCREASE_REVIEW":
                summary.price_increase_review_count += 1
            if item.editable_size_price:
                summary.editable_size_price_count += 1
            if item.is_bad_turnover:
                summary.bad_turnover_count += 1
            if item.quarantine:
                summary.quarantine_count += 1
            if item.wholesale_discount_thresholds:
                summary.wholesale_discount_count += 1
            if item.promotion_calendar_synced:
                summary.promotion_calendar_synced_count += 1
            if item.promotion_active_count > 0:
                summary.promotion_active_count += 1
            if item.promotion_available_count > 0:
                summary.promotion_available_count += 1
            promotion_plan_state = str(item.promotion_plan_state or "").strip().lower()
            if promotion_plan_state == "below_break_even":
                summary.promotion_plan_below_break_even_count += 1
            elif promotion_plan_state == "below_target":
                summary.promotion_plan_below_target_count += 1
            elif promotion_plan_state == "safe":
                summary.promotion_plan_safe_count += 1
        return summary

    @staticmethod
    def _payload_float(payload: dict[str, Any], *keys: str) -> float | None:
        for key in keys:
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _payload_int(payload: dict[str, Any], *keys: str) -> int | None:
        value = ControlTowerService._payload_float(payload, *keys)
        return int(value) if value is not None else None

    async def _attach_wb_price_signals(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        items: list[PriceSafetyRow],
    ) -> None:
        nm_ids = sorted({int(item.nm_id) for item in items if item.nm_id is not None})
        if not nm_ids:
            return

        price_rows = list(
            (
                await session.execute(
                    select(WBPrice).where(
                        WBPrice.account_id == account_id,
                        WBPrice.nm_id.in_(nm_ids),
                    )
                )
            ).scalars()
        )
        prices_by_nm = {int(row.nm_id): row for row in price_rows}

        size_rows = list(
            (
                await session.execute(
                    select(WBPriceSize).where(
                        WBPriceSize.account_id == account_id,
                        WBPriceSize.nm_id.in_(nm_ids),
                    )
                )
            ).scalars()
        )
        sizes_by_nm: dict[int, list[WBPriceSize]] = defaultdict(list)
        for row in size_rows:
            sizes_by_nm[int(row.nm_id)].append(row)

        quarantine_rows = list(
            (
                await session.execute(
                    select(WBPriceQuarantine)
                    .where(
                        WBPriceQuarantine.account_id == account_id,
                        WBPriceQuarantine.nm_id.in_(nm_ids),
                    )
                    .order_by(
                        WBPriceQuarantine.nm_id.asc(),
                        WBPriceQuarantine.snapshot_at.desc(),
                        WBPriceQuarantine.id.desc(),
                    )
                )
            ).scalars()
        )
        quarantine_by_nm: dict[int, WBPriceQuarantine] = {}
        for row in quarantine_rows:
            if row.nm_id is not None:
                quarantine_by_nm.setdefault(int(row.nm_id), row)

        for item in items:
            if item.nm_id is None:
                continue
            nm_id = int(item.nm_id)
            price = prices_by_nm.get(nm_id)
            if price is not None:
                payload = price.payload if isinstance(price.payload, dict) else {}
                thresholds = (
                    payload.get("wholesaleDiscountThreshold")
                    or payload.get("wholesale_discount_threshold")
                    or []
                )
                item.currency_iso_code = price.currency_iso_code
                item.discount = price.discount
                item.club_discount = price.club_discount
                item.editable_size_price = price.editable_size_price
                item.is_bad_turnover = price.is_bad_turnover
                item.wholesale_discount_thresholds = (
                    [
                        threshold
                        for threshold in thresholds
                        if isinstance(threshold, dict)
                    ]
                    if isinstance(thresholds, list)
                    else []
                )

            sizes = sizes_by_nm.get(nm_id, [])
            if sizes:
                prices = [float(row.price) for row in sizes if row.price is not None]
                discounted = [
                    float(row.discounted_price)
                    for row in sizes
                    if row.discounted_price is not None
                ]
                club_discounted = [
                    float(row.club_discounted_price)
                    for row in sizes
                    if row.club_discounted_price is not None
                ]
                item.sizes_count = len(sizes)
                item.min_size_price = min(prices) if prices else None
                item.max_size_price = max(prices) if prices else None
                item.min_discounted_price = min(discounted) if discounted else None
                item.max_discounted_price = max(discounted) if discounted else None
                item.min_club_discounted_price = (
                    min(club_discounted) if club_discounted else None
                )
                item.max_club_discounted_price = (
                    max(club_discounted) if club_discounted else None
                )

            quarantine = quarantine_by_nm.get(nm_id)
            if quarantine is not None:
                payload = (
                    quarantine.payload if isinstance(quarantine.payload, dict) else {}
                )
                item.quarantine = True
                item.quarantine_new_price = self._payload_float(
                    payload, "newPrice", "new_price"
                )
                item.quarantine_old_price = self._payload_float(
                    payload, "oldPrice", "old_price"
                )
                item.quarantine_new_discount = self._payload_int(
                    payload, "newDiscount", "new_discount"
                )
                item.quarantine_old_discount = self._payload_int(
                    payload, "oldDiscount", "old_discount"
                )
                item.quarantine_price_diff = self._payload_float(
                    payload, "priceDiff", "price_diff"
                )

    async def _attach_wb_promotion_signals(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        items: list[PriceSafetyRow],
    ) -> None:
        nm_ids = sorted({int(item.nm_id) for item in items if item.nm_id is not None})
        if not nm_ids:
            return

        promotion_synced = (
            await session.execute(
                select(WBSyncCursor.id)
                .where(
                    WBSyncCursor.account_id == account_id,
                    WBSyncCursor.domain == "promotions",
                )
                .limit(1)
            )
        ).scalar_one_or_none() is not None
        if promotion_synced:
            for item in items:
                item.promotion_calendar_synced = True

        if not promotion_synced:
            return

        now = utcnow()
        promo_rows = (
            await session.execute(
                select(WBPromotionNomenclature, WBPromotionCalendar)
                .join(
                    WBPromotionCalendar,
                    and_(
                        WBPromotionCalendar.account_id
                        == WBPromotionNomenclature.account_id,
                        WBPromotionCalendar.promotion_id
                        == WBPromotionNomenclature.promotion_id,
                    ),
                )
                .where(
                    WBPromotionNomenclature.account_id == account_id,
                    WBPromotionNomenclature.nm_id.in_(nm_ids),
                    or_(
                        WBPromotionCalendar.end_at.is_(None),
                        WBPromotionCalendar.end_at >= now,
                    ),
                )
                .order_by(
                    WBPromotionNomenclature.nm_id.asc(),
                    WBPromotionNomenclature.in_action.desc(),
                    WBPromotionCalendar.start_at.asc().nullslast(),
                    WBPromotionCalendar.promotion_id.asc(),
                )
            )
        ).all()
        rows_by_nm: dict[
            int, list[tuple[WBPromotionNomenclature, WBPromotionCalendar]]
        ] = defaultdict(list)
        for nomenclature, promotion in promo_rows:
            rows_by_nm[int(nomenclature.nm_id)].append((nomenclature, promotion))

        for item in items:
            if item.nm_id is None:
                continue
            rows = rows_by_nm.get(int(item.nm_id), [])
            if not rows:
                continue
            in_action_rows = [
                (nomenclature, promotion)
                for nomenclature, promotion in rows
                if bool(nomenclature.in_action)
            ]
            active_rows = [
                (nomenclature, promotion)
                for nomenclature, promotion in in_action_rows
                if (promotion.start_at is None or promotion.start_at <= now)
                and (promotion.end_at is None or promotion.end_at >= now)
            ]
            available_rows = [
                (nomenclature, promotion)
                for nomenclature, promotion in rows
                if not bool(nomenclature.in_action)
            ]
            display_rows = active_rows or in_action_rows or available_rows
            names: list[str] = []
            for _nomenclature, promotion in display_rows:
                name = str(promotion.name or "").strip()
                if name and name not in names:
                    names.append(name)
            plan_prices = [
                float(nomenclature.plan_price)
                for nomenclature, _promotion in rows
                if nomenclature.plan_price is not None
            ]
            plan_discounts = [
                int(nomenclature.plan_discount)
                for nomenclature, _promotion in rows
                if nomenclature.plan_discount is not None
            ]
            item.promotion_active_count = len(active_rows)
            item.promotion_available_count = len(available_rows)
            item.promotion_names = names[:5]
            if display_rows:
                first_nomenclature, first_promotion = display_rows[0]
                item.promotion_nearest_name = first_promotion.name
                item.promotion_nearest_starts_at = first_promotion.start_at
                if not plan_prices and first_nomenclature.plan_price is not None:
                    plan_prices.append(float(first_nomenclature.plan_price))
                if not plan_discounts and first_nomenclature.plan_discount is not None:
                    plan_discounts.append(int(first_nomenclature.plan_discount))
            item.promotion_min_plan_price = min(plan_prices) if plan_prices else None
            item.promotion_max_plan_discount = (
                max(plan_discounts) if plan_discounts else None
            )
            self._attach_promotion_plan_risk(item)
            item.promotion_details = [
                self._promotion_detail_from_row(
                    item=item,
                    nomenclature=nomenclature,
                    promotion=promotion,
                    now=now,
                )
                for nomenclature, promotion in rows
            ]

    @classmethod
    def _promotion_detail_from_row(
        cls,
        *,
        item: PriceSafetyRow,
        nomenclature: WBPromotionNomenclature,
        promotion: WBPromotionCalendar,
        now,
    ) -> PriceSafetyPromotion:
        plan_safe_gap, plan_target_gap, plan_state = cls._promotion_plan_risk_values(
            item=item, plan_price=float(nomenclature.plan_price)
            if nomenclature.plan_price is not None
            else None
        )
        starts_at = promotion.start_at
        ends_at = promotion.end_at
        in_action = bool(nomenclature.in_action)
        if in_action and (starts_at is None or starts_at <= now) and (
            ends_at is None or ends_at >= now
        ):
            status = "active"
        elif in_action:
            status = "scheduled"
        else:
            status = "available"

        advantages = promotion.advantages if isinstance(promotion.advantages, list) else []
        return PriceSafetyPromotion(
            promotion_id=int(promotion.promotion_id),
            name=promotion.name,
            promo_type=promotion.promo_type,
            status=status,
            in_action=in_action,
            start_at=starts_at,
            end_at=ends_at,
            price=float(nomenclature.price) if nomenclature.price is not None else None,
            currency_code=nomenclature.currency_code,
            plan_price=float(nomenclature.plan_price)
            if nomenclature.plan_price is not None
            else None,
            discount=nomenclature.discount,
            plan_discount=nomenclature.plan_discount,
            plan_safe_gap=plan_safe_gap,
            plan_target_gap=plan_target_gap,
            plan_state=plan_state,
            participation_percentage=promotion.participation_percentage,
            in_promo_action_leftovers=promotion.in_promo_action_leftovers,
            in_promo_action_total=promotion.in_promo_action_total,
            not_in_promo_action_leftovers=promotion.not_in_promo_action_leftovers,
            not_in_promo_action_total=promotion.not_in_promo_action_total,
            exception_products_count=promotion.exception_products_count,
            advantages=[str(value) for value in advantages if value not in (None, "")],
            description=promotion.description,
        )

    @staticmethod
    def _attach_promotion_plan_risk(item: PriceSafetyRow) -> None:
        safe_gap, target_gap, state = ControlTowerService._promotion_plan_risk_values(
            item=item, plan_price=item.promotion_min_plan_price
        )
        item.promotion_plan_safe_gap = safe_gap
        item.promotion_plan_target_gap = target_gap
        item.promotion_plan_state = state

    @staticmethod
    def _promotion_plan_risk_values(
        *, item: PriceSafetyRow, plan_price: float | None
    ) -> tuple[float | None, float | None, str | None]:
        if plan_price is None:
            return None, None, None

        safe_gap = (
            float(plan_price) - float(item.break_even_price)
            if item.break_even_price is not None
            else None
        )
        target_gap = (
            float(plan_price) - float(item.target_margin_price)
            if item.target_margin_price is not None
            else None
        )

        if safe_gap is not None and safe_gap < 0:
            return safe_gap, target_gap, "below_break_even"
        if target_gap is not None and target_gap < 0:
            return safe_gap, target_gap, "below_target"
        if safe_gap is not None or target_gap is not None:
            return safe_gap, target_gap, "safe"
        return safe_gap, target_gap, "not_computable"

    async def _load_ads_source_by_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> tuple[dict[int, Decimal], Decimal]:
        cache_key = self._ads_source_cache_key(
            account_id=account_id, date_from=date_from, date_to=date_to
        )
        cached = self._ads_source_cache.get(cache_key)
        if cached is not None:
            cached_at, cached_by_nm, cached_total = cached
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.ADS_SOURCE_CACHE_TTL_SECONDS
            ):
                return dict(cached_by_nm), cached_total
        rows = (
            await session.execute(
                select(
                    WBAdStatsDaily.nm_id,
                    func.coalesce(func.sum(WBAdStatsDaily.sum), 0),
                )
                .where(
                    WBAdStatsDaily.account_id == account_id,
                    WBAdStatsDaily.stat_date >= date_from,
                    WBAdStatsDaily.stat_date <= date_to,
                )
                .group_by(WBAdStatsDaily.nm_id)
            )
        ).all()
        by_nm: dict[int, Decimal] = {}
        total = Decimal("0")
        for nm_id, amount in rows:
            decimal_amount = self._decimal(amount)
            total += decimal_amount
            if nm_id is not None:
                by_nm[int(nm_id)] = by_nm.get(int(nm_id), Decimal("0")) + decimal_amount
        self._ads_source_cache[cache_key] = (utcnow(), dict(by_nm), total)
        return by_nm, total

    @classmethod
    def _allocate_source_ads_by_sku(
        cls,
        *,
        rows: list[Any],
        ads_source_by_nm: dict[int, Decimal],
    ) -> dict[int, Decimal]:
        """Allocate WB ad source spend from nm_id level to SKU/size rows.

        WB ad stats usually arrive by nm_id/article. Business UI, purchase plan and
        SKU detail still need a per-SKU number. We allocate source spend inside the
        backend by revenue share first, then by sold units, then evenly as the last
        fallback. This prevents the old bug where the full nm_id ad spend was shown
        on every size/SKU row.
        """
        if not rows or not ads_source_by_nm:
            return {}

        revenue_by_nm: dict[int, Decimal] = defaultdict(Decimal)
        units_by_nm: dict[int, Decimal] = defaultdict(Decimal)
        count_by_nm: dict[int, int] = defaultdict(int)

        for row in rows:
            if (
                getattr(row, "sku_id", None) is None
                or getattr(row, "nm_id", None) is None
            ):
                continue
            nm_id = int(row.nm_id)
            count_by_nm[nm_id] += 1
            revenue = cls._decimal(getattr(row, "realized_revenue", None))
            units = Decimal(
                str(
                    max(
                        int(
                            getattr(row, "net_units", 0)
                            or getattr(row, "gross_units", 0)
                            or 0
                        ),
                        0,
                    )
                )
            )
            if revenue > 0:
                revenue_by_nm[nm_id] += revenue
            if units > 0:
                units_by_nm[nm_id] += units

        allocated: dict[int, Decimal] = {}
        for row in rows:
            if (
                getattr(row, "sku_id", None) is None
                or getattr(row, "nm_id", None) is None
            ):
                continue
            sku_id = int(row.sku_id)
            nm_id = int(row.nm_id)
            source_spend = ads_source_by_nm.get(nm_id, Decimal("0"))
            if source_spend <= 0:
                allocated[sku_id] = Decimal("0")
                continue
            revenue_total = revenue_by_nm.get(nm_id, Decimal("0"))
            if revenue_total > 0:
                share_base = cls._decimal(getattr(row, "realized_revenue", None))
                allocated[sku_id] = (
                    source_spend * share_base / revenue_total
                    if share_base > 0
                    else Decimal("0")
                )
                continue
            units_total = units_by_nm.get(nm_id, Decimal("0"))
            if units_total > 0:
                units = Decimal(
                    str(
                        max(
                            int(
                                getattr(row, "net_units", 0)
                                or getattr(row, "gross_units", 0)
                                or 0
                            ),
                            0,
                        )
                    )
                )
                allocated[sku_id] = (
                    source_spend * units / units_total if units > 0 else Decimal("0")
                )
                continue
            allocated[sku_id] = source_spend / Decimal(
                str(max(count_by_nm.get(nm_id, 1), 1))
            )
        return allocated

    @staticmethod
    def _ads_efficiency_allocation_status_label(status: str | None) -> str:
        mapping = {
            "matched": "Привязано",
            "partial": "Частично распределено",
            "overallocated": "Есть превышение разноса",
            "no_source_data": "Нет источника рекламы",
        }
        return mapping.get(str(status or "").strip().lower(), "Неизвестно")

    @staticmethod
    def _ads_efficiency_action_label(
        *,
        action_hint: str | None,
        trust_state: str | None,
        blocked_reasons: list[str] | None,
    ) -> str:
        reasons = set(blocked_reasons or [])
        if (
            str(trust_state or "").strip().lower() == TRUST_STATE_DATA_BLOCKED
            or reasons
        ):
            return "Сначала исправить данные"
        mapping = {
            "AD_ALLOCATION_REVIEW": "Проверить разнос рекламы",
            "AD_PAUSE_REVIEW": "Проверить / остановить рекламу",
            "AD_SCALE_REVIEW": "Можно масштабировать",
        }
        return mapping.get(str(action_hint or "").strip().upper(), "Наблюдать")

    @classmethod
    def _ads_efficiency_row_weights(cls, rows: list[Any]) -> list[Decimal]:
        spend_weights = [
            max(cls._decimal(getattr(row, "ad_spend", None)), Decimal("0"))
            for row in rows
        ]
        total_spend = sum(spend_weights, start=Decimal("0"))
        if total_spend > 0:
            return [value / total_spend for value in spend_weights]
        revenue_weights = [
            max(cls._decimal(getattr(row, "revenue", None)), Decimal("0"))
            for row in rows
        ]
        total_revenue = sum(revenue_weights, start=Decimal("0"))
        if total_revenue > 0:
            return [value / total_revenue for value in revenue_weights]
        row_count = max(len(rows), 1)
        return [Decimal("1") / Decimal(str(row_count)) for _ in rows]

    @staticmethod
    def _allocate_integer_total_by_weights(
        total: int | None, weights: list[Decimal]
    ) -> list[int]:
        normalized_total = max(int(total or 0), 0)
        if normalized_total <= 0 or not weights:
            return [0 for _ in weights]
        raw_allocations = [
            Decimal(str(normalized_total)) * weight for weight in weights
        ]
        allocated = [
            int(value.to_integral_value(rounding=ROUND_FLOOR))
            for value in raw_allocations
        ]
        remainder = normalized_total - sum(allocated)
        if remainder <= 0:
            return allocated
        ranked_indexes = sorted(
            range(len(weights)),
            key=lambda index: (
                raw_allocations[index] - Decimal(str(allocated[index])),
                weights[index],
                -index,
            ),
            reverse=True,
        )
        for index in ranked_indexes[:remainder]:
            allocated[index] += 1
        return allocated

    async def _load_ads_efficiency_stats_by_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        campaign_id: int | None = None,
    ) -> dict[int, dict[str, Any]]:
        if not hasattr(session, "execute"):
            return {}
        query = select(WBAdStatsDaily).where(
            WBAdStatsDaily.account_id == account_id,
            WBAdStatsDaily.nm_id.is_not(None),
            WBAdStatsDaily.stat_date >= date_from,
            WBAdStatsDaily.stat_date <= date_to,
        )
        if campaign_id is not None:
            query = query.where(WBAdStatsDaily.advert_id == campaign_id)
        rows = list((await session.execute(query)).scalars())
        if not rows:
            return {}
        advert_ids = {int(row.advert_id) for row in rows if row.advert_id is not None}
        campaign_names: dict[int, str | None] = {}
        if advert_ids:
            campaign_rows = (
                await session.execute(
                    select(WBAdCampaign.advert_id, WBAdCampaign.name).where(
                        WBAdCampaign.account_id == account_id,
                        WBAdCampaign.advert_id.in_(advert_ids),
                    )
                )
            ).all()
            campaign_names = {
                int(advert_id): name
                for advert_id, name in campaign_rows
                if advert_id is not None
            }
        by_nm: dict[int, dict[str, Any]] = {}
        for row in rows:
            if row.nm_id is None:
                continue
            nm_id = int(row.nm_id)
            payload = by_nm.setdefault(
                nm_id,
                {
                    "stats_rows_count": 0,
                    "views": 0,
                    "clicks": 0,
                    "orders": 0,
                    "atbs": 0,
                    "shks": 0,
                    "canceled": 0,
                    "source_ad_spend": Decimal("0"),
                    "source_revenue": Decimal("0"),
                    "advert_ids": set(),
                },
            )
            payload["stats_rows_count"] += 1
            payload["views"] += int(row.views or 0)
            payload["clicks"] += int(row.clicks or 0)
            payload["orders"] += int(row.orders or 0)
            payload["atbs"] += int(row.atbs or 0)
            payload["shks"] += int(row.shks or 0)
            payload["canceled"] += int(row.canceled or 0)
            payload["source_ad_spend"] += self._decimal(row.sum)
            payload["source_revenue"] += self._decimal(row.sum_price)
            if row.advert_id is not None:
                payload["advert_ids"].add(int(row.advert_id))
        for payload in by_nm.values():
            distinct_advert_ids = sorted(payload.pop("advert_ids"))
            payload["advert_ids"] = distinct_advert_ids
            payload["campaign_count"] = len(distinct_advert_ids)
            if campaign_id is not None:
                payload["advert_id"] = campaign_id
                payload["campaign_name"] = campaign_names.get(campaign_id)
            elif len(distinct_advert_ids) == 1:
                payload["advert_id"] = distinct_advert_ids[0]
                payload["campaign_name"] = campaign_names.get(distinct_advert_ids[0])
            else:
                payload["advert_id"] = None
                payload["campaign_name"] = (
                    f"{len(distinct_advert_ids)} кампаний"
                    if distinct_advert_ids
                    else None
                )
            payload["ctr_percent"] = (
                self._percent0(payload["clicks"], payload["views"])
                if payload["views"] > 0
                else None
            )
            payload["cpc"] = (
                self._float(
                    payload["source_ad_spend"] / Decimal(str(payload["clicks"]))
                )
                if payload["clicks"] > 0 and payload["source_ad_spend"] > 0
                else None
            )
            payload["cr_percent"] = (
                self._percent0(payload["orders"], payload["clicks"])
                if payload["clicks"] > 0
                else None
            )
        return by_nm

    @classmethod
    def _ads_efficiency_summary(
        cls, items: list[AdsEfficiencyRow]
    ) -> AdsEfficiencySummary:
        summary = AdsEfficiencySummary(total_count=len(items))
        source_ad_spend = sum(
            (cls._decimal(item.source_ad_spend) for item in items), start=Decimal("0")
        )
        allocated_ad_spend = sum(
            (cls._decimal(item.ad_spend) for item in items), start=Decimal("0")
        )
        overallocated_ad_spend = sum(
            (cls._decimal(item.overallocated_ad_spend) for item in items),
            start=Decimal("0"),
        )
        unallocated_ad_spend = sum(
            (cls._decimal(item.unallocated_ad_spend) for item in items),
            start=Decimal("0"),
        )
        source_revenue_total = sum(
            (cls._decimal(item.source_revenue) for item in items), start=Decimal("0")
        )
        business_revenue_total = sum(
            (
                cls._decimal(item.revenue)
                for item in items
                if item.revenue is not None and item.revenue > 0
            ),
            start=Decimal("0"),
        )
        summary.source_ad_spend = cls._float0(source_ad_spend)
        summary.allocated_ad_spend = cls._float0(allocated_ad_spend)
        summary.overallocated_ad_spend = cls._float0(overallocated_ad_spend)
        summary.unallocated_ad_spend = cls._float0(unallocated_ad_spend)
        summary.source_revenue = cls._float0(source_revenue_total)
        summary.drr_percent = (
            cls._percent0(source_ad_spend, source_revenue_total)
            if source_revenue_total > 0
            else cls._percent0(allocated_ad_spend, business_revenue_total)
            if business_revenue_total > 0
            else 0.0
        )
        summary.profit_after_ads = sum(
            ((item.net_profit or 0.0) for item in items), start=0.0
        )
        summary.views = sum((item.views for item in items), start=0)
        summary.clicks = sum((item.clicks for item in items), start=0)
        summary.orders = sum((item.orders for item in items), start=0)
        summary.atbs = sum((item.atbs for item in items), start=0)
        summary.shks = sum((item.shks for item in items), start=0)
        summary.canceled = sum((item.canceled for item in items), start=0)
        summary.ctr_percent = (
            cls._percent0(summary.clicks, summary.views) if summary.views > 0 else None
        )
        summary.cr_percent = (
            cls._percent0(summary.orders, summary.clicks)
            if summary.clicks > 0
            else None
        )
        summary.cpc = (
            cls._float(source_ad_spend / Decimal(str(summary.clicks)))
            if summary.clicks > 0 and source_ad_spend > 0
            else None
        )
        if overallocated_ad_spend > 0:
            summary.ads_allocation_status = "overallocated"
        elif unallocated_ad_spend > 0:
            summary.ads_allocation_status = "partial"
        elif source_ad_spend > 0:
            summary.ads_allocation_status = "matched"
        else:
            summary.ads_allocation_status = "no_source_data"
        summary.ads_allocation_status_label = (
            cls._ads_efficiency_allocation_status_label(summary.ads_allocation_status)
        )
        for item in items:
            status = str(item.ads_allocation_status or "").strip().lower()
            if status == "matched":
                summary.matched_count += 1
            elif status == "partial":
                summary.partial_count += 1
            elif status == "overallocated":
                summary.overallocated_count += 1
            else:
                summary.no_source_count += 1
            if (item.drr_percent or 0) > 25:
                summary.high_drr_count += 1
            if (item.net_profit or 0) < 0:
                summary.negative_profit_count += 1
            if str(item.confidence or "").strip().lower() == "low":
                summary.low_confidence_count += 1
            action_hint = str(item.action_hint or "").strip().upper()
            if item.action_label == "Сначала исправить данные":
                summary.data_fix_first_count += 1
            elif action_hint == "AD_PAUSE_REVIEW":
                summary.pause_review_count += 1
            elif action_hint == "AD_SCALE_REVIEW":
                summary.scale_candidate_count += 1
        return summary

    @classmethod
    def _ads_allocation_metrics(
        cls,
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

    @classmethod
    def _merge_settings(cls, stored: dict | None) -> dict:
        merged = dict(cls.DEFAULT_SETTINGS)
        if stored:
            for key, value in stored.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**merged[key], **value}
                else:
                    merged[key] = value
        return merged

    @staticmethod
    def _is_missing_relation_error(exc: ProgrammingError, *table_names: str) -> bool:
        message = str(exc).lower()
        return "does not exist" in message and any(
            table_name.lower() in message for table_name in table_names
        )

    @classmethod
    def _raise_storage_not_ready(cls) -> None:
        raise HTTPException(status_code=503, detail=cls.STORAGE_NOT_READY_DETAIL)

    @staticmethod
    def _short_reason(text: str | None, *, max_len: int = 96) -> str:
        normalized = " ".join(str(text or "").split())
        if len(normalized) <= max_len:
            return normalized
        return normalized[: max_len - 1].rstrip() + "…"

    @staticmethod
    def list_sku_statuses() -> dict[str, str]:
        return get_enum_mapping("sku_status")

    @staticmethod
    def _action_business_copy(
        *,
        action_type: str,
        reason: str,
        blocked_reasons: list[str],
        payload: dict[str, Any] | None,
        vendor_code: str | None,
        nm_id: int | None,
        sku_id: int | None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        linked_entity = {
            "sku_id": sku_id,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
        }
        playbook: dict[str, dict[str, Any]] = {
            "DATA_FIX_REQUIRED": {
                "what_to_do": "Закройте соответствующие блокеры данных и затем повторно запустите аналитические таблицы и проверку качества данных.",
                "why": "С текущими данными принимать окончательное бизнес-решение рискованно.",
                "how_to_fix": [
                    "Определите блокирующую причину",
                    "Исправьте проблему с привязкой данных, себестоимостью или загрузкой",
                    "Пересчитайте аналитические таблицы",
                    "Запустите DQ-проверку",
                ],
            },
            "FIX_COST_TRUST": {
                "what_to_do": "Загрузите и подтвердите реальную себестоимость поставщика.",
                "why": "Без подтвержденной реальной себестоимости прибыль, окупаемость и закупочные рекомендации не считаются окончательными.",
                "how_to_fix": [
                    "Скачайте шаблон себестоимости",
                    "Заполните реальные себестоимости",
                    "Загрузите файл и подтвердите импорт",
                    "Пересчитайте аналитические таблицы",
                ],
            },
            "MAP_UNMATCHED_SKU": {
                "what_to_do": "Свяжите несопоставленные SKU с нужной карточкой или классифицируйте их.",
                "why": "Если маппинг не закрыт, финансы, остатки и себестоимость будут связаны с карточками неверно.",
                "how_to_fix": [
                    "Откройте разбор проблем качества данных",
                    "Проверьте кандидатов на привязку",
                    "Свяжите SKU или отметьте причину исключения",
                    "Запустите проверку качества данных",
                ],
            },
            "FIX_STOCK_SYNC": {
                "what_to_do": "Доведите загрузку остатков до завершенного состояния и получите новый снимок остатков.",
                "why": "Если остатки и стоимость склада неверны, закупочное решение тоже будет ошибочным.",
                "how_to_fix": [
                    "Проверьте историю синхронизаций и курсоры",
                    "Повторно запустите загрузку остатков",
                    "Дождитесь завершенного снимка",
                ],
            },
            "FIX_AD_ALLOCATION": {
                "what_to_do": "Полностью привяжите рекламные расходы к слою прибыльности по SKU.",
                "why": "Если расходы на рекламу не попадают в расчет прибыли, карточка выглядит искусственно лучше.",
                "how_to_fix": [
                    "Сравните исходные рекламные расходы и расчеты по карточкам",
                    "Проверьте привязку по артикулу",
                    "Пересчитайте распределение рекламных расходов",
                ],
            },
            "FIX_PRICE_MAPPING": {
                "what_to_do": "Сопоставьте фактическую цену карточки или заполните данные о цене по размерам.",
                "why": "Если цена не найдена, безопасная цена и защита маржи не рассчитываются.",
                "how_to_fix": [
                    "Проверьте ценовые поля карточки",
                    "Подтвердите привязку цен WB по размерам",
                    "Проверьте цены внутри данных по размерам",
                ],
            },
            "RECONCILE_FINANCE": {
                "what_to_do": "Закройте расхождения между финансовым отчетом WB, продажами и расчетной выручкой.",
                "why": "Если отчет WB не совпадает с продажами, прибыль и следующие действия будут вводить в заблуждение.",
                "how_to_fix": [
                    "Откройте аудит артикула",
                    "Сравните выручку из отчета WB и продажи",
                    "Классифицируйте причину расхождения",
                ],
            },
            "RECONCILIATION_REVIEW": {
                "what_to_do": "Сравните финансовый отчет WB, продажи и расчетную выручку на уровне исходных строк.",
                "why": "Пока сверка не закрыта, прибыль и действия могут быть неверными.",
                "how_to_fix": [
                    "Откройте проблемный SKU или артикул",
                    "Сравните строки финансового отчета и строки продаж",
                    "Классифицируйте причину расхождения",
                ],
            },
            "REORDER": {
                "what_to_do": "Подготовьте дозаказ до того, как товар закончится.",
                "why": "У прибыльной карточки запас подходит к минимальному уровню на время новой поставки.",
                "how_to_fix": [
                    "Проверьте рекомендованное количество",
                    "Подтвердите бюджет и план поставщика",
                    "Разместите закупку",
                ],
            },
            "PROTECT_STOCK": {
                "what_to_do": "Защитите остаток и не усиливайте спрос, пока не придет товар в пути.",
                "why": "Риск, что товар закончится, высокий, но товар в пути уже должен закрыть ближайший спрос.",
                "how_to_fix": [
                    "Проверьте дату прихода товара",
                    "Не запускайте агрессивные промо",
                    "После прихода пересчитайте решение по закупке",
                ],
            },
            "DO_NOT_REORDER": {
                "what_to_do": "Остановите повторную закупку и пересмотрите экономику SKU.",
                "why": "В текущем периоде SKU показывает убыток или прибыль около нуля.",
                "how_to_fix": [
                    "Проверьте цену и рекламные расходы",
                    "Проверьте себестоимость и уровень возвратов",
                    "После этого обновите решение по повторной закупке",
                ],
            },
            "LIQUIDATE_STOCK": {
                "what_to_do": "Подготовьте распродажу или промо, чтобы разгрузить замороженный остаток.",
                "why": "Остаток слишком глубокий относительно спроса.",
                "how_to_fix": [
                    "Выберите канал ликвидации",
                    "Обновите ценовую и промо-стратегию",
                    "Временно остановите новую закупку",
                ],
            },
            "PRICE_INCREASE_REVIEW": {
                "what_to_do": "Перепроверьте цену относительно минимальной цены без убытка и целевой маржи.",
                "why": "Текущая цена может быть слишком низкой для защиты прибыли.",
                "how_to_fix": [
                    "Подтвердите текущую цену со скидкой",
                    "Сравните с минимальной ценой без убытка",
                    "При необходимости обновите цену",
                ],
            },
            "AD_PAUSE_REVIEW": {
                "what_to_do": "Временно ограничьте рекламные расходы и проверьте экономику кампании.",
                "why": "Реклама включена, но чистая прибыль не положительная.",
                "how_to_fix": [
                    "Проверьте долю рекламы в выручке и саму выручку",
                    "Поставьте на паузу убыточные кампании",
                    "Перенастройте таргетинг и ставки",
                ],
            },
            "CARD_CONTENT_REVIEW": {
                "what_to_do": "Проверьте контент карточки, фото и факторы, влияющие на конверсию.",
                "why": "Трафик есть, но конверсия или качество выкупа могут быть низкими.",
                "how_to_fix": [
                    "Проверьте, сколько людей открывают карточку, кладут в корзину и доходят до заказа",
                    "Обновите контент и фотографии",
                    "Проверьте отзывы и проблемы с размерами",
                ],
            },
        }
        copy = playbook.get(
            action_type,
            {
                "what_to_do": "Откройте действие и проверьте проблему на уровне исходных данных.",
                "why": reason or "Это действие требует внимания.",
                "how_to_fix": ["Проверьте payload действия и исходные строки"],
            },
        )
        if action_type == "DATA_FIX_REQUIRED" and blocked_reasons:
            copy["why"] = f"Блокирующие причины: {', '.join(blocked_reasons)}."
        copy["linked_entity"] = linked_entity
        copy["deadline_hint"] = payload.get("deadlineHint")
        copy["required_cash"] = payload.get("requiredCash")
        copy["money_effect"] = dict(payload.get("moneyEffect") or {})
        return copy

    @staticmethod
    def _action_category(action_type: str) -> str:
        if action_type in {
            "FIX_COST_TRUST",
            "MAP_UNMATCHED_SKU",
            "FIX_STOCK_SYNC",
            "FIX_AD_ALLOCATION",
            "FIX_PRICE_MAPPING",
            "DATA_FIX_REQUIRED",
        }:
            return "data_fix"
        if action_type in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}:
            return "finance_reconcile"
        if action_type in {"LIQUIDATE_STOCK"}:
            return "release_cash"
        if action_type in {"PROTECT_STOCK"}:
            return "protect_revenue"
        if action_type in {"REORDER", "CARD_CONTENT_REVIEW"}:
            return "growth"
        if action_type in {
            "DO_NOT_REORDER",
            "AD_PAUSE_REVIEW",
            "PRICE_INCREASE_REVIEW",
        }:
            return "save_money"
        return "data_fix" if action_type.startswith("FIX_") else "watch"

    @staticmethod
    def _action_source_endpoint(
        *, action_type: str, linked_entity: dict[str, Any] | None
    ) -> str:
        entity = dict(linked_entity or {})
        nm_id = entity.get("nm_id")
        sku_id = entity.get("sku_id")
        if nm_id:
            return f"/money/articles/{int(nm_id)}"
        if sku_id:
            return f"/money/cards/{int(sku_id)}"
        if action_type in {"RECONCILE_FINANCE", "RECONCILIATION_REVIEW"}:
            return "/money/summary"
        return "/money/data-blockers"

    @staticmethod
    def _sort_control_rows(
        items: list[ControlTowerSkuRow],
        *,
        sort_by: str | None,
        sort_dir: str,
    ) -> list[ControlTowerSkuRow]:
        if not sort_by:
            return sorted(items, key=lambda item: item.priority_score, reverse=True)
        reverse = sort_dir != "asc"
        attr_map = {
            "revenue": "revenue",
            "net_profit": "net_profit",
            "margin_percent": "margin_percent",
            "priority_score": "priority_score",
            "stock_qty": "stock_qty",
            "days_of_stock": "days_of_stock",
            "ad_spend": "ad_spend",
            "drr_percent": "drr_percent",
        }
        attr_name = attr_map.get(sort_by)
        if attr_name is None:
            return sorted(items, key=lambda item: item.priority_score, reverse=True)
        return sorted(
            items,
            key=lambda item: (
                getattr(item, attr_name)
                if getattr(item, attr_name) is not None
                else float("-inf" if reverse else "inf")
            ),
            reverse=reverse,
        )

    async def get_business_settings(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> BusinessSettingsRead:
        try:
            row = (
                await session.execute(
                    select(UserBusinessSetting).where(
                        UserBusinessSetting.account_id == account_id
                    )
                )
            ).scalar_one_or_none()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "user_business_settings"):
                row = None
            else:
                raise
        return BusinessSettingsRead(
            account_id=account_id,
            settings=self._merge_settings(
                row.settings_json if row is not None else None
            ),
            updated_at=row.updated_at if row is not None else None,
            comment=row.comment if row is not None else None,
        )

    def get_business_policies(self) -> BusinessPoliciesRead:
        return BusinessPoliciesRead(
            cost_trust_policy=[
                BusinessPolicyOption(**item) for item in self.COST_TRUST_POLICIES
            ]
        )

    async def update_business_settings(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        user_id: int | None,
        payload: BusinessSettingsUpdateRequest,
    ) -> BusinessSettingsRead:
        try:
            row = (
                await session.execute(
                    select(UserBusinessSetting).where(
                        UserBusinessSetting.account_id == account_id
                    )
                )
            ).scalar_one_or_none()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(
                exc, "user_business_settings", "user_business_settings_audit"
            ):
                self._raise_storage_not_ready()
            raise
        previous = row.settings_json if row is not None else {}
        merged = self._merge_settings(payload.settings)
        if row is None:
            row = UserBusinessSetting(
                account_id=account_id,
                updated_by_user_id=user_id,
                settings_json=merged,
                comment=payload.comment,
            )
            session.add(row)
        else:
            row.updated_by_user_id = user_id
            row.settings_json = merged
            row.comment = payload.comment
        session.add(
            UserBusinessSettingAudit(
                account_id=account_id,
                changed_by_user_id=user_id,
                previous_settings_json=previous or {},
                next_settings_json=merged,
                comment=payload.comment,
            )
        )
        try:
            await session.flush()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(
                exc, "user_business_settings", "user_business_settings_audit"
            ):
                self._raise_storage_not_ready()
            raise
        return BusinessSettingsRead(
            account_id=account_id,
            settings=merged,
            updated_at=row.updated_at,
            comment=row.comment,
        )

    async def _load_profit_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ):
        return await self.dashboard.sku_profitability(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )

    async def _load_latest_stock_by_sku(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[int, AggregatedLatestStock]:
        base_filters = [
            MartStockDaily.account_id == account_id,
            MartStockDaily.stat_date >= date_from,
            MartStockDaily.stat_date <= date_to,
            MartStockDaily.sku_id.is_not(None),
        ]
        quantity_present = or_(
            MartStockDaily.quantity.is_not(None),
            MartStockDaily.quantity_full.is_not(None),
        )
        latest_any_date = (
            select(
                MartStockDaily.sku_id.label("sku_id"),
                func.max(MartStockDaily.stat_date).label("latest_stat_date"),
            )
            .where(*base_filters)
            .group_by(MartStockDaily.sku_id)
            .subquery()
        )
        latest_quantity_date = (
            select(
                MartStockDaily.sku_id.label("sku_id"),
                func.max(MartStockDaily.stat_date).label("latest_quantity_date"),
            )
            .where(*base_filters, quantity_present)
            .group_by(MartStockDaily.sku_id)
            .subquery()
        )
        rows = (
            await session.execute(
                select(
                    MartStockDaily.sku_id,
                    MartStockDaily.stat_date,
                    MartStockDaily.warehouse_name,
                    MartStockDaily.quantity,
                    MartStockDaily.quantity_full,
                    MartStockDaily.in_way_to_client,
                    MartStockDaily.in_way_from_client,
                    MartStockDaily.avg_sales_per_day_30d,
                    MartStockDaily.sales_7d,
                    MartStockDaily.sales_14d,
                    MartStockDaily.sales_30d,
                    MartStockDaily.days_since_last_sale,
                    MartStockDaily.turnover_rate,
                )
                .select_from(MartStockDaily)
                .join(
                    latest_any_date,
                    latest_any_date.c.sku_id == MartStockDaily.sku_id,
                )
                .outerjoin(
                    latest_quantity_date,
                    latest_quantity_date.c.sku_id == MartStockDaily.sku_id,
                )
                .where(
                    *base_filters,
                    or_(
                        MartStockDaily.stat_date == latest_any_date.c.latest_stat_date,
                        and_(
                            latest_quantity_date.c.latest_quantity_date.is_not(None),
                            MartStockDaily.stat_date
                            == latest_quantity_date.c.latest_quantity_date,
                        ),
                    ),
                )
            )
        ).all()
        grouped: dict[int, list[Any]] = defaultdict(list)
        for row in rows:
            sku_id = getattr(row, "sku_id", None)
            if sku_id is None:
                continue
            grouped[int(sku_id)].append(
                SimpleNamespace(
                    stat_date=row.stat_date,
                    warehouse_name=row.warehouse_name,
                    quantity=row.quantity,
                    quantity_full=row.quantity_full,
                    in_way_to_client=row.in_way_to_client,
                    in_way_from_client=row.in_way_from_client,
                    avg_sales_per_day_30d=row.avg_sales_per_day_30d,
                    sales_7d=row.sales_7d,
                    sales_14d=row.sales_14d,
                    sales_30d=row.sales_30d,
                    days_since_last_sale=row.days_since_last_sale,
                    turnover_rate=row.turnover_rate,
                )
            )
        latest: dict[int, AggregatedLatestStock] = {}
        for sku_id, sku_rows in grouped.items():
            latest[sku_id] = self._aggregate_latest_stock_rows(sku_rows)
        return latest

    async def _load_latest_stock_detail_rows_by_sku(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        sku_ids: list[int],
    ) -> dict[int, list[MartStockDaily]]:
        if not sku_ids:
            return {}
        unique_sku_ids = list(dict.fromkeys(int(sku_id) for sku_id in sku_ids))
        latest_dates = (
            select(
                MartStockDaily.sku_id.label("sku_id"),
                func.max(MartStockDaily.stat_date).label("stat_date"),
            )
            .where(
                MartStockDaily.account_id == account_id,
                MartStockDaily.stat_date >= date_from,
                MartStockDaily.stat_date <= date_to,
                MartStockDaily.sku_id.in_(unique_sku_ids),
            )
            .group_by(MartStockDaily.sku_id)
            .subquery()
        )
        rows = list(
            (
                await session.execute(
                    select(MartStockDaily)
                    .join(
                        latest_dates,
                        and_(
                            MartStockDaily.sku_id == latest_dates.c.sku_id,
                            MartStockDaily.stat_date == latest_dates.c.stat_date,
                        ),
                    )
                    .where(
                        MartStockDaily.account_id == account_id,
                        MartStockDaily.sku_id.in_(unique_sku_ids),
                    )
                )
            ).scalars()
        )
        result: dict[int, list[MartStockDaily]] = defaultdict(list)
        for row in rows:
            if row.sku_id is None:
                continue
            result[int(row.sku_id)].append(row)
        return dict(result)

    async def _load_product_cards_by_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_ids: list[int],
    ) -> dict[int, WBProductCard]:
        if not nm_ids:
            return {}
        rows = list(
            (
                await session.execute(
                    select(WBProductCard).where(
                        WBProductCard.account_id == account_id,
                        WBProductCard.nm_id.in_(list(dict.fromkeys(nm_ids))),
                    )
                )
            ).scalars()
        )
        return {int(row.nm_id): row for row in rows if row.nm_id is not None}

    def _stock_detail_payload(
        self,
        *,
        row: MartStockDaily,
        core_sku: CoreSKU | None,
    ) -> dict[str, Any]:
        payload = row.payload if isinstance(row.payload, dict) else {}
        quantity = self._optional_decimal(row.quantity_full)
        if quantity is None:
            quantity = self._optional_decimal(row.quantity)
        in_way_to_client = self._optional_decimal(row.in_way_to_client) or Decimal("0")
        in_way_from_client = self._optional_decimal(row.in_way_from_client) or Decimal(
            "0"
        )
        region_name = self._payload_first_text(
            payload,
            "regionName",
            "region_name",
            "region",
            "shippingRegion",
            "shipping_region",
            "oblastName",
            "oblast",
        )
        office_name = self._payload_first_text(
            payload, "officeName", "office_name", "office"
        )
        return {
            "sku_id": row.sku_id,
            "nm_id": row.nm_id,
            "barcode": row.barcode
            or (core_sku.barcode if core_sku is not None else None),
            "tech_size": core_sku.tech_size if core_sku is not None else None,
            "warehouse_id": row.warehouse_id,
            "warehouse_name": row.warehouse_name,
            "region_name": region_name or row.warehouse_name or "Без региона",
            "office_name": office_name,
            "quantity": self._float0(quantity),
            "quantity_full": self._float0(row.quantity_full),
            "in_way_to_client": self._float0(in_way_to_client),
            "in_way_from_client": self._float0(in_way_from_client),
            "in_transit_qty": self._float0(in_way_to_client + in_way_from_client),
            "sales_7d": self._int0(row.sales_7d),
            "sales_14d": self._int0(row.sales_14d),
            "sales_30d": self._int0(row.sales_30d),
            "days_of_stock": self._float(row.days_of_stock),
            "days_since_last_sale": row.days_since_last_sale,
        }

    def _region_breakdown_from_stock_details(
        self, details: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        buckets: dict[str, dict[str, Any]] = {}
        for item in details:
            region = str(
                item.get("region_name") or item.get("warehouse_name") or "Без региона"
            )
            bucket = buckets.setdefault(
                region,
                {
                    "region_name": region,
                    "quantity": 0.0,
                    "in_transit_qty": 0.0,
                    "sales_30d": 0,
                    "warehouses": [],
                },
            )
            bucket["quantity"] += float(item.get("quantity") or 0)
            bucket["in_transit_qty"] += float(item.get("in_transit_qty") or 0)
            bucket["sales_30d"] = max(
                int(bucket.get("sales_30d") or 0), int(item.get("sales_30d") or 0)
            )
            bucket["warehouses"].append(item)
        return sorted(
            buckets.values(),
            key=lambda item: (
                float(item.get("quantity") or 0),
                int(item.get("sales_30d") or 0),
            ),
            reverse=True,
        )

    def _aggregate_latest_stock_rows(
        self, rows: list[MartStockDaily]
    ) -> AggregatedLatestStock:
        snapshot = latest_stock_snapshot(rows)
        if snapshot is None:
            raise ValueError("Cannot aggregate empty stock rows")
        sales_7d = max(
            (self._int0(getattr(row, "sales_7d", 0)) for row in rows), default=0
        )
        sales_14d = max(
            (self._int0(getattr(row, "sales_14d", 0)) for row in rows), default=0
        )
        sales_30d = max(
            (self._int0(getattr(row, "sales_30d", 0)) for row in rows), default=0
        )
        days_since_candidates = [
            self._int0(getattr(row, "days_since_last_sale", 0))
            for row in rows
            if getattr(row, "days_since_last_sale", None) is not None
        ]
        turnover_candidates = [
            self._optional_decimal(getattr(row, "turnover_rate", None))
            for row in rows
            if self._optional_decimal(getattr(row, "turnover_rate", None)) is not None
        ]
        return AggregatedLatestStock(
            stat_date=snapshot.stat_date,
            quantity=snapshot.quantity,
            quantity_full=snapshot.quantity_full,
            in_way_to_client=snapshot.in_way_to_client,
            in_way_from_client=snapshot.in_way_from_client,
            avg_sales_per_day_30d=snapshot.avg_sales_per_day_30d,
            days_of_stock=snapshot.days_of_stock,
            sales_7d=sales_7d,
            sales_14d=sales_14d,
            sales_30d=sales_30d,
            days_since_last_sale=min(days_since_candidates)
            if days_since_candidates
            else None,
            turnover_rate=max(turnover_candidates, default=None),
        )

    async def _load_latest_sku_daily_by_sku(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[int, MartSKUDaily]:
        latest_dates = (
            select(
                MartSKUDaily.sku_id.label("sku_id"),
                func.max(MartSKUDaily.stat_date).label("stat_date"),
            )
            .where(
                MartSKUDaily.account_id == account_id,
                MartSKUDaily.stat_date >= date_from,
                MartSKUDaily.stat_date <= date_to,
                MartSKUDaily.sku_id.is_not(None),
            )
            .group_by(MartSKUDaily.sku_id)
            .subquery()
        )
        rows = list(
            (
                await session.execute(
                    select(MartSKUDaily)
                    .join(
                        latest_dates,
                        and_(
                            MartSKUDaily.sku_id == latest_dates.c.sku_id,
                            MartSKUDaily.stat_date == latest_dates.c.stat_date,
                        ),
                    )
                    .where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.sku_id.is_not(None),
                    )
                )
            ).scalars()
        )
        latest: dict[int, MartSKUDaily] = {}
        for row in rows:
            if row.sku_id is None:
                continue
            current = latest.get(int(row.sku_id))
            if current is None or (row.stat_date, row.id) > (
                current.stat_date,
                current.id,
            ):
                latest[int(row.sku_id)] = row
        return latest

    async def _load_core_skus_by_id(
        self,
        session: AsyncSession,
        *,
        sku_ids: list[int],
    ) -> dict[int, CoreSKU]:
        if not sku_ids:
            return {}
        rows = list(
            (
                await session.execute(select(CoreSKU).where(CoreSKU.id.in_(sku_ids)))
            ).scalars()
        )
        return {int(row.id): row for row in rows}

    async def _load_price_snapshot_by_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_ids: list[int],
    ) -> dict[int, PriceSnapshot]:
        if not nm_ids:
            return {}
        price_rows = list(
            (
                await session.execute(
                    select(WBPrice).where(
                        WBPrice.account_id == account_id,
                        WBPrice.nm_id.in_(nm_ids),
                    )
                )
            ).scalars()
        )
        size_rows = list(
            (
                await session.execute(
                    select(WBPriceSize).where(
                        WBPriceSize.account_id == account_id,
                        WBPriceSize.nm_id.in_(nm_ids),
                    )
                )
            ).scalars()
        )
        by_nm: dict[int, dict[str, Decimal | None]] = defaultdict(
            lambda: {"price": None, "discounted": None}
        )
        for row in size_rows:
            bucket = by_nm[int(row.nm_id)]
            price_value = self._optional_decimal(row.price)
            discounted_value = self._optional_decimal(row.discounted_price)
            if price_value is not None:
                bucket["price"] = (
                    min(bucket["price"], price_value)
                    if bucket["price"] is not None
                    else price_value
                )
            if discounted_value is not None:
                bucket["discounted"] = (
                    min(bucket["discounted"], discounted_value)
                    if bucket["discounted"] is not None
                    else discounted_value
                )

        snapshots: dict[int, PriceSnapshot] = {}
        for row in price_rows:
            payload = row.payload if isinstance(row.payload, dict) else {}
            payload_price, payload_discounted = self._extract_payload_prices(payload)
            size_bucket = by_nm.get(int(row.nm_id), {})
            price_value = payload_price or size_bucket.get("price")
            discounted_value = payload_discounted or size_bucket.get("discounted")
            source = None
            if payload_discounted is not None:
                source = "wb_prices.payload.sizes.discountedPrice"
            elif payload_price is not None:
                source = "wb_prices.payload.sizes.price"
            elif size_bucket.get("discounted") is not None:
                source = "wb_price_sizes.discounted_price"
            elif size_bucket.get("price") is not None:
                source = "wb_price_sizes.price"
            snapshots[int(row.nm_id)] = PriceSnapshot(
                current_price=price_value,
                current_discounted_price=discounted_value,
                price_source=source,
                mapping_status="mapped" if source else "unmapped",
            )
        return snapshots

    def _resolve_price_inputs(
        self,
        *,
        core_sku: CoreSKU | None,
        price_snapshot: PriceSnapshot | None,
        article_price_snapshot: PriceSnapshot | None = None,
        average_sale_price: Decimal | None = None,
    ) -> PriceSnapshot:
        core_discounted = (
            self._optional_decimal(getattr(core_sku, "current_discounted_price", None))
            if core_sku is not None
            else None
        )
        core_price = (
            self._optional_decimal(getattr(core_sku, "current_price", None))
            if core_sku is not None
            else None
        )
        if core_discounted is not None and core_discounted > 0:
            return PriceSnapshot(
                current_price=core_price
                if core_price is not None and core_price > 0
                else None,
                current_discounted_price=core_discounted,
                price_source="current_sku",
                mapping_status="mapped",
            )
        if core_price is not None and core_price > 0:
            return PriceSnapshot(
                current_price=core_price,
                current_discounted_price=None,
                price_source="current_sku",
                mapping_status="mapped",
            )
        if price_snapshot is not None and (
            price_snapshot.current_discounted_price is not None
            or price_snapshot.current_price is not None
        ):
            return PriceSnapshot(
                current_price=price_snapshot.current_price,
                current_discounted_price=price_snapshot.current_discounted_price,
                price_source="wb_price_snapshot",
                mapping_status=price_snapshot.mapping_status,
            )
        if article_price_snapshot is not None and (
            article_price_snapshot.current_discounted_price is not None
            or article_price_snapshot.current_price is not None
        ):
            return PriceSnapshot(
                current_price=article_price_snapshot.current_price,
                current_discounted_price=article_price_snapshot.current_discounted_price,
                price_source="article_price",
                mapping_status=article_price_snapshot.mapping_status,
            )
        if average_sale_price is not None and average_sale_price > 0:
            return PriceSnapshot(
                current_price=average_sale_price,
                current_discounted_price=None,
                price_source="average_sale",
                mapping_status="fallback",
            )
        return PriceSnapshot(
            current_price=None,
            current_discounted_price=None,
            price_source="missing",
            mapping_status="unmapped",
        )

    def _article_price_snapshot_from_daily(
        self, latest_daily: Any | None
    ) -> PriceSnapshot | None:
        if latest_daily is None:
            return None
        current_price = self._optional_decimal(
            getattr(latest_daily, "current_price", None)
        )
        current_discounted_price = self._optional_decimal(
            getattr(latest_daily, "current_discounted_price", None)
        )
        if current_price is None and current_discounted_price is None:
            return None
        return PriceSnapshot(
            current_price=current_price,
            current_discounted_price=current_discounted_price,
            price_source="article_price",
            mapping_status="fallback",
        )

    @staticmethod
    def _extract_payload_prices(
        payload: dict[str, Any] | None,
    ) -> tuple[Decimal | None, Decimal | None]:
        if not isinstance(payload, dict):
            return None, None
        sizes = payload.get("sizes")
        values = sizes if isinstance(sizes, list) else [payload]
        prices: list[Decimal] = []
        discounted: list[Decimal] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            price = item.get("price") or item.get("basicPrice") or item.get("priceU")
            discounted_price = (
                item.get("discountedPrice")
                or item.get("discountPrice")
                or item.get("finalPrice")
            )
            if price not in (None, ""):
                prices.append(Decimal(str(price)))
            if discounted_price not in (None, ""):
                discounted.append(Decimal(str(discounted_price)))
        return (
            min(prices) if prices else None,
            min(discounted) if discounted else None,
        )

    async def _load_open_issues_by_ref(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> tuple[dict[int, list[DataQualityIssue]], dict[int, list[DataQualityIssue]]]:
        issues = list(
            (
                await session.execute(
                    select(DataQualityIssue).where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                    )
                )
            ).scalars()
        )
        by_sku: dict[int, list[DataQualityIssue]] = defaultdict(list)
        by_nm: dict[int, list[DataQualityIssue]] = defaultdict(list)
        for issue in issues:
            sku_id, nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if sku_id is not None:
                by_sku[int(sku_id)].append(issue)
            if nm_id is not None:
                by_nm[int(nm_id)].append(issue)
        return by_sku, by_nm

    async def _latest_formula_audit_passed(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> bool | None:
        try:
            row = (
                await session.execute(
                    select(FormulaAuditRun)
                    .where(
                        or_(
                            FormulaAuditRun.account_id == account_id,
                            FormulaAuditRun.account_id.is_(None),
                        ),
                    )
                    .order_by(
                        FormulaAuditRun.finished_at.desc().nulls_last(),
                        FormulaAuditRun.id.desc(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "formula_audit_runs"):
                return None
            raise
        if row is None:
            return None
        return bool(row.passed)

    async def _trust_decision(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        settings: dict[str, Any] | None = None,
        health: Any | None = None,
    ):
        resolved_settings = (
            settings
            or (
                await self.get_business_settings(session, account_id=account_id)
            ).settings
        )
        resolved_health = health or await self.dashboard.data_health(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        article_audit_consistent = await self._latest_formula_audit_passed(
            session, account_id=account_id
        )
        blocking_issue_count = (
            1
            if "open_blocking_dq_issues" in (resolved_health.blocked_reasons or [])
            else 0
        )
        return build_global_trust_decision(
            supplier_confirmed_revenue_coverage_percent=resolved_health.supplier_confirmed_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=resolved_health.trusted_revenue_cost_coverage_percent,
            cost_trust_policy=resolved_settings.get("cost_trust_policy"),
            failed_domains=resolved_health.failed_domains,
            unresolved_unmatched_sku_count=resolved_health.blocking_unmatched_sku_count,
            latest_stocks_status=resolved_health.latest_stocks_status,
            blocking_open_issue_count=blocking_issue_count,
            article_audit_consistent=article_audit_consistent,
            scheduler_stable=True,
        )

    @staticmethod
    def _safe_price_metrics(
        *,
        current_price: Decimal | None,
        current_discounted_price: Decimal | None,
        average_sale_price: Decimal | None,
        total_unit_cost: Decimal | None,
        revenue: Decimal,
        ad_spend: Decimal,
        net_units: int,
        commission: Decimal,
        acquiring_fee: Decimal,
        deductions: Decimal,
        additional_payments: Decimal,
        logistics: Decimal,
        paid_acceptance: Decimal,
        storage: Decimal,
        penalties: Decimal,
        target_margin_rate: Decimal,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None, bool]:
        if total_unit_cost is None or total_unit_cost <= 0 or net_units <= 0:
            return None, None, None, None, True
        fixed_unit_cost = total_unit_cost
        fixed_unit_cost += (
            logistics + paid_acceptance + storage + penalties + ad_spend
        ) / Decimal(str(max(net_units, 1)))
        if revenue > 0:
            variable_rate = (
                commission + acquiring_fee + deductions - additional_payments
            ) / revenue
        else:
            variable_rate = Decimal("0.18")
        denominator = Decimal("1") - variable_rate
        if denominator <= Decimal("0.05"):
            return None, None, None, None, True
        break_even = fixed_unit_cost / denominator
        target_denominator = Decimal("1") - variable_rate - target_margin_rate
        target_margin_price = None
        if target_denominator > Decimal("0.05"):
            target_margin_price = fixed_unit_cost / target_denominator
        reference_price = (
            current_discounted_price or current_price or average_sale_price
        )
        safe_gap = (
            (reference_price - break_even) if reference_price is not None else None
        )
        estimated_margin = None
        if reference_price is not None and reference_price > 0:
            estimated_margin = (
                (reference_price - break_even) / reference_price
            ) * Decimal("100")
        return break_even, target_margin_price, safe_gap, estimated_margin, False

    @staticmethod
    def _price_not_computable_reason(
        *,
        current_price: Decimal | None,
        current_discounted_price: Decimal | None,
        average_sale_price: Decimal | None,
        total_unit_cost: Decimal | None,
        revenue: Decimal,
        net_units: int,
        break_even: Decimal | None,
    ) -> str | None:
        reasons = ControlTowerService._price_not_computable_reasons(
            current_price=current_price,
            current_discounted_price=current_discounted_price,
            average_sale_price=average_sale_price,
            total_unit_cost=total_unit_cost,
            revenue=revenue,
            net_units=net_units,
            break_even=break_even,
        )
        return reasons[0] if reasons else None

    @staticmethod
    def _price_not_computable_reasons(
        *,
        current_price: Decimal | None,
        current_discounted_price: Decimal | None,
        average_sale_price: Decimal | None,
        total_unit_cost: Decimal | None,
        revenue: Decimal,
        net_units: int,
        break_even: Decimal | None,
    ) -> list[str]:
        reasons: list[str] = []
        if total_unit_cost is None or total_unit_cost <= 0:
            reasons.append("missing_cost")
        if (
            current_price is None
            and current_discounted_price is None
            and average_sale_price is None
        ):
            reasons.append("missing_price")
        if total_unit_cost is None or total_unit_cost <= 0:
            return reasons
        if net_units <= 0:
            reasons.append("not_enough_units")
        if break_even is None and revenue <= 0:
            reasons.append("revenue_not_available")
        if break_even is None:
            reasons.append("formula_not_computable")
        return list(dict.fromkeys(reasons))

    def _priority_score(
        self,
        *,
        profit: Decimal | None,
        revenue: Decimal,
        days_of_stock: Decimal | None,
        trust_state: str,
        blocked_reasons: list[str],
    ) -> float:
        money_impact = abs(float(profit or Decimal("0")))
        urgency = 1.0
        if days_of_stock is not None and days_of_stock <= Decimal("7"):
            urgency = 1.6
        elif days_of_stock is not None and days_of_stock >= Decimal("90"):
            urgency = 1.3
        confidence = (
            1.0
            if trust_state == TRUST_STATE_TRUSTED
            else (0.6 if trust_state != TRUST_STATE_DATA_BLOCKED else 0.35)
        )
        if blocked_reasons:
            confidence *= 0.8
        baseline = max(money_impact, float(revenue) * 0.05)
        return round(baseline * urgency * confidence, 2)

    def _classify_sku_status(
        self,
        *,
        trust_state: str,
        profit: Decimal | None,
        days_of_stock: Decimal | None,
        ad_spend: Decimal,
        safe_price_gap: Decimal | None,
        overstock_threshold_days: int,
        finance_rows: int,
        net_units: int,
    ) -> str:
        if trust_state == TRUST_STATE_DATA_BLOCKED:
            return "DATA_BLOCKED"
        if (
            days_of_stock is not None
            and days_of_stock <= Decimal("7")
            and (profit or Decimal("0")) > 0
        ):
            return "PROTECT_STOCK"
        if profit is not None and profit < 0:
            return "STOP_PURCHASE"
        if days_of_stock is not None and days_of_stock >= Decimal(
            str(overstock_threshold_days)
        ):
            return "LIQUIDATE"
        if safe_price_gap is not None and safe_price_gap < 0:
            return "PRICE_REVIEW"
        if ad_spend > 0 and (profit or Decimal("0")) <= 0:
            return "AD_REVIEW"
        if finance_rows <= 3 and net_units <= 3 and (profit or Decimal("0")) >= 0:
            return "NEW_SKU"
        if (profit or Decimal("0")) > 0:
            return "SCALE"
        return "WATCH"

    @staticmethod
    def _purchase_financial_final(
        *, trust_state: str, final_profit_allowed: bool
    ) -> bool:
        return trust_state == TRUST_STATE_TRUSTED and final_profit_allowed

    @classmethod
    def _purchase_confidence(
        cls, *, trust_state: str, final_profit_allowed: bool
    ) -> str:
        if cls._purchase_financial_final(
            trust_state=trust_state, final_profit_allowed=final_profit_allowed
        ):
            return "high"
        if trust_state != TRUST_STATE_DATA_BLOCKED:
            return "medium"
        return "low"

    @staticmethod
    def _hard_purchase_blocker(blocked_reasons: list[str] | None) -> str | None:
        blocker_priority = [
            "latest_stocks_not_completed",
            "stocks_task_not_ready",
            "stocks_not_completed",
            "finance_not_confirmed",
            "article_audit_mismatch",
            "open_blocking_dq_issues",
            "missing_manual_cost",
            "price_not_mapped",
            "missing_price",
        ]
        reasons = list(blocked_reasons or [])
        for code in blocker_priority:
            if code in reasons:
                return code
        return None

    @staticmethod
    def _purchase_next_step(status: str) -> str:
        if status == "REORDER":
            return "Подготовьте дозаказ по рекомендованному количеству и подтвердите бюджет."
        if status == "LIQUIDATE":
            return (
                "Подготовьте промо/распродажу и не докупайте товар до снижения остатка."
            )
        if status == "DO_NOT_BUY":
            return "Не пополняйте товар, пока не улучшится экономика или не будут сняты риски."
        if status == "PROTECT_STOCK":
            return (
                "Защитите остаток: не давайте лишний трафик и дождитесь прихода товара."
            )
        if status == "WAIT_DATA":
            return "Сначала закройте блокирующие проблемы в данных, затем вернитесь к решению по закупке."
        return (
            "Оставьте товар под наблюдением и перепроверьте динамику в следующем цикле."
        )

    def _purchase_status_and_reason(
        self,
        *,
        trust_state: str,
        estimated_profit: Decimal | None,
        days_of_stock: Decimal | None,
        available_stock_qty: Decimal | None = None,
        lead_time_days: int,
        safety_days: int,
        overstock_threshold_days: int,
        blocked_reasons: list[str] | None = None,
        recommended_qty: int = 0,
        in_transit_qty: Decimal | None = None,
        sales_velocity_daily: Decimal | None = None,
        stock_value: Decimal | None = None,
        margin_percent: Decimal | None = None,
        roi_percent: Decimal | None = None,
        min_profit_threshold: Decimal | None = None,
        target_margin_percent: Decimal | None = None,
        target_roi_percent: Decimal | None = None,
        final_profit_allowed: bool = True,
    ) -> PurchaseDecision:
        financial_final = self._purchase_financial_final(
            trust_state=trust_state, final_profit_allowed=final_profit_allowed
        )
        confidence = self._purchase_confidence(
            trust_state=trust_state, final_profit_allowed=final_profit_allowed
        )
        primary_reason = (
            self._hard_purchase_blocker(blocked_reasons)
            if trust_state == TRUST_STATE_DATA_BLOCKED
            else None
        )
        if trust_state == TRUST_STATE_DATA_BLOCKED or primary_reason is not None:
            primary_reason = primary_reason or next(
                iter(blocked_reasons or []), "data_blocked"
            )
            reason_map = {
                "supplier_cost_not_confirmed": "Себестоимость поставщика еще не подтверждена, поэтому закупочная рекомендация заблокирована.",
                "missing_manual_cost": "Ручная себестоимость отсутствует, поэтому закупочная рекомендация заблокирована.",
                "latest_stocks_not_completed": "Последняя синхронизация остатков не завершена, поэтому закупочная рекомендация заблокирована.",
                "finance_not_confirmed": "Финансовые данные еще не подтверждены, поэтому закупочная рекомендация заблокирована.",
                "article_audit_mismatch": "Сначала нужно закрыть расхождение в аудите артикула, после этого закупка станет доступна.",
                "open_blocking_dq_issues": "Есть блокирующие проблемы качества данных, сначала закройте их.",
                "data_blocked": "Текущего уровня доверия к данным недостаточно для закупочной рекомендации.",
            }
            return PurchaseDecision(
                status="WAIT_DATA",
                reason=reason_map.get(
                    primary_reason,
                    "Текущего уровня доверия к данным недостаточно для закупочной рекомендации.",
                ),
                risk=primary_reason,
                confidence="low",
                next_step=self._purchase_next_step("WAIT_DATA"),
                financial_final=False,
            )
        if estimated_profit is None:
            return PurchaseDecision(
                status="WAIT_DATA",
                reason="По этому SKU пока нет достаточных данных о прибыли.",
                risk="profit_data_missing",
                confidence="low",
                next_step=self._purchase_next_step("WAIT_DATA"),
                financial_final=False,
            )
        min_profit_value = (
            min_profit_threshold if min_profit_threshold is not None else Decimal("0")
        )
        target_margin_value = (
            target_margin_percent if target_margin_percent is not None else Decimal("0")
        )
        target_roi_value = (
            target_roi_percent if target_roi_percent is not None else Decimal("0")
        )
        in_transit = in_transit_qty or Decimal("0")
        velocity = sales_velocity_daily or Decimal("0")
        stock_value_decimal = stock_value or Decimal("0")
        available_stock = available_stock_qty or Decimal("0")
        if days_of_stock is None:
            if available_stock > Decimal("0") and velocity <= Decimal("0"):
                reason = "Остаток есть, но за последние 30 дней продаж не было, поэтому дни остатка не считаются. Деньги заморожены в товаре."
                if not financial_final and trust_state != TRUST_STATE_DATA_BLOCKED:
                    reason += " Финальная прибыль остается предварительной, но операционное решение уже можно принять."
                return PurchaseDecision(
                    status="LIQUIDATE",
                    reason=reason,
                    risk="overstock",
                    confidence=confidence,
                    next_step=self._purchase_next_step("LIQUIDATE"),
                    financial_final=financial_final,
                )
            return PurchaseDecision(
                status="WAIT_DATA",
                reason="По этому SKU пока нет достаточных данных по остаткам.",
                risk="stock_data_missing",
                confidence="low",
                next_step=self._purchase_next_step("WAIT_DATA"),
                financial_final=False,
            )
        reorder_threshold = Decimal(str(lead_time_days + safety_days))
        weak_profit = estimated_profit <= min_profit_value
        margin_ok = margin_percent is None or margin_percent >= target_margin_value
        roi_ok = roi_percent is None or roi_percent >= target_roi_value
        low_velocity_overstock = (
            stock_value_decimal > Decimal("0")
            and velocity <= Decimal("0.2")
            and days_of_stock >= Decimal(str(max(lead_time_days + safety_days, 30)))
        )
        if (
            days_of_stock >= Decimal(str(overstock_threshold_days))
            or low_velocity_overstock
        ):
            reason = "Остаток слишком глубокий относительно скорости продаж, деньги заморожены в товаре."
            if not financial_final and trust_state != TRUST_STATE_DATA_BLOCKED:
                reason += " Финальная прибыль остается предварительной, но операционное решение уже можно принять."
            return PurchaseDecision(
                status="LIQUIDATE",
                reason=reason,
                risk="overstock",
                confidence=confidence,
                next_step=self._purchase_next_step("LIQUIDATE"),
                financial_final=financial_final,
            )
        if weak_profit or not margin_ok or not roi_ok:
            reasons: list[str] = []
            if estimated_profit < 0:
                reasons.append("Юнит-экономика отрицательная.")
            elif weak_profit:
                reasons.append("Прибыль слишком слабая относительно порога закупки.")
            if not margin_ok:
                reasons.append("Маржа ниже бизнес-порога.")
            if not roi_ok:
                reasons.append("Окупаемость ниже бизнес-порога.")
            reason = (
                " ".join(reasons)
                or "Экономика карточки слишком слабая для новой закупки."
            )
            if not financial_final and trust_state != TRUST_STATE_DATA_BLOCKED:
                reason += " Финальная прибыль остается предварительной, поэтому решение нужно держать под контролем."
            return PurchaseDecision(
                status="DO_NOT_BUY",
                reason=reason,
                risk="weak_unit_economics",
                confidence=confidence,
                next_step=self._purchase_next_step("DO_NOT_BUY"),
                financial_final=financial_final,
            )
        if days_of_stock < reorder_threshold:
            if recommended_qty > 0:
                risk = (
                    "out_of_stock"
                    if days_of_stock <= Decimal(str(lead_time_days))
                    else "low_stock"
                )
                reason = "Запаса не хватит на время новой поставки и страховой запас, хотя карточка пока прибыльная."
                if not financial_final and trust_state != TRUST_STATE_DATA_BLOCKED:
                    reason += " Решение операционно допустимо, но финальная прибыль еще предварительная."
                return PurchaseDecision(
                    status="REORDER",
                    reason=reason,
                    risk=risk,
                    confidence=confidence,
                    next_step=self._purchase_next_step("REORDER"),
                    financial_final=financial_final,
                )
            if in_transit > 0:
                reason = "Остаток низкий, но товар уже в пути и перекрывает ближайшую потребность."
                if not financial_final and trust_state != TRUST_STATE_DATA_BLOCKED:
                    reason += " Финальная прибыль еще предварительная."
                return PurchaseDecision(
                    status="PROTECT_STOCK",
                    reason=reason,
                    risk="in_transit_cover",
                    confidence=confidence,
                    next_step=self._purchase_next_step("PROTECT_STOCK"),
                    financial_final=financial_final,
                )
            return PurchaseDecision(
                status="WATCH",
                reason="Остаток снижается, но подтвержденного объема для заказа пока нет.",
                risk="watch_low_stock",
                confidence=confidence,
                next_step=self._purchase_next_step("WATCH"),
                financial_final=financial_final,
            )
        reason = "Текущий уровень остатка приемлем и не требует срочного действия."
        if not financial_final and trust_state != TRUST_STATE_DATA_BLOCKED:
            reason += " Финальная прибыль остается предварительной, поэтому наблюдайте карточку осторожно."
        return PurchaseDecision(
            status="WATCH",
            reason=reason,
            risk=None,
            confidence=confidence,
            next_step=self._purchase_next_step("WATCH"),
            financial_final=financial_final,
        )

    def _formula_audit_result(
        self,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        trust_decision,
        price_rows: dict[int, PriceSafetyRow],
        purchase_rows: dict[int, PurchasePlanRow],
        article_samples: list[dict[str, Any]],
    ) -> tuple[bool, dict[str, Any]]:
        failed_checks: list[str] = []
        price_check_total = len(price_rows)
        price_check_failed = sum(
            1
            for row in price_rows.values()
            if row.action_hint == "PRICE_INCREASE_REVIEW"
            and (row.safe_price_gap is None or row.safe_price_gap >= 0)
        )
        if price_check_failed:
            failed_checks.append("price_safety_contract")
        purchase_check_total = len(purchase_rows)
        purchase_check_failed = sum(
            1
            for row in purchase_rows.values()
            if (
                (
                    row.status == "REORDER"
                    and (
                        row.recommended_qty <= 0
                        or row.trust_state == TRUST_STATE_DATA_BLOCKED
                        or (row.expected_profit is not None and row.expected_profit < 0)
                    )
                )
                or (row.status == "LIQUIDATE" and row.required_cash > 0)
            )
        )
        if purchase_check_failed:
            failed_checks.append("purchase_plan_gate")
        article_failed = [
            sample for sample in article_samples if not sample["revenue_matches_mart"]
        ]
        if article_failed:
            failed_checks.append("article_audit_consistency")
        return (
            len(failed_checks) == 0 and trust_decision.business_trusted,
            {
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "trust_state": trust_decision.trust_state,
                "blocked_reasons": list(trust_decision.blocked_reasons),
                "can_generate_business_actions": trust_decision.can_generate_business_actions,
                "checks": [
                    {
                        "name": "price_safety_contract",
                        "passed": price_check_failed == 0,
                        "checked_rows": price_check_total,
                        "failed_rows": price_check_failed,
                    },
                    {
                        "name": "purchase_plan_gate",
                        "passed": purchase_check_failed == 0,
                        "checked_rows": purchase_check_total,
                        "failed_rows": purchase_check_failed,
                    },
                    {
                        "name": "article_audit_consistency",
                        "passed": len(article_failed) == 0,
                        "checked_rows": len(article_samples),
                        "failed_rows": len(article_failed),
                    },
                ],
                "article_samples": article_samples,
                "summary": {
                    "price_safety_failed_rows": price_check_failed,
                    "purchase_gate_failed_rows": purchase_check_failed,
                    "article_mismatch_rows": len(article_failed),
                    "article_max_difference_amount": max(
                        (
                            abs(float(sample["difference_amount"]))
                            for sample in article_samples
                        ),
                        default=0.0,
                    ),
                },
                "failed_checks": failed_checks,
            },
        )

    async def _build_control_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        profit_rows: list[Any] | None = None,
    ) -> tuple[
        list[ControlTowerSkuRow],
        dict[int, PriceSafetyRow],
        dict[int, PurchasePlanRow],
        dict[int, Any],
    ]:
        window_key = self._control_rows_window_key(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        warm_cached = self._control_rows_window_cache.get(window_key)
        if warm_cached is not None and self._cache_is_fresh(
            warm_cached.computed_at,
            ttl_seconds=self.WARM_CONTROL_ROWS_CACHE_TTL_SECONDS,
        ):
            return self._control_rows_result_from_snapshot(
                window_key=window_key,
                snapshot=warm_cached,
                cache_status="hit",
            )
        inflight_task = self._control_rows_inflight.get(window_key)
        if inflight_task is not None and not inflight_task.done():
            snapshot, _cache_status = await inflight_task
            return self._control_rows_result_from_snapshot(
                window_key=window_key,
                snapshot=snapshot,
                cache_status="hit",
            )
        task = asyncio.create_task(
            self._build_control_rows_uncached(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                profit_rows=profit_rows,
            )
        )
        self._control_rows_inflight[window_key] = task
        try:
            snapshot, cache_status = await task
            return self._control_rows_result_from_snapshot(
                window_key=window_key,
                snapshot=snapshot,
                cache_status=cache_status,
            )
        finally:
            if self._control_rows_inflight.get(window_key) is task:
                self._control_rows_inflight.pop(window_key, None)

    async def _build_control_rows_uncached(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        profit_rows: list[Any] | None = None,
    ) -> tuple[CachedControlRowsSnapshot, str]:
        data_version_hash = await self._control_rows_version_hash(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        cache_key = self._control_rows_cache_key(
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            data_version_hash=data_version_hash,
        )
        window_key = self._control_rows_window_key(
            account_id=account_id, date_from=date_from, date_to=date_to
        )
        cached = self._control_rows_cache.get(cache_key)
        if cached is not None and self._cache_is_fresh(
            cached.computed_at, ttl_seconds=self.CONTROL_ROWS_CACHE_TTL_SECONDS
        ):
            self._control_rows_window_cache[window_key] = cached
            return cached, "hit"

        settings = (
            await self.get_business_settings(session, account_id=account_id)
        ).settings
        cost_trust_policy = str(
            settings.get("cost_trust_policy") or "operator_baseline"
        )
        source_profit_rows = profit_rows or await self._load_profit_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        latest_stock_by_sku = await self._load_latest_stock_by_sku(
            session, account_id=account_id, date_from=date_from, date_to=date_to
        )
        latest_sku_daily_by_sku = await self._load_latest_sku_daily_by_sku(
            session, account_id=account_id, date_from=date_from, date_to=date_to
        )
        sku_ids = [
            int(row.sku_id) for row in source_profit_rows if row.sku_id is not None
        ]
        nm_ids = [int(row.nm_id) for row in source_profit_rows if row.nm_id is not None]
        latest_stock_details_by_sku = await self._load_latest_stock_detail_rows_by_sku(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            sku_ids=sku_ids,
        )
        product_cards_by_nm = await self._load_product_cards_by_nm(
            session,
            account_id=account_id,
            nm_ids=nm_ids,
        )
        price_snapshots_by_nm = await self._load_price_snapshot_by_nm(
            session,
            account_id=account_id,
            nm_ids=nm_ids,
        )
        core_skus_by_id = await self._load_core_skus_by_id(
            session,
            sku_ids=sku_ids,
        )
        open_issues_by_sku, open_issues_by_nm = await self._load_open_issues_by_ref(
            session, account_id=account_id
        )
        action_counts = await self._load_open_action_counts(
            session, account_id=account_id
        )
        ads_source_by_nm, _ads_source_total = await self._load_ads_source_by_nm(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        ads_source_by_sku = self._allocate_source_ads_by_sku(
            rows=source_profit_rows, ads_source_by_nm=ads_source_by_nm
        )
        control_rows: list[ControlTowerSkuRow] = []
        price_rows: dict[int, PriceSafetyRow] = {}
        purchase_rows: dict[int, PurchasePlanRow] = {}

        for row in source_profit_rows:
            sku_id = int(row.sku_id) if row.sku_id is not None else None
            latest_stock = (
                latest_stock_by_sku.get(sku_id) if sku_id is not None else None
            )
            latest_daily = (
                latest_sku_daily_by_sku.get(sku_id) if sku_id is not None else None
            )
            core_sku = core_skus_by_id.get(sku_id) if sku_id is not None else None
            product_card = (
                product_cards_by_nm.get(int(row.nm_id))
                if row.nm_id is not None
                else None
            )
            issue_rows = []
            if sku_id is not None:
                issue_rows.extend(open_issues_by_sku.get(sku_id, []))
            if row.nm_id is not None:
                issue_rows.extend(open_issues_by_nm.get(int(row.nm_id), []))
            blocking_issue_codes = [
                issue.code
                for issue in issue_rows
                if self.dashboard._issue_blocks_business_analysis(issue)
            ]
            raw_blocked_reasons = list(
                dict.fromkeys((row.blocked_reasons or []) + blocking_issue_codes)
            )
            row_cost_truth_level = cost_truth_level_from_flags(
                has_manual_cost=row.has_manual_cost,
                has_real_manual_cost=row.has_real_manual_cost,
                has_placeholder_cost=row.has_placeholder_cost,
                cost_source=row.cost_source,
            )
            per_row_blocked_reasons = normalize_blocked_reasons_for_cost_policy(
                raw_blocked_reasons,
                has_manual_cost=row.has_manual_cost,
                has_real_manual_cost=row.has_real_manual_cost,
                has_placeholder_cost=row.has_placeholder_cost,
                cost_source=row.cost_source,
                cost_truth_level=row_cost_truth_level,
                cost_trust_policy=cost_trust_policy,
            )
            trust_state = trust_state_for_row(
                has_manual_cost=row.has_manual_cost,
                has_real_manual_cost=row.has_real_manual_cost,
                has_placeholder_cost=row.has_placeholder_cost,
                cost_source=row.cost_source,
                cost_truth_level=row_cost_truth_level,
                cost_trust_policy=cost_trust_policy,
                blocked_reasons=per_row_blocked_reasons,
            )
            revenue_decimal = self._decimal(row.realized_revenue)
            net_profit_after_all_expenses = self._optional_decimal(
                getattr(row, "net_profit_after_all_expenses", None)
            )
            profit_decimal = (
                net_profit_after_all_expenses
                if net_profit_after_all_expenses is not None
                else self._optional_decimal(getattr(row, "estimated_profit", None))
            )
            source_ad_spend = (
                self._decimal(getattr(row, "source_ad_spend", None))
                if getattr(row, "source_ad_spend", None) is not None
                else (
                    ads_source_by_sku.get(sku_id, Decimal("0"))
                    if sku_id is not None
                    else Decimal("0")
                )
            )
            row_ad = self.dashboard._row_ad_components(
                row, source_ad_spend=source_ad_spend
            )
            ad_spend_operational = self._decimal(row_ad["ad_spend_operational"])
            ad_spend_finance = self._decimal(row_ad["ad_spend_finance"])
            effective_ad_spend = self._decimal(row_ad["ad_spend_final"])
            ad_spend_source = str(row_ad["ad_spend_source"])
            ad_spend_delta = self._decimal(row_ad["ad_spend_delta"])
            additional_income = expense_additional_income(row)
            raw_ad_spend = self._decimal(getattr(row, "raw_ad_spend", None))
            overallocated_ad_spend = self._decimal(
                getattr(row, "overallocated_ad_spend", None)
            )
            unallocated_ad_spend = self._decimal(
                getattr(row, "unallocated_ad_spend", None)
            )
            ads_allocation_status = str(getattr(row, "ads_allocation_status", "") or "")
            final_profit_allowed = getattr(row, "final_profit_allowed", None)
            if ad_spend_source == "finance_report" or ad_spend_finance > 0:
                if effective_ad_spend <= 0:
                    effective_ad_spend = ad_spend_finance
                ads_metrics = {
                    "raw_ad_spend": effective_ad_spend,
                    "capped_ad_spend": effective_ad_spend,
                    "overallocated_ad_spend": Decimal("0"),
                    "unallocated_ad_spend": (
                        unallocated_ad_spend
                        if unallocated_ad_spend > 0
                        else max(
                            Decimal("0"),
                            source_ad_spend
                            - (
                                ad_spend_operational
                                if ad_spend_operational > 0
                                else source_ad_spend
                            ),
                        )
                    ),
                    "ads_allocation_status": ads_allocation_status or "finance_final",
                    "final_profit_allowed": True
                    if final_profit_allowed is None
                    else bool(final_profit_allowed),
                }
            else:
                mart_ad_spend = (
                    raw_ad_spend
                    if raw_ad_spend > 0
                    else ad_spend_operational
                    if ad_spend_operational > 0
                    else effective_ad_spend
                )
                ads_metrics = self._ads_allocation_metrics(
                    mart_ad_spend=mart_ad_spend,
                    source_ad_spend=source_ad_spend,
                )
                if raw_ad_spend > 0:
                    ads_metrics["raw_ad_spend"] = raw_ad_spend
                if overallocated_ad_spend > 0:
                    ads_metrics["overallocated_ad_spend"] = overallocated_ad_spend
                if unallocated_ad_spend > 0:
                    ads_metrics["unallocated_ad_spend"] = unallocated_ad_spend
                if ads_allocation_status:
                    ads_metrics["ads_allocation_status"] = ads_allocation_status
                if final_profit_allowed is not None:
                    ads_metrics["final_profit_allowed"] = bool(final_profit_allowed)
                effective_ad_spend = (
                    effective_ad_spend
                    if effective_ad_spend > 0
                    else self._decimal(ads_metrics["capped_ad_spend"])
                )
            effective_profit_decimal = profit_decimal
            estimated_cogs_decimal = self._decimal(getattr(row, "estimated_cogs", None))
            effective_margin_percent = (
                row.margin_percent
                if row.margin_percent is not None
                else (
                    self._percent0(effective_profit_decimal, revenue_decimal)
                    if effective_profit_decimal is not None
                    else row.margin_percent
                )
            )
            effective_roi_percent = (
                row.roi_percent
                if row.roi_percent is not None
                else (
                    self._percent0(effective_profit_decimal, estimated_cogs_decimal)
                    if effective_profit_decimal is not None
                    and estimated_cogs_decimal > 0
                    else row.roi_percent
                )
            )
            effective_drr_percent = (
                row.drr_percent
                if row.drr_percent is not None
                else (
                    self._percent0(effective_ad_spend, revenue_decimal)
                    if effective_ad_spend > 0
                    else row.drr_percent
                )
            )
            resolved_price = self._resolve_price_inputs(
                core_sku=core_sku,
                price_snapshot=price_snapshots_by_nm.get(int(row.nm_id))
                if row.nm_id is not None
                else None,
                article_price_snapshot=self._article_price_snapshot_from_daily(
                    latest_daily
                ),
                average_sale_price=self._optional_decimal(
                    getattr(latest_daily, "avg_sale_price", None)
                )
                if latest_daily is not None
                else None,
            )
            current_price = resolved_price.current_price
            current_discounted_price = resolved_price.current_discounted_price
            average_sale_price = (
                self._optional_decimal(getattr(latest_daily, "avg_sale_price", None))
                if latest_daily is not None
                else None
            )
            reference_price = (
                current_discounted_price or current_price or average_sale_price
            )
            total_unit_cost = (
                self._optional_decimal(getattr(core_sku, "total_unit_cost", None))
                if core_sku is not None
                else None
            )
            if total_unit_cost is None:
                estimated_cogs = self._optional_decimal(
                    getattr(row, "estimated_cogs", None)
                )
                net_units = int(getattr(row, "net_units", 0) or 0)
                if estimated_cogs is not None and net_units > 0:
                    total_unit_cost = estimated_cogs / Decimal(str(net_units))
            break_even, target_margin_price, safe_gap, estimated_margin, estimated = (
                self._safe_price_metrics(
                    current_price=current_price,
                    current_discounted_price=current_discounted_price,
                    average_sale_price=average_sale_price,
                    total_unit_cost=total_unit_cost,
                    revenue=revenue_decimal,
                    ad_spend=effective_ad_spend,
                    net_units=int(row.net_units or 0),
                    commission=self._decimal(row.commission),
                    acquiring_fee=self._decimal(row.acquiring_fee),
                    deductions=self._decimal(row.deductions),
                    additional_payments=expense_additional_income(row),
                    logistics=self._decimal(row.logistics),
                    paid_acceptance=self._decimal(row.paid_acceptance),
                    storage=self._decimal(row.storage),
                    penalties=self._decimal(row.penalties),
                    target_margin_rate=Decimal(
                        str(settings.get("target_margin_rate") or 0.2)
                    ),
                )
            )
            target_margin_gap = (
                reference_price - target_margin_price
                if reference_price is not None and target_margin_price is not None
                else None
            )
            days_of_stock = (
                self._optional_decimal(getattr(latest_stock, "days_of_stock", None))
                if latest_stock is not None
                else None
            )
            stock_qty = (
                self._optional_decimal(getattr(latest_stock, "quantity_full", None))
                if latest_stock is not None
                else self._optional_decimal(row.closing_stock_qty)
            )
            stock_value = (
                (stock_qty * total_unit_cost)
                if stock_qty is not None and total_unit_cost is not None
                else None
            )
            sales_7d = (
                int(getattr(latest_stock, "sales_7d", 0) or 0)
                if latest_stock is not None
                else 0
            )
            sales_14d = (
                int(getattr(latest_stock, "sales_14d", 0) or 0)
                if latest_stock is not None
                else 0
            )
            sales_30d = (
                int(getattr(latest_stock, "sales_30d", 0) or 0)
                if latest_stock is not None
                else int(getattr(row, "net_units", 0) or 0)
            )
            previous_7d_sales = max(sales_14d - sales_7d, 0)
            sales_trend_units = sales_7d - previous_7d_sales
            sales_trend_percent = self._safe_percent(
                sales_trend_units, previous_7d_sales
            )
            sales_trend_direction = self._trend_direction(sales_trend_units)
            net_units = int(
                getattr(row, "net_units", 0)
                or getattr(row, "finance_net_units", 0)
                or 0
            )
            unit_profit = (
                effective_profit_decimal / Decimal(str(net_units))
                if effective_profit_decimal is not None and net_units > 0
                else None
            )
            if unit_profit is None and total_unit_cost is not None:
                reference_price = (
                    current_discounted_price or current_price or average_sale_price
                )
                if reference_price is not None:
                    unit_profit = reference_price - total_unit_cost
            stock_detail_rows = [
                self._stock_detail_payload(row=detail_row, core_sku=core_sku)
                for detail_row in (
                    latest_stock_details_by_sku.get(sku_id or 0, [])
                    if sku_id is not None
                    else []
                )
            ]
            region_breakdown = self._region_breakdown_from_stock_details(
                stock_detail_rows
            )
            photo_url = (
                self._first_product_photo_url(product_card.photos)
                if product_card is not None
                else None
            )
            price_not_computable_reason = self._price_not_computable_reason(
                current_price=current_price,
                current_discounted_price=current_discounted_price,
                average_sale_price=average_sale_price,
                total_unit_cost=total_unit_cost,
                revenue=revenue_decimal,
                net_units=int(row.net_units or 0),
                break_even=break_even,
            )
            price_not_computable_reasons = self._price_not_computable_reasons(
                current_price=current_price,
                current_discounted_price=current_discounted_price,
                average_sale_price=average_sale_price,
                total_unit_cost=total_unit_cost,
                revenue=revenue_decimal,
                net_units=int(row.net_units or 0),
                break_even=break_even,
            )
            calculation_state = (
                "not_computable"
                if price_not_computable_reasons
                else "estimated"
                if resolved_price.price_source == "average_sale"
                else "computed"
            )
            sku_status = self._classify_sku_status(
                trust_state=trust_state,
                profit=effective_profit_decimal,
                days_of_stock=days_of_stock,
                ad_spend=effective_ad_spend,
                safe_price_gap=safe_gap,
                overstock_threshold_days=int(
                    settings.get("overstock_threshold_days") or 90
                ),
                finance_rows=int(row.finance_rows or 0),
                net_units=int(row.net_units or 0),
            )
            priority_score = self._priority_score(
                profit=effective_profit_decimal,
                revenue=revenue_decimal,
                days_of_stock=days_of_stock,
                trust_state=trust_state,
                blocked_reasons=per_row_blocked_reasons,
            )
            control_row = ControlTowerSkuRow(
                sku_id=row.sku_id,
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                barcode=row.barcode,
                title=row.title,
                brand=row.brand,
                subject_name=row.subject_name,
                revenue=float(revenue_decimal),
                revenue_final=float(revenue_decimal),
                net_profit=float(effective_profit_decimal)
                if effective_profit_decimal is not None
                else None,
                net_profit_after_all_expenses=float(net_profit_after_all_expenses)
                if net_profit_after_all_expenses is not None
                else None,
                margin_percent=effective_margin_percent,
                roi_percent=effective_roi_percent,
                ad_spend=float(effective_ad_spend),
                ad_spend_operational=float(
                    ad_spend_operational
                    if ad_spend_operational > 0
                    else source_ad_spend
                ),
                ad_spend_finance=float(ad_spend_finance),
                ad_spend_final=float(effective_ad_spend),
                ad_spend_source=ad_spend_source,
                ad_spend_delta=float(ad_spend_delta),
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
                drr_percent=effective_drr_percent,
                total_wb_expenses=self._float0(getattr(row, "total_wb_expenses", None)),
                seller_cogs=self._float0(getattr(row, "seller_cogs", None)),
                seller_other_expense=self._float0(
                    getattr(row, "seller_other_expense", None)
                ),
                total_seller_expenses=self._float0(
                    getattr(row, "total_seller_expenses", None)
                ),
                total_seller_costs=self._float0(
                    getattr(row, "total_seller_expenses", None)
                ),
                additional_income=self._float0(additional_income),
                expense_data_quality=compute_expense_data_quality(row),
                stock_qty=float(stock_qty) if stock_qty is not None else None,
                days_of_stock=float(days_of_stock)
                if days_of_stock is not None
                else None,
                stock_value=float(stock_value) if stock_value is not None else None,
                safe_price_gap=float(safe_gap) if safe_gap is not None else None,
                cost_truth_level=row_cost_truth_level,
                trust_state=trust_state,
                blocked_reasons=per_row_blocked_reasons,
                sku_status=sku_status,
                priority_score=priority_score,
                open_action_count=action_counts.get(int(row.sku_id or 0), 0)
                if row.sku_id is not None
                else 0,
            )
            control_rows.append(control_row)
            if sku_id is not None:
                estimated = calculation_state == "estimated"
                confidence = (
                    "low"
                    if calculation_state == "not_computable"
                    else "high"
                    if trust_state == TRUST_STATE_TRUSTED
                    and resolved_price.price_source
                    in {"current_sku", "wb_price_snapshot"}
                    and not estimated
                    else "medium"
                )
                action_hint = None
                if safe_gap is not None and safe_gap < 0:
                    action_hint = "PRICE_INCREASE_REVIEW"
                elif price_not_computable_reason == "missing_price":
                    action_hint = "FIX_PRICE_MAPPING"
                elif (
                    effective_profit_decimal is not None
                    and effective_profit_decimal < 0
                ):
                    action_hint = "DO_NOT_REORDER"
                price_rows[sku_id] = PriceSafetyRow(
                    sku_id=row.sku_id,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    title=row.title,
                    current_price=float(current_price)
                    if current_price is not None
                    else None,
                    current_discounted_price=float(current_discounted_price)
                    if current_discounted_price is not None
                    else None,
                    average_sale_price=float(average_sale_price)
                    if average_sale_price is not None
                    else None,
                    reference_price=float(reference_price)
                    if reference_price is not None
                    else None,
                    break_even_price=float(break_even)
                    if break_even is not None
                    else None,
                    target_margin_price=float(target_margin_price)
                    if target_margin_price is not None
                    else None,
                    safe_price_gap=float(safe_gap) if safe_gap is not None else None,
                    safe_price_gap_unit="RUB",
                    safe_price_gap_kind="currency_amount",
                    target_margin_gap=float(target_margin_gap)
                    if target_margin_gap is not None
                    else None,
                    target_margin_gap_unit="RUB",
                    target_margin_gap_kind="currency_amount",
                    estimated_margin_at_current_price=float(estimated_margin)
                    if estimated_margin is not None
                    else None,
                    estimated_margin_percent=float(estimated_margin)
                    if estimated_margin is not None
                    else None,
                    estimated=estimated,
                    confidence=confidence,
                    action_hint=action_hint,
                    price_source=resolved_price.price_source or "missing",
                    calculation_state=calculation_state,
                    not_computable_reason=price_not_computable_reason,
                    not_computable_reasons=price_not_computable_reasons,
                    data_state="ready"
                    if calculation_state != "not_computable"
                    else "incomplete",
                    mapping_status=resolved_price.mapping_status
                    or ("fallback" if average_sale_price is not None else "unmapped"),
                )
                sales_velocity = (
                    self._optional_decimal(
                        getattr(latest_stock, "avg_sales_per_day_30d", None)
                    )
                    if latest_stock is not None
                    else None
                )
                sales_velocity = sales_velocity or Decimal("0")
                available_stock = stock_qty or Decimal("0")
                in_transit = (
                    (
                        (
                            self._optional_decimal(
                                getattr(latest_stock, "in_way_to_client", None)
                            )
                            or Decimal("0")
                        )
                        + (
                            self._optional_decimal(
                                getattr(latest_stock, "in_way_from_client", None)
                            )
                            or Decimal("0")
                        )
                    )
                    if latest_stock is not None
                    else Decimal("0")
                )
                lead_time_days = int(settings.get("lead_time_days") or 14)
                safety_days = int(settings.get("safety_days") or 7)
                required_stock = sales_velocity * Decimal(
                    str(lead_time_days + safety_days)
                )
                reorder_qty = max(
                    Decimal("0"), required_stock - available_stock - in_transit
                )
                pack_multiple = max(int(settings.get("pack_multiple") or 1), 1)
                reorder_qty_rounded = (
                    int(ceil(float(reorder_qty) / pack_multiple) * pack_multiple)
                    if reorder_qty > 0
                    else 0
                )
                purchase_decision = self._purchase_status_and_reason(
                    trust_state=trust_state,
                    estimated_profit=effective_profit_decimal,
                    days_of_stock=days_of_stock,
                    available_stock_qty=available_stock,
                    lead_time_days=lead_time_days,
                    safety_days=safety_days,
                    overstock_threshold_days=int(
                        settings.get("overstock_threshold_days") or 90
                    ),
                    blocked_reasons=per_row_blocked_reasons,
                    recommended_qty=reorder_qty_rounded,
                    in_transit_qty=in_transit,
                    sales_velocity_daily=sales_velocity,
                    stock_value=stock_value,
                    margin_percent=effective_margin_percent,
                    roi_percent=effective_roi_percent,
                    min_profit_threshold=Decimal(
                        str(settings.get("min_profit_threshold") or 0)
                    ),
                    target_margin_percent=Decimal(
                        str(settings.get("target_margin_rate") or 0.2)
                    )
                    * Decimal("100"),
                    target_roi_percent=Decimal(
                        str(settings.get("target_roi_percent") or 30)
                    ),
                    final_profit_allowed=control_row.final_profit_allowed,
                )
                purchase_status = purchase_decision.status
                purchase_reason = purchase_decision.reason
                recommended_qty = (
                    reorder_qty_rounded
                    if purchase_status == "REORDER" and reorder_qty_rounded > 0
                    else 0
                )
                risk = purchase_decision.risk
                wait_data_reasons = self._purchase_wait_data_reasons(
                    status=purchase_status,
                    blocked_reasons=per_row_blocked_reasons,
                    risk=risk,
                    reason=purchase_reason,
                    main_reason=purchase_reason,
                )
                required_cash = float(
                    (Decimal(str(recommended_qty)) * total_unit_cost)
                    if total_unit_cost is not None
                    else Decimal("0")
                )
                money_effect: dict[str, Any] = {}
                if purchase_status == "LIQUIDATE":
                    affected_stock_value = self._float0(stock_value)
                    money_effect = {
                        "affected_stock_value": affected_stock_value,
                        "expected_cash_release": affected_stock_value,
                        "expected_profit_impact": None,
                    }
                    required_cash = 0.0
                elif purchase_status == "REORDER":
                    money_effect = {
                        "affected_stock_value": self._float0(stock_value),
                        "expected_cash_release": 0.0,
                        "expected_profit_impact": self._float(effective_profit_decimal),
                    }
                elif purchase_status == "DO_NOT_BUY":
                    money_effect = {
                        "affected_stock_value": self._float0(stock_value),
                        "expected_cash_release": 0.0,
                        "expected_profit_impact": self._float(effective_profit_decimal),
                    }
                purchase_rows[sku_id] = PurchasePlanRow(
                    sku_id=row.sku_id,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    title=row.title
                    or (product_card.title if product_card is not None else None),
                    brand=row.brand
                    or (product_card.brand if product_card is not None else None),
                    subject_name=row.subject_name
                    or (
                        product_card.subject_name if product_card is not None else None
                    ),
                    barcode=row.barcode
                    or (core_sku.barcode if core_sku is not None else None),
                    tech_size=core_sku.tech_size if core_sku is not None else None,
                    photo_url=photo_url,
                    image_url=photo_url,
                    status=purchase_status,
                    decision=purchase_status,
                    trust_state=trust_state,
                    sales_velocity_daily=float(sales_velocity),
                    sales_7d=sales_7d,
                    sales_14d=sales_14d,
                    sales_30d=sales_30d,
                    sales_trend_units=sales_trend_units,
                    sales_trend_percent=sales_trend_percent,
                    sales_trend_direction=sales_trend_direction,
                    days_since_last_sale=getattr(
                        latest_stock, "days_since_last_sale", None
                    )
                    if latest_stock is not None
                    else None,
                    available_stock=float(available_stock),
                    in_transit_qty=float(in_transit),
                    days_of_stock=float(days_of_stock)
                    if days_of_stock is not None
                    else None,
                    lead_time_days=lead_time_days,
                    safety_days=safety_days,
                    recommended_qty=recommended_qty,
                    required_cash=required_cash,
                    expected_profit=float(effective_profit_decimal)
                    if effective_profit_decimal is not None
                    else None,
                    stock_value=self._float0(stock_value),
                    frozen_cash=self._float0(stock_value),
                    current_price=float(current_price)
                    if current_price is not None
                    else None,
                    current_discounted_price=float(current_discounted_price)
                    if current_discounted_price is not None
                    else None,
                    avg_sale_price=float(average_sale_price)
                    if average_sale_price is not None
                    else None,
                    unit_cost=float(total_unit_cost)
                    if total_unit_cost is not None
                    else None,
                    net_profit_per_unit=float(unit_profit)
                    if unit_profit is not None
                    else None,
                    margin_percent=float(effective_margin_percent)
                    if effective_margin_percent is not None
                    else None,
                    roi_percent=float(effective_roi_percent)
                    if effective_roi_percent is not None
                    else None,
                    is_profitable=(effective_profit_decimal > 0)
                    if effective_profit_decimal is not None
                    else None,
                    risk=risk,
                    reason=purchase_reason,
                    main_reason=purchase_reason,
                    missing_data=list(wait_data_reasons),
                    missing_fields=list(wait_data_reasons),
                    wait_data_reasons=list(wait_data_reasons),
                    next_step=purchase_decision.next_step,
                    confidence=purchase_decision.confidence,
                    decision_confidence=purchase_decision.confidence,
                    cost_source=row.cost_source,
                    cost_truth=row_cost_truth_level,
                    cost_truth_level=row_cost_truth_level,
                    financial_final=purchase_decision.financial_final,
                    money_effect=money_effect,
                    region_breakdown=region_breakdown,
                    warehouse_breakdown=stock_detail_rows,
                )
        control_rows.sort(
            key=lambda item: (item.priority_score, item.revenue), reverse=True
        )
        computed_at = utcnow()
        snapshot = CachedControlRowsSnapshot(
            control_rows=control_rows,
            price_rows=price_rows,
            purchase_rows=purchase_rows,
            settings=settings,
            computed_at=computed_at,
            data_version_hash=data_version_hash,
        )
        self._control_rows_cache[cache_key] = snapshot
        self._control_rows_window_cache[window_key] = snapshot
        return snapshot, "miss"

    async def _load_open_action_counts(
        self, session: AsyncSession, *, account_id: int
    ) -> dict[int, int]:
        try:
            rows = (
                await session.execute(
                    select(
                        ActionRecommendation.sku_id, func.count(ActionRecommendation.id)
                    )
                    .where(
                        ActionRecommendation.account_id == account_id,
                        ActionRecommendation.status.in_(
                            ["new", "in_progress", "snoozed"]
                        ),
                        ActionRecommendation.sku_id.is_not(None),
                    )
                    .group_by(ActionRecommendation.sku_id)
                )
            ).all()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "action_recommendations"):
                return {}
            raise
        return {int(sku_id): int(count) for sku_id, count in rows if sku_id is not None}

    async def _load_existing_action_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        status: str | None = None,
        action_type: str | None = None,
    ) -> list[ActionRecommendation]:
        stmt = select(ActionRecommendation).where(
            ActionRecommendation.account_id == account_id,
            ActionRecommendation.source_date_from == date_from,
            ActionRecommendation.source_date_to == date_to,
        )
        if status is not None:
            stmt = stmt.where(ActionRecommendation.status == status)
        if action_type is not None:
            stmt = stmt.where(ActionRecommendation.action_type == action_type)
        try:
            return list(
                (
                    await session.execute(
                        stmt.order_by(
                            ActionRecommendation.updated_at.desc(),
                            ActionRecommendation.id.desc(),
                        )
                    )
                ).scalars()
            )
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "action_recommendations"):
                return []
            raise

    async def _sync_recommendations_cached(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        control_rows: list[ControlTowerSkuRow],
        price_rows: dict[int, PriceSafetyRow],
        purchase_rows: dict[int, PurchasePlanRow],
        trust_decision: Any,
    ) -> list[ActionRecommendation]:
        cache_key = self._action_sync_cache_key(
            account_id=account_id, date_from=date_from, date_to=date_to
        )
        cached = self._action_sync_cache.get(cache_key)
        if cached is not None:
            cached_at, data_version_hash = cached
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.ACTION_SYNC_CACHE_TTL_SECONDS
            ):
                rows = await self._load_existing_action_rows(
                    session,
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                )
                if rows:
                    self._action_sync_last_meta[cache_key] = {
                        "computed_at": cached_at,
                        "cache_status": "hit",
                        "data_version_hash": data_version_hash,
                    }
                    return rows

        actions = await self._sync_recommendations(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            control_rows=control_rows,
            price_rows=price_rows,
            purchase_rows=purchase_rows,
            trust_decision=trust_decision,
        )
        await self._sync_alerts_from_actions(session, actions=actions)
        persisted_rows = await self._load_existing_action_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        if not persisted_rows and actions:
            persisted_rows = list(actions)
        computed_at = utcnow()
        data_version_hash = hashlib.sha1(
            "|".join(
                [
                    str(account_id),
                    date_from.isoformat(),
                    date_to.isoformat(),
                    str(len(persisted_rows)),
                    str(
                        sum(
                            (
                                self._decimal(item.expected_effect_amount)
                                for item in persisted_rows
                                if item.expected_effect_amount is not None
                            ),
                            start=Decimal("0"),
                        )
                    ),
                ]
            ).encode("utf-8"),
            usedforsecurity=False,
        ).hexdigest()
        self._action_sync_cache[cache_key] = (computed_at, data_version_hash)
        self._action_sync_last_meta[cache_key] = {
            "computed_at": computed_at,
            "cache_status": "miss",
            "data_version_hash": data_version_hash,
        }
        return persisted_rows

    def _make_action_key(
        self,
        *,
        account_id: int,
        sku_id: int | None,
        nm_id: int | None,
        action_type: str,
        reason_code: str,
        date_from: date,
        date_to: date,
    ) -> str:
        return "|".join(
            [
                str(account_id),
                str(sku_id or ""),
                str(nm_id or ""),
                action_type,
                reason_code,
                f"{date_from.isoformat()}:{date_to.isoformat()}",
            ]
        )

    def _snapshot_hash(self, row: ControlTowerSkuRow) -> str:
        payload = "|".join(
            [
                str(row.sku_id or ""),
                str(row.nm_id or ""),
                str(row.vendor_code or ""),
                str(row.sku_status),
                str(row.trust_state),
                str(row.priority_score),
                str(row.stock_qty or ""),
                str(row.days_of_stock or ""),
                str(row.net_profit or ""),
            ]
        )
        return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _action_priority(self, *, score: float, blocked: bool) -> str:
        if blocked or score >= 5000:
            return "critical"
        if score >= 2000:
            return "high"
        if score >= 500:
            return "medium"
        return "low"

    @staticmethod
    def _blocked_action_type(blocked_reasons: list[str]) -> str:
        if any(
            reason
            in {
                "missing_manual_cost",
                "supplier_cost_not_confirmed",
                "supplier_cost_coverage_below_threshold",
            }
            for reason in blocked_reasons
        ):
            return "FIX_COST_TRUST"
        if any(
            reason in {"unmatched_sku_detected", "sku_mapping_incomplete"}
            for reason in blocked_reasons
        ):
            return "MAP_UNMATCHED_SKU"
        if any(
            reason
            in {
                "latest_stocks_not_completed",
                "stocks_task_not_ready",
                "stocks_not_completed",
            }
            for reason in blocked_reasons
        ):
            return "FIX_STOCK_SYNC"
        if any(
            reason
            in {
                "article_audit_mismatch",
                "finance_not_confirmed",
                "open_blocking_dq_issues",
            }
            for reason in blocked_reasons
        ):
            return "RECONCILE_FINANCE"
        if any(
            reason in {"ad_spend_not_allocated", "ads_not_allocated_to_profitability"}
            for reason in blocked_reasons
        ):
            return "FIX_AD_ALLOCATION"
        if any(
            reason in {"price_not_mapped", "price_missing", "missing_price"}
            for reason in blocked_reasons
        ):
            return "FIX_PRICE_MAPPING"
        return "DATA_FIX_REQUIRED"

    async def _sync_recommendations(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
        control_rows: list[ControlTowerSkuRow],
        price_rows: dict[int, PriceSafetyRow],
        purchase_rows: dict[int, PurchasePlanRow],
        trust_decision,
    ) -> list[ActionRecommendation]:
        try:
            existing = await self._load_existing_action_rows(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
            )
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "action_recommendations"):
                return []
            raise
        by_key = {row.action_unique_key: row for row in existing}
        touched: dict[str, ActionRecommendation] = {}
        data_fix_action_types = {
            "DATA_FIX_REQUIRED",
            "RECONCILIATION_REVIEW",
            "FIX_COST_TRUST",
            "MAP_UNMATCHED_SKU",
            "FIX_STOCK_SYNC",
            "RECONCILE_FINANCE",
            "FIX_AD_ALLOCATION",
            "FIX_PRICE_MAPPING",
        }

        def row_unit_cost(current_row: ControlTowerSkuRow) -> float | None:
            if current_row.stock_value is None or current_row.stock_qty in (None, 0):
                return None
            return float(
                Decimal(str(current_row.stock_value))
                / Decimal(str(current_row.stock_qty))
            )

        def store_action(
            *,
            sku_id: int | None,
            nm_id: int | None,
            vendor_code: str | None,
            title: str | None,
            trust_state: str,
            blocked_reasons: list[str],
            priority_score: float,
            action_type: str,
            reason_code: str,
            reason: str,
            calculation_basis: str | None,
            expected_effect_amount: Any,
            confidence: str,
            snapshot_hash: str,
            payload: dict[str, Any] | None = None,
        ) -> None:
            unique_key = self._make_action_key(
                account_id=account_id,
                sku_id=sku_id,
                nm_id=nm_id,
                action_type=action_type,
                reason_code=reason_code,
                date_from=date_from,
                date_to=date_to,
            )
            action = by_key.get(unique_key)
            business_copy = self._action_business_copy(
                action_type=action_type,
                reason=reason,
                blocked_reasons=blocked_reasons,
                payload=payload,
                vendor_code=vendor_code,
                nm_id=nm_id,
                sku_id=sku_id,
            )
            merged_payload = {
                **dict(payload or {}),
                "whatToDo": business_copy["what_to_do"],
                "why": business_copy["why"],
                "howToFix": list(business_copy["how_to_fix"]),
                "linkedEntity": business_copy["linked_entity"],
            }
            if business_copy.get("deadline_hint") is not None:
                merged_payload["deadlineHint"] = business_copy["deadline_hint"]
            if (
                business_copy.get("required_cash") is not None
                and merged_payload.get("requiredCash") is None
            ):
                merged_payload["requiredCash"] = business_copy["required_cash"]
            priority = self._action_priority(
                score=priority_score, blocked=action_type in data_fix_action_types
            )
            if action is None:
                action = ActionRecommendation(
                    account_id=account_id,
                    sku_id=sku_id,
                    nm_id=nm_id,
                    vendor_code=vendor_code,
                    title=title,
                    action_type=action_type,
                    priority=priority,
                    status="new",
                    reason_code=reason_code,
                    reason=reason,
                    calculation_basis=calculation_basis,
                    expected_effect_amount=expected_effect_amount,
                    confidence=confidence,
                    trust_state=trust_state,
                    blocked_reasons=blocked_reasons,
                    source_date_from=date_from,
                    source_date_to=date_to,
                    source_snapshot_hash=snapshot_hash,
                    action_unique_key=unique_key,
                    payload=merged_payload,
                )
                session.add(action)
                by_key[unique_key] = action
            else:
                action.vendor_code = vendor_code
                action.title = title
                action.priority = priority
                action.reason = reason
                action.calculation_basis = calculation_basis
                action.expected_effect_amount = expected_effect_amount
                action.confidence = confidence
                action.trust_state = trust_state
                action.blocked_reasons = blocked_reasons
                action.source_date_from = date_from
                action.source_date_to = date_to
                action.source_snapshot_hash = snapshot_hash
                action.payload = merged_payload
            touched[unique_key] = action

        for row in control_rows:
            sku_id = int(row.sku_id) if row.sku_id is not None else None
            price = price_rows.get(sku_id) if sku_id is not None else None
            purchase = purchase_rows.get(sku_id) if sku_id is not None else None
            candidates: list[dict[str, Any]] = []
            effective_blocked_reasons = list(
                dict.fromkeys(
                    list(trust_decision.blocked_reasons) + list(row.blocked_reasons)
                )
            )
            if (
                not trust_decision.can_generate_business_actions
                or row.trust_state == TRUST_STATE_DATA_BLOCKED
            ):
                if effective_blocked_reasons:
                    action_type = self._blocked_action_type(effective_blocked_reasons)
                    candidates.append(
                        {
                            "action_type": action_type,
                            "reason_code": effective_blocked_reasons[0],
                            "reason": f"SKU заблокирован для бизнес-автоматизации: {', '.join(effective_blocked_reasons)}",
                            "expected_effect_amount": None,
                            "confidence": "high"
                            if effective_blocked_reasons
                            else "medium",
                            "calculation_basis": "Глобальный уровень доверия к данным или блокеры на уровне SKU не позволяют запускать бизнес-действия.",
                            "payload": {
                                "currentStock": row.stock_qty or 0,
                                "daysOfStock": row.days_of_stock or 0,
                            },
                        }
                    )
            else:
                if any(
                    reason
                    in {
                        "finance_not_confirmed",
                        "article_audit_mismatch",
                        "open_blocking_dq_issues",
                    }
                    for reason in row.blocked_reasons
                ):
                    candidates.append(
                        {
                            "action_type": "RECONCILE_FINANCE",
                            "reason_code": "finance_not_confirmed",
                            "reason": "Нужно проверить расхождение между финансовым отчетом WB, продажами и расчетной выручкой по карточке.",
                            "expected_effect_amount": abs(row.net_profit)
                            if row.net_profit is not None and row.net_profit < 0
                            else row.revenue,
                            "confidence": "high",
                            "calculation_basis": f"blocked_reasons={row.blocked_reasons}",
                            "payload": {
                                "currentStock": row.stock_qty or 0,
                                "daysOfStock": row.days_of_stock or 0,
                            },
                        }
                    )
                if (
                    purchase is not None
                    and purchase.status == "REORDER"
                    and purchase.recommended_qty > 0
                ):
                    candidates.append(
                        {
                            "action_type": "REORDER",
                            "reason_code": str(purchase.risk or "reorder"),
                            "reason": purchase.main_reason or purchase.reason,
                            "expected_effect_amount": purchase.expected_profit,
                            "confidence": purchase.confidence
                            or (
                                "high"
                                if row.trust_state == TRUST_STATE_TRUSTED
                                else "medium"
                            ),
                            "calculation_basis": (
                                f"days_of_stock={purchase.days_of_stock}, lead_time_days={purchase.lead_time_days}, safety_days={purchase.safety_days}"
                                + (
                                    "; решение предварительное"
                                    if not purchase.financial_final
                                    else ""
                                )
                            ),
                            "payload": {
                                "recommendedQty": purchase.recommended_qty,
                                "requiredCash": purchase.required_cash,
                                "unitCost": (
                                    purchase.required_cash / purchase.recommended_qty
                                )
                                if purchase.recommended_qty
                                else None,
                                "currentStock": purchase.available_stock,
                                "daysOfStock": purchase.days_of_stock,
                                "leadTimeDays": purchase.lead_time_days,
                                "safetyDays": purchase.safety_days,
                                "moneyEffect": dict(purchase.money_effect or {}),
                                "financialFinal": purchase.financial_final,
                            },
                        }
                    )
                if purchase is not None and purchase.status == "PROTECT_STOCK":
                    candidates.append(
                        {
                            "action_type": "PROTECT_STOCK",
                            "reason_code": str(purchase.risk or "protect_stock"),
                            "reason": purchase.main_reason or purchase.reason,
                            "expected_effect_amount": row.revenue,
                            "confidence": purchase.confidence
                            or (
                                "high"
                                if row.trust_state == TRUST_STATE_TRUSTED
                                else "medium"
                            ),
                            "calculation_basis": f"days_of_stock={purchase.days_of_stock}, in_transit_qty={purchase.in_transit_qty}",
                            "payload": {
                                "currentStock": purchase.available_stock,
                                "daysOfStock": purchase.days_of_stock,
                                "leadTimeDays": purchase.lead_time_days,
                                "safetyDays": purchase.safety_days,
                                "moneyEffect": {
                                    "protected_revenue": row.revenue,
                                    "affected_stock_value": row.stock_value,
                                    **dict(purchase.money_effect or {}),
                                },
                                "financialFinal": purchase.financial_final,
                            },
                        }
                    )
                if row.net_profit is not None and row.net_profit < 0:
                    negative_type = (
                        "PRICE_INCREASE_REVIEW"
                        if price is not None
                        and price.safe_price_gap is not None
                        and price.safe_price_gap < 0
                        else "DO_NOT_REORDER"
                    )
                    candidates.append(
                        {
                            "action_type": negative_type,
                            "reason_code": "negative_profit",
                            "reason": "Выбранный SKU убыточен в текущем периоде.",
                            "expected_effect_amount": abs(row.net_profit),
                            "confidence": "high"
                            if row.trust_state == TRUST_STATE_TRUSTED
                            else "medium",
                            "calculation_basis": f"net_profit={row.net_profit}, margin={row.margin_percent}",
                            "payload": {
                                "currentStock": row.stock_qty or 0,
                                "daysOfStock": row.days_of_stock or 0,
                                "unitCost": row_unit_cost(row),
                                "financialFinal": row.trust_state == TRUST_STATE_TRUSTED
                                and row.final_profit_allowed,
                            },
                        }
                    )
                if purchase is not None and purchase.status == "LIQUIDATE":
                    candidates.append(
                        {
                            "action_type": "LIQUIDATE_STOCK",
                            "reason_code": "overstock",
                            "reason": purchase.main_reason or purchase.reason,
                            "expected_effect_amount": float(
                                (purchase.money_effect or {}).get(
                                    "affected_stock_value"
                                )
                                or row.stock_value
                                or 0
                            ),
                            "confidence": purchase.confidence or "medium",
                            "calculation_basis": f"days_of_stock={purchase.days_of_stock}, stock_value={row.stock_value}",
                            "payload": {
                                "currentStock": purchase.available_stock,
                                "daysOfStock": purchase.days_of_stock,
                                "requiredCash": 0,
                                "unitCost": row_unit_cost(row),
                                "moneyEffect": dict(purchase.money_effect or {}),
                                "financialFinal": purchase.financial_final,
                            },
                        }
                    )
                if (
                    price is not None
                    and price.safe_price_gap is not None
                    and price.safe_price_gap < 0
                ):
                    candidates.append(
                        {
                            "action_type": "PRICE_INCREASE_REVIEW",
                            "reason_code": "below_break_even",
                            "reason": "Текущая цена продажи ниже расчетного порога безубыточности.",
                            "expected_effect_amount": abs(price.safe_price_gap),
                            "confidence": price.confidence,
                            "calculation_basis": f"break_even_price={price.break_even_price}, current_discounted_price={price.current_discounted_price}",
                            "payload": {
                                "unitCost": row_unit_cost(row),
                                "currentPrice": price.current_price,
                                "currentDiscountedPrice": price.current_discounted_price,
                                "financialFinal": row.trust_state == TRUST_STATE_TRUSTED
                                and row.final_profit_allowed,
                            },
                        }
                    )
                if (
                    row.ad_spend > 0
                    and row.net_profit is not None
                    and row.net_profit <= 0
                ):
                    candidates.append(
                        {
                            "action_type": "AD_PAUSE_REVIEW",
                            "reason_code": "ad_waste",
                            "reason": "Рекламные расходы активны, а чистая прибыль не положительная.",
                            "expected_effect_amount": row.ad_spend,
                            "confidence": "medium",
                            "calculation_basis": f"ad_spend={row.ad_spend}, net_profit={row.net_profit}, drr={row.drr_percent}",
                            "payload": {
                                "currentStock": row.stock_qty or 0,
                                "daysOfStock": row.days_of_stock or 0,
                                "financialFinal": row.trust_state == TRUST_STATE_TRUSTED
                                and row.final_profit_allowed,
                            },
                        }
                    )
                if (
                    row.ad_spend <= 0
                    and row.net_profit is not None
                    and row.net_profit > 0
                    and row.revenue > 0
                    and row.priority_score >= 500
                ):
                    candidates.append(
                        {
                            "action_type": "CARD_CONTENT_REVIEW",
                            "reason_code": "conversion_growth",
                            "reason": "SKU прибыльный, но дополнительный рост можно получить через оптимизацию контента и конверсии.",
                            "expected_effect_amount": row.net_profit,
                            "confidence": "medium",
                            "calculation_basis": f"revenue={row.revenue}, priority_score={row.priority_score}",
                            "payload": {
                                "currentStock": row.stock_qty or 0,
                                "daysOfStock": row.days_of_stock or 0,
                                "financialFinal": row.trust_state == TRUST_STATE_TRUSTED
                                and row.final_profit_allowed,
                            },
                        }
                    )
            for candidate in candidates:
                store_action(
                    sku_id=sku_id,
                    nm_id=row.nm_id,
                    vendor_code=row.vendor_code,
                    title=row.title,
                    trust_state=row.trust_state,
                    blocked_reasons=row.blocked_reasons,
                    priority_score=row.priority_score,
                    action_type=candidate["action_type"],
                    reason_code=candidate["reason_code"],
                    reason=candidate["reason"],
                    calculation_basis=candidate["calculation_basis"],
                    expected_effect_amount=candidate["expected_effect_amount"],
                    confidence=candidate["confidence"],
                    snapshot_hash=self._snapshot_hash(row),
                    payload={
                        "skuStatus": row.sku_status,
                        "priorityScore": row.priority_score,
                        **dict(candidate.get("payload") or {}),
                    },
                )
        for reason in trust_decision.blocked_reasons:
            action_type = self._blocked_action_type([reason])
            blocker_titles = {
                "supplier_cost_coverage_below_threshold": "Реальная себестоимость не подтверждена",
                "unmatched_sku_detected": "Есть несвязанные SKU",
                "latest_stocks_not_completed": "Синхронизация остатков не завершена",
                "open_blocking_dq_issues": "Есть блокирующие проблемы качества данных",
                "failed_sync_domains": "Есть ошибки в загрузке данных",
                "article_audit_mismatch": "Есть расхождение в аудите артикула",
            }
            store_action(
                sku_id=None,
                nm_id=None,
                vendor_code=None,
                title=blocker_titles.get(reason, "Глобальный блокер данных"),
                trust_state=trust_decision.trust_state,
                blocked_reasons=[reason],
                priority_score=10_000,
                action_type=action_type,
                reason_code=reason,
                reason=f"Глобальный блокер данных: {reason}",
                calculation_basis="Global trust gate blocks final business decisions until the blocker is closed.",
                expected_effect_amount=None,
                confidence="high",
                snapshot_hash=hashlib.sha1(
                    f"{account_id}|{reason}|{date_from}|{date_to}".encode("utf-8"),
                    usedforsecurity=False,
                ).hexdigest(),
                payload={
                    "linkedEntity": {"account_id": account_id},
                },
            )
        open_statuses = {"new", "in_progress", "snoozed"}
        for action in existing:
            if action.source_date_from != date_from or action.source_date_to != date_to:
                continue
            if action.status not in open_statuses:
                continue
            if action.action_unique_key in touched:
                continue
            action.status = "resolved"
            action.resolved_at = utcnow()
            action.user_comment = (
                action.user_comment
                or "Auto-resolved because the recommendation is no longer produced by the latest sync."
            )
        try:
            await session.flush()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "action_recommendations"):
                return []
            raise
        return list(touched.values())

    async def _sync_alerts_from_actions(
        self,
        session: AsyncSession,
        *,
        actions: list[ActionRecommendation],
    ) -> list[AlertEvent]:
        if not actions:
            return []
        account_id = actions[0].account_id
        action_ids = [int(action.id) for action in actions if action.id is not None]
        if not action_ids:
            return []
        try:
            existing = list(
                (
                    await session.execute(
                        select(AlertEvent).where(
                            AlertEvent.account_id == account_id,
                            AlertEvent.action_id.in_(action_ids),
                        )
                    )
                ).scalars()
            )
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "alert_events"):
                return []
            raise
        by_action_id = {
            row.action_id: row for row in existing if row.action_id is not None
        }
        touched: list[AlertEvent] = []
        for action in actions:
            if action.priority not in {"critical", "high"}:
                continue
            title = f"{action.action_type.replace('_', ' ').title()} · {action.vendor_code or action.nm_id or action.sku_id or 'магазин'}"
            message = action.reason
            alert = by_action_id.get(action.id)
            if alert is None:
                alert = AlertEvent(
                    account_id=action.account_id,
                    action_id=action.id,
                    alert_type=action.action_type,
                    severity=action.priority,
                    status="new",
                    title=title,
                    message=message,
                    confidence=action.confidence,
                    payload={"trustState": action.trust_state},
                )
                session.add(alert)
                by_action_id[action.id] = alert
            else:
                alert.alert_type = action.action_type
                alert.severity = action.priority
                alert.title = title
                alert.message = message
                alert.confidence = action.confidence
                alert.payload = {"trustState": action.trust_state}
            touched.append(alert)
        try:
            await session.flush()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "alert_events"):
                return []
            raise
        return touched

    def _action_read(self, row: ActionRecommendation) -> ActionRecommendationRead:
        reason = row.reason or ""
        payload = dict(row.payload or {})
        business_copy = self._action_business_copy(
            action_type=row.action_type,
            reason=reason,
            blocked_reasons=list(row.blocked_reasons or []),
            payload=payload,
            vendor_code=row.vendor_code,
            nm_id=row.nm_id,
            sku_id=row.sku_id,
        )
        money_effect = dict(
            payload.get("moneyEffect") or business_copy.get("money_effect") or {}
        )
        linked_entity = payload.get("linkedEntity") or business_copy["linked_entity"]
        category = self._action_category(row.action_type)
        affected_nm_ids = []
        if row.nm_id is not None:
            affected_nm_ids.append(int(row.nm_id))
        elif linked_entity.get("nm_id"):
            affected_nm_ids.append(int(linked_entity["nm_id"]))
        affected_sku_ids = []
        if row.sku_id is not None:
            affected_sku_ids.append(int(row.sku_id))
        elif linked_entity.get("sku_id"):
            affected_sku_ids.append(int(linked_entity["sku_id"]))
        financial_final = (
            bool(payload.get("financialFinal"))
            if payload.get("financialFinal") is not None
            else (
                row.trust_state == TRUST_STATE_TRUSTED
                and not list(row.blocked_reasons or [])
            )
        )
        required_cash = (
            float(self._decimal(payload.get("requiredCash")))
            if payload.get("requiredCash") is not None
            else business_copy.get("required_cash")
        )
        if row.action_type == "LIQUIDATE_STOCK":
            affected_stock_value = float(
                self._decimal(
                    money_effect.get("affected_stock_value")
                    or payload.get("affectedStockValue")
                    or payload.get("requiredCash")
                    or row.expected_effect_amount
                )
            )
            if affected_stock_value > 0:
                if not money_effect.get("affected_stock_value"):
                    money_effect["affected_stock_value"] = affected_stock_value
                if not money_effect.get("expected_cash_release"):
                    money_effect["expected_cash_release"] = float(
                        self._decimal(
                            row.expected_effect_amount or affected_stock_value
                        )
                    )
            required_cash = 0.0
        primary_amount = (
            float(self._decimal(row.expected_effect_amount))
            if row.expected_effect_amount is not None
            else 0.0
        )
        if row.action_type == "LIQUIDATE_STOCK":
            primary_amount = float(
                self._decimal(
                    money_effect.get("affected_stock_value") or primary_amount
                )
            )
        elif row.action_type == "REORDER":
            primary_amount = float(
                self._decimal(
                    money_effect.get("expected_profit_impact") or primary_amount
                )
            )
        elif row.action_type == "PROTECT_STOCK":
            primary_amount = float(
                self._decimal(money_effect.get("protected_revenue") or primary_amount)
            )
        money_trust = classify_money_trust(
            value=primary_amount,
            value_type="money",
            confidence=row.confidence,
            trust_state=row.trust_state,
            financial_final=financial_final,
            source_module="control_tower",
            source_endpoint=self._action_source_endpoint(
                action_type=row.action_type, linked_entity=linked_entity
            ),
            action_type=row.action_type,
            payload=payload,
        )
        return ActionRecommendationRead(
            id=row.id,
            account_id=row.account_id,
            sku_id=row.sku_id,
            nm_id=row.nm_id,
            vendor_code=row.vendor_code,
            title=row.title,
            action_type=row.action_type,
            category=category,
            priority=row.priority,
            status=row.status,
            reason_code=row.reason_code,
            reason=reason,
            reason_short=self._short_reason(reason),
            reason_full=reason,
            business_reason=payload.get("why") or business_copy["why"],
            next_step=payload.get("whatToDo") or business_copy["what_to_do"],
            calculation_basis=row.calculation_basis,
            expected_effect_amount=primary_amount
            if row.expected_effect_amount is not None or primary_amount > 0
            else None,
            priority_score=float(self._decimal(row.expected_effect_amount))
            if row.expected_effect_amount is not None
            else primary_amount,
            confidence=row.confidence,
            trust_state=row.trust_state,
            financial_final=financial_final,
            blocked_reasons=list(row.blocked_reasons or []),
            source_date_from=row.source_date_from,
            source_date_to=row.source_date_to,
            source_snapshot_hash=row.source_snapshot_hash,
            assigned_to=row.assigned_to,
            deadline_at=row.deadline_at,
            resolved_at=row.resolved_at,
            user_comment=row.user_comment,
            payload=payload,
            what_to_do=payload.get("whatToDo") or business_copy["what_to_do"],
            why=payload.get("why") or business_copy["why"],
            how_to_fix=list(payload.get("howToFix") or business_copy["how_to_fix"]),
            required_cash=required_cash,
            money_effect=money_effect,
            deadline_hint=payload.get("deadlineHint")
            or business_copy.get("deadline_hint"),
            linked_entity=linked_entity,
            affected_nm_ids=affected_nm_ids,
            affected_sku_ids=affected_sku_ids,
            source_endpoint=self._action_source_endpoint(
                action_type=row.action_type, linked_entity=linked_entity
            ),
            money_trust=money_trust,
            seller_visible_by_default=money_trust.seller_visible_by_default,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _money_service(self):
        # Imported lazily to avoid module-level circular imports:
        # money_management imports ControlTowerService for runtime composition.
        if self._money_management_service is None:
            from app.services.money_management import MoneyManagementService

            self._money_management_service = MoneyManagementService()
        return self._money_management_service

    def _action_list_item(
        self, row: ActionRecommendation
    ) -> ActionRecommendationListItem:
        payload = dict(row.payload or {})
        linked_entity = dict(payload.get("linkedEntity") or {})
        linked_entity_type = linked_entity.get("type")
        linked_entity_id = linked_entity.get("id")
        if linked_entity_id is None:
            linked_entity_id = row.nm_id if row.nm_id is not None else row.sku_id
        money_trust = classify_money_trust(
            value=row.expected_effect_amount,
            value_type="money" if row.expected_effect_amount is not None else "text",
            confidence=row.confidence,
            trust_state=getattr(row, "trust_state", None),
            source_module="control_tower",
            action_type=row.action_type,
            payload=payload,
        )
        return ActionRecommendationListItem(
            id=row.id,
            account_id=row.account_id,
            status=row.status,
            priority=row.priority,
            action_type=row.action_type,
            title=row.title,
            short_reason=self._short_reason(row.reason),
            expected_effect_amount=float(self._decimal(row.expected_effect_amount))
            if row.expected_effect_amount is not None
            else None,
            confidence=row.confidence,
            money_trust=money_trust,
            seller_visible_by_default=money_trust.seller_visible_by_default,
            linked_entity_type=linked_entity_type,
            linked_entity_id=int(linked_entity_id)
            if linked_entity_id is not None
            else None,
            nm_id=row.nm_id,
            sku_id=row.sku_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @staticmethod
    def _owner_business_status_from_summary(summary: Any) -> str:
        summary_trust = getattr(summary, "trust", None) or getattr(
            summary.meta, "data_trust", None
        )
        trust_state = str(
            getattr(summary_trust, "trust_state", "")
            or getattr(summary_trust, "state", "")
            or ""
        )
        if trust_state:
            return trust_state
        if bool(getattr(summary_trust, "financial_final", False)):
            return "financial_final"
        if bool(
            getattr(summary.meta.data_trust, "can_generate_business_actions", False)
        ):
            return "operational_provisional"
        return "blocked"

    def _owner_message_reason_from_summary(self, summary: Any) -> str:
        parts: list[str] = []
        if getattr(summary.revenue_sources, "reconciliation_status", "") != "matched":
            parts.append(
                f"Есть расхождение между отчетом WB и продажами: {self._float0(getattr(summary.revenue_sources, 'difference_percent', 0)):.2f}%"
            )
        supplier_percent = self._float0(
            getattr(summary.quality, "supplier_confirmed_cost_coverage_percent", None)
            if getattr(
                summary.quality, "supplier_confirmed_cost_coverage_percent", None
            )
            is not None
            else getattr(summary.quality, "supplier_cost_coverage_percent", 0)
        )
        if supplier_percent < 95:
            parts.append(
                f"Подтвержденная реальная себестоимость покрывает только {supplier_percent:.2f}% выручки"
            )
        if self._decimal(getattr(summary.quality, "ads_overallocated_spend", 0)) > 0:
            parts.append("рекламные расходы распределены с превышением")
        elif (
            self._float0(getattr(summary.kpis, "ads_source_spend", 0)) > 0
            and self._float0(
                getattr(summary.quality, "ads_allocation_percent_capped", 0)
            )
            < 95
        ):
            parts.append("рекламные расходы распределены не полностью")
        if (
            self._float0(getattr(summary.kpis, "unallocated_expense_ratio_percent", 0))
            > 5
        ):
            parts.append("слишком много общих расходов без привязки к карточкам")
        return (
            ", ".join(parts)
            if parts
            else (
                getattr(summary.answer, "main_problem", "")
                or "Итоговая прибыль подтверждена и готова к работе."
            )
        )

    def _owner_today_focus_from_summary(self, summary: Any, actions_page: Any) -> str:
        top_focus_count = int(
            getattr(actions_page, "summary", {}).get("top_focus_count", 0)
        )
        main_step = (getattr(summary.answer, "main_next_step", "") or "").strip()
        if main_step.endswith("."):
            main_step = main_step[:-1]
        if main_step and top_focus_count > 0:
            return f"{main_step}, затем выполните главные действия по магазину; в приоритете {top_focus_count} пунктов."
        if main_step:
            return f"{main_step}."
        actions = [
            item.what_to_do
            for item in getattr(summary, "next_actions", [])[:3]
            if getattr(item, "what_to_do", "")
        ]
        if actions and top_focus_count > 0:
            return f"{actions[0].rstrip('.')}, затем выполните главные действия по магазину; в приоритете {top_focus_count} пунктов."
        return "Сверьте сводку по деньгам магазина и выполните главные действия на сегодня."

    def _owner_trust_from_summary(self, summary: Any) -> OwnerDashboardTrust:
        status = self._owner_business_status_from_summary(summary)
        summary_trust = getattr(summary, "trust", None) or getattr(
            summary.meta, "data_trust", None
        )
        financial_final = bool(getattr(summary_trust, "financial_final", False))
        return OwnerDashboardTrust(
            status=status,
            business_status=getattr(summary.answer, "business_status", ""),
            trust_state=str(getattr(summary_trust, "trust_state", "") or status),
            business_trusted=bool(getattr(summary_trust, "business_trusted", False)),
            operational_trusted=bool(
                getattr(
                    summary_trust,
                    "operational_trusted",
                    getattr(
                        summary.meta.data_trust, "can_generate_business_actions", False
                    ),
                )
            ),
            financial_final=financial_final,
            cost_trust_policy=getattr(summary_trust, "cost_trust_policy", None),
            supplier_confirmed_revenue_coverage_percent=self._float0(
                getattr(summary_trust, "supplier_confirmed_revenue_coverage_percent", 0)
            ),
            operator_baseline_revenue_coverage_percent=self._float0(
                getattr(summary_trust, "operator_baseline_revenue_coverage_percent", 0)
            ),
            trusted_revenue_cost_coverage_percent=self._float0(
                getattr(summary_trust, "trusted_revenue_cost_coverage_percent", 0)
            ),
            financial_final_blockers_total=int(
                getattr(summary_trust, "financial_final_blockers_total", 0) or 0
            ),
            final_profit_blockers_total=int(
                getattr(summary_trust, "final_profit_blockers_total", 0) or 0
            ),
            all_open_issues_total=int(
                getattr(summary_trust, "all_open_issues_total", 0) or 0
            ),
            blocking_open_issues_total=int(
                getattr(summary_trust, "blocking_open_issues_total", 0) or 0
            ),
            blocked_reasons=list(getattr(summary_trust, "blocked_reasons", []) or []),
            confidence=getattr(summary_trust, "confidence", "")
            or (
                "high"
                if financial_final
                else "medium"
                if status == "operational_provisional"
                else "low"
            ),
            human_message=getattr(summary.answer, "short_text", "")
            or getattr(summary.answer, "title", ""),
        )

    def _owner_dashboard_item_from_action(
        self, action: Any, *, trust_state: str
    ) -> OwnerDashboardItem:
        linked_entity = dict(getattr(action, "linked_entity", {}) or {})
        return OwnerDashboardItem(
            sku_id=linked_entity.get("sku_id"),
            nm_id=linked_entity.get("nm_id"),
            vendor_code=linked_entity.get("vendor_code"),
            title=linked_entity.get("title") or getattr(action, "title", None),
            action_type=getattr(action, "action_type", ""),
            priority=getattr(action, "priority", ""),
            confidence=getattr(action, "confidence", ""),
            trust_state=trust_state,
            reason=getattr(action, "why", "") or getattr(action, "title", "") or "",
            expected_effect_amount=getattr(action, "expected_effect_amount", None),
        )

    async def owner_dashboard(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> OwnerDashboardRead:
        actual_from, actual_to = self._date_range(date_from, date_to)
        cache_key = (account_id, actual_from, actual_to)
        cached = self._owner_dashboard_cache.get(cache_key)
        if cached is not None:
            cached_at, cached_owner = cached
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.OWNER_DASHBOARD_CACHE_TTL_SECONDS
            ):
                return cached_owner.model_copy(
                    deep=True,
                    update={
                        "cache_status": "hit",
                    },
                )
        money = self._money_service()
        summary = await money.summary(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        actions_page = await money.today_actions(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            group_by="article",
            limit=100,
            offset=0,
        )
        owner_trust = self._owner_trust_from_summary(summary)
        owner_message = OwnerMessage(
            status=owner_trust.status,
            title=(
                "Финальная прибыль подтверждена, магазин готов к уверенным решениям."
                if owner_trust.financial_final
                else "Прибыль предварительная"
                if owner_trust.operational_trusted
                else "Сначала закройте блокеры данных, затем возвращайтесь к решениям по магазину"
            ),
            reason=self._owner_message_reason_from_summary(summary),
            today_focus=self._owner_today_focus_from_summary(summary, actions_page),
        )
        action_summary = OwnerActionSummary(
            critical=int(actions_page.summary.get("critical", 0)),
            high=int(actions_page.summary.get("high", 0)),
            medium=int(actions_page.summary.get("medium", 0)),
            low=int(actions_page.summary.get("low", 0)),
            data_blocked_count=int(getattr(summary.kpis, "blocked_data_sku_count", 0)),
            business_actionable_count=(
                int(actions_page.summary.get("money_saving", 0))
                + int(actions_page.summary.get("growth", 0))
                + int(actions_page.summary.get("watch", 0))
            ),
        )
        top_risk_actions = (
            list(actions_page.groups.global_blockers)
            + list(actions_page.groups.data_fix)
            + list(actions_page.groups.money_saving)
        )[:10]
        top_opportunity_actions = (
            list(actions_page.groups.growth) + list(actions_page.groups.watch)
        )[:10]
        next_action_items = actions_page.items[:5]
        notes: list[str] = []
        if getattr(summary.answer, "main_problem", ""):
            notes.append(summary.answer.main_problem)
        for risk in list(getattr(summary.risk_summary, "risks", []) or [])[:3]:
            notes.append(f"{risk.title}: {risk.business_impact}")
        if getattr(summary.store_answer, "where_money_went", ""):
            notes.append(summary.store_answer.where_money_went)
        if getattr(summary.store_answer, "where_money_is_now", ""):
            notes.append(summary.store_answer.where_money_is_now)
        revenue_value = getattr(summary.kpis, "revenue_final", None)
        if revenue_value is None:
            revenue_value = getattr(summary.kpis, "revenue", 0.0)
        ad_spend_value = getattr(summary.kpis, "ad_spend", 0.0)
        ad_spend_operational = getattr(summary.kpis, "ad_spend_operational", None)
        if ad_spend_operational is None:
            ad_spend_operational = ad_spend_value
        ad_spend_final = getattr(summary.kpis, "ad_spend_final", None)
        if ad_spend_final is None:
            ad_spend_final = ad_spend_value
        total_seller_costs = getattr(summary.kpis, "total_seller_costs", None)
        if total_seller_costs is None:
            total_seller_costs = getattr(summary.kpis, "total_seller_expenses", 0.0)
        result = OwnerDashboardRead(
            computed_at=getattr(summary, "computed_at", None),
            cache_status=str(getattr(summary, "cache_status", "miss") or "miss"),
            data_version_hash=getattr(summary, "data_version_hash", None),
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            trust_state=owner_trust.status,
            blocked_reasons=list(owner_trust.blocked_reasons),
            can_generate_business_actions=owner_trust.operational_trusted,
            business_trusted=owner_trust.business_trusted,
            operational_trusted=owner_trust.operational_trusted,
            financial_final=owner_trust.financial_final,
            cost_trust_policy=owner_trust.cost_trust_policy,
            supplier_confirmed_revenue_coverage_percent=owner_trust.supplier_confirmed_revenue_coverage_percent,
            operator_baseline_revenue_coverage_percent=owner_trust.operator_baseline_revenue_coverage_percent,
            trusted_revenue_cost_coverage_percent=owner_trust.trusted_revenue_cost_coverage_percent,
            financial_final_blockers_total=owner_trust.financial_final_blockers_total,
            final_profit_blockers_total=owner_trust.final_profit_blockers_total,
            all_open_issues_total=owner_trust.all_open_issues_total,
            blocking_open_issues_total=owner_trust.blocking_open_issues_total,
            trust=owner_trust,
            owner_message=owner_message,
            primary_message=owner_message.title,
            revenue=self._float0(revenue_value),
            revenue_final=self._float0(revenue_value),
            net_profit=self._float(summary.kpis.net_profit_after_overhead),
            margin_percent=self._float(summary.kpis.margin_after_overhead_percent),
            roi_percent=self._float(summary.kpis.roi_on_cogs_percent),
            ad_spend=self._float0(ad_spend_value),
            ad_spend_operational=self._float0(ad_spend_operational),
            ad_spend_finance=self._float0(
                getattr(summary.kpis, "ad_spend_finance", 0.0)
            ),
            ad_spend_final=self._float0(ad_spend_final),
            ad_spend_source=str(getattr(summary.kpis, "ad_spend_source", "") or ""),
            ad_spend_delta=self._float0(getattr(summary.kpis, "ad_spend_delta", 0.0)),
            stock_value=self._float0(summary.kpis.stock_value),
            unallocated_expenses=self._float0(summary.kpis.unallocated_expenses),
            total_wb_expenses=self._float0(
                getattr(summary.kpis, "wb_expenses_total", 0.0)
            ),
            seller_cogs=self._float0(getattr(summary.kpis, "seller_cogs", 0.0)),
            seller_other_expense=self._float0(
                getattr(summary.kpis, "seller_other_expense", 0.0)
            ),
            total_seller_expenses=self._float0(
                getattr(summary.kpis, "total_seller_expenses", 0.0)
            ),
            total_seller_costs=self._float0(total_seller_costs),
            additional_income=self._float0(
                getattr(summary.kpis, "additional_income", 0.0)
            ),
            expense_breakdown=getattr(summary, "expense_breakdown", None),
            profit_cascade=getattr(summary, "profit_cascade", None),
            net_profit_after_all_expenses=self._float(
                getattr(summary.kpis, "net_profit_after_all_expenses", None)
            ),
            expense_data_quality=str(
                getattr(summary.kpis, "expense_data_quality", "partial") or "partial"
            ),
            overstock_value=self._float0(summary.kpis.overstock_value),
            out_of_stock_risk_count=int(actions_page.summary.get("growth", 0)),
            negative_profit_sku_count=int(summary.kpis.negative_profit_sku_count),
            blocked_data_sku_count=int(summary.kpis.blocked_data_sku_count),
            action_summary=action_summary,
            top_risks=[
                self._owner_dashboard_item_from_action(
                    item, trust_state=owner_trust.status
                )
                for item in top_risk_actions
            ],
            top_opportunities=[
                self._owner_dashboard_item_from_action(
                    item, trust_state=owner_trust.status
                )
                for item in top_opportunity_actions
            ],
            next_actions_preview=[
                self._owner_dashboard_item_from_action(
                    item, trust_state=owner_trust.status
                )
                for item in next_action_items
            ],
            notes=notes,
        )
        self._owner_dashboard_cache[cache_key] = (
            utcnow(),
            result.model_copy(deep=True),
        )
        return result

    async def list_control_skus(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        search: str | None = None,
        sku_status: list[str] | None = None,
        trust_state: list[str] | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        preset: str | None = None,
        has_open_actions: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ControlTowerSkuRow]:
        actual_from, actual_to = self._date_range(date_from, date_to)
        control_rows, _, _, _ = await self._build_control_rows(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        cache_meta = self._control_cache_meta(
            account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        filtered = control_rows
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
            ]
        if sku_status:
            allowed = set(sku_status)
            filtered = [item for item in filtered if item.sku_status in allowed]
        if trust_state:
            allowed_trust = set(trust_state)
            filtered = [item for item in filtered if item.trust_state in allowed_trust]
        if has_open_actions is not None:
            filtered = [
                item
                for item in filtered
                if (item.open_action_count > 0) is has_open_actions
            ]
        if preset == "loss":
            filtered = [item for item in filtered if (item.net_profit or 0) < 0]
        elif preset == "oos":
            filtered = [item for item in filtered if item.sku_status == "PROTECT_STOCK"]
        elif preset == "overstock":
            filtered = [item for item in filtered if item.sku_status == "LIQUIDATE"]
        elif preset == "noads":
            filtered = [item for item in filtered if (item.ad_spend or 0) <= 0]
        elif preset == "toppriority":
            filtered = [item for item in filtered if item.priority_score >= 500]
        filtered = self._sort_control_rows(filtered, sort_by=sort_by, sort_dir=sort_dir)
        total = len(filtered)
        return self._with_page_cache_meta(
            Page(
                total=total,
                limit=limit,
                offset=offset,
                items=filtered[offset : offset + limit],
            ),
            cache_meta,
        )

    async def get_control_sku_detail(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int,
        date_from: date | None,
        date_to: date | None,
    ) -> ControlTowerSkuDetail:
        actual_from, actual_to = self._date_range(date_from, date_to)
        control_rows, price_rows, purchase_rows, _ = await self._build_control_rows(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        row = next((item for item in control_rows if item.sku_id == sku_id), None)
        if row is None:
            raise HTTPException(status_code=404, detail="Control Tower SKU not found")
        try:
            actions = list(
                (
                    await session.execute(
                        select(ActionRecommendation).where(
                            ActionRecommendation.account_id == account_id,
                            ActionRecommendation.sku_id == sku_id,
                        )
                    )
                ).scalars()
            )
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "action_recommendations"):
                actions = []
            else:
                raise
        notes = []
        if row.trust_state == TRUST_STATE_DATA_BLOCKED:
            notes.append(
                "Карточка все еще заблокирована правилами доверия к данным; автоматические бизнес-действия ограничены."
            )
        elif row.trust_state == TRUST_STATE_TEST_ONLY:
            notes.append(
                "Карточка пока использует предварительную экономику: работать можно, но подтвержденной реальной себестоимости еще нет."
            )
        if row.safe_price_gap is not None and row.safe_price_gap < 0:
            notes.append("Текущая цена продажи ниже расчетного порога безубыточности.")
        return ControlTowerSkuDetail(
            summary=row,
            actions=[self._action_read(item) for item in actions],
            price_safety=price_rows.get(sku_id),
            purchase_plan=purchase_rows.get(sku_id),
            notes=notes,
        )

    async def list_actions(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        status: str | None = None,
        action_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[ActionRecommendationListItem]:
        actual_from, actual_to = self._date_range(date_from, date_to)
        await self._ensure_actions_for_window(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        allowed_statuses = self._action_status_filter_values(status)
        stmt = select(ActionRecommendation).where(
            ActionRecommendation.account_id == account_id,
            ActionRecommendation.source_date_from == actual_from,
            ActionRecommendation.source_date_to == actual_to,
        )
        if allowed_statuses is not None:
            stmt = stmt.where(ActionRecommendation.status.in_(sorted(allowed_statuses)))
        if action_type is not None:
            stmt = stmt.where(ActionRecommendation.action_type == action_type)
        stmt = stmt.order_by(
            ActionRecommendation.priority.desc(),
            ActionRecommendation.expected_effect_amount.desc().nullslast(),
            ActionRecommendation.id.desc(),
        )
        total = int(
            (
                await session.execute(select(func.count()).select_from(stmt.subquery()))
            ).scalar_one()
        )
        rows = list((await session.execute(stmt.limit(limit).offset(offset))).scalars())
        return self._with_page_cache_meta(
            Page(
                total=total,
                limit=limit,
                offset=offset,
                items=[self._action_list_item(row) for row in rows],
            ),
            self._action_sync_meta(
                account_id=account_id, date_from=actual_from, date_to=actual_to
            ),
        )

    async def _ensure_actions_for_window(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> None:
        existing_result = await session.execute(
            select(func.count())
            .select_from(ActionRecommendation)
            .where(
                ActionRecommendation.account_id == account_id,
                ActionRecommendation.source_date_from == date_from,
                ActionRecommendation.source_date_to == date_to,
            )
        )
        if hasattr(existing_result, "scalar_one"):
            existing_count = int(existing_result.scalar_one())
        elif hasattr(existing_result, "scalar"):
            existing_count = int(existing_result.scalar() or 0)
        else:
            scalar_rows = list(existing_result.scalars())
            first_value = scalar_rows[0] if scalar_rows else 0
            if isinstance(first_value, (int, float, Decimal)):
                existing_count = int(first_value or 0)
            else:
                existing_count = len(scalar_rows)
        if existing_count > 0:
            self._action_sync_last_meta[
                self._action_sync_cache_key(
                    account_id=account_id, date_from=date_from, date_to=date_to
                )
            ] = {
                "computed_at": utcnow(),
                "cache_status": "bypassed",
                "data_version_hash": None,
            }
            return
        (
            control_rows,
            price_rows,
            purchase_rows,
            settings,
        ) = await self._build_control_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        trust_decision = await self._trust_decision(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            settings=settings,
        )
        await self._sync_recommendations_cached(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            control_rows=control_rows,
            price_rows=price_rows,
            purchase_rows=purchase_rows,
            trust_decision=trust_decision,
        )

    async def get_action_detail(
        self,
        session: AsyncSession,
        *,
        action_id: int,
    ) -> ActionRecommendationRead:
        action = await session.get(ActionRecommendation, action_id)
        if action is None:
            raise HTTPException(status_code=404, detail="Action not found")
        return self._action_read(action)

    async def update_action(
        self,
        session: AsyncSession,
        *,
        action_id: int,
        user_id: int | None,
        payload: ActionRecommendationUpdateRequest,
    ) -> ActionRecommendationRead:
        try:
            action = await session.get(ActionRecommendation, action_id)
        except ProgrammingError as exc:
            if self._is_missing_relation_error(
                exc, "action_recommendations", "action_recommendation_history"
            ):
                self._raise_storage_not_ready()
            raise
        if action is None:
            raise HTTPException(status_code=404, detail="Action not found")
        previous_status = action.status
        if payload.status is not None:
            action.status = payload.status
            if payload.status == "done":
                action.resolved_at = utcnow()
        if payload.assigned_to is not None:
            action.assigned_to = payload.assigned_to
        if payload.comment is not None:
            action.user_comment = payload.comment
        session.add(
            ActionRecommendationHistory(
                action_id=action.id,
                previous_status=previous_status,
                new_status=action.status,
                changed_by_user_id=user_id,
                comment=payload.comment,
                payload={"assignedTo": action.assigned_to},
            )
        )
        try:
            await session.flush()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(
                exc, "action_recommendations", "action_recommendation_history"
            ):
                self._raise_storage_not_ready()
            raise
        return self._action_read(action)

    async def bulk_update_actions(
        self,
        session: AsyncSession,
        *,
        ids: list[int],
        user_id: int | None,
        status: str,
        assigned_to: int | None = None,
        comment: str | None = None,
    ) -> int:
        updated = 0
        for action_id in ids:
            try:
                await self.update_action(
                    session,
                    action_id=action_id,
                    user_id=user_id,
                    payload=ActionRecommendationUpdateRequest(
                        status=status,
                        assigned_to=assigned_to,
                        comment=comment,
                    ),
                )
                updated += 1
            except HTTPException:
                continue
        return updated

    @staticmethod
    def _purchase_status_rank(status: str) -> int:
        return {
            "WAIT_DATA": 0,
            "LIQUIDATE": 1,
            "DO_NOT_BUY": 2,
            "REORDER": 3,
            "PROTECT_STOCK": 4,
            "WATCH": 5,
        }.get(status, 6)

    @staticmethod
    def _aggregate_purchase_trust_state(states: list[str]) -> str:
        unique = set(states)
        if unique == {TRUST_STATE_DATA_BLOCKED}:
            return TRUST_STATE_DATA_BLOCKED
        if TRUST_STATE_TEST_ONLY in unique or (
            TRUST_STATE_DATA_BLOCKED in unique and TRUST_STATE_TRUSTED in unique
        ):
            return TRUST_STATE_TEST_ONLY
        if TRUST_STATE_TRUSTED in unique and len(unique) == 1:
            return TRUST_STATE_TRUSTED
        return TRUST_STATE_TEST_ONLY if unique else TRUST_STATE_DATA_BLOCKED

    @classmethod
    def _normalize_purchase_wait_data_reasons(cls, reasons: list[str]) -> list[str]:
        normalized = {
            str(reason).strip().lower()
            for reason in reasons
            if isinstance(reason, str) and str(reason).strip()
        }
        return [
            reason
            for reason in cls.PURCHASE_WAIT_DATA_REASON_ORDER
            if reason in normalized
        ]

    @classmethod
    def _purchase_wait_data_reason_from_code(cls, code: str | None) -> str | None:
        normalized = str(code or "").strip().lower()
        if not normalized:
            return None
        return cls.PURCHASE_WAIT_DATA_REASON_BY_CODE.get(normalized)

    @classmethod
    def _purchase_wait_data_reason_from_text(
        cls,
        *,
        risk: str | None = None,
        reason: str | None = None,
        main_reason: str | None = None,
    ) -> str:
        haystack = " ".join(
            part.strip().lower()
            for part in (
                risk or "",
                reason or "",
                main_reason or "",
            )
            if isinstance(part, str) and part.strip()
        )
        if any(
            token in haystack
            for token in ("finance", "финанс", "audit", "расхожден", "dq_issues")
        ):
            return "finance"
        if any(
            token in haystack
            for token in ("cost", "себестоим", "manual_cost", "supplier_cost")
        ):
            return "cost"
        if any(
            token in haystack for token in ("velocity", "скорост", "оборач", "turnover")
        ):
            return "velocity"
        if any(
            token in haystack for token in ("sales", "продаж", "profit_data_missing")
        ):
            return "sales"
        if any(
            token in haystack for token in ("stock", "остат", "stocks_", "warehouse")
        ):
            return "stock"
        return "sales"

    @classmethod
    def _purchase_wait_data_reasons(
        cls,
        *,
        status: str,
        blocked_reasons: list[str] | None = None,
        risk: str | None = None,
        reason: str | None = None,
        main_reason: str | None = None,
    ) -> list[str]:
        if str(status or "").strip().upper() != "WAIT_DATA":
            return []
        collected: list[str] = []
        for code in blocked_reasons or []:
            mapped = cls._purchase_wait_data_reason_from_code(code)
            if mapped is not None:
                collected.append(mapped)
        mapped_risk = cls._purchase_wait_data_reason_from_code(risk)
        if mapped_risk is not None:
            collected.append(mapped_risk)
        normalized = cls._normalize_purchase_wait_data_reasons(collected)
        if normalized:
            return normalized
        return [
            cls._purchase_wait_data_reason_from_text(
                risk=risk,
                reason=reason,
                main_reason=main_reason,
            )
        ]

    @classmethod
    def _purchase_wait_data_reasons_from_item(cls, item: PurchasePlanRow) -> list[str]:
        stored: list[str] = []
        for source in (item.wait_data_reasons, item.missing_data, item.missing_fields):
            stored.extend(source or [])
        normalized = cls._normalize_purchase_wait_data_reasons(stored)
        if normalized:
            return normalized
        return cls._purchase_wait_data_reasons(
            status=item.status,
            risk=item.risk,
            reason=item.reason,
            main_reason=item.main_reason,
        )

    @staticmethod
    def _merge_purchase_variant_field(values: list[str | None]) -> str | None:
        normalized = [
            str(value).strip()
            if isinstance(value, str) and str(value).strip()
            else None
            for value in values
        ]
        if not normalized or all(value is None for value in normalized):
            return None
        first = normalized[0]
        if all(value == first for value in normalized):
            return first
        return "mixed"

    def _purchase_plan_summary(
        self,
        *,
        items: list[PurchasePlanRow],
        page_items: list[PurchasePlanRow],
    ) -> PurchasePlanSummary:
        reason_counts = PurchasePlanWaitDataReasonCounts()
        reorder_count = 0
        liquidate_count = 0
        do_not_buy_count = 0
        watch_count = 0
        wait_data_count = 0
        required_cash_total = Decimal("0")
        expected_profit_total = Decimal("0")
        stock_value_total = Decimal("0")

        for item in items:
            status = str(item.status or "").strip().upper()
            stock_value_total += self._decimal(
                item.stock_value if item.stock_value is not None else item.frozen_cash
            )
            if status == "REORDER":
                reorder_count += 1
                required_cash_total += self._decimal(item.required_cash)
                expected_profit_total += self._decimal(item.expected_profit)
            elif status == "LIQUIDATE":
                liquidate_count += 1
            elif status in {"DO_NOT_BUY", "DO_NOT_REORDER"}:
                do_not_buy_count += 1
            elif status == "WAIT_DATA":
                wait_data_count += 1
                for bucket in self._purchase_wait_data_reasons_from_item(item):
                    setattr(
                        reason_counts,
                        bucket,
                        int(getattr(reason_counts, bucket, 0)) + 1,
                    )
            else:
                watch_count += 1

        return PurchasePlanSummary(
            total_count=len(items),
            page_count=len(page_items),
            total_positions=len(items),
            total_items=len(items),
            reorder_count=reorder_count,
            liquidate_count=liquidate_count,
            do_not_buy_count=do_not_buy_count,
            watch_count=watch_count,
            wait_data_count=wait_data_count,
            required_cash_total=self._float0(required_cash_total),
            expected_profit_total=self._float0(expected_profit_total),
            stock_value_total=self._float0(stock_value_total),
            frozen_cash_total=self._float0(stock_value_total),
            total_required_cash=self._float0(required_cash_total),
            total_expected_profit=self._float0(expected_profit_total),
            total_stock_value=self._float0(stock_value_total),
            wait_data_reason_counts=reason_counts,
        )

    def _filter_purchase_plan_items(
        self,
        items: list[PurchasePlanRow],
        *,
        status_filter: str | None,
        search: str | None,
        profit_filter: str | None,
        data_filter: str | None,
        stock_filter: str | None,
    ) -> list[PurchasePlanRow]:
        filtered = list(items)
        normalized_status = str(status_filter or "all").strip().upper()
        if normalized_status and normalized_status != "ALL":
            if normalized_status == "ACTIONABLE":
                actionable = {
                    "REORDER",
                    "LIQUIDATE",
                    "DO_NOT_BUY",
                    "DO_NOT_REORDER",
                    "PROTECT_STOCK",
                }
                filtered = [
                    item
                    for item in filtered
                    if str(item.status or "").upper() in actionable
                ]
            elif normalized_status == "DO_NOT_BUY":
                filtered = [
                    item
                    for item in filtered
                    if str(item.status or "").upper()
                    in {"DO_NOT_BUY", "DO_NOT_REORDER"}
                ]
            else:
                filtered = [
                    item
                    for item in filtered
                    if str(item.status or "").upper() == normalized_status
                ]

        query = str(search or "").strip().lower()
        if query:

            def matches_search(item: PurchasePlanRow) -> bool:
                values = [
                    item.nm_id,
                    item.sku_id,
                    item.vendor_code,
                    item.barcode,
                    item.title,
                    item.brand,
                    item.subject_name,
                    item.tech_size,
                ]
                return any(
                    query in str(value).lower()
                    for value in values
                    if value not in (None, "")
                )

            filtered = [item for item in filtered if matches_search(item)]

        normalized_profit = str(profit_filter or "all").strip().lower()
        if normalized_profit != "all":

            def profit_value(item: PurchasePlanRow) -> float | None:
                if item.net_profit_per_unit is not None:
                    return float(item.net_profit_per_unit)
                return None

            if normalized_profit == "profitable":
                filtered = [
                    item
                    for item in filtered
                    if profit_value(item) is not None and profit_value(item) > 0
                ]
            elif normalized_profit == "loss":
                filtered = [
                    item
                    for item in filtered
                    if profit_value(item) is not None and profit_value(item) < 0
                ]
            elif normalized_profit == "unknown":
                filtered = [item for item in filtered if profit_value(item) is None]

        normalized_data = str(data_filter or "all").strip().lower()
        if normalized_data != "all":
            if normalized_data == "final":
                filtered = [item for item in filtered if item.financial_final is True]
            elif normalized_data == "estimated":
                filtered = [
                    item
                    for item in filtered
                    if item.financial_final is False and not item.wait_data_reasons
                ]
            elif normalized_data == "missing":
                filtered = [
                    item
                    for item in filtered
                    if str(item.status or "").upper() == "WAIT_DATA"
                    or bool(
                        item.wait_data_reasons
                        or item.missing_data
                        or item.missing_fields
                    )
                ]

        normalized_stock = str(stock_filter or "all").strip().lower()
        if normalized_stock != "all":

            def target_days(item: PurchasePlanRow) -> float:
                return float((item.lead_time_days or 0) + (item.safety_days or 0))

            if normalized_stock == "out":
                filtered = [
                    item for item in filtered if float(item.available_stock or 0) <= 0
                ]
            elif normalized_stock == "low":
                filtered = [
                    item
                    for item in filtered
                    if str(item.status or "").upper() == "REORDER"
                    or (
                        item.days_of_stock is not None
                        and target_days(item) > 0
                        and float(item.days_of_stock) < target_days(item)
                    )
                ]
            elif normalized_stock == "overstock":
                filtered = [
                    item
                    for item in filtered
                    if str(item.status or "").upper() == "LIQUIDATE"
                    or (
                        item.days_of_stock is not None
                        and float(item.days_of_stock) >= 90
                    )
                ]
            elif normalized_stock == "in_transit":
                filtered = [
                    item for item in filtered if float(item.in_transit_qty or 0) > 0
                ]

        return filtered

    def _sort_purchase_plan_items(
        self,
        items: list[PurchasePlanRow],
        *,
        sort_by: str | None,
        sort_dir: str,
    ) -> None:
        normalized = str(sort_by or "priority").strip().lower()
        descending = sort_dir != "asc"

        attr_map = {
            "recommended_qty": "recommended_qty",
            "required_cash": "required_cash",
            "stock_value": "stock_value",
            "frozen_cash": "frozen_cash",
            "available_stock": "available_stock",
            "sales_30d": "sales_30d",
            "sales_velocity": "sales_velocity_daily",
            "trend": "sales_trend_percent",
            "unit_profit": "net_profit_per_unit",
            "expected_profit": "expected_profit",
            "days_of_stock": "days_of_stock",
            "margin": "margin_percent",
            "roi": "roi_percent",
        }

        attr_name = attr_map.get(normalized)
        if attr_name:

            def numeric_key(item: PurchasePlanRow) -> tuple[int, float]:
                value = getattr(item, attr_name, None)
                if value is None:
                    return (1, 0.0)
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    return (1, 0.0)
                return (0, -number if descending else number)

            items.sort(key=numeric_key)
            return

        if normalized in {"title", "name"}:
            items.sort(
                key=lambda item: str(item.title or item.vendor_code or "").lower(),
                reverse=descending,
            )
            return

        if normalized == "vendor_code":
            items.sort(
                key=lambda item: str(item.vendor_code or item.barcode or "").lower(),
                reverse=descending,
            )
            return

        items.sort(
            key=lambda item: (
                self._purchase_status_rank(item.status),
                -float(item.money_effect.get("affected_stock_value") or 0),
                -float(item.required_cash or 0),
            ),
        )

    def _group_purchase_rows_by_article(
        self,
        *,
        control_rows: list[ControlTowerSkuRow],
        purchase_rows: dict[int, PurchasePlanRow],
        settings: dict[str, Any],
    ) -> list[PurchasePlanRow]:
        control_by_sku = {
            int(row.sku_id): row for row in control_rows if row.sku_id is not None
        }
        grouped: dict[tuple[str, int], list[PurchasePlanRow]] = defaultdict(list)
        for row in purchase_rows.values():
            if row.nm_id is not None:
                grouped[("nm", int(row.nm_id))].append(row)
            elif row.sku_id is not None:
                grouped[("sku", int(row.sku_id))].append(row)

        aggregated_rows: list[PurchasePlanRow] = []
        lead_time_days = int(settings.get("lead_time_days") or 14)
        safety_days = int(settings.get("safety_days") or 7)
        overstock_threshold_days = int(settings.get("overstock_threshold_days") or 90)
        min_profit_threshold = Decimal(str(settings.get("min_profit_threshold") or 0))
        target_margin_percent = Decimal(
            str(settings.get("target_margin_rate") or 0.2)
        ) * Decimal("100")
        target_roi_percent = Decimal(str(settings.get("target_roi_percent") or 30))
        pack_multiple = max(int(settings.get("pack_multiple") or 1), 1)

        for (_group_type, _entity_id), variants in grouped.items():
            if len(variants) == 1 and variants[0].nm_id is None:
                aggregated_rows.append(variants[0])
                continue
            detail_rows: list[dict[str, Any]] = []
            blocked_reasons: list[str] = []
            trust_states: list[str] = []
            aggregated_wait_data_reasons: list[str] = []
            variant_cost_sources: list[str | None] = []
            variant_cost_truth_levels: list[str | None] = []
            sales_velocity = Decimal("0")
            available_stock = Decimal("0")
            in_transit = Decimal("0")
            stock_value = Decimal("0")
            revenue = Decimal("0")
            expected_profit = Decimal("0")
            weighted_margin_numerator = Decimal("0")
            weighted_roi_numerator = Decimal("0")
            weighted_margin_denominator = Decimal("0")
            weighted_roi_denominator = Decimal("0")
            sales_7d_sum = 0
            sales_14d_sum = 0
            sales_30d_sum = 0
            recommended_qty_sum = 0
            required_cash_sum = Decimal("0")
            unit_profit_values: list[Decimal] = []
            warehouse_details: list[dict[str, Any]] = []
            final_profit_allowed = True
            dominant_row = variants[0]

            for item in variants:
                trust_states.append(item.trust_state)
                if item.reason and self._purchase_status_rank(
                    item.status
                ) < self._purchase_status_rank(dominant_row.status):
                    dominant_row = item
                available_stock += Decimal(str(item.available_stock or 0))
                in_transit += Decimal(str(item.in_transit_qty or 0))
                sales_velocity += Decimal(str(item.sales_velocity_daily or 0))
                sales_7d_sum += int(item.sales_7d or 0)
                sales_14d_sum += int(item.sales_14d or 0)
                sales_30d_sum += int(item.sales_30d or 0)
                recommended_qty_sum += int(item.recommended_qty or 0)
                required_cash_sum += Decimal(str(item.required_cash or 0))
                if item.net_profit_per_unit is not None:
                    unit_profit_values.append(Decimal(str(item.net_profit_per_unit)))
                warehouse_details.extend(list(item.warehouse_breakdown or []))
                if item.financial_final is False:
                    final_profit_allowed = False
                aggregated_wait_data_reasons.extend(
                    self._purchase_wait_data_reasons_from_item(item)
                )
                variant_cost_sources.append(item.cost_source)
                variant_cost_truth_levels.append(
                    item.cost_truth_level or item.cost_truth
                )
                control_row = (
                    control_by_sku.get(int(item.sku_id))
                    if item.sku_id is not None
                    else None
                )
                if control_row is not None:
                    blocked_reasons.extend(list(control_row.blocked_reasons or []))
                    stock_value += Decimal(str(control_row.stock_value or 0))
                    revenue += Decimal(str(control_row.revenue or 0))
                    expected_profit += Decimal(str(control_row.net_profit or 0))
                    if control_row.margin_percent is not None:
                        weighted_margin_numerator += Decimal(
                            str(control_row.margin_percent)
                        ) * Decimal(str(control_row.revenue or 0))
                        weighted_margin_denominator += Decimal(
                            str(control_row.revenue or 0)
                        )
                    if control_row.roi_percent is not None:
                        weighted_roi_numerator += Decimal(
                            str(control_row.roi_percent)
                        ) * Decimal(str(control_row.revenue or 0))
                        weighted_roi_denominator += Decimal(
                            str(control_row.revenue or 0)
                        )
                    final_profit_allowed = final_profit_allowed and bool(
                        control_row.final_profit_allowed
                    )
                detail_rows.append(
                    {
                        "sku_id": item.sku_id,
                        "nm_id": item.nm_id,
                        "vendor_code": item.vendor_code,
                        "title": item.title,
                        "brand": item.brand,
                        "subject_name": item.subject_name,
                        "barcode": item.barcode,
                        "tech_size": item.tech_size,
                        "status": item.status,
                        "available_stock": item.available_stock,
                        "in_transit_qty": item.in_transit_qty,
                        "days_of_stock": item.days_of_stock,
                        "sales_7d": item.sales_7d,
                        "sales_14d": item.sales_14d,
                        "sales_30d": item.sales_30d,
                        "sales_trend_units": item.sales_trend_units,
                        "sales_trend_percent": item.sales_trend_percent,
                        "sales_trend_direction": item.sales_trend_direction,
                        "recommended_qty": item.recommended_qty,
                        "required_cash": item.required_cash,
                        "stock_value": item.stock_value,
                        "frozen_cash": item.frozen_cash,
                        "unit_cost": item.unit_cost,
                        "net_profit_per_unit": item.net_profit_per_unit,
                        "margin_percent": item.margin_percent,
                        "roi_percent": item.roi_percent,
                        "confidence": item.confidence,
                        "financial_final": item.financial_final,
                        "missing_data": list(item.missing_data),
                        "missing_fields": list(item.missing_fields),
                        "wait_data_reasons": list(item.wait_data_reasons),
                        "cost_source": item.cost_source,
                        "cost_truth": item.cost_truth,
                        "cost_truth_level": item.cost_truth_level,
                    }
                )

            group_trust_state = self._aggregate_purchase_trust_state(trust_states)
            days_of_stock = None
            if sales_velocity > 0:
                days_of_stock = available_stock / sales_velocity
            group_margin = (
                (weighted_margin_numerator / weighted_margin_denominator)
                if weighted_margin_denominator > 0
                else None
            )
            group_roi = (
                (weighted_roi_numerator / weighted_roi_denominator)
                if weighted_roi_denominator > 0
                else None
            )
            previous_7d_sales = max(sales_14d_sum - sales_7d_sum, 0)
            sales_trend_units = sales_7d_sum - previous_7d_sales
            sales_trend_percent = self._safe_percent(
                sales_trend_units, previous_7d_sales
            )
            sales_trend_direction = self._trend_direction(sales_trend_units)
            group_unit_profit = (
                sum(unit_profit_values, start=Decimal("0"))
                / Decimal(str(len(unit_profit_values)))
                if unit_profit_values
                else None
            )
            region_breakdown = self._region_breakdown_from_stock_details(
                warehouse_details
            )
            required_stock = sales_velocity * Decimal(str(lead_time_days + safety_days))
            reorder_qty = max(
                Decimal("0"), required_stock - available_stock - in_transit
            )
            reorder_qty_rounded = (
                int(ceil(float(reorder_qty) / pack_multiple) * pack_multiple)
                if reorder_qty > 0
                else 0
            )
            decision = self._purchase_status_and_reason(
                trust_state=group_trust_state,
                estimated_profit=expected_profit,
                days_of_stock=days_of_stock,
                available_stock_qty=available_stock,
                lead_time_days=lead_time_days,
                safety_days=safety_days,
                overstock_threshold_days=overstock_threshold_days,
                blocked_reasons=list(dict.fromkeys(blocked_reasons)),
                recommended_qty=reorder_qty_rounded
                if reorder_qty_rounded > 0
                else recommended_qty_sum,
                in_transit_qty=in_transit,
                sales_velocity_daily=sales_velocity,
                stock_value=stock_value,
                margin_percent=group_margin,
                roi_percent=group_roi,
                min_profit_threshold=min_profit_threshold,
                target_margin_percent=target_margin_percent,
                target_roi_percent=target_roi_percent,
                final_profit_allowed=final_profit_allowed,
            )
            merged_wait_data_reasons = self._normalize_purchase_wait_data_reasons(
                aggregated_wait_data_reasons
            )
            if not merged_wait_data_reasons:
                merged_wait_data_reasons = self._purchase_wait_data_reasons(
                    status=decision.status,
                    blocked_reasons=list(dict.fromkeys(blocked_reasons)),
                    risk=decision.risk,
                    reason=decision.reason,
                    main_reason=decision.reason,
                )
            merged_cost_source = self._merge_purchase_variant_field(
                variant_cost_sources
            )
            merged_cost_truth_level = self._merge_purchase_variant_field(
                variant_cost_truth_levels
            )
            final_recommended_qty = (
                (
                    reorder_qty_rounded
                    if reorder_qty_rounded > 0
                    else recommended_qty_sum
                )
                if decision.status == "REORDER"
                else 0
            )
            final_required_cash = (
                float(required_cash_sum) if decision.status == "REORDER" else 0.0
            )
            money_effect: dict[str, Any] = {}
            if decision.status == "LIQUIDATE":
                affected_stock_value = self._float0(stock_value)
                money_effect = {
                    "affected_stock_value": affected_stock_value,
                    "expected_cash_release": affected_stock_value,
                    "expected_profit_impact": None,
                }
            elif decision.status == "REORDER":
                money_effect = {
                    "affected_stock_value": self._float0(stock_value),
                    "expected_cash_release": 0.0,
                    "expected_profit_impact": self._float(expected_profit),
                }
            aggregated_rows.append(
                PurchasePlanRow(
                    sku_id=dominant_row.sku_id if len(variants) == 1 else None,
                    nm_id=dominant_row.nm_id,
                    vendor_code=dominant_row.vendor_code,
                    title=dominant_row.title,
                    brand=dominant_row.brand,
                    subject_name=dominant_row.subject_name,
                    barcode=dominant_row.barcode if len(variants) == 1 else None,
                    tech_size=dominant_row.tech_size if len(variants) == 1 else None,
                    photo_url=dominant_row.photo_url or dominant_row.image_url,
                    image_url=dominant_row.image_url or dominant_row.photo_url,
                    status=decision.status,
                    decision=decision.status,
                    trust_state=group_trust_state,
                    sales_velocity_daily=self._float0(sales_velocity),
                    sales_7d=sales_7d_sum,
                    sales_14d=sales_14d_sum,
                    sales_30d=sales_30d_sum,
                    sales_trend_units=sales_trend_units,
                    sales_trend_percent=sales_trend_percent,
                    sales_trend_direction=sales_trend_direction,
                    days_since_last_sale=min(
                        [
                            int(item.days_since_last_sale)
                            for item in variants
                            if item.days_since_last_sale is not None
                        ],
                        default=None,
                    ),
                    available_stock=self._float0(available_stock),
                    in_transit_qty=self._float0(in_transit),
                    days_of_stock=self._float(days_of_stock),
                    lead_time_days=lead_time_days,
                    safety_days=safety_days,
                    recommended_qty=final_recommended_qty,
                    required_cash=final_required_cash,
                    expected_profit=self._float(expected_profit),
                    stock_value=self._float0(stock_value),
                    frozen_cash=self._float0(stock_value),
                    current_price=dominant_row.current_price,
                    current_discounted_price=dominant_row.current_discounted_price,
                    avg_sale_price=dominant_row.avg_sale_price,
                    unit_cost=dominant_row.unit_cost,
                    net_profit_per_unit=self._float(group_unit_profit),
                    margin_percent=self._float(group_margin),
                    roi_percent=self._float(group_roi),
                    is_profitable=expected_profit > Decimal("0"),
                    risk=decision.risk,
                    reason=decision.reason,
                    main_reason=decision.reason,
                    missing_data=list(merged_wait_data_reasons),
                    missing_fields=list(merged_wait_data_reasons),
                    wait_data_reasons=list(merged_wait_data_reasons),
                    next_step=decision.next_step,
                    confidence=decision.confidence,
                    decision_confidence=decision.confidence,
                    cost_source=merged_cost_source,
                    cost_truth=merged_cost_truth_level,
                    cost_truth_level=merged_cost_truth_level,
                    financial_final=decision.financial_final,
                    money_effect=money_effect,
                    variant_count=len(variants),
                    size_breakdown=detail_rows,
                    region_breakdown=region_breakdown,
                    warehouse_breakdown=warehouse_details,
                )
            )
        return aggregated_rows

    async def list_purchase_plan(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        group_by: str = "article",
        include_blocked: bool = True,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        status_filter: str | None = None,
        search: str | None = None,
        profit_filter: str | None = None,
        data_filter: str | None = None,
        stock_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> PurchasePlanPage:
        actual_from, actual_to = self._date_range(date_from, date_to)
        (
            control_rows,
            _price_rows,
            purchase_rows,
            settings,
        ) = await self._build_control_rows(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        cache_meta = self._control_cache_meta(
            account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        items = (
            list(purchase_rows.values())
            if group_by == "sku"
            else self._group_purchase_rows_by_article(
                control_rows=control_rows,
                purchase_rows=purchase_rows,
                settings=settings,
            )
        )
        items = [
            item
            if isinstance(item, PurchasePlanRow)
            else PurchasePlanRow.model_validate(
                vars(item) if hasattr(item, "__dict__") else item
            )
            for item in items
        ]
        if not include_blocked:
            items = [
                item for item in items if item.trust_state != TRUST_STATE_DATA_BLOCKED
            ]
        summary_items = list(items)
        items = self._filter_purchase_plan_items(
            items,
            status_filter=status_filter,
            search=search,
            profit_filter=profit_filter,
            data_filter=data_filter,
            stock_filter=stock_filter,
        )
        self._sort_purchase_plan_items(items, sort_by=sort_by, sort_dir=sort_dir)
        total = len(items)
        page_items = items[offset : offset + limit]
        return self._with_page_cache_meta(
            PurchasePlanPage(
                total=total,
                limit=limit,
                offset=offset,
                items=page_items,
                summary=self._purchase_plan_summary(
                    items=summary_items, page_items=page_items
                ),
            ),
            cache_meta,
        )

    async def list_price_safety(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        only_risk: bool = False,
        search: str | None = None,
        status: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> PriceSafetyPage:
        actual_from, actual_to = self._date_range(date_from, date_to)
        _rows, price_rows, _purchase_rows, _ = await self._build_control_rows(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        cache_meta = self._control_cache_meta(
            account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        health = await self.dashboard.data_health(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        items = list(price_rows.values())
        normalized_status = str(status or "").strip().lower()
        if only_risk:
            normalized_status = "risk"
        if search and search.strip():
            query = search.strip().lower()
            items = [
                item
                for item in items
                if query in str(item.nm_id or "").lower()
                or query in str(item.sku_id or "").lower()
                or query in str(item.vendor_code or "").lower()
                or query in str(item.title or "").lower()
            ]
        if normalized_status and normalized_status != "all":

            def matches_status(item: PriceSafetyRow) -> bool:
                state = str(item.calculation_state or "").lower()
                safe_gap = item.safe_price_gap
                target_gap = item.target_margin_gap
                if (
                    target_gap is None
                    and item.reference_price is not None
                    and item.target_margin_price is not None
                ):
                    target_gap = item.reference_price - item.target_margin_price
                if normalized_status in {"risk", "below_break_even"}:
                    return safe_gap is not None and safe_gap < 0
                if normalized_status in {"below_target", "margin_gap"}:
                    return (
                        state == "computed"
                        and target_gap is not None
                        and target_gap < 0
                    )
                if normalized_status in {"margin_watch", "target_watch"}:
                    return (
                        state == "computed"
                        and (safe_gap is None or safe_gap >= 0)
                        and target_gap is not None
                        and target_gap < 0
                    )
                if normalized_status in {"safe", "healthy"}:
                    return (
                        state == "computed"
                        and safe_gap is not None
                        and safe_gap >= 0
                        and (target_gap is None or target_gap >= 0)
                    )
                if normalized_status in {"not_computable", "blocked", "data"}:
                    return state != "computed"
                if normalized_status in {"price_review", "review"}:
                    return (
                        str(item.action_hint or "").upper() == "PRICE_INCREASE_REVIEW"
                    )
                return True

            items = [item for item in items if matches_status(item)]
        normalized_sort = str(sort_by or "risk").strip().lower()
        reverse = str(sort_dir or "asc").lower() == "desc"

        def sort_value(item: PriceSafetyRow) -> Any:
            if normalized_sort in {"target_gap", "target_margin_gap"}:
                value = item.target_margin_gap
                if (
                    value is None
                    and item.reference_price is not None
                    and item.target_margin_price is not None
                ):
                    value = item.reference_price - item.target_margin_price
                return value if value is not None else float("inf")
            if normalized_sort in {"margin", "estimated_margin"}:
                return (
                    item.estimated_margin_at_current_price
                    if item.estimated_margin_at_current_price is not None
                    else float("-inf")
                )
            if normalized_sort in {"price", "reference_price"}:
                return (
                    item.reference_price
                    if item.reference_price is not None
                    else float("-inf")
                )
            if normalized_sort in {"nm_id", "nm"}:
                return item.nm_id if item.nm_id is not None else float("inf")
            if normalized_sort in {"not_computable", "state"}:
                return str(item.calculation_state or "")
            return (
                item.safe_price_gap if item.safe_price_gap is not None else float("inf")
            )

        items = sorted(
            items,
            key=sort_value,
            reverse=reverse,
        )
        await self._attach_wb_price_signals(session, account_id=account_id, items=items)
        await self._attach_wb_promotion_signals(
            session, account_id=account_id, items=items
        )
        total = len(items)
        page = PriceSafetyPage(
            total=total,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
            summary=self._price_safety_summary(items),
            operational_trusted=bool(getattr(health, "operational_trusted", False)),
            business_trusted=bool(getattr(health, "business_trusted", False)),
            financial_final=bool(getattr(health, "financial_final", False)),
            trust_state=str(getattr(health, "trust_state", "unknown") or "unknown"),
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
        )
        page.computed_at = cache_meta.get("computed_at")
        page.cache_status = str(cache_meta.get("cache_status") or "miss")
        page.data_version_hash = cache_meta.get("data_version_hash")
        return page

    async def simulate_price(
        self,
        session: AsyncSession,
        *,
        payload: PriceSimulationRequest,
    ) -> PriceSimulationResponse:
        actual_from, actual_to = self._date_range(payload.date_from, payload.date_to)
        control_rows, price_rows, _purchase_rows, _ = await self._build_control_rows(
            session,
            account_id=payload.account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        target_row = None
        if payload.sku_id is not None:
            target_row = next(
                (item for item in control_rows if item.sku_id == payload.sku_id), None
            )
        elif payload.nm_id is not None:
            target_row = next(
                (item for item in control_rows if item.nm_id == payload.nm_id), None
            )
        if target_row is None:
            raise HTTPException(
                status_code=404, detail="SKU for price simulation not found"
            )
        price_row = price_rows.get(int(target_row.sku_id or 0))
        if price_row is None:
            raise HTTPException(
                status_code=400, detail="Price safety data is unavailable for this SKU"
            )
        baseline_units = Decimal("1")
        if target_row.revenue > 0 and target_row.net_profit is not None:
            average_price = self._decimal(
                price_row.average_sale_price
                or price_row.current_discounted_price
                or payload.price
                or 0
            )
            if average_price > 0:
                baseline_units = max(
                    self._decimal(target_row.revenue) / average_price, Decimal("1")
                )
        unit_drop_multiplier = Decimal("1") - (
            Decimal(str(payload.sales_drop_assumption_percent or 0)) / Decimal("100")
        )
        simulated_units = baseline_units * max(unit_drop_multiplier, Decimal("0"))
        simulated_revenue = Decimal(str(payload.price)) * simulated_units
        break_even = self._decimal(price_row.break_even_price)
        target_margin_price = self._decimal(price_row.target_margin_price)
        expected_profit = (
            (Decimal(str(payload.price)) - break_even) * simulated_units
            if break_even > 0
            else None
        )
        expected_margin = (
            float((expected_profit / simulated_revenue) * Decimal("100"))
            if expected_profit is not None and simulated_revenue > 0
            else None
        )
        expected_roi = None
        if (
            price_row.break_even_price is not None
            and break_even > 0
            and expected_profit is not None
        ):
            expected_roi = (
                float(
                    (expected_profit / (break_even * simulated_units)) * Decimal("100")
                )
                if simulated_units > 0
                else None
            )
        risk_flag = None
        if (
            price_row.break_even_price is not None
            and Decimal(str(payload.price)) < break_even
        ):
            risk_flag = "below_break_even"
        elif (
            price_row.target_margin_price is not None
            and Decimal(str(payload.price)) < target_margin_price
        ):
            risk_flag = "below_target_margin"
        return PriceSimulationResponse(
            sku_id=target_row.sku_id,
            nm_id=target_row.nm_id,
            simulated_price=payload.price,
            expected_revenue=float(simulated_revenue),
            expected_profit=float(expected_profit)
            if expected_profit is not None
            else None,
            expected_margin_percent=expected_margin,
            expected_roi_percent=expected_roi,
            break_even_price=price_row.break_even_price,
            target_margin_price=price_row.target_margin_price,
            risk_flag=risk_flag,
            estimated=price_row.estimated,
            confidence=price_row.confidence,
        )

    async def list_ads_efficiency(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        campaign_id: int | None = None,
        min_drr_percent: float | None = None,
        max_drr_percent: float | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> AdsEfficiencyPage:
        actual_from, actual_to = self._date_range(date_from, date_to)
        control_rows, _price_rows, _purchase_rows, _ = await self._build_control_rows(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        cache_meta = self._control_cache_meta(
            account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        ads_stats_by_nm = await self._load_ads_efficiency_stats_by_nm(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            campaign_id=campaign_id,
        )
        allowed_nm_ids: set[int] | None = (
            set(ads_stats_by_nm.keys()) if campaign_id is not None else None
        )
        rows_with_ads = [
            row
            for row in control_rows
            if self._decimal(row.ad_spend) > 0
            and (
                allowed_nm_ids is None
                or (row.nm_id is not None and int(row.nm_id) in allowed_nm_ids)
            )
        ]
        rows_by_nm: dict[int | None, list[Any]] = defaultdict(list)
        for row in rows_with_ads:
            rows_by_nm[int(row.nm_id) if row.nm_id is not None else None].append(row)
        items: list[AdsEfficiencyRow] = []
        for nm_id, nm_rows in rows_by_nm.items():
            stats = ads_stats_by_nm.get(nm_id or 0, {}) if nm_id is not None else {}
            weights = self._ads_efficiency_row_weights(nm_rows)
            views_allocations = self._allocate_integer_total_by_weights(
                int(stats.get("views") or 0), weights
            )
            clicks_allocations = self._allocate_integer_total_by_weights(
                int(stats.get("clicks") or 0), weights
            )
            orders_allocations = self._allocate_integer_total_by_weights(
                int(stats.get("orders") or 0), weights
            )
            atbs_allocations = self._allocate_integer_total_by_weights(
                int(stats.get("atbs") or 0), weights
            )
            shks_allocations = self._allocate_integer_total_by_weights(
                int(stats.get("shks") or 0), weights
            )
            canceled_allocations = self._allocate_integer_total_by_weights(
                int(stats.get("canceled") or 0), weights
            )
            stats_source_spend = self._decimal(stats.get("source_ad_spend"))
            stats_source_revenue = self._decimal(stats.get("source_revenue"))
            for index, row in enumerate(nm_rows):
                ad_spend = self._decimal(row.ad_spend)
                revenue = self._decimal(row.revenue)
                weight = weights[index] if index < len(weights) else Decimal("0")
                row_source_ad_spend = (
                    stats_source_spend * weight
                    if stats_source_spend > 0
                    else self._decimal(getattr(row, "source_ad_spend", None))
                )
                row_source_revenue = (
                    stats_source_revenue * weight
                    if stats_source_revenue > 0
                    else Decimal("0")
                )
                action_hint = (
                    "AD_ALLOCATION_REVIEW"
                    if self._decimal(getattr(row, "overallocated_ad_spend", None)) > 0
                    else "AD_PAUSE_REVIEW"
                    if ad_spend > 0 and (row.net_profit or 0) <= 0
                    else "AD_SCALE_REVIEW"
                    if ad_spend > 0
                    and row.trust_state == TRUST_STATE_TRUSTED
                    and (row.net_profit or 0) > 0
                    else None
                )
                blocked_reasons = list(getattr(row, "blocked_reasons", []) or [])
                allocation_status = str(getattr(row, "ads_allocation_status", "") or "")
                row_views = (
                    views_allocations[index] if index < len(views_allocations) else 0
                )
                row_clicks = (
                    clicks_allocations[index] if index < len(clicks_allocations) else 0
                )
                row_orders = (
                    orders_allocations[index] if index < len(orders_allocations) else 0
                )
                row_atbs = (
                    atbs_allocations[index] if index < len(atbs_allocations) else 0
                )
                row_shks = (
                    shks_allocations[index] if index < len(shks_allocations) else 0
                )
                row_canceled = (
                    canceled_allocations[index]
                    if index < len(canceled_allocations)
                    else 0
                )
                row_drr_percent = (
                    self._percent0(row_source_ad_spend, row_source_revenue)
                    if row_source_revenue > 0 and row_source_ad_spend > 0
                    else row.drr_percent
                    if row.drr_percent is not None and row.drr_percent > 0
                    else self._float((ad_spend / revenue) * Decimal("100"))
                    if revenue > 0 and ad_spend > 0
                    else None
                )
                items.append(
                    AdsEfficiencyRow(
                        sku_id=row.sku_id,
                        nm_id=row.nm_id,
                        vendor_code=row.vendor_code,
                        title=row.title,
                        level="sku" if row.sku_id is not None else "nm",
                        level_label="по размеру"
                        if row.sku_id is not None
                        else "по карточке",
                        advert_id=stats.get("advert_id"),
                        campaign_name=stats.get("campaign_name"),
                        campaign_count=int(stats.get("campaign_count") or 0),
                        advert_ids=list(stats.get("advert_ids") or []),
                        stats_rows_count=int(stats.get("stats_rows_count") or 0),
                        views=row_views,
                        clicks=row_clicks,
                        ctr_percent=self._percent0(row_clicks, row_views)
                        if row_views > 0
                        else None,
                        cr_percent=self._percent0(row_orders, row_clicks)
                        if row_clicks > 0
                        else None,
                        cpc=self._float(row_source_ad_spend / Decimal(str(row_clicks)))
                        if row_clicks > 0 and row_source_ad_spend > 0
                        else None,
                        orders=row_orders,
                        atbs=row_atbs,
                        shks=row_shks,
                        canceled=row_canceled,
                        source_revenue=float(row_source_revenue),
                        ad_revenue=float(row_source_revenue),
                        revenue=row.revenue,
                        ad_spend=float(ad_spend),
                        raw_ad_spend=float(
                            self._decimal(getattr(row, "raw_ad_spend", None))
                        ),
                        source_ad_spend=float(row_source_ad_spend),
                        overallocated_ad_spend=float(
                            self._decimal(getattr(row, "overallocated_ad_spend", None))
                        ),
                        unallocated_ad_spend=float(
                            self._decimal(getattr(row, "unallocated_ad_spend", None))
                        ),
                        ads_allocation_status=allocation_status,
                        ads_allocation_status_label=self._ads_efficiency_allocation_status_label(
                            allocation_status
                        ),
                        final_profit_allowed=bool(
                            getattr(row, "final_profit_allowed", True)
                        ),
                        net_profit=row.net_profit,
                        profit_after_ads=row.net_profit,
                        drr_percent=row_drr_percent,
                        stock_qty=row.stock_qty,
                        days_of_stock=row.days_of_stock,
                        confidence=(
                            "high"
                            if row_source_ad_spend > 0
                            and self._decimal(
                                getattr(row, "overallocated_ad_spend", None)
                            )
                            <= 0
                            else "medium"
                            if ad_spend > 0
                            else "low"
                        ),
                        action_hint=action_hint,
                        action_label=self._ads_efficiency_action_label(
                            action_hint=action_hint,
                            trust_state=getattr(row, "trust_state", None),
                            blocked_reasons=blocked_reasons,
                        ),
                        trust_state=str(getattr(row, "trust_state", "") or ""),
                        blocked_reasons=blocked_reasons,
                    )
                )
        total_source_spend_for_share = sum(
            (self._decimal(item.source_ad_spend) for item in items), start=Decimal("0")
        )
        if total_source_spend_for_share > 0:
            for item in items:
                item.spend_share_percent = self._percent0(
                    item.source_ad_spend, total_source_spend_for_share
                )
        if min_drr_percent is not None:
            items = [
                item
                for item in items
                if item.drr_percent is not None and item.drr_percent >= min_drr_percent
            ]
        if max_drr_percent is not None:
            items = [
                item
                for item in items
                if item.drr_percent is not None and item.drr_percent <= max_drr_percent
            ]
        reverse = sort_dir != "asc"
        if sort_by == "drr_percent":
            items.sort(
                key=lambda item: (
                    item.drr_percent if item.drr_percent is not None else float("-inf")
                ),
                reverse=reverse,
            )
        elif sort_by == "revenue":
            items.sort(key=lambda item: item.revenue, reverse=reverse)
        elif sort_by == "spend":
            items.sort(key=lambda item: item.ad_spend, reverse=reverse)
        else:
            items.sort(
                key=lambda item: (item.ad_spend, -(item.net_profit or 0)), reverse=True
            )
        total = len(items)
        page = AdsEfficiencyPage(
            total=total,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
            summary=self._ads_efficiency_summary(items),
        )
        page.computed_at = cache_meta.get("computed_at")
        page.cache_status = str(cache_meta.get("cache_status") or "miss")
        page.data_version_hash = cache_meta.get("data_version_hash")
        return page

    async def list_alerts(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        severity: str | None = None,
        alert_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> Page[AlertRead]:
        try:
            rows = list(
                (
                    await session.execute(
                        select(AlertEvent)
                        .where(AlertEvent.account_id == account_id)
                        .order_by(AlertEvent.updated_at.desc(), AlertEvent.id.desc())
                    )
                ).scalars()
            )
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "alert_events"):
                rows = []
            else:
                raise
        if severity is not None:
            rows = [row for row in rows if row.severity == severity]
        if alert_type is not None:
            rows = [row for row in rows if row.alert_type == alert_type]
        if status is not None:
            rows = [row for row in rows if row.status == status]
        items = [
            AlertRead(
                id=row.id,
                account_id=row.account_id,
                action_id=row.action_id,
                alert_type=row.alert_type,
                severity=row.severity,
                status=row.status,
                title=row.title,
                message=row.message,
                confidence=row.confidence,
                payload=dict(row.payload or {}),
                snoozed_until=row.snoozed_until,
                resolved_at=row.resolved_at,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
        total = len(items)
        return Page(
            total=total,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
        )

    async def bulk_update_alerts(
        self,
        session: AsyncSession,
        *,
        ids: list[int],
        status: str,
        snoozed_until: datetime | None = None,
    ) -> int:
        updated = 0
        for alert_id in ids:
            try:
                await self.update_alert(
                    session,
                    alert_id=alert_id,
                    payload=AlertUpdateRequest(
                        status=status, snoozed_until=snoozed_until
                    ),
                )
                updated += 1
            except HTTPException:
                continue
        return updated

    async def run_formula_audit(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        sample_limit: int = 5,
    ) -> FormulaAuditRun:
        actual_from, actual_to = self._date_range(date_from, date_to)
        started_at = utcnow()
        control_rows, price_rows, purchase_rows, _ = await self._build_control_rows(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        trust_decision = await self._trust_decision(
            session, account_id=account_id, date_from=actual_from, date_to=actual_to
        )
        article_samples: list[dict[str, Any]] = []
        for row in [item for item in control_rows if item.nm_id is not None][
            :sample_limit
        ]:
            audit = await self.dashboard.article_audit(
                session,
                account_id=account_id,
                nm_id=int(row.nm_id),
                date_from=actual_from,
                date_to=actual_to,
            )
            reconciliation = audit.reconciliation
            article_samples.append(
                {
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "revenue_matches_mart": bool(reconciliation.revenue_matches_mart)
                    if reconciliation is not None
                    else True,
                    "difference_amount": float(reconciliation.difference_amount)
                    if reconciliation is not None
                    else 0.0,
                    "difference_ratio": reconciliation.difference_ratio
                    if reconciliation is not None
                    else None,
                }
            )
        passed, result_json = self._formula_audit_result(
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            trust_decision=trust_decision,
            price_rows=price_rows,
            purchase_rows=purchase_rows,
            article_samples=article_samples,
        )
        row = FormulaAuditRun(
            account_id=account_id,
            scope="account",
            status="passed" if passed else "failed",
            passed=passed,
            result_json=result_json,
            started_at=started_at,
            finished_at=utcnow(),
        )
        session.add(row)
        try:
            await session.flush()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "formula_audit_runs"):
                self._raise_storage_not_ready()
            raise
        return row

    async def build_daily_digest_payload(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        action_limit: int = 10,
        alert_limit: int = 10,
    ) -> dict[str, Any]:
        actual_from, actual_to = self._date_range(date_from, date_to)
        owner = await self.owner_dashboard(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        actions_page = await self.list_actions(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            limit=action_limit,
            offset=0,
        )
        alerts_page = await self.list_alerts(
            session,
            account_id=account_id,
            limit=alert_limit,
            offset=0,
        )
        purchase_page = await self.list_purchase_plan(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            limit=action_limit,
            offset=0,
        )
        try:
            latest_formula_audit = (
                await session.execute(
                    select(FormulaAuditRun)
                    .where(FormulaAuditRun.account_id == account_id)
                    .order_by(
                        FormulaAuditRun.finished_at.desc().nulls_last(),
                        FormulaAuditRun.id.desc(),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "formula_audit_runs"):
                latest_formula_audit = None
            else:
                raise
        return {
            "generated_at": utcnow().isoformat(),
            "account_id": account_id,
            "date_from": actual_from.isoformat(),
            "date_to": actual_to.isoformat(),
            "trust_state": owner.trust_state,
            "blocked_reasons": list(owner.blocked_reasons),
            "can_generate_business_actions": owner.can_generate_business_actions,
            "kpis": {
                "revenue": owner.revenue,
                "net_profit": owner.net_profit,
                "margin_percent": owner.margin_percent,
                "roi_percent": owner.roi_percent,
                "ad_spend": owner.ad_spend,
                "stock_value": owner.stock_value,
                "overstock_value": owner.overstock_value,
                "out_of_stock_risk_count": owner.out_of_stock_risk_count,
                "negative_profit_sku_count": owner.negative_profit_sku_count,
                "blocked_data_sku_count": owner.blocked_data_sku_count,
            },
            "top_risks": [item.model_dump() for item in owner.top_risks[:action_limit]],
            "top_opportunities": [
                item.model_dump() for item in owner.top_opportunities[:action_limit]
            ],
            "actions": [
                item.model_dump() for item in actions_page.items[:action_limit]
            ],
            "alerts": [item.model_dump() for item in alerts_page.items[:alert_limit]],
            "purchase_focus": [
                item.model_dump() for item in purchase_page.items[:action_limit]
            ],
            "formula_audit": {
                "status": latest_formula_audit.status
                if latest_formula_audit is not None
                else None,
                "passed": latest_formula_audit.passed
                if latest_formula_audit is not None
                else None,
                "finished_at": latest_formula_audit.finished_at.isoformat()
                if latest_formula_audit is not None
                and latest_formula_audit.finished_at is not None
                else None,
                "result": dict(latest_formula_audit.result_json or {})
                if latest_formula_audit is not None
                else None,
            },
            "notes": list(owner.notes),
        }

    async def update_alert(
        self,
        session: AsyncSession,
        *,
        alert_id: int,
        payload: AlertUpdateRequest,
    ) -> AlertRead:
        try:
            alert = await session.get(AlertEvent, alert_id)
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "alert_events"):
                self._raise_storage_not_ready()
            raise
        if alert is None:
            raise HTTPException(status_code=404, detail="Alert not found")
        alert.status = payload.status
        alert.snoozed_until = payload.snoozed_until
        if payload.status == "resolved":
            alert.resolved_at = utcnow()
        try:
            await session.flush()
        except ProgrammingError as exc:
            if self._is_missing_relation_error(exc, "alert_events"):
                self._raise_storage_not_ready()
            raise
        return AlertRead(
            id=alert.id,
            account_id=alert.account_id,
            action_id=alert.action_id,
            alert_type=alert.alert_type,
            severity=alert.severity,
            status=alert.status,
            title=alert.title,
            message=alert.message,
            confidence=alert.confidence,
            payload=dict(alert.payload or {}),
            snoozed_until=alert.snoozed_until,
            resolved_at=alert.resolved_at,
            created_at=alert.created_at,
            updated_at=alert.updated_at,
        )
