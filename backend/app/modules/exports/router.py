from __future__ import annotations

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db_session
from app.models.auth import AuthUser
from app.models.data_quality import DataQualityIssue
from app.models.marts import MartFinanceReconciliation, MartSKUDaily, MartStockDaily
from app.models.product_cards import CoreSKU
from app.models.manual_costs import ManualCost
from app.services.auth import get_current_superuser, get_current_user, require_account_role, resolve_user_account
from app.services.exports import ExportService

router = APIRouter(tags=["exports"])
service = ExportService()
READ_ROLES = {"viewer", "operator", "manager", "admin"}


def _xlsx_response_bytes(filename: str, payload: bytes, *, cache_status: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(payload),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Mode": "long-running-download",
            "X-Export-Cache": cache_status,
        },
    )


def _excel_scalar(value: object) -> object:
    return service.excel_scalar(value)


@router.get("/export/profit-by-sku.xlsx")
async def export_profit_by_sku(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    await resolve_user_account(session, current_user, account_id=account_id, require_account=True)
    await require_account_role(session, current_user, account_id=account_id, allowed_roles=READ_ROLES)
    stmt = select(MartSKUDaily).where(MartSKUDaily.account_id == account_id).order_by(MartSKUDaily.stat_date.desc(), MartSKUDaily.nm_id.asc().nullslast())
    if date_from is not None:
        stmt = stmt.where(MartSKUDaily.stat_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(MartSKUDaily.stat_date <= date_to)
    rows = list((await session.execute(stmt)).scalars())
    payload, cache_status = await service.export_cached(
        session=session,
        export_type="profit_by_sku",
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        headers=[
            "date", "sku_id", "nm_id", "vendor_code", "barcode", "title", "revenue", "for_pay",
            "commission", "logistics", "storage", "acquiring_fee", "ad_spend", "cogs",
            "profit_after_ads", "margin_percent", "roi_percent", "drr_percent", "has_real_manual_cost",
            "has_placeholder_cost", "business_trusted",
        ],
        rows=(
            (
                row.stat_date, row.sku_id, row.nm_id, row.vendor_code, row.barcode, row.title,
                row.final_revenue, row.final_for_pay, row.commission, row.logistics, row.storage,
                row.acquiring_fee, row.ad_spend, row.estimated_cogs, row.estimated_profit_after_ads,
                row.margin_percent, row.roi_percent, row.drr_percent, row.has_real_manual_cost,
                row.has_placeholder_cost, row.business_trusted,
            )
            for row in rows
        ),
        data_version_hash=await service.profit_by_sku_version_hash(session, account_id=account_id, date_from=date_from, date_to=date_to),
    )
    return _xlsx_response_bytes("profit_by_sku.xlsx", payload, cache_status=cache_status)


@router.get("/export/data-quality.xlsx")
async def export_data_quality(
    account_id: int = Query(...),
    only_open: bool = Query(default=True),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    stmt = select(DataQualityIssue).where(DataQualityIssue.account_id == account_id).order_by(DataQualityIssue.detected_at.desc())
    if only_open:
        stmt = stmt.where(DataQualityIssue.resolved_at.is_(None))
    rows = list((await session.execute(stmt)).scalars())
    payload, cache_status = await service.export_cached(
        session=session,
        export_type="data_quality",
        account_id=account_id,
        date_from=None,
        date_to=None,
        headers=["id", "domain", "code", "severity", "sku_id", "nm_id", "entity_key", "source_table", "message", "detected_at", "resolved_at"],
        rows=(
            tuple(
                _excel_scalar(value)
                for value in (
                    row.id,
                    row.domain,
                    row.code,
                    row.severity,
                    row.sku_id,
                    row.nm_id,
                    row.entity_key,
                    row.source_table,
                    row.message,
                    row.detected_at,
                    row.resolved_at,
                )
            )
            for row in rows
        ),
        data_version_hash=await service.data_quality_version_hash(session, account_id=account_id, only_open=only_open),
        extra_key=f"only_open={int(only_open)}",
    )
    return _xlsx_response_bytes("data_quality.xlsx", payload, cache_status=cache_status)


@router.get("/export/reconciliation.xlsx")
async def export_reconciliation(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    stmt = select(MartFinanceReconciliation).where(MartFinanceReconciliation.account_id == account_id).order_by(MartFinanceReconciliation.stat_date.desc())
    if date_from is not None:
        stmt = stmt.where(MartFinanceReconciliation.stat_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(MartFinanceReconciliation.stat_date <= date_to)
    rows = list((await session.execute(stmt)).scalars())
    payload, cache_status = await service.export_cached(
        session=session,
        export_type="reconciliation",
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        headers=["date", "srid", "sku_id", "nm_id", "barcode", "status", "sale_revenue", "finance_revenue", "revenue_delta", "sale_for_pay", "finance_for_pay", "for_pay_delta"],
        rows=((row.stat_date, row.srid, row.sku_id, row.nm_id, row.barcode, row.status, row.sale_revenue, row.finance_revenue, row.revenue_delta, row.sale_for_pay, row.finance_for_pay, row.for_pay_delta) for row in rows),
        data_version_hash=await service.reconciliation_version_hash(session, account_id=account_id, date_from=date_from, date_to=date_to),
    )
    return _xlsx_response_bytes("reconciliation.xlsx", payload, cache_status=cache_status)


@router.get("/export/stock.xlsx")
async def export_stock(
    account_id: int = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    nm_id: int | None = Query(default=None),
    current_user: AuthUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    await resolve_user_account(session, current_user, account_id=account_id, require_account=True)
    await require_account_role(session, current_user, account_id=account_id, allowed_roles=READ_ROLES)
    stmt = select(MartStockDaily).where(MartStockDaily.account_id == account_id).order_by(MartStockDaily.stat_date.desc(), MartStockDaily.nm_id.asc().nullslast())
    if date_from is not None:
        stmt = stmt.where(MartStockDaily.stat_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(MartStockDaily.stat_date <= date_to)
    if nm_id is not None:
        stmt = stmt.where(MartStockDaily.nm_id == nm_id)
    rows = list((await session.execute(stmt)).scalars())
    payload, cache_status = await service.export_cached(
        session=session,
        export_type="stock",
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        headers=["date", "sku_id", "nm_id", "barcode", "warehouse", "qty", "sales_7d", "sales_14d", "sales_30d", "avg_sales_per_day_30d", "days_of_stock", "turnover_rate", "out_of_stock_risk", "dead_stock"],
        rows=((row.stat_date, row.sku_id, row.nm_id, row.barcode, row.warehouse_name, row.quantity, row.sales_7d, row.sales_14d, row.sales_30d, row.avg_sales_per_day_30d, row.days_of_stock, row.turnover_rate, row.is_out_of_stock_risk, row.is_dead_stock) for row in rows),
        data_version_hash=await service.stock_version_hash(session, account_id=account_id, date_from=date_from, date_to=date_to),
        extra_key=f"nm_id={nm_id or ''}",
    )
    filename = f"stock_{nm_id}.xlsx" if nm_id is not None else "stock.xlsx"
    return _xlsx_response_bytes(filename, payload, cache_status=cache_status)


@router.get("/export/missing-costs.xlsx")
async def export_missing_costs(
    account_id: int = Query(...),
    _: AuthUser = Depends(get_current_superuser),
    session: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    has_active_cost = sa.exists(
        select(ManualCost.id).where(
            ManualCost.account_id == CoreSKU.account_id,
            ManualCost.sku_id == CoreSKU.id,
            ManualCost.is_business_trusted.is_(True),
            ManualCost.is_placeholder.is_(False),
        )
    )
    stmt = (
        select(CoreSKU)
        .where(CoreSKU.account_id == account_id, CoreSKU.is_active.is_(True), ~has_active_cost)
        .order_by(CoreSKU.vendor_code.asc().nullslast(), CoreSKU.nm_id.asc().nullslast())
    )
    rows = list((await session.execute(stmt)).scalars())
    payload, cache_status = await service.export_cached(
        session=session,
        export_type="missing_costs",
        account_id=account_id,
        date_from=None,
        date_to=None,
        headers=["sku_id", "nm_id", "vendor_code", "barcode", "tech_size", "title", "brand", "subject_name"],
        rows=((row.id, row.nm_id, row.vendor_code, row.barcode, row.tech_size, row.title, row.brand, row.subject_name) for row in rows),
        data_version_hash=await service.missing_costs_version_hash(session, account_id=account_id),
    )
    return _xlsx_response_bytes("missing_costs.xlsx", payload, cache_status=cache_status)
