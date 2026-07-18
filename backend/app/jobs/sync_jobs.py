from __future__ import annotations

import logging
import traceback

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.config import get_settings
from app.models.accounts import WBAPICategory, WBAPIToken, WBAccount
from app.models.card_quality import CardQualityAnalysisRun
from app.models.claims import ClaimDetectionRun
from app.models.grouping import GroupingRun
from app.models.photo_studio import PhotoGenerationJob
from app.models.reputation import ReputationSettings
from app.models.sync import WBSyncRun
from app.services.claims_adapter import ClaimsDefectAdapter
from app.services.claims_factory import ClaimsFactoryService
from app.services.card_quality import CardQualityAnalysisService
from app.services.data_quality import DataQualityService
from app.services.grouping import GroupingBetaService
from app.services.marts import MartService
from app.services.sync import SyncOrchestrator
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.operator_snapshots import OperatorEndpointSnapshotService
from app.services.photo_studio import PhotoStudioService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService
from app.services.reputation import ReputationService
from app.services.stock_control import StockControlService
from app.services.experiments import ExperimentSchedulerService
from app.services.ab_tests import ABTestService

logger = logging.getLogger(__name__)


async def _evaluate_dynamic_problems_after_sync(session, run: WBSyncRun) -> bool:
    account_id = int(run.account_id)
    domain = str(run.domain)
    sync_run_id = int(run.id)
    settings = get_settings()
    if not settings.dynamic_problem_engine_enabled:
        return True
    rollout_ids = set(settings.dynamic_problem_engine_test_account_ids or [])
    if rollout_ids and account_id not in {int(item) for item in rollout_ids}:
        return True
    try:
        await ProblemEvaluationRunnerService().evaluate_after_sync(
            session, sync_run=run
        )
    except Exception:
        logger.exception(
            "Dynamic problem evaluation after sync failed",
            extra={
                "account_id": account_id,
                "domain": domain,
                "sync_run_id": sync_run_id,
            },
        )
        return False
    return True


async def run_scheduled_domain_sync(domain: str) -> None:
    async with SessionLocal() as discovery_session:
        accounts = list(
            (
                await discovery_session.execute(
                    select(WBAccount.id).where(WBAccount.is_active.is_(True))
                )
            ).scalars()
        )

    for account_id in accounts:
        async with SessionLocal() as session:
            orchestrator = SyncOrchestrator(session)
            dq = DataQualityService()
            try:
                service = orchestrator._get_service(domain)
                token_exists = (
                    await session.execute(
                        select(WBAPIToken.id).where(
                            WBAPIToken.account_id == account_id,
                            WBAPIToken.category == service.category,
                            WBAPIToken.is_active.is_(True),
                        )
                    )
                ).scalar_one_or_none()
                if token_exists is None:
                    await dq.resolve_issues(
                        session,
                        account_id=account_id,
                        domain="scheduler",
                        codes=["scheduler_job_failed"],
                        entity_key=f"{domain}:{account_id}",
                    )
                    await session.commit()
                    continue
                run = await orchestrator.trigger(
                    account_id=account_id,
                    domain=domain,
                    trigger="scheduler",
                    raise_on_error=False,
                )
                if run.status == "failed":
                    await dq.open_issue(
                        session,
                        account_id=account_id,
                        domain="scheduler",
                        code="scheduler_job_failed",
                        message=run.error_text
                        or f"Scheduled sync failed for domain {domain}",
                        severity="warning",
                        entity_key=f"{domain}:{account_id}",
                        payload={
                            "domain": domain,
                            "accountId": account_id,
                            "syncRunId": run.id,
                            "details": run.details,
                            "errorText": run.error_text,
                        },
                    )
                elif run.status in {"completed", "partial"}:
                    await dq.resolve_issues(
                        session,
                        account_id=account_id,
                        domain="scheduler",
                        codes=["scheduler_job_failed"],
                        entity_key=f"{domain}:{account_id}",
                    )
                    await _evaluate_dynamic_problems_after_sync(session, run)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "Scheduled domain sync failed",
                    extra={"account_id": account_id, "domain": domain},
                )
                try:
                    await dq.open_issue(
                        session,
                        account_id=account_id,
                        domain="scheduler",
                        code="scheduler_job_failed",
                        message=str(exc),
                        severity="warning",
                        entity_key=f"{domain}:{account_id}",
                        payload={
                            "domain": domain,
                            "accountId": account_id,
                            "traceback": traceback.format_exc(limit=10)[-4000:],
                        },
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()


async def process_queued_wb_sync_run(run_id: int) -> None:
    sync_run_id = int(run_id)
    account_id: int | None = None
    domain: str | None = None
    run_status: str | None = None

    async with SessionLocal() as session:
        try:
            orchestrator = SyncOrchestrator(session)
            run = await orchestrator.process_queued_run(run_id=sync_run_id)
            sync_run_id = int(run.id)
            account_id = int(run.account_id)
            domain = str(run.domain)
            run_status = str(run.status)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Queued WB sync run failed", extra={"run_id": sync_run_id})
            return

    if account_id is None or domain is None:
        return

    async with SessionLocal() as session:
        try:
            await MoneyEndpointSnapshotService().invalidate_snapshots(
                session, account_id=account_id
            )
            await OperatorEndpointSnapshotService().invalidate_snapshots(
                session, account_id=account_id
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Queued WB sync snapshot invalidation failed",
                extra={
                    "account_id": account_id,
                    "domain": domain,
                    "sync_run_id": sync_run_id,
                },
            )

    if run_status not in {"completed", "partial"}:
        return

    async with SessionLocal() as session:
        try:
            run = await session.get(WBSyncRun, sync_run_id)
            if run is None:
                logger.warning(
                    "Queued WB sync run disappeared before dynamic problem evaluation",
                    extra={
                        "account_id": account_id,
                        "domain": domain,
                        "sync_run_id": sync_run_id,
                    },
                )
                return
            if await _evaluate_dynamic_problems_after_sync(session, run):
                await session.commit()
            else:
                await session.rollback()
        except Exception:
            await session.rollback()
            logger.exception(
                "Dynamic problem evaluation after queued sync failed",
                extra={
                    "account_id": account_id,
                    "domain": domain,
                    "sync_run_id": sync_run_id,
                },
            )


async def process_queued_wb_sync_runs(*, max_runs: int = 3) -> None:
    async with SessionLocal() as discovery_session:
        run_ids = list(
            (
                await discovery_session.execute(
                    select(WBSyncRun.id)
                    .where(WBSyncRun.status.in_(("queued", "running")))
                    .order_by(WBSyncRun.id.asc())
                    .limit(max(1, int(max_runs)))
                )
            ).scalars()
        )
    for run_id in run_ids:
        await process_queued_wb_sync_run(int(run_id))


async def refresh_scheduled_marts() -> None:
    async with SessionLocal() as discovery_session:
        accounts = list(
            (
                await discovery_session.execute(
                    select(WBAccount.id).where(WBAccount.is_active.is_(True))
                )
            ).scalars()
        )
    service = MartService()
    for account_id in accounts:
        async with SessionLocal() as session:
            try:
                await service.refresh_account(session, account_id=account_id)
                await session.commit()
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "Scheduled mart refresh failed", extra={"account_id": account_id}
                )
                dq = DataQualityService()
                try:
                    await dq.open_issue(
                        session,
                        account_id=account_id,
                        domain="scheduler",
                        code="scheduler_job_failed",
                        message=str(exc),
                        severity="warning",
                        entity_key=f"marts:{account_id}",
                        payload={
                            "domain": "marts",
                            "accountId": account_id,
                            "traceback": traceback.format_exc(limit=10)[-4000:],
                        },
                    )
                    await session.commit()
                except Exception:
                    await session.rollback()


async def run_nightly_dynamic_problem_evaluation() -> None:
    settings = get_settings()
    if not settings.dynamic_problem_engine_enabled:
        return
    async with SessionLocal() as discovery_session:
        stmt = select(WBAccount.id).where(WBAccount.is_active.is_(True))
        rollout_ids = set(settings.dynamic_problem_engine_test_account_ids or [])
        if rollout_ids:
            stmt = stmt.where(WBAccount.id.in_([int(item) for item in rollout_ids]))
        accounts = list((await discovery_session.execute(stmt)).scalars())
    runner = ProblemEvaluationRunnerService()
    for account_id in accounts:
        async with SessionLocal() as session:
            try:
                await runner.evaluate_all_active_products(
                    session,
                    account_id=int(account_id),
                    trigger="scheduled_nightly",
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Nightly dynamic problem evaluation failed",
                    extra={"account_id": int(account_id)},
                )


async def run_scheduled_data_quality_checks() -> None:
    service = DataQualityService()
    async with SessionLocal() as session:
        try:
            await service.run_checks(session)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled data quality run failed")


async def refresh_scheduled_money_snapshots() -> None:
    money_service = MoneyEndpointSnapshotService()
    operator_service = OperatorEndpointSnapshotService()
    try:
        await money_service.refresh_active_account_snapshots()
        await operator_service.refresh_active_account_snapshots()
    except Exception:
        logger.exception("Scheduled money snapshot refresh failed")


async def process_queued_card_quality_runs(
    *, max_runs: int = 5, batch_limit: int = 100
) -> None:
    async with SessionLocal() as discovery_session:
        run_ids = list(
            (
                await discovery_session.execute(
                    select(CardQualityAnalysisRun.id)
                    .where(
                        CardQualityAnalysisRun.run_type == "account_batch",
                        CardQualityAnalysisRun.status.in_(("queued", "running")),
                    )
                    .order_by(CardQualityAnalysisRun.id.asc())
                    .limit(max(1, int(max_runs)))
                )
            ).scalars()
        )

    service = CardQualityAnalysisService()
    for run_id in run_ids:
        async with SessionLocal() as session:
            try:
                await service.process_run_batch(
                    session, run_id=int(run_id), batch_limit=batch_limit
                )
            except Exception:
                await session.rollback()
                logger.exception(
                    "Scheduled card quality batch failed", extra={"run_id": int(run_id)}
                )


async def process_queued_stock_control_runs(*, max_runs: int = 5) -> None:
    service = StockControlService()
    async with SessionLocal() as session:
        try:
            await service.process_queued_runs(session, max_runs=max_runs)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled stock control run processing failed")


async def process_scheduled_reputation_syncs(*, max_accounts: int = 20) -> None:
    settings = get_settings()
    if not settings.reputation_auto_sync_enabled:
        logger.info(
            "Scheduled reputation sync skipped: REPUTATION_AUTO_SYNC_ENABLED=false"
        )
        return
    async with SessionLocal() as discovery_session:
        account_ids = list(
            (
                await discovery_session.execute(
                    select(WBAccount.id)
                    .join(WBAPIToken, WBAPIToken.account_id == WBAccount.id)
                    .where(
                        WBAccount.is_active.is_(True),
                        WBAPIToken.category == WBAPICategory.FEEDBACKS_QUESTIONS.value,
                        WBAPIToken.is_active.is_(True),
                    )
                    .order_by(WBAccount.id.asc())
                    .limit(max(1, int(max_accounts)))
                )
            ).scalars()
        )

    service = ReputationService()
    for account_id in account_ids:
        async with SessionLocal() as session:
            try:
                account = await session.get(WBAccount, int(account_id))
                if account is None:
                    continue
                module_settings = (
                    await session.execute(
                        select(
                            ReputationSettings.automation_enabled,
                            ReputationSettings.auto_sync,
                        ).where(ReputationSettings.account_id == int(account_id))
                    )
                ).one_or_none()
                if module_settings is None:
                    continue
                automation_enabled, auto_sync = module_settings
                if not automation_enabled or not auto_sync:
                    continue
                await service.sync_reputation(session, account)
            except Exception:
                await session.rollback()
                logger.exception(
                    "Scheduled reputation sync failed",
                    extra={"account_id": int(account_id)},
                )


async def process_scheduled_reputation_auto_drafts(*, max_items: int = 50) -> None:
    settings = get_settings()
    if not settings.reputation_auto_draft_enabled:
        logger.info(
            "Scheduled reputation auto-draft skipped: REPUTATION_AUTO_DRAFT_ENABLED=false"
        )
        return
    service = ReputationService(settings=settings)
    async with SessionLocal() as session:
        try:
            await service.process_auto_draft_queue(session, max_items=max_items)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled reputation auto-draft queue failed")


async def process_queued_claim_detection_runs(*, max_runs: int = 10) -> None:
    async with SessionLocal() as discovery_session:
        run_ids = list(
            (
                await discovery_session.execute(
                    select(ClaimDetectionRun.id)
                    .where(ClaimDetectionRun.status.in_(("queued", "running")))
                    .order_by(ClaimDetectionRun.id.asc())
                    .limit(max(1, int(max_runs)))
                )
            ).scalars()
        )

    service = ClaimsFactoryService()
    detector = ClaimsDefectAdapter()
    for run_id in run_ids:
        async with SessionLocal() as session:
            try:
                await service.process_detection_run(
                    session, run_id=int(run_id), detector=detector
                )
                await session.commit()
            except Exception:
                await session.rollback()
                logger.exception(
                    "Scheduled claims detection run failed",
                    extra={"run_id": int(run_id)},
                )


async def process_queued_grouping_runs(*, max_runs: int = 5) -> None:
    async with SessionLocal() as discovery_session:
        has_runs = (
            await discovery_session.execute(
                select(GroupingRun.id)
                .where(GroupingRun.status.in_(("queued", "running")))
                .limit(1)
            )
        ).scalar_one_or_none()
    if has_runs is None:
        return
    async with SessionLocal() as session:
        try:
            await GroupingBetaService().process_queued_runs(session, max_runs=max_runs)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled grouping beta run processing failed")


async def process_queued_photo_jobs(*, max_jobs: int = 5) -> None:
    async with SessionLocal() as discovery_session:
        has_jobs = (
            await discovery_session.execute(
                select(PhotoGenerationJob.id)
                .where(PhotoGenerationJob.status.in_(("queued", "running")))
                .limit(1)
            )
        ).scalar_one_or_none()
    if has_jobs is None:
        return
    async with SessionLocal() as session:
        try:
            await PhotoStudioService().process_queued_jobs(session, max_jobs=max_jobs)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled photo job processing failed")


async def collect_experiment_metric_snapshots(*, limit: int = 100) -> None:
    service = ExperimentSchedulerService()
    async with SessionLocal() as session:
        try:
            await service.collect_daily_metric_snapshots(session, limit=limit)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled experiment metric collection failed")


async def process_due_experiment_evaluations(*, limit: int = 50) -> None:
    service = ExperimentSchedulerService()
    async with SessionLocal() as session:
        try:
            await service.process_due(session, limit=limit)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled experiment evaluation processing failed")


async def process_ab_tests(*, limit: int = 100) -> None:
    service = ABTestService()
    async with SessionLocal() as session:
        try:
            await service.process_due(session, limit=limit)
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception("Scheduled A/B test processing failed")
