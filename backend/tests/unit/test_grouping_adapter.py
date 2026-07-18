from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.grouping_adapter import GroupingAdapter


def _account(account_id: int = 1):
    return SimpleNamespace(id=account_id, external_account_id=None, name="Test")


@pytest.mark.asyncio
async def test_grouping_adapter_is_disabled_by_default() -> None:
    adapter = GroupingAdapter(Settings())

    health_status, health_detail = await adapter.health(_account())
    grouping = await adapter.product_grouping(_account(), nm_id=1001)

    assert adapter.is_configured is False
    assert health_status == "disabled"
    assert "disabled" in str(health_detail)
    assert grouping.status == "disabled"


@pytest.mark.asyncio
async def test_grouping_adapter_requires_test_account_flag() -> None:
    adapter = GroupingAdapter(
        Settings(
            grouping_enabled=True,
            grouping_base_url="http://grouping.internal",
            grouping_test_account_ids=[7],
        )
    )

    health_status, health_detail = await adapter.health(_account(1))

    assert health_status == "not_configured"
    assert "test accounts" in str(health_detail)


@pytest.mark.asyncio
async def test_grouping_adapter_reports_beta_health_for_allowed_account() -> None:
    adapter = GroupingAdapter(
        Settings(
            grouping_enabled=True,
            grouping_base_url="http://grouping.internal",
            grouping_test_account_ids=[1],
        )
    )
    adapter._request = AsyncMock(return_value={"status": "ok"})

    health_status, health_detail = await adapter.health(_account())

    assert health_status == "beta"
    assert "Beta" in str(health_detail)
    adapter._request.assert_awaited_once_with("GET", "/api/health", auth=False)


@pytest.mark.asyncio
async def test_grouping_adapter_maps_product_recommendations_without_merge() -> None:
    adapter = GroupingAdapter(
        Settings(
            grouping_enabled=True,
            grouping_base_url="http://grouping.internal",
            grouping_test_account_ids=[1],
            grouping_internal_token="secret",
        )
    )
    adapter._request = AsyncMock(
        return_value={
            "total": 1,
            "items": [
                {
                    "source": {"nmid": 1001, "article": "A-1", "brand": "Brand"},
                    "targets": [{"nmid": 2002, "article": "B-1", "color": "black"}],
                    "recommendation_count": 1,
                    "updated_at": "2026-06-09T00:00:00Z",
                    "wb_api_key": "must-not-leak",
                }
            ],
        }
    )

    grouping = await adapter.product_grouping(_account(), nm_id=1001)
    actions, unavailable = await adapter.recommendation_actions(_account(), limit=10)

    assert grouping.status == "beta"
    assert grouping.recommendation_count == 1
    assert grouping.beta_notice == "Beta / recommendation only. WB merge/apply is disabled."
    assert grouping.auto_merge_enabled is False
    assert grouping.recommendations[0]["candidate_group_id"] == "1001"
    assert grouping.recommendations[0]["nm_ids"] == [1001, 2002]
    assert grouping.recommendations[0]["risk_level"] == "low"
    assert grouping.recommendations[0]["risk_reasons"] == []
    assert grouping.recommendations[0]["preview_payload_available"] is True
    assert grouping.recommendations[0]["auto_merge_enabled"] is False
    assert "wb_api_key" not in grouping.raw
    assert unavailable is None
    assert actions[0].source_module == "grouping"
    assert actions[0].can_update_status is True
    assert actions[0].priority == "P4"
    assert actions[0].severity == "low"
    assert actions[0].payload["auto_merge_enabled"] is False


@pytest.mark.asyncio
async def test_grouping_preview_uses_dry_run_only() -> None:
    adapter = GroupingAdapter(
        Settings(
            grouping_enabled=True,
            grouping_base_url="http://grouping.internal",
            grouping_test_account_ids=[1],
        )
    )
    adapter._request = AsyncMock(return_value={"dry_run": True, "inserted_pairs": 12})
    adapter.product_grouping = AsyncMock(
        return_value=SimpleNamespace(recommendations=[{"nm_id": 2002, "article": "B-1"}])
    )

    preview = await adapter.preview(
        _account(),
        nm_id=1001,
        preset_key="balanced",
        recommendation_scenario_id=None,
        custom_config={"limit": 5},
    )

    assert preview.status == "beta"
    assert preview.summary["dry_run"] is True
    assert preview.auto_merge_enabled is False
    assert preview.recommendations[0]["nm_id"] == 2002
    adapter._request.assert_awaited_once()
    _, _, kwargs = adapter._request.mock_calls[0]
    assert kwargs["params"]["dry_run"] == "true"
    assert kwargs["params"]["replace_existing"] == "false"


@pytest.mark.asyncio
async def test_grouping_adapter_filters_high_risk_actions_unless_review_needed() -> None:
    adapter = GroupingAdapter(
        Settings(
            grouping_enabled=True,
            grouping_base_url="http://grouping.internal",
            grouping_test_account_ids=[1],
        )
    )
    adapter._request = AsyncMock(
        return_value={
            "total": 2,
            "items": [
                {
                    "candidate_group_id": "unsafe",
                    "source": {"nmid": 1001, "subject": "Dresses"},
                    "targets": [{"nmid": 2002, "subject": "Shoes"}],
                    "risk_level": "high",
                    "risk_reasons": ["subject mismatch"],
                },
                {
                    "candidate_group_id": "needs-review",
                    "source": {"nmid": 1003, "subject": "Dresses"},
                    "targets": [{"nmid": 2004, "subject": "Shoes"}],
                    "risk_level": "high",
                    "risk_reasons": ["subject mismatch"],
                    "review_needed": True,
                },
            ],
        }
    )

    actions, unavailable = await adapter.recommendation_actions(_account(), limit=10)

    assert unavailable is None
    assert [action.source_id for action in actions] == ["needs-review"]
    assert actions[0].severity == "high"
    assert actions[0].payload["risk_level"] == "high"
    assert actions[0].payload["review_needed"] is True
    assert actions[0].payload["auto_merge_enabled"] is False
