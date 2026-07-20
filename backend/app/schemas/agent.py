from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SECRET_FIELD_TOKENS = (
    "api_key",
    "authorization",
    "credential",
    "encrypted_token",
    "encryption_key",
    "headers",
    "jwt",
    "password",
    "refresh_token",
    "secret",
    "token",
)


def _scrub_secret_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _scrub_secret_fields(item)
            for key, item in value.items()
            if not any(token in str(key).lower() for token in SECRET_FIELD_TOKENS)
        }
    if isinstance(value, list):
        return [_scrub_secret_fields(item) for item in value]
    return value


class AgentBaseModel(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def scrub_secret_fields(cls, data: Any) -> Any:
        return _scrub_secret_fields(data)


AgentIntent = Literal[
    "help",
    "admin_answer",
    "product_search",
    "product_details",
    "stock_export",
    "title_update",
    "page_explain",
    "reputation_agent",
    "scenario_create",
    "pricing_agent",
    "insights_report",
    "strategy_advice",
    "module_navigate",
    "open_logistics",
    "open_action_center",
    "open_checker",
    "open_pricing",
    "open_stock_control",
    "open_money",
    "api_action",
]

AgentActionType = Literal[
    "answer",
    "navigate",
    "open_product_picker",
    "open_title_editor",
    "open_preview_dialog",
    "download_file",
    "create_manual_task",
    "api_request",
]


class AgentMessageRequest(AgentBaseModel):
    account_id: int | None = None
    message: str = Field(default="", max_length=4000)
    intent: AgentIntent | None = None
    selected_nm_id: int | None = None
    new_title: str | None = Field(default=None, max_length=500)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentToolSpec(AgentBaseModel):
    name: str
    intent: AgentIntent
    title: str
    description: str
    required_args: list[str] = Field(default_factory=list)
    write_policy: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class AgentToolsResponse(AgentBaseModel):
    protocol: Literal["finance-agent-tools-v1"] = "finance-agent-tools-v1"
    tools: list[AgentToolSpec] = Field(default_factory=list)
    modules: dict[str, dict[str, str]] = Field(default_factory=dict)
    api_actions: dict[str, dict[str, Any]] = Field(default_factory=dict)
    direct_marketplace_writes: bool = False


class AgentToolCallRequest(AgentBaseModel):
    account_id: int | None = None
    tool_name: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentProductRef(AgentBaseModel):
    nm_id: int
    vendor_code: str | None = None
    title: str | None = None
    brand: str | None = None
    subject_name: str | None = None
    thumbnail_url: str | None = None


class AgentUIAction(AgentBaseModel):
    type: AgentActionType
    title: str
    description: str | None = None
    href: str | None = None
    method: Literal["GET", "POST", "PATCH", "PUT", "DELETE"] | None = None
    confirm_required: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentMessageResponse(AgentBaseModel):
    status: Literal["ok", "needs_input", "blocked", "error"] = "ok"
    mode: Literal["ai", "ai_fallback"] = "ai"
    intent: AgentIntent = "help"
    message: str
    actions: list[AgentUIAction] = Field(default_factory=list)
    products: list[AgentProductRef] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit: dict[str, Any] = Field(default_factory=dict)
