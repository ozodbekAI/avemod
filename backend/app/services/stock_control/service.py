from __future__ import annotations

from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.stock_fallback import is_total_stock_row
from app.core.time import utcnow
from app.domain.stock_control.algorithms import (
    DemandRow,
    HandStockRow,
    StockRow,
    compute_store_balance,
    compute_return_excess,
    compute_ship_from_hand,
)
from app.domain.stock_control.io import (
    build_export_xlsx,
    export_base64,
    hand_stock_template_csv,
    parse_table_upload,
)
from app.domain.stock_control.regions import normalize_region
from app.models.analytics import WBRegionSalesDaily
from app.models.orders import WBOrder
from app.models.stock_control import (
    StockControlExportArtifact,
    StockControlHandStockDraft,
    StockControlHandStockRow,
    StockControlImport,
    StockControlImportRow,
    StockControlMovement,
    StockControlRegionRow,
    StockControlRun,
    WarehouseRegionMapping,
)
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.repositories.stock_control import StockControlRepository
from app.schemas.portal import (
    PortalActionRead,
    PortalStockOpsInsightsRead,
    PortalStockOpsRunRead,
    PortalStockOpsRunsPage,
)
from app.schemas.stock_control import (
    HandStockDraftCreate,
    HandStockDraftRead,
    HandStockDraftUpdate,
    HandStockDraftsPage,
    HandStockRowIn,
    HandStockRowRead,
    StockControlExportRead,
    StockControlImportPreview,
    StockControlImportRead,
    StockControlMovementRead,
    StockControlMovementsPage,
    StockControlOverviewRead,
    StockControlRegionRowRead,
    StockControlRegionRowsPage,
    StockControlRunCreate,
    StockControlRunRead,
    StockControlRunsPage,
    StockControlSettingsRead,
    StockControlSettingsUpdate,
    StockControlStatusRead,
    StockControlTemplateRead,
    StockControlStoreBalancePreviewRequest,
)


class StockControlService:
    READ_STATUSES = {"completed", "partial", "failed", "cancelled", "queued", "running"}

    def __init__(self) -> None:
        self.repo = StockControlRepository()

    async def status(
        self, session: AsyncSession, *, account_id: int
    ) -> StockControlStatusRead:
        total_runs, runs = await self.repo.list_runs(
            session, account_id=account_id, limit=6, offset=0
        )
        latest_success = await self.repo.latest_successful_run(
            session, account_id=account_id
        )
        latest_stock_at = (
            await session.execute(
                select(func.max(WBStockSnapshot.snapshot_at)).where(
                    WBStockSnapshot.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        latest_region_demand_at = (
            await session.execute(
                select(func.max(WBRegionSalesDaily.stat_date)).where(
                    WBRegionSalesDaily.account_id == account_id
                )
            )
        ).scalar_one_or_none()
        latest = runs[0] if runs else None
        if latest is not None and latest.status == "running":
            status = "running"
        elif latest_success is not None:
            status = "ok" if latest_success.status == "completed" else "partial"
        elif total_runs:
            status = "failed" if latest and latest.status == "failed" else "empty"
        else:
            status = "empty"
        summary = dict(getattr(latest_success, "result_summary_json", None) or {})
        coverage, unmapped = await self._warehouse_mapping_coverage(
            session, account_id=account_id
        )
        latest_run_read = (
            StockControlRunRead.model_validate(latest) if latest is not None else None
        )
        latest_runs = [StockControlRunRead.model_validate(row) for row in runs]
        return StockControlStatusRead(
            status=status,
            account_id=account_id,
            last_success_at=latest_success.finished_at
            if latest_success is not None
            else None,
            latest_stock_snapshot_at=latest_stock_at,
            latest_region_demand_at=latest_region_demand_at,
            warehouse_mapping_coverage_percent=coverage,
            products_analyzed=int(summary.get("products") or 0),
            regions_analyzed=int(summary.get("regions") or 0),
            movements_generated=int(summary.get("movements") or 0),
            unmapped_warehouses=unmapped,
            latest_run=latest_run_read,
            latest_runs=latest_runs,
            summary=summary,
            source_freshness={
                "stock_snapshot_at": latest_stock_at,
                "regional_demand_at": latest_region_demand_at,
                "latest_success_at": latest_success.finished_at
                if latest_success is not None
                else None,
            },
            mapping_summary={
                "coverage_percent": coverage,
                "unmapped_warehouses": unmapped,
            },
            warnings=(["warehouse_mapping_incomplete"] if unmapped else []),
        )

    async def get_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> StockControlSettingsRead:
        row = await self.repo.get_or_create_settings(session, account_id=account_id)
        return StockControlSettingsRead.model_validate(row)

    async def update_settings(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: StockControlSettingsUpdate,
    ) -> StockControlSettingsRead:
        row = await self.repo.get_or_create_settings(session, account_id=account_id)
        data = payload.model_dump(exclude_unset=True)
        for key, value in data.items():
            if value is not None:
                setattr(row, key, value)
        await session.flush()
        return StockControlSettingsRead.model_validate(row)

    async def preview_import(
        self, *, file_name: str, content: bytes, import_type: str
    ) -> StockControlImportPreview:
        metadata, _rows = parse_table_upload(
            content, file_name, import_type=import_type
        )
        return StockControlImportPreview(**metadata)

    async def import_regional_supply(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        file_name: str,
        content: bytes,
        created_by_user_id: int | None,
    ) -> StockControlImportRead:
        metadata, rows = parse_table_upload(
            content, file_name, import_type="regional_supply"
        )
        import_row = StockControlImport(
            account_id=account_id,
            import_type="regional_supply",
            status="imported",
            file_name=file_name,
            sheet_name=metadata.get("sheet_name"),
            rows_total=len(rows),
            metadata_json=metadata,
            created_by_user_id=created_by_user_id,
        )
        session.add(import_row)
        await session.flush()
        for row in rows:
            session.add(
                StockControlImportRow(
                    import_id=import_row.id,
                    account_id=account_id,
                    row_type="regional_supply",
                    nm_id=row.get("nm_id"),
                    vendor_code=row.get("vendor_code"),
                    barcode=row.get("barcode"),
                    size_name=row.get("size_name"),
                    region=normalize_region(row.get("region")),
                    warehouse_name=row.get("warehouse_name"),
                    orders_qty=Decimal(str(row.get("orders_qty") or 0)),
                    stock_qty=Decimal(str(row.get("stock_qty") or 0)),
                    raw_json=row,
                )
            )
        await session.flush()
        return StockControlImportRead.model_validate(import_row)

    async def create_hand_draft(
        self,
        session: AsyncSession,
        *,
        payload: HandStockDraftCreate,
        created_by_user_id: int | None,
    ) -> HandStockDraftRead:
        draft = StockControlHandStockDraft(
            account_id=payload.account_id,
            name=payload.name,
            status="draft",
            created_by_user_id=created_by_user_id,
        )
        session.add(draft)
        await session.flush()
        await self.repo.replace_hand_rows(
            session,
            account_id=payload.account_id,
            draft_id=draft.id,
            rows=[
                self._hand_row_model(payload.account_id, draft.id, row)
                for row in payload.rows
            ],
        )
        return await self.get_hand_draft(
            session, account_id=payload.account_id, draft_id=draft.id
        )

    async def list_hand_drafts(
        self, session: AsyncSession, *, account_id: int, limit: int, offset: int
    ) -> HandStockDraftsPage:
        total, drafts = await self.repo.list_hand_drafts(
            session, account_id=account_id, limit=limit, offset=offset
        )
        return HandStockDraftsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                await self._draft_read(session, account_id=account_id, draft=draft)
                for draft in drafts
            ],
        )

    async def get_hand_draft(
        self, session: AsyncSession, *, account_id: int, draft_id: int
    ) -> HandStockDraftRead:
        draft = await self.repo.get_hand_draft(
            session, account_id=account_id, draft_id=draft_id
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="Hand stock draft not found")
        return await self._draft_read(session, account_id=account_id, draft=draft)

    async def update_hand_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        draft_id: int,
        payload: HandStockDraftUpdate,
    ) -> HandStockDraftRead:
        draft = await self.repo.get_hand_draft(
            session, account_id=account_id, draft_id=draft_id
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="Hand stock draft not found")
        if payload.name is not None:
            draft.name = payload.name
        if payload.status is not None:
            draft.status = payload.status
        if payload.rows is not None:
            await self.repo.replace_hand_rows(
                session,
                account_id=account_id,
                draft_id=draft_id,
                rows=[
                    self._hand_row_model(account_id, draft_id, row)
                    for row in payload.rows
                ],
            )
        await session.flush()
        return await self._draft_read(session, account_id=account_id, draft=draft)

    async def delete_hand_draft(
        self, session: AsyncSession, *, account_id: int, draft_id: int
    ) -> dict[str, Any]:
        draft = await self.repo.get_hand_draft(
            session, account_id=account_id, draft_id=draft_id
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="Hand stock draft not found")
        await session.delete(draft)
        await session.flush()
        return {"status": "deleted", "id": draft_id}

    def hand_stock_template(self) -> StockControlTemplateRead:
        return StockControlTemplateRead(
            file_name="hand_stock_template.csv", content=hand_stock_template_csv()
        )

    async def preview_store_balance(
        self,
        session: AsyncSession,
        *,
        payload: StockControlStoreBalancePreviewRequest,
    ) -> dict[str, Any]:
        source_account_id = int(payload.source_account_id or payload.account_id)
        (
            source_rows,
            source_snapshot_at,
            source_warnings,
        ) = await self._collect_stock_rows(session, account_id=source_account_id)
        (
            target_rows,
            target_snapshot_at,
            target_warnings,
        ) = await self._collect_stock_rows(
            session, account_id=int(payload.target_account_id)
        )
        result = compute_store_balance(
            source_stock_rows=source_rows,
            target_stock_rows=target_rows,
            mode=payload.mode,
            min_source_stock=payload.min_source_stock,
            max_target_stock=payload.max_target_stock,
            size_aware=payload.size_aware,
            excluded_nm_ids=payload.excluded_nm_ids,
        )
        summary = dict(result.get("summary") or {})
        errors = []
        if source_account_id == int(payload.target_account_id):
            errors.append("same_account")
        if int(summary.get("shared_skus_count") or 0) == 0:
            errors.append("no_shared_skus")
        warnings = [*source_warnings, *target_warnings]
        return {
            "status": "ok" if not errors else "blocked",
            "kind": "store_balance",
            "ready_to_run": not errors,
            "source_account_id": source_account_id,
            "target_account_id": int(payload.target_account_id),
            "source_skus_count": summary.get("source_skus_count", 0),
            "target_skus_count": summary.get("target_skus_count", 0),
            "shared_skus_count": summary.get("shared_skus_count", 0),
            "source_excess_units": summary.get("source_excess_units", 0),
            "target_shortage_units": summary.get("target_shortage_units", 0),
            "planned_units": summary.get("planned_units", 0),
            "warnings": warnings,
            "errors": errors,
            "data_freshness": {
                "source_stock_snapshot_at": source_snapshot_at,
                "target_stock_snapshot_at": target_snapshot_at,
                "stock_snapshot_at": source_snapshot_at,
            },
            "marketplace_change": False,
            "can_execute": False,
        }

    async def create_run(
        self,
        session: AsyncSession,
        *,
        payload: StockControlRunCreate,
        requested_by_user_id: int | None,
    ) -> StockControlRunRead:
        settings = await self.repo.get_or_create_settings(
            session, account_id=payload.account_id
        )
        run = StockControlRun(
            account_id=payload.account_id,
            run_type=payload.run_type,
            status="queued",
            source_mode=payload.source_mode,
            allocation_mode=payload.allocation_mode,
            priority_strategy=payload.priority_strategy,
            requested_by_user_id=requested_by_user_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            settings_snapshot_json={
                **StockControlSettingsRead.model_validate(settings).model_dump(
                    mode="json"
                ),
                **payload.settings_override,
            },
            input_summary_json={
                "demand_run_id": payload.demand_run_id,
                "hand_stock_draft_id": payload.hand_stock_draft_id,
                "regional_supply_import_id": payload.regional_supply_import_id,
                "ship_all_available": payload.ship_all_available,
                "target_account_id": payload.target_account_id,
                "mode": payload.mode,
                "min_source_stock": payload.min_source_stock,
                "max_target_stock": payload.max_target_stock,
                "size_aware": payload.size_aware,
                "excluded_nm_ids": payload.excluded_nm_ids,
                "external_write_enabled": False,
            },
        )
        session.add(run)
        await session.flush()
        return StockControlRunRead.model_validate(run)

    async def list_runs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_type: str | None,
        limit: int,
        offset: int,
    ) -> StockControlRunsPage:
        total, runs = await self.repo.list_runs(
            session,
            account_id=account_id,
            run_type=run_type,
            limit=limit,
            offset=offset,
        )
        return StockControlRunsPage(
            status="ok" if runs else "empty",
            total=total,
            limit=limit,
            offset=offset,
            items=[StockControlRunRead.model_validate(row) for row in runs],
        )

    async def get_run(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlRunRead:
        run = await self._required_run(session, account_id=account_id, run_id=run_id)
        return StockControlRunRead.model_validate(run)

    async def retry_run(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlRunRead:
        run = await self._required_run(session, account_id=account_id, run_id=run_id)
        run.status = "queued"
        run.error_code = None
        run.error_summary = None
        run.finished_at = None
        await session.flush()
        return StockControlRunRead.model_validate(run)

    async def cancel_run(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlRunRead:
        run = await self._required_run(session, account_id=account_id, run_id=run_id)
        if run.status in {"completed", "partial"}:
            raise HTTPException(
                status_code=409,
                detail="Completed stock control runs cannot be cancelled",
            )
        run.status = "cancelled"
        run.finished_at = utcnow()
        await session.flush()
        return StockControlRunRead.model_validate(run)

    async def process_queued_runs(
        self, session: AsyncSession, *, max_runs: int = 5
    ) -> int:
        run_ids = await self.repo.queued_run_ids(session, limit=max_runs)
        processed = 0
        for run_id in run_ids:
            await self.process_run(session, run_id=run_id)
            processed += 1
        return processed

    async def process_run(
        self, session: AsyncSession, *, run_id: int
    ) -> StockControlRun:
        run = await session.get(StockControlRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Stock control run not found")
        if run.status == "cancelled":
            return run
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        run.heartbeat_at = utcnow()
        await session.flush()
        try:
            settings = dict(run.settings_snapshot_json or {})
            demand_rows = await self._collect_demand_rows(session, run=run)
            if (
                run.run_type == "return_excess"
                and run.source_mode == "regional_supply_import"
            ):
                (
                    stock_rows,
                    source_snapshot_at,
                    stock_warnings,
                ) = await self._collect_import_stock_rows(session, run=run)
            else:
                (
                    stock_rows,
                    source_snapshot_at,
                    stock_warnings,
                ) = await self._collect_stock_rows(session, account_id=run.account_id)
            run.source_snapshot_at = source_snapshot_at
            if run.run_type == "return_excess":
                result = compute_return_excess(
                    demand_rows=demand_rows,
                    stock_rows=stock_rows,
                    excluded_regions=settings.get("excluded_regions_json") or [],
                    minimum_keep_per_size=int(
                        settings.get("minimum_keep_per_size") or 0
                    ),
                )
                unmatched: list[dict[str, Any]] = []
            elif run.run_type == "ship_from_hand":
                hand_rows = await self._hand_rows_for_run(session, run=run)
                result = compute_ship_from_hand(
                    demand_rows=demand_rows,
                    stock_rows=stock_rows,
                    hand_rows=hand_rows,
                    excluded_regions=settings.get("excluded_regions_json") or [],
                    allocation_mode=str(run.allocation_mode or "redistribute"),
                    ship_all_available=bool(
                        (run.input_summary_json or {}).get("ship_all_available")
                        or settings.get("ship_all_available_default")
                    ),
                    default_il_profile=settings.get("default_il_profile_json") or {},
                    minimum_history_orders=int(
                        settings.get("minimum_history_orders") or 10
                    ),
                )
                unmatched = list(result.get("unmatched") or [])
            elif run.run_type == "store_balance":
                target_account_id = int(
                    (run.input_summary_json or {}).get("target_account_id") or 0
                )
                if target_account_id <= 0:
                    raise ValueError("target_account_id is required for store_balance")
                (
                    target_stock_rows,
                    target_snapshot_at,
                    target_warnings,
                ) = await self._collect_stock_rows(
                    session, account_id=target_account_id
                )
                result = compute_store_balance(
                    source_stock_rows=stock_rows,
                    target_stock_rows=target_stock_rows,
                    mode=str(
                        (run.input_summary_json or {}).get("mode") or "donor_recipient"
                    ),
                    min_source_stock=int(
                        (run.input_summary_json or {}).get("min_source_stock") or 0
                    ),
                    max_target_stock=(run.input_summary_json or {}).get(
                        "max_target_stock"
                    ),
                    size_aware=bool(
                        (run.input_summary_json or {}).get("size_aware", True)
                    ),
                    excluded_nm_ids=(run.input_summary_json or {}).get(
                        "excluded_nm_ids"
                    )
                    or [],
                )
                unmatched = list(result.get("unmatched") or [])
                stock_warnings = [*stock_warnings, *target_warnings]
                run.input_summary_json = {
                    **dict(run.input_summary_json or {}),
                    "target_stock_snapshot_at": target_snapshot_at.isoformat()
                    if target_snapshot_at is not None
                    else None,
                }
            else:
                raise ValueError(f"unsupported stock control run type: {run.run_type}")

            now = utcnow()
            region_models = [
                self._region_model(run.account_id, item, created_at=now)
                for item in result["region_rows"]
            ]
            movement_models = [
                self._movement_model(run.account_id, item)
                for item in result["movements"]
            ]
            await self.repo.replace_run_outputs(
                session,
                run_id=run.id,
                account_id=run.account_id,
                region_rows=region_models,
                movements=movement_models,
            )
            summary = dict(result.get("summary") or {})
            summary["warnings"] = [*stock_warnings, *summary.get("warnings", [])]
            run.result_summary_json = summary
            run.input_summary_json = {
                **dict(run.input_summary_json or {}),
                "demand_rows": len(demand_rows),
                "stock_rows": len(stock_rows),
                "external_write_enabled": False,
                "marketplace_change": False,
            }
            run.eligible_products = int(summary.get("products") or 0)
            run.rows_processed = len(demand_rows) + len(stock_rows)
            run.rows_created = len(region_models) + len(movement_models)
            run.rows_skipped = len(unmatched)
            run.status = "partial" if unmatched or stock_warnings else "completed"
            run.finished_at = utcnow()
            run.heartbeat_at = utcnow()
            await self._replace_export(
                session,
                run=run,
                region_rows=result["region_rows"],
                movements=result["movements"],
                unmatched=unmatched,
            )
            await session.flush()
            return run
        except Exception as exc:
            run.status = "failed"
            run.finished_at = utcnow()
            run.error_code = exc.__class__.__name__
            run.error_summary = str(exc)[:1000]
            await session.flush()
            return run

    async def overview(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlOverviewRead:
        run = await self._required_run(session, account_id=account_id, run_id=run_id)
        total_rows, _ = await self.repo.list_region_rows(
            session, account_id=account_id, run_id=run_id, limit=1, offset=0
        )
        total_movements, _ = await self.repo.list_movements(
            session, account_id=account_id, run_id=run_id, limit=1, offset=0
        )
        return StockControlOverviewRead(
            run=StockControlRunRead.model_validate(run),
            summary=dict(run.result_summary_json or {}),
            region_summary={"total": total_rows, **dict(run.result_summary_json or {})},
            movement_summary={"total": total_movements},
            warnings=list((run.result_summary_json or {}).get("warnings") or []),
        )

    async def region_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_id: int,
        status: str | None,
        nm_id: int | None,
        limit: int,
        offset: int,
    ) -> StockControlRegionRowsPage:
        await self._required_run(session, account_id=account_id, run_id=run_id)
        total, rows = await self.repo.list_region_rows(
            session,
            account_id=account_id,
            run_id=run_id,
            status=status,
            nm_id=nm_id,
            limit=limit,
            offset=offset,
        )
        return StockControlRegionRowsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[StockControlRegionRowRead.model_validate(row) for row in rows],
        )

    async def movements(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_id: int,
        movement_type: str | None,
        limit: int,
        offset: int,
    ) -> StockControlMovementsPage:
        await self._required_run(session, account_id=account_id, run_id=run_id)
        total, rows = await self.repo.list_movements(
            session,
            account_id=account_id,
            run_id=run_id,
            movement_type=movement_type,
            limit=limit,
            offset=offset,
        )
        return StockControlMovementsPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[StockControlMovementRead.model_validate(row) for row in rows],
        )

    async def unmatched(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_id: int,
        limit: int,
        offset: int,
    ) -> StockControlRegionRowsPage:
        return await self.region_rows(
            session,
            account_id=account_id,
            run_id=run_id,
            status="unmatched",
            nm_id=None,
            limit=limit,
            offset=offset,
        )

    async def export(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlExportRead:
        run = await self._required_run(session, account_id=account_id, run_id=run_id)
        artifact = await self.repo.get_export(
            session, account_id=account_id, run_id=run_id
        )
        if artifact is None:
            raise HTTPException(status_code=404, detail="Export artifact not found")
        return StockControlExportRead(
            run_id=run.id,
            file_name=artifact.file_name,
            content_type=artifact.content_type,
            content_base64=export_base64(artifact.content or b""),
            metadata=artifact.metadata_json or {},
        )

    async def compatibility_run(
        self, session: AsyncSession, payload, *, requested_by_user_id: int | None = None
    ) -> PortalStockOpsRunRead:
        if payload.run_type == "ship_from_hand" and not (payload.payload or {}).get(
            "hand_stock_draft_id"
        ):
            return PortalStockOpsRunRead(
                status="disabled",
                run_type=payload.run_type,
                account_id=payload.account_id,
                message="ship_from_hand requires a local hand stock draft",
                raw={
                    "mode": "local",
                    "marketplace_change": False,
                    "can_execute": False,
                },
            )
        if payload.run_type == "store_balance" and not (payload.payload or {}).get(
            "target_account_id"
        ):
            return PortalStockOpsRunRead(
                status="disabled",
                run_type=payload.run_type,
                account_id=payload.account_id,
                message="store_balance requires target_account_id",
                raw={
                    "mode": "local",
                    "marketplace_change": False,
                    "can_execute": False,
                },
            )
        create_payload = StockControlRunCreate(
            account_id=payload.account_id,
            run_type=payload.run_type,
            source_mode="finance_db",
            allocation_mode=str(
                (payload.payload or {}).get("allocation_mode") or "redistribute"
            ),
            date_from=(payload.payload or {}).get("date_from"),
            date_to=(payload.payload or {}).get("date_to"),
            hand_stock_draft_id=(payload.payload or {}).get("hand_stock_draft_id"),
            ship_all_available=(payload.payload or {}).get("ship_all_available"),
            target_account_id=(payload.payload or {}).get("target_account_id"),
            mode=(payload.payload or {}).get("mode"),
            min_source_stock=int((payload.payload or {}).get("min_source_stock") or 0),
            max_target_stock=(payload.payload or {}).get("max_target_stock"),
            size_aware=bool((payload.payload or {}).get("size_aware", True)),
            excluded_nm_ids=(payload.payload or {}).get("excluded_nm_ids") or [],
            settings_override=(payload.payload or {}).get("settings_override") or {},
        )
        run = await self.create_run(
            session, payload=create_payload, requested_by_user_id=requested_by_user_id
        )
        return PortalStockOpsRunRead(
            status="queued",
            run_type=run.run_type,
            run_id=run.id,
            account_id=run.account_id,
            summary=run.result_summary_json,
            message="Local Stock Control run queued. No WB operation will be performed.",
            raw={"mode": "local", "marketplace_change": False, "can_execute": False},
        )

    async def compatibility_runs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_type: str | None,
        limit: int,
        offset: int,
    ) -> PortalStockOpsRunsPage:
        page = await self.list_runs(
            session,
            account_id=account_id,
            run_type=run_type,
            limit=limit,
            offset=offset,
        )
        return PortalStockOpsRunsPage(
            status="ok" if page.items else "ok",
            total=page.total,
            limit=limit,
            offset=offset,
            items=[
                PortalStockOpsRunRead(
                    status=self._stockops_status(item.status),
                    run_type=item.run_type,
                    run_id=item.id,
                    account_id=item.account_id,
                    summary=item.result_summary_json,
                    export_url=f"/api/v1/portal/stock-control/runs/{item.id}/export",
                    raw={
                        "mode": "local",
                        "marketplace_change": False,
                        "can_execute": False,
                    },
                )
                for item in page.items
            ],
        )

    async def product_stock_insights(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        limit: int = 20,
    ) -> PortalStockOpsInsightsRead:
        run = await self.repo.latest_successful_run(session, account_id=account_id)
        if run is None:
            return PortalStockOpsInsightsRead(
                status="empty",
                account_id=account_id,
                nm_id=nm_id,
                summary={"mode": "local"},
            )
        _total, rows = await self.repo.list_region_rows(
            session,
            account_id=account_id,
            run_id=run.id,
            nm_id=nm_id,
            limit=limit,
            offset=0,
        )
        _movement_total, movements = await self.repo.list_movements(
            session, account_id=account_id, run_id=run.id, limit=limit, offset=0
        )
        candidates = [
            {
                "run_id": run.id,
                "nm_id": row.nm_id,
                "vendor_code": row.vendor_code,
                "region": row.region,
                "status": row.status,
                "quantity": abs(float(row.delta_qty or 0)),
                "marketplace_change": False,
            }
            for row in rows
            if row.status in {"shortage", "excess"}
        ]
        return PortalStockOpsInsightsRead(
            status="ok" if candidates or movements else "empty",
            account_id=account_id,
            nm_id=nm_id,
            summary={
                **dict(run.result_summary_json or {}),
                "mode": "local",
                "latest_run_id": run.id,
            },
            latest_runs=[
                PortalStockOpsRunRead(
                    status=self._stockops_status(run.status),
                    run_type=run.run_type,
                    run_id=run.id,
                    account_id=account_id,
                    summary=run.result_summary_json,
                    raw={"mode": "local"},
                )
            ],
            regional_candidates=candidates,
            action_candidates=[self._movement_candidate(item) for item in movements],
        )

    async def action_candidates(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        limit: int = 20,
    ) -> tuple[list[PortalActionRead], str | None]:
        run = await self.repo.latest_successful_run(session, account_id=account_id)
        if run is None:
            return [], None
        _total, movements = await self.repo.list_movements(
            session,
            account_id=account_id,
            run_id=run.id,
            nm_id=nm_id,
            limit=limit,
            offset=0,
        )
        actions = []
        for movement in movements:
            item = self._movement_candidate(movement)
            qty = int(item.get("quantity") or 0)
            if qty <= 0:
                continue
            actions.append(
                PortalActionRead(
                    id=f"stock_control:{item.get('run_id')}:{item.get('id')}",
                    source="stock_control",
                    source_module="stockops",
                    source_id=f"stock_control:{item.get('run_id')}:{item.get('id')}",
                    account_id=account_id,
                    nm_id=item.get("nm_id"),
                    action_type=str(
                        item.get("movement_type") or "regional_redistribution"
                    ),
                    title="Перераспределить остаток по регионам",
                    priority="P2",
                    severity="high",
                    status="new",
                    reason=str(
                        item.get("business_explanation")
                        or "Regional stock imbalance detected."
                    ),
                    next_step="Откройте Stock Control plan, проверьте движение donor -> recipient, затем выполните изменения вручную в WB при необходимости.",
                    expected_effect_amount=None,
                    confidence="medium",
                    payload=item,
                    raw=item,
                    can_update_status=True,
                    can_update=True,
                    can_execute=False,
                    can_update_reason=None,
                    guided_fix={
                        "id": "open_stock_control",
                        "marketplace_change": False,
                        "requires_confirmation": True,
                    },
                )
            )
        return actions, None

    def _movement_candidate(self, movement: StockControlMovement) -> dict[str, Any]:
        return {
            "id": movement.id,
            "run_id": movement.run_id,
            "nm_id": movement.nm_id,
            "vendor_code": movement.vendor_code,
            "movement_type": movement.movement_type,
            "donor_region": movement.donor_region,
            "recipient_region": movement.recipient_region,
            "quantity": float(movement.quantity or 0),
            "business_explanation": movement.business_explanation,
            "marketplace_change": False,
        }

    async def _required_run(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> StockControlRun:
        run = await self.repo.get_run(session, account_id=account_id, run_id=run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Stock control run not found")
        return run

    async def _collect_demand_rows(
        self, session: AsyncSession, *, run: StockControlRun
    ) -> list[DemandRow]:
        input_summary = dict(run.input_summary_json or {})
        regional_supply_import_id = input_summary.get("regional_supply_import_id")
        if run.source_mode == "regional_supply_import" and regional_supply_import_id:
            import_row = await session.get(
                StockControlImport, int(regional_supply_import_id)
            )
            if import_row is None or int(import_row.account_id) != int(run.account_id):
                raise ValueError("regional_supply_import_id not found for this account")
            stmt = select(StockControlImportRow).where(
                StockControlImportRow.account_id == run.account_id,
                StockControlImportRow.import_id == import_row.id,
            )
            return [
                DemandRow(
                    nm_id=item.nm_id,
                    vendor_code=item.vendor_code,
                    barcode=item.barcode,
                    chrt_id=None,
                    size_name=item.size_name,
                    region=normalize_region(item.region or item.warehouse_name),
                    orders_qty=int(item.orders_qty or 0),
                    subject=(item.raw_json or {}).get("subject"),
                    brand=(item.raw_json or {}).get("brand"),
                    source="regional_supply_import",
                )
                for item in (await session.execute(stmt)).scalars()
                if int(item.orders_qty or 0) > 0
            ]

        date_from_dt = (
            datetime.combine(run.date_from, time.min, tzinfo=UTC)
            if run.date_from
            else None
        )
        date_to_dt = (
            datetime.combine(run.date_to, time.max, tzinfo=UTC) if run.date_to else None
        )
        stmt = select(
            WBOrder.nm_id,
            WBOrder.supplier_article,
            WBOrder.barcode,
            WBOrder.region_name,
            func.count(WBOrder.id),
        ).where(
            WBOrder.account_id == run.account_id,
            or_(WBOrder.is_cancel.is_(False), WBOrder.is_cancel.is_(None)),
        )
        if date_from_dt is not None:
            stmt = stmt.where(WBOrder.date >= date_from_dt)
        if date_to_dt is not None:
            stmt = stmt.where(WBOrder.date <= date_to_dt)
        stmt = stmt.group_by(
            WBOrder.nm_id,
            WBOrder.supplier_article,
            WBOrder.barcode,
            WBOrder.region_name,
        )
        rows = [
            DemandRow(
                nm_id=nm_id,
                vendor_code=article,
                barcode=barcode,
                chrt_id=None,
                size_name=None,
                region=normalize_region(region),
                orders_qty=int(qty or 0),
            )
            for nm_id, article, barcode, region, qty in (
                await session.execute(stmt)
            ).all()
            if qty
        ]
        if rows:
            return rows
        regional_stmt = select(
            WBRegionSalesDaily.nm_id,
            WBRegionSalesDaily.vendor_code,
            WBRegionSalesDaily.region_name,
            func.sum(WBRegionSalesDaily.sale_quantity),
        ).where(WBRegionSalesDaily.account_id == run.account_id)
        if run.date_from is not None:
            regional_stmt = regional_stmt.where(
                WBRegionSalesDaily.stat_date >= run.date_from
            )
        if run.date_to is not None:
            regional_stmt = regional_stmt.where(
                WBRegionSalesDaily.stat_date <= run.date_to
            )
        regional_stmt = regional_stmt.group_by(
            WBRegionSalesDaily.nm_id,
            WBRegionSalesDaily.vendor_code,
            WBRegionSalesDaily.region_name,
        )
        return [
            DemandRow(
                nm_id=nm_id,
                vendor_code=vendor_code,
                barcode=None,
                chrt_id=None,
                size_name=None,
                region=normalize_region(region),
                orders_qty=int(qty or 0),
                source="region_sales_daily",
            )
            for nm_id, vendor_code, region, qty in (
                await session.execute(regional_stmt)
            ).all()
            if qty
        ]

    async def _collect_import_stock_rows(
        self, session: AsyncSession, *, run: StockControlRun
    ) -> tuple[list[StockRow], datetime | None, list[str]]:
        input_summary = dict(run.input_summary_json or {})
        regional_supply_import_id = input_summary.get("regional_supply_import_id")
        if not regional_supply_import_id:
            raise ValueError(
                "regional_supply_import_id is required for imported return stock"
            )
        import_row = await session.get(
            StockControlImport, int(regional_supply_import_id)
        )
        if import_row is None or int(import_row.account_id) != int(run.account_id):
            raise ValueError("regional_supply_import_id not found for this account")
        stmt = select(StockControlImportRow).where(
            StockControlImportRow.account_id == run.account_id,
            StockControlImportRow.import_id == import_row.id,
        )
        rows = [
            StockRow(
                nm_id=item.nm_id,
                vendor_code=item.vendor_code,
                barcode=item.barcode,
                chrt_id=None,
                size_name=item.size_name,
                region=normalize_region(item.region or item.warehouse_name),
                warehouse_id=None,
                warehouse_name=item.warehouse_name,
                quantity=int(item.stock_qty or 0),
                subject=(item.raw_json or {}).get("subject"),
                brand=(item.raw_json or {}).get("brand"),
                source="regional_supply_import",
            )
            for item in (await session.execute(stmt)).scalars()
            if int(item.stock_qty or 0) > 0
        ]
        return rows, import_row.created_at, ([] if rows else ["import_stock_empty"])

    async def _collect_stock_rows(
        self, session: AsyncSession, *, account_id: int
    ) -> tuple[list[StockRow], datetime | None, list[str]]:
        snapshot = (
            (
                await session.execute(
                    select(WBStockSnapshot)
                    .where(WBStockSnapshot.account_id == account_id)
                    .order_by(
                        WBStockSnapshot.snapshot_at.desc(), WBStockSnapshot.id.desc()
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if snapshot is None:
            return [], None, ["stock_snapshot_missing"]
        mappings = await self._warehouse_mappings(session)
        stmt = select(WBStockSnapshotRow).where(
            WBStockSnapshotRow.account_id == account_id,
            WBStockSnapshotRow.snapshot_id == snapshot.id,
        )
        rows: list[StockRow] = []
        unmapped = 0
        for item in (await session.execute(stmt)).scalars():
            if is_total_stock_row(item.warehouse_name):
                continue
            region = self._mapped_region(
                item.warehouse_id, item.warehouse_name, mappings
            )
            if region is None:
                unmapped += 1
                region = item.warehouse_name
            qty = int(Decimal(str(item.quantity or item.quantity_full or 0)))
            if qty <= 0:
                continue
            rows.append(
                StockRow(
                    nm_id=item.nm_id,
                    vendor_code=None,
                    barcode=item.barcode,
                    chrt_id=item.chrt_id,
                    size_name=None,
                    region=region,
                    warehouse_id=item.warehouse_id,
                    warehouse_name=item.warehouse_name,
                    quantity=qty,
                    subject=item.subject,
                    brand=item.brand,
                )
            )
        warnings = ["unmapped_warehouses"] if unmapped else []
        return rows, snapshot.snapshot_at, warnings

    async def _hand_rows_for_run(
        self, session: AsyncSession, *, run: StockControlRun
    ) -> list[HandStockRow]:
        draft_id = (run.input_summary_json or {}).get("hand_stock_draft_id")
        if draft_id is None:
            return []
        rows = await self.repo.hand_rows(
            session, account_id=run.account_id, draft_id=int(draft_id)
        )
        return [
            HandStockRow(
                nm_id=row.nm_id,
                vendor_code=row.vendor_code,
                barcode=row.barcode,
                size_name=row.size_name,
                available_qty=int(row.available_qty or 0),
                source_name=row.source_name,
            )
            for row in rows
        ]

    async def _warehouse_mappings(
        self, session: AsyncSession
    ) -> dict[tuple[str, str], str]:
        result: dict[tuple[str, str], str] = {}
        for row in (await session.execute(select(WarehouseRegionMapping))).scalars():
            result[
                (
                    str(row.warehouse_id or ""),
                    str(row.warehouse_name or "").strip().casefold(),
                )
            ] = normalize_region(row.canonical_region)
            result[("", str(row.warehouse_name or "").strip().casefold())] = (
                normalize_region(row.canonical_region)
            )
        return result

    def _mapped_region(
        self,
        warehouse_id: int | None,
        warehouse_name: str | None,
        mappings: dict[tuple[str, str], str],
    ) -> str | None:
        name = str(warehouse_name or "").strip().casefold()
        return mappings.get((str(warehouse_id or ""), name)) or mappings.get(("", name))

    async def _warehouse_mapping_coverage(
        self, session: AsyncSession, *, account_id: int
    ) -> tuple[float | None, int]:
        snapshot = (
            (
                await session.execute(
                    select(WBStockSnapshot)
                    .where(WBStockSnapshot.account_id == account_id)
                    .order_by(
                        WBStockSnapshot.snapshot_at.desc(), WBStockSnapshot.id.desc()
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if snapshot is None:
            return None, 0
        mappings = await self._warehouse_mappings(session)
        rows = list(
            (
                await session.execute(
                    select(
                        WBStockSnapshotRow.warehouse_id,
                        WBStockSnapshotRow.warehouse_name,
                    )
                    .where(
                        WBStockSnapshotRow.account_id == account_id,
                        WBStockSnapshotRow.snapshot_id == snapshot.id,
                    )
                    .group_by(
                        WBStockSnapshotRow.warehouse_id,
                        WBStockSnapshotRow.warehouse_name,
                    )
                )
            ).all()
        )
        real_rows = [(wid, name) for wid, name in rows if not is_total_stock_row(name)]
        if not real_rows:
            return None, 0
        mapped = sum(
            1 for wid, name in real_rows if self._mapped_region(wid, name, mappings)
        )
        unmapped = len(real_rows) - mapped
        return round((mapped / len(real_rows)) * 100, 2), unmapped

    def _region_model(
        self, account_id: int, item: dict[str, Any], *, created_at: datetime
    ) -> StockControlRegionRow:
        return StockControlRegionRow(
            run_id=0,
            account_id=account_id,
            nm_id=item.get("nm_id"),
            vendor_code=item.get("vendor_code"),
            barcode=item.get("barcode"),
            chrt_id=item.get("chrt_id"),
            size_name=item.get("size_name"),
            subject=item.get("subject"),
            brand=item.get("brand"),
            region=item.get("region") or "Неизвестный регион",
            warehouse_id=item.get("warehouse_id"),
            warehouse_name=item.get("warehouse_name"),
            orders_qty=Decimal(str(item.get("orders_qty") or 0)),
            local_orders_qty=Decimal(str(item.get("local_orders_qty") or 0)),
            region_share=Decimal(str(item.get("region_share") or 0)),
            current_stock_qty=Decimal(str(item.get("current_stock_qty") or 0)),
            target_stock_qty=Decimal(str(item.get("target_stock_qty") or 0)),
            delta_qty=Decimal(str(item.get("delta_qty") or 0)),
            status=item.get("status") or "balanced",
            localization_pct=Decimal(str(item["localization_pct"]))
            if item.get("localization_pct") is not None
            else None,
            impact_pct=Decimal(str(item["impact_pct"]))
            if item.get("impact_pct") is not None
            else None,
            distribution_source=item.get("distribution_source"),
            source_metadata_json=item.get("source_metadata_json") or {},
            created_at=created_at,
        )

    def _movement_model(
        self, account_id: int, item: dict[str, Any]
    ) -> StockControlMovement:
        return StockControlMovement(
            run_id=0,
            account_id=account_id,
            nm_id=item.get("nm_id"),
            vendor_code=item.get("vendor_code"),
            barcode=item.get("barcode"),
            size_name=item.get("size_name"),
            movement_type=item.get("movement_type") or "regional_redistribution",
            donor_region=item.get("donor_region"),
            donor_warehouse=item.get("donor_warehouse"),
            recipient_region=item.get("recipient_region"),
            recipient_warehouse=item.get("recipient_warehouse"),
            quantity=Decimal(str(item.get("quantity") or 0)),
            priority=item.get("priority") or "P3",
            reason_code=item.get("reason_code"),
            business_explanation=item.get("business_explanation"),
            confidence=item.get("confidence") or "medium",
            status=item.get("status") or "new",
        )

    async def _replace_export(
        self,
        session: AsyncSession,
        *,
        run: StockControlRun,
        region_rows: list[dict[str, Any]],
        movements: list[dict[str, Any]],
        unmatched: list[dict[str, Any]],
    ) -> None:
        await session.execute(
            delete(StockControlExportArtifact).where(
                StockControlExportArtifact.run_id == run.id
            )
        )
        content = build_export_xlsx(
            summary=run.result_summary_json or {},
            region_rows=region_rows,
            movements=movements,
            unmatched=unmatched,
        )
        session.add(
            StockControlExportArtifact(
                run_id=run.id,
                account_id=run.account_id,
                file_name=f"stock_control_run_{run.id}.xlsx",
                content=content,
                metadata_json={"mode": "local", "marketplace_change": False},
            )
        )

    def _hand_row_model(
        self, account_id: int, draft_id: int, row: HandStockRowIn
    ) -> StockControlHandStockRow:
        errors = []
        if not row.nm_id and not row.vendor_code:
            errors.append("nm_id_or_vendor_code_required")
        if row.available_qty <= 0:
            errors.append("available_qty_must_be_positive")
        return StockControlHandStockRow(
            draft_id=draft_id,
            account_id=account_id,
            nm_id=row.nm_id,
            vendor_code=row.vendor_code,
            barcode=row.barcode,
            size_name=row.size_name,
            available_qty=Decimal(str(row.available_qty or 0)),
            source_name=row.source_name,
            matching_status="invalid" if errors else "pending",
            validation_errors_json=errors,
        )

    async def _draft_read(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        draft: StockControlHandStockDraft,
    ) -> HandStockDraftRead:
        rows = await self.repo.hand_rows(
            session, account_id=account_id, draft_id=draft.id
        )
        return HandStockDraftRead.model_validate(draft).model_copy(
            update={"rows": [HandStockRowRead.model_validate(row) for row in rows]}
        )

    def _stockops_status(self, status: str) -> str:
        if status == "partial":
            return "completed"
        if status in {"queued", "running", "completed", "failed", "cancelled"}:
            return "failed" if status == "cancelled" else status
        return "failed"
