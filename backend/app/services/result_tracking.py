from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.control_tower import ActionRecommendation
from app.models.marts import MartSKUDaily
from app.models.operator import ResultEvent, UnifiedAction
from app.models.problem_engine import ProblemInstance
from app.models.product_cards import CoreSKU
from app.schemas.portal import (
    PortalResultEventCreate,
    PortalResultEventRead,
    PortalResultEventsPage,
)

# Experiment result events must sanitize every payload before persistence:
# payload=self._safe_snapshot(payload)

POSITIVE_METRICS = {
    "revenue",
    "profit",
    "margin",
    "margin_pct",
    "conversion",
    "rating",
    "orders",
    "buyouts",
    "cost_coverage",
    "compensation_amount",
    "stock_days_left",
    "unit_profit",
    "unit_profit_after_ads",
    "roas",
    "quality_score",
    "sales_velocity",
}
NEGATIVE_METRICS = {
    "ad_spend",
    "returns",
    "defects",
    "penalties",
    "cancellations",
    "stockout_days",
    "surplus_stock",
    "open_issue_count",
    "drr",
}
BASE_ACTION_EFFECT_METRICS = {
    "revenue",
    "profit",
    "orders",
    "rating",
    "compensation_amount",
}
PRODUCT_RESULT_METRICS: dict[str, tuple[str, ...]] = {
    "low_stock_risk": ("stock_days_left", "orders", "stockout_days"),
    "fast_stock_depletion": ("stock_days_left", "orders", "stockout_days"),
    "overstock_slow_moving": ("days_of_stock", "sales_velocity", "surplus_stock"),
    "overstock": ("days_of_stock", "sales_velocity", "surplus_stock"),
    "dead_stock": ("days_of_stock", "sales_velocity", "surplus_stock"),
    "negative_unit_profit": ("unit_profit", "margin_pct"),
    "ads_spend_without_profit": ("ad_spend", "unit_profit_after_ads", "roas", "drr"),
    "ad_spend_without_profit": ("ad_spend", "unit_profit_after_ads", "roas", "drr"),
    "card_quality_issue": ("quality_score", "open_issue_count"),
    "card_quality_fix": ("quality_score", "open_issue_count"),
}
RESULT_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "stock_days_left": ("stock_days_left", "days_of_stock", "stock_days"),
    "orders": (
        "orders",
        "orders_7d",
        "orders_qty",
        "order_qty",
        "sales_qty",
        "final_sales_qty",
        "buyouts",
    ),
    "stockout_days": ("stockout_days", "out_of_stock_days"),
    "days_of_stock": ("days_of_stock", "stock_days"),
    "sales_velocity": (
        "sales_velocity",
        "sales_velocity_daily",
        "avg_daily_sales_7d",
        "avg_daily_sales_14d",
    ),
    "surplus_stock": ("surplus_stock", "overstock_qty", "stock_surplus_qty"),
    "unit_profit": ("unit_profit", "profit"),
    "margin_pct": ("margin_pct", "margin_percent", "margin"),
    "ad_spend": ("ad_spend", "ad_spend_7d", "ads_spend"),
    "unit_profit_after_ads": ("unit_profit_after_ads", "profit_after_ads"),
    "roas": ("roas", "ROAS"),
    "drr": ("drr", "drr_pct", "drr_percent", "DRR"),
    "quality_score": ("quality_score", "card_quality_score"),
    "open_issue_count": (
        "open_issue_count",
        "open_issues",
        "issue_count",
        "card_quality_issue_count",
    ),
}
ACTION_EFFECT_METRICS = BASE_ACTION_EFFECT_METRICS | {
    metric for metrics in PRODUCT_RESULT_METRICS.values() for metric in metrics
}
DISCLAIMER = "Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."
CALCULATION_NOTE = DISCLAIMER
RESULT_MODULES = (
    "action_center",
    "problem_engine",
    "profit_doctor",
    "claims",
    "reputation",
    "experiments",
    "checker",
    "photo",
    "grouping",
    "stockops",
)
OUTCOME_CATEGORIES = (
    "improved",
    "worse",
    "neutral",
    "pending",
    "blocked",
    "not_enough_data",
)
RESULT_STATUS_ALIASES = {
    "pending_data": "pending_data",
    "pending": "pending_data",
    "waiting_for_data": "pending_data",
    "not_enough_data": "not_enough_data",
    "missing_data": "not_enough_data",
    "improved": "improved",
    "worse": "worse",
    "neutral": "neutral",
}
MEASURED_RESULT_STATUSES = {"improved", "worse", "neutral"}
PROBLEM_ACTION_EVENT_TYPES = {
    "action_started",
    "action_completed",
    "status_changed",
    "cost_uploaded",
    "card_issue_fixed",
    "photo_changed",
    "photo_fix_started",
    "photo_fix_completed",
    "photo_fix_skipped",
    "title_changed",
    "description_changed",
    "price_changed",
    "ad_review_done",
    "stock_action_done",
    "grouping_review_completed",
}


class ResultTrackingService:
    source_module = "result_tracking"

    async def create_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        payload: PortalResultEventCreate,
        created_by: int | None,
    ) -> PortalResultEventRead:
        action = await self._action_context(
            session, action_id=action_id, account_id=account_id
        )
        before = self._safe_snapshot(
            dict(payload.before_snapshot or {})
            or dict(action.get("before_snapshot") or {})
        )
        after = self._safe_snapshot(dict(payload.after_snapshot or {}))
        comparison = self.compare(before, after)
        event = ResultEvent(
            account_id=account_id,
            action_id=action_id if action.get("kind") == "unified" else None,
            source_module=self.source_module,
            source_id=str(action_id),
            external_id=str(action_id),
            nm_id=payload.nm_id if payload.nm_id is not None else action.get("nm_id"),
            vendor_code=action.get("vendor_code"),
            event_type=payload.event_type,
            status="done",
            message=payload.message or self._message(comparison["outcome"]),
            payload_json={
                **(payload.payload or {}),
                "action_id": action_id,
                "action_kind": action.get("kind"),
                "legacy_action_id": action_id
                if action.get("kind") == "legacy"
                else None,
                "sku_id": payload.sku_id
                if payload.sku_id is not None
                else action.get("sku_id"),
                "before_snapshot": before,
                "after_snapshot": after,
                "snapshot_day": payload.snapshot_day,
                "comparison": comparison,
                "outcome": comparison["outcome"],
                "created_by": created_by,
                "causality_note": DISCLAIMER,
            },
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        self._add_result_notification_if_measured(
            session,
            event=event,
            outcome=str(comparison.get("outcome") or ""),
            created_by=created_by,
        )
        return self._read(event)

    async def ensure_before_snapshot(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        created_by: int | None,
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        existing = await session.execute(
            select(ResultEvent.id)
            .where(
                ResultEvent.account_id == account_id,
                ResultEvent.source_module == self.source_module,
                ResultEvent.source_id == str(action_id),
                ResultEvent.event_type == "before_snapshot",
            )
            .limit(1)
        )
        if next(iter(existing.scalars()), None) is not None:
            return
        action = await self._action_context(
            session, action_id=action_id, account_id=account_id
        )
        before = self._safe_snapshot(
            dict(snapshot or {})
            or dict(action.get("before_snapshot") or {})
            or self._default_action_snapshot(action)
        )
        session.add(
            ResultEvent(
                account_id=account_id,
                action_id=action_id if action.get("kind") == "unified" else None,
                source_module=self.source_module,
                source_id=str(action_id),
                external_id=str(action_id),
                nm_id=action.get("nm_id"),
                vendor_code=action.get("vendor_code"),
                event_type="before_snapshot",
                status="done",
                message="Снимок «до» сохранён для последующего сравнения результата.",
                payload_json={
                    "action_id": action_id,
                    "action_kind": action.get("kind"),
                    "legacy_action_id": action_id
                    if action.get("kind") == "legacy"
                    else None,
                    "sku_id": action.get("sku_id"),
                    "before_snapshot": before,
                    "after_snapshot": {},
                    "snapshot_day": 0,
                    "comparison": {"outcome": "not_enough_data", "metrics": {}},
                    "outcome": "not_enough_data",
                    "created_by": created_by,
                    "causality_note": DISCLAIMER,
                },
            )
        )

    async def create_action_completed_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int,
        created_by: int | None,
        after_snapshot: dict[str, Any] | None = None,
    ) -> PortalResultEventRead:
        await self.ensure_before_snapshot(
            session, account_id=account_id, action_id=action_id, created_by=created_by
        )
        before = await self._latest_before_snapshot(
            session, account_id=account_id, action_id=action_id
        )
        return await self.create_event(
            session,
            account_id=account_id,
            action_id=action_id,
            payload=PortalResultEventCreate(
                event_type="action_completed",
                before_snapshot=before,
                after_snapshot=self._safe_snapshot(after_snapshot or {}),
                snapshot_day=0,
                message="Действие отмечено выполненным. Сравнение эффекта показывает корреляцию, а не гарантированную причинность.",
                payload={
                    "saved_money_claimed": False,
                    "money_note": "Ожидаемый эффект не считается сэкономленными деньгами, пока нет измеренных данных после действия.",
                },
            ),
            created_by=created_by,
        )

    async def ensure_problem_before_snapshot(
        self,
        session: AsyncSession,
        *,
        problem_instance_id: int,
        created_by: int | None = None,
    ) -> None:
        problem = await self._problem_context(
            session, problem_instance_id=problem_instance_id
        )
        existing = await session.execute(
            select(ResultEvent.id)
            .where(
                ResultEvent.account_id == problem.account_id,
                ResultEvent.problem_instance_id == problem.id,
                ResultEvent.source_module == "problem_engine",
                ResultEvent.event_type == "before_snapshot",
            )
            .limit(1)
        )
        if next(iter(existing.scalars()), None) is not None:
            return
        before = self._problem_before_snapshot(problem)
        session.add(
            ResultEvent(
                account_id=problem.account_id,
                problem_instance_id=problem.id,
                problem_code=problem.problem_code,
                source_module="problem_engine",
                source_id=str(problem.id),
                external_id=str(problem.id),
                nm_id=problem.nm_id,
                vendor_code=problem.vendor_code,
                event_type="before_snapshot",
                status="done",
                message="Снимок «до» сохранён для отслеживания результата динамической проблемы.",
                payload_json=self._problem_event_payload(
                    problem,
                    before_snapshot=before,
                    current_snapshot=self._problem_current_snapshot(problem),
                    after_snapshot={},
                    comparison={
                        "outcome": "not_enough_data",
                        "metrics": {},
                        "causality": "not_claimed",
                    },
                    outcome="not_enough_data",
                    created_by=created_by,
                ),
            )
        )
        await session.flush()

    async def create_problem_status_event(
        self,
        session: AsyncSession,
        *,
        problem_instance_id: int,
        old_status: str | None = None,
        new_status: str | None = None,
        comment: str | None = None,
        created_by: int | None = None,
    ) -> PortalResultEventRead:
        problem = await self._problem_context(
            session, problem_instance_id=problem_instance_id
        )
        await self.ensure_problem_before_snapshot(
            session, problem_instance_id=problem.id, created_by=created_by
        )
        normalized_status = str(new_status or problem.status or "new")
        event_type = (
            "action_started" if normalized_status == "in_progress" else "status_changed"
        )
        payload = self._problem_event_payload(
            problem,
            before_snapshot=await self._latest_problem_before_snapshot(
                session, problem=problem
            ),
            current_snapshot=self._problem_current_snapshot(problem),
            after_snapshot={},
            comparison={
                "outcome": "pending",
                "metrics": {},
                "causality": "not_claimed",
            },
            outcome="pending",
            created_by=created_by,
            extra={
                "old_status": old_status,
                "new_status": normalized_status,
                "comment": comment,
            },
        )
        event = ResultEvent(
            account_id=problem.account_id,
            problem_instance_id=problem.id,
            problem_code=problem.problem_code,
            source_module="problem_engine",
            source_id=str(problem.id),
            external_id=str(problem.id),
            nm_id=problem.nm_id,
            vendor_code=problem.vendor_code,
            event_type=event_type,
            status=normalized_status,
            message=comment
            or f"Статус динамической проблемы изменён на {normalized_status}.",
            payload_json=payload,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return self._read(event)

    def _add_result_notification_if_measured(
        self,
        session: AsyncSession,
        *,
        event: ResultEvent,
        outcome: str,
        created_by: int | None,
    ) -> None:
        normalized = str(outcome or "").strip().lower()
        if normalized not in {"improved", "worse"}:
            return
        source_payload = dict(event.payload_json or {})
        notification_type = (
            "result_improved" if normalized == "improved" else "result_worsened"
        )
        session.add(
            ResultEvent(
                account_id=event.account_id,
                action_id=event.action_id,
                problem_instance_id=event.problem_instance_id,
                problem_code=event.problem_code,
                source_module="action_center_notifications",
                source_id=event.source_id,
                external_id=event.external_id,
                nm_id=event.nm_id,
                vendor_code=event.vendor_code,
                event_type="action_center_notification",
                status="new",
                message=(
                    "Измеренный результат улучшился после работы в Центре действий."
                    if normalized == "improved"
                    else "Измеренный результат ухудшился после работы в Центре действий."
                ),
                payload_json={
                    "notification_type": notification_type,
                    "outcome": normalized,
                    "source_event_id": str(event.id),
                    "source_event_type": event.event_type,
                    "created_by": created_by,
                    "marketplace_change": source_payload.get(
                        "marketplace_change", False
                    ),
                    "saved_money_claimed": False,
                    "causality_note": DISCLAIMER,
                },
            )
        )

    async def create_problem_completed_event(
        self,
        session: AsyncSession,
        *,
        problem_instance_id: int,
        created_by: int | None = None,
        after_snapshot: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> PortalResultEventRead:
        problem = await self._problem_context(
            session, problem_instance_id=problem_instance_id
        )
        await self.ensure_problem_before_snapshot(
            session, problem_instance_id=problem.id, created_by=created_by
        )
        before = await self._latest_problem_before_snapshot(session, problem=problem)
        after = self._safe_snapshot(dict(after_snapshot or {}))
        comparison = self.compare(before, after, problem_code=problem.problem_code)
        event = ResultEvent(
            account_id=problem.account_id,
            problem_instance_id=problem.id,
            problem_code=problem.problem_code,
            source_module="problem_engine",
            source_id=str(problem.id),
            external_id=str(problem.id),
            nm_id=problem.nm_id,
            vendor_code=problem.vendor_code,
            event_type="action_completed",
            status=str(problem.status or "done"),
            message=comment
            or "Действие по динамической проблеме отмечено выполненным. Эффект оценивается как корреляция только при наличии данных после действия.",
            payload_json=self._problem_event_payload(
                problem,
                before_snapshot=before,
                current_snapshot=self._problem_current_snapshot(problem),
                after_snapshot=after,
                comparison=comparison,
                outcome=str(comparison.get("outcome") or "not_enough_data"),
                created_by=created_by,
                extra={
                    "saved_money_claimed": False,
                    "money_note": "Ожидаемый эффект не считается сэкономленными деньгами, пока нет измеренных данных после действия.",
                },
            ),
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        self._add_result_notification_if_measured(
            session,
            event=event,
            outcome=str(comparison.get("outcome") or ""),
            created_by=created_by,
        )
        return self._read(event)

    async def create_problem_recheck_event(
        self,
        session: AsyncSession,
        *,
        problem_instance_id: int,
        created_by: int | None = None,
        run_log_id: int | None = None,
        status: str | None = None,
        message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> PortalResultEventRead:
        problem = await self._problem_context(
            session, problem_instance_id=problem_instance_id
        )
        await self.ensure_problem_before_snapshot(
            session, problem_instance_id=problem.id, created_by=created_by
        )
        before = await self._latest_problem_before_snapshot(session, problem=problem)
        payload_data = dict(payload or {})
        after = self._safe_snapshot(dict(payload_data.get("after_snapshot") or {}))
        comparison_payload = payload_data.get("comparison")
        comparison = (
            dict(comparison_payload)
            if isinstance(comparison_payload, dict)
            else self.compare(before, after, problem_code=problem.problem_code)
        )
        outcome = str(comparison.get("outcome") or "not_enough_data")
        event = ResultEvent(
            account_id=problem.account_id,
            problem_instance_id=problem.id,
            problem_code=problem.problem_code,
            source_module="problem_engine",
            source_id=str(problem.id),
            external_id=str(problem.id),
            nm_id=problem.nm_id,
            vendor_code=problem.vendor_code,
            event_type="recheck_result",
            status=str(status or problem.status or "done"),
            message=message
            or "Dynamic problem re-check completed. Result remains correlation only until measured after-data exists.",
            payload_json=self._problem_event_payload(
                problem,
                before_snapshot=before,
                current_snapshot=self._problem_current_snapshot(problem),
                after_snapshot=after,
                comparison=comparison,
                outcome=outcome,
                created_by=created_by,
                extra={
                    "run_log_id": run_log_id,
                    "recheck_payload": payload_data,
                    "saved_money_claimed": False,
                },
            ),
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return self._read(event)

    async def list_results(
        self,
        session: AsyncSession,
        *,
        account_id: int,
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
        limit: int = 50,
        offset: int = 0,
    ) -> PortalResultEventsPage:
        filters = [ResultEvent.account_id == account_id]
        if action_id is not None:
            filters.append(
                or_(
                    ResultEvent.action_id == action_id,
                    ResultEvent.source_id == str(action_id),
                )
            )
        if problem_instance_id is not None:
            filters.append(ResultEvent.problem_instance_id == problem_instance_id)
        if problem_code:
            filters.append(ResultEvent.problem_code == problem_code)
        if nm_id is not None:
            filters.append(ResultEvent.nm_id == nm_id)
        if source_module:
            filters.append(
                ResultEvent.source_module.in_(
                    self._source_module_filter_values(source_module)
                )
            )
        if event_type:
            filters.append(ResultEvent.event_type == event_type)
        search_text = str(search or "").strip()
        if search_text:
            pattern = f"%{search_text}%"
            filters.append(
                or_(
                    ResultEvent.message.ilike(pattern),
                    ResultEvent.source_module.ilike(pattern),
                    ResultEvent.source_id.ilike(pattern),
                    ResultEvent.external_id.ilike(pattern),
                    ResultEvent.problem_code.ilike(pattern),
                    ResultEvent.event_type.ilike(pattern),
                    ResultEvent.vendor_code.ilike(pattern),
                    cast(ResultEvent.nm_id, String).ilike(pattern),
                    cast(ResultEvent.action_id, String).ilike(pattern),
                    cast(ResultEvent.problem_instance_id, String).ilike(pattern),
                )
            )
        if date_from is not None:
            filters.append(
                ResultEvent.created_at
                >= datetime.combine(date_from, time.min, tzinfo=timezone.utc)
            )
        if date_to is not None:
            filters.append(
                ResultEvent.created_at
                <= datetime.combine(date_to, time.max, tzinfo=timezone.utc)
            )
        if trust_state or impact_type:
            problem_filters = [ProblemInstance.account_id == account_id]
            if trust_state:
                problem_filters.append(ProblemInstance.trust_state == trust_state)
            if impact_type:
                problem_filters.append(ProblemInstance.impact_type == impact_type)
            filters.append(
                ResultEvent.problem_instance_id.in_(
                    select(ProblemInstance.id).where(*problem_filters)
                )
            )

        normalized_result_status = self._normalize_result_status(result_status)
        base_query = (
            select(ResultEvent)
            .where(*filters)
            .order_by(ResultEvent.created_at.desc(), ResultEvent.id.desc())
        )
        status_filtered_items: list[PortalResultEventRead] | None = None
        if normalized_result_status is not None:
            result = await session.execute(base_query)
            status_filtered_items = [
                item
                for item in [self._read(event) for event in result.scalars()]
                if self._item_result_status(item) == normalized_result_status
            ]
            total = len(status_filtered_items)
            items = status_filtered_items[offset : offset + limit]
        else:
            total = int(
                (
                    await session.execute(
                        select(func.count()).select_from(ResultEvent).where(*filters)
                    )
                ).scalar_one()
                or 0
            )
            result = await session.execute(base_query.limit(limit).offset(offset))
            items = [self._read(event) for event in result.scalars()]
        if status_filtered_items is not None:
            all_items = status_filtered_items[:1000]
        else:
            all_result = await session.execute(base_query.limit(1000))
            all_items = [self._read(event) for event in all_result.scalars()]
        all_items = await self._attach_product_identity(
            session, account_id=account_id, items=all_items
        )
        all_items = await self._attach_result_context(
            session, account_id=account_id, items=all_items
        )
        items = await self._attach_product_identity(
            session, account_id=account_id, items=items
        )
        items = await self._attach_result_context(
            session, account_id=account_id, items=items, peer_items=all_items
        )
        summary_items = all_items or items
        summary = self.effect_summary(summary_items)
        finance_windows = await self.finance_window_summaries(
            session,
            account_id=account_id,
            action_id=action_id,
            nm_id=nm_id,
            items=summary_items,
        )
        summary["windows"] = finance_windows
        return PortalResultEventsPage(
            total=total,
            limit=limit,
            offset=offset,
            summary=summary,
            by_module=self.by_module_summary(summary_items),
            by_outcome=self.by_outcome_summary(summary_items),
            recent_events=items,
            pending_followups=self.pending_followups(summary_items),
            finance_windows=finance_windows,
            disclaimer=DISCLAIMER,
            items=items,
        )

    def empty_page(
        self, *, limit: int, offset: int, unavailable_sources: list[str] | None = None
    ) -> PortalResultEventsPage:
        items: list[PortalResultEventRead] = []
        return PortalResultEventsPage(
            total=0,
            limit=limit,
            offset=offset,
            summary=self.effect_summary(items),
            by_module=self.by_module_summary(items),
            by_outcome=self.by_outcome_summary(items),
            recent_events=[],
            pending_followups=[],
            finance_windows={},
            disclaimer=DISCLAIMER,
            items=[],
            unavailable_sources=list(unavailable_sources or []),
        )

    def effect_summary(self, items: list[PortalResultEventRead]) -> dict[str, Any]:
        problem_code = next(
            (item.problem_code for item in items if item.problem_code), None
        )
        latest_with_after = next((item for item in items if item.after_snapshot), None)
        latest_before = next((item for item in items if item.before_snapshot), None)
        source = latest_with_after or latest_before
        before = self._canonical_result_snapshot(
            self._safe_snapshot(dict((source.before_snapshot if source else {}) or {})),
            problem_code=problem_code,
        )
        after = self._canonical_result_snapshot(
            self._safe_snapshot(
                dict(
                    (latest_with_after.after_snapshot if latest_with_after else {})
                    or {}
                )
            ),
            problem_code=problem_code,
        )
        comparison = self.compare(before, after, problem_code=problem_code)
        metrics = self._filter_result_metrics(
            comparison.get("metrics"), problem_code=problem_code
        )
        return {
            "before_snapshot": before,
            "after_snapshot": after,
            "comparison": comparison.get("outcome") or "not_enough_data",
            "metrics": metrics,
            "confidence": self._summary_confidence(comparison.get("outcome"), metrics),
            "calculation_note": CALCULATION_NOTE,
            "disclaimer": DISCLAIMER,
            "problem_code": problem_code,
            "result_metric_keys": self._problem_result_metric_keys(problem_code),
            "saved_money_claimed": False,
        }

    def problem_timeline_summary(
        self,
        *,
        problem: ProblemInstance,
        items: list[PortalResultEventRead],
        base_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base = dict(base_summary or {})
        chronological = sorted(
            list(items),
            key=lambda item: (
                item.created_at.isoformat() if item.created_at is not None else "",
                self._int(item.id) or 0,
            ),
        )
        reverse_chronological = list(reversed(chronological))
        before_event = next(
            (
                item
                for item in chronological
                if item.event_type == "before_snapshot" and item.before_snapshot
            ),
            None,
        )
        if before_event is None:
            before_event = next(
                (item for item in chronological if item.before_snapshot), None
            )
        before_snapshot = self._safe_snapshot(
            dict(
                (before_event.before_snapshot if before_event is not None else None)
                or base.get("before_snapshot")
                or self._problem_before_snapshot(problem)
                or {}
            )
        )
        after_event = next(
            (item for item in reverse_chronological if item.after_snapshot), None
        )
        after_snapshot = self._safe_snapshot(
            dict(
                (after_event.after_snapshot if after_event is not None else None)
                or base.get("after_snapshot")
                or {}
            )
        )
        measured_comparison: dict[str, Any] | None = None
        if after_snapshot:
            comparison = self.compare(
                before_snapshot, after_snapshot, problem_code=problem.problem_code
            )
            metrics = self._filter_result_metrics(
                comparison.get("metrics"), problem_code=problem.problem_code
            )
            if metrics:
                measured_comparison = {
                    **comparison,
                    "metrics": metrics,
                    "confidence": self._summary_confidence(
                        comparison.get("outcome"), metrics
                    ),
                    "correlation_disclaimer": DISCLAIMER,
                    "saved_money_claimed": False,
                    "is_measured": True,
                }
            else:
                measured_comparison = {
                    "outcome": "not_enough_data",
                    "metrics": {},
                    "confidence": "low",
                    "correlation_disclaimer": DISCLAIMER,
                    "saved_money_claimed": False,
                    "is_measured": False,
                }
        result_status = self._timeline_result_status(
            after_snapshot=after_snapshot,
            measured_comparison=measured_comparison,
        )
        confidence = (
            str((measured_comparison or {}).get("confidence") or "")
            or str(base.get("confidence") or "")
            or "low"
        )
        warnings = self._problem_timeline_warnings(
            problem=problem,
            items=chronological,
            result_status=result_status,
            measured_comparison=measured_comparison,
        )
        action_events = [
            self._timeline_event_payload(item)
            for item in chronological
            if item.event_type in PROBLEM_ACTION_EVENT_TYPES
        ]
        recheck_events = [
            self._timeline_event_payload(item)
            for item in chronological
            if "recheck" in str(item.event_type or "")
        ]
        problem_identity = {
            "problem_instance_id": problem.id,
            "problem_code": problem.problem_code,
            "title": problem.title,
            "source_module": problem.source_module,
            "nm_id": problem.nm_id,
            "vendor_code": problem.vendor_code,
        }
        action_center_href = self._frontend_href(
            "/action-center",
            problem_instance_id=problem.id,
            nm_id=problem.nm_id,
        )
        product_href = (
            self._frontend_href(
                "/products/" + str(problem.nm_id), problem_instance_id=problem.id
            )
            if problem.nm_id is not None
            else self._frontend_href("/products", problem_instance_id=problem.id)
        )
        data_fix_href = (
            self._frontend_href(
                "/data-fix",
                problem_instance_id=problem.id,
                nm_id=problem.nm_id,
                code=problem.problem_code,
            )
            if self._problem_data_fix_relevant(problem)
            else None
        )
        checker_href = (
            self._frontend_href(
                f"/checker/{problem.nm_id}", problem_instance_id=problem.id
            )
            if problem.nm_id is not None and self._problem_checker_relevant(problem)
            else None
        )
        comparison_outcome = (
            str((measured_comparison or {}).get("outcome") or "not_enough_data")
            if after_snapshot
            else "not_enough_data"
        )
        timeline = {
            **base,
            **problem_identity,
            "problem_title": problem.title,
            "problem_identity": problem_identity,
            "status": base.get("status") or problem.status,
            "before_snapshot": before_snapshot,
            "action_events": action_events,
            "recheck_events": recheck_events,
            "after_snapshot": after_snapshot,
            "measured_comparison": measured_comparison,
            "comparison": comparison_outcome,
            "result_status": result_status,
            "confidence": confidence,
            "warnings": warnings,
            "correlation_disclaimer": DISCLAIMER,
            "disclaimer": DISCLAIMER,
            "calculation_note": CALCULATION_NOTE,
            "evidence_ledger": self._safe_snapshot(
                dict(problem.evidence_ledger_json or {})
            ),
            "action_center_href": action_center_href,
            "product_href": product_href,
            "data_fix_href": data_fix_href,
            "checker_href": checker_href,
            "saved_money_claimed": False,
            "is_measured": result_status in MEASURED_RESULT_STATUSES
            and bool((measured_comparison or {}).get("metrics")),
            "money_note": "Ожидаемый эффект не считается сэкономленными деньгами, пока нет измеренных данных после действия.",
        }
        if measured_comparison and measured_comparison.get("metrics"):
            timeline["metrics"] = measured_comparison["metrics"]
        elif result_status == "pending_data":
            timeline["metrics"] = {}
        return self._safe_snapshot(timeline)

    def _timeline_result_status(
        self,
        *,
        after_snapshot: dict[str, Any],
        measured_comparison: dict[str, Any] | None,
    ) -> str:
        if not after_snapshot:
            return "pending_data"
        metrics = dict((measured_comparison or {}).get("metrics") or {})
        outcome = str((measured_comparison or {}).get("outcome") or "")
        if metrics and outcome in MEASURED_RESULT_STATUSES:
            return outcome
        return "not_enough_data"

    def _problem_timeline_warnings(
        self,
        *,
        problem: ProblemInstance,
        items: list[PortalResultEventRead],
        result_status: str,
        measured_comparison: dict[str, Any] | None,
    ) -> list[str]:
        warnings: list[str] = []
        for item in items:
            warnings.extend(
                str(warning) for warning in item.warnings if str(warning or "").strip()
            )
        ledger = dict(problem.evidence_ledger_json or {})
        for key in ("warnings", "calculation_warnings"):
            raw = ledger.get(key)
            if isinstance(raw, list):
                warnings.extend(
                    str(warning) for warning in raw if str(warning or "").strip()
                )
        warnings.append("causality_not_claimed")
        warnings.append("saved_money_not_claimed")
        if result_status == "pending_data":
            warnings.append("missing_after_snapshot")
        if measured_comparison is None or not dict(
            (measured_comparison or {}).get("metrics") or {}
        ):
            warnings.append("not_enough_measured_data")
        return list(dict.fromkeys(warnings))

    def _timeline_event_payload(self, item: PortalResultEventRead) -> dict[str, Any]:
        return item.model_dump(mode="json")

    def _problem_data_fix_relevant(self, problem: ProblemInstance) -> bool:
        ledger = dict(problem.evidence_ledger_json or {})
        code = str(problem.problem_code or "").lower()
        missing_data = ledger.get("missing_data")
        return (
            str(problem.impact_type or "").lower() == "data_blocker"
            or (isinstance(missing_data, list) and bool(missing_data))
            or any(
                token in code for token in ("missing", "unclassified", "cost", "data")
            )
        )

    def _problem_checker_relevant(self, problem: ProblemInstance) -> bool:
        code = str(problem.problem_code or "").lower()
        source_module = str(problem.source_module or "").lower()
        return source_module == "checker" or any(
            token in code
            for token in (
                "checker",
                "card_quality",
                "content",
                "title",
                "description",
                "photo",
            )
        )

    def _frontend_href(self, path: str, **params: Any) -> str:
        clean = {
            key: value
            for key, value in params.items()
            if value is not None and str(value).strip()
        }
        if not clean:
            return path
        query = "&".join(f"{key}={value}" for key, value in clean.items())
        return f"{path}?{query}"

    def by_module_summary(self, items: list[PortalResultEventRead]) -> dict[str, Any]:
        result: dict[str, Any] = {
            module: {
                "module": module,
                "total": 0,
                "outcomes": {outcome: 0 for outcome in OUTCOME_CATEGORIES},
                "latest_event_at": None,
                "pending_followups": 0,
                "confidence": "low",
                "calculation_note": CALCULATION_NOTE,
            }
            for module in RESULT_MODULES
        }
        for item in items:
            module = self._result_module(item)
            if module not in result:
                result[module] = {
                    "module": module,
                    "total": 0,
                    "outcomes": {outcome: 0 for outcome in OUTCOME_CATEGORIES},
                    "latest_event_at": None,
                    "pending_followups": 0,
                    "confidence": "low",
                    "calculation_note": CALCULATION_NOTE,
                }
            bucket = result[module]
            bucket["total"] += 1
            bucket["outcomes"][item.outcome] = (
                int(bucket["outcomes"].get(item.outcome, 0)) + 1
            )
            if item.outcome in {"pending", "blocked"}:
                bucket["pending_followups"] += 1
            if item.created_at is not None and (
                bucket["latest_event_at"] is None
                or item.created_at.isoformat() > str(bucket["latest_event_at"])
            ):
                bucket["latest_event_at"] = item.created_at.isoformat()
            bucket["confidence"] = self._module_confidence(bucket["outcomes"])
        return result

    def by_outcome_summary(self, items: list[PortalResultEventRead]) -> dict[str, int]:
        result = {outcome: 0 for outcome in OUTCOME_CATEGORIES}
        for item in items:
            result[item.outcome] = int(result.get(item.outcome, 0)) + 1
        return result

    def pending_followups(
        self, items: list[PortalResultEventRead]
    ) -> list[dict[str, Any]]:
        followups: list[dict[str, Any]] = []
        for item in items:
            if item.outcome not in {"pending", "blocked"}:
                continue
            if self._result_module(item) not in {
                "claims",
                "reputation",
            } and item.source_module not in {"claims", "reputation"}:
                continue
            followups.append(
                {
                    "id": item.id,
                    "source_module": item.source_module,
                    "module": self._result_module(item),
                    "source_id": item.source_id,
                    "external_id": item.external_id,
                    "nm_id": item.nm_id,
                    "product_identity": item.product_identity,
                    "event_type": item.event_type,
                    "outcome": item.outcome,
                    "message": item.message,
                    "created_at": item.created_at,
                    "calculation_note": "Операционный статус последующего действия; финансовая причинность не заявляется.",
                }
            )
        return followups[:20]

    async def finance_window_summaries(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        action_id: int | None = None,
        nm_id: int | None = None,
        items: list[PortalResultEventRead] | None = None,
    ) -> dict[str, Any]:
        events = list(items or [])
        target_nm_id = nm_id or next(
            (item.nm_id for item in events if item.nm_id is not None), None
        )
        action_at = self._action_anchor_date(events)
        if target_nm_id is None and action_id is not None:
            context = await self._action_context(
                session, action_id=action_id, account_id=account_id
            )
            target_nm_id = self._int(context.get("nm_id"))
        return {
            "7d": await self.finance_window_summary(
                session,
                account_id=account_id,
                nm_id=target_nm_id,
                window_days=7,
                action_at=action_at,
            ),
            "14d": await self.finance_window_summary(
                session,
                account_id=account_id,
                nm_id=target_nm_id,
                window_days=14,
                action_at=action_at,
            ),
        }

    async def finance_window_summary(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None,
        window_days: int,
        action_at: date | None = None,
    ) -> dict[str, Any]:
        if window_days not in {7, 14}:
            return self._window_not_enough(window_days, "unsupported_window")
        if nm_id is None:
            return self._window_not_enough(
                window_days, "nm_id is required for finance metric comparison"
            )
        today = utcnow().date()
        if action_at is not None:
            before_to = action_at - timedelta(days=1)
            before_from = before_to - timedelta(days=window_days - 1)
            after_from = action_at
            after_to = action_at + timedelta(days=window_days - 1)
            if after_to >= today:
                return self._window_not_enough(
                    window_days,
                    f"after window is incomplete until {after_to.isoformat()}",
                    before_window=(before_from, before_to),
                    after_window=(after_from, after_to),
                )
        else:
            after_to = today
            after_from = today - timedelta(days=window_days - 1)
            before_to = after_from - timedelta(days=1)
            before_from = before_to - timedelta(days=window_days - 1)
        before = await self._finance_window_snapshot(
            session,
            account_id=account_id,
            nm_id=nm_id,
            date_from=before_from,
            date_to=before_to,
        )
        after = await self._finance_window_snapshot(
            session,
            account_id=account_id,
            nm_id=nm_id,
            date_from=after_from,
            date_to=after_to,
        )
        before_rows = int(before.pop("_rows_count", 0) or 0)
        after_rows = int(after.pop("_rows_count", 0) or 0)
        if before_rows <= 0 or after_rows <= 0:
            return self._window_not_enough(
                window_days,
                "finance mart rows are missing for before or after window",
                before_window=(before_from, before_to),
                after_window=(after_from, after_to),
                before_snapshot=before,
                after_snapshot=after,
            )
        comparison = self.compare(before, after)
        return {
            "window_days": window_days,
            "status": comparison.get("outcome") or "not_enough_data",
            "comparison": comparison.get("outcome") or "not_enough_data",
            "before_window": self._window_payload(before_from, before_to),
            "after_window": self._window_payload(after_from, after_to),
            "before_snapshot": before,
            "after_snapshot": after,
            "metrics": {
                key: value
                for key, value in dict(comparison.get("metrics") or {}).items()
                if key in ACTION_EFFECT_METRICS
            },
            "explanation": None,
            "confidence": self._summary_confidence(
                comparison.get("outcome"), comparison.get("metrics")
            ),
            "calculation_note": CALCULATION_NOTE,
            "disclaimer": DISCLAIMER,
        }

    def compare(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        *,
        problem_code: str | None = None,
    ) -> dict[str, Any]:
        before = self._canonical_result_snapshot(before, problem_code=problem_code)
        after = self._canonical_result_snapshot(after, problem_code=problem_code)
        metrics: dict[str, Any] = {}
        improved = worse = 0
        for key, before_value in before.items():
            if key not in after:
                continue
            before_number = self._float(before_value)
            after_number = self._float(after.get(key))
            if before_number is None or after_number is None:
                continue
            delta = after_number - before_number
            direction = self._direction(key, delta, problem_code=problem_code)
            if direction == "improved":
                improved += 1
            elif direction == "worse":
                worse += 1
            metrics[key] = {
                "before": before_number,
                "after": after_number,
                "delta": delta,
                "direction": direction,
            }
        if not metrics:
            outcome = "not_enough_data"
        elif improved > worse:
            outcome = "improved"
        elif worse > improved:
            outcome = "worse"
        else:
            outcome = "neutral"
        return {"outcome": outcome, "metrics": metrics, "causality": "not_claimed"}

    async def _finance_window_snapshot(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        try:
            result = await session.execute(
                select(
                    func.count(MartSKUDaily.id),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue), 0),
                    func.coalesce(
                        func.sum(MartSKUDaily.net_profit_after_all_expenses), 0
                    ),
                    func.coalesce(func.sum(MartSKUDaily.final_sales_qty), 0),
                ).where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.nm_id == nm_id,
                    MartSKUDaily.stat_date >= date_from,
                    MartSKUDaily.stat_date <= date_to,
                )
            )
        except SQLAlchemyError:
            return {"_rows_count": 0}
        row = result.one() if hasattr(result, "one") else next(iter(result), None)
        if row is None:
            return {"_rows_count": 0}
        rows_count, revenue, profit, orders = row
        return {
            "_rows_count": int(rows_count or 0),
            "revenue": self._float(revenue),
            "profit": self._float(profit),
            "orders": self._float(orders),
        }

    async def _action_context(
        self, session: AsyncSession, *, action_id: int, account_id: int
    ) -> dict[str, Any]:
        unified = await session.get(UnifiedAction, action_id)
        if unified is not None and unified.account_id == account_id:
            payload = dict(unified.payload_json or {})
            return {
                "kind": "unified",
                "account_id": unified.account_id,
                "nm_id": unified.nm_id,
                "sku_id": None,
                "vendor_code": unified.vendor_code,
                "action_type": unified.action_type,
                "priority": unified.priority,
                "before_snapshot": payload.get("before_snapshot")
                or payload.get("snapshot"),
            }
        legacy = await session.get(ActionRecommendation, action_id)
        if legacy is not None and legacy.account_id == account_id:
            payload = dict(legacy.payload or {})
            return {
                "kind": "legacy",
                "account_id": legacy.account_id,
                "nm_id": legacy.nm_id,
                "sku_id": legacy.sku_id,
                "vendor_code": legacy.vendor_code,
                "action_type": legacy.action_type,
                "priority": legacy.priority,
                "before_snapshot": payload.get("before_snapshot")
                or payload.get("snapshot"),
            }
        return {
            "kind": "unknown",
            "account_id": account_id,
            "nm_id": None,
            "sku_id": None,
            "vendor_code": None,
        }

    def _read(self, event: ResultEvent) -> PortalResultEventRead:
        payload = dict(event.payload_json or {})
        comparison = dict(payload.get("comparison") or {})
        outcome = self._event_outcome(event, payload=payload, comparison=comparison)
        source_module = str(event.source_module or self.source_module)
        source_id = str(
            event.source_id or event.external_id or f"{source_module}:{event.id}"
        )
        before_snapshot = self._safe_snapshot(
            dict(payload.get("before_snapshot") or {})
        )
        after_snapshot = self._safe_snapshot(dict(payload.get("after_snapshot") or {}))
        confidence = self._event_confidence(outcome, comparison)
        safe_payload = self._safe_snapshot(payload)
        if "saved_money_claimed" in safe_payload:
            safe_payload["saved_money_claimed"] = self._saved_money_claim_allowed(
                saved_money_claimed=safe_payload.get("saved_money_claimed"),
                outcome=outcome,
                comparison=comparison,
                after_snapshot=after_snapshot,
                confidence=confidence,
            )
        product_identity = self._event_product_identity(event, payload)
        problem_code = (
            str(
                getattr(event, "problem_code", None)
                or payload.get("problem_code")
                or ""
            )
            or None
        )
        measured_comparison = self._event_measured_comparison(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            problem_code=problem_code,
        )
        result_status = self._event_result_status(
            after_snapshot=after_snapshot,
            measured_comparison=measured_comparison,
        )
        relevant_metric_keys = self._problem_result_metric_keys(problem_code)
        return PortalResultEventRead(
            id=str(event.id),
            account_id=event.account_id,
            action_id=int(
                payload.get("legacy_action_id")
                or event.action_id
                or payload.get("action_id")
                or 0
            )
            or None,
            problem_instance_id=self._int(
                getattr(event, "problem_instance_id", None)
                or payload.get("problem_instance_id")
            ),
            problem_code=problem_code,
            source_module=source_module,
            source_id=source_id,
            external_id=str(event.external_id)
            if event.external_id is not None
            else None,
            nm_id=event.nm_id,
            sku_id=self._int(payload.get("sku_id")),
            vendor_code=str(
                event.vendor_code
                or payload.get("vendor_code")
                or product_identity.get("vendor_code")
                or ""
            )
            or None,
            product_title=str(
                payload.get("product_title") or product_identity.get("title") or ""
            )
            or None,
            impact_type=str(
                payload.get("impact_type") or before_snapshot.get("impact_type") or ""
            )
            or None,
            trust_state=str(
                payload.get("trust_state") or before_snapshot.get("trust_state") or ""
            )
            or None,
            event_type=event.event_type,
            outcome=outcome,
            result_status=result_status,
            comparison=comparison,
            measured_comparison=measured_comparison,
            product_identity=product_identity,
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            evidence_ledger=self._safe_snapshot(
                dict(
                    payload.get("evidence_ledger")
                    or before_snapshot.get("evidence_ledger")
                    or before_snapshot.get("evidence_snapshot")
                    or {}
                )
            ),
            snapshot_day=self._int(payload.get("snapshot_day")),
            message=event.message or "",
            payload=safe_payload,
            confidence=confidence,
            saved_money_claimed=self._saved_money_claim_allowed(
                saved_money_claimed=safe_payload.get("saved_money_claimed"),
                outcome=outcome,
                comparison=comparison,
                after_snapshot=after_snapshot,
                confidence=confidence,
            ),
            metric_template_code=problem_code,
            relevant_metric_keys=relevant_metric_keys,
            missing_metric_keys=self._missing_metric_keys(
                after_snapshot if after_snapshot else {},
                problem_code=problem_code,
                relevant_metric_keys=relevant_metric_keys,
            ),
            calculation_note=str(
                payload.get("calculation_note")
                or payload.get("causality_note")
                or CALCULATION_NOTE
            ),
            created_by=self._int(payload.get("created_by")),
            created_at=event.created_at,
            warnings=["causality_not_claimed"],
        )

    async def _attach_result_context(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        items: list[PortalResultEventRead],
        peer_items: list[PortalResultEventRead] | None = None,
    ) -> list[PortalResultEventRead]:
        if not items:
            return items
        problem_ids = sorted(
            {
                int(item.problem_instance_id)
                for item in items
                if item.problem_instance_id is not None
            }
        )
        problems = await self._problem_contexts(
            session, account_id=account_id, problem_instance_ids=problem_ids
        )
        peers = list(peer_items or items)
        last_rechecks = self._last_recheck_at_by_problem(peers)
        enriched: list[PortalResultEventRead] = []
        for item in items:
            problem = (
                problems.get(int(item.problem_instance_id))
                if item.problem_instance_id is not None
                else None
            )
            enriched.append(
                self._item_with_context(
                    item,
                    problem=problem,
                    last_recheck_at=last_rechecks.get(item.problem_instance_id),
                )
            )
        return enriched

    async def _problem_contexts(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        problem_instance_ids: list[int],
    ) -> dict[int, ProblemInstance]:
        if not problem_instance_ids:
            return {}
        try:
            result = await session.execute(
                select(ProblemInstance).where(
                    ProblemInstance.account_id == account_id,
                    ProblemInstance.id.in_(problem_instance_ids),
                )
            )
        except Exception:
            return {}
        problems: dict[int, ProblemInstance] = {}
        for problem in result.scalars():
            if isinstance(problem, ProblemInstance) and problem.id is not None:
                problems[int(problem.id)] = problem
        return problems

    def _last_recheck_at_by_problem(
        self, items: list[PortalResultEventRead]
    ) -> dict[int | None, datetime]:
        result: dict[int | None, datetime] = {}
        for item in items:
            if "recheck" not in str(item.event_type or "") or item.created_at is None:
                continue
            current = result.get(item.problem_instance_id)
            if current is None or item.created_at.isoformat() > current.isoformat():
                result[item.problem_instance_id] = item.created_at
        return result

    def _item_with_context(
        self,
        item: PortalResultEventRead,
        *,
        problem: ProblemInstance | None,
        last_recheck_at: datetime | None,
    ) -> PortalResultEventRead:
        product_identity = dict(item.product_identity or {})
        payload = dict(item.payload or {})
        problem_code = item.problem_code or (
            problem.problem_code if problem is not None else None
        )
        nm_id = (
            item.nm_id
            if item.nm_id is not None
            else (problem.nm_id if problem is not None else None)
        )
        vendor_code = self._first_non_empty(
            item.vendor_code,
            problem.vendor_code if problem is not None else None,
            product_identity.get("vendor_code"),
            payload.get("vendor_code"),
        )
        product_title = self._first_non_empty(
            item.product_title,
            product_identity.get("title"),
            payload.get("product_title"),
            payload.get("product_name"),
        )
        before_snapshot = self._safe_snapshot(dict(item.before_snapshot or {}))
        after_snapshot = self._safe_snapshot(dict(item.after_snapshot or {}))
        measured_comparison = self._event_measured_comparison(
            before_snapshot=before_snapshot,
            after_snapshot=after_snapshot,
            problem_code=problem_code,
        )
        result_status = self._event_result_status(
            after_snapshot=after_snapshot,
            measured_comparison=measured_comparison,
        )
        relevant_metric_keys = self._problem_result_metric_keys(problem_code)
        evidence_ledger = self._safe_snapshot(
            dict(
                item.evidence_ledger
                or payload.get("evidence_ledger")
                or before_snapshot.get("evidence_ledger")
                or before_snapshot.get("evidence_snapshot")
                or (problem.evidence_ledger_json if problem is not None else {})
                or {}
            )
        )
        impact_type = self._first_non_empty(
            item.impact_type,
            problem.impact_type if problem is not None else None,
            payload.get("impact_type"),
            before_snapshot.get("impact_type"),
            (before_snapshot.get("money_at_risk") or {}).get("impact_type")
            if isinstance(before_snapshot.get("money_at_risk"), dict)
            else None,
        )
        trust_state = self._first_non_empty(
            item.trust_state,
            problem.trust_state if problem is not None else None,
            payload.get("trust_state"),
            before_snapshot.get("trust_state"),
            (before_snapshot.get("money_at_risk") or {}).get("trust_state")
            if isinstance(before_snapshot.get("money_at_risk"), dict)
            else None,
        )
        confidence = self._first_non_empty(
            item.confidence,
            problem.confidence if problem is not None else None,
            payload.get("confidence"),
        )
        saved_money_claimed = self._saved_money_claim_allowed(
            saved_money_claimed=item.saved_money_claimed
            or payload.get("saved_money_claimed"),
            outcome=result_status,
            comparison=measured_comparison or {},
            after_snapshot=after_snapshot,
            confidence=confidence,
        )
        return item.model_copy(
            update={
                "problem_instance_id": item.problem_instance_id
                or (problem.id if problem is not None else None),
                "problem_code": problem_code,
                "nm_id": nm_id,
                "vendor_code": vendor_code,
                "product_title": product_title,
                "impact_type": impact_type,
                "trust_state": trust_state,
                "confidence": confidence,
                "result_status": result_status,
                "measured_comparison": measured_comparison,
                "evidence_ledger": evidence_ledger,
                "saved_money_claimed": saved_money_claimed,
                "action_center_href": self._action_center_href(
                    item, problem=problem, nm_id=nm_id
                ),
                "product_href": self._product_href(
                    problem_instance_id=item.problem_instance_id, nm_id=nm_id
                ),
                "results_href": self._results_href(item, problem=problem, nm_id=nm_id),
                "data_fix_href": self._data_fix_href(
                    item, problem=problem, nm_id=nm_id, problem_code=problem_code
                ),
                "checker_href": self._checker_href(
                    item, problem=problem, nm_id=nm_id, problem_code=problem_code
                ),
                "metric_template_code": problem_code,
                "relevant_metric_keys": relevant_metric_keys,
                "missing_metric_keys": self._missing_metric_keys(
                    after_snapshot,
                    problem_code=problem_code,
                    relevant_metric_keys=relevant_metric_keys,
                ),
                "last_recheck_at": last_recheck_at,
                "payload": {
                    **payload,
                    "saved_money_claimed": saved_money_claimed,
                }
                if "saved_money_claimed" in payload
                else payload,
            }
        )

    def _event_outcome(
        self, event: ResultEvent, *, payload: dict[str, Any], comparison: dict[str, Any]
    ) -> str:
        event_type = str(event.event_type or "").strip().lower()
        if event_type == "photo_fix_started":
            return "pending"
        if event_type == "photo_fix_skipped":
            return "neutral"
        explicit = str(
            payload.get("outcome") or comparison.get("outcome") or ""
        ).strip()
        if explicit in OUTCOME_CATEGORIES:
            if (
                explicit in {"improved", "worse", "neutral"}
                and str(event.source_module or "").strip().lower()
                in {self.source_module, "problem_engine"}
                and not self._payload_has_measured_after_data(payload)
            ):
                return "not_enough_data"
            return explicit
        if explicit == "informational":
            return "neutral"
        status = str(event.status or "").strip().lower()
        external_status = str(event.external_status or "").strip().lower()
        combined = f"{status} {event_type} {external_status}"
        if any(
            token in combined
            for token in (
                "blocked",
                "confirmation_required",
                "disabled",
                "not_configured",
            )
        ):
            return "blocked"
        if any(
            token in combined
            for token in (
                "pending",
                "new",
                "draft",
                "submitted",
                "in_progress",
                "queued",
                "waiting",
            )
        ):
            return "pending"
        if event.source_module != self.source_module:
            return "neutral"
        return "not_enough_data"

    async def _latest_before_snapshot(
        self, session: AsyncSession, *, account_id: int, action_id: int
    ) -> dict[str, Any]:
        result = await session.execute(
            select(ResultEvent)
            .where(
                ResultEvent.account_id == account_id,
                ResultEvent.source_module == self.source_module,
                ResultEvent.source_id == str(action_id),
                ResultEvent.event_type == "before_snapshot",
            )
            .order_by(ResultEvent.created_at.desc(), ResultEvent.id.desc())
            .limit(1)
        )
        for event in result.scalars():
            return self._safe_snapshot(
                dict((event.payload_json or {}).get("before_snapshot") or {})
            )
        return {}

    async def _latest_problem_before_snapshot(
        self,
        session: AsyncSession,
        *,
        problem: ProblemInstance,
    ) -> dict[str, Any]:
        result = await session.execute(
            select(ResultEvent)
            .where(
                ResultEvent.account_id == problem.account_id,
                ResultEvent.problem_instance_id == problem.id,
                ResultEvent.source_module == "problem_engine",
                ResultEvent.event_type == "before_snapshot",
            )
            .order_by(ResultEvent.created_at.desc(), ResultEvent.id.desc())
            .limit(1)
        )
        for event in result.scalars():
            return self._safe_snapshot(
                dict((event.payload_json or {}).get("before_snapshot") or {})
            )
        return self._problem_before_snapshot(problem)

    async def _problem_context(
        self,
        session: AsyncSession,
        *,
        problem_instance_id: int,
    ) -> ProblemInstance:
        problem = await session.get(ProblemInstance, problem_instance_id)
        if problem is None:
            raise ValueError(f"Problem instance {problem_instance_id} not found")
        return problem

    def _problem_before_snapshot(self, problem: ProblemInstance) -> dict[str, Any]:
        ledger = dict(problem.evidence_ledger_json or {})
        facts: dict[str, Any] = {}
        raw_facts = ledger.get("input_facts")
        if isinstance(raw_facts, list):
            for fact in raw_facts:
                if not isinstance(fact, dict):
                    continue
                code = str(fact.get("metric_code") or fact.get("label") or "").strip()
                if code:
                    facts[code] = fact.get("value")
        normalized_facts = {
            str(key).strip().lower(): value for key, value in facts.items()
        }
        result_metrics = self._problem_result_metrics_from_facts(
            normalized_facts, problem.problem_code
        )
        evidence_snapshot = {
            key: ledger.get(key)
            for key in (
                "formula_human",
                "formula_code",
                "source_refs",
                "input_facts",
                "missing_data",
                "trust_notes",
                "warnings",
                "price_safety",
            )
            if ledger.get(key) not in (None, "", [], {})
        }
        return self._safe_snapshot(
            {
                "status": "new",
                "problem_instance_id": problem.id,
                "problem_code": problem.problem_code,
                "nm_id": problem.nm_id,
                "title": getattr(problem, "title", None),
                "explanation": getattr(problem, "explanation", None),
                "recommendation": getattr(problem, "recommendation", None),
                "price": self._first_fact(
                    normalized_facts,
                    "price",
                    "sale_price",
                    "current_price",
                    "avg_price",
                    "average_price",
                ),
                "stock": self._first_fact(
                    normalized_facts,
                    "stock",
                    "stock_qty",
                    "stocks",
                    "available_stock",
                    "quantity",
                ),
                "sales": self._first_fact(
                    normalized_facts,
                    "sales",
                    "sales_qty",
                    "final_sales_qty",
                    "sale_qty",
                    "buyouts",
                ),
                "orders": self._first_fact(
                    normalized_facts, "orders", "orders_qty", "order_qty"
                ),
                "revenue": self._first_fact(
                    normalized_facts, "revenue", "final_revenue", "gross_revenue"
                ),
                "profit": self._first_fact(
                    normalized_facts,
                    "profit",
                    "unit_profit",
                    "net_profit",
                    "net_profit_after_all_expenses",
                ),
                **result_metrics,
                "money_impact_amount": self._float(problem.money_impact_amount),
                "money_impact_currency": problem.money_impact_currency or "RUB",
                "money_at_risk": {
                    "amount": self._float(problem.money_impact_amount),
                    "currency": problem.money_impact_currency or "RUB",
                    "impact_type": problem.impact_type,
                    "trust_state": problem.trust_state,
                },
                "impact_type": problem.impact_type,
                "trust_state": problem.trust_state,
                "severity": problem.severity,
                "metrics": facts,
                "result_metrics": result_metrics,
                "result_metric_keys": self._problem_result_metric_keys(
                    problem.problem_code
                ),
                "formula_human": ledger.get("formula_human"),
                "formula_code": ledger.get("formula_code"),
                "evidence_snapshot": evidence_snapshot,
                "first_seen_at": problem.first_seen_at.isoformat()
                if problem.first_seen_at is not None
                else None,
            }
        )

    def _problem_current_snapshot(self, problem: ProblemInstance) -> dict[str, Any]:
        return self._safe_snapshot(
            {
                "status": problem.status,
                "problem_instance_id": problem.id,
                "problem_code": problem.problem_code,
                "nm_id": problem.nm_id,
                "title": getattr(problem, "title", None),
                "explanation": getattr(problem, "explanation", None),
                "recommendation": getattr(problem, "recommendation", None),
                "impact_type": problem.impact_type,
                "trust_state": problem.trust_state,
                "severity": problem.severity,
                "last_seen_at": problem.last_seen_at.isoformat()
                if problem.last_seen_at is not None
                else None,
                "resolved_at": problem.resolved_at.isoformat()
                if problem.resolved_at is not None
                else None,
                "dismissed_at": problem.dismissed_at.isoformat()
                if problem.dismissed_at is not None
                else None,
            }
        )

    def _problem_event_payload(
        self,
        problem: ProblemInstance,
        *,
        before_snapshot: dict[str, Any],
        current_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
        comparison: dict[str, Any],
        outcome: str,
        created_by: int | None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._safe_snapshot(
            {
                "problem_instance_id": problem.id,
                "problem_code": problem.problem_code,
                "title": getattr(problem, "title", None),
                "explanation": getattr(problem, "explanation", None),
                "recommendation": getattr(problem, "recommendation", None),
                "source_module": "problem_engine",
                "source_id": str(problem.id),
                "nm_id": problem.nm_id,
                "vendor_code": problem.vendor_code,
                "before_snapshot": before_snapshot,
                "current_snapshot": current_snapshot,
                "after_snapshot": after_snapshot,
                "comparison": comparison,
                "outcome": outcome,
                "confidence": self._event_confidence(outcome, comparison),
                "created_by": created_by,
                "calculation_note": CALCULATION_NOTE,
                "causality_note": DISCLAIMER,
                "disclaimer": DISCLAIMER,
                "saved_money_claimed": False,
                **dict(extra or {}),
            }
        )

    def _action_anchor_date(self, items: list[PortalResultEventRead]) -> date | None:
        action_event = next(
            (
                item
                for item in items
                if item.event_type
                in {
                    "action_completed",
                    "price_changed",
                    "cost_uploaded",
                    "ad_review_done",
                    "stock_action_done",
                }
                and item.created_at is not None
            ),
            None,
        )
        if action_event is None:
            action_event = next(
                (
                    item
                    for item in items
                    if item.nm_id is not None
                    and item.created_at is not None
                    and item.event_type != "before_snapshot"
                ),
                None,
            )
        if action_event is None or action_event.created_at is None:
            return None
        return action_event.created_at.date()

    def _window_not_enough(
        self,
        window_days: int,
        explanation: str,
        *,
        before_window: tuple[date, date] | None = None,
        after_window: tuple[date, date] | None = None,
        before_snapshot: dict[str, Any] | None = None,
        after_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "window_days": window_days,
            "status": "not_enough_data",
            "comparison": "not_enough_data",
            "before_window": self._window_payload(*before_window)
            if before_window
            else None,
            "after_window": self._window_payload(*after_window)
            if after_window
            else None,
            "before_snapshot": self._safe_snapshot(before_snapshot or {}),
            "after_snapshot": self._safe_snapshot(after_snapshot or {}),
            "metrics": {},
            "explanation": explanation,
            "confidence": "low",
            "calculation_note": CALCULATION_NOTE,
            "disclaimer": DISCLAIMER,
        }

    def _window_payload(self, date_from: date, date_to: date) -> dict[str, str]:
        return {"date_from": date_from.isoformat(), "date_to": date_to.isoformat()}

    def _direction(
        self, key: str, delta: float, *, problem_code: str | None = None
    ) -> str:
        normalized = key.lower()
        code = str(problem_code or "").strip().lower()
        if abs(delta) < 0.000001:
            return "neutral"
        if normalized == "days_of_stock" and code in {
            "overstock_slow_moving",
            "overstock",
            "dead_stock",
        }:
            return "improved" if delta < 0 else "worse"
        if normalized == "surplus_stock":
            return "improved" if delta < 0 else "worse"
        if normalized == "stock_days_left":
            return "improved" if delta > 0 else "worse"
        if normalized in NEGATIVE_METRICS or any(
            token in normalized for token in ("spend", "return", "defect", "penalty")
        ):
            return "improved" if delta < 0 else "worse"
        if normalized in POSITIVE_METRICS or any(
            token in normalized
            for token in ("revenue", "profit", "margin", "rating", "conversion")
        ):
            return "improved" if delta > 0 else "worse"
        return "neutral"

    def _problem_result_metric_keys(self, problem_code: str | None) -> list[str]:
        code = str(problem_code or "").strip().lower()
        return list(PRODUCT_RESULT_METRICS.get(code, ()))

    def _filter_result_metrics(
        self, metrics: Any, *, problem_code: str | None = None
    ) -> dict[str, Any]:
        raw = dict(metrics or {})
        allowed = (
            set(self._problem_result_metric_keys(problem_code)) or ACTION_EFFECT_METRICS
        )
        return {key: value for key, value in raw.items() if key in allowed}

    def _problem_result_metrics_from_facts(
        self, facts: dict[str, Any], problem_code: str | None
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for metric in self._problem_result_metric_keys(problem_code):
            value = self._first_fact(
                facts, *RESULT_METRIC_ALIASES.get(metric, (metric,))
            )
            if value not in (None, ""):
                result[metric] = value
        return result

    def _canonical_result_snapshot(
        self, snapshot: dict[str, Any], *, problem_code: str | None = None
    ) -> dict[str, Any]:
        if not snapshot:
            return {}
        result = self._safe_snapshot(dict(snapshot))
        nested_metrics = result.get("result_metrics") or result.get("metrics")
        lookup = {str(key).strip().lower(): value for key, value in result.items()}
        if isinstance(nested_metrics, dict):
            lookup.update(
                {
                    str(key).strip().lower(): value
                    for key, value in nested_metrics.items()
                }
            )
        for metric in self._problem_result_metric_keys(problem_code):
            if metric in result and result[metric] not in (None, ""):
                continue
            value = self._first_fact(
                lookup, *RESULT_METRIC_ALIASES.get(metric, (metric,))
            )
            if value not in (None, ""):
                result[metric] = value
        return result

    def _payload_has_measured_after_data(self, payload: dict[str, Any]) -> bool:
        after_snapshot = payload.get("after_snapshot")
        if isinstance(after_snapshot, dict) and bool(after_snapshot):
            return True
        if payload.get("post_window") or payload.get("after_window"):
            return True
        windows = payload.get("windows") or payload.get("finance_windows")
        if isinstance(windows, dict):
            return any(
                isinstance(window, dict)
                and (bool(window.get("after_snapshot")) or bool(window.get("metrics")))
                for window in windows.values()
            )
        return False

    def _normalize_result_status(self, result_status: str | None) -> str | None:
        raw = str(result_status or "").strip().lower()
        if not raw or raw == "all":
            return None
        return RESULT_STATUS_ALIASES.get(raw, raw)

    def _item_result_status(self, item: PortalResultEventRead) -> str:
        measured_comparison = self._event_measured_comparison(
            before_snapshot=item.before_snapshot,
            after_snapshot=item.after_snapshot,
            problem_code=item.problem_code,
        )
        return self._event_result_status(
            after_snapshot=item.after_snapshot,
            measured_comparison=measured_comparison,
        )

    def _event_measured_comparison(
        self,
        *,
        before_snapshot: dict[str, Any],
        after_snapshot: dict[str, Any],
        problem_code: str | None,
    ) -> dict[str, Any] | None:
        if not after_snapshot:
            return None
        comparison = self.compare(
            before_snapshot, after_snapshot, problem_code=problem_code
        )
        metrics = self._filter_result_metrics(
            comparison.get("metrics"), problem_code=problem_code
        )
        outcome = str(comparison.get("outcome") or "")
        if not metrics or outcome not in MEASURED_RESULT_STATUSES:
            return None
        return {
            **comparison,
            "metrics": metrics,
            "confidence": self._summary_confidence(outcome, metrics),
            "correlation_disclaimer": DISCLAIMER,
            "is_measured": True,
            "saved_money_claimed": False,
        }

    def _event_result_status(
        self,
        *,
        after_snapshot: dict[str, Any],
        measured_comparison: dict[str, Any] | None,
    ) -> str:
        if not after_snapshot:
            return "pending_data"
        outcome = str((measured_comparison or {}).get("outcome") or "")
        if outcome in MEASURED_RESULT_STATUSES and dict(
            (measured_comparison or {}).get("metrics") or {}
        ):
            return outcome
        return "not_enough_data"

    def _saved_money_claim_allowed(
        self,
        *,
        saved_money_claimed: Any,
        outcome: str,
        comparison: dict[str, Any],
        after_snapshot: dict[str, Any],
        confidence: str | None,
    ) -> bool:
        if saved_money_claimed is not True:
            return False
        metrics = dict(comparison.get("metrics") or {})
        measured = str(outcome or "") in MEASURED_RESULT_STATUSES and bool(metrics)
        return bool(after_snapshot) and measured and bool(str(confidence or "").strip())

    def _action_center_href(
        self,
        item: PortalResultEventRead,
        *,
        problem: ProblemInstance | None,
        nm_id: int | None,
    ) -> str | None:
        problem_instance_id = item.problem_instance_id or (
            problem.id if problem is not None else None
        )
        if problem_instance_id is not None:
            return self._frontend_href(
                "/action-center", problem_instance_id=problem_instance_id, nm_id=nm_id
            )
        if item.action_id is not None:
            return self._frontend_href(
                "/action-center", action_id=item.action_id, nm_id=nm_id
            )
        if item.source_module or item.source_id:
            return self._frontend_href(
                "/action-center",
                source_module=item.source_module,
                source_id=item.source_id,
                nm_id=nm_id,
            )
        return None

    def _product_href(
        self, *, problem_instance_id: int | None, nm_id: int | None
    ) -> str | None:
        if nm_id is None:
            return None
        return self._frontend_href(
            f"/products/{nm_id}", problem_instance_id=problem_instance_id
        )

    def _results_href(
        self,
        item: PortalResultEventRead,
        *,
        problem: ProblemInstance | None,
        nm_id: int | None,
    ) -> str:
        problem_instance_id = item.problem_instance_id or (
            problem.id if problem is not None else None
        )
        if problem_instance_id is not None:
            return self._frontend_href(
                "/results", problem_instance_id=problem_instance_id, nm_id=nm_id
            )
        if item.action_id is not None:
            return self._frontend_href(
                "/results", action_id=item.action_id, nm_id=nm_id
            )
        return self._frontend_href(
            "/results",
            source_module=item.source_module,
            source_id=item.source_id,
            nm_id=nm_id,
        )

    def _data_fix_href(
        self,
        item: PortalResultEventRead,
        *,
        problem: ProblemInstance | None,
        nm_id: int | None,
        problem_code: str | None,
    ) -> str | None:
        if problem is not None and self._problem_data_fix_relevant(problem):
            return self._frontend_href(
                "/data-fix",
                problem_instance_id=problem.id,
                nm_id=nm_id,
                code=problem.problem_code,
            )
        code = str(problem_code or "").lower()
        impact_type = str(item.impact_type or "").lower()
        if impact_type == "data_blocker" or any(
            token in code for token in ("missing", "unclassified", "cost", "data")
        ):
            return self._frontend_href(
                "/data-fix",
                problem_instance_id=item.problem_instance_id,
                nm_id=nm_id,
                code=problem_code,
            )
        return None

    def _checker_href(
        self,
        item: PortalResultEventRead,
        *,
        problem: ProblemInstance | None,
        nm_id: int | None,
        problem_code: str | None,
    ) -> str | None:
        if nm_id is None:
            return None
        if problem is not None and self._problem_checker_relevant(problem):
            return self._frontend_href(
                f"/checker/{nm_id}", problem_instance_id=problem.id
            )
        code = str(problem_code or "").lower()
        source_module = str(item.source_module or "").lower()
        if source_module == "checker" or any(
            token in code
            for token in (
                "checker",
                "card_quality",
                "content",
                "title",
                "description",
                "photo",
            )
        ):
            return self._frontend_href(
                f"/checker/{nm_id}", problem_instance_id=item.problem_instance_id
            )
        return None

    def _missing_metric_keys(
        self,
        snapshot: dict[str, Any],
        *,
        problem_code: str | None,
        relevant_metric_keys: list[str] | None = None,
    ) -> list[str]:
        keys = list(
            relevant_metric_keys or self._problem_result_metric_keys(problem_code)
        )
        if not keys:
            return []
        canonical = self._canonical_result_snapshot(snapshot, problem_code=problem_code)
        return [key for key in keys if canonical.get(key) in (None, "")]

    def _first_non_empty(self, *values: Any) -> Any:
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return None

    def _default_action_snapshot(self, action: dict[str, Any]) -> dict[str, Any]:
        return {
            "action_type": action.get("action_type"),
            "priority": action.get("priority"),
            "nm_id": action.get("nm_id"),
        }

    async def _attach_product_identity(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        items: list[PortalResultEventRead],
    ) -> list[PortalResultEventRead]:
        nm_ids = sorted({int(item.nm_id) for item in items if item.nm_id is not None})
        if not nm_ids:
            return items
        identities = await self._product_identities(
            session, account_id=account_id, nm_ids=nm_ids
        )
        if not identities:
            return items
        enriched: list[PortalResultEventRead] = []
        for item in items:
            identity = (
                identities.get(int(item.nm_id)) if item.nm_id is not None else None
            )
            if identity:
                product_identity = {**dict(item.product_identity or {}), **identity}
                enriched.append(
                    item.model_copy(
                        update={
                            "product_identity": product_identity,
                            "vendor_code": item.vendor_code
                            or product_identity.get("vendor_code"),
                            "product_title": item.product_title
                            or product_identity.get("title"),
                        }
                    )
                )
            else:
                enriched.append(item)
        return enriched

    async def _product_identities(
        self, session: AsyncSession, *, account_id: int, nm_ids: list[int]
    ) -> dict[int, dict[str, Any]]:
        try:
            result = await session.execute(
                select(
                    CoreSKU.nm_id,
                    CoreSKU.vendor_code,
                    CoreSKU.title,
                    CoreSKU.brand,
                    CoreSKU.subject_name,
                )
                .where(CoreSKU.account_id == account_id, CoreSKU.nm_id.in_(nm_ids))
                .order_by(CoreSKU.updated_at.desc(), CoreSKU.id.desc())
                .limit(len(nm_ids) * 3)
            )
        except Exception:
            return {}
        identities: dict[int, dict[str, Any]] = {}
        for row in result:
            try:
                nm_id, vendor_code, title, brand, subject_name = row
            except (TypeError, ValueError):
                continue
            if nm_id is None or int(nm_id) in identities:
                continue
            identities[int(nm_id)] = self._safe_snapshot(
                {
                    "nm_id": int(nm_id),
                    "vendor_code": vendor_code,
                    "title": title,
                    "brand": brand,
                    "subject_name": subject_name,
                }
            )
        return identities

    def _event_product_identity(
        self, event: ResultEvent, payload: dict[str, Any]
    ) -> dict[str, Any]:
        product_identity = dict(payload.get("product_identity") or {})
        if event.nm_id is not None:
            product_identity.setdefault("nm_id", event.nm_id)
        if event.vendor_code:
            product_identity.setdefault("vendor_code", event.vendor_code)
        for key in ("title", "brand", "subject_name"):
            value = payload.get(key)
            if value:
                product_identity.setdefault(key, value)
        for source_key in ("product_title", "product_name"):
            value = payload.get(source_key)
            if value:
                product_identity.setdefault("title", value)
        return self._safe_snapshot(product_identity)

    def _result_module(self, item: PortalResultEventRead) -> str:
        source_module = str(item.source_module or "").strip().lower().replace("-", "_")
        if str(item.event_type or "").startswith("photo_fix_"):
            return "photo"
        if source_module in {"result_tracking", "action", "actions"}:
            return "action_center"
        if source_module in {"grouping_beta", "grouping"}:
            return "grouping"
        if source_module in {"stock", "stock_ops", "stockops"}:
            return "stockops"
        if source_module in RESULT_MODULES:
            return source_module
        if str(item.event_type or "").startswith("experiment_"):
            return "experiments"
        return source_module or "action_center"

    def _source_module_filter_values(self, source_module: str) -> list[str]:
        normalized = str(source_module or "").strip().lower().replace("-", "_")
        aliases = {
            "action_center": ["result_tracking", "action", "actions", "action_center"],
            "result_tracking": [
                "result_tracking",
                "action",
                "actions",
                "action_center",
            ],
            "grouping": ["grouping", "grouping_beta"],
            "grouping_beta": ["grouping", "grouping_beta"],
            "stockops": ["stockops", "stock_ops", "stock"],
            "stock_ops": ["stockops", "stock_ops", "stock"],
            "stock": ["stockops", "stock_ops", "stock"],
        }
        return aliases.get(normalized, [normalized])

    def _event_confidence(self, outcome: str, comparison: dict[str, Any]) -> str:
        metrics = dict(comparison.get("metrics") or {})
        if outcome in {"improved", "worse", "neutral"} and metrics:
            return "medium"
        if outcome in {"pending", "blocked"}:
            return "high"
        return "low"

    def _summary_confidence(self, outcome: Any, metrics: Any) -> str:
        if str(outcome or "") in {"improved", "worse", "neutral"} and dict(
            metrics or {}
        ):
            return "medium"
        return "low"

    def _module_confidence(self, outcomes: dict[str, int]) -> str:
        measured = (
            int(outcomes.get("improved", 0) or 0)
            + int(outcomes.get("worse", 0) or 0)
            + int(outcomes.get("neutral", 0) or 0)
        )
        operational = int(outcomes.get("pending", 0) or 0) + int(
            outcomes.get("blocked", 0) or 0
        )
        if measured:
            return "medium"
        if operational:
            return "high"
        return "low"

    def _message(self, outcome: str) -> str:
        return {
            "improved": "Metrics improved after the action window.",
            "worse": "Metrics worsened after the action window.",
            "neutral": "Metrics were neutral after the action window.",
            "not_enough_data": "Not enough before/after data to compare.",
        }.get(outcome, "Result comparison recorded.")

    def _safe_snapshot(self, value: Any) -> Any:
        secret_tokens = {
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
        }
        private_tokens = {
            "phone",
            "email",
            "buyer",
            "customer",
            "passport",
            "address",
            "full_name",
            "fio",
        }
        if isinstance(value, dict):
            return {
                key: self._safe_snapshot(item)
                for key, item in value.items()
                if not any(
                    token in str(key).lower()
                    for token in secret_tokens | private_tokens
                )
            }
        if isinstance(value, list):
            return [self._safe_snapshot(item) for item in value]
        return value

    def _first_fact(self, facts: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key in facts and facts[key] not in (None, ""):
                return facts[key]
        return None

    def _float(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
