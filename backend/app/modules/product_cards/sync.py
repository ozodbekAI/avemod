from __future__ import annotations

from collections import defaultdict

from app.core.dedupe import compute_dedupe_key_from_mapping
from app.core.parsing import parse_datetime
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.wb_sync import DomainSyncBase
from app.models.manual_costs import ManualCost
from app.modules.product_cards.client import ProductCardsClient
from app.models.prices import WBPrice, WBPriceSize
from app.models.product_cards import (
    CoreSKU,
    WBProductCard,
    WBProductCardCharacteristic,
    WBProductCardSize,
    WBProductCardTag,
)
from app.repositories.product_cards import CoreSKURepository, ProductCardRepository
from app.services.manual_costs import ManualCostService


class ProductCardsSyncService(DomainSyncBase):
    domain = "product_cards"
    category = "content"

    def __init__(self) -> None:
        super().__init__()
        self.client = ProductCardsClient(self)
        self.repo = ProductCardRepository()
        self.core_skus = CoreSKURepository()

    @staticmethod
    def _dedupe_key_for_core_sku_row(row: dict) -> str:
        return compute_dedupe_key_from_mapping(CoreSKU.__dedupe_fields__, row)

    @classmethod
    def _build_card_core_sku_rows(
        cls,
        *,
        account_id: int,
        db_card: WBProductCard,
        card_payload: dict,
    ) -> list[dict]:
        sizes = card_payload.get("sizes") or []
        rows: list[dict] = []
        if not sizes:
            rows.append(
                {
                    "account_id": account_id,
                    "nm_id": db_card.nm_id,
                    "vendor_code": db_card.vendor_code,
                    "supplier_article": db_card.vendor_code,
                    "barcode": None,
                    "sku": None,
                    "chrt_id": None,
                    "size_id": None,
                    "tech_size": None,
                    "title": db_card.title,
                    "brand": db_card.brand,
                    "subject_id": db_card.subject_id,
                    "subject_name": db_card.subject_name,
                    "is_active": True,
                    "status": "active",
                    "comment": None,
                    "source_updated_at": db_card.updated_at_wb,
                }
            )
            return rows
        for size in sizes:
            barcode_values = size.get("skus", []) or [None]
            for barcode in barcode_values:
                rows.append(
                    {
                        "account_id": account_id,
                        "nm_id": db_card.nm_id,
                        "vendor_code": db_card.vendor_code,
                        "supplier_article": db_card.vendor_code,
                        "barcode": barcode,
                        "sku": barcode,
                        "chrt_id": size.get("chrtID"),
                        "size_id": size.get("sizeID"),
                        "tech_size": size.get("techSize"),
                        "title": db_card.title,
                        "brand": db_card.brand,
                        "subject_id": db_card.subject_id,
                        "subject_name": db_card.subject_name,
                        "is_active": True,
                        "status": "active",
                        "comment": None,
                        "source_updated_at": db_card.updated_at_wb,
                    }
                )
        return rows

    async def _sync_core_sku_rows_for_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        rows: list[dict],
    ) -> int:
        if rows:
            await self.core_skus.upsert_many(
                session, rows, conflict_fields=["dedupe_key"]
            )
        await self.core_skus.archive_missing_for_nm(
            session,
            account_id=account_id,
            nm_id=nm_id,
            active_dedupe_keys={self._dedupe_key_for_core_sku_row(row) for row in rows},
        )
        await self._relink_manual_costs_for_nm(
            session,
            account_id=account_id,
            nm_id=nm_id,
            vendor_codes={
                row.get("vendor_code") for row in rows if row.get("vendor_code")
            },
        )
        return len(rows)

    async def _relink_manual_costs_for_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        vendor_codes: set[str],
    ) -> dict[str, int]:
        active_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.nm_id == nm_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        if not active_skus:
            return {"relinked": 0, "ambiguous": 0, "unresolved": 0}
        conditions = [ManualCost.nm_id == nm_id]
        if vendor_codes:
            conditions.append(ManualCost.vendor_code.in_(sorted(vendor_codes)))
        cost_rows = list(
            (
                await session.execute(
                    select(ManualCost).where(
                        ManualCost.account_id == account_id,
                        or_(*conditions),
                    )
                )
            ).scalars()
        )
        active_by_id = {sku.id: sku for sku in active_skus}
        relinked = 0
        ambiguous = 0
        unresolved = 0
        for cost in cost_rows:
            if cost.sku_id is not None and cost.sku_id in active_by_id:
                continue
            matches, match_rule = ManualCostService._resolve_sku_candidates(
                active_skus,
                vendor_code=cost.vendor_code,
                nm_id=cost.nm_id,
                barcode=cost.barcode,
                tech_size=cost.tech_size,
            )
            if len(matches) == 1:
                cost.sku_id = matches[0].id
                cost.match_rule = match_rule
                cost.is_ambiguous = False
                relinked += 1
            elif len(matches) > 1:
                cost.is_ambiguous = True
                ambiguous += 1
            else:
                unresolved += 1
        return {"relinked": relinked, "ambiguous": ambiguous, "unresolved": unresolved}

    async def _sync_price_only_core_skus(
        self, session: AsyncSession, *, account_id: int
    ) -> int:
        existing_nm_ids = set(
            (
                await session.execute(
                    select(CoreSKU.nm_id).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.nm_id.is_not(None),
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        price_rows = list(
            (
                await session.execute(
                    select(WBPrice).where(WBPrice.account_id == account_id)
                )
            ).scalars()
        )
        missing_prices = [row for row in price_rows if row.nm_id not in existing_nm_ids]
        if not missing_prices:
            return 0

        missing_nm_ids = [row.nm_id for row in missing_prices]
        price_sizes = list(
            (
                await session.execute(
                    select(WBPriceSize).where(
                        WBPriceSize.account_id == account_id,
                        WBPriceSize.nm_id.in_(missing_nm_ids),
                    )
                )
            ).scalars()
        )
        sizes_by_nm: dict[int, list[WBPriceSize]] = defaultdict(list)
        for size in price_sizes:
            sizes_by_nm[size.nm_id].append(size)

        created = 0
        desired_rows_by_nm: dict[int, list[dict]] = {}
        for price in missing_prices:
            sizes = sizes_by_nm.get(price.nm_id)
            desired_rows: list[dict] = []
            if sizes:
                for size in sizes:
                    desired_rows.append(
                        {
                            "account_id": account_id,
                            "nm_id": price.nm_id,
                            "vendor_code": size.vendor_code or price.vendor_code,
                            "supplier_article": size.vendor_code or price.vendor_code,
                            "barcode": None,
                            "sku": None,
                            "chrt_id": None,
                            "size_id": size.size_id,
                            "tech_size": size.tech_size_name,
                            "title": None,
                            "brand": None,
                            "subject_id": None,
                            "subject_name": None,
                            "is_active": True,
                            "status": "active",
                            "comment": None,
                            "source_updated_at": price.updated_at,
                        }
                    )
                    created += 1
            else:
                desired_rows.append(
                    {
                        "account_id": account_id,
                        "nm_id": price.nm_id,
                        "vendor_code": price.vendor_code,
                        "supplier_article": price.vendor_code,
                        "barcode": None,
                        "sku": None,
                        "chrt_id": None,
                        "size_id": None,
                        "tech_size": None,
                        "title": None,
                        "brand": None,
                        "subject_id": None,
                        "subject_name": None,
                        "is_active": True,
                        "status": "active",
                        "comment": None,
                        "source_updated_at": price.updated_at,
                    }
                )
                created += 1
            desired_rows_by_nm[price.nm_id] = desired_rows
        for nm_id, desired_rows in desired_rows_by_nm.items():
            await self._sync_core_sku_rows_for_nm(
                session,
                account_id=account_id,
                nm_id=nm_id,
                rows=desired_rows,
            )
        return created

    async def run(
        self,
        session: AsyncSession,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        cursor_row = (
            None
            if force_full
            else await self._get_cursor(session, account_id=account.id)
        )
        request_cursor = cursor_row.cursor_value if cursor_row else None
        await self.client.list_tags(session, account_id=account.id)
        collected = 0
        pages_loaded = 0
        page_limit = 100
        while True:
            payload = await self.client.list_cards(
                session,
                account_id=account.id,
                cursor=request_cursor,
                limit=page_limit,
                ascending=True,
            )
            pages_loaded += 1
            cards = payload.get("cards", [])
            if not cards:
                break
            rows = []
            for card in cards:
                rows.append(
                    {
                        "account_id": account.id,
                        "nm_id": card.get("nmID"),
                        "imt_id": card.get("imtID"),
                        "nm_uuid": card.get("nmUUID"),
                        "subject_id": card.get("subjectID"),
                        "subject_name": card.get("subjectName"),
                        "vendor_code": card.get("vendorCode"),
                        "title": card.get("title"),
                        "description": card.get("description"),
                        "brand": card.get("brand"),
                        "need_kiz": card.get("needKiz"),
                        "kiz_marked": card.get("kizMarked"),
                        "photos": card.get("photos"),
                        "video": card.get("video"),
                        "dimensions": card.get("dimensions"),
                        "created_at_wb": parse_datetime(card.get("createdAt")),
                        "updated_at_wb": parse_datetime(card.get("updatedAt")),
                        "payload": card,
                    }
                )
            await self.repo.upsert_many(
                session, rows, conflict_fields=["account_id", "nm_id"]
            )
            card_rows = list(
                (
                    await session.execute(
                        select(WBProductCard).where(
                            WBProductCard.account_id == account.id,
                            WBProductCard.nm_id.in_([row["nm_id"] for row in rows]),
                        )
                    )
                ).scalars()
            )
            by_nm_id = {row.nm_id: row for row in card_rows}
            for card in cards:
                db_card = by_nm_id.get(card.get("nmID"))
                if db_card is None:
                    continue
                await self.repo.replace_children(session, db_card.id)
                desired_core_sku_rows = self._build_card_core_sku_rows(
                    account_id=account.id,
                    db_card=db_card,
                    card_payload=card,
                )
                await self._sync_core_sku_rows_for_nm(
                    session,
                    account_id=account.id,
                    nm_id=db_card.nm_id,
                    rows=desired_core_sku_rows,
                )
                for size in card.get("sizes", []):
                    session.add(
                        WBProductCardSize(
                            product_card_id=db_card.id,
                            account_id=account.id,
                            chrt_id=size.get("chrtID"),
                            size_id=size.get("sizeID"),
                            tech_size=size.get("techSize"),
                            skus=size.get("skus", []),
                        )
                    )
                for characteristic in card.get("characteristics", []):
                    session.add(
                        WBProductCardCharacteristic(
                            product_card_id=db_card.id,
                            account_id=account.id,
                            char_id=characteristic.get("id"),
                            name=characteristic.get("name"),
                            value=characteristic.get("value"),
                        )
                    )
                for tag in card.get("tags", []):
                    session.add(
                        WBProductCardTag(
                            product_card_id=db_card.id,
                            account_id=account.id,
                            tag_id=tag.get("id"),
                            name=tag.get("name"),
                            color=tag.get("color"),
                        )
                    )
            collected += len(cards)
            request_cursor = payload.get("cursor") or {}
            cursor_total_raw = request_cursor.get("total")
            try:
                cursor_total = (
                    int(cursor_total_raw) if cursor_total_raw is not None else None
                )
            except (TypeError, ValueError):
                cursor_total = None
            if cursor_total is not None and cursor_total < page_limit:
                break
            if len(cards) < page_limit:
                break
        if request_cursor:
            await self._set_cursor(
                session,
                account_id=account.id,
                cursor_value={
                    "updatedAt": request_cursor.get("updatedAt"),
                    "nmID": request_cursor.get("nmID"),
                },
            )
        fallback_rows = await self._sync_price_only_core_skus(
            session, account_id=account.id
        )
        return {
            "status": "completed",
            "rows": collected,
            "pagesLoaded": pages_loaded,
            "fallbackCoreSkuRows": fallback_rows,
        }
