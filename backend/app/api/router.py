from __future__ import annotations

from fastapi import APIRouter

from app.modules.ab_tests.router import promotion_router, router as ab_tests_router
from app.modules.accounts.router import router as accounts_router
from app.modules.ads.router import router as ads_router
from app.modules.agent.router import router as agent_router
from app.modules.analytics.router import router as analytics_router
from app.modules.auth.router import router as auth_router
from app.modules.control_tower.router import router as control_tower_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.data_quality.router import router as data_quality_router
from app.modules.documents.router import router as documents_router
from app.modules.exports.router import router as exports_router
from app.modules.finance.router import router as finance_router
from app.modules.core_sku.router import router as core_sku_router
from app.modules.health.router import router as health_router
from app.modules.logistics.router import router as logistics_router
from app.modules.manual_costs.router import router as manual_costs_router
from app.modules.marts.router import router as marts_router
from app.modules.meta.router import router as meta_router
from app.modules.money_management.router import router as money_management_router
from app.modules.orders.router import router as orders_router
from app.modules.portal.router import router as portal_router
from app.modules.photo_chat.router import router as photo_chat_router
from app.modules.problem_rules.router import router as problem_rules_router
from app.modules.prices.router import router as prices_router
from app.modules.product_cards.router import router as product_cards_router
from app.modules.sales.router import router as sales_router
from app.modules.stock_control.router import router as stock_control_router
from app.modules.stocks.router import router as stocks_router
from app.modules.supplies.router import router as supplies_router
from app.modules.sync.router import router as sync_router
from app.modules.tariffs.router import router as tariffs_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(agent_router)
api_router.include_router(ab_tests_router)
api_router.include_router(promotion_router)
api_router.include_router(control_tower_router)
api_router.include_router(accounts_router)
api_router.include_router(meta_router)
api_router.include_router(money_management_router)
api_router.include_router(portal_router)
api_router.include_router(photo_chat_router)
api_router.include_router(problem_rules_router)
api_router.include_router(stock_control_router)
api_router.include_router(sync_router)
api_router.include_router(manual_costs_router)
api_router.include_router(marts_router)
api_router.include_router(data_quality_router)
api_router.include_router(core_sku_router)
api_router.include_router(logistics_router)
api_router.include_router(product_cards_router)
api_router.include_router(prices_router)
api_router.include_router(orders_router)
api_router.include_router(sales_router)
api_router.include_router(stocks_router)
api_router.include_router(finance_router)
api_router.include_router(supplies_router)
api_router.include_router(ads_router)
api_router.include_router(analytics_router)
api_router.include_router(tariffs_router)
api_router.include_router(documents_router)
api_router.include_router(exports_router)
api_router.include_router(dashboard_router)
