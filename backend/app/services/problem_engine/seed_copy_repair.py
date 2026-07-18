from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problem_engine import (
    ProblemDefinition,
    ProblemInstance,
    ProblemRuleVersion,
)
from app.services.problem_engine.evaluator import ProblemTemplateRenderer
from app.services.problem_engine.problem_seeds import (
    INITIAL_PROBLEM_DEFINITION_SEEDS,
    INITIAL_PROBLEM_RULE_SEEDS,
    OLD_SEEDED_DEFINITION_TEMPLATES,
)


OPEN_INSTANCE_STATUSES = {
    "new",
    "acknowledged",
    "in_progress",
    "postponed",
    "blocked",
    "reopened",
}


OLD_SEEDED_RULE_COPY: dict[str, dict[str, Any]] = {
    "missing_cost_blocks_profit": {
        "recheck": "Re-run after cost mapping/upload or when the product no longer has revenue in the window.",
        "formula": "cost_price is missing AND revenue_30d > 0",
        "evidence_recheck": "Upload/map cost or re-run after revenue changes.",
        "trust_notes": [
            "Negative profit is intentionally not evaluated while cost data is missing."
        ],
    },
    "negative_unit_profit": {
        "recheck": "Re-run after price, cost, ads, promo, logistics, or margin data changes.",
        "formula": "cost_price exists AND (unit_profit < 0 OR margin_pct < 10)",
        "evidence_recheck": "Re-run after price, cost, ads, promo, logistics, or margin changes.",
        "trust_notes": [
            "This rule is blocked when cost_price is missing; missing_cost_blocks_profit should trigger instead."
        ],
    },
    "overstock_slow_moving": {
        "recheck": "Re-run after stock, sales velocity, or cost data changes.",
        "formula": "stock_qty > 50 AND days_of_stock > 60 AND avg_daily_sales_14d < 2; blocked_cash = max(stock_qty - 50, 0) * cost_price",
        "evidence_recheck": "Re-run after stock, sales velocity, or cost updates.",
    },
    "low_stock_risk": {
        "recheck": "Re-run after stock, supply, or sales velocity updates.",
        "formula": "days_of_stock < 7 AND avg_daily_sales_7d > 1; lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)",
        "evidence_recheck": "Re-run after stock, supply, or sales velocity updates.",
    },
    "ads_spend_without_profit": {
        "recheck": "Re-run after ads spend, bid, price, or profit data changes.",
        "formula": "ad_spend_7d > 500 AND unit_profit_after_ads < 0; probable_loss = abs(unit_profit_after_ads) * units_sold_7d",
        "evidence_recheck": "Re-run after ads spend, bid, price, or profit changes.",
    },
    "promo_not_profitable": {
        "recheck": "Re-run after promo spend, price, cost, or margin data changes.",
        "formula": "cost_price exists AND promo_spend_30d > 0 AND (unit_profit < 0 OR margin_pct < 10)",
        "evidence_recheck": "Re-run after promo spend, price, cost, or margin changes.",
        "trust_notes": [
            "Promo recommendations are bounded by price-safety unit economics."
        ],
    },
    "price_below_safe_margin": {
        "recheck": "Re-run after price, cost, fee, or margin data changes.",
        "formula": "cost_price exists AND price_after_discount > 0 AND margin_pct < 10",
        "evidence_recheck": "Re-run after price, cost, fee, or margin changes.",
        "trust_notes": [
            "Target price is calculated from cost plus commission, logistics, acquiring, and storage."
        ],
    },
    "dead_stock": {
        "recheck": "Re-run after stock, sales, or cost data changes.",
        "formula": "stock_qty > 0 AND sales_30d = 0 AND days_of_stock > 90; blocked_cash = stock_qty * cost_price",
        "evidence_recheck": "Re-run after stock, sales, or cost changes.",
    },
    "fast_stock_depletion": {
        "recheck": "Re-run after stock, supply, or sales velocity updates.",
        "formula": "days_of_stock < 3 AND avg_daily_sales_7d > 2; lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)",
        "evidence_recheck": "Re-run after stock, supply, or sales velocity updates.",
    },
}


@dataclass(slots=True)
class ProblemSeedCopyRepairResult:
    definitions_marked: int = 0
    definitions_updated: int = 0
    rules_marked: int = 0
    rules_updated: int = 0
    instances_updated: int = 0


class DynamicProblemSeedCopyRepairService:
    """Repair seller-facing copy for built-in dynamic problem rules.

    The service is intentionally narrow: it only accepts known built-in problem
    codes, only marks rows whose ownership and old/new seed copy identify them
    as system rows, and updates instance text field-by-field when the field still
    equals an old or current seeded rendering.
    """

    def __init__(
        self, *, template_renderer: ProblemTemplateRenderer | None = None
    ) -> None:
        self.template_renderer = template_renderer or ProblemTemplateRenderer()
        self.definition_seeds = {
            seed.problem_code: seed for seed in INITIAL_PROBLEM_DEFINITION_SEEDS
        }
        self.rule_seeds = {
            seed.problem_code: seed for seed in INITIAL_PROBLEM_RULE_SEEDS
        }

    async def repair(self, session: AsyncSession) -> ProblemSeedCopyRepairResult:
        result = ProblemSeedCopyRepairResult()
        system_definition_ids = await self._repair_definitions(session, result)
        await self._repair_rules(
            session, result, system_definition_ids=system_definition_ids
        )
        await session.flush()
        await self._repair_instances(
            session, result, system_definition_ids=system_definition_ids
        )
        await session.flush()
        return result

    async def _repair_definitions(
        self,
        session: AsyncSession,
        result: ProblemSeedCopyRepairResult,
    ) -> set[int]:
        stmt = select(ProblemDefinition).where(
            ProblemDefinition.problem_code.in_(self.definition_seeds)
        )
        definitions = list((await session.execute(stmt)).scalars())
        system_definition_ids: set[int] = set()
        for definition in definitions:
            seed = self.definition_seeds.get(definition.problem_code)
            if seed is None or not self._is_seed_definition_candidate(definition, seed):
                continue
            if not bool(getattr(definition, "is_system_seeded", False)):
                definition.is_system_seeded = True
                result.definitions_marked += 1
            changed = False
            for attr, value in (
                ("title_template", seed.title_template),
                ("description_template", seed.description_template),
                ("recommendation_template", seed.recommendation_template),
            ):
                if getattr(definition, attr) != value:
                    setattr(definition, attr, value)
                    changed = True
            if changed:
                result.definitions_updated += 1
            if definition.id is not None:
                system_definition_ids.add(int(definition.id))
        await session.flush()
        return system_definition_ids

    async def _repair_rules(
        self,
        session: AsyncSession,
        result: ProblemSeedCopyRepairResult,
        *,
        system_definition_ids: set[int],
    ) -> None:
        if not system_definition_ids:
            return
        stmt = (
            select(ProblemRuleVersion, ProblemDefinition)
            .join(
                ProblemDefinition,
                ProblemDefinition.id == ProblemRuleVersion.problem_definition_id,
            )
            .where(ProblemRuleVersion.problem_definition_id.in_(system_definition_ids))
        )
        rows = list((await session.execute(stmt)).all())
        for rule, definition in rows:
            seed = self.rule_seeds.get(definition.problem_code)
            if seed is None:
                continue
            if not self._is_seed_rule_candidate(rule, seed):
                continue
            if not bool(getattr(rule, "is_system_seeded", False)):
                rule.is_system_seeded = True
                result.rules_marked += 1

            changed = False
            recheck = dict(rule.recheck_rule_json or {})
            target_recheck = str(seed.recheck_rule_json.get("human") or "")
            if target_recheck and recheck.get("human") != target_recheck:
                recheck["human"] = target_recheck
                rule.recheck_rule_json = recheck
                changed = True

            evidence = dict(rule.evidence_template_json or {})
            seed_evidence = dict(seed.evidence_template_json or {})
            for key in ("formula_human", "recheck_rule_human"):
                target = seed_evidence.get(key)
                if isinstance(target, str) and target and evidence.get(key) != target:
                    evidence[key] = target
                    changed = True
            if "trust_notes" in seed_evidence:
                target_notes = list(seed_evidence.get("trust_notes") or [])
                if evidence.get("trust_notes") != target_notes:
                    evidence["trust_notes"] = target_notes
                    changed = True
            elif "trust_notes" in evidence and self._looks_like_english_notes(
                evidence.get("trust_notes")
            ):
                evidence.pop("trust_notes", None)
                changed = True
            if changed:
                rule.evidence_template_json = evidence
                result.rules_updated += 1

    async def _repair_instances(
        self,
        session: AsyncSession,
        result: ProblemSeedCopyRepairResult,
        *,
        system_definition_ids: set[int],
    ) -> None:
        if not system_definition_ids:
            return
        stmt = (
            select(ProblemInstance, ProblemDefinition, ProblemRuleVersion)
            .join(
                ProblemDefinition,
                ProblemDefinition.id == ProblemInstance.problem_definition_id,
            )
            .join(
                ProblemRuleVersion,
                ProblemRuleVersion.id == ProblemInstance.rule_version_id,
            )
            .where(
                ProblemInstance.problem_definition_id.in_(system_definition_ids),
                ProblemInstance.problem_code.in_(self.definition_seeds),
            )
        )
        rows = list((await session.execute(stmt)).all())
        for instance, definition, rule in rows:
            if str(instance.status or "") not in OPEN_INSTANCE_STATUSES:
                continue
            if str(instance.source_module or "") != "problem_engine":
                continue
            if not bool(getattr(definition, "is_system_seeded", False)):
                continue
            if not bool(getattr(rule, "is_system_seeded", False)):
                continue

            seed = self.definition_seeds.get(instance.problem_code)
            old_templates = OLD_SEEDED_DEFINITION_TEMPLATES.get(instance.problem_code)
            if seed is None or old_templates is None:
                continue
            values = self._render_values(instance, rule)
            changed = False
            if self._field_is_seeded(
                instance.title, old_templates[0], seed.title_template, values
            ):
                new_title = self._render(seed.title_template, values)[:255]
                if instance.title != new_title:
                    instance.title = new_title
                    changed = True
            if self._field_is_seeded(
                instance.explanation,
                old_templates[1],
                seed.description_template,
                values,
            ):
                new_explanation = self._render(seed.description_template, values)
                if instance.explanation != new_explanation:
                    instance.explanation = new_explanation
                    changed = True
            if self._field_is_seeded(
                instance.recommendation,
                old_templates[2],
                seed.recommendation_template,
                values,
            ):
                new_recommendation = self._render(seed.recommendation_template, values)
                if instance.recommendation != new_recommendation:
                    instance.recommendation = new_recommendation
                    changed = True

            repaired_ledger = self._repair_evidence_payload(
                instance.evidence_ledger_json, instance.problem_code
            )
            if repaired_ledger is not instance.evidence_ledger_json:
                instance.evidence_ledger_json = repaired_ledger
                changed = True
            if changed:
                result.instances_updated += 1

    def _is_seed_definition_candidate(
        self, definition: ProblemDefinition, seed: Any
    ) -> bool:
        if str(definition.source_module or "") != "problem_engine":
            return False
        if definition.created_by_user_id is not None:
            return False
        if bool(getattr(definition, "is_system_seeded", False)):
            return True
        current = (
            str(definition.title_template or ""),
            str(definition.description_template or ""),
            str(definition.recommendation_template or ""),
        )
        return current == self._template_tuple(
            seed
        ) or current == OLD_SEEDED_DEFINITION_TEMPLATES.get(definition.problem_code)

    def _is_seed_rule_candidate(self, rule: ProblemRuleVersion, seed: Any) -> bool:
        if rule.created_by_user_id is not None:
            return False
        if bool(getattr(rule, "is_system_seeded", False)):
            return True
        if int(rule.version or 0) != int(seed.version):
            return False
        old = OLD_SEEDED_RULE_COPY.get(seed.problem_code)
        if old is None:
            return False
        recheck = dict(rule.recheck_rule_json or {})
        evidence = dict(rule.evidence_template_json or {})
        seed_evidence = dict(seed.evidence_template_json or {})
        return (
            recheck.get("human")
            in {old.get("recheck"), seed.recheck_rule_json.get("human")}
            and evidence.get("formula_human")
            in {old.get("formula"), seed_evidence.get("formula_human")}
            and evidence.get("recheck_rule_human")
            in {old.get("evidence_recheck"), seed_evidence.get("recheck_rule_human")}
        )

    def _render_values(
        self, instance: ProblemInstance, rule: ProblemRuleVersion
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "account_id": instance.account_id,
            "nm_id": instance.nm_id,
            "vendor_code": instance.vendor_code,
            "problem_code": instance.problem_code,
            "rule_version": rule.version,
            "severity": instance.severity,
            "impact": instance.money_impact_amount,
            "impact_amount": instance.money_impact_amount,
            "money_impact_amount": instance.money_impact_amount,
            "confidence": instance.confidence,
            "trust_state": instance.trust_state,
            "dedup_key": instance.dedup_key,
        }
        snapshot = instance.calculation_snapshot_json or {}
        if isinstance(snapshot, dict):
            metrics = snapshot.get("metrics")
            if isinstance(metrics, dict):
                for code, metric in metrics.items():
                    if isinstance(metric, dict):
                        values[str(code)] = metric.get("value")
            if snapshot.get("rule_version") is not None:
                values["rule_version"] = snapshot.get("rule_version")
        return values

    def _field_is_seeded(
        self,
        current: str | None,
        old_template: str,
        new_template: str,
        values: dict[str, Any],
    ) -> bool:
        text = str(current or "").strip()
        if not text:
            return True
        candidates = {
            old_template.strip(),
            new_template.strip(),
            self._render(old_template, values).strip(),
            self._render(new_template, values).strip(),
        }
        return text in candidates

    def _render(self, template: str, values: dict[str, Any]) -> str:
        return self.template_renderer.render(template, values).strip() or str(
            template or ""
        )

    def _repair_evidence_payload(
        self, payload: Any, problem_code: str
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        old = OLD_SEEDED_RULE_COPY.get(problem_code)
        seed = self.rule_seeds.get(problem_code)
        if old is None or seed is None:
            return payload
        repaired = dict(payload)
        seed_evidence = dict(seed.evidence_template_json or {})
        changed = False
        for current_key, old_key, seed_key in (
            ("formula_human", "formula", "formula_human"),
            ("recheck_rule_human", "evidence_recheck", "recheck_rule_human"),
        ):
            target = seed_evidence.get(seed_key)
            if isinstance(target, str) and repaired.get(current_key) in {
                old.get(old_key),
                target,
                None,
                "",
            }:
                if repaired.get(current_key) != target:
                    repaired[current_key] = target
                    changed = True
        if "trust_notes" in seed_evidence:
            target_notes = list(seed_evidence.get("trust_notes") or [])
            current_notes = repaired.get("trust_notes")
            if (
                current_notes is None
                or current_notes == old.get("trust_notes")
                or current_notes == target_notes
            ):
                if current_notes != target_notes:
                    repaired["trust_notes"] = target_notes
                    changed = True
        elif "trust_notes" in repaired and self._looks_like_english_notes(
            repaired.get("trust_notes")
        ):
            repaired.pop("trust_notes", None)
            changed = True
        return repaired if changed else payload

    @staticmethod
    def _template_tuple(seed: Any) -> tuple[str, str, str]:
        return (
            str(seed.title_template),
            str(seed.description_template),
            str(seed.recommendation_template),
        )

    @staticmethod
    def _looks_like_english_notes(value: Any) -> bool:
        if not isinstance(value, list):
            return False
        notes = [str(item or "").strip() for item in value if str(item or "").strip()]
        return bool(notes) and all(
            any("a" <= char.lower() <= "z" for char in note)
            and not any("а" <= char.lower() <= "я" or char == "ё" for char in note)
            for note in notes
        )
