"""Mark system problem seeds and repair live seller copy.

Revision ID: 20260710_000064
Revises: 20260707_000063
Create Date: 2026-07-10
"""

from __future__ import annotations

import json
import re
from typing import Any

from alembic import op
import sqlalchemy as sa


revision = "20260710_000064"
down_revision = "20260707_000063"
branch_labels = None
depends_on = None


PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
OPEN_INSTANCE_STATUSES = ("new", "acknowledged", "in_progress", "postponed", "blocked", "reopened")


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


RULE_COPY: dict[str, dict[str, Any]] = {
    "missing_cost_blocks_profit": {
        "old_recheck": "Re-run after cost mapping/upload or when the product no longer has revenue in the window.",
        "old_formula": "cost_price is missing AND revenue_30d > 0",
        "old_evidence_recheck": "Upload/map cost or re-run after revenue changes.",
        "new_recheck": "Запустите повторную проверку после загрузки или сопоставления себестоимости либо когда в периоде больше нет выручки.",
        "new_formula": "Себестоимость отсутствует, а выручка за 30 дней больше 0.",
        "new_evidence_recheck": "Загрузите или сопоставьте себестоимость, затем перепроверьте товар после обновления выручки.",
        "old_trust_notes": ["Negative profit is intentionally not evaluated while cost data is missing."],
        "new_trust_notes": ["Платформа специально не считает отрицательную прибыль, пока не хватает себестоимости."],
    },
    "negative_unit_profit": {
        "old_recheck": "Re-run after price, cost, ads, promo, logistics, or margin data changes.",
        "old_formula": "cost_price exists AND (unit_profit < 0 OR margin_pct < 10)",
        "old_evidence_recheck": "Re-run after price, cost, ads, promo, logistics, or margin changes.",
        "new_recheck": "Запустите повторную проверку после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
        "new_formula": "Себестоимость заполнена, и прибыль на единицу ниже 0 или маржа ниже 10%.",
        "new_evidence_recheck": "Перепроверьте после изменения цены, себестоимости, рекламы, промо, логистики или маржи.",
        "old_trust_notes": ["This rule is blocked when cost_price is missing; missing_cost_blocks_profit should trigger instead."],
        "new_trust_notes": ["Если себестоимость отсутствует, это правило блокируется и вместо него показывается проблема с недостающей себестоимостью."],
    },
    "overstock_slow_moving": {
        "old_recheck": "Re-run after stock, sales velocity, or cost data changes.",
        "old_formula": "stock_qty > 50 AND days_of_stock > 60 AND avg_daily_sales_14d < 2; blocked_cash = max(stock_qty - 50, 0) * cost_price",
        "old_evidence_recheck": "Re-run after stock, sales velocity, or cost updates.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, скорости продаж или себестоимости.",
        "new_formula": "Остаток выше 50 штук, запаса больше чем на 60 дней, а средние продажи за 14 дней ниже 2 шт./день. Замороженные деньги считаются по лишнему остатку и себестоимости.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, скорости продаж или себестоимости.",
    },
    "low_stock_risk": {
        "old_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "old_formula": "days_of_stock < 7 AND avg_daily_sales_7d > 1; lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)",
        "old_evidence_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
        "new_formula": "Запаса меньше чем на 7 дней, а средние продажи за 7 дней выше 1 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
    },
    "ads_spend_without_profit": {
        "old_recheck": "Re-run after ads spend, bid, price, or profit data changes.",
        "old_formula": "ad_spend_7d > 500 AND unit_profit_after_ads < 0; probable_loss = abs(unit_profit_after_ads) * units_sold_7d",
        "old_evidence_recheck": "Re-run after ads spend, bid, price, or profit changes.",
        "new_recheck": "Запустите повторную проверку после изменения рекламных расходов, ставок, цены или прибыли.",
        "new_formula": "Расход на рекламу за 7 дней выше 500, а прибыль на единицу после рекламы ниже 0. Вероятный убыток считается по модулю прибыли после рекламы и продажам за 7 дней.",
        "new_evidence_recheck": "Перепроверьте после изменения рекламных расходов, ставок, цены или прибыли.",
    },
    "promo_not_profitable": {
        "old_recheck": "Re-run after promo spend, price, cost, or margin data changes.",
        "old_formula": "cost_price exists AND promo_spend_30d > 0 AND (unit_profit < 0 OR margin_pct < 10)",
        "old_evidence_recheck": "Re-run after promo spend, price, cost, or margin changes.",
        "new_recheck": "Запустите повторную проверку после изменения промо, цены, себестоимости или маржи.",
        "new_formula": "Себестоимость заполнена, есть расходы на промо, и прибыль на единицу ниже 0 или маржа ниже 10%.",
        "new_evidence_recheck": "Перепроверьте после изменения промо, цены, себестоимости или маржи.",
        "old_trust_notes": ["Promo recommendations are bounded by price-safety unit economics."],
        "new_trust_notes": ["Рекомендации по промо ограничены проверкой безопасной маржи и экономики единицы товара."],
    },
    "price_below_safe_margin": {
        "old_recheck": "Re-run after price, cost, fee, or margin data changes.",
        "old_formula": "cost_price exists AND price_after_discount > 0 AND margin_pct < 10",
        "old_evidence_recheck": "Re-run after price, cost, fee, or margin changes.",
        "new_recheck": "Запустите повторную проверку после изменения цены, себестоимости, комиссий или маржи.",
        "new_formula": "Себестоимость заполнена, эффективная цена выше 0, а маржа ниже 10%.",
        "new_evidence_recheck": "Перепроверьте после изменения цены, себестоимости, комиссий или маржи.",
        "old_trust_notes": ["Target price is calculated from cost plus commission, logistics, acquiring, and storage."],
        "new_trust_notes": ["Целевая цена считается из себестоимости, комиссии, логистики, эквайринга и хранения."],
    },
    "dead_stock": {
        "old_recheck": "Re-run after stock, sales, or cost data changes.",
        "old_formula": "stock_qty > 0 AND sales_30d = 0 AND days_of_stock > 90; blocked_cash = stock_qty * cost_price",
        "old_evidence_recheck": "Re-run after stock, sales, or cost changes.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, продаж или себестоимости.",
        "new_formula": "Остаток больше 0, продаж за 30 дней нет, а запас больше чем на 90 дней. Замороженные деньги считаются как остаток, умноженный на себестоимость.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, продаж или себестоимости.",
    },
    "fast_stock_depletion": {
        "old_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "old_formula": "days_of_stock < 3 AND avg_daily_sales_7d > 2; lost_sales_risk = avg_daily_revenue_7d * max(7 - days_of_stock, 0)",
        "old_evidence_recheck": "Re-run after stock, supply, or sales velocity updates.",
        "new_recheck": "Запустите повторную проверку после обновления остатков, поставки или скорости продаж.",
        "new_formula": "Запаса меньше чем на 3 дня, а средние продажи за 7 дней выше 2 шт./день. Риск потери продаж считается по недостающим дням запаса и средней выручке.",
        "new_evidence_recheck": "Перепроверьте после обновления остатков, поставки или скорости продаж.",
    },
}


DEFINITION_BY_CODE = {row["code"]: row for row in DEFINITION_COPY}


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _render(template: str, values: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = values.get(match.group(1))
        return "" if value is None else str(value)

    return PLACEHOLDER_RE.sub(replace, template).strip() or template


def _field_is_seeded(current: str | None, old_template: str, new_template: str, values: dict[str, Any]) -> bool:
    text = str(current or "").strip()
    if not text:
        return True
    return text in {
        old_template.strip(),
        new_template.strip(),
        _render(old_template, values).strip(),
        _render(new_template, values).strip(),
    }


def _render_values(row: Any) -> dict[str, Any]:
    values = {
        "account_id": row["account_id"],
        "nm_id": row["nm_id"],
        "vendor_code": row["vendor_code"],
        "problem_code": row["problem_code"],
        "rule_version": row["rule_version"],
        "severity": row["severity"],
        "impact": row["money_impact_amount"],
        "impact_amount": row["money_impact_amount"],
        "money_impact_amount": row["money_impact_amount"],
        "confidence": row["confidence"],
        "trust_state": row["trust_state"],
        "dedup_key": row["dedup_key"],
    }
    snapshot = _json_dict(row["calculation_snapshot_json"])
    metrics = snapshot.get("metrics")
    if isinstance(metrics, dict):
        for code, metric in metrics.items():
            if isinstance(metric, dict):
                values[str(code)] = metric.get("value")
    if snapshot.get("rule_version") is not None:
        values["rule_version"] = snapshot.get("rule_version")
    return values


def _looks_like_english_notes(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    notes = [str(item or "").strip() for item in value if str(item or "").strip()]
    return bool(notes) and all(
        any("a" <= char.lower() <= "z" for char in note)
        and not any("а" <= char.lower() <= "я" or char == "ё" for char in note)
        for note in notes
    )


def _repair_evidence_payload(payload: Any, problem_code: str) -> tuple[dict[str, Any], bool]:
    repaired = _json_dict(payload)
    rule = RULE_COPY.get(problem_code)
    if not repaired or rule is None:
        return repaired, False
    changed = False
    for current_key, old_key, new_key in (
        ("formula_human", "old_formula", "new_formula"),
        ("recheck_rule_human", "old_evidence_recheck", "new_evidence_recheck"),
    ):
        target = rule[new_key]
        if repaired.get(current_key) in {rule.get(old_key), target, None, ""} and repaired.get(current_key) != target:
            repaired[current_key] = target
            changed = True
    if "new_trust_notes" in rule:
        target_notes = list(rule.get("new_trust_notes") or [])
        current_notes = repaired.get("trust_notes")
        if current_notes is None or current_notes == rule.get("old_trust_notes") or current_notes == target_notes:
            if current_notes != target_notes:
                repaired["trust_notes"] = target_notes
                changed = True
    elif "trust_notes" in repaired and _looks_like_english_notes(repaired.get("trust_notes")):
        repaired.pop("trust_notes", None)
        changed = True
    return repaired, changed


def _mark_and_repair_definitions(bind: Any) -> None:
    statement = sa.text(
        """
        UPDATE problem_definitions
        SET is_system_seeded = true,
            title_template = :new_title,
            description_template = :new_description,
            recommendation_template = :new_recommendation,
            updated_at = now()
        WHERE problem_code = :code
          AND source_module = 'problem_engine'
          AND created_by_user_id IS NULL
          AND (
            is_system_seeded = true
            OR (
              title_template = :old_title
              AND description_template = :old_description
              AND recommendation_template = :old_recommendation
            )
            OR (
              title_template = :new_title
              AND description_template = :new_description
              AND recommendation_template = :new_recommendation
            )
          )
        """
    )
    for row in DEFINITION_COPY:
        bind.execute(statement, row)


def _mark_and_repair_rules(bind: Any) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT prv.id,
                   pd.problem_code,
                   prv.recheck_rule_json,
                   prv.evidence_template_json,
                   prv.is_system_seeded
            FROM problem_rule_versions AS prv
            JOIN problem_definitions AS pd ON pd.id = prv.problem_definition_id
            WHERE pd.is_system_seeded = true
              AND pd.source_module = 'problem_engine'
              AND pd.created_by_user_id IS NULL
              AND prv.created_by_user_id IS NULL
              AND prv.version = 1
            """
        )
    ).mappings()
    update_statement = sa.text(
        """
        UPDATE problem_rule_versions
        SET is_system_seeded = true,
            recheck_rule_json = CAST(:recheck_rule_json AS jsonb),
            evidence_template_json = CAST(:evidence_template_json AS jsonb),
            updated_at = now()
        WHERE id = :id
        """
    )
    for row in rows:
        rule = RULE_COPY.get(str(row["problem_code"]))
        if rule is None:
            continue
        recheck = _json_dict(row["recheck_rule_json"])
        evidence = _json_dict(row["evidence_template_json"])
        current_is_seeded = bool(row["is_system_seeded"])
        copy_matches = (
            recheck.get("human") in {rule["old_recheck"], rule["new_recheck"]}
            and evidence.get("formula_human") in {rule["old_formula"], rule["new_formula"]}
            and evidence.get("recheck_rule_human") in {rule["old_evidence_recheck"], rule["new_evidence_recheck"]}
        )
        if not current_is_seeded and not copy_matches:
            continue
        recheck["human"] = rule["new_recheck"]
        evidence["formula_human"] = rule["new_formula"]
        evidence["recheck_rule_human"] = rule["new_evidence_recheck"]
        if "new_trust_notes" in rule:
            evidence["trust_notes"] = list(rule["new_trust_notes"])
        elif "trust_notes" in evidence and _looks_like_english_notes(evidence.get("trust_notes")):
            evidence.pop("trust_notes", None)
        bind.execute(
            update_statement,
            {
                "id": row["id"],
                "recheck_rule_json": _json_dumps(recheck),
                "evidence_template_json": _json_dumps(evidence),
            },
        )


def _repair_instances(bind: Any) -> None:
    rows = bind.execute(
        sa.text(
            """
            SELECT pi.id,
                   pi.account_id,
                   pi.problem_code,
                   pi.nm_id,
                   pi.vendor_code,
                   pi.dedup_key,
                   pi.title,
                   pi.explanation,
                   pi.recommendation,
                   pi.severity,
                   pi.money_impact_amount,
                   pi.trust_state,
                   pi.confidence,
                   pi.evidence_ledger_json,
                   pi.calculation_snapshot_json,
                   prv.version AS rule_version
            FROM problem_instances AS pi
            JOIN problem_definitions AS pd ON pd.id = pi.problem_definition_id
            JOIN problem_rule_versions AS prv ON prv.id = pi.rule_version_id
            WHERE pd.is_system_seeded = true
              AND prv.is_system_seeded = true
              AND pi.source_module = 'problem_engine'
              AND pi.status IN :open_statuses
            """
        ).bindparams(sa.bindparam("open_statuses", expanding=True)),
        {"open_statuses": OPEN_INSTANCE_STATUSES},
    ).mappings()
    update_statement = sa.text(
        """
        UPDATE problem_instances
        SET title = :title,
            explanation = :explanation,
            recommendation = :recommendation,
            evidence_ledger_json = CAST(:evidence_ledger_json AS jsonb),
            updated_at = now()
        WHERE id = :id
        """
    )
    for row in rows:
        copy = DEFINITION_BY_CODE.get(str(row["problem_code"]))
        if copy is None:
            continue
        values = _render_values(row)
        title = str(row["title"] or "")
        explanation = str(row["explanation"] or "")
        recommendation = str(row["recommendation"] or "")
        changed = False
        if _field_is_seeded(title, copy["old_title"], copy["new_title"], values):
            title = _render(copy["new_title"], values)[:255]
            changed = changed or title != row["title"]
        if _field_is_seeded(explanation, copy["old_description"], copy["new_description"], values):
            explanation = _render(copy["new_description"], values)
            changed = changed or explanation != row["explanation"]
        if _field_is_seeded(recommendation, copy["old_recommendation"], copy["new_recommendation"], values):
            recommendation = _render(copy["new_recommendation"], values)
            changed = changed or recommendation != row["recommendation"]
        ledger, ledger_changed = _repair_evidence_payload(row["evidence_ledger_json"], str(row["problem_code"]))
        if not changed and not ledger_changed:
            continue
        bind.execute(
            update_statement,
            {
                "id": row["id"],
                "title": title,
                "explanation": explanation,
                "recommendation": recommendation,
                "evidence_ledger_json": _json_dumps(ledger),
            },
        )


def upgrade() -> None:
    op.add_column(
        "problem_definitions",
        sa.Column("is_system_seeded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_problem_definitions_system_seeded", "problem_definitions", ["is_system_seeded"])
    op.add_column(
        "problem_rule_versions",
        sa.Column("is_system_seeded", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.create_index("ix_problem_rule_versions_system_seeded", "problem_rule_versions", ["is_system_seeded"])

    bind = op.get_bind()
    _mark_and_repair_definitions(bind)
    _mark_and_repair_rules(bind)
    _repair_instances(bind)


def downgrade() -> None:
    op.drop_index("ix_problem_rule_versions_system_seeded", table_name="problem_rule_versions")
    op.drop_column("problem_rule_versions", "is_system_seeded")
    op.drop_index("ix_problem_definitions_system_seeded", table_name="problem_definitions")
    op.drop_column("problem_definitions", "is_system_seeded")
