from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class LogisticsPeriod(BaseModel):
    date_from: date
    date_to: date


class LogisticsKpis(BaseModel):
    orders_qty: float = 0
    sales_qty: float = 0
    revenue: float = 0
    for_pay: float = 0
    logistics_cost: float = 0
    storage_cost: float = 0
    acceptance_cost: float = 0
    return_logistics_cost: float = 0
    missed_orders_qty: float = 0
    missed_revenue: float = 0
    cancelled_orders_qty: float = 0
    cancelled_revenue: float = 0
    stock_units: float = 0
    in_way_to_client: float = 0
    in_way_from_client: float = 0
    active_warehouses: int = 0
    risky_warehouses: int = 0
    available_acceptance_slots: int = 0
    avg_logistics_per_order: float | None = None
    logistics_share_percent: float | None = None
    buyout_percent: float | None = None
    margin_percent: float | None = None
    paid_storage_detail_cost: float = 0
    paid_storage_detail_rows: int = 0
    acceptance_detail_cost: float = 0
    acceptance_detail_rows: int = 0
    transit_route_count: int = 0
    seller_warehouse_count: int = 0
    seller_stock_units: float = 0


class LogisticsWarehouseRow(BaseModel):
    warehouse_id: int | None = None
    warehouse_name: str
    region_name: str | None = None
    stock_units: float = 0
    in_way_to_client: float = 0
    in_way_from_client: float = 0
    orders_qty: float = 0
    sales_qty: float = 0
    revenue: float = 0
    for_pay: float = 0
    revenue_source: str = "sales"
    finance_rows: int = 0
    logistics_cost: float = 0
    storage_cost: float = 0
    acceptance_cost: float = 0
    return_logistics_cost: float = 0
    cancelled_orders_qty: float = 0
    cancelled_revenue: float = 0
    missed_orders_qty: float = 0
    missed_revenue: float = 0
    buyout_percent: float | None = None
    logistics_share_percent: float | None = None
    margin_percent: float | None = None
    turnover_days: float | None = None
    acceptance_coefficient: str | None = None
    acceptance_status: str = "unknown"
    allow_unload: bool | None = None
    acceptance_next_available_at: date | None = None
    acceptance_box_type_id: int | None = None
    box_type_ids: list[int] = Field(default_factory=list)
    delivery_base: float | None = None
    delivery_liter: float | None = None
    storage_base: float | None = None
    region_sales_qty: float = 0
    region_sales_amount: float = 0
    region_sales_share_percent: float | None = None
    supply_count: int = 0
    open_supply_count: int = 0
    risk_level: str = "ok"
    recommendation: str | None = None


class LogisticsSupplyRow(BaseModel):
    supply_id: int
    preorder_id: int | None = None
    warehouse_name: str | None = None
    actual_warehouse_name: str | None = None
    status_id: int | None = None
    status_label: str
    supply_date: datetime | None = None
    fact_date: datetime | None = None
    planned_qty: float = 0
    accepted_qty: float = 0
    gap_qty: float = 0
    box_type_id: int | None = None
    last_enriched_at: datetime | None = None


class LogisticsDataSourceStatus(BaseModel):
    key: str
    label: str
    status: str
    rows: int = 0
    latest_at: datetime | date | None = None
    note: str | None = None


class LogisticsApiCapability(BaseModel):
    key: str
    label: str
    endpoint: str
    token_category: str
    status: str
    note: str | None = None


class LogisticsRecommendation(BaseModel):
    severity: str
    title: str
    detail: str
    action: str
    source: str | None = None


class LogisticsTaskRow(BaseModel):
    id: str
    task_type: str
    severity: str
    title: str
    warehouse_name: str | None = None
    region_name: str | None = None
    detail: str
    action: str
    forecast_days: int | None = None
    stockout_in_days: float | None = None
    recommended_supply_qty: float = 0
    potential_orders_qty: float = 0
    potential_revenue: float = 0
    expected_net_effect: float = 0
    logistics_share_percent: float | None = None
    buyout_percent: float | None = None
    confidence: str = "medium"
    tags: list[str] = Field(default_factory=list)


class LogisticsProductRow(BaseModel):
    id: str
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    title: str | None = None
    brand: str | None = None
    subject_name: str | None = None
    warehouse_name: str
    region_name: str | None = None
    stock_units: float = 0
    in_way_to_client: float = 0
    in_way_from_client: float = 0
    orders_qty: float = 0
    sales_qty: float = 0
    cancelled_orders_qty: float = 0
    cancelled_revenue: float = 0
    revenue: float = 0
    for_pay: float = 0
    revenue_source: str = "sales"
    finance_rows: int = 0
    logistics_cost: float = 0
    storage_cost: float = 0
    acceptance_cost: float = 0
    return_logistics_cost: float = 0
    buyout_percent: float | None = None
    logistics_share_percent: float | None = None
    margin_percent: float | None = None
    avg_daily_sales: float = 0
    turnover_days: float | None = None
    recommended_supply_14: float = 0
    recommended_supply_30: float = 0
    potential_orders_qty: float = 0
    potential_revenue: float = 0
    expected_net_effect: float = 0
    risk_level: str = "ok"
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)


class LogisticsRegionalShipmentRow(BaseModel):
    id: str
    warehouse_name: str
    region_name: str | None = None
    recommended_supply_qty: float = 0
    potential_orders_qty: float = 0
    potential_revenue: float = 0
    region_sales_qty: float = 0
    region_sales_amount: float = 0
    region_sales_share_percent: float | None = None
    expected_logistics_cost: float = 0
    expected_net_effect: float = 0
    current_stock_units: float = 0
    turnover_days: float | None = None
    acceptance_status: str = "unknown"
    acceptance_coefficient: str | None = None
    priority: str = "planned"
    reason: str
    tags: list[str] = Field(default_factory=list)


class LogisticsWarehouseControlRow(BaseModel):
    warehouse_name: str
    region_name: str | None = None
    mode: str = "active"
    recommended_mode: str = "active"
    task_count: int = 0
    potential_revenue: float = 0
    stock_units: float = 0
    turnover_days: float | None = None
    acceptance_status: str = "unknown"
    logistics_share_percent: float | None = None
    reason: str | None = None


class LogisticsPaidStorageDetailRow(BaseModel):
    id: int
    report_date: date | None = None
    warehouse_name: str | None = None
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    title: str | None = None
    brand: str | None = None
    subject_name: str | None = None
    quantity: float = 0
    amount: float = 0
    amount_per_unit: float | None = None
    share_percent: float | None = None
    task_id: str | None = None
    source_row_key: str | None = None


class LogisticsAcceptanceDetailRow(BaseModel):
    id: int
    operation_date: date | None = None
    warehouse_name: str | None = None
    operation_name: str | None = None
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    title: str | None = None
    brand: str | None = None
    subject_name: str | None = None
    quantity: float = 0
    amount: float = 0
    amount_per_unit: float | None = None
    share_percent: float | None = None
    task_id: str | None = None
    source_row_key: str | None = None


class LogisticsTransitTariffRow(BaseModel):
    id: int
    collected_at: datetime
    route_label: str | None = None
    source_warehouse_id: int | None = None
    source_warehouse_name: str | None = None
    transit_warehouse_id: int | None = None
    transit_warehouse_name: str | None = None
    destination_warehouse_id: int | None = None
    destination_warehouse_name: str | None = None
    box_type_id: int | None = None
    coefficient: str | None = None
    delivery_base: float | None = None
    delivery_liter: float | None = None
    amount: float | None = None
    currency: str | None = None
    transit_time_days: float | None = None
    score: float | None = None


class LogisticsSellerWarehouseRow(BaseModel):
    id: int
    warehouse_id: int
    name: str | None = None
    office_id: int | None = None
    delivery_type: str | None = None
    delivery_type_label: str | None = None
    cargo_type: str | None = None
    address: str | None = None
    is_active: bool | None = None
    stock_rows: int = 0
    stock_units: float = 0
    latest_stock_at: datetime | None = None


class LogisticsShipmentScopeOption(BaseModel):
    key: str
    label: str
    scope_type: str
    region_name: str | None = None
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    enabled_by_default: bool = True
    selectable: bool = True
    reason: str | None = None
    risk_level: str = "ok"
    acceptance_status: str | None = None
    stock_units: float = 0
    current_stock_qty: float = 0
    target_stock_qty: float = 0
    delta_qty: float = 0
    shortage_qty: float = 0
    excess_qty: float = 0
    inbound_qty: float = 0
    outbound_qty: float = 0
    sales_qty: float = 0
    revenue: float = 0
    product_count: int = 0


class LogisticsShipmentMovementRow(BaseModel):
    id: int
    movement_type: str
    nm_id: int | None = None
    vendor_code: str | None = None
    barcode: str | None = None
    size_name: str | None = None
    donor_region: str | None = None
    donor_warehouse: str | None = None
    recipient_region: str | None = None
    recipient_warehouse: str | None = None
    quantity: float = 0
    priority: str = "P3"
    reason_code: str | None = None
    business_explanation: str | None = None
    confidence: str = "medium"
    status: str = "new"


class LogisticsShipmentFormulaRead(BaseModel):
    source: str = "logistics"
    title: str = "Логистическая формула"
    detail: str
    latest_run_id: int | None = None
    latest_run_type: str | None = None
    latest_run_finished_at: datetime | None = None
    warning: str | None = None


class LogisticsShipmentPlanningRead(BaseModel):
    status: str = "fallback"
    formula: LogisticsShipmentFormulaRead
    regions: list[LogisticsShipmentScopeOption] = Field(default_factory=list)
    warehouses: list[LogisticsShipmentScopeOption] = Field(default_factory=list)
    movements: list[LogisticsShipmentMovementRow] = Field(default_factory=list)
    excluded_regions: list[str] = Field(default_factory=list)
    source_run_id: int | None = None
    source_run_type: str | None = None
    source_run_finished_at: datetime | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class LogisticsOverviewRead(BaseModel):
    account_id: int
    period: LogisticsPeriod
    kpis: LogisticsKpis = Field(default_factory=LogisticsKpis)
    warehouses: list[LogisticsWarehouseRow] = Field(default_factory=list)
    supplies: list[LogisticsSupplyRow] = Field(default_factory=list)
    tasks: list[LogisticsTaskRow] = Field(default_factory=list)
    products: list[LogisticsProductRow] = Field(default_factory=list)
    regional_shipments: list[LogisticsRegionalShipmentRow] = Field(default_factory=list)
    warehouse_controls: list[LogisticsWarehouseControlRow] = Field(default_factory=list)
    paid_storage_details: list[LogisticsPaidStorageDetailRow] = Field(
        default_factory=list
    )
    acceptance_details: list[LogisticsAcceptanceDetailRow] = Field(default_factory=list)
    transit_tariffs: list[LogisticsTransitTariffRow] = Field(default_factory=list)
    seller_warehouses: list[LogisticsSellerWarehouseRow] = Field(default_factory=list)
    shipment_planning: LogisticsShipmentPlanningRead | None = None
    data_sources: list[LogisticsDataSourceStatus] = Field(default_factory=list)
    api_capabilities: list[LogisticsApiCapability] = Field(default_factory=list)
    recommendations: list[LogisticsRecommendation] = Field(default_factory=list)
    generated_at: datetime
