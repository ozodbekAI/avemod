from __future__ import annotations

import importlib
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core import http as http_module
from app.core.http import WBHTTPClient
from app.core.wb_connector_inventory import (
    WB_CONNECTOR_INVENTORY,
    active_inventory,
    inventory_as_markdown,
    inventory_by_connector_id,
)
from app.models.accounts import WBAPICategory
from app.modules.finance.sync import FinanceSyncService
from app.schemas.finance import RealizationReportRowRead
from app.services.reputation import ReputationService
from app.services.sync import SyncOrchestrator


EXPECTED_WB_TOKEN_CATEGORIES = {
    "content",
    "prices",
    "statistics",
    "analytics",
    "finance",
    "promotion",
    "feedbacks_questions",
    "buyer_chat",
    "buyer_returns",
    "supplies",
    "documents",
    "tariffs",
    "users",
}


def test_wb_token_model_contains_current_official_categories() -> None:
    assert {category.value for category in WBAPICategory} >= EXPECTED_WB_TOKEN_CATEGORIES


def test_inventory_covers_current_backend_and_required_wb_domains() -> None:
    required_domains = {
        "product_cards",
        "prices",
        "orders",
        "sales",
        "stocks",
        "finance",
        "analytics",
        "ads",
        "tariffs",
        "documents",
        "supplies",
        "reputation",
        "buyer_chat",
        "buyer_returns",
        "users",
    }
    assert {entry.domain for entry in WB_CONNECTOR_INVENTORY} >= required_domains

    for entry in WB_CONNECTOR_INVENTORY:
        assert entry.connector_id
        assert entry.endpoint_url.startswith("https://")
        assert entry.token_category in EXPECTED_WB_TOKEN_CATEGORIES
        assert entry.method
        assert entry.request_shape
        assert entry.pagination_cursor
        assert entry.date_range_limit
        assert entry.rate_limit
        assert entry.success_shape
        assert entry.no_data_shape
        assert entry.status in {"active", "not_implemented", "legacy_not_used"}
        assert entry.raw_response_storage


def test_inventory_markdown_report_has_required_columns_and_guardrails() -> None:
    report = inventory_as_markdown()

    assert "WB endpoint URL" in report
    assert "token category" in report
    assert "pagination/cursor" in report
    assert "raw storage" in report
    assert "feedbacks_questions" in report
    assert "legacy `/api/v5/supplier/reportDetailByPeriod` is marked `legacy_not_used`" in report


def test_active_inventory_matches_registered_sync_token_categories() -> None:
    expected = {
        "product_cards": WBAPICategory.CONTENT.value,
        "prices": WBAPICategory.PRICES.value,
        "orders": WBAPICategory.STATISTICS.value,
        "sales": WBAPICategory.STATISTICS.value,
        "stocks": WBAPICategory.ANALYTICS.value,
        "finance": WBAPICategory.FINANCE.value,
        "supplies": WBAPICategory.SUPPLIES.value,
        "ads": WBAPICategory.PROMOTION.value,
        "analytics": WBAPICategory.ANALYTICS.value,
        "tariffs": WBAPICategory.TARIFFS.value,
        "documents": WBAPICategory.DOCUMENTS.value,
    }

    orchestrator = SyncOrchestrator(session=object())  # type: ignore[arg-type]
    for domain, token_category in expected.items():
        service = orchestrator._get_service(domain)
        assert service.category == token_category
        assert any(
            entry.domain == domain and entry.token_category == token_category and entry.status == "active"
            for entry in WB_CONNECTOR_INVENTORY
        )


def test_inventory_client_methods_exist() -> None:
    for entry in active_inventory():
        assert entry.client_path, entry.connector_id
        assert entry.client_method, entry.connector_id
        module_name, class_name = entry.client_path.rsplit(".", 1)
        cls = getattr(importlib.import_module(module_name), class_name)
        assert hasattr(cls, entry.client_method), entry.connector_id


def test_feedback_chat_returns_use_separate_token_categories() -> None:
    inventory = inventory_by_connector_id()

    assert inventory["feedbacks_questions.reputation"].token_category == WBAPICategory.FEEDBACKS_QUESTIONS.value
    assert inventory["buyer_chat"].token_category == WBAPICategory.BUYER_CHAT.value
    assert inventory["buyer_returns"].token_category == WBAPICategory.BUYER_RETURNS.value
    assert inventory["users.access"].token_category == WBAPICategory.USERS.value

    app_root = Path(__file__).resolve().parents[2] / "app"
    reputation_source = (app_root / "services" / "reputation.py").read_text(encoding="utf-8")
    jobs_source = (app_root / "jobs" / "sync_jobs.py").read_text(encoding="utf-8")
    assert "WBAPICategory.FEEDBACKS_QUESTIONS.value" in reputation_source
    assert "WBAPICategory.FEEDBACKS_QUESTIONS.value" in jobs_source
    assert "WBAPICategory.CONTENT.value" not in reputation_source


def test_legacy_finance_report_detail_endpoint_is_not_called_by_production_code() -> None:
    app_root = Path(__file__).resolve().parents[2] / "app"
    legacy_pattern = "reportDetailByPeriod"
    matches: list[str] = []

    for path in app_root.rglob("*.py"):
        if path.name == "wb_connector_inventory.py":
            continue
        if legacy_pattern in path.read_text(encoding="utf-8"):
            matches.append(str(path.relative_to(app_root)))

    assert matches == []


@pytest.mark.parametrize("entry", active_inventory(), ids=lambda entry: entry.connector_id)
def test_each_active_connector_documents_rate_limit_and_backoff_contract(entry) -> None:
    assert entry.rate_limit
    assert WBHTTPClient._rate_limit_sleep_seconds(
        {"x-ratelimit-retry": "2.5"},
        attempt_count=1,
    ) == 2.5


@pytest.mark.parametrize("entry", active_inventory(), ids=lambda entry: entry.connector_id)
def test_each_active_connector_has_raw_snapshot_storage_contract(entry) -> None:
    assert "raw_wb_api_responses" in entry.db_target_tables
    assert entry.raw_response_storage in {
        "DomainSyncBase._request_json",
        "ReputationService._store_wb_raw_response",
    }


@pytest.mark.asyncio
async def test_reputation_raw_snapshot_uses_feedbacks_questions_category() -> None:
    service = ReputationService()
    service.raw_service = SimpleNamespace(store=AsyncMock())
    response = SimpleNamespace(
        text='{"data":{"feedbacks":[]}}',
        headers={"X-Ratelimit-Remaining": "5"},
        status_code=200,
    )

    await service._store_wb_raw_response(
        None,
        account_id=1,
        endpoint="/api/v1/feedbacks",
        http_method="GET",
        request_params={"isAnswered": "false", "take": 100, "skip": 0},
        response=response,
        response_json={"data": {"feedbacks": []}},
        requested_at=datetime(2026, 7, 3, 10, 0, tzinfo=timezone.utc),
        loaded_at=datetime(2026, 7, 3, 10, 0, 1, tzinfo=timezone.utc),
    )

    service.raw_service.store.assert_awaited_once()
    stored = service.raw_service.store.await_args.kwargs
    assert stored["api_category"] == WBAPICategory.FEEDBACKS_QUESTIONS.value
    assert stored["endpoint"] == "/api/v1/feedbacks"
    assert stored["response_headers"] == {"x-ratelimit-remaining": "5"}
    assert stored["is_success"] is True


@pytest.mark.asyncio
async def test_wb_http_client_preserves_204_no_data_payload_without_network(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 204
        text = ""
        headers = {"x-ratelimit-remaining": "1"}

        def json(self) -> object:
            raise AssertionError("204 no-content response must not be parsed as JSON")

    class FakeAsyncClient:
        def __init__(self, *, timeout: int) -> None:
            self.timeout = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def request(self, **kwargs) -> FakeResponse:
            requests.append(kwargs)
            return FakeResponse()

    async def no_spacing(cls, url: str) -> None:
        return None

    monkeypatch.setattr(http_module.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(WBHTTPClient, "_apply_pre_request_spacing", classmethod(no_spacing))

    response = await WBHTTPClient("token").request_json(
        "POST",
        "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed",
        json_body={"dateFrom": "2026-07-01", "dateTo": "2026-07-02", "rrdId": 0},
    )

    assert response.status_code == 204
    assert response.payload == {"noData": True}
    assert requests[0]["headers"] == {"Authorization": "token"}


def test_finance_raw_response_mapping_to_db_and_ui_fields() -> None:
    rows = FinanceSyncService._normalize_realization_rows(
        7,
        [
            {
                "reportId": 55,
                "rrdId": 123,
                "rrDate": "2026-07-01",
                "saleDt": "2026-07-01T10:20:30Z",
                "docTypeName": "Продажа",
                "orderId": 9001,
                "nmId": 987654321,
                "vendorCode": "SKU-1",
                "retailAmount": "1500.50",
                "forPay": "1200.00",
                "acquiringFee": "25.50",
            }
        ],
        report_fk_map={55: 5005},
    )

    assert rows == [
        {
            **rows[0],
            "account_id": 7,
            "report_id_fk": 5005,
            "rrd_id": 123,
            "report_id": 55,
            "doc_type_name": "Продажа",
            "operation_type": "sale",
            "is_sale_operation": True,
            "is_reconcilable": True,
            "order_id": 9001,
            "nm_id": 987654321,
            "vendor_code": "SKU-1",
            "retail_amount": "1500.50",
            "for_pay": "1200.00",
            "acquiring_fee": "25.50",
        }
    ]
    for ui_field in ("rrd_id", "report_id", "nm_id", "vendor_code", "retail_amount", "for_pay", "acquiring_fee"):
        assert ui_field in RealizationReportRowRead.model_fields
