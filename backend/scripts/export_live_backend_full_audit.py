from __future__ import annotations

import json
import os
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPO_ROOT / "exports"
DOCS_DIR = REPO_ROOT / "docs"

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_EMAIL = "audit-user@example.invalid"
DEFAULT_ACCOUNT_ID = 1
DEFAULT_ACCOUNT_NAME = "wb-live-test"
NGROK_HEADER = {"ngrok-skip-browser-warning": "true"}
MAX_BODY_CHARS = 300_000
MAX_LIST_ITEMS = 5
MAX_CAPTURE_WORKERS = int(os.getenv("BACKEND_AUDIT_CAPTURE_WORKERS", "8"))
CAPTURE_PAGE_RETRIES = int(os.getenv("BACKEND_AUDIT_CAPTURE_PAGE_RETRIES", "3"))
BASE_URL = os.getenv("BACKEND_AUDIT_BASE_URL", DEFAULT_BASE_URL)
AUDIT_EMAIL = os.getenv("BACKEND_AUDIT_EMAIL", DEFAULT_EMAIL)
AUDIT_ACCOUNT_ID = os.getenv("BACKEND_AUDIT_ACCOUNT_ID")
AUDIT_ACCOUNT_NAME = os.getenv("BACKEND_AUDIT_ACCOUNT_NAME", DEFAULT_ACCOUNT_NAME)
AUDIT_DATE_FROM = os.getenv("BACKEND_AUDIT_DATE_FROM")
AUDIT_DATE_TO = os.getenv("BACKEND_AUDIT_DATE_TO")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise SystemExit(f"{name} is required; set it in the environment before running this audit.")

ALL_ROUTER_SPECS: list[dict[str, Any]] = [
    {"label": "health", "router_file": "app/modules/health/router.py", "path_prefixes": ["/health"]},
    {"label": "auth", "router_file": "app/modules/auth/router.py", "path_prefixes": ["/auth", "/users"]},
    {"label": "accounts", "router_file": "app/modules/accounts/router.py", "path_prefixes": ["/accounts"]},
    {
        "label": "control-tower",
        "router_file": "app/modules/control_tower/router.py",
        "path_prefixes": ["/dashboard/owner", "/skus", "/actions", "/alerts", "/inventory/purchase-plan", "/pricing", "/ads/efficiency", "/settings/business"],
    },
    {"label": "money-management", "router_file": "app/modules/money_management/router.py", "path_prefixes": ["/money"]},
    {
        "label": "dashboard",
        "router_file": "app/modules/dashboard/router.py",
        "path_prefixes": ["/dashboard/data-health", "/dashboard/sku-profitability", "/dashboard/article-audit"],
    },
    {"label": "marts", "router_file": "app/modules/marts/router.py", "path_prefixes": ["/marts"]},
    {"label": "data-quality", "router_file": "app/modules/data_quality/router.py", "path_prefixes": ["/dq/issues"]},
    {"label": "core-sku", "router_file": "app/modules/core_sku/router.py", "path_prefixes": ["/core-sku"]},
    {"label": "product-cards", "router_file": "app/modules/product_cards/router.py", "path_prefixes": ["/products"]},
    {"label": "prices", "router_file": "app/modules/prices/router.py", "path_prefixes": ["/prices"]},
    {"label": "orders", "router_file": "app/modules/orders/router.py", "path_prefixes": ["/orders"]},
    {"label": "sales", "router_file": "app/modules/sales/router.py", "path_prefixes": ["/sales"]},
    {"label": "stocks", "router_file": "app/modules/stocks/router.py", "path_prefixes": ["/stocks/snapshots"]},
    {"label": "documents", "router_file": "app/modules/documents/router.py", "path_prefixes": ["/documents"]},
    {"label": "finance", "router_file": "app/modules/finance/router.py", "path_prefixes": ["/finance", "/balance"]},
    {"label": "manual-costs", "router_file": "app/modules/manual_costs/router.py", "path_prefixes": ["/costs"]},
    {"label": "ads", "router_file": "app/modules/ads/router.py", "path_prefixes": ["/ads/campaigns", "/ads/stats"]},
    {"label": "analytics", "router_file": "app/modules/analytics/router.py", "path_prefixes": ["/analytics"]},
    {"label": "sync", "router_file": "app/modules/sync/router.py", "path_prefixes": ["/sync"]},
    {"label": "supplies", "router_file": "app/modules/supplies/router.py", "path_prefixes": ["/supplies"]},
    {"label": "tariffs", "router_file": "app/modules/tariffs/router.py", "path_prefixes": ["/tariffs"]},
    {"label": "meta", "router_file": "app/modules/meta/router.py", "path_prefixes": ["/meta"]},
    {"label": "exports", "router_file": "app/modules/exports/router.py", "path_prefixes": ["/export"]},
]

FINANCE_ROUTER_SPECS: list[dict[str, Any]] = [
    {
        "label": "finance",
        "router_file": "app/modules/finance/router.py",
        "path_prefixes": ["/finance", "/balance"],
    },
    {
        "label": "money-management",
        "router_file": "app/modules/money_management/router.py",
        "path_prefixes": ["/money"],
    },
    {
        "label": "marts",
        "router_file": "app/modules/marts/router.py",
        "path_prefixes": ["/marts"],
    },
    {
        "label": "control-tower",
        "router_file": "app/modules/control_tower/router.py",
        "path_prefixes": ["/dashboard/owner", "/actions", "/alerts", "/inventory/purchase-plan", "/pricing", "/ads/efficiency", "/settings/business", "/skus"],
    },
    {
        "label": "dashboard",
        "router_file": "app/modules/dashboard/router.py",
        "path_prefixes": ["/dashboard/data-health", "/dashboard/sku-profitability", "/dashboard/article-audit"],
    },
    {
        "label": "manual-costs",
        "router_file": "app/modules/manual_costs/router.py",
        "path_prefixes": ["/costs"],
    },
    {
        "label": "ads",
        "router_file": "app/modules/ads/router.py",
        "path_prefixes": ["/ads/campaigns", "/ads/stats"],
    },
    {
        "label": "analytics",
        "router_file": "app/modules/analytics/router.py",
        "path_prefixes": ["/analytics"],
    },
    {
        "label": "exports",
        "router_file": "app/modules/exports/router.py",
        "path_prefixes": ["/export"],
    },
]


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


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _schema_name(schema: dict[str, Any] | None) -> str | None:
    if not schema:
        return None
    if "$ref" in schema:
        return str(schema["$ref"]).split("/")[-1]
    if "items" in schema and isinstance(schema["items"], dict) and "$ref" in schema["items"]:
        return f"array[{str(schema['items']['$ref']).split('/')[-1]}]"
    type_name = schema.get("type")
    if type_name:
        return str(type_name)
    if "anyOf" in schema:
        return "anyOf"
    if "oneOf" in schema:
        return "oneOf"
    return None


def _extract_response_contracts(operation: dict[str, Any]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for status_code, response in (operation.get("responses") or {}).items():
        content = response.get("content") or {}
        content_types = list(content.keys())
        schema_names = []
        for _, content_meta in content.items():
            schema_name = _schema_name(content_meta.get("schema"))
            if schema_name:
                schema_names.append(schema_name)
        results[status_code] = {
            "description": response.get("description"),
            "content_types": content_types,
            "schema_names": schema_names,
        }
    return results


def _extract_request_contract(operation: dict[str, Any]) -> dict[str, Any] | None:
    request_body = operation.get("requestBody")
    if not request_body:
        return None
    content = request_body.get("content") or {}
    content_types = list(content.keys())
    schema_names = []
    for _, content_meta in content.items():
        schema_name = _schema_name(content_meta.get("schema"))
        if schema_name:
            schema_names.append(schema_name)
    return {
        "required": bool(request_body.get("required")),
        "content_types": content_types,
        "schema_names": schema_names,
    }


def _extract_parameters(operation: dict[str, Any]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for parameter in operation.get("parameters") or []:
        schema = parameter.get("schema") or {}
        results.append(
            {
                "name": parameter.get("name"),
                "in": parameter.get("in"),
                "required": bool(parameter.get("required")),
                "type": schema.get("type"),
                "format": schema.get("format"),
                "default": schema.get("default"),
            }
        )
    return results


def _build_contract_index(openapi: dict[str, Any]) -> list[dict[str, Any]]:
    contracts: list[dict[str, Any]] = []
    for path, path_item in sorted((openapi.get("paths") or {}).items()):
        for method, operation in sorted(path_item.items()):
            if method.lower() not in {"get", "post", "patch", "put", "delete"}:
                continue
            contracts.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": operation.get("summary"),
                    "operation_id": operation.get("operationId"),
                    "tags": operation.get("tags") or [],
                    "auth_required": bool(operation.get("security")),
                    "parameters": _extract_parameters(operation),
                    "request_body": _extract_request_contract(operation),
                    "responses": _extract_response_contracts(operation),
                }
            )
    return contracts


def _shape_of(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shape_of(inner) for key, inner in list(value.items())[:20]}
    if isinstance(value, list):
        if not value:
            return []
        return [_shape_of(value[0])]
    return type(value).__name__


def _sample_json(value: Any, *, max_items: int = MAX_LIST_ITEMS, depth: int = 0) -> Any:
    if depth >= 4:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return {key: _sample_json(inner, max_items=max_items, depth=depth + 1) for key, inner in value.items()}
    if isinstance(value, list):
        return [_sample_json(item, max_items=max_items, depth=depth + 1) for item in value[:max_items]]
    return value


def _sample_response_body(body: Any) -> tuple[Any, bool]:
    serialized = json.dumps(body, ensure_ascii=False, default=_json_default)
    if len(serialized) <= MAX_BODY_CHARS:
        return body, False
    return _sample_json(body), True


def _redact_sensitive(value: Any) -> Any:
    sensitive_keys = {"password", "access_token", "refresh_token", "token"}
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner in value.items():
            if key in sensitive_keys and inner not in (None, ""):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_sensitive(inner)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    return value


@dataclass
class ExecutedEndpoint:
    method: str
    path_template: str
    path: str
    params: dict[str, Any] | None = None
    json_body: dict[str, Any] | None = None
    auth: bool = True
    binary: bool = False
    live_execute: bool = True
    note: str | None = None


class BackendClient:
    def __init__(self, *, base_url: str, email: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.email = email
        self.password = password
        self.client = httpx.Client(
            follow_redirects=True,
            headers=NGROK_HEADER.copy(),
            timeout=httpx.Timeout(120.0, connect=30.0),
        )
        self.access_token: str | None = None
        self.refresh_token: str | None = None

    @property
    def root_url(self) -> str:
        if self.base_url.endswith("/api/v1"):
            return self.base_url[: -len("/api/v1")]
        return self.base_url

    def _headers(self, *, auth: bool) -> dict[str, str]:
        headers = NGROK_HEADER.copy()
        if auth and self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
        full_url: bool = False,
    ) -> httpx.Response:
        url = path if full_url else f"{self.base_url}/{path.lstrip('/')}"
        return self.client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=self._headers(auth=auth),
        )

    def login(self) -> dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/login",
            json_body={"email": self.email, "password": self.password},
            auth=False,
        )
        response.raise_for_status()
        payload = response.json()
        self.access_token = payload.get("access_token")
        self.refresh_token = payload.get("refresh_token")
        return payload

    def refresh(self) -> dict[str, Any]:
        response = self.request(
            "POST",
            "/auth/refresh",
            json_body={"refresh_token": self.refresh_token},
            auth=False,
        )
        response.raise_for_status()
        payload = response.json()
        self.access_token = payload.get("access_token")
        self.refresh_token = payload.get("refresh_token")
        return payload

    def fetch_openapi(self) -> dict[str, Any]:
        candidates = [
            f"{self.root_url}/openapi.json",
            f"{self.base_url}/openapi.json",
        ]
        for candidate in candidates:
            response = self.request("GET", candidate, auth=False, full_url=True)
            if response.status_code == 200:
                return response.json()
        raise RuntimeError(f"Could not fetch OpenAPI JSON from {candidates}")


DATA_SOURCE_MAP: list[dict[str, Any]] = [
    {
        "path_prefixes": ["/meta"],
        "db_tables": [],
        "upstream_wb_apis": [],
        "layer": "metadata",
        "notes": "Internal enum/label metadata for frontend rendering and AI interpretation.",
    },
    {
        "path_prefixes": ["/auth", "/users"],
        "db_tables": ["auth_users", "auth_refresh_tokens"],
        "upstream_wb_apis": [],
        "layer": "admin-auth",
        "notes": "Internal admin auth layer, not WB data.",
    },
    {
        "path_prefixes": ["/accounts", "/accounts/{account_id}/tokens"],
        "db_tables": ["wb_accounts", "wb_api_tokens"],
        "upstream_wb_apis": [],
        "layer": "account-config",
        "notes": "Seller cabinet registry and token metadata.",
    },
    {
        "path_prefixes": ["/products", "/core-sku"],
        "db_tables": ["wb_product_cards", "wb_product_card_sizes", "core_sku", "data_quality_issues", "manual_costs"],
        "upstream_wb_apis": ["https://content-api.wildberries.ru/content/v2/get/cards/list"],
        "layer": "identity",
        "notes": "Core identity layer built on top of WB product cards and local SKU resolution.",
    },
    {
        "path_prefixes": ["/prices", "/pricing/safety", "/pricing/simulate"],
        "db_tables": ["wb_prices", "wb_price_sizes", "core_sku", "mart_sku_daily", "manual_costs"],
        "upstream_wb_apis": [
            "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter",
            "https://discounts-prices-api.wildberries.ru/api/v2/list/goods/size/nm",
        ],
        "layer": "price",
        "notes": "Raw price snapshots plus business price safety calculations.",
    },
    {
        "path_prefixes": ["/orders"],
        "db_tables": ["wb_orders"],
        "upstream_wb_apis": ["https://statistics-api.wildberries.ru/api/v1/supplier/orders"],
        "layer": "operations",
        "notes": "Operational order feed from WB statistics API.",
    },
    {
        "path_prefixes": ["/sales"],
        "db_tables": ["wb_sales"],
        "upstream_wb_apis": ["https://statistics-api.wildberries.ru/api/v1/supplier/sales"],
        "layer": "operations",
        "notes": "Operational sales/returns feed from WB statistics API.",
    },
    {
        "path_prefixes": ["/stocks/snapshots", "/marts/stock-daily"],
        "db_tables": ["wb_stock_snapshots", "wb_stock_snapshot_rows", "mart_stock_daily"],
        "upstream_wb_apis": [
            "https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains",
            "https://seller-analytics-api.wildberries.ru/api/v1/warehouse_remains/tasks/{task_id}/download",
        ],
        "layer": "stock",
        "notes": "Raw stock snapshot tasks and normalized stock daily mart.",
    },
    {
        "path_prefixes": ["/finance/reports", "/finance/report-rows", "/balance"],
        "db_tables": ["wb_realization_reports", "wb_realization_report_rows", "wb_balance_snapshots"],
        "upstream_wb_apis": [
            "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list",
            "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed",
            "https://finance-api.wildberries.ru/api/v1/account/balance",
        ],
        "layer": "finance",
        "notes": "Financial truth layer from WB finance reports and balance snapshots.",
    },
    {
        "path_prefixes": ["/documents"],
        "db_tables": ["wb_document_categories", "wb_documents"],
        "upstream_wb_apis": [
            "https://documents-api.wildberries.ru/api/v1/documents/categories",
            "https://documents-api.wildberries.ru/api/v1/documents/list",
        ],
        "layer": "documents",
        "notes": "WB documents metadata imported for admin visibility.",
    },
    {
        "path_prefixes": ["/supplies"],
        "db_tables": ["wb_supplies", "wb_supply_goods", "wb_supply_packages", "wb_supply_warehouses", "wb_supply_acceptance_options"],
        "upstream_wb_apis": [
            "https://supplies-api.wildberries.ru/api/v1/warehouses",
            "https://supplies-api.wildberries.ru/api/v1/acceptance/options",
            "https://supplies-api.wildberries.ru/api/v1/supplies",
        ],
        "layer": "supplies",
        "notes": "Inbound supply and warehouse acceptance data.",
    },
    {
        "path_prefixes": ["/ads/campaigns", "/ads/stats", "/ads/efficiency"],
        "db_tables": ["wb_ad_campaigns", "wb_ad_campaign_items", "wb_ad_stats_daily", "wb_ad_cluster_stats", "mart_sku_daily"],
        "upstream_wb_apis": [
            "https://advert-api.wildberries.ru/api/advert/v2/adverts",
            "https://advert-api.wildberries.ru/adv/v3/fullstats",
            "https://advert-api.wildberries.ru/adv/v1/normquery/stats",
        ],
        "layer": "ads",
        "notes": "Raw ad stats plus SKU-level ads efficiency aggregation.",
    },
    {
        "path_prefixes": ["/analytics/funnel", "/analytics/regions"],
        "db_tables": ["wb_card_funnel_daily", "wb_region_sales_daily", "wb_hidden_products"],
        "upstream_wb_apis": [
            "https://seller-analytics-api.wildberries.ru/api/analytics/v3/sales-funnel/products/history",
            "https://seller-analytics-api.wildberries.ru/api/v1/analytics/region-sale",
        ],
        "layer": "analytics",
        "notes": "Card funnel and regional sales analytics from WB analytics API.",
    },
    {
        "path_prefixes": ["/costs"],
        "db_tables": ["manual_cost_uploads", "manual_costs", "core_sku"],
        "upstream_wb_apis": [],
        "layer": "manual-costs",
        "notes": "External business input uploaded by operators, not sourced from WB.",
    },
    {
        "path_prefixes": ["/marts", "/dashboard/sku-profitability", "/dashboard/article-audit"],
        "db_tables": [
            "mart_sku_daily",
            "mart_stock_daily",
            "mart_finance_reconciliation",
            "mart_account_expense_daily",
            "mart_reconciliation_daily",
            "manual_costs",
            "data_quality_issues",
        ],
        "upstream_wb_apis": [],
        "layer": "business-marts",
        "notes": "Derived business tables built from normalized operational, finance, ads, and cost data.",
    },
    {
        "path_prefixes": ["/dashboard/data-health", "/dq/issues", "/dq/issues/investigator"],
        "db_tables": ["data_quality_issues", "wb_sync_runs", "wb_sync_cursors", "mart_sku_daily", "manual_costs", "wb_ad_cluster_stats"],
        "upstream_wb_apis": [],
        "layer": "quality-and-health",
        "notes": "Computed health and issue diagnostics over sync, mart, and manual cost layers.",
    },
    {
        "path_prefixes": ["/dashboard/owner", "/skus", "/actions", "/alerts", "/inventory/purchase-plan", "/settings/business"],
        "db_tables": [
            "mart_sku_daily",
            "mart_stock_daily",
            "action_recommendations",
            "action_recommendation_history",
            "alert_events",
            "user_business_settings",
            "user_business_settings_audit",
            "formula_audit_runs",
            "data_quality_issues",
        ],
        "upstream_wb_apis": [],
        "layer": "control-tower",
        "notes": "Operator-facing business control layer derived from marts, issues, settings, and recommendations.",
    },
    {
        "path_prefixes": ["/money"],
        "db_tables": [
            "mart_sku_daily",
            "mart_stock_daily",
            "mart_finance_reconciliation",
            "mart_account_expense_daily",
            "action_recommendations",
            "alert_events",
            "user_business_settings",
            "data_quality_issues",
            "manual_costs",
            "core_sku",
            "wb_ad_stats_daily",
        ],
        "upstream_wb_apis": [],
        "layer": "money-management",
        "notes": "Primary business-facing money management layer built over marts, actions, costs, stocks, and DQ trust gates.",
    },
    {
        "path_prefixes": ["/sync/runs", "/sync/cursors", "/sync/trigger", "/sync/backfill"],
        "db_tables": ["wb_sync_runs", "wb_sync_cursors", "raw_wb_api_responses"],
        "upstream_wb_apis": [],
        "layer": "sync-control",
        "notes": "Sync scheduler state and raw audit-log entrypoints.",
    },
    {
        "path_prefixes": ["/tariffs"],
        "db_tables": [
            "wb_tariff_commissions",
            "wb_tariff_boxes",
            "wb_tariff_pallets",
            "wb_tariff_returns",
            "wb_tariff_acceptance",
        ],
        "upstream_wb_apis": [
            "https://common-api.wildberries.ru/api/v1/tariffs/commission",
            "https://common-api.wildberries.ru/api/v1/tariffs/box",
            "https://common-api.wildberries.ru/api/v1/tariffs/pallet",
            "https://common-api.wildberries.ru/api/v1/tariffs/return",
            "https://common-api.wildberries.ru/api/tariffs/v1/acceptance/coefficients",
        ],
        "layer": "tariffs",
        "notes": "Reference tariff coefficients from WB common API.",
    },
]


def _data_source_for(path: str) -> dict[str, Any] | None:
    normalized_path = path
    if normalized_path.startswith("/api/v1"):
        normalized_path = normalized_path[len("/api/v1") :] or "/"
    for item in DATA_SOURCE_MAP:
        if any(normalized_path.startswith(prefix) for prefix in item["path_prefixes"]):
            return item
    return None


def _contracts_for_prefixes(
    contract_index: list[dict[str, Any]],
    path_prefixes: list[str],
) -> list[dict[str, Any]]:
    return [
        item
        for item in contract_index
        if any(
            (
                item["path"].startswith(prefix)
                or (
                    item["path"].startswith("/api/v1")
                    and (item["path"][len("/api/v1") :] or "/").startswith(prefix)
                )
            )
            for prefix in path_prefixes
        )
    ]


def _build_finance_router_inventory(contract_index: list[dict[str, Any]]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for spec in FINANCE_ROUTER_SPECS:
        source_path = REPO_ROOT / spec["router_file"]
        inventory.append(
            {
                "label": spec["label"],
                "router_file": spec["router_file"],
                "path_prefixes": spec["path_prefixes"],
                "router_exists": source_path.exists(),
                "endpoint_count": len(_contracts_for_prefixes(contract_index, spec["path_prefixes"])),
                "endpoints": _contracts_for_prefixes(contract_index, spec["path_prefixes"]),
            }
        )
    return inventory


def _build_finance_router_markdown(*, inventory: list[dict[str, Any]], base_url: str) -> str:
    lines = [
        "# Finance Router Audit",
        "",
        f"- Generated: `{_utc_now().isoformat()}`",
        f"- Backend: `{base_url}`",
        "- Scope: finance-related routers, their paths, and saved live/full-list captures.",
        "",
    ]
    for router in inventory:
        lines.append(f"## {router['label']}")
        lines.append("")
        lines.append(f"- Router file: `{router['router_file']}`")
        lines.append(f"- Path prefixes: `{', '.join(router['path_prefixes'])}`")
        lines.append(f"- Router exists: `{'yes' if router['router_exists'] else 'no'}`")
        lines.append(f"- Endpoint count: `{router['endpoint_count']}`")
        lines.append("")
        for endpoint in router["endpoints"]:
            lines.append(f"- `{endpoint['method']} {endpoint['path']}`")
        lines.append("")
    return "\n".join(lines)


def _parse_env_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _normalize_contract_path(path: str) -> str:
    if path.startswith("/api/v1"):
        return path[len("/api/v1") :] or "/"
    return path


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        return [item for item in payload["items"] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _build_router_inventory(
    *,
    router_specs: list[dict[str, Any]],
    contract_index: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    for spec in router_specs:
        source_path = REPO_ROOT / spec["router_file"]
        inventory.append(
            {
                "label": spec["label"],
                "router_file": spec["router_file"],
                "path_prefixes": spec["path_prefixes"],
                "router_exists": source_path.exists(),
                "endpoint_count": len(_contracts_for_prefixes(contract_index, spec["path_prefixes"])),
                "endpoints": _contracts_for_prefixes(contract_index, spec["path_prefixes"]),
            }
        )
    return inventory


def _build_router_markdown(
    *,
    title: str,
    inventory: list[dict[str, Any]],
    base_url: str,
    scope_note: str,
) -> str:
    lines = [
        f"# {title}",
        "",
        f"- Generated: `{_utc_now().isoformat()}`",
        f"- Backend: `{base_url}`",
        f"- Scope: {scope_note}",
        "",
    ]
    for router in inventory:
        lines.append(f"## {router['label']}")
        lines.append("")
        lines.append(f"- Router file: `{router['router_file']}`")
        lines.append(f"- Path prefixes: `{', '.join(router['path_prefixes'])}`")
        lines.append(f"- Router exists: `{'yes' if router['router_exists'] else 'no'}`")
        lines.append(f"- Endpoint count: `{router['endpoint_count']}`")
        lines.append("")
        for endpoint in router["endpoints"]:
            lines.append(f"- `{endpoint['method']} {endpoint['path']}`")
        lines.append("")
    return "\n".join(lines)


def _resolve_account_id(
    *,
    accounts_payload: Any,
    requested_account_id: str | None,
    requested_account_name: str | None,
) -> int:
    items = _extract_items(accounts_payload)
    if requested_account_id:
        wanted_id = int(requested_account_id)
        for item in items:
            if item.get("id") == wanted_id:
                return wanted_id
    if requested_account_name:
        wanted_name = requested_account_name.strip().lower()
        for item in items:
            name = str(item.get("name") or "").strip().lower()
            if name == wanted_name:
                return int(item["id"])
    if items:
        return int(items[0]["id"])
    return DEFAULT_ACCOUNT_ID


def _instantiate_path_template(
    path_template: str,
    *,
    account_id: int,
    sample_sku_id: int | None,
    sample_nm_id: int | None,
    sample_upload_id: int | None,
    sample_action_id: int | None,
) -> tuple[str, list[str]]:
    path = _normalize_contract_path(path_template)
    replacements = {
        "account_id": account_id,
        "sku_id": sample_sku_id,
        "nm_id": sample_nm_id,
        "upload_id": sample_upload_id,
        "action_id": sample_action_id,
    }
    missing: list[str] = []
    for key, value in replacements.items():
        token = "{" + key + "}"
        if token not in path:
            continue
        if value is None:
            missing.append(key)
            continue
        path = path.replace(token, str(value))
    return path, missing


def _build_default_query_params(
    *,
    contract: dict[str, Any],
    account_id: int,
    date_from: date,
    date_to: date,
    sample_issue_code: str | None,
) -> tuple[dict[str, Any], list[str]]:
    params: dict[str, Any] = {}
    missing_required: list[str] = []
    normalized_path = _normalize_contract_path(contract["path"])
    for parameter in contract.get("parameters") or []:
        if parameter.get("in") != "query":
            continue
        name = parameter.get("name")
        value: Any = None
        if name == "account_id":
            value = account_id
        elif name == "date_from":
            value = date_from.isoformat()
        elif name == "date_to":
            value = date_to.isoformat()
        elif name == "limit":
            value = 200
        elif name == "offset":
            value = 0
        elif name == "include_inactive":
            value = True
        elif name == "code" and normalized_path == "/dq/issues/investigator":
            value = sample_issue_code
        if value is not None:
            params[str(name)] = value
        elif parameter.get("required"):
            missing_required.append(str(name))
    return params, missing_required


def _is_binary_path(path: str) -> bool:
    normalized_path = _normalize_contract_path(path)
    return normalized_path.startswith("/export/") or normalized_path == "/costs/template"


def _build_all_full_list_endpoints(
    *,
    contract_index: list[dict[str, Any]],
    account_id: int,
    date_from: date,
    date_to: date,
    sample_issue_code: str | None,
) -> list[ExecutedEndpoint]:
    endpoints: list[ExecutedEndpoint] = []
    for contract in contract_index:
        if contract["method"] != "GET":
            continue
        param_names = {parameter.get("name") for parameter in contract.get("parameters") or []}
        if "limit" not in param_names or "offset" not in param_names:
            continue
        path, missing_path_params = _instantiate_path_template(
            contract["path"],
            account_id=account_id,
            sample_sku_id=None,
            sample_nm_id=None,
            sample_upload_id=None,
            sample_action_id=None,
        )
        if missing_path_params:
            continue
        params, missing_required_params = _build_default_query_params(
            contract=contract,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            sample_issue_code=sample_issue_code,
        )
        if missing_required_params:
            continue
        endpoints.append(
            ExecutedEndpoint(
                method="GET",
                path_template=_normalize_contract_path(contract["path"]),
                path=path,
                params=params,
                auth=_normalize_contract_path(contract["path"]) != "/health",
                binary=_is_binary_path(contract["path"]),
            )
        )
    return endpoints


def _build_all_full_single_endpoints(
    *,
    contract_index: list[dict[str, Any]],
    account_id: int,
    date_from: date,
    date_to: date,
    sample_sku_id: int | None,
    sample_nm_id: int | None,
    sample_upload_id: int | None,
    sample_action_id: int | None,
    sample_issue_code: str | None,
) -> list[ExecutedEndpoint]:
    endpoints: list[ExecutedEndpoint] = []
    for contract in contract_index:
        if contract["method"] != "GET":
            continue
        param_names = {parameter.get("name") for parameter in contract.get("parameters") or []}
        if "limit" in param_names and "offset" in param_names:
            continue
        path, missing_path_params = _instantiate_path_template(
            contract["path"],
            account_id=account_id,
            sample_sku_id=sample_sku_id,
            sample_nm_id=sample_nm_id,
            sample_upload_id=sample_upload_id,
            sample_action_id=sample_action_id,
        )
        if missing_path_params:
            continue
        params, missing_required_params = _build_default_query_params(
            contract=contract,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            sample_issue_code=sample_issue_code,
        )
        if missing_required_params:
            continue
        endpoints.append(
            ExecutedEndpoint(
                method="GET",
                path_template=_normalize_contract_path(contract["path"]),
                path=path,
                params=params or None,
                auth=_normalize_contract_path(contract["path"]) != "/health",
                binary=_is_binary_path(contract["path"]),
            )
        )
    return endpoints


def _build_finance_full_list_endpoints(
    *,
    account_id: int,
    date_from: date,
    date_to: date,
) -> list[ExecutedEndpoint]:
    common_window = {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    return [
        ExecutedEndpoint("GET", "/finance/reports", "/finance/reports", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/finance/report-rows", "/finance/report-rows", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/balance", "/balance", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/money/cards", "/money/cards", params={**common_window, "limit": 200, "offset": 0, "sort_by": "priority_score", "sort_dir": "desc"}),
        ExecutedEndpoint("GET", "/money/articles", "/money/articles", params={**common_window, "limit": 200, "offset": 0, "sort_by": "priority_score", "sort_dir": "desc"}),
        ExecutedEndpoint("GET", "/money/expenses/report-rows", "/money/expenses/report-rows", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/money/actions/today", "/money/actions/today", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/marts/sku-daily", "/marts/sku-daily", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/marts/stock-daily", "/marts/stock-daily", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/marts/finance-reconciliation", "/marts/finance-reconciliation", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/marts/account-expense-daily", "/marts/account-expense-daily", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/marts/reconciliation-daily", "/marts/reconciliation-daily", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/dashboard/sku-profitability", "/dashboard/sku-profitability", params={**common_window, "limit": 200, "offset": 0, "sort": "profit_desc"}),
        ExecutedEndpoint("GET", "/ads/efficiency", "/ads/efficiency", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/ads/campaigns", "/ads/campaigns", params={"account_id": account_id, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/ads/stats", "/ads/stats", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/analytics/funnel", "/analytics/funnel", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/analytics/regions", "/analytics/regions", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/costs/imports", "/costs/imports", params={"limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/costs/rows", "/costs/rows", params={"account_id": account_id, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/costs/unresolved", "/costs/unresolved", params={"account_id": account_id, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/actions", "/actions", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/alerts", "/alerts", params={"account_id": account_id, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/inventory/purchase-plan", "/inventory/purchase-plan", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/pricing/safety", "/pricing/safety", params={**common_window, "limit": 200, "offset": 0}),
        ExecutedEndpoint("GET", "/dq/issues", "/dq/issues", params={"account_id": account_id, "only_open": True, "limit": 200, "offset": 0}),
    ]


def _execute_full_list_capture(
    *,
    client: BackendClient,
    endpoint: ExecutedEndpoint,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    slug = _slugify(endpoint.path_template.strip("/").replace("/", "_") or "root")
    limit = int((endpoint.params or {}).get("limit") or 200)
    offset = int((endpoint.params or {}).get("offset") or 0)
    aggregated_items: list[Any] = []
    page_files: list[str] = []
    status_codes: list[int | None] = []
    total: int | None = None
    extra_payload: dict[str, Any] = {}
    error_text: str | None = None

    def fetch_page(page_offset: int, page_index: int) -> dict[str, Any]:
        page_params = dict(endpoint.params or {})
        page_params["limit"] = limit
        page_params["offset"] = page_offset
        last_response: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, CAPTURE_PAGE_RETRIES + 1):
            try:
                started_at = _utc_now()
                response = client.request(
                    endpoint.method,
                    endpoint.path,
                    params=page_params,
                    json_body=endpoint.json_body,
                    auth=endpoint.auth,
                )
                elapsed_ms = int((_utc_now() - started_at).total_seconds() * 1000)
                content_type = response.headers.get("content-type", "")
                if "application/json" in content_type:
                    body = _redact_sensitive(response.json())
                else:
                    body = {
                        "_meta": {
                            "binary": True,
                            "content_type": content_type,
                            "content_length": response.headers.get("content-length"),
                            "status_code": response.status_code,
                        }
                    }
                last_response = {
                    "page_index": page_index,
                    "params": page_params,
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "elapsed_ms": elapsed_ms,
                    "body": body,
                }
                if response.status_code < 500 or attempt == CAPTURE_PAGE_RETRIES:
                    return last_response
            except Exception as exc:
                last_error = exc
                if attempt == CAPTURE_PAGE_RETRIES:
                    raise
            time.sleep(min(0.25 * attempt, 1.0))
        if last_response is not None:
            return last_response
        raise RuntimeError(f"Failed to fetch page {page_index}") from last_error

    def write_page_result(page_result: dict[str, Any]) -> None:
        page_file = f"{slug}_page_{page_result['page_index']:03d}.json"
        _write_json(
            pages_dir / page_file,
            {
                "request": {
                    "method": endpoint.method,
                    "path_template": endpoint.path_template,
                    "path": endpoint.path,
                    "query": page_result["params"],
                },
                "response": {
                    "status_code": page_result["status_code"],
                    "content_type": page_result["content_type"],
                    "elapsed_ms": page_result["elapsed_ms"],
                    "body": page_result["body"],
                },
            },
        )
        page_files.append(f"pages/{page_file}")
        status_codes.append(page_result["status_code"])

    try:
        first_page = fetch_page(offset, 1)
        write_page_result(first_page)
        first_body = first_page["body"]

        if first_page["status_code"] != 200:
            extra_payload = first_body if isinstance(first_body, dict) else {"body": first_body}
        elif isinstance(first_body, list):
            aggregated_items.extend(first_body)
            total = len(first_body)
        elif isinstance(first_body, dict) and "items" in first_body:
            first_items = list(first_body.get("items") or [])
            aggregated_items.extend(first_items)
            total = int(first_body.get("total") or len(first_items))
            extra_payload = {key: value for key, value in first_body.items() if key != "items"}

            if first_items and total > len(first_items):
                remaining_page_specs: list[tuple[int, int]] = []
                next_offset = offset + len(first_items)
                next_page_index = 2
                while next_offset < total:
                    remaining_page_specs.append((next_page_index, next_offset))
                    next_page_index += 1
                    next_offset += limit

                remaining_results: dict[int, dict[str, Any]] = {}
                with ThreadPoolExecutor(max_workers=MAX_CAPTURE_WORKERS) as executor:
                    future_map = {
                        executor.submit(fetch_page, page_offset, page_index): (page_index, page_offset)
                        for page_index, page_offset in remaining_page_specs
                    }
                    for future in as_completed(future_map):
                        page_index, page_offset = future_map[future]
                        try:
                            remaining_results[page_index] = future.result()
                        except Exception as exc:
                            remaining_results[page_index] = {
                                "page_index": page_index,
                                "params": {
                                    **(endpoint.params or {}),
                                    "limit": limit,
                                    "offset": page_offset,
                                },
                                "status_code": None,
                                "content_type": None,
                                "elapsed_ms": None,
                                "body": {"error": repr(exc)},
                            }

                for page_index in sorted(remaining_results):
                    page_result = remaining_results[page_index]
                    write_page_result(page_result)
                    body = page_result["body"]
                    if page_result["status_code"] != 200:
                        error_text = error_text or f"page {page_index} status {page_result['status_code']}"
                        continue
                    if isinstance(body, dict) and "items" in body:
                        aggregated_items.extend(list(body.get("items") or []))
                    elif isinstance(body, list):
                        aggregated_items.extend(body)
                    else:
                        error_text = error_text or f"page {page_index} returned unexpected shape"
        else:
            extra_payload = first_body if isinstance(first_body, dict) else {"body": first_body}
    except Exception as exc:
        error_text = repr(exc)
        status_codes.append(None)

    aggregate_file = f"{slug}_all.json"
    aggregate_payload = {
        "request": {
            "method": endpoint.method,
            "path_template": endpoint.path_template,
            "path": endpoint.path,
            "base_query": endpoint.params,
        },
        "response": {
            "page_count": len(page_files),
            "status_codes": status_codes,
            "total": total if total is not None else len(aggregated_items),
            "collected_items": len(aggregated_items),
            "extra": extra_payload,
            "items": aggregated_items,
            "page_files": page_files,
            "error": error_text,
        },
    }
    _write_json(output_dir / aggregate_file, aggregate_payload)
    return {
        "path_template": endpoint.path_template,
        "path": endpoint.path,
        "method": endpoint.method,
        "query": endpoint.params,
        "page_count": len(page_files),
        "status_codes": status_codes,
        "total": total if total is not None else len(aggregated_items),
        "collected_items": len(aggregated_items),
        "aggregate_file": aggregate_file,
        "page_files": page_files,
        "error": error_text,
    }


def _build_data_source_markdown(*, base_url: str) -> str:
    lines = [
        "# Live Backend Data Source Audit",
        "",
        f"- Generated: `{_utc_now().date().isoformat()}`",
        f"- Backend: `{base_url}`",
        "- Scope: endpoint -> DB tables -> WB upstream API -> business meaning",
        "",
        "## High-Level Flow",
        "",
        "1. WB APIs are pulled into normalized PostgreSQL tables plus `raw_wb_api_responses`.",
        "2. `core_sku` resolves article identity across nmId/vendorCode/barcode/size.",
        "3. `mart_*` tables aggregate daily economics, stock, reconciliation, and expenses.",
        "4. `data_quality_issues` and sync state gate trust/business readiness.",
        "5. Control Tower and Dashboard endpoints read those marts/issues/settings to build operator views.",
        "",
        "## Endpoint Source Map",
        "",
    ]
    for item in DATA_SOURCE_MAP:
        lines.append(f"### {', '.join(item['path_prefixes'])}")
        lines.append("")
        lines.append(f"- Layer: `{item['layer']}`")
        lines.append(f"- DB tables: `{', '.join(item['db_tables'])}`")
        if item["upstream_wb_apis"]:
            lines.append(f"- WB upstream APIs: `{'; '.join(item['upstream_wb_apis'])}`")
        else:
            lines.append("- WB upstream APIs: `none / internal-only`")
        lines.append(f"- Notes: {item['notes']}")
        lines.append("")
    return "\n".join(lines)


def _build_endpoint_markdown(
    *,
    base_url: str,
    executed_results: list[dict[str, Any]],
    skipped_mutations: list[dict[str, Any]],
    bundle_dir: Path,
) -> str:
    lines = [
        "# Live Backend Endpoint Request Catalog",
        "",
        f"- Generated: `{_utc_now().isoformat()}`",
        f"- Backend: `{base_url}`",
        f"- Bundle: `{bundle_dir.name}`",
        "- Safe read endpoints and read-only simulation endpoints were executed live.",
        "- Write/mutating endpoints were not executed against the live account; their contracts were extracted from OpenAPI.",
        "",
        "## Live Executed Endpoints",
        "",
    ]
    for item in executed_results:
        lines.append(f"### {item['method']} {item['path_template']}")
        lines.append("")
        lines.append(f"- Executed live: `{'yes' if item['executed_live'] else 'no'}`")
        lines.append(f"- Status: `{item.get('status_code')}`")
        lines.append(f"- Content-Type: `{item.get('content_type')}`")
        if item.get("query_string"):
            lines.append(f"- Query: `{item['query_string']}`")
        if item.get("json_body") is not None:
            lines.append(f"- JSON body: `{json.dumps(item['json_body'], ensure_ascii=False)}`")
        lines.append(f"- Top-level shape: `{item.get('top_level_type')}`")
        if item.get("top_level_keys"):
            lines.append(f"- Top-level keys: `{', '.join(item['top_level_keys'])}`")
        if item.get("note"):
            lines.append(f"- Note: {item['note']}")
        lines.append(f"- Sample file: `exports/{bundle_dir.name}/responses/{item['response_file']}`")
        lines.append("")
    lines.extend(
        [
            "## Mutation Contracts Only",
            "",
        ]
    )
    for item in skipped_mutations:
        lines.append(f"### {item['method']} {item['path']}")
        lines.append("")
        lines.append("- Executed live: `no`")
        lines.append("- Reason: `mutation endpoint intentionally skipped on live data`")
        if item.get("request_body"):
            lines.append(f"- Request body schemas: `{', '.join(item['request_body'].get('schema_names') or [])}`")
        response_summaries = []
        for code, response in (item.get("responses") or {}).items():
            schema_names = ", ".join(response.get("schema_names") or []) or "none"
            response_summaries.append(f"{code}: {schema_names}")
        if response_summaries:
            lines.append(f"- Response schemas: `{'; '.join(response_summaries)}`")
        lines.append("")
    return "\n".join(lines)


def _build_readme_for_ai(
    *,
    bundle_slug: str,
    meta: dict[str, Any],
    executed_results: list[dict[str, Any]],
    skipped_mutations: list[dict[str, Any]],
) -> str:
    lines = [
        "# README FOR AI",
        "",
        "This bundle contains a live backend audit for AI analysis.",
        "",
        "## Read First",
        "",
        f"- Bundle: `{bundle_slug}`",
        f"- Generated at: `{meta['generated_at']}`",
        f"- Backend base URL: `{meta['base_url']}`",
        f"- Account ID: `{meta['account_id']}`",
        f"- Date window: `{meta['date_from']}` .. `{meta['date_to']}`",
        f"- Sample SKU ID: `{meta.get('sample_sku_id')}`",
        f"- Sample nmId: `{meta.get('sample_nm_id')}`",
        "",
        "## File Guide",
        "",
        "- `meta.json`: top-level bundle metadata and counts",
        "- `openapi.json`: live OpenAPI document fetched from the backend",
        "- `endpoint_contract_index.json`: contract index for every endpoint in OpenAPI",
        "- `executed_live_index.json`: every safe endpoint that was executed live",
        "- `skipped_mutation_contracts.json`: write endpoints intentionally not executed live",
        "- `endpoint_data_sources.json`: endpoint -> DB/source map",
        "- `router_inventory.json`: all router files with endpoint inventories",
        "- `full_list_captures_index.json`: full paginated captures for list/read endpoints",
        "- `router_sources/`: saved router source snapshots for all routers",
        "- `ai_business_dump.json`: consolidated business-oriented snapshot for quick AI ingestion",
        "- `responses/*.json`: per-endpoint request/response JSON files",
        "- `responses_full/*.json`: full non-truncated response payloads for executed endpoints",
        "",
        "## Execution Summary",
        "",
        f"- Live executed endpoints: `{len(executed_results)}`",
        f"- Mutation contracts only: `{len(skipped_mutations)}`",
        f"- Contract count: `{meta['contract_count']}`",
        "",
        "## Important Notes",
        "",
        "- Safe GET endpoints and read-only calculation endpoints were executed live.",
        "- Write/mutation endpoints were not executed against the live account; only their request/response contracts are included.",
        "- Credentials/tokens/passwords are redacted in saved JSON.",
        "- When a response was too large, the bundle stores a sampled/truncated JSON body and marks it in the response metadata.",
        "",
        "## Recommended AI Reading Order",
        "",
        "1. `README_FOR_AI.md`",
        "2. `meta.json`",
        "3. `ai_business_dump.json`",
        "4. `executed_live_index.json`",
        "5. `endpoint_contract_index.json`",
        "6. `endpoint_data_sources.json`",
        "7. any specific `responses/*.json` files needed for deeper analysis",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    now = _utc_now()
    bundle_slug = f"live_backend_full_audit_{_slug_timestamp(now)}"
    bundle_dir = EXPORTS_DIR / bundle_slug
    responses_dir = bundle_dir / "responses"
    responses_full_dir = bundle_dir / "responses_full"
    router_sources_dir = bundle_dir / "router_sources"
    full_list_captures_dir = bundle_dir / "full_list_captures"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    responses_full_dir.mkdir(parents=True, exist_ok=True)
    router_sources_dir.mkdir(parents=True, exist_ok=True)
    full_list_captures_dir.mkdir(parents=True, exist_ok=True)

    date_to = _parse_env_date(AUDIT_DATE_TO) or now.date()
    date_from = _parse_env_date(AUDIT_DATE_FROM) or (date_to - timedelta(days=30))
    audit_password = _required_env("BACKEND_AUDIT_PASSWORD")

    client = BackendClient(
        base_url=BASE_URL,
        email=AUDIT_EMAIL,
        password=audit_password,
    )

    login_payload = client.login()
    refresh_payload = client.refresh()
    openapi = client.fetch_openapi()
    contract_index = _build_contract_index(openapi)
    contract_lookup = {(item["method"], item["path"]): item for item in contract_index}
    router_inventory = _build_router_inventory(router_specs=ALL_ROUTER_SPECS, contract_index=contract_index)
    for router in ALL_ROUTER_SPECS:
        source_path = REPO_ROOT / router["router_file"]
        if source_path.exists():
            _write_text(router_sources_dir / router["router_file"], source_path.read_text(encoding="utf-8"))

    safe_results: list[dict[str, Any]] = []

    def execute(endpoint: ExecutedEndpoint) -> dict[str, Any]:
        started_at = _utc_now()
        query_string = urlencode({k: v for k, v in (endpoint.params or {}).items() if v is not None}, doseq=True)
        response_file = f"{endpoint.method.lower()}_{_slugify(endpoint.path_template.strip('/').replace('/', '_') or 'root')}.json"
        full_response_file = response_file
        try:
            response = client.request(
                endpoint.method,
                endpoint.path,
                params=endpoint.params,
                json_body=endpoint.json_body,
                auth=endpoint.auth,
            )
            elapsed_ms = int((_utc_now() - started_at).total_seconds() * 1000)
            content_type = response.headers.get("content-type", "")
            body_payload: Any

            if endpoint.binary or "application/json" not in content_type:
                body_payload = {
                    "_meta": {
                        "binary": True,
                        "content_type": content_type,
                        "content_length": response.headers.get("content-length"),
                        "status_code": response.status_code,
                        "sample_text_head": response.text[:300] if response.text else None,
                    }
                }
                sampled = body_payload
                truncated = False
                top_level_type = "binary"
                top_level_keys: list[str] = []
            else:
                try:
                    raw_json = _redact_sensitive(response.json())
                    sampled, truncated = _sample_response_body(raw_json)
                    body_payload = raw_json
                    top_level_type = type(raw_json).__name__
                    top_level_keys = list(raw_json.keys()) if isinstance(raw_json, dict) else []
                except Exception:
                    sampled = {"_raw_text_head": response.text[:1000]}
                    body_payload = sampled
                    truncated = True
                    top_level_type = "unparsed_json_text"
                    top_level_keys = []

            wrapped_payload = {
                "request": {
                    "method": endpoint.method,
                    "path_template": endpoint.path_template,
                    "path": endpoint.path,
                    "query": endpoint.params,
                    "json_body": _redact_sensitive(endpoint.json_body),
                },
                "response": {
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "elapsed_ms": elapsed_ms,
                    "truncated_for_bundle": truncated,
                    "top_level_type": top_level_type,
                    "top_level_keys": top_level_keys,
                    "shape": _shape_of(sampled),
                    "body": sampled,
                },
            }
            full_wrapped_payload = {
                "request": {
                    "method": endpoint.method,
                    "path_template": endpoint.path_template,
                    "path": endpoint.path,
                    "query": endpoint.params,
                    "json_body": _redact_sensitive(endpoint.json_body),
                },
                "response": {
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "elapsed_ms": elapsed_ms,
                    "truncated_for_bundle": False,
                    "top_level_type": top_level_type,
                    "top_level_keys": top_level_keys,
                    "shape": _shape_of(body_payload),
                    "body": body_payload,
                },
            }
            _write_json(responses_dir / response_file, wrapped_payload)
            _write_json(responses_full_dir / full_response_file, full_wrapped_payload)

            result = {
                "method": endpoint.method,
                "path_template": endpoint.path_template,
                "path": endpoint.path,
                "query": endpoint.params,
                "query_string": query_string,
                "json_body": _redact_sensitive(endpoint.json_body),
                "status_code": response.status_code,
                "content_type": content_type,
                "elapsed_ms": elapsed_ms,
                "executed_live": True,
                "response_file": response_file,
                "full_response_file": full_response_file,
                "truncated_for_bundle": truncated,
                "top_level_type": top_level_type,
                "top_level_keys": top_level_keys,
                "note": endpoint.note,
            }
            safe_results.append(result)
            return {"raw": body_payload, "meta": result}
        except Exception as exc:
            elapsed_ms = int((_utc_now() - started_at).total_seconds() * 1000)
            wrapped_payload = {
                "request": {
                    "method": endpoint.method,
                    "path_template": endpoint.path_template,
                    "path": endpoint.path,
                    "query": endpoint.params,
                    "json_body": _redact_sensitive(endpoint.json_body),
                },
                "response": {
                    "status_code": None,
                    "content_type": None,
                    "elapsed_ms": elapsed_ms,
                    "error": repr(exc),
                },
            }
            _write_json(responses_dir / response_file, wrapped_payload)
            _write_json(responses_full_dir / full_response_file, wrapped_payload)
            result = {
                "method": endpoint.method,
                "path_template": endpoint.path_template,
                "path": endpoint.path,
                "query": endpoint.params,
                "query_string": query_string,
                "json_body": _redact_sensitive(endpoint.json_body),
                "status_code": None,
                "content_type": None,
                "elapsed_ms": elapsed_ms,
                "executed_live": False,
                "response_file": response_file,
                "full_response_file": full_response_file,
                "truncated_for_bundle": False,
                "top_level_type": "error",
                "top_level_keys": [],
                "note": f"{endpoint.note or ''} error={repr(exc)}".strip(),
            }
            safe_results.append(result)
            return {"raw": {"error": repr(exc)}, "meta": result}

    health = execute(ExecutedEndpoint("GET", "/health", "/health", auth=False))["raw"]
    me = execute(ExecutedEndpoint("GET", "/auth/me", "/auth/me"))["raw"]
    ping = execute(ExecutedEndpoint("GET", "/auth/ping", "/auth/ping"))["raw"]
    execute(
        ExecutedEndpoint(
            "POST",
            "/auth/login",
            "/auth/login",
            auth=False,
            json_body={"email": DEFAULT_EMAIL, "password": audit_password},
            note="Safe auth endpoint executed live.",
        )
    )
    execute(
        ExecutedEndpoint(
            "POST",
            "/auth/refresh",
            "/auth/refresh",
            auth=False,
            json_body={"refresh_token": refresh_payload["refresh_token"]},
            note="Safe auth refresh endpoint executed live.",
        )
    )
    users = execute(ExecutedEndpoint("GET", "/users", "/users"))["raw"]
    meta_enums = execute(ExecutedEndpoint("GET", "/meta/enums", "/meta/enums"))["raw"]
    accounts = execute(
        ExecutedEndpoint("GET", "/accounts", "/accounts", params={"include_inactive": True, "limit": 200, "offset": 0})
    )["raw"]
    account_id = _resolve_account_id(
        accounts_payload=accounts,
        requested_account_id=AUDIT_ACCOUNT_ID,
        requested_account_name=AUDIT_ACCOUNT_NAME,
    )

    tokens = execute(
        ExecutedEndpoint("GET", "/accounts/{account_id}/tokens", f"/accounts/{account_id}/tokens")
    )["raw"]

    common_window = {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    dashboard_health = execute(
        ExecutedEndpoint("GET", "/dashboard/data-health", "/dashboard/data-health", params=common_window)
    )["raw"]
    owner_dashboard = execute(
        ExecutedEndpoint("GET", "/dashboard/owner", "/dashboard/owner", params=common_window)
    )["raw"]
    actions = execute(
        ExecutedEndpoint(
            "GET",
            "/actions",
            "/actions",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    sample_action_id: int | None = None
    action_items = _extract_items(actions)
    if action_items and action_items[0].get("id") is not None:
        sample_action_id = int(action_items[0]["id"])
    alerts = execute(
        ExecutedEndpoint(
            "GET",
            "/alerts",
            "/alerts",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    purchase_plan = execute(
        ExecutedEndpoint(
            "GET",
            "/inventory/purchase-plan",
            "/inventory/purchase-plan",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    price_safety = execute(
        ExecutedEndpoint(
            "GET",
            "/pricing/safety",
            "/pricing/safety",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    ads_efficiency = execute(
        ExecutedEndpoint(
            "GET",
            "/ads/efficiency",
            "/ads/efficiency",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    business_settings = execute(
        ExecutedEndpoint(
            "GET",
            "/settings/business",
            "/settings/business",
            params={"account_id": account_id},
        )
    )["raw"]
    business_policies = execute(
        ExecutedEndpoint(
            "GET",
            "/settings/business/policies",
            "/settings/business/policies",
            params={"account_id": account_id},
        )
    )["raw"]
    control_sku_statuses = execute(ExecutedEndpoint("GET", "/skus/statuses", "/skus/statuses"))["raw"]
    control_skus = execute(
        ExecutedEndpoint(
            "GET",
            "/skus",
            "/skus",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    core_skus = execute(
        ExecutedEndpoint(
            "GET",
            "/core-sku",
            "/core-sku",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    profitability = execute(
        ExecutedEndpoint(
            "GET",
            "/dashboard/sku-profitability",
            "/dashboard/sku-profitability",
            params={**common_window, "limit": 5, "offset": 0, "sort": "profit_desc"},
        )
    )["raw"]

    sample_sku_id: int | None = None
    sample_nm_id: int | None = None
    if isinstance(profitability, dict):
        for item in profitability.get("items") or []:
            if item.get("sku_id") is not None and item.get("nm_id") is not None:
                sample_sku_id = int(item["sku_id"])
                sample_nm_id = int(item["nm_id"])
                break
    if sample_sku_id is None and isinstance(control_skus, dict):
        first = next((item for item in control_skus.get("items") or [] if item.get("sku_id") is not None), None)
        if first:
            sample_sku_id = int(first["sku_id"])
            if first.get("nm_id") is not None:
                sample_nm_id = int(first["nm_id"])
    if sample_sku_id is None and isinstance(core_skus, dict):
        first = next((item for item in core_skus.get("items") or [] if item.get("id") is not None), None)
        if first:
            sample_sku_id = int(first["id"])
            if first.get("nm_id") is not None:
                sample_nm_id = int(first["nm_id"])

    control_sku_detail = None
    core_sku_detail = None
    article_audit = None
    if sample_sku_id is not None:
        control_sku_detail = execute(
            ExecutedEndpoint(
                "GET",
                "/skus/{sku_id}",
                f"/skus/{sample_sku_id}",
                params=common_window,
            )
        )["raw"]
        core_sku_detail = execute(
            ExecutedEndpoint(
                "GET",
                "/core-sku/{sku_id}",
                f"/core-sku/{sample_sku_id}",
                params={"date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
            )
        )["raw"]
    if sample_nm_id is not None:
        article_audit = execute(
            ExecutedEndpoint(
                "GET",
                "/dashboard/article-audit",
                "/dashboard/article-audit",
                params={**common_window, "nm_id": sample_nm_id},
            )
        )["raw"]

    money_summary = execute(
        ExecutedEndpoint("GET", "/money/summary", "/money/summary", params=common_window)
    )["raw"]
    money_cards = execute(
        ExecutedEndpoint(
            "GET",
            "/money/cards",
            "/money/cards",
            params={**common_window, "limit": 5, "offset": 0, "sort_by": "priority_score", "sort_dir": "desc"},
        )
    )["raw"]
    money_articles = execute(
        ExecutedEndpoint(
            "GET",
            "/money/articles",
            "/money/articles",
            params={**common_window, "limit": 5, "offset": 0, "sort_by": "priority_score", "sort_dir": "desc"},
        )
    )["raw"]
    money_actions_today = execute(
        ExecutedEndpoint(
            "GET",
            "/money/actions/today",
            "/money/actions/today",
            params={**common_window, "limit": 10, "offset": 0},
        )
    )["raw"]
    money_data_blockers = execute(
        ExecutedEndpoint(
            "GET",
            "/money/data-blockers",
            "/money/data-blockers",
            params=common_window,
        )
    )["raw"]
    money_filters = execute(
        ExecutedEndpoint(
            "GET",
            "/money/filters",
            "/money/filters",
            params={"account_id": account_id},
        )
    )["raw"]
    money_expense_breakdown = execute(
        ExecutedEndpoint(
            "GET",
            "/money/expenses/breakdown",
            "/money/expenses/breakdown",
            params={**common_window, "group_by": "category", "include_unallocated": True},
        )
    )["raw"]
    money_expense_logistics = execute(
        ExecutedEndpoint(
            "GET",
            "/money/expenses/logistics",
            "/money/expenses/logistics",
            params={**common_window, "include_unallocated": True},
        )
    )["raw"]
    money_expense_report_rows = execute(
        ExecutedEndpoint(
            "GET",
            "/money/expenses/report-rows",
            "/money/expenses/report-rows",
            params={**common_window, "limit": 10, "offset": 0},
        )
    )["raw"]
    money_card_detail = None
    money_article_detail = None
    if sample_sku_id is not None:
        money_card_detail = execute(
            ExecutedEndpoint(
                "GET",
                "/money/cards/{sku_id}",
                f"/money/cards/{sample_sku_id}",
                params=common_window,
            )
        )["raw"]
    if sample_nm_id is not None:
        money_article_detail = execute(
            ExecutedEndpoint(
                "GET",
                "/money/articles/{nm_id}",
                f"/money/articles/{sample_nm_id}",
                params=common_window,
            )
        )["raw"]

    dq_issues = execute(
        ExecutedEndpoint(
            "GET",
            "/dq/issues",
            "/dq/issues",
            params={
                "account_id": account_id,
                "only_open": True,
                "limit": 10,
                "offset": 0,
            },
        )
    )["raw"]
    sample_issue_code: str | None = None
    if isinstance(dq_issues, dict):
        first_issue = next((item for item in dq_issues.get("items") or [] if item.get("code")), None)
        if first_issue:
            sample_issue_code = str(first_issue["code"])
    dq_investigator = None
    if sample_issue_code is not None:
        dq_investigator = execute(
            ExecutedEndpoint(
                "GET",
                "/dq/issues/investigator",
                "/dq/issues/investigator",
                params={"account_id": account_id, "code": sample_issue_code, "limit": 10, "offset": 0},
            )
        )["raw"]
    dq_summary = execute(
        ExecutedEndpoint(
            "GET",
            "/dq/issues/summary",
            "/dq/issues/summary",
            params={"account_id": account_id},
        )
    )["raw"]

    documents = execute(
        ExecutedEndpoint(
            "GET",
            "/documents",
            "/documents",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    balance = execute(
        ExecutedEndpoint(
            "GET",
            "/balance",
            "/balance",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    finance_reports = execute(
        ExecutedEndpoint(
            "GET",
            "/finance/reports",
            "/finance/reports",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    finance_report_rows = execute(
        ExecutedEndpoint(
            "GET",
            "/finance/report-rows",
            "/finance/report-rows",
            params={**common_window, "limit": 10, "offset": 0},
        )
    )["raw"]

    costs_imports = execute(ExecutedEndpoint("GET", "/costs/imports", "/costs/imports"))["raw"]
    costs_rows = execute(
        ExecutedEndpoint(
            "GET",
            "/costs/rows",
            "/costs/rows",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    execute(
        ExecutedEndpoint(
            "GET",
            "/costs/template",
            "/costs/template",
            params={"account_id": account_id},
            binary=True,
        )
    )
    costs_unresolved = execute(
        ExecutedEndpoint(
            "GET",
            "/costs/unresolved",
            "/costs/unresolved",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    sample_upload_id: int | None = None
    if isinstance(costs_imports, list) and costs_imports:
        if costs_imports[0].get("id") is not None:
            sample_upload_id = int(costs_imports[0]["id"])
    elif isinstance(costs_imports, dict):
        items = costs_imports.get("items") or []
        first_item = next((item for item in items if isinstance(item, dict) and item.get("id") is not None), None)
        if first_item is not None:
            sample_upload_id = int(first_item["id"])
    costs_upload_preview = None
    if sample_upload_id is not None:
        costs_upload_preview = execute(
            ExecutedEndpoint(
                "GET",
                "/costs/uploads/{upload_id}/preview",
                f"/costs/uploads/{sample_upload_id}/preview",
            )
        )["raw"]

    mart_account_expense = execute(
        ExecutedEndpoint(
            "GET",
            "/marts/account-expense-daily",
            "/marts/account-expense-daily",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    mart_finance_reconciliation = execute(
        ExecutedEndpoint(
            "GET",
            "/marts/finance-reconciliation",
            "/marts/finance-reconciliation",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    mart_reconciliation_daily = execute(
        ExecutedEndpoint(
            "GET",
            "/marts/reconciliation-daily",
            "/marts/reconciliation-daily",
            params={**common_window, "sku_id": sample_sku_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    mart_sku_daily = execute(
        ExecutedEndpoint(
            "GET",
            "/marts/sku-daily",
            "/marts/sku-daily",
            params={**common_window, "nm_id": sample_nm_id, "limit": 10, "offset": 0},
        )
    )["raw"]
    mart_stock_daily = execute(
        ExecutedEndpoint(
            "GET",
            "/marts/stock-daily",
            "/marts/stock-daily",
            params={**common_window, "sku_id": sample_sku_id, "limit": 10, "offset": 0},
        )
    )["raw"]

    orders = execute(
        ExecutedEndpoint(
            "GET",
            "/orders",
            "/orders",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    prices = execute(
        ExecutedEndpoint(
            "GET",
            "/prices",
            "/prices",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    products = execute(
        ExecutedEndpoint(
            "GET",
            "/products",
            "/products",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    sales = execute(
        ExecutedEndpoint(
            "GET",
            "/sales",
            "/sales",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    stocks = execute(
        ExecutedEndpoint(
            "GET",
            "/stocks/snapshots",
            "/stocks/snapshots",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    supplies = execute(
        ExecutedEndpoint(
            "GET",
            "/supplies",
            "/supplies",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    sync_cursors = execute(
        ExecutedEndpoint(
            "GET",
            "/sync/cursors",
            "/sync/cursors",
            params={"account_id": account_id, "limit": 10, "offset": 0},
        )
    )["raw"]
    sync_runs = execute(
        ExecutedEndpoint(
            "GET",
            "/sync/runs",
            "/sync/runs",
            params={"account_id": account_id, "limit": 10, "offset": 0},
        )
    )["raw"]
    tariffs = execute(
        ExecutedEndpoint(
            "GET",
            "/tariffs",
            "/tariffs",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    ads_campaigns = execute(
        ExecutedEndpoint(
            "GET",
            "/ads/campaigns",
            "/ads/campaigns",
            params={"account_id": account_id, "limit": 5, "offset": 0},
        )
    )["raw"]
    ads_stats = execute(
        ExecutedEndpoint(
            "GET",
            "/ads/stats",
            "/ads/stats",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    analytics_funnel = execute(
        ExecutedEndpoint(
            "GET",
            "/analytics/funnel",
            "/analytics/funnel",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]
    analytics_regions = execute(
        ExecutedEndpoint(
            "GET",
            "/analytics/regions",
            "/analytics/regions",
            params={**common_window, "limit": 5, "offset": 0},
        )
    )["raw"]

    current_price_for_sim = None
    if isinstance(price_safety, dict):
        first = next((item for item in price_safety.get("items") or [] if item.get("current_price") not in (None, 0, "0", "0.0")), None)
        if first is not None:
            current_price_for_sim = first.get("current_price")
    if current_price_for_sim is None:
        current_price_for_sim = 1000
    pricing_simulation = execute(
        ExecutedEndpoint(
            "POST",
            "/pricing/simulate",
            "/pricing/simulate",
            json_body={
                "account_id": account_id,
                "sku_id": sample_sku_id,
                "nm_id": sample_nm_id,
                "price": current_price_for_sim,
                "sales_drop_assumption_percent": 0,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
            note="Read-only calculation endpoint executed live.",
        )
    )["raw"]

    export_paths = [
        "/export/data-quality.xlsx",
        "/export/missing-costs.xlsx",
        "/export/profit-by-sku.xlsx",
        "/export/reconciliation.xlsx",
        "/export/stock.xlsx",
    ]
    for export_path in export_paths:
        execute(
            ExecutedEndpoint(
                "GET",
                export_path,
                export_path,
                params={"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                binary=True,
            )
        )

    executed_pairs = {(item["method"], item["path_template"]) for item in safe_results}
    for endpoint in _build_all_full_single_endpoints(
        contract_index=contract_index,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        sample_sku_id=sample_sku_id,
        sample_nm_id=sample_nm_id,
        sample_upload_id=sample_upload_id,
        sample_action_id=sample_action_id,
        sample_issue_code=sample_issue_code,
    ):
        if (endpoint.method, endpoint.path_template) in executed_pairs:
            continue
        execute(endpoint)
        executed_pairs.add((endpoint.method, endpoint.path_template))

    full_list_capture_results = [
        _execute_full_list_capture(
            client=client,
            endpoint=endpoint,
            output_dir=full_list_captures_dir,
        )
        for endpoint in _build_all_full_list_endpoints(
            contract_index=contract_index,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            sample_issue_code=sample_issue_code,
        )
    ]

    executed_pairs = {(item["method"], item["path_template"]) for item in safe_results}
    skipped_mutations = [
        item
        for item in contract_index
        if item["method"] not in {"GET"}
        and (item["method"], _normalize_contract_path(item["path"])) not in executed_pairs
        and not (
            item["method"] == "POST"
            and _normalize_contract_path(item["path"]) in {"/auth/login", "/auth/refresh", "/pricing/simulate"}
        )
    ]

    data_source_index = []
    for item in contract_index:
        source = _data_source_for(item["path"])
        data_source_index.append(
            {
                "method": item["method"],
                "path": item["path"],
                "summary": item["summary"],
                "operation_id": item["operation_id"],
                "data_source": source,
            }
        )

    ai_business_dump = {
        "meta": {
            "generated_at": now.isoformat(),
            "base_url": BASE_URL,
            "account_id": account_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "sample_sku_id": sample_sku_id,
            "sample_nm_id": sample_nm_id,
            "user_id": me.get("id") if isinstance(me, dict) else None,
        },
        "health": health,
        "auth": {"me": me, "ping": ping},
        "meta_enums": meta_enums,
        "dashboard_data_health": dashboard_health,
        "owner_dashboard": owner_dashboard,
        "money_summary": money_summary,
        "money_cards": money_cards,
        "money_articles": money_articles,
        "money_card_detail": money_card_detail,
        "money_article_detail": money_article_detail,
        "money_actions_today": money_actions_today,
        "money_data_blockers": money_data_blockers,
        "money_filters": money_filters,
        "money_expense_breakdown": money_expense_breakdown,
        "money_expense_logistics": money_expense_logistics,
        "money_expense_report_rows": money_expense_report_rows,
        "actions_sample": actions,
        "alerts_sample": alerts,
        "purchase_plan_sample": purchase_plan,
        "price_safety_sample": price_safety,
        "pricing_simulation_sample": pricing_simulation,
        "ads_efficiency_sample": ads_efficiency,
        "business_settings": business_settings,
        "business_policies": business_policies,
        "control_sku_statuses": control_sku_statuses,
        "control_skus_sample": control_skus,
        "control_sku_detail_sample": control_sku_detail,
        "core_skus_sample": core_skus,
        "core_sku_detail_sample": core_sku_detail,
        "article_audit_sample": article_audit,
        "profitability_sample": profitability,
        "dq_issues_sample": dq_issues,
        "dq_summary_sample": dq_summary,
        "dq_investigator_sample": dq_investigator,
        "finance_reports_sample": finance_reports,
        "finance_report_rows_sample": finance_report_rows,
        "balance_sample": balance,
        "documents_sample": documents,
        "orders_sample": orders,
        "sales_sample": sales,
        "products_sample": products,
        "prices_sample": prices,
        "stocks_sample": stocks,
        "supplies_sample": supplies,
        "analytics_funnel_sample": analytics_funnel,
        "analytics_regions_sample": analytics_regions,
        "ads_campaigns_sample": ads_campaigns,
        "ads_stats_sample": ads_stats,
        "marts_account_expense_sample": mart_account_expense,
        "marts_finance_reconciliation_sample": mart_finance_reconciliation,
        "marts_reconciliation_daily_sample": mart_reconciliation_daily,
        "marts_sku_daily_sample": mart_sku_daily,
        "marts_stock_daily_sample": mart_stock_daily,
        "manual_cost_imports_sample": costs_imports,
        "manual_cost_rows_sample": costs_rows,
        "manual_cost_unresolved_sample": costs_unresolved,
        "manual_cost_upload_preview_sample": costs_upload_preview,
        "sync_cursors_sample": _sample_json(sync_cursors),
        "sync_runs_sample": _sample_json(sync_runs),
        "tariffs_sample": tariffs,
        "users_sample": users,
        "accounts_sample": accounts,
        "account_tokens_sample": tokens,
    }

    meta = {
        "generated_at": now.isoformat(),
        "bundle_slug": bundle_slug,
        "base_url": BASE_URL,
        "account_id": account_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "sample_sku_id": sample_sku_id,
        "sample_nm_id": sample_nm_id,
        "openapi_path_count": len(openapi.get("paths") or {}),
        "contract_count": len(contract_index),
        "router_count": len(router_inventory),
        "full_list_capture_count": len(full_list_capture_results),
        "executed_live_count": len(safe_results),
        "skipped_mutation_count": len(skipped_mutations),
        "login_token_shape": {
            "token_type": login_payload.get("token_type"),
            "has_access_token": bool(login_payload.get("access_token")),
            "has_refresh_token": bool(login_payload.get("refresh_token")),
        },
    }

    _write_json(bundle_dir / "meta.json", meta)
    _write_json(bundle_dir / "openapi.json", openapi)
    _write_json(bundle_dir / "endpoint_contract_index.json", contract_index)
    _write_json(bundle_dir / "executed_live_index.json", safe_results)
    _write_json(bundle_dir / "skipped_mutation_contracts.json", skipped_mutations)
    _write_json(bundle_dir / "data_source_map.json", DATA_SOURCE_MAP)
    _write_json(bundle_dir / "endpoint_data_sources.json", data_source_index)
    _write_json(bundle_dir / "router_inventory.json", router_inventory)
    _write_json(bundle_dir / "full_list_captures_index.json", full_list_capture_results)
    _write_json(bundle_dir / "ai_business_dump.json", ai_business_dump)
    _write_text(
        bundle_dir / "README_FOR_AI.md",
        _build_readme_for_ai(
            bundle_slug=bundle_slug,
            meta=meta,
            executed_results=safe_results,
            skipped_mutations=skipped_mutations,
        ),
    )

    data_source_doc = DOCS_DIR / f"live_backend_data_source_audit_{date_to.isoformat()}.md"
    endpoint_doc = DOCS_DIR / f"live_backend_endpoint_request_catalog_{date_to.isoformat()}.md"
    router_doc = DOCS_DIR / f"router_audit_{date_to.isoformat()}.md"
    _write_text(data_source_doc, _build_data_source_markdown(base_url=BASE_URL))
    _write_text(
        endpoint_doc,
        _build_endpoint_markdown(
            base_url=BASE_URL,
            executed_results=safe_results,
            skipped_mutations=skipped_mutations,
            bundle_dir=bundle_dir,
        ),
    )
    _write_text(
        router_doc,
        _build_router_markdown(
            title="Router Audit",
            inventory=router_inventory,
            base_url=BASE_URL,
            scope_note="all router files, their paths, and saved live/full-list captures.",
        ),
    )
    zip_path = Path(shutil.make_archive(str(bundle_dir), "zip", root_dir=bundle_dir.parent, base_dir=bundle_dir.name))

    print(
        json.dumps(
            {
                "bundle_dir": str(bundle_dir),
                "zip_path": str(zip_path),
                "meta_file": str(bundle_dir / "meta.json"),
                "readme_file": str(bundle_dir / "README_FOR_AI.md"),
                "business_dump": str(bundle_dir / "ai_business_dump.json"),
                "data_source_doc": str(data_source_doc),
                "endpoint_doc": str(endpoint_doc),
                "router_doc": str(router_doc),
                "router_inventory": str(bundle_dir / "router_inventory.json"),
                "full_list_captures_index": str(bundle_dir / "full_list_captures_index.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
