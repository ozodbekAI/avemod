from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.modules.problem_rules import router as problem_rules_router
from app.services.auth import get_current_user


async def _override_session():
    yield None


class _FakeSession:
    async def commit(self):
        return None

    async def refresh(self, _row):
        return None


async def _override_fake_session():
    yield _FakeSession()


def _normal_user():
    return SimpleNamespace(id=2, is_superuser=False, is_active=True)


def _admin_user():
    return SimpleNamespace(id=3, is_superuser=False, is_active=True, role="admin")


def test_problem_rule_admin_routes_are_registered_in_openapi() -> None:
    with TestClient(app) as client:
        response = client.get("/openapi.json")

    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {
        "/api/v1/admin/problem-rules/metrics",
        "/api/v1/admin/problem-rules/actions/catalog",
        "/api/v1/admin/problem-rules/evaluate",
        "/api/v1/admin/problem-rules/summary",
        "/api/v1/admin/problem-rules/{id}/backtests",
        "/api/v1/admin/problem-rules/{id}/instances",
        "/api/v1/admin/problem-rules/definitions",
        "/api/v1/admin/problem-rules/definitions/{definition_id}",
        "/api/v1/admin/problem-rules/definitions/{definition_id}/instances",
        "/api/v1/admin/problem-rules/definitions/{definition_id}/versions/compare",
        "/api/v1/admin/problem-rules/definitions/{definition_id}/versions",
        "/api/v1/admin/problem-rules/versions/{version_id}",
        "/api/v1/admin/problem-rules/versions/{version_id}/validate",
        "/api/v1/admin/problem-rules/versions/{version_id}/backtest",
        "/api/v1/admin/problem-rules/versions/{version_id}/backtests",
        "/api/v1/admin/problem-rules/versions/{version_id}/publish",
        "/api/v1/admin/problem-rules/versions/{version_id}/pause",
        "/api/v1/admin/problem-rules/versions/{version_id}/archive",
        "/api/v1/admin/problem-rules/audit",
    }.issubset(paths.keys())


def test_problem_rule_admin_write_routes_require_superuser() -> None:
    app.dependency_overrides[get_current_user] = _normal_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            create_response = client.post(
                "/api/v1/admin/problem-rules/definitions",
                json={
                    "problem_code": "admin_only_test",
                    "source_module": "problem_engine",
                    "category": "stock",
                    "entity_type": "product",
                    "title_template": "Admin only",
                    "description_template": "Admin only",
                    "recommendation_template": "Admin only",
                    "impact_type_default": "system_warning",
                    "trust_state_default": "test_only",
                    "severity_default": "low",
                    "allowed_actions_json": ["recheck"],
                },
            )
            publish_response = client.post("/api/v1/admin/problem-rules/versions/1/publish", json={"override": True})
            update_version_response = client.patch("/api/v1/admin/problem-rules/versions/1", json={"lookback_days": 14})
            evaluate_response = client.post("/api/v1/admin/problem-rules/evaluate", json={"account_id": 1})
    finally:
        app.dependency_overrides.clear()

    assert create_response.status_code == 403
    assert publish_response.status_code == 403
    assert update_version_response.status_code == 403
    assert evaluate_response.status_code == 403


def test_problem_rule_admin_role_can_create_definition(monkeypatch) -> None:
    async def _fake_create_definition(session, payload, *, actor_user_id):
        assert actor_user_id == 3
        return SimpleNamespace(
            id=10,
            problem_code=payload.problem_code,
            source_module=payload.source_module,
            category=payload.category,
            entity_type=payload.entity_type,
            title_template=payload.title_template,
            description_template=payload.description_template,
            recommendation_template=payload.recommendation_template,
            impact_type_default=payload.impact_type_default,
            trust_state_default=payload.trust_state_default,
            severity_default=payload.severity_default,
            allowed_actions_json=payload.allowed_actions_json,
            status="draft",
            is_system_seeded=False,
            created_by_user_id=actor_user_id,
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    monkeypatch.setattr(problem_rules_router.service, "create_definition", _fake_create_definition)
    app.dependency_overrides[get_current_user] = _admin_user
    app.dependency_overrides[get_db_session] = _override_fake_session
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/admin/problem-rules/definitions",
                json={
                    "problem_code": "admin_role_test",
                    "source_module": "problem_engine",
                    "category": "stock",
                    "entity_type": "product",
                    "title_template": "Admin role",
                    "description_template": "Admin role",
                    "recommendation_template": "Admin role",
                    "impact_type_default": "system_warning",
                    "trust_state_default": "estimated",
                    "severity_default": "low",
                    "allowed_actions_json": ["recheck"],
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["created_by_user_id"] == 3
    assert response.json()["seller_visible"] is True
    assert response.json()["visibility_mode"] == "seller"
