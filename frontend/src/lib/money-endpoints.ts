// Central API mapping for money-control frontend.
// Thin wrappers — all paths come from API_ENDPOINTS, all business queries
// flow through buildBizQuery so account_id / date_from / date_to are always
// attached.

import { api, ApiError } from "./api";
import type {
  MMoneySummary,
  MCardItem,
  MDataBlocker,
  MDataBlockersResponse,
  Paginated,
  DashboardDataHealth,
  DataQualityIssuesPage,
} from "./api";
import { API_ENDPOINTS, buildBizQuery } from "./endpoints";

export interface BizParams {
  accountId: number;
  dateFrom: string;
  dateTo: string;
  limit?: number;
  offset?: number;
  search?: string;
  subjectName?: string;
  status?: string;
  onlyDiff?: boolean;
  sortBy?: string;
  sortDir?: "asc" | "desc";
}

function baseQ(p: BizParams) {
  return buildBizQuery({
    accountId: p.accountId,
    dateFrom: p.dateFrom,
    dateTo: p.dateTo,
    limit: p.limit,
    offset: p.offset,
    extra: {
      ...(p.search ? { search: p.search } : {}),
      ...(p.subjectName ? { subject_name: p.subjectName } : {}),
      ...(p.status ? { status: p.status } : {}),
      ...(p.onlyDiff ? { only_diff: true } : {}),
      ...(p.sortBy ? { sort_by: p.sortBy } : {}),
      ...(p.sortDir ? { sort_dir: p.sortDir } : {}),
    },
  });
}

async function tryThen<T>(
  primary: () => Promise<T>,
  fallback: () => Promise<T>,
): Promise<T> {
  try {
    return await primary();
  } catch (e) {
    if (e instanceof ApiError && (e.status === 404 || e.status === 501)) {
      return fallback();
    }
    throw e;
  }
}

/* ─── 1) Money dashboard ────────────────────────────────────────────── */
export function fetchMoneySummary(p: BizParams, signal?: AbortSignal) {
  return tryThen<MMoneySummary>(
    () =>
      api<MMoneySummary>(API_ENDPOINTS.money.summary, {
        query: { ...baseQ(p), include_control_panel: false },
        signal,
      }),
    async () => {
      const [owner, health] = await Promise.all([
        api<any>(API_ENDPOINTS.dashboard.owner, {
          query: baseQ(p),
          signal,
        }).catch(() => null),
        api<DashboardDataHealth>(API_ENDPOINTS.dashboard.dataHealth, {
          query: baseQ(p),
          signal,
        }).catch(() => null),
      ]);
      return composeSummaryFromLegacy(owner, health);
    },
  );
}

/* ─── 2) Cards / articles list ──────────────────────────────────────── */
export function fetchMoneyArticles(p: BizParams) {
  return tryThen<Paginated<MCardItem> | MCardItem[]>(
    () =>
      api<Paginated<MCardItem> | MCardItem[]>(API_ENDPOINTS.money.articles, {
        query: baseQ(p),
      }),
    () =>
      api<Paginated<MCardItem> | MCardItem[]>(
        API_ENDPOINTS.catalog.controlSkus,
        { query: baseQ(p) },
      ),
  );
}

/* ─── 3) Article detail ─────────────────────────────────────────────── */
export function fetchArticleDetail(nmId: number, p: BizParams) {
  return tryThen<any>(
    () => api(API_ENDPOINTS.money.articleDetail(nmId), { query: baseQ(p) }),
    () =>
      api(API_ENDPOINTS.dashboard.articleAudit, {
        query: { ...baseQ(p), nm_id: nmId },
      }),
  );
}

/* ─── 4) SKU detail ─────────────────────────────────────────────────── */
// Primary owner endpoint: /money/cards/{sku_id} (secondary to nm_id article view).
// Falls back to /skus/{id} only if the money endpoint is not present.
export function fetchSkuDetail(skuId: number, p: BizParams) {
  return tryThen<any>(
    () => api(API_ENDPOINTS.money.cardDetail(skuId), { query: baseQ(p) }),
    () =>
      api(API_ENDPOINTS.catalog.controlSkuDetail(skuId), { query: baseQ(p) }),
  );
}
export function fetchCoreSku(
  skuId: number,
  p: Pick<BizParams, "dateFrom" | "dateTo">,
) {
  return api(API_ENDPOINTS.catalog.coreSkuDetail(skuId), {
    query: { date_from: p.dateFrom, date_to: p.dateTo },
  });
}

/* ─── 5) Actions ────────────────────────────────────────────────────── */
export function fetchMoneyActions(
  p: BizParams & { groupBy?: "article" | "sku" },
) {
  const q = { ...baseQ(p), group_by: p.groupBy ?? "article" };
  return tryThen<any>(
    () => api(API_ENDPOINTS.money.actions, { query: q }),
    () => api(API_ENDPOINTS.actions.legacyList, { query: baseQ(p) }),
  );
}
export function fetchMoneyActionsToday(p: BizParams) {
  return api(API_ENDPOINTS.money.actionsToday, {
    query: { ...baseQ(p), include_groups: false },
  });
}
export function updateAction(
  actionId: number | string,
  body: Record<string, unknown>,
) {
  return api(API_ENDPOINTS.actions.update(actionId), { method: "PATCH", body });
}

/* ─── 6) Data Fix ───────────────────────────────────────────────────── */
export function fetchDataBlockers(p: BizParams) {
  return tryThen<MDataBlockersResponse>(
    () =>
      api<MDataBlockersResponse>(API_ENDPOINTS.money.dataBlockers, {
        query: baseQ(p),
      }),
    () =>
      Promise.all([
        api<DashboardDataHealth>(API_ENDPOINTS.dashboard.dataHealth, {
          query: baseQ(p),
        }),
        api<DataQualityIssuesPage>(API_ENDPOINTS.dq.issues, {
          query: {
            account_id: p.accountId,
            only_open: true,
            date_from: p.dateFrom,
            date_to: p.dateTo,
            limit: p.limit ?? 100,
          },
        }).catch(() => null),
      ]).then(([health, issues]) =>
        composeDataBlockersFromLegacy(health, issues, p),
      ),
  );
}

/* ─── 7) Costs ──────────────────────────────────────────────────────── */
export function fetchCostsRows(p: BizParams) {
  return api(API_ENDPOINTS.costs.rows, {
    query: { account_id: p.accountId, limit: p.limit, offset: p.offset },
  });
}
export function fetchCostsImports(accountId?: number | null) {
  return api(API_ENDPOINTS.costs.imports, {
    query: { account_id: accountId ?? undefined },
  });
}
export function fetchCostsUnresolved(accountId: number) {
  return api(API_ENDPOINTS.costs.unresolved, {
    query: { account_id: accountId },
  });
}
export interface CostsMissingItem {
  sku_id?: number;
  nm_id?: number | null;
  vendor_code?: string | null;
  barcode?: string | null;
  tech_size?: string | null;
  product_title?: string | null;
  affected_revenue?: number | null;
}
export interface CostsMissingResponse {
  total: number;
  limit?: number;
  offset?: number;
  summary?: {
    missing_sku_count?: number;
    affected_revenue?: number;
    revenue_cost_coverage_percent?: number;
  };
  items: CostsMissingItem[];
}
export function fetchCostsMissing(
  accountId: number,
  opts: {
    limit?: number;
    offset?: number;
    dateFrom?: string;
    dateTo?: string;
    onlyRevenue?: boolean;
  } = {},
) {
  return api<CostsMissingResponse>(API_ENDPOINTS.costs.missing, {
    query: {
      account_id: accountId,
      limit: opts.limit ?? 50,
      offset: opts.offset ?? 0,
      date_from: opts.dateFrom,
      date_to: opts.dateTo,
      only_revenue: opts.onlyRevenue,
    },
  });
}
export async function downloadCostsTemplate(accountId: number): Promise<Blob> {
  const res = (await api<Response>(API_ENDPOINTS.costs.template, {
    query: { account_id: accountId },
    raw: true,
  })) as unknown as Response;
  return res.blob();
}
export function uploadCostsFile(formData: FormData) {
  return api(API_ENDPOINTS.costs.upload, { method: "POST", formData });
}
export function previewCostsUpload(uploadId: number | string) {
  return api(API_ENDPOINTS.costs.previewUpload(uploadId));
}
export function confirmCostsUpload(
  uploadId: number | string,
  body?: Record<string, unknown>,
) {
  return api(API_ENDPOINTS.costs.confirmUpload(uploadId), {
    method: "POST",
    body: body ?? {},
  });
}
export function patchCost(
  costId: number | string,
  body: Record<string, unknown>,
) {
  return api(API_ENDPOINTS.costs.updateRow(costId), { method: "PATCH", body });
}
export function saveInlineCosts(body: Record<string, unknown>) {
  return api(API_ENDPOINTS.costs.inlineSave, { method: "POST", body });
}

/* ─── 8) Ads ────────────────────────────────────────────────────────── */
export function fetchAdsEfficiency(p: BizParams) {
  return api(API_ENDPOINTS.ads.efficiency, { query: baseQ(p) });
}
export function fetchAdsStats(p: BizParams) {
  return api(API_ENDPOINTS.ads.stats, { query: baseQ(p) });
}
export function fetchAdsCampaigns(accountId: number) {
  return api(API_ENDPOINTS.ads.campaigns, { query: { account_id: accountId } });
}

/* ─── 9) Pricing ────────────────────────────────────────────────────── */
export function fetchPricingSafety(p: BizParams) {
  return api(API_ENDPOINTS.pricing.safety, { query: baseQ(p) });
}
export function simulatePricing(body: Record<string, unknown>) {
  return api(API_ENDPOINTS.pricing.simulate, { method: "POST", body });
}

/* ─── 10) Purchase plan ─────────────────────────────────────────────── */
export interface PurchasePlanParams extends BizParams {
  groupBy?: "article" | "sku";
  includeBlocked?: boolean;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  statusFilter?: string;
  search?: string;
  profitFilter?: string;
  dataFilter?: string;
  stockFilter?: string;
}
export function fetchPurchasePlan(p: PurchasePlanParams) {
  const q = buildBizQuery({
    accountId: p.accountId,
    dateFrom: p.dateFrom,
    dateTo: p.dateTo,
    limit: p.limit,
    offset: p.offset,
    extra: {
      ...(p.groupBy ? { group_by: p.groupBy } : {}),
      ...(p.includeBlocked != null
        ? { include_blocked: p.includeBlocked }
        : {}),
      ...(p.sortBy ? { sort_by: p.sortBy } : {}),
      ...(p.sortDir ? { sort_dir: p.sortDir } : {}),
      ...(p.statusFilter ? { status_filter: p.statusFilter } : {}),
      ...(p.search ? { search: p.search } : {}),
      ...(p.profitFilter ? { profit_filter: p.profitFilter } : {}),
      ...(p.dataFilter ? { data_filter: p.dataFilter } : {}),
      ...(p.stockFilter ? { stock_filter: p.stockFilter } : {}),
    },
  });
  return api(API_ENDPOINTS.inventory.purchasePlan, { query: q });
}

/* ─── 11) Settings ──────────────────────────────────────────────────── */
export function fetchBusinessSettings(accountId: number) {
  return api(API_ENDPOINTS.settings.business, {
    query: { account_id: accountId },
  });
}
export function patchBusinessSettings(
  accountId: number,
  body: Record<string, unknown> | object,
) {
  return api(API_ENDPOINTS.settings.business, {
    method: "PATCH",
    query: { account_id: accountId },
    body: body as Record<string, unknown>,
  });
}

/* ─── 12) Finance / reconciliation ──────────────────────────────────── */
export function fetchFinanceReports(p: BizParams) {
  return api(API_ENDPOINTS.finance.reports, { query: baseQ(p) });
}
export function fetchFinanceReportRows(p: BizParams) {
  return api(API_ENDPOINTS.finance.rows, { query: baseQ(p) });
}
export function fetchFinanceReconciliation(p: BizParams) {
  return api(API_ENDPOINTS.finance.reconciliation, { query: baseQ(p) });
}
export function fetchBusinessDaily(p: BizParams) {
  return api(API_ENDPOINTS.finance.businessDaily, { query: baseQ(p) });
}
export function fetchAccountExpenseDaily(p: BizParams) {
  return api(API_ENDPOINTS.finance.accountExpenseDaily, { query: baseQ(p) });
}
export function fetchReconciliationDaily(p: BizParams) {
  return api(API_ENDPOINTS.finance.reconciliationDaily, { query: baseQ(p) });
}

/* ─── Legacy compose helper ─────────────────────────────────────────── */
function composeSummaryFromLegacy(
  owner: any,
  health: DashboardDataHealth | null,
): MMoneySummary {
  return {
    meta: {
      account_id: owner?.account_id ?? null,
      account_name: owner?.account_name ?? null,
      date_from: owner?.date_from ?? "",
      date_to: owner?.date_to ?? "",
      generated_at: new Date().toISOString(),
      data_trust: {
        state: "test_only",
        confidence: "medium",
        blocked_reasons: health?.open_issues_total
          ? ["open_blocking_dq_issues"]
          : [],
        human_message: "Сводка собрана из устаревших источников.",
      },
    } as any,
    answer: {
      title: "Предварительная сводка",
      short_text:
        "Главный эндпойнт /money/summary недоступен — данные собраны из legacy источников.",
      main_problem: null,
      main_next_step: null,
    } as any,
    kpis: {
      revenue: owner?.revenue ?? null,
      finance_confirmed_revenue: 0,
      supplier_cost_confirmed_revenue: 0,
      supplier_cost_confirmed_revenue_percent:
        health?.revenue_cost_coverage_percent ?? null,
      for_pay: 0,
      net_profit_after_ads: owner?.profit ?? null,
      margin_percent: null as any,
      roi_percent: null as any,
      cash_on_wb: null as any,
      available_for_withdraw: null as any,
      wb_expenses_total: null as any,
      stock_value: null as any,
      overstock_value: null as any,
      in_transit_value: null as any,
      stock_value_confidence: "medium",
      stock_value_reason: "",
      ad_spend: null as any,
      ads_source_spend: 0,
      ads_allocated_spend: 0,
      ads_unallocated_spend: 0,
      ads_allocation_status: "",
      unallocated_expenses: 0,
      negative_profit_sku_count: 0,
      blocked_data_sku_count: 0,
    } as any,
    money_flow: { incoming: [], outgoing: [], cash_and_stock: [] },
    risk_summary: { critical_count: 0, risks: [] },
    top_cards: {
      profitable: [],
      loss_making: [],
      stock_risk: [],
      data_blocked: [],
    },
    next_actions: [],
  };
}

function composeDataBlockersFromLegacy(
  health: DashboardDataHealth,
  issues: DataQualityIssuesPage | null,
  p: BizParams,
): MDataBlockersResponse {
  const issueItems = issues?.items ?? [];
  const blockers: MDataBlocker[] = issueItems
    .filter(
      (issue) =>
        issue.effective_financial_final_blocker ||
        issue.financial_final_blocker ||
        issue.severity === "critical" ||
        issue.severity === "error",
    )
    .map((issue) => ({
      code: issue.code,
      priority:
        issue.severity === "critical" || issue.severity === "error"
          ? "critical"
          : "high",
      title: issue.simple_reason || issue.message || issue.code,
      affected_sku_count: issue.sku_id != null ? 1 : 0,
      affected_revenue: 0,
      affected_amount: 0,
      current_value: 0,
      required_value: 1,
      unit: "issue",
      business_impact:
        issue.business_impact ||
        issue.message ||
        "Проверьте проблему качества данных.",
      how_to_fix: issue.step_by_step?.length
        ? issue.step_by_step
        : [
            issue.recommended_fix ||
              issue.first_action ||
              "Откройте исправление данных и проверьте проблему.",
          ],
      related_endpoints: [API_ENDPOINTS.dq.issues],
      exact_next_endpoint: API_ENDPOINTS.dq.issues,
      simple_reason: issue.simple_reason || issue.message || "",
      first_action: issue.first_action || issue.recommended_fix || "",
      success_check: issue.success_check ?? [],
      wait_or_fix_hint: issue.wait_or_fix_hint ?? "",
      next_screen_path: issue.next_screen_path || "/data-fix",
      next_screen_label:
        issue.next_screen_label || "Открыть исправление данных",
      source_endpoints: [API_ENDPOINTS.dq.issues],
    }));

  return {
    meta: {
      account_id: p.accountId,
      date_from: p.dateFrom,
      date_to: p.dateTo,
      currency: "RUB",
      generated_at: new Date().toISOString(),
      data_trust: {
        state: health.open_issues_total > 0 ? "data_blocked" : "trusted",
        business_trusted: health.open_issues_total === 0,
        can_generate_business_actions: health.open_issues_total === 0,
        confidence: health.open_issues_total === 0 ? "high" : "medium",
        blocked_reasons:
          health.open_issues_total > 0 ? ["open_data_quality_issues"] : [],
        human_message:
          health.open_issues_total > 0
            ? "Есть открытые проблемы качества данных."
            : "Критичных проблем качества данных нет.",
      },
    },
    overall_state: health.open_issues_total > 0 ? "data_blocked" : "trusted",
    overall_message:
      health.open_issues_total > 0
        ? "Есть открытые проблемы качества данных."
        : "Критичных блокеров нет.",
    can_generate_business_actions: health.open_issues_total === 0,
    blockers_count: blockers.length,
    warnings_count: 0,
    open_issue_summary: {},
    data_quality_summary: {
      open_issues_total: health.open_issues_total,
      all_open_issues_total: issues?.total ?? health.open_issues_total,
      blocking_open_issues_total: blockers.length,
      financial_final_blockers_total: blockers.length,
    },
    blockers,
    warnings: [],
  };
}

// Re-export for callers that want direct access
export { API_ENDPOINTS, buildBizQuery } from "./endpoints";
