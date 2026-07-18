from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import stable_hash, table_signature
from app.core.config import get_settings
from app.core.issue_refs import extract_issue_refs
from app.core.pagination import Page
from app.core.sorting import apply_sort_direction
from app.core.time import utcnow
from app.models.data_quality import DataQualityIssue
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.prices import WBPrice, WBPriceSize
from app.models.product_cards import CoreSKU
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.schemas.core_sku import CoreSKUDetail, CoreSKUListItem
from app.services.trust import core_sku_cost_trust_snapshot


class CoreSKUService:
    RESPONSE_CACHE_TTL_SECONDS = get_settings().heavy_endpoint_cache_ttl_seconds
    _shared_list_cache: dict[
        tuple[object, ...], tuple[datetime, Page[CoreSKUListItem]]
    ] = {}
    _shared_detail_cache: dict[tuple[object, ...], tuple[datetime, CoreSKUDetail]] = {}

    def __init__(self) -> None:
        self._list_cache = type(self)._shared_list_cache
        self._detail_cache = type(self)._shared_detail_cache

    @staticmethod
    def _cache_is_fresh(cached_at: datetime, *, ttl_seconds: int) -> bool:
        return (utcnow() - cached_at) <= timedelta(seconds=ttl_seconds)

    @staticmethod
    def _with_page_cache_meta(
        page: Page[CoreSKUListItem],
        *,
        computed_at: datetime,
        cache_status: str,
        data_version_hash: str,
    ) -> Page[CoreSKUListItem]:
        return page.model_copy(
            deep=True,
            update={
                "computed_at": computed_at,
                "cache_status": cache_status,
                "data_version_hash": data_version_hash,
            },
        )

    async def _list_version_hash(
        self,
        session: AsyncSession,
        *,
        account_id: int | None,
        date_from: date,
        date_to: date,
    ) -> str:
        core_hash = await table_signature(session, model=CoreSKU, account_id=account_id)
        cost_hash = await table_signature(
            session,
            model=ManualCost,
            account_id=account_id,
            extra_filters=[
                or_(ManualCost.valid_from.is_(None), ManualCost.valid_from <= date_to),
                or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= date_from),
            ],
        )
        mart_hash = await table_signature(
            session,
            model=MartSKUDaily,
            account_id=account_id,
            date_column=MartSKUDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        stock_hash = await table_signature(
            session,
            model=MartStockDaily,
            account_id=account_id,
            date_column=MartStockDaily.stat_date,
            date_from=date_from,
            date_to=date_to,
        )
        price_hash = await table_signature(
            session, model=WBPrice, account_id=account_id
        )
        dq_hash = await table_signature(
            session,
            model=DataQualityIssue,
            account_id=account_id,
            extra_filters=[DataQualityIssue.resolved_at.is_(None)],
        )
        return stable_hash(
            "core-sku-list",
            account_id,
            date_from.isoformat(),
            date_to.isoformat(),
            core_hash,
            cost_hash,
            mart_hash,
            stock_hash,
            price_hash,
            dq_hash,
        )

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value))
        except Exception:
            return None

    @staticmethod
    def _is_total_stock_row(warehouse_name: str | None) -> bool:
        return "всего" in str(warehouse_name or "").strip().lower()

    @classmethod
    def _collect_price_range(
        cls,
        items: list[dict[str, Any]],
        *,
        price_key: str,
        discounted_key: str,
    ) -> tuple[Decimal | None, Decimal | None]:
        prices = [
            value
            for value in (cls._optional_decimal(item.get(price_key)) for item in items)
            if value is not None
        ]
        discounted = [
            value
            for value in (
                cls._optional_decimal(item.get(discounted_key)) for item in items
            )
            if value is not None
        ]
        return (
            min(prices) if prices else None,
            min(discounted) if discounted else None,
        )

    @classmethod
    def _extract_payload_prices_for_sku(
        cls,
        payload: dict[str, Any] | None,
        *,
        size_id: int | None,
        tech_size: str | None,
    ) -> tuple[Decimal | None, Decimal | None]:
        if not isinstance(payload, dict):
            return None, None
        sizes = payload.get("sizes")
        if isinstance(sizes, list) and sizes:
            normalized_tech_size = str(tech_size or "").strip().lower()
            exact_items = [
                item
                for item in sizes
                if isinstance(item, dict)
                and (
                    (size_id is not None and item.get("sizeID") == size_id)
                    or (
                        normalized_tech_size
                        and str(item.get("techSizeName") or "").strip().lower()
                        == normalized_tech_size
                    )
                )
            ]
            exact_price, exact_discounted = cls._collect_price_range(
                exact_items,
                price_key="price",
                discounted_key="discountedPrice",
            )
            any_price, any_discounted = cls._collect_price_range(
                [item for item in sizes if isinstance(item, dict)],
                price_key="price",
                discounted_key="discountedPrice",
            )
            return exact_price or any_price, exact_discounted or any_discounted

        top_level_price = cls._optional_decimal(
            payload.get("price") or payload.get("basicPrice") or payload.get("priceU")
        )
        top_level_discounted = cls._optional_decimal(
            payload.get("discountedPrice")
            or payload.get("discountPrice")
            or payload.get("finalPrice")
        )
        return top_level_price, top_level_discounted

    @classmethod
    def _extract_size_row_prices_for_sku(
        cls,
        rows: list[WBPriceSize],
        *,
        size_id: int | None,
        tech_size: str | None,
    ) -> tuple[Decimal | None, Decimal | None]:
        if not rows:
            return None, None
        normalized_tech_size = str(tech_size or "").strip().lower()
        exact_rows = [
            row
            for row in rows
            if (size_id is not None and row.size_id == size_id)
            or (
                normalized_tech_size
                and str(row.tech_size_name or "").strip().lower()
                == normalized_tech_size
            )
        ]
        exact_items = [
            {"price": row.price, "discounted_price": row.discounted_price}
            for row in exact_rows
        ]
        any_items = [
            {"price": row.price, "discounted_price": row.discounted_price}
            for row in rows
        ]
        exact_price, exact_discounted = cls._collect_price_range(
            exact_items,
            price_key="price",
            discounted_key="discounted_price",
        )
        any_price, any_discounted = cls._collect_price_range(
            any_items,
            price_key="price",
            discounted_key="discounted_price",
        )
        return exact_price or any_price, exact_discounted or any_discounted

    @classmethod
    def _aggregate_stock_snapshot_rows(
        cls,
        rows: list[WBStockSnapshotRow],
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
        if not rows:
            return None, None, None, None
        total_rows = [
            row for row in rows if cls._is_total_stock_row(row.warehouse_name)
        ]
        quantity_source = total_rows or rows
        transit_rows = [
            row
            for row in rows
            if cls._optional_decimal(getattr(row, "quantity", None)) is None
            and cls._optional_decimal(getattr(row, "quantity_full", None)) is None
        ]
        transit_source = transit_rows or quantity_source
        quantity = sum(
            (
                cls._optional_decimal(getattr(row, "quantity_full", None))
                if total_rows
                else cls._optional_decimal(getattr(row, "quantity", None))
            )
            or Decimal("0")
            for row in quantity_source
        )
        in_way_to_client = sum(
            (
                cls._optional_decimal(getattr(row, "in_way_to_client", None))
                or Decimal("0")
            )
            for row in transit_source
        )
        in_way_from_client = sum(
            (
                cls._optional_decimal(getattr(row, "in_way_from_client", None))
                or Decimal("0")
            )
            for row in transit_source
        )
        return quantity, quantity, in_way_to_client, in_way_from_client

    async def list_skus(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        search: str | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        brand: str | None = None,
        subject_name: str | None = None,
        status: str | None = None,
        has_manual_cost: bool | None = None,
        has_open_issues: bool | None = None,
        has_price: bool | None = None,
        has_sales: bool | None = None,
        has_revenue: bool | None = None,
        has_stock: bool | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[CoreSKUListItem]:
        today = utcnow().date()
        actual_from = date_from or (today - timedelta(days=30))
        actual_to = date_to or today
        data_version_hash = await self._list_version_hash(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        cache_key = (
            account_id,
            search or "",
            nm_id,
            vendor_code or "",
            barcode or "",
            brand or "",
            subject_name or "",
            status or "",
            has_manual_cost,
            has_open_issues,
            has_price,
            has_sales,
            has_revenue,
            has_stock,
            actual_from,
            actual_to,
            sort_by or "",
            sort_dir,
            limit,
            offset,
            data_version_hash,
        )
        cached_page = self._list_cache.get(cache_key)
        if cached_page is not None:
            cached_at, page = cached_page
            if self._cache_is_fresh(
                cached_at, ttl_seconds=self.RESPONSE_CACHE_TTL_SECONDS
            ):
                return self._with_page_cache_meta(
                    page,
                    computed_at=cached_at,
                    cache_status="hit",
                    data_version_hash=data_version_hash,
                )

        def finalize_page(page: Page[CoreSKUListItem]) -> Page[CoreSKUListItem]:
            computed_at = utcnow()
            cached_page = self._with_page_cache_meta(
                page,
                computed_at=computed_at,
                cache_status="miss",
                data_version_hash=data_version_hash,
            )
            self._list_cache[cache_key] = (
                computed_at,
                cached_page.model_copy(deep=True),
            )
            return cached_page

        cost_exists = (
            select(ManualCost.id)
            .where(
                ManualCost.account_id == CoreSKU.account_id,
                ManualCost.sku_id == CoreSKU.id,
                or_(
                    ManualCost.valid_from.is_(None), ManualCost.valid_from <= actual_to
                ),
                or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= actual_from),
            )
            .limit(1)
        )
        price_exists = (
            select(WBPriceSize.id)
            .where(
                WBPriceSize.account_id == CoreSKU.account_id,
                WBPriceSize.nm_id == CoreSKU.nm_id,
                or_(
                    WBPriceSize.price > 0,
                    WBPriceSize.discounted_price > 0,
                    WBPriceSize.club_discounted_price > 0,
                ),
            )
            .limit(1)
        )
        sales_exists = (
            select(MartSKUDaily.id)
            .where(
                MartSKUDaily.account_id == CoreSKU.account_id,
                MartSKUDaily.sku_id == CoreSKU.id,
                MartSKUDaily.stat_date >= actual_from,
                MartSKUDaily.stat_date <= actual_to,
                MartSKUDaily.final_sales_qty > 0,
            )
            .limit(1)
        )
        revenue_exists = (
            select(MartSKUDaily.id)
            .where(
                MartSKUDaily.account_id == CoreSKU.account_id,
                MartSKUDaily.sku_id == CoreSKU.id,
                MartSKUDaily.stat_date >= actual_from,
                MartSKUDaily.stat_date <= actual_to,
                MartSKUDaily.final_revenue > 0,
            )
            .limit(1)
        )
        stock_exists = (
            select(MartStockDaily.id)
            .where(
                MartStockDaily.account_id == CoreSKU.account_id,
                MartStockDaily.sku_id == CoreSKU.id,
                MartStockDaily.stat_date >= actual_from,
                MartStockDaily.stat_date <= actual_to,
                or_(
                    MartStockDaily.quantity > 0,
                    MartStockDaily.quantity_full > 0,
                    MartStockDaily.in_way_to_client > 0,
                    MartStockDaily.in_way_from_client > 0,
                ),
            )
            .limit(1)
        )
        sort_map = {
            "id": CoreSKU.id,
            "nm_id": CoreSKU.nm_id,
            "vendor_code": CoreSKU.vendor_code,
            "barcode": CoreSKU.barcode,
            "title": CoreSKU.title,
            "brand": CoreSKU.brand,
            "subject_name": CoreSKU.subject_name,
            "status": CoreSKU.status,
        }
        sort_column = sort_map.get(sort_by or "", CoreSKU.vendor_code)
        order_clauses = [
            apply_sort_direction(sort_column, sort_dir),
            CoreSKU.id.desc(),
        ]
        stmt = select(CoreSKU.id).where(CoreSKU.is_active.is_(True))
        if account_id is not None:
            stmt = stmt.where(CoreSKU.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(CoreSKU.nm_id == nm_id)
        if vendor_code is not None:
            stmt = stmt.where(CoreSKU.vendor_code == vendor_code)
        if barcode is not None:
            stmt = stmt.where(CoreSKU.barcode == barcode)
        if brand is not None:
            stmt = stmt.where(CoreSKU.brand == brand)
        if subject_name is not None:
            stmt = stmt.where(CoreSKU.subject_name == subject_name)
        if status is not None:
            stmt = stmt.where(CoreSKU.status == status)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    CoreSKU.vendor_code.ilike(pattern),
                    CoreSKU.barcode.ilike(pattern),
                    CoreSKU.title.ilike(pattern),
                    sa.cast(CoreSKU.nm_id, sa.String).ilike(pattern),
                )
            )
        if has_manual_cost is True:
            stmt = stmt.where(sa.exists(cost_exists))
        elif has_manual_cost is False:
            stmt = stmt.where(~sa.exists(cost_exists))
        if has_price is True:
            stmt = stmt.where(sa.exists(price_exists))
        elif has_price is False:
            stmt = stmt.where(~sa.exists(price_exists))
        if has_sales is True:
            stmt = stmt.where(sa.exists(sales_exists))
        elif has_sales is False:
            stmt = stmt.where(~sa.exists(sales_exists))
        if has_revenue is True:
            stmt = stmt.where(sa.exists(revenue_exists))
        elif has_revenue is False:
            stmt = stmt.where(~sa.exists(revenue_exists))
        if has_stock is True:
            stmt = stmt.where(sa.exists(stock_exists))
        elif has_stock is False:
            stmt = stmt.where(~sa.exists(stock_exists))

        if has_open_issues is not None:
            candidate_rows = (
                await session.execute(
                    select(CoreSKU.id, CoreSKU.account_id, CoreSKU.nm_id)
                    .where(CoreSKU.id.in_(stmt.subquery()))
                    .order_by(*order_clauses)
                )
            ).all()
            if not candidate_rows:
                return finalize_page(
                    Page(total=0, limit=limit, offset=offset, items=[])
                )

            account_ids = sorted(
                {row.account_id for row in candidate_rows if row.account_id is not None}
            )
            open_issues = await self._load_open_issues_for_accounts(
                session, account_ids=account_ids
            )
            issue_matches_by_sku_id, issue_matches_by_nm_id = (
                self._collect_issue_match_sets(open_issues)
            )
            filtered_ids: list[int] = []
            for row in candidate_rows:
                has_issue = row.id in issue_matches_by_sku_id or (
                    row.nm_id is not None and row.nm_id in issue_matches_by_nm_id
                )
                if has_issue is has_open_issues:
                    filtered_ids.append(int(row.id))

            total = len(filtered_ids)
            page_ids = filtered_ids[offset : offset + limit]
            if not page_ids:
                return finalize_page(
                    Page(total=total, limit=limit, offset=offset, items=[])
                )
            rows = await self._load_enriched_rows(
                session,
                sku_ids=page_ids,
                date_from=actual_from,
                date_to=actual_to,
                open_issues=open_issues,
            )
            row_map = {row.id: row for row in rows}
            ordered_rows = [row_map[sku_id] for sku_id in page_ids if sku_id in row_map]
            return finalize_page(
                Page(total=total, limit=limit, offset=offset, items=ordered_rows)
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await session.execute(count_stmt)).scalar_one())
        page_ids = list(
            (
                await session.execute(
                    stmt.order_by(*order_clauses).limit(limit).offset(offset)
                )
            ).scalars()
        )
        if not page_ids:
            return finalize_page(
                Page(total=total, limit=limit, offset=offset, items=[])
            )

        rows = await self._load_enriched_rows(
            session,
            sku_ids=page_ids,
            date_from=actual_from,
            date_to=actual_to,
        )
        row_map = {row.id: row for row in rows}
        ordered_rows = [row_map[sku_id] for sku_id in page_ids if sku_id in row_map]
        return finalize_page(
            Page(total=total, limit=limit, offset=offset, items=ordered_rows)
        )

    async def get_sku_detail(
        self,
        session: AsyncSession,
        *,
        sku_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> CoreSKUDetail | None:
        today = utcnow().date()
        actual_from = date_from or (today - timedelta(days=30))
        actual_to = date_to or today
        account_id = (
            await session.execute(
                select(CoreSKU.account_id)
                .where(CoreSKU.id == sku_id, CoreSKU.is_active.is_(True))
                .limit(1)
            )
        ).scalar_one_or_none()
        if account_id is not None:
            data_version_hash = await self._list_version_hash(
                session,
                account_id=account_id,
                date_from=actual_from,
                date_to=actual_to,
            )
            cache_key = (sku_id, actual_from, actual_to, data_version_hash)
            cached_detail = self._detail_cache.get(cache_key)
            if cached_detail is not None:
                cached_at, detail = cached_detail
                if self._cache_is_fresh(
                    cached_at, ttl_seconds=self.RESPONSE_CACHE_TTL_SECONDS
                ):
                    return detail.model_copy(deep=True)
        rows = await self._load_enriched_rows(
            session,
            sku_ids=[sku_id],
            date_from=actual_from,
            date_to=actual_to,
        )
        if not rows:
            return None
        row = rows[0]
        recent_issue_codes = [
            issue.code
            for issue in await self._load_recent_issue_rows_for_sku(
                session,
                account_id=row.account_id,
                sku_id=row.id,
                nm_id=row.nm_id,
                limit=20,
            )
        ]
        latest_snapshot_at = row.latest_stock_snapshot_at
        warehouses: list[str] = []
        if latest_snapshot_at is not None:
            warehouse_filters = [
                WBStockSnapshotRow.account_id == row.account_id,
                WBStockSnapshotRow.nm_id == row.nm_id,
                WBStockSnapshot.snapshot_at == latest_snapshot_at,
            ]
            if row.barcode is None:
                warehouse_filters.append(WBStockSnapshotRow.barcode.is_(None))
            else:
                warehouse_filters.append(WBStockSnapshotRow.barcode == row.barcode)
            warehouses = list(
                (
                    await session.execute(
                        select(WBStockSnapshotRow.warehouse_name)
                        .join(
                            WBStockSnapshot,
                            WBStockSnapshot.id == WBStockSnapshotRow.snapshot_id,
                        )
                        .where(*warehouse_filters)
                    )
                ).scalars()
            )
        result = CoreSKUDetail(
            sku=row,
            recent_issue_codes=recent_issue_codes,
            warehouses=sorted({item for item in warehouses if item}),
        )
        if account_id is not None:
            self._detail_cache[cache_key] = (utcnow(), result.model_copy(deep=True))
        return result

    async def _load_enriched_rows(
        self,
        session: AsyncSession,
        *,
        sku_ids: list[int],
        date_from: date,
        date_to: date,
        open_issues: list[DataQualityIssue] | None = None,
    ) -> list[CoreSKUListItem]:
        if not sku_ids:
            return []
        view_rows = (
            (
                await session.execute(
                    sa.text(
                        """
                    SELECT
                        id,
                        account_id,
                        nm_id,
                        vendor_code,
                        supplier_article,
                        barcode,
                        chrt_id,
                        size_id,
                        tech_size,
                        title,
                        brand,
                        subject_id,
                        subject_name,
                        is_active,
                        status,
                        comment,
                        source_updated_at,
                        current_price,
                        current_discounted_price,
                        seller_discount,
                        club_discount,
                        latest_stock_snapshot_at,
                        latest_quantity,
                        latest_quantity_full,
                        latest_in_way_to_client,
                        latest_in_way_from_client,
                        manual_cost_id,
                        cost_price,
                        seller_other_expense,
                        packaging_cost,
                        inbound_logistics_cost,
                        total_unit_cost,
                        supplier,
                        latest_sale_date,
                        open_issue_count,
                        has_open_issues
                    FROM v_core_sku_enriched
                    WHERE id = ANY(:sku_ids)
                    """
                    ),
                    {"sku_ids": sku_ids},
                )
            )
            .mappings()
            .all()
        )
        mart_stats = {
            row["sku_id"]: row
            for row in (
                await session.execute(
                    select(
                        MartSKUDaily.sku_id,
                        func.sum(MartSKUDaily.final_sales_qty).label("sales_qty"),
                        func.sum(MartSKUDaily.final_revenue).label("revenue"),
                    )
                    .where(
                        MartSKUDaily.sku_id.in_(sku_ids),
                        MartSKUDaily.stat_date >= date_from,
                        MartSKUDaily.stat_date <= date_to,
                    )
                    .group_by(MartSKUDaily.sku_id)
                )
            ).mappings()
        }
        manual_cost_ids = [
            int(row["manual_cost_id"])
            for row in view_rows
            if row.get("manual_cost_id") is not None
        ]
        manual_costs_by_id: dict[int, ManualCost] = {}
        if manual_cost_ids:
            manual_costs_by_id = {
                int(item.id): item
                for item in (
                    await session.execute(
                        select(ManualCost).where(ManualCost.id.in_(manual_cost_ids))
                    )
                ).scalars()
            }
        price_fallbacks = await self._load_price_fallbacks(session, view_rows=view_rows)
        stock_fallbacks = await self._load_stock_fallbacks(session, view_rows=view_rows)
        if open_issues is None:
            account_ids = sorted({int(row["account_id"]) for row in view_rows})
            open_issues = await self._load_open_issues_for_accounts(
                session, account_ids=account_ids
            )
        issue_matches_by_sku_id, issue_matches_by_nm_id = (
            self._collect_issue_match_sets(open_issues)
        )
        enriched: list[CoreSKUListItem] = []
        for row in view_rows:
            mart_row = mart_stats.get(row["id"], {})
            price_fallback = price_fallbacks.get(row["id"], {})
            stock_fallback = stock_fallbacks.get(row["id"], {})
            issue_ids = set(issue_matches_by_sku_id.get(row["id"], set()))
            if row["nm_id"] is not None:
                issue_ids.update(issue_matches_by_nm_id.get(row["nm_id"], set()))
            open_issue_count = len(issue_ids)
            current_price = price_fallback.get("current_price", row["current_price"])
            current_discounted_price = price_fallback.get(
                "current_discounted_price",
                row["current_discounted_price"],
            )
            latest_stock_snapshot_at = stock_fallback.get(
                "latest_stock_snapshot_at",
                row["latest_stock_snapshot_at"],
            )
            latest_quantity = stock_fallback.get(
                "latest_quantity", row["latest_quantity"]
            )
            latest_quantity_full = stock_fallback.get(
                "latest_quantity_full",
                row["latest_quantity_full"],
            )
            latest_in_way_to_client = stock_fallback.get(
                "latest_in_way_to_client",
                row["latest_in_way_to_client"],
            )
            latest_in_way_from_client = stock_fallback.get(
                "latest_in_way_from_client",
                row["latest_in_way_from_client"],
            )
            cost_snapshot = core_sku_cost_trust_snapshot(
                manual_costs_by_id.get(int(row["manual_cost_id"]))
                if row["manual_cost_id"] is not None
                else None
            )
            enriched.append(
                CoreSKUListItem(
                    id=row["id"],
                    account_id=row["account_id"],
                    nm_id=row["nm_id"],
                    vendor_code=row["vendor_code"],
                    supplier_article=row["supplier_article"],
                    barcode=row["barcode"],
                    chrt_id=row["chrt_id"],
                    size_id=row["size_id"],
                    tech_size=row["tech_size"],
                    title=row["title"],
                    brand=row["brand"],
                    subject_id=row["subject_id"],
                    subject_name=row["subject_name"],
                    is_active=row["is_active"],
                    status=row["status"],
                    comment=row["comment"],
                    source_updated_at=row["source_updated_at"],
                    current_price=current_price,
                    current_discounted_price=current_discounted_price,
                    seller_discount=row["seller_discount"],
                    club_discount=row["club_discount"],
                    latest_quantity=latest_quantity,
                    latest_quantity_full=latest_quantity_full,
                    latest_in_way_to_client=latest_in_way_to_client,
                    latest_in_way_from_client=latest_in_way_from_client,
                    latest_stock_snapshot_at=latest_stock_snapshot_at,
                    latest_sale_date=row["latest_sale_date"],
                    manual_cost_id=row["manual_cost_id"],
                    cost_price=row["cost_price"],
                    seller_other_expense=row["seller_other_expense"],
                    packaging_cost=row["packaging_cost"],
                    inbound_logistics_cost=row["inbound_logistics_cost"],
                    total_unit_cost=row["total_unit_cost"],
                    supplier=row["supplier"],
                    has_manual_cost=row["manual_cost_id"] is not None,
                    has_real_manual_cost=bool(cost_snapshot["has_real_manual_cost"]),
                    has_placeholder_cost=bool(cost_snapshot["has_placeholder_cost"]),
                    business_trusted=bool(cost_snapshot["business_trusted"]),
                    operational_trusted=bool(cost_snapshot["operational_trusted"]),
                    cost_source=cost_snapshot["cost_source"],
                    cost_truth_level=str(cost_snapshot["cost_truth_level"])
                    if cost_snapshot["cost_truth_level"] is not None
                    else None,
                    open_issue_count=open_issue_count,
                    has_open_issues=bool(issue_ids),
                    last_30d_sales_qty=int(mart_row.get("sales_qty") or 0),
                    last_30d_revenue=mart_row.get("revenue"),
                )
            )
        return enriched

    async def _load_price_fallbacks(
        self,
        session: AsyncSession,
        *,
        view_rows: list[sa.RowMapping],
    ) -> dict[int, dict[str, Decimal]]:
        keys = sorted(
            {
                (int(row["account_id"]), int(row["nm_id"]))
                for row in view_rows
                if row["nm_id"] is not None
            }
        )
        if not keys:
            return {}

        price_rows = list(
            (
                await session.execute(
                    select(WBPrice)
                    .where(tuple_(WBPrice.account_id, WBPrice.nm_id).in_(keys))
                    .order_by(WBPrice.account_id, WBPrice.nm_id, WBPrice.id.desc())
                )
            ).scalars()
        )
        latest_prices_by_key: dict[tuple[int, int], WBPrice] = {}
        for row in price_rows:
            key = (int(row.account_id), int(row.nm_id))
            latest_prices_by_key.setdefault(key, row)

        size_rows = list(
            (
                await session.execute(
                    select(WBPriceSize).where(
                        tuple_(WBPriceSize.account_id, WBPriceSize.nm_id).in_(keys)
                    )
                )
            ).scalars()
        )
        size_rows_by_key: dict[tuple[int, int], list[WBPriceSize]] = defaultdict(list)
        for row in size_rows:
            size_rows_by_key[(int(row.account_id), int(row.nm_id))].append(row)

        fallbacks: dict[int, dict[str, Decimal]] = {}
        for row in view_rows:
            if row["nm_id"] is None:
                continue
            key = (int(row["account_id"]), int(row["nm_id"]))
            size_price, size_discounted = self._extract_size_row_prices_for_sku(
                size_rows_by_key.get(key, []),
                size_id=row["size_id"],
                tech_size=row["tech_size"],
            )
            payload_price, payload_discounted = self._extract_payload_prices_for_sku(
                getattr(latest_prices_by_key.get(key), "payload", None),
                size_id=row["size_id"],
                tech_size=row["tech_size"],
            )
            resolved_price = size_price or payload_price
            resolved_discounted = size_discounted or payload_discounted
            if resolved_price is None and resolved_discounted is None:
                continue
            fallbacks[int(row["id"])] = {
                "current_price": resolved_price,
                "current_discounted_price": resolved_discounted,
            }
        return fallbacks

    async def _load_stock_fallbacks(
        self,
        session: AsyncSession,
        *,
        view_rows: list[sa.RowMapping],
    ) -> dict[int, dict[str, Decimal | date | None]]:
        refs = [row for row in view_rows if row["nm_id"] is not None]
        if not refs:
            return {}

        filters = [
            and_(
                WBStockSnapshotRow.account_id == int(row["account_id"]),
                WBStockSnapshotRow.nm_id == int(row["nm_id"]),
                WBStockSnapshotRow.barcode.is_(None)
                if row["barcode"] is None
                else WBStockSnapshotRow.barcode == row["barcode"],
            )
            for row in refs
        ]
        latest_snapshots = (
            select(
                WBStockSnapshotRow.account_id.label("account_id"),
                WBStockSnapshotRow.nm_id.label("nm_id"),
                WBStockSnapshotRow.barcode.label("barcode"),
                func.max(WBStockSnapshot.snapshot_at).label("latest_stock_snapshot_at"),
            )
            .join(WBStockSnapshot, WBStockSnapshot.id == WBStockSnapshotRow.snapshot_id)
            .where(or_(*filters))
            .group_by(
                WBStockSnapshotRow.account_id,
                WBStockSnapshotRow.nm_id,
                WBStockSnapshotRow.barcode,
            )
            .subquery()
        )

        latest_rows = list(
            (
                await session.execute(
                    select(WBStockSnapshotRow, WBStockSnapshot.snapshot_at)
                    .join(
                        WBStockSnapshot,
                        WBStockSnapshot.id == WBStockSnapshotRow.snapshot_id,
                    )
                    .join(
                        latest_snapshots,
                        and_(
                            latest_snapshots.c.account_id
                            == WBStockSnapshotRow.account_id,
                            latest_snapshots.c.nm_id == WBStockSnapshotRow.nm_id,
                            latest_snapshots.c.barcode.is_not_distinct_from(
                                WBStockSnapshotRow.barcode
                            ),
                            latest_snapshots.c.latest_stock_snapshot_at
                            == WBStockSnapshot.snapshot_at,
                        ),
                    )
                )
            ).all()
        )

        rows_by_key: dict[tuple[int, int, str | None], list[WBStockSnapshotRow]] = (
            defaultdict(list)
        )
        snapshot_by_key: dict[tuple[int, int, str | None], Any] = {}
        for stock_row, snapshot_at in latest_rows:
            key = (int(stock_row.account_id), int(stock_row.nm_id), stock_row.barcode)
            rows_by_key[key].append(stock_row)
            snapshot_by_key[key] = snapshot_at

        fallbacks: dict[int, dict[str, Any]] = {}
        for row in refs:
            key = (int(row["account_id"]), int(row["nm_id"]), row["barcode"])
            stock_rows_for_key = rows_by_key.get(key, [])
            if not stock_rows_for_key:
                continue
            (
                latest_quantity,
                latest_quantity_full,
                latest_in_way_to_client,
                latest_in_way_from_client,
            ) = self._aggregate_stock_snapshot_rows(stock_rows_for_key)
            fallbacks[int(row["id"])] = {
                "latest_stock_snapshot_at": snapshot_by_key.get(key),
                "latest_quantity": latest_quantity,
                "latest_quantity_full": latest_quantity_full,
                "latest_in_way_to_client": latest_in_way_to_client,
                "latest_in_way_from_client": latest_in_way_from_client,
            }
        return fallbacks

    async def _load_open_issues_for_accounts(
        self,
        session: AsyncSession,
        *,
        account_ids: list[int],
    ) -> list[DataQualityIssue]:
        if not account_ids:
            return []
        return list(
            (
                await session.execute(
                    select(DataQualityIssue).where(
                        DataQualityIssue.account_id.in_(account_ids),
                        DataQualityIssue.resolved_at.is_(None),
                    )
                )
            ).scalars()
        )

    def _collect_issue_match_sets(
        self,
        issues: list[DataQualityIssue],
    ) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
        issue_matches_by_sku_id: dict[int, set[int]] = defaultdict(set)
        issue_matches_by_nm_id: dict[int, set[int]] = defaultdict(set)
        for issue in issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if issue_sku_id is not None:
                issue_matches_by_sku_id[issue_sku_id].add(issue.id)
            if issue_nm_id is not None:
                issue_matches_by_nm_id[issue_nm_id].add(issue.id)
        return issue_matches_by_sku_id, issue_matches_by_nm_id

    async def _load_recent_issue_rows_for_sku(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int,
        nm_id: int | None,
        limit: int,
    ) -> list[DataQualityIssue]:
        issues = list(
            (
                await session.execute(
                    select(DataQualityIssue)
                    .where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                    )
                    .order_by(DataQualityIssue.detected_at.desc())
                )
            ).scalars()
        )
        matched: list[DataQualityIssue] = []
        for issue in issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if issue_sku_id == sku_id or (nm_id is not None and issue_nm_id == nm_id):
                matched.append(issue)
                if len(matched) >= limit:
                    break
        return matched
