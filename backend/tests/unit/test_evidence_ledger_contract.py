from __future__ import annotations

import os

os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("WB_TOKEN_ENCRYPTION_KEY", "XfoaFGX-I78C74Vi8pXyppYXQ05g7H0jBPJCOncKAsg=")

from app.main import app


def _schema_for(path: str) -> dict:
    schema = app.openapi()
    return schema["paths"][path]["get"]["responses"]["200"]["content"]["application/json"]["schema"]


def _resolve(schema: dict, components: dict) -> dict:
    while "$ref" in schema:
        schema = components[schema["$ref"].split("/")[-1]]
    return schema


def _variants(schema: dict, components: dict) -> list[dict]:
    resolved = _resolve(schema, components)
    if "anyOf" in resolved:
        return [item for variant in resolved["anyOf"] for item in _variants(variant, components)]
    if "oneOf" in resolved:
        return [item for variant in resolved["oneOf"] for item in _variants(variant, components)]
    if "allOf" in resolved:
        return [item for variant in resolved["allOf"] for item in _variants(variant, components)]
    return [resolved]


def _has_field(schema: dict, path: str, components: dict) -> bool:
    candidates = [schema]
    for raw_part in path.split("."):
        wants_array = raw_part.endswith("[]")
        part = raw_part[:-2] if wants_array else raw_part
        next_candidates: list[dict] = []
        for candidate in candidates:
            for variant in _variants(candidate, components):
                props = variant.get("properties") or {}
                if part in props:
                    next_candidates.append(props[part])
        if not next_candidates:
            return False
        if wants_array:
            array_items: list[dict] = []
            for candidate in next_candidates:
                for variant in _variants(candidate, components):
                    if variant.get("type") == "array" and "items" in variant:
                        array_items.append(variant["items"])
            if not array_items:
                return False
            next_candidates = array_items
        candidates = next_candidates
    return True


def test_mvp_endpoint_schemas_expose_evidence_ledger() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    expected = {
        "/api/v1/portal/actions": ["items[].evidence_ledger", "items[].money_trust", "items[].payload"],
        "/api/v1/money/summary": [
            "evidence_ledger",
            "kpis.evidence_ledger",
            "next_actions[].evidence_ledger",
            "next_actions[].money_trust",
            "risk_summary.risks[].evidence_ledger",
            "risk_summary.risks[].money_trust",
            "top_cards.profitable[].money_trust",
            "top_cards.loss_making[].money_trust",
        ],
        "/api/v1/money/data-blockers": ["evidence_ledger", "blockers[].evidence_ledger", "blockers[].money_trust", "warnings[].evidence_ledger", "warnings[].money_trust"],
        "/api/v1/dq/issues": ["items[].evidence_ledger", "items[].money_trust"],
        "/api/v1/dq/issues/summary": ["evidence_ledger", "items[].evidence_ledger", "items[].money_trust"],
        "/api/v1/portal/data-readiness": ["evidence_ledger", "blockers[].evidence_ledger", "blockers[].money_trust"],
        "/api/v1/portal/card-quality/issues": ["evidence_ledger", "items[].evidence_ledger", "items[].money_trust"],
        "/api/v1/portal/products": ["items[].evidence_ledger", "items[].money_trust"],
        "/api/v1/portal/products/{nm_id}": ["evidence_ledger", "money.evidence_ledger", "card_quality.evidence_ledger", "actions[].evidence_ledger", "actions[].money_trust"],
    }

    for path, fields in expected.items():
        schema = _schema_for(path)
        missing = [field for field in fields if not _has_field(schema, field, components)]
        assert missing == [], f"{path} missing evidence fields: {missing}"


def test_evidence_ledger_openapi_exposes_calculation_contract() -> None:
    openapi = app.openapi()
    components = openapi["components"]["schemas"]
    ledger = components["EvidenceLedger"]
    input_fact = components["EvidenceInputFact"]
    source_reference = components["EvidenceSourceReference"]

    assert {
        "formula_human",
        "formula_code",
        "formula_id",
        "input_facts",
        "source_references",
        "missing_data",
        "trust_notes",
        "recheck_rule_human",
        "calculation_warnings",
    } <= set(ledger["properties"])
    assert {
        "label",
        "metric_code",
        "value",
        "unit",
        "trust_state",
        "source",
        "source_table",
        "source_endpoint",
        "date_range",
    } <= set(input_fact["properties"])
    assert {
        "source_table",
        "source_endpoint",
        "date_range",
        "row_count",
        "sync_run_id",
    } <= set(source_reference["properties"])
