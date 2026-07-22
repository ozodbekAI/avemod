from __future__ import annotations

from decimal import Decimal
import asyncio

from fastapi import HTTPException
import pytest

from app.core.db import Base
from app.core.model_registry import load_all_models
from app.models.agent import (
    AgentActionPreview,
    AgentScenario,
    AgentScenarioRun,
    AgentUsageLedger,
)
from app.services.agent.scenarios import AgentScenarioService
from app.schemas.agent import AgentMCPRequest
from app.services.agent.mcp import AgentMCPService
from app.services.agent.orchestrator import (
    AGENT_API_ACTION_CATALOG,
    AGENT_TOOL_REGISTRY,
    AgentService,
)


AGENT_MODELS = (
    AgentScenario,
    AgentScenarioRun,
    AgentActionPreview,
    AgentUsageLedger,
)


def test_agent_scenario_models_are_registered() -> None:
    load_all_models()

    for model in AGENT_MODELS:
        assert model.__tablename__ in Base.metadata.tables


def test_agent_scenario_models_have_product_level_columns() -> None:
    scenario_columns = AgentScenario.__table__.c
    assert {
        "account_id",
        "scenario_type",
        "status",
        "approval_policy",
        "auto_execute_enabled",
        "scope_json",
        "schedule_json",
        "guardrails_json",
        "actions_json",
        "next_run_at",
        "last_run_status",
    }.issubset(scenario_columns.keys())

    run_columns = AgentScenarioRun.__table__.c
    assert {
        "scenario_id",
        "trigger",
        "dry_run",
        "actions_preview_json",
        "actions_executed",
        "actions_blocked",
        "estimated_cost_usd",
    }.issubset(run_columns.keys())


def test_agent_scenario_templates_cover_jvo_like_domains() -> None:
    templates = AgentScenarioService.templates()
    types = {item.scenario_type for item in templates.items}

    assert {"reputation", "pricing", "ads", "stock", "strategy"}.issubset(types)
    assert all(item.default_guardrails_json for item in templates.items)
    assert all(item.default_actions_json for item in templates.items)


def test_agent_manifest_exposes_scenario_history_and_finance_actions() -> None:
    assert AGENT_TOOL_REGISTRY["scenario.create_manual_task"]["write_policy"] == (
        "scenario_draft_preview_first"
    )
    for key in (
        "agent.scenarios",
        "agent.scenario_runs",
        "agent.finance",
        "agent.scenario.run",
    ):
        assert key in AGENT_API_ACTION_CATALOG
    assert AGENT_API_ACTION_CATALOG["agent.scenario.run"]["confirm_required"] is True
    assert AGENT_API_ACTION_CATALOG["agent.scenario.run"]["required_params"] == [
        "scenario_id"
    ]


def test_agent_scenario_actions_are_strictly_allow_listed() -> None:
    service = AgentScenarioService()

    assert service._validate_actions_json([{"api_action_key": "portal.overview"}]) == [
        {"api_action_key": "portal.overview"}
    ]
    with pytest.raises(HTTPException) as exc:
        service._validate_actions_json([{"api_action_key": "invented.action"}])

    assert exc.value.status_code == 422
    assert "allow-listed" in str(exc.value.detail)


def test_agent_usage_cost_uses_configured_openai_prices() -> None:
    service = AgentScenarioService()

    assert service._usage_tokens(
        {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}
    ) == {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
    }
    assert service._estimate_openai_cost(
        model="gpt-5-mini",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
    ) == Decimal("2.250000")


def test_agent_mcp_tools_list_matches_protocol_shape() -> None:
    response = asyncio.run(
        AgentMCPService(AgentService()).handle(
            None,  # type: ignore[arg-type]
            account_id=1,
            role="admin",
            user=object(),  # type: ignore[arg-type]
            payload=AgentMCPRequest(id=1, method="tools/list"),
        )
    )

    assert response.error is None
    assert response.result is not None
    assert response.result["tools"]
    first_tool = response.result["tools"][0]
    assert {"name", "title", "description", "inputSchema", "annotations"}.issubset(
        first_tool
    )


def test_agent_mcp_unknown_tool_returns_tool_error_result() -> None:
    response = asyncio.run(
        AgentMCPService(AgentService()).handle(
            None,  # type: ignore[arg-type]
            account_id=1,
            role="admin",
            user=object(),  # type: ignore[arg-type]
            payload=AgentMCPRequest(
                id="call-1",
                method="tools/call",
                params={"name": "missing.tool", "arguments": {}},
            ),
        )
    )

    assert response.error is None
    assert response.result is not None
    assert response.result["isError"] is True
    assert response.result["structuredContent"]["status"] == "blocked"
