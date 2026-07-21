from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.current_state import orders_current_subquery, sales_current_subquery
from app.core.manual_cost_math import (
    manual_cost_price,
    manual_cost_seller_other_expense,
    manual_cost_total_unit_cost,
)
from app.core.expense_taxonomy import (
    AD_SPEND_SOURCE_FINANCE,
    AD_SPEND_SOURCE_NONE,
    AD_SPEND_SOURCE_OPERATIONAL,
    ALL_EXPENSE_CATEGORIES,
    DEFAULT_EXPENSE_CURRENCY,
    EXPENSE_CATEGORY_ACCEPTANCE,
    EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
    EXPENSE_CATEGORY_DEDUCTION,
    EXPENSE_CATEGORY_LOYALTY,
    EXPENSE_CATEGORY_MARKETING_DEDUCTION,
    EXPENSE_CATEGORY_PAYMENT_PROCESSING,
    EXPENSE_CATEGORY_PENALTY,
    EXPENSE_CATEGORY_PVZ_REWARD,
    EXPENSE_CATEGORY_STORAGE,
    EXPENSE_CATEGORY_UNCLASSIFIED,
    EXPENSE_CATEGORY_WB_COMMISSION,
    EXPENSE_CATEGORY_WB_LOGISTICS,
    EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
    EXPENSE_SIGN_EXPENSE,
    EXPENSE_SIGN_INCOME,
    EXPENSE_SOURCE_FINANCE_REPORT,
    additional_income as expense_additional_income,
    expense_data_quality as compute_expense_data_quality,
    extra_ad_spend_not_in_wb_expenses,
    legacy_expense_fields,
    net_profit_after_all_expenses,
    normalized_wb_expenses_total,
    row_decimal,
    total_seller_costs,
    total_seller_expenses,
)
from app.core.issue_refs import extract_issue_refs
from app.core.pagination import Page
from app.core.stock_fallback import stock_snapshot_on_or_before
from app.core.time import utcnow
from app.models.ads import WBAdStatsDaily
from app.models.analytics import WBCardFunnelDaily
from app.models.accounts import WBAccount
from app.models.data_quality import DataQualityIssue
from app.models.finance import WBRealizationReport, WBRealizationReportRow
from app.models.manual_costs import ManualCost
from app.models.marts import (
    MartAccountExpenseDaily,
    MartExpenseDaily,
    MartFinanceReconciliation,
    MartReconciliationDaily,
    MartSKUDaily,
    MartStockDaily,
)
from app.models.prices import WBPrice
from app.models.product_cards import CoreSKU
from app.models.stocks import WBStockSnapshot, WBStockSnapshotRow
from app.repositories.manual_costs import ManualCostRepository
from app.repositories.marts import (
    MartAccountExpenseDailyRepository,
    MartExpenseDailyRepository,
    MartFinanceReconciliationRepository,
    MartReconciliationDailyRepository,
    MartSKUDailyRepository,
    MartStockDailyRepository,
)
from app.schemas.marts import (
    MartBusinessDailyRead,
    MartReconciliationDailyRead,
    MartSKUDailyRead,
)
from app.services.dashboard import DashboardService
from app.services.trust import (
    COST_TRUST_POLICY_OPERATOR_BASELINE,
    cost_truth_level_from_cost,
    effective_cost_is_business_trusted,
    is_placeholder_manual_cost,
    is_supplier_confirmed_manual_cost,
)


class MartService:
    DEFAULT_FINANCE_TIMEZONE = "Europe/Moscow"
    MARKETING_DEDUCTION_KEYWORDS = (
        "wb продвиж",
        "продвижение",
        "promotion",
        "оказание услуг",
    )
    KNOWN_FINANCE_PAYLOAD_KEYS = {
        "deliveryservice",
        "rebilllogisticcost",
        "paidstorage",
        "paidacceptance",
        "deduction",
        "penalty",
        "acquiringfee",
        "ppvzreward",
        "ppvzsalescommission",
        "vw",
        "vwnds",
        "additionalpayment",
        "cashbackamount",
        "cashbackdiscount",
        "cashbackcommissionchange",
        "rrdid",
        "rrd_id",
        "rrdate",
        "sale_dt",
        "saledt",
        "orderid",
        "srid",
        "nmid",
        "barcode",
        "vendorcode",
        "supplierarticle",
        "subjectname",
        "doctypename",
        "retailamount",
        "retailprice",
        "retailpricewithdisc",
        "deliveryamount",
        "returnamount",
        "forpay",
        "quantity",
        "office_name",
        "selleropername",
        "bonustypename",
        "currency",
    }
    STRONG_TECHNICAL_FINANCE_PAYLOAD_KEY_PARTS = {
        "percent",
        "prc",
        "coefficient",
        "coeff",
        "coef",
        "kvw",
        "spp",
    }
    TECHNICAL_FINANCE_PAYLOAD_KEY_EXACT = {
        "shkid",
        "reportid",
        "giid",
        "ppvzofficeid",
        "officeid",
    }
    TECHNICAL_FINANCE_PAYLOAD_KEY_PARTS = {
        "office",
        "report",
        "doctype",
        "date",
        "currency",
        "quantity",
        "qty",
        "count",
        "status",
        "subject",
        "supplierarticle",
        "barcode",
        "nmid",
        "nmid",
        "srid",
        "order",
    }
    MONEY_LIKE_FINANCE_PAYLOAD_KEY_PARTS = {
        "amount",
        "sum",
        "cost",
        "price",
        "fee",
        "reward",
        "commission",
        "logistic",
        "storage",
        "acceptance",
        "deduction",
        "penalty",
        "payment",
        "service",
        "charge",
        "rebill",
        "cashback",
        "loyalty",
        "expense",
        "income",
    }

    def __init__(self) -> None:
        self.sku_repo = MartSKUDailyRepository()
        self.stock_repo = MartStockDailyRepository()
        self.finance_repo = MartFinanceReconciliationRepository()
        self.account_expense_repo = MartAccountExpenseDailyRepository()
        self.expense_repo = MartExpenseDailyRepository()
        self.reconciliation_daily_repo = MartReconciliationDailyRepository()
        self.cost_repo = ManualCostRepository()
        self.dashboard = DashboardService()

    @staticmethod
    def _decimal(value: object) -> Decimal:
        return Decimal(str(value or 0))

    @staticmethod
    def _row_date(value: datetime | None, fallback: datetime | None) -> date | None:
        if value is not None:
            return value.date()
        if fallback is not None:
            return fallback.date()
        return None

    @staticmethod
    def _timezone(timezone_name: str | None = None) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name or MartService.DEFAULT_FINANCE_TIMEZONE)
        except ZoneInfoNotFoundError:
            return ZoneInfo(MartService.DEFAULT_FINANCE_TIMEZONE)

    @classmethod
    def _local_datetime_date(
        cls, value: datetime | None, timezone_name: str | None = None
    ) -> date | None:
        if value is None:
            return None
        if value.tzinfo is not None and value.utcoffset() is not None:
            return value.astimezone(cls._timezone(timezone_name)).date()
        return value.date()

    @classmethod
    def _finance_row_date(
        cls, row: WBRealizationReportRow, *, timezone_name: str | None = None
    ) -> date | None:
        if row.sale_dt is not None:
            return cls._local_datetime_date(row.sale_dt, timezone_name=timezone_name)
        if row.rr_date is not None:
            return row.rr_date
        return None

    @staticmethod
    def _payload_text(payload: dict[str, Any] | None, *keys: str) -> str | None:
        if not isinstance(payload, dict):
            return None
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    @classmethod
    def _finance_row_barcode(cls, row: WBRealizationReportRow) -> str | None:
        if row.barcode not in (None, ""):
            return str(row.barcode)
        return cls._payload_text(getattr(row, "payload", None), "barcode", "sku")

    @staticmethod
    def _finance_sale_date_expr(*, timezone_name: str | None = None) -> Any:
        return func.date(
            func.timezone(
                timezone_name or MartService.DEFAULT_FINANCE_TIMEZONE,
                WBRealizationReportRow.sale_dt,
            )
        )

    @classmethod
    def _finance_stat_date_filter(
        cls, *, date_from: date, date_to: date, timezone_name: str | None = None
    ) -> Any:
        sale_date_expr = cls._finance_sale_date_expr(timezone_name=timezone_name)
        return or_(
            and_(
                WBRealizationReportRow.sale_dt.is_not(None),
                sale_date_expr >= date_from,
                sale_date_expr <= date_to,
            ),
            and_(
                WBRealizationReportRow.sale_dt.is_(None),
                WBRealizationReportRow.rr_date.is_not(None),
                WBRealizationReportRow.rr_date >= date_from,
                WBRealizationReportRow.rr_date <= date_to,
            ),
        )

    async def _account_timezone(self, session: AsyncSession, *, account_id: int) -> str:
        value = (
            await session.execute(
                select(WBAccount.timezone).where(WBAccount.id == account_id)
            )
        ).scalar_one_or_none()
        return str(value or self.DEFAULT_FINANCE_TIMEZONE)

    async def _finance_closed_through_date(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> date | None:
        return (
            await session.execute(
                select(func.max(WBRealizationReport.date_to)).where(
                    WBRealizationReport.account_id == account_id,
                    WBRealizationReport.date_to.is_not(None),
                    WBRealizationReport.date_to >= date_from,
                    WBRealizationReport.date_to <= date_to,
                )
            )
        ).scalar_one_or_none()

    @staticmethod
    def _should_use_operational_sale(
        stat_date: date, closed_finance_date_to: date | None
    ) -> bool:
        return closed_finance_date_to is None or stat_date > closed_finance_date_to

    @staticmethod
    def _finance_sign(row: WBRealizationReportRow) -> int:
        doc_type = (row.doc_type_name or "").lower()
        if "возврат" in doc_type or "return" in doc_type:
            return -1
        if (
            Decimal(str(row.retail_amount or 0)) < 0
            or Decimal(str(row.for_pay or 0)) < 0
        ):
            return -1
        return 1

    @staticmethod
    def _is_reconcilable_finance_row(row: WBRealizationReportRow) -> bool:
        if row.is_reconcilable is not None:
            return bool(row.is_reconcilable)
        doc_type = (row.doc_type_name or "").strip().lower()
        return doc_type in {"продажа", "возврат", "sale", "return"}

    @classmethod
    def _signed_finance_amount(cls, row: WBRealizationReportRow, value: Any) -> Decimal:
        amount = cls._decimal(value)
        if amount == 0:
            return amount
        # WB realization report can keep return amount positive while marking doc_type=Возврат.
        # Normalize returns to negative so finance/mart reconciliation is not inflated.
        if cls._finance_sign(row) < 0 and amount > 0:
            return -amount
        return amount

    @staticmethod
    def _finance_operation_type(row: WBRealizationReportRow) -> str:
        if row.operation_type:
            return row.operation_type
        doc_type = (row.doc_type_name or "").strip().lower()
        if doc_type in {"продажа", "sale"}:
            return "sale"
        if doc_type in {"возврат", "return"}:
            return "return"
        return "expense"

    @classmethod
    def _payload_value(cls, payload: dict[str, Any] | None, *keys: str) -> Decimal:
        if not isinstance(payload, dict):
            return Decimal("0")
        for key in keys:
            value = payload.get(key)
            if value not in (None, ""):
                try:
                    return cls._decimal(value)
                except Exception:
                    return Decimal("0")
        return Decimal("0")

    @staticmethod
    def _normalized_payload_key(payload_key: Any) -> str:
        return "".join(
            ch for ch in str(payload_key).lower() if ch.isalnum() or ch == "_"
        )

    @classmethod
    def _is_technical_finance_payload_key(cls, normalized_key: str) -> bool:
        if not normalized_key:
            return True
        if normalized_key in cls.TECHNICAL_FINANCE_PAYLOAD_KEY_EXACT:
            return True
        if any(
            part in normalized_key
            for part in cls.STRONG_TECHNICAL_FINANCE_PAYLOAD_KEY_PARTS
        ):
            return True
        has_money_signal = any(
            part in normalized_key for part in cls.MONEY_LIKE_FINANCE_PAYLOAD_KEY_PARTS
        )
        if (
            normalized_key.endswith("id") or normalized_key.endswith("_id")
        ) and not has_money_signal:
            return True
        if (
            any(
                part in normalized_key
                for part in cls.TECHNICAL_FINANCE_PAYLOAD_KEY_PARTS
            )
            and not has_money_signal
        ):
            return True
        return False

    @classmethod
    def _marketing_deduction_text(cls, row: WBRealizationReportRow) -> str:
        payload = dict(row.payload or {})
        return " ".join(
            part.strip().lower()
            for part in [
                row.seller_oper_name,
                row.bonus_type_name,
                payload.get("sellerOperName"),
                payload.get("seller_oper_name"),
                payload.get("bonusTypeName"),
                payload.get("bonus_type_name"),
            ]
            if isinstance(part, str) and part.strip()
        )

    @classmethod
    def _is_marketing_deduction(cls, row: WBRealizationReportRow) -> bool:
        haystack = cls._marketing_deduction_text(row)
        return any(keyword in haystack for keyword in cls.MARKETING_DEDUCTION_KEYWORDS)

    @classmethod
    def _empty_expense_totals(cls) -> dict[str, Decimal]:
        return {category: Decimal("0") for category in ALL_EXPENSE_CATEGORIES}

    @classmethod
    def _expense_entry(
        cls,
        row: WBRealizationReportRow,
        *,
        stat_date: date,
        expense_category: str,
        amount: Decimal,
        source_field: str,
        source_reason: str,
        sku_id: int | None,
        logistics_type: str | None = None,
        expense_source: str = EXPENSE_SOURCE_FINANCE_REPORT,
        amount_sign: str | None = None,
    ) -> dict[str, Any]:
        sign = amount_sign or (
            EXPENSE_SIGN_EXPENSE if amount >= 0 else EXPENSE_SIGN_INCOME
        )
        absolute_amount = abs(amount)
        return {
            "account_id": row.account_id,
            "stat_date": stat_date,
            "report_id": row.report_id,
            "rrd_id": row.rrd_id,
            "sku_id": sku_id,
            "nm_id": row.nm_id,
            "barcode": cls._finance_row_barcode(row),
            "srid": row.srid,
            "order_id": row.order_id,
            "expense_category": expense_category,
            "expense_source": expense_source,
            "amount": absolute_amount,
            "amount_sign": sign,
            "currency": row.currency or DEFAULT_EXPENSE_CURRENCY,
            "source_field": source_field,
            "source_reason": source_reason,
            "seller_oper_name": row.seller_oper_name,
            "bonus_type_name": row.bonus_type_name,
            "logistics_type": logistics_type,
            "is_allocated_to_sku": sku_id is not None,
            "allocation_method": "core_sku_match"
            if sku_id is not None
            else "unallocated",
            "raw_payload": dict(row.payload or {}),
        }

    @classmethod
    def _entry_signed_amount(cls, entry: dict[str, Any]) -> Decimal:
        amount = cls._decimal(entry.get("amount"))
        return amount if entry.get("amount_sign") == EXPENSE_SIGN_EXPENSE else -amount

    @classmethod
    def _finance_expense_details(
        cls,
        row: WBRealizationReportRow,
        *,
        sku_id: int | None = None,
        timezone_name: str | None = None,
    ) -> dict[str, Any]:
        stat_date = cls._finance_row_date(row, timezone_name=timezone_name)
        if stat_date is None:
            return {"entries": [], "totals": cls._empty_expense_totals(), "issues": []}

        payload = dict(row.payload or {})
        entries: list[dict[str, Any]] = []
        issue_specs: list[dict[str, Any]] = []

        def add(
            category: str,
            amount: Decimal,
            *,
            source_field: str,
            source_reason: str,
            logistics_type: str | None = None,
        ) -> None:
            if amount == 0:
                return
            entries.append(
                cls._expense_entry(
                    row,
                    stat_date=stat_date,
                    expense_category=category,
                    amount=amount,
                    source_field=source_field,
                    source_reason=source_reason,
                    sku_id=sku_id,
                    logistics_type=logistics_type,
                    amount_sign=(
                        EXPENSE_SIGN_INCOME
                        if category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                        and amount >= 0
                        else EXPENSE_SIGN_EXPENSE
                        if category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                        else None
                    ),
                )
            )

        add(
            EXPENSE_CATEGORY_WB_LOGISTICS,
            cls._decimal(row.delivery_service),
            source_field="delivery_service",
            source_reason="Услуги по доставке товара покупателю",
            logistics_type="delivery_service",
        )
        add(
            EXPENSE_CATEGORY_WB_LOGISTICS_REBILL,
            cls._decimal(row.rebill_logistic_cost),
            source_field="rebill_logistic_cost",
            source_reason="Возмещение издержек по перевозке/складским операциям",
            logistics_type="rebill_logistic_cost",
        )
        add(
            EXPENSE_CATEGORY_STORAGE,
            cls._decimal(row.paid_storage),
            source_field="paid_storage",
            source_reason="Хранение",
        )
        add(
            EXPENSE_CATEGORY_ACCEPTANCE,
            cls._decimal(row.paid_acceptance),
            source_field="paid_acceptance",
            source_reason="Операции на приемке",
        )
        add(
            EXPENSE_CATEGORY_PENALTY,
            cls._decimal(row.penalty),
            source_field="penalty",
            source_reason="Общая сумма штрафов",
        )
        deduction_category = (
            EXPENSE_CATEGORY_MARKETING_DEDUCTION
            if cls._is_marketing_deduction(row)
            else EXPENSE_CATEGORY_DEDUCTION
        )
        add(
            deduction_category,
            cls._decimal(row.deduction),
            source_field="deduction",
            source_reason="WB promotion deduction"
            if deduction_category == EXPENSE_CATEGORY_MARKETING_DEDUCTION
            else "Generic deduction",
        )
        add(
            EXPENSE_CATEGORY_PAYMENT_PROCESSING,
            cls._decimal(row.acquiring_fee),
            source_field="acquiring_fee",
            source_reason="Компенсация платежных услуг / эквайринг",
        )
        add(
            EXPENSE_CATEGORY_WB_COMMISSION,
            cls._decimal(row.ppvz_sales_commission),
            source_field="ppvz_sales_commission",
            source_reason="Вознаграждение WB",
        )
        add(
            EXPENSE_CATEGORY_WB_COMMISSION,
            cls._payload_value(payload, "vw", "VW"),
            source_field="payload.vw",
            source_reason="WB commission VW",
        )
        add(
            EXPENSE_CATEGORY_WB_COMMISSION,
            cls._payload_value(payload, "vwNds", "vw_nds", "VWNds"),
            source_field="payload.vwNds",
            source_reason="WB commission VW NDS",
        )
        add(
            EXPENSE_CATEGORY_PVZ_REWARD,
            cls._payload_value(payload, "ppvzReward", "ppvz_reward"),
            source_field="payload.ppvzReward",
            source_reason="Возмещение за выдачу и возврат товаров на ПВЗ",
        )
        add(
            EXPENSE_CATEGORY_ADDITIONAL_PAYMENT,
            cls._decimal(row.additional_payment),
            source_field="additional_payment",
            source_reason="Additional payment / positive adjustment",
        )
        add(
            EXPENSE_CATEGORY_LOYALTY,
            cls._payload_value(payload, "cashbackAmount", "cashback_amount"),
            source_field="payload.cashbackAmount",
            source_reason="Cashback amount",
        )
        add(
            EXPENSE_CATEGORY_LOYALTY,
            cls._payload_value(payload, "cashbackDiscount", "cashback_discount"),
            source_field="payload.cashbackDiscount",
            source_reason="Cashback discount",
        )
        add(
            EXPENSE_CATEGORY_LOYALTY,
            cls._payload_value(
                payload, "cashbackCommissionChange", "cashback_commission_change"
            ),
            source_field="payload.cashbackCommissionChange",
            source_reason="Cashback commission change",
        )

        for payload_key, payload_value in payload.items():
            if payload_value in (None, "", False):
                continue
            if not isinstance(payload_value, (int, float, Decimal)):
                continue
            normalized_key = cls._normalized_payload_key(payload_key)
            if normalized_key in cls.KNOWN_FINANCE_PAYLOAD_KEYS:
                continue
            if cls._is_technical_finance_payload_key(normalized_key):
                continue
            try:
                amount = cls._decimal(payload_value)
            except Exception:
                continue
            if amount == 0:
                continue
            add(
                EXPENSE_CATEGORY_UNCLASSIFIED,
                amount,
                source_field=f"payload.{payload_key}",
                source_reason="Unknown non-zero finance payload field",
            )
            issue_specs.append(
                {
                    "code": "expense_unclassified",
                    "message": f"Unclassified finance amount detected in field `{payload_key}`.",
                    "entity_key": f"finance-expense:{row.account_id}:{row.rrd_id}:{payload_key}",
                    "sku_id": sku_id,
                    "nm_id": row.nm_id,
                    "payload": {
                        "rrdId": row.rrd_id,
                        "reportId": row.report_id,
                        "sourceField": payload_key,
                        "amount": str(abs(amount)),
                        "amountSign": EXPENSE_SIGN_EXPENSE
                        if amount >= 0
                        else EXPENSE_SIGN_INCOME,
                        "sellerOperName": row.seller_oper_name,
                        "bonusTypeName": row.bonus_type_name,
                    },
                }
            )

        totals = cls._empty_expense_totals()
        for entry in entries:
            signed_amount = cls._entry_signed_amount(entry)
            totals[str(entry["expense_category"])] += signed_amount
        return {"entries": entries, "totals": totals, "issues": issue_specs}

    @classmethod
    def _finance_expense_values(cls, row: WBRealizationReportRow) -> dict[str, Decimal]:
        totals = cls._finance_expense_details(row)["totals"]
        return {
            "commission": totals[EXPENSE_CATEGORY_WB_COMMISSION],
            "acquiring_fee": totals[EXPENSE_CATEGORY_PAYMENT_PROCESSING],
            "logistics": totals[EXPENSE_CATEGORY_WB_LOGISTICS]
            + totals[EXPENSE_CATEGORY_WB_LOGISTICS_REBILL],
            "paid_acceptance": totals[EXPENSE_CATEGORY_ACCEPTANCE],
            "storage": totals[EXPENSE_CATEGORY_STORAGE],
            "penalties": totals[EXPENSE_CATEGORY_PENALTY],
            "deductions": totals[EXPENSE_CATEGORY_DEDUCTION]
            + totals[EXPENSE_CATEGORY_MARKETING_DEDUCTION]
            + totals[EXPENSE_CATEGORY_LOYALTY]
            + totals[EXPENSE_CATEGORY_UNCLASSIFIED],
            "additional_payments": totals[EXPENSE_CATEGORY_ADDITIONAL_PAYMENT],
        }

    @staticmethod
    def _apply_expense_values(
        bucket: dict[str, Any], values: dict[str, Decimal]
    ) -> None:
        for field, amount in values.items():
            bucket[field] += amount

    @staticmethod
    def _apply_normalized_expense_totals(
        bucket: dict[str, Any], values: dict[str, Decimal]
    ) -> None:
        for field, amount in values.items():
            if field in bucket:
                bucket[field] += amount
            elif (
                field == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT
                and "additional_payments" in bucket
            ):
                bucket["additional_payments"] += amount
            elif (
                field == EXPENSE_CATEGORY_UNCLASSIFIED and "other_wb_expenses" in bucket
            ):
                bucket["other_wb_expenses"] += amount

    @classmethod
    def _apply_compatibility_expense_fields(cls, bucket: dict[str, Any]) -> None:
        compatibility = legacy_expense_fields(
            SimpleNamespace(**{field: bucket.get(field) for field in bucket.keys()})
        )
        for field, amount in compatibility.items():
            bucket[field] = amount

    @staticmethod
    def _total_expense_from_bucket(bucket: dict[str, Any]) -> Decimal:
        return (
            bucket["commission"]
            + bucket["acquiring_fee"]
            + bucket["logistics"]
            + bucket["paid_acceptance"]
            + bucket["storage"]
            + bucket["penalties"]
            + bucket["deductions"]
            - bucket["additional_payments"]
        )

    @staticmethod
    def _ad_fields_for_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
        view = SimpleNamespace(**bucket)
        ad_operational = row_decimal(view, "ad_spend_operational")
        ad_finance = row_decimal(view, "ad_spend_finance")
        if ad_finance > 0:
            ad_final = ad_finance
            ad_source = AD_SPEND_SOURCE_FINANCE
        elif ad_operational > 0:
            ad_final = ad_operational
            ad_source = AD_SPEND_SOURCE_OPERATIONAL
        else:
            ad_final = Decimal("0")
            ad_source = AD_SPEND_SOURCE_NONE
        return {
            "ad_spend_operational": ad_operational,
            "ad_spend_finance": ad_finance,
            "ad_spend_final": ad_final,
            "ad_spend_source": ad_source,
            "ad_spend_delta": ad_operational - ad_finance,
        }

    @staticmethod
    def _reconciliation_bucket(
        *,
        age_days: int,
        has_order_without_sale: bool,
        has_sale_without_finance: bool,
        has_finance_without_sale: bool,
        has_stock_without_sales: bool,
        has_ad_spend_without_sales: bool,
        has_price_anomaly: bool,
    ) -> tuple[str, str]:
        if (
            has_sale_without_finance
            or has_finance_without_sale
            or has_order_without_sale
        ):
            if age_days <= 2:
                return "pending", "expected_lag"
            if age_days <= 7:
                if has_order_without_sale:
                    return "warning", "missing_followup"
                return "warning", "finance_lag"
            if has_order_without_sale:
                return "error", "missing_followup"
            if has_sale_without_finance:
                return "error", "missing_finance"
            return "error", "missing_sale"
        if has_price_anomaly:
            return "warning", "price_anomaly"
        if has_ad_spend_without_sales:
            return "warning", "ad_spend_without_sales"
        if has_stock_without_sales:
            return "warning", "stock_without_sales"
        return "ok", "matched"

    @staticmethod
    def _collect_open_issue_refs(
        issues: list[DataQualityIssue],
    ) -> tuple[set[int], set[int]]:
        sku_ids: set[int] = set()
        nm_ids: set[int] = set()
        for issue in issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if issue_sku_id is not None:
                sku_ids.add(issue_sku_id)
            if issue_nm_id is not None:
                nm_ids.add(issue_nm_id)
        return sku_ids, nm_ids

    @staticmethod
    def _mapping_date(value: Any) -> date | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return None

    @staticmethod
    def _mapping_datetime(value: Any) -> datetime | None:
        return value if isinstance(value, datetime) else None

    @staticmethod
    def _event_timestamp_expr(source: Any):
        return source.c.date

    @staticmethod
    def _period_start(stat_date: date, aggregate: str) -> date:
        if aggregate == "week":
            return stat_date - timedelta(days=stat_date.weekday())
        if aggregate == "month":
            return stat_date.replace(day=1)
        return stat_date

    @classmethod
    def _aggregate_sku_items(
        cls,
        rows: list[MartSKUDaily],
        *,
        aggregate: str,
        sort_by: str | None,
        sort_dir: str,
        limit: int,
        offset: int,
    ) -> Page[MartSKUDailyRead]:
        int_fields = [
            "order_rows",
            "ordered_units",
            "cancelled_orders",
            "sale_rows",
            "finance_rows",
            "operational_sales_qty",
            "operational_return_qty",
            "finance_sales_qty",
            "finance_return_qty",
            "finance_net_units",
            "final_sales_qty",
            "final_return_qty",
            "final_net_qty",
            "ad_views",
            "ad_clicks",
            "funnel_opens",
            "funnel_carts",
            "funnel_orders",
            "funnel_buyouts",
        ]
        decimal_sum_fields = [
            "operational_revenue",
            "operational_for_pay",
            "finance_revenue",
            "finance_for_pay",
            "final_revenue",
            "final_for_pay",
            "wb_commission",
            "payment_processing",
            "pvz_reward",
            "wb_logistics",
            "wb_logistics_rebill",
            "acceptance",
            "penalty",
            "deduction",
            "marketing_deduction",
            "loyalty",
            "other_wb_expenses",
            "total_wb_expenses",
            "seller_cogs",
            "seller_other_expense",
            "total_seller_expenses",
            "commission",
            "acquiring_fee",
            "logistics",
            "paid_acceptance",
            "storage",
            "penalties",
            "deductions",
            "additional_payments",
            "ad_spend_operational",
            "ad_spend_finance",
            "ad_spend_final",
            "ad_spend_delta",
            "ad_spend",
            "estimated_cogs",
            "estimated_profit_before_ads",
            "estimated_profit_after_ads",
            "net_profit_after_all_expenses",
        ]
        grouped: dict[
            tuple[date, int | None, int | None, str | None, str | None], dict[str, Any]
        ] = {}
        meta: dict[
            tuple[date, int | None, int | None, str | None, str | None], dict[str, date]
        ] = {}

        for row in rows:
            period_start = cls._period_start(row.stat_date, aggregate)
            key = (period_start, row.sku_id, row.nm_id, row.vendor_code, row.barcode)
            if key not in grouped:
                grouped[key] = {
                    "id": len(grouped) + 1,
                    "account_id": row.account_id,
                    "stat_date": period_start,
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "barcode": row.barcode,
                    "title": row.title,
                    "brand": row.brand,
                    "subject_name": row.subject_name,
                    "final_revenue_source": row.final_revenue_source,
                    "opening_stock_qty": float(row.opening_stock_qty)
                    if row.opening_stock_qty is not None
                    else None,
                    "closing_stock_qty": float(row.closing_stock_qty)
                    if row.closing_stock_qty is not None
                    else None,
                    "in_way_to_client": float(row.in_way_to_client)
                    if row.in_way_to_client is not None
                    else None,
                    "in_way_from_client": float(row.in_way_from_client)
                    if row.in_way_from_client is not None
                    else None,
                    "current_price": float(row.current_price)
                    if row.current_price is not None
                    else None,
                    "current_discounted_price": float(row.current_discounted_price)
                    if row.current_discounted_price is not None
                    else None,
                    "avg_sale_price": float(row.avg_sale_price)
                    if row.avg_sale_price is not None
                    else None,
                    "seller_discount": row.seller_discount,
                    "club_discount": row.club_discount,
                    "cost_price": float(row.cost_price)
                    if row.cost_price is not None
                    else None,
                    "packaging_cost": float(row.packaging_cost)
                    if row.packaging_cost is not None
                    else None,
                    "inbound_logistics_cost": float(row.inbound_logistics_cost)
                    if row.inbound_logistics_cost is not None
                    else None,
                    "total_unit_cost": float(row.total_unit_cost)
                    if row.total_unit_cost is not None
                    else None,
                    "margin_percent": None,
                    "roi_percent": None,
                    "drr_percent": None,
                    "has_manual_cost": bool(row.has_manual_cost),
                    "has_real_manual_cost": bool(row.has_real_manual_cost),
                    "has_placeholder_cost": bool(row.has_placeholder_cost),
                    "business_trusted": bool(row.business_trusted),
                    "cost_source": row.cost_source,
                    "has_open_issues": bool(row.has_open_issues),
                    "payload": {"aggregate": aggregate, "source_rows": 0},
                }
                for field in int_fields:
                    grouped[key][field] = int(getattr(row, field) or 0)
                for field in decimal_sum_fields:
                    grouped[key][field] = float(cls._decimal(getattr(row, field, None)))
                grouped[key]["revenue_final"] = float(
                    cls._decimal(getattr(row, "final_revenue", None))
                )
                grouped[key]["total_seller_costs"] = float(total_seller_costs(row))
                grouped[key]["additional_income"] = float(
                    expense_additional_income(row)
                )
                grouped[key]["expense_data_quality"] = compute_expense_data_quality(row)
                meta[key] = {"first_date": row.stat_date, "last_date": row.stat_date}
                grouped[key]["payload"]["source_rows"] = 1
                continue

            bucket = grouped[key]
            bucket["payload"]["source_rows"] += 1
            for field in int_fields:
                bucket[field] += int(getattr(row, field) or 0)
            for field in decimal_sum_fields:
                bucket[field] += float(cls._decimal(getattr(row, field, None)))
            bucket["revenue_final"] = float(cls._decimal(bucket["final_revenue"]))
            bucket["total_seller_costs"] = float(
                cls._decimal(bucket["total_seller_expenses"])
                if cls._decimal(bucket["total_seller_expenses"]) != 0
                else cls._decimal(bucket["estimated_cogs"])
            )
            bucket["additional_income"] = float(
                cls._decimal(bucket["additional_payments"])
                if cls._decimal(bucket["additional_payments"]) > 0
                else Decimal("0")
            )
            bucket["has_manual_cost"] = bucket["has_manual_cost"] or bool(
                row.has_manual_cost
            )
            bucket["has_real_manual_cost"] = bucket["has_real_manual_cost"] or bool(
                row.has_real_manual_cost
            )
            bucket["has_placeholder_cost"] = bucket["has_placeholder_cost"] or bool(
                row.has_placeholder_cost
            )
            bucket["business_trusted"] = bucket["business_trusted"] or bool(
                row.business_trusted
            )
            bucket["has_open_issues"] = bucket["has_open_issues"] or bool(
                row.has_open_issues
            )
            if row.cost_source:
                bucket["cost_source"] = row.cost_source

            if row.stat_date < meta[key]["first_date"]:
                meta[key]["first_date"] = row.stat_date
                bucket["opening_stock_qty"] = (
                    float(row.opening_stock_qty)
                    if row.opening_stock_qty is not None
                    else None
                )
            if row.stat_date >= meta[key]["last_date"]:
                meta[key]["last_date"] = row.stat_date
                bucket["closing_stock_qty"] = (
                    float(row.closing_stock_qty)
                    if row.closing_stock_qty is not None
                    else None
                )
                bucket["in_way_to_client"] = (
                    float(row.in_way_to_client)
                    if row.in_way_to_client is not None
                    else None
                )
                bucket["in_way_from_client"] = (
                    float(row.in_way_from_client)
                    if row.in_way_from_client is not None
                    else None
                )
                bucket["current_price"] = (
                    float(row.current_price) if row.current_price is not None else None
                )
                bucket["current_discounted_price"] = (
                    float(row.current_discounted_price)
                    if row.current_discounted_price is not None
                    else None
                )
                bucket["seller_discount"] = row.seller_discount
                bucket["club_discount"] = row.club_discount
                bucket["cost_price"] = (
                    float(row.cost_price)
                    if row.cost_price is not None
                    else bucket["cost_price"]
                )
                bucket["packaging_cost"] = (
                    float(row.packaging_cost)
                    if row.packaging_cost is not None
                    else bucket["packaging_cost"]
                )
                bucket["inbound_logistics_cost"] = (
                    float(row.inbound_logistics_cost)
                    if row.inbound_logistics_cost is not None
                    else bucket["inbound_logistics_cost"]
                )
                bucket["total_unit_cost"] = (
                    float(row.total_unit_cost)
                    if row.total_unit_cost is not None
                    else bucket["total_unit_cost"]
                )
                bucket["final_revenue_source"] = (
                    row.final_revenue_source or bucket["final_revenue_source"]
                )
                bucket["title"] = row.title or bucket["title"]
                bucket["brand"] = row.brand or bucket["brand"]
                bucket["subject_name"] = row.subject_name or bucket["subject_name"]

        items: list[MartSKUDailyRead] = []
        for bucket in grouped.values():
            revenue = Decimal(str(bucket["final_revenue"] or 0))
            cogs = Decimal(str(bucket["estimated_cogs"] or 0))
            profit = Decimal(str(bucket["estimated_profit_after_ads"] or 0))
            ad_spend = Decimal(str(bucket["ad_spend"] or 0))
            net_qty = int(bucket["final_net_qty"] or 0)
            if net_qty > 0 and revenue > 0:
                bucket["avg_sale_price"] = float(revenue / Decimal(net_qty))
            if revenue > 0:
                bucket["margin_percent"] = float((profit / revenue) * Decimal("100"))
                bucket["drr_percent"] = float((ad_spend / revenue) * Decimal("100"))
            if cogs > 0 and bucket["has_manual_cost"]:
                bucket["roi_percent"] = float((profit / cogs) * Decimal("100"))
            bucket["expense_data_quality"] = compute_expense_data_quality(
                SimpleNamespace(**bucket)
            )
            items.append(MartSKUDailyRead(**bucket))

        reverse = sort_dir != "asc"
        sort_field = sort_by or "stat_date"
        items.sort(
            key=lambda item: (
                getattr(item, sort_field)
                if getattr(item, sort_field, None) is not None
                else (date.min if sort_field == "stat_date" else float("-inf"))
            ),
            reverse=reverse,
        )
        total = len(items)
        return Page(
            total=total,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
        )

    @classmethod
    def _aggregate_reconciliation_items(
        cls,
        rows: list[MartReconciliationDaily],
        *,
        aggregate: str,
        sort_by: str | None,
        sort_dir: str,
        limit: int,
        offset: int,
    ) -> Page[MartReconciliationDailyRead]:
        int_fields = [
            "orders_qty",
            "sales_qty",
            "returns_qty",
            "finance_qty",
            "ad_orders",
        ]
        decimal_sum_fields = [
            "orders_amount",
            "sales_amount",
            "returns_amount",
            "finance_revenue",
            "finance_for_pay",
            "ad_spend_operational",
            "ad_spend_finance",
            "ad_spend_final",
            "ad_spend_delta",
            "ad_spend",
            "revenue_delta",
            "for_pay_delta",
        ]
        severity_rank = {"error": 3, "warning": 2, "pending": 1, "ok": 0, None: -1}
        grouped: dict[
            tuple[date, int, int | None, str | None, str | None], dict[str, Any]
        ] = {}
        meta: dict[
            tuple[date, int, int | None, str | None, str | None], dict[str, Any]
        ] = {}

        for row in rows:
            period_start = cls._period_start(row.stat_date, aggregate)
            key = (period_start, row.sku_id, row.nm_id, row.vendor_code, row.barcode)
            if key not in grouped:
                grouped[key] = {
                    "id": len(grouped) + 1,
                    "account_id": row.account_id,
                    "stat_date": period_start,
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "barcode": row.barcode,
                    "title": row.title,
                    "brand": row.brand,
                    "subject_name": row.subject_name,
                    "opening_stock_qty": float(row.opening_stock_qty)
                    if row.opening_stock_qty is not None
                    else None,
                    "closing_stock_qty": float(row.closing_stock_qty)
                    if row.closing_stock_qty is not None
                    else None,
                    "avg_sale_price": float(row.avg_sale_price)
                    if row.avg_sale_price is not None
                    else None,
                    "current_price": float(row.current_price)
                    if row.current_price is not None
                    else None,
                    "current_discounted_price": float(row.current_discounted_price)
                    if row.current_discounted_price is not None
                    else None,
                    "status_bucket": row.status_bucket,
                    "status_reason": row.status_reason,
                    "has_order_without_sale": bool(row.has_order_without_sale),
                    "has_sale_without_finance": bool(row.has_sale_without_finance),
                    "has_finance_without_sale": bool(row.has_finance_without_sale),
                    "has_stock_without_sales": bool(row.has_stock_without_sales),
                    "has_ad_spend_without_sales": bool(row.has_ad_spend_without_sales),
                    "has_price_anomaly": bool(row.has_price_anomaly),
                    "payload": {"aggregate": aggregate, "source_rows": 0},
                }
                for field in int_fields:
                    grouped[key][field] = int(getattr(row, field) or 0)
                for field in decimal_sum_fields:
                    grouped[key][field] = float(cls._decimal(getattr(row, field, None)))
                meta[key] = {
                    "first_date": row.stat_date,
                    "last_date": row.stat_date,
                    "status_rank": severity_rank.get(row.status_bucket, -1),
                }
                grouped[key]["payload"]["source_rows"] = 1
                continue

            bucket = grouped[key]
            bucket["payload"]["source_rows"] += 1
            for field in int_fields:
                bucket[field] += int(getattr(row, field) or 0)
            for field in decimal_sum_fields:
                bucket[field] += float(cls._decimal(getattr(row, field, None)))
            bucket["has_order_without_sale"] = bucket["has_order_without_sale"] or bool(
                row.has_order_without_sale
            )
            bucket["has_sale_without_finance"] = bucket[
                "has_sale_without_finance"
            ] or bool(row.has_sale_without_finance)
            bucket["has_finance_without_sale"] = bucket[
                "has_finance_without_sale"
            ] or bool(row.has_finance_without_sale)
            bucket["has_stock_without_sales"] = bucket[
                "has_stock_without_sales"
            ] or bool(row.has_stock_without_sales)
            bucket["has_ad_spend_without_sales"] = bucket[
                "has_ad_spend_without_sales"
            ] or bool(row.has_ad_spend_without_sales)
            bucket["has_price_anomaly"] = bucket["has_price_anomaly"] or bool(
                row.has_price_anomaly
            )

            rank = severity_rank.get(row.status_bucket, -1)
            if rank >= meta[key]["status_rank"]:
                meta[key]["status_rank"] = rank
                bucket["status_bucket"] = row.status_bucket
                bucket["status_reason"] = row.status_reason
            if row.stat_date < meta[key]["first_date"]:
                meta[key]["first_date"] = row.stat_date
                bucket["opening_stock_qty"] = (
                    float(row.opening_stock_qty)
                    if row.opening_stock_qty is not None
                    else None
                )
            if row.stat_date >= meta[key]["last_date"]:
                meta[key]["last_date"] = row.stat_date
                bucket["closing_stock_qty"] = (
                    float(row.closing_stock_qty)
                    if row.closing_stock_qty is not None
                    else None
                )
                bucket["current_price"] = (
                    float(row.current_price) if row.current_price is not None else None
                )
                bucket["current_discounted_price"] = (
                    float(row.current_discounted_price)
                    if row.current_discounted_price is not None
                    else None
                )
                bucket["title"] = row.title or bucket["title"]
                bucket["brand"] = row.brand or bucket["brand"]
                bucket["subject_name"] = row.subject_name or bucket["subject_name"]

        items: list[MartReconciliationDailyRead] = []
        for bucket in grouped.values():
            sales_qty = int(bucket["sales_qty"] or 0)
            sales_amount = Decimal(str(bucket["sales_amount"] or 0))
            if sales_qty > 0 and sales_amount > 0:
                bucket["avg_sale_price"] = float(sales_amount / Decimal(sales_qty))
            items.append(MartReconciliationDailyRead(**bucket))

        reverse = sort_dir != "asc"
        sort_field = sort_by or "stat_date"
        items.sort(
            key=lambda item: (
                getattr(item, sort_field)
                if getattr(item, sort_field, None) is not None
                else (date.min if sort_field == "stat_date" else float("-inf"))
            ),
            reverse=reverse,
        )
        total = len(items)
        return Page(
            total=total,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
        )

    async def _load_current_orders(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        orders_current = orders_current_subquery()
        rows = (
            (
                await session.execute(
                    select(orders_current).where(
                        orders_current.c.account_id == account_id,
                        self._event_timestamp_expr(orders_current)
                        >= datetime.combine(date_from, datetime.min.time()),
                        self._event_timestamp_expr(orders_current)
                        <= datetime.combine(date_to, datetime.max.time()),
                    )
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    async def _load_current_sales(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[dict[str, Any]]:
        sales_current = sales_current_subquery()
        rows = (
            (
                await session.execute(
                    select(sales_current).where(
                        sales_current.c.account_id == account_id,
                        self._event_timestamp_expr(sales_current)
                        >= datetime.combine(date_from, datetime.min.time()),
                        self._event_timestamp_expr(sales_current)
                        <= datetime.combine(date_to, datetime.max.time()),
                    )
                )
            )
            .mappings()
            .all()
        )
        return [dict(row) for row in rows]

    @staticmethod
    def _build_core_sku_index(
        core_skus: list[CoreSKU],
    ) -> dict[str, dict[Any, list[CoreSKU]]]:
        index: dict[str, dict[Any, list[CoreSKU]]] = {
            "vendor_barcode_size": defaultdict(list),
            "nm_barcode": defaultdict(list),
            "barcode": defaultdict(list),
            "nm_size": defaultdict(list),
            "vendor_size": defaultdict(list),
            "vendor": defaultdict(list),
            "nm_barcode_vendor": defaultdict(list),
        }
        for sku in core_skus:
            index["vendor_barcode_size"][
                (sku.vendor_code, sku.barcode, sku.tech_size)
            ].append(sku)
            index["nm_barcode"][(sku.nm_id, sku.barcode)].append(sku)
            index["barcode"][sku.barcode].append(sku)
            index["nm_size"][(sku.nm_id, sku.tech_size)].append(sku)
            index["vendor_size"][(sku.vendor_code, sku.tech_size)].append(sku)
            index["vendor"][sku.vendor_code].append(sku)
            index["nm_barcode_vendor"][
                (sku.nm_id, sku.barcode, sku.vendor_code)
            ].append(sku)
        return index

    def _resolve_core_sku(
        self,
        index: dict[str, dict[Any, list[CoreSKU]]],
        *,
        vendor_code: str | None,
        nm_id: int | None,
        barcode: str | None,
        tech_size: str | None,
    ) -> CoreSKU | None:
        candidates = [
            index["vendor_barcode_size"].get((vendor_code, barcode, tech_size), []),
            index["nm_barcode"].get((nm_id, barcode), []),
            index["barcode"].get(barcode, []),
            index["nm_size"].get((nm_id, tech_size), []),
            index["vendor_size"].get((vendor_code, tech_size), []),
            index["vendor"].get(vendor_code, []),
            index["nm_barcode_vendor"].get((nm_id, barcode, vendor_code), []),
        ]
        for group in candidates:
            if len(group) == 1:
                return group[0]
        return None

    def _match_cost_for_sku(
        self,
        costs: list[ManualCost],
        *,
        sku_id: int | None,
        at_date: date | None,
    ) -> ManualCost | None:
        if sku_id is None:
            return None
        candidates = [
            cost
            for cost in costs
            if cost.sku_id == sku_id and self.dashboard._cost_is_active(cost, at_date)
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda cost: (cost.valid_from or date.min, cost.id), reverse=True
        )
        return candidates[0]

    @staticmethod
    def _build_cost_index(costs: list[ManualCost]) -> dict[int, list[ManualCost]]:
        index: dict[int, list[ManualCost]] = defaultdict(list)
        for cost in costs:
            if cost.sku_id is None:
                continue
            index[int(cost.sku_id)].append(cost)
        for sku_costs in index.values():
            sku_costs.sort(
                key=lambda cost: (cost.valid_from or date.min, cost.id), reverse=True
            )
        return index

    def _match_cost_from_index(
        self,
        cost_index: dict[int, list[ManualCost]],
        *,
        sku_id: int | None,
        at_date: date | None,
    ) -> ManualCost | None:
        if sku_id is None:
            return None
        for cost in cost_index.get(int(sku_id), []):
            if self.dashboard._cost_is_active(cost, at_date):
                return cost
        return None

    @staticmethod
    def _extract_price(
        payload: dict[str, Any] | None,
    ) -> tuple[Decimal | None, Decimal | None]:
        if not isinstance(payload, dict):
            return None, None
        sizes = payload.get("sizes")
        values = sizes if isinstance(sizes, list) else [payload]
        prices: list[Decimal] = []
        discounted: list[Decimal] = []
        for item in values:
            if not isinstance(item, dict):
                continue
            price = item.get("price") or item.get("basicPrice") or item.get("priceU")
            discounted_price = (
                item.get("discountedPrice")
                or item.get("discountPrice")
                or item.get("finalPrice")
            )
            if price not in (None, ""):
                prices.append(Decimal(str(price)))
            if discounted_price not in (None, ""):
                discounted.append(Decimal(str(discounted_price)))
        return (
            min(prices) if prices else None,
            min(discounted) if discounted else None,
        )

    @staticmethod
    def _total_unit_cost(cost: ManualCost | None) -> Decimal:
        return manual_cost_total_unit_cost(cost)

    @staticmethod
    def _manual_cost_amounts(
        cost: ManualCost | None, *, net_qty: int
    ) -> dict[str, Decimal]:
        cost_price_value = manual_cost_price(cost)
        seller_other_expense_unit = manual_cost_seller_other_expense(cost)
        total_unit_cost = manual_cost_total_unit_cost(cost)
        return {
            "cost_price": cost_price_value,
            "seller_other_expense_unit": seller_other_expense_unit,
            "total_unit_cost": total_unit_cost,
            "seller_cogs_total": cost_price_value * net_qty,
            "seller_other_expense_total": seller_other_expense_unit * net_qty,
            "estimated_cogs_total": total_unit_cost * net_qty,
        }

    async def _load_cost_rows(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[ManualCost]:
        return await self.cost_repo.list_overlapping_for_account(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )

    async def _refresh_expense_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> int:
        from app.services.data_quality import DataQualityService

        dq_service = DataQualityService()
        timezone_name = await self._account_timezone(session, account_id=account_id)
        await session.execute(
            delete(MartExpenseDaily).where(
                MartExpenseDaily.account_id == account_id,
                MartExpenseDaily.stat_date >= date_from,
                MartExpenseDaily.stat_date <= date_to,
            )
        )
        await dq_service.resolve_issues(
            session,
            domain="data_quality",
            codes=["expense_unclassified"],
            account_id=account_id,
        )
        await dq_service.resolve_issues(
            session,
            domain="finance",
            codes=["unclassified_finance_expense"],
            account_id=account_id,
        )

        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        core_index = self._build_core_sku_index(core_skus)
        finance_rows = list(
            (
                await session.execute(
                    select(WBRealizationReportRow).where(
                        WBRealizationReportRow.account_id == account_id,
                        self._finance_stat_date_filter(
                            date_from=date_from,
                            date_to=date_to,
                            timezone_name=timezone_name,
                        ),
                    )
                )
            ).scalars()
        )
        rows_to_insert: list[dict[str, Any]] = []
        for row in finance_rows:
            finance_barcode = self._finance_row_barcode(row)
            resolved_sku = self._resolve_core_sku(
                core_index,
                vendor_code=row.vendor_code,
                nm_id=row.nm_id,
                barcode=finance_barcode,
                tech_size=None,
            )
            details = self._finance_expense_details(
                row,
                sku_id=resolved_sku.id if resolved_sku is not None else None,
                timezone_name=timezone_name,
            )
            rows_to_insert.extend(details["entries"])
            for issue_spec in details["issues"]:
                await dq_service.open_issue(
                    session,
                    domain="data_quality",
                    code=str(issue_spec["code"]),
                    message=str(issue_spec["message"]),
                    account_id=account_id,
                    severity="warning",
                    entity_key=str(issue_spec["entity_key"]),
                    entity_type="finance_expense",
                    entity_id=row.rrd_id,
                    sku_id=issue_spec.get("sku_id"),
                    nm_id=issue_spec.get("nm_id"),
                    source_table="wb_realization_report_rows",
                    payload=dict(issue_spec.get("payload") or {}),
                )
        await self.expense_repo.upsert_many(
            session,
            rows_to_insert,
            conflict_fields=["dedupe_key"],
        )
        return len(rows_to_insert)

    async def refresh_account(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, int | date]:
        today = date.today()
        actual_from = date_from or (today - timedelta(days=30))
        actual_to = date_to or today
        stock_rows = await self._refresh_stock_daily(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        await self._refresh_expense_daily(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        sku_rows = await self._refresh_sku_daily(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        finance_rows = await self._refresh_finance_reconciliation(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        account_expense_rows = await self._refresh_account_expense_daily(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        reconciliation_rows = await self._refresh_reconciliation_daily(
            session,
            account_id=account_id,
            date_from=actual_from,
            date_to=actual_to,
        )
        return {
            "account_id": account_id,
            "date_from": actual_from,
            "date_to": actual_to,
            "sku_rows": sku_rows,
            "stock_rows": stock_rows,
            "finance_rows": finance_rows,
            "account_expense_rows": account_expense_rows,
            "reconciliation_rows": reconciliation_rows,
        }

    async def list_sku_daily(self, session: AsyncSession, **filters):
        aggregate = filters.pop("aggregate", None)
        if aggregate not in {"week", "month"}:
            page = await self.sku_repo.list_filtered(session, **filters)
            await self._backfill_stock_fields(session, rows=list(page.items))
            return page
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        sort_by = filters.get("sort_by")
        sort_dir = filters.get("sort_dir", "desc")
        load_filters = {**filters, "limit": 1_000_000, "offset": 0}
        page = await self.sku_repo.list_filtered(session, **load_filters)
        return self._aggregate_sku_items(
            list(page.items),
            aggregate=aggregate,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    async def list_business_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> Page[MartBusinessDailyRead]:
        sku_stmt = (
            select(
                MartSKUDaily.stat_date.label("stat_date"),
                func.count(MartSKUDaily.id).label("sku_rows"),
                func.coalesce(func.sum(MartSKUDaily.final_revenue), 0).label("revenue"),
                func.coalesce(func.sum(MartSKUDaily.final_for_pay), 0).label("payout"),
                func.coalesce(func.sum(MartSKUDaily.total_wb_expenses), 0).label(
                    "sku_wb_expenses"
                ),
            )
            .where(MartSKUDaily.account_id == account_id)
            .group_by(MartSKUDaily.stat_date)
        )
        expense_stmt = (
            select(
                MartAccountExpenseDaily.stat_date.label("stat_date"),
                func.count(MartAccountExpenseDaily.id).label("expense_rows"),
                func.coalesce(
                    func.sum(MartAccountExpenseDaily.total_wb_expenses), 0
                ).label("total_wb_expenses"),
                func.coalesce(
                    func.sum(MartAccountExpenseDaily.total_seller_expenses), 0
                ).label("total_seller_costs"),
                func.coalesce(
                    func.sum(MartAccountExpenseDaily.ad_spend_final), 0
                ).label("ad_spend"),
                func.coalesce(
                    func.sum(MartAccountExpenseDaily.additional_payments), 0
                ).label("additional_income"),
            )
            .where(MartAccountExpenseDaily.account_id == account_id)
            .group_by(MartAccountExpenseDaily.stat_date)
        )
        ads_stmt = (
            select(
                WBAdStatsDaily.stat_date.label("stat_date"),
                func.coalesce(func.sum(WBAdStatsDaily.sum), 0).label("ad_spend"),
            )
            .where(WBAdStatsDaily.account_id == account_id)
            .group_by(WBAdStatsDaily.stat_date)
        )
        if date_from is not None:
            sku_stmt = sku_stmt.where(MartSKUDaily.stat_date >= date_from)
            expense_stmt = expense_stmt.where(
                MartAccountExpenseDaily.stat_date >= date_from
            )
            ads_stmt = ads_stmt.where(WBAdStatsDaily.stat_date >= date_from)
        if date_to is not None:
            sku_stmt = sku_stmt.where(MartSKUDaily.stat_date <= date_to)
            expense_stmt = expense_stmt.where(
                MartAccountExpenseDaily.stat_date <= date_to
            )
            ads_stmt = ads_stmt.where(WBAdStatsDaily.stat_date <= date_to)

        rows: dict[date, dict[str, Any]] = {}
        for row in (await session.execute(sku_stmt)).mappings():
            stat_date = row["stat_date"]
            total_wb_expenses = float(self._decimal(row["sku_wb_expenses"]))
            revenue = float(self._decimal(row["revenue"]))
            rows[stat_date] = {
                "account_id": account_id,
                "stat_date": stat_date,
                "revenue": revenue,
                "payout": float(self._decimal(row["payout"])),
                "expenses": total_wb_expenses,
                "total_wb_expenses": total_wb_expenses,
                "total_seller_costs": 0.0,
                "ad_spend": 0.0,
                "profit": revenue - total_wb_expenses,
                "sku_rows": int(row["sku_rows"] or 0),
                "expense_rows": 0,
            }

        for row in (await session.execute(expense_stmt)).mappings():
            stat_date = row["stat_date"]
            bucket = rows.setdefault(
                stat_date,
                {
                    "account_id": account_id,
                    "stat_date": stat_date,
                    "revenue": 0.0,
                    "payout": 0.0,
                    "expenses": 0.0,
                    "total_wb_expenses": 0.0,
                    "total_seller_costs": 0.0,
                    "ad_spend": 0.0,
                    "profit": 0.0,
                    "sku_rows": 0,
                    "expense_rows": 0,
                },
            )
            total_wb_expenses = float(bucket["total_wb_expenses"]) + float(
                self._decimal(row["total_wb_expenses"])
            )
            total_seller_costs = float(self._decimal(row["total_seller_costs"]))
            ad_spend = float(self._decimal(row["ad_spend"]))
            additional_income = float(self._decimal(row["additional_income"]))
            bucket["total_wb_expenses"] = total_wb_expenses
            bucket["total_seller_costs"] = total_seller_costs
            bucket["ad_spend"] = ad_spend
            bucket["expenses"] = total_wb_expenses + total_seller_costs + ad_spend
            bucket["profit"] = (
                float(bucket["revenue"])
                - bucket["expenses"]
                + max(0.0, additional_income)
            )
            bucket["expense_rows"] = int(row["expense_rows"] or 0)

        for row in (await session.execute(ads_stmt)).mappings():
            stat_date = row["stat_date"]
            ads_api_spend = float(self._decimal(row["ad_spend"]))
            if ads_api_spend <= 0:
                continue
            bucket = rows.setdefault(
                stat_date,
                {
                    "account_id": account_id,
                    "stat_date": stat_date,
                    "revenue": 0.0,
                    "payout": 0.0,
                    "expenses": 0.0,
                    "total_wb_expenses": 0.0,
                    "total_seller_costs": 0.0,
                    "ad_spend": 0.0,
                    "profit": 0.0,
                    "sku_rows": 0,
                    "expense_rows": 0,
                },
            )
            existing_ad_spend = float(bucket["ad_spend"])
            if abs(existing_ad_spend) > 0.01:
                continue
            bucket["ad_spend"] = ads_api_spend
            bucket["expenses"] = float(bucket["expenses"]) + ads_api_spend
            bucket["profit"] = float(bucket["profit"]) - ads_api_spend

        items = [
            MartBusinessDailyRead(**bucket)
            for _, bucket in sorted(rows.items(), key=lambda item: item[0])
        ]
        total = len(items)
        return Page(
            total=total,
            limit=limit,
            offset=offset,
            items=items[offset : offset + limit],
        )

    async def list_stock_daily(self, session: AsyncSession, **filters):
        return await self.stock_repo.list_filtered(session, **filters)

    async def list_finance_reconciliation(self, session: AsyncSession, **filters):
        return await self.finance_repo.list_filtered(session, **filters)

    async def list_account_expense_daily(self, session: AsyncSession, **filters):
        return await self.account_expense_repo.list_filtered(session, **filters)

    async def list_reconciliation_daily(self, session: AsyncSession, **filters):
        aggregate = filters.pop("aggregate", None)
        if aggregate not in {"week", "month"}:
            page = await self.reconciliation_daily_repo.list_filtered(
                session, **filters
            )
            await self._backfill_stock_fields(session, rows=list(page.items))
            return page
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        sort_by = filters.get("sort_by")
        sort_dir = filters.get("sort_dir", "desc")
        load_filters = {**filters, "limit": 1_000_000, "offset": 0}
        page = await self.reconciliation_daily_repo.list_filtered(
            session, **load_filters
        )
        return self._aggregate_reconciliation_items(
            list(page.items),
            aggregate=aggregate,
            sort_by=sort_by,
            sort_dir=sort_dir,
            limit=limit,
            offset=offset,
        )

    async def _backfill_stock_fields(
        self, session: AsyncSession, *, rows: list[Any]
    ) -> None:
        targets = [
            row
            for row in rows
            if getattr(row, "sku_id", None) is not None
            and (
                getattr(row, "opening_stock_qty", None) is None
                or getattr(row, "closing_stock_qty", None) is None
                or getattr(row, "in_way_to_client", None) is None
                or getattr(row, "in_way_from_client", None) is None
            )
        ]
        if not targets:
            return

        account_id = int(targets[0].account_id)
        sku_ids = sorted({int(row.sku_id) for row in targets if row.sku_id is not None})
        max_date = max(row.stat_date for row in targets)
        stock_rows = list(
            (
                await session.execute(
                    select(MartStockDaily).where(
                        MartStockDaily.account_id == account_id,
                        MartStockDaily.sku_id.in_(sku_ids),
                        MartStockDaily.stat_date <= max_date,
                    )
                )
            ).scalars()
        )
        rows_by_sku: dict[int, list[MartStockDaily]] = defaultdict(list)
        for stock_row in stock_rows:
            if stock_row.sku_id is None:
                continue
            rows_by_sku[int(stock_row.sku_id)].append(stock_row)

        for row in targets:
            sku_rows = rows_by_sku.get(int(row.sku_id), [])
            if not sku_rows:
                continue
            closing_snapshot = stock_snapshot_on_or_before(
                sku_rows,
                target_date=row.stat_date,
            )
            opening_snapshot = stock_snapshot_on_or_before(
                sku_rows,
                target_date=row.stat_date,
                strict_before=True,
            )
            if (
                getattr(row, "closing_stock_qty", None) is None
                and closing_snapshot is not None
            ):
                row.closing_stock_qty = closing_snapshot.quantity_full
            if (
                getattr(row, "opening_stock_qty", None) is None
                and opening_snapshot is not None
            ):
                row.opening_stock_qty = opening_snapshot.quantity_full
            if (
                getattr(row, "in_way_to_client", None) is None
                and closing_snapshot is not None
            ):
                row.in_way_to_client = closing_snapshot.in_way_to_client
            if (
                getattr(row, "in_way_from_client", None) is None
                and closing_snapshot is not None
            ):
                row.in_way_from_client = closing_snapshot.in_way_from_client

    async def _refresh_sku_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> int:
        timezone_name = await self._account_timezone(session, account_id=account_id)
        await session.execute(
            delete(MartSKUDaily).where(
                MartSKUDaily.account_id == account_id,
                MartSKUDaily.stat_date >= date_from,
                MartSKUDaily.stat_date <= date_to,
            )
        )

        price_rows = list(
            (
                await session.execute(
                    select(WBPrice).where(WBPrice.account_id == account_id)
                )
            ).scalars()
        )
        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        core_index = self._build_core_sku_index(core_skus)
        vendor_by_nm: dict[int, str | None] = {}
        active_skus_by_nm: dict[int, list[CoreSKU]] = defaultdict(list)
        for sku in core_skus:
            if sku.nm_id is not None:
                active_skus_by_nm[sku.nm_id].append(sku)
                if sku.vendor_code and sku.nm_id not in vendor_by_nm:
                    vendor_by_nm[sku.nm_id] = sku.vendor_code
        current_prices: dict[int, dict[str, Any]] = {}
        for price in price_rows:
            base_price, discounted_price = self._extract_price(price.payload)
            current_prices[price.nm_id] = {
                "current_price": base_price,
                "current_discounted_price": discounted_price,
                "seller_discount": price.discount,
                "club_discount": price.club_discount,
            }

        costs = await self._load_cost_rows(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        cost_index = self._build_cost_index(costs)
        open_issues = list(
            (
                await session.execute(
                    select(DataQualityIssue).where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                    )
                )
            ).scalars()
        )
        open_issue_sku_ids, open_issue_nm_ids = self._collect_open_issue_refs(
            open_issues
        )

        buckets: dict[
            tuple[date, int | None, str | None, str | None], dict[str, Any]
        ] = {}

        def get_bucket(
            stat_date: date,
            nm_id: int | None,
            vendor_code: str | None,
            barcode: str | None,
        ) -> dict[str, Any]:
            allocated_from_nm_level = False
            if nm_id is not None and barcode is None:
                candidates = active_skus_by_nm.get(nm_id, [])
                if len(candidates) == 1:
                    candidate = candidates[0]
                    vendor_code = vendor_code or candidate.vendor_code
                    barcode = candidate.barcode
                    allocated_from_nm_level = True
            key = (stat_date, nm_id, vendor_code, barcode)
            if key not in buckets:
                price_state = current_prices.get(nm_id or -1, {})
                buckets[key] = {
                    "account_id": account_id,
                    "stat_date": stat_date,
                    "nm_id": nm_id,
                    "vendor_code": vendor_code or vendor_by_nm.get(nm_id or -1),
                    "barcode": barcode,
                    "title": None,
                    "brand": None,
                    "subject_name": None,
                    "sku_id": None,
                    "order_rows": 0,
                    "ordered_units": 0,
                    "cancelled_orders": 0,
                    "sale_rows": 0,
                    "finance_rows": 0,
                    "operational_sales_qty": 0,
                    "operational_return_qty": 0,
                    "operational_revenue": Decimal("0"),
                    "operational_for_pay": Decimal("0"),
                    "finance_sales_qty": 0,
                    "finance_return_qty": 0,
                    "finance_net_units": 0,
                    "finance_revenue": Decimal("0"),
                    "finance_for_pay": Decimal("0"),
                    "final_sales_qty": 0,
                    "final_return_qty": 0,
                    "final_net_qty": 0,
                    "final_revenue": Decimal("0"),
                    "final_for_pay": Decimal("0"),
                    "final_revenue_source": None,
                    "wb_commission": Decimal("0"),
                    "payment_processing": Decimal("0"),
                    "pvz_reward": Decimal("0"),
                    "wb_logistics": Decimal("0"),
                    "wb_logistics_rebill": Decimal("0"),
                    "acceptance": Decimal("0"),
                    "penalty": Decimal("0"),
                    "deduction": Decimal("0"),
                    "marketing_deduction": Decimal("0"),
                    "loyalty": Decimal("0"),
                    "other_wb_expenses": Decimal("0"),
                    "total_wb_expenses": Decimal("0"),
                    "seller_cogs": Decimal("0"),
                    "seller_other_expense": Decimal("0"),
                    "total_seller_expenses": Decimal("0"),
                    "commission": Decimal("0"),
                    "acquiring_fee": Decimal("0"),
                    "logistics": Decimal("0"),
                    "paid_acceptance": Decimal("0"),
                    "storage": Decimal("0"),
                    "penalties": Decimal("0"),
                    "deductions": Decimal("0"),
                    "additional_payments": Decimal("0"),
                    "ad_spend_operational": Decimal("0"),
                    "ad_spend_finance": Decimal("0"),
                    "ad_spend_final": Decimal("0"),
                    "ad_spend_source": AD_SPEND_SOURCE_NONE,
                    "ad_spend_delta": Decimal("0"),
                    "ad_spend": Decimal("0"),
                    "ad_views": 0,
                    "ad_clicks": 0,
                    "funnel_opens": 0,
                    "funnel_carts": 0,
                    "funnel_orders": 0,
                    "funnel_buyouts": 0,
                    "opening_stock_qty": None,
                    "closing_stock_qty": None,
                    "in_way_to_client": None,
                    "in_way_from_client": None,
                    "current_price": price_state.get("current_price"),
                    "current_discounted_price": price_state.get(
                        "current_discounted_price"
                    ),
                    "avg_sale_price": None,
                    "seller_discount": price_state.get("seller_discount"),
                    "club_discount": price_state.get("club_discount"),
                    "cost_price": None,
                    "packaging_cost": None,
                    "inbound_logistics_cost": None,
                    "total_unit_cost": None,
                    "estimated_cogs": None,
                    "estimated_profit_before_ads": None,
                    "estimated_profit_after_ads": None,
                    "net_profit_after_all_expenses": None,
                    "margin_percent": None,
                    "roi_percent": None,
                    "drr_percent": None,
                    "has_manual_cost": False,
                    "has_real_manual_cost": False,
                    "has_placeholder_cost": False,
                    "business_trusted": False,
                    "cost_source": None,
                    "has_open_issues": False,
                    "payload": {
                        "sources": [],
                        "allocated_from_nm_level": allocated_from_nm_level,
                    },
                }
            elif allocated_from_nm_level:
                buckets[key]["payload"]["allocated_from_nm_level"] = True
            return buckets[key]

        order_rows = await self._load_current_orders(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        closed_finance_date_to = await self._finance_closed_through_date(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        for order in order_rows:
            stat_date = self._mapping_date(order.get("date"))
            if stat_date is None:
                continue
            bucket = get_bucket(
                stat_date,
                order.get("nm_id"),
                order.get("supplier_article"),
                order.get("barcode"),
            )
            bucket["title"] = bucket["title"] or order.get("supplier_article")
            bucket["order_rows"] += 1
            if order.get("is_cancel"):
                bucket["cancelled_orders"] += 1
            else:
                bucket["ordered_units"] += 1
            bucket["payload"]["sources"].append("orders")

        sale_rows = await self._load_current_sales(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        for sale in sale_rows:
            stat_date = self._mapping_date(sale.get("date"))
            if stat_date is None:
                continue
            if not self._should_use_operational_sale(
                stat_date, closed_finance_date_to
            ):
                continue
            bucket = get_bucket(
                stat_date,
                sale.get("nm_id"),
                sale.get("supplier_article"),
                sale.get("barcode"),
            )
            bucket["brand"] = bucket["brand"] or sale.get("brand")
            bucket["subject_name"] = bucket["subject_name"] or sale.get("subject")
            bucket["sale_rows"] += 1
            sign = (
                -1
                if sale.get("is_cancel") or self._decimal(sale.get("for_pay")) < 0
                else 1
            )
            if sign > 0:
                bucket["operational_sales_qty"] += 1
            else:
                bucket["operational_return_qty"] += 1
            bucket["operational_revenue"] += self._decimal(
                sale.get("finished_price")
                or sale.get("price_with_disc")
                or sale.get("total_price")
            )
            bucket["operational_for_pay"] += self._decimal(sale.get("for_pay"))
            bucket["payload"]["sources"].append("sales")

        finance_rows = list(
            (
                await session.execute(
                    select(WBRealizationReportRow).where(
                        WBRealizationReportRow.account_id == account_id,
                        self._finance_stat_date_filter(
                            date_from=date_from,
                            date_to=date_to,
                            timezone_name=timezone_name,
                        ),
                    )
                )
            ).scalars()
        )
        for row in finance_rows:
            stat_date = self._finance_row_date(row, timezone_name=timezone_name)
            if stat_date is None:
                continue
            finance_barcode = self._finance_row_barcode(row)
            bucket = get_bucket(stat_date, row.nm_id, row.vendor_code, finance_barcode)
            bucket["title"] = bucket["title"] or row.title
            bucket["brand"] = bucket["brand"] or row.brand
            bucket["subject_name"] = bucket["subject_name"] or row.subject_name
            if self._is_reconcilable_finance_row(row):
                bucket["finance_rows"] += 1
                quantity = int(row.quantity or 1)
                sign = self._finance_sign(row)
                bucket["finance_net_units"] += quantity * sign
                if sign > 0:
                    bucket["finance_sales_qty"] += quantity
                else:
                    bucket["finance_return_qty"] += quantity
                bucket["finance_revenue"] += self._signed_finance_amount(
                    row, row.retail_amount
                )
                bucket["finance_for_pay"] += self._signed_finance_amount(
                    row, row.for_pay
                )
            expense_details = self._finance_expense_details(
                row, timezone_name=timezone_name
            )
            self._apply_normalized_expense_totals(bucket, expense_details["totals"])
            bucket["payload"]["sources"].append("finance")

        ad_rows = list(
            (
                await session.execute(
                    select(WBAdStatsDaily).where(
                        WBAdStatsDaily.account_id == account_id,
                        WBAdStatsDaily.stat_date >= date_from,
                        WBAdStatsDaily.stat_date <= date_to,
                    )
                )
            ).scalars()
        )
        for row in ad_rows:
            bucket = get_bucket(row.stat_date, row.nm_id, None, None)
            bucket["ad_spend_operational"] += self._decimal(row.sum)
            bucket["ad_views"] += int(row.views or 0)
            bucket["ad_clicks"] += int(row.clicks or 0)
            bucket["payload"]["sources"].append("ads")

        funnel_rows = list(
            (
                await session.execute(
                    select(WBCardFunnelDaily).where(
                        WBCardFunnelDaily.account_id == account_id,
                        WBCardFunnelDaily.stat_date >= date_from,
                        WBCardFunnelDaily.stat_date <= date_to,
                    )
                )
            ).scalars()
        )
        for row in funnel_rows:
            bucket = get_bucket(row.stat_date, row.nm_id, row.vendor_code, None)
            bucket["title"] = bucket["title"] or row.title
            bucket["brand"] = bucket["brand"] or row.brand_name
            bucket["subject_name"] = bucket["subject_name"] or row.subject_name
            bucket["funnel_opens"] += int(row.open_count or 0)
            bucket["funnel_carts"] += int(row.cart_count or 0)
            bucket["funnel_orders"] += int(row.order_count or 0)
            bucket["funnel_buyouts"] += int(row.buyout_count or 0)
            bucket["payload"]["sources"].append("funnel")

        stock_rows = list(
            (
                await session.execute(
                    select(MartStockDaily).where(
                        MartStockDaily.account_id == account_id,
                        MartStockDaily.stat_date >= date_from - timedelta(days=7),
                        MartStockDaily.stat_date <= date_to,
                    )
                )
            ).scalars()
        )
        stock_series_exact: dict[
            tuple[int | None, str | None], dict[date, dict[str, Decimal]]
        ] = defaultdict(dict)
        stock_series_nm: dict[int | None, dict[date, dict[str, Decimal]]] = defaultdict(
            dict
        )
        for row in stock_rows:
            exact_key = (row.nm_id, row.barcode)
            nm_key = row.nm_id
            exact_state = stock_series_exact[exact_key].setdefault(
                row.stat_date,
                {
                    "quantity": Decimal("0"),
                    "in_way_to_client": Decimal("0"),
                    "in_way_from_client": Decimal("0"),
                },
            )
            exact_state["quantity"] += self._decimal(row.quantity)
            exact_state["in_way_to_client"] += self._decimal(row.in_way_to_client)
            exact_state["in_way_from_client"] += self._decimal(row.in_way_from_client)
            nm_state = stock_series_nm[nm_key].setdefault(
                row.stat_date,
                {
                    "quantity": Decimal("0"),
                    "in_way_to_client": Decimal("0"),
                    "in_way_from_client": Decimal("0"),
                },
            )
            nm_state["quantity"] += self._decimal(row.quantity)
            nm_state["in_way_to_client"] += self._decimal(row.in_way_to_client)
            nm_state["in_way_from_client"] += self._decimal(row.in_way_from_client)

        rows_to_insert: list[dict[str, Any]] = []
        for bucket in buckets.values():
            resolved_sku = self._resolve_core_sku(
                core_index,
                vendor_code=bucket["vendor_code"],
                nm_id=bucket["nm_id"],
                barcode=bucket["barcode"],
                tech_size=None,
            )
            if resolved_sku is None:
                # Keep mart_sku_daily at a strict SKU grain.
                # Ambiguous or article-level-only rows are surfaced through DQ/reconciliation,
                # but must not become pseudo-SKU rows inside the main profitability mart.
                continue
            bucket["sku_id"] = resolved_sku.id
            bucket["vendor_code"] = bucket["vendor_code"] or resolved_sku.vendor_code
            bucket["title"] = bucket["title"] or resolved_sku.title
            bucket["brand"] = bucket["brand"] or resolved_sku.brand
            bucket["subject_name"] = bucket["subject_name"] or resolved_sku.subject_name
            stock_history = stock_series_exact.get(
                (bucket["nm_id"], bucket["barcode"])
            ) or stock_series_nm.get(bucket["nm_id"], {})
            if stock_history:
                closing_state = stock_history.get(bucket["stat_date"])
                previous_dates = [
                    stock_date
                    for stock_date in stock_history
                    if stock_date < bucket["stat_date"]
                ]
                opening_state = (
                    stock_history[max(previous_dates)] if previous_dates else None
                )
                if opening_state is not None:
                    bucket["opening_stock_qty"] = opening_state["quantity"]
                if closing_state is not None:
                    bucket["closing_stock_qty"] = closing_state["quantity"]
                    bucket["in_way_to_client"] = closing_state["in_way_to_client"]
                    bucket["in_way_from_client"] = closing_state["in_way_from_client"]
            use_finance = bucket["finance_rows"] > 0
            if use_finance:
                bucket["final_sales_qty"] = bucket["finance_sales_qty"]
                bucket["final_return_qty"] = bucket["finance_return_qty"]
                bucket["final_net_qty"] = bucket["finance_net_units"]
                bucket["final_revenue"] = self._decimal(bucket["finance_revenue"])
                bucket["final_for_pay"] = self._decimal(bucket["finance_for_pay"])
                bucket["final_revenue_source"] = "finance"
            else:
                bucket["final_sales_qty"] = bucket["operational_sales_qty"]
                bucket["final_return_qty"] = bucket["operational_return_qty"]
                bucket["final_net_qty"] = int(bucket["operational_sales_qty"]) - int(
                    bucket["operational_return_qty"]
                )
                bucket["final_revenue"] = self._decimal(bucket["operational_revenue"])
                bucket["final_for_pay"] = self._decimal(bucket["operational_for_pay"])
                bucket["final_revenue_source"] = "operational"
            if int(bucket["final_sales_qty"] or 0) > 0:
                bucket["avg_sale_price"] = self._decimal(
                    bucket["final_revenue"]
                ) / Decimal(str(bucket["final_sales_qty"]))

            matched_cost = self._match_cost_from_index(
                cost_index,
                sku_id=bucket["sku_id"],
                at_date=bucket["stat_date"],
            )
            bucket["ad_spend_finance"] = self._decimal(bucket["marketing_deduction"])
            bucket["total_wb_expenses"] = normalized_wb_expenses_total(
                SimpleNamespace(**bucket)
            )
            self._apply_compatibility_expense_fields(bucket)
            ad_fields = self._ad_fields_for_bucket(bucket)
            bucket.update(ad_fields)
            bucket["ad_spend"] = self._decimal(bucket["ad_spend_final"])
            if matched_cost is not None:
                net_qty = int(bucket["final_net_qty"])
                manual_amounts = self._manual_cost_amounts(
                    matched_cost, net_qty=net_qty
                )
                bucket["estimated_cogs"] = manual_amounts["estimated_cogs_total"]
                bucket["cost_price"] = manual_amounts["cost_price"]
                bucket["packaging_cost"] = Decimal(
                    str(matched_cost.packaging_cost or 0)
                )
                bucket["inbound_logistics_cost"] = Decimal(
                    str(matched_cost.inbound_logistics_cost or 0)
                )
                bucket["total_unit_cost"] = manual_amounts["total_unit_cost"]
                bucket["seller_cogs"] = manual_amounts["seller_cogs_total"]
                bucket["seller_other_expense"] = manual_amounts[
                    "seller_other_expense_total"
                ]
                bucket["total_seller_expenses"] = total_seller_expenses(
                    SimpleNamespace(**bucket)
                )
                bucket["has_manual_cost"] = True
                bucket["has_placeholder_cost"] = is_placeholder_manual_cost(
                    matched_cost
                )
                bucket["has_real_manual_cost"] = is_supplier_confirmed_manual_cost(
                    matched_cost
                )
                bucket["business_trusted"] = effective_cost_is_business_trusted(
                    has_manual_cost=True,
                    has_real_manual_cost=bool(bucket["has_real_manual_cost"]),
                    has_placeholder_cost=bool(bucket["has_placeholder_cost"]),
                    cost_source=getattr(matched_cost, "cost_source", None),
                    cost_truth_level=cost_truth_level_from_cost(matched_cost),
                    cost_trust_policy=COST_TRUST_POLICY_OPERATOR_BASELINE,
                )
                bucket["cost_source"] = (
                    getattr(matched_cost, "cost_source", None)
                    or matched_cost.match_rule
                    or matched_cost.supplier
                    or "manual_cost"
                )
            else:
                bucket["seller_cogs"] = Decimal("0")
                bucket["seller_other_expense"] = Decimal("0")
                bucket["total_seller_expenses"] = Decimal("0")
            if bucket["has_manual_cost"]:
                additional_income_value = expense_additional_income(
                    SimpleNamespace(**bucket)
                )
                bucket["estimated_profit_before_ads"] = (
                    self._decimal(bucket["final_revenue"])
                    - self._decimal(bucket["total_wb_expenses"])
                    - self._decimal(bucket["total_seller_expenses"])
                    + additional_income_value
                )
                bucket["estimated_profit_after_ads"] = self._decimal(
                    bucket["estimated_profit_before_ads"]
                ) - self._decimal(
                    extra_ad_spend_not_in_wb_expenses(SimpleNamespace(**bucket))
                )
                bucket["net_profit_after_all_expenses"] = net_profit_after_all_expenses(
                    SimpleNamespace(**bucket)
                )
                final_revenue = self._decimal(bucket["final_revenue"])
                estimated_cogs = self._decimal(bucket["estimated_cogs"])
                if final_revenue > 0:
                    bucket["margin_percent"] = (
                        self._decimal(bucket["estimated_profit_after_ads"])
                        / final_revenue
                    ) * Decimal("100")
                    bucket["drr_percent"] = (
                        self._decimal(bucket["ad_spend_final"]) / final_revenue
                    ) * Decimal("100")
                if estimated_cogs > 0:
                    bucket["roi_percent"] = (
                        self._decimal(bucket["estimated_profit_after_ads"])
                        / estimated_cogs
                    ) * Decimal("100")
            elif self._decimal(bucket["final_revenue"]) > 0:
                bucket["drr_percent"] = (
                    self._decimal(bucket["ad_spend_final"])
                    / self._decimal(bucket["final_revenue"])
                ) * Decimal("100")
            bucket["has_open_issues"] = bool(
                (
                    bucket["sku_id"] is not None
                    and bucket["sku_id"] in open_issue_sku_ids
                )
                or (
                    bucket["nm_id"] is not None and bucket["nm_id"] in open_issue_nm_ids
                )
            )
            rows_to_insert.append(bucket)

        await self.sku_repo.upsert_many(
            session,
            rows_to_insert,
            conflict_fields=["dedupe_key"],
        )
        return len(rows_to_insert)

    async def _refresh_stock_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> int:
        await session.execute(
            delete(MartStockDaily).where(
                MartStockDaily.account_id == account_id,
                MartStockDaily.stat_date >= date_from,
                MartStockDaily.stat_date <= date_to,
            )
        )

        snapshots = list(
            (
                await session.execute(
                    select(WBStockSnapshot).where(
                        WBStockSnapshot.account_id == account_id,
                        WBStockSnapshot.snapshot_at
                        >= datetime.combine(date_from, datetime.min.time()),
                        WBStockSnapshot.snapshot_at
                        <= datetime.combine(date_to, datetime.max.time()),
                    )
                )
            ).scalars()
        )
        snapshot_map = {snapshot.id: snapshot.snapshot_at for snapshot in snapshots}
        latest_sale_by_nm: dict[int, date] = {}
        sales_by_exact_date: dict[tuple[int | None, str | None], dict[date, int]] = (
            defaultdict(lambda: defaultdict(int))
        )
        sales_by_nm_date: dict[int | None, dict[date, int]] = defaultdict(
            lambda: defaultdict(int)
        )
        sale_rows = await self._load_current_sales(
            session,
            account_id=account_id,
            date_from=date_from - timedelta(days=90),
            date_to=date_to,
        )
        for sale in sale_rows:
            if sale.get("nm_id") is None:
                continue
            sale_date = self._mapping_date(sale.get("date"))
            if sale_date is None:
                continue
            previous = latest_sale_by_nm.get(sale["nm_id"])
            if previous is None or sale_date > previous:
                latest_sale_by_nm[sale["nm_id"]] = sale_date
            if sale.get("is_cancel") or self._decimal(sale.get("for_pay")) < 0:
                continue
            sales_by_exact_date[(sale.get("nm_id"), sale.get("barcode"))][
                sale_date
            ] += 1
            sales_by_nm_date[sale.get("nm_id")][sale_date] += 1

        def rolling_sales(
            nm_id: int | None, barcode: str | None, stat_date: date, days: int
        ) -> int:
            start_date = stat_date - timedelta(days=days - 1)
            series = sales_by_exact_date.get((nm_id, barcode)) or sales_by_nm_date.get(
                nm_id, {}
            )
            return sum(
                qty
                for sale_date, qty in series.items()
                if start_date <= sale_date <= stat_date
            )

        bucket_candidates: dict[
            tuple[date, int | None, str | None, int | None, str | None], dict[str, Any]
        ] = {}
        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        sku_vendor: dict[tuple[int | None, str | None], str | None] = {
            (sku.nm_id, sku.barcode): sku.vendor_code for sku in core_skus
        }

        row_items = list(
            (
                await session.execute(
                    select(WBStockSnapshotRow).where(
                        WBStockSnapshotRow.account_id == account_id
                    )
                )
            ).scalars()
        )
        for row in row_items:
            snapshot_at = snapshot_map.get(row.snapshot_id)
            if snapshot_at is None:
                continue
            stat_date = snapshot_at.date()
            if stat_date < date_from or stat_date > date_to:
                continue
            key = (
                stat_date,
                row.nm_id,
                row.barcode,
                row.warehouse_id,
                row.warehouse_name,
            )
            current = bucket_candidates.get(key)
            if current is None or snapshot_at > current["snapshot_at"]:
                last_sale_date = latest_sale_by_nm.get(row.nm_id or -1)
                days_since_last_sale = (
                    (stat_date - last_sale_date).days if last_sale_date else None
                )
                sales_7d = rolling_sales(row.nm_id, row.barcode, stat_date, 7)
                sales_14d = rolling_sales(row.nm_id, row.barcode, stat_date, 14)
                sales_30d = rolling_sales(row.nm_id, row.barcode, stat_date, 30)
                quantity = self._decimal(row.quantity)
                avg_sales_per_day_30d = (
                    Decimal(str(sales_30d)) / Decimal("30")
                    if sales_30d
                    else Decimal("0")
                )
                days_of_stock = (
                    (quantity / avg_sales_per_day_30d)
                    if avg_sales_per_day_30d > 0
                    else None
                )
                turnover_rate = (
                    (Decimal(str(sales_30d)) / quantity) if quantity > 0 else None
                )
                is_dead_stock = bool(quantity > 0 and sales_30d == 0)
                is_out_of_stock_risk = bool(
                    quantity > 0
                    and avg_sales_per_day_30d > 0
                    and days_of_stock is not None
                    and days_of_stock <= Decimal("7")
                )
                payload = dict(row.payload or {})
                payload["stockMetrics"] = {
                    "sales7d": sales_7d,
                    "sales14d": sales_14d,
                    "sales30d": sales_30d,
                    "avgSalesPerDay30d": str(avg_sales_per_day_30d),
                    "daysOfStock": str(days_of_stock)
                    if days_of_stock is not None
                    else None,
                    "turnoverRate": str(turnover_rate)
                    if turnover_rate is not None
                    else None,
                }
                bucket_candidates[key] = {
                    "snapshot_at": snapshot_at,
                    "account_id": account_id,
                    "stat_date": stat_date,
                    "nm_id": row.nm_id,
                    "sku_id": None,
                    "vendor_code": sku_vendor.get((row.nm_id, row.barcode)),
                    "barcode": row.barcode,
                    "warehouse_id": row.warehouse_id,
                    "warehouse_name": row.warehouse_name,
                    "quantity": row.quantity,
                    "quantity_full": row.quantity_full,
                    "in_way_to_client": row.in_way_to_client,
                    "in_way_from_client": row.in_way_from_client,
                    "days_since_last_sale": days_since_last_sale,
                    "sales_7d": sales_7d,
                    "sales_14d": sales_14d,
                    "sales_30d": sales_30d,
                    "avg_sales_per_day_30d": avg_sales_per_day_30d,
                    "days_of_stock": days_of_stock,
                    "turnover_rate": turnover_rate,
                    "is_out_of_stock_risk": is_out_of_stock_risk,
                    "is_dead_stock": is_dead_stock,
                    "payload": payload,
                }

        rows_to_insert = [value for value in bucket_candidates.values()]
        for row in rows_to_insert:
            row.pop("snapshot_at", None)
        core_index = self._build_core_sku_index(core_skus)
        for row in rows_to_insert:
            resolved_sku = self._resolve_core_sku(
                core_index,
                vendor_code=row["vendor_code"],
                nm_id=row["nm_id"],
                barcode=row["barcode"],
                tech_size=None,
            )
            row["sku_id"] = resolved_sku.id if resolved_sku is not None else None
        await self.stock_repo.upsert_many(
            session,
            rows_to_insert,
            conflict_fields=["dedupe_key"],
        )
        return len(rows_to_insert)

    async def _refresh_finance_reconciliation(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> int:
        timezone_name = await self._account_timezone(session, account_id=account_id)
        current_orders = await self._load_current_orders(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        current_sales = await self._load_current_sales(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        finance_rows = list(
            (
                await session.execute(
                    select(WBRealizationReportRow).where(
                        WBRealizationReportRow.account_id == account_id,
                        self._finance_stat_date_filter(
                            date_from=date_from,
                            date_to=date_to,
                            timezone_name=timezone_name,
                        ),
                    )
                )
            ).scalars()
        )
        buckets: dict[tuple[str, int | None], dict[str, Any]] = {}

        def get_bucket(srid: str, nm_id: int | None) -> dict[str, Any]:
            key = (srid, nm_id)
            if key not in buckets:
                buckets[key] = {
                    "account_id": account_id,
                    "srid": srid,
                    "stat_date": date_to,
                    "order_id": None,
                    "nm_id": nm_id,
                    "sku_id": None,
                    "vendor_code": None,
                    "barcode": None,
                    "order_date": None,
                    "sale_date": None,
                    "finance_sale_date": None,
                    "finance_rr_date": None,
                    "first_seen_at": None,
                    "last_seen_at": None,
                    "order_rows": 0,
                    "sale_rows": 0,
                    "finance_rows": 0,
                    "has_order": False,
                    "has_sale": False,
                    "has_finance": False,
                    "order_revenue": Decimal("0"),
                    "sale_revenue": Decimal("0"),
                    "finance_revenue": Decimal("0"),
                    "sale_for_pay": Decimal("0"),
                    "finance_for_pay": Decimal("0"),
                    "revenue_delta": Decimal("0"),
                    "for_pay_delta": Decimal("0"),
                    "status": "matched",
                    "payload": {"sources": []},
                }
            return buckets[key]

        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        core_index = self._build_core_sku_index(core_skus)

        delete_stmt = delete(MartFinanceReconciliation).where(
            MartFinanceReconciliation.account_id == account_id,
            MartFinanceReconciliation.stat_date >= date_from,
            MartFinanceReconciliation.stat_date <= date_to,
        )
        await session.execute(delete_stmt)

        for row in current_orders:
            if not row.get("srid"):
                continue
            bucket = get_bucket(row["srid"], row.get("nm_id"))
            bucket["has_order"] = True
            bucket["order_rows"] += 1
            bucket["order_id"] = bucket["order_id"] or row.get("order_id")
            bucket["vendor_code"] = bucket["vendor_code"] or row.get("supplier_article")
            bucket["barcode"] = bucket["barcode"] or row.get("barcode")
            order_date = self._mapping_date(row.get("date"))
            bucket["order_date"] = bucket["order_date"] or order_date
            seen_at = self._mapping_datetime(
                row.get("last_change_date")
            ) or self._mapping_datetime(row.get("date"))
            bucket["first_seen_at"] = (
                seen_at
                if bucket["first_seen_at"] is None
                else min(bucket["first_seen_at"], seen_at)
            )
            bucket["last_seen_at"] = (
                seen_at
                if bucket["last_seen_at"] is None
                else max(bucket["last_seen_at"], seen_at)
            )
            bucket["order_revenue"] += self._decimal(
                row.get("finished_price")
                or row.get("price_with_disc")
                or row.get("total_price")
            )
            bucket["payload"]["sources"].append("orders")

        for row in current_sales:
            if not row.get("srid"):
                continue
            bucket = get_bucket(row["srid"], row.get("nm_id"))
            bucket["has_sale"] = True
            bucket["sale_rows"] += 1
            bucket["order_id"] = bucket["order_id"] or row.get("order_id")
            bucket["vendor_code"] = bucket["vendor_code"] or row.get("supplier_article")
            bucket["barcode"] = bucket["barcode"] or row.get("barcode")
            sale_date = self._mapping_date(row.get("date"))
            bucket["sale_date"] = bucket["sale_date"] or sale_date
            seen_at = self._mapping_datetime(
                row.get("last_change_date")
            ) or self._mapping_datetime(row.get("date"))
            bucket["first_seen_at"] = (
                seen_at
                if bucket["first_seen_at"] is None
                else min(bucket["first_seen_at"], seen_at)
            )
            bucket["last_seen_at"] = (
                seen_at
                if bucket["last_seen_at"] is None
                else max(bucket["last_seen_at"], seen_at)
            )
            bucket["sale_revenue"] += self._decimal(
                row.get("finished_price")
                or row.get("price_with_disc")
                or row.get("total_price")
            )
            bucket["sale_for_pay"] += self._decimal(row.get("for_pay"))
            bucket["payload"]["sources"].append("sales")

        for row in finance_rows:
            if not self._is_reconcilable_finance_row(row):
                continue
            finance_barcode = self._finance_row_barcode(row)
            srid_key = row.srid or (
                f"finance-only:{row.nm_id or 'na'}:{finance_barcode or 'na'}:{row.vendor_code or 'na'}:{row.rrd_id}"
            )
            bucket = get_bucket(srid_key, row.nm_id)
            bucket["has_finance"] = True
            bucket["finance_rows"] += 1
            bucket["order_id"] = bucket["order_id"] or row.order_id
            bucket["vendor_code"] = bucket["vendor_code"] or row.vendor_code
            bucket["barcode"] = bucket["barcode"] or finance_barcode
            sale_date = self._local_datetime_date(
                row.sale_dt, timezone_name=timezone_name
            )
            bucket["finance_sale_date"] = bucket["finance_sale_date"] or sale_date
            bucket["finance_rr_date"] = bucket["finance_rr_date"] or row.rr_date
            seen_at = row.sale_dt
            if seen_at is not None:
                bucket["first_seen_at"] = (
                    seen_at
                    if bucket["first_seen_at"] is None
                    else min(bucket["first_seen_at"], seen_at)
                )
                bucket["last_seen_at"] = (
                    seen_at
                    if bucket["last_seen_at"] is None
                    else max(bucket["last_seen_at"], seen_at)
                )
            bucket["finance_revenue"] += self._signed_finance_amount(
                row, row.retail_amount
            )
            bucket["finance_for_pay"] += self._signed_finance_amount(row, row.for_pay)
            bucket["payload"]["sources"].append("finance")

        rows_to_insert: list[dict[str, Any]] = []
        for bucket in buckets.values():
            resolved_sku = self._resolve_core_sku(
                core_index,
                vendor_code=bucket["vendor_code"],
                nm_id=bucket["nm_id"],
                barcode=bucket["barcode"],
                tech_size=None,
            )
            bucket["sku_id"] = resolved_sku.id if resolved_sku is not None else None
            bucket["stat_date"] = (
                bucket["finance_sale_date"]
                or bucket["sale_date"]
                or bucket["order_date"]
                or bucket["finance_rr_date"]
                or date_to
            )
            bucket["revenue_delta"] = self._decimal(
                bucket["sale_revenue"]
            ) - self._decimal(bucket["finance_revenue"])
            bucket["for_pay_delta"] = self._decimal(
                bucket["sale_for_pay"]
            ) - self._decimal(bucket["finance_for_pay"])
            if bucket["has_sale"] and not bucket["has_finance"]:
                bucket["status"] = "missing_finance"
            elif bucket["has_finance"] and not bucket["has_sale"]:
                bucket["status"] = "missing_sale"
            elif (
                bucket["has_order"]
                and not bucket["has_sale"]
                and not bucket["has_finance"]
            ):
                bucket["status"] = "order_without_followup"
            elif abs(self._decimal(bucket["revenue_delta"])) > Decimal("1") or abs(
                self._decimal(bucket["for_pay_delta"])
            ) > Decimal("1"):
                bucket["status"] = "mismatch"
            else:
                bucket["status"] = "matched"
            rows_to_insert.append(bucket)

        await self.finance_repo.upsert_many(
            session,
            rows_to_insert,
            conflict_fields=["dedupe_key"],
        )
        return len(rows_to_insert)

    async def _refresh_account_expense_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> int:
        await session.execute(
            delete(MartAccountExpenseDaily).where(
                MartAccountExpenseDaily.account_id == account_id,
                MartAccountExpenseDaily.stat_date >= date_from,
                MartAccountExpenseDaily.stat_date <= date_to,
            )
        )
        expense_rows = list(
            (
                await session.execute(
                    select(MartExpenseDaily).where(
                        MartExpenseDaily.account_id == account_id,
                        MartExpenseDaily.stat_date >= date_from,
                        MartExpenseDaily.stat_date <= date_to,
                        MartExpenseDaily.is_allocated_to_sku.is_(False),
                    )
                )
            ).scalars()
        )
        seller_rollup_rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= date_from,
                        MartSKUDaily.stat_date <= date_to,
                    )
                )
            ).scalars()
        )
        normalized_expense_rows: list[Any] = []
        for row in expense_rows:
            if getattr(row, "stat_date", None) is not None:
                normalized_expense_rows.append(row)
                continue
            details = self._finance_expense_details(row, sku_id=None)
            normalized_expense_rows.extend(
                SimpleNamespace(**entry)
                for entry in details["entries"]
                if not bool(entry.get("is_allocated_to_sku"))
            )
        buckets: dict[date, dict[str, Any]] = {}

        def get_bucket(stat_date: date) -> dict[str, Any]:
            if stat_date not in buckets:
                buckets[stat_date] = {
                    "account_id": account_id,
                    "stat_date": stat_date,
                    "source_rows": 0,
                    "wb_commission": Decimal("0"),
                    "payment_processing": Decimal("0"),
                    "pvz_reward": Decimal("0"),
                    "wb_logistics": Decimal("0"),
                    "wb_logistics_rebill": Decimal("0"),
                    "acceptance": Decimal("0"),
                    "penalty": Decimal("0"),
                    "deduction": Decimal("0"),
                    "marketing_deduction": Decimal("0"),
                    "loyalty": Decimal("0"),
                    "other_wb_expenses": Decimal("0"),
                    "total_wb_expenses": Decimal("0"),
                    "commission": Decimal("0"),
                    "acquiring_fee": Decimal("0"),
                    "logistics": Decimal("0"),
                    "paid_acceptance": Decimal("0"),
                    "storage": Decimal("0"),
                    "penalties": Decimal("0"),
                    "deductions": Decimal("0"),
                    "additional_payments": Decimal("0"),
                    "ad_spend_operational": Decimal("0"),
                    "ad_spend_finance": Decimal("0"),
                    "ad_spend_final": Decimal("0"),
                    "ad_spend_source": AD_SPEND_SOURCE_NONE,
                    "ad_spend_delta": Decimal("0"),
                    "seller_cogs": Decimal("0"),
                    "seller_other_expense": Decimal("0"),
                    "total_seller_expenses": Decimal("0"),
                    "net_profit_after_all_expenses": Decimal("0"),
                    "total_expense": Decimal("0"),
                    "payload": {"sources": [], "rrdIds": []},
                }
            return buckets[stat_date]

        for row in normalized_expense_rows:
            bucket = get_bucket(row.stat_date)
            bucket["source_rows"] += 1
            signed_amount = self._decimal(row.amount)
            if row.amount_sign == EXPENSE_SIGN_INCOME:
                signed_amount *= Decimal("-1")
            category = str(row.expense_category)
            if category in bucket:
                bucket[category] += signed_amount
            elif category == EXPENSE_CATEGORY_ADDITIONAL_PAYMENT:
                bucket["additional_payments"] += signed_amount
            elif category == EXPENSE_CATEGORY_UNCLASSIFIED:
                bucket["other_wb_expenses"] += signed_amount
            if row.rrd_id is not None:
                bucket["payload"]["rrdIds"].append(row.rrd_id)
            bucket["payload"]["sources"].append(
                str(row.expense_source or EXPENSE_SOURCE_FINANCE_REPORT)
            )
        for row in seller_rollup_rows:
            bucket = get_bucket(row.stat_date)
            bucket["seller_cogs"] += self._decimal(getattr(row, "seller_cogs", None))
            bucket["seller_other_expense"] += self._decimal(
                getattr(row, "seller_other_expense", None)
            )
            bucket["total_seller_expenses"] += self._decimal(
                getattr(row, "total_seller_expenses", None)
            )
            bucket["additional_payments"] += self._decimal(
                getattr(row, "additional_payments", None)
            )
            bucket["net_profit_after_all_expenses"] += self._decimal(
                getattr(row, "net_profit_after_all_expenses", None)
            )
            bucket["payload"]["seller_cost_sku_rows"] = (
                int(bucket["payload"].get("seller_cost_sku_rows") or 0) + 1
            )
            bucket["payload"]["sources"].append("mart_sku_daily")

        rows_to_insert: list[dict[str, Any]] = []
        for bucket in buckets.values():
            bucket["ad_spend_finance"] = self._decimal(bucket["marketing_deduction"])
            bucket["total_seller_expenses"] = total_seller_expenses(
                SimpleNamespace(**bucket)
            )
            bucket["total_wb_expenses"] = normalized_wb_expenses_total(
                SimpleNamespace(**bucket)
            )
            self._apply_compatibility_expense_fields(bucket)
            ad_fields = self._ad_fields_for_bucket(bucket)
            bucket.update(ad_fields)
            bucket["total_expense"] = self._decimal(
                bucket["total_wb_expenses"]
            ) + self._decimal(bucket["ad_spend_final"])
            rows_to_insert.append(bucket)

        await self.account_expense_repo.upsert_many(
            session,
            rows_to_insert,
            conflict_fields=["dedupe_key"],
        )
        return len(rows_to_insert)

    async def _refresh_reconciliation_daily(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> int:
        await session.execute(
            delete(MartReconciliationDaily).where(
                MartReconciliationDaily.account_id == account_id,
                MartReconciliationDaily.stat_date >= date_from,
                MartReconciliationDaily.stat_date <= date_to,
            )
        )

        sku_rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.stat_date >= date_from,
                        MartSKUDaily.stat_date <= date_to,
                        MartSKUDaily.sku_id.is_not(None),
                    )
                )
            ).scalars()
        )
        if not sku_rows:
            return 0

        core_skus = list(
            (
                await session.execute(
                    select(CoreSKU).where(
                        CoreSKU.account_id == account_id,
                        CoreSKU.is_active.is_(True),
                    )
                )
            ).scalars()
        )
        core_index = self._build_core_sku_index(core_skus)
        order_rows = await self._load_current_orders(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        sale_rows = await self._load_current_sales(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
        )
        finance_rows = list(
            (
                await session.execute(
                    select(MartFinanceReconciliation).where(
                        MartFinanceReconciliation.account_id == account_id,
                        MartFinanceReconciliation.stat_date >= date_from,
                        MartFinanceReconciliation.stat_date <= date_to,
                        MartFinanceReconciliation.sku_id.is_not(None),
                    )
                )
            ).scalars()
        )

        order_amounts: dict[tuple[date, int], Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        order_qtys: dict[tuple[date, int], int] = defaultdict(int)
        for row in order_rows:
            stat_date = self._mapping_date(row.get("date"))
            if stat_date is None:
                continue
            resolved_sku = self._resolve_core_sku(
                core_index,
                vendor_code=row.get("supplier_article"),
                nm_id=row.get("nm_id"),
                barcode=row.get("barcode"),
                tech_size=None,
            )
            if resolved_sku is None:
                continue
            key = (stat_date, resolved_sku.id)
            order_qtys[key] += 0 if row.get("is_cancel") else 1
            order_amounts[key] += self._decimal(
                row.get("finished_price")
                or row.get("price_with_disc")
                or row.get("total_price")
            )

        sales_amounts: dict[tuple[date, int], Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        sales_qtys: dict[tuple[date, int], int] = defaultdict(int)
        returns_qtys: dict[tuple[date, int], int] = defaultdict(int)
        returns_amounts: dict[tuple[date, int], Decimal] = defaultdict(
            lambda: Decimal("0")
        )
        for row in sale_rows:
            stat_date = self._mapping_date(row.get("date"))
            if stat_date is None:
                continue
            resolved_sku = self._resolve_core_sku(
                core_index,
                vendor_code=row.get("supplier_article"),
                nm_id=row.get("nm_id"),
                barcode=row.get("barcode"),
                tech_size=None,
            )
            if resolved_sku is None:
                continue
            key = (stat_date, resolved_sku.id)
            value = self._decimal(
                row.get("finished_price")
                or row.get("price_with_disc")
                or row.get("total_price")
            )
            sign = (
                -1
                if row.get("is_cancel") or self._decimal(row.get("for_pay")) < 0
                else 1
            )
            if sign > 0:
                sales_qtys[key] += 1
                sales_amounts[key] += value
            else:
                returns_qtys[key] += 1
                returns_amounts[key] += abs(value)

        finance_map: dict[tuple[date, int], dict[str, Decimal | int | bool]] = (
            defaultdict(
                lambda: {
                    "finance_qty": 0,
                    "finance_revenue": Decimal("0"),
                    "finance_for_pay": Decimal("0"),
                    "has_missing_finance": False,
                    "has_missing_sale": False,
                }
            )
        )
        for row in finance_rows:
            if row.sku_id is None:
                continue
            key = (row.stat_date, row.sku_id)
            finance_map[key]["finance_qty"] = int(
                finance_map[key]["finance_qty"]
            ) + int(row.finance_rows or 0)
            finance_map[key]["finance_revenue"] = self._decimal(
                finance_map[key]["finance_revenue"]
            ) + self._decimal(row.finance_revenue)
            finance_map[key]["finance_for_pay"] = self._decimal(
                finance_map[key]["finance_for_pay"]
            ) + self._decimal(row.finance_for_pay)
            if row.status == "missing_finance":
                finance_map[key]["has_missing_finance"] = True
            if row.status == "missing_sale":
                finance_map[key]["has_missing_sale"] = True

        rows_to_insert: list[dict[str, Any]] = []
        for row in sku_rows:
            if row.sku_id is None:
                continue
            key = (row.stat_date, row.sku_id)
            finance_state = finance_map[key]
            current_price = row.current_discounted_price or row.current_price
            has_order_without_sale = (
                (order_qtys[key] or int(row.ordered_units or 0)) > 0
                and (sales_qtys[key] or int(row.final_sales_qty or 0)) == 0
                and (returns_qtys[key] or int(row.final_return_qty or 0)) == 0
            )
            has_sale_without_finance = bool(finance_state["has_missing_finance"]) or (
                (sales_qtys[key] or int(row.final_sales_qty or 0)) > 0
                and int(finance_state["finance_qty"]) == 0
            )
            has_finance_without_sale = bool(finance_state["has_missing_sale"]) or (
                int(finance_state["finance_qty"]) > 0
                and (sales_qtys[key] or int(row.final_sales_qty or 0)) == 0
            )
            has_stock_without_sales = (
                self._decimal(row.closing_stock_qty) > 0
                and (sales_qtys[key] or int(row.final_sales_qty or 0)) == 0
            )
            has_ad_spend_without_sales = (
                self._decimal(row.ad_spend) > 0
                and (sales_qtys[key] or int(row.final_sales_qty or 0)) == 0
            )
            has_price_anomaly = self._decimal(current_price) <= 0
            age_days = max((utcnow().date() - row.stat_date).days, 0)
            status_bucket, status_reason = self._reconciliation_bucket(
                age_days=age_days,
                has_order_without_sale=has_order_without_sale,
                has_sale_without_finance=has_sale_without_finance,
                has_finance_without_sale=has_finance_without_sale,
                has_stock_without_sales=has_stock_without_sales,
                has_ad_spend_without_sales=has_ad_spend_without_sales,
                has_price_anomaly=has_price_anomaly,
            )
            rows_to_insert.append(
                {
                    "account_id": account_id,
                    "stat_date": row.stat_date,
                    "sku_id": row.sku_id,
                    "nm_id": row.nm_id,
                    "vendor_code": row.vendor_code,
                    "barcode": row.barcode,
                    "title": row.title,
                    "brand": row.brand,
                    "subject_name": row.subject_name,
                    "orders_qty": order_qtys[key] or int(row.ordered_units or 0),
                    "orders_amount": order_amounts[key],
                    "sales_qty": sales_qtys[key] or int(row.final_sales_qty or 0),
                    "sales_amount": sales_amounts[key]
                    or self._decimal(row.final_revenue),
                    "returns_qty": returns_qtys[key] or int(row.final_return_qty or 0),
                    "returns_amount": returns_amounts[key],
                    "finance_qty": int(finance_state["finance_qty"]),
                    "finance_revenue": self._decimal(finance_state["finance_revenue"]),
                    "finance_for_pay": self._decimal(finance_state["finance_for_pay"]),
                    "ad_spend_operational": self._decimal(
                        getattr(row, "ad_spend_operational", None)
                    ),
                    "ad_spend_finance": self._decimal(
                        getattr(row, "ad_spend_finance", None)
                    ),
                    "ad_spend_final": self._decimal(
                        getattr(row, "ad_spend_final", None)
                    ),
                    "ad_spend_source": getattr(row, "ad_spend_source", None),
                    "ad_spend_delta": self._decimal(
                        getattr(row, "ad_spend_delta", None)
                    ),
                    "ad_spend": self._decimal(row.ad_spend),
                    "ad_orders": int(row.funnel_orders or 0),
                    "opening_stock_qty": row.opening_stock_qty,
                    "closing_stock_qty": row.closing_stock_qty,
                    "avg_sale_price": row.avg_sale_price,
                    "current_price": row.current_price,
                    "current_discounted_price": row.current_discounted_price,
                    "revenue_delta": self._decimal(row.final_revenue)
                    - self._decimal(finance_state["finance_revenue"]),
                    "for_pay_delta": self._decimal(row.final_for_pay)
                    - self._decimal(finance_state["finance_for_pay"]),
                    "status_bucket": status_bucket,
                    "status_reason": status_reason,
                    "has_order_without_sale": has_order_without_sale,
                    "has_sale_without_finance": has_sale_without_finance,
                    "has_finance_without_sale": has_finance_without_sale,
                    "has_stock_without_sales": has_stock_without_sales,
                    "has_ad_spend_without_sales": has_ad_spend_without_sales,
                    "has_price_anomaly": has_price_anomaly,
                    "payload": {
                        "sources": ["orders", "sales", "finance", "marts"],
                        "finalRevenueSource": row.final_revenue_source,
                        "ageDays": age_days,
                    },
                }
            )

        await self.reconciliation_daily_repo.upsert_many(
            session,
            rows_to_insert,
            conflict_fields=["dedupe_key"],
        )
        return len(rows_to_insert)
