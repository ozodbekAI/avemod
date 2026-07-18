#!/usr/bin/env python3
"""Export DB/schema evidence for a full page audit bundle."""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import re
import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect, select, text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.core.db import Base  # noqa: E402
import app.models as models_pkg  # noqa: E402

REDACTED = "<REDACTED>"
SENSITIVE_NAME_RE = re.compile(
    r"(token|authorization|password|secret|api_key|jwt|cookie|email|phone|address|buyer|customer|passport|encrypted|credential|refresh|fio|full_name|contact)",
    re.IGNORECASE,
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_+/=-]{48,}\b")

RELEVANT_TABLES_BY_AREA: dict[str, list[str]] = {
    "action_center": [
      "unified_actions",
      "problem_instances",
      "problem_instance_history",
      "result_events",
    ],
    "problem_rules": [
      "problem_definitions",
      "problem_rule_versions",
      "problem_metrics",
      "problem_rule_test_runs",
      "problem_evaluation_run_logs",
    ],
    "data_fix_and_costs": [
      "data_quality_issues",
      "manual_costs",
      "manual_cost_imports",
      "manual_cost_import_rows",
    ],
    "product_and_checker": [
      "product_cards",
      "card_quality_runs",
      "card_quality_issues",
      "card_quality_fixed_files",
    ],
    "commerce_sources": [
      "wb_accounts",
      "wb_orders",
      "wb_sales",
      "wb_stocks",
      "wb_realization_report_rows",
      "wb_ad_campaigns",
      "wb_ad_stats",
      "prices",
      "sync_runs",
      "sync_cursors",
    ],
    "portal_surfaces": [
      "ab_tests",
      "claims_cases",
      "photo_projects",
      "grouping_recommendations",
      "stock_control_runs",
      "reputation_items",
    ],
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def redact_string(value: str) -> str:
    value = JWT_RE.sub(REDACTED, value)
    value = EMAIL_RE.sub(REDACTED, value)
    value = LONG_SECRET_RE.sub(REDACTED, value)
    return value


def sanitize(value: Any, key: str | None = None) -> Any:
    if key and SENSITIVE_NAME_RE.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(k): sanitize(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_string(value)
    return value


def import_model_modules() -> list[str]:
    imported: list[str] = []
    for module in pkgutil.iter_modules(models_pkg.__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"app.models.{module.name}")
        imported.append(f"app.models.{module.name}")
    return sorted(imported)


def schema_inventory() -> dict[str, Any]:
    imported_modules = import_model_modules()
    tables: dict[str, Any] = {}
    for table_name, table in sorted(Base.metadata.tables.items()):
        tables[table_name] = {
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                    "unique": column.unique,
                    "index": column.index,
                    "default": str(column.default.arg) if column.default is not None else None,
                    "server_default": str(column.server_default.arg) if column.server_default is not None else None,
                }
                for column in table.columns
            ],
            "foreign_keys": [
                {
                    "column": fk.parent.name,
                    "target": str(fk.column),
                }
                for fk in table.foreign_keys
            ],
            "indexes": [
                {
                    "name": index.name,
                    "columns": [column.name for column in index.columns],
                    "unique": index.unique,
                }
                for index in table.indexes
            ],
        }
    return {
        "generated_at": utc_now(),
        "imported_model_modules": imported_modules,
        "table_count": len(tables),
        "tables": tables,
        "relevant_tables_by_area": RELEVANT_TABLES_BY_AREA,
    }


def table_exists(inspector: Any, table_name: str) -> bool:
    return table_name in set(inspector.get_table_names())


def quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def safe_database_url(url: str) -> str:
    return re.sub(r"://([^:/@]+):([^@]+)@", r"://\1:<REDACTED>@", url)


def live_db_export(output_dir: Path, limit: int) -> dict[str, Any]:
    settings = get_settings()
    database_url = os.getenv("DATABASE_URL") or settings.sync_database_url
    status: dict[str, Any] = {
        "generated_at": utc_now(),
        "database_url_redacted": safe_database_url(database_url),
        "connected": False,
        "tables": {},
        "errors": [],
    }
    try:
        engine = create_engine(database_url, future=True)
        with engine.connect() as connection:
            inspector = inspect(connection)
            status["connected"] = True
            existing = set(inspector.get_table_names())
            for area, table_names in RELEVANT_TABLES_BY_AREA.items():
                for table_name in table_names:
                    table_status: dict[str, Any] = {
                        "area": area,
                        "exists": table_name in existing,
                    }
                    if table_name not in existing:
                        status["tables"][table_name] = table_status
                        continue
                    try:
                        count = connection.execute(text(f"SELECT count(*) FROM {quote_ident(table_name)}")).scalar()
                        table_status["row_count"] = int(count or 0)
                    except Exception as exc:
                        connection.rollback()
                        table_status["count_error"] = {"type": exc.__class__.__name__, "message": redact_string(str(exc))}
                    try:
                        columns = [col["name"] for col in inspector.get_columns(table_name)]
                        table_status["columns_in_live_db"] = columns
                        if columns and limit > 0:
                            select_list = ", ".join(quote_ident(column) for column in columns)
                            rows = connection.execute(
                                text(f"SELECT {select_list} FROM {quote_ident(table_name)} LIMIT :limit"),
                                {"limit": limit},
                            ).mappings().all()
                            table_status["sample_rows"] = [
                                {column: sanitize(row.get(column), column) for column in columns}
                                for row in rows
                            ]
                        else:
                            table_status["sample_rows"] = []
                    except Exception as exc:
                        connection.rollback()
                        table_status["sample_error"] = {"type": exc.__class__.__name__, "message": redact_string(str(exc))}
                    status["tables"][table_name] = table_status
        engine.dispose()
    except Exception as exc:
        status["errors"].append({"type": exc.__class__.__name__, "message": redact_string(str(exc))})
    write_json(output_dir / "live_db_export.json", status)
    return status


def write_query_pack(output_dir: Path) -> None:
    lines = [
        "-- Full page audit DB query pack",
        "-- Run these queries against the Finance backend database to inspect page-related records.",
        "-- Keep exports redacted before sharing externally.",
        "",
    ]
    for area, table_names in RELEVANT_TABLES_BY_AREA.items():
        lines.append(f"-- {area}")
        for table_name in table_names:
            lines.append(f'SELECT * FROM "{table_name}" LIMIT 50;')
        lines.append("")
    write_text(output_dir / "related_db_export_queries.sql", "\n".join(lines))


def write_db_scope(output_dir: Path, live_status: dict[str, Any]) -> None:
    lines = [
        "# Database Evidence Scope",
        "",
        f"Generated at: `{utc_now()}`",
        "",
        "This directory contains SQLAlchemy model schema, relevant table mapping, optional live DB sample rows and export queries.",
        "",
        f"Live DB connected: `{bool(live_status.get('connected'))}`",
    ]
    if live_status.get("errors"):
        lines.extend(["", "## Live DB Errors", ""])
        for error in live_status["errors"]:
            lines.append(f"- `{error.get('type')}`: {error.get('message')}")
    lines.extend(["", "## Areas", ""])
    for area, table_names in RELEVANT_TABLES_BY_AREA.items():
        lines.append(f"### {area}")
        for table_name in table_names:
            table_status = live_status.get("tables", {}).get(table_name, {})
            exists = table_status.get("exists")
            count = table_status.get("row_count")
            suffix = f", rows={count}" if count is not None else ""
            lines.append(f"- `{table_name}` (exists={exists}{suffix})")
        lines.append("")
    write_text(output_dir / "DB_SCOPE.md", "\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=os.getenv("AUDIT_DB_OUTPUT_DIR"))
    parser.add_argument("--sample-limit", type=int, default=int(os.getenv("AUDIT_DB_SAMPLE_LIMIT", "20")))
    args = parser.parse_args()

    output_dir = Path(args.output_dir or Path.cwd() / "audit_db").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory = schema_inventory()
    write_json(output_dir / "schema_inventory.json", inventory)
    write_json(output_dir / "relevant_tables_by_area.json", RELEVANT_TABLES_BY_AREA)
    write_query_pack(output_dir)
    live_status = live_db_export(output_dir, max(0, args.sample_limit))
    write_db_scope(output_dir, live_status)


if __name__ == "__main__":
    main()
