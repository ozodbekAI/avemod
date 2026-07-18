from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.modules.analytics import router as analytics_router
from app.services.auth import get_current_user


async def _override_session():
    yield None


def _override_user():
    return SimpleNamespace(id=1, is_superuser=True)


async def _allow_read(*args, **kwargs):
    return None


def _metric(value: float | int | None):
    return {
        "value": value,
        "previous_value": None,
        "delta": None,
        "delta_percent": None,
    }


def _overview_payload():
    return {
        "account_id": 1,
        "period": {
            "date_from": "2026-07-01",
            "date_to": "2026-07-17",
            "previous_date_from": "2026-06-14",
            "previous_date_to": "2026-06-30",
        },
        "summary": {
            "open_count": _metric(1000),
            "cart_count": _metric(120),
            "order_count": _metric(50),
            "buyout_count": _metric(40),
            "cancel_count": _metric(2),
            "revenue": _metric(125000),
            "units_sold": _metric(42),
            "active_cards": _metric(7),
            "cart_rate": _metric(12.0),
            "order_rate": _metric(41.67),
            "buyout_rate": _metric(80.0),
            "avg_order_value": _metric(2500),
            "hidden_blocked": 0,
            "hidden_shadowed": 1,
        },
        "trend": [
            {
                "date": "2026-07-01",
                "open_count": 100,
                "cart_count": 12,
                "order_count": 5,
                "buyout_count": 4,
                "cancel_count": 0,
                "revenue": 12000,
                "units_sold": 4,
                "cart_rate": 12.0,
                "order_rate": 41.67,
                "buyout_rate": 80.0,
            }
        ],
        "products": [
            {
                "nm_id": 123,
                "vendor_code": "SKU-123",
                "title": "Card",
                "brand_name": "Brand",
                "subject_name": "Subject",
                "open_count": 100,
                "cart_count": 12,
                "order_count": 5,
                "buyout_count": 4,
                "cancel_count": 0,
                "revenue": 12000,
                "units_sold": 4,
                "cart_rate": 12.0,
                "order_rate": 41.67,
                "buyout_rate": 80.0,
                "open_delta_percent": None,
                "order_delta_percent": None,
                "revenue_delta_percent": None,
                "status": "ok",
                "issue": None,
                "action": None,
            }
        ],
        "regions": [
            {
                "country_name": "RU",
                "region_name": "Moscow",
                "city_name": "Moscow",
                "federal_district": None,
                "revenue": 12000,
                "units_sold": 4,
                "cards_count": 1,
                "share_percent": 100.0,
            }
        ],
        "data_sources": [
            {
                "key": "sales_funnel",
                "label": "WB sales funnel history",
                "status": "ok",
                "rows": 1,
                "note": "/api/analytics/v3/sales-funnel/products/history",
            }
        ],
        "api_capabilities": [
            {
                "key": "sales_funnel",
                "label": "Sales funnel by item",
                "endpoint": "/api/analytics/v3/sales-funnel/products",
                "status": "active",
                "note": None,
            }
        ],
        "recommendations": [],
        "export_datasets": ["products", "regions", "trend"],
    }


def test_analytics_overview_route_contract(monkeypatch) -> None:
    async def _fake_overview(session, **kwargs):
        assert kwargs["account_id"] == 1
        assert str(kwargs["date_from"]) == "2026-07-01"
        return _overview_payload()

    monkeypatch.setattr(analytics_router, "_require_analytics_read", _allow_read)
    monkeypatch.setattr(analytics_router.service, "overview", _fake_overview)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/analytics/overview?account_id=1&date_from=2026-07-01&date_to=2026-07-17"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["summary"]["order_count"]["value"] == 50
    assert body["products"][0]["vendor_code"] == "SKU-123"
    assert body["export_datasets"] == ["products", "regions", "trend"]


def test_analytics_csv_export_route_contract(monkeypatch) -> None:
    async def _fake_export_csv(session, **kwargs):
        assert kwargs["dataset"] == "products"
        return "nm_id,orders\n123,5\n"

    monkeypatch.setattr(analytics_router, "_require_analytics_read", _allow_read)
    monkeypatch.setattr(analytics_router.service, "export_csv", _fake_export_csv)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/analytics/export.csv?account_id=1&dataset=products")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "analytics_products_1.csv" in response.headers["content-disposition"]
    assert response.text.startswith("nm_id,orders")
