from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.finance import (
    BalanceSnapshotRead,
    FinanceReportRowsPage,
    RealizationReportRead,
)
from app.services.auth import get_current_superuser
from app.services.finance import FinanceService

router = APIRouter(tags=["finance"])
service = FinanceService()


@router.get("/finance/reports", response_model=Page[RealizationReportRead])
async def list_finance_reports(
    account_id: int | None = Query(default=None),
    report_id: int | None = Query(default=None),
    report_name: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_reports(
        session,
        account_id=account_id,
        report_id=report_id,
        report_name=report_name,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/finance/report-rows", response_model=FinanceReportRowsPage)
async def list_finance_report_rows(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    srid: str | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    doc_type_name: str | None = Query(default=None),
    doc_type_names: list[str] | None = Query(default=None),
    operation_type: str | None = Query(default=None),
    seller_oper_name: str | None = Query(default=None),
    seller_oper_names: list[str] | None = Query(default=None),
    office_name: str | None = Query(default=None),
    office_names: list[str] | None = Query(default=None),
    report_id: int | None = Query(default=None),
    is_reconcilable: bool | None = Query(default=None),
    search: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    min_amount: float | None = Query(default=None),
    max_amount: float | None = Query(default=None),
    aggregate: bool = Query(default=False),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_report_rows(
        session,
        account_id=account_id,
        nm_id=nm_id,
        srid=srid,
        vendor_code=vendor_code,
        barcode=barcode,
        doc_type_name=doc_type_name,
        doc_type_names=doc_type_names,
        operation_type=operation_type,
        seller_oper_name=seller_oper_name,
        seller_oper_names=seller_oper_names,
        office_name=office_name,
        office_names=office_names,
        report_id=report_id,
        is_reconcilable=is_reconcilable,
        search=search,
        date_from=date_from,
        date_to=date_to,
        min_amount=min_amount,
        max_amount=max_amount,
        aggregate=aggregate,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/balance", response_model=Page[BalanceSnapshotRead])
async def list_balance_snapshots(
    account_id: int | None = Query(default=None),
    currency: str | None = Query(default=None),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_balances(
        session,
        account_id=account_id,
        currency=currency,
        date_from=date_from,
        date_to=date_to,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
