from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, TypeVar, cast

from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.cache import TTLMemoryCache
from app.core.db import SessionLocal
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.response_snapshots import APIResponseSnapshot
from app.schemas.money_management import (
    DataBlockersRead,
    ExpenseBreakdownSummaryRead,
    MoneyArticleDetailRead,
    MoneyArticlePage,
    MoneyCardDetailRead,
    MoneyCardPage,
    MoneyExpenseLogisticsRead,
    MoneySummaryRead,
    ProfitCascadeRead,
    TodayActionsPage,
)
from app.services.money_management import MoneyManagementService

SnapshotModelT = TypeVar("SnapshotModelT", bound=BaseModel)


@dataclass(frozen=True)
class MoneySnapshotSpec:
    endpoint_key: str
    account_id: int
    date_from: date
    date_to: date
    params: dict[str, Any]


class MoneyEndpointSnapshotService:
    NAMESPACE = "money"
    DEADLOCK_RETRIES = 3
    MEMORY_CACHE_TTL_SECONDS = 30
    _shared_response_cache: TTLMemoryCache[BaseModel] = TTLMemoryCache(
        default_ttl_seconds=MEMORY_CACHE_TTL_SECONDS
    )

    def __init__(self) -> None:
        self.money = MoneyManagementService()
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
        return self.money._date_range(date_from, date_to)

    @staticmethod
    def _normalize_param_value(value: Any) -> Any:
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        if isinstance(value, dict):
            return {
                str(key): MoneyEndpointSnapshotService._normalize_param_value(inner)
                for key, inner in value.items()
            }
        if isinstance(value, (list, tuple)):
            return [
                MoneyEndpointSnapshotService._normalize_param_value(item)
                for item in value
            ]
        return value

    def _params_hash(
        self,
        *,
        endpoint_key: str,
        account_id: int,
        date_from: date,
        date_to: date,
        params: dict[str, Any],
    ) -> str:
        payload = {
            "endpoint_key": endpoint_key,
            "account_id": account_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "params": self._normalize_param_value(params),
        }
        encoded = json.dumps(
            payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")
        )
        return hashlib.sha1(encoded.encode("utf-8"), usedforsecurity=False).hexdigest()

    def _response_cache_key(
        self,
        *,
        endpoint_key: str,
        account_id: int,
        date_from: date,
        date_to: date,
        params: dict[str, Any],
    ) -> tuple[object, ...]:
        return (
            self.NAMESPACE,
            endpoint_key,
            int(account_id),
            date_from.isoformat(),
            date_to.isoformat(),
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
        endpoint_key: str,
        account_id: int,
        date_from: date,
        date_to: date,
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
                    APIResponseSnapshot.namespace == self.NAMESPACE,
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
        return payload.model_copy(
            deep=True,
            update={
                "computed_at": row.computed_at,
                "cache_status": cache_status,
            },
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
        endpoint_key: str,
        account_id: int,
        date_from: date,
        date_to: date,
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
                        namespace=self.NAMESPACE,
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
            namespace=self.NAMESPACE,
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
        endpoint_key: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        params: dict[str, Any],
        model_cls: type[SnapshotModelT],
        compute: Any,
    ) -> SnapshotModelT:
        actual_from, actual_to = self._normalize_window(date_from, date_to)
        response_cache_key = self._response_cache_key(
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            params=params,
        )
        cached = self._response_cache.get(response_cache_key)
        if cached is not None:
            return cast(SnapshotModelT, cached)
        snapshot = await self._load_snapshot(
            session,
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            params=params,
            model_cls=model_cls,
        )
        if snapshot is not None:
            self._response_cache.set(response_cache_key, snapshot)
            return snapshot
        response = await compute(actual_from, actual_to)
        await self._save_snapshot(
            session,
            endpoint_key=endpoint_key,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
            params=params,
            response=response,
        )
        self._response_cache.set(response_cache_key, response)
        return response

    async def invalidate_snapshots(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        endpoint_keys: set[str] | None = None,
    ) -> None:
        stmt = (
            update(APIResponseSnapshot)
            .where(APIResponseSnapshot.namespace == self.NAMESPACE)
            .values(
                snapshot_status="invalidated",
                expires_at=utcnow(),
                updated_at=func.now(),
            )
        )
        if account_id is not None:
            stmt = stmt.where(APIResponseSnapshot.account_id == account_id)
        if endpoint_keys:
            stmt = stmt.where(APIResponseSnapshot.endpoint_key.in_(list(endpoint_keys)))
        await session.execute(stmt)
        self._response_cache.clear()

    async def summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> MoneySummaryRead:
        return await self._get_or_compute(
            session,
            endpoint_key="money_summary",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params={"formula_version": self.money.SUMMARY_FORMULA_VERSION},
            model_cls=MoneySummaryRead,
            compute=lambda actual_from, actual_to: self.money.summary(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
        )

    async def profit_cascade(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> ProfitCascadeRead:
        return await self._get_or_compute(
            session,
            endpoint_key="money_profit_cascade",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params={"formula_version": self.money.SUMMARY_FORMULA_VERSION},
            model_cls=ProfitCascadeRead,
            compute=lambda actual_from, actual_to: self.money.profit_cascade(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
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
        params = {
            "formula_version": self.money.SUMMARY_FORMULA_VERSION,
            "group_by": group_by,
            "include_unallocated": include_unallocated,
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_expense_breakdown",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=ExpenseBreakdownSummaryRead,
            compute=lambda actual_from, actual_to: self.money.expense_breakdown(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                group_by=group_by,
                include_unallocated=include_unallocated,
            ),
        )

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
        params = {
            "formula_version": self.money.SUMMARY_FORMULA_VERSION,
            "include_unallocated": include_unallocated,
            "top_n": top_n,
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_expense_logistics",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=MoneyExpenseLogisticsRead,
            compute=lambda actual_from, actual_to: self.money.expense_logistics(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                include_unallocated=include_unallocated,
                top_n=top_n,
            ),
        )

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
        params = {
            "search": search,
            "status": status,
            "next_action": next_action,
            "trust_state": trust_state,
            "subject_name": subject_name,
            "brand": brand,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_cards",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=MoneyCardPage,
            compute=lambda actual_from, actual_to: self.money.cards(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                search=search,
                status=status,
                next_action=next_action,
                trust_state=trust_state,
                subject_name=subject_name,
                brand=brand,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
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
        params = {
            "sku_id": int(sku_id),
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_card_detail",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=MoneyCardDetailRead,
            compute=lambda actual_from, actual_to: self.money.card_detail(
                session,
                account_id=account_id,
                sku_id=sku_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
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
        params = {
            "summary_version": 2,
            "search": search,
            "status": status,
            "trust_state": trust_state,
            "subject_name": subject_name,
            "brand": brand,
            "sort_by": sort_by,
            "sort_dir": sort_dir,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_articles",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=MoneyArticlePage,
            compute=lambda actual_from, actual_to: self.money.articles(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                search=search,
                status=status,
                trust_state=trust_state,
                subject_name=subject_name,
                brand=brand,
                sort_by=sort_by,
                sort_dir=sort_dir,
                limit=limit,
                offset=offset,
            ),
        )

    async def article_detail(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        include_audit: bool = False,
    ) -> MoneyArticleDetailRead:
        params = {
            "nm_id": int(nm_id),
            "include_audit": bool(include_audit),
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_article_detail",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=MoneyArticleDetailRead,
            compute=lambda actual_from, actual_to: self.money.article_detail(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=actual_from,
                date_to=actual_to,
                include_audit=include_audit,
            ),
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
        params = {
            "priority": priority,
            "status": status,
            "action_type": action_type,
            "group_by": group_by,
            "focus_limit": focus_limit,
            "limit": limit,
            "offset": offset,
        }
        return await self._get_or_compute(
            session,
            endpoint_key="money_actions_today",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params=params,
            model_cls=TodayActionsPage,
            compute=lambda actual_from, actual_to: self.money.today_actions(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
                priority=priority,
                status=status,
                action_type=action_type,
                group_by=group_by,
                focus_limit=focus_limit,
                limit=limit,
                offset=offset,
            ),
        )

    async def data_blockers(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> DataBlockersRead:
        return await self._get_or_compute(
            session,
            endpoint_key="money_data_blockers",
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            params={},
            model_cls=DataBlockersRead,
            compute=lambda actual_from, actual_to: self.money.data_blockers(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            ),
        )

    def _default_specs_for_account(self, *, account_id: int) -> list[MoneySnapshotSpec]:
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
        specs: list[MoneySnapshotSpec] = []
        for window_from, window_to in sorted(windows):
            specs.extend(
                [
                    MoneySnapshotSpec(
                        "money_summary",
                        account_id,
                        window_from,
                        window_to,
                        {"formula_version": self.money.SUMMARY_FORMULA_VERSION},
                    ),
                    MoneySnapshotSpec(
                        "money_profit_cascade",
                        account_id,
                        window_from,
                        window_to,
                        {"formula_version": self.money.SUMMARY_FORMULA_VERSION},
                    ),
                    MoneySnapshotSpec(
                        "money_expense_breakdown",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "formula_version": self.money.SUMMARY_FORMULA_VERSION,
                            "group_by": "category",
                            "include_unallocated": True,
                        },
                    ),
                    MoneySnapshotSpec(
                        "money_expense_logistics",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "formula_version": self.money.SUMMARY_FORMULA_VERSION,
                            "include_unallocated": True,
                            "top_n": 100,
                        },
                    ),
                    MoneySnapshotSpec(
                        "money_data_blockers", account_id, window_from, window_to, {}
                    ),
                ]
            )
            for limit in (10, 20, 100):
                specs.append(
                    MoneySnapshotSpec(
                        "money_actions_today",
                        account_id,
                        window_from,
                        window_to,
                        {
                            "priority": None,
                            "status": None,
                            "action_type": None,
                            "group_by": "article",
                            "focus_limit": 10,
                            "limit": limit,
                            "offset": 0,
                        },
                    )
                )
            for endpoint_key, limits in {
                "money_cards": (8, 10, 50),
                "money_articles": (8, 10, 50, 200),
            }.items():
                for limit in limits:
                    specs.append(
                        MoneySnapshotSpec(
                            endpoint_key,
                            account_id,
                            window_from,
                            window_to,
                            {
                                **(
                                    {"summary_version": 2}
                                    if endpoint_key == "money_articles"
                                    else {}
                                ),
                                "search": None,
                                "status": None,
                                "trust_state": None,
                                "subject_name": None,
                                "brand": None,
                                "sort_by": "priority_score",
                                "sort_dir": "desc",
                                "limit": limit,
                                "offset": 0,
                                **(
                                    {"next_action": None}
                                    if endpoint_key == "money_cards"
                                    else {}
                                ),
                            },
                        )
                    )
        return specs

    def _spec_from_row(self, row: APIResponseSnapshot) -> MoneySnapshotSpec | None:
        params = dict(row.request_params or {})
        endpoint_key = str(row.endpoint_key or "")
        if endpoint_key not in {
            "money_summary",
            "money_profit_cascade",
            "money_expense_breakdown",
            "money_expense_logistics",
            "money_data_blockers",
            "money_actions_today",
            "money_cards",
            "money_card_detail",
            "money_articles",
            "money_article_detail",
        }:
            return None
        if row.date_from is None or row.date_to is None:
            return None
        return MoneySnapshotSpec(
            endpoint_key=endpoint_key,
            account_id=int(row.account_id),
            date_from=row.date_from,
            date_to=row.date_to,
            params=params,
        )

    def _spec_key(self, spec: MoneySnapshotSpec) -> tuple[str, int, date, date, str]:
        return (
            spec.endpoint_key,
            spec.account_id,
            spec.date_from,
            spec.date_to,
            json.dumps(spec.params, sort_keys=True),
        )

    def _spec_sort_key(self, spec: MoneySnapshotSpec) -> tuple[str, date, date, str]:
        return (
            spec.endpoint_key,
            spec.date_from,
            spec.date_to,
            json.dumps(spec.params, sort_keys=True),
        )

    async def _refresh_spec(
        self, session: AsyncSession, spec: MoneySnapshotSpec
    ) -> None:
        if spec.endpoint_key == "money_summary":
            response = await self.money.summary(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
            )
        elif spec.endpoint_key == "money_profit_cascade":
            response = await self.money.profit_cascade(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
            )
        elif spec.endpoint_key == "money_expense_breakdown":
            response = await self.money.expense_breakdown(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                group_by=str(spec.params.get("group_by") or "category"),
                include_unallocated=bool(spec.params.get("include_unallocated", True)),
            )
        elif spec.endpoint_key == "money_expense_logistics":
            response = await self.money.expense_logistics(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                include_unallocated=bool(spec.params.get("include_unallocated", True)),
                top_n=int(spec.params.get("top_n") or 100),
            )
        elif spec.endpoint_key == "money_data_blockers":
            response = await self.money.data_blockers(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
            )
        elif spec.endpoint_key == "money_actions_today":
            response = await self.money.today_actions(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                priority=spec.params.get("priority"),
                status=spec.params.get("status"),
                action_type=spec.params.get("action_type"),
                group_by=str(spec.params.get("group_by") or "article"),
                focus_limit=int(spec.params.get("focus_limit") or 10),
                limit=int(spec.params.get("limit") or 100),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "money_cards":
            response = await self.money.cards(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                search=spec.params.get("search"),
                status=spec.params.get("status"),
                next_action=spec.params.get("next_action"),
                trust_state=spec.params.get("trust_state"),
                subject_name=spec.params.get("subject_name"),
                brand=spec.params.get("brand"),
                sort_by=str(spec.params.get("sort_by") or "priority_score"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "money_card_detail":
            sku_id = spec.params.get("sku_id")
            if sku_id is None:
                return
            response = await self.money.card_detail(
                session,
                account_id=spec.account_id,
                sku_id=int(sku_id),
                date_from=spec.date_from,
                date_to=spec.date_to,
            )
        elif spec.endpoint_key == "money_articles":
            response = await self.money.articles(
                session,
                account_id=spec.account_id,
                date_from=spec.date_from,
                date_to=spec.date_to,
                search=spec.params.get("search"),
                status=spec.params.get("status"),
                trust_state=spec.params.get("trust_state"),
                subject_name=spec.params.get("subject_name"),
                brand=spec.params.get("brand"),
                sort_by=str(spec.params.get("sort_by") or "priority_score"),
                sort_dir=str(spec.params.get("sort_dir") or "desc"),
                limit=int(spec.params.get("limit") or 50),
                offset=int(spec.params.get("offset") or 0),
            )
        elif spec.endpoint_key == "money_article_detail":
            nm_id = spec.params.get("nm_id")
            if nm_id is None:
                return
            response = await self.money.article_detail(
                session,
                account_id=spec.account_id,
                nm_id=int(nm_id),
                date_from=spec.date_from,
                date_to=spec.date_to,
                include_audit=bool(spec.params.get("include_audit") or False),
            )
        else:
            return
        await self._save_snapshot(
            session,
            endpoint_key=spec.endpoint_key,
            account_id=spec.account_id,
            date_from=spec.date_from,
            date_to=spec.date_to,
            params=spec.params,
            response=response,
            auto_commit=False,
        )

    async def _refresh_spec_with_retry(self, spec: MoneySnapshotSpec) -> None:
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
                            APIResponseSnapshot.namespace == self.NAMESPACE,
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
            specs: dict[tuple[str, int, date, date, str], MoneySnapshotSpec] = {}
            for spec in self._default_specs_for_account(account_id=account_id):
                specs[self._spec_key(spec)] = spec
            for row in rows:
                spec = self._spec_from_row(row)
                if spec is None:
                    continue
                specs[self._spec_key(spec)] = spec
        for spec in sorted(specs.values(), key=self._spec_sort_key):
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
