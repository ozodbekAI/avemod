from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.models.data_quality import DataQualityIssue
from app.models.problem_engine import (
    ProblemDefinition,
    ProblemInstance,
    ProblemInstanceHistory,
    ProblemRuleVersion,
)
from app.schemas.data_quality import (
    DataQualityIssueRead,
    GuidedFixDefinition,
    issue_resolution_guide,
)
from app.schemas.problem_engine import ProblemInstanceCreate


@dataclass(frozen=True, slots=True)
class DataFixProblemMapping:
    issue_codes: tuple[str, ...]
    problem_code: str
    category: str
    impact_type: str
    trust_state: str
    severity: str
    title: str
    description: str
    recommendation: str
    allowed_actions: tuple[str, ...]


DATA_FIX_PROBLEM_MAPPINGS: tuple[DataFixProblemMapping, ...] = (
    DataFixProblemMapping(
        issue_codes=("missing_manual_cost", "missing_cost_blocks_profit"),
        problem_code="missing_cost_blocks_profit",
        category="data_quality",
        impact_type="data_blocker",
        trust_state="blocked",
        severity="critical",
        title="Нет себестоимости, прибыль не считается",
        description="По товару есть выручка, но себестоимость не заполнена. Поэтому прибыль и маржа пока не считаются надёжно.",
        recommendation="Загрузите или сопоставьте себестоимость, затем запустите повторную проверку прибыльности.",
        allowed_actions=("upload_cost", "map_sku", "create_task", "recheck", "dismiss"),
    ),
    DataFixProblemMapping(
        issue_codes=("manual_cost_unresolved_sku",),
        problem_code="manual_cost_unresolved_sku",
        category="data_quality",
        impact_type="data_blocker",
        trust_state="blocked",
        severity="high",
        title="Строка себестоимости не привязана к SKU",
        description="Строка ручной себестоимости пока не связана с надёжным SKU товара.",
        recommendation="Привяжите строку себестоимости ровно к одному SKU, затем перепроверьте прибыльность.",
        allowed_actions=("map_sku", "upload_cost", "create_task", "recheck", "dismiss"),
    ),
    DataFixProblemMapping(
        issue_codes=("manual_cost_ambiguous_match",),
        problem_code="manual_cost_ambiguous_match",
        category="data_quality",
        impact_type="data_blocker",
        trust_state="blocked",
        severity="high",
        title="У строки себестоимости несколько возможных SKU",
        description="Строка ручной себестоимости подходит к нескольким SKU и требует подтверждения.",
        recommendation="Выберите правильный SKU по исходным идентификаторам, прежде чем доверять прибыли.",
        allowed_actions=("map_sku", "upload_cost", "create_task", "recheck", "dismiss"),
    ),
    DataFixProblemMapping(
        issue_codes=("unmatched_sku", "unmatched_sku_detected"),
        problem_code="unmatched_sku",
        category="data_quality",
        impact_type="data_blocker",
        trust_state="blocked",
        severity="high",
        title="Источник не сопоставлен с каталогом",
        description="В продажах, остатках или себестоимости есть идентификатор, который не привязан к SKU каталога.",
        recommendation="Сопоставьте исходный идентификатор с SKU каталога после проверки nmID, баркода и артикула продавца.",
        allowed_actions=("map_sku", "create_task", "recheck", "dismiss"),
    ),
    DataFixProblemMapping(
        issue_codes=("expense_unclassified", "unclassified_finance_expense"),
        problem_code="expense_unclassified",
        category="data_quality",
        impact_type="data_blocker",
        trust_state="blocked",
        severity="high",
        title="Расход не классифицирован",
        description="У финансового расхода нет надёжной категории, поэтому прибыль может быть неполной.",
        recommendation="Назначьте категорию расхода, не меняя исходную сумму WB.",
        allowed_actions=("classify_expense", "create_task", "recheck", "dismiss"),
    ),
    DataFixProblemMapping(
        issue_codes=("sale_without_finance",),
        problem_code="sale_without_finance",
        category="data_quality",
        impact_type="system_warning",
        trust_state="provisional",
        severity="medium",
        title="Продажа ждёт финансовую строку",
        description="Продажа есть, но соответствующая строка финансового отчёта WB ещё не пришла или не сопоставилась.",
        recommendation="Дождитесь следующего финансового отчёта WB или перезапустите синхронизацию. Не правьте продажи и финансы вручную.",
        allowed_actions=("recheck", "create_task", "dismiss"),
    ),
    DataFixProblemMapping(
        issue_codes=("finance_without_sale",),
        problem_code="finance_without_sale",
        category="data_quality",
        impact_type="system_warning",
        trust_state="provisional",
        severity="medium",
        title="Финансовая строка ждёт продажу",
        description="Финансовая строка WB есть, но соответствующая операционная продажа или заказ ещё не сопоставились.",
        recommendation="Перезапустите синхронизацию продаж/заказов или передайте администратору. Финансовые факты WB остаются только для чтения.",
        allowed_actions=("recheck", "create_task", "dismiss"),
    ),
)

_MAPPING_BY_ISSUE_CODE = {
    issue_code: mapping
    for mapping in DATA_FIX_PROBLEM_MAPPINGS
    for issue_code in mapping.issue_codes
}

USER_DECISION_STATUSES = {"ignored", "postponed", "in_progress", "done", "dismissed"}
ACTIVE_DYNAMIC_STATUSES = {
    "new",
    "acknowledged",
    "in_progress",
    "postponed",
    "blocked",
    "reopened",
}


class DataFixProblemBridge:
    """Mirror actionable Data Fix blockers into Dynamic Problem instances."""

    def mapping_for_issue(
        self, issue: DataQualityIssue
    ) -> DataFixProblemMapping | None:
        return _MAPPING_BY_ISSUE_CODE.get(str(issue.code or "").strip().lower())

    @staticmethod
    def _issue_classification_status(issue: DataQualityIssue) -> str:
        payload = dict(issue.payload or {})
        return (
            str(
                getattr(issue, "classification_status", None)
                or payload.get("classificationStatus")
                or payload.get("resolutionStatus")
                or ""
            )
            .strip()
            .lower()
        )

    @staticmethod
    def _is_supply_source_unmatched(issue: DataQualityIssue) -> bool:
        if str(issue.code or "").strip().lower() != "unmatched_sku":
            return False
        payload = dict(issue.payload or {})
        source_kind = str(payload.get("sourceKind") or "").strip().lower()
        source_domains = {
            str(item).strip().lower()
            for item in (payload.get("sourceDomains") or [])
            if str(item).strip()
        }
        classification_reason = (
            str(payload.get("classificationReason") or "").strip().lower()
        )
        return (
            source_kind == "source_level"
            and source_domains == {"supplies"}
            and classification_reason in {"missing_nm_id", "source_level_missing_nm_id"}
        )

    def _should_close_without_action(self, issue: DataQualityIssue) -> bool:
        if issue.resolved_at is not None:
            return True
        if self._issue_classification_status(issue) in {
            "archived",
            "ignored",
            "ignored_with_reason",
            "ignored_non_financial",
            "known_exception",
        }:
            return True
        return self._is_supply_source_unmatched(issue)

    async def sync_issue(
        self,
        session: AsyncSession,
        issue: DataQualityIssue,
        *,
        guided_definition: GuidedFixDefinition | None = None,
    ) -> ProblemInstance | None:
        mapping = self.mapping_for_issue(issue)
        if mapping is None or issue.account_id is None:
            return None

        existing = await self._find_existing_instance(
            session, issue=issue, problem_code=mapping.problem_code
        )
        now = utcnow()

        if self._should_close_without_action(issue):
            if existing is None:
                return None
            old_status = existing.status
            existing.status = "resolved"
            existing.resolved_at = issue.resolved_at or now
            existing.last_seen_at = now
            self._add_history(
                session,
                instance=existing,
                event_type="closed_by_data_fix_classification",
                old_value={"status": old_status},
                new_value={
                    "status": "resolved",
                    "data_quality_issue_id": issue.id,
                    "classification_status": self._issue_classification_status(issue),
                },
            )
            await session.flush()
            return existing

        dynamic_duplicate = await self._find_active_dynamic_problem_instance(
            session,
            issue=issue,
            mapping=mapping,
        )
        if dynamic_duplicate is not None:
            if existing is None:
                return None
            old_status = existing.status
            existing.status = "resolved"
            existing.resolved_at = now
            existing.last_seen_at = now
            self._add_history(
                session,
                instance=existing,
                event_type="closed_by_dynamic_problem",
                old_value={"status": old_status},
                new_value={
                    "status": "resolved",
                    "data_quality_issue_id": issue.id,
                    "dynamic_problem_instance_id": dynamic_duplicate.id,
                },
            )
            await session.flush()
            return existing

        definition = await self._ensure_definition(session, mapping)
        rule = await self._ensure_rule_version(
            session, definition, mapping, guided_definition=guided_definition
        )
        payload = self._instance_payload(
            issue=issue,
            mapping=mapping,
            definition=definition,
            rule=rule,
            guided_definition=guided_definition,
            existing=existing,
            now=now,
        )
        if existing is None:
            instance = ProblemInstance(**payload.model_dump())
            session.add(instance)
            await session.flush()
            self._add_history(
                session,
                instance=instance,
                event_type="created_from_data_fix",
                old_value=None,
                new_value={
                    "data_quality_issue_id": issue.id,
                    "problem_code": mapping.problem_code,
                },
            )
            await session.flush()
            return instance

        old_status = existing.status
        self._apply_payload(existing, payload)
        if old_status in USER_DECISION_STATUSES:
            existing.status = old_status
        await session.flush()
        return existing

    async def _ensure_definition(
        self,
        session: AsyncSession,
        mapping: DataFixProblemMapping,
    ) -> ProblemDefinition:
        result = await session.execute(
            select(ProblemDefinition)
            .where(ProblemDefinition.problem_code == mapping.problem_code)
            .limit(1)
        )
        definition = result.scalar_one_or_none()
        if definition is not None:
            return definition
        definition = ProblemDefinition(
            problem_code=mapping.problem_code,
            source_module="data_quality",
            category=mapping.category,
            entity_type="product",
            title_template=mapping.title,
            description_template=mapping.description,
            recommendation_template=mapping.recommendation,
            impact_type_default=mapping.impact_type,
            trust_state_default=mapping.trust_state,
            severity_default=mapping.severity,
            allowed_actions_json=list(mapping.allowed_actions),
            status="active",
        )
        session.add(definition)
        await session.flush()
        return definition

    async def _ensure_rule_version(
        self,
        session: AsyncSession,
        definition: ProblemDefinition,
        mapping: DataFixProblemMapping,
        *,
        guided_definition: GuidedFixDefinition | None,
    ) -> ProblemRuleVersion:
        result = await session.execute(
            select(ProblemRuleVersion)
            .where(
                ProblemRuleVersion.problem_definition_id == definition.id,
                ProblemRuleVersion.version == 1,
            )
            .limit(1)
        )
        rule = result.scalar_one_or_none()
        if rule is not None:
            return rule
        recheck_rule = dict(
            guided_definition.recheck_query if guided_definition else {}
        )
        rule = ProblemRuleVersion(
            problem_definition_id=definition.id,
            version=1,
            status="paused" if definition.source_module == "data_quality" else "active",
            evaluation_grain="product_period",
            lookback_days=30,
            condition_json={"==": [1, 1]},
            impact_formula_json={"case": [{"else": 0}]},
            severity_formula_json={"case": [{"else": mapping.severity}]},
            confidence_formula_json={"case": [{"else": mapping.trust_state}]},
            dedup_key_template="{account_id}:{problem_code}:{source_issue_id}",
            recheck_rule_json={
                "human": recheck_rule.get("rule")
                or "Запустите повторную проверку исправления данных и убедитесь, что исходная проблема закрыта.",
                "source": "data_fix_bridge",
            },
            evidence_template_json={
                "formula_human": f"Проблема исправления данных `{mapping.issue_codes[0]}` открыта и требует действия.",
                "formula_code": f"{mapping.problem_code}.data_fix_bridge.v1",
                "recheck_rule_human": recheck_rule.get("rule")
                or "Запустите повторную проверку исправления данных.",
                "impact_type": mapping.impact_type,
                "confidence": mapping.trust_state,
                "trust_notes": [
                    "Эта проблема создана из исправления данных и перепроверяется правилами качества данных."
                ],
            },
            published_at=datetime.now(UTC),
        )
        session.add(rule)
        await session.flush()
        return rule

    async def _find_existing_instance(
        self,
        session: AsyncSession,
        *,
        issue: DataQualityIssue,
        problem_code: str,
    ) -> ProblemInstance | None:
        stmt = (
            select(ProblemInstance)
            .where(
                ProblemInstance.account_id == issue.account_id,
                ProblemInstance.problem_code == problem_code,
                ProblemInstance.dedup_key
                == self._dedup_key(issue=issue, problem_code=problem_code),
            )
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    async def _find_active_dynamic_problem_instance(
        self,
        session: AsyncSession,
        *,
        issue: DataQualityIssue,
        mapping: DataFixProblemMapping,
    ) -> ProblemInstance | None:
        if mapping.problem_code != "missing_cost_blocks_profit":
            return None
        if str(issue.code or "").strip().lower() not in {
            "missing_manual_cost",
            "missing_cost_blocks_profit",
        }:
            return None
        if issue.nm_id is None:
            return None
        stmt = (
            select(ProblemInstance)
            .where(
                ProblemInstance.account_id == issue.account_id,
                ProblemInstance.problem_code == mapping.problem_code,
                ProblemInstance.nm_id == issue.nm_id,
                ProblemInstance.source_module != "data_quality",
                ProblemInstance.status.in_(ACTIVE_DYNAMIC_STATUSES),
            )
            .order_by(ProblemInstance.last_seen_at.desc(), ProblemInstance.id.desc())
            .limit(1)
        )
        return (await session.execute(stmt)).scalar_one_or_none()

    def _instance_payload(
        self,
        *,
        issue: DataQualityIssue,
        mapping: DataFixProblemMapping,
        definition: ProblemDefinition,
        rule: ProblemRuleVersion,
        guided_definition: GuidedFixDefinition | None,
        existing: ProblemInstance | None,
        now: datetime,
    ) -> ProblemInstanceCreate:
        issue_read = DataQualityIssueRead.from_issue(issue)
        guide = issue_resolution_guide(issue.code, dict(issue.payload or {}))
        ledger = self._ledger_json(
            issue=issue,
            issue_read=issue_read,
            mapping=mapping,
            guided_definition=guided_definition,
        )
        entity_type, entity_id = self._entity_ref(issue)
        status = (
            existing.status
            if existing and existing.status in USER_DECISION_STATUSES
            else self._initial_status(issue, mapping)
        )
        return ProblemInstanceCreate.model_validate(
            {
                "account_id": issue.account_id,
                "problem_code": mapping.problem_code,
                "problem_definition_id": definition.id,
                "rule_version_id": rule.id,
                "source_module": "data_quality",
                "entity_type": entity_type,
                "entity_id": entity_id,
                "nm_id": issue.nm_id,
                "vendor_code": issue_read.vendor_code,
                "dedup_key": self._dedup_key(
                    issue=issue, problem_code=mapping.problem_code
                ),
                "title": issue_read.message or mapping.title,
                "explanation": issue_read.simple_reason
                or issue_read.business_impact
                or guide.get("simple_reason")
                or mapping.description,
                "recommendation": issue_read.first_action
                or issue_read.recommended_fix
                or guide.get("first_action")
                or mapping.recommendation,
                "severity": self._severity(issue, mapping),
                "status": status,
                "impact_type": mapping.impact_type,
                "money_impact_amount": self._money_impact(issue),
                "money_impact_currency": "RUB"
                if self._money_impact(issue) is not None
                else None,
                "trust_state": "blocked"
                if issue_read.effective_financial_final_blocker
                else mapping.trust_state,
                "confidence": "blocked"
                if issue_read.effective_financial_final_blocker
                else mapping.trust_state,
                "evidence_ledger_json": ledger,
                "calculation_snapshot_json": self._calculation_snapshot(
                    issue=issue,
                    issue_read=issue_read,
                    mapping=mapping,
                    guided_definition=guided_definition,
                ),
                "first_seen_at": existing.first_seen_at
                if existing is not None
                else now,
                "last_seen_at": now,
                "resolved_at": None,
                "dismissed_at": existing.dismissed_at if existing is not None else None,
                "dismiss_reason": existing.dismiss_reason
                if existing is not None
                else None,
            }
        )

    def _ledger_json(
        self,
        *,
        issue: DataQualityIssue,
        issue_read: DataQualityIssueRead,
        mapping: DataFixProblemMapping,
        guided_definition: GuidedFixDefinition | None,
    ) -> dict[str, Any]:
        ledger = (
            issue_read.evidence_ledger.model_dump(mode="json")
            if issue_read.evidence_ledger
            else {}
        )
        recheck_rule = str(
            (guided_definition.recheck_query if guided_definition else {}).get("rule")
            or issue_read.wait_or_fix_hint
            or ""
        )
        ledger["formula_human"] = (
            f"Open Data Fix issue `{issue.code}` maps to dynamic problem `{mapping.problem_code}`."
        )
        ledger["formula_code"] = f"{mapping.problem_code}.data_fix_bridge.v1"
        ledger["formula_id"] = f"data_quality_issue:{issue.id}"
        ledger["confidence"] = (
            "blocked"
            if issue_read.effective_financial_final_blocker
            else mapping.trust_state
        )
        ledger["impact_type"] = mapping.impact_type
        ledger["recheck_rule_human"] = (
            recheck_rule
            or "Re-run Data Fix/DQ checks and verify the source issue is closed."
        )
        ledger["recheck_rule"] = ledger["recheck_rule_human"]
        ledger["next_fix_action"] = {
            "label": "Open Data Fix",
            "screen_path": f"/data-fix?code={issue.code}",
            "source_endpoint": f"GET /api/v1/dq/issues/{issue.id}/resolution-context",
            "action_type": issue.code,
        }
        trust_notes = list(ledger.get("trust_notes") or [])
        trust_notes.append(
            "Dynamic problem mirrored from Data Fix; user actions must use the guided fix component."
        )
        if guided_definition and not guided_definition.can_user_fix_inside_platform:
            trust_notes.append(
                "This issue is not user-fixable inside the platform; WB facts remain read-only."
            )
        ledger["trust_notes"] = list(
            dict.fromkeys(str(item) for item in trust_notes if str(item).strip())
        )
        warnings = list(ledger.get("calculation_warnings") or [])
        if guided_definition:
            warnings.extend(str(note) for note in guided_definition.safety_notes)
        ledger["calculation_warnings"] = list(
            dict.fromkeys(str(item) for item in warnings if str(item).strip())
        )
        ledger["data_fix"] = {
            "issue_id": issue.id,
            "issue_code": issue.code,
            "owner_type": guided_definition.owner_type if guided_definition else None,
            "fixability": guided_definition.fixability if guided_definition else None,
            "issue_nature": guided_definition.issue_nature
            if guided_definition
            else None,
            "can_user_fix_inside_platform": guided_definition.can_user_fix_inside_platform
            if guided_definition
            else None,
            "is_manual_edit_allowed": guided_definition.is_manual_edit_allowed
            if guided_definition
            else None,
            "primary_action_code": guided_definition.primary_action_code
            if guided_definition
            else None,
            "primary_action_label": guided_definition.primary_action_label
            if guided_definition
            else None,
            "target_href": guided_definition.target_href if guided_definition else None,
            "disabled_reason": guided_definition.disabled_reason
            if guided_definition
            else None,
            "recheck_mode": guided_definition.recheck_mode
            if guided_definition
            else None,
            "seller_explanation": guided_definition.seller_explanation
            if guided_definition
            else None,
            "admin_explanation": guided_definition.admin_explanation
            if guided_definition
            else None,
            "fix_component_type": guided_definition.fix_component_type
            if guided_definition
            else None,
            "required_inputs": guided_definition.required_inputs
            if guided_definition
            else [],
            "preview_before_change": guided_definition.preview_before_change
            if guided_definition
            else {},
            "apply_action": guided_definition.apply_action if guided_definition else {},
            "recheck_rule": guided_definition.recheck_query
            if guided_definition
            else {},
        }
        return ledger

    def _calculation_snapshot(
        self,
        *,
        issue: DataQualityIssue,
        issue_read: DataQualityIssueRead,
        mapping: DataFixProblemMapping,
        guided_definition: GuidedFixDefinition | None,
    ) -> dict[str, Any]:
        return {
            "source": "data_fix_bridge",
            "data_quality_issue": {
                "id": issue.id,
                "code": issue.code,
                "classification_status": issue_read.classification_status,
                "effective_financial_final_blocker": issue_read.effective_financial_final_blocker,
                "resolved_at": issue.resolved_at.isoformat()
                if issue.resolved_at
                else None,
            },
            "data_fix_contract": {
                "owner_type": guided_definition.owner_type
                if guided_definition
                else None,
                "fixability": guided_definition.fixability
                if guided_definition
                else None,
                "issue_nature": guided_definition.issue_nature
                if guided_definition
                else None,
                "can_user_fix_inside_platform": guided_definition.can_user_fix_inside_platform
                if guided_definition
                else None,
                "is_manual_edit_allowed": guided_definition.is_manual_edit_allowed
                if guided_definition
                else None,
                "primary_action_code": guided_definition.primary_action_code
                if guided_definition
                else None,
                "primary_action_label": guided_definition.primary_action_label
                if guided_definition
                else None,
                "target_href": guided_definition.target_href
                if guided_definition
                else None,
                "disabled_reason": guided_definition.disabled_reason
                if guided_definition
                else None,
                "recheck_mode": guided_definition.recheck_mode
                if guided_definition
                else None,
                "seller_explanation": guided_definition.seller_explanation
                if guided_definition
                else None,
                "admin_explanation": guided_definition.admin_explanation
                if guided_definition
                else None,
                "fix_component_type": guided_definition.fix_component_type
                if guided_definition
                else None,
                "required_inputs": guided_definition.required_inputs
                if guided_definition
                else [],
                "preview_before_change": guided_definition.preview_before_change
                if guided_definition
                else {},
                "apply_action": guided_definition.apply_action
                if guided_definition
                else {},
                "recheck_rule": guided_definition.recheck_query
                if guided_definition
                else {},
            },
            "action_center": {
                "review_status": "new",
                "last_changed_at": utcnow().isoformat(),
            },
            "problem_mapping": {
                "issue_code": issue.code,
                "problem_code": mapping.problem_code,
                "category": mapping.category,
            },
        }

    @staticmethod
    def _apply_payload(
        instance: ProblemInstance, payload: ProblemInstanceCreate
    ) -> None:
        for key, value in payload.model_dump().items():
            if key == "first_seen_at":
                continue
            setattr(instance, key, value)

    @staticmethod
    def _dedup_key(*, issue: DataQualityIssue, problem_code: str) -> str:
        source_key = issue.entity_key or f"issue:{issue.id}"
        return f"{issue.account_id}:{problem_code}:{issue.code}:{source_key}"

    @staticmethod
    def _entity_ref(issue: DataQualityIssue) -> tuple[str, str]:
        if issue.nm_id is not None:
            return "product", str(issue.nm_id)
        if issue.sku_id is not None:
            return "product", f"sku:{issue.sku_id}"
        if (
            issue.entity_type
            in {"product", "account", "campaign", "warehouse", "category"}
            and issue.entity_id is not None
        ):
            return str(issue.entity_type), str(issue.entity_id)
        return "account", str(issue.account_id)

    @staticmethod
    def _severity(issue: DataQualityIssue, mapping: DataFixProblemMapping) -> str:
        severity = str(issue.severity or "").strip().lower()
        if severity in {"critical", "error", "blocker"}:
            return "critical"
        if severity in {"high"}:
            return "high"
        if severity in {"warning"}:
            return "high" if mapping.impact_type == "data_blocker" else "medium"
        if severity in {"low", "info"}:
            return "low"
        return mapping.severity

    @staticmethod
    def _initial_status(issue: DataQualityIssue, mapping: DataFixProblemMapping) -> str:
        if mapping.impact_type == "data_blocker":
            return "blocked"
        return "new"

    @staticmethod
    def _money_impact(issue: DataQualityIssue) -> Decimal | None:
        payload = dict(issue.payload or {})
        for key in (
            "affectedAmount",
            "affected_amount",
            "affectedRevenue",
            "affected_revenue",
            "revenueDelta",
            "forPayDelta",
        ):
            value = payload.get(key)
            if value in (None, ""):
                continue
            try:
                return abs(Decimal(str(value)))
            except (InvalidOperation, TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _add_history(
        session: AsyncSession,
        *,
        instance: ProblemInstance,
        event_type: str,
        old_value: dict[str, Any] | None,
        new_value: dict[str, Any] | None,
    ) -> None:
        session.add(
            ProblemInstanceHistory(
                problem_instance_id=instance.id,
                event_type=event_type,
                old_value_json=old_value,
                new_value_json=new_value,
                comment="Data Fix dynamic problem bridge",
            )
        )
