from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.schemas.agent import (
    AgentMessageRequest,
    AgentMessageResponse,
    AgentToolCallRequest,
    AgentToolsResponse,
)
from app.services.agent import AgentService
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
    resolve_user_account_role,
)

router = APIRouter(tags=["agent"])
service = AgentService()

READ_ROLES = {"viewer", "operator", "manager", "admin"}
OPERATOR_ROLES = {"operator", "manager", "admin"}


@router.post("/portal/agent/message", response_model=AgentMessageResponse)
async def portal_agent_message(
    payload: AgentMessageRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentMessageResponse:
    account = await resolve_user_account(
        session,
        current_user,
        account_id=payload.account_id,
        require_account=True,
    )
    if account is None:
        raise HTTPException(status_code=400, detail="account_id is required")
    await require_account_role(
        session, current_user, account_id=account.id, allowed_roles=READ_ROLES
    )
    role = await resolve_user_account_role(session, current_user, account_id=account.id)
    return await service.handle(
        session,
        account_id=int(account.id),
        role=role,
        user=current_user,
        payload=payload.model_copy(update={"account_id": int(account.id)}),
    )


@router.get("/portal/agent/tools", response_model=AgentToolsResponse)
async def portal_agent_tools(
    account_id: int | None = None,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentToolsResponse:
    account = await resolve_user_account(
        session,
        current_user,
        account_id=account_id,
        require_account=True,
    )
    if account is None:
        raise HTTPException(status_code=400, detail="account_id is required")
    await require_account_role(
        session, current_user, account_id=account.id, allowed_roles=READ_ROLES
    )
    return service.list_tools()


@router.post("/portal/agent/tool-call", response_model=AgentMessageResponse)
async def portal_agent_tool_call(
    payload: AgentToolCallRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentMessageResponse:
    account = await resolve_user_account(
        session,
        current_user,
        account_id=payload.account_id,
        require_account=True,
    )
    if account is None:
        raise HTTPException(status_code=400, detail="account_id is required")
    await require_account_role(
        session, current_user, account_id=account.id, allowed_roles=READ_ROLES
    )
    role = await resolve_user_account_role(session, current_user, account_id=account.id)
    return await service.execute_tool(
        session,
        account_id=int(account.id),
        role=role,
        user=current_user,
        payload=payload.model_copy(update={"account_id": int(account.id)}),
    )


@router.post("/portal/agent/manual-task")
async def portal_agent_manual_task(
    payload: dict,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    account_id = payload.get("account_id")
    account = await resolve_user_account(
        session, current_user, account_id=account_id, require_account=True
    )
    if account is None:
        raise HTTPException(status_code=400, detail="account_id is required")
    await require_account_role(
        session, current_user, account_id=account.id, allowed_roles=OPERATOR_ROLES
    )
    scoped_payload = {**payload, "account_id": int(account.id)}
    action = await service.create_manual_task(
        session, payload=scoped_payload, user_id=int(current_user.id)
    )
    await session.commit()
    return action
