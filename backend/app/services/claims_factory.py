from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date, datetime
from io import BytesIO
from urllib.parse import parse_qs, unquote, urlparse
from typing import Any
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.time import utcnow
from app.models.claims import ClaimCandidate, ClaimDetectionRun
from app.models.finance import WBRealizationReportRow
from app.models.operator import (
    ExternalTicket,
    OperatorCase,
    OperatorDraft,
    OperatorEvidence,
    ResultEvent,
)
from app.models.orders import WBOrder
from app.models.sales import WBSale
from app.schemas.claims import (
    CaseDetailOut,
    CaseListItemOut,
    ClaimCandidatesPage,
    ClaimCandidateOut,
    ClaimCandidateStatusUpdate,
    ClaimDetectionRunOut,
    ClaimDetectionRunsPage,
    ClaimScanStartOut,
    ClaimsCaseCreate,
    ClaimsCaseFromSignalCreate,
    ClaimsCaseStatus,
    ClaimsCaseUpdate,
    ClaimsAppealDraftOut,
    ClaimsAppealDraftRequest,
    ClaimsCasesPage,
    ClaimsDraftGenerateRequest,
    ClaimsDraftMutationOut,
    ClaimsEvidenceCreate,
    ClaimsOrderLookupRequest,
    ClaimsProofCheckOut,
    ClaimsProofCheckRequest,
    ClaimsQrExtractOut,
    ClaimsSupportCategoriesOut,
    ClaimsSupportCategoryOut,
    ClaimsSupportSubcategoryOut,
    ClaimsSubmitRequest,
)
from app.schemas.operator import (
    CaseType,
    DraftOut,
    EvidenceOut,
    ExternalStatus,
    OperatorModule,
    ResultEventOut,
    TrustState,
)
from app.services.claims_case_templates import get_claim_case_template

logger = logging.getLogger(__name__)

NUMERIC_CODE_RE = re.compile(r"\d{4,20}")
SRID_CODE_RE = re.compile(r"[0-9a-f]{8,}[\w.-]*", re.IGNORECASE)


class ClaimsFactoryService:
    OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
    _rapidocr_instance: Any = None
    APPEAL_EXAMPLE_TEXT = """Здравствуйте!

Сообщаем о получении возврата товара с нарушениями.

Артикул: 203979308
Баркод: 4311001523761
Штрихкод: 32591063543
Номер стикера: 44633744017
Дата выдачи: 20.04.2026
SRID: 7c3f9bf41e4642d7b10b4f468c27d4d0
ПВЗ: г. Долгопрудный, Набережная улица, 29к1

При приемке установлено:
— молния выдрана (механическое повреждение изделия);
— товар утратил товарный вид и потребительские свойства.

Данный дефект носит эксплуатационный характер и не относится к производственным.
Изделие не подлежит повторной реализации и является некондиционным возвратом.

В связи с вышеизложенным, просим:
— провести проверку по данному возврату;
— компенсировать стоимость товара в полном объёме.

Готовы предоставить фото- и видеоматериалы, подтверждающие выявленные нарушения.

Ожидаем решение по обращению."""

    SUPPORT_CATEGORIES = [
        {
            "label": "Возврат товара продавцу",
            "value": "возврат-товара-продавцу",
            "index": 8,
            "subcategories": [
                {
                    "label": "Вернулся товар с дефектами",
                    "value": "вернулся-товар-с-дефектами",
                    "index": 2,
                },
                {
                    "label": "Вернулся не тот товар",
                    "value": "вернулся-не-тот-товар",
                    "index": 3,
                },
                {
                    "label": "Не пришел возврат",
                    "value": "не-пришел-возврат",
                    "index": 4,
                },
            ],
        },
        {
            "label": "Финансовые удержания и компенсации",
            "value": "финансовые-удержания-и-компенсации",
            "index": 9,
            "subcategories": [
                {
                    "label": "Не начислена компенсация",
                    "value": "не-начислена-компенсация",
                    "index": 1,
                },
                {
                    "label": "Некорректное удержание",
                    "value": "некорректное-удержание",
                    "index": 2,
                },
            ],
        },
        {
            "label": "Поставки и приемка",
            "value": "поставки-и-приемка",
            "index": 10,
            "subcategories": [
                {"label": "Недостача товара", "value": "недостача-товара", "index": 1},
                {
                    "label": "Расхождение по поставке",
                    "value": "расхождение-по-поставке",
                    "index": 2,
                },
            ],
        },
    ]

    source_module = "claims"
    detector_types = (
        "defect",
        "supply_discrepancy",
        "missing_goods",
        "report_anomaly",
        "compensation_underpayment",
        "repeat_claim",
        "pretrial",
    )

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def support_categories(
        self, *, account_id: int | None = None
    ) -> ClaimsSupportCategoriesOut:
        return ClaimsSupportCategoriesOut(
            account_id=account_id,
            categories=[
                ClaimsSupportCategoryOut(
                    label=str(item["label"]),
                    value=str(item["value"]),
                    index=int(item["index"]) if item.get("index") is not None else None,
                    subcategories=[
                        ClaimsSupportSubcategoryOut(
                            label=str(child["label"]),
                            value=str(child["value"]),
                            index=int(child["index"])
                            if child.get("index") is not None
                            else None,
                        )
                        for child in item.get("subcategories", [])
                    ],
                )
                for item in self.SUPPORT_CATEGORIES
            ],
        )

    async def extract_order_from_qr_image(
        self,
        *,
        account_id: int,
        content: bytes,
        content_type: str,
        filename: str | None = None,
    ) -> ClaimsQrExtractOut:
        warnings: list[str] = []
        if not content:
            raise HTTPException(status_code=400, detail="Image file is empty")
        if not content_type.startswith("image/"):
            warnings.append("file_content_type_is_not_image")

        extracted = self._extract_wb_order_fields_from_image(content)
        order_fields = {
            "filename": filename or None,
            **extracted["order_fields"],
        }
        if extracted["raw_text"]:
            order_fields["raw_text"] = extracted["raw_text"]
        if extracted["extracted_codes"]:
            order_fields["extracted_codes"] = extracted["extracted_codes"]
        if not any(
            order_fields.get(key)
            for key in ("srid", "order_id", "shk_id", "sticker_id", "barcode", "nm_id")
        ):
            warnings.append("order_identifiers_not_found_in_media")
        return ClaimsQrExtractOut(
            account_id=account_id,
            order_fields={
                key: value
                for key, value in order_fields.items()
                if value not in (None, "")
            },
            raw_text=extracted["raw_text"] or None,
            confidence=extracted["confidence"],
            warnings=warnings,
        )

    async def lookup_order_fields(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        payload: ClaimsOrderLookupRequest,
    ) -> ClaimsQrExtractOut:
        order_fields = self._normalize_order_fields(payload.order_fields)
        media_fields = {
            key: value
            for key, value in payload.order_fields.items()
            if key in {"media_files", "video_file", "filename"}
            and value not in (None, "")
        }
        enriched = {**media_fields, **order_fields}
        warnings: list[str] = []

        identifiers = {
            "srid": self._str_or_none(order_fields.get("srid")),
            "barcode": self._str_or_none(order_fields.get("barcode")),
            "order_id": self._int_or_none(order_fields.get("order_id")),
            "shk_id": self._int_or_none(
                order_fields.get("shk_id") or order_fields.get("sticker_id")
            ),
            "sticker_id": self._str_or_none(order_fields.get("sticker_id")),
            "nm_id": self._int_or_none(order_fields.get("nm_id")),
        }
        if not any(identifiers.values()):
            warnings.append("order_identifiers_not_found_in_media")
            return ClaimsQrExtractOut(
                account_id=account_id, order_fields=enriched, warnings=warnings
            )

        row, source = await self._find_wb_order_source(
            session, account_id=account_id, identifiers=identifiers
        )
        if row is None:
            warnings.append("wb_order_not_found")
            return ClaimsQrExtractOut(
                account_id=account_id, order_fields=enriched, warnings=warnings
            )

        enriched.update(self._order_fields_from_wb_row(row, source=source))
        enriched["source_system"] = source
        return ClaimsQrExtractOut(
            account_id=account_id, order_fields=enriched, warnings=warnings
        )

    async def generate_ai_appeal_draft(
        self,
        *,
        account_id: int,
        payload: ClaimsAppealDraftRequest,
    ) -> ClaimsAppealDraftOut:
        order_fields = self._normalize_order_fields(payload.order_fields)
        fallback = self._fallback_appeal_payload(
            payload=payload, order_fields=order_fields
        )
        warnings: list[str] = []
        if not self.settings.openai_api_key:
            warnings.append("openai_api_key_not_configured")
            return ClaimsAppealDraftOut(
                account_id=account_id, warnings=warnings, **fallback
            )

        prompt = {
            "example_text": self.APPEAL_EXAMPLE_TEXT,
            "category": payload.category,
            "subcategory": payload.subcategory,
            "order_fields": order_fields,
            "defect_description": payload.defect_description,
            "operator_note": payload.operator_note,
            "video_url": payload.video_url or None,
            "requirements": [
                "Пиши на русском языке для поддержки WB.",
                "Сохраняй деловой тон и структуру, близкую к примеру, но не копируй дословно.",
                "Не придумывай факты и не добавляй отсутствующие идентификаторы.",
                "Верни строго JSON с полями category, subcategory, subject, body, facts_used, missing_fields.",
                "body должен быть готовым текстом обращения без markdown.",
            ],
        }
        request = {
            "model": self.settings.openai_model,
            "instructions": "Ты пишешь обращения для поддержки продавца Wildberries. Возвращай только JSON.",
            "input": json.dumps(prompt, ensure_ascii=False),
        }
        try:
            data = await self._request_openai_response(request)
            parsed = self._load_json_object(self._extract_openai_text(data))
            merged = self._merge_appeal_payload(parsed, fallback)
            merged["model_name"] = self.settings.openai_model
            return ClaimsAppealDraftOut(
                account_id=account_id, warnings=warnings, **merged
            )
        except Exception as exc:
            warnings.append(f"openai_draft_failed:{exc.__class__.__name__}")
            return ClaimsAppealDraftOut(
                account_id=account_id, warnings=warnings, **fallback
            )

    async def start_detection_scan(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        detector_types: list[str] | None,
        date_from: date | None = None,
        date_to: date | None = None,
        requested_by_user_id: int | None = None,
        force: bool = False,
        detector: Any,
    ) -> ClaimScanStartOut:
        normalized = self._normalize_detector_types(detector_types)
        warnings: list[str] = []
        unavailable_sources: list[str] = []
        runs: list[ClaimDetectionRunOut] = []

        for detector_type in normalized:
            run = ClaimDetectionRun(
                account_id=account_id,
                detector_type=detector_type,
                status="running",
                requested_by_user_id=requested_by_user_id,
                date_from=date_from,
                date_to=date_to,
                started_at=utcnow(),
                heartbeat_at=utcnow(),
                source_snapshot_json={"force": force, "mode": "local_sync"},
                cursor_json={},
            )
            session.add(run)
            await session.flush()
            try:
                raw = await self._run_detector(
                    detector,
                    detector_type=detector_type,
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                    session=session,
                )
                items = list((raw or {}).get("items") or [])
                created, updated, skipped = await self._upsert_claim_candidates(
                    session,
                    account_id=account_id,
                    detector_type=detector_type,
                    run=run,
                    items=items,
                    date_from=date_from,
                    date_to=date_to,
                )
                status = str((raw or {}).get("status") or ("ok" if items else "empty"))
                if status == "ok" and not items:
                    status = "empty"
                if status in {"ok", "empty", "not_enough_data"}:
                    run.status = "completed"
                else:
                    run.status = "failed"
                    unavailable_sources.append(detector_type)
                run.candidates_found = len(items)
                run.candidates_created = created
                run.candidates_updated = updated
                run.candidates_skipped = skipped
                run.error_code = None if run.status == "completed" else status
                run.error_summary = self._str_or_none((raw or {}).get("message"))
                run.source_snapshot_json = self._safe_payload(
                    {
                        "detector_response_status": status,
                        "item_count": len(items),
                        "unavailable_sources": list(
                            (raw or {}).get("unavailable_sources") or []
                        ),
                        "warnings": list((raw or {}).get("warnings") or []),
                        "force": force,
                    }
                )
                warnings.extend(str(item) for item in (raw or {}).get("warnings") or [])
            except Exception as exc:
                run.status = "failed"
                run.error_code = exc.__class__.__name__
                run.error_summary = str(exc)[:500]
                run.rows_failed = 1
                unavailable_sources.append(detector_type)
            run.finished_at = utcnow()
            run.heartbeat_at = run.finished_at
            runs.append(self._run_out(run))

        await session.commit()
        return ClaimScanStartOut(
            account_id=account_id,
            run_ids=[item.id for item in runs],
            runs=runs,
            warnings=sorted(set(warnings)),
            unavailable_sources=sorted(set(unavailable_sources)),
        )

    async def process_detection_run(
        self,
        session: AsyncSession,
        *,
        run_id: int,
        detector: Any,
    ) -> ClaimDetectionRunOut | None:
        run = await session.get(ClaimDetectionRun, run_id)
        if run is None or run.status not in {"queued", "running"}:
            return None
        run.status = "running"
        run.started_at = run.started_at or utcnow()
        run.heartbeat_at = utcnow()
        run.source_snapshot_json = self._safe_payload(
            {**(run.source_snapshot_json or {}), "mode": "local_worker"}
        )
        try:
            raw = await self._run_detector(
                detector,
                detector_type=run.detector_type,
                account_id=run.account_id,
                date_from=run.date_from,
                date_to=run.date_to,
                session=session,
            )
            items = list((raw or {}).get("items") or [])
            created, updated, skipped = await self._upsert_claim_candidates(
                session,
                account_id=run.account_id,
                detector_type=run.detector_type,
                run=run,
                items=items,
                date_from=run.date_from,
                date_to=run.date_to,
            )
            status = str((raw or {}).get("status") or ("ok" if items else "empty"))
            if status == "ok" and not items:
                status = "empty"
            run.status = (
                "completed"
                if status in {"ok", "empty", "not_enough_data"}
                else "failed"
            )
            run.candidates_found = len(items)
            run.candidates_created = created
            run.candidates_updated = updated
            run.candidates_skipped = skipped
            run.error_code = None if run.status == "completed" else status
            run.error_summary = self._str_or_none((raw or {}).get("message"))
            run.source_snapshot_json = self._safe_payload(
                {
                    **(run.source_snapshot_json or {}),
                    "detector_response_status": status,
                    "item_count": len(items),
                    "unavailable_sources": list(
                        (raw or {}).get("unavailable_sources") or []
                    ),
                    "warnings": list((raw or {}).get("warnings") or []),
                }
            )
        except Exception as exc:
            run.status = "failed"
            run.error_code = exc.__class__.__name__
            run.error_summary = str(exc)[:500]
            run.rows_failed += 1
        run.finished_at = utcnow()
        run.heartbeat_at = run.finished_at
        await session.flush()
        return self._run_out(run)

    async def list_detection_runs(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        detector_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ClaimDetectionRunsPage:
        filters = [ClaimDetectionRun.account_id == account_id]
        if detector_type:
            filters.append(ClaimDetectionRun.detector_type == detector_type)
        if status:
            filters.append(ClaimDetectionRun.status == status)
        total_result = await session.execute(
            select(func.count()).select_from(ClaimDetectionRun).where(*filters)
        )
        rows_result = await session.execute(
            select(ClaimDetectionRun)
            .where(*filters)
            .order_by(ClaimDetectionRun.created_at.desc(), ClaimDetectionRun.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return ClaimDetectionRunsPage(
            account_id=account_id,
            total=int(total_result.scalar_one() or 0),
            limit=limit,
            offset=offset,
            items=[self._run_out(row) for row in rows_result.scalars()],
        )

    async def get_detection_run(
        self, session: AsyncSession, *, account_id: int, run_id: int
    ) -> ClaimDetectionRunOut:
        row = await session.get(ClaimDetectionRun, run_id)
        if row is None or row.account_id != account_id:
            raise HTTPException(status_code=404, detail="Claim detection run not found")
        return self._run_out(row)

    async def list_candidates(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        detector_type: str | None = None,
        status: str | None = None,
        nm_id: int | None = None,
        run_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ClaimCandidatesPage:
        filters = [ClaimCandidate.account_id == account_id]
        if detector_type:
            filters.append(ClaimCandidate.detector_type == detector_type)
        if status:
            filters.append(ClaimCandidate.status == status)
        if nm_id is not None:
            filters.append(ClaimCandidate.nm_id == nm_id)
        if run_id is not None:
            filters.append(ClaimCandidate.detection_run_id == run_id)
        total_result = await session.execute(
            select(func.count()).select_from(ClaimCandidate).where(*filters)
        )
        rows_result = await session.execute(
            select(ClaimCandidate)
            .where(*filters)
            .order_by(ClaimCandidate.last_seen_at.desc(), ClaimCandidate.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return ClaimCandidatesPage(
            account_id=account_id,
            total=int(total_result.scalar_one() or 0),
            limit=limit,
            offset=offset,
            items=[self._candidate_out(row) for row in rows_result.scalars()],
        )

    async def get_candidate(
        self, session: AsyncSession, *, account_id: int, candidate_id: int
    ) -> ClaimCandidateOut:
        row = await self._candidate_or_404(
            session, account_id=account_id, candidate_id=candidate_id
        )
        return self._candidate_out(row)

    async def update_candidate_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        candidate_id: int,
        payload: ClaimCandidateStatusUpdate,
        updated_by: int | None = None,
    ) -> ClaimCandidateOut:
        row = await self._candidate_or_404(
            session, account_id=account_id, candidate_id=candidate_id
        )
        allowed = {
            "new",
            "reviewing",
            "accepted",
            "rejected",
            "ignored",
            "resolved",
            "case_created",
        }
        if payload.status not in allowed:
            raise HTTPException(
                status_code=400, detail="Unsupported claim candidate status"
            )
        row.status = payload.status
        if payload.status in {"rejected", "ignored", "resolved"}:
            row.resolved_at = utcnow()
        data = dict(row.payload_json or {})
        data["status_change"] = {
            "status": payload.status,
            "reason": payload.reason,
            "updated_by": updated_by,
        }
        row.payload_json = self._safe_payload(data)
        await session.commit()
        await session.refresh(row)
        return self._candidate_out(row)

    async def create_case_from_candidate(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        candidate_id: int,
        created_by: int | None = None,
    ) -> CaseDetailOut:
        candidate = await self._candidate_or_404(
            session, account_id=account_id, candidate_id=candidate_id
        )
        if candidate.case_id is not None:
            return await self.get_case(
                session, account_id=account_id, case_id=candidate.case_id
            )
        case_payload = ClaimsCaseCreate(
            account_id=account_id,
            case_type=self._case_type_for_detector(candidate.detector_type),
            nm_id=candidate.nm_id,
            order_id=candidate.order_id,
            title=candidate.title or "Claim candidate",
            summary=candidate.business_explanation or "",
            priority=self._priority_for_candidate(candidate),
            estimated_amount=candidate.expected_amount,
            source_id=f"claims:candidate:{candidate.id}",
            external_id=candidate.external_reference,
            payload={
                **dict(candidate.payload_json or {}),
                "candidate_id": candidate.id,
                "detector_type": candidate.detector_type,
                "reason_code": candidate.reason_code,
                "fingerprint": candidate.fingerprint,
                "evidence_summary": dict(candidate.evidence_summary_json or {}),
                "created_from_candidate": True,
            },
        )
        detail = await self.create_case(
            session, payload=case_payload, created_by=created_by
        )
        candidate.case_id = int(detail.id)
        candidate.status = "case_created"
        candidate.resolved_at = utcnow()
        await session.commit()
        return detail

    async def create_case(
        self,
        session: AsyncSession,
        *,
        payload: ClaimsCaseCreate,
        created_by: int | None = None,
    ) -> CaseDetailOut:
        source_id = payload.source_id or f"claims:case:{uuid4().hex}"
        template = get_claim_case_template(payload.case_type)
        case_payload = {
            **payload.payload,
            "priority": str(payload.priority),
            "estimated_amount": payload.estimated_amount,
            "order_id": payload.order_id,
            "srid": payload.srid,
            "created_by": created_by,
            "case_template": {
                "required_evidence_types": list(template.required_evidence_types),
                "draft_type": template.draft_type.value,
                "recommended_guided_fix": template.recommended_guided_fix,
                "default_priority": template.default_priority.value,
                "requires_external_ticket": template.requires_external_ticket,
            },
        }
        row = OperatorCase(
            account_id=payload.account_id,
            source_module=self.source_module,
            source_id=source_id,
            external_id=payload.external_id,
            nm_id=payload.nm_id,
            vendor_code=payload.vendor_code,
            case_type=str(payload.case_type),
            status=ClaimsCaseStatus.CANDIDATE,
            external_status=ExternalStatus.NOT_CREATED,
            title=payload.title,
            summary=payload.summary,
            payload_json=case_payload,
        )
        session.add(row)
        await session.flush()
        self._add_event(
            session,
            account_id=row.account_id,
            case_id=row.id,
            source_id=row.source_id,
            event_type="case_created",
            status="done",
            message="Claims case candidate created.",
            payload={"created_by": created_by, "case_type": row.case_type},
        )
        await session.commit()
        await session.refresh(row)
        return await self.get_case(session, account_id=row.account_id, case_id=row.id)

    async def create_case_from_signal(
        self,
        session: AsyncSession,
        *,
        payload: ClaimsCaseFromSignalCreate,
        created_by: int | None = None,
    ) -> CaseDetailOut:
        existing = await self._case_by_source(
            session,
            account_id=payload.account_id,
            source_id=payload.source_id,
        )
        if existing is not None:
            return await self.get_case(
                session, account_id=payload.account_id, case_id=existing.id
            )

        signal = payload.model_dump(mode="json")
        create_payload = ClaimsCaseCreate(
            account_id=payload.account_id,
            case_type=payload.case_type,
            nm_id=payload.nm_id,
            vendor_code=payload.vendor_code,
            title=payload.title,
            summary=payload.summary,
            priority=payload.priority,
            estimated_amount=payload.estimated_amount,
            source_id=payload.source_id,
            payload={
                **(payload.payload or {}),
                "signal": signal,
                "source_module": payload.source_module,
                "created_from_signal": True,
            },
        )
        detail = await self.create_case(
            session, payload=create_payload, created_by=created_by
        )
        case_id = int(detail.id)
        self._add_event(
            session,
            account_id=payload.account_id,
            case_id=case_id,
            source_id=payload.source_id,
            event_type="case_created_from_signal",
            status="done",
            message="Claims case created from Action Center signal.",
            payload={
                "created_by": created_by,
                "source_module": payload.source_module,
                "source_id": payload.source_id,
                "signal": signal,
                "external_operation": False,
            },
        )
        await session.commit()
        return await self.get_case(
            session, account_id=payload.account_id, case_id=case_id
        )

    async def list_cases(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_type: str | None = None,
        status: str | None = None,
        nm_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> ClaimsCasesPage:
        filters = [
            OperatorCase.account_id == account_id,
            OperatorCase.source_module == self.source_module,
        ]
        if case_type:
            filters.append(OperatorCase.case_type == case_type)
        if status:
            filters.append(OperatorCase.status == status)
        if nm_id is not None:
            filters.append(OperatorCase.nm_id == nm_id)

        result = await session.execute(
            select(OperatorCase)
            .where(*filters)
            .order_by(OperatorCase.created_at.desc(), OperatorCase.id.desc())
        )
        rows = [row for row in result.scalars() if not self._is_synthetic_case(row)]
        total = len(rows)
        rows = rows[offset : offset + limit]
        return ClaimsCasesPage(
            account_id=account_id,
            total=total,
            limit=limit,
            offset=offset,
            items=[self._case_list_item(row) for row in rows],
        )

    async def get_case(
        self, session: AsyncSession, *, account_id: int, case_id: int
    ) -> CaseDetailOut:
        row = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        evidence = await self._case_evidence(
            session, account_id=account_id, case_id=case_id
        )
        drafts = await self._case_drafts(
            session, account_id=account_id, case_id=case_id
        )
        events = await self.result_events(
            session, account_id=account_id, case_id=case_id
        )
        base = self._case_list_item(
            row, evidence_count=len(evidence), draft_count=len(drafts)
        )
        return CaseDetailOut(
            **base.model_dump(),
            description=str(
                (row.payload_json or {}).get("description") or row.summary or ""
            ),
            finance_trace=dict((row.payload_json or {}).get("finance_trace") or {}),
            evidence=evidence,
            drafts=drafts,
            result_events=events,
        )

    async def update_case_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        payload: ClaimsCaseUpdate,
        updated_by: int | None = None,
    ) -> CaseDetailOut:
        row = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        previous_status = row.status
        if payload.status is not None:
            row.status = str(payload.status)
        if payload.title is not None:
            row.title = payload.title
        if payload.summary is not None:
            row.summary = payload.summary
        merged_payload = dict(row.payload_json or {})
        if payload.priority is not None:
            merged_payload["priority"] = str(payload.priority)
        if payload.estimated_amount is not None:
            merged_payload["estimated_amount"] = payload.estimated_amount
        merged_payload.update(payload.payload or {})
        merged_payload["updated_by"] = updated_by
        row.payload_json = merged_payload
        self._add_event(
            session,
            account_id=account_id,
            case_id=row.id,
            source_id=row.source_id,
            event_type="case_updated",
            status="done",
            message="Claims case updated.",
            payload={
                "previous_status": previous_status,
                "status": row.status,
                "updated_by": updated_by,
            },
        )
        await session.commit()
        await session.refresh(row)
        return await self.get_case(session, account_id=account_id, case_id=case_id)

    async def attach_evidence(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        payload: ClaimsEvidenceCreate,
        created_by: int | None = None,
    ) -> EvidenceOut:
        case = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        evidence_payload = {
            **payload.payload,
            "description": payload.description,
            "file_name": payload.file_name,
            "content_type": payload.content_type,
            "url": payload.url,
            "captured_at": payload.captured_at.isoformat()
            if payload.captured_at
            else None,
            "created_by": created_by,
        }
        row = OperatorEvidence(
            account_id=account_id,
            case_id=case.id,
            source_module=self.source_module,
            source_id=payload.source_id or f"claims:evidence:{case.id}:{uuid4().hex}",
            external_id=payload.external_id,
            nm_id=case.nm_id,
            vendor_code=case.vendor_code,
            evidence_type=payload.evidence_type,
            status="new",
            title=payload.title,
            payload_json=evidence_payload,
        )
        session.add(row)
        if case.status == ClaimsCaseStatus.CANDIDATE:
            case.status = ClaimsCaseStatus.EVIDENCE_NEEDED
        self._add_event(
            session,
            account_id=account_id,
            case_id=case.id,
            source_id=row.source_id,
            event_type="evidence_attached",
            status="done",
            message="Evidence linked to claims case.",
            payload={"evidence_type": payload.evidence_type, "created_by": created_by},
        )
        await session.commit()
        await session.refresh(row)
        return self._evidence_out(row)

    async def generate_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        payload: ClaimsDraftGenerateRequest,
        created_by: int | None = None,
    ) -> ClaimsDraftMutationOut:
        case = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        body = self._draft_body(case, payload=payload)
        row = OperatorDraft(
            account_id=account_id,
            case_id=case.id,
            source_module=self.source_module,
            source_id=f"claims:draft:{case.id}:{uuid4().hex}",
            external_id=case.external_id,
            nm_id=case.nm_id,
            vendor_code=case.vendor_code,
            draft_type=str(payload.draft_type),
            status="new",
            external_status=ExternalStatus.DRAFT_READY,
            title=f"Черновик обращения: {case.title or case.case_type}",
            body_text=body,
            payload_json={
                **payload.payload,
                "language": payload.language,
                "tone": payload.tone,
                "created_by": created_by,
                "requires_confirmation": True,
            },
        )
        session.add(row)
        case.status = ClaimsCaseStatus.DRAFT_READY
        case.external_status = ExternalStatus.DRAFT_READY
        await session.flush()
        self._add_event(
            session,
            account_id=account_id,
            case_id=case.id,
            draft_id=row.id,
            source_id=row.source_id,
            event_type="draft_generated",
            status="done",
            external_status=ExternalStatus.DRAFT_READY,
            message="Claims draft generated for manual review.",
            payload={"draft_type": str(payload.draft_type), "created_by": created_by},
        )
        await session.commit()
        await session.refresh(row)
        return ClaimsDraftMutationOut(
            account_id=account_id,
            case_id=str(case.id),
            draft=self._draft_out(row),
            message="Draft generated. Manual review and confirm are required before submission.",
        )

    async def proof_check(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        payload: ClaimsProofCheckRequest | None = None,
    ) -> ClaimsProofCheckOut:
        case = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        evidence = await self._case_evidence(
            session, account_id=account_id, case_id=case_id
        )
        drafts = await self._case_drafts(
            session, account_id=account_id, case_id=case_id
        )
        case_payload = dict(case.payload_json or {})
        missing: list[str] = []
        if not evidence:
            missing.append("evidence")
        if not (case.nm_id or case.vendor_code):
            missing.append("product_identity")
        if not (
            case_payload.get("order_id")
            or case_payload.get("srid")
            or case_payload.get("sticker_id")
            or case_payload.get("shk_id")
            or case_payload.get("return_id")
        ):
            missing.append("order_or_return_identity")
        if not drafts:
            missing.append("draft")
        passed = not missing
        recommendations = self._proof_recommendations(missing)
        case_payload["last_proof_check"] = {
            "passed": passed,
            "missing_evidence": missing,
            "checked_at": utcnow().isoformat(),
            "request": (payload.payload if payload else {}),
        }
        case.payload_json = case_payload
        if passed and case.status == ClaimsCaseStatus.DRAFT_READY:
            case.status = ClaimsCaseStatus.READY_TO_SUBMIT
        elif not passed and case.status in {
            ClaimsCaseStatus.CANDIDATE,
            ClaimsCaseStatus.DRAFT_READY,
        }:
            case.status = ClaimsCaseStatus.EVIDENCE_NEEDED
        self._add_event(
            session,
            account_id=account_id,
            case_id=case.id,
            source_id=case.source_id,
            event_type="proof_checked",
            status="done" if passed else "blocked",
            message="Proof check passed."
            if passed
            else "Proof check found missing evidence.",
            payload={"passed": passed, "missing_evidence": missing},
        )
        await session.commit()
        return ClaimsProofCheckOut(
            account_id=account_id,
            case_id=str(case_id),
            passed=passed,
            missing_evidence=missing,
            recommendations=recommendations,
            warnings=[] if passed else ["case_not_ready_to_submit"],
            data={"evidence_count": len(evidence), "draft_count": len(drafts)},
        )

    async def submit_case_manual_confirm(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        payload: ClaimsSubmitRequest,
        created_by: int | None = None,
    ) -> ResultEventOut:
        case = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        draft = await self._resolve_draft(
            session, account_id=account_id, case_id=case_id, draft_id=payload.draft_id
        )
        external_submit_enabled = bool(self.settings.enable_claims_submit)
        if not payload.confirm:
            result = self._result_out(
                account_id=account_id,
                case_id=str(case_id),
                draft_id=str(draft.id) if draft is not None else payload.draft_id,
                event_type="submit_blocked_confirmation_required",
                title="Требуется ручное подтверждение",
                message="Отправка претензии требует явного confirm=true.",
                success=False,
                data=self._submit_safety_data(
                    external_submit_enabled=external_submit_enabled,
                    external_submit_attempted=False,
                    external_ticket_created=False,
                    local_status=str(case.status),
                    user_message="Подтвердите действие вручную. Без confirm=true внешняя отправка невозможна.",
                ),
                warnings=["manual_confirm_required"],
            )
            self._persist_result_event(
                session,
                result,
                case=case,
                draft=draft,
                payload={
                    "manual_confirm": False,
                    "created_by": created_by,
                    "external_submit_enabled": external_submit_enabled,
                    "external_submit_attempted": False,
                },
            )
            await session.commit()
            return result

        if not external_submit_enabled:
            case.status = ClaimsCaseStatus.IN_REVIEW
            case.external_status = ExternalStatus.NOT_CREATED
            if draft is not None:
                draft.status = "done"
                draft.external_status = ExternalStatus.DRAFT_READY
            result = self._result_out(
                account_id=account_id,
                case_id=str(case.id),
                draft_id=str(draft.id) if draft is not None else None,
                event_type="manual_submission_recorded",
                external_status=ExternalStatus.NOT_CREATED,
                title="Manual submission recorded locally",
                message=(
                    "Manual claims submission was recorded in finance. "
                    "No external claims service was called because ENABLE_CLAIMS_SUBMIT=false."
                ),
                success=True,
                data=self._submit_safety_data(
                    external_submit_enabled=False,
                    external_submit_attempted=False,
                    external_ticket_created=False,
                    local_status="manual_submission_recorded",
                    user_message=(
                        "Ручная отправка зафиксирована локально. "
                        "Внешняя отправка отключена настройкой ENABLE_CLAIMS_SUBMIT=false."
                    ),
                ),
                warnings=["claims_external_submit_disabled"],
            )
            self._persist_result_event(
                session,
                result,
                case=case,
                draft=draft,
                payload={
                    "manual_confirm": True,
                    "created_by": created_by,
                    "external_submit_enabled": False,
                    "external_submit_attempted": False,
                    "external_ticket_created": False,
                },
            )
            await session.commit()
            return result

        ticket = await self.track_external_ticket(
            session,
            account_id=account_id,
            case_id=case.id,
            draft_id=draft.id if draft is not None else None,
            external_ticket_id=payload.external_ticket_id,
            ticket_number=payload.ticket_number,
            status=ExternalStatus.SUBMITTED,
            payload={
                **payload.payload,
                "created_by": created_by,
                "manual_confirm": True,
            },
            commit=False,
        )
        case.status = ClaimsCaseStatus.SUBMITTED
        case.external_status = ExternalStatus.SUBMITTED
        if draft is not None:
            draft.status = "done"
            draft.external_status = ExternalStatus.SUBMITTED
        result = self._result_out(
            account_id=account_id,
            case_id=str(case.id),
            draft_id=str(draft.id) if draft is not None else None,
            event_type="submit_confirmed",
            external_status=ExternalStatus.SUBMITTED,
            title="Claims submission confirmed",
            message="Manual confirmation recorded and external ticket tracking created.",
            success=True,
            data={
                **self._submit_safety_data(
                    external_submit_enabled=True,
                    external_submit_attempted=False,
                    external_ticket_created=True,
                    local_status=str(case.status),
                    user_message=(
                        "Подтверждение принято. Создана запись внешнего тикета; "
                        "сам вызов внешнего сервиса должен выполняться только через включенный claims adapter."
                    ),
                ),
                "ticket_id": str(ticket.id) if ticket.id is not None else None,
                "external_submission_mode": "manual_confirm",
            },
        )
        self._persist_result_event(
            session,
            result,
            case=case,
            draft=draft,
            ticket=ticket,
            payload={
                "manual_confirm": True,
                "created_by": created_by,
                "external_submit_enabled": True,
                "external_submit_attempted": False,
                "external_ticket_created": True,
            },
        )
        await session.commit()
        return result

    def _submit_safety_data(
        self,
        *,
        external_submit_enabled: bool,
        external_submit_attempted: bool,
        external_ticket_created: bool,
        local_status: str,
        user_message: str,
    ) -> dict[str, Any]:
        return {
            "external_submit_attempted": external_submit_attempted,
            "external_submit_enabled": external_submit_enabled,
            "external_ticket_created": external_ticket_created,
            "local_status": local_status,
            "user_message": user_message,
        }

    async def track_external_ticket(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        draft_id: int | None = None,
        external_ticket_id: str | None = None,
        ticket_number: str | None = None,
        status: str = ExternalStatus.SUBMITTED,
        payload: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> ExternalTicket:
        case = await self._case_or_404(session, account_id=account_id, case_id=case_id)
        row = ExternalTicket(
            account_id=account_id,
            case_id=case.id,
            draft_id=draft_id,
            source_module=self.source_module,
            source_id=f"claims:ticket:{case.id}:{uuid4().hex}",
            external_id=external_ticket_id,
            nm_id=case.nm_id,
            vendor_code=case.vendor_code,
            ticket_type=case.case_type,
            status=str(status),
            title=ticket_number
            or external_ticket_id
            or f"Claims ticket for case {case.id}",
            payload_json=payload or {},
        )
        session.add(row)
        await session.flush()
        if commit:
            await session.commit()
            await session.refresh(row)
        return row

    async def result_events(
        self, session: AsyncSession, *, account_id: int, case_id: int
    ) -> list[ResultEventOut]:
        result = await session.execute(
            select(ResultEvent)
            .where(
                ResultEvent.account_id == account_id,
                ResultEvent.case_id == case_id,
                ResultEvent.source_module == self.source_module,
            )
            .order_by(ResultEvent.created_at.desc(), ResultEvent.id.desc())
        )
        return [self._event_out(row) for row in result.scalars()]

    async def _run_detector(
        self,
        detector: Any,
        *,
        detector_type: str,
        account_id: int,
        date_from: date | None,
        date_to: date | None,
        session: AsyncSession,
    ) -> dict[str, Any]:
        date_range = (date_from, date_to) if date_from or date_to else None
        if detector_type == "defect":
            return await detector.detect_defect_candidates(
                account_id, date_range=date_range, nm_id=None
            )
        if detector_type == "supply_discrepancy":
            return await detector.detect_supply_discrepancy_candidates(
                account_id, date_range=date_range, session=session
            )
        if detector_type == "missing_goods":
            return await detector.detect_missing_goods_candidates(
                account_id, date_range=date_range, session=session
            )
        if detector_type == "report_anomaly":
            return await detector.detect_report_anomaly_candidates(
                account_id, date_range=date_range, session=session
            )
        if detector_type == "compensation_underpayment":
            return await detector.detect_compensation_underpayment_candidates(
                account_id, date_range=date_range, session=session
            )
        if detector_type == "repeat_claim":
            return await detector.detect_repeat_claim_candidates(
                account_id, date_range=date_range
            )
        if detector_type == "pretrial":
            return await detector.detect_pretrial_candidates(
                account_id, date_range=date_range
            )
        return {
            "status": "not_implemented",
            "items": [],
            "message": f"Unknown detector type: {detector_type}",
        }

    async def _upsert_claim_candidates(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        detector_type: str,
        run: ClaimDetectionRun,
        items: list[dict[str, Any]],
        date_from: date | None,
        date_to: date | None,
    ) -> tuple[int, int, int]:
        created = 0
        updated = 0
        skipped = 0
        for item in items:
            if not isinstance(item, dict):
                skipped += 1
                continue
            fingerprint = self._candidate_fingerprint(
                account_id=account_id,
                detector_type=detector_type,
                item=item,
                date_from=date_from,
                date_to=date_to,
            )
            result = await session.execute(
                select(ClaimCandidate)
                .where(
                    ClaimCandidate.account_id == account_id,
                    ClaimCandidate.fingerprint == fingerprint,
                )
                .limit(1)
            )
            existing = next(iter(result.scalars()), None)
            values = self._candidate_values(
                account_id=account_id,
                detector_type=detector_type,
                item=item,
                run=run,
                fingerprint=fingerprint,
                date_from=date_from,
                date_to=date_to,
            )
            if existing is None:
                session.add(ClaimCandidate(**values))
                created += 1
            else:
                protected_statuses = {
                    "accepted",
                    "rejected",
                    "ignored",
                    "resolved",
                    "case_created",
                }
                values.pop("first_seen_at", None)
                for key, value in values.items():
                    if key == "status" and existing.status in protected_statuses:
                        continue
                    setattr(existing, key, value)
                updated += 1
        return created, updated, skipped

    def _candidate_values(
        self,
        *,
        account_id: int,
        detector_type: str,
        item: dict[str, Any],
        run: ClaimDetectionRun,
        fingerprint: str,
        date_from: date | None,
        date_to: date | None,
    ) -> dict[str, Any]:
        source_id = self._first_present(
            item, "source_id", "id", "candidate_id", "external_id"
        )
        expected_amount = self._float_or_none(
            self._first_present(
                item,
                "expected_amount",
                "estimated_amount",
                "amount",
                "impact",
                "delta_amount",
            )
        )
        quantity_affected = self._float_or_none(
            self._first_present(
                item, "quantity_affected", "quantity", "missing_quantity", "qty"
            )
        )
        now = utcnow()
        return {
            "account_id": account_id,
            "detector_type": detector_type,
            "source_type": str(item.get("source_type") or detector_type),
            "source_id": self._str_or_none(source_id),
            "external_id": self._str_or_none(
                self._first_present(item, "external_id", "externalId")
            ),
            "external_reference": self._str_or_none(
                self._first_present(
                    item,
                    "external_reference",
                    "supply_external_id",
                    "supply_id",
                    "order_id",
                    "sale_id",
                )
            ),
            "nm_id": self._int_or_none(self._first_present(item, "nm_id", "nmId")),
            "sku_id": self._int_or_none(self._first_present(item, "sku_id", "skuId")),
            "supply_id": self._str_or_none(
                self._first_present(item, "supply_id", "supplyId", "supply_external_id")
            ),
            "report_id": self._str_or_none(
                self._first_present(item, "report_id", "realizationreport_id")
            ),
            "order_id": self._str_or_none(
                self._first_present(item, "order_id", "orderId", "srid")
            ),
            "sale_id": self._str_or_none(
                self._first_present(item, "sale_id", "saleId")
            ),
            "warehouse_id": self._str_or_none(
                self._first_present(item, "warehouse_id", "warehouseId")
            ),
            "period_from": self._date_or_none(item.get("period_from")) or date_from,
            "period_to": self._date_or_none(item.get("period_to")) or date_to,
            "title": str(
                item.get("title") or self._default_candidate_title(detector_type)
            ),
            "business_explanation": self._str_or_none(
                self._first_present(
                    item,
                    "business_explanation",
                    "summary",
                    "reason",
                    "message",
                    "explanation",
                )
            ),
            "reason_code": self._str_or_none(
                self._first_present(
                    item, "reason_code", "action_type", "case_type", "type"
                )
            ),
            "severity": self._severity(item),
            "confidence": self._confidence(item.get("confidence")),
            "expected_amount": expected_amount,
            "quantity_affected": quantity_affected,
            "status": "new",
            "fingerprint": fingerprint,
            "evidence_summary_json": self._safe_payload(
                self._first_present(
                    item,
                    "evidence_summary",
                    "evidence_snapshot",
                    "finance_trace",
                    "evidence",
                )
                or {}
            ),
            "source_revision": self._str_or_none(item.get("source_revision"))
            or "claims_factory_v1",
            "detection_run_id": run.id,
            "case_id": self._int_or_none(item.get("case_id")),
            "first_seen_at": now,
            "last_seen_at": now,
            "payload_json": self._safe_payload(item),
        }

    def _candidate_out(self, row: ClaimCandidate) -> ClaimCandidateOut:
        return ClaimCandidateOut(
            id=str(row.id),
            account_id=row.account_id,
            detector_type=row.detector_type,
            source_type=row.source_type,
            source_id=row.source_id,
            external_id=row.external_id,
            external_reference=row.external_reference,
            nm_id=row.nm_id,
            sku_id=row.sku_id,
            supply_id=row.supply_id,
            report_id=row.report_id,
            order_id=row.order_id,
            sale_id=row.sale_id,
            warehouse_id=row.warehouse_id,
            period_from=row.period_from,
            period_to=row.period_to,
            title=row.title or "",
            business_explanation=row.business_explanation,
            reason_code=row.reason_code,
            severity=row.severity or "medium",
            confidence=row.confidence,
            expected_amount=row.expected_amount,
            quantity_affected=row.quantity_affected,
            status=row.status or "new",
            fingerprint=row.fingerprint,
            evidence_summary=dict(row.evidence_summary_json or {}),
            source_revision=row.source_revision,
            detection_run_id=str(row.detection_run_id)
            if row.detection_run_id is not None
            else None,
            case_id=str(row.case_id) if row.case_id is not None else None,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            data=dict(row.payload_json or {}),
        )

    def _run_out(self, row: ClaimDetectionRun) -> ClaimDetectionRunOut:
        return ClaimDetectionRunOut(
            id=str(row.id),
            account_id=row.account_id,
            detector_type=row.detector_type,
            status=row.status,
            requested_by_user_id=row.requested_by_user_id,
            date_from=row.date_from,
            date_to=row.date_to,
            started_at=row.started_at,
            finished_at=row.finished_at,
            heartbeat_at=row.heartbeat_at,
            candidates_found=row.candidates_found or 0,
            candidates_created=row.candidates_created or 0,
            candidates_updated=row.candidates_updated or 0,
            candidates_skipped=row.candidates_skipped or 0,
            rows_failed=row.rows_failed or 0,
            error_code=row.error_code,
            error_summary=row.error_summary,
            data=dict(row.source_snapshot_json or {}),
            warnings=list((row.source_snapshot_json or {}).get("warnings") or []),
        )

    async def _candidate_or_404(
        self, session: AsyncSession, *, account_id: int, candidate_id: int
    ) -> ClaimCandidate:
        row = await session.get(ClaimCandidate, candidate_id)
        if row is None or row.account_id != account_id:
            raise HTTPException(status_code=404, detail="Claim candidate not found")
        return row

    def _candidate_fingerprint(
        self,
        *,
        account_id: int,
        detector_type: str,
        item: dict[str, Any],
        date_from: date | None,
        date_to: date | None,
    ) -> str:
        explicit = self._str_or_none(item.get("fingerprint"))
        if explicit:
            return explicit[:96]
        basis = {
            "account_id": account_id,
            "detector_type": detector_type,
            "source_id": self._first_present(
                item, "source_id", "id", "candidate_id", "external_id"
            ),
            "nm_id": self._first_present(item, "nm_id", "nmId"),
            "sku_id": self._first_present(item, "sku_id", "skuId"),
            "supply_id": self._first_present(
                item, "supply_id", "supplyId", "supply_external_id"
            ),
            "report_id": self._first_present(item, "report_id", "realizationreport_id"),
            "order_id": self._first_present(item, "order_id", "orderId", "srid"),
            "sale_id": self._first_present(item, "sale_id", "saleId"),
            "reason_code": self._first_present(
                item, "reason_code", "action_type", "case_type", "type"
            ),
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        }
        encoded = json.dumps(basis, sort_keys=True, default=str, ensure_ascii=True)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _normalize_detector_types(self, values: list[str] | None) -> list[str]:
        raw = [
            str(value).strip().lower().replace("-", "_")
            for value in (values or ["all"])
            if str(value).strip()
        ]
        if not raw or "all" in raw:
            return list(self.detector_types)
        normalized = []
        for value in raw:
            if value in self.detector_types and value not in normalized:
                normalized.append(value)
        if not normalized:
            raise HTTPException(
                status_code=400, detail="No supported detector_types provided"
            )
        return normalized

    def _case_type_for_detector(self, detector_type: str) -> CaseType:
        try:
            return CaseType(detector_type)
        except ValueError:
            return CaseType.DEFECT

    def _priority_for_candidate(self, row: ClaimCandidate) -> str:
        severity = str(row.severity or "").lower()
        if severity in {"critical", "high"}:
            return "P1"
        if severity == "low":
            return "P4"
        return "P2"

    def _default_candidate_title(self, detector_type: str) -> str:
        return {
            "defect": "Defect compensation candidate",
            "supply_discrepancy": "Supply discrepancy candidate",
            "missing_goods": "Missing goods candidate",
            "report_anomaly": "Report anomaly candidate",
            "compensation_underpayment": "Compensation underpayment candidate",
            "repeat_claim": "Repeat claim candidate",
            "pretrial": "Pretrial candidate",
        }.get(detector_type, "Claim candidate")

    def _first_present(self, values: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            if key not in values:
                continue
            value = values[key]
            if value is None or value == "":
                continue
            return value
        return None

    def _severity(self, item: dict[str, Any]) -> str:
        raw = str(self._first_present(item, "severity", "priority") or "medium").lower()
        mapping = {
            "p0": "high",
            "p1": "high",
            "p2": "medium",
            "p3": "medium",
            "p4": "low",
        }
        return mapping.get(
            raw, raw if raw in {"low", "medium", "high", "critical"} else "medium"
        )

    def _confidence(self, value: Any) -> float | None:
        if isinstance(value, str):
            mapping = {"high": 0.85, "medium": 0.6, "low": 0.35}
            if value.lower() in mapping:
                return mapping[value.lower()]
        return self._float_or_none(value)

    def _safe_payload(self, value: Any) -> Any:
        private_tokens = {
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
        if isinstance(value, dict):
            return {
                key: self._safe_payload(item)
                for key, item in value.items()
                if not any(token in str(key).lower() for token in private_tokens)
            }
        if isinstance(value, list):
            return [self._safe_payload(item) for item in value]
        return value

    async def _case_or_404(
        self, session: AsyncSession, *, account_id: int, case_id: int
    ) -> OperatorCase:
        row = await session.get(OperatorCase, case_id)
        if (
            row is None
            or row.account_id != account_id
            or row.source_module != self.source_module
            or self._is_synthetic_case(row)
        ):
            raise HTTPException(status_code=404, detail="Case not found")
        return row

    def _is_synthetic_case(self, row: OperatorCase) -> bool:
        payload = dict(row.payload_json or {})
        if payload.get("synthetic") is True or payload.get("shadow_synthetic") is True:
            return True
        if payload.get("audit") is True or payload.get("is_test") is True:
            return True
        source = str(
            payload.get("source_module") or payload.get("source") or row.source_id or ""
        ).lower()
        if source in {"audit", "test", "synthetic"}:
            return True
        title = f"{row.title or ''} {row.summary or ''}".lower()
        return (
            "runtime audit" in title or "runtime-audit" in title or "synthetic" in title
        )

    async def _case_by_source(
        self, session: AsyncSession, *, account_id: int, source_id: str
    ) -> OperatorCase | None:
        result = await session.execute(
            select(OperatorCase)
            .where(
                OperatorCase.account_id == account_id,
                OperatorCase.source_module == self.source_module,
                OperatorCase.source_id == source_id,
            )
            .limit(1)
        )
        return next(iter(result.scalars()), None)

    async def _case_evidence(
        self, session: AsyncSession, *, account_id: int, case_id: int
    ) -> list[EvidenceOut]:
        result = await session.execute(
            select(OperatorEvidence)
            .where(
                OperatorEvidence.account_id == account_id,
                OperatorEvidence.case_id == case_id,
                OperatorEvidence.source_module == self.source_module,
            )
            .order_by(OperatorEvidence.created_at.desc(), OperatorEvidence.id.desc())
        )
        return [self._evidence_out(row) for row in result.scalars()]

    async def _case_drafts(
        self, session: AsyncSession, *, account_id: int, case_id: int
    ) -> list[DraftOut]:
        result = await session.execute(
            select(OperatorDraft)
            .where(
                OperatorDraft.account_id == account_id,
                OperatorDraft.case_id == case_id,
                OperatorDraft.source_module == self.source_module,
            )
            .order_by(OperatorDraft.created_at.desc(), OperatorDraft.id.desc())
        )
        return [self._draft_out(row) for row in result.scalars()]

    async def _resolve_draft(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        case_id: int,
        draft_id: str | None,
    ) -> OperatorDraft | None:
        if draft_id:
            try:
                row = await session.get(OperatorDraft, int(draft_id))
            except ValueError:
                row = None
            if (
                row is not None
                and row.account_id == account_id
                and row.case_id == case_id
                and row.source_module == self.source_module
            ):
                return row
            return None
        result = await session.execute(
            select(OperatorDraft)
            .where(
                OperatorDraft.account_id == account_id,
                OperatorDraft.case_id == case_id,
                OperatorDraft.source_module == self.source_module,
            )
            .order_by(OperatorDraft.created_at.desc(), OperatorDraft.id.desc())
            .limit(1)
        )
        return next(iter(result.scalars()), None)

    def _case_list_item(
        self, row: OperatorCase, *, evidence_count: int = 0, draft_count: int = 0
    ) -> CaseListItemOut:
        payload = dict(row.payload_json or {})
        return CaseListItemOut(
            id=str(row.id),
            case_type=row.case_type,
            external_id=row.external_id,
            external_status=row.external_status or ExternalStatus.NOT_CREATED,
            account_id=row.account_id,
            nm_id=row.nm_id,
            order_id=self._str_or_none(payload.get("order_id")),
            srid=self._str_or_none(payload.get("srid")),
            title=row.title or "",
            summary=row.summary or "",
            priority=self._priority(payload.get("priority")),
            status=self._case_status(row.status),
            trust_state=TrustState.PROVISIONAL,
            amount_claimed=self._float_or_none(
                payload.get("estimated_amount") or payload.get("amount_claimed")
            ),
            amount_approved=self._float_or_none(payload.get("amount_approved")),
            opened_at=row.created_at,
            updated_at=row.updated_at,
            deadline_at=self._datetime_or_none(payload.get("deadline_at")),
            evidence_count=evidence_count,
            draft_count=draft_count,
            data=payload,
            warnings=[],
        )

    def _evidence_out(self, row: OperatorEvidence) -> EvidenceOut:
        payload = dict(row.payload_json or {})
        return EvidenceOut(
            id=str(row.id),
            case_id=str(row.case_id) if row.case_id is not None else None,
            module=OperatorModule.CLAIMS,
            evidence_type=row.evidence_type,
            title=row.title or "",
            description=str(payload.get("description") or ""),
            source_type="claims",
            source_id=row.source_id,
            file_name=self._str_or_none(payload.get("file_name")),
            content_type=self._str_or_none(payload.get("content_type")),
            url=self._str_or_none(payload.get("url")),
            captured_at=self._datetime_or_none(payload.get("captured_at")),
            data=payload,
        )

    def _draft_out(self, row: OperatorDraft) -> DraftOut:
        payload = dict(row.payload_json or {})
        return DraftOut(
            id=str(row.id),
            draft_type=row.draft_type,
            external_status=row.external_status or ExternalStatus.DRAFT_READY,
            account_id=row.account_id,
            case_id=str(row.case_id) if row.case_id is not None else None,
            source_type="claims",
            source_id=row.source_id,
            title=row.title or "",
            text=row.body_text or "",
            language=self._str_or_none(payload.get("language")),
            status=row.status or "new",
            trust_state=TrustState.PROVISIONAL,
            requires_confirmation=True,
            created_by=self._int_or_none(payload.get("created_by")),
            approved_by=self._int_or_none(payload.get("approved_by")),
            created_at=row.created_at,
            updated_at=row.updated_at,
            data=payload,
        )

    def _event_out(self, row: ResultEvent) -> ResultEventOut:
        payload = dict(row.payload_json or {})
        return ResultEventOut(
            id=str(row.id),
            module=OperatorModule.CLAIMS,
            event_type=row.event_type,
            external_status=row.external_status,
            account_id=row.account_id,
            action_id=str(row.action_id) if row.action_id is not None else None,
            case_id=str(row.case_id) if row.case_id is not None else None,
            draft_id=str(row.draft_id) if row.draft_id is not None else None,
            title=str(payload.get("title") or row.event_type),
            message=row.message or "",
            success=payload.get("success"),
            occurred_at=row.created_at,
            created_by=self._int_or_none(payload.get("created_by")),
            data=dict(payload.get("data") or {}),
            warnings=list(payload.get("warnings") or []),
        )

    def _result_out(
        self,
        *,
        account_id: int,
        case_id: str,
        event_type: str,
        title: str,
        message: str,
        success: bool,
        draft_id: str | None = None,
        external_status: str | None = None,
        data: dict[str, Any] | None = None,
        warnings: list[str] | None = None,
    ) -> ResultEventOut:
        return ResultEventOut(
            module=OperatorModule.CLAIMS,
            event_type=event_type,
            external_status=external_status,
            account_id=account_id,
            case_id=case_id,
            draft_id=draft_id,
            title=title,
            message=message,
            success=success,
            occurred_at=utcnow(),
            data=data or {},
            warnings=warnings or [],
        )

    def _persist_result_event(
        self,
        session: AsyncSession,
        result: ResultEventOut,
        *,
        case: OperatorCase,
        draft: OperatorDraft | None = None,
        ticket: ExternalTicket | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_payload = {
            **(payload or {}),
            "success": result.success,
            "title": result.title,
            "data": result.data,
            "warnings": result.warnings,
        }
        session.add(
            ResultEvent(
                account_id=case.account_id,
                case_id=case.id,
                draft_id=draft.id if draft is not None else None,
                ticket_id=ticket.id if ticket is not None else None,
                source_module=self.source_module,
                source_id=case.source_id,
                external_id=case.external_id,
                nm_id=case.nm_id,
                vendor_code=case.vendor_code,
                event_type=result.event_type,
                status="done" if result.success else "blocked",
                external_status=str(result.external_status)
                if result.external_status is not None
                else None,
                message=result.message,
                payload_json=event_payload,
            )
        )

    def _add_event(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        event_type: str,
        status: str,
        message: str,
        source_id: str | None = None,
        case_id: int | None = None,
        draft_id: int | None = None,
        ticket_id: int | None = None,
        external_status: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        session.add(
            ResultEvent(
                account_id=account_id,
                case_id=case_id,
                draft_id=draft_id,
                ticket_id=ticket_id,
                source_module=self.source_module,
                source_id=source_id,
                event_type=event_type,
                status=status,
                external_status=str(external_status)
                if external_status is not None
                else None,
                message=message,
                payload_json=payload or {},
            )
        )

    def _draft_body(
        self, case: OperatorCase, *, payload: ClaimsDraftGenerateRequest
    ) -> str:
        case_payload = dict(case.payload_json or {})
        provided_body = (
            payload.payload.get("body") if isinstance(payload.payload, dict) else None
        )
        if isinstance(provided_body, str) and provided_body.strip():
            return provided_body.strip()
        facts: list[str] = []
        identifiers = [
            ("Артикул WB / nm_id", case.nm_id),
            ("Артикул продавца", case.vendor_code),
            ("Штрихкод", case_payload.get("barcode")),
            ("ШК", case_payload.get("shk_id")),
            ("Стикер", case_payload.get("sticker_id")),
            ("Заказ", case_payload.get("order_id")),
            ("SRID", case_payload.get("srid")),
            ("Возврат", case_payload.get("return_id")),
            (
                "ПВЗ / склад",
                case_payload.get("pvz_address") or case_payload.get("warehouse_name"),
            ),
        ]
        for label, value in identifiers:
            if value not in (None, ""):
                facts.append(f"- {label}: {value}")
        amount = (
            case_payload.get("estimated_amount")
            or case_payload.get("amount")
            or case.estimated_amount
        )

        defect_lines = [
            str(case_payload.get(key)).strip()
            for key in (
                "defect_description",
                "damage_description",
                "defect_reason",
                "reason",
            )
            if str(case_payload.get(key) or "").strip()
        ]
        parts = [
            "Здравствуйте.",
            "",
            f"Прошу рассмотреть обращение по случаю «{case.title or case.case_type}».",
            "",
            "Данные по обращению:",
        ]
        parts.extend(facts or ["- Идентификаторы будут приложены оператором вручную."])
        if amount not in (None, ""):
            parts.append(f"- Ожидаемая сумма компенсации/корректировки: {amount}.")
        if case.summary:
            parts.extend(["", "Описание ситуации:", case.summary])
        if defect_lines:
            parts.extend(
                [
                    "",
                    "Зафиксированные признаки дефекта/расхождения:",
                    *[f"- {line}" for line in defect_lines],
                ]
            )
        parts.extend(
            [
                "",
                "Просим проверить материалы, историю движения товара и корректность начислений.",
                "При подтверждении факта просим оформить компенсацию/корректировку по данному случаю.",
                "Фото, видео, строки отчета и другие доказательства приложены к обращению при наличии.",
            ]
        )
        if payload.instructions:
            parts.extend(["", f"Комментарий оператора: {payload.instructions}"])
        return "\n".join(parts)

    def _proof_recommendations(self, missing: list[str]) -> list[str]:
        recommendations = {
            "evidence": "Attach photo, video, report row, or support screenshot evidence.",
            "product_identity": "Add nm_id or vendor_code so the case can be linked to Product 360.",
            "order_or_return_identity": "Add order_id, srid, sticker_id, or return identifier.",
            "draft": "Generate and review a draft before submission.",
        }
        return [recommendations[item] for item in missing if item in recommendations]

    async def _request_openai_response(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(
            timeout=self.settings.openai_timeout_seconds
        ) as client:
            response = await client.post(
                self.OPENAI_RESPONSES_URL, headers=headers, json=payload
            )
            response.raise_for_status()
            return response.json() if response.text else {}

    def _extract_openai_text(self, payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    if isinstance(block, dict):
                        text = block.get("text")
                        if isinstance(text, str) and text.strip():
                            parts.append(text.strip())
            if parts:
                return "\n".join(parts).strip()
        return ""

    def _load_json_object(self, raw: str) -> dict[str, Any]:
        candidate = raw.strip()
        if candidate.startswith("```"):
            candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
            candidate = re.sub(r"\s*```$", "", candidate)
        parsed = json.loads(candidate or "{}")
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI response is not a JSON object")
        return parsed

    def _extract_wb_order_fields_from_image(self, content: bytes) -> dict[str, Any]:
        decoded_texts = self._decode_qr_and_barcodes(content)
        ocr_text = self._extract_order_ocr_text(content)
        raw_parts = [text for text in [*decoded_texts, ocr_text] if text]
        raw_text = "\n".join(dict.fromkeys(raw_parts))
        parsed_fields = self._extract_order_fields_from_text(raw_text)

        extracted_codes: list[dict[str, Any]] = []
        for text in raw_parts:
            extracted_codes.extend(
                self._classify_extracted_codes(
                    text, source="barcode" if text in decoded_texts else "ocr"
                )
            )

        best_codes: dict[tuple[str, str], dict[str, Any]] = {}
        for item in extracted_codes:
            key = (str(item.get("code_type") or ""), str(item.get("value") or ""))
            if not key[0] or not key[1]:
                continue
            current = best_codes.get(key)
            if current is None or float(current.get("confidence") or 0) < float(
                item.get("confidence") or 0
            ):
                best_codes[key] = item

        order_fields = dict(parsed_fields)
        sorted_codes = sorted(
            best_codes.values(),
            key=lambda item: float(item.get("confidence") or 0),
            reverse=True,
        )
        for code in sorted_codes:
            code_type = str(code.get("code_type") or "")
            value = str(code.get("value") or "").strip()
            if not value:
                continue
            if code_type == "srid":
                order_fields.setdefault("srid", value)
            elif code_type == "barcode":
                order_fields.setdefault("barcode", value)
            elif code_type == "shk_id":
                order_fields.setdefault("shk_id", value)
            elif code_type == "sticker_id":
                order_fields.setdefault("sticker_id", value)

        return {
            "order_fields": self._normalize_order_fields(order_fields),
            "raw_text": raw_text,
            "extracted_codes": sorted_codes,
            "confidence": max(
                (float(item.get("confidence") or 0) for item in sorted_codes),
                default=None,
            ),
        }

    def _decode_qr_and_barcodes(self, content: bytes) -> list[str]:
        try:
            from PIL import Image, ImageOps
        except Exception:
            return []

        try:
            image = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("RGB")
        except Exception:
            return []

        variants = self._image_variants_for_code_scan(image)
        values: list[str] = []
        seen: set[str] = set()

        try:
            import zxingcpp  # type: ignore
        except Exception:
            zxingcpp = None
        if zxingcpp is not None:
            for variant in variants:
                try:
                    decoded = zxingcpp.read_barcodes(variant)
                except Exception:
                    continue
                for item in decoded:
                    value = str(getattr(item, "text", "") or "").strip()
                    if value and value not in seen:
                        seen.add(value)
                        values.append(value)

        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
        except Exception:
            cv2 = None
            np = None
        if cv2 is not None and np is not None:
            qr_detector = getattr(cv2, "QRCodeDetector", lambda: None)()
            barcode_factory = getattr(cv2, "barcode_BarcodeDetector", None)
            barcode_detector = (
                barcode_factory() if barcode_factory is not None else None
            )
            for variant in variants:
                try:
                    cv_image = cv2.cvtColor(
                        np.array(variant.convert("RGB")), cv2.COLOR_RGB2BGR
                    )
                except Exception:
                    continue
                for value in self._opencv_qr_values(qr_detector, cv_image):
                    if value not in seen:
                        seen.add(value)
                        values.append(value)
                for value in self._opencv_barcode_values(barcode_detector, cv_image):
                    if value not in seen:
                        seen.add(value)
                        values.append(value)

        return values

    def _extract_order_ocr_text(self, content: bytes) -> str:
        rapid_text = self._extract_order_rapidocr_text(content)
        if rapid_text:
            return rapid_text

        try:
            from PIL import Image, ImageOps
            import pytesseract  # type: ignore
        except Exception:
            return ""

        try:
            image = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("L")
            text = pytesseract.image_to_string(
                image,
                config="--psm 6 -c tessedit_char_whitelist=0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-_:/?=&",
            )
        except Exception:
            return ""
        return str(text or "").strip()

    def _extract_order_rapidocr_text(self, content: bytes) -> str:
        try:
            from PIL import Image, ImageOps
            import numpy as np  # type: ignore
        except Exception:
            return ""

        engine = self._rapidocr_engine()
        if engine is None:
            return ""

        try:
            image = ImageOps.exif_transpose(Image.open(BytesIO(content))).convert("RGB")
            result, _ = engine(np.array(image))
        except Exception:
            return ""

        hits = self._rapidocr_hits(result or [])
        parts = [hit["text"] for hit in hits if hit.get("text")]
        parts.extend(
            value for value, _score in self._combined_rapidocr_numeric_hits(hits)
        )
        return "\n".join(dict.fromkeys(parts))

    @classmethod
    def _rapidocr_engine(cls) -> Any:
        if cls._rapidocr_instance is not None:
            return cls._rapidocr_instance or None
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except Exception:
            cls._rapidocr_instance = False
            return None
        try:
            cls._rapidocr_instance = RapidOCR()
        except Exception:
            cls._rapidocr_instance = False
        return cls._rapidocr_instance or None

    @staticmethod
    def _rapidocr_hits(items: list[Any]) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = str(item[1]).strip()
            if not text:
                continue
            try:
                score = float(item[2]) if len(item) > 2 else 0.0
            except (TypeError, ValueError):
                score = 0.0
            box = ClaimsFactoryService._rapidocr_box(item[0] if item else None)
            hits.append({"text": text, "score": score, "box": box})
        return hits

    @staticmethod
    def _rapidocr_box(raw_box: Any) -> tuple[tuple[float, float], ...] | None:
        if not isinstance(raw_box, (list, tuple)):
            return None
        points: list[tuple[float, float]] = []
        for point in raw_box:
            if not isinstance(point, (list, tuple)) or len(point) < 2:
                return None
            try:
                x = float(point[0])
                y = float(point[1])
            except (TypeError, ValueError):
                return None
            points.append((x, y))
        return tuple(points) if len(points) >= 4 else None

    @staticmethod
    def _combined_rapidocr_numeric_hits(
        hits: list[dict[str, Any]],
    ) -> list[tuple[str, float]]:
        combined: dict[str, float] = {}
        numeric_hits = [
            hit
            for hit in hits
            if str(hit.get("text") or "").isdigit()
            and 4 <= len(str(hit.get("text") or "")) <= 9
            and hit.get("box") is not None
        ]

        for top_hit in numeric_hits:
            top_bounds = ClaimsFactoryService._box_bounds(top_hit.get("box"))
            if top_bounds is None:
                continue
            top_left, top_top, top_right, top_bottom = top_bounds
            top_width = top_right - top_left
            top_height = top_bottom - top_top

            for bottom_hit in numeric_hits:
                if bottom_hit is top_hit:
                    continue
                combined_text = f"{top_hit['text']}{bottom_hit['text']}"
                if not combined_text.isdigit() or len(combined_text) not in {
                    10,
                    11,
                    12,
                    13,
                    14,
                }:
                    continue

                bottom_bounds = ClaimsFactoryService._box_bounds(bottom_hit.get("box"))
                if bottom_bounds is None:
                    continue
                bottom_left, bottom_top, bottom_right, bottom_bottom = bottom_bounds
                bottom_width = bottom_right - bottom_left
                bottom_height = bottom_bottom - bottom_top

                if bottom_top <= top_top:
                    continue
                if bottom_top - top_bottom > max(top_height, bottom_height) * 1.25:
                    continue

                overlap = min(top_right, bottom_right) - max(top_left, bottom_left)
                overlap_ratio = overlap / max(min(top_width, bottom_width), 1.0)
                center_dx = abs(
                    ((top_left + top_right) / 2.0)
                    - ((bottom_left + bottom_right) / 2.0)
                )
                center_limit = max(top_width, bottom_width) * 0.45
                if overlap_ratio < 0.35 and center_dx > center_limit:
                    continue

                quality = min(
                    float(top_hit.get("score") or 0),
                    float(bottom_hit.get("score") or 0),
                )
                stored = combined.get(combined_text)
                if stored is None or quality > stored:
                    combined[combined_text] = quality

        return [(value, score) for value, score in combined.items()]

    @staticmethod
    def _box_bounds(box: Any) -> tuple[float, float, float, float] | None:
        if not box:
            return None
        try:
            xs = [point[0] for point in box]
            ys = [point[1] for point in box]
        except Exception:
            return None
        return min(xs), min(ys), max(xs), max(ys)

    @staticmethod
    def _image_variants_for_code_scan(image: Any) -> list[Any]:
        try:
            from PIL import ImageOps
        except Exception:
            return [image]

        variants: list[Any] = []
        try:
            rgb = image.convert("RGB")
            max_edge = max(rgb.size)
            if max_edge > 1920:
                scale = 1920 / max_edge
                rgb = rgb.resize(
                    (
                        max(1, round(rgb.width * scale)),
                        max(1, round(rgb.height * scale)),
                    )
                )
            variants.append(rgb)
            if max(rgb.size) < 1200:
                scale = min(2.0, 2400 / max(max(rgb.size), 1))
                variants.append(
                    rgb.resize(
                        (
                            max(1, round(rgb.width * scale)),
                            max(1, round(rgb.height * scale)),
                        )
                    )
                )
            gray = ImageOps.grayscale(rgb)
            variants.append(gray)
            variants.append(ImageOps.autocontrast(gray))
        except Exception:
            return [image]
        return variants

    @staticmethod
    def _opencv_qr_values(detector: Any, cv_image: Any) -> list[str]:
        if detector is None:
            return []
        values: list[str] = []
        try:
            detected, decoded_info, _points, _ = detector.detectAndDecodeMulti(cv_image)
            if detected:
                values.extend(decoded_info)
        except Exception:
            pass
        try:
            value, _points, _ = detector.detectAndDecode(cv_image)
            values.append(value)
        except Exception:
            pass
        try:
            value, _points = detector.detectAndDecodeCurved(cv_image)
            values.append(value)
        except Exception:
            pass
        return [str(value).strip() for value in values if str(value or "").strip()]

    @staticmethod
    def _opencv_barcode_values(detector: Any, cv_image: Any) -> list[str]:
        if detector is None:
            return []
        try:
            decoded = detector.detectAndDecode(cv_image)
        except Exception:
            return []
        text = decoded[0] if isinstance(decoded, tuple) and decoded else decoded
        values = list(text) if isinstance(text, (list, tuple)) else [text]
        return [str(value).strip() for value in values if str(value or "").strip()]

    def _extract_order_fields_from_text(self, raw: str) -> dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}

        candidates: list[dict[str, Any]] = []
        candidates.append(self._parse_structured_order_text(text))
        for token in re.split(r"[\s;|]+", text):
            token = token.strip()
            if not token:
                continue
            candidates.append(self._parse_structured_order_text(unquote(token)))

        merged: dict[str, Any] = {}
        for item in candidates:
            for key, value in item.items():
                if value not in (None, "") and key not in merged:
                    merged[key] = value
        return self._normalize_order_fields(merged)

    def _parse_structured_order_text(self, text: str) -> dict[str, Any]:
        result: dict[str, Any] = {}

        try:
            parsed = json.loads(text)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            result.update(parsed)

        parsed_url = urlparse(text)
        query = parse_qs(parsed_url.query)
        if query:
            result.update({key: values[0] for key, values in query.items() if values})

        for key, value in re.findall(
            r"([A-Za-zА-Яа-я_ -]{2,32})\s*[:=]\s*([A-Za-z0-9._/-]{3,80})", text
        ):
            result[key.strip()] = value.strip()

        return result

    def _classify_extracted_codes(
        self, text: str, *, source: str
    ) -> list[dict[str, Any]]:
        codes: list[dict[str, Any]] = []
        base_confidence = 0.96 if source == "barcode" else 0.72

        for value in NUMERIC_CODE_RE.findall(str(text or "")):
            if len(value) in {12, 13, 14}:
                codes.append(
                    {
                        "code_type": "barcode",
                        "source": source,
                        "value": value,
                        "confidence": base_confidence,
                    }
                )
            elif len(value) in {10, 11}:
                codes.append(
                    {
                        "code_type": "sticker_id",
                        "source": source,
                        "value": value,
                        "confidence": base_confidence - 0.04,
                    }
                )
                codes.append(
                    {
                        "code_type": "shk_id",
                        "source": source,
                        "value": value,
                        "confidence": base_confidence - 0.08,
                    }
                )
            elif len(value) in {6, 7, 8, 9}:
                codes.append(
                    {
                        "code_type": "sticker_id",
                        "source": source,
                        "value": value,
                        "confidence": base_confidence - 0.16,
                    }
                )
                codes.append(
                    {
                        "code_type": "shk_id",
                        "source": source,
                        "value": value,
                        "confidence": base_confidence - 0.2,
                    }
                )

        for value in SRID_CODE_RE.findall(str(text or "")):
            if value.isdigit():
                continue
            if "." in value or len(value) >= 24:
                codes.append(
                    {
                        "code_type": "srid",
                        "source": source,
                        "value": value,
                        "confidence": base_confidence - 0.12,
                    }
                )
        return codes

    def _normalize_order_fields(self, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, Any] = {}
        aliases = {
            "nm_id": (
                "nm_id",
                "nmId",
                "nmID",
                "nm",
                "article",
                "Артикул",
                "Артикул WB",
            ),
            "vendor_code": (
                "vendor_code",
                "vendorCode",
                "supplier_article",
                "Артикул продавца",
            ),
            "barcode": (
                "barcode",
                "bar_code",
                "sku",
                "barcodeSku",
                "Баркод",
                "Штрихкод товара",
            ),
            "shk_id": ("shk_id", "shkId", "shk", "ШК", "Штрихкод"),
            "sticker_id": (
                "sticker_id",
                "stickerId",
                "sticker",
                "sticker_id_wb",
                "Номер стикера",
                "Стикер",
            ),
            "order_id": (
                "order_id",
                "orderId",
                "order_number",
                "orderNumber",
                "rid",
                "Заказ",
                "Номер заказа",
            ),
            "srid": ("srid", "SRID", "Srid"),
            "pvz_address": ("pvz_address", "pvz", "pickup_point", "ПВЗ"),
            "date": ("date", "completed_dt", "return_date", "Дата выдачи"),
            "raw_text": ("raw_text", "text", "decoded_text"),
        }
        for target, keys in aliases.items():
            for key in keys:
                item = value.get(key)
                if item not in (None, ""):
                    result[target] = item
                    break
        return result

    async def _find_wb_order_source(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        identifiers: dict[str, Any],
    ) -> tuple[Any | None, str | None]:
        sources: list[tuple[Any, str]] = [
            (WBRealizationReportRow, "wb_realization_report_rows"),
            (WBSale, "wb_sales"),
            (WBOrder, "wb_orders"),
        ]
        lookup_order = ("srid", "order_id", "shk_id", "sticker_id", "barcode", "nm_id")
        field_aliases = {"sticker_id": ("sticker",)}
        for model, source in sources:
            for key in lookup_order:
                value = identifiers.get(key)
                if value in (None, ""):
                    continue
                model_fields = (key, *field_aliases.get(key, ()))
                for model_field in model_fields:
                    column = getattr(model, model_field, None)
                    if column is None:
                        continue
                    stmt = select(model).where(
                        model.account_id == account_id, column == value
                    )
                    order_column = getattr(model, "created_at", None)
                    if order_column is None:
                        order_column = getattr(model, "id", None)
                    if order_column is not None:
                        stmt = stmt.order_by(order_column.desc())
                    row = await session.scalar(stmt.limit(1))
                    if row is not None:
                        return row, source
        return None, None

    def _order_fields_from_wb_row(
        self, row: Any, *, source: str | None
    ) -> dict[str, Any]:
        def first(*names: str) -> Any:
            for name in names:
                value = getattr(row, name, None)
                if value not in (None, ""):
                    return value
            payload = getattr(row, "payload", None)
            if isinstance(payload, dict):
                for name in names:
                    value = payload.get(name)
                    if value not in (None, ""):
                        return value
            return None

        fields: dict[str, Any] = {
            "srid": first("srid"),
            "order_id": first("order_id"),
            "nm_id": first("nm_id"),
            "vendor_code": first("vendor_code", "supplier_article"),
            "barcode": first("barcode"),
            "shk_id": first("shk_id"),
            "sticker_id": first("sticker", "sticker_id"),
            "pvz_address": first("office_name", "warehouse_name", "pvz_address"),
            "date": first("rr_date", "sale_dt", "date"),
            "product_name": first("title", "subject"),
            "brand": first("brand"),
            "source_system": source,
        }
        return {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in fields.items()
            if value not in (None, "")
        }

    def _fallback_appeal_payload(
        self, *, payload: ClaimsAppealDraftRequest, order_fields: dict[str, Any]
    ) -> dict[str, Any]:
        def field(key: str, default: str = "—") -> str:
            value = order_fields.get(key)
            return str(value).strip() if value not in (None, "") else default

        defect_lines = [
            line.strip(" -—;\t")
            for line in re.split(
                r"[\n;]+",
                payload.defect_description
                or payload.operator_note
                or "товар вернулся с признаками дефекта",
            )
            if line.strip(" -—;\t")
        ]
        body_lines = [
            "Здравствуйте!",
            "",
            "Сообщаем о получении возврата товара с нарушениями.",
            "",
            f"Артикул: {field('nm_id')}",
            f"Баркод: {field('barcode')}",
            f"Штрихкод: {field('shk_id')}",
            f"Номер стикера: {field('sticker_id')}",
            f"Дата выдачи: {field('date')}",
            f"SRID: {field('srid')}",
            f"ПВЗ: {field('pvz_address')}",
            "",
            "При приемке установлено:",
            *[f"— {line}" for line in defect_lines],
            "",
            "Данный дефект носит эксплуатационный характер и не относится к производственным.",
            "Изделие не подлежит повторной реализации и является некондиционным возвратом.",
            "",
            "В связи с вышеизложенным, просим:",
            "— провести проверку по данному возврату;",
            "— компенсировать стоимость товара в полном объёме.",
            "",
            "Готовы предоставить фото- и видеоматериалы, подтверждающие выявленные нарушения.",
        ]
        if payload.video_url:
            body_lines.extend(["", f"Видео: {payload.video_url}"])
        return {
            "category": payload.category,
            "subcategory": payload.subcategory,
            "subject": f"Обращение по возврату {field('sticker_id', field('srid', ''))}".strip(),
            "body": "\n".join(body_lines),
            "facts_used": [
                f"{key}={val}"
                for key, val in order_fields.items()
                if val not in (None, "")
            ],
            "missing_fields": [
                key
                for key in (
                    "nm_id",
                    "barcode",
                    "shk_id",
                    "sticker_id",
                    "srid",
                    "pvz_address",
                )
                if not order_fields.get(key)
            ],
            "model_name": "fallback-template",
        }

    def _merge_appeal_payload(
        self, parsed: dict[str, Any], fallback: dict[str, Any]
    ) -> dict[str, Any]:
        merged = dict(fallback)
        merged.update(
            {key: value for key, value in parsed.items() if value is not None}
        )
        for field in ("category", "subcategory", "subject", "body"):
            if (
                not isinstance(merged.get(field), str)
                or not str(merged.get(field)).strip()
            ):
                merged[field] = fallback[field]
        for field in ("facts_used", "missing_fields"):
            if not isinstance(merged.get(field), list):
                merged[field] = fallback[field]
        if not merged.get("model_name"):
            merged["model_name"] = fallback["model_name"]
        return merged

    def _case_status(self, value: Any) -> ClaimsCaseStatus:
        try:
            return ClaimsCaseStatus(str(value))
        except ValueError:
            return ClaimsCaseStatus.CANDIDATE

    def _priority(self, value: Any) -> str:
        text = str(value or "P3").upper()
        return text if text in {"P0", "P1", "P2", "P3", "P4"} else "P3"

    def _str_or_none(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value)
        return text if text else None

    def _int_or_none(self, value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _float_or_none(self, value: Any) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _datetime_or_none(self, value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    def _date_or_none(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value)).date()
        except ValueError:
            try:
                return date.fromisoformat(str(value))
            except ValueError:
                return None
