from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class CoreSKUListItem(BaseModel):
    id: int
    account_id: int
    nm_id: int | None
    vendor_code: str | None
    supplier_article: str | None
    barcode: str | None
    chrt_id: int | None
    size_id: int | None
    tech_size: str | None
    title: str | None
    brand: str | None
    subject_id: int | None
    subject_name: str | None
    is_active: bool
    status: str
    comment: str | None
    source_updated_at: datetime | None
    current_price: float | None
    current_discounted_price: float | None
    seller_discount: int | None
    club_discount: int | None
    latest_quantity: float | None
    latest_quantity_full: float | None
    latest_in_way_to_client: float | None
    latest_in_way_from_client: float | None
    latest_stock_snapshot_at: datetime | None
    latest_sale_date: date | None
    manual_cost_id: int | None
    cost_price: float | None
    seller_other_expense: float | None = None
    packaging_cost: float | None
    inbound_logistics_cost: float | None
    total_unit_cost: float | None
    supplier: str | None
    has_manual_cost: bool
    has_real_manual_cost: bool = False
    has_placeholder_cost: bool = False
    business_trusted: bool = False
    operational_trusted: bool = False
    cost_source: str | None = None
    cost_truth_level: str | None = None
    open_issue_count: int
    has_open_issues: bool
    last_30d_sales_qty: int
    last_30d_revenue: float | None


class CoreSKUDetail(BaseModel):
    sku: CoreSKUListItem
    recent_issue_codes: list[str]
    warehouses: list[str]
