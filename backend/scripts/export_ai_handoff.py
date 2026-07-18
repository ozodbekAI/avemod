from __future__ import annotations

import json
import os
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, text

from app.core.config import get_settings


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPO_ROOT / "exports"
MAX_SAMPLE_ROWS = 100
MAX_SYNC_RUNS = 100
MAX_DQ_ROWS = 200


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _slug_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
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


def _redact_database_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    prefix, suffix = url.split("://", 1)
    if "@" not in suffix:
        return url
    credentials, host = suffix.split("@", 1)
    if ":" in credentials:
        username = credentials.split(":", 1)[0]
        return f"{prefix}://{username}:***@{host}"
    return f"{prefix}://***@{host}"


def _run_command(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "cmd": " ".join(cmd),
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "ok": completed.returncode == 0,
    }


def _list_code_files() -> list[str]:
    return [
        "docs/backend_correctness_closure_2026-05-16.md",
        "app/services/marts.py",
        "app/services/data_quality.py",
        "app/services/dashboard.py",
        "app/modules/product_cards/sync.py",
        "app/modules/orders/sync.py",
        "app/modules/sales/sync.py",
        "app/modules/finance/sync.py",
        "app/modules/ads/sync.py",
        "app/modules/analytics/sync.py",
        "app/core/current_state.py",
        "app/core/http.py",
        "app/core/dedupe.py",
        "app/models/marts.py",
        "app/models/orders.py",
        "app/models/sales.py",
        "app/models/product_cards.py",
        "app/models/raw.py",
    ]


def _build_repo_summary() -> str:
    return """# Repo Summary for External AI Review

## Goal
This backend is a read-only Wildberries Data Core that ingests seller data, normalizes it, builds marts, and runs data-quality checks.

## Main capabilities
- Wildberries read-only sync domains: product cards, prices, orders, sales, stocks, finance, supplies, ads, analytics, tariffs, documents
- Raw HTTP audit logging with request/response metadata
- Normalized business tables and stable `dedupe_key` upserts
- Business marts:
  - `mart_sku_daily`
  - `mart_stock_daily`
  - `mart_finance_reconciliation`
  - `mart_account_expense_daily`
- Data quality engine with source-level and mart-level checks

## Important implementation notes
- `CoreSKU` uses stable upsert/archive, not delete/reinsert
- orders/sales use pagination + `dedupe_key`
- current-state views preserve multi-line rows using business grain
- analytics funnel batching is capped at WB docs limit `20`
- ads fullstats is filtered to WB-allowed statuses `{7,9,11}`
- rate-limit headers are captured and used for retry decisions

## Files to review first
""" + "\n".join(f"- `{path}`" for path in _list_code_files())


def _build_prompt(manifest: dict[str, Any]) -> str:
    bundle_dir = manifest["bundle_dir"]
    return f"""# AI Analysis Prompt

You are reviewing a Wildberries Data Core backend plus exported live data snapshots.

## What you received
- Codebase: this repository
- Data bundle directory: `{bundle_dir}`

## Your task
Analyze whether the pulled data and current backend behavior look correct and production-ready for:
- profitability analysis
- finance reconciliation
- stock planning foundations
- ad performance analysis

## Focus areas
1. Validate whether marts and source tables are internally consistent.
2. Look for suspicious gaps, mismatches, duplicates, stale cursors, or loading anomalies.
3. Check whether open DQ issues look like real business signals or backend/data-loading bugs.
4. Review whether sync runs, cursor movement, and raw-response growth suggest healthy ingestion.
5. If you see risk, separate it into:
   - backend logic bug
   - migration/schema risk
   - external WB API/runtime risk
   - business-data incompleteness

## Important context
- Backend correctness closure is documented in `docs/backend_correctness_closure_2026-05-16.md`.
- Live business DQ issues may still exist and are not automatically backend bugs.
- The main exported DB evidence is under:
  - `db/summary.json`
  - `db/table_counts.json`
  - `db/account_summary.json`
  - `db/sync_cursors.json`
  - `db/recent_sync_runs.json`
  - `db/open_dq_issues.json`
  - `db/*_sample.json`

## Deliverable format
Please return:
1. Executive summary
2. Critical findings
3. Major findings
4. Data anomalies that look business-real rather than code bugs
5. Recommended next actions
"""


def _bundle_readme(manifest: dict[str, Any]) -> str:
    return f"""# AI Handoff Bundle

Generated at: `{manifest["generated_at"]}`
Bundle slug: `{manifest["bundle_slug"]}`

## What to send to the external AI
1. The relevant code files listed in `repo_summary.md`
2. This entire bundle directory or the zip file
3. `PROMPT.md` as the analysis instruction

## Bundle contents
- `PROMPT.md` — ready-to-send analysis prompt
- `repo_summary.md` — high-level repo map
- `manifest.json` — generation metadata
- `verification.json` — local compile/test/verification status
- `db/summary.json` — top-level counts and latest status
- `db/*.json` — sync, DQ, marts, and sample slices

## Notes
- This bundle is intended for analysis, not backup.
- Samples are capped to keep the package compact.
"""


@dataclass
class QueryExport:
    name: str
    sql: str
    limit: int | None = None


def _fetch_rows(conn, sql: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    result = conn.execute(text(sql), params or {})
    return [dict(row._mapping) for row in result]


def _fetch_scalar(conn, sql: str, *, params: dict[str, Any] | None = None) -> Any:
    return conn.execute(text(sql), params or {}).scalar()


def _db_exports() -> list[QueryExport]:
    return [
        QueryExport(
            "sync_cursors",
            """
            select account_id, domain, cursor_key, status, last_synced_at, cursor_value
            from wb_sync_cursors
            order by account_id, domain, cursor_key
            """,
        ),
        QueryExport(
            "recent_sync_runs",
            """
            select id, account_id, domain, trigger, status, is_backfill, started_at, finished_at, details, error_text
            from wb_sync_runs
            order by started_at desc nulls last, id desc
            limit :limit
            """,
            limit=MAX_SYNC_RUNS,
        ),
        QueryExport(
            "open_dq_issues",
            """
            select id, account_id, domain, severity, code, entity_key, message, payload, detected_at
            from data_quality_issues
            where resolved_at is null
            order by severity desc, detected_at desc, id desc
            limit :limit
            """,
            limit=MAX_DQ_ROWS,
        ),
        QueryExport(
            "core_sku_sample",
            """
            select id, account_id, nm_id, vendor_code, barcode, tech_size, brand, subject_name, is_active, source_updated_at
            from core_sku
            order by updated_at desc nulls last, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "manual_costs_sample",
            """
            select id, account_id, sku_id, vendor_code, nm_id, barcode, tech_size, cost_price,
                   packaging_cost, inbound_logistics_cost, valid_from, valid_to, is_ambiguous, match_rule
            from manual_costs
            order by updated_at desc nulls last, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "manual_cost_uploads_sample",
            """
            select id, account_id, filename, rows_total, rows_valid, rows_invalid, status, error_text, imported_at, summary
            from manual_cost_uploads
            order by imported_at desc nulls last, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "mart_sku_daily_sample",
            """
            select stat_date, account_id, sku_id, nm_id, vendor_code, barcode,
                   final_sales_qty, final_return_qty, final_net_qty,
                   final_revenue, final_for_pay, final_revenue_source,
                   total_unit_cost, estimated_cogs, estimated_profit_before_ads,
                   estimated_profit_after_ads, has_manual_cost, ad_spend
            from mart_sku_daily
            order by stat_date desc, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "mart_finance_reconciliation_sample",
            """
            select stat_date, account_id, srid, order_id, nm_id, vendor_code, barcode,
                   has_order, has_sale, has_finance, status,
                   order_revenue, sale_revenue, finance_revenue,
                   sale_for_pay, finance_for_pay, revenue_delta, for_pay_delta
            from mart_finance_reconciliation
            order by stat_date desc, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "mart_account_expense_daily_sample",
            """
            select stat_date, account_id, source_rows, commission, acquiring_fee, logistics,
                   paid_acceptance, storage, penalties, deductions, additional_payments, total_expense
            from mart_account_expense_daily
            order by stat_date desc, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "ad_cluster_stats_sample",
            """
            select id, account_id, advert_id, stat_date, cluster, nm_id, views, clicks, ctr, cpc, cpm,
                   orders, atbs, sum, avg_position
            from wb_ad_cluster_stats
            order by stat_date desc, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
        QueryExport(
            "raw_responses_recent_sample",
            """
            select id, account_id, api_category, endpoint, status_code, is_success, retry_count,
                   request_fingerprint, response_fingerprint, requested_at, loaded_at, response_headers
            from raw_wb_api_responses
            order by loaded_at desc, id desc
            limit :limit
            """,
            limit=MAX_SAMPLE_ROWS,
        ),
    ]


def _collect_table_counts(conn) -> dict[str, Any]:
    tables = {
        "wb_accounts": "select count(*) from wb_accounts",
        "core_sku": "select count(*) from core_sku",
        "wb_product_cards": "select count(*) from wb_product_cards",
        "wb_prices": "select count(*) from wb_prices",
        "wb_orders": "select count(*) from wb_orders",
        "wb_sales": "select count(*) from wb_sales",
        "wb_stock_snapshot_rows": "select count(*) from wb_stock_snapshot_rows",
        "wb_realization_report_rows": "select count(*) from wb_realization_report_rows",
        "wb_supplies": "select count(*) from wb_supplies",
        "wb_ad_campaigns": "select count(*) from wb_ad_campaigns",
        "wb_ad_stats_daily": "select count(*) from wb_ad_stats_daily",
        "wb_ad_cluster_stats": "select count(*) from wb_ad_cluster_stats",
        "wb_card_funnel_daily": "select count(*) from wb_card_funnel_daily",
        "wb_region_sales_daily": "select count(*) from wb_region_sales_daily",
        "wb_documents": "select count(*) from wb_documents",
        "manual_cost_uploads": "select count(*) from manual_cost_uploads",
        "manual_costs": "select count(*) from manual_costs",
        "raw_wb_api_responses": "select count(*) from raw_wb_api_responses",
        "wb_sync_cursors": "select count(*) from wb_sync_cursors",
        "wb_sync_runs": "select count(*) from wb_sync_runs",
        "data_quality_issues_open": "select count(*) from data_quality_issues where resolved_at is null",
        "mart_sku_daily": "select count(*) from mart_sku_daily",
        "mart_stock_daily": "select count(*) from mart_stock_daily",
        "mart_finance_reconciliation": "select count(*) from mart_finance_reconciliation",
        "mart_account_expense_daily": "select count(*) from mart_account_expense_daily",
    }
    return {name: _fetch_scalar(conn, sql) for name, sql in tables.items()}


def _collect_account_summary(conn) -> list[dict[str, Any]]:
    return _fetch_rows(
        conn,
        """
        select
          a.id,
          a.name,
          a.seller_name,
          a.external_account_id,
          a.timezone,
          a.is_active,
          count(distinct t.id) as token_count,
          count(distinct c.id) as cursor_count,
          count(distinct dq.id) filter (where dq.resolved_at is null) as open_dq_issues
        from wb_accounts a
        left join wb_api_tokens t on t.account_id = a.id and t.is_active is true
        left join wb_sync_cursors c on c.account_id = a.id
        left join data_quality_issues dq on dq.account_id = a.id
        group by a.id, a.name, a.seller_name, a.external_account_id, a.timezone, a.is_active
        order by a.id
        """,
    )


def _collect_dq_grouped(conn) -> list[dict[str, Any]]:
    return _fetch_rows(
        conn,
        """
        select code, severity, count(*) as open_count
        from data_quality_issues
        where resolved_at is null
        group by code, severity
        order by open_count desc, code
        """,
    )


def _collect_latest_run_status(conn) -> list[dict[str, Any]]:
    return _fetch_rows(
        conn,
        """
        with ranked as (
          select *,
                 row_number() over (
                   partition by account_id, domain
                   order by started_at desc nulls last, id desc
                 ) as rn
          from wb_sync_runs
        )
        select account_id, domain, status, started_at, finished_at, details, error_text
        from ranked
        where rn = 1
        order by account_id, domain
        """,
    )


def _collect_schema_overview(conn) -> list[dict[str, Any]]:
    return _fetch_rows(
        conn,
        """
        select table_name, table_type
        from information_schema.tables
        where table_schema = 'public'
          and (
            table_name like 'wb_%'
            or table_name like 'mart_%'
            or table_name in ('core_sku', 'manual_costs', 'manual_cost_uploads', 'data_quality_issues', 'raw_wb_api_responses')
          )
        order by table_type, table_name
        """,
    )


def _zip_directory(source_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(source_dir))


def main() -> None:
    generated_at = _utc_now()
    bundle_slug = f"ai_handoff_{_slug_timestamp(generated_at)}"
    bundle_dir = EXPORTS_DIR / bundle_slug
    db_dir = bundle_dir / "db"
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    db_dir.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    manifest: dict[str, Any] = {
        "generated_at": generated_at.isoformat(),
        "bundle_slug": bundle_slug,
        "bundle_dir": str(bundle_dir),
        "database_url_redacted": _redact_database_url(settings.sync_database_url),
        "included_code_files": _list_code_files(),
        "errors": [],
    }

    verification = {
        "compileall": _run_command(
            [os.fspath(REPO_ROOT / ".venv/bin/python"), "-m", "compileall", "-q", "app", "tests", "scripts", "alembic"],
            cwd=REPO_ROOT,
        ),
        "pytest": _run_command(
            [os.fspath(REPO_ROOT / ".venv/bin/pytest"), "tests/unit", "tests/api", "-q"],
            cwd=REPO_ROOT,
        ),
        "verify_backend_correctness": _run_command(
            [os.fspath(REPO_ROOT / ".venv/bin/python"), "scripts/verify_backend_correctness.py"],
            cwd=REPO_ROOT,
        ),
        "alembic_current": _run_command(
            [os.fspath(REPO_ROOT / ".venv/bin/alembic"), "current"],
            cwd=REPO_ROOT,
        ),
    }

    db_summary: dict[str, Any] = {}
    try:
        engine = create_engine(settings.sync_database_url)
        with engine.connect() as conn:
            table_counts = _collect_table_counts(conn)
            account_summary = _collect_account_summary(conn)
            dq_grouped = _collect_dq_grouped(conn)
            latest_run_status = _collect_latest_run_status(conn)
            schema_overview = _collect_schema_overview(conn)

            db_summary = {
                "table_counts": table_counts,
                "account_summary": account_summary,
                "open_dq_by_code": dq_grouped,
                "latest_sync_status_by_domain": latest_run_status,
                "schema_overview": schema_overview,
            }

            _write_json(db_dir / "table_counts.json", table_counts)
            _write_json(db_dir / "account_summary.json", account_summary)
            _write_json(db_dir / "open_dq_by_code.json", dq_grouped)
            _write_json(db_dir / "latest_sync_status_by_domain.json", latest_run_status)
            _write_json(db_dir / "schema_overview.json", schema_overview)

            for export in _db_exports():
                params = {"limit": export.limit} if export.limit is not None else {}
                rows = _fetch_rows(conn, export.sql, params=params)
                _write_json(db_dir / f"{export.name}.json", rows)
    except Exception as exc:  # pragma: no cover - operational fallback
        manifest["errors"].append({"stage": "database_export", "error": str(exc)})

    summary = {
        "generated_at": generated_at.isoformat(),
        "database_url_redacted": _redact_database_url(settings.sync_database_url),
        "verification_ok": all(step.get("ok") for step in verification.values()),
        "table_counts": db_summary.get("table_counts", {}),
        "accounts": db_summary.get("account_summary", []),
        "open_dq_by_code": db_summary.get("open_dq_by_code", []),
        "latest_sync_status_by_domain": db_summary.get("latest_sync_status_by_domain", []),
    }

    _write_json(bundle_dir / "manifest.json", manifest)
    _write_json(bundle_dir / "verification.json", verification)
    _write_json(db_dir / "summary.json", summary)
    _write_text(bundle_dir / "repo_summary.md", _build_repo_summary())
    _write_text(bundle_dir / "PROMPT.md", _build_prompt(manifest))
    _write_text(bundle_dir / "README.md", _bundle_readme(manifest))

    zip_path = EXPORTS_DIR / f"{bundle_slug}.zip"
    if zip_path.exists():
        zip_path.unlink()
    _zip_directory(bundle_dir, zip_path)

    print(json.dumps({"bundle_dir": str(bundle_dir), "zip_path": str(zip_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
