// @ts-nocheck
// Curated per-problem metric templates for /results page.
// No fixtures — only reads fields backend already returns.

import { formatMoney, formatPercent, formatNumber } from "@/lib/format";

type Formatter = (v: unknown) => string;
type MetricDef = {
  label: string;
  keys: string[]; // fallback keys within before/after snapshot
  format?: Formatter;
};

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}

function pick(obj: unknown, keys: string[]): unknown {
  if (!isRecord(obj)) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v != null && v !== "") return v;
  }
  return undefined;
}

const fmtMoney: Formatter = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? formatMoney(n) : "—";
};
const fmtPct: Formatter = (v) => {
  const n = Number(v);
  if (!Number.isFinite(n)) return "—";
  return formatPercent(Math.abs(n) <= 1 ? n * 100 : n, 1);
};
const fmtNum: Formatter = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? formatNumber(n) : "—";
};
const fmtText: Formatter = (v) => (v == null || v === "" ? "—" : String(v));
const fmtDate: Formatter = (v) => {
  if (!v) return "—";
  const d = new Date(String(v));
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
};

const TEMPLATES: Record<string, MetricDef[]> = {
  low_stock_risk: [
    { label: "Остаток", keys: ["stock", "stock_qty", "quantity", "on_hand"], format: fmtNum },
    { label: "Дней запаса", keys: ["days_of_stock", "days_left", "days_supply"], format: fmtNum },
    { label: "Средние продажи", keys: ["avg_sales", "avg_daily_sales", "sales_per_day"], format: fmtNum },
    { label: "Риск дней без товара", keys: ["stockout_days_risk", "risk_days"], format: fmtNum },
    { label: "Заказы", keys: ["orders", "orders_count"], format: fmtNum },
    { label: "Выручка", keys: ["revenue", "revenue_amount"], format: fmtMoney },
  ],
  overstock_slow_moving: [
    { label: "Остаток", keys: ["stock", "stock_qty", "quantity"], format: fmtNum },
    { label: "Дней запаса", keys: ["days_of_stock", "days_left"], format: fmtNum },
    { label: "Скорость продаж", keys: ["sell_through", "sales_velocity", "avg_daily_sales"], format: fmtNum },
    { label: "Излишек остатка", keys: ["excess_stock", "overstock_qty"], format: fmtNum },
    { label: "Замороженные деньги", keys: ["frozen_money", "frozen_amount", "capital_locked"], format: fmtMoney },
  ],
  negative_unit_profit: [
    { label: "Прибыль на единицу", keys: ["unit_profit", "profit_per_unit"], format: fmtMoney },
    { label: "Маржа", keys: ["margin", "margin_pct"], format: fmtPct },
    { label: "Цена", keys: ["price", "current_price"], format: fmtMoney },
    { label: "Себестоимость", keys: ["cost", "cogs", "unit_cost"], format: fmtMoney },
    { label: "Реклама на единицу", keys: ["ads_per_unit", "ad_cost_per_unit"], format: fmtMoney },
    { label: "Логистика", keys: ["logistics", "logistics_cost"], format: fmtMoney },
    { label: "Комиссия", keys: ["commission", "commission_amount"], format: fmtMoney },
  ],
  missing_cost_blocks_profit: [
    { label: "Себестоимость", keys: ["cost", "cogs", "unit_cost"], format: fmtMoney },
    { label: "Расчёт прибыли", keys: ["profit_computable", "profit_status"], format: fmtText },
    { label: "Статус блокера", keys: ["blocker_status", "status"], format: fmtText },
    { label: "Затронутые строки", keys: ["affected_rows", "rows_count"], format: fmtNum },
  ],
  ads_spend_without_profit: [
    { label: "Расход на рекламу", keys: ["ads_spend", "ad_spend", "ads_cost"], format: fmtMoney },
    { label: "Заказы от рекламы", keys: ["ads_orders", "attributed_orders"], format: fmtNum },
    { label: "Выручка от рекламы", keys: ["ads_revenue", "attributed_revenue"], format: fmtMoney },
    { label: "Прибыль после рекламы", keys: ["profit_after_ads", "net_profit"], format: fmtMoney },
    { label: "ДРР", keys: ["drr", "acos"], format: fmtPct },
    { label: "ROAS", keys: ["roas"], format: fmtNum },
  ],
  promo_not_profitable: [
    { label: "Цена промо", keys: ["promo_price", "price"], format: fmtMoney },
    { label: "Маржа в промо", keys: ["promo_margin", "margin"], format: fmtPct },
    { label: "Продажи", keys: ["sales", "orders"], format: fmtNum },
    { label: "Прибыль", keys: ["profit"], format: fmtMoney },
    { label: "Статус промо", keys: ["promo_status", "status"], format: fmtText },
  ],
  price_below_safe_margin: [
    { label: "Текущая цена", keys: ["price", "current_price"], format: fmtMoney },
    { label: "Минимальная безопасная цена", keys: ["safe_price", "min_safe_price"], format: fmtMoney },
    { label: "Маржа", keys: ["margin", "margin_pct"], format: fmtPct },
    { label: "Целевая маржа", keys: ["target_margin", "target_margin_pct"], format: fmtPct },
  ],
  card_quality: [
    { label: "Оценка карточки", keys: ["score", "card_score"], format: fmtNum },
    { label: "Открытые ошибки", keys: ["open_issues", "issues_open"], format: fmtNum },
    { label: "Исправленные ошибки", keys: ["fixed_issues", "issues_fixed"], format: fmtNum },
    { label: "Статус отправки в WB", keys: ["wb_submit_status", "submit_status"], format: fmtText },
    { label: "Последняя проверка", keys: ["last_check_at", "checked_at"], format: fmtDate },
  ],
};

// Aliases (problem_code prefix → template key)
const ALIASES: Array<[RegExp, string]> = [
  [/checker|card_quality|content|photo|title|description|characteristics/i, "card_quality"],
];

export function resolveMetricTemplate(problemCode?: string | null, sourceModule?: string | null): MetricDef[] | null {
  const code = String(problemCode ?? "").toLowerCase();
  const mod = String(sourceModule ?? "").toLowerCase();
  if (code && TEMPLATES[code]) return TEMPLATES[code];
  for (const [re, key] of ALIASES) {
    if (re.test(code) || re.test(mod)) return TEMPLATES[key] ?? null;
  }
  if (mod === "checker" || mod === "card_quality") return TEMPLATES.card_quality;
  return null;
}

export type MetricRow = {
  label: string;
  before: string;
  after: string;
  rawBefore: unknown;
  rawAfter: unknown;
  state: "improved" | "worse" | "neutral" | "missing";
  deltaLabel: string | null;
};

function numericDelta(before: unknown, after: unknown): number | null {
  const a = Number(before);
  const b = Number(after);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return b - a;
}

function stateFor(label: string, before: unknown, after: unknown): MetricRow["state"] {
  if (before == null && after == null) return "missing";
  const d = numericDelta(before, after);
  if (d == null) {
    if (String(before) === String(after)) return "neutral";
    return "neutral";
  }
  if (d === 0) return "neutral";
  // Direction heuristics: cost/losses/errors/risk lower is better; profit/revenue/margin/score higher is better.
  const lowerBetter =
    /себестоимость|расход|излишек|заморожен|риск|дрр|acos|логистика|комиссия|ошибк/i.test(label);
  const better = lowerBetter ? d < 0 : d > 0;
  return better ? "improved" : "worse";
}

export function buildMetricRows(
  template: MetricDef[],
  before: unknown,
  after: unknown,
): MetricRow[] {
  return template.map((m) => {
    const rawBefore = pick(before, m.keys);
    const rawAfter = pick(after, m.keys);
    const fmt = m.format ?? fmtText;
    const bStr = rawBefore == null ? "—" : fmt(rawBefore);
    const aStr = rawAfter == null ? "—" : fmt(rawAfter);
    const state = rawBefore == null && rawAfter == null
      ? "missing"
      : stateFor(m.label, rawBefore, rawAfter);
    let deltaLabel: string | null = null;
    const d = numericDelta(rawBefore, rawAfter);
    if (d != null && d !== 0) {
      const abs = Math.abs(d);
      const sign = d > 0 ? "+" : "−";
      if (m.format === fmtMoney) deltaLabel = `${sign}${formatMoney(abs)}`;
      else if (m.format === fmtPct) deltaLabel = `${sign}${formatPercent(Math.abs(abs) <= 1 ? abs * 100 : abs, 1)}`;
      else deltaLabel = `${sign}${formatNumber(abs)}`;
    }
    return { label: m.label, before: bStr, after: aStr, rawBefore, rawAfter, state, deltaLabel };
  });
}

// -------- Detection helpers --------

const DATA_BLOCKER_CODES = /cost|data|sku|expense|finance_without_sale|sale_without_finance/i;
const DATA_BLOCKER_MODULES = /data_quality|data_fix/i;

export function isDataBlockerResult(event: unknown): boolean {
  if (!isRecord(event)) return false;
  const impact = String(event.impact_type ?? "").toLowerCase();
  if (impact === "data_blocker") return true;
  const trust = String(event.trust_state ?? "").toLowerCase();
  if (trust === "blocked") return true;
  const code = String(event.problem_code ?? "");
  const mod = String(event.source_module ?? "");
  if (DATA_BLOCKER_CODES.test(code)) return true;
  if (DATA_BLOCKER_MODULES.test(mod)) return true;
  return false;
}

const CHECKER_CODES = /checker|card_quality|content|photo|title|description|characteristics/i;

export function isCheckerResult(event: unknown): boolean {
  if (!isRecord(event)) return false;
  const mod = String(event.source_module ?? "").toLowerCase();
  if (mod === "checker" || mod === "card_quality") return true;
  const code = String(event.problem_code ?? "");
  return CHECKER_CODES.test(code);
}

export type ContextLink = {
  key: "action_center" | "product360" | "product_results" | "data_fix" | "checker";
  label: string;
  to: string;
  params?: Record<string, string>;
  search?: Record<string, string | undefined>;
  disabled?: boolean;
  disabledReason?: string;
};

export function buildContextLinks(event: unknown): ContextLink[] {
  if (!isRecord(event)) return [];
  const productIdentity = isRecord(event.product_identity) ? event.product_identity : {};
  const nmIdRaw = productIdentity.nm_id ?? event.nm_id;
  const nmId = nmIdRaw != null && nmIdRaw !== "" ? String(nmIdRaw) : null;
  const problemInstanceId = event.problem_instance_id != null ? String(event.problem_instance_id) : null;
  const actionId = event.action_id != null ? String(event.action_id) : null;

  const links: ContextLink[] = [];

  // Action Center
  if (problemInstanceId) {
    links.push({
      key: "action_center",
      label: "Открыть задачу",
      to: "/action-center",
      search: { problem_instance_id: problemInstanceId },
    });
  } else if (actionId) {
    links.push({
      key: "action_center",
      label: "Открыть задачу",
      to: "/action-center",
      search: { action_id: actionId },
    });
  }

  // Product360
  if (nmId) {
    links.push({
      key: "product360",
      label: "Открыть товар",
      to: "/products/$nmId",
      params: { nmId },
    });
    links.push({
      key: "product_results",
      label: "Все результаты по товару",
      to: "/results",
      search: { nm_id: nmId },
    });
  }

  // Data Fix
  if (isDataBlockerResult(event)) {
    if (nmId && problemInstanceId) {
      links.push({
        key: "data_fix",
        label: "Открыть исправление данных",
        to: "/data-fix",
        search: { problem_instance_id: problemInstanceId, nm_id: nmId },
      });
    } else if (nmId) {
      links.push({
        key: "data_fix",
        label: "Открыть исправление данных",
        to: "/data-fix",
        search: { nm_id: nmId },
      });
    } else {
      links.push({
        key: "data_fix",
        label: "Открыть исправление данных",
        to: "/data-fix",
        disabled: true,
        disabledReason: "Нет nmID для перехода",
      });
    }
  }

  // Checker
  if (isCheckerResult(event)) {
    if (nmId) {
      links.push({
        key: "checker",
        label: "Открыть Checker",
        to: "/checker/$nmId",
        params: { nmId },
        search: problemInstanceId ? { problem_instance_id: problemInstanceId } : undefined,
      });
    } else {
      links.push({
        key: "checker",
        label: "Открыть Checker",
        to: "/checker/$nmId",
        disabled: true,
        disabledReason: "Нет nmID для перехода",
      });
    }
  }

  return links;
}

export function formatConfidenceValue(event: unknown): string {
  if (!isRecord(event)) return "—";
  const c = event.confidence ?? event.confidence_label ?? event.confidence_value;
  if (c == null || c === "") return "—";
  if (typeof c === "number" && Number.isFinite(c)) {
    const pct = Math.abs(c) <= 1 ? c * 100 : c;
    return `${Math.round(pct)}%`;
  }
  const s = String(c).toLowerCase();
  const map: Record<string, string> = {
    high: "Высокая",
    confirmed: "Высокая",
    medium: "Средняя",
    mid: "Средняя",
    low: "Низкая",
    высокая: "Высокая",
    средняя: "Средняя",
    низкая: "Низкая",
  };
  return map[s] ?? String(c);
}

export function hasEvidence(event: unknown): boolean {
  if (!isRecord(event)) return false;
  if (event.evidence_ledger != null) return true;
  const p = isRecord(event.payload) ? event.payload : {};
  return p.evidence_ledger != null;
}
