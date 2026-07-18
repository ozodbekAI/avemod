from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from time import perf_counter
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import String

from app.core.config import get_settings
from app.core.time import utcnow
from app.models.product_cards import WBProductCard
from app.schemas.agent import (
    AgentIntent,
    AgentMessageRequest,
    AgentMessageResponse,
    AgentProductRef,
    AgentUIAction,
)
from app.schemas.portal import PortalManualActionCreateRequest
from app.services.checker_core.title_policy import (
    should_keep_current_title_as_safer,
    validate_title,
)

if TYPE_CHECKING:
    from app.models.auth import AuthUser
    from app.services.portal import PortalService


logger = logging.getLogger(__name__)


MAX_DB_INT32 = 2_147_483_647
MIN_WB_NM_ID = 1
OPENAI_MAX_ATTEMPTS = 2
OPENAI_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}
OPENAI_RETRY_BASE_SECONDS = 0.35
OPENAI_RETRY_MAX_SECONDS = 2.0


ALLOWED_AGENT_INTENTS: list[AgentIntent] = [
    "help",
    "admin_answer",
    "product_search",
    "product_details",
    "stock_export",
    "title_update",
    "page_explain",
    "open_action_center",
    "open_checker",
    "open_pricing",
    "open_stock_control",
    "open_money",
]


@dataclass(frozen=True, slots=True)
class AgentPlan:
    intent: AgentIntent
    search_query: str | None = None
    selected_nm_id: int | None = None
    new_title: str | None = None
    confidence: str = "medium"
    source: str = "ai"
    assistant_message: str | None = None


class AgentService:
    """AI command orchestrator for the Seller Portal.

    OpenAI is the only natural-language planner. This service never uses regex
    or keyword rules to infer user intent; the backend only executes
    allow-listed tools from the structured AI plan.
    """

    OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
    PRODUCT_PICKER_LIMIT = 8
    OPENAI_PLAN_SCHEMA: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "intent",
            "search_query",
            "selected_nm_id",
            "new_title",
            "confidence",
            "assistant_message",
        ],
        "properties": {
            "intent": {
                "type": "string",
                "enum": ALLOWED_AGENT_INTENTS,
                "description": (
                    "The single portal intent that best matches the user's command. "
                    "Use admin_answer for greetings, conversational follow-ups, and general admin-style advice "
                    "that does not require a portal tool. Use page_explain for questions about visible page numbers, "
                    "formulas, sources, or why a metric has its value."
                ),
            },
            "search_query": {
                "type": ["string", "null"],
                "description": "Short cleaned product search text, or null when the command does not need product search.",
            },
            "selected_nm_id": {
                "type": ["integer", "null"],
                "description": "Exact WB nm_id mentioned by the user, or null. Never invent an id.",
            },
            "new_title": {
                "type": ["string", "null"],
                "description": "New product title requested by the user, or null.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Confidence in the planning decision.",
            },
            "assistant_message": {
                "type": ["string", "null"],
                "description": "Short Russian conversational/admin answer for admin_answer or help-like commands.",
            },
        },
    }
    OPENAI_PAGE_ANSWER_SCHEMA: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["answer", "used_sources", "warnings", "confidence"],
        "properties": {
            "answer": {
                "type": "string",
                "description": "A concise Russian explanation of the visible page number, its source and calculation path.",
            },
            "used_sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Visible page labels, API endpoints, fields, or formulas used for the answer.",
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Uncertainty notes when exact calculation cannot be proven from the provided context.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
        },
    }
    OPENAI_PAGE_QUESTION_SCHEMA: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["is_page_question", "confidence", "reason"],
        "properties": {
            "is_page_question": {
                "type": "boolean",
                "description": "True when the user asks about the current page, a visible number, formula, source, or metric meaning.",
            },
            "confidence": {
                "type": "string",
                "enum": ["low", "medium", "high"],
            },
            "reason": {
                "type": "string",
            },
        },
    }

    def __init__(self, portal_service: "PortalService | None" = None) -> None:
        self.settings = get_settings()
        self.portal = portal_service

    async def handle(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: "AuthUser",
        payload: AgentMessageRequest,
    ) -> AgentMessageResponse:
        if payload.intent is not None:
            plan = self._ui_plan(payload)
        else:
            plan = await self._plan(payload)

        if payload.selected_nm_id is not None and plan.selected_nm_id is None:
            plan = self._replace_plan(plan, selected_nm_id=payload.selected_nm_id)
        if payload.new_title is not None and plan.new_title is None:
            plan = self._replace_plan(plan, new_title=payload.new_title)

        if (
            plan.intent == "help" or plan.source == "ai_error"
        ) and self._can_answer_page_metric_from_context(payload):
            plan = self._replace_plan(
                plan,
                intent="page_explain",
                confidence="medium",
                source="context_fallback",
            )
        elif (
            plan.intent == "help" or plan.source == "ai_error"
        ) and await self._is_page_explain_question(payload):
            plan = self._replace_plan(
                plan, intent="page_explain", confidence="high", source="ai"
            )

        if plan.source in {"ai_unconfigured", "ai_error"}:
            return self._planner_unavailable_response(plan)

        if plan.intent == "admin_answer":
            return self._admin_answer(plan)
        if plan.intent == "product_search":
            return await self._product_search(session, account_id=account_id, plan=plan)
        if plan.intent == "product_details":
            return await self._product_details(
                session, account_id=account_id, plan=plan
            )
        if plan.intent == "stock_export":
            return await self._stock_export(session, account_id=account_id, plan=plan)
        if plan.intent == "title_update":
            return await self._title_update(
                session, account_id=account_id, role=role, user=user, plan=plan
            )
        if plan.intent == "page_explain":
            return await self._page_explain(payload=payload, plan=plan)
        if plan.intent == "open_checker":
            return self._navigation_response(
                plan,
                "/checker",
                "Проверка карточек",
                "Открыл раздел проверки карточек.",
            )
        if plan.intent == "open_pricing":
            return self._navigation_response(
                plan, "/pricing", "Цены", "Открыл раздел цен и безопасной маржи."
            )
        if plan.intent == "open_stock_control":
            return self._navigation_response(
                plan,
                "/stock-control",
                "Управление остатками",
                "Открыл раздел управления остатками.",
            )
        if plan.intent == "open_money":
            return self._navigation_response(
                plan, "/money", "Деньги", "Открыл денежный контур."
            )
        if plan.intent == "open_action_center":
            return self._navigation_response(
                plan, "/action-center", "Центр действий", "Открыл список задач."
            )

        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="help",
            message=self._help_message(),
            actions=[
                AgentUIAction(
                    type="navigate", title="Центр действий", href="/action-center"
                ),
            ],
            suggestions=[
                "Покажи остатки по товару",
                "Хочу изменить название товара",
                "Открой проверку карточек",
            ],
            audit=self._audit(plan),
        )

    @staticmethod
    def _help_message() -> str:
        return (
            "Я могу найти товар, открыть карточку товара, подготовить Excel по остаткам, "
            "показать безопасный предпросмотр изменения названия, открыть цены, управление остатками, "
            "деньги, проверку карточек, Центр действий или объяснить видимые цифры на текущей странице. "
            "Напишите вопрос или команду обычным текстом."
        )

    def _admin_answer(self, plan: AgentPlan) -> AgentMessageResponse:
        message = self._nullable_text(plan.assistant_message) or (
            "Я на связи. Могу помочь как администратор портала: разобрать вопрос, "
            "подсказать следующий шаг или выполнить безопасное действие в системе."
        )
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="admin_answer",
            message=message,
            suggestions=[
                "Что проверить сегодня?",
                "Объясни цифру на странице",
                "Найди товар",
            ],
            audit=self._audit(plan),
        )

    @staticmethod
    def _replace_plan(plan: AgentPlan, **updates: Any) -> AgentPlan:
        data = {
            "intent": plan.intent,
            "search_query": plan.search_query,
            "selected_nm_id": plan.selected_nm_id,
            "new_title": plan.new_title,
            "confidence": plan.confidence,
            "source": plan.source,
            "assistant_message": plan.assistant_message,
        }
        data.update(updates)
        return AgentPlan(**data)

    @staticmethod
    def _ui_plan(payload: AgentMessageRequest) -> AgentPlan:
        return AgentPlan(
            intent=payload.intent or "help",
            search_query=str(payload.message or "").strip() or None,
            selected_nm_id=payload.selected_nm_id,
            new_title=payload.new_title,
            confidence="high",
            source="ui",
        )

    async def _plan(self, payload: AgentMessageRequest) -> AgentPlan:
        if not self.settings.openai_api_key:
            return AgentPlan(
                "help",
                confidence="low",
                source="ai_unconfigured",
                assistant_message="AI-оператор не настроен: добавьте OPENAI_API_KEY на backend.",
            )
        return await self._openai_plan(payload)

    async def _openai_plan(self, payload: AgentMessageRequest) -> AgentPlan:
        request_payload = self._openai_request_payload(payload)
        started_at = perf_counter()
        last_error: Exception | None = None
        for attempt in range(OPENAI_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    timeout=min(float(self.settings.openai_timeout_seconds), 60.0)
                ) as client:
                    response = await client.post(
                        self.OPENAI_RESPONSES_URL,
                        headers={
                            "Authorization": f"Bearer {self.settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_payload,
                    )
                    if self._should_retry_openai_response(response, attempt):
                        await self._sleep_before_openai_retry(response, attempt)
                        continue
                    response.raise_for_status()
                    data = response.json() if response.text else {}
                logger.info(
                    "agent_openai_plan_succeeded",
                    extra={
                        "attempt": attempt + 1,
                        "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                        "model": self.settings.openai_model,
                    },
                )
                return self._plan_from_openai_payload(data)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "agent_openai_plan_attempt_failed",
                    extra={
                        "attempt": attempt + 1,
                        "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                        "model": self.settings.openai_model,
                        "error_type": type(exc).__name__,
                        "status_code": self._openai_error_status_code(exc),
                    },
                    exc_info=self._should_log_openai_exc_info(exc),
                )
                if not self._should_retry_openai_exception(exc, attempt):
                    break
                await self._sleep_before_openai_retry(None, attempt)
        logger.warning(
            "agent_openai_plan_failed",
            extra={
                "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                "model": self.settings.openai_model,
                "error_type": type(last_error).__name__
                if last_error
                else "UnknownError",
            },
        )
        return AgentPlan(
            "help",
            confidence="low",
            source="ai_error",
            assistant_message=self._planner_error_message(last_error),
        )

    def _openai_request_payload(self, payload: AgentMessageRequest) -> dict[str, Any]:
        user_payload = {
            "message": payload.message,
            "context": self._planner_context(payload.context),
            "selected_nm_id": payload.selected_nm_id,
            "new_title": payload.new_title,
            "allowed_intents": ALLOWED_AGENT_INTENTS,
            "tool_policy": {
                "direct_marketplace_writes": False,
                "writes": "Only preview/confirm/audit or manual task flows are allowed.",
                "available_backend_tools": [
                    "product_search",
                    "product_details",
                    "stock_export",
                    "title_update_preview",
                    "page_explain",
                    "navigate_to_portal_section",
                ],
            },
        }
        examples = [
            (
                {
                    "message": "привет",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "admin_answer",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": "Здравствуйте! Я на связи. Могу помочь с товарами, остатками, ценами, проверкой карточек, задачами или объяснить показатели на текущей странице. Что делаем?",
                },
            ),
            (
                {
                    "message": "Как админ, что мне проверить сегодня?",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "admin_answer",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": "Начал бы с денег, блокеров карточек и остатков: проверьте чистую прибыль, товары с риском остатков, карточки без данных и задачи с максимальным влиянием. Если хотите, открою нужный раздел или объясню конкретную цифру на странице.",
                },
            ),
            (
                {
                    "message": "Bu 287 127 ₽ qayerdan keldi va qanday hisoblanayapti?",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "page_explain",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
            ),
            (
                {
                    "message": "Откуда взялась цифра 287 127 ₽ и как она считается?",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "page_explain",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
            ),
            (
                {
                    "message": "Привет, что ты умеешь делать?",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "help",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": "Кратко расскажите возможности панели.",
                },
            ),
            (
                {
                    "message": "Menga АК 279 черный tovarini topib ber",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "product_search",
                    "search_query": "АК 279 черный",
                    "selected_nm_id": None,
                    "new_title": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
            ),
        ]
        example_messages: list[dict[str, str]] = []
        for example_payload, example_response in examples:
            example_messages.append(
                {
                    "role": "user",
                    "content": json.dumps(example_payload, ensure_ascii=False),
                }
            )
            example_messages.append(
                {
                    "role": "assistant",
                    "content": json.dumps(example_response, ensure_ascii=False),
                }
            )
        return {
            "model": self.settings.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Ты AI-оператор панели продавца Wildberries. Понимай русский, узбекский и английский. "
                        "Всегда планируй действия через разрешённые backend tools. "
                        "Никогда не выдумывай nm_id, товар, остатки, цену или факт. "
                        "Если товар не указан точно, верни selected_nm_id=null и хороший search_query. "
                        "Если пользователь просит изменить карточку WB, выбери preview workflow, не прямую запись. "
                        "Если пользователь просто здоровается, благодарит, задаёт общий вопрос, просит совет администратора "
                        "или хочет обсудить работу портала без конкретного действия, выбери admin_answer и дай живой, "
                        "самостоятельный, короткий ответ как опытный администратор. "
                        "Если пользователь спрашивает про текущую страницу, видимую цифру, формулу, источник данных "
                        "или почему показатель такой, выбери page_explain. "
                        "Примеры page_explain: 'bu son qayerdan keldi', 'shu raqam qanday hisoblanayapti', "
                        "'qayerdan bu raqamlar kelayapti', 'откуда эта цифра', 'как считается этот показатель', "
                        "'where does this number come from'. "
                        "Все сообщения пользователю должны быть на русском. "
                        "Для admin_answer не перечисляй весь список возможностей, если пользователь просто поздоровался. "
                        "Не показывай пользователю внутренние названия intent, backend tools, JSON-поля или технические коды."
                    ),
                },
                *example_messages,
                {
                    "role": "user",
                    "content": json.dumps(user_payload, ensure_ascii=False),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "seller_portal_agent_plan",
                    "strict": True,
                    "schema": self.OPENAI_PLAN_SCHEMA,
                }
            },
            "max_output_tokens": 4096,
        }

    def _plan_from_openai_payload(self, data: dict[str, Any]) -> AgentPlan:
        parsed = self._load_json_object(self._extract_openai_text(data))
        intent = str(parsed.get("intent") or "help")
        if intent not in ALLOWED_AGENT_INTENTS:
            intent = "help"
        return AgentPlan(
            intent=intent,  # type: ignore[arg-type]
            search_query=self._nullable_text(parsed.get("search_query")),
            selected_nm_id=self._nullable_int(parsed.get("selected_nm_id")),
            new_title=self._nullable_text(parsed.get("new_title")),
            confidence=str(parsed.get("confidence") or "medium"),
            source="ai",
            assistant_message=self._nullable_text(parsed.get("assistant_message")),
        )

    @staticmethod
    def _nullable_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _nullable_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    async def _product_search(
        self, session: AsyncSession, *, account_id: int, plan: AgentPlan
    ) -> AgentMessageResponse:
        products = await self._search_products(
            session, account_id=account_id, query=plan.search_query, limit=10
        )
        if plan.selected_nm_id is not None and len(products) == 0:
            product = await self._get_product(
                session, account_id=account_id, nm_id=plan.selected_nm_id
            )
            if product is not None:
                products = [self._product_ref(product)]
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="product_search",
            message="Товары найдены. Выберите нужный товар."
            if products
            else "По этому запросу товары не найдены.",
            products=products,
            actions=[
                AgentUIAction(
                    type="open_product_picker",
                    title="Выбрать товар",
                    payload={
                        "intent": "product_details",
                        "search_query": plan.search_query or "",
                    },
                )
            ],
            suggestions=[
                "Покажи остатки по выбранному товару",
                "Открой Product 360",
                "Хочу изменить название",
            ],
            audit=self._audit(plan),
        )

    async def _product_details(
        self, session: AsyncSession, *, account_id: int, plan: AgentPlan
    ) -> AgentMessageResponse:
        if plan.selected_nm_id is None:
            products = await self._search_products(
                session,
                account_id=account_id,
                query=plan.search_query,
                limit=self.PRODUCT_PICKER_LIMIT,
            )
            return self._need_product_response(
                plan, products=products, next_intent="product_details"
            )
        product = await self._get_product(
            session, account_id=account_id, nm_id=plan.selected_nm_id
        )
        if product is None:
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="product_details",
                message="Выбранный товар не найден или не относится к этому аккаунту.",
                audit=self._audit(plan),
            )
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="product_details",
            message=f"Готов открыть Product 360 по товару: {product.title or product.vendor_code or product.nm_id}.",
            products=[self._product_ref(product)],
            actions=[
                AgentUIAction(
                    type="navigate",
                    title="Открыть товар",
                    href=f"/products/{product.nm_id}",
                ),
                AgentUIAction(
                    type="download_file",
                    title="Остатки Excel",
                    href=self._export_href("stock", account_id, nm_id=product.nm_id),
                ),
            ],
            suggestions=[
                "Хочу изменить название",
                "Покажи остатки Excel",
                "Запусти проверку карточки",
            ],
            audit=self._audit(plan),
        )

    async def _stock_export(
        self, session: AsyncSession, *, account_id: int, plan: AgentPlan
    ) -> AgentMessageResponse:
        if plan.selected_nm_id is None:
            products = await self._search_products(
                session,
                account_id=account_id,
                query=plan.search_query,
                limit=self.PRODUCT_PICKER_LIMIT,
            )
            return self._need_product_response(
                plan, products=products, next_intent="stock_export"
            )
        product = await self._get_product(
            session, account_id=account_id, nm_id=plan.selected_nm_id
        )
        if product is None:
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="stock_export",
                message="Товар с этим nm_id не найден.",
                audit=self._audit(plan),
            )
        href = self._export_href("stock", account_id, nm_id=product.nm_id)
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="stock_export",
            message="Excel по остаткам готов. Файл формируется по последним синхронизированным данным сервера.",
            products=[self._product_ref(product)],
            actions=[
                AgentUIAction(
                    type="download_file",
                    title="Скачать остатки XLSX",
                    href=href,
                    payload={
                        "nm_id": product.nm_id,
                        "vendor_code": product.vendor_code,
                    },
                ),
                AgentUIAction(
                    type="navigate",
                    title="Открыть товар",
                    href=f"/products/{product.nm_id}",
                ),
            ],
            suggestions=[
                "Открой управление остатками",
                "Покажи Product 360",
                "Хочу изменить название",
            ],
            audit=self._audit(plan),
        )

    async def _title_update(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: AuthUser,
        plan: AgentPlan,
    ) -> AgentMessageResponse:
        if plan.selected_nm_id is None:
            products = await self._search_products(
                session,
                account_id=account_id,
                query=plan.search_query,
                limit=self.PRODUCT_PICKER_LIMIT,
            )
            return self._need_product_response(
                plan, products=products, next_intent="title_update"
            )
        product = await self._get_product(
            session, account_id=account_id, nm_id=plan.selected_nm_id
        )
        if product is None:
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="title_update",
                message="Товар не найден.",
                audit=self._audit(plan),
            )
        if not plan.new_title:
            return AgentMessageResponse(
                status="needs_input",
                mode=self._mode(plan),
                intent="title_update",
                message="Введите новое название. Сначала я подготовлю предпросмотр и сравнение изменений.",
                products=[self._product_ref(product)],
                actions=[
                    AgentUIAction(
                        type="open_title_editor",
                        title="Ввести новое название",
                        payload={
                            "intent": "title_update",
                            "nm_id": product.nm_id,
                            "current_title": product.title,
                            "vendor_code": product.vendor_code,
                        },
                    )
                ],
                audit=self._audit(plan),
            )

        warnings: list[str] = []
        card_context = {
            "title": product.title,
            "subjectName": product.subject_name,
            "brand": product.brand,
            "characteristics": [],
        }
        valid, reason = validate_title(str(plan.new_title), card_context)
        if not valid:
            warnings.append(reason)
        try:
            keep_current, guard = should_keep_current_title_as_safer(
                str(product.title or ""), str(plan.new_title), card_context
            )
            if keep_current:
                warnings.append(
                    self._title_guard_warning(
                        str(guard.get("reason") or "candidate_not_safer")
                    )
                )
        except Exception:
            pass

        can_create_task = role in {"operator", "manager", "admin", "superuser"}
        task_action = AgentUIAction(
            type="create_manual_task",
            title="Создать задачу на изменение",
            method="POST",
            confirm_required=False,
            payload={
                "account_id": account_id,
                "title": "Изменить название товара",
                "description": f"Текущий title: {product.title or ''}\nНовый title: {plan.new_title}",
                "task_kind": "title_update",
                "priority": "P2",
                "assigned_to_user_id": int(user.id),
                "deadline_at": (utcnow() + timedelta(days=3)).isoformat(),
                "products": [
                    {
                        "nm_id": int(product.nm_id),
                        "vendor_code": product.vendor_code,
                        "title": product.title,
                    }
                ],
            },
        )
        actions = [
            AgentUIAction(
                type="open_preview_dialog",
                title="Предпросмотр изменения названия",
                description="Запись в WB не выполняется автоматически.",
                confirm_required=True,
                payload={
                    "nm_id": int(product.nm_id),
                    "field_path": "title",
                    "before": product.title,
                    "after": plan.new_title,
                    "can_apply_to_wb": False,
                    "apply_disabled_reason": "wb_content_write_requires_dedicated_preview_confirm_audit_flow",
                    "warnings": warnings,
                },
            ),
            AgentUIAction(
                type="navigate",
                title="Открыть товар",
                href=f"/products/{product.nm_id}",
            ),
        ]
        if can_create_task:
            actions.insert(1, task_action)
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="title_update",
            message="Предпросмотр готов. Я не меняю карточку WB автоматически: сначала нужно безопасное подтверждение через сравнение и задачу.",
            products=[self._product_ref(product)],
            actions=actions,
            suggestions=[
                "Создать задачу",
                "Открыть товар",
                "Запустить проверку карточки",
            ],
            warnings=warnings,
            audit={**self._audit(plan), "write_policy": "preview_manual_task_first"},
        )

    async def _is_page_explain_question(self, payload: AgentMessageRequest) -> bool:
        if not self.settings.openai_api_key:
            return False
        planner_context = self._planner_context(payload.context)
        if not planner_context.get("path") and not planner_context.get("visible_text"):
            return False
        request_payload = {
            "model": self.settings.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Ты строгий классификатор. Верни true, если пользователь спрашивает про текущую страницу, "
                        "видимое число, источник данных, формулу расчета или значение метрики. "
                        "Примеры true: 'bu son qayerdan keldi', 'shu raqam qanday hisoblanayapti', "
                        "'откуда эта цифра', 'как считается этот показатель'. "
                        "Верни false для вопросов о возможностях ассистента, навигации, поиске товара или изменении карточки."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "message": payload.message,
                            "page_context": planner_context,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "seller_portal_page_question_check",
                    "strict": True,
                    "schema": self.OPENAI_PAGE_QUESTION_SCHEMA,
                }
            },
            "max_output_tokens": 2048,
        }
        started_at = perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=min(float(self.settings.openai_timeout_seconds), 60.0)
            ) as client:
                response = await client.post(
                    self.OPENAI_RESPONSES_URL,
                    headers={
                        "Authorization": f"Bearer {self.settings.openai_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_payload,
                )
                response.raise_for_status()
                data = response.json() if response.text else {}
            parsed = self._load_json_object(self._extract_openai_text(data))
            logger.info(
                "agent_page_question_check_succeeded",
                extra={
                    "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                    "model": self.settings.openai_model,
                    "is_page_question": bool(parsed.get("is_page_question")),
                },
            )
            return bool(parsed.get("is_page_question"))
        except Exception as exc:
            logger.warning(
                "agent_page_question_check_failed",
                extra={
                    "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                    "model": self.settings.openai_model,
                    "error_type": type(exc).__name__,
                    "status_code": self._openai_error_status_code(exc),
                },
                exc_info=self._should_log_openai_exc_info(exc),
            )
            return False

    async def _page_explain(
        self, *, payload: AgentMessageRequest, plan: AgentPlan
    ) -> AgentMessageResponse:
        if plan.source == "context_fallback" or not self.settings.openai_api_key:
            answer = self._page_explain_fallback(payload.context, payload.message)
        else:
            context_text = self._format_page_context_for_ai(payload.context)
            try:
                answer = await self._openai_page_answer(
                    message=payload.message, context_text=context_text
                )
            except Exception as exc:
                logger.warning(
                    "agent_page_explain_failed",
                    extra={
                        "error_type": type(exc).__name__,
                        "status_code": self._openai_error_status_code(exc),
                        "model": self.settings.openai_model,
                    },
                    exc_info=self._should_log_openai_exc_info(exc),
                )
                answer = self._page_explain_fallback(payload.context, payload.message)

        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="page_explain",
            message=str(
                answer.get("answer")
                or self._page_explain_fallback(payload.context, payload.message)[
                    "answer"
                ]
            ),
            suggestions=[
                "Объясни эту цифру подробнее",
                "Покажи, из какого API это пришло",
                "Какие данные здесь предварительные?",
            ],
            warnings=[
                str(item) for item in answer.get("warnings", []) if str(item).strip()
            ],
            audit={
                **self._audit(plan),
                "page_path": str((payload.context or {}).get("path") or ""),
                "used_sources": [
                    str(item)
                    for item in answer.get("used_sources", [])
                    if str(item).strip()
                ],
            },
        )

    @staticmethod
    def _can_answer_page_metric_from_context(payload: AgentMessageRequest) -> bool:
        context = payload.context if isinstance(payload.context, dict) else {}
        message_digits = AgentService._digits_only(payload.message)
        selected_digits = AgentService._digits_only(context.get("selected_text"))
        if len(message_digits) < 3 and len(selected_digits) < 3:
            return False
        return (
            AgentService._money_summary_page_fallback(context, payload.message)
            is not None
        )

    async def _openai_page_answer(
        self, *, message: str, context_text: str
    ) -> dict[str, Any]:
        request_payload = {
            "model": self.settings.openai_model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "Ты аналитик интерфейса WB Seller Portal. Пользователь спрашивает про текущую страницу, "
                        "видимую цифру, формулу или источник данных. Отвечай только по переданному page_context. "
                        "Если точную формулу или поле нельзя доказать из context, прямо скажи это. "
                        "Объясняй по-русски: где число видно, из какого endpoint/поля оно вероятно пришло, "
                        "как считается, какие данные предварительные или финальные. Не выдумывай факты."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": message, "page_context": context_text},
                        ensure_ascii=False,
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "seller_portal_page_explanation",
                    "strict": True,
                    "schema": self.OPENAI_PAGE_ANSWER_SCHEMA,
                }
            },
            "max_output_tokens": 4096,
        }
        started_at = perf_counter()
        last_error: Exception | None = None
        for attempt in range(OPENAI_MAX_ATTEMPTS):
            try:
                async with httpx.AsyncClient(
                    timeout=min(float(self.settings.openai_timeout_seconds), 60.0)
                ) as client:
                    response = await client.post(
                        self.OPENAI_RESPONSES_URL,
                        headers={
                            "Authorization": f"Bearer {self.settings.openai_api_key}",
                            "Content-Type": "application/json",
                        },
                        json=request_payload,
                    )
                    if self._should_retry_openai_response(response, attempt):
                        await self._sleep_before_openai_retry(response, attempt)
                        continue
                    response.raise_for_status()
                    data = response.json() if response.text else {}
                parsed = self._load_json_object(self._extract_openai_text(data))
                logger.info(
                    "agent_page_explain_succeeded",
                    extra={
                        "attempt": attempt + 1,
                        "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                        "model": self.settings.openai_model,
                    },
                )
                return {
                    "answer": self._nullable_text(parsed.get("answer")) or "",
                    "used_sources": parsed.get("used_sources")
                    if isinstance(parsed.get("used_sources"), list)
                    else [],
                    "warnings": parsed.get("warnings")
                    if isinstance(parsed.get("warnings"), list)
                    else [],
                    "confidence": str(parsed.get("confidence") or "medium"),
                }
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "agent_page_explain_attempt_failed",
                    extra={
                        "attempt": attempt + 1,
                        "elapsed_ms": round((perf_counter() - started_at) * 1000, 2),
                        "model": self.settings.openai_model,
                        "error_type": type(exc).__name__,
                        "status_code": self._openai_error_status_code(exc),
                    },
                    exc_info=self._should_log_openai_exc_info(exc),
                )
                if not self._should_retry_openai_exception(exc, attempt):
                    break
                await self._sleep_before_openai_retry(None, attempt)
        if last_error:
            raise last_error
        raise RuntimeError("page_explain_failed")

    @staticmethod
    def _should_retry_openai_response(response: httpx.Response, attempt: int) -> bool:
        return (
            attempt + 1 < OPENAI_MAX_ATTEMPTS
            and response.status_code in OPENAI_RETRYABLE_STATUS_CODES
        )

    @staticmethod
    def _should_retry_openai_exception(exc: Exception, attempt: int) -> bool:
        if attempt + 1 >= OPENAI_MAX_ATTEMPTS:
            return False
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code in OPENAI_RETRYABLE_STATUS_CODES
        return isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.NetworkError,
                httpx.ReadTimeout,
                httpx.TimeoutException,
            ),
        )

    @staticmethod
    def _should_log_openai_exc_info(exc: Exception) -> bool:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code not in OPENAI_RETRYABLE_STATUS_CODES
        return not isinstance(
            exc,
            (
                httpx.ConnectError,
                httpx.NetworkError,
                httpx.ReadTimeout,
                httpx.TimeoutException,
            ),
        )

    @staticmethod
    def _openai_error_status_code(exc: Exception) -> int | None:
        if isinstance(exc, httpx.HTTPStatusError):
            return exc.response.status_code
        return None

    @staticmethod
    def _openai_error_code(exc: Exception | None) -> str | None:
        if not isinstance(exc, httpx.HTTPStatusError):
            return None
        try:
            body = exc.response.json() if exc.response.text else {}
        except ValueError:
            return None
        error = body.get("error") if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return None
        code = error.get("code") or error.get("type")
        return str(code) if code else None

    def _planner_error_message(self, exc: Exception | None) -> str:
        status_code = self._openai_error_status_code(exc) if exc else None
        error_code = self._openai_error_code(exc)
        if status_code == 429 and error_code == "insufficient_quota":
            return (
                "AI-оператор временно недоступен: исчерпана квота OpenAI. "
                "Проверьте billing/лимиты OpenAI API и повторите команду."
            )
        if status_code == 429:
            return (
                "AI-оператор временно перегружен или ограничен лимитом OpenAI. "
                "Повторите команду позже."
            )
        return (
            "AI-планировщик временно недоступен. Проверьте OPENAI_API_KEY, "
            "модель и сетевой доступ backend."
        )

    @staticmethod
    def _openai_retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after")
            if retry_after:
                try:
                    return max(0.0, min(float(retry_after), OPENAI_RETRY_MAX_SECONDS))
                except ValueError:
                    pass
        return min(
            OPENAI_RETRY_BASE_SECONDS * (2**attempt),
            OPENAI_RETRY_MAX_SECONDS,
        )

    async def _sleep_before_openai_retry(
        self, response: httpx.Response | None, attempt: int
    ) -> None:
        await asyncio.sleep(self._openai_retry_delay(response, attempt))

    @staticmethod
    def _planner_context(context: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(context, dict):
            return {}

        def text(value: Any, limit: int = 240) -> str:
            normalized = " ".join(str(value or "").split())
            return normalized[:limit]

        headings = (
            context.get("headings") if isinstance(context.get("headings"), list) else []
        )
        numbers = (
            context.get("visible_number_context")
            if isinstance(context.get("visible_number_context"), list)
            else []
        )
        recent_api = (
            context.get("recent_api")
            if isinstance(context.get("recent_api"), list)
            else []
        )

        compact_numbers: list[str] = []
        for item in numbers[:10]:
            if isinstance(item, dict):
                compact_numbers.append(text(item.get("text")))
            else:
                compact_numbers.append(text(item))

        compact_api: list[dict[str, Any]] = []
        for item in recent_api[:12]:
            if not isinstance(item, dict):
                continue
            compact_api.append(
                {
                    "method": text(item.get("method"), 12),
                    "path": text(item.get("path"), 180),
                    "status": item.get("status"),
                }
            )

        return {
            "path": text(context.get("path"), 220),
            "search": text(context.get("search"), 220),
            "selected_text": text(context.get("selected_text"), 300),
            "headings": [text(item, 180) for item in headings[:10]],
            "visible_text": text(context.get("visible_text"), 2000),
            "visible_number_context": [item for item in compact_numbers if item],
            "recent_api": compact_api,
        }

    @staticmethod
    def _format_page_context_for_ai(context: dict[str, Any]) -> str:
        try:
            text = json.dumps(context or {}, ensure_ascii=False, default=str)
        except TypeError:
            text = json.dumps({"context": str(context)}, ensure_ascii=False)
        max_len = 24000
        if len(text) > max_len:
            return f"{text[:max_len]}\n...context truncated..."
        return text

    @staticmethod
    def _page_explain_fallback(
        context: dict[str, Any], message: str = ""
    ) -> dict[str, Any]:
        if not isinstance(context, dict):
            context = {}
        money_answer = AgentService._money_summary_page_fallback(context, message)
        if money_answer:
            return money_answer

        headings = context.get("headings") if isinstance(context, dict) else []
        recent_api = context.get("recent_api") if isinstance(context, dict) else []
        selected = str(context.get("selected_text") or "").strip()
        path = str(context.get("path") or "")
        sources: list[str] = []
        if isinstance(recent_api, list):
            for item in recent_api[:8]:
                if isinstance(item, dict):
                    endpoint = str(item.get("path") or "").strip()
                    status = str(item.get("status") or "").strip()
                    if endpoint:
                        sources.append(f"{endpoint} ({status})" if status else endpoint)
        heading_text = (
            ", ".join(str(item) for item in headings[:5])
            if isinstance(headings, list)
            else ""
        )
        selected_text = f" Выделенный текст: {selected}." if selected else ""
        source_text = (
            "; ".join(sources) if sources else "в snapshot нет списка endpointов"
        )
        return {
            "answer": (
                f"Я вижу текущую страницу {path or 'без указанного пути'}. "
                f"Заголовки страницы: {heading_text or 'не переданы'}.{selected_text} "
                f"Последние источники данных: {source_text}. "
                "Точную формулу по этому fallback-ответу подтверждать нельзя: нужен ответ AI по page context "
                "или более конкретный вопрос с выбранной цифрой."
            ),
            "used_sources": sources,
            "warnings": [
                "Точный разбор формулы не подтверждён: сработал fallback без AI-анализа."
            ],
            "confidence": "low",
        }

    @staticmethod
    def _money_summary_page_fallback(
        context: dict[str, Any], message: str
    ) -> dict[str, Any] | None:
        recent_api = (
            context.get("recent_api")
            if isinstance(context.get("recent_api"), list)
            else []
        )
        if not recent_api:
            return None

        requested_digits = AgentService._digits_only(message)
        visible_digits = AgentService._visible_context_digits(context)
        candidates: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        for item in recent_api:
            if not isinstance(item, dict):
                continue
            endpoint = str(item.get("path") or "")
            if "/money/summary" not in endpoint:
                continue
            fields = AgentService._api_snapshot_field_map(item)
            net_profit = AgentService._field_float(
                fields,
                "expense_breakdown.net_profit_after_all_expenses",
                "kpis.net_profit_after_all_expenses",
                "profit_cascade.totals.net_profit_after_all_expenses",
            )
            if net_profit is None:
                continue
            rounded_digits = AgentService._digits_only(str(round(net_profit)))
            score = 1
            if AgentService._digits_match(requested_digits, rounded_digits):
                score += 20
            if any(
                AgentService._digits_match(rounded_digits, digits)
                for digits in visible_digits
            ):
                score += 10
            candidates.append((score, item, fields))
        if not candidates:
            return None

        _, snapshot, fields = max(candidates, key=lambda candidate: candidate[0])
        endpoint = str(snapshot.get("path") or "/money/summary")
        method = str(snapshot.get("method") or "GET").upper()
        net_profit = AgentService._field_float(
            fields,
            "expense_breakdown.net_profit_after_all_expenses",
            "kpis.net_profit_after_all_expenses",
            "profit_cascade.totals.net_profit_after_all_expenses",
        )
        revenue = AgentService._field_float(
            fields,
            "expense_breakdown.revenue_final",
            "kpis.revenue_final",
            "kpis.revenue",
        )
        total_expenses = AgentService._field_float(
            fields,
            "expense_breakdown.total_expenses",
            "profit_cascade.totals.total_expenses",
        )
        margin = AgentService._field_float(
            fields, "kpis.margin_after_overhead_percent", "kpis.margin_percent"
        )
        financial_final = fields.get(
            "meta.data_trust.financial_final", fields.get("trust.financial_final")
        )
        reconciliation_status = fields.get("finance_reconciliation.status")
        target_digits = AgentService._digits_only(str(round(net_profit or 0)))
        visible_label = AgentService._visible_number_label(
            context,
            target_digits,
        ) or AgentService._visible_text_label(
            context,
            target_digits,
        )
        visible_label = visible_label.rstrip(" .")

        sources = [
            f"{method} {endpoint}",
            f"API field: expense_breakdown.net_profit_after_all_expenses = {net_profit}",
        ]
        answer_parts = []
        if visible_label:
            answer_parts.append(
                f"В текущем page context эта цифра видна рядом с метрикой: {visible_label}."
            )
        if net_profit is not None:
            answer_parts.append(
                "Источник числа: "
                f"{method} {endpoint}, поле expense_breakdown.net_profit_after_all_expenses = {net_profit}. "
                f"В интерфейсе оно округляется до {AgentService._format_money(net_profit)} ₽."
            )
        if (
            revenue is not None
            and total_expenses is not None
            and net_profit is not None
        ):
            calculated = revenue - total_expenses
            sources.extend(
                [
                    f"API field: expense_breakdown.revenue_final = {revenue}",
                    f"API field: expense_breakdown.total_expenses = {total_expenses}",
                ]
            )
            if abs(calculated - net_profit) <= 0.05:
                answer_parts.append(
                    "Формула по переданным полям: "
                    f"expense_breakdown.revenue_final ({revenue}) - "
                    f"expense_breakdown.total_expenses ({total_expenses}) = {calculated} "
                    f"→ {AgentService._format_money(calculated)} ₽."
                )
            else:
                answer_parts.append(
                    "В snapshot есть revenue_final и total_expenses, но их разница не совпала с net_profit_after_all_expenses "
                    f"({revenue} - {total_expenses} = {calculated}, поле прибыли = {net_profit})."
                )
        if margin is not None:
            sources.append(f"API field: kpis.margin_after_overhead_percent = {margin}")
            answer_parts.append(
                f"Маржа рядом с метрикой берётся из KPI-поля около {margin:.2f}%."
            )

        warnings = [
            "OpenAI-анализ временно не выполнился; использован проверяемый fallback по API snapshot текущей страницы."
        ]
        if financial_final is False:
            warnings.append(
                "meta.data_trust.financial_final = false: финансовые данные ещё предварительные."
            )
            sources.append("API field: meta.data_trust.financial_final = false")
        if reconciliation_status and str(reconciliation_status).lower() not in {
            "ok",
            "success",
            "passed",
            "none",
        }:
            warnings.append(
                f"finance_reconciliation.status = {reconciliation_status}: есть предупреждение по сверке финансов."
            )
            sources.append(
                f"API field: finance_reconciliation.status = {reconciliation_status}"
            )

        return {
            "answer": " ".join(answer_parts),
            "used_sources": sources,
            "warnings": warnings,
            "confidence": "medium",
        }

    @staticmethod
    def _api_snapshot_field_map(snapshot: dict[str, Any]) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for group_name in ("priority_fields", "fields"):
            group = snapshot.get(group_name)
            if isinstance(group, dict):
                fields.update({str(key): value for key, value in group.items()})
                continue
            if not isinstance(group, list):
                continue
            for field in group:
                if not isinstance(field, dict):
                    continue
                path = str(field.get("path") or "").strip()
                if path and "value" in field:
                    fields[path] = field.get("value")
        return fields

    @staticmethod
    def _field_float(fields: dict[str, Any], *paths: str) -> float | None:
        for path in paths:
            value = fields.get(path)
            if isinstance(value, bool) or value is None:
                continue
            try:
                return float(str(value).replace(" ", "").replace(",", "."))
            except ValueError:
                continue
        return None

    @staticmethod
    def _digits_only(value: Any) -> str:
        return "".join(char for char in str(value or "") if char.isdigit())

    @staticmethod
    def _digits_match(left: str, right: str) -> bool:
        if len(left) < 3 or len(right) < 3:
            return False
        return left in right or right in left

    @staticmethod
    def _format_money(value: float) -> str:
        return f"{round(value):,}".replace(",", " ")

    @staticmethod
    def _visible_context_digits(context: dict[str, Any]) -> list[str]:
        numbers = context.get("visible_number_context")
        if not isinstance(numbers, list):
            return []
        digits: list[str] = []
        for item in numbers[:30]:
            if isinstance(item, dict):
                text = str(item.get("text") or "")
            else:
                text = str(item or "")
            only_digits = AgentService._digits_only(text)
            if len(only_digits) >= 3:
                digits.append(only_digits)
        return digits

    @staticmethod
    def _visible_number_label(context: dict[str, Any], target_digits: str) -> str:
        numbers = context.get("visible_number_context")
        if not isinstance(numbers, list):
            return ""
        for item in numbers[:30]:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
                digits = AgentService._digits_only(text)
                if target_digits and not AgentService._digits_match(
                    target_digits, digits
                ):
                    continue
                before = str(item.get("before") or "").strip()
                after = str(item.get("after") or "").strip()
                return " ".join(part for part in [before, text, after] if part)
            text = str(item or "").strip()
            digits = AgentService._digits_only(text)
            if text and (
                not target_digits or AgentService._digits_match(target_digits, digits)
            ):
                return text
        return ""

    @staticmethod
    def _visible_text_label(context: dict[str, Any], target_digits: str) -> str:
        if len(target_digits) < 3:
            return ""
        text = str(context.get("visible_text") or "")
        if not text:
            return ""
        digit_positions: list[int] = []
        digit_stream_parts: list[str] = []
        for index, char in enumerate(text):
            if char.isdigit():
                digit_positions.append(index)
                digit_stream_parts.append(char)
        digit_stream = "".join(digit_stream_parts)
        stream_index = digit_stream.find(target_digits)
        if stream_index < 0:
            return ""
        start_index = digit_positions[stream_index]
        end_index = digit_positions[
            min(stream_index + len(target_digits) - 1, len(digit_positions) - 1)
        ]
        label_start = AgentService._nearby_metric_label_start(text, start_index)
        if label_start is not None:
            snippet_start = label_start
            snippet_end = min(len(text), end_index + 70)
            return " ".join(text[snippet_start:snippet_end].split())
        snippet_start = max(0, start_index - 90)
        snippet_end = min(len(text), end_index + 90)
        return " ".join(text[snippet_start:snippet_end].split())

    @staticmethod
    def _nearby_metric_label_start(text: str, value_start_index: int) -> int | None:
        labels = [
            "Чистая прибыль",
            "Выручка",
            "Маржа",
            "Расходы",
            "К перечислению",
            "Комиссии WB",
            "Реклама",
            "Себестоимость",
        ]
        prefix_start = max(0, value_start_index - 180)
        prefix = text[prefix_start:value_start_index]
        normalized_prefix = prefix.lower()
        best_index: int | None = None
        for label in labels:
            index = normalized_prefix.rfind(label.lower())
            if index < 0:
                continue
            absolute = prefix_start + index
            if best_index is None or absolute > best_index:
                best_index = absolute
        return best_index

    async def create_manual_task(
        self,
        session: AsyncSession,
        *,
        payload: dict[str, Any],
        user_id: int,
    ) -> Any:
        if self.portal is None:
            from app.services.portal import PortalService

            self.portal = PortalService()
        request = PortalManualActionCreateRequest.model_validate(payload)
        return await self.portal.create_manual_action(
            session, payload=request, user_id=user_id
        )

    def _need_product_response(
        self,
        plan: AgentPlan,
        *,
        products: list[AgentProductRef],
        next_intent: AgentIntent,
    ) -> AgentMessageResponse:
        return AgentMessageResponse(
            status="needs_input",
            mode=self._mode(plan),
            intent=plan.intent,
            message="С каким товаром работаем? Выберите товар из списка или уточните поисковый запрос.",
            products=products,
            actions=[
                AgentUIAction(
                    type="open_product_picker",
                    title="Выбрать товар",
                    payload={
                        "intent": next_intent,
                        "search_query": plan.search_query or "",
                    },
                )
            ],
            audit=self._audit(plan),
        )

    def _navigation_response(
        self, plan: AgentPlan, href: str, title: str, message: str
    ) -> AgentMessageResponse:
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent=plan.intent,
            message=message,
            actions=[AgentUIAction(type="navigate", title=title, href=href)],
            audit=self._audit(plan),
        )

    async def _search_products(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        query: str | None,
        limit: int,
    ) -> list[AgentProductRef]:
        stmt = (
            select(WBProductCard)
            .where(WBProductCard.account_id == account_id)
            .order_by(
                WBProductCard.updated_at.desc().nullslast(), WBProductCard.id.desc()
            )
            .limit(max(1, min(int(limit), 20)))
        )
        normalized = str(query or "").strip()
        if normalized.isdigit():
            nm_id = self._coerce_nm_id(normalized)
            if nm_id is None:
                return []
            stmt = stmt.where(WBProductCard.nm_id == nm_id)
        elif normalized:
            pattern = f"%{normalized}%"
            stmt = stmt.where(
                or_(
                    WBProductCard.title.ilike(pattern),
                    WBProductCard.vendor_code.ilike(pattern),
                    WBProductCard.brand.ilike(pattern),
                    WBProductCard.subject_name.ilike(pattern),
                    cast(WBProductCard.nm_id, String).ilike(pattern),
                )
            )
        rows = list((await session.execute(stmt)).scalars())
        return [self._product_ref(row) for row in rows]

    async def _get_product(
        self, session: AsyncSession, *, account_id: int, nm_id: int
    ) -> WBProductCard | None:
        safe_nm_id = self._coerce_nm_id(nm_id)
        if safe_nm_id is None:
            return None
        return await session.scalar(
            select(WBProductCard).where(
                WBProductCard.account_id == account_id,
                WBProductCard.nm_id == safe_nm_id,
            )
        )

    @staticmethod
    def _coerce_nm_id(value: int | str | None) -> int | None:
        try:
            nm_id = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if nm_id < MIN_WB_NM_ID or nm_id > MAX_DB_INT32:
            return None
        return nm_id

    @staticmethod
    def _product_ref(row: WBProductCard) -> AgentProductRef:
        thumbnail = None
        photos = row.photos
        if isinstance(photos, list) and photos:
            first = photos[0]
            if isinstance(first, dict):
                thumbnail = (
                    first.get("big")
                    or first.get("c516x688")
                    or first.get("tm")
                    or first.get("url")
                )
            elif isinstance(first, str):
                thumbnail = first
        elif isinstance(photos, dict):
            thumbnail = (
                photos.get("big")
                or photos.get("c516x688")
                or photos.get("tm")
                or photos.get("url")
            )
        return AgentProductRef(
            nm_id=int(row.nm_id),
            vendor_code=row.vendor_code,
            title=row.title,
            brand=row.brand,
            subject_name=row.subject_name,
            thumbnail_url=str(thumbnail) if thumbnail else None,
        )

    @staticmethod
    def _title_guard_warning(reason: str) -> str:
        messages = {
            "candidate_regressed_confirmed_business_tokens": "Новое название может потерять важные подтверждённые признаки товара.",
            "current_title_already_strict_valid": "Текущее название уже проходит строгую проверку, а новое выглядит слабее.",
            "candidate_not_materially_better": "Новое название не выглядит заметно лучше текущего.",
            "candidate_not_safer": "Новое название не выглядит безопаснее текущего.",
            "missing_title": "Не хватает текущего или нового названия для проверки.",
        }
        return messages.get(
            reason, "Новое название требует ручной проверки перед применением."
        )

    @staticmethod
    def _extract_openai_text(payload: dict[str, Any]) -> str:
        direct = payload.get("output_text")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        output = payload.get("output")
        if isinstance(output, list):
            parts: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                for block in item.get("content") or []:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        parts.append(block["text"])
            if parts:
                return "\n".join(parts).strip()
        return ""

    @staticmethod
    def _load_json_object(raw: str) -> dict[str, Any]:
        parsed = json.loads(str(raw or "{}").strip() or "{}")
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _export_href(
        export_type: str, account_id: int, *, nm_id: int | None = None
    ) -> str:
        params: dict[str, Any] = {"account_id": account_id}
        if nm_id is not None:
            params["nm_id"] = int(nm_id)
        return f"/export/{export_type}.xlsx?{urlencode(params)}"

    @staticmethod
    def _mode(plan: AgentPlan) -> str:
        if plan.source in {"ai", "ui"}:
            return "ai"
        return "ai_fallback"

    @staticmethod
    def _audit(plan: AgentPlan) -> dict[str, Any]:
        return {
            "planner": plan.source,
            "confidence": plan.confidence,
            "direct_marketplace_writes": False,
            "tool_policy": "ai_planner_with_allow_listed_backend_tools_only",
        }

    def _planner_unavailable_response(self, plan: AgentPlan) -> AgentMessageResponse:
        status = "blocked" if plan.source == "ai_unconfigured" else "error"
        return AgentMessageResponse(
            status=status,
            mode="ai_fallback",
            intent="help",
            message=plan.assistant_message
            or "AI-оператор сейчас недоступен. Проверьте настройки OpenAI на backend.",
            suggestions=[
                "Проверьте OPENAI_API_KEY",
                "Проверьте OPENAI_MODEL",
                "Повторите команду после восстановления AI",
            ],
            audit=self._audit(plan),
        )
