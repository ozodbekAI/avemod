from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, computed_field


class ManualCostRead(BaseModel):
    id: int
    account_id: int
    upload_id: int | None
    sku_id: int | None
    vendor_code: str
    nm_id: int | None
    barcode: str | None
    tech_size: str | None
    unit_cost: float
    cost_price: float
    seller_other_expense: float | None = None
    packaging_cost: float | None = None
    inbound_logistics_cost: float | None = None
    supplier: str | None
    currency: str
    valid_from: date | None
    valid_to: date | None
    source_file_name: str | None
    uploaded_by_user_id: int | None
    uploaded_at: datetime | None
    match_rule: str | None
    cost_source: str | None
    is_ambiguous: bool
    is_placeholder: bool = False
    is_business_trusted: bool = True
    is_supplier_confirmed: bool = False
    supplier_confirmed_at: datetime | None = None
    supplier_confirmed_by_user_id: int | None = None
    comment: str | None

    model_config = {"from_attributes": True}

    @computed_field
    @property
    def total_unit_cost(self) -> float:
        seller_other_expense = self.seller_other_expense
        if seller_other_expense is None:
            seller_other_expense = float(
                (self.packaging_cost or 0) + (self.inbound_logistics_cost or 0)
            )
        return float((self.cost_price or 0) + seller_other_expense)

    @computed_field
    @property
    def cost_truth_level(self) -> str:
        normalized_supplier = str(self.supplier or "").strip().upper()
        normalized_source = str(self.cost_source or "").strip().lower()
        if self.is_ambiguous:
            return "ambiguous"
        if (
            self.is_placeholder
            or normalized_supplier == "AUTO_TEMPLATE"
            or normalized_source.startswith("placeholder")
        ):
            return "placeholder"
        if self.is_supplier_confirmed or normalized_source == "supplier_confirmed":
            return "supplier_confirmed"
        if normalized_source == "estimated_range":
            return "estimated_range"
        if (
            bool(self.is_business_trusted)
            or normalized_supplier == "OPERATOR_TRUSTED_COST"
            or normalized_source
            in {"operator_baseline", "operator_trusted_manual", "manual_upload"}
        ):
            return "operator_baseline"
        return "manual_untrusted"

    @computed_field
    @property
    def cost_truth_label(self) -> str:
        mapping = {
            "missing": "Нет себестоимости",
            "placeholder": "Шаблон / тестовые данные",
            "supplier_confirmed": "Подтверждено поставщиком",
            "estimated_range": "Оценочный диапазон",
            "operator_baseline": "Принято оператором",
            "manual_untrusted": "Не подтверждено",
            "ambiguous": "Неоднозначная привязка",
        }
        return mapping.get(self.cost_truth_level, "Неизвестно")


class ManualCostUploadRead(BaseModel):
    id: int
    account_id: int
    filename: str
    content_type: str | None
    rows_total: int
    rows_valid: int
    rows_invalid: int
    status: str
    error_text: str | None
    imported_at: datetime | None
    summary: dict

    model_config = {"from_attributes": True}


class CostUploadResponse(BaseModel):
    upload: ManualCostUploadRead
    preview_rows: list[dict]

    @computed_field
    @property
    def rows_total(self) -> int:
        return self.upload.rows_total

    @computed_field
    @property
    def rows_valid(self) -> int:
        return self.upload.rows_valid

    @computed_field
    @property
    def rows_invalid(self) -> int:
        return self.upload.rows_invalid

    @computed_field
    @property
    def rows_committed(self) -> int:
        return int((self.upload.summary or {}).get("rowsCommitted") or 0)


class ManualCostUpdateRequest(BaseModel):
    cost_price: Decimal | None = None
    seller_other_expense: Decimal | None = None
    packaging_cost: Decimal | None = None
    inbound_logistics_cost: Decimal | None = None
    supplier: str | None = None
    currency: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    comment: str | None = None
    cost_source: str | None = None
    is_placeholder: bool | None = None
    is_business_trusted: bool | None = None
    is_supplier_confirmed: bool | None = None


class ManualCostInlineSaveRow(BaseModel):
    cost_id: int | None = None
    sku_id: int | None = None
    cost_price: Decimal
    seller_other_expense: Decimal | None = None
    supplier: str | None = None
    currency: str | None = None
    valid_from: date | None = None
    comment: str | None = None
    is_supplier_confirmed: bool | None = None


class ManualCostInlineSaveRequest(BaseModel):
    account_id: int
    rows: list[ManualCostInlineSaveRow] = Field(min_length=1, max_length=200)


class ManualCostInlineSaveResponse(BaseModel):
    rows: list[ManualCostRead]
    changed_count: int
    recalculated: bool = True


class ManualCostSupplierConfirmRequest(BaseModel):
    comment: str | None = None


class ManualCostConfirmResponse(BaseModel):
    upload: ManualCostUploadRead
    rows_committed: int
    next_step: dict | None = None


class ManualCostRelinkResponse(BaseModel):
    checked_count: int
    relinked_count: int
    ambiguous_count: int
    unresolved_count: int


class ManualCostTemplateRow(BaseModel):
    vendorCode: str | None
    nmId: int | None
    barcode: str | None
    techSize: str | None
    cost_price: str
    seller_other_expense: str
    supplier: str
    valid_from: str
    comment: str


class MissingCostSummary(BaseModel):
    missing_sku_count: int
    affected_revenue: float
    revenue_cost_coverage_percent: float | None = None


class MissingCostItem(BaseModel):
    sku_id: int
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    tech_size: str | None = None
    product_title: str | None = None
    affected_revenue: float = 0.0
    recommended_action: str = "Заполнить себестоимость"


class MissingCostsResponse(BaseModel):
    total: int
    limit: int
    offset: int
    summary: MissingCostSummary
    items: list[MissingCostItem]
