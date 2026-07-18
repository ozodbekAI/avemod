from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import sqlalchemy as sa
from sqlalchemy import and_, func, or_, select

from app.core.current_state import orders_current_subquery, sales_current_subquery
from app.core.db import SessionLocal
from app.core.issue_refs import extract_issue_refs
from app.models.data_quality import DataQualityIssue
from app.models.finance import WBRealizationReportRow
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily
from app.models.prices import WBPrice, WBPriceSize
from app.models.product_cards import CoreSKU, WBProductCard
from app.models.stocks import WBStockSnapshotRow
from app.models.sync import WBSyncCursor, WBSyncRun


BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_EMAIL = "audit-user@example.invalid"


def dec(value: object) -> Decimal:
    return Decimal(str(value or 0))


def pct(part: object, whole: object) -> float | None:
    whole_decimal = dec(whole)
    if whole_decimal <= 0:
        return None
    return float((dec(part) / whole_decimal) * Decimal("100"))


def json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    return value


def issue_classification_status(issue: DataQualityIssue) -> str:
    payload = dict(issue.payload or {})
    return str(payload.get("classificationStatus") or payload.get("resolutionStatus") or "").lower()


def issue_is_classified_for_acceptance(issue: DataQualityIssue) -> bool:
    return issue_classification_status(issue) in {"classified", "ignored", "mapped"}


def blocking_open_issue_count(issues: list[DataQualityIssue]) -> int:
    return sum(
        1
        for issue in issues
        if str(issue.severity or "").lower() in {"error", "critical"}
        and not issue_is_classified_for_acceptance(issue)
    )


def finance_report_revenue_total(rows: list[WBRealizationReportRow]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        doc_type = (row.doc_type_name or "").strip().lower()
        is_reconcilable = row.is_reconcilable is True or (
            row.is_reconcilable is None and doc_type in {"продажа", "возврат", "sale", "return"}
        )
        if is_reconcilable:
            total += dec(row.retail_amount)
    return total


def _profitability_bucket(rows: list[MartSKUDaily]) -> dict[str, Any]:
    bucket: dict[str, Any] = {
        "sku_id": rows[0].sku_id if rows else None,
        "nm_id": rows[0].nm_id if rows else None,
        "vendor_code": rows[0].vendor_code if rows else None,
        "barcode": rows[0].barcode if rows else None,
        "title": rows[0].title if rows else None,
        "brand": rows[0].brand if rows else None,
        "subject_name": rows[0].subject_name if rows else None,
        "finance_rows": 0,
        "gross_units": 0,
        "return_units": 0,
        "net_units": 0,
        "realized_revenue": Decimal("0"),
        "for_pay": Decimal("0"),
        "commission": Decimal("0"),
        "acquiring_fee": Decimal("0"),
        "logistics": Decimal("0"),
        "paid_acceptance": Decimal("0"),
        "storage": Decimal("0"),
        "penalties": Decimal("0"),
        "deductions": Decimal("0"),
        "additional_payments": Decimal("0"),
        "ad_spend": Decimal("0"),
        "estimated_cogs": Decimal("0"),
        "matched_cost_rows": 0,
        "cost_required_rows": 0,
        "cost_ready_rows": 0,
        "real_cost_ready_rows": 0,
        "placeholder_cost_rows": 0,
        "closing_stock_qty": None,
        "cost_sources": set(),
    }
    for row in rows:
        bucket["finance_rows"] += int(row.finance_rows or 0)
        bucket["gross_units"] += int(row.final_sales_qty or 0)
        bucket["return_units"] += int(row.final_return_qty or 0)
        bucket["net_units"] += int(row.final_net_qty or 0)
        bucket["realized_revenue"] += dec(row.final_revenue)
        bucket["for_pay"] += dec(row.final_for_pay)
        bucket["commission"] += dec(row.commission)
        bucket["acquiring_fee"] += dec(row.acquiring_fee)
        bucket["logistics"] += dec(row.logistics)
        bucket["paid_acceptance"] += dec(row.paid_acceptance)
        bucket["storage"] += dec(row.storage)
        bucket["penalties"] += dec(row.penalties)
        bucket["deductions"] += dec(row.deductions)
        bucket["additional_payments"] += dec(row.additional_payments)
        bucket["ad_spend"] += dec(row.ad_spend)
        bucket["estimated_cogs"] += dec(row.estimated_cogs)
        if row.closing_stock_qty is not None:
            bucket["closing_stock_qty"] = row.closing_stock_qty
        requires_cost = bool(
            int(row.final_sales_qty or 0)
            or int(row.final_return_qty or 0)
            or int(row.final_net_qty or 0)
            or row.final_revenue
            or row.sale_rows
            or row.finance_rows
        )
        if requires_cost:
            bucket["cost_required_rows"] += 1
        if row.has_manual_cost:
            bucket["matched_cost_rows"] += 1
            if requires_cost:
                bucket["cost_ready_rows"] += 1
            if row.has_real_manual_cost and requires_cost:
                bucket["real_cost_ready_rows"] += 1
            if row.has_placeholder_cost and requires_cost:
                bucket["placeholder_cost_rows"] += 1
            bucket["cost_sources"].add(row.cost_source or row.final_revenue_source or "unknown")
    has_complete_manual_cost = bucket["cost_required_rows"] > 0 and bucket["cost_ready_rows"] == bucket["cost_required_rows"]
    has_complete_real_cost = bucket["cost_required_rows"] > 0 and bucket["real_cost_ready_rows"] == bucket["cost_required_rows"]
    has_placeholder_cost = bucket["placeholder_cost_rows"] > 0
    estimated_profit = None
    margin_percent = None
    roi_percent = None
    if has_complete_manual_cost:
        estimated_profit = (
            bucket["realized_revenue"]
            + bucket["additional_payments"]
            - bucket["commission"]
            - bucket["acquiring_fee"]
            - bucket["logistics"]
            - bucket["paid_acceptance"]
            - bucket["storage"]
            - bucket["penalties"]
            - bucket["deductions"]
            - bucket["ad_spend"]
            - bucket["estimated_cogs"]
        )
        if bucket["realized_revenue"] > 0:
            margin_percent = float((estimated_profit / bucket["realized_revenue"]) * Decimal("100"))
        if bucket["estimated_cogs"] > 0:
            roi_percent = float((estimated_profit / bucket["estimated_cogs"]) * Decimal("100"))
    return {
        "sku_id": bucket["sku_id"],
        "nm_id": bucket["nm_id"],
        "vendor_code": bucket["vendor_code"],
        "barcode": bucket["barcode"],
        "title": bucket["title"],
        "brand": bucket["brand"],
        "subject_name": bucket["subject_name"],
        "finance_rows": bucket["finance_rows"],
        "gross_units": bucket["gross_units"],
        "return_units": bucket["return_units"],
        "net_units": bucket["net_units"],
        "realized_revenue": float(bucket["realized_revenue"]),
        "for_pay": float(bucket["for_pay"]),
        "commission": float(bucket["commission"]),
        "acquiring_fee": float(bucket["acquiring_fee"]),
        "logistics": float(bucket["logistics"]),
        "paid_acceptance": float(bucket["paid_acceptance"]),
        "storage": float(bucket["storage"]),
        "penalties": float(bucket["penalties"]),
        "deductions": float(bucket["deductions"]),
        "additional_payments": float(bucket["additional_payments"]),
        "ad_spend": float(bucket["ad_spend"]),
        "estimated_cogs": float(bucket["estimated_cogs"]),
        "matched_cost_rows": bucket["matched_cost_rows"],
        "estimated_profit": float(estimated_profit) if estimated_profit is not None else None,
        "margin_percent": margin_percent,
        "roi_percent": roi_percent,
        "drr_percent": float((bucket["ad_spend"] / bucket["realized_revenue"]) * Decimal("100")) if bucket["realized_revenue"] > 0 else None,
        "closing_stock_qty": float(dec(bucket["closing_stock_qty"])) if bucket["closing_stock_qty"] is not None else None,
        "has_manual_cost": has_complete_manual_cost,
        "has_real_manual_cost": has_complete_real_cost,
        "has_placeholder_cost": has_placeholder_cost,
        "business_trusted": has_complete_real_cost,
        "cost_source": next(iter(bucket["cost_sources"])) if len(bucket["cost_sources"]) == 1 else ("mixed" if bucket["cost_sources"] else None),
    }


async def run_audit(
    *,
    account_id: int,
    nm_id: int,
    sku_id: int,
    barcode: str,
    date_from: date,
    date_to: date,
    wide_from: date,
    email: str,
    password: str,
    output: Path,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "scope": {
            "account_id": account_id,
            "nm_id": nm_id,
            "sku_id": sku_id,
            "barcode": barcode,
            "date_from": date_from,
            "date_to": date_to,
            "wide_from": wide_from,
        },
        "row_level_checks": {},
        "endpoint_comparisons": {},
    }

    with httpx.Client(timeout=httpx.Timeout(60.0, connect=5.0), follow_redirects=True) as client:
        login = client.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        def api_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
            response = client.get(f"{BASE_URL}{path}", params=params, headers=headers)
            response.raise_for_status()
            return response.json()

        api_core = api_get(
            "/core-sku",
            {
                "account_id": account_id,
                "barcode": barcode,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "limit": 10,
                "offset": 0,
            },
        )
        api_audit = api_get(
            "/dashboard/article-audit",
            {
                "account_id": account_id,
                "nm_id": nm_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        api_profit = api_get(
            "/dashboard/sku-profitability",
            {
                "account_id": account_id,
                "barcode": barcode,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "limit": 10,
                "offset": 0,
            },
        )
        api_health = api_get(
            "/dashboard/data-health",
            {
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )

    async with SessionLocal() as session:
        orders_current = orders_current_subquery()
        sales_current = sales_current_subquery()

        orders = (
            await session.execute(
                select(orders_current).where(
                    orders_current.c.account_id == account_id,
                    orders_current.c.nm_id == nm_id,
                    orders_current.c.date >= datetime.combine(date_from, time.min),
                    orders_current.c.date <= datetime.combine(date_to, time.max),
                )
            )
        ).mappings().all()
        sales = (
            await session.execute(
                select(sales_current).where(
                    sales_current.c.account_id == account_id,
                    sales_current.c.nm_id == nm_id,
                    sales_current.c.date >= datetime.combine(date_from, time.min),
                    sales_current.c.date <= datetime.combine(date_to, time.max),
                )
            )
        ).mappings().all()
        wide_sales = (
            await session.execute(
                select(sales_current).where(
                    sales_current.c.account_id == account_id,
                    sales_current.c.nm_id == nm_id,
                    sales_current.c.date >= datetime.combine(wide_from, time.min),
                    sales_current.c.date <= datetime.combine(date_to, time.max),
                )
            )
        ).mappings().all()
        finance_rows = list(
            (
                await session.execute(
                    select(WBRealizationReportRow).where(
                        WBRealizationReportRow.account_id == account_id,
                        WBRealizationReportRow.nm_id == nm_id,
                        WBRealizationReportRow.rr_date >= date_from,
                        WBRealizationReportRow.rr_date <= date_to,
                    )
                )
            ).scalars()
        )
        mart_rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.nm_id == nm_id,
                        MartSKUDaily.stat_date >= date_from,
                        MartSKUDaily.stat_date <= date_to,
                    ).order_by(MartSKUDaily.stat_date.asc(), MartSKUDaily.sku_id.asc())
                )
            ).scalars()
        )
        wide_mart_rows = list(
            (
                await session.execute(
                    select(MartSKUDaily).where(
                        MartSKUDaily.account_id == account_id,
                        MartSKUDaily.nm_id == nm_id,
                        MartSKUDaily.stat_date >= wide_from,
                        MartSKUDaily.stat_date <= date_to,
                    ).order_by(MartSKUDaily.stat_date.asc(), MartSKUDaily.sku_id.asc())
                )
            ).scalars()
        )
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
        price = (
            await session.execute(select(WBPrice).where(WBPrice.account_id == account_id, WBPrice.nm_id == nm_id))
        ).scalar_one_or_none()
        product_card = (
            await session.execute(
                select(WBProductCard).where(
                    WBProductCard.account_id == account_id,
                    WBProductCard.nm_id == nm_id,
                )
            )
        ).scalar_one_or_none()
        latest_stock_row = (
            await session.execute(
                select(WBStockSnapshotRow)
                .where(
                    WBStockSnapshotRow.account_id == account_id,
                    WBStockSnapshotRow.nm_id == nm_id,
                )
                .order_by(WBStockSnapshotRow.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        price_sizes = list(
            (
                await session.execute(
                    select(WBPriceSize).where(WBPriceSize.account_id == account_id, WBPriceSize.nm_id == nm_id)
                )
            ).scalars()
        )
        matched_cost = (
            await session.execute(
                select(ManualCost)
                .where(
                    ManualCost.account_id == account_id,
                    ManualCost.sku_id == sku_id,
                    or_(ManualCost.valid_from.is_(None), ManualCost.valid_from <= date_to),
                    or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= date_from),
                )
                .order_by(ManualCost.valid_from.desc().nullslast(), ManualCost.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        sales_by_key: dict[tuple[date, str], list[dict[str, Any]]] = defaultdict(list)
        for row in wide_sales:
            if row.get("date") and row.get("barcode"):
                sales_by_key[(row["date"].date(), row["barcode"])].append(row)
        mart_by_key = {
            (row.stat_date, row.barcode): row
            for row in wide_mart_rows
            if row.stat_date is not None and row.barcode
        }
        sample_keys = sorted(set(sales_by_key).intersection(mart_by_key))[:2]
        for stat_day, sample_barcode in sample_keys:
            mart_row = mart_by_key[(stat_day, sample_barcode)]
            sales_group = sales_by_key[(stat_day, sample_barcode)]
            operational_sales_qty = 0
            operational_return_qty = 0
            operational_revenue = Decimal("0")
            operational_for_pay = Decimal("0")
            for sale in sales_group:
                sign = -1 if sale.get("is_cancel") or dec(sale.get("for_pay")) < 0 else 1
                if sign > 0:
                    operational_sales_qty += 1
                else:
                    operational_return_qty += 1
                operational_revenue += dec(sale.get("finished_price") or sale.get("price_with_disc") or sale.get("total_price"))
                operational_for_pay += dec(sale.get("for_pay"))
            total_unit_cost = dec(mart_row.cost_price) + dec(mart_row.packaging_cost) + dec(mart_row.inbound_logistics_cost)
            estimated_cogs = total_unit_cost * Decimal(mart_row.final_net_qty)
            estimated_profit_before_ads = (
                operational_revenue
                - dec(mart_row.commission)
                - dec(mart_row.logistics)
                - dec(mart_row.storage)
                - dec(mart_row.paid_acceptance)
                - dec(mart_row.acquiring_fee)
                - dec(mart_row.penalties)
                - dec(mart_row.deductions)
                - estimated_cogs
                + dec(mart_row.additional_payments)
            )
            estimated_profit_after_ads = estimated_profit_before_ads - dec(mart_row.ad_spend)
            report["row_level_checks"][f"{stat_day}_{sample_barcode}"] = {
                "api": {
                    "operational_sales_qty": mart_row.operational_sales_qty,
                    "operational_return_qty": mart_row.operational_return_qty,
                    "operational_revenue": mart_row.operational_revenue,
                    "operational_for_pay": mart_row.operational_for_pay,
                    "estimated_cogs": mart_row.estimated_cogs,
                    "estimated_profit_before_ads": mart_row.estimated_profit_before_ads,
                    "estimated_profit_after_ads": mart_row.estimated_profit_after_ads,
                },
                "manual": {
                    "operational_sales_qty": operational_sales_qty,
                    "operational_return_qty": operational_return_qty,
                    "operational_revenue": operational_revenue,
                    "operational_for_pay": operational_for_pay,
                    "estimated_cogs": estimated_cogs,
                    "estimated_profit_before_ads": estimated_profit_before_ads,
                    "estimated_profit_after_ads": estimated_profit_after_ads,
                },
                "match": {
                    "operational_sales_qty": mart_row.operational_sales_qty == operational_sales_qty,
                    "operational_return_qty": mart_row.operational_return_qty == operational_return_qty,
                    "operational_revenue": dec(mart_row.operational_revenue) == operational_revenue,
                    "operational_for_pay": dec(mart_row.operational_for_pay) == operational_for_pay,
                    "estimated_cogs": dec(mart_row.estimated_cogs) == estimated_cogs,
                    "estimated_profit_before_ads": dec(mart_row.estimated_profit_before_ads) == estimated_profit_before_ads,
                    "estimated_profit_after_ads": dec(mart_row.estimated_profit_after_ads) == estimated_profit_after_ads,
                },
            }

        issue_ids: set[int] = set()
        for issue in open_issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if issue_sku_id == sku_id or issue_nm_id == nm_id:
                issue_ids.add(issue.id)

        core_manual = {
            "id": sku_id,
            "nm_id": nm_id,
            "barcode": barcode,
            "current_price": min((dec(item.price) for item in price_sizes if item.price is not None), default=None),
            "current_discounted_price": min((dec(item.discounted_price) for item in price_sizes if item.discounted_price is not None), default=None),
            "seller_discount": price.discount if price else None,
            "club_discount": price.club_discount if price else None,
            "has_manual_cost": matched_cost is not None,
            "cost_price": matched_cost.cost_price if matched_cost else None,
            "packaging_cost": matched_cost.packaging_cost if matched_cost else None,
            "inbound_logistics_cost": matched_cost.inbound_logistics_cost if matched_cost else None,
            "total_unit_cost": (
                dec(matched_cost.cost_price or matched_cost.unit_cost)
                + dec(matched_cost.packaging_cost)
                + dec(matched_cost.inbound_logistics_cost)
            ) if matched_cost else None,
            "open_issue_count": len(issue_ids),
            "has_open_issues": bool(issue_ids),
            "last_30d_sales_qty": sum(int(row.final_sales_qty or 0) for row in mart_rows if row.sku_id == sku_id),
            "last_30d_revenue": sum((dec(row.final_revenue) for row in mart_rows if row.sku_id == sku_id), start=Decimal("0")),
        }
        report["endpoint_comparisons"]["core_sku"] = {
            "api": api_core["items"][0],
            "manual_subset": core_manual,
        }

        operations_dates = [row["date"] for row in orders if row.get("date") is not None] + [
            row["date"] for row in sales if row.get("date") is not None
        ]
        latest_order = max(
            orders,
            key=lambda row: row.get("last_change_date") or row.get("date") or datetime.min,
            default=None,
        )
        latest_sale = max(
            sales,
            key=lambda row: row.get("last_change_date") or row.get("date") or datetime.min,
            default=None,
        )
        identity_barcode = (
            (latest_stock_row.barcode if latest_stock_row is not None else None)
            or (latest_sale.get("barcode") if latest_sale else None)
            or (latest_order.get("barcode") if latest_order else None)
        )
        representative_sku = (
            await session.execute(
                select(CoreSKU).where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.nm_id == nm_id,
                    CoreSKU.barcode == identity_barcode,
                    CoreSKU.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        representative_cost = None
        if representative_sku is not None:
            representative_cost = (
                await session.execute(
                    select(ManualCost)
                    .where(
                        ManualCost.account_id == account_id,
                        ManualCost.sku_id == representative_sku.id,
                        or_(ManualCost.valid_from.is_(None), ManualCost.valid_from <= date_to),
                        or_(ManualCost.valid_to.is_(None), ManualCost.valid_to >= date_from),
                    )
                    .order_by(ManualCost.valid_from.desc().nullslast(), ManualCost.id.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
        revenue = sum((dec(row.final_revenue) for row in mart_rows), start=Decimal("0"))
        for_pay = sum((dec(row.final_for_pay) for row in mart_rows), start=Decimal("0"))
        wb_expenses = sum(
            (
                dec(row.commission)
                + dec(row.acquiring_fee)
                + dec(row.logistics)
                + dec(row.storage)
                + dec(row.paid_acceptance)
                + dec(row.penalties)
                + dec(row.deductions)
                - dec(row.additional_payments)
                for row in mart_rows
            ),
            start=Decimal("0"),
        )
        ad_spend = sum((dec(row.ad_spend) for row in mart_rows), start=Decimal("0"))
        estimated_cogs = sum((dec(row.estimated_cogs) for row in mart_rows if row.estimated_cogs is not None), start=Decimal("0"))
        estimated_profit_before_ads = sum(
            (dec(row.estimated_profit_before_ads) for row in mart_rows if row.estimated_profit_before_ads is not None),
            start=Decimal("0"),
        )
        estimated_profit_after_ads = sum(
            (dec(row.estimated_profit_after_ads) for row in mart_rows if row.estimated_profit_after_ads is not None),
            start=Decimal("0"),
        )
        has_cost_for_all = all(row.has_manual_cost for row in mart_rows)
        issue_rows = []
        mart_sku_ids = {row.sku_id for row in mart_rows if row.sku_id is not None}
        for issue in open_issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            if issue_nm_id == nm_id or issue_sku_id in mart_sku_ids:
                issue_rows.append(issue)
        pending_count = warning_count = error_count = ignored_count = 0
        for issue in issue_rows:
            payload = issue.payload or {}
            classification_status = str(payload.get("classificationStatus") or "").lower()
            age_bucket = str(payload.get("ageBucket") or "").lower()
            if classification_status == "ignored":
                ignored_count += 1
                continue
            if age_bucket == "pending":
                pending_count += 1
            elif age_bucket == "warning" or issue.severity == "warning":
                warning_count += 1
            elif issue.severity == "error":
                error_count += 1
        report["endpoint_comparisons"]["article_audit"] = {
            "api_subset": {
                "operations": api_audit["operations"],
                "daily_economics": api_audit["daily_economics"],
                "finance": api_audit["finance"],
                "manual_cost": api_audit["manual_cost"],
                "reconciliation": api_audit["reconciliation"],
            },
            "manual_subset": {
                "operations": {
                    "orders_count": len(orders),
                    "cancelled_orders_count": sum(1 for row in orders if row.get("is_cancel")),
                    "orders_gross_amount": float(sum((dec(row.get("total_price")) for row in orders), start=Decimal("0"))),
                    "orders_finished_amount": float(sum((dec(row.get("finished_price")) for row in orders), start=Decimal("0"))),
                    "sales_count": sum(1 for row in sales if dec(row.get("total_price")) >= 0),
                    "returns_count": sum(1 for row in sales if dec(row.get("total_price")) < 0),
                    "sales_gross_amount": float(sum((dec(row.get("total_price")) for row in sales), start=Decimal("0"))),
                    "sales_for_pay": float(sum((dec(row.get("for_pay")) for row in sales), start=Decimal("0"))),
                    "first_event_at": min(operations_dates) if operations_dates else None,
                    "last_event_at": max(operations_dates) if operations_dates else None,
                },
                "daily_economics": {
                    "days_count": len({row.stat_date for row in mart_rows}),
                    "sales_qty": sum((row.final_sales_qty or 0) for row in mart_rows),
                    "returns_qty": sum((row.final_return_qty or 0) for row in mart_rows),
                    "net_qty": sum((row.final_net_qty or 0) for row in mart_rows),
                    "revenue": float(revenue),
                    "for_pay": float(for_pay),
                    "wb_expenses": float(wb_expenses),
                    "ad_spend": float(ad_spend),
                    "estimated_cogs": float(estimated_cogs) if has_cost_for_all else None,
                    "estimated_profit_before_ads": float(estimated_profit_before_ads) if has_cost_for_all else None,
                    "estimated_profit_after_ads": float(estimated_profit_after_ads) if has_cost_for_all else None,
                    "margin_percent": float((estimated_profit_after_ads / revenue) * Decimal("100")) if revenue > 0 and has_cost_for_all else None,
                    "roi_percent": float((estimated_profit_after_ads / estimated_cogs) * Decimal("100")) if estimated_cogs > 0 and has_cost_for_all else None,
                    "drr_percent": float((ad_spend / revenue) * Decimal("100")) if revenue > 0 else None,
                },
                "finance": {
                    "report_rows_count": len(finance_rows),
                    "gross_units": sum((row.final_sales_qty or 0) for row in mart_rows),
                    "return_units": sum((row.final_return_qty or 0) for row in mart_rows),
                    "net_units": sum((row.final_net_qty or 0) for row in mart_rows),
                    "realized_revenue": float(revenue),
                    "for_pay": float(for_pay),
                    "commission": float(sum((dec(row.commission) for row in mart_rows), start=Decimal("0"))),
                    "acquiring_fee": float(sum((dec(row.acquiring_fee) for row in mart_rows), start=Decimal("0"))),
                    "logistics": float(sum((dec(row.logistics) for row in mart_rows), start=Decimal("0"))),
                    "paid_acceptance": float(sum((dec(row.paid_acceptance) for row in mart_rows), start=Decimal("0"))),
                    "storage": float(sum((dec(row.storage) for row in mart_rows), start=Decimal("0"))),
                    "penalties": float(sum((dec(row.penalties) for row in mart_rows), start=Decimal("0"))),
                    "deductions": float(sum((dec(row.deductions) for row in mart_rows), start=Decimal("0"))),
                    "additional_payments": float(sum((dec(row.additional_payments) for row in mart_rows), start=Decimal("0"))),
                    "estimated_cogs": float(estimated_cogs) if has_cost_for_all else None,
                    "estimated_profit_before_ads": float(estimated_profit_before_ads) if has_cost_for_all else None,
                    "first_report_date": min((row.rr_date for row in finance_rows if row.rr_date is not None), default=None),
                    "last_report_date": max((row.rr_date for row in finance_rows if row.rr_date is not None), default=None),
                },
                "manual_cost": (
                    {
                        "matched": True,
                        "source": representative_cost.cost_source or representative_cost.match_rule,
                        "unit_cost": float(dec(representative_cost.unit_cost)),
                        "cost_price": float(dec(representative_cost.cost_price or representative_cost.unit_cost)),
                        "packaging_cost": float(dec(representative_cost.packaging_cost)),
                        "inbound_logistics_cost": float(dec(representative_cost.inbound_logistics_cost)),
                        "total_unit_cost": float(
                            dec(representative_cost.cost_price or representative_cost.unit_cost)
                            + dec(representative_cost.packaging_cost)
                            + dec(representative_cost.inbound_logistics_cost)
                        ),
                        "supplier": representative_cost.supplier,
                        "valid_from": representative_cost.valid_from,
                        "valid_to": representative_cost.valid_to,
                        "is_placeholder": bool(representative_cost.is_placeholder),
                        "is_business_trusted": bool(representative_cost.is_business_trusted and not representative_cost.is_placeholder),
                    }
                    if representative_cost is not None else None
                ),
                "reconciliation": {
                    "pending_count": pending_count,
                    "warning_count": warning_count,
                    "error_count": error_count,
                    "ignored_count": ignored_count,
                    "revenue_matches_mart": abs(revenue - finance_report_revenue_total(finance_rows)) <= Decimal("0.01"),
                    "mart_revenue_total": float(revenue),
                    "article_revenue_total": float(finance_report_revenue_total(finance_rows)),
                },
            },
        }

        report["endpoint_comparisons"]["sku_profitability"] = {
            "api": api_profit["items"][0],
            "manual_subset": _profitability_bucket([row for row in mart_rows if row.barcode == barcode]),
        }

        health_open_issues = list(
            (
                await session.execute(
                    select(DataQualityIssue).where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                        DataQualityIssue.detected_at >= datetime.combine(date_from, time.min),
                        DataQualityIssue.detected_at <= datetime.combine(date_to, time.max),
                    )
                )
            ).scalars()
        )
        runs = list(
            (
                await session.execute(
                    select(WBSyncRun).where(WBSyncRun.account_id == account_id).order_by(WBSyncRun.id.desc())
                )
            ).scalars()
        )
        latest_run_by_domain: dict[str, WBSyncRun] = {}
        for run in runs:
            latest_run_by_domain.setdefault(run.domain, run)
        cursors = list(
            (
                await session.execute(
                    select(WBSyncCursor).where(WBSyncCursor.account_id == account_id)
                )
            ).scalars()
        )
        cursor_by_domain = {cursor.domain: cursor for cursor in cursors if cursor.cursor_key == "default"}
        domains = sorted({*latest_run_by_domain.keys(), *cursor_by_domain.keys()})
        failed_domains = [domain for domain in domains if latest_run_by_domain.get(domain) and latest_run_by_domain[domain].status == "failed"]
        skipped_domains = [domain for domain in domains if latest_run_by_domain.get(domain) and latest_run_by_domain[domain].status == "skipped"]
        classified_unmatched_sku_count = sum(
            1 for issue in health_open_issues if issue.code == "unmatched_sku" and issue_is_classified_for_acceptance(issue)
        )
        unmatched_sku_total = sum(1 for issue in health_open_issues if issue.code == "unmatched_sku")
        blocking_issue_total = blocking_open_issue_count(health_open_issues)
        active_sku_stats = (
            await session.execute(
                select(
                    func.count(CoreSKU.id),
                    func.count(CoreSKU.id).filter(
                        sa.exists(
                            select(ManualCost.id).where(
                                ManualCost.account_id == CoreSKU.account_id,
                                ManualCost.sku_id == CoreSKU.id,
                            )
                        )
                    ),
                ).where(
                    CoreSKU.account_id == account_id,
                    CoreSKU.is_active.is_(True),
                )
            )
        ).one()
        placeholder_manual_cost_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(ManualCost).where(
                        ManualCost.account_id == account_id,
                        or_(ManualCost.is_placeholder.is_(True), ManualCost.supplier == "AUTO_TEMPLATE"),
                    )
                )
            ).scalar_one()
        )
        trusted_manual_cost_count = int(
            (
                await session.execute(
                    select(func.count()).select_from(ManualCost).where(
                        ManualCost.account_id == account_id,
                        ManualCost.is_business_trusted.is_(True),
                        ManualCost.is_placeholder.is_(False),
                    )
                )
            ).scalar_one()
        )
        mart_revenue_stats = (
            await session.execute(
                select(
                    func.count(MartSKUDaily.id).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(True))),
                    func.count(MartSKUDaily.id).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(False))),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(True))), 0),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(False))), 0),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_real_manual_cost.is_(True))), 0),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_placeholder_cost.is_(True))), 0),
                ).where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.stat_date >= date_from,
                    MartSKUDaily.stat_date <= date_to,
                )
            )
        ).one()
        revenue_with_cost = dec(mart_revenue_stats[2])
        revenue_without_cost = dec(mart_revenue_stats[3])
        revenue_with_real_cost = dec(mart_revenue_stats[4])
        latest_stocks_status = latest_run_by_domain.get("stocks").status if latest_run_by_domain.get("stocks") else None
        report["endpoint_comparisons"]["data_health"] = {
            "api_subset": {
                key: api_health[key]
                for key in [
                    "open_issues_total",
                    "failed_domains",
                    "skipped_domains",
                    "missed_days_count",
                    "missing_manual_cost_count",
                    "unmatched_sku_count",
                    "duplicate_srid_count",
                    "active_sku_count",
                    "active_sku_with_manual_cost_count",
                    "placeholder_manual_cost_count",
                    "real_manual_cost_count",
                    "trusted_manual_cost_count",
                    "revenue_rows_with_cost",
                    "revenue_rows_without_cost",
                    "revenue_with_cost",
                    "revenue_without_cost",
                    "revenue_with_real_cost",
                    "revenue_with_placeholder_cost",
                    "sku_cost_coverage_percent",
                    "revenue_cost_coverage_percent",
                    "real_revenue_cost_coverage_percent",
                    "trusted_revenue_cost_coverage_percent",
                    "classified_unmatched_sku_count",
                    "business_trusted",
                    "latest_stocks_status",
                ]
            },
            "manual_subset": {
                "open_issues_total": len(health_open_issues),
                "failed_domains": failed_domains,
                "skipped_domains": skipped_domains,
                "missed_days_count": sum(1 for issue in health_open_issues if issue.code == "missed_load"),
                "missing_manual_cost_count": sum(1 for issue in health_open_issues if issue.code == "missing_manual_cost"),
                "unmatched_sku_count": unmatched_sku_total - classified_unmatched_sku_count,
                "duplicate_srid_count": sum(1 for issue in health_open_issues if issue.code == "duplicate_srid"),
                "active_sku_count": int(active_sku_stats[0] or 0),
                "active_sku_with_manual_cost_count": int(active_sku_stats[1] or 0),
                "placeholder_manual_cost_count": placeholder_manual_cost_count,
                "real_manual_cost_count": trusted_manual_cost_count,
                "trusted_manual_cost_count": trusted_manual_cost_count,
                "revenue_rows_with_cost": int(mart_revenue_stats[0] or 0),
                "revenue_rows_without_cost": int(mart_revenue_stats[1] or 0),
                "revenue_with_cost": float(revenue_with_cost),
                "revenue_without_cost": float(revenue_without_cost),
                "revenue_with_real_cost": float(revenue_with_real_cost),
                "revenue_with_placeholder_cost": float(dec(mart_revenue_stats[5])),
                "sku_cost_coverage_percent": pct(active_sku_stats[1], active_sku_stats[0]),
                "revenue_cost_coverage_percent": pct(revenue_with_cost, revenue_with_cost + revenue_without_cost),
                "real_revenue_cost_coverage_percent": pct(revenue_with_real_cost, revenue_with_cost + revenue_without_cost),
                "trusted_revenue_cost_coverage_percent": pct(revenue_with_real_cost, revenue_with_cost + revenue_without_cost),
                "classified_unmatched_sku_count": classified_unmatched_sku_count,
                "business_trusted": bool(
                    pct(revenue_with_real_cost, revenue_with_cost + revenue_without_cost)
                    and pct(revenue_with_real_cost, revenue_with_cost + revenue_without_cost) >= 95
                    and not failed_domains
                    and (unmatched_sku_total - classified_unmatched_sku_count) == 0
                    and latest_stocks_status == "completed"
                    and blocking_issue_total == 0
                ),
                "latest_stocks_status": latest_stocks_status,
            },
        }

    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=json_default), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual correctness audit for computed endpoints")
    parser.add_argument("--account-id", type=int, default=1)
    parser.add_argument("--nm-id", type=int, required=True)
    parser.add_argument("--sku-id", type=int, required=True)
    parser.add_argument("--barcode", required=True)
    parser.add_argument("--date-from", type=date.fromisoformat, required=True)
    parser.add_argument("--date-to", type=date.fromisoformat, required=True)
    parser.add_argument("--wide-from", type=date.fromisoformat, default=date(2026, 3, 29))
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument(
        "--password",
        default=os.getenv("MANUAL_CORRECTNESS_PASSWORD"),
        required=os.getenv("MANUAL_CORRECTNESS_PASSWORD") is None,
        help="Backend login password. May also be set with MANUAL_CORRECTNESS_PASSWORD.",
    )
    parser.add_argument("--output", type=Path, default=Path("exports/manual_correctness_audit.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = asyncio.run(
        run_audit(
            account_id=args.account_id,
            nm_id=args.nm_id,
            sku_id=args.sku_id,
            barcode=args.barcode,
            date_from=args.date_from,
            date_to=args.date_to,
            wide_from=args.wide_from,
            email=args.email,
            password=args.password,
            output=args.output,
        )
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=json_default))


if __name__ == "__main__":
    main()
