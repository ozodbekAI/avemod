from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


DEMO_ACCOUNT_NAME = "ai-operator-demo"
DEMO_EXTERNAL_ACCOUNT_ID = "demo-account"
DEMO_PILOT_EMAIL = "ai-operator-demo@example.test"
DEMO_PRODUCT_NM_ID = 1001001
DEMO_PRODUCT_VENDOR_CODE = "DEMO-1001"
DEMO_REPORT_NM_ID = 1001002
DEMO_REPORT_VENDOR_CODE = "DEMO-1002"
DEMO_PRODUCTS = [
    {
        "nm_id": DEMO_PRODUCT_NM_ID,
        "vendor_code": DEMO_PRODUCT_VENDOR_CODE,
        "barcode": "DEMO-BC-1001",
        "title": "Demo basic cotton t-shirt",
        "price": Decimal("1990.0000"),
        "cost": Decimal("740.0000"),
    },
    {
        "nm_id": DEMO_REPORT_NM_ID,
        "vendor_code": DEMO_REPORT_VENDOR_CODE,
        "barcode": "DEMO-BC-1002",
        "title": "Demo relaxed hoodie",
        "price": Decimal("2490.0000"),
        "cost": Decimal("910.0000"),
    },
    {
        "nm_id": 1001003,
        "vendor_code": "DEMO-1003",
        "barcode": "DEMO-BC-1003",
        "title": "Demo rib knit top",
        "price": Decimal("1490.0000"),
        "cost": Decimal("520.0000"),
    },
    {
        "nm_id": 1001004,
        "vendor_code": "DEMO-1004",
        "barcode": "DEMO-BC-1004",
        "title": "Demo straight fit trousers",
        "price": Decimal("3290.0000"),
        "cost": Decimal("1340.0000"),
    },
    {
        "nm_id": 1001005,
        "vendor_code": "DEMO-1005",
        "barcode": "DEMO-BC-1005",
        "title": "Demo summer dress",
        "price": Decimal("2990.0000"),
        "cost": Decimal("1180.0000"),
    },
    {
        "nm_id": 1001006,
        "vendor_code": "DEMO-1006",
        "barcode": "DEMO-BC-1006",
        "title": "Demo lightweight jacket",
        "price": Decimal("3490.0000"),
        "cost": Decimal("1510.0000"),
    },
    {
        "nm_id": 1001007,
        "vendor_code": "DEMO-1007",
        "barcode": "DEMO-BC-1007",
        "title": "Demo leggings",
        "price": Decimal("1290.0000"),
        "cost": Decimal("430.0000"),
    },
    {
        "nm_id": 1001008,
        "vendor_code": "DEMO-1008",
        "barcode": "DEMO-BC-1008",
        "title": "Demo homewear set",
        "price": Decimal("2790.0000"),
        "cost": Decimal("980.0000"),
    },
]


def demo_source_id(kind: str, *, nm_id: int | None = None, suffix: str | None = None) -> str:
    parts = ["demo", kind]
    if nm_id is not None:
        parts.append(str(nm_id))
    if suffix:
        parts.append(str(suffix))
    return ":".join(parts)


def demo_payload(**extra: Any) -> dict[str, Any]:
    payload = {
        "demo": True,
        "safe_demo": True,
        "external_operation": False,
        "marketplace_change": False,
    }
    payload.update(extra)
    return payload


def display_price(value: Any) -> Decimal:
    amount = Decimal(str(value or "0"))
    if amount > Decimal("10000"):
        amount = amount / Decimal("100")
    return amount.quantize(Decimal("0.0001"))


def dry_run_payload() -> dict[str, Any]:
    return {
        "account": {
            "name": DEMO_ACCOUNT_NAME,
            "seller_name": "AI Operator Demo Seller",
            "external_account_id": DEMO_EXTERNAL_ACCOUNT_ID,
        },
        "pilot_user": {"email": DEMO_PILOT_EMAIL, "role": "manager"},
        "products": [
            {"nm_id": item["nm_id"], "vendor_code": item["vendor_code"], "price": str(item["price"])}
            for item in DEMO_PRODUCTS
        ],
        "source_ids": demo_source_ids(),
        "safety": {
            "no_real_wb_tokens": True,
            "no_private_buyer_data": True,
            "payload_json_demo": True,
            "idempotent": True,
        },
    }


def demo_source_ids() -> dict[str, list[str]]:
    return {
        "actions": [
            demo_source_id("finance:review_profit", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("checker:card_quality_fix", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("reputation:draft_reply", nm_id=DEMO_PRODUCT_NM_ID, suffix="review-fb1"),
            demo_source_id("claims:draft_claim", nm_id=DEMO_PRODUCT_NM_ID, suffix="defect"),
            demo_source_id("claims:open_case", nm_id=DEMO_REPORT_NM_ID, suffix="report-anomaly"),
        ],
        "cases": [
            demo_source_id("case:defect", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("case:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
        ],
        "evidence": [
            demo_source_id("evidence:defect:finance_trace", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("evidence:report_anomaly:finance_trace", nm_id=DEMO_REPORT_NM_ID),
        ],
        "drafts": [
            demo_source_id("draft:defect", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("draft:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
        ],
        "result_events": [
            demo_source_id("result:draft_generated", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("result:action_completed", nm_id=DEMO_PRODUCT_NM_ID),
            demo_source_id("result:submit_blocked", nm_id=DEMO_PRODUCT_NM_ID),
        ],
    }


async def _get_or_create_account(session: AsyncSession):
    from app.models.accounts import WBAccount

    account = await session.scalar(select(WBAccount).where(WBAccount.name == DEMO_ACCOUNT_NAME))
    if account is None:
        account = WBAccount(
            name=DEMO_ACCOUNT_NAME,
            seller_name="AI Operator Demo Seller",
            external_account_id=DEMO_EXTERNAL_ACCOUNT_ID,
            timezone="Europe/Moscow",
            is_active=True,
        )
        session.add(account)
        await session.flush()
    else:
        account.seller_name = "AI Operator Demo Seller"
        account.external_account_id = DEMO_EXTERNAL_ACCOUNT_ID
        account.is_active = True
    return account


async def _get_or_create_pilot_user(session: AsyncSession, *, account_id: int, email: str, password: str, role: str):
    from app.core.security import hash_password
    from app.models.auth import AuthUser, AuthUserAccountAccess

    user = await session.scalar(select(AuthUser).where(AuthUser.email == email))
    if user is None:
        user = AuthUser(
            email=email,
            full_name="AI Operator Demo Pilot",
            password_hash=hash_password(password),
            is_active=True,
            is_superuser=False,
        )
        session.add(user)
        await session.flush()
    else:
        user.full_name = user.full_name or "AI Operator Demo Pilot"
        user.is_active = True

    access = await session.scalar(
        select(AuthUserAccountAccess).where(
            AuthUserAccountAccess.user_id == user.id,
            AuthUserAccountAccess.account_id == account_id,
        )
    )
    if access is None:
        access = AuthUserAccountAccess(user_id=user.id, account_id=account_id, role=role, is_default=True)
        session.add(access)
    else:
        access.role = role
        access.is_default = True
    return user, access


async def _upsert_one(
    session: AsyncSession,
    model,
    *,
    where,
    values: dict[str, Any],
):
    row = await session.scalar(select(model).where(*where))
    if row is None:
        row = model(**values)
        session.add(row)
        await session.flush()
        return row, True
    for key, value in values.items():
        if key == "id":
            continue
        setattr(row, key, value)
    return row, False


async def _seed_product_rows(session: AsyncSession, *, account_id: int) -> dict[str, Any]:
    from app.models.manual_costs import ManualCost
    from app.models.prices import WBPrice, WBPriceSize
    from app.models.product_cards import CoreSKU, WBProductCard

    now = datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc)
    products = DEMO_PRODUCTS
    seeded: dict[str, Any] = {"products": 0, "core_skus": 0, "prices": 0, "manual_costs": 0}
    for item in products:
        card, created = await _upsert_one(
            session,
            WBProductCard,
            where=(WBProductCard.account_id == account_id, WBProductCard.nm_id == item["nm_id"]),
            values={
                "account_id": account_id,
                "nm_id": item["nm_id"],
                "subject_id": 1,
                "subject_name": "Demo",
                "vendor_code": item["vendor_code"],
                "title": item["title"],
                "description": "Safe AI Operator demo product. No real marketplace data.",
                "brand": "Demo Brand",
                "photos": [],
                "dimensions": {},
                "updated_at_wb": now,
                "payload": demo_payload(product_demo=True),
            },
        )
        seeded["products"] += int(created)

        core, created = await _upsert_one(
            session,
            CoreSKU,
            where=(
                CoreSKU.account_id == account_id,
                CoreSKU.nm_id == item["nm_id"],
                CoreSKU.vendor_code == item["vendor_code"],
                CoreSKU.barcode == item["barcode"],
                CoreSKU.tech_size == "0",
            ),
            values={
                "account_id": account_id,
                "nm_id": item["nm_id"],
                "vendor_code": item["vendor_code"],
                "supplier_article": item["vendor_code"],
                "barcode": item["barcode"],
                "sku": f"SKU-{item['nm_id']}",
                "chrt_id": item["nm_id"] * 10,
                "size_id": item["nm_id"] * 10 + 1,
                "tech_size": "0",
                "title": item["title"],
                "brand": "Demo Brand",
                "subject_id": 1,
                "subject_name": "Demo",
                "is_active": True,
                "status": "active",
                "comment": "AI Operator demo SKU; safe local seed.",
                "source_updated_at": now,
            },
        )
        seeded["core_skus"] += int(created)

        _, created = await _upsert_one(
            session,
            WBPrice,
            where=(WBPrice.account_id == account_id, WBPrice.nm_id == item["nm_id"]),
            values={
                "account_id": account_id,
                "nm_id": item["nm_id"],
                "vendor_code": item["vendor_code"],
                "currency_iso_code": "RUB",
                "discount": 20,
                "club_discount": 0,
                "editable_size_price": True,
                "is_bad_turnover": False,
                "payload": demo_payload(price=float(item["price"])),
            },
        )
        seeded["prices"] += int(created)

        _, created = await _upsert_one(
            session,
            WBPriceSize,
            where=(WBPriceSize.account_id == account_id, WBPriceSize.nm_id == item["nm_id"], WBPriceSize.size_id == item["nm_id"] * 10 + 1),
            values={
                "account_id": account_id,
                "nm_id": item["nm_id"],
                "size_id": item["nm_id"] * 10 + 1,
                "vendor_code": item["vendor_code"],
                "tech_size_name": "0",
                "price": item["price"],
                "discounted_price": item["price"] * Decimal("0.8"),
                "club_discounted_price": item["price"] * Decimal("0.8"),
                "discount": 20,
                "club_discount": 0,
                "payload": demo_payload(),
            },
        )
        seeded["prices"] += int(created)

        _, created = await _upsert_one(
            session,
            ManualCost,
            where=(
                ManualCost.account_id == account_id,
                ManualCost.vendor_code == item["vendor_code"],
                ManualCost.nm_id == item["nm_id"],
                ManualCost.barcode == item["barcode"],
                ManualCost.tech_size == "0",
                ManualCost.valid_from == date(2026, 6, 1),
            ),
            values={
                "account_id": account_id,
                "sku_id": core.id,
                "vendor_code": item["vendor_code"],
                "nm_id": item["nm_id"],
                "barcode": item["barcode"],
                "tech_size": "0",
                "unit_cost": item["cost"],
                "cost_price": item["cost"],
                "seller_other_expense": Decimal("35.0000"),
                "packaging_cost": Decimal("20.0000"),
                "inbound_logistics_cost": Decimal("45.0000"),
                "supplier": "Demo Supplier",
                "currency": "RUB",
                "valid_from": date(2026, 6, 1),
                "source_file_name": "ai_operator_demo_seed.csv",
                "uploaded_at": now,
                "match_rule": "demo_exact",
                "cost_source": "demo_seed",
                "is_ambiguous": False,
                "is_placeholder": False,
                "is_business_trusted": True,
                "comment": "AI Operator demo cost; no real supplier data.",
            },
        )
        seeded["manual_costs"] += int(created)
        _ = card
    return seeded


async def _seed_missing_price_sizes(session: AsyncSession, *, account_id: int) -> dict[str, Any]:
    from app.models.prices import WBPrice, WBPriceSize

    seeded = {"created": 0, "updated": 0, "source": "wb_prices.payload.sizes_or_near_price"}
    rows = list(
        (
            await session.execute(
                select(WBPrice)
                .where(WBPrice.account_id == account_id)
                .order_by(WBPrice.id.asc())
            )
        ).scalars()
    )
    for row in rows:
        payload_sizes = []
        if isinstance(row.payload, dict):
            payload_sizes = row.payload.get("sizes") or []
        if not payload_sizes:
            existing_any = await session.scalar(
                select(WBPriceSize).where(
                    WBPriceSize.account_id == row.account_id,
                    WBPriceSize.nm_id == row.nm_id,
                )
            )
            if existing_any is not None:
                continue
            base_price = Decimal("990") + Decimal(int(row.nm_id or row.id) % 25) * Decimal("100")
            payload_sizes = [
                {
                    "sizeID": int(row.nm_id or row.id),
                    "techSizeName": "0",
                    "price": base_price,
                    "discountedPrice": base_price * Decimal("0.85"),
                    "clubDiscountedPrice": base_price * Decimal("0.85"),
                }
            ]
        for index, size in enumerate(payload_sizes, start=1):
            size_id = int(size.get("sizeID") or row.nm_id or row.id or index)
            raw_price = display_price(size.get("price"))
            raw_discounted = display_price(size.get("discountedPrice") or raw_price)
            raw_club = display_price(size.get("clubDiscountedPrice") or raw_discounted)
            existing = await session.scalar(
                select(WBPriceSize).where(
                    WBPriceSize.account_id == row.account_id,
                    WBPriceSize.nm_id == row.nm_id,
                    WBPriceSize.size_id == size_id,
                )
            )
            values = {
                "account_id": row.account_id,
                "nm_id": row.nm_id,
                "size_id": size_id,
                "vendor_code": row.vendor_code,
                "tech_size_name": str(size.get("techSizeName") or "0"),
                "price": raw_price,
                "discounted_price": raw_discounted,
                "club_discounted_price": raw_club,
                "discount": row.discount,
                "club_discount": row.club_discount,
                "payload": demo_payload(backfilled_from_price_payload=True),
            }
            if existing is None:
                session.add(WBPriceSize(**values))
                seeded["created"] += 1
            else:
                for key, value in values.items():
                    setattr(existing, key, value)
                seeded["updated"] += 1
    await session.flush()
    return seeded


async def _seed_demo_marts(session: AsyncSession, *, account_id: int) -> dict[str, Any]:
    from app.models.marts import MartSKUDaily, MartStockDaily
    from app.models.product_cards import CoreSKU

    stat_date = date(2026, 6, 12)
    counts = {"mart_sku_daily": 0, "mart_stock_daily": 0}
    for index, item in enumerate(DEMO_PRODUCTS, start=1):
        core = await session.scalar(
            select(CoreSKU).where(
                CoreSKU.account_id == account_id,
                CoreSKU.nm_id == item["nm_id"],
                CoreSKU.vendor_code == item["vendor_code"],
                CoreSKU.barcode == item["barcode"],
            )
        )
        if core is None:
            continue
        units = 12 + index * 3
        returns = index % 2
        net_units = units - returns
        price = Decimal(item["price"])
        revenue = price * Decimal(net_units)
        for_pay = revenue * Decimal("0.82")
        seller_cogs = Decimal(item["cost"]) * Decimal(net_units)
        seller_other = Decimal("55") * Decimal(net_units)
        wb_commission = revenue * Decimal("0.12")
        acquiring = revenue * Decimal("0.015")
        logistics = Decimal("95") * Decimal(net_units)
        total_wb = wb_commission + acquiring + logistics
        total_seller = seller_cogs + seller_other
        ad_spend = Decimal("450") + Decimal(index * 120)
        profit = revenue - total_wb - total_seller - ad_spend
        row, created = await _upsert_one(
            session,
            MartSKUDaily,
            where=(
                MartSKUDaily.account_id == account_id,
                MartSKUDaily.stat_date == stat_date,
                MartSKUDaily.nm_id == item["nm_id"],
                MartSKUDaily.vendor_code == item["vendor_code"],
                MartSKUDaily.barcode == item["barcode"],
            ),
            values={
                "account_id": account_id,
                "dedupe_key": f"demo-mart-sku-{account_id}-{item['nm_id']}",
                "stat_date": stat_date,
                "sku_id": core.id,
                "nm_id": item["nm_id"],
                "vendor_code": item["vendor_code"],
                "barcode": item["barcode"],
                "title": item["title"],
                "brand": "Demo Brand",
                "subject_name": "Demo",
                "order_rows": units,
                "ordered_units": units,
                "sale_rows": units,
                "finance_rows": units,
                "operational_sales_qty": units,
                "operational_return_qty": returns,
                "operational_revenue": revenue,
                "operational_for_pay": for_pay,
                "finance_sales_qty": units,
                "finance_return_qty": returns,
                "finance_net_units": net_units,
                "finance_revenue": revenue,
                "finance_for_pay": for_pay,
                "final_sales_qty": units,
                "final_return_qty": returns,
                "final_net_qty": net_units,
                "final_revenue": revenue,
                "final_for_pay": for_pay,
                "final_revenue_source": "demo_finance",
                "wb_commission": wb_commission,
                "payment_processing": acquiring,
                "wb_logistics": logistics,
                "total_wb_expenses": total_wb,
                "commission": wb_commission,
                "acquiring_fee": acquiring,
                "logistics": logistics,
                "seller_cogs": seller_cogs,
                "seller_other_expense": seller_other,
                "total_seller_expenses": total_seller,
                "ad_spend_operational": ad_spend,
                "ad_spend_final": ad_spend,
                "ad_spend_source": "demo",
                "ad_spend": ad_spend,
                "opening_stock_qty": Decimal(80 + index * 4),
                "closing_stock_qty": Decimal(60 + index * 5),
                "current_price": price,
                "current_discounted_price": price * Decimal("0.8"),
                "avg_sale_price": price,
                "seller_discount": 20,
                "club_discount": 0,
                "cost_price": item["cost"],
                "packaging_cost": Decimal("20"),
                "inbound_logistics_cost": Decimal("45"),
                "total_unit_cost": Decimal(item["cost"]) + Decimal("120"),
                "estimated_cogs": seller_cogs,
                "estimated_profit_before_ads": profit + ad_spend,
                "estimated_profit_after_ads": profit,
                "net_profit_after_all_expenses": profit,
                "margin_percent": (profit / revenue * Decimal("100")) if revenue else None,
                "roi_percent": (profit / seller_cogs * Decimal("100")) if seller_cogs else None,
                "drr_percent": (ad_spend / revenue * Decimal("100")) if revenue else None,
                "has_manual_cost": True,
                "has_real_manual_cost": True,
                "has_placeholder_cost": False,
                "business_trusted": True,
                "cost_source": "demo_seed",
                "has_open_issues": False,
                "payload": demo_payload(realistic_demo=True),
            },
        )
        counts["mart_sku_daily"] += int(created)
        _ = row

        _, created = await _upsert_one(
            session,
            MartStockDaily,
            where=(
                MartStockDaily.account_id == account_id,
                MartStockDaily.stat_date == stat_date,
                MartStockDaily.nm_id == item["nm_id"],
                MartStockDaily.barcode == item["barcode"],
                MartStockDaily.warehouse_id == 1,
                MartStockDaily.warehouse_name == "Demo warehouse",
            ),
            values={
                "account_id": account_id,
                "dedupe_key": f"demo-mart-stock-{account_id}-{item['nm_id']}",
                "stat_date": stat_date,
                "sku_id": core.id,
                "nm_id": item["nm_id"],
                "vendor_code": item["vendor_code"],
                "barcode": item["barcode"],
                "warehouse_id": 1,
                "warehouse_name": "Demo warehouse",
                "quantity": Decimal(60 + index * 5),
                "quantity_full": Decimal(70 + index * 5),
                "in_way_to_client": Decimal(index),
                "in_way_from_client": Decimal(0),
                "days_since_last_sale": index,
                "sales_7d": 4 + index,
                "sales_14d": 8 + index * 2,
                "sales_30d": net_units,
                "avg_sales_per_day_30d": Decimal(net_units) / Decimal("30"),
                "days_of_stock": Decimal("30"),
                "turnover_rate": Decimal("1.5"),
                "is_out_of_stock_risk": False,
                "is_dead_stock": False,
                "payload": demo_payload(realistic_demo=True),
            },
        )
        counts["mart_stock_daily"] += int(created)
    return counts


async def _upsert_action(
    session: AsyncSession,
    *,
    account_id: int,
    source_module: str,
    source_id: str,
    nm_id: int,
    vendor_code: str,
    action_type: str,
    status: str,
    priority: str,
    title: str,
    summary: str,
    guided_fix: dict[str, Any],
    payload: dict[str, Any],
):
    from app.models.operator import UnifiedAction

    row, _ = await _upsert_one(
        session,
        UnifiedAction,
        where=(
            UnifiedAction.account_id == account_id,
            UnifiedAction.source_module == source_module,
            UnifiedAction.source_id == source_id,
        ),
        values={
            "account_id": account_id,
            "source_module": source_module,
            "source_id": source_id,
            "external_id": source_id,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
            "action_type": action_type,
            "status": status,
            "priority": priority,
            "trust_state": "provisional",
            "title": title,
            "summary": summary,
            "guided_fix_json": guided_fix,
            "payload_json": payload,
        },
    )
    return row


async def _seed_operator_rows(session: AsyncSession, *, account_id: int) -> dict[str, Any]:
    from app.models.operator import OperatorCase, OperatorDraft, OperatorEvidence, OperatorSignal, ResultEvent

    counts = {"signals": 0, "actions": 0, "cases": 0, "evidence": 0, "drafts": 0, "result_events": 0}
    signals = [
        {
            "source_module": "finance",
            "source_id": demo_source_id("signal:profit_leak", nm_id=DEMO_PRODUCT_NM_ID),
            "nm_id": DEMO_PRODUCT_NM_ID,
            "vendor_code": DEMO_PRODUCT_VENDOR_CODE,
            "signal_type": "profit",
            "title": "Demo profit leak signal",
            "message": "Advertising spend is high relative to profit.",
        },
        {
            "source_module": "claims",
            "source_id": demo_source_id("signal:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
            "nm_id": DEMO_REPORT_NM_ID,
            "vendor_code": DEMO_REPORT_VENDOR_CODE,
            "signal_type": "claim",
            "title": "Demo report anomaly candidate",
            "message": "Finance reconciliation candidate requires review and proof-check.",
        },
    ]
    for item in signals:
        _, created = await _upsert_one(
            session,
            OperatorSignal,
            where=(
                OperatorSignal.account_id == account_id,
                OperatorSignal.source_module == item["source_module"],
                OperatorSignal.source_id == item["source_id"],
            ),
            values={
                "account_id": account_id,
                "source_module": item["source_module"],
                "source_id": item["source_id"],
                "external_id": item["source_id"],
                "nm_id": item["nm_id"],
                "vendor_code": item["vendor_code"],
                "signal_type": item["signal_type"],
                "status": "new",
                "trust_state": "provisional",
                "title": item["title"],
                "message": item["message"],
                "observed_at": datetime(2026, 6, 12, 10, 0, tzinfo=timezone.utc),
                "payload_json": demo_payload(),
            },
        )
        counts["signals"] += int(created)

    finance_action = await _upsert_action(
        session,
        account_id=account_id,
        source_module="finance",
        source_id=demo_source_id("finance:review_profit", nm_id=DEMO_PRODUCT_NM_ID),
        nm_id=DEMO_PRODUCT_NM_ID,
        vendor_code=DEMO_PRODUCT_VENDOR_CODE,
        action_type="review_profit",
        status="in_progress",
        priority="P1",
        title="Demo: review profit and advertising spend",
        summary="Open Product 360 Money and inspect ad spend versus profit.",
        guided_fix=demo_payload(
            route_key="product_360_money",
            label="Open Product 360 Money",
            steps=["Open Product 360", "Review money block", "Mark action done"],
            confirm_required=False,
        ),
        payload=demo_payload(expected_effect_amount=12000.0),
    )
    checker_action = await _upsert_action(
        session,
        account_id=account_id,
        source_module="checker",
        source_id=demo_source_id("checker:card_quality_fix", nm_id=DEMO_PRODUCT_NM_ID),
        nm_id=DEMO_PRODUCT_NM_ID,
        vendor_code=DEMO_PRODUCT_VENDOR_CODE,
        action_type="card_quality_fix",
        status="new",
        priority="P2",
        title="Demo: improve card quality",
        summary="Checker recommendation is read-only in MVP; open Product 360 Quality.",
        guided_fix=demo_payload(route_key="product_360_quality", label="Open quality block", confirm_required=False),
        payload=demo_payload(score=68, issue_count=3),
    )
    reputation_action = await _upsert_action(
        session,
        account_id=account_id,
        source_module="reputation",
        source_id=demo_source_id("reputation:draft_reply", nm_id=DEMO_PRODUCT_NM_ID, suffix="review-fb1"),
        nm_id=DEMO_PRODUCT_NM_ID,
        vendor_code=DEMO_PRODUCT_VENDOR_CODE,
        action_type="draft_reply",
        status="new",
        priority="P1",
        title="Demo: prepare reply draft for negative review",
        summary="Generate a reply draft; publish remains manager-confirm only.",
        guided_fix=demo_payload(
            route_key="reputation_draft_editor",
            label="Open draft editor",
            source_id="review:demo-fb1",
            confirm_required=False,
            safety_note="Публикация требует роль менеджера/администратора, confirm=true и включённый feature flag.",
        ),
        payload=demo_payload(item_type="review", rating=1, sentiment="negative", safe_display_text="Плохое качество"),
    )
    defect_claim_action = await _upsert_action(
        session,
        account_id=account_id,
        source_module="claims",
        source_id=demo_source_id("claims:draft_claim", nm_id=DEMO_PRODUCT_NM_ID, suffix="defect"),
        nm_id=DEMO_PRODUCT_NM_ID,
        vendor_code=DEMO_PRODUCT_VENDOR_CODE,
        action_type="draft_claim",
        status="new",
        priority="P1",
        title="Demo: create defect claim case",
        summary="Create a local Claims Factory case from a defect candidate.",
        guided_fix=demo_payload(route_key="claims_case_from_signal", label="Create case", confirm_required=False),
        payload=demo_payload(estimated_amount=6450.0),
    )
    report_case_action = await _upsert_action(
        session,
        account_id=account_id,
        source_module="claims",
        source_id=demo_source_id("claims:open_case", nm_id=DEMO_REPORT_NM_ID, suffix="report-anomaly"),
        nm_id=DEMO_REPORT_NM_ID,
        vendor_code=DEMO_REPORT_VENDOR_CODE,
        action_type="open_case",
        status="new",
        priority="P2",
        title="Demo: review report anomaly candidate",
        summary="Open Claims Factory and review finance trace evidence.",
        guided_fix=demo_payload(route_key="claims_center", label="Open Claims Center", confirm_required=False),
        payload=demo_payload(case_type="report_anomaly", estimated_amount=3200.0),
    )
    counts["actions"] = 5
    _ = checker_action
    _ = reputation_action

    defect_case, created = await _upsert_one(
        session,
        OperatorCase,
        where=(
            OperatorCase.account_id == account_id,
            OperatorCase.source_module == "claims",
            OperatorCase.source_id == demo_source_id("case:defect", nm_id=DEMO_PRODUCT_NM_ID),
        ),
        values={
            "account_id": account_id,
            "action_id": defect_claim_action.id,
            "source_module": "claims",
            "source_id": demo_source_id("case:defect", nm_id=DEMO_PRODUCT_NM_ID),
            "external_id": demo_source_id("case:defect", nm_id=DEMO_PRODUCT_NM_ID),
            "nm_id": DEMO_PRODUCT_NM_ID,
            "vendor_code": DEMO_PRODUCT_VENDOR_CODE,
            "case_type": "defect",
            "status": "draft_ready",
            "external_status": "not_created",
            "title": "Demo defect compensation candidate",
            "summary": "Local demo case. No external support ticket was submitted.",
            "payload_json": demo_payload(estimated_amount=6450.0, signal={"source_id": defect_claim_action.source_id}),
        },
    )
    counts["cases"] += int(created)
    report_case, created = await _upsert_one(
        session,
        OperatorCase,
        where=(
            OperatorCase.account_id == account_id,
            OperatorCase.source_module == "claims",
            OperatorCase.source_id == demo_source_id("case:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
        ),
        values={
            "account_id": account_id,
            "action_id": report_case_action.id,
            "source_module": "claims",
            "source_id": demo_source_id("case:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
            "external_id": demo_source_id("case:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
            "nm_id": DEMO_REPORT_NM_ID,
            "vendor_code": DEMO_REPORT_VENDOR_CODE,
            "case_type": "report_anomaly",
            "status": "evidence_needed",
            "external_status": "not_created",
            "title": "Demo report anomaly candidate",
            "summary": "Requires review and proof-check. Not proven.",
            "payload_json": demo_payload(estimated_amount=3200.0, wording="candidate, requires review, proof-check required"),
        },
    )
    counts["cases"] += int(created)

    evidence_specs = [
        (defect_case, "finance_trace", demo_source_id("evidence:defect:finance_trace", nm_id=DEMO_PRODUCT_NM_ID), DEMO_PRODUCT_NM_ID, DEMO_PRODUCT_VENDOR_CODE, "Demo defect finance trace"),
        (report_case, "finance_trace", demo_source_id("evidence:report_anomaly:finance_trace", nm_id=DEMO_REPORT_NM_ID), DEMO_REPORT_NM_ID, DEMO_REPORT_VENDOR_CODE, "Demo report anomaly finance trace"),
    ]
    for case, evidence_type, source_id, nm_id, vendor_code, title in evidence_specs:
        _, created = await _upsert_one(
            session,
            OperatorEvidence,
            where=(
                OperatorEvidence.account_id == account_id,
                OperatorEvidence.source_module == "claims",
                OperatorEvidence.source_id == source_id,
            ),
            values={
                "account_id": account_id,
                "case_id": case.id,
                "source_module": "claims",
                "source_id": source_id,
                "external_id": source_id,
                "nm_id": nm_id,
                "vendor_code": vendor_code,
                "evidence_type": evidence_type,
                "status": "new",
                "title": title,
                "payload_json": demo_payload(period="2026-06-01..2026-06-12", private_data=False),
            },
        )
        counts["evidence"] += int(created)

    defect_draft, created = await _upsert_one(
        session,
        OperatorDraft,
        where=(
            OperatorDraft.account_id == account_id,
            OperatorDraft.source_module == "claims",
            OperatorDraft.source_id == demo_source_id("draft:defect", nm_id=DEMO_PRODUCT_NM_ID),
        ),
        values={
            "account_id": account_id,
            "action_id": defect_claim_action.id,
            "case_id": defect_case.id,
            "source_module": "claims",
            "source_id": demo_source_id("draft:defect", nm_id=DEMO_PRODUCT_NM_ID),
            "external_id": demo_source_id("draft:defect", nm_id=DEMO_PRODUCT_NM_ID),
            "nm_id": DEMO_PRODUCT_NM_ID,
            "vendor_code": DEMO_PRODUCT_VENDOR_CODE,
            "draft_type": "support_appeal",
            "status": "new",
            "external_status": "draft_ready",
            "title": "Demo defect claim draft",
            "body_text": "Demo draft text. Review manually before any external submission.",
            "payload_json": demo_payload(requires_confirmation=True),
        },
    )
    counts["drafts"] += int(created)
    _, created = await _upsert_one(
        session,
        OperatorDraft,
        where=(
            OperatorDraft.account_id == account_id,
            OperatorDraft.source_module == "claims",
            OperatorDraft.source_id == demo_source_id("draft:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
        ),
        values={
            "account_id": account_id,
            "action_id": report_case_action.id,
            "case_id": report_case.id,
            "source_module": "claims",
            "source_id": demo_source_id("draft:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
            "external_id": demo_source_id("draft:report_anomaly", nm_id=DEMO_REPORT_NM_ID),
            "nm_id": DEMO_REPORT_NM_ID,
            "vendor_code": DEMO_REPORT_VENDOR_CODE,
            "draft_type": "support_appeal",
            "status": "new",
            "external_status": "draft_ready",
            "title": "Demo report anomaly draft",
            "body_text": "Demo report anomaly draft. Candidate wording only; proof-check required.",
            "payload_json": demo_payload(requires_confirmation=True),
        },
    )
    counts["drafts"] += int(created)

    event_specs = [
        {
            "action": defect_claim_action,
            "case": defect_case,
            "draft_id": defect_draft.id,
            "source_id": demo_source_id("result:draft_generated", nm_id=DEMO_PRODUCT_NM_ID),
            "event_type": "draft_generated",
            "status": "done",
            "external_status": "draft_ready",
            "message": "Демо-черновик создан локально.",
            "payload": demo_payload(created_by_demo=True),
        },
        {
            "action": finance_action,
            "case": None,
            "draft_id": None,
            "source_id": demo_source_id("result:action_completed", nm_id=DEMO_PRODUCT_NM_ID),
            "event_type": "action_completed",
            "status": "done",
            "external_status": None,
            "message": "Демо-действие выполнено локально. Отслеживание результата показывает только корреляцию.",
            "payload": demo_payload(before_snapshot={"profit": 12000.0}, after_snapshot={"profit": 14500.0}, comparison="improved", disclaimer="Сравнение показывает связь по данным после действия, но не доказывает причинность само по себе."),
        },
        {
            "action": defect_claim_action,
            "case": defect_case,
            "draft_id": defect_draft.id,
            "source_id": demo_source_id("result:submit_blocked", nm_id=DEMO_PRODUCT_NM_ID),
            "event_type": "submit_blocked_confirmation_required",
            "status": "blocked",
            "external_status": "not_created",
            "message": "Демо-отправка заблокирована, потому что confirm=true не передан.",
            "payload": demo_payload(manual_confirm=False, warnings=["manual_confirm_required"]),
        },
    ]
    for event in event_specs:
        _, created = await _upsert_one(
            session,
            ResultEvent,
            where=(
                ResultEvent.account_id == account_id,
                ResultEvent.source_module == "demo",
                ResultEvent.source_id == event["source_id"],
                ResultEvent.event_type == event["event_type"],
            ),
            values={
                "account_id": account_id,
                "action_id": event["action"].id if event["action"] is not None else None,
                "case_id": event["case"].id if event["case"] is not None else None,
                "draft_id": event["draft_id"],
                "source_module": "demo",
                "source_id": event["source_id"],
                "external_id": event["source_id"],
                "nm_id": DEMO_PRODUCT_NM_ID,
                "vendor_code": DEMO_PRODUCT_VENDOR_CODE,
                "event_type": event["event_type"],
                "status": event["status"],
                "external_status": event["external_status"],
                "message": event["message"],
                "payload_json": event["payload"],
            },
        )
        counts["result_events"] += int(created)
    return counts


async def apply_seed(*, pilot_email: str, pilot_password: str, pilot_role: str) -> dict[str, Any]:
    from app.core.db import SessionLocal

    async with SessionLocal() as session:
        account = await _get_or_create_account(session)
        pilot_user, access = await _get_or_create_pilot_user(
            session,
            account_id=account.id,
            email=pilot_email,
            password=pilot_password,
            role=pilot_role,
        )
        product_counts = await _seed_product_rows(session, account_id=account.id)
        price_size_counts = await _seed_missing_price_sizes(session, account_id=account.id)
        mart_counts = await _seed_demo_marts(session, account_id=account.id)
        operator_counts = await _seed_operator_rows(session, account_id=account.id)
        await session.commit()
        return {
            "account_id": account.id,
            "account_name": account.name,
            "pilot_user_id": pilot_user.id,
            "pilot_email": pilot_user.email,
            "pilot_role": access.role,
            "products": product_counts,
            "price_sizes": price_size_counts,
            "marts": mart_counts,
            "operator": operator_counts,
            "source_ids": demo_source_ids(),
            "safety": {
                "no_real_wb_tokens": True,
                "no_private_buyer_data": True,
                "payload_json_demo": True,
            },
        }


async def backfill_all_price_sizes() -> dict[str, Any]:
    from app.core.db import SessionLocal
    from app.models.accounts import WBAccount

    async with SessionLocal() as session:
        accounts = list((await session.execute(select(WBAccount).order_by(WBAccount.id.asc()))).scalars())
        result: dict[str, Any] = {"accounts": {}, "total_created": 0, "total_updated": 0}
        for account in accounts:
            counts = await _seed_missing_price_sizes(session, account_id=int(account.id))
            result["accounts"][str(account.id)] = counts
            result["total_created"] += int(counts["created"])
            result["total_updated"] += int(counts["updated"])
        await session.commit()
        return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed safe, deterministic AI Operator demo records.")
    parser.add_argument("--apply", action="store_true", help="Write demo records to the configured database.")
    parser.add_argument("--backfill-all-price-sizes", action="store_true", help="Backfill display-ready price sizes for every account from existing price payloads.")
    parser.add_argument("--pilot-email", default=DEMO_PILOT_EMAIL, help="Pilot user email to create/grant access.")
    parser.add_argument(
        "--password",
        default=os.getenv("AI_OPERATOR_DEMO_PASSWORD"),
        help="Pilot user password. May also be set with AI_OPERATOR_DEMO_PASSWORD. Required with --apply.",
    )
    parser.add_argument("--pilot-role", default="manager", choices=["viewer", "operator", "manager", "admin"], help="Pilot role for the demo account.")
    args = parser.parse_args()

    if args.backfill_all_price_sizes:
        result = asyncio.run(backfill_all_price_sizes())
        print(json.dumps(result, indent=2, sort_keys=True, default=str))
        print("\nBackfilled display-ready price sizes without external marketplace writes.")
        return

    if not args.apply:
        print(json.dumps(dry_run_payload(), indent=2, sort_keys=True))
        print("\nDry run only. Re-run with --apply to write safe demo records to the configured database.")
        return

    if not args.password:
        raise SystemExit("--password or AI_OPERATOR_DEMO_PASSWORD is required when using --apply.")

    result = asyncio.run(apply_seed(pilot_email=args.pilot_email, pilot_password=args.password, pilot_role=args.pilot_role))
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    print("\nSeeded AI Operator demo data without WB tokens or private buyer data.")


if __name__ == "__main__":
    main()
