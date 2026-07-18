from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class RealizationReportRead(BaseModel):
    id: int
    account_id: int
    report_id: int | None
    report_name: str | None
    period: str | None
    date_from: date | None
    date_to: date | None
    create_date: date | None
    currency: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class RealizationReportRowRead(BaseModel):
    id: int
    account_id: int
    rrd_id: int
    report_id: int | None
    rr_date: date | None
    doc_type_name: str | None
    srid: str | None
    order_id: int | None
    nm_id: int | None
    vendor_code: str | None
    barcode: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    office_name: str | None
    seller_oper_name: str | None
    bonus_type_name: str | None
    quantity: int | None
    retail_amount: float | None
    retail_price: float | None
    retail_price_with_disc: float | None
    delivery_amount: float | None
    delivery_service: float | None
    paid_acceptance: float | None
    additional_payment: float | None
    rebill_logistic_cost: float | None
    return_amount: float | None
    for_pay: float | None
    ppvz_sales_commission: float | None
    acquiring_fee: float | None
    paid_storage: float | None
    penalty: float | None
    deduction: float | None

    model_config = {"from_attributes": True}


class FinanceReportRowsSummary(BaseModel):
    rows_count: int
    sum_retail_amount: float
    sum_for_pay: float
    sum_logistics: float
    sum_storage: float
    sum_paid_acceptance: float
    sum_penalty: float
    sum_deduction: float
    sum_additional_payment: float


class FinanceReportRowsPage(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[RealizationReportRowRead]
    summary: FinanceReportRowsSummary | None = None


class BalanceSnapshotRead(BaseModel):
    id: int
    account_id: int
    snapshot_at: datetime
    currency: str | None
    current: float | None
    for_withdraw: float | None

    model_config = {"from_attributes": True}
