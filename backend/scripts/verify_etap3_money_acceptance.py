#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import date
from types import SimpleNamespace
from typing import Any

from fastapi.testclient import TestClient

from app.main import app
from app.services.auth import get_current_superuser


@dataclass
class CheckResult:
    name: str
    status: str
    details: str


def _fake_superuser() -> SimpleNamespace:
    return SimpleNamespace(id=1, is_superuser=True, is_active=True, email="audit@example.com")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify Etap 3 money-management acceptance checks.")
    parser.add_argument("--account-id", type=int, default=1)
    parser.add_argument("--date-from", type=date.fromisoformat, default=None)
    parser.add_argument("--date-to", type=date.fromisoformat, default=None)
    parser.add_argument("--nm-id", type=int, default=None)
    parser.add_argument("--focus-limit", type=int, default=10)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    return parser.parse_args()


def _ok(name: str, details: str) -> CheckResult:
    return CheckResult(name=name, status="PASS", details=details)


def _fail(name: str, details: str) -> CheckResult:
    return CheckResult(name=name, status="FAIL", details=details)


def _skip(name: str, details: str) -> CheckResult:
    return CheckResult(name=name, status="SKIP", details=details)


def _get_json(client: TestClient, path: str, *, params: dict[str, Any]) -> dict[str, Any]:
    response = client.get(path, params={key: value for key, value in params.items() if value is not None})
    if response.status_code != 200:
        raise RuntimeError(f"{path} -> {response.status_code}: {response.text}")
    return response.json()


def _check_summary(summary: dict[str, Any]) -> CheckResult:
    required_paths = [
        ("revenue_sources", "operational_revenue"),
        ("revenue_sources", "finance_confirmed_revenue"),
        ("finance_reconciliation", "status"),
        ("kpis", "ads_source_spend"),
        ("kpis", "stock_value"),
        ("kpis", "unallocated_expenses"),
        ("kpis", "net_profit_after_ads"),
        ("kpis", "net_profit_after_overhead"),
        ("meta", "data_trust"),
    ]
    missing = [
        ".".join(path)
        for path in required_paths
        if not isinstance(summary.get(path[0]), dict) or path[1] not in summary[path[0]]
    ]
    if missing:
        return _fail("money_summary_store_question", f"Missing fields: {', '.join(missing)}")
    return _ok(
        "money_summary_store_question",
        (
            f"revenue={summary['revenue_sources']['operational_revenue']}, "
            f"finance={summary['revenue_sources']['finance_confirmed_revenue']}, "
            f"ads={summary['kpis']['ads_source_spend']}, stock={summary['kpis']['stock_value']}"
        ),
    )


def _check_articles_page(articles: dict[str, Any]) -> CheckResult:
    items = articles.get("items") or []
    if not items:
        return _skip("money_articles_card_question", "No article rows returned for the selected window.")
    nm_ids = [item.get("nm_id") for item in items]
    if len(nm_ids) != len(set(nm_ids)):
        return _fail("money_articles_card_question", "Duplicate nm_id rows found on the same page.")
    summary = articles.get("summary") or {}
    missing_summary = [
        field
        for field in ("economic_profitable_count", "economic_loss_count", "final_profitable_count", "final_loss_count")
        if field not in summary
    ]
    if missing_summary:
        return _fail("money_articles_card_question", f"Missing article summary fields: {', '.join(missing_summary)}")
    for item in items:
        if "financial_final" not in item:
            return _fail("money_articles_card_question", f"financial_final missing for nm_id={item.get('nm_id')}")
        ads = item.get("ads") or {}
        stock = item.get("stock") or {}
        if "allocation_status" not in ads or "stock_value" not in stock:
            return _fail("money_articles_card_question", f"ads/stock contract missing for nm_id={item.get('nm_id')}")
    return _ok(
        "money_articles_card_question",
        (
            f"rows={len(items)}, unique_nm={len(set(nm_ids))}, "
            f"economic_profitable={summary.get('economic_profitable_count')}, "
            f"final_profitable={summary.get('final_profitable_count')}"
        ),
    )


def _check_article_detail(detail: dict[str, Any]) -> CheckResult:
    money_answer = detail.get("money_answer") or {}
    actions = detail.get("actions") or []
    if not money_answer.get("short_text"):
        return _fail("money_article_detail_next_step", "money_answer.short_text is empty")
    if not money_answer.get("next_step"):
        return _fail("money_article_detail_next_step", "money_answer.next_step is empty")
    if not actions:
        return _fail("money_article_detail_next_step", "top actions list is empty")
    return _ok(
        "money_article_detail_next_step",
        f"next_step={money_answer['next_step']}; actions={len(actions)}",
    )


def _check_actions(actions_page: dict[str, Any], *, focus_limit: int) -> CheckResult:
    owner_focus_actions = actions_page.get("owner_focus_actions") or []
    cap = min(max(focus_limit, 1), 20)
    if len(owner_focus_actions) > cap:
        return _fail("money_actions_owner_focus", f"owner_focus_actions={len(owner_focus_actions)} exceeds cap={cap}")
    return _ok("money_actions_owner_focus", f"owner_focus_actions={len(owner_focus_actions)}")


def _check_owner_vs_summary(owner: dict[str, Any], summary: dict[str, Any]) -> CheckResult:
    owner_trust = owner.get("trust") or {}
    summary_answer = summary.get("answer") or {}
    if owner_trust.get("business_status") != summary_answer.get("business_status"):
        return _fail(
            "dashboard_owner_matches_summary",
            f"owner={owner_trust.get('business_status')} summary={summary_answer.get('business_status')}",
        )
    return _ok(
        "dashboard_owner_matches_summary",
        f"business_status={owner_trust.get('business_status')}",
    )


def _check_price_safety(price_page: dict[str, Any]) -> CheckResult:
    items = price_page.get("items") or []
    if not items:
        return _skip("pricing_safety_no_fake_zero", "No price safety rows returned for the selected window.")
    bad_rows: list[str] = []
    for item in items:
        current_price = item.get("current_price")
        current_discounted_price = item.get("current_discounted_price")
        average_sale_price = item.get("average_sale_price")
        price_source = item.get("price_source")
        if current_price == 0 and price_source not in {None, "", "missing"}:
            bad_rows.append(f"sku_id={item.get('sku_id')} source={price_source}")
        if current_price == 0 and (current_discounted_price not in (None, 0) or average_sale_price not in (None, 0)):
            bad_rows.append(f"sku_id={item.get('sku_id')} has alternate price source but current_price=0")
    if bad_rows:
        return _fail("pricing_safety_no_fake_zero", "; ".join(bad_rows[:5]))
    return _ok("pricing_safety_no_fake_zero", f"checked_rows={len(items)}")


def _check_purchase_plan(purchase_page: dict[str, Any]) -> CheckResult:
    items = purchase_page.get("items") or []
    liquidate_rows = [item for item in items if item.get("status") == "LIQUIDATE"]
    if not liquidate_rows:
        return _skip("purchase_plan_liquidate_cash_zero", "No LIQUIDATE rows returned for the selected window.")
    bad_rows = [str(item.get("nm_id") or item.get("sku_id")) for item in liquidate_rows if float(item.get("required_cash") or 0) != 0.0]
    if bad_rows:
        return _fail("purchase_plan_liquidate_cash_zero", f"Non-zero required_cash for LIQUIDATE: {', '.join(bad_rows[:5])}")
    return _ok("purchase_plan_liquidate_cash_zero", f"liquidate_rows={len(liquidate_rows)}")


def _check_financial_final_guards(
    *,
    summary: dict[str, Any],
    owner: dict[str, Any],
    articles: dict[str, Any],
    detail: dict[str, Any] | None,
) -> CheckResult:
    supplier_coverage = float(((summary.get("cost_coverage") or {}).get("supplier_confirmed_cost_coverage_percent")) or 0.0)
    finance_status = ((summary.get("finance_reconciliation") or {}).get("status")) or ""
    final_blocked = supplier_coverage <= 0 or finance_status == "critical_mismatch"
    if not final_blocked:
        return _skip("financial_final_guard", "Final-profit gate is not active for the selected snapshot.")

    failures: list[str] = []
    if (summary.get("answer") or {}).get("business_status") == "healthy":
        failures.append("/money/summary says healthy")
    if bool(owner.get("financial_final")):
        failures.append("/dashboard/owner financial_final=true")
    for item in (articles.get("items") or []):
        if bool(item.get("financial_final")):
            failures.append(f"/money/articles nm_id={item.get('nm_id')} financial_final=true")
            break
    if detail is not None and bool(((detail.get("trust") or {}).get("financial_final"))):
        failures.append("/money/articles/{nm_id} trust.financial_final=true")

    if failures:
        return _fail("financial_final_guard", "; ".join(failures))
    return _ok(
        "financial_final_guard",
        f"supplier_coverage={supplier_coverage:.2f}, finance_status={finance_status}",
    )


def main() -> int:
    args = _parse_args()
    params = {
        "account_id": args.account_id,
        "date_from": args.date_from.isoformat() if args.date_from else None,
        "date_to": args.date_to.isoformat() if args.date_to else None,
    }
    results: list[CheckResult] = []
    app.dependency_overrides[get_current_superuser] = _fake_superuser
    try:
        with TestClient(app) as client:
            summary = _get_json(client, "/api/v1/money/summary", params=params)
            articles = _get_json(client, "/api/v1/money/articles", params={**params, "limit": args.limit, "offset": 0})
            owner = _get_json(client, "/api/v1/dashboard/owner", params=params)
            actions_page = _get_json(
                client,
                "/api/v1/money/actions/today",
                params={**params, "focus_limit": min(max(args.focus_limit, 1), 20), "limit": min(max(args.limit, 1), 200), "offset": 0},
            )
            price_page = _get_json(client, "/api/v1/pricing/safety", params={**params, "limit": min(max(args.limit, 1), 200), "offset": 0})
            purchase_page = _get_json(
                client,
                "/api/v1/inventory/purchase-plan",
                params={**params, "group_by": "article", "limit": min(max(args.limit, 1), 200), "offset": 0},
            )

            items = articles.get("items") or []
            sample_nm_id = args.nm_id or (items[0].get("nm_id") if items else None)
            detail = None
            if sample_nm_id is not None:
                detail = _get_json(client, f"/api/v1/money/articles/{int(sample_nm_id)}", params=params)

            results.append(_check_summary(summary))
            results.append(_check_articles_page(articles))
            results.append(_check_article_detail(detail) if detail is not None else _skip("money_article_detail_next_step", "No sample nm_id available."))
            results.append(_check_actions(actions_page, focus_limit=args.focus_limit))
            results.append(_check_owner_vs_summary(owner, summary))
            results.append(_check_price_safety(price_page))
            results.append(_check_purchase_plan(purchase_page))
            results.append(_check_financial_final_guards(summary=summary, owner=owner, articles=articles, detail=detail))
    finally:
        app.dependency_overrides.pop(get_current_superuser, None)

    if args.json:
        print(json.dumps([asdict(item) for item in results], ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"[{item.status}] {item.name}: {item.details}")

    return 1 if any(item.status == "FAIL" for item in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
