from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import urlopen


DEFAULT_OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"
DEFAULT_OUTPUT_PATH = Path("docs/backend_api_lovable_handoff_2026-05-18.md")
DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"

PROJECT_SUMMARY = """WB Data Core is a read-only Wildberries data platform for one or more seller cabinets.

Its core purpose is to turn fragmented WB operational and financial data into a business-ready model:

`товар → заказ → продажа/возврат → финансовый отчёт → расходы → прибыль → остаток`.

The backend does four things:
1. Collects source data from WB APIs into normalized PostgreSQL tables and raw audit logs.
2. Resolves product identity into a stable `core_sku` model.
3. Builds business marts for daily SKU economics, stock history, and reconciliation.
4. Exposes internal admin APIs for sync control, QA, profitability analysis, and frontend consumption.

Important constraints:
- The platform is read-only towards WB on this stage.
- Operational orders/sales are used for fast monitoring.
- Financial truth comes from finance/report data.
- Manual cost is an external business input and can be missing.
"""

ARCHITECTURE_SUMMARY = """## High-Level Data Flow

1. **WB Sync Layer**
   - Pulls product cards, prices, orders, sales, stocks, finance, ads, analytics, supplies, tariffs, documents.
   - Stores raw responses for auditability.
   - Writes normalized domain tables with idempotent upserts and cursor tracking.

2. **Business Identity Layer**
   - Resolves SKU identity in `core_sku`.
   - Links `nmId`, `vendorCode`, `barcode`, `size`, `chrtId`, and manual cost.

3. **Business Mart Layer**
   - `mart_sku_daily`
   - `mart_stock_daily`
   - `mart_finance_reconciliation`
   - `mart_reconciliation_daily`
   - `mart_account_expense_daily`

4. **Data Quality Layer**
   - Stores open/resolved issues in `data_quality_issues`.
   - Flags missing cost, unmatched SKU, sale/finance mismatch, dead stock, ad spend without sales, etc.

5. **Internal Admin API Layer**
   - Used by Swagger, the internal Next.js frontend, and external builders like Lovable.
"""

COMMON_RULES = """## Common API Rules

- Base URL: `{base_url}`
- Auth: `Authorization: Bearer <access_token>` for almost all endpoints.
- Date format: `YYYY-MM-DD`
- DateTime format: ISO 8601 UTC unless otherwise stated
- Pagination style:
  - query: `limit`, `offset`
  - response: `{{ total, limit, offset, items }}`
- Numeric money fields are returned as JSON numbers or numeric strings depending on schema serialization.
- All endpoints are internal/admin APIs, not public storefront APIs.

## Auth Flow

1. `POST /auth/login`
   - request: email + password
   - response: access token + refresh token
2. `POST /auth/refresh`
   - request: refresh token
   - response: new access token + refresh token
3. Pass the access token in `Authorization: Bearer ...`
"""

LOVABLE_MAPPING = """## Recommended Screen-to-API Mapping for Lovable

### 1. Data Health Screen
- `GET /dashboard/data-health`
- `GET /sync/runs`
- `GET /dq/issues`

### 2. SKU Directory Screen
- `GET /core-sku`

### 3. SKU Detail Screen
- `GET /core-sku/{sku_id}`
- `GET /dashboard/article-audit`
- `GET /marts/sku-daily`
- `GET /marts/reconciliation-daily`
- `GET /dq/issues`

### 4. Profitability Screen
- `GET /dashboard/sku-profitability`

### 5. Discrepancies Screen
- `GET /marts/reconciliation-daily`
- `GET /dq/issues`
- `GET /dq/issues/investigator`

### 6. Owner Dashboard Screen
- `GET /dashboard/owner`

### 7. SKU Control Center Screen
- `GET /skus`
- `GET /skus/{sku_id}`

### 8. Action Center Screen
- `GET /actions`
- `PATCH /actions/{action_id}`

### 9. Inventory / Purchase Plan Screen
- `GET /inventory/purchase-plan`

### 10. Price Safety Screen
- `GET /pricing/safety`
- `POST /pricing/simulate`

### 11. Ads Efficiency Screen
- `GET /ads/efficiency`

### 12. Settings / Alerts Screens
- `GET /settings/business`
- `PATCH /settings/business`
- `GET /alerts`
- `PATCH /alerts/{alert_id}`

### 13. Admin / Setup Screens
- `GET /accounts`
- `POST /accounts`
- `GET /accounts/{account_id}/tokens`
- `POST /accounts/{account_id}/tokens`
- `GET /costs/imports`
- `GET /costs/rows`
- `GET /costs/template`
- `POST /costs/upload`
- `POST /sync/trigger`
- `POST /sync/backfill`
- `POST /marts/refresh`
- `POST /dq/run`
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--openapi-url", default=DEFAULT_OPENAPI_URL)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--generated-on", default=str(date.today()))
    return parser.parse_args()


def load_openapi(openapi_url: str) -> dict[str, Any]:
    try:
        with urlopen(openapi_url) as response:  # noqa: S310 - local trusted backend
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        from app.main import app

        return app.openapi()


def ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def schema_title(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return ref_name(schema["$ref"])
    if "title" in schema:
        return str(schema["title"])
    if schema.get("type") == "array":
        return f"array[{schema_title(schema.get('items', {}))}]"
    return schema.get("type", "object")


def format_type(schema: dict[str, Any]) -> str:
    if "$ref" in schema:
        return ref_name(schema["$ref"])
    if "anyOf" in schema:
        return " | ".join(format_type(item) for item in schema["anyOf"])
    if "allOf" in schema:
        return " & ".join(format_type(item) for item in schema["allOf"])
    if schema.get("type") == "array":
        return f"array[{format_type(schema.get('items', {}))}]"
    if "enum" in schema:
        return "enum(" + ", ".join(map(str, schema["enum"])) + ")"
    result = schema.get("type", "object")
    fmt = schema.get("format")
    if fmt:
        result = f"{result} ({fmt})"
    return result


def resolve_schema(schema: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    if "$ref" in schema:
        return resolve_schema(components[ref_name(schema["$ref"])], components)
    if "allOf" in schema:
        merged: dict[str, Any] = {"type": "object", "properties": {}, "required": []}
        for item in schema["allOf"]:
            resolved = resolve_schema(item, components)
            merged["properties"].update(resolved.get("properties", {}))
            merged["required"].extend(resolved.get("required", []))
        merged["required"] = sorted(set(merged["required"]))
        return merged
    return schema


def example_for_schema(schema: dict[str, Any], components: dict[str, Any], depth: int = 0) -> Any:
    if depth > 3:
        return "..."
    if "$ref" in schema:
        return example_for_schema(components[ref_name(schema["$ref"])], components, depth + 1)
    if "example" in schema:
        return schema["example"]
    if "default" in schema:
        return schema["default"]
    if "anyOf" in schema:
        non_null = [item for item in schema["anyOf"] if item.get("type") != "null"]
        return example_for_schema(non_null[0] if non_null else schema["anyOf"][0], components, depth + 1)
    schema_type = schema.get("type")
    schema_format = schema.get("format")
    if schema.get("enum"):
        return schema["enum"][0]
    if schema_type == "string":
        if schema_format == "date":
            return "2026-05-18"
        if schema_format == "date-time":
            return "2026-05-18T12:00:00Z"
        return "string"
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0
    if schema_type == "boolean":
        return False
    if schema_type == "array":
        return [example_for_schema(schema.get("items", {}), components, depth + 1)]
    properties = schema.get("properties", {})
    if properties:
        return {
            key: example_for_schema(value, components, depth + 1)
            for key, value in properties.items()
        }
    return {}


def render_param_table(params: list[dict[str, Any]]) -> str:
    if not params:
        return "_No path/query parameters._\n"
    lines = [
        "| Name | In | Required | Type | Default |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in params:
        schema = item.get("schema", {})
        default = schema.get("default", "")
        lines.append(
            f"| `{item['name']}` | `{item.get('in', '')}` | `{item.get('required', False)}` | `{format_type(schema)}` | `{default}` |"
        )
    return "\n".join(lines) + "\n"


def render_schema_fields(name: str, schema: dict[str, Any], components: dict[str, Any]) -> str:
    resolved = resolve_schema(schema, components)
    properties = resolved.get("properties", {})
    required = set(resolved.get("required", []))
    if not properties:
        return f"_`{name}` has no object fields in OpenAPI (scalar, array, or opaque response)._"
    lines = [
        f"**Schema:** `{name}`",
        "",
        "| Field | Type | Required |",
        "| --- | --- | --- |",
    ]
    for field_name, field_schema in properties.items():
        lines.append(
            f"| `{field_name}` | `{format_type(field_schema)}` | `{'yes' if field_name in required else 'no'}` |"
        )
    return "\n".join(lines)


def render_request_body(spec: dict[str, Any], components: dict[str, Any]) -> str:
    request_body = spec.get("requestBody")
    if not request_body:
        return "_No request body._\n"
    content = request_body.get("content", {})
    lines: list[str] = []
    for media_type, media in content.items():
        schema = media.get("schema", {})
        name = schema_title(schema)
        lines.append(f"- Content-Type: `{media_type}`")
        lines.append("")
        lines.append(render_schema_fields(name, schema, components))
        lines.append("")
        example = example_for_schema(schema, components)
        if media_type == "multipart/form-data":
            lines.append("**Body Example**")
            lines.append("")
            lines.append("```text")
            lines.append(json.dumps(example, ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append("**Body Example**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(example, ensure_ascii=False, indent=2))
            lines.append("```")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def success_response_entries(spec: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    result: list[tuple[str, str, dict[str, Any]]] = []
    for code, response in sorted(spec.get("responses", {}).items()):
        if not str(code).startswith("2"):
            continue
        content = response.get("content", {})
        if not content:
            result.append((str(code), "no-content", {}))
            continue
        for media_type, media in content.items():
            result.append((str(code), media_type, media.get("schema", {})))
    return result


def render_response_section(spec: dict[str, Any], components: dict[str, Any], path: str) -> str:
    lines: list[str] = []
    for code, media_type, schema in success_response_entries(spec):
        lines.append(f"### Success Response `{code}`")
        if path == "/api/v1/costs/template":
            lines.append("- Returns a downloadable file response (template CSV/XLSX depending on implementation).")
            lines.append("- Use the browser or file-download client flow, not JSON parsing.")
            lines.append("")
            continue
        if media_type != "no-content":
            lines.append(f"- Content-Type: `{media_type}`")
        name = schema_title(schema) if schema else "no-content"
        if schema:
            lines.append("")
            lines.append(render_schema_fields(name, schema, components))
            lines.append("")
            lines.append("**Response Example**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(example_for_schema(schema, components), ensure_ascii=False, indent=2))
            lines.append("```")
        else:
            lines.append("- No structured response body.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_schema_catalog(names: list[str], components: dict[str, Any]) -> str:
    lines = ["# Schema Catalog", ""]
    for name in sorted(set(names)):
        schema = components.get(name)
        if not schema:
            continue
        lines.append(f"## `{name}`")
        lines.append("")
        lines.append(render_schema_fields(name, schema, components))
        lines.append("")
        lines.append("**Example**")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(example_for_schema(schema, components), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    openapi = load_openapi(args.openapi_url)
    info = openapi["info"]
    components = openapi.get("components", {}).get("schemas", {})

    tag_groups: dict[str, list[tuple[str, str, dict[str, Any]]]] = defaultdict(list)
    referenced_schemas: set[str] = set()

    for path, methods in sorted(openapi["paths"].items()):
        for method, spec in sorted(methods.items()):
            tags = spec.get("tags") or ["misc"]
            tag_groups[tags[0]].append((path, method.upper(), spec))

            for param in spec.get("parameters", []):
                schema = param.get("schema", {})
                if "$ref" in schema:
                    referenced_schemas.add(ref_name(schema["$ref"]))
            request_body = spec.get("requestBody", {})
            for media in request_body.get("content", {}).values():
                schema = media.get("schema", {})
                if "$ref" in schema:
                    referenced_schemas.add(ref_name(schema["$ref"]))
            for _, _, schema in success_response_entries(spec):
                if "$ref" in schema:
                    referenced_schemas.add(ref_name(schema["$ref"]))

    lines: list[str] = []
    lines.append(f"# {info['title']} — Backend API Handoff for Lovable")
    lines.append("")
    lines.append(f"- Generated from current backend OpenAPI on `{args.generated_on}`")
    lines.append(f"- Version: `{info.get('version', 'unknown')}`")
    lines.append(f"- OpenAPI: `{openapi.get('openapi', 'unknown')}`")
    lines.append("")
    lines.append("## Project Goal")
    lines.append("")
    lines.append(PROJECT_SUMMARY)
    lines.append("")
    lines.append(ARCHITECTURE_SUMMARY)
    lines.append("")
    lines.append(COMMON_RULES.format(base_url=args.base_url))
    lines.append("")
    lines.append(LOVABLE_MAPPING)
    lines.append("")
    lines.append("## Endpoint Index")
    lines.append("")
    for tag in sorted(tag_groups):
        lines.append(f"- [{tag}](#{tag.replace('_', '-').replace(' ', '-')})")
    lines.append("")

    for tag in sorted(tag_groups):
        lines.append(f"# {tag}")
        lines.append("")
        for path, method, spec in tag_groups[tag]:
            auth_required = "yes" if spec.get("security") else "no"
            lines.append(f"## `{method} {path}`")
            lines.append("")
            lines.append(f"- Summary: `{spec.get('summary', '')}`")
            lines.append(f"- Operation ID: `{spec.get('operationId', '')}`")
            lines.append(f"- Auth required: `{auth_required}`")
            lines.append("")
            lines.append("### Parameters")
            lines.append("")
            lines.append(render_param_table(spec.get("parameters", [])))
            lines.append("### Request Body")
            lines.append("")
            lines.append(render_request_body(spec, components))
            lines.append("### Responses")
            lines.append("")
            lines.append(render_response_section(spec, components, path))
        lines.append("")

    lines.append(render_schema_catalog(sorted(referenced_schemas), components))
    args.output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"written {args.output}")


if __name__ == "__main__":
    main()
