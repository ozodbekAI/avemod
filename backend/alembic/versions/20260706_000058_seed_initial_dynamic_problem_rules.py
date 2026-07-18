"""Seed initial Dynamic Problem Engine product rules.

Revision ID: 20260706_000058
Revises: 20260706_000057
Create Date: 2026-07-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260706_000058"
down_revision = "20260706_000057"
branch_labels = None
depends_on = None


JSONB = postgresql.JSONB(astext_type=sa.Text())


def _metric(
    metric_code: str,
    title: str,
    description: str,
    value_type: str,
    unit: str | None,
    grain: str,
    entity_type: str,
    source_module: str,
    *,
    source_tables: list[str],
    source_endpoints: list[str] | None = None,
    required_metrics: list[str] | None = None,
    formula: dict | None = None,
    trust_state: str = "provisional",
) -> dict:
    return {
        "metric_code": metric_code,
        "title": title,
        "description": description,
        "value_type": value_type,
        "unit": unit,
        "grain": grain,
        "entity_type": entity_type,
        "source_module": source_module,
        "formula_json": formula,
        "source_tables_json": source_tables,
        "source_endpoints_json": source_endpoints or [],
        "required_metrics_json": required_metrics or [],
        "trust_state": trust_state,
        "is_admin_visible": True,
        "is_deprecated": False,
    }


EXTRA_METRICS = [
    _metric("avg_daily_revenue_7d", "Average daily revenue, 7 days", "Product revenue per day over the latest seven-day window.", "money", "RUB/day", "product_period", "product", "money", source_tables=["mart_sku_daily"], source_endpoints=["GET /api/v1/marts/sku-daily"], required_metrics=["revenue_7d"], formula={"/": [{"metric": "revenue_7d"}, 7]}, trust_state="confirmed"),
    _metric("sales_7d", "Sales, 7 days", "Product sale units over the latest seven-day window.", "count", "pcs", "product_period", "product", "money", source_tables=["mart_sku_daily", "mart_stock_daily"], source_endpoints=["GET /api/v1/marts/sku-daily"], trust_state="confirmed"),
    _metric("units_sold_7d", "Units sold, 7 days", "Alias for seven-day product sold units used by ad profitability rules.", "count", "pcs", "product_period", "product", "money", source_tables=["mart_sku_daily", "mart_stock_daily"], source_endpoints=["GET /api/v1/marts/sku-daily"], required_metrics=["sales_7d"], formula={"metric": "sales_7d"}, trust_state="confirmed"),
    _metric("unit_profit_after_ads", "Unit profit after ads", "Estimated profit after ads divided by net sold units when trusted cost data exists.", "money", "RUB/unit", "product_period", "product", "money", source_tables=["mart_sku_daily"], required_metrics=["cost_price", "sales_30d", "unit_profit"], formula={"metric": "unit_profit"}, trust_state="estimated"),
]


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
    _definition("missing_cost_blocks_profit", "data_quality", "Нет себестоимости для товара {nm_id}", "За 30 дней есть выручка {revenue_30d}, но себестоимость не заполнена. Поэтому прибыль и маржа по товару пока не считаются надёжно.", "Загрузите или сопоставьте себестоимость, затем запустите повторную проверку прибыльности.", "data_blocker", "blocked", "critical", ["upload_cost", "map_sku", "create_task", "recheck", "dismiss"]),
    _definition("negative_unit_profit", "profitability", "Товар {nm_id} продаётся в минус", "Прибыль на единицу: {unit_profit}, маржа: {margin_pct}%. Минимальная безопасная маржа: 10%.", "Проверьте цену, себестоимость, рекламу, промо и логистику. Не снижайте цену без проверки безопасной маржи.", "probable_loss", "estimated", "high", ["review_price", "review_cost", "review_ads", "review_promo", "create_task", "recheck", "dismiss"]),
    _definition("overstock_slow_moving", "stock", "Пересток и медленные продажи по товару {nm_id}", "Остаток: {stock_qty}, запас в днях: {days_of_stock}, средние продажи за 14 дней: {avg_daily_sales_14d} шт./день.", "Проверьте безопасное промо, цену, комплект, рекламу или качество карточки. Скидку можно запускать только после проверки маржи.", "blocked_cash", "estimated", "medium", ["safe_promo", "review_price", "bundle", "review_ads", "review_content", "create_task", "recheck", "dismiss"]),
    _definition("low_stock_risk", "stock", "Риск низкого остатка по товару {nm_id}", "Запаса осталось на {days_of_stock} дней при средних продажах за 7 дней {avg_daily_sales_7d} шт./день.", "Запланируйте поставку или пополнение. Если поставить товар быстро нельзя, снизьте промо или рекламу, чтобы не уйти в дефицит.", "lost_sales_risk", "provisional", "medium", ["plan_supply", "reduce_promo", "reduce_ads", "create_task", "recheck", "dismiss"]),
    _definition("ads_spend_without_profit", "ads", "Реклама съедает прибыль по товару {nm_id}", "Расход на рекламу за 7 дней: {ad_spend_7d}; прибыль на единицу после рекламы: {unit_profit_after_ads}.", "Снизьте или приостановите рекламу, проверьте качество карточки, ставки и цену.", "probable_loss", "provisional", "high", ["pause_ads", "lower_ads", "check_card_quality", "review_bids", "review_price", "create_task", "recheck", "dismiss"]),
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
        "missing_cost_blocks_profit",
        30,
        {"and": [{"missing": ["cost_price"]}, {">": [{"metric": "revenue_30d"}, 0]}]},
        {"metric": "revenue_30d"},
        {"case": [{"if": {">": [{"metric": "revenue_30d"}, 50000]}, "then": "critical"}, {"else": "high"}]},
        _constant("blocked"),
        {
            "human": "Запустите повторную проверку после загрузки или сопоставления себестоимости либо когда в периоде больше нет выручки.",
            "resolved_when": {"or": [{"not": {"missing": ["cost_price"]}}, {"<=": [{"metric": "revenue_30d"}, 0]}]},
            "missing_metrics_policy": "condition_only",
            "create_data_blocker_on_missing": False,
            "initial_status": "blocked",
        },
        {"formula_human": "Себестоимость отсутствует, а выручка за 30 дней больше 0.", "formula_code": "missing_cost_blocks_profit.v1", "recheck_rule_human": "Загрузите или сопоставьте себестоимость, затем перепроверьте товар после обновления выручки.", "impact_type": "data_blocker", "confidence": "blocked", "money_currency": "RUB", "trust_notes": ["Платформа специально не считает отрицательную прибыль, пока не хватает себестоимости."]},
    ),
    _rule(
        "negative_unit_profit",
        30,
        {"and": [{"not": {"missing": ["cost_price"]}}, {"or": [{"<": [{"metric": "unit_profit"}, 0]}, {"<": [{"metric": "margin_pct"}, 10]}]}]},
        {"case": [{"if": {"<": [{"metric": "unit_profit"}, 0]}, "then": {"abs": {"*": [{"metric": "unit_profit"}, {"metric": "sales_30d"}]}}}, {"else": 0}]},
        {"case": [{"if": {"<": [{"metric": "unit_profit"}, -100]}, "then": "critical"}, {"if": {"<": [{"metric": "margin_pct"}, 0]}, "then": "high"}, {"else": "medium"}]},
        _constant("estimated"),
        {"human": "Запустите повторную проверку после изменения цены, себестоимости, рекламы, промо, логистики или маржи.", "resolved_when": {"or": [{"missing": ["cost_price"]}, {"and": [{">=": [{"metric": "unit_profit"}, 0]}, {">=": [{"metric": "margin_pct"}, 10]}]}]}},
        {"formula_human": "Себестоимость заполнена, и прибыль на единицу ниже 0 или маржа ниже 10%.", "formula_code": "negative_unit_profit.v1", "recheck_rule_human": "Перепроверьте после изменения цены, себестоимости, рекламы, промо, логистики или маржи.", "impact_type": "probable_loss", "confidence": "estimated", "money_currency": "RUB", "trust_notes": ["Если себестоимость отсутствует, это правило блокируется и вместо него показывается проблема с недостающей себестоимостью."]},
    ),
    _rule(
        "overstock_slow_moving",
        30,
        {"and": [{">": [{"metric": "stock_qty"}, 50]}, {">": [{"metric": "days_of_stock"}, 60]}, {"<": [{"metric": "avg_daily_sales_14d"}, 2]}]},
        {"*": [{"max": [0, {"-": [{"metric": "stock_qty"}, 50]}]}, {"metric": "cost_price"}]},
        {"case": [{"if": {">": [{"metric": "days_of_stock"}, 120]}, "then": "high"}, {"else": "medium"}]},
        _constant("estimated"),
        {"human": "Запустите повторную проверку после обновления остатков, скорости продаж или себестоимости.", "resolved_when": {"or": [{"<=": [{"metric": "stock_qty"}, 50]}, {"<=": [{"metric": "days_of_stock"}, 60]}, {">=": [{"metric": "avg_daily_sales_14d"}, 2]}]}},
        {"formula_human": "Остаток выше 50 штук, запаса больше чем на 60 дней, а средние продажи за 14 дней ниже 2 шт./день. Замороженные деньги считаются по лишнему остатку и себестоимости.", "formula_code": "overstock_slow_moving.v1", "recheck_rule_human": "Перепроверьте после обновления остатков, скорости продаж или себестоимости.", "impact_type": "blocked_cash", "confidence": "estimated", "money_currency": "RUB"},
    ),
    _rule(
        "low_stock_risk",
        7,
        {"and": [{"<": [{"metric": "days_of_stock"}, 7]}, {">": [{"metric": "avg_daily_sales_7d"}, 1]}]},
        {"*": [{"metric": "avg_daily_revenue_7d"}, {"max": [0, {"-": [7, {"metric": "days_of_stock"}]}]}]},
        {"case": [{"if": {"<": [{"metric": "days_of_stock"}, 3]}, "then": "high"}, {"else": "medium"}]},
        _constant("provisional"),
        {"human": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.", "resolved_when": {"or": [{">=": [{"metric": "days_of_stock"}, 7]}, {"<=": [{"metric": "avg_daily_sales_7d"}, 1]}]}},
        {"formula_human": "Запаса меньше чем на 7 дней, а средние продажи за 7 дней выше 1 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.", "formula_code": "low_stock_risk.v1", "recheck_rule_human": "Перепроверьте после обновления остатков, поставки или скорости продаж.", "impact_type": "lost_sales_risk", "confidence": "provisional", "money_currency": "RUB"},
    ),
    _rule(
        "ads_spend_without_profit",
        7,
        {"and": [{">": [{"metric": "ad_spend_7d"}, 500]}, {"<": [{"metric": "unit_profit_after_ads"}, 0]}]},
        {"*": [{"abs": {"metric": "unit_profit_after_ads"}}, {"metric": "units_sold_7d"}]},
        {"case": [{"if": {">": [{"metric": "ad_spend_7d"}, 5000]}, "then": "high"}, {"else": "medium"}]},
        _constant("estimated"),
        {"human": "Запустите повторную проверку после изменения рекламных расходов, ставок, цены или прибыли.", "resolved_when": {"or": [{"<=": [{"metric": "ad_spend_7d"}, 500]}, {">=": [{"metric": "unit_profit_after_ads"}, 0]}]}},
        {"formula_human": "Расход на рекламу за 7 дней выше 500, а прибыль на единицу после рекламы ниже 0. Вероятный убыток считается по модулю прибыли после рекламы и продажам за 7 дней.", "formula_code": "ads_spend_without_profit.v1", "recheck_rule_human": "Перепроверьте после изменения рекламных расходов, ставок, цены или прибыли.", "impact_type": "probable_loss", "confidence": "estimated", "money_currency": "RUB"},
    ),
]


PROBLEM_CODES = [definition["problem_code"] for definition in PROBLEM_DEFINITIONS]
EXTRA_METRIC_CODES = [metric["metric_code"] for metric in EXTRA_METRICS]


def _metric_table() -> sa.TableClause:
    return sa.table(
        "metric_catalog",
        sa.column("metric_code", sa.String),
        sa.column("title", sa.String),
        sa.column("description", sa.Text),
        sa.column("value_type", sa.String),
        sa.column("unit", sa.String),
        sa.column("grain", sa.String),
        sa.column("entity_type", sa.String),
        sa.column("source_module", sa.String),
        sa.column("formula_json", JSONB),
        sa.column("source_tables_json", JSONB),
        sa.column("source_endpoints_json", JSONB),
        sa.column("required_metrics_json", JSONB),
        sa.column("trust_state", sa.String),
        sa.column("is_admin_visible", sa.Boolean),
        sa.column("is_deprecated", sa.Boolean),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )


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

    metric_table = _metric_table()
    metric_stmt = postgresql.insert(metric_table).values(EXTRA_METRICS)
    metric_updates = {
        key: getattr(metric_stmt.excluded, key)
        for key in (
            "title",
            "description",
            "value_type",
            "unit",
            "grain",
            "entity_type",
            "source_module",
            "formula_json",
            "source_tables_json",
            "source_endpoints_json",
            "required_metrics_json",
            "trust_state",
            "is_admin_visible",
            "is_deprecated",
        )
    }
    metric_updates["updated_at"] = sa.func.now()
    bind.execute(metric_stmt.on_conflict_do_update(index_elements=["metric_code"], set_=metric_updates))

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
    rule_table = _rule_table()
    rule_rows = [
        {
            key: value
            for key, value in rule.items()
            if key != "problem_code"
        }
        | {"problem_definition_id": definitions_by_code[rule["problem_code"]]}
        for rule in PROBLEM_RULES
    ]
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
    metric_table = _metric_table()
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
    bind.execute(metric_table.delete().where(metric_table.c.metric_code.in_(EXTRA_METRIC_CODES)))
