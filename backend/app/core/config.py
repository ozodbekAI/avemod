from __future__ import annotations

import base64
import binascii
import json
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, ClassVar

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    DEFAULT_ACCESS_SECRET: ClassVar[str] = "local-dev-access-secret"
    DEFAULT_REFRESH_SECRET: ClassVar[str] = "local-dev-refresh-secret"
    DEFAULT_WB_ENCRYPTION_KEY: ClassVar[str] = (
        "XfoaFGX-I78C74Vi8pXyppYXQ05g7H0jBPJCOncKAsg="
    )
    WB_ENCRYPTION_KEY_PLACEHOLDER: ClassVar[str] = "replace-with-fernet-key"

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "WB Data Core Backend"
    app_env: str = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    cors_allowed_origins: Annotated[list[str], NoDecode] = [
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ]
    cors_allow_origin_regex: str | None = None
    cors_allow_credentials: bool = True
    cors_allow_methods: Annotated[list[str], NoDecode] = [
        "GET",
        "POST",
        "PUT",
        "PATCH",
        "DELETE",
        "OPTIONS",
    ]
    cors_allow_headers: Annotated[list[str], NoDecode] = ["*"]

    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/wb_data_core"
    )
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout_seconds: int = 60
    database_pool_recycle_seconds: int = 1800
    database_statement_timeout_ms: int = 120_000
    database_lock_timeout_ms: int = 20_000
    database_idle_in_transaction_timeout_ms: int = 300_000

    jwt_secret_key: str = DEFAULT_ACCESS_SECRET
    jwt_refresh_secret_key: str = DEFAULT_REFRESH_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    wb_token_encryption_key: str = DEFAULT_WB_ENCRYPTION_KEY

    enable_scheduler: bool = True
    scheduler_timezone: str = "UTC"

    default_page_size: int = 50
    max_page_size: int = 200
    heavy_endpoint_cache_ttl_seconds: int = 600
    money_response_snapshot_refresh_minutes: int = 1440
    money_response_snapshot_max_stale_minutes: int = 1440
    money_response_snapshot_active_days: int = 7
    money_response_snapshot_refresh_max_specs_per_account: int = 80
    money_response_snapshot_refresh_min_access_count: int = 2

    wb_http_timeout: int = 30
    wb_http_retry_attempts: int = 3
    wb_http_retry_backoff_seconds: int = 1
    analytics_funnel_batch_size: int = 20
    finance_detail_pages_per_run: int = 3
    finance_detail_page_limit: int = 100_000
    finance_refresh_marts_after_sync: bool = True
    stocks_pending_task_max_age_hours: int = 6
    sync_running_cursor_stale_hours: int = 6
    checker_base_url: str | None = None
    checker_internal_token: str | None = None
    checker_service_token: str | None = None
    checker_store_map: dict[str, int] = Field(default_factory=dict)
    checker_account_store_mapping: dict[str, int] = Field(default_factory=dict)
    checker_http_timeout_seconds: float = 5.0
    checker_timeout_seconds: float | None = None
    stockops_base_url: str | None = None
    stockops_internal_token: str | None = None
    stockops_http_timeout_seconds: float = 10.0
    grouping_enabled: bool = False
    grouping_base_url: str | None = None
    grouping_internal_token: str | None = None
    grouping_test_account_ids: list[int] = Field(default_factory=list)
    grouping_http_timeout_seconds: float = 5.0
    dynamic_problem_engine_enabled: bool = True
    dynamic_problem_engine_test_account_ids: list[int] = Field(default_factory=list)
    show_legacy_problem_cards: bool = True
    enable_legacy_diagnostics: bool = False
    reputation_enabled: bool = False
    reputation_base_url: str | None = None
    reputation_internal_token: str | None = None
    reputation_shop_map: dict[str, int] = Field(default_factory=dict)
    reputation_http_timeout_seconds: float = 5.0
    reputation_ai_default_enabled: bool = False
    reputation_auto_sync_enabled: bool = True
    reputation_auto_draft_enabled: bool = False
    claims_enabled: bool = False
    claims_base_url: str | None = None
    claims_internal_token: str | None = None
    claims_http_timeout_seconds: float = 5.0
    photo_enabled: bool = False
    photo_base_url: str | None = None
    photo_internal_token: str | None = None
    photo_http_timeout_seconds: float = 5.0
    photo_storage_root: str = ".local/photo_studio"
    photo_signed_url_ttl_seconds: int = 900
    media_root: str | None = None
    media_public_base_url: str | None = None
    public_base_url: str | None = None
    gemini_api_key: str | None = None
    gemini_api_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_image_model: str = "gemini-3.1-flash-image-preview"
    gemini_image_model_fallback: str = "gemini-2.5-flash-image"
    gemini_image_timeout_seconds: float = 240.0
    gemini_image_max_retries: int = 2
    experiments_enabled: bool = True
    enable_reputation_publish: bool = False
    enable_reputation_write_actions: bool = False
    enable_claims_submit: bool = False
    enable_grouping_merge: bool = False
    enable_card_auto_apply: bool = False
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    openai_vision_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 60.0
    agent_openai_input_usd_per_million: Decimal = Decimal("0.25")
    agent_openai_output_usd_per_million: Decimal = Decimal("2.00")
    wb_checker_data_path: str = "data/wb_checker"
    checker_ai_enabled: bool = False
    checker_vision_enabled: bool = False
    checker_min_title_length: int = 40
    checker_max_title_length: int = 60
    checker_min_description_length: int = 1000
    checker_max_description_length: int = 1800
    checker_min_photos_count: int = 3
    checker_recommended_photos_count: int = 6
    checker_ai_context_photos_count: int = 2
    checker_product_dna_photos_count: int = 4
    checker_ai_max_output_tokens: int = 4096
    checker_ai_temperature: float = 0.2

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug(cls, value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "on", "debug", "development"}:
                return True
            if normalized in {
                "0",
                "false",
                "no",
                "off",
                "release",
                "prod",
                "production",
            }:
                return False
        return bool(value)

    @field_validator("analytics_funnel_batch_size")
    @classmethod
    def validate_analytics_funnel_batch_size(cls, value: int) -> int:
        if value < 1 or value > 20:
            raise ValueError("analytics_funnel_batch_size must be between 1 and 20")
        return value

    @field_validator("wb_token_encryption_key", mode="before")
    @classmethod
    def validate_wb_token_encryption_key(cls, value: object) -> str:
        raw = str(value or "").strip()
        if raw == cls.WB_ENCRYPTION_KEY_PLACEHOLDER:
            raw = cls.DEFAULT_WB_ENCRYPTION_KEY
        if not raw:
            raise ValueError(
                "WB_TOKEN_ENCRYPTION_KEY must be set to a Fernet key; generate one with cryptography.fernet.Fernet.generate_key()"
            )
        try:
            decoded = base64.b64decode(
                raw.encode("utf-8"), altchars=b"-_", validate=True
            )
        except (binascii.Error, ValueError) as exc:
            raise ValueError(
                "WB_TOKEN_ENCRYPTION_KEY must be a valid Fernet key: 32 url-safe base64-encoded bytes"
            ) from exc
        if len(decoded) != 32:
            raise ValueError(
                "WB_TOKEN_ENCRYPTION_KEY must be a valid Fernet key: 32 url-safe base64-encoded bytes"
            )
        return raw

    @field_validator(
        "database_pool_size",
        "database_max_overflow",
        "database_pool_timeout_seconds",
        "database_pool_recycle_seconds",
        "database_statement_timeout_ms",
        "database_lock_timeout_ms",
        "database_idle_in_transaction_timeout_ms",
        "money_response_snapshot_refresh_minutes",
        "money_response_snapshot_max_stale_minutes",
        "money_response_snapshot_active_days",
        "money_response_snapshot_refresh_max_specs_per_account",
        "money_response_snapshot_refresh_min_access_count",
    )
    @classmethod
    def validate_positive_pool_settings(cls, value: int) -> int:
        if value < 0:
            raise ValueError("database pool settings must be zero or positive")
        return value

    @field_validator(
        "cors_allowed_origins",
        "cors_allow_methods",
        "cors_allow_headers",
        mode="before",
    )
    @classmethod
    def normalize_csv_or_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [str(item).strip() for item in parsed if str(item).strip()]
            return [item.strip() for item in raw.split(",") if item.strip()]
        return [str(value).strip()]

    @model_validator(mode="after")
    def apply_checker_env_aliases(self) -> "Settings":
        if not self.checker_internal_token and self.checker_service_token:
            self.checker_internal_token = self.checker_service_token
        if not self.checker_store_map and self.checker_account_store_mapping:
            self.checker_store_map = dict(self.checker_account_store_mapping)
        if self.checker_timeout_seconds is not None:
            self.checker_http_timeout_seconds = float(self.checker_timeout_seconds)
        return self

    @field_validator(
        "checker_store_map", "checker_account_store_mapping", mode="before"
    )
    @classmethod
    def normalize_checker_store_map(cls, value: object) -> dict[str, int]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return {
                str(key): int(store_id)
                for key, store_id in value.items()
                if str(key).strip()
            }
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return {
                    str(key): int(store_id)
                    for key, store_id in parsed.items()
                    if str(key).strip()
                }
            result: dict[str, int] = {}
            for part in raw.split(","):
                if not part.strip() or ":" not in part:
                    continue
                account_id, store_id = part.split(":", 1)
                account_key = account_id.strip()
                if account_key:
                    result[account_key] = int(store_id.strip())
            return result
        return {}

    @field_validator("reputation_shop_map", mode="before")
    @classmethod
    def normalize_reputation_shop_map(cls, value: object) -> dict[str, int]:
        if value in (None, ""):
            return {}
        if isinstance(value, dict):
            return {
                str(key): int(shop_id)
                for key, shop_id in value.items()
                if str(key).strip()
            }
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return {}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return {
                    str(key): int(shop_id)
                    for key, shop_id in parsed.items()
                    if str(key).strip()
                }
            result: dict[str, int] = {}
            for part in raw.split(","):
                if not part.strip() or ":" not in part:
                    continue
                account_id, shop_id = part.split(":", 1)
                account_key = account_id.strip()
                if account_key:
                    result[account_key] = int(shop_id.strip())
            return result
        return {}

    @field_validator(
        "grouping_test_account_ids",
        "dynamic_problem_engine_test_account_ids",
        mode="before",
    )
    @classmethod
    def normalize_account_id_list(cls, value: object) -> list[int]:
        if value in (None, ""):
            return []
        if isinstance(value, list):
            return [int(item) for item in value if str(item).strip()]
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return []
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                return [int(item) for item in parsed if str(item).strip()]
            return [int(item.strip()) for item in raw.split(",") if item.strip()]
        return [int(value)]

    @property
    def is_production_like(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod", "staging"}

    @model_validator(mode="after")
    def validate_secure_defaults(self) -> "Settings":
        if self.is_production_like:
            insecure_fields = []
            if self.jwt_secret_key == self.DEFAULT_ACCESS_SECRET:
                insecure_fields.append("jwt_secret_key")
            if self.jwt_refresh_secret_key == self.DEFAULT_REFRESH_SECRET:
                insecure_fields.append("jwt_refresh_secret_key")
            if self.wb_token_encryption_key == self.DEFAULT_WB_ENCRYPTION_KEY:
                insecure_fields.append("wb_token_encryption_key")
            if self.jwt_secret_key == self.jwt_refresh_secret_key:
                insecure_fields.append("jwt_refresh_secret_key")
            if insecure_fields:
                joined = ", ".join(insecure_fields)
                raise ValueError(
                    f"Production-like environment requires non-default secrets: {joined}"
                )
        return self

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "")

    @property
    def effective_cors_allow_origin_regex(self) -> str | None:
        if self.cors_allow_origin_regex:
            return self.cors_allow_origin_regex
        if self.is_production_like:
            return None
        # Allow browser-based frontends from any preview, tunnel, or deployed
        # host in local/dev while still supporting credentialed requests.
        return r".*"

    @property
    def OPENAI_API_KEY(self) -> str:
        return self.openai_api_key or ""

    @property
    def OPENAI_MODEL(self) -> str:
        return self.openai_model

    @property
    def OPENAI_VISION_MODEL(self) -> str:
        return self.openai_vision_model

    @property
    def AI_ENABLED(self) -> bool:
        return self.checker_ai_enabled

    @property
    def MIN_TITLE_LENGTH(self) -> int:
        return self.checker_min_title_length

    @property
    def MAX_TITLE_LENGTH(self) -> int:
        return self.checker_max_title_length

    @property
    def MIN_DESCRIPTION_LENGTH(self) -> int:
        return self.checker_min_description_length

    @property
    def MAX_DESCRIPTION_LENGTH(self) -> int:
        return self.checker_max_description_length

    @property
    def MIN_PHOTOS_COUNT(self) -> int:
        return self.checker_min_photos_count

    @property
    def RECOMMENDED_PHOTOS_COUNT(self) -> int:
        return self.checker_recommended_photos_count

    @property
    def AI_CONTEXT_PHOTOS_COUNT(self) -> int:
        return self.checker_ai_context_photos_count

    @property
    def PRODUCT_DNA_PHOTOS_COUNT(self) -> int:
        return self.checker_product_dna_photos_count

    @property
    def GEMINI_MAX_OUTPUT_TOKENS(self) -> int:
        return self.checker_ai_max_output_tokens

    @property
    def GEMINI_TEMPERATURE(self) -> float:
        return self.checker_ai_temperature

    @property
    def GEMINI_AUDIT_MAX_OUTPUT_TOKENS(self) -> int:
        return self.checker_ai_max_output_tokens

    @property
    def GEMINI_FIX_MAX_OUTPUT_TOKENS(self) -> int:
        return self.checker_ai_max_output_tokens


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
