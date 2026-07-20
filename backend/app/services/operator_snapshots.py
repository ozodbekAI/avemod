from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, TypeVar, cast

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import TTLMemoryCache
from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.pagination import Page
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.response_snapshots import APIResponseSnapshot
from app.schemas.control_tower import (
    AdsEfficiencyPage,
    ControlTowerSkuRow,
    OwnerDashboardRead,
    PriceSafetyPage,
    PurchasePlanPage,
)
from app.schemas.dashboard import (
    ArticleAuditRead,
    DashboardDataHealth,
    SKUProfitabilityRow,
)
from app.schemas.data_quality import (
    DataQualityIssueRead,
    DataQualityIssueSummaryResponse,
    DataQualityIssueSummaryRow,
)
from app.schemas.marts import (
    MartAccountExpenseDailyRead,
    MartBusinessDailyRead,
    MartFinanceReconciliationRead,
    MartReconciliationDailyRead,
    MartSKUDailyRead,
    MartStockDailyRead,
)
from app.services.control_tower import ControlTowerService
from app.services.dashboard import DashboardService
from app.services.data_quality import DataQualityService
from app.services.marts import MartService
from app.services.money_management import MoneyManagementService

SnapshotModelT = TypeVar("SnapshotModelT", bound=BaseModel)
DataQualityIssuePage = Page[DataQualityIssueRead]
ControlTowerSkuPage = Page[ControlTowerSkuRow]
SKUProfitabilityPage = Page[SKUProfitabilityRow]
MartReconciliationDailyPage = Page[MartReconciliationDailyRead]
MartSKUDailyPage = Page[MartSKUDailyRead]
MartBusinessDailyPage = Page[MartBusinessDailyRead]
MartStockDailyPage = Page[MartStockDailyRead]
MartFinanceReconciliationPage = Page[MartFinanceReconciliationRead]
MartAccountExpenseDailyPage = Page[MartAccountExpenseDailyRead]


@dataclass(frozen=True)
class OperatorSnapshotSpec:
    namespace: str
    endpoint_key: str
    account_id: int
    date_from: date | None
    date_to: date | None
    params: dict[str, Any]


class OperatorEndpointSnapshotService:
    SUPPORTED_NAMESPACES = ("dashboard", "data_quality", "control_tower", "marts")
    DEADLOCK_RETRIES = 3
    MEMORY_CACHE_TTL_SECONDS = 30
    PAYLOAD_VERSION_BY_ENDPOINT = {
        # v2 separates owner dashboard snapshots that carry dense WB/Ads daily
        # funnel fields from older cached payloads.
        "dashboard_owner": 2,
    }
    _shared_response_cache: TTLMemoryCache[BaseModel] = TTLMemoryCache(
        default_ttl_seconds=MEMORY_CACHE_TTL_SECONDS
    )

    def __init__(self) -> None:
        self.dashboard = DashboardService()
        self.data_quality = DataQualityService()
        self.control_tower = ControlTowerService()
        self.marts = MartService()
        self._window_service = MoneyManagementService()
        self._response_cache = type(self)._shared_response_cache
        settings = get_settings()
        self.refresh_interval = timedelta(
            minutes=max(int(settings.money_response_snapshot_refresh_minutes), 1)
        )
        self.max_stale_interval = timedelta(
            minutes=max(int(settings.money_response_snapshot_max_stale_minutes), 1)
        )
        self.active_days = max(int(settings.money_response_snapshot_active_days), 1)
        self.refresh_max_specs_per_account = max(
            int(settings.money_response_snapshot_refresh_max_specs_per_account),
            1,
        )
        self.refresh_min_access_count = max(
            int(settings.money_response_snapshot_refresh_min_access_count),
            1,
        )

    def _normalize_window(
        self, date_from: date | None, date_to: date | None
    ) -> tuple[date, date]:
        return self._window_service._date_range(date_from, date_to)

    @staticmethod
    def _normalize_param_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): OperatorEndpointSnapshotService._normalize_param_value(inner)
                for key, inner in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                OperatorEndpointSnapshotService._normalize_param_value(item)
                for item in value
            ]
        return value

    @staticmethod
    def _page_model(item_model: type[Any]) -> type[Page[Any]]:
        return Page[item_model]  # type: ignore[index]

    @staticmethod
    def _list_param(params: dict[str, Any], key: str) -> list[str] | None:
        value = params.get(key)
        if value is None:
            return None
        if isinstance(value, list):
            return [str(item) for item in value]
        return [str(value)]

    @classmethod
    def _payload_version(cls, endpoint_key: str) -> int:
        return int(cls.PAYLOAD_VERSION_BY_ENDPOINT.get(endpoint_key, 1))

    @staticmethod
    def _with_snapshot_meta(
        payload: SnapshotModelT, *, computed_at: datetime, cache_status: str
    ) -> SnapshotModelT:
        updates: dict[str, Any] = {}
        model_fields = type(payload).model_fields
        if "computed_at" in model_fields:
            updates["computed_at"] = computed_at
        if "cache_status" in model_fields:
            updates["cache_status"] = cache_status
        if not updates:
            return payload
        return payload.model_copy(deep=True, update=updates)

    def _model_cls_for_endpoint(self, endpoint_key: str) -> type[BaseModel] | None:
        mapping: dict[str, type[BaseModel]] = {
            "dashboard_data_health": DashboardDataHealth,
            "dashboard_owner": OwnerDashboardRead,
            "dashboard_sku_profitability": self._page_model(SKUProfitabilityRow),
            "dashboard_article_audit": ArticleAuditRead,
            "dq_issue_summary": DataQualityIssueSummaryResponse,
            "dq_issues": self._page_model(DataQualityIssueRead),
            "dq_investigator_issues": self._page_model(DataQualityIssueRead),
            "control_skus": self._page_model(ControlTowerSkuRow),
            "inventory_purchase_plan": PurchasePlanPage,
            "pricing_safety": PriceSafetyPage,
            "ads_efficiency": AdsEfficiencyPage,
            "marts_business_daily": self._page_model(MartBusinessDailyRead),
            "marts_reconciliation_daily": self._page_model(MartReconciliationDailyRead),
            "marts_sku_daily": self._page_model(MartSKUDailyRead),
            "marts_stock_daily": self._page_model(MartStockDailyRead),
            "marts_finance_reconciliation": self._page_model(
                MartFinanceReconciliationRead
            ),
            "marts_account_expense_daily": self._page_model(
                MartAccountExpenseDailyRead
            ),
        }
        return mapping.get(endpoint_key)

    def _params_hash(
        self,
        *,
        endpoint_key: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        params: dict[str, Any],
    ) -> str:
        payload = {
            "endpoint_key": endpoint_key,
            "account_id": account_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "params": self._normalize_param_value(params),
        }
        payload_version = self._payload_version(endpoint_key)
        if payload_version > 1:
            payload["payload_version"] = payload_version
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        )
        return hashlib.sha1(encoded.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _response_cache_key(
        self,
        *,
        namespace: str,
        endpoint_key: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        params: dict[str, Any],
    ) -> tuple[object, ...]:
        return (
            namespace,
            endpoint_key,
            int(account_id),
            date_from.isoformat() if date_from else None,
            date_to.isoformat() if date_to else None,
            self._params_hash(
                endpoint_key=endpoint_key,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                params=params,
            ),
        )

    @staticmethod
    def _snapshot_lock_key(
        *, namespace: str, endpoint_key: str, account_id: int, params_hash: str
    ) -> int:
        raw = hashlib.sha1(
            f"{namespace}:{endpoint_key}:{account_id}:{params_hash}".encode("utf-8"),
            usedforsecurity=False,
        ).digest()[:8]
        return int.from_bytes(raw, "big", signed=True)

    @staticmethod
    def _is_deadlock(exc: BaseException) -> bool:
        if not isinstance(exc, DBAPIError):
            return False
        orig = getattr(exc, "orig", None)
        return (
            getattr(orig, "sqlstate", None) == "40P01"
            or getattr(orig, "pgcode", None) == "40P01"
            or "deadlock detected" in str(exc).lower()
        )

    async def _load_snapshot(
        self,
        session: AsyncSession,
        *,
        namespace: str,
        endpoint_key: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        params: dict[str, Any],
        model_cls: type[SnapshotModelT],
    ) -> SnapshotModelT | None:
        params_hash = self._params_hash(
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
        )
        row = (
            await session.execute(
                select(APIResponseSnapshot).where(
                    APIResponseSnapshot.namespace == namespace,
                    APIResponseSnapshot.endpoint_key == endpoint_key,
                    APIResponseSnapshot.account_id == account_id,
                    APIResponseSnapshot.params_hash == params_hash,
                    APIResponseSnapshot.snapshot_status == "ready",
                )
            )
        ).scalar_one_or_none()
        if row is None or not isinstance(row.payload, dict) or not row.payload:
            return None
        now = utcnow()
        try:
            computed_stale = row.computed_at + self.max_stale_interval < now
        except TypeError:
            computed_stale = row.computed_at.replace(
                tzinfo=None
            ) + self.max_stale_interval < now.replace(tzinfo=None)
        try:
            expired = row.expires_at is None or row.expires_at <= now
        except TypeError:
            expired = row.expires_at.replace(tzinfo=None) <= now.replace(tzinfo=None)
        payload = model_cls.model_validate(row.payload)
        cache_status = (
            "db_snapshot_stale" if computed_stale or expired else "db_snapshot_hit"
        )
        row_id = getattr(row, "id", None)
        if row_id is not None:
            await self._touch_snapshot_access(snapshot_id=int(row_id))
        return self._with_snapshot_meta(
            payload, computed_at=row.computed_at, cache_status=cache_status
        )

    async def _touch_snapshot_access(self, *, snapshot_id: int) -> None:
        try:
            async with SessionLocal() as touch_session:
                await touch_session.execute(
                    update(APIResponseSnapshot)
                    .where(APIResponseSnapshot.id == snapshot_id)
                    .values(
                        last_accessed_at=utcnow(),
                        access_count=APIResponseSnapshot.access_count + 1,
                        updated_at=func.now(),
                    )
                )
                await touch_session.commit()
        except Exception:
            return

    async def _save_snapshot(
        self,
        session: AsyncSession,
        *,
        namespace: str,
        endpoint_key: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        params: dict[str, Any],
        response: BaseModel,
        auto_commit: bool = True,
    ) -> None:
        params_hash = self._params_hash(
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
        )
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    self._snapshot_lock_key(
                        namespace=namespace,
                        endpoint_key=endpoint_key,
                        account_id=account_id,
                        params_hash=params_hash,
                    )
                )
            )
        )
        normalized_params = self._normalize_param_value(params)
        now = utcnow()
        computed_at = getattr(response, "computed_at", None) or now
        stmt = insert(APIResponseSnapshot).values(
            namespace=namespace,
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params_hash=params_hash,
            request_params=normalized_params,
            response_model=type(response).__name__,
            payload=response.model_dump(mode="json"),
            snapshot_status="ready",
            last_error=None,
            computed_at=computed_at,
            expires_at=now + self.refresh_interval,
            last_accessed_at=now,
            access_count=1,
        )
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                APIResponseSnapshot.namespace,
                APIResponseSnapshot.endpoint_key,
                APIResponseSnapshot.account_id,
                APIResponseSnapshot.params_hash,
            ],
            set_={
                "date_from": excluded.date_from,
                "date_to": excluded.date_to,
                "request_params": excluded.request_params,
                "response_model": excluded.response_model,
                "payload": excluded.payload,
                "snapshot_status": excluded.snapshot_status,
                "last_error": excluded.last_error,
                "computed_at": excluded.computed_at,
                "expires_at": excluded.expires_at,
                "last_accessed_at": excluded.last_accessed_at,
                "access_count": APIResponseSnapshot.access_count + 1,
                "updated_at": func.now(),
            },
        )
        await session.execute(stmt)
        if auto_commit:
            await session.commit()

    async def _get_or_compute(
        self,
        session: AsyncSession,
        *,
        namespace: str,
        endpoint_key: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        params: dict[str, Any],
        model_cls: type[SnapshotModelT],
        compute: Any,
        normalize_window: bool = False,
        validate_snapshot: Callable[[SnapshotModelT, date | None, date | None], bool]
        | None = None,
    ) -> SnapshotModelT:
        actual_from: date | None
        actual_to: date | None
        if normalize_window:
            actual_from, actual_to = self._normalize_window(date_from, date_to)
        else:
            actual_from, actual_to = date_from, date_to
        response_cache_key = self._response_cache_key(
            namespace=namespace,
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            params=params,
        )
        cached = self._response_cache.get(response_cache_key)
        if cached is not None:
            cached_model = cast(SnapshotModelT, cached)
            if validate_snapshot is None or validate_snapshot(
                cached_model, actual_from, actual_to
            ):
                return cached_model
            self._response_cache.clear()
        snapshot = await self._load_snapshot(
            session,
            namespace=namespace,
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            params=params,
            model_cls=model_cls,
        )
        if snapshot is not None:
            if validate_snapshot is None or validate_snapshot(
                snapshot, actual_from, actual_to
            ):
                self._response_cache.set(response_cache_key, snapshot)
                return snapshot
            self._response_cache.clear()
        response = await compute(actual_from, actual_to)
        response = model_cls.model_validate(response)
        await self._save_snapshot(
            session,
            namespace=namespace,
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            params=params,
            response=response,
        )
        self._response_cache.set(response_cache_key, response)
        return response

    @staticmethod
    def _owner_dashboard_has_dense_daily(
        snapshot: OwnerDashboardRead, date_from: date | None, date_to: date | None
    ) -> bool:
        window_from = date_from or getattr(snapshot, "date_from", None)
        window_to = date_to or getattr(snapshot, "date_to", None)
        if window_from is None or window_to is None:
            return True
        expected_days = (window_to - window_from).days + 1
        if expected_days <= 1:
            return True
        wb_daily = list(getattr(snapshot.wb_summary, "daily", []) or [])
        ads_daily = list(getattr(snapshot.ads_summary, "daily", []) or [])
        if len(wb_daily) < expected_days or len(ads_daily) < expected_days:
            return False

        wb_orders_total = int(getattr(snapshot.wb_summary, "funnel_orders_count", 0) or 0)
        wb_daily_orders_total = sum(
            int(getattr(item, "order_count", 0) or 0) for item in wb_daily
        )
        if wb_orders_total > 0 and wb_daily_orders_total <= 0:
            return False

        wb_buyout_total = int(getattr(snapshot.wb_summary, "buyout_count", 0) or 0)
        wb_daily_buyout_total = sum(
            int(getattr(item, "buyout_count", 0) or 0) for item in wb_daily
        )
        if wb_buyout_total > 0 and wb_daily_buyout_total <= 0:
            return False

        ads_orders_amount = float(getattr(snapshot.ads_summary, "orders_amount", 0) or 0)
        ads_daily_orders_total = sum(
            int(getattr(item, "orders_count", 0) or 0) for item in ads_daily
        )
        if ads_orders_amount > 0 and ads_daily_orders_total <= 0:
            return False

        return True

    async def invalidate_snapshots(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        namespaces: set[str] | None = None,
        endpoint_keys: set[str] | None = None,
    ) -> None:
        stmt = (
            update(APIResponseSnapshot)
            .where(
                APIResponseSnapshot.namespace.in_(
                    list(namespaces or self.SUPPORTED_NAMESPACES)
                )
            )
            .values(expires_at=utcnow(), updated_at=func.now())
        )
        if account_id is not None:
            stmt = stmt.where(APIResponseSnapshot.account_id == account_id)
        if endpoint_keys:
            stmt = stmt.where(APIResponseSnapshot.endpoint_key.in_(list(endpoint_keys)))
        await session.execute(stmt)
        self._response_cache.clear()

    async def data_health(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DashboardDataHealth:
        return await self._get_or_compute(
            session,
            namespace="dashboard",
            endpoint_key="dashboard_data_health",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params={},
            model_cls=DashboardDataHealth,
            compute=lambda actual_from, actual_to: self.dashboard.data_health(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
        )

    async def dq_issue_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> DataQualityIssueSummaryResponse:
        return await self._get_or_compute(
            session,
            namespace="data_quality",
            endpoint_key="dq_issue_summary",
            account_id=account_id,
            date_from=None,
            date_to=None,
            params={},
            model_cls=DataQualityIssueSummaryResponse,
            compute=lambda *_: self._build_dq_issue_summary(
                session, account_id=account_id
            ),
        )

    async def dq_issues(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        only_open: bool = False,
        code: list[str] | None = None,
        issue_type: list[str] | None = None,
        severity: list[str] | None = None,
        domain: list[str] | None = None,
        source_table: list[str] | None = None,
        financial_final_blocker: bool | None = None,
        classification_status: list[str] | None = None,
        age_bucket: list[str] | None = None,
        status: str | None = None,
        sku_id: int | None = None,
        nm_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> DataQualityIssuePage:
        params = {
            "only_open": only_open,
            "code": code,
            "issue_type": issue_type,
            "severity": severity,
            "domain": domain,
            "source_table": source_table,
            "financial_final_blocker": financial_final_blocker,
            "classification_status": classification_status,
            "age_bucket": age_bucket,
            "status": status,
            "sku_id": sku_id,
            "nm_id": nm_id,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="data_quality",
            endpoint_key="dq_issues",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(DataQualityIssueRead),
            compute=lambda actual_from, actual_to: self.data_quality.list_issues(
                session,
                account_id=account_id,
                only_open=only_open,
                codes=code,
                issue_types=issue_type,
                severities=severity,
                domains=domain,
                source_tables=source_table,
                classification_statuses=classification_status,
                age_buckets=age_bucket,
                status=status,
                sku_id=sku_id,
                nm_id=nm_id,
                detected_from=actual_from,
                detected_to=actual_to,
                financial_final_blocker=financial_final_blocker,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )

    async def dq_investigator_issues(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        code: str,
        limit: int = 100,
        offset: int = 0,
    ) -> DataQualityIssuePage:
        params = {
            "code": code,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="data_quality",
            endpoint_key="dq_investigator_issues",
            account_id=account_id,
            date_from=None,
            date_to=None,
            params=params,
            model_cls=self._page_model(DataQualityIssueRead),
            compute=lambda *_: self.data_quality.list_investigator_issues(
                session,
                account_id=account_id,
                code=code,
                limit=limit,
                offset=offset,
            ),
        )

    async def owner_dashboard(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> OwnerDashboardRead:
        return await self._get_or_compute(
            session,
            namespace="control_tower",
            endpoint_key="dashboard_owner",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params={},
            model_cls=OwnerDashboardRead,
            compute=lambda actual_from, actual_to: self.control_tower.owner_dashboard(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
            validate_snapshot=self._owner_dashboard_has_dense_daily,
        )

    async def control_skus(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        sku_status: list[str] | None = None,
        trust_state: list[str] | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        preset: str | None = None,
        has_open_actions: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ControlTowerSkuPage:
        params = {
            "search": search,
            "sku_status": sku_status,
            "trust_state": trust_state,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "preset": preset,
            "has_open_actions": has_open_actions,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="control_tower",
            endpoint_key="control_skus",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(ControlTowerSkuRow),
            compute=lambda actual_from, actual_to: self.control_tower.list_control_skus(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                search=search,
                sku_status=sku_status,
                trust_state=trust_state,
                sort_by=sort_by,
                sort_dir=sort_dir,
                preset=preset,
                has_open_actions=has_open_actions,
                limit=limit,
                offset=offset,
            ),
        )

    async def purchase_plan(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
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
        params = {
            "group_by": group_by,
            "include_blocked": include_blocked,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "status_filter": status_filter,
            "search": search,
            "profit_filter": profit_filter,
            "data_filter": data_filter,
            "stock_filter": stock_filter,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="control_tower",
            endpoint_key="inventory_purchase_plan",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=PurchasePlanPage,
            compute=lambda actual_from, actual_to: (
                self.control_tower.list_purchase_plan(
                    session,
                    account_id=account_id,
                    date_from=actual_from,
                    date_to=actual_to,
                    group_by=group_by,
                    include_blocked=include_blocked,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    status_filter=status_filter,
                    search=search,
                    profit_filter=profit_filter,
                    data_filter=data_filter,
                    stock_filter=stock_filter,
                    limit=limit,
                    offset=offset,
                )
            ),
        )

    async def price_safety(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        only_risk: bool = False,
        search: str | None = None,
        status: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> PriceSafetyPage:
        params = {
            "only_risk": only_risk,
            "search": search,
            "status": status,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="control_tower",
            endpoint_key="pricing_safety",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=PriceSafetyPage,
            compute=lambda actual_from, actual_to: self.control_tower.list_price_safety(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                only_risk=only_risk,
                search=search,
                status=status,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )

    async def ads_efficiency(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        campaign_id: int | None = None,
        min_drr_percent: float | None = None,
        max_drr_percent: float | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 100,
        offset: int = 0,
    ) -> AdsEfficiencyPage:
        params = {
            "campaign_id": campaign_id,
            "min_drr_percent": min_drr_percent,
            "max_drr_percent": max_drr_percent,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="control_tower",
            endpoint_key="ads_efficiency",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=AdsEfficiencyPage,
            compute=lambda actual_from, actual_to: (
                self.control_tower.list_ads_efficiency(
                    session,
                    account_id=account_id,
                    date_from=actual_from,
                    date_to=actual_to,
                    campaign_id=campaign_id,
                    min_drr_percent=min_drr_percent,
                    max_drr_percent=max_drr_percent,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    limit=limit,
                    offset=offset,
                )
            ),
        )

    async def sku_profitability(
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
    ) -> SKUProfitabilityPage:
        params = {
            "search": search,
            "vendor_code": vendor_code,
            "barcode": barcode,
            "brand": brand,
            "subject_name": subject_name,
            "has_manual_cost": has_manual_cost,
            "business_trusted": business_trusted,
            "sort": sort,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="dashboard",
            endpoint_key="dashboard_sku_profitability",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(SKUProfitabilityRow),
            compute=lambda actual_from, actual_to: (
                self.dashboard.sku_profitability_page(
                    session,
                    account_id=account_id,
                    date_from=actual_from,
                    date_to=actual_to,
                    search=search,
                    vendor_code=vendor_code,
                    barcode=barcode,
                    brand=brand,
                    subject_name=subject_name,
                    has_manual_cost=has_manual_cost,
                    business_trusted=business_trusted,
                    sort=sort,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    limit=limit,
                    offset=offset,
                )
            ),
        )

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
        params = {
            "nm_id": nm_id,
            "issues_limit": issues_limit,
            "issues_offset": issues_offset,
        }
        return await self._get_or_compute(
            session,
            namespace="dashboard",
            endpoint_key="dashboard_article_audit",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=ArticleAuditRead,
            compute=lambda actual_from, actual_to: self.dashboard.article_audit(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=actual_from,
                date_to=actual_to,
                issues_limit=issues_limit,
                issues_offset=issues_offset,
            ),
        )

    async def reconciliation_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        search: str | None = None,
        flag: str | None = None,
        status_bucket: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        aggregate: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MartReconciliationDailyPage:
        params = {
            "sku_id": sku_id,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
            "barcode": barcode,
            "search": search,
            "flag": flag,
            "status_bucket": status_bucket,
            "aggregate": aggregate,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="marts",
            endpoint_key="marts_reconciliation_daily",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(MartReconciliationDailyRead),
            compute=lambda actual_from, actual_to: self.marts.list_reconciliation_daily(
                session,
                account_id=account_id,
                sku_id=sku_id,
                nm_id=nm_id,
                vendor_code=vendor_code,
                barcode=barcode,
                search=search,
                flag=flag,
                status_bucket=status_bucket,
                date_from=actual_from,
                date_to=actual_to,
                aggregate=aggregate,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )

    async def sku_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        brand: str | None = None,
        subject_name: str | None = None,
        search: str | None = None,
        has_manual_cost: bool | None = None,
        has_open_issues: bool | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        aggregate: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MartSKUDailyPage:
        params = {
            "sku_id": sku_id,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
            "barcode": barcode,
            "brand": brand,
            "subject_name": subject_name,
            "search": search,
            "has_manual_cost": has_manual_cost,
            "has_open_issues": has_open_issues,
            "aggregate": aggregate,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="marts",
            endpoint_key="marts_sku_daily",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(MartSKUDailyRead),
            compute=lambda actual_from, actual_to: self.marts.list_sku_daily(
                session,
                account_id=account_id,
                sku_id=sku_id,
                nm_id=nm_id,
                vendor_code=vendor_code,
                barcode=barcode,
                brand=brand,
                subject_name=subject_name,
                search=search,
                has_manual_cost=has_manual_cost,
                has_open_issues=has_open_issues,
                date_from=actual_from,
                date_to=actual_to,
                aggregate=aggregate,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )

    async def business_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> MartBusinessDailyPage:
        params = {
            "snapshot_schema": "ads_api_fallback_v1",
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="marts",
            endpoint_key="marts_business_daily",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(MartBusinessDailyRead),
            compute=lambda actual_from, actual_to: self.marts.list_business_daily(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                limit=limit,
                offset=offset,
            ),
        )

    async def stock_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int | None = None,
        nm_id: int | None = None,
        barcode: str | None = None,
        warehouse_name: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MartStockDailyPage:
        params = {
            "sku_id": sku_id,
            "nm_id": nm_id,
            "barcode": barcode,
            "warehouse_name": warehouse_name,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="marts",
            endpoint_key="marts_stock_daily",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(MartStockDailyRead),
            compute=lambda actual_from, actual_to: self.marts.list_stock_daily(
                session,
                account_id=account_id,
                sku_id=sku_id,
                nm_id=nm_id,
                barcode=barcode,
                warehouse_name=warehouse_name,
                date_from=actual_from,
                date_to=actual_to,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )

    async def finance_reconciliation(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        srid: str | None = None,
        barcode: str | None = None,
        status: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        only_diff: bool = False,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MartFinanceReconciliationPage:
        params = {
            "nm_id": nm_id,
            "srid": srid,
            "barcode": barcode,
            "status": status,
            "only_diff": only_diff,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="marts",
            endpoint_key="marts_finance_reconciliation",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(MartFinanceReconciliationRead),
            compute=lambda actual_from, actual_to: (
                self.marts.list_finance_reconciliation(
                    session,
                    account_id=account_id,
                    nm_id=nm_id,
                    srid=srid,
                    barcode=barcode,
                    status=status,
                    date_from=actual_from,
                    date_to=actual_to,
                    only_diff=only_diff,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    limit=limit,
                    offset=offset,
                )
            ),
        )

    async def account_expense_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> MartAccountExpenseDailyPage:
        params = {
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            namespace="marts",
            endpoint_key="marts_account_expense_daily",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=self._page_model(MartAccountExpenseDailyRead),
            compute=lambda actual_from, actual_to: (
                self.marts.list_account_expense_daily(
                    session,
                    account_id=account_id,
                    date_from=actual_from,
                    date_to=actual_to,
                    sort_by=sort_by,
                    sort_dir=sort_dir,
                    limit=limit,
                    offset=offset,
                )
            ),
        )

    async def _build_dq_issue_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> DataQualityIssueSummaryResponse:
        payload = await self.data_quality.list_issue_summary(
            session, account_id=account_id
        )
        return DataQualityIssueSummaryResponse(
            items=[DataQualityIssueSummaryRow(**item) for item in payload["items"]],
            open_issues_total=int(payload["open_issues_total"]),
            all_open_issues_total=int(
                payload.get("all_open_issues_total") or payload["open_issues_total"]
            ),
            blocking_open_issues_total=int(
                payload.get("blocking_open_issues_total") or 0
            ),
            financial_final_blockers_total=int(
                payload["financial_final_blockers_total"]
            ),
            by_severity=dict(payload["by_severity"]),
            by_issue_type=dict(payload["by_issue_type"]),
            by_source_table=dict(payload["by_source_table"]),
            by_group=dict(payload["by_group"]),
            by_group_blocking=dict(payload.get("by_group_blocking") or {}),
            by_group_all_open=dict(payload.get("by_group_all_open") or {}),
        )

    def _default_specs_for_account(
        self, *, account_id: int
    ) -> list[OperatorSnapshotSpec]:
        today = utcnow().date()
        rolling_from, rolling_to = self._normalize_window(None, None)
        current_month_from = today.replace(day=1)
        previous_month_last_day = current_month_from - timedelta(days=1)
        previous_month_from = previous_month_last_day.replace(day=1)
        windows = {
            (rolling_from, rolling_to),
            (current_month_from, today),
            (previous_month_from, previous_month_last_day),
        }
        specs = [
            OperatorSnapshotSpec(
                "data_quality", "dq_issue_summary", account_id, None, None, {}
            ),
            OperatorSnapshotSpec(
                "data_quality",
                "dq_issues",
                account_id,
                None,
                None,
                {
                    "only_open": True,
                    "code": None,
                    "issue_type": None,
                    "severity": None,
                    "domain": None,
                    "source_table": None,
                    "financial_final_blocker": None,
                    "classification_status": None,
                    "age_bucket": None,
                    "status": None,
                    "sku_id": None,
                    "nm_id": None,
                    "sort_by": None,
                    "sort_dir": "desc",
                    "limit": 10,
                    "offset": 0,
                },
            ),
            OperatorSnapshotSpec(
                "data_quality",
                "dq_issues",
                account_id,
                None,
                None,
                {
                    "only_open": False,
                    "code": None,
                    "issue_type": None,
                    "severity": None,
                    "domain": None,
                    "source_table": None,
                    "financial_final_blocker": None,
                    "classification_status": None,
                    "age_bucket": None,
                    "status": None,
                    "sku_id": None,
                    "nm_id": None,
                    "sort_by": None,
                    "sort_dir": "desc",
                    "limit": 100,
                    "offset": 0,
                },
            ),
        ]
        for window_from, window_to in sorted(windows):
            specs.extend(
                [
                    OperatorSnapshotSpec(
                        "dashboard",
                        "dashboard_data_health",
                        account_id,
                        window_from,
                        window_to,
                        {},
                    ),
                    OperatorSnapshotSpec(
                        "control_tower",
                        "dashboard_owner",
                        account_id,
                        window_from,
                        window_to,
                        {},
                    ),
                    OperatorSnapshotSpec(
                        "dashboard",
                        "dashboard_sku_profitability",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "search": None,
                            "vendor_code": None,
                            "barcode": None,
                            "brand": None,
                            "subject_name": None,
                            "has_manual_cost": None,
                            "business_trusted": None,
                            "sort": "profit_desc",
                            "sort_by": None,
                            "limit": 50,
                            "offset": 0,
                            "sort_dir": "desc",
                        },
                    ),
                    OperatorSnapshotSpec(
                        "control_tower",
                        "control_skus",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "search": None,
                            "sku_status": None,
                            "trust_state": None,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "preset": None,
                            "has_open_actions": None,
                            "limit": 50,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "control_tower",
                        "inventory_purchase_plan",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "group_by": "article",
                            "include_blocked": True,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "status_filter": None,
                            "search": None,
                            "profit_filter": None,
                            "data_filter": None,
                            "stock_filter": None,
                            "limit": 100,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "control_tower",
                        "pricing_safety",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "only_risk": False,
                            "search": None,
                            "status": None,
                            "sort_by": None,
                            "sort_dir": "asc",
                            "limit": 100,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "control_tower",
                        "ads_efficiency",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "campaign_id": None,
                            "min_drr_percent": None,
                            "max_drr_percent": None,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "limit": 100,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "marts",
                        "marts_business_daily",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "snapshot_schema": "ads_api_fallback_v1",
                            "limit": 200,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "marts",
                        "marts_sku_daily",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "sku_id": None,
                            "nm_id": None,
                            "vendor_code": None,
                            "barcode": None,
                            "brand": None,
                            "subject_name": None,
                            "search": None,
                            "has_manual_cost": None,
                            "has_open_issues": None,
                            "aggregate": None,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "limit": 50,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "marts",
                        "marts_stock_daily",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "sku_id": None,
                            "nm_id": None,
                            "barcode": None,
                            "warehouse_name": None,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "limit": 50,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "marts",
                        "marts_finance_reconciliation",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "nm_id": None,
                            "srid": None,
                            "barcode": None,
                            "status": None,
                            "only_diff": False,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "limit": 50,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "marts",
                        "marts_account_expense_daily",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "sort_by": None,
                            "sort_dir": "desc",
                            "limit": 50,
                            "offset": 0,
                        },
                    ),
                    OperatorSnapshotSpec(
                        "marts",
                        "marts_reconciliation_daily",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "sku_id": None,
                            "nm_id": None,
                            "vendor_code": None,
                            "barcode": None,
                            "search": None,
                            "flag": None,
                            "status_bucket": None,
                            "aggregate": None,
                            "sort_by": None,
                            "sort_dir": "desc",
                            "limit": 50,
                            "offset": 0,
                        },
                    ),
                ]
            )
        return specs

    def _spec_key(
        self, spec: OperatorSnapshotSpec
    ) -> tuple[str, str, int, date | None, date | None, str]:
        return (
            spec.namespace,
            spec.endpoint_key,
            spec.account_id,
            spec.date_from,
            spec.date_to,
            json.dumps(spec.params, sort_keys=True),
        )

    def _spec_sort_key(
        self, spec: OperatorSnapshotSpec
    ) -> tuple[str, str, int, str, str, str]:
        return (
            spec.namespace,
            spec.endpoint_key,
            spec.account_id,
            spec.date_from.isoformat() if spec.date_from else "",
            spec.date_to.isoformat() if spec.date_to else "",
            json.dumps(spec.params, sort_keys=True),
        )

    def _spec_from_row(self, row: APIResponseSnapshot) -> OperatorSnapshotSpec | None:
        namespace = str(row.namespace or "")
        endpoint_key = str(row.endpoint_key or "")
        if namespace not in self.SUPPORTED_NAMESPACES:
            return None
        supported = {
            "dashboard_data_health",
            "dashboard_owner",
            "dashboard_sku_profitability",
            "dashboard_article_audit",
            "dq_issue_summary",
            "dq_issues",
            "dq_investigator_issues",
            "control_skus",
            "inventory_purchase_plan",
            "pricing_safety",
            "ads_efficiency",
            "marts_business_daily",
            "marts_reconciliation_daily",
            "marts_sku_daily",
            "marts_stock_daily",
            "marts_finance_reconciliation",
            "marts_account_expense_daily",
        }
        if endpoint_key not in supported:
            return None
        return OperatorSnapshotSpec(
            namespace=namespace,
            endpoint_key=endpoint_key,
            account_id=int(row.account_id),
            date_from=row.date_from,
            date_to=row.date_to,
            params=dict(row.request_params or {}),
        )

    async def _refresh_spec(
        self, session: AsyncSession, spec: OperatorSnapshotSpec
    ) -> None:
        if spec.endpoint_key == "dashboard_data_health":
            response = await self.dashboard.data_health(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
            )
        elif spec.endpoint_key == "dashboard_owner":
            response = await self.control_tower.owner_dashboard(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
            )
        elif spec.endpoint_key == "dashboard_sku_profitability":
            response = await self.dashboard.sku_profitability_page(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                search=spec.params.get("search"),
                vendor_code=spec.params.get("vendor_code"),
                barcode=spec.params.get("barcode"),
                brand=spec.params.get("brand"),
                subject_name=spec.params.get("subject_name"),
                has_manual_cost=spec.params.get("has_manual_cost"),
                business_trusted=spec.params.get("business_trusted"),
                sort=str(spec.params.get("sort") or "profit_desc"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "dashboard_article_audit":
            nm_id = spec.params.get("nm_id")
            if nm_id is None:
                return
            response = await self.dashboard.article_audit(
                session,
                account_id=spec.account_id,
                nm_id=int(nm_id),
                date_from=spec.date_from,
                date_to=spec.date_to,
                issues_limit=int(spec.params.get("issues_limit") or 50),
                issues_offset=int(spec.params.get("issues_offset") or 0),
            )
        elif spec.endpoint_key == "dq_issue_summary":
            response = await self._build_dq_issue_summary(
                session, account_id=spec.account_id
            )
        elif spec.endpoint_key == "dq_issues":
            response = await self.data_quality.list_issues(
                session,
                account_id=spec.account_id,
                only_open=bool(spec.params.get("only_open") or False),
                codes=self._list_param(spec.params, "code"),
                issue_types=self._list_param(spec.params, "issue_type"),
                severities=self._list_param(spec.params, "severity"),
                domains=self._list_param(spec.params, "domain"),
                source_tables=self._list_param(spec.params, "source_table"),
                classification_statuses=self._list_param(
                    spec.params, "classification_status"
                ),
                age_buckets=self._list_param(spec.params, "age_bucket"),
                status=spec.params.get("status"),
                sku_id=spec.params.get("sku_id"),
                nm_id=spec.params.get("nm_id"),
                detected_from=spec.date_from,
                detected_to=spec.date_to,
                financial_final_blocker=spec.params.get("financial_final_blocker"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 100),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "dq_investigator_issues":
            code = str(spec.params.get("code") or "")
            if not code:
                return
            response = await self.data_quality.list_investigator_issues(
                session,
                account_id=spec.account_id,
                code=code,
                limit=int(spec.params.get("limit") or 100),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "control_skus":
            response = await self.control_tower.list_control_skus(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                search=spec.params.get("search"),
                sku_status=self._list_param(spec.params, "sku_status"),
                trust_state=self._list_param(spec.params, "trust_state"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                preset=spec.params.get("preset"),
                has_open_actions=spec.params.get("has_open_actions"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "inventory_purchase_plan":
            response = await self.control_tower.list_purchase_plan(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                group_by=str(spec.params.get("group_by") or "article"),
                include_blocked=bool(spec.params.get("include_blocked", True)),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                status_filter=spec.params.get("status_filter"),
                search=spec.params.get("search"),
                profit_filter=spec.params.get("profit_filter"),
                data_filter=spec.params.get("data_filter"),
                stock_filter=spec.params.get("stock_filter"),
                limit=int(spec.params.get("limit") or 100),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "pricing_safety":
            response = await self.control_tower.list_price_safety(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                only_risk=bool(spec.params.get("only_risk") or False),
                search=spec.params.get("search"),
                status=spec.params.get("status"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "asc"),
                limit=int(spec.params.get("limit") or 100),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "ads_efficiency":
            response = await self.control_tower.list_ads_efficiency(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                campaign_id=spec.params.get("campaign_id"),
                min_drr_percent=spec.params.get("min_drr_percent"),
                max_drr_percent=spec.params.get("max_drr_percent"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 100),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "marts_business_daily":
            response = await self.marts.list_business_daily(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                limit=int(spec.params.get("limit") or 200),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "marts_reconciliation_daily":
            response = await self.marts.list_reconciliation_daily(
                session,
                account_id=spec.account_id,
                sku_id=spec.params.get("sku_id"),
                nm_id=spec.params.get("nm_id"),
                vendor_code=spec.params.get("vendor_code"),
                barcode=spec.params.get("barcode"),
                search=spec.params.get("search"),
                flag=spec.params.get("flag"),
                status_bucket=spec.params.get("status_bucket"),
                date_from=spec.date_from,
                date_to=spec.date_to,
                aggregate=spec.params.get("aggregate"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "marts_sku_daily":
            response = await self.marts.list_sku_daily(
                session,
                account_id=spec.account_id,
                sku_id=spec.params.get("sku_id"),
                nm_id=spec.params.get("nm_id"),
                vendor_code=spec.params.get("vendor_code"),
                barcode=spec.params.get("barcode"),
                brand=spec.params.get("brand"),
                subject_name=spec.params.get("subject_name"),
                search=spec.params.get("search"),
                has_manual_cost=spec.params.get("has_manual_cost"),
                has_open_issues=spec.params.get("has_open_issues"),
                date_from=spec.date_from,
                date_to=spec.date_to,
                aggregate=spec.params.get("aggregate"),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "marts_stock_daily":
            response = await self.marts.list_stock_daily(
                session,
                account_id=spec.account_id,
                sku_id=spec.params.get("sku_id"),
                nm_id=spec.params.get("nm_id"),
                barcode=spec.params.get("barcode"),
                warehouse_name=spec.params.get("warehouse_name"),
                date_from=spec.date_from,
                date_to=spec.date_to,
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "marts_finance_reconciliation":
            response = await self.marts.list_finance_reconciliation(
                session,
                account_id=spec.account_id,
                nm_id=spec.params.get("nm_id"),
                srid=spec.params.get("srid"),
                barcode=spec.params.get("barcode"),
                status=spec.params.get("status"),
                date_from=spec.date_from,
                date_to=spec.date_to,
                only_diff=bool(spec.params.get("only_diff") or False),
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "marts_account_expense_daily":
            response = await self.marts.list_account_expense_daily(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                sort_by=spec.params.get("sort_by"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        else:
            return
        model_cls = self._model_cls_for_endpoint(spec.endpoint_key)
        if model_cls is not None:
            response = model_cls.model_validate(response)
        await self._save_snapshot(
            session,
            namespace=spec.namespace,
            endpoint_key=spec.endpoint_key,
            account_id=spec.account_id,
            date_from=spec.date_from,
            date_to=spec.date_to,
            params=spec.params,
            response=response,
            auto_commit=False,
        )

    async def _refresh_spec_with_retry(self, spec: OperatorSnapshotSpec) -> None:
        for attempt in range(self.DEADLOCK_RETRIES):
            async with SessionLocal() as session:
                try:
                    await self._refresh_spec(session, spec)
                    await session.commit()
                    return
                except Exception as exc:
                    await session.rollback()
                    if (
                        not self._is_deadlock(exc)
                        or attempt + 1 >= self.DEADLOCK_RETRIES
                    ):
                        raise
                    await asyncio.sleep(0.15 * (2**attempt))

    async def refresh_account_snapshots(self, *, account_id: int) -> None:
        now = utcnow()
        async with SessionLocal() as session:
            rows = list(
                (
                    await session.execute(
                        select(APIResponseSnapshot)
                        .where(
                            APIResponseSnapshot.namespace.in_(
                                list(self.SUPPORTED_NAMESPACES)
                            ),
                            APIResponseSnapshot.account_id == account_id,
                            APIResponseSnapshot.snapshot_status == "ready",
                            APIResponseSnapshot.access_count
                            >= self.refresh_min_access_count,
                            APIResponseSnapshot.last_accessed_at
                            >= now - timedelta(days=self.active_days),
                            (
                                APIResponseSnapshot.expires_at.is_(None)
                                | (APIResponseSnapshot.expires_at <= now)
                            ),
                        )
                        .order_by(
                            APIResponseSnapshot.access_count.desc(),
                            APIResponseSnapshot.last_accessed_at.desc().nullslast(),
                            APIResponseSnapshot.updated_at.asc(),
                        )
                        .limit(self.refresh_max_specs_per_account)
                    )
                ).scalars()
            )
            specs: dict[
                tuple[str, str, int, date | None, date | None, str],
                OperatorSnapshotSpec,
            ] = {}
            for spec in self._default_specs_for_account(account_id=account_id):
                specs[self._spec_key(spec)] = spec
            for row in rows:
                spec = self._spec_from_row(row)
                if spec is None:
                    continue
                specs[self._spec_key(spec)] = spec
        for spec in sorted(specs.values(), key=lambda item: self._spec_sort_key(item)):
            await self._refresh_spec_with_retry(spec)

    async def refresh_active_account_snapshots(self) -> None:
        async with SessionLocal() as session:
            account_ids = list(
                (
                    await session.execute(
                        select(WBAccount.id).where(WBAccount.is_active.is_(True))
                    )
                ).scalars()
            )
        for account_id in account_ids:
            await self.refresh_account_snapshots(account_id=int(account_id))
