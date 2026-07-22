from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.schemas.agent import (
    AgentFinanceSummary,
    AgentMCPRequest,
    AgentMCPResponse,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentScenarioCreate,
    AgentScenarioListResponse,
    AgentScenarioRead,
    AgentScenarioRunCreate,
    AgentScenarioRunListResponse,
    AgentScenarioRunRead,
    AgentScenarioTemplatesResponse,
    AgentScenarioUpdate,
    AgentToolCallRequest,
    AgentToolsResponse,
)
from app.services.agent import AgentMCPService, AgentScenarioService, AgentService
from app.services.auth import (
    get_current_user,
    require_account_role,
    resolve_user_account,
    resolve_user_account_role,
)

router = APIRouter(tags=["agent"])
service = AgentService()
scenario_service = AgentScenarioService()
mcp_service = AgentMCPService(service)

READ_ROLES = {"viewer", "operator", "manager", "admin"}
OPERATOR_ROLES = {"operator", "manager", "admin"}


async def _resolve_account_id(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
    roles: set[str],
) -> int:
    account = await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )
    if account is None:
        raise HTTPException(status_code=400, detail="account_id is required")
    await require_account_role(session, user, account_id=account.id, allowed_roles=roles)
    return int(account.id)


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
    response = await service.handle(
        session,
        account_id=int(account.id),
        role=role,
        user=current_user,
        payload=payload.model_copy(update={"account_id": int(account.id)}),
    )
    await session.commit()
    return response


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


@router.post("/portal/agent/mcp", response_model=AgentMCPResponse)
async def portal_agent_mcp(
    payload: AgentMCPRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentMCPResponse:
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
    role = await resolve_user_account_role(session, current_user, account_id=account.id)
    response = await mcp_service.handle(
        session,
        account_id=int(account.id),
        role=role,
        user=current_user,
        payload=payload,
    )
    await session.commit()
    return response


@router.get(
    "/portal/agent/scenario-templates",
    response_model=AgentScenarioTemplatesResponse,
)
async def portal_agent_scenario_templates(
    current_user: AuthUser = Depends(get_current_user),
) -> AgentScenarioTemplatesResponse:
    _ = current_user
    return scenario_service.templates()


@router.get("/portal/agent/scenarios", response_model=AgentScenarioListResponse)
async def portal_agent_scenarios(
    account_id: int | None = Query(default=None),
    scenario_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentScenarioListResponse:
    resolved = await _resolve_account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await scenario_service.list_scenarios(
        session,
        account_id=resolved,
        status=scenario_status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/portal/agent/scenarios",
    response_model=AgentScenarioRead,
    status_code=status.HTTP_201_CREATED,
)
async def portal_agent_create_scenario(
    payload: AgentScenarioCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentScenarioRead:
    resolved = await _resolve_account_id(
        session, current_user, account_id=payload.account_id, roles=OPERATOR_ROLES
    )
    result = await scenario_service.create_scenario(
        session,
        account_id=resolved,
        payload=payload.model_copy(update={"account_id": resolved}),
        user_id=int(current_user.id),
    )
    await session.commit()
    return result


@router.get("/portal/agent/scenarios/{scenario_id}", response_model=AgentScenarioRead)
async def portal_agent_scenario_detail(
    scenario_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentScenarioRead:
    resolved = await _resolve_account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await scenario_service.get_scenario(
        session, account_id=resolved, scenario_id=scenario_id
    )


@router.patch("/portal/agent/scenarios/{scenario_id}", response_model=AgentScenarioRead)
async def portal_agent_update_scenario(
    scenario_id: int,
    payload: AgentScenarioUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentScenarioRead:
    resolved = await _resolve_account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    result = await scenario_service.update_scenario(
        session,
        account_id=resolved,
        scenario_id=scenario_id,
        payload=payload,
        user_id=int(current_user.id),
    )
    await session.commit()
    return result


@router.post(
    "/portal/agent/scenarios/{scenario_id}/run",
    response_model=AgentScenarioRunRead,
)
async def portal_agent_run_scenario(
    scenario_id: int,
    payload: AgentScenarioRunCreate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentScenarioRunRead:
    resolved = await _resolve_account_id(
        session, current_user, account_id=account_id, roles=OPERATOR_ROLES
    )
    result = await scenario_service.run_scenario(
        session,
        account_id=resolved,
        scenario_id=scenario_id,
        payload=payload,
        user_id=int(current_user.id),
    )
    await session.commit()
    return result


@router.get("/portal/agent/scenario-runs", response_model=AgentScenarioRunListResponse)
async def portal_agent_scenario_runs(
    account_id: int | None = Query(default=None),
    scenario_id: int | None = Query(default=None),
    run_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentScenarioRunListResponse:
    resolved = await _resolve_account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await scenario_service.list_runs(
        session,
        account_id=resolved,
        scenario_id=scenario_id,
        status=run_status,
        limit=limit,
        offset=offset,
    )


@router.get("/portal/agent/finance", response_model=AgentFinanceSummary)
async def portal_agent_finance(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> AgentFinanceSummary:
    resolved = await _resolve_account_id(
        session, current_user, account_id=account_id, roles=READ_ROLES
    )
    return await scenario_service.finance_summary(session, account_id=resolved)


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
    response = await service.execute_tool(
        session,
        account_id=int(account.id),
        role=role,
        user=current_user,
        payload=payload.model_copy(update={"account_id": int(account.id)}),
    )
    await session.commit()
    return response


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
