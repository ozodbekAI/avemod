from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.core.pagination import Page
from app.models.auth import AuthUser
from app.schemas.marts import (
    MartAccountExpenseDailyRead,
    MartBusinessDailyRead,
    MartFinanceReconciliationRead,
    MartReconciliationDailyRead,
    MartRefreshRequest,
    MartRefreshResponse,
    MartSKUDailyRead,
    MartStockDailyRead,
)
from app.services.auth import get_current_superuser
from app.services.marts import MartService
from app.services.operator_snapshots import OperatorEndpointSnapshotService

router = APIRouter(tags=["marts"])
service = MartService()
snapshot_service = OperatorEndpointSnapshotService()
snapshot_service.marts = service


@router.post("/marts/refresh", response_model=MartRefreshResponse)
async def refresh_marts(
    payload: MartRefreshRequest,
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> MartRefreshResponse:
    result = await service.refresh_account(
        session,
        account_id=payload.account_id,
        date_from=payload.date_from,
        date_to=payload.date_to,
    )
    await session.commit()
    return MartRefreshResponse(**result)


@router.get("/marts/sku-daily", response_model=Page[MartSKUDailyRead])
async def list_sku_daily(
    account_id: int | None = Query(default=None),
    sku_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    brand: str | None = Query(default=None),
    subject_name: str | None = Query(default=None),
    search: str | None = Query(default=None),
    has_manual_cost: bool | None = Query(default=None),
    has_open_issues: bool | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    aggregate: str | None = Query(default=None, pattern="^(week|month)$"),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    if account_id is None:
        return await service.list_sku_daily(
            session,
            account_id=account_id,
            sku_id=sku_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            barcode=barcode,
            brand=brand,
            subject_name=subject_name,
            search=search,
            has_manual_cost=has_manual_cost,
            has_open_issues=has_open_issues,
            date_from=None if date_from is None else date.fromisoformat(date_from),
            date_to=None if date_to is None else date.fromisoformat(date_to),
            aggregate=aggregate,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    return await snapshot_service.sku_daily(
        session,
        account_id=account_id,
        sku_id=sku_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        barcode=barcode,
        brand=brand,
        subject_name=subject_name,
        search=search,
        has_manual_cost=has_manual_cost,
        has_open_issues=has_open_issues,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        aggregate=aggregate,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get("/marts/business-daily", response_model=Page[MartBusinessDailyRead])
async def list_business_daily(
    account_id: int = Query(...),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await snapshot_service.business_daily(
        session,
        account_id=account_id,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        limit=limit,
        offset=offset,
    )


@router.get("/marts/stock-daily", response_model=Page[MartStockDailyRead])
async def list_stock_daily(
    account_id: int | None = Query(default=None),
    sku_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    barcode: str | None = Query(default=None),
    warehouse_name: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_stock_daily(
        session,
        account_id=account_id,
        sku_id=sku_id,
        nm_id=nm_id,
        barcode=barcode,
        warehouse_name=warehouse_name,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/marts/finance-reconciliation", response_model=Page[MartFinanceReconciliationRead]
)
async def list_finance_reconciliation(
    account_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    srid: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    only_diff: bool = Query(default=False),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_finance_reconciliation(
        session,
        account_id=account_id,
        nm_id=nm_id,
        srid=srid,
        barcode=barcode,
        status=status,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        only_diff=only_diff,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/marts/account-expense-daily", response_model=Page[MartAccountExpenseDailyRead]
)
async def list_account_expense_daily(
    account_id: int | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    return await service.list_account_expense_daily(
        session,
        account_id=account_id,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/marts/reconciliation-daily", response_model=Page[MartReconciliationDailyRead]
)
async def list_reconciliation_daily(
    account_id: int | None = Query(default=None),
    sku_id: int | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    vendor_code: str | None = Query(default=None),
    barcode: str | None = Query(default=None),
    search: str | None = Query(default=None),
    flag: str | None = Query(default=None),
    status_bucket: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    aggregate: str | None = Query(default=None, pattern="^(week|month)$"),
    sort_by: str | None = Query(default=None),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
):
    if account_id is None:
        return await service.list_reconciliation_daily(
            session,
            account_id=account_id,
            sku_id=sku_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            barcode=barcode,
            search=search,
            flag=flag,
            status_bucket=status_bucket,
            date_from=None if date_from is None else date.fromisoformat(date_from),
            date_to=None if date_to is None else date.fromisoformat(date_to),
            aggregate=aggregate,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
    return await snapshot_service.reconciliation_daily(
        session,
        account_id=account_id,
        sku_id=sku_id,
        nm_id=nm_id,
        vendor_code=vendor_code,
        barcode=barcode,
        search=search,
        flag=flag,
        status_bucket=status_bucket,
        date_from=None if date_from is None else date.fromisoformat(date_from),
        date_to=None if date_to is None else date.fromisoformat(date_to),
        aggregate=aggregate,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
