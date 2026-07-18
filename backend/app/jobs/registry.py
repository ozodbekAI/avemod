from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.jobs.sync_jobs import (
    collect_experiment_metric_snapshots,
    process_ab_tests,
    process_queued_card_quality_runs,
    process_queued_claim_detection_runs,
    process_queued_grouping_runs,
    process_queued_photo_jobs,
    process_due_experiment_evaluations,
    process_queued_wb_sync_runs,
    process_queued_stock_control_runs,
    process_scheduled_reputation_auto_drafts,
    process_scheduled_reputation_syncs,
    refresh_scheduled_marts,
    refresh_scheduled_money_snapshots,
    run_nightly_dynamic_problem_evaluation,
    run_scheduled_data_quality_checks,
    run_scheduled_domain_sync,
)


def register_jobs(scheduler: AsyncIOScheduler) -> None:
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute="*/30"),
        kwargs={"domain": "orders"},
        id="sync-orders",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute="*/30"),
        kwargs={"domain": "sales"},
        id="sync-sales",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour="*/3"),
        kwargs={"domain": "stocks"},
        id="sync-stocks",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour=1),
        kwargs={"domain": "product_cards"},
        id="sync-product-cards",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour="2,14"),
        kwargs={"domain": "prices"},
        id="sync-prices",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour=3),
        kwargs={"domain": "finance"},
        id="sync-finance",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute="*/30"),
        kwargs={"domain": "supplies"},
        id="sync-supplies",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour="6,12,18"),
        kwargs={"domain": "ads"},
        id="sync-ads",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour="*/2"),
        kwargs={"domain": "analytics"},
        id="sync-analytics",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour=5),
        kwargs={"domain": "tariffs"},
        id="sync-tariffs",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_domain_sync,
        CronTrigger(minute=0, hour=7),
        kwargs={"domain": "documents"},
        id="sync-documents",
        replace_existing=True,
    )
    scheduler.add_job(
        process_queued_wb_sync_runs,
        CronTrigger(minute="*/1"),
        id="process-queued-wb-sync-runs",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_scheduled_marts,
        CronTrigger(minute=15, hour=8),
        id="refresh-marts",
        replace_existing=True,
    )
    scheduler.add_job(
        run_scheduled_data_quality_checks,
        CronTrigger(minute=30, hour=8),
        id="run-data-quality",
        replace_existing=True,
    )
    scheduler.add_job(
        refresh_scheduled_money_snapshots,
        CronTrigger(minute="*/10"),
        id="refresh-money-snapshots",
        replace_existing=True,
    )
    scheduler.add_job(
        run_nightly_dynamic_problem_evaluation,
        CronTrigger(minute=30, hour=4),
        id="dynamic-problem-nightly",
        replace_existing=True,
    )
    scheduler.add_job(
        process_queued_card_quality_runs,
        CronTrigger(minute="*/5"),
        id="process-card-quality-runs",
        replace_existing=True,
    )
    scheduler.add_job(
        process_queued_stock_control_runs,
        CronTrigger(minute="*/5"),
        id="process-queued-stock-control-runs",
        replace_existing=True,
    )
    scheduler.add_job(
        process_scheduled_reputation_syncs,
        CronTrigger(minute=20, hour="*/2"),
        id="sync-local-reputation",
        replace_existing=True,
    )
    scheduler.add_job(
        process_scheduled_reputation_auto_drafts,
        CronTrigger(minute=35, hour="*/2"),
        id="reputation-auto-draft-local",
        replace_existing=True,
    )
    scheduler.add_job(
        process_queued_claim_detection_runs,
        CronTrigger(minute="*/10"),
        id="process-queued-claim-detection-runs",
        replace_existing=True,
    )
    scheduler.add_job(
        process_queued_grouping_runs,
        CronTrigger(minute="*/15"),
        id="process-queued-grouping-runs",
        replace_existing=True,
    )
    scheduler.add_job(
        process_queued_photo_jobs,
        CronTrigger(minute="*/10"),
        id="process-queued-photo-jobs",
        replace_existing=True,
    )
    scheduler.add_job(
        collect_experiment_metric_snapshots,
        CronTrigger(minute=30, hour=9),
        id="collect-experiment-metric-snapshots",
        replace_existing=True,
    )
    scheduler.add_job(
        process_due_experiment_evaluations,
        CronTrigger(minute=45, hour=9),
        id="process-due-experiment-evaluations",
        replace_existing=True,
    )
    scheduler.add_job(
        process_ab_tests,
        CronTrigger(minute="*/2"),
        id="process-ab-tests",
        replace_existing=True,
    )
