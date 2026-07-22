from __future__ import annotations

from datetime import datetime
from decimal import Decimal
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


AgentMCPId = int | str | None


class AgentMCPRequest(AgentBaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: AgentMCPId = None
    method: str = Field(min_length=1, max_length=120)
    params: dict[str, Any] = Field(default_factory=dict)


class AgentMCPResponse(AgentBaseModel):
    jsonrpc: Literal["2.0"] = "2.0"
    id: AgentMCPId = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


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


AgentScenarioType = Literal[
    "general",
    "reputation",
    "pricing",
    "ads",
    "stock",
    "strategy",
    "report",
]
AgentScenarioStatus = Literal["draft", "active", "paused", "archived"]
AgentScenarioApprovalPolicy = Literal[
    "manual_review",
    "confirm_each_action",
    "auto_readonly",
]
AgentScenarioRunStatus = Literal[
    "queued",
    "running",
    "completed",
    "partial",
    "failed",
    "blocked",
    "cancelled",
]


class AgentScenarioTemplate(AgentBaseModel):
    key: str
    title: str
    description: str
    scenario_type: AgentScenarioType
    default_schedule_json: dict[str, Any] = Field(default_factory=dict)
    default_guardrails_json: dict[str, Any] = Field(default_factory=dict)
    default_actions_json: list[dict[str, Any]] = Field(default_factory=list)


class AgentScenarioTemplatesResponse(AgentBaseModel):
    status: Literal["ok"] = "ok"
    items: list[AgentScenarioTemplate] = Field(default_factory=list)


class AgentScenarioCreate(AgentBaseModel):
    account_id: int | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    scenario_type: AgentScenarioType = "general"
    source_prompt: str | None = Field(default=None, max_length=4000)
    scope_json: dict[str, Any] = Field(default_factory=dict)
    schedule_json: dict[str, Any] = Field(default_factory=dict)
    trigger_json: dict[str, Any] = Field(default_factory=dict)
    guardrails_json: dict[str, Any] = Field(default_factory=dict)
    actions_json: list[dict[str, Any]] = Field(default_factory=list)
    notification_json: dict[str, Any] = Field(default_factory=dict)
    ai_plan_json: dict[str, Any] = Field(default_factory=dict)
    approval_policy: AgentScenarioApprovalPolicy = "manual_review"
    auto_execute_enabled: bool = False


class AgentScenarioUpdate(AgentBaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    status: AgentScenarioStatus | None = None
    source_prompt: str | None = Field(default=None, max_length=4000)
    scope_json: dict[str, Any] | None = None
    schedule_json: dict[str, Any] | None = None
    trigger_json: dict[str, Any] | None = None
    guardrails_json: dict[str, Any] | None = None
    actions_json: list[dict[str, Any]] | None = None
    notification_json: dict[str, Any] | None = None
    ai_plan_json: dict[str, Any] | None = None
    approval_policy: AgentScenarioApprovalPolicy | None = None
    auto_execute_enabled: bool | None = None


class AgentScenarioRead(AgentBaseModel):
    id: int
    account_id: int
    created_by_user_id: int | None = None
    updated_by_user_id: int | None = None
    name: str
    description: str | None = None
    scenario_type: str
    status: str
    approval_policy: str
    auto_execute_enabled: bool
    source_prompt: str | None = None
    scope_json: dict[str, Any] = Field(default_factory=dict)
    schedule_json: dict[str, Any] = Field(default_factory=dict)
    trigger_json: dict[str, Any] = Field(default_factory=dict)
    guardrails_json: dict[str, Any] = Field(default_factory=dict)
    actions_json: list[dict[str, Any]] = Field(default_factory=list)
    notification_json: dict[str, Any] = Field(default_factory=dict)
    ai_plan_json: dict[str, Any] = Field(default_factory=dict)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_run_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentScenarioListResponse(AgentBaseModel):
    status: Literal["ok", "empty"] = "empty"
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[AgentScenarioRead] = Field(default_factory=list)


class AgentScenarioRunCreate(AgentBaseModel):
    trigger: Literal["manual", "scheduler", "chat", "test"] = "manual"
    dry_run: bool = True
    input_json: dict[str, Any] = Field(default_factory=dict)


class AgentActionPreviewRead(AgentBaseModel):
    id: int
    account_id: int
    scenario_id: int | None = None
    run_id: int | None = None
    api_action_key: str | None = None
    title: str
    status: str
    confirm_required: bool
    idempotency_key: str
    before_json: dict[str, Any] = Field(default_factory=dict)
    after_json: dict[str, Any] = Field(default_factory=dict)
    payload_json: dict[str, Any] = Field(default_factory=dict)
    risk_json: dict[str, Any] = Field(default_factory=dict)
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentScenarioRunRead(AgentBaseModel):
    id: int
    account_id: int
    scenario_id: int
    requested_by_user_id: int | None = None
    trigger: str
    status: str
    dry_run: bool
    started_at: datetime | None = None
    finished_at: datetime | None = None
    input_json: dict[str, Any] = Field(default_factory=dict)
    output_json: dict[str, Any] = Field(default_factory=dict)
    actions_preview_json: list[dict[str, Any]] = Field(default_factory=list)
    actions_executed: int = 0
    actions_blocked: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    log_text: str | None = None
    error_code: str | None = None
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime
    action_previews: list[AgentActionPreviewRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class AgentScenarioRunListResponse(AgentBaseModel):
    status: Literal["ok", "empty"] = "empty"
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[AgentScenarioRunRead] = Field(default_factory=list)


class AgentFinanceSummary(AgentBaseModel):
    status: Literal["ok"] = "ok"
    account_id: int
    scenarios_total: int = 0
    active_scenarios: int = 0
    runs_total: int = 0
    runs_last_30d: int = 0
    failed_runs_last_30d: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal("0")
    ledger_items: list[dict[str, Any]] = Field(default_factory=list)
