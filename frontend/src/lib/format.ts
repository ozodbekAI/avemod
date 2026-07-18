// Форматтеры. null НИКОГДА не возвращается как 0.

const NBSP = "\u202F";

/**
 * Состояние расчёта значения.
 * Передавайте, чтобы отличить "ещё нет данных" от "посчитано и равно 0".
 *   { state: "not_computable", reason: "нет себестоимости" } → "не рассчитано: нет себестоимости"
 *   { state: "pending" } → "расчёт выполняется"
 *   { state: "ok" } или undefined → обычное форматирование
 */
export type ValueState =
  | { state?: "ok" | "final" | "preliminary" }
  | { state: "not_computable"; reason?: string }
  | { state: "pending" }
  | { state: "missing"; reason?: string };

export type FormatMoneyOpts = ValueState & { currency?: string };

function isOpts(v: unknown): v is FormatMoneyOpts {
  return typeof v === "object" && v !== null;
}

/**
 * formatMoney(value, currency?) — back-compat string form.
 * formatMoney(value, { state, reason, currency? }) — рекомендуемая форма.
 *
 * null/undefined  → "не рассчитано"
 * 0               → "0 ₽"
 * not_computable  → "не рассчитано[: reason]"
 * pending         → "расчёт выполняется"
 */
export function formatMoney(
  value: number | null | undefined,
  opts: FormatMoneyOpts | string = "₽"
): string {
  const o: FormatMoneyOpts = typeof opts === "string" ? { currency: opts } : opts;
  const currency = o.currency ?? "₽";
  const state = (o as any).state as string | undefined;
  const reason = (o as any).reason as string | undefined;

  if (state === "pending") return "расчёт выполняется";
  if (state === "not_computable" || state === "missing") {
    return reason ? `не рассчитано: ${reason}` : "не рассчитано";
  }
  if (value === null || value === undefined || Number.isNaN(value)) {
    return reason ? `не рассчитано: ${reason}` : "не рассчитано";
  }
  const rounded = Math.round(value);
  const s = Math.abs(rounded).toString().replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
  return `${rounded < 0 ? "−" : ""}${s}${NBSP}${currency}`;
}

export function formatMoneyCompact(value: number | null | undefined, currency = "₽"): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const abs = Math.abs(value);
  const sign = value < 0 ? "−" : "";
  if (abs >= 1_000_000) return `${sign}${(abs / 1_000_000).toFixed(1)}M${NBSP}${currency}`;
  if (abs >= 1_000) return `${sign}${(abs / 1_000).toFixed(1)}k${NBSP}${currency}`;
  return `${sign}${Math.round(abs)}${NBSP}${currency}`;
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return Math.round(value).toString().replace(/\B(?=(\d{3})+(?!\d))/g, NBSP);
}

export function formatConfidence(conf: string | null | undefined): string {
  switch (conf) {
    case "high": return "Высокая точность";
    case "medium": return "Приблизительно";
    case "low": return "Низкая точность";
    default: return "—";
  }
}

export function formatDate(d: string | null | undefined): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch { return d; }
}

export function formatDateTime(d: string | null | undefined): string {
  if (!d) return "—";
  try {
    return new Date(d).toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return d; }
}
