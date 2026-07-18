from __future__ import annotations

from typing import Any

import httpx

from app.core.config import Settings, get_settings
from app.models.accounts import WBAccount
from app.schemas.portal import (
    PortalActionRead,
    PortalStockOpsInsightsRead,
    PortalStockOpsRunRead,
    PortalStockOpsRunRequest,
    PortalStockOpsRunsPage,
)


class StockOpsAdapter:
    """Optional read/analyze adapter for the external StockOps/TZostatka service."""

    SAFE_REFERENCE_ENDPOINTS = (
        "GET /api/health",
        "GET /api/state/latest",
        "GET /api/state/latest/overview",
        "GET /api/runs",
        "GET /api/runs/{run_id}",
        "GET /api/runs/{run_id}/overview",
        "GET /api/runs/{run_id}/sheets/{sheet_id}",
        "GET /api/export/latest",
        "GET /api/export/run/{run_id}",
    )

    FLOW_MATRIX = {
        "return_excess": {
            "finance_run_type": "return_excess",
            "external_business_mode": "return_excess",
            "safe_endpoints": [
                "GET /api/state/latest/overview?business_mode=return_excess",
                "GET /api/runs?business_mode=return_excess",
                "GET /api/runs/{run_id}/overview",
                "GET /api/runs/{run_id}/sheets/pickup",
                "GET /api/runs/{run_id}/sheets/residual-demand",
                "GET /api/export/run/{run_id}",
            ],
            "signals": ["stock_excess", "stock_shortage", "frozen_inventory_value"],
            "write_status": "disabled",
        },
        "ship_from_hand": {
            "finance_run_type": "ship_from_hand",
            "external_business_mode": "ship_from_hand",
            "safe_endpoints": [
                "GET /api/state/latest/overview?business_mode=ship_from_hand",
                "GET /api/runs?business_mode=ship_from_hand",
                "GET /api/runs/{run_id}/overview",
                "GET /api/runs/{run_id}/sheets/plan",
                "GET /api/runs/{run_id}/sheets/leftover-supply",
                "GET /api/runs/{run_id}/sheets/unresolved-demand",
                "GET /api/export/run/{run_id}",
            ],
            "signals": ["stock_shortage", "regional_redistribution", "stock_excess"],
            "write_status": "disabled",
        },
        "store_balance": {
            "finance_run_type": "store_balance",
            "external_business_mode": "store_percent_balance",
            "safe_endpoints": [
                "GET /api/state/latest/overview?business_mode=store_percent_balance",
                "GET /api/runs?business_mode=store_percent_balance",
                "GET /api/runs/{run_id}/overview",
                "GET /api/runs/{run_id}/sheets/return_plan",
                "GET /api/runs/{run_id}/sheets/ship_plan",
                "GET /api/export/run/{run_id}",
            ],
            "signals": ["stock_excess", "stock_shortage", "regional_redistribution"],
            "write_status": "disabled",
        },
    }

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url)

    async def health(self) -> tuple[str, str | None]:
        if not self.is_configured:
            return "not_configured", "stockops_base_url is not configured"
        try:
            payload = await self._request("GET", "/api/health", auth=False)
        except Exception:
            return "unavailable", "stockops service is not reachable"
        status = (
            str((payload or {}).get("status") or "").strip().lower()
            if isinstance(payload, dict)
            else ""
        )
        if status and status != "ok":
            return "unavailable", f"stockops health status is {status}"
        return "ok", None

    async def list_runs(
        self, *, account_id: int | None, run_type: str | None, limit: int, offset: int
    ) -> PortalStockOpsRunsPage:
        if not self.is_configured:
            return PortalStockOpsRunsPage(
                status="not_configured",
                limit=limit,
                offset=offset,
                message="stockops_base_url is not configured",
            )
        try:
            params: dict[str, Any] = {"limit": min(limit + offset, 200)}
            if run_type:
                params["business_mode"] = self._external_run_type(run_type)
            if account_id is not None:
                params["account_id"] = account_id
            payload = await self._request(
                "GET",
                "/api/runs",
                params=params,
            )
        except Exception:
            return PortalStockOpsRunsPage(
                status="unavailable",
                limit=limit,
                offset=offset,
                message="stockops service is unavailable",
            )

        rows = payload.get("runs") if isinstance(payload, dict) else []
        items = [
            self._run_from_payload(row)
            for row in rows or []
            if isinstance(row, dict)
            and self._row_matches_account(row, account_id=account_id)
        ]
        page_items = items[offset : offset + limit]
        return PortalStockOpsRunsPage(
            status="ok",
            total=len(items),
            limit=limit,
            offset=offset,
            items=page_items,
        )

    async def run_summary(
        self, *, account_id: int | None = None
    ) -> PortalStockOpsInsightsRead:
        if not self.is_configured:
            return PortalStockOpsInsightsRead(
                status="not_configured",
                account_id=account_id,
                message="stockops_base_url is not configured",
            )
        latest_runs = await self.latest_runs(account_id=account_id, limit=6)
        if latest_runs.status != "ok":
            return PortalStockOpsInsightsRead(
                status=latest_runs.status,
                account_id=account_id,
                latest_runs=latest_runs.items,
                message=latest_runs.message,
                unavailable_sources=["stockops"]
                if latest_runs.status == "unavailable"
                else [],
            )
        summary: dict[str, Any] = {
            "flow_matrix": self.compatibility_matrix(),
            "runs_by_type": {},
        }
        for item in latest_runs.items:
            key = str(item.run_type or "unknown")
            summary["runs_by_type"].setdefault(key, 0)
            summary["runs_by_type"][key] += 1
        return PortalStockOpsInsightsRead(
            status="ok" if latest_runs.items else "empty",
            account_id=account_id,
            summary=summary,
            latest_runs=latest_runs.items,
        )

    async def latest_runs(
        self, *, account_id: int | None, limit: int = 6
    ) -> PortalStockOpsRunsPage:
        return await self.list_runs(
            account_id=account_id, run_type=None, limit=limit, offset=0
        )

    async def regional_excess_shortage_candidates(
        self,
        *,
        account_id: int | None,
        nm_id: int | None = None,
        limit: int = 20,
    ) -> PortalStockOpsInsightsRead:
        if not self.is_configured:
            return PortalStockOpsInsightsRead(
                status="not_configured",
                account_id=account_id,
                nm_id=nm_id,
                message="stockops_base_url is not configured",
            )
        try:
            rows = await self._collect_candidate_rows(
                account_id=account_id, nm_id=nm_id, limit=limit
            )
        except Exception:
            return PortalStockOpsInsightsRead(
                status="unavailable",
                account_id=account_id,
                nm_id=nm_id,
                message="stockops service is unavailable",
                unavailable_sources=["stockops"],
            )
        runs = [item["run"] for item in rows if item.get("kind") == "run"]
        candidates = [
            item["candidate"] for item in rows if item.get("kind") == "candidate"
        ]
        summary = self._candidate_summary(candidates)
        return PortalStockOpsInsightsRead(
            status="ok" if candidates else "empty",
            account_id=account_id,
            nm_id=nm_id,
            summary=summary,
            latest_runs=runs[:6],
            regional_candidates=candidates[:limit],
            action_candidates=candidates[:limit],
        )

    async def stock_redistribution_action_candidates(
        self,
        account: WBAccount,
        *,
        nm_id: int | None = None,
        limit: int = 20,
    ) -> tuple[list[PortalActionRead], str | None]:
        insights = await self.regional_excess_shortage_candidates(
            account_id=account.id,
            nm_id=nm_id,
            limit=limit,
        )
        if insights.status == "not_configured":
            return [], None
        if insights.status == "unavailable":
            return [], "stockops"
        return [
            self._action_from_candidate(account_id=account.id, candidate=item)
            for item in insights.action_candidates or insights.regional_candidates
        ], None

    async def product_stock_insights(
        self,
        account: WBAccount,
        *,
        nm_id: int,
        limit: int = 10,
    ) -> PortalStockOpsInsightsRead:
        return await self.regional_excess_shortage_candidates(
            account_id=account.id, nm_id=nm_id, limit=limit
        )

    def compatibility_matrix(self) -> dict[str, Any]:
        return {key: dict(value) for key, value in self.FLOW_MATRIX.items()}

    async def run(self, payload: PortalStockOpsRunRequest) -> PortalStockOpsRunRead:
        if not self.is_configured:
            return PortalStockOpsRunRead(
                status="not_configured",
                run_type=payload.run_type,
                account_id=payload.account_id,
                message="stockops_base_url is not configured",
            )

        health_status, health_detail = await self.health()
        if health_status != "ok":
            return PortalStockOpsRunRead(
                status="unavailable",
                run_type=payload.run_type,
                account_id=payload.account_id,
                message=health_detail or "stockops service is unavailable",
            )

        return PortalStockOpsRunRead(
            status="not_started",
            run_type=payload.run_type,
            account_id=payload.account_id,
            message=(
                "StockOps is configured, but automatic run start is disabled in MVP. "
                "Use the external StockOps upload/analyze screen or add an explicit "
                "finance-side file handoff before enabling this."
            ),
            raw={
                "safe_reference_endpoints": list(self.SAFE_REFERENCE_ENDPOINTS),
                "requested_payload_keys": sorted(payload.payload.keys()),
            },
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        base_url = self._base_url
        if not base_url:
            raise RuntimeError("stockops is not configured")
        headers: dict[str, str] = {}
        if auth and self.settings.stockops_internal_token:
            headers["Authorization"] = f"Bearer {self.settings.stockops_internal_token}"
        timeout = httpx.Timeout(float(self.settings.stockops_http_timeout_seconds))
        async with httpx.AsyncClient(
            base_url=base_url, timeout=timeout, headers=headers
        ) as client:
            response = await client.request(method, path, params=params)
            response.raise_for_status()
            try:
                return response.json()
            except ValueError:
                return {}

    @property
    def _base_url(self) -> str:
        return str(self.settings.stockops_base_url or "").strip().rstrip("/")

    def _run_from_payload(self, payload: dict[str, Any]) -> PortalStockOpsRunRead:
        run_id = payload.get("id") or payload.get("run_id")
        run_type = (
            payload.get("business_mode")
            or payload.get("run_type")
            or payload.get("mode")
        )
        return PortalStockOpsRunRead(
            status=self._status(payload.get("status")),
            run_type=str(run_type) if run_type is not None else None,
            run_id=run_id,
            account_id=self._int(payload.get("account_id")),
            summary=self._summary(payload),
            export_url=None,
            raw=self._safe_payload(payload),
        )

    async def _collect_candidate_rows(
        self,
        *,
        account_id: int | None,
        nm_id: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        runs_page = await self.latest_runs(account_id=account_id, limit=12)
        if runs_page.status != "ok":
            if runs_page.status == "unavailable":
                raise RuntimeError("stockops runs unavailable")
            return []
        result: list[dict[str, Any]] = [
            {"kind": "run", "run": item} for item in runs_page.items
        ]
        for run in runs_page.items:
            if (
                len([item for item in result if item.get("kind") == "candidate"])
                >= limit
            ):
                break
            for sheet_id, action_type in self._candidate_sheets(run.run_type):
                sheet = await self._safe_sheet(
                    run.run_id, sheet_id=sheet_id, page_size=limit
                )
                for index, row in enumerate(self._sheet_rows(sheet), start=1):
                    candidate = self._candidate_from_row(
                        run=run,
                        sheet_id=sheet_id,
                        action_type=action_type,
                        row=row,
                        row_index=index,
                    )
                    if candidate is None:
                        continue
                    if nm_id is not None and candidate.get("nm_id") != nm_id:
                        continue
                    result.append({"kind": "candidate", "candidate": candidate})
                    if (
                        len(
                            [item for item in result if item.get("kind") == "candidate"]
                        )
                        >= limit
                    ):
                        break
                if (
                    len([item for item in result if item.get("kind") == "candidate"])
                    >= limit
                ):
                    break
        return result

    async def _safe_sheet(
        self, run_id: int | str | None, *, sheet_id: str, page_size: int
    ) -> dict[str, Any]:
        if run_id is None:
            return {}
        try:
            payload = await self._request(
                "GET",
                f"/api/runs/{run_id}/sheets/{sheet_id}",
                params={"page": 1, "page_size": min(max(page_size, 1), 100)},
            )
        except Exception:
            return {}
        return self._safe_payload(payload) if isinstance(payload, dict) else {}

    def _candidate_sheets(self, run_type: str | None) -> list[tuple[str, str]]:
        normalized = self._finance_run_type(run_type)
        if normalized == "return_excess":
            return [
                ("pickup", "stock_excess"),
                ("residual-demand", "stock_shortage"),
                ("movement", "regional_redistribution"),
            ]
        if normalized == "ship_from_hand":
            return [
                ("plan", "regional_redistribution"),
                ("unresolved-demand", "stock_shortage"),
                ("leftover-supply", "stock_excess"),
            ]
        if normalized == "store_balance":
            return [
                ("return_plan", "stock_excess"),
                ("ship_plan", "stock_shortage"),
                ("ship_plan", "regional_redistribution"),
            ]
        return []

    def _sheet_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        sheet = (
            payload.get("sheet") if isinstance(payload.get("sheet"), dict) else payload
        )
        rows = sheet.get("rows") if isinstance(sheet, dict) else []
        return [self._safe_payload(row) for row in rows or [] if isinstance(row, dict)]

    def _candidate_from_row(
        self,
        *,
        run: PortalStockOpsRunRead,
        sheet_id: str,
        action_type: str,
        row: dict[str, Any],
        row_index: int,
    ) -> dict[str, Any] | None:
        quantity = self._candidate_quantity(action_type=action_type, row=row)
        if quantity is not None and quantity <= 0:
            return None
        nm_id = self._int(
            row.get("nm_id")
            or row.get("wb_article")
            or row.get("store_1_nm_id")
            or row.get("store_2_nm_id")
        )
        source_id = self._candidate_source_id(
            run=run,
            sheet_id=sheet_id,
            action_type=action_type,
            row=row,
            row_index=row_index,
        )
        candidate = {
            "source_module": "stockops",
            "source_id": source_id,
            "source_type": "stockops_sheet_row",
            "external_id": source_id,
            "run_id": run.run_id,
            "run_type": self._finance_run_type(run.run_type),
            "sheet_id": sheet_id,
            "action_type": action_type,
            "nm_id": nm_id,
            "vendor_code": self._first_string(
                row.get("seller_article"), row.get("vendor_code"), row.get("article")
            ),
            "sku_id": self._int(row.get("sku_id") or row.get("barcode")),
            "region": self._first_string(
                row.get("region"), row.get("recipient_region"), row.get("donor_region")
            ),
            "warehouse": self._first_string(
                row.get("warehouse_name"),
                row.get("recipient_warehouse"),
                row.get("donor_warehouse"),
                row.get("source_name"),
            ),
            "quantity": quantity,
            "expected_effect_amount": self._candidate_amount(row),
            "reason": self._candidate_reason(action_type=action_type, row=row),
            "next_step": "Open Stock Planner, review the read-only recommendation, and record the result after manual warehouse work.",
            "payload": row,
        }
        return candidate

    def _action_from_candidate(
        self, *, account_id: int, candidate: dict[str, Any]
    ) -> PortalActionRead:
        action_type = str(candidate.get("action_type") or "regional_redistribution")
        priority = (
            "P1"
            if action_type in {"stock_shortage", "regional_redistribution"}
            else "P2"
        )
        severity = "high" if priority == "P1" else "medium"
        title_map = {
            "stock_excess": "Review regional stock excess",
            "stock_shortage": "Review regional stock shortage",
            "regional_redistribution": "Review stock redistribution candidate",
            "frozen_inventory_value": "Review frozen inventory value",
        }
        return PortalActionRead(
            id=f"stockops:{candidate.get('source_id')}",
            source="stockops_signals",
            source_module="stockops",
            source_id=str(candidate.get("source_id") or ""),
            external_id=str(
                candidate.get("external_id") or candidate.get("source_id") or ""
            ),
            account_id=account_id,
            nm_id=self._int(candidate.get("nm_id")),
            sku_id=self._int(candidate.get("sku_id")),
            action_type=action_type,
            title=title_map.get(action_type, "Review StockOps recommendation"),
            priority=priority,
            severity=severity,
            reason=str(candidate.get("reason") or ""),
            next_step=str(candidate.get("next_step") or ""),
            expected_effect_amount=self._optional_float(
                candidate.get("expected_effect_amount")
            ),
            confidence="medium",
            linked_entity={
                "nm_id": candidate.get("nm_id"),
                "sku_id": candidate.get("sku_id"),
                "vendor_code": candidate.get("vendor_code"),
                "region": candidate.get("region"),
                "warehouse": candidate.get("warehouse"),
            },
            payload={
                "run_id": candidate.get("run_id"),
                "run_type": candidate.get("run_type"),
                "sheet_id": candidate.get("sheet_id"),
                "quantity": candidate.get("quantity"),
                "write_status": "disabled",
                "marketplace_change": False,
            },
            raw=candidate,
        )

    def _candidate_summary(self, candidates: list[dict[str, Any]]) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        frozen_qty = 0.0
        for item in candidates:
            action_type = str(item.get("action_type") or "unknown")
            by_type[action_type] = by_type.get(action_type, 0) + 1
            if action_type == "stock_excess":
                frozen_qty += float(item.get("quantity") or 0)
        return {
            "candidate_count": len(candidates),
            "by_action_type": by_type,
            "frozen_inventory_qty_signal": frozen_qty or None,
            "write_status": "disabled",
            "flow_matrix": self.compatibility_matrix(),
        }

    def _candidate_quantity(
        self, *, action_type: str, row: dict[str, Any]
    ) -> float | None:
        keys_by_type = {
            "stock_excess": (
                "to_pick",
                "leftover_qty",
                "return_qty",
                "warehouse_stock",
                "available_qty",
            ),
            "stock_shortage": (
                "remaining_need",
                "open_need",
                "deficit_qty",
                "target_need",
            ),
            "regional_redistribution": (
                "planned_ship_qty",
                "total_qty",
                "shipped_qty",
                "planned_need_cover_qty",
            ),
        }
        for key in keys_by_type.get(action_type, ()):
            value = self._optional_float(row.get(key))
            if value is not None:
                return value
        return None

    def _candidate_amount(self, row: dict[str, Any]) -> float | None:
        return self._optional_float(
            row.get("stock_value")
            or row.get("frozen_inventory_value")
            or row.get("logistics_cost")
            or row.get("recipient_logistics_cost")
        )

    def _candidate_reason(self, *, action_type: str, row: dict[str, Any]) -> str:
        article = (
            self._first_string(
                row.get("seller_article"), row.get("vendor_code"), row.get("article")
            )
            or "product"
        )
        region = self._first_string(
            row.get("recipient_region"), row.get("donor_region"), row.get("region")
        )
        warehouse = self._first_string(
            row.get("warehouse_name"),
            row.get("recipient_warehouse"),
            row.get("donor_warehouse"),
        )
        place = ", ".join(part for part in (region, warehouse) if part)
        if action_type == "stock_excess":
            return f"StockOps found excess stock for {article}" + (
                f" at {place}." if place else "."
            )
        if action_type == "stock_shortage":
            return f"StockOps found uncovered regional demand for {article}" + (
                f" at {place}." if place else "."
            )
        if action_type == "regional_redistribution":
            return f"StockOps suggested a redistribution review for {article}" + (
                f" at {place}." if place else "."
            )
        return f"StockOps produced a stock signal for {article}."

    def _candidate_source_id(
        self,
        *,
        run: PortalStockOpsRunRead,
        sheet_id: str,
        action_type: str,
        row: dict[str, Any],
        row_index: int,
    ) -> str:
        parts = [
            str(run.run_id or "latest"),
            sheet_id,
            action_type,
            str(
                row.get("wb_article")
                or row.get("nm_id")
                or row.get("seller_article")
                or row_index
            ),
            str(
                row.get("recipient_region")
                or row.get("donor_region")
                or row.get("region")
                or row.get("warehouse_name")
                or ""
            ),
            str(row_index),
        ]
        return ":".join(
            part.strip().replace(" ", "_") for part in parts if part is not None
        )

    def _row_matches_account(
        self, payload: dict[str, Any], *, account_id: int | None
    ) -> bool:
        if account_id is None:
            return True
        payload_account_id = self._int(payload.get("account_id"))
        return payload_account_id is None or payload_account_id == account_id

    def _summary(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        summary = (
            payload.get("summary")
            or payload.get("overview")
            or payload.get("sync_meta")
        )
        return self._safe_payload(summary) if isinstance(summary, dict) else None

    def _status(self, value: Any) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"queued", "running", "completed", "failed"}:
            return normalized
        if normalized in {"ok", "success", "done", "finished"}:
            return "completed"
        if normalized in {"error", "failed_upload"}:
            return "failed"
        return "completed"

    def _external_run_type(self, value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return {
            "store_balance": "store_percent_balance",
            "store_percent_balance": "store_percent_balance",
            "ship_from_hand": "ship_from_hand",
            "return_excess": "return_excess",
        }.get(normalized)

    def _finance_run_type(self, value: str | None) -> str | None:
        normalized = str(value or "").strip().lower()
        return {
            "store_percent_balance": "store_balance",
            "store_balance": "store_balance",
            "ship_from_hand": "ship_from_hand",
            "return_excess": "return_excess",
        }.get(normalized, normalized or None)

    def _int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def _optional_float(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None and value != "" else None
        except (TypeError, ValueError):
            return None

    def _first_string(self, *values: Any) -> str | None:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return None

    def _safe_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        secret_keys = {
            "token",
            "api_key",
            "access_token",
            "refresh_token",
            "authorization",
            "wb_api_token",
        }
        safe: dict[str, Any] = {}
        for key, value in payload.items():
            if any(secret in key.lower() for secret in secret_keys):
                continue
            if isinstance(value, dict):
                safe[key] = self._safe_payload(value)
            elif isinstance(value, list):
                safe[key] = [
                    self._safe_payload(item) if isinstance(item, dict) else item
                    for item in value
                ]
            else:
                safe[key] = value
        return safe
