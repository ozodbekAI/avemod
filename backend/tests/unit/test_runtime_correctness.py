from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from decimal import Decimal

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session

from app.core.pagination import Page
from app.core.dedupe import compute_dedupe_key_from_mapping
from app.core.current_state import orders_current_subquery, sales_current_subquery
from app.core.http import WBHTTPClient, WBResponse
from app.jobs.registry import register_jobs
from app.models.ads import WBAdCampaign
from app.models.accounts import WBAccount
from app.models.finance import WBRealizationReportRow
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily
from app.models.orders import WBOrder
from app.models.product_cards import CoreSKU
from app.models.sales import WBSale
from app.modules.ads.client import AdsClient
from app.modules.ads.sync import AdsSyncService
from app.modules.analytics.sync import AnalyticsSyncService
from app.modules.finance.sync import FinanceSyncService
from app.modules.logistics.sync import LogisticsSyncService
from app.modules.orders.sync import OrdersSyncService
from app.modules.product_cards.sync import ProductCardsSyncService
from app.modules.sales.sync import SalesSyncService
from app.services.data_quality import DataQualityService
from app.services.raw import RawResponseService
from app.services.marts import MartService


class _FakeExecuteResult:
    def __init__(self, scalar_values):
        self._scalar_values = scalar_values

    def scalars(self):
        return self._scalar_values


class _AsyncSessionAdapter:
    def __init__(self, sync_session: Session):
        self._session = sync_session

    async def execute(self, statement):
        return self._session.execute(statement)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()

    async def commit(self) -> None:
        self._session.commit()


def _order_dedupe_key(
    *,
    account_id: int,
    srid: str,
    last_change_date: datetime,
    nm_id: int | None,
    barcode: str | None,
    order_id: int | None = None,
) -> str:
    return compute_dedupe_key_from_mapping(
        WBOrder.__dedupe_fields__,
        {
            "account_id": account_id,
            "srid": srid,
            "last_change_date": last_change_date,
            "nm_id": nm_id,
            "barcode": barcode,
            "order_id": order_id,
        },
    )


def _sale_dedupe_key(
    *,
    account_id: int,
    srid: str,
    last_change_date: datetime,
    nm_id: int | None,
    barcode: str | None,
    sale_id: str | None = None,
) -> str:
    return compute_dedupe_key_from_mapping(
        WBSale.__dedupe_fields__,
        {
            "account_id": account_id,
            "srid": srid,
            "last_change_date": last_change_date,
            "nm_id": nm_id,
            "barcode": barcode,
            "sale_id": sale_id,
        },
    )


def _core_sku_dedupe_key(
    *,
    account_id: int,
    nm_id: int | None,
    vendor_code: str | None,
    tech_size: str | None,
    chrt_id: int | None,
    size_id: int | None,
    barcode: str | None,
) -> str:
    return compute_dedupe_key_from_mapping(
        CoreSKU.__dedupe_fields__,
        {
            "account_id": account_id,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
            "tech_size": tech_size,
            "chrt_id": chrt_id,
            "size_id": size_id,
            "barcode": barcode,
        },
    )


def test_register_jobs_does_not_raise_and_registers_jobs() -> None:
    scheduler = AsyncIOScheduler()

    register_jobs(scheduler)

    job_ids = {job.id for job in scheduler.get_jobs()}
    assert len(job_ids) == 29
    assert "process-card-quality-runs" in job_ids
    assert "process-queued-stock-control-runs" in job_ids
    assert "dynamic-problem-nightly" in job_ids
    assert "sync-promotions" in job_ids
    assert "sync-local-reputation" in job_ids
    assert "process-queued-claim-detection-runs" in job_ids
    assert "process-queued-grouping-runs" in job_ids
    assert "process-queued-photo-jobs" in job_ids
    assert "collect-experiment-metric-snapshots" in job_ids
    assert "process-due-experiment-evaluations" in job_ids

    def cron_field(job_id: str, field_name: str) -> str:
        job = scheduler.get_job(job_id)
        assert job is not None
        return next(
            str(field) for field in job.trigger.fields if field.name == field_name
        )

    daily_jobs = {
        "sync-orders",
        "sync-sales",
        "sync-stocks",
        "sync-product-cards",
        "sync-prices",
        "sync-finance",
        "sync-supplies",
        "sync-ads",
        "sync-promotions",
        "sync-analytics",
        "sync-tariffs",
        "sync-logistics",
        "sync-documents",
        "sync-local-reputation",
        "reputation-auto-draft-local",
        "refresh-marts",
        "dynamic-problem-nightly",
        "run-data-quality",
        "refresh-money-snapshots",
    }
    for job_id in daily_jobs:
        hour = cron_field(job_id, "hour")
        minute = cron_field(job_id, "minute")
        assert hour != "*"
        assert "*/" not in hour
        assert "," not in hour
        assert "*/" not in minute
        assert "," not in minute


def test_dedupe_datetime_normalizes_to_canonical_utc_isoformat() -> None:
    dedupe = compute_dedupe_key_from_mapping(
        ("changed_at",),
        {"changed_at": datetime.fromisoformat("2026-05-15T15:00:00+03:00")},
    )
    expected = compute_dedupe_key_from_mapping(
        ("changed_at",),
        {"changed_at": datetime.fromisoformat("2026-05-15T12:00:00+00:00")},
    )

    assert dedupe == expected


def test_logistics_paid_storage_chunks_cover_default_money_window() -> None:
    chunks = LogisticsSyncService._date_chunks(
        date_from=date(2026, 6, 19),
        date_to=date(2026, 7, 19),
        max_days=LogisticsSyncService.PAID_STORAGE_CHUNK_DAYS,
    )

    assert chunks == [
        (date(2026, 6, 19), date(2026, 6, 26)),
        (date(2026, 6, 27), date(2026, 7, 4)),
        (date(2026, 7, 5), date(2026, 7, 12)),
        (date(2026, 7, 13), date(2026, 7, 19)),
    ]


def test_orders_current_subquery_keeps_distinct_rows_for_same_srid_and_different_nm_id() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBOrder.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(WBOrder),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "date": datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 15, 10, 5, tzinfo=timezone.utc
                    ),
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SRID-1",
                        last_change_date=datetime(
                            2026, 5, 15, 10, 5, tzinfo=timezone.utc
                        ),
                        nm_id=1001,
                        barcode="111",
                    ),
                    "srid": "SRID-1",
                    "nm_id": 1001,
                    "barcode": "111",
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "date": datetime(2026, 5, 15, 10, 1, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 15, 10, 6, tzinfo=timezone.utc
                    ),
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SRID-1",
                        last_change_date=datetime(
                            2026, 5, 15, 10, 6, tzinfo=timezone.utc
                        ),
                        nm_id=1002,
                        barcode="222",
                    ),
                    "srid": "SRID-1",
                    "nm_id": 1002,
                    "barcode": "222",
                },
                {
                    "id": 3,
                    "account_id": 1,
                    "date": datetime(2026, 5, 15, 10, 2, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 15, 10, 7, tzinfo=timezone.utc
                    ),
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SRID-1",
                        last_change_date=datetime(
                            2026, 5, 15, 10, 7, tzinfo=timezone.utc
                        ),
                        nm_id=1001,
                        barcode="111",
                    ),
                    "srid": "SRID-1",
                    "nm_id": 1001,
                    "barcode": "111",
                },
            ],
        )
        rows = (
            connection.execute(
                select(orders_current_subquery()).order_by("nm_id", "barcode")
            )
            .mappings()
            .all()
        )

    assert [
        (
            row["nm_id"],
            row["barcode"],
            row["last_change_date"].hour,
            row["last_change_date"].minute,
        )
        for row in rows
    ] == [
        (1001, "111", 10, 7),
        (1002, "222", 10, 6),
    ]


def test_sales_current_subquery_keeps_distinct_rows_for_same_srid_and_barcode() -> None:
    engine = create_engine("sqlite:///:memory:")
    WBSale.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(
            insert(WBSale),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "date": datetime(2026, 5, 15, 11, 0, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 15, 11, 5, tzinfo=timezone.utc
                    ),
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SRID-2",
                        last_change_date=datetime(
                            2026, 5, 15, 11, 5, tzinfo=timezone.utc
                        ),
                        nm_id=2001,
                        barcode="AAA",
                    ),
                    "srid": "SRID-2",
                    "nm_id": 2001,
                    "barcode": "AAA",
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "date": datetime(2026, 5, 15, 11, 1, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 15, 11, 6, tzinfo=timezone.utc
                    ),
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SRID-2",
                        last_change_date=datetime(
                            2026, 5, 15, 11, 6, tzinfo=timezone.utc
                        ),
                        nm_id=2001,
                        barcode="AAA",
                    ),
                    "srid": "SRID-2",
                    "nm_id": 2001,
                    "barcode": "AAA",
                },
                {
                    "id": 3,
                    "account_id": 1,
                    "date": datetime(2026, 5, 15, 11, 2, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 15, 11, 4, tzinfo=timezone.utc
                    ),
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SRID-2",
                        last_change_date=datetime(
                            2026, 5, 15, 11, 4, tzinfo=timezone.utc
                        ),
                        nm_id=2002,
                        barcode="BBB",
                    ),
                    "srid": "SRID-2",
                    "nm_id": 2002,
                    "barcode": "BBB",
                },
            ],
        )
        rows = (
            connection.execute(
                select(sales_current_subquery()).order_by("nm_id", "barcode")
            )
            .mappings()
            .all()
        )

    assert [
        (
            row["nm_id"],
            row["barcode"],
            row["last_change_date"].hour,
            row["last_change_date"].minute,
        )
        for row in rows
    ] == [
        (2001, "AAA", 11, 6),
        (2002, "BBB", 11, 4),
    ]


def test_orders_current_subquery_keeps_distinct_rows_for_same_line_and_different_order_ids() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBOrder.__table__.create(engine)
    same_ts = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(WBOrder),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SRID-LINE",
                        last_change_date=same_ts,
                        nm_id=1001,
                        barcode="111",
                        order_id=11,
                    ),
                    "srid": "SRID-LINE",
                    "nm_id": 1001,
                    "barcode": "111",
                    "order_id": 11,
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SRID-LINE",
                        last_change_date=same_ts,
                        nm_id=1001,
                        barcode="111",
                        order_id=22,
                    ),
                    "srid": "SRID-LINE",
                    "nm_id": 1001,
                    "barcode": "111",
                    "order_id": 22,
                },
            ],
        )
        rows = (
            connection.execute(select(orders_current_subquery()).order_by("order_id"))
            .mappings()
            .all()
        )

    assert [row["order_id"] for row in rows] == [11, 22]


def test_sales_current_subquery_keeps_distinct_rows_for_same_line_and_different_sale_ids() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBSale.__table__.create(engine)
    same_ts = datetime(2026, 5, 15, 11, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(WBSale),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SRID-LINE",
                        last_change_date=same_ts,
                        nm_id=2001,
                        barcode="AAA",
                        sale_id="SALE-11",
                    ),
                    "srid": "SRID-LINE",
                    "nm_id": 2001,
                    "barcode": "AAA",
                    "sale_id": "SALE-11",
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SRID-LINE",
                        last_change_date=same_ts,
                        nm_id=2001,
                        barcode="AAA",
                        sale_id="SALE-22",
                    ),
                    "srid": "SRID-LINE",
                    "nm_id": 2001,
                    "barcode": "AAA",
                    "sale_id": "SALE-22",
                },
            ],
        )
        rows = (
            connection.execute(select(sales_current_subquery()).order_by("sale_id"))
            .mappings()
            .all()
        )

    assert [row["sale_id"] for row in rows] == ["SALE-11", "SALE-22"]


def test_orders_sync_tracks_max_last_change_date() -> None:
    service = OrdersSyncService()

    newest = service._update_max_last_change(None, "2026-05-15T10:00:00+00:00")
    max_value = service._update_max_last_change(newest, "2026-05-15T12:00:00+00:00")
    unchanged = service._update_max_last_change(max_value, "2026-05-15T11:00:00+00:00")

    assert max_value == datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    assert unchanged == max_value


def test_sales_sync_tracks_max_last_change_date() -> None:
    service = SalesSyncService()

    newest = service._update_max_last_change(None, "2026-05-15T08:00:00+00:00")
    max_value = service._update_max_last_change(newest, "2026-05-15T09:30:00+00:00")
    unchanged = service._update_max_last_change(max_value, "invalid")

    assert max_value == datetime(2026, 5, 15, 9, 30, tzinfo=timezone.utc)
    assert unchanged == max_value


@pytest.mark.asyncio
async def test_orders_sync_paginates_until_empty_and_uses_dedupe_key() -> None:
    service = OrdersSyncService()
    service.client = SimpleNamespace(
        fetch_orders=AsyncMock(
            side_effect=[
                [
                    {
                        "date": "2026-05-15T10:00:00+00:00",
                        "lastChangeDate": "2026-05-15T10:05:00+00:00",
                        "srid": "A",
                        "nmId": 111,
                        "barcode": "AAA",
                    },
                    {
                        "date": "2026-05-15T10:01:00+00:00",
                        "lastChangeDate": "2026-05-15T10:06:00+00:00",
                        "srid": "B",
                        "nmId": 222,
                        "barcode": "BBB",
                    },
                ],
                [
                    {
                        "date": "2026-05-15T10:02:00+00:00",
                        "lastChangeDate": "2026-05-15T10:07:00+00:00",
                        "srid": "C",
                        "nmId": 333,
                        "barcode": "CCC",
                    }
                ],
                [],
            ]
        )
    )
    service.repo = SimpleNamespace(upsert_many=AsyncMock())
    service._set_cursor = AsyncMock()
    service.dq_service = SimpleNamespace(resolve_issues=AsyncMock())
    service._open_issue = AsyncMock()

    result = await service.run(
        SimpleNamespace(), account=SimpleNamespace(id=1), force_full=True
    )

    assert service.client.fetch_orders.await_count == 3
    assert service.repo.upsert_many.await_args.kwargs["conflict_fields"] == [
        "dedupe_key"
    ]
    assert len(service.repo.upsert_many.await_args.args[1]) == 3
    assert (
        service._set_cursor.await_args.kwargs["cursor_value"]["lastChangeDate"]
        == "2026-05-15T10:07:00+00:00"
    )
    assert result["pagesLoaded"] == 3


@pytest.mark.asyncio
async def test_sales_sync_paginates_until_empty_and_uses_dedupe_key() -> None:
    service = SalesSyncService()
    service.client = SimpleNamespace(
        fetch_sales=AsyncMock(
            side_effect=[
                [
                    {
                        "date": "2026-05-15T10:00:00+00:00",
                        "lastChangeDate": "2026-05-15T10:05:00+00:00",
                        "srid": "A",
                        "nmId": 111,
                        "barcode": "AAA",
                    },
                    {
                        "date": "2026-05-15T10:01:00+00:00",
                        "lastChangeDate": "2026-05-15T10:06:00+00:00",
                        "srid": "B",
                        "nmId": 222,
                        "barcode": "BBB",
                    },
                ],
                [
                    {
                        "date": "2026-05-15T10:02:00+00:00",
                        "lastChangeDate": "2026-05-15T10:07:00+00:00",
                        "srid": "C",
                        "nmId": 333,
                        "barcode": "CCC",
                    }
                ],
                [],
            ]
        )
    )
    service.repo = SimpleNamespace(upsert_many=AsyncMock())
    service._set_cursor = AsyncMock()
    service.dq_service = SimpleNamespace(resolve_issues=AsyncMock())
    service._open_issue = AsyncMock()

    result = await service.run(
        SimpleNamespace(), account=SimpleNamespace(id=1), force_full=True
    )

    assert service.client.fetch_sales.await_count == 3
    assert service.repo.upsert_many.await_args.kwargs["conflict_fields"] == [
        "dedupe_key"
    ]
    assert len(service.repo.upsert_many.await_args.args[1]) == 3
    assert (
        service._set_cursor.await_args.kwargs["cursor_value"]["lastChangeDate"]
        == "2026-05-15T10:07:00+00:00"
    )
    assert result["pagesLoaded"] == 3


@pytest.mark.asyncio
async def test_orders_sync_boundary_replay_does_not_raise_stuck_issue_for_small_page() -> (
    None
):
    service = OrdersSyncService()
    boundary = "2026-05-15T10:05:00+00:00"
    service.client = SimpleNamespace(
        fetch_orders=AsyncMock(
            return_value=[
                {
                    "date": "2026-05-15T10:00:00+00:00",
                    "lastChangeDate": boundary,
                    "srid": "A",
                    "nmId": 111,
                    "barcode": "AAA",
                }
            ]
        )
    )
    service.repo = SimpleNamespace(upsert_many=AsyncMock())
    service._get_cursor = AsyncMock(
        return_value=SimpleNamespace(cursor_value={"lastChangeDate": boundary})
    )
    service._set_cursor = AsyncMock()
    service.dq_service = SimpleNamespace(resolve_issues=AsyncMock())
    service._open_issue = AsyncMock()

    result = await service.run(
        SimpleNamespace(), account=SimpleNamespace(id=1), force_full=False
    )

    assert (
        service.client.fetch_orders.await_args_list[0].kwargs["date_from"]
        == "2026-05-12T10:05:00+00:00"
    )
    assert result["pagesLoaded"] == 2
    service._open_issue.assert_not_called()


@pytest.mark.asyncio
async def test_sales_sync_boundary_replay_raises_stuck_issue_near_limit() -> None:
    service = SalesSyncService()
    service.PAGINATION_STUCK_WARNING_THRESHOLD = 1
    boundary = "2026-05-15T10:05:00+00:00"
    service.client = SimpleNamespace(
        fetch_sales=AsyncMock(
            return_value=[
                {
                    "date": "2026-05-15T10:00:00+00:00",
                    "lastChangeDate": boundary,
                    "srid": "A",
                    "nmId": 111,
                    "barcode": "AAA",
                }
            ]
        )
    )
    service.repo = SimpleNamespace(upsert_many=AsyncMock())
    service._get_cursor = AsyncMock(
        return_value=SimpleNamespace(cursor_value={"lastChangeDate": boundary})
    )
    service._set_cursor = AsyncMock()
    service.dq_service = SimpleNamespace(resolve_issues=AsyncMock())
    service._open_issue = AsyncMock()

    result = await service.run(
        SimpleNamespace(), account=SimpleNamespace(id=1), force_full=False
    )

    assert (
        service.client.fetch_sales.await_args_list[0].kwargs["date_from"]
        == "2026-05-12T10:05:00+00:00"
    )
    assert result["pagesLoaded"] == 2
    service._open_issue.assert_awaited_once()


def test_orders_table_supports_same_srid_same_last_change_for_different_skus() -> None:
    engine = create_engine("sqlite:///:memory:")
    WBOrder.__table__.create(engine)
    same_ts = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(WBOrder),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=111,
                        barcode="AAA",
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 111,
                    "barcode": "AAA",
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=222,
                        barcode="BBB",
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 222,
                    "barcode": "BBB",
                },
            ],
        )
        rows = (
            connection.execute(select(orders_current_subquery()).order_by("nm_id"))
            .mappings()
            .all()
        )

    assert len(rows) == 2


def test_sales_table_supports_same_srid_same_last_change_for_different_skus() -> None:
    engine = create_engine("sqlite:///:memory:")
    WBSale.__table__.create(engine)
    same_ts = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(WBSale),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=111,
                        barcode="AAA",
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 111,
                    "barcode": "AAA",
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=222,
                        barcode="BBB",
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 222,
                    "barcode": "BBB",
                },
            ],
        )
        rows = (
            connection.execute(select(sales_current_subquery()).order_by("nm_id"))
            .mappings()
            .all()
        )

    assert len(rows) == 2


def test_orders_table_supports_same_srid_same_last_change_same_sku_with_different_order_ids() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBOrder.__table__.create(engine)
    same_ts = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(WBOrder),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=111,
                        barcode="AAA",
                        order_id=101,
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 111,
                    "barcode": "AAA",
                    "order_id": 101,
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=111,
                        barcode="AAA",
                        order_id=202,
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 111,
                    "barcode": "AAA",
                    "order_id": 202,
                },
            ],
        )
        rows = (
            connection.execute(select(WBOrder.__table__).order_by(WBOrder.order_id))
            .mappings()
            .all()
        )

    assert [row["order_id"] for row in rows] == [101, 202]


def test_sales_table_supports_same_srid_same_last_change_same_sku_with_different_sale_ids() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBSale.__table__.create(engine)
    same_ts = datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            insert(WBSale),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=111,
                        barcode="AAA",
                        sale_id="SALE-101",
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 111,
                    "barcode": "AAA",
                    "sale_id": "SALE-101",
                },
                {
                    "id": 2,
                    "account_id": 1,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SAME",
                        last_change_date=same_ts,
                        nm_id=111,
                        barcode="AAA",
                        sale_id="SALE-202",
                    ),
                    "date": same_ts,
                    "last_change_date": same_ts,
                    "srid": "SAME",
                    "nm_id": 111,
                    "barcode": "AAA",
                    "sale_id": "SALE-202",
                },
            ],
        )
        rows = (
            connection.execute(select(WBSale.__table__).order_by(WBSale.sale_id))
            .mappings()
            .all()
        )

    assert [row["sale_id"] for row in rows] == ["SALE-101", "SALE-202"]


def test_finance_acquiring_error_classification_distinguishes_rate_limit() -> None:
    assert FinanceSyncService._classify_acquiring_sync_exception(
        Exception("429 Too Many Requests")
    ) == ("rate_limited", "acquiring_sync_rate_limited", "info")
    assert FinanceSyncService._classify_acquiring_sync_exception(
        Exception("404 not found")
    ) == ("unsupported_by_wb", "acquiring_sync_unsupported", "info")
    assert FinanceSyncService._classify_acquiring_sync_exception(
        Exception("500 boom")
    ) == ("failed_internal", "acquiring_sync_failed", "warning")


@pytest.mark.asyncio
async def test_ads_sync_uses_dedupe_key_conflicts_for_stats_and_clusters() -> None:
    service = AdsSyncService()
    service.client = SimpleNamespace(
        campaigns=AsyncMock(
            return_value={
                "adverts": [
                    {
                        "id": 101,
                        "status": 9,
                        "type": 8,
                        "nm_settings": [{"nmId": 555}],
                    }
                ]
            }
        ),
        full_stats=AsyncMock(
            return_value=[
                {
                    "advertId": 101,
                    "days": [{"date": "2026-05-15", "views": 10, "clicks": 2}],
                }
            ]
        ),
        cluster_stats=AsyncMock(
            return_value=[
                {
                    "advertId": 101,
                    "nmId": 555,
                    "date": "2026-05-15",
                    "cluster": "query",
                    "views": 3,
                    "clicks": 1,
                }
            ]
        ),
    )
    service.campaigns = SimpleNamespace(upsert_many=AsyncMock())
    service.stats = SimpleNamespace(upsert_many=AsyncMock())
    service.cluster_stats = SimpleNamespace(upsert_many=AsyncMock())
    service._set_cursor = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeExecuteResult([WBAdCampaign(id=1, account_id=1, advert_id=101)]),
                _FakeExecuteResult([]),
            ]
        ),
        add=Mock(),
    )

    await service.run(session, account=SimpleNamespace(id=1))

    assert service.stats.upsert_many.await_args.kwargs["conflict_fields"] == [
        "dedupe_key"
    ]
    assert service.cluster_stats.upsert_many.await_args.kwargs["conflict_fields"] == [
        "dedupe_key"
    ]


def test_ads_sync_stats_only_include_allowed_statuses() -> None:
    campaign_ids = AdsSyncService._campaign_ids_for_stats(
        [
            {"advert_id": 101, "status": 9},
            {"advert_id": 202, "status": 11},
            {"advert_id": 303, "status": 4},
        ]
    )

    assert campaign_ids == [101, 202]


@pytest.mark.asyncio
async def test_analytics_region_sales_uses_dedupe_key_conflict() -> None:
    service = AnalyticsSyncService()
    service.client = SimpleNamespace(
        funnel_history=AsyncMock(return_value=[]),
        region_sales=AsyncMock(
            return_value={
                "report": [
                    {
                        "date": "2026-05-15",
                        "regionName": None,
                        "countryName": "UZ",
                        "cityName": None,
                        "nmId": None,
                        "vendorCode": None,
                    }
                ]
            }
        ),
        blocked_products=AsyncMock(return_value={"report": []}),
        shadowed_products=AsyncMock(return_value={"report": []}),
    )
    service.funnel_repo = SimpleNamespace(upsert_many=AsyncMock())
    service.region_repo = SimpleNamespace(upsert_many=AsyncMock())
    service._set_cursor = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeExecuteResult([101]),
                _FakeExecuteResult([]),
                _FakeExecuteResult([]),
                _FakeExecuteResult([]),
                _FakeExecuteResult([]),
                _FakeExecuteResult([]),
            ]
        ),
        add=Mock(),
    )

    await service.run(session, account=SimpleNamespace(id=1))

    assert service.region_repo.upsert_many.await_args.kwargs["conflict_fields"] == [
        "dedupe_key"
    ]


def test_analytics_batches_respect_wb_limit() -> None:
    batches = AnalyticsSyncService._batched_nm_ids(list(range(1, 26)), batch_size=20)

    assert [len(batch) for batch in batches] == [20, 5]
    assert max(len(batch) for batch in batches) == 20


def test_analytics_default_window_is_seven_inclusive_days() -> None:
    start_date, end_date = AnalyticsSyncService._default_window()

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    assert (end - start).days == 6


@pytest.mark.asyncio
async def test_ads_client_uses_v1_cluster_stats_endpoint() -> None:
    sync_base = SimpleNamespace(_request_json=AsyncMock(return_value={}))
    client = AdsClient(sync_base)

    await client.cluster_stats(
        None,
        account_id=1,
        items=[{"advert_id": 1, "nm_id": 2}],
        date_from="2026-05-01",
        date_to="2026-05-02",
    )

    kwargs = sync_base._request_json.await_args.kwargs
    assert kwargs["endpoint"] == "/adv/v1/normquery/stats"
    assert kwargs["url"].endswith("/adv/v1/normquery/stats")
    assert kwargs["json_body"]["items"] == [{"advertId": 1, "nmId": 2}]


def test_ads_sync_fullstats_parser_aggregates_nested_app_nm_rows() -> None:
    rows = AdsSyncService._nm_rows_from_fullstats_period(
        {
            "date": "2026-05-15",
            "apps": [
                {
                    "appType": 1,
                    "nms": [
                        {
                            "nmId": 555,
                            "name": "Dress",
                            "views": 10,
                            "clicks": 2,
                            "sum": 20,
                            "orders": 1,
                            "shks": 2,
                            "canceled": 1,
                            "sum_price": 200,
                        }
                    ],
                },
                {
                    "appType": 32,
                    "nms": [
                        {
                            "nmId": 555,
                            "views": 30,
                            "clicks": 3,
                            "sum": 45,
                            "orders": 2,
                            "shks": 3,
                            "canceled": 0,
                            "sum_price": 300,
                        },
                        {
                            "nmId": 777,
                            "views": 5,
                            "clicks": 0,
                            "sum": 0,
                        },
                    ],
                },
            ],
        },
        linked_nm_ids=[555, 777],
    )

    by_nm = {row["nmId"]: row for row in rows}
    assert by_nm[555]["views"] == 40
    assert by_nm[555]["clicks"] == 5
    assert by_nm[555]["orders"] == 3
    assert by_nm[555]["shks"] == 5
    assert by_nm[555]["canceled"] == 1
    assert by_nm[555]["sum"] == 65
    assert by_nm[555]["sum_price"] == 500
    assert by_nm[555]["ctr"] == 12.5
    assert by_nm[555]["cr"] == 60
    assert by_nm[555]["cpc"] == 13
    assert by_nm[555]["cpm"] == 1625
    assert by_nm[777]["views"] == 5


def test_ads_sync_cluster_parser_supports_v1_daily_stats_payload() -> None:
    rows = AdsSyncService._iter_cluster_stats(
        {
            "items": [
                {
                    "advertId": 101,
                    "nmId": 555,
                    "dailyStats": [
                        {
                            "date": "2026-05-15",
                            "stat": {
                                "normQuery": "summer dress",
                                "avgPos": 3.3,
                                "views": 192,
                                "clicks": 75,
                                "spend": 108,
                            },
                        }
                    ],
                }
            ]
        },
        default_date="2026-05-01",
    )

    assert rows == [
        {
            "advert_id": 101,
            "nm_id": 555,
            "date": "2026-05-15",
            "normQuery": "summer dress",
            "cluster": "summer dress",
            "avgPos": 3.3,
            "avg_position": 3.3,
            "views": 192,
            "clicks": 75,
            "spend": 108,
            "sum": 108,
        }
    ]


@pytest.mark.asyncio
async def test_ads_sync_cluster_parser_supports_norm_query_and_avg_pos() -> None:
    service = AdsSyncService()
    service.client = SimpleNamespace(
        campaigns=AsyncMock(
            return_value={
                "adverts": [
                    {
                        "id": 101,
                        "status": 9,
                        "type": 8,
                        "nm_settings": [{"nmId": 555}],
                    }
                ]
            }
        ),
        full_stats=AsyncMock(return_value=[]),
        cluster_stats=AsyncMock(
            return_value=[
                {
                    "advertId": 101,
                    "nmId": 555,
                    "date": "2026-05-15",
                    "norm_query": "winter jacket",
                    "avg_pos": "2.5",
                    "views": 30,
                    "clicks": 4,
                }
            ]
        ),
    )
    service.campaigns = SimpleNamespace(upsert_many=AsyncMock())
    service.stats = SimpleNamespace(upsert_many=AsyncMock())
    service.cluster_stats = SimpleNamespace(upsert_many=AsyncMock())
    service._set_cursor = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeExecuteResult([WBAdCampaign(id=1, account_id=1, advert_id=101)]),
                _FakeExecuteResult([]),
            ]
        ),
        add=Mock(),
    )

    await service.run(session, account=SimpleNamespace(id=1))

    rows = service.cluster_stats.upsert_many.await_args.args[1]
    assert rows[0]["cluster"] == "winter jacket"
    assert rows[0]["avg_position"] == "2.5"


def test_product_cards_sync_resync_keeps_manual_cost_sku_id() -> None:
    service = ProductCardsSyncService()
    service._relink_manual_costs_for_nm = AsyncMock()
    existing_row = SimpleNamespace(
        id=10,
        account_id=1,
        nm_id=1001,
        vendor_code="SKU-1",
        barcode="111",
        tech_size="42",
        chrt_id=9001,
        size_id=5001,
        dedupe_key=compute_dedupe_key_from_mapping(
            CoreSKU.__dedupe_fields__,
            {
                "account_id": 1,
                "nm_id": 1001,
                "vendor_code": "SKU-1",
                "tech_size": "42",
                "chrt_id": 9001,
                "size_id": 5001,
                "barcode": "111",
            },
        ),
        is_active=True,
    )
    manual_cost = SimpleNamespace(sku_id=10)

    class _FakeCoreSKURepo:
        def __init__(self, rows):
            self.rows = rows
            self.next_id = max(row.id for row in rows) + 1

        async def upsert_many(self, _session, rows, *, conflict_fields):
            assert conflict_fields == ["dedupe_key"]
            for row in rows:
                dedupe_key = row.get("dedupe_key") or compute_dedupe_key_from_mapping(
                    CoreSKU.__dedupe_fields__, row
                )
                existing = next(
                    (item for item in self.rows if item.dedupe_key == dedupe_key), None
                )
                if existing is None:
                    self.rows.append(
                        SimpleNamespace(id=self.next_id, dedupe_key=dedupe_key, **row)
                    )
                    self.next_id += 1
                else:
                    for key, value in row.items():
                        setattr(existing, key, value)
                    existing.dedupe_key = dedupe_key

        async def archive_missing_for_nm(
            self, _session, *, account_id, nm_id, active_dedupe_keys
        ):
            for row in self.rows:
                if row.account_id == account_id and row.nm_id == nm_id:
                    row.is_active = (
                        row.dedupe_key in active_dedupe_keys
                        if active_dedupe_keys
                        else False
                    )

    service.core_skus = _FakeCoreSKURepo([existing_row])
    desired_rows = [
        {
            "account_id": 1,
            "nm_id": 1001,
            "vendor_code": "SKU-1",
            "supplier_article": "SKU-1",
            "barcode": "111",
            "sku": "111",
            "chrt_id": 9001,
            "size_id": 5001,
            "tech_size": "42",
            "title": "Demo",
            "brand": "Brand",
            "subject_id": 10,
            "subject_name": "Subject",
            "is_active": True,
            "source_updated_at": None,
        }
    ]

    import asyncio

    asyncio.run(
        service._sync_core_sku_rows_for_nm(
            None,
            account_id=1,
            nm_id=1001,
            rows=desired_rows,
        )
    )

    assert manual_cost.sku_id == existing_row.id == 10
    assert service.core_skus.rows[0].is_active is True


def test_product_cards_sync_archives_stale_rows_without_deleting_them() -> None:
    service = ProductCardsSyncService()
    service._relink_manual_costs_for_nm = AsyncMock()
    active_row = SimpleNamespace(
        id=10,
        account_id=1,
        nm_id=1001,
        dedupe_key="active-row",
        is_active=True,
    )
    stale_row = SimpleNamespace(
        id=11,
        account_id=1,
        nm_id=1001,
        dedupe_key="stale-row",
        is_active=True,
    )
    manual_cost = SimpleNamespace(sku_id=11)

    class _FakeCoreSKURepo:
        def __init__(self, rows):
            self.rows = rows

        async def upsert_many(self, _session, rows, *, conflict_fields):
            assert conflict_fields == ["dedupe_key"]

        async def archive_missing_for_nm(
            self, _session, *, account_id, nm_id, active_dedupe_keys
        ):
            for row in self.rows:
                if row.account_id == account_id and row.nm_id == nm_id:
                    row.is_active = (
                        row.dedupe_key in active_dedupe_keys
                        if active_dedupe_keys
                        else False
                    )

    service.core_skus = _FakeCoreSKURepo([active_row, stale_row])
    desired_rows = [
        {
            "account_id": 1,
            "nm_id": 1001,
            "vendor_code": "SKU-1",
            "supplier_article": "SKU-1",
            "barcode": "111",
            "sku": "111",
            "chrt_id": 9001,
            "size_id": 5001,
            "tech_size": "42",
            "title": "Demo",
            "brand": "Brand",
            "subject_id": 10,
            "subject_name": "Subject",
            "is_active": True,
            "source_updated_at": None,
            "dedupe_key": "active-row",
        }
    ]

    import asyncio

    asyncio.run(
        service._sync_core_sku_rows_for_nm(
            None,
            account_id=1,
            nm_id=1001,
            rows=desired_rows,
        )
    )

    assert stale_row.id == 11
    assert stale_row.is_active is False
    assert manual_cost.sku_id == 11


@pytest.mark.asyncio
async def test_product_cards_sync_relinks_manual_cost_from_inactive_sku_to_active_sku() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBAccount.__table__.create(engine)
    CoreSKU.__table__.create(engine)
    ManualCost.__table__.create(engine)
    old_dedupe = compute_dedupe_key_from_mapping(
        CoreSKU.__dedupe_fields__,
        {
            "account_id": 1,
            "nm_id": 1001,
            "vendor_code": "SKU-1",
            "tech_size": None,
            "chrt_id": None,
            "size_id": None,
            "barcode": None,
        },
    )
    new_dedupe = compute_dedupe_key_from_mapping(
        CoreSKU.__dedupe_fields__,
        {
            "account_id": 1,
            "nm_id": 1001,
            "vendor_code": "SKU-1",
            "tech_size": "42",
            "chrt_id": 9001,
            "size_id": 5001,
            "barcode": "111",
        },
    )
    with Session(engine) as sync_session:
        sync_session.execute(
            insert(WBAccount),
            [{"id": 1, "name": "Demo", "timezone": "UTC", "is_active": True}],
        )
        sync_session.execute(
            insert(CoreSKU),
            [
                {
                    "id": 10,
                    "account_id": 1,
                    "dedupe_key": old_dedupe,
                    "nm_id": 1001,
                    "vendor_code": "SKU-1",
                    "supplier_article": "SKU-1",
                    "barcode": None,
                    "sku": None,
                    "chrt_id": None,
                    "size_id": None,
                    "tech_size": None,
                    "is_active": False,
                },
                {
                    "id": 11,
                    "account_id": 1,
                    "dedupe_key": new_dedupe,
                    "nm_id": 1001,
                    "vendor_code": "SKU-1",
                    "supplier_article": "SKU-1",
                    "barcode": "111",
                    "sku": "111",
                    "chrt_id": 9001,
                    "size_id": 5001,
                    "tech_size": "42",
                    "is_active": True,
                },
            ],
        )
        sync_session.execute(
            insert(ManualCost),
            [
                {
                    "id": 100,
                    "account_id": 1,
                    "dedupe_key": compute_dedupe_key_from_mapping(
                        ManualCost.__dedupe_fields__,
                        {
                            "account_id": 1,
                            "sku_id": 10,
                            "vendor_code": "SKU-1",
                            "nm_id": 1001,
                            "barcode": "111",
                            "tech_size": "42",
                            "valid_from": date(2026, 5, 1),
                        },
                    ),
                    "sku_id": 10,
                    "vendor_code": "SKU-1",
                    "nm_id": 1001,
                    "barcode": "111",
                    "tech_size": "42",
                    "unit_cost": Decimal("100"),
                    "cost_price": Decimal("100"),
                    "packaging_cost": Decimal("0"),
                    "inbound_logistics_cost": Decimal("0"),
                    "currency": "RUB",
                    "valid_from": date(2026, 5, 1),
                    "is_ambiguous": False,
                }
            ],
        )
        sync_session.commit()
        session = _AsyncSessionAdapter(sync_session)
        service = ProductCardsSyncService()

        metrics = await service._relink_manual_costs_for_nm(
            session,
            account_id=1,
            nm_id=1001,
            vendor_codes={"SKU-1"},
        )
        updated_cost = sync_session.execute(
            select(ManualCost).where(ManualCost.id == 100)
        ).scalar_one()

    assert metrics["relinked"] == 1
    assert updated_cost.sku_id == 11


@pytest.mark.asyncio
async def test_product_cards_sync_uses_cursor_total_and_persists_last_cursor() -> None:
    service = ProductCardsSyncService()

    def _card(nm_id: int) -> dict:
        return {
            "nmID": nm_id,
            "imtID": nm_id + 1000,
            "nmUUID": f"uuid-{nm_id}",
            "subjectID": 10,
            "subjectName": "Outerwear",
            "vendorCode": f"SKU-{nm_id}",
            "title": f"Card {nm_id}",
            "description": f"Description {nm_id}",
            "brand": "Brand",
            "needKiz": False,
            "kizMarked": False,
            "photos": [],
            "video": None,
            "dimensions": {},
            "createdAt": "2026-05-16T09:00:00+00:00",
            "updatedAt": "2026-05-16T10:00:00+00:00",
            "sizes": [],
            "characteristics": [],
            "tags": [],
        }

    page_one_cards = [_card(nm_id) for nm_id in range(1, 101)]
    page_two_cards = [_card(nm_id) for nm_id in range(101, 106)]
    first_cursor = {"updatedAt": "2026-05-16T10:00:00+00:00", "nmID": 100, "total": 100}
    second_cursor = {"updatedAt": "2026-05-16T11:00:00+00:00", "nmID": 105, "total": 5}

    service.client = SimpleNamespace(
        list_tags=AsyncMock(return_value={}),
        list_cards=AsyncMock(
            side_effect=[
                {"cards": page_one_cards, "cursor": first_cursor},
                {"cards": page_two_cards, "cursor": second_cursor},
            ]
        ),
    )
    service.repo = SimpleNamespace(
        upsert_many=AsyncMock(),
        replace_children=AsyncMock(),
    )
    service._sync_core_sku_rows_for_nm = AsyncMock()
    service._sync_price_only_core_skus = AsyncMock(return_value=0)
    service._set_cursor = AsyncMock()
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeExecuteResult(
                    [
                        SimpleNamespace(
                            id=nm_id,
                            account_id=1,
                            nm_id=nm_id,
                            vendor_code=f"SKU-{nm_id}",
                            title=f"Card {nm_id}",
                            brand="Brand",
                            subject_id=10,
                            subject_name="Outerwear",
                            updated_at_wb=datetime(
                                2026, 5, 16, 10, 0, tzinfo=timezone.utc
                            ),
                        )
                        for nm_id in range(1, 101)
                    ]
                ),
                _FakeExecuteResult(
                    [
                        SimpleNamespace(
                            id=nm_id,
                            account_id=1,
                            nm_id=nm_id,
                            vendor_code=f"SKU-{nm_id}",
                            title=f"Card {nm_id}",
                            brand="Brand",
                            subject_id=10,
                            subject_name="Outerwear",
                            updated_at_wb=datetime(
                                2026, 5, 16, 11, 0, tzinfo=timezone.utc
                            ),
                        )
                        for nm_id in range(101, 106)
                    ]
                ),
            ]
        ),
        add=Mock(),
    )

    result = await service.run(session, account=SimpleNamespace(id=1), force_full=True)

    assert service.client.list_cards.await_count == 2
    assert service.client.list_cards.await_args_list[1].kwargs["cursor"] == first_cursor
    assert result["rows"] == 105
    assert result["pagesLoaded"] == 2
    assert service._set_cursor.await_args.kwargs["cursor_value"] == {
        "updatedAt": second_cursor["updatedAt"],
        "nmID": second_cursor["nmID"],
    }


@pytest.mark.asyncio
async def test_mart_sales_loader_uses_event_date_not_last_change_date() -> None:
    engine = create_engine("sqlite:///:memory:")
    WBAccount.__table__.create(engine)
    WBSale.__table__.create(engine)
    with Session(engine) as sync_session:
        sync_session.execute(
            insert(WBAccount),
            [{"id": 1, "name": "Demo", "timezone": "UTC", "is_active": True}],
        )
        sync_session.execute(
            insert(WBSale),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SALE-1",
                        last_change_date=datetime(
                            2026, 5, 11, 9, 0, tzinfo=timezone.utc
                        ),
                        nm_id=1001,
                        barcode="111",
                    ),
                    "date": datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 11, 9, 0, tzinfo=timezone.utc
                    ),
                    "srid": "SALE-1",
                    "nm_id": 1001,
                    "barcode": "111",
                }
            ],
        )
        sync_session.commit()
        session = _AsyncSessionAdapter(sync_session)

        rows = await MartService()._load_current_sales(
            session,
            account_id=1,
            date_from=date(2026, 5, 10),
            date_to=date(2026, 5, 10),
        )

    assert len(rows) == 1
    assert rows[0]["srid"] == "SALE-1"


@pytest.mark.asyncio
async def test_mart_orders_loader_uses_event_date_not_last_change_date() -> None:
    engine = create_engine("sqlite:///:memory:")
    WBAccount.__table__.create(engine)
    WBOrder.__table__.create(engine)
    with Session(engine) as sync_session:
        sync_session.execute(
            insert(WBAccount),
            [{"id": 1, "name": "Demo", "timezone": "UTC", "is_active": True}],
        )
        sync_session.execute(
            insert(WBOrder),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="ORDER-1",
                        last_change_date=datetime(
                            2026, 5, 11, 9, 0, tzinfo=timezone.utc
                        ),
                        nm_id=1001,
                        barcode="111",
                    ),
                    "date": datetime(2026, 5, 10, 10, 0, tzinfo=timezone.utc),
                    "last_change_date": datetime(
                        2026, 5, 11, 9, 0, tzinfo=timezone.utc
                    ),
                    "srid": "ORDER-1",
                    "nm_id": 1001,
                    "barcode": "111",
                }
            ],
        )
        sync_session.commit()
        session = _AsyncSessionAdapter(sync_session)

        rows = await MartService()._load_current_orders(
            session,
            account_id=1,
            date_from=date(2026, 5, 10),
            date_to=date(2026, 5, 10),
        )

    assert len(rows) == 1
    assert rows[0]["srid"] == "ORDER-1"


@pytest.mark.asyncio
async def test_mart_sales_loader_does_not_fallback_to_last_change_date_when_event_date_is_missing() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBAccount.__table__.create(engine)
    WBSale.__table__.create(engine)
    with Session(engine) as sync_session:
        sync_session.execute(
            insert(WBAccount),
            [{"id": 1, "name": "Demo", "timezone": "UTC", "is_active": True}],
        )
        sync_session.execute(
            insert(WBSale),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _sale_dedupe_key(
                        account_id=1,
                        srid="SALE-NULL-DATE",
                        last_change_date=datetime(
                            2026, 5, 10, 9, 0, tzinfo=timezone.utc
                        ),
                        nm_id=1001,
                        barcode="111",
                    ),
                    "date": None,
                    "last_change_date": datetime(
                        2026, 5, 10, 9, 0, tzinfo=timezone.utc
                    ),
                    "srid": "SALE-NULL-DATE",
                    "nm_id": 1001,
                    "barcode": "111",
                }
            ],
        )
        sync_session.commit()
        session = _AsyncSessionAdapter(sync_session)

        rows = await MartService()._load_current_sales(
            session,
            account_id=1,
            date_from=date(2026, 5, 10),
            date_to=date(2026, 5, 10),
        )

    assert rows == []


@pytest.mark.asyncio
async def test_mart_orders_loader_does_not_fallback_to_last_change_date_when_event_date_is_missing() -> (
    None
):
    engine = create_engine("sqlite:///:memory:")
    WBAccount.__table__.create(engine)
    WBOrder.__table__.create(engine)
    with Session(engine) as sync_session:
        sync_session.execute(
            insert(WBAccount),
            [{"id": 1, "name": "Demo", "timezone": "UTC", "is_active": True}],
        )
        sync_session.execute(
            insert(WBOrder),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _order_dedupe_key(
                        account_id=1,
                        srid="ORDER-NULL-DATE",
                        last_change_date=datetime(
                            2026, 5, 10, 9, 0, tzinfo=timezone.utc
                        ),
                        nm_id=1001,
                        barcode="111",
                    ),
                    "date": None,
                    "last_change_date": datetime(
                        2026, 5, 10, 9, 0, tzinfo=timezone.utc
                    ),
                    "srid": "ORDER-NULL-DATE",
                    "nm_id": 1001,
                    "barcode": "111",
                }
            ],
        )
        sync_session.commit()
        session = _AsyncSessionAdapter(sync_session)

        rows = await MartService()._load_current_orders(
            session,
            account_id=1,
            date_from=date(2026, 5, 10),
            date_to=date(2026, 5, 10),
        )

    assert rows == []


def test_http_rate_limit_sleep_prefers_retry_header() -> None:
    assert (
        WBHTTPClient._rate_limit_sleep_seconds(
            {"x-ratelimit-retry": "20"},
            attempt_count=2,
        )
        == 20
    )


def test_http_rate_limit_sleep_falls_back_without_headers() -> None:
    assert WBHTTPClient._rate_limit_sleep_seconds({}, attempt_count=2) == 2


@pytest.mark.asyncio
async def test_raw_response_service_stores_response_headers() -> None:
    service = RawResponseService()
    service.repo = SimpleNamespace(create=AsyncMock(return_value=SimpleNamespace(id=1)))

    await service.store(
        None,
        account_id=1,
        api_category="finance",
        endpoint="/api/finance/v1/sales-reports/detailed",
        http_method="POST",
        request_params={},
        request_body={"dateFrom": "2026-05-01"},
        response_json={"ok": True},
        response_text='{"ok": true}',
        response_headers={"x-ratelimit-retry": "20"},
        status_code=200,
        is_success=True,
        retry_count=0,
        requested_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
        loaded_at=datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc),
    )

    assert service.repo.create.await_args.kwargs["response_headers"] == {
        "x-ratelimit-retry": "20"
    }


@pytest.mark.asyncio
async def test_domain_sync_base_tracks_rate_limit_runtime_details(monkeypatch) -> None:
    service = OrdersSyncService()
    service.account_service = SimpleNamespace(
        get_decrypted_token=AsyncMock(return_value="token")
    )
    service.raw_service = SimpleNamespace(store=AsyncMock())

    async def _fake_request_json(self, _method, _url, *, params=None, json_body=None):
        return WBResponse(
            status_code=200,
            requested_at=datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc),
            loaded_at=datetime(2026, 5, 16, 10, 0, 20, tzinfo=timezone.utc),
            payload={"ok": True},
            retry_count=1,
            text='{"ok": true}',
            headers={"x-ratelimit-retry": "20"},
            rate_limited_count=1,
            last_rate_limit_retry_after=20.0,
        )

    monkeypatch.setattr(
        "app.core.wb_sync.WBHTTPClient.request_json", _fake_request_json
    )

    payload = await service._request_json(
        SimpleNamespace(),
        account_id=1,
        endpoint="/api/v1/some-endpoint",
        url="https://statistics-api.wildberries.ru/api/v1/supplier/orders",
    )

    assert payload == {"ok": True}
    assert service.runtime_details() == {
        "rate_limited_count": 1,
        "last_rate_limit_retry_after": 20.0,
    }


@pytest.mark.asyncio
async def test_refresh_account_expense_daily_collects_unallocated_finance_expenses() -> (
    None
):
    service = MartService()
    service.account_expense_repo = SimpleNamespace(upsert_many=AsyncMock())
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _FakeExecuteResult([]),
                _FakeExecuteResult(
                    [
                        WBRealizationReportRow(
                            rr_date=date(2026, 5, 15),
                            nm_id=None,
                            doc_type_name="Хранение",
                            paid_storage=Decimal("25"),
                            penalty=Decimal("5"),
                            additional_payment=Decimal("2"),
                            rrd_id=10,
                        ),
                        WBRealizationReportRow(
                            rr_date=date(2026, 5, 15),
                            nm_id=1001,
                            doc_type_name="Хранение",
                            paid_storage=Decimal("99"),
                            rrd_id=11,
                        ),
                    ]
                ),
                _FakeExecuteResult(
                    [
                        MartSKUDaily(
                            account_id=1,
                            dedupe_key="sku-daily-1",
                            stat_date=date(2026, 5, 15),
                            nm_id=1001,
                            seller_cogs=Decimal("40"),
                            seller_other_expense=Decimal("10"),
                            total_seller_expenses=Decimal("50"),
                            additional_payments=Decimal("-3"),
                            net_profit_after_all_expenses=Decimal("17"),
                        )
                    ]
                ),
            ]
        ),
    )

    rows = await service._refresh_account_expense_daily(
        session,
        account_id=1,
        date_from=date(2026, 5, 15),
        date_to=date(2026, 5, 15),
    )

    assert rows == 1
    upsert_rows = service.account_expense_repo.upsert_many.await_args.args[1]
    assert upsert_rows[0]["seller_cogs"] == Decimal("40")
    assert upsert_rows[0]["seller_other_expense"] == Decimal("10")
    assert upsert_rows[0]["total_seller_expenses"] == Decimal("50")
    assert upsert_rows[0]["additional_payments"] == Decimal("5")
    assert upsert_rows[0]["net_profit_after_all_expenses"] == Decimal("17")
    assert upsert_rows[0]["payload"]["seller_cost_sku_rows"] == 1


@pytest.mark.asyncio
async def test_data_quality_flags_manual_cost_unresolved_active_sku_link() -> None:
    engine = create_engine("sqlite:///:memory:")
    WBAccount.__table__.create(engine)
    CoreSKU.__table__.create(engine)
    ManualCost.__table__.create(engine)

    with Session(engine) as sync_session:
        sync_session.execute(
            insert(WBAccount),
            [{"id": 1, "name": "Demo", "timezone": "UTC", "is_active": True}],
        )
        sync_session.execute(
            insert(CoreSKU),
            [
                {
                    "id": 1,
                    "account_id": 1,
                    "dedupe_key": _core_sku_dedupe_key(
                        account_id=1,
                        nm_id=1001,
                        vendor_code="SKU-1",
                        tech_size="M",
                        chrt_id=10,
                        size_id=20,
                        barcode="111",
                    ),
                    "nm_id": 1001,
                    "vendor_code": "SKU-1",
                    "barcode": "111",
                    "tech_size": "M",
                    "chrt_id": 10,
                    "size_id": 20,
                    "is_active": True,
                }
            ],
        )
        sync_session.execute(
            insert(ManualCost),
            [
                {
                    "id": 500,
                    "account_id": 1,
                    "dedupe_key": compute_dedupe_key_from_mapping(
                        ManualCost.__dedupe_fields__,
                        {
                            "account_id": 1,
                            "sku_id": None,
                            "vendor_code": "UNMATCHED",
                            "nm_id": 9999,
                            "barcode": "999",
                            "tech_size": "XL",
                            "valid_from": date(2026, 5, 1),
                        },
                    ),
                    "sku_id": None,
                    "vendor_code": "UNMATCHED",
                    "nm_id": 9999,
                    "barcode": "999",
                    "tech_size": "XL",
                    "unit_cost": Decimal("10"),
                    "cost_price": Decimal("10"),
                    "packaging_cost": Decimal("0"),
                    "inbound_logistics_cost": Decimal("0"),
                    "currency": "RUB",
                    "valid_from": date(2026, 5, 1),
                    "is_ambiguous": False,
                }
            ],
        )
        sync_session.commit()

        session = _AsyncSessionAdapter(sync_session)
        service = DataQualityService()
        service.open_issue = AsyncMock()

        touched = await service._check_manual_cost_linkage(session, account_id=1)

    assert touched == 1
    assert service.open_issue.await_args.kwargs["code"] == "manual_cost_unresolved_sku"


@pytest.mark.asyncio
async def test_resolve_issues_can_target_specific_entity_key() -> None:
    execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))
    session = SimpleNamespace(execute=execute)
    service = DataQualityService()

    resolved = await service.resolve_issues(
        session,  # type: ignore[arg-type]
        domain="scheduler",
        codes=["scheduler_job_failed"],
        account_id=1,
        entity_key="analytics:1",
    )

    statement = execute.await_args.args[0]
    compiled = str(statement.compile(compile_kwargs={"literal_binds": True}))

    assert resolved == 1
    assert "entity_key = 'analytics:1'" in compiled
    assert "domain = 'scheduler'" in compiled
    assert "scheduler_job_failed" in compiled


@pytest.mark.asyncio
async def test_list_issues_passes_detected_period_to_repository() -> None:
    raw_issue = SimpleNamespace(
        id=1,
        account_id=1,
        domain="data_quality",
        severity="warning",
        code="missing_manual_cost",
        entity_key=None,
        entity_type=None,
        entity_id=None,
        sku_id=None,
        nm_id=100,
        source_table=None,
        message="msg",
        payload={},
        detected_at=datetime(2026, 5, 16),
        resolved_at=None,
    )
    repo = SimpleNamespace(
        list_filtered=AsyncMock(
            return_value=Page(total=1, limit=100, offset=0, items=[raw_issue])
        )
    )
    service = DataQualityService()
    service.repo = repo  # type: ignore[assignment]

    result = await service.list_issues(
        None,  # type: ignore[arg-type]
        account_id=1,
        only_open=True,
        detected_from=date(2026, 5, 10),
        detected_to=date(2026, 5, 16),
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].code == "missing_manual_cost"
    kwargs = repo.list_filtered.await_args.kwargs
    assert kwargs["detected_from"] == date(2026, 5, 10)
    assert kwargs["detected_to"] == date(2026, 5, 16)
