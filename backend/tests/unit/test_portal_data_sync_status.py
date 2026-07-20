from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.schemas.portal import PortalDataSyncDomainStatus, PortalDataSyncStatusRead
from app.services.portal import PortalService


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def one(self):
        return self._rows[0]

    def scalar_one(self):
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    def __init__(self, *result_rows):
        self._result_rows = list(result_rows)

    async def execute(self, _stmt):
        return _FakeResult(self._result_rows.pop(0))


async def _fake_empty_local_source_counts(*_args, **_kwargs):
    return {}


@pytest.mark.asyncio
async def test_data_sync_status_reports_missing_finance_token_and_preliminary_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)
    sales_run = SimpleNamespace(
        domain="sales",
        status="completed",
        finished_at=now - timedelta(hours=1),
        started_at=now - timedelta(hours=1, minutes=2),
        details={"rowsLoaded": 120},
        error_text=None,
    )
    sales_cursor = SimpleNamespace(
        domain="sales",
        cursor_key="default",
        cursor_value={},
        status="idle",
        last_synced_at=now - timedelta(hours=1),
        updated_at=now - timedelta(hours=1),
        created_at=now - timedelta(hours=1),
    )
    async def fake_raw_counts(*_args, **_kwargs):
        return {"sales": 3, "finance": 0}

    monkeypatch.setattr(service, "_raw_response_counts_by_domain", fake_raw_counts)
    monkeypatch.setattr(service, "_portal_local_source_counts", _fake_empty_local_source_counts)

    result = await service.data_sync_status(
        _FakeSession([sales_run], ["statistics"], [sales_cursor]),
        account_id=1,
    )

    by_domain = {item.domain: item for item in result.domains}
    assert by_domain["sales"].permission_status == "ok"
    assert by_domain["sales"].freshness_status == "fresh"
    assert by_domain["sales"].rows_loaded == 120
    assert by_domain["finance"].token_category == "finance"
    assert by_domain["finance"].permission_status == "missing"
    assert by_domain["finance"].freshness_status == "missing"
    assert "finance" in by_domain["finance"].next_recommended_action
    assert result.overall_state == "failed"


@pytest.mark.asyncio
async def test_data_sync_status_turns_wb_403_into_human_permission_message(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)
    failed_run = SimpleNamespace(
        domain="finance",
        status="failed",
        finished_at=now,
        started_at=now - timedelta(minutes=1),
        details={},
        error_text="WB API error 403: forbidden",
    )
    async def fake_raw_counts(*_args, **_kwargs):
        return {"finance": 0}

    monkeypatch.setattr(service, "_raw_response_counts_by_domain", fake_raw_counts)
    monkeypatch.setattr(service, "_portal_local_source_counts", _fake_empty_local_source_counts)

    result = await service.data_sync_status(
        _FakeSession([failed_run], ["finance"], []),
        account_id=1,
    )

    finance = {item.domain: item for item in result.domains}["finance"]
    assert finance.token_configured is True
    assert finance.permission_status == "missing"
    assert finance.source_status == "not_configured"
    assert finance.last_error_human_message == "Нет доступа WB. Нужен активный токен категории `finance`."
    assert finance.next_action == "fix_token"
    assert finance.user_facing_status == "Источник не настроен"


def test_auth_error_detection_ignores_sql_placeholders_with_401_403() -> None:
    error_text = (
        "(sqlalchemy.dialects.postgresql.asyncpg.IntegrityError) "
        "duplicate key value violates unique constraint ix_wb_sales_dedupe_key "
        "[SQL: INSERT INTO wb_sales VALUES ($399::BIGINT, $400::VARCHAR, "
        "$401::TIMESTAMP WITH TIME ZONE, $403::VARCHAR)]"
    )

    assert PortalService._is_auth_error(error_text) is False
    assert PortalService._is_auth_error("WB API error 403: forbidden") is True
    assert PortalService._is_auth_error("WB API error 401: unauthorized") is True


def test_data_sync_alignment_detects_new_connected_account() -> None:
    status, warnings, domains = PortalService._data_sync_alignment(
        [
            PortalDataSyncDomainStatus(
                domain="sales",
                status="not_started",
                token_category="statistics",
                token_configured=True,
                configured=True,
                permission_status="unknown",
                freshness_status="missing",
                source_status="missing",
            ),
            PortalDataSyncDomainStatus(
                domain="finance",
                status="not_started",
                token_category="finance",
                token_configured=True,
                configured=True,
                permission_status="unknown",
                freshness_status="missing",
                source_status="missing",
            ),
        ]
    )

    assert status == "new_account"
    assert "первая загрузка" in warnings[0]
    assert domains == ["sales", "finance"]


def test_data_sync_alignment_detects_domain_date_mismatch() -> None:
    now = datetime.now(timezone.utc)
    status, warnings, domains = PortalService._data_sync_alignment(
        [
            PortalDataSyncDomainStatus(
                domain="sales",
                status="completed",
                token_category="statistics",
                token_configured=True,
                configured=True,
                permission_status="ok",
                freshness_status="fresh",
                source_status="fresh",
                data_watermark_at=now,
                last_successful_sync_at=now,
            ),
            PortalDataSyncDomainStatus(
                domain="orders",
                status="completed",
                token_category="statistics",
                token_configured=True,
                configured=True,
                permission_status="ok",
                freshness_status="fresh",
                source_status="fresh",
                data_watermark_at=now - timedelta(hours=3),
                last_successful_sync_at=now,
            ),
        ]
    )

    assert status == "misaligned"
    assert any("Sales / orders" in warning for warning in warnings)
    assert domains == ["orders"]


def test_sync_data_watermark_does_not_use_run_timestamps_without_data_cursor() -> None:
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        status="completed",
        finished_at=now,
        started_at=now - timedelta(minutes=2),
        details={"rowsLoaded": 10},
    )

    assert PortalService._sync_data_watermark(cursor=None, run=run) is None


def test_data_sync_alignment_ignores_success_time_without_loaded_data() -> None:
    now = datetime.now(timezone.utc)
    status, warnings, domains = PortalService._data_sync_alignment(
        [
            PortalDataSyncDomainStatus(
                domain="sales",
                status="completed",
                token_category="statistics",
                token_configured=True,
                configured=True,
                permission_status="ok",
                freshness_status="fresh",
                source_status="fresh",
                last_successful_sync_at=now,
            )
        ]
    )

    assert status == "new_account"
    assert "первая загрузка" in warnings[0]
    assert domains == ["sales"]


@pytest.mark.asyncio
async def test_data_sync_status_treats_partial_as_stale_not_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)
    partial_run = SimpleNamespace(
        id=1,
        domain="sales",
        status="partial",
        trigger="manual",
        is_backfill=False,
        finished_at=now - timedelta(hours=1),
        started_at=now - timedelta(hours=1, minutes=2),
        details={"rowsLoaded": 7},
        error_text=None,
    )

    async def fake_raw_counts(*_args, **_kwargs):
        return {"sales": 7}

    monkeypatch.setattr(service, "_raw_response_counts_by_domain", fake_raw_counts)
    monkeypatch.setattr(
        service, "_portal_local_source_counts", _fake_empty_local_source_counts
    )

    result = await service.data_sync_status(
        _FakeSession([partial_run], ["statistics"], []),
        account_id=1,
    )

    sales = {item.domain: item for item in result.domains}["sales"]
    assert sales.status == "partial"
    assert sales.freshness_status == "stale"
    assert sales.source_status == "stale"
    assert sales.user_facing_status == "Нужна синхронизация"
    assert sales.next_recommended_action == "Запустить синхронизацию домена `sales`."


@pytest.mark.asyncio
async def test_data_sync_status_reports_fresh_missing_stale_error_not_configured_and_active_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)
    runs = [
        SimpleNamespace(
            id=1,
            domain="sales",
            status="completed",
            trigger="manual",
            is_backfill=False,
            finished_at=now - timedelta(hours=1),
            started_at=now - timedelta(hours=1, minutes=1),
            details={"rowsLoaded": 10},
            error_text=None,
        ),
        SimpleNamespace(
            id=2,
            domain="stocks",
            status="completed",
            trigger="manual",
            is_backfill=False,
            finished_at=now - timedelta(days=3),
            started_at=now - timedelta(days=3, minutes=1),
            details={"rowsLoaded": 20},
            error_text=None,
        ),
        SimpleNamespace(
            id=3,
            domain="finance",
            status="failed",
            trigger="manual",
            is_backfill=False,
            finished_at=now - timedelta(minutes=5),
            started_at=now - timedelta(minutes=6),
            details={},
            error_text="WB API 500",
        ),
        SimpleNamespace(
            id=4,
            domain="orders",
            status="running",
            trigger="manual",
            is_backfill=False,
            finished_at=None,
            started_at=now - timedelta(minutes=2),
            details={"progress_percent": 45},
            error_text=None,
        ),
        SimpleNamespace(
            id=5,
            domain="ads",
            status="queued",
            trigger="manual",
            is_backfill=False,
            finished_at=None,
            started_at=now,
            details={},
            error_text=None,
        ),
    ]
    cursors = [
        SimpleNamespace(
            domain="sales",
            cursor_key="default",
            cursor_value={},
            status="idle",
            last_synced_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
            created_at=now - timedelta(hours=1),
        ),
        SimpleNamespace(
            domain="stocks",
            cursor_key="default",
            cursor_value={},
            status="idle",
            last_synced_at=now - timedelta(days=3),
            updated_at=now - timedelta(days=3),
            created_at=now - timedelta(days=3),
        ),
    ]

    async def fake_raw_counts(*_args, **_kwargs):
        return {"sales": 10, "stocks": 20, "finance": 0, "prices": 0, "orders": 0, "ads": 0}

    monkeypatch.setattr(service, "_raw_response_counts_by_domain", fake_raw_counts)
    monkeypatch.setattr(service, "_portal_local_source_counts", _fake_empty_local_source_counts)

    result = await service.data_sync_status(
        _FakeSession(
            runs,
            ["statistics", "analytics", "finance", "prices", "promotion"],
            cursors,
        ),
        account_id=1,
    )

    by_domain = {item.domain: item for item in result.domains}
    assert by_domain["sales"].source_status == "fresh"
    assert by_domain["sales"].freshness_minutes is not None
    assert by_domain["prices"].source_status == "missing"
    assert by_domain["prices"].missing_reason == "Успешной синхронизации ещё не было."
    assert by_domain["stocks"].source_status == "stale"
    assert by_domain["finance"].source_status == "error"
    assert by_domain["documents"].source_status == "not_configured"
    assert by_domain["orders"].user_facing_status == "Синхронизация идёт"
    assert (
        result.user_facing_status
        == "Синхронизация идёт, расчёты обновятся после завершения"
    )
    assert result.has_active_sync is True
    assert result.calculation_refresh_status == "pending"
    assert (
        result.calculation_refresh_message
        == "Синхронизация идёт. Расчёты обновятся после завершения."
    )
    assert [run.id for run in result.active_sync_progress] == [4]
    assert [run.id for run in result.queued_syncs] == [5]
    assert result.active_sync_progress[0].progress_percent == 45


@pytest.mark.asyncio
async def test_data_sync_status_marks_stale_running_cursor_as_stuck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)
    stale_at = now - timedelta(hours=8)
    cursors = [
        SimpleNamespace(
            id=10,
            domain="stocks",
            cursor_key="default",
            cursor_value={},
            status="completed",
            last_synced_at=now - timedelta(hours=1),
            updated_at=now - timedelta(hours=1),
            created_at=now - timedelta(hours=1),
        ),
        SimpleNamespace(
            id=11,
            domain="stocks",
            cursor_key="pending_task",
            cursor_value={"taskId": "old-task"},
            status="running",
            last_synced_at=stale_at,
            updated_at=stale_at,
            created_at=stale_at - timedelta(minutes=5),
        ),
    ]

    async def fake_raw_counts(*_args, **_kwargs):
        return {"stocks": 20}

    monkeypatch.setattr(service, "_raw_response_counts_by_domain", fake_raw_counts)
    monkeypatch.setattr(service, "_portal_local_source_counts", _fake_empty_local_source_counts)

    result = await service.data_sync_status(
        _FakeSession([], ["analytics"], cursors),
        account_id=1,
    )

    stocks = {item.domain: item for item in result.domains}["stocks"]
    assert stocks.status == "failed"
    assert stocks.source_status == "error"
    assert stocks.last_successful_sync_at == cursors[0].last_synced_at
    assert "зависла" in (stocks.last_error_human_message or "")
    assert result.has_active_sync is False
    assert result.has_stale_running_sync is True
    assert result.calculation_refresh_status == "blocked"


@pytest.mark.asyncio
async def test_data_sync_status_uses_local_counts_for_readiness_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)

    async def fake_raw_counts(*_args, **_kwargs):
        return {}

    async def fake_local_counts(*_args, **_kwargs):
        return {
            "manual_costs": {
                "row_count": 12,
                "last_seen_at": now,
                "missing_reason": "Себестоимость не загружена.",
            }
        }

    monkeypatch.setattr(service, "_raw_response_counts_by_domain", fake_raw_counts)
    monkeypatch.setattr(service, "_portal_local_source_counts", fake_local_counts)

    result = await service.data_sync_status(
        _FakeSession([], [], []),
        account_id=1,
    )

    by_source = {item.source_code: item for item in result.sources}
    assert by_source["manual_costs"].status == "fresh"
    assert by_source["manual_costs"].last_synced_at == now
    assert by_source["manual_costs"].missing_reason is None
    assert by_source["manual_costs"].blocks_calculation == []


@pytest.mark.asyncio
async def test_data_readiness_sources_block_calculations_for_missing_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    service = PortalService()
    now = datetime.now(timezone.utc)

    async def fake_data_health(*_args, **_kwargs):
        return SimpleNamespace(
            final_profit_blockers_total=1,
            financial_final=False,
            operational_trusted=True,
            can_generate_business_actions=True,
            sku_cost_coverage_percent=0,
            revenue_cost_coverage_percent=0,
            missing_manual_cost_count=10,
            revenue_without_cost=1000,
            active_sku_count=10,
            active_sku_with_manual_cost_count=0,
        )

    async def fake_blockers(*_args, **_kwargs):
        return SimpleNamespace(blockers=[], warnings=[], warnings_count=0)

    async def fake_dq_summary(*_args, **_kwargs):
        return SimpleNamespace(financial_final_blockers_total=1)

    async def fake_sync_status(*_args, **_kwargs):
        return PortalDataSyncStatusRead(
            account_id=1,
            overall_state="warning",
            domains=[
                PortalDataSyncDomainStatus(
                    domain="finance",
                    status="not_started",
                    source_status="not_configured",
                    token_category="finance",
                    token_configured=False,
                    permission_status="missing",
                    freshness_status="missing",
                    missing_reason="Не настроен активный WB токен категории `finance`.",
                ),
                PortalDataSyncDomainStatus(
                    domain="sales",
                    status="completed",
                    source_status="fresh",
                    token_category="statistics",
                    token_configured=True,
                    permission_status="ok",
                    freshness_status="fresh",
                    last_synced_at=now,
                    last_successful_sync_at=now,
                ),
                PortalDataSyncDomainStatus(
                    domain="orders",
                    status="completed",
                    source_status="fresh",
                    token_category="statistics",
                    token_configured=True,
                    permission_status="ok",
                    freshness_status="fresh",
                    last_synced_at=now,
                    last_successful_sync_at=now,
                ),
            ],
        )

    async def fake_local_counts(*_args, **_kwargs):
        return {
            "manual_costs": {"row_count": 0, "missing_reason": "Себестоимость не загружена."},
            "checker_card_quality": {"row_count": 0},
            "data_fix": {"row_count": 1, "last_seen_at": now},
            "problem_engine": {"row_count": 0, "configured": False, "missing_reason": "Нет активных правил problem engine."},
        }

    monkeypatch.setattr(service.operator_snapshots, "data_health", fake_data_health)
    monkeypatch.setattr(service.money, "data_blockers", fake_blockers)
    monkeypatch.setattr(service.operator_snapshots, "dq_issue_summary", fake_dq_summary)
    monkeypatch.setattr(service, "data_sync_status", fake_sync_status)
    monkeypatch.setattr(service, "_portal_local_source_counts", fake_local_counts)

    result = await service.data_readiness(
        _FakeSession(),
        account_id=1,
        date_from=None,
        date_to=None,
    )

    by_source = {item.source_code: item for item in result.sources}
    assert by_source["finance_reports_wb"].status == "not_configured"
    assert "final_profit" in by_source["finance_reports_wb"].blocks_calculation
    assert by_source["manual_costs"].status == "missing"
    assert "unit_profit" in by_source["manual_costs"].blocks_calculation
    assert by_source["data_fix"].status == "fresh"
