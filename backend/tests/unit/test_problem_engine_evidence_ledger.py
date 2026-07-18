from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.schemas.evidence import EvidenceLedger, evidence_ledger
from app.schemas.problem_engine import MetricSourceReference, ProblemInstanceCreate, ProductMetricResolution, ResolvedMetricValue
from app.services.problem_engine import EvidenceLedgerBuilder, FormulaEvaluator


def test_evidence_ledger_contract_contains_required_problem_fields() -> None:
    ledger = evidence_ledger(
        value=Decimal("120.50"),
        value_type="money",
        confidence="confirmed",
        impact_type="confirmed_loss",
        formula_human="Revenue - costs - ads.",
        formula_code="negative_unit_profit.v1",
        label="Unit profit",
        metric_code="unit_profit",
        unit="RUB",
        trust_state="confirmed",
        source="money",
        source_table="mart_sku_daily",
        source_endpoint="GET /api/v1/marts/sku-daily",
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 6),
        row_count=6,
        missing_data=[],
        trust_notes=["Confirmed from mart data."],
        recheck_rule="Refresh marts and re-run the rule.",
        calculation_warnings=["Rounded to 2 decimals."],
    )

    dumped = ledger.model_dump(mode="json")
    fact = dumped["input_facts"][0]
    source = dumped["source_references"][0]
    assert fact["metric_code"] == "unit_profit"
    assert fact["trust_state"] == "confirmed"
    assert fact["source"] == "money"
    assert fact["source_table"] == "mart_sku_daily"
    assert fact["source_endpoint"] == "GET /api/v1/marts/sku-daily"
    assert fact["date_range"]["date_from"] == "2026-07-01"
    assert source["source_table"] == "mart_sku_daily"
    assert source["source_endpoint"] == "GET /api/v1/marts/sku-daily"
    assert source["row_count"] == 6
    assert dumped["recheck_rule_human"] == "Refresh marts and re-run the rule."
    assert dumped["calculation_warnings"] == ["Rounded to 2 decimals."]


def test_evidence_source_reference_accepts_legacy_aliases() -> None:
    ledger = EvidenceLedger.model_validate(
        {
            "formula_human": "Legacy source.",
            "formula_code": "legacy.v1",
            "source_references": [{"table": "data_quality_issues", "wb_endpoint": "GET /api/v1/dq/issues"}],
        }
    )

    assert ledger.source_references[0].source_table == "data_quality_issues"
    assert ledger.source_references[0].source_endpoint == "GET /api/v1/dq/issues"


def test_problem_engine_evidence_builder_uses_resolved_metrics_and_diagnostics() -> None:
    resolved = ProductMetricResolution(
        account_id=1,
        nm_id=1001,
        date_from=date(2026, 7, 1),
        date_to=date(2026, 7, 6),
        metrics={
            "stock_qty": ResolvedMetricValue(
                metric_code="stock_qty",
                value=Decimal("60"),
                value_type="count",
                unit="pcs",
                trust_state="confirmed",
                evidence=MetricSourceReference(
                    source_module="stock",
                    source_table="mart_stock_daily",
                    source_endpoint="GET /api/v1/stocks",
                    date_from=date(2026, 7, 1),
                    date_to=date(2026, 7, 6),
                    row_count=1,
                    freshness={"sync_cursor": {"sync_run_id": 44, "status": "completed"}},
                    filters={"account_id": 1, "nm_id": 1001},
                ),
            ),
            "cost_price": ResolvedMetricValue(
                metric_code="cost_price",
                value=None,
                value_type="money",
                unit="RUB",
                trust_state="blocked",
                is_missing=True,
                missing_reason="source_data_missing",
                evidence=MetricSourceReference(
                    source_module="costs",
                    source_table="manual_costs",
                    source_endpoint="GET /api/v1/costs/rows",
                    date_from=date(2026, 7, 1),
                    date_to=date(2026, 7, 6),
                    row_count=0,
                    filters={"account_id": 1, "nm_id": 1001},
                ),
            ),
        },
        missing_metrics=["cost_price"],
    )
    condition = FormulaEvaluator().evaluate_condition(
        {">": [{"metric": "cost_price"}, 0]},
        metrics=resolved.values_for_formula(),
        evaluation_context={"allowed_metrics": {"stock_qty", "cost_price"}},
    )
    rule = SimpleNamespace(
        id=7,
        problem_definition_id=3,
        version=2,
        evidence_template_json={
            "formula_human": "cost_price > 0",
            "formula_code": "missing_cost_blocks_profit.v2",
            "formula_id": "missing_cost_blocks_profit:2",
            "trust_notes": ["Cost is required before profit can be shown."],
        },
        recheck_rule_json={"human": "Upload cost data and re-run metric resolution."},
    )

    ledger = EvidenceLedgerBuilder().build_for_problem(
        rule_version=rule,
        resolved_metrics=resolved,
        formula_diagnostics=condition,
    )
    dumped = ledger.model_dump(mode="json")

    assert dumped["formula_human"] == "cost_price > 0"
    assert dumped["formula_code"] == "missing_cost_blocks_profit.v2"
    assert dumped["input_facts"][0]["metric_code"] == "stock_qty"
    assert dumped["input_facts"][1]["metric_code"] == "cost_price"
    assert dumped["input_facts"][1]["trust_state"] == "blocked"
    assert dumped["source_references"][0]["source_table"] == "mart_stock_daily"
    assert dumped["source_references"][0]["sync_run_id"] == 44
    assert "cost_price: source_data_missing" in dumped["missing_data"]
    assert "cost_price: missing during formula evaluation" in dumped["missing_data"]
    assert dumped["recheck_rule_human"] == "Upload cost data and re-run metric resolution."


def test_generated_problem_instance_create_requires_full_evidence_ledger() -> None:
    now = datetime(2026, 7, 6, tzinfo=timezone.utc)
    valid_ledger = {
        "formula_human": "stock_qty > 50",
        "formula_code": "overstock_slow_moving.v1",
        "input_facts": [
            {
                "label": "stock qty",
                "metric_code": "stock_qty",
                "value": 60,
                "unit": "pcs",
                "trust_state": "confirmed",
                "source": "stock",
                "source_table": "mart_stock_daily",
                "source_endpoint": "GET /api/v1/stocks",
                "date_range": {"date_from": "2026-07-01", "date_to": "2026-07-06"},
            }
        ],
        "source_references": [
            {
                "source_table": "mart_stock_daily",
                "source_endpoint": "GET /api/v1/stocks",
                "date_range": {"date_from": "2026-07-01", "date_to": "2026-07-06"},
                "row_count": 1,
            }
        ],
        "missing_data": [],
        "trust_notes": [],
        "recheck_rule_human": "Refresh stocks and re-run the rule.",
        "calculation_warnings": [],
    }
    payload = {
        "account_id": 1,
        "problem_code": "overstock_slow_moving",
        "problem_definition_id": 1,
        "rule_version_id": 1,
        "source_module": "problem_engine",
        "entity_type": "product",
        "entity_id": "1001",
        "nm_id": 1001,
        "dedup_key": "overstock:1001",
        "title": "Overstock",
        "explanation": "Stock is high.",
        "recommendation": "Review promotion.",
        "severity": "medium",
        "impact_type": "blocked_cash",
        "trust_state": "confirmed",
        "evidence_ledger_json": valid_ledger,
        "calculation_snapshot_json": {},
        "first_seen_at": now,
        "last_seen_at": now,
    }

    instance = ProblemInstanceCreate.model_validate(payload)
    assert instance.evidence_ledger_json["formula_code"] == "overstock_slow_moving.v1"

    invalid_payload = {**payload, "evidence_ledger_json": {}}
    with pytest.raises(ValueError, match="evidence_ledger_json"):
        ProblemInstanceCreate.model_validate(invalid_payload)
