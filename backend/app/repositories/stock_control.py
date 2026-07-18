from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.stock_control import (
    StockControlExportArtifact,
    StockControlHandStockDraft,
    StockControlHandStockRow,
    StockControlImport,
    StockControlImportRow,
    StockControlMovement,
    StockControlRegionRow,
    StockControlRun,
    StockControlSettings,
    WarehouseRegionMapping,
)


class StockControlRepository:
    async def get_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> StockControlSettings | None:
        return (
            (
                await session.execute(
                    select(StockControlSettings)
                    .where(StockControlSettings.account_id == account_id)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def get_or_create_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> StockControlSettings:
        row = await self.get_settings(session, account_id=account_id)
        if row is not None:
            return row
        row = StockControlSettings(account_id=account_id)
        session.add(row)
        await session.flush()
        return row

    async def get_run(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlRun | None:
        return (
            (
                await session.execute(
                    select(StockControlRun)
                    .where(
                        StockControlRun.account_id == account_id,
                        StockControlRun.id == run_id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def list_runs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[StockControlRun]]:
        stmt = select(StockControlRun).where(StockControlRun.account_id == account_id)
        count_stmt = (
            select(func.count())
            .select_from(StockControlRun)
            .where(StockControlRun.account_id == account_id)
        )
        if run_type:
            stmt = stmt.where(StockControlRun.run_type == run_type)
            count_stmt = count_stmt.where(StockControlRun.run_type == run_type)
        total = int((await session.execute(count_stmt)).scalar_one())
        items = list(
            (
                await session.execute(
                    stmt.order_by(StockControlRun.id.desc()).limit(limit).offset(offset)
                )
            ).scalars()
        )
        return total, items

    async def list_region_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_id: int,
        status: str | None = None,
        nm_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[StockControlRegionRow]]:
        stmt = select(StockControlRegionRow).where(
            StockControlRegionRow.account_id == account_id,
            StockControlRegionRow.run_id == run_id,
        )
        count_stmt = (
            select(func.count())
            .select_from(StockControlRegionRow)
            .where(
                StockControlRegionRow.account_id == account_id,
                StockControlRegionRow.run_id == run_id,
            )
        )
        if status:
            stmt = stmt.where(StockControlRegionRow.status == status)
            count_stmt = count_stmt.where(StockControlRegionRow.status == status)
        if nm_id is not None:
            stmt = stmt.where(StockControlRegionRow.nm_id == nm_id)
            count_stmt = count_stmt.where(StockControlRegionRow.nm_id == nm_id)
        total = int((await session.execute(count_stmt)).scalar_one())
        rows = list(
            (
                await session.execute(
                    stmt.order_by(StockControlRegionRow.id.asc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return total, rows

    async def list_movements(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_id: int,
        movement_type: str | None = None,
        nm_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[StockControlMovement]]:
        stmt = select(StockControlMovement).where(
            StockControlMovement.account_id == account_id,
            StockControlMovement.run_id == run_id,
        )
        count_stmt = (
            select(func.count())
            .select_from(StockControlMovement)
            .where(
                StockControlMovement.account_id == account_id,
                StockControlMovement.run_id == run_id,
            )
        )
        if movement_type:
            stmt = stmt.where(StockControlMovement.movement_type == movement_type)
            count_stmt = count_stmt.where(
                StockControlMovement.movement_type == movement_type
            )
        if nm_id is not None:
            stmt = stmt.where(StockControlMovement.nm_id == nm_id)
            count_stmt = count_stmt.where(StockControlMovement.nm_id == nm_id)
        total = int((await session.execute(count_stmt)).scalar_one())
        rows = list(
            (
                await session.execute(
                    stmt.order_by(StockControlMovement.id.asc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return total, rows

    async def replace_run_outputs(
        self,
        session: AsyncSession,
        *,
        run_id: int,
        account_id: int,
        region_rows: list[StockControlRegionRow],
        movements: list[StockControlMovement],
    ) -> None:
        await session.execute(
            delete(StockControlRegionRow).where(StockControlRegionRow.run_id == run_id)
        )
        await session.execute(
            delete(StockControlMovement).where(StockControlMovement.run_id == run_id)
        )
        for row in region_rows:
            row.run_id = run_id
            row.account_id = account_id
            session.add(row)
        for row in movements:
            row.run_id = run_id
            row.account_id = account_id
            session.add(row)
        await session.flush()

    async def latest_successful_run(
        self, session: AsyncSession, *, account_id: int, run_type: str | None = None
    ) -> StockControlRun | None:
        stmt = select(StockControlRun).where(
            StockControlRun.account_id == account_id,
            StockControlRun.status.in_(("completed", "partial")),
        )
        if run_type:
            stmt = stmt.where(StockControlRun.run_type == run_type)
        return (
            (
                await session.execute(
                    stmt.order_by(
                        StockControlRun.finished_at.desc().nullslast(),
                        StockControlRun.id.desc(),
                    ).limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def queued_run_ids(
        self, session: AsyncSession, *, limit: int = 5
    ) -> list[int]:
        return list(
            (
                await session.execute(
                    select(StockControlRun.id)
                    .where(StockControlRun.status.in_(("queued", "running")))
                    .order_by(StockControlRun.id.asc())
                    .limit(limit)
                )
            ).scalars()
        )

    async def list_hand_drafts(
        self, session: AsyncSession, *, account_id: int, limit: int, offset: int
    ) -> tuple[int, list[StockControlHandStockDraft]]:
        stmt = select(StockControlHandStockDraft).where(
            StockControlHandStockDraft.account_id == account_id
        )
        total = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(StockControlHandStockDraft)
                    .where(StockControlHandStockDraft.account_id == account_id)
                )
            ).scalar_one()
        )
        rows = list(
            (
                await session.execute(
                    stmt.order_by(StockControlHandStockDraft.id.desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return total, rows

    async def get_hand_draft(
        self, session: AsyncSession, *, account_id: int, draft_id: int
    ) -> StockControlHandStockDraft | None:
        return (
            (
                await session.execute(
                    select(StockControlHandStockDraft)
                    .where(
                        StockControlHandStockDraft.account_id == account_id,
                        StockControlHandStockDraft.id == draft_id,
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def hand_rows(
        self, session: AsyncSession, *, account_id: int, draft_id: int
    ) -> list[StockControlHandStockRow]:
        return list(
            (
                await session.execute(
                    select(StockControlHandStockRow)
                    .where(
                        StockControlHandStockRow.account_id == account_id,
                        StockControlHandStockRow.draft_id == draft_id,
                    )
                    .order_by(StockControlHandStockRow.id.asc())
                )
            ).scalars()
        )

    async def replace_hand_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        draft_id: int,
        rows: list[StockControlHandStockRow],
    ) -> None:
        await session.execute(
            delete(StockControlHandStockRow).where(
                StockControlHandStockRow.draft_id == draft_id
            )
        )
        for row in rows:
            row.account_id = account_id
            row.draft_id = draft_id
            session.add(row)
        await session.flush()

    async def get_export(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlExportArtifact | None:
        return (
            (
                await session.execute(
                    select(StockControlExportArtifact)
                    .where(
                        StockControlExportArtifact.account_id == account_id,
                        StockControlExportArtifact.run_id == run_id,
                    )
                    .order_by(StockControlExportArtifact.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )


__all__ = [
    "StockControlRepository",
    "StockControlSettings",
    "StockControlRun",
    "StockControlRegionRow",
    "StockControlMovement",
    "StockControlHandStockDraft",
    "StockControlHandStockRow",
    "StockControlImport",
    "StockControlImportRow",
    "WarehouseRegionMapping",
    "StockControlExportArtifact",
]
