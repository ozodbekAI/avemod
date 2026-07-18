from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repository import SQLAlchemyRepository
from app.core.sorting import apply_sort_direction
from app.models.supplies import (
    WBSupply,
    WBSupplyAcceptanceOption,
    WBSupplyGood,
    WBSupplyPackage,
    WBSupplyWarehouse,
)


class SupplyRepository(SQLAlchemyRepository[WBSupply]):
    def __init__(self) -> None:
        super().__init__(WBSupply)

    async def list_filtered(
        self,
        session: AsyncSession,
        *,
        account_id=None,
        supply_id: int | None = None,
        status_id: int | None = None,
        warehouse_name: str | None = None,
        search: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort_by: str | None = None,
        sort_dir: str = "desc",
        limit=50,
        offset=0,
    ):
        sort_map = {
            "updated_date": WBSupply.updated_date,
            "supply_date": WBSupply.supply_date,
            "fact_date": WBSupply.fact_date,
            "supply_id": WBSupply.supply_id,
            "status_id": WBSupply.status_id,
            "warehouse_name": WBSupply.warehouse_name,
        }
        sort_column = sort_map.get(sort_by or "", WBSupply.updated_date)
        stmt = select(WBSupply).order_by(
            apply_sort_direction(sort_column, sort_dir),
            WBSupply.id.desc(),
        )
        if account_id is not None:
            stmt = stmt.where(WBSupply.account_id == account_id)
        if supply_id is not None:
            stmt = stmt.where(WBSupply.supply_id == supply_id)
        if status_id is not None:
            stmt = stmt.where(WBSupply.status_id == status_id)
        if warehouse_name is not None:
            stmt = stmt.where(
                or_(
                    WBSupply.warehouse_name.ilike(f"%{warehouse_name}%"),
                    WBSupply.actual_warehouse_name.ilike(f"%{warehouse_name}%"),
                )
            )
        if search is not None:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    WBSupply.warehouse_name.ilike(pattern),
                    WBSupply.actual_warehouse_name.ilike(pattern),
                )
            )
        if date_from is not None:
            stmt = stmt.where(
                or_(
                    WBSupply.updated_date >= datetime.combine(date_from, time.min),
                    WBSupply.supply_date >= datetime.combine(date_from, time.min),
                    WBSupply.fact_date >= datetime.combine(date_from, time.min),
                )
            )
        if date_to is not None:
            stmt = stmt.where(
                or_(
                    WBSupply.updated_date <= datetime.combine(date_to, time.max),
                    WBSupply.supply_date <= datetime.combine(date_to, time.max),
                    WBSupply.fact_date <= datetime.combine(date_to, time.max),
                )
            )
        return await self.list(session, statement=stmt, limit=limit, offset=offset)


class SupplyWarehouseRepository(SQLAlchemyRepository[WBSupplyWarehouse]):
    def __init__(self) -> None:
        super().__init__(WBSupplyWarehouse)


class SupplyAcceptanceOptionRepository(SQLAlchemyRepository[WBSupplyAcceptanceOption]):
    def __init__(self) -> None:
        super().__init__(WBSupplyAcceptanceOption)


class SupplyGoodRepository(SQLAlchemyRepository[WBSupplyGood]):
    def __init__(self) -> None:
        super().__init__(WBSupplyGood)


class SupplyPackageRepository(SQLAlchemyRepository[WBSupplyPackage]):
    def __init__(self) -> None:
        super().__init__(WBSupplyPackage)
