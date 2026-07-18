from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionLocal, get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.models.manual_costs import ManualCost, ManualCostUpload
from app.schemas.manual_costs import (
    CostUploadResponse,
    ManualCostInlineSaveRequest,
    ManualCostInlineSaveResponse,
    MissingCostsResponse,
    ManualCostConfirmResponse,
    ManualCostRead,
    ManualCostRelinkResponse,
    ManualCostSupplierConfirmRequest,
    ManualCostUpdateRequest,
    ManualCostUploadRead,
)
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
)
from app.services.data_quality import DataQualityService
from app.services.manual_costs import ManualCostService
from app.services.marts import MartService
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.operator_snapshots import OperatorEndpointSnapshotService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService

router = APIRouter(tags=["manual-costs"])
service = ManualCostService()
mart_service = MartService()
data_quality_service = DataQualityService()
money_snapshot_service = MoneyEndpointSnapshotService()
operator_snapshot_service = OperatorEndpointSnapshotService()

READ_ROLES = {"viewer", "operator", "manager", "admin"}
MANAGER_ROLES = {"manager", "admin"}
logger = logging.getLogger(__name__)


async def _require_account_access(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int,
    allowed_roles: set[str],
) -> None:
    await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )
    await require_account_role(
        session, user, account_id=account_id, allowed_roles=allowed_roles
    )


async def _invalidate_account_snapshots(
    session: AsyncSession, *, account_id: int
) -> None:
    service.clear_runtime_caches()
    await money_snapshot_service.invalidate_snapshots(session, account_id=account_id)
    await operator_snapshot_service.invalidate_snapshots(session, account_id=account_id)


async def _refresh_dq_and_snapshots(session: AsyncSession, *, account_id: int) -> None:
    await mart_service.refresh_account(session, account_id=account_id)
    await data_quality_service.run_checks(session, account_id=account_id)
    await _invalidate_account_snapshots(session, account_id=account_id)


def _nm_ids_from_rows(rows: list[Any]) -> list[int]:
    values: set[int] = set()
    for row in rows:
        raw = row.get("nm_id") if isinstance(row, dict) else getattr(row, "nm_id", None)
        try:
            nm_id = int(raw)
        except (TypeError, ValueError):
            continue
        if nm_id > 0:
            values.add(nm_id)
    return sorted(values)


def _nm_ids_from_upload(upload: ManualCostUpload) -> list[int]:
    summary = dict(upload.summary or {})
    return _nm_ids_from_rows(list(summary.get("validRows") or []))


async def _evaluate_dynamic_problems_for_cost_change(
    account_id: int, nm_ids: list[int] | None = None
) -> None:
    settings = get_settings()
    rollout_ids = set(settings.dynamic_problem_engine_test_account_ids or [])
    if not settings.dynamic_problem_engine_enabled or (
        rollout_ids and int(account_id) not in {int(item) for item in rollout_ids}
    ):
        return
    async with SessionLocal() as session:
        try:
            await ProblemEvaluationRunnerService().evaluate_after_manual_cost_import(
                session,
                account_id=account_id,
                nm_ids=nm_ids or [],
            )
            await session.commit()
        except Exception:
            await session.rollback()
            logger.exception(
                "Dynamic problem evaluation after manual cost change failed",
                extra={"account_id": account_id},
            )


@router.post("/costs/upload", response_model=CostUploadResponse)
async def upload_costs(
    background_tasks: BackgroundTasks,
    account_id: int = Form(...),
    commit_rows: bool = Form(True),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CostUploadResponse:
    await _require_account_access(
        session, current_user, account_id=account_id, allowed_roles=MANAGER_ROLES
    )
    upload, preview = await service.import_costs(
        session,
        account_id=account_id,
        created_by_user_id=current_user.id,
        file=file,
        commit_rows=commit_rows,
    )
    if commit_rows:
        await _refresh_dq_and_snapshots(session, account_id=account_id)
    await session.commit()
    await session.refresh(upload)
    if commit_rows:
        background_tasks.add_task(
            _evaluate_dynamic_problems_for_cost_change,
            account_id,
            _nm_ids_from_upload(upload),
        )
    return CostUploadResponse(upload=upload, preview_rows=preview)


@router.get("/costs/imports", response_model=Page[ManualCostUploadRead])
async def list_cost_uploads(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[ManualCostUploadRead]:
    account = await resolve_user_account(
        session,
        current_user,
        account_id=account_id,
        require_account=not current_user.is_superuser,
    )
    if account is not None:
        await require_account_role(
            session, current_user, account_id=account.id, allowed_roles=READ_ROLES
        )
    items = await service.list_uploads(
        session, account_id=account.id if account is not None else None
    )
    total = len(items)
    return Page(
        total=total, limit=limit, offset=offset, items=items[offset : offset + limit]
    )


@router.get("/costs/rows", response_model=Page[ManualCostRead])
async def list_cost_rows(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await resolve_user_account(
        session,
        current_user,
        account_id=account_id,
        require_account=not current_user.is_superuser,
    )
    if account is not None:
        await require_account_role(
            session, current_user, account_id=account.id, allowed_roles=READ_ROLES
        )
    return await service.list_costs(
        session,
        account_id=account.id if account is not None else None,
        limit=limit,
        offset=offset,
    )


@router.get("/costs/template")
async def download_cost_template(
    account_id: int = Query(...),
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    mode: str = Query(default="all", pattern="^(all|missing)$"),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _require_account_access(
        session, current_user, account_id=account_id, allowed_roles=READ_ROLES
    )
    today = date.today().isoformat()
    filename = f"manual_cost_template_account_{account_id}_{mode}_{today}.{format}"
    if format == "xlsx":
        content = await service.build_template_xlsx(
            session,
            account_id=account_id,
            mode=mode,
            date_from=date_from,
            date_to=date_to,
        )
        return Response(
            content=content,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    csv_text = await service.build_template_csv(
        session,
        account_id=account_id,
        mode=mode,
        date_from=date_from,
        date_to=date_to,
    )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/costs/missing", response_model=MissingCostsResponse)
async def missing_manual_costs(
    account_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    only_revenue: bool = Query(default=True),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MissingCostsResponse:
    await _require_account_access(
        session, current_user, account_id=account_id, allowed_roles=READ_ROLES
    )
    payload = await service.list_missing_costs(
        session,
        account_id=account_id,
        limit=limit,
        offset=offset,
        date_from=date_from,
        date_to=date_to,
        only_revenue=only_revenue,
    )
    return MissingCostsResponse(**payload)


@router.get("/costs/uploads/{upload_id}/preview", response_model=CostUploadResponse)
async def preview_cost_upload(
    upload_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CostUploadResponse:
    upload_row = await session.get(ManualCostUpload, upload_id)
    if upload_row is None:
        upload, preview = await service.get_upload_preview(session, upload_id=upload_id)
        return CostUploadResponse(upload=upload, preview_rows=preview)
    await _require_account_access(
        session,
        current_user,
        account_id=upload_row.account_id,
        allowed_roles=READ_ROLES,
    )
    upload, preview = await service.get_upload_preview(session, upload_id=upload_id)
    return CostUploadResponse(upload=upload, preview_rows=preview)


@router.post(
    "/costs/uploads/{upload_id}/confirm", response_model=ManualCostConfirmResponse
)
async def confirm_cost_upload(
    upload_id: int,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ManualCostConfirmResponse:
    upload_row = await session.get(ManualCostUpload, upload_id)
    if upload_row is None:
        await service.get_upload_preview(session, upload_id=upload_id)
    else:
        await _require_account_access(
            session,
            current_user,
            account_id=upload_row.account_id,
            allowed_roles=MANAGER_ROLES,
        )
    upload, rows_committed = await service.confirm_upload(
        session,
        upload_id=upload_id,
        user_id=current_user.id,
    )
    await _refresh_dq_and_snapshots(session, account_id=upload.account_id)
    await session.commit()
    await session.refresh(upload)
    if rows_committed > 0:
        background_tasks.add_task(
            _evaluate_dynamic_problems_for_cost_change,
            upload.account_id,
            _nm_ids_from_upload(upload),
        )
    return ManualCostConfirmResponse(
        upload=upload,
        rows_committed=rows_committed,
        next_step={
            "label": "Пересчитать качество данных",
            "endpoint": "POST /api/v1/dq/run",
        },
    )


@router.post("/costs/inline-save", response_model=ManualCostInlineSaveResponse)
async def save_inline_costs(
    payload: ManualCostInlineSaveRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ManualCostInlineSaveResponse:
    await _require_account_access(
        session,
        current_user,
        account_id=payload.account_id,
        allowed_roles=MANAGER_ROLES,
    )
    rows = await service.save_inline_costs(
        session,
        account_id=payload.account_id,
        rows=payload.rows,
        user_id=current_user.id,
    )
    await _refresh_dq_and_snapshots(session, account_id=payload.account_id)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    background_tasks.add_task(
        _evaluate_dynamic_problems_for_cost_change,
        payload.account_id,
        _nm_ids_from_rows(rows),
    )
    return ManualCostInlineSaveResponse(
        rows=rows, changed_count=len(rows), recalculated=True
    )


@router.patch("/costs/{cost_id}", response_model=ManualCostRead)
async def update_cost_row(
    cost_id: int,
    payload: ManualCostUpdateRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ManualCostRead:
    cost = await session.get(ManualCost, cost_id)
    if cost is None:
        row = await service.update_cost(
            session, cost_id=cost_id, payload=payload, user_id=current_user.id
        )
        return row
    await _require_account_access(
        session, current_user, account_id=cost.account_id, allowed_roles=MANAGER_ROLES
    )
    row = await service.update_cost(
        session, cost_id=cost_id, payload=payload, user_id=current_user.id
    )
    await _refresh_dq_and_snapshots(session, account_id=row.account_id)
    await session.commit()
    await session.refresh(row)
    background_tasks.add_task(
        _evaluate_dynamic_problems_for_cost_change,
        row.account_id,
        _nm_ids_from_rows([row]),
    )
    return row


@router.post("/costs/{cost_id}/mark-supplier-confirmed", response_model=ManualCostRead)
async def mark_cost_supplier_confirmed(
    cost_id: int,
    background_tasks: BackgroundTasks,
    payload: ManualCostSupplierConfirmRequest | None = None,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ManualCostRead:
    cost = await session.get(ManualCost, cost_id)
    if cost is not None:
        await _require_account_access(
            session,
            current_user,
            account_id=cost.account_id,
            allowed_roles=MANAGER_ROLES,
        )
    row = await service.mark_supplier_confirmed(
        session,
        cost_id=cost_id,
        user_id=current_user.id,
        comment=(payload.comment if payload is not None else None),
    )
    await _refresh_dq_and_snapshots(session, account_id=row.account_id)
    await session.commit()
    await session.refresh(row)
    background_tasks.add_task(
        _evaluate_dynamic_problems_for_cost_change,
        row.account_id,
        _nm_ids_from_rows([row]),
    )
    return row


@router.post("/costs/relink", response_model=ManualCostRelinkResponse)
async def relink_manual_costs(
    background_tasks: BackgroundTasks,
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ManualCostRelinkResponse:
    await _require_account_access(
        session, current_user, account_id=account_id, allowed_roles=MANAGER_ROLES
    )
    result = await service.relink_costs(session, account_id=account_id)
    await _refresh_dq_and_snapshots(session, account_id=account_id)
    await session.commit()
    background_tasks.add_task(
        _evaluate_dynamic_problems_for_cost_change, account_id, []
    )
    return ManualCostRelinkResponse(**result)


@router.get(
    "/costs/unresolved",
    response_model=Page[ManualCostRead],
    description="Unresolved uploaded cost rows that are not linked or are ambiguous; not products/SKUs missing себестоимость.",
)
async def unresolved_manual_costs(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[ManualCostRead]:
    account = await resolve_user_account(
        session,
        current_user,
        account_id=account_id,
        require_account=not current_user.is_superuser,
    )
    if account is not None:
        await require_account_role(
            session, current_user, account_id=account.id, allowed_roles=READ_ROLES
        )
    return await service.list_unresolved_costs_page(
        session,
        account_id=account.id if account is not None else None,
        limit=limit,
        offset=offset,
    )
