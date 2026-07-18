from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from app.schemas.evidence import (
    EvidenceDateRange,
    EvidenceInputFact,
    EvidenceLedger,
    EvidenceSourceReference,
)
from app.schemas.problem_engine import ProductMetricResolution
from app.services.problem_engine.formula_evaluator import FormulaEvaluationResult


class EvidenceLedgerBuilder:
    """Build the canonical evidence ledger for generated problem instances."""

    def build_for_problem(
        self,
        *,
        rule_version: Any,
        resolved_metrics: ProductMetricResolution,
        formula_diagnostics: FormulaEvaluationResult
        | dict[str, Any]
        | Iterable[FormulaEvaluationResult | dict[str, Any]]
        | None = None,
        source_references: list[EvidenceSourceReference | dict[str, Any]] | None = None,
        formula_human: str | None = None,
        formula_code: str | None = None,
        formula_id: str | None = None,
        recheck_rule_human: str | None = None,
        trust_notes: list[str] | None = None,
        calculation_warnings: list[str] | None = None,
    ) -> EvidenceLedger:
        template = self._mapping(
            self._get(rule_version, "evidence_template_json") or {}
        )
        recheck_rule = self._mapping(self._get(rule_version, "recheck_rule_json") or {})
        version = self._get(rule_version, "version")
        rule_id = self._get(rule_version, "id")
        definition_id = self._get(rule_version, "problem_definition_id")

        diagnostics = self._diagnostics(formula_diagnostics)
        missing_data = self._missing_data(resolved_metrics, diagnostics)
        warnings = self._dedupe(
            [*(calculation_warnings or []), *diagnostics["warnings"]]
        )
        notes = self._dedupe(
            [
                *(trust_notes or []),
                *list(template.get("trust_notes") or []),
                "Каждый входной факт берётся из каталога метрик; отсутствующие входы перечислены в блоке недостающих данных.",
            ]
        )

        ledger = EvidenceLedger(
            value=diagnostics["value"],
            value_type=self._value_type(diagnostics["value"]),
            confidence=str(template.get("confidence") or "provisional"),
            impact_type=str(template.get("impact_type") or "system_warning"),
            formula_human=formula_human
            or str(
                template.get("formula_human")
                or "Правило проблемы проверило доступные метрики и диагностические результаты формулы."
            ),
            formula_code=formula_code
            or template.get("formula_code")
            or self._formula_code(definition_id=definition_id, version=version),
            formula_id=formula_id
            or template.get("formula_id")
            or self._formula_id(rule_id=rule_id, version=version),
            input_facts=self._input_facts(resolved_metrics),
            source_references=self._source_references(
                resolved_metrics, source_references or []
            ),
            trust_notes=notes,
            missing_data=missing_data,
            recheck_rule_human=recheck_rule_human
            or str(
                template.get("recheck_rule_human")
                or recheck_rule.get("human")
                or recheck_rule.get("description")
                or "Запустите правило повторно после обновления источников метрик."
            ),
            calculation_warnings=warnings,
        )
        ledger.recheck_rule = ledger.recheck_rule_human
        return ledger

    def build_json(
        self,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.build_for_problem(**kwargs).model_dump(mode="json")

    def _input_facts(
        self, resolved_metrics: ProductMetricResolution
    ) -> list[EvidenceInputFact]:
        facts: list[EvidenceInputFact] = []
        for metric_code, metric in resolved_metrics.metrics.items():
            evidence = metric.evidence
            facts.append(
                EvidenceInputFact(
                    label=metric_code.replace("_", " "),
                    metric_code=metric.metric_code,
                    value=metric.value,
                    unit=metric.unit,
                    trust_state=metric.trust_state or "provisional",
                    source=evidence.source_module or evidence.source_service,
                    source_table=evidence.source_table,
                    source_endpoint=evidence.source_endpoint,
                    date_range=EvidenceDateRange(
                        date_from=evidence.date_from, date_to=evidence.date_to
                    ),
                    filters=evidence.filters,
                    row_count=max(0, int(evidence.row_count or 0)),
                    sample_rows=[],
                )
            )
        return facts

    def _source_references(
        self,
        resolved_metrics: ProductMetricResolution,
        explicit_refs: list[EvidenceSourceReference | dict[str, Any]],
    ) -> list[EvidenceSourceReference]:
        refs: list[EvidenceSourceReference] = []
        for metric in resolved_metrics.metrics.values():
            evidence = metric.evidence
            refs.append(
                EvidenceSourceReference(
                    source_table=evidence.source_table,
                    source_endpoint=evidence.source_endpoint,
                    date_range=EvidenceDateRange(
                        date_from=evidence.date_from, date_to=evidence.date_to
                    ),
                    row_count=evidence.row_count,
                    sync_run_id=self._sync_run_id(evidence.freshness),
                    loaded_at=evidence.freshness.get("latest_updated_at")
                    if evidence.freshness
                    else None,
                )
            )
        refs.extend(
            ref
            if isinstance(ref, EvidenceSourceReference)
            else EvidenceSourceReference.model_validate(ref)
            for ref in explicit_refs
        )

        deduped: list[EvidenceSourceReference] = []
        seen: set[tuple[Any, ...]] = set()
        for ref in refs:
            key = (
                ref.source_table,
                ref.source_endpoint,
                ref.date_range.date_from if ref.date_range else None,
                ref.date_range.date_to if ref.date_range else None,
                ref.row_count,
                ref.sync_run_id,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(ref)
        return deduped

    def _missing_data(
        self, resolved_metrics: ProductMetricResolution, diagnostics: dict[str, Any]
    ) -> list[str]:
        missing: list[str] = []
        for metric_code in resolved_metrics.missing_metrics:
            metric = resolved_metrics.metrics.get(metric_code)
            reason = metric.missing_reason if metric else "missing"
            missing.append(f"{metric_code}: {reason}")
        missing.extend(
            f"{metric_code}: missing during formula evaluation"
            for metric_code in diagnostics["missing_metrics"]
        )
        return self._dedupe(missing)

    def _diagnostics(
        self,
        formula_diagnostics: FormulaEvaluationResult
        | dict[str, Any]
        | Iterable[FormulaEvaluationResult | dict[str, Any]]
        | None,
    ) -> dict[str, Any]:
        value: Any = None
        missing_metrics: list[str] = []
        warnings: list[str] = []
        if formula_diagnostics is None:
            return {
                "value": value,
                "missing_metrics": missing_metrics,
                "warnings": warnings,
            }
        items: Iterable[FormulaEvaluationResult | dict[str, Any]]
        if (
            isinstance(formula_diagnostics, FormulaEvaluationResult)
            or isinstance(formula_diagnostics, dict)
            or hasattr(formula_diagnostics, "missing_metrics")
        ):
            items = [formula_diagnostics]
        else:
            items = formula_diagnostics
        for item in items:
            mapping = self._mapping(item)
            if mapping.get("value") is not None:
                value = mapping.get("value")
            missing_metrics.extend(
                str(metric) for metric in (mapping.get("missing_metrics") or [])
            )
            warnings.extend(str(warning) for warning in (mapping.get("warnings") or []))
            if mapping.get("error"):
                warnings.append(str(mapping["error"]))
        return {
            "value": value,
            "missing_metrics": self._dedupe(missing_metrics),
            "warnings": self._dedupe(warnings),
        }

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump"):
            return value.model_dump()
        if hasattr(value, "__dict__"):
            return dict(value.__dict__)
        return {
            "value": getattr(value, "value", None),
            "missing_metrics": getattr(value, "missing_metrics", []),
            "warnings": getattr(value, "warnings", []),
            "error": getattr(value, "error", None),
        }

    @staticmethod
    def _get(value: Any, key: str) -> Any:
        if isinstance(value, dict):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _dedupe(items: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for item in items:
            normalized = str(item)
            if normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _sync_run_id(freshness: dict[str, Any]) -> str | int | None:
        sync_cursor = (freshness or {}).get("sync_cursor")
        if isinstance(sync_cursor, dict):
            return sync_cursor.get("sync_run_id") or sync_cursor.get("last_run_id")
        return None

    @staticmethod
    def _value_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (Decimal, int, float)):
            return "number"
        return "text"

    @staticmethod
    def _formula_code(*, definition_id: Any, version: Any) -> str:
        if definition_id is not None and version is not None:
            return f"problem_definition:{definition_id}.v{version}"
        if version is not None:
            return f"problem_rule.v{version}"
        return "problem_rule"

    @staticmethod
    def _formula_id(*, rule_id: Any, version: Any) -> str:
        if rule_id is not None:
            return f"problem_rule_version:{rule_id}"
        if version is not None:
            return f"problem_rule_version:v{version}"
        return "problem_rule_version"
