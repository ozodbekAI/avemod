from __future__ import annotations

from datetime import date
from typing import Any

import httpx
from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings, get_settings
from app.models.accounts import WBAccount
from app.models.finance import WBRealizationReportRow
from app.models.supplies import WBSupply, WBSupplyGood
from app.schemas.claims import (
    ClaimsCaseCreate,
    ClaimsDraftGenerateRequest,
    ClaimsEvidenceCreate,
    ClaimsProofCheckRequest,
    ClaimsSubmitRequest,
)
from app.schemas.data_quality import issue_bucket_meta, issue_display_message
from app.schemas.operator import (
    CaseType,
    DraftType,
    ExternalStatus,
    Priority,
    ResultEventOut,
)
from app.schemas.portal import PortalActionRead
from app.services.claims_case_templates import get_claim_case_template
from app.services.claims_factory import ClaimsFactoryService
from app.services.data_quality import DataQualityService
from app.services.guided_fixes import GuidedFixMapper


class ClaimsDefectAdapter:
    """Optional adapter for defect claims logic inspired by backenddefect.

    The adapter keeps finance as the public auth/account boundary. External
    support/WB writes are never attempted unless the caller explicitly confirms
    and an internal claims service is configured.
    """

    SAFE_REFERENCE_ENDPOINTS = (
        "GET /api/cases",
        "GET /api/cases/{case_id}",
        "POST /api/cases",
        "POST /api/cases/{case_id}/media",
        "POST /api/cases/{case_id}/rematch",
        "POST /api/cases/{case_id}/generate-draft",
        "POST /api/cases/{case_id}/proof-check",
        "POST /api/cases/{case_id}/repeat-claim/draft",
        "POST /api/cases/{case_id}/report-objection/draft",
        "POST /api/cases/{case_id}/pretrial/draft",
        "GET /api/cases/{case_id}/legal-package",
        "POST /api/wb/cases/{case_id}/compensation-check",
        "POST /api/wb/cases/{case_id}/finance-trace",
        "POST /api/wb/cases/finance-trace",
        "POST /api/video-links/{case_id}",
    )
    COMPATIBILITY_ENDPOINTS = ("GET /defect-candidates",)
    DANGEROUS_REFERENCE_ENDPOINTS = (
        "POST /api/cases/{case_id}/submit",
        "POST /api/cases/{case_id}/create-appeal",
        "POST /api/cases/{case_id}/repeat-claim/send",
        "POST /api/cases/{case_id}/report-objection/send",
        "POST /api/cases/{case_id}/pretrial/approve",
        "POST /api/cases/{case_id}/pretrial/send",
    )

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        factory: ClaimsFactoryService | None = None,
        data_quality: DataQualityService | None = None,
        mock_candidates: list[dict[str, Any]] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.factory = factory or ClaimsFactoryService()
        self.data_quality = data_quality or DataQualityService()
        self.mock_candidates = mock_candidates or []
        self.guided_fixes = GuidedFixMapper()
        self.report_anomaly_codes = {
            "finance_reconciliation_mismatch",
            "finance_without_sale",
            "sale_without_finance",
        }

    @property
    def is_configured(self) -> bool:
        return bool(self.settings.claims_enabled and self._base_url)

    async def health(self, account: WBAccount | None = None) -> tuple[str, str | None]:
        if self.mock_candidates:
            return "ok", "claims adapter is running in mock mode"
        if not self.settings.claims_enabled:
            return "disabled", "claims module is disabled"
        if not self._base_url:
            return "not_configured", "claims_base_url is not configured"
        try:
            await self._request("GET", "/health", auth=False)
        except Exception:
            return "unavailable", "claims service is not reachable"
        return "ok", None

    async def detect_defect_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
    ) -> dict[str, Any]:
        if self.mock_candidates:
            candidates = [
                self._candidate(item, account_id=account_id)
                for item in self.mock_candidates
            ]
            if nm_id is not None:
                candidates = [
                    item for item in candidates if self._int(item.get("nm_id")) == nm_id
                ]
            return {
                "status": "ok",
                "items": candidates,
                "trust_state": "provisional",
                "mock_mode": True,
            }
        if not self.is_configured:
            return {
                "status": "not_configured",
                "items": [],
                "message": "claims service is not configured",
                "unavailable_sources": ["claims"],
                "trust_state": "unavailable",
            }
        date_from, date_to = date_range or (None, None)
        params = {
            "account_id": account_id,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
            "nm_id": nm_id,
        }
        try:
            payload = await self._request(
                "GET",
                "/defect-candidates",
                params={k: v for k, v in params.items() if v is not None},
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 404:
                return {
                    "status": "unavailable",
                    "items": [],
                    "unavailable_sources": ["claims"],
                    "trust_state": "unavailable",
                }
            try:
                payload = await self._request("GET", "/cases")
            except Exception:
                return {
                    "status": "unavailable",
                    "items": [],
                    "unavailable_sources": ["claims"],
                    "trust_state": "unavailable",
                }
        except Exception:
            return {
                "status": "unavailable",
                "items": [],
                "unavailable_sources": ["claims"],
                "trust_state": "unavailable",
            }
        items = [
            self._candidate(item, account_id=account_id)
            for item in self._items(payload)
        ]
        if nm_id is not None:
            items = [item for item in items if self._int(item.get("nm_id")) == nm_id]
        status = (
            str(payload.get("status") or "ok") if isinstance(payload, dict) else "ok"
        )
        return {"status": status, "items": items, "trust_state": "provisional"}

    async def detect_supply_discrepancy_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
        session=None,
    ) -> dict[str, Any]:
        if session is None:
            return {
                "status": "not_configured",
                "case_type": CaseType.SUPPLY_DISCREPANCY.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Supply discrepancy detection requires finance supply data.",
                "unavailable_sources": ["supplies"],
                "trust_state": "unavailable",
            }

        date_from, date_to = date_range or (None, None)
        stmt = (
            select(WBSupply, WBSupplyGood)
            .join(WBSupplyGood, WBSupplyGood.supply_fk_id == WBSupply.id)
            .where(
                WBSupply.account_id == account_id, WBSupplyGood.account_id == account_id
            )
        )
        if nm_id is not None:
            stmt = stmt.where(WBSupplyGood.nm_id == nm_id)
        if date_from is not None:
            stmt = stmt.where(WBSupply.fact_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBSupply.fact_date <= date_to)

        try:
            result = await session.execute(
                stmt.order_by(WBSupply.fact_date.desc(), WBSupply.id.desc()).limit(500)
            )
            rows = list(result.all())
        except SQLAlchemyError:
            return {
                "status": "unavailable",
                "case_type": CaseType.SUPPLY_DISCREPANCY.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Supply tables are unavailable.",
                "unavailable_sources": ["supplies"],
                "trust_state": "unavailable",
            }
        except Exception:
            return {
                "status": "unavailable",
                "case_type": CaseType.SUPPLY_DISCREPANCY.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Supply discrepancy data could not be loaded.",
                "unavailable_sources": ["supplies"],
                "trust_state": "unavailable",
            }

        if not rows:
            return {
                "status": "empty",
                "case_type": CaseType.SUPPLY_DISCREPANCY.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "No supply goods were found for the selected window.",
                "unavailable_sources": [],
                "trust_state": "provisional",
            }

        any_acceptance_data = False
        items: list[dict[str, Any]] = []
        for supply, good in rows:
            expected_qty = self._int(getattr(good, "quantity", None))
            accepted_qty = self._int(getattr(good, "accepted_quantity", None))
            if accepted_qty is not None:
                any_acceptance_data = True
            if (
                expected_qty is None
                or accepted_qty is None
                or expected_qty <= accepted_qty
            ):
                continue
            items.append(
                self._supply_discrepancy_candidate(
                    account_id=account_id, supply=supply, good=good
                )
            )

        if not any_acceptance_data:
            return {
                "status": "not_enough_data",
                "case_type": CaseType.SUPPLY_DISCREPANCY.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Supply rows exist, but accepted quantities are not synced.",
                "unavailable_sources": ["supply_acceptance"],
                "trust_state": "unavailable",
                "warnings": ["supply_acceptance_not_synced"],
            }

        return {
            "status": "ok" if items else "empty",
            "case_type": CaseType.SUPPLY_DISCREPANCY.value,
            "account_id": account_id,
            "items": items,
            "item_count": len(items),
            "message": None if items else "No supply discrepancies were found.",
            "unavailable_sources": [],
            "trust_state": "provisional",
        }

    async def detect_missing_goods_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
        session=None,
    ) -> dict[str, Any]:
        if session is None:
            return {
                "status": "not_configured",
                "case_type": CaseType.MISSING_GOODS.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Missing goods detection requires finance supply data.",
                "unavailable_sources": ["supplies"],
                "trust_state": "unavailable",
                "required_fields": ["wb_supply_goods.accepted_quantity"],
            }
        date_from, date_to = date_range or (None, None)
        stmt = (
            select(WBSupply, WBSupplyGood)
            .join(WBSupplyGood, WBSupplyGood.supply_fk_id == WBSupply.id)
            .where(
                WBSupply.account_id == account_id, WBSupplyGood.account_id == account_id
            )
        )
        if nm_id is not None:
            stmt = stmt.where(WBSupplyGood.nm_id == nm_id)
        if date_from is not None:
            stmt = stmt.where(WBSupply.fact_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBSupply.fact_date <= date_to)
        try:
            result = await session.execute(
                stmt.order_by(WBSupply.fact_date.desc(), WBSupply.id.desc()).limit(500)
            )
            rows = list(result.all())
        except SQLAlchemyError:
            return {
                "status": "unavailable",
                "case_type": CaseType.MISSING_GOODS.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Supply tables are unavailable.",
                "unavailable_sources": ["supplies"],
                "trust_state": "unavailable",
            }
        if not rows:
            return {
                "status": "empty",
                "case_type": CaseType.MISSING_GOODS.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "No supply goods were found for the selected window.",
                "unavailable_sources": [],
                "trust_state": "provisional",
            }
        any_acceptance_data = False
        items: list[dict[str, Any]] = []
        for supply, good in rows:
            expected_qty = self._int(getattr(good, "quantity", None))
            accepted_qty = self._int(getattr(good, "accepted_quantity", None))
            if accepted_qty is not None:
                any_acceptance_data = True
            if (
                expected_qty is None
                or accepted_qty is None
                or expected_qty <= 0
                or accepted_qty != 0
            ):
                continue
            items.append(
                self._missing_goods_candidate(
                    account_id=account_id, supply=supply, good=good
                )
            )
        if not any_acceptance_data:
            return {
                "status": "not_enough_data",
                "case_type": CaseType.MISSING_GOODS.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Supply rows exist, but accepted quantities are not synced.",
                "unavailable_sources": ["supply_acceptance"],
                "trust_state": "unavailable",
                "warnings": ["supply_acceptance_not_synced"],
            }
        return {
            "status": "ok" if items else "empty",
            "case_type": CaseType.MISSING_GOODS.value,
            "account_id": account_id,
            "items": items,
            "item_count": len(items),
            "message": None if items else "No missing goods candidates were found.",
            "unavailable_sources": [],
            "trust_state": "provisional",
        }

    async def detect_report_anomaly_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
        session=None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if session is None:
            return {
                "status": "not_configured",
                "case_type": CaseType.REPORT_ANOMALY.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "report_anomaly detection requires a finance DB session with data-quality issues",
                "unavailable_sources": ["data_quality"],
                "trust_state": "unavailable",
                "required_fields": ["data_quality_issues"],
            }
        date_from, date_to = date_range or (None, None)
        try:
            page = await self.data_quality.list_issues(
                session,
                account_id=account_id,
                only_open=True,
                codes=sorted(self.report_anomaly_codes),
                nm_id=nm_id,
                detected_from=date_from,
                detected_to=date_to,
                sort_by="detected_at",
                sort_dir="desc",
                limit=max(1, min(int(limit or 50), 100)),
                offset=0,
            )
        except Exception:
            return {
                "status": "unavailable",
                "case_type": CaseType.REPORT_ANOMALY.value,
                "account_id": account_id,
                "items": [],
                "message": "data-quality report anomaly issues are unavailable",
                "unavailable_sources": ["data_quality"],
                "trust_state": "unavailable",
            }
        items = [
            self._report_anomaly_candidate(
                issue, account_id=account_id, date_range=date_range
            )
            for issue in self._items(page)
        ]
        return {
            "status": "ok" if items else "empty",
            "case_type": CaseType.REPORT_ANOMALY.value,
            "account_id": account_id,
            "items": items,
            "message": None
            if items
            else "No open finance report anomaly candidates were found.",
            "unavailable_sources": [],
            "trust_state": "provisional",
        }

    async def detect_compensation_underpayment_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
        session=None,
    ) -> dict[str, Any]:
        defect_candidates = await self.detect_defect_candidates(
            account_id, date_range, nm_id=nm_id
        )
        if defect_candidates.get("status") not in {"ok", "empty"}:
            return {
                "status": defect_candidates.get("status") or "not_configured",
                "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": defect_candidates.get("message")
                or "Defect compensation candidates are unavailable.",
                "unavailable_sources": list(
                    defect_candidates.get("unavailable_sources") or ["claims"]
                ),
                "trust_state": "unavailable",
                "required_fields": ["defect_or_return_candidate"],
            }
        candidates = list(defect_candidates.get("items") or [])
        if not candidates:
            return {
                "status": "empty",
                "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "No defect compensation candidates were found.",
                "unavailable_sources": [],
                "trust_state": "provisional",
            }
        if session is None:
            return {
                "status": "not_configured",
                "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Compensation underpayment detection requires finance report rows.",
                "unavailable_sources": ["finance_reports"],
                "trust_state": "unavailable",
                "required_fields": ["finance_report_rows"],
            }

        items: list[dict[str, Any]] = []
        required_fields: set[str] = set()
        try:
            for candidate in candidates:
                expected_amount = self._candidate_expected_compensation(candidate)
                if expected_amount is None:
                    required_fields.add("expected_compensation_amount")
                    continue
                rows = await self._compensation_finance_rows(
                    session,
                    account_id=account_id,
                    candidate=candidate,
                    date_range=date_range,
                )
                if rows is None:
                    required_fields.add("return_or_order_identity")
                    continue
                if not rows:
                    required_fields.add("actual_compensation_amount")
                    actual_amount = 0.0
                    evidence_refs = []
                else:
                    actual_amount = round(
                        sum(self._finance_row_compensation_amount(row) for row in rows),
                        2,
                    )
                    evidence_refs = [
                        {
                            "source_type": "finance_report_row",
                            "source_id": str(
                                getattr(row, "rrd_id", None) or getattr(row, "id", "")
                            ),
                            "table": "wb_realization_report_rows",
                            "report_id": getattr(row, "report_id", None),
                        }
                        for row in rows
                        if self._finance_row_compensation_amount(row) > 0
                    ]
                threshold = expected_amount * max(
                    min(
                        float(
                            getattr(self.settings, "compensation_full_match_ratio", 1.0)
                            or 1.0
                        ),
                        1.0,
                    ),
                    0.0,
                )
                if actual_amount < threshold:
                    items.append(
                        self._compensation_underpayment_candidate(
                            account_id=account_id,
                            candidate=candidate,
                            expected_amount=expected_amount,
                            actual_amount=actual_amount,
                            evidence_refs=evidence_refs,
                        )
                    )
        except SQLAlchemyError:
            return {
                "status": "unavailable",
                "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Finance report rows are unavailable.",
                "unavailable_sources": ["finance_reports"],
                "trust_state": "unavailable",
            }

        if required_fields and not items:
            return {
                "status": "not_enough_data",
                "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": "Compensation underpayment detection needs expected and actual compensation data.",
                "unavailable_sources": ["finance_reports"]
                if "actual_compensation_amount" in required_fields
                else [],
                "trust_state": "unavailable",
                "required_fields": sorted(required_fields),
                "warnings": ["compensation_underpayment_not_enough_data"],
            }

        return {
            "status": "ok" if items else "empty",
            "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
            "account_id": account_id,
            "items": items,
            "item_count": len(items),
            "message": None if items else "No compensation underpayments were found.",
            "unavailable_sources": [],
            "trust_state": "provisional",
        }

    async def detect_repeat_claim_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
    ) -> dict[str, Any]:
        defects = await self.detect_defect_candidates(
            account_id, date_range, nm_id=nm_id
        )
        if defects.get("status") not in {"ok", "empty"}:
            return {
                "status": defects.get("status") or "not_configured",
                "case_type": CaseType.REPEAT_CLAIM.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": defects.get("message")
                or "Defect candidates are unavailable.",
                "unavailable_sources": list(
                    defects.get("unavailable_sources") or ["claims"]
                ),
                "trust_state": "unavailable",
            }
        items = [
            self._repeat_claim_candidate(item)
            for item in defects.get("items") or []
            if self._is_repeat_claim_candidate(item)
        ]
        return {
            "status": "ok" if items else "empty",
            "case_type": CaseType.REPEAT_CLAIM.value,
            "account_id": account_id,
            "items": items,
            "item_count": len(items),
            "message": None if items else "No repeat claim candidates were found.",
            "unavailable_sources": [],
            "trust_state": "provisional",
        }

    async def detect_pretrial_candidates(
        self,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
        *,
        nm_id: int | None = None,
    ) -> dict[str, Any]:
        defects = await self.detect_defect_candidates(
            account_id, date_range, nm_id=nm_id
        )
        if defects.get("status") not in {"ok", "empty"}:
            return {
                "status": defects.get("status") or "not_configured",
                "case_type": CaseType.PRETRIAL.value,
                "account_id": account_id,
                "items": [],
                "item_count": 0,
                "message": defects.get("message")
                or "Defect candidates are unavailable.",
                "unavailable_sources": list(
                    defects.get("unavailable_sources") or ["claims"]
                ),
                "trust_state": "unavailable",
            }
        items = [
            self._pretrial_candidate(item)
            for item in defects.get("items") or []
            if self._is_pretrial_candidate(item)
        ]
        return {
            "status": "ok" if items else "empty",
            "case_type": CaseType.PRETRIAL.value,
            "account_id": account_id,
            "items": items,
            "item_count": len(items),
            "message": None if items else "No pretrial candidates were found.",
            "unavailable_sources": [],
            "trust_state": "provisional",
        }

    async def profit_doctor_signals(
        self,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        nm_id: int | None = None,
        session=None,
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []
        candidates = await self.detect_defect_candidates(
            account_id, (date_from, date_to), nm_id=nm_id
        )
        if candidates.get("status") in {"ok", "empty"}:
            signals.extend(self._signal(item) for item in candidates.get("items") or [])
        report_anomalies = await self.detect_report_anomaly_candidates(
            account_id,
            (date_from, date_to),
            nm_id=nm_id,
            session=session,
        )
        if report_anomalies.get("status") in {"ok", "empty"}:
            signals.extend(
                self._signal(item) for item in report_anomalies.get("items") or []
            )
        return signals

    async def claims_actions(
        self, account: WBAccount, *, limit: int = 50, session=None
    ) -> tuple[list[PortalActionRead], str | None]:
        candidates = await self.detect_defect_candidates(account.id, None)
        status = candidates.get("status")
        if status in {"disabled", "not_configured"}:
            defect_actions: list[PortalActionRead] = []
        elif status == "unavailable":
            defect_actions = []
        else:
            defect_actions = [
                self._action(item) for item in candidates.get("items") or []
            ]
        report_anomalies = await self.detect_report_anomaly_candidates(
            account.id, None, session=session, limit=limit
        )
        anomaly_status = report_anomalies.get("status")
        unavailable = None
        if status == "unavailable":
            unavailable = "claims"
        if anomaly_status == "unavailable":
            unavailable = "data_quality"
        actions = defect_actions + [
            self._action(item) for item in report_anomalies.get("items") or []
        ]
        return actions[: max(int(limit or 50), 1)], unavailable

    async def product_360(
        self,
        *,
        account_id: int,
        nm_id: int,
        vendor_code: str | None = None,
        barcode: str | None = None,
    ) -> dict[str, Any]:
        candidates = await self.detect_defect_candidates(account_id, None, nm_id=nm_id)
        status = str(candidates.get("status") or "not_configured")
        items = list(candidates.get("items") or [])
        compensation = sum(
            float(item.get("estimated_amount") or item.get("impact") or 0)
            for item in items
        )
        return {
            "status": status,
            "open_cases_count": len(items) if status == "ok" else None,
            "potential_compensation_amount": compensation if items else None,
            "items": items,
            "actions": [self._action(item).model_dump(mode="json") for item in items],
            "message": candidates.get("message"),
            "unavailable_sources": list(candidates.get("unavailable_sources") or []),
            "trust_state": candidates.get("trust_state")
            or ("provisional" if status == "ok" else "unavailable"),
        }

    async def create_defect_case_from_signal(
        self,
        session,
        *,
        account_id: int,
        signal: dict[str, Any],
        created_by: int | None = None,
    ):
        candidate = self._candidate(signal, account_id=account_id)
        template = get_claim_case_template(CaseType.DEFECT)
        return await self.factory.create_case(
            session,
            payload=ClaimsCaseCreate(
                account_id=account_id,
                case_type=CaseType.DEFECT,
                nm_id=self._int(candidate.get("nm_id")),
                vendor_code=self._str(candidate.get("vendor_code")),
                order_id=self._str(candidate.get("order_id")),
                srid=self._str(candidate.get("srid")),
                title=str(candidate.get("title") or "Defect claim candidate"),
                summary=str(candidate.get("reason") or candidate.get("summary") or ""),
                priority=self._priority(
                    candidate.get("priority") or template.default_priority
                ),
                estimated_amount=self._float(
                    candidate.get("estimated_amount") or candidate.get("impact")
                ),
                source_id=self._str(candidate.get("source_id")),
                external_id=self._str(candidate.get("external_id")),
                payload={
                    "signal": candidate,
                    "adapter": "claims_defect",
                    "source_pattern": "backenddefect_reference",
                    "case_template": {
                        "required_evidence_types": list(
                            template.required_evidence_types
                        ),
                        "draft_type": template.draft_type.value,
                        "recommended_guided_fix": template.recommended_guided_fix,
                        "requires_external_ticket": template.requires_external_ticket,
                    },
                },
            ),
            created_by=created_by,
        )

    async def collect_evidence_snapshot(
        self, session, *, account_id: int, case_id: int
    ) -> dict[str, Any]:
        case = await self.factory.get_case(
            session, account_id=account_id, case_id=case_id
        )
        return {
            "status": "ok",
            "case_id": case.id,
            "evidence_count": len(case.evidence),
            "draft_count": len(case.drafts),
            "finance_trace": case.finance_trace,
            "evidence": [item.model_dump(mode="json") for item in case.evidence],
            "warnings": case.warnings,
        }

    async def create_evidence_from_signal(
        self,
        session,
        *,
        account_id: int,
        case_id: int,
        signal: dict[str, Any],
        created_by: int | None = None,
    ):
        candidate = self._candidate(signal, account_id=account_id)
        evidence_snapshot = self._safe_payload(candidate.get("evidence_snapshot") or {})
        finance_trace = self._safe_payload(candidate.get("finance_trace") or {})
        payload = {
            "signal_source_id": candidate.get("source_id"),
            "signal": candidate,
            "evidence_snapshot": evidence_snapshot,
            "finance_trace": finance_trace,
            "external_operation": False,
            "source_pattern": "backenddefect_reference",
        }
        return await self.factory.attach_evidence(
            session,
            account_id=account_id,
            case_id=case_id,
            payload=ClaimsEvidenceCreate(
                evidence_type="finance_trace"
                if finance_trace
                else "defect_signal_snapshot",
                title=str(candidate.get("title") or "Defect signal evidence"),
                description=str(
                    candidate.get("reason")
                    or "Evidence snapshot created from defect signal."
                ),
                source_id=f"claims:evidence:{candidate.get('source_id') or case_id}",
                external_id=self._str(candidate.get("external_id")),
                payload=payload,
            ),
            created_by=created_by,
        )

    async def generate_defect_claim_draft(
        self, session, *, account_id: int, case_id: int, created_by: int | None = None
    ):
        return await self.factory.generate_draft(
            session,
            account_id=account_id,
            case_id=case_id,
            payload=ClaimsDraftGenerateRequest(
                draft_type=DraftType.SUPPORT_APPEAL, language="ru"
            ),
            created_by=created_by,
        )

    async def proof_check(self, session, *, account_id: int, case_id: int):
        return await self.factory.proof_check(
            session,
            account_id=account_id,
            case_id=case_id,
            payload=ClaimsProofCheckRequest(),
        )

    async def submit_to_support(
        self,
        session,
        *,
        account_id: int,
        case_id: int,
        confirm: bool = True,
        draft_id: str | None = None,
        created_by: int | None = None,
    ) -> ResultEventOut:
        if not confirm:
            return await self.factory.submit_case_manual_confirm(
                session,
                account_id=account_id,
                case_id=case_id,
                payload=ClaimsSubmitRequest(confirm=False, draft_id=draft_id),
                created_by=created_by,
            )
        if not self.settings.enable_claims_submit:
            return ResultEventOut(
                module="claims",
                event_type="submit_disabled_by_feature_flag",
                account_id=account_id,
                case_id=str(case_id),
                title="Claims submit disabled",
                message="Claims support submission is disabled by ENABLE_CLAIMS_SUBMIT=false.",
                success=False,
                data={
                    "external_submit_attempted": False,
                    "external_write_enabled": False,
                    "local_only": True,
                },
                warnings=["claims_submit_disabled"],
            )
        if not self.is_configured:
            return ResultEventOut(
                module="claims",
                event_type="submit_not_configured",
                account_id=account_id,
                case_id=str(case_id),
                title="Claims service is not configured",
                message="External support submission is unavailable; manual tracking can still be recorded in finance.",
                success=False,
                data={
                    "external_submit_attempted": False,
                    "external_write_enabled": False,
                    "local_only": True,
                },
                warnings=["claims_not_configured"],
            )
        return await self.factory.submit_case_manual_confirm(
            session,
            account_id=account_id,
            case_id=case_id,
            payload=ClaimsSubmitRequest(confirm=True, draft_id=draft_id),
            created_by=created_by,
        )

    async def check_ticket_status(
        self, session, *, account_id: int, case_id: int
    ) -> dict[str, Any]:
        if not self.is_configured and not self.mock_candidates:
            return {
                "status": "not_configured",
                "case_id": str(case_id),
                "unavailable_sources": ["claims"],
            }
        events = await self.factory.result_events(
            session, account_id=account_id, case_id=case_id
        )
        submitted = [
            event
            for event in events
            if event.external_status == ExternalStatus.SUBMITTED
        ]
        return {
            "status": "ok",
            "case_id": str(case_id),
            "external_status": "submitted" if submitted else "not_created",
            "events": [event.model_dump(mode="json") for event in events],
        }

    def _signal(self, item: dict[str, Any]) -> dict[str, Any]:
        action_type = str(item.get("action_type") or "defect_claim_candidate")
        title = str(item.get("title") or "Defect claim candidate")
        reason = str(
            item.get("reason")
            or item.get("summary")
            or "Potential defect compensation should be reviewed."
        )
        return {
            **item,
            "case_type": item.get("case_type") or "defect",
            "diagnosis_type": item.get("diagnosis_type") or "claim_opportunity",
            "action_type": action_type,
            "priority": item.get("priority") or "P1",
            "title": title,
            "reason": reason,
            "next_step": item.get("next_step")
            or "Open Claims Factory, review evidence, generate draft, then submit only after confirm.",
            "impact": self._float(item.get("impact") or item.get("estimated_amount")),
        }

    def _report_anomaly_candidate(
        self,
        issue: Any,
        *,
        account_id: int,
        date_range: tuple[date | None, date | None] | None = None,
    ) -> dict[str, Any]:
        raw = self._safe_payload(self._dump(issue))
        payload = dict(raw.get("payload") or {})
        code = str(raw.get("code") or "finance_reconciliation_mismatch")
        issue_id = raw.get("id")
        nm_id = self._int(raw.get("nm_id") or payload.get("nmId"))
        detected_at = raw.get("detected_at") or payload.get("detectedAt")
        source_id = (
            f"report_anomaly:{issue_id}"
            if issue_id is not None
            else f"report_anomaly:{code}:{nm_id or raw.get('entity_key') or detected_at or 'unknown'}"
        )
        meta = issue_bucket_meta(code)
        amount = self._float(
            payload.get("affectedRevenue")
            or payload.get("affected_amount")
            or payload.get("revenueDelta")
            or payload.get("forPayDelta")
            or payload.get("differenceAmount")
            or payload.get("amount")
            or raw.get("affected_amount")
        )
        date_from, date_to = date_range or (
            payload.get("dateFrom"),
            payload.get("dateTo"),
        )
        message = str(raw.get("message") or "")
        title = "Report anomaly candidate requires review"
        reason = str(
            meta.get("business_impact")
            or message
            or "Finance/data-quality found a report anomaly candidate. It is not proven and requires proof-check."
        )
        return {
            "case_type": CaseType.REPORT_ANOMALY.value,
            "diagnosis_type": "report_anomaly",
            "action_type": "report_anomaly_candidate",
            "title": title,
            "reason": f"{reason} Candidate requires review and proof-check required.",
            "priority": self._priority_from_issue(raw),
            "estimated_amount": amount,
            "impact": amount,
            "account_id": account_id,
            "nm_id": nm_id,
            "sku_id": self._int(raw.get("sku_id") or payload.get("skuId")),
            "vendor_code": self._str(
                raw.get("vendor_code") or payload.get("vendorCode")
            ),
            "source_id": source_id,
            "period": {
                "date_from": date_from.isoformat()
                if hasattr(date_from, "isoformat")
                else date_from,
                "date_to": date_to.isoformat()
                if hasattr(date_to, "isoformat")
                else date_to,
            },
            "finance_trace": {
                "source": "data_quality.list_issues",
                "issue_id": issue_id,
                "code": code,
                "domain": raw.get("domain"),
                "severity": raw.get("severity"),
                "source_table": raw.get("source_table"),
                "entity_key": raw.get("entity_key"),
                "detected_at": detected_at,
                "message": issue_display_message(code, message),
                "payload": payload,
            },
            "next_step": "Open Claims Factory, review finance trace, attach evidence, generate draft, then submit only after manual confirm.",
        }

    def _supply_discrepancy_candidate(
        self, *, account_id: int, supply: Any, good: Any
    ) -> dict[str, Any]:
        supply_id = getattr(supply, "supply_id", None)
        nm_id = self._int(getattr(good, "nm_id", None))
        vendor_code = self._str(getattr(good, "vendor_code", None))
        barcode = self._str(getattr(good, "barcode", None))
        expected_qty = self._int(getattr(good, "quantity", None)) or 0
        accepted_qty = self._int(getattr(good, "accepted_quantity", None)) or 0
        diff_qty = max(expected_qty - accepted_qty, 0)
        warehouse = self._str(
            getattr(supply, "actual_warehouse_name", None)
            or getattr(supply, "warehouse_name", None)
        )
        detected_date = (
            getattr(supply, "fact_date", None)
            or getattr(supply, "supply_date", None)
            or getattr(supply, "updated_date", None)
        )
        unit_amount = self._payload_amount(
            getattr(good, "payload", None)
        ) or self._payload_amount(getattr(supply, "payload", None))
        estimated_amount = (
            round(unit_amount * diff_qty, 2) if unit_amount is not None else None
        )
        source_id = "supply_discrepancy:{supply}:{item}".format(
            supply=supply_id or getattr(supply, "id", "unknown"),
            item=nm_id or barcode or vendor_code or getattr(good, "id", "unknown"),
        )
        evidence_refs = [
            {
                "source_type": "supply",
                "source_id": str(supply_id or getattr(supply, "id", "")),
                "table": "wb_supplies",
            },
            {
                "source_type": "supply_good",
                "source_id": str(getattr(good, "id", "")),
                "table": "wb_supply_goods",
            },
        ]
        return {
            "account_id": account_id,
            "case_type": CaseType.SUPPLY_DISCREPANCY.value,
            "diagnosis_type": "claim_opportunity",
            "action_type": "draft_claim",
            "source_module": "claims",
            "source_type": "supply_discrepancy_signal",
            "source_id": source_id,
            "external_id": str(supply_id) if supply_id is not None else None,
            "supply_id": supply_id,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
            "barcode": barcode,
            "expected_qty": expected_qty,
            "accepted_qty": accepted_qty,
            "diff_qty": diff_qty,
            "estimated_amount": estimated_amount,
            "impact": estimated_amount,
            "warehouse": warehouse,
            "date": detected_date.isoformat()
            if hasattr(detected_date, "isoformat")
            else detected_date,
            "evidence_refs": evidence_refs,
            "priority": "P1",
            "title": "Supply discrepancy candidate",
            "reason": (
                f"Accepted quantity is below expected quantity: expected {expected_qty}, "
                f"accepted {accepted_qty}, diff {diff_qty}. Candidate requires review and proof-check."
            ),
            "next_step": "Open Claims Factory, review supply evidence, generate draft, then submit only after confirm.",
            "trust_state": "provisional",
            "evidence_snapshot": {
                "supply_id": supply_id,
                "warehouse": warehouse,
                "expected_qty": expected_qty,
                "accepted_qty": accepted_qty,
                "diff_qty": diff_qty,
                "evidence_refs": evidence_refs,
            },
            "warnings": [],
        }

    def _missing_goods_candidate(
        self, *, account_id: int, supply: Any, good: Any
    ) -> dict[str, Any]:
        candidate = self._supply_discrepancy_candidate(
            account_id=account_id, supply=supply, good=good
        )
        candidate.update(
            {
                "case_type": CaseType.MISSING_GOODS.value,
                "source_type": "missing_goods_signal",
                "source_id": str(candidate.get("source_id") or "").replace(
                    "supply_discrepancy:", "missing_goods:", 1
                ),
                "title": "Missing goods candidate",
                "reason": (
                    f"Accepted quantity is zero while expected quantity is {candidate.get('expected_qty')}. "
                    "Candidate requires review and proof-check."
                ),
                "next_step": "Open Claims Factory, review missing goods evidence, generate draft, then submit only after confirm.",
            }
        )
        return candidate

    def _is_repeat_claim_candidate(self, item: dict[str, Any]) -> bool:
        payload = dict(item or {})
        haystack = " ".join(
            str(payload.get(key) or "").lower()
            for key in (
                "action_type",
                "case_type",
                "external_status",
                "status",
                "reason",
                "title",
            )
        )
        return bool(
            payload.get("needs_repeat")
            or payload.get("repeat_claim_needed")
            or "repeat" in haystack
            or "needs_repeat" in haystack
        )

    def _repeat_claim_candidate(self, item: dict[str, Any]) -> dict[str, Any]:
        raw = self._safe_payload(dict(item or {}))
        source_id = str(raw.get("source_id") or raw.get("id") or "unknown")
        return {
            **raw,
            "case_type": CaseType.REPEAT_CLAIM.value,
            "diagnosis_type": "claim_opportunity",
            "action_type": "repeat_claim_needed",
            "source_id": f"repeat_claim:{source_id}"
            if not source_id.startswith("repeat_claim:")
            else source_id,
            "title": raw.get("title") or "Repeat claim candidate",
            "reason": raw.get("reason")
            or "Previous claim requires repeat action after marketplace response.",
            "priority": str(raw.get("priority") or "P1").upper(),
            "next_step": "Open Claims Factory, review previous outcome, update evidence, then submit only after confirm.",
            "trust_state": "provisional",
        }

    def _is_pretrial_candidate(self, item: dict[str, Any]) -> bool:
        payload = dict(item or {})
        haystack = " ".join(
            str(payload.get(key) or "").lower()
            for key in (
                "action_type",
                "case_type",
                "external_status",
                "status",
                "reason",
                "title",
            )
        )
        return bool(
            payload.get("pretrial_required")
            or payload.get("legal_escalation")
            or "pretrial" in haystack
            or "pre-trial" in haystack
        )

    def _pretrial_candidate(self, item: dict[str, Any]) -> dict[str, Any]:
        raw = self._safe_payload(dict(item or {}))
        source_id = str(raw.get("source_id") or raw.get("id") or "unknown")
        return {
            **raw,
            "case_type": CaseType.PRETRIAL.value,
            "diagnosis_type": "claim_opportunity",
            "action_type": "pretrial_prepare",
            "source_id": f"pretrial:{source_id}"
            if not source_id.startswith("pretrial:")
            else source_id,
            "title": raw.get("title") or "Pretrial candidate",
            "reason": raw.get("reason")
            or "Claim may require pretrial preparation after unresolved marketplace response.",
            "priority": str(raw.get("priority") or "P0").upper(),
            "next_step": "Open Claims Factory, verify legal evidence, generate draft, then submit only after confirm.",
            "trust_state": "provisional",
        }

    async def _compensation_finance_rows(
        self,
        session,
        *,
        account_id: int,
        candidate: dict[str, Any],
        date_range: tuple[date | None, date | None] | None = None,
    ) -> list[Any] | None:
        conditions = []
        srid = self._str(candidate.get("srid"))
        order_id = self._int(candidate.get("order_id"))
        barcode = self._str(
            candidate.get("barcode")
            or (candidate.get("evidence_snapshot") or {}).get("barcode")
        )
        nm_id = self._int(candidate.get("nm_id"))
        if srid:
            conditions.append(WBRealizationReportRow.srid == srid)
        if order_id is not None:
            conditions.append(WBRealizationReportRow.order_id == order_id)
        if barcode:
            conditions.append(WBRealizationReportRow.barcode == barcode)
        if nm_id is not None:
            conditions.append(WBRealizationReportRow.nm_id == nm_id)
        if not conditions:
            return None
        date_from, date_to = date_range or (None, None)
        stmt = select(WBRealizationReportRow).where(
            WBRealizationReportRow.account_id == account_id, or_(*conditions)
        )
        if date_from is not None:
            stmt = stmt.where(WBRealizationReportRow.rr_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(WBRealizationReportRow.rr_date <= date_to)
        return list((await session.execute(stmt.limit(1000))).scalars())

    def _candidate_expected_compensation(
        self, candidate: dict[str, Any]
    ) -> float | None:
        basis = (
            candidate.get("claim_amount_basis")
            if isinstance(candidate.get("claim_amount_basis"), dict)
            else {}
        )
        compensation_check = (
            candidate.get("compensation_check")
            if isinstance(candidate.get("compensation_check"), dict)
            else {}
        )
        for value in (
            candidate.get("expected_compensation_amount"),
            candidate.get("estimated_amount"),
            candidate.get("expected_amount"),
            candidate.get("impact"),
            basis.get("amount"),
            basis.get("value"),
            compensation_check.get("expected_amount"),
            compensation_check.get("expectedAmount"),
        ):
            amount = self._float(value)
            if amount is not None and amount > 0:
                return amount
        return None

    def _finance_row_compensation_amount(self, row: Any) -> float:
        if not self._finance_row_looks_like_compensation(row):
            return 0.0
        candidates = [
            self._float(getattr(row, "additional_payment", None)),
            self._float(getattr(row, "for_pay", None)),
        ]
        positive = [value for value in candidates if value is not None and value > 0]
        return max(positive) if positive else 0.0

    def _finance_row_looks_like_compensation(self, row: Any) -> bool:
        text = " ".join(
            str(value or "").lower()
            for value in (
                getattr(row, "seller_oper_name", None),
                getattr(row, "bonus_type_name", None),
                getattr(row, "doc_type_name", None),
                getattr(row, "operation_type", None),
                getattr(row, "payload", {})
                if isinstance(getattr(row, "payload", {}), str)
                else "",
            )
        )
        if any(
            token in text
            for token in (
                "компен",
                "возмещ",
                "брак",
                "подмен",
                "доначисл",
                "корректировк брака",
            )
        ):
            return True
        return bool(
            self._float(getattr(row, "additional_payment", None))
            and self._float(getattr(row, "additional_payment", None)) > 0
        )

    def _compensation_underpayment_candidate(
        self,
        *,
        account_id: int,
        candidate: dict[str, Any],
        expected_amount: float,
        actual_amount: float,
        evidence_refs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        underpaid_amount = round(max(expected_amount - actual_amount, 0.0), 2)
        defect_id = self._str(
            candidate.get("defect_id")
            or candidate.get("id")
            or candidate.get("external_id")
            or candidate.get("source_id")
        )
        return_id = self._str(
            candidate.get("return_id")
            or candidate.get("matched_return_record_id")
            or candidate.get("srid")
            or candidate.get("order_id")
        )
        source_id = f"compensation_underpayment:{candidate.get('source_id') or defect_id or return_id or candidate.get('nm_id') or 'candidate'}"
        return {
            "account_id": account_id,
            "case_type": CaseType.COMPENSATION_UNDERPAYMENT.value,
            "diagnosis_type": "claim_opportunity",
            "action_type": "draft_claim",
            "source_module": "claims",
            "source_type": "compensation_underpayment_signal",
            "source_id": source_id,
            "external_id": defect_id,
            "nm_id": self._int(candidate.get("nm_id")),
            "vendor_code": self._str(candidate.get("vendor_code")),
            "defect_id": defect_id,
            "return_id": return_id,
            "expected_compensation_amount": round(expected_amount, 2),
            "actual_compensation_amount": round(actual_amount, 2),
            "underpaid_amount": underpaid_amount,
            "estimated_amount": underpaid_amount,
            "impact": underpaid_amount,
            "evidence_refs": [
                {
                    "source_type": "defect_candidate",
                    "source_id": str(candidate.get("source_id") or defect_id or ""),
                    "table": None,
                },
                *evidence_refs,
            ],
            "priority": "P1",
            "title": "Compensation underpayment candidate",
            "reason": (
                f"Expected compensation is {expected_amount:.2f}, actual matched compensation is "
                f"{actual_amount:.2f}. Candidate requires review and proof-check."
            ),
            "next_step": "Open Claims Factory, review finance rows, generate draft, then submit only after confirm.",
            "trust_state": "provisional",
            "finance_trace": {
                "expected_compensation_amount": round(expected_amount, 2),
                "actual_compensation_amount": round(actual_amount, 2),
                "underpaid_amount": underpaid_amount,
                "evidence_refs": evidence_refs,
            },
            "evidence_snapshot": {
                "defect_candidate": candidate,
                "evidence_refs": evidence_refs,
            },
            "warnings": [],
        }

    def _payload_amount(self, payload: Any) -> float | None:
        if not isinstance(payload, dict):
            return None
        for key in (
            "unit_price",
            "price",
            "retail_price",
            "retailPrice",
            "retail_amount",
            "retailAmount",
            "priceWithDisc",
        ):
            value = self._float(payload.get(key))
            if value is not None and value > 0:
                return value
        return None

    def _action(self, item: dict[str, Any]) -> PortalActionRead:
        signal = self._signal(item)
        action_type = str(signal.get("action_type") or "defect_claim_candidate")
        priority = str(signal.get("priority") or "P1").upper()
        impact = self._float(signal.get("impact") or signal.get("estimated_amount"))
        source_id = str(
            signal.get("source_id")
            or f"claims:{action_type}:{signal.get('nm_id') or signal.get('external_id') or 'candidate'}"
        )
        guided_fix = self.guided_fixes.map(
            source_module="claims",
            action_type=action_type,
            nm_id=self._int(signal.get("nm_id")),
            target_id=source_id,
        )
        guided_fix.update(
            {
                "endpoint": "/api/v1/portal/cases/from-signal",
                "method_http": "POST",
                "payload": {
                    "account_id": self._int(signal.get("account_id")),
                    "source_module": "claims",
                    "source_id": source_id,
                    "case_type": signal.get("case_type") or "defect",
                    "nm_id": self._int(signal.get("nm_id")),
                    "vendor_code": self._str(signal.get("vendor_code")),
                    "title": str(signal.get("title") or "Claims candidate"),
                    "summary": str(signal.get("reason") or ""),
                    "estimated_amount": impact,
                    "payload": signal,
                },
            }
        )
        return PortalActionRead(
            id=f"claims:{source_id}",
            source="claims_adapter",
            source_module="claims",
            source_id=source_id,
            account_id=self._int(signal.get("account_id")),
            nm_id=self._int(signal.get("nm_id")),
            action_type=action_type,
            title=str(signal.get("title") or "Claims candidate"),
            priority=priority if priority in {"P0", "P1", "P2", "P3", "P4"} else "P2",
            severity=self._severity(priority),
            status="new",
            reason=str(signal.get("reason") or ""),
            next_step=str(signal.get("next_step") or "Open Claims Factory"),
            expected_effect_amount=impact,
            priority_score=self._priority_score(priority, impact),
            confidence=str(signal.get("confidence") or "medium")
            if str(signal.get("confidence") or "medium") in {"high", "medium", "low"}
            else "medium",
            linked_entity={"case_type": signal.get("case_type") or "defect"},
            payload=signal,
            raw=signal,
            can_update=False,
            can_update_status=False,
            can_update_reason="create_case_first",
            guided_fix=guided_fix,
        )

    def _candidate(self, item: dict[str, Any], *, account_id: int) -> dict[str, Any]:
        raw = self._safe_payload(dict(item or {}))
        action_type = str(
            raw.get("action_type") or raw.get("type") or "defect_claim_candidate"
        )
        if action_type not in {
            "defect_claim_candidate",
            "compensation_underpayment_candidate",
            "evidence_missing",
            "report_anomaly_candidate",
            "repeat_claim_needed",
        }:
            action_type = "defect_claim_candidate"
        matched_return = self._first_dict(
            raw.get("matched_return_record"),
            raw.get("matchedReturnRecord"),
            raw.get("return_record"),
            raw.get("wb_return"),
            raw.get("wbReturn"),
        )
        matched_identifiers = self._first_dict(
            raw.get("matched_return_identifiers"),
            raw.get("matchedReturnIdentifiers"),
            raw.get("identifiers"),
        )
        first_match = self._first_dict(
            *(raw.get("match_candidates") or raw.get("matchCandidates") or [])
        )
        claim_amount_basis = self._first_dict(
            raw.get("claim_amount_basis"), raw.get("claimAmountBasis")
        )
        compensation_check = self._first_dict(
            raw.get("compensation_check"), raw.get("compensationCheck")
        )
        finance_trace = self._finance_trace(
            raw, matched_return=matched_return, compensation_check=compensation_check
        )
        evidence_snapshot = self._evidence_snapshot(raw, matched_return=matched_return)
        nm_id = self._int(
            raw.get("nm_id")
            or raw.get("nmId")
            or matched_return.get("nm_id")
            or matched_return.get("nmId")
            or matched_identifiers.get("nm_id")
            or matched_identifiers.get("nmId")
            or first_match.get("nm_id")
            or first_match.get("nmId")
        )
        vendor_code = self._str(
            raw.get("vendor_code")
            or raw.get("vendorCode")
            or matched_return.get("vendor_code")
            or matched_return.get("vendorCode")
        )
        order_id = self._str(
            raw.get("order_id")
            or raw.get("orderId")
            or matched_return.get("order_id")
            or matched_return.get("orderId")
            or matched_identifiers.get("order_id")
            or matched_identifiers.get("orderId")
            or first_match.get("order_id")
            or first_match.get("orderId")
        )
        srid = self._str(
            raw.get("srid")
            or matched_return.get("srid")
            or matched_identifiers.get("srid")
            or first_match.get("srid")
        )
        estimated_amount = self._float(
            raw.get("estimated_amount")
            or raw.get("estimatedAmount")
            or raw.get("expected_compensation_amount")
            or raw.get("expectedCompensationAmount")
            or raw.get("expected_amount")
            or raw.get("expectedAmount")
            or raw.get("amount")
            or raw.get("impact")
            or claim_amount_basis.get("amount")
            or claim_amount_basis.get("expected_amount")
            or claim_amount_basis.get("expectedAmount")
            or compensation_check.get("expected_amount")
            or compensation_check.get("expectedAmount")
        )
        source_id = self._source_id(
            raw,
            action_type=action_type,
            nm_id=nm_id,
            order_id=order_id,
            srid=srid,
            matched_return=matched_return,
        )
        reason = (
            raw.get("reason")
            or raw.get("summary")
            or raw.get("employee_note")
            or raw.get("operator_note")
            or raw.get("match_reason")
            or first_match.get("match_reason")
            or raw.get("status")
            or "Backend defect signal candidate requires review and proof-check."
        )
        return {
            **raw,
            "account_id": account_id,
            "case_type": raw.get("case_type") or "defect",
            "action_type": action_type,
            "title": raw.get("title") or self._title(action_type),
            "reason": reason,
            "priority": str(raw.get("priority") or "P1").upper(),
            "source_id": source_id,
            "estimated_amount": estimated_amount,
            "impact": self._float(raw.get("impact")) or estimated_amount,
            "nm_id": nm_id,
            "vendor_code": vendor_code,
            "order_id": order_id,
            "srid": srid,
            "finance_trace": finance_trace,
            "evidence_snapshot": evidence_snapshot,
        }

    def _items(self, payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            items = (
                payload.get("items")
                or payload.get("candidates")
                or payload.get("cases")
                or payload.get("traces")
                or payload.get("data")
                or []
            )
            return [item for item in items if isinstance(item, dict)]
        items = getattr(payload, "items", None)
        if isinstance(items, list):
            return items
        return []

    def _first_dict(self, *values: Any) -> dict[str, Any]:
        for value in values:
            if isinstance(value, dict):
                return value
        return {}

    def _source_id(
        self,
        raw: dict[str, Any],
        *,
        action_type: str,
        nm_id: int | None,
        order_id: str | None,
        srid: str | None,
        matched_return: dict[str, Any],
    ) -> str:
        explicit = self._str(
            raw.get("source_id")
            or raw.get("sourceId")
            or raw.get("external_id")
            or raw.get("externalId")
        )
        if explicit:
            return explicit
        case_code = self._str(raw.get("case_code") or raw.get("caseCode"))
        if case_code:
            return f"defect_case:{case_code}"
        case_id = self._str(raw.get("id") or raw.get("case_id") or raw.get("caseId"))
        if case_id:
            return f"defect_case:{case_id}"
        return_record_id = self._str(
            matched_return.get("id")
            or matched_return.get("record_id")
            or matched_return.get("recordId")
        )
        if return_record_id:
            return f"defect_return:{return_record_id}"
        stable = (
            srid or order_id or (str(nm_id) if nm_id is not None else None) or "manual"
        )
        return f"{action_type}:{stable}"

    def _finance_trace(
        self,
        raw: dict[str, Any],
        *,
        matched_return: dict[str, Any],
        compensation_check: dict[str, Any],
    ) -> dict[str, Any] | None:
        trace = raw.get("finance_trace") or raw.get("financeTrace") or raw.get("trace")
        if isinstance(trace, dict):
            return self._safe_payload(trace)
        finance_snapshot = {
            "source": "backenddefect",
            "case_id": raw.get("id") or raw.get("case_id") or raw.get("caseId"),
            "case_code": raw.get("case_code") or raw.get("caseCode"),
            "matched_return_record_id": raw.get("matched_return_record_id")
            or raw.get("matchedReturnRecordId")
            or matched_return.get("id"),
            "claim_amount_basis": raw.get("claim_amount_basis")
            or raw.get("claimAmountBasis"),
            "compensation_check": compensation_check or None,
            "compensation_matches": raw.get("compensation_matches")
            or raw.get("compensationMatches"),
            "matching_details": raw.get("matching_details")
            or raw.get("matchingDetails"),
        }
        finance_snapshot = {
            key: value
            for key, value in finance_snapshot.items()
            if value not in (None, [], {})
        }
        return self._safe_payload(finance_snapshot) if finance_snapshot else None

    def _evidence_snapshot(
        self, raw: dict[str, Any], *, matched_return: dict[str, Any]
    ) -> dict[str, Any] | None:
        snapshot = {
            "matched_return_record": matched_return or None,
            "match_candidates": raw.get("match_candidates")
            or raw.get("matchCandidates"),
            "media_items": raw.get("media_items")
            or raw.get("mediaItems")
            or raw.get("media"),
            "extracted_codes": raw.get("extracted_codes") or raw.get("extractedCodes"),
            "support_submissions": raw.get("support_submissions")
            or raw.get("supportSubmissions"),
            "support_tickets": raw.get("support_tickets") or raw.get("supportTickets"),
            "appeal_drafts": raw.get("appeal_drafts") or raw.get("appealDrafts"),
            "proof_check_result": raw.get("proof_check_result")
            or raw.get("proofCheckResult"),
        }
        snapshot = {
            key: value for key, value in snapshot.items() if value not in (None, [], {})
        }
        return self._safe_payload(snapshot) if snapshot else None

    def _dump(self, value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if hasattr(value, "__dict__"):
            return {
                key: item
                for key, item in vars(value).items()
                if not key.startswith("_")
            }
        return {}

    def _title(self, action_type: str) -> str:
        return {
            "defect_claim_candidate": "Defect claim candidate",
            "compensation_underpayment_candidate": "Compensation underpayment candidate",
            "evidence_missing": "Claims evidence missing",
            "repeat_claim_needed": "Repeat claim needed",
        }.get(action_type, "Claims candidate")

    def _priority(self, value: Any) -> Priority:
        try:
            return Priority(str(value or "P2").upper())
        except ValueError:
            return Priority.P2

    def _severity(self, priority: str) -> str:
        return {
            "P0": "critical",
            "P1": "high",
            "P2": "medium",
            "P3": "low",
            "P4": "low",
        }.get(str(priority).upper(), "medium")

    def _priority_from_issue(self, raw: dict[str, Any]) -> str:
        severity = str(raw.get("severity") or "").lower()
        if (
            severity == "critical"
            or raw.get("effective_financial_final_blocker") is True
        ):
            return "P1"
        if severity == "error" or raw.get("financial_final_blocker") is True:
            return "P1"
        if severity == "warning":
            return "P2"
        return "P3"

    def _priority_score(self, priority: str, impact: float | None) -> float:
        base = {"P0": 100.0, "P1": 80.0, "P2": 60.0, "P3": 40.0, "P4": 20.0}.get(
            str(priority).upper(), 40.0
        )
        return base + min(float(impact or 0) / 1000.0, 20.0)

    def _safe_payload(self, value: Any) -> Any:
        secret_tokens = {
            "api_key",
            "authorization",
            "credential",
            "encrypted_token",
            "encryption_key",
            "headers",
            "jwt",
            "password",
            "refresh_token",
            "secret",
            "token",
        }
        private_tokens = {
            "phone",
            "email",
            "buyer",
            "customer",
            "passport",
            "address",
            "fio",
            "full_name",
        }
        if isinstance(value, dict):
            return {
                key: self._safe_payload(item)
                for key, item in value.items()
                if not any(
                    token in str(key).lower()
                    for token in secret_tokens | private_tokens
                )
            }
        if isinstance(value, list):
            return [self._safe_payload(item) for item in value]
        return value

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if auth and self.settings.claims_internal_token:
            headers["Authorization"] = f"Bearer {self.settings.claims_internal_token}"
        async with httpx.AsyncClient(
            timeout=self.settings.claims_http_timeout_seconds
        ) as client:
            response = await client.request(
                method,
                f"{self._base_url}{path}",
                params=params,
                json=json_body,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()

    @property
    def _base_url(self) -> str:
        return str(self.settings.claims_base_url or "").rstrip("/")

    def _int(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _float(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
