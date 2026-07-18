from __future__ import annotations

from pathlib import Path

from app.modules.ab_tests.router import promotion_router


def test_promotion_compatibility_routes_exist_with_account_id_query():
    routes = {
        (method, route.path): route
        for route in promotion_router.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }

    for method, path in [
        ("GET", "/promotion/balance"),
        ("GET", "/promotion/{status}"),
        ("GET", "/promotion/company/{company_id}/stats"),
        ("POST", "/promotion/company/{company_id}/start"),
        ("POST", "/promotion/company/{company_id}/stop"),
    ]:
        route = routes[(method, path)]
        query_names = {param.name for param in route.dependant.query_params}
        assert "account_id" in query_names

    for method, path in [
        ("POST", "/promotion/create_company"),
        ("POST", "/promotion/update"),
    ]:
        route = routes[(method, path)]
        body_names = {param.name for param in route.dependant.body_params}
        assert "payload" in body_names


def test_promotion_write_routes_require_confirm_query_for_real_wb_start_stop():
    routes = {
        (method, route.path): route
        for route in promotion_router.routes
        if getattr(route, "methods", None)
        for method in route.methods
    }

    for method, path in [
        ("POST", "/promotion/company/{company_id}/start"),
        ("POST", "/promotion/company/{company_id}/stop"),
    ]:
        query_names = {param.name for param in routes[(method, path)].dependant.query_params}
        assert "confirm" in query_names


def test_ab_tests_ui_remains_in_beta_navigation():
    sidebar = Path("../frontend/src/components/AppSidebar.tsx").read_text(encoding="utf-8")
    assert "const betaNav" in sidebar
    assert '{ to: "/ab-tests", label: "A/B тесты", icon: FlaskConical, module: "experiments" }' in sidebar
    assert "VITE_ENABLE_BETA_MODULES" in sidebar
