from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.action_registry import (
    RULE_BUILDER_KNOWN_ACTIONS,
    RULE_BUILDER_PRICE_PROMO_ADS_ACTIONS,
    canonical_registry_items,
    dangerous_action_codes,
    disallowed_rule_builder_actions,
    get_action,
    unknown_action_codes,
)
from app.models.accounts import WBAccount
from app.models.problem_engine import (
    AdminRuleTestRun,
    MetricCatalog,
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleAdminAudit,
    ProblemRuleVersion,
)
from app.schemas.problem_engine import (
    AdminFormulaValidationDiagnostic,
    AdminProblemDefinitionCreate,
    AdminProblemDefinitionUpdate,
    AdminProblemRuleVersionCreate,
    AdminProblemRuleVersionUpdate,
    AdminRuleBacktestRequest,
    AdminRuleBacktestHistoryItem,
    AdminRuleBacktestHistoryPage,
    AdminRuleBacktestResponse,
    AdminRulePublishBlocker,
    AdminRulePublishRequest,
    AdminRuleValidationRequest,
    AdminRuleValidationResponse,
    ProblemDefinitionRead,
    ProblemDefinitionWithVersionsRead,
    ProblemRuleActionCatalogItem,
    ProblemRuleActionCatalogResponse,
    ProblemRuleInstancesPage,
    ProblemRuleSummaryDefinition,
    ProblemRuleSummaryResponse,
    ProblemRuleAdminAuditPage,
    ProblemRuleInstanceItem,
    ProblemRuleVersionCompareResponse,
    ProblemRuleVersionRead,
)
from app.schemas.portal import normalize_action_center_allowed_actions
from app.services.problem_engine.evaluator import ProblemEvaluatorService
from app.services.problem_engine.formula_evaluator import FormulaEvaluator
from app.services.problem_engine.metric_catalog import MetricCatalogService


ALLOWED_RULE_ACTIONS = RULE_BUILDER_KNOWN_ACTIONS

PRIMARY_SAFE_ACTIONS = frozenset(
    {
        "classify_expense",
        "map_sku",
        "open_ads_dashboard",
        "open_data_fix",
        "open_price_review",
        "open_promo_planner",
        "open_supply_planner",
        "run_checker",
        "upload_cost",
    }
)
SOLVE_STEP_STATUSES = frozenset(
    {"ready", "available", "blocked", "waiting_for_data", "done"}
)
MUTABLE_DEFINITION_STATUSES = {"draft", "paused"}
MUTABLE_RULE_STATUSES = {"draft", "testing", "paused"}
PRICE_SAFETY_METRICS = frozenset(
    {
        "cost_price",
        "margin_pct",
        "min_safe_price",
        "price_after_discount",
        "price_current",
        "safe_price",
        "target_margin_pct",
    }
)
DANGEROUS_DIRECT_ACTIONS = frozenset(
    action_code
    for action_code in ALLOWED_RULE_ACTIONS
    if (entry := get_action(action_code)) is not None and entry.is_dangerous
)
PRICE_OR_PROMO_ACTIONS = RULE_BUILDER_PRICE_PROMO_ADS_ACTIONS
PUBLISH_BLOCKER_KEYS = (
    "invalid_formula",
    "unknown_metric_or_operator",
    "no_evidence",
    "no_backtest",
    "dangerous_action",
    "price_promo_missing_safety",
    "too_many_matches",
    "test_only_visibility_conflict",
    "high_missing_metric_rate",
    "no_recheck_rule",
    "no_allowed_action",
    "seller_preview_missing",
)
WIDE_MATCH_MIN_EVALUATED = 20
WIDE_MATCH_RATIO = 0.5


class ProblemRuleAdminService:
    def __init__(
        self,
        *,
        metric_catalog: MetricCatalogService | None = None,
        formula_evaluator: FormulaEvaluator | None = None,
        evaluator: ProblemEvaluatorService | None = None,
    ) -> None:
        self.metric_catalog = metric_catalog or MetricCatalogService()
        self.formula_evaluator = formula_evaluator or FormulaEvaluator()
        self.evaluator = evaluator or ProblemEvaluatorService(
            metric_catalog=self.metric_catalog, formula_evaluator=self.formula_evaluator
        )

    async def list_metrics(self, session: AsyncSession) -> list[MetricCatalog]:
        return await self.metric_catalog.list_metrics(
            session, admin_visible_only=True, include_deprecated=False
        )

    async def action_catalog(self) -> ProblemRuleActionCatalogResponse:
        items = [
            self._action_catalog_item(entry.action_code)
            for entry in canonical_registry_items()
        ]
        return ProblemRuleActionCatalogResponse(items=items)

    async def compare_versions_capability(
        self,
        session: AsyncSession,
        *,
        definition_id: int,
        left: int | None,
        right: int | None,
    ) -> ProblemRuleVersionCompareResponse:
        await self._definition_or_404(session, definition_id)
        return ProblemRuleVersionCompareResponse(
            definition_id=definition_id,
            left=left,
            right=right,
            compare_available=False,
            disabled_reason="Сравнение версий будет доступно позже.",
        )

    async def list_definitions(
        self,
        session: AsyncSession,
        *,
        status_filter: str | None = None,
        category: str | None = None,
        entity_type: str | None = None,
    ) -> list[ProblemDefinitionRead]:
        stmt = select(ProblemDefinition)
        if status_filter:
            stmt = stmt.where(ProblemDefinition.status == status_filter)
        if category:
            stmt = stmt.where(ProblemDefinition.category == category)
        if entity_type:
            stmt = stmt.where(ProblemDefinition.entity_type == entity_type)
        stmt = stmt.order_by(ProblemDefinition.problem_code.asc())
        definitions = list((await session.execute(stmt)).scalars())
        rates = await self._rates_by_definition_ids(
            session, [definition.id for definition in definitions]
        )
        return [
            self._definition_read(definition, rates=rates.get(definition.id))
            for definition in definitions
        ]

    async def create_definition(
        self,
        session: AsyncSession,
        payload: AdminProblemDefinitionCreate,
        *,
        actor_user_id: int | None,
    ) -> ProblemDefinition:
        self._validate_actions(payload.allowed_actions_json)
        existing = (
            await session.execute(
                select(ProblemDefinition).where(
                    ProblemDefinition.problem_code == payload.problem_code
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Problem definition code already exists",
            )
        definition = ProblemDefinition(
            **payload.model_dump(),
            status="draft",
            created_by_user_id=actor_user_id,
        )
        session.add(definition)
        await session.flush()
        self._audit(
            session,
            object_type="definition",
            object_id=definition.id,
            event_type="created",
            old_value=None,
            new_value=self._definition_snapshot(definition),
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return definition

    async def get_definition(
        self, session: AsyncSession, definition_id: int
    ) -> ProblemDefinitionWithVersionsRead:
        definition = await self._definition_or_404(session, definition_id)
        versions = await self._versions_for_definition(
            session, definition_id=definition.id
        )
        version_ids = [version.id for version in versions]
        definition_rates = await self._rates_by_definition_ids(session, [definition.id])
        version_rates = await self._rates_by_rule_ids(session, version_ids)
        audit_stmt = (
            select(ProblemRuleAdminAudit)
            .where(
                or_(
                    and_(
                        ProblemRuleAdminAudit.object_type == "definition",
                        ProblemRuleAdminAudit.object_id == definition.id,
                    ),
                    and_(
                        ProblemRuleAdminAudit.object_type == "rule_version",
                        ProblemRuleAdminAudit.object_id.in_(version_ids or [-1]),
                    ),
                )
            )
            .order_by(
                ProblemRuleAdminAudit.created_at.desc(), ProblemRuleAdminAudit.id.desc()
            )
        )
        audits = list((await session.execute(audit_stmt)).scalars())
        return ProblemDefinitionWithVersionsRead.model_validate(
            {
                **self._definition_read(
                    definition, rates=definition_rates.get(definition.id)
                ).model_dump(),
                "created_at": definition.created_at,
                "updated_at": definition.updated_at,
                "versions": [
                    self._rule_read(version, rates=version_rates.get(version.id))
                    for version in versions
                ],
                "audit": audits,
            }
        )

    async def update_definition(
        self,
        session: AsyncSession,
        definition_id: int,
        payload: AdminProblemDefinitionUpdate,
        *,
        actor_user_id: int | None,
    ) -> ProblemDefinition:
        definition = await self._definition_or_404(session, definition_id)
        if definition.status not in MUTABLE_DEFINITION_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only draft or paused problem definitions can be edited",
            )
        update_data = payload.model_dump(exclude_unset=True)
        if (
            "allowed_actions_json" in update_data
            and update_data["allowed_actions_json"] is not None
        ):
            self._validate_actions(update_data["allowed_actions_json"])
        old = self._definition_snapshot(definition)
        for key, value in update_data.items():
            setattr(definition, key, value)
        await session.flush()
        self._audit(
            session,
            object_type="definition",
            object_id=definition.id,
            event_type="updated",
            old_value=old,
            new_value=self._definition_snapshot(definition),
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return definition

    async def create_version(
        self,
        session: AsyncSession,
        definition_id: int,
        payload: AdminProblemRuleVersionCreate,
        *,
        actor_user_id: int | None,
    ) -> ProblemRuleVersion:
        definition = await self._definition_or_404(session, definition_id)
        if definition.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Archived definitions cannot receive new versions",
            )
        await self._ensure_formulas_valid_for_save(session, payload)
        next_version = (
            int(
                (
                    await session.execute(
                        select(
                            func.coalesce(func.max(ProblemRuleVersion.version), 0)
                        ).where(
                            ProblemRuleVersion.problem_definition_id == definition.id
                        )
                    )
                ).scalar_one()
            )
            + 1
        )
        rule = ProblemRuleVersion(
            problem_definition_id=definition.id,
            version=next_version,
            status="draft",
            evaluation_grain=payload.evaluation_grain,
            lookback_days=payload.lookback_days,
            condition_json=payload.condition_json,
            impact_formula_json=payload.impact_formula_json,
            severity_formula_json=payload.severity_formula_json,
            confidence_formula_json=payload.confidence_formula_json,
            dedup_key_template=payload.dedup_key_template,
            recheck_rule_json=payload.recheck_rule_json,
            evidence_template_json=payload.evidence_template_json,
            test_only=payload.test_only,
            seller_visible=payload.seller_visible,
            visibility_mode=payload.visibility_mode,
            created_by_user_id=actor_user_id,
        )
        session.add(rule)
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=rule.id,
            event_type="created",
            old_value=None,
            new_value=self._rule_snapshot(rule),
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return rule

    async def update_version(
        self,
        session: AsyncSession,
        version_id: int,
        payload: AdminProblemRuleVersionUpdate,
        *,
        actor_user_id: int | None,
    ) -> ProblemRuleVersion:
        rule, definition = await self._rule_and_definition_or_404(session, version_id)
        update_data = payload.model_dump(exclude_unset=True)
        if not update_data:
            return rule
        if rule.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Archived rule versions cannot be edited",
            )
        if rule.status == "active":
            draft = await self._copy_rule_as_draft(
                session,
                definition=definition,
                source_rule=rule,
                update_data=update_data,
                actor_user_id=actor_user_id,
            )
            self._audit(
                session,
                object_type="rule_version",
                object_id=rule.id,
                event_type="active_edit_created_draft",
                old_value=self._rule_snapshot(rule),
                new_value={
                    "draft_rule_version_id": draft.id,
                    "draft_version": draft.version,
                    "changes": update_data,
                },
                actor_user_id=actor_user_id,
            )
            await session.flush()
            return draft
        if rule.status not in MUTABLE_RULE_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only draft, testing, or paused rule versions can be edited",
            )
        old = self._rule_snapshot(rule)
        final_values = {
            "evaluation_grain": rule.evaluation_grain,
            "lookback_days": rule.lookback_days,
            "condition_json": rule.condition_json,
            "impact_formula_json": rule.impact_formula_json,
            "severity_formula_json": rule.severity_formula_json,
            "confidence_formula_json": rule.confidence_formula_json,
            "dedup_key_template": rule.dedup_key_template,
            "recheck_rule_json": rule.recheck_rule_json,
            "evidence_template_json": rule.evidence_template_json,
            **update_data,
        }
        await self._ensure_rule_values_valid(session, final_values)
        for key, value in update_data.items():
            setattr(rule, key, value)
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=rule.id,
            event_type="updated",
            old_value=old,
            new_value=self._rule_snapshot(rule),
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return rule

    async def validate_version(
        self,
        session: AsyncSession,
        version_id: int,
        payload: AdminRuleValidationRequest | None = None,
    ) -> AdminRuleValidationResponse:
        rule, _definition = await self._rule_and_definition_or_404(session, version_id)
        return await self._validate_rule_payload(session, rule=rule, payload=payload)

    async def backtest(
        self,
        session: AsyncSession,
        version_id: int,
        payload: AdminRuleBacktestRequest,
        *,
        actor_user_id: int | None,
    ) -> AdminRuleBacktestResponse:
        if payload.date_from > payload.date_to:
            raise HTTPException(
                status_code=422, detail="date_from must be before or equal to date_to"
            )
        account = await session.get(WBAccount, payload.account_id)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Account not found"
            )
        rule, definition = await self._rule_and_definition_or_404(session, version_id)
        validation = await self._validate_rule_payload(session, rule=rule, payload=None)
        if not validation.valid:
            raise HTTPException(status_code=422, detail=jsonable_encoder(validation))
        result = await self.evaluator.evaluate_rule_version(
            session,
            definition=definition,
            rule=rule,
            account_id=payload.account_id,
            nm_id=payload.nm_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            test_mode=True,
        )
        matched_previews = [preview for preview in result.previews if preview.matched]
        sample_issues = [
            preview.model_dump() for preview in matched_previews[: payload.sample_limit]
        ]
        total_impact = self._total_impact(matched_previews)
        warnings = self._dedupe(
            [
                *result.warnings,
                *[
                    warning
                    for preview in result.previews
                    for warning in preview.warnings
                ],
            ]
        )
        if result.evaluated_count == 0:
            warnings.append(
                "No eligible product entities were found for this backtest window."
            )
        missing_metric_stats = self._missing_metric_stats(result.previews)
        total_expected_impact = self._total_expected_impact(matched_previews)
        sample_evidence = self._sample_evidence(sample_issues)
        seller_preview_payload = self._seller_preview_payload(
            definition=definition,
            rule=rule,
            matched_count=result.matched_count,
            evaluated_count=result.evaluated_count,
            sample_issues=sample_issues,
            total_expected_impact=total_expected_impact,
            missing_metric_stats=missing_metric_stats,
            warnings=warnings,
        )
        test_run = AdminRuleTestRun(
            rule_version_id=rule.id,
            account_id=payload.account_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            matched_count=result.matched_count,
            sample_issues_json=sample_issues,
            total_impact_amount=total_impact,
            warnings_json=warnings,
            created_by_user_id=actor_user_id,
        )
        session.add(test_run)
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=rule.id,
            event_type="backtested",
            old_value=None,
            new_value={
                "account_id": payload.account_id,
                "date_from": payload.date_from,
                "date_to": payload.date_to,
                "matched_count": result.matched_count,
                "evaluated_count": result.evaluated_count,
                "missing_metric_stats": missing_metric_stats,
                "sample_issue_count": len(sample_issues),
                "total_expected_impact": total_expected_impact,
                "sample_evidence_count": len(sample_evidence),
                "sample_evidence": sample_evidence,
                "seller_preview_payload": seller_preview_payload,
                "test_run_id": test_run.id,
            },
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return AdminRuleBacktestResponse(
            rule_version_id=rule.id,
            account_id=payload.account_id,
            date_from=payload.date_from,
            date_to=payload.date_to,
            matched_count=result.matched_count,
            evaluated_count=result.evaluated_count,
            sample_issues=sample_issues,
            total_impact_amount=total_impact,
            total_expected_impact=total_expected_impact,
            warnings=warnings,
            missing_metric_stats=missing_metric_stats,
            sample_evidence=sample_evidence,
            seller_preview_payload=seller_preview_payload,
            test_run_id=test_run.id,
        )

    async def publish(
        self,
        session: AsyncSession,
        version_id: int,
        payload: AdminRulePublishRequest,
        *,
        actor_user_id: int | None,
    ) -> ProblemRuleVersion:
        rule, definition = await self._rule_and_definition_or_404(session, version_id)
        if rule.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Archived rule versions cannot be published",
            )
        validation = await self._validate_rule_payload(session, rule=rule, payload=None)
        if not validation.valid:
            key = self._formula_blocker_key(validation)
            self._raise_publish_blocker(
                key,
                "Rule formulas must be valid before publish",
                details={"validation": validation.model_dump()},
            )
        backtest_metadata = await self._latest_backtest_metadata(
            session, rule_id=rule.id
        )
        self._validate_publish_contract(
            definition,
            rule,
            validation=validation,
            backtest_metadata=backtest_metadata,
            publish_request=payload,
        )

        old_rule = self._rule_snapshot(rule)
        old_definition = self._definition_snapshot(definition)
        other_active = list(
            (
                await session.execute(
                    select(ProblemRuleVersion).where(
                        ProblemRuleVersion.problem_definition_id == definition.id,
                        ProblemRuleVersion.id != rule.id,
                        ProblemRuleVersion.status == "active",
                    )
                )
            ).scalars()
        )
        for other in other_active:
            other.status = "archived"
        definition.status = "active"
        rule.status = "active"
        rule.published_by_user_id = actor_user_id
        rule.published_at = datetime.now(UTC)
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=rule.id,
            event_type="published",
            old_value=old_rule,
            new_value={
                **self._rule_snapshot(rule),
                "override": payload.override,
                "override_reason": payload.override_reason,
                "replaced_rule_version_ids": [item.id for item in other_active],
                "archived_rule_version_ids": [item.id for item in other_active],
            },
            actor_user_id=actor_user_id,
        )
        if definition.status != old_definition.get("status"):
            self._audit(
                session,
                object_type="definition",
                object_id=definition.id,
                event_type="activated",
                old_value=old_definition,
                new_value=self._definition_snapshot(definition),
                actor_user_id=actor_user_id,
            )
        await session.flush()
        return rule

    async def list_audit(
        self,
        session: AsyncSession,
        *,
        object_type: str | None = None,
        object_id: int | None = None,
        event_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ProblemRuleAdminAuditPage:
        stmt = select(ProblemRuleAdminAudit)
        count_stmt = select(func.count()).select_from(ProblemRuleAdminAudit)
        if object_type:
            stmt = stmt.where(ProblemRuleAdminAudit.object_type == object_type)
            count_stmt = count_stmt.where(
                ProblemRuleAdminAudit.object_type == object_type
            )
        if object_id is not None:
            stmt = stmt.where(ProblemRuleAdminAudit.object_id == object_id)
            count_stmt = count_stmt.where(ProblemRuleAdminAudit.object_id == object_id)
        if event_type:
            stmt = stmt.where(ProblemRuleAdminAudit.event_type == event_type)
            count_stmt = count_stmt.where(
                ProblemRuleAdminAudit.event_type == event_type
            )
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        rows = list(
            (
                await session.execute(
                    stmt.order_by(
                        ProblemRuleAdminAudit.created_at.desc(),
                        ProblemRuleAdminAudit.id.desc(),
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        return ProblemRuleAdminAuditPage(
            total=total, limit=limit, offset=offset, items=rows
        )

    async def list_backtests(
        self,
        session: AsyncSession,
        *,
        definition_id: int,
        account_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminRuleBacktestHistoryPage:
        definition = await self._definition_or_404(session, definition_id)
        versions = await self._versions_for_definition(
            session, definition_id=definition.id
        )
        version_ids = [version.id for version in versions]
        if not version_ids:
            return AdminRuleBacktestHistoryPage(
                total=0, limit=limit, offset=offset, items=[]
            )

        filters = [AdminRuleTestRun.rule_version_id.in_(version_ids)]
        if account_id is not None:
            filters.append(AdminRuleTestRun.account_id == account_id)
        count_stmt = select(func.count()).select_from(AdminRuleTestRun).where(*filters)
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        runs = list(
            (
                await session.execute(
                    select(AdminRuleTestRun)
                    .where(*filters)
                    .order_by(
                        AdminRuleTestRun.created_at.desc(), AdminRuleTestRun.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        metadata_by_run_id = await self._backtest_metadata_by_run_ids(
            session,
            version_ids=version_ids,
            run_ids=[run.id for run in runs],
        )
        return AdminRuleBacktestHistoryPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                self._backtest_history_item(
                    run, metadata=metadata_by_run_id.get(run.id)
                )
                for run in runs
            ],
        )

    async def list_backtests_for_version(
        self,
        session: AsyncSession,
        *,
        version_id: int,
        account_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> AdminRuleBacktestHistoryPage:
        rule = await session.get(ProblemRuleVersion, version_id)
        if rule is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Problem rule version not found",
            )

        filters = [AdminRuleTestRun.rule_version_id == version_id]
        if account_id is not None:
            filters.append(AdminRuleTestRun.account_id == account_id)
        count_stmt = select(func.count()).select_from(AdminRuleTestRun).where(*filters)
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        runs = list(
            (
                await session.execute(
                    select(AdminRuleTestRun)
                    .where(*filters)
                    .order_by(
                        AdminRuleTestRun.created_at.desc(), AdminRuleTestRun.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        metadata_by_run_id = await self._backtest_metadata_by_run_ids(
            session,
            version_ids=[version_id],
            run_ids=[run.id for run in runs],
        )
        return AdminRuleBacktestHistoryPage(
            total=total,
            limit=limit,
            offset=offset,
            items=[
                self._backtest_history_item(
                    run, metadata=metadata_by_run_id.get(run.id)
                )
                for run in runs
            ],
        )

    async def list_instances(
        self,
        session: AsyncSession,
        *,
        definition_id: int,
        status_filter: str | None = None,
        account_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        problem_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> ProblemRuleInstancesPage:
        definition = await self._definition_or_404(session, definition_id)
        filters: list[Any] = [ProblemInstance.problem_definition_id == definition.id]
        if problem_code:
            filters.append(ProblemInstance.problem_code == problem_code)
        if status_filter:
            filters.append(ProblemInstance.status == status_filter)
        if account_id is not None:
            filters.append(ProblemInstance.account_id == account_id)
        if date_from is not None:
            filters.append(ProblemInstance.last_seen_at >= self._date_start(date_from))
        if date_to is not None:
            filters.append(
                ProblemInstance.last_seen_at
                < self._date_start(date_to + timedelta(days=1))
            )

        total = int(
            (
                await session.execute(
                    select(func.count()).select_from(ProblemInstance).where(*filters)
                )
            ).scalar_one()
            or 0
        )
        dismissed_count = int(
            (
                await session.execute(
                    select(func.count(func.distinct(ProblemInstance.id)))
                    .select_from(ProblemInstance)
                    .join(
                        ProblemInstanceHistory,
                        ProblemInstanceHistory.problem_instance_id
                        == ProblemInstance.id,
                    )
                    .where(*filters, ProblemInstanceHistory.event_type == "dismissed")
                )
            ).scalar_one()
            or 0
        )
        resolved_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ProblemInstance)
                    .where(
                        *filters, ProblemInstance.status.in_(self._resolved_statuses())
                    )
                )
            ).scalar_one()
            or 0
        )
        active_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(ProblemInstance)
                    .where(
                        *filters,
                        ProblemInstance.status.notin_(
                            sorted(self._inactive_statuses())
                        ),
                    )
                )
            ).scalar_one()
            or 0
        )
        items = list(
            (
                await session.execute(
                    select(ProblemInstance)
                    .where(*filters)
                    .order_by(
                        ProblemInstance.last_seen_at.desc(), ProblemInstance.id.desc()
                    )
                    .limit(limit)
                    .offset(offset)
                )
            ).scalars()
        )
        rate = self._rate(dismissed_count, total)
        return ProblemRuleInstancesPage(
            total=total,
            limit=limit,
            offset=offset,
            account_id=account_id,
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to,
            problem_code=problem_code,
            total_instances=total,
            dismissed_count=dismissed_count,
            resolved_count=resolved_count,
            active_count=active_count,
            dismissed_rate=rate,
            false_positive_rate=rate,
            items=[self._instance_item(item) for item in items],
        )

    async def summary(
        self, session: AsyncSession, *, recent_days: int = 30
    ) -> ProblemRuleSummaryResponse:
        recent_days = max(1, min(int(recent_days or 30), 365))
        definitions = list(
            (
                await session.execute(
                    select(ProblemDefinition).order_by(
                        ProblemDefinition.problem_code.asc()
                    )
                )
            ).scalars()
        )
        versions = list((await session.execute(select(ProblemRuleVersion))).scalars())
        definition_ids = [definition.id for definition in definitions]
        rates = await self._rates_by_definition_ids(session, definition_ids)
        instance_counts = await self._counts_by_definition_ids(session, definition_ids)
        active_instance_counts = await self._counts_by_definition_ids(
            session,
            definition_ids,
            exclude_statuses=self._inactive_statuses(),
        )
        resolved_counts = await self._counts_by_definition_ids(
            session,
            definition_ids,
            include_statuses=self._resolved_statuses(),
        )
        dismissed_counts = await self._dismissed_counts_by_definition_ids(
            session, definition_ids
        )
        recent_since = datetime.now(UTC) - timedelta(days=recent_days)
        recent_counts = await self._counts_by_definition_ids(
            session,
            definition_ids,
            recent_since=recent_since,
        )
        recent_created_counts = await self._recent_counts_by_definition_ids(
            session,
            definition_ids,
            timestamp_column=ProblemInstance.first_seen_at,
            recent_since=recent_since,
        )
        recent_resolved_counts = await self._recent_counts_by_definition_ids(
            session,
            definition_ids,
            timestamp_column=ProblemInstance.resolved_at,
            recent_since=recent_since,
        )
        recent_dismissed_counts = await self._recent_dismissed_counts_by_definition_ids(
            session,
            definition_ids,
            recent_since=recent_since,
        )
        versions_by_definition: dict[int, list[ProblemRuleVersion]] = {}
        for version in versions:
            versions_by_definition.setdefault(version.problem_definition_id, []).append(
                version
            )
        definition_summaries: list[ProblemRuleSummaryDefinition] = []
        for definition in definitions:
            definition_versions = versions_by_definition.get(definition.id, [])
            active_version = next(
                (
                    version
                    for version in definition_versions
                    if version.status == "active"
                ),
                None,
            )
            latest_version = max(
                definition_versions, key=lambda version: version.version, default=None
            )
            rate_payload = rates.get(definition.id) or {}
            definition_summaries.append(
                ProblemRuleSummaryDefinition(
                    id=definition.id,
                    problem_code=definition.problem_code,
                    title_template=definition.title_template,
                    category=definition.category,
                    entity_type=definition.entity_type,  # type: ignore[arg-type]
                    status=definition.status,  # type: ignore[arg-type]
                    active_version_id=active_version.id if active_version else None,
                    latest_version_id=latest_version.id if latest_version else None,
                    total_instances=instance_counts.get(definition.id, 0),
                    dismissed_count=dismissed_counts.get(definition.id, 0),
                    resolved_count=resolved_counts.get(definition.id, 0),
                    active_count=active_instance_counts.get(definition.id, 0),
                    generated_instances_count=instance_counts.get(definition.id, 0),
                    active_instances_count=active_instance_counts.get(definition.id, 0),
                    dismissed_instances_count=dismissed_counts.get(definition.id, 0),
                    recent_matches_count=recent_counts.get(definition.id, 0),
                    recent_created_instances=recent_created_counts.get(
                        definition.id, 0
                    ),
                    recent_resolved_instances=recent_resolved_counts.get(
                        definition.id, 0
                    ),
                    recent_dismissed_instances=recent_dismissed_counts.get(
                        definition.id, 0
                    ),
                    false_positive_rate=rate_payload.get("false_positive_rate"),
                    dismissed_rate=rate_payload.get("dismissed_rate"),
                )
            )

        generated_instances_count = sum(instance_counts.values())
        dismissed_instances_count = sum(dismissed_counts.values())
        resolved_count = sum(resolved_counts.values())
        active_count = sum(active_instance_counts.values())
        dismissed_rate = self._rate(
            dismissed_instances_count, generated_instances_count
        )
        version_status_counts = Counter(str(version.status) for version in versions)
        capabilities = {
            "compare_available": False,
            "disabled_reason": "Сравнение версий будет доступно позже.",
        }
        return ProblemRuleSummaryResponse(
            total_definitions=len(definitions),
            active_definitions=sum(
                1 for definition in definitions if definition.status == "active"
            ),
            total_versions=len(versions),
            active_versions=version_status_counts.get("active", 0),
            testing_versions=version_status_counts.get("testing", 0),
            draft_versions=version_status_counts.get("draft", 0),
            paused_versions=version_status_counts.get("paused", 0),
            generated_instances_count=generated_instances_count,
            total_instances=generated_instances_count,
            active_instances_count=active_count,
            active_count=active_count,
            dismissed_instances_count=dismissed_instances_count,
            dismissed_count=dismissed_instances_count,
            resolved_count=resolved_count,
            recent_matches_count=sum(recent_counts.values()),
            recent_created_instances=sum(recent_created_counts.values()),
            recent_resolved_instances=sum(recent_resolved_counts.values()),
            recent_dismissed_instances=sum(recent_dismissed_counts.values()),
            false_positive_rate=dismissed_rate,
            dismissed_rate=dismissed_rate,
            compare_available=False,
            disabled_reason="Сравнение версий будет доступно позже.",
            capabilities=capabilities,
            definitions=definition_summaries,
        )

    async def pause(
        self, session: AsyncSession, version_id: int, *, actor_user_id: int | None
    ) -> ProblemRuleVersion:
        rule, definition = await self._rule_and_definition_or_404(session, version_id)
        if rule.status == "archived":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Archived rule versions cannot be paused",
            )
        old_rule = self._rule_snapshot(rule)
        old_definition = self._definition_snapshot(definition)
        rule.status = "paused"
        await session.flush()
        if not await self._definition_has_active_versions(
            session, definition_id=definition.id
        ):
            definition.status = "paused"
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=rule.id,
            event_type="paused",
            old_value=old_rule,
            new_value=self._rule_snapshot(rule),
            actor_user_id=actor_user_id,
        )
        if definition.status != old_definition.get("status"):
            self._audit(
                session,
                object_type="definition",
                object_id=definition.id,
                event_type="paused",
                old_value=old_definition,
                new_value=self._definition_snapshot(definition),
                actor_user_id=actor_user_id,
            )
        await session.flush()
        return rule

    async def archive(
        self, session: AsyncSession, version_id: int, *, actor_user_id: int | None
    ) -> ProblemRuleVersion:
        rule, definition = await self._rule_and_definition_or_404(session, version_id)
        old_rule = self._rule_snapshot(rule)
        old_definition = self._definition_snapshot(definition)
        rule.status = "archived"
        await session.flush()
        if not await self._definition_has_active_versions(
            session, definition_id=definition.id
        ):
            definition.status = (
                "paused" if definition.status == "active" else definition.status
            )
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=rule.id,
            event_type="archived",
            old_value=old_rule,
            new_value=self._rule_snapshot(rule),
            actor_user_id=actor_user_id,
        )
        if definition.status != old_definition.get("status"):
            self._audit(
                session,
                object_type="definition",
                object_id=definition.id,
                event_type="paused",
                old_value=old_definition,
                new_value=self._definition_snapshot(definition),
                actor_user_id=actor_user_id,
            )
        await session.flush()
        return rule

    async def _definition_or_404(
        self, session: AsyncSession, definition_id: int
    ) -> ProblemDefinition:
        definition = await session.get(ProblemDefinition, definition_id)
        if definition is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Problem definition not found",
            )
        return definition

    async def _rule_and_definition_or_404(
        self,
        session: AsyncSession,
        version_id: int,
    ) -> tuple[ProblemRuleVersion, ProblemDefinition]:
        row = (
            await session.execute(
                select(ProblemRuleVersion, ProblemDefinition)
                .join(
                    ProblemDefinition,
                    ProblemDefinition.id == ProblemRuleVersion.problem_definition_id,
                )
                .where(ProblemRuleVersion.id == version_id)
            )
        ).one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Problem rule version not found",
            )
        return row[0], row[1]

    async def _versions_for_definition(
        self, session: AsyncSession, *, definition_id: int
    ) -> list[ProblemRuleVersion]:
        return list(
            (
                await session.execute(
                    select(ProblemRuleVersion)
                    .where(ProblemRuleVersion.problem_definition_id == definition_id)
                    .order_by(ProblemRuleVersion.version.desc())
                )
            ).scalars()
        )

    async def _copy_rule_as_draft(
        self,
        session: AsyncSession,
        *,
        definition: ProblemDefinition,
        source_rule: ProblemRuleVersion,
        update_data: dict[str, Any],
        actor_user_id: int | None,
    ) -> ProblemRuleVersion:
        next_version = (
            int(
                (
                    await session.execute(
                        select(
                            func.coalesce(func.max(ProblemRuleVersion.version), 0)
                        ).where(
                            ProblemRuleVersion.problem_definition_id == definition.id
                        )
                    )
                ).scalar_one()
            )
            + 1
        )
        values = {
            "evaluation_grain": source_rule.evaluation_grain,
            "lookback_days": source_rule.lookback_days,
            "condition_json": dict(source_rule.condition_json or {}),
            "impact_formula_json": source_rule.impact_formula_json,
            "severity_formula_json": source_rule.severity_formula_json,
            "confidence_formula_json": source_rule.confidence_formula_json,
            "dedup_key_template": source_rule.dedup_key_template,
            "recheck_rule_json": dict(source_rule.recheck_rule_json or {}),
            "evidence_template_json": dict(source_rule.evidence_template_json or {}),
            "test_only": bool(getattr(source_rule, "test_only", False)),
            "seller_visible": bool(getattr(source_rule, "seller_visible", True)),
            "visibility_mode": str(
                getattr(source_rule, "visibility_mode", None) or "seller"
            ),
            **update_data,
        }
        draft = ProblemRuleVersion(
            problem_definition_id=definition.id,
            version=next_version,
            status="draft",
            created_by_user_id=actor_user_id,
            **values,
        )
        await self._ensure_rule_values_valid(session, values)
        session.add(draft)
        await session.flush()
        self._audit(
            session,
            object_type="rule_version",
            object_id=draft.id,
            event_type="created_from_active_edit",
            old_value=self._rule_snapshot(source_rule),
            new_value=self._rule_snapshot(draft),
            actor_user_id=actor_user_id,
        )
        await session.flush()
        return draft

    async def _validate_rule_payload(
        self,
        session: AsyncSession,
        *,
        rule: ProblemRuleVersion,
        payload: AdminRuleValidationRequest | None,
    ) -> AdminRuleValidationResponse:
        formulas = {
            "condition": rule.condition_json,
            "impact": rule.impact_formula_json,
            "severity": rule.severity_formula_json,
            "confidence": rule.confidence_formula_json,
        }
        recheck_rule_json = rule.recheck_rule_json
        if payload is not None:
            override_map = {
                "condition_json": "condition",
                "impact_formula_json": "impact",
                "severity_formula_json": "severity",
                "confidence_formula_json": "confidence",
            }
            for payload_key, formula_key in override_map.items():
                value = getattr(payload, payload_key)
                if value is not None:
                    formulas[formula_key] = value
            if payload.recheck_rule_json is not None:
                recheck_rule_json = payload.recheck_rule_json
        resolved_when = (
            (recheck_rule_json or {}).get("resolved_when")
            if isinstance(recheck_rule_json, dict)
            else None
        )
        if isinstance(resolved_when, dict):
            formulas["resolved_when"] = resolved_when
        return await self._validate_formulas(session, formulas=formulas)

    async def _ensure_formulas_valid_for_save(
        self, session: AsyncSession, payload: AdminProblemRuleVersionCreate
    ) -> None:
        response = await self._validate_formulas(
            session,
            formulas={
                "condition": payload.condition_json,
                "impact": payload.impact_formula_json,
                "severity": payload.severity_formula_json,
                "confidence": payload.confidence_formula_json,
                "resolved_when": (payload.recheck_rule_json or {}).get("resolved_when"),
            },
        )
        if not response.valid:
            raise HTTPException(status_code=422, detail=jsonable_encoder(response))

    async def _ensure_rule_formulas_valid(
        self, session: AsyncSession, rule: ProblemRuleVersion
    ) -> None:
        response = await self._validate_formulas(
            session,
            formulas={
                "condition": rule.condition_json,
                "impact": rule.impact_formula_json,
                "severity": rule.severity_formula_json,
                "confidence": rule.confidence_formula_json,
                "resolved_when": (rule.recheck_rule_json or {}).get("resolved_when"),
            },
        )
        if not response.valid:
            raise HTTPException(status_code=422, detail=jsonable_encoder(response))

    async def _ensure_rule_values_valid(
        self, session: AsyncSession, values: dict[str, Any]
    ) -> None:
        response = await self._validate_formulas(
            session,
            formulas={
                "condition": values.get("condition_json"),
                "impact": values.get("impact_formula_json"),
                "severity": values.get("severity_formula_json"),
                "confidence": values.get("confidence_formula_json"),
                "resolved_when": (values.get("recheck_rule_json") or {}).get(
                    "resolved_when"
                )
                if isinstance(values.get("recheck_rule_json"), dict)
                else None,
            },
        )
        if not response.valid:
            raise HTTPException(status_code=422, detail=jsonable_encoder(response))

    async def _validate_formulas(
        self, session: AsyncSession, *, formulas: dict[str, Any]
    ) -> AdminRuleValidationResponse:
        allowed_metrics = await self.metric_catalog.allowed_metric_codes(session)
        results: dict[str, AdminFormulaValidationDiagnostic] = {}
        warnings: list[str] = []
        required_metrics: set[str] = set()
        for name, expression in formulas.items():
            if expression is None or (
                expression == {} and name in {"severity", "confidence", "resolved_when"}
            ):
                results[name] = AdminFormulaValidationDiagnostic(valid=True)
                continue
            if expression == {} and name in {"condition", "impact"}:
                results[name] = AdminFormulaValidationDiagnostic(
                    valid=False, error=f"{name} formula is required"
                )
                continue
            required_metrics.update(self._collect_metric_codes(expression))
            context = {"allowed_metrics": allowed_metrics}
            if name == "condition" or name == "resolved_when":
                diagnostic = self.formula_evaluator.evaluate_condition(
                    expression, metrics={}, evaluation_context=context
                )
            elif name == "impact":
                diagnostic = self.formula_evaluator.evaluate_numeric(
                    expression, metrics={}, evaluation_context=context
                )
            else:
                diagnostic = self.formula_evaluator.evaluate(
                    expression, metrics={}, evaluation_context=context
                )
            results[name] = AdminFormulaValidationDiagnostic(
                valid=diagnostic.error is None,
                error=diagnostic.error,
                missing_metrics=list(diagnostic.missing_metrics),
                warnings=list(diagnostic.warnings),
            )
            warnings.extend(diagnostic.warnings)
        return AdminRuleValidationResponse(
            valid=all(result.valid for result in results.values()),
            formula_results=results,
            required_metrics=sorted(required_metrics),
            warnings=self._dedupe(warnings),
        )

    def _validate_publish_contract(
        self,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        *,
        validation: AdminRuleValidationResponse,
        backtest_metadata: dict[str, Any] | None,
        publish_request: AdminRulePublishRequest,
    ) -> None:
        if not definition.allowed_actions_json:
            self._raise_publish_blocker(
                "no_allowed_action", "Publish requires at least one allowed action"
            )
        invalid_actions = self._invalid_actions(definition.allowed_actions_json)
        if invalid_actions:
            self._raise_publish_blocker(
                "dangerous_action",
                "Publish includes unknown or unsafe action codes",
                details={"invalid_actions": invalid_actions},
            )
        dangerous_actions = dangerous_action_codes(
            definition.allowed_actions_json or []
        )
        if dangerous_actions:
            self._raise_publish_blocker(
                "dangerous_action",
                "Publish cannot expose direct mutation actions; use a safe review workbench action instead",
                details={"dangerous_actions": dangerous_actions},
            )
        if (
            not str(definition.title_template or "").strip()
            or not str(definition.description_template or "").strip()
            or not str(definition.recommendation_template or "").strip()
        ):
            self._raise_publish_blocker(
                "seller_preview_missing",
                "Publish requires seller-facing title, explanation, and next step",
            )
        if not isinstance(rule.condition_json, dict) or not rule.condition_json:
            self._raise_publish_blocker(
                "invalid_formula", "Publish requires detection condition"
            )
        if (
            not str(definition.impact_type_default or "").strip()
            or not str(definition.trust_state_default or "").strip()
        ):
            self._raise_publish_blocker(
                "invalid_formula", "Publish requires impact/trust semantics"
            )
        evidence = rule.evidence_template_json or {}
        if (
            not isinstance(evidence, dict)
            or not str(evidence.get("formula_human") or "").strip()
        ):
            self._raise_publish_blocker(
                "no_evidence", "Publish requires evidence_template_json.formula_human"
            )
        selected_input_metrics = evidence.get("selected_input_metrics")
        if not isinstance(selected_input_metrics, list) or not [
            item for item in selected_input_metrics if str(item).strip()
        ]:
            self._raise_publish_blocker(
                "no_evidence", "Publish requires evidence selected_input_metrics"
            )
        seller_visible = self._is_seller_visible(definition, rule)
        try:
            self._validate_solve_map_template(
                evidence.get("solve_map_template") or evidence.get("solve_map"),
                allowed_actions=definition.allowed_actions_json or [],
            )
        except HTTPException as exc:
            self._raise_publish_blocker(
                "seller_preview_missing",
                "Publish requires complete seller preview solve map",
                details={"solve_map_error": exc.detail},
            )
        recheck_human = (
            evidence.get("recheck_rule_human")
            or (rule.recheck_rule_json or {}).get("human")
            or (rule.recheck_rule_json or {}).get("description")
        )
        if not str(recheck_human or "").strip():
            self._raise_publish_blocker(
                "no_recheck_rule", "Publish requires a human-readable recheck rule"
            )
        if (
            definition.trust_state_default == "test_only"
            or rule.confidence_formula_json == "test_only"
            or (
                seller_visible
                and (
                    bool(getattr(definition, "test_only", False))
                    or bool(getattr(rule, "test_only", False))
                )
            )
        ):
            self._raise_publish_blocker(
                "test_only_visibility_conflict",
                "Rule is still test_only and cannot be published to sellers",
            )
        normalized_actions = normalize_action_center_allowed_actions(
            definition.allowed_actions_json or []
        )
        if seller_visible and "recheck" not in normalized_actions:
            self._raise_publish_blocker(
                "no_recheck_rule", "Seller-visible rules require a recheck action"
            )
        if not [
            action for action in normalized_actions if action in PRIMARY_SAFE_ACTIONS
        ]:
            self._raise_publish_blocker(
                "no_allowed_action", "Publish requires at least one primary safe action"
            )
        selected_metrics = set(validation.required_metrics)
        selected_metrics.update(
            str(item) for item in selected_input_metrics if str(item).strip()
        )
        if PRICE_OR_PROMO_ACTIONS.intersection(
            set(definition.allowed_actions_json or [])
        ) and not selected_metrics.intersection(PRICE_SAFETY_METRICS):
            self._raise_publish_blocker(
                "price_promo_missing_safety",
                "Unsafe price or promo action requires margin/cost/safe price metrics",
            )
        if backtest_metadata is None:
            self._raise_publish_blocker(
                "no_backtest",
                "Publish requires at least one successful backtest",
                status_code=status.HTTP_409_CONFLICT,
            )
        evaluated_count = int(backtest_metadata.get("evaluated_count") or 0)
        matched_count = int(backtest_metadata.get("matched_count") or 0)
        missing_metric_stats = backtest_metadata.get("missing_metric_stats")
        if not isinstance(missing_metric_stats, dict):
            self._raise_publish_blocker(
                "seller_preview_missing",
                "Publish requires backtest missing data rates",
                status_code=status.HTTP_409_CONFLICT,
            )
        sample_issue_count = int(backtest_metadata.get("sample_issue_count") or 0)
        seller_preview_payload = backtest_metadata.get("seller_preview_payload")
        required_preview_keys = {
            "action_center_preview",
            "product360_preview",
            "data_fix_preview",
            "money_preview",
            "results_preview",
        }
        if matched_count <= 0 or sample_issue_count <= 0:
            self._raise_publish_blocker(
                "seller_preview_missing",
                "Publish requires at least one backtest sample card preview",
            )
        if not isinstance(
            seller_preview_payload, dict
        ) or not required_preview_keys.issubset(seller_preview_payload.keys()):
            self._raise_publish_blocker(
                "seller_preview_missing",
                "Publish requires complete seller_preview_payload from latest backtest",
                details={
                    "missing_preview_keys": sorted(
                        required_preview_keys.difference(
                            (seller_preview_payload or {}).keys()
                        )
                    )
                },
            )
        if evaluated_count > 0:
            for metric, count in missing_metric_stats.items():
                if int(count or 0) / evaluated_count > 0.5:
                    self._raise_publish_blocker(
                        "high_missing_metric_rate",
                        f"Metric {metric} is missing for more than half of backtested products",
                        status_code=status.HTTP_409_CONFLICT,
                        details={
                            "metric": metric,
                            "missing_count": count,
                            "evaluated_count": evaluated_count,
                        },
                    )
        if (
            evaluated_count >= WIDE_MATCH_MIN_EVALUATED
            and matched_count / max(evaluated_count, 1) > WIDE_MATCH_RATIO
        ):
            if not publish_request.override:
                self._raise_publish_blocker(
                    "too_many_matches",
                    "Rule matches too many products; provide override_reason to publish intentionally",
                    status_code=status.HTTP_409_CONFLICT,
                    details={
                        "matched_count": matched_count,
                        "evaluated_count": evaluated_count,
                    },
                )
            if not (publish_request.override_reason or "").strip():
                self._raise_publish_blocker(
                    "too_many_matches",
                    "override_reason is required for broad-match publish override",
                    details={
                        "matched_count": matched_count,
                        "evaluated_count": evaluated_count,
                    },
                )

    @staticmethod
    def _require_text(value: Any, detail: str) -> None:
        if not str(value or "").strip():
            raise HTTPException(status_code=422, detail=detail)

    def _validate_solve_map_template(
        self, template: Any, *, allowed_actions: list[str]
    ) -> None:
        if not isinstance(template, dict):
            raise HTTPException(
                status_code=422, detail="Publish requires solve_map_template"
            )
        if not str(template.get("title") or "").strip():
            raise HTTPException(
                status_code=422, detail="Publish requires solve_map_template.title"
            )
        if not str(template.get("summary") or "").strip():
            raise HTTPException(
                status_code=422, detail="Publish requires solve_map_template.summary"
            )
        steps = template.get("steps")
        if not isinstance(steps, list) or not steps:
            raise HTTPException(
                status_code=422, detail="Publish requires solve_map_template.steps"
            )
        normalized_allowed = normalize_action_center_allowed_actions(allowed_actions)
        primary_actions: list[str] = []
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                raise HTTPException(
                    status_code=422,
                    detail=f"solve_map_template.steps[{index}] must be an object",
                )
            for field in (
                "step_id",
                "title",
                "description",
                "status",
                "completion_signal",
            ):
                if not str(step.get(field) or "").strip():
                    raise HTTPException(
                        status_code=422,
                        detail=f"solve_map_template.steps[{index}] requires {field}",
                    )
            try:
                int(step.get("order"))
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=422,
                    detail=f"solve_map_template.steps[{index}] requires numeric order",
                )
            status_value = str(step.get("status") or "").strip().lower()
            if status_value not in SOLVE_STEP_STATUSES:
                raise HTTPException(
                    status_code=422,
                    detail=f"solve_map_template.steps[{index}] has invalid status",
                )
            metrics = step.get("required_metrics")
            if not isinstance(metrics, list) or not [
                str(item).strip() for item in metrics if str(item).strip()
            ]:
                raise HTTPException(
                    status_code=422,
                    detail=f"solve_map_template.steps[{index}] requires required_metrics",
                )
            action_code = str(step.get("action_code") or "").strip()
            if action_code:
                primary_actions.extend(
                    action
                    for action in normalize_action_center_allowed_actions([action_code])
                    if action in normalized_allowed
                )
        if not [action for action in primary_actions if action in PRIMARY_SAFE_ACTIONS]:
            raise HTTPException(
                status_code=422,
                detail="solve_map_template requires at least one allowed primary safe action step",
            )

    @staticmethod
    def _validate_actions(actions: list[str]) -> None:
        invalid = ProblemRuleAdminService._invalid_actions(actions)
        if invalid:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Unknown problem rule actions",
                    "invalid_actions": invalid,
                },
            )
        disallowed = disallowed_rule_builder_actions(actions)
        if disallowed:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Dangerous or external-write actions are not allowed directly in rule builder",
                    "blocker_key": "dangerous_action",
                    "dangerous_actions": disallowed,
                    "allowed_safe_navigation": [
                        "open_price_review",
                        "open_promo_planner",
                        "open_ads_dashboard",
                        "run_checker",
                    ],
                },
            )

    @staticmethod
    def _invalid_actions(actions: list[str]) -> list[str]:
        return unknown_action_codes(actions)

    async def _has_successful_backtest(
        self, session: AsyncSession, *, rule_id: int
    ) -> bool:
        count = int(
            (
                await session.execute(
                    select(func.count(AdminRuleTestRun.id)).where(
                        AdminRuleTestRun.rule_version_id == rule_id
                    )
                )
            ).scalar_one()
        )
        return count > 0

    async def _latest_backtest_metadata(
        self, session: AsyncSession, *, rule_id: int
    ) -> dict[str, Any] | None:
        audit = (
            await session.execute(
                select(ProblemRuleAdminAudit)
                .where(
                    ProblemRuleAdminAudit.object_type == "rule_version",
                    ProblemRuleAdminAudit.object_id == rule_id,
                    ProblemRuleAdminAudit.event_type == "backtested",
                )
                .order_by(
                    ProblemRuleAdminAudit.created_at.desc(),
                    ProblemRuleAdminAudit.id.desc(),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if audit is not None and isinstance(audit.new_value_json, dict):
            metadata = dict(audit.new_value_json)
            run_id = metadata.get("test_run_id")
            if run_id is not None:
                run = await session.get(AdminRuleTestRun, int(run_id))
                if run is not None:
                    metadata.setdefault(
                        "sample_issue_count", len(run.sample_issues_json or [])
                    )
                    metadata.setdefault(
                        "missing_metric_stats",
                        metadata.get("missing_metric_stats") or {},
                    )
                    metadata.setdefault("warnings", list(run.warnings_json or []))
            return metadata
        run = (
            await session.execute(
                select(AdminRuleTestRun)
                .where(AdminRuleTestRun.rule_version_id == rule_id)
                .order_by(
                    AdminRuleTestRun.created_at.desc(), AdminRuleTestRun.id.desc()
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        return {
            "matched_count": int(run.matched_count or 0),
            "evaluated_count": None,
            "missing_metric_stats": {},
            "sample_issue_count": len(run.sample_issues_json or []),
            "test_run_id": run.id,
        }

    async def _backtest_metadata_by_run_ids(
        self,
        session: AsyncSession,
        *,
        version_ids: list[int],
        run_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        if not version_ids or not run_ids:
            return {}
        run_id_set = {int(run_id) for run_id in run_ids}
        audits = list(
            (
                await session.execute(
                    select(ProblemRuleAdminAudit)
                    .where(
                        ProblemRuleAdminAudit.object_type == "rule_version",
                        ProblemRuleAdminAudit.object_id.in_(version_ids),
                        ProblemRuleAdminAudit.event_type == "backtested",
                    )
                    .order_by(
                        ProblemRuleAdminAudit.created_at.desc(),
                        ProblemRuleAdminAudit.id.desc(),
                    )
                )
            ).scalars()
        )
        metadata_by_run_id: dict[int, dict[str, Any]] = {}
        for audit in audits:
            if not isinstance(audit.new_value_json, dict):
                continue
            try:
                run_id = int(audit.new_value_json.get("test_run_id"))
            except (TypeError, ValueError):
                continue
            if run_id in run_id_set and run_id not in metadata_by_run_id:
                metadata_by_run_id[run_id] = dict(audit.new_value_json)
        return metadata_by_run_id

    @staticmethod
    def _backtest_history_item(
        run: AdminRuleTestRun,
        *,
        metadata: dict[str, Any] | None,
    ) -> AdminRuleBacktestHistoryItem:
        metadata = metadata or {}
        total_expected_impact = metadata.get("total_expected_impact")
        if not isinstance(total_expected_impact, dict) or not total_expected_impact:
            total_expected_impact = {
                "amount": str(run.total_impact_amount)
                if run.total_impact_amount is not None
                else None,
                "currency": "RUB" if run.total_impact_amount is not None else None,
                "by_trust_state": {},
                "by_impact_type": {},
                "by_trust_and_impact_type": {},
                "claim": "expected_impact_not_saved_money",
            }
        return AdminRuleBacktestHistoryItem.model_validate(
            {
                "id": run.id,
                "run_id": run.id,
                "rule_version_id": run.rule_version_id,
                "account_id": run.account_id,
                "date_from": run.date_from,
                "date_to": run.date_to,
                "started_at": run.created_at,
                "finished_at": run.created_at,
                "status": "completed",
                "matched_count": run.matched_count,
                "sample_issues_json": list(run.sample_issues_json or []),
                "total_impact_amount": run.total_impact_amount,
                "warnings_json": list(run.warnings_json or []),
                "warnings": list(run.warnings_json or []),
                "created_by_user_id": run.created_by_user_id,
                "created_at": run.created_at,
                "evaluated_count": metadata.get("evaluated_count"),
                "total_expected_impact": total_expected_impact,
                "missing_metric_stats": metadata.get("missing_metric_stats") or {},
                "sample_evidence": metadata.get("sample_evidence") or [],
                "seller_preview_payload": metadata.get("seller_preview_payload") or {},
            }
        )

    async def _rates_by_definition_ids(
        self,
        session: AsyncSession,
        definition_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        counts = await self._counts_by_definition_ids(session, definition_ids)
        dismissed_counts = await self._dismissed_counts_by_definition_ids(
            session, definition_ids
        )
        resolved_counts = await self._counts_by_definition_ids(
            session,
            definition_ids,
            include_statuses=self._resolved_statuses(),
        )
        active_counts = await self._counts_by_definition_ids(
            session,
            definition_ids,
            exclude_statuses=self._inactive_statuses(),
        )
        return {
            definition_id: {
                "total_instances": counts.get(definition_id, 0),
                "dismissed_count": dismissed_counts.get(definition_id, 0),
                "resolved_count": resolved_counts.get(definition_id, 0),
                "active_count": active_counts.get(definition_id, 0),
                "dismissed_rate": self._rate(
                    dismissed_counts.get(definition_id, 0), counts.get(definition_id, 0)
                ),
                "false_positive_rate": self._rate(
                    dismissed_counts.get(definition_id, 0), counts.get(definition_id, 0)
                ),
            }
            for definition_id in definition_ids
        }

    async def _rates_by_rule_ids(
        self,
        session: AsyncSession,
        rule_ids: list[int],
    ) -> dict[int, dict[str, Any]]:
        counts = await self._counts_by_rule_ids(session, rule_ids)
        dismissed_counts = await self._dismissed_counts_by_rule_ids(session, rule_ids)
        resolved_counts = await self._counts_by_rule_ids(
            session,
            rule_ids,
            include_statuses=self._resolved_statuses(),
        )
        active_counts = await self._counts_by_rule_ids(
            session,
            rule_ids,
            exclude_statuses=self._inactive_statuses(),
        )
        return {
            rule_id: {
                "total_instances": counts.get(rule_id, 0),
                "dismissed_count": dismissed_counts.get(rule_id, 0),
                "resolved_count": resolved_counts.get(rule_id, 0),
                "active_count": active_counts.get(rule_id, 0),
                "dismissed_rate": self._rate(
                    dismissed_counts.get(rule_id, 0), counts.get(rule_id, 0)
                ),
                "false_positive_rate": self._rate(
                    dismissed_counts.get(rule_id, 0), counts.get(rule_id, 0)
                ),
            }
            for rule_id in rule_ids
        }

    async def _counts_by_definition_ids(
        self,
        session: AsyncSession,
        definition_ids: list[int],
        *,
        include_statuses: set[str] | None = None,
        exclude_statuses: set[str] | None = None,
        recent_since: datetime | None = None,
    ) -> dict[int, int]:
        if not definition_ids:
            return {}
        stmt = select(
            ProblemInstance.problem_definition_id, func.count(ProblemInstance.id)
        ).where(ProblemInstance.problem_definition_id.in_(definition_ids))
        if include_statuses:
            stmt = stmt.where(ProblemInstance.status.in_(sorted(include_statuses)))
        if exclude_statuses:
            stmt = stmt.where(ProblemInstance.status.notin_(sorted(exclude_statuses)))
        if recent_since is not None:
            stmt = stmt.where(ProblemInstance.last_seen_at >= recent_since)
        rows = (
            await session.execute(stmt.group_by(ProblemInstance.problem_definition_id))
        ).all()
        return {int(definition_id): int(count or 0) for definition_id, count in rows}

    async def _counts_by_rule_ids(
        self,
        session: AsyncSession,
        rule_ids: list[int],
        *,
        include_statuses: set[str] | None = None,
        exclude_statuses: set[str] | None = None,
    ) -> dict[int, int]:
        if not rule_ids:
            return {}
        stmt = select(
            ProblemInstance.rule_version_id, func.count(ProblemInstance.id)
        ).where(ProblemInstance.rule_version_id.in_(rule_ids))
        if include_statuses:
            stmt = stmt.where(ProblemInstance.status.in_(sorted(include_statuses)))
        if exclude_statuses:
            stmt = stmt.where(ProblemInstance.status.notin_(sorted(exclude_statuses)))
        rows = (
            await session.execute(stmt.group_by(ProblemInstance.rule_version_id))
        ).all()
        return {int(rule_id): int(count or 0) for rule_id, count in rows}

    async def _recent_counts_by_definition_ids(
        self,
        session: AsyncSession,
        definition_ids: list[int],
        *,
        timestamp_column: Any,
        recent_since: datetime,
    ) -> dict[int, int]:
        if not definition_ids:
            return {}
        rows = (
            await session.execute(
                select(
                    ProblemInstance.problem_definition_id,
                    func.count(ProblemInstance.id),
                )
                .where(
                    ProblemInstance.problem_definition_id.in_(definition_ids),
                    timestamp_column.is_not(None),
                    timestamp_column >= recent_since,
                )
                .group_by(ProblemInstance.problem_definition_id)
            )
        ).all()
        return {int(definition_id): int(count or 0) for definition_id, count in rows}

    async def _recent_dismissed_counts_by_definition_ids(
        self,
        session: AsyncSession,
        definition_ids: list[int],
        *,
        recent_since: datetime,
    ) -> dict[int, int]:
        if not definition_ids:
            return {}
        history_rows = (
            await session.execute(
                select(
                    ProblemInstance.problem_definition_id,
                    func.count(
                        func.distinct(ProblemInstanceHistory.problem_instance_id)
                    ),
                )
                .select_from(ProblemInstance)
                .join(
                    ProblemInstanceHistory,
                    ProblemInstanceHistory.problem_instance_id == ProblemInstance.id,
                )
                .where(
                    ProblemInstance.problem_definition_id.in_(definition_ids),
                    ProblemInstanceHistory.event_type == "dismissed",
                    ProblemInstanceHistory.created_at >= recent_since,
                )
                .group_by(ProblemInstance.problem_definition_id)
            )
        ).all()
        counts = {
            int(definition_id): int(count or 0) for definition_id, count in history_rows
        }
        fallback_rows = (
            await session.execute(
                select(
                    ProblemInstance.problem_definition_id,
                    func.count(ProblemInstance.id),
                )
                .where(
                    ProblemInstance.problem_definition_id.in_(definition_ids),
                    ProblemInstance.dismissed_at.is_not(None),
                    ProblemInstance.dismissed_at >= recent_since,
                )
                .group_by(ProblemInstance.problem_definition_id)
            )
        ).all()
        for definition_id, count in fallback_rows:
            definition_key = int(definition_id)
            counts[definition_key] = max(counts.get(definition_key, 0), int(count or 0))
        return counts

    async def _dismissed_counts_by_definition_ids(
        self,
        session: AsyncSession,
        definition_ids: list[int],
    ) -> dict[int, int]:
        if not definition_ids:
            return {}
        rows = (
            await session.execute(
                select(
                    ProblemInstance.problem_definition_id,
                    func.count(
                        func.distinct(ProblemInstanceHistory.problem_instance_id)
                    ),
                )
                .select_from(ProblemInstance)
                .join(
                    ProblemInstanceHistory,
                    ProblemInstanceHistory.problem_instance_id == ProblemInstance.id,
                )
                .where(
                    ProblemInstance.problem_definition_id.in_(definition_ids),
                    ProblemInstanceHistory.event_type == "dismissed",
                )
                .group_by(ProblemInstance.problem_definition_id)
            )
        ).all()
        return {int(definition_id): int(count or 0) for definition_id, count in rows}

    async def _dismissed_counts_by_rule_ids(
        self,
        session: AsyncSession,
        rule_ids: list[int],
    ) -> dict[int, int]:
        if not rule_ids:
            return {}
        rows = (
            await session.execute(
                select(
                    ProblemInstance.rule_version_id,
                    func.count(
                        func.distinct(ProblemInstanceHistory.problem_instance_id)
                    ),
                )
                .select_from(ProblemInstance)
                .join(
                    ProblemInstanceHistory,
                    ProblemInstanceHistory.problem_instance_id == ProblemInstance.id,
                )
                .where(
                    ProblemInstance.rule_version_id.in_(rule_ids),
                    ProblemInstanceHistory.event_type == "dismissed",
                )
                .group_by(ProblemInstance.rule_version_id)
            )
        ).all()
        return {int(rule_id): int(count or 0) for rule_id, count in rows}

    async def _definition_has_active_versions(
        self, session: AsyncSession, *, definition_id: int
    ) -> bool:
        count = int(
            (
                await session.execute(
                    select(func.count(ProblemRuleVersion.id)).where(
                        ProblemRuleVersion.problem_definition_id == definition_id,
                        ProblemRuleVersion.status == "active",
                    )
                )
            ).scalar_one()
        )
        return count > 0

    @staticmethod
    def _resolved_statuses() -> set[str]:
        return {"resolved", "candidate_resolved", "done"}

    @staticmethod
    def _inactive_statuses() -> set[str]:
        return {"resolved", "dismissed", "candidate_resolved", "done", "ignored"}

    @staticmethod
    def _is_seller_visible(
        definition: ProblemDefinition, rule: ProblemRuleVersion
    ) -> bool:
        visibility_modes = {
            str(getattr(definition, "visibility_mode", None) or "seller"),
            str(getattr(rule, "visibility_mode", None) or "seller"),
        }
        return (
            bool(getattr(definition, "seller_visible", True))
            or bool(getattr(rule, "seller_visible", True))
            or bool({"beta", "seller"}.intersection(visibility_modes))
        )

    @staticmethod
    def _instance_item(instance: ProblemInstance) -> ProblemRuleInstanceItem:
        return ProblemRuleInstanceItem.model_validate(
            {
                "id": instance.id,
                "problem_instance_id": instance.id,
                "account_id": instance.account_id,
                "nm_id": instance.nm_id,
                "problem_code": instance.problem_code,
                "title": instance.title,
                "status": instance.status,
                "severity": instance.severity,
                "trust_state": instance.trust_state,
                "impact_type": instance.impact_type,
                "money_impact_amount": instance.money_impact_amount,
                "first_seen_at": instance.first_seen_at,
                "last_seen_at": instance.last_seen_at,
                "dismissed_at": instance.dismissed_at,
                "dismiss_reason": instance.dismiss_reason,
            }
        )

    @staticmethod
    def _action_catalog_item(action_code: str) -> ProblemRuleActionCatalogItem:
        entry = get_action(action_code)
        if entry is None:
            raise HTTPException(
                status_code=500,
                detail=f"Action registry entry missing for {action_code}",
            )
        return ProblemRuleActionCatalogItem(
            **entry.model_dump(),
            allowed_for_rule_builder=entry.allowed_in_rule_builder,
        )

    def _definition_read(
        self,
        definition: ProblemDefinition,
        *,
        rates: dict[str, Any] | None = None,
    ) -> ProblemDefinitionRead:
        rates = rates or {}
        return ProblemDefinitionRead.model_validate(
            {
                **self._definition_snapshot(definition),
                "total_instances": rates.get("total_instances", 0),
                "dismissed_count": rates.get("dismissed_count", 0),
                "resolved_count": rates.get("resolved_count", 0),
                "active_count": rates.get("active_count", 0),
                "false_positive_rate": rates.get("false_positive_rate"),
                "dismissed_rate": rates.get("dismissed_rate"),
                "created_at": definition.created_at,
                "updated_at": definition.updated_at,
            }
        )

    def _rule_read(
        self,
        rule: ProblemRuleVersion,
        *,
        rates: dict[str, Any] | None = None,
    ) -> ProblemRuleVersionRead:
        rates = rates or {}
        return ProblemRuleVersionRead.model_validate(
            {
                **self._rule_snapshot(rule),
                "total_instances": rates.get("total_instances", 0),
                "dismissed_count": rates.get("dismissed_count", 0),
                "resolved_count": rates.get("resolved_count", 0),
                "active_count": rates.get("active_count", 0),
                "false_positive_rate": rates.get("false_positive_rate"),
                "dismissed_rate": rates.get("dismissed_rate"),
                "created_at": rule.created_at,
                "updated_at": rule.updated_at,
            }
        )

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float | None:
        if denominator <= 0:
            return None
        return round(float(numerator) / float(denominator), 4)

    @staticmethod
    def _date_start(value: date) -> datetime:
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)

    @staticmethod
    def _publish_blocker(
        key: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> AdminRulePublishBlocker:
        return AdminRulePublishBlocker.model_validate(
            {
                "key": key,
                "message": message,
                "severity": "blocker",
                "details": details or {},
            }
        )

    def _raise_publish_blocker(
        self,
        key: str,
        message: str,
        *,
        status_code: int = status.HTTP_422_UNPROCESSABLE_CONTENT,
        details: dict[str, Any] | None = None,
    ) -> None:
        blocker = self._publish_blocker(key, message, details=details)
        raise HTTPException(
            status_code=status_code,
            detail=jsonable_encoder(
                {
                    "message": message,
                    "blocker_keys": [key],
                    "known_blocker_keys": list(PUBLISH_BLOCKER_KEYS),
                    "blockers": [blocker.model_dump()],
                }
            ),
        )

    @staticmethod
    def _formula_blocker_key(validation: AdminRuleValidationResponse) -> str:
        for diagnostic in validation.formula_results.values():
            error = str(diagnostic.error or "").lower()
            if "unknown metric" in error or "unknown operator" in error:
                return "unknown_metric_or_operator"
        return "invalid_formula"

    @staticmethod
    def _definition_snapshot(definition: ProblemDefinition) -> dict[str, Any]:
        return {
            "id": definition.id,
            "problem_code": definition.problem_code,
            "source_module": definition.source_module,
            "category": definition.category,
            "entity_type": definition.entity_type,
            "title_template": definition.title_template,
            "description_template": definition.description_template,
            "recommendation_template": definition.recommendation_template,
            "impact_type_default": definition.impact_type_default,
            "trust_state_default": definition.trust_state_default,
            "severity_default": definition.severity_default,
            "allowed_actions_json": list(definition.allowed_actions_json or []),
            "test_only": bool(getattr(definition, "test_only", False)),
            "seller_visible": bool(getattr(definition, "seller_visible", True)),
            "visibility_mode": str(
                getattr(definition, "visibility_mode", None) or "seller"
            ),
            "status": definition.status,
            "is_system_seeded": bool(getattr(definition, "is_system_seeded", False)),
            "created_by_user_id": definition.created_by_user_id,
        }

    @staticmethod
    def _rule_snapshot(rule: ProblemRuleVersion) -> dict[str, Any]:
        return {
            "id": rule.id,
            "problem_definition_id": rule.problem_definition_id,
            "version": rule.version,
            "status": rule.status,
            "evaluation_grain": rule.evaluation_grain,
            "lookback_days": rule.lookback_days,
            "condition_json": rule.condition_json,
            "impact_formula_json": rule.impact_formula_json,
            "severity_formula_json": rule.severity_formula_json,
            "confidence_formula_json": rule.confidence_formula_json,
            "dedup_key_template": rule.dedup_key_template,
            "recheck_rule_json": rule.recheck_rule_json,
            "evidence_template_json": rule.evidence_template_json,
            "test_only": bool(getattr(rule, "test_only", False)),
            "seller_visible": bool(getattr(rule, "seller_visible", True)),
            "visibility_mode": str(getattr(rule, "visibility_mode", None) or "seller"),
            "is_system_seeded": bool(getattr(rule, "is_system_seeded", False)),
            "created_by_user_id": rule.created_by_user_id,
            "published_by_user_id": rule.published_by_user_id,
            "published_at": rule.published_at,
        }

    @staticmethod
    def _audit(
        session: AsyncSession,
        *,
        object_type: str,
        object_id: int,
        event_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
        actor_user_id: int | None,
        comment: str | None = None,
    ) -> None:
        session.add(
            ProblemRuleAdminAudit(
                object_type=object_type,
                object_id=object_id,
                event_type=event_type,
                old_value_json=jsonable_encoder(old_value),
                new_value_json=jsonable_encoder(new_value),
                comment=comment,
                actor_user_id=actor_user_id,
            )
        )

    @staticmethod
    def _collect_metric_codes(node: Any) -> set[str]:
        codes: set[str] = set()
        if isinstance(node, dict):
            if set(node.keys()) == {"metric"} and isinstance(node.get("metric"), str):
                codes.add(str(node["metric"]))
                return codes
            if set(node.keys()) == {"missing"} and isinstance(
                node.get("missing"), list
            ):
                for item in node["missing"]:
                    if isinstance(item, str):
                        codes.add(item)
                    elif isinstance(item, dict):
                        codes.update(
                            ProblemRuleAdminService._collect_metric_codes(item)
                        )
                return codes
            for value in node.values():
                codes.update(ProblemRuleAdminService._collect_metric_codes(value))
        elif isinstance(node, list):
            for item in node:
                codes.update(ProblemRuleAdminService._collect_metric_codes(item))
        return codes

    @staticmethod
    def _missing_metric_stats(previews: list[Any]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for preview in previews:
            preview_codes: set[str] = set()
            snapshot_metrics = (preview.calculation_snapshot_json or {}).get(
                "missing_metrics"
            ) or []
            for metric_code in snapshot_metrics:
                preview_codes.add(str(metric_code))
            for metric_code in preview.missing_metrics:
                code = str(metric_code).split(":", 1)[0].strip()
                if code:
                    preview_codes.add(code)
            for code in preview_codes:
                counts[code] += 1
        return dict(sorted(counts.items()))

    @staticmethod
    def _total_impact(previews: list[Any]) -> Decimal | None:
        total = Decimal("0")
        seen = False
        for preview in previews:
            amount = preview.money_impact_amount
            if amount is None:
                continue
            total += Decimal(str(amount))
            seen = True
        return total if seen else None

    @staticmethod
    def _total_expected_impact(previews: list[Any]) -> dict[str, Any]:
        by_trust_state: dict[str, str] = {}
        by_impact_type: dict[str, str] = {}
        by_pair: dict[str, str] = {}
        total = Decimal("0")
        seen = False
        for preview in previews:
            amount = preview.money_impact_amount
            if amount is None:
                continue
            value = Decimal(str(amount))
            seen = True
            total += value
            trust_state = str(getattr(preview, "trust_state", None) or "unknown")
            impact_type = str(getattr(preview, "impact_type", None) or "unknown")
            pair_key = f"{trust_state}:{impact_type}"
            by_trust_state[trust_state] = str(
                Decimal(by_trust_state.get(trust_state, "0")) + value
            )
            by_impact_type[impact_type] = str(
                Decimal(by_impact_type.get(impact_type, "0")) + value
            )
            by_pair[pair_key] = str(Decimal(by_pair.get(pair_key, "0")) + value)
        return {
            "amount": str(total) if seen else None,
            "currency": "RUB" if seen else None,
            "by_trust_state": by_trust_state,
            "by_impact_type": by_impact_type,
            "by_trust_and_impact_type": by_pair,
            "claim": "expected_impact_not_saved_money",
        }

    @staticmethod
    def _sample_evidence(sample_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
        evidence_rows: list[dict[str, Any]] = []
        for issue in sample_issues:
            evidence = (
                issue.get("evidence_ledger_json") if isinstance(issue, dict) else None
            )
            if isinstance(evidence, dict) and evidence:
                evidence_rows.append(
                    {
                        "nm_id": issue.get("nm_id"),
                        "problem_code": issue.get("problem_code"),
                        "dedup_key": issue.get("dedup_key"),
                        "evidence_ledger": evidence,
                    }
                )
        return evidence_rows

    @staticmethod
    def _seller_preview_payload(
        *,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        matched_count: int,
        evaluated_count: int,
        sample_issues: list[dict[str, Any]],
        total_expected_impact: dict[str, Any],
        missing_metric_stats: dict[str, int],
        warnings: list[str],
    ) -> dict[str, Any]:
        sample_actions = [
            {
                "nm_id": issue.get("nm_id"),
                "title": issue.get("title"),
                "explanation": issue.get("explanation"),
                "recommendation": issue.get("recommendation"),
                "severity": issue.get("severity"),
                "impact_type": issue.get("impact_type"),
                "trust_state": issue.get("trust_state"),
                "money_impact_amount": issue.get("money_impact_amount"),
                "status": issue.get("status"),
                "action": issue.get("action"),
                "dedup_key": issue.get("dedup_key"),
            }
            for issue in sample_issues[:10]
        ]
        product360_items = [
            {
                "nm_id": issue.get("nm_id"),
                "problem_code": issue.get("problem_code") or definition.problem_code,
                "title": issue.get("title"),
                "severity": issue.get("severity") or definition.severity_default,
                "trust_state": issue.get("trust_state")
                or definition.trust_state_default,
                "impact_type": issue.get("impact_type")
                or definition.impact_type_default,
                "href": f"/products/{issue.get('nm_id')}?problem_code={definition.problem_code}"
                if issue.get("nm_id") is not None
                else "/products",
            }
            for issue in sample_issues[:10]
        ]
        data_fix_actions = {
            "open_data_fix",
            "upload_cost",
            "map_sku",
            "classify_expense",
        }
        data_fix_available = (
            bool(
                data_fix_actions.intersection(
                    set(definition.allowed_actions_json or [])
                )
            )
            or definition.impact_type_default == "data_blocker"
        )
        data_fix_items = [
            {
                "nm_id": issue.get("nm_id"),
                "problem_code": issue.get("problem_code") or definition.problem_code,
                "missing_metrics": (issue.get("calculation_snapshot_json") or {}).get(
                    "missing_metrics", []
                )
                if isinstance(issue.get("calculation_snapshot_json"), dict)
                else [],
                "href": f"/data-fix?problem_code={definition.problem_code}&nm_id={issue.get('nm_id')}"
                if issue.get("nm_id") is not None
                else f"/data-fix?problem_code={definition.problem_code}",
            }
            for issue in sample_issues[:10]
        ]
        results_items = [
            {
                "nm_id": issue.get("nm_id"),
                "problem_code": issue.get("problem_code") or definition.problem_code,
                "dedup_key": issue.get("dedup_key"),
                "evidence_ledger": issue.get("evidence_ledger_json") or {},
                "calculation_snapshot": issue.get("calculation_snapshot_json") or {},
                "href": f"/results?problem_code={definition.problem_code}&nm_id={issue.get('nm_id')}"
                if issue.get("nm_id") is not None
                else f"/results?problem_code={definition.problem_code}",
            }
            for issue in sample_issues[:10]
        ]
        return {
            "problem_code": definition.problem_code,
            "definition_id": definition.id,
            "rule_version_id": rule.id,
            "rule_version": rule.version,
            "source_module": definition.source_module,
            "category": definition.category,
            "entity_type": definition.entity_type,
            "title_template": definition.title_template,
            "description_template": definition.description_template,
            "recommendation_template": definition.recommendation_template,
            "impact_type_default": definition.impact_type_default,
            "trust_state_default": definition.trust_state_default,
            "allowed_actions": list(definition.allowed_actions_json or []),
            "matched_count": matched_count,
            "evaluated_count": evaluated_count,
            "total_expected_impact": total_expected_impact,
            "missing_metric_stats": dict(missing_metric_stats or {}),
            "warnings": list(warnings or []),
            "sample_actions": sample_actions,
            "action_center_preview": {
                "matched_count": matched_count,
                "evaluated_count": evaluated_count,
                "items": sample_actions,
                "allowed_actions": list(definition.allowed_actions_json or []),
            },
            "product360_preview": {
                "items": product360_items,
                "group": definition.category,
                "problem_count": matched_count,
            },
            "data_fix_preview": {
                "available": data_fix_available,
                "items": data_fix_items,
                "missing_metric_stats": dict(missing_metric_stats or {}),
            },
            "money_preview": {
                "expected_impact": total_expected_impact,
                "sample_total_impact_amount": total_expected_impact.get("amount"),
                "currency": total_expected_impact.get("currency"),
                "claim": total_expected_impact.get("claim"),
            },
            "results_preview": {
                "items": results_items,
                "sample_evidence_count": len(
                    [item for item in results_items if item.get("evidence_ledger")]
                ),
            },
        }

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value)
            if text and text not in result:
                result.append(text)
        return result
