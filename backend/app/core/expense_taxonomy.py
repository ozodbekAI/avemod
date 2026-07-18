from __future__ import annotations

from decimal import Decimal
from typing import Any


EXPENSE_CATEGORY_WB_COMMISSION = "wb_commission"
EXPENSE_CATEGORY_PAYMENT_PROCESSING = "payment_processing"
EXPENSE_CATEGORY_PVZ_REWARD = "pvz_reward"
EXPENSE_CATEGORY_WB_LOGISTICS = "wb_logistics"
EXPENSE_CATEGORY_WB_LOGISTICS_REBILL = "wb_logistics_rebill"
EXPENSE_CATEGORY_STORAGE = "storage"
EXPENSE_CATEGORY_ACCEPTANCE = "acceptance"
EXPENSE_CATEGORY_PENALTY = "penalty"
EXPENSE_CATEGORY_DEDUCTION = "deduction"
EXPENSE_CATEGORY_MARKETING_DEDUCTION = "marketing_deduction"
EXPENSE_CATEGORY_LOYALTY = "loyalty"
EXPENSE_CATEGORY_ADDITIONAL_PAYMENT = "additional_payment"
EXPENSE_CATEGORY_SELLER_COGS = "seller_cogs"
EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE = "seller_other_expense"
EXPENSE_CATEGORY_ADS_OPERATIONAL = "ads_operational"
EXPENSE_CATEGORY_UNCLASSIFIED = "unclassified"

ALL_EXPENSE_CATEGORIES = (
    EXPENSE_CATEGORY_WB_COMMISSION,
    EXPENSE_CATEGORY_PAYMENT_PROCESSING,
    EXPENSE_CATEGORY_PVZ_REWARD,
    EXPENSE_CATEGORY_WB_LOGISTICS,
    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
    EXPENSE_CATEGORY_STORAGE,
    EXPENSE_CATEGORY_ACCEPTANCE,
    EXPENSE_CATEGORY_PENALTY,
    EXPENSE_CATEGORY_DEDUCTION,
    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
    EXPENSE_CATEGORY_LOYALTY,
    EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
    EXPENSE_CATEGORY_SELLER_COGS,
    EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE,
    EXPENSE_CATEGORY_ADS_OPERATIONAL,
    EXPENSE_CATEGORY_UNCLASSIFIED,
)

WB_EXPENSE_OUTPUT_FIELDS = (
    EXPENSE_CATEGORY_WB_COMMISSION,
    EXPENSE_CATEGORY_PAYMENT_PROCESSING,
    EXPENSE_CATEGORY_PVZ_REWARD,
    EXPENSE_CATEGORY_WB_LOGISTICS,
    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
    EXPENSE_CATEGORY_STORAGE,
    EXPENSE_CATEGORY_ACCEPTANCE,
    EXPENSE_CATEGORY_PENALTY,
    EXPENSE_CATEGORY_DEDUCTION,
    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
    EXPENSE_CATEGORY_LOYALTY,
    EXPENSE_CATEGORY_UNCLASSIFIED,
)

EXPENSE_SOURCE_FINANCE_REPORT = "finance_report"
EXPENSE_SOURCE_ADS_API = "ads_api"
EXPENSE_SOURCE_MANUAL_COST = "manual_cost"
EXPENSE_SOURCE_COMPUTED = "computed"

EXPENSE_SIGN_EXPENSE = "expense"
EXPENSE_SIGN_INCOME = "income"

AD_SPEND_SOURCE_FINANCE = "finance_report"
AD_SPEND_SOURCE_OPERATIONAL = "ads_api"
AD_SPEND_SOURCE_NONE = "none"

EXPENSE_DATA_QUALITY_COMPLETE = "complete"
EXPENSE_DATA_QUALITY_PARTIAL = "partial"
EXPENSE_DATA_QUALITY_UNCLASSIFIED_PRESENT = "unclassified_present"
EXPENSE_DATA_QUALITY_AD_DOUBLE_COUNT_RISK = "ad_double_count_risk"

DEFAULT_EXPENSE_CURRENCY = "RUB"


def decimal_or_zero(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def positive_expense_amount(value: Any) -> Decimal:
    amount = decimal_or_zero(value)
    return amount if amount > 0 else Decimal("0")


def positive_income_amount(value: Any) -> Decimal:
    amount = decimal_or_zero(value)
    return abs(amount) if amount < 0 else Decimal("0")


def field_value(source: Any, field: str) -> Any:
    if isinstance(source, dict):
        return source.get(field)
    source_dict = getattr(source, "__dict__", None)
    if isinstance(source_dict, dict) and field in source_dict:
        return source_dict.get(field)
    descriptor = getattr(type(source), field, None)
    if isinstance(descriptor, property):
        return None
    return getattr(source, field, None)


def row_decimal(row: Any, field: str) -> Decimal:
    return decimal_or_zero(field_value(row, field))


def revenue_final(source: Any) -> Decimal:
    explicit_value = row_decimal(source, "revenue_final")
    if explicit_value != 0:
        return explicit_value
    if getattr(source, "final_revenue", None) is not None:
        return row_decimal(source, "final_revenue")
    if getattr(source, "realized_revenue", None) is not None:
        return row_decimal(source, "realized_revenue")
    finance_value = getattr(source, "finance_revenue", None)
    if finance_value not in (None, ""):
        return row_decimal(source, "finance_revenue")
    return row_decimal(source, "operational_revenue")


def additional_income(source: Any) -> Decimal:
    explicit_value = row_decimal(source, "additional_income")
    if explicit_value > 0:
        return explicit_value
    raw_value = getattr(source, EXPENSE_CATEGORY_ADDITIONAL_PAYMENT, None)
    if raw_value in (None, ""):
        raw_value = getattr(source, "additional_payments", None)
    amount = decimal_or_zero(raw_value)
    if amount < 0:
        return abs(amount)
    return amount if amount > 0 else Decimal("0")


def ad_spend_operational(source: Any) -> Decimal:
    explicit_value = row_decimal(source, "ad_spend_operational")
    if explicit_value > 0:
        return explicit_value
    source_value = row_decimal(source, "source_ad_spend")
    if source_value > 0:
        return source_value
    ad_source = str(getattr(source, "ad_spend_source", "") or "")
    ad_final = row_decimal(source, "ad_spend_final")
    ad_legacy = row_decimal(source, "ad_spend")
    if ad_source == AD_SPEND_SOURCE_OPERATIONAL:
        return ad_final if ad_final > 0 else ad_legacy
    return Decimal("0")


def ad_spend_finance(source: Any) -> Decimal:
    explicit_value = row_decimal(source, "ad_spend_finance")
    if explicit_value > 0:
        return explicit_value
    marketing = row_decimal(source, EXPENSE_CATEGORY_MARKETING_DEDUCTION)
    return marketing if marketing > 0 else Decimal("0")


def ad_spend_source(source: Any) -> str:
    finance_value = ad_spend_finance(source)
    if finance_value > 0:
        return AD_SPEND_SOURCE_FINANCE
    operational_value = ad_spend_operational(source)
    if (
        operational_value > 0
        or row_decimal(source, "ad_spend_final") > 0
        or row_decimal(source, "ad_spend") > 0
    ):
        return AD_SPEND_SOURCE_OPERATIONAL
    return AD_SPEND_SOURCE_NONE


def ad_spend_final(source: Any) -> Decimal:
    finance_value = ad_spend_finance(source)
    if finance_value > 0:
        return finance_value
    explicit_final = row_decimal(source, "ad_spend_final")
    if explicit_final > 0:
        return explicit_final
    operational_value = ad_spend_operational(source)
    if operational_value > 0:
        return operational_value
    return row_decimal(source, "ad_spend")


def normalized_wb_expenses_total(source: Any) -> Decimal:
    return (
        row_decimal(source, EXPENSE_CATEGORY_WB_COMMISSION)
        + row_decimal(source, EXPENSE_CATEGORY_PAYMENT_PROCESSING)
        + row_decimal(source, EXPENSE_CATEGORY_PVZ_REWARD)
        + row_decimal(source, EXPENSE_CATEGORY_WB_LOGISTICS)
        + row_decimal(source, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL)
        + row_decimal(source, EXPENSE_CATEGORY_STORAGE)
        + row_decimal(source, EXPENSE_CATEGORY_ACCEPTANCE)
        + row_decimal(source, EXPENSE_CATEGORY_PENALTY)
        + row_decimal(source, EXPENSE_CATEGORY_DEDUCTION)
        + row_decimal(source, EXPENSE_CATEGORY_LOYALTY)
        + row_decimal(source, "other_wb_expenses")
    )


def total_seller_expenses(source: Any) -> Decimal:
    return row_decimal(source, EXPENSE_CATEGORY_SELLER_COGS) + row_decimal(
        source, EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE
    )


def total_seller_costs(source: Any) -> Decimal:
    explicit_value = row_decimal(source, "total_seller_costs")
    if explicit_value != 0:
        return explicit_value
    explicit_expenses = row_decimal(source, "total_seller_expenses")
    if explicit_expenses != 0:
        return explicit_expenses
    estimated_cogs = row_decimal(source, "estimated_cogs")
    if estimated_cogs != 0 and (
        getattr(source, EXPENSE_CATEGORY_SELLER_COGS, None) in (None, "")
        and getattr(source, EXPENSE_CATEGORY_SELLER_OTHER_EXPENSE, None) in (None, "")
    ):
        return estimated_cogs
    return total_seller_expenses(source)


def extra_ad_spend_not_in_wb_expenses(source: Any) -> Decimal:
    return ad_spend_final(source)


def expense_data_quality(source: Any) -> str:
    explicit_final = row_decimal(source, "ad_spend_final")
    raw_legacy_ad = row_decimal(source, "ad_spend")
    finance_value = ad_spend_finance(source)
    operational_value = ad_spend_operational(source)
    raw_final_reference = explicit_final if explicit_final > 0 else raw_legacy_ad
    if (
        finance_value > 0
        and operational_value > 0
        and (
            raw_final_reference > finance_value + Decimal("0.01")
            or str(getattr(source, "ad_spend_source", "") or "")
            == AD_SPEND_SOURCE_OPERATIONAL
        )
    ):
        return EXPENSE_DATA_QUALITY_AD_DOUBLE_COUNT_RISK
    other_wb_expenses = row_decimal(source, "other_wb_expenses")
    unclassified = row_decimal(source, EXPENSE_CATEGORY_UNCLASSIFIED)
    if other_wb_expenses > 0 or unclassified > 0:
        return EXPENSE_DATA_QUALITY_UNCLASSIFIED_PRESENT
    if (
        str(getattr(source, "final_revenue_source", "") or "") == "finance"
        or int(getattr(source, "finance_rows", 0) or 0) > 0
        or row_decimal(source, "finance_revenue") > 0
    ):
        return EXPENSE_DATA_QUALITY_COMPLETE
    return EXPENSE_DATA_QUALITY_PARTIAL


def merge_expense_data_quality(statuses: list[str]) -> str:
    priority = {
        EXPENSE_DATA_QUALITY_COMPLETE: 0,
        EXPENSE_DATA_QUALITY_PARTIAL: 1,
        EXPENSE_DATA_QUALITY_UNCLASSIFIED_PRESENT: 2,
        EXPENSE_DATA_QUALITY_AD_DOUBLE_COUNT_RISK: 3,
    }
    if not statuses:
        return EXPENSE_DATA_QUALITY_PARTIAL
    return max(statuses, key=lambda item: priority.get(item, 0))


def net_profit_after_all_expenses(
    source: Any, *, revenue_field: str = "final_revenue"
) -> Decimal:
    revenue_value = (
        revenue_final(source)
        if revenue_field == "final_revenue"
        else row_decimal(source, revenue_field)
    )
    return (
        revenue_value
        + additional_income(source)
        - normalized_wb_expenses_total(source)
        - total_seller_costs(source)
        - ad_spend_final(source)
    )


def legacy_expense_fields(source: Any) -> dict[str, Decimal]:
    return {
        "commission": row_decimal(source, EXPENSE_CATEGORY_WB_COMMISSION),
        "acquiring_fee": row_decimal(source, EXPENSE_CATEGORY_PAYMENT_PROCESSING),
        "logistics": row_decimal(source, EXPENSE_CATEGORY_WB_LOGISTICS)
        + row_decimal(source, EXPENSE_CATEGORY_WB_LOGISTICS_REBILL),
        "paid_acceptance": row_decimal(source, EXPENSE_CATEGORY_ACCEPTANCE),
        "storage": row_decimal(source, EXPENSE_CATEGORY_STORAGE),
        "penalties": row_decimal(source, EXPENSE_CATEGORY_PENALTY),
        "deductions": row_decimal(source, EXPENSE_CATEGORY_DEDUCTION)
        + row_decimal(source, EXPENSE_CATEGORY_LOYALTY)
        + row_decimal(source, "other_wb_expenses"),
        "additional_payments": additional_income(source),
    }
