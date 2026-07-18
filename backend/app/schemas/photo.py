from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.portal import PortalBaseModel


PhotoProjectStatus = Literal[
    "draft", "in_progress", "review", "approved", "rejected", "archived"
]
PhotoVersionStatus = Literal[
    "draft", "ready", "preferred", "approved", "rejected", "archived", "failed"
]
PhotoJobStatus = Literal[
    "queued",
    "running",
    "completed",
    "partial",
    "failed",
    "cancelled",
    "not_configured",
    "disabled",
]


class PhotoGenerationState(PortalBaseModel):
    status: Literal["ok", "not_configured", "disabled"]
    provider: str | None = None
    message: str | None = None


class PhotoStudioStatusOut(PortalBaseModel):
    status: Literal["ok", "empty", "partial", "failed"] = "ok"
    mode: Literal["local"] = "local"
    configured: bool = True
    generation: PhotoGenerationState = Field(
        default_factory=lambda: PhotoGenerationState(status="not_configured")
    )
    projects_total: int = 0
    projects_active: int = 0
    versions_ready: int = 0
    last_activity_at: datetime | None = None
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class PhotoSettingsOut(PortalBaseModel):
    account_id: int
    provider_mode: str = "manual"
    default_provider: str | None = None
    default_model: str | None = None
    default_aspect_ratio: str | None = None
    default_output_format: str = "jpeg"
    max_upload_mb: int = 10
    allowed_mime_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp"]
    )
    generation_enabled: bool = False
    editing_enabled: bool = False
    external_apply_enabled: bool = False


class PhotoSettingsUpdate(PortalBaseModel):
    provider_mode: Literal["manual", "ai_optional"] | None = None
    default_provider: str | None = None
    default_model: str | None = None
    default_aspect_ratio: str | None = None
    default_output_format: Literal["jpeg", "png", "webp"] | None = None
    max_upload_mb: int | None = Field(default=None, ge=1, le=50)
    allowed_mime_types: list[str] | None = None
    generation_enabled: bool | None = None
    editing_enabled: bool | None = None

    @field_validator("allowed_mime_types")
    @classmethod
    def validate_mime_types(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        allowed = {"image/jpeg", "image/png", "image/webp"}
        normalized = sorted({item.strip().lower() for item in value if item.strip()})
        if not normalized or any(item not in allowed for item in normalized):
            raise ValueError(
                "allowed_mime_types supports image/jpeg, image/png, image/webp"
            )
        return normalized


class PhotoProjectCreate(PortalBaseModel):
    account_id: int
    nm_id: int
    sku_id: int | None = None
    source_issue_id: int | None = None
    source_action_key: str | None = None
    title: str = "Photo Studio project"


class PhotoProjectUpdate(PortalBaseModel):
    title: str | None = None
    status: PhotoProjectStatus | None = None
    preferred_version_id: int | None = None


class PhotoAssetOut(PortalBaseModel):
    id: int
    account_id: int
    nm_id: int | None = None
    project_id: int | None = None
    asset_type: str
    source_type: str
    original_file_name: str | None = None
    mime_type: str
    width: int | None = None
    height: int | None = None
    file_size: int
    checksum: str | None = None
    exif_removed: bool = False
    source_url: str | None = None
    url: str | None = None
    thumbnail: str | None = None
    source_asset_id: int | None = None
    is_test: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    deleted_at: datetime | None = None


class PhotoVersionCreate(PortalBaseModel):
    asset_id: int
    parent_version_id: int | None = None
    label: str | None = None
    brief_text: str | None = None
    change_summary: str | None = None


class PhotoVersionReview(PortalBaseModel):
    status: Literal["preferred", "approved", "rejected"]
    reason: str | None = None


class PhotoVersionOut(PortalBaseModel):
    id: int
    account_id: int
    project_id: int
    asset_id: int
    version_number: int
    parent_version_id: int | None = None
    status: PhotoVersionStatus
    label: str | None = None
    brief_text: str | None = None
    change_summary: str | None = None
    generation_job_id: int | None = None
    created_by_user_id: int | None = None
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    rejected_at: datetime | None = None
    rejection_reason: str | None = None
    url: str | None = None
    thumbnail: str | None = None
    operation: str | None = None
    source: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PhotoProjectMessageCreate(PortalBaseModel):
    message_type: Literal[
        "brief", "comment", "provider_instruction", "system", "review"
    ] = "comment"
    text: str = Field(min_length=1, max_length=4000)
    linked_asset_ids: list[int] = Field(default_factory=list)


class PhotoProjectMessageOut(PortalBaseModel):
    id: int
    account_id: int
    project_id: int
    author_user_id: int | None = None
    author_type: str
    message_type: str
    text: str
    linked_asset_ids: list[int] = Field(default_factory=list)
    created_at: datetime


class PhotoProjectEventOut(PortalBaseModel):
    id: int
    account_id: int
    project_id: int
    event_type: str
    actor_user_id: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class PhotoProjectOut(PortalBaseModel):
    id: int
    account_id: int
    nm_id: int
    sku_id: int | None = None
    title: str
    product_name: str | None = None
    vendor_code: str | None = None
    thumbnail: str | None = None
    preferred_thumbnail: str | None = None
    approved_thumbnail: str | None = None
    photos: list[str] = Field(default_factory=list)
    status: PhotoProjectStatus
    source_issue_id: int | None = None
    source_action_key: str | None = None
    created_by_user_id: int | None = None
    preferred_version_id: int | None = None
    approved_version_id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    archived_at: datetime | None = None
    assets: list[PhotoAssetOut] = Field(default_factory=list)
    versions: list[PhotoVersionOut] = Field(default_factory=list)
    jobs: list["PhotoJobOut"] = Field(default_factory=list)
    messages: list[PhotoProjectMessageOut] = Field(default_factory=list)
    events: list[PhotoProjectEventOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PhotoProjectsPage(PortalBaseModel):
    status: str = "ok"
    total: int
    limit: int
    offset: int
    items: list[PhotoProjectOut]
    warnings: list[str] = Field(default_factory=list)
    unavailable_sources: list[str] = Field(default_factory=list)


class PhotoWBImportOut(PortalBaseModel):
    status: Literal["ok", "empty"] = "ok"
    imported: int = 0
    assets: list[PhotoAssetOut] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PhotoExperimentCreateRequest(PortalBaseModel):
    hypothesis: str | None = None
    primary_metric: str = "conversion_rate"
    secondary_metrics: list[str] = Field(
        default_factory=lambda: ["revenue", "orders_count"]
    )
    guardrail_metrics: list[str] = Field(
        default_factory=lambda: ["stockout_days", "ads_spend"]
    )
    baseline_days: int | None = Field(default=None, ge=3, le=30)
    post_days: int | None = Field(default=14, ge=3, le=30)
    evaluation_delay_days: int | None = Field(default=0, ge=0, le=14)
    is_test: bool = False


class PhotoDownloadUrlOut(PortalBaseModel):
    asset_id: int
    url: str
    expires_at: datetime


class PhotoJobCreate(PortalBaseModel):
    job_type: Literal[
        "generate",
        "edit",
        "background_replace",
        "crop_resize",
        "remove_background",
        "enhance",
        "variant",
    ]
    input_asset_ids: list[int] = Field(default_factory=list)
    prompt: str | None = Field(default=None, max_length=4000)
    provider: str | None = None
    model: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def require_prompt_for_ai_jobs(self) -> "PhotoJobCreate":
        if (
            self.job_type
            in {
                "generate",
                "edit",
                "background_replace",
                "remove_background",
                "enhance",
                "variant",
            }
            and not self.prompt
        ):
            self.prompt = ""
        return self


class PhotoJobOut(PortalBaseModel):
    id: int
    account_id: int
    project_id: int
    input_asset_ids: list[int] = Field(default_factory=list)
    job_type: str
    provider: str | None = None
    model: str | None = None
    status: PhotoJobStatus
    prompt_version: str | None = None
    sanitized_prompt: str | None = None
    settings_snapshot: dict[str, Any] = Field(default_factory=dict)
    requested_by_user_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    attempt: int = 1
    progress_percent: int = 0
    output_asset_ids: list[int] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class PhotoJobsPage(PortalBaseModel):
    status: str = "ok"
    total: int
    limit: int
    offset: int
    items: list[PhotoJobOut]
