from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_endpoint_with_scheduler_enabled_startup() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
