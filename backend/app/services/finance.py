from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.finance import (
    BalanceSnapshotRepository,
    RealizationReportRepository,
    RealizationReportRowRepository,
)
from app.schemas.finance import FinanceReportRowsPage, FinanceReportRowsSummary


class FinanceService:
    def __init__(self) -> None:
        self.reports = RealizationReportRepository()
        self.rows = RealizationReportRowRepository()
        self.balances = BalanceSnapshotRepository()

    async def list_reports(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        report_id: int | None = None,
        report_name: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.reports.list_filtered(
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

    async def list_report_rows(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        nm_id=None,
        srid: str | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        doc_type_name: str | None = None,
        doc_type_names: list[str] | None = None,
        operation_type: str | None = None,
        seller_oper_name: str | None = None,
        seller_oper_names: list[str] | None = None,
        office_name: str | None = None,
        office_names: list[str] | None = None,
        report_id: int | None = None,
        is_reconcilable: bool | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        min_amount: float | None = None,
        max_amount: float | None = None,
        aggregate: bool = False,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        page = await self.rows.list_filtered(
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
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        summary = None
        if aggregate:
            summary_data = await self.rows.summary(
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
            )
            summary = FinanceReportRowsSummary(
                rows_count=int(summary_data["rows_count"]),
                sum_retail_amount=float(summary_data["sum_retail_amount"] or 0),
                sum_for_pay=float(summary_data["sum_for_pay"] or 0),
                sum_logistics=float(summary_data["sum_logistics"] or 0),
                sum_storage=float(summary_data["sum_storage"] or 0),
                sum_paid_acceptance=float(summary_data["sum_paid_acceptance"] or 0),
                sum_penalty=float(summary_data["sum_penalty"] or 0),
                sum_deduction=float(summary_data["sum_deduction"] or 0),
                sum_additional_payment=float(
                    summary_data["sum_additional_payment"] or 0
                ),
            )
        return FinanceReportRowsPage(
            total=page.total,
            limit=page.limit,
            offset=page.offset,
            items=list(page.items),
            summary=summary,
        )

    async def list_balances(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        currency: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        return await self.balances.list_filtered(
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
