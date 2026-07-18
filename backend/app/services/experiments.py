from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import scrub_sensitive_payload
from app.core.time import utcnow
from app.models.analytics import WBCardFunnelDaily
from app.models.experiments import (
    Experiment,
    ExperimentEvaluation,
    ExperimentEvent,
    ExperimentIntervention,
    ExperimentMetricSnapshot,
    ExperimentSettings,
)
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.operator import ResultEvent
from app.schemas.portal import (
    PortalExperimentCreate,
    PortalExperimentEvaluationRead,
    PortalExperimentEventCreate,
    PortalExperimentEventRead,
    PortalExperimentEventsPage,
    PortalExperimentInterventionCreate,
    PortalExperimentInterventionRead,
    PortalExperimentMetricSnapshotRead,
    PortalExperimentMetricsPage,
    PortalExperimentRead,
    PortalExperimentsPage,
    PortalExperimentSettingsRead,
    PortalExperimentSettingsUpdate,
    PortalExperimentsStatusRead,
    PortalExperimentUpdate,
    PortalActionRead,
)


CAUSALITY_DISCLAIMER = "Это наблюдаемая связь, а не доказанная причинность."
SUPPORTED_INTERVENTIONS = (
    "photo",
    "title",
    "description",
    "price",
    "ads",
    "grouping",
    "stock",
    "reputation",
    "manual_other",
)
TERMINAL_STATUSES = {"evaluated", "inconclusive", "cancelled", "failed"}
ACTIVE_STATUSES = {
    "planned",
    "baseline_collecting",
    "ready_for_change",
    "change_recorded",
    "post_collecting",
    "ready_for_evaluation",
}


@dataclass(frozen=True)
class MetricDefinition:
    code: str
    label: str
    source: str
    unit: str
    aggregation: str
    positive_is_good: bool = True


METRIC_CATALOG: dict[str, MetricDefinition] = {
    "revenue": MetricDefinition(
        "revenue", "Выручка", "mart_sku_daily.final_revenue", "currency", "sum"
    ),
    "for_pay": MetricDefinition(
        "for_pay", "К перечислению", "mart_sku_daily.final_for_pay", "currency", "sum"
    ),
    "estimated_profit": MetricDefinition(
        "estimated_profit",
        "Оценочная прибыль",
        "mart_sku_daily.net_profit_after_all_expenses",
        "currency",
        "sum",
    ),
    "margin_revenue_percent": MetricDefinition(
        "margin_revenue_percent",
        "Маржинальность",
        "mart_sku_daily.margin_percent",
        "percent",
        "avg",
    ),
    "cogs": MetricDefinition(
        "cogs",
        "Себестоимость",
        "mart_sku_daily.estimated_cogs",
        "currency",
        "sum",
        positive_is_good=False,
    ),
    "wb_expenses": MetricDefinition(
        "wb_expenses",
        "Расходы WB",
        "mart_sku_daily.total_wb_expenses",
        "currency",
        "sum",
        positive_is_good=False,
    ),
    "orders_count": MetricDefinition(
        "orders_count", "Заказы", "mart_sku_daily.ordered_units", "count", "sum"
    ),
    "units_sold": MetricDefinition(
        "units_sold", "Продано штук", "mart_sku_daily.final_sales_qty", "count", "sum"
    ),
    "sales_count": MetricDefinition(
        "sales_count", "Продажи", "mart_sku_daily.sale_rows", "count", "sum"
    ),
    "return_count": MetricDefinition(
        "return_count",
        "Возвраты",
        "mart_sku_daily.final_return_qty",
        "count",
        "sum",
        positive_is_good=False,
    ),
    "return_rate": MetricDefinition(
        "return_rate",
        "Доля возвратов",
        "mart_sku_daily.final_return_qty/final_sales_qty",
        "percent",
        "ratio",
        positive_is_good=False,
    ),
    "average_order_value": MetricDefinition(
        "average_order_value",
        "Средний чек",
        "mart_sku_daily.final_revenue/ordered_units",
        "currency",
        "ratio",
    ),
    "ads_spend": MetricDefinition(
        "ads_spend",
        "Расходы на рекламу",
        "mart_sku_daily.ad_spend",
        "currency",
        "sum",
        positive_is_good=False,
    ),
    "roas": MetricDefinition(
        "roas", "ROAS", "mart_sku_daily.final_revenue/ad_spend", "ratio", "ratio"
    ),
    "acos": MetricDefinition(
        "acos",
        "ACOS",
        "mart_sku_daily.ad_spend/final_revenue",
        "percent",
        "ratio",
        positive_is_good=False,
    ),
    "clicks": MetricDefinition(
        "clicks", "Клики", "mart_sku_daily.ad_clicks", "count", "sum"
    ),
    "ctr": MetricDefinition(
        "ctr", "CTR", "mart_sku_daily.ad_clicks/ad_views", "percent", "ratio"
    ),
    "cpc": MetricDefinition(
        "cpc",
        "CPC",
        "mart_sku_daily.ad_spend/ad_clicks",
        "currency",
        "ratio",
        positive_is_good=False,
    ),
    "views": MetricDefinition(
        "views", "Просмотры", "wb_card_funnel_daily.open_count", "count", "sum"
    ),
    "add_to_cart": MetricDefinition(
        "add_to_cart",
        "Добавления в корзину",
        "wb_card_funnel_daily.cart_count",
        "count",
        "sum",
    ),
    "conversion_rate": MetricDefinition(
        "conversion_rate",
        "Конверсия в заказ",
        "wb_card_funnel_daily.order_count/open_count",
        "percent",
        "ratio",
    ),
    "in_stock_days": MetricDefinition(
        "in_stock_days",
        "Дней в наличии",
        "mart_stock_daily.quantity",
        "days",
        "stock_days",
    ),
    "stockout_days": MetricDefinition(
        "stockout_days",
        "Дней без остатка",
        "mart_stock_daily.quantity",
        "days",
        "stockout_days",
        positive_is_good=False,
    ),
    "average_stock": MetricDefinition(
        "average_stock", "Средний остаток", "mart_stock_daily.quantity", "count", "avg"
    ),
    "days_of_stock": MetricDefinition(
        "days_of_stock", "Дней запаса", "mart_stock_daily.days_of_stock", "days", "avg"
    ),
}


class ExperimentRepository:
    async def get(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> Experiment | None:
        return (
            await session.execute(
                select(Experiment)
                .where(
                    Experiment.id == experiment_id, Experiment.account_id == account_id
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def latest_evaluation(
        self, session: AsyncSession, *, experiment_id: int
    ) -> ExperimentEvaluation | None:
        return (
            await session.execute(
                select(ExperimentEvaluation)
                .where(ExperimentEvaluation.experiment_id == experiment_id)
                .order_by(
                    ExperimentEvaluation.evaluated_at.desc(),
                    ExperimentEvaluation.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def settings(
        self, session: AsyncSession, *, account_id: int
    ) -> ExperimentSettings:
        row = (
            await session.execute(
                select(ExperimentSettings)
                .where(ExperimentSettings.account_id == account_id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = ExperimentSettings(
            account_id=account_id,
            default_baseline_days=7,
            default_post_days=7,
            default_evaluation_delay_days=0,
            minimum_orders=3,
            minimum_revenue=Decimal("0"),
            maximum_stockout_days=1,
            allow_overlapping_experiments=False,
            weekday_matched_baseline=False,
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        return row


class ExperimentMetricCollector:
    async def collect_window(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        window_type: str,
        start_date: date,
        end_date: date,
        metrics: list[str],
    ) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "window_type": window_type,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "metrics": {},
        }
        if start_date > end_date:
            summary["warnings"] = ["empty_window"]
            return summary
        dates = [
            start_date + timedelta(days=offset)
            for offset in range((end_date - start_date).days + 1)
        ]
        for metric in dict.fromkeys(metrics):
            if metric not in METRIC_CATALOG:
                summary["metrics"][metric] = {"status": "unsupported", "values": []}
                continue
            values = await self._daily_values(
                session, experiment=experiment, metric=metric, dates=dates
            )
            for metric_date, value, source, warnings in values:
                await self._upsert_snapshot(
                    session,
                    experiment=experiment,
                    window_type=window_type,
                    metric_date=metric_date,
                    metric_name=metric,
                    metric_value=value,
                    source=source,
                    warnings=warnings,
                )
            non_null = [value for _, value, _, _ in values if value is not None]
            summary["metrics"][metric] = {
                "status": "ok" if non_null else "empty",
                "days": len(values),
                "complete_days": len(non_null),
                "value": self._aggregate(metric, non_null),
                "unit": METRIC_CATALOG[metric].unit,
            }
        await session.flush()
        return summary

    async def _daily_values(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        metric: str,
        dates: list[date],
    ) -> list[tuple[date, Decimal | None, str, list[str]]]:
        if metric in {"views", "add_to_cart", "conversion_rate"}:
            return await self._funnel_values(
                session, experiment=experiment, metric=metric, dates=dates
            )
        if metric in {
            "in_stock_days",
            "stockout_days",
            "average_stock",
            "days_of_stock",
        }:
            return await self._stock_values(
                session, experiment=experiment, metric=metric, dates=dates
            )
        return await self._sku_values(
            session, experiment=experiment, metric=metric, dates=dates
        )

    async def _sku_values(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        metric: str,
        dates: list[date],
    ) -> list[tuple[date, Decimal | None, str, list[str]]]:
        value_expr = {
            "revenue": func.sum(MartSKUDaily.final_revenue),
            "for_pay": func.sum(MartSKUDaily.final_for_pay),
            "estimated_profit": func.sum(MartSKUDaily.net_profit_after_all_expenses),
            "margin_revenue_percent": func.avg(MartSKUDaily.margin_percent),
            "cogs": func.sum(MartSKUDaily.estimated_cogs),
            "wb_expenses": func.sum(MartSKUDaily.total_wb_expenses),
            "orders_count": func.sum(MartSKUDaily.ordered_units),
            "units_sold": func.sum(MartSKUDaily.final_sales_qty),
            "sales_count": func.sum(MartSKUDaily.sale_rows),
            "return_count": func.sum(MartSKUDaily.final_return_qty),
            "ads_spend": func.sum(MartSKUDaily.ad_spend),
            "clicks": func.sum(MartSKUDaily.ad_clicks),
        }.get(metric)
        if metric == "return_rate":
            value_expr = (
                func.sum(MartSKUDaily.final_return_qty)
                / func.nullif(func.sum(MartSKUDaily.final_sales_qty), 0)
                * 100
            )
        elif metric == "average_order_value":
            value_expr = func.sum(MartSKUDaily.final_revenue) / func.nullif(
                func.sum(MartSKUDaily.ordered_units), 0
            )
        elif metric == "roas":
            value_expr = func.sum(MartSKUDaily.final_revenue) / func.nullif(
                func.sum(MartSKUDaily.ad_spend), 0
            )
        elif metric == "acos":
            value_expr = (
                func.sum(MartSKUDaily.ad_spend)
                / func.nullif(func.sum(MartSKUDaily.final_revenue), 0)
                * 100
            )
        elif metric == "ctr":
            value_expr = (
                func.sum(MartSKUDaily.ad_clicks)
                / func.nullif(func.sum(MartSKUDaily.ad_views), 0)
                * 100
            )
        elif metric == "cpc":
            value_expr = func.sum(MartSKUDaily.ad_spend) / func.nullif(
                func.sum(MartSKUDaily.ad_clicks), 0
            )
        rows = await self._metric_rows(
            session,
            experiment=experiment,
            dates=dates,
            value_expr=value_expr,
            model=MartSKUDaily,
        )
        return [
            (
                day,
                rows.get(day),
                "mart_sku_daily",
                [] if day in rows else ["missing_day"],
            )
            for day in dates
        ]

    async def _funnel_values(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        metric: str,
        dates: list[date],
    ) -> list[tuple[date, Decimal | None, str, list[str]]]:
        if metric == "views":
            value_expr = func.sum(WBCardFunnelDaily.open_count)
        elif metric == "add_to_cart":
            value_expr = func.sum(WBCardFunnelDaily.cart_count)
        else:
            value_expr = (
                func.sum(WBCardFunnelDaily.order_count)
                / func.nullif(func.sum(WBCardFunnelDaily.open_count), 0)
                * 100
            )
        rows = await self._metric_rows(
            session,
            experiment=experiment,
            dates=dates,
            value_expr=value_expr,
            model=WBCardFunnelDaily,
        )
        return [
            (
                day,
                rows.get(day),
                "wb_card_funnel_daily",
                [] if day in rows else ["missing_day"],
            )
            for day in dates
        ]

    async def _stock_values(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        metric: str,
        dates: list[date],
    ) -> list[tuple[date, Decimal | None, str, list[str]]]:
        filters = [
            MartStockDaily.account_id == experiment.account_id,
            MartStockDaily.stat_date.in_(dates),
        ]
        if experiment.nm_id is not None:
            filters.append(MartStockDaily.nm_id == experiment.nm_id)
        result = await session.execute(
            select(
                MartStockDaily.stat_date,
                func.sum(MartStockDaily.quantity).label("quantity"),
                func.avg(MartStockDaily.quantity).label("average_stock"),
                func.avg(MartStockDaily.days_of_stock).label("days_of_stock"),
            )
            .where(*filters)
            .group_by(MartStockDaily.stat_date)
        )
        rows: dict[date, Decimal | None] = {}
        for row in result.all():
            quantity = self._decimal(row.quantity)
            if metric == "in_stock_days":
                rows[row.stat_date] = (
                    Decimal("1")
                    if quantity is not None and quantity > 0
                    else Decimal("0")
                )
            elif metric == "stockout_days":
                rows[row.stat_date] = (
                    Decimal("1")
                    if quantity is not None and quantity <= 0
                    else Decimal("0")
                )
            elif metric == "days_of_stock":
                rows[row.stat_date] = self._decimal(row.days_of_stock)
            else:
                rows[row.stat_date] = self._decimal(row.average_stock)
        return [
            (
                day,
                rows.get(day),
                "mart_stock_daily",
                [] if day in rows else ["missing_day"],
            )
            for day in dates
        ]

    async def _metric_rows(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        dates: list[date],
        value_expr: Any,
        model: Any,
    ) -> dict[date, Decimal | None]:
        if value_expr is None:
            return {}
        filters = [
            model.account_id == experiment.account_id,
            model.stat_date.in_(dates),
        ]
        if experiment.nm_id is not None:
            filters.append(model.nm_id == experiment.nm_id)
        result = await session.execute(
            select(model.stat_date, value_expr.label("value"))
            .where(*filters)
            .group_by(model.stat_date)
        )
        return {row.stat_date: self._decimal(row.value) for row in result.all()}

    async def _upsert_snapshot(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        window_type: str,
        metric_date: date,
        metric_name: str,
        metric_value: Decimal | None,
        source: str,
        warnings: list[str],
    ) -> None:
        row = (
            await session.execute(
                select(ExperimentMetricSnapshot)
                .where(
                    ExperimentMetricSnapshot.experiment_id == experiment.id,
                    ExperimentMetricSnapshot.window_type == window_type,
                    ExperimentMetricSnapshot.metric_date == metric_date,
                    ExperimentMetricSnapshot.metric_name == metric_name,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            session.add(
                ExperimentMetricSnapshot(
                    account_id=experiment.account_id,
                    experiment_id=experiment.id,
                    window_type=window_type,
                    metric_date=metric_date,
                    metric_name=metric_name,
                    metric_value=metric_value,
                    metric_unit=METRIC_CATALOG[metric_name].unit,
                    source=source,
                    data_status="ok" if metric_value is not None else "empty",
                    data_freshness_at=utcnow(),
                    is_complete=metric_value is not None,
                    warnings_json=warnings,
                )
            )
            return
        row.metric_value = metric_value
        row.metric_unit = METRIC_CATALOG[metric_name].unit
        row.source = source
        row.data_status = "ok" if metric_value is not None else "empty"
        row.data_freshness_at = utcnow()
        row.is_complete = metric_value is not None
        row.warnings_json = warnings

    def _aggregate(self, metric: str, values: list[Decimal]) -> float | None:
        if not values:
            return None
        definition = METRIC_CATALOG[metric]
        if definition.aggregation in {"avg", "ratio"}:
            return float(sum(values) / Decimal(len(values)))
        return float(sum(values))

    def _decimal(self, value: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(str(value))


class ExperimentEvaluationService:
    async def evaluate(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        settings: ExperimentSettings,
    ) -> ExperimentEvaluation:
        if experiment.experiment_type == "controlled_split":
            return await self._save_not_supported(session, experiment=experiment)
        metrics = [
            experiment.primary_metric,
            *list(experiment.secondary_metrics_json or []),
            *list(experiment.guardrail_metrics_json or []),
        ]
        snapshots = await self._snapshots(
            session, experiment_id=experiment.id, metrics=list(dict.fromkeys(metrics))
        )
        primary = self._compare_metric(experiment.primary_metric, snapshots)
        stockouts = self._metric_total("stockout_days", snapshots, "post")
        orders = self._metric_total("orders_count", snapshots, "post")
        revenue = self._metric_total("revenue", snapshots, "post")
        confounders = self._confounders(experiment, snapshots, settings=settings)
        data_sufficiency = {
            "post_orders": orders,
            "post_revenue": revenue,
            "minimum_orders": settings.minimum_orders,
            "minimum_revenue": float(settings.minimum_revenue or 0),
            "stockout_days": stockouts,
            "missing_post_days": self._missing_days(
                snapshots, "post", experiment.primary_metric
            ),
        }
        outcome = self._outcome(
            primary, data_sufficiency, confounders, settings=settings
        )
        confidence = self._confidence(data_sufficiency, confounders)
        now = utcnow()
        evaluation = ExperimentEvaluation(
            account_id=experiment.account_id,
            experiment_id=experiment.id,
            status="ok",
            evaluation_version="before_after_v1",
            evaluated_at=now,
            baseline_window_json=self._window_summary(snapshots, "baseline"),
            post_window_json=self._window_summary(snapshots, "post"),
            primary_result_json=primary,
            secondary_results_json=[
                self._compare_metric(metric, snapshots)
                for metric in (experiment.secondary_metrics_json or [])
            ],
            guardrail_results_json=[
                self._compare_metric(metric, snapshots)
                for metric in (experiment.guardrail_metrics_json or [])
            ],
            data_sufficiency_json=data_sufficiency,
            confounders_json=confounders,
            confidence=confidence,
            outcome=outcome,
            seller_summary=self._seller_summary(
                experiment.primary_metric, primary, outcome, confounders
            ),
            technical_summary_json={
                "causality": "before_after_observational",
                "disclaimer": CAUSALITY_DISCLAIMER,
            },
        )
        session.add(evaluation)
        experiment.status = (
            "evaluated"
            if outcome not in {"inconclusive", "not_enough_data"}
            else "inconclusive"
        )
        experiment.completed_at = now
        session.add(
            ResultEvent(
                account_id=experiment.account_id,
                source_module="experiments",
                source_id=str(experiment.id),
                external_id=str(experiment.id),
                nm_id=experiment.nm_id,
                event_type="experiment_evaluated",
                status="done",
                external_status=outcome,
                message=evaluation.seller_summary,
                payload_json={
                    "experiment_id": experiment.id,
                    "intervention_type": experiment.intervention_type,
                    "primary_metric": experiment.primary_metric,
                    "outcome": outcome,
                    "confidence": confidence,
                    "baseline_window": evaluation.baseline_window_json or {},
                    "post_window": evaluation.post_window_json or {},
                    "primary_result": primary,
                    "data_sufficiency": data_sufficiency,
                    "confounders": confounders,
                    "causality_note": CAUSALITY_DISCLAIMER,
                    "evaluation_version": evaluation.evaluation_version,
                },
            )
        )
        await session.flush()
        await session.refresh(evaluation)
        return evaluation

    async def _save_not_supported(
        self, session: AsyncSession, *, experiment: Experiment
    ) -> ExperimentEvaluation:
        now = utcnow()
        evaluation = ExperimentEvaluation(
            account_id=experiment.account_id,
            experiment_id=experiment.id,
            status="not_supported",
            evaluation_version="controlled_split_v1",
            evaluated_at=now,
            baseline_window_json={},
            post_window_json={},
            primary_result_json={"status": "not_supported"},
            secondary_results_json=[],
            guardrail_results_json=[],
            data_sufficiency_json={
                "reason": "controlled_split_assignment_not_available"
            },
            confounders_json=[],
            confidence="low",
            outcome="inconclusive",
            seller_summary="Controlled split is not supported until real split assignment and variant data exist.",
            technical_summary_json={"controlled_split": "not_supported"},
        )
        experiment.status = "inconclusive"
        experiment.completed_at = now
        session.add(evaluation)
        await session.flush()
        await session.refresh(evaluation)
        return evaluation

    async def _snapshots(
        self, session: AsyncSession, *, experiment_id: int, metrics: list[str]
    ) -> dict[str, dict[str, list[ExperimentMetricSnapshot]]]:
        result = await session.execute(
            select(ExperimentMetricSnapshot)
            .where(
                ExperimentMetricSnapshot.experiment_id == experiment_id,
                ExperimentMetricSnapshot.metric_name.in_(metrics),
            )
            .order_by(ExperimentMetricSnapshot.metric_date.asc())
        )
        grouped: dict[str, dict[str, list[ExperimentMetricSnapshot]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for row in result.scalars().all():
            grouped[row.metric_name][row.window_type].append(row)
        return grouped

    def _compare_metric(
        self,
        metric: str,
        snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]],
    ) -> dict[str, Any]:
        baseline = self._metric_total(metric, snapshots, "baseline")
        post = self._metric_total(metric, snapshots, "post")
        delta = None if baseline is None or post is None else post - baseline
        relative = (
            None if delta is None or baseline in (None, 0) else (delta / baseline) * 100
        )
        return {
            "metric": metric,
            "baseline": baseline,
            "post": post,
            "absolute_change": delta,
            "relative_change_percent": relative,
            "unit": METRIC_CATALOG.get(
                metric, MetricDefinition(metric, metric, "unknown", "number", "sum")
            ).unit,
            "positive_is_good": METRIC_CATALOG.get(
                metric, MetricDefinition(metric, metric, "unknown", "number", "sum")
            ).positive_is_good,
        }

    def _metric_total(
        self,
        metric: str,
        snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]],
        window: str,
    ) -> float | None:
        values = [
            row.metric_value
            for row in snapshots.get(metric, {}).get(window, [])
            if row.metric_value is not None
        ]
        if not values:
            return None
        definition = METRIC_CATALOG.get(metric)
        if definition and definition.aggregation in {"avg", "ratio"}:
            return float(sum(values) / Decimal(len(values)))
        return float(sum(values))

    def _missing_days(
        self,
        snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]],
        window: str,
        metric: str,
    ) -> int:
        return len(
            [
                row
                for row in snapshots.get(metric, {}).get(window, [])
                if not row.is_complete
            ]
        )

    def _window_summary(
        self,
        snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]],
        window: str,
    ) -> dict[str, Any]:
        days = sorted(
            {
                row.metric_date.isoformat()
                for metric_rows in snapshots.values()
                for row in metric_rows.get(window, [])
            }
        )
        return {"days": days, "day_count": len(days)}

    def _confounders(
        self,
        experiment: Experiment,
        snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]],
        *,
        settings: ExperimentSettings,
    ) -> list[dict[str, Any]]:
        confounders: list[dict[str, Any]] = []
        stockouts = self._metric_total("stockout_days", snapshots, "post") or 0
        if stockouts > settings.maximum_stockout_days:
            confounders.append(
                {
                    "code": "stockout",
                    "severity": "high",
                    "message": "Post window contains stockout days.",
                }
            )
        if experiment.intervention_type != "price":
            price_change = self._price_change_signal(snapshots)
            if price_change:
                confounders.append(price_change)
        if experiment.intervention_type != "ads":
            ads_change = self._ads_change_signal(snapshots)
            if ads_change:
                confounders.append(ads_change)
        return confounders

    def _price_change_signal(
        self, snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]]
    ) -> dict[str, Any] | None:
        return None

    def _ads_change_signal(
        self, snapshots: dict[str, dict[str, list[ExperimentMetricSnapshot]]]
    ) -> dict[str, Any] | None:
        result = self._compare_metric("ads_spend", snapshots)
        baseline = result.get("baseline")
        relative = result.get("relative_change_percent")
        if baseline is not None and relative is not None and abs(relative) >= 30:
            return {
                "code": "ads_changed",
                "severity": "medium",
                "message": "Ads spend changed materially during the experiment.",
                "relative_change_percent": relative,
            }
        return None

    def _outcome(
        self,
        primary: dict[str, Any],
        data: dict[str, Any],
        confounders: list[dict[str, Any]],
        *,
        settings: ExperimentSettings,
    ) -> str:
        if (data.get("post_orders") or 0) < settings.minimum_orders or (
            data.get("post_revenue") or 0
        ) < float(settings.minimum_revenue or 0):
            return "not_enough_data"
        if any(item.get("severity") == "high" for item in confounders):
            return "inconclusive"
        relative = primary.get("relative_change_percent")
        if relative is None:
            return "not_enough_data"
        direction = 1 if primary.get("positive_is_good", True) else -1
        adjusted = relative * direction
        if adjusted >= 5:
            return "improved"
        if adjusted <= -5:
            return "worse"
        return "neutral"

    def _confidence(
        self, data: dict[str, Any], confounders: list[dict[str, Any]]
    ) -> str:
        if confounders or data.get("missing_post_days"):
            return "low"
        if (data.get("post_orders") or 0) >= 10:
            return "medium"
        return "low"

    def _seller_summary(
        self,
        metric: str,
        primary: dict[str, Any],
        outcome: str,
        confounders: list[dict[str, Any]],
    ) -> str:
        label = METRIC_CATALOG.get(
            metric, MetricDefinition(metric, metric, "unknown", "number", "sum")
        ).label
        relative = primary.get("relative_change_percent")
        if outcome == "not_enough_data":
            return f"Недостаточно данных для оценки метрики {label}. {CAUSALITY_DISCLAIMER}"
        if outcome == "inconclusive":
            return f"Результат искажён или неубедителен для метрики {label}. {CAUSALITY_DISCLAIMER}"
        change_text = (
            "без заметного изменения" if relative is None else f"{relative:.1f}%"
        )
        prefix = {
            "improved": "Наблюдаемое улучшение",
            "worse": "Наблюдаемое ухудшение",
            "neutral": "Нейтральный результат",
        }.get(outcome, "Результат")
        suffix = " Есть возможные искажающие факторы." if confounders else ""
        return f"{prefix}: {label} изменился на {change_text}.{suffix} {CAUSALITY_DISCLAIMER}"


class ExperimentSchedulerService:
    def __init__(self) -> None:
        self.collector = ExperimentMetricCollector()
        self.evaluator = ExperimentEvaluationService()
        self.repo = ExperimentRepository()

    async def process_due(self, session: AsyncSession, *, limit: int = 50) -> int:
        now = utcnow()
        result = await session.execute(
            select(Experiment)
            .where(
                Experiment.status.in_(("post_collecting", "ready_for_evaluation")),
                Experiment.evaluation_due_at <= now,
            )
            .order_by(Experiment.evaluation_due_at.asc(), Experiment.id.asc())
            .limit(limit)
        )
        count = 0
        for experiment in result.scalars().all():
            settings = await self.repo.settings(
                session, account_id=experiment.account_id
            )
            await ExperimentEventService().collect_post_and_evaluate(
                session, experiment=experiment, settings=settings
            )
            count += 1
        return count

    async def collect_daily_metric_snapshots(
        self, session: AsyncSession, *, limit: int = 100
    ) -> int:
        today = utcnow().date()
        yesterday = today - timedelta(days=1)
        result = await session.execute(
            select(Experiment)
            .where(
                Experiment.status == "post_collecting",
                Experiment.intervention_at.is_not(None),
            )
            .order_by(Experiment.intervention_at.asc(), Experiment.id.asc())
            .limit(limit)
        )
        count = 0
        for experiment in result.scalars().all():
            if experiment.intervention_at is None:
                continue
            post_start = experiment.intervention_at.date() + timedelta(
                days=max(0, experiment.evaluation_delay_days)
            )
            post_end = min(
                yesterday, post_start + timedelta(days=max(1, experiment.post_days) - 1)
            )
            if post_start > post_end:
                continue
            await self.collector.collect_window(
                session,
                experiment=experiment,
                window_type="post",
                start_date=post_start,
                end_date=post_end,
                metrics=ExperimentEventService()._metrics_for(experiment),
            )
            experiment.progress_json = {
                **(experiment.progress_json or {}),
                "post": {
                    "collected_through": post_end.isoformat(),
                    "target_days": experiment.post_days,
                },
            }
            count += 1
        return count


class ExperimentEventService:
    def __init__(self) -> None:
        self.repo = ExperimentRepository()
        self.collector = ExperimentMetricCollector()
        self.evaluator = ExperimentEvaluationService()

    def status(self) -> PortalExperimentsStatusRead:
        return PortalExperimentsStatusRead(
            supported_intervention_types=list(SUPPORTED_INTERVENTIONS)
        )

    async def settings(
        self, session: AsyncSession, *, account_id: int
    ) -> PortalExperimentSettingsRead:
        return self._settings_read(
            await self.repo.settings(session, account_id=account_id)
        )

    async def update_settings(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: PortalExperimentSettingsUpdate,
    ) -> PortalExperimentSettingsRead:
        row = await self.repo.settings(session, account_id=account_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            if value is not None:
                setattr(row, field, value)
        await session.flush()
        await session.refresh(row)
        return self._settings_read(row)

    async def create_experiment(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: PortalExperimentCreate,
        created_by: int | None,
    ) -> PortalExperimentRead:
        settings = await self.repo.settings(session, account_id=account_id)
        experiment = Experiment(
            account_id=account_id,
            nm_id=payload.nm_id,
            sku_id=payload.sku_id,
            name=payload.name,
            description=payload.description,
            experiment_type=payload.experiment_type,
            intervention_type=payload.intervention_type,
            status="planned" if payload.planned_start_at else "draft",
            hypothesis=payload.hypothesis,
            primary_metric=payload.primary_metric,
            secondary_metrics_json=payload.secondary_metrics,
            guardrail_metrics_json=payload.guardrail_metrics,
            baseline_days=payload.baseline_days or settings.default_baseline_days,
            post_days=payload.post_days or settings.default_post_days,
            evaluation_delay_days=payload.evaluation_delay_days
            if payload.evaluation_delay_days is not None
            else settings.default_evaluation_delay_days,
            planned_start_at=payload.planned_start_at,
            created_by_user_id=created_by,
            source_module=payload.source_module,
            source_action_key=payload.source_action_key,
            source_project_id=payload.source_project_id,
            is_test=payload.is_test,
            warnings_json=self._validation_warnings(payload),
        )
        session.add(experiment)
        await session.flush()
        await session.refresh(experiment)
        return await self._experiment_read(session, experiment)

    async def list_experiments(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        status: str | None = None,
        intervention_type: str | None = None,
        nm_id: int | None = None,
        include_test: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> PortalExperimentsPage:
        filters = [Experiment.account_id == account_id]
        if status:
            filters.append(Experiment.status == status)
        if intervention_type:
            filters.append(Experiment.intervention_type == intervention_type)
        if nm_id is not None:
            filters.append(Experiment.nm_id == nm_id)
        if not include_test:
            filters.append(Experiment.is_test.is_(False))
        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(Experiment).where(*filters)
                )
            ).scalar_one()
            or 0
        )
        rows = (
            (
                await session.execute(
                    select(Experiment)
                    .where(*filters)
                    .order_by(Experiment.created_at.desc(), Experiment.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        items = [await self._experiment_read(session, row) for row in rows]
        return PortalExperimentsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=items,
            summary=self._summary(items),
        )

    async def get_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None:
            return None
        return await self._experiment_read(session, row)

    async def update_experiment(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
        payload: PortalExperimentUpdate,
    ) -> PortalExperimentRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None or row.status in TERMINAL_STATUSES:
            return None
        data = payload.model_dump(exclude_unset=True)
        mapping = {
            "secondary_metrics": "secondary_metrics_json",
            "guardrail_metrics": "guardrail_metrics_json",
        }
        for field, value in data.items():
            setattr(row, mapping.get(field, field), value)
        await session.flush()
        await session.refresh(row)
        return await self._experiment_read(session, row)

    async def start_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None:
            return None
        settings = await self.repo.settings(session, account_id=account_id)
        if not settings.allow_overlapping_experiments and await self._has_overlap(
            session, row
        ):
            row.status = "failed"
            row.warnings_json = [
                *list(row.warnings_json or []),
                "overlapping_experiment",
            ]
            await session.flush()
            return await self._experiment_read(session, row)
        today = utcnow().date()
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=max(1, row.baseline_days) - 1)
        metrics = self._metrics_for(row)
        baseline = await self.collector.collect_window(
            session,
            experiment=row,
            window_type="baseline",
            start_date=start_date,
            end_date=end_date,
            metrics=metrics,
        )
        row.started_at = utcnow()
        row.baseline_summary_json = baseline
        row.progress_json = {
            "baseline": baseline,
            "post": {"complete_days": 0, "target_days": row.post_days},
        }
        row.status = (
            "ready_for_change"
            if self._baseline_ok(
                baseline, settings=settings, primary_metric=row.primary_metric
            )
            else "inconclusive"
        )
        await self._add_experiment_event(
            session,
            row,
            "baseline_ready"
            if row.status == "ready_for_change"
            else "baseline_invalid",
        )
        await session.flush()
        await session.refresh(row)
        return await self._experiment_read(session, row)

    async def record_intervention(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
        payload: PortalExperimentInterventionCreate,
        user_id: int | None,
    ) -> PortalExperimentInterventionRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None or row.status not in {
            "ready_for_change",
            "change_recorded",
            "post_collecting",
        }:
            return None
        if payload.applied_at > utcnow():
            row.warnings_json = [
                *list(row.warnings_json or []),
                "future_intervention_rejected",
            ]
            return None
        intervention = ExperimentIntervention(
            account_id=account_id,
            experiment_id=row.id,
            intervention_type=row.intervention_type,
            applied_at=payload.applied_at,
            applied_by_user_id=user_id,
            application_mode=payload.application_mode,
            before_reference_json=scrub_sensitive_payload(payload.before_reference),
            after_reference_json=scrub_sensitive_payload(payload.after_reference),
            change_summary=payload.change_summary,
            external_reference=payload.external_reference,
            confirmed_by_sync=payload.confirmed_by_sync,
            confirmed_at=utcnow() if payload.confirmed_by_sync else None,
        )
        row.intervention_at = payload.applied_at
        row.evaluation_due_at = payload.applied_at + timedelta(
            days=row.evaluation_delay_days + row.post_days
        )
        row.status = "post_collecting"
        session.add(intervention)
        await self._add_experiment_event(
            session,
            row,
            "intervention_recorded",
            before=payload.before_reference,
            after=payload.after_reference,
            changed_at=payload.applied_at,
        )
        await session.flush()
        await session.refresh(intervention)
        return self._intervention_read(intervention)

    async def collect_post_and_evaluate(
        self,
        session: AsyncSession,
        *,
        experiment: Experiment,
        settings: ExperimentSettings,
    ) -> ExperimentEvaluation:
        if experiment.intervention_at is None:
            raise ValueError("intervention_not_recorded")
        post_start = experiment.intervention_at.date() + timedelta(
            days=max(0, experiment.evaluation_delay_days)
        )
        post_end = post_start + timedelta(days=max(1, experiment.post_days) - 1)
        await self.collector.collect_window(
            session,
            experiment=experiment,
            window_type="post",
            start_date=post_start,
            end_date=post_end,
            metrics=self._metrics_for(experiment),
        )
        experiment.status = "ready_for_evaluation"
        evaluation = await self.evaluator.evaluate(
            session, experiment=experiment, settings=settings
        )
        await self._add_experiment_event(session, experiment, "evaluated")
        return evaluation

    async def evaluate_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentEvaluationRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None:
            return None
        settings = await self.repo.settings(session, account_id=account_id)
        evaluation = await self.collect_post_and_evaluate(
            session, experiment=row, settings=settings
        )
        return self._evaluation_read(evaluation)

    async def latest_evaluation(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentEvaluationRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None:
            return None
        evaluation = await self.repo.latest_evaluation(
            session, experiment_id=experiment_id
        )
        return self._evaluation_read(evaluation) if evaluation is not None else None

    async def metrics_page(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        experiment_id: int,
        limit: int,
        offset: int,
    ) -> PortalExperimentMetricsPage | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None:
            return None
        filters = [ExperimentMetricSnapshot.experiment_id == experiment_id]
        total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ExperimentMetricSnapshot)
                    .where(*filters)
                )
            ).scalar_one()
            or 0
        )
        rows = (
            (
                await session.execute(
                    select(ExperimentMetricSnapshot)
                    .where(*filters)
                    .order_by(
                        ExperimentMetricSnapshot.metric_date.asc(),
                        ExperimentMetricSnapshot.metric_name.asc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            )
            .scalars()
            .all()
        )
        return PortalExperimentMetricsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[self._metric_read(item) for item in rows],
        )

    async def cancel_experiment(
        self, session: AsyncSession, *, account_id: int, experiment_id: int
    ) -> PortalExperimentRead | None:
        row = await self.repo.get(
            session, account_id=account_id, experiment_id=experiment_id
        )
        if row is None:
            return None
        row.status = "cancelled"
        row.cancelled_at = utcnow()
        await self._add_experiment_event(session, row, "cancelled")
        await session.flush()
        await session.refresh(row)
        return await self._experiment_read(session, row)

    async def product_block(
        self, session: AsyncSession, *, account_id: int, nm_id: int, limit: int = 5
    ) -> dict[str, Any]:
        page = await self.list_experiments(
            session, account_id=account_id, nm_id=nm_id, limit=limit, offset=0
        )
        active = [
            item.model_dump(mode="json")
            for item in page.items
            if item.status in ACTIVE_STATUSES
        ]
        results = [
            item.latest_evaluation.model_dump(mode="json")
            for item in page.items
            if item.latest_evaluation is not None
        ]
        status = "empty"
        if active:
            status = "collecting"
        elif results:
            status = "ok"
        return {
            "status": status,
            "active_experiments": active,
            "latest_results": results,
            "recommended_experiment": self._recommended_experiment(nm_id),
            "warnings": sorted(
                {warning for item in page.items for warning in item.warnings}
            ),
            "last_evaluated_at": results[0]["evaluated_at"] if results else None,
        }

    async def action_candidates(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        limit: int = 50,
    ) -> list[PortalActionRead]:
        filters = [
            Experiment.account_id == account_id,
            Experiment.status.in_(
                tuple(ACTIVE_STATUSES | {"draft", "inconclusive", "failed"})
            ),
        ]
        if nm_id is not None:
            filters.append(Experiment.nm_id == nm_id)
        rows = (
            (
                await session.execute(
                    select(Experiment)
                    .where(*filters)
                    .order_by(
                        Experiment.evaluation_due_at.asc().nullslast(),
                        Experiment.updated_at.desc(),
                        Experiment.id.desc(),
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return [self._action_candidate(row) for row in rows]

    async def create_event(
        self,
        session: AsyncSession,
        *,
        payload: PortalExperimentEventCreate,
        created_by: int | None,
    ) -> PortalExperimentEventRead:
        event = ExperimentEvent(
            account_id=payload.account_id,
            nm_id=payload.nm_id,
            sku_id=payload.sku_id,
            action_id=payload.action_id,
            event_type=payload.event_type,
            before_json=scrub_sensitive_payload(payload.before_json or {}),
            after_json=scrub_sensitive_payload(payload.after_json or {}),
            changed_at=payload.changed_at or utcnow(),
            created_by=created_by,
        )
        session.add(event)
        await session.flush()
        await session.refresh(event)
        return self._event_read(event)

    async def list_product_events(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        nm_id: int,
        limit: int,
        offset: int,
    ) -> PortalExperimentEventsPage:
        filters = [ExperimentEvent.nm_id == nm_id]
        if account_id is not None:
            filters.append(ExperimentEvent.account_id == account_id)

        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(ExperimentEvent).where(*filters)
                )
            ).scalar_one()
            or 0
        )
        result = await session.execute(
            select(ExperimentEvent)
            .where(*filters)
            .order_by(ExperimentEvent.changed_at.desc(), ExperimentEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return PortalExperimentEventsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[self._event_read(event) for event in result.scalars().all()],
        )

    async def _add_experiment_event(
        self,
        session: AsyncSession,
        experiment: Experiment,
        event_type: str,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        changed_at: datetime | None = None,
    ) -> None:
        if experiment.nm_id is None:
            return
        session.add(
            ExperimentEvent(
                account_id=experiment.account_id,
                nm_id=experiment.nm_id,
                sku_id=experiment.sku_id,
                action_id=None,
                event_type=event_type,
                before_json=scrub_sensitive_payload(before or {}),
                after_json=scrub_sensitive_payload(
                    after
                    or {"experiment_id": experiment.id, "status": experiment.status}
                ),
                changed_at=changed_at or utcnow(),
                created_by=experiment.created_by_user_id,
            )
        )

    async def _has_overlap(self, session: AsyncSession, experiment: Experiment) -> bool:
        if experiment.nm_id is None:
            return False
        return (
            await session.execute(
                select(Experiment.id)
                .where(
                    Experiment.account_id == experiment.account_id,
                    Experiment.nm_id == experiment.nm_id,
                    Experiment.id != experiment.id,
                    Experiment.status.in_(tuple(ACTIVE_STATUSES)),
                )
                .limit(1)
            )
        ).scalar_one_or_none() is not None

    def _validation_warnings(self, payload: PortalExperimentCreate) -> list[str]:
        warnings: list[str] = []
        if payload.experiment_type == "controlled_split":
            warnings.append("controlled_split_not_supported_without_variant_assignment")
        if payload.primary_metric not in METRIC_CATALOG:
            warnings.append("primary_metric_unsupported")
        return warnings

    def _baseline_ok(
        self,
        baseline: dict[str, Any],
        *,
        settings: ExperimentSettings,
        primary_metric: str,
    ) -> bool:
        metric = (baseline.get("metrics") or {}).get(primary_metric) or {}
        if metric.get("status") != "ok":
            return False
        orders = ((baseline.get("metrics") or {}).get("orders_count") or {}).get(
            "value"
        )
        revenue = ((baseline.get("metrics") or {}).get("revenue") or {}).get("value")
        if orders is not None and orders < settings.minimum_orders:
            return False
        if revenue is not None and revenue < float(settings.minimum_revenue or 0):
            return False
        return True

    def _metrics_for(self, experiment: Experiment) -> list[str]:
        metrics = [
            experiment.primary_metric,
            "orders_count",
            "revenue",
            "ads_spend",
            "stockout_days",
        ]
        metrics.extend(experiment.secondary_metrics_json or [])
        metrics.extend(experiment.guardrail_metrics_json or [])
        return [metric for metric in dict.fromkeys(metrics) if metric in METRIC_CATALOG]

    def _summary(self, items: list[PortalExperimentRead]) -> dict[str, Any]:
        by_status: dict[str, int] = defaultdict(int)
        for item in items:
            by_status[item.status] += 1
        return {
            "by_status": dict(by_status),
            "active_count": sum(1 for item in items if item.status in ACTIVE_STATUSES),
        }

    def _recommended_experiment(self, nm_id: int) -> dict[str, Any]:
        return {
            "intervention_type": "manual_other",
            "nm_id": nm_id,
            "primary_metric": "estimated_profit",
            "post_days": 14,
            "message": "Track the next manual product change for 14 days before claiming impact.",
        }

    def _action_candidate(self, row: Experiment) -> PortalActionRead:
        action_by_status = {
            "draft": (
                "start_experiment",
                "Запустить эксперимент",
                "Зафиксируйте baseline перед ручным изменением.",
            ),
            "planned": (
                "start_experiment",
                "Запустить запланированный эксперимент",
                "Соберите baseline перед изменением.",
            ),
            "baseline_collecting": (
                "review_experiment_baseline",
                "Проверить baseline эксперимента",
                "Дождитесь готовности baseline или проверьте блокеры данных.",
            ),
            "ready_for_change": (
                "record_experiment_intervention",
                "Зафиксировать изменение для эксперимента",
                "Укажите точное время ручного изменения и что именно поменялось.",
            ),
            "change_recorded": (
                "monitor_experiment",
                "Проверить прогресс эксперимента",
                "Проверьте сбор post-window данных.",
            ),
            "post_collecting": (
                "monitor_experiment",
                "Проверить прогресс эксперимента",
                "Дождитесь окончания post-window или проверьте блокеры.",
            ),
            "ready_for_evaluation": (
                "evaluate_experiment",
                "Эксперимент готов к оценке",
                "Откройте Results и проверьте результат эксперимента.",
            ),
            "inconclusive": (
                "extend_experiment_observation",
                "Недостаточно данных по эксперименту",
                "Продлите наблюдение или проверьте confounders.",
            ),
            "failed": (
                "review_experiment_blocker",
                "Проверить блокер эксперимента",
                "Исправьте причину блокировки перед новым запуском.",
            ),
        }
        action_type, title, next_step = action_by_status.get(
            row.status,
            (
                "review_experiment",
                "Проверить эксперимент",
                "Откройте Results и проверьте состояние эксперимента.",
            ),
        )
        can_execute = row.status in {
            "draft",
            "planned",
            "ready_for_change",
            "ready_for_evaluation",
        }
        severity = "high" if row.status in {"failed", "inconclusive"} else "medium"
        priority = (
            "P2"
            if row.status in {"ready_for_change", "ready_for_evaluation", "failed"}
            else "P3"
        )
        return PortalActionRead(
            id=f"experiments:{row.id}:{action_type}",
            source="experiments",
            source_module="experiments",
            source_id=str(row.id),
            account_id=row.account_id,
            action_type=action_type,
            title=title,
            priority=priority,
            severity=severity,
            status="blocked" if row.status == "failed" else "new",
            reason=f"{row.name}: {row.hypothesis}",
            next_step=next_step,
            confidence="medium",
            nm_id=row.nm_id,
            sku_id=row.sku_id,
            deadline_at=row.evaluation_due_at,
            linked_entity={
                "experiment_id": row.id,
                "intervention_type": row.intervention_type,
            },
            payload={
                "experiment_id": row.id,
                "experiment_status": row.status,
                "primary_metric": row.primary_metric,
                "intervention_type": row.intervention_type,
                "evaluation_due_at": row.evaluation_due_at.isoformat()
                if row.evaluation_due_at
                else None,
                "causality_note": CAUSALITY_DISCLAIMER,
            },
            can_execute=can_execute,
            can_update_status=True,
            guided_fix={
                "target": "experiments",
                "action": action_type,
                "experiment_id": row.id,
                "path": f"/results/experiments/{row.id}",
            },
        )

    async def _experiment_read(
        self, session: AsyncSession, row: Experiment
    ) -> PortalExperimentRead:
        latest = await self.repo.latest_evaluation(session, experiment_id=row.id)
        return PortalExperimentRead(
            id=row.id,
            account_id=row.account_id,
            nm_id=row.nm_id,
            sku_id=row.sku_id,
            name=row.name,
            description=row.description,
            experiment_type=row.experiment_type,
            intervention_type=row.intervention_type,
            status=row.status,
            hypothesis=row.hypothesis,
            primary_metric=row.primary_metric,
            secondary_metrics=list(row.secondary_metrics_json or []),
            guardrail_metrics=list(row.guardrail_metrics_json or []),
            baseline_days=row.baseline_days,
            post_days=row.post_days,
            evaluation_delay_days=row.evaluation_delay_days,
            planned_start_at=row.planned_start_at,
            started_at=row.started_at,
            intervention_at=row.intervention_at,
            evaluation_due_at=row.evaluation_due_at,
            completed_at=row.completed_at,
            cancelled_at=row.cancelled_at,
            created_by_user_id=row.created_by_user_id,
            source_module=row.source_module,
            source_action_key=row.source_action_key,
            source_project_id=row.source_project_id,
            is_test=row.is_test,
            baseline_summary=row.baseline_summary_json or {},
            progress=row.progress_json or {},
            warnings=list(row.warnings_json or []),
            latest_evaluation=self._evaluation_read(latest)
            if latest is not None
            else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _settings_read(self, row: ExperimentSettings) -> PortalExperimentSettingsRead:
        return PortalExperimentSettingsRead(
            account_id=row.account_id,
            default_baseline_days=row.default_baseline_days,
            default_post_days=row.default_post_days,
            default_evaluation_delay_days=row.default_evaluation_delay_days,
            minimum_orders=row.minimum_orders,
            minimum_revenue=float(row.minimum_revenue or 0),
            minimum_views=row.minimum_views,
            maximum_stockout_days=row.maximum_stockout_days,
            allow_overlapping_experiments=row.allow_overlapping_experiments,
            weekday_matched_baseline=row.weekday_matched_baseline,
        )

    def _evaluation_read(
        self, row: ExperimentEvaluation
    ) -> PortalExperimentEvaluationRead:
        return PortalExperimentEvaluationRead(
            id=row.id,
            experiment_id=row.experiment_id,
            status=row.status,
            evaluation_version=row.evaluation_version,
            evaluated_at=row.evaluated_at,
            baseline_window=row.baseline_window_json or {},
            post_window=row.post_window_json or {},
            primary_result=row.primary_result_json or {},
            secondary_results=list(row.secondary_results_json or []),
            guardrail_results=list(row.guardrail_results_json or []),
            data_sufficiency=row.data_sufficiency_json or {},
            confounders=list(row.confounders_json or []),
            confidence=row.confidence,
            outcome=row.outcome,
            seller_summary=row.seller_summary,
            technical_summary=row.technical_summary_json or {},
        )

    def _intervention_read(
        self, row: ExperimentIntervention
    ) -> PortalExperimentInterventionRead:
        return PortalExperimentInterventionRead(
            id=row.id,
            experiment_id=row.experiment_id,
            intervention_type=row.intervention_type,
            applied_at=row.applied_at,
            applied_by_user_id=row.applied_by_user_id,
            application_mode=row.application_mode,
            change_summary=row.change_summary,
            before_reference=row.before_reference_json or {},
            after_reference=row.after_reference_json or {},
            external_reference=row.external_reference,
            confirmed_by_sync=row.confirmed_by_sync,
            confirmed_at=row.confirmed_at,
        )

    def _metric_read(
        self, row: ExperimentMetricSnapshot
    ) -> PortalExperimentMetricSnapshotRead:
        return PortalExperimentMetricSnapshotRead(
            id=row.id,
            experiment_id=row.experiment_id,
            window_type=row.window_type,
            metric_date=row.metric_date,
            metric_name=row.metric_name,
            metric_value=float(row.metric_value)
            if row.metric_value is not None
            else None,
            metric_unit=row.metric_unit,
            source=row.source,
            data_status=row.data_status,
            is_complete=row.is_complete,
            warnings=list(row.warnings_json or []),
            data_freshness_at=row.data_freshness_at,
            created_at=row.created_at,
        )

    def _event_read(self, event: ExperimentEvent) -> PortalExperimentEventRead:
        return PortalExperimentEventRead(
            id=event.id,
            account_id=event.account_id,
            nm_id=event.nm_id,
            sku_id=event.sku_id,
            action_id=event.action_id,
            event_type=event.event_type,
            before_json=event.before_json or {},
            after_json=event.after_json or {},
            changed_at=event.changed_at,
            created_by=event.created_by,
            created_at=event.created_at,
        )
