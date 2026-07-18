from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.supplies import SupplyRepository


class SuppliesService:
    def __init__(self) -> None:
        self.repo = SupplyRepository()

    async def list_supplies(
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
        return await self.repo.list_filtered(
            session,
            account_id=account_id,
            supply_id=supply_id,
            status_id=status_id,
            warehouse_name=warehouse_name,
            search=search,
            date_from=date_from,
            date_to=date_to,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )
