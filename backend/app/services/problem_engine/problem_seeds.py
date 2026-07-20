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
AD_SPEND_NO_ORDERS_THRESHOLD = 1000
LOW_STOCK_RISK_DAYS = 7
OVERSTOCK_BASE_STOCK_QTY = 50
DEAD_STOCK_DAYS_THRESHOLD = 90
FAST_STOCK_DEPLETION_DAYS = 3
LOW_CONVERSION_MIN_VIEWS_30D = 1000
LOW_CONVERSION_RATE_PCT = 1
HIGH_RETURN_RATE_MIN_SALES_30D = 5
HIGH_RETURN_RATE_PCT = 30
HIGH_AD_DRR_PCT = 25
HIGH_AD_CPO_RUB = 500
LOW_AD_CTR_MIN_VIEWS_7D = 1000
LOW_AD_CTR_PCT = 0.5
ADS_STOCK_RISK_DAYS = 3
STOCKOUT_RISK_14D_DAYS = 14
STORAGE_PRESSURE_STOCK_QTY = 50
STORAGE_PRESSURE_DAYS = 60
STORAGE_PRESSURE_FEE_PER_UNIT = 5
NO_SALES_WITH_VIEWS_MIN_VIEWS_30D = 1000
PRICE_CONVERSION_MIN_MARGIN_PCT = 30
HIGH_DEMAND_ORDERS_7D = 20
PRICE_PROTECT_STOCK_DAYS = 7
LOW_PRODUCT_RATING_THRESHOLD = 4
LOW_PRODUCT_RATING_MIN_NEGATIVE_REVIEWS = 2


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
        problem_code="ads_spend_no_orders",
        source_module="problem_engine",
        category="ads",
        entity_type="product",
        title_template="Реклама по товару {nm_id} тратит бюджет без заказов",
        description_template="Расход на рекламу за 7 дней: {ad_spend_7d}, заказов за 7 дней: {orders_7d}.",
        recommendation_template="Проверьте кампанию, ставки, поисковые кластеры, карточку и цену. Не останавливайте кампанию автоматически: сначала откройте рекламный review.",
        impact_type_default="probable_loss",
        trust_state_default="provisional",
        severity_default="medium",
        allowed_actions_json=[
            "review_ads",
            "review_bids",
            "check_card_quality",
            "review_price",
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
        problem_code="low_conversion_card",
        source_module="problem_engine",
        category="content_quality",
        entity_type="product",
        title_template="Карточка товара {nm_id} получает просмотры, но плохо конвертирует",
        description_template="Просмотры за 30 дней: {views_30d}, конверсия в заказ: {conversion_rate}%, заказы: {orders_30d}.",
        recommendation_template="Проверьте название, главное фото, характеристики, цену, отзывы и качество рекламного трафика. После исправления перепроверьте конверсию.",
        impact_type_default="opportunity",
        trust_state_default="opportunity",
        severity_default="medium",
        allowed_actions_json=[
            "check_card_quality",
            "review_content",
            "review_ads",
            "review_price",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="high_return_rate",
        source_module="problem_engine",
        category="content_quality",
        entity_type="product",
        title_template="Высокий процент возвратов по товару {nm_id}",
        description_template="Продажи за 30 дней: {sales_30d}, возвратность: {return_rate}%, выручка: {revenue_30d}.",
        recommendation_template="Проверьте карточку, размерную сетку, фото, описание, качество товара и ожидания покупателя. Исправьте карточку или создайте задачу ответственному.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="medium",
        allowed_actions_json=[
            "check_card_quality",
            "review_content",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="high_ad_drr",
        source_module="problem_engine",
        category="ads",
        entity_type="product",
        title_template="Высокий ДРР рекламы по товару {nm_id}",
        description_template="Расход на рекламу за 7 дней: {ad_spend_7d}, выручка за 7 дней: {revenue_7d}. ДРР выше безопасного порога 25%.",
        recommendation_template="Проверьте кампанию, ставки, карточку и цену. Снижайте расход только после проверки маржи и качества трафика.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="medium",
        allowed_actions_json=[
            "review_ads",
            "review_bids",
            "check_card_quality",
            "review_price",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="high_ad_cpo",
        source_module="problem_engine",
        category="ads",
        entity_type="product",
        title_template="Высокая стоимость заказа из рекламы по товару {nm_id}",
        description_template="CPO за 7 дней: {ad_cpo_7d}, расход: {ad_spend_7d}, рекламных заказов: {ad_orders_7d}.",
        recommendation_template="Проверьте ставки, кластеры, карточку и цену. Если CPO не окупается, снизьте ставку или перенесите бюджет.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="medium",
        allowed_actions_json=[
            "review_ads",
            "review_bids",
            "check_card_quality",
            "review_price",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="low_ads_ctr",
        source_module="problem_engine",
        category="ads",
        entity_type="product",
        title_template="Низкий CTR рекламы по товару {nm_id}",
        description_template="Показы рекламы за 7 дней: {ad_views_7d}, клики: {ad_clicks_7d}, CTR: {ad_ctr_7d}%.",
        recommendation_template="Проверьте главное фото, цену, позицию, ставку и релевантность кластера. Это задача на качество трафика.",
        impact_type_default="opportunity",
        trust_state_default="opportunity",
        severity_default="medium",
        allowed_actions_json=[
            "review_ads",
            "review_bids",
            "check_card_quality",
            "review_content",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="ads_stockout_risk",
        source_module="problem_engine",
        category="ads",
        entity_type="product",
        title_template="Реклама ведёт спрос к дефициту по товару {nm_id}",
        description_template="Расход на рекламу за 7 дней: {ad_spend_7d}, запаса осталось на {days_of_stock} дней.",
        recommendation_template="Запланируйте поставку или временно снизьте рекламный спрос, чтобы не уйти в out-of-stock.",
        impact_type_default="lost_sales_risk",
        trust_state_default="provisional",
        severity_default="high",
        allowed_actions_json=[
            "plan_supply",
            "reduce_ads",
            "review_ads",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="stockout_now_with_recent_orders",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Товар {nm_id} уже без остатка, но спрос есть",
        description_template="Текущий остаток: {stock_qty}, заказов за 7 дней: {orders_7d}.",
        recommendation_template="Срочно проверьте остатки и поставку. Если остаток реально ноль, создайте пополнение и уберите лишний спрос.",
        impact_type_default="lost_sales_risk",
        trust_state_default="provisional",
        severity_default="critical",
        allowed_actions_json=[
            "plan_supply",
            "reduce_ads",
            "reduce_promo",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="stockout_risk_14d",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Товар {nm_id} закончится в ближайшие 14 дней",
        description_template="Запаса осталось на {days_of_stock} дней, средние продажи за 14 дней: {avg_daily_sales_14d} шт./день.",
        recommendation_template="Запланируйте пополнение заранее. Если поставка не успевает, снижайте промо или рекламу до прихода товара.",
        impact_type_default="lost_sales_risk",
        trust_state_default="provisional",
        severity_default="medium",
        allowed_actions_json=[
            "plan_supply",
            "reduce_ads",
            "reduce_promo",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="storage_cost_pressure",
        source_module="problem_engine",
        category="stock",
        entity_type="product",
        title_template="Остаток товара {nm_id} создаёт давление по хранению",
        description_template="Остаток: {stock_qty}, запас в днях: {days_of_stock}, хранение на единицу: {storage_fee_per_unit}.",
        recommendation_template="Проверьте безопасную распродажу, комплект, карточку или перераспределение. Скидку запускайте только после проверки маржи.",
        impact_type_default="blocked_cash",
        trust_state_default="estimated",
        severity_default="medium",
        allowed_actions_json=[
            "safe_promo",
            "review_price",
            "bundle",
            "review_content",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="no_sales_with_views",
        source_module="problem_engine",
        category="content_quality",
        entity_type="product",
        title_template="Карточка товара {nm_id} получает просмотры, но заказов нет",
        description_template="Просмотры за 30 дней: {views_30d}, заказов за 30 дней: {orders_30d}.",
        recommendation_template="Проверьте оффер: фото, название, характеристики, цену, отзывы и рекламный трафик.",
        impact_type_default="opportunity",
        trust_state_default="opportunity",
        severity_default="medium",
        allowed_actions_json=[
            "check_card_quality",
            "review_content",
            "review_price",
            "review_ads",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="price_offer_blocks_conversion",
        source_module="problem_engine",
        category="price",
        entity_type="product",
        title_template="Цена или оффер тормозит конверсию товара {nm_id}",
        description_template="Маржа: {margin_pct}%, просмотры: {views_30d}, конверсия: {conversion_rate}%.",
        recommendation_template="Проверьте цену относительно оффера. Если маржа высокая, протестируйте безопасную цену или улучшите карточку.",
        impact_type_default="opportunity",
        trust_state_default="opportunity",
        severity_default="medium",
        allowed_actions_json=[
            "review_price",
            "pricing_review",
            "check_card_quality",
            "review_ads",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="raise_price_possible_high_demand",
        source_module="problem_engine",
        category="price",
        entity_type="product",
        title_template="Можно защитить остаток ценой по товару {nm_id}",
        description_template="Заказов за 7 дней: {orders_7d}, запаса осталось на {days_of_stock} дней, маржа: {margin_pct}%.",
        recommendation_template="Проверьте price review: при высоком спросе и низком запасе можно поднять цену или снизить промо, чтобы не потерять продажи из-за дефицита.",
        impact_type_default="opportunity",
        trust_state_default="provisional",
        severity_default="medium",
        allowed_actions_json=[
            "review_price",
            "pricing_review",
            "reduce_promo",
            "reduce_ads",
            "plan_supply",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="negative_reviews_need_reply",
        source_module="problem_engine",
        category="reputation",
        entity_type="product",
        title_template="Негативные отзывы по товару {nm_id} ждут ответа",
        description_template="Негативных отзывов за 30 дней: {negative_reviews_30d}, без ответа: {unanswered_negative_reviews_30d}.",
        recommendation_template="Откройте репутацию, подготовьте корректный ответ и создайте задачу, если нужен разбор качества товара.",
        impact_type_default="opportunity",
        trust_state_default="confirmed",
        severity_default="high",
        allowed_actions_json=[
            "review_reputation",
            "reply_review",
            "check_card_quality",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="questions_need_reply",
        source_module="problem_engine",
        category="reputation",
        entity_type="product",
        title_template="Вопросы покупателей по товару {nm_id} ждут ответа",
        description_template="Вопросов без ответа за 30 дней: {unanswered_questions_30d}.",
        recommendation_template="Ответьте на вопросы покупателей. Если вопрос повторяется, улучшите карточку товара.",
        impact_type_default="opportunity",
        trust_state_default="confirmed",
        severity_default="medium",
        allowed_actions_json=[
            "review_reputation",
            "reply_question",
            "review_content",
            "create_task",
            "recheck",
            "dismiss",
        ],
    ),
    ProblemDefinitionSeed(
        problem_code="low_product_rating",
        source_module="problem_engine",
        category="reputation",
        entity_type="product",
        title_template="Низкий рейтинг товара {nm_id}",
        description_template="Средний рейтинг за 30 дней: {avg_rating_30d}, негативных отзывов: {negative_reviews_30d}.",
        recommendation_template="Разберите причины негативных отзывов, проверьте качество товара, карточку, размеры и ожидания покупателя.",
        impact_type_default="probable_loss",
        trust_state_default="estimated",
        severity_default="high",
        allowed_actions_json=[
            "review_reputation",
            "check_card_quality",
            "review_content",
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
    "ads_spend_no_orders": (
        "Ads spend without orders for {nm_id}",
        "Ad spend in 7 days is {ad_spend_7d}, orders in 7 days are {orders_7d}.",
        "Review campaign, bids, card quality, and price before changing ads.",
    ),
    "price_below_safe_margin": (
        "Price is below safe margin for {nm_id}",
        "Current effective price is {price_after_discount}; margin is {margin_pct}%. Minimum margin is 10%.",
        "Review price and raise it to a safe target if unit economics are complete.",
    ),
    "low_conversion_card": (
        "Low card conversion for {nm_id}",
        "Views in 30 days are {views_30d}, conversion is {conversion_rate}%, and orders are {orders_30d}.",
        "Review title, photo, characteristics, price, reviews, and traffic quality.",
    ),
    "high_return_rate": (
        "High return rate for {nm_id}",
        "Sales in 30 days are {sales_30d}, return rate is {return_rate}%, and revenue is {revenue_30d}.",
        "Review card content, sizing, photos, description, and product quality.",
    ),
    "high_ad_drr": (
        "High ad DRR for {nm_id}",
        "Ad spend in 7 days is {ad_spend_7d}, revenue in 7 days is {revenue_7d}, and DRR is above the safe threshold.",
        "Review campaign, bids, card quality, and price before changing ad budget.",
    ),
    "high_ad_cpo": (
        "High ad CPO for {nm_id}",
        "Ad CPO in 7 days is {ad_cpo_7d}, spend is {ad_spend_7d}, and ad orders are {ad_orders_7d}.",
        "Review bids, clusters, card quality, and price.",
    ),
    "low_ads_ctr": (
        "Low ad CTR for {nm_id}",
        "Ad views in 7 days are {ad_views_7d}, clicks are {ad_clicks_7d}, and CTR is {ad_ctr_7d}%.",
        "Review main photo, price, position, bid, and cluster relevance.",
    ),
    "ads_stockout_risk": (
        "Ads may push {nm_id} into stockout",
        "Ad spend in 7 days is {ad_spend_7d}, and days of stock is {days_of_stock}.",
        "Plan supply or reduce ad demand until replenishment is safe.",
    ),
    "stockout_now_with_recent_orders": (
        "Product {nm_id} is out of stock while demand exists",
        "Current stock is {stock_qty}, and orders in 7 days are {orders_7d}.",
        "Check stock freshness, plan replenishment, and reduce avoidable demand.",
    ),
    "stockout_risk_14d": (
        "Product {nm_id} will run out within 14 days",
        "Days of stock is {days_of_stock}, and 14-day sales velocity is {avg_daily_sales_14d} pcs/day.",
        "Plan replenishment before the product reaches stockout.",
    ),
    "storage_cost_pressure": (
        "Storage pressure for {nm_id}",
        "Stock is {stock_qty}, days of stock is {days_of_stock}, and storage fee per unit is {storage_fee_per_unit}.",
        "Review safe liquidation, bundle, content, or redistribution.",
    ),
    "no_sales_with_views": (
        "Views without orders for {nm_id}",
        "Views in 30 days are {views_30d}, and orders in 30 days are {orders_30d}.",
        "Review photo, title, characteristics, price, reviews, and ad traffic.",
    ),
    "price_offer_blocks_conversion": (
        "Price or offer blocks conversion for {nm_id}",
        "Margin is {margin_pct}%, views are {views_30d}, and conversion is {conversion_rate}%.",
        "Review price against the offer and test a safe price or card improvement.",
    ),
    "raise_price_possible_high_demand": (
        "Price can protect stock for {nm_id}",
        "Orders in 7 days are {orders_7d}, days of stock is {days_of_stock}, and margin is {margin_pct}%.",
        "Review price or promo to protect stock while demand is high.",
    ),
    "negative_reviews_need_reply": (
        "Negative reviews need replies for {nm_id}",
        "Negative reviews in 30 days are {negative_reviews_30d}, unanswered are {unanswered_negative_reviews_30d}.",
        "Open reputation, reply carefully, and create a product quality task if needed.",
    ),
    "questions_need_reply": (
        "Questions need replies for {nm_id}",
        "Unanswered questions in 30 days are {unanswered_questions_30d}.",
        "Reply to buyer questions and improve the card if the same question repeats.",
    ),
    "low_product_rating": (
        "Low product rating for {nm_id}",
        "Average rating in 30 days is {avg_rating_30d}, negative reviews are {negative_reviews_30d}.",
        "Review negative reasons, product quality, card content, sizing, and buyer expectations.",
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
        problem_code="ads_spend_no_orders",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {
                    ">": [
                        {"metric": "ad_spend_7d"},
                        AD_SPEND_NO_ORDERS_THRESHOLD,
                    ]
                },
                {"==": [{"metric": "orders_7d"}, 0]},
            ]
        },
        impact_formula_json={"metric": "ad_spend_7d"},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "ad_spend_7d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "provisional"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения ставки, бюджета, кластера, цены, карточки или после обновления рекламной статистики.",
            "resolved_when": {
                "or": [
                    {
                        "<=": [
                            {"metric": "ad_spend_7d"},
                            AD_SPEND_NO_ORDERS_THRESHOLD,
                        ]
                    },
                    {">": [{"metric": "orders_7d"}, 0]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Расход на рекламу за 7 дней выше 1000 ₽, а заказов за 7 дней нет. Риск считается по потраченному рекламному бюджету.",
            "formula_code": "ads_spend_no_orders.v1",
            "recheck_rule_human": "Перепроверьте после изменения рекламной кампании, карточки, цены или после обновления рекламной статистики.",
            "impact_type": "probable_loss",
            "confidence": "provisional",
            "money_currency": "RUB",
            "trust_notes": [
                "Это не автоматическая остановка рекламы: Action Center открывает review, чтобы оператор проверил кампанию перед изменением."
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
        problem_code="low_conversion_card",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "views_30d"}, LOW_CONVERSION_MIN_VIEWS_30D]},
                {"<": [{"metric": "conversion_rate"}, LOW_CONVERSION_RATE_PCT]},
            ]
        },
        impact_formula_json={"metric": "revenue_30d"},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "views_30d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "opportunity"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения карточки, цены, рекламы или после обновления аналитики карточки.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "views_30d"}, LOW_CONVERSION_MIN_VIEWS_30D]},
                    {">=": [{"metric": "conversion_rate"}, LOW_CONVERSION_RATE_PCT]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Карточка получила больше 1000 просмотров за 30 дней, но конверсия в заказ ниже 1%. Это возможность роста, а не подтверждённый убыток.",
            "formula_code": "low_conversion_card.v1",
            "recheck_rule_human": "Перепроверьте после правки карточки, цены, рекламы или после обновления аналитики карточки.",
            "impact_type": "opportunity",
            "confidence": "opportunity",
            "money_currency": "RUB",
            "trust_notes": [
                "Сумма используется только для приоритизации карточек по обороту; финансовая потеря не считается подтверждённой."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="high_return_rate",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">=": [{"metric": "sales_30d"}, HIGH_RETURN_RATE_MIN_SALES_30D]},
                {">": [{"metric": "return_rate"}, HIGH_RETURN_RATE_PCT]},
            ]
        },
        impact_formula_json={
            "*": [
                {"metric": "revenue_30d"},
                {"/": [{"metric": "return_rate"}, 100]},
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "return_rate"}, 50]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после правки карточки, размерной сетки, фото, описания или после обновления продаж и возвратов.",
            "resolved_when": {
                "or": [
                    {"<": [{"metric": "sales_30d"}, HIGH_RETURN_RATE_MIN_SALES_30D]},
                    {"<=": [{"metric": "return_rate"}, HIGH_RETURN_RATE_PCT]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Продаж за 30 дней не меньше 5, а возвратность выше 30%. Риск считается как доля выручки, соответствующая возвратности.",
            "formula_code": "high_return_rate.v1",
            "recheck_rule_human": "Перепроверьте после правки карточки, размерной сетки, описания или после обновления продаж и возвратов.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="high_ad_drr",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {">": [{"metric": "ad_spend_7d"}, AD_SPEND_NO_ORDERS_THRESHOLD]},
                {">": [{"metric": "revenue_7d"}, 0]},
                {
                    ">": [
                        {
                            "*": [
                                {"/": [{"metric": "ad_spend_7d"}, {"metric": "revenue_7d"}]},
                                100,
                            ]
                        },
                        HIGH_AD_DRR_PCT,
                    ]
                },
            ]
        },
        impact_formula_json={"metric": "ad_spend_7d"},
        severity_formula_json={
            "case": [
                {
                    "if": {
                        ">": [
                            {
                                "*": [
                                    {"/": [{"metric": "ad_spend_7d"}, {"metric": "revenue_7d"}]},
                                    100,
                                ]
                            },
                            40,
                        ]
                    },
                    "then": "high",
                },
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения ставок, бюджета, цены, карточки или обновления рекламы и продаж.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "ad_spend_7d"}, AD_SPEND_NO_ORDERS_THRESHOLD]},
                    {"<=": [{"metric": "revenue_7d"}, 0]},
                    {
                        "<=": [
                            {
                                "*": [
                                    {"/": [{"metric": "ad_spend_7d"}, {"metric": "revenue_7d"}]},
                                    100,
                                ]
                            },
                            HIGH_AD_DRR_PCT,
                        ]
                    },
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Расход на рекламу за 7 дней выше 1000 ₽, выручка есть, а ДРР выше 25%.",
            "formula_code": "high_ad_drr.v1",
            "recheck_rule_human": "Перепроверьте после изменения рекламы, цены, карточки или обновления продаж.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="high_ad_cpo",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {">": [{"metric": "ad_spend_7d"}, AD_SPEND_NO_ORDERS_THRESHOLD]},
                {">": [{"metric": "ad_orders_7d"}, 0]},
                {">": [{"metric": "ad_cpo_7d"}, HIGH_AD_CPO_RUB]},
            ]
        },
        impact_formula_json={
            "max": [
                0,
                {
                    "-": [
                        {"metric": "ad_spend_7d"},
                        {"*": [{"metric": "ad_orders_7d"}, HIGH_AD_CPO_RUB]},
                    ]
                },
            ]
        },
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "ad_cpo_7d"}, 1000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения ставок, кластера, бюджета, карточки или цены.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "ad_spend_7d"}, AD_SPEND_NO_ORDERS_THRESHOLD]},
                    {"<=": [{"metric": "ad_orders_7d"}, 0]},
                    {"<=": [{"metric": "ad_cpo_7d"}, HIGH_AD_CPO_RUB]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Расход на рекламу за 7 дней выше 1000 ₽, есть рекламные заказы, но CPO выше 500 ₽.",
            "formula_code": "high_ad_cpo.v1",
            "recheck_rule_human": "Перепроверьте после изменения ставок, кластера, карточки или цены.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="low_ads_ctr",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {">": [{"metric": "ad_views_7d"}, LOW_AD_CTR_MIN_VIEWS_7D]},
                {"<": [{"metric": "ad_ctr_7d"}, LOW_AD_CTR_PCT]},
            ]
        },
        impact_formula_json={"metric": "ad_spend_7d"},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "ad_spend_7d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "opportunity"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения фото, ставки, позиции, кластера, цены или обновления рекламной статистики.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "ad_views_7d"}, LOW_AD_CTR_MIN_VIEWS_7D]},
                    {">=": [{"metric": "ad_ctr_7d"}, LOW_AD_CTR_PCT]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Показов рекламы за 7 дней больше 1000, но CTR ниже 0.5%.",
            "formula_code": "low_ads_ctr.v1",
            "recheck_rule_human": "Перепроверьте после правки фото, ставки, позиции, кластера или цены.",
            "impact_type": "opportunity",
            "confidence": "opportunity",
            "money_currency": "RUB",
            "trust_notes": [
                "Расход используется для приоритизации, а не как подтверждённый убыток."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="ads_stockout_risk",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {">": [{"metric": "ad_spend_7d"}, AD_SPEND_WITHOUT_PROFIT_THRESHOLD]},
                {"<": [{"metric": "days_of_stock"}, ADS_STOCK_RISK_DAYS]},
                {">": [{"metric": "avg_daily_sales_7d"}, 0]},
            ]
        },
        impact_formula_json={"metric": "ad_spend_7d"},
        severity_formula_json={
            "case": [
                {"if": {"<": [{"metric": "days_of_stock"}, 1]}, "then": "critical"},
                {"else": "high"},
            ]
        },
        confidence_formula_json={"case": [{"else": "provisional"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после поставки, обновления остатков или изменения рекламы.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "ad_spend_7d"}, AD_SPEND_WITHOUT_PROFIT_THRESHOLD]},
                    {">=": [{"metric": "days_of_stock"}, ADS_STOCK_RISK_DAYS]},
                    {"<=": [{"metric": "avg_daily_sales_7d"}, 0]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Расход на рекламу за 7 дней выше 500 ₽, а запаса меньше чем на 3 дня.",
            "formula_code": "ads_stockout_risk.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, поставки или изменения рекламы.",
            "impact_type": "lost_sales_risk",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="stockout_now_with_recent_orders",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {"<=": [{"metric": "stock_qty"}, 0]},
                {">": [{"metric": "orders_7d"}, 0]},
            ]
        },
        impact_formula_json={"*": [{"metric": "avg_daily_revenue_7d"}, 7]},
        severity_formula_json={"case": [{"else": "critical"}]},
        confidence_formula_json={"case": [{"else": "provisional"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков или создания поставки.",
            "resolved_when": {
                "or": [
                    {">": [{"metric": "stock_qty"}, 0]},
                    {"<=": [{"metric": "orders_7d"}, 0]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Текущий остаток равен нулю или ниже, но за 7 дней есть заказы.",
            "formula_code": "stockout_now_with_recent_orders.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков или создания поставки.",
            "impact_type": "lost_sales_risk",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="stockout_risk_14d",
        version=1,
        evaluation_grain="product_period",
        lookback_days=14,
        condition_json={
            "and": [
                {">=": [{"metric": "days_of_stock"}, LOW_STOCK_RISK_DAYS]},
                {"<": [{"metric": "days_of_stock"}, STOCKOUT_RISK_14D_DAYS]},
                {">": [{"metric": "avg_daily_sales_14d"}, 1]},
            ]
        },
        impact_formula_json={
            "*": [
                {"metric": "avg_daily_revenue_7d"},
                {"max": [0, {"-": [STOCKOUT_RISK_14D_DAYS, {"metric": "days_of_stock"}]}]},
            ]
        },
        severity_formula_json={"case": [{"else": "medium"}]},
        confidence_formula_json={"case": [{"else": "provisional"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
            "resolved_when": {
                "or": [
                    {">=": [{"metric": "days_of_stock"}, STOCKOUT_RISK_14D_DAYS]},
                    {"<": [{"metric": "days_of_stock"}, LOW_STOCK_RISK_DAYS]},
                    {"<=": [{"metric": "avg_daily_sales_14d"}, 1]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Запаса от 7 до 14 дней, а средние продажи за 14 дней выше 1 шт./день.",
            "formula_code": "stockout_risk_14d.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
            "impact_type": "lost_sales_risk",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="storage_cost_pressure",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "stock_qty"}, STORAGE_PRESSURE_STOCK_QTY]},
                {">": [{"metric": "days_of_stock"}, STORAGE_PRESSURE_DAYS]},
                {">": [{"metric": "storage_fee_per_unit"}, STORAGE_PRESSURE_FEE_PER_UNIT]},
            ]
        },
        impact_formula_json={
            "*": [{"metric": "stock_qty"}, {"metric": "storage_fee_per_unit"}]
        },
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "days_of_stock"}, 120]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после обновления остатков, хранения, продаж или безопасной распродажи.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "stock_qty"}, STORAGE_PRESSURE_STOCK_QTY]},
                    {"<=": [{"metric": "days_of_stock"}, STORAGE_PRESSURE_DAYS]},
                    {"<=": [{"metric": "storage_fee_per_unit"}, STORAGE_PRESSURE_FEE_PER_UNIT]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Остаток выше 50 штук, запаса больше чем на 60 дней, а хранение на единицу выше 5 ₽.",
            "formula_code": "storage_cost_pressure.v1",
            "recheck_rule_human": "Перепроверьте после изменения остатков, хранения, продаж или безопасной распродажи.",
            "impact_type": "blocked_cash",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="no_sales_with_views",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "views_30d"}, NO_SALES_WITH_VIEWS_MIN_VIEWS_30D]},
                {"==": [{"metric": "orders_30d"}, 0]},
            ]
        },
        impact_formula_json={"case": [{"else": 0}]},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "views_30d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "opportunity"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после правки карточки, цены, рекламы или обновления аналитики.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "views_30d"}, NO_SALES_WITH_VIEWS_MIN_VIEWS_30D]},
                    {">": [{"metric": "orders_30d"}, 0]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Карточка получила больше 1000 просмотров за 30 дней, но заказов за 30 дней нет.",
            "formula_code": "no_sales_with_views.v1",
            "recheck_rule_human": "Перепроверьте после правки карточки, цены, рекламы или обновления аналитики.",
            "impact_type": "opportunity",
            "confidence": "opportunity",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="price_offer_blocks_conversion",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "views_30d"}, LOW_CONVERSION_MIN_VIEWS_30D]},
                {"<": [{"metric": "conversion_rate"}, LOW_CONVERSION_RATE_PCT]},
                {">": [{"metric": "margin_pct"}, PRICE_CONVERSION_MIN_MARGIN_PCT]},
            ]
        },
        impact_formula_json={"metric": "revenue_30d"},
        severity_formula_json={
            "case": [
                {"if": {">": [{"metric": "views_30d"}, 5000]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "opportunity"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после изменения цены, карточки, рекламы или обновления аналитики.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "views_30d"}, LOW_CONVERSION_MIN_VIEWS_30D]},
                    {">=": [{"metric": "conversion_rate"}, LOW_CONVERSION_RATE_PCT]},
                    {"<=": [{"metric": "margin_pct"}, PRICE_CONVERSION_MIN_MARGIN_PCT]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Просмотров больше 1000, конверсия ниже 1%, а маржа выше 30%, поэтому цену или оффер можно безопасно проверить.",
            "formula_code": "price_offer_blocks_conversion.v1",
            "recheck_rule_human": "Перепроверьте после изменения цены, карточки, рекламы или обновления аналитики.",
            "impact_type": "opportunity",
            "confidence": "opportunity",
            "money_currency": "RUB",
            "trust_notes": [
                "Это гипотеза для price review, а не автоматическое снижение цены."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="raise_price_possible_high_demand",
        version=1,
        evaluation_grain="product_period",
        lookback_days=7,
        condition_json={
            "and": [
                {">": [{"metric": "orders_7d"}, HIGH_DEMAND_ORDERS_7D]},
                {"<": [{"metric": "days_of_stock"}, PRICE_PROTECT_STOCK_DAYS]},
                {"<": [{"metric": "margin_pct"}, PRICE_CONVERSION_MIN_MARGIN_PCT]},
                {">": [{"metric": "price_after_discount"}, 0]},
            ]
        },
        impact_formula_json={
            "*": [
                {"metric": "avg_daily_revenue_7d"},
                {"max": [0, {"-": [PRICE_PROTECT_STOCK_DAYS, {"metric": "days_of_stock"}]}]},
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
            "human": "Запустите повторную проверку после изменения цены, промо, рекламы, поставки или обновления остатков.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "orders_7d"}, HIGH_DEMAND_ORDERS_7D]},
                    {">=": [{"metric": "days_of_stock"}, PRICE_PROTECT_STOCK_DAYS]},
                    {">=": [{"metric": "margin_pct"}, PRICE_CONVERSION_MIN_MARGIN_PCT]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Заказов за 7 дней больше 20, запаса меньше 7 дней, а маржа ниже 30%. Price review может защитить остаток.",
            "formula_code": "raise_price_possible_high_demand.v1",
            "recheck_rule_human": "Перепроверьте после изменения цены, промо, рекламы, поставки или обновления остатков.",
            "impact_type": "opportunity",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="negative_reviews_need_reply",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "negative_reviews_30d"}, 0]},
                {">": [{"metric": "unanswered_negative_reviews_30d"}, 0]},
            ]
        },
        impact_formula_json={"metric": "revenue_30d"},
        severity_formula_json={
            "case": [
                {
                    "if": {
                        ">=": [{"metric": "unanswered_negative_reviews_30d"}, 3]
                    },
                    "then": "critical",
                },
                {"else": "high"},
            ]
        },
        confidence_formula_json={"case": [{"else": "confirmed"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после ответа на отзывы или обновления репутации.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "negative_reviews_30d"}, 0]},
                    {"<=": [{"metric": "unanswered_negative_reviews_30d"}, 0]},
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "За 30 дней есть негативные отзывы, и хотя бы один негативный отзыв всё ещё без ответа.",
            "formula_code": "negative_reviews_need_reply.v1",
            "recheck_rule_human": "Перепроверьте после ответа на отзывы или обновления репутации.",
            "impact_type": "opportunity",
            "confidence": "confirmed",
            "money_currency": "RUB",
            "trust_notes": [
                "Выручка используется для приоритизации карточек, а не как подтверждённый убыток."
            ],
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="questions_need_reply",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={">": [{"metric": "unanswered_questions_30d"}, 0]},
        impact_formula_json={"case": [{"else": 0}]},
        severity_formula_json={
            "case": [
                {"if": {">=": [{"metric": "unanswered_questions_30d"}, 5]}, "then": "high"},
                {"else": "medium"},
            ]
        },
        confidence_formula_json={"case": [{"else": "confirmed"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после ответа на вопросы или обновления репутации.",
            "resolved_when": {"<=": [{"metric": "unanswered_questions_30d"}, 0]},
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "За 30 дней есть вопросы покупателей без ответа.",
            "formula_code": "questions_need_reply.v1",
            "recheck_rule_human": "Перепроверьте после ответа на вопросы или обновления репутации.",
            "impact_type": "opportunity",
            "confidence": "confirmed",
            "money_currency": "RUB",
        },
    ),
    ProblemRuleVersionSeed(
        problem_code="low_product_rating",
        version=1,
        evaluation_grain="product_period",
        lookback_days=30,
        condition_json={
            "and": [
                {">": [{"metric": "avg_rating_30d"}, 0]},
                {"<": [{"metric": "avg_rating_30d"}, LOW_PRODUCT_RATING_THRESHOLD]},
                {
                    ">=": [
                        {"metric": "negative_reviews_30d"},
                        LOW_PRODUCT_RATING_MIN_NEGATIVE_REVIEWS,
                    ]
                },
            ]
        },
        impact_formula_json={"metric": "revenue_30d"},
        severity_formula_json={
            "case": [
                {"if": {"<": [{"metric": "avg_rating_30d"}, 3.5]}, "then": "critical"},
                {"else": "high"},
            ]
        },
        confidence_formula_json={"case": [{"else": "estimated"}]},
        recheck_rule_json={
            "human": "Запустите повторную проверку после ответа на отзывы, правки карточки, проверки качества или обновления репутации.",
            "resolved_when": {
                "or": [
                    {
                        ">=": [
                            {"metric": "avg_rating_30d"},
                            LOW_PRODUCT_RATING_THRESHOLD,
                        ]
                    },
                    {
                        "<": [
                            {"metric": "negative_reviews_30d"},
                            LOW_PRODUCT_RATING_MIN_NEGATIVE_REVIEWS,
                        ]
                    },
                ]
            },
            "missing_metrics_policy": "condition_only",
        },
        evidence_template_json={
            "formula_human": "Средний рейтинг за 30 дней ниже 4.0, и негативных отзывов не меньше 2.",
            "formula_code": "low_product_rating.v1",
            "recheck_rule_human": "Перепроверьте после ответа на отзывы, правки карточки, проверки качества или обновления репутации.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
            "trust_notes": [
                "Выручка используется для приоритизации товара, а причина рейтинга требует ручного разбора."
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
