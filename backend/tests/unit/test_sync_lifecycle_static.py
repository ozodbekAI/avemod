from __future__ import annotations

from pathlib import Path


def test_manual_sync_routes_are_accepted_and_queued() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    router_text = (repo_root / "backend/app/modules/sync/router.py").read_text(encoding="utf-8")
    service_text = (repo_root / "backend/app/services/sync.py").read_text(encoding="utf-8")
    jobs_text = (repo_root / "backend/app/jobs/sync_jobs.py").read_text(encoding="utf-8")
    registry_text = (repo_root / "backend/app/jobs/registry.py").read_text(encoding="utf-8")

    assert 'status_code=status.HTTP_202_ACCEPTED' in router_text
    assert "orchestrator.enqueue(" in router_text
    assert "background_tasks.add_task(process_queued_wb_sync_run" in router_text
    assert "async def enqueue(" in service_text
    assert 'status="queued"' in service_text
    assert "async def process_queued_run(" in service_text
    assert "async def process_queued_wb_sync_runs(" in jobs_text
    assert 'id="process-queued-wb-sync-runs"' in registry_text
