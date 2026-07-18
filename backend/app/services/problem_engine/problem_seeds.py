from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.problem_engine import ProblemDefinition, ProblemRuleVersion


@dataclass(frozen=True, slots=True)
class ProblemDefinitionSeed:
    problem_code: str
    source_module: str
    category: str
    entity_type: str
    title_template: str
    description_template: str
    recommendation_template: str
    impact_type_default: str
    trust_state_default: str
    severity_default: str
    allowed_actions_json: list[str]

    def model_kwargs(self) -> dict[str, Any]:
        return {
            "problem_code": self.problem_code,
            "source_module": self.source_module,
            "category": self.category,
            "entity_type": self.entity_type,
            "title_template": self.title_template,
            "description_template": self.description_template,
            "recommendation_template": self.recommendation_template,
            "impact_type_default": self.impact_type_default,
            "trust_state_default": self.trust_state_default,
            "severity_default": self.severity_default,
            "allowed_actions_json": list(self.allowed_actions_json),
            "status": "active",
            "is_system_seeded": True,
        }


@dataclass(frozen=True, slots=True)
class ProblemRuleVersionSeed:
    problem_code: str
    version: int
    evaluation_grain: str
    lookback_days: int
    condition_json: dict[str, Any]
    impact_formula_json: dict[str, Any]
    severity_formula_json: dict[str, Any] = field(default_factory=dict)
    confidence_formula_json: dict[str, Any] = field(default_factory=dict)
    dedup_key_template: str = "{account_id}:{problem_code}:{nm_id}"
    recheck_rule_json: dict[str, Any] = field(default_factory=dict)
    evidence_template_json: dict[str, Any] = field(default_factory=dict)

    def model_kwargs(
        self, *, problem_definition_id: int, published_at: datetime | None
    ) -> dict[str, Any]:
        return {
            "problem_definition_id": problem_definition_id,
            "version": self.version,
            "status": "active",
            "evaluation_grain": self.evaluation_grain,
            "lookback_days": self.lookback_days,
            "condition_json": self.condition_json,
            "impact_formula_json": self.impact_formula_json,
            "severity_formula_json": self.severity_formula_json,
            "confidence_formula_json": self.confidence_formula_json,
            "dedup_key_template": self.dedup_key_template,
            "recheck_rule_json": self.recheck_rule_json,
            "evidence_template_json": self.evidence_template_json,
            "is_system_seeded": True,
            "published_at": published_at,
        }


MINIMUM_MARGIN_PCT = 10
AD_SPEND_WITHOUT_PROFIT_THRESHOLD = 500
LOW_STOCK_RISK_DAYS = 7
OVERSTOCK_BASE_STOCK_QTY = 50
DEAD_STOCK_DAYS_THRESHOLD = 90
FAST_STOCK_DEPLETION_DAYS = 3


INITIAL_PROBLEM_DEFINITION_SEEDS: tuple[ProblemDefinitionSeed, ...] = (
    ProblemDefinitionSeed(
        problem_code="missing_cost_blocks_profit",
        source_module="problem_engine",
        category="data_quality",
        entity_type="product",
        title_template="Нет себестоимости для товара {nm_id}",
        description_template="За 30 дней есть выручка {revenue_30d}, но себестоимость не заполнена. Поэтому прибыль и маржа по товару пока не считаются надёжно.",
        recommendation_template="Загрузите или сопоставьте себестоимость, затем запустите повторную проверку прибыльности.",
        impact_type_default="data_blocker",
        trust_state_default="blocked",
        severity_default="critical",
        allowed_actions_json=[
            "upload_cost",
            "map_sku",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="negative_unit_profit",
        source_module="problem_engine",
        category="profitability",
        entity_type="product",
        title_template="Товар {nm_id} продаётся в минус",
        description_template="Прибыль на единицу: {unit_profit}, маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
        recommendation_template="Проверьте цену, себестоимость, рекламу, промо и логистику. Не снижайте цену без проверки безопасной маржи.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=[
            "review_price",
            "review_cost",
            "review_ads",
            "review_promo",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="overstock_slow_moving",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Пересток и медленные продажи по товару {nm_id}",
        description_template="Остаток: {stock_qty}, запас в днях: {days_of_stock}, средние продажи за 14 дней: {avg_daily_sales_14d} шт./день.",
        recommendation_template="Проверьте безопасное промо, цену, комплект, рекламу или качество карточки. Скидку можно запускать только после проверки маржи.",
        impact_type_default="blocked_cash",
        trust_state_default="estimated",
        severity_default="medium",
        allowed_actions_json=[
            "safe_promo",
            "review_price",
            "bundle",
            "review_ads",
            "review_content",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="low_stock_risk",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Риск низкого остатка по товару {nm_id}",
        description_template="Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
        recommendation_template="Запланируйте поставку или пополнение. Если поставить товар быстро нельзя, снизьте промо или рекламу, чтобы не уйти в дефицит.",
        impact_type_default="lost_sales_risk",
        trust_state_default="provisional",
        severity_default="medium",
        allowed_actions_json=[
            "plan_supply",
            "reduce_promo",
            "reduce_ads",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="ads_spend_without_profit",
        source_module="problem_engine",
        category="ads",
        entity_type="product",
        title_template="Реклама съедает прибыль по товару {nm_id}",
        description_template="Расход на рекламу за 7 дней: {ad_spend_7d}; прибыль на единицу после рекламы: {unit_profit_after_ads}.",
        recommendation_template="Снизьте или приостановите рекламу, проверьте качество карточки, ставки и цену.",
        impact_type_default="probable_loss",
        trust_state_default="provisional",
        severity_default="high",
        allowed_actions_json=[
            "pause_ads",
            "lower_ads",
            "check_card_quality",
            "review_bids",
            "review_price",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="promo_not_profitable",
        source_module="problem_engine",
        category="promo",
        entity_type="product",
        title_template="Промо уводит товар {nm_id} в минус",
        description_template="Расход на промо: {promo_spend_30d}, прибыль на единицу: {unit_profit}, маржа: {margin_pct}%.",
        recommendation_template="Снизьте или остановите промо, проверьте цену и убедитесь, что скидка сохраняет безопасную маржу.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=[
            "review_promo",
            "reduce_promo",
            "review_price",
            "review_cost",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="price_below_safe_margin",
        source_module="problem_engine",
        category="price",
        entity_type="product",
        title_template="Цена ниже безопасной маржи по товару {nm_id}",
        description_template="Текущая эффективная цена: {price_after_discount}; маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
        recommendation_template="Проверьте цену и поднимите её до безопасного уровня, если экономика товара заполнена полностью.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=[
            "review_price",
            "pricing_review",
            "review_cost",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="dead_stock",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Риск зависшего остатка по товару {nm_id}",
        description_template="Остаток: {stock_qty}, продажи за 30 дней: {sales_30d}, запас в днях: {days_of_stock}.",
        recommendation_template="Проверьте карточку, рекламу, комплекты и безопасный сценарий распродажи до запуска скидки.",
        impact_type_default="blocked_cash",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=[
            "safe_promo",
            "bundle",
            "review_content",
            "review_ads",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="fast_stock_depletion",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Товар {nm_id} быстро заканчивается",
        description_template="Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
        recommendation_template="Срочно запланируйте пополнение. Если поставка невозможна, снизьте промо или рекламу, чтобы избежать дефицита.",
        impact_type_default="lost_sales_risk",
        trust_state_default="provisional",
        severity_default="high",
        allowed_actions_json=[
            "plan_supply",
            "reduce_promo",
            "reduce_ads",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
)

OLD_SEEDED_DEFINITION_TEMPLATES: dict[str, tuple[str, str, str]] = {
    "missing_cost_blocks_profit": (
        "Missing cost blocks profit for {nm_id}",
        "Revenue in 30 days is {revenue_30d}, but cost_price is missing, so profitability cannot be trusted.",
        "Upload or map cost price before profitability can be trusted.",
    ),
    "negative_unit_profit": (
        "Negative unit profit for {nm_id}",
        "Unit profit is {unit_profit} and margin is {margin_pct}%. Minimum margin is 10%.",
        "Review price, cost, ads spend, promo, and logistics.",
    ),
    "overstock_slow_moving": (
        "Overstock and slow moving product {nm_id}",
        "Stock is {stock_qty}, days of stock is {days_of_stock}, and 14-day sales velocity is {avg_daily_sales_14d} pcs/day.",
        "Consider safe promo, price review, bundle, or ads/content check.",
    ),
    "low_stock_risk": (
        "Low stock risk for {nm_id}",
        "Days of stock is {days_of_stock} while 7-day sales velocity is {avg_daily_sales_7d} pcs/day.",
        "Plan supply/replenishment. If supply cannot happen, reduce promo/ads.",
    ),
    "ads_spend_without_profit": (
        "Ads spend without profit for {nm_id}",
        "Ad spend in 7 days is {ad_spend_7d}; unit profit after ads is {unit_profit_after_ads}.",
        "Pause or lower ads, check card quality, review bids and price.",
    ),
    "promo_not_profitable": (
        "Promo is not profitable for {nm_id}",
        "Promo spend is {promo_spend_30d}, unit profit is {unit_profit}, and margin is {margin_pct}%.",
        "Reduce or pause promo, review price, and check whether the discount still preserves safe margin.",
    ),
    "price_below_safe_margin": (
        "Price is below safe margin for {nm_id}",
        "Current effective price is {price_after_discount}; margin is {margin_pct}%. Minimum margin is 10%.",
        "Review price and raise it to a safe target if unit economics are complete.",
    ),
    "dead_stock": (
        "Dead stock risk for {nm_id}",
        "Stock is {stock_qty}, sales in 30 days are {sales_30d}, and days of stock is {days_of_stock}.",
        "Review content, ads, bundle options, and safe liquidation path before discounting.",
    ),
    "fast_stock_depletion": (
        "Fast stock depletion for {nm_id}",
        "Days of stock is {days_of_stock} while 7-day sales velocity is {avg_daily_sales_7d} pcs/day.",
        "Plan urgent replenishment. If supply cannot happen, reduce promo/ads to avoid stockout.",
    ),
}


INITIAL_PROBLEM_RULE_SEEDS: tuple[ProblemRuleVersionSeed, ...] = (
    ProblemRuleVersionSeed(
        problem_code="missing_cost_blocks_profit",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {"missing": ["cost_price"]},
                {">": [{"metric": "revenue_30d"}, 0]},
            ]
        },
        impact_formula_json={"metric": "revenue_30d"},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "revenue_30d"}, 50000]}, "then": "critical"},
                {"else": "high"},
            ]
        },
        confidence_formula_json={"case": [{"else": "blocked"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после загрузки или сопоставления себестоимости либо когда в периоде больше нет выручки.",
            "resolved_when": {
                "or": [
                    {"not": {"missing": ["cost_price"]}},
                    {"<=": [{"metric": "revenue_30d"}, 0]},
                ]
            },
            "missing_metrics_policy": "condition_only",
            "create_data_blocker_on_missing": False,
            "initial_status": "blocked",
        },
        evidence_template_json={
            "formula_human": "Себестоимость отсутствует, а выручка за 30 дней больше 0.",
            "formula_code": "missing_cost_blocks_profit.v1",
            "recheck_rule_human": "Загрузите или сопоставьте себестоимость, затем перепроверьте товар после обновления выручки.",
            "impact_type": "data_blocker",
            "confidence": "blocked",
            "money_currency": "RUB",
            "trust_notes": [
                "Платформа специально не считает отрицательную прибыль, пока не хватает себестоимости."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="negative_unit_profit",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {"not": {"missing": ["cost_price"]}},
                {
                    "or": [
                        {"<": [{"metric": "unit_profit"}, 0]},
                        {"<": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
                    ]
                },
            ]
        },
        impact_formula_json={
            "case": [
                {
                    "if": {"<": [{"metric": "unit_profit"}, 0]},
                    "then": {
                        "abs": {
                            "*": [{"metric": "unit_profit"}, {"metric": "sales_30d"}]
                        }
                    },
                },
                {"else": 0},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {"<": [{"metric": "unit_profit"}, -100]}, "then": "critical"},
                {"if": {"<": [{"metric": "margin_pct"}, 0]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
            "resolved_when": {
                "or": [
                    {"missing": ["cost_price"]},
                    {
                        "and": [
                            {">=": [{"metric": "unit_profit"}, 0]},
                            {">=": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
                        ]
                    },
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Себестоимость заполнена, и прибыль на единицу ниже 0 или маржа ниже 10%.",
            "formula_code": "negative_unit_profit.v1",
            "recheck_rule_human": "Перепроверьте после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
            "trust_notes": [
                "Если себестоимость отсутствует, это правило блокируется и вместо него показывается проблема с недостающей себестоимостью."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="overstock_slow_moving",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "stock_qty"}, OVERSTOCK_BASE_STOCK_QTY]},
                {">": [{"metric": "days_of_stock"}, 60]},
                {"<": [{"metric": "avg_daily_sales_14d"}, 2]},
            ]
        },
        impact_formula_json={
            "*": [
                {
                    "max": [
                        0,
                        {"-": [{"metric": "stock_qty"}, OVERSTOCK_BASE_STOCK_QTY]},
                    ]
                },
                {"metric": "cost_price"},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "days_of_stock"}, 120]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков, скорости продаж или себестоимости.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "stock_qty"}, OVERSTOCK_BASE_STOCK_QTY]},
                    {"<=": [{"metric": "days_of_stock"}, 60]},
                    {">=": [{"metric": "avg_daily_sales_14d"}, 2]},
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Остаток выше 50 штук, запаса больше чем на 60 дней, а средние продажи за 14 дней ниже 2 шт./день. Замороженные деньги считаются по лишнему остатку и себестоимости.",
            "formula_code": "overstock_slow_moving.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, скорости продаж или себестоимости.",
            "impact_type": "blocked_cash",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="low_stock_risk",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {"<": [{"metric": "days_of_stock"}, LOW_STOCK_RISK_DAYS]},
                {">": [{"metric": "avg_daily_sales_7d"}, 1]},
            ]
        },
        impact_formula_json={
            "*": [
                {"metric": "avg_daily_revenue_7d"},
                {"max": [0, {"-": [LOW_STOCK_RISK_DAYS, {"metric": "days_of_stock"}]}]},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {"<": [{"metric": "days_of_stock"}, 3]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "provisional"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
            "resolved_when": {
                "or": [
                    {">=": [{"metric": "days_of_stock"}, LOW_STOCK_RISK_DAYS]},
                    {"<=": [{"metric": "avg_daily_sales_7d"}, 1]},
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Запаса меньше чем на 7 дней, а средние продажи за 7 дней выше 1 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
            "formula_code": "low_stock_risk.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
            "impact_type": "lost_sales_risk",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="ads_spend_without_profit",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {">": [{"metric": "ad_spend_7d"}, AD_SPEND_WITHOUT_PROFIT_THRESHOLD]},
                {"<": [{"metric": "unit_profit_after_ads"}, 0]},
            ]
        },
        impact_formula_json={
            "*": [
                {"abs": {"metric": "unit_profit_after_ads"}},
                {"metric": "units_sold_7d"},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "ad_spend_7d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения рекламных расходов, ставок, цены или прибыли.",
            "resolved_when": {
                "or": [
                    {
                        "<=": [
                            {"metric": "ad_spend_7d"},
                            AD_SPEND_WITHOUT_PROFIT_THRESHOLD,
                        ]
                    },
                    {">=": [{"metric": "unit_profit_after_ads"}, 0]},
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Расход на рекламу за 7 дней выше 500, а прибыль на единицу после рекламы ниже 0. Вероятный убыток считается по модулю прибыли после рекламы и продажам за 7 дней.",
            "formula_code": "ads_spend_without_profit.v1",
            "recheck_rule_human": "Перепроверьте после изменения рекламных расходов, ставок, цены или прибыли.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="promo_not_profitable",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {"not": {"missing": ["cost_price"]}},
                {">": [{"metric": "promo_spend_30d"}, 0]},
                {
                    "or": [
                        {"<": [{"metric": "unit_profit"}, 0]},
                        {"<": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
                    ]
                },
            ]
        },
        impact_formula_json={
            "max": [
                {"metric": "promo_spend_30d"},
                {
                    "case": [
                        {
                            "if": {"<": [{"metric": "unit_profit"}, 0]},
                            "then": {
                                "abs": {
                                    "*": [
                                        {"metric": "unit_profit"},
                                        {"metric": "sales_30d"},
                                    ]
                                }
                            },
                        },
                        {"else": 0},
                    ]
                },
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "promo_spend_30d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения промо, цены, себестоимости или маржи.",
            "resolved_when": {
                "or": [
                    {"missing": ["cost_price"]},
                    {"<=": [{"metric": "promo_spend_30d"}, 0]},
                    {
                        "and": [
                            {">=": [{"metric": "unit_profit"}, 0]},
                            {">=": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
                        ]
                    },
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Себестоимость заполнена, есть расходы на промо, и прибыль на единицу ниже 0 или маржа ниже 10%.",
            "formula_code": "promo_not_profitable.v1",
            "recheck_rule_human": "Перепроверьте после изменения промо, цены, себестоимости или маржи.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
            "trust_notes": [
                "Рекомендации по промо ограничены проверкой безопасной маржи и экономики единицы товара."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="price_below_safe_margin",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {"not": {"missing": ["cost_price"]}},
                {">": [{"metric": "price_after_discount"}, 0]},
                {"<": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
            ]
        },
        impact_formula_json={
            "case": [
                {
                    "if": {"<": [{"metric": "unit_profit"}, 0]},
                    "then": {
                        "abs": {
                            "*": [{"metric": "unit_profit"}, {"metric": "sales_30d"}]
                        }
                    },
                },
                {"else": 0},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {"<": [{"metric": "margin_pct"}, 0]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения цены, себестоимости, комиссий или маржи.",
            "resolved_when": {
                "or": [
                    {"missing": ["cost_price"]},
                    {">=": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Себестоимость заполнена, эффективная цена выше 0, а маржа ниже 10%.",
            "formula_code": "price_below_safe_margin.v1",
            "recheck_rule_human": "Перепроверьте после изменения цены, себестоимости, комиссий или маржи.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
            "trust_notes": [
                "Целевая цена считается из себестоимости, комиссии, логистики, эквайринга и хранения."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="dead_stock",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "stock_qty"}, 0]},
                {"==": [{"metric": "sales_30d"}, 0]},
                {">": [{"metric": "days_of_stock"}, DEAD_STOCK_DAYS_THRESHOLD]},
            ]
        },
        impact_formula_json={"*": [{"metric": "stock_qty"}, {"metric": "cost_price"}]},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "stock_qty"}, 100]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков, продаж или себестоимости.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "stock_qty"}, 0]},
                    {">": [{"metric": "sales_30d"}, 0]},
                    {"<=": [{"metric": "days_of_stock"}, DEAD_STOCK_DAYS_THRESHOLD]},
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Остаток больше 0, продаж за 30 дней нет, а запас больше чем на 90 дней. Замороженные деньги считаются как остаток, умноженный на себестоимость.",
            "formula_code": "dead_stock.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, продаж или себестоимости.",
            "impact_type": "blocked_cash",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="fast_stock_depletion",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {"<": [{"metric": "days_of_stock"}, FAST_STOCK_DEPLETION_DAYS]},
                {">": [{"metric": "avg_daily_sales_7d"}, 2]},
            ]
        },
        impact_formula_json={
            "*": [
                {"metric": "avg_daily_revenue_7d"},
                {"max": [0, {"-": [LOW_STOCK_RISK_DAYS, {"metric": "days_of_stock"}]}]},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {"<": [{"metric": "days_of_stock"}, 1]}, "then": "critical"},
                {"else": "high"},
            ]
        },
        confidence_formula_json={"case": [{"else": "provisional"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
            "resolved_when": {
                "or": [
                    {">=": [{"metric": "days_of_stock"}, FAST_STOCK_DEPLETION_DAYS]},
                    {"<=": [{"metric": "avg_daily_sales_7d"}, 2]},
                ]
            },
        },
        evidence_template_json={
            "formula_human": "Запаса меньше чем на 3 дня, а средние продажи за 7 дней выше 2 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
            "formula_code": "fast_stock_depletion.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
            "impact_type": "lost_sales_risk",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
)


INITIAL_PROBLEM_CODES = frozenset(
    definition.problem_code for definition in INITIAL_PROBLEM_DEFINITION_SEEDS
)


class DynamicProblemSeedService:
    def initial_definitions(self) -> list[ProblemDefinitionSeed]:
        return list(INITIAL_PROBLEM_DEFINITION_SEEDS)

    def initial_rule_versions(self) -> list[ProblemRuleVersionSeed]:
        return list(INITIAL_PROBLEM_RULE_SEEDS)

    def initial_problem_codes(self) -> set[str]:
        return set(INITIAL_PROBLEM_CODES)

    async def seed_initial_problem_rules(
        self, session: AsyncSession
    ) -> list[ProblemRuleVersion]:
        codes = [
            definition.problem_code for definition in INITIAL_PROBLEM_DEFINITION_SEEDS
        ]
        result = await session.execute(
            select(ProblemDefinition).where(ProblemDefinition.problem_code.in_(codes))
        )
        existing_by_code = {
            definition.problem_code: definition for definition in result.scalars()
        }

        definitions_by_code: dict[str, ProblemDefinition] = {}
        protected_definition_codes: set[str] = set()
        for seed in INITIAL_PROBLEM_DEFINITION_SEEDS:
            payload = seed.model_kwargs()
            definition = existing_by_code.get(seed.problem_code)
            if definition is None:
                definition = ProblemDefinition(**payload)
                session.add(definition)
            elif self._can_update_seed_definition(definition, seed):
                for key, value in payload.items():
                    setattr(definition, key, value)
            else:
                protected_definition_codes.add(seed.problem_code)
            definitions_by_code[seed.problem_code] = definition

        await session.flush()

        rule_result = await session.execute(
            select(ProblemRuleVersion).where(
                ProblemRuleVersion.problem_definition_id.in_(
                    [
                        definition.id
                        for definition in definitions_by_code.values()
                        if definition.id is not None
                    ]
                )
            )
        )
        existing_by_definition_version = {
            (rule.problem_definition_id, rule.version): rule
            for rule in rule_result.scalars()
        }
        published_at = datetime.now(UTC)
        seeded: list[ProblemRuleVersion] = []
        for seed in INITIAL_PROBLEM_RULE_SEEDS:
            if seed.problem_code in protected_definition_codes:
                continue
            definition = definitions_by_code[seed.problem_code]
            payload = seed.model_kwargs(
                problem_definition_id=definition.id, published_at=published_at
            )
            rule = existing_by_definition_version.get((definition.id, seed.version))
            if rule is None:
                rule = ProblemRuleVersion(**payload)
                session.add(rule)
            elif self._can_update_seed_rule(rule, seed):
                for key, value in payload.items():
                    setattr(rule, key, value)
            seeded.append(rule)

        await session.flush()
        return seeded

    @staticmethod
    def _template_tuple(
        definition: ProblemDefinition | ProblemDefinitionSeed,
    ) -> tuple[str, str, str]:
        return (
            str(definition.title_template),
            str(definition.description_template),
            str(definition.recommendation_template),
        )

    def _can_update_seed_definition(
        self, definition: ProblemDefinition, seed: ProblemDefinitionSeed
    ) -> bool:
        if definition.created_by_user_id is not None:
            return False
        if bool(getattr(definition, "is_system_seeded", False)):
            return True
        current = self._template_tuple(definition)
        return current == self._template_tuple(
            seed
        ) or current == OLD_SEEDED_DEFINITION_TEMPLATES.get(seed.problem_code)

    @staticmethod
    def _can_update_seed_rule(
        rule: ProblemRuleVersion, seed: ProblemRuleVersionSeed
    ) -> bool:
        if rule.created_by_user_id is not None:
            return False
        if bool(getattr(rule, "is_system_seeded", False)):
            return True
        if int(rule.version or 0) != int(seed.version):
            return False
        current_formula_code = (rule.evidence_template_json or {}).get("formula_code")
        seed_formula_code = (seed.evidence_template_json or {}).get("formula_code")
        return bool(seed_formula_code) and current_formula_code == seed_formula_code
