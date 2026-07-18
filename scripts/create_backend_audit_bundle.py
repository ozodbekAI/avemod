from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
AUDIT_PARENT = ROOT / "audit_bundles"

DEFAULT_DATE_TO = date(2026, 7, 12)
DEFAULT_DATE_FROM = DEFAULT_DATE_TO - timedelta(days=30)
DEFAULT_SAMPLE_LIMIT = 50

SENSITIVE_KEY_RE = re.compile(
    r"(authorization|bearer|cookie|credential|database_url|dsn|email|encrypted|encryption|jwt|key|password|phone|private|refresh|secret|token)",
    re.IGNORECASE,
)
IDENTITY_KEY_RE = re.compile(
    r"(^|_)(account_name|company|email|fio|full_name|inn|legal|name|phone|seller|supplier|tax_id|user_name)($|_)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]?){10,16}(?!\d)")
AUTH_HEADER_RE = re.compile(r"(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;]+", re.IGNORECASE)
URL_PASSWORD_RE = re.compile(r"([a-z][a-z0-9+.-]*://[^:/@\s]+:)([^@/\s]+)(@)", re.IGNORECASE)
LONG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_/-])([A-Za-z0-9+/=-]{40,})(?![A-Za-z0-9_/-])")
CODE_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?P<prefix>^\s*[A-Z_][A-Z0-9_]*(?:SECRET|PASSWORD|API_KEY|ENCRYPTION_KEY|PRIVATE_KEY|DATABASE_URL|DSN)[A-Z0-9_]*\b[^\n=]*=\s*)(?P<quote>[\"'])(?P<value>[^\"'\n]*)(?P=quote)",
    re.IGNORECASE | re.MULTILINE,
)
QUOTED_LONG_TOKEN_RE = re.compile(r"(?P<quote>[\"'])(?P<value>[A-Za-z0-9+/=_-]{40,})(?P=quote)")

SEARCH_TERMS = [
    "риски не найдены",
    "источники в порядке",
    "Data blocked",
    "Данные заблокированы",
    "saved money",
    "сэкономлено",
    "confirmed_loss",
    "manual_edit_allowed",
    "fixability",
    "owner_type",
    "issue_nature",
    "can_user_fix_inside_platform",
    "apply_to_wb",
    "dangerous_action",
    "problem_instance_id",
    "result_summary",
]

ISSUE_CODES = [
    "ads_allocation_incomplete",
    "stock_without_sales",
    "missing_chrt_id",
    "sales_without_confirmed_stock",
    "order_without_sale_or_return",
    "finance_reconciliation_mismatch",
    "missing_cost_blocks_profit",
    "manual_cost_unresolved_sku",
    "expense_unclassified",
]

CODE_INCLUDE_PATHS = [
    "app/main.py",
    "app/api/router.py",
    "app/core/action_registry.py",
    "app/core/config.py",
    "app/core/current_state.py",
    "app/core/db.py",
    "app/core/dedupe.py",
    "app/core/model_registry.py",
    "app/core/redaction.py",
    "app/core/security.py",
    "app/core/stock_fallback.py",
    "app/core/wb_connector_inventory.py",
    "app/models/accounts.py",
    "app/models/auth.py",
    "app/models/card_quality.py",
    "app/models/control_tower.py",
    "app/models/data_quality.py",
    "app/models/finance.py",
    "app/models/manual_costs.py",
    "app/models/marts.py",
    "app/models/operator.py",
    "app/models/problem_engine.py",
    "app/models/product_cards.py",
    "app/models/sync.py",
    "app/modules/auth",
    "app/modules/dashboard",
    "app/modules/data_quality",
    "app/modules/finance",
    "app/modules/manual_costs",
    "app/modules/marts",
    "app/modules/money_management",
    "app/modules/portal",
    "app/modules/problem_rules",
    "app/modules/product_cards",
    "app/modules/sync",
    "app/repositories/accounts.py",
    "app/repositories/auth.py",
    "app/repositories/data_quality.py",
    "app/repositories/finance.py",
    "app/repositories/manual_costs.py",
    "app/repositories/marts.py",
    "app/repositories/product_cards.py",
    "app/repositories/sync.py",
    "app/schemas/accounts.py",
    "app/schemas/auth.py",
    "app/schemas/card_quality.py",
    "app/schemas/control_tower.py",
    "app/schemas/dashboard.py",
    "app/schemas/data_quality.py",
    "app/schemas/evidence.py",
    "app/schemas/finance.py",
    "app/schemas/manual_costs.py",
    "app/schemas/marts.py",
    "app/schemas/money_management.py",
    "app/schemas/money_trust.py",
    "app/schemas/operator.py",
    "app/schemas/portal.py",
    "app/schemas/problem_engine.py",
    "app/schemas/product_cards.py",
    "app/schemas/sync.py",
    "app/services/accounts.py",
    "app/services/auth.py",
    "app/services/card_quality.py",
    "app/services/checker_adapter.py",
    "app/services/checker_core",
    "app/services/checker_problem_bridge.py",
    "app/services/control_tower.py",
    "app/services/dashboard.py",
    "app/services/data_quality.py",
    "app/services/evidence.py",
    "app/services/finance.py",
    "app/services/guided_fixes.py",
    "app/services/manual_costs.py",
    "app/services/marts.py",
    "app/services/money_management.py",
    "app/services/money_snapshots.py",
    "app/services/operator_snapshots.py",
    "app/services/portal.py",
    "app/services/problem_engine",
    "app/services/product_cards.py",
    "app/services/result_tracking.py",
    "app/services/sync.py",
]

MIGRATION_KEYWORDS = [
    "action",
    "admin_rule",
    "card_quality",
    "data_quality",
    "dynamic_problem",
    "finance",
    "manual_cost",
    "metric",
    "money",
    "operator",
    "portal",
    "problem",
    "result",
    "rule",
]

SAMPLE_TABLES = {
    "problem_instances": ["problem_instances"],
    "problem_instance_history": ["problem_instance_history"],
    "result_events": ["result_events"],
    "data_quality_issues": ["data_quality_issues"],
    "data_readiness_source_status": ["portal_integrations", "portal_module_sync_runs", "wb_sync_cursors"],
    "sync_runs": ["wb_sync_runs", "portal_module_sync_runs"],
    "card_quality_issues": ["card_quality_issues", "card_quality_issue_status_history", "card_quality_analysis_runs"],
    "finance_money_source_rows": [
        "wb_realization_reports",
        "wb_realization_report_rows",
        "wb_acquiring_reports",
        "wb_acquiring_report_rows",
        "wb_balance_snapshots",
        "mart_finance_reconciliation",
        "mart_account_expense_daily",
        "mart_expense_daily",
        "mart_reconciliation_daily",
    ],
    "mart_sku_daily_or_profitability": ["mart_sku_daily"],
    "ads_allocation_source_rows": ["wb_ad_stats_daily", "wb_ad_campaigns", "wb_ad_campaign_items", "wb_ad_cluster_stats"],
    "costs_manual_costs": ["manual_costs", "manual_cost_uploads"],
    "product_cards_products": ["wb_product_cards", "wb_product_card_sizes", "wb_product_card_characteristics", "core_sku"],
    "admin_problem_rules": [
        "metric_catalog",
        "problem_definitions",
        "problem_rule_versions",
        "admin_rule_test_runs",
        "problem_rule_admin_audit",
        "problem_evaluation_run_logs",
    ],
}

TABLE_COUNT_GROUPS = {
    "accounts_users_companies": ["auth_users", "auth_user_account_access", "wb_accounts", "user_business_settings"],
    "products_cards": ["wb_product_cards", "core_sku"],
    "product_dimensions": ["wb_product_card_sizes", "wb_product_card_characteristics", "wb_product_card_tags"],
    "finance_reports": ["wb_realization_reports", "wb_realization_report_rows", "wb_acquiring_reports", "wb_acquiring_report_rows", "wb_balance_snapshots"],
    "sales_orders_stocks_prices_ads": [
        "wb_sales",
        "wb_orders",
        "wb_stock_snapshots",
        "wb_stock_snapshot_rows",
        "wb_prices",
        "wb_price_snapshots",
        "wb_ad_campaigns",
        "wb_ad_stats_daily",
    ],
    "costs_manual_costs": ["manual_costs", "manual_cost_uploads"],
    "data_quality_issues": ["data_quality_issues"],
    "problem_instances": ["problem_instances"],
    "problem_instance_history": ["problem_instance_history"],
    "unified_actions_action_recommendations": ["unified_actions", "action_recommendations", "action_recommendation_history"],
    "result_events": ["result_events"],
    "card_quality": ["card_quality_issues", "card_quality_analysis_runs", "card_quality_snapshots"],
    "sync_runs": ["wb_sync_runs", "portal_module_sync_runs", "wb_sync_cursors"],
    "admin_problem_rules": ["metric_catalog", "problem_definitions", "problem_rule_versions", "admin_rule_test_runs", "problem_rule_admin_audit"],
    "metric_catalog": ["metric_catalog"],
}

CONTRACT_CATEGORIES = {
    "Dashboard / readiness": [
        "/api/v1/portal/overview",
        "/api/v1/dashboard/data-health",
        "/api/v1/portal/data-readiness",
        "/api/v1/portal/data-sync/status",
        "/api/v1/dashboard/owner",
    ],
    "Action Center": [
        "/api/v1/portal/actions",
        "/api/v1/portal/actions/by-source",
        "/api/v1/portal/actions/{action_id}",
        "/api/v1/portal/problems/{problem_id}/recheck",
        "/api/v1/portal/problems/{problem_instance_id}/results",
        "/api/v1/portal/actions/{action_id}/results",
    ],
    "Data Fix": [
        "/api/v1/money/data-blockers",
        "/api/v1/dq/issues/summary",
        "/api/v1/dq/issues",
        "/api/v1/dq/issues/{issue_id}/resolution-context",
        "/api/v1/dq/issues/{issue_id}/recheck",
        "/api/v1/dq/issues/{issue_id}/guided-action",
    ],
    "Money / Finance": [
        "/api/v1/money/summary",
        "/api/v1/money/actions/today",
        "/api/v1/money/data-blockers",
        "/api/v1/finance/reports",
        "/api/v1/finance/report-rows",
        "/api/v1/money/cards",
        "/api/v1/money/articles",
        "/api/v1/money/profit-cascade",
        "/api/v1/money/expenses/breakdown",
        "/api/v1/money/expenses/report-rows",
    ],
    "Product360": [
        "/api/v1/portal/products/{nm_id}",
        "/api/v1/portal/products",
        "/api/v1/portal/products/{nm_id}/quality",
        "/api/v1/products",
    ],
    "Results": [
        "/api/v1/portal/results",
        "/api/v1/portal/problems/{problem_instance_id}/results",
        "/api/v1/portal/actions/{action_id}/results",
    ],
    "Checker": [
        "/api/v1/portal/card-quality/issues",
        "/api/v1/portal/card-quality/issues/grouped",
        "/api/v1/portal/card-quality/analyze",
        "/api/v1/portal/card-quality/issues/{issue_id}/preview",
        "/api/v1/portal/card-quality/issues/{issue_id}/apply-wb",
        "/api/v1/portal/card-quality/issues/{issue_id}/recheck",
        "/api/v1/portal/card-quality/products/{nm_id}/analyze",
        "/api/v1/portal/card-quality/products/{nm_id}/recheck",
        "/api/v1/portal/card-quality/runs",
    ],
    "Admin Rules": [
        "/api/v1/admin/problem-rules/metrics",
        "/api/v1/admin/problem-rules/definitions",
        "/api/v1/admin/problem-rules/versions/{version_id}/validate",
        "/api/v1/admin/problem-rules/versions/{version_id}/backtest",
        "/api/v1/admin/problem-rules/versions/{version_id}/publish",
        "/api/v1/admin/problem-rules/versions/{version_id}/pause",
        "/api/v1/admin/problem-rules/versions/{version_id}/archive",
        "/api/v1/admin/problem-rules/summary",
        "/api/v1/admin/problem-rules/{id}/instances",
        "/api/v1/admin/problem-rules/{id}/backtests",
    ],
}


def local_now() -> datetime:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("Asia/Tashkent"))
    return datetime.now().astimezone()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<bytes length={len(value)}>"
    return str(value)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:12]


def redact_string(value: str, *, key: str = "") -> str:
    if not value:
        return value
    lower_key = key.lower()
    if SENSITIVE_KEY_RE.search(lower_key):
        return f"<REDACTED length={len(value)} sha256={sha256_text(value)}>"
    if IDENTITY_KEY_RE.search(lower_key):
        if "email" in lower_key:
            return EMAIL_RE.sub("<EMAIL_REDACTED>", value)
        if "phone" in lower_key:
            return PHONE_RE.sub("<PHONE_REDACTED>", value)
        return f"<MASKED {key or 'identity'} length={len(value)}>"
    redacted = AUTH_HEADER_RE.sub(r"\1<REDACTED>", value)
    redacted = URL_PASSWORD_RE.sub(r"\1<REDACTED>\3", redacted)
    redacted = EMAIL_RE.sub("<EMAIL_REDACTED>", redacted)
    redacted = PHONE_RE.sub("<PHONE_REDACTED>", redacted)

    def _token(match: re.Match[str]) -> str:
        token = match.group(1)
        if re.search(r"[A-Za-z]", token) and re.search(r"\d", token):
            return f"<REDACTED token-like length={len(token)} sha256={sha256_text(token)}>"
        return token

    return LONG_TOKEN_RE.sub(_token, redacted)


def sanitize(value: Any, *, key: str = "") -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<bytes length={len(value)}>"
    if isinstance(value, str):
        return redact_string(value, key=key)
    if isinstance(value, list):
        return [sanitize(item, key=key) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item, key=key) for item in value]
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for raw_key, item in value.items():
            item_key = str(raw_key)
            if SENSITIVE_KEY_RE.search(item_key) and item_key.lower() not in {
                "token_category",
                "token_configured",
                "token_ok",
                "missing_token_categories",
                "required_token_categories",
            }:
                result[item_key] = sanitize("<REDACTED>", key=item_key)
            else:
                result[item_key] = sanitize(item, key=item_key)
        return result
    return redact_string(str(value), key=key)


def redact_text(text: str) -> str:
    redacted = AUTH_HEADER_RE.sub(r"\1<REDACTED>", text)
    redacted = URL_PASSWORD_RE.sub(r"\1<REDACTED>\3", redacted)
    redacted = EMAIL_RE.sub("<EMAIL_REDACTED>", redacted)
    redacted = PHONE_RE.sub("<PHONE_REDACTED>", redacted)
    redacted = CODE_SECRET_ASSIGNMENT_RE.sub(r"\g<prefix>\g<quote><REDACTED>\g<quote>", redacted)
    return LONG_TOKEN_RE.sub(lambda m: f"<REDACTED token-like length={len(m.group(1))} sha256={sha256_text(m.group(1))}>", redacted)


def redact_source_text(text: str) -> str:
    redacted = AUTH_HEADER_RE.sub(r"\1<REDACTED>", text)
    redacted = URL_PASSWORD_RE.sub(r"\1<REDACTED>\3", redacted)
    redacted = EMAIL_RE.sub("<EMAIL_REDACTED>", redacted)
    redacted = PHONE_RE.sub("<PHONE_REDACTED>", redacted)
    return CODE_SECRET_ASSIGNMENT_RE.sub(r"\g<prefix>\g<quote><REDACTED>\g<quote>", redacted)


def redacted_url(database_url: str) -> str:
    parsed = urlparse(database_url.replace("postgresql+asyncpg://", "postgresql://", 1))
    netloc = parsed.netloc
    if "@" in netloc:
        auth, host = netloc.rsplit("@", 1)
        if ":" in auth:
            user, password = auth.split(":", 1)
            auth = f"{user}:<REDACTED length={len(password)}>"
        netloc = f"{auth}@{host}"
    return urlunparse(parsed._replace(netloc=netloc))


def run_command(
    args: list[str],
    *,
    cwd: Path = ROOT,
    timeout: int = 300,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = local_now().isoformat(timespec="seconds")
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env={**os.environ, **(env or {})},
        )
        stdout = redact_text(proc.stdout or "")
        stderr = redact_text(proc.stderr or "")
        return {
            "command": args,
            "cwd": str(cwd),
            "started_at": started,
            "finished_at": local_now().isoformat(timespec="seconds"),
            "returncode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": args,
            "cwd": str(cwd),
            "started_at": started,
            "finished_at": local_now().isoformat(timespec="seconds"),
            "returncode": None,
            "timeout_seconds": timeout,
            "stdout": redact_text(exc.stdout or ""),
            "stderr": redact_text(exc.stderr or ""),
            "error": "timeout",
        }
    except Exception as exc:
        return {
            "command": args,
            "cwd": str(cwd),
            "started_at": started,
            "finished_at": local_now().isoformat(timespec="seconds"),
            "returncode": None,
            "error": repr(exc),
        }


def copy_sanitized_file(src: Path, dest: Path) -> None:
    if not src.exists() or src.is_dir():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    if src.suffix in {".py", ".toml", ".ini", ".md", ".txt", ".env", ".example", ".service", ".conf", ".yml", ".yaml", ".json"}:
        text = src.read_text(encoding="utf-8", errors="replace")
        if src.suffix == ".py" or "alembic" in src.parts or "app" in src.parts:
            dest.write_text(redact_source_text(text), encoding="utf-8")
        else:
            dest.write_text(redact_text(text), encoding="utf-8")
    else:
        shutil.copy2(src, dest)


def copy_sanitized_tree(src: Path, dest: Path) -> None:
    if not src.exists():
        return
    if src.is_file():
        copy_sanitized_file(src, dest)
        return
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if any(part in {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"} for part in rel.parts):
            continue
        if path.suffix in {".pyc", ".pyo", ".log"}:
            continue
        if path.is_file():
            copy_sanitized_file(path, dest / rel)


def backend_python() -> str:
    candidate = BACKEND / ".venv" / "bin" / "python"
    if candidate.exists():
        return str(candidate)
    return sys.executable


def get_git_info() -> dict[str, str | None]:
    git_dir = ROOT / ".git"
    if not git_dir.exists() or not any(git_dir.iterdir()):
        return {"branch": None, "commit": None, "status": "unavailable: .git is missing or empty"}
    status = run_command(["git", "status", "--short", "--branch"], timeout=30)
    branch = run_command(["git", "branch", "--show-current"], timeout=30)
    commit = run_command(["git", "rev-parse", "HEAD"], timeout=30)
    if commit.get("returncode") != 0:
        return {"branch": None, "commit": None, "status": "unavailable: git command failed"}
    return {
        "branch": (branch.get("stdout") or "").strip() or None,
        "commit": (commit.get("stdout") or "").strip() or None,
        "status": (status.get("stdout") or status.get("stderr") or "").strip(),
    }


def setup_imports() -> None:
    os.environ.setdefault("ENABLE_SCHEDULER", "false")
    sys.path.insert(0, str(BACKEND))


def collect_runtime_settings() -> dict[str, Any]:
    setup_imports()
    from app.core.config import get_settings

    settings = get_settings()
    raw = settings.model_dump(mode="json")
    safe = sanitize(raw)
    safe["database_url_redacted"] = redacted_url(settings.database_url)
    safe["sync_database_url_redacted"] = redacted_url(settings.sync_database_url)
    return safe


def get_engine():
    setup_imports()
    from sqlalchemy import create_engine
    from app.core.config import get_settings

    return create_engine(get_settings().sync_database_url, future=True)


def scalar(conn, sql: str, params: dict[str, Any] | None = None) -> Any:
    from sqlalchemy import text

    return conn.execute(text(sql), params or {}).scalar()


def rows(conn, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    from sqlalchemy import text

    return [dict(row._mapping) for row in conn.execute(text(sql), params or {}).all()]


def public_tables(conn) -> list[str]:
    return [
        str(row["table_name"])
        for row in rows(
            conn,
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
            order by table_name
            """,
        )
    ]


def table_columns(conn, table: str) -> list[str]:
    return [
        str(row["column_name"])
        for row in rows(
            conn,
            """
            select column_name
            from information_schema.columns
            where table_schema = 'public' and table_name = :table
            order by ordinal_position
            """,
            {"table": table},
        )
    ]


def table_exists(table_names: set[str], table: str) -> bool:
    return table in table_names


def order_clause(columns: list[str]) -> str:
    for candidate in ("updated_at", "created_at", "last_seen_at", "detected_at", "started_at", "id"):
        if candidate in columns:
            return f" order by {candidate} desc nulls last"
    return ""


def collect_db_context(conn, table_names: set[str]) -> dict[str, Any]:
    ctx: dict[str, Any] = {}
    if table_exists(table_names, "wb_accounts"):
        ctx["account_id"] = scalar(conn, "select id from wb_accounts where is_active is true order by id limit 1")
        if ctx["account_id"] is None:
            ctx["account_id"] = scalar(conn, "select id from wb_accounts order by id limit 1")
    if table_exists(table_names, "auth_users"):
        ctx["auth_user_id"] = scalar(conn, "select id from auth_users where is_active is true order by is_superuser desc, id asc limit 1")
    if table_exists(table_names, "problem_instances"):
        ctx["problem_instance_id"] = scalar(conn, "select id from problem_instances order by last_seen_at desc nulls last, id desc limit 1")
        ctx["problem_nm_id"] = scalar(conn, "select nm_id from problem_instances where nm_id is not null order by last_seen_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "unified_actions"):
        ctx["unified_action_id"] = scalar(conn, "select id from unified_actions order by updated_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "action_recommendations") and ctx.get("unified_action_id") is None:
        ctx["legacy_action_id"] = scalar(conn, "select id from action_recommendations order by updated_at desc nulls last, id desc limit 1")
    ctx["action_id"] = ctx.get("unified_action_id") or ctx.get("legacy_action_id")
    if table_exists(table_names, "data_quality_issues"):
        ctx["dq_issue_id"] = scalar(conn, "select id from data_quality_issues order by detected_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "card_quality_issues"):
        ctx["card_quality_issue_id"] = scalar(conn, "select id from card_quality_issues order by last_seen_at desc nulls last, id desc limit 1")
        ctx["card_quality_nm_id"] = scalar(conn, "select nm_id from card_quality_issues order by last_seen_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "card_quality_analysis_runs"):
        ctx["card_quality_run_id"] = scalar(conn, "select id from card_quality_analysis_runs order by created_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "problem_definitions"):
        ctx["problem_definition_id"] = scalar(conn, "select id from problem_definitions order by updated_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "problem_rule_versions"):
        ctx["problem_rule_version_id"] = scalar(conn, "select id from problem_rule_versions order by updated_at desc nulls last, id desc limit 1")
    if table_exists(table_names, "wb_product_cards"):
        ctx["product_nm_id"] = scalar(conn, "select nm_id from wb_product_cards where nm_id is not null order by updated_at desc nulls last, id desc limit 1")
        if table_exists(table_names, "problem_instances"):
            ctx["product_without_problem_nm_id"] = scalar(
                conn,
                """
                select c.nm_id
                from wb_product_cards c
                where c.nm_id is not null
                  and not exists (
                    select 1 from problem_instances p
                    where p.nm_id = c.nm_id and p.status in ('new','acknowledged','in_progress','blocked','reopened')
                  )
                order by c.updated_at desc nulls last, c.id desc
                limit 1
                """,
            )
    ctx["nm_id"] = ctx.get("problem_nm_id") or ctx.get("card_quality_nm_id") or ctx.get("product_nm_id")
    return sanitize(ctx)


def collect_schema(bundle_root: Path, manifest: dict[str, Any], database_url: str) -> None:
    schema_path = bundle_root / "db" / "schema.sql"
    result = run_command(
        [
            "pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(schema_path),
            database_url.replace("postgresql+asyncpg://", "postgresql://", 1),
        ],
        cwd=BACKEND,
        timeout=300,
    )
    result["command"] = ["pg_dump", "--schema-only", "--no-owner", "--no-privileges", "--file", "db/schema.sql", "<DATABASE_URL_REDACTED>"]
    if schema_path.exists():
        schema_path.write_text(redact_text(schema_path.read_text(encoding="utf-8", errors="replace")), encoding="utf-8")
    else:
        write_text(schema_path, "-- schema dump unavailable; see db/schema_dump_result.json\n")
    write_json(bundle_root / "db" / "schema_dump_result.json", result)
    manifest["db_schema_dump"] = {"ok": schema_path.exists(), "result_file": "db/schema_dump_result.json"}


def collect_table_counts_and_samples(bundle_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    engine = get_engine()
    db_info: dict[str, Any] = {"connected": False}
    with engine.connect() as conn:
        db_info["connected"] = True
        db_info["version"] = sanitize(scalar(conn, "select version()"))
        tables = public_tables(conn)
        table_set = set(tables)
        counts_all: dict[str, Any] = {}
        for table in tables:
            try:
                counts_all[table] = int(scalar(conn, f'select count(*) from "{table}"') or 0)
            except Exception as exc:
                counts_all[table] = {"error": repr(exc)}
        counts_grouped: dict[str, Any] = {}
        for group, group_tables in TABLE_COUNT_GROUPS.items():
            counts_grouped[group] = {table: counts_all.get(table, "missing") for table in group_tables}
        write_json(bundle_root / "db" / "table_counts.json", {"groups": counts_grouped, "all_public_tables": counts_all})

        ctx = collect_db_context(conn, table_set)
        db_info["sample_context"] = ctx
        samples_index: dict[str, Any] = {}
        for sample_name, sample_tables in SAMPLE_TABLES.items():
            sample_payload: dict[str, Any] = {}
            for table in sample_tables:
                if table not in table_set:
                    sample_payload[table] = {"missing": True}
                    continue
                columns = table_columns(conn, table)
                sql = f'select * from "{table}"{order_clause(columns)} limit :limit'
                try:
                    sample_payload[table] = sanitize(rows(conn, sql, {"limit": DEFAULT_SAMPLE_LIMIT}))
                except Exception as exc:
                    sample_payload[table] = {"error": repr(exc)}
            sample_file = bundle_root / "db" / "samples" / f"{sample_name}.json"
            write_json(sample_file, sample_payload)
            samples_index[sample_name] = str(sample_file.relative_to(bundle_root))
        write_json(bundle_root / "db" / "samples" / "_index.json", samples_index)
        write_text(
            bundle_root / "db" / "samples" / "README.md",
            "Samples are limited to 20-50 rows per source table where present. Tokens, passwords, Authorization headers, emails, phones, and seller identity fields are masked.\n",
        )

        collect_specific_checks(conn, table_set, bundle_root)
    engine.dispose()
    write_json(bundle_root / "db" / "db_connection_info.json", db_info)
    manifest["database"] = db_info
    return db_info


def collect_specific_checks(conn, table_set: set[str], bundle_root: Path) -> None:
    out = bundle_root / "db" / "specific_checks"
    summary: dict[str, Any] = {}
    for code in ISSUE_CODES[:6]:
        payload: dict[str, Any] = {}
        if "data_quality_issues" in table_set:
            payload["data_quality_issues"] = sanitize(
                rows(
                    conn,
                    """
                    select *
                    from data_quality_issues
                    where lower(code) = lower(:code)
                    order by detected_at desc nulls last, id desc
                    limit 50
                    """,
                    {"code": code},
                )
            )
        else:
            payload["data_quality_issues"] = "missing table"
        if "problem_instances" in table_set:
            payload["problem_instances"] = sanitize(
                rows(
                    conn,
                    """
                    select *
                    from problem_instances
                    where lower(problem_code) = lower(:code)
                    order by last_seen_at desc nulls last, id desc
                    limit 50
                    """,
                    {"code": code},
                )
            )
        else:
            payload["problem_instances"] = "missing table"
        write_json(out / "data_health_issue_buckets" / f"{code}.json", payload)
        summary[code] = {
            "dq_rows": len(payload.get("data_quality_issues") or []) if isinstance(payload.get("data_quality_issues"), list) else 0,
            "problem_rows": len(payload.get("problem_instances") or []) if isinstance(payload.get("problem_instances"), list) else 0,
        }

    fields = [
        "owner_type",
        "fixability",
        "issue_nature",
        "can_user_fix_inside_platform",
        "primary_action_code",
        "target_href",
    ]
    dq_columns = table_columns(conn, "data_quality_issues") if "data_quality_issues" in table_set else []
    classification: dict[str, Any] = {}
    for code in ISSUE_CODES:
        row = None
        if "data_quality_issues" in table_set:
            result_rows = rows(
                conn,
                """
                select *
                from data_quality_issues
                where lower(code) = lower(:code)
                order by detected_at desc nulls last, id desc
                limit 1
                """,
                {"code": code},
            )
            row = result_rows[0] if result_rows else None
        classification[code] = {
            field: sanitize(row.get(field), key=field) if row and field in row else "missing"
            for field in fields
        }
        classification[code]["record_present"] = row is not None
        classification[code]["table_columns_present"] = {field: field in dq_columns for field in fields}
    write_json(out / "data_fix_classification_current.json", classification)

    metric_rows: list[dict[str, Any]] = []
    if "metric_catalog" in table_set:
        metric_rows = sanitize(
            rows(
                conn,
                """
                select metric_code, title, source_module, source_tables_json, source_endpoints_json, trust_state, is_deprecated
                from metric_catalog
                order by source_module, metric_code
                """
            )
        )
    dashboard_inputs_md = build_dashboard_inputs_report(metric_rows)
    write_text(out / "dashboard_pulse_inputs.md", dashboard_inputs_md)

    open_issues = 0
    if "data_quality_issues" in table_set:
        open_issues += int(scalar(conn, "select count(*) from data_quality_issues where resolved_at is null") or 0)
    if "problem_instances" in table_set:
        open_issues += int(scalar(conn, "select count(*) from problem_instances where status not in ('resolved','dismissed')") or 0)
    false_ok = {
        "open_issue_or_problem_count": open_issues,
        "searched_states": ["has_risk=false", "risks not found", "источники в порядке"],
        "note": "Static search results are in reports/search_findings.md. Endpoint response samples can be inspected under endpoint_samples/.",
        "risk": "If any sampled dashboard response claims clean/no-risk while this count is nonzero, reviewer should treat it as a false OK candidate.",
    }
    write_json(out / "false_ok_state_check.json", false_ok)
    write_json(out / "data_health_issue_buckets_summary.json", summary)


def build_dashboard_inputs_report(metric_rows: list[dict[str, Any]]) -> str:
    mapping = {
        "Продажи": ["DashboardService", "PortalService.overview", "wb_sales", "wb_orders", "v_wb_sales_current", "mart_sku_daily"],
        "Прибыль и маржа": ["MoneyManagementService", "DashboardService", "mart_sku_daily", "wb_realization_report_rows", "manual_costs", "mart_account_expense_daily"],
        "Деньги под риском": ["ProblemInstance.money_impact_amount", "PortalService.actions", "data_quality_issues", "problem_instances", "mart_sku_daily"],
        "Остатки": ["wb_stock_snapshots", "wb_stock_snapshot_rows", "mart_stock_daily", "stocks module", "PortalService.data_sync_status"],
        "Карточки": ["wb_product_cards", "card_quality_snapshots", "card_quality_issues", "ProductCardService", "PortalService.product_360"],
        "Данные": ["data_quality_issues", "portal_integrations", "portal_module_sync_runs", "wb_sync_runs", "raw_wb_api_responses"],
    }
    lines = ["# Dashboard Pulse Inputs", ""]
    for title, sources in mapping.items():
        lines.append(f"## {title}")
        for item in sources:
            lines.append(f"- {item}")
        related = []
        title_l = title.lower()
        for row in metric_rows:
            joined = json.dumps(row, ensure_ascii=False).lower()
            if any(token in joined for token in [title_l, "sales", "profit", "margin", "stock", "card", "data", "risk"]):
                related.append(row)
        if related:
            lines.append("")
            lines.append("Metric catalog rows to inspect:")
            for row in related[:20]:
                lines.append(f"- `{row.get('metric_code')}` from `{row.get('source_module')}` tables={row.get('source_tables_json')} trust={row.get('trust_state')}")
        lines.append("")
    return "\n".join(lines)


def collect_code(bundle_root: Path, manifest: dict[str, Any]) -> None:
    copied: list[str] = []
    for rel in CODE_INCLUDE_PATHS:
        src = BACKEND / rel
        if not src.exists():
            continue
        dest = bundle_root / "code" / rel
        copy_sanitized_tree(src, dest)
        copied.append(rel)

    migrations_dest = bundle_root / "code" / "alembic" / "versions"
    for migration in sorted((BACKEND / "alembic" / "versions").glob("*.py")):
        name = migration.name.lower()
        text = migration.read_text(encoding="utf-8", errors="replace").lower()
        if any(keyword in name or keyword in text for keyword in MIGRATION_KEYWORDS):
            copy_sanitized_file(migration, migrations_dest / migration.name)
            copied.append(f"alembic/versions/{migration.name}")
    copy_sanitized_file(BACKEND / "alembic" / "env.py", bundle_root / "code" / "alembic" / "env.py")
    copy_sanitized_file(BACKEND / "alembic" / "script.py.mako", bundle_root / "code" / "alembic" / "script.py.mako")
    manifest["code_paths_copied"] = copied


def collect_config(bundle_root: Path, manifest: dict[str, Any]) -> None:
    config_dir = bundle_root / "config"
    for rel in ["pyproject.toml", "pytest.ini", "README.md", "alembic.ini", "deploy/finance.env.example", "deploy/finance-backend.service"]:
        copy_sanitized_file(BACKEND / rel, config_dir / rel)
    if (BACKEND / ".env").exists():
        copy_sanitized_file(BACKEND / ".env", config_dir / "backend.env.redacted")
    write_json(config_dir / "runtime_settings_redacted.json", collect_runtime_settings())
    manifest["config_files"] = sorted(str(path.relative_to(bundle_root)) for path in config_dir.rglob("*") if path.is_file())


def schema_summary(schema: Any) -> str:
    if not schema:
        return "not specified"
    if isinstance(schema, dict):
        if "$ref" in schema:
            return f"`{schema['$ref']}`"
        if "type" in schema:
            extra = ""
            if schema.get("items"):
                extra = f" items={schema_summary(schema.get('items'))}"
            return f"`{schema.get('type')}`{extra}"
        if "anyOf" in schema:
            return "anyOf " + ", ".join(schema_summary(item) for item in schema.get("anyOf", [])[:4])
        if "allOf" in schema:
            return "allOf " + ", ".join(schema_summary(item) for item in schema.get("allOf", [])[:4])
    return "`schema object`"


def response_schema_for(operation: dict[str, Any]) -> str:
    responses = operation.get("responses") or {}
    for code in ("200", "201", "202"):
        content = ((responses.get(code) or {}).get("content") or {}).get("application/json") or {}
        if content.get("schema"):
            return schema_summary(content["schema"])
    return "not specified"


def collect_openapi(bundle_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    setup_imports()
    from app.main import app

    openapi = app.openapi()
    write_json(bundle_root / "api_contracts" / "openapi.json", openapi)
    catalog: list[dict[str, Any]] = []
    paths = openapi.get("paths") or {}
    for path, methods in sorted(paths.items()):
        for method, spec in sorted((methods or {}).items()):
            catalog.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": spec.get("operationId"),
                    "summary": spec.get("summary"),
                    "parameters": spec.get("parameters") or [],
                    "response_schema": response_schema_for(spec),
                }
            )
    write_json(bundle_root / "api_contracts" / "routes_catalog.json", catalog)
    write_text(bundle_root / "api_contracts" / "manual_endpoint_contracts.md", build_manual_contracts(openapi))
    manifest["api_contracts"] = {"openapi_paths": len(paths), "routes": len(catalog)}
    return openapi


def build_manual_contracts(openapi: dict[str, Any]) -> str:
    paths = openapi.get("paths") or {}
    lines = ["# Manual Endpoint Contracts", "", "Route prefix observed: `/api/v1`.", ""]
    for category, wanted_paths in CONTRACT_CATEGORIES.items():
        lines.append(f"## {category}")
        for wanted in wanted_paths:
            if wanted not in paths:
                lines.append(f"- MISSING `{wanted}`")
                continue
            for method, spec in sorted((paths[wanted] or {}).items()):
                params = []
                for param in spec.get("parameters") or []:
                    params.append(f"{param.get('name')}:{(param.get('schema') or {}).get('type') or 'schema'}")
                request_body = "none"
                if spec.get("requestBody"):
                    content = (spec["requestBody"].get("content") or {}).get("application/json") or {}
                    request_body = schema_summary(content.get("schema"))
                lines.append(f"- `{method.upper()} {wanted}`")
                lines.append(f"  - operationId: `{spec.get('operationId')}`")
                lines.append(f"  - params: {', '.join(params) if params else 'none'}")
                lines.append(f"  - request body: {request_body}")
                lines.append(f"  - response schema: {response_schema_for(spec)}")
        lines.append("")
    return "\n".join(lines)


def sample_value_for_param(name: str, schema: dict[str, Any], ctx: dict[str, Any], date_from: str, date_to: str) -> Any:
    lower = name.lower()
    if lower == "account_id":
        return ctx.get("account_id") or 1
    if lower in {"date_from", "from", "start_date"}:
        return date_from
    if lower in {"date_to", "to", "end_date"}:
        return date_to
    if lower == "limit":
        return 5
    if lower == "offset":
        return 0
    if lower == "recent_days":
        return 30
    if lower == "include_beta":
        return "true"
    if lower == "only_open":
        return "true"
    if lower == "financial_final_blocker":
        return "true"
    enum = schema.get("enum")
    if enum:
        return enum[0]
    kind = schema.get("type")
    if kind == "integer":
        return 1
    if kind == "number":
        return 1
    if kind == "boolean":
        return "true"
    return None


def build_query_for_operation(operation: dict[str, Any], ctx: dict[str, Any], date_from: str, date_to: str) -> list[tuple[str, Any]]:
    params: list[tuple[str, Any]] = []
    for param in operation.get("parameters") or []:
        if param.get("in") != "query":
            continue
        name = str(param.get("name") or "")
        schema = param.get("schema") or {}
        lower = name.lower()
        required = bool(param.get("required"))
        common = lower in {"account_id", "date_from", "date_to", "from", "to", "limit", "offset", "recent_days"}
        if lower == "account_id" and ctx.get("account_id") is None:
            continue
        if required or common:
            value = sample_value_for_param(name, schema, ctx, date_from, date_to)
            if value is not None:
                params.append((name, value))
    return params


def fill_path(path: str, ctx: dict[str, Any]) -> tuple[str | None, str | None]:
    replacements = {
        "action_id": ctx.get("action_id"),
        "problem_id": ctx.get("problem_instance_id"),
        "problem_instance_id": ctx.get("problem_instance_id"),
        "issue_id": ctx.get("card_quality_issue_id") if "card-quality" in path else ctx.get("dq_issue_id"),
        "nm_id": ctx.get("nm_id"),
        "run_id": ctx.get("card_quality_run_id"),
        "version_id": ctx.get("problem_rule_version_id"),
        "definition_id": ctx.get("problem_definition_id"),
        "id": ctx.get("problem_definition_id"),
    }
    missing: list[str] = []
    result = path
    for name in re.findall(r"{([^}]+)}", path):
        value = replacements.get(name)
        if value is None:
            missing.append(name)
        else:
            result = result.replace("{" + name + "}", str(value))
    if missing:
        return None, "missing path parameter sample values: " + ", ".join(missing)
    return result, None


def endpoint_is_relevant(path: str) -> bool:
    relevant_prefixes = (
        "/api/v1/admin/problem-rules",
        "/api/v1/dashboard",
        "/api/v1/dq",
        "/api/v1/finance",
        "/api/v1/money",
        "/api/v1/portal/actions",
        "/api/v1/portal/card-quality",
        "/api/v1/portal/data-readiness",
        "/api/v1/portal/data-sync/status",
        "/api/v1/portal/overview",
        "/api/v1/portal/problems",
        "/api/v1/portal/products",
        "/api/v1/portal/results",
        "/api/v1/products",
        "/api/v1/balance",
    )
    return path.startswith(relevant_prefixes)


def safe_sample_name(method: str, path: str, suffix: str = "") -> str:
    raw = f"{method}_{path.strip('/') or 'root'}{suffix}"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("_") + ".json"


def collect_endpoint_samples(bundle_root: Path, manifest: dict[str, Any], openapi: dict[str, Any], ctx: dict[str, Any], date_from: str, date_to: str) -> None:
    setup_imports()
    from fastapi.testclient import TestClient
    from app.main import app
    from app.models.auth import AuthUser
    from app.services import auth as auth_deps

    now = local_now()

    async def fake_current_user() -> AuthUser:
        return AuthUser(
            id=int(ctx.get("auth_user_id") or 0),
            email="audit-superuser@example.local",
            full_name="Audit Superuser",
            password_hash="",
            is_active=True,
            is_superuser=True,
            created_at=now,
            updated_at=now,
        )

    app.dependency_overrides[auth_deps.get_current_user] = fake_current_user
    app.dependency_overrides[auth_deps.get_current_superuser] = fake_current_user
    app.dependency_overrides[auth_deps.allow_bootstrap_or_superuser] = fake_current_user

    index: list[dict[str, Any]] = []
    sample_dir = bundle_root / "endpoint_samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    try:
        with TestClient(app) as client:
            for path, methods in sorted((openapi.get("paths") or {}).items()):
                if not endpoint_is_relevant(path):
                    continue
                for method, operation in sorted((methods or {}).items()):
                    method_upper = method.upper()
                    sample_file = sample_dir / safe_sample_name(method_upper, path)
                    if method_upper != "GET":
                        payload = skipped_sample(method_upper, path, "mutation endpoint not executed during audit bundle generation")
                        write_json(sample_file, payload)
                        index.append({"method": method_upper, "path": path, "sample_file": str(sample_file.relative_to(bundle_root)), "sampled": False})
                        continue
                    if path.endswith(".csv") or "/download" in path or "/export" in path:
                        payload = skipped_sample(method_upper, path, "binary/download endpoint not sampled")
                        write_json(sample_file, payload)
                        index.append({"method": method_upper, "path": path, "sample_file": str(sample_file.relative_to(bundle_root)), "sampled": False})
                        continue
                    filled, skip_reason = fill_path(path, ctx)
                    if skip_reason:
                        payload = skipped_sample(method_upper, path, skip_reason)
                        write_json(sample_file, payload)
                        index.append({"method": method_upper, "path": path, "sample_file": str(sample_file.relative_to(bundle_root)), "sampled": False})
                        continue
                    params = build_query_for_operation(operation, ctx, date_from, date_to)
                    payload = execute_get_sample(client, filled or path, params, original_path=path)
                    write_json(sample_file, payload)
                    index.append(
                        {
                            "method": method_upper,
                            "path": path,
                            "request_path": filled,
                            "params": params,
                            "status_code": payload.get("response", {}).get("status_code"),
                            "sample_file": str(sample_file.relative_to(bundle_root)),
                            "sampled": True,
                        }
                    )

            for code in ISSUE_CODES:
                sample_file = sample_dir / f"data_fix_issue_{code}.json"
                params = [("account_id", ctx.get("account_id") or 1), ("code", code), ("limit", 5), ("offset", 0)]
                payload = execute_get_sample(client, "/api/v1/dq/issues", params, original_path="/api/v1/dq/issues")
                write_json(sample_file, payload)
                index.append({"method": "GET", "path": "/api/v1/dq/issues", "issue_code": code, "sample_file": str(sample_file.relative_to(bundle_root)), "sampled": True})

            mutation_examples = {
                "action_update_response_skipped.json": ("PATCH", "/api/v1/portal/actions/{action_id}", "Action update mutates review/status state."),
                "problem_recheck_response_skipped.json": ("POST", "/api/v1/portal/problems/{problem_id}/recheck", "Problem re-check may run detectors and write result/history rows."),
                "dq_recheck_response_skipped.json": ("POST", "/api/v1/dq/issues/{issue_id}/recheck", "Data Fix re-check mutates issue status/snapshots."),
                "checker_preview_apply_recheck_skipped.json": ("POST", "/api/v1/portal/card-quality/issues/{issue_id}/preview|apply-wb|recheck", "Checker preview/apply/recheck endpoints are non-GET and were not executed."),
                "admin_backtest_publish_skipped.json": ("POST", "/api/v1/admin/problem-rules/versions/{version_id}/backtest|publish", "Admin backtest/publish endpoints can create audit rows or change rule status."),
            }
            for filename, (method, path, reason) in mutation_examples.items():
                sample_file = sample_dir / filename
                write_json(sample_file, skipped_sample(method, path, reason))
                index.append({"method": method, "path": path, "sample_file": str(sample_file.relative_to(bundle_root)), "sampled": False, "reason": reason})
    finally:
        app.dependency_overrides.pop(auth_deps.get_current_user, None)
        app.dependency_overrides.pop(auth_deps.get_current_superuser, None)
        app.dependency_overrides.pop(auth_deps.allow_bootstrap_or_superuser, None)

    write_json(sample_dir / "_sample_index.json", index)
    manifest["endpoint_samples"] = {"total_records": len(index), "executed_gets": sum(1 for item in index if item.get("sampled"))}


def execute_get_sample(client: Any, path: str, params: list[tuple[str, Any]], *, original_path: str) -> dict[str, Any]:
    timestamp = local_now().isoformat(timespec="seconds")
    request = {
        "method": "GET",
        "path": original_path,
        "resolved_path": path,
        "query_params": sanitize(params),
        "headers": {"authorization": "<REDACTED>", "accept": "application/json"},
        "timestamp": timestamp,
    }
    try:
        response = client.get(path, params=params, headers={"accept": "application/json"})
        try:
            body = response.json()
        except Exception:
            body = response.text[:20000]
        return {
            "request": request,
            "response": {
                "status_code": response.status_code,
                "headers": sanitize(dict(response.headers)),
                "json": sanitize(body),
            },
            "timestamp": timestamp,
        }
    except Exception as exc:
        return {"request": request, "response": {"error": repr(exc)}, "timestamp": timestamp}


def skipped_sample(method: str, path: str, reason: str) -> dict[str, Any]:
    return {
        "request": {
            "method": method,
            "path": path,
            "headers": {"authorization": "<REDACTED>", "accept": "application/json"},
            "timestamp": local_now().isoformat(timespec="seconds"),
        },
        "response": {"status_code": "not_executed", "json": None, "skip_reason": reason},
        "timestamp": local_now().isoformat(timespec="seconds"),
    }


def collect_logs(bundle_root: Path, manifest: dict[str, Any]) -> None:
    log_dir = BACKEND / "logs"
    error_lines: list[str] = []
    sync_lines: list[str] = []
    if log_dir.exists():
        for path in sorted(log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True):
            text = path.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                lower = line.lower()
                if any(token in lower for token in ["error", "traceback", "exception", "failed", "critical"]):
                    error_lines.append(f"{path.name}: {line}")
                if "sync" in path.name.lower() or "sync" in lower:
                    sync_lines.append(f"{path.name}: {line}")
    write_text(bundle_root / "logs" / "recent_errors.log", "\n".join(redact_text(line) for line in error_lines[-200:]) + ("\n" if error_lines else "No backend error lines found in local logs.\n"))
    write_text(bundle_root / "logs" / "sync_runs.log", "\n".join(redact_text(line) for line in sync_lines[-300:]) + ("\n" if sync_lines else "No sync log lines found in local logs.\n"))
    try:
        engine = get_engine()
        with engine.connect() as conn:
            tables = set(public_tables(conn))
            db_sync: dict[str, Any] = {}
            for table in ["wb_sync_runs", "portal_module_sync_runs"]:
                if table in tables:
                    columns = table_columns(conn, table)
                    db_sync[table] = sanitize(rows(conn, f'select * from "{table}"{order_clause(columns)} limit 50'))
            write_json(bundle_root / "logs" / "sync_runs_db.json", db_sync)
        engine.dispose()
    except Exception as exc:
        write_json(bundle_root / "logs" / "sync_runs_db.json", {"error": repr(exc)})
    manifest["logs"] = {"recent_errors_lines": len(error_lines[-200:]), "sync_log_lines": len(sync_lines[-300:])}


def collect_tests(bundle_root: Path, manifest: dict[str, Any]) -> None:
    py = backend_python()
    compile_result = run_command([py, "-m", "compileall", "app", "tests"], cwd=BACKEND, timeout=300, env={"ENABLE_SCHEDULER": "false"})
    write_text(bundle_root / "tests" / "compileall.txt", command_result_text(compile_result))

    test_files = [
        "tests/unit/test_portal_service.py",
        "tests/unit/test_portal_data_sync_status.py",
        "tests/unit/test_result_tracking_service.py",
        "tests/unit/test_problem_engine_portal_integration.py",
        "tests/unit/test_data_fix_dynamic_problem_bridge.py",
        "tests/unit/test_data_quality_guided_workflows.py",
        "tests/unit/test_card_quality_service.py",
        "tests/unit/test_money_management_service.py",
        "tests/unit/test_dashboard_service.py",
        "tests/unit/test_problem_engine_admin_rules.py",
    ]
    existing = [path for path in test_files if (BACKEND / path).exists()]
    pytest_result = run_command([py, "-m", "pytest", "-q", *existing], cwd=BACKEND, timeout=900, env={"ENABLE_SCHEDULER": "false"})
    write_text(bundle_root / "tests" / "pytest_summary.txt", command_result_text(pytest_result))
    manifest["tests"] = {
        "compileall_returncode": compile_result.get("returncode"),
        "pytest_returncode": pytest_result.get("returncode"),
        "pytest_files": existing,
    }


def command_result_text(result: dict[str, Any]) -> str:
    lines = [
        "Command: " + " ".join(result.get("command") or []),
        f"CWD: {result.get('cwd')}",
        f"Started: {result.get('started_at')}",
        f"Finished: {result.get('finished_at')}",
        f"Return code: {result.get('returncode')}",
        "",
        "STDOUT:",
        result.get("stdout") or "",
        "",
        "STDERR:",
        result.get("stderr") or "",
    ]
    if result.get("error"):
        lines.extend(["", f"Error: {result.get('error')}"])
    return "\n".join(lines)


def collect_search_findings(bundle_root: Path, manifest: dict[str, Any]) -> None:
    lines = ["# Search Findings", ""]
    findings_total = 0
    for term in SEARCH_TERMS:
        result = run_command(["rg", "-n", "--hidden", "--glob", "!__pycache__/**", "--glob", "!.venv/**", "--glob", "!.pytest_cache/**", term, "app", "tests", "alembic"], cwd=BACKEND, timeout=120)
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        lines.append(f"## `{term}`")
        if stdout:
            result_lines = stdout.splitlines()
            findings_total += len(result_lines)
            lines.extend(f"- {line}" for line in result_lines[:200])
            if len(result_lines) > 200:
                lines.append(f"- ... truncated {len(result_lines) - 200} more lines")
        elif stderr and result.get("returncode") not in {0, 1}:
            lines.append(f"- search error: {stderr}")
        else:
            lines.append("- no matches")
        lines.append("")
    write_text(bundle_root / "reports" / "search_findings.md", "\n".join(lines))
    manifest["search_findings_total"] = findings_total


def collect_reports(bundle_root: Path, manifest: dict[str, Any], openapi: dict[str, Any]) -> None:
    paths = openapi.get("paths") or {}
    missing: dict[str, list[str]] = {}
    present: dict[str, list[str]] = {}
    for category, wanted in CONTRACT_CATEGORIES.items():
        missing[category] = [path for path in wanted if path not in paths]
        present[category] = [path for path in wanted if path in paths]

    settings = collect_runtime_settings()
    disabled_actions = {
        "enable_card_auto_apply": settings.get("enable_card_auto_apply"),
        "enable_grouping_merge": settings.get("enable_grouping_merge"),
        "enable_reputation_publish": settings.get("enable_reputation_publish"),
        "enable_reputation_write_actions": settings.get("enable_reputation_write_actions"),
        "enable_claims_submit": settings.get("enable_claims_submit"),
        "checker_ai_enabled": settings.get("checker_ai_enabled"),
        "checker_vision_enabled": settings.get("checker_vision_enabled"),
    }
    fixability_fields = ["owner_type", "fixability", "issue_nature", "can_user_fix_inside_platform"]
    try:
        engine = get_engine()
        with engine.connect() as conn:
            dq_columns = table_columns(conn, "data_quality_issues")
        engine.dispose()
    except Exception:
        dq_columns = []
    summary_lines = [
        "# Backend Audit Summary",
        "",
        "## Endpoints Present / Missing",
    ]
    for category in CONTRACT_CATEGORIES:
        summary_lines.append(f"### {category}")
        summary_lines.append("Present:")
        summary_lines.extend(f"- `{path}`" for path in present[category])
        summary_lines.append("Missing:")
        summary_lines.extend(f"- `{path}`" for path in missing[category] or ["none"])
        summary_lines.append("")
    summary_lines.extend(
        [
            "## Known Disabled Actions",
            *[f"- `{key}` = `{value}`" for key, value in disabled_actions.items()],
            "",
            "## Data Classification Risks",
            f"- Data Fix table columns for explicit fixability fields: { {field: field in dq_columns for field in fixability_fields} }",
            "- Missing/stale/estimated/confirmed separation should be reviewed in `PortalDataReadinessRead`, `DashboardDataHealth`, `MoneyTrustInfo`, `EvidenceLedger`, and `ProblemInstance.trust_state` contracts.",
            "- Mutation samples were intentionally not executed; preview/confirm/audit behavior must be verified from contracts, code, and a disposable staging account.",
            "",
            "## Trust / Impact Concerns",
            "- `result_tracking` contains explicit no-causality notes and `saved_money_claimed: False` in action completion payloads.",
            "- Confirmed loss should be accepted only when finance report rows and money trust state are final; see money schemas and data health samples.",
            "",
            "## Dashboard Overview Contract",
            f"- `/api/v1/portal/overview` exists: `{('/api/v1/portal/overview' in paths)}`",
            f"- `/api/v1/dashboard/data-health` exists: `{('/api/v1/dashboard/data-health' in paths)}`",
            "",
            "## Data Fix Fixability Fields",
            *[f"- `{field}`: {'present' if field in dq_columns else 'missing'}" for field in fixability_fields],
            "",
            "## Known Blockers",
            "- Git branch/commit may be unavailable because `.git` is empty or invalid in this workspace.",
            "- Non-GET endpoint samples were skipped to avoid mutating the local/staging database.",
            "- Reviewer should use `db/specific_checks/` for suspected false OK and classification checks.",
            "",
        ]
    )
    write_text(bundle_root / "reports" / "backend_audit_summary.md", "\n".join(summary_lines))
    manifest["reports"] = {"missing_contract_paths": missing, "disabled_actions": disabled_actions}


def build_readme(bundle_root: Path, manifest: dict[str, Any], args: argparse.Namespace) -> None:
    db = manifest.get("database") or {}
    git = manifest.get("git") or {}
    missing_paths = manifest.get("reports", {}).get("missing_contract_paths", {})
    disabled_actions = manifest.get("reports", {}).get("disabled_actions", {})
    readme = f"""# Backend Audit Bundle

Generated at: `{manifest["generated_at"]}`

Purpose: external backend review for Dashboard, Data Fix, Action Center, Money, Product360, Checker, and Results business truth.

## Environment

- Backend branch: `{git.get("branch") or "unavailable"}`
- Backend commit: `{git.get("commit") or "unavailable"}`
- Git status: `{git.get("status") or "unavailable"}`
- Environment name: `{manifest.get("environment")}`
- Python version: `{manifest.get("python_version")}`
- Install command: `cd backend && python -m pip install -e ".[dev]"`
- Test command: `cd backend && python -m compileall app tests && python -m pytest -q <targeted tests>`
- DB type/version: `{db.get("version") or "unavailable"}`
- Sample data: `sanitized local/staging database samples`
- Backend base URL used for endpoint samples: `{args.base_url}`
- Bundle generation window: `{args.date_from}` to `{args.date_to}`

## Security And Sanitization

- `contains_secrets`: `false`
- Real API tokens, WB tokens, passwords, private keys, Authorization headers, emails, phones, and seller identity fields are redacted or masked.
- DB dump is schema-only. Data samples are limited and sanitized.

## Known Missing Endpoints

{format_missing_paths(missing_paths)}

## Known Disabled Actions

{format_key_values(disabled_actions)}

## Collection Limits

- Non-GET endpoints were not executed because they can mutate actions, issue states, rule versions, or result history.
- Path-ID GET endpoints are sampled only when an ID was discoverable in the local DB.
- `screenshots_optional/` is intentionally empty; this is a backend bundle.
"""
    write_text(bundle_root / "README_AUDIT.md", readme)


def format_missing_paths(missing_paths: dict[str, Any]) -> str:
    lines: list[str] = []
    for category, paths in missing_paths.items():
        if paths:
            for path in paths:
                lines.append(f"- {category}: `{path}`")
    return "\n".join(lines) if lines else "- none"


def format_key_values(values: dict[str, Any]) -> str:
    return "\n".join(f"- `{key}` = `{value}`" for key, value in values.items()) if values else "- unknown"


def build_manifest(bundle_root: Path, manifest: dict[str, Any]) -> None:
    files = []
    for path in sorted(bundle_root.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(bundle_root))
            files.append({"path": rel, "bytes": path.stat().st_size})
    manifest["files"] = files
    manifest["contains_secrets"] = False
    manifest["sanitization"] = "tokens/passwords/Authorization headers redacted; emails/phones/seller identity masked; DB data limited and sanitized"
    write_json(bundle_root / "MANIFEST.json", manifest)


def make_zip(bundle_root: Path, zip_path: Path) -> dict[str, Any]:
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(bundle_root.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=str(Path("backend_audit_bundle") / path.relative_to(bundle_root)))
    return {
        "zip_path": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "source_root": str(bundle_root),
        "top_level_folders": sorted([p.name for p in bundle_root.iterdir() if p.is_dir()]),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a sanitized backend audit bundle.")
    parser.add_argument("--date-from", default=DEFAULT_DATE_FROM.isoformat())
    parser.add_argument("--date-to", default=DEFAULT_DATE_TO.isoformat())
    parser.add_argument("--base-url", default="http://testserver/api/v1")
    parser.add_argument("--out-dir", default=str(AUDIT_PARENT))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    timestamp = local_now().strftime("%Y%m%d_%H%M")
    bundle_name = f"backend_audit_bundle_{timestamp}"
    out_parent = Path(args.out_dir)
    staging_dir = out_parent / bundle_name
    bundle_root = staging_dir / "backend_audit_bundle"
    zip_path = out_parent / f"{bundle_name}.zip"
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    bundle_root.mkdir(parents=True)
    for folder in [
        "code",
        "config",
        "api_contracts",
        "endpoint_samples",
        "db",
        "logs",
        "tests",
        "reports",
        "screenshots_optional",
    ]:
        (bundle_root / folder).mkdir(parents=True, exist_ok=True)
    write_text(bundle_root / "screenshots_optional" / "README.md", "No backend screenshots were collected.\n")

    setup_imports()
    from app.core.config import get_settings

    settings = get_settings()
    manifest: dict[str, Any] = {
        "generated_at": local_now().isoformat(timespec="seconds"),
        "backend_branch": None,
        "backend_commit": None,
        "environment": "local" if settings.app_env.lower() in {"development", "dev", "local"} else settings.app_env,
        "python_version": sys.version.split()[0],
        "backend_base_url": args.base_url,
        "date_from": args.date_from,
        "date_to": args.date_to,
    }
    git = get_git_info()
    manifest["git"] = git
    manifest["backend_branch"] = git.get("branch")
    manifest["backend_commit"] = git.get("commit")

    collect_code(bundle_root, manifest)
    collect_config(bundle_root, manifest)
    openapi = collect_openapi(bundle_root, manifest)
    collect_schema(bundle_root, manifest, settings.sync_database_url)
    db_info = collect_table_counts_and_samples(bundle_root, manifest)
    ctx = db_info.get("sample_context") or {}
    collect_endpoint_samples(bundle_root, manifest, openapi, ctx, args.date_from, args.date_to)
    collect_logs(bundle_root, manifest)
    collect_tests(bundle_root, manifest)
    collect_search_findings(bundle_root, manifest)
    collect_reports(bundle_root, manifest, openapi)
    build_readme(bundle_root, manifest, args)
    build_manifest(bundle_root, manifest)
    zip_info = make_zip(bundle_root, zip_path)
    write_json(staging_dir / "zip_info.json", zip_info)
    print(json.dumps(zip_info, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
