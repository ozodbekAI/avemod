from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.schemas.portal import PortalStockOpsRunRequest
from app.services.stockops_adapter import StockOpsAdapter


@pytest.mark.asyncio
async def test_stockops_adapter_reports_not_configured_without_base_url() -> None:
    adapter = StockOpsAdapter(Settings())

    health_status, health_detail = await adapter.health()
    runs = await adapter.list_runs(account_id=1, run_type="return_excess", limit=50, offset=0)
    run = await adapter.run(PortalStockOpsRunRequest(run_type="return_excess", account_id=1))

    assert health_status == "not_configured"
    assert "stockops_base_url" in str(health_detail)
    assert runs.status == "not_configured"
    assert run.status == "not_configured"


@pytest.mark.asyncio
async def test_stockops_adapter_lists_existing_runs_from_safe_endpoint() -> None:
    adapter = StockOpsAdapter(Settings(stockops_base_url="http://stockops.internal"))
    adapter._request = AsyncMock(
        return_value={
            "runs": [
                {
                    "id": 11,
                    "business_mode": "return_excess",
                    "status": "ok",
                    "account_id": 1,
                    "summary": {"items_total": 4},
                    "wb_api_token": "secret-token",
                }
            ]
        }
    )

    page = await adapter.list_runs(account_id=1, run_type="return_excess", limit=50, offset=0)

    assert page.status == "ok"
    assert page.total == 1
    assert page.items[0].run_id == 11
    assert page.items[0].account_id == 1
    assert page.items[0].run_type == "return_excess"
    assert page.items[0].status == "completed"
    assert page.items[0].export_url is None
    assert "wb_api_token" not in page.items[0].raw
    adapter._request.assert_awaited_once()
    assert adapter._request.await_args.kwargs["params"]["account_id"] == 1


@pytest.mark.asyncio
async def test_stockops_adapter_run_is_non_destructive_placeholder_when_configured() -> None:
    adapter = StockOpsAdapter(Settings(stockops_base_url="http://stockops.internal"))
    adapter.health = AsyncMock(return_value=("ok", None))

    run = await adapter.run(
        PortalStockOpsRunRequest(
            run_type="ship_from_hand",
            account_id=1,
            payload={"draft_id": 123, "token": "must-not-leak"},
        )
    )

    assert run.status == "not_started"
    assert run.run_type == "ship_from_hand"
    assert run.account_id == 1
    assert "automatic run start is disabled" in str(run.message)
    assert run.raw["requested_payload_keys"] == ["draft_id"]


@pytest.mark.asyncio
async def test_stockops_adapter_builds_read_only_action_candidates_from_run_sheets() -> None:
    adapter = StockOpsAdapter(Settings(stockops_base_url="http://stockops.internal"))

    async def _fake_request(method, path, **kwargs):
        if path == "/api/runs":
            return {
                "runs": [
                    {
                        "id": 2,
                        "business_mode": "ship_from_hand",
                        "status": "completed",
                        "account_id": 1,
                        "summary": {"allocation_rows": 1},
                    },
                    {
                        "id": 1,
                        "business_mode": "return_excess",
                        "status": "completed",
                        "account_id": 1,
                        "summary": {"rows_excess": 1},
                    },
                ]
            }
        if path == "/api/runs/1/sheets/pickup":
            return {
                "sheet": {
                    "rows": [
                        {
                            "seller_article": "VC-1",
                            "wb_article": 1001,
                            "warehouse_name": "Tula",
                            "warehouse_stock": 8,
                            "to_pick": 3,
                            "wb_api_token": "secret",
                        }
                    ]
                }
            }
        if path == "/api/runs/2/sheets/plan":
            return {
                "sheet": {
                    "rows": [
                        {
                            "seller_article": "VC-1",
                            "wb_article": 1001,
                            "recipient_region": "Northwest",
                            "recipient_warehouse": "SPB",
                            "planned_ship_qty": 5,
                        }
                    ]
                }
            }
        return {"sheet": {"rows": []}}

    adapter._request = AsyncMock(side_effect=_fake_request)

    account = type("Account", (), {"id": 1})()
    actions, unavailable = await adapter.stock_redistribution_action_candidates(account, nm_id=1001, limit=10)
    insights = await adapter.product_stock_insights(account, nm_id=1001, limit=10)

    assert unavailable is None
    assert {item.action_type for item in actions} == {"stock_excess", "regional_redistribution"}
    assert all(item.source_module == "stockops" for item in actions)
    assert all(item.can_update_status is False for item in actions)
    assert all(item.payload["marketplace_change"] is False for item in actions)
    assert "wb_api_token" not in str(insights.model_dump(mode="json"))
    assert insights.status == "ok"
    assert insights.summary["flow_matrix"]["return_excess"]["write_status"] == "disabled"


@pytest.mark.asyncio
async def test_stockops_adapter_candidates_degrade_without_configuration() -> None:
    adapter = StockOpsAdapter(Settings())
    account = type("Account", (), {"id": 1})()

    actions, unavailable = await adapter.stock_redistribution_action_candidates(account, limit=10)
    insights = await adapter.product_stock_insights(account, nm_id=1001, limit=10)

    assert actions == []
    assert unavailable is None
    assert insights.status == "not_configured"
