from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

import psycopg2
import psycopg2.extras


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPO_ROOT / "exports"
DEFAULT_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/wb_data_core",
)
DECIMAL_TOLERANCE = Decimal("0.0001")
UNSUPPORTED_PATHS = {
    "/actions",
    "/ads/efficiency",
    "/alerts",
    "/core-sku",
    "/dashboard/sku-profitability",
    "/inventory/purchase-plan",
    "/money/actions",
    "/money/actions/today",
    "/money/articles",
    "/money/cards",
    "/pricing/safety",
    "/skus",
}


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def _latest_bundle_dir() -> Path:
    candidates = sorted(
        [
            path
            for path in EXPORTS_DIR.glob("live_backend_full_audit_*")
            if path.is_dir() and (path / "full_list_captures_index.json").exists()
        ],
        key=lambda path: path.stat().st_mtime,
    )
    if not candidates:
        raise FileNotFoundError("No live audit bundle directory found in exports/")
    return candidates[-1]


def _to_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal("1") if value else Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _normalize_group_key(value: Any) -> str:
    if value is None:
        return "<null>"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _parse_temporal(value: Any) -> date | datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            if "T" in raw or " " in raw:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return date.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _serialize_temporal(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _metrics_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Decimal) or isinstance(right, Decimal):
        return abs(_to_decimal(left) - _to_decimal(right)) <= DECIMAL_TOLERANCE
    return left == right


@dataclass(frozen=True)
class GroupSpec:
    name: str
    bundle_field: str
    db_expr: str


@dataclass(frozen=True)
class RangeSpec:
    name: str
    bundle_field: str
    db_expr: str


@dataclass
class CaptureContext:
    capture: dict[str, Any]
    meta: dict[str, Any]
    query: dict[str, Any]
    account_id: int | None
    date_from: date | None
    date_to: date | None
    date_from_dt: datetime | None
    date_to_dt: datetime | None


WhereBuilder = Callable[[CaptureContext], tuple[str, dict[str, Any]]]


@dataclass
class EndpointSpec:
    path_template: str
    table_sql: str
    note: str
    where_builder: WhereBuilder
    db_id_expr: str = "id"
    bundle_sum_fields: dict[str, tuple[str, ...]] = field(default_factory=dict)
    db_sum_expr_overrides: dict[str, str] = field(default_factory=dict)
    group_specs: tuple[GroupSpec, ...] = ()
    range_specs: tuple[RangeSpec, ...] = ()


def _capture_context(capture: dict[str, Any], meta: dict[str, Any]) -> CaptureContext:
    query = dict(capture.get("query") or {})
    account_id_raw = query.get("account_id", meta.get("account_id"))
    account_id = int(account_id_raw) if account_id_raw not in (None, "") else None
    date_from_raw = query.get("date_from", meta.get("date_from"))
    date_to_raw = query.get("date_to", meta.get("date_to"))
    date_from = date.fromisoformat(date_from_raw) if date_from_raw else None
    date_to = date.fromisoformat(date_to_raw) if date_to_raw else None
    date_from_dt = datetime.combine(date_from, time.min) if date_from is not None else None
    date_to_dt = datetime.combine(date_to, time.max) if date_to is not None else None
    return CaptureContext(
        capture=capture,
        meta=meta,
        query=query,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        date_from_dt=date_from_dt,
        date_to_dt=date_to_dt,
    )


def _where_true(_: CaptureContext) -> tuple[str, dict[str, Any]]:
    return "TRUE", {}


def _where_accounts(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    if ctx.query.get("include_inactive"):
        return "TRUE", {}
    return "is_active IS TRUE", {}


def _where_account_only(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    if ctx.account_id is None:
        return "TRUE", {}
    return "account_id = %(account_id)s", {"account_id": ctx.account_id}


def _where_account_date(ctx: CaptureContext, *, column: str, timestamp: bool = False) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if ctx.account_id is not None:
        clauses.append("account_id = %(account_id)s")
        params["account_id"] = ctx.account_id
    if timestamp:
        if ctx.date_from_dt is not None:
            clauses.append(f"{column} >= %(date_from_dt)s")
            params["date_from_dt"] = ctx.date_from_dt
        if ctx.date_to_dt is not None:
            clauses.append(f"{column} <= %(date_to_dt)s")
            params["date_to_dt"] = ctx.date_to_dt
    else:
        if ctx.date_from is not None:
            clauses.append(f"{column} >= %(date_from)s")
            params["date_from"] = ctx.date_from
        if ctx.date_to is not None:
            clauses.append(f"{column} <= %(date_to)s")
            params["date_to"] = ctx.date_to
    return " AND ".join(clauses) if clauses else "TRUE", params


def _where_finance_reports(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if ctx.account_id is not None:
        clauses.append("account_id = %(account_id)s")
        params["account_id"] = ctx.account_id
    if ctx.date_from is not None:
        clauses.append("(date_to IS NULL OR date_to >= %(date_from)s)")
        params["date_from"] = ctx.date_from
    if ctx.date_to is not None:
        clauses.append("(date_from IS NULL OR date_from <= %(date_to)s)")
        params["date_to"] = ctx.date_to
    return " AND ".join(clauses) if clauses else "TRUE", params


def _where_stock_snapshot_rows(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if ctx.account_id is not None:
        clauses.append("rows.account_id = %(account_id)s")
        params["account_id"] = ctx.account_id
    if ctx.date_from_dt is not None:
        clauses.append("snaps.snapshot_at >= %(date_from_dt)s")
        params["date_from_dt"] = ctx.date_from_dt
    if ctx.date_to_dt is not None:
        clauses.append("snaps.snapshot_at <= %(date_to_dt)s")
        params["date_to_dt"] = ctx.date_to_dt
    return " AND ".join(clauses) if clauses else "TRUE", params


def _where_supplies(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if ctx.account_id is not None:
        clauses.append("account_id = %(account_id)s")
        params["account_id"] = ctx.account_id
    if ctx.date_from_dt is not None:
        clauses.append(
            "("
            "updated_date >= %(date_from_dt)s OR "
            "supply_date >= %(date_from_dt)s OR "
            "fact_date >= %(date_from_dt)s"
            ")"
        )
        params["date_from_dt"] = ctx.date_from_dt
    if ctx.date_to_dt is not None:
        clauses.append(
            "("
            "updated_date <= %(date_to_dt)s OR "
            "supply_date <= %(date_to_dt)s OR "
            "fact_date <= %(date_to_dt)s"
            ")"
        )
        params["date_to_dt"] = ctx.date_to_dt
    return " AND ".join(clauses) if clauses else "TRUE", params


def _where_dq_issues(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    clauses = []
    params: dict[str, Any] = {}
    if ctx.account_id is not None:
        clauses.append("account_id = %(account_id)s")
        params["account_id"] = ctx.account_id
    code_value = ctx.query.get("code")
    if code_value:
        if isinstance(code_value, list):
            clauses.append("code = ANY(%(codes)s)")
            params["codes"] = list(code_value)
        else:
            clauses.append("code = %(code)s")
            params["code"] = str(code_value)
    if ctx.query.get("only_open") is True or ctx.query.get("status") == "open":
        clauses.append("resolved_at IS NULL")
    elif ctx.query.get("status") == "resolved":
        clauses.append("resolved_at IS NOT NULL")
    elif ctx.query.get("status") == "reopened":
        clauses.append("resolved_at IS NULL")
        clauses.append("payload->>'reopenComment' IS NOT NULL")
    if ctx.date_from_dt is not None:
        clauses.append("detected_at >= %(date_from_dt)s")
        params["date_from_dt"] = ctx.date_from_dt
    if ctx.date_to_dt is not None:
        clauses.append("detected_at <= %(date_to_dt)s")
        params["date_to_dt"] = ctx.date_to_dt
    return " AND ".join(clauses) if clauses else "TRUE", params


def _where_costs_unresolved(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    clauses = [
        "("
        "costs.sku_id IS NULL OR "
        "costs.is_ambiguous IS TRUE OR "
        "sku.id IS NULL OR "
        "sku.is_active IS FALSE"
        ")"
    ]
    params: dict[str, Any] = {}
    if ctx.account_id is not None:
        clauses.insert(0, "costs.account_id = %(account_id)s")
        params["account_id"] = ctx.account_id
    return " AND ".join(clauses), params


def _where_sync_runs(ctx: CaptureContext) -> tuple[str, dict[str, Any]]:
    clauses, params = _where_account_only(ctx)
    if clauses == "TRUE":
        clauses_list: list[str] = []
        params = {}
    else:
        clauses_list = [clauses]
    if ctx.query.get("domain"):
        clauses_list.append("domain = %(domain)s")
        params["domain"] = ctx.query["domain"]
    return " AND ".join(clauses_list) if clauses_list else "TRUE", params


def _default_db_sum_expr(fields: tuple[str, ...]) -> str:
    if len(fields) == 1:
        return f"COALESCE(SUM({fields[0]}), 0)"
    terms = " + ".join(f"COALESCE({field}, 0)" for field in fields)
    return f"COALESCE(SUM({terms}), 0)"


def _load_bundle(bundle_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    meta = json.loads((bundle_dir / "meta.json").read_text(encoding="utf-8"))
    captures = json.loads((bundle_dir / "full_list_captures_index.json").read_text(encoding="utf-8"))
    capture_map = {item["path_template"]: item for item in captures}
    return meta, captures, capture_map


def _load_capture_items(bundle_dir: Path, capture: dict[str, Any]) -> list[dict[str, Any]]:
    aggregate_path = bundle_dir / "full_list_captures" / capture["aggregate_file"]
    payload = json.loads(aggregate_path.read_text(encoding="utf-8"))
    return list((payload.get("response") or {}).get("items") or [])


def _bundle_sum_metrics(items: list[dict[str, Any]], sum_fields: dict[str, tuple[str, ...]]) -> dict[str, Decimal]:
    results: dict[str, Decimal] = {}
    for alias, fields in sum_fields.items():
        total = Decimal("0")
        for item in items:
            subtotal = Decimal("0")
            for field_name in fields:
                subtotal += _to_decimal(item.get(field_name))
            total += subtotal
        results[alias] = total
    return results


def _bundle_group_counts(items: list[dict[str, Any]], field_name: str) -> dict[str, int]:
    counter = Counter(_normalize_group_key(item.get(field_name)) for item in items)
    return dict(sorted(counter.items(), key=lambda pair: pair[0]))


def _bundle_range(items: list[dict[str, Any]], field_name: str) -> dict[str, str | None]:
    values = [value for item in items if (value := _parse_temporal(item.get(field_name))) is not None]
    if not values:
        return {"min": None, "max": None}
    return {
        "min": _serialize_temporal(min(values)),
        "max": _serialize_temporal(max(values)),
    }


def _db_group_counts(
    cursor: psycopg2.extras.RealDictCursor,
    *,
    table_sql: str,
    where_sql: str,
    params: dict[str, Any],
    db_expr: str,
) -> dict[str, int]:
    sql = (
        f"SELECT COALESCE(({db_expr})::text, '<null>') AS bucket, COUNT(*)::bigint AS rows_count "
        f"FROM {table_sql} "
        f"WHERE {where_sql} "
        "GROUP BY 1 "
        "ORDER BY 1"
    )
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    return {row["bucket"]: int(row["rows_count"]) for row in rows}


def _compare_supported_endpoint(
    cursor: psycopg2.extras.RealDictCursor,
    *,
    bundle_dir: Path,
    meta: dict[str, Any],
    capture: dict[str, Any],
    spec: EndpointSpec,
) -> dict[str, Any]:
    ctx = _capture_context(capture, meta)
    items = _load_capture_items(bundle_dir, capture)
    where_sql, params = spec.where_builder(ctx)

    select_parts = ["COUNT(*)::bigint AS row_count"]
    if items and isinstance(items[0], dict) and "id" in items[0]:
        select_parts.extend(
            [
                f"MIN({spec.db_id_expr})::bigint AS min_id",
                f"MAX({spec.db_id_expr})::bigint AS max_id",
                f"COALESCE(SUM({spec.db_id_expr}), 0)::numeric AS sum_id",
            ]
        )
    for alias, fields in spec.bundle_sum_fields.items():
        db_expr = spec.db_sum_expr_overrides.get(alias) or _default_db_sum_expr(fields)
        select_parts.append(f"{db_expr} AS {alias}")
    for range_spec in spec.range_specs:
        select_parts.append(f"MIN({range_spec.db_expr}) AS min_{range_spec.name}")
        select_parts.append(f"MAX({range_spec.db_expr}) AS max_{range_spec.name}")

    sql = f"SELECT {', '.join(select_parts)} FROM {spec.table_sql} WHERE {where_sql}"
    cursor.execute(sql, params)
    db_row = cursor.fetchone()

    bundle_metrics: dict[str, Any] = {
        "row_count": int(capture.get("total") if capture.get("total") is not None else len(items)),
        "collected_items": len(items),
    }
    db_metrics: dict[str, Any] = {
        "row_count": int(db_row["row_count"]),
        "collected_items": int(db_row["row_count"]),
    }

    if items and isinstance(items[0], dict) and "id" in items[0]:
        bundle_metrics["min_id"] = min(item["id"] for item in items)
        bundle_metrics["max_id"] = max(item["id"] for item in items)
        bundle_metrics["sum_id"] = sum(_to_decimal(item["id"]) for item in items)
        db_metrics["min_id"] = int(db_row["min_id"]) if db_row["min_id"] is not None else None
        db_metrics["max_id"] = int(db_row["max_id"]) if db_row["max_id"] is not None else None
        db_metrics["sum_id"] = _to_decimal(db_row["sum_id"])

    bundle_metrics.update(_bundle_sum_metrics(items, spec.bundle_sum_fields))
    for alias in spec.bundle_sum_fields:
        db_metrics[alias] = _to_decimal(db_row[alias])

    for range_spec in spec.range_specs:
        bundle_metrics[range_spec.name] = _bundle_range(items, range_spec.bundle_field)
        db_metrics[range_spec.name] = {
            "min": _serialize_temporal(db_row[f"min_{range_spec.name}"]),
            "max": _serialize_temporal(db_row[f"max_{range_spec.name}"]),
        }

    bundle_groups: dict[str, dict[str, int]] = {}
    db_groups: dict[str, dict[str, int]] = {}
    for group_spec in spec.group_specs:
        bundle_groups[group_spec.name] = _bundle_group_counts(items, group_spec.bundle_field)
        db_groups[group_spec.name] = _db_group_counts(
            cursor,
            table_sql=spec.table_sql,
            where_sql=where_sql,
            params=params,
            db_expr=group_spec.db_expr,
        )

    differences: list[str] = []
    for metric_name, bundle_value in bundle_metrics.items():
        db_value = db_metrics.get(metric_name)
        if isinstance(bundle_value, dict):
            if bundle_value != db_value:
                differences.append(f"{metric_name} differs")
        elif not _metrics_equal(bundle_value, db_value):
            differences.append(f"{metric_name} differs")

    for group_name, bundle_group in bundle_groups.items():
        if bundle_group != db_groups.get(group_name):
            differences.append(f"{group_name} differs")

    return {
        "path_template": spec.path_template,
        "path": capture.get("path"),
        "query": capture.get("query"),
        "status": "match" if not differences else "mismatch",
        "supported": True,
        "note": spec.note,
        "bundle": {
            "metrics": bundle_metrics,
            "groups": bundle_groups,
            "page_count": capture.get("page_count"),
            "status_codes": capture.get("status_codes"),
            "error": capture.get("error"),
        },
        "db": {
            "metrics": db_metrics,
            "groups": db_groups,
        },
        "differences": differences,
    }


def _unsupported_result(capture: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "path_template": capture.get("path_template"),
        "path": capture.get("path"),
        "query": capture.get("query"),
        "status": "unsupported",
        "supported": False,
        "note": note,
        "bundle": {
            "metrics": {
                "row_count": capture.get("total"),
                "collected_items": capture.get("collected_items"),
            },
            "page_count": capture.get("page_count"),
            "status_codes": capture.get("status_codes"),
            "error": capture.get("error"),
        },
        "db": None,
        "differences": [],
    }


def _build_supported_specs() -> dict[str, EndpointSpec]:
    return {
        "/accounts": EndpointSpec(
            path_template="/accounts",
            table_sql="wb_accounts",
            note="Direct compare against wb_accounts with include_inactive respected.",
            where_builder=_where_accounts,
            group_specs=(GroupSpec("by_is_active", "is_active", "is_active"),),
        ),
        "/accounts/{account_id}/tokens": EndpointSpec(
            path_template="/accounts/{account_id}/tokens",
            table_sql="wb_api_tokens",
            note="Direct compare against wb_api_tokens for the selected account.",
            where_builder=_where_account_only,
            group_specs=(GroupSpec("by_category", "category", "category"),),
        ),
        "/users": EndpointSpec(
            path_template="/users",
            table_sql="auth_users",
            note="Direct compare against auth_users.",
            where_builder=_where_true,
        ),
        "/ads/campaigns": EndpointSpec(
            path_template="/ads/campaigns",
            table_sql="wb_ad_campaigns",
            note="Direct compare against wb_ad_campaigns.",
            where_builder=_where_account_only,
            group_specs=(GroupSpec("by_status", "status", "status"),),
        ),
        "/ads/stats": EndpointSpec(
            path_template="/ads/stats",
            table_sql="wb_ad_stats_daily",
            note="Direct compare against wb_ad_stats_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_views": ("views",),
                "sum_clicks": ("clicks",),
                "sum_orders": ("orders",),
                "sum_spend": ("sum",),
            },
            db_sum_expr_overrides={
                "sum_spend": 'COALESCE(SUM("sum"), 0)',
            },
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/analytics/funnel": EndpointSpec(
            path_template="/analytics/funnel",
            table_sql="wb_card_funnel_daily",
            note="Direct compare against wb_card_funnel_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_open_count": ("open_count",),
                "sum_cart_count": ("cart_count",),
                "sum_order_count": ("order_count",),
                "sum_buyout_count": ("buyout_count",),
                "sum_cancel_count": ("cancel_count",),
            },
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/analytics/regions": EndpointSpec(
            path_template="/analytics/regions",
            table_sql="wb_region_sales_daily",
            note="Direct compare against wb_region_sales_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_sale_quantity": ("sale_quantity",),
                "sum_sale_amount": ("sale_amount",),
            },
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/balance": EndpointSpec(
            path_template="/balance",
            table_sql="wb_balance_snapshots",
            note="Direct compare against wb_balance_snapshots by snapshot_at.",
            where_builder=lambda ctx: _where_account_date(ctx, column="snapshot_at", timestamp=True),
            bundle_sum_fields={
                "sum_current": ("current",),
                "sum_for_withdraw": ("for_withdraw",),
            },
        ),
        "/costs/imports": EndpointSpec(
            path_template="/costs/imports",
            table_sql="manual_cost_uploads",
            note="Direct compare against manual_cost_uploads.",
            where_builder=_where_true,
            bundle_sum_fields={
                "sum_rows_total": ("rows_total",),
                "sum_rows_valid": ("rows_valid",),
                "sum_rows_invalid": ("rows_invalid",),
            },
            group_specs=(GroupSpec("by_status", "status", "status"),),
        ),
        "/costs/rows": EndpointSpec(
            path_template="/costs/rows",
            table_sql="manual_costs",
            note="Direct compare against manual_costs for the selected account.",
            where_builder=_where_account_only,
            bundle_sum_fields={
                "sum_unit_cost": ("unit_cost",),
                "sum_cost_price": ("cost_price",),
                "sum_packaging_cost": ("packaging_cost",),
                "sum_inbound_logistics_cost": ("inbound_logistics_cost",),
            },
            group_specs=(GroupSpec("by_is_placeholder", "is_placeholder", "is_placeholder"),),
        ),
        "/costs/unresolved": EndpointSpec(
            path_template="/costs/unresolved",
            table_sql="manual_costs costs LEFT JOIN core_sku sku ON sku.id = costs.sku_id",
            note="Direct compare against unresolved manual_costs join logic used by the API.",
            where_builder=_where_costs_unresolved,
            db_id_expr="costs.id",
        ),
        "/documents": EndpointSpec(
            path_template="/documents",
            table_sql="wb_documents",
            note="Direct compare against wb_documents by document_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="document_date", timestamp=False),
            group_specs=(GroupSpec("by_category", "category", "category"),),
            range_specs=(RangeSpec("document_date_range", "document_date", "document_date"),),
        ),
        "/dq/issues": EndpointSpec(
            path_template="/dq/issues",
            table_sql="data_quality_issues",
            note="Direct compare against data_quality_issues using the captured query filters.",
            where_builder=_where_dq_issues,
            group_specs=(GroupSpec("by_severity", "severity", "severity"),),
        ),
        "/dq/issues/investigator": EndpointSpec(
            path_template="/dq/issues/investigator",
            table_sql="data_quality_issues",
            note="Direct compare against investigator issue subset (open issues for one code).",
            where_builder=lambda ctx: (
                "account_id = %(account_id)s AND code = %(code)s AND resolved_at IS NULL",
                {"account_id": ctx.account_id, "code": ctx.query.get("code")},
            ),
        ),
        "/finance/report-rows": EndpointSpec(
            path_template="/finance/report-rows",
            table_sql="wb_realization_report_rows",
            note="Finance-critical compare against wb_realization_report_rows by rr_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="rr_date", timestamp=False),
            bundle_sum_fields={
                "sum_quantity": ("quantity",),
                "sum_retail_amount": ("retail_amount",),
                "sum_for_pay": ("for_pay",),
                "sum_logistics": ("delivery_service", "rebill_logistic_cost"),
                "sum_storage": ("paid_storage",),
                "sum_paid_acceptance": ("paid_acceptance",),
                "sum_penalty": ("penalty",),
                "sum_deduction": ("deduction",),
                "sum_additional_payment": ("additional_payment",),
            },
            range_specs=(RangeSpec("rr_date_range", "rr_date", "rr_date"),),
        ),
        "/finance/reports": EndpointSpec(
            path_template="/finance/reports",
            table_sql="wb_realization_reports",
            note="Finance-critical compare against wb_realization_reports with overlap date logic.",
            where_builder=_where_finance_reports,
            range_specs=(
                RangeSpec("report_date_from_range", "date_from", "date_from"),
                RangeSpec("report_date_to_range", "date_to", "date_to"),
            ),
        ),
        "/marts/account-expense-daily": EndpointSpec(
            path_template="/marts/account-expense-daily",
            table_sql="mart_account_expense_daily",
            note="Finance-critical compare against mart_account_expense_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_source_rows": ("source_rows",),
                "sum_total_expense": ("total_expense",),
                "sum_commission": ("commission",),
                "sum_logistics": ("logistics",),
                "sum_storage": ("storage",),
                "sum_paid_acceptance": ("paid_acceptance",),
                "sum_penalties": ("penalties",),
                "sum_deductions": ("deductions",),
                "sum_additional_payments": ("additional_payments",),
            },
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/marts/finance-reconciliation": EndpointSpec(
            path_template="/marts/finance-reconciliation",
            table_sql="mart_finance_reconciliation",
            note="Finance-critical compare against mart_finance_reconciliation by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_order_rows": ("order_rows",),
                "sum_sale_rows": ("sale_rows",),
                "sum_finance_rows": ("finance_rows",),
                "sum_order_revenue": ("order_revenue",),
                "sum_sale_revenue": ("sale_revenue",),
                "sum_finance_revenue": ("finance_revenue",),
                "sum_sale_for_pay": ("sale_for_pay",),
                "sum_finance_for_pay": ("finance_for_pay",),
                "sum_revenue_delta": ("revenue_delta",),
                "sum_for_pay_delta": ("for_pay_delta",),
            },
            group_specs=(GroupSpec("by_status", "status", "status"),),
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/marts/reconciliation-daily": EndpointSpec(
            path_template="/marts/reconciliation-daily",
            table_sql="mart_reconciliation_daily",
            note="Finance-critical compare against mart_reconciliation_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_orders_qty": ("orders_qty",),
                "sum_orders_amount": ("orders_amount",),
                "sum_sales_qty": ("sales_qty",),
                "sum_sales_amount": ("sales_amount",),
                "sum_returns_qty": ("returns_qty",),
                "sum_returns_amount": ("returns_amount",),
                "sum_finance_qty": ("finance_qty",),
                "sum_finance_revenue": ("finance_revenue",),
                "sum_finance_for_pay": ("finance_for_pay",),
                "sum_ad_spend": ("ad_spend",),
                "sum_revenue_delta": ("revenue_delta",),
                "sum_for_pay_delta": ("for_pay_delta",),
            },
            group_specs=(GroupSpec("by_status_bucket", "status_bucket", "status_bucket"),),
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/marts/sku-daily": EndpointSpec(
            path_template="/marts/sku-daily",
            table_sql="mart_sku_daily",
            note="Direct compare against mart_sku_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_final_sales_qty": ("final_sales_qty",),
                "sum_final_return_qty": ("final_return_qty",),
                "sum_final_revenue": ("final_revenue",),
                "sum_final_for_pay": ("final_for_pay",),
                "sum_ad_spend": ("ad_spend",),
                "sum_estimated_profit_after_ads": ("estimated_profit_after_ads",),
            },
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/marts/stock-daily": EndpointSpec(
            path_template="/marts/stock-daily",
            table_sql="mart_stock_daily",
            note="Direct compare against mart_stock_daily by stat_date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="stat_date", timestamp=False),
            bundle_sum_fields={
                "sum_quantity": ("quantity",),
                "sum_quantity_full": ("quantity_full",),
                "sum_in_way_to_client": ("in_way_to_client",),
                "sum_in_way_from_client": ("in_way_from_client",),
                "sum_sales_30d": ("sales_30d",),
            },
            range_specs=(RangeSpec("stat_date_range", "stat_date", "stat_date"),),
        ),
        "/orders": EndpointSpec(
            path_template="/orders",
            table_sql="wb_orders",
            note="Direct compare against wb_orders by order date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="date", timestamp=True),
            bundle_sum_fields={
                "sum_total_price": ("total_price",),
            },
            group_specs=(GroupSpec("by_is_cancel", "is_cancel", "is_cancel"),),
        ),
        "/prices": EndpointSpec(
            path_template="/prices",
            table_sql="wb_prices",
            note="Direct compare against wb_prices for the selected account.",
            where_builder=_where_account_only,
            bundle_sum_fields={
                "sum_discount": ("discount",),
                "sum_club_discount": ("club_discount",),
            },
            group_specs=(GroupSpec("by_is_bad_turnover", "is_bad_turnover", "is_bad_turnover"),),
        ),
        "/products": EndpointSpec(
            path_template="/products",
            table_sql="wb_product_cards",
            note="Direct compare against wb_product_cards for the selected account.",
            where_builder=_where_account_only,
        ),
        "/sales": EndpointSpec(
            path_template="/sales",
            table_sql="wb_sales",
            note="Direct compare against wb_sales by sale date.",
            where_builder=lambda ctx: _where_account_date(ctx, column="date", timestamp=True),
            bundle_sum_fields={
                "sum_total_price": ("total_price",),
                "sum_for_pay": ("for_pay",),
            },
            group_specs=(GroupSpec("by_is_cancel", "is_cancel", "is_cancel"),),
        ),
        "/stocks/snapshots": EndpointSpec(
            path_template="/stocks/snapshots",
            table_sql="wb_stock_snapshot_rows rows JOIN wb_stock_snapshots snaps ON snaps.id = rows.snapshot_id",
            note="Direct compare against wb_stock_snapshot_rows joined to wb_stock_snapshots by snapshot_at.",
            where_builder=_where_stock_snapshot_rows,
            db_id_expr="rows.id",
            bundle_sum_fields={
                "sum_quantity": ("quantity",),
                "sum_quantity_full": ("quantity_full",),
                "sum_in_way_to_client": ("in_way_to_client",),
                "sum_in_way_from_client": ("in_way_from_client",),
            },
        ),
        "/supplies": EndpointSpec(
            path_template="/supplies",
            table_sql="wb_supplies",
            note="Direct compare against wb_supplies using the same OR date logic as the API.",
            where_builder=_where_supplies,
            group_specs=(GroupSpec("by_status_id", "status_id", "status_id"),),
        ),
        "/sync/cursors": EndpointSpec(
            path_template="/sync/cursors",
            table_sql="wb_sync_cursors",
            note="Direct compare against wb_sync_cursors.",
            where_builder=_where_sync_runs,
            group_specs=(
                GroupSpec("by_domain", "domain", "domain"),
                GroupSpec("by_status", "status", "status"),
            ),
        ),
        "/sync/runs": EndpointSpec(
            path_template="/sync/runs",
            table_sql="wb_sync_runs",
            note="Direct compare against wb_sync_runs.",
            where_builder=_where_sync_runs,
            group_specs=(
                GroupSpec("by_domain", "domain", "domain"),
                GroupSpec("by_status", "status", "status"),
            ),
        ),
        "/tariffs": EndpointSpec(
            path_template="/tariffs",
            table_sql="wb_tariff_commissions",
            note="Direct compare against wb_tariff_commissions, which is the table used by GET /tariffs.",
            where_builder=_where_account_only,
            bundle_sum_fields={
                "sum_kgvp_marketplace": ("kgvp_marketplace",),
            },
        ),
    }


def _build_report_markdown(
    *,
    bundle_dir: Path,
    db_url: str,
    meta: dict[str, Any],
    results: list[dict[str, Any]],
) -> str:
    matched = [item for item in results if item["status"] == "match"]
    mismatched = [item for item in results if item["status"] == "mismatch"]
    unsupported = [item for item in results if item["status"] == "unsupported"]
    finance_focus_paths = {
        "/balance",
        "/finance/reports",
        "/finance/report-rows",
        "/marts/account-expense-daily",
        "/marts/finance-reconciliation",
        "/marts/reconciliation-daily",
        "/marts/sku-daily",
        "/marts/stock-daily",
        "/orders",
        "/sales",
        "/prices",
        "/products",
    }
    finance_focus = [item for item in results if item["path_template"] in finance_focus_paths]

    lines = [
        "# Bundle vs DB Compare Report",
        "",
        f"- Generated at: `{datetime.now().isoformat()}`",
        f"- Bundle: `{bundle_dir.name}`",
        f"- DB: `{db_url}`",
        f"- Account ID: `{meta.get('account_id')}`",
        f"- Date window: `{meta.get('date_from')}` .. `{meta.get('date_to')}`",
        "",
        "## Summary",
        "",
        f"- Matched endpoints: `{len(matched)}`",
        f"- Mismatched endpoints: `{len(mismatched)}`",
        f"- Unsupported endpoints: `{len(unsupported)}`",
        "",
    ]

    if mismatched:
        lines.extend(["## Findings", ""])
        for item in mismatched:
            diff_text = ", ".join(item["differences"])
            lines.append(f"- `{item['path_template']}`: {diff_text}")
        lines.append("")
    else:
        lines.extend(["## Findings", "", "- No direct DB mismatches were detected in the configured endpoint set.", ""])

    lines.extend(["## Finance Focus", ""])
    for item in finance_focus:
        bundle_metrics = item["bundle"]["metrics"]
        db_metrics = (item.get("db") or {}).get("metrics") or {}
        status = item["status"]
        line = (
            f"- `{item['path_template']}`: `{status}` "
            f"(bundle rows `{bundle_metrics.get('row_count')}`, db rows `{db_metrics.get('row_count')}`)"
        )
        lines.append(line)
        if item["path_template"] == "/finance/report-rows":
            lines.append(
                "  "
                f"retail `{bundle_metrics.get('sum_retail_amount')}` vs `{db_metrics.get('sum_retail_amount')}`, "
                f"for_pay `{bundle_metrics.get('sum_for_pay')}` vs `{db_metrics.get('sum_for_pay')}`"
            )
        if item["path_template"] == "/marts/finance-reconciliation":
            lines.append(
                "  "
                f"finance_revenue `{bundle_metrics.get('sum_finance_revenue')}` vs `{db_metrics.get('sum_finance_revenue')}`, "
                f"revenue_delta `{bundle_metrics.get('sum_revenue_delta')}` vs `{db_metrics.get('sum_revenue_delta')}`"
            )
        if item["path_template"] == "/marts/reconciliation-daily":
            lines.append(
                "  "
                f"orders_amount `{bundle_metrics.get('sum_orders_amount')}` vs `{db_metrics.get('sum_orders_amount')}`, "
                f"finance_for_pay `{bundle_metrics.get('sum_finance_for_pay')}` vs `{db_metrics.get('sum_finance_for_pay')}`"
            )
        if item["path_template"] == "/marts/account-expense-daily":
            lines.append(
                "  "
                f"total_expense `{bundle_metrics.get('sum_total_expense')}` vs `{db_metrics.get('sum_total_expense')}`"
            )
    lines.append("")

    if unsupported:
        lines.extend(["## Unsupported", ""])
        for item in unsupported:
            lines.append(f"- `{item['path_template']}`: {item['note']}")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare a saved live audit bundle against the real PostgreSQL DB.")
    parser.add_argument(
        "--bundle-dir",
        type=Path,
        default=None,
        help="Path to the live audit bundle directory. Defaults to the latest bundle in exports/.",
    )
    parser.add_argument(
        "--db-url",
        default=DEFAULT_DB_URL,
        help="PostgreSQL connection URL.",
    )
    args = parser.parse_args()

    bundle_dir = args.bundle_dir.resolve() if args.bundle_dir else _latest_bundle_dir()
    meta, captures, capture_map = _load_bundle(bundle_dir)
    supported_specs = _build_supported_specs()
    results: list[dict[str, Any]] = []

    with psycopg2.connect(args.db_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cursor:
            cursor.execute("SET TIME ZONE 'Asia/Tashkent'")
            for capture in captures:
                path_template = capture["path_template"]
                if path_template in supported_specs:
                    results.append(
                        _compare_supported_endpoint(
                            cursor,
                            bundle_dir=bundle_dir,
                            meta=meta,
                            capture=capture,
                            spec=supported_specs[path_template],
                        )
                    )
                else:
                    note = (
                        "Derived/service-composed endpoint; no 1:1 DB compare configured yet."
                        if path_template in UNSUPPORTED_PATHS
                        else "No compare spec configured for this endpoint yet."
                    )
                    results.append(_unsupported_result(capture, note))

    matched = sum(1 for item in results if item["status"] == "match")
    mismatched = sum(1 for item in results if item["status"] == "mismatch")
    unsupported = sum(1 for item in results if item["status"] == "unsupported")

    summary = {
        "generated_at": datetime.now().isoformat(),
        "bundle_dir": str(bundle_dir),
        "db_url": args.db_url,
        "account_id": meta.get("account_id"),
        "date_from": meta.get("date_from"),
        "date_to": meta.get("date_to"),
        "matched": matched,
        "mismatched": mismatched,
        "unsupported": unsupported,
        "capture_count": len(captures),
    }
    finance_focus = [
        item
        for item in results
        if item["path_template"]
        in {
            "/balance",
            "/finance/reports",
            "/finance/report-rows",
            "/marts/account-expense-daily",
            "/marts/finance-reconciliation",
            "/marts/reconciliation-daily",
            "/marts/sku-daily",
            "/marts/stock-daily",
            "/orders",
            "/sales",
            "/prices",
            "/products",
        }
    ]

    summary_path = bundle_dir / "db_compare_summary.json"
    results_path = bundle_dir / "db_compare_results.json"
    finance_path = bundle_dir / "db_compare_finance_focus.json"
    report_path = bundle_dir / "DB_COMPARE_REPORT.md"
    _write_json(summary_path, summary)
    _write_json(results_path, results)
    _write_json(finance_path, finance_focus)
    _write_text(
        report_path,
        _build_report_markdown(
            bundle_dir=bundle_dir,
            db_url=args.db_url,
            meta=meta,
            results=results,
        ),
    )

    print(
        json.dumps(
            {
                "summary_file": str(summary_path),
                "results_file": str(results_path),
                "finance_focus_file": str(finance_path),
                "report_file": str(report_path),
                "matched": matched,
                "mismatched": mismatched,
                "unsupported": unsupported,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
