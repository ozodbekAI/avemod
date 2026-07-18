from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.finance import (
    WBAcquiringReport,
    WBAcquiringReportRow,
    WBBalanceSnapshot,
    WBRealizationReport,
    WBRealizationReportRow,
)


class RealizationReportRepository(SQLAlchemyRepository[WBRealizationReport]):
    def __init__(self) -> None:
        super().__init__(WBRealizationReport)

    async def list_filtered(
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
        sort_map = {
            "create_date": WBRealizationReport.create_date,
            "report_id": WBRealizationReport.report_id,
            "report_name": WBRealizationReport.report_name,
            "date_from": WBRealizationReport.date_from,
            "date_to": WBRealizationReport.date_to,
        }
        sort_column = sort_map.get(sort_by or "", WBRealizationReport.create_date)
        stmt = select(WBRealizationReport).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBRealizationReport.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBRealizationReport.account_id == account_id)
        if report_id is not None:
            stmt = stmt.where(WBRealizationReport.report_id == report_id)
        if report_name is not None:
            stmt = stmt.where(WBRealizationReport.report_name.ilike(f"%{report_name}%"))
        if date_from is not None:
            stmt = stmt.where(
                (WBRealizationReport.date_to.is_(None))
                | (WBRealizationReport.date_to >= date_from)
            )
        if date_to is not None:
            stmt = stmt.where(
                (WBRealizationReport.date_from.is_(None))
                | (WBRealizationReport.date_from <= date_to)
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class RealizationReportRowRepository(SQLAlchemyRepository[WBRealizationReportRow]):
    def __init__(self) -> None:
        super().__init__(WBRealizationReportRow)

    def _build_filtered_stmt(
        self,
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
    ):
        stmt = select(WBRealizationReportRow)
        if account_id is not None:
            stmt = stmt.where(WBRealizationReportRow.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBRealizationReportRow.nm_id == nm_id)
        if srid is not None:
            stmt = stmt.where(WBRealizationReportRow.srid == srid)
        if vendor_code is not None:
            stmt = stmt.where(
                WBRealizationReportRow.vendor_code.ilike(f"%{vendor_code}%")
            )
        if barcode is not None:
            stmt = stmt.where(WBRealizationReportRow.barcode.ilike(f"%{barcode}%"))

        doc_type_filters = [value for value in (doc_type_names or []) if value]
        if doc_type_name:
            doc_type_filters.append(doc_type_name)
        if doc_type_filters:
            stmt = stmt.where(
                or_(
                    *[
                        WBRealizationReportRow.doc_type_name.ilike(f"%{value}%")
                        for value in doc_type_filters
                    ]
                )
            )

        if operation_type is not None:
            stmt = stmt.where(
                WBRealizationReportRow.operation_type.ilike(f"%{operation_type}%")
            )

        seller_oper_filters = [value for value in (seller_oper_names or []) if value]
        if seller_oper_name:
            seller_oper_filters.append(seller_oper_name)
        if seller_oper_filters:
            stmt = stmt.where(
                or_(
                    *[
                        WBRealizationReportRow.seller_oper_name.ilike(f"%{value}%")
                        for value in seller_oper_filters
                    ]
                )
            )

        office_filters = [value for value in (office_names or []) if value]
        if office_name:
            office_filters.append(office_name)
        if office_filters:
            stmt = stmt.where(
                or_(
                    *[
                        WBRealizationReportRow.office_name.ilike(f"%{value}%")
                        for value in office_filters
                    ]
                )
            )

        if report_id is not None:
            stmt = stmt.where(WBRealizationReportRow.report_id == report_id)
        if is_reconcilable is not None:
            stmt = stmt.where(
                WBRealizationReportRow.is_reconcilable.is_(is_reconcilable)
            )
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBRealizationReportRow.srid.ilike(pattern),
                    WBRealizationReportRow.vendor_code.ilike(pattern),
                    WBRealizationReportRow.barcode.ilike(pattern),
                    WBRealizationReportRow.title.ilike(pattern),
                    WBRealizationReportRow.brand.ilike(pattern),
                    WBRealizationReportRow.subject_name.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(WBRealizationReportRow.rr_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBRealizationReportRow.rr_date <= date_to)
        if min_amount is not None:
            stmt = stmt.where(
                func.coalesce(WBRealizationReportRow.retail_amount, 0) >= min_amount
            )
        if max_amount is not None:
            stmt = stmt.where(
                func.coalesce(WBRealizationReportRow.retail_amount, 0) <= max_amount
            )
        return stmt

    async def list_filtered(
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
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        sort_map = {
            "rr_date": WBRealizationReportRow.rr_date,
            "nm_id": WBRealizationReportRow.nm_id,
            "srid": WBRealizationReportRow.srid,
            "vendor_code": WBRealizationReportRow.vendor_code,
            "barcode": WBRealizationReportRow.barcode,
            "report_id": WBRealizationReportRow.report_id,
            "doc_type_name": WBRealizationReportRow.doc_type_name,
            "operation_type": WBRealizationReportRow.operation_type,
            "retail_amount": WBRealizationReportRow.retail_amount,
            "for_pay": WBRealizationReportRow.for_pay,
        }
        sort_column = sort_map.get(sort_by or "", WBRealizationReportRow.rr_date)
        stmt = self._build_filtered_stmt(
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
        ).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBRealizationReportRow.id.desc(),
        )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)

    async def summary(
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
    ) -> dict[str, object]:
        base = self._build_filtered_stmt(
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
        ).subquery()
        row = (
            (
                await session.execute(
                    select(
                        func.count().label("rows_count"),
                        func.coalesce(func.sum(base.c.retail_amount), 0).label(
                            "sum_retail_amount"
                        ),
                        func.coalesce(func.sum(base.c.for_pay), 0).label("sum_for_pay"),
                        func.coalesce(
                            func.sum(
                                base.c.delivery_service + base.c.rebill_logistic_cost
                            ),
                            0,
                        ).label("sum_logistics"),
                        func.coalesce(func.sum(base.c.paid_storage), 0).label(
                            "sum_storage"
                        ),
                        func.coalesce(func.sum(base.c.paid_acceptance), 0).label(
                            "sum_paid_acceptance"
                        ),
                        func.coalesce(func.sum(base.c.penalty), 0).label("sum_penalty"),
                        func.coalesce(func.sum(base.c.deduction), 0).label(
                            "sum_deduction"
                        ),
                        func.coalesce(func.sum(base.c.additional_payment), 0).label(
                            "sum_additional_payment"
                        ),
                    )
                )
            )
            .mappings()
            .one()
        )
        return dict(row)


class AcquiringReportRepository(SQLAlchemyRepository[WBAcquiringReport]):
    def __init__(self) -> None:
        super().__init__(WBAcquiringReport)


class AcquiringReportRowRepository(SQLAlchemyRepository[WBAcquiringReportRow]):
    def __init__(self) -> None:
        super().__init__(WBAcquiringReportRow)

    async def list_for_reports(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        report_ids: list[int],
    ) -> list[WBAcquiringReportRow]:
        if not report_ids:
            return []
        return list(
            (
                await session.execute(
                    select(WBAcquiringReportRow).where(
                        WBAcquiringReportRow.account_id == account_id,
                        WBAcquiringReportRow.report_id.in_(report_ids),
                    )
                )
            ).scalars()
        )


class BalanceSnapshotRepository(SQLAlchemyRepository[WBBalanceSnapshot]):
    def __init__(self) -> None:
        super().__init__(WBBalanceSnapshot)

    async def list_filtered(
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
        sort_map = {
            "snapshot_at": WBBalanceSnapshot.snapshot_at,
            "currency": WBBalanceSnapshot.currency,
            "current": WBBalanceSnapshot.current,
            "for_withdraw": WBBalanceSnapshot.for_withdraw,
        }
        sort_column = sort_map.get(sort_by or "", WBBalanceSnapshot.snapshot_at)
        stmt = select(WBBalanceSnapshot).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBBalanceSnapshot.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBBalanceSnapshot.account_id == account_id)
        if currency is not None:
            stmt = stmt.where(WBBalanceSnapshot.currency == currency)
        if date_from is not None:
            stmt = stmt.where(
                WBBalanceSnapshot.snapshot_at >= datetime.combine(date_from, time.min)
            )
        if date_to is not None:
            stmt = stmt.where(
                WBBalanceSnapshot.snapshot_at <= datetime.combine(date_to, time.max)
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)
