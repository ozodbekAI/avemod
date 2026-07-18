from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.schemas.stock_control import (
    HandStockDraftCreate,
    HandStockDraftRead,
    HandStockDraftUpdate,
    HandStockDraftsPage,
    StockControlExportRead,
    StockControlImportPreview,
    StockControlImportRead,
    StockControlMovementsPage,
    StockControlOverviewRead,
    StockControlRegionRowsPage,
    StockControlRunCreate,
    StockControlRunRead,
    StockControlRunsPage,
    StockControlSettingsRead,
    StockControlSettingsUpdate,
    StockControlStatusRead,
    StockControlStoreBalancePreviewRequest,
    StockControlTemplateRead,
)
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
)
from app.services.stock_control import StockControlService

router = APIRouter(tags=["stock-control"])
service = StockControlService()

READ_ROLES = {"viewer", "operator", "manager", "admin"}
OPERATOR_ROLES = {"operator", "manager", "admin"}
MANAGER_ROLES = {"manager", "admin"}


async def _account_id(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
    roles: set[str],
) -> int:
    account = await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )
    assert account is not None
    await require_account_role(
        session, user, account_id=account.id, allowed_roles=roles
    )
    return int(account.id)


@router.get("/portal/stock-control/status", response_model=StockControlStatusRead)
async def stock_control_status(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlStatusRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.status(session, account_id=resolved)


@router.get("/portal/stock-control/settings", response_model=StockControlSettingsRead)
async def stock_control_settings(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlSettingsRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.get_settings(session, account_id=resolved)


@router.put("/portal/stock-control/settings", response_model=StockControlSettingsRead)
async def stock_control_update_settings(
    payload: StockControlSettingsUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlSettingsRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=MANAGER_ROLES
    )
    result = await service.update_settings(
        session, account_id=resolved, payload=payload
    )
    await session.commit()
    return result


@router.post(
    "/portal/stock-control/imports/regional-supply/preview",
    response_model=StockControlImportPreview,
)
async def stock_control_preview_regional_supply(
    account_id: int = Query(...),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlImportPreview:
    await _account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    return await service.preview_import(
        file_name=file.filename or "regional_supply.xlsx",
        content=await file.read(),
        import_type="regional_supply",
    )


@router.post(
    "/portal/stock-control/imports/regional-supply",
    response_model=StockControlImportRead,
)
async def stock_control_import_regional_supply(
    account_id: int = Query(...),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlImportRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    result = await service.import_regional_supply(
        session,
        account_id=resolved,
        file_name=file.filename or "regional_supply.xlsx",
        content=await file.read(),
        created_by_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.get(
    "/portal/stock-control/templates/hand-stock",
    response_model=StockControlTemplateRead,
)
async def stock_control_hand_stock_template(
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlTemplateRead:
    await _account_id(session, current_user, account_id=account_id, roles=READ_ROLES)
    return service.hand_stock_template()


@router.post(
    "/portal/stock-control/imports/hand-stock/preview",
    response_model=StockControlImportPreview,
)
async def stock_control_preview_hand_stock(
    account_id: int = Query(...),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlImportPreview:
    await _account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    return await service.preview_import(
        file_name=file.filename or "hand_stock.xlsx",
        content=await file.read(),
        import_type="hand_stock",
    )


@router.post("/portal/stock-control/preview", response_model=dict)
async def stock_control_preview(
    payload: StockControlStoreBalancePreviewRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    source_account_id = payload.source_account_id or payload.account_id
    await _account_id(
        session, current_user, account_id=source_account_id, roles=READ_ROLES
    )
    await _account_id(
        session, current_user, account_id=payload.target_account_id, roles=READ_ROLES
    )
    scoped = payload.model_copy(
        update={"account_id": source_account_id, "source_account_id": source_account_id}
    )
    return await service.preview_store_balance(session, payload=scoped)


@router.get(
    "/portal/stock-control/hand-stock-drafts", response_model=HandStockDraftsPage
)
async def stock_control_hand_stock_drafts(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HandStockDraftsPage:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.list_hand_drafts(
        session, account_id=resolved, limit=limit, offset=offset
    )


@router.post(
    "/portal/stock-control/hand-stock-drafts",
    response_model=HandStockDraftRead,
    status_code=status.HTTP_201_CREATED,
)
async def stock_control_create_hand_stock_draft(
    payload: HandStockDraftCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HandStockDraftRead:
    resolved = await _account_id(
        session, current_user, account_id=payload.account_id, roles=OPERATOR_ROLES
    )
    scoped = payload.model_copy(update={"account_id": resolved})
    result = await service.create_hand_draft(
        session, payload=scoped, created_by_user_id=current_user.id
    )
    await session.commit()
    return result


@router.get(
    "/portal/stock-control/hand-stock-drafts/{draft_id}",
    response_model=HandStockDraftRead,
)
async def stock_control_get_hand_stock_draft(
    draft_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HandStockDraftRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.get_hand_draft(session, account_id=resolved, draft_id=draft_id)


@router.put(
    "/portal/stock-control/hand-stock-drafts/{draft_id}",
    response_model=HandStockDraftRead,
)
async def stock_control_update_hand_stock_draft(
    draft_id: int,
    payload: HandStockDraftUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> HandStockDraftRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    result = await service.update_hand_draft(
        session, account_id=resolved, draft_id=draft_id, payload=payload
    )
    await session.commit()
    return result


@router.delete("/portal/stock-control/hand-stock-drafts/{draft_id}")
async def stock_control_delete_hand_stock_draft(
    draft_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    result = await service.delete_hand_draft(
        session, account_id=resolved, draft_id=draft_id
    )
    await session.commit()
    return result


@router.post(
    "/portal/stock-control/runs",
    response_model=StockControlRunRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def stock_control_create_run(
    payload: StockControlRunCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRunRead:
    resolved = await _account_id(
        session, current_user, account_id=payload.account_id, roles=OPERATOR_ROLES
    )
    if payload.run_type == "store_balance" and payload.target_account_id is not None:
        await _account_id(
            session,
            current_user,
            account_id=payload.target_account_id,
            roles=OPERATOR_ROLES,
        )
    result = await service.create_run(
        session,
        payload=payload.model_copy(update={"account_id": resolved}),
        requested_by_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.get("/portal/stock-control/runs", response_model=StockControlRunsPage)
async def stock_control_runs(
    account_id: int | None = Query(default=None),
    run_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRunsPage:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.list_runs(
        session, account_id=resolved, run_type=run_type, limit=limit, offset=offset
    )


@router.get("/portal/stock-control/runs/{run_id}", response_model=StockControlRunRead)
async def stock_control_run_detail(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRunRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.get_run(session, account_id=resolved, run_id=run_id)


@router.post(
    "/portal/stock-control/runs/{run_id}/retry", response_model=StockControlRunRead
)
async def stock_control_retry_run(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRunRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=MANAGER_ROLES
    )
    result = await service.retry_run(session, account_id=resolved, run_id=run_id)
    await session.commit()
    return result


@router.post(
    "/portal/stock-control/runs/{run_id}/cancel", response_model=StockControlRunRead
)
async def stock_control_cancel_run(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRunRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=MANAGER_ROLES
    )
    result = await service.cancel_run(session, account_id=resolved, run_id=run_id)
    await session.commit()
    return result


@router.get(
    "/portal/stock-control/runs/{run_id}/overview",
    response_model=StockControlOverviewRead,
)
async def stock_control_run_overview(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlOverviewRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.overview(session, account_id=resolved, run_id=run_id)


@router.get(
    "/portal/stock-control/runs/{run_id}/region-rows",
    response_model=StockControlRegionRowsPage,
)
async def stock_control_region_rows(
    run_id: int,
    account_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRegionRowsPage:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.region_rows(
        session,
        account_id=resolved,
        run_id=run_id,
        status=status,
        nm_id=nm_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/portal/stock-control/runs/{run_id}/movements",
    response_model=StockControlMovementsPage,
)
async def stock_control_movements(
    run_id: int,
    account_id: int | None = Query(default=None),
    movement_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlMovementsPage:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.movements(
        session,
        account_id=resolved,
        run_id=run_id,
        movement_type=movement_type,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/portal/stock-control/runs/{run_id}/unmatched",
    response_model=StockControlRegionRowsPage,
)
async def stock_control_unmatched(
    run_id: int,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlRegionRowsPage:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.unmatched(
        session, account_id=resolved, run_id=run_id, limit=limit, offset=offset
    )


@router.get(
    "/portal/stock-control/runs/{run_id}/export", response_model=StockControlExportRead
)
async def stock_control_export(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StockControlExportRead:
    resolved = await _account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await service.export(session, account_id=resolved, run_id=run_id)
