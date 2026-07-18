from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.grouping import (
    GroupingCandidate,
    GroupingProductSnapshot,
    GroupingRecommendation,
    GroupingReviewHistory,
    GroupingRun,
    GroupingSettings,
)
from app.models.product_cards import (
    WBProductCard,
    WBProductCardCharacteristic,
    WBProductCardSize,
)
from app.schemas.portal import (
    PortalActionRead,
    PortalGroupingPreviewRead,
    PortalProductGroupingRead,
)


SAFE_GROUPING_STATUSES = {
    "new",
    "reviewing",
    "accepted",
    "rejected",
    "postponed",
    "expired",
}


@dataclass(frozen=True)
class NormalizedGroupingProduct:
    account_id: int
    nm_id: int
    imt_id: int | None
    vendor_code: str | None
    article_core: str | None
    article_base_core: str | None
    title: str | None
    brand: str | None
    subject_name: str | None
    color_normalized: str | None
    characteristics: list[dict[str, Any]]
    sizes: list[dict[str, Any]]
    barcodes: list[str]
    media_summary: dict[str, Any]
    stock_summary: dict[str, Any]
    finance_summary: dict[str, Any]
    source_revision: str


@dataclass(frozen=True)
class EffectiveGroupingSettings:
    mode: str
    default_scenario: str
    minimum_confidence: float
    maximum_risk: float
    allow_cross_brand: bool
    allow_cross_subject: bool
    require_identity_evidence: bool


class GroupingBetaService:
    """Finance-owned local Grouping Beta.

    This service creates recommendation-only local candidates. It never calls WB
    write APIs and never produces a destructive merge/apply operation.
    """

    MAX_PRODUCTS_PER_RUN = 1500
    MAX_CANDIDATE_GROUPS = 200

    async def preview(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None,
        preset_key: str | None,
        recommendation_scenario_id: int | None,
        custom_config: dict[str, Any],
        requested_by_user_id: int | None = None,
    ) -> PortalGroupingPreviewRead:
        scenario = self._scenario(preset_key=preset_key, custom_config=custom_config)
        settings = await self._get_or_create_settings(session, account_id=account_id)
        effective_settings = self._effective_settings(
            settings, custom_config=custom_config
        )
        run = GroupingRun(
            account_id=account_id,
            scenario=scenario,
            status="running",
            requested_by_user_id=requested_by_user_id,
            started_at=utcnow(),
            heartbeat_at=utcnow(),
            settings_snapshot_json=self._settings_snapshot(
                effective_settings, custom_config=custom_config
            ),
            cursor_json={
                "nm_id": nm_id,
                "preset_key": preset_key,
                "recommendation_scenario_id": recommendation_scenario_id,
                "mode": "local",
            },
        )
        session.add(run)
        await session.flush()

        products = await self._load_products(
            session, account_id=account_id, nm_id=nm_id
        )
        snapshots = [
            self._snapshot_from_product(product, run_id=run.id) for product in products
        ]
        for snapshot in snapshots:
            session.add(snapshot)

        candidates = self._build_candidates(
            products,
            account_id=account_id,
            run_id=run.id,
            scenario=scenario,
            settings=effective_settings,
        )
        (
            persisted_candidates,
            created_count,
            updated_count,
        ) = await self._replace_run_candidates(
            session,
            account_id=account_id,
            run_id=run.id,
            candidates=candidates,
        )

        run.status = "completed"
        run.finished_at = utcnow()
        run.heartbeat_at = run.finished_at
        run.eligible_products = len(products)
        run.products_processed = len(products)
        run.products_skipped = max(0, len(products) - len(snapshots))
        run.products_failed = 0
        run.candidate_groups = len(persisted_candidates)
        run.candidate_pairs = sum(
            max(0, len(item.member_nm_ids_json) - 1) for item in persisted_candidates
        )
        run.recommendations_created = created_count
        run.recommendations_updated = updated_count
        run.source_revision = self._hash_payload(
            [product.source_revision for product in products]
        )
        await session.flush()
        await session.commit()

        visible_candidates = self._filter_candidates_for_nm(
            persisted_candidates, nm_id=nm_id
        )
        status = "beta" if visible_candidates else "empty"
        return PortalGroupingPreviewRead(
            status=status,
            account_id=account_id,
            nm_id=nm_id,
            summary={
                "mode": "local",
                "run_id": run.id,
                "scenario": scenario,
                "analyzed_product_count": len(products),
                "candidate_groups": len(persisted_candidates),
                "recommendations_created": created_count,
                "recommendations_updated": updated_count,
                "auto_merge_enabled": False,
                "analyzed_at": run.finished_at.isoformat() if run.finished_at else None,
            },
            recommendations=[
                self._candidate_payload(item) for item in visible_candidates
            ],
            message="local grouping beta run completed"
            if products
            else "no finance product cards found for grouping beta",
            raw={
                "mode": "local",
                "safe_operations": ["preview", "review", "export_payload"],
                "blocked_operations": ["merge-wb", "auto_apply", "card_mutation"],
            },
        )

    async def product_grouping(
        self, session: AsyncSession, *, account_id: int, nm_id: int
    ) -> PortalProductGroupingRead:
        candidates = await self._latest_candidates_for_nm(
            session, account_id=account_id, nm_id=nm_id
        )
        source = await self._latest_source_for_nm(
            session, account_id=account_id, nm_id=nm_id
        )
        if not candidates:
            latest_run = await self._latest_run(session, account_id=account_id)
            return PortalProductGroupingRead(
                status="empty",
                account_id=account_id,
                nm_id=nm_id,
                source=source,
                recommendation_count=0,
                message="no local grouping recommendations for this product",
                raw={
                    "mode": "local",
                    "last_run_id": latest_run.id if latest_run is not None else None,
                    "analyzed_product_count": latest_run.products_processed
                    if latest_run is not None
                    else 0,
                    "auto_merge_enabled": False,
                },
            )
        latest_run_id = candidates[0].run_id
        return PortalProductGroupingRead(
            status="beta",
            account_id=account_id,
            nm_id=nm_id,
            source=source,
            recommendations=[
                self._candidate_payload(candidate) for candidate in candidates
            ],
            recommendation_count=len(candidates),
            message="local grouping beta recommendations are review-only",
            raw={"mode": "local", "run_id": latest_run_id, "auto_merge_enabled": False},
        )

    async def process_queued_runs(
        self, session: AsyncSession, *, max_runs: int = 5
    ) -> int:
        runs = list(
            (
                await session.execute(
                    select(GroupingRun)
                    .where(GroupingRun.status.in_(("queued", "running")))
                    .order_by(GroupingRun.id.asc())
                    .limit(max(1, int(max_runs)))
                )
            ).scalars()
        )
        processed = 0
        for run in runs:
            try:
                run.status = "running"
                run.started_at = run.started_at or utcnow()
                run.heartbeat_at = utcnow()
                cursor = dict(run.cursor_json or {})
                nm_id_raw = cursor.get("nm_id")
                nm_id = int(nm_id_raw) if nm_id_raw not in (None, "") else None
                settings = await self._get_or_create_settings(
                    session, account_id=run.account_id
                )
                effective_settings = self._effective_settings(
                    settings,
                    custom_config=dict(run.settings_snapshot_json or {}).get(
                        "custom_config"
                    )
                    or {},
                )
                products = await self._load_products(
                    session, account_id=run.account_id, nm_id=nm_id
                )
                snapshots = [
                    self._snapshot_from_product(product, run_id=run.id)
                    for product in products
                ]
                for snapshot in snapshots:
                    session.add(snapshot)
                candidates = self._build_candidates(
                    products,
                    account_id=run.account_id,
                    run_id=run.id,
                    scenario=run.scenario,
                    settings=effective_settings,
                )
                (
                    persisted_candidates,
                    created_count,
                    updated_count,
                ) = await self._replace_run_candidates(
                    session,
                    account_id=run.account_id,
                    run_id=run.id,
                    candidates=candidates,
                )
                run.status = "completed"
                run.finished_at = utcnow()
                run.heartbeat_at = run.finished_at
                run.eligible_products = len(products)
                run.products_processed = len(products)
                run.products_skipped = max(0, len(products) - len(snapshots))
                run.products_failed = 0
                run.candidate_groups = len(persisted_candidates)
                run.candidate_pairs = sum(
                    max(0, len(item.member_nm_ids_json) - 1)
                    for item in persisted_candidates
                )
                run.recommendations_created = created_count
                run.recommendations_updated = updated_count
                run.source_revision = self._hash_payload(
                    [product.source_revision for product in products]
                )
                processed += 1
            except Exception as exc:
                run.status = "failed"
                run.finished_at = utcnow()
                run.heartbeat_at = run.finished_at
                run.products_failed += 1
                run.error_code = exc.__class__.__name__
                run.error_summary = str(exc)[:500]
        await session.flush()
        return processed

    async def recommendation_actions(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None = None,
        limit: int = 50,
        include_reviewed: bool = False,
    ) -> list[PortalActionRead]:
        statuses = ["new", "reviewing", "postponed"]
        if include_reviewed:
            statuses.extend(["accepted", "rejected"])
        stmt = select(GroupingCandidate).where(
            GroupingCandidate.account_id == account_id,
            GroupingCandidate.status.in_(statuses),
            GroupingCandidate.risk_level != "blocked",
        )
        if nm_id is not None:
            stmt = stmt.where(
                (GroupingCandidate.anchor_nm_id == nm_id)
                | (GroupingCandidate.member_nm_ids_json.contains([int(nm_id)]))
            )
        rows = list(
            (
                await session.execute(
                    stmt.order_by(
                        GroupingCandidate.confidence.desc(), GroupingCandidate.id.desc()
                    ).limit(max(1, min(limit, 100)))
                )
            ).scalars()
        )
        return [self._action_from_candidate(candidate) for candidate in rows]

    async def update_candidate_status(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        candidate_id: int,
        status: str,
        actor_user_id: int | None,
        reason: str | None,
    ) -> dict[str, Any]:
        new_status = str(status or "").strip().lower()
        if new_status not in SAFE_GROUPING_STATUSES:
            raise ValueError("illegal_status_transition")
        candidate = (
            (
                await session.execute(
                    select(GroupingCandidate).where(
                        GroupingCandidate.account_id == account_id,
                        GroupingCandidate.id == candidate_id,
                    )
                )
            )
            .scalars()
            .first()
        )
        if candidate is None:
            raise ValueError("candidate_not_found")
        old_status = candidate.status
        candidate.status = new_status
        candidate.reviewed_by_user_id = actor_user_id
        candidate.reviewed_at = utcnow()
        candidate.review_comment = reason
        session.add(
            GroupingReviewHistory(
                account_id=account_id,
                candidate_id=candidate.id,
                old_status=old_status,
                new_status=new_status,
                actor_user_id=actor_user_id,
                reason=reason,
                created_at=utcnow(),
            )
        )
        await session.flush()
        await session.commit()
        return self._candidate_payload(candidate)

    async def health(self, session: AsyncSession, *, account_id: int) -> dict[str, Any]:
        latest_run = await self._latest_run(session, account_id=account_id)
        if latest_run is None:
            eligible = int(
                (
                    await session.execute(
                        select(func.count(func.distinct(WBProductCard.nm_id))).where(
                            WBProductCard.account_id == account_id
                        )
                    )
                ).scalar()
                or 0
            )
            return {
                "status": "empty" if eligible else "disabled",
                "enabled": bool(eligible),
                "configured": True,
                "message": "local grouping beta has no runs yet"
                if eligible
                else "no finance product cards for local grouping beta",
                "eligible_products": eligible,
            }
        return {
            "status": "beta" if latest_run.candidate_groups else "empty",
            "enabled": True,
            "configured": True,
            "message": "local grouping beta uses Finance product cards",
            "eligible_products": latest_run.eligible_products,
            "unique_products_analyzed": latest_run.products_processed,
            "last_run_id": latest_run.id,
            "last_success_at": latest_run.finished_at,
            "candidate_groups": latest_run.candidate_groups,
        }

    async def _get_or_create_settings(
        self, session: AsyncSession, *, account_id: int
    ) -> GroupingSettings:
        row = (
            (
                await session.execute(
                    select(GroupingSettings)
                    .where(GroupingSettings.account_id == account_id)
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if row is not None:
            return row
        row = GroupingSettings(account_id=account_id)
        session.add(row)
        await session.flush()
        return row

    async def _load_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int | None,
    ) -> list[NormalizedGroupingProduct]:
        if nm_id is not None:
            seed = (
                (
                    await session.execute(
                        select(WBProductCard)
                        .where(
                            WBProductCard.account_id == account_id,
                            WBProductCard.nm_id == nm_id,
                        )
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if seed is None:
                return []
            brand = self._normalize_text(seed.brand)
            subject = self._normalize_text(seed.subject_name)
            article_base = self._article_base(seed.vendor_code)
            stmt = select(WBProductCard).where(WBProductCard.account_id == account_id)
            if brand:
                stmt = stmt.where(func.lower(WBProductCard.brand) == brand)
            if subject:
                stmt = stmt.where(func.lower(WBProductCard.subject_name) == subject)
            if article_base:
                stmt = stmt.where(WBProductCard.vendor_code.ilike(f"{article_base}%"))
        else:
            stmt = select(WBProductCard).where(WBProductCard.account_id == account_id)
        cards = list(
            (
                await session.execute(
                    stmt.order_by(WBProductCard.nm_id.asc()).limit(
                        self.MAX_PRODUCTS_PER_RUN
                    )
                )
            ).scalars()
        )
        if not cards:
            return []
        card_ids = [card.id for card in cards]
        chars_by_card: dict[int, list[WBProductCardCharacteristic]] = {}
        for row in (
            await session.execute(
                select(WBProductCardCharacteristic).where(
                    WBProductCardCharacteristic.product_card_id.in_(card_ids)
                )
            )
        ).scalars():
            chars_by_card.setdefault(row.product_card_id, []).append(row)
        sizes_by_card: dict[int, list[WBProductCardSize]] = {}
        for row in (
            await session.execute(
                select(WBProductCardSize).where(
                    WBProductCardSize.product_card_id.in_(card_ids)
                )
            )
        ).scalars():
            sizes_by_card.setdefault(row.product_card_id, []).append(row)
        return [
            self._normalize_product(
                card, chars_by_card.get(card.id, []), sizes_by_card.get(card.id, [])
            )
            for card in cards
            if card.nm_id is not None
        ]

    def _normalize_product(
        self,
        card: WBProductCard,
        characteristics: list[WBProductCardCharacteristic],
        sizes: list[WBProductCardSize],
    ) -> NormalizedGroupingProduct:
        char_payload = [
            {"name": row.name, "value": row.value, "char_id": row.char_id}
            for row in characteristics
        ]
        size_payload = [
            {
                "size_id": row.size_id,
                "chrt_id": row.chrt_id,
                "tech_size": row.tech_size,
                "skus": row.skus or [],
            }
            for row in sizes
        ]
        barcodes = sorted(
            {
                str(sku).strip()
                for row in sizes
                for sku in (row.skus or [])
                if str(sku).strip()
            }
        )
        color = self._extract_color(char_payload)
        article_core = self._normalize_article(card.vendor_code)
        article_base = self._article_base(card.vendor_code, color=color)
        media_summary = {
            "photo_count": len(card.photos) if isinstance(card.photos, list) else 0,
            "has_video": bool(card.video),
        }
        source_revision = self._hash_payload(
            {
                "nm_id": card.nm_id,
                "imt_id": card.imt_id,
                "vendor_code": card.vendor_code,
                "title": card.title,
                "brand": card.brand,
                "subject_name": card.subject_name,
                "characteristics": char_payload,
                "sizes": size_payload,
                "photos": card.photos,
                "video": card.video,
                "updated_at_wb": card.updated_at_wb.isoformat()
                if card.updated_at_wb
                else None,
            }
        )
        return NormalizedGroupingProduct(
            account_id=card.account_id,
            nm_id=card.nm_id,
            imt_id=card.imt_id,
            vendor_code=card.vendor_code,
            article_core=article_core,
            article_base_core=article_base,
            title=self._clean(card.title),
            brand=self._clean(card.brand),
            subject_name=self._clean(card.subject_name),
            color_normalized=color,
            characteristics=char_payload,
            sizes=size_payload,
            barcodes=barcodes,
            media_summary=media_summary,
            stock_summary={},
            finance_summary={},
            source_revision=source_revision,
        )

    def _build_candidates(
        self,
        products: list[NormalizedGroupingProduct],
        *,
        account_id: int,
        run_id: int,
        scenario: str,
        settings: GroupingSettings | EffectiveGroupingSettings,
    ) -> list[GroupingCandidate]:
        now = utcnow()
        buckets: dict[tuple[str, str, str, str], list[NormalizedGroupingProduct]] = {}
        for product in products:
            brand = self._normalize_text(product.brand)
            subject = self._normalize_text(product.subject_name)
            if not brand or not subject:
                continue
            if scenario == "imt_id_validation" and product.imt_id:
                key = ("imt_id", brand, subject, str(product.imt_id))
            else:
                base = product.article_base_core
                if not base:
                    continue
                key = ("article_base", brand, subject, base)
            buckets.setdefault(key, []).append(product)

        candidates: list[GroupingCandidate] = []
        for key, members in buckets.items():
            if len(members) < 2:
                continue
            members = sorted(members, key=lambda item: item.nm_id)
            conflicts = self._conflicts(members, settings=settings)
            risk_score = self._risk_score(members, conflicts)
            if risk_score > float(settings.maximum_risk):
                continue
            risk_level = self._risk_level(risk_score, conflicts)
            if risk_level == "blocked":
                continue
            confidence = self._confidence(members, key=key, conflicts=conflicts)
            if confidence < float(settings.minimum_confidence):
                continue
            member_nm_ids = [item.nm_id for item in members]
            fingerprint = self._hash_payload(
                {"scenario": scenario, "members": member_nm_ids, "key": key}
            )
            candidate_key = ":".join(key)
            candidates.append(
                GroupingCandidate(
                    account_id=account_id,
                    run_id=run_id,
                    candidate_key=candidate_key,
                    anchor_nm_id=member_nm_ids[0],
                    member_nm_ids_json=member_nm_ids,
                    scenario=scenario,
                    candidate_type=key[0],
                    confidence=round(confidence, 4),
                    risk_level=risk_level,
                    risk_score=round(risk_score, 4),
                    reasons_json=self._reasons(members, key=key),
                    risk_reasons_json=self._risk_reasons(conflicts),
                    conflicts_json=conflicts,
                    evidence_json=self._evidence(members, key=key),
                    status="new",
                    fingerprint=fingerprint,
                    first_seen_at=now,
                    last_seen_at=now,
                )
            )
            if len(candidates) >= self.MAX_CANDIDATE_GROUPS:
                break
        return candidates

    async def _replace_run_candidates(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        run_id: int,
        candidates: list[GroupingCandidate],
    ) -> tuple[list[GroupingCandidate], int, int]:
        persisted_candidates: list[GroupingCandidate] = []
        created_count = 0
        updated_count = 0
        for candidate in candidates:
            existing = (
                (
                    await session.execute(
                        select(GroupingCandidate).where(
                            GroupingCandidate.account_id == account_id,
                            GroupingCandidate.scenario == candidate.scenario,
                            GroupingCandidate.fingerprint == candidate.fingerprint,
                        )
                    )
                )
                .scalars()
                .first()
            )
            if existing is not None:
                existing.run_id = run_id
                existing.last_seen_at = candidate.last_seen_at
                existing.confidence = candidate.confidence
                existing.risk_level = candidate.risk_level
                existing.risk_score = candidate.risk_score
                existing.reasons_json = candidate.reasons_json
                existing.risk_reasons_json = candidate.risk_reasons_json
                existing.conflicts_json = candidate.conflicts_json
                existing.evidence_json = candidate.evidence_json
                existing.member_nm_ids_json = candidate.member_nm_ids_json
                existing.anchor_nm_id = candidate.anchor_nm_id
                existing.candidate_key = candidate.candidate_key
                if existing.status == "expired":
                    existing.status = "new"
                persisted = existing
                updated_count += 1
            else:
                session.add(candidate)
                await session.flush()
                persisted = candidate
                created_count += 1
            await session.execute(
                delete(GroupingRecommendation).where(
                    GroupingRecommendation.account_id == account_id,
                    GroupingRecommendation.candidate_id == persisted.id,
                )
            )
            session.add(
                GroupingRecommendation(
                    account_id=account_id,
                    candidate_id=persisted.id,
                    recommendation_type="merge_preview",
                    source_nm_id=persisted.anchor_nm_id,
                    target_group_key=persisted.candidate_key,
                    proposed_members_json=persisted.member_nm_ids_json,
                    preview_payload_json=self._preview_payload(persisted),
                    expected_effect_json={
                        "measured": False,
                        "note": "No money effect is claimed by Grouping Beta without a measured model.",
                    },
                    confidence=persisted.confidence,
                    risk_level=persisted.risk_level,
                    status=persisted.status,
                )
            )
            persisted_candidates.append(persisted)
        await session.flush()
        return persisted_candidates, created_count, updated_count

    def _snapshot_from_product(
        self, product: NormalizedGroupingProduct, *, run_id: int
    ) -> GroupingProductSnapshot:
        return GroupingProductSnapshot(
            account_id=product.account_id,
            run_id=run_id,
            nm_id=product.nm_id,
            imt_id=product.imt_id,
            vendor_code=product.vendor_code,
            article_core=product.article_core,
            article_base_core=product.article_base_core,
            title=product.title,
            brand=product.brand,
            subject_name=product.subject_name,
            color_normalized=product.color_normalized,
            characteristics_json=product.characteristics,
            sizes_json=product.sizes,
            barcodes_json=product.barcodes,
            media_summary_json=product.media_summary,
            stock_summary_json=product.stock_summary,
            finance_summary_json=product.finance_summary,
            source_revision=product.source_revision,
            created_at=utcnow(),
        )

    async def _latest_candidates_for_nm(
        self, session: AsyncSession, *, account_id: int, nm_id: int
    ) -> list[GroupingCandidate]:
        latest_run = await self._latest_run(session, account_id=account_id)
        if latest_run is None:
            return []
        rows = list(
            (
                await session.execute(
                    select(GroupingCandidate)
                    .where(
                        GroupingCandidate.account_id == account_id,
                        GroupingCandidate.run_id == latest_run.id,
                        GroupingCandidate.status.in_(
                            ("new", "reviewing", "accepted", "postponed")
                        ),
                    )
                    .order_by(
                        GroupingCandidate.confidence.desc(), GroupingCandidate.id.desc()
                    )
                )
            ).scalars()
        )
        return [
            row
            for row in rows
            if int(nm_id) in [int(item) for item in (row.member_nm_ids_json or [])]
        ]

    async def _latest_source_for_nm(
        self, session: AsyncSession, *, account_id: int, nm_id: int
    ) -> dict[str, Any] | None:
        row = (
            (
                await session.execute(
                    select(GroupingProductSnapshot)
                    .where(
                        GroupingProductSnapshot.account_id == account_id,
                        GroupingProductSnapshot.nm_id == nm_id,
                    )
                    .order_by(GroupingProductSnapshot.id.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            return None
        return {
            "nm_id": row.nm_id,
            "article": row.vendor_code,
            "brand": row.brand,
            "subject": row.subject_name,
            "color": row.color_normalized,
        }

    async def _latest_run(
        self, session: AsyncSession, *, account_id: int
    ) -> GroupingRun | None:
        return (
            (
                await session.execute(
                    select(GroupingRun)
                    .where(
                        GroupingRun.account_id == account_id,
                        GroupingRun.status.in_(("completed", "partial")),
                    )
                    .order_by(
                        GroupingRun.finished_at.desc().nullslast(),
                        GroupingRun.id.desc(),
                    )
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    def _candidate_payload(self, candidate: GroupingCandidate) -> dict[str, Any]:
        nm_ids = [int(item) for item in (candidate.member_nm_ids_json or [])]
        return {
            "candidate_id": candidate.id,
            "candidate_group_id": str(candidate.id),
            "candidate_key": candidate.candidate_key,
            "scenario": candidate.scenario,
            "candidate_type": candidate.candidate_type,
            "nm_ids": nm_ids,
            "anchor_nm_id": candidate.anchor_nm_id,
            "confidence": float(candidate.confidence),
            "risk_level": candidate.risk_level,
            "risk_score": float(candidate.risk_score),
            "reasons": list(candidate.reasons_json or []),
            "risk_reasons": list(candidate.risk_reasons_json or []),
            "conflicts": list(candidate.conflicts_json or []),
            "evidence": dict(candidate.evidence_json or {}),
            "status": candidate.status,
            "preview_payload_available": True,
            "preview_payload": self._preview_payload(candidate),
            "expected_effect_note": "Review-only beta recommendation. No measured money effect is claimed.",
            "auto_merge_enabled": False,
            "review_needed": candidate.risk_level in {"medium", "high"},
        }

    def _preview_payload(self, candidate: GroupingCandidate) -> dict[str, Any]:
        return {
            "operation": "merge_preview",
            "enabled": False,
            "auto_merge_enabled": False,
            "blocked_submit_reason": "Grouping Beta is recommendation-only in Finance MVP.",
            "candidate_id": candidate.id,
            "source_nm_id": candidate.anchor_nm_id,
            "proposed_member_nm_ids": [
                int(item) for item in (candidate.member_nm_ids_json or [])
            ],
            "risk_level": candidate.risk_level,
            "risk_reasons": list(candidate.risk_reasons_json or []),
        }

    def _action_from_candidate(self, candidate: GroupingCandidate) -> PortalActionRead:
        severity = (
            candidate.risk_level
            if candidate.risk_level in {"high", "medium", "low"}
            else "medium"
        )
        return PortalActionRead(
            id=f"grouping-local:{candidate.id}",
            action_id=None,
            source="grouping_beta",
            source_module="grouping",
            source_id=str(candidate.id),
            account_id=candidate.account_id,
            nm_id=candidate.anchor_nm_id,
            action_type="GROUPING_RECOMMENDATION",
            title="Проверить Beta-рекомендацию группировки",
            priority="P4",
            severity=severity,
            confidence="high" if float(candidate.confidence) >= 0.8 else "medium",
            status=(
                "in_progress"
                if candidate.status == "reviewing"
                else "done"
                if candidate.status == "accepted"
                else "ignored"
                if candidate.status == "rejected"
                else candidate.status
                if candidate.status in {"new", "postponed"}
                else "new"
            ),
            reason="Local Grouping Beta found a safe review-only card family candidate.",
            next_step="Open grouping preview and accept, reject, or postpone locally",
            can_update_status=True,
            can_update=True,
            can_execute=False,
            payload=self._candidate_payload(candidate),
            raw={"mode": "local", "auto_merge_enabled": False},
        )

    def _filter_candidates_for_nm(
        self, candidates: list[GroupingCandidate], *, nm_id: int | None
    ) -> list[GroupingCandidate]:
        if nm_id is None:
            return candidates
        return [
            candidate
            for candidate in candidates
            if int(nm_id) in [int(item) for item in candidate.member_nm_ids_json or []]
        ]

    def _settings_snapshot(
        self,
        settings: GroupingSettings | EffectiveGroupingSettings,
        *,
        custom_config: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "mode": settings.mode,
            "default_scenario": settings.default_scenario,
            "minimum_confidence": float(settings.minimum_confidence),
            "maximum_risk": float(settings.maximum_risk),
            "allow_cross_brand": settings.allow_cross_brand,
            "allow_cross_subject": settings.allow_cross_subject,
            "require_identity_evidence": settings.require_identity_evidence,
            "custom_config": custom_config or {},
        }

    def _effective_settings(
        self,
        settings: GroupingSettings,
        *,
        custom_config: dict[str, Any],
    ) -> EffectiveGroupingSettings:
        recommendation_config = {}
        if isinstance(custom_config, dict) and isinstance(
            custom_config.get("recommendation_config"), dict
        ):
            recommendation_config = dict(custom_config["recommendation_config"])

        minimum_confidence = self._bounded_float(
            recommendation_config.get("minimum_confidence"),
            default=float(settings.minimum_confidence),
            min_value=0.0,
            max_value=1.0,
        )
        maximum_risk = self._bounded_float(
            recommendation_config.get("maximum_risk"),
            default=float(settings.maximum_risk),
            min_value=0.0,
            max_value=1.0,
        )
        same_brand_required = recommendation_config.get("same_brand_required")
        same_subject_required = recommendation_config.get("same_subject_required")
        return EffectiveGroupingSettings(
            mode=settings.mode,
            default_scenario=settings.default_scenario,
            minimum_confidence=minimum_confidence,
            maximum_risk=maximum_risk,
            allow_cross_brand=settings.allow_cross_brand
            if same_brand_required is None
            else not bool(same_brand_required),
            allow_cross_subject=settings.allow_cross_subject
            if same_subject_required is None
            else not bool(same_subject_required),
            require_identity_evidence=bool(settings.require_identity_evidence),
        )

    def _bounded_float(
        self, value: Any, *, default: float, min_value: float, max_value: float
    ) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        return max(min_value, min(max_value, parsed))

    def _scenario(
        self, *, preset_key: str | None, custom_config: dict[str, Any]
    ) -> str:
        explicit = (
            str((custom_config or {}).get("scenario") or preset_key or "")
            .strip()
            .lower()
        )
        if explicit in {"imt", "imt_id", "imt_id_validation"}:
            return "imt_id_validation"
        if explicit in {"variant", "variant_candidate"}:
            return "variant_candidate"
        if explicit in {"duplicate", "duplicate_candidate"}:
            return "duplicate_candidate"
        return "article_family"

    def _conflicts(
        self,
        members: list[NormalizedGroupingProduct],
        *,
        settings: GroupingSettings | EffectiveGroupingSettings,
    ) -> list[str]:
        conflicts: list[str] = []
        brands = {
            self._normalize_text(item.brand)
            for item in members
            if self._normalize_text(item.brand)
        }
        subjects = {
            self._normalize_text(item.subject_name)
            for item in members
            if self._normalize_text(item.subject_name)
        }
        if len(brands) > 1 and not settings.allow_cross_brand:
            conflicts.append("different_brand")
        if len(subjects) > 1 and not settings.allow_cross_subject:
            conflicts.append("different_subject")
        article_bases = {
            item.article_base_core for item in members if item.article_base_core
        }
        if len(article_bases) > 1:
            conflicts.append("conflicting_article_family")
        if (
            settings.require_identity_evidence
            and not article_bases
            and not any(item.imt_id for item in members)
        ):
            conflicts.append("missing_identity_evidence")
        return conflicts

    def _risk_score(
        self, members: list[NormalizedGroupingProduct], conflicts: list[str]
    ) -> float:
        score = 0.1
        score += min(0.4, len(conflicts) * 0.25)
        if any(item.color_normalized is None for item in members):
            score += 0.1
        if len({item.imt_id for item in members if item.imt_id}) > 1:
            score += 0.15
        return min(score, 1.0)

    def _risk_level(self, risk_score: float, conflicts: list[str]) -> str:
        if any(
            item in conflicts
            for item in {
                "different_brand",
                "different_subject",
                "conflicting_article_family",
                "missing_identity_evidence",
            }
        ):
            return "blocked"
        if risk_score >= 0.65:
            return "high"
        if risk_score >= 0.35:
            return "medium"
        return "low"

    def _confidence(
        self,
        members: list[NormalizedGroupingProduct],
        *,
        key: tuple[str, str, str, str],
        conflicts: list[str],
    ) -> float:
        confidence = 0.55
        if key[0] == "article_base":
            confidence += 0.25
        if key[0] == "imt_id":
            confidence += 0.2
        if len({item.brand for item in members}) == 1:
            confidence += 0.08
        if len({item.subject_name for item in members}) == 1:
            confidence += 0.08
        confidence -= len(conflicts) * 0.2
        return max(0, min(confidence, 0.98))

    def _reasons(
        self,
        members: list[NormalizedGroupingProduct],
        *,
        key: tuple[str, str, str, str],
    ) -> list[str]:
        reasons = ["same_brand", "same_subject"]
        if key[0] == "article_base":
            reasons.append("same_article_base_core")
        if key[0] == "imt_id":
            reasons.append("same_existing_imt_id")
        colors = sorted(
            {item.color_normalized for item in members if item.color_normalized}
        )
        if len(colors) > 1:
            reasons.append("variant_color_evidence")
        return reasons

    def _risk_reasons(self, conflicts: list[str]) -> list[str]:
        if not conflicts:
            return []
        return [f"blocked_by_{item}" for item in conflicts]

    def _evidence(
        self,
        members: list[NormalizedGroupingProduct],
        *,
        key: tuple[str, str, str, str],
    ) -> dict[str, Any]:
        return {
            "source_module": "finance",
            "source_type": "product_cards",
            "blocking_key": {
                "type": key[0],
                "brand": key[1],
                "subject": key[2],
                "identity": key[3],
            },
            "member_count": len(members),
            "member_nm_ids": [item.nm_id for item in members],
            "article_base_cores": sorted(
                {item.article_base_core for item in members if item.article_base_core}
            ),
            "imt_ids": sorted({item.imt_id for item in members if item.imt_id}),
            "colors": sorted(
                {item.color_normalized for item in members if item.color_normalized}
            ),
        }

    def _extract_color(self, characteristics: list[dict[str, Any]]) -> str | None:
        for row in characteristics:
            name = self._normalize_text(row.get("name"))
            if name not in {"цвет", "color", "colors"}:
                continue
            value = row.get("value")
            if isinstance(value, list) and value:
                return self._normalize_text(value[0])
            if isinstance(value, str):
                return self._normalize_text(value)
        return None

    def _normalize_article(self, value: str | None) -> str | None:
        cleaned = self._clean(value)
        return cleaned.upper() if cleaned else None

    def _article_base(
        self, value: str | None, *, color: str | None = None
    ) -> str | None:
        article = self._normalize_article(value)
        if not article:
            return None
        if color and article.lower().endswith(color.lower()):
            article = article[: -len(color)].strip()
        match = re.match(
            r"^([A-ZА-ЯЁ]+[\s_-]*\d+(?:-\d+)?)", article, flags=re.IGNORECASE
        )
        if match:
            return re.sub(r"\s+", " ", match.group(1).replace("_", " ").strip()).upper()
        tokens = re.split(r"[\s_/.-]+", article)
        return " ".join(tokens[:2]).strip().upper() if tokens else article

    def _normalize_text(self, value: Any) -> str:
        return (self._clean(value) or "").lower()

    def _clean(self, value: Any) -> str | None:
        text = unicodedata.normalize("NFKC", str(value or "")).strip()
        text = re.sub(r"\s+", " ", text)
        return text or None

    def _hash_payload(self, payload: Any) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()
