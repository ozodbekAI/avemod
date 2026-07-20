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
    AgentToolCallRequest,
    AgentToolsResponse,
    AgentToolSpec,
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
    "reputation_agent",
    "scenario_create",
    "pricing_agent",
    "insights_report",
    "strategy_advice",
    "module_navigate",
    "open_logistics",
    "open_action_center",
    "open_checker",
    "open_pricing",
    "open_stock_control",
    "open_money",
    "api_action",
]


AGENT_MODULE_CATALOG: dict[str, dict[str, str]] = {
    "dashboard": {
        "title": "Обзор",
        "href": "/dashboard",
        "description": "Главный контур: деньги, задачи и товары.",
    },
    "action_center": {
        "title": "Фокус на сегодня",
        "href": "/action-center",
        "description": "Очередь задач, рекомендаций и ручных проверок.",
    },
    "actions": {
        "title": "Действия",
        "href": "/actions",
        "description": "Рекомендации и действия операционного контура.",
    },
    "money": {
        "title": "Деньги",
        "href": "/money",
        "description": "Прибыль, расходы, сверка и денежные показатели.",
    },
    "logistics": {
        "title": "Логистика",
        "href": "/logistics",
        "description": "Отгрузки, доставка, возвраты и логистические риски.",
    },
    "products": {
        "title": "Товары",
        "href": "/products",
        "description": "Список товаров и Product 360.",
    },
    "cards": {
        "title": "Карточки",
        "href": "/cards",
        "description": "Карточки товаров и контент.",
    },
    "checker": {
        "title": "Проверка карточек",
        "href": "/checker",
        "description": "Проверка качества карточек WB.",
    },
    "data_fix": {
        "title": "Качество данных",
        "href": "/data-fix",
        "description": "Блокеры данных и исправление проблем.",
    },
    "results": {
        "title": "Результаты",
        "href": "/results",
        "description": "История результатов и эффектов действий.",
    },
    "stock_control": {
        "title": "Остатки и поставки",
        "href": "/stock-control",
        "description": "Управление остатками, поставками и stock operations.",
    },
    "stock": {
        "title": "Остатки",
        "href": "/stock",
        "description": "Складские остатки и snapshots.",
    },
    "pricing": {
        "title": "Цены",
        "href": "/pricing",
        "description": "Цены, промо, безопасная маржа и симуляции.",
    },
    "purchase_plan": {
        "title": "План закупок",
        "href": "/purchase-plan",
        "description": "План закупок и потребность в поставках.",
    },
    "ads": {
        "title": "Реклама",
        "href": "/ads",
        "description": "Рекламные кампании, статистика и эффективность.",
    },
    "analytics": {
        "title": "Аналитика",
        "href": "/analytics",
        "description": "Воронки, регионы и аналитические отчёты.",
    },
    "operations": {
        "title": "Операции",
        "href": "/operations",
        "description": "Заказы, продажи, поставки и синхронизации.",
    },
    "costs": {
        "title": "Себестоимость",
        "href": "/costs",
        "description": "Загрузка, проверка и исправление себестоимости.",
    },
    "expenses": {
        "title": "Расходы",
        "href": "/expenses",
        "description": "Операционные расходы и детализация затрат.",
    },
    "finance": {
        "title": "Финансы WB",
        "href": "/finance",
        "description": "Финансовые отчёты WB и строки отчётов.",
    },
    "marts": {
        "title": "Витрины данных",
        "href": "/marts",
        "description": "Marts, дневные агрегаты и сверки.",
    },
    "catalog": {
        "title": "Каталог",
        "href": "/catalog",
        "description": "Каталог товаров и справочные данные.",
    },
    "claims": {
        "title": "Претензии",
        "href": "/claims",
        "description": "Претензии, кейсы, доказательства и апелляции.",
    },
    "reputation": {
        "title": "Отзывы",
        "href": "/reputation",
        "description": "Отзывы, вопросы, чаты и ответы покупателям.",
    },
    "ab_tests": {
        "title": "A/B тесты",
        "href": "/ab-tests",
        "description": "Эксперименты и тестирование изменений.",
    },
    "grouping": {
        "title": "Группировка",
        "href": "/grouping",
        "description": "Группы товаров и кандидаты группировки.",
    },
    "photo_studio": {
        "title": "Фотостудия",
        "href": "/photo-studio",
        "description": "AI-фото, проекты, ассеты и версии изображений.",
    },
    "settings": {
        "title": "Настройки",
        "href": "/settings",
        "description": "Настройки аккаунта, бизнеса и модулей.",
    },
    "doctor": {
        "title": "Доктор",
        "href": "/doctor",
        "description": "Диагностика проблем и здоровья портала.",
    },
    "admin": {
        "title": "Админ",
        "href": "/admin",
        "description": "Административная зона.",
    },
    "problem_rules": {
        "title": "Правила проблем",
        "href": "/admin/problem-rules",
        "description": "Администрирование правил проблем и действий.",
    },
}


def _account_query() -> dict[str, str]:
    return {"account_id": "{account_id}"}


def _account_body(**extra: Any) -> dict[str, Any]:
    return {"account_id": "{account_id}", **extra}


AGENT_API_ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "dashboard.data_health": {
        "title": "Проверить здоровье данных",
        "description": "Получить snapshot покрытия данных, синхронизаций и блокеров.",
        "method": "GET",
        "path": "/dashboard/data-health",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "dashboard",
    },
    "portal.overview": {
        "title": "Сводка портала",
        "description": "Получить общий snapshot портала по выбранному аккаунту.",
        "method": "GET",
        "path": "/portal/overview",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "dashboard",
    },
    "portal.modules_health": {
        "title": "Здоровье модулей",
        "description": "Проверить состояние подключённых модулей портала.",
        "method": "GET",
        "path": "/portal/modules/health",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "doctor",
    },
    "portal.actions.list": {
        "title": "Список задач",
        "description": "Получить задачи и рекомендации из Центра действий.",
        "method": "GET",
        "path": "/portal/actions",
        "query": {**_account_query(), "limit": 20, "offset": 0},
        "write_policy": "read",
        "module_key": "action_center",
    },
    "products.list": {
        "title": "Список товаров",
        "description": "Получить первые товары аккаунта для проверки ассортимента.",
        "method": "GET",
        "path": "/portal/products",
        "query": {**_account_query(), "limit": 20, "offset": 0},
        "write_policy": "read",
        "module_key": "products",
    },
    "money.summary": {
        "title": "Денежная сводка",
        "description": "Получить сводку по прибыли, выручке, расходам и сверке.",
        "method": "GET",
        "path": "/money/summary",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "money",
    },
    "money.expenses_breakdown": {
        "title": "Структура расходов",
        "description": "Получить breakdown расходов по денежному контуру.",
        "method": "GET",
        "path": "/money/expenses/breakdown",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "expenses",
    },
    "analytics.overview": {
        "title": "Аналитика продаж",
        "description": "Получить обзор аналитики по товарам, регионам и трендам.",
        "method": "GET",
        "path": "/analytics/overview",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "analytics",
    },
    "analytics.funnel": {
        "title": "Воронка карточек",
        "description": "Получить строки воронки карточек.",
        "method": "GET",
        "path": "/analytics/funnel",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "analytics",
    },
    "analytics.regions": {
        "title": "Продажи по регионам",
        "description": "Получить аналитику региональных продаж.",
        "method": "GET",
        "path": "/analytics/regions",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "analytics",
    },
    "analytics.export_products_csv": {
        "title": "CSV аналитики товаров",
        "description": "Скачать CSV по товарной аналитике.",
        "method": "GET",
        "path": "/analytics/export.csv",
        "query": {**_account_query(), "dataset": "products"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "analytics",
    },
    "analytics.export_regions_csv": {
        "title": "CSV регионов",
        "description": "Скачать CSV по региональной аналитике.",
        "method": "GET",
        "path": "/analytics/export.csv",
        "query": {**_account_query(), "dataset": "regions"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "analytics",
    },
    "analytics.export_trend_csv": {
        "title": "CSV тренда",
        "description": "Скачать CSV с трендом аналитики.",
        "method": "GET",
        "path": "/analytics/export.csv",
        "query": {**_account_query(), "dataset": "trend"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "analytics",
    },
    "logistics.overview": {
        "title": "Обзор логистики",
        "description": "Получить overview логистики: задачи, склады, товары и риски.",
        "method": "GET",
        "path": "/portal/logistics/overview",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "logistics",
    },
    "logistics.export_tasks_csv": {
        "title": "CSV задач логистики",
        "description": "Скачать CSV логистических задач.",
        "method": "GET",
        "path": "/portal/logistics/export.csv",
        "query": {**_account_query(), "dataset": "tasks"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "logistics",
    },
    "logistics.export_products_csv": {
        "title": "CSV товаров логистики",
        "description": "Скачать CSV логистических показателей товаров.",
        "method": "GET",
        "path": "/portal/logistics/export.csv",
        "query": {**_account_query(), "dataset": "products"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "logistics",
    },
    "logistics.export_warehouses_csv": {
        "title": "CSV складов",
        "description": "Скачать CSV по складам и логистике.",
        "method": "GET",
        "path": "/portal/logistics/export.csv",
        "query": {**_account_query(), "dataset": "warehouses"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "logistics",
    },
    "logistics.export_shipment_csv": {
        "title": "CSV отгрузок",
        "description": "Скачать CSV по отгрузкам.",
        "method": "GET",
        "path": "/portal/logistics/export.csv",
        "query": {**_account_query(), "dataset": "shipment"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "logistics",
    },
    "reputation.summary": {
        "title": "Сводка отзывов",
        "description": "Получить сводку по отзывам, вопросам и репутации.",
        "method": "GET",
        "path": "/portal/reputation/summary",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "reputation",
    },
    "reputation.inbox": {
        "title": "Входящие отзывы",
        "description": "Получить список отзывов, вопросов и чатов.",
        "method": "GET",
        "path": "/portal/reputation/inbox",
        "query": {**_account_query(), "item_type": "all", "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "reputation",
    },
    "reputation.drafts": {
        "title": "Черновики ответов",
        "description": "Получить черновики ответов покупателям.",
        "method": "GET",
        "path": "/portal/reputation/drafts",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "reputation",
    },
    "reputation.chats": {
        "title": "Чаты покупателей",
        "description": "Получить список чатов покупателей.",
        "method": "GET",
        "path": "/portal/reputation/chats",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "reputation",
    },
    "reputation.learning": {
        "title": "Обучение репутации",
        "description": "Получить состояние базы обучения ответов.",
        "method": "GET",
        "path": "/portal/reputation/learning",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "reputation",
    },
    "reputation.sync": {
        "title": "Синхронизировать отзывы",
        "description": "Запустить ручную синхронизацию отзывов, вопросов и репутационных данных.",
        "method": "POST",
        "path": "/portal/reputation/sync",
        "query": _account_query(),
        "confirm_required": True,
        "success_message": "Синхронизация репутации запущена.",
        "write_policy": "confirmed_mutation",
        "module_key": "reputation",
    },
    "reputation.learning_reset": {
        "title": "Сбросить обучение",
        "description": "Сбросить накопленное обучение ответов. Требует подтверждения.",
        "method": "POST",
        "path": "/portal/reputation/learning/reset",
        "query": _account_query(),
        "confirm_required": True,
        "success_message": "Обучение репутации сброшено.",
        "write_policy": "confirmed_mutation",
        "module_key": "reputation",
    },
    "ads.efficiency": {
        "title": "Эффективность рекламы",
        "description": "Получить эффективность рекламных кампаний.",
        "method": "GET",
        "path": "/ads/efficiency",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "ads",
    },
    "ads.campaigns": {
        "title": "Рекламные кампании",
        "description": "Получить список рекламных кампаний.",
        "method": "GET",
        "path": "/ads/campaigns",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "ads",
    },
    "ads.stats": {
        "title": "Статистика рекламы",
        "description": "Получить рекламную статистику.",
        "method": "GET",
        "path": "/ads/stats",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "ads",
    },
    "pricing.safety": {
        "title": "Безопасность цен",
        "description": "Получить товары с рисками цены, маржи и промо.",
        "method": "GET",
        "path": "/pricing/safety",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "pricing",
    },
    "stock_control.status": {
        "title": "Статус остатков",
        "description": "Получить статус модуля управления остатками.",
        "method": "GET",
        "path": "/portal/stock-control/status",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "stock_control",
    },
    "stock_control.settings": {
        "title": "Настройки остатков",
        "description": "Получить настройки управления остатками.",
        "method": "GET",
        "path": "/portal/stock-control/settings",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "stock_control",
    },
    "stock_control.runs": {
        "title": "Запуски остатков",
        "description": "Получить последние запуски stock-control.",
        "method": "GET",
        "path": "/portal/stock-control/runs",
        "query": {**_account_query(), "limit": 20, "offset": 0},
        "write_policy": "read",
        "module_key": "stock_control",
    },
    "stockops.runs": {
        "title": "StockOps запуски",
        "description": "Получить историю операций по остаткам.",
        "method": "GET",
        "path": "/portal/stockops/runs",
        "query": {**_account_query(), "limit": 20, "offset": 0},
        "write_policy": "read",
        "module_key": "stock_control",
    },
    "stockops.return_excess": {
        "title": "Запустить возврат излишков",
        "description": "Запустить stock operation return_excess. Требует подтверждения.",
        "method": "POST",
        "path": "/portal/stockops/run",
        "body": _account_body(run_type="return_excess", payload={}),
        "confirm_required": True,
        "success_message": "StockOps return_excess запущен.",
        "write_policy": "confirmed_mutation",
        "module_key": "stock_control",
    },
    "stockops.ship_from_hand": {
        "title": "Запустить поставку с рук",
        "description": "Запустить stock operation ship_from_hand. Требует подтверждения.",
        "method": "POST",
        "path": "/portal/stockops/run",
        "body": _account_body(run_type="ship_from_hand", payload={}),
        "confirm_required": True,
        "success_message": "StockOps ship_from_hand запущен.",
        "write_policy": "confirmed_mutation",
        "module_key": "stock_control",
    },
    "costs.rows": {
        "title": "Строки себестоимости",
        "description": "Получить строки ручной себестоимости.",
        "method": "GET",
        "path": "/costs/rows",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "costs",
    },
    "costs.missing": {
        "title": "Недостающая себестоимость",
        "description": "Получить товары без себестоимости.",
        "method": "GET",
        "path": "/costs/missing",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "costs",
    },
    "costs.template_xlsx": {
        "title": "Шаблон себестоимости XLSX",
        "description": "Скачать XLSX-шаблон для загрузки себестоимости.",
        "method": "GET",
        "path": "/costs/template",
        "query": {**_account_query(), "format": "xlsx", "mode": "all"},
        "action_type": "download_file",
        "write_policy": "download_only",
        "module_key": "costs",
    },
    "finance.reports": {
        "title": "Финансовые отчёты",
        "description": "Получить список финансовых отчётов WB.",
        "method": "GET",
        "path": "/finance/reports",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "finance",
    },
    "finance.report_rows": {
        "title": "Строки финансовых отчётов",
        "description": "Получить строки финансовых отчётов WB.",
        "method": "GET",
        "path": "/finance/report-rows",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "finance",
    },
    "inventory.purchase_plan": {
        "title": "План закупок",
        "description": "Получить план закупок и потребность в поставках.",
        "method": "GET",
        "path": "/inventory/purchase-plan",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "purchase_plan",
    },
    "inventory.stock_snapshots": {
        "title": "Снимки остатков",
        "description": "Получить складские snapshots.",
        "method": "GET",
        "path": "/stocks/snapshots",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "stock",
    },
    "data_quality.summary": {
        "title": "Сводка качества данных",
        "description": "Получить summary проблем качества данных.",
        "method": "GET",
        "path": "/dq/issues/summary",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "data_fix",
    },
    "data_quality.issues": {
        "title": "Проблемы качества данных",
        "description": "Получить список проблем качества данных.",
        "method": "GET",
        "path": "/dq/issues",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "data_fix",
    },
    "data_quality.run": {
        "title": "Запустить проверку данных",
        "description": "Запустить проверку качества данных. Требует подтверждения.",
        "method": "POST",
        "path": "/dq/run",
        "body": _account_body(),
        "confirm_required": True,
        "success_message": "Проверка качества данных запущена.",
        "write_policy": "confirmed_mutation",
        "module_key": "data_fix",
    },
    "sync.runs": {
        "title": "Запуски синхронизаций",
        "description": "Получить историю синхронизаций.",
        "method": "GET",
        "path": "/sync/runs",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "operations",
    },
    "sync.cursors": {
        "title": "Курсоры синхронизаций",
        "description": "Получить состояние курсоров синхронизаций.",
        "method": "GET",
        "path": "/sync/cursors",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "operations",
    },
    "sync.trigger_product_cards": {
        "title": "Синхронизировать карточки",
        "description": "Запустить ручную синхронизацию карточек товаров.",
        "method": "POST",
        "path": "/sync/trigger",
        "body": _account_body(domain="product_cards", force_full=False),
        "confirm_required": True,
        "success_message": "Синхронизация карточек запущена.",
        "write_policy": "confirmed_mutation",
        "module_key": "operations",
    },
    "sync.trigger_stocks": {
        "title": "Синхронизировать остатки",
        "description": "Запустить ручную синхронизацию остатков.",
        "method": "POST",
        "path": "/sync/trigger",
        "body": _account_body(domain="stocks", force_full=False),
        "confirm_required": True,
        "success_message": "Синхронизация остатков запущена.",
        "write_policy": "confirmed_mutation",
        "module_key": "operations",
    },
    "sync.trigger_prices": {
        "title": "Синхронизировать цены",
        "description": "Запустить ручную синхронизацию цен.",
        "method": "POST",
        "path": "/sync/trigger",
        "body": _account_body(domain="prices", force_full=False),
        "confirm_required": True,
        "success_message": "Синхронизация цен запущена.",
        "write_policy": "confirmed_mutation",
        "module_key": "operations",
    },
    "sync.trigger_reputation": {
        "title": "Синхронизировать репутацию",
        "description": "Запустить синхронизацию отзывов и вопросов через sync layer.",
        "method": "POST",
        "path": "/sync/trigger",
        "body": _account_body(domain="reputation", force_full=False),
        "confirm_required": True,
        "success_message": "Синхронизация репутации запущена.",
        "write_policy": "confirmed_mutation",
        "module_key": "reputation",
    },
    "marts.refresh": {
        "title": "Обновить витрины данных",
        "description": "Пересобрать marts для аккаунта. Требует прав администратора и подтверждения.",
        "method": "POST",
        "path": "/marts/refresh",
        "body": _account_body(),
        "confirm_required": True,
        "success_message": "Обновление витрин данных запущено.",
        "write_policy": "confirmed_admin_mutation",
        "module_key": "marts",
    },
    "marts.sku_daily": {
        "title": "Marts по SKU",
        "description": "Получить дневные агрегаты SKU.",
        "method": "GET",
        "path": "/marts/sku-daily",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "marts",
    },
    "marts.business_daily": {
        "title": "Marts бизнес-день",
        "description": "Получить дневные бизнес-агрегаты.",
        "method": "GET",
        "path": "/marts/business-daily",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "marts",
    },
    "photo.status": {
        "title": "Статус фотостудии",
        "description": "Получить состояние AI-фотостудии.",
        "method": "GET",
        "path": "/portal/photo/status",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "photo_studio",
    },
    "photo.projects": {
        "title": "Проекты фотостудии",
        "description": "Получить список проектов AI-фотостудии.",
        "method": "GET",
        "path": "/portal/photo/projects",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "photo_studio",
    },
    "photo.jobs": {
        "title": "Задачи фотостудии",
        "description": "Получить jobs AI-фотостудии.",
        "method": "GET",
        "path": "/portal/photo/jobs",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "photo_studio",
    },
    "experiments.list": {
        "title": "A/B эксперименты",
        "description": "Получить список экспериментов.",
        "method": "GET",
        "path": "/portal/experiments",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "ab_tests",
    },
    "experiments.settings": {
        "title": "Настройки экспериментов",
        "description": "Получить настройки A/B экспериментов.",
        "method": "GET",
        "path": "/portal/experiments/settings",
        "query": _account_query(),
        "write_policy": "read",
        "module_key": "ab_tests",
    },
    "claims.cases": {
        "title": "Кейсы претензий",
        "description": "Получить список кейсов претензий.",
        "method": "GET",
        "path": "/portal/cases",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "claims",
    },
    "claims.scans": {
        "title": "Сканы претензий",
        "description": "Получить запуски поиска претензий.",
        "method": "GET",
        "path": "/portal/claims/scans",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "claims",
    },
    "claims.candidates": {
        "title": "Кандидаты претензий",
        "description": "Получить кандидатов на претензии.",
        "method": "GET",
        "path": "/portal/claims/candidates",
        "query": {**_account_query(), "limit": 50, "offset": 0},
        "write_policy": "read",
        "module_key": "claims",
    },
    "claims.scan_start": {
        "title": "Запустить поиск претензий",
        "description": "Запустить автоматический scan претензий. Требует подтверждения.",
        "method": "POST",
        "path": "/portal/claims/scans",
        "body": _account_body(detector_types=["all"], force=False),
        "confirm_required": True,
        "success_message": "Поиск претензий запущен.",
        "write_policy": "confirmed_mutation",
        "module_key": "claims",
    },
}


AGENT_API_ACTION_CATALOG.update(
    {
        "portal.action.update_status": {
            "title": "Обновить статус задачи",
            "description": "Изменить статус задачи Центра действий по action_id.",
            "method": "PATCH",
            "path": "/portal/actions/{action_id}",
            "body": {"status": "{status}"},
            "body_from_params": [
                "comment",
                "status_reason",
                "assigned_to_user_id",
                "deadline_at",
                "review_status",
                "event_type",
            ],
            "required_params": ["action_id", "status"],
            "confirm_required": True,
            "success_message": "Статус задачи обновлён.",
            "write_policy": "confirmed_mutation",
            "module_key": "action_center",
        },
        "portal.problem.recheck": {
            "title": "Перепроверить проблему",
            "description": "Запустить recheck problem instance по problem_id.",
            "method": "POST",
            "path": "/portal/problems/{problem_id}/recheck",
            "required_params": ["problem_id"],
            "confirm_required": True,
            "success_message": "Проблема отправлена на перепроверку.",
            "write_policy": "confirmed_mutation",
            "module_key": "action_center",
        },
        "control.action.update_status": {
            "title": "Обновить рекомендацию",
            "description": "Изменить статус рекомендации control tower по action_id.",
            "method": "PATCH",
            "path": "/actions/{action_id}",
            "body": {"status": "{status}"},
            "body_from_params": ["assigned_to", "comment"],
            "required_params": ["action_id", "status"],
            "confirm_required": True,
            "success_message": "Рекомендация обновлена.",
            "write_policy": "confirmed_mutation",
            "module_key": "actions",
        },
        "card_quality.issue.status": {
            "title": "Статус проблемы карточки",
            "description": "Обновить статус проблемы качества карточки.",
            "method": "PATCH",
            "path": "/portal/card-quality/issues/{issue_id}/status",
            "query": _account_query(),
            "body": {"status": "{status}"},
            "body_from_params": ["reason", "fixed_value", "postponed_until"],
            "required_params": ["issue_id", "status"],
            "confirm_required": True,
            "success_message": "Статус проблемы карточки обновлён.",
            "write_policy": "confirmed_mutation",
            "module_key": "checker",
        },
        "card_quality.issue.preview": {
            "title": "Предпросмотр исправления карточки",
            "description": "Получить preview исправления проблемы карточки.",
            "method": "POST",
            "path": "/portal/card-quality/issues/{issue_id}/preview",
            "query": _account_query(),
            "body": {},
            "body_from_params": ["fixed_value", "reason"],
            "required_params": ["issue_id"],
            "success_message": "Предпросмотр исправления подготовлен.",
            "write_policy": "preview",
            "module_key": "checker",
        },
        "card_quality.issue.save_draft": {
            "title": "Сохранить черновик исправления",
            "description": "Сохранить draft исправления карточки.",
            "method": "POST",
            "path": "/portal/card-quality/issues/{issue_id}/draft",
            "query": _account_query(),
            "body": {},
            "body_from_params": ["fixed_value", "reason"],
            "required_params": ["issue_id"],
            "confirm_required": True,
            "success_message": "Черновик исправления сохранён.",
            "write_policy": "confirmed_mutation",
            "module_key": "checker",
        },
        "card_quality.issue.accept_local": {
            "title": "Принять исправление локально",
            "description": "Зафиксировать исправление карточки локально, без прямой записи WB.",
            "method": "POST",
            "path": "/portal/card-quality/issues/{issue_id}/accept-local",
            "query": _account_query(),
            "body": {},
            "body_from_params": ["fixed_value", "reason"],
            "required_params": ["issue_id"],
            "confirm_required": True,
            "success_message": "Исправление принято локально.",
            "write_policy": "confirmed_mutation",
            "module_key": "checker",
        },
        "card_quality.issue.mark_fixed": {
            "title": "Отметить проблему исправленной",
            "description": "Отметить проблему карточки как исправленную.",
            "method": "POST",
            "path": "/portal/card-quality/issues/{issue_id}/mark-fixed",
            "query": _account_query(),
            "body": {},
            "body_from_params": ["fixed_value", "reason"],
            "required_params": ["issue_id"],
            "confirm_required": True,
            "success_message": "Проблема отмечена исправленной.",
            "write_policy": "confirmed_mutation",
            "module_key": "checker",
        },
        "reputation.draft.approve": {
            "title": "Одобрить черновик ответа",
            "description": "Одобрить черновик ответа покупателю по draft_id.",
            "method": "POST",
            "path": "/portal/reputation/drafts/{draft_id}/approve",
            "query": _account_query(),
            "required_params": ["draft_id"],
            "confirm_required": True,
            "success_message": "Черновик ответа одобрен.",
            "write_policy": "confirmed_mutation",
            "module_key": "reputation",
        },
        "reputation.draft.reject": {
            "title": "Отклонить черновик ответа",
            "description": "Отклонить черновик ответа покупателю по draft_id.",
            "method": "POST",
            "path": "/portal/reputation/drafts/{draft_id}/reject",
            "query": _account_query(),
            "body": {},
            "body_from_params": ["reason"],
            "required_params": ["draft_id"],
            "confirm_required": True,
            "success_message": "Черновик ответа отклонён.",
            "write_policy": "confirmed_mutation",
            "module_key": "reputation",
        },
        "reputation.draft.regenerate": {
            "title": "Перегенерировать черновик ответа",
            "description": "Создать новый вариант черновика ответа по draft_id.",
            "method": "POST",
            "path": "/portal/reputation/drafts/{draft_id}/regenerate",
            "query": _account_query(),
            "body": {},
            "body_from_params": ["reason"],
            "required_params": ["draft_id"],
            "confirm_required": True,
            "success_message": "Черновик ответа отправлен на перегенерацию.",
            "write_policy": "confirmed_mutation",
            "module_key": "reputation",
        },
        "reputation.draft.publish": {
            "title": "Опубликовать ответ",
            "description": "Опубликовать одобренный ответ покупателю по draft_id.",
            "method": "POST",
            "path": "/portal/reputation/drafts/{draft_id}/publish",
            "query": _account_query(),
            "body": {"confirm": True},
            "body_from_params": ["text"],
            "required_params": ["draft_id"],
            "confirm_required": True,
            "success_message": "Ответ отправлен на публикацию.",
            "write_policy": "confirmed_marketplace_mutation",
            "module_key": "reputation",
        },
        "reputation.item.no_reply_needed": {
            "title": "Ответ не требуется",
            "description": "Отметить отзыв/вопрос как не требующий ответа.",
            "method": "POST",
            "path": "/portal/reputation/items/{item_id}/no-reply-needed",
            "query": _account_query(),
            "body": {"confirm": True},
            "body_from_params": ["reason"],
            "required_params": ["item_id"],
            "confirm_required": True,
            "success_message": "Элемент отмечен как не требующий ответа.",
            "write_policy": "confirmed_mutation",
            "module_key": "reputation",
        },
        "reputation.learning.toggle": {
            "title": "Переключить обучение ответов",
            "description": "Включить или выключить обучение репутационного агента.",
            "method": "POST",
            "path": "/portal/reputation/learning/toggle",
            "query": _account_query(),
            "body": {"enabled": "{enabled}"},
            "required_params": ["enabled"],
            "confirm_required": True,
            "success_message": "Настройка обучения обновлена.",
            "write_policy": "confirmed_mutation",
            "module_key": "reputation",
        },
        "reputation.learning.delete_entry": {
            "title": "Удалить запись обучения",
            "description": "Удалить запись обучения репутационного агента.",
            "method": "DELETE",
            "path": "/portal/reputation/learning/entries/{entry_id}",
            "query": _account_query(),
            "required_params": ["entry_id"],
            "confirm_required": True,
            "success_message": "Запись обучения удалена.",
            "write_policy": "confirmed_mutation",
            "module_key": "reputation",
        },
        "experiments.start": {
            "title": "Запустить эксперимент",
            "description": "Запустить A/B эксперимент по experiment_id.",
            "method": "POST",
            "path": "/portal/experiments/{experiment_id}/start",
            "query": _account_query(),
            "required_params": ["experiment_id"],
            "confirm_required": True,
            "success_message": "Эксперимент запущен.",
            "write_policy": "confirmed_mutation",
            "module_key": "ab_tests",
        },
        "experiments.cancel": {
            "title": "Отменить эксперимент",
            "description": "Отменить A/B эксперимент по experiment_id.",
            "method": "POST",
            "path": "/portal/experiments/{experiment_id}/cancel",
            "query": _account_query(),
            "required_params": ["experiment_id"],
            "confirm_required": True,
            "success_message": "Эксперимент отменён.",
            "write_policy": "confirmed_mutation",
            "module_key": "ab_tests",
        },
        "experiments.evaluate": {
            "title": "Оценить эксперимент",
            "description": "Запустить оценку A/B эксперимента.",
            "method": "POST",
            "path": "/portal/experiments/{experiment_id}/evaluate",
            "query": _account_query(),
            "required_params": ["experiment_id"],
            "confirm_required": True,
            "success_message": "Оценка эксперимента запущена.",
            "write_policy": "confirmed_mutation",
            "module_key": "ab_tests",
        },
        "photo.job.retry": {
            "title": "Повторить задачу фотостудии",
            "description": "Повторить failed job AI-фотостудии.",
            "method": "POST",
            "path": "/portal/photo/jobs/{job_id}/retry",
            "query": _account_query(),
            "required_params": ["job_id"],
            "confirm_required": True,
            "success_message": "Задача фотостудии отправлена на повтор.",
            "write_policy": "confirmed_mutation",
            "module_key": "photo_studio",
        },
        "photo.job.cancel": {
            "title": "Отменить задачу фотостудии",
            "description": "Отменить job AI-фотостудии.",
            "method": "POST",
            "path": "/portal/photo/jobs/{job_id}/cancel",
            "query": _account_query(),
            "required_params": ["job_id"],
            "confirm_required": True,
            "success_message": "Задача фотостудии отменена.",
            "write_policy": "confirmed_mutation",
            "module_key": "photo_studio",
        },
        "photo.version.review": {
            "title": "Оценить версию фото",
            "description": "Поставить статус версии фото: preferred, approved или rejected.",
            "method": "POST",
            "path": "/portal/photo/projects/{project_id}/versions/{version_id}/review",
            "query": _account_query(),
            "body": {"status": "{status}"},
            "body_from_params": ["reason"],
            "required_params": ["project_id", "version_id", "status"],
            "confirm_required": True,
            "success_message": "Статус версии фото обновлён.",
            "write_policy": "confirmed_mutation",
            "module_key": "photo_studio",
        },
        "photo.version.apply_wb": {
            "title": "Применить фото в WB",
            "description": "Отправить выбранную версию фото в WB после подтверждения.",
            "method": "POST",
            "path": "/portal/photo/projects/{project_id}/versions/{version_id}/apply-wb",
            "query": _account_query(),
            "body": {"confirm": True},
            "required_params": ["project_id", "version_id"],
            "confirm_required": True,
            "success_message": "Версия фото отправлена на применение в WB.",
            "write_policy": "confirmed_marketplace_mutation",
            "module_key": "photo_studio",
        },
        "stock_control.run.retry": {
            "title": "Повторить stock-control запуск",
            "description": "Повторить запуск управления остатками по run_id.",
            "method": "POST",
            "path": "/portal/stock-control/runs/{run_id}/retry",
            "query": _account_query(),
            "required_params": ["run_id"],
            "confirm_required": True,
            "success_message": "Stock-control запуск отправлен на повтор.",
            "write_policy": "confirmed_mutation",
            "module_key": "stock_control",
        },
        "stock_control.run.cancel": {
            "title": "Отменить stock-control запуск",
            "description": "Отменить запуск управления остатками по run_id.",
            "method": "POST",
            "path": "/portal/stock-control/runs/{run_id}/cancel",
            "query": _account_query(),
            "required_params": ["run_id"],
            "confirm_required": True,
            "success_message": "Stock-control запуск отменён.",
            "write_policy": "confirmed_mutation",
            "module_key": "stock_control",
        },
        "claims.candidate.status": {
            "title": "Статус кандидата претензии",
            "description": "Обновить статус кандидата претензии.",
            "method": "PATCH",
            "path": "/portal/claims/candidates/{candidate_id}/status",
            "query": _account_query(),
            "body": {"status": "{status}"},
            "body_from_params": ["reason"],
            "required_params": ["candidate_id", "status"],
            "confirm_required": True,
            "success_message": "Статус кандидата претензии обновлён.",
            "write_policy": "confirmed_mutation",
            "module_key": "claims",
        },
        "claims.candidate.create_case": {
            "title": "Создать кейс из кандидата",
            "description": "Создать claim case из кандидата претензии.",
            "method": "POST",
            "path": "/portal/claims/candidates/{candidate_id}/create-case",
            "query": _account_query(),
            "required_params": ["candidate_id"],
            "confirm_required": True,
            "success_message": "Кейс претензии создан.",
            "write_policy": "confirmed_mutation",
            "module_key": "claims",
        },
        "claims.case.proof_check": {
            "title": "Проверить доказательства кейса",
            "description": "Запустить proof-check по claim case.",
            "method": "POST",
            "path": "/portal/cases/{case_id}/proof-check",
            "body": {},
            "required_params": ["case_id"],
            "confirm_required": True,
            "success_message": "Проверка доказательств запущена.",
            "write_policy": "confirmed_mutation",
            "module_key": "claims",
        },
        "grouping.candidate.status": {
            "title": "Статус кандидата группировки",
            "description": "Обновить статус кандидата группировки товаров.",
            "method": "PATCH",
            "path": "/portal/grouping/candidates/{candidate_id}/status",
            "query": _account_query(),
            "body": {"status": "{status}"},
            "body_from_params": ["reason"],
            "required_params": ["candidate_id", "status"],
            "confirm_required": True,
            "success_message": "Статус кандидата группировки обновлён.",
            "write_policy": "confirmed_mutation",
            "module_key": "grouping",
        },
        "sync.cursor.run_now": {
            "title": "Запустить cursor sync",
            "description": "Запустить синхронизацию по конкретному cursor_id.",
            "method": "POST",
            "path": "/sync/cursors/{cursor_id}/run-now",
            "required_params": ["cursor_id"],
            "confirm_required": True,
            "success_message": "Синхронизация cursor запущена.",
            "write_policy": "confirmed_mutation",
            "module_key": "operations",
        },
        "sync.cursor.reset": {
            "title": "Сбросить cursor sync",
            "description": "Сбросить cursor синхронизации по cursor_id.",
            "method": "POST",
            "path": "/sync/cursors/{cursor_id}/reset",
            "required_params": ["cursor_id"],
            "confirm_required": True,
            "success_message": "Cursor синхронизации сброшен.",
            "write_policy": "confirmed_admin_mutation",
            "module_key": "operations",
        },
    }
)


AGENT_API_ACTION_PARAM_SCHEMA: dict[str, Any] = {
    "type": ["object", "null"],
    "additionalProperties": False,
    "properties": {
        "action_id": {"type": ["integer", "null"], "minimum": 1},
        "problem_id": {"type": ["integer", "null"], "minimum": 1},
        "issue_id": {"type": ["integer", "null"], "minimum": 1},
        "entry_id": {"type": ["integer", "null"], "minimum": 1},
        "experiment_id": {"type": ["integer", "null"], "minimum": 1},
        "job_id": {"type": ["integer", "null"], "minimum": 1},
        "project_id": {"type": ["integer", "null"], "minimum": 1},
        "version_id": {"type": ["integer", "null"], "minimum": 1},
        "run_id": {"type": ["integer", "null"], "minimum": 1},
        "candidate_id": {"type": ["integer", "null"], "minimum": 1},
        "case_id": {"type": ["integer", "null"], "minimum": 1},
        "cursor_id": {"type": ["integer", "null"], "minimum": 1},
        "assigned_to": {"type": ["integer", "null"], "minimum": 1},
        "assigned_to_user_id": {"type": ["integer", "null"], "minimum": 1},
        "draft_id": {"type": ["string", "null"], "maxLength": 200},
        "item_id": {"type": ["string", "null"], "maxLength": 300},
        "status": {"type": ["string", "null"], "maxLength": 80},
        "comment": {"type": ["string", "null"], "maxLength": 1000},
        "reason": {"type": ["string", "null"], "maxLength": 1000},
        "status_reason": {"type": ["string", "null"], "maxLength": 1000},
        "fixed_value": {"type": ["string", "null"], "maxLength": 1000},
        "postponed_until": {"type": ["string", "null"], "maxLength": 80},
        "deadline_at": {"type": ["string", "null"], "maxLength": 80},
        "review_status": {"type": ["string", "null"], "maxLength": 80},
        "event_type": {"type": ["string", "null"], "maxLength": 120},
        "text": {"type": ["string", "null"], "maxLength": 4000},
        "enabled": {"type": ["boolean", "null"]},
    },
}


AGENT_TOOL_REGISTRY: dict[str, dict[str, Any]] = {
    "admin.answer": {
        "intent": "admin_answer",
        "title": "Ответ администратора",
        "description": "Ответить на общий вопрос, приветствие или совет по работе портала.",
        "required_args": [],
        "write_policy": "none",
    },
    "portal.navigate": {
        "intent": "module_navigate",
        "title": "Открыть модуль портала",
        "description": "Открыть любой известный раздел портала по module_key из module_catalog.",
        "required_args": ["module_key"],
        "write_policy": "none",
    },
    "product.search": {
        "intent": "product_search",
        "title": "Найти товары",
        "description": "Найти товары по названию, артикулу, бренду или nm_id.",
        "required_args": ["search_query"],
        "write_policy": "none",
    },
    "product.details": {
        "intent": "product_details",
        "title": "Открыть Product 360",
        "description": "Открыть карточку Product 360; если товар не выбран, запросить выбор товара.",
        "required_args": ["selected_nm_id_or_search_query"],
        "write_policy": "none",
    },
    "stock.export_xlsx": {
        "intent": "stock_export",
        "title": "Выгрузить остатки XLSX",
        "description": "Подготовить Excel по остаткам выбранного товара.",
        "required_args": ["selected_nm_id_or_search_query"],
        "write_policy": "download_only",
    },
    "card.title_update_preview": {
        "intent": "title_update",
        "title": "Предпросмотр изменения названия",
        "description": "Подготовить безопасный предпросмотр изменения названия и ручную задачу.",
        "required_args": ["selected_nm_id_or_search_query", "new_title_optional"],
        "write_policy": "preview_manual_task_first",
    },
    "page.explain": {
        "intent": "page_explain",
        "title": "Объяснить текущую страницу",
        "description": "Объяснить видимую цифру, источник, формулу или API snapshot текущей страницы.",
        "required_args": ["page_context"],
        "write_policy": "none",
    },
    "reputation.open": {
        "intent": "reputation_agent",
        "title": "Открыть репутацию",
        "description": "Открыть отзывы, вопросы, чаты, ответы и репутационные задачи.",
        "required_args": [],
        "write_policy": "none",
    },
    "scenario.create_manual_task": {
        "intent": "scenario_create",
        "title": "Создать AI-сценарий как задачу",
        "description": "Подготовить AI-сценарий ответов/автоматизации как безопасную ручную задачу.",
        "required_args": ["selected_nm_id_or_search_query", "scenario_request"],
        "write_policy": "manual_task_first",
    },
    "pricing.open": {
        "intent": "pricing_agent",
        "title": "Открыть цены",
        "description": "Открыть контур цен, промо, маржи и безопасных симуляций.",
        "required_args": [],
        "write_policy": "none",
    },
    "insights.create_report_task": {
        "intent": "insights_report",
        "title": "Создать AI-отчёт как задачу",
        "description": "Подготовить R&D/маркетинговый/логистический/NPD отчёт как ручную задачу.",
        "required_args": ["selected_nm_id_or_search_query", "report_request"],
        "write_policy": "manual_task_first",
    },
    "strategy.advice": {
        "intent": "strategy_advice",
        "title": "Разобрать комплексную стратегию",
        "description": (
            "Ответить как e-commerce стратег: разобрать цель, приоритеты, алгоритм, "
            "ограничения, stop-loss/recovery и метрики проверки."
        ),
        "required_args": ["strategy_request"],
        "write_policy": "advice_plus_safe_read_actions",
    },
    "logistics.open": {
        "intent": "open_logistics",
        "title": "Открыть логистику",
        "description": "Открыть логистический контур.",
        "required_args": [],
        "write_policy": "none",
    },
    "action_center.open": {
        "intent": "open_action_center",
        "title": "Открыть Центр действий",
        "description": "Открыть очередь задач и рекомендаций.",
        "required_args": [],
        "write_policy": "none",
    },
    "checker.open": {
        "intent": "open_checker",
        "title": "Открыть проверку карточек",
        "description": "Открыть проверку качества карточек.",
        "required_args": [],
        "write_policy": "none",
    },
    "stock_control.open": {
        "intent": "open_stock_control",
        "title": "Открыть управление остатками",
        "description": "Открыть управление остатками и поставками.",
        "required_args": [],
        "write_policy": "none",
    },
    "money.open": {
        "intent": "open_money",
        "title": "Открыть деньги",
        "description": "Открыть денежный контур.",
        "required_args": [],
        "write_policy": "none",
    },
    "portal.api_action": {
        "intent": "api_action",
        "title": "Выполнить действие портала",
        "description": (
            "Выполнить allow-listed API action из api_action_catalog: read-only запрос, "
            "download или подтверждаемую mutation операцию."
        ),
        "required_args": ["api_action_key"],
        "write_policy": "read_download_or_confirmed_mutation",
    },
}


@dataclass(frozen=True, slots=True)
class AgentPlan:
    intent: AgentIntent
    tool_name: str | None = None
    search_query: str | None = None
    selected_nm_id: int | None = None
    new_title: str | None = None
    module_key: str | None = None
    api_action_key: str | None = None
    api_action_params: dict[str, Any] | None = None
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
            "tool_name",
            "search_query",
            "selected_nm_id",
            "new_title",
            "module_key",
            "api_action_key",
            "api_action_params",
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
                    "formulas, sources, or why a metric has its value. Use reputation_agent for reviews/questions, "
                    "scenario_create for safe AI сценарии that must become manual tasks, pricing_agent for smart price "
                    "analysis/navigation, insights_report for R&D/marketing/logistics/NPD report requests, "
                    "strategy_advice for complex business strategies with rules, priorities, price/stock/review tradeoffs, "
                    "module_navigate for opening a known portal module from module_catalog, and open_logistics "
                    "for logistics workflows."
                ),
            },
            "tool_name": {
                "type": ["string", "null"],
                "enum": [None, *AGENT_TOOL_REGISTRY.keys()],
                "description": (
                    "MCP-style backend tool name selected from tool_registry. "
                    "Use null only for help when no tool should run. Never invent a tool."
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
            "module_key": {
                "type": ["string", "null"],
                "enum": [None, *AGENT_MODULE_CATALOG.keys()],
                "description": (
                    "Portal module key from module_catalog when intent is module_navigate, otherwise null. "
                    "Never invent a module key."
                ),
            },
            "api_action_key": {
                "type": ["string", "null"],
                "enum": [None, *AGENT_API_ACTION_CATALOG.keys()],
                "description": (
                    "Allow-listed API action key from api_action_catalog when tool_name is portal.api_action. "
                    "Use null for all other tools. Never invent an action key."
                ),
            },
            "api_action_params": {
                **AGENT_API_ACTION_PARAM_SCHEMA,
                "description": (
                    "Parameters for api_action_key, such as action_id, issue_id, draft_id, "
                    "status, reason, enabled or other allowed fields. Use null when no "
                    "parameter is needed. Never invent ids."
                ),
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

    def list_tools(self) -> AgentToolsResponse:
        return AgentToolsResponse(
            tools=[
                AgentToolSpec(
                    name=name,
                    intent=spec["intent"],
                    title=str(spec["title"]),
                    description=str(spec["description"]),
                    required_args=[
                        str(item) for item in spec.get("required_args", [])
                    ],
                    write_policy=str(spec.get("write_policy") or "none"),
                    input_schema=self._tool_input_schema(name),
                )
                for name, spec in AGENT_TOOL_REGISTRY.items()
            ],
            modules=AGENT_MODULE_CATALOG,
            api_actions=self._api_action_catalog_for_manifest(),
            direct_marketplace_writes=False,
        )

    async def execute_tool(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: "AuthUser",
        payload: AgentToolCallRequest,
    ) -> AgentMessageResponse:
        spec = AGENT_TOOL_REGISTRY.get(payload.tool_name)
        if spec is None:
            return AgentMessageResponse(
                status="blocked",
                mode="ai_fallback",
                intent="help",
                message="Инструмент не найден в registry. Выберите tool_name из /portal/agent/tools.",
                audit={
                    "planner": "tool_call",
                    "tool_name": payload.tool_name,
                    "direct_marketplace_writes": False,
                    "tool_policy": "unknown_tool_blocked",
                },
            )

        args = payload.arguments if isinstance(payload.arguments, dict) else {}
        intent = spec["intent"]
        plan = AgentPlan(
            intent=intent,
            tool_name=payload.tool_name,
            search_query=self._nullable_text(args.get("search_query")),
            selected_nm_id=self._nullable_int(args.get("selected_nm_id")),
            new_title=self._nullable_text(args.get("new_title")),
            module_key=self._nullable_text(args.get("module_key")),
            api_action_key=self._nullable_text(args.get("api_action_key")),
            api_action_params=self._api_action_params_from_args(args),
            confidence="high",
            source="tool_call",
            assistant_message=self._nullable_text(args.get("assistant_message")),
        )
        request_message = self._nullable_text(args.get("message")) or payload.tool_name
        request_context = (
            args.get("context") if isinstance(args.get("context"), dict) else payload.context
        )
        request = AgentMessageRequest(
            account_id=account_id,
            message=request_message,
            selected_nm_id=plan.selected_nm_id,
            new_title=plan.new_title,
            context=request_context,
        )
        return await self._execute_plan(
            session,
            account_id=account_id,
            role=role,
            user=user,
            payload=request,
            plan=plan,
        )

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

        return await self._execute_plan(
            session,
            account_id=account_id,
            role=role,
            user=user,
            payload=payload,
            plan=plan,
        )

    async def _execute_plan(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: "AuthUser",
        payload: AgentMessageRequest,
        plan: AgentPlan,
    ) -> AgentMessageResponse:
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
        if plan.intent == "reputation_agent":
            return self._reputation_agent(plan)
        if plan.intent == "scenario_create":
            return await self._scenario_create(
                session,
                account_id=account_id,
                role=role,
                user=user,
                plan=plan,
                request_text=payload.message,
            )
        if plan.intent == "pricing_agent":
            return self._pricing_agent(plan)
        if plan.intent == "insights_report":
            return await self._insights_report(
                session,
                account_id=account_id,
                role=role,
                user=user,
                plan=plan,
                request_text=payload.message,
            )
        if plan.intent == "strategy_advice":
            return self._strategy_advice(plan, account_id=account_id)
        if plan.intent == "module_navigate":
            return self._module_navigate_response(plan)
        if plan.intent == "open_logistics":
            return self._logistics_response(plan)
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
        if plan.intent == "api_action":
            return self._api_action_response(plan, account_id=account_id)
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
            "деньги, проверку карточек, отзывы, логистику, AI-сценарии, отчёты по инсайтам, "
            "Центр действий, запустить разрешённые действия портала или объяснить видимые цифры на текущей странице. "
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

    def _reputation_agent(self, plan: AgentPlan) -> AgentMessageResponse:
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="reputation_agent",
            message=(
                self._nullable_text(plan.assistant_message)
                or "Открыл контур репутации: отзывы, вопросы, ответы покупателям и задачи по карточкам."
            ),
            actions=[
                AgentUIAction(
                    type="navigate",
                    title="Репутация",
                    href="/reputation",
                    description="Отзывы, вопросы и работа с ответами.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="История задач",
                    href="/action-center",
                    description="Задачи и ручные проверки, созданные агентом.",
                ),
            ],
            suggestions=[
                "Создай сценарий ответов",
                "Подготовь отчёт по отзывам",
                "Открой Центр действий",
            ],
            audit=self._audit(plan),
        )

    async def _scenario_create(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: AuthUser,
        plan: AgentPlan,
        request_text: str,
    ) -> AgentMessageResponse:
        if plan.selected_nm_id is None:
            products = await self._search_products(
                session,
                account_id=account_id,
                query=plan.search_query,
                limit=self.PRODUCT_PICKER_LIMIT,
            )
            return self._need_product_response(
                plan,
                products=products,
                next_intent="scenario_create",
                payload_extra={
                    "draft_message": self._task_request_text(
                        request_text,
                        plan,
                        "Создать безопасный AI-сценарий для выбранного товара.",
                    )
                },
            )

        product = await self._get_product(
            session, account_id=account_id, nm_id=plan.selected_nm_id
        )
        if product is None:
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="scenario_create",
                message="Товар для сценария не найден или не относится к этому аккаунту.",
                audit=self._audit(plan),
            )

        if not self._can_create_manual_task(role):
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="scenario_create",
                message=(
                    "Я понял сценарий, но у вашей роли нет прав на создание задач. "
                    "Можно открыть раздел репутации и передать настройку менеджеру."
                ),
                products=[self._product_ref(product)],
                actions=[
                    AgentUIAction(type="navigate", title="Репутация", href="/reputation")
                ],
                audit=self._audit(plan),
            )

        request = self._task_request_text(
            request_text,
            plan,
            "Создать безопасный AI-сценарий для выбранного товара.",
        )
        description = self._task_description(
            "Запрос пользователя:",
            request,
            "Черновик агента:",
            self._nullable_text(plan.assistant_message)
            or (
                "Подготовить сценарий работы AI-оператора. Сценарий должен учитывать карточку товара, "
                "отзывы/вопросы покупателей, tone of voice бренда и требовать ручной проверки перед публикацией."
            ),
            "Правило безопасности:",
            "Не публиковать ответы и не менять данные WB без ручного подтверждения ответственного пользователя.",
        )
        action = self._manual_task_action(
            account_id=account_id,
            user=user,
            product=product,
            title="AI-сценарий для проверки",
            description=description,
            task_kind="agent_scenario",
            deadline_days=2,
        )
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="scenario_create",
            message=(
                "Сценарий подготовлен как безопасная задача. Я не публикую ответы и не меняю WB автоматически: "
                "сначала задача попадёт в ручную проверку."
            ),
            products=[self._product_ref(product)],
            actions=[
                action,
                AgentUIAction(
                    type="navigate",
                    title="Центр действий",
                    href="/action-center",
                    description="Проверить и запустить подготовленную задачу.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="Репутация",
                    href="/reputation",
                    description="Открыть отзывы и вопросы.",
                ),
            ],
            suggestions=[
                "Создать задачу",
                "Открыть отзывы",
                "Подготовь R&D отчёт",
            ],
            audit={**self._audit(plan), "write_policy": "manual_task_first"},
        )

    def _pricing_agent(self, plan: AgentPlan) -> AgentMessageResponse:
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="pricing_agent",
            message=(
                self._nullable_text(plan.assistant_message)
                or (
                    "Открыл контур цен. Здесь можно разбирать безопасную маржу, промо, риск скидок "
                    "и готовить ручные задачи на изменение цен."
                )
            ),
            actions=[
                AgentUIAction(
                    type="navigate",
                    title="Цены",
                    href="/pricing",
                    description="Безопасная маржа, цены и промо.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="Центр действий",
                    href="/action-center",
                    description="Задачи на ручную проверку цен.",
                ),
            ],
            suggestions=[
                "Проверь цену товара",
                "Создай сценарий умных цен",
                "Объясни маржу на странице",
            ],
            audit=self._audit(plan),
        )

    async def _insights_report(
        self,
        session: AsyncSession,
        *,
        account_id: int,
        role: str,
        user: AuthUser,
        plan: AgentPlan,
        request_text: str,
    ) -> AgentMessageResponse:
        if plan.selected_nm_id is None:
            products = await self._search_products(
                session,
                account_id=account_id,
                query=plan.search_query,
                limit=self.PRODUCT_PICKER_LIMIT,
            )
            return self._need_product_response(
                plan,
                products=products,
                next_intent="insights_report",
                payload_extra={
                    "draft_message": self._task_request_text(
                        request_text,
                        plan,
                        "Подготовить AI-отчёт по отзывам и бизнес-инсайтам выбранного товара.",
                    )
                },
            )

        product = await self._get_product(
            session, account_id=account_id, nm_id=plan.selected_nm_id
        )
        if product is None:
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="insights_report",
                message="Товар для отчёта не найден или не относится к этому аккаунту.",
                audit=self._audit(plan),
            )

        if not self._can_create_manual_task(role):
            return AgentMessageResponse(
                status="blocked",
                mode=self._mode(plan),
                intent="insights_report",
                message=(
                    "Отчёт требует создания задачи на обработку данных, но у вашей роли нет прав на создание задач."
                ),
                products=[self._product_ref(product)],
                actions=[
                    AgentUIAction(type="navigate", title="Репутация", href="/reputation")
                ],
                audit=self._audit(plan),
            )

        request = self._task_request_text(
            request_text,
            plan,
            "Подготовить AI-отчёт по отзывам и бизнес-инсайтам выбранного товара.",
        )
        description = self._task_description(
            "Запрос пользователя:",
            request,
            "Черновик агента:",
            self._nullable_text(plan.assistant_message)
            or (
                "Собрать инсайты из отзывов, вопросов, карточки товара и операционных данных. "
                "Отдельно выделить продуктовые доработки, маркетинговые формулировки, логистические риски "
                "и идеи для NPD."
            ),
            "Правило безопасности:",
            "Отчёт должен ссылаться только на доступные данные портала; недоказанные выводы помечать как гипотезы.",
        )
        action = self._manual_task_action(
            account_id=account_id,
            user=user,
            product=product,
            title="AI-отчёт по инсайтам товара",
            description=description,
            task_kind="agent_insights_report",
            deadline_days=2,
        )
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="insights_report",
            message=(
                "Подготовил задачу на AI-отчёт по товару. Отчёт должен опираться на отзывы, вопросы, карточку "
                "и операционные данные; непроверенные выводы будут идти как гипотезы."
            ),
            products=[self._product_ref(product)],
            actions=[
                action,
                AgentUIAction(
                    type="navigate",
                    title="Центр действий",
                    href="/action-center",
                    description="Проверить задачу отчёта.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="Отзывы",
                    href="/reputation",
                    description="Открыть исходный контур отзывов.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="Логистика",
                    href="/logistics",
                    description="Проверить логистические сигналы.",
                ),
            ],
            suggestions=[
                "Создать задачу",
                "Открыть отзывы",
                "Открыть логистику",
            ],
            audit={**self._audit(plan), "write_policy": "manual_task_first"},
        )

    def _logistics_response(self, plan: AgentPlan) -> AgentMessageResponse:
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="open_logistics",
            message=(
                self._nullable_text(plan.assistant_message)
                or "Открыл логистику: здесь можно искать слабые места доставки, упаковки, возвратов и отгрузок."
            ),
            actions=[
                AgentUIAction(
                    type="navigate",
                    title="Логистика",
                    href="/logistics",
                    description="Отгрузки, доставка, возвраты и логистические риски.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="Центр действий",
                    href="/action-center",
                    description="Задачи по логистическим проблемам.",
                ),
            ],
            suggestions=[
                "Сделай отчёт по логистике",
                "Открой задачи по логистике",
                "Объясни цифру на странице",
            ],
            audit=self._audit(plan),
        )

    def _strategy_advice(self, plan: AgentPlan, *, account_id: int) -> AgentMessageResponse:
        message = self._nullable_text(plan.assistant_message) or (
            "Я бы собрал стратегию в таком порядке:\n"
            "1. Сначала защитить наличие: если до нулевого остатка меньше 14 дней, не снижать цену и проверить поставку.\n"
            "2. Затем разделить товары по проблеме: падение заказов, слабая конверсия, избыток остатка, негативные отзывы.\n"
            "3. Для каждого товара задать мягкий дневной шаг цены, дневной кап и stop-loss по конверсии/заказам.\n"
            "4. Любое повышение цены делать только при запасе больше 21 дня, стабильной конверсии и отсутствии свежего негатива.\n"
            "5. Проверять эффект через 3-7 дней: заказы, конверсия в корзину, дни запаса, маржа и отзывы."
        )
        actions: list[AgentUIAction] = []
        for key in (
            "pricing.safety",
            "analytics.overview",
            "reputation.summary",
            "stock_control.status",
            "inventory.purchase_plan",
        ):
            action = self._api_action_from_catalog(key, account_id=account_id)
            if action is not None:
                actions.append(action)
        actions.extend(
            [
                AgentUIAction(
                    type="navigate",
                    title="Цены",
                    href="/pricing",
                    description="Проверить безопасную маржу и ценовые риски.",
                ),
                AgentUIAction(
                    type="navigate",
                    title="Аналитика",
                    href="/analytics",
                    description="Проверить воронку, регионы и тренды.",
                ),
            ]
        )
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="strategy_advice",
            message=message,
            actions=actions[:6],
            suggestions=[
                "Проверь товары с риском цены",
                "Покажи аналитику продаж",
                "Сделай стратегию для остатков",
            ],
            warnings=[
                "Стратегия не меняет цены и данные WB автоматически. Для изменений нужен отдельный preview/confirm/audit."
            ],
            audit={**self._audit(plan), "strategy_mode": "complex_ecommerce_advice"},
        )

    def _module_navigate_response(self, plan: AgentPlan) -> AgentMessageResponse:
        module = AGENT_MODULE_CATALOG.get(str(plan.module_key or ""))
        if module is None:
            return AgentMessageResponse(
                status="needs_input",
                mode=self._mode(plan),
                intent="module_navigate",
                message=(
                    "Не понял, какой раздел открыть. Напишите название раздела: товары, деньги, логистика, "
                    "реклама, аналитика, отзывы, настройки или другой модуль портала."
                ),
                suggestions=[
                    "Открой товары",
                    "Открой рекламу",
                    "Открой настройки",
                ],
                audit={**self._audit(plan), "module_key": plan.module_key},
            )
        title = module["title"]
        description = module["description"]
        href = module["href"]
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="module_navigate",
            message=(
                self._nullable_text(plan.assistant_message)
                or f"Открыл раздел «{title}». {description}"
            ),
            actions=[
                AgentUIAction(
                    type="navigate",
                    title=title,
                    href=href,
                    description=description,
                )
            ],
            suggestions=[
                "Объясни цифру на странице",
                "Найди товар",
                "Открой Центр действий",
            ],
            audit={**self._audit(plan), "module_key": plan.module_key},
        )

    def _api_action_response(
        self, plan: AgentPlan, *, account_id: int
    ) -> AgentMessageResponse:
        action_key = str(plan.api_action_key or "")
        spec = AGENT_API_ACTION_CATALOG.get(action_key)
        if spec is None:
            return AgentMessageResponse(
                status="needs_input",
                mode=self._mode(plan),
                intent="api_action",
                message=(
                    "Не понял, какое действие портала выполнить. Напишите конкретнее: "
                    "проверить деньги, синхронизировать отзывы, скачать CSV логистики, "
                    "запустить DQ-проверку, показать задачи или открыть нужный раздел."
                ),
                actions=[
                    AgentUIAction(
                        type="navigate",
                        title="Центр действий",
                        href="/action-center",
                        description="Открыть очередь задач и действий.",
                    )
                ],
                suggestions=[
                    "Синхронизируй отзывы",
                    "Скачай CSV по логистике",
                    "Запусти проверку качества данных",
                ],
                audit={**self._audit(plan), "api_action_key": plan.api_action_key},
            )

        params = plan.api_action_params or {}
        missing_params = self._missing_api_action_params(spec, params)
        if missing_params:
            missing = ", ".join(missing_params)
            return AgentMessageResponse(
                status="needs_input",
                mode=self._mode(plan),
                intent="api_action",
                message=(
                    f"Для действия «{spec['title']}» нужно уточнить параметры: {missing}. "
                    "Напишите их в сообщении или выберите объект в интерфейсе."
                ),
                actions=[
                    AgentUIAction(
                        type="navigate",
                        title="Открыть раздел",
                        href=AGENT_MODULE_CATALOG.get(
                            str(spec.get("module_key") or ""), {}
                        ).get("href", "/action-center"),
                        description=str(spec.get("description") or ""),
                    )
                ],
                suggestions=[
                    "Укажу ID и статус",
                    "Открой связанный раздел",
                    "Покажи задачи",
                ],
                audit={
                    **self._audit(plan),
                    "api_action_key": action_key,
                    "missing_params": missing_params,
                },
            )

        href = self._api_action_href(spec, account_id=account_id, params=params)
        payload: dict[str, Any] = {
            "api_action_key": action_key,
            "api_action_params": params,
            "write_policy": spec.get("write_policy", "read"),
            "success_message": spec.get("success_message")
            or f"Действие «{spec['title']}» выполнено.",
        }
        body = self._api_action_body(spec, account_id=account_id, params=params)
        if body:
            payload["body"] = body
        action_type = str(spec.get("action_type") or "api_request")
        action = AgentUIAction(
            type=action_type,  # type: ignore[arg-type]
            title=str(spec["title"]),
            description=str(spec.get("description") or ""),
            href=href,
            method=str(spec.get("method") or "GET"),  # type: ignore[arg-type]
            confirm_required=bool(spec.get("confirm_required")),
            payload=payload,
        )
        module = AGENT_MODULE_CATALOG.get(str(spec.get("module_key") or ""))
        actions = [action]
        if module is not None:
            actions.append(
                AgentUIAction(
                    type="navigate",
                    title=f"Открыть «{module['title']}»",
                    href=module["href"],
                    description=module["description"],
                )
            )
        policy = str(spec.get("write_policy") or "read")
        if policy == "read":
            message = (
                self._nullable_text(plan.assistant_message)
                or f"Готов выполнить запрос «{spec['title']}» и показать краткий результат в чате."
            )
        elif policy == "download_only":
            message = (
                self._nullable_text(plan.assistant_message)
                or f"Готов скачать файл «{spec['title']}»."
            )
        else:
            message = (
                self._nullable_text(plan.assistant_message)
                or (
                    f"Готов выполнить «{spec['title']}». Это действие меняет состояние портала, "
                    "поэтому перед запуском потребуется подтверждение."
                )
            )
        return AgentMessageResponse(
            mode=self._mode(plan),
            intent="api_action",
            message=message,
            actions=actions,
            suggestions=[
                "Объясни результат",
                "Открой связанный раздел",
                "Покажи задачи",
            ],
            warnings=[
                "Прямые записи в Wildberries не выполняются без отдельного подтверждения, аудита и прав пользователя."
            ]
            if policy != "read" and policy != "download_only"
            else [],
            audit={
                **self._audit(plan),
                "api_action_key": action_key,
                "write_policy": policy,
                "http_method": spec.get("method") or "GET",
                "path": spec.get("path"),
            },
        )

    def _api_action_from_catalog(
        self,
        action_key: str,
        *,
        account_id: int,
        params: dict[str, Any] | None = None,
    ) -> AgentUIAction | None:
        spec = AGENT_API_ACTION_CATALOG.get(action_key)
        if spec is None or self._missing_api_action_params(spec, params or {}):
            return None
        body = self._api_action_body(spec, account_id=account_id, params=params)
        payload: dict[str, Any] = {
            "api_action_key": action_key,
            "api_action_params": params or {},
            "write_policy": spec.get("write_policy", "read"),
            "success_message": spec.get("success_message")
            or f"Действие «{spec['title']}» выполнено.",
        }
        if body:
            payload["body"] = body
        return AgentUIAction(
            type=str(spec.get("action_type") or "api_request"),  # type: ignore[arg-type]
            title=str(spec["title"]),
            description=str(spec.get("description") or ""),
            href=self._api_action_href(spec, account_id=account_id, params=params),
            method=str(spec.get("method") or "GET"),  # type: ignore[arg-type]
            confirm_required=bool(spec.get("confirm_required")),
            payload=payload,
        )

    @staticmethod
    def _replace_plan(plan: AgentPlan, **updates: Any) -> AgentPlan:
        data = {
            "intent": plan.intent,
            "tool_name": plan.tool_name,
            "search_query": plan.search_query,
            "selected_nm_id": plan.selected_nm_id,
            "new_title": plan.new_title,
            "module_key": plan.module_key,
            "api_action_key": plan.api_action_key,
            "api_action_params": plan.api_action_params,
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
            tool_name=AgentService._tool_for_intent(payload.intent or "help"),
            search_query=str(payload.message or "").strip() or None,
            selected_nm_id=payload.selected_nm_id,
            new_title=payload.new_title,
            module_key=None,
            api_action_key=None,
            api_action_params=None,
            confidence="high",
            source="ui",
        )

    @staticmethod
    def _tool_for_intent(intent: AgentIntent) -> str | None:
        for tool_name, spec in AGENT_TOOL_REGISTRY.items():
            if spec.get("intent") == intent:
                return tool_name
        return None

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
            "allowed_tools": list(AGENT_TOOL_REGISTRY.keys()),
            "tool_registry": self._tool_registry_for_ai(),
            "module_catalog": AGENT_MODULE_CATALOG,
            "api_action_catalog": self._api_action_catalog_for_ai(),
            "tool_policy": {
                "direct_marketplace_writes": False,
                "writes": "Only preview/confirm/audit or manual task flows are allowed.",
                "available_backend_tools": [
                    "product_search",
                    "product_details",
                    "stock_export",
                    "title_update_preview",
                    "page_explain",
                    "reputation_agent",
                    "scenario_create_safe_manual_task",
                    "pricing_agent",
                    "insights_report_manual_task",
                    "module_navigation_catalog",
                    "open_logistics",
                    "navigate_to_portal_section",
                    "allow_listed_api_actions",
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
                    "tool_name": "admin.answer",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
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
                    "tool_name": "admin.answer",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
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
                    "tool_name": "page.explain",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
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
                    "tool_name": "page.explain",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
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
                    "tool_name": None,
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
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
                    "tool_name": "product.search",
                    "search_query": "АК 279 черный",
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": None,
                },
            ),
            (
                {
                    "message": "Открой отзывы и вопросы покупателей",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "reputation_agent",
                    "tool_name": "reputation.open",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Открыл раздел репутации: там можно работать с отзывами, вопросами и задачами по ответам покупателям.",
                },
            ),
            (
                {
                    "message": "Создай сценарий ответов на негативные отзывы для товара nm 1001001",
                    "context": {"path": "/reputation"},
                },
                {
                    "intent": "scenario_create",
                    "tool_name": "scenario.create_manual_task",
                    "search_query": None,
                    "selected_nm_id": 1001001,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Подготовить сценарий ответов на негативные отзывы: учитывать карточку товара, tone of voice бренда, не публиковать без ручной проверки.",
                },
            ),
            (
                {
                    "message": "Сделай маркетинговый R&D отчёт по отзывам для кросс-продаж",
                    "context": {"path": "/reputation"},
                },
                {
                    "intent": "insights_report",
                    "tool_name": "insights.create_report_task",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Подготовить отчёт по отзывам: выделить язык клиента, причины покупки, барьеры, идеи кросс-продаж и улучшения карточки.",
                },
            ),
            (
                {
                    "message": "Настрой умные цены без риска потерять маржу",
                    "context": {"path": "/pricing"},
                },
                {
                    "intent": "pricing_agent",
                    "tool_name": "pricing.open",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Открыл контур цен. Изменения цен готовятся только через безопасную проверку маржи и ручное подтверждение.",
                },
            ),
            (
                {
                    "message": "Увеличивай продажи без ценовой войны и сохраняй маржу. Приоритеты: дни до нулевого остатка, негативные отзывы, тренд заказов, дни запаса, конверсия в корзину.",
                    "context": {"path": "/pricing"},
                },
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
                    "assistant_message": (
                        "Стратегия: сначала защищаем наличие, затем управляем ценой по тренду заказов, "
                        "оборачиваемости, конверсии и свежему негативу. Для каждого товара вернуть шаг %, "
                        "причину, текущие тренды, конверсию, дни запаса и дни до нулевого остатка. "
                        "Изменения цен не применять автоматически: сначала проверка маржи и подтверждение."
                    ),
                },
            ),
            (
                {
                    "message": "Придумай алгоритм для увеличения продаж на 30% за месяц, не сильно снижая конверсию и контролируя остаток в пределах 60 дней.",
                    "context": {"path": "/dashboard"},
                },
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
                    "assistant_message": (
                        "Разложу цель на гипотезы: сегментация товаров, безопасные ценовые шаги, контроль "
                        "конверсии, защита от OOS, работа с негативом и weekly review эффекта. Нужны метрики: "
                        "заказы, конверсия, маржа, дни запаса, оборачиваемость и отзывы."
                    ),
                },
            ),
            (
                {
                    "message": "Сделай отчёт по логистике: где теряются заказы и почему возвраты",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "insights_report",
                    "tool_name": "insights.create_report_task",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Подготовить логистический отчёт: найти слабые места доставки, упаковки, возвратов и дать конкретные рекомендации.",
                },
            ),
            (
                {
                    "message": "Открой логистику",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "open_logistics",
                    "tool_name": "logistics.open",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Открыл логистику: можно проверить отгрузки, доставку, возвраты и риски.",
                },
            ),
            (
                {
                    "message": "Синхронизируй отзывы и вопросы покупателей",
                    "context": {"path": "/reputation"},
                },
                {
                    "intent": "api_action",
                    "tool_name": "portal.api_action",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": "reputation.sync",
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Готов запустить синхронизацию отзывов и вопросов. Перед выполнением потребуется подтверждение.",
                },
            ),
            (
                {
                    "message": "Скачай CSV по товарам в аналитике",
                    "context": {"path": "/analytics"},
                },
                {
                    "intent": "api_action",
                    "tool_name": "portal.api_action",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": "analytics.export_products_csv",
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Готов скачать CSV по товарной аналитике.",
                },
            ),
            (
                {
                    "message": "Запусти проверку качества данных",
                    "context": {"path": "/data-fix"},
                },
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
                    "assistant_message": "Готов запустить проверку качества данных. Перед выполнением потребуется подтверждение.",
                },
            ),
            (
                {
                    "message": "Закрой задачу 42 как done, комментарий проверено",
                    "context": {"path": "/action-center"},
                },
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
                    "assistant_message": "Готов обновить статус задачи 42. Перед выполнением потребуется подтверждение.",
                },
            ),
            (
                {
                    "message": "Одобри черновик ответа draft-123",
                    "context": {"path": "/reputation"},
                },
                {
                    "intent": "api_action",
                    "tool_name": "portal.api_action",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": None,
                    "api_action_key": "reputation.draft.approve",
                    "api_action_params": {"draft_id": "draft-123"},
                    "confidence": "high",
                    "assistant_message": "Готов одобрить черновик ответа draft-123. Перед выполнением потребуется подтверждение.",
                },
            ),
            (
                {
                    "message": "Открой рекламу и статистику кампаний",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "module_navigate",
                    "tool_name": "portal.navigate",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": "ads",
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Открыл раздел «Реклама»: там можно смотреть кампании, статистику и эффективность.",
                },
            ),
            (
                {
                    "message": "Настройки аккаунта где?",
                    "context": {"path": "/dashboard"},
                },
                {
                    "intent": "module_navigate",
                    "tool_name": "portal.navigate",
                    "search_query": None,
                    "selected_nm_id": None,
                    "new_title": None,
                    "module_key": "settings",
                    "api_action_key": None,
                    "api_action_params": None,
                    "confidence": "high",
                    "assistant_message": "Открыл настройки аккаунта и модулей.",
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
                        "Всегда выбирай tool_name строго из tool_registry; intent должен соответствовать выбранному tool. "
                        "Никогда не выдумывай nm_id, товар, остатки, цену или факт. "
                        "Если товар не указан точно, верни selected_nm_id=null и хороший search_query. "
                        "Если пользователь просит изменить карточку WB, выбери preview workflow, не прямую запись. "
                        "Если пользователь просит создать AI-сценарий, автоответы, работу с отзывами/вопросами, умные цены "
                        "по расписанию или похожую автоматизацию, выбери scenario_create: backend создаст только безопасную "
                        "ручную задачу, без публикации и без записи в WB. "
                        "Если пользователь просит открыть отзывы, вопросы покупателей, репутацию или ответы бренда, "
                        "выбери reputation_agent. "
                        "Если пользователь просит R&D, маркетинговый, логистический, производственный, NPD отчёт или "
                        "инсайты по отзывам, выбери insights_report. "
                        "Если пользователь просит умное изменение цен, анализ цены, маржи или промо без явного сценария, "
                        "выбери pricing_agent. Если просит раздел логистики, выбери open_logistics. "
                        "Если пользователь задаёт комплексную e-commerce стратегию, правила с приоритетами, "
                        "алгоритм роста продаж/маржи, управление завалами, негативом, конверсией, остатками, "
                        "оборачиваемостью или расплывчатую бизнес-цель вроде 'увеличь продажи'/'сделай меня богатым', "
                        "выбери strategy_advice и дай самостоятельный русский ответ: приоритеты, шаги, guardrails, "
                        "stop-loss/recovery, метрики проверки и безопасные следующие действия в портале. "
                        "Если пользователь просит открыть любой другой раздел портала, выбери module_navigate и "
                        "module_key строго из module_catalog. "
                        "Если пользователь просит выполнить действие внутри портала, получить snapshot данных, скачать CSV/XLSX, "
                        "запустить синхронизацию, проверку качества данных, scan претензий, stock operation или refresh marts, "
                        "выбери tool_name=portal.api_action, intent=api_action и api_action_key строго из api_action_catalog. "
                        "Если action требует ID или статус, положи их в api_action_params. Никогда не выдумывай ID: "
                        "если ID не указан и его нет в контексте страницы, верни нужный api_action_key с null/пустыми params, "
                        "чтобы backend запросил уточнение. "
                        "Для действий с confirm_required объясни, что перед запуском потребуется подтверждение. "
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

    @staticmethod
    def _tool_registry_for_ai() -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for name, spec in AGENT_TOOL_REGISTRY.items():
            tools.append(
                {
                    "name": name,
                    "intent": spec.get("intent"),
                    "title": spec.get("title"),
                    "description": spec.get("description"),
                    "required_args": spec.get("required_args", []),
                    "write_policy": spec.get("write_policy", "none"),
                }
            )
        return tools

    @staticmethod
    def _api_action_catalog_for_ai() -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        for key, spec in AGENT_API_ACTION_CATALOG.items():
            actions.append(
                {
                    "key": key,
                    "title": spec.get("title"),
                    "description": spec.get("description"),
                    "method": spec.get("method", "GET"),
                    "write_policy": spec.get("write_policy", "read"),
                    "confirm_required": bool(spec.get("confirm_required")),
                    "module_key": spec.get("module_key"),
                    "required_params": spec.get("required_params", []),
                }
            )
        return actions

    @staticmethod
    def _api_action_catalog_for_manifest() -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for key, spec in AGENT_API_ACTION_CATALOG.items():
            out[key] = {
                "title": spec.get("title"),
                "description": spec.get("description"),
                "method": spec.get("method", "GET"),
                "path": spec.get("path"),
                "query": spec.get("query", {}),
                "action_type": spec.get("action_type", "api_request"),
                "write_policy": spec.get("write_policy", "read"),
                "confirm_required": bool(spec.get("confirm_required")),
                "module_key": spec.get("module_key"),
                "required_params": spec.get("required_params", []),
                "body_from_params": spec.get("body_from_params", []),
                "query_from_params": spec.get("query_from_params", []),
            }
        return out

    @staticmethod
    def _tool_input_schema(tool_name: str) -> dict[str, Any]:
        common_string = {"type": "string", "minLength": 1, "maxLength": 4000}
        nullable_nm_id = {
            "type": ["integer", "null"],
            "minimum": MIN_WB_NM_ID,
            "maximum": MAX_DB_INT32,
        }
        product_args = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "selected_nm_id": nullable_nm_id,
                "search_query": {"type": ["string", "null"], "maxLength": 500},
                "message": {"type": ["string", "null"], "maxLength": 4000},
            },
        }
        if tool_name == "admin.answer":
            return {
                "type": "object",
                "additionalProperties": False,
                "properties": {"message": common_string},
                "required": ["message"],
            }
        if tool_name == "portal.navigate":
            return {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "module_key": {
                        "type": "string",
                        "enum": list(AGENT_MODULE_CATALOG.keys()),
                    },
                    "assistant_message": {
                        "type": ["string", "null"],
                        "maxLength": 1000,
                    },
                },
                "required": ["module_key"],
            }
        if tool_name == "product.search":
            return {
                "type": "object",
                "additionalProperties": False,
                "properties": {"search_query": common_string},
                "required": ["search_query"],
            }
        if tool_name in {"product.details", "stock.export_xlsx"}:
            return product_args
        if tool_name == "card.title_update_preview":
            schema = dict(product_args)
            schema["properties"] = {
                **product_args["properties"],
                "new_title": {"type": ["string", "null"], "maxLength": 500},
            }
            return schema
        if tool_name == "page.explain":
            return {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "message": common_string,
                    "context": {"type": "object"},
                },
                "required": ["message"],
            }
        if tool_name in {
            "scenario.create_manual_task",
            "insights.create_report_task",
        }:
            schema = dict(product_args)
            schema["properties"] = {
                **product_args["properties"],
                "assistant_message": {
                    "type": ["string", "null"],
                    "maxLength": 2000,
                },
            }
            return schema
        if tool_name == "portal.api_action":
            return {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "api_action_key": {
                        "type": "string",
                        "enum": list(AGENT_API_ACTION_CATALOG.keys()),
                    },
                    "api_action_params": AGENT_API_ACTION_PARAM_SCHEMA,
                    "assistant_message": {
                        "type": ["string", "null"],
                        "maxLength": 1000,
                    },
                    "message": {
                        "type": ["string", "null"],
                        "maxLength": 4000,
                    },
                },
                "required": ["api_action_key"],
            }
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "message": {"type": ["string", "null"], "maxLength": 4000},
                "assistant_message": {
                    "type": ["string", "null"],
                    "maxLength": 1000,
                },
            },
        }

    @staticmethod
    def _api_action_values(
        params: dict[str, Any] | None, *, account_id: int
    ) -> dict[str, Any]:
        values: dict[str, Any] = {"account_id": account_id}
        for key, value in (params or {}).items():
            if value is None or value == "":
                continue
            values[str(key)] = value
        return values

    @staticmethod
    def _fill_api_action_placeholders(value: Any, *, values: dict[str, Any]) -> Any:
        if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
            key = value[1:-1]
            if key in values:
                return values[key]
            return None
        if isinstance(value, dict):
            return {
                str(key): AgentService._fill_api_action_placeholders(
                    item, values=values
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                AgentService._fill_api_action_placeholders(
                    item, values=values
                )
                for item in value
            ]
        return value

    @staticmethod
    def _api_action_href(
        spec: dict[str, Any], *, account_id: int, params: dict[str, Any] | None = None
    ) -> str:
        values = AgentService._api_action_values(params, account_id=account_id)
        path = str(spec.get("path") or "/")
        for key, value in values.items():
            path = path.replace(f"{{{key}}}", str(value))
        raw_query = spec.get("query") if isinstance(spec.get("query"), dict) else {}
        query = AgentService._fill_api_action_placeholders(
            raw_query, values=values
        )
        for key in spec.get("query_from_params", []):
            if key in values:
                query[str(key)] = values[key]
        if not query:
            return path
        return f"{path}?{urlencode(query, doseq=True)}"

    @staticmethod
    def _api_action_body(
        spec: dict[str, Any], *, account_id: int, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        values = AgentService._api_action_values(params, account_id=account_id)
        raw_body = spec.get("body")
        if not isinstance(raw_body, dict):
            return {}
        body = AgentService._fill_api_action_placeholders(
            raw_body, values=values
        )
        if not isinstance(body, dict):
            return {}
        for key in spec.get("body_from_params", []):
            if key in values:
                body[str(key)] = values[key]
        return {key: value for key, value in body.items() if value is not None}

    @staticmethod
    def _missing_api_action_params(
        spec: dict[str, Any], params: dict[str, Any] | None
    ) -> list[str]:
        values = params or {}
        missing: list[str] = []
        for key in spec.get("required_params", []):
            value = values.get(str(key))
            if value is None or value == "":
                missing.append(str(key))
        return missing

    @staticmethod
    def _api_action_params_from_args(args: dict[str, Any]) -> dict[str, Any] | None:
        raw = args.get("api_action_params")
        merged: dict[str, Any] = raw.copy() if isinstance(raw, dict) else {}
        allowed = set(AGENT_API_ACTION_PARAM_SCHEMA["properties"].keys())
        for key in allowed:
            if key in args and args[key] is not None:
                merged[key] = args[key]
        cleaned = {
            str(key): value
            for key, value in merged.items()
            if key in allowed and value is not None and value != ""
        }
        return cleaned or None

    def _plan_from_openai_payload(self, data: dict[str, Any]) -> AgentPlan:
        parsed = self._load_json_object(self._extract_openai_text(data))
        intent = str(parsed.get("intent") or "help")
        if intent not in ALLOWED_AGENT_INTENTS:
            intent = "help"
        tool_name = self._nullable_text(parsed.get("tool_name"))
        if tool_name not in AGENT_TOOL_REGISTRY:
            tool_name = None
        if tool_name is not None:
            tool_intent = str(AGENT_TOOL_REGISTRY[tool_name].get("intent") or "")
            if tool_intent in ALLOWED_AGENT_INTENTS:
                intent = tool_intent
        module_key = self._nullable_text(parsed.get("module_key"))
        if module_key not in AGENT_MODULE_CATALOG:
            module_key = None
        api_action_key = self._nullable_text(parsed.get("api_action_key"))
        if api_action_key not in AGENT_API_ACTION_CATALOG:
            api_action_key = None
        raw_api_params = parsed.get("api_action_params")
        api_action_params = (
            self._api_action_params_from_args({"api_action_params": raw_api_params})
            if isinstance(raw_api_params, dict)
            else None
        )
        return AgentPlan(
            intent=intent,  # type: ignore[arg-type]
            tool_name=tool_name,
            search_query=self._nullable_text(parsed.get("search_query")),
            selected_nm_id=self._nullable_int(parsed.get("selected_nm_id")),
            new_title=self._nullable_text(parsed.get("new_title")),
            module_key=module_key,
            api_action_key=api_action_key,
            api_action_params=api_action_params,
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

    @staticmethod
    def _can_create_manual_task(role: str) -> bool:
        return role in {"operator", "manager", "admin", "superuser"}

    def _manual_task_action(
        self,
        *,
        account_id: int,
        user: AuthUser,
        product: WBProductCard,
        title: str,
        description: str,
        task_kind: str,
        deadline_days: int,
        priority: str = "P2",
    ) -> AgentUIAction:
        product_ref = self._product_ref(product)
        return AgentUIAction(
            type="create_manual_task",
            title="Создать задачу",
            method="POST",
            confirm_required=False,
            payload={
                "account_id": account_id,
                "title": title,
                "description": description,
                "task_kind": task_kind,
                "priority": priority,
                "assigned_to_user_id": int(user.id),
                "deadline_at": (utcnow() + timedelta(days=deadline_days)).isoformat(),
                "products": [
                    {
                        "nm_id": int(product_ref.nm_id),
                        "vendor_code": product_ref.vendor_code,
                        "title": product_ref.title,
                        "photo_url": product_ref.thumbnail_url,
                    }
                ],
            },
        )

    def _task_request_text(
        self, request_text: str, plan: AgentPlan, fallback: str
    ) -> str:
        return (
            self._nullable_text(request_text)
            or self._nullable_text(plan.assistant_message)
            or fallback
        )

    @staticmethod
    def _task_description(*parts: str) -> str:
        text = "\n".join(str(part).strip() for part in parts if str(part).strip())
        max_len = 3900
        if len(text) <= max_len:
            return text
        return f"{text[:max_len].rstrip()}\n\nОписание сокращено до лимита задачи."

    def _need_product_response(
        self,
        plan: AgentPlan,
        *,
        products: list[AgentProductRef],
        next_intent: AgentIntent,
        payload_extra: dict[str, Any] | None = None,
    ) -> AgentMessageResponse:
        action_payload: dict[str, Any] = {
            "intent": next_intent,
            "search_query": plan.search_query or "",
        }
        if payload_extra:
            action_payload.update(payload_extra)
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
                    payload=action_payload,
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
        if plan.source in {"ai", "ui", "tool_call"}:
            return "ai"
        return "ai_fallback"

    @staticmethod
    def _audit(plan: AgentPlan) -> dict[str, Any]:
        return {
            "planner": plan.source,
            "tool_name": plan.tool_name,
            "api_action_key": plan.api_action_key,
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
