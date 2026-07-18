from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.marts import MartSKUDaily, MartStockDaily
from app.models.operator import ResultEvent
from app.models.problem_engine import (
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleVersion,
)
from app.schemas.problem_engine import ProblemInstanceCreate, ProductMetricResolution
from app.services.problem_engine.evidence_ledger import EvidenceLedgerBuilder
from app.services.problem_engine.formula_evaluator import (
    ConditionEvaluationResult,
    FormulaEvaluationResult,
    FormulaEvaluator,
    NumericFormulaEvaluationResult,
)
from app.services.problem_engine.metric_catalog import (
    MetricCatalogService,
    ProductMetricResolver,
)
from app.services.problem_engine.price_safety import (
    PriceSafetyCalculator,
    PriceSafetyResult,
)


SEVERITIES = ("critical", "high", "medium", "low")
TRUST_STATES = (
    "confirmed",
    "provisional",
    "estimated",
    "opportunity",
    "blocked",
    "test_only",
)
IMPACT_TYPES = (
    "confirmed_loss",
    "probable_loss",
    "blocked_cash",
    "lost_sales_risk",
    "opportunity",
    "data_blocker",
    "system_warning",
)
USER_PRESERVED_STATUSES = {"ignored", "postponed", "in_progress", "done"}
ACTIVE_STATUSES = {
    "new",
    "acknowledged",
    "in_progress",
    "postponed",
    "ignored",
    "blocked",
    "done",
}
PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass(frozen=True, slots=True)
class ProblemEntityCandidate:
    account_id: int
    nm_id: int
    vendor_code: str | None = None


@dataclass(slots=True)
class ProblemEvaluationPreview:
    account_id: int
    nm_id: int
    problem_code: str
    dedup_key: str
    matched: bool
    action: str
    status: str
    title: str = ""
    explanation: str = ""
    recommendation: str = ""
    severity: str = "medium"
    impact_type: str = "system_warning"
    money_impact_amount: Decimal | None = None
    confidence: str | None = None
    trust_state: str = "provisional"
    evidence_ledger_json: dict[str, Any] = field(default_factory=dict)
    calculation_snapshot_json: dict[str, Any] = field(default_factory=dict)
    missing_metrics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    existing_instance_id: int | None = None

    def model_dump(self) -> dict[str, Any]:
        return jsonable_encoder(self)


@dataclass(slots=True)
class ProblemEvaluationResult:
    evaluated_count: int = 0
    matched_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    resolved_count: int = 0
    candidate_resolved_count: int = 0
    skipped_count: int = 0
    test_mode: bool = False
    previews: list[ProblemEvaluationPreview] = field(default_factory=list)
    instances: list[ProblemInstance] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class ProblemTemplateRenderer:
    """Render small admin-authored templates with a closed placeholder set."""

    def render(
        self, template: str, values: dict[str, Any], *, strict: bool = False
    ) -> str:
        text = str(template or "")

        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in values:
                if strict:
                    raise ValueError(f"unknown template placeholder: {key}")
                return ""
            value = values[key]
            if value is None:
                return ""
            return self._format(value)

        return PLACEHOLDER_RE.sub(replace, text)

    @staticmethod
    def _format(value: Any) -> str:
        if isinstance(value, Decimal):
            normalized = (
                value.quantize(Decimal("0.01"))
                if value.as_tuple().exponent < -2
                else value
            )
            return format(normalized.normalize(), "f")
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return str(value)


class ProblemEvaluatorService:
    """Evaluate active dynamic product problem rules and upsert instances."""

    def __init__(
        self,
        *,
        metric_resolver: ProductMetricResolver | None = None,
        formula_evaluator: FormulaEvaluator | None = None,
        evidence_builder: EvidenceLedgerBuilder | None = None,
        metric_catalog: MetricCatalogService | None = None,
        price_safety_calculator: PriceSafetyCalculator | None = None,
        template_renderer: ProblemTemplateRenderer | None = None,
    ) -> None:
        self.metric_catalog = metric_catalog or MetricCatalogService()
        self.metric_resolver = metric_resolver or ProductMetricResolver(
            self.metric_catalog
        )
        self.formula_evaluator = formula_evaluator or FormulaEvaluator()
        self.evidence_builder = evidence_builder or EvidenceLedgerBuilder()
        self.price_safety_calculator = (
            price_safety_calculator or PriceSafetyCalculator()
        )
        self.template_renderer = template_renderer or ProblemTemplateRenderer()

    async def evaluate_account(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        test_mode: bool = False,
    ) -> ProblemEvaluationResult:
        date_to = date_to or datetime.now(UTC).date()
        date_from = date_from or date_to - timedelta(days=29)
        result = ProblemEvaluationResult(test_mode=test_mode)
        rules = await self._active_product_rules(session)
        candidates = await self._eligible_products(
            session, account_id=account_id, date_from=date_from, date_to=date_to
        )

        for candidate in candidates:
            product_result = await self._evaluate_product_candidates(
                session,
                account_id=account_id,
                candidate=candidate,
                date_from=date_from,
                date_to=date_to,
                rules=rules,
                test_mode=test_mode,
            )
            self._merge_result(result, product_result)
        return result

    async def evaluate_all_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        test_mode: bool = False,
    ) -> ProblemEvaluationResult:
        return await self.evaluate_account(
            session,
            account_id=account_id,
            date_from=date_from,
            date_to=date_to,
            test_mode=test_mode,
        )

    async def evaluate_product(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date | None = None,
        date_to: date | None = None,
        test_mode: bool = False,
    ) -> ProblemEvaluationResult:
        date_to = date_to or datetime.now(UTC).date()
        date_from = date_from or date_to - timedelta(days=29)
        rules = await self._active_product_rules(session)
        candidate = ProblemEntityCandidate(
            account_id=account_id,
            nm_id=nm_id,
            vendor_code=await self._vendor_code_for_product(
                session,
                account_id=account_id,
                nm_id=nm_id,
                date_from=date_from,
                date_to=date_to,
            ),
        )
        return await self._evaluate_product_candidates(
            session,
            account_id=account_id,
            candidate=candidate,
            date_from=date_from,
            date_to=date_to,
            rules=rules,
            test_mode=test_mode,
        )

    async def evaluate_rule_version(
        self,
        session: AsyncSession,
        *,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        account_id: int,
        nm_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        test_mode: bool = True,
    ) -> ProblemEvaluationResult:
        """Evaluate one rule version directly for admin preview/backtest.

        This intentionally bypasses active-status filtering so draft/testing
        rules can be previewed before publication.
        """

        date_to = date_to or datetime.now(UTC).date()
        date_from = date_from or date_to - timedelta(
            days=max(int(rule.lookback_days or 30), 1) - 1
        )
        rules = [(rule, definition)]
        if definition.entity_type != "product":
            return ProblemEvaluationResult(test_mode=test_mode)
        if nm_id is not None:
            candidate = ProblemEntityCandidate(
                account_id=account_id,
                nm_id=nm_id,
                vendor_code=await self._vendor_code_for_product(
                    session,
                    account_id=account_id,
                    nm_id=nm_id,
                    date_from=date_from,
                    date_to=date_to,
                ),
            )
            return await self._evaluate_product_candidates(
                session,
                account_id=account_id,
                candidate=candidate,
                date_from=date_from,
                date_to=date_to,
                rules=rules,
                test_mode=test_mode,
            )

        result = ProblemEvaluationResult(test_mode=test_mode)
        candidates = await self._eligible_products(
            session, account_id=account_id, date_from=date_from, date_to=date_to
        )
        for candidate in candidates:
            product_result = await self._evaluate_product_candidates(
                session,
                account_id=account_id,
                candidate=candidate,
                date_from=date_from,
                date_to=date_to,
                rules=rules,
                test_mode=test_mode,
            )
            self._merge_result(result, product_result)
        return result

    async def _evaluate_product_candidates(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        candidate: ProblemEntityCandidate,
        date_from: date,
        date_to: date,
        rules: list[tuple[ProblemRuleVersion, ProblemDefinition]],
        test_mode: bool,
    ) -> ProblemEvaluationResult:
        result = ProblemEvaluationResult(test_mode=test_mode)
        allowed_metrics = await self.metric_catalog.allowed_metric_codes(session)

        for rule, definition in rules:
            metric_codes = self._metric_codes_for_rule(rule)
            for metric_code in self.price_safety_calculator.required_metric_codes(
                definition.problem_code
            ):
                if metric_code not in metric_codes:
                    metric_codes.append(metric_code)
            resolved = await self.metric_resolver.resolve_product_metrics(
                session,
                account_id=account_id,
                nm_id=candidate.nm_id,
                date_from=date_from,
                date_to=date_to,
                metric_codes=metric_codes,
            )
            preview, instance = await self._evaluate_rule_for_product(
                session,
                definition=definition,
                rule=rule,
                candidate=candidate,
                resolved=resolved,
                allowed_metrics=allowed_metrics,
                date_from=date_from,
                date_to=date_to,
                test_mode=test_mode,
            )
            result.evaluated_count += 1
            result.previews.append(preview)
            result.warnings.extend(preview.warnings)
            if instance is not None:
                result.instances.append(instance)
            match preview.action:
                case "created":
                    result.created_count += 1
                    result.matched_count += 1
                case "updated" | "preserved":
                    result.updated_count += 1
                    result.matched_count += 1
                case "resolved":
                    result.resolved_count += 1
                case "candidate_resolved":
                    result.candidate_resolved_count += 1
                case "preview_create" | "preview_update" | "preview_preserve":
                    result.matched_count += 1
                case "skipped":
                    result.skipped_count += 1
        return result

    async def _evaluate_rule_for_product(
        self,
        session: AsyncSession,
        *,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        candidate: ProblemEntityCandidate,
        resolved: ProductMetricResolution,
        allowed_metrics: set[str],
        date_from: date,
        date_to: date,
        test_mode: bool,
    ) -> tuple[ProblemEvaluationPreview, ProblemInstance | None]:
        now = datetime.now(UTC)
        metric_values = resolved.values_for_formula()
        context = {
            "allowed_metrics": allowed_metrics,
            "account_id": candidate.account_id,
            "nm_id": candidate.nm_id,
        }
        condition = self.formula_evaluator.evaluate_condition(
            rule.condition_json, metrics=metric_values, evaluation_context=context
        )
        create_blocker = bool(
            resolved.missing_metrics
            and self._missing_metrics_create_blocker(definition, rule)
        )
        matched = bool(condition.value or create_blocker)
        render_values = self._render_values(
            definition=definition,
            rule=rule,
            candidate=candidate,
            resolved=resolved,
            impact=None,
            severity=definition.severity_default,
            confidence=None,
            trust_state="blocked" if create_blocker else definition.trust_state_default,
            dedup_key=None,
        )
        dedup_key = self.template_renderer.render(
            rule.dedup_key_template, render_values, strict=True
        )
        render_values["dedup_key"] = dedup_key
        existing = await self._find_existing_instance(
            session,
            account_id=candidate.account_id,
            problem_code=definition.problem_code,
            entity_type=definition.entity_type,
            entity_id=str(candidate.nm_id),
            dedup_key=dedup_key,
        )

        if not matched:
            preview, instance = await self._handle_no_match(
                session,
                existing=existing,
                definition=definition,
                rule=rule,
                candidate=candidate,
                dedup_key=dedup_key,
                resolved=resolved,
                condition=condition,
                allowed_metrics=allowed_metrics,
                now=now,
                test_mode=test_mode,
            )
            return preview, instance

        impact = (
            NumericFormulaEvaluationResult(
                value=None, missing_metrics=[], warnings=[], error=None
            )
            if create_blocker
            else self.formula_evaluator.evaluate_numeric(
                rule.impact_formula_json,
                metrics=metric_values,
                evaluation_context=context,
            )
        )
        severity_eval = (
            self.formula_evaluator.evaluate(
                rule.severity_formula_json,
                metrics=metric_values,
                evaluation_context=context,
            )
            if rule.severity_formula_json
            else FormulaEvaluationResult(value=None)
        )
        confidence_eval = (
            self.formula_evaluator.evaluate(
                rule.confidence_formula_json,
                metrics=metric_values,
                evaluation_context=context,
            )
            if rule.confidence_formula_json
            else FormulaEvaluationResult(value=None)
        )
        severity = self._severity_from(
            severity_eval.value, default=definition.severity_default
        )
        confidence = self._confidence_from(confidence_eval.value)
        trust_state = (
            "blocked"
            if create_blocker
            else self._trust_state_from(
                confidence, default=definition.trust_state_default
            )
        )
        impact_type = (
            "data_blocker"
            if create_blocker
            else self._impact_type_from(definition.impact_type_default)
        )
        money_impact = None if create_blocker else impact.value
        price_safety = self.price_safety_calculator.evaluate(
            problem_code=definition.problem_code, resolved=resolved
        )
        snapshot = self._calculation_snapshot(
            definition=definition,
            rule=rule,
            candidate=candidate,
            resolved=resolved,
            condition=condition,
            impact=impact,
            severity=severity_eval,
            confidence=confidence_eval,
            matched=True,
            create_blocker=create_blocker,
            generated_at=now,
        )
        solve_map_template = self._solve_map_template(rule)
        if solve_map_template is not None:
            snapshot["solve_map_template"] = jsonable_encoder(solve_map_template)
        if price_safety is not None:
            snapshot["price_safety"] = jsonable_encoder(price_safety.to_snapshot())
            snapshot["allowed_actions"] = self._allowed_actions_for_instance(
                definition, price_safety=price_safety
            )
        if self._price_safety_resolves_negative_profit(
            definition.problem_code, price_safety
        ):
            snapshot["matched"] = False
            snapshot["suppressed_by_price_safety"] = {
                "status": price_safety.status if price_safety is not None else None,
                "reason": price_safety.reason if price_safety is not None else None,
            }
            return await self._handle_suppressed_match(
                session,
                existing=existing,
                definition=definition,
                rule=rule,
                candidate=candidate,
                dedup_key=dedup_key,
                resolved=resolved,
                condition=condition,
                snapshot=snapshot,
                now=now,
                test_mode=test_mode,
                reason="Current effective price is already above the safe minimum; the historical loss should not stay as a price task.",
            )
        render_values = self._render_values(
            definition=definition,
            rule=rule,
            candidate=candidate,
            resolved=resolved,
            impact=money_impact,
            severity=severity,
            confidence=confidence,
            trust_state=trust_state,
            dedup_key=dedup_key,
        )
        if price_safety is not None:
            render_values.update(price_safety.render_values())
        title = (
            self.template_renderer.render(
                definition.title_template, render_values
            ).strip()
            or definition.title_template
        )
        explanation = (
            self.template_renderer.render(
                definition.description_template, render_values
            ).strip()
            or definition.description_template
        )
        recommendation = (
            self.template_renderer.render(
                definition.recommendation_template, render_values
            ).strip()
            or definition.recommendation_template
        )
        recommendation = self.price_safety_calculator.recommendation(
            problem_code=definition.problem_code,
            base_recommendation=recommendation,
            price_safety=price_safety,
        )
        ledger = self.evidence_builder.build_json(
            rule_version=rule,
            resolved_metrics=resolved,
            formula_diagnostics=[condition, impact, severity_eval, confidence_eval],
            formula_human=self._formula_human(rule, definition),
            formula_code=f"{definition.problem_code}.v{rule.version}",
            recheck_rule_human=self._recheck_rule_human(rule),
            trust_notes=price_safety.trust_notes if price_safety is not None else None,
            calculation_warnings=[
                *resolved.warnings,
                *(price_safety.warnings if price_safety is not None else []),
            ],
        )
        payload = ProblemInstanceCreate.model_validate(
            {
                "account_id": candidate.account_id,
                "problem_code": definition.problem_code,
                "problem_definition_id": definition.id,
                "rule_version_id": rule.id,
                "source_module": definition.source_module,
                "entity_type": definition.entity_type,
                "entity_id": str(candidate.nm_id),
                "nm_id": candidate.nm_id,
                "vendor_code": candidate.vendor_code,
                "dedup_key": dedup_key,
                "title": title[:255],
                "explanation": explanation,
                "recommendation": recommendation,
                "severity": severity,
                "status": self._initial_status(impact_type=impact_type, rule=rule),
                "impact_type": impact_type,
                "money_impact_amount": money_impact,
                "money_impact_currency": self._money_currency(rule),
                "trust_state": trust_state,
                "confidence": confidence,
                "evidence_ledger_json": ledger,
                "calculation_snapshot_json": snapshot,
                "first_seen_at": now,
                "last_seen_at": now,
            }
        )
        if test_mode:
            action = "preview_update" if existing else "preview_create"
            if (
                existing
                and existing.status in USER_PRESERVED_STATUSES
                and not self._reopen_preserved_status(rule, existing.status)
            ):
                action = "preview_preserve"
            return self._preview_from_payload(
                payload, matched=True, action=action, existing=existing
            ), None
        if existing is None:
            instance = ProblemInstance(**payload.model_dump())
            session.add(instance)
            await session.flush()
            self._add_history(
                session, instance, "created", None, {"status": instance.status}
            )
            if str(instance.severity or "").lower() == "critical":
                self._add_notification(
                    session,
                    instance,
                    notification_type="new_critical_issue",
                    message="New critical dynamic problem created.",
                    outcome="pending",
                )
            return self._preview_from_instance(
                instance, matched=True, action="created"
            ), instance

        old_status = existing.status
        action = "updated"
        self._apply_payload(existing, payload)
        if old_status in USER_PRESERVED_STATUSES and not self._reopen_preserved_status(
            rule, old_status
        ):
            existing.status = old_status
            action = "preserved"
        elif old_status in {
            "resolved",
            "dismissed",
            "candidate_resolved",
        } or self._reopen_preserved_status(rule, old_status):
            existing.status = "new"
            existing.resolved_at = None
            existing.dismissed_at = None
            existing.dismiss_reason = None
            action = "updated"
        await session.flush()
        if existing.status != old_status:
            self._add_history(
                session,
                existing,
                "status_changed",
                {"status": old_status},
                {"status": existing.status},
            )
            if existing.status == "new" and old_status in {
                "resolved",
                "dismissed",
                "candidate_resolved",
            }:
                self._add_notification(
                    session,
                    existing,
                    notification_type="issue_reopened",
                    message="Dynamic problem condition matched again.",
                    outcome="pending",
                    payload={"old_status": old_status, "new_status": existing.status},
                )
        else:
            self._add_history(
                session,
                existing,
                "rechecked",
                {"status": old_status},
                {"status": existing.status},
            )
        return self._preview_from_instance(
            existing, matched=True, action=action
        ), existing

    async def _handle_suppressed_match(
        self,
        session: AsyncSession,
        *,
        existing: ProblemInstance | None,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        candidate: ProblemEntityCandidate,
        dedup_key: str,
        resolved: ProductMetricResolution,
        condition: ConditionEvaluationResult,
        snapshot: dict[str, Any],
        now: datetime,
        test_mode: bool,
        reason: str,
    ) -> tuple[ProblemEvaluationPreview, ProblemInstance | None]:
        if existing is None:
            return (
                ProblemEvaluationPreview(
                    account_id=candidate.account_id,
                    nm_id=candidate.nm_id,
                    problem_code=definition.problem_code,
                    dedup_key=dedup_key,
                    matched=False,
                    action="skipped",
                    status="not_created",
                    calculation_snapshot_json=snapshot,
                    missing_metrics=list(resolved.missing_metrics),
                    warnings=self._diagnostic_warnings(condition),
                ),
                None,
            )
        if existing.status in {"resolved", "dismissed"}:
            return self._preview_from_instance(
                existing, matched=False, action="skipped"
            ), existing
        if test_mode:
            preview = self._preview_from_instance(
                existing, matched=False, action="resolved"
            )
            preview.status = "resolved"
            preview.calculation_snapshot_json = snapshot
            return preview, None

        old_status = existing.status
        existing.status = "resolved"
        existing.resolved_at = now
        existing.last_seen_at = now
        existing.calculation_snapshot_json = snapshot
        await session.flush()
        self._add_history(
            session,
            existing,
            "status_changed",
            {"status": old_status},
            {"status": "resolved", "reason": reason},
        )
        return self._preview_from_instance(
            existing, matched=False, action="resolved"
        ), existing

    async def _handle_no_match(
        self,
        session: AsyncSession,
        *,
        existing: ProblemInstance | None,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        candidate: ProblemEntityCandidate,
        dedup_key: str,
        resolved: ProductMetricResolution,
        condition: ConditionEvaluationResult,
        allowed_metrics: set[str],
        now: datetime,
        test_mode: bool,
    ) -> tuple[ProblemEvaluationPreview, ProblemInstance | None]:
        snapshot = self._calculation_snapshot(
            definition=definition,
            rule=rule,
            candidate=candidate,
            resolved=resolved,
            condition=condition,
            impact=NumericFormulaEvaluationResult(value=None),
            severity=FormulaEvaluationResult(value=None),
            confidence=FormulaEvaluationResult(value=None),
            matched=False,
            create_blocker=False,
            generated_at=now,
        )
        resolved_when = self._resolved_when(rule)
        resolution_allowed = True
        resolution_condition: ConditionEvaluationResult | None = None
        if resolved_when:
            resolution_condition = self.formula_evaluator.evaluate_condition(
                resolved_when,
                metrics=resolved.values_for_formula(),
                evaluation_context={"allowed_metrics": allowed_metrics},
            )
            resolution_allowed = bool(resolution_condition.value)
            snapshot["resolved_when"] = jsonable_encoder(
                {
                    "value": resolution_condition.value,
                    "missing_metrics": resolution_condition.missing_metrics,
                    "warnings": resolution_condition.warnings,
                    "error": resolution_condition.error,
                }
            )
        if existing is None:
            return (
                ProblemEvaluationPreview(
                    account_id=candidate.account_id,
                    nm_id=candidate.nm_id,
                    problem_code=definition.problem_code,
                    dedup_key=dedup_key,
                    matched=False,
                    action="skipped",
                    status="not_created",
                    calculation_snapshot_json=snapshot,
                    missing_metrics=list(resolved.missing_metrics),
                    warnings=self._diagnostic_warnings(condition, resolution_condition),
                ),
                None,
            )
        if existing.status in {"resolved", "dismissed"}:
            return self._preview_from_instance(
                existing, matched=False, action="skipped"
            ), existing
        new_status = (
            "resolved"
            if resolution_allowed and not self._candidate_resolved(rule)
            else "candidate_resolved"
        )
        snapshot["previous_status"] = existing.status
        snapshot["resolution_candidate"] = new_status == "candidate_resolved"
        if test_mode:
            preview = self._preview_from_instance(
                existing, matched=False, action=new_status
            )
            preview.calculation_snapshot_json = snapshot
            preview.status = new_status
            return preview, None
        old_status = existing.status
        existing.status = new_status
        existing.last_seen_at = now
        existing.calculation_snapshot_json = snapshot
        if new_status == "resolved":
            existing.resolved_at = now
        await session.flush()
        self._add_history(
            session,
            existing,
            "status_changed",
            {"status": old_status},
            {"status": new_status},
        )
        return self._preview_from_instance(
            existing, matched=False, action=new_status
        ), existing

    async def _active_product_rules(
        self, session: AsyncSession
    ) -> list[tuple[ProblemRuleVersion, ProblemDefinition]]:
        stmt = (
            select(ProblemRuleVersion, ProblemDefinition)
            .join(
                ProblemDefinition,
                ProblemDefinition.id == ProblemRuleVersion.problem_definition_id,
            )
            .where(
                ProblemRuleVersion.status == "active",
                ProblemDefinition.status == "active",
                ProblemDefinition.entity_type == "product",
            )
            .order_by(
                ProblemDefinition.problem_code.asc(), ProblemRuleVersion.version.desc()
            )
        )
        result = await session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def _eligible_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        date_from: date,
        date_to: date,
    ) -> list[ProblemEntityCandidate]:
        candidates: dict[int, ProblemEntityCandidate] = {}
        for model in (MartSKUDaily, MartStockDaily):
            stmt = (
                select(model.nm_id, func.max(model.vendor_code).label("vendor_code"))
                .where(
                    model.account_id == account_id,
                    model.nm_id.is_not(None),
                    model.stat_date >= date_from,
                    model.stat_date <= date_to,
                )
                .group_by(model.nm_id)
            )
            result = await session.execute(stmt)
            for nm_id, vendor_code in result.all():
                if nm_id is None:
                    continue
                current = candidates.get(int(nm_id))
                candidates[int(nm_id)] = ProblemEntityCandidate(
                    account_id=account_id,
                    nm_id=int(nm_id),
                    vendor_code=str(vendor_code)
                    if vendor_code is not None
                    else current.vendor_code
                    if current
                    else None,
                )
        return list(candidates.values())

    async def _vendor_code_for_product(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        nm_id: int,
        date_from: date,
        date_to: date,
    ) -> str | None:
        for model in (MartSKUDaily, MartStockDaily):
            result = await session.execute(
                select(model.vendor_code)
                .where(
                    model.account_id == account_id,
                    model.nm_id == nm_id,
                    model.stat_date >= date_from,
                    model.stat_date <= date_to,
                    model.vendor_code.is_not(None),
                )
                .order_by(model.stat_date.desc(), model.id.desc())
                .limit(1)
            )
            value = result.scalar_one_or_none()
            if value:
                return str(value)
        return None

    async def _find_existing_instance(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        problem_code: str,
        entity_type: str,
        entity_id: str,
        dedup_key: str,
    ) -> ProblemInstance | None:
        stmt: Select[tuple[ProblemInstance]] = select(ProblemInstance).where(
            ProblemInstance.account_id == account_id,
            ProblemInstance.problem_code == problem_code,
            ProblemInstance.entity_type == entity_type,
            ProblemInstance.entity_id == entity_id,
            ProblemInstance.dedup_key == dedup_key,
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()

    def _metric_codes_for_rule(self, rule: ProblemRuleVersion) -> list[str]:
        codes: set[str] = set()
        for expression in (
            rule.condition_json,
            rule.impact_formula_json,
            rule.severity_formula_json,
            rule.confidence_formula_json,
            self._resolved_when(rule),
        ):
            self._collect_metric_codes(expression, codes)
        return sorted(codes)

    def _collect_metric_codes(self, node: Any, codes: set[str]) -> None:
        if isinstance(node, dict):
            if set(node.keys()) == {"metric"} and isinstance(node.get("metric"), str):
                codes.add(str(node["metric"]))
                return
            if set(node.keys()) == {"missing"}:
                raw_args = node.get("missing")
                if isinstance(raw_args, list):
                    for item in raw_args:
                        if isinstance(item, str):
                            codes.add(item)
                        else:
                            self._collect_metric_codes(item, codes)
                return
            for value in node.values():
                self._collect_metric_codes(value, codes)
        elif isinstance(node, list):
            for item in node:
                self._collect_metric_codes(item, codes)

    def _render_values(
        self,
        *,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        candidate: ProblemEntityCandidate,
        resolved: ProductMetricResolution,
        impact: Decimal | None,
        severity: str,
        confidence: str | None,
        trust_state: str,
        dedup_key: str | None,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "account_id": candidate.account_id,
            "nm_id": candidate.nm_id,
            "vendor_code": candidate.vendor_code,
            "problem_code": definition.problem_code,
            "rule_version": rule.version,
            "severity": severity,
            "impact": impact,
            "impact_amount": impact,
            "confidence": confidence,
            "trust_state": trust_state,
            "dedup_key": dedup_key,
        }
        for metric_code, metric in resolved.metrics.items():
            values[metric_code] = metric.value
        return values

    def _calculation_snapshot(
        self,
        *,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        candidate: ProblemEntityCandidate,
        resolved: ProductMetricResolution,
        condition: ConditionEvaluationResult,
        impact: NumericFormulaEvaluationResult,
        severity: FormulaEvaluationResult,
        confidence: FormulaEvaluationResult,
        matched: bool,
        create_blocker: bool,
        generated_at: datetime,
    ) -> dict[str, Any]:
        return jsonable_encoder(
            {
                "problem_code": definition.problem_code,
                "rule_version_id": rule.id,
                "rule_version": rule.version,
                "account_id": candidate.account_id,
                "nm_id": candidate.nm_id,
                "matched": matched,
                "create_blocker": create_blocker,
                "generated_at": generated_at,
                "metrics": {
                    code: {
                        "value": metric.value,
                        "value_type": metric.value_type,
                        "unit": metric.unit,
                        "trust_state": metric.trust_state,
                        "is_missing": metric.is_missing,
                        "missing_reason": metric.missing_reason,
                    }
                    for code, metric in resolved.metrics.items()
                },
                "missing_metrics": list(resolved.missing_metrics),
                "condition": self._diagnostic_snapshot(condition),
                "impact": self._diagnostic_snapshot(impact),
                "severity": self._diagnostic_snapshot(severity),
                "confidence": self._diagnostic_snapshot(confidence),
            }
        )

    def _allowed_actions_for_instance(
        self,
        definition: ProblemDefinition,
        *,
        price_safety: PriceSafetyResult | None,
    ) -> list[str]:
        raw = getattr(definition, "allowed_actions_json", None)
        base = (
            [str(item) for item in raw if str(item).strip()]
            if isinstance(raw, list)
            else []
        )
        return self.price_safety_calculator.allowed_actions(
            base_actions=base, price_safety=price_safety
        )

    @staticmethod
    def _diagnostic_snapshot(result: Any) -> dict[str, Any]:
        return {
            "value": getattr(result, "value", None),
            "missing_metrics": list(getattr(result, "missing_metrics", []) or []),
            "warnings": list(getattr(result, "warnings", []) or []),
            "error": getattr(result, "error", None),
        }

    def _preview_from_payload(
        self,
        payload: ProblemInstanceCreate,
        *,
        matched: bool,
        action: str,
        existing: ProblemInstance | None,
    ) -> ProblemEvaluationPreview:
        return ProblemEvaluationPreview(
            account_id=payload.account_id,
            nm_id=int(payload.nm_id or 0),
            problem_code=payload.problem_code,
            dedup_key=payload.dedup_key,
            matched=matched,
            action=action,
            status=existing.status
            if existing is not None and action == "preview_preserve"
            else payload.status,
            title=payload.title,
            explanation=payload.explanation,
            recommendation=payload.recommendation,
            severity=payload.severity,
            impact_type=payload.impact_type,
            money_impact_amount=payload.money_impact_amount,
            confidence=payload.confidence,
            trust_state=payload.trust_state,
            evidence_ledger_json=payload.evidence_ledger_json,
            calculation_snapshot_json=payload.calculation_snapshot_json,
            missing_metrics=list(
                payload.evidence_ledger_json.get("missing_data") or []
            ),
            warnings=list(
                payload.evidence_ledger_json.get("calculation_warnings") or []
            ),
            existing_instance_id=existing.id if existing is not None else None,
        )

    def _preview_from_instance(
        self, instance: ProblemInstance, *, matched: bool, action: str
    ) -> ProblemEvaluationPreview:
        return ProblemEvaluationPreview(
            account_id=instance.account_id,
            nm_id=int(instance.nm_id or 0),
            problem_code=instance.problem_code,
            dedup_key=instance.dedup_key,
            matched=matched,
            action=action,
            status=instance.status,
            title=instance.title,
            explanation=instance.explanation,
            recommendation=instance.recommendation,
            severity=instance.severity,
            impact_type=instance.impact_type,
            money_impact_amount=instance.money_impact_amount,
            confidence=instance.confidence,
            trust_state=instance.trust_state,
            evidence_ledger_json=dict(instance.evidence_ledger_json or {}),
            calculation_snapshot_json=dict(instance.calculation_snapshot_json or {}),
            missing_metrics=list(
                (instance.evidence_ledger_json or {}).get("missing_data") or []
            ),
            warnings=list(
                (instance.evidence_ledger_json or {}).get("calculation_warnings") or []
            ),
            existing_instance_id=instance.id,
        )

    @staticmethod
    def _apply_payload(
        instance: ProblemInstance, payload: ProblemInstanceCreate
    ) -> None:
        old_first_seen = instance.first_seen_at
        for key, value in payload.model_dump().items():
            if key == "first_seen_at":
                continue
            setattr(instance, key, value)
        instance.first_seen_at = old_first_seen

    @staticmethod
    def _add_history(
        session: AsyncSession,
        instance: ProblemInstance,
        event_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
    ) -> None:
        session.add(
            ProblemInstanceHistory(
                problem_instance_id=instance.id,
                event_type=event_type,
                old_value_json=jsonable_encoder(old_value),
                new_value_json=jsonable_encoder(new_value),
            )
        )

    @staticmethod
    def _add_notification(
        session: AsyncSession,
        instance: ProblemInstance,
        *,
        notification_type: str,
        message: str,
        outcome: str = "pending",
        payload: dict[str, Any] | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        session.add(
            ResultEvent(
                account_id=instance.account_id,
                problem_instance_id=instance.id,
                problem_code=instance.problem_code,
                source_module="action_center_notifications",
                source_id=str(instance.id),
                external_id=str(instance.id),
                nm_id=instance.nm_id,
                vendor_code=instance.vendor_code,
                event_type="action_center_notification",
                status="new",
                message=message,
                payload_json={
                    **jsonable_encoder(payload or {}),
                    "notification_type": notification_type,
                    "outcome": outcome,
                    "actor_user_id": actor_user_id,
                    "severity": instance.severity,
                    "impact_type": instance.impact_type,
                    "trust_state": instance.trust_state,
                    "saved_money_claimed": False,
                },
            )
        )

    @staticmethod
    def _merge_result(
        target: ProblemEvaluationResult, source: ProblemEvaluationResult
    ) -> None:
        target.evaluated_count += source.evaluated_count
        target.matched_count += source.matched_count
        target.created_count += source.created_count
        target.updated_count += source.updated_count
        target.resolved_count += source.resolved_count
        target.candidate_resolved_count += source.candidate_resolved_count
        target.skipped_count += source.skipped_count
        target.previews.extend(source.previews)
        target.instances.extend(source.instances)
        target.warnings.extend(source.warnings)

    @staticmethod
    def _severity_from(value: Any, *, default: str) -> str:
        normalized = str(value or default).strip().lower()
        return normalized if normalized in SEVERITIES else default

    @staticmethod
    def _confidence_from(value: Any) -> str | None:
        if value is None:
            return None
        return str(value).strip() or None

    @staticmethod
    def _trust_state_from(confidence: str | None, *, default: str) -> str:
        normalized = str(confidence or "").strip().lower()
        if normalized in TRUST_STATES:
            return normalized
        return default if default in TRUST_STATES else "provisional"

    @staticmethod
    def _impact_type_from(value: str) -> str:
        return value if value in IMPACT_TYPES else "system_warning"

    @staticmethod
    def _money_currency(rule: ProblemRuleVersion) -> str | None:
        template = rule.evidence_template_json or {}
        return str(template.get("money_currency") or template.get("currency") or "RUB")

    @staticmethod
    def _solve_map_template(rule: ProblemRuleVersion) -> dict[str, Any] | None:
        template = rule.evidence_template_json or {}
        raw = template.get("solve_map_template") or template.get("solve_map")
        return dict(raw) if isinstance(raw, dict) else None

    @staticmethod
    def _formula_human(rule: ProblemRuleVersion, definition: ProblemDefinition) -> str:
        template = rule.evidence_template_json or {}
        return str(
            template.get("formula_human")
            or f"{definition.problem_code} rule v{rule.version}"
        )

    @staticmethod
    def _recheck_rule_human(rule: ProblemRuleVersion) -> str:
        recheck = rule.recheck_rule_json or {}
        template = rule.evidence_template_json or {}
        return str(
            template.get("recheck_rule_human")
            or recheck.get("human")
            or recheck.get("description")
            or "Refresh metric sources and re-run this dynamic rule."
        )

    @staticmethod
    def _missing_metrics_create_blocker(
        definition: ProblemDefinition, rule: ProblemRuleVersion
    ) -> bool:
        for payload in (
            rule.recheck_rule_json or {},
            rule.evidence_template_json or {},
        ):
            if (
                payload.get("create_data_blocker_on_missing") is False
                or payload.get("create_data_blocker") is False
            ):
                return False
            policy = (
                str(
                    payload.get("missing_metrics_policy")
                    or payload.get("on_missing_metrics")
                    or ""
                )
                .strip()
                .lower()
            )
            if policy in {"condition_only", "skip", "do_not_create"}:
                return False
        if (
            definition.impact_type_default == "data_blocker"
            or definition.trust_state_default == "blocked"
        ):
            return True
        for payload in (
            rule.recheck_rule_json or {},
            rule.evidence_template_json or {},
        ):
            if (
                payload.get("create_data_blocker") is True
                or payload.get("create_data_blocker_on_missing") is True
            ):
                return True
            policy = (
                str(
                    payload.get("missing_metrics_policy")
                    or payload.get("on_missing_metrics")
                    or ""
                )
                .strip()
                .lower()
            )
            if policy in {"data_blocker", "blocker", "create_data_blocker"}:
                return True
            nested = payload.get("missing_metrics")
            if isinstance(nested, dict) and nested.get("create_data_blocker") is True:
                return True
        return False

    @staticmethod
    def _initial_status(*, impact_type: str, rule: ProblemRuleVersion) -> str:
        configured = str(
            (rule.recheck_rule_json or {}).get("initial_status") or ""
        ).strip()
        if configured:
            return configured
        return "blocked" if impact_type == "data_blocker" else "new"

    @staticmethod
    def _reopen_preserved_status(rule: ProblemRuleVersion, status: str) -> bool:
        recheck = rule.recheck_rule_json or {}
        if recheck.get("reopen_on_match") is True:
            return True
        if str(recheck.get("on_match") or "").strip().lower() == "reopen":
            return True
        statuses = recheck.get("reopen_statuses")
        return isinstance(statuses, list) and status in {str(item) for item in statuses}

    @staticmethod
    def _candidate_resolved(rule: ProblemRuleVersion) -> bool:
        recheck = rule.recheck_rule_json or {}
        mode = (
            str(recheck.get("resolve_mode") or recheck.get("on_resolved") or "")
            .strip()
            .lower()
        )
        return mode == "candidate_resolved" or recheck.get("candidate_resolved") is True

    @staticmethod
    def _price_safety_resolves_negative_profit(
        problem_code: str, price_safety: PriceSafetyResult | None
    ) -> bool:
        return (
            str(problem_code or "").strip().lower() == "negative_unit_profit"
            and price_safety is not None
            and price_safety.status == "price_ok"
            and not price_safety.can_recommend_price_increase
        )

    @staticmethod
    def _resolved_when(rule: ProblemRuleVersion) -> dict[str, Any] | None:
        recheck = rule.recheck_rule_json or {}
        expression = recheck.get("resolved_when")
        return expression if isinstance(expression, dict) else None

    @staticmethod
    def _diagnostic_warnings(*results: Any) -> list[str]:
        warnings: list[str] = []
        for result in results:
            if result is None:
                continue
            warnings.extend(
                str(warning) for warning in (getattr(result, "warnings", []) or [])
            )
            error = getattr(result, "error", None)
            if error:
                warnings.append(str(error))
        deduped: list[str] = []
        for warning in warnings:
            if warning not in deduped:
                deduped.append(warning)
        return deduped
