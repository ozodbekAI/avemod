from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.modules.control_tower import router as control_tower_router
from app.schemas.control_tower import PriceSafetyPage, PurchasePlanPage, PurchasePlanRow
from app.services.auth import get_current_superuser


async def _override_session():
    yield None


def _override_user():
    return SimpleNamespace(id=1)


def test_control_tower_routes_are_registered_in_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    expected_paths = {
        "/api/v1/dashboard/owner",
        "/api/v1/skus/statuses",
        "/api/v1/skus",
        "/api/v1/skus/{sku_id}",
        "/api/v1/actions",
        "/api/v1/actions/{action_id}",
        "/api/v1/actions/bulk",
        "/api/v1/inventory/purchase-plan",
        "/api/v1/pricing/safety",
        "/api/v1/pricing/simulate",
        "/api/v1/ads/efficiency",
        "/api/v1/money/summary",
        "/api/v1/money/profit-cascade",
        "/api/v1/money/expenses/breakdown",
        "/api/v1/money/expenses/logistics",
        "/api/v1/money/expenses/report-rows",
        "/api/v1/money/cards",
        "/api/v1/money/cards/{sku_id}",
        "/api/v1/money/articles",
        "/api/v1/money/articles/{nm_id}",
        "/api/v1/money/actions/today",
        "/api/v1/money/data-blockers",
        "/api/v1/money/filters",
        "/api/v1/settings/business",
        "/api/v1/settings/business/policies",
        "/api/v1/alerts",
        "/api/v1/alerts/{alert_id}",
        "/api/v1/alerts/bulk",
    }

    assert expected_paths.issubset(paths.keys())


def test_purchase_plan_openapi_schema_exposes_summary_and_wait_data_fields() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    purchase_page = schema["components"]["schemas"]["PurchasePlanPage"]["properties"]
    purchase_row = schema["components"]["schemas"]["PurchasePlanRow"]["properties"]
    purchase_summary = schema["components"]["schemas"]["PurchasePlanSummary"]["properties"]

    assert "summary" in purchase_page
    assert "missing_data" in purchase_row
    assert "missing_fields" in purchase_row
    assert "wait_data_reasons" in purchase_row
    assert "cost_source" in purchase_row
    assert "cost_truth" in purchase_row
    assert "cost_truth_level" in purchase_row
    assert "total_positions" in purchase_summary
    assert "total_items" in purchase_summary
    assert "total_required_cash" in purchase_summary
    assert "total_expected_profit" in purchase_summary


def test_price_safety_openapi_schema_exposes_wb_promotion_details() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    price_row = schema["components"]["schemas"]["PriceSafetyRow"]["properties"]
    promotion = schema["components"]["schemas"]["PriceSafetyPromotion"]["properties"]

    assert "promotion_details" in price_row
    assert "promotion_plan_state" in price_row
    assert "promotion_plan_safe_gap" in price_row
    assert "promotion_plan_target_gap" in price_row
    assert "price" in promotion
    assert "plan_price" in promotion
    assert "discount" in promotion
    assert "plan_discount" in promotion
    assert "participation_percentage" in promotion


def test_purchase_plan_route_serializes_summary_and_alias_fields(monkeypatch) -> None:
    async def _fake_purchase_plan(session, **kwargs):
        return PurchasePlanPage(
            total=1,
            limit=100,
            offset=0,
            items=[
                PurchasePlanRow(
                    sku_id=1,
                    nm_id=1001,
                    vendor_code="SKU-1",
                    title="Sample SKU",
                    status="WAIT_DATA",
                    decision="WAIT_DATA",
                    trust_state="data_blocked",
                    sales_velocity_daily=0.0,
                    available_stock=0.0,
                    in_transit_qty=0.0,
                    days_of_stock=None,
                    lead_time_days=14,
                    safety_days=7,
                    recommended_qty=0,
                    required_cash=0.0,
                    expected_profit=None,
                    risk="finance_not_confirmed",
                    reason="Финансовые данные еще не подтверждены.",
                    main_reason="Финансовые данные еще не подтверждены.",
                    missing_data=["finance", "cost"],
                    missing_fields=["finance", "cost"],
                    wait_data_reasons=["finance", "cost"],
                    next_step="Сначала закройте блокирующие проблемы в данных.",
                    confidence="low",
                    decision_confidence="low",
                    cost_source="operator_trusted_manual",
                    cost_truth="operator_baseline",
                    cost_truth_level="operator_baseline",
                    financial_final=False,
                )
            ],
        )

    monkeypatch.setattr(control_tower_router.snapshot_service, "purchase_plan", _fake_purchase_plan)
    app.dependency_overrides[get_current_superuser] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/inventory/purchase-plan?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert "summary" in body
    assert body["summary"]["total_positions"] == 0
    assert body["summary"]["total_required_cash"] == 0.0
    assert body["items"][0]["missing_data"] == ["finance", "cost"]
    assert body["items"][0]["wait_data_reasons"] == ["finance", "cost"]
    assert body["items"][0]["cost_source"] == "operator_trusted_manual"
    assert body["items"][0]["cost_truth"] == "operator_baseline"


def test_price_safety_route_forwards_filter_params(monkeypatch) -> None:
    captured = {}

    async def _fake_price_safety(session, **kwargs):
        captured.update(kwargs)
        return PriceSafetyPage(total=0, limit=kwargs["limit"], offset=kwargs["offset"], items=[])

    monkeypatch.setattr(control_tower_router.snapshot_service, "price_safety", _fake_price_safety)
    app.dependency_overrides[get_current_superuser] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/pricing/safety"
                "?account_id=1&search=323108780&status=safe&sort_by=target_margin_gap"
                "&sort_dir=desc&limit=25&offset=50"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["account_id"] == 1
    assert captured["search"] == "323108780"
    assert captured["status"] == "safe"
    assert captured["sort_by"] == "target_margin_gap"
    assert captured["sort_dir"] == "desc"
    assert captured["limit"] == 25
    assert captured["offset"] == 50
