from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import BigInteger, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from app.models.accounts import WBAccount
from app.models.ads import WBAdStatsDaily
from app.models.analytics import WBCardFunnelDaily
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.prices import WBPrice, WBPriceSize
from app.models.problem_engine import MetricCatalog
from app.models.sync import WBSyncCursor
from app.services.problem_engine import FormulaEvaluator, MetricCatalogService, ProductMetricResolver


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw) -> str:
    return "JSON"


@compiles(BigInteger, "sqlite")
def _compile_bigint_sqlite(_type, _compiler, **_kw) -> str:
    return "INTEGER"


class _AsyncSessionAdapter:
    def __init__(self, sync_session: Session):
        self._session = sync_session

    async def execute(self, statement):
        return self._session.execute(statement)

    def add(self, instance) -> None:
        self._session.add(instance)

    async def flush(self) -> None:
        self._session.flush()


def _create_tables(engine, *tables) -> None:
    for table in tables:
        table.create(engine)


async def _seed_catalog(session: _AsyncSessionAdapter) -> MetricCatalogService:
    service = MetricCatalogService()
    await service.seed_initial_metrics(session)  # type: ignore[arg-type]
    return service


def _source_tables():
    return (
        WBAccount.__table__,
        MetricCatalog.__table__,
        WBSyncCursor.__table__,
        MartSKUDaily.__table__,
        MartStockDaily.__table__,
        WBPrice.__table__,
        WBPriceSize.__table__,
        ManualCost.__table__,
        WBAdStatsDaily.__table__,
        WBCardFunnelDaily.__table__,
    )


def _insert_product_metric_sources(sync_session: Session) -> None:
    sync_session.add(WBAccount(id=1, name="Test account"))
    sync_session.add_all(
        [
            WBSyncCursor(id=1, account_id=1, domain="finance", cursor_key="default", last_synced_at=datetime(2026, 7, 6, tzinfo=timezone.utc), status="completed"),
            WBSyncCursor(id=2, account_id=1, domain="stocks", cursor_key="default", last_synced_at=datetime(2026, 7, 6, tzinfo=timezone.utc), status="completed"),
            WBSyncCursor(id=3, account_id=1, domain="prices", cursor_key="default", last_synced_at=datetime(2026, 7, 6, tzinfo=timezone.utc), status="completed"),
            WBSyncCursor(id=4, account_id=1, domain="ads", cursor_key="default", last_synced_at=datetime(2026, 7, 6, tzinfo=timezone.utc), status="completed"),
            WBSyncCursor(id=5, account_id=1, domain="analytics", cursor_key="default", last_synced_at=datetime(2026, 7, 6, tzinfo=timezone.utc), status="completed"),
        ]
    )
    sync_session.add(
        MartSKUDaily(
            id=1,
            account_id=1,
            stat_date=date(2026, 7, 6),
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="BC-1",
            ordered_units=10,
            final_sales_qty=8,
            final_return_qty=2,
            final_net_qty=6,
            final_revenue=Decimal("1000"),
            commission=Decimal("60"),
            logistics=Decimal("30"),
            acquiring_fee=Decimal("12"),
            storage=Decimal("6"),
            marketing_deduction=Decimal("20"),
            cost_price=Decimal("50"),
            estimated_profit_after_ads=Decimal("240"),
            margin_percent=Decimal("24"),
            current_price=Decimal("200"),
            current_discounted_price=Decimal("150"),
            has_manual_cost=True,
            has_real_manual_cost=True,
            business_trusted=True,
        )
    )
    sync_session.add(
        MartStockDaily(
            id=1,
            account_id=1,
            stat_date=date(2026, 7, 6),
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="BC-1",
            warehouse_id=77,
            warehouse_name="Main",
            quantity=Decimal("60"),
            quantity_full=Decimal("60"),
            sales_7d=7,
            sales_14d=14,
            sales_30d=6,
        )
    )
    sync_session.add(WBPriceSize(id=1, account_id=1, nm_id=1001, size_id=1, price=Decimal("200"), discounted_price=Decimal("150")))
    sync_session.add(
        ManualCost(
            id=1,
            account_id=1,
            nm_id=1001,
            vendor_code="SKU-1",
            barcode="BC-1",
            unit_cost=Decimal("50"),
            cost_price=Decimal("50"),
            valid_from=date(2026, 1, 1),
            is_business_trusted=True,
            is_placeholder=False,
            is_ambiguous=False,
        )
    )
    sync_session.add(WBAdStatsDaily(id=1, account_id=1, advert_id=10, stat_date=date(2026, 7, 6), nm_id=1001, views=100, orders=4, sum=Decimal("70")))
    sync_session.add(WBCardFunnelDaily(id=1, account_id=1, stat_date=date(2026, 7, 6), nm_id=1001, open_count=100, order_count=5))
    sync_session.flush()


@pytest.mark.asyncio
async def test_metric_catalog_service_lists_seeded_metrics() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine, MetricCatalog.__table__)

    with Session(engine) as sync_session:
        session = _AsyncSessionAdapter(sync_session)
        service = await _seed_catalog(session)

        metrics = await service.list_metrics(session)  # type: ignore[arg-type]

    codes = {metric.metric_code for metric in metrics}
    assert len(codes) >= 29
    assert {
        "stock_qty",
        "unit_profit",
        "promo_spend_30d",
        "sales_30d",
        "sales_7d",
        "units_sold_7d",
        "avg_daily_revenue_7d",
        "unit_profit_after_ads",
    }.issubset(codes)


@pytest.mark.asyncio
async def test_product_metric_resolver_returns_values_with_source_evidence() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine, *_source_tables())

    with Session(engine) as sync_session:
        session = _AsyncSessionAdapter(sync_session)
        catalog = await _seed_catalog(session)
        _insert_product_metric_sources(sync_session)

        result = await ProductMetricResolver(catalog).resolve_product_metrics(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            metric_codes=[
                "stock_qty",
                "days_of_stock",
                "revenue_30d",
                "avg_daily_revenue_7d",
                "orders_30d",
                "price_after_discount",
                "commission_per_unit",
                "ad_spend_30d",
                "cost_price",
                "unit_profit",
                "unit_profit_after_ads",
                "return_rate",
                "conversion_rate",
                "views_30d",
                "sales_7d",
                "units_sold_7d",
            ],
        )

    assert result.missing_metrics == []
    assert result.metrics["stock_qty"].value == Decimal("60.0000")
    assert result.metrics["days_of_stock"].value == Decimal("300.0000")
    assert result.metrics["revenue_30d"].value == Decimal("1000.0000")
    assert result.metrics["avg_daily_revenue_7d"].value == Decimal("142.8571428571428571428571429")
    assert result.metrics["orders_30d"].value == 10
    assert result.metrics["price_after_discount"].value == Decimal("150.0000")
    assert result.metrics["commission_per_unit"].value == Decimal("10.0000")
    assert result.metrics["ad_spend_30d"].value == Decimal("70.0000")
    assert result.metrics["cost_price"].value == Decimal("50.0000")
    assert result.metrics["unit_profit"].value == Decimal("40.0000")
    assert result.metrics["unit_profit_after_ads"].value == Decimal("40.0000")
    assert result.metrics["return_rate"].value == Decimal("25.00")
    assert result.metrics["conversion_rate"].value == Decimal("5.00")
    assert result.metrics["views_30d"].value == 100
    assert result.metrics["sales_7d"].value == Decimal("7.0000")
    assert result.metrics["units_sold_7d"].value == Decimal("7.0000")
    assert result.metrics["stock_qty"].evidence.source_table == "mart_stock_daily"
    assert result.metrics["stock_qty"].evidence.row_count == 1
    assert result.metrics["stock_qty"].evidence.freshness["sync_cursor"]["status"] == "completed"


@pytest.mark.asyncio
async def test_product_metric_resolver_prefers_fresh_price_payload_over_stale_size_rows() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine, *_source_tables())

    with Session(engine) as sync_session:
        sync_session.add(WBAccount(id=1, name="Test account"))
        sync_session.add(
            WBSyncCursor(
                id=1,
                account_id=1,
                domain="prices",
                cursor_key="default",
                last_synced_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
                status="completed",
            )
        )
        sync_session.add(
            WBPrice(
                id=1,
                account_id=1,
                nm_id=405299326,
                payload={
                    "sizes": [
                        {"sizeID": 583552422, "price": 18900, "discountedPrice": 15876},
                        {"sizeID": 583552423, "price": 18900, "discountedPrice": 15876},
                    ]
                },
                updated_at=datetime(2026, 7, 13, tzinfo=timezone.utc),
            )
        )
        sync_session.add(
            WBPriceSize(
                id=1,
                account_id=1,
                nm_id=405299326,
                size_id=583552422,
                price=Decimal("189"),
                discounted_price=Decimal("107.73"),
                updated_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
            )
        )
        session = _AsyncSessionAdapter(sync_session)
        catalog = await _seed_catalog(session)

        result = await ProductMetricResolver(catalog).resolve_product_metrics(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=405299326,
            date_from=date(2026, 6, 15),
            date_to=date(2026, 7, 14),
            metric_codes=["price_current", "price_after_discount"],
        )

    assert result.missing_metrics == []
    assert result.metrics["price_current"].value == Decimal("18900")
    assert result.metrics["price_after_discount"].value == Decimal("15876")
    assert result.metrics["price_current"].evidence.source_table == "wb_prices"


@pytest.mark.asyncio
async def test_product_metric_resolver_reports_missing_metrics_instead_of_fake_values() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine, *_source_tables())

    with Session(engine) as sync_session:
        sync_session.add(WBAccount(id=1, name="Test account"))
        session = _AsyncSessionAdapter(sync_session)
        catalog = await _seed_catalog(session)

        result = await ProductMetricResolver(catalog).resolve_product_metrics(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=404,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            metric_codes=["cost_price", "promo_spend_30d", "unknown_metric"],
        )

    assert result.missing_metrics == ["cost_price", "promo_spend_30d", "unknown_metric"]
    assert result.metrics["cost_price"].value is None
    assert result.metrics["promo_spend_30d"].value is None
    assert result.metrics["unknown_metric"].missing_reason == "unknown_metric"
    assert result.metrics["cost_price"].evidence.row_count == 0


@pytest.mark.asyncio
async def test_formula_engine_can_use_resolved_metric_values() -> None:
    engine = create_engine("sqlite:///:memory:")
    _create_tables(engine, *_source_tables())

    with Session(engine) as sync_session:
        session = _AsyncSessionAdapter(sync_session)
        catalog = await _seed_catalog(session)
        _insert_product_metric_sources(sync_session)

        resolution = await ProductMetricResolver(catalog).resolve_product_metrics(
            session,  # type: ignore[arg-type]
            account_id=1,
            nm_id=1001,
            date_from=date(2026, 6, 7),
            date_to=date(2026, 7, 6),
            metric_codes=["stock_qty", "avg_daily_sales_7d", "unit_profit"],
        )
        allowed_metrics = await catalog.allowed_metric_codes(session)  # type: ignore[arg-type]

    result = FormulaEvaluator().evaluate_condition(
        {
            "and": [
                {">": [{"metric": "stock_qty"}, 50]},
                {">": [{"metric": "avg_daily_sales_7d"}, 0]},
                {">": [{"metric": "unit_profit"}, 0]},
            ]
        },
        metrics=resolution.values_for_formula(),
        evaluation_context={"allowed_metrics": allowed_metrics},
    )

    assert result.error is None
    assert result.value is True
    assert result.missing_metrics == []
