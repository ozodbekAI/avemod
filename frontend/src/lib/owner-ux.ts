import { formatDateTime, formatMoney } from "@/lib/format";

export type MetricTrustState = "final" | "preliminary" | "needs_data" | "system_sync";

export type MetricBreakdownRow = {
  label: string;
  value: number | string | null | undefined;
  operation?: "plus" | "minus" | "equals" | "info";
  note?: string | null;
};

export type MetricBreakdown = {
  title: string;
  value: number | string | null | undefined;
  formula: string;
  rows: MetricBreakdownRow[];
  sources: string[];
  period?: { from?: string | null; to?: string | null } | string | null;
  lastSyncedAt?: string | null;
  trustState: MetricTrustState;
};

export type DataFreshnessDomain = "sales" | "finance" | "stocks" | "ads" | "costs";

export type DataFreshnessItem = {
  label: string;
  lastSyncedAt: string | null;
  status: string | null;
  source?: string | null;
};

export type DataFreshness = Record<DataFreshnessDomain, DataFreshnessItem>;

export const TRUST_LABEL: Record<MetricTrustState, string> = {
  final: "Финально",
  preliminary: "Предварительно",
  needs_data: "Нет данных",
  system_sync: "Автосверка",
};

export const SYSTEM_HANDLED_DQ_CODES = new Set([
  "finance_reconciliation_mismatch",
  "finance_without_sale",
  "sale_without_finance",
]);

export function isSystemHandledCode(code: unknown): boolean {
  return typeof code === "string" && SYSTEM_HANDLED_DQ_CODES.has(code);
}

export function formatBreakdownValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "нет данных";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "нет данных";
    return formatMoney(value);
  }
  return String(value);
}

export function formatBreakdownPeriod(period: MetricBreakdown["period"]): string {
  if (!period) return "Период не указан";
  if (typeof period === "string") return period;
  const from = period.from ?? null;
  const to = period.to ?? null;
  if (!from && !to) return "Период не указан";
  if (from && to) return `${from} — ${to}`;
  return from ?? to ?? "Период не указан";
}

export function formatSyncTime(value: string | null | undefined): string {
  if (!value) return "синхронизации нет";
  try {
    return formatDateTime(value);
  } catch {
    return value;
  }
}
