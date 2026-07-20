from __future__ import annotations

import zlib
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.pagination import Page
from app.core.time import utcnow
from app.models.accounts import WBAccount
from app.models.sync import WBSyncCursor, WBSyncRun
from app.repositories.sync import WBSyncCursorRepository, WBSyncRunRepository


class BaseDomainSyncService:
    async def run(
        self,
        session: AsyncSession,
        *,
        account: WBAccount,
        force_full: bool = False,
        backfill_from: date | None = None,
        backfill_to: date | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError


class SyncOrchestrator:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.cursors = WBSyncCursorRepository()
        self.runs = WBSyncRunRepository()
        self.settings = get_settings()

    @staticmethod
    def _progress_payload(
        *,
        status: str,
        stage: str,
        progress_percent: int | float,
        stage_label: str | None = None,
        message: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        percent = max(0, min(100, int(round(float(progress_percent)))))
        payload: dict[str, Any] = {
            "status": status,
            "stage": stage,
            "progress_percent": percent,
            "progress_updated_at": utcnow().isoformat(),
        }
        if stage_label:
            payload["stage_label"] = stage_label
        if message:
            payload["message"] = message
        for key, value in extra.items():
            if value is not None:
                payload[key] = value
        return payload

    @staticmethod
    def _merge_progress_details(run: WBSyncRun, payload: dict[str, Any]) -> None:
        run.details = {
            **(run.details or {}),
            **{key: value for key, value in payload.items() if value is not None},
        }

    async def _publish_run_progress(
        self, *, run_id: int, payload: dict[str, Any]
    ) -> None:
        from app.core.db import SessionLocal

        async with SessionLocal() as progress_session:
            progress_run = await progress_session.get(WBSyncRun, run_id)
            if progress_run is None or progress_run.status not in {"queued", "running"}:
                return
            status_value = str(payload.get("status") or "")
            if status_value in {"queued", "running"}:
                progress_run.status = status_value
                if status_value == "running":
                    progress_run.finished_at = None
            self._merge_progress_details(progress_run, payload)
            await progress_session.commit()

    async def _reset_stale_running_state(
        self, *, account_id: int, domain: str
    ) -> dict[str, int]:
        stale_before = utcnow() - timedelta(
            hours=self.settings.sync_running_cursor_stale_hours
        )
        stale_cursors = list(
            (
                await self.session.execute(
                    select(WBSyncCursor).where(
                        WBSyncCursor.account_id == account_id,
                        WBSyncCursor.domain == domain,
                        WBSyncCursor.status == "running",
                    )
                )
            ).scalars()
        )
        reset_cursors = 0
        for cursor in stale_cursors:
            reference_time = (
                cursor.updated_at or cursor.last_synced_at or cursor.created_at
            )
            if reference_time is None or reference_time > stale_before:
                continue
            cursor.status = "idle"
            cursor.cursor_value = {
                **(cursor.cursor_value or {}),
                "staleResetAt": utcnow().isoformat(),
                "stalePreviousStatus": "running",
                "lastErrorText": "Stale running cursor was reset before the next attempt",
            }
            reset_cursors += 1

        stale_runs_stmt = (
            update(WBSyncRun)
            .where(
                WBSyncRun.account_id == account_id,
                WBSyncRun.domain == domain,
                WBSyncRun.status == "running",
                WBSyncRun.started_at < stale_before,
            )
            .values(
                status="failed",
                finished_at=utcnow(),
                error_text="Stale sync run was reset before the next attempt",
            )
        )
        stale_runs_result = await self.session.execute(stale_runs_stmt)
        return {
            "reset_cursors": reset_cursors,
            "reset_runs": int(stale_runs_result.rowcount or 0),
        }

    async def trigger(
        self,
        *,
        account_id: int,
        domain: str,
        trigger: str = "manual",
        force_full: bool = False,
        backfill_from: date | None = None,
        backfill_to: date | None = None,
        raise_on_error: bool = False,
    ) -> WBSyncRun:
        account = await self.session.get(WBAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        service = self._get_service(domain)
        stale_reset = await self._reset_stale_running_state(
            account_id=account_id, domain=domain
        )
        run = WBSyncRun(
            account_id=account_id,
            domain=domain,
            trigger=trigger,
            status="running",
            is_backfill=backfill_from is not None or backfill_to is not None,
            started_at=utcnow(),
            details=self._progress_payload(
                status="running",
                stage="running",
                progress_percent=5,
                stage_label="Sync started",
            ),
        )
        self.session.add(run)
        await self.session.flush()
        lock_key = zlib.crc32(f"{account_id}:{domain}".encode("utf-8"))
        lock_acquired = (
            await self.session.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
            )
        ).scalar_one()
        if not lock_acquired:
            run.status = "skipped"
            run.error_text = "Another sync instance is already running"
            run.details = {
                "status": "skipped",
                "reason": "already_running",
                **stale_reset,
            }
            run.finished_at = utcnow()
            await self.session.flush()
            return run
        original_exception: Exception | None = None
        try:
            async with self.session.begin_nested():
                details = await service.run(
                    self.session,
                    account=account,
                    force_full=force_full,
                    backfill_from=backfill_from,
                    backfill_to=backfill_to,
                )
                runtime_details = getattr(service, "runtime_details", None)
                if callable(runtime_details):
                    details = details | {
                        key: value
                        for key, value in runtime_details().items()
                        if key not in details
                    }
                if stale_reset["reset_cursors"] or stale_reset["reset_runs"]:
                    details = details | stale_reset
            run.status = details.get("status", "completed")
            run.details = {
                **details,
                **self._progress_payload(
                    status=run.status,
                    stage=run.status,
                    progress_percent=100,
                    stage_label="Sync finished",
                ),
            }
        except Exception as exc:
            run.status = "failed"
            run.error_text = str(exc)
            run.details = self._progress_payload(
                status="failed",
                stage="failed",
                progress_percent=100,
                stage_label="Sync failed",
                error=str(exc),
            )
            original_exception = exc
        finally:
            run.finished_at = utcnow()
            try:
                await self.session.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key}
                )
                await self.session.flush()
            except Exception:
                # If the transaction is already aborted, closing/rolling back the session
                # will release the advisory lock. Keep the original exception visible.
                pass
        if original_exception is not None and raise_on_error:
            raise original_exception
        return run

    async def enqueue(
        self,
        *,
        account_id: int,
        domain: str,
        trigger: str = "manual",
        force_full: bool = False,
        backfill_from: date | None = None,
        backfill_to: date | None = None,
    ) -> WBSyncRun:
        account = await self.session.get(WBAccount, account_id)
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
        self._get_service(domain)
        run = WBSyncRun(
            account_id=account_id,
            domain=domain,
            trigger=trigger,
            status="queued",
            is_backfill=backfill_from is not None or backfill_to is not None,
            started_at=utcnow(),
            details={
                **self._progress_payload(
                    status="queued",
                    stage="queued",
                    progress_percent=0,
                    stage_label="Waiting in queue",
                ),
                "force_full": force_full,
                "backfill_from": backfill_from.isoformat() if backfill_from else None,
                "backfill_to": backfill_to.isoformat() if backfill_to else None,
            },
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def process_queued_run(
        self, *, run_id: int, raise_on_error: bool = False
    ) -> WBSyncRun:
        run = await self.session.get(WBSyncRun, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Sync run not found")
        if run.status not in {"queued", "running"}:
            return run
        account = await self.session.get(WBAccount, run.account_id)
        if account is None:
            run.status = "failed"
            run.error_text = "Account not found"
            run.finished_at = utcnow()
            await self.session.flush()
            return run

        queued_details = run.details or {}
        force_full = bool(queued_details.get("force_full"))
        backfill_from = (
            date.fromisoformat(queued_details["backfill_from"])
            if queued_details.get("backfill_from")
            else None
        )
        backfill_to = (
            date.fromisoformat(queued_details["backfill_to"])
            if queued_details.get("backfill_to")
            else None
        )
        service = self._get_service(run.domain)
        stale_reset = await self._reset_stale_running_state(
            account_id=run.account_id, domain=run.domain
        )

        lock_key = zlib.crc32(f"{run.account_id}:{run.domain}".encode("utf-8"))
        lock_acquired = (
            await self.session.execute(
                text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
            )
        ).scalar_one()
        if not lock_acquired:
            if run.status == "running":
                return run
            run.status = "skipped"
            run.error_text = "Another sync instance is already running"
            run.details = {
                **self._progress_payload(
                    status="skipped",
                    stage="skipped",
                    progress_percent=100,
                    stage_label="Another sync is already running",
                    reason="already_running",
                ),
                **stale_reset,
            }
            run.finished_at = utcnow()
            await self.session.flush()
            return run

        await self._publish_run_progress(
            run_id=int(run.id),
            payload=self._progress_payload(
                status="running",
                stage="running",
                progress_percent=5,
                stage_label="Sync started",
            ),
        )
        progress_setter = getattr(service, "set_progress_callback", None)
        if callable(progress_setter):

            async def progress_callback(payload: dict[str, Any]) -> None:
                await self._publish_run_progress(
                    run_id=int(run.id),
                    payload={
                        **payload,
                        "status": payload.get("status") or "running",
                        "progress_updated_at": payload.get("progress_updated_at")
                        or utcnow().isoformat(),
                    },
                )

            progress_setter(progress_callback)

        original_exception: Exception | None = None
        try:
            async with self.session.begin_nested():
                details = await service.run(
                    self.session,
                    account=account,
                    force_full=force_full,
                    backfill_from=backfill_from,
                    backfill_to=backfill_to,
                )
                runtime_details = getattr(service, "runtime_details", None)
                if callable(runtime_details):
                    details = details | {
                        key: value
                        for key, value in runtime_details().items()
                        if key not in details
                    }
                if stale_reset["reset_cursors"] or stale_reset["reset_runs"]:
                    details = details | stale_reset
            run.status = details.get("status", "completed")
            run.details = {
                **(run.details or {}),
                **details,
                **self._progress_payload(
                    status=run.status,
                    stage=run.status,
                    progress_percent=100,
                    stage_label="Sync finished",
                ),
            }
            run.error_text = None
        except Exception as exc:
            run.status = "failed"
            run.error_text = str(exc)
            run.details = self._progress_payload(
                status="failed",
                stage="failed",
                progress_percent=100,
                stage_label="Sync failed",
                error=str(exc),
            )
            original_exception = exc
        finally:
            run.finished_at = utcnow()
            try:
                await self.session.execute(
                    text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key}
                )
                await self.session.flush()
            except Exception:
                pass
        if original_exception is not None and raise_on_error:
            raise original_exception
        return run

    async def set_cursor(
        self,
        *,
        account_id: int,
        domain: str,
        cursor_value: dict[str, Any],
        cursor_key: str = "default",
        status: str = "idle",
    ) -> WBSyncCursor:
        cursor = await self.cursors.get_for_domain(
            self.session, account_id=account_id, domain=domain, cursor_key=cursor_key
        )
        if cursor is None:
            cursor = WBSyncCursor(
                account_id=account_id,
                domain=domain,
                cursor_key=cursor_key,
                cursor_value=cursor_value,
                last_synced_at=utcnow(),
                status=status,
            )
            self.session.add(cursor)
        else:
            cursor.cursor_value = cursor_value
            cursor.last_synced_at = utcnow()
            cursor.status = status
        await self.session.flush()
        return cursor

    async def list_runs(
        self,
        *,
        account_id: int | None = None,
        domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        stmt = select(WBSyncRun).order_by(
            WBSyncRun.started_at.desc(), WBSyncRun.id.desc()
        )
        count_stmt = select(func.count()).select_from(WBSyncRun)
        if account_id is not None:
            stmt = stmt.where(WBSyncRun.account_id == account_id)
            count_stmt = count_stmt.where(WBSyncRun.account_id == account_id)
        if domain is not None:
            stmt = stmt.where(WBSyncRun.domain == domain)
            count_stmt = count_stmt.where(WBSyncRun.domain == domain)
        total = int((await self.session.execute(count_stmt)).scalar_one())
        items = list(
            (await self.session.execute(stmt.limit(limit).offset(offset))).scalars()
        )
        return Page(total=total, limit=limit, offset=offset, items=items)

    async def list_cursors(
        self,
        *,
        account_id: int | None = None,
        domain: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ):
        stmt = select(WBSyncCursor).order_by(
            WBSyncCursor.domain, WBSyncCursor.account_id, WBSyncCursor.cursor_key
        )
        count_stmt = select(func.count()).select_from(WBSyncCursor)
        if account_id is not None:
            stmt = stmt.where(WBSyncCursor.account_id == account_id)
            count_stmt = count_stmt.where(WBSyncCursor.account_id == account_id)
        if domain is not None:
            stmt = stmt.where(WBSyncCursor.domain == domain)
            count_stmt = count_stmt.where(WBSyncCursor.domain == domain)
        total = int((await self.session.execute(count_stmt)).scalar_one())
        items = list(
            (await self.session.execute(stmt.limit(limit).offset(offset))).scalars()
        )
        return Page(total=total, limit=limit, offset=offset, items=items)

    async def reset_cursor(self, *, cursor_id: int) -> WBSyncCursor:
        cursor = await self.session.get(WBSyncCursor, cursor_id)
        if cursor is None:
            raise HTTPException(status_code=404, detail="Cursor not found")
        cursor.cursor_value = {}
        cursor.status = "idle"
        cursor.last_synced_at = utcnow()
        await self.session.flush()
        return cursor

    async def run_cursor_now(self, *, cursor_id: int) -> WBSyncRun:
        cursor = await self.session.get(WBSyncCursor, cursor_id)
        if cursor is None:
            raise HTTPException(status_code=404, detail="Cursor not found")
        return await self.trigger(
            account_id=cursor.account_id,
            domain=cursor.domain,
            trigger="cursor_run_now",
            force_full=True,
        )

    def _get_service(self, domain: str) -> BaseDomainSyncService:
        if domain == "product_cards":
            from app.modules.product_cards.sync import ProductCardsSyncService

            return ProductCardsSyncService()
        if domain == "prices":
            from app.modules.prices.sync import PricesSyncService

            return PricesSyncService()
        if domain == "promotions":
            from app.modules.promotions.sync import PromotionsSyncService

            return PromotionsSyncService()
        if domain == "orders":
            from app.modules.orders.sync import OrdersSyncService

            return OrdersSyncService()
        if domain == "sales":
            from app.modules.sales.sync import SalesSyncService

            return SalesSyncService()
        if domain == "stocks":
            from app.modules.stocks.sync import StocksSyncService

            return StocksSyncService()
        if domain == "finance":
            from app.modules.finance.sync import FinanceSyncService

            return FinanceSyncService()
        if domain == "supplies":
            from app.modules.supplies.sync import SuppliesSyncService

            return SuppliesSyncService()
        if domain == "ads":
            from app.modules.ads.sync import AdsSyncService

            return AdsSyncService()
        if domain == "analytics":
            from app.modules.analytics.sync import AnalyticsSyncService

            return AnalyticsSyncService()
        if domain == "tariffs":
            from app.modules.tariffs.sync import TariffsSyncService

            return TariffsSyncService()
        if domain == "logistics":
            from app.modules.logistics.sync import LogisticsSyncService

            return LogisticsSyncService()
        if domain == "documents":
            from app.modules.documents.sync import DocumentsSyncService

            return DocumentsSyncService()
        raise HTTPException(status_code=400, detail=f"Unsupported domain: {domain}")
