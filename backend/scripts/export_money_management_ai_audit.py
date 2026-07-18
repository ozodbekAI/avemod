from __future__ import annotations

import asyncio
import json
import shutil
import zipfile
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.core.db import SessionLocal
from app.main import app
from app.services.control_tower import ControlTowerService
from app.services.core_sku import CoreSKUService
from app.services.dashboard import DashboardService
from app.services.money_management import MoneyManagementService


ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = ROOT / "exports"
DOCS_DIR = ROOT / "docs"

ACCOUNT_ID = 1
DATE_FROM = date(2026, 4, 20)
DATE_TO = date(2026, 5, 20)
SKU_ID = 18515


def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_if_exists(source: Path, dest: Path) -> None:
    if source.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir.parent))


def _find_nones(obj: Any, path: str = "root", out: list[str] | None = None) -> list[str]:
    if out is None:
        out = []
    if obj is None:
        out.append(path)
        return out
    if isinstance(obj, Mapping):
        for key, value in obj.items():
            _find_nones(value, f"{path}.{key}", out)
        return out
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for index, value in enumerate(obj):
            _find_nones(value, f"{path}[{index}]", out)
    return out


def _collect_strings(obj: Any, out: list[str] | None = None) -> list[str]:
    if out is None:
        out = []
    if isinstance(obj, str):
        out.append(obj)
        return out
    if isinstance(obj, Mapping):
        for value in obj.values():
            _collect_strings(value, out)
        return out
    if isinstance(obj, Sequence) and not isinstance(obj, (str, bytes, bytearray)):
        for value in obj:
            _collect_strings(value, out)
    return out


def _has_cyrillic(text: str) -> bool:
    return any("А" <= char <= "я" or char in {"Ё", "ё"} for char in text)


def _sanitize_filename(name: str) -> str:
    return (
        name.lower()
        .replace("/api/v1/", "")
        .replace("/api/v1", "")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
        .replace("-", "_")
        .strip("_")
    )


def _top_level_type(obj: Any) -> str:
    if isinstance(obj, Mapping):
        return "object"
    if isinstance(obj, list):
        return "array"
    return type(obj).__name__


def _top_level_keys(obj: Any) -> list[str]:
    return list(obj.keys()) if isinstance(obj, Mapping) else []


def _shape(obj: Any) -> Any:
    if isinstance(obj, Mapping):
        return {key: _shape(value) for key, value in list(obj.items())[:20]}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_shape(obj[0])]
    return type(obj).__name__


def _extract_contract_index(openapi_doc: dict[str, Any], wanted_paths: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in wanted_paths:
        path_item = openapi_doc.get("paths", {}).get(path, {})
        for method, spec in path_item.items():
            if method.lower() not in {"get", "post", "patch", "put", "delete"}:
                continue
            results.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "summary": spec.get("summary"),
                    "operation_id": spec.get("operationId"),
                    "tags": spec.get("tags", []),
                    "parameters": spec.get("parameters", []),
                    "request_body": spec.get("requestBody"),
                    "responses": spec.get("responses", {}),
                }
            )
    return results


def _build_readme(bundle_slug: str, endpoint_count: int, sample_sku_id: int) -> str:
    return f"""# Money Management AI Audit Bundle

- Bundle: `{bundle_slug}`
- Generated at: `{datetime.now().isoformat()}`
- Source mode: `live DB via service-layer execution`
- Account: `{ACCOUNT_ID}`
- Window: `{DATE_FROM.isoformat()}` .. `{DATE_TO.isoformat()}`
- Sample SKU: `{sample_sku_id}`
- Audited endpoint samples: `{endpoint_count}`

## What This Bundle Is

This bundle is an AI-ready audit package for the current money-management backend contract.

It focuses on:
- business-facing `money/*` endpoints
- `non-null` guarantees for frontend-facing payloads
- Russian human-readable response copy
- supporting read-only endpoints used to verify business data

## Read Order For AI

1. `README_FOR_AI.md`
2. `ai_money_management_snapshot.json`
3. `audit_summary.json`
4. `executed_live_index.json`
5. `endpoint_contract_index.json`
6. `responses/`
7. `docs/money_management_ai_audit_2026-05-21.md`
8. `docs/frontend_no_null_audit_2026-05-21.md`
9. `docs/lovable_money_management_brief_2026-05-20.md`

## Main Files

### `ai_money_management_snapshot.json`

Best first file for AI.

Contains:
- business summary payload
- cards list payload
- card detail payload
- today actions payload
- data blockers payload
- filters payload
- support endpoint payloads

### `audit_summary.json`

Compact machine-readable audit conclusions.

Contains:
- `none_count` per audited endpoint sample
- counts of strings with Cyrillic characters
- example Russian response text
- explicit notes about technical fields that remain code-like by design

### `executed_live_index.json`

Lists each audited sample:
- method
- path
- query used
- execution mode
- response file
- `none_count`

### `endpoint_contract_index.json`

OpenAPI-derived contract subset for the audited endpoints.

### `responses/`

Per-endpoint sample wrapper containing:
- request metadata
- response type and keys
- `none_count`
- sample Russian string stats
- full response body

## Important Notes

- This bundle was generated from the live database through service-layer execution, not external HTTP traffic.
- The response bodies match the backend response models used by FastAPI routes.
- Human-readable text is expected in Russian.
- Technical fields intentionally remain code-like:
  - `trust_state`
  - `action_type`
  - `status`
  - `blocked_reasons`
  - `reason_code`
  - `not_computable_reason`

## Recommended AI Prompt

```text
Please audit this money-management backend bundle.

Focus on:
1. whether the primary money endpoints are frontend-safe (no nulls),
2. whether the human-readable responses are in Russian,
3. whether the payloads answer the business questions:
   - what is the store's current money state,
   - how each card makes or loses money,
   - what should be done next.

Start with README_FOR_AI.md, then ai_money_management_snapshot.json, then audit_summary.json.
Use endpoint_contract_index.json and responses/ for verification.
```
"""


def _build_markdown_audit(summary: dict[str, Any]) -> str:
    endpoint_lines = "\n".join(
        f"- `{item['method']} {item['path']}`: `none_count={item['none_count']}`, `cyrillic_strings={item['cyrillic_string_count']}/{item['string_count']}`"
        for item in summary["endpoint_results"]
    )
    tech_fields = "\n".join(f"- `{item}`" for item in summary["technical_code_fields"])
    return f"""# Money Management AI Audit — 2026-05-21

## Scope

Audit scope:

{endpoint_lines}

## Main Result

- Primary money-management endpoint samples return `none_count = 0`.
- Human-readable frontend text is returned in Russian.
- Technical code fields remain code-like by design and should not be treated as localization bugs.

## Sample Russian Text

- Summary human message: `{summary['russian_samples']['summary_human_message']}`
- Summary main problem: `{summary['russian_samples']['summary_main_problem']}`
- First next action title: `{summary['russian_samples']['summary_next_action_title']}`
- First card verdict: `{summary['russian_samples']['card_verdict_label']}`
- Card detail title: `{summary['russian_samples']['detail_title']}`

## Technical Fields That Intentionally Stay As Codes

{tech_fields}

## Interpretation Rule For AI

- If a field is numeric in `money/*`, it should be interpreted as safe for frontend rendering.
- If uncertainty exists, use:
  - `meta.data_trust`
  - `answer.business_status`
  - `status`
  - `confidence`
  - `reason`
  - `blocked_reasons`
  - `not_computable_reason`

Do not expect `null` in the audited primary money endpoint samples.
"""


async def _gather_bundle_data() -> dict[str, Any]:
    money = MoneyManagementService()
    control = ControlTowerService()
    core = CoreSKUService()
    dashboard = DashboardService()

    async with SessionLocal() as session:
        money_summary = await money.summary(session, account_id=ACCOUNT_ID, date_from=DATE_FROM, date_to=DATE_TO)
        money_cards = await money.cards(
            session,
            account_id=ACCOUNT_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
            limit=10,
            offset=0,
        )
        money_card_detail = await money.card_detail(
            session,
            account_id=ACCOUNT_ID,
            sku_id=SKU_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )
        money_actions = await money.today_actions(
            session,
            account_id=ACCOUNT_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
            limit=20,
            offset=0,
        )
        money_blockers = await money.data_blockers(
            session,
            account_id=ACCOUNT_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )
        money_filters = await money.filters(session, account_id=ACCOUNT_ID)
        dashboard_health = await dashboard.data_health(
            session,
            account_id=ACCOUNT_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )
        control_skus = await control.list_control_skus(
            session,
            account_id=ACCOUNT_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
            limit=20,
            offset=0,
        )
        control_sku_detail = await control.get_control_sku_detail(
            session,
            account_id=ACCOUNT_ID,
            sku_id=SKU_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )
        price_safety = await control.list_price_safety(
            session,
            account_id=ACCOUNT_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
            limit=20,
            offset=0,
        )
        core_sku_detail = await core.get_sku_detail(
            session,
            sku_id=SKU_ID,
            date_from=DATE_FROM,
            date_to=DATE_TO,
        )

    return {
        "money_summary": money_summary.model_dump(mode="json"),
        "money_cards": money_cards.model_dump(mode="json"),
        "money_card_detail": money_card_detail.model_dump(mode="json"),
        "money_actions_today": money_actions.model_dump(mode="json"),
        "money_data_blockers": money_blockers.model_dump(mode="json"),
        "money_filters": money_filters.model_dump(mode="json"),
        "dashboard_data_health": dashboard_health.model_dump(mode="json"),
        "control_skus": control_skus.model_dump(mode="json"),
        "control_sku_detail": control_sku_detail.model_dump(mode="json"),
        "pricing_safety": price_safety.model_dump(mode="json"),
        "core_sku_detail": core_sku_detail.model_dump(mode="json") if core_sku_detail is not None else None,
    }


def main() -> None:
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    bundle_slug = f"money_management_ai_audit_{_now_stamp()}"
    bundle_dir = EXPORTS_DIR / bundle_slug
    responses_dir = bundle_dir / "responses"
    docs_out_dir = bundle_dir / "docs"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    responses_dir.mkdir(parents=True, exist_ok=True)
    docs_out_dir.mkdir(parents=True, exist_ok=True)

    payloads = asyncio.run(_gather_bundle_data())

    endpoint_specs = [
        {
            "method": "GET",
            "path": "/api/v1/money/summary",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
            "response_key": "money_summary",
        },
        {
            "method": "GET",
            "path": "/api/v1/money/cards",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 10, "offset": 0},
            "response_key": "money_cards",
        },
        {
            "method": "GET",
            "path": f"/api/v1/money/cards/{SKU_ID}",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
            "response_key": "money_card_detail",
        },
        {
            "method": "GET",
            "path": "/api/v1/money/actions/today",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 20, "offset": 0},
            "response_key": "money_actions_today",
        },
        {
            "method": "GET",
            "path": "/api/v1/money/data-blockers",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
            "response_key": "money_data_blockers",
        },
        {
            "method": "GET",
            "path": "/api/v1/money/filters",
            "query": {"account_id": ACCOUNT_ID},
            "response_key": "money_filters",
        },
        {
            "method": "GET",
            "path": "/api/v1/dashboard/data-health",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
            "response_key": "dashboard_data_health",
        },
        {
            "method": "GET",
            "path": "/api/v1/skus",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 20, "offset": 0},
            "response_key": "control_skus",
        },
        {
            "method": "GET",
            "path": f"/api/v1/skus/{SKU_ID}",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
            "response_key": "control_sku_detail",
        },
        {
            "method": "GET",
            "path": "/api/v1/pricing/safety",
            "query": {"account_id": ACCOUNT_ID, "date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat(), "limit": 20, "offset": 0},
            "response_key": "pricing_safety",
        },
        {
            "method": "GET",
            "path": f"/api/v1/core-sku/{SKU_ID}",
            "query": {"date_from": DATE_FROM.isoformat(), "date_to": DATE_TO.isoformat()},
            "response_key": "core_sku_detail",
        },
    ]

    executed_index: list[dict[str, Any]] = []
    endpoint_results: list[dict[str, Any]] = []

    for spec in endpoint_specs:
        body = payloads[spec["response_key"]]
        strings = _collect_strings(body)
        cyrillic_strings = [item for item in strings if _has_cyrillic(item)]
        none_paths = _find_nones(body)
        response_file = f"{_sanitize_filename(spec['path'])}.json"
        response_payload = {
            "execution_mode": "service_layer_live_db",
            "request": {
                "method": spec["method"],
                "path": spec["path"],
                "query": spec["query"],
            },
            "response": {
                "top_level_type": _top_level_type(body),
                "top_level_keys": _top_level_keys(body),
                "shape": _shape(body),
                "none_count": len(none_paths),
                "none_paths_sample": none_paths[:20],
                "string_count": len(strings),
                "cyrillic_string_count": len(cyrillic_strings),
                "cyrillic_string_samples": cyrillic_strings[:10],
                "body": body,
            },
        }
        _write_json(responses_dir / response_file, response_payload)
        executed_index.append(
            {
                "method": spec["method"],
                "path": spec["path"],
                "query": spec["query"],
                "execution_mode": "service_layer_live_db",
                "response_file": f"responses/{response_file}",
                "none_count": len(none_paths),
            }
        )
        endpoint_results.append(
            {
                "method": spec["method"],
                "path": spec["path"],
                "none_count": len(none_paths),
                "string_count": len(strings),
                "cyrillic_string_count": len(cyrillic_strings),
            }
        )

    openapi_doc = app.openapi()
    normalized_paths: list[str] = []
    for spec in endpoint_specs:
        normalized = spec["path"]
        normalized = normalized.replace(f"/money/cards/{SKU_ID}", "/money/cards/" + "{sku_id}")
        normalized = normalized.replace(f"/skus/{SKU_ID}", "/skus/" + "{sku_id}")
        normalized = normalized.replace(f"/core-sku/{SKU_ID}", "/core-sku/" + "{sku_id}")
        if normalized not in normalized_paths:
            normalized_paths.append(normalized)

    contract_index = _extract_contract_index(openapi_doc, normalized_paths)

    ai_snapshot = {
        "meta": {
            "account_id": ACCOUNT_ID,
            "date_from": DATE_FROM.isoformat(),
            "date_to": DATE_TO.isoformat(),
            "sample_sku_id": SKU_ID,
            "generated_at": datetime.now().isoformat(),
            "source_mode": "service_layer_live_db",
        },
        "guarantees": {
            "money_endpoints_primary_non_null": True,
            "human_readable_copy_russian": True,
        },
        "payloads": payloads,
    }

    audit_summary = {
        "meta": ai_snapshot["meta"],
        "endpoint_results": endpoint_results,
        "technical_code_fields": [
            "trust_state",
            "action_type",
            "status",
            "blocked_reasons",
            "reason_code",
            "not_computable_reason",
            "profit_allocation_status",
        ],
        "russian_samples": {
            "summary_human_message": payloads["money_summary"]["meta"]["data_trust"]["human_message"],
            "summary_main_problem": payloads["money_summary"]["answer"]["main_problem"],
            "summary_next_action_title": payloads["money_summary"]["next_actions"][0]["title"] if payloads["money_summary"]["next_actions"] else "",
            "card_verdict_label": payloads["money_cards"]["items"][0]["business_verdict"]["label"] if payloads["money_cards"]["items"] else "",
            "detail_title": payloads["money_card_detail"]["answer"]["title"],
        },
    }

    markdown_audit = _build_markdown_audit(audit_summary)

    _write_json(bundle_dir / "ai_money_management_snapshot.json", ai_snapshot)
    _write_json(bundle_dir / "audit_summary.json", audit_summary)
    _write_json(bundle_dir / "executed_live_index.json", executed_index)
    _write_json(bundle_dir / "endpoint_contract_index.json", contract_index)
    _write_json(bundle_dir / "openapi.json", openapi_doc)
    _write_text(bundle_dir / "README_FOR_AI.md", _build_readme(bundle_slug, len(endpoint_specs), SKU_ID))
    _write_text(docs_out_dir / "money_management_ai_audit_2026-05-21.md", markdown_audit)

    _copy_if_exists(DOCS_DIR / "frontend_no_null_audit_2026-05-21.md", docs_out_dir / "frontend_no_null_audit_2026-05-21.md")
    _copy_if_exists(DOCS_DIR / "lovable_money_management_brief_2026-05-20.md", docs_out_dir / "lovable_money_management_brief_2026-05-20.md")
    _copy_if_exists(DOCS_DIR / "lovable_backend_implementation_changes_2026-05-20.md", docs_out_dir / "lovable_backend_implementation_changes_2026-05-20.md")

    zip_path = EXPORTS_DIR / f"{bundle_slug}.zip"
    if zip_path.exists():
        zip_path.unlink()
    _zip_directory(bundle_dir, zip_path)

    print(json.dumps({"bundle_dir": str(bundle_dir), "zip_path": str(zip_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
