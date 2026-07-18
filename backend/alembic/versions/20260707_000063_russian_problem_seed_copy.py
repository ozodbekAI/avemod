"""Update system-seeded dynamic problem copy to Russian.

Revision ID: 20260707_000063
Revises: 20260707_000062
Create Date: 2026-07-07
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "20260707_000063"
down_revision = "20260707_000062"
branch_labels = None
depends_on = None


DEFINITION_COPY: tuple[dict[str, str], ...] = (
    {
        "code": "missing_cost_blocks_profit",
        "old_title": "Missing cost blocks profit for {nm_id}",
        "old_description": "Revenue in 30 days is {revenue_30d}, but cost_price is missing, so profitability cannot be trusted.",
        "old_recommendation": "Upload or map cost price before profitability can be trusted.",
        "new_title": "Нет себестоимости для товара {nm_id}",
        "new_description": "За 30 дней есть выручка {revenue_30d}, но себестоимость не заполнена. Поэтому прибыль и маржа по товару пока не считаются надёжно.",
        "new_recommendation": "Загрузите или сопоставьте себестоимость, затем запустите повторную проверку прибыльности.",
    },
    {
        "code": "negative_unit_profit",
        "old_title": "Negative unit profit for {nm_id}",
        "old_description": "Unit profit is {unit_profit} and margin is {margin_pct}%. Minimum margin is 10%.",
        "old_recommendation": "Review price, cost, ads spend, promo, and logistics.",
        "new_title": "Товар {nm_id} продаётся в минус",
        "new_description": "Прибыль на единицу: {unit_profit}, маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
        "new_recommendation": "Проверьте цену, себестоимость, рекламу, промо и логистику. Не снижайте цену без проверки безопасной маржи.",
    },
    {
        "code": "overstock_slow_moving",
        "old_title": "Overstock and slow moving product {nm_id}",
        "old_description": "Stock is {stock_qty}, days of stock is {days_of_stock}, and 14-day sales velocity is {avg_daily_sales_14d} pcs/day.",
        "old_recommendation": "Consider safe promo, price review, bundle, or ads/content check.",
        "new_title": "Пересток и медленные продажи по товару {nm_id}",
        "new_description": "Остаток: {stock_qty}, запас в днях: {days_of_stock}, средние продажи за 14 дней: {avg_daily_sales_14d} шт./день.",
        "new_recommendation": "Проверьте безопасное промо, цену, комплект, рекламу или качество карточки. Скидку можно запускать только после проверки маржи.",
    },
    {
        "code": "low_stock_risk",
        "old_title": "Low stock risk for {nm_id}",
        "old_description": "Days of stock is {days_of_stock} while 7-day sales velocity is {avg_daily_sales_7d} pcs/day.",
        "old_recommendation": "Plan supply/replenishment. If supply cannot happen, reduce promo/ads.",
        "new_title": "Риск низкого остатка по товару {nm_id}",
        "new_description": "Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
        "new_recommendation": "Запланируйте поставку или пополнение. Если поставить товар быстро нельзя, снизьте промо или рекламу, чтобы не уйти в дефицит.",
    },
    {
        "code": "ads_spend_without_profit",
        "old_title": "Ads spend without profit for {nm_id}",
        "old_description": "Ad spend in 7 days is {ad_spend_7d}; unit profit after ads is {unit_profit_after_ads}.",
        "old_recommendation": "Pause or lower ads, check card quality, review bids and price.",
        "new_title": "Реклама съедает прибыль по товару {nm_id}",
        "new_description": "Расход на рекламу за 7 дней: {ad_spend_7d}; прибыль на единицу после рекламы: {unit_profit_after_ads}.",
        "new_recommendation": "Снизьте или приостановите рекламу, проверьте качество карточки, ставки и цену.",
    },
    {
        "code": "promo_not_profitable",
        "old_title": "Promo is not profitable for {nm_id}",
        "old_description": "Promo spend is {promo_spend_30d}, unit profit is {unit_profit}, and margin is {margin_pct}%.",
        "old_recommendation": "Reduce or pause promo, review price, and check whether the discount still preserves safe margin.",
        "new_title": "Промо уводит товар {nm_id} в минус",
        "new_description": "Расход на промо: {promo_spend_30d}, прибыль на единицу: {unit_profit}, маржа: {margin_pct}%.",
        "new_recommendation": "Снизьте или остановите промо, проверьте цену и убедитесь, что скидка сохраняет безопасную маржу.",
    },
    {
        "code": "price_below_safe_margin",
        "old_title": "Price is below safe margin for {nm_id}",
        "old_description": "Current effective price is {price_after_discount}; margin is {margin_pct}%. Minimum margin is 10%.",
        "old_recommendation": "Review price and raise it to a safe target if unit economics are complete.",
        "new_title": "Цена ниже безопасной маржи по товару {nm_id}",
        "new_description": "Текущая эффективная цена: {price_after_discount}; маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
        "new_recommendation": "Проверьте цену и поднимите её до безопасного уровня, если экономика товара заполнена полностью.",
    },
    {
        "code": "dead_stock",
        "old_title": "Dead stock risk for {nm_id}",
        "old_description": "Stock is {stock_qty}, sales in 30 days are {sales_30d}, and days of stock is {days_of_stock}.",
        "old_recommendation": "Review content, ads, bundle options, and safe liquidation path before discounting.",
        "new_title": "Риск зависшего остатка по товару {nm_id}",
        "new_description": "Остаток: {stock_qty}, продажи за 30 дней: {sales_30d}, запас в днях: {days_of_stock}.",
        "new_recommendation": "Проверьте карточку, рекламу, комплекты и безопасный сценарий распродажи до запуска скидки.",
    },
    {
        "code": "fast_stock_depletion",
        "old_title": "Fast stock depletion for {nm_id}",
        "old_description": "Days of stock is {days_of_stock} while 7-day sales velocity is {avg_daily_sales_7d} pcs/day.",
        "old_recommendation": "Plan urgent replenishment. If supply cannot happen, reduce promo/ads to avoid stockout.",
        "new_title": "Товар {nm_id} быстро заканчивается",
        "new_description": "Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
        "new_recommendation": "Срочно запланируйте пополнение. Если поставка невозможна, снизьте промо или рекламу, чтобы избежать дефицита.",
    },
)


RULE_COPY: tuple[dict[str, object], ...] = (
    {
        "code": "missing_cost_blocks_profit",
        "old_recheck": "Re-run after cost mapping/upload or when the product no longer has revenue in the window.",
        "old_formula": "cost_price is missing AND revenue_30d > 0",
        "old_evidence_recheck": "Upload/map cost or re-run after revenue changes.",
        "new_recheck": "Запустите повторную проверку после загрузки или сопоставления себестоимости либо когда в периоде больше нет выручки.",
        "new_formula": "Себестоимость отсутствует, а выручка за 30 дней больше 0.",
        "new_evidence_recheck": "Загрузите или сопоставьте себестоимость, затем перепроверьте товар после обновления выручки.",
        "old_trust_notes": ["Negative profit is intentionally not evaluated while cost data is missing."],
        "new_trust_notes": ["Платформа специально не считает отрицательную прибыль, пока не хватает себестоимости."],
    },
    {
        "code": "negative_unit_profit",
        "old_recheck": "Re-run after price, cost, ads, promo, logistics, or margin data changes.",
        "old_formula": "cost_price exists AND (unit_profit < 0 OR margin_pct < 10)",
        "old_evidence_recheck": "Re-run after price, cost, ads, promo, logistics, or margin changes.",
        "new_recheck": "Запустите повторную проверку после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
        "new_formula": "Себестоимость заполнена, и прибыль на единицу ниже 0 или маржа ниже 10%.",
        "new_evidence_recheck": "Перепроверьте после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
        "old_trust_notes": ["This rule is blocked when cost_price is missing; missing_cost_blocks_profit should trigger instead."],
        "new_trust_notes": ["Если себестоимость отсутствует, это правило блокируется и вместо него показывается проблема с недостающей себестоимостью."],
    },
    {
        "code": "overstock_slow_moving",
        "old_recheck": "Re-run after stock, sales velocity, or cost data changes.",
        "old_formula": "stock_qty > 50 AND days_of_stock > 60 AND avg_daily_sales_14d < 2; blocked_cash = max(stock_qty - 50, 0) * cost_price",
        "old_evidence_recheck": "Re-run after stock, sales velocity, or cost updates.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, скорости продаж или себестоимости.",
        "new_formula": "Остаток выше 50 штук, запаса больше чем на 60 дней, а средние продажи за 14 дней ниже 2 шт./день. Замороженные деньги считаются по лишнему остатку и себестоимости.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, скорости продаж или себестоимости.",
    },
    {
        "code": "low_stock_risk",
        "old_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "old_formula": "days_of_stock < 7 AND avg_daily_sales_7d > 1; lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)",
        "old_evidence_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
        "new_formula": "Запаса меньше чем на 7 дней, а средние продажи за 7 дней выше 1 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
    },
    {
        "code": "ads_spend_without_profit",
        "old_recheck": "Re-run after ads spend, bid, price, or profit data changes.",
        "old_formula": "ad_spend_7d > 500 AND unit_profit_after_ads < 0; probable_loss = abs(unit_profit_after_ads) * units_sold_7d",
        "old_evidence_recheck": "Re-run after ads spend, bid, price, or profit changes.",
        "new_recheck": "Запустите повторную проверку после изменения рекламных расходов, ставок, цены или прибыли.",
        "new_formula": "Расход на рекламу за 7 дней выше 500, а прибыль на единицу после рекламы ниже 0. Вероятный убыток считается по модулю прибыли после рекламы и продажам за 7 дней.",
        "new_evidence_recheck": "Перепроверьте после изменения рекламных расходов, ставок, цены или прибыли.",
    },
    {
        "code": "promo_not_profitable",
        "old_recheck": "Re-run after promo spend, price, cost, or margin data changes.",
        "old_formula": "cost_price exists AND promo_spend_30d > 0 AND (unit_profit < 0 OR margin_pct < 10)",
        "old_evidence_recheck": "Re-run after promo spend, price, cost, or margin changes.",
        "new_recheck": "Запустите повторную проверку после изменения промо, цены, себестоимости или маржи.",
        "new_formula": "Себестоимость заполнена, есть расходы на промо, и прибыль на единицу ниже 0 или маржа ниже 10%.",
        "new_evidence_recheck": "Перепроверьте после изменения промо, цены, себестоимости или маржи.",
        "old_trust_notes": ["Promo recommendations are bounded by price-safety unit economics."],
        "new_trust_notes": ["Рекомендации по промо ограничены проверкой безопасной маржи и экономики единицы товара."],
    },
    {
        "code": "price_below_safe_margin",
        "old_recheck": "Re-run after price, cost, fee, or margin data changes.",
        "old_formula": "cost_price exists AND price_after_discount > 0 AND margin_pct < 10",
        "old_evidence_recheck": "Re-run after price, cost, fee, or margin changes.",
        "new_recheck": "Запустите повторную проверку после изменения цены, себестоимости, комиссий или маржи.",
        "new_formula": "Себестоимость заполнена, эффективная цена выше 0, а маржа ниже 10%.",
        "new_evidence_recheck": "Перепроверьте после изменения цены, себестоимости, комиссий или маржи.",
        "old_trust_notes": ["Target price is calculated from cost plus commission, logistics, acquiring, and storage."],
        "new_trust_notes": ["Целевая цена считается из себестоимости, комиссии, логистики, эквайринга и хранения."],
    },
    {
        "code": "dead_stock",
        "old_recheck": "Re-run after stock, sales, or cost data changes.",
        "old_formula": "stock_qty > 0 AND sales_30d = 0 AND days_of_stock > 90; blocked_cash = stock_qty * cost_price",
        "old_evidence_recheck": "Re-run after stock, sales, or cost changes.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, продаж или себестоимости.",
        "new_formula": "Остаток больше 0, продаж за 30 дней нет, а запас больше чем на 90 дней. Замороженные деньги считаются как остаток, умноженный на себестоимость.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, продаж или себестоимости.",
    },
    {
        "code": "fast_stock_depletion",
        "old_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "old_formula": "days_of_stock < 3 AND avg_daily_sales_7d > 2; lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)",
        "old_evidence_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
        "new_formula": "Запаса меньше чем на 3 дня, а средние продажи за 7 дней выше 2 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
    },
)


def _update_definitions(*, reverse: bool = False) -> None:
    statement = sa.text(
        """
        UPDATE problem_definitions
        SET title_template = :target_title,
            description_template = :target_description,
            recommendation_template = :target_recommendation,
            updated_at = now()
        WHERE problem_code = :code
          AND source_module = 'problem_engine'
          AND created_by_user_id IS NULL
          AND title_template = :match_title
          AND description_template = :match_description
          AND recommendation_template = :match_recommendation
        """
    )
    bind = op.get_bind()
    for row in DEFINITION_COPY:
        source = "new" if reverse else "old"
        target = "old" if reverse else "new"
        bind.execute(
            statement,
            {
                "code": row["code"],
                "match_title": row[f"{source}_title"],
                "match_description": row[f"{source}_description"],
                "match_recommendation": row[f"{source}_recommendation"],
                "target_title": row[f"{target}_title"],
                "target_description": row[f"{target}_description"],
                "target_recommendation": row[f"{target}_recommendation"],
            },
        )


def _update_rules(*, reverse: bool = False) -> None:
    bind = op.get_bind()
    base_statement = sa.text(
        """
        UPDATE problem_rule_versions AS prv
        SET recheck_rule_json = jsonb_set(
                COALESCE(prv.recheck_rule_json, '{}'::jsonb),
                '{human}',
                to_jsonb(CAST(:target_recheck AS text)),
                true
            ),
            evidence_template_json = jsonb_set(
                jsonb_set(
                    COALESCE(prv.evidence_template_json, '{}'::jsonb),
                    '{formula_human}',
                    to_jsonb(CAST(:target_formula AS text)),
                    true
                ),
                '{recheck_rule_human}',
                to_jsonb(CAST(:target_evidence_recheck AS text)),
                true
            ),
            updated_at = now()
        FROM problem_definitions AS pd
        WHERE pd.id = prv.problem_definition_id
          AND pd.problem_code = :code
          AND pd.source_module = 'problem_engine'
          AND pd.created_by_user_id IS NULL
          AND prv.created_by_user_id IS NULL
          AND prv.version = 1
          AND prv.recheck_rule_json ->> 'human' = :match_recheck
          AND prv.evidence_template_json ->> 'formula_human' = :match_formula
          AND prv.evidence_template_json ->> 'recheck_rule_human' = :match_evidence_recheck
        """
    )
    trust_statement = sa.text(
        """
        UPDATE problem_rule_versions AS prv
        SET evidence_template_json = jsonb_set(
                COALESCE(prv.evidence_template_json, '{}'::jsonb),
                '{trust_notes}',
                CAST(:target_trust_notes AS jsonb),
                true
            ),
            updated_at = now()
        FROM problem_definitions AS pd
        WHERE pd.id = prv.problem_definition_id
          AND pd.problem_code = :code
          AND pd.source_module = 'problem_engine'
          AND pd.created_by_user_id IS NULL
          AND prv.created_by_user_id IS NULL
          AND prv.version = 1
          AND prv.recheck_rule_json ->> 'human' = :target_recheck
          AND prv.evidence_template_json ->> 'formula_human' = :target_formula
          AND prv.evidence_template_json ->> 'recheck_rule_human' = :target_evidence_recheck
          AND prv.evidence_template_json -> 'trust_notes' = CAST(:match_trust_notes AS jsonb)
        """
    )
    for row in RULE_COPY:
        source = "new" if reverse else "old"
        target = "old" if reverse else "new"
        bind.execute(
            base_statement,
            {
                "code": row["code"],
                "match_recheck": row[f"{source}_recheck"],
                "match_formula": row[f"{source}_formula"],
                "match_evidence_recheck": row[f"{source}_evidence_recheck"],
                "target_recheck": row[f"{target}_recheck"],
                "target_formula": row[f"{target}_formula"],
                "target_evidence_recheck": row[f"{target}_evidence_recheck"],
            },
        )
        if row.get("old_trust_notes") and row.get("new_trust_notes"):
            bind.execute(
                trust_statement,
                {
                    "code": row["code"],
                    "target_recheck": row[f"{target}_recheck"],
                    "target_formula": row[f"{target}_formula"],
                    "target_evidence_recheck": row[f"{target}_evidence_recheck"],
                    "match_trust_notes": json.dumps(row[f"{source}_trust_notes"], ensure_ascii=False),
                    "target_trust_notes": json.dumps(row[f"{target}_trust_notes"], ensure_ascii=False),
                },
            )


def upgrade() -> None:
    _update_definitions()
    _update_rules()


def downgrade() -> None:
    _update_rules(reverse=True)
    _update_definitions(reverse=True)
