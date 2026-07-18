from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.schemas.claims import CaseDetailOut, ClaimsCasesPage, ClaimsDraftMutationOut, ClaimsProofCheckOut
from app.schemas.operator import ProfitDoctorOut, ResultEventOut
from app.schemas.portal import (
    PortalActionRead,
    PortalActionsPage,
    PortalModulesHealthRead,
    PortalOverviewRead,
    PortalProduct360Read,
    PortalProductsPage,
    PortalResultEventsPage,
)
from app.schemas.reputation import ReputationDraftMutationOut, ReputationInboxOut, ReputationSummaryOut


FIXTURE_MODELS = {
    "action_update_ok.json": PortalActionRead,
    "actions_page_ok.json": PortalActionsPage,
    "case_detail_ok.json": CaseDetailOut,
    "cases_page_ok.json": ClaimsCasesPage,
    "claims_draft_ok.json": ClaimsDraftMutationOut,
    "claims_proof_check_ok.json": ClaimsProofCheckOut,
    "claims_submit_blocked.json": ResultEventOut,
    "doctor_ok.json": ProfitDoctorOut,
    "modules_health_ok.json": PortalModulesHealthRead,
    "overview_ok.json": PortalOverviewRead,
    "product_360_contract_ok.json": PortalProduct360Read,
    "product_360_ok.json": PortalProduct360Read,
    "products_page_ok.json": PortalProductsPage,
    "reputation_draft_ok.json": ReputationDraftMutationOut,
    "reputation_inbox_ok.json": ReputationInboxOut,
    "reputation_publish_blocked.json": ResultEventOut,
    "reputation_summary_ok.json": ReputationSummaryOut,
    "results_unified_ok.json": PortalResultEventsPage,
}

LOVABLE_PILOT_ENDPOINT_FIXTURES = {
    "/portal/doctor": ("doctor_ok.json", ProfitDoctorOut),
    "/portal/actions": ("actions_page_ok.json", PortalActionsPage),
    "/portal/products/{nm_id}": ("product_360_contract_ok.json", PortalProduct360Read),
    "/portal/reputation/inbox": ("reputation_inbox_ok.json", ReputationInboxOut),
    "/portal/cases": ("cases_page_ok.json", ClaimsCasesPage),
    "/portal/results": ("results_unified_ok.json", PortalResultEventsPage),
}


LOVABLE_CONTRACT_ENDPOINT_FIXTURES = {
    "GET /api/v1/portal/modules/health": ("modules_health_ok.json", PortalModulesHealthRead),
    "GET /api/v1/portal/doctor": ("doctor_ok.json", ProfitDoctorOut),
    "GET /api/v1/portal/overview": ("overview_ok.json", PortalOverviewRead),
    "GET /api/v1/portal/actions": ("actions_page_ok.json", PortalActionsPage),
    "PATCH /api/v1/portal/actions/by-source": ("action_update_ok.json", PortalActionRead),
    "GET /api/v1/portal/products": ("products_page_ok.json", PortalProductsPage),
    "GET /api/v1/portal/products/{nm_id}": ("product_360_contract_ok.json", PortalProduct360Read),
    "GET /api/v1/portal/reputation/inbox": ("reputation_inbox_ok.json", ReputationInboxOut),
    "GET /api/v1/portal/reputation/summary": ("reputation_summary_ok.json", ReputationSummaryOut),
    "GET /api/v1/portal/cases": ("cases_page_ok.json", ClaimsCasesPage),
    "POST /api/v1/portal/cases/from-signal": ("case_detail_ok.json", CaseDetailOut),
    "GET /api/v1/portal/results": ("results_unified_ok.json", PortalResultEventsPage),
}


@pytest.mark.parametrize("fixture_name,model", sorted(FIXTURE_MODELS.items()))
def test_portal_contract_fixture_validates_against_schema(fixture_name: str, model) -> None:
    fixture_path = Path("tests/fixtures/portal") / fixture_name
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    parsed = model.model_validate(payload)
    dumped = parsed.model_dump(mode="json")

    assert dumped
    assert "must-not-leak" not in str(dumped)
    assert "authorization" not in str(dumped).lower()
    assert "token" not in str(dumped).lower()


@pytest.mark.parametrize("endpoint,fixture_model", sorted(LOVABLE_CONTRACT_ENDPOINT_FIXTURES.items()))
def test_lovable_contract_fixture_top_level_keys_match_schema_output(endpoint: str, fixture_model) -> None:
    fixture_name, model = fixture_model
    fixture_path = Path("tests/fixtures/portal") / fixture_name
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    dumped = model.model_validate(payload).model_dump(mode="json")

    assert set(payload) == set(dumped), endpoint


def test_product_360_contract_fixture_uses_direct_schema_blocks() -> None:
    fixture_path = Path("tests/fixtures/portal/product_360_contract_ok.json")
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))

    documented_fields = set(payload)
    schema_fields = set(PortalProduct360Read.model_fields)

    assert documented_fields <= schema_fields
    assert "product" not in documented_fields
    assert "tabs" not in documented_fields

    required_direct_blocks = {
        "nm_id",
        "overview_diagnosis",
        "identity",
        "money",
        "costs",
        "ads",
        "stock",
        "pricing",
        "data_quality",
        "quality",
        "card_quality",
        "reputation",
        "claims",
        "grouping",
        "grouping_beta",
        "actions",
        "history",
        "result_history",
        "next_best_action",
        "module_health",
        "stock_summary",
        "ads_summary",
        "data_issues",
        "finance",
        "unavailable_sources",
        "raw",
    }
    assert required_direct_blocks <= documented_fields

    parsed = PortalProduct360Read.model_validate(payload)
    statuses = {
        parsed.costs.status,
        parsed.ads.status,
        parsed.quality.status,
        parsed.reputation.status,
        parsed.claims.status,
        parsed.grouping_beta.status,
    }
    assert {"empty", "unavailable", "not_configured", "disabled"} <= statuses


@pytest.mark.parametrize("endpoint,fixture_model", sorted(LOVABLE_PILOT_ENDPOINT_FIXTURES.items()))
def test_lovable_pilot_endpoint_fixture_validates_and_stays_scrubbed(endpoint: str, fixture_model) -> None:
    fixture_name, model = fixture_model
    payload = json.loads((Path("tests/fixtures/portal") / fixture_name).read_text(encoding="utf-8"))

    parsed = model.model_validate(payload)
    dumped = parsed.model_dump(mode="json")

    assert endpoint.startswith("/portal/")
    assert dumped
    assert "must-not-leak" not in str(dumped)
    assert "authorization" not in str(dumped).lower()
    assert "token" not in str(dumped).lower()
