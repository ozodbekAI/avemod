from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.services.module_registry import ModuleRegistryService

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.asyncio
async def test_module_registry_default_optional_modules_are_safe() -> None:
    registry = ModuleRegistryService(settings=Settings())

    health = await registry.health(account=None)
    payload = health.model_dump(mode="json")

    assert payload["finance"]["status"] == "ok"
    assert payload["finance"]["enabled"] is True
    assert payload["finance"]["configured"] is True
    assert payload["finance"]["visible"] is True
    assert payload["finance"]["navigation_group"] == "core"
    assert payload["finance"]["runtime_status"] == "enabled_safe"
    assert payload["expenses"]["status"] == "ok"
    assert payload["expenses"]["enabled"] is True
    assert payload["expenses"]["configured"] is True
    assert payload["expenses"]["visible"] is True
    assert payload["expenses"]["navigation_group"] == "core"
    assert payload["expenses"]["runtime_status"] == "enabled_safe"
    assert payload["doctor"]["status"] == "disabled"
    assert payload["doctor"]["enabled"] is False
    assert payload["doctor"]["visible"] is False
    assert payload["doctor"]["navigation_group"] == "hidden"
    assert payload["actions"]["visible"] is True
    assert payload["products"]["visible"] is True
    assert payload["checker"]["status"] == "not_configured"
    assert payload["checker"]["visible"] is True
    assert payload["checker"]["required_env_keys"] == ["CHECKER_BASE_URL"]
    assert payload["checker"]["marketplace_write_policy"]["requires_explicit_confirm"] is True
    assert payload["stockops"]["status"] == "not_configured"
    assert payload["stockops"]["visible"] is True
    assert payload["stockops"]["beta"] is True
    assert payload["stockops"]["navigation_group"] == "beta"
    assert payload["stockops"]["runtime_status"] == "not_configured"
    assert payload["grouping"]["status"] == "disabled"
    assert payload["grouping"]["visible"] is False
    assert payload["grouping"]["navigation_group"] == "hidden"
    assert payload["grouping"]["runtime_status"] == "disabled"
    assert payload["reputation"]["status"] == "disabled"
    assert payload["reputation"]["visible"] is False
    assert payload["reputation"]["required_env_keys"] == ["REPUTATION_ENABLED"]
    assert payload["reputation"]["runtime_status"] == "disabled"
    assert payload["claims"]["status"] == "disabled"
    assert payload["claims"]["visible"] is False
    assert payload["claims"]["runtime_status"] == "disabled"
    assert payload["photo"]["status"] == "disabled"
    assert payload["photo"]["visible"] is False
    assert payload["photo"]["runtime_status"] == "disabled"
    assert payload["experiments"]["status"] == "ok"
    assert payload["experiments"]["visible"] is True
    assert payload["experiments"]["beta"] is True
    assert payload["experiments"]["navigation_group"] == "beta"
    assert payload["experiments"]["runtime_status"] == "beta_draft_only"
    assert payload["results"]["visible"] is True
    dumped = str(payload).lower()
    assert "bearer" not in dumped
    assert "encrypted" not in dumped
    assert "secret" not in dumped


@pytest.mark.asyncio
async def test_module_registry_legacy_diagnostics_visible_only_when_enabled() -> None:
    registry = ModuleRegistryService(settings=Settings(enable_legacy_diagnostics=True))

    health = await registry.health(account=None)
    payload = health.model_dump(mode="json")

    assert payload["doctor"]["status"] == "ok"
    assert payload["doctor"]["enabled"] is True
    assert payload["doctor"]["visible"] is True


@pytest.mark.asyncio
async def test_module_registry_reports_not_configured_for_configured_checker_without_account_mapping() -> None:
    registry = ModuleRegistryService(settings=Settings(checker_base_url="http://checker.internal"))
    account = SimpleNamespace(id=1, external_account_id=None, name="main")

    health = await registry.health(account=account)

    assert health.checker.status == "not_configured"
    assert health.checker.enabled is True
    assert health.checker.configured is False
    assert health.checker.visible is True
    assert health.checker.navigation_group == "operator"
    assert "checker_account_store_mapping" in " ".join(health.checker.warnings)
    assert "CHECKER_ACCOUNT_STORE_MAPPING" in health.checker.required_env_keys
    assert "checker.internal" not in str(health.checker.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_module_registry_reports_degraded_for_grouping_account_not_enabled_for_beta() -> None:
    registry = ModuleRegistryService(
        settings=Settings(
            grouping_enabled=True,
            grouping_base_url="http://grouping.internal",
            grouping_test_account_ids=[2],
        )
    )
    account = SimpleNamespace(id=1, external_account_id=None, name="main")

    health = await registry.health(account=account)

    assert health.grouping.status == "degraded"
    assert health.grouping.enabled is True
    assert health.grouping.configured is True
    assert health.grouping.visible is False
    assert health.grouping.beta is True
    assert health.grouping.navigation_group == "hidden"
    assert health.grouping.required_env_keys == ["GROUPING_TEST_ACCOUNT_IDS"]
    assert "grouping_test_account_ids" in str(health.grouping.message)


@pytest.mark.asyncio
async def test_module_registry_reports_config_only_modules_as_degraded_when_enabled_with_base_url() -> None:
    class _FakeReputation:
        def resolve_shop_id(self, account):
            return None

        async def health(self, account=None):
            return "ok", "reputation service is available"

    registry = ModuleRegistryService(
        settings=Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            claims_enabled=True,
            claims_base_url="http://claims.internal",
            photo_enabled=True,
            photo_base_url="http://photo.internal",
        ),
        reputation=_FakeReputation(),
    )

    health = await registry.health(account=None)

    assert health.reputation.status == "ok"
    assert health.claims.status == "degraded"
    assert health.photo.status == "degraded"
    assert health.reputation.enabled is True
    assert health.reputation.configured is True
    assert health.reputation.visible is True
    assert health.reputation.beta is True
    assert health.reputation.navigation_group == "beta"
    assert health.reputation.runtime_status == "beta_draft_only"
    assert health.reputation.marketplace_write_policy["required_token_categories"] == [
        "feedbacks_questions",
        "buyer_chat",
    ]
    assert health.reputation.warnings == []
    assert health.claims.runtime_status == "beta_draft_only"
    assert health.claims.navigation_group == "beta"
    assert health.photo.runtime_status == "beta_draft_only"
    assert health.photo.navigation_group == "beta"
    dumped = str(health.model_dump(mode="json"))
    assert "reputation.internal" not in dumped
    assert "claims.internal" not in dumped
    assert "photo.internal" not in dumped


@pytest.mark.asyncio
async def test_module_registry_reports_degraded_for_reputation_without_account_mapping() -> None:
    registry = ModuleRegistryService(
        settings=Settings(
            reputation_enabled=True,
            reputation_base_url="http://reputation.internal",
            reputation_shop_map={"2": 20},
        )
    )
    account = SimpleNamespace(id=1, external_account_id=None, name="main")

    health = await registry.health(account=account)

    assert health.reputation.status == "degraded"
    assert health.reputation.enabled is True
    assert health.reputation.configured is True
    assert health.reputation.visible is True
    assert health.reputation.required_env_keys == ["REPUTATION_SHOP_MAP"]
    assert "reputation_shop_map" in " ".join(health.reputation.warnings)
    assert "reputation.internal" not in str(health.reputation.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_module_registry_production_like_settings_do_not_leak_secret_values() -> None:
    class _FakeChecker:
        async def health(self, account=None):
            return "ok", "checker service is available"

        def resolve_store_id(self, account):
            return 10

    class _FakeReputation:
        async def health(self, account=None):
            return "ok", "reputation service is available"

        def resolve_shop_id(self, account):
            return 20

    registry = ModuleRegistryService(
        settings=Settings(
            checker_base_url="https://checker.internal/secret-path",
            checker_internal_token="checker-secret-value",
            reputation_enabled=True,
            reputation_base_url="https://reputation.internal",
            reputation_internal_token="reputation-secret-value",
            claims_enabled=True,
            claims_base_url="https://claims.internal",
            claims_internal_token="claims-secret-value",
        ),
        checker=_FakeChecker(),
        reputation=_FakeReputation(),
    )

    health = await registry.health(account=None)
    dumped = str(health.model_dump(mode="json"))

    assert "checker-secret-value" not in dumped
    assert "reputation-secret-value" not in dumped
    assert "claims-secret-value" not in dumped
    assert "https://checker.internal" not in dumped
    assert "https://reputation.internal" not in dumped
    assert "https://claims.internal" not in dumped
    assert all(
        isinstance(key, str) and "=" not in key
        for item in health.model_dump(mode="json").values()
        for key in item["required_env_keys"]
    )


@pytest.mark.asyncio
async def test_module_registry_uses_db_state_before_env_fallback(monkeypatch) -> None:
    registry = ModuleRegistryService(settings=Settings())
    account = SimpleNamespace(id=1, external_account_id=None, name="main")
    integration = SimpleNamespace(
        module="checker",
        enabled=True,
        mode="local",
        status="empty",
        configuration_encrypted_json="encrypted-secret-not-returned",
        last_error_code=None,
        last_error_message=None,
    )

    async def fake_db_states(*, session, account):
        return {"checker": registry._db_integration_item(integration, module="checker")}

    monkeypatch.setattr(registry, "_db_integration_states", fake_db_states)

    health = await registry.health(account=account, session=object())
    payload = health.model_dump(mode="json")

    assert payload["checker"]["status"] == "empty"
    assert payload["checker"]["enabled"] is True
    assert payload["checker"]["configured"] is True
    assert payload["checker"]["visible"] is True
    assert "encrypted-secret-not-returned" not in str(payload)
    assert "CHECKER_BASE_URL" not in payload["checker"]["required_env_keys"]


@pytest.mark.asyncio
async def test_module_registry_db_error_message_redacts_secret_like_values(monkeypatch) -> None:
    registry = ModuleRegistryService(settings=Settings())
    account = SimpleNamespace(id=1, external_account_id=None, name="main")
    integration = SimpleNamespace(
        module="checker",
        enabled=True,
        mode="local",
        status="unavailable",
        configuration_encrypted_json=None,
        last_error_code="upstream_auth_failed",
        last_error_message="WB failed Authorization: Bearer must-not-leak password=must-not-leak",
    )

    async def fake_db_states(*, session, account):
        return {"checker": registry._db_integration_item(integration, module="checker")}

    monkeypatch.setattr(registry, "_db_integration_states", fake_db_states)

    health = await registry.health(account=account, session=object())
    payload = health.model_dump(mode="json")

    assert "must-not-leak" not in str(payload)
    assert payload["checker"]["message"] == "WB failed Authorization=<redacted> password=<redacted>"


@pytest.mark.asyncio
async def test_module_registry_db_state_is_account_scoped(monkeypatch) -> None:
    registry = ModuleRegistryService(settings=Settings(reputation_enabled=True, reputation_base_url="http://legacy.internal"))
    account_one = SimpleNamespace(id=1, external_account_id=None, name="main")
    account_two = SimpleNamespace(id=2, external_account_id=None, name="second")

    async def fake_db_states(*, session, account):
        if account.id != 1:
            return {}
        integration = SimpleNamespace(
            module="reputation",
            enabled=False,
            mode="local",
            status="disabled",
            configuration_encrypted_json=None,
            last_error_code=None,
            last_error_message=None,
        )
        return {"reputation": registry._db_integration_item(integration, module="reputation")}

    monkeypatch.setattr(registry, "_db_integration_states", fake_db_states)

    account_one_health = await registry.health(account=account_one, session=object())
    account_two_health = await registry.health(account=account_two, session=object())

    assert account_one_health.reputation.status == "disabled"
    assert account_one_health.reputation.enabled is False
    assert account_two_health.reputation.status in {"degraded", "ok"}
    assert account_two_health.reputation.enabled is True


def test_reputation_module_health_uses_reputation_token_categories_not_content() -> None:
    source = (ROOT / "app/services/module_registry.py").read_text(encoding="utf-8")

    assert "WBAPICategory.FEEDBACKS_QUESTIONS.value" in source
    assert "WBAPICategory.BUYER_CHAT.value" in source
    assert "wb_content_token_not_configured" not in source
