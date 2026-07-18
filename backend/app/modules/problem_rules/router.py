from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.schemas.problem_engine import (
    AdminProblemEvaluationRequest,
    AdminProblemDefinitionCreate,
    AdminProblemDefinitionUpdate,
    AdminProblemRuleVersionCreate,
    AdminProblemRuleVersionUpdate,
    AdminRuleBacktestRequest,
    AdminRuleBacktestHistoryPage,
    AdminRuleBacktestResponse,
    AdminRulePublishRequest,
    AdminRuleValidationRequest,
    AdminRuleValidationResponse,
    MetricCatalogRead,
    ProblemEvaluationRunLogRead,
    ProblemDefinitionRead,
    ProblemDefinitionWithVersionsRead,
    ProblemRuleActionCatalogResponse,
    ProblemRuleInstancesPage,
    ProblemRuleSummaryResponse,
    ProblemRuleAdminAuditPage,
    ProblemRuleVersionCompareResponse,
    ProblemRuleVersionRead,
)
from app.services.auth import get_current_user
from app.services.problem_engine.admin_rules import ProblemRuleAdminService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService


router = APIRouter(prefix="/admin/problem-rules", tags=["admin-problem-rules"])
service = ProblemRuleAdminService()
evaluation_runner = ProblemEvaluationRunnerService()


def _is_admin_or_superuser(user: AuthUser) -> bool:
    if bool(getattr(user, "is_superuser", False)):
        return True
    role = str(getattr(user, "role", "") or "").lower()
    if role == "admin":
        return True
    roles = getattr(user, "roles", None)
    if isinstance(roles, (list, tuple, set)):
        return bool(
            {"admin", "superuser"}.intersection({str(item).lower() for item in roles})
        )
    permissions = getattr(user, "permissions", None)
    if isinstance(permissions, (list, tuple, set)):
        return "admin:problem_rules" in {str(item).lower() for item in permissions}
    return False


async def require_problem_rules_admin(
    current_user: AuthUser = Depends(get_current_user),
) -> AuthUser:
    if not _is_admin_or_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin or superuser role required",
        )
    return current_user


@router.get("/metrics", response_model=list[MetricCatalogRead])
async def list_metric_catalog(
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[MetricCatalogRead]:
    return await service.list_metrics(session)  # type: ignore[return-value]


@router.get("/actions/catalog", response_model=ProblemRuleActionCatalogResponse)
async def list_problem_rule_action_catalog(
    _: AuthUser = Depends(require_problem_rules_admin),
) -> ProblemRuleActionCatalogResponse:
    return await service.action_catalog()


@router.post("/evaluate", response_model=ProblemEvaluationRunLogRead)
async def evaluate_problem_rules(
    payload: AdminProblemEvaluationRequest,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemEvaluationRunLogRead:
    settings = get_settings()
    rollout_ids = set(settings.dynamic_problem_engine_test_account_ids or [])
    if not settings.dynamic_problem_engine_enabled:
        raise HTTPException(
            status_code=409, detail="dynamic_problem_engine_enabled is false"
        )
    if rollout_ids and int(payload.account_id) not in {
        int(item) for item in rollout_ids
    }:
        raise HTTPException(
            status_code=409, detail="account is outside dynamic problem engine rollout"
        )
    if payload.nm_ids:
        run_log = await evaluation_runner.evaluate_products(
            session,
            account_id=payload.account_id,
            nm_ids=payload.nm_ids,
            date_from=payload.date_from,
            date_to=payload.date_to,
            trigger="admin_manual",
            actor_user_id=current_user.id,
        )
    else:
        run_log = await evaluation_runner.evaluate_account(
            session,
            account_id=payload.account_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            trigger="admin_manual",
            actor_user_id=current_user.id,
        )
    await session.commit()
    await session.refresh(run_log)
    return run_log  # type: ignore[return-value]


@router.get("/summary", response_model=ProblemRuleSummaryResponse)
async def get_problem_rules_summary(
    recent_days: int = Query(default=30, ge=1, le=365),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleSummaryResponse:
    return await service.summary(session, recent_days=recent_days)


@router.get("/{id}/backtests", response_model=AdminRuleBacktestHistoryPage)
async def list_problem_rule_backtests(
    id: int,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminRuleBacktestHistoryPage:
    return await service.list_backtests(
        session,
        definition_id=id,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/versions/{version_id}/backtests", response_model=AdminRuleBacktestHistoryPage
)
async def list_problem_rule_version_backtests(
    version_id: int,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminRuleBacktestHistoryPage:
    return await service.list_backtests_for_version(
        session,
        version_id=version_id,
        account_id=account_id,
        limit=limit,
        offset=offset,
    )


@router.get("/{id}/instances", response_model=ProblemRuleInstancesPage)
async def list_problem_rule_instances(
    id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    problem_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleInstancesPage:
    return await service.list_instances(
        session,
        definition_id=id,
        status_filter=status_filter,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        problem_code=problem_code,
        limit=limit,
        offset=offset,
    )


@router.get("/definitions", response_model=list[ProblemDefinitionRead])
async def list_problem_definitions(
    status_filter: str | None = Query(default=None, alias="status"),
    category: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> list[ProblemDefinitionRead]:
    return await service.list_definitions(
        session,
        status_filter=status_filter,
        category=category,
        entity_type=entity_type,
    )  # type: ignore[return-value]


@router.post(
    "/definitions",
    response_model=ProblemDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_problem_definition(
    payload: AdminProblemDefinitionCreate,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemDefinitionRead:
    definition = await service.create_definition(
        session, payload, actor_user_id=current_user.id
    )
    await session.commit()
    await session.refresh(definition)
    return definition  # type: ignore[return-value]


@router.get(
    "/definitions/{definition_id}", response_model=ProblemDefinitionWithVersionsRead
)
async def get_problem_definition(
    definition_id: int,
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemDefinitionWithVersionsRead:
    return await service.get_definition(session, definition_id)


@router.get(
    "/definitions/{definition_id}/instances", response_model=ProblemRuleInstancesPage
)
async def list_problem_definition_instances(
    definition_id: int,
    status_filter: str | None = Query(default=None, alias="status"),
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    problem_code: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleInstancesPage:
    return await service.list_instances(
        session,
        definition_id=definition_id,
        status_filter=status_filter,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        problem_code=problem_code,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/definitions/{definition_id}/versions/compare",
    response_model=ProblemRuleVersionCompareResponse,
)
async def compare_problem_rule_versions(
    definition_id: int,
    left: int | None = Query(default=None),
    right: int | None = Query(default=None),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleVersionCompareResponse:
    return await service.compare_versions_capability(
        session,
        definition_id=definition_id,
        left=left,
        right=right,
    )


@router.patch("/definitions/{definition_id}", response_model=ProblemDefinitionRead)
async def update_problem_definition(
    definition_id: int,
    payload: AdminProblemDefinitionUpdate,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemDefinitionRead:
    definition = await service.update_definition(
        session, definition_id, payload, actor_user_id=current_user.id
    )
    await session.commit()
    await session.refresh(definition)
    return definition  # type: ignore[return-value]


@router.post(
    "/definitions/{definition_id}/versions",
    response_model=ProblemRuleVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_problem_rule_version(
    definition_id: int,
    payload: AdminProblemRuleVersionCreate,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleVersionRead:
    rule = await service.create_version(
        session, definition_id, payload, actor_user_id=current_user.id
    )
    await session.commit()
    await session.refresh(rule)
    return rule  # type: ignore[return-value]


@router.patch("/versions/{version_id}", response_model=ProblemRuleVersionRead)
async def update_problem_rule_version(
    version_id: int,
    payload: AdminProblemRuleVersionUpdate,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleVersionRead:
    rule = await service.update_version(
        session, version_id, payload, actor_user_id=current_user.id
    )
    await session.commit()
    await session.refresh(rule)
    return rule  # type: ignore[return-value]


@router.post(
    "/versions/{version_id}/validate", response_model=AdminRuleValidationResponse
)
async def validate_problem_rule_version(
    version_id: int,
    payload: AdminRuleValidationRequest | None = Body(default=None),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminRuleValidationResponse:
    return await service.validate_version(session, version_id, payload)


@router.post(
    "/versions/{version_id}/backtest", response_model=AdminRuleBacktestResponse
)
async def backtest_problem_rule_version(
    version_id: int,
    payload: AdminRuleBacktestRequest,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> AdminRuleBacktestResponse:
    result = await service.backtest(
        session, version_id, payload, actor_user_id=current_user.id
    )
    await session.commit()
    return result


@router.post("/versions/{version_id}/publish", response_model=ProblemRuleVersionRead)
async def publish_problem_rule_version(
    version_id: int,
    payload: AdminRulePublishRequest | None = Body(default=None),
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleVersionRead:
    rule = await service.publish(
        session,
        version_id,
        payload or AdminRulePublishRequest(),
        actor_user_id=current_user.id,
    )
    await session.commit()
    await session.refresh(rule)
    return rule  # type: ignore[return-value]


@router.post("/versions/{version_id}/pause", response_model=ProblemRuleVersionRead)
async def pause_problem_rule_version(
    version_id: int,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleVersionRead:
    rule = await service.pause(session, version_id, actor_user_id=current_user.id)
    await session.commit()
    await session.refresh(rule)
    return rule  # type: ignore[return-value]


@router.post("/versions/{version_id}/archive", response_model=ProblemRuleVersionRead)
async def archive_problem_rule_version(
    version_id: int,
    current_user: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleVersionRead:
    rule = await service.archive(session, version_id, actor_user_id=current_user.id)
    await session.commit()
    await session.refresh(rule)
    return rule  # type: ignore[return-value]


@router.get("/audit", response_model=ProblemRuleAdminAuditPage)
async def list_problem_rule_admin_audit(
    object_type: str | None = Query(default=None),
    object_id: int | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(require_problem_rules_admin),
    session: AsyncSession = Depends(get_db_session),
) -> ProblemRuleAdminAuditPage:
    return await service.list_audit(
        session,
        object_type=object_type,
        object_id=object_id,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
