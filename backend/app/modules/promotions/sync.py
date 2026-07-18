from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http import WBAPIError
from app.core.parsing import parse_datetime
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.models.promotions import WBPromotionNomenclature
from app.modules.promotions.client import PromotionsClient
from app.repositories.promotions import (
    PromotionCalendarRepository,
    PromotionNomenclatureRepository,
)


class PromotionsSyncService(DomainSyncBase):
    domain = "promotions"
    category = "promotion"

    DEFAULT_LOOKBACK_DAYS = 30
    DEFAULT_LOOKAHEAD_DAYS = 90

    def __init__(self) -> None:
        super().__init__()
        self.client = PromotionsClient(self)
        self.promotions_repo = PromotionCalendarRepository()
        self.nomenclature_repo = PromotionNomenclatureRepository()

    @staticmethod
    def _period(
        backfill_from: date | None, backfill_to: date | None
    ) -> tuple[datetime, datetime]:
        today = utcnow().date()
        if backfill_from is None and backfill_to is None:
            return (
                datetime.combine(
                    today - timedelta(days=PromotionsSyncService.DEFAULT_LOOKBACK_DAYS),
                    time.min,
                    tzinfo=UTC,
                ),
                datetime.combine(
                    today
                    + timedelta(days=PromotionsSyncService.DEFAULT_LOOKAHEAD_DAYS),
                    time.max,
                    tzinfo=UTC,
                ),
            )
        start = backfill_from or today - timedelta(
            days=PromotionsSyncService.DEFAULT_LOOKBACK_DAYS
        )
        end = backfill_to or today + timedelta(
            days=PromotionsSyncService.DEFAULT_LOOKAHEAD_DAYS
        )
        return (
            datetime.combine(start, time.min, tzinfo=UTC),
            datetime.combine(end, time.max, tzinfo=UTC),
        )

    @staticmethod
    def _iso_z(value: datetime) -> str:
        return (
            value.astimezone(UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _int_or_none(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _promotions_from_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("promotions"), list):
            return [item for item in data["promotions"] if isinstance(item, dict)]
        if isinstance(payload.get("promotions"), list):
            return [item for item in payload["promotions"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _nomenclatures_from_payload(payload: Any) -> list[dict[str, Any]]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if isinstance(data, dict) and isinstance(data.get("nomenclatures"), list):
            return [item for item in data["nomenclatures"] if isinstance(item, dict)]
        if isinstance(payload.get("nomenclatures"), list):
            return [item for item in payload["nomenclatures"] if isinstance(item, dict)]
        return []

    @classmethod
    def _promotion_row(
        cls,
        *,
        account_id: int,
        item: dict[str, Any],
        snapshot_at: datetime,
    ) -> dict[str, Any] | None:
        promotion_id = cls._int_or_none(
            item.get("id") or item.get("promotionID") or item.get("promotionId")
        )
        if promotion_id is None:
            return None
        return {
            "account_id": account_id,
            "promotion_id": promotion_id,
            "name": item.get("name"),
            "promo_type": item.get("type"),
            "start_at": parse_datetime(
                item.get("startDateTime") or item.get("start_at")
            ),
            "end_at": parse_datetime(item.get("endDateTime") or item.get("end_at")),
            "description": item.get("description"),
            "advantages": item.get("advantages")
            if isinstance(item.get("advantages"), list)
            else None,
            "in_promo_action_leftovers": cls._int_or_none(
                item.get("inPromoActionLeftovers")
            ),
            "in_promo_action_total": cls._int_or_none(item.get("inPromoActionTotal")),
            "not_in_promo_action_leftovers": cls._int_or_none(
                item.get("notInPromoActionLeftovers")
            ),
            "not_in_promo_action_total": cls._int_or_none(
                item.get("notInPromoActionTotal")
            ),
            "participation_percentage": cls._int_or_none(
                item.get("participationPercentage")
            ),
            "exception_products_count": cls._int_or_none(
                item.get("exceptionProductsCount")
            ),
            "snapshot_at": snapshot_at,
            "payload": item,
        }

    @classmethod
    def _nomenclature_row(
        cls,
        *,
        account_id: int,
        promotion_id: int,
        item: dict[str, Any],
        in_action: bool,
        snapshot_at: datetime,
    ) -> dict[str, Any] | None:
        nm_id = cls._int_or_none(item.get("id") or item.get("nmID") or item.get("nmId"))
        if nm_id is None:
            return None
        return {
            "account_id": account_id,
            "promotion_id": promotion_id,
            "nm_id": nm_id,
            "in_action": bool(item.get("inAction", in_action)),
            "price": item.get("price"),
            "currency_code": item.get("currencyCode") or item.get("currency_code"),
            "plan_price": item.get("planPrice") or item.get("plan_price"),
            "discount": cls._int_or_none(item.get("discount")),
            "plan_discount": cls._int_or_none(
                item.get("planDiscount") or item.get("plan_discount")
            ),
            "snapshot_at": snapshot_at,
            "payload": item,
        }

    async def _fetch_nomenclature_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        promotion_id: int,
        in_action: bool,
        snapshot_at: datetime,
    ) -> list[dict[str, Any]]:
        offset = 0
        limit = 1000
        rows: list[dict[str, Any]] = []
        while True:
            payload = await self.client.nomenclatures(
                session,
                account_id=account_id,
                promotion_id=promotion_id,
                in_action=in_action,
                limit=limit,
                offset=offset,
            )
            items = self._nomenclatures_from_payload(payload)
            if not items:
                break
            for item in items:
                row = self._nomenclature_row(
                    account_id=account_id,
                    promotion_id=promotion_id,
                    item=item,
                    in_action=in_action,
                    snapshot_at=snapshot_at,
                )
                if row is not None:
                    rows.append(row)
            if len(items) < limit:
                break
            offset += limit
        return rows

    async def run(
        self,
        session: AsyncSession,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        period_start, period_end = self._period(backfill_from, backfill_to)
        start_value = self._iso_z(period_start)
        end_value = self._iso_z(period_end)
        snapshot_at = utcnow()

        promotions: list[dict[str, Any]] = []
        offset = 0
        limit = 1000
        while True:
            payload = await self.client.promotions(
                session,
                account_id=account.id,
                start_date_time=start_value,
                end_date_time=end_value,
                all_promo=True,
                limit=limit,
                offset=offset,
            )
            items = self._promotions_from_payload(payload)
            if not items:
                break
            promotions.extend(items)
            if len(items) < limit:
                break
            offset += limit

        ids = [
            promotion_id
            for item in promotions
            if (
                promotion_id := self._int_or_none(
                    item.get("id") or item.get("promotionID") or item.get("promotionId")
                )
            )
            is not None
        ]

        detail_by_id: dict[int, dict[str, Any]] = {}
        for start in range(0, len(ids), 100):
            batch_ids = ids[start : start + 100]
            if not batch_ids:
                continue
            detail_payload = await self.client.details(
                session, account_id=account.id, promotion_ids=batch_ids
            )
            for item in self._promotions_from_payload(detail_payload):
                promotion_id = self._int_or_none(
                    item.get("id") or item.get("promotionID") or item.get("promotionId")
                )
                if promotion_id is not None:
                    detail_by_id[promotion_id] = item

        promotion_rows = []
        regular_ids: list[int] = []
        for item in promotions:
            promotion_id = self._int_or_none(
                item.get("id") or item.get("promotionID") or item.get("promotionId")
            )
            if promotion_id is None:
                continue
            merged = item | detail_by_id.get(promotion_id, {})
            row = self._promotion_row(
                account_id=account.id, item=merged, snapshot_at=snapshot_at
            )
            if row is not None:
                promotion_rows.append(row)
            if str(merged.get("type") or "").strip().lower() != "auto":
                regular_ids.append(promotion_id)

        await self.promotions_repo.upsert_many(
            session,
            promotion_rows,
            conflict_fields=["account_id", "promotion_id"],
        )

        nomenclature_rows: list[dict[str, Any]] = []
        nomenclature_errors = 0
        if regular_ids:
            await session.execute(
                delete(WBPromotionNomenclature).where(
                    WBPromotionNomenclature.account_id == account.id,
                    WBPromotionNomenclature.promotion_id.in_(regular_ids),
                )
            )
        for promotion_id in regular_ids:
            for in_action in (True, False):
                try:
                    nomenclature_rows.extend(
                        await self._fetch_nomenclature_rows(
                            session,
                            account_id=account.id,
                            promotion_id=promotion_id,
                            in_action=in_action,
                            snapshot_at=snapshot_at,
                        )
                    )
                except WBAPIError as exc:
                    nomenclature_errors += 1
                    await self._open_issue(
                        session,
                        account_id=account.id,
                        code="promotions_nomenclatures_unavailable",
                        message=str(exc),
                        severity="info",
                        entity_key=str(promotion_id),
                    )

        await self.nomenclature_repo.upsert_many(
            session,
            nomenclature_rows,
            conflict_fields=["account_id", "promotion_id", "nm_id", "in_action"],
        )
        if nomenclature_errors == 0:
            await self.dq_service.resolve_issues(
                session,
                domain=self.domain,
                codes=["promotions_nomenclatures_unavailable"],
                account_id=account.id,
            )
        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={
                "startDateTime": start_value,
                "endDateTime": end_value,
                "promotionsLoaded": len(promotion_rows),
                "regularPromotions": len(regular_ids),
                "nomenclatureRowsLoaded": len(nomenclature_rows),
                "nomenclatureErrors": nomenclature_errors,
                "syncedAt": snapshot_at.isoformat(),
            },
        )
        return {
            "status": "completed",
            "promotionsLoaded": len(promotion_rows),
            "regularPromotions": len(regular_ids),
            "nomenclatureRowsLoaded": len(nomenclature_rows),
            "nomenclatureErrors": nomenclature_errors,
        }
