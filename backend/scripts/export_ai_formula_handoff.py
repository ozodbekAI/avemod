from __future__ import annotations

import json
import os
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPO_ROOT / "exports"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_EMAIL = "audit-user@example.invalid"
DATE_TO = date(2026, 5, 18)
DATE_FROM = DATE_TO - timedelta(days=30)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slug_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise SystemExit(f"{name} is required; set it in the environment before running this export.")


def _to_decimal(value: Any) -> Decimal:
    if value in (None, "", "null"):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


@dataclass
class ApiCall:
    name: str
    path: str
    params: dict[str, Any] | None = None


class BackendClient:
    def __init__(self, *, base_url: str, email: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.session = requests.Session()
        self.token: str | None = None

    def login(self) -> dict[str, Any]:
        response = self.session.post(
            f"{self.base_url}/auth/login",
            json={"email": self.email, "password": self.password},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        self.token = payload["access_token"]
        return payload

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        response = self.session.get(
            f"{self.base_url}/{path.lstrip('/')}",
            params=params,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text


def _build_formula_doc() -> str:
    return f"""# Formula Mapping for AI Verification

## Scope
This file explains how to verify backend business calculations against real endpoint responses.

## Primary Date Window Used in This Bundle
- `date_from={DATE_FROM.isoformat()}`
- `date_to={DATE_TO.isoformat()}`

## Core Formula: `mart_sku_daily`

### Revenue Source
- `final_revenue_source = "finance"` when finance rows exist for the SKU/day
- otherwise `final_revenue_source = "operational"`

### Unit Cost
- `total_unit_cost = cost_price + packaging_cost + inbound_logistics_cost`

### Estimated COGS
- `estimated_cogs = total_unit_cost * final_net_qty`

### Profit Before Ads
When `has_manual_cost = true`:

```text
estimated_profit_before_ads =
    final_revenue
  - commission
  - logistics
  - storage
  - paid_acceptance
  - acquiring_fee
  - penalties
  - deductions
  - estimated_cogs
  + additional_payments
```

### Profit After Ads
When `has_manual_cost = true`:

```text
estimated_profit_after_ads =
    estimated_profit_before_ads
  - ad_spend
```

### Margin
When `final_revenue > 0` and `has_manual_cost = true`:

```text
margin_percent = estimated_profit_after_ads / final_revenue * 100
```

### ROI
When `estimated_cogs > 0` and `has_manual_cost = true`:

```text
roi_percent = estimated_profit_after_ads / estimated_cogs * 100
```

### DRR
When `final_revenue > 0`:

```text
drr_percent = ad_spend / final_revenue * 100
```

## Aggregated Formula: `GET /dashboard/sku-profitability`

The profitability endpoint aggregates `mart_sku_daily` rows by SKU and period.

### Aggregation Mapping
- `realized_revenue = sum(final_revenue)`
- `for_pay = sum(final_for_pay)`
- `commission = sum(commission)`
- `acquiring_fee = sum(acquiring_fee)`
- `logistics = sum(logistics)`
- `paid_acceptance = sum(paid_acceptance)`
- `storage = sum(storage)`
- `penalties = sum(penalties)`
- `deductions = sum(deductions)`
- `additional_payments = sum(additional_payments)`
- `ad_spend = sum(ad_spend)`
- `estimated_cogs = sum(estimated_cogs)` only when cost coverage exists

### Aggregated Profit
When `has_manual_cost = true` for the aggregated SKU result:

```text
estimated_profit =
    realized_revenue
  - commission
  - logistics
  - storage
  - paid_acceptance
  - acquiring_fee
  - penalties
  - deductions
  - ad_spend
  - estimated_cogs
  + additional_payments
```

### Aggregated Margin / ROI / DRR
```text
margin_percent = estimated_profit / realized_revenue * 100
roi_percent = estimated_profit / estimated_cogs * 100
drr_percent = ad_spend / realized_revenue * 100
```

## Audit Rules for the External AI
The external AI should verify:
1. Formula math on sample mart rows.
2. Formula math on sample aggregated profitability rows.
3. `article-audit.daily_economics` consistency with `mart_sku_daily` for the same SKU/article and date range.
4. Whether missing cost or missing SKU links make profit fields intentionally null.
5. Whether finance-vs-operational source choice explains gaps in cost coverage.

## Important Business Caveat
Current manual costs in this environment are placeholder `AUTO_TEMPLATE` values, not real supplier costs.
So:
- formula correctness can be tested
- endpoint consistency can be tested
- real business profitability cannot yet be trusted as final truth
"""


def _build_prompt(bundle_slug: str) -> str:
    return f"""# AI Prompt for Endpoint + Formula Validation

You are reviewing a Wildberries Data Core backend handoff bundle.

Bundle: `{bundle_slug}`

Your task:
1. Read the endpoint responses under `api/`.
2. Read `FORMULAS.md`.
3. Read `formula_checks.json`.
4. Verify whether the backend responses are internally consistent with the documented formulas.
5. Separate:
   - math/formula correctness
   - API contract correctness
   - data completeness gaps
   - business trust issues caused by placeholder cost or missing source linkage

Please return:
1. Executive summary
2. Formula validation result
3. Endpoint consistency result
4. Data trust risks
5. Recommended next actions
"""


def _build_readme(bundle_slug: str) -> str:
    return f"""# AI Formula Handoff Bundle

Bundle slug: `{bundle_slug}`

This bundle is designed for external AI testing of:
- backend endpoint contracts
- business formulas
- real sample responses

## Send these files
1. `FORMULAS.md`
2. `API_REQUEST_MAP.md`
3. `formula_checks.json`
4. the entire `api/` folder
5. `PROMPT.md`

## Notes
- Data is from the live local backend at generation time.
- This environment uses placeholder manual cost rows (`AUTO_TEMPLATE`), so profit math can be tested but business truth is still provisional.
"""


def _build_api_request_map(calls: list[ApiCall], sample_sku_id: int | None, sample_nm_id: int | None) -> str:
    lines = [
        "# API Request Map",
        "",
        "This file shows exactly which backend requests were used to build the AI handoff bundle.",
        "",
        f"- Period: `{DATE_FROM.isoformat()} .. {DATE_TO.isoformat()}`",
        f"- Sample SKU ID: `{sample_sku_id}`",
        f"- Sample nmId: `{sample_nm_id}`",
        "",
    ]
    for call in calls:
        lines.append(f"## {call.name}")
        lines.append("")
        query = ""
        if call.params:
            parts = [f"{key}={value}" for key, value in call.params.items() if value is not None]
            if parts:
                query = "?" + "&".join(parts)
        lines.append(f"`GET /api/v1/{call.path}{query}`")
        lines.append("")
    return "\n".join(lines)


def _collect_formula_checks(
    *,
    profitability_payload: dict[str, Any],
    mart_payload: dict[str, Any],
    article_audit_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    mart_checks: list[dict[str, Any]] = []
    for row in mart_payload.get("items", [])[:20]:
        if not row.get("has_manual_cost"):
            continue
        final_revenue = _to_decimal(row.get("final_revenue"))
        commission = _to_decimal(row.get("commission"))
        logistics = _to_decimal(row.get("logistics"))
        storage = _to_decimal(row.get("storage"))
        paid_acceptance = _to_decimal(row.get("paid_acceptance"))
        acquiring_fee = _to_decimal(row.get("acquiring_fee"))
        penalties = _to_decimal(row.get("penalties"))
        deductions = _to_decimal(row.get("deductions"))
        estimated_cogs = _to_decimal(row.get("estimated_cogs"))
        additional_payments = _to_decimal(row.get("additional_payments"))
        ad_spend = _to_decimal(row.get("ad_spend"))

        expected_before_ads = (
            final_revenue
            - commission
            - logistics
            - storage
            - paid_acceptance
            - acquiring_fee
            - penalties
            - deductions
            - estimated_cogs
            + additional_payments
        )
        expected_after_ads = expected_before_ads - ad_spend
        expected_margin = (expected_after_ads / final_revenue * Decimal("100")) if final_revenue > 0 else None
        expected_roi = (expected_after_ads / estimated_cogs * Decimal("100")) if estimated_cogs > 0 else None
        expected_drr = (ad_spend / final_revenue * Decimal("100")) if final_revenue > 0 else None

        mart_checks.append(
            {
                "row_id": row.get("id"),
                "stat_date": row.get("stat_date"),
                "sku_id": row.get("sku_id"),
                "nm_id": row.get("nm_id"),
                "expected_profit_before_ads": str(expected_before_ads),
                "actual_profit_before_ads": str(row.get("estimated_profit_before_ads")),
                "before_ads_match": _to_decimal(row.get("estimated_profit_before_ads")) == expected_before_ads,
                "expected_profit_after_ads": str(expected_after_ads),
                "actual_profit_after_ads": str(row.get("estimated_profit_after_ads")),
                "after_ads_match": _to_decimal(row.get("estimated_profit_after_ads")) == expected_after_ads,
                "expected_margin_percent": str(expected_margin) if expected_margin is not None else None,
                "actual_margin_percent": str(row.get("margin_percent")),
                "expected_roi_percent": str(expected_roi) if expected_roi is not None else None,
                "actual_roi_percent": str(row.get("roi_percent")),
                "expected_drr_percent": str(expected_drr) if expected_drr is not None else None,
                "actual_drr_percent": str(row.get("drr_percent")),
            }
        )

    profitability_checks: list[dict[str, Any]] = []
    for row in profitability_payload.get("items", [])[:20]:
        if not row.get("has_manual_cost"):
            continue
        realized_revenue = _to_decimal(row.get("realized_revenue"))
        commission = _to_decimal(row.get("commission"))
        logistics = _to_decimal(row.get("logistics"))
        storage = _to_decimal(row.get("storage"))
        paid_acceptance = _to_decimal(row.get("paid_acceptance"))
        acquiring_fee = _to_decimal(row.get("acquiring_fee"))
        penalties = _to_decimal(row.get("penalties"))
        deductions = _to_decimal(row.get("deductions"))
        estimated_cogs = _to_decimal(row.get("estimated_cogs"))
        additional_payments = _to_decimal(row.get("additional_payments"))
        ad_spend = _to_decimal(row.get("ad_spend"))
        expected_profit = (
            realized_revenue
            - commission
            - logistics
            - storage
            - paid_acceptance
            - acquiring_fee
            - penalties
            - deductions
            - ad_spend
            - estimated_cogs
            + additional_payments
        )
        profitability_checks.append(
            {
                "sku_id": row.get("sku_id"),
                "nm_id": row.get("nm_id"),
                "expected_estimated_profit": str(expected_profit),
                "actual_estimated_profit": str(row.get("estimated_profit")),
                "profit_match": _to_decimal(row.get("estimated_profit")) == expected_profit,
            }
        )

    article_check: dict[str, Any] | None = None
    if article_audit_payload is not None:
        daily_economics = article_audit_payload.get("daily_economics") or {}
        mart_rows = mart_payload.get("items", [])
        revenue = sum((_to_decimal(item.get("final_revenue")) for item in mart_rows), start=Decimal("0"))
        ad_spend = sum((_to_decimal(item.get("ad_spend")) for item in mart_rows), start=Decimal("0"))
        article_check = {
            "expected_revenue_from_mart_sum": str(revenue),
            "actual_article_audit_revenue": str(daily_economics.get("revenue")),
            "revenue_matches": _to_decimal(daily_economics.get("revenue")) == revenue,
            "expected_ad_spend_from_mart_sum": str(ad_spend),
            "actual_article_audit_ad_spend": str(daily_economics.get("ad_spend")),
            "ad_spend_matches": _to_decimal(daily_economics.get("ad_spend")) == ad_spend,
        }

    return {
        "window": {"date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
        "mart_row_checks": mart_checks,
        "profitability_checks": profitability_checks,
        "article_audit_check": article_check,
    }


def main() -> None:
    generated_at = _utc_now()
    bundle_slug = f"ai_formula_handoff_{_slug_timestamp(generated_at)}"
    bundle_dir = EXPORTS_DIR / bundle_slug
    api_dir = bundle_dir / "api"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    api_dir.mkdir(parents=True, exist_ok=True)

    base_url = os.getenv("AI_HANDOFF_BASE_URL", DEFAULT_BASE_URL)
    email = os.getenv("AI_HANDOFF_EMAIL", DEFAULT_EMAIL)
    password = _required_env("AI_HANDOFF_PASSWORD")

    client = BackendClient(base_url=base_url, email=email, password=password)
    token_pair = client.login()

    calls: list[ApiCall] = []

    def record_get(name: str, path: str, params: dict[str, Any] | None = None) -> Any:
        calls.append(ApiCall(name=name, path=path, params=params))
        payload = client.get(path, params=params)
        _write_json(api_dir / f"{name}.json", payload)
        return payload

    def record_get_all_pages(name: str, path: str, params: dict[str, Any] | None = None, *, page_limit: int = 200) -> Any:
        base_params = dict(params or {})
        base_params["limit"] = page_limit
        base_params["offset"] = 0
        first_payload = client.get(path, params=base_params)
        if not isinstance(first_payload, dict) or "items" not in first_payload:
            calls.append(ApiCall(name=name, path=path, params=base_params))
            _write_json(api_dir / f"{name}.json", first_payload)
            return first_payload
        total = int(first_payload.get("total") or len(first_payload.get("items") or []))
        items = list(first_payload.get("items") or [])
        calls.append(ApiCall(name=f"{name}:page0", path=path, params=base_params))
        offset = page_limit
        while offset < total:
            page_params = {**base_params, "offset": offset}
            calls.append(ApiCall(name=f"{name}:page{offset // page_limit}", path=path, params=page_params))
            page_payload = client.get(path, params=page_params)
            items.extend(list(page_payload.get("items") or []))
            offset += page_limit
        payload = {**first_payload, "items": items, "limit": page_limit, "offset": 0, "fetched_all_pages": True}
        _write_json(api_dir / f"{name}.json", payload)
        return payload

    health = record_get("health", "health")
    accounts = record_get("accounts", "accounts", {"include_inactive": False})
    account_id = accounts[0]["id"] if accounts else 1

    dashboard_health = record_get(
        "dashboard_data_health",
        "dashboard/data-health",
        {"account_id": account_id, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
    )
    core_sku_sample = record_get(
        "core_sku_sample",
        "core-sku",
        {"account_id": account_id, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 20, "offset": 0},
    )
    core_sku_issues_sample = record_get(
        "core_sku_with_issues_sample",
        "core-sku",
        {
            "account_id": account_id,
            "has_open_issues": True,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 20,
            "offset": 0,
        },
    )
    profitability = record_get(
        "sku_profitability_top",
        "dashboard/sku-profitability",
        {
            "account_id": account_id,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 20,
            "offset": 0,
            "sort": "profit_desc",
        },
    )

    sample_profit_item = next((item for item in profitability.get("items", []) if item.get("sku_id")), None)
    sample_sku_id = sample_profit_item["sku_id"] if sample_profit_item else None
    sample_nm_id = sample_profit_item["nm_id"] if sample_profit_item else None

    article_audit = None
    mart_sku_daily = {"items": []}
    reconciliation_daily = {"items": []}
    if sample_sku_id is not None and sample_nm_id is not None:
        record_get(
            "core_sku_detail_sample",
            f"core-sku/{sample_sku_id}",
            {"date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
        )
        article_audit = record_get(
            "article_audit_sample",
            "dashboard/article-audit",
            {
                "account_id": account_id,
                "nm_id": sample_nm_id,
                "date_from": DATE_FROM.isoformat(),
                "date_to": DATE_TO.isoformat(),
            },
        )
        mart_sku_daily = record_get_all_pages(
            "mart_sku_daily_sample",
            "marts/sku-daily",
            {
                "account_id": account_id,
                "nm_id": sample_nm_id,
                "date_from": DATE_FROM.isoformat(),
                "date_to": DATE_TO.isoformat(),
            },
            page_limit=200,
        )
        reconciliation_daily = record_get(
            "reconciliation_daily_sample",
            "marts/reconciliation-daily",
            {
                "account_id": account_id,
                "sku_id": sample_sku_id,
                "date_from": DATE_FROM.isoformat(),
                "date_to": DATE_TO.isoformat(),
                "limit": 120,
                "offset": 0,
            },
        )

    dq_issues = record_get(
        "dq_open_sample",
        "dq/issues",
        {
            "account_id": account_id,
            "only_open": True,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 50,
            "offset": 0,
        },
    )
    finance_reports = record_get(
        "finance_reports_sample",
        "finance/reports",
        {
            "account_id": account_id,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 20,
            "offset": 0,
        },
    )
    finance_report_rows = record_get(
        "finance_report_rows_sample",
        "finance/report-rows",
        {
            "account_id": account_id,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 50,
            "offset": 0,
        },
    )
    orders_sample = record_get(
        "orders_sample",
        "orders",
        {
            "account_id": account_id,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 50,
            "offset": 0,
        },
    )
    sales_sample = record_get(
        "sales_sample",
        "sales",
        {
            "account_id": account_id,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "limit": 50,
            "offset": 0,
        },
    )
    stocks_sample = record_get(
        "stocks_sample",
        "stocks/snapshots",
        {"account_id": account_id, "limit": 50, "offset": 0},
    )
    ads_stats_sample = record_get(
        "ads_stats_sample",
        "ads/stats",
        {"account_id": account_id, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 50, "offset": 0},
    )
    analytics_funnel_sample = record_get(
        "analytics_funnel_sample",
        "analytics/funnel",
        {"account_id": account_id, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 50, "offset": 0},
    )

    _write_text(bundle_dir / "FORMULAS.md", _build_formula_doc())
    _write_text(bundle_dir / "PROMPT.md", _build_prompt(bundle_slug))
    _write_text(bundle_dir / "README.md", _build_readme(bundle_slug))
    _write_text(
        bundle_dir / "API_REQUEST_MAP.md",
        _build_api_request_map(calls, sample_sku_id=sample_sku_id, sample_nm_id=sample_nm_id),
    )

    formula_checks = _collect_formula_checks(
        profitability_payload=profitability,
        mart_payload=mart_sku_daily,
        article_audit_payload=article_audit,
    )
    _write_json(bundle_dir / "formula_checks.json", formula_checks)

    meta = {
        "generated_at": generated_at.isoformat(),
        "bundle_slug": bundle_slug,
        "base_url": base_url,
        "account_id": account_id,
        "sample_sku_id": sample_sku_id,
        "sample_nm_id": sample_nm_id,
        "date_from": DATE_FROM.isoformat(),
        "date_to": DATE_TO.isoformat(),
        "token_pair_shape": {"token_type": token_pair.get("token_type"), "has_access_token": bool(token_pair.get("access_token")), "has_refresh_token": bool(token_pair.get("refresh_token"))},
        "health": health,
        "dashboard_health_headline": {
            "open_issues_total": dashboard_health.get("open_issues_total"),
            "missing_manual_cost_count": dashboard_health.get("missing_manual_cost_count"),
            "unmatched_sku_count": dashboard_health.get("unmatched_sku_count"),
            "revenue_cost_coverage_percent": dashboard_health.get("revenue_cost_coverage_percent"),
            "placeholder_manual_cost_count": dashboard_health.get("placeholder_manual_cost_count"),
            "ad_cluster_rows": dashboard_health.get("ad_cluster_rows"),
        },
    }
    _write_json(bundle_dir / "meta.json", meta)

    zip_path = EXPORTS_DIR / f"{bundle_slug}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in bundle_dir.rglob("*"):
            zf.write(path, path.relative_to(bundle_dir.parent))

    print(json.dumps({"bundle_dir": str(bundle_dir), "zip_path": str(zip_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
