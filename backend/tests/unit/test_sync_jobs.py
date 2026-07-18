from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.jobs import sync_jobs


class _FakeSession:
    def __init__(self, *, run=None) -> None:
        self.run = run
        self.commits = 0
        self.rollbacks = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def get(self, model, item_id):
        return self.run


@pytest.mark.asyncio
async def test_process_queued_run_commits_sync_before_problem_evaluation_failure(monkeypatch) -> None:
    run = SimpleNamespace(id=7700, account_id=1, domain="stocks", status="completed")
    sync_session = _FakeSession()
    snapshot_session = _FakeSession()
    evaluation_session = _FakeSession(run=run)
    sessions = [sync_session, snapshot_session, evaluation_session]

    def fake_session_local():
        return sessions.pop(0)

    class FakeOrchestrator:
        def __init__(self, session) -> None:
            self.session = session

        async def process_queued_run(self, *, run_id: int):
            assert run_id == 7700
            return run

    class FakeSnapshotService:
        async def invalidate_snapshots(self, session, *, account_id: int) -> None:
            assert account_id == 1

    async def fail_problem_evaluation(session, sync_run) -> bool:
        raise RuntimeError("evaluation failed after sync commit")

    monkeypatch.setattr(sync_jobs, "SessionLocal", fake_session_local)
    monkeypatch.setattr(sync_jobs, "SyncOrchestrator", FakeOrchestrator)
    monkeypatch.setattr(sync_jobs, "MoneyEndpointSnapshotService", FakeSnapshotService)
    monkeypatch.setattr(sync_jobs, "OperatorEndpointSnapshotService", FakeSnapshotService)
    monkeypatch.setattr(sync_jobs, "_evaluate_dynamic_problems_after_sync", fail_problem_evaluation)

    await sync_jobs.process_queued_wb_sync_run(7700)

    assert sync_session.commits == 1
    assert sync_session.rollbacks == 0
    assert snapshot_session.commits == 1
    assert snapshot_session.rollbacks == 0
    assert evaluation_session.commits == 0
    assert evaluation_session.rollbacks == 1
