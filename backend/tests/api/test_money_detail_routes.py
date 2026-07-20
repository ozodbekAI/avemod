from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.db import get_db_session
from app.main import app
from app.modules.money_management import router as money_router
from app.services.auth import get_current_superuser, get_current_user


async def _override_session():
    yield None


def _override_user():
    return SimpleNamespace(id=1)


async def _allow_money_read(*args, **kwargs):
    return None


def _money_meta() -> dict:
    return {
        "account_id": 1,
        "date_from": "2026-05-01",
        "date_to": "2026-05-20",
        "currency": "RUB",
        "generated_at": "2026-05-28T00:00:00Z",
        "data_trust": {
            "state": "operational_provisional",
            "trust_state": "operational_provisional",
            "business_trusted": True,
            "operational_trusted": True,
            "financial_final": False,
            "can_generate_business_actions": True,
            "confidence": "medium",
            "cost_trust_policy": "operator_baseline",
            "supplier_confirmed_revenue_coverage_percent": 0.0,
            "operator_baseline_revenue_coverage_percent": 99.6,
            "trusted_revenue_cost_coverage_percent": 99.6,
            "financial_final_blockers_total": 2,
            "final_profit_blockers_total": 2,
            "blocked_reasons": [],
            "human_message": "Данные предварительные",
        },
    }


def _money_answer() -> dict:
    return {
        "status": "profitable_but_provisional",
        "title": "Карточка выглядит рабочей",
        "short_text": "Операционно карточка нормальная, но финальная прибыль ещё не подтверждена.",
        "decision": "WATCH",
        "next_step": "Проверить reconciliation и supplier cost",
        "main_next_step": "Проверить reconciliation и supplier cost",
        "main_reason": "Supplier-confirmed coverage отсутствует",
    }


def _next_action() -> dict:
    return {
        "id": 10,
        "action_type": "ADS_REVIEW",
        "action_group": "business",
        "category": "save_money",
        "priority": "high",
        "status": "new",
        "title": "Проверить рекламу",
        "what_to_do": "Проверить рекламу",
        "why": "Есть риск перерасхода",
        "business_reason": "Ads spend требует проверки",
        "next_step": "Сверить spend и отключить слабые кампании",
        "how_to_fix": ["Проверить spend", "Отключить слабые кампании"],
        "expected_effect_amount": 1500.0,
        "priority_score": 90.0,
        "required_cash": 0.0,
        "recommended_qty": 0,
        "unit_cost": 0.0,
        "current_stock": 15.0,
        "days_of_stock": 20.0,
        "lead_time_days": 14,
        "safety_days": 7,
        "confidence": "medium",
        "financial_final": False,
        "deadline_hint": "today",
        "deadline_at": None,
        "linked_entity": {"nm_id": 223205606, "sku_id": 18516},
        "affected_nm_ids": [223205606],
        "affected_sku_ids": [18516],
        "blocked_reasons": [],
        "money_effect": {"expected_cash_release": 0.0},
        "source_endpoint": "/money/articles/223205606",
    }


def _card_money() -> dict:
    return {
        "revenue": 100000.0,
        "for_pay": 90000.0,
        "wb_expenses": {
            "commission": 5000.0,
            "acquiring_fee": 500.0,
            "logistics": 1000.0,
            "paid_acceptance": 0.0,
            "storage": 0.0,
            "penalties": 0.0,
            "deductions": 0.0,
            "additional_payments": 0.0,
            "direct": 6500.0,
            "account_level": 1000.0,
            "allocated_overhead": 1000.0,
            "unallocated": 500.0,
            "confidence": "medium",
            "reason": "Часть расходов остаётся overhead",
            "status": "partial",
        },
        "ads": {
            "spend": 5000.0,
            "source_spend": 5000.0,
            "raw_allocated_spend": 5000.0,
            "capped_allocated_spend": 5000.0,
            "allocated_spend": 5000.0,
            "unallocated_spend": 0.0,
            "overallocated_spend": 0.0,
            "drr_percent": 5.0,
            "drr_percent_source": 5.0,
            "status": "matched",
            "allocation_status": "matched",
            "profit_allocation_status": "matched",
            "allocation_method": "nm_direct",
            "allocation_confidence": "high",
            "final_profit_allowed": True,
        },
        "cogs": {
            "unit_cost": 2000.0,
            "estimated_cogs": 40000.0,
            "truth_level": "operator_baseline",
            "cost_truth_label": "operator baseline",
            "supplier_confirmed": False,
            "business_trusted": True,
            "confidence": "medium",
            "reason": "Operator baseline используется для операционных решений",
        },
        "profit": {
            "before_ads": 43500.0,
            "after_allocated_ads": 38500.0,
            "after_source_ads": 38500.0,
            "after_overhead": 37500.0,
            "with_allocated_overhead": 37500.0,
            "after_ads": 38500.0,
            "margin_after_ads_percent": 38.5,
            "roi_after_ads_percent": 96.25,
            "roi_on_cogs_percent": 96.25,
            "stock_roi_percent": 96.25,
            "roas_percent": 1800.0,
            "confidence": "medium",
        },
        "wb_expenses_total": 6500.0,
        "stock_value": 30000.0,
    }


def _card_detail_payload() -> dict:
    return {
        "computed_at": "2026-05-28T00:00:00Z",
        "cache_status": "hit",
        "data_version_hash": "money-detail-hash",
        "meta": _money_meta(),
        "identity": {
            "sku_id": 18516,
            "nm_id": 223205606,
            "vendor_code": "SKU-18516",
            "barcode": "123456",
            "title": "Test card",
            "brand": "Brand",
            "subject_name": "Category",
        },
        "answer": _money_answer(),
        "money": _card_money(),
        "expense_breakdown": {
            "direct_expenses": {
                "commission": 5000.0,
                "acquiring_fee": 500.0,
                "logistics": 1000.0,
                "paid_acceptance": 0.0,
                "storage": 0.0,
                "penalties": 0.0,
                "deductions": 0.0,
                "additional_payments": 0.0,
            },
            "allocated_overhead": 1000.0,
            "account_level_total": 1000.0,
            "unallocated_total": 500.0,
            "unallocated_warning": True,
            "not_linked_reason": "finance rows have no nm_id/barcode or are account-level",
            "message": "Часть расходов учтена как overhead",
        },
        "operations": {
            "orders_count": 10,
            "cancelled_orders_count": 1,
            "cancel_rate_percent": 10.0,
            "sales_count": 9,
            "returns_count": 1,
            "return_rate_percent": 11.1,
            "net_units": 8,
            "issue": "",
        },
        "funnel": {
            "open_count": 100,
            "cart_count": 12,
            "order_count": 10,
            "buyout_count": 9,
            "cart_conversion_percent": 12.0,
            "order_conversion_percent": 10.0,
            "buyout_rate_percent": 90.0,
            "issue": "",
        },
        "stock": {
            "quantity": 15.0,
            "quantity_full": 15.0,
            "stock_value": 30000.0,
            "stock_value_confidence": "medium",
            "stock_value_reason": "operator baseline cost",
            "days_of_stock": 20.0,
            "stock_status": "ok",
            "in_transit_qty": 0.0,
            "in_transit_value": 0.0,
        },
        "price": {
            "current_price": 18900.0,
            "current_discounted_price": 10962.0,
            "discount": 42,
            "break_even_price": 3436.13,
            "break_even_price_final": 0.0,
            "break_even_price_estimated": 3436.13,
            "target_margin_price": 4295.16,
            "target_margin_price_final": 0.0,
            "target_margin_price_estimated": 4295.16,
            "safe_price_gap": 7525.87,
            "safe_price_gap_final": 0.0,
            "safe_price_gap_estimated": 7525.87,
            "status": "safe",
            "confidence": "medium",
            "price_source": "wb_price_snapshot",
            "not_computable_reason": "",
        },
        "reconciliation": {
            "mart_matches_article": True,
            "mart_matches_finance": False,
            "finance_matches_operational": False,
            "revenue_matches_mart": True,
            "mart_revenue_total": 100000.0,
            "article_revenue_total": 100000.0,
            "finance_report_revenue_total": 85000.0,
            "difference_amount": 15000.0,
            "difference_ratio_percent": 15.0,
            "status": "critical_mismatch",
            "mismatch_reason": "finance lag",
            "root_cause_candidates": ["finance lag"],
            "next_debug_endpoint": "/dashboard/article-audit",
            "business_effect": "Final profit is provisional",
        },
        "problems": [],
        "next_actions": [_next_action()],
        "article_summary": {
            "nm_id": 223205606,
            "title": "Test card",
            "revenue": 100000.0,
            "profit_before_ads": 43500.0,
            "ads_source_spend": 5000.0,
            "profit_after_ads": 38500.0,
            "stock_qty": 15.0,
            "stock_value": 30000.0,
            "cancel_rate_percent": 10.0,
            "return_rate_percent": 11.1,
            "decision": "watch",
        },
        "variant_breakdown": [],
        "profit_variants": {
            "before_ads": 43500.0,
            "after_allocated_ads": 38500.0,
            "after_source_ads": 38500.0,
            "after_overhead": 37500.0,
            "with_allocated_overhead": 37500.0,
        },
        "finality": {
            "profit_final": False,
            "restock_final": False,
            "price_final": True,
            "reasons": ["supplier_confirmed coverage is 0"],
        },
    }


def _article_detail_payload() -> dict:
    return {
        "computed_at": "2026-05-28T00:00:00Z",
        "cache_status": "hit",
        "data_version_hash": "money-article-hash",
        "meta": _money_meta(),
        "nm_id": 223205606,
        "identity": {
            "nm_id": 223205606,
            "title": "Article title",
            "brand": "Brand",
            "subject_name": "Category",
        },
        "trust": {
            "state": "operational_provisional",
            "business_trusted": True,
            "operational_trusted": True,
            "financial_final": False,
            "confidence": "medium",
            "blocked_reasons": [],
            "cost_truth_level": "operator_baseline",
            "supplier_confirmed": False,
            "finance_status": "critical_mismatch",
            "human_message": "Данные предварительные",
            "reason": "supplier cost not confirmed",
        },
        "money_answer": _money_answer(),
        "kpis": {
            "revenue": 100000.0,
            "for_pay": 90000.0,
            "profit_before_ads": 43500.0,
            "profit_after_allocated_ads": 38500.0,
            "profit_after_source_ads": 38500.0,
            "profit_after_overhead": 37500.0,
            "wb_expenses_total": 6500.0,
            "stock_qty": 15.0,
            "stock_value": 30000.0,
            "ads_source_spend": 5000.0,
            "ads_allocated_spend": 5000.0,
            "cancel_rate_percent": 10.0,
            "return_rate_percent": 11.1,
        },
        "waterfall": {
            "revenue": 100000.0,
            "cogs": 40000.0,
            "direct_wb_expenses": 6500.0,
            "ads_source_spend": 5000.0,
            "allocated_overhead": 1000.0,
            "profit_before_ads": 43500.0,
            "profit_after_source_ads": 38500.0,
            "profit_after_overhead": 37500.0,
        },
        "cost_coverage": {
            "operational_cost_coverage_percent": 99.6,
            "supplier_confirmed_cost_coverage_percent": 0.0,
            "business_accepted_cost_coverage_percent": 99.6,
            "cost_policy": "operator_baseline",
            "cost_truth_level": "operator_baseline",
            "can_use_for_operations": True,
            "can_use_for_final_profit": False,
            "missing_cost_revenue": 0.0,
            "operator_baseline_revenue": 100000.0,
            "supplier_confirmed_revenue": 0.0,
            "message": "Операционная себестоимость покрыта, supplier-confirmed ещё не загружена",
        },
        "money": _card_money(),
        "expense_breakdown": {
            "direct_expenses": {
                "commission": 5000.0,
                "acquiring_fee": 500.0,
                "logistics": 1000.0,
                "paid_acceptance": 0.0,
                "storage": 0.0,
                "penalties": 0.0,
                "deductions": 0.0,
                "additional_payments": 0.0,
            },
            "allocated_overhead": 1000.0,
            "account_level_total": 1000.0,
            "unallocated_total": 500.0,
            "unallocated_warning": True,
            "not_linked_reason": "finance rows have no nm_id/barcode or are account-level",
            "message": "Часть расходов учтена как overhead",
        },
        "ads": _card_money()["ads"],
        "stock": _card_detail_payload()["stock"],
        "operations": _card_detail_payload()["operations"],
        "funnel": _card_detail_payload()["funnel"],
        "price_safety": _card_detail_payload()["price"],
        "purchase_plan": {
            "decision": "WATCH",
            "main_reason": "Нужна проверка reconciliation",
            "next_step": "Не докупать до закрытия вопросов по данным",
            "recommended_qty": 0,
            "required_cash": 0.0,
            "money_effect": {
                "affected_stock_value": 30000.0,
                "expected_cash_release": 0.0,
            },
            "confidence": "medium",
            "decision_confidence": "medium",
            "financial_final": False,
            "available_stock": 15.0,
            "in_transit_qty": 0.0,
            "days_of_stock": 20.0,
            "lead_time_days": 14,
            "safety_days": 7,
            "variant_count": 1,
            "size_breakdown": [],
        },
        "reconciliation": _card_detail_payload()["reconciliation"],
        "actions": [_next_action()],
        "issues": [],
        "sku_breakdown": [],
        "article_summary": _card_detail_payload()["article_summary"],
        "profit_variants": _card_detail_payload()["profit_variants"],
        "finality": _card_detail_payload()["finality"],
        "answer": _money_answer(),
        "price": _card_detail_payload()["price"],
        "next_actions": [_next_action()],
        "problems": [],
    }


def test_money_card_detail_route_returns_trust_fields(monkeypatch) -> None:
    async def _fake_card_detail(session, **kwargs):
        return _card_detail_payload()

    monkeypatch.setattr(money_router.snapshot_service, "card_detail", _fake_card_detail)
    app.dependency_overrides[get_current_superuser] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/money/cards/18516?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["data_trust"]["operational_trusted"] is True
    assert body["meta"]["data_trust"]["financial_final"] is False
    assert body["meta"]["data_trust"]["trust_state"] == "operational_provisional"


def test_money_article_detail_route_returns_trust_fields(monkeypatch) -> None:
    async def _fake_article_detail(session, **kwargs):
        return _article_detail_payload()

    monkeypatch.setattr(
        money_router.snapshot_service, "article_detail", _fake_article_detail
    )
    app.dependency_overrides[get_current_superuser] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/money/articles/223205606?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["trust"]["operational_trusted"] is True
    assert body["trust"]["financial_final"] is False
    assert body["trust"]["state"] == "operational_provisional"


def _expense_breakdown_payload() -> dict:
    return {
        "account_id": 1,
        "date_from": "2026-05-01",
        "date_to": "2026-05-20",
        "group_by": "category",
        "include_unallocated": True,
        "revenue_final": 1000000.0,
        "net_profit_after_all_expenses": 370000.0,
        "seller_cogs": 300000.0,
        "seller_other_expense": 50000.0,
        "ad_spend_final": 40000.0,
        "additional_income": 10000.0,
        "total_expenses": 868000.0,
        "total_wb_expenses": 701498.22,
        "total_seller_expenses": 120000.0,
        "total_ad_expenses": 46501.78,
        "logistics_total": 701498.22,
        "logistics_share_base_kind": "wb_expenses",
        "logistics_share_base_amount": 868686.91,
        "logistics_share_percent": 80.8,
        "data_version_hash": "summary-hash-1",
        "source_of_truth": "finance_report",
        "items": [
            {
                "group_key": "wb_logistics",
                "label": "Логистика WB",
                "amount": 701498.22,
                "share_percent": 80.8,
                "category": "wb_logistics",
                "source": "finance_report",
                "is_final": True,
                "row_count": 18,
            }
        ],
    }


def _profit_cascade_payload() -> dict:
    return {
        "account_id": 1,
        "date_from": "2026-05-01",
        "date_to": "2026-05-20",
        "currency": "RUB",
        "source_of_truth": "finance_report",
        "financial_final": False,
        "operational_trusted": True,
        "trust_state": "operational_provisional",
        "cascade": {
            "revenue": {
                "code": "revenue",
                "label": "Выручка",
                "amount": 1000000.0,
                "sign": "income",
            },
            "groups": [
                {
                    "code": "seller_cogs",
                    "label": "Себестоимость",
                    "amount": 300000.0,
                    "sign": "expense",
                    "children": [
                        {
                            "code": "seller_cogs",
                            "label": "Себестоимость",
                            "amount": 300000.0,
                            "share_percent": 100.0,
                            "source": "manual_cost",
                        }
                    ],
                },
                {
                    "code": "seller_other_expenses",
                    "label": "Прочие расходы продавца",
                    "amount": 50000.0,
                    "sign": "expense",
                    "children": [
                        {
                            "code": "seller_other_expense",
                            "label": "Прочие расходы продавца",
                            "amount": 50000.0,
                            "share_percent": 100.0,
                            "source": "manual_cost",
                        }
                    ],
                },
                {
                    "code": "wb_direct_expenses",
                    "label": "Прямые расходы WB",
                    "amount": 250000.0,
                    "sign": "expense",
                    "children": [
                        {
                            "code": "wb_logistics",
                            "label": "Логистика WB",
                            "amount": 200000.0,
                            "share_percent": 80.0,
                            "source": "finance_report",
                        },
                        {
                            "code": "wb_commission",
                            "label": "Комиссия WB",
                            "amount": 50000.0,
                            "share_percent": 20.0,
                            "source": "finance_report",
                        },
                    ],
                },
                {
                    "code": "ad_expenses",
                    "label": "Реклама / продвижение",
                    "amount": 40000.0,
                    "sign": "expense",
                    "children": [
                        {
                            "code": "ad_spend_final",
                            "label": "Реклама / продвижение",
                            "amount": 40000.0,
                            "share_percent": 100.0,
                            "source": "finance_report",
                            "ad_spend_operational": 60000.0,
                            "ad_spend_finance": 40000.0,
                            "ad_spend_source": "finance_report",
                        }
                    ],
                },
                {
                    "code": "additional_income",
                    "label": "Доплаты / компенсации",
                    "amount": 10000.0,
                    "sign": "income",
                    "children": [
                        {
                            "code": "additional_payment",
                            "label": "Доплаты / компенсации",
                            "amount": 10000.0,
                            "share_percent": 100.0,
                            "source": "finance_report",
                        }
                    ],
                },
            ],
            "totals": {
                "gross_revenue": 1000000.0,
                "seller_cogs": 300000.0,
                "seller_other_expense": 50000.0,
                "total_seller_expenses": 350000.0,
                "total_wb_expenses": 250000.0,
                "total_ad_expenses": 40000.0,
                "additional_income": 10000.0,
                "net_profit_after_all_expenses": 370000.0,
                "logistics_total": 200000.0,
                "logistics_share_percent": 80.0,
            },
            "validation": {
                "groups_match_children": True,
                "profit_formula_valid": True,
                "issues": [],
            },
        },
    }


def _expense_logistics_payload() -> dict:
    return {
        "account_id": 1,
        "date_from": "2026-05-01",
        "date_to": "2026-05-20",
        "include_unallocated": True,
        "total_logistics": 701498.22,
        "total_wb_logistics": 650000.0,
        "total_wb_logistics_rebill": 51498.22,
        "logistics_share_base_kind": "wb_expenses",
        "logistics_share_base_amount": 868686.91,
        "logistics_share_percent": 80.8,
        "delivery_to_client": 550000.0,
        "return_from_client": 120000.0,
        "cancellation_to_client": 10000.0,
        "cancellation_from_client": 5000.0,
        "seller_initiated_return": 8000.0,
        "defect_return": 3000.0,
        "unknown": 5498.22,
        "by_category": [
            {
                "group_key": "wb_logistics",
                "label": "Логистика WB",
                "amount": 650000.0,
                "share_percent": 92.66,
                "category": "wb_logistics",
                "source": "finance_report",
                "is_final": True,
                "row_count": 10,
            }
        ],
        "by_logistics_type": [
            {
                "group_key": "delivery_to_client",
                "label": "Доставка до клиента",
                "amount": 550000.0,
                "share_percent": 78.4,
                "source": "finance_report",
                "is_final": True,
                "row_count": 8,
            }
        ],
        "by_bonus_type_name": [],
        "by_seller_oper_name": [],
        "by_sku": [],
        "by_nm": [],
        "by_day": [],
    }


def _expense_report_rows_payload() -> dict:
    return {
        "total": 1,
        "limit": 50,
        "offset": 0,
        "items": [
            {
                "report_id": 1001,
                "rrd_id": 5001,
                "date": "2026-05-10",
                "nm_id": 223205606,
                "sku_id": 18516,
                "vendor_code": "SKU-18516",
                "barcode": "123456",
                "category": "wb_logistics",
                "category_label": "Логистика WB",
                "amount": 1200.0,
                "source": "finance_report",
                "source_field": "delivery_service",
                "seller_oper_name": "Логистика",
                "bonus_type_name": None,
                "logistics_type": "delivery_service",
                "srid": "SRID-1",
                "order_id": 101,
                "is_allocated_to_sku": True,
            }
        ],
    }


def test_money_expense_breakdown_route_returns_payload(monkeypatch) -> None:
    async def _fake_breakdown(session, **kwargs):
        return _expense_breakdown_payload()

    monkeypatch.setattr(
        money_router.snapshot_service, "expense_breakdown", _fake_breakdown
    )
    monkeypatch.setattr(money_router, "_require_money_read", _allow_money_read)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/money/expenses/breakdown?account_id=1&group_by=category"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["group_by"] == "category"
    assert body["net_profit_after_all_expenses"] == 370000.0
    assert body["items"][0]["category"] == "wb_logistics"
    assert body["items"][0]["is_final"] is True


def test_money_profit_cascade_route_returns_payload(monkeypatch) -> None:
    async def _fake_profit_cascade(session, **kwargs):
        return _profit_cascade_payload()

    monkeypatch.setattr(
        money_router.snapshot_service, "profit_cascade", _fake_profit_cascade
    )
    monkeypatch.setattr(money_router, "_require_money_read", _allow_money_read)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/money/profit-cascade?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["source_of_truth"] == "finance_report"
    assert body["cascade"]["groups"][2]["code"] == "wb_direct_expenses"
    assert (
        body["cascade"]["groups"][3]["children"][0]["ad_spend_source"]
        == "finance_report"
    )


def test_money_expense_logistics_route_returns_payload(monkeypatch) -> None:
    async def _fake_logistics(session, **kwargs):
        return _expense_logistics_payload()

    monkeypatch.setattr(
        money_router.snapshot_service, "expense_logistics", _fake_logistics
    )
    monkeypatch.setattr(money_router, "_require_money_read", _allow_money_read)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/money/expenses/logistics?account_id=1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["delivery_to_client"] == 550000.0
    assert body["by_logistics_type"][0]["group_key"] == "delivery_to_client"


def test_money_expense_report_rows_route_returns_payload(monkeypatch) -> None:
    captured: dict = {}

    async def _fake_report_rows(session, **kwargs):
        captured.update(kwargs)
        return _expense_report_rows_payload()

    monkeypatch.setattr(money_router.service, "expense_report_rows", _fake_report_rows)
    monkeypatch.setattr(money_router, "_require_money_read", _allow_money_read)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_db_session] = _override_session
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/v1/money/expenses/report-rows",
                params={
                    "account_id": 1,
                    "category": "wb_logistics",
                    "sku_id": 18516,
                    "nm_id": 223205606,
                    "amount_exact": 1,
                    "amount_min": 1,
                    "amount_max": 2,
                    "search": "SKU-18516",
                    "source_field": "delivery_service",
                    "seller_oper_name": "Логистика",
                    "allocated": "true",
                    "limit": 100,
                    "offset": 10,
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["category"] == "wb_logistics"
    assert body["items"][0]["source_field"] == "delivery_service"
    assert captured["category"] == "wb_logistics"
    assert captured["sku_id"] == 18516
    assert captured["nm_id"] == 223205606
    assert captured["amount_exact"] == 1
    assert captured["amount_min"] == 1
    assert captured["amount_max"] == 2
    assert captured["search"] == "SKU-18516"
    assert captured["source_field"] == "delivery_service"
    assert captured["seller_oper_name"] == "Логистика"
    assert captured["allocated"] is True
    assert captured["limit"] == 100
    assert captured["offset"] == 10
