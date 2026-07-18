from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.data_quality import (
    BulkMutationResponse,
    DataQualityIssueActionRequest,
    DataQualityIssueActionResponse,
    DataQualityIssueBulkRequest,
    DataQualityIssueBulkClassifyRequest,
    DataQualityIssueClassifyRequest,
    DataQualityIssueRecheckResponse,
    DataQualityIssueRead,
    DataQualityIssueSummaryResponse,
    DataQualityIssueSummaryRow,
    DataQualityResolutionContext,
    GuidedFixActionRequest,
    GuidedFixActionResponse,
    DataQualityRunRequest,
    DataQualityRunResponse,
)
from app.services.auth import (
    get_current_superuser,
    get_current_user,
    require_account_role,
    resolve_user_account,
    resolve_user_account_role,
)
from app.services.data_quality import DataQualityService
from app.services.money_snapshots import MoneyEndpointSnapshotService
from app.services.operator_snapshots import OperatorEndpointSnapshotService

router = APIRouter(tags=["data-quality"])
service = DataQualityService()
money_snapshot_service = MoneyEndpointSnapshotService()
snapshot_service = OperatorEndpointSnapshotService()
snapshot_service.data_quality = service

READ_ROLES = {"viewer", "operator", "manager", "admin"}
OPERATOR_ROLES = {"operator", "manager", "admin"}
MANAGER_ROLES = {"manager", "admin"}


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


async def _require_issue_account_role(
    session: AsyncSession,
    user: AuthUser,
    *,
    issue_id: int,
    allowed_roles: set[str],
) -> int | None:
    issue = await service.get_issue(session, issue_id=issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Data quality issue not found")
    if issue.account_id is not None:
        await resolve_user_account(
            session, user, account_id=issue.account_id, require_account=True
        )
        await require_account_role(
            session, user, account_id=issue.account_id, allowed_roles=allowed_roles
        )
        return int(issue.account_id)
    if not user.is_superuser:
        await resolve_user_account(session, user, account_id=None, require_account=True)
    return None


@router.get("/dq/issues", response_model=Page[DataQualityIssueRead])
async def list_data_quality_issues(
    account_id: int | None = Query(default=None),
    only_open: bool = Query(default=False),
    code: list[str] | None = Query(default=None),
    issue_type: list[str] | None = Query(default=None),
    severity: list[str] | None = Query(default=None),
    domain: list[str] | None = Query(default=None),
    source_table: list[str] | None = Query(default=None),
    financial_final_blocker: bool | None = Query(default=None),
    classification_status: list[str] | None = Query(default=None),
    age_bucket: list[str] | None = Query(default=None),
    status: str | None = Query(default=None),
    sku_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[DataQualityIssueRead]:
    account_id = await _resolve_read_account(
        session, current_user, account_id=account_id
    )
    if account_id is None:
        return await service.list_issues(
            session,
            account_id=account_id,
            only_open=only_open,
            codes=code,
            issue_types=issue_type,
            severities=severity,
            domains=domain,
            source_tables=source_table,
            classification_statuses=classification_status,
            age_buckets=age_bucket,
            status=status,
            sku_id=sku_id,
            nm_id=nm_id,
            detected_from=date_from,
            detected_to=date_to,
            financial_final_blocker=financial_final_blocker,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    return await snapshot_service.dq_issues(
        session,
        account_id=account_id,
        only_open=only_open,
        code=code,
        issue_type=issue_type,
        severity=severity,
        domain=domain,
        source_table=source_table,
        financial_final_blocker=financial_final_blocker,
        classification_status=classification_status,
        age_bucket=age_bucket,
        status=status,
        sku_id=sku_id,
        nm_id=nm_id,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/dq/issues/summary", response_model=DataQualityIssueSummaryResponse)
async def data_quality_issue_summary(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityIssueSummaryResponse:
    account_id = await _resolve_read_account(
        session, current_user, account_id=account_id
    )
    if account_id is not None:
        return await snapshot_service.dq_issue_summary(session, account_id=account_id)
    payload = await service.list_issue_summary(session, account_id=account_id)
    return DataQualityIssueSummaryResponse(
        items=[DataQualityIssueSummaryRow(**item) for item in payload["items"]],
        open_issues_total=int(payload["open_issues_total"]),
        all_open_issues_total=int(
            payload.get("all_open_issues_total") or payload["open_issues_total"]
        ),
        blocking_open_issues_total=int(payload.get("blocking_open_issues_total") or 0),
        financial_final_blockers_total=int(payload["financial_final_blockers_total"]),
        by_severity=dict(payload["by_severity"]),
        by_issue_type=dict(payload["by_issue_type"]),
        by_source_table=dict(payload["by_source_table"]),
        by_group=dict(payload["by_group"]),
        by_group_blocking=dict(payload.get("by_group_blocking") or {}),
        by_group_all_open=dict(payload.get("by_group_all_open") or {}),
    )


@router.get(
    "/dq/issues/{issue_id}/resolution-context",
    response_model=DataQualityResolutionContext,
)
async def data_quality_issue_resolution_context(
    issue_id: int,
    affected_rows_limit: int = Query(default=50, ge=1, le=200),
    affected_rows_offset: int = Query(default=0, ge=0),
    include_debug: bool = Query(default=False),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityResolutionContext:
    issue_account_id = await _require_issue_account_role(
        session, current_user, issue_id=issue_id, allowed_roles=READ_ROLES
    )
    include_debug_rows = False
    if include_debug:
        if current_user.is_superuser:
            include_debug_rows = True
        elif issue_account_id is not None:
            role = await resolve_user_account_role(
                session, current_user, account_id=issue_account_id
            )
            include_debug_rows = role == "admin"
    return await service.resolution_context(
        session,
        issue_id=issue_id,
        affected_rows_limit=affected_rows_limit,
        affected_rows_offset=affected_rows_offset,
        include_debug_rows=include_debug_rows,
    )


@router.get("/dq/issues/{issue_id}/affected-rows.csv")
async def export_data_quality_issue_affected_rows(
    issue_id: int,
    limit: int = Query(default=1000, ge=1, le=1000),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    await _require_issue_account_role(
        session, current_user, issue_id=issue_id, allowed_roles=READ_ROLES
    )
    content = await service.affected_rows_csv(session, issue_id=issue_id, limit=limit)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="dq_issue_{issue_id}_affected_rows.csv"'
        },
    )


@router.post(
    "/dq/issues/{issue_id}/guided-action", response_model=GuidedFixActionResponse
)
async def apply_data_quality_guided_action(
    issue_id: int,
    payload: GuidedFixActionRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> GuidedFixActionResponse:
    account_id = await _require_issue_account_role(
        session, current_user, issue_id=issue_id, allowed_roles=MANAGER_ROLES
    )
    result = await service.apply_guided_fix(
        session,
        issue_id=issue_id,
        request=payload,
        user_id=current_user.id,
    )
    await money_snapshot_service.invalidate_snapshots(session, account_id=account_id)
    await snapshot_service.invalidate_snapshots(session, account_id=account_id)
    await session.commit()
    return result


@router.post(
    "/dq/issues/{issue_id}/recheck", response_model=DataQualityIssueRecheckResponse
)
async def recheck_data_quality_issue(
    issue_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityIssueRecheckResponse:
    account_id = await _require_issue_account_role(
        session, current_user, issue_id=issue_id, allowed_roles=OPERATOR_ROLES
    )
    result = await service.recheck_issue(
        session, issue_id=issue_id, user_id=current_user.id
    )
    await money_snapshot_service.invalidate_snapshots(session, account_id=account_id)
    await snapshot_service.invalidate_snapshots(session, account_id=account_id)
    await session.commit()
    return result


@router.get("/dq/issues/investigator", response_model=Page[DataQualityIssueRead])
async def investigator_data_quality_issues(
    account_id: int | None = Query(default=None),
    code: str = Query(...),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[DataQualityIssueRead]:
    account_id = await _resolve_read_account(
        session, current_user, account_id=account_id
    )
    if account_id is None:
        return await service.list_investigator_issues(
            session,
            account_id=account_id,
            code=code,
            limit=limit,
            offset=offset,
        )
    return await snapshot_service.dq_investigator_issues(
        session,
        account_id=account_id,
        code=code,
        limit=limit,
        offset=offset,
    )


@router.post("/dq/run", response_model=DataQualityRunResponse)
async def run_data_quality_checks(
    payload: DataQualityRunRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityRunResponse:
    await resolve_user_account(
        session, current_user, account_id=payload.account_id, require_account=True
    )
    await require_account_role(
        session,
        current_user,
        account_id=payload.account_id,
        allowed_roles=MANAGER_ROLES,
    )
    result = await service.run_checks(session, account_id=payload.account_id)
    await money_snapshot_service.invalidate_snapshots(
        session, account_id=payload.account_id
    )
    await snapshot_service.invalidate_snapshots(session, account_id=payload.account_id)
    await session.commit()
    return DataQualityRunResponse(**result)


@router.post("/dq/issues/bulk", response_model=BulkMutationResponse)
async def bulk_update_data_quality_issues(
    payload: DataQualityIssueBulkRequest,
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> BulkMutationResponse:
    updated_count = await service.bulk_update_issues(
        session,
        ids=payload.ids,
        action=payload.action,
        comment=payload.comment,
        classification_status=payload.classification_status,
        classification_reason=payload.classification_reason,
        financial_final_blocker_override=payload.financial_final_blocker_override,
        mapped_sku_id=payload.mapped_sku_id,
        user_id=current_user.id,
    )
    await money_snapshot_service.invalidate_snapshots(session)
    await snapshot_service.invalidate_snapshots(session)
    await session.commit()
    return BulkMutationResponse(updated_count=updated_count)


@router.post(
    "/dq/issues/{issue_id}/resolve", response_model=DataQualityIssueActionResponse
)
async def resolve_data_quality_issue(
    issue_id: int,
    payload: DataQualityIssueActionRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityIssueActionResponse:
    issue = await service.resolve_issue_by_id(
        session, issue_id=issue_id, comment=payload.comment
    )
    await money_snapshot_service.invalidate_snapshots(
        session, account_id=issue.account_id
    )
    await snapshot_service.invalidate_snapshots(session, account_id=issue.account_id)
    await session.commit()
    await session.refresh(issue)
    return DataQualityIssueActionResponse(issue=DataQualityIssueRead.from_issue(issue))


@router.post(
    "/dq/issues/{issue_id}/reopen", response_model=DataQualityIssueActionResponse
)
async def reopen_data_quality_issue(
    issue_id: int,
    payload: DataQualityIssueActionRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityIssueActionResponse:
    issue = await service.reopen_issue_by_id(
        session, issue_id=issue_id, comment=payload.comment
    )
    await money_snapshot_service.invalidate_snapshots(
        session, account_id=issue.account_id
    )
    await snapshot_service.invalidate_snapshots(session, account_id=issue.account_id)
    await session.commit()
    await session.refresh(issue)
    return DataQualityIssueActionResponse(issue=DataQualityIssueRead.from_issue(issue))


@router.patch(
    "/dq/issues/{issue_id}/comment", response_model=DataQualityIssueActionResponse
)
async def comment_data_quality_issue(
    issue_id: int,
    payload: DataQualityIssueActionRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityIssueActionResponse:
    issue = await service.comment_issue_by_id(
        session, issue_id=issue_id, comment=payload.comment or ""
    )
    await money_snapshot_service.invalidate_snapshots(
        session, account_id=issue.account_id
    )
    await snapshot_service.invalidate_snapshots(session, account_id=issue.account_id)
    await session.commit()
    await session.refresh(issue)
    return DataQualityIssueActionResponse(issue=DataQualityIssueRead.from_issue(issue))


@router.patch(
    "/dq/issues/{issue_id}/classify", response_model=DataQualityIssueActionResponse
)
async def classify_data_quality_issue(
    issue_id: int,
    payload: DataQualityIssueClassifyRequest,
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> DataQualityIssueActionResponse:
    issue = await service.classify_issue_by_id(
        session,
        issue_id=issue_id,
        classification_status=payload.classification_status,
        classification_reason=payload.classification_reason,
        financial_final_blocker_override=payload.financial_final_blocker_override,
        user_id=current_user.id,
        comment=payload.comment,
        mapped_sku_id=payload.mapped_sku_id,
    )
    await money_snapshot_service.invalidate_snapshots(
        session, account_id=issue.account_id
    )
    await snapshot_service.invalidate_snapshots(session, account_id=issue.account_id)
    await session.commit()
    await session.refresh(issue)
    return DataQualityIssueActionResponse(issue=DataQualityIssueRead.from_issue(issue))


@router.post("/dq/issues/bulk-classify", response_model=BulkMutationResponse)
async def bulk_classify_data_quality_issues(
    payload: DataQualityIssueBulkClassifyRequest,
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> BulkMutationResponse:
    updated_count = await service.bulk_update_issues(
        session,
        ids=payload.issue_ids,
        action="classify",
        classification_status=payload.classification_status,
        classification_reason=payload.classification_reason,
        financial_final_blocker_override=payload.financial_final_blocker_override,
        user_id=current_user.id,
    )
    await money_snapshot_service.invalidate_snapshots(session)
    await snapshot_service.invalidate_snapshots(session)
    await session.commit()
    return BulkMutationResponse(updated_count=updated_count)
