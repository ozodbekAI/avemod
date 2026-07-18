from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import Page
from app.models.prices import WBPriceSize
from app.repositories.prices import PriceRepository


class PriceService:
    def __init__(self) -> None:
        self.repo = PriceRepository()

    async def list_prices(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        nm_id: int | None = None,
        vendor_code: str | None = None,
        currency: str | None = None,
        is_bad_turnover: bool | None = None,
        search: str | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit: int = 50,
        offset: int = 0,
    ) -> Page[dict]:
        page = await self.repo.list_filtered(
            session,
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=vendor_code,
            currency=currency,
            is_bad_turnover=is_bad_turnover,
            search=search,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
        nm_ids = [row.nm_id for row in page.items]
        sizes_by_nm: dict[int, list[WBPriceSize]] = {nm: [] for nm in nm_ids}
        if nm_ids:
            size_stmt = select(WBPriceSize).where(WBPriceSize.nm_id.in_(nm_ids))
            if account_id is not None:
                size_stmt = size_stmt.where(WBPriceSize.account_id == account_id)
            size_rows = list(
                (
                    await session.execute(
                        size_stmt.order_by(
                            WBPriceSize.nm_id.asc(),
                            WBPriceSize.tech_size_name.asc().nullslast(),
                            WBPriceSize.id.asc(),
                        )
                    )
                ).scalars()
            )
            for size in size_rows:
                sizes_by_nm.setdefault(int(size.nm_id), []).append(size)

        items: list[dict] = []
        for row in page.items:
            sizes = sizes_by_nm.get(int(row.nm_id), [])
            price_candidates = [
                float(size.price) for size in sizes if size.price is not None
            ]
            discounted_candidates = [
                float(size.discounted_price)
                for size in sizes
                if size.discounted_price is not None
            ]
            items.append(
                {
                    "id": row.id,
                    "account_id": row.account_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "currency_iso_code": row.currency_iso_code,
                    "discount": row.discount,
                    "club_discount": row.club_discount,
                    "editable_size_price": row.editable_size_price,
                    "current_price": price_candidates[0] if price_candidates else None,
                    "discounted_price": discounted_candidates[0]
                    if discounted_candidates
                    else None,
                    "min_size_price": min(price_candidates)
                    if price_candidates
                    else None,
                    "max_size_price": max(price_candidates)
                    if price_candidates
                    else None,
                    "sizes": [
                        {
                            "tech_size": size.tech_size_name,
                            "price": float(size.price)
                            if size.price is not None
                            else None,
                            "discounted_price": float(size.discounted_price)
                            if size.discounted_price is not None
                            else None,
                            "club_discounted_price": (
                                float(size.club_discounted_price)
                                if size.club_discounted_price is not None
                                else None
                            ),
                        }
                        for size in sizes
                    ],
                    "created_at": row.created_at,
                }
            )
        return Page(total=page.total, limit=page.limit, offset=page.offset, items=items)
