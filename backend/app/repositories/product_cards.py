from __future__ import annotations

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.product_cards import (
    CoreSKU,
    WBProductCard,
    WBProductCardCharacteristic,
    WBProductCardSize,
    WBProductCardTag,
)


class ProductCardRepository(SQLAlchemyRepository[WBProductCard]):
    def __init__(self) -> None:
        super().__init__(WBProductCard)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        brand: str | None = None,
        subject_name: str | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ):
        sort_map = {
            "updated_at_wb": WBProductCard.updated_at_wb,
            "nm_id": WBProductCard.nm_id,
            "vendor_code": WBProductCard.vendor_code,
            "title": WBProductCard.title,
            "brand": WBProductCard.brand,
            "subject_name": WBProductCard.subject_name,
        }
        sort_column = sort_map.get(sort_by or "", WBProductCard.updated_at_wb)
        stmt = select(WBProductCard).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBProductCard.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBProductCard.account_id == account_id)
        if nm_id is not None:
            stmt = stmt.where(WBProductCard.nm_id == nm_id)
        if vendor_code is not None:
            stmt = stmt.where(WBProductCard.vendor_code.ilike(f"%{vendor_code}%"))
        if brand is not None:
            stmt = stmt.where(WBProductCard.brand.ilike(f"%{brand}%"))
        if subject_name is not None:
            stmt = stmt.where(WBProductCard.subject_name.ilike(f"%{subject_name}%"))
        if barcode is not None:
            stmt = stmt.where(
                WBProductCard.id.in_(
                    select(WBProductCardSize.product_card_id).where(
                        WBProductCardSize.skus.contains([barcode])
                    )
                )
            )
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBProductCard.vendor_code.ilike(pattern),
                    WBProductCard.title.ilike(pattern),
                    WBProductCard.brand.ilike(pattern),
                    WBProductCard.subject_name.ilike(pattern),
                )
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)

    async def replace_children(
        self, session: AsyncSession, product_card_id: int
    ) -> None:
        await session.execute(
            delete(WBProductCardSize).where(
                WBProductCardSize.product_card_id == product_card_id
            )
        )
        await session.execute(
            delete(WBProductCardCharacteristic).where(
                WBProductCardCharacteristic.product_card_id == product_card_id
            )
        )
        await session.execute(
            delete(WBProductCardTag).where(
                WBProductCardTag.product_card_id == product_card_id
            )
        )


class CoreSKURepository(SQLAlchemyRepository[CoreSKU]):
    def __init__(self) -> None:
        super().__init__(CoreSKU)

    async def archive_missing_for_nm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        active_dedupe_keys: set[str],
    ) -> None:
        if active_dedupe_keys:
            await session.execute(
                update(CoreSKU)
                .where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.nm_id == nm_id,
                    CoreSKU.dedupe_key.not_in(active_dedupe_keys),
                )
                .values(is_active=False, status="archived")
            )
            await session.execute(
                update(CoreSKU)
                .where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.nm_id == nm_id,
                    CoreSKU.dedupe_key.in_(active_dedupe_keys),
                )
                .values(is_active=True, status="active")
            )
            return
        await session.execute(
            update(CoreSKU)
            .where(
                CoreSKU.account_id == account_id,
                CoreSKU.nm_id == nm_id,
            )
            .values(is_active=False, status="archived")
        )
