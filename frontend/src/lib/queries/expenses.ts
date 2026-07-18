// Query options for the new WB expense endpoints.
import { queryOptions } from "@tanstack/react-query";
import { api, ApiError } from "@/lib/api";
import { API_ENDPOINTS, buildBizQuery } from "@/lib/endpoints";

export interface ExpenseParams {
  accountId: number | null | undefined;
  dateFrom: string;
  dateTo: string;
}

export type ExpenseGroupBy = "category" | "source" | "sku" | "nm" | "day";

export interface BreakdownItem {
  group_key?: string | null;
  label?: string | null;
  category: string;
  category_label?: string | null;
  amount: number | null;
  share_percent?: number | null;
  source?: string | null;
  is_final?: boolean | null;
  sku_id?: number | null;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  stat_date?: string | null;
  row_count?: number | null;
  rows_count?: number | null;
}

export interface BreakdownResponse {
  total_expenses?: number | null;
  total_wb_expenses?: number | null;
  total_seller_expenses?: number | null;
  total_ad_expenses?: number | null;
  logistics_total?: number | null;
  logistics_share_percent?: number | null;
  items?: BreakdownItem[];
  // optional extras the backend may include
  revenue_final?: number | null;
  seller_cogs?: number | null;
  seller_other_expense?: number | null;
  ad_spend_final?: number | null;
  ad_spend_source?: string | null;
  net_profit_after_all_expenses?: number | null;
  source_of_truth?: string | null;
}

export interface ProfitCascadeChild {
  code: string;
  label: string;
  amount?: number | null;
  share_percent?: number | null;
  source?: string | null;
  ad_spend_operational?: number | null;
  ad_spend_finance?: number | null;
  ad_spend_source?: string | null;
}
export interface ProfitCascadeGroup {
  code: string;
  label: string;
  amount?: number | null;
  sign?: "income" | "expense" | string | null;
  children?: ProfitCascadeChild[];
}
export interface ProfitCascadeRevenue {
  code?: string | null;
  label?: string | null;
  amount?: number | null;
  sign?: string | null;
}
export interface ProfitCascadeTotals {
  gross_revenue?: number | null;
  seller_cogs?: number | null;
  seller_other_expense?: number | null;
  total_seller_expenses?: number | null;
  total_wb_expenses?: number | null;
  total_ad_expenses?: number | null;
  additional_income?: number | null;
  net_profit_after_all_expenses?: number | null;
  logistics_total?: number | null;
  logistics_share_percent?: number | null;
}
export interface ProfitCascadeValidation {
  groups_match_children?: boolean | null;
  profit_formula_valid?: boolean | null;
  issues?: string[] | null;
}
export interface ProfitCascadeBody {
  revenue?: ProfitCascadeRevenue | null;
  groups?: ProfitCascadeGroup[];
  totals?: ProfitCascadeTotals | null;
  validation?: ProfitCascadeValidation | null;
}
export interface ProfitCascadeResponse {
  account_id?: number;
  date_from?: string | null;
  date_to?: string | null;
  currency?: string;
  source_of_truth?: string;
  financial_final?: boolean;
  operational_trusted?: boolean;
  trust_state?: string;
  cascade?: ProfitCascadeBody | null;
}

export interface LogisticsResponse {
  total_logistics?: number | null;
  total_wb_logistics?: number | null;
  total_wb_logistics_rebill?: number | null;
  logistics_share_percent?: number | null;
  delivery_to_client?: number | null;
  return_from_client?: number | null;
  cancellation_to_client?: number | null;
  cancellation_from_client?: number | null;
  seller_initiated_return?: number | null;
  defect_return?: number | null;
  by_logistics_type?: Array<{
    logistics_type?: string | null;
    label?: string | null;
    amount?: number | null;
    count?: number | null;
  }>;
  by_bonus_type_name?: Array<{
    group_key?: string | null;
    label?: string | null;
    bonus_type_name?: string | null;
    amount?: number | null;
    count?: number | null;
  }>;
  by_seller_oper_name?: Array<{
    group_key?: string | null;
    label?: string | null;
    amount?: number | null;
    count?: number | null;
    row_count?: number | null;
  }>;
  by_sku?: Array<{
    group_key?: string | null;
    sku_id?: number | null;
    label?: string | null;
    amount?: number | null;
    count?: number | null;
    row_count?: number | null;
  }>;
  by_nm?: Array<{
    nm_id?: number | null;
    vendor_code?: string | null;
    amount?: number | null;
    count?: number | null;
  }>;
  by_day?: Array<{ date?: string | null; amount?: number | null }>;
}

export interface ExpenseReportRow {
  report_id?: number | string | null;
  rrd_id?: number | string | null;
  date?: string | null;
  nm_id?: number | null;
  sku_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  category?: string | null;
  category_label?: string | null;
  amount?: number | null;
  source_field?: string | null;
  seller_oper_name?: string | null;
  bonus_type_name?: string | null;
  logistics_type?: string | null;
  srid?: string | null;
  order_id?: string | number | null;
  is_allocated_to_sku?: boolean | null;
}

export function expensesBreakdownQueryOptions(
  p: ExpenseParams & {
    groupBy?: ExpenseGroupBy;
    includeUnallocated?: boolean;
  },
) {
  const groupBy = p.groupBy ?? "category";
  const includeUnallocated = p.includeUnallocated ?? true;
  return queryOptions<BreakdownResponse>({
    queryKey: [
      "expenses-breakdown",
      p.accountId,
      p.dateFrom,
      p.dateTo,
      groupBy,
      includeUnallocated,
    ],
    enabled: !!p.accountId,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
    queryFn: ({ signal }) =>
      api<BreakdownResponse>(API_ENDPOINTS.money.expensesBreakdown, {
        query: buildBizQuery({
          accountId: p.accountId,
          dateFrom: p.dateFrom,
          dateTo: p.dateTo,
          extra: {
            group_by: groupBy,
            include_unallocated: includeUnallocated,
          },
        }),
        signal,
      }),
  });
}

export function expensesLogisticsQueryOptions(p: ExpenseParams) {
  return queryOptions<LogisticsResponse>({
    queryKey: ["expenses-logistics", p.accountId, p.dateFrom, p.dateTo],
    enabled: !!p.accountId,
    staleTime: 5 * 60 * 1000,
    queryFn: ({ signal }) =>
      api<LogisticsResponse>(API_ENDPOINTS.money.expensesLogistics, {
        query: buildBizQuery({
          accountId: p.accountId,
          dateFrom: p.dateFrom,
          dateTo: p.dateTo,
        }),
        signal,
      }),
  });
}

export function expensesReportRowsQueryOptions(
  p: ExpenseParams & {
    category?: string;
    skuId?: number | null;
    nmId?: number | null;
    amountMin?: number | null;
    amountMax?: number | null;
    amountExact?: number | null;
    search?: string | null;
    sourceField?: string | null;
    sellerOperName?: string | null;
    allocated?: boolean | null;
    limit?: number;
    offset?: number;
    enabled?: boolean;
  },
) {
  const limit = p.limit ?? 100;
  const offset = p.offset ?? 0;
  return queryOptions<
    ExpenseReportRow[] | { items: ExpenseReportRow[]; total?: number }
  >({
    queryKey: [
      "expenses-report-rows",
      p.accountId,
      p.dateFrom,
      p.dateTo,
      p.category,
      p.skuId,
      p.nmId,
      p.amountMin,
      p.amountMax,
      p.amountExact,
      p.search,
      p.sourceField,
      p.sellerOperName,
      p.allocated,
      limit,
      offset,
    ],
    enabled:
      (p.enabled ?? true) &&
      !!p.accountId &&
      (!!p.category || p.skuId != null || p.nmId != null || !!p.search),
    staleTime: 2 * 60 * 1000,
    queryFn: ({ signal }) =>
      api(API_ENDPOINTS.money.expensesReportRows, {
        query: buildBizQuery({
          accountId: p.accountId,
          dateFrom: p.dateFrom,
          dateTo: p.dateTo,
          limit,
          offset,
          extra: {
            category: p.category || undefined,
            sku_id: p.skuId ?? undefined,
            nm_id: p.nmId ?? undefined,
            amount_min: p.amountMin ?? undefined,
            amount_max: p.amountMax ?? undefined,
            amount_exact: p.amountExact ?? undefined,
            search: p.search || undefined,
            source_field: p.sourceField || undefined,
            seller_oper_name: p.sellerOperName || undefined,
            allocated: p.allocated ?? undefined,
          },
        }),
        signal,
      }) as Promise<
        ExpenseReportRow[] | { items: ExpenseReportRow[]; total?: number }
      >,
  });
}

export function profitCascadeQueryOptions(p: ExpenseParams) {
  return queryOptions<ProfitCascadeResponse | null>({
    queryKey: ["profit-cascade", p.accountId, p.dateFrom, p.dateTo],
    enabled: !!p.accountId,
    staleTime: 5 * 60 * 1000,
    placeholderData: (prev) => prev,
    retry: false,
    queryFn: async ({ signal }) => {
      try {
        return await api<ProfitCascadeResponse>(
          API_ENDPOINTS.money.profitCascade,
          {
            query: buildBizQuery({
              accountId: p.accountId,
              dateFrom: p.dateFrom,
              dateTo: p.dateTo,
            }),
            signal,
          },
        );
      } catch (e) {
        if (e instanceof ApiError && (e.status === 404 || e.status === 501))
          return null;
        throw e;
      }
    },
  });
}

export const CATEGORY_LABELS: Record<string, string> = {
  wb_logistics: "Логистика Вайлдберриз",
  wb_logistics_rebill: "Перевыставленная логистика Вайлдберриз",
  storage: "Хранение",
  payment_processing: "Эквайринг",
  pvz_reward: "ПВЗ",
  penalty: "Штрафы",
  deduction: "Удержания",
  acceptance: "Приемка",
  wb_commission: "Комиссия Вайлдберриз",
  wb_other: "Прочие расходы Вайлдберриз",
  marketing_deduction: "Реклама / продвижение",
  seller_cogs: "Себестоимость",
  seller_other_expense: "Прочие расходы продавца",
  compensation: "Доплаты / компенсации",
  surcharge: "Доплаты / компенсации",
  additional_payment: "Доплаты / компенсации",
  other_or_rounding_delta: "Прочие / округление",
  other_wb_expenses: "Прочие расходы Вайлдберриз",
  unclassified_wb_expenses: "Неразобранные расходы Вайлдберриз",
  loyalty: "Лояльность и кешбэк",
};

export function categoryLabel(
  cat?: string | null,
  fallback?: string | null,
): string {
  if (!cat) return fallback || "—";
  return CATEGORY_LABELS[cat] || fallback || cat;
}

export function formatMoneyRu(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toLocaleString("ru-RU", { maximumFractionDigits: 0 }) + " ₽";
}

export function formatPercent(
  v: number | null | undefined,
  digits = 1,
): string {
  if (v == null || Number.isNaN(v)) return "—";
  return v.toFixed(digits) + "%";
}
