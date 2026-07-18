// Категоризация финансовых проблем/блокеров по коду.
// Используется на /money для группировки в разделе «Финансовые проблемы».

export type FinanceCategory =
  | "reconciliation"
  | "cost"
  | "margin"
  | "expense"
  | "ads"
  | "documents"
  | "data_blockers"
  | "system";

export const FINANCE_CATEGORY_LABEL: Record<FinanceCategory, string> = {
  reconciliation: "Расхождения",
  cost: "Себестоимость",
  margin: "Маржа и прибыль",
  expense: "Расходы",
  ads: "Реклама",
  documents: "Документы",
  data_blockers: "Блокеры данных",
  system: "Системные проверки",
};

export const FINANCE_CATEGORY_ORDER: FinanceCategory[] = [
  "reconciliation",
  "cost",
  "margin",
  "expense",
  "ads",
  "documents",
  "data_blockers",
  "system",
];

export function categorizeFinanceCode(code?: string | null): FinanceCategory {
  const c = String(code ?? "").toLowerCase();
  if (!c) return "data_blockers";
  if (/reconc|mismatch|finance_without_sale|sale_without_finance|sales_without_finance|order_without_sale/.test(c))
    return "reconciliation";
  if (/system|investigation|integrity|sync|self_check/.test(c)) return "system";
  if (/cost|cogs|supplier|missing_cost/.test(c)) return "cost";
  if (/ads|ad_spend|campaign|drr/.test(c)) return "ads";
  if (/expense|unclassified|unallocated/.test(c)) return "expense";
  if (/document|invoice|unpaid|duplicate_doc/.test(c)) return "documents";
  if (/profit|margin|negative_unit|unprofitable|loss/.test(c)) return "margin";
  return "data_blockers";
}

export function isFinanceBlocker(code?: string | null): boolean {
  const c = String(code ?? "").toLowerCase();
  if (!c) return false;
  // Фильтруем нефинансовые (карточка, фото, seo и т.п.), чтобы раздел был про деньги.
  if (/card_quality|photo|seo|content|title|description|listing/.test(c)) return false;
  return true;
}
