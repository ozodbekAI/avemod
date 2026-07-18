from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
)
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import SessionLocal, get_db_session
from app.core.runtime_profiling import profile_endpoint
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.control_tower import ActionRecommendation
from app.models.auth import AuthUser
from app.models.operator import OperatorCase, UnifiedAction
from app.models.photo_studio import PhotoAsset
from app.models.problem_engine import ProblemDefinition, ProblemInstance
from app.schemas.claims import (
    CaseDetailOut,
    ClaimCandidatesPage,
    ClaimCandidateOut,
    ClaimCandidateStatusUpdate,
    ClaimDetectionRunOut,
    ClaimDetectionRunsPage,
    ClaimsAppealDraftOut,
    ClaimsAppealDraftRequest,
    ClaimScanRequest,
    ClaimScanStartOut,
    ClaimsCaseCreate,
    ClaimsCaseFromSignalCreate,
    ClaimsCaseUpdate,
    ClaimsCasesPage,
    ClaimsDetectionOut,
    ClaimsDraftGenerateRequest,
    ClaimsDraftMutationOut,
    ClaimsEvidenceCreate,
    ClaimsOrderLookupRequest,
    ClaimsProofCheckOut,
    ClaimsProofCheckRequest,
    ClaimsQrExtractOut,
    ClaimsSubmitRequest,
    ClaimsSupportCategoriesOut,
)
from app.schemas.card_quality import (
    CardQualityAnalyzeRequest,
    CardQualityAnalyzeResponse,
    CardQualityFixedFileEntriesPage,
    CardQualityFixedFileEntryMutation,
    CardQualityFixedFileEntryRead,
    CardQualityFixedFileStatus,
    CardQualityFixedFileUploadResponse,
    CardQualityIssueApplyPreview,
    CardQualityIssueDraftRequest,
    CardQualityIssueFixRequest,
    CardQualityIssueFixResponse,
    CardQualityIssueMarkFixedRequest,
    CardQualityIssueRead,
    CardQualityIssuesGrouped,
    CardQualityIssuesPage,
    CardQualityIssueStatusUpdate,
    CardQualityProductAnalyzeRequest,
    CardQualityProductsPage,
    CardQualityProductRecheckResponse,
    CardQualityQueueProgress,
    CardQualityRunRead,
    CardQualityRunsPage,
)
from app.schemas.operator import CaseType, ProfitDoctorOut, ResultEventOut
from app.schemas.photo import (
    PhotoAssetOut,
    PhotoDownloadUrlOut,
    PhotoExperimentCreateRequest,
    PhotoJobCreate,
    PhotoJobOut,
    PhotoJobsPage,
    PhotoProjectCreate,
    PhotoProjectMessageCreate,
    PhotoProjectMessageOut,
    PhotoProjectOut,
    PhotoProjectsPage,
    PhotoProjectUpdate,
    PhotoSettingsOut,
    PhotoSettingsUpdate,
    PhotoStudioStatusOut,
    PhotoVersionCreate,
    PhotoVersionOut,
    PhotoVersionReview,
    PhotoWBImportOut,
)
from app.schemas.portal import (
    PortalActionRead,
    PortalActionsPage,
    PortalActionSourceUpdateRequest,
    PortalActionUpdateRequest,
    PortalAssignableUserRead,
    PortalDashboardOverviewRead,
    PortalDataReadinessRead,
    PortalDataSyncStatusRead,
    PortalExperimentCreate,
    PortalExperimentEvaluationRead,
    PortalExperimentEventCreate,
    PortalExperimentEventRead,
    PortalExperimentEventsPage,
    PortalExperimentInterventionCreate,
    PortalExperimentInterventionRead,
    PortalExperimentMetricsPage,
    PortalExperimentRead,
    PortalExperimentsPage,
    PortalExperimentSettingsRead,
    PortalExperimentSettingsUpdate,
    PortalExperimentsStatusRead,
    PortalExperimentUpdate,
    PortalGroupingCandidateStatusUpdate,
    PortalGroupingPreviewRead,
    PortalGroupingPreviewRequest,
    PortalManualActionCreateRequest,
    PortalModulesHealthRead,
    PortalOverviewRead,
    PortalProduct360Read,
    PortalProductGroupingRead,
    PortalProductQualityRead,
    PortalProductRead,
    PortalProductsPage,
    PortalResultEventCreate,
    PortalResultEventRead,
    PortalResultEventsPage,
    PortalStockOpsRunRead,
    PortalStockOpsRunRequest,
    PortalStockOpsRunsPage,
)
from app.schemas.reputation import (
    ReputationAnalyticsOut,
    ReputationBrandsOut,
    ReputationBulkDraftDecisionOut,
    ReputationChatEventsOut,
    ReputationChatsOut,
    ReputationDraftDecisionRequest,
    ReputationDraftMutationOut,
    ReputationDraftRequest,
    ReputationDraftsOut,
    ReputationInboxOut,
    ReputationItemOut,
    ReputationLearningApplyRequest,
    ReputationLearningOut,
    ReputationLearningToggleRequest,
    ReputationNoReplyRequest,
    ReputationProductInsightOut,
    ReputationPromptUpdateRequest,
    ReputationPublishRequest,
    ReputationSettingsOut,
    ReputationSettingsUpdateRequest,
    ReputationSummaryOut,
    ReputationSyncOut,
)
from app.services.auth import (
    get_current_superuser,
    get_current_user,
    resolve_user_account,
    resolve_user_account_role,
)
from app.services.claims_adapter import ClaimsDefectAdapter
from app.services.claims_case_templates import (
    claim_case_template_metadata,
    not_implemented_detection,
)
from app.services.claims_factory import ClaimsFactoryService
from app.services.diagnosis.profit_doctor import ProfitDoctorService
from app.services.photo_studio import PhotoStudioService
from app.services.portal import PortalService
from app.services.problem_engine.runner import ProblemEvaluationRunnerService

router = APIRouter(tags=["portal"])
service = PortalService()
doctor_service = ProfitDoctorService(claims_adapter=ClaimsDefectAdapter())
claims_service = ClaimsFactoryService()
claims_detection_adapter = ClaimsDefectAdapter()
photo_service = PhotoStudioService()
problem_evaluation_runner = ProblemEvaluationRunnerService()

_ACTION_LIST_PAYLOAD_DROP_KEYS = {
    "allowed_actions",
    "calculation_snapshot",
    "data_freshness",
    "dedup_key",
    "dedupe_key",
    "evidence_ledger",
    "money_trust",
    "raw",
    "recheck_rule",
    "resolver",
    "solve_map",
    "source_references",
}


def _compact_action_for_list(item: PortalActionRead) -> PortalActionRead:
    payload = {
        key: value
        for key, value in dict(item.payload or {}).items()
        if key not in _ACTION_LIST_PAYLOAD_DROP_KEYS
    }
    evidence_ledger = _compact_evidence_ledger_model(item.evidence_ledger)
    return item.model_copy(
        deep=False,
        update={
            "payload": payload,
            "raw": {},
            "evidence_ledger": evidence_ledger,
            "source_references": list(item.source_references or [])[:3],
        },
    )


def _compact_evidence_ledger_model(evidence_ledger: object) -> object:
    if evidence_ledger is not None:
        facts = [
            fact.model_copy(deep=False, update={"sample_rows": []})
            for fact in list(getattr(evidence_ledger, "input_facts", []) or [])[:1]
        ]
        evidence_ledger = evidence_ledger.model_copy(
            deep=False,
            update={
                "input_facts": facts,
                "source_references": list(
                    getattr(evidence_ledger, "source_references", []) or []
                )[:3],
                "trust_notes": list(getattr(evidence_ledger, "trust_notes", []) or [])[
                    :3
                ],
                "calculation_warnings": list(
                    getattr(evidence_ledger, "calculation_warnings", []) or []
                )[:3],
                "money_trust": None,
            },
        )
    return evidence_ledger


def _compact_action_list_page(page: PortalActionsPage) -> PortalActionsPage:
    items: list[PortalActionRead] = []
    for item in page.items:
        items.append(_compact_action_for_list(item))
    return page.model_copy(deep=False, update={"items": items})


def _compact_evidence_ledger_dict(value: object) -> object:
    if not isinstance(value, dict):
        return value
    ledger = dict(value)
    facts: list[object] = []
    for fact in list(ledger.get("input_facts") or [])[:1]:
        if isinstance(fact, dict):
            compact_fact = dict(fact)
            compact_fact["sample_rows"] = []
            facts.append(compact_fact)
        else:
            facts.append(fact)
    ledger["input_facts"] = facts
    for key, max_items in (
        ("source_references", 3),
        ("trust_notes", 3),
        ("calculation_warnings", 3),
    ):
        current = ledger.get(key)
        if isinstance(current, list):
            ledger[key] = current[:max_items]
    ledger["money_trust"] = None
    return ledger


def _compact_action_dict_for_list(value: object) -> object:
    if not isinstance(value, dict):
        return value
    item = dict(value)
    payload = {
        key: payload_value
        for key, payload_value in dict(item.get("payload") or {}).items()
        if key not in _ACTION_LIST_PAYLOAD_DROP_KEYS
    }
    item["payload"] = payload
    item["raw"] = {}
    source_references = item.get("source_references")
    if isinstance(source_references, list):
        item["source_references"] = source_references[:3]
    item["evidence_ledger"] = _compact_evidence_ledger_dict(
        item.get("evidence_ledger")
    )
    return item


def _compact_product360_business_issues(block: object) -> object:
    data = dict(getattr(block, "data", {}) or {})
    for key in ("items", "open", "resolved", "actions"):
        value = data.get(key)
        if isinstance(value, list):
            data[key] = [_compact_action_dict_for_list(item) for item in value]
    groups = data.get("groups")
    if isinstance(groups, list):
        compact_groups: list[object] = []
        for group in groups:
            if not isinstance(group, dict):
                compact_groups.append(group)
                continue
            compact_group = dict(group)
            for key in ("items", "open", "resolved", "actions"):
                value = compact_group.get(key)
                if isinstance(value, list):
                    compact_group[key] = [
                        _compact_action_dict_for_list(item) for item in value
                    ]
            compact_groups.append(compact_group)
        data["groups"] = compact_groups
    return block.model_copy(deep=False, update={"data": data})


def _compact_product_row(
    row: PortalProductRead,
    *,
    include_action_payload: bool,
    include_raw: bool,
    include_row_details: bool,
) -> PortalProductRead:
    updates: dict[str, object] = {
        "evidence_ledger": _compact_evidence_ledger_model(row.evidence_ledger)
    }
    if not include_action_payload:
        if row.top_action is not None:
            updates["top_action"] = _compact_action_for_list(row.top_action)
        if row.next_action is not None:
            updates["next_action"] = _compact_action_for_list(row.next_action)
    if not include_raw:
        updates["raw"] = {}
    if not include_row_details:
        updates["money"] = None
        updates["stock"] = None
        updates["ads"] = None
        updates["stock_summary"] = None
    return row.model_copy(deep=False, update=updates)


def _compact_products_page(
    page: PortalProductsPage,
    *,
    include_action_payload: bool,
    include_raw: bool,
    include_row_details: bool,
) -> PortalProductsPage:
    if include_action_payload and include_raw and include_row_details:
        return page
    return page.model_copy(
        deep=False,
        update={
            "items": [
                _compact_product_row(
                    row,
                    include_action_payload=include_action_payload,
                    include_raw=include_raw,
                    include_row_details=include_row_details,
                )
                for row in page.items
            ]
        },
    )


def _compact_product360_page(
    page: PortalProduct360Read,
    *,
    include_reputation_items: bool,
    include_action_payload: bool,
    include_raw: bool,
) -> PortalProduct360Read:
    updates: dict[str, object] = {}
    if not include_reputation_items:
        reputation_data = dict(page.reputation.data or {})
        for key in ("items", "last_items"):
            value = reputation_data.get(key)
            if isinstance(value, list):
                reputation_data[key] = value[:3]
        reputation_data.pop("actions", None)
        reputation_data.pop("next_reputation_action", None)
        updates["reputation"] = page.reputation.model_copy(
            deep=False,
            update={"data": reputation_data},
        )
    if not include_action_payload:
        updates["actions"] = [_compact_action_for_list(item) for item in page.actions]
        if page.next_best_action is not None:
            updates["next_best_action"] = _compact_action_for_list(
                page.next_best_action
            )
        updates["business_issues"] = _compact_product360_business_issues(
            page.business_issues
        )
    if not include_raw:
        updates["raw"] = {}
    if not updates:
        return page
    return page.model_copy(deep=False, update=updates)


async def _process_photo_jobs_background(max_jobs: int = 1) -> None:
    async with SessionLocal() as session:
        try:
            await PhotoStudioService().process_queued_jobs(session, max_jobs=max_jobs)
            await session.commit()
        except Exception:
            await session.rollback()


_DETECTION_STATUSES = {
    "ok",
    "not_configured",
    "not_implemented",
    "not_enough_data",
    "unavailable",
    "empty",
}
_DETECTION_PRIVATE_FIELD_TOKENS = {
    "address",
    "api_key",
    "authorization",
    "buyer",
    "credential",
    "customer",
    "email",
    "encrypted_token",
    "encryption_key",
    "fio",
    "full_name",
    "headers",
    "jwt",
    "passport",
    "password",
    "phone",
    "refresh_token",
    "secret",
    "token",
}
_PORTAL_ROLE_RANK = {
    "viewer": 0,
    "operator": 1,
    "manager": 2,
    "admin": 3,
    "superuser": 4,
}


def _validate_date_window(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=400, detail="date_from must be less than or equal to date_to"
        )


def _resolve_period_window(
    *,
    period: Literal["today", "7d", "30d", "custom"] | None,
    date_from: date | None,
    date_to: date | None,
) -> tuple[date | None, date | None]:
    if period in {None, "custom"}:
        _validate_date_window(date_from, date_to)
        return date_from, date_to

    today = utcnow().date()
    if period == "today":
        return today, today
    if period == "7d":
        return today - timedelta(days=6), today
    if period == "30d":
        return today - timedelta(days=29), today
    _validate_date_window(date_from, date_to)
    return date_from, date_to


def _normalize_claims_detection_status(raw_status: object, *, has_items: bool) -> str:
    status = str(raw_status or "empty")
    if status == "disabled":
        return "not_configured"
    if status == "ok" and not has_items:
        return "empty"
    if status not in _DETECTION_STATUSES:
        return "unavailable"
    return status


def _claims_detection_trust_state(raw_trust_state: object, *, status: str) -> str:
    trust_state = str(raw_trust_state or "")
    if trust_state == "provisional" or status in {"ok", "empty"}:
        return "provisional"
    return "unavailable"


def _safe_claims_detection_payload(value):
    if isinstance(value, dict):
        return {
            key: _safe_claims_detection_payload(item)
            for key, item in value.items()
            if not any(
                token in str(key).lower() for token in _DETECTION_PRIVATE_FIELD_TOKENS
            )
        }
    if isinstance(value, list):
        return [_safe_claims_detection_payload(item) for item in value]
    return value


async def _optional_portal_account(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
) -> WBAccount | None:
    return await resolve_user_account(
        session, user, account_id=account_id, require_account=False
    )


async def _required_portal_account(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
) -> WBAccount:
    account = await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )
    if account is None:
        raise HTTPException(status_code=400, detail="account_id is required")
    return account


def _role_rank(role: str | None) -> int:
    return _PORTAL_ROLE_RANK.get(str(role or "viewer").lower(), 0)


async def _require_portal_role(
    session: AsyncSession,
    user: AuthUser,
    *,
    account: WBAccount,
    minimum_role: Literal["operator", "manager", "admin"],
    detail: str | None = None,
) -> str:
    role = await resolve_user_account_role(session, user, account_id=account.id)
    if _role_rank(role) < _role_rank(minimum_role):
        raise HTTPException(
            status_code=403,
            detail=detail
            or f"{minimum_role}+ account role required for this portal operation",
        )
    return role


async def _required_portal_account_for_role(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int | None,
    minimum_role: Literal["operator", "manager", "admin"],
    detail: str | None = None,
) -> WBAccount:
    account = await _required_portal_account(session, user, account_id=account_id)
    await _require_portal_role(
        session, user, account=account, minimum_role=minimum_role, detail=detail
    )
    return account


async def _required_action_account(
    session: AsyncSession,
    user: AuthUser,
    *,
    action_id: int,
) -> WBAccount:
    action = await session.get(ActionRecommendation, action_id)
    unified_action = None
    if action is None:
        unified_action = await session.get(UnifiedAction, action_id)
    if action is None and unified_action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return await _required_portal_account(
        session,
        user,
        account_id=action.account_id
        if action is not None
        else unified_action.account_id,
    )


def _require_legacy_diagnostics_access(user: AuthUser) -> None:
    settings = get_settings()
    if bool(getattr(user, "is_superuser", False)) and bool(
        settings.enable_legacy_diagnostics
    ):
        return
    raise HTTPException(status_code=404, detail="Legacy diagnostics are disabled")


@router.get("/portal/doctor", response_model=ProfitDoctorOut)
async def portal_profit_doctor(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    period: Literal["today", "7d", "30d", "custom"] | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProfitDoctorOut:
    resolved_from, resolved_to = _resolve_period_window(
        period=period, date_from=date_from, date_to=date_to
    )
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    _require_legacy_diagnostics_access(current_user)
    return await doctor_service.diagnose(
        session,
        account_id=account.id,
        date_from=resolved_from,
        date_to=resolved_to,
        nm_id=nm_id,
    )


@router.get("/portal/overview", response_model=PortalOverviewRead)
async def portal_overview(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalOverviewRead:
    with profile_endpoint("/portal/overview", account_id=account_id, limit=limit):
        _validate_date_window(date_from, date_to)
        account = await _optional_portal_account(
            session, current_user, account_id=account_id
        )
        return await service.overview(
            session,
            account_id=account.id if account is not None else None,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )


@router.get("/portal/dashboard/overview", response_model=PortalDashboardOverviewRead)
async def portal_dashboard_overview(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalDashboardOverviewRead:
    with profile_endpoint(
        "/portal/dashboard/overview", account_id=account_id, limit=limit
    ):
        _validate_date_window(date_from, date_to)
        account = await _optional_portal_account(
            session, current_user, account_id=account_id
        )
        return await service.dashboard_overview(
            session,
            account_id=account.id if account is not None else None,
            date_from=date_from,
            date_to=date_to,
            limit=limit,
        )


@router.get("/portal/data-readiness", response_model=PortalDataReadinessRead)
async def portal_data_readiness(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalDataReadinessRead:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.data_readiness(
        session,
        account_id=account.id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/portal/data-sync/status", response_model=PortalDataSyncStatusRead)
async def portal_data_sync_status(
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalDataSyncStatusRead:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.data_sync_status(session, account_id=account.id)


@router.get("/portal/actions", response_model=PortalActionsPage)
async def portal_actions(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    status: str | None = Query(default=None),
    source_module: list[str] | None = Query(default=None),
    priority: list[str] | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    action_type: list[str] | None = Query(default=None),
    problem_code: list[str] | None = Query(default=None),
    trust_state: list[str] | None = Query(default=None),
    impact_type: list[str] | None = Query(default=None),
    include_beta: bool = Query(default=False),
    include_payload: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalActionsPage:
    with profile_endpoint(
        "/portal/actions",
        account_id=account_id,
        nm_id=nm_id,
        limit=limit,
        offset=offset,
    ):
        _validate_date_window(date_from, date_to)
        account = await _optional_portal_account(
            session, current_user, account_id=account_id
        )
        if include_beta and account is not None:
            await _require_portal_role(
                session,
                current_user,
                account=account,
                minimum_role="admin",
                detail="admin account role required to include beta Action Center sources",
            )
        page = await service.actions(
            session,
            account_id=account.id if account is not None else None,
            date_from=date_from,
            date_to=date_to,
            status=status,
            source_module=source_module,
            priority=priority,
            nm_id=nm_id,
            action_type=action_type,
            problem_code=problem_code,
            trust_state=trust_state,
            impact_type=impact_type,
            include_beta=include_beta,
            limit=limit,
            offset=offset,
        )
        if include_payload:
            return page
        return _compact_action_list_page(page)


@router.get("/portal/assignable-users", response_model=list[PortalAssignableUserRead])
async def portal_assignable_users(
    account_id: int = Query(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[PortalAssignableUserRead]:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    return await service.assignable_users(
        session, account_id=account.id, user=current_user
    )


@router.post("/portal/actions/manual", response_model=PortalActionRead)
async def portal_create_manual_action(
    payload: PortalManualActionCreateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalActionRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await service.create_manual_action(
        session, payload=scoped_payload, user_id=current_user.id
    )


@router.patch("/portal/actions/by-source", response_model=PortalActionRead)
async def portal_update_action_by_source(
    payload: PortalActionSourceUpdateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalActionRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await service.update_action_by_source(
        session, payload=scoped_payload, user_id=current_user.id
    )


@router.post("/portal/problems/{problem_id}/recheck", response_model=PortalActionRead)
async def portal_recheck_problem_instance(
    problem_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalActionRead:
    instance = await session.get(ProblemInstance, problem_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Problem instance not found")
    await _required_portal_account_for_role(
        session,
        current_user,
        account_id=instance.account_id,
        minimum_role="operator",
    )
    _, refreshed = await problem_evaluation_runner.recheck_problem_instance(
        session,
        problem_instance_id=problem_id,
        actor_user_id=current_user.id,
    )
    definition = await session.get(ProblemDefinition, refreshed.problem_definition_id)
    await session.commit()
    await session.refresh(refreshed)
    return service._finalize_action(
        service._problem_instance_action(refreshed, definition=definition)
    )


@router.patch("/portal/actions/{action_id}", response_model=PortalActionRead)
async def portal_update_action(
    action_id: int,
    payload: PortalActionUpdateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalActionRead:
    action = await session.get(ActionRecommendation, action_id)
    unified_action = None
    if action is None:
        unified_action = await session.get(UnifiedAction, action_id)
    if action is None and unified_action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    account = await _required_portal_account(
        session,
        current_user,
        account_id=action.account_id
        if action is not None
        else unified_action.account_id,
    )
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    return await service.update_action(
        session, action_id=action_id, user_id=current_user.id, payload=payload
    )


@router.get("/portal/results", response_model=PortalResultEventsPage)
async def portal_results(
    account_id: int | None = Query(default=None),
    action_id: int | None = Query(default=None),
    problem_instance_id: int | None = Query(default=None),
    problem_code: str | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    source_module: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    result_status: str | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    trust_state: str | None = Query(default=None),
    impact_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalResultEventsPage:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.results(
        session,
        account_id=account.id,
        action_id=action_id,
        problem_instance_id=problem_instance_id,
        problem_code=problem_code,
        nm_id=nm_id,
        source_module=source_module,
        event_type=event_type,
        result_status=result_status,
        search=search,
        date_from=date_from,
        date_to=date_to,
        trust_state=trust_state,
        impact_type=impact_type,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/portal/actions/{action_id}/results", response_model=PortalResultEventsPage
)
async def portal_action_results(
    action_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalResultEventsPage:
    account = await _required_action_account(session, current_user, action_id=action_id)
    return await service.action_results(
        session, account_id=account.id, action_id=action_id, limit=limit, offset=offset
    )


@router.get(
    "/portal/problems/{problem_instance_id}/results",
    response_model=PortalResultEventsPage,
)
async def portal_problem_results(
    problem_instance_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalResultEventsPage:
    instance = await session.get(ProblemInstance, problem_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="Problem instance not found")
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=instance.account_id,
        minimum_role="operator",
    )
    return await service.problem_results(
        session,
        account_id=account.id,
        problem_instance_id=problem_instance_id,
        limit=limit,
        offset=offset,
        ensure_before_snapshot=True,
        created_by=current_user.id,
    )


@router.post(
    "/portal/actions/{action_id}/result-event", response_model=PortalResultEventRead
)
async def portal_create_action_result_event(
    action_id: int,
    payload: PortalResultEventCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalResultEventRead:
    account = await _required_action_account(session, current_user, action_id=action_id)
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    return await service.create_result_event(
        session,
        account_id=account.id,
        action_id=action_id,
        payload=payload,
        created_by=current_user.id,
    )


@router.get("/portal/products", response_model=PortalProductsPage)
async def portal_products(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    card_quality_status: str | None = Query(default=None),
    sort_by: Literal[
        "priority_score", "revenue", "profit", "quality_score", "quality_issues"
    ] = Query(default="priority_score"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_action_payload: bool = Query(default=True),
    include_raw: bool = Query(default=True),
    include_row_details: bool = Query(default=True),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalProductsPage:
    with profile_endpoint(
        "/portal/products", account_id=account_id, limit=limit, offset=offset
    ):
        _validate_date_window(date_from, date_to)
        account = await _optional_portal_account(
            session, current_user, account_id=account_id
        )
        page = await service.products(
            session,
            account_id=account.id if account is not None else None,
            date_from=date_from,
            date_to=date_to,
            search=search,
            card_quality_status=card_quality_status,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        return _compact_products_page(
            page,
            include_action_payload=include_action_payload,
            include_raw=include_raw,
            include_row_details=include_row_details,
        )


@router.get("/portal/products/{nm_id}", response_model=PortalProduct360Read)
async def portal_product_360(
    nm_id: int,
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    history_limit: int = Query(default=10, ge=1, le=50),
    actions_limit: int = Query(default=10, ge=1, le=50),
    claims_limit: int = Query(default=10, ge=1, le=50),
    include_reputation_items: bool = Query(default=True),
    include_action_payload: bool = Query(default=True),
    include_raw: bool = Query(default=True),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalProduct360Read:
    with profile_endpoint(
        "/portal/products/{nm_id}", account_id=account_id, nm_id=nm_id
    ):
        _validate_date_window(date_from, date_to)
        account = await _optional_portal_account(
            session, current_user, account_id=account_id
        )
        page = await service.product_360(
            session,
            account_id=account.id if account is not None else None,
            nm_id=nm_id,
            date_from=date_from,
            date_to=date_to,
            history_limit=history_limit,
            actions_limit=actions_limit,
            claims_limit=claims_limit,
        )
        return _compact_product360_page(
            page,
            include_reputation_items=include_reputation_items,
            include_action_payload=include_action_payload,
            include_raw=include_raw,
        )


@router.get("/portal/products/{nm_id}/quality", response_model=PortalProductQualityRead)
async def portal_product_quality(
    nm_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalProductQualityRead:
    account = await _optional_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.product_quality(
        session,
        account_id=account.id if account is not None else None,
        nm_id=nm_id,
    )


@router.post(
    "/portal/card-quality/analyze",
    response_model=CardQualityAnalyzeResponse,
    status_code=202,
)
async def portal_card_quality_analyze(
    payload: CardQualityAnalyzeRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityAnalyzeResponse:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    return await service.card_quality.analyze_account(
        session,
        account_id=account.id,
        force=payload.force,
        limit=payload.limit,
        requested_by_user_id=current_user.id,
    )


@router.get("/portal/card-quality/products", response_model=CardQualityProductsPage)
async def portal_card_quality_products(
    account_id: int | None = Query(default=None),
    search: str | None = Query(default=None),
    quality_status: str | None = Query(default=None),
    score_filter: str | None = Query(default=None),
    ai_filter: str | None = Query(default=None),
    media_filter: str | None = Query(default=None),
    sort_by: str = Query(default="quality_issues"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityProductsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.list_product_cards(
        session,
        account_id=account.id,
        search=search,
        quality_status=quality_status,
        score_filter=score_filter,
        ai_filter=ai_filter,
        media_filter=media_filter,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/portal/card-quality/products/{nm_id}/analyze",
    response_model=PortalProductQualityRead,
)
async def portal_card_quality_product_analyze(
    nm_id: int,
    payload: CardQualityProductAnalyzeRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalProductQualityRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    return await service.card_quality.analyze_product(
        session,
        account_id=account.id,
        nm_id=nm_id,
        force=payload.force,
        requested_by_user_id=current_user.id,
    )


@router.post(
    "/portal/card-quality/products/{nm_id}/recheck",
    response_model=CardQualityProductRecheckResponse,
)
async def portal_card_quality_product_recheck(
    nm_id: int,
    payload: CardQualityProductAnalyzeRequest | None = None,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityProductRecheckResponse:
    resolved_account_id = (
        payload.account_id
        if payload is not None and payload.account_id is not None
        else account_id
    )
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=resolved_account_id,
        minimum_role="operator",
    )
    return await service.card_quality.recheck_product(
        session,
        account_id=account.id,
        nm_id=nm_id,
        requested_by_user_id=current_user.id,
    )


@router.get("/portal/card-quality/runs", response_model=CardQualityRunsPage)
async def portal_card_quality_runs(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityRunsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.list_runs(
        session, account_id=account.id, limit=limit, offset=offset
    )


@router.get("/portal/card-quality/runs/{run_id}", response_model=CardQualityRunRead)
async def portal_card_quality_run(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityRunRead:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    try:
        return await service.card_quality.get_run(
            session, account_id=account.id, run_id=run_id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail="Card quality run not found"
        ) from exc


@router.post(
    "/portal/card-quality/runs/{run_id}/retry",
    response_model=CardQualityAnalyzeResponse,
    status_code=202,
)
async def portal_card_quality_run_retry(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityAnalyzeResponse:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.retry_run(
            session,
            account_id=account.id,
            run_id=run_id,
            requested_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404, detail="Card quality run not found"
        ) from exc


@router.get("/portal/card-quality/issues", response_model=CardQualityIssuesPage)
async def portal_card_quality_issues(
    account_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    include_info: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssuesPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.list_issues(
        session,
        account_id=account.id,
        category=category,
        status=status,
        include_info=include_info,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/portal/card-quality/issues/grouped", response_model=CardQualityIssuesGrouped
)
async def portal_card_quality_issues_grouped(
    account_id: int | None = Query(default=None),
    bucket: str = Query(
        default="actionable", pattern="^(actionable|human_check|media|all)$"
    ),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssuesGrouped:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.list_issues_grouped(
        session, account_id=account.id, bucket=bucket, limit=limit
    )


@router.get("/portal/card-quality/issues/queue/next", response_model=dict | None)
async def portal_card_quality_queue_next(
    account_id: int | None = Query(default=None),
    after: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    severity: str | None = Query(default=None),
    bucket: str = Query(
        default="actionable", pattern="^(actionable|human_check|media|all)$"
    ),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any] | None:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.get_next_issue(
        session,
        account_id=account.id,
        after_issue_id=after,
        nm_id=nm_id,
        severity=severity,
        bucket=bucket,
    )


@router.get(
    "/portal/card-quality/issues/queue/progress",
    response_model=CardQualityQueueProgress,
)
async def portal_card_quality_queue_progress(
    account_id: int | None = Query(default=None),
    severity: str | None = Query(default=None),
    bucket: str = Query(
        default="actionable", pattern="^(actionable|human_check|media|all)$"
    ),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityQueueProgress:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.get_queue_progress(
        session, account_id=account.id, severity=severity, bucket=bucket
    )


@router.get(
    "/portal/card-quality/fixed-file/status", response_model=CardQualityFixedFileStatus
)
async def portal_card_quality_fixed_file_status(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityFixedFileStatus:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.fixed_file_status(session, account_id=account.id)


@router.get(
    "/portal/card-quality/fixed-file", response_model=CardQualityFixedFileEntriesPage
)
async def portal_card_quality_fixed_file_entries(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    brand: str | None = Query(default=None, max_length=255),
    subject_name: str | None = Query(default=None, max_length=255),
    char_name: str | None = Query(default=None, max_length=255),
    sort_by: str = Query(
        default="nm_id",
        pattern="^(nm_id|brand|subject_name|char_name|fixed_value|updated_at|created_at)$",
    ),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityFixedFileEntriesPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.card_quality.list_fixed_file_entries(
        session,
        account_id=account.id,
        nm_id=nm_id,
        search=search,
        brand=brand,
        subject_name=subject_name,
        char_name=char_name,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/portal/card-quality/fixed-file/export")
async def portal_card_quality_fixed_file_export(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    brand: str | None = Query(default=None, max_length=255),
    subject_name: str | None = Query(default=None, max_length=255),
    char_name: str | None = Query(default=None, max_length=255),
    sort_by: str = Query(
        default="nm_id",
        pattern="^(nm_id|brand|subject_name|char_name|fixed_value|updated_at|created_at)$",
    ),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    try:
        content = await service.card_quality.export_fixed_file_entries(
            session,
            account_id=account.id,
            nm_id=nm_id,
            search=search,
            brand=brand,
            subject_name=subject_name,
            char_name=char_name,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    filename = f"card_quality_fixed_file_account_{account.id}.xlsx"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/portal/card-quality/fixed-file/upload",
    response_model=CardQualityFixedFileUploadResponse,
)
async def portal_card_quality_fixed_file_upload(
    account_id: int | None = Query(default=None),
    replace_all: bool = Query(default=False),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityFixedFileUploadResponse:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    content = await file.read()
    try:
        return await service.card_quality.upload_fixed_file(
            session,
            account_id=account.id,
            content=content,
            filename=file.filename,
            replace_all=replace_all,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/portal/card-quality/fixed-file", response_model=CardQualityFixedFileEntryRead
)
async def portal_card_quality_fixed_file_create(
    payload: CardQualityFixedFileEntryMutation,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityFixedFileEntryRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    try:
        return await service.card_quality.create_fixed_file_entry(
            session,
            account_id=account.id,
            payload=payload,
            created_by_user_id=current_user.id,
        )
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=409 if code == "fixed_file_entry_duplicate" else 422,
            detail=code,
        ) from exc


@router.patch(
    "/portal/card-quality/fixed-file/{entry_id}",
    response_model=CardQualityFixedFileEntryRead,
)
async def portal_card_quality_fixed_file_update(
    entry_id: int,
    payload: CardQualityFixedFileEntryMutation,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityFixedFileEntryRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    try:
        return await service.card_quality.update_fixed_file_entry(
            session,
            account_id=account.id,
            entry_id=entry_id,
            payload=payload,
            updated_by_user_id=current_user.id,
        )
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=404
            if code == "fixed_file_entry_not_found"
            else 409
            if code == "fixed_file_entry_duplicate"
            else 422,
            detail=code,
        ) from exc


@router.delete("/portal/card-quality/fixed-file/{entry_id}")
async def portal_card_quality_fixed_file_delete(
    entry_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    try:
        return await service.card_quality.delete_fixed_file_entry(
            session, account_id=account.id, entry_id=entry_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/portal/card-quality/fixed-file")
async def portal_card_quality_fixed_file_clear(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    return await service.card_quality.clear_fixed_file_entries(
        session, account_id=account.id
    )


@router.patch(
    "/portal/card-quality/issues/{issue_id}/status", response_model=CardQualityIssueRead
)
async def portal_card_quality_issue_status(
    issue_id: int,
    payload: CardQualityIssueStatusUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.update_issue_status(
            session,
            account_id=account.id,
            issue_id=issue_id,
            status=payload.status,
            changed_by_user_id=current_user.id,
            reason=payload.reason,
            fixed_value=payload.fixed_value,
            postponed_until=payload.postponed_until,
        )
    except ValueError as exc:
        if str(exc) in {
            "illegal_status_transition",
            "human_check_issue_requires_manual_review",
        }:
            raise HTTPException(
                status_code=409, detail="Illegal card quality status transition"
            ) from exc
        raise HTTPException(
            status_code=404, detail="Card quality issue not found"
        ) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/preview",
    response_model=CardQualityIssueApplyPreview,
)
async def portal_card_quality_issue_preview(
    issue_id: int,
    payload: CardQualityIssueFixRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueApplyPreview:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.preview_issue_apply(
            session,
            account_id=account.id,
            issue_id=issue_id,
            fixed_value=payload.fixed_value,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/preview-wb",
    response_model=CardQualityIssueApplyPreview,
)
async def portal_card_quality_issue_preview_wb(
    issue_id: int,
    payload: CardQualityIssueFixRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueApplyPreview:
    return await portal_card_quality_issue_preview(
        issue_id=issue_id,
        payload=payload,
        account_id=account_id,
        current_user=current_user,
        session=session,
    )


@router.post(
    "/portal/card-quality/issues/{issue_id}/fix",
    response_model=CardQualityIssueFixResponse,
)
async def portal_card_quality_issue_fix(
    issue_id: int,
    payload: CardQualityIssueFixRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueFixResponse:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.fix_issue(
            session,
            account_id=account.id,
            issue_id=issue_id,
            fixed_value=payload.fixed_value,
            apply_to_wb=payload.apply_to_wb,
            confirm=payload.confirm,
            changed_by_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        if detail in {
            "illegal_status_transition",
            "human_check_issue_requires_manual_review",
        }:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/accept-local",
    response_model=CardQualityIssueFixResponse,
)
async def portal_card_quality_issue_accept_local(
    issue_id: int,
    payload: CardQualityIssueFixRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueFixResponse:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.accept_issue_local(
            session,
            account_id=account.id,
            issue_id=issue_id,
            fixed_value=payload.fixed_value,
            changed_by_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        if detail in {
            "illegal_status_transition",
            "human_check_issue_requires_manual_review",
        }:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/mark-fixed",
    response_model=CardQualityIssueRead,
)
async def portal_card_quality_issue_mark_fixed(
    issue_id: int,
    payload: CardQualityIssueMarkFixedRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.mark_issue_fixed(
            session,
            account_id=account.id,
            issue_id=issue_id,
            fixed_value=payload.fixed_value,
            changed_by_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        if detail == "illegal_status_transition":
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/draft", response_model=CardQualityIssueRead
)
async def portal_card_quality_issue_save_draft(
    issue_id: int,
    payload: CardQualityIssueDraftRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.save_issue_draft(
            session,
            account_id=account.id,
            issue_id=issue_id,
            fixed_value=payload.fixed_value,
            changed_by_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        if detail == "illegal_status_transition":
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/apply-wb",
    response_model=CardQualityIssueFixResponse,
)
async def portal_card_quality_issue_apply_wb(
    issue_id: int,
    payload: CardQualityIssueFixRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueFixResponse:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.fix_issue(
            session,
            account_id=account.id,
            issue_id=issue_id,
            fixed_value=payload.fixed_value,
            apply_to_wb=True,
            confirm=payload.confirm,
            changed_by_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        if detail in {
            "illegal_status_transition",
            "human_check_issue_requires_manual_review",
        }:
            raise HTTPException(status_code=409, detail=detail) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.post(
    "/portal/card-quality/issues/{issue_id}/recheck",
    response_model=CardQualityIssueRead,
)
async def portal_card_quality_issue_recheck(
    issue_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CardQualityIssueRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.card_quality.recheck_issue(
            session,
            account_id=account.id,
            issue_id=issue_id,
            requested_by_user_id=current_user.id,
        )
    except ValueError as exc:
        detail = str(exc)
        if detail == "issue_not_found":
            raise HTTPException(
                status_code=404, detail="Card quality issue not found"
            ) from exc
        raise HTTPException(status_code=400, detail=detail) from exc


@router.get(
    "/portal/products/{nm_id}/grouping", response_model=PortalProductGroupingRead
)
async def portal_product_grouping(
    nm_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalProductGroupingRead:
    account = await _optional_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.product_grouping(
        session,
        account_id=account.id if account is not None else None,
        nm_id=nm_id,
    )


@router.get("/portal/photo/status", response_model=PhotoStudioStatusOut)
async def portal_photo_status(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoStudioStatusOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.status(session, account_id=account.id)


@router.get("/portal/photo/settings", response_model=PhotoSettingsOut)
async def portal_photo_settings(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoSettingsOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.get_settings(session, account_id=account.id)


@router.put("/portal/photo/settings", response_model=PhotoSettingsOut)
async def portal_photo_settings_update(
    payload: PhotoSettingsUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoSettingsOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="manager"
    )
    result = await photo_service.update_settings(
        session, account_id=account.id, payload=payload
    )
    await session.commit()
    return result


@router.get("/portal/photo/projects", response_model=PhotoProjectsPage)
async def portal_photo_projects(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoProjectsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.list_projects(
        session,
        account_id=account.id,
        nm_id=nm_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post("/portal/photo/projects", response_model=PhotoProjectOut, status_code=201)
async def portal_photo_project_create(
    payload: PhotoProjectCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoProjectOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=payload.account_id, minimum_role="operator"
    )
    if payload.account_id != account.id:
        raise HTTPException(status_code=403, detail="account_id mismatch")
    result = await photo_service.create_project(
        session, payload=payload, created_by_user_id=current_user.id
    )
    await session.commit()
    return result


@router.get("/portal/photo/projects/{project_id}", response_model=PhotoProjectOut)
async def portal_photo_project(
    project_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoProjectOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.get_project(
        session, account_id=account.id, project_id=project_id
    )


@router.patch("/portal/photo/projects/{project_id}", response_model=PhotoProjectOut)
async def portal_photo_project_update(
    project_id: int,
    payload: PhotoProjectUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoProjectOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.update_project(
        session,
        account_id=account.id,
        project_id=project_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post(
    "/portal/photo/projects/{project_id}/archive", response_model=PhotoProjectOut
)
async def portal_photo_project_archive(
    project_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoProjectOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.archive_project(
        session,
        account_id=account.id,
        project_id=project_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post(
    "/portal/photo/projects/{project_id}/assets/upload",
    response_model=PhotoAssetOut,
    status_code=201,
)
async def portal_photo_asset_upload(
    project_id: int,
    account_id: int | None = Query(default=None),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoAssetOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.upload_asset(
        session,
        account_id=account.id,
        project_id=project_id,
        file=file,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post(
    "/portal/photo/projects/{project_id}/assets/import-wb",
    response_model=PhotoWBImportOut,
)
async def portal_photo_import_wb_assets(
    project_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoWBImportOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.import_wb_assets(
        session,
        account_id=account.id,
        project_id=project_id,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.get(
    "/portal/photo/projects/{project_id}/assets", response_model=list[PhotoAssetOut]
)
async def portal_photo_assets(
    project_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[PhotoAssetOut]:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.list_assets(
        session, account_id=account.id, project_id=project_id
    )


@router.delete("/portal/photo/assets/{asset_id}", response_model=PhotoAssetOut)
async def portal_photo_asset_delete(
    asset_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoAssetOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.delete_asset(
        session, account_id=account.id, asset_id=asset_id, actor_user_id=current_user.id
    )
    await session.commit()
    return result


@router.get(
    "/portal/photo/assets/{asset_id}/download-url", response_model=PhotoDownloadUrlOut
)
async def portal_photo_asset_download_url(
    asset_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoDownloadUrlOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.download_url(
        session, account_id=account.id, asset_id=asset_id
    )


@router.get("/portal/photo/assets/{asset_id}/download")
async def portal_photo_asset_download(
    asset_id: int,
    token: str = Query(...),
    account_id: int | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
) -> FileResponse:
    asset = await session.get(PhotoAsset, asset_id)
    if asset is None or asset.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Local photo asset file not found")
    if account_id is not None and int(asset.account_id) != int(account_id):
        raise HTTPException(status_code=404, detail="Local photo asset file not found")
    if not asset.storage_key:
        raise HTTPException(status_code=404, detail="Local photo asset file not found")
    photo_service.storage.verify_download_token(
        asset_id=asset.id, storage_key=asset.storage_key, token=token
    )
    path = photo_service.storage.path_for_key(asset.storage_key)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Local photo asset file not found")
    return FileResponse(
        path,
        media_type=asset.mime_type,
        filename=asset.original_file_name or f"photo_asset_{asset.id}",
    )


@router.post(
    "/portal/photo/projects/{project_id}/versions",
    response_model=PhotoVersionOut,
    status_code=201,
)
async def portal_photo_version_create(
    project_id: int,
    payload: PhotoVersionCreate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoVersionOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.create_version(
        session,
        account_id=account.id,
        project_id=project_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post(
    "/portal/photo/projects/{project_id}/versions/{version_id}/review",
    response_model=PhotoVersionOut,
)
async def portal_photo_version_review(
    project_id: int,
    version_id: int,
    payload: PhotoVersionReview,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoVersionOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.review_version(
        session,
        account_id=account.id,
        project_id=project_id,
        version_id=version_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post("/portal/photo/projects/{project_id}/versions/{version_id}/apply-wb")
async def portal_photo_version_apply_wb(
    project_id: int,
    version_id: int,
    payload: dict[str, Any] | None = None,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.apply_version_to_wb(
        session,
        account_id=account.id,
        project_id=project_id,
        version_id=version_id,
        photo_number=int((payload or {}).get("photo_number") or 1),
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post("/portal/photo/projects/{project_id}/card-photos/save-wb")
async def portal_photo_card_photos_save_wb(
    project_id: int,
    payload: dict[str, Any] | None = None,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    raw_photos = (payload or {}).get("photos") or []
    if not isinstance(raw_photos, list):
        raise HTTPException(status_code=400, detail="photos must be a list")
    result = await photo_service.save_project_card_photos_to_wb(
        session,
        account_id=account.id,
        project_id=project_id,
        photos=[str(item) for item in raw_photos],
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post(
    "/portal/photo/projects/{project_id}/versions/{version_id}/experiment",
    response_model=PortalExperimentRead,
)
async def portal_photo_version_create_experiment(
    project_id: int,
    version_id: int,
    payload: PhotoExperimentCreateRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    return await service.create_photo_experiment(
        session,
        account_id=account.id,
        project_id=project_id,
        version_id=version_id,
        payload=payload,
        created_by=current_user.id,
    )


@router.post(
    "/portal/photo/projects/{project_id}/messages",
    response_model=PhotoProjectMessageOut,
    status_code=201,
)
async def portal_photo_message_create(
    project_id: int,
    payload: PhotoProjectMessageCreate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoProjectMessageOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.add_message(
        session,
        account_id=account.id,
        project_id=project_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await session.commit()
    return result


@router.post(
    "/portal/photo/projects/{project_id}/jobs",
    response_model=PhotoJobOut,
    status_code=202,
)
async def portal_photo_job_create(
    project_id: int,
    payload: PhotoJobCreate,
    background_tasks: BackgroundTasks,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoJobOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.create_job(
        session,
        account_id=account.id,
        project_id=project_id,
        payload=payload,
        actor_user_id=current_user.id,
    )
    await session.commit()
    if result.status == "queued":
        background_tasks.add_task(_process_photo_jobs_background, 1)
    return result


@router.get("/portal/photo/jobs", response_model=PhotoJobsPage)
async def portal_photo_jobs(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoJobsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return PhotoJobsPage.model_validate(
        await photo_service.list_jobs(
            session, account_id=account.id, limit=limit, offset=offset
        )
    )


@router.get("/portal/photo/jobs/{job_id}", response_model=PhotoJobOut)
async def portal_photo_job(
    job_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoJobOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await photo_service.get_job(session, account_id=account.id, job_id=job_id)


@router.post(
    "/portal/photo/jobs/{job_id}/retry", response_model=PhotoJobOut, status_code=202
)
async def portal_photo_job_retry(
    job_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoJobOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.retry_job(
        session, account_id=account.id, job_id=job_id, actor_user_id=current_user.id
    )
    await session.commit()
    return result


@router.post("/portal/photo/jobs/{job_id}/cancel", response_model=PhotoJobOut)
async def portal_photo_job_cancel(
    job_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PhotoJobOut:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await photo_service.cancel_job(
        session, account_id=account.id, job_id=job_id
    )
    await session.commit()
    return result


@router.get(
    "/portal/products/{nm_id}/events", response_model=PortalExperimentEventsPage
)
async def portal_product_events(
    nm_id: int,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentEventsPage:
    account = await _optional_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.product_events(
        session,
        account_id=account.id if account is not None else None,
        nm_id=nm_id,
        limit=limit,
        offset=offset,
    )


@router.get("/portal/experiments/status", response_model=PortalExperimentsStatusRead)
async def portal_experiments_status() -> PortalExperimentsStatusRead:
    return service.experiments_status()


@router.get("/portal/experiments/settings", response_model=PortalExperimentSettingsRead)
async def portal_experiment_settings(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentSettingsRead:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.experiment_settings(session, account_id=account.id)


@router.put("/portal/experiments/settings", response_model=PortalExperimentSettingsRead)
async def portal_update_experiment_settings(
    payload: PortalExperimentSettingsUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentSettingsRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    return await service.update_experiment_settings(
        session, account_id=account.id, payload=payload
    )


@router.get("/portal/experiments", response_model=PortalExperimentsPage)
async def portal_experiments(
    account_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    intervention_type: str | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    include_test: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.list_experiments(
        session,
        account_id=account.id,
        status=status,
        intervention_type=intervention_type,
        nm_id=nm_id,
        include_test=include_test,
        limit=limit,
        offset=offset,
    )


@router.post("/portal/experiments", response_model=PortalExperimentRead)
async def portal_create_experiment(
    payload: PortalExperimentCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=payload.account_id, minimum_role="operator"
    )
    return await service.create_experiment(
        session, account_id=account.id, payload=payload, created_by=current_user.id
    )


@router.get("/portal/experiments/{experiment_id}", response_model=PortalExperimentRead)
async def portal_experiment(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentRead:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    result = await service.get_experiment(
        session, account_id=account.id, experiment_id=experiment_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return result


@router.patch(
    "/portal/experiments/{experiment_id}", response_model=PortalExperimentRead
)
async def portal_update_experiment(
    experiment_id: int,
    payload: PortalExperimentUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await service.update_experiment(
        session, account_id=account.id, experiment_id=experiment_id, payload=payload
    )
    if result is None:
        raise HTTPException(status_code=404, detail="experiment_not_found_or_terminal")
    return result


@router.post(
    "/portal/experiments/{experiment_id}/start", response_model=PortalExperimentRead
)
async def portal_start_experiment(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await service.start_experiment(
        session, account_id=account.id, experiment_id=experiment_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return result


@router.post(
    "/portal/experiments/{experiment_id}/record-intervention",
    response_model=PortalExperimentInterventionRead,
)
async def portal_record_experiment_intervention(
    experiment_id: int,
    payload: PortalExperimentInterventionCreate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentInterventionRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await service.record_experiment_intervention(
        session,
        account_id=account.id,
        experiment_id=experiment_id,
        payload=payload,
        user_id=current_user.id,
    )
    if result is None:
        raise HTTPException(
            status_code=400, detail="experiment_intervention_not_allowed"
        )
    return result


@router.post(
    "/portal/experiments/{experiment_id}/cancel", response_model=PortalExperimentRead
)
async def portal_cancel_experiment(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await service.cancel_experiment(
        session, account_id=account.id, experiment_id=experiment_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return result


@router.post(
    "/portal/experiments/{experiment_id}/evaluate",
    response_model=PortalExperimentEvaluationRead,
)
async def portal_evaluate_experiment(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentEvaluationRead:
    account = await _required_portal_account_for_role(
        session, current_user, account_id=account_id, minimum_role="operator"
    )
    result = await service.evaluate_experiment(
        session, account_id=account.id, experiment_id=experiment_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return result


@router.get(
    "/portal/experiments/{experiment_id}/evaluation",
    response_model=PortalExperimentEvaluationRead | None,
)
async def portal_experiment_evaluation(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentEvaluationRead | None:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.latest_experiment_evaluation(
        session, account_id=account.id, experiment_id=experiment_id
    )


@router.get(
    "/portal/experiments/{experiment_id}/metrics",
    response_model=PortalExperimentMetricsPage,
)
async def portal_experiment_metrics(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentMetricsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    result = await service.experiment_metrics(
        session,
        account_id=account.id,
        experiment_id=experiment_id,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return result


@router.get(
    "/portal/experiments/{experiment_id}/events",
    response_model=PortalExperimentEventsPage,
)
async def portal_experiment_events(
    experiment_id: int,
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentEventsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    experiment = await service.get_experiment(
        session, account_id=account.id, experiment_id=experiment_id
    )
    if experiment is None or experiment.nm_id is None:
        raise HTTPException(status_code=404, detail="experiment_not_found")
    return await service.product_events(
        session,
        account_id=account.id,
        nm_id=experiment.nm_id,
        limit=limit,
        offset=offset,
    )


@router.get("/portal/reputation/inbox", response_model=ReputationInboxOut)
async def portal_reputation_inbox(
    account_id: int | None = Query(default=None),
    item_type: Literal["review", "question", "chat", "all"] | None = Query(
        default=None
    ),
    status: str | None = Query(default=None),
    rating: int | None = Query(default=None, ge=1, le=5),
    sentiment: Literal["negative", "neutral", "positive", "unknown"] | None = Query(
        default=None
    ),
    priority: Literal["P0", "P1", "P2", "P3", "P4"] | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationInboxOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_inbox(
        session,
        account_id=account.id,
        item_type=item_type,
        status=status,
        rating=rating,
        sentiment=sentiment,
        priority=priority,
        nm_id=nm_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/portal/reputation/summary", response_model=ReputationSummaryOut)
async def portal_reputation_summary(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationSummaryOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_summary(
        session,
        account_id=account.id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/portal/reputation/analytics", response_model=ReputationAnalyticsOut)
async def portal_reputation_analytics(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    granularity: Literal["day", "week", "month"] = Query(default="day"),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationAnalyticsOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_analytics(
        session,
        account_id=account.id,
        date_from=date_from,
        date_to=date_to,
        granularity=granularity,
    )


@router.post("/portal/reputation/sync", response_model=ReputationSyncOut)
async def portal_reputation_sync(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationSyncOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
        detail="manager/admin account role required for manual reputation approval",
    )
    return await service.reputation_sync(session, account_id=account.id)


@router.get("/portal/reputation/items/{item_id}", response_model=ReputationItemOut)
async def portal_reputation_item(
    item_id: str,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationItemOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_item(
        session, account_id=account.id, item_id=item_id
    )


@router.post(
    "/portal/reputation/items/{item_id}/draft",
    response_model=ReputationDraftMutationOut,
)
async def portal_reputation_generate_draft(
    item_id: str,
    payload: ReputationDraftRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationDraftMutationOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    return await service.reputation_generate_draft(
        session,
        account_id=account.id,
        item_id=item_id,
        payload=payload,
        user_id=current_user.id,
    )


@router.get("/portal/reputation/drafts", response_model=ReputationDraftsOut)
async def portal_reputation_drafts(
    account_id: int | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationDraftsOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_drafts(
        session,
        account_id=account.id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/portal/reputation/drafts/approve-all",
    response_model=ReputationBulkDraftDecisionOut,
)
async def portal_reputation_approve_all_drafts(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationBulkDraftDecisionOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
        detail="manager/admin account role required for bulk reputation draft approval",
    )
    return await service.reputation_approve_all_drafts(
        session, account_id=account.id, limit=limit
    )


@router.get("/portal/reputation/chats", response_model=ReputationChatsOut)
async def portal_reputation_chats(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationChatsOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_chats(
        session, account_id=account.id, limit=limit, offset=offset
    )


@router.get(
    "/portal/reputation/chats/{chat_id}/events", response_model=ReputationChatEventsOut
)
async def portal_reputation_chat_events(
    chat_id: str,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationChatEventsOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_chat_events(
        session, account_id=account.id, chat_id=chat_id
    )


@router.post(
    "/portal/reputation/chats/{chat_id}/draft",
    response_model=ReputationDraftMutationOut,
)
async def portal_reputation_chat_draft(
    chat_id: str,
    payload: ReputationDraftRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationDraftMutationOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    item_id = chat_id if ":" in chat_id else f"chat:{chat_id}"
    return await service.reputation_generate_draft(
        session,
        account_id=account.id,
        item_id=item_id,
        payload=payload,
        user_id=current_user.id,
    )


@router.post(
    "/portal/reputation/items/{item_id}/no-reply-needed", response_model=ResultEventOut
)
async def portal_reputation_no_reply_needed(
    item_id: str,
    payload: ReputationNoReplyRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ResultEventOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
        detail="manager/admin account role required for manual reputation decisions",
    )
    return await service.reputation_mark_no_reply_needed(
        session,
        account_id=account.id,
        item_id=item_id,
        payload=payload,
        user_id=current_user.id,
    )


@router.post(
    "/portal/reputation/drafts/{draft_id}/approve",
    response_model=ReputationDraftMutationOut,
)
async def portal_reputation_approve_draft(
    draft_id: str,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationDraftMutationOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
        detail="manager/admin account role required for manual reputation approval",
    )
    return await service.reputation_approve_draft(
        session,
        account_id=account.id,
        draft_id=draft_id,
        approved_by=current_user.id,
    )


@router.post(
    "/portal/reputation/drafts/{draft_id}/regenerate",
    response_model=ReputationDraftMutationOut,
)
async def portal_reputation_regenerate_draft(
    draft_id: str,
    payload: ReputationDraftDecisionRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationDraftMutationOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    return await service.reputation_regenerate_draft(
        session,
        account_id=account.id,
        draft_id=draft_id,
        payload=payload,
    )


@router.post(
    "/portal/reputation/drafts/{draft_id}/reject",
    response_model=ReputationDraftMutationOut,
)
async def portal_reputation_reject_draft(
    draft_id: str,
    payload: ReputationDraftDecisionRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationDraftMutationOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    return await service.reputation_reject_draft(
        session,
        account_id=account.id,
        draft_id=draft_id,
        payload=payload,
    )


@router.post(
    "/portal/reputation/drafts/{draft_id}/publish", response_model=ResultEventOut
)
async def portal_reputation_publish_reply(
    draft_id: str,
    payload: ReputationPublishRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ResultEventOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
        detail="manager/admin account role required for manual reputation publish",
    )
    return await service.reputation_publish_reply(
        session,
        account_id=account.id,
        draft_id=draft_id,
        payload=payload,
        user_id=current_user.id,
    )


@router.get("/portal/reputation/settings", response_model=ReputationSettingsOut)
async def portal_reputation_settings(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationSettingsOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_settings(session, account_id=account.id)


@router.get("/portal/reputation/brands", response_model=ReputationBrandsOut)
async def portal_reputation_brands(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationBrandsOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_brands(session, account_id=account.id)


@router.put("/portal/reputation/settings", response_model=ReputationSettingsOut)
async def portal_reputation_update_settings(
    payload: ReputationSettingsUpdateRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationSettingsOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
    )
    return await service.reputation_update_settings(
        session, account_id=account.id, payload=payload
    )


@router.get("/portal/reputation/learning", response_model=ReputationLearningOut)
async def portal_reputation_learning(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationLearningOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_learning(session, account_id=account.id)


@router.post("/portal/reputation/learning/toggle", response_model=ReputationLearningOut)
async def portal_reputation_toggle_learning(
    payload: ReputationLearningToggleRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationLearningOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
    )
    return await service.reputation_toggle_learning(
        session, account_id=account.id, payload=payload
    )


@router.put("/portal/reputation/prompts", response_model=ReputationLearningOut)
async def portal_reputation_update_prompts(
    payload: ReputationPromptUpdateRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationLearningOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
    )
    return await service.reputation_update_prompts(
        session, account_id=account.id, payload=payload
    )


@router.post("/portal/reputation/learning/apply", response_model=ReputationLearningOut)
async def portal_reputation_apply_learning(
    payload: ReputationLearningApplyRequest,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationLearningOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
    )
    return await service.reputation_apply_learning(
        session, account_id=account.id, payload=payload
    )


@router.delete(
    "/portal/reputation/learning/entries/{entry_id}",
    response_model=ReputationLearningOut,
)
async def portal_reputation_delete_learning_entry(
    entry_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationLearningOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
    )
    return await service.reputation_delete_learning_entry(
        session, account_id=account.id, entry_id=entry_id
    )


@router.post("/portal/reputation/learning/reset", response_model=ReputationLearningOut)
async def portal_reputation_reset_learning(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationLearningOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="manager",
    )
    return await service.reputation_reset_learning(session, account_id=account.id)


@router.get(
    "/portal/reputation/product-insights/{nm_id}",
    response_model=ReputationProductInsightOut,
)
async def portal_reputation_product_insights(
    nm_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ReputationProductInsightOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation_product_insights(
        session, account_id=account.id, nm_id=nm_id
    )


@router.get("/portal/admin/reputation/prompt-debug")
async def portal_admin_reputation_prompt_debug(
    item_id: str = Query(...),
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation.admin_prompt_debug_context(
        session, account, item_id=item_id
    )


@router.post("/portal/admin/reputation/prompt-probe")
async def portal_admin_reputation_prompt_probe(
    payload: dict[str, Any] | None = None,
    item_id: str = Query(...),
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation.admin_prompt_probe(
        session, account, item_id=item_id, payload=payload
    )


@router.get("/portal/admin/reputation/provider-status")
async def portal_admin_reputation_provider_status(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation.admin_provider_status(session, account)


@router.get("/portal/admin/reputation/generation-logs")
async def portal_admin_reputation_generation_logs(
    account_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: str | None = Query(default=None),
    provider: str | None = Query(default=None),
    q: str | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation.admin_generation_logs(
        session,
        account,
        limit=limit,
        offset=offset,
        status=status,
        provider=provider,
        q=q,
    )


@router.get("/portal/admin/reputation/generation-logs/{log_id}")
async def portal_admin_reputation_generation_log_detail(
    log_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.reputation.admin_generation_log_detail(
        session, account, log_id=log_id
    )


async def _required_case_account(
    session: AsyncSession,
    user: AuthUser,
    *,
    case_id: int,
) -> WBAccount:
    case = await session.get(OperatorCase, case_id)
    if case is None or case.source_module != "claims":
        raise HTTPException(status_code=404, detail="Case not found")
    return await _required_portal_account(session, user, account_id=case.account_id)


@router.get("/portal/cases", response_model=ClaimsCasesPage)
async def portal_cases(
    account_id: int | None = Query(default=None),
    case_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsCasesPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await claims_service.list_cases(
        session,
        account_id=account.id,
        case_type=case_type,
        status=status,
        nm_id=nm_id,
        limit=limit,
        offset=offset,
    )


@router.post("/portal/cases", response_model=CaseDetailOut)
async def portal_create_case(
    payload: ClaimsCaseCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDetailOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await claims_service.create_case(
        session, payload=scoped_payload, created_by=current_user.id
    )


@router.post("/portal/cases/from-signal", response_model=CaseDetailOut)
async def portal_create_case_from_signal(
    payload: ClaimsCaseFromSignalCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDetailOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await claims_service.create_case_from_signal(
        session, payload=scoped_payload, created_by=current_user.id
    )


async def _detect_defect_claims(
    *,
    account_id: int | None,
    date_from: date | None,
    date_to: date | None,
    nm_id: int | None,
    current_user: AuthUser,
    session: AsyncSession,
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = await claims_detection_adapter.detect_defect_candidates(
        account.id,
        (date_from, date_to),
        nm_id=nm_id,
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.DEFECT,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        template=claim_case_template_metadata(CaseType.DEFECT),
    )


async def _not_implemented_claim_detection(
    *,
    account_id: int | None,
    case_type: CaseType,
    current_user: AuthUser,
    session: AsyncSession,
) -> ClaimsDetectionOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return ClaimsDetectionOut(
        **not_implemented_detection(account_id=account.id, case_type=case_type)
    )


@router.get("/portal/cases/detect/defects", response_model=ClaimsDetectionOut)
async def portal_detect_defect_claims(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    return await _detect_defect_claims(
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        nm_id=nm_id,
        current_user=current_user,
        session=session,
    )


@router.get(
    "/portal/cases/detect/supply-discrepancies", response_model=ClaimsDetectionOut
)
async def portal_detect_supply_discrepancies(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = await claims_detection_adapter.detect_supply_discrepancy_candidates(
        account.id,
        (date_from, date_to),
        nm_id=nm_id,
        session=session,
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.SUPPLY_DISCREPANCY,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        required_fields=list(detected.get("required_fields") or []),
        warnings=list(detected.get("warnings") or []),
        template=claim_case_template_metadata(CaseType.SUPPLY_DISCREPANCY),
    )


@router.get("/portal/cases/detect/missing-goods", response_model=ClaimsDetectionOut)
async def portal_detect_missing_goods(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = await claims_detection_adapter.detect_missing_goods_candidates(
        account.id,
        (date_from, date_to),
        nm_id=nm_id,
        session=session,
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.MISSING_GOODS,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        required_fields=list(detected.get("required_fields") or []),
        warnings=list(detected.get("warnings") or []),
        template=claim_case_template_metadata(CaseType.MISSING_GOODS),
    )


@router.get("/portal/cases/detect/report-anomalies", response_model=ClaimsDetectionOut)
async def portal_detect_report_anomalies(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = await claims_detection_adapter.detect_report_anomaly_candidates(
        account.id,
        (date_from, date_to),
        nm_id=nm_id,
        session=session,
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.REPORT_ANOMALY,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        template=claim_case_template_metadata(CaseType.REPORT_ANOMALY),
    )


@router.get(
    "/portal/cases/detect/compensation-underpayments", response_model=ClaimsDetectionOut
)
async def portal_detect_compensation_underpayments(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = (
        await claims_detection_adapter.detect_compensation_underpayment_candidates(
            account.id,
            (date_from, date_to),
            nm_id=nm_id,
            session=session,
        )
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.COMPENSATION_UNDERPAYMENT,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        required_fields=list(detected.get("required_fields") or []),
        warnings=list(detected.get("warnings") or []),
        template=claim_case_template_metadata(CaseType.COMPENSATION_UNDERPAYMENT),
    )


@router.get("/portal/cases/detect/repeat-claims", response_model=ClaimsDetectionOut)
async def portal_detect_repeat_claims(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = await claims_detection_adapter.detect_repeat_claim_candidates(
        account.id, (date_from, date_to), nm_id=nm_id
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.REPEAT_CLAIM,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        template=claim_case_template_metadata(CaseType.REPEAT_CLAIM),
    )


@router.get("/portal/cases/detect/pretrial", response_model=ClaimsDetectionOut)
async def portal_detect_pretrial_cases(
    account_id: int | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDetectionOut:
    _validate_date_window(date_from, date_to)
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    detected = await claims_detection_adapter.detect_pretrial_candidates(
        account.id, (date_from, date_to), nm_id=nm_id
    )
    items = _safe_claims_detection_payload(list(detected.get("items") or []))
    status = _normalize_claims_detection_status(
        detected.get("status"), has_items=bool(items)
    )
    return ClaimsDetectionOut(
        status=status,
        case_type=CaseType.PRETRIAL,
        account_id=account.id,
        items=items,
        item_count=len(items),
        trust_state=_claims_detection_trust_state(
            detected.get("trust_state"), status=status
        ),
        message=detected.get("message"),
        next_stage=detected.get("next_stage"),
        unavailable_sources=list(detected.get("unavailable_sources") or []),
        template=claim_case_template_metadata(CaseType.PRETRIAL),
    )


@router.get("/portal/cases/{case_id}", response_model=CaseDetailOut)
async def portal_case_detail(
    case_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDetailOut:
    account = await _required_case_account(session, current_user, case_id=case_id)
    return await claims_service.get_case(
        session, account_id=account.id, case_id=case_id
    )


@router.patch("/portal/cases/{case_id}", response_model=CaseDetailOut)
async def portal_update_case(
    case_id: int,
    payload: ClaimsCaseUpdate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDetailOut:
    account = await _required_case_account(session, current_user, case_id=case_id)
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    return await claims_service.update_case_status(
        session,
        account_id=account.id,
        case_id=case_id,
        payload=payload,
        updated_by=current_user.id,
    )


@router.post("/portal/cases/{case_id}/evidence", response_model=CaseDetailOut)
async def portal_attach_case_evidence(
    case_id: int,
    payload: ClaimsEvidenceCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDetailOut:
    account = await _required_case_account(session, current_user, case_id=case_id)
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    await claims_service.attach_evidence(
        session,
        account_id=account.id,
        case_id=case_id,
        payload=payload,
        created_by=current_user.id,
    )
    return await claims_service.get_case(
        session, account_id=account.id, case_id=case_id
    )


@router.post(
    "/portal/cases/{case_id}/generate-draft", response_model=ClaimsDraftMutationOut
)
async def portal_generate_case_draft(
    case_id: int,
    payload: ClaimsDraftGenerateRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsDraftMutationOut:
    account = await _required_case_account(session, current_user, case_id=case_id)
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    return await claims_service.generate_draft(
        session,
        account_id=account.id,
        case_id=case_id,
        payload=payload,
        created_by=current_user.id,
    )


@router.post("/portal/cases/{case_id}/proof-check", response_model=ClaimsProofCheckOut)
async def portal_case_proof_check(
    case_id: int,
    payload: ClaimsProofCheckRequest | None = None,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsProofCheckOut:
    account = await _required_case_account(session, current_user, case_id=case_id)
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    return await claims_service.proof_check(
        session, account_id=account.id, case_id=case_id, payload=payload
    )


@router.post("/portal/cases/{case_id}/submit", response_model=ResultEventOut)
async def portal_submit_case(
    case_id: int,
    payload: ClaimsSubmitRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ResultEventOut:
    account = await _required_case_account(session, current_user, case_id=case_id)
    await _require_portal_role(
        session,
        current_user,
        account=account,
        minimum_role="manager",
        detail="manager/admin account role required for manual claims submit",
    )
    return await claims_service.submit_case_manual_confirm(
        session,
        account_id=account.id,
        case_id=case_id,
        payload=payload,
        created_by=current_user.id,
    )


@router.get("/portal/cases/{case_id}/events", response_model=list[ResultEventOut])
async def portal_case_events(
    case_id: int,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> list[ResultEventOut]:
    account = await _required_case_account(session, current_user, case_id=case_id)
    return await claims_service.result_events(
        session, account_id=account.id, case_id=case_id
    )


@router.post("/portal/claims/scans", response_model=ClaimScanStartOut, status_code=202)
async def portal_claims_scan_start(
    payload: ClaimScanRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimScanStartOut:
    _validate_date_window(payload.date_from, payload.date_to)
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    return await claims_service.start_detection_scan(
        session,
        account_id=account.id,
        detector_types=payload.detector_types,
        date_from=payload.date_from,
        date_to=payload.date_to,
        requested_by_user_id=current_user.id,
        force=payload.force,
        detector=claims_detection_adapter,
    )


@router.get(
    "/portal/claims/support/categories", response_model=ClaimsSupportCategoriesOut
)
async def portal_claims_support_categories(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsSupportCategoriesOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    return claims_service.support_categories(account_id=account.id)


@router.post("/portal/claims/qr/extract", response_model=ClaimsQrExtractOut)
async def portal_claims_extract_qr_image(
    account_id: int = Query(...),
    file: UploadFile = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsQrExtractOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    content = await file.read()
    try:
        return await claims_service.extract_order_from_qr_image(
            account_id=account.id,
            content=content,
            content_type=file.content_type or "application/octet-stream",
            filename=file.filename,
        )
    finally:
        await file.close()


@router.post("/portal/claims/media/extract", response_model=ClaimsQrExtractOut)
async def portal_claims_extract_media(
    account_id: int = Query(...),
    files: list[UploadFile] = File(...),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsQrExtractOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    if not files:
        raise HTTPException(status_code=400, detail="At least one image is required")

    media_files: list[dict[str, Any]] = []
    first_image: tuple[bytes, str, str | None] | None = None
    for upload in files:
        content_type = upload.content_type or "application/octet-stream"
        media_files.append(
            {
                "filename": upload.filename,
                "content_type": content_type,
                "kind": "video"
                if content_type.startswith("video/")
                else "image"
                if content_type.startswith("image/")
                else "file",
            }
        )
        content = await upload.read()
        if first_image is None and content_type.startswith("image/"):
            first_image = (content, content_type, upload.filename)
        await upload.close()

    if first_image is None:
        raise HTTPException(
            status_code=400,
            detail="At least one image file is required for order extraction",
        )

    result = await claims_service.extract_order_from_qr_image(
        account_id=account.id,
        content=first_image[0],
        content_type=first_image[1],
        filename=first_image[2],
    )
    result.order_fields["media_files"] = media_files
    video = next((item for item in media_files if item.get("kind") == "video"), None)
    if video:
        result.order_fields["video_file"] = video.get("filename")
    return result


@router.post("/portal/claims/order/lookup", response_model=ClaimsQrExtractOut)
async def portal_claims_lookup_order(
    payload: ClaimsOrderLookupRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsQrExtractOut:
    account = await _required_portal_account(
        session, current_user, account_id=payload.account_id
    )
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await claims_service.lookup_order_fields(
        session, account_id=account.id, payload=scoped_payload
    )


@router.post("/portal/claims/appeal-draft", response_model=ClaimsAppealDraftOut)
async def portal_claims_generate_appeal_draft(
    payload: ClaimsAppealDraftRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimsAppealDraftOut:
    account = await _required_portal_account(
        session, current_user, account_id=payload.account_id
    )
    await _require_portal_role(
        session, current_user, account=account, minimum_role="operator"
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await claims_service.generate_ai_appeal_draft(
        account_id=account.id, payload=scoped_payload
    )


@router.get("/portal/claims/scans", response_model=ClaimDetectionRunsPage)
async def portal_claims_scans(
    account_id: int | None = Query(default=None),
    detector_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimDetectionRunsPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await claims_service.list_detection_runs(
        session,
        account_id=account.id,
        detector_type=detector_type,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/portal/claims/scans/{run_id}", response_model=ClaimDetectionRunOut)
async def portal_claims_scan_detail(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimDetectionRunOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await claims_service.get_detection_run(
        session, account_id=account.id, run_id=run_id
    )


@router.post(
    "/portal/claims/scans/{run_id}/retry",
    response_model=ClaimScanStartOut,
    status_code=202,
)
async def portal_claims_scan_retry(
    run_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimScanStartOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    run = await claims_service.get_detection_run(
        session, account_id=account.id, run_id=run_id
    )
    return await claims_service.start_detection_scan(
        session,
        account_id=account.id,
        detector_types=[run.detector_type],
        date_from=run.date_from,
        date_to=run.date_to,
        requested_by_user_id=current_user.id,
        force=True,
        detector=claims_detection_adapter,
    )


@router.get("/portal/claims/candidates", response_model=ClaimCandidatesPage)
async def portal_claims_candidates(
    account_id: int | None = Query(default=None),
    detector_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    run_id: int | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimCandidatesPage:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await claims_service.list_candidates(
        session,
        account_id=account.id,
        detector_type=detector_type,
        status=status,
        nm_id=nm_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/portal/claims/candidates/{candidate_id}", response_model=ClaimCandidateOut
)
async def portal_claims_candidate_detail(
    candidate_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimCandidateOut:
    account = await _required_portal_account(
        session, current_user, account_id=account_id
    )
    return await claims_service.get_candidate(
        session, account_id=account.id, candidate_id=candidate_id
    )


@router.patch(
    "/portal/claims/candidates/{candidate_id}/status", response_model=ClaimCandidateOut
)
async def portal_claims_candidate_status(
    candidate_id: int,
    payload: ClaimCandidateStatusUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ClaimCandidateOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    return await claims_service.update_candidate_status(
        session,
        account_id=account.id,
        candidate_id=candidate_id,
        payload=payload,
        updated_by=current_user.id,
    )


@router.post(
    "/portal/claims/candidates/{candidate_id}/create-case", response_model=CaseDetailOut
)
async def portal_claims_candidate_create_case(
    candidate_id: int,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> CaseDetailOut:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    return await claims_service.create_case_from_candidate(
        session,
        account_id=account.id,
        candidate_id=candidate_id,
        created_by=current_user.id,
    )


@router.post("/portal/experiments/events", response_model=PortalExperimentEventRead)
async def portal_create_experiment_event(
    payload: PortalExperimentEventCreate,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalExperimentEventRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    scoped_payload = payload.model_copy(update={"account_id": account.id})
    return await service.create_experiment_event(
        session,
        payload=scoped_payload,
        created_by=current_user.id,
    )


@router.post("/portal/grouping/preview", response_model=PortalGroupingPreviewRead)
async def portal_grouping_preview(
    payload: PortalGroupingPreviewRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalGroupingPreviewRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    return await service.grouping_preview(
        session, payload.model_copy(update={"account_id": account.id})
    )


@router.patch("/portal/grouping/candidates/{candidate_id}/status")
async def portal_grouping_candidate_status(
    candidate_id: int,
    payload: PortalGroupingCandidateStatusUpdate,
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=account_id,
        minimum_role="operator",
    )
    try:
        return await service.update_grouping_candidate_status(
            session,
            account_id=account.id,
            candidate_id=candidate_id,
            status=payload.status,
            actor_user_id=current_user.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        if str(exc) == "illegal_status_transition":
            raise HTTPException(
                status_code=409, detail="Illegal grouping status transition"
            ) from exc
        raise HTTPException(
            status_code=404, detail="Grouping candidate not found"
        ) from exc


@router.post("/portal/stockops/run", response_model=PortalStockOpsRunRead)
async def portal_stockops_run(
    payload: PortalStockOpsRunRequest,
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalStockOpsRunRead:
    account = await _required_portal_account_for_role(
        session,
        current_user,
        account_id=payload.account_id,
        minimum_role="operator",
    )
    return await service.stockops_run(
        session,
        payload=payload.model_copy(update={"account_id": account.id}),
        user_id=current_user.id,
    )


@router.get("/portal/stockops/runs", response_model=PortalStockOpsRunsPage)
async def portal_stockops_runs(
    account_id: int | None = Query(default=None),
    run_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalStockOpsRunsPage:
    account = await _optional_portal_account(
        session, current_user, account_id=account_id
    )
    if account is None:
        return PortalStockOpsRunsPage(
            status="not_configured",
            total=0,
            limit=limit,
            offset=offset,
            items=[],
            message="account_id is required when account cannot be inferred",
        )
    return await service.stockops_runs(
        session, account_id=account.id, run_type=run_type, limit=limit, offset=offset
    )


@router.get("/portal/modules/health", response_model=PortalModulesHealthRead)
async def portal_modules_health(
    account_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> PortalModulesHealthRead:
    account = await _optional_portal_account(
        session, current_user, account_id=account_id
    )
    return await service.modules_health(
        session, account_id=account.id if account is not None else None
    )
