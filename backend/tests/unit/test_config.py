from __future__ import annotations

from pydantic import ValidationError

from app.core.config import Settings


def test_production_like_env_rejects_default_secrets() -> None:
    try:
        Settings(app_env="production")
    except ValidationError:
        pass
    else:
        raise AssertionError("production config must reject default secrets")


def test_production_like_env_accepts_custom_secrets() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="custom-access-secret",
        jwt_refresh_secret_key="custom-refresh-secret",
        wb_token_encryption_key="u7WlBtvwlHGawEqTG3OCAXoTr4Wr9L5xRngkQCxwB3I=",
    )

    assert settings.is_production_like is True


def test_cors_default_allows_any_origin_with_credentials() -> None:
    settings = Settings()

    assert settings.cors_allow_credentials is True
    assert settings.effective_cors_allow_origin_regex == r".*"


def test_production_cors_default_requires_explicit_allowed_origins() -> None:
    settings = Settings(
        app_env="production",
        jwt_secret_key="custom-access-secret",
        jwt_refresh_secret_key="custom-refresh-secret",
        wb_token_encryption_key="u7WlBtvwlHGawEqTG3OCAXoTr4Wr9L5xRngkQCxwB3I=",
    )

    assert settings.cors_allow_credentials is True
    assert settings.effective_cors_allow_origin_regex is None


def test_explicit_cors_origin_regex_is_preserved() -> None:
    settings = Settings(cors_allow_origin_regex=r"^https://finance\\.example\\.com$")

    assert settings.effective_cors_allow_origin_regex == r"^https://finance\\.example\\.com$"


def test_cors_lists_accept_json_array_env_format() -> None:
    settings = Settings(
        cors_allow_methods='["GET", "POST", "OPTIONS"]',
        cors_allow_headers='["Authorization", "Content-Type"]',
    )

    assert settings.cors_allow_methods == ["GET", "POST", "OPTIONS"]
    assert settings.cors_allow_headers == ["Authorization", "Content-Type"]


def test_production_like_env_rejects_shared_access_and_refresh_secret() -> None:
    try:
        Settings(
            app_env="production",
            jwt_secret_key="shared-secret",
            jwt_refresh_secret_key="shared-secret",
            wb_token_encryption_key="u7WlBtvwlHGawEqTG3OCAXoTr4Wr9L5xRngkQCxwB3I=",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("production config must require distinct access and refresh secrets")


def test_wb_token_encryption_key_must_be_valid_fernet_key() -> None:
    try:
        Settings(wb_token_encryption_key="not-a-fernet-key")
    except ValidationError as exc:
        assert "WB_TOKEN_ENCRYPTION_KEY" in str(exc)
        assert "32 url-safe base64-encoded bytes" in str(exc)
    else:
        raise AssertionError("invalid WB token encryption key must be rejected")


def test_dev_placeholder_wb_token_encryption_key_uses_local_default() -> None:
    settings = Settings(wb_token_encryption_key="replace-with-fernet-key")

    assert settings.wb_token_encryption_key == Settings.DEFAULT_WB_ENCRYPTION_KEY


def test_production_like_env_rejects_placeholder_wb_token_encryption_key() -> None:
    try:
        Settings(
            app_env="production",
            jwt_secret_key="custom-access-secret",
            jwt_refresh_secret_key="custom-refresh-secret",
            wb_token_encryption_key="replace-with-fernet-key",
        )
    except ValidationError as exc:
        assert "wb_token_encryption_key" in str(exc)
    else:
        raise AssertionError("production config must reject placeholder WB token encryption key")


def test_finance_detail_pages_per_run_defaults_to_three() -> None:
    settings = Settings()

    assert settings.finance_detail_pages_per_run == 3


def test_analytics_funnel_batch_size_defaults_to_twenty() -> None:
    settings = Settings()

    assert settings.analytics_funnel_batch_size == 20


def test_analytics_funnel_batch_size_rejects_values_over_twenty() -> None:
    try:
        Settings(analytics_funnel_batch_size=21)
    except ValidationError:
        pass
    else:
        raise AssertionError("analytics_funnel_batch_size > 20 must be rejected")


def test_grouping_test_account_ids_accept_csv_or_json() -> None:
    assert Settings(grouping_test_account_ids="1,2").grouping_test_account_ids == [1, 2]
    assert Settings(grouping_test_account_ids="[3, 4]").grouping_test_account_ids == [3, 4]


def test_dynamic_problem_engine_rollout_flags_are_available() -> None:
    settings = Settings(
        dynamic_problem_engine_test_account_ids="10,20",
        show_legacy_problem_cards="false",
        enable_legacy_diagnostics="true",
    )

    assert settings.dynamic_problem_engine_enabled is True
    assert settings.dynamic_problem_engine_test_account_ids == [10, 20]
    assert settings.show_legacy_problem_cards is False
    assert settings.enable_legacy_diagnostics is True


def test_marketplace_write_kill_switches_default_to_disabled() -> None:
    settings = Settings()

    assert settings.enable_reputation_publish is False
    assert settings.enable_reputation_write_actions is False
    assert settings.enable_claims_submit is False
    assert settings.enable_grouping_merge is False
    assert settings.enable_card_auto_apply is False


def test_reputation_write_actions_flag_accepts_env_name(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_REPUTATION_WRITE_ACTIONS", "true")

    assert Settings().enable_reputation_write_actions is True
