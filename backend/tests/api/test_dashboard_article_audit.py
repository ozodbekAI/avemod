from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.modules.dashboard import router as dashboard_router
from app.services.auth import get_current_superuser


async def _override_session():
    yield None


def _override_user():
    return SimpleNamespace(id=1)


def test_dashboard_article_audit_returns_trust_fields(monkeypatch) -> None:
    async def _fake_article_audit(session, **kwargs):
        return {
            "operational_trusted": True,
            "business_trusted": True,
            "financial_final": False,
            "trust_state": "operational_provisional",
            "cost_trust_policy": "operator_baseline",
            "supplier_confirmed_revenue_coverage_percent": 0.0,
            "operator_baseline_revenue_coverage_percent": 99.6,
            "trusted_revenue_cost_coverage_percent": 99.6,
            "financial_final_blockers_total": 2,
            "final_profit_blockers_total": 2,
            "identity": {
                "nm_id": 223205606,
                "vendor_code": "SKU-1",
                "barcode": None,
                "title": "Article",
                "brand": None,
                "subject_name": None,
            },
            "completeness": {
                "has_product_card": True,
                "has_price": True,
                "has_orders": True,
                "has_sales": True,
                "has_stock": True,
                "has_finance": True,
                "has_ads": True,
                "has_funnel": True,
                "has_manual_cost": True,
            },
            "price": None,
            "operations": {
                "orders_count": 1,
                "cancelled_orders_count": 0,
                "orders_gross_amount": 100.0,
                "orders_finished_amount": 100.0,
                "sales_count": 1,
                "returns_count": 0,
                "sales_gross_amount": 100.0,
                "sales_for_pay": 90.0,
                "first_event_at": None,
                "last_event_at": None,
            },
            "finance": {
                "report_rows_count": 1,
                "gross_units": 1,
                "return_units": 0,
                "net_units": 1,
                "realized_revenue": 100.0,
                "for_pay": 90.0,
                "commission": 5.0,
                "acquiring_fee": 1.0,
                "logistics": 1.0,
                "paid_acceptance": 0.0,
                "storage": 0.0,
                "penalties": 0.0,
                "deductions": 0.0,
                "additional_payments": 0.0,
                "estimated_cogs": 40.0,
                "estimated_profit_before_ads": 42.0,
                "first_report_date": None,
                "last_report_date": None,
            },
            "ads": {
                "stats_rows_count": 1,
                "spend": 10.0,
                "raw_allocated_spend": 10.0,
                "capped_allocated_spend": 10.0,
                "overallocated_spend": 0.0,
                "unallocated_spend": 0.0,
                "allocation_status": "matched",
                "final_profit_allowed": True,
                "views": 10,
                "clicks": 1,
                "orders": 0,
                "atbs": 0,
            },
            "funnel": {
                "days_count": 1,
                "open_count": 10,
                "cart_count": 2,
                "order_count": 1,
                "buyout_count": 1,
                "cancel_count": 0,
            },
            "stock": {
                "snapshot_at": None,
                "rows_count": 1,
                "quantity": 5.0,
                "quantity_full": 5.0,
                "in_way_to_client": 0.0,
                "in_way_from_client": 0.0,
                "warehouses": [],
            },
            "manual_cost": None,
            "daily_economics": None,
            "daily_series": [],
            "reconciliation": {
                "pending_count": 0,
                "warning_count": 1,
                "error_count": 0,
                "ignored_count": 0,
                "mart_matches_article": True,
                "mart_matches_finance": True,
                "finance_matches_operational": False,
                "revenue_matches_mart": True,
                "mart_revenue_total": 100.0,
                "article_revenue_total": 100.0,
                "finance_report_revenue_total": 100.0,
                "difference_amount": 0.0,
                "difference_ratio": 0.0,
                "difference_ratio_percent": 0.0,
                "mismatch_reason": None,
            },
            "issues_total": 0,
            "issues_limit": 50,
            "issues_offset": 0,
            "issues": [],
            "notes": [],
        }

    monkeypatch.setattr(dashboard_router.snapshot_service, "article_audit", _fake_article_audit)
    app.dependency_overrides[get_current_superuser] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/dashboard/article-audit?account_id=1&nm_id=223205606")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["operational_trusted"] is True
    assert body["financial_final"] is False
    assert body["trust_state"] == "operational_provisional"
