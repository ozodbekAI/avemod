from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field

from app.schemas.operator import (
    DraftOut,
    ExternalStatus,
    OperatorBaseModel,
    OperatorModule,
    Priority,
    TrustState,
    UnifiedActionOut,
)


ReputationRuntimeMode = Literal["local", "external_adapter", "disabled"]


class ReputationRuntimeOut(OperatorBaseModel):
    runtime_mode: ReputationRuntimeMode = "disabled"
    dangerous_actions_enabled: bool = False
    publish_enabled: bool = False
    auto_publish_enabled: bool = False
    chat_send_enabled: bool = False


class ReputationReviewInstructionPlanOut(OperatorBaseModel):
    instructions: str = ""
    primary_review_category: str | None = None
    primary_review_bucket: str | None = None
    secondary_review_categories: list[str] = Field(default_factory=list)
    tone_only_review_categories: list[str] = Field(default_factory=list)
    suppressed_review_categories: list[str] = Field(default_factory=list)
    no_clear_primary: bool = False
    routing_scores: dict[str, int] = Field(default_factory=dict)
    routing_primary_candidate: str | None = None
    routing_secondary_candidate: str | None = None
    primary_review_role: str | None = None
    primary_review_weighted_score: int | None = None
    secondary_review_buckets: dict[str, str] = Field(default_factory=dict)
    routing_weighted_scores: dict[str, int] = Field(default_factory=dict)
    routing_margin: int | None = None


class ReputationItemOut(OperatorBaseModel):
    id: str
    item_type: str
    item_id: str | None = None
    kind: str | None = None
    external_id: str | None = None
    external_status: ExternalStatus = ExternalStatus.NOT_CREATED
    account_id: int | None = None
    nm_id: int | None = None
    sku_id: int | None = None
    rating: int | None = None
    buyer_name: str | None = None
    title: str = ""
    text: str = ""
    pros: str | None = None
    cons: str | None = None
    answer_text: str | None = None
    answer_state: str | None = None
    answer_editable: bool | None = None
    sentiment: str | None = None
    priority: Priority = Priority.P3
    review_type: str | None = None
    review_categories: list[str] = Field(default_factory=list)
    review_category_matches: list[dict[str, Any]] = Field(default_factory=list)
    review_instruction_plan: ReputationReviewInstructionPlanOut | None = None
    review_need_reply_score: int | None = None
    review_requires_manual_attention: bool = False
    status: str = "new"
    trust_state: TrustState = TrustState.PROVISIONAL
    received_at: datetime | None = None
    created_at: datetime | None = None
    replied_at: datetime | None = None
    needs_reply: bool = False
    draft: DraftOut | None = None
    actions: list[UnifiedActionOut] = Field(default_factory=list)
    product_details: dict[str, Any] = Field(default_factory=dict)
    media: list[dict[str, Any]] = Field(default_factory=list)
    bables: list[Any] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    source_payload: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ReputationInboxOut(OperatorBaseModel):
    status: str = "unavailable"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[ReputationItemOut] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    trust_state: TrustState = TrustState.UNAVAILABLE
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class ReputationSyncOut(OperatorBaseModel):
    status: str = "not_configured"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    job_id: str | None = None
    message: str | None = None
    reviews_sync_status: str = "not_configured"
    questions_sync_status: str = "not_configured"
    chats_sync_status: str = "not_configured"
    backlog_status: str = "disabled"
    automation_status: str = "disabled"
    last_error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.UNAVAILABLE


class ReputationDraftRequest(OperatorBaseModel):
    draft_type: str | None = None
    text: str | None = None
    force_ai: bool | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReputationDraftMutationOut(OperatorBaseModel):
    status: str = "unavailable"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    draft: DraftOut | None = None
    message: str | None = None
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.UNAVAILABLE


class ReputationPublishRequest(OperatorBaseModel):
    confirm: bool = False
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReputationDraftDecisionRequest(OperatorBaseModel):
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReputationNoReplyRequest(OperatorBaseModel):
    confirm: bool = False
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReputationSummaryOut(ReputationRuntimeOut):
    status: str = "unavailable"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    unanswered_reviews_count: int | None = None
    unanswered_questions_count: int | None = None
    unread_chats_count: int | None = None
    negative_unanswered_count: int | None = None
    draft_ready_count: int | None = None
    average_rating: float | None = None
    sentiment: dict[str, int] = Field(default_factory=dict)
    priority: dict[str, int] = Field(default_factory=dict)
    reviews_sync_status: str = "not_configured"
    questions_sync_status: str = "not_configured"
    chats_sync_status: str = "not_configured"
    backlog_status: str = "disabled"
    automation_status: str = "disabled"
    last_error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.UNAVAILABLE


class ReputationSettingsUpdateRequest(OperatorBaseModel):
    automation_enabled: bool | None = None
    auto_sync: bool | None = None
    auto_draft: bool | None = None
    auto_draft_limit_per_sync: int | None = None
    reply_mode: str | None = None
    tone: str | None = None
    language: str | None = None
    signature: str | None = None
    templates: dict[str, Any] | list[dict[str, Any]] | None = None
    signatures: list[dict[str, Any] | str] | None = None
    rating_mode_map: dict[str, str] | None = None
    config: dict[str, Any] | None = None
    blacklist_keywords: list[str] | None = None
    whitelist_keywords: list[str] | None = None
    ai_enabled: bool | None = None
    ai_provider: str | None = None
    ai_model: str | None = None
    auto_publish_enabled: bool | None = None
    auto_publish: bool | None = None
    questions_reply_mode: str | None = None
    questions_auto_draft: bool | None = None
    questions_auto_publish: bool | None = None
    chat_enabled: bool | None = None
    chat_auto_reply_enabled: bool | None = None
    chat_auto_reply: bool | None = None
    analytics_enabled: bool | None = None
    analytics_period: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ReputationSettingsOut(ReputationRuntimeOut):
    status: str = "unavailable"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    message: str | None = None
    auto_sync: bool = True
    auto_draft: bool = False
    auto_draft_limit_per_sync: int = 30
    reply_mode: str | None = None
    tone: str | None = None
    language: str | None = None
    signature: str | None = None
    templates: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    signatures: list[dict[str, Any]] = Field(default_factory=list)
    rating_mode_map: dict[str, str] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    blacklist_keywords: list[str] = Field(default_factory=list)
    whitelist_keywords: list[str] = Field(default_factory=list)
    ai_enabled: bool = False
    ai_provider: str = "openai"
    ai_model: str | None = None
    auto_publish_enabled: bool = False
    auto_publish: bool = False
    automation_enabled: bool = False
    chat_auto_reply_enabled: bool = False
    chat_auto_reply: bool = False
    questions_reply_mode: str = "semi"
    questions_auto_draft: bool = False
    questions_auto_publish: bool = False
    chat_enabled: bool = False
    analytics_enabled: bool = False
    analytics_ready: bool = False
    analytics_period: str | None = None
    analytics_status: str = "activation_required"
    analytics_status_reason: str | None = None
    reviews_sync_status: str = "not_configured"
    questions_sync_status: str = "not_configured"
    chats_sync_status: str = "not_configured"
    backlog_status: str = "disabled"
    automation_status: str = "disabled"
    last_error: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.UNAVAILABLE


class ReputationBrandsOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    brands: list[str] = Field(default_factory=list)
    total: int = 0
    source: str = "catalog_reputation"
    warnings: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.PROVISIONAL


class ReputationDraftsOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[DraftOut] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    trust_state: TrustState = TrustState.PROVISIONAL


class ReputationBulkDraftDecisionOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    approved_count: int = 0
    published_count: int = 0
    total: int = 0
    data: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.PROVISIONAL


class ReputationChatEventOut(OperatorBaseModel):
    id: str
    chat_id: str
    account_id: int | None = None
    event_type: str = "message"
    sender_role: str = "buyer"
    text: str = ""
    created_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ReputationChatsOut(OperatorBaseModel):
    status: str = "not_configured"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[ReputationItemOut] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.UNAVAILABLE


class ReputationChatEventsOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    chat_id: str
    items: list[ReputationChatEventOut] = Field(default_factory=list)
    trust_state: TrustState = TrustState.PROVISIONAL


class ReputationAnalyticsOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    analytics_status: str = "activation_required"
    analytics_status_reason: str | None = None
    analytics_enabled: bool = False
    analytics_ready: bool = False
    selected_period: str | None = None
    total: int = 0
    prev_total: int = 0
    period_growth: int = 0
    growth_pct: float = 0.0
    avg_rating: float | None = None
    positive_share: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    category_labels: dict[str, str] = Field(default_factory=dict)
    by_category_sentiment: list[dict[str, Any]] = Field(default_factory=list)
    by_rating: dict[int, int] = Field(default_factory=dict)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    trust_state: TrustState = TrustState.OPERATIONAL


class ReputationPromptCategoryOut(OperatorBaseModel):
    code: str
    label: str
    positive_prompt: str
    negative_prompt: str
    sort_order: int = 0
    is_active: bool = True
    scope: str = "global"


class ReputationLearningEntryOut(OperatorBaseModel):
    id: int
    account_id: int
    nm_id: int | None = None
    target_type: str
    category_code: str | None = None
    category_label: str | None = None
    sentiment_scope: str | None = None
    user_instruction: str
    applied_text: str
    stop_word: str | None = None
    source_answer_text: str | None = None
    is_active: bool = True
    created_at: datetime | None = None


class ReputationLearningOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    enabled: bool = False
    review_prompt_template: str = ""
    question_prompt_template: str = ""
    chat_prompt_template: str = ""
    stop_words: list[str] = Field(default_factory=list)
    categories: list[ReputationPromptCategoryOut] = Field(default_factory=list)
    entries: list[ReputationLearningEntryOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.PROVISIONAL


class ReputationLearningToggleRequest(OperatorBaseModel):
    enabled: bool


class ReputationLearningApplyRequest(OperatorBaseModel):
    instruction: str
    answer_text: str | None = None
    item_id: str | None = None
    nm_id: int | None = None
    target_type: str | None = None
    category_code: str | None = None
    sentiment_scope: str | None = None
    stop_word: str | None = None


class ReputationPromptUpdateRequest(OperatorBaseModel):
    review_prompt_template: str | None = None
    question_prompt_template: str | None = None
    chat_prompt_template: str | None = None
    stop_words: list[str] | None = None
    categories: list[dict[str, Any]] | None = None


class ReputationProductInsightOut(OperatorBaseModel):
    status: str = "ok"
    module: OperatorModule = OperatorModule.REPUTATION
    account_id: int | None = None
    nm_id: int
    total: int = 0
    avg_rating: float | None = None
    rating_distribution: dict[str, int] = Field(default_factory=dict)
    top_categories: list[dict[str, Any]] = Field(default_factory=list)
    pain_points: list[dict[str, Any]] = Field(default_factory=list)
    customer_wants: list[dict[str, Any]] = Field(default_factory=list)
    prompt_rules: list[dict[str, Any]] = Field(default_factory=list)
    learning_entries: list[ReputationLearningEntryOut] = Field(default_factory=list)
    recent_items: list[ReputationItemOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    trust_state: TrustState = TrustState.PROVISIONAL
