"""Seed remaining Dynamic Problem Engine product rules.

Revision ID: 20260706_000061
Revises: 20260706_000060
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260706_000061"
down_revision = "20260706_000060"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())
MINIMUM_MARGIN_PCT = 10
DEAD_STOCK_DAYS_THRESHOLD = 90
FAST_STOCK_DEPLETION_DAYS = 3
LOW_STOCK_RISK_DAYS = 7


def _definition(
    problem_code: str,
    category: str,
    title_template: str,
    description_template: str,
    recommendation_template: str,
    impact_type_default: str,
    trust_state_default: str,
    severity_default: str,
    allowed_actions: list[str],
) -> dict:
    return {
        "problem_code": problem_code,
        "source_module": "problem_engine",
        "category": category,
        "entity_type": "product",
        "title_template": title_template,
        "description_template": description_template,
        "recommendation_template": recommendation_template,
        "impact_type_default": impact_type_default,
        "trust_state_default": trust_state_default,
        "severity_default": severity_default,
        "allowed_actions_json": allowed_actions,
        "status": "active",
    }


PROBLEM_DEFINITIONS = [
    _definition(
        "promo_not_profitable",
        "promo",
        "Промо уводит товар {nm_id} в минус",
        "Расход на промо: {promo_spend_30d}, прибыль на единицу: {unit_profit}, маржа: {margin_pct}%.",
        "Снизьте или остановите промо, проверьте цену и убедитесь, что скидка сохраняет безопасную маржу.",
        "probable_loss",
        "estimated",
        "high",
        ["review_promo", "reduce_promo", "review_price", "review_cost", "create_task", "recheck", "dismiss"],
    ),
    _definition(
        "price_below_safe_margin",
        "price",
        "Цена ниже безопасной маржи по товару {nm_id}",
        "Текущая эффективная цена: {price_after_discount}; маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.",
        "Проверьте цену и поднимите её до безопасного уровня, если экономика товара заполнена полностью.",
        "probable_loss",
        "estimated",
        "high",
        ["review_price", "pricing_review", "review_cost", "create_task", "recheck", "dismiss"],
    ),
    _definition(
        "dead_stock",
        "stock",
        "Риск зависшего остатка по товару {nm_id}",
        "Остаток: {stock_qty}, продажи за 30 дней: {sales_30d}, запас в днях: {days_of_stock}.",
        "Проверьте карточку, рекламу, комплекты и безопасный сценарий распродажи до запуска скидки.",
        "blocked_cash",
        "estimated",
        "high",
        ["safe_promo", "bundle", "review_content", "review_ads", "create_task", "recheck", "dismiss"],
    ),
    _definition(
        "fast_stock_depletion",
        "stock",
        "Товар {nm_id} быстро заканчивается",
        "Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.",
        "Срочно запланируйте пополнение. Если поставка невозможна, снизьте промо или рекламу, чтобы избежать дефицита.",
        "lost_sales_risk",
        "provisional",
        "high",
        ["plan_supply", "reduce_promo", "reduce_ads", "create_task", "recheck", "dismiss"],
    ),
]


def _constant(value: str) -> dict:
    return {"case": [{"else": value}]}


def _rule(problem_code: str, lookback_days: int, condition: dict, impact: dict, severity: dict, confidence: dict, recheck: dict, evidence: dict) -> dict:
    return {
        "problem_code": problem_code,
        "version": 1,
        "status": "active",
        "evaluation_grain": "product_period",
        "lookback_days": lookback_days,
        "condition_json": condition,
        "impact_formula_json": impact,
        "severity_formula_json": severity,
        "confidence_formula_json": confidence,
        "dedup_key_template": "{account_id}:{problem_code}:{nm_id}",
        "recheck_rule_json": recheck,
        "evidence_template_json": evidence,
        "published_at": sa.func.now(),
    }


PROBLEM_RULES = [
    _rule(
        "promo_not_profitable",
        30,
        {
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
        {
            "max": [
                {"metric": "promo_spend_30d"},
                {
                    "case": [
                        {
                            "if": {"<": [{"metric": "unit_profit"}, 0]},
                            "then": {"abs": {"*": [{"metric": "unit_profit"}, {"metric": "sales_30d"}]}},
                        },
                        {"else": 0},
                    ]
                },
            ]
        },
        {"case": [{"if": {">": [{"metric": "promo_spend_30d"}, 5000]}, "then": "high"}, {"else": "medium"}]},
        _constant("estimated"),
        {
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
        {
            "formula_human": "Себестоимость заполнена, есть расходы на промо, и прибыль на единицу ниже 0 или маржа ниже 10%.",
            "formula_code": "promo_not_profitable.v1",
            "recheck_rule_human": "Перепроверьте после изменения промо, цены, себестоимости или маржи.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
            "trust_notes": ["Рекомендации по промо ограничены проверкой безопасной маржи и экономики единицы товара."],
        },
    ),
    _rule(
        "price_below_safe_margin",
        30,
        {
            "and": [
                {"not": {"missing": ["cost_price"]}},
                {">": [{"metric": "price_after_discount"}, 0]},
                {"<": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
            ]
        },
        {
            "case": [
                {
                    "if": {"<": [{"metric": "unit_profit"}, 0]},
                    "then": {"abs": {"*": [{"metric": "unit_profit"}, {"metric": "sales_30d"}]}},
                },
                {"else": 0},
            ]
        },
        {"case": [{"if": {"<": [{"metric": "margin_pct"}, 0]}, "then": "high"}, {"else": "medium"}]},
        _constant("estimated"),
        {
            "human": "Запустите повторную проверку после изменения цены, себестоимости, комиссий или маржи.",
            "resolved_when": {
                "or": [
                    {"missing": ["cost_price"]},
                    {">=": [{"metric": "margin_pct"}, MINIMUM_MARGIN_PCT]},
                ]
            },
        },
        {
            "formula_human": "Себестоимость заполнена, эффективная цена выше 0, а маржа ниже 10%.",
            "formula_code": "price_below_safe_margin.v1",
            "recheck_rule_human": "Перепроверьте после изменения цены, себестоимости, комиссий или маржи.",
            "impact_type": "probable_loss",
            "confidence": "estimated",
            "money_currency": "RUB",
            "trust_notes": ["Целевая цена считается из себестоимости, комиссии, логистики, эквайринга и хранения."],
        },
    ),
    _rule(
        "dead_stock",
        30,
        {
            "and": [
                {">": [{"metric": "stock_qty"}, 0]},
                {"==": [{"metric": "sales_30d"}, 0]},
                {">": [{"metric": "days_of_stock"}, DEAD_STOCK_DAYS_THRESHOLD]},
            ]
        },
        {"*": [{"metric": "stock_qty"}, {"metric": "cost_price"}]},
        {"case": [{"if": {">": [{"metric": "stock_qty"}, 100]}, "then": "high"}, {"else": "medium"}]},
        _constant("estimated"),
        {
            "human": "Запустите повторную проверку после обновления остатков, продаж или себестоимости.",
            "resolved_when": {
                "or": [
                    {"<=": [{"metric": "stock_qty"}, 0]},
                    {">": [{"metric": "sales_30d"}, 0]},
                    {"<=": [{"metric": "days_of_stock"}, DEAD_STOCK_DAYS_THRESHOLD]},
                ]
            },
        },
        {
            "formula_human": "Остаток больше 0, продаж за 30 дней нет, а запас больше чем на 90 дней. Замороженные деньги считаются как остаток, умноженный на себестоимость.",
            "formula_code": "dead_stock.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, продаж или себестоимости.",
            "impact_type": "blocked_cash",
            "confidence": "estimated",
            "money_currency": "RUB",
        },
    ),
    _rule(
        "fast_stock_depletion",
        7,
        {
            "and": [
                {"<": [{"metric": "days_of_stock"}, FAST_STOCK_DEPLETION_DAYS]},
                {">": [{"metric": "avg_daily_sales_7d"}, 2]},
            ]
        },
        {
            "*": [
                {"metric": "avg_daily_revenue_7d"},
                {"max": [0, {"-": [LOW_STOCK_RISK_DAYS, {"metric": "days_of_stock"}]}]},
            ]
        },
        {"case": [{"if": {"<": [{"metric": "days_of_stock"}, 1]}, "then": "critical"}, {"else": "high"}]},
        _constant("provisional"),
        {
            "human": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
            "resolved_when": {
                "or": [
                    {">=": [{"metric": "days_of_stock"}, FAST_STOCK_DEPLETION_DAYS]},
                    {"<=": [{"metric": "avg_daily_sales_7d"}, 2]},
                ]
            },
        },
        {
            "formula_human": "Запаса меньше чем на 3 дня, а средние продажи за 7 дней выше 2 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
            "formula_code": "fast_stock_depletion.v1",
            "recheck_rule_human": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
            "impact_type": "lost_sales_risk",
            "confidence": "provisional",
            "money_currency": "RUB",
        },
    ),
]


PROBLEM_CODES = [definition["problem_code"] for definition in PROBLEM_DEFINITIONS]


def _definition_table() -> sa.TableClause:
    return sa.table(
        "problem_definitions",
        sa.column("id", sa.BigInteger),
        sa.column("problem_code", sa.String),
        sa.column("source_module", sa.String),
        sa.column("category", sa.String),
        sa.column("entity_type", sa.String),
        sa.column("title_template", sa.Text),
        sa.column("description_template", sa.Text),
        sa.column("recommendation_template", sa.Text),
        sa.column("impact_type_default", sa.String),
        sa.column("trust_state_default", sa.String),
        sa.column("severity_default", sa.String),
        sa.column("allowed_actions_json", JSONB),
        sa.column("status", sa.String),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def _rule_table() -> sa.TableClause:
    return sa.table(
        "problem_rule_versions",
        sa.column("problem_definition_id", sa.BigInteger),
        sa.column("version", sa.Integer),
        sa.column("status", sa.String),
        sa.column("evaluation_grain", sa.String),
        sa.column("lookback_days", sa.Integer),
        sa.column("condition_json", JSONB),
        sa.column("impact_formula_json", JSONB),
        sa.column("severity_formula_json", JSONB),
        sa.column("confidence_formula_json", JSONB),
        sa.column("dedup_key_template", sa.String),
        sa.column("recheck_rule_json", JSONB),
        sa.column("evidence_template_json", JSONB),
        sa.column("published_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    bind = op.get_bind()

    definition_table = _definition_table()
    definition_stmt = postgresql.insert(definition_table).values(PROBLEM_DEFINITIONS)
    definition_updates = {
        key: getattr(definition_stmt.excluded, key)
        for key in (
            "source_module",
            "category",
            "entity_type",
            "title_template",
            "description_template",
            "recommendation_template",
            "impact_type_default",
            "trust_state_default",
            "severity_default",
            "allowed_actions_json",
            "status",
        )
    }
    definition_updates["updated_at"] = sa.func.now()
    bind.execute(definition_stmt.on_conflict_do_update(index_elements=["problem_code"], set_=definition_updates))

    definitions_by_code = {
        row.problem_code: row.id
        for row in bind.execute(
            sa.select(definition_table.c.id, definition_table.c.problem_code).where(definition_table.c.problem_code.in_(PROBLEM_CODES))
        )
    }

    rule_rows = [
        {key: value for key, value in rule.items() if key != "problem_code"}
        | {"problem_definition_id": definitions_by_code[rule["problem_code"]]}
        for rule in PROBLEM_RULES
    ]
    rule_table = _rule_table()
    rule_stmt = postgresql.insert(rule_table).values(rule_rows)
    rule_updates = {
        key: getattr(rule_stmt.excluded, key)
        for key in (
            "status",
            "evaluation_grain",
            "lookback_days",
            "condition_json",
            "impact_formula_json",
            "severity_formula_json",
            "confidence_formula_json",
            "dedup_key_template",
            "recheck_rule_json",
            "evidence_template_json",
            "published_at",
        )
    }
    rule_updates["updated_at"] = sa.func.now()
    bind.execute(
        rule_stmt.on_conflict_do_update(
            index_elements=["problem_definition_id", "version"],
            set_=rule_updates,
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    definition_table = _definition_table()
    rule_table = _rule_table()
    problem_instances = sa.table(
        "problem_instances",
        sa.column("id", sa.BigInteger),
        sa.column("problem_code", sa.String),
    )
    history = sa.table(
        "problem_instance_history",
        sa.column("problem_instance_id", sa.BigInteger),
    )

    instance_ids = sa.select(problem_instances.c.id).where(problem_instances.c.problem_code.in_(PROBLEM_CODES))
    bind.execute(history.delete().where(history.c.problem_instance_id.in_(instance_ids)))
    bind.execute(problem_instances.delete().where(problem_instances.c.problem_code.in_(PROBLEM_CODES)))

    definition_ids = sa.select(definition_table.c.id).where(definition_table.c.problem_code.in_(PROBLEM_CODES))
    bind.execute(rule_table.delete().where(rule_table.c.problem_definition_id.in_(definition_ids)))
    bind.execute(definition_table.delete().where(definition_table.c.problem_code.in_(PROBLEM_CODES)))
