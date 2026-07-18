from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.config import Settings
from app.services.checker_adapter import CheckerAdapter
from app.services.module_registry import ModuleRegistryService


@pytest.mark.asyncio
async def test_checker_adapter_maps_card_quality_read_only_payload() -> None:
    adapter = CheckerAdapter(
        Settings(
            checker_base_url="http://checker.internal",
            checker_store_map={"1": 5},
            checker_internal_token="secret",
        )
    )
    adapter._request = AsyncMock(
        side_effect=[
            {
                "items": [
                    {
                        "id": 10,
                        "store_id": 5,
                        "nm_id": 1001,
                        "score": 70,
                        "critical_issues_count": 1,
                        "warnings_count": 1,
                    }
                ]
            },
            {
                "id": 10,
                "store_id": 5,
                "nm_id": 1001,
                "score": 70,
                "score_breakdown": {"title_score": 5, "total_score": 70},
                "critical_issues_count": 1,
                "warnings_count": 1,
            },
            [
                {
                    "id": 77,
                    "code": "title_short",
                    "severity": "critical",
                    "category": "title",
                    "title": "Название короткое",
                    "description": "Снижает кликабельность карточки",
                    "field_path": "title",
                    "suggested_value": "Новое название",
                    "score_impact": 20,
                    "status": "pending",
                },
                {
                    "id": 78,
                    "code": "no_video",
                    "severity": "warning",
                    "category": "video",
                    "title": "Нет видео",
                    "score_impact": 5,
                    "status": "pending",
                },
            ],
        ]
    )

    quality = await adapter.product_quality(SimpleNamespace(id=1, external_account_id=None, name="A"), nm_id=1001)

    assert quality.status == "ok"
    assert quality.module == "checker"
    assert quality.source == "checker"
    assert quality.severity == "critical"
    assert quality.store_id == 5
    assert quality.card_id == 10
    assert quality.score == 70
    assert quality.critical_issue_count == 1
    assert quality.issues_by_category == {"title": 1, "video": 1}
    assert quality.title_issues[0]["code"] == "title_short"
    assert quality.title_issues[0]["type"] == "title"
    assert quality.title_issues[0]["recommendation"] == "Новое название"
    assert quality.photo_video_issues[0]["code"] == "no_video"
    assert "Новое название" in quality.recommendations


def test_checker_adapter_resolves_store_from_config_or_external_account_id() -> None:
    adapter = CheckerAdapter(Settings(checker_base_url="http://checker.internal", checker_store_map={"1": 5}))

    assert adapter.resolve_store_id(SimpleNamespace(id=1, external_account_id=None, name="A")) == 5
    assert adapter.resolve_store_id(SimpleNamespace(id=2, external_account_id="8", name="B")) == 8


@pytest.mark.asyncio
async def test_checker_adapter_builds_actions_from_grouped_issue_read_endpoint() -> None:
    adapter = CheckerAdapter(Settings(checker_base_url="http://checker.internal", checker_store_map={"1": 5}))
    adapter._request = AsyncMock(
        return_value={
            "critical": [
                {
                    "id": 77,
                    "card_id": 10,
                    "card_nm_id": 1001,
                    "card_title": "Article",
                    "code": "title_short",
                    "severity": "critical",
                    "category": "title",
                    "title": "Название короткое",
                    "description": "Снижает кликабельность карточки",
                    "score_impact": 20,
                    "status": "pending",
                }
            ],
            "warnings": [],
            "media": [
                {
                    "id": 78,
                    "card_id": 10,
                    "card_nm_id": 1001,
                    "card_title": "Article",
                    "code": "few_photos",
                    "severity": "warning",
                    "category": "photos",
                    "title": "Мало фото",
                    "description": "Добавьте фото товара",
                    "score_impact": 8,
                    "status": "pending",
                }
            ],
            "postponed": [],
        }
    )

    actions, unavailable = await adapter.quality_actions(SimpleNamespace(id=1, external_account_id=None, name="A"))

    assert unavailable is None
    assert actions[0].source_module == "checker"
    assert actions[0].nm_id == 1001
    assert actions[0].priority == "P2"
    assert actions[0].action_type == "CARD_QUALITY_FIX"
    assert actions[1].action_type == "photo_fix"
    assert actions[1].guided_fix["type"] == "photo_fix"
    assert actions[1].guided_fix["label"] == "Fix photo"
    assert actions[1].guided_fix["target_module"] == "photo_studio"
    assert actions[1].guided_fix["route_hint"] == "photo_studio"
    assert actions[1].guided_fix["nm_id"] == 1001
    assert actions[1].guided_fix["source_issue_id"] == "78"
    assert actions[1].guided_fix["marketplace_change"] is False
    assert actions[1].payload["guided_fix"]["target_module"] == "photo_studio"


def test_checker_adapter_reports_not_configured_without_base_url() -> None:
    adapter = CheckerAdapter(Settings())

    assert adapter.is_configured is False


def test_checker_settings_accept_requested_env_aliases() -> None:
    settings = Settings(
        checker_base_url="http://checker.internal",
        checker_service_token="service-token",
        checker_account_store_mapping={"1": 5},
        checker_timeout_seconds=1.25,
    )

    assert settings.checker_internal_token == "service-token"
    assert settings.checker_store_map == {"1": 5}
    assert settings.checker_http_timeout_seconds == 1.25


@pytest.mark.asyncio
async def test_checker_module_health_reports_missing_account_mapping_as_not_configured() -> None:
    registry = ModuleRegistryService(settings=Settings(checker_base_url="http://checker.internal"))

    health = await registry._checker_health(SimpleNamespace(id=1, external_account_id=None, name="A"))

    assert health.status == "not_configured"
    assert health.message == "checker service is configured, but this account has no checker store mapping"
    assert "CHECKER_ACCOUNT_STORE_MAPPING" in health.required_env_keys
