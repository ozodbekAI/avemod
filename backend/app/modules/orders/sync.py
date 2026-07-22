from __future__ import annotations

from datetime import timedelta

from app.core.parsing import parse_datetime
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.modules.orders.client import OrdersClient
from app.repositories.orders import OrderRepository


class OrdersSyncService(DomainSyncBase):
    domain = "orders"
    category = "statistics"
    MAX_PAGES_PER_RUN = 200
    PAGINATION_STUCK_WARNING_THRESHOLD = 79_000
    CURSOR_LOOKBACK_DAYS = 3

    def __init__(self) -> None:
        super().__init__()
        self.client = OrdersClient(self)
        self.repo = OrderRepository()

    @staticmethod
    def _update_max_last_change(current_max, raw_value):
        try:
            parsed = parse_datetime(raw_value)
        except ValueError:
            return current_max
        if parsed is None:
            return current_max
        if current_max is None or parsed > current_max:
            return parsed
        return current_max

    @classmethod
    def _cursor_start_with_lookback(cls, raw_value: str) -> str:
        try:
            parsed = parse_datetime(raw_value)
        except ValueError:
            return raw_value
        if parsed is None:
            return raw_value
        return (parsed - timedelta(days=cls.CURSOR_LOOKBACK_DAYS)).isoformat()

    async def _resolve_pagination_issues(self, session, *, account_id: int) -> None:
        await self.dq_service.resolve_issues(
            session,
            domain=self.domain,
            codes=["orders_pagination_limit_reached", "orders_pagination_stuck"],
            account_id=account_id,
        )

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        await self._resolve_pagination_issues(session, account_id=account.id)
        cursor = (
            None
            if force_full
            else await self._get_cursor(session, account_id=account.id)
        )
        if backfill_from is not None:
            start_dt = backfill_from.isoformat()
        elif cursor and cursor.cursor_value.get("lastChangeDate"):
            start_dt = self._cursor_start_with_lookback(
                cursor.cursor_value["lastChangeDate"]
            )
        else:
            start_dt = (utcnow() - timedelta(days=90)).isoformat()
        rows = []
        max_last_change = None
        page_cursor = start_dt
        pages_loaded = 0
        while True:
            payload = await self.client.fetch_orders(
                session, account_id=account.id, date_from=page_cursor
            )
            pages_loaded += 1
            if not payload:
                break
            for item in payload:
                parsed_last_change = parse_datetime(item.get("lastChangeDate"))
                rows.append(
                    {
                        "account_id": account.id,
                        "date": parse_datetime(item.get("date")),
                        "last_change_date": parsed_last_change,
                        "srid": item.get("srid"),
                        "g_number": item.get("gNumber"),
                        "order_id": item.get("orderId"),
                        "nm_id": item.get("nmId"),
                        "supplier_article": item.get("supplierArticle"),
                        "barcode": item.get("barcode"),
                        "warehouse_name": item.get("warehouseName"),
                        "warehouse_type": item.get("warehouseType"),
                        "region_name": item.get("regionName"),
                        "oblast_okrug_name": item.get("oblastOkrugName"),
                        "country_name": item.get("countryName"),
                        "total_price": item.get("totalPrice"),
                        "discount_percent": item.get("discountPercent"),
                        "spp": item.get("spp"),
                        "finished_price": item.get("finishedPrice"),
                        "price_with_disc": item.get("priceWithDisc"),
                        "is_cancel": item.get("isCancel"),
                        "cancel_date": parse_datetime(item.get("cancelDate")),
                    }
                )
                max_last_change = self._update_max_last_change(
                    max_last_change, item.get("lastChangeDate")
                )
            if pages_loaded >= self.MAX_PAGES_PER_RUN:
                await self._open_issue(
                    session,
                    account_id=account.id,
                    code="orders_pagination_limit_reached",
                    message="Orders sync hit pagination safety limit before receiving an empty page",
                    severity="warning",
                    entity_key=f"account:{account.id}",
                    payload={"pagesLoaded": pages_loaded, "dateFrom": start_dt},
                )
                break
            last_row_last_change = parse_datetime(payload[-1].get("lastChangeDate"))
            if last_row_last_change is None:
                break
            next_page_cursor = last_row_last_change.isoformat()
            if next_page_cursor == page_cursor:
                if len(payload) >= self.PAGINATION_STUCK_WARNING_THRESHOLD:
                    await self._open_issue(
                        session,
                        account_id=account.id,
                        code="orders_pagination_stuck",
                        message="Orders sync pagination cursor stopped advancing near the WB response limit",
                        severity="warning",
                        entity_key=f"account:{account.id}",
                        payload={
                            "pagesLoaded": pages_loaded,
                            "dateFrom": page_cursor,
                            "rowsInPage": len(payload),
                        },
                    )
                break
            page_cursor = next_page_cursor
        await self.repo.upsert_many(session, rows, conflict_fields=["dedupe_key"])
        if max_last_change is not None:
            await self._set_cursor(
                session,
                account_id=account.id,
                cursor_value={"lastChangeDate": max_last_change.isoformat()},
            )
        return {"status": "completed", "rows": len(rows), "pagesLoaded": pages_loaded}
