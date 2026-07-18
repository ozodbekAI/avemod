from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPO_ROOT / "exports"

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_EMAIL = "audit-user@example.invalid"
DEFAULT_ACCOUNT_ID = 1
DEFAULT_LIMIT = 100
NGROK_HEADER = {"ngrok-skip-browser-warning": "true"}


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise SystemExit(f"{name} is required; set it in the environment before running this audit.")


BASE_URL = os.getenv("FRONTEND_AUDIT_BASE_URL", DEFAULT_BASE_URL)
AUDIT_EMAIL = os.getenv("FRONTEND_AUDIT_EMAIL", DEFAULT_EMAIL)
AUDIT_PASSWORD = _required_env("FRONTEND_AUDIT_PASSWORD")
ACCOUNT_ID = int(os.getenv("FRONTEND_AUDIT_ACCOUNT_ID", str(DEFAULT_ACCOUNT_ID)))
LIMIT = int(os.getenv("FRONTEND_AUDIT_LIMIT", str(DEFAULT_LIMIT)))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slug_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _count_missing(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    missing = 0
    empty_list = 0
    for item in items:
        value = item.get(field)
        if value is None:
            missing += 1
        elif isinstance(value, list) and not value:
            empty_list += 1
    return {"missing": missing, "empty_list": empty_list, "present": len(items) - missing}


def _page_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _compare_numeric_fields(
    left: dict[str, Any],
    right: dict[str, Any],
    fields: list[str | tuple[str, str]],
) -> list[dict[str, Any]]:
    comparisons: list[dict[str, Any]] = []
    for field in fields:
        if isinstance(field, tuple):
            left_field, right_field = field
            label = f"{left_field}->{right_field}"
        else:
            left_field = field
            right_field = field
            label = field
        left_value = float(left.get(left_field) or 0)
        right_value = float(right.get(right_field) or 0)
        comparisons.append(
            {
                "field": label,
                "left": left_value,
                "right": right_value,
                "delta": round(left_value - right_value, 6),
                "match": abs(left_value - right_value) < 1e-6,
            }
        )
    return comparisons


def _build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Frontend Placeholder And Consistency Audit",
        "",
        f"- Generated: `{report['meta']['generated_at']}`",
        f"- Backend: `{report['meta']['base_url']}`",
        f"- Account ID: `{report['meta']['account_id']}`",
        f"- Window: `{report['meta']['date_from']}` .. `{report['meta']['date_to']}`",
        "",
        "## Consistency",
        "",
    ]
    for name, checks in report["consistency"].items():
        lines.append(f"### {name}")
        lines.append("")
        for item in checks:
            status = "match" if item["match"] else "mismatch"
            lines.append(
                f"- `{item['field']}`: `{status}` left=`{item['left']}` right=`{item['right']}` delta=`{item['delta']}`"
            )
        lines.append("")
    lines.extend(["## Coverage", ""])
    for endpoint, fields in report["coverage"].items():
        lines.append(f"### {endpoint}")
        lines.append("")
        for field, counts in fields.items():
            lines.append(
                f"- `{field}`: present=`{counts['present']}` missing=`{counts['missing']}` empty_list=`{counts['empty_list']}`"
            )
        lines.append("")
    lines.extend(["## Notes", ""])
    for note in report["notes"]:
        lines.append(f"- {note}")
    return "\n".join(lines)


def main() -> None:
    now = _utc_now()
    date_to = os.getenv("FRONTEND_AUDIT_DATE_TO", "2026-05-31")
    date_from = os.getenv("FRONTEND_AUDIT_DATE_FROM", "2026-05-01")
    bundle_dir = EXPORTS_DIR / f"frontend_placeholder_consistency_audit_{_slug_timestamp(now)}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    client = httpx.Client(
        follow_redirects=True,
        timeout=httpx.Timeout(90.0, connect=30.0),
        headers=NGROK_HEADER.copy(),
    )
    login = client.post(
        f"{BASE_URL}/auth/login",
        json={"email": AUDIT_EMAIL, "password": AUDIT_PASSWORD},
    )
    login.raise_for_status()
    token = login.json()["access_token"]
    headers = {**NGROK_HEADER, "Authorization": f"Bearer {token}"}

    common_window = {
        "account_id": ACCOUNT_ID,
        "date_from": date_from,
        "date_to": date_to,
        "limit": LIMIT,
        "offset": 0,
    }
    endpoints = {
        "dashboard_owner": ("/dashboard/owner", {"account_id": ACCOUNT_ID, "date_from": date_from, "date_to": date_to}),
        "dashboard_data_health": ("/dashboard/data-health", {"account_id": ACCOUNT_ID, "date_from": date_from, "date_to": date_to}),
        "dashboard_sku_profitability": ("/dashboard/sku-profitability", {**common_window, "sort": "profit_desc"}),
        "money_summary": ("/money/summary", {"account_id": ACCOUNT_ID, "date_from": date_from, "date_to": date_to}),
        "money_profit_cascade": ("/money/profit-cascade", {"account_id": ACCOUNT_ID, "date_from": date_from, "date_to": date_to}),
        "money_cards": ("/money/cards", {**common_window, "sort_by": "priority_score", "sort_dir": "desc"}),
        "skus": ("/skus", common_window),
        "purchase_plan": ("/inventory/purchase-plan", common_window),
        "price_safety": ("/pricing/safety", common_window),
        "ads_efficiency": ("/ads/efficiency", common_window),
        "reconciliation_daily": ("/marts/reconciliation-daily", common_window),
        "dq_issues": ("/dq/issues", {"account_id": ACCOUNT_ID, "only_open": True, "limit": LIMIT, "offset": 0}),
    }
    payloads: dict[str, Any] = {}
    for key, (path, params) in endpoints.items():
        response = client.get(f"{BASE_URL}{path}", params=params, headers=headers)
        response.raise_for_status()
        payloads[key] = response.json()

    coverage = {
        "purchase_plan": {
            "days_of_stock": _count_missing(_page_items(payloads["purchase_plan"]), "days_of_stock"),
            "available_stock": _count_missing(_page_items(payloads["purchase_plan"]), "available_stock"),
            "in_transit_qty": _count_missing(_page_items(payloads["purchase_plan"]), "in_transit_qty"),
        },
        "price_safety": {
            "average_sale_price": _count_missing(_page_items(payloads["price_safety"]), "average_sale_price"),
            "action_hint": _count_missing(_page_items(payloads["price_safety"]), "action_hint"),
            "not_computable_reason": _count_missing(_page_items(payloads["price_safety"]), "not_computable_reason"),
        },
        "ads_efficiency": {
            "advert_id": _count_missing(_page_items(payloads["ads_efficiency"]), "advert_id"),
            "action_hint": _count_missing(_page_items(payloads["ads_efficiency"]), "action_hint"),
        },
        "reconciliation_daily": {
            "opening_stock_qty": _count_missing(_page_items(payloads["reconciliation_daily"]), "opening_stock_qty"),
            "closing_stock_qty": _count_missing(_page_items(payloads["reconciliation_daily"]), "closing_stock_qty"),
            "avg_sale_price": _count_missing(_page_items(payloads["reconciliation_daily"]), "avg_sale_price"),
        },
        "dq_issues": {
            "source_domains": _count_missing(_page_items(payloads["dq_issues"]), "source_domains"),
            "candidate_sku_ids": _count_missing(_page_items(payloads["dq_issues"]), "candidate_sku_ids"),
            "mapped_sku_id": _count_missing(_page_items(payloads["dq_issues"]), "mapped_sku_id"),
        },
    }

    owner = payloads["dashboard_owner"]
    summary_kpis = payloads["money_summary"].get("kpis", {})
    cascade_totals = payloads["money_profit_cascade"]["cascade"]["totals"]
    consistency = {
        "owner_vs_summary": _compare_numeric_fields(
            owner,
            summary_kpis,
            [
                "revenue_final",
                ("total_wb_expenses", "wb_expenses_total"),
                "seller_cogs",
                "seller_other_expense",
                "total_seller_costs",
                "ad_spend_final",
                "additional_income",
                "net_profit_after_all_expenses",
            ],
        ),
        "summary_vs_profit_cascade": _compare_numeric_fields(
            summary_kpis,
            cascade_totals,
            [
                ("revenue_final", "gross_revenue"),
                ("wb_expenses_total", "total_wb_expenses"),
                ("total_seller_costs", "total_seller_expenses"),
                ("ad_spend_final", "total_ad_expenses"),
                "additional_income",
                "net_profit_after_all_expenses",
            ],
        ),
    }

    notes = [
        "purchase_plan WAIT_DATA rows with positive stock may still be blocked by trust_state=data_blocked, not by missing stock only.",
        "reconciliation_daily stock nulls are mostly source-data gaps: many mart_sku_daily rows have no matching mart_stock_daily snapshot on or before the date.",
        "price_safety average_sale_price nulls are usually expected for SKUs without realized sales in the selected window.",
        "ads_efficiency advert_id nulls are expected when spend is allocated from article-level or multi-campaign data.",
    ]

    report = {
        "meta": {
            "generated_at": now.isoformat(),
            "base_url": BASE_URL,
            "account_id": ACCOUNT_ID,
            "date_from": date_from,
            "date_to": date_to,
            "limit": LIMIT,
        },
        "consistency": consistency,
        "coverage": coverage,
        "notes": notes,
        "samples": {
            "purchase_plan": _page_items(payloads["purchase_plan"])[:10],
            "reconciliation_daily": _page_items(payloads["reconciliation_daily"])[:10],
            "price_safety": _page_items(payloads["price_safety"])[:10],
            "dq_issues": _page_items(payloads["dq_issues"])[:10],
        },
    }

    json_path = bundle_dir / "report.json"
    md_path = bundle_dir / "REPORT.md"
    _write_json(json_path, report)
    _write_text(md_path, _build_markdown(report))
    print(json.dumps({"bundle_dir": str(bundle_dir), "report_json": str(json_path), "report_md": str(md_path)}))


if __name__ == "__main__":
    main()
