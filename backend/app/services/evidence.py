from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.evidence import (
    EvidenceLedger,
    confidence_from_trust_state,
    evidence_ledger,
)


def money_kpi_evidence(
    *,
    key: str,
    value: Any,
    account_id: int | None,
    date_from: date | str | None,
    date_to: date | str | None,
    trust_state: str | None = None,
    financial_final: bool | None = None,
) -> EvidenceLedger:
    value_type = (
        "percent" if key.endswith("_percent") or key in {"margin", "roi"} else "money"
    )
    formula_map = {
        "revenue": "Сумма операционной выручки за выбранный период.",
        "revenue_final": "Финальная выручка после сверки с финансовыми строками WB.",
        "finance_confirmed_revenue": "Сумма выручки из финансовых отчетов WB за закрытый период.",
        "net_profit_after_ads": "Выручка минус себестоимость, расходы WB и реклама.",
        "net_profit_after_overhead": "Прибыль после рекламы минус распределенные расходы аккаунта.",
        "margin_percent": "Прибыль / выручка * 100.",
        "cash_on_wb": "Последний доступный снимок баланса WB.",
        "available_for_withdraw": "Доступно к выводу из последнего снимка баланса WB.",
        "stock_value": "Текущий остаток * подтвержденная или оценочная себестоимость.",
        "ad_spend": "Расход рекламы из WB и/или финансового отчета за период.",
        "unallocated_expenses": "Расходы аккаунта, которые не удалось безопасно распределить на карточки.",
    }
    source_table_map = {
        "cash_on_wb": "wb_balance_snapshots",
        "available_for_withdraw": "wb_balance_snapshots",
        "stock_value": "mart_stock_daily",
        "ad_spend": "ad_stats",
        "ads_source_spend": "ad_stats",
        "finance_confirmed_revenue": "realization_report_rows",
    }
    return evidence_ledger(
        value=value,
        value_type=value_type,  # type: ignore[arg-type]
        confidence=confidence_from_trust_state(trust_state, final=financial_final),
        impact_type="system_warning"
        if key in {"unallocated_expenses"}
        else "opportunity",
        formula_human=formula_map.get(
            key, f"KPI `{key}` рассчитан backend-агрегатором Money Summary."
        ),
        formula_code=f"money_summary.kpis.{key}",
        formula_id=f"money_summary:{key}",
        label=key,
        unit="RUB" if value_type == "money" else "%",
        source_table=source_table_map.get(key, "mart_sku_daily"),
        source_endpoint="GET /api/v1/money/summary",
        date_from=date_from,
        date_to=date_to,
        filters={"account_id": account_id} if account_id is not None else {},
        row_count=0,
        trust_notes=[
            "Evidence ledger exposes calculation lineage. Exact DB row references are attached when the source module provides them.",
        ],
        missing_data=[]
        if financial_final
        else ["financial_final=false"]
        if financial_final is False
        else [],
        recheck_rule="Refresh /money/summary after sync or data-fix changes.",
    )


def issue_evidence(
    *,
    code: str,
    title: str,
    value: Any = None,
    source_table: str | None = None,
    source_endpoint: str,
    account_id: int | None = None,
    date_from: date | str | None = None,
    date_to: date | str | None = None,
    row_count: int = 0,
    severity: str | None = None,
    next_screen_path: str | None = None,
    next_screen_label: str | None = None,
    sample_rows: list[dict[str, Any]] | None = None,
) -> EvidenceLedger:
    normalized_severity = str(severity or "").lower()
    confidence = (
        "blocked"
        if normalized_severity in {"critical", "error", "blocker"}
        else "provisional"
    )
    return evidence_ledger(
        value=value if value is not None else title,
        value_type="text" if value is None else "count",
        confidence=confidence,  # type: ignore[arg-type]
        impact_type="data_blocker" if confidence == "blocked" else "system_warning",
        formula_human=f"Проблема `{code}` создана правилом качества данных и сгруппирована по источнику.",
        formula_code=f"issue.{code}",
        formula_id=f"issue:{code}",
        label=title or code,
        source_table=source_table,
        source_endpoint=source_endpoint,
        date_from=date_from,
        date_to=date_to,
        filters={"account_id": account_id, "code": code}
        if account_id is not None
        else {"code": code},
        row_count=row_count,
        sample_rows=sample_rows,
        next_fix_action={
            "label": next_screen_label or "Открыть исправление",
            "screen_path": next_screen_path,
            "source_endpoint": source_endpoint,
            "action_type": code,
        },
        recheck_rule="Re-run sync/DQ check, then reload the endpoint.",
    )
