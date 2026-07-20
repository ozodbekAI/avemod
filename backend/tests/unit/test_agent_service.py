from __future__ import annotations

import asyncio
import inspect
import json

import httpx

import app.services.agent.orchestrator as orchestrator
from app.schemas.agent import AgentMessageRequest, AgentToolCallRequest
from app.services.agent import AgentService


def _money_page_context() -> dict[str, object]:
    return {
        "path": "/dashboard",
        "visible_text": (
            "ПЕРИОД Неделя Месяц Произвольный период 7 дн. "
            "Чистая прибыль 287 127 ₽ Маржа 42.5% Было: 978.4k ₽."
        ),
        "visible_number_context": [
            {"text": "ПЕРИОД Неделя Месяц Произвольный период 7 дн."},
        ],
        "recent_api": [
            {
                "method": "GET",
                "path": "/money/summary",
                "status": 200,
                "priority_fields": [
                    {
                        "path": "expense_breakdown.net_profit_after_all_expenses",
                        "value": 287127.0418,
                    },
                    {"path": "expense_breakdown.revenue_final", "value": 832026.47},
                    {
                        "path": "expense_breakdown.total_expenses",
                        "value": 544899.4282,
                    },
                    {
                        "path": "kpis.margin_after_overhead_percent",
                        "value": 42.54191598014904,
                    },
                    {"path": "meta.data_trust.financial_final", "value": False},
                    {
                        "path": "finance_reconciliation.status",
                        "value": "critical_mismatch",
                    },
                ],
            }
        ],
    }


def test_agent_openai_request_uses_strict_structured_outputs() -> None:
    service = AgentService()

    body = service._openai_request_payload(
        AgentMessageRequest(
            account_id=1,
            message="Покажи остатки по товару nm 1001001 в Excel",
        )
    )

    fmt = body["text"]["format"]
    assert body["model"] == service.settings.openai_model
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "seller_portal_agent_plan"
    assert fmt["strict"] is True
    assert fmt["schema"]["additionalProperties"] is False
    assert "tool_name" in fmt["schema"]["required"]
    assert "api_action_key" in fmt["schema"]["required"]
    assert "api_action_params" in fmt["schema"]["required"]
    assert "portal.navigate" in fmt["schema"]["properties"]["tool_name"]["enum"]
    assert "portal.api_action" in fmt["schema"]["properties"]["tool_name"]["enum"]
    assert "admin_answer" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "api_action" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "strategy_advice" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "reputation_agent" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "scenario_create" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "insights_report" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "module_navigate" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "module_key" in fmt["schema"]["required"]
    assert "ads" in fmt["schema"]["properties"]["module_key"]["enum"]
    assert "data_quality.run" in fmt["schema"]["properties"]["api_action_key"][
        "enum"
    ]
    assert "action_id" in fmt["schema"]["properties"]["api_action_params"][
        "properties"
    ]
    assert "stock_export" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "module_catalog" in body["input"][-1]["content"]
    assert "tool_registry" in body["input"][-1]["content"]
    assert "api_action_catalog" in body["input"][-1]["content"]
    assert "stock.export_xlsx" in body["input"][-1]["content"]
    assert "strategy.advice" in body["input"][-1]["content"]
    assert "reputation.sync" in body["input"][-1]["content"]
    assert "portal.action.update_status" in body["input"][-1]["content"]
    assert any('"message": "привет"' in item.get("content", "") for item in body["input"])
    assert any(
        "Создай сценарий ответов" in item.get("content", "")
        for item in body["input"]
    )


def test_agent_parses_structured_stock_export_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "stock_export",
                    "search_query": None,
                    "selected_nm_id": 1001001,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "stock_export"
    assert plan.selected_nm_id == 1001001
    assert plan.source == "ai"
    assert service._export_href("stock", 7, nm_id=1001001) == (
        "/export/stock.xlsx?account_id=7&nm_id=1001001"
    )


def test_agent_parses_structured_title_update_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "title_update",
                    "search_query": None,
                    "selected_nm_id": 1001001,
                    "new_title": "Блузка офисная с бантом",
                    "confidence": "high",
                    "assistant_message": None,
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "title_update"
    assert plan.selected_nm_id == 1001001
    assert plan.new_title == "Блузка офисная с бантом"


def test_agent_parses_structured_product_search_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "product_search",
                    "search_query": "брюки",
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "product_search"
    assert plan.search_query == "брюки"


def test_agent_parses_structured_admin_answer_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "admin_answer",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": "Здравствуйте! Я на связи. Что проверим?",
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "admin_answer"
    assert plan.assistant_message == "Здравствуйте! Я на связи. Что проверим?"


def test_agent_parses_jvo_like_structured_plans() -> None:
    service = AgentService()

    scenario_plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "scenario_create",
                    "search_query": None,
                    "selected_nm_id": 1001001,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": "Создать сценарий ответов на отзывы.",
                },
                ensure_ascii=False,
            )
        }
    )
    report_plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "insights_report",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": "Подготовить R&D отчёт.",
                },
                ensure_ascii=False,
            )
        }
    )

    assert scenario_plan.intent == "scenario_create"
    assert scenario_plan.selected_nm_id == 1001001
    assert report_plan.intent == "insights_report"
    assert report_plan.assistant_message == "Подготовить R&D отчёт."


def test_agent_parses_complex_strategy_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "strategy_advice",
                    "tool_name": "strategy.advice",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Стратегия: защитить наличие, затем управлять ценой по тренду.",
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "strategy_advice"
    assert plan.tool_name == "strategy.advice"
    assert "защитить наличие" in str(plan.assistant_message)


def test_agent_parses_module_navigation_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "module_navigate",
                    "tool_name": "portal.navigate",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": "ads",
                    "confidence": "high",
                    "assistant_message": "Открыл рекламу.",
                },
                ensure_ascii=False,
            )
        }
    )
    invalid = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "module_navigate",
                    "tool_name": "portal.navigate",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": "invented_module",
                    "confidence": "high",
                    "assistant_message": "Открыл что-то.",
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "module_navigate"
    assert plan.tool_name == "portal.navigate"
    assert plan.module_key == "ads"
    assert invalid.module_key is None


def test_agent_parses_api_action_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "api_action",
                    "tool_name": "portal.api_action",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": "data_quality.run",
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Готов запустить проверку качества данных.",
                },
                ensure_ascii=False,
            )
        }
    )
    invalid = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "api_action",
                    "tool_name": "portal.api_action",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": "invented.action",
                    "api_action_params": {"action_id": 42},
                    "confidence": "high",
                    "assistant_message": "Готов.",
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "api_action"
    assert plan.tool_name == "portal.api_action"
    assert plan.api_action_key == "data_quality.run"
    assert plan.api_action_params is None
    assert invalid.api_action_key is None


def test_agent_parses_parameterized_api_action_plan() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "api_action",
                    "tool_name": "portal.api_action",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": "portal.action.update_status",
                    "api_action_params": {
                        "action_id": 42,
                        "status": "done",
                        "comment": "проверено",
                    },
                    "confidence": "high",
                    "assistant_message": "Готов обновить задачу.",
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "api_action"
    assert plan.api_action_key == "portal.action.update_status"
    assert plan.api_action_params == {
        "action_id": 42,
        "status": "done",
        "comment": "проверено",
    }


def test_agent_tool_registry_overrides_mismatched_intent() -> None:
    service = AgentService()

    plan = service._plan_from_openai_payload(
        {
            "output_text": json.dumps(
                {
                    "intent": "help",
                    "tool_name": "stock.export_xlsx",
                    "search_query": None,
                    "selected_nm_id": 1001001,
                    "new_title": None,
                    "module_key": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
                ensure_ascii=False,
            )
        }
    )

    assert plan.intent == "stock_export"
    assert plan.tool_name == "stock.export_xlsx"
    assert service._audit(plan)["tool_name"] == "stock.export_xlsx"


def test_agent_tool_registry_is_mcp_style_catalog() -> None:
    service = AgentService()
    registry = service._tool_registry_for_ai()
    names = {tool["name"] for tool in registry}

    assert "portal.navigate" in names
    assert "product.search" in names
    assert "stock.export_xlsx" in names
    assert "scenario.create_manual_task" in names
    assert "strategy.advice" in names
    assert "portal.api_action" in names
    assert all("write_policy" in tool for tool in registry)


def test_agent_tools_manifest_is_external_contract() -> None:
    service = AgentService()
    manifest = service.list_tools()
    tools = {tool.name: tool for tool in manifest.tools}

    assert manifest.protocol == "finance-agent-tools-v1"
    assert manifest.direct_marketplace_writes is False
    assert "portal.navigate" in tools
    assert tools["portal.navigate"].input_schema["properties"]["module_key"][
        "enum"
    ]
    assert "portal.api_action" in tools
    assert tools["portal.api_action"].input_schema["properties"]["api_action_key"][
        "enum"
    ]
    assert "api_action_params" in tools["portal.api_action"].input_schema[
        "properties"
    ]
    assert tools["stock.export_xlsx"].write_policy == "download_only"
    assert "ads" in manifest.modules
    assert "data_quality.run" in manifest.api_actions
    assert "portal.action.update_status" in manifest.api_actions
    assert manifest.api_actions["portal.action.update_status"]["required_params"] == [
        "action_id",
        "status",
    ]
    assert manifest.api_actions["data_quality.run"]["confirm_required"] is True


def test_direct_tool_call_executes_portal_navigation() -> None:
    class User:
        id = 1

    service = AgentService()
    response = asyncio.run(
        service.execute_tool(
            None,  # type: ignore[arg-type]
            account_id=1,
            role="admin",
            user=User(),  # type: ignore[arg-type]
            payload=AgentToolCallRequest(
                account_id=1,
                tool_name="portal.navigate",
                arguments={"module_key": "ads"},
            ),
        )
    )

    assert response.status == "ok"
    assert response.intent == "module_navigate"
    assert response.actions[0].href == "/ads"
    assert response.audit["tool_name"] == "portal.navigate"
    assert response.audit["module_key"] == "ads"


def test_direct_tool_call_blocks_unknown_tool() -> None:
    class User:
        id = 1

    service = AgentService()
    response = asyncio.run(
        service.execute_tool(
            None,  # type: ignore[arg-type]
            account_id=1,
            role="admin",
            user=User(),  # type: ignore[arg-type]
            payload=AgentToolCallRequest(
                account_id=1,
                tool_name="unknown.tool",
            ),
        )
    )

    assert response.status == "blocked"
    assert response.audit["tool_policy"] == "unknown_tool_blocked"


def test_direct_tool_call_builds_api_action_request() -> None:
    class User:
        id = 1

    service = AgentService()
    response = asyncio.run(
        service.execute_tool(
            None,  # type: ignore[arg-type]
            account_id=7,
            role="admin",
            user=User(),  # type: ignore[arg-type]
            payload=AgentToolCallRequest(
                account_id=7,
                tool_name="portal.api_action",
                arguments={"api_action_key": "data_quality.run"},
            ),
        )
    )

    assert response.status == "ok"
    assert response.intent == "api_action"
    assert response.actions[0].type == "api_request"
    assert response.actions[0].href == "/dq/run"
    assert response.actions[0].method == "POST"
    assert response.actions[0].confirm_required is True
    assert response.actions[0].payload["body"] == {"account_id": 7}
    assert response.audit["api_action_key"] == "data_quality.run"


def test_api_action_download_builds_account_query() -> None:
    service = AgentService()

    response = service._api_action_response(
        orchestrator.AgentPlan(
            intent="api_action",
            tool_name="portal.api_action",
            api_action_key="analytics.export_products_csv",
            confidence="high",
        ),
        account_id=7,
    )

    assert response.status == "ok"
    assert response.intent == "api_action"
    assert response.actions[0].type == "download_file"
    assert response.actions[0].href == (
        "/analytics/export.csv?account_id=7&dataset=products"
    )
    assert response.actions[0].confirm_required is False


def test_direct_tool_call_builds_parameterized_api_action_request() -> None:
    class User:
        id = 1

    service = AgentService()
    response = asyncio.run(
        service.execute_tool(
            None,  # type: ignore[arg-type]
            account_id=7,
            role="admin",
            user=User(),  # type: ignore[arg-type]
            payload=AgentToolCallRequest(
                account_id=7,
                tool_name="portal.api_action",
                arguments={
                    "api_action_key": "portal.action.update_status",
                    "api_action_params": {
                        "action_id": 42,
                        "status": "done",
                        "comment": "проверено",
                    },
                },
            ),
        )
    )

    assert response.status == "ok"
    assert response.intent == "api_action"
    assert response.actions[0].href == "/portal/actions/42"
    assert response.actions[0].method == "PATCH"
    assert response.actions[0].payload["body"] == {
        "status": "done",
        "comment": "проверено",
    }
    assert response.actions[0].payload["api_action_params"]["action_id"] == 42


def test_api_action_requires_missing_dynamic_params() -> None:
    service = AgentService()

    response = service._api_action_response(
        orchestrator.AgentPlan(
            intent="api_action",
            tool_name="portal.api_action",
            api_action_key="portal.action.update_status",
            api_action_params={"status": "done"},
            confidence="high",
        ),
        account_id=7,
    )

    assert response.status == "needs_input"
    assert response.intent == "api_action"
    assert "action_id" in response.message
    assert response.audit["missing_params"] == ["action_id"]


def test_admin_answer_is_conversational_without_actions() -> None:
    service = AgentService()
    response = service._admin_answer(
        orchestrator.AgentPlan(
            intent="admin_answer",
            confidence="high",
            source="ai",
            assistant_message="Здравствуйте! Я на связи. Что делаем?",
        )
    )

    assert response.status == "ok"
    assert response.intent == "admin_answer"
    assert response.actions == []
    assert "Я могу найти товар" not in response.message
    assert "Здравствуйте" in response.message


def test_jvo_like_navigation_actions_are_safe() -> None:
    service = AgentService()
    reputation = service._reputation_agent(
        orchestrator.AgentPlan(intent="reputation_agent", confidence="high")
    )
    pricing = service._pricing_agent(
        orchestrator.AgentPlan(intent="pricing_agent", confidence="high")
    )
    logistics = service._logistics_response(
        orchestrator.AgentPlan(intent="open_logistics", confidence="high")
    )

    assert reputation.intent == "reputation_agent"
    assert [action.href for action in reputation.actions] == [
        "/reputation",
        "/action-center",
    ]
    assert pricing.actions[0].href == "/pricing"
    assert logistics.actions[0].href == "/logistics"
    assert reputation.audit["direct_marketplace_writes"] is False


def test_complex_strategy_response_includes_safe_read_actions() -> None:
    service = AgentService()
    response = service._strategy_advice(
        orchestrator.AgentPlan(
            intent="strategy_advice",
            tool_name="strategy.advice",
            confidence="high",
            assistant_message=(
                "Приоритеты: дни до нулевого остатка, негативные отзывы, тренд заказов, "
                "дни запаса и конверсия."
            ),
        ),
        account_id=7,
    )

    assert response.status == "ok"
    assert response.intent == "strategy_advice"
    assert "Приоритеты" in response.message
    assert response.actions[0].type == "api_request"
    assert response.actions[0].href == "/pricing/safety?account_id=7&limit=50&offset=0"
    assert any(
        action.href == "/analytics/overview?account_id=7"
        for action in response.actions
    )
    assert response.audit["strategy_mode"] == "complex_ecommerce_advice"


def test_need_product_response_preserves_original_scenario_prompt() -> None:
    service = AgentService()
    response = service._need_product_response(
        orchestrator.AgentPlan(intent="scenario_create", confidence="high"),
        products=[],
        next_intent="scenario_create",
        payload_extra={"draft_message": "Создай сценарий ответов на негативные отзывы"},
    )

    assert response.status == "needs_input"
    assert response.intent == "scenario_create"
    assert response.actions[0].payload["intent"] == "scenario_create"
    assert (
        response.actions[0].payload["draft_message"]
        == "Создай сценарий ответов на негативные отзывы"
    )


def test_module_navigation_catalog_covers_portal_sections() -> None:
    expected = {
        "dashboard": "/dashboard",
        "action_center": "/action-center",
        "money": "/money",
        "logistics": "/logistics",
        "products": "/products",
        "checker": "/checker",
        "data_fix": "/data-fix",
        "results": "/results",
        "stock_control": "/stock-control",
        "stock": "/stock",
        "pricing": "/pricing",
        "purchase_plan": "/purchase-plan",
        "ads": "/ads",
        "analytics": "/analytics",
        "operations": "/operations",
        "costs": "/costs",
        "finance": "/finance",
        "marts": "/marts",
        "catalog": "/catalog",
        "claims": "/claims",
        "reputation": "/reputation",
        "ab_tests": "/ab-tests",
        "grouping": "/grouping",
        "photo_studio": "/photo-studio",
        "settings": "/settings",
        "doctor": "/doctor",
        "admin": "/admin",
        "problem_rules": "/admin/problem-rules",
    }

    for key, href in expected.items():
        assert orchestrator.AGENT_MODULE_CATALOG[key]["href"] == href


def test_module_navigation_response_uses_catalog_href() -> None:
    service = AgentService()
    response = service._module_navigate_response(
        orchestrator.AgentPlan(
            intent="module_navigate",
            module_key="ads",
            confidence="high",
        )
    )

    assert response.status == "ok"
    assert response.intent == "module_navigate"
    assert response.actions[0].type == "navigate"
    assert response.actions[0].href == "/ads"
    assert response.audit["module_key"] == "ads"


def test_agent_ui_intent_is_not_language_parsed() -> None:
    service = AgentService()

    plan = service._ui_plan(
        AgentMessageRequest(
            account_id=1,
            intent="stock_export",
            selected_nm_id=1001001,
            message="whatever the UI sends",
        )
    )

    assert plan.intent == "stock_export"
    assert plan.selected_nm_id == 1001001
    assert plan.source == "ui"


def test_agent_without_openai_key_is_blocked_not_regex_fallback() -> None:
    service = AgentService()
    original_key = service.settings.openai_api_key
    service.settings.openai_api_key = None
    try:
        plan = asyncio.run(service._plan(AgentMessageRequest(account_id=1, message="salom")))
    finally:
        service.settings.openai_api_key = original_key

    assert plan.source == "ai_unconfigured"
    assert plan.intent == "help"


def test_agent_orchestrator_has_no_regex_language_parser() -> None:
    source = inspect.getsource(orchestrator)

    assert "import re" not in source
    assert "_rule_based_plan" not in source
    assert "_parse_nm_id" not in source
    assert "_clean_query" not in source
    assert "_extract_quoted_title" not in source
    assert "re.search" not in source
    assert "re.sub" not in source


def test_agent_rejects_out_of_range_nm_id_before_db_query() -> None:
    service = AgentService()

    assert service._coerce_nm_id("213098423") == 213098423
    assert service._coerce_nm_id(0) is None
    assert service._coerce_nm_id(2_147_483_648) is None
    assert service._coerce_nm_id("999999999999") is None


def test_page_metric_context_fallback_explains_money_summary_formula() -> None:
    answer = AgentService._page_explain_fallback(
        _money_page_context(),
        "shu 287 127 ₽ son qayerdan kelayapti va qanday hisoblanayapti?",
    )

    assert "Чистая прибыль 287 127 ₽" in answer["answer"]
    assert "ПЕРИОД" not in answer["answer"]
    assert "expense_breakdown.net_profit_after_all_expenses" in answer["answer"]
    assert "expense_breakdown.revenue_final (832026.47)" in answer["answer"]
    assert "expense_breakdown.total_expenses (544899.4282)" in answer["answer"]
    assert "287 127 ₽" in answer["answer"]
    assert "GET /money/summary" in answer["used_sources"]


def test_agent_can_route_page_metric_from_context_when_ai_planner_fails() -> None:
    payload = AgentMessageRequest(
        account_id=1,
        message="shu 287 127 ₽ son qayerdan kelayapti?",
        context=_money_page_context(),
    )

    assert AgentService._can_answer_page_metric_from_context(payload) is True


def test_context_fallback_page_explain_skips_openai_answer_call() -> None:
    class NoOpenAIPageAgent(AgentService):
        async def _openai_page_answer(
            self, *, message: str, context_text: str
        ) -> dict[str, object]:
            raise AssertionError("context fallback must not call OpenAI")

    service = NoOpenAIPageAgent()
    payload = AgentMessageRequest(
        account_id=1,
        message="shu 287 127 ₽ son qayerdan kelayapti?",
        context=_money_page_context(),
    )
    plan = orchestrator.AgentPlan(
        intent="page_explain",
        confidence="medium",
        source="context_fallback",
    )

    response = asyncio.run(service._page_explain(payload=payload, plan=plan))

    assert response.status == "ok"
    assert response.mode == "ai_fallback"
    assert response.intent == "page_explain"
    assert response.audit["planner"] == "context_fallback"
    assert "net_profit_after_all_expenses" in response.message
    assert "revenue_final" in response.message
    assert "total_expenses" in response.message


def test_openai_retry_helpers_treat_rate_limits_as_expected() -> None:
    request = httpx.Request("POST", AgentService.OPENAI_RESPONSES_URL)
    response = httpx.Response(429, headers={"retry-after": "0.1"}, request=request)
    exc = httpx.HTTPStatusError("rate limited", request=request, response=response)

    assert AgentService._should_retry_openai_response(response, attempt=0) is True
    assert AgentService._should_retry_openai_response(response, attempt=1) is False
    assert AgentService._should_retry_openai_exception(exc, attempt=0) is True
    assert AgentService._should_log_openai_exc_info(exc) is False
    assert AgentService._openai_retry_delay(response, attempt=0) == 0.1


def test_planner_error_message_is_clear_for_insufficient_quota() -> None:
    service = AgentService()
    request = httpx.Request("POST", AgentService.OPENAI_RESPONSES_URL)
    response = httpx.Response(
        429,
        json={"error": {"type": "insufficient_quota", "code": "insufficient_quota"}},
        request=request,
    )
    exc = httpx.HTTPStatusError("quota", request=request, response=response)

    assert "исчерпана квота OpenAI" in service._planner_error_message(exc)
