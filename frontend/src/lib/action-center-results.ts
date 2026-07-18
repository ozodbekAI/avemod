// @ts-nocheck
import {
  actionCenterItemToResultsSearch,
  type ActionCenterItem,
} from "@/lib/action-center-contract";
import type { PortalResultEventsPage } from "@/lib/portal";
import type {
  JsonRecord,
  ProblemResultEvent,
  ProblemStatusHistoryItem,
} from "@/lib/problem-contracts";
import {
  PROBLEM_RESULT_CORRELATION_DISCLAIMER,
  problemResultHasAfterData,
  problemResultSummaryFromPage,
  problemResultTimelineMessageFromEvent,
} from "@/lib/problem-results";
import { formatMoney, formatNumber } from "@/lib/format";
import {
  asJsonRecord,
  hasRecordKeys,
  moneyValue,
} from "@/lib/action-center-utils";

export type ProblemRowResultStatus =
  | "pending_data"
  | "improved"
  | "worse"
  | "neutral"
  | "not_enough_data";

export const ROW_RESULT_STATUS_CLASS: Record<ProblemRowResultStatus, string> = {
  pending_data: "border-muted-foreground/30 bg-muted/30 text-muted-foreground",
  improved: "border-success/35 bg-success/10 text-success",
  worse: "border-destructive/35 bg-destructive/10 text-destructive",
  neutral: "border-muted-foreground/30 bg-muted/30 text-muted-foreground",
  not_enough_data:
    "border-amber-500/45 bg-amber-500/10 text-amber-700 dark:text-amber-300",
};

export type ResultMetricRow = {
  key: string;
  label: string;
  before: number;
  after: number;
  delta: number;
  direction?: string;
};

const RESULT_METRIC_LABELS: Record<string, string> = {
  revenue: "Выручка",
  profit: "Прибыль",
  orders: "Заказы",
  margin: "Маржа",
  margin_pct: "Маржа",
  ad_spend: "Реклама",
  unit_profit_after_ads: "Прибыль после рекламы",
  roas: "ROAS",
  drr: "DRR",
  returns: "Возвраты",
  stock_days_left: "Запас в днях",
  days_of_stock: "Дней остатка",
  sales_velocity: "Скорость продаж",
  surplus_stock: "Излишек остатка",
  unit_profit: "Прибыль на единицу",
  stockout_days: "Дни без остатка",
  quality_score: "Качество карточки",
  open_issue_count: "Открытые проблемы",
};

export function formatResultDate(value: unknown): string {
  if (!value) return "—";
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function resultSummaryFromAction(
  action: ActionCenterItem,
  resultPage?: PortalResultEventsPage | null,
): JsonRecord {
  const payloadSummary =
    action.result_summary && typeof action.result_summary === "object"
      ? (action.result_summary as JsonRecord)
      : {};
  const canonical = resultPage
    ? problemResultSummaryFromPage(resultPage)
    : null;
  if (canonical && canonical.events.length > 0) {
    return {
      ...payloadSummary,
      result_status: canonical.status,
      before_snapshot: canonical.before_snapshot,
      current_snapshot: canonical.current_snapshot,
      after_snapshot: canonical.after_snapshot,
      comparison: canonical.comparison,
      metrics: canonical.metrics,
      finance_windows: canonical.finance_windows,
      status_history: canonical.status_history,
      calculation_note:
        canonical.calculation_note || PROBLEM_RESULT_CORRELATION_DISCLAIMER,
      disclaimer: PROBLEM_RESULT_CORRELATION_DISCLAIMER,
      confidence: canonical.confidence,
      result_events: canonical.events,
    };
  }
  const pageSummary = asJsonRecord(resultPage?.summary);
  const financeWindows =
    resultPage?.finance_windows ??
    pageSummary?.windows ??
    payloadSummary.finance_windows ??
    {};
  return {
    ...payloadSummary,
    before_snapshot:
      pageSummary.before_snapshot ?? payloadSummary.before_snapshot ?? {},
    current_snapshot:
      pageSummary.after_snapshot ??
      payloadSummary.current_snapshot ??
      payloadSummary.after_snapshot ??
      {},
    comparison: pageSummary.comparison ?? payloadSummary.comparison,
    metrics: pageSummary.metrics ?? payloadSummary.metrics ?? {},
    finance_windows: financeWindows,
    status_history: payloadSummary.status_history ?? [],
    calculation_note:
      pageSummary.calculation_note ??
      payloadSummary.calculation_note ??
      PROBLEM_RESULT_CORRELATION_DISCLAIMER,
    disclaimer: PROBLEM_RESULT_CORRELATION_DISCLAIMER,
  };
}

export function resultMetricRows(summary: JsonRecord): ResultMetricRow[] {
  if (!resultSummaryHasAfterData(summary)) return [];
  const windows = asJsonRecord(summary.finance_windows);
  const preferredWindow = hasRecordKeys(asJsonRecord(windows["14d"]).metrics)
    ? asJsonRecord(windows["14d"])
    : hasRecordKeys(asJsonRecord(windows["7d"]).metrics)
      ? asJsonRecord(windows["7d"])
      : null;
  const rawMetrics = hasRecordKeys(preferredWindow?.metrics)
    ? asJsonRecord(preferredWindow?.metrics)
    : hasRecordKeys(summary.metrics)
      ? asJsonRecord(summary.metrics)
      : {};
  return Object.entries(rawMetrics)
    .map(([key, value]) => {
      const metric = asJsonRecord(value);
      const before = Number(metric.before);
      const after = Number(metric.after);
      const delta = Number(metric.delta ?? after - before);
      if (!Number.isFinite(before) || !Number.isFinite(after)) return null;
      return {
        key,
        label: RESULT_METRIC_LABELS[key] ?? key.replaceAll("_", " "),
        before,
        after,
        delta: Number.isFinite(delta) ? delta : after - before,
        direction: String(metric.direction ?? ""),
      };
    })
    .filter(Boolean) as ResultMetricRow[];
}

export function resultStatusFromSummary(
  summary: JsonRecord,
): ProblemRowResultStatus {
  const hasAfterData = resultSummaryHasAfterData(summary);
  const comparison = asJsonRecord(summary.comparison);
  const rawStatus = String(
    summary.result_status ??
      summary.status ??
      summary.outcome ??
      comparison.status ??
      "",
  )
    .trim()
    .toLowerCase();
  if (
    [
      "pending_data",
      "pending",
      "waiting_data",
      "waiting_for_data",
      "awaiting_data",
    ].includes(rawStatus)
  ) {
    return "pending_data";
  }
  if (["improved", "better", "success", "positive"].includes(rawStatus)) {
    return hasAfterData ? "improved" : "pending_data";
  }
  if (["worse", "degraded", "negative", "regressed"].includes(rawStatus)) {
    return hasAfterData ? "worse" : "pending_data";
  }
  if (["neutral", "no_change", "unchanged", "same"].includes(rawStatus)) {
    return hasAfterData ? "neutral" : "pending_data";
  }
  if (
    [
      "not_enough_data",
      "no_data",
      "insufficient_data",
      "missing_data",
    ].includes(rawStatus)
  ) {
    return hasAfterData ? "not_enough_data" : "pending_data";
  }

  const rows = resultMetricRows(summary);
  if (rows.some((row) => row.direction === "improved")) return "improved";
  if (rows.some((row) => row.direction === "worse")) return "worse";
  if (rows.length > 0) return "neutral";

  return "pending_data";
}

export function resultHasMeasuredComparison(summary: JsonRecord): boolean {
  if (!resultSummaryHasAfterData(summary)) return false;
  if (resultMetricRows(summary).length > 0) return true;
  const comparison = asJsonRecord(summary.comparison);
  return hasRecordKeys(comparison.metrics);
}

export function resultSummaryHasAfterData(summary: JsonRecord): boolean {
  return problemResultHasAfterData(summary);
}

export function resultIsCorrelationOnly(summary: JsonRecord): boolean {
  if (!resultHasMeasuredComparison(summary)) return false;
  const text = `${summary.calculation_note ?? ""} ${summary.disclaimer ?? ""}`
    .trim()
    .toLowerCase();
  return (
    text.includes("корреля") ||
    text.includes("correlation") ||
    text.includes("caus")
  );
}

export function problemResultTimelineLabel(value: unknown): string {
  const key = String(value ?? "")
    .trim()
    .toLowerCase();
  const labels: Record<string, string> = {
    before_snapshot: "Снимок «до»",
    action_started: "Действие начато",
    status_changed: "Статус изменён",
    action_completed: "Действие выполнено",
    card_quality_local_fix_saved: "Локальная правка сохранена",
    card_quality_wb_submit_attempted: "Отправка в WB",
    card_quality_wb_validation_waiting: "Ждём проверку WB",
    card_quality_recheck_resolved: "Проблема карточки закрыта",
    card_quality_recheck_reopened: "Проблема карточки переоткрыта",
    recheck_result: "Повторная проверка",
    after_snapshot: "Снимок «после»",
    measured_comparison: "Измеренное сравнение",
    result_evaluated: "Измеренное сравнение",
  };
  return labels[key] ?? "Событие результата";
}

export function problemResultTimelineMessage(
  event: ProblemResultEvent,
): string | null {
  return problemResultTimelineMessageFromEvent(event);
}

export function resultEventsFromPage(
  page?: PortalResultEventsPage | null,
): PortalResultEventsPage["items"] {
  if (!page) return [];
  const byKey = new Map<string, PortalResultEventsPage["items"][number]>();
  const add = (event: PortalResultEventsPage["items"][number]) => {
    const key = String(
      event.id ??
        `${event.event_type}-${event.created_at ?? ""}-${event.problem_instance_id ?? ""}`,
    );
    byKey.set(key, event);
  };
  if (Array.isArray(page.items)) page.items.forEach(add);
  if (Array.isArray(page.recent_events)) page.recent_events.forEach(add);
  return Array.from(byKey.values());
}

export function resultPageHasCanonicalData(
  page?: PortalResultEventsPage | null,
): boolean {
  if (!page) return false;
  if (resultEventsFromPage(page).length > 0) return true;
  if (
    page.summary &&
    typeof page.summary === "object" &&
    Object.keys(page.summary).length > 0
  ) {
    return true;
  }
  return Boolean(
    page.finance_windows &&
    typeof page.finance_windows === "object" &&
    Object.keys(page.finance_windows).length > 0,
  );
}

export function latestRecheckEventFromPage(
  page?: PortalResultEventsPage | null,
) {
  return resultEventsFromPage(page)
    .slice()
    .sort(
      (a, b) =>
        new Date(String(b.created_at ?? "")).getTime() -
        new Date(String(a.created_at ?? "")).getTime(),
    )
    .find((event) =>
      String(event.event_type ?? "")
        .toLowerCase()
        .includes("recheck"),
    );
}

export function metricDeltaLabel(metric: ResultMetricRow): string {
  return metric.key === "orders"
    ? formatNumber(metric.delta)
    : formatMoney(metric.delta);
}

export function metricValueLabel(
  metric: ResultMetricRow,
  value: number,
): string {
  return metric.key === "orders" ? formatNumber(value) : formatMoney(value);
}

export function expectedLossValue(
  action: ActionCenterItem,
  summary: JsonRecord,
): number | null {
  const before = asJsonRecord(summary.before_snapshot);
  const moneyAtRisk = asJsonRecord(summary.money_at_risk);
  return (
    Number(
      moneyAtRisk.before ??
        before.money_impact_amount ??
        moneyValue(action) ??
        0,
    ) || null
  );
}

export type ResultTimelineData = {
  summary: JsonRecord;
  rows: ResultMetricRow[];
  resultEvents: ProblemResultEvent[];
  history: ProblemStatusHistoryItem[];
  statusFlow: JsonRecord;
  before: JsonRecord;
  current: JsonRecord;
  after: JsonRecord;
  expectedLoss: number | null;
  hasWindows: boolean;
  hasAfterData: boolean;
  hasMeasuredComparison: boolean;
  status: ProblemRowResultStatus;
  confidence: string | null;
};

export function resultTimelineData(
  action: ActionCenterItem,
  resultPage?: PortalResultEventsPage | null,
): ResultTimelineData {
  const summary = resultSummaryFromAction(action, resultPage);
  return {
    summary,
    rows: resultMetricRows(summary),
    resultEvents: Array.isArray(summary.result_events)
      ? (summary.result_events as ProblemResultEvent[])
      : [],
    history: Array.isArray(summary.status_history)
      ? (summary.status_history as ProblemStatusHistoryItem[]).slice(-6)
      : [],
    statusFlow: asJsonRecord(summary.status_flow),
    before: asJsonRecord(summary.before_snapshot),
    current: asJsonRecord(summary.current_snapshot),
    after: asJsonRecord(summary.after_snapshot),
    expectedLoss: expectedLossValue(action, summary),
    hasWindows: Object.keys(summary.finance_windows ?? {}).length > 0,
    hasAfterData: resultSummaryHasAfterData(summary),
    hasMeasuredComparison: resultHasMeasuredComparison(summary),
    status: resultStatusFromSummary(summary),
    confidence: String(summary.confidence ?? "").trim() || null,
  };
}

export function resultsLinkSearch(action: ActionCenterItem) {
  return actionCenterItemToResultsSearch(action);
}
