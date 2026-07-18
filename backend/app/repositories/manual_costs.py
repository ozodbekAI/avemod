from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.models.product_cards import CoreSKU
from app.models.manual_costs import ManualCost, ManualCostUpload
from app.core.pagination import Page


class ManualCostRepository(SQLAlchemyRepository[ManualCost]):
    def __init__(self) -> None:
        super().__init__(ManualCost)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ManualCost]:
        stmt = select(ManualCost).order_by(
            ManualCost.valid_from.desc().nullslast(),
            ManualCost.vendor_code.asc(),
            ManualCost.tech_size.asc().nullslast(),
        )
        if account_id is not None:
            stmt = stmt.where(ManualCost.account_id == account_id)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)

    async def close_overlapping_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int,
        effective_from: date,
    ) -> None:
        await session.execute(
            update(ManualCost)
            .where(
                ManualCost.account_id == account_id,
                ManualCost.sku_id == sku_id,
                or_(
                    ManualCost.valid_to.is_(None), ManualCost.valid_to >= effective_from
                ),
                or_(
                    ManualCost.valid_from.is_(None),
                    ManualCost.valid_from <= effective_from,
                ),
            )
            .values(valid_to=effective_from - timedelta(days=1))
        )

    async def delete_placeholder_rows_for_sku(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        sku_id: int,
    ) -> None:
        await session.execute(
            delete(ManualCost).where(
                ManualCost.account_id == account_id,
                ManualCost.sku_id == sku_id,
                or_(
                    ManualCost.is_placeholder.is_(True),
                    ManualCost.supplier == "AUTO_TEMPLATE",
                ),
            )
        )

    async def list_active_for_account(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        active_on: date,
    ) -> list[ManualCost]:
        return list(
            (
                await session.execute(
                    select(ManualCost).where(
                        ManualCost.account_id == account_id,
                        or_(
                            ManualCost.valid_from.is_(None),
                            ManualCost.valid_from <= active_on,
                        ),
                        or_(
                            ManualCost.valid_to.is_(None),
                            ManualCost.valid_to >= active_on,
                        ),
                    )
                )
            ).scalars()
        )

    async def list_unresolved_page(
        self,
        session: AsyncSession,
        *,
        account_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Page[ManualCost]:
        stmt = (
            select(ManualCost)
            .outerjoin(CoreSKU, CoreSKU.id == ManualCost.sku_id)
            .where(
                or_(
                    ManualCost.sku_id.is_(None),
                    ManualCost.is_ambiguous.is_(True),
                    CoreSKU.id.is_(None),
                    CoreSKU.is_active.is_(False),
                )
            )
            .order_by(
                ManualCost.valid_from.desc().nullslast(),
                ManualCost.vendor_code.asc(),
                ManualCost.tech_size.asc().nullslast(),
            )
        )
        if account_id is not None:
            stmt = stmt.where(ManualCost.account_id == account_id)
        return await self.list(session, statement=stmt, limit=limit, offset=offset)

    async def list_unresolved_for_product(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        sku_id: int | None = None,
        vendor_code: str | None = None,
        barcode: str | None = None,
        limit: int = 20,
    ) -> list[ManualCost]:
        product_filters = []
        if nm_id is not None:
            product_filters.append(ManualCost.nm_id == nm_id)
        if sku_id is not None:
            product_filters.append(ManualCost.sku_id == sku_id)
        if vendor_code:
            product_filters.append(ManualCost.vendor_code == vendor_code)
        if barcode:
            product_filters.append(ManualCost.barcode == barcode)
        if not product_filters:
            return []

        stmt = (
            select(ManualCost)
            .outerjoin(CoreSKU, CoreSKU.id == ManualCost.sku_id)
            .where(
                ManualCost.account_id == account_id,
                or_(
                    ManualCost.sku_id.is_(None),
                    ManualCost.is_ambiguous.is_(True),
                    CoreSKU.id.is_(None),
                    CoreSKU.is_active.is_(False),
                ),
                or_(*product_filters),
            )
            .order_by(
                ManualCost.valid_from.desc().nullslast(),
                ManualCost.vendor_code.asc(),
                ManualCost.tech_size.asc().nullslast(),
            )
            .limit(max(int(limit or 20), 1))
        )
        return list((await session.execute(stmt)).scalars())

    async def list_overlapping_for_account(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[ManualCost]:
        return list(
            (
                await session.execute(
                    select(ManualCost).where(
                        ManualCost.account_id == account_id,
                        or_(
                            ManualCost.valid_from.is_(None),
                            ManualCost.valid_from <= date_to,
                        ),
                        or_(
                            ManualCost.valid_to.is_(None),
                            ManualCost.valid_to >= date_from,
                        ),
                    )
                )
            ).scalars()
        )


class ManualCostUploadRepository(SQLAlchemyRepository[ManualCostUpload]):
    def __init__(self) -> None:
        super().__init__(ManualCostUpload)


class ManualCostTemplateRepository(SQLAlchemyRepository[CoreSKU]):
    def __init__(self) -> None:
        super().__init__(CoreSKU)

    async def list_template_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
    ) -> list[CoreSKU]:
        return list(
            (
                await session.execute(
                    select(CoreSKU)
                    .where(
                        CoreSKU.account_id == account_id, CoreSKU.is_active.is_(True)
                    )
                    .order_by(
                        CoreSKU.vendor_code.asc().nullslast(),
                        CoreSKU.tech_size.asc().nullslast(),
                        CoreSKU.barcode.asc().nullslast(),
                    )
                )
            ).scalars()
        )
