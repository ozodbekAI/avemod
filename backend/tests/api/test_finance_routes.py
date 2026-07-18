from __future__ import annotations

from app.main import app


def test_wb_finance_fact_routes_are_read_only() -> None:
    finance_fact_paths = {
        "/api/v1/finance/reports",
        "/api/v1/finance/report-rows",
        "/api/v1/balance",
    }

    routes = {
        getattr(route, "path", ""): set(getattr(route, "methods", set()) or set())
        for route in app.routes
        if getattr(route, "path", "") in finance_fact_paths
    }

    assert set(routes) == finance_fact_paths
    assert all(methods <= {"GET"} for methods in routes.values())
