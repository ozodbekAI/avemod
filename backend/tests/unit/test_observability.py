from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.observability import record_unavailable_source, request_timing_middleware, scrub_log_fields


def test_scrub_log_fields_removes_secret_like_keys_recursively() -> None:
    payload = {
        "endpoint_path": "/api/v1/portal/overview",
        "account_id": 1,
        "authorization": "Bearer must-not-leak",
        "nested": {
            "password": "must-not-leak",
            "ok": "visible",
            "items": [{"refresh_token": "must-not-leak", "source": "checker"}],
        },
    }

    scrubbed = scrub_log_fields(payload)

    dumped = json.dumps(scrubbed)
    assert "must-not-leak" not in dumped
    assert scrubbed == {
        "endpoint_path": "/api/v1/portal/overview",
        "account_id": 1,
        "nested": {"ok": "visible", "items": [{"source": "checker"}]},
    }


def test_request_timing_log_has_safe_structured_fields(caplog) -> None:
    app = FastAPI()
    app.middleware("http")(request_timing_middleware)

    @app.get("/probe/{account_id}")
    async def probe(account_id: int):
        record_unavailable_source("checker")
        return {"account_id": account_id, "status": "ok"}

    with caplog.at_level(logging.INFO, logger="app.observability"):
        response = TestClient(app).get("/probe/42?token=must-not-leak&password=must-not-leak")

    assert response.status_code == 200
    messages = [record.getMessage() for record in caplog.records if "http_request" in record.getMessage()]
    assert messages
    payload = json.loads(messages[-1])
    assert payload["endpoint_path"] == "/probe/{account_id}"
    assert payload["method"] == "GET"
    assert payload["status_code"] == 200
    assert payload["account_id"] == 42
    assert payload["unavailable_sources_count"] == 1
    assert payload["unavailable_sources"] == ["checker"]
    assert payload["duration_ms"] >= 0
    assert "must-not-leak" not in messages[-1]
