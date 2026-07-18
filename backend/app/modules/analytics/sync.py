from __future__ import annotations

from datetime import timedelta

from sqlalchemy import delete, select

from app.core.config import get_settings
from app.core.parsing import parse_date
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.modules.analytics.client import AnalyticsClient
from app.models.analytics import WBHiddenProduct
from app.models.product_cards import CoreSKU
from app.models.orders import WBOrder
from app.models.prices import WBPrice
from app.models.sales import WBSale
from app.models.stocks import WBStockSnapshotRow
from app.repositories.analytics import CardFunnelRepository, RegionSalesRepository


class AnalyticsSyncService(DomainSyncBase):
    domain = "analytics"
    category = "analytics"

    def __init__(self) -> None:
        super().__init__()
        self.client = AnalyticsClient(self)
        self.funnel_repo = CardFunnelRepository()
        self.region_repo = RegionSalesRepository()

    @staticmethod
    def _batched_nm_ids(nm_ids: list[int], *, batch_size: int) -> list[list[int]]:
        return [
            nm_ids[offset : offset + batch_size]
            for offset in range(0, len(nm_ids), batch_size)
        ]

    @staticmethod
    def _default_window() -> tuple[str, str]:
        today = utcnow().date()
        return (today - timedelta(days=6)).isoformat(), today.isoformat()

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        if backfill_from is None and backfill_to is None:
            start_date, end_date = self._default_window()
        else:
            start_date = (
                backfill_from or (utcnow().date() - timedelta(days=6))
            ).isoformat()
            end_date = (backfill_to or utcnow().date()).isoformat()
        batch_size = get_settings().analytics_funnel_batch_size
        nm_ids: list[int] = []
        for model in (CoreSKU, WBPrice, WBOrder, WBSale, WBStockSnapshotRow):
            filters = [model.account_id == account.id, model.nm_id.is_not(None)]
            if model is CoreSKU:
                filters.append(CoreSKU.is_active.is_(True))
            model_nm_ids = list(
                (
                    await session.execute(
                        select(model.nm_id).where(*filters).distinct()
                    )
                ).scalars()
            )
            for nm_id in model_nm_ids:
                if nm_id is not None and nm_id not in nm_ids:
                    nm_ids.append(int(nm_id))
        funnel_rows = []
        batch_count = 0
        for batch_index, batch_nm_ids in enumerate(
            self._batched_nm_ids(nm_ids, batch_size=batch_size),
            start=1,
        ):
            if not batch_nm_ids:
                continue
            batch_count += 1
            funnel_payload = await self.client.funnel_history(
                session,
                account_id=account.id,
                nm_ids=batch_nm_ids,
                start_date=start_date,
                end_date=end_date,
            )
            for product_item in (
                funnel_payload if isinstance(funnel_payload, list) else []
            ):
                product = product_item.get("product", {})
                for history in product_item.get("history", []):
                    stat_date = parse_date(history.get("date"))
                    nm_id = product.get("nmId")
                    if stat_date is None or nm_id is None:
                        continue
                    funnel_rows.append(
                        {
                            "account_id": account.id,
                            "stat_date": stat_date,
                            "nm_id": nm_id,
                            "vendor_code": product.get("vendorCode"),
                            "title": product.get("title"),
                            "brand_name": product.get("brandName"),
                            "subject_id": product.get("subjectId"),
                            "subject_name": product.get("subjectName"),
                            "open_count": history.get("openCount"),
                            "cart_count": history.get("cartCount"),
                            "order_count": history.get("orderCount"),
                            "buyout_count": history.get("buyoutCount"),
                            "cancel_count": history.get("cancelCount"),
                            "add_to_cart_conversion": history.get(
                                "addToCartConversion"
                            ),
                            "cart_to_order_conversion": history.get(
                                "cartToOrderConversion"
                            ),
                            "buyout_percent": history.get("buyoutPercent"),
                            "payload": {
                                "product": product,
                                "history": history,
                                "batchIndex": batch_index,
                            },
                        }
                    )
        if funnel_rows:
            await self.funnel_repo.upsert_many(
                session,
                funnel_rows,
                conflict_fields=["account_id", "stat_date", "nm_id"],
            )
        region_payload = await self.client.region_sales(
            session, account_id=account.id, date_from=start_date, date_to=end_date
        )
        region_rows = []
        for item in (
            region_payload.get("report", []) if isinstance(region_payload, dict) else []
        ):
            region_rows.append(
                {
                    "account_id": account.id,
                    "stat_date": parse_date(item.get("date")) or utcnow().date(),
                    "region_name": item.get("regionName"),
                    "country_name": item.get("countryName"),
                    "city_name": item.get("cityName"),
                    "federal_district": item.get("foName"),
                    "nm_id": item.get("nmId") or item.get("nmID"),
                    "vendor_code": item.get("vendorCode") or item.get("sa"),
                    "sale_amount": item.get("saleInvoiceCostPrice"),
                    "sale_amount_percent": item.get("saleInvoiceCostPricePerc"),
                    "sale_quantity": item.get("saleItemInvoiceQty"),
                    "payload": item,
                }
            )
        await self.region_repo.upsert_many(
            session,
            region_rows,
            conflict_fields=["dedupe_key"],
        )
        await session.execute(
            delete(WBHiddenProduct).where(WBHiddenProduct.account_id == account.id)
        )
        for hidden_type, payload in (
            (
                "blocked",
                await self.client.blocked_products(session, account_id=account.id),
            ),
            (
                "shadowed",
                await self.client.shadowed_products(session, account_id=account.id),
            ),
        ):
            for item in payload.get("report", []) if isinstance(payload, dict) else []:
                session.add(
                    WBHiddenProduct(
                        account_id=account.id,
                        hidden_type=hidden_type,
                        nm_id=item.get("nmId"),
                        vendor_code=item.get("vendorCode"),
                        title=item.get("title"),
                        reason=item.get("reason"),
                        payload=item,
                    )
                )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={
                "startDate": start_date,
                "endDate": end_date,
                "batchCount": batch_count,
                "nmCount": len(nm_ids),
                "rowsLoaded": len(funnel_rows),
            },
        )
        return {
            "status": "completed",
            "batchCount": batch_count,
            "nmCount": len(nm_ids),
            "rowsLoaded": len(funnel_rows),
        }
