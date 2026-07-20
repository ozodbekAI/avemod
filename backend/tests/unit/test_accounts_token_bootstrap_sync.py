from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.modules.accounts import router as accounts_router


class _FakeScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeSession:
    def __init__(self, *scalar_values):
        self._scalar_values = list(scalar_values)
        self.enqueued: list[dict] = []

    async def execute(self, _stmt):
        return _FakeScalarResult(self._scalar_values.pop(0))


class _FakeSyncOrchestrator:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session

    async def enqueue(self, **kwargs):
        self.session.enqueued.append(kwargs)
        return SimpleNamespace(id=len(self.session.enqueued))


@pytest.mark.asyncio
async def test_token_bootstrap_enqueues_missing_domain_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(accounts_router, "SyncOrchestrator", _FakeSyncOrchestrator)
    session = _FakeSession(
        None,  # orders has no active run
        None,  # orders has no previous run
        None,  # sales has no active run
        "completed",  # sales was already loaded
    )

    run_ids = await accounts_router._enqueue_initial_sync_for_token(
        session, account_id=1, category="statistics"
    )

    assert run_ids == [1]
    assert session.enqueued == [
        {
            "account_id": 1,
            "domain": "orders",
            "trigger": "token_configured",
            "force_full": True,
        }
    ]
