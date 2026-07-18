from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.schemas.ab_tests import ABTestCreateRequest, ABTestUpdateRequest
from app.services.ab_tests import ABTestService
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
)

router = APIRouter(prefix="/ab-tests", tags=["ab-tests"])
promotion_router = APIRouter(prefix="/promotion", tags=["promotion"])
service = ABTestService()

MUTATION_ROLES = {"operator", "manager", "admin"}


async def _require_read_account(session: AsyncSession, user: AuthUser, account_id: int):
    return await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )


async def _require_write_account(
    session: AsyncSession, user: AuthUser, account_id: int
):
    account = await _require_read_account(session, user, account_id)
    await require_account_role(
        session, user, account_id=int(account.id), allowed_roles=MUTATION_ROLES
    )
    return account


@router.get("/balance")
async def ab_test_balance(
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    return await service.balance(session, account_id=int(account.id))


@router.post("/create-company")
async def ab_test_create_company(
    payload: ABTestCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, payload.account_id)
    result = await service.create_company(
        session,
        account_id=int(account.id),
        user_id=int(current_user.id),
        payload=payload.model_dump(),
    )
    await session.commit()
    return result


@router.post("/update")
async def ab_test_update(
    payload: ABTestUpdateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, payload.account_id)
    result = await service.update_company_and_start(
        session,
        account_id=int(account.id),
        payload=payload.model_dump(),
    )
    await session.commit()
    return result


@router.get("/company/{company_id}/stats")
async def ab_test_company_stats(
    company_id: int,
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    return await service.company_stats(
        session, account_id=int(account.id), company_id=company_id
    )


@router.post("/company/{company_id}/start")
async def ab_test_start_company(
    company_id: int,
    account_id: int = Query(...),
    confirm: bool = Query(default=False),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, account_id)
    result = await service.start_company(
        session, account_id=int(account.id), company_id=company_id, confirm=confirm
    )
    await session.commit()
    return result


@router.post("/company/{company_id}/stop")
async def ab_test_stop_company(
    company_id: int,
    account_id: int = Query(...),
    confirm: bool = Query(default=False),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, account_id)
    result = await service.stop_company_confirmed(
        session, account_id=int(account.id), company_id=company_id, confirm=confirm
    )
    await session.commit()
    return result


@router.get("/{status}")
async def ab_test_list(
    status: str,
    account_id: int = Query(...),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    return await service.list_companies(
        session,
        account_id=int(account.id),
        status=status,
        limit=limit,
        offset=offset,
    )


@promotion_router.get("/balance")
async def promotion_balance(
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    return await service.balance(session, account_id=int(account.id))


@promotion_router.post("/create_company")
async def promotion_create_company(
    payload: ABTestCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, payload.account_id)
    result = await service.create_company(
        session,
        account_id=int(account.id),
        user_id=int(current_user.id),
        payload=payload.model_dump(),
    )
    await session.commit()
    return result


@promotion_router.post("/update")
async def promotion_update(
    payload: ABTestUpdateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, payload.account_id)
    result = await service.update_company_and_start(
        session,
        account_id=int(account.id),
        payload=payload.model_dump(),
    )
    await session.commit()
    return result


@promotion_router.get("/company/{company_id}/stats")
async def promotion_company_stats(
    company_id: int,
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    return await service.company_stats(
        session, account_id=int(account.id), company_id=company_id
    )


@promotion_router.get("/company/{company_id}/debug")
async def promotion_company_debug(
    company_id: int,
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    stats = await service.company_stats(
        session, account_id=int(account.id), company_id=company_id
    )
    return {"company": stats, "source": "finance-ab-tests"}


@promotion_router.post("/company/{company_id}/start")
async def promotion_start_company(
    company_id: int,
    account_id: int = Query(...),
    confirm: bool = Query(default=False),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, account_id)
    result = await service.start_company(
        session, account_id=int(account.id), company_id=company_id, confirm=confirm
    )
    await session.commit()
    return result


@promotion_router.post("/company/{company_id}/stop")
async def promotion_stop_company(
    company_id: int,
    account_id: int = Query(...),
    confirm: bool = Query(default=False),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_write_account(session, current_user, account_id)
    result = await service.stop_company_confirmed(
        session, account_id=int(account.id), company_id=company_id, confirm=confirm
    )
    await session.commit()
    return result


@promotion_router.get("/{status}")
async def promotion_list(
    status: str,
    account_id: int = Query(...),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account = await _require_read_account(session, current_user, account_id)
    return await service.list_companies(
        session,
        account_id=int(account.id),
        status=status,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
