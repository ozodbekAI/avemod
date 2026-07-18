from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any

from sqlalchemy import delete, select

from app.core.parsing import parse_date, parse_datetime
from app.core.time import utcnow
from app.core.wb_sync import DomainSyncBase
from app.modules.ads.client import AdsClient
from app.models.ads import WBAdCampaign, WBAdCampaignItem
from app.repositories.ads import (
    AdCampaignItemRepository,
    AdCampaignRepository,
    AdClusterStatsRepository,
    AdStatsRepository,
)


class AdsSyncService(DomainSyncBase):
    domain = "ads"
    category = "promotion"
    FULLSTATS_BATCH_SIZE = 50
    FULLSTATS_INTERVAL_SECONDS = 20
    STAT_ALLOWED_STATUSES = {7, 9, 11}

    def __init__(self) -> None:
        super().__init__()
        self.client = AdsClient(self)
        self.campaigns = AdCampaignRepository()
        self.items = AdCampaignItemRepository()
        self.stats = AdStatsRepository()
        self.cluster_stats = AdClusterStatsRepository()

    @staticmethod
    def _campaign_ids_for_stats(campaign_rows: list[dict[str, Any]]) -> list[int]:
        return [
            int(item["advert_id"])
            for item in campaign_rows
            if item.get("advert_id") is not None
            and item.get("status") in AdsSyncService.STAT_ALLOWED_STATUSES
        ]

    @staticmethod
    def _iter_campaigns(payload: dict[str, Any]) -> list[dict[str, Any]]:
        campaigns: list[dict[str, Any]] = []
        for entry in payload.get("adverts") or payload.get("data") or []:
            if not isinstance(entry, dict):
                continue
            advert_list = entry.get("advert_list")
            if isinstance(advert_list, list):
                for advert in advert_list:
                    if not isinstance(advert, dict):
                        continue
                    campaigns.append(
                        {
                            "advert_id": advert.get("advertId"),
                            "campaign_type": entry.get("type") or advert.get("type"),
                            "status": entry.get("status") or advert.get("status"),
                            "bid_type": advert.get("bid_type"),
                            "name": advert.get("name"),
                            "change_time": parse_datetime(advert.get("changeTime")),
                            "payload": advert | {"group": entry},
                            "nm_settings": advert.get("nm_settings")
                            or advert.get("nmSettings")
                            or [],
                        }
                    )
                continue
            advert_id = entry.get("advertId") or entry.get("id")
            if advert_id is None:
                continue
            campaigns.append(
                {
                    "advert_id": advert_id,
                    "campaign_type": entry.get("type"),
                    "status": entry.get("status"),
                    "bid_type": entry.get("bid_type"),
                    "name": entry.get("name")
                    or (entry.get("settings") or {}).get("name"),
                    "change_time": parse_datetime(
                        entry.get("changeTime")
                        or (entry.get("timestamps") or {}).get("updated")
                    ),
                    "payload": entry,
                    "nm_settings": entry.get("nm_settings")
                    or entry.get("nmSettings")
                    or [],
                }
            )
        return [
            campaign for campaign in campaigns if campaign.get("advert_id") is not None
        ]

    @staticmethod
    def _number(value: Any) -> float:
        if value is None or value == "":
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _aggregate_nm_rows(cls, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_nm: dict[int | None, dict[str, Any]] = {}
        for row in rows:
            nm_id = row.get("nmId") or row.get("nm_id")
            nm_key = int(nm_id) if nm_id is not None else None
            aggregate = by_nm.setdefault(
                nm_key,
                {
                    "nmId": nm_key,
                    "name": row.get("name"),
                    "views": 0,
                    "clicks": 0,
                    "atbs": 0,
                    "orders": 0,
                    "shks": 0,
                    "canceled": 0,
                    "sum": 0.0,
                    "sum_price": 0.0,
                    "payload_rows": [],
                },
            )
            aggregate["name"] = aggregate.get("name") or row.get("name")
            for field in ("views", "clicks", "atbs", "orders", "shks", "canceled"):
                aggregate[field] += int(cls._number(row.get(field)))
            for field in ("sum", "sum_price"):
                aggregate[field] += cls._number(row.get(field))
            aggregate["payload_rows"].append(row)

        result: list[dict[str, Any]] = []
        for aggregate in by_nm.values():
            views = cls._number(aggregate.get("views"))
            clicks = cls._number(aggregate.get("clicks"))
            spend = cls._number(aggregate.get("sum"))
            aggregate["ctr"] = (clicks / views * 100) if views > 0 else None
            aggregate["cr"] = (
                (cls._number(aggregate.get("orders")) / clicks * 100)
                if clicks > 0
                else None
            )
            aggregate["cpc"] = (spend / clicks) if clicks > 0 else None
            aggregate["cpm"] = (spend / views * 1000) if views > 0 else None
            result.append(aggregate)
        return result

    @classmethod
    def _nm_rows_from_fullstats_period(
        cls,
        period: dict[str, Any],
        *,
        linked_nm_ids: list[int],
    ) -> list[dict[str, Any]]:
        direct_rows = [
            row for row in (period.get("nms") or []) if isinstance(row, dict)
        ]
        if direct_rows:
            return direct_rows

        app_nm_rows: list[dict[str, Any]] = []
        for app in period.get("apps") or []:
            if not isinstance(app, dict):
                continue
            for nm_row in app.get("nms") or []:
                if isinstance(nm_row, dict):
                    app_nm_rows.append(nm_row | {"app": app})
        if app_nm_rows:
            return cls._aggregate_nm_rows(app_nm_rows)

        fallback_nm_id = linked_nm_ids[0] if len(linked_nm_ids) == 1 else None
        return [{"nmId": fallback_nm_id, **period}]

    @staticmethod
    def _iter_cluster_stats(payload: Any, *, default_date: str) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if not isinstance(payload, dict):
            return []

        rows: list[dict[str, Any]] = []
        v1_items = payload.get("items")
        if isinstance(v1_items, list):
            for item in v1_items:
                if not isinstance(item, dict):
                    continue
                advert_id = item.get("advertId") or item.get("advert_id")
                nm_id = item.get("nmId") or item.get("nm_id")
                for daily in item.get("dailyStats") or []:
                    if not isinstance(daily, dict):
                        continue
                    stat = daily.get("stat")
                    if not isinstance(stat, dict):
                        continue
                    rows.append(
                        {
                            **stat,
                            "advert_id": advert_id,
                            "nm_id": nm_id,
                            "date": daily.get("date") or default_date,
                            "cluster": stat.get("normQuery") or stat.get("norm_query"),
                            "sum": stat.get("spend") or stat.get("sum"),
                            "avg_position": stat.get("avgPos") or stat.get("avg_pos"),
                        }
                    )
            if rows:
                return rows

        nested_groups = payload.get("stats")
        if isinstance(nested_groups, list):
            for group in nested_groups:
                if not isinstance(group, dict):
                    continue
                inner_rows = group.get("stats")
                if isinstance(inner_rows, list) and inner_rows:
                    for row in inner_rows:
                        if isinstance(row, dict):
                            rows.append(
                                {
                                    **row,
                                    "advert_id": row.get("advert_id")
                                    or row.get("advertId")
                                    or group.get("advert_id")
                                    or group.get("advertId"),
                                    "nm_id": row.get("nm_id")
                                    or row.get("nmId")
                                    or group.get("nm_id")
                                    or group.get("nmId"),
                                    "date": row.get("date") or default_date,
                                }
                            )
                elif any(
                    group.get(field) is not None
                    for field in (
                        "date",
                        "cluster",
                        "phrase",
                        "normquery",
                        "norm_query",
                        "views",
                        "clicks",
                    )
                ):
                    rows.append(group | {"date": group.get("date") or default_date})
            return rows

        for key in ("data", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                rows.extend(
                    row | {"date": row.get("date") or default_date}
                    for row in value
                    if isinstance(row, dict)
                )
        return rows

    async def run(
        self,
        session,
        *,
        account,
        force_full=False,
        backfill_from=None,
        backfill_to=None,
    ):
        campaigns_payload = await self.client.campaigns(session, account_id=account.id)
        campaign_rows = self._iter_campaigns(campaigns_payload)
        campaign_nm_ids: dict[int, list[int]] = {}
        for item in campaign_rows:
            unique_nm_ids = []
            for nm_setting in item.get("nm_settings", []):
                nm_id = nm_setting.get("nm_id") or nm_setting.get("nmId")
                if nm_id is not None and nm_id not in unique_nm_ids:
                    unique_nm_ids.append(int(nm_id))
            campaign_nm_ids[int(item["advert_id"])] = unique_nm_ids
        await self.campaigns.upsert_many(
            session,
            [
                {
                    "account_id": account.id,
                    "advert_id": item["advert_id"],
                    "campaign_type": item["campaign_type"],
                    "status": item["status"],
                    "bid_type": item["bid_type"],
                    "name": item["name"],
                    "change_time": item["change_time"],
                    "payload": item["payload"],
                }
                for item in campaign_rows
            ],
            conflict_fields=["account_id", "advert_id"],
        )

        db_campaigns = {
            item.advert_id: item
            for item in list(
                (
                    await session.execute(
                        select(WBAdCampaign).where(
                            WBAdCampaign.account_id == account.id
                        )
                    )
                ).scalars()
            )
        }
        await session.execute(
            delete(WBAdCampaignItem).where(WBAdCampaignItem.account_id == account.id)
        )
        for item in campaign_rows:
            campaign = db_campaigns.get(item["advert_id"])
            if campaign is None:
                continue
            for nm_setting in item.get("nm_settings", []):
                session.add(
                    WBAdCampaignItem(
                        campaign_fk_id=campaign.id,
                        account_id=account.id,
                        nm_id=nm_setting.get("nm_id") or nm_setting.get("nmId"),
                        name=(nm_setting.get("subject") or {}).get("name"),
                        payload=nm_setting,
                    )
                )

        begin_date = (
            backfill_from or (utcnow().date() - timedelta(days=6))
        ).isoformat()
        end_date = (backfill_to or utcnow().date()).isoformat()
        campaign_ids_for_stats = self._campaign_ids_for_stats(campaign_rows)
        for batch_index, start in enumerate(
            range(0, len(campaign_ids_for_stats), self.FULLSTATS_BATCH_SIZE)
        ):
            batch_ids = campaign_ids_for_stats[
                start : start + self.FULLSTATS_BATCH_SIZE
            ]
            if not batch_ids:
                continue
            if batch_index > 0:
                await asyncio.sleep(self.FULLSTATS_INTERVAL_SECONDS)
            stats_payload = await self.client.full_stats(
                session,
                account_id=account.id,
                ids=batch_ids,
                begin_date=begin_date,
                end_date=end_date,
            )
            stats_rows = (
                stats_payload
                if isinstance(stats_payload, list)
                else (stats_payload or {}).get("data", [])
            )
            for campaign_stat in stats_rows:
                advert_id = campaign_stat.get("advertId") or campaign_stat.get(
                    "advert_id"
                )
                linked_nm_ids = (
                    campaign_nm_ids.get(int(advert_id), [])
                    if advert_id is not None
                    else []
                )
                for period in campaign_stat.get("days", campaign_stat.get("dates", [])):
                    stat_date = period.get("date")
                    nm_rows = self._nm_rows_from_fullstats_period(
                        period, linked_nm_ids=linked_nm_ids
                    )
                    await self.stats.upsert_many(
                        session,
                        [
                            {
                                "account_id": account.id,
                                "advert_id": advert_id,
                                "stat_date": parse_date(stat_date),
                                "nm_id": item.get("nmId") or item.get("nm_id"),
                                "views": item.get("views"),
                                "clicks": item.get("clicks"),
                                "ctr": item.get("ctr"),
                                "cpc": item.get("cpc"),
                                "cpm": item.get("cpm"),
                                "atbs": item.get("atbs"),
                                "orders": item.get("orders"),
                                "shks": item.get("shks"),
                                "sum": item.get("sum"),
                                "sum_price": item.get("sum_price"),
                                "payload": item | {"period": period},
                            }
                            for item in nm_rows
                        ],
                        conflict_fields=["dedupe_key"],
                    )

        cluster_items = list(
            {
                (
                    item["advert_id"],
                    nm_setting.get("nm_id") or nm_setting.get("nmId"),
                )
                for item in campaign_rows
                if item.get("status") in self.STAT_ALLOWED_STATUSES
                for nm_setting in item.get("nm_settings", [])[:5]
                if (nm_setting.get("nm_id") or nm_setting.get("nmId")) is not None
            }
        )
        if cluster_items:
            cluster_payload = await self.client.cluster_stats(
                session,
                account_id=account.id,
                items=[
                    {"advert_id": advert_id, "nm_id": nm_id}
                    for advert_id, nm_id in cluster_items[:100]
                ],
                date_from=begin_date,
                date_to=end_date,
            )
            cluster_rows = self._iter_cluster_stats(
                cluster_payload, default_date=begin_date
            )
            cluster_rows_to_upsert = []
            for row in cluster_rows:
                if not isinstance(row, dict):
                    continue
                stat_date = parse_date(row.get("date"))
                if stat_date is None:
                    continue
                cluster_rows_to_upsert.append(
                    {
                        "account_id": account.id,
                        "advert_id": row.get("advert_id") or row.get("advertId"),
                        "stat_date": stat_date,
                        "cluster": row.get("normQuery")
                        or row.get("norm_query")
                        or row.get("normquery")
                        or row.get("cluster")
                        or row.get("phrase"),
                        "nm_id": row.get("nm_id") or row.get("nmId"),
                        "views": row.get("views"),
                        "clicks": row.get("clicks"),
                        "ctr": row.get("ctr"),
                        "cpc": row.get("cpc"),
                        "cpm": row.get("cpm"),
                        "orders": row.get("orders"),
                        "atbs": row.get("atbs"),
                        "sum": row.get("spend") or row.get("sum"),
                        "avg_position": row.get("avgPos")
                        or row.get("avg_pos")
                        or row.get("avg_position")
                        or row.get("avgPosition"),
                        "payload": row,
                    }
                )
            await self.cluster_stats.upsert_many(
                session,
                cluster_rows_to_upsert,
                conflict_fields=["dedupe_key"],
            )

        await self._set_cursor(
            session,
            account_id=account.id,
            cursor_value={"syncedAt": utcnow().isoformat()},
        )
        return {"status": "completed", "campaigns": len(campaign_rows)}
