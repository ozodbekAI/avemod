from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.core.runtime_profiling import profile_endpoint
from app.models.auth import AuthUser
from app.schemas.money_management import (
    ActionGroups,
    DataBlockersRead,
    ExpenseBreakdownSummaryRead,
    ExpenseReportRowRead,
    MoneyArticleDetailRead,
    MoneyArticlePage,
    MoneyCardDetailRead,
    MoneyCardPage,
    MoneyExpenseLogisticsRead,
    MoneyFiltersRead,
    MoneyControlPanel,
    ProfitCascadeRead,
    MoneySummaryRead,
    TodayActionsPage,
)
from app.services.auth import (
    get_current_superuser,
    get_current_user,
    require_account_role,
    resolve_user_account,
)
from app.services.money_management import MoneyManagementService
from app.services.money_snapshots import MoneyEndpointSnapshotService

router = APIRouter(tags=["money-management"])
service = MoneyManagementService()
snapshot_service = MoneyEndpointSnapshotService()
READ_ROLES = {"viewer", "operator", "manager", "admin"}


async def _require_money_read(
    session: AsyncSession,
    user: AuthUser,
    *,
    account_id: int,
) -> None:
    await resolve_user_account(
        session, user, account_id=account_id, require_account=True
    )
    await require_account_role(
        session, user, account_id=account_id, allowed_roles=READ_ROLES
    )


@router.get("/money/summary", response_model=MoneySummaryRead)
async def money_summary(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    include_control_panel: bool = Query(default=True),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MoneySummaryRead:
    await _require_money_read(session, current_user, account_id=account_id)
    with profile_endpoint("/money/summary", account_id=account_id):
        summary = await snapshot_service.summary(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        if include_control_panel:
            return summary
        return summary.model_copy(
            deep=False,
            update={"control_panel": MoneyControlPanel()},
        )


@router.get("/money/profit-cascade", response_model=ProfitCascadeRead)
async def money_profit_cascade(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ProfitCascadeRead:
    await _require_money_read(session, current_user, account_id=account_id)
    return await service.profit_cascade(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/money/expenses/breakdown", response_model=ExpenseBreakdownSummaryRead)
async def money_expense_breakdown(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    group_by: str = Query(default="category", pattern="^(category|source|sku|nm|day)$"),
    include_unallocated: bool = Query(default=True),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> ExpenseBreakdownSummaryRead:
    await _require_money_read(session, current_user, account_id=account_id)
    if group_by == "category" and include_unallocated:
        summary = await snapshot_service.summary(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        if summary.expense_breakdown is not None:
            return summary.expense_breakdown.model_copy(
                deep=False,
                update={
                    "group_by": group_by,
                    "include_unallocated": include_unallocated,
                },
            )
    return await service.expense_breakdown(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        group_by=group_by,
        include_unallocated=include_unallocated,
    )


@router.get("/money/expenses/logistics", response_model=MoneyExpenseLogisticsRead)
async def money_expense_logistics(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    include_unallocated: bool = Query(default=True),
    top_n: int = Query(default=100, ge=1, le=500),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MoneyExpenseLogisticsRead:
    await _require_money_read(session, current_user, account_id=account_id)
    return await service.expense_logistics(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        include_unallocated=include_unallocated,
        top_n=top_n,
    )


@router.get("/money/expenses/report-rows", response_model=Page[ExpenseReportRowRead])
async def money_expense_report_rows(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    category: str | None = Query(default=None),
    sku_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    amount_min: float | None = Query(default=None),
    amount_max: float | None = Query(default=None),
    amount_exact: float | None = Query(default=None),
    search: str | None = Query(default=None),
    source_field: str | None = Query(default=None),
    seller_oper_name: str | None = Query(default=None),
    allocated: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> Page[ExpenseReportRowRead]:
    await _require_money_read(session, current_user, account_id=account_id)
    return await service.expense_report_rows(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        category=category,
        sku_id=sku_id,
        nm_id=nm_id,
        amount_min=amount_min,
        amount_max=amount_max,
        amount_exact=amount_exact,
        search=search,
        source_field=source_field,
        seller_oper_name=seller_oper_name,
        allocated=allocated,
        limit=limit,
        offset=offset,
    )


@router.get("/money/cards", response_model=MoneyCardPage)
async def money_cards(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    next_action: str | None = Query(default=None),
    trust_state: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    sort_by: str = Query(default="priority_score"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> MoneyCardPage:
    return await snapshot_service.cards(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        status=status,
        next_action=next_action,
        trust_state=trust_state,
        subject_name=subject_name,
        brand=brand,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/money/cards/{sku_id}", response_model=MoneyCardDetailRead)
async def money_card_detail(
    sku_id: int,
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> MoneyCardDetailRead:
    return await service.card_detail(
        session,
        account_id=account_id,
        sku_id=sku_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/money/articles", response_model=MoneyArticlePage)
async def money_articles(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    trust_state: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    sort_by: str = Query(default="priority_score"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> MoneyArticlePage:
    await _require_money_read(session, current_user, account_id=account_id)
    return await snapshot_service.articles(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
        status=status,
        trust_state=trust_state,
        subject_name=subject_name,
        brand=brand,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/money/articles/{nm_id}", response_model=MoneyArticleDetailRead)
async def money_article_detail(
    nm_id: int,
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> MoneyArticleDetailRead:
    return await service.article_detail(
        session,
        account_id=account_id,
        nm_id=nm_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/money/actions", response_model=TodayActionsPage)
@router.get("/money/actions/today", response_model=TodayActionsPage)
async def money_today_actions(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    priority: str | None = Query(default=None),
    status: str | None = Query(default=None),
    action_type: str | None = Query(default=None),
    group_by: str = Query(default="article", pattern="^(article|sku)$"),
    focus_limit: int = Query(default=10, ge=1, le=20),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    include_groups: bool = Query(default=True),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> TodayActionsPage:
    await _require_money_read(session, current_user, account_id=account_id)
    page = await snapshot_service.today_actions(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        priority=priority,
        status=status,
        action_type=action_type,
        group_by=group_by,
        focus_limit=focus_limit,
        limit=limit,
        offset=offset,
    )
    if include_groups:
        return page
    return page.model_copy(deep=False, update={"groups": ActionGroups()})


@router.get("/money/data-blockers", response_model=DataBlockersRead)
async def money_data_blockers(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> DataBlockersRead:
    await _require_money_read(session, current_user, account_id=account_id)
    return await snapshot_service.data_blockers(
        session,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/money/filters", response_model=MoneyFiltersRead)
async def money_filters(
    account_id: int = Query(...),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> MoneyFiltersRead:
    return await service.filters(session, account_id=account_id)
