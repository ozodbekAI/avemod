from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from sqlalchemy import and_, func, or_, select

from app.core.db import SessionLocal
from app.core.expense_taxonomy import (
    AD_SPEND_SOURCE_FINANCE,
    additional_income as expense_additional_income,
    normalized_wb_expenses_total,
)
from app.core.issue_refs import extract_issue_refs
from app.models.accounts import WBAccount
from app.models.data_quality import DataQualityIssue
from app.models.manual_costs import ManualCost
from app.models.marts import MartSKUDaily
from app.models.product_cards import CoreSKU
from app.models.sync import WBSyncCursor, WBSyncRun
from app.modules.finance.sync import FinanceSyncService
from app.services.accounts import AccountService
from app.services.marts import MartService


REPO_ROOT = Path(__file__).resolve().parents[1]
EXPORTS_DIR = REPO_ROOT / "exports"
DOCS_DIR = REPO_ROOT / "docs"

DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1"
DEFAULT_EMAIL = "audit-user@example.invalid"
DEFAULT_ACCOUNT_NAME = "wb-live-test"
DEFAULT_DATE_FROM = date(2026, 5, 1)
DEFAULT_DATE_TO = date(2026, 5, 31)
PAGE_LIMIT = 200
DIRECT_WB_PAGE_LIMIT = 100_000
WB_FINANCE_MIN_SPACING_SECONDS = 62.0
DECIMAL_TOLERANCE = Decimal("0.01")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _slug_timestamp(value: datetime) -> str:
    return value.strftime("%Y%m%d_%H%M%S")


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _float0(value: Any) -> float:
    return float(_decimal(value))


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


def _progress(message: str) -> None:
    if os.getenv("AUDIT_PROGRESS", "").strip().lower() in {"1", "true", "yes", "on"}:
        print(message, flush=True)


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value:
        return value
    raise SystemExit(f"{name} is required; set it in the environment before running this audit.")


async def _wb_request_json(
    client: httpx.AsyncClient,
    token: str,
    method: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(3):
        response = await client.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            headers={"Authorization": token},
        )
        if response.status_code == 429:
            retry_after_raw = response.headers.get("x-ratelimit-retry") or response.headers.get("retry-after")
            try:
                retry_after = float(retry_after_raw) if retry_after_raw else WB_FINANCE_MIN_SPACING_SECONDS
            except ValueError:
                retry_after = WB_FINANCE_MIN_SPACING_SECONDS
            last_error = httpx.HTTPStatusError(
                f"429 Too Many Requests for {url}",
                request=response.request,
                response=response,
            )
            _progress(f"direct WB 429 for {url}; sleeping {retry_after:.1f}s before retry {attempt + 2}")
            await asyncio.sleep(retry_after)
            continue
        response.raise_for_status()
        if not response.text:
            return {}
        return response.json()
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Failed to fetch {url}")


def _quantize(value: Any) -> Decimal:
    return _decimal(value).quantize(DECIMAL_TOLERANCE)


def _match_decimal(left: Any, right: Any, tolerance: Decimal = DECIMAL_TOLERANCE) -> bool:
    return abs(_decimal(left) - _decimal(right)) <= tolerance


def _match_int(left: Any, right: Any) -> bool:
    return int(left or 0) == int(right or 0)


def _api_get(mapping: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cursor: Any = mapping
    for key in keys:
        if not isinstance(cursor, dict):
            return default
        cursor = cursor.get(key)
    return cursor if cursor is not None else default


def _status(matches: list[bool]) -> str:
    return "match" if all(matches) else "mismatch"


def _as_list(payload: Any, *keys: str) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return []


def _bucket_template() -> dict[str, Any]:
    return {
        "finance_rows": 0,
        "gross_units": 0,
        "return_units": 0,
        "net_units": 0,
        "realized_revenue": Decimal("0"),
        "revenue_final": Decimal("0"),
        "for_pay": Decimal("0"),
        "wb_commission": Decimal("0"),
        "payment_processing": Decimal("0"),
        "pvz_reward": Decimal("0"),
        "wb_logistics": Decimal("0"),
        "wb_logistics_rebill": Decimal("0"),
        "acceptance": Decimal("0"),
        "penalty": Decimal("0"),
        "deduction": Decimal("0"),
        "marketing_deduction": Decimal("0"),
        "loyalty": Decimal("0"),
        "other_wb_expenses": Decimal("0"),
        "storage": Decimal("0"),
        "commission": Decimal("0"),
        "acquiring_fee": Decimal("0"),
        "logistics": Decimal("0"),
        "paid_acceptance": Decimal("0"),
        "penalties": Decimal("0"),
        "deductions": Decimal("0"),
        "additional_payments": Decimal("0"),
        "additional_income": Decimal("0"),
        "total_wb_expenses": Decimal("0"),
        "ad_spend_finance": Decimal("0"),
        "ad_spend_final": Decimal("0"),
        "ad_spend_source": "",
    }


def _finalize_bucket(bucket: dict[str, Any]) -> dict[str, Any]:
    view = SimpleNamespace(**bucket)
    bucket["revenue_final"] = bucket["realized_revenue"]
    bucket["total_wb_expenses"] = normalized_wb_expenses_total(view)
    bucket["commission"] = bucket["wb_commission"]
    bucket["acquiring_fee"] = bucket["payment_processing"]
    bucket["logistics"] = bucket["wb_logistics"] + bucket["wb_logistics_rebill"]
    bucket["paid_acceptance"] = bucket["acceptance"]
    bucket["penalties"] = bucket["penalty"]
    bucket["deductions"] = bucket["deduction"] + bucket["marketing_deduction"] + bucket["loyalty"] + bucket["other_wb_expenses"]
    bucket["additional_income"] = expense_additional_income(view)
    bucket["ad_spend_finance"] = bucket["marketing_deduction"] if bucket["marketing_deduction"] > 0 else Decimal("0")
    bucket["ad_spend_final"] = bucket["ad_spend_finance"]
    bucket["ad_spend_source"] = AD_SPEND_SOURCE_FINANCE if bucket["ad_spend_finance"] > 0 else ""
    return bucket


def _compare_numeric_fields(
    api_item: dict[str, Any],
    wb_item: dict[str, Any],
    fields: list[str],
) -> dict[str, Any]:
    mismatches: dict[str, Any] = {}
    for field in fields:
        api_value = _decimal(api_item.get(field))
        wb_value = _decimal(wb_item.get(field))
        if not _match_decimal(api_value, wb_value):
            mismatches[field] = {
                "api": float(api_value),
                "wb": float(wb_value),
                "delta": float(api_value - wb_value),
            }
    return mismatches


def _compare_count_fields(
    api_item: dict[str, Any],
    wb_item: dict[str, Any],
    fields: list[str],
) -> dict[str, Any]:
    mismatches: dict[str, Any] = {}
    for field in fields:
        api_value = int(api_item.get(field) or 0)
        wb_value = int(wb_item.get(field) or 0)
        if api_value != wb_value:
            mismatches[field] = {
                "api": api_value,
                "wb": wb_value,
                "delta": api_value - wb_value,
            }
    return mismatches


@dataclass
class BackendAuditClient:
    base_url: str
    email: str
    password: str

    async def __aenter__(self) -> "BackendAuditClient":
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(120.0, connect=30.0),
            follow_redirects=True,
        )
        response = await self.client.post(
            f"{self.base_url}/auth/login",
            json={"email": self.email, "password": self.password},
        )
        response.raise_for_status()
        payload = response.json()
        self.headers = {"Authorization": f"Bearer {payload['access_token']}"}
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.client.aclose()

    async def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        response = await self.client.get(f"{self.base_url}{path}", params=params, headers=self.headers)
        response.raise_for_status()
        return response.json()

    async def get_all_pages(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int = PAGE_LIMIT,
    ) -> dict[str, Any]:
        base_params = dict(params or {})
        first = await self.get_json(path, params={**base_params, "limit": limit, "offset": 0})
        items = list(first.get("items") or [])
        total = int(first.get("total") or len(items))
        offset = len(items)
        while offset < total:
            page = await self.get_json(path, params={**base_params, "limit": limit, "offset": offset})
            page_items = list(page.get("items") or [])
            items.extend(page_items)
            if not page_items:
                break
            offset += len(page_items)
        return {
            "total": total,
            "items": items,
            "summary": first.get("summary"),
        }


async def _resolve_account_id(account_name: str) -> int:
    async with SessionLocal() as session:
        account = (
            await session.execute(
                select(WBAccount).where(WBAccount.name == account_name).limit(1)
            )
        ).scalar_one_or_none()
        if account is None:
            raise RuntimeError(f"WB account `{account_name}` not found")
        return int(account.id)


async def _load_core_sku_maps(account_id: int) -> dict[str, Any]:
    async with SessionLocal() as session:
        rows = list(
            (
                await session.execute(
                    select(CoreSKU).where(CoreSKU.account_id == account_id).order_by(CoreSKU.is_active.desc(), CoreSKU.id.asc())
                )
            ).scalars()
        )
        by_nm_barcode: dict[tuple[int | None, str | None], int] = {}
        by_nm_vendor: dict[tuple[int | None, str | None], int] = {}
        for row in rows:
            nm_barcode_key = (row.nm_id, row.barcode)
            nm_vendor_key = (row.nm_id, row.vendor_code)
            if nm_barcode_key not in by_nm_barcode:
                by_nm_barcode[nm_barcode_key] = int(row.id)
            if nm_vendor_key not in by_nm_vendor:
                by_nm_vendor[nm_vendor_key] = int(row.id)
        mart_service = MartService()
        return {
            "by_nm_barcode": by_nm_barcode,
            "by_nm_vendor": by_nm_vendor,
            "core_index": mart_service._build_core_sku_index(rows),
            "mart_service": mart_service,
        }


async def _fetch_direct_wb_finance(
    *,
    account_id: int,
    date_from: date,
    date_to: date,
) -> dict[str, Any]:
    async with SessionLocal() as session:
        token = await AccountService().get_decrypted_token(session, account_id, "finance")
    async with httpx.AsyncClient(timeout=httpx.Timeout(180.0, connect=30.0)) as client:
        _progress("direct WB balance request")
        balance_payload = await _wb_request_json(client, token, "GET", "https://finance-api.wildberries.ru/api/v1/account/balance")
        _progress("direct WB balance done")
        await asyncio.sleep(WB_FINANCE_MIN_SPACING_SECONDS)
        _progress("direct WB reports list request")
        reports_payload = await _wb_request_json(
            client,
            token,
            "POST",
            "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/list",
            json_body={"dateFrom": date_from.isoformat(), "dateTo": date_to.isoformat()},
        )
        _progress(f"direct WB reports list done count={len(_as_list(reports_payload, 'report', 'reports', 'data'))}")
        await asyncio.sleep(WB_FINANCE_MIN_SPACING_SECONDS)
        all_rows: list[dict[str, Any]] = []
        rrd_id = 0
        while True:
            _progress(f"direct WB detailed request rrd_id={rrd_id}")
            detail_payload = await _wb_request_json(
                client,
                token,
                "POST",
                "https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed",
                json_body={
                    "dateFrom": date_from.isoformat(),
                    "dateTo": date_to.isoformat(),
                    "period": "weekly",
                    "rrdId": rrd_id,
                    "limit": DIRECT_WB_PAGE_LIMIT,
                },
            )
            rows = _as_list(detail_payload, "report", "reports", "data")
            _progress(f"direct WB detailed response rows={len(rows)}")
            if not rows:
                break
            all_rows.extend(rows)
            last_rrd = max(int(row.get("rrdId") or row.get("rrd_id") or 0) for row in rows)
            if len(rows) < DIRECT_WB_PAGE_LIMIT or last_rrd <= rrd_id:
                break
            rrd_id = last_rrd
            await asyncio.sleep(WB_FINANCE_MIN_SPACING_SECONDS)
    normalized_rows = [
        SimpleNamespace(**row)
        for row in FinanceSyncService._normalize_realization_rows(account_id, all_rows)
    ]
    return {
        "balance": balance_payload,
        "reports": _as_list(reports_payload, "report", "reports", "data"),
        "report_rows_raw": all_rows,
        "report_rows": normalized_rows,
    }


def _resolve_sku_id(row: Any, sku_maps: dict[str, dict[Any, Any]]) -> int | None:
    resolved = sku_maps["mart_service"]._resolve_core_sku(
        sku_maps["core_index"],
        vendor_code=getattr(row, "vendor_code", None),
        nm_id=getattr(row, "nm_id", None),
        barcode=getattr(row, "barcode", None),
        tech_size=None,
    )
    if resolved is not None:
        return int(resolved.id)
    barcode_key = (getattr(row, "nm_id", None), getattr(row, "barcode", None))
    vendor_key = (getattr(row, "nm_id", None), getattr(row, "vendor_code", None))
    return sku_maps["by_nm_barcode"].get(barcode_key) or sku_maps["by_nm_vendor"].get(vendor_key)


def _aggregate_direct_wb_rows(
    rows: list[Any],
    *,
    sku_maps: dict[str, dict[Any, Any]],
) -> dict[str, Any]:
    account_bucket = _bucket_template()
    per_sku: dict[int, dict[str, Any]] = {}
    per_nm: dict[int, dict[str, Any]] = {}
    unmatched_rows_count = 0
    unmatched_revenue = Decimal("0")
    unmatched_expenses = Decimal("0")

    def get_bucket(storage: dict[int, dict[str, Any]], key: int, row: Any) -> dict[str, Any]:
        bucket = storage.get(key)
        if bucket is None:
            bucket = _bucket_template()
            bucket["sku_id"] = key if storage is per_sku else None
            bucket["nm_id"] = key if storage is per_nm else getattr(row, "nm_id", None)
            bucket["vendor_code"] = getattr(row, "vendor_code", None)
            bucket["barcode"] = getattr(row, "barcode", None)
            storage[key] = bucket
        return bucket

    def apply_row(bucket: dict[str, Any], row: Any, expense_totals: dict[str, Decimal]) -> None:
        if MartService._is_reconcilable_finance_row(row):
            quantity = int(getattr(row, "quantity", None) or 1)
            sign = MartService._finance_sign(row)
            bucket["finance_rows"] += 1
            bucket["net_units"] += quantity * sign
            if sign > 0:
                bucket["gross_units"] += quantity
            else:
                bucket["return_units"] += quantity
            bucket["realized_revenue"] += MartService._signed_finance_amount(row, getattr(row, "retail_amount", None))
            bucket["for_pay"] += MartService._signed_finance_amount(row, getattr(row, "for_pay", None))
        bucket["wb_commission"] += expense_totals["wb_commission"]
        bucket["payment_processing"] += expense_totals["payment_processing"]
        bucket["pvz_reward"] += expense_totals["pvz_reward"]
        bucket["wb_logistics"] += expense_totals["wb_logistics"]
        bucket["wb_logistics_rebill"] += expense_totals["wb_logistics_rebill"]
        bucket["acceptance"] += expense_totals["acceptance"]
        bucket["penalty"] += expense_totals["penalty"]
        bucket["deduction"] += expense_totals["deduction"]
        bucket["marketing_deduction"] += expense_totals["marketing_deduction"]
        bucket["loyalty"] += expense_totals["loyalty"]
        bucket["other_wb_expenses"] += expense_totals["unclassified"]
        bucket["storage"] += expense_totals["storage"]
        bucket["additional_payments"] += expense_totals["additional_payment"]

    for row in rows:
        sku_id = _resolve_sku_id(row, sku_maps)
        details = MartService._finance_expense_details(row, sku_id=sku_id)
        expense_totals = details["totals"]
        apply_row(account_bucket, row, expense_totals)
        if getattr(row, "nm_id", None) is not None:
            apply_row(get_bucket(per_nm, int(row.nm_id), row), row, expense_totals)
        if sku_id is not None:
            apply_row(get_bucket(per_sku, int(sku_id), row), row, expense_totals)
        else:
            unmatched_rows_count += 1
            unmatched_revenue += MartService._signed_finance_amount(row, getattr(row, "retail_amount", None))
            unmatched_expenses += normalized_wb_expenses_total(SimpleNamespace(**expense_totals))

    finalized_sku = {key: _finalize_bucket(bucket) for key, bucket in per_sku.items()}
    finalized_nm = {key: _finalize_bucket(bucket) for key, bucket in per_nm.items()}
    return {
        "account": _finalize_bucket(account_bucket),
        "by_sku": finalized_sku,
        "by_nm": finalized_nm,
        "unmatched_rows_count": unmatched_rows_count,
        "unmatched_revenue": unmatched_revenue,
        "unmatched_wb_expenses": unmatched_expenses,
    }


async def _data_health_manual_subset(account_id: int, date_from: date, date_to: date) -> dict[str, Any]:
    async with SessionLocal() as session:
        issues = list(
            (
                await session.execute(
                    select(DataQualityIssue).where(
                        DataQualityIssue.account_id == account_id,
                        DataQualityIssue.resolved_at.is_(None),
                        DataQualityIssue.detected_at >= datetime.combine(date_from, datetime.min.time()),
                        DataQualityIssue.detected_at <= datetime.combine(date_to, datetime.max.time()),
                    )
                )
            ).scalars()
        )
        runs = list(
            (
                await session.execute(
                    select(WBSyncRun).where(WBSyncRun.account_id == account_id).order_by(WBSyncRun.id.desc())
                )
            ).scalars()
        )
        cursors = list(
            (
                await session.execute(
                    select(WBSyncCursor).where(WBSyncCursor.account_id == account_id, WBSyncCursor.cursor_key == "default")
                )
            ).scalars()
        )
        active_sku_count, active_sku_with_manual_cost_count = (
            await session.execute(
                select(
                    func.count(CoreSKU.id),
                    func.count(CoreSKU.id).filter(
                        and_(
                            CoreSKU.id.in_(select(ManualCost.sku_id).where(ManualCost.account_id == account_id)),
                        )
                    ),
                ).where(CoreSKU.account_id == account_id, CoreSKU.is_active.is_(True))
            )
        ).one()
        mart_stats = (
            await session.execute(
                select(
                    func.count(MartSKUDaily.id).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(True))),
                    func.count(MartSKUDaily.id).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(False))),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(True))), 0),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_manual_cost.is_(False))), 0),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_real_manual_cost.is_(True))), 0),
                    func.coalesce(func.sum(MartSKUDaily.final_revenue).filter(and_(MartSKUDaily.final_revenue.is_not(None), MartSKUDaily.final_revenue > 0, MartSKUDaily.has_placeholder_cost.is_(True))), 0),
                ).where(
                    MartSKUDaily.account_id == account_id,
                    MartSKUDaily.stat_date >= date_from,
                    MartSKUDaily.stat_date <= date_to,
                )
            )
        ).one()
        latest_run_by_domain: dict[str, Any] = {}
        for run in runs:
            latest_run_by_domain.setdefault(run.domain, run)
        failed_domains = sorted([domain for domain, run in latest_run_by_domain.items() if run.status == "failed"])
        skipped_domains = sorted([domain for domain, run in latest_run_by_domain.items() if run.status == "skipped"])
        latest_stocks_status = latest_run_by_domain.get("stocks").status if latest_run_by_domain.get("stocks") else None
        classified_unmatched = 0
        unmatched_open = 0
        for issue in issues:
            issue_sku_id, issue_nm_id = extract_issue_refs(
                sku_id=issue.sku_id,
                nm_id=issue.nm_id,
                entity_key=issue.entity_key,
                payload=issue.payload,
            )
            del issue_sku_id, issue_nm_id
            if issue.code == "unmatched_sku":
                classification_status = str((issue.payload or {}).get("classificationStatus") or "").lower()
                if classification_status in {"classified", "ignored", "mapped"}:
                    classified_unmatched += 1
                else:
                    unmatched_open += 1
        return {
            "open_issues_total": len(issues),
            "failed_domains": failed_domains,
            "skipped_domains": skipped_domains,
            "missing_manual_cost_count": sum(1 for issue in issues if issue.code == "missing_manual_cost"),
            "unmatched_sku_count": unmatched_open,
            "duplicate_srid_count": sum(1 for issue in issues if issue.code == "duplicate_srid"),
            "active_sku_count": int(active_sku_count or 0),
            "active_sku_with_manual_cost_count": int(active_sku_with_manual_cost_count or 0),
            "revenue_rows_with_cost": int(mart_stats[0] or 0),
            "revenue_rows_without_cost": int(mart_stats[1] or 0),
            "revenue_with_cost": float(_decimal(mart_stats[2])),
            "revenue_without_cost": float(_decimal(mart_stats[3])),
            "revenue_with_real_cost": float(_decimal(mart_stats[4])),
            "revenue_with_placeholder_cost": float(_decimal(mart_stats[5])),
            "classified_unmatched_sku_count": classified_unmatched,
            "latest_stocks_status": latest_stocks_status,
            "cursor_domains": sorted(cursor.domain for cursor in cursors),
        }


def _build_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    finance = report["finance_api_audit"]
    dashboards = report["dashboard_audit"]
    findings = report["findings"]
    lines = [
        "# Dashboard And Finance vs WB Audit",
        "",
        f"- Generated: `{meta['generated_at']}`",
        f"- Backend: `{meta['base_url']}`",
        f"- Account: `{meta['account_name']}` (`{meta['account_id']}`)",
        f"- Window: `{meta['date_from']}` .. `{meta['date_to']}`",
        f"- WB direct report rows: `{meta['wb_report_rows_count']}`",
        "",
        "## Finance APIs",
        "",
        f"- `/balance`: `{finance['balance']['status']}`",
        f"- `/finance/reports`: `{finance['reports']['status']}`",
        f"- `/finance/report-rows`: `{finance['report_rows']['status']}`",
        "",
        "## Dashboards",
        "",
        f"- `/dashboard/owner`: `{dashboards['owner']['status']}`",
        f"- `/dashboard/sku-profitability`: `{dashboards['sku_profitability']['status']}`",
        f"- `/dashboard/article-audit` samples: `{dashboards['article_audit_samples']['status']}`",
        f"- `/dashboard/data-health`: `{dashboards['data_health']['status']}`",
        "",
        "## Key Numbers",
        "",
        f"- WB logistics total: `{finance['report_rows']['wb_summary']['sum_logistics']}`",
        f"- WB expense total from direct rows: `{dashboards['owner']['wb_direct_subset']['total_wb_expenses']}`",
        f"- Owner dashboard logistics share: `{dashboards['owner']['api_subset']['expense_breakdown']['logistics_share_percent']}`",
        "",
        "## Findings",
        "",
    ]
    if findings:
        for finding in findings:
            lines.append(f"- {finding}")
    else:
        lines.append("- No mismatches detected in the audited fields.")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- `data-health` has no direct WB API equivalent, so it was checked against internal DB state instead.")
    lines.append("- `article-audit` is parameterized by `nm_id`; the audit used representative live samples rather than every article.")
    return "\n".join(lines)


async def run_audit() -> dict[str, Any]:
    now = _utc_now()
    base_url = os.getenv("BACKEND_AUDIT_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    email = os.getenv("BACKEND_AUDIT_EMAIL", DEFAULT_EMAIL)
    password = _required_env("BACKEND_AUDIT_PASSWORD")
    account_name = os.getenv("BACKEND_AUDIT_ACCOUNT_NAME", DEFAULT_ACCOUNT_NAME)
    date_from = date.fromisoformat(os.getenv("BACKEND_AUDIT_DATE_FROM", DEFAULT_DATE_FROM.isoformat()))
    date_to = date.fromisoformat(os.getenv("BACKEND_AUDIT_DATE_TO", DEFAULT_DATE_TO.isoformat()))

    account_id = await _resolve_account_id(account_name)
    _progress(f"resolved account_id={account_id}")
    sku_maps = await _load_core_sku_maps(account_id)
    _progress(f"loaded sku maps barcode={len(sku_maps['by_nm_barcode'])} vendor={len(sku_maps['by_nm_vendor'])}")

    async with BackendAuditClient(base_url=base_url, email=email, password=password) as backend:
        _progress("backend login complete")
        finance_reports = await backend.get_all_pages(
            "/finance/reports",
            params={
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        finance_report_rows = await backend.get_json(
            "/finance/report-rows",
            params={
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                "aggregate": "true",
                "limit": PAGE_LIMIT,
                "offset": 0,
            },
        )
        balances = await backend.get_all_pages(
            "/balance",
            params={
                "account_id": account_id,
            },
        )
        owner_dashboard = await backend.get_json(
            "/dashboard/owner",
            params={
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        data_health = await backend.get_json(
            "/dashboard/data-health",
            params={
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )
        sku_profitability = await backend.get_all_pages(
            "/dashboard/sku-profitability",
            params={
                "account_id": account_id,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )

        profitability_items = list(sku_profitability["items"])
        sample_nm_ids: list[int] = []
        by_revenue = sorted(
            [item for item in profitability_items if item.get("nm_id") is not None],
            key=lambda item: _decimal(item.get("realized_revenue")),
            reverse=True,
        )
        if by_revenue:
            sample_nm_ids.append(int(by_revenue[0]["nm_id"]))
        by_logistics = sorted(
            [item for item in profitability_items if item.get("nm_id") is not None],
            key=lambda item: _decimal(item.get("wb_logistics")) + _decimal(item.get("wb_logistics_rebill")),
            reverse=True,
        )
        if by_logistics:
            nm_id = int(by_logistics[0]["nm_id"])
            if nm_id not in sample_nm_ids:
                sample_nm_ids.append(nm_id)
        by_loss = [item for item in profitability_items if item.get("nm_id") is not None and _decimal(item.get("net_profit_after_all_expenses")) < 0]
        if by_loss:
            nm_id = int(by_loss[0]["nm_id"])
            if nm_id not in sample_nm_ids:
                sample_nm_ids.append(nm_id)
        article_audits: dict[int, Any] = {}
        for nm_id in sample_nm_ids[:3]:
            article_audits[nm_id] = await backend.get_json(
                "/dashboard/article-audit",
                params={
                    "account_id": account_id,
                    "nm_id": nm_id,
                    "date_from": date_from.isoformat(),
                    "date_to": date_to.isoformat(),
                },
            )
        _progress(
            f"backend endpoints loaded reports={finance_reports.get('total')} report_rows_total={finance_report_rows.get('total')} "
            f"sku_profitability={sku_profitability.get('total')} article_samples={len(article_audits)}"
        )

    _progress("fetching direct WB finance")
    wb_direct = await _fetch_direct_wb_finance(
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )
    _progress(f"direct WB fetched reports={len(wb_direct['reports'])} rows={len(wb_direct['report_rows'])}")
    direct_aggregates = _aggregate_direct_wb_rows(wb_direct["report_rows"], sku_maps=sku_maps)
    _progress(
        f"aggregated direct WB account_wb_expenses={_float0(direct_aggregates['account']['total_wb_expenses'])} "
        f"sku_buckets={len(direct_aggregates['by_sku'])} nm_buckets={len(direct_aggregates['by_nm'])}"
    )
    data_health_manual = await _data_health_manual_subset(account_id, date_from, date_to)
    _progress("loaded manual data-health subset")

    wb_report_ids = sorted(int(item.get("reportId") or item.get("id")) for item in wb_direct["reports"] if item.get("reportId") or item.get("id"))
    api_report_ids = sorted(int(item.get("report_id")) for item in finance_reports["items"] if item.get("report_id") is not None)

    wb_row_rrd_ids = sorted(int(getattr(row, "rrd_id")) for row in wb_direct["report_rows"] if getattr(row, "rrd_id", None) is not None)
    wb_row_rrd_set = set(wb_row_rrd_ids)

    wb_row_summary = {
        "rows_count": len(wb_direct["report_rows"]),
        "sum_retail_amount": _float0(sum((_decimal(getattr(row, "retail_amount", None)) for row in wb_direct["report_rows"]), start=Decimal("0"))),
        "sum_for_pay": _float0(sum((_decimal(getattr(row, "for_pay", None)) for row in wb_direct["report_rows"]), start=Decimal("0"))),
        "sum_logistics": _float0(direct_aggregates["account"]["wb_logistics"] + direct_aggregates["account"]["wb_logistics_rebill"]),
        "sum_storage": _float0(direct_aggregates["account"]["storage"]),
        "sum_paid_acceptance": _float0(direct_aggregates["account"]["acceptance"]),
        "sum_penalty": _float0(direct_aggregates["account"]["penalty"]),
        "sum_deduction": _float0(sum((_decimal(getattr(row, "deduction", None)) for row in wb_direct["report_rows"]), start=Decimal("0"))),
        "sum_additional_payment": _float0(sum((_decimal(getattr(row, "additional_payment", None)) for row in wb_direct["report_rows"]), start=Decimal("0"))),
    }

    latest_api_balance = balances["items"][0] if balances["items"] else None
    wb_balance = dict(wb_direct["balance"] or {})
    finance_balance_status = "match"
    finance_balance_notes: list[str] = []
    if latest_api_balance is None:
        finance_balance_status = "mismatch"
        finance_balance_notes.append("Backend /balance returned no snapshots.")
    else:
        if not _match_decimal(latest_api_balance.get("current"), wb_balance.get("current")):
            finance_balance_status = "mismatch"
            finance_balance_notes.append("`current` differs from live WB balance.")
        if not _match_decimal(latest_api_balance.get("for_withdraw"), wb_balance.get("for_withdraw")):
            finance_balance_status = "mismatch"
            finance_balance_notes.append("`for_withdraw` differs from live WB balance.")

    finance_reports_status = "match"
    finance_reports_notes: list[str] = []
    if api_report_ids != wb_report_ids:
        finance_reports_status = "mismatch"
        finance_reports_notes.append("Report ID sets differ.")

    finance_rows_summary = finance_report_rows.get("summary") or {}
    finance_row_matches = [
        int(finance_report_rows.get("total") or 0) == len(wb_row_rrd_ids),
        _match_decimal(finance_rows_summary.get("sum_retail_amount"), wb_row_summary["sum_retail_amount"]),
        _match_decimal(finance_rows_summary.get("sum_for_pay"), wb_row_summary["sum_for_pay"]),
        _match_decimal(finance_rows_summary.get("sum_logistics"), wb_row_summary["sum_logistics"]),
        _match_decimal(finance_rows_summary.get("sum_storage"), wb_row_summary["sum_storage"]),
        _match_decimal(finance_rows_summary.get("sum_paid_acceptance"), wb_row_summary["sum_paid_acceptance"]),
        _match_decimal(finance_rows_summary.get("sum_penalty"), wb_row_summary["sum_penalty"]),
        _match_decimal(finance_rows_summary.get("sum_deduction"), wb_row_summary["sum_deduction"]),
        _match_decimal(finance_rows_summary.get("sum_additional_payment"), wb_row_summary["sum_additional_payment"]),
    ]
    finance_rows_status = _status(finance_row_matches)

    owner_api_subset = {
        "revenue_final": _api_get(owner_dashboard, "revenue_final", default=0),
        "total_wb_expenses": _api_get(owner_dashboard, "total_wb_expenses", default=0),
        "ad_spend_finance": _api_get(owner_dashboard, "ad_spend_finance", default=0),
        "ad_spend_final": _api_get(owner_dashboard, "ad_spend_final", default=0),
        "expense_breakdown": {
            "total_wb_expenses": _api_get(owner_dashboard, "expense_breakdown", "total_wb_expenses", default=0),
            "logistics_total": _api_get(owner_dashboard, "expense_breakdown", "logistics_total", default=0),
            "logistics_share_base_kind": _api_get(owner_dashboard, "expense_breakdown", "logistics_share_base_kind", default=""),
            "logistics_share_base_amount": _api_get(owner_dashboard, "expense_breakdown", "logistics_share_base_amount", default=0),
            "logistics_share_percent": _api_get(owner_dashboard, "expense_breakdown", "logistics_share_percent", default=0),
        },
    }
    owner_wb_subset = {
        "revenue_final": _float0(direct_aggregates["account"]["revenue_final"]),
        "total_wb_expenses": _float0(direct_aggregates["account"]["total_wb_expenses"]),
        "ad_spend_finance": _float0(direct_aggregates["account"]["ad_spend_finance"]),
        "ad_spend_final": _float0(direct_aggregates["account"]["ad_spend_final"]),
        "expense_breakdown": {
            "total_wb_expenses": _float0(direct_aggregates["account"]["total_wb_expenses"]),
            "logistics_total": _float0(direct_aggregates["account"]["logistics"]),
            "logistics_share_base_kind": "wb_expenses",
            "logistics_share_base_amount": _float0(direct_aggregates["account"]["total_wb_expenses"]),
            "logistics_share_percent": _float0(
                (direct_aggregates["account"]["logistics"] / direct_aggregates["account"]["total_wb_expenses"] * Decimal("100"))
                if direct_aggregates["account"]["total_wb_expenses"] > 0
                else Decimal("0")
            ),
        },
    }
    owner_matches = [
        _match_decimal(owner_api_subset["revenue_final"], owner_wb_subset["revenue_final"]),
        _match_decimal(owner_api_subset["total_wb_expenses"], owner_wb_subset["total_wb_expenses"]),
        _match_decimal(owner_api_subset["ad_spend_finance"], owner_wb_subset["ad_spend_finance"]),
        _match_decimal(owner_api_subset["ad_spend_final"], owner_wb_subset["ad_spend_final"]),
        _match_decimal(owner_api_subset["expense_breakdown"]["total_wb_expenses"], owner_wb_subset["expense_breakdown"]["total_wb_expenses"]),
        _match_decimal(owner_api_subset["expense_breakdown"]["logistics_total"], owner_wb_subset["expense_breakdown"]["logistics_total"]),
        owner_api_subset["expense_breakdown"]["logistics_share_base_kind"] == owner_wb_subset["expense_breakdown"]["logistics_share_base_kind"],
        _match_decimal(owner_api_subset["expense_breakdown"]["logistics_share_base_amount"], owner_wb_subset["expense_breakdown"]["logistics_share_base_amount"]),
        _match_decimal(owner_api_subset["expense_breakdown"]["logistics_share_percent"], owner_wb_subset["expense_breakdown"]["logistics_share_percent"]),
    ]

    comparable_sku_fields_counts = ["finance_rows", "gross_units", "return_units", "net_units"]
    comparable_sku_fields_decimals = [
        "realized_revenue",
        "revenue_final",
        "for_pay",
        "wb_commission",
        "payment_processing",
        "pvz_reward",
        "wb_logistics",
        "wb_logistics_rebill",
        "acceptance",
        "penalty",
        "deduction",
        "marketing_deduction",
        "loyalty",
        "other_wb_expenses",
        "total_wb_expenses",
        "additional_income",
        "commission",
        "acquiring_fee",
        "logistics",
        "paid_acceptance",
        "storage",
        "penalties",
        "deductions",
        "additional_payments",
        "ad_spend_finance",
        "ad_spend_final",
    ]
    sku_row_mismatches: list[dict[str, Any]] = []
    matched_sku_rows = 0
    for api_row in profitability_items:
        sku_id = api_row.get("sku_id")
        if sku_id is None:
            continue
        wb_row = direct_aggregates["by_sku"].get(int(sku_id))
        if wb_row is None:
            sku_row_mismatches.append(
                {
                    "sku_id": sku_id,
                    "nm_id": api_row.get("nm_id"),
                    "vendor_code": api_row.get("vendor_code"),
                    "reason": "No direct WB aggregate row mapped to this SKU.",
                }
            )
            continue
        count_mismatches = _compare_count_fields(api_row, wb_row, comparable_sku_fields_counts)
        decimal_mismatches = _compare_numeric_fields(api_row, wb_row, comparable_sku_fields_decimals)
        if count_mismatches or decimal_mismatches:
            sku_row_mismatches.append(
                {
                    "sku_id": sku_id,
                    "nm_id": api_row.get("nm_id"),
                    "vendor_code": api_row.get("vendor_code"),
                    "count_mismatches": count_mismatches,
                    "decimal_mismatches": decimal_mismatches,
                }
            )
        else:
            matched_sku_rows += 1
    _progress(f"compared sku profitability rows matched={matched_sku_rows} mismatches={len(sku_row_mismatches)}")

    article_samples_results: list[dict[str, Any]] = []
    for nm_id, payload in article_audits.items():
        wb_row = direct_aggregates["by_nm"].get(int(nm_id), _bucket_template())
        api_finance = payload.get("finance") or {}
        api_reconciliation = payload.get("reconciliation") or {}
        wb_finance = {
            "report_rows_count": int(wb_row.get("finance_rows") or 0),
            "gross_units": int(wb_row.get("gross_units") or 0),
            "return_units": int(wb_row.get("return_units") or 0),
            "net_units": int(wb_row.get("net_units") or 0),
            "realized_revenue": _float0(wb_row.get("realized_revenue")),
            "revenue_final": _float0(wb_row.get("revenue_final")),
            "for_pay": _float0(wb_row.get("for_pay")),
            "wb_logistics": _float0(wb_row.get("wb_logistics")),
            "wb_logistics_rebill": _float0(wb_row.get("wb_logistics_rebill")),
            "payment_processing": _float0(wb_row.get("payment_processing")),
            "storage": _float0(wb_row.get("storage")),
            "penalty": _float0(wb_row.get("penalty")),
            "deduction": _float0(wb_row.get("deduction")),
            "marketing_deduction": _float0(wb_row.get("marketing_deduction")),
            "total_wb_expenses": _float0(wb_row.get("total_wb_expenses")),
            "additional_income": _float0(wb_row.get("additional_income")),
            "ad_spend_finance": _float0(wb_row.get("ad_spend_finance")),
            "ad_spend_final": _float0(wb_row.get("ad_spend_final")),
        }
        sample_matches = [
            _match_int(api_finance.get("report_rows_count"), wb_finance["report_rows_count"]),
            _match_int(api_finance.get("gross_units"), wb_finance["gross_units"]),
            _match_int(api_finance.get("return_units"), wb_finance["return_units"]),
            _match_int(api_finance.get("net_units"), wb_finance["net_units"]),
            _match_decimal(api_finance.get("realized_revenue"), wb_finance["realized_revenue"]),
            _match_decimal(api_finance.get("for_pay"), wb_finance["for_pay"]),
            _match_decimal(api_finance.get("wb_logistics"), wb_finance["wb_logistics"]),
            _match_decimal(api_finance.get("wb_logistics_rebill"), wb_finance["wb_logistics_rebill"]),
            _match_decimal(api_finance.get("payment_processing"), wb_finance["payment_processing"]),
            _match_decimal(api_finance.get("storage"), wb_finance["storage"]),
            _match_decimal(api_finance.get("penalty"), wb_finance["penalty"]),
            _match_decimal(api_finance.get("deduction"), wb_finance["deduction"]),
            _match_decimal(api_finance.get("marketing_deduction"), wb_finance["marketing_deduction"]),
            _match_decimal(api_finance.get("total_wb_expenses"), wb_finance["total_wb_expenses"]),
            _match_decimal(api_finance.get("ad_spend_finance"), wb_finance["ad_spend_finance"]),
            _match_decimal(api_finance.get("ad_spend_final"), wb_finance["ad_spend_final"]),
        ]
        article_samples_results.append(
            {
                "nm_id": nm_id,
                "status": _status(sample_matches),
                "api_finance": {
                    "report_rows_count": api_finance.get("report_rows_count"),
                    "gross_units": api_finance.get("gross_units"),
                    "return_units": api_finance.get("return_units"),
                    "net_units": api_finance.get("net_units"),
                    "realized_revenue": api_finance.get("realized_revenue"),
                    "for_pay": api_finance.get("for_pay"),
                    "wb_logistics": api_finance.get("wb_logistics"),
                    "wb_logistics_rebill": api_finance.get("wb_logistics_rebill"),
                    "payment_processing": api_finance.get("payment_processing"),
                    "storage": api_finance.get("storage"),
                    "penalty": api_finance.get("penalty"),
                    "deduction": api_finance.get("deduction"),
                    "marketing_deduction": api_finance.get("marketing_deduction"),
                    "total_wb_expenses": api_finance.get("total_wb_expenses"),
                    "ad_spend_finance": api_finance.get("ad_spend_finance"),
                    "ad_spend_final": api_finance.get("ad_spend_final"),
                },
                "wb_finance": wb_finance,
                "api_reconciliation": {
                    "revenue_matches_mart": api_reconciliation.get("revenue_matches_mart"),
                    "finance_report_revenue_total": api_reconciliation.get("finance_report_revenue_total"),
                },
            }
        )
    _progress(
        "compared article audit samples "
        + ", ".join(f"{sample['nm_id']}={sample['status']}" for sample in article_samples_results)
    )

    data_health_matches = [
        _match_int(data_health.get("open_issues_total"), data_health_manual["open_issues_total"]),
        sorted(data_health.get("failed_domains") or []) == data_health_manual["failed_domains"],
        sorted(data_health.get("skipped_domains") or []) == data_health_manual["skipped_domains"],
        _match_int(data_health.get("missing_manual_cost_count"), data_health_manual["missing_manual_cost_count"]),
        _match_int(data_health.get("unmatched_sku_count"), data_health_manual["unmatched_sku_count"]),
        _match_int(data_health.get("duplicate_srid_count"), data_health_manual["duplicate_srid_count"]),
        _match_int(data_health.get("active_sku_count"), data_health_manual["active_sku_count"]),
        _match_int(data_health.get("active_sku_with_manual_cost_count"), data_health_manual["active_sku_with_manual_cost_count"]),
        _match_int(data_health.get("revenue_rows_with_cost"), data_health_manual["revenue_rows_with_cost"]),
        _match_int(data_health.get("revenue_rows_without_cost"), data_health_manual["revenue_rows_without_cost"]),
        _match_decimal(data_health.get("revenue_with_cost"), data_health_manual["revenue_with_cost"]),
        _match_decimal(data_health.get("revenue_without_cost"), data_health_manual["revenue_without_cost"]),
        _match_decimal(data_health.get("revenue_with_real_cost"), data_health_manual["revenue_with_real_cost"]),
        _match_decimal(data_health.get("revenue_with_placeholder_cost"), data_health_manual["revenue_with_placeholder_cost"]),
        _match_int(data_health.get("classified_unmatched_sku_count"), data_health_manual["classified_unmatched_sku_count"]),
        (data_health.get("latest_stocks_status") == data_health_manual["latest_stocks_status"]),
    ]

    findings: list[str] = []
    if finance_balance_status != "match":
        findings.extend(finance_balance_notes)
    if finance_reports_status != "match":
        findings.extend(finance_reports_notes)
    if finance_rows_status != "match":
        findings.append(
            f"/finance/report-rows mismatch: api_total={int(finance_report_rows.get('total') or 0)} "
            f"wb_total={len(wb_row_rrd_ids)}"
        )
    if not all(owner_matches):
        findings.append("/dashboard/owner finance-backed fields differ from direct WB aggregates.")
    if sku_row_mismatches:
        findings.append(f"/dashboard/sku-profitability has {len(sku_row_mismatches)} mismatched rows out of {len(profitability_items)}.")
    if any(sample["status"] != "match" for sample in article_samples_results):
        findings.append("/dashboard/article-audit sample finance sections differ from direct WB aggregates.")
    if not all(data_health_matches):
        findings.append("/dashboard/data-health differs from internal DB state.")

    report = {
        "meta": {
            "generated_at": now.isoformat(),
            "base_url": base_url,
            "account_name": account_name,
            "account_id": account_id,
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "wb_report_rows_count": len(wb_direct["report_rows"]),
            "api_finance_report_rows_count": int(finance_report_rows.get("total") or 0),
            "api_sku_profitability_rows_count": len(profitability_items),
        },
        "finance_api_audit": {
            "balance": {
                "status": finance_balance_status,
                "api_latest": latest_api_balance,
                "wb_current": wb_balance,
                "notes": finance_balance_notes,
            },
            "reports": {
                "status": finance_reports_status,
                "api_total": len(api_report_ids),
                "wb_total": len(wb_report_ids),
                "missing_report_ids": sorted(set(wb_report_ids) - set(api_report_ids))[:50],
                "extra_report_ids": sorted(set(api_report_ids) - set(wb_report_ids))[:50],
                "notes": finance_reports_notes,
            },
            "report_rows": {
                "status": finance_rows_status,
                "api_total": int(finance_report_rows.get("total") or 0),
                "wb_total": len(wb_row_rrd_ids),
                "api_sample_rrd_ids": sorted(
                    int(item.get("rrd_id"))
                    for item in finance_report_rows.get("items", [])
                    if item.get("rrd_id") is not None
                )[:20],
                "wb_sample_rrd_ids": sorted(wb_row_rrd_set)[:20],
                "api_summary": finance_rows_summary,
                "wb_summary": wb_row_summary,
            },
        },
        "dashboard_audit": {
            "owner": {
                "status": _status(owner_matches),
                "api_subset": owner_api_subset,
                "wb_direct_subset": owner_wb_subset,
            },
            "sku_profitability": {
                "status": "match" if not sku_row_mismatches else "mismatch",
                "api_total_rows": len(profitability_items),
                "direct_wb_mapped_rows": len(direct_aggregates["by_sku"]),
                "matched_rows": matched_sku_rows,
                "mismatched_rows_count": len(sku_row_mismatches),
                "unmatched_wb_rows_count": direct_aggregates["unmatched_rows_count"],
                "unmatched_wb_revenue": _float0(direct_aggregates["unmatched_revenue"]),
                "unmatched_wb_expenses": _float0(direct_aggregates["unmatched_wb_expenses"]),
                "sample_mismatches": sku_row_mismatches[:20],
            },
            "article_audit_samples": {
                "status": "match" if all(sample["status"] == "match" for sample in article_samples_results) else "mismatch",
                "samples": article_samples_results,
            },
            "data_health": {
                "status": "match" if all(data_health_matches) else "mismatch",
                "source_of_truth": "internal_db",
                "api_subset": {
                    "open_issues_total": data_health.get("open_issues_total"),
                    "failed_domains": data_health.get("failed_domains"),
                    "skipped_domains": data_health.get("skipped_domains"),
                    "missing_manual_cost_count": data_health.get("missing_manual_cost_count"),
                    "unmatched_sku_count": data_health.get("unmatched_sku_count"),
                    "duplicate_srid_count": data_health.get("duplicate_srid_count"),
                    "active_sku_count": data_health.get("active_sku_count"),
                    "active_sku_with_manual_cost_count": data_health.get("active_sku_with_manual_cost_count"),
                    "revenue_rows_with_cost": data_health.get("revenue_rows_with_cost"),
                    "revenue_rows_without_cost": data_health.get("revenue_rows_without_cost"),
                    "revenue_with_cost": data_health.get("revenue_with_cost"),
                    "revenue_without_cost": data_health.get("revenue_without_cost"),
                    "revenue_with_real_cost": data_health.get("revenue_with_real_cost"),
                    "revenue_with_placeholder_cost": data_health.get("revenue_with_placeholder_cost"),
                    "classified_unmatched_sku_count": data_health.get("classified_unmatched_sku_count"),
                    "latest_stocks_status": data_health.get("latest_stocks_status"),
                },
                "manual_subset": data_health_manual,
                "note": "No direct WB API equivalent exists for data-health; it was compared to internal DB state.",
            },
        },
        "findings": findings,
    }
    _progress("assembled report payload")
    return report


def main() -> None:
    report = asyncio.run(run_audit())
    now = datetime.fromisoformat(report["meta"]["generated_at"])
    bundle_slug = f"dashboard_finance_vs_wb_audit_{_slug_timestamp(now)}"
    bundle_dir = EXPORTS_DIR / bundle_slug
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    report_path = bundle_dir / "report.json"
    markdown_path = bundle_dir / "REPORT.md"
    doc_path = DOCS_DIR / f"dashboard_finance_vs_wb_audit_{report['meta']['date_to']}.md"
    _write_json(report_path, report)
    markdown = _build_markdown(report)
    _write_text(markdown_path, markdown)
    _write_text(doc_path, markdown)
    print(
        json.dumps(
            {
                "bundle_dir": str(bundle_dir),
                "report_json": str(report_path),
                "report_md": str(markdown_path),
                "doc_md": str(doc_path),
                "findings_total": len(report["findings"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
