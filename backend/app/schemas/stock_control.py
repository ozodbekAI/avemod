from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.redaction import scrub_sensitive_payload


StockControlRunType = Literal["return_excess", "ship_from_hand"]
StockControlRunTypeWithPlanned = Literal[
    "return_excess", "ship_from_hand", "store_balance"
]
StockControlRunStatus = Literal[
    "queued", "running", "completed", "partial", "failed", "cancelled"
]
StockControlAllocationMode = Literal["redistribute", "balance"]


class StockControlBase(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def scrub_payloads(cls, value: Any) -> Any:
        return scrub_sensitive_payload(value)


class StockControlSettingsRead(StockControlBase):
    account_id: int
    default_il_profile_json: dict[str, float] = Field(default_factory=dict)
    minimum_history_orders: int = 10
    max_share_ratio_from_default: float = 3.0
    minimum_keep_per_size: int = 1
    excluded_regions_json: list[str] = Field(default_factory=list)
    ship_all_available_default: bool = False
    extra_allocation_method_default: str = "largest_remainder"

    model_config = {"from_attributes": True}


class StockControlSettingsUpdate(StockControlBase):
    default_il_profile_json: dict[str, float] | None = None
    minimum_history_orders: int | None = Field(default=None, ge=0)
    max_share_ratio_from_default: float | None = Field(default=None, ge=1)
    minimum_keep_per_size: int | None = Field(default=None, ge=0)
    excluded_regions_json: list[str] | None = None
    ship_all_available_default: bool | None = None
    extra_allocation_method_default: Literal["largest_remainder"] | None = None


class StockControlStatusRead(StockControlBase):
    status: Literal["ok", "empty", "running", "partial", "failed"] = "empty"
    mode: Literal["local"] = "local"
    configured: bool = True
    account_id: int | None = None
    last_success_at: datetime | None = None
    latest_stock_snapshot_at: datetime | None = None
    latest_region_demand_at: date | None = None
    warehouse_mapping_coverage_percent: float | None = None
    products_analyzed: int = 0
    regions_analyzed: int = 0
    movements_generated: int = 0
    unmapped_warehouses: int = 0
    latest_run: "StockControlRunRead | None" = None
    latest_runs: list["StockControlRunRead"] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    source_freshness: dict[str, Any] = Field(default_factory=dict)
    mapping_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class StockControlRunCreate(StockControlBase):
    account_id: int
    run_type: StockControlRunTypeWithPlanned
    source_mode: Literal["finance_db", "regional_supply_import", "latest_valid_run"] = (
        "finance_db"
    )
    date_from: date | None = None
    date_to: date | None = None
    allocation_mode: StockControlAllocationMode = "redistribute"
    priority_strategy: str | None = None
    settings_override: dict[str, Any] = Field(default_factory=dict)
    demand_run_id: int | None = None
    hand_stock_draft_id: int | None = None
    regional_supply_import_id: int | None = None
    ship_all_available: bool | None = None
    target_account_id: int | None = None
    mode: Literal["donor_recipient", "equalize"] | None = None
    min_source_stock: int = Field(default=0, ge=0)
    max_target_stock: int | None = Field(default=None, ge=0)
    size_aware: bool = True
    excluded_nm_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_phase_one(self) -> "StockControlRunCreate":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be before or equal to date_to")
        if self.run_type == "ship_from_hand" and self.hand_stock_draft_id is None:
            raise ValueError("hand_stock_draft_id is required for ship_from_hand")
        if self.run_type == "store_balance":
            if self.target_account_id is None:
                raise ValueError(
                    "target_account_id is required for store_balance phase 2 execution"
                )
            if int(self.target_account_id) == int(self.account_id):
                raise ValueError("target_account_id must differ from account_id")
        return self


class StockControlStoreBalancePreviewRequest(StockControlBase):
    account_id: int
    source_account_id: int | None = None
    target_account_id: int
    mode: Literal["donor_recipient", "equalize"] = "donor_recipient"
    min_source_stock: int = Field(default=0, ge=0)
    max_target_stock: int | None = Field(default=None, ge=0)
    size_aware: bool = True
    excluded_nm_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_accounts(self) -> "StockControlStoreBalancePreviewRequest":
        source = self.source_account_id or self.account_id
        if int(source) == int(self.target_account_id):
            raise ValueError("source and target accounts must differ")
        return self


class StockControlRunRead(StockControlBase):
    id: int
    account_id: int
    run_type: str
    status: str
    source_mode: str
    allocation_mode: str | None = None
    priority_strategy: str | None = None
    requested_by_user_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    source_snapshot_at: datetime | None = None
    input_summary_json: dict[str, Any] = Field(default_factory=dict)
    result_summary_json: dict[str, Any] = Field(default_factory=dict)
    eligible_products: int = 0
    rows_processed: int = 0
    rows_created: int = 0
    rows_skipped: int = 0
    rows_failed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    error_code: str | None = None
    error_summary: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StockControlRunsPage(StockControlBase):
    status: Literal["ok", "empty"] = "empty"
    total: int = 0
    limit: int = 50
    offset: int = 0
    items: list[StockControlRunRead] = Field(default_factory=list)


class StockControlRegionRowRead(StockControlBase):
    id: int
    run_id: int
    account_id: int
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    chrt_id: int | None = None
    size_name: str | None = None
    subject: str | None = None
    brand: str | None = None
    region: str
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    orders_qty: float = 0.0
    local_orders_qty: float = 0.0
    region_share: float = 0.0
    current_stock_qty: float = 0.0
    target_stock_qty: float = 0.0
    delta_qty: float = 0.0
    status: str
    localization_pct: float | None = None
    impact_pct: float | None = None
    distribution_source: str | None = None
    source_metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class StockControlRegionRowsPage(StockControlBase):
    total: int
    limit: int
    offset: int
    items: list[StockControlRegionRowRead]


class StockControlMovementRead(StockControlBase):
    id: int
    run_id: int
    account_id: int
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    size_name: str | None = None
    movement_type: str
    donor_region: str | None = None
    donor_warehouse: str | None = None
    recipient_region: str | None = None
    recipient_warehouse: str | None = None
    quantity: float = 0.0
    priority: str = "P3"
    reason_code: str | None = None
    business_explanation: str | None = None
    confidence: str = "medium"
    status: str = "new"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class StockControlMovementsPage(StockControlBase):
    total: int
    limit: int
    offset: int
    items: list[StockControlMovementRead]


class StockControlImportPreview(StockControlBase):
    file_name: str
    sheet_name: str | None = None
    rows_total: int = 0
    products: int = 0
    regions: int = 0
    sizes: int = 0
    warnings: list[str] = Field(default_factory=list)
    sample_rows: list[dict[str, Any]] = Field(default_factory=list)


class StockControlImportRead(StockControlBase):
    id: int
    account_id: int
    import_type: str
    status: str
    file_name: str | None = None
    sheet_name: str | None = None
    rows_total: int = 0
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HandStockRowIn(StockControlBase):
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    size_name: str | None = None
    available_qty: int = Field(ge=0)
    source_name: str | None = None


class HandStockDraftCreate(StockControlBase):
    account_id: int
    name: str
    rows: list[HandStockRowIn] = Field(default_factory=list)


class HandStockDraftUpdate(StockControlBase):
    name: str | None = None
    status: Literal["draft", "ready", "archived"] | None = None
    rows: list[HandStockRowIn] | None = None


class HandStockRowRead(StockControlBase):
    id: int
    draft_id: int
    account_id: int
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    size_name: str | None = None
    available_qty: float = 0.0
    source_name: str | None = None
    matching_status: str = "pending"
    validation_errors_json: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class HandStockDraftRead(StockControlBase):
    id: int
    account_id: int
    name: str
    status: str
    created_by_user_id: int | None = None
    created_at: datetime
    updated_at: datetime
    rows: list[HandStockRowRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class HandStockDraftsPage(StockControlBase):
    total: int
    limit: int
    offset: int
    items: list[HandStockDraftRead]


class StockControlExportRead(StockControlBase):
    run_id: int
    file_name: str
    content_type: str
    content_base64: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class StockControlTemplateRead(StockControlBase):
    file_name: str
    content_type: str = "text/csv; charset=utf-8"
    content: str


class StockControlOverviewRead(StockControlBase):
    run: StockControlRunRead
    summary: dict[str, Any] = Field(default_factory=dict)
    region_summary: dict[str, Any] = Field(default_factory=dict)
    movement_summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
