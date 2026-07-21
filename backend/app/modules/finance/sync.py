from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.parsing import parse_date, parse_datetime
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.modules.finance.client import FinanceClient
from app.models.finance import (
    WBAcquiringReport,
    WBRealizationReport,
    WBBalanceSnapshot,
)
from app.repositories.finance import (
    AcquiringReportRepository,
    AcquiringReportRowRepository,
    BalanceSnapshotRepository,
    RealizationReportRepository,
    RealizationReportRowRepository,
)


class FinanceSyncService(DomainSyncBase):
    domain = "finance"
    category = "finance"
    REQUEST_INTERVAL_SECONDS = 61
    DETAIL_PAGE_LIMIT = get_settings().finance_detail_page_limit
    MAX_DETAIL_PAGES_PER_RUN = get_settings().finance_detail_pages_per_run
    DETAILS_CURSOR_KEY = "realization_details"
    ACQUIRING_CURSOR_KEY = "acquiring_details"
    REPORT_FK_MAP_CHUNK_SIZE = 1000

    def __init__(self) -> None:
        super().__init__()
        self.client = FinanceClient(self)
        self.reports = RealizationReportRepository()
        self.rows = RealizationReportRowRepository()
        self.acquiring = AcquiringReportRepository()
        self.acquiring_rows = AcquiringReportRowRepository()
        self.balances = BalanceSnapshotRepository()

    @staticmethod
    def _as_mapping(payload: Any) -> dict[str, Any]:
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _as_list(payload: Any, *keys: str) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _classify_finance_row_payload(item: dict[str, Any]) -> dict[str, Any]:
        doc_type_name = item.get("docTypeName") or item.get("doc_type_name")
        normalized = (doc_type_name or "").strip().lower()
        operation_type = "expense"
        is_sale = False
        is_return = False
        if normalized in {"продажа", "sale"}:
            operation_type = "sale"
            is_sale = True
        elif normalized in {"возврат", "return"}:
            operation_type = "return"
            is_return = True
        return {
            "doc_type_name": doc_type_name,
            "operation_type": operation_type,
            "is_sale_operation": is_sale,
            "is_return_operation": is_return,
            "is_expense_operation": not (is_sale or is_return),
            "is_reconcilable": is_sale or is_return,
        }

    @staticmethod
    def _normalize_realization_rows(
        account_id: int,
        rows: list[dict[str, Any]],
        report_fk_map: dict[int, int] | None = None,
    ) -> list[dict[str, Any]]:
        normalized_rows: list[dict[str, Any]] = []
        for sale in rows:
            row_id = sale.get("rrdId") or sale.get("rrd_id") or sale.get("id")
            if row_id is None:
                continue
            report_id = sale.get("reportId")
            normalized_rows.append(
                {
                    "account_id": account_id,
                    "report_id_fk": report_fk_map.get(int(report_id))
                    if report_fk_map and report_id is not None
                    else None,
                    "rrd_id": row_id,
                    "report_id": report_id,
                    "rr_date": parse_date(sale.get("rrDate") or sale.get("rr_dt")),
                    "sale_dt": parse_datetime(
                        sale.get("saleDt") or sale.get("sale_dt")
                    ),
                    **FinanceSyncService._classify_finance_row_payload(sale),
                    "order_id": sale.get("orderId"),
                    "srid": sale.get("srid"),
                    "shk_id": sale.get("shkId"),
                    "nm_id": sale.get("nmId") or sale.get("nm_id"),
                    "vendor_code": sale.get("vendorCode") or sale.get("saName"),
                    "barcode": sale.get("barcode") or sale.get("sku"),
                    "title": sale.get("title"),
                    "brand": sale.get("brand"),
                    "subject_name": sale.get("subjectName") or sale.get("subject_name"),
                    "office_name": sale.get("officeName") or sale.get("office_name"),
                    "seller_oper_name": sale.get("sellerOperName")
                    or sale.get("seller_oper_name"),
                    "bonus_type_name": sale.get("bonusTypeName")
                    or sale.get("bonus_type_name"),
                    "quantity": sale.get("quantity"),
                    "retail_amount": sale.get("retailAmount"),
                    "retail_price": sale.get("retailPrice"),
                    "retail_price_with_disc": sale.get("retailPriceWithDisc"),
                    "delivery_amount": sale.get("deliveryAmount"),
                    "delivery_service": sale.get("deliveryService"),
                    "paid_acceptance": sale.get("paidAcceptance"),
                    "additional_payment": sale.get("additionalPayment"),
                    "rebill_logistic_cost": sale.get("rebillLogisticCost"),
                    "return_amount": sale.get("returnAmount"),
                    "ppvz_sales_commission": sale.get("ppvzSalesCommission"),
                    "acquiring_fee": sale.get("acquiringFee"),
                    "paid_storage": sale.get("paidStorage"),
                    "penalty": sale.get("penalty"),
                    "deduction": sale.get("deduction"),
                    "for_pay": sale.get("forPay") or sale.get("ppvz_for_pay"),
                    "currency": sale.get("currency"),
                    "payload": sale,
                }
            )
        return normalized_rows

    async def _report_fk_map(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        report_ids: list[int],
    ) -> dict[int, int]:
        del report_ids
        rows = list(
            (
                await session.execute(
                    select(WBRealizationReport).where(
                        WBRealizationReport.account_id == account_id,
                    )
                )
            ).scalars()
        )
        return {int(row.report_id): row.id for row in rows if row.report_id is not None}

    async def _acquiring_report_fk_map(
        self,
        session,
        *,
        account_id: int,
        report_ids: list[int],
    ) -> dict[int, int]:
        del report_ids
        rows = list(
            (
                await session.execute(
                    select(WBAcquiringReport).where(
                        WBAcquiringReport.account_id == account_id,
                    )
                )
            ).scalars()
        )
        return {int(row.report_id): row.id for row in rows if row.report_id is not None}

    async def _pause(self) -> None:
        await asyncio.sleep(self.REQUEST_INTERVAL_SECONDS)

    @staticmethod
    def _is_rate_limited(exc: Exception) -> bool:
        return "429" in str(exc) and "Too Many Requests" in str(exc)

    @classmethod
    def _classify_acquiring_sync_exception(cls, exc: Exception) -> tuple[str, str, str]:
        if cls._is_rate_limited(exc):
            return ("rate_limited", "acquiring_sync_rate_limited", "info")
        if "404" in str(exc):
            return ("unsupported_by_wb", "acquiring_sync_unsupported", "info")
        return ("failed_internal", "acquiring_sync_failed", "warning")

    async def _sync_balance_if_needed(self, session, *, account_id: int) -> bool:
        today = utcnow().date()
        existing = (
            await session.execute(
                select(WBBalanceSnapshot.id)
                .where(
                    WBBalanceSnapshot.account_id == account_id,
                    WBBalanceSnapshot.snapshot_at
                    >= parse_datetime(f"{today.isoformat()}T00:00:00+00:00"),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False
        balance_payload = await self.client.balance(session, account_id=account_id)
        balance_data = self._as_mapping(balance_payload)
        session.add(
            WBBalanceSnapshot(
                account_id=account_id,
                snapshot_at=utcnow(),
                currency=balance_data.get("currency"),
                current=balance_data.get("current"),
                for_withdraw=balance_data.get("for_withdraw")
                or balance_data.get("forWithdraw"),
                payload=balance_payload,
            )
        )
        return True

    async def _upsert_reports_from_rows(
        self, session, *, account_id: int, rows: list[dict[str, Any]]
    ) -> int:
        report_rows: dict[int, dict[str, Any]] = {}
        for item in rows:
            report_id = item.get("reportId") or item.get("id")
            if report_id is None:
                continue
            report_rows[int(report_id)] = {
                "account_id": account_id,
                "report_id": report_id,
                "report_name": item.get("name") or item.get("title"),
                "period": str(item.get("period") or item.get("reportType"))
                if (item.get("period") or item.get("reportType")) is not None
                else None,
                "date_from": parse_date(item.get("dateFrom")),
                "date_to": parse_date(item.get("dateTo")),
                "create_date": parse_date(item.get("createDate")),
                "currency": item.get("currency"),
                "payload": {
                    "reportId": report_id,
                    "dateFrom": item.get("dateFrom"),
                    "dateTo": item.get("dateTo"),
                    "createDate": item.get("createDate"),
                    "currency": item.get("currency"),
                    "reportType": item.get("reportType"),
                },
            }
        await self.reports.upsert_many(
            session,
            list(report_rows.values()),
            conflict_fields=["account_id", "report_id"],
        )
        return len(report_rows)

    async def _fetch_realization_details(
        self,
        session,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        rrd_id = 0
        while True:
            payload = await self.client.sales_reports_detailed(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                rrd_id=rrd_id,
                limit=self.DETAIL_PAGE_LIMIT,
            )
            rows = self._as_list(payload, "report", "reports", "data")
            if not rows:
                break
            typed_rows = [row for row in rows if isinstance(row, dict)]
            if not typed_rows:
                break
            all_rows.extend(typed_rows)
            last_rrd_id = typed_rows[-1].get("rrdId") or typed_rows[-1].get("rrd_id")
            if len(typed_rows) < self.DETAIL_PAGE_LIMIT or last_rrd_id in (None, rrd_id):
                break
            rrd_id = int(last_rrd_id)
            await self._pause()
        return all_rows

    async def _fetch_acquiring_details(
        self,
        session,
        *,
        account_id: int,
        date_from: str,
        date_to: str,
    ) -> list[dict[str, Any]]:
        all_rows: list[dict[str, Any]] = []
        rrd_id = 0
        page_count = 0
        while True:
            payload = await self.client.acquiring_reports_detailed(
                session,
                account_id=account_id,
                date_from=date_from,
                date_to=date_to,
                rrd_id=rrd_id,
                limit=self.DETAIL_PAGE_LIMIT,
            )
            rows = self._as_list(payload, "report", "reports", "data")
            if not rows:
                break
            typed_rows = [row for row in rows if isinstance(row, dict)]
            if not typed_rows:
                break
            all_rows.extend(typed_rows)
            page_count += 1
            last_rrd_id = typed_rows[-1].get("rrdId") or typed_rows[-1].get("rrd_id")
            await self._progress(
                stage="finance_acquiring_details",
                progress_percent=min(94, 90 + page_count),
                rowsLoaded=len(all_rows),
                nextRrdId=last_rrd_id,
            )
            if len(typed_rows) < self.DETAIL_PAGE_LIMIT or last_rrd_id in (None, rrd_id):
                break
            rrd_id = int(last_rrd_id)
            await self._progress(
                stage="finance_rate_limit_wait",
                progress_percent=min(94, 90 + page_count),
                waitSeconds=self.REQUEST_INTERVAL_SECONDS,
                nextStage="finance_acquiring_details",
            )
            await self._pause()
        return all_rows

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        if backfill_from:
            date_from = backfill_from.isoformat()
            date_to = (backfill_to or utcnow().date()).isoformat()
        else:
            date_from = (
                utcnow().date() - timedelta(days=365 if force_full else 30)
            ).isoformat()
            date_to = utcnow().date().isoformat()

        await self._progress(
            stage="finance_prepare",
            progress_percent=10,
            dateFrom=date_from,
            dateTo=date_to,
            forceFull=force_full,
        )
        details_cursor = await self._get_cursor(
            session,
            account_id=account.id,
            cursor_key=self.DETAILS_CURSOR_KEY,
        )
        acquiring_cursor = await self._get_cursor(
            session,
            account_id=account.id,
            cursor_key=self.ACQUIRING_CURSOR_KEY,
        )
        details_state = (
            details_cursor.cursor_value if details_cursor is not None else {}
        )
        acquiring_state = (
            acquiring_cursor.cursor_value if acquiring_cursor is not None else {}
        )
        if (
            force_full
            or details_state.get("dateFrom") != date_from
            or details_state.get("dateTo") != date_to
        ):
            details_state = {
                "dateFrom": date_from,
                "dateTo": date_to,
                "rrdId": 0,
                "pagesLoaded": 0,
                "rowsLoaded": 0,
                "done": False,
            }
        if (
            force_full
            or acquiring_state.get("dateFrom") != date_from
            or acquiring_state.get("dateTo") != date_to
        ):
            acquiring_state = {
                "dateFrom": date_from,
                "dateTo": date_to,
                "pagesLoaded": 0,
                "rowsLoaded": 0,
                "done": False,
            }

        await self._progress(stage="finance_balance", progress_percent=15)
        balance_synced = await self._sync_balance_if_needed(
            session, account_id=account.id
        )
        await self._progress(
            stage="finance_balance_done",
            progress_percent=20,
            balanceSynced=balance_synced,
        )
        if balance_synced:
            await self._progress(
                stage="finance_rate_limit_wait",
                progress_percent=20,
                waitSeconds=self.REQUEST_INTERVAL_SECONDS,
                nextStage="finance_reports",
            )
            await self._pause()

        report_rows_count = 0
        acquiring_rows_total = 0
        try:
            await self._progress(stage="finance_reports", progress_percent=30)
            reports_payload = await self.client.sales_reports_list(
                session, account_id=account.id, date_from=date_from, date_to=date_to
            )
            report_items = self._as_list(reports_payload, "reports", "data")
            report_rows = [
                {
                    "account_id": account.id,
                    "report_id": item.get("reportId") or item.get("id"),
                    "report_name": item.get("name") or item.get("title"),
                    "period": item.get("period"),
                    "date_from": parse_date(item.get("dateFrom")),
                    "date_to": parse_date(item.get("dateTo")),
                    "create_date": parse_date(item.get("createDate")),
                    "currency": item.get("currency"),
                    "payload": item,
                }
                for item in report_items
                if isinstance(item, dict)
            ]
            report_rows_count = len(report_rows)
            await self.reports.upsert_many(
                session, report_rows, conflict_fields=["account_id", "report_id"]
            )
            await self._progress(
                stage="finance_reports_done",
                progress_percent=40,
                reportsListed=report_rows_count,
            )
            await self._progress(
                stage="finance_rate_limit_wait",
                progress_percent=40,
                waitSeconds=self.REQUEST_INTERVAL_SECONDS,
                nextStage="finance_details",
            )
            await self._pause()
        except Exception as exc:
            if self._is_rate_limited(exc):
                await self._progress(
                    stage="finance_rate_limited",
                    progress_percent=45,
                    reason="finance_meta_rate_limited",
                )
                await self._set_cursor(
                    session,
                    account_id=account.id,
                    cursor_key=self.DETAILS_CURSOR_KEY,
                    cursor_value=details_state,
                    status="rate_limited",
                )
                return {
                    "status": "partial",
                    "reports": 0,
                    "reportRows": 0,
                    "reportsListed": 0,
                    "detailsPagesLoaded": details_state.get("pagesLoaded", 0),
                    "detailsPending": 1,
                    "nextRrdId": details_state.get("rrdId", 0),
                    "reason": "finance_meta_rate_limited",
                }
            raise

        realization_rows_total = 0
        pages_loaded = 0
        current_rrd_id = int(details_state.get("rrdId", 0) or 0)
        details_done = bool(details_state.get("done"))
        if not details_done:
            await self._progress(
                stage="finance_details",
                progress_percent=45,
                nextRrdId=current_rrd_id,
                detailsPagesLoaded=details_state.get("pagesLoaded", 0),
                detailsRowsLoaded=details_state.get("rowsLoaded", 0),
            )
            while pages_loaded < self.MAX_DETAIL_PAGES_PER_RUN:
                try:
                    payload = await self.client.sales_reports_detailed(
                        session,
                        account_id=account.id,
                        date_from=date_from,
                        date_to=date_to,
                        rrd_id=current_rrd_id,
                        limit=self.DETAIL_PAGE_LIMIT,
                    )
                except Exception as exc:
                    if self._is_rate_limited(exc):
                        await self._progress(
                            stage="finance_rate_limited",
                            progress_percent=55,
                            reason="finance_details_rate_limited",
                            nextRrdId=current_rrd_id,
                        )
                        await self._set_cursor(
                            session,
                            account_id=account.id,
                            cursor_key=self.DETAILS_CURSOR_KEY,
                            cursor_value={
                                **details_state,
                                "rrdId": current_rrd_id,
                                "done": False,
                            },
                            status="rate_limited",
                        )
                        return {
                            "status": "partial",
                            "reports": report_rows_count,
                            "reportRows": realization_rows_total,
                            "reportsListed": report_rows_count,
                            "detailsPagesLoaded": details_state.get("pagesLoaded", 0),
                            "detailsPending": 1,
                            "nextRrdId": current_rrd_id,
                            "reason": "finance_details_rate_limited",
                        }
                    raise

                typed_rows = [
                    row
                    for row in self._as_list(payload, "report", "reports", "data")
                    if isinstance(row, dict)
                ]
                if not typed_rows:
                    details_done = True
                    await self._progress(
                        stage="finance_details_done",
                        progress_percent=80,
                        detailsPagesLoaded=details_state.get("pagesLoaded", 0),
                        detailsRowsLoaded=details_state.get("rowsLoaded", 0),
                        nextRrdId=current_rrd_id,
                    )
                    break
                await self._upsert_reports_from_rows(
                    session, account_id=account.id, rows=typed_rows
                )
                report_fk_map = await self._report_fk_map(
                    session,
                    account_id=account.id,
                    report_ids=[
                        int(row["reportId"])
                        for row in typed_rows
                        if row.get("reportId") is not None
                    ],
                )
                normalized = self._normalize_realization_rows(
                    account.id,
                    typed_rows,
                    report_fk_map=report_fk_map,
                )
                await self.rows.upsert_many(
                    session, normalized, conflict_fields=["account_id", "rrd_id"]
                )
                realization_rows_total += len(normalized)
                pages_loaded += 1
                details_state["pagesLoaded"] = (
                    int(details_state.get("pagesLoaded", 0) or 0) + 1
                )
                details_state["rowsLoaded"] = int(
                    details_state.get("rowsLoaded", 0) or 0
                ) + len(normalized)
                last_rrd_id = typed_rows[-1].get("rrdId") or typed_rows[-1].get(
                    "rrd_id"
                )
                if len(typed_rows) < self.DETAIL_PAGE_LIMIT or last_rrd_id in (
                    None,
                    current_rrd_id,
                ):
                    current_rrd_id = int(last_rrd_id or current_rrd_id)
                    details_done = True
                    await self._progress(
                        stage="finance_details_done",
                        progress_percent=80,
                        detailsPagesLoaded=details_state.get("pagesLoaded", 0),
                        detailsRowsLoaded=details_state.get("rowsLoaded", 0),
                        nextRrdId=current_rrd_id,
                    )
                    break
                current_rrd_id = int(last_rrd_id)
                detail_progress = min(
                    75,
                    45
                    + int((pages_loaded / max(1, self.MAX_DETAIL_PAGES_PER_RUN)) * 30),
                )
                await self._progress(
                    stage="finance_details",
                    progress_percent=detail_progress,
                    detailsPagesLoaded=details_state.get("pagesLoaded", 0),
                    detailsRowsLoaded=details_state.get("rowsLoaded", 0),
                    nextRrdId=current_rrd_id,
                )
                await self._set_cursor(
                    session,
                    account_id=account.id,
                    cursor_key=self.DETAILS_CURSOR_KEY,
                    cursor_value={
                        **details_state,
                        "dateFrom": date_from,
                        "dateTo": date_to,
                        "rrdId": current_rrd_id,
                        "done": False,
                    },
                    status="running",
                )
                if pages_loaded < self.MAX_DETAIL_PAGES_PER_RUN:
                    await self._progress(
                        stage="finance_rate_limit_wait",
                        progress_percent=detail_progress,
                        waitSeconds=self.REQUEST_INTERVAL_SECONDS,
                        nextStage="finance_details",
                    )
                    await self._pause()
        elif details_done:
            await self._progress(
                stage="finance_details_done",
                progress_percent=80,
                detailsPagesLoaded=details_state.get("pagesLoaded", 0),
                detailsRowsLoaded=details_state.get("rowsLoaded", 0),
                nextRrdId=current_rrd_id,
            )

        acquiring_status = "unsupported_by_wb"
        mart_refresh_status = "skipped"
        mart_refresh_result: dict[str, Any] = {}
        if details_done and get_settings().finance_refresh_marts_after_sync:
            try:
                await self._progress(
                    stage="finance_rate_limit_wait",
                    progress_percent=82,
                    waitSeconds=self.REQUEST_INTERVAL_SECONDS,
                    nextStage="finance_acquiring",
                )
                await self._pause()
                await self._progress(stage="finance_acquiring", progress_percent=85)
                acquiring_payload = await self.client.acquiring_reports_list(
                    session, account_id=account.id, date_from=date_from, date_to=date_to
                )
                acquiring_items = self._as_list(acquiring_payload, "reports", "data")
                acquiring_rows = [
                    {
                        "account_id": account.id,
                        "report_id": item.get("reportId") or item.get("id"),
                        "date_from": parse_date(item.get("dateFrom")),
                        "date_to": parse_date(item.get("dateTo")),
                        "create_date": parse_date(item.get("createDate")),
                        "currency": item.get("currency"),
                        "payload": item,
                    }
                    for item in acquiring_items
                    if isinstance(item, dict)
                ]
                await self.acquiring.upsert_many(
                    session, acquiring_rows, conflict_fields=["account_id", "report_id"]
                )

                await self._progress(
                    stage="finance_rate_limit_wait",
                    progress_percent=88,
                    waitSeconds=self.REQUEST_INTERVAL_SECONDS,
                    nextStage="finance_acquiring_details",
                    acquiringReportsListed=len(acquiring_rows),
                )
                await self._pause()
                await self._progress(
                    stage="finance_acquiring_details",
                    progress_percent=90,
                    acquiringReportsListed=len(acquiring_rows),
                )
                acquiring_detail_rows = await self._fetch_acquiring_details(
                    session,
                    account_id=account.id,
                    date_from=date_from,
                    date_to=date_to,
                )
                acquiring_fk_map = await self._acquiring_report_fk_map(
                    session,
                    account_id=account.id,
                    report_ids=[
                        int(item["reportId"])
                        for item in acquiring_detail_rows
                        if isinstance(item, dict) and item.get("reportId") is not None
                    ],
                )
                normalized_acquiring_rows = [
                    {
                        "account_id": account.id,
                        "report_id_fk": acquiring_fk_map.get(int(item["reportId"]))
                        if item.get("reportId") is not None
                        else None,
                        "report_id": item.get("reportId"),
                        "order_id": item.get("orderId"),
                        "srid": item.get("srid"),
                        "shk_id": item.get("shkId"),
                        "nm_id": item.get("nmId"),
                        "retail_amount": item.get("retailAmount"),
                        "acquiring_fee": item.get("acquiringFee"),
                        "currency": item.get("currency"),
                        "payload": item,
                    }
                    for item in acquiring_detail_rows
                    if isinstance(item, dict)
                ]
                await self.acquiring_rows.upsert_many(
                    session,
                    normalized_acquiring_rows,
                    conflict_fields=["dedupe_key"],
                )
                acquiring_rows_total = len(normalized_acquiring_rows)
                await self._progress(
                    stage="finance_acquiring_done",
                    progress_percent=95,
                    acquiringRows=acquiring_rows_total,
                )
                acquiring_state = {
                    "dateFrom": date_from,
                    "dateTo": date_to,
                    "pagesLoaded": 1 if acquiring_rows else 0,
                    "rowsLoaded": acquiring_rows_total,
                    "done": True,
                    "syncedAt": utcnow().isoformat(),
                }
                acquiring_status = "completed"
            except Exception as exc:
                acquiring_status, issue_code, issue_severity = (
                    self._classify_acquiring_sync_exception(exc)
                )
                await self._progress(
                    stage="finance_acquiring_failed",
                    progress_percent=95,
                    acquiringStatus=acquiring_status,
                    error=str(exc),
                )
                acquiring_state = {
                    "dateFrom": date_from,
                    "dateTo": date_to,
                    "pagesLoaded": 0,
                    "rowsLoaded": 0,
                    "done": False,
                    "lastError": str(exc),
                    "syncedAt": utcnow().isoformat(),
                }
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code=issue_code,
                    message=str(exc),
                    severity=issue_severity,
                )

        if details_done and get_settings().finance_refresh_marts_after_sync:
            try:
                await self._progress(
                    stage="finance_marts_refresh",
                    progress_percent=96,
                    dateFrom=date_from,
                    dateTo=date_to,
                )
                from app.services.marts import MartService

                mart_refresh_result = await MartService().refresh_account(
                    session,
                    account_id=account.id,
                    date_from=parse_date(date_from),
                    date_to=parse_date(date_to),
                )
                mart_refresh_status = "completed"
            except Exception as exc:
                mart_refresh_status = "failed"
                mart_refresh_result = {"error": str(exc)}
                await self._progress(
                    stage="finance_marts_refresh_failed",
                    progress_percent=96,
                    error=str(exc),
                )
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="finance_mart_refresh_failed",
                    message=f"Finance sync loaded WB rows, but mart refresh failed: {exc}",
                    severity="warning",
                )

        await self._progress(
            stage="finance_cursors",
            progress_percent=97 if details_done else 82,
            detailsDone=details_done,
            acquiringStatus=acquiring_status,
            martRefreshStatus=mart_refresh_status,
        )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={
                "dateFrom": date_from,
                "dateTo": date_to,
                "syncedAt": utcnow().isoformat(),
            },
        )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_key=self.DETAILS_CURSOR_KEY,
            cursor_value={
                **details_state,
                "dateFrom": date_from,
                "dateTo": date_to,
                "rrdId": current_rrd_id,
                "done": details_done,
                "syncedAt": utcnow().isoformat(),
            },
            status="completed" if details_done else "running",
        )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_key=self.ACQUIRING_CURSOR_KEY,
            cursor_value=acquiring_state,
            status=acquiring_status,
        )
        return {
            "status": "completed" if details_done else "partial",
            "reports": report_rows_count,
            "reportsListed": report_rows_count,
            "reportRows": realization_rows_total,
            "detailsPagesLoaded": details_state.get("pagesLoaded", 0),
            "detailsPending": 0 if details_done else 1,
            "nextRrdId": current_rrd_id,
            "detailsDone": details_done,
            "acquiringStatus": acquiring_status,
            "acquiringPagesLoaded": acquiring_state.get("pagesLoaded", 0),
            "acquiringRows": acquiring_rows_total,
            "acquiringPending": 0 if acquiring_state.get("done") else 1,
            "martRefreshStatus": mart_refresh_status,
            "martRefresh": mart_refresh_result,
        }
