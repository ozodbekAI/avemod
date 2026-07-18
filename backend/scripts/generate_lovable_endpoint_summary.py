from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import urlopen


DEFAULT_OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"
DEFAULT_OUTPUT_PATH = Path("docs/lovable_backend_endpoint_summary_2026-05-18.md")
DEFAULT_FULL_DOC_PATH = "docs/backend_api_lovable_handoff_2026-05-18.md"
DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi-url", default=DEFAULT_OPENAPI_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--full-doc-path", default=DEFAULT_FULL_DOC_PATH)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--generated-on", default=str(date.today()))
    return parser.parse_args()


def load_openapi(openapi_url: str) -> dict[str, Any]:
    try:
        with urlopen(openapi_url) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        from app.main import app

        return app.openapi()


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def schema_name(schema: dict[str, Any]) -> str:
    if not schema:
        return "none"
    if "$ref" in schema:
        return ref_name(schema["$ref"])
    if schema.get("type") == "array":
        return f"array[{schema_name(schema.get('items', {}))}]"
    if "title" in schema:
        return str(schema["title"])
    return schema.get("type", "object")


def first_success_response(spec: dict[str, Any]) -> tuple[str, str]:
    for code, response in sorted(spec.get("responses", {}).items()):
        if not str(code).startswith("2"):
            continue
        content = response.get("content", {})
        if not content:
            return str(code), "none"
        for media in content.values():
            return str(code), schema_name(media.get("schema", {}))
    return "unknown", "unknown"


def param_line(params: list[dict[str, Any]]) -> str:
    if not params:
        return "- Query/Path: none"
    parts: list[str] = []
    for item in params:
        location = item.get("in", "query")
        required = "required" if item.get("required", False) else "optional"
        parts.append(f"`{item['name']}` ({location}, {required})")
    return "- Query/Path: " + ", ".join(parts)


def body_line(spec: dict[str, Any]) -> str:
    request_body = spec.get("requestBody")
    if not request_body:
        return "- Body: none"
    content = request_body.get("content", {})
    if not content:
        return "- Body: yes"
    media_type, media = next(iter(content.items()))
    return f"- Body: `{media_type}` → `{schema_name(media.get('schema', {}))}`"


def auth_line(spec: dict[str, Any]) -> str:
    return "- Auth: Bearer token required" if spec.get("security") else "- Auth: public"


def project_intro(full_doc_path: str, base_url: str, generated_on: str) -> str:
    return f"""# Lovable Backend Endpoint Summary

- Generated from current backend OpenAPI on `{generated_on}`

This file is a frontend-oriented backend handoff for Lovable.

Use this document when you need a clean explanation of:
- what each endpoint is for
- what request it expects
- what response it returns

If Lovable needs full field-level schemas, also send:
- `{full_doc_path}`

## Product Goal

WB Data Core is an internal admin backend for Wildberries seller analytics.

Main business flow:
`товар → заказ → продажа/возврат → финансовый отчёт → расходы → прибыль → остаток`

The frontend is not a public storefront. It is an internal operator dashboard for:
- sync health
- SKU directory
- SKU detail
- profitability
- discrepancies / reconciliation

## Base Rules

- Base URL: `{base_url}`
- Auth style: `Authorization: Bearer <access_token>`
- Dates: `YYYY-MM-DD`
- Pagination shape:
  - request: `limit`, `offset`
  - response: `{{ total, limit, offset, items }}`
"""


def screen_mapping() -> str:
    return """## Screen Mapping

### 1. Login
- `POST /auth/login`
- `POST /auth/refresh`
- `GET /auth/me`

### 2. Data Health
- `GET /dashboard/data-health`
- `GET /sync/runs`
- `GET /dq/issues`

### 3. SKU Directory
- `GET /core-sku`

### 4. SKU Detail
- `GET /core-sku/{sku_id}`
- `GET /dashboard/article-audit`
- `GET /marts/sku-daily`
- `GET /marts/reconciliation-daily`
- `GET /dq/issues`

### 5. Profitability
- `GET /dashboard/sku-profitability`

### 6. Discrepancies
- `GET /marts/reconciliation-daily`
- `GET /dq/issues`
- `GET /dq/issues/investigator`

### 7. Owner Dashboard
- `GET /dashboard/owner`

### 8. SKU Control Center
- `GET /skus`
- `GET /skus/{sku_id}`

### 9. Action Center
- `GET /actions`
- `PATCH /actions/{action_id}`

### 10. Inventory & Purchase Planning
- `GET /inventory/purchase-plan`

### 11. Price Safety
- `GET /pricing/safety`
- `POST /pricing/simulate`

### 12. Ads Efficiency
- `GET /ads/efficiency`

### 13. Settings & Alerts
- `GET /settings/business`
- `PATCH /settings/business`
- `GET /alerts`
- `PATCH /alerts/{alert_id}`

### 14. Operator Tools
- `POST /sync/trigger`
- `POST /sync/backfill`
- `POST /marts/refresh`
- `POST /dq/run`
- cost upload / confirm / relink
- export endpoints
"""


def main() -> None:
    args = parse_args()
    openapi = load_openapi(args.openapi_url)
    grouped: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)

    for path, methods in sorted(openapi["paths"].items()):
        for method, spec in sorted(methods.items()):
            tag = (spec.get("tags") or ["misc"])[0]
            grouped[tag].append((method.upper(), path, spec))

    lines: list[str] = []
    lines.append(project_intro(args.full_doc_path, args.base_url, args.generated_on))
    lines.append("")
    lines.append(screen_mapping())
    lines.append("")
    lines.append("## Endpoint Groups")
    lines.append("")

    for tag in sorted(grouped):
        lines.append(f"### {tag}")
        lines.append("")
        for method, path, spec in grouped[tag]:
            code, response_schema = first_success_response(spec)
            lines.append(f"#### `{method} {path}`")
            lines.append(f"- Purpose: {spec.get('summary', 'No summary')}")
            lines.append(auth_line(spec))
            lines.append(param_line(spec.get("parameters", [])))
            lines.append(body_line(spec))
            lines.append(f"- Response: `{code}` → `{response_schema}`")
            lines.append("")

    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"written {args.output}")


if __name__ == "__main__":
    main()
