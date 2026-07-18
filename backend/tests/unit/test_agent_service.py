from __future__ import annotations

import asyncio
import inspect
import json

import httpx

import app.services.agent.orchestrator as orchestrator
from app.schemas.agent import AgentMessageRequest
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
    assert "admin_answer" in fmt["schema"]["properties"]["intent"]["enum"]
    assert "stock_export" in fmt["schema"]["properties"]["intent"]["enum"]
    assert any('"message": "привет"' in item.get("content", "") for item in body["input"])


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
