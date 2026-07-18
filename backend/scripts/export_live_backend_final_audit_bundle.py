#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.core.security import create_access_token


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = REPO_ROOT / "audit-bundle-final"
DEFAULT_LOCAL_API_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_ACCOUNT_ID = 1
DEFAULT_HTTP_TIMEOUT = httpx.Timeout(120.0, connect=15.0)
MAX_ERROR_TEXT_CHARS = 2000
MAX_SUMMARY_FIELDS = 60
SMALL_EXPORT_BYTES = 250_000

SOURCE_INCLUDE_PATHS = [
    "app",
    "alembic",
    "tests",
    "scripts",
    "docs",
    "pyproject.toml",
    "alembic.ini",
    "README.md",
    ".env.example",
]

SOURCE_EXCLUDE_DIR_NAMES = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "node_modules",
}
SOURCE_EXCLUDE_FILE_SUFFIXES = {".pyc", ".har", ".log"}

TABLES_TO_COUNT = [
    "core_sku",
    "manual_costs",
    "wb_product_cards",
    "wb_prices",
    "wb_orders",
    "wb_sales",
    "wb_stock_snapshot_rows",
    "wb_realization_report_rows",
    "wb_ad_campaigns",
    "wb_ad_stats_daily",
    "wb_ad_cluster_stats",
    "wb_card_funnel_daily",
    "wb_region_sales_daily",
    "mart_sku_daily",
    "mart_stock_daily",
    "mart_finance_reconciliation",
    "mart_reconciliation_daily",
    "mart_account_expense_daily",
    "raw_wb_api_responses",
    "data_quality_issues",
    "wb_sync_runs",
]

MART_TABLES = [
    "mart_sku_daily",
    "mart_stock_daily",
    "mart_finance_reconciliation",
    "mart_reconciliation_daily",
    "mart_account_expense_daily",
]

OPENAPI_RELATED_GROUPS = {
    "dashboard": ["/dashboard/"],
    "money": ["/money/"],
    "core-sku": ["/core-sku"],
    "pricing": ["/pricing/"],
    "dq": ["/dq/"],
    "actions": ["/actions"],
    "marts": ["/marts/"],
    "costs": ["/costs/"],
    "exports": ["/export/"],
    "auth": ["/auth/", "/users"],
}


@dataclass(frozen=True)
class CommandSpec:
    requested: str
    actual: list[str]
    output_file: str
    timeout_seconds: int = 1800
    stdout_to_file: bool = False


@dataclass(frozen=True)
class EndpointSpec:
    key: str
    method: str
    path: str
    params: dict[str, Any]
    sample_file: str | None = None
    binary: bool = False


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
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


def _now_local() -> datetime:
    return datetime.now().astimezone()


def _timestamp_slug(now: datetime) -> str:
    return now.strftime("%Y%m%d_%H%M%S")


def _safe_filename(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "root"


def _short_error_text(text_value: str | None) -> str | None:
    if not text_value:
        return None
    text_value = text_value.strip()
    if len(text_value) <= MAX_ERROR_TEXT_CHARS:
        return text_value
    return text_value[:MAX_ERROR_TEXT_CHARS] + "...<truncated>"


def _pick_python_bin() -> Path:
    preferred = REPO_ROOT / ".venv" / "bin" / "python"
    if preferred.exists():
        return preferred
    for candidate in ("python", "python3"):
        resolved = shutil.which(candidate)
        if resolved:
            return Path(resolved)
    raise FileNotFoundError("No python interpreter found")


def _normalize_base_url(candidate: str | None) -> str:
    if not candidate:
        return DEFAULT_LOCAL_API_BASE_URL
    return candidate.rstrip("/")


def _root_openapi_urls(base_url: str) -> list[str]:
    if base_url.endswith("/api/v1"):
        root_url = base_url[: -len("/api/v1")]
        return [f"{root_url}/openapi.json", f"{base_url}/openapi.json"]
    return [f"{base_url}/openapi.json"]


def _is_local_api_reachable(base_url: str) -> bool:
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0), follow_redirects=True) as client:
            for url in _root_openapi_urls(base_url):
                response = client.get(url)
                if response.status_code == 200:
                    return True
    except Exception:
        return False
    return False


def _load_runtime_settings() -> Any:
    return get_settings()


def _resolve_database_url(settings: Any) -> str:
    return str(os.getenv("DATABASE_URL") or settings.sync_database_url)


def _sanitize_source_text(rel_path: str, content: str) -> str:
    sanitized = content
    sanitized = re.sub(
        r"(?im)^([A-Z0-9_]*PASSWORD[A-Z0-9_]*\s*=\s*)[\"'][^\"']+[\"']",
        r'\1"<redacted>"',
        sanitized,
    )
    if rel_path == ".env.example":
        sanitized = re.sub(
            r"^(JWT_SECRET_KEY=).*$",
            r"\1replace-with-strong-access-secret",
            sanitized,
            flags=re.MULTILINE,
        )
        sanitized = re.sub(
            r"^(JWT_REFRESH_SECRET_KEY=).*$",
            r"\1replace-with-strong-refresh-secret",
            sanitized,
            flags=re.MULTILINE,
        )
        sanitized = re.sub(
            r"^(WB_TOKEN_ENCRYPTION_KEY=).*$",
            r"\1replace-with-generated-fernet-key",
            sanitized,
            flags=re.MULTILINE,
        )
    return sanitized


def _should_exclude_source_path(path: Path, rel_path: Path) -> bool:
    if any(part in SOURCE_EXCLUDE_DIR_NAMES for part in rel_path.parts):
        return True
    if any(part.startswith("audit-bundle") or part.startswith("live_backend_full_audit") for part in rel_path.parts):
        return True
    if path.suffix in SOURCE_EXCLUDE_FILE_SUFFIXES:
        return True
    if path.name.endswith(".egg-info"):
        return True
    return False


def _create_backend_source_zip(output_path: Path) -> dict[str, Any]:
    files_added = 0
    dirs_seen: set[str] = set()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for include in SOURCE_INCLUDE_PATHS:
            source = REPO_ROOT / include
            if not source.exists():
                continue
            if source.is_dir():
                for path in sorted(source.rglob("*")):
                    rel_path = path.relative_to(REPO_ROOT)
                    if _should_exclude_source_path(path, rel_path):
                        continue
                    if path.is_dir():
                        dirs_seen.add(str(rel_path))
                        continue
                    data: bytes
                    try:
                        text_value = path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        data = path.read_bytes()
                    else:
                        data = _sanitize_source_text(str(rel_path), text_value).encode("utf-8")
                    archive.writestr(str(rel_path), data)
                    files_added += 1
            else:
                rel_path = source.relative_to(REPO_ROOT)
                if _should_exclude_source_path(source, rel_path):
                    continue
                try:
                    text_value = source.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    archive.write(source, arcname=str(rel_path))
                else:
                    archive.writestr(str(rel_path), _sanitize_source_text(str(rel_path), text_value))
                files_added += 1
    return {"path": str(output_path), "files_added": files_added, "directories_seen": sorted(dirs_seen)}


def _run_command(spec: CommandSpec, reports_dir: Path) -> dict[str, Any]:
    started = time.perf_counter()
    output_path = reports_dir / spec.output_file
    try:
        process = subprocess.run(
            spec.actual,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout = process.stdout or ""
        stderr = process.stderr or ""
        if spec.stdout_to_file:
            output_path.write_text(stdout, encoding="utf-8")
        else:
            parts = [
                f"requested_command: {spec.requested}",
                f"actual_command: {' '.join(spec.actual)}",
                f"returncode: {process.returncode}",
                f"duration_ms: {duration_ms}",
                "",
                "stdout:",
                stdout.rstrip(),
                "",
                "stderr:",
                stderr.rstrip(),
            ]
            output_path.write_text("\n".join(parts).rstrip() + "\n", encoding="utf-8")
        return {
            "requested_command": spec.requested,
            "actual_command": " ".join(spec.actual),
            "returncode": process.returncode,
            "duration_ms": duration_ms,
            "ok": process.returncode == 0,
            "stdout": stdout,
            "stderr": stderr,
            "output_file": str(output_path),
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        output_path.write_text(
            "\n".join(
                [
                    f"requested_command: {spec.requested}",
                    f"actual_command: {' '.join(spec.actual)}",
                    "returncode: timeout",
                    f"duration_ms: {duration_ms}",
                    "",
                    "stdout:",
                    stdout.rstrip(),
                    "",
                    "stderr:",
                    stderr.rstrip(),
                ]
            ).rstrip()
            + "\n",
            encoding="utf-8",
        )
        return {
            "requested_command": spec.requested,
            "actual_command": " ".join(spec.actual),
            "returncode": None,
            "duration_ms": duration_ms,
            "ok": False,
            "timed_out": True,
            "stdout": stdout,
            "stderr": stderr,
            "output_file": str(output_path),
        }


def _build_commands_log(results: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for result in results:
        lines.extend(
            [
                f"requested_command: {result['requested_command']}",
                f"actual_command: {result['actual_command']}",
                f"returncode: {result['returncode']}",
                f"duration_ms: {result['duration_ms']}",
                f"ok: {result['ok']}",
                f"output_file: {result['output_file']}",
                "",
                "stdout:",
                (result.get("stdout") or "").rstrip(),
                "",
                "stderr:",
                (result.get("stderr") or "").rstrip(),
                "",
                "=" * 80,
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _parse_pytest_summary(output_text: str) -> dict[str, Any]:
    summary = {
        "total_reported": None,
        "passed": 0,
        "failed": 0,
        "errors": 0,
        "skipped": 0,
        "xfailed": 0,
        "xpassed": 0,
    }
    combined = output_text.replace("\n", " ")
    for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed"):
        match = re.search(rf"(\d+)\s+{key}", combined)
        if match:
            summary[key] = int(match.group(1))
    if any(summary[key] for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")):
        summary["total_reported"] = sum(int(summary[key]) for key in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed"))
    return summary


def _fetch_openapi(base_url: str) -> tuple[dict[str, Any], str]:
    with httpx.Client(timeout=DEFAULT_HTTP_TIMEOUT, follow_redirects=True) as client:
        for url in _root_openapi_urls(base_url):
            try:
                response = client.get(url)
            except Exception:
                continue
            if response.status_code == 200:
                return response.json(), f"live_fetch:{url}"
    from app.main import app

    return app.openapi(), "local_import:app.main.app"


def _build_openapi_summary(openapi_doc: dict[str, Any]) -> dict[str, Any]:
    paths = sorted((openapi_doc.get("paths") or {}).keys())
    method_count = 0
    related: dict[str, list[str]] = {}
    for path in paths:
        method_count += sum(
            1
            for method in (openapi_doc.get("paths", {}).get(path) or {})
            if method.lower() in {"get", "post", "put", "patch", "delete"}
        )
    for group, needles in OPENAPI_RELATED_GROUPS.items():
        related[group] = [path for path in paths if any(needle in path for needle in needles)]
    return {
        "path_count": len(paths),
        "method_count": method_count,
        "paths": paths,
        "related_paths": related,
    }


def _redact_sensitive(value: Any) -> Any:
    sensitive_keys = {
        "password",
        "access_token",
        "refresh_token",
        "token",
        "authorization",
        "cookie",
        "set-cookie",
    }
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, inner in value.items():
            normalized = str(key).strip().lower()
            if normalized in sensitive_keys and inner not in (None, ""):
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact_sensitive(inner)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive(item) for item in value]
    if isinstance(value, str):
        return re.sub(
            r"(?i)(password|token|jwt|secret|api[_-]?key)=([^;&\s]+)",
            r"\1=<redacted>",
            value,
        )
    return value


def _extract_top_level_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return list(value.keys())
    return []


def _collect_summary_numbers(value: Any, prefix: str = "", *, limit: int = MAX_SUMMARY_FIELDS) -> dict[str, float | int]:
    result: dict[str, float | int] = {}

    def visit(node: Any, node_prefix: str, depth: int) -> None:
        if len(result) >= limit or depth > 3:
            return
        if isinstance(node, dict):
            interesting = {"summary", "kpis", "trust", "data_quality_summary", "reconciliation", "waterfall", "cost_coverage", "action_summary"}
            for key, inner in node.items():
                next_prefix = f"{node_prefix}.{key}" if node_prefix else str(key)
                if isinstance(inner, (int, float)) and not isinstance(inner, bool):
                    result[next_prefix] = inner
                elif key in interesting or depth == 0:
                    visit(inner, next_prefix, depth + 1)
        elif isinstance(node, list) and depth < 2 and node:
            visit(node[0], f"{node_prefix}[0]", depth + 1)

    visit(value, prefix, 0)
    return result


def _get_json_sample(value: Any, max_items: int = 3, depth: int = 0) -> Any:
    if depth >= 4:
        return f"<{type(value).__name__}>"
    if isinstance(value, dict):
        return {key: _get_json_sample(inner, max_items=max_items, depth=depth + 1) for key, inner in value.items()}
    if isinstance(value, list):
        return [_get_json_sample(inner, max_items=max_items, depth=depth + 1) for inner in value[:max_items]]
    return value


def _resolve_account_id(database_url: str, preferred_account_id: int) -> tuple[int, str]:
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            preferred_exists = conn.execute(
                text("SELECT EXISTS (SELECT 1 FROM wb_accounts WHERE id = :account_id)"),
                {"account_id": preferred_account_id},
            ).scalar_one()
            if preferred_exists:
                return preferred_account_id, "requested_default_account_id"
            first_account_id = conn.execute(
                text("SELECT id FROM wb_accounts ORDER BY id LIMIT 1")
            ).scalar_one_or_none()
            if first_account_id is not None:
                return int(first_account_id), "fallback_first_account_id"
    except Exception:
        return preferred_account_id, "requested_default_account_id"
    finally:
        engine.dispose()
    return preferred_account_id, "requested_default_account_id"


def _build_auth_token(database_url: str, env_token: str | None) -> tuple[str | None, str]:
    if env_token:
        return env_token, "env_api_auth_token"
    engine = create_engine(database_url, future=True)
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT id, email, is_superuser
                    FROM auth_users
                    WHERE is_active IS TRUE
                    ORDER BY is_superuser DESC, id ASC
                    LIMIT 1
                    """
                )
            ).mappings().first()
            if row is None:
                return None, "no_active_auth_user"
            token = create_access_token(str(int(row["id"])))
            source = "generated_local_superuser_token" if bool(row["is_superuser"]) else "generated_local_user_token"
            return token, source
    except Exception:
        return None, "token_generation_failed"
    finally:
        engine.dispose()


def _http_headers(token: str | None) -> dict[str, str]:
    headers = {"accept": "application/json"}
    if token:
        headers["authorization"] = f"Bearer {token}"
    return headers


def _build_live_endpoint_specs(account_id: int, date_from: date, date_to: date) -> list[EndpointSpec]:
    common_window = {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    return [
        EndpointSpec("dashboard_data_health", "GET", "/dashboard/data-health", common_window, "sample_data_health.json"),
        EndpointSpec("dashboard_owner", "GET", "/dashboard/owner", common_window, "sample_owner_dashboard.json"),
        EndpointSpec("money_summary", "GET", "/money/summary", common_window, "sample_money_summary.json"),
        EndpointSpec("core_sku", "GET", "/core-sku", {**common_window, "limit": 20, "offset": 0}, "sample_core_sku.json"),
        EndpointSpec("dashboard_sku_profitability", "GET", "/dashboard/sku-profitability", {**common_window, "limit": 20, "offset": 0}, "sample_sku_profitability.json"),
        EndpointSpec("pricing_safety", "GET", "/pricing/safety", {**common_window, "limit": 20, "offset": 0}, "sample_pricing_safety.json"),
        EndpointSpec("dq_summary", "GET", "/dq/issues/summary", {"account_id": account_id}, "sample_dq_summary.json"),
        EndpointSpec("dq_issues_open", "GET", "/dq/issues", {**common_window, "account_id": account_id, "only_open": True, "limit": 20, "offset": 0}),
        EndpointSpec("dq_issues_final_blockers", "GET", "/dq/issues", {**common_window, "account_id": account_id, "only_open": True, "financial_final_blocker": True, "limit": 20, "offset": 0}, "sample_dq_final_blockers.json"),
        EndpointSpec("actions", "GET", "/actions", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("money_actions_today", "GET", "/money/actions/today", {**common_window, "limit": 10, "offset": 0}, "sample_actions_today.json"),
        EndpointSpec("marts_sku_daily", "GET", "/marts/sku-daily", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("marts_stock_daily", "GET", "/marts/stock-daily", {**common_window, "limit": 20, "offset": 0}, "sample_stock_daily.json"),
        EndpointSpec("marts_finance_reconciliation", "GET", "/marts/finance-reconciliation", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("marts_reconciliation_daily", "GET", "/marts/reconciliation-daily", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("costs_rows", "GET", "/costs/rows", {"account_id": account_id, "limit": 20, "offset": 0}),
        EndpointSpec("costs_unresolved", "GET", "/costs/unresolved", {"account_id": account_id, "limit": 20, "offset": 0}),
        EndpointSpec("ads_efficiency", "GET", "/ads/efficiency", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("ads_campaigns", "GET", "/ads/campaigns", {"account_id": account_id, "limit": 20, "offset": 0}),
        EndpointSpec("ads_stats", "GET", "/ads/stats", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("analytics_funnel", "GET", "/analytics/funnel", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("analytics_regions", "GET", "/analytics/regions", {**common_window, "limit": 20, "offset": 0}),
        EndpointSpec("sync_runs", "GET", "/sync/runs", {"account_id": account_id, "limit": 20, "offset": 0}),
        EndpointSpec("sync_cursors", "GET", "/sync/cursors", {"account_id": account_id, "limit": 20, "offset": 0}),
    ]


def _build_export_specs(account_id: int, date_from: date, date_to: date) -> list[EndpointSpec]:
    params = {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()}
    return [
        EndpointSpec("export_profit_by_sku", "GET", "/export/profit-by-sku.xlsx", dict(params), binary=True),
        EndpointSpec("export_data_quality", "GET", "/export/data-quality.xlsx", dict(params), binary=True),
        EndpointSpec("export_reconciliation", "GET", "/export/reconciliation.xlsx", dict(params), binary=True),
        EndpointSpec("export_stock", "GET", "/export/stock.xlsx", dict(params), binary=True),
        EndpointSpec("export_missing_costs", "GET", "/export/missing-costs.xlsx", dict(params), binary=True),
    ]


def _execute_endpoint(
    client: httpx.Client,
    base_url: str,
    spec: EndpointSpec,
    live_dir: Path,
) -> tuple[dict[str, Any], Any]:
    url = f"{base_url.rstrip('/')}/{spec.path.lstrip('/')}"
    started = time.perf_counter()
    response_json: Any = None
    try:
        response = client.request(spec.method, url, params=spec.params)
        duration_ms = int((time.perf_counter() - started) * 1000)
        content_type = response.headers.get("content-type", "")
        response_size_bytes = len(response.content)
        top_level_keys: list[str] = []
        summary_numbers: dict[str, Any] = {}
        error_text: str | None = None

        if spec.binary or "application/json" not in content_type:
            if response.status_code >= 400:
                error_text = _short_error_text(response.text)
        else:
            try:
                response_json = _redact_sensitive(response.json())
                top_level_keys = _extract_top_level_keys(response_json)
                summary_numbers = _collect_summary_numbers(response_json)
                if response.status_code >= 400:
                    error_text = _short_error_text(json.dumps(_get_json_sample(response_json), ensure_ascii=False))
            except Exception:
                error_text = _short_error_text(response.text)

        if spec.sample_file and response_json is not None:
            _write_json(live_dir / spec.sample_file, response_json)
        elif spec.sample_file and response_json is None:
            _write_json(
                live_dir / spec.sample_file,
                {
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "response_size_bytes": response_size_bytes,
                    "error_text": error_text,
                },
            )

        result = {
            "key": spec.key,
            "method": spec.method,
            "path": spec.path,
            "query": spec.params,
            "query_string": urlencode({k: v for k, v in spec.params.items() if v is not None}, doseq=True),
            "status_code": response.status_code,
            "duration_ms": duration_ms,
            "response_size_bytes": response_size_bytes,
            "content_type": content_type,
            "top_level_keys": top_level_keys,
            "summary_numbers": summary_numbers,
            "error_text": error_text,
            "sample_file": spec.sample_file,
        }
        return result, response_json
    except Exception as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        result = {
            "key": spec.key,
            "method": spec.method,
            "path": spec.path,
            "query": spec.params,
            "query_string": urlencode({k: v for k, v in spec.params.items() if v is not None}, doseq=True),
            "status_code": None,
            "duration_ms": duration_ms,
            "response_size_bytes": 0,
            "content_type": None,
            "top_level_keys": [],
            "summary_numbers": {},
            "error_text": repr(exc),
            "sample_file": spec.sample_file,
        }
        if spec.sample_file:
            _write_json(live_dir / spec.sample_file, {"error_text": repr(exc), "status_code": None})
        return result, None


def _extract_core_sku_candidates(core_sku_payload: Any) -> list[tuple[int, int | None]]:
    items = []
    if isinstance(core_sku_payload, dict):
        items = list(core_sku_payload.get("items") or [])
    candidates: list[tuple[int, int | None]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sku_id = item.get("id")
        nm_id = item.get("nm_id")
        if sku_id is not None:
            candidates.append((int(sku_id), int(nm_id) if nm_id is not None else None))
    return candidates


def _extend_core_sku_candidates(
    client: httpx.Client,
    base_url: str,
    *,
    account_id: int,
    date_from: date,
    date_to: date,
    existing: list[tuple[int, int | None]],
) -> list[tuple[int, int | None]]:
    seen = set(existing)
    params = {
        "account_id": account_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "has_revenue": True,
        "limit": 200,
        "offset": 0,
    }
    try:
        response = client.get(f"{base_url.rstrip('/')}/core-sku", params=params)
        if response.status_code != 200:
            return existing
        payload = _redact_sensitive(response.json())
        for candidate in _extract_core_sku_candidates(payload):
            if candidate not in seen:
                existing.append(candidate)
                seen.add(candidate)
    except Exception:
        return existing
    return existing


def _audit_live_endpoints(
    live_dir: Path,
    base_url: str,
    token: str | None,
    account_id: int,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    headers = _http_headers(token)
    specs = _build_live_endpoint_specs(account_id, date_from, date_to)
    results: list[dict[str, Any]] = []
    payloads: dict[str, Any] = {}

    with httpx.Client(headers=headers, timeout=DEFAULT_HTTP_TIMEOUT, follow_redirects=True) as client:
        for spec in specs:
            result, payload = _execute_endpoint(client, base_url, spec, live_dir)
            results.append(result)
            payloads[spec.key] = payload

        core_sku_candidates = _extract_core_sku_candidates(payloads.get("core_sku"))
        core_sku_candidates = _extend_core_sku_candidates(
            client,
            base_url,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            existing=core_sku_candidates,
        )
        sample_sku_id: int | None = None
        sample_nm_id: int | None = None

        for candidate_sku_id, _ in core_sku_candidates:
            detail_spec = EndpointSpec(
                "money_card_detail",
                "GET",
                f"/money/cards/{candidate_sku_id}",
                {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                "sample_money_card.json",
            )
            result, payload = _execute_endpoint(client, base_url, detail_spec, live_dir)
            if result["status_code"] == 200:
                sample_sku_id = candidate_sku_id
                results.append(result)
                payloads[detail_spec.key] = payload
                break
        if sample_sku_id is None:
            if core_sku_candidates:
                fallback_sku_id = core_sku_candidates[0][0]
                detail_spec = EndpointSpec(
                    "money_card_detail",
                    "GET",
                    f"/money/cards/{fallback_sku_id}",
                    {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                    "sample_money_card.json",
                )
                result, payload = _execute_endpoint(client, base_url, detail_spec, live_dir)
                results.append(result)
                payloads[detail_spec.key] = payload
            else:
                payloads["money_card_detail"] = None

        for _, candidate_nm_id in core_sku_candidates:
            if candidate_nm_id is None:
                continue
            article_spec = EndpointSpec(
                "money_article_detail",
                "GET",
                f"/money/articles/{candidate_nm_id}",
                {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                "sample_money_article.json",
            )
            result, payload = _execute_endpoint(client, base_url, article_spec, live_dir)
            if result["status_code"] == 200:
                sample_nm_id = candidate_nm_id
                results.append(result)
                payloads[article_spec.key] = payload
                break
        if sample_nm_id is None:
            fallback_nm_id = next((nm_id for _, nm_id in core_sku_candidates if nm_id is not None), None)
            if fallback_nm_id is not None:
                article_spec = EndpointSpec(
                    "money_article_detail",
                    "GET",
                    f"/money/articles/{fallback_nm_id}",
                    {"account_id": account_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                    "sample_money_article.json",
                )
                result, payload = _execute_endpoint(client, base_url, article_spec, live_dir)
                results.append(result)
                payloads[article_spec.key] = payload
            else:
                payloads["money_article_detail"] = None

        if sample_nm_id is not None:
            audit_spec = EndpointSpec(
                "dashboard_article_audit",
                "GET",
                "/dashboard/article-audit",
                {"account_id": account_id, "nm_id": sample_nm_id, "date_from": date_from.isoformat(), "date_to": date_to.isoformat()},
                "sample_article_audit.json",
            )
            result, payload = _execute_endpoint(client, base_url, audit_spec, live_dir)
            results.append(result)
            payloads[audit_spec.key] = payload
        elif "dashboard_article_audit" not in payloads:
            payloads["dashboard_article_audit"] = None

        export_results: list[dict[str, Any]] = []
        for spec in _build_export_specs(account_id, date_from, date_to):
            url = f"{base_url.rstrip('/')}/{spec.path.lstrip('/')}"
            started = time.perf_counter()
            try:
                response = client.request(spec.method, url, params=spec.params)
                duration_ms = int((time.perf_counter() - started) * 1000)
                content_type = response.headers.get("content-type", "")
                file_size_bytes = len(response.content)
                saved_file = None
                if response.status_code == 200 and file_size_bytes <= SMALL_EXPORT_BYTES:
                    save_name = f"{_safe_filename(spec.key)}.xlsx"
                    (live_dir / save_name).write_bytes(response.content)
                    saved_file = save_name
                export_results.append(
                    {
                        "key": spec.key,
                        "method": spec.method,
                        "path": spec.path,
                        "query": spec.params,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms,
                        "content_type": content_type,
                        "file_size_bytes": file_size_bytes,
                        "saved_file": saved_file,
                        "error_text": _short_error_text(response.text) if response.status_code >= 400 else None,
                    }
                )
            except Exception as exc:
                duration_ms = int((time.perf_counter() - started) * 1000)
                export_results.append(
                    {
                        "key": spec.key,
                        "method": spec.method,
                        "path": spec.path,
                        "query": spec.params,
                        "status_code": None,
                        "duration_ms": duration_ms,
                        "content_type": None,
                        "file_size_bytes": 0,
                        "saved_file": None,
                        "error_text": repr(exc),
                    }
                )

    errors = [
        item
        for item in results
        if item["status_code"] is None or int(item["status_code"]) >= 400
    ]
    slow = [item for item in results if item["duration_ms"] > 3000]
    very_slow = [item for item in results if item["duration_ms"] > 10000]
    endpoint_summary = {
        "account_id": account_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "base_url": base_url,
        "sample_sku_id": sample_sku_id,
        "sample_nm_id": sample_nm_id,
        "results": results,
    }
    performance_summary = {
        "endpoint_count": len(results),
        "export_count": len(export_results),
        "slow_threshold_ms": 3000,
        "very_slow_threshold_ms": 10000,
        "slow_endpoints": slow,
        "very_slow_endpoints": very_slow,
        "max_duration_ms": max((item["duration_ms"] for item in results), default=0),
        "average_duration_ms": round(sum(item["duration_ms"] for item in results) / len(results), 2) if results else 0.0,
        "acceptance": {
            "no_500": all(item["status_code"] != 500 for item in results),
            "no_404_or_405": all(item["status_code"] not in {404, 405} for item in results),
            "all_exports_xlsx_200": all(
                item["status_code"] == 200
                and item["content_type"] is not None
                and "spreadsheetml.sheet" in str(item["content_type"])
                for item in export_results
            ),
        },
    }

    _write_json(live_dir / "endpoints_result.json", endpoint_summary)
    _write_json(live_dir / "performance_summary.json", performance_summary)
    _write_json(live_dir / "endpoint_errors.json", errors)
    _write_json(live_dir / "export_results.json", export_results)

    return {
        "endpoint_summary": endpoint_summary,
        "performance_summary": performance_summary,
        "errors": errors,
        "exports": export_results,
        "payloads": payloads,
        "sample_sku_id": sample_sku_id,
        "sample_nm_id": sample_nm_id,
    }


def _table_columns(inspector_obj: Any, table_name: str) -> list[str]:
    return [column["name"] for column in inspector_obj.get_columns(table_name)]


def _count_table(conn: Any, table_name: str) -> int:
    return int(conn.execute(text(f'SELECT count(*) FROM "{table_name}"')).scalar_one())


def _count_table_by_account(conn: Any, table_name: str, account_id: int) -> int:
    return int(
        conn.execute(
            text(f'SELECT count(*) FROM "{table_name}" WHERE account_id = :account_id'),
            {"account_id": account_id},
        ).scalar_one()
    )


def _count_table_by_window(conn: Any, table_name: str, date_from: date, date_to: date) -> int:
    return int(
        conn.execute(
            text(
                f'SELECT count(*) FROM "{table_name}" '
                "WHERE stat_date >= :date_from AND stat_date <= :date_to"
            ),
            {"date_from": date_from, "date_to": date_to},
        ).scalar_one()
    )


def _query_db_outputs(
    db_dir: Path,
    database_url: str,
    account_id: int,
    date_from: date,
    date_to: date,
    data_health_payload: Any,
) -> dict[str, Any]:
    engine = create_engine(database_url, future=True)
    try:
        inspector_obj = inspect(engine)
        existing_tables = set(inspector_obj.get_table_names())
        table_counts: dict[str, Any] = {}
        mart_counts: dict[str, Any] = {}
        with engine.connect() as conn:
            for table_name in TABLES_TO_COUNT:
                if table_name not in existing_tables:
                    table_counts[table_name] = {"exists": False}
                    continue
                columns = _table_columns(inspector_obj, table_name)
                payload = {
                    "exists": True,
                    "columns": columns,
                    "total_rows": _count_table(conn, table_name),
                }
                if "account_id" in columns:
                    payload["account_rows"] = _count_table_by_account(conn, table_name, account_id)
                if "stat_date" in columns:
                    payload["window_rows"] = _count_table_by_window(conn, table_name, date_from, date_to)
                table_counts[table_name] = payload
            for table_name in MART_TABLES:
                mart_counts[table_name] = table_counts.get(table_name, {"exists": False})

            dq_severity_rows = conn.execute(
                text(
                    """
                    SELECT severity, count(*) AS count
                    FROM data_quality_issues
                    WHERE resolved_at IS NULL AND account_id = :account_id
                    GROUP BY severity
                    ORDER BY count DESC, severity
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "data_quality_issues" in existing_tables else []
            dq_type_rows = conn.execute(
                text(
                    """
                    SELECT code, count(*) AS count
                    FROM data_quality_issues
                    WHERE resolved_at IS NULL AND account_id = :account_id
                    GROUP BY code
                    ORDER BY count DESC, code
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "data_quality_issues" in existing_tables else []
            dq_blocker_rows = conn.execute(
                text(
                    """
                    SELECT code, count(*) AS count
                    FROM data_quality_issues
                    WHERE resolved_at IS NULL
                      AND account_id = :account_id
                      AND effective_financial_final_blocker IS TRUE
                    GROUP BY code
                    ORDER BY count DESC, code
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "data_quality_issues" in existing_tables else []
            dq_classification_rows = conn.execute(
                text(
                    """
                    SELECT COALESCE(NULLIF(classification_status, ''), 'unclassified') AS classification_status, count(*) AS count
                    FROM data_quality_issues
                    WHERE account_id = :account_id
                    GROUP BY COALESCE(NULLIF(classification_status, ''), 'unclassified')
                    ORDER BY count DESC, classification_status
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "data_quality_issues" in existing_tables else []
            known_exception_count = int(
                conn.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM data_quality_issues
                        WHERE resolved_at IS NULL
                          AND account_id = :account_id
                          AND COALESCE(NULLIF(classification_reason, ''), payload->>'classificationReason') = 'known_exception'
                        """
                    ),
                    {"account_id": account_id},
                ).scalar_one()
            ) if "data_quality_issues" in existing_tables else 0
            expected_lag_count = int(
                conn.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM data_quality_issues
                        WHERE resolved_at IS NULL
                          AND account_id = :account_id
                          AND COALESCE(NULLIF(classification_reason, ''), payload->>'classificationReason') = 'expected_lag'
                        """
                    ),
                    {"account_id": account_id},
                ).scalar_one()
            ) if "data_quality_issues" in existing_tables else 0
            data_quality_counts = {
                "open_issues_by_severity": {str(row["severity"]): int(row["count"]) for row in dq_severity_rows},
                "open_issues_by_type": {str(row["code"]): int(row["count"]) for row in dq_type_rows},
                "financial_final_blockers_by_type": {str(row["code"]): int(row["count"]) for row in dq_blocker_rows},
                "classified_issues_by_classification_status": {str(row["classification_status"]): int(row["count"]) for row in dq_classification_rows},
                "known_exception_count": known_exception_count,
                "expected_lag_count": expected_lag_count,
            }

            latest_runs = conn.execute(
                text(
                    """
                    SELECT DISTINCT ON (domain)
                        domain,
                        status,
                        trigger,
                        is_backfill,
                        started_at,
                        finished_at,
                        error_text
                    FROM wb_sync_runs
                    WHERE account_id = :account_id
                    ORDER BY domain, started_at DESC, id DESC
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "wb_sync_runs" in existing_tables else []
            cursor_rows = conn.execute(
                text(
                    """
                    SELECT
                        domain,
                        cursor_key,
                        status,
                        last_synced_at,
                        cursor_value->>'nextScheduledAt' AS next_scheduled_at,
                        cursor_value->>'lastErrorText' AS last_error_text,
                        cursor_value->>'lastErrorAt' AS last_error_at
                    FROM wb_sync_cursors
                    WHERE account_id = :account_id
                    ORDER BY domain, cursor_key
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "wb_sync_cursors" in existing_tables else []
            runs_by_status = conn.execute(
                text(
                    """
                    SELECT status, count(*) AS count
                    FROM wb_sync_runs
                    WHERE account_id = :account_id
                    GROUP BY status
                    ORDER BY count DESC, status
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "wb_sync_runs" in existing_tables else []
            sync_status = {
                "latest_run_by_domain": [dict(row) for row in latest_runs],
                "cursor_status_by_domain": [dict(row) for row in cursor_rows],
                "runs_by_status": {str(row["status"]): int(row["count"]) for row in runs_by_status},
            }

            manual_cost_summary = {
                "total_manual_costs": 0,
                "supplier_confirmed_count": 0,
                "operator_baseline_count": 0,
                "placeholder_count": 0,
                "estimated_range_count": 0,
                "missing_count": int((data_health_payload or {}).get("missing_manual_cost_count") or 0),
                "revenue_coverage": {
                    "supplier_confirmed_revenue_coverage_percent": float((data_health_payload or {}).get("supplier_confirmed_revenue_coverage_percent") or 0.0),
                    "operator_baseline_revenue_coverage_percent": float((data_health_payload or {}).get("operator_baseline_revenue_coverage_percent") or 0.0),
                    "trusted_revenue_cost_coverage_percent": float((data_health_payload or {}).get("trusted_revenue_cost_coverage_percent") or 0.0),
                    "revenue_cost_coverage_percent": float((data_health_payload or {}).get("revenue_cost_coverage_percent") or 0.0),
                    "placeholder_revenue_coverage_percent": 0.0,
                    "missing_revenue_coverage_percent": 0.0,
                },
            }
            if "manual_costs" in existing_tables:
                manual_row = conn.execute(
                    text(
                        """
                        SELECT
                            count(*) AS total_manual_costs,
                            sum(
                                CASE
                                    WHEN is_supplier_confirmed IS TRUE OR lower(COALESCE(cost_source, '')) = 'supplier_confirmed' THEN 1
                                    ELSE 0
                                END
                            ) AS supplier_confirmed_count,
                            sum(
                                CASE
                                    WHEN is_placeholder IS TRUE
                                      OR upper(COALESCE(supplier, '')) = 'AUTO_TEMPLATE'
                                      OR lower(COALESCE(cost_source, '')) LIKE 'placeholder%%'
                                    THEN 1
                                    ELSE 0
                                END
                            ) AS placeholder_count,
                            sum(
                                CASE
                                    WHEN lower(COALESCE(cost_source, '')) = 'estimated_range' THEN 1
                                    ELSE 0
                                END
                            ) AS estimated_range_count,
                            sum(
                                CASE
                                    WHEN NOT (
                                        is_placeholder IS TRUE
                                        OR upper(COALESCE(supplier, '')) = 'AUTO_TEMPLATE'
                                        OR lower(COALESCE(cost_source, '')) LIKE 'placeholder%%'
                                    )
                                    AND NOT (
                                        is_supplier_confirmed IS TRUE
                                        OR lower(COALESCE(cost_source, '')) = 'supplier_confirmed'
                                    )
                                    AND (
                                        is_business_trusted IS TRUE
                                        OR upper(COALESCE(supplier, '')) = 'OPERATOR_TRUSTED_COST'
                                        OR lower(COALESCE(cost_source, '')) IN ('operator_baseline', 'operator_trusted_manual', 'manual_upload')
                                    )
                                    THEN 1
                                    ELSE 0
                                END
                            ) AS operator_baseline_count
                        FROM manual_costs
                        WHERE account_id = :account_id
                        """
                    ),
                    {"account_id": account_id},
                ).mappings().one()
                manual_cost_summary.update(
                    {
                        "total_manual_costs": int(manual_row["total_manual_costs"] or 0),
                        "supplier_confirmed_count": int(manual_row["supplier_confirmed_count"] or 0),
                        "operator_baseline_count": int(manual_row["operator_baseline_count"] or 0),
                        "placeholder_count": int(manual_row["placeholder_count"] or 0),
                        "estimated_range_count": int(manual_row["estimated_range_count"] or 0),
                    }
                )
            total_coverage = float((data_health_payload or {}).get("revenue_cost_coverage_percent") or 0.0)
            supplier_coverage = float((data_health_payload or {}).get("supplier_confirmed_revenue_coverage_percent") or 0.0)
            operator_coverage = float((data_health_payload or {}).get("operator_baseline_revenue_coverage_percent") or 0.0)
            placeholder_coverage = float((data_health_payload or {}).get("revenue_with_placeholder_cost") or 0.0)
            revenue_with_cost = float((data_health_payload or {}).get("revenue_with_cost") or 0.0)
            revenue_without_cost = float((data_health_payload or {}).get("revenue_without_cost") or 0.0)
            denominator = revenue_with_cost + revenue_without_cost
            manual_cost_summary["revenue_coverage"]["placeholder_revenue_coverage_percent"] = round((placeholder_coverage / denominator) * 100, 4) if denominator else 0.0
            manual_cost_summary["revenue_coverage"]["missing_revenue_coverage_percent"] = max(0.0, round(100.0 - total_coverage, 4))
            manual_cost_summary["revenue_coverage"]["supplier_confirmed_revenue_coverage_percent"] = supplier_coverage
            manual_cost_summary["revenue_coverage"]["operator_baseline_revenue_coverage_percent"] = operator_coverage

            top_financial_blockers = conn.execute(
                text(
                    """
                    SELECT
                        code,
                        severity,
                        domain,
                        source_table,
                        COALESCE(NULLIF(classification_status, ''), 'unclassified') AS classification_status,
                        COALESCE(NULLIF(classification_reason, ''), payload->>'classificationReason') AS classification_reason,
                        count(*) AS count
                    FROM data_quality_issues
                    WHERE resolved_at IS NULL
                      AND account_id = :account_id
                      AND effective_financial_final_blocker IS TRUE
                    GROUP BY
                        code,
                        severity,
                        domain,
                        source_table,
                        COALESCE(NULLIF(classification_status, ''), 'unclassified'),
                        COALESCE(NULLIF(classification_reason, ''), payload->>'classificationReason')
                    ORDER BY count DESC, code
                    LIMIT 20
                    """
                ),
                {"account_id": account_id},
            ).mappings().all() if "data_quality_issues" in existing_tables else []

        trust_summary = {
            "operational_trusted": bool((data_health_payload or {}).get("operational_trusted")),
            "business_trusted": bool((data_health_payload or {}).get("business_trusted")),
            "financial_final": bool((data_health_payload or {}).get("financial_final")),
            "trust_state": (data_health_payload or {}).get("trust_state"),
            "supplier_confirmed_revenue_coverage_percent": float((data_health_payload or {}).get("supplier_confirmed_revenue_coverage_percent") or 0.0),
            "operator_baseline_revenue_coverage_percent": float((data_health_payload or {}).get("operator_baseline_revenue_coverage_percent") or 0.0),
            "trusted_revenue_cost_coverage_percent": float((data_health_payload or {}).get("trusted_revenue_cost_coverage_percent") or 0.0),
            "financial_final_blockers_total": int((data_health_payload or {}).get("financial_final_blockers_total") or 0),
            "open_issues_total": int((data_health_payload or {}).get("open_issues_total") or 0),
            "missing_manual_cost_count": int((data_health_payload or {}).get("missing_manual_cost_count") or 0),
            "unmatched_sku_count": int((data_health_payload or {}).get("unmatched_sku_count") or 0),
            "duplicate_srid_count": int((data_health_payload or {}).get("duplicate_srid_count") or 0),
            "source": "dashboard/data-health endpoint derived from current database state",
        }

        _write_json(db_dir / "table_counts.json", table_counts)
        _write_json(db_dir / "data_quality_counts.json", data_quality_counts)
        _write_json(db_dir / "sync_status.json", sync_status)
        _write_json(db_dir / "trust_summary.json", trust_summary)
        _write_json(db_dir / "top_financial_blockers.json", [dict(row) for row in top_financial_blockers])
        _write_json(db_dir / "manual_cost_summary.json", manual_cost_summary)
        _write_json(db_dir / "mart_counts.json", mart_counts)

        return {
            "table_counts": table_counts,
            "data_quality_counts": data_quality_counts,
            "sync_status": sync_status,
            "trust_summary": trust_summary,
            "top_financial_blockers": [dict(row) for row in top_financial_blockers],
            "manual_cost_summary": manual_cost_summary,
            "mart_counts": mart_counts,
        }
    finally:
        engine.dispose()


def _build_db_not_available(db_dir: Path, reason: str) -> dict[str, Any]:
    _write_text(
        db_dir / "DB_NOT_AVAILABLE.md",
        "\n".join(
            [
                "# DB Not Available",
                "",
                "Database access was not available for this audit run.",
                "",
                f"- Reason: {reason}",
                "- Fallback: report relies on live endpoint results where possible.",
            ]
        ),
    )
    return {"reason": reason}


def _floatish(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _approx_equal(left: Any, right: Any, tolerance: float = 0.01) -> bool:
    left_value = _floatish(left)
    right_value = _floatish(right)
    if left_value is None or right_value is None:
        return False
    return abs(left_value - right_value) <= tolerance


def _compute_formula_checks(
    reports_dir: Path,
    payloads: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    article_detail = payloads.get("money_article_detail")
    if isinstance(article_detail, dict):
        waterfall = article_detail.get("waterfall") or {}
        if waterfall:
            left = (_floatish(waterfall.get("revenue")) or 0.0) - (_floatish(waterfall.get("cogs")) or 0.0) - (_floatish(waterfall.get("direct_wb_expenses")) or 0.0) - (_floatish(waterfall.get("ads_source_spend")) or 0.0)
            right = waterfall.get("profit_after_source_ads")
            checks.append(
                {
                    "name": "money_article_waterfall_profit_after_ads",
                    "available": True,
                    "passed": _approx_equal(left, right),
                    "expected": left,
                    "actual": right,
                    "context": "money_article_detail.waterfall",
                }
            )
            left_overhead = (_floatish(waterfall.get("profit_after_source_ads")) or 0.0) - (_floatish(waterfall.get("allocated_overhead")) or 0.0)
            right_overhead = waterfall.get("profit_after_overhead")
            checks.append(
                {
                    "name": "money_article_waterfall_profit_after_overhead",
                    "available": True,
                    "passed": _approx_equal(left_overhead, right_overhead),
                    "expected": left_overhead,
                    "actual": right_overhead,
                    "context": "money_article_detail.waterfall",
                }
            )
        else:
            checks.append({"name": "money_article_waterfall", "available": False, "passed": False, "reason": "waterfall block missing"})
    else:
        checks.append({"name": "money_article_waterfall", "available": False, "passed": False, "reason": "money article detail unavailable"})

    stock_daily = payloads.get("marts_stock_daily")
    stock_items = stock_daily.get("items") if isinstance(stock_daily, dict) else None
    if isinstance(stock_items, list) and stock_items:
        row = stock_items[0]
        sales_30d = _floatish(row.get("sales_30d"))
        qty = _floatish(row.get("quantity"))
        avg_sales_per_day_30d = row.get("avg_sales_per_day_30d")
        if sales_30d is not None:
            checks.append(
                {
                    "name": "stock_avg_sales_per_day_30d",
                    "available": True,
                    "passed": _approx_equal(sales_30d / 30.0, avg_sales_per_day_30d, tolerance=0.001),
                    "expected": sales_30d / 30.0,
                    "actual": avg_sales_per_day_30d,
                    "context": "marts_stock_daily.items[0]",
                }
            )
        if qty is not None and qty > 0 and avg_sales_per_day_30d not in (None, 0):
            checks.append(
                {
                    "name": "stock_days_of_stock",
                    "available": True,
                    "passed": _approx_equal(qty / float(avg_sales_per_day_30d), row.get("days_of_stock"), tolerance=0.001),
                    "expected": qty / float(avg_sales_per_day_30d),
                    "actual": row.get("days_of_stock"),
                    "context": "marts_stock_daily.items[0]",
                }
            )
            checks.append(
                {
                    "name": "stock_turnover_rate",
                    "available": True,
                    "passed": _approx_equal((sales_30d or 0.0) / qty, row.get("turnover_rate"), tolerance=0.001),
                    "expected": (sales_30d or 0.0) / qty,
                    "actual": row.get("turnover_rate"),
                    "context": "marts_stock_daily.items[0]",
                }
            )
    else:
        checks.append({"name": "stock_mart_formulas", "available": False, "passed": False, "reason": "stock daily items unavailable"})

    pricing = payloads.get("pricing_safety")
    if isinstance(pricing, dict):
        items = pricing.get("items") or []
        summary = pricing.get("summary") or {}
        total = pricing.get("total")
        if isinstance(items, list) and total == len(items):
            below_break_even = sum(1 for item in items if isinstance(item, dict) and (_floatish(item.get("safe_price_gap")) or 0.0) < 0)
            checks.append(
                {
                    "name": "pricing_below_break_even_count",
                    "available": True,
                    "passed": int(summary.get("below_break_even_count") or 0) == below_break_even,
                    "expected": below_break_even,
                    "actual": int(summary.get("below_break_even_count") or 0),
                    "context": "pricing_safety.summary",
                }
            )
        else:
            checks.append(
                {
                    "name": "pricing_below_break_even_count",
                    "available": False,
                    "passed": False,
                    "reason": "pricing summary scope differs from current page",
                }
            )

    dq_summary = payloads.get("dq_summary")
    if isinstance(dq_summary, dict):
        open_issues_total = int(dq_summary.get("open_issues_total") or 0)
        by_severity_total = sum(int(value or 0) for value in (dq_summary.get("by_severity") or {}).values())
        by_issue_type_total = sum(int(value or 0) for value in (dq_summary.get("by_issue_type") or {}).values())
        checks.append(
            {
                "name": "dq_sum_by_severity",
                "available": True,
                "passed": by_severity_total == open_issues_total,
                "expected": open_issues_total,
                "actual": by_severity_total,
                "context": "dq_summary.by_severity",
            }
        )
        checks.append(
            {
                "name": "dq_sum_by_issue_type",
                "available": True,
                "passed": by_issue_type_total == open_issues_total,
                "expected": open_issues_total,
                "actual": by_issue_type_total,
                "context": "dq_summary.by_issue_type",
            }
        )

    failures = [check for check in checks if check.get("available") and not check.get("passed")]
    skipped = [check for check in checks if not check.get("available")]
    result = {
        "checks": checks,
        "passed_count": sum(1 for check in checks if check.get("available") and check.get("passed")),
        "failed_count": len(failures),
        "skipped_count": len(skipped),
        "failures": failures,
        "skipped": skipped,
    }
    _write_json(reports_dir / "formula_checks.json", result)
    _write_json(reports_dir / "formula_check_failures.json", failures)
    return result


def _build_final_report(
    report_path: Path,
    *,
    now: datetime,
    assumptions: list[str],
    command_results: list[dict[str, Any]],
    pytest_summary: dict[str, Any],
    openapi_summary: dict[str, Any],
    live_result: dict[str, Any],
    db_result: dict[str, Any],
    formula_result: dict[str, Any],
) -> None:
    data_health = live_result.get("payloads", {}).get("dashboard_data_health") or {}
    dq_summary = live_result.get("payloads", {}).get("dq_summary") or {}
    endpoint_results = list(live_result.get("endpoint_summary", {}).get("results") or [])
    export_results = list(live_result.get("exports") or [])
    endpoint_errors = list(live_result.get("errors") or [])
    performance_summary = live_result.get("performance_summary") or {}
    trust_summary = db_result.get("trust_summary") or {}
    financial_final_ready = bool(trust_summary.get("financial_final")) and int(trust_summary.get("financial_final_blockers_total") or 0) == 0
    operational_ready = bool(trust_summary.get("operational_trusted")) and not endpoint_errors

    lines = [
        "# Final Backend Audit Report",
        "",
        f"- Generated at: `{now.isoformat()}`",
        "",
        "## 1. Commands run and results",
        "",
    ]
    for result in command_results:
        lines.append(
            f"- `{result['requested_command']}` -> returncode `{result['returncode']}`, duration `{result['duration_ms']} ms`, status `{'ok' if result['ok'] else 'failed'}`"
        )
    lines.extend(
        [
            "",
            "## 2. Test count",
            "",
            f"- Total reported tests: `{pytest_summary.get('total_reported')}`",
            f"- Passed: `{pytest_summary.get('passed')}`",
            f"- Failed: `{pytest_summary.get('failed')}`",
            f"- Errors: `{pytest_summary.get('errors')}`",
            f"- Skipped: `{pytest_summary.get('skipped')}`",
            "",
            "## 3. Alembic head",
            "",
        ]
    )
    alembic_head_result = next((item for item in command_results if item["requested_command"] == "python -m alembic heads"), None)
    alembic_head_text = (alembic_head_result or {}).get("stdout", "").strip() or "not available"
    lines.append(f"- Alembic heads output: `{alembic_head_text}`")
    lines.extend(
        [
            "",
            "## 4. Endpoint status summary",
            "",
            f"- OpenAPI path count: `{openapi_summary.get('path_count')}`",
            f"- Audited live endpoints: `{len(endpoint_results)}`",
            f"- Endpoint errors: `{len(endpoint_errors)}`",
            f"- No 500 responses: `{performance_summary.get('acceptance', {}).get('no_500')}`",
            f"- No 404/405 responses: `{performance_summary.get('acceptance', {}).get('no_404_or_405')}`",
        ]
    )
    if endpoint_errors:
        lines.append("- Failed endpoints:")
        for item in endpoint_errors:
            lines.append(f"  - `{item['method']} {item['path']}` -> `{item['status_code']}` `{item['error_text']}`")
    lines.extend(
        [
            "",
            "## 5. Export status summary",
            "",
            f"- Export endpoints checked: `{len(export_results)}`",
            f"- All exports returned 200 XLSX: `{performance_summary.get('acceptance', {}).get('all_exports_xlsx_200')}`",
        ]
    )
    for item in export_results:
        lines.append(
            f"- `{item['path']}` -> status `{item['status_code']}`, type `{item['content_type']}`, size `{item['file_size_bytes']}` bytes, duration `{item['duration_ms']} ms`"
        )
    lines.extend(
        [
            "",
            "## 6. Performance summary",
            "",
            f"- Average endpoint duration: `{performance_summary.get('average_duration_ms')} ms`",
            f"- Max endpoint duration: `{performance_summary.get('max_duration_ms')} ms`",
            f"- Slow endpoints over 3s: `{len(performance_summary.get('slow_endpoints') or [])}`",
            f"- Very slow endpoints over 10s: `{len(performance_summary.get('very_slow_endpoints') or [])}`",
            "",
            "## 7. DB table counts",
            "",
        ]
    )
    table_counts = db_result.get("table_counts") or {}
    if table_counts:
        for table_name, payload in table_counts.items():
            if payload.get("exists"):
                lines.append(f"- `{table_name}` -> total `{payload.get('total_rows')}`, account `{payload.get('account_rows')}`")
    else:
        lines.append("- Database summary unavailable")
    lines.extend(
        [
            "",
            "## 8. Data trust summary",
            "",
            f"- trust_state: `{trust_summary.get('trust_state')}`",
            f"- operational_trusted: `{trust_summary.get('operational_trusted')}`",
            f"- business_trusted: `{trust_summary.get('business_trusted')}`",
            f"- financial_final: `{trust_summary.get('financial_final')}`",
            f"- supplier_confirmed_revenue_coverage_percent: `{trust_summary.get('supplier_confirmed_revenue_coverage_percent')}`",
            f"- operator_baseline_revenue_coverage_percent: `{trust_summary.get('operator_baseline_revenue_coverage_percent')}`",
            f"- trusted_revenue_cost_coverage_percent: `{trust_summary.get('trusted_revenue_cost_coverage_percent')}`",
            "",
            "## 9. DQ summary",
            "",
            f"- open_issues_total: `{dq_summary.get('open_issues_total')}`",
            f"- financial_final_blockers_total: `{dq_summary.get('financial_final_blockers_total')}`",
            f"- by_severity: `{json.dumps(dq_summary.get('by_severity') or {}, ensure_ascii=False)}`",
            f"- by_issue_type: `{json.dumps(dq_summary.get('by_issue_type') or {}, ensure_ascii=False)}`",
            "",
            "## 10. Financial final status",
            "",
            f"- Financial final ready: `{financial_final_ready}`",
            f"- financial_final flag: `{trust_summary.get('financial_final')}`",
            f"- financial_final_blockers_total: `{trust_summary.get('financial_final_blockers_total')}`",
            "",
            "## 11. Formula checks",
            "",
            f"- Passed checks: `{formula_result.get('passed_count')}`",
            f"- Failed checks: `{formula_result.get('failed_count')}`",
            f"- Skipped checks: `{formula_result.get('skipped_count')}`",
            "",
            "## 12. Known remaining issues",
            "",
        ]
    )
    remaining_issues: list[str] = []
    if endpoint_errors:
        remaining_issues.append(f"{len(endpoint_errors)} audited endpoints returned non-2xx responses")
    if int(trust_summary.get("financial_final_blockers_total") or 0) > 0:
        remaining_issues.append(
            f"financial_final_blockers_total remains {trust_summary.get('financial_final_blockers_total')}"
        )
    if int(trust_summary.get("open_issues_total") or 0) > 0:
        remaining_issues.append(f"open_issues_total remains {trust_summary.get('open_issues_total')}")
    if int(trust_summary.get("missing_manual_cost_count") or 0) > 0:
        remaining_issues.append(f"missing_manual_cost_count remains {trust_summary.get('missing_manual_cost_count')}")
    if formula_result.get("failed_count"):
        remaining_issues.append(f"{formula_result.get('failed_count')} formula checks failed")
    if not remaining_issues:
        remaining_issues.append("No critical remaining issues were detected by this bundle")
    for item in remaining_issues:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 13. Whether operational usage is ready",
            "",
            f"- Operational usage ready: `{operational_ready}`",
            "",
            "## 14. Whether financial final is ready",
            "",
            f"- Financial final ready: `{financial_final_ready}`",
            "",
            "## 15. Security note",
            "",
            "- Credentials redacted. No API tokens, cookies, or passwords were intentionally written into the bundle.",
        ]
    )
    if assumptions:
        lines.extend(["", "## Assumptions", ""])
        for item in assumptions:
            lines.append(f"- {item}")
    _write_text(report_path, "\n".join(lines))


def _zip_directory(source_dir: Path, output_zip: Path) -> Path:
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path == output_zip:
                continue
            if path.is_dir():
                continue
            archive.write(path, arcname=str(path.relative_to(source_dir)))
    return output_zip


def main() -> int:
    now = _now_local()
    timestamp = _timestamp_slug(now)
    bundle_name = f"backend_live_audit_final_{timestamp}"
    bundle_dir = OUTPUT_ROOT / bundle_name
    reports_dir = bundle_dir / "reports"
    live_dir = bundle_dir / "live"
    db_dir = bundle_dir / "db"
    final_report_path = bundle_dir / "FINAL_BACKEND_AUDIT_REPORT.md"
    backend_source_zip_path = bundle_dir / "backend_final.zip"
    final_zip_path = REPO_ROOT / f"{bundle_name}.zip"
    assumptions: list[str] = []

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    live_dir.mkdir(parents=True, exist_ok=True)
    db_dir.mkdir(parents=True, exist_ok=True)

    settings = _load_runtime_settings()
    python_bin = _pick_python_bin()
    base_url_env = os.getenv("API_BASE_URL")
    base_url = _normalize_base_url(base_url_env)
    if not base_url_env and _is_local_api_reachable(DEFAULT_LOCAL_API_BASE_URL):
        base_url = DEFAULT_LOCAL_API_BASE_URL
        assumptions.append("`API_BASE_URL` was not set, so the audit used the reachable local backend at `http://127.0.0.1:8000/api/v1`.")
    date_to = date.fromisoformat(os.getenv("DATE_TO")) if os.getenv("DATE_TO") else now.date()
    date_from = date.fromisoformat(os.getenv("DATE_FROM")) if os.getenv("DATE_FROM") else date_to - timedelta(days=30)
    database_url = _resolve_database_url(settings)
    account_id, account_source = _resolve_account_id(database_url, int(os.getenv("ACCOUNT_ID") or DEFAULT_ACCOUNT_ID))
    if account_source == "fallback_first_account_id":
        assumptions.append(f"Account `{DEFAULT_ACCOUNT_ID}` was not present in `wb_accounts`, so the audit used account `{account_id}` instead.")
    token, token_source = _build_auth_token(database_url, os.getenv("API_AUTH_TOKEN"))
    if token_source != "env_api_auth_token":
        assumptions.append(f"Auth used `{token_source}` because `API_AUTH_TOKEN` was not set.")

    source_result = _create_backend_source_zip(backend_source_zip_path)

    command_specs = [
        CommandSpec(
            requested="python -m compileall -q app tests scripts alembic",
            actual=[str(python_bin), "-m", "compileall", "-q", "app", "tests", "scripts", "alembic"],
            output_file="compileall_result.txt",
        ),
        CommandSpec(
            requested="python -m pytest -q -p no:ddtrace",
            actual=[str(python_bin), "-m", "pytest", "-q", "-p", "no:ddtrace"],
            output_file="pytest_result.txt",
            timeout_seconds=2400,
        ),
        CommandSpec(
            requested="python -m alembic heads",
            actual=[str(python_bin), "-m", "alembic", "heads"],
            output_file="alembic_heads.txt",
        ),
        CommandSpec(
            requested="python -m alembic upgrade head --sql > reports/alembic_upgrade_head.sql",
            actual=[str(python_bin), "-m", "alembic", "upgrade", "head", "--sql"],
            output_file="alembic_upgrade_head.sql",
            stdout_to_file=True,
        ),
    ]
    verify_script = REPO_ROOT / "scripts" / "verify_backend_correctness.py"
    if verify_script.exists():
        command_specs.append(
            CommandSpec(
                requested="python scripts/verify_backend_correctness.py --skip-clean-postgres",
                actual=[str(python_bin), "scripts/verify_backend_correctness.py", "--skip-clean-postgres"],
                output_file="verify_backend_correctness.txt",
                timeout_seconds=3600,
            )
        )
    command_results = [_run_command(spec, reports_dir) for spec in command_specs]
    _write_text(reports_dir / "commands.log", _build_commands_log(command_results))

    pytest_result = next((item for item in command_results if item["requested_command"] == "python -m pytest -q -p no:ddtrace"), None)
    pytest_summary = _parse_pytest_summary((pytest_result or {}).get("stdout", "") + "\n" + (pytest_result or {}).get("stderr", ""))

    openapi_doc, openapi_source = _fetch_openapi(base_url)
    openapi_summary = _build_openapi_summary(openapi_doc)
    openapi_summary["source"] = openapi_source
    _write_json(reports_dir / "openapi.json", openapi_doc)
    _write_json(reports_dir / "openapi_summary.json", openapi_summary)

    live_result = _audit_live_endpoints(
        live_dir=live_dir,
        base_url=base_url,
        token=token,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )

    try:
        db_result = _query_db_outputs(
            db_dir=db_dir,
            database_url=database_url,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            data_health_payload=live_result.get("payloads", {}).get("dashboard_data_health"),
        )
    except Exception as exc:
        db_result = _build_db_not_available(db_dir, repr(exc))

    formula_result = _compute_formula_checks(reports_dir, live_result.get("payloads") or {})

    _build_final_report(
        final_report_path,
        now=now,
        assumptions=assumptions,
        command_results=command_results,
        pytest_summary=pytest_summary,
        openapi_summary=openapi_summary,
        live_result=live_result,
        db_result=db_result,
        formula_result=formula_result,
    )

    if final_zip_path.exists():
        final_zip_path.unlink()
    _zip_directory(bundle_dir, final_zip_path)

    summary = {
        "backend_final_zip": str(backend_source_zip_path),
        "final_bundle_zip": str(final_zip_path),
        "bundle_dir": str(bundle_dir),
        "source_files_added": source_result["files_added"],
        "account_id": account_id,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "base_url": base_url,
        "token_source": token_source,
        "endpoint_error_count": len(live_result.get("errors") or []),
        "export_error_count": sum(
            1 for item in (live_result.get("exports") or []) if item.get("status_code") != 200
        ),
        "financial_final": bool((db_result.get("trust_summary") or {}).get("financial_final")),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
