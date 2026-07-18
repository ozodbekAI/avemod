from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.operator import ResultEvent
from app.models.problem_engine import (
    ProblemEvaluationRunLog,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleVersion,
)
from app.models.sync import WBSyncRun
from app.services.problem_engine.evaluator import (
    ProblemEvaluationResult,
    ProblemEvaluatorService,
)
from app.services.result_tracking import ResultTrackingService


RELEVANT_SYNC_DOMAINS = frozenset(
    {
        "finance",
        "product_cards",
        "stocks",
        "sales",
        "orders",
        "ads",
        "prices",
    }
)
SUCCESSFUL_SYNC_STATUSES = frozenset({"completed", "partial"})


class ProblemEvaluationRunnerService:
    """Run the dynamic evaluator from jobs, sync hooks, admin APIs, and rechecks."""

    def __init__(self, *, evaluator: ProblemEvaluatorService | None = None) -> None:
        self.evaluator = evaluator or ProblemEvaluatorService()

    async def evaluate_account(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        trigger: str = "manual",
        sync_run_id: int | None = None,
        actor_user_id: int | None = None,
        problem_instance_id: int | None = None,
    ) -> ProblemEvaluationRunLog:
        return await self._run(
            session,
            account_id=account_id,
            trigger=trigger,
            scope="account",
            nm_ids=[],
            sync_run_id=sync_run_id,
            actor_user_id=actor_user_id,
            problem_instance_id=problem_instance_id,
            evaluate=lambda: self.evaluator.evaluate_account(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
            ),
        )

    async def evaluate_all_active_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        trigger: str = "scheduled_nightly",
    ) -> ProblemEvaluationRunLog:
        return await self._run(
            session,
            account_id=account_id,
            trigger=trigger,
            scope="all_active_products",
            nm_ids=[],
            sync_run_id=None,
            actor_user_id=None,
            problem_instance_id=None,
            evaluate=lambda: self.evaluator.evaluate_all_products(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
            ),
        )

    async def evaluate_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_ids: list[int] | tuple[int, ...] | set[int],
        date_from: date | None = None,
        date_to: date | None = None,
        trigger: str = "manual_products",
        sync_run_id: int | None = None,
        actor_user_id: int | None = None,
        problem_instance_id: int | None = None,
    ) -> ProblemEvaluationRunLog:
        unique_nm_ids = self._normalize_nm_ids(nm_ids)
        if not unique_nm_ids:
            return await self.evaluate_account(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                trigger=trigger,
                sync_run_id=sync_run_id,
                actor_user_id=actor_user_id,
                problem_instance_id=problem_instance_id,
            )

        async def evaluate() -> ProblemEvaluationResult:
            aggregate = ProblemEvaluationResult()
            for nm_id in unique_nm_ids:
                product_result = await self.evaluator.evaluate_product(
                    session,
                    account_id=account_id,
                    nm_id=nm_id,
                    date_from=date_from,
                    date_to=date_to,
                )
                self._merge_result(aggregate, product_result)
            return aggregate

        return await self._run(
            session,
            account_id=account_id,
            trigger=trigger,
            scope="products",
            nm_ids=unique_nm_ids,
            sync_run_id=sync_run_id,
            actor_user_id=actor_user_id,
            problem_instance_id=problem_instance_id,
            evaluate=evaluate,
        )

    async def evaluate_after_sync(
        self,
        session: AsyncSession,
        *,
        sync_run: WBSyncRun,
    ) -> ProblemEvaluationRunLog | None:
        if sync_run.domain not in RELEVANT_SYNC_DOMAINS:
            return None
        if sync_run.status not in SUCCESSFUL_SYNC_STATUSES:
            return None
        nm_ids = self.extract_nm_ids(sync_run.details or {})
        trigger = f"sync_{sync_run.domain}"
        if nm_ids:
            return await self.evaluate_products(
                session,
                account_id=sync_run.account_id,
                nm_ids=nm_ids,
                trigger=trigger,
                sync_run_id=sync_run.id,
            )
        return await self.evaluate_account(
            session,
            account_id=sync_run.account_id,
            trigger=trigger,
            sync_run_id=sync_run.id,
        )

    async def evaluate_after_manual_cost_import(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_ids: list[int] | tuple[int, ...] | set[int] | None = None,
    ) -> ProblemEvaluationRunLog:
        normalized = self._normalize_nm_ids(nm_ids or [])
        if normalized:
            return await self.evaluate_products(
                session,
                account_id=account_id,
                nm_ids=normalized,
                trigger="manual_cost_import",
            )
        return await self.evaluate_account(
            session,
            account_id=account_id,
            trigger="manual_cost_import",
        )

    async def recheck_problem_instance(
        self,
        session: AsyncSession,
        *,
        problem_instance_id: int,
        actor_user_id: int | None = None,
    ) -> tuple[ProblemEvaluationRunLog, ProblemInstance]:
        instance = await session.get(ProblemInstance, problem_instance_id)
        if instance is None:
            raise HTTPException(status_code=404, detail="Problem instance not found")
        rule = await session.get(ProblemRuleVersion, instance.rule_version_id)
        date_to = utcnow().date()
        lookback_days = max(int(getattr(rule, "lookback_days", 30) or 30), 1)
        date_from = date_to - timedelta(days=lookback_days - 1)
        old_value = {
            "status": instance.status,
            "last_seen_at": instance.last_seen_at.isoformat()
            if instance.last_seen_at
            else None,
            "resolved_at": instance.resolved_at.isoformat()
            if instance.resolved_at
            else None,
            "dismissed_at": instance.dismissed_at.isoformat()
            if instance.dismissed_at
            else None,
        }

        if instance.nm_id is not None and instance.entity_type == "product":
            log = await self.evaluate_products(
                session,
                account_id=instance.account_id,
                nm_ids=[int(instance.nm_id)],
                date_from=date_from,
                date_to=date_to,
                trigger="portal_recheck",
                actor_user_id=actor_user_id,
                problem_instance_id=instance.id,
            )
        else:
            log = await self.evaluate_account(
                session,
                account_id=instance.account_id,
                date_from=date_from,
                date_to=date_to,
                trigger="portal_recheck",
                actor_user_id=actor_user_id,
                problem_instance_id=instance.id,
            )

        refreshed = await session.get(ProblemInstance, problem_instance_id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Problem instance not found")
        old_status = str(old_value.get("status") or "")
        reopened_by_recheck = False
        if old_status in {"done", "resolved"} and str(refreshed.status or "") in {
            "done",
            "new",
            "acknowledged",
            "in_progress",
        }:
            before_reopen_status = str(refreshed.status or "new")
            refreshed.status = "reopened"
            reopened_by_recheck = True
            refreshed.resolved_at = None
            refreshed.dismissed_at = None
            refreshed.dismiss_reason = None
            snapshot = dict(refreshed.calculation_snapshot_json or {})
            action_state = (
                dict(snapshot.get("action_center") or {})
                if isinstance(snapshot.get("action_center"), dict)
                else {}
            )
            now = utcnow()
            action_state.update(
                {
                    "review_status": "in_progress",
                    "last_changed_at": now.isoformat(),
                    "last_status_changed_at": now.isoformat(),
                    "last_actor_user_id": actor_user_id,
                    "last_changed_by_user_id": actor_user_id,
                    "status_reason": "Problem condition still matches after re-check.",
                }
            )
            action_state.pop("closed_at", None)
            snapshot["action_center"] = action_state
            refreshed.calculation_snapshot_json = snapshot
            session.add(
                ProblemInstanceHistory(
                    problem_instance_id=refreshed.id,
                    event_type="reopened",
                    old_value_json={
                        "status": before_reopen_status,
                        "recheck_old_status": old_status,
                    },
                    new_value_json={"status": "reopened"},
                    comment="Problem condition still matches after re-check.",
                    actor_user_id=actor_user_id,
                )
            )
        new_value = {
            "status": refreshed.status,
            "last_seen_at": refreshed.last_seen_at.isoformat()
            if refreshed.last_seen_at
            else None,
            "resolved_at": refreshed.resolved_at.isoformat()
            if refreshed.resolved_at
            else None,
            "dismissed_at": refreshed.dismissed_at.isoformat()
            if refreshed.dismissed_at
            else None,
            "run_log_id": log.id,
        }
        session.add(
            ProblemInstanceHistory(
                problem_instance_id=refreshed.id,
                event_type="recheck_completed",
                old_value_json=old_value,
                new_value_json=new_value,
                comment="Problem instance rechecked from portal",
                actor_user_id=actor_user_id,
            )
        )
        await session.flush()
        await ResultTrackingService().create_problem_recheck_event(
            session,
            problem_instance_id=refreshed.id,
            created_by=actor_user_id,
            run_log_id=log.id,
            status=refreshed.status,
            payload={
                "trigger": "portal_recheck",
                "old_value": old_value,
                "new_value": new_value,
                "run_result": dict(log.result_json or {}),
            },
        )
        self._add_notification(
            session,
            refreshed,
            notification_type="recheck_completed",
            message="Dynamic problem re-check completed.",
            outcome="pending",
            payload={
                "old_value": old_value,
                "new_value": new_value,
                "run_log_id": log.id,
            },
            actor_user_id=actor_user_id,
        )
        if reopened_by_recheck or refreshed.status == "reopened":
            self._add_notification(
                session,
                refreshed,
                notification_type="issue_reopened",
                message="Dynamic problem reopened after re-check.",
                outcome="pending",
                payload={
                    "old_status": old_status,
                    "new_status": refreshed.status,
                    "run_log_id": log.id,
                },
                actor_user_id=actor_user_id,
            )
        if old_value.get("status") != refreshed.status and refreshed.status in {
            "done",
            "resolved",
        }:
            await ResultTrackingService().create_problem_completed_event(
                session,
                problem_instance_id=refreshed.id,
                created_by=actor_user_id,
                comment="Dynamic problem marked resolved after re-check.",
            )
        return log, refreshed

    @staticmethod
    def _add_notification(
        session: AsyncSession,
        instance: ProblemInstance,
        *,
        notification_type: str,
        message: str,
        outcome: str,
        payload: dict[str, Any] | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        session.add(
            ResultEvent(
                account_id=instance.account_id,
                problem_instance_id=instance.id,
                problem_code=instance.problem_code,
                source_module="action_center_notifications",
                source_id=str(instance.id),
                external_id=str(instance.id),
                nm_id=instance.nm_id,
                vendor_code=instance.vendor_code,
                event_type="action_center_notification",
                status="new",
                message=message,
                payload_json={
                    **jsonable_encoder(payload or {}),
                    "notification_type": notification_type,
                    "outcome": outcome,
                    "actor_user_id": actor_user_id,
                    "saved_money_claimed": False,
                },
            )
        )

    async def _run(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        trigger: str,
        scope: str,
        nm_ids: list[int],
        sync_run_id: int | None,
        actor_user_id: int | None,
        problem_instance_id: int | None,
        evaluate: Callable[[], Awaitable[ProblemEvaluationResult]],
    ) -> ProblemEvaluationRunLog:
        started_at = utcnow()
        log = ProblemEvaluationRunLog(
            account_id=account_id,
            trigger=trigger,
            scope=scope,
            sync_run_id=sync_run_id,
            problem_instance_id=problem_instance_id,
            actor_user_id=actor_user_id,
            nm_ids_json=nm_ids,
            started_at=started_at,
            status="running",
        )
        session.add(log)
        await session.flush()

        try:
            if hasattr(session, "begin_nested"):
                async with session.begin_nested():
                    result = await evaluate()
            else:
                result = await evaluate()
            self._apply_result(log, result, default_entities=len(nm_ids))
            log.status = "completed"
        except (
            Exception
        ) as exc:  # pragma: no cover - exercised through jobs in integration.
            log.status = "failed"
            log.errors_json = [str(exc)]
            log.result_json = {"error": str(exc), "trigger": trigger, "scope": scope}
        finally:
            log.finished_at = utcnow()
            await session.flush()
        return log

    def _apply_result(
        self,
        log: ProblemEvaluationRunLog,
        result: ProblemEvaluationResult,
        *,
        default_entities: int,
    ) -> None:
        entities = {
            preview.nm_id
            for preview in result.previews
            if getattr(preview, "nm_id", None) is not None
        }
        log.rules_evaluated = int(result.evaluated_count)
        log.entities_evaluated = len(entities) if entities else int(default_entities)
        log.issues_created = int(result.created_count)
        log.issues_updated = int(result.updated_count)
        log.issues_resolved = int(result.resolved_count)
        log.issues_candidate_resolved = int(result.candidate_resolved_count)
        log.issues_skipped = int(result.skipped_count)
        log.warnings_json = list(
            dict.fromkeys(str(item) for item in result.warnings if item)
        )[:100]
        log.errors_json = []
        log.result_json = jsonable_encoder(
            {
                "evaluated_count": result.evaluated_count,
                "matched_count": result.matched_count,
                "created_count": result.created_count,
                "updated_count": result.updated_count,
                "resolved_count": result.resolved_count,
                "candidate_resolved_count": result.candidate_resolved_count,
                "skipped_count": result.skipped_count,
                "test_mode": result.test_mode,
                "sample_previews": [
                    preview.model_dump() for preview in result.previews[:20]
                ],
            }
        )

    @staticmethod
    def _merge_result(
        target: ProblemEvaluationResult, source: ProblemEvaluationResult
    ) -> None:
        target.evaluated_count += source.evaluated_count
        target.matched_count += source.matched_count
        target.created_count += source.created_count
        target.updated_count += source.updated_count
        target.resolved_count += source.resolved_count
        target.candidate_resolved_count += source.candidate_resolved_count
        target.skipped_count += source.skipped_count
        target.previews.extend(source.previews)
        target.instances.extend(source.instances)
        target.warnings.extend(source.warnings)

    @staticmethod
    def extract_nm_ids(payload: Any) -> list[int]:
        values: set[int] = set()
        list_keys = {
            "nm_ids",
            "nmIds",
            "nmIDs",
            "changed_nm_ids",
            "changedNmIds",
            "product_nm_ids",
            "productNmIds",
            "updated_nm_ids",
            "updatedNmIds",
        }
        scalar_keys = {"nm_id", "nmId", "nmID", "nmid"}

        def add(value: Any) -> None:
            if value is None:
                return
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                return
            if parsed > 0:
                values.add(parsed)

        def walk(value: Any, *, key_context: str | None = None) -> None:
            if key_context in list_keys:
                if isinstance(value, (list, tuple, set)):
                    for item in value:
                        if isinstance(item, dict):
                            walk(item)
                        else:
                            add(item)
                    return
                add(value)
                return
            if key_context in scalar_keys:
                add(value)
                return
            if isinstance(value, dict):
                for key, item in value.items():
                    walk(item, key_context=str(key))
            elif isinstance(value, (list, tuple, set)):
                for item in value:
                    walk(item)

        walk(payload)
        return sorted(values)

    @staticmethod
    def _normalize_nm_ids(nm_ids: list[int] | tuple[int, ...] | set[int]) -> list[int]:
        normalized: set[int] = set()
        for value in nm_ids:
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            if parsed > 0:
                normalized.add(parsed)
        return sorted(normalized)
