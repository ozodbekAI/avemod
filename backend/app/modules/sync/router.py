from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.config import get_settings
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.models.sync import WBSyncCursor
from app.schemas.sync import (
    SyncBackfillRequest,
    SyncCursorRead,
    SyncRunRead,
    SyncTriggerRequest,
)
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
)
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.operator_snapshots import OperatorEndpointSnapshotService
from app.services.portal import PortalService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService
from app.services.sync import SyncOrchestrator
from app.jobs.sync_jobs import process_queued_wb_sync_run

router = APIRouter(tags=["sync"])
money_snapshot_service = MoneyEndpointSnapshotService()
operator_snapshot_service = OperatorEndpointSnapshotService()
problem_evaluation_runner = ProblemEvaluationRunnerService()

READ_ROLES = {"viewer", "operator", "manager", "admin"}
MANAGER_ROLES = {"manager", "admin"}
ADMIN_ROLES = {"admin"}


async def _resolve_read_account(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
) -> int | None:
    account = await resolve_user_account(
        session, user, account_id=account_id, require_account=not user.is_superuser
    )
    if account is not None:
        await require_account_role(
            session, user, account_id=account.id, allowed_roles=READ_ROLES
        )
        return int(account.id)
    return None


async def _invalidate_account_snapshots(
    session: AsyncSession, *, account_id: int
) -> None:
    await money_snapshot_service.invalidate_snapshots(session, account_id=account_id)
    await operator_snapshot_service.invalidate_snapshots(session, account_id=account_id)
    PortalService.invalidate_shared_runtime_caches()


def _cursor_read(cursor: WBSyncCursor) -> SyncCursorRead:
    return SyncCursorRead(
        id=cursor.id,
        account_id=cursor.account_id,
        domain=cursor.domain,
        cursor_key=cursor.cursor_key,
        cursor_value=cursor.cursor_value,
        last_synced_at=cursor.last_synced_at,
        status=cursor.status,
        next_scheduled_at=(cursor.cursor_value or {}).get("nextScheduledAt"),
        last_error_text=(cursor.cursor_value or {}).get("lastErrorText"),
        last_error_at=(cursor.cursor_value or {}).get("lastErrorAt"),
    )


@router.post(
    "/sync/trigger", response_model=SyncRunRead, status_code=status.HTTP_202_ACCEPTED
)
async def trigger_sync(
    payload: SyncTriggerRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SyncRunRead:
    await resolve_user_account(
        session, current_user, account_id=payload.account_id, require_account=True
    )
    await require_account_role(
        session,
        current_user,
        account_id=payload.account_id,
        allowed_roles=MANAGER_ROLES,
    )
    orchestrator = SyncOrchestrator(session)
    run = await orchestrator.enqueue(
        account_id=payload.account_id,
        domain=payload.domain,
        trigger="manual",
        force_full=payload.force_full,
    )
    await _invalidate_account_snapshots(session, account_id=payload.account_id)
    await session.commit()
    background_tasks.add_task(process_queued_wb_sync_run, int(run.id))
    return run


@router.post(
    "/sync/backfill", response_model=SyncRunRead, status_code=status.HTTP_202_ACCEPTED
)
async def backfill_sync(
    payload: SyncBackfillRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SyncRunRead:
    await resolve_user_account(
        session, current_user, account_id=payload.account_id, require_account=True
    )
    await require_account_role(
        session, current_user, account_id=payload.account_id, allowed_roles=ADMIN_ROLES
    )
    orchestrator = SyncOrchestrator(session)
    run = await orchestrator.enqueue(
        account_id=payload.account_id,
        domain=payload.domain,
        trigger="manual_backfill",
        force_full=payload.force_full,
        backfill_from=payload.date_from,
        backfill_to=payload.date_to,
    )
    await _invalidate_account_snapshots(session, account_id=payload.account_id)
    await session.commit()
    background_tasks.add_task(process_queued_wb_sync_run, int(run.id))
    return run


@router.get("/sync/runs", response_model=Page[SyncRunRead])
async def list_runs(
    account_id: int | None = Query(default=None),
    domain: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[SyncRunRead]:
    account_id = await _resolve_read_account(
        session, current_user, account_id=account_id
    )
    orchestrator = SyncOrchestrator(session)
    return await orchestrator.list_runs(
        account_id=account_id, domain=domain, limit=limit, offset=offset
    )


@router.get("/sync/cursors", response_model=Page[SyncCursorRead])
async def list_cursors(
    account_id: int | None = Query(default=None),
    domain: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[SyncCursorRead]:
    account_id = await _resolve_read_account(
        session, current_user, account_id=account_id
    )
    orchestrator = SyncOrchestrator(session)
    page = await orchestrator.list_cursors(
        account_id=account_id, domain=domain, limit=limit, offset=offset
    )
    page.items = [_cursor_read(row) for row in page.items]
    return page


@router.post("/sync/cursors/{cursor_id}/reset", response_model=SyncCursorRead)
async def reset_cursor(
    cursor_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SyncCursorRead:
    cursor_row = await session.get(WBSyncCursor, cursor_id)
    if cursor_row is not None:
        await resolve_user_account(
            session,
            current_user,
            account_id=cursor_row.account_id,
            require_account=True,
        )
        await require_account_role(
            session,
            current_user,
            account_id=cursor_row.account_id,
            allowed_roles=ADMIN_ROLES,
        )
    orchestrator = SyncOrchestrator(session)
    cursor = await orchestrator.reset_cursor(cursor_id=cursor_id)
    await session.commit()
    return _cursor_read(cursor)


@router.post("/sync/cursors/{cursor_id}/run-now", response_model=SyncRunRead)
async def run_cursor_now(
    cursor_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> SyncRunRead:
    cursor_row = await session.get(WBSyncCursor, cursor_id)
    if cursor_row is not None:
        await resolve_user_account(
            session,
            current_user,
            account_id=cursor_row.account_id,
            require_account=True,
        )
        await require_account_role(
            session,
            current_user,
            account_id=cursor_row.account_id,
            allowed_roles=MANAGER_ROLES,
        )
    orchestrator = SyncOrchestrator(session)
    run = await orchestrator.run_cursor_now(cursor_id=cursor_id)
    await _invalidate_account_snapshots(session, account_id=run.account_id)
    settings = get_settings()
    rollout_ids = set(settings.dynamic_problem_engine_test_account_ids or [])
    if settings.dynamic_problem_engine_enabled and (
        not rollout_ids or int(run.account_id) in {int(item) for item in rollout_ids}
    ):
        await problem_evaluation_runner.evaluate_after_sync(session, sync_run=run)
    await session.commit()
    return run
