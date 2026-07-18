from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.models.product_cards import WBProductCard
from app.repositories.product_cards import ProductCardRepository


class ProductCardService:
    def __init__(self) -> None:
        self.repo = ProductCardRepository()

    async def list_cards(
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
    ) -> Page[WBProductCard]:
        return await self.repo.list_filtered(
            session,
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            barcode=barcode,
            brand=brand,
            subject_name=subject_name,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
